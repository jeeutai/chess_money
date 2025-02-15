import eventlet
eventlet.monkey_patch()

import os
from flask import Flask
from flask_login import LoginManager
from flask_socketio import SocketIO
import logging
from ChessMoneyTransfer.models import db  # 🔥 db를 models에서 가져옴 (순환 참조 해결)
import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

# 환경 변수에서 데이터베이스 URI를 불러와서 설정
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('SQLALCHEMY_DATABASE_URI')

# SQLAlchemy 초기화
db = SQLAlchemy(app)


# 로그 설정
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

# 🔥 db를 Flask 앱에 연결
db.init_app(app)

# 로그인 관리 설정
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Socket.IO 설정
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins="*", logger=True, engineio_logger=True)

# 데이터 디렉토리 생성
if not os.path.exists('data'):
    os.makedirs('data')

@login_manager.user_loader
def load_user(user_id):
    from ChessMoneyTransfer.models import User  # Import 시점 조정 (순환 참조 방지)
    return User.query.get(int(user_id))

# 🔥 데이터베이스 테이블 생성
with app.app_context():
    from ChessMoneyTransfer.models import User, Transaction, Chat
    db.create_all()
    logger.info("Database tables created successfully")

# ⚠️ routes는 app 설정이 끝난 후 import해야 함
import routes  

# Socket.IO 이벤트 핸들러
@socketio.on('message')
def handle_message(data):
    from ChessMoneyTransfer.models import Chat
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

