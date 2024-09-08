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

def save_message(room, username, content, is_private=False, recipient=None):
    timestamp = datetime.now()
    message = {
        'username': username,
        'content': content,
        'timestamp': timestamp.isoformat(),
        'type': 'private' if is_private else 'public',
        'recipient': recipient
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
    emit('load_history', rooms[room]['messages'], room=request.sid)

@socketio.on('chat_message')
def handle_chat_message(data):
    room = session.get('room', 'general')
    username = session['username']
    content = data['content']
    
    # 普通消息，廣播給所有人
    save_message(room, username, content)
    emit('chat_message', {'username': username, 'content': content, 'timestamp': datetime.now().isoformat()}, room=room)

@socketio.on('private_message')
def handle_private_message(data):
    room = session.get('room', 'general')
    username = session['username']
    content = data['content']
    recipient = data.get('recipient')  # 指定接收者

    if recipient:
        # 確認接收者在線
        recipient_sid = [sid for sid, user in users.items() if user == recipient]
        if recipient_sid:
            # 保存並發送私訊，僅給接收者與自己
            save_message(room, username, content, is_private=True, recipient=recipient)
            emit('private_message', {'username': username, 'content': content, 'timestamp': datetime.now().isoformat()}, room=recipient_sid[0])
            emit('private_message', {'username': username, 'content': content, 'timestamp': datetime.now().isoformat()}, room=request.sid)
        else:
            # 接收者不在線，通知發送者
            emit('system_message', {'content': f'User {recipient} is not online.'}, room=request.sid)
    else:
        emit('system_message', {'content': 'Recipient not specified for private message.'}, room=request.sid)

if __name__ == '__main__':
    socketio.run(app)
