import os
import time
from datetime import datetime, timedelta
import threading
import asyncio
import logging
import re
import random
from pymongo import MongoClient
from pyrogram import Client, filters, enums, errors
from pyrogram.errors import BadRequest, Forbidden, MessageNotModified, FloodWait, UserIsBlocked, ChatAdminRequired
from flask import Flask, request, jsonify
from dotenv import load_dotenv

# --- Custom module imports ---
from handlers import setup_all_handlers
from callbacks import setup_all_callbacks
from utils import is_admin, is_group_admin, log_to_channel, handle_incident, broadcast_to_all
from database import init_mongodb, get_group_settings, update_group_setting, get_warn_settings, update_warn_settings, get_notification_delete_time, update_notification_delete_time, is_whitelisted_sync, add_whitelist_sync, remove_whitelist_sync, get_whitelist_sync, get_warnings_sync, increment_warning_sync, reset_warnings_sync
from profanity_filter import ProfanityFilter
from reminder_scheduler import reminder_scheduler
from config import API_ID, API_HASH, TELEGRAM_BOT_TOKEN, LOG_CHANNEL_ID, ADMIN_USER_IDS, MONGO_DB_URI, DEFAULT_WARNING_LIMIT, DEFAULT_PUNISHMENT, URL_PATTERN

# Load environment variables from .env file
load_dotenv()

# --- Global Variables and Logging ---
bot_start_time = datetime.now()
BROADCAST_MESSAGE = {}
LOCKED_MESSAGES = {}
SECRET_CHATS = {}
TIC_TAC_TOE_GAMES = {}
TIC_TAC_TOE_TASK = {}

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- Pyrogram Client Initialization ---
client = Client(
    "my_bot_session",
    bot_token=TELEGRAM_BOT_TOKEN,
    api_id=API_ID,
    api_hash=API_HASH
)

# --- MongoDB and Profanity Filter Initialization ---
db, profanity_filter = init_mongodb(MONGO_DB_URI)

# --- Flask App for Health Check ---
@app.route('/')
def health_check():
    return jsonify({"status": "healthy", "bot_running": True, "mongodb_connected": db is not None}), 200

def run_flask_app():
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)

# --- Setup Handlers and Callbacks ---
setup_all_handlers(client, db, LOCKED_MESSAGES, SECRET_CHATS, TIC_TAC_TOE_GAMES, TIC_TAC_TOE_TASK, BROADCAST_MESSAGE, profanity_filter)
setup_all_callbacks(client, db, LOCKED_MESSAGES, SECRET_CHATS, TIC_TAC_TOE_GAMES, TIC_TAC_TOE_TASK, BROADCAST_MESSAGE, profanity_filter)

# --- Entry Point ---
if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask_app)
    flask_thread.daemon = True
    flask_thread.start()

    logger.info("Bot is starting...")
    
    if db is not None:
        client.loop.create_task(reminder_scheduler(client, db))

    client.run()
    logger.info("Bot stopped")
