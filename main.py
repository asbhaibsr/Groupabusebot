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
from pyrogram.errors import BadRequest, Forbidden, MessageNotModified, FloodWait, UserIsBlocked, ChatAdminRequired
from flask import Flask, request, jsonify
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Custom module import (ensure this file exists and is correctly configured)
# Assuming profanity_filter.py is available and correctly configured
from profanity_filter import ProfanityFilter

# --- Configuration ---
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Yahan par tumhara actual log channel ID daalo
LOG_CHANNEL_ID = -1002717243409

# Yahan par apne bot admin user IDs daalo
ADMIN_USER_IDS = [7315805581]

MONGO_DB_URI = os.getenv("MONGO_DB_URI")

bot_start_time = datetime.now()
BROADCAST_MESSAGE = {}

# Corrected regex pattern to catch all links and usernames
URL_PATTERN = re.compile(r'\b(?:https?://|www\.|t\.me/|telegra\.ph/)[^\s]+\b|@\w+', re.IGNORECASE)

# --- New Constants from your first snippet ---
DEFAULT_WARNING_LIMIT = 3
DEFAULT_PUNISHMENT = "mute"
DEFAULT_CONFIG = ("warn", DEFAULT_WARNING_LIMIT, DEFAULT_PUNISHMENT)
DEFAULT_DELETE_TIME = 0 # 0 means no auto-delete

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

# --- Lock Message & Tic Tac Toe Game State ---
LOCKED_MESSAGES = {}
SECRET_CHATS = {}
TIC_TAC_TOE_GAMES = {}
TIC_TAC_TOE_TASK = {}


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
        db.warn_settings.create_index("chat_id", unique=True)
        # New index for notification delete time
        db.notification_settings.create_index("chat_id", unique=True)

        profanity_filter = ProfanityFilter(mongo_uri=MONGO_DB_URI)
        logger.info("MongoDB connection and collections initialized successfully. Profanity filter is ready.")
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB or initialize collections: {e}.")
        profanity_filter = ProfanityFilter(mongo_uri=None)
        logger.warning("Falling back to default profanity list due to MongoDB connection error.")

# --- Helper Functions ---
def is_admin(user_id: int) -> bool:
    """Checks if the given user_id is a bot admin."""
    return user_id in ADMIN_USER_IDS

async def is_group_admin(chat_id: int, user_id: int) -> bool:
    """Checks if the given user_id is an admin in the specified chat."""
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in [enums.ChatMemberStatus.OWNER, enums.ChatMemberStatus.ADMINISTRATOR]
    except (BadRequest, Forbidden):
        return False
    except Exception as e:
        logger.error(f"Error checking admin status for user {user_id} in chat {chat_id}: {e}")
        return False

# FIX: Log function updated to handle cases where LOG_CHANNEL_ID is not set.
async def log_to_channel(text: str, parse_mode: enums.ParseMode = None) -> None:
    """Sends a log message to the predefined LOG_CHANNEL_ID with better error handling."""
    if not LOG_CHANNEL_ID or LOG_CHANNEL_ID == -1: # Added -1 check as a safety
        logger.warning("LOG_CHANNEL_ID is not set or invalid, cannot log to channel.")
        return

    try:
        await client.send_message(chat_id=LOG_CHANNEL_ID, text=text, parse_mode=parse_mode)
    except Forbidden:
        logger.error(f"Bot does not have permissions to send messages to log channel {LOG_CHANNEL_ID}.")
    except BadRequest as e:
        logger.error(f"Cannot send to log channel: {e}. Channel may not exist or bot lacks permissions.")
    except Exception as e:
        logger.error(f"Error logging to channel: {e}")

def get_warn_settings(chat_id, category):
    if db is None: return DEFAULT_WARNING_LIMIT, DEFAULT_PUNISHMENT
    settings = db.warn_settings.find_one({"chat_id": chat_id})
    if not settings or category not in settings:
        return DEFAULT_WARNING_LIMIT, DEFAULT_PUNISHMENT
    return settings[category].get("limit", DEFAULT_WARNING_LIMIT), settings[category].get("punishment", DEFAULT_PUNISHMENT)

def update_warn_settings(chat_id, category, limit=None, punishment=None):
    if db is None: return
    update_doc = {}
    if limit is not None: update_doc[f"{category}.limit"] = limit
    if punishment: update_doc[f"{category}.punishment"] = punishment
    db.warn_settings.update_one({"chat_id": chat_id}, {"$set": update_doc}, upsert=True)

def get_group_settings(chat_id):
    if db is None:
        return {
            "delete_biolink": True,
            "delete_abuse": True,
            "delete_edited": True,
            "delete_links_usernames": True
        }
    settings = db.settings.find_one({"chat_id": chat_id})
    if not settings:
        default_settings = {
            "chat_id": chat_id,
            "delete_biolink": True,
            "delete_abuse": True,
            "delete_edited": True,
            "delete_links_usernames": True
        }
        db.settings.insert_one(default_settings)
        return default_settings
    return settings

def update_group_setting(chat_id, setting_key, setting_value):
    if db is None: return
    db.settings.update_one(
        {"chat_id": chat_id},
        {"$set": {setting_key: setting_value}},
        upsert=True
    )

def get_notification_delete_time(chat_id):
    if db is None: return DEFAULT_DELETE_TIME
    settings = db.notification_settings.find_one({"chat_id": chat_id})
    return settings.get("delete_time", DEFAULT_DELETE_TIME) if settings else DEFAULT_DELETE_TIME

def update_notification_delete_time(chat_id, time_in_minutes):
    if db is None: return
    db.notification_settings.update_one({"chat_id": chat_id}, {"$set": {"delete_time": time_in_minutes}}, upsert=True)

def is_whitelisted_sync(chat_id, user_id):
    if db is None: return False
    return db.whitelist.find_one({"chat_id": chat_id, "user_id": user_id}) is not None

def add_whitelist_sync(chat_id, user_id):
    if db is None: return
    db.whitelist.update_one({"chat_id": chat_id, "user_id": user_id}, {"$set": {"timestamp": datetime.now()}}, upsert=True)

def remove_whitelist_sync(chat_id, user_id):
    if db is None: return
    db.whitelist.delete_one({"chat_id": chat_id, "user_id": user_id})

def get_whitelist_sync(chat_id):
    if db is None: return []
    return [doc["user_id"] for doc in db.whitelist.find({"chat_id": chat_id})]

def get_warnings_sync(user_id: int, chat_id: int, category: str):
    if db is None: return 0
    warnings_doc = db.warnings.find_one({"user_id": user_id, "chat_id": chat_id})
    if warnings_doc and "counts" in warnings_doc and category in warnings_doc["counts"]:
        return warnings_doc["counts"][category]
    return 0

def increment_warning_sync(chat_id, user_id, category):
    if db is None: return 1
    warnings_doc = db.warnings.find_one_and_update(
        {"chat_id": chat_id, "user_id": user_id},
        {"$inc": {f"counts.{category}": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER
    )
    return warnings_doc["counts"][category]

def reset_warnings_sync(chat_id, user_id, category):
    if db is None: return
    db.warnings.update_one(
        {"chat_id": chat_id, "user_id": user_id},
        {"$set": {f"counts.{category}": 0}}
    )

async def handle_incident(client: Client, chat_id, user, reason, original_message: Message, case_type, category=None):
    original_message_id = original_message.id
    full_name = f"{user.first_name}{(' ' + user.last_name) if user.last_name else ''}"
    user_mention_text = f"<a href='tg://user?id={user.id}'>{full_name}</a>"

    try:
        await client.delete_messages(chat_id=chat_id, message_ids=original_message_id)
        logger.info(f"Deleted {reason} message from {user.username or user.mention} ({user.id}) in {chat_id}.")
    except Exception as e:
        logger.error(f"Error deleting message in {chat_id}: {e}. Make sure the bot has 'Delete Messages' admin permission.")

    notification_text = ""
    keyboard = []
    
    warn_limit, punishment = get_warn_settings(chat_id, category) if category else (DEFAULT_WARNING_LIMIT, DEFAULT_PUNISHMENT)

    if case_type == "edited_message_deleted":
        notification_text = (
            f"<b>📝 Edited Message Deleted!</b>\n\n"
            f"Hey {user_mention_text}, your edited message was removed as editing messages to circumvent rules is not allowed.\n\n"
            f"<i>Please send a new message instead of editing old ones.</i>"
        )
        keyboard = [[InlineKeyboardButton("🗑️ Close", callback_data="close")]]

    elif case_type == "warn":
        count = increment_warning_sync(chat_id, user.id, category)
        notification_text = (
            f"<b>🚫 Hey {user_mention_text}, your message was removed!</b>\n\n"
            f"Reason: {reason}\n"
            f"<b>This is your warning number {count}/{warn_limit}.</b>"
        )
        keyboard = [[InlineKeyboardButton("🗑️ Close", callback_data="close")]]
        
    elif case_type == "punished":
        if punishment == "mute":
             await client.restrict_chat_member(chat_id, user.id, ChatPermissions())
             notification_text = (
                f"<b>🚫 Hey {user_mention_text}, you have been muted!</b>\n\n"
                f"You reached the maximum warning limit ({warn_limit}) for violating rules.\n"
                f"This is an automated action based on group settings."
            )
             keyboard = [[InlineKeyboardButton("Unmute ✅", callback_data=f"unmute_{user.id}_{chat_id}"), InlineKeyboardButton("🗑️ Close", callback_data="close")]]
        else: # punishment == "ban"
            await client.ban_chat_member(chat_id, user.id)
            notification_text = (
                f"<b>🚫 Hey {user_mention_text}, you have been banned!</b>\n\n"
                f"You reached the maximum warning limit ({warn_limit}) for violating rules.\n"
                f"This is an automated action based on group settings."
            )
            keyboard = [[InlineKeyboardButton("🗑️ Close", callback_data="close")]]

    if notification_text:
        try:
            sent_notification = await client.send_message(
                chat_id=chat_id,
                text=notification_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=enums.ParseMode.HTML
            )
            logger.info(f"Incident notification sent for user {user.id} in chat {chat_id}.")

            delete_time_minutes = get_notification_delete_time(chat_id)
            if delete_time_minutes > 0:
                await asyncio.sleep(delete_time_minutes * 60)
                try:
                    await client.delete_messages(chat_id=chat_id, message_ids=sent_notification.id)
                except Exception as e:
                    logger.error(f"Error deleting timed notification: {e}")

        except Exception as e:
            logger.error(f"Error sending notification in chat {chat_id}: {e}. Make sure bot has 'Post Messages' permission.")

# --- Bot Commands Handlers ---
@client.on_message(filters.command("start"))
async def start(client: Client, message: Message) -> None:
    user = message.from_user
    chat = message.chat
    bot_info = await client.get_me()
    bot_name = bot_info.first_name
    bot_username = bot_info.username
    add_to_group_url = f"https://t.me/{bot_username}?startgroup=true"

    if chat.type == enums.ChatType.PRIVATE:
        welcome_message = (
            f"👋 <b>Namaste {user.first_name}!</b>\n\n"
            f"Mai <b>{bot_name}</b> hun, aapka group moderator bot. "
            f"Mai aapke groups ko saaf suthra rakhne mein madad karta hun."
        )

        keyboard = [
            [InlineKeyboardButton("➕ Add Me To Your Group", url=add_to_group_url)],
            [InlineKeyboardButton("❓ Help", callback_data="help_menu"), InlineKeyboardButton("🤖 Other Bots", callback_data="other_bots")],
            [InlineKeyboardButton("📢 Update Channel", url="https://t.me/asbhai_bsr"), InlineKeyboardButton("💖 Donate", callback_data="donate_info")],
            [InlineKeyboardButton("📈 Promotion", url="https://t.me/asprmotion")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await message.reply_text(
            text=welcome_message,
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML,
            disable_web_page_preview=True
        )
        logger.info(f"User {user.first_name} ({user.id}) started the bot in private chat.")

        if db is not None and db.users is not None:
            try:
                db.users.update_one(
                    {"user_id": user.id},
                    {"$set": {"first_name": user.first_name, "username": user.username, "last_interaction": datetime.now()}},
                    upsert=True
                )
            except Exception as e:
                logger.error(f"Error saving user {user.id} to DB (from start command): {e}")

        log_message = (
            f"<b>✨ New User Started Bot:</b>\n"
            f"User: {user.first_name} (`{user.id}`)\n"
            f"Username: @{user.username if user.username else 'N/A'}\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}"
        )
        await log_to_channel(log_message, parse_mode=enums.ParseMode.HTML)

    elif chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        try:
            bot_info = await client.get_me()
            bot_username = bot_info.username
            add_to_group_url = f"https://t.me/{bot_username}?startgroup=true"

            if await is_group_admin(chat.id, bot_info.id):
                group_start_message = f"Hello! Main <b>{bot_info.first_name}</b> hun, aapka group moderation bot. Main aapke group ko saaf suthra rakhne mein madad karunga."
                group_keyboard = [
                    [InlineKeyboardButton("➕ Add Me To Your Group", url=add_to_group_url)],
                    [InlineKeyboardButton("🔧 Bot Settings", callback_data="show_settings_main_menu")],
                    [InlineKeyboardButton("📢 Update Channel", url="https://t.me/asbhai_bsr")]
                ]
            else:
                group_start_message = f"Hello! Main <b>{bot_info.first_name}</b> hun. Is group mein moderation ke liye, kripya mujhe <b>admin</b> banayein aur <b>'Delete Messages'</b>, <b>'Restrict Users'</b>, <b>'Post Messages'</b> ki permissions dein."
                group_keyboard = [
                    [InlineKeyboardButton("➕ Add Me To Your Group", url=add_to_group_url)],
                    [InlineKeyboardButton("📢 Update Channel", url="https://t.me/asbhai_bsr")]
                ]

            reply_markup = InlineKeyboardMarkup(group_keyboard)

            await message.reply_text(
                text=group_start_message,
                reply_markup=reply_markup,
                parse_mode=enums.ParseMode.HTML
            )
            logger.info(f"Bot received /start in group: {chat.title} ({chat.id}).")
            if db is not None and db.groups is not None:
                try:
                    db.groups.update_one(
                        {"chat_id": chat.id},
                        {"$set": {"title": chat.title, "type": chat.type.value, "last_active": datetime.now()}},
                        upsert=True
                    )
                except Exception as e:
                    logger.error(f"Error saving group {chat.id} to DB: {e}")
        except Exception as e:
            logger.error(f"Error handling start in group: {e}")


@client.on_message(filters.command("help"))
async def help_handler(client: Client, message: Message):
    chat_id = message.chat.id
    help_text = (
        "<b>🛠️ Bot Commands & Usage</b>\n\n"
        "<b>Private Message Commands:</b>\n"
        "`/lock <@username> <message>` - Message ko lock karein taaki sirf mention kiya gaya user hi dekh sake. (Group mein hi kaam karega)\n"
        "`/secretchat <@username> <message>` - Ek secret message bhejein, jo group mein sirf ek pop-up mein dikhega. (Group mein hi kaam karega)\n\n"
        "<b>Tic Tac Toe Game:</b>\n"
        "`/tictac @user1 @user2` - Do users ke saath Tic Tac Toe game shuru karein. Ek baar mein ek hi game chalega.\n\n"
        "<b>BioLink Protector Commands:</b>\n"
        "`/free` – whitelist a user (reply or user/id)\n"
        "`/unfree` – remove from whitelist\n"
        "`/freelist` – list all whitelisted users\n\n"
        "<b>General Moderation Commands:</b>\n"
        f"• <code>/settings</code>: Bot ki settings kholen (Group Admins only).\n"
        f"• <code>/stats</code>: Bot usage stats dekhein (sirf bot admins ke liye).\n"
        f"• <code>/broadcast</code>: Sabhi groups mein message bhejein (sirf bot admins ke liye).\n"
        f"• <code>/addabuse &lt;shabd&gt;</code>: Custom gaali wala shabd filter mein add karein (sirf bot admins ke liye).\n"
        f"• <code>/checkperms</code>: Group mein bot ki permissions jaanchein (sirf group admins ke liye).\n"
        "• <code>/cleartempdata</code>: Bot ka temporary aur bekar data saaf karein (sirf bot admins ke liye).\n\n"
        "<b>When someone with a URL in their bio or a link in their message posts, I’ll:</b>\n"
        " 1. ⚠️ Warn them\n"
        " 2. 🔇 Mute if they exceed limit\n"
        " 3. 🔨 Ban if set to ban\n\n"
        "<b>Use the inline buttons on warnings to cancel or whitelist</b>"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🗑️ Close", callback_data="close")]])
    await client.send_message(chat_id, help_text, reply_markup=kb, parse_mode=enums.ParseMode.HTML)

@client.on_message(filters.group & filters.command("lock"))
async def lock_message_handler(client: Client, message: Message):
    # Check if sender is an admin
    if not await is_group_admin(message.chat.id, message.from_user.id):
        await message.reply_text("Aapke paas is command ko use karne ki permission nahi hai.")
        return

    # Check for arguments
    if len(message.command) < 3:
        await message.reply_text("Kripya user ko mention karein aur message likhein. Upyog: `/lock <@username> <message>`")
        return
        
    target_mention = message.command[1]
    message_content = " ".join(message.command[2:])

    if not target_mention.startswith('@'):
        await message.reply_text("Kripya us user ko mention karein jise aap message dikhana chahte hain.")
        return

    if not message_content:
        await message.reply_text("Kripya lock karne ke liye message bhi likhein.")
        return

    sender_user = message.from_user
    target_user = None

    try:
        target_user = await client.get_users(target_mention)
    except Exception:
        await message.reply_text("Invalid username. Please mention a valid user.")
        return

    # Store the locked message
    lock_id = f"{message.chat.id}_{sender_user.id}_{target_user.id}_{int(time.time())}"
    LOCKED_MESSAGES[lock_id] = {
        'text': message_content,
        'sender_id': sender_user.id,
        'target_id': target_user.id,
        'chat_id': message.chat.id
    }
    
    # Delete the original command message
    try:
        await message.delete()
    except Exception as e:
        logger.error(f"Error deleting lock command message: {e}")

    # Get the sender and target names
    sender_name = f"{sender_user.first_name}{(' ' + sender_user.last_name) if sender_user.last_name else ''}"
    target_name = f"{target_user.first_name}{(' ' + target_user.last_name) if target_user.last_name else ''}"
    
    # Send the lock message as per your request
    unlock_button = InlineKeyboardMarkup([[InlineKeyboardButton("Show Message", callback_data=f"show_lock_{lock_id}")]])
    
    await client.send_message(
        chat_id=message.chat.id,
        text=f"Hey <a href='tg://user?id={target_user.id}'>{target_name}</a>, aapko is <a href='tg://user?id={sender_user.id}'>{sender_name}</a> ne ek lock message bheja hai. Message dekhne ke liye niche button par click kare.",
        reply_markup=unlock_button,
        parse_mode=enums.ParseMode.HTML
    )

@client.on_callback_query(filters.regex("^show_lock_"))
async def show_lock_callback_handler(client: Client, query: CallbackQuery):
    lock_id = query.data.split('_', 2)[2]
    locked_message_data = LOCKED_MESSAGES.get(lock_id)

    if not locked_message_data:
        await query.answer("This message has been unlocked or is no longer available.", show_alert=True)
        return

    user_id = query.from_user.id
    if user_id != locked_message_data['target_id']:
        await query.answer("This message is not for you.", show_alert=True)
        return

    # Get the sender and target names
    try:
        sender_user = await client.get_users(locked_message_data['sender_id'])
        sender_name = f"{sender_user.first_name}{(' ' + sender_user.last_name) if sender_user.last_name else ''}"
    except Exception:
        sender_name = "Unknown User"

    target_user = query.from_user
    target_name = f"{target_user.first_name}{(' ' + target_user.last_name) if target_user.last_name else ''}"

    # Edit the message to show the content
    await query.message.edit_text(
        f"**🔓 Unlocked Message:**\n\n"
        f"**From:** <a href='tg://user?id={locked_message_data['sender_id']}'>{sender_name}</a>\n"
        f"**To:** <a href='tg://user?id={target_user.id}'>{target_name}</a>\n\n"
        f"**Message:**\n"
        f"{locked_message_data['text']}\n\n"
        f"This message will self-destruct in 1 minute."
    )

    # Remove the message from memory and delete it after a timeout
    LOCKED_MESSAGES.pop(lock_id)
    await asyncio.sleep(60)
    try:
        await query.message.delete()
    except Exception:
        pass

@client.on_message(filters.group & filters.command("secretchat"))
async def secret_chat_command(client: Client, message: Message):
    if not await is_group_admin(message.chat.id, message.from_user.id):
        await message.reply_text("Aapke paas is command ko use karne ki permission nahi hai.")
        return

    if len(message.command) < 3:
        await message.reply_text("Kripya user ko mention karein aur message likhein. Upyog: `/secretchat <@username> <message>`")
        return

    target_mention = message.command[1]
    secret_message = " ".join(message.command[2:])

    if not target_mention.startswith('@'):
        await message.reply_text("Kripya us user ko mention karein jise aap secret message bhejna chahte hain.")
        return
        
    try:
        target_user = await client.get_users(target_mention)
    except Exception:
        await message.reply_text("Invalid username. Please mention a valid user.")
        return

    sender_user = message.from_user
    
    secret_chat_id = f"{message.chat.id}_{sender_user.id}_{target_user.id}_{int(time.time())}"
    SECRET_CHATS[secret_chat_id] = {
        'message': secret_message,
        'sender_id': sender_user.id,
        'target_id': target_user.id,
        'chat_id': message.chat.id
    }
    
    try:
        await message.delete()
    except Exception as e:
        logger.error(f"Error deleting secretchat command message: {e}")
        
    sender_name = f"{sender_user.first_name}{(' ' + sender_user.last_name) if sender_user.last_name else ''}"
    target_name = f"{target_user.first_name}{(' ' + target_user.last_name) if target_user.last_name else ''}"

    notification_text = (
        f"Hey <a href='tg://user?id={target_user.id}'>{target_name}</a>, aapko ek secret message bheja gaya hai.\n"
        f"Ise dekhne ke liye niche button par click karein."
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Show Message", callback_data=f"show_secret_{secret_chat_id}")]
    ])
    
    await client.send_message(
        chat_id=message.chat.id,
        text=notification_text,
        reply_markup=keyboard,
        parse_mode=enums.ParseMode.HTML
    )

@client.on_callback_query(filters.regex("^show_secret_"))
async def show_secret_callback(client: Client, query: CallbackQuery):
    secret_chat_id = query.data.split('_', 2)[2]
    secret_chat_data = SECRET_CHATS.get(secret_chat_id)
    
    if not secret_chat_data:
        await query.answer("This secret message is no longer available.", show_alert=True)
        return

    if query.from_user.id != secret_chat_data['target_id']:
        await query.answer("This secret message is not for you.", show_alert=True)
        return
    
    try:
        sender_user = await client.get_users(secret_chat_data['sender_id'])
        sender_name = f"{sender_user.first_name}{(' ' + sender_user.last_name) if sender_user.last_name else ''}"
    except Exception:
        sender_name = "Unknown User"
        
    secret_message_text = f"From: {sender_name}\n\nMessage: {secret_chat_data['message']}"
    
    await query.answer(secret_message_text, show_alert=True)
    
    SECRET_CHATS.pop(secret_chat_id)
    
# --- Tic Tac Toe Game Logic (CORRECTED) ---
TIC_TAC_TOE_BUTTONS = [
    [InlineKeyboardButton("➖", callback_data="tictac_0"), InlineKeyboardButton("➖", callback_data="tictac_1"), InlineKeyboardButton("➖", callback_data="tictac_2")],
    [InlineKeyboardButton("➖", callback_data="tictac_3"), InlineKeyboardButton("➖", callback_data="tictac_4"), InlineKeyboardButton("➖", callback_data="tictac_5")],
    [InlineKeyboardButton("➖", callback_data="tictac_6"), InlineKeyboardButton("➖", callback_data="tictac_7"), InlineKeyboardButton("➖", callback_data="tictac_8")]
]
WINNING_COMBINATIONS = [
    [0, 1, 2], [3, 4, 5], [6, 7, 8],  # Rows
    [0, 3, 6], [1, 4, 7], [2, 5, 8],  # Columns
    [0, 4, 8], [2, 4, 6]            # Diagonals
]

async def end_tictactoe_game(client: Client, chat_id: int):
    """Ends an ongoing game gracefully and cleans up state."""
    if chat_id in TIC_TAC_TOE_GAMES:
        game = TIC_TAC_TOE_GAMES.pop(chat_id)
        if game.get("message_id"):
            try:
                await client.edit_message_text(
                    chat_id=chat_id,
                    message_id=game['message_id'],
                    text="😔 <b>Game has been cancelled due to inactivity.</b>",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🗑️ Close", callback_data="close")]])
                )
            except Exception as e:
                logger.error(f"Failed to edit game message on timeout: {e}")
    if chat_id in TIC_TAC_TOE_TASK:
        task = TIC_TAC_TOE_TASK.pop(chat_id)
        task.cancel()

def check_win(board):
    for combo in WINNING_COMBINATIONS:
        if board[combo[0]] == board[combo[1]] == board[combo[2]] and board[combo[0]] != "➖":
            return board[combo[0]]
    return None

def check_draw(board):
    return all(cell != "➖" for cell in board)

def get_tictac_keyboard(board, end_game=False):
    keyboard = []
    for i in range(3):
        row = []
        for j in range(3):
            index = i * 3 + j
            row.append(InlineKeyboardButton(board[index], callback_data=f"tictac_{index}" if not end_game else "tictac_noop"))
        keyboard.append(row)
    return InlineKeyboardMarkup(keyboard)

@client.on_message(filters.group & filters.command("tictac"))
async def tictac_game_start_command(client: Client, message: Message):
    chat_id = message.chat.id
    if chat_id in TIC_TAC_TOE_GAMES:
        await message.reply_text("Ek Tic Tac Toe game pehle se hi chal raha hai. Kripya uske khatam hone ka intezaar karein.")
        return
    
    sender = message.from_user
    
    if len(message.command) > 1 and message.command[1].startswith('@'):
        mentions = [mention for mention in message.command[1:] if mention.startswith('@')]
        if len(mentions) != 2:
            await message.reply_text("Game shuru karne ke liye do users ko mention karein.\nUpyog: `/tictac @user1 @user2`")
            return
        
        try:
            user1 = await client.get_users(mentions[0])
            user2 = await client.get_users(mentions[1])
        except Exception:
            await message.reply_text("Invalid users. Please mention valid users.")
            return

        players = [user1, user2]
        random.shuffle(players)
        
        board = ["➖"] * 9
        
        TIC_TAC_TOE_GAMES[chat_id] = {
            'players': {players[0].id: '❌', players[1].id: '⭕'},
            'player_names': {players[0].id: players[0].first_name, players[1].id: players[1].first_name},
            'board': board,
            'current_turn_id': players[0].id,
            'message_id': None,
            'last_active': datetime.now()
        }

        async def inactivity_check():
            await asyncio.sleep(300) # 5 minutes
            if chat_id in TIC_TAC_TOE_GAMES and (datetime.now() - TIC_TAC_TOE_GAMES[chat_id]['last_active']).total_seconds() >= 300:
                await end_tictactoe_game(client, chat_id)
                
        TIC_TAC_TOE_TASK[chat_id] = asyncio.create_task(inactivity_check())

        initial_text = f"**Tic Tac Toe (Zero Katte) Game!**\n\n" \
                       f"**Player 1:** {TIC_TAC_TOE_GAMES[chat_id]['player_names'][players[0].id]} (❌)\n" \
                       f"**Player 2:** {TIC_TAC_TOE_GAMES[chat_id]['player_names'][players[1].id]} (⭕)\n\n" \
                       f"**Current Turn:** {TIC_TAC_TOE_GAMES[chat_id]['player_names'][players[0].id]}"
        
        sent_message = await message.reply_text(
            initial_text,
            reply_markup=get_tictac_keyboard(board),
            parse_mode=enums.ParseMode.MARKDOWN
        )
        
        TIC_TAC_TOE_GAMES[chat_id]['message_id'] = sent_message.id
    else:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"Join Game", callback_data=f"tictac_join_game_{sender.id}")]
        ])
        
        await message.reply_text(
            f"<b>Tic Tac Toe Game Start</b>\n\n"
            f"<a href='tg://user?id={sender.id}'>{sender.first_name}</a> ne ek Tic Tac Toe game shuru kiya hai!\n"
            f"Ek aur player ke join karne ka intezaar hai.",
            reply_markup=keyboard,
            parse_mode=enums.ParseMode.HTML
        )

@client.on_callback_query(filters.regex("^tictac_join_game_"))
async def tictac_join_game(client: Client, query: CallbackQuery):
    chat_id = query.message.chat.id
    joiner_id = query.from_user.id
    starter_id = int(query.data.split("_")[-1])

    if chat_id in TIC_TAC_TOE_GAMES:
        await query.answer("Ek game pehle hi chal raha hai.", show_alert=True)
        return

    if joiner_id == starter_id:
        await query.answer("Aap pehle se hi player 1 hain. Kripya kisi aur ko join karne dein.", show_alert=True)
        return
    
    try:
        starter_user = await client.get_users(starter_id)
        joiner_user = query.from_user
    except Exception:
        await query.answer("Starting user not found.", show_alert=True)
        return

    players = [starter_user, joiner_user]
    random.shuffle(players)
    
    board = ["➖"] * 9

    TIC_TAC_TOE_GAMES[chat_id] = {
        'players': {players[0].id: '❌', players[1].id: '⭕'},
        'player_names': {players[0].id: players[0].first_name, players[1].id: players[1].first_name},
        'board': board,
        'current_turn_id': players[0].id,
        'message_id': query.message.id,
        'last_active': datetime.now()
    }
    
    async def inactivity_check():
        await asyncio.sleep(300)
        if chat_id in TIC_TAC_TOE_GAMES and (datetime.now() - TIC_TAC_TOE_GAMES[chat_id]['last_active']).total_seconds() >= 300:
            await end_tictactoe_game(client, chat_id)
    
    TIC_TAC_TOE_TASK[chat_id] = asyncio.create_task(inactivity_check())
    
    initial_text = f"**Tic Tac Toe (Zero Katte) Game!**\n\n" \
                   f"**Player 1:** {TIC_TAC_TOE_GAMES[chat_id]['player_names'][players[0].id]} (❌)\n" \
                   f"**Player 2:** {TIC_TAC_TOE_GAMES[chat_id]['player_names'][players[1].id]} (⭕)\n\n" \
                   f"**Current Turn:** {TIC_TAC_TOE_GAMES[chat_id]['player_names'][players[0].id]}"

    try:
        await query.message.edit_text(
            initial_text,
            reply_markup=get_tictac_keyboard(board),
            parse_mode=enums.ParseMode.MARKDOWN
        )
    except MessageNotModified:
        pass


@client.on_callback_query(filters.regex("^tictac_"))
async def tictac_game_play(client: Client, query: CallbackQuery):
    chat_id = query.message.chat.id
    game_state = TIC_TAC_TOE_GAMES.get(chat_id)
    
    if not game_state:
        user = query.from_user
        await client.send_message(
            chat_id,
            f"**Yeh game abhi active nahi hai.**\n\n"
            f"<a href='tg://user?id={user.id}'>{user.first_name}</a> ne ek naya game shuru kiya hai!\n"
            f"Ek aur player ke join karne ka intezaar hai.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Join Game", callback_data=f"tictac_join_game_{user.id}")]
            ]),
            parse_mode=enums.ParseMode.HTML
        )
        await query.answer("Yeh game abhi active nahi hai, naya game shuru kiya ja raha hai.", show_alert=True)
        return
    
    user_id = query.from_user.id
    if user_id not in game_state['players']:
        await query.answer("Aap is game ke player nahi hain.", show_alert=True)
        return

    if user_id != game_state['current_turn_id']:
        player_name = query.from_user.first_name
        await query.answer(f"It's not your turn, {player_name}!", show_alert=True)
        return

    button_index_str = query.data.split('_')[1]
    if button_index_str == 'noop':
        await query.answer("Game khatam ho chuka hai, kripya naya game shuru karein.", show_alert=True)
        return

    button_index = int(button_index_str)
    board = game_state['board']
    
    if board[button_index] != "➖":
        await query.answer("Yeh jagah pehle se hi bhari hui hai.", show_alert=True)
        return

    player_mark = game_state['players'][user_id]
    board[button_index] = player_mark

    game_state['last_active'] = datetime.now()
    if chat_id in TIC_TAC_TOE_TASK:
        TIC_TAC_TOE_TASK[chat_id].cancel()

    async def inactivity_check():
        await asyncio.sleep(300)
        if chat_id in TIC_TAC_TOE_GAMES and (datetime.now() - TIC_TAC_TOE_GAMES[chat_id]['last_active']).total_seconds() >= 300:
            await end_tictactoe_game(client, chat_id)
    
    TIC_TAC_TOE_TASK[chat_id] = asyncio.create_task(inactivity_check())
    
    winner = check_win(board)
    if winner:
        winner_name = game_state['player_names'][user_id]
        final_text = f"🎉 **{winner_name} wins the game!** 🎉\n\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Join New Game", callback_data=f"tictac_new_game_starter_{user_id}")],
            [InlineKeyboardButton("🗑️ Close", callback_data="close")]
        ])
        
        await query.message.edit_text(
            final_text,
            reply_markup=keyboard,
            parse_mode=enums.ParseMode.MARKDOWN
        )
        del TIC_TAC_TOE_GAMES[chat_id]
        return
    
    if check_draw(board):
        final_text = "🤝 **Game is a draw!** 🤝\n\n"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Join New Game", callback_data=f"tictac_new_game_starter_{user_id}")],
            [InlineKeyboardButton("🗑️ Close", callback_data="close")]
        ])
        
        await query.message.edit_text(
            final_text,
            reply_markup=keyboard,
            parse_mode=enums.ParseMode.MARKDOWN
        )
        del TIC_TAC_TOE_GAMES[chat_id]
        return

    other_player_id = [p for p in game_state['players'] if p != user_id][0]
    game_state['current_turn_id'] = other_player_id
    
    current_player_name = game_state['player_names'][other_player_id]

    updated_text = f"**Tic Tac Toe (Zero Katte) Game!**\n\n" \
                   f"**Player 1:** {game_state['player_names'][list(game_state['players'].keys())[0]]} (❌)\n" \
                   f"**Player 2:** {game_state['player_names'][list(game_state['players'].keys())[1]]} (⭕)\n\n" \
                   f"**Current Turn:** {current_player_name}"

    try:
        await query.message.edit_text(
            updated_text,
            reply_markup=get_tictac_keyboard(board),
            parse_mode=enums.ParseMode.MARKDOWN
        )
    except MessageNotModified:
        pass
    
@client.on_callback_query(filters.regex("^tictac_new_game_starter_"))
async def tictac_new_game_starter(client: Client, query: CallbackQuery):
    chat_id = query.message.chat.id
    starter_id = int(query.data.split('_')[-1])
    
    if chat_id in TIC_TAC_TOE_GAMES:
        await query.answer("Ek game pehle hi chal raha hai.", show_alert=True)
        return

    try:
        starter_user = await client.get_users(starter_id)
    except Exception:
        starter_user = query.from_user

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Join Game", callback_data=f"tictac_join_game_{starter_id}")]
    ])
    
    await client.send_message(
        chat_id,
        f"<b>Tic Tac Toe Game Start</b>\n\n"
        f"<a href='tg://user?id={starter_user.id}'>{starter_user.first_name}</a> ne ek Tic Tac Toe game shuru kiya hai!\n"
        f"Ek aur player ke join karne ka intezaar hai.",
        reply_markup=keyboard,
        parse_mode=enums.ParseMode.HTML
    )
    await query.message.delete()


@client.on_message(filters.group & filters.command("settings"))
async def settings_command_handler(client: Client, message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    if not await is_group_admin(chat_id, user_id):
        await message.reply_text("Aap group admin nahi hain, is command ka upyog nahi kar sakte.")
        return

    await show_settings_main_menu(client, message)

async def show_settings_main_menu(client, message):
    if isinstance(message, CallbackQuery):
        chat_id = message.message.chat.id
        user_id = message.from_user.id
    else:
        chat_id = message.chat.id
        user_id = message.from_user.id
    
    settings_text = "⚙️ <b>Bot Settings Menu:</b>\n\n" \
                    "Yahan aap group moderation features ko configure kar sakte hain."
                    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ On/Off Settings", callback_data="show_onoff_settings")],
        [InlineKeyboardButton("📋 Warn & Punishment Settings", callback_data="show_warn_punishment_settings")],
        [InlineKeyboardButton("📝 Whitelist List", callback_data="freelist_settings")],
        [InlineKeyboardButton("⏱️ Notification Delete Time", callback_data="show_notification_delete_time_menu")],
        [InlineKeyboardButton("🕹️ Game Settings", callback_data="show_game_settings")],
        [InlineKeyboardButton("🗑️ Close", callback_data="close")]
    ])

    if isinstance(message, CallbackQuery):
        await message.message.edit_text(settings_text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)
    else:
        await message.reply_text(settings_text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)


async def show_on_off_settings(client, message):
    if isinstance(message, CallbackQuery):
        chat_id = message.message.chat.id
    else:
        chat_id = message.chat.id

    settings = get_group_settings(chat_id)
    
    biolink_status = "✅ On" if settings.get("delete_biolink", True) else "❌ Off"
    abuse_status = "✅ On" if settings.get("delete_abuse", True) else "❌ Off"
    edited_status = "✅ On" if settings.get("delete_edited", True) else "❌ Off"
    links_usernames_status = "✅ On" if settings.get("delete_links_usernames", True) else "❌ Off" 

    settings_text = (
        "⚙️ <b>On/Off Settings:</b>\n\n"
        "Yahan aap group moderation features ko chalu/band kar sakte hain."
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🚨 Bio-Link Detected - {biolink_status}", callback_data="toggle_delete_biolink")],
        [InlineKeyboardButton(f"🚨 Abuse Detected - {abuse_status}", callback_data="toggle_delete_abuse")],
        [InlineKeyboardButton(f"📝 Edited Message Deleted - {edited_status}", callback_data="toggle_delete_edited")],
        [InlineKeyboardButton(f"🔗 Link/Username Removed - {links_usernames_status}", callback_data="toggle_delete_links_usernames")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_settings_main_menu")]
    ])

    if isinstance(message, CallbackQuery):
        await message.message.edit_text(settings_text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)
    else:
        await message.reply_text(settings_text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)


async def show_warn_punishment_settings(client, message):
    if isinstance(message, CallbackQuery):
        chat_id = message.message.chat.id
    else:
        chat_id = message.chat.id
    
    biolink_limit, biolink_punishment = get_warn_settings(chat_id, "biolink")
    abuse_limit, abuse_punishment = get_warn_settings(chat_id, "abuse")
    
    settings_text = (
        "<b>📋 Warn & Punishment Settings:</b>\n\n"
        "Yahan aap warning limit aur punishment set kar sakte hain."
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🚨 Bio-Link ({biolink_limit} warns)", callback_data="config_biolink")],
        [InlineKeyboardButton(f"Punish: {biolink_punishment.capitalize()}", callback_data="toggle_punishment_biolink")],
        [InlineKeyboardButton(f"🚨 Abuse ({abuse_limit} warns)", callback_data="config_abuse")],
        [InlineKeyboardButton(f"Punish: {abuse_punishment.capitalize()}", callback_data="toggle_punishment_abuse")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_settings_main_menu")]
    ])
    
    if isinstance(message, CallbackQuery):
        await message.message.edit_text(settings_text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)
    else:
        await message.reply_text(settings_text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)

async def show_notification_delete_time_menu(client, message):
    if isinstance(message, CallbackQuery):
        chat_id = message.message.chat.id
    else:
        chat_id = message.chat.id
        
    delete_time = get_notification_delete_time(chat_id)
    
    status_text = (
        f"<b>⏱️ Notification Delete Time:</b>\n\n"
        f"Choose how long warning/punishment notifications will stay before being automatically deleted.\n\n"
        f"<b>Current setting:</b> {'Off' if delete_time == 0 else f'{delete_time} min'}"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"Off {'✅' if delete_time == 0 else ''}", callback_data="set_notif_time_0")],
        [InlineKeyboardButton(f"1 min {'✅' if delete_time == 1 else ''}", callback_data="set_notif_time_1"),
         InlineKeyboardButton(f"5 min {'✅' if delete_time == 5 else ''}", callback_data="set_notif_time_5")],
        [InlineKeyboardButton(f"10 min {'✅' if delete_time == 10 else ''}", callback_data="set_notif_time_10"),
         InlineKeyboardButton(f"1 hour {'✅' if delete_time == 60 else ''}", callback_data="set_notif_time_60")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_settings_main_menu")]
    ])
    
    if isinstance(message, CallbackQuery):
        await message.message.edit_text(status_text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)
    else:
        await message.reply_text(status_text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)


async def show_game_settings(client, message):
    if isinstance(message, CallbackQuery):
        chat_id = message.message.chat.id
    else:
        chat_id = message.chat.id
        
    game_status_text = "<b>🕹️ Game Settings:</b>\n\n" \
                       "Yahan aap games se related settings dekh sakte hain."
                       
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Tic Tac Toe Game Start", callback_data="start_tictactoe_from_settings")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_settings_main_menu")]
    ])
    
    if isinstance(message, CallbackQuery):
        await message.message.edit_text(game_status_text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)
    else:
        await message.reply_text(game_status_text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)


@client.on_message(filters.group & filters.command("free"))
async def command_free(client: Client, message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not await is_group_admin(chat_id, user_id):
        return await message.reply_text("Aap group admin nahi hain.")

    if message.reply_to_message:
        target = message.reply_to_message.from_user
    elif len(message.command) > 1:
        arg = message.command[1]
        try:
            target = await client.get_users(int(arg) if arg.isdigit() else arg)
        except Exception:
            return await client.send_message(chat_id, "<b>Invalid user or id provided.</b>", parse_mode=enums.ParseMode.HTML)
    else:
        return await client.send_message(chat_id, "<b>Reply or use /free user or id to whitelist someone.</b>", parse_mode=enums.ParseMode.HTML)

    if not target:
        return await client.send_message(chat_id, "<b>User not found.</b>", parse_mode=enums.ParseMode.HTML)

    add_whitelist_sync(chat_id, target.id)
    reset_warnings_sync(chat_id, target.id, "biolink")
    reset_warnings_sync(chat_id, target.id, "abuse")

    full_name = f"{target.first_name}{(' ' + target.last_name) if target.last_name else ''}"
    mention = f"{full_name}"
    text = f"<b>✅ {mention} has been added to the whitelist</b>"
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🚫 Unwhitelist", callback_data=f"unwhitelist_{target.id}"),
            InlineKeyboardButton("🗑️ Close", callback_data="close")
        ]
    ])
    await client.send_message(chat_id, text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)

@client.on_message(filters.group & filters.command("unfree"))
async def command_unfree(client: Client, message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not await is_group_admin(chat_id, user_id):
        return await message.reply_text("Aap group admin nahi hain.")

    if message.reply_to_message:
        target = message.reply_to_message.from_user
    elif len(message.command) > 1:
        arg = message.command[1]
        try:
            target = await client.get_users(int(arg) if arg.isdigit() else arg)
        except Exception:
            return await client.send_message(chat_id, "<b>Invalid user or id provided.</b>", parse_mode=enums.ParseMode.HTML)
    else:
        return await client.send_message(chat_id, "<b>Reply or use /unfree user or id to unwhitelist someone.</b>", parse_mode=enums.ParseMode.HTML)

    if not target:
        return await client.send_message(chat_id, "<b>User not found.</b>", parse_mode=enums.ParseMode.HTML)

    full_name = f"{target.first_name}{(' ' + target.last_name) if target.last_name else ''}"
    mention = f"{full_name}"

    if is_whitelisted_sync(chat_id, target.id):
        remove_whitelist_sync(chat_id, target.id)
        text = f"<b>🚫 {mention} has been removed from the whitelist</b>"
    else:
        text = f"<b>ℹ️ {mention} is not whitelisted.</b>"

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Whitelist", callback_data=f"whitelist_{target.id}"),
            InlineKeyboardButton("🗑️ Close", callback_data="close")
        ]
    ])
    await client.send_message(chat_id, text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)

@client.on_message(filters.group & filters.command("freelist"))
async def command_freelist(client: Client, message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not await is_group_admin(chat_id, user_id):
        return await message.reply_text("Aap group admin nahi hain.")

    ids = get_whitelist_sync(chat_id)
    if not ids:
        await client.send_message(chat_id, "<b>⚠️ No users are whitelisted in this group.</b>", parse_mode=enums.ParseMode.HTML)
        return

    text = "<b>📋 Whitelisted Users:</b>\n\n"
    for i, uid in enumerate(ids, start=1):
        try:
            user = await client.get_users(uid)
            name = f"{user.first_name}{(' ' + user.last_name) if user.last_name else ''}"
            text += f"{i}: {name} [`{uid}`]\n"
        except:
            text += f"{i}: [User not found] [`{uid}`]\n"

    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🗑️ Close", callback_data="close")]])
    await client.send_message(chat_id, text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)

@client.on_message(filters.command("stats") & filters.user(ADMIN_USER_IDS))
async def stats(client: Client, message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.reply_text("Aapke paas is command ko use karne ki permission nahi hai.")
        return

    total_groups = 0
    total_users = 0
    if db is not None:
        try:
            if db.groups is not None:
                total_groups = db.groups.count_documents({})
            if db.users is not None:
                total_users = db.users.count_documents({})
        except Exception as e:
            logger.error(f"Error fetching stats from DB: {e}")
            await message.reply_text(f"Stats fetch karte samay error hui: {e}")
            return

    stats_message = (
        f"📊 <b>Bot Status:</b>\n\n"
        f"• Total Unique Users (via /start in private chat): {total_users}\n"
        f"• Total Groups Managed: {total_groups}\n"
        f"• Uptime: {str(datetime.now() - bot_start_time).split('.')[0]} \n"
        f"• Last Check: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}"
    )
    await message.reply_text(stats_message, parse_mode=enums.ParseMode.HTML)
    logger.info(f"Admin {message.from_user.id} requested stats.")

@client.on_message(filters.command("broadcast") & filters.user(ADMIN_USER_IDS) & filters.private)
async def broadcast_command(client: Client, message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.reply_text("Aapke paas is command ko use karne ki permission nahi hai.")
        return

    await message.reply_text("📢 Broadcast shuru karne ke liye, kripya apna message bhejein:")
    BROADCAST_MESSAGE[message.from_user.id] = "waiting_for_message"
    logger.info(f"Admin {message.from_user.id} initiated broadcast.")

@client.on_message(filters.private & filters.user(ADMIN_USER_IDS) & ~filters.command([]))
async def handle_broadcast_message(client: Client, message: Message) -> None:
    user = message.from_user

    if BROADCAST_MESSAGE.get(user.id) != "waiting_for_message":
        return

    BROADCAST_MESSAGE[user.id] = message

    keyboard = [
        [InlineKeyboardButton("✅ Yes, Broadcast Now", callback_data="confirm_broadcast")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_broadcast")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await message.reply_text(
            "Kya aap is message ko sabhi groups aur users ko bhejna chahte hain?",
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Error sending broadcast confirmation message to {user.id}: {e}")
        await message.reply_text("Broadcast confirmation message bhejne mein error aaya.")
        BROADCAST_MESSAGE.pop(user.id, None)

@client.on_message(filters.command("addabuse") & filters.user(ADMIN_USER_IDS))
async def add_abuse_word(client: Client, message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.reply_text("Aapke paas is command ko use karne ki permission nahi hai.")
        return
    if len(message.command) < 2:
        await message.reply_text("Kripya woh shabd dein jise aap add karna chahte hain. Upyog: <code>/addabuse &lt;shabd&gt;</code>", parse_mode=enums.ParseMode.HTML)
        return
    word_to_add = " ".join(message.command[1:]).lower().strip()
    if not word_to_add:
        await message.reply_text("Kripya ek valid shabd dein.")
        return
    if profanity_filter is not None:
        try:
            if await profanity_filter.add_bad_word(word_to_add):
                await message.reply_text(f"✅ Shabd <code>{word_to_add}</code> safaltapoorvak jod diya gaya hai\\.", parse_mode=enums.ParseMode.HTML)
                logger.info(f"Admin {message.from_user.id} added abuse word: {word_to_add}.")
            else:
                await message.reply_text(f"Shabd <code>{word_to_add}</code> pehle se ही list mein maujood hai\\.", parse_mode=enums.ParseMode.HTML)
        except Exception as e:
            await message.reply_text(f"Shabd jodte samay error hui: {e}")
            logger.error(f"Error adding abuse word {word_to_add}: {e}")
    else:
        await message.reply_text("Profanity filter initialize nahi hua hai. MongoDB connection mein problem ho sakti hai.")
        logger.error("Profanity filter not initialized, cannot add abuse word.")


# --- NEW COMMAND ---
@client.on_message(filters.command("cleartempdata") & filters.user(ADMIN_USER_IDS))
async def clear_temp_data(client: Client, message: Message):
    """Clears temporary in-memory data and stale database entries."""
    if not is_admin(message.from_user.id):
        return

    status_msg = await message.reply_text("🧹 Safai shuru ho rahi hai... Kripya intezaar karein.")
    
    # 1. Clear in-memory data
    in_memory_cleared = {
        "Tic Tac Toe Games": len(TIC_TAC_TOE_GAMES),
        "Locked Messages": len(LOCKED_MESSAGES),
        "Secret Chats": len(SECRET_CHATS),
    }
    TIC_TAC_TOE_GAMES.clear()
    LOCKED_MESSAGES.clear()
    SECRET_CHATS.clear()

    report_text = "<b>📊 Safai Report</b>\n\n"
    report_text += "<b>In-Memory Data Cleared:</b>\n"
    for key, value in in_memory_cleared.items():
        if value > 0:
            report_text += f"• {key}: {value} entries\n"
    
    logger.info(f"Admin {message.from_user.id} cleared in-memory data.")

    # 2. Clean database
    if db is None:
        report_text += "\n⚠️ MongoDB se connect nahi ho paya, isliye database saaf nahi hua."
        await status_msg.edit_text(report_text, parse_mode=enums.ParseMode.HTML)
        return

    await status_msg.edit_text("🧠 In-memory data saaf ho gaya hai. Ab database check kiya jaa raha hai...")

    inactive_groups = 0
    total_groups = 0
    try:
        group_ids = [g["chat_id"] for g in db.groups.find({}, {"chat_id": 1})]
        total_groups = len(group_ids)
        
        for i, chat_id in enumerate(group_ids):
            if i % 20 == 0: # Update status every 20 checks
                await status_msg.edit_text(f"🔍 Database check ho raha hai... [{i}/{total_groups}]")
            
            try:
                # This call will fail if the bot is not in the chat
                await client.get_chat(chat_id)
                await asyncio.sleep(0.1) # Be gentle with the API
            except (Forbidden, BadRequest, ChatAdminRequired, ValueError) as e:
                # ValueError can happen for invalid chat_id format, good to catch
                logger.warning(f"Bot is no longer in chat {chat_id} or cannot access it ({type(e).__name__}). Deleting related data.")
                
                # Delete all data associated with this chat_id
                db.groups.delete_one({"chat_id": chat_id})
                db.settings.delete_one({"chat_id": chat_id})
                db.warn_settings.delete_one({"chat_id": chat_id})
                db.whitelist.delete_many({"chat_id": chat_id})
                db.warnings.delete_many({"chat_id": chat_id})
                
                inactive_groups += 1
                
        report_text += "\n<b>Database Data Cleared:</b>\n"
        report_text += f"• Kul groups check kiye gaye: {total_groups}\n"
        report_text += f"• Inactive groups ka data hataya gaya: {inactive_groups}\n"
        
        logger.info(f"Database cleanup complete. Removed {inactive_groups} inactive groups.")

    except Exception as e:
        logger.error(f"Error during database cleanup: {e}")
        report_text += f"\n❌ Database saaf karte samay ek error aayi: `{e}`"

    report_text += "\n\n✅ Safai poori hui!"
    await status_msg.edit_text(report_text, parse_mode=enums.ParseMode.HTML)


@client.on_message(filters.new_chat_members)
async def welcome_new_member(client: Client, message: Message) -> None:
    new_members = message.new_chat_members
    chat = message.chat
    bot_info = await client.get_me()

    for member in new_members:
        if member.id == bot_info.id:
            log_message = (
                f"<b>🤖 Bot Joined Group:</b>\n"
                f"Group Name: <code>{chat.title}</code>\n"
                f"Group ID: <code>{chat.id}</code>\n"
                f"Members: {await client.get_chat_members_count(chat.id)}\n"
                f"Added by: {message.from_user.first_name} (`{message.from_user.id}`)\n"
                f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}"
            )
            await log_to_channel(log_message, parse_mode=enums.ParseMode.HTML)
            logger.info(f"Bot joined group: {chat.title} ({chat.id}) added by {message.from_user.id}.")

            if db is not None and db.groups is not None:
                try:
                    db.groups.update_one(
                        {"chat_id": chat.id},
                        {"$set": {"title": chat.title, "type": chat.type.value, "last_active": datetime.now()}},
                        upsert=True
                    )
                except Exception as e:
                    logger.error(f"Error saving group {chat.id} to DB: {e}")
            
            try:
                if await is_group_admin(chat.id, bot_info.id):
                    welcome_text = (
                        f"Hello! Main <b>{bot_info.first_name}</b> hun, aur ab main is group mein moderation karunga.\n"
                        f"Kripya सुनिश्चित karein ki mere paas <b>'Delete Messages'</b>, <b>'Restrict Users'</b> aur <b>'Post Messages'</b> ki admin permissions hain takki main apna kaam theek se kar sakoon.\n\n"
                        f"Aap bot settings ko configure karne ke liye niche diye gaye button ka upyog kar sakte hain."
                    )
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔧 Bot Settings", callback_data="show_settings_main_menu")]
                    ])
                    await message.reply_text(welcome_text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)
                    logger.info(f"Bot confirmed admin status in {chat.title} ({chat.id}).")
                else:
                    await message.reply_text(
                        f"Hello! Main <b>{bot_info.first_name}</b> hun. Is group mein moderation ke liye, kripya mujhe <b>admin</b> banayein aur <b>'Delete Messages'</b>, <b>'Restrict Users'</b>, <b>'Post Messages'</b> ki permissions dein."
                        , parse_mode=enums.ParseMode.HTML)
                    logger.warning(f"Bot is not admin in {chat.title} ({chat.id}). Functionality will be limited.")
            except Exception as e:
                logger.error(f"Error during bot's self-introduction in {chat.title} ({chat.id}): {e}")
        else:
            log_message = (
                f"<b>🆕 New Member Joined:</b>\n"
                f"Group: <code>{chat.title}</code>\n"
                f"Group ID: <code>{chat.id}</code>\n"
                f"User: {member.first_name} (`{member.id}`)\n"
                f"Username: @{member.username if member.username else 'N/A'}\n"
                f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}"
            )
            await log_to_channel(log_message, parse_mode=enums.ParseMode.HTML)
            logger.info(f"New member {member.id} joined group {chat.id}.")

            try:
                user_profile = await client.get_chat(member.id)
                bio = user_profile.bio or ""
                settings = get_group_settings(chat.id)
                
                is_whitelisted = is_whitelisted_sync(chat.id, member.id)
                
                if settings.get("delete_biolink", True) and not is_whitelisted and URL_PATTERN.search(bio):
                    warn_limit, punishment = get_warn_settings(chat.id, "biolink")

                    if punishment:
                        count = increment_warning_sync(chat.id, member.id, "biolink")
                        if count >= warn_limit:
                            await handle_incident(client, chat.id, member, "bio-link", message, "punished", category="biolink")
                        else:
                            await handle_incident(client, chat.id, member, "bio-link", message, "warn", category="biolink")
            except Exception as e:
                logger.error(f"Error checking bio for new member {member.id}: {e}")

@client.on_message(filters.left_chat_member)
async def left_member_handler(client: Client, message: Message) -> None:
    left_member = message.left_chat_member
    bot_info = await client.get_me()
    chat = message.chat

    if left_member and left_member.id == bot_info.id:
        log_message = (
            f"<b>❌ Bot Left Group:</b>\n"
            f"Group Name: <code>{chat.title}</code>\n"
            f"Group ID: <code>{chat.id}</code>\n"
            f"Removed by: {message.from_user.first_name} (`{message.from_user.id}`)\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}"
        )
        await log_to_channel(log_message, parse_mode=enums.ParseMode.HTML)
        logger.info(f"Bot was removed from group: {chat.title} ({chat.id}) by {message.from_user.id}.")
        # No need to delete from DB here, /cleartempdata will handle it.
    else:
        log_message = (
            f"<b>➡️ Member Left:</b>\n"
            f"Group: <code>{chat.title}</code>\n"
            f"Group ID: <code>{chat.id}</code>\n"
            f"User: {left_member.first_name} (`{left_member.id}`)\n"
            f"Username: @{left_member.username if left_member.username else 'N/A'}\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}"
        )
        await log_to_channel(log_message, parse_mode=enums.ParseMode.HTML)
        logger.info(f"Member {left_member.id} left group {chat.id}.")


# --- Core Message Handler (Profanity, URL in message) ---
@client.on_message(filters.group & filters.text & ~filters.via_bot)
async def handle_all_messages(client: Client, message: Message) -> None:
    user = message.from_user
    chat = message.chat
    message_text = message.text

    if not user:
        return
    if await is_group_admin(chat.id, user.id) or is_whitelisted_sync(chat.id, user.id):
        return

    settings = get_group_settings(chat.id)

    # First, check for abuse words
    if settings.get("delete_abuse", True) and profanity_filter is not None and profanity_filter.contains_profanity(message_text):
        warn_limit, punishment = get_warn_settings(chat.id, "abuse")
        count = get_warnings_sync(user.id, chat.id, "abuse") + 1
        
        if count >= warn_limit:
            await handle_incident(client, chat.id, user, "Abusive word", message, "punished", category="abuse")
        else:
            await handle_incident(client, chat.id, user, "Abusive word", message, "warn", category="abuse")
        return

    # Check for links/usernames
    if settings.get("delete_links_usernames", True) and URL_PATTERN.search(message_text):
        await handle_incident(client, chat.id, user, "Link or Username in Message", message, "link_or_username")
        return

    # Check for biolink
    if settings.get("delete_biolink", True):
        try:
            user_profile = await client.get_chat(user.id)
            user_bio = user_profile.bio or ""
            if URL_PATTERN.search(user_bio):
                warn_limit, punishment = get_warn_settings(chat.id, "biolink")
                count = get_warnings_sync(user.id, chat.id, "biolink") + 1
                
                if count >= warn_limit:
                    await handle_incident(client, chat.id, user, "bio-link", message, "punished", category="biolink")
                else:
                    await handle_incident(client, chat.id, user, "bio-link", message, "warn", category="biolink")
                return

        except Exception as e:
            logger.error(f"Error checking bio for user {user.id}: {e}")
            
# --- Handler for Edited Messages ---
@client.on_edited_message(filters.text & filters.group & ~filters.via_bot)
async def handle_edited_messages(client: Client, edited_message: Message) -> None:
    if not edited_message or not edited_message.text or not edited_message.edit_date:
        return

    user = edited_message.from_user
    chat = edited_message.chat

    if not user:
        return

    is_sender_admin = await is_group_admin(chat.id, user.id)
    if is_sender_admin or is_whitelisted_sync(chat.id, user.id):
        return
    
    settings = get_group_settings(chat.id)
    if settings.get("delete_edited", True):
        # The edit_date check confirms it's an actual edit, not a forward or other message type that might trigger this.
        await handle_incident(client, chat.id, user, "Edited message deleted", edited_message, "edited_message_deleted")


# --- Callback Query Handlers ---
@client.on_callback_query()
async def callback_handler(client: Client, query: CallbackQuery) -> None:
    data = query.data
    user_id = query.from_user.id
    chat_id = query.message.chat.id
    
    if query.message.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        if data not in ["close", "help_menu", "other_bots", "donate_info", "back_to_main_menu"] and not data.startswith(('show_', 'toggle_', 'config_', 'setwarn_', 'tictac_', 'show_lock_', 'show_secret_', 'freelist_settings', 'toggle_punishment_', 'freelist_show', 'whitelist_', 'unwhitelist_', 'tictac_new_game_starter_','set_notif_time_')):
            is_current_group_admin = await is_group_admin(chat_id, user_id)
            if not is_current_group_admin:
                return await query.answer("❌ Aapke paas is action ko karne ki permission nahi hai. Aap group admin nahi hain.", show_alert=True)
    else:
        await query.answer()

    if data == "close":
        try:
            await query.message.delete()
        except MessageNotModified:
            pass
        return

    if data == "help_menu":
        help_text = (
            "<b>🛠️ Bot Commands & Usage</b>\n\n"
            "<b>Private Message Commands:</b>\n"
            "`/lock <@username> <message>` - Message ko lock karein taaki sirf mention kiya gaya user hi dekh sake. (Group mein hi kaam karega)\n"
            "`/secretchat <@username> <message>` - Ek secret message bhejein, jo group mein sirf ek pop-up mein dikhega. (Group mein hi kaam karega)\n\n"
            "<b>Tic Tac Toe Game:</b>\n"
            "`/tictac @user1 @user2` - Do users ke saath Tic Tac Toe game shuru karein. Ek baar mein ek hi game chalega.\n\n"
            "<b>BioLink Protector Commands:</b>\n"
            "`/free` – whitelist a user (reply or user/id)\n"
            "`/unfree` – remove from whitelist\n"
            "`/freelist` – list all whitelisted users\n\n"
            "<b>General Moderation Commands:</b>\n"
            f"• <code>/settings</code>: Bot ki settings kholen (Group Admins only).\n"
            f"• <code>/stats</code>: Bot usage stats dekhein (sirf bot admins ke liye).\n"
            f"• <code>/broadcast</code>: Sabhi groups mein message bhejein (sirf bot admins ke liye).\n"
            f"• <code>/addabuse &lt;shabd&gt;</code>: Custom gaali wala shabd filter mein add karein (sirf bot admins ke liye).\n"
            f"• <code>/checkperms</code>: Group mein bot ki permissions jaanchein (sirf group admins ke liye).\n"
            "• <code>/cleartempdata</code>: Bot ka temporary aur bekar data saaf karein (sirf bot admins ke liye).\n\n"
            "<b>When someone with a URL in their bio or a link in their message posts, I’ll:</b>\n"
            " 1. ⚠️ Warn them\n"
            " 2. 🔇 Mute if they exceed limit\n"
            " 3. 🔨 Ban if set to ban\n\n"
            "<b>Use the inline buttons on warnings to cancel or whitelist</b>"
        )
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="back_to_main_menu")], [InlineKeyboardButton("🗑️ Close", callback_data="close")]])
        await query.message.edit_text(help_text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)
        return

    if data == "other_bots":
        other_bots_text = (
            "🤖 <b>Mere Dusre Bots:</b>\n\n"
            "Movies, webseries, anime, etc. dekhne ke liye sabse best bot: \n"
            "➡️ @asfilter_bot\n\n"
            "Group par chat ke liye bot chahiye jo aapke group par aadmi ki tarah baatein kare, logon ka manoranjan kare, aur isme kai commands aur tagde features bhi hain. Isme har mahine paise jeetne ka leaderboard bhi hai: \n"
            "➡️ @askiangelbot"
        )
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="back_to_main_menu")], [InlineKeyboardButton("🗑️ Close", callback_data="close")]])
        await query.message.edit_text(other_bots_text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML, disable_web_page_preview=True)
        return
        
    if data == "donate_info":
        donate_text = (
            "💖 <b>Humein Support Karein!</b>\n\n"
            "Agar aapko mera kaam pasand aaya hai, toh aap humein support kar sakte hain. Aapka chhota sa daan bhi bahut madad karega!\n\n"
            "<b>UPI ID:</b> `arsadsaifi8272@ibl`\n\n"
            "<b>Thank you for your support!</b>"
        )
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="back_to_main_menu")], [InlineKeyboardButton("🗑️ Close", callback_data="close")]])
        await query.message.edit_text(donate_text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)
        return

    if data == "back_to_main_menu":
        bot_info = await client.get_me()
        bot_name = bot_info.first_name
        bot_username = bot_info.username
        add_to_group_url = f"https://t.me/{bot_username}?startgroup=true"
        
        welcome_message = (
            f"👋 <b>Namaste {query.from_user.first_name}!</b>\n\n"
            f"Mai <b>{bot_name}</b> hun, aapka group moderator bot. "
            f"Mai aapke groups ko saaf suthra rakhne mein madad karta hun."
        )

        keyboard = [
            [InlineKeyboardButton("➕ Add Me To Your Group", url=add_to_group_url)],
            [InlineKeyboardButton("❓ Help", callback_data="help_menu"), InlineKeyboardButton("🤖 Other Bots", callback_data="other_bots")],
            [InlineKeyboardButton("📢 Update Channel", url="https://t.me/asbhai_bsr"), InlineKeyboardButton("💖 Donate", callback_data="donate_info")],
            [InlineKeyboardButton("📈 Promotion", url="https://t.me/asprmotion")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.message.edit_text(
            text=welcome_message,
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML,
            disable_web_page_preview=True
        )
        return

    if data == "show_settings_main_menu":
        await show_settings_main_menu(client, query)
        return

    if data == "show_onoff_settings":
        await show_on_off_settings(client, query)
        return
        
    if data == "show_warn_punishment_settings":
        await show_warn_punishment_settings(client, query)
        return
        
    if data == "show_game_settings":
        await show_game_settings(client, query)
        return

    if data == "show_notification_delete_time_menu":
        await show_notification_delete_time_menu(client, query)
        return
    
    if data.startswith("set_notif_time_"):
        try:
            time_in_minutes = int(data.split('_')[-1])
            update_notification_delete_time(chat_id, time_in_minutes)
            await show_notification_delete_time_menu(client, query)
        except ValueError:
            await query.answer("Invalid time selected.")
        return
        
    if data == "freelist_settings":
        await command_freelist_callback(client, query)
        return

    if data.startswith("toggle_"):
        setting_key = data.split('toggle_', 1)[1]
        settings = get_group_settings(chat_id)
        current_status = settings.get(setting_key, True)
        new_status = not current_status
        update_group_setting(chat_id, setting_key, new_status)
        await show_on_off_settings(client, query)
        return
        
    if data.startswith("config_"):
        category = data.split('_')[1]
        warn_limit, punishment = get_warn_settings(chat_id, category)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"Set Warn Limit ({warn_limit})", callback_data=f"set_warn_limit_{category}")],
            [
                InlineKeyboardButton(f"Punish: Mute {'✅' if punishment == 'mute' else ''}", callback_data=f"set_punishment_mute_{category}"),
                InlineKeyboardButton(f"Punish: Ban {'✅' if punishment == 'ban' else ''}", callback_data=f"set_punishment_ban_{category}")
            ],
            [InlineKeyboardButton("⬅️ Back", callback_data="show_warn_punishment_settings")]
        ])
        await query.message.edit_text(f"<b>⚙️ Configure {category.capitalize()} Warnings:</b>", reply_markup=kb, parse_mode=enums.ParseMode.HTML)
        return

    if data.startswith("set_warn_limit_"):
        category = data.split('_')[-1]
        warn_limit, _ = get_warn_settings(chat_id, category)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"3 {'✅' if warn_limit == 3 else ''}", callback_data=f"set_limit_{category}_3"),
             InlineKeyboardButton(f"4 {'✅' if warn_limit == 4 else ''}", callback_data=f"set_limit_{category}_4"),
             InlineKeyboardButton(f"5 {'✅' if warn_limit == 5 else ''}", callback_data=f"set_limit_{category}_5")],
            [InlineKeyboardButton("⬅️ Back", callback_data=f"config_{category}")]
        ])
        await query.message.edit_text(f"<b>{category.capitalize()} Warn Limit:</b>\n"
                                     f"Select the number of warnings before a user is punished.",
                                     reply_markup=kb, parse_mode=enums.ParseMode.HTML)
        return

    if data.startswith("set_limit_"):
        parts = data.split('_')
        category = parts[2]
        limit = int(parts[3])
        update_warn_settings(chat_id, category, limit=limit)
        await query.message.edit_text(f"✅ {category.capitalize()} warning limit set to {limit}.",
                                     reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data=f"config_{category}")]])
                                     , parse_mode=enums.ParseMode.HTML)
        return

    if data.startswith("set_punishment_"):
        parts = data.split('_')
        punishment = parts[2]
        category = parts[3]
        update_warn_settings(chat_id, category, punishment=punishment)
        await query.message.edit_text(f"✅ {category.capitalize()} punishment set to {punishment.capitalize()}.",
                                     reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data=f"config_{category}")]])
                                     , parse_mode=enums.ParseMode.HTML)
        return

    if data == "back_to_settings_main_menu":
        await show_settings_main_menu(client, query)
        return

    if data == "start_tictactoe_from_settings":
        user_id = query.from_user.id
        user = query.from_user
        
        if chat_id in TIC_TAC_TOE_GAMES:
            await query.answer("Ek game pehle se hi chal raha hai.", show_alert=True)
            return

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"Join Game", callback_data=f"tictac_join_game_{user.id}")]
        ])
        
        await query.message.edit_text(
            f"<b>Tic Tac Toe Game Start</b>\n\n"
            f"<a href='tg://user?id={user.id}'>{user.first_name}</a> ne ek Tic Tac Toe game shuru kiya hai!\n"
            f"Ek aur player ke join karne ka intezaar hai.",
            reply_markup=keyboard,
            parse_mode=enums.ParseMode.HTML
        )
        return
        
    if data.startswith("unmute_"):
        parts = data.split('_')
        target_id = int(parts[1])
        group_chat_id = int(parts[2])
        try:
            await client.restrict_chat_member(group_chat_id, target_id, ChatPermissions(can_send_messages=True))
            reset_warnings_sync(group_chat_id, target_id, "abuse")
            reset_warnings_sync(group_chat_id, target_id, "biolink")
            user_obj = await client.get_chat_member(group_chat_id, target_id)
            user_mention = f"<a href='tg://user?id={target_id}'>{user_obj.user.first_name}</a>"
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("Whitelist ✅", callback_data=f"whitelist_{target_id}_{group_chat_id}"), InlineKeyboardButton("🗑️ Close", callback_data="close")]])
            try:
                await query.message.edit_text(f"<b>✅ {user_mention} unmuted!</b>", reply_markup=kb, parse_mode=enums.ParseMode.HTML)
            except MessageNotModified:
                pass
        except errors.ChatAdminRequired:
            try:
                await query.message.edit_text("<b>I don't have permission to unmute users.</b>", parse_mode=enums.ParseMode.HTML)
            except MessageNotModified:
                pass
        return

    if data.startswith("cancel_warn_"):
        target_id = int(data.split("_")[-1])
        reset_warnings_sync(chat_id, target_id, "biolink")
        reset_warnings_sync(chat_id, target_id, "abuse")
        user_obj = await client.get_chat_member(chat_id, target_id)
        full_name = f"{user_obj.user.first_name}{(' ' + user_obj.user.last_name) if user_obj.user.last_name else ''}"
        mention = f"<a href='tg://user?id={target_id}'>{full_name}</a>"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Whitelist✅", callback_data=f"whitelist_{target_id}_{chat_id}"),
             InlineKeyboardButton("🗑️ Close", callback_data="close")]
        ])
        try:
            await query.message.edit_text(f"<b>✅ {mention} (`{target_id}`) has no more warnings!</b>", reply_markup=kb, parse_mode=enums.ParseMode.HTML)
        except MessageNotModified:
            pass
        return
        
    if data.startswith("whitelist_"):
        target_id = int(data.split("_")[1])
        add_whitelist_sync(chat_id, target_id)
        reset_warnings_sync(chat_id, target_id, "biolink")
        reset_warnings_sync(chat_id, target_id, "abuse")
        try:
            user = await client.get_chat_member(chat_id, target_id)
            full_name = f"{user.first_name}{(' ' + user.last_name) if user.last_name else ''}"
            mention = f"<a href='tg://user?id={target_id}'>{full_name}</a>"
        except Exception:
            mention = f"User (`{target_id}`)"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚫 Unwhitelist", callback_data=f"unwhitelist_{target_id}"),
             InlineKeyboardButton("🗑️ Close", callback_data="close")]
        ])
        try:
            await query.message.edit_text(f"<b>✅ {mention} has been whitelisted!</b>", reply_markup=kb, parse_mode=enums.ParseMode.HTML)
        except MessageNotModified:
            pass
        return

    if data.startswith("unwhitelist_"):
        target_id = int(data.split("_")[1])
        remove_whitelist_sync(chat_id, target_id)
        try:
            user = await client.get_chat_member(chat_id, target_id)
            full_name = f"{user.first_name}{(' ' + user.last_name) if user.last_name else ''}"
            mention = f"<a href='tg://user?id={target_id}'>{full_name}</a>"
        except Exception:
            mention = f"User (`{target_id}`)"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Whitelist✅", callback_data=f"whitelist_{target_id}"),
             InlineKeyboardButton("🗑️ Close", callback_data="close")]
        ])
        try:
            await query.message.edit_text(f"<b>❌ {mention} has been removed from whitelist.</b>", reply_markup=kb, parse_mode=enums.ParseMode.HTML)
        except MessageNotModified:
            pass
        return

    async def command_freelist_callback(client, query):
        chat_id = query.message.chat.id
        ids = get_whitelist_sync(chat_id)
        if not ids:
            text = "<b>⚠️ No users are whitelisted in this group.</b>"
        else:
            text = "<b>📋 Whitelisted Users:</b>\n\n"
            for i, uid in enumerate(ids, start=1):
                try:
                    user = await client.get_users(uid)
                    name = f"{user.first_name}{(' ' + user.last_name) if user.last_name else ''}"
                    text += f"{i}: <a href='tg://user?id={uid}'>{name}</a> [`{uid}`]\n"
                except:
                    text += f"{i}: [User not found] [`{uid}`]\n"

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Back", callback_data="show_settings_main_menu")],
            [InlineKeyboardButton("🗑️ Close", callback_data="close")]
        ])
        await query.message.edit_text(text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML, disable_web_page_preview=True)

@client.on_message(filters.command("checkperms") & filters.group)
async def check_permissions(client: Client, message: Message):
    chat = message.chat
    bot_id = client.me.id
    
    if not await is_group_admin(chat.id, message.from_user.id):
        await message.reply_text("Aap group admin nahi hain, isliye aap yeh command ka upyog nahi kar sakte.")
        return

    try:
        bot_member = await client.get_chat_member(chat.id, bot_id)
        if bot_member.status != enums.ChatMemberStatus.ADMINISTRATOR:
            await message.reply_text("Bot is not an admin in this group. Please make the bot an admin.")
            return

        perms = bot_member.privileges
        message_text = (
            f"<b>{chat.title} mein bot ki anumatiyan (Permissions):</b>\n\n"
            f"<b>Can Delete Messages:</b> {'✅ Yes' if perms.can_delete_messages else '❌ No'}\n"
            f"<b>Can Restrict Members:</b> {'✅ Yes' if perms.can_restrict_members else '❌ No'}\n"
            f"<b>Can Pin Messages:</b> {'✅ Yes' if perms.can_pin_messages else '❌ No'}\n"
            f"<b>Can Post Messages:</b> {'✅ Yes' if perms.can_post_messages else '❌ No'}\n"
        )

        await message.reply_text(message_text, parse_mode=enums.ParseMode.HTML)
        logger.info(f"Admin {message.from_user.id} requested permissions check in chat {chat.id}.")
    except Exception as e:
        logger.error(f"Anumatiyan jaanchte samay ek error hui: {e}")
        await message.reply_text(f"Anumatiyan jaanchte samay ek error hui: {e}")


# --- Flask App for Health Check ---
@app.route('/')
def health_check():
    """Simple health check endpoint for Koyeb."""
    return jsonify({"status": "healthy", "bot_running": True, "mongodb_connected": db is not None}), 200

def run_flask_app():
    """Runs the Flask application."""
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)

# --- Entry Point ---
if __name__ == "__main__":
    init_mongodb()

    flask_thread = threading.Thread(target=run_flask_app)
    flask_thread.daemon = True
    flask_thread.start()

    logger.info("Bot is starting...")
    client.run()
    logger.info("Bot stopped")
