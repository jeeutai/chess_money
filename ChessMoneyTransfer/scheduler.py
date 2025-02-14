import threading
import time
from datetime import datetime, timedelta

def process_scheduled_payments(db, User, Transaction, ScheduledPayment):
    """예약된 월급을 처리하는 함수"""
    current_day = datetime.now().day
    scheduled_payments = ScheduledPayment.query.filter_by(
        schedule_day=current_day,
        is_active=True
    ).all()

    for payment in scheduled_payments:
        admin = User.query.get(payment.created_by)
        if not admin or not admin.is_admin:
            continue

        regular_users = User.query.filter_by(is_admin=False).all()
        for user in regular_users:
            user.balance += payment.amount
            transaction = Transaction(
                sender_id=admin.id,
                receiver_id=user.id,
                amount=payment.amount,
                type='monthly'
            )
            db.session.add(transaction)

        db.session.commit()

def run_scheduler(app, db, User, Transaction, ScheduledPayment):
    """스케줄러 실행 함수"""
    while True:
        with app.app_context():
            current_date = datetime.now()
            try:
                process_scheduled_payments(db, User, Transaction, ScheduledPayment)
                print(f"Scheduled payments processed at: {current_date}")
            except Exception as e:
                print(f"Error processing scheduled payments: {e}")

        # 다음 자정까지 대기
        tomorrow = (current_date + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        sleep_seconds = (tomorrow - current_date).total_seconds()
        time.sleep(sleep_seconds)

def start_scheduler(app, db, User, Transaction, ScheduledPayment):
    """백그라운드에서 스케줄러 시작"""
    scheduler_thread = threading.Thread(
        target=run_scheduler,
        args=(app, db, User, Transaction, ScheduledPayment),
        daemon=True
    )
    scheduler_thread.start()
    print("Payment scheduler started")