from ChessMoneyTransfer.app import app, socketio
import logging
from ChessMoneyTransfer.app import app  # app.py를 임포트

if __name__ == "__main__":
    app.run(debug=True)


logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logger.info("Starting server from main.py...")
    try:
        socketio.run(app, host='0.0.0.0', port=5000, debug=True, use_reloader=True, log_output=True)
    except Exception as e:
        logger.error(f"Error starting server: {e}", exc_info=True)
