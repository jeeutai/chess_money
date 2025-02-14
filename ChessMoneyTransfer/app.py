import eventlet
eventlet.monkey_patch()
import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_socketio import SocketIO
import logging
from ChessMoneyTransfer.models import models

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or "chess_empire_secret_key"

# PostgreSQL 데이터베이스 설정
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('SQLALCHEMY_DATABASE_URI', 'postgresql://postgres:130313@localhost/chess_money')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Initialize Socket.IO with eventlet
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins="*", logger=True, engineio_logger=True)

# Create data directory if it doesn't exist
if not os.path.exists('data'):
    os.makedirs('data')

@login_manager.user_loader
def load_user(user_id):
    from models import User  # Import here to avoid circular import
    return User.query.get(int(user_id))

with app.app_context():
    from models import User, Transaction, Chat
    db.create_all()
    logger.info("Database tables created successfully")

# Import routes after app is fully configured
import routes  # noqa: E402, F401

# Socket.IO event handlers
@socketio.on('message')
def handle_message(data):
    from models import Chat
    from flask_login import current_user

    if not current_user.is_authenticated:
        return

    message = Chat(
        sender_id=current_user.id,
        message=data['message']
    )
    db.session.add(message)
    db.session.commit()

    socketio.emit('new_message', {
        'message': message.message,
        'sender_id': message.sender_id,
        'username': message.sender.username,
        'timestamp': message.timestamp.strftime('%H:%M'),
        'message_id': message.id
    })
