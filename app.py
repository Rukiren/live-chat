from flask import Flask, render_template, request, session
from flask_socketio import SocketIO, emit, join_room, leave_room
from datetime import datetime, timedelta

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'
socketio = SocketIO(app)

# Store connected users, messages, and rooms
users = {}
rooms = {'general': {'users': set(), 'messages': []}}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/username')
def username():
    return render_template('username.html')

def save_message(room, username, content, is_private=False):
    timestamp = datetime.now()
    message = {
        'username': username,
        'content': content,
        'timestamp': timestamp.isoformat(),
        'type': 'private' if is_private else 'public'
    }
    rooms[room]['messages'].append(message)
    
    # Remove messages older than 2 days
    two_days_ago = timestamp - timedelta(days=2)
    rooms[room]['messages'] = [msg for msg in rooms[room]['messages'] if datetime.fromisoformat(msg['timestamp']) > two_days_ago]

@socketio.on('connect')
def handle_connect():
    print('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    if 'username' in session:
        username = session['username']
        room = session.get('room', 'general')
        leave_room(room)
        if username in rooms[room]['users']:
            rooms[room]['users'].remove(username)
        del users[request.sid]
        emit('system_message', {'content': f'{username} has left the chat.'}, room=room)
        emit('update_user_list', list(rooms[room]['users']), room=room)

@socketio.on('login')
def handle_login(data):
    username = data['username']
    room = data.get('room', 'general')
    session['username'] = username
    session['room'] = room
    users[request.sid] = username
    join_room(room)
    if room not in rooms:
        rooms[room] = {'users': set(), 'messages': []}
    rooms[room]['users'].add(username)
    emit('system_message', {'content': f'{username} has joined the chat.'}, room=room)
    emit('update_user_list', list(rooms[room]['users']), room=room)
    
    # Send last 2 days of messages
    recent_messages = get_recent_messages(room)
    emit('load_history', recent_messages)

@socketio.on('chat_message')
def handle_message(data):
    username = session.get('username', 'Anonymous')
    room = session.get('room', 'general')
    content = data['content']
    save_message(room, username, content)
    emit('chat_message', {
        'username': username,
        'content': content,
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }, room=room)

@socketio.on('private_message')
def handle_private_message(data):
    sender = session.get('username', 'Anonymous')
    recipient = data['recipient']
    content = data['content']
    room = session.get('room', 'general')
    save_message(room, sender, content, is_private=True)
    
    recipient_sid = next((sid for sid, name in users.items() if name == recipient), None)
    if recipient_sid:
        emit('private_message', {
            'username': sender,
            'content': content,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }, room=recipient_sid)
    else:
        emit('system_message', {'content': f'User {recipient} not found or offline.'}, room=request.sid)

@socketio.on('join_room')
def handle_join_room(data):
    new_room = data['room']
    old_room = session.get('room')
    username = session.get('username')
    
    if old_room != new_room:
        leave_room(old_room)
        if username in rooms[old_room]['users']:
            rooms[old_room]['users'].remove(username)
        emit('system_message', {'content': f'{username} has left the room.'}, room=old_room)
        emit('update_user_list', list(rooms[old_room]['users']), room=old_room)
        
        join_room(new_room)
        if new_room not in rooms:
            rooms[new_room] = {'users': set(), 'messages': []}
        rooms[new_room]['users'].add(username)
        session['room'] = new_room
        emit('system_message', {'content': f'{username} has joined the room.'}, room=new_room)
        emit('update_user_list', list(rooms[new_room]['users']), room=new_room)
        
        # Send recent messages history
        recent_messages = get_recent_messages(new_room)
        emit('load_history', recent_messages)

@socketio.on('create_room')
def handle_create_room(data):
    new_room = data['room']
    username = session.get('username')
    if new_room not in rooms:
        rooms[new_room] = {'users': set(), 'messages': []}
        emit('room_list', list(rooms.keys()), broadcast=True)
    
    # Automatically join the newly created room
    handle_join_room({'room': new_room})

@socketio.on('get_rooms')
def handle_get_rooms():
    emit('room_list', list(rooms.keys()))

def get_recent_messages(room):
    two_days_ago = datetime.now() - timedelta(days=2)
    return [msg for msg in rooms[room]['messages'] if datetime.fromisoformat(msg['timestamp']) > two_days_ago]

def update_user_list(room):
    users_in_room = list(rooms[room]['users'])
    emit('update_user_list', users_in_room, room=room)

if __name__ == '__main__':
    socketio.run(app, debug=True)