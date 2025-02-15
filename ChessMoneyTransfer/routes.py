from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
from ChessMoneyTransfer.app import app, db, socketio
from ChessMoneyTransfer.models import User, Transaction, Chat, ChatRead, Notice, Poll, PollOption, PollVote, ChatStatistics
from datetime import datetime, timedelta, date
from vutils import save_chat_to_csv, load_chat_history
import os
import logging

# 파일 업로드 설정
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx'}

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max-limit

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.check_password(request.form['password']):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('아이디 또는 비밀번호가 잘못되었습니다')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        if User.query.filter_by(username=username).first():
            flash('이미 존재하는 아이디입니다')
            return redirect(url_for('register'))

        user = User(username=username)
        user.set_password(request.form['password'])

        # First user becomes admin with a reasonable balance
        if User.query.count() == 0:
            user.is_admin = True
            user.balance = 100000  # 적절한 정수값으로 수정됨

        db.session.add(user)
        db.session.commit()
        flash('회원가입이 완료되었습니다')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.is_admin:
        return redirect(url_for('users'))

    transactions = Transaction.query.filter(
        (Transaction.sender_id == current_user.id) |
        (Transaction.receiver_id == current_user.id)
    ).order_by(Transaction.timestamp.desc()).all()

    return render_template('dashboard.html',
                         user=current_user,
                         transactions=transactions)

@app.route('/chat')
@login_required
def chat():
    # 데이터베이스의 최근 메시지와 CSV 파일의 히스토리 결합
    db_messages = Chat.query.order_by(Chat.timestamp.desc()).limit(100).all()
    csv_messages = load_chat_history()

    # CSV 메시지를 Chat 객체로 변환
    chat_objects = []
    for msg in csv_messages:
        sender = User.query.get(msg['sender_id'])
        if sender:
            chat = Chat(
                sender_id=msg['sender_id'],
                message=msg['message'],
                timestamp=msg['timestamp']
            )
            chat.sender = sender
            chat_objects.append(chat)

    # 모든 메시지 결합 및 정렬
    all_messages = chat_objects + db_messages
    all_messages.sort(key=lambda x: x.timestamp)

    # 고정된 공지사항 가져오기
    pinned_notices = Notice.query.filter_by(is_pinned=True).all()

    # 진행 중인 투표 가져오기
    active_polls = Poll.query.filter(
        (Poll.ends_at > datetime.utcnow()) | (Poll.ends_at.is_(None))
    ).all()

    active_users = User.query.all()
    return render_template('chat.html', 
                         messages=all_messages, 
                         active_users=active_users,
                         pinned_notices=pinned_notices,
                         active_polls=active_polls)

@app.route('/upload_file', methods=['POST'])
@login_required
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': '파일이 없습니다'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': '선택된 파일이 없습니다'}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
        filename = timestamp + filename
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        file_type = 'image' if file.filename.split('.')[-1].lower() in {'png', 'jpg', 'jpeg', 'gif'} else 'file'
        return jsonify({
            'file_url': url_for('static', filename=f'uploads/{filename}'),
            'file_type': file_type
        })

    return jsonify({'error': '허용되지 않는 파일 형식입니다'}), 400

@app.route('/search_messages')
@login_required
def search_messages():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify([])

    messages = Chat.query.filter(Chat.message.ilike(f'%{query}%')).order_by(Chat.timestamp.desc()).limit(50).all()
    return jsonify([{
        'id': msg.id,
        'message': msg.message,
        'sender': msg.sender.username,
        'timestamp': msg.timestamp.strftime('%Y-%m-%d %H:%M:%S')
    } for msg in messages])

@app.route('/mark_notifications_read', methods=['POST'])
@login_required
def mark_notifications_read():
    ChatNotification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).update({'is_read': True})
    db.session.commit()
    return jsonify({'success': True})

@socketio.on('message')
def handle_message(data):
    if not current_user.is_authenticated:
        return

    message = Chat(
        sender_id=current_user.id,
        message=data.get('message', ''),
        reply_to_id=data.get('reply_to_id'),
        file_url=data.get('file_url'),
        file_type=data.get('file_type')
    )
    db.session.add(message)
    db.session.commit()

    # CSV 파일에도 저장
    save_chat_to_csv(message)

    # 메시지 전송자의 통계 업데이트
    today = date.today()
    current_hour = datetime.now().hour
    stats = ChatStatistics.query.filter_by(
        date=today,
        hour=current_hour,
        user_id=current_user.id
    ).first()

    if not stats:
        stats = ChatStatistics(
            date=today,
            hour=current_hour,
            user_id=current_user.id
        )
        db.session.add(stats)

    stats.message_count += 1
    stats.character_count += len(data.get('message', ''))
    db.session.commit()

    # 메시지 읽음 표시 (자신의 메시지는 자동으로 읽음)
    read = ChatRead(chat_id=message.id, user_id=current_user.id)
    db.session.add(read)
    db.session.commit()

    socketio.emit('new_message', {
        'message': message.message,
        'sender_id': message.sender_id,
        'username': message.sender.username,
        'timestamp': message.timestamp.strftime('%H:%M'),
        'message_id': message.id,
        'reply_to_id': message.reply_to_id,
        'file_url': message.file_url,
        'file_type': message.file_type
    })

@app.route('/read_message/<int:message_id>', methods=['POST'])
@login_required
def read_message(message_id):
    if not ChatRead.query.filter_by(chat_id=message_id, user_id=current_user.id).first():
        read = ChatRead(chat_id=message_id, user_id=current_user.id)
        db.session.add(read)
        db.session.commit()
    return '', 204

@app.route('/message_reads/<int:message_id>')
@login_required
def message_reads(message_id):
    if not current_user.is_admin:
        return jsonify({'error': '권한이 없습니다'}), 403

    reads = ChatRead.query.filter_by(chat_id=message_id).all()
    return jsonify([{
        'username': read.user.username,
        'read_at': read.read_at.strftime('%Y-%m-%d %H:%M:%S')
    } for read in reads])

@app.route('/notice/create', methods=['POST'])
@login_required
def create_notice():
    if not current_user.is_admin:
        return jsonify({'error': '권한이 없습니다'}), 403

    data = request.get_json()
    notice = Notice(
        title=data['title'],
        content=data['content'],
        is_pinned=data.get('is_pinned', False),
        created_by=current_user.id,
        expires_at=datetime.fromisoformat(data['expires_at']) if data.get('expires_at') else None
    )
    db.session.add(notice)
    db.session.commit()

    socketio.emit('new_notice', {
        'id': notice.id,
        'title': notice.title,
        'content': notice.content,
        'is_pinned': notice.is_pinned,
        'created_at': notice.created_at.isoformat(),
        'author': current_user.username
    })

    return jsonify({'message': '공지사항이 생성되었습니다'})

@app.route('/notice/<int:notice_id>/delete', methods=['POST'])
@login_required
def delete_notice(notice_id):
    if not current_user.is_admin:
        return jsonify({'error': '권한이 없습니다'}), 403

    notice = Notice.query.get_or_404(notice_id)
    db.session.delete(notice)
    db.session.commit()

    socketio.emit('notice_deleted', {'id': notice_id})
    return jsonify({'message': '공지사항이 삭제되었습니다'})

@app.route('/poll/create', methods=['POST'])
@login_required
def create_poll():
    if not current_user.is_admin:
        return jsonify({'error': '권한이 없습니다'}), 403

    data = request.get_json()
    poll = Poll(
        question=data['question'],
        created_by=current_user.id,
        ends_at=datetime.fromisoformat(data['ends_at']) if data.get('ends_at') else None,
        is_multiple=data.get('is_multiple', False),
        is_anonymous=data.get('is_anonymous', False)
    )
    db.session.add(poll)

    for option_text in data['options']:
        option = PollOption(content=option_text)
        poll.options.append(option)

    db.session.commit()

    socketio.emit('new_poll', {
        'id': poll.id,
        'question': poll.question,
        'options': [{'id': opt.id, 'content': opt.content} for opt in poll.options],
        'ends_at': poll.ends_at.isoformat() if poll.ends_at else None,
        'is_multiple': poll.is_multiple,
        'is_anonymous': poll.is_anonymous
    })

    return jsonify({'message': '투표가 생성되었습니다'})

@app.route('/poll/<int:poll_id>/vote', methods=['POST'])
@login_required
def vote_poll(poll_id):
    data = request.get_json()
    poll = Poll.query.get_or_404(poll_id)

    if poll.ends_at and poll.ends_at < datetime.utcnow():
        return jsonify({'error': '종료된 투표입니다'}), 400

    # 기존 투표 삭제
    PollVote.query.filter_by(poll_id=poll_id, user_id=current_user.id).delete()

    # 새 투표 추가
    option_ids = data['option_ids'] if isinstance(data['option_ids'], list) else [data['option_ids']]
    for option_id in option_ids:
        vote = PollVote(poll_id=poll_id, option_id=option_id, user_id=current_user.id)
        db.session.add(vote)

    db.session.commit()

    # 투표 결과 집계
    results = {}
    for option in poll.options:
        votes = PollVote.query.filter_by(option_id=option.id).count()
        voters = []
        if not poll.is_anonymous:
            voters = [vote.user.username for vote in PollVote.query.filter_by(option_id=option.id).all()]
        results[option.id] = {
            'content': option.content,
            'votes': votes,
            'voters': voters
        }

    socketio.emit('poll_updated', {
        'poll_id': poll_id,
        'results': results
    })

    return jsonify({'message': '투표가 완료되었습니다'})

@app.route('/poll/<int:poll_id>/delete', methods=['POST'])
@login_required
def delete_poll(poll_id):
    if not current_user.is_admin:
        return jsonify({'error': '권한이 없습니다'}), 403

    poll = Poll.query.get_or_404(poll_id)
    db.session.delete(poll)
    db.session.commit()

    socketio.emit('poll_deleted', {'id': poll_id})
    return jsonify({'message': '투표가 삭제되었습니다'})

@app.route('/chat/statistics')
@login_required
def chat_statistics():
    if not current_user.is_admin:
        return jsonify({'error': '권한이 없습니다'}), 403

    # 일별 통계
    daily_stats = db.session.query(
        ChatStatistics.date,
        db.func.sum(ChatStatistics.message_count).label('messages'),
        db.func.count(db.distinct(ChatStatistics.user_id)).label('active_users')
    ).group_by(ChatStatistics.date).order_by(ChatStatistics.date.desc()).limit(7).all()

    # 시간대별 통계
    hourly_stats = db.session.query(
        ChatStatistics.hour,
        db.func.sum(ChatStatistics.message_count).label('messages')
    ).group_by(ChatStatistics.hour).order_by(ChatStatistics.hour).all()

    # 사용자별 통계
    user_stats = db.session.query(
        User.username,
        db.func.sum(ChatStatistics.message_count).label('messages'),
        db.func.sum(ChatStatistics.character_count).label('characters')
    ).join(ChatStatistics).group_by(User.username).all()

    return jsonify({
        'daily_stats': [{
            'date': stats.date.strftime('%Y-%m-%d'),
            'messages': stats.messages,
            'active_users': stats.active_users
        } for stats in daily_stats],
        'hourly_stats': [{
            'hour': stats.hour,
            'messages': stats.messages
        } for stats in hourly_stats],
        'user_stats': [{
            'username': stats.username,
            'messages': stats.messages,
            'characters': stats.characters
        } for stats in user_stats]
    })

@app.route('/delete_message/<int:message_id>', methods=['POST'])
@login_required
def delete_message(message_id):
    message = Chat.query.get_or_404(message_id)
    if current_user.is_admin or message.sender_id == current_user.id:
        db.session.delete(message)
        db.session.commit()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return '', 204
    return redirect(url_for('chat'))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        flash('프로필이 변경되었습니다')
    return render_template('profile.html', user=current_user)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/users')
@login_required
def users():
    if not current_user.is_admin:
        flash('관리자 권한이 필요합니다')
        return redirect(url_for('dashboard'))
    users = User.query.all()
    return render_template('users.html', users=users)

@app.route('/admin/add_user', methods=['POST'])
@login_required
def admin_add_user():
    if not current_user.is_admin:
        flash('관리자 권한이 필요합니다')
        return redirect(url_for('dashboard'))

    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    is_admin = request.form.get('is_admin') == 'on'

    if not username or not password:
        flash('아이디와 비밀번호를 모두 입력해주세요')
        return redirect(url_for('users'))

    if User.query.filter_by(username=username).first():
        flash('이미 존재하는 아이디입니다')
        return redirect(url_for('users'))

    try:
        user = User(
            username=username,
            is_admin=is_admin,
            balance=100000 if is_admin else 0  # 수정된 부분
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash('회원이 추가되었습니다')
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"회원 추가 중 오류 발생: {str(e)}")
        flash('회원 추가 중 오류가 발생했습니다')

    return redirect(url_for('users'))

@app.route('/admin/remove_user', methods=['POST'])
@login_required
def admin_remove_user():
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))

    user = User.query.filter_by(username=request.form['username']).first()
    if user:
        if user.is_admin:
            flash('관리자는 삭제할 수 없습니다')
            return redirect(url_for('users'))
        db.session.delete(user)
        db.session.commit()
        flash('회원이 삭제되었습니다')
    return redirect(url_for('users'))

@app.route('/admin/modify_balance', methods=['POST'])
@login_required
def admin_modify_balance():
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))

    user = User.query.filter_by(username=request.form['username']).first()
    if user and not user.is_admin:
        user.balance = int(request.form['balance'])
        db.session.commit()
        flash('잔액이 수정되었습니다')
        return redirect(url_for('users'))
    flash('사용자를 찾을 수 없거나 관리자의 잔액은 수정할 수 없습니다')
    return redirect(url_for('users'))

@app.route('/admin/apply_fine', methods=['POST'])
@login_required
def admin_apply_fine():
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))

    user = User.query.filter_by(username=request.form['username']).first()
    if not user or user.is_admin:
        flash('사용자를 찾을 수 없거나 관리자에게는 벌금을 부과할 수 없습니다')
        return redirect(url_for('users'))

    amount = int(request.form['amount'])
    user.balance -= amount
    transaction = Transaction(
        sender_id=user.id,
        receiver_id=current_user.id,
        amount=amount,
        type='fine'
    )
    db.session.add(transaction)
    db.session.commit()
    flash('벌금이 부과되었습니다')
    return redirect(url_for('users'))

@app.route('/admin/monthly_pay', methods=['POST'])
@login_required
def admin_monthly_pay():
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))

    amount = int(request.form['amount'])
    regular_users = User.query.filter_by(is_admin=False).all()

    for user in regular_users:
        user.balance += amount
        transaction = Transaction(
            sender_id=current_user.id,
            receiver_id=user.id,
            amount=amount,
            type='monthly'
        )
        db.session.add(transaction)

    db.session.commit()
    flash(f'모든 일반 회원에게 {amount} 체스머니가 지급되었습니다')
    return redirect(url_for('users'))

@app.route('/admin/clear_messages', methods=['POST'])
@login_required
def admin_clear_messages():
    if not current_user.is_admin:
        return jsonify({'error': '권한이 없습니다'}), 403

    try:
        # 모든 메시지 삭제
        Chat.query.delete()
        db.session.commit()
        return '', 204
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"메시지 삭제 중 오류 발생: {str(e)}")
        return jsonify({'error': '메시지 삭제 중 오류가 발생했습니다'}), 500

@app.route('/admin/mute_user', methods=['POST'])
@login_required
def admin_mute_user():
    if not current_user.is_admin:
        return jsonify({'error': '권한이 없습니다'}), 403

    data = request.get_json()
    username = data.get('username')
    if not username:
        return jsonify({'error': '사용자명이 필요합니다'}), 400

    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({'error': '사용자를 찾을 수 없습니다'}), 404

    try:
        user.is_muted = True
        db.session.commit()
        return jsonify({'message': f'{username}님의 채팅이 금지되었습니다'})
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"사용자 채팅 금지 중 오류 발생: {str(e)}")
        return jsonify({'error': '사용자 채팅 금지 중 오류가 발생했습니다'}), 500

@app.route('/change_password', methods=['POST'])
@login_required
def change_password():
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')

    if not current_user.check_password(current_password):
        flash('현재 비밀번호가 일치하지 않습니다')
        return redirect(url_for('profile'))

    if new_password != confirm_password:
        flash('새 비밀번호가 일치하지 않습니다')
        return redirect(url_for('profile'))

    if len(new_password) < 8:
        flash('비밀번호는 8자 이상이어야 합니다')
        return redirect(url_for('profile'))

    try:
        current_user.set_password(new_password)
        db.session.commit()
        flash('비밀번호가 성공적으로 변경되었습니다')
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"비밀번호 변경 중 오류 발생: {str(e)}")
        flash('비밀번호 변경 중 오류가 발생했습니다')

    return redirect(url_for('profile'))

@app.route('/update_profile', methods=['POST'])
@login_required
def update_profile():
    profile_piece = request.form.get('profile_piece')
    if profile_piece:
        current_user.profile_piece = profile_piece
        current_user.profile_color = 'white' if profile_piece in ['♔', '♕', '♖', '♗', '♘', '♙'] else 'black'
        try:
            db.session.commit()
            flash('프로필이 성공적으로 업데이트되었습니다')
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"프로필 업데이트 중 오류 발생: {str(e)}")
            flash('프로필 업데이트 중 오류가 발생했습니다')

    return redirect(url_for('profile'))
