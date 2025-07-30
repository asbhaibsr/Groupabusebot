# web.py
import os
import logging
from flask import Flask

# Logging configuration
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
PORT = int(os.getenv("PORT", 8000))

@app.route('/')
def health_check():
    """Koyeb health checks ke liye simple endpoint."""
    return "Bot is healthy!", 200

if __name__ == '__main__':
    logger.info(f"Flask application starting on port {PORT} for health checks only...")
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)

