import eventlet
eventlet.monkey_patch()
from dotenv import load_dotenv
load_dotenv()  # .env 파일을 로드해서 환경 변수에 반영
import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_socketio import SocketIO
import logging
from ChessMoneyTransfer.models import db  # 🔥 db를 models에서 가져옴 (순환 참조 해결)

# Flask 앱 초기화
app = Flask(__name__)

# config.py에서 설정을 가져와서 Flask 앱에 적용
app.config.from_object('ChessMoneyTransfer.config.Config')  # config.py의 Config 클래스를 불러와 설정 적용

# SQLAlchemy 초기화
db.init_app(app)

# 로그인 관리 설정
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Socket.IO 설정
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins="*", logger=True, engineio_logger=True)

# 로그 설정
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# 데이터 디렉토리 생성 (없으면 생성)
if not os.path.exists('data'):
    os.makedirs('data')

# 사용자 로딩 함수 (로그인 세션에서 사용자 정보 로드)
@login_manager.user_loader
def load_user(user_id):
    from ChessMoneyTransfer.models import User  # Import 시점 조정 (순환 참조 방지)
    return User.query.get(int(user_id))

# 데이터베이스 테이블 생성
with app.app_context():
    from ChessMoneyTransfer.models import User, Transaction, Chat
    db.create_all()
    logger.info("Database tables created successfully")

# routes는 앱 설정 후에 임포트 (순환 참조 방지)
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
