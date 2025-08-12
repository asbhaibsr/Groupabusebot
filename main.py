import os
import time
from datetime import datetime, timedelta
import threading
import asyncio
import logging
import re
import random
from pymongo import MongoClient, ReturnDocument
from pyrogram import Client, filters, enums, errors
from pyrogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    ChatPermissions, BotCommand
)
from pyrogram.errors import BadRequest, Forbidden, MessageNotModified, FloodWait
from flask import Flask, request, jsonify
from dotenv import load_dotenv

# Load environment variables from .env file (for local development)
load_dotenv()

# --- Custom module import (ensure this file exists and is correctly configured)
from profanity_filter import ProfanityFilter

# --- Configuration ---
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Fix: Use a static ID here instead of fetching from .env
LOG_CHANNEL_ID = -1002352329534

MONGO_DB_URI = os.getenv("MONGO_DB_URI")
ADMIN_USER_IDS = [7315805581]

bot_start_time = datetime.now()
BROADCAST_MESSAGE = {}

URL_PATTERN = re.compile(r'\b(?:https?://|www\.|t\.me/|telegra\.ph/)[^\s]+\b|@\w+', re.IGNORECASE)

# --- Tagging variables
TAG_MESSAGES = {}
ONGOING_TAGGING_TASKS = {}
EMOJIS = ['😀', '😃', '😄', '😁', '😆', '😅', '🤣', '😂', '🙂', '🙃', '🫠', '😉', '😊', '😇', '🥰', '😍']

# --- New Constants ---
DEFAULT_WARNING_LIMIT = 3
DEFAULT_PUNISHMENT = "mute"
DEFAULT_CONFIG = ("warn", DEFAULT_WARNING_LIMIT, DEFAULT_PUNISHMENT)

# --- Logging Setup ---
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

mongo_client = None
db = None
profanity_filter = None

# --- MongoDB Initialization ---
def init_mongodb():
    global mongo_client, db, profanity_filter
    if MONGO_DB_URI is None:
        logger.error("MONGO_DB_URI environment variable is not set. Cannot connect to MongoDB.")
        profanity_filter = ProfanityFilter(mongo_uri=None)
        return

    try:
        mongo_client = MongoClient(MONGO_DB_URI)
        db = mongo_client.get_database("asfilter")
        
        db.groups.create_index("chat_id", unique=True)
        db.users.create_index("user_id", unique=True)
        db.warnings.create_index([("user_id", 1), ("chat_id", 1)], unique=True)
        db.config.create_index("chat_id", unique=True)
        db.whitelist.create_index([("chat_id", 1), ("user_id", 1)], unique=True)
        db.biolink_exceptions.create_index([("chat_id", 1), ("user_id", 1)], unique=True)
        db.settings.create_index("chat_id", unique=True)
        
        profanity_filter = ProfanityFilter(mongo_uri=MONGO_DB_URI)
        logger.info("MongoDB connection and collections initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        profanity_filter = ProfanityFilter(mongo_uri=None)

# --- Helper Functions ---
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_USER_IDS

async def is_group_admin(chat_id: int, user_id: int) -> bool:
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in [enums.ChatMemberStatus.OWNER, enums.ChatMemberStatus.ADMINISTRATOR]
    except (BadRequest, Forbidden):
        return False
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
        return False

# --- Settings Functions ---
def get_group_settings(chat_id):
    if db is None:
        return {
            "delete_biolink": True,
            "delete_abuse": True,
            "delete_edited": True,
            "delete_links_usernames": True,
            "biolink_warn_limit": 3,
            "abuse_warn_limit": 3,
            "biolink_penalty": "mute",
            "abuse_penalty": "mute"
        }
    
    settings = db.settings.find_one({"chat_id": chat_id})
    if not settings:
        default_settings = {
            "chat_id": chat_id,
            "delete_biolink": True,
            "delete_abuse": True,
            "delete_edited": True,
            "delete_links_usernames": True,
            "biolink_warn_limit": 3,
            "abuse_warn_limit": 3,
            "biolink_penalty": "mute",
            "abuse_penalty": "mute"
        }
        db.settings.insert_one(default_settings)
        return default_settings
    return settings

def update_group_setting(chat_id, setting_key, setting_value):
    if db is None:
        return
    db.settings.update_one(
        {"chat_id": chat_id},
        {"$set": {setting_key: setting_value}},
        upsert=True
    )

# --- Professional Settings Menu ---
async def show_settings_menu(client, message_or_query):
    if isinstance(message_or_query, CallbackQuery):
        chat_id = message_or_query.message.chat.id
        message = message_or_query.message
    else:
        chat_id = message_or_query.chat.id
        message = message_or_query

    settings = get_group_settings(chat_id)
    
    settings_text = (
        "⚙️ **Bot Settings Menu**\n\n"
        "Choose a category to configure:\n"
        "• **Bio-Link Protection** - Handle users with links in bio\n"
        "• **Abuse Detection** - Handle abusive language\n"
        "• **Message Controls** - Handle edited messages & links"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚨 Bio-Link Protection", callback_data="settings_biolink")],
        [InlineKeyboardButton("🚫 Abuse Detection", callback_data="settings_abuse")],
        [InlineKeyboardButton("📝 Message Controls", callback_data="settings_messages")],
        [InlineKeyboardButton("🔙 Back to Main", callback_data="back_main")]
    ])

    if isinstance(message_or_query, CallbackQuery):
        await message.edit_text(settings_text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)
    else:
        await message.reply_text(settings_text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)

# --- Bio-Link Settings ---
async def show_biolink_settings(client, callback_query):
    chat_id = callback_query.message.chat.id
    settings = get_group_settings(chat_id)
    
    status = "✅ **ENABLED**" if settings.get("delete_biolink", True) else "❌ **DISABLED**"
    limit = settings.get("biolink_warn_limit", 3)
    penalty = settings.get("biolink_penalty", "mute").upper()
    
    text = (
        f"🚨 **Bio-Link Protection Settings**\n\n"
        f"**Status:** {status}\n"
        f"**Warn Limit:** {limit}\n"
        f"**Penalty:** {penalty}\n\n"
        f"Configure options below:"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Toggle Status", callback_data="toggle_biolink_status")],
        [InlineKeyboardButton(f"Warn Limit: {limit}", callback_data="change_biolink_limit")],
        [InlineKeyboardButton(f"Penalty: {penalty}", callback_data="change_biolink_penalty")],
        [InlineKeyboardButton("🔙 Back to Settings", callback_data="back_settings")]
    ])
    
    await callback_query.message.edit_text(text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)

# --- Abuse Settings ---
async def show_abuse_settings(client, callback_query):
    chat_id = callback_query.message.chat.id
    settings = get_group_settings(chat_id)
    
    status = "✅ **ENABLED**" if settings.get("delete_abuse", True) else "❌ **DISABLED**"
    limit = settings.get("abuse_warn_limit", 3)
    penalty = settings.get("abuse_penalty", "mute").upper()
    
    text = (
        f"🚫 **Abuse Detection Settings**\n\n"
        f"**Status:** {status}\n"
        f"**Warn Limit:** {limit}\n"
        f"**Penalty:** {penalty}\n\n"
        f"Configure options below:"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Toggle Status", callback_data="toggle_abuse_status")],
        [InlineKeyboardButton(f"Warn Limit: {limit}", callback_data="change_abuse_limit")],
        [InlineKeyboardButton(f"Penalty: {penalty}", callback_data="change_abuse_penalty")],
        [InlineKeyboardButton("🔙 Back to Settings", callback_data="back_settings")]
    ])
    
    await callback_query.message.edit_text(text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)

# --- Message Controls Settings ---
async def show_message_settings(client, callback_query):
    chat_id = callback_query.message.chat.id
    settings = get_group_settings(chat_id)
    
    edited_status = "✅ **ENABLED**" if settings.get("delete_edited", True) else "❌ **DISABLED**"
    links_status = "✅ **ENABLED**" if settings.get("delete_links_usernames", True) else "❌ **DISABLED**"
    
    text = (
        f"📝 **Message Controls**\n\n"
        f"**Delete Edited Messages:** {edited_status}\n"
        f"**Delete Links/Usernames:** {links_status}\n\n"
        f"Toggle options below:"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"Edit Messages: {edited_status.split()[0]}", callback_data="toggle_edited")],
        [InlineKeyboardButton(f"Links/Usernames: {links_status.split()[0]}", callback_data="toggle_links")],
        [InlineKeyboardButton("🔙 Back to Settings", callback_data="back_settings")]
    ])
    
    await callback_query.message.edit_text(text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)

# --- Updated /config Command ---
@client.on_message(filters.group & filters.command("config"))
async def configure(client: Client, message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not await is_group_admin(chat_id, user_id):
        return await message.reply_text("**❌ You must be an admin to use this command.**")

    settings = get_group_settings(chat_id)
    
    text = (
        "**📋 Configuration Panel**\n\n"
        "Manage your bot settings below:"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚨 Bio-Link Settings", callback_data="settings_biolink")],
        [InlineKeyboardButton("🚫 Abuse Settings", callback_data="settings_abuse")],
        [InlineKeyboardButton("📝 Message Controls", callback_data="settings_messages")],
        [InlineKeyboardButton("❌ Close", callback_data="close")]
    ])
    
    await client.send_message(chat_id, text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)
    await message.delete()

# --- Callback Query Handler for Settings ---
@client.on_callback_query()
async def settings_callback_handler(client: Client, callback_query: CallbackQuery):
    data = callback_query.data
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id
    
    # Admin check for group callbacks
    if chat_id < 0:  # Group chat
        if not await is_group_admin(chat_id, user_id):
            await callback_query.answer("❌ Only admins can change settings!", show_alert=True)
            return
    
    await callback_query.answer()
    
    if data == "settings_biolink":
        await show_biolink_settings(client, callback_query)
    
    elif data == "settings_abuse":
        await show_abuse_settings(client, callback_query)
    
    elif data == "settings_messages":
        await show_message_settings(client, callback_query)
    
    elif data == "back_settings":
        await show_settings_menu(client, callback_query)
    
    elif data == "back_main":
        # Handle back to main menu
        try:
            await callback_query.message.delete()
        except:
            pass
    
    # Toggle handlers
    elif data == "toggle_biolink_status":
        settings = get_group_settings(chat_id)
        current = settings.get("delete_biolink", True)
        update_group_setting(chat_id, "delete_biolink", not current)
        await show_biolink_settings(client, callback_query)
    
    elif data == "toggle_abuse_status":
        settings = get_group_settings(chat_id)
        current = settings.get("delete_abuse", True)
        update_group_setting(chat_id, "delete_abuse", not current)
        await show_abuse_settings(client, callback_query)
    
    elif data == "toggle_edited":
        settings = get_group_settings(chat_id)
        current = settings.get("delete_edited", True)
        update_group_setting(chat_id, "delete_edited", not current)
        await show_message_settings(client, callback_query)
    
    elif data == "toggle_links":
        settings = get_group_settings(chat_id)
        current = settings.get("delete_links_usernames", True)
        update_group_setting(chat_id, "delete_links_usernames", not current)
        await show_message_settings(client, callback_query)
    
    # Limit change handlers
    elif data.startswith("change_") and data.endswith("_limit"):
        setting_type = data.split('_')[1]
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("3", callback_data=f"set_limit_{setting_type}_3")],
            [InlineKeyboardButton("4", callback_data=f"set_limit_{setting_type}_4")],
            [InlineKeyboardButton("5", callback_data=f"set_limit_{setting_type}_5")],
            [InlineKeyboardButton("🔙 Back", callback_data=f"settings_{setting_type}")]
        ])
        await callback_query.message.edit_text(
            f"**Select warn limit for {setting_type}:**",
            reply_markup=keyboard,
            parse_mode=enums.ParseMode.MARKDOWN
        )
    
    elif data.startswith("set_limit_"):
        parts = data.split('_')
        setting_type = parts[2]
        limit = int(parts[3])
        
        if setting_type == "biolink":
            update_group_setting(chat_id, "biolink_warn_limit", limit)
            await show_biolink_settings(client, callback_query)
        elif setting_type == "abuse":
            update_group_setting(chat_id, "abuse_warn_limit", limit)
            await show_abuse_settings(client, callback_query)
    
    # Penalty change handlers
    elif data.startswith("change_") and data.endswith("_penalty"):
        setting_type = data.split('_')[1]
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Mute", callback_data=f"set_penalty_{setting_type}_mute")],
            [InlineKeyboardButton("Ban", callback_data=f"set_penalty_{setting_type}_ban")],
            [InlineKeyboardButton("🔙 Back", callback_data=f"settings_{setting_type}")]
        ])
        await callback_query.message.edit_text(
            f"**Select penalty for {setting_type}:**",
            reply_markup=keyboard,
            parse_mode=enums.ParseMode.MARKDOWN
        )
    
    elif data.startswith("set_penalty_"):
        parts = data.split('_')
        setting_type = parts[2]
        penalty = parts[3]
        
        if setting_type == "biolink":
            update_group_setting(chat_id, "biolink_penalty", penalty)
            await show_biolink_settings(client, callback_query)
        elif setting_type == "abuse":
            update_group_setting(chat_id, "abuse_penalty", penalty)
            await show_abuse_settings(client, callback_query)

# --- Updated Settings Command ---
@client.on_message(filters.group & filters.command("settings"))
async def settings_command_handler(client: Client, message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if not await is_group_admin(chat_id, user_id):
        await message.reply_text("**❌ You must be an admin to use this command.**")
        return
    
    await show_settings_menu(client, message)

# --- Keep existing functions unchanged ---
# [Rest of your existing code remains the same - message handlers, logging, etc.]

# --- Flask App for Health Check ---
@app.route('/')
def health_check():
    return jsonify({"status": "healthy", "bot_running": True, "mongodb_connected": db is not None}), 200

def run_flask_app():
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)

# --- Entry Point ---
if __name__ == "__main__":
    init_mongodb()
    
    flask_thread = threading.Thread(target=run_flask_app)
    flask_thread.daemon = True
    flask_thread.start()
    
    logger.info("Professional Bot is starting...")
    client.run()
    logger.info("Bot stopped")
