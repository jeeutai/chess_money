import os

class Config:
    # Render에서 받은 PostgreSQL 연결 URL을 설정
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'postgresql://chess_money_user:RKj8m0EVCdPnSt1ao3xHJKC4CKWtpNnL@dpg-cuo6t5d2ng1s73e447tg-a/chess_money'
    SQLALCHEMY_TRACK_MODIFICATIONS = False  # 변경 사항 추적 비활성화
