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
# Assuming profanity_filter.py is in the same directory and has a working ProfanityFilter class
from profanity_filter import ProfanityFilter

# --- Configuration ---
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "-1002352329534"))
MONGO_DB_URI = os.getenv("MONGO_DB_URI")
ADMIN_USER_IDS = [7315805581]  # NOTE: Replace with your actual admin IDs.

bot_start_time = datetime.now()
BROADCAST_MESSAGE = {}

# Corrected regex pattern to be case-insensitive for 'HTTPS' and to handle @usernames
URL_PATTERN = re.compile(r'(https?://|www\.)[a-zA-Z0-9.\-]+(\.[a-zA-Z]{2,})+(/[a-zA-Z0-9._%+-]*)*', re.IGNORECASE)
USERNAME_PATTERN = re.compile(r'@\w+', re.IGNORECASE)

# --- Tagging variables
TAG_MESSAGES = {}
ONGOING_TAGGING_TASKS = {}
# Updated EMOJIS as per your request
EMOJIS = ['😀', '😃', '😄', '😁', '😆', '😅', '🤣', '😂', '🙂', '🙃', '🫠', '😉', '😊', '😇', '🥰', '😍', '🙂', '😘', '😙', '☺️', '🥲', '😋', '😛', '😜', '😝', '🤑', '🤗', '🤭', '🫢', '🫣', '😐', '🤨', '🤔', '🤐', '🫡', '🤥', '🫥', '😮‍💨', '😶‍🌫️', '🙄', '😏', '😒', '🙂‍↕️', '🫨', '🙂‍↕️', '🤥', '😔', '😪', '😴', '🤧', '😷', '🤢', '🤕', '🥶', '🥵', '😵', '🤯', '🤠', '🥳', '🙁', '🥸', '🫤', '🫤', '🤓', '😕', '🧐', '☹️', '😮', '😦', '🥺', '😲', '😳', '😥', '😰', '😧', '😢', '😭', '😱', '😡', '😣', '🥱', '😓', '😫', '😩', '😠', '🤬', '🤡', '👿', '☠️', '💀', '💀', '👺', '👽', '👹', '👾', '👻', '😺', '😸', '😹', '🙈', '😻', '😾', '😽', '😿', '🙀', '💋', '💌', '🙉', '💝', '💖', '💗', '❤️‍🩹', '💕', '❤️‍🔥', '💟', '💔', '❣️', '🧡', '💛', '🩷', '💙', '❤️', '💜', '🤎', '💫', '🩶', '💢', '🤍', '💯', '💣', '💬', '💨', '🗯', '💦', '💭', '💤', '🖕', '🫦', '👄', '👅', '🧠', '👀', '👁', '🦴', '🦷', '🤳', '👶', '🧒', '👦', '🧑', '👱', '👨', '🧔', '🧔‍♀️', '👨‍🦱', '👨‍🦳', '👨‍🦲', '👩‍🦳', '👩‍🦰', '🧑‍🦱', '👩‍🦱', '👩‍🦰', '🧑‍🦰', '🫆', '🫂', '🗣', '👥️', '👤', '🧑‍🧒', '🧑‍🧑‍🧒‍🧒', '🧑‍🧒‍🧒', '🧑‍🧑‍🧒‍🧒']


# --- New Constants from your first snippet ---
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
        
        # New: `settings` collection to store group settings
        db.settings.create_index("chat_id", unique=True)
        
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

async def log_to_channel(text: str, parse_mode: enums.ParseMode = None) -> None:
    """Sends a log message to the predefined LOG_CHANNEL_ID with better error handling."""
    if not LOG_CHANNEL_ID:
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


def get_config_sync(chat_id):
    if db is None: return DEFAULT_CONFIG
    config = db.config.find_one({"chat_id": chat_id})
    if config:
        return config.get("mode", "warn"), config.get("limit", DEFAULT_WARNING_LIMIT), config.get("penalty", DEFAULT_PUNISHMENT)
    return DEFAULT_CONFIG

def update_config_sync(chat_id, mode=None, limit=None, penalty=None):
    if db is None: return
    update_doc = {}
    if mode: update_doc["mode"] = mode
    if limit is not None: update_doc["limit"] = limit
    if penalty: update_doc["penalty"] = penalty
    db.config.update_one({"chat_id": chat_id}, {"$set": update_doc}, upsert=True)

# New: Get group settings from DB
def get_group_settings(chat_id):
    if db is None:
        return {
            "delete_biolink": True,
            "delete_abuse": True,
            "delete_edited": True
        }
    settings = db.settings.find_one({"chat_id": chat_id})
    if not settings:
        # Default settings if not found
        default_settings = {
            "chat_id": chat_id,
            "delete_biolink": True,
            "delete_abuse": True,
            "delete_edited": True
        }
        db.settings.insert_one(default_settings)
        return default_settings
    return settings

# New: Update group settings in DB
def update_group_setting(chat_id, setting_key, setting_value):
    if db is None: return
    db.settings.update_one(
        {"chat_id": chat_id},
        {"$set": {setting_key: setting_value}},
        upsert=True
    )

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

def get_warnings_sync(user_id: int, chat_id: int):
    if db is None: return 0
    warnings_doc = db.warnings.find_one({"user_id": user_id, "chat_id": chat_id})
    return warnings_doc.get("count", 0) if warnings_doc else 0

def increment_warning_sync(chat_id, user_id):
    if db is None: return 1
    warnings_doc = db.warnings.find_one_and_update(
        {"chat_id": chat_id, "user_id": user_id},
        {"$inc": {"count": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER
    )
    return warnings_doc.get("count", 1)

def reset_warnings_sync(chat_id, user_id):
    if db is None: return
    db.warnings.delete_one({"chat_id": chat_id, "user_id": user_id})

# User profile button ko hatakar code ko badla gaya hai
async def handle_incident(client: Client, chat_id, user, reason, original_message: Message, case_type):
    original_message_id = original_message.id
    user_mention = user.mention

    try:
        await client.delete_messages(chat_id=chat_id, message_ids=original_message_id)
        logger.info(f"Deleted {reason} message from {user.username or user.mention} ({user.id}) in {chat_id}.")
    except Exception as e:
        logger.error(f"Error deleting message in {chat_id}: {e}. Make sure the bot has 'Delete Messages' admin permission.")

    full_name = f"{user.first_name}{(' ' + user.last_name) if user.last_name else ''}"
    user_mention_text = f"<a href='tg://user?id={user.id}'>{full_name}</a>"

    # THIS IS THE EDITED MESSAGE NOTIFICATION
    if case_type == "edited_message_deleted":
        notification_text = (
            f"<b>📝 Edited Message Deleted!</b>\n\n"
            f"Hey {user_mention_text}, your edited message was removed as editing messages to circumvent rules is not allowed.\n\n"
            f"<i>Please send a new message instead of editing old ones.</i>"
        )
    # THIS IS THE ABUSIVE MESSAGE NOTIFICATION
    elif case_type == "abuse":
         notification_text = (
            f"<b>🚫 Hey {user_mention_text}, your message was removed!</b>\n\n"
            f"It contained language that violates our community guidelines.\n\n"
            f"✅ <i>Please be mindful of your words to maintain a safe and respectful environment for everyone.</i>"
        )
    # THIS IS THE LINK OR USERNAME NOTIFICATION
    else:
        notification_text = (
            f"<b>🔗 Link/Username Removed!</b>\n\n"
            f"Hey {user_mention_text}, your message was removed because it contained a link or username."
            f"\n\n"
            f"<i>Please avoid sharing links or usernames in the group.</i>"
        )

    keyboard = [
        [
            InlineKeyboardButton("🔧 Admin Actions", callback_data=f"admin_actions_menu_{user.id}_{chat_id}")
        ],
        [InlineKeyboardButton("🗑️ Close", callback_data="close")]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await client.send_message(
            chat_id=chat_id,
            text=notification_text,
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML
        )
        logger.info(f"Incident notification sent for user {user.id} in chat {chat_id}.")
        
        log_message = (
            f"🚨 <b>Incident Detected</b> 🚨\n\n"
            f"<b>Group:</b> {original_message.chat.title} (`{chat_id}`)\n"
            f"<b>User:</b> {user.mention} (`{user.id}`)\n"
            f"<b>Reason:</b> {reason}\n"
            f"<b>Case Type:</b> {case_type}\n"
            f"<b>Timestamp:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}"
        )
        await log_to_channel(log_message, parse_mode=enums.ParseMode.HTML)

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
            f"👋 <b>Namaste {user.mention}!</b>\n\n"
            f"Mai <b>{bot_name}</b> hun, aapka group moderator bot. "
            f"Mai aapke groups ko saaf suthra rakhne mein madad karta hun, "
            f"gaaliyon wale messages ko delete karta hun aur zaroorat padne par warning bhi deta hun.\n\n"
            f"<b>Mere features:</b>\n"
            f"• Gaali detection aur deletion\n"
            f"• Bio-link protection\n"
            f"• User warnings aur actions (Mute, Ban, Kick)\n"
            f"• Whitelist management\n"
            f"• Incident logging\n\n"
            f"Agar aapko koi madad chahiye, toh niche diye gaye buttons ka upyog karein."
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
            f"User: {user.mention} (`{user.id}`)\n"
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
                # ADDED: Settings button for group start message
                group_start_message = f"Hello! Main <b>{bot_info.first_name}</b> hun, aapka group moderation bot. Main aapke group ko saaf suthra rakhne mein madad karunga."
                group_keyboard = [
                    [InlineKeyboardButton("➕ Add Me To Your Group", url=add_to_group_url)],
                    [InlineKeyboardButton("🔧 Bot Settings", callback_data="show_settings_menu")],
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
        "<b>BioLink Protector Commands:</b>\n"
        "`/config` – set warn-limit & punishment mode\n"
        "`/free` – whitelist a user (reply or user/id)\n"
        "`/unfree` – remove from whitelist\n"
        "`/freelist` – list all whitelisted users\n\n"
        "<b>General Moderation Commands:</b>\n"
        f"• <code>/settings</code>: Bot ki settings kholen (Group Admins only).\n" # ADDED: New settings command
        f"• <code>/stats</code>: Bot usage stats dekhein (sirf bot admins ke liye).\n"
        f"• <code>/broadcast</code>: Sabhi groups mein message bhejein (sirf bot admins ke liye).\n"
        f"• <code>/addabuse &lt;shabd&gt;</code>: Custom gaali wala shabd filter mein add karein (sirf bot admins ke liye).\n"
        f"• <code>/checkperms</code>: Group mein bot ki permissions jaanchein (sirf group admins ke liye).\n"
        "• <code>/tagall &lt;message&gt;</code>: Sabhi members ko tag karein.\n"
        "• <code>/onlinetag &lt;message&gt;</code>: Online members ko tag karein.\n"
        "• <code>/admin &lt;message&gt;</code>: Sirf group admins ko tag karein.\n"
        "• <code>/tagstop</code>: Saare tagging messages ko delete kar dein.\n\n"
        "<b>When someone with a URL in their bio or a link in their message posts, I’ll:</b>\n"
        " 1. ⚠️ Warn them\n"
        " 2. 🔇 Mute if they exceed limit\n"
        " 3. 🔨 Ban if set to ban\n\n"
        "<b>Use the inline buttons on warnings to cancel or whitelist</b>"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🗑️ Close", callback_data="close")]])
    await client.send_message(chat_id, help_text, reply_markup=kb, parse_mode=enums.ParseMode.HTML)

# ADDED: New settings command handler
@client.on_message(filters.group & filters.command("settings"))
async def settings_command_handler(client: Client, message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    if not await is_group_admin(chat_id, user_id):
        await message.reply_text("Aap group admin nahi hain, is command ka upyog nahi kar sakte.")
        return

    await show_settings_menu(client, message)

async def show_settings_menu(client, message):
    chat_id = message.chat.id
    settings = get_group_settings(chat_id)
    
    biolink_status = "✅ On" if settings.get("delete_biolink", True) else "❌ Off"
    abuse_status = "✅ On" if settings.get("delete_abuse", True) else "❌ Off"
    edited_status = "✅ On" if settings.get("delete_edited", True) else "❌ Off"

    settings_text = (
        "⚙️ <b>Bot Settings:</b>\n\n"
        "Yahan aap group moderation features ko chalu/band kar sakte hain."
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"Bio Link Users Delete: {biolink_status}", callback_data="toggle_delete_biolink")],
        [InlineKeyboardButton(f"Abuse Messages Delete: {abuse_status}", callback_data="toggle_delete_abuse")],
        [InlineKeyboardButton(f"Edited Messages Deletion: {edited_status}", callback_data="toggle_delete_edited")],
        [InlineKeyboardButton("🗑️ Close", callback_data="close")]
    ])

    if isinstance(message, CallbackQuery):
        await message.message.edit_text(settings_text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)
    else:
        await message.reply_text(settings_text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)


@client.on_message(filters.group & filters.command("config"))
async def configure(client: Client, message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    if not await is_group_admin(chat_id, user_id):
        return

    mode, limit, penalty = get_config_sync(chat_id)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Warn Limit", callback_data="warn_limit")],
        [
            InlineKeyboardButton("Mute ✅" if penalty == "mute" else "Mute", callback_data="mute"),
            InlineKeyboardButton("Ban ✅" if penalty == "ban" else "Ban", callback_data="ban")
        ],
        [InlineKeyboardButton("Close", callback_data="close")]
    ])
    await client.send_message(
        chat_id,
        "<b>Choose penalty for users with links in bio:</b>",
        reply_markup=keyboard,
        parse_mode=enums.ParseMode.HTML
    )
    await message.delete()

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
    reset_warnings_sync(chat_id, target.id)

    full_name = f"{target.first_name}{(' ' + target.last_name) if target.last_name else ''}"
    mention = f"<a href='tg://user?id={target.id}'>{full_name}</a>"
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
    mention = f"<a href='tg://user?id={target.id}'>{full_name}</a>"

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
                await message.reply_text(f"Shabd <code>{word_to_add}</code> pehle se hi list mein maujood hai\\.", parse_mode=enums.ParseMode.HTML)
        except Exception as e:
            await message.reply_text(f"Shabd jodte samay error hui: {e}")
            logger.error(f"Error adding abuse word {word_to_add}: {e}")
    else:
        await message.reply_text("Profanity filter initialize nahi hua hai. MongoDB connection mein problem ho sakti hai.")
        logger.error("Profanity filter not initialized, cannot add abuse word.")


# CHANGED: new_chat_members handler for better logging and settings button
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
                f"Added by: {message.from_user.mention} (`{message.from_user.id}`)\n"
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
            
            # ADDED: New settings button on bot's welcome message
            try:
                if await is_group_admin(chat.id, bot_info.id):
                    welcome_text = (
                        f"Hello! Main <b>{bot_info.first_name}</b> hun, aur ab main is group mein moderation karunga.\n"
                        f"Kripya सुनिश्चित karein ki mere paas <b>'Delete Messages'</b>, <b>'Restrict Users'</b> aur <b>'Post Messages'</b> ki admin permissions hain takki main apna kaam theek se kar sakoon.\n\n"
                        f"Aap bot settings ko configure karne ke liye niche diye gaye button ka upyog kar sakte hain."
                    )
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔧 Bot Settings", callback_data="show_settings_menu")]
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
            # New user joined, log this event
            log_message = (
                f"<b>🆕 New Member Joined:</b>\n"
                f"Group: <code>{chat.title}</code>\n"
                f"Group ID: <code>{chat.id}</code>\n"
                f"User: {member.mention} (`{member.id}`)\n"
                f"Username: @{member.username if member.username else 'N/A'}\n"
                f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}"
            )
            await log_to_channel(log_message, parse_mode=enums.ParseMode.HTML)
            logger.info(f"New member {member.id} joined group {chat.id}.")

            try:
                user_profile = await client.get_chat(member.id)
                bio = user_profile.bio or ""
                # CHECKED: Check if biolink deletion is enabled for the group
                settings = get_group_settings(chat.id)
                if settings.get("delete_biolink", True) and URL_PATTERN.search(bio):
                    await message.delete()

                    mode, limit, penalty = get_config_sync(chat.id)
                    full_name = f"{member.first_name}{(' ' + member.last_name) if member.last_name else ''}"
                    mention = f"<a href='tg://user?id={member.id}'>{full_name}</a>"

                    if mode == "warn":
                        count = increment_warning_sync(chat.id, member.id)

                        warning_text = (
                            "🚨 <b>Bio-Link Detected</b>\n\n"
                            f"- <b>User:</b> {mention}\n"
                            f"- <b>Reason:</b> A link was found in your bio.\n"
                            f"- <b>Warning:</b> {count}/{limit}\n\n"
                            "Please remove the link from your bio to avoid being restricted."
                        )
                        keyboard = InlineKeyboardMarkup([
                            [InlineKeyboardButton("❌ Cancel Warning", callback_data=f"cancel_warn_{member.id}"),
                             InlineKeyboardButton("✅ Whitelist", callback_data=f"whitelist_{member.id}")],
                            [InlineKeyboardButton("🗑️ Close", callback_data="close")]
                        ])

                        try:
                            sent = await message.reply_text(warning_text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)
                        except Exception as e:
                            logger.error(f"Error sending bio-link warning: {e}")
                            return

                        if count >= limit:
                            try:
                                if penalty == "mute":
                                    await client.restrict_chat_member(chat.id, member.id, ChatPermissions())
                                    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Unmute ✅", callback_data=f"unmute_{member.id}_{chat.id}"), InlineKeyboardButton("🗑️ Close", callback_data="close")]])
                                    await sent.edit_text(f"<b>{full_name} को 🔇 म्यूट कर दिया गया है (बायो में लिंक के लिए)。</b>", reply_markup=kb, parse_mode=enums.ParseMode.HTML)
                                else:
                                    await client.ban_chat_member(chat.id, member.id)
                                    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Unban ✅", callback_data=f"unban_{member.id}_{chat.id}"), InlineKeyboardButton("🗑️ Close", callback_data="close")]])
                                    await sent.edit_text(f"<b>{full_name} को 🔨 बैन कर दिया गया है (बायो में लिंक के लिए)。</b>", reply_markup=kb, parse_mode=enums.ParseMode.HTML)
                            except errors.ChatAdminRequired:
                                await sent.edit_text(f"<b>I don't have permission to {penalty} users.</b>", parse_mode=enums.ParseMode.HTML)

                    else:
                        try:
                            if penalty == "mute":
                                await client.restrict_chat_member(chat.id, member.id, ChatPermissions())
                                kb = InlineKeyboardMarkup([[InlineKeyboardButton("Unmute", callback_data=f"unmute_{member.id}_{chat.id}"), InlineKeyboardButton("🗑️ Close", callback_data="close")]])
                                await message.reply_text(f"<b>{full_name} को 🔇 म्यूट कर दिया गया है (बायो में लिंक के लिए)。</b>", reply_markup=kb, parse_mode=enums.ParseMode.HTML)
                            else:
                                await client.ban_chat_member(chat.id, member.id)
                                kb = InlineKeyboardMarkup([[InlineKeyboardButton("Unban", callback_data=f"unban_{member.id}_{chat.id}"), InlineKeyboardButton("🗑️ Close", callback_data="close")]])
                                await message.reply_text(f"<b>{full_name} को 🔨 बैन कर दिया गया है (बायो में लिंक के लिए)。</b>", reply_markup=kb, parse_mode=enums.ParseMode.HTML)
                        except errors.ChatAdminRequired:
                            return await message.reply_text(f"<b>I don't have permission to {penalty} users.</b>", parse_mode=enums.ParseMode.HTML)


            except Exception as e:
                logger.error(f"Error checking bio for new member {member.id}: {e}")

# CHANGED: left_chat_member handler with improved logging
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
            f"Removed by: {message.from_user.mention} (`{message.from_user.id}`)\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}"
        )
        await log_to_channel(log_message, parse_mode=enums.ParseMode.HTML)
        logger.info(f"Bot was removed from group: {chat.title} ({chat.id}) by {message.from_user.id}.")
    else:
        # A user left the group, log this event
        log_message = (
            f"<b>➡️ Member Left:</b>\n"
            f"Group: <code>{chat.title}</code>\n"
            f"Group ID: <code>{chat.id}</code>\n"
            f"User: {left_member.mention} (`{left_member.id}`)\n"
            f"Username: @{left_member.username if left_member.username else 'N/A'}\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}"
        )
        await log_to_channel(log_message, parse_mode=enums.ParseMode.HTML)
        logger.info(f"Member {left_member.id} left group {chat.id}.")

# --- Tagging Commands ---
@client.on_message(filters.command("tagall") & filters.group)
async def tag_all(client: Client, message: Message) -> None:
    is_sender_admin = await is_group_admin(message.chat.id, message.from_user.id)
    if not is_sender_admin:
        await message.reply_text("Aapke paas is command ko use karne ki permission nahi hai.")
        return

    chat_id = message.chat.id
    if chat_id in ONGOING_TAGGING_TASKS:
        await message.reply_text("टैगिंग पहले से ही चल रही है। इसे रोकने के लिए /tagstop का उपयोग करें।")
        return

    message_text = " ".join(message.command[1:]) if len(message.command) > 1 else ""
    
    try:
        members_to_tag = []
        async for member in client.get_chat_members(chat_id):
            if not member.user.is_bot:
                emoji = random.choice(EMOJIS)
                members_to_tag.append(member.user.mention(emoji))

        if not members_to_tag:
            await message.reply_text("कोई भी सदस्य नहीं मिला जिसे टैग किया जा सके।", parse_mode=enums.ParseMode.HTML)
            return

        chunk_size = 10
        tag_messages_to_delete = []

        async def tag_task():
            nonlocal tag_messages_to_delete
            try:
                for i in range(0, len(members_to_tag), chunk_size):
                    if chat_id not in ONGOING_TAGGING_TASKS:
                        return
                    
                    chunk = members_to_tag[i:i + chunk_size]
                    final_message = " ".join(chunk)
                    
                    if message_text:
                        final_message += f"\n\n{message_text}"

                    sent_message = await message.reply_text(
                        final_message,
                        parse_mode=enums.ParseMode.HTML,
                        disable_web_page_preview=True
                    )
                    tag_messages_to_delete.append(sent_message.id)
                    await asyncio.sleep(4)

                ONGOING_TAGGING_TASKS.pop(chat_id)
                bot_info = await client.get_me()
                bot_username = bot_info.username
                add_to_group_url = f"https://t.me/{bot_username}?startgroup=true"

                final_message_text = "सभी users को सफलतापूर्वक tag कर दिया गया है!"
                keyboard = [
                    [InlineKeyboardButton("➕ मुझे ग्रुप में जोड़ें", url=add_to_group_url)],
                    [InlineKeyboardButton("📢 अपडेट चैनल", url="https://t.me/asbhai_bsr")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await message.reply_text(
                    final_message_text,
                    reply_markup=reply_markup,
                    parse_mode=enums.ParseMode.HTML
                )

            except asyncio.CancelledError:
                logger.info(f"Tagging task for chat {chat_id} was cancelled.")
            except FloodWait as e:
                logger.warning(f"FloodWait error in /tagall. Sleeping for {e.value} seconds.")
                await asyncio.sleep(e.value)
            except Exception as e:
                logger.error(f"Error during tagging task: {e}")
            finally:
                if chat_id in ONGOING_TAGGING_TASKS:
                    ONGOING_TAGGING_TASKS.pop(chat_id)
        
        task = asyncio.create_task(tag_task())
        ONGOING_TAGGING_TASKS[chat_id] = task

        if chat_id not in TAG_MESSAGES:
            TAG_MESSAGES[chat_id] = []
        TAG_MESSAGES[chat_id] = tag_messages_to_delete

    except errors.MessageTooLong:
        await message.reply_text("टैग करते समय error हुई: मैसेज बहुत लंबा है। यह गलती नहीं है, बल्कि टेलीग्राम की एक सीमा है।")
        if chat_id in ONGOING_TAGGING_TASKS:
            ONGOING_TAGGING_TASKS.pop(chat_id)
    except Exception as e:
        logger.error(f"Error in /tagall command: {e}")
        await message.reply_text(f"टैग करते समय error हुई: {e}")
        if chat_id in ONGOING_TAGGING_TASKS:
            ONGOING_TAGGING_TASKS.pop(chat_id)

@client.on_message(filters.command("onlinetag") & filters.group)
async def online_tag(client: Client, message: Message) -> None:
    is_sender_admin = await is_group_admin(message.chat.id, message.from_user.id)
    if not is_sender_admin:
        await message.reply_text("Aapke paas is command ko use karne ki permission nahi hai.")
        return

    chat_id = message.chat.id
    if chat_id in ONGOING_TAGGING_TASKS:
        await message.reply_text("टैगिंग पहले से ही चल रही है। इसे रोकने के लिए /tagstop का उपयोग करें।")
        return

    message_text = " ".join(message.command[1:]) if len(message.command) > 1 else ""

    try:
        online_members_to_tag = []
        async for member in client.get_chat_members(chat_id):
            if not member.user.is_bot and member.user.status in [enums.UserStatus.ONLINE, enums.UserStatus.RECENTLY]:
                emoji = random.choice(EMOJIS)
                online_members_to_tag.append(member.user.mention(emoji))

        if not online_members_to_tag:
            await message.reply_text("Pichle kuch samay se koi bhi sadasya online nahi hai.", parse_mode=enums.ParseMode.HTML)
            return

        chunk_size = 10
        tag_messages_to_delete = []

        async def online_tag_task():
            nonlocal tag_messages_to_delete
            try:
                for i in range(0, len(online_members_to_tag), chunk_size):
                    if chat_id not in ONGOING_TAGGING_TASKS:
                        return

                    chunk = online_members_to_tag[i:i + chunk_size]
                    final_message = " ".join(chunk)
                    
                    if message_text:
                        final_message += f"\n\n{message_text}"

                    sent_message = await message.reply_text(
                        final_message,
                        parse_mode=enums.ParseMode.HTML,
                        disable_web_page_preview=True
                    )
                    tag_messages_to_delete.append(sent_message.id)
                    await asyncio.sleep(4)

                ONGOING_TAGGING_TASKS.pop(chat_id)
                bot_info = await client.get_me()
                bot_username = bot_info.username
                add_to_group_url = f"https://t.me/{bot_username}?startgroup=true"
                
                final_message_text = "सभी users को सफलतापूर्वक tag कर दिया गया है!"
                keyboard = [
                    [InlineKeyboardButton("➕ मुझे ग्रुप में जोड़ें", url=add_to_group_url)],
                    [InlineKeyboardButton("📢 अपडेट चैनल", url="https://t.me/asbhai_bsr")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await message.reply_text(
                    final_message_text,
                    reply_markup=reply_markup,
                    parse_mode=enums.ParseMode.HTML
                )
            
            except asyncio.CancelledError:
                logger.info(f"Online tagging task for chat {chat_id} was cancelled.")
            except FloodWait as e:
                logger.warning(f"FloodWait error in /onlinetag. Sleeping for {e.value} seconds.")
                await asyncio.sleep(e.value)
            except Exception as e:
                logger.error(f"Error during online tagging task: {e}")
            finally:
                if chat_id in ONGOING_TAGGING_TASKS:
                    ONGOING_TAGGING_TASKS.pop(chat_id)
        
        task = asyncio.create_task(online_tag_task())
        ONGOING_TAGGING_TASKS[chat_id] = task

        if chat_id not in TAG_MESSAGES:
            TAG_MESSAGES[chat_id] = []
        TAG_MESSAGES[chat_id] = tag_messages_to_delete

    except errors.MessageTooLong:
        await message.reply_text("टैग करते समय error हुई: मैसेज बहुत लंबा है। यह गलती नहीं है, बल्कि टेलीग्राम की एक सीमा है।")
        if chat_id in ONGOING_TAGGING_TASKS:
            ONGOING_TAGGING_TASKS.pop(chat_id)
    except Exception as e:
        logger.error(f"Error in /onlinetag command: {e}")
        await message.reply_text(f"टैग करते समय error हुई: {e}")
        if chat_id in ONGOING_TAGGING_TASKS:
            ONGOING_TAGGING_TASKS.pop(chat_id)


@client.on_message(filters.command("admin") & filters.group)
async def tag_admins(client: Client, message: Message) -> None:
    is_sender_admin = await is_group_admin(message.chat.id, message.from_user.id)
    if not is_sender_admin:
        await message.reply_text("Aapke paas is command ko use karne ki permission nahi hai.")
        return

    message_text = " ".join(message.command[1:]) if len(message.command) > 1 else "Admins, attention please!"
    chat_id = message.chat.id

    try:
        admins = [admin async for admin in client.get_chat_members(chat_id, filter=enums.ChatMembersFilter.ADMINISTRATORS)]
        tagged_admins = []
        for admin in admins:
            if not admin.user.is_bot:
                full_name = f"{admin.user.first_name}{(' ' + admin.user.last_name) if admin.user.last_name else ''}"
                tagged_admins.append(f"👑 <a href='tg://user?id={admin.user.id}'>{full_name}</a>")

        if not tagged_admins:
            await message.reply_text("Is group mein koi admins nahi hain jinhe tag kiya ja sake.", parse_mode=enums.ParseMode.HTML)
            return

        tag_message_text = " ".join(tagged_admins)

        if chat_id not in TAG_MESSAGES:
            TAG_MESSAGES[chat_id] = []

        sent_message = await message.reply_text(
            f"{tag_message_text}\n\n<b>Message:</b> {message_text}",
            parse_mode=enums.ParseMode.HTML,
            disable_web_page_preview=True
        )
        TAG_MESSAGES[chat_id].append(sent_message.id)

    except Exception as e:
        logger.error(f"Error in /admin command: {e}")
        await message.reply_text(f"Admins ko tag karte samay error hui: {e}")


@client.on_message(filters.command("tagstop") & filters.group)
async def tag_stop(client: Client, message: Message) -> None:
    chat_id = message.chat.id
    is_sender_admin = await is_group_admin(chat_id, message.from_user.id)
    if not is_sender_admin:
        await message.reply_text("Aapke paas is command ko use karne ki permission nahi hai.")
        return

    if chat_id in ONGOING_TAGGING_TASKS:
        try:
            task = ONGOING_TAGGING_TASKS.pop(chat_id)
            task.cancel()
            await message.reply_text("टैगिंग प्रक्रिया बंद कर दी गई है।")
            logger.info(f"Admin {message.from_user.id} stopped ongoing tagging in chat {chat_id}.")
        except Exception as e:
            logger.error(f"Error canceling tagging task: {e}")
            await message.reply_text(f"टैगिंग प्रक्रिया बंद karte samay error hui: {e}")
        return

    if chat_id not in TAG_MESSAGES or not TAG_MESSAGES[chat_id]:
        await message.reply_text("कोई भी टैगिंग मैसेज नहीं mila jise roka ja sake।")
        return

    try:
        await client.delete_messages(chat_id, TAG_MESSAGES[chat_id])
        TAG_MESSAGES.pop(chat_id)

        bot_info = await client.get_me()
        bot_username = bot_info.username
        add_to_group_url = f"https://t.me/{bot_username}?startgroup=true"

        final_message_text = "पिछली टैगिंग के सारे मैसेज डिलीट कर दिए गए हैं।"

        keyboard = [
            [InlineKeyboardButton("➕ मुझे ग्रुप में जोड़ें", url=add_to_group_url)],
            [InlineKeyboardButton("📢 अपडेट चैनल", url="https://t.me/asbhai_bsr")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await message.reply_text(
            final_message_text,
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML
        )
        logger.info(f"Admin {message.from_user.id} cleaned up old tagging messages in chat {chat_id}.")

    except Exception as e:
        logger.error(f"Error in /tagstop command: {e}")
        await message.reply_text(f"टैगिंग रोकते समय एक error हुई: {e}")


@client.on_message(filters.command("checkperms") & filters.group)
async def check_permissions(client: Client, message: Message):
    chat = message.chat

    if not await is_group_admin(chat.id, message.from_user.id):
        await message.reply_text("आप ग्रुप एडमिन नहीं हैं, इसलिए आप यह कमांड का उपयोग नहीं कर सकते।")
        return

    try:
        bot_member = await client.get_chat_member(chat.id, client.me.id)
        perms = bot_member.privileges

        message_text = (
            f"<b>{chat.title}</b> में बॉट की अनुमतियाँ (Permissions):\n\n"
            f"<b>✅ मैसेज हटा सकता है:</b> {perms.can_delete_messages}\n"
            f"<b>✅ सदस्यों को प्रतिबंधित कर सकता है:</b> {perms.can_restrict_members}\n"
            f"<b>✅ मैसेज पिन कर सकता है:</b> {perms.can_pin_messages}\n"
            f"<b>✅ मैसेज भेज सकता है:</b> {perms.can_post_messages}\n"
        )

        await message.reply_text(message_text, parse_mode=enums.ParseMode.HTML)
        logger.info(f"Admin {message.from_user.id} requested permissions check in chat {chat.id}.")
    except Exception as e:
        logger.error(f"अनुमतियाँ जाँचते समय एक error हुई: {e}")
        await message.reply_text(f"अनुमतियाँ जाँचते समय एक error हुई: {e}")


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

    if settings.get("delete_biolink", True) and await check_and_delete_biolink(client, message):
        return

    if settings.get("delete_abuse", True) and profanity_filter is not None and profanity_filter.contains_profanity(message_text):
        await handle_incident(client, chat.id, user, "गाली-गलौज (Profanity) 😡", message, "abuse")
        return

    # Assuming link in message is also tied to biolink setting
    if settings.get("delete_biolink", True) and (URL_PATTERN.search(message_text) or USERNAME_PATTERN.search(message_text)):
        await handle_incident(client, chat.id, user, "मैसेज में लिंक या यूज़रनेम (Link or Username in Message) 🔗", message, "link_or_username")
        return


async def check_and_delete_biolink(client: Client, message: Message):
    user = message.from_user
    user_id = user.id
    chat_id = message.chat.id

    if not user:
        return False
    
    is_sender_admin = await is_group_admin(chat_id, user_id)
    is_biolink_exception = is_whitelisted_sync(chat_id, user_id)

    if is_sender_admin or is_biolink_exception:
        return False
    
    try:
        user_profile = await client.get_chat(user_id)
        user_bio = user_profile.bio or ""
        
        if URL_PATTERN.search(user_bio):
            try:
                await message.delete()

                mode, limit, penalty = get_config_sync(chat_id)
                full_name = f"{user.first_name}{(' ' + user.last_name) if user.last_name else ''}"
                mention = f"<a href='tg://user?id={user.id}'>{full_name}</a>"

                if mode == "warn":
                    count = increment_warning_sync(chat_id, user.id)

                    warning_text = (
                        "🚨 <b>Bio-Link Detected</b>\n\n"
                        f"- <b>User:</b> {mention}\n"
                        f"- <b>Reason:</b> A link was found in your bio.\n"
                        f"- <b>Warning:</b> {count}/{limit}\n\n"
                        "Please remove the link from your bio to avoid being restricted."
                    )
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton("❌ Cancel Warning", callback_data=f"cancel_warn_{user.id}"),
                         InlineKeyboardButton("✅ Whitelist", callback_data=f"whitelist_{user.id}")],
                        [InlineKeyboardButton("🗑️ Close", callback_data="close")]
                    ])

                    try:
                        sent = await message.reply_text(warning_text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)
                        
                    except Exception as e:
                        logger.error(f"Error sending bio-link warning: {e}")
                        return True

                    if count >= limit:
                        try:
                            if penalty == "mute":
                                await client.restrict_chat_member(chat_id, user.id, ChatPermissions())
                                kb = InlineKeyboardMarkup([[InlineKeyboardButton("Unmute ✅", callback_data=f"unmute_{user.id}_{chat_id}"), InlineKeyboardButton("🗑️ Close", callback_data="close")]])
                                await sent.edit_text(f"<b>{full_name} को 🔇 म्यूट कर दिया गया है (बायो में लिंक के लिए)。</b>", reply_markup=kb, parse_mode=enums.ParseMode.HTML)
                            else:
                                await client.ban_chat_member(chat_id, user.id)
                                kb = InlineKeyboardMarkup([[InlineKeyboardButton("Unban ✅", callback_data=f"unban_{user.id}_{chat_id}"), InlineKeyboardButton("🗑️ Close", callback_data="close")]])
                                await sent.edit_text(f"<b>{full_name} को 🔨 बैन कर दिया गया है (बायो में लिंक के लिए)。</b>", reply_markup=kb, parse_mode=enums.ParseMode.HTML)
                        except errors.ChatAdminRequired:
                            await sent.edit_text(f"<b>I don't have permission to {penalty} users.</b>", parse_mode=enums.ParseMode.HTML)
                else:
                    try:
                        if penalty == "mute":
                            await client.restrict_chat_member(chat_id, user.id, ChatPermissions())
                            kb = InlineKeyboardMarkup([[InlineKeyboardButton("Unmute", callback_data=f"unmute_{user.id}_{chat_id}"), InlineKeyboardButton("🗑️ Close", callback_data="close")]])
                            await message.reply_text(f"<b>{full_name} को 🔇 म्यूट कर दिया गया है (बायो में लिंक के लिए)。</b>", reply_markup=kb, parse_mode=enums.ParseMode.HTML)
                        else:
                            await client.ban_chat_member(chat_id, user.id)
                            kb = InlineKeyboardMarkup([[InlineKeyboardButton("Unban", callback_data=f"unban_{user.id}_{chat_id}"), InlineKeyboardButton("🗑️ Close", callback_data="close")]])
                            await message.reply_text(f"<b>{full_name} को 🔨 बैन कर दिया गया है (बायो में लिंक के लिए)。</b>", reply_markup=kb, parse_mode=enums.ParseMode.HTML)
                    except errors.ChatAdminRequired:
                        return await message.reply_text(f"<b>I don't have permission to {penalty} users.</b>", parse_mode=enums.ParseMode.HTML)
                return True
            except Exception:
                pass
                    
        return False

    except Exception:
        pass


# --- Handler for Edited Messages ---
@client.on_edited_message(filters.text & filters.group & ~filters.via_bot)
async def handle_edited_messages(client: Client, edited_message: Message) -> None:
    if not edited_message or not edited_message.text:
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
        await handle_incident(client, chat.id, user, "Edited message deleted", edited_message, "edited_message_deleted")

# --- Callback Query Handlers ---
@client.on_callback_query()
async def callback_handler(client: Client, query: CallbackQuery) -> None:
    data = query.data
    user_id = query.from_user.id
    chat_id = query.message.chat.id

    if query.message.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        if data != "close" and not data.startswith(('help_menu', 'other_bots', 'donate_info', 'back_to_main_menu', 'show_settings_menu', 'toggle_', 'back_to_settings')):
            is_current_group_admin = await is_group_admin(chat_id, user_id)
            if not is_current_group_admin:
                return await query.answer("❌ Aapke paas is action ko karne ki permission nahi hai. Aap group admin nahi hain.", show_alert=True)

        if data == "close":
            # Modified to allow closing by any user in private chat but only admins in groups
            if query.message.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
                is_current_group_admin = await is_group_admin(chat_id, user_id)
                if not is_current_group_admin:
                    return await query.answer("❌ Aapke paas is action ko karne ki permission nahi hai. Aap group admin nahi hain.", show_alert=True)
            
            try:
                await query.message.delete()
            except MessageNotModified:
                pass
            return
    else:
        if data == "close":
            try:
                await query.message.delete()
            except MessageNotModified:
                pass
            return

    await query.answer()

    # ADDED: New settings menu callbacks
    if data == "show_settings_menu":
        await show_settings_menu(client, query)
        return

    if data.startswith("toggle_"):
        setting_key = data.split('_', 1)[1]
        settings = get_group_settings(chat_id)
        current_status = settings.get(setting_key, True)
        new_status = not current_status
        update_group_setting(chat_id, setting_key, new_status)
        await show_settings_menu(client, query)
        return

    # --- BioLink Bot Callbacks ---
    if data == "warn_limit":
        _, selected_limit, _ = get_config_sync(chat_id)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"3 ✅" if selected_limit == 3 else "3", callback_data="setwarn_3"),
             InlineKeyboardButton(f"4 ✅" if selected_limit == 4 else "4", callback_data="setwarn_4"),
             InlineKeyboardButton(f"5 ✅" if selected_limit == 5 else "5", callback_data="setwarn_5")],
            [InlineKeyboardButton("Back", callback_data="back"), InlineKeyboardButton("Close", callback_data="close")]
        ])
        try:
            await query.message.edit_text("<b>Select number of warns before penalty:</b>", reply_markup=kb, parse_mode=enums.ParseMode.HTML)
        except MessageNotModified:
            pass
        return

    if data in ["mute", "ban"]:
        update_config_sync(chat_id, penalty=data)
        mode, limit, penalty = get_config_sync(chat_id)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Warn Limit", callback_data="warn_limit")],
            [
                InlineKeyboardButton("Mute ✅" if penalty == "mute" else "Mute", callback_data="mute"),
                InlineKeyboardButton("Ban ✅" if penalty == "ban" else "Ban", callback_data="ban")
            ],
            [InlineKeyboardButton("Close", callback_data="close")]
        ])
        try:
            await query.message.edit_text("<b>Punishment selected:</b>", reply_markup=kb, parse_mode=enums.ParseMode.HTML)
        except MessageNotModified:
            pass
        return

    if data.startswith("setwarn_"):
        count = int(data.split("_")[1])
        update_config_sync(chat_id, limit=count)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"3 ✅" if count == 3 else "3", callback_data="setwarn_3"),
             InlineKeyboardButton(f"4 ✅" if count == 4 else "4", callback_data="setwarn_4"),
             InlineKeyboardButton(f"5 ✅" if count == 5 else "5", callback_data="setwarn_5")],
            [InlineKeyboardButton("Back", callback_data="back"), InlineKeyboardButton("Close", callback_data="close")]
        ])
        try:
            await query.message.edit_text(f"<b>Warning limit set to {count}</b>", reply_markup=kb, parse_mode=enums.ParseMode.HTML)
        except MessageNotModified:
            pass
        return

    if data.startswith("unmute_"):
        parts = data.split('_')
        target_id = int(parts[1])
        group_chat_id = int(parts[2])
        try:
            await client.restrict_chat_member(group_chat_id, target_id, ChatPermissions(can_send_messages=True))
            reset_warnings_sync(group_chat_id, target_id)
            user_obj = await client.get_chat_member(group_chat_id, target_id)
            user_mention = f"<a href='tg://user?id={user_obj.user.id}'>{user_obj.user.first_name}</a>"
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

    if data.startswith("unban_"):
        parts = data.split('_')
        target_id = int(parts[1])
        group_chat_id = int(parts[2])
        try:
            await client.unban_chat_member(group_chat_id, target_id)
            reset_warnings_sync(group_chat_id, target_id)
            try:
                user_obj = await client.get_chat_member(group_chat_id, target_id)
                user_mention = f"<a href='tg://user?id={user_obj.user.id}'>{user_obj.user.first_name}</a>"
            except Exception:
                user_mention = f"User (`{target_id}`)"
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("Whitelist ✅", callback_data=f"whitelist_{target_id}_{group_chat_id}"), InlineKeyboardButton("🗑️ Close", callback_data="close")]])
            try:
                await query.message.edit_text(f"<b>✅ {user_mention} unbanned!</b>", reply_markup=kb, parse_mode=enums.ParseMode.HTML)
            except MessageNotModified:
                pass
        except errors.ChatAdminRequired:
            try:
                await query.message.edit_text("<b>I don't have permission to unban users.</b>", parse_mode=enums.ParseMode.HTML)
            except MessageNotModified:
                pass
        return

    if data.startswith("cancel_warn_"):
        target_id = int(data.split("_")[-1])
        reset_warnings_sync(chat_id, target_id)
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
        reset_warnings_sync(chat_id, target_id)
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

    # --- General Bot Callbacks ---
    elif data == "help_menu":
        help_text = (
            "<b>Bot Help Menu:</b>\n\n"
            "<b>• Gaali detection:</b> Automatic message deletion for profanity.\n"
            "<b>• Edited Message Deletion:</b> Deletes any edited message from non-admins to prevent rule-breaking edits.\n"
            "<b>• Bio-link protection:</b> Warns/mutes users with links in their bio.\n"
            "<b>• Admin Actions:</b> Mute, ban, kick users directly from the group notification.\n"
            "<b>• Incident Logging:</b> All violations are logged in a dedicated case channel.\n\n"
            "<b>Commands:</b>\n"
            "• <code>/start</code>: Bot ko start karein (private aur group mein).\n"
            "• <code>/settings</code>: Bot ki settings kholen (Group Admins only).\n" # UPDATED: Help menu with new command
            "• <code>/config</code>: Bio-link protection settings (warn-limit, penalty).\n"
            "• <code>/free</code>, <code>/unfree</code>, <code>/freelist</code>: Whitelist management.\n"
            "• <code>/stats</code>: Bot usage stats dekhein (sirf bot admins ke liye).\n"
            "• <code>/broadcast</code>: Sabhi groups mein message bhejein (sirf bot admins ke liye).\n"
            f"• <code>/addabuse &lt;shabd&gt;</code>: Custom gaali wala shabd filter mein add karein (sirf bot admins ke liye).\n"
            f"• <code>/checkperms</code>: Group mein bot ki permissions jaanchein (sirf group admins ke liye).\n"
            "• <code>/tagall &lt;message&gt;</code>: Sabhi members ko tag karein.\n"
            "• <code>/onlinetag &lt;message&gt;</code>: Online members ko tag karein.\n"
            "• <code>/admin &lt;message&gt;</code>: Sirf group admins ko tag karein.\n"
            "• <code>/tagstop</code>: Saare tagging messages ko delete kar dein."
        )
        keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="back_to_main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.message.edit_text(help_text, reply_markup=reply_markup, parse_mode=enums.ParseMode.HTML)
        except MessageNotModified:
            pass

    elif data == "other_bots":
        other_bots_text = (
            "<b>Mere kuch aur bots:</b>\n\n"
            "• <b>Movies & Webseries:</b> <a href='https://t.me/asflter_bot'>@asflter_bot</a>\n"
            "  <i>Ye hai sabhi movies, webseries, anime, Korean drama, aur sabhi TV show sabhi languages mein yahan milte hain.</i>\n\n"
            "• <b>Chat Bot:</b> <a href='https://t.me/askiangelbot'>@askiangelbot</a>\n"
            "  <i>Ye bot group par chat karti hai aur isme acche acche group manage karne ke liye commands hain.</i>\n"
        )
        keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="back_to_main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.message.edit_text(other_bots_text, reply_markup=reply_markup, parse_mode=enums.ParseMode.HTML)
        except MessageNotModified:
            pass

    elif data == "donate_info":
        donate_text = (
            "<b>💖 Bot ko support karein!</b>\n\n"
            "Agar aapko ye bot pasand aaya hai to aap humein kuch paisa de sakte hain "
            "jisse hum is bot ko aage tak chalate rahein.\n\n"
            "<b>Donation Methods:</b>\n"
            "• UPI: <code>arsadsaifi8272@ibl</code>\n\n"
            "Aapka har sahyog value karta hai! Dhanyawad!"
        )
        keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="back_to_main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.message.edit_text(donate_text, reply_markup=reply_markup, parse_mode=enums.ParseMode.HTML)
        except MessageNotModified:
            pass

    elif data == "back_to_main_menu":
        bot_info = await client.get_me()
        bot_name = bot_info.first_name
        bot_username = bot_info.username
        add_to_group_url = f"https://t.me/{bot_username}?startgroup=true"

        welcome_message = (
            f"👋 <b>Namaste {query.from_user.mention}!</b>\n\n"
            f"Mai <b>{bot_name}</b> hun, aapka group moderator bot. "
            f"Mai aapke groups ko saaf suthra rakhne mein madad karta hun, "
            f"gaaliyon wale messages ko delete karta hun aur zaroorat padne par warning bhi deta hun.\n\n"
            f"<b>Mere features:</b>\n"
            f"• Gaali detection aur deletion\n"
            f"• Bio-link protection\n"
            f"• User warnings aur actions (Mute, Ban, Kick)\n"
            f"• Whitelist management\n"
            f"• Incident logging\n\n"
            f"Agar aapko koi madad chahiye, toh niche diye gaye buttons ka upyog karein."
        )
        
        # New keyboard to handle the back button functionality
        keyboard = [
            [InlineKeyboardButton("➕ Add Me To Your Group", url=add_to_group_url)],
            [InlineKeyboardButton("❓ Help", callback_data="help_menu"), InlineKeyboardButton("🤖 Other Bots", callback_data="other_bots")],
            [InlineKeyboardButton("📢 Update Channel", url="https://t.me/asbhai_bsr"), InlineKeyboardButton("💖 Donate", callback_data="donate_info")],
            [InlineKeyboardButton("📈 Promotion", url="https://t.me/asprmotion")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.message.edit_text(welcome_message, reply_markup=reply_markup, parse_mode=enums.ParseMode.HTML)
        except MessageNotModified:
            pass

    elif data.startswith("admin_actions_menu_"):
        parts = data.split('_')
        target_user_id = int(parts[3])
        group_chat_id = int(parts[4])

        try:
            target_user = await client.get_chat_member(group_chat_id, target_user_id)
            target_user_mention = f"<a href='tg://user?id={target_user.user.id}'>{target_user.user.first_name}</a>"
        except Exception:
            target_user_mention = f"User (`{target_user_id}`)"

        actions_text = (
            f"<b>{target_user_mention}</b> के लिए एक्शन चुनें:\n"
            f"ग्रुप: <b>{query.message.chat.title}</b>"
        )
        actions_keyboard = [
            [InlineKeyboardButton("Mute (30 min)", callback_data=f"mute_{target_user_id}_{group_chat_id}_30m")],
            [InlineKeyboardButton("Mute (1 hr)", callback_data=f"mute_{target_user_id}_{group_chat_id}_1h")],
            [InlineKeyboardButton("Mute (24 hr)", callback_data=f"mute_{target_user_id}_{group_chat_id}_24h")],
            [InlineKeyboardButton("Ban", callback_data=f"ban_{target_user_id}_{group_chat_id}")],
            [InlineKeyboardButton("Kick", callback_data=f"kick_{target_user_id}_{group_chat_id}")],
            [InlineKeyboardButton("Warn", callback_data=f"warn_{target_user_id}_{group_chat_id}")],
            [InlineKeyboardButton("⬅️ Back", callback_data=f"back_to_notification_{target_user_id}_{group_chat_id}")],
        ]

        reply_markup = InlineKeyboardMarkup(actions_keyboard)
        try:
            await query.message.edit_text(actions_text, reply_markup=reply_markup, parse_mode=enums.ParseMode.HTML)
        except MessageNotModified:
            pass

    elif data.startswith("mute_"):
        parts = data.split('_')
        target_user_id = int(parts[1])
        group_chat_id = int(parts[2])
        duration_str = parts[3]

        try:
            if duration_str.endswith('m'):
                duration_minutes = int(duration_str[:-1])
                until_date = datetime.now() + timedelta(minutes=duration_minutes)
            elif duration_str.endswith('h'):
                duration_hours = int(duration_str[:-1])
                until_date = datetime.now() + timedelta(hours=duration_hours)
            else:
                try:
                    await query.edit_message_text("Invalid mute duration.")
                except MessageNotModified:
                    pass
                return

            permissions = ChatPermissions(can_send_messages=False)
            await client.restrict_chat_member(
                chat_id=group_chat_id,
                user_id=target_user_id,
                permissions=permissions,
                until_date=until_date
            )
            try:
                target_user = await client.get_chat_member(group_chat_id, target_user_id)
                mention = f"<a href='tg://user?id={target_user.user.id}'>{target_user.user.first_name}</a>"
                await query.edit_message_text(f"✅ {mention} को {duration_str} के लिए म्यूट कर दिया गया है।", parse_mode=enums.ParseMode.HTML)
                logger.info(f"Admin {user_id} muted user {target_user_id} in chat {group_chat_id} for {duration_str}.")
            except Exception:
                await query.edit_message_text(f"✅ User (`{target_user_id}`) को {duration_str} के लिए म्यूट कर दिया गया है।", parse_mode=enums.ParseMode.HTML)

        except Exception as e:
            try:
                await query.edit_message_text(f"Mute karte samay error hui: {e}")
            except MessageNotModified:
                pass
            logger.error(f"Error muting user {target_user_id} in {group_chat_id}: {e}")

    elif data.startswith("ban_"):
        parts = data.split('_')
        target_user_id = int(parts[1])
        group_chat_id = int(parts[2])
        try:
            await client.ban_chat_member(chat_id=group_chat_id, user_id=target_user_id)
            try:
                target_user = await client.get_chat_member(group_chat_id, target_user_id)
                mention = f"<a href='tg://user?id={target_user.user.id}'>{target_user.user.first_name}</a>"
                await query.edit_message_text(f"✅ {mention} को group से ban कर दिया गया है।", parse_mode=enums.ParseMode.HTML)
                logger.info(f"Admin {user_id} banned user {target_user_id} from chat {group_chat_id}.")
            except Exception:
                await query.edit_message_text(f"✅ User (`{target_user_id}`) को group से ban kar diya gaya hai।", parse_mode=enums.ParseMode.HTML)
        except Exception as e:
            try:
                await query.message.edit_text(f"Ban karte samay error hui: {e}")
            except MessageNotModified:
                pass
            logger.error(f"Error banning user {target_user_id} from {group_chat_id}: {e}")

    elif data.startswith("kick_"):
        parts = data.split('_')
        target_user_id = int(parts[1])
        group_chat_id = int(parts[2])
        try:
            await client.unban_chat_member(chat_id=group_chat_id, user_id=target_user_id, only_if_banned=False)
            try:
                target_user = await client.get_chat_member(group_chat_id, target_user_id)
                mention = f"<a href='tg://user?id={target_user.user.id}'>{target_user.user.first_name}</a>"
                await query.edit_message_text(f"✅ {mention} को group से निकाल दिया गया है।", parse_mode=enums.ParseMode.HTML)
                logger.info(f"Admin {user_id} kicked user {target_user_id} from chat {group_chat_id}.")
            except Exception:
                await query.edit_message_text(f"✅ User (`{target_user_id}`) को group से निकाल दिया गया है।", parse_mode=enums.ParseMode.HTML)
        except Exception as e:
            try:
                await query.message.edit_text(f"Kick karte samay error hui: {e}")
            except MessageNotModified:
                pass
            logger.error(f"Error kicking user {target_user_id} from {group_chat_id}: {e}")

    elif data.startswith("warn_"):
        parts = data.split('_')
        target_user_id = int(parts[1])
        group_chat_id = int(parts[2])

        if db is None:
            await query.edit_message_text("Database connection available nahi hai. Chetavni nahi de sakte.")
            return

        try:
            try:
                target_user = await client.get_chat_member(group_chat_id, target_user_id)
                mention = f"<a href='tg://user?id={target_user.user.id}'>{target_user.user.first_name}</a>"
            except Exception:
                mention = f"User (`{target_user_id}`)"

            warn_count = increment_warning_sync(group_chat_id, target_user_id)

            warn_message = (
                f"🚨 <b>Chetavni</b> 🚨\n\n"
                f"➡️ {mention}, aapko group ke niyam todne ke liye chetavni di jaati hai. Please group ke rules follow karein.\n\n"
                f"➡️ <b>Yeh aapki {warn_count}vi chetavni hai.</b>"
            )

            await client.send_message(chat_id=group_chat_id, text=warn_message, parse_mode=enums.ParseMode.HTML)

            if warn_count >= 3:
                permissions = ChatPermissions(can_send_messages=False, can_send_media_messages=False, can_send_polls=False, can_send_other_messages=False)
                await client.restrict_chat_member(
                    chat_id=group_chat_id,
                    user_id=target_user_id,
                    permissions=permissions
                )
                permanent_mute_message = (
                    f"❌ <b>Permanent Mute</b> ❌\n\n"
                    f"➡️ {mention}, aapko 3 warnings mil chuki hain. Isliye aapko group mein permanent mute kar diya gaya hai."
                )
                await client.send_message(chat_id=group_chat_id, text=permanent_mute_message, parse_mode=enums.ParseMode.HTML)
                try:
                    await query.message.edit_text(f"✅ {mention} ko {warn_count} chetavniyan milne ke baad permanent mute kar diya gaya hai।", parse_mode=enums.ParseMode.HTML)
                except MessageNotModified:
                    pass
                logger.info(f"User {target_user_id} was permanently muted after 3 warnings in chat {group_chat_id}.")
            else:
                try:
                    await query.message.edit_text(f"✅ {mention} ko chetavni bhej di gai hai. Warnings: {warn_count}/3.", parse_mode=enums.ParseMode.HTML)
                except MessageNotModified:
                    pass
            logger.info(f"Admin {user_id} warned user {target_user_id} in chat {group_chat_id}. Current warnings: {warn_count}.")

        except Exception as e:
            try:
                await query.message.edit_text(f"Chetavni bhejte samay error hui: {e}")
            except MessageNotModified:
                pass
            logger.error(f"Error warning user {target_user_id} in {group_chat_id}: {e}")

    elif data.startswith("back_to_notification_"):
        parts = data.split('_')
        target_user_id = int(parts[3])
        group_chat_id = int(parts[4])

        try:
            user_obj = await client.get_chat_member(group_chat_id, target_user_id)
            mention = f"<a href='tg://user?id={user_obj.user.id}'>{user_obj.user.first_name}</a>"
        except Exception:
            mention = f"User (`{target_user_id}`)"

        notification_message = (
            f"🚨 <b>नियम उल्लंघन</b> 🚨\n\n"
            f"<b>👤 यूज़र:</b> {mention}\n"
            f"<b>📝 कारण:</b> (पिछला उल्लंघन)\n\n"
            f"<b>⏰ समय:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}"
        )

        keyboard = [
            [
                InlineKeyboardButton("🔧 Admin Actions", callback_data=f"admin_actions_menu_{target_user_id}_{group_chat_id}")
            ],
            [
            ]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.message.edit_text(notification_message, reply_markup=reply_markup, parse_mode=enums.ParseMode.HTML)
        except MessageNotModified:
            pass

    # CHANGED: Broadcast logic to send to both users and groups with flood control
    if data == "confirm_broadcast":
        admin_id = query.from_user.id
        message_to_broadcast = BROADCAST_MESSAGE.get(admin_id)

        if not message_to_broadcast:
            await query.message.edit_text("Broadcast message not found. Please try again.")
            return

        try:
            await query.message.edit_text("📢 Broadcast शुरू हो रहा है...")
        except MessageNotModified:
            pass

        if db is None:
            await query.message.reply_text("Database connection उपलब्ध नहीं है, Broadcast नहीं कर सकते।")
            return

        # Get a list of both groups and users from the database
        all_chats = []
        if db.groups is not None:
            try:
                groups = db.groups.find({})
                for group in groups:
                    all_chats.append(group.get("chat_id"))
            except Exception as e:
                logger.error(f"Error fetching groups from DB for broadcast: {e}")

        if db.users is not None:
            try:
                users = db.users.find({})
                for user in users:
                    all_chats.append(user.get("user_id"))
            except Exception as e:
                logger.error(f"Error fetching users from DB for broadcast: {e}")

        success_count = 0
        fail_count = 0
        total_chats = len(all_chats)

        for i, chat_id in enumerate(all_chats):
            try:
                await client.copy_message(
                    chat_id=chat_id,
                    from_chat_id=message_to_broadcast.chat.id,
                    message_id=message_to_broadcast.id
                )
                success_count += 1
            except FloodWait as e:
                logger.warning(f"Broadcast: FloodWait error. Sleeping for {e.value} seconds.")
                await asyncio.sleep(e.value)
                # Retry sending the message after the wait
                try:
                    await client.copy_message(
                        chat_id=chat_id,
                        from_chat_id=message_to_broadcast.chat.id,
                        message_id=message_to_broadcast.id
                    )
                    success_count += 1
                except Exception as e_retry:
                    logger.error(f"Broadcast retry failed for {chat_id}: {e_retry}")
                    fail_count += 1
            except Exception as e:
                logger.error(f"Failed to broadcast to chat {chat_id}: {e}")
                fail_count += 1
            
            # Update progress for every 10 messages
            if (i + 1) % 10 == 0 or (i + 1) == total_chats:
                try:
                    await query.message.edit_text(f"📢 Broadcast चल रहा है...\n\nसफलतापूर्वक भेजा गया: {success_count}/{total_chats}\nविफल: {fail_count}/{total_chats}", parse_mode=enums.ParseMode.HTML)
                except MessageNotModified:
                    pass

        report_text = f"✅ Broadcast पूरा हुआ!\n\nसफलतापूर्वक भेजा गया: {success_count} चैट में\nविफल: {fail_count} चैट में"
        try:
            await query.message.edit_text(report_text, parse_mode=enums.ParseMode.HTML)
        except MessageNotModified:
            pass
        BROADCAST_MESSAGE.pop(admin_id, None)
        logger.info(f"Admin {admin_id} successfully broadcasted message to {success_count} chats.")

    if data == "cancel_broadcast":
        await query.message.edit_text("Broadcast cancelled.")
        user_id = query.from_user.id
        if BROADCAST_MESSAGE.get(user_id):
            BROADCAST_MESSAGE.pop(user_id)


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

    # Run the Flask app in a separate thread
    flask_thread = threading.Thread(target=run_flask_app)
    flask_thread.daemon = True
    flask_thread.start()

    # The client.run() method handles starting the bot and running event loops
    logger.info("Bot is starting...")
    client.run()
    logger.info("Bot stopped")

