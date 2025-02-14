import os
import csv
from datetime import datetime
from models import User, Transaction, ScheduledPayment, Chat
from app import db

def save_chat_to_csv(message):
    """채팅 메시지를 CSV 파일에 저장"""
    csv_file = 'data/chat_history.csv'
    os.makedirs('data', exist_ok=True)

    # CSV 파일이 없으면 헤더와 함께 생성
    if not os.path.exists(csv_file):
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['timestamp', 'sender_id', 'sender_name', 'message'])

    # 메시지 추가
    with open(csv_file, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            message.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            message.sender_id,
            message.sender.username,
            message.message
        ])

def load_chat_history():
    """CSV 파일에서 채팅 히스토리 불러오기"""
    csv_file = 'data/chat_history.csv'
    messages = []

    if os.path.exists(csv_file):
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                messages.append({
                    'timestamp': datetime.strptime(row['timestamp'], '%Y-%m-%d %H:%M:%S'),
                    'sender_id': int(row['sender_id']),
                    'sender_name': row['sender_name'],
                    'message': row['message']
                })

    return messages