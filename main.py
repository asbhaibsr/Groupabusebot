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

# --- Constants
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
        logger.error("MONGO_DB_URI environment variable is not set.")
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
        logger.info("MongoDB connection initialized successfully.")
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

async def log_to_channel(text: str, parse_mode: enums.ParseMode = None) -> None:
    if not LOG_CHANNEL_ID:
        logger.warning("LOG_CHANNEL_ID is not set or invalid")
        return
    
    try:
        await client.send_message(chat_id=LOG_CHANNEL_ID, text=text, parse_mode=parse_mode)
    except Exception as e:
        logger.error(f"Error logging to channel: {e}")

# --- Settings Functions (NEW) ---
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
    if db is None: return
    db.settings.update_one(
        {"chat_id": chat_id},
        {"$set": {setting_key: setting_value}},
        upsert=True
    )

# --- Warning Functions ---
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

def get_abuse_warnings_sync(user_id: int, chat_id: int):
    if db is None: return 0
    warnings_doc = db.warnings.find_one({"user_id": user_id, "chat_id": chat_id})
    return warnings_doc.get("abuse_count", 0) if warnings_doc else 0

def increment_abuse_warning_sync(chat_id, user_id):
    if db is None: return 1
    warnings_doc = db.warnings.find_one_and_update(
        {"chat_id": chat_id, "user_id": user_id},
        {"$inc": {"abuse_count": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER
    )
    return warnings_doc.get("abuse_count", 1)

def reset_abuse_warnings_sync(chat_id, user_id):
    if db is None: return
    db.warnings.update_one(
        {"chat_id": chat_id, "user_id": user_id},
        {"$set": {"abuse_count": 0}}
    )

# --- Whitelist Functions ---
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

# --- Handle Incident ---
async def handle_incident(client: Client, chat_id, user, reason, original_message: Message, case_type):
    original_message_id = original_message.id
    full_name = f"{user.first_name}{(' ' + user.last_name) if user.last_name else ''}"
    user_mention_text = f"<a href='tg://user?id={user.id}'>{full_name}</a>"

    try:
        await client.delete_messages(chat_id=chat_id, message_ids=original_message_id)
    except Exception as e:
        logger.error(f"Error deleting message: {e}")

    notification_text = ""
    keyboard = []

    settings = get_group_settings(chat_id)

    if case_type == "edited_message_deleted":
        notification_text = (
            f"✏️ **EDITED MESSAGE REMOVED**\n\n"
            f"Hello {user_mention_text}!\n\n"
            f"Your edited message was removed as editing messages to bypass rules is not allowed.\n\n"
            f"Please send a new message instead."
        )
        keyboard = [[InlineKeyboardButton("🗑️ Close", callback_data="close")]]
    
    elif case_type == "abuse_warn":
        abuse_count = get_abuse_warnings_sync(user.id, chat_id)
        notification_text = (
            f"🚫 **INAPPROPRIATE LANGUAGE DETECTED**\n\n"
            f"Hello {user_mention_text}!\n\n"
            f"Your message contained inappropriate language.\n"
            f"**Warning:** {abuse_count}/{settings['abuse_warn_limit']}\n\n"
            f"Please maintain respectful communication."
        )
        keyboard = [[InlineKeyboardButton("🗑️ Close", callback_data="close")]]

    elif case_type == "abuse_mute":
        notification_text = (
            f"🔇 **USER MUTED**\n\n"
            f"Hello {user_mention_text}!\n\n"
            f"You've been muted for repeated inappropriate language."
        )
        keyboard = [[InlineKeyboardButton("✅ Unmute", callback_data=f"unmute_{user.id}_{chat_id}"), InlineKeyboardButton("🗑️ Close", callback_data="close")]]

    elif case_type == "link_or_username":
        notification_text = (
            f"🔗 **LINK/USERNAME REMOVED**\n\n"
            f"Hello {user_mention_text}!\n\n"
            f"Your message contained a link/username and was removed.\n\n"
            f"Please avoid sharing external links."
        )
        keyboard = [[InlineKeyboardButton("🗑️ Close", callback_data="close")]]
    
    elif case_type == "biolink_warn":
        count = increment_warning_sync(chat_id, user.id)
        limit = settings['biolink_warn_limit']
        
        notification_text = (
            f"🚨 **BIO-LINK DETECTED**\n\n"
            f"Hello {user_mention_text}!\n\n"
            f"We found a link in your bio.\n"
            f"**Warning:** {count}/{limit}\n\n"
            f"Please remove the link from your bio."
        )
        keyboard = [
            [InlineKeyboardButton("✅ Whitelist", callback_data=f"whitelist_{user.id}"),
             InlineKeyboardButton("🗑️ Close", callback_data="close")]
        ]
        
    elif case_type == "biolink_mute":
        notification_text = (
            f"🔇 **USER MUTED**\n\n"
            f"{user_mention_text} has been muted for bio-link violation."
        )
        keyboard = [[InlineKeyboardButton("✅ Unmute", callback_data=f"unmute_{user.id}_{chat_id}"), InlineKeyboardButton("🗑️ Close", callback_data="close")]]

    if notification_text:
        try:
            await client.send_message(
                chat_id=chat_id,
                text=notification_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=enums.ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Error sending notification: {e}")

# --- Professional Settings Menu (NEW) ---
async def show_settings_menu(client, message_or_query):
    if isinstance(message_or_query, CallbackQuery):
        chat_id = message_or_query.message.chat.id
        message = message_or_query.message
    else:
        chat_id = message_or_query.chat.id
        message = message_or_query

    if not await is_group_admin(chat_id, message_or_query.from_user.id):
        await message_or_query.reply_text("**❌ Only admins can access settings!**")
        return

    settings = get_group_settings(chat_id)
    
    settings_text = (
        "⚙️ **Bot Settings Menu**\n\n"
        "Choose a category to configure your bot:"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚨 **BIO-LINK PROTECTION**", callback_data="settings_biolink")],
        [InlineKeyboardButton("🚫 **ABUSE DETECTION**", callback_data="settings_abuse")],
        [InlineKeyboardButton("📝 **MESSAGE CONTROLS**", callback_data="settings_messages")],
        [InlineKeyboardButton("❌ **CLOSE**", callback_data="close")]
    ])

    if isinstance(message_or_query, CallbackQuery):
        await message.edit_text(settings_text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)
    else:
        await message.reply_text(settings_text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)

# --- Settings Callbacks ---
async def show_biolink_settings(client, callback_query):
    chat_id = callback_query.message.chat.id
    settings = get_group_settings(chat_id)
    
    status = "✅ **ON**" if settings.get("delete_biolink", True) else "❌ **OFF**"
    limit = settings.get("biolink_warn_limit", 3)
    penalty = settings.get("biolink_penalty", "mute").upper()
    
    text = (
        f"🚨 **Bio-Link Protection**\n\n"
        f"**Status:** {status}\n"
        f"**Warn Limit:** {limit}\n"
        f"**Penalty:** {penalty}\n\n"
        f"**Configure below:**"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🔄 Toggle Status", callback_data="toggle_biolink")],
        [InlineKeyboardButton(f"⚠️ Warn Limit: {limit}", callback_data="change_biolink_limit")],
        [InlineKeyboardButton(f"🔨 Penalty: {penalty}", callback_data="change_biolink_penalty")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_settings")]
    ])
    
    await callback_query.message.edit_text(text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)

# --- Bot Commands ---
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
            f"👋 **Hello {user.mention}!**\n\n"
            f"I'm **{bot_name}**, your group moderation bot.\n"
            f"I help keep your groups clean and safe!"
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

    elif chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        if await is_group_admin(chat.id, bot_info.id):
            group_start_message = f"Hello! I'm **{bot_info.first_name}**, your group moderation bot. I'll help keep this group clean!"
            group_keyboard = [
                [InlineKeyboardButton("➕ Add Me To Your Group", url=add_to_group_url)],
                [InlineKeyboardButton("⚙️ Settings", callback_data="show_settings_menu")]
            ]
        else:
            group_start_message = f"Hello! I'm **{bot_info.first_name}**. Please make me admin with proper permissions to moderate this group."
            group_keyboard = [
                [InlineKeyboardButton("➕ Add Me To Your Group", url=add_to_group_url)]
            ]
        
        reply_markup = InlineKeyboardMarkup(group_keyboard)
        await message.reply_text(group_start_message, reply_markup=reply_markup, parse_mode=enums.ParseMode.HTML)

@client.on_message(filters.command("help"))
async def help_handler(client: Client, message: Message):
    chat_id = message.chat.id
    help_text = (
        "**📋 Bot Commands & Usage**\n\n"
        
        "**🔧 Settings Commands:**\n"
        "`/settings` - Open bot settings menu\n"
        "`/config` - Configure bio-link & abuse settings\n\n"
        
        "**🛡️ Whitelist Commands:**\n"
        "`/free <user>` - Add user to whitelist\n"
        "`/unfree <user>` - Remove from whitelist\n"
        "`/freelist` - Show whitelisted users\n\n"
        
        "**📢 Tagging Commands:**\n"
        "`/tagall <message>` - Tag all members\n"
        "`/onlinetag <message>` - Tag online members\n"
        "`/admin <message>` - Tag admins only\n"
        "`/tagstop` - Stop & delete all tags\n\n"
        
        "**🔍 Other Commands:**\n"
        "`/checkperms` - Check bot permissions\n"
        "`/stats` - Bot statistics (Admin only)\n"
        "`/addabuse <word>` - Add abuse word (Admin only)\n"
        "`/broadcast` - Broadcast message (Admin only)\n\n"
        
        "**Features:**\n"
        "• Auto-delete bio-links\n"
        "• Profanity filter\n"
        "• Edited message deletion\n"
        "• Link/username removal\n"
        "• Warning system with mute/ban"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🗑️ Close", callback_data="close")]])
    await client.send_message(chat_id, help_text, reply_markup=kb, parse_mode=enums.ParseMode.MARKDOWN)

# --- Settings Commands ---
@client.on_message(filters.group & filters.command("settings"))
async def settings_command_handler(client: Client, message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if not await is_group_admin(chat_id, user_id):
        await message.reply_text("**❌ Only admins can use this command!**")
        return

    await show_settings_menu(client, message)

@client.on_message(filters.group & filters.command("config"))
async def configure(client: Client, message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not await is_group_admin(chat_id, user_id):
        return

    settings = get_group_settings(chat_id)
    
    text = (
        "**📋 Configuration Panel**\n\n"
        "Manage your bot settings:"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚨 Bio-Link Settings", callback_data="settings_biolink")],
        [InlineKeyboardButton("🚫 Abuse Settings", callback_data="settings_abuse")],
        [InlineKeyboardButton("📝 Message Controls", callback_data="settings_messages")],
        [InlineKeyboardButton("❌ Close", callback_data="close")]
    ])
    
    await client.send_message(chat_id, text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)
    await message.delete()

# --- Whitelist Commands ---
@client.on_message(filters.group & filters.command("free"))
async def command_free(client: Client, message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not await is_group_admin(chat_id, user_id):
        return await message.reply_text("**❌ Only admins can use this command!**")

    if message.reply_to_message:
        target = message.reply_to_message.from_user
    elif len(message.command) > 1:
        arg = message.command[1]
        try:
            target = await client.get_users(int(arg) if arg.isdigit() else arg)
        except Exception:
            return await client.send_message(chat_id, "**Invalid user or ID provided**", parse_mode=enums.ParseMode.MARKDOWN)
    else:
        return await client.send_message(chat_id, "**Reply to a user or use `/free user_id/username`**", parse_mode=enums.ParseMode.MARKDOWN)

    if not target:
        return await client.send_message(chat_id, "**User not found**", parse_mode=enums.ParseMode.MARKDOWN)

    add_whitelist_sync(chat_id, target.id)
    reset_warnings_sync(chat_id, target.id)

    mention = f"<a href='tg://user?id={target.id}'>{target.first_name}</a>"
    text = f"✅ **{mention} has been whitelisted**"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚫 Unwhitelist", callback_data=f"unwhitelist_{target.id}"),
         InlineKeyboardButton("🗑️ Close", callback_data="close")]
    ])
    await client.send_message(chat_id, text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)

@client.on_message(filters.group & filters.command("unfree"))
async def command_unfree(client: Client, message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not await is_group_admin(chat_id, user_id):
        return await message.reply_text("**❌ Only admins can use this command!**")

    if message.reply_to_message:
        target = message.reply_to_message.from_user
    elif len(message.command) > 1:
        arg = message.command[1]
        try:
            target = await client.get_users(int(arg) if arg.isdigit() else arg)
        except Exception:
            return await client.send_message(chat_id, "**Invalid user or ID provided**", parse_mode=enums.ParseMode.MARKDOWN)
    else:
        return await client.send_message(chat_id, "**Reply to a user or use `/unfree user_id/username`**", parse_mode=enums.ParseMode.MARKDOWN)

    mention = f"<a href='tg://user?id={target.id}'>{target.first_name}</a>"

    if is_whitelisted_sync(chat_id, target.id):
        remove_whitelist_sync(chat_id, target.id)
        text = f"🚫 **{mention} removed from whitelist**"
    else:
        text = f"ℹ️ **{mention} is not whitelisted**"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Whitelist", callback_data=f"whitelist_{target.id}"),
         InlineKeyboardButton("🗑️ Close", callback_data="close")]
    ])
    await client.send_message(chat_id, text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)

@client.on_message(filters.group & filters.command("freelist"))
async def command_freelist(client: Client, message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    
    if not await is_group_admin(chat_id, user_id):
        return await message.reply_text("**❌ Only admins can use this command!**")

    ids = get_whitelist_sync(chat_id)
    if not ids:
        await client.send_message(chat_id, "**⚠️ No whitelisted users in this group**", parse_mode=enums.ParseMode.MARKDOWN)
        return

    text = "**📋 Whitelisted Users:**\n\n"
    for i, uid in enumerate(ids, start=1):
        try:
            user = await client.get_users(uid)
            name = user.first_name
            text += f"{i}. {name} [`{uid}`]\n"
        except:
            text += f"{i}. [User not found] [`{uid}`]\n"

    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🗑️ Close", callback_data="close")]])
    await client.send_message(chat_id, text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)

# --- Tagging Commands ---
@client.on_message(filters.command("tagall") & filters.group)
async def tag_all(client: Client, message: Message) -> None:
    is_sender_admin = await is_group_admin(message.chat.id, message.from_user.id)
    if not is_sender_admin:
        await message.reply_text("**❌ Only admins can use this command!**")
        return

    chat_id = message.chat.id
    if chat_id in ONGOING_TAGGING_TASKS:
        await message.reply_text("**Tagging already in progress. Use /tagstop to cancel.**")
        return

    message_text = " ".join(message.command[1:]) if len(message.command) > 1 else ""
    
    try:
        members_to_tag = []
        async for member in client.get_chat_members(chat_id):
            if not member.user.is_bot:
                emoji = random.choice(EMOJIS)
                members_to_tag.append(member.user.mention(emoji))

        if not members_to_tag:
            await message.reply_text("**No members found to tag.**", parse_mode=enums.ParseMode.MARKDOWN)
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
                await message.reply_text("**✅ All members tagged successfully!**", parse_mode=enums.ParseMode.MARKDOWN)

            except Exception as e:
                logger.error(f"Error in /tagall: {e}")
                await message.reply_text(f"**Error in tagging: {e}**")
                if chat_id in ONGOING_TAGGING_TASKS:
                    ONGOING_TAGGING_TASKS.pop(chat_id)
        
        task = asyncio.create_task(tag_task())
        ONGOING_TAGGING_TASKS[chat_id] = task
        TAG_MESSAGES[chat_id] = tag_messages_to_delete

    except Exception as e:
        await message.reply_text(f"**Error: {e}**")
        if chat_id in ONGOING_TAGGING_TASKS:
            ONGOING_TAGGING_TASKS.pop(chat_id)

@client.on_message(filters.command("onlinetag") & filters.group)
async def online_tag(client: Client, message: Message) -> None:
    is_sender_admin = await is_group_admin(message.chat.id, message.from_user.id)
    if not is_sender_admin:
        await message.reply_text("**❌ Only admins can use this command!**")
        return

    chat_id = message.chat.id
    if chat_id in ONGOING_TAGGING_TASKS:
        await message.reply_text("**Tagging already in progress. Use /tagstop to cancel.**")
        return

    message_text = " ".join(message.command[1:]) if len(message.command) > 1 else ""

    try:
        online_members_to_tag = []
        async for member in client.get_chat_members(chat_id):
            if not member.user.is_bot and member.user.status in [enums.UserStatus.ONLINE, enums.UserStatus.RECENTLY]:
                emoji = random.choice(EMOJIS)
                online_members_to_tag.append(member.user.mention(emoji))

        if not online_members_to_tag:
            await message.reply_text("**No online members found.**", parse_mode=enums.ParseMode.MARKDOWN)
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
                await message.reply_text("**✅ Online members tagged successfully!**", parse_mode=enums.ParseMode.MARKDOWN)

            except Exception as e:
                logger.error(f"Error in /onlinetag: {e}")
                await message.reply_text(f"**Error: {e}**")
                if chat_id in ONGOING_TAGGING_TASKS:
                    ONGOING_TAGGING_TASKS.pop(chat_id)
        
        task = asyncio.create_task(online_tag_task())
        ONGOING_TAGGING_TASKS[chat_id] = task
        TAG_MESSAGES[chat_id] = tag_messages_to_delete

    except Exception as e:
        await message.reply_text(f"**Error: {e}**")
        if chat_id in ONGOING_TAGGING_TASKS:
            ONGOING_TAGGING_TASKS.pop(chat_id)

@client.on_message(filters.command("admin") & filters.group)
async def tag_admins(client: Client, message: Message) -> None:
    is_sender_admin = await is_group_admin(message.chat.id, message.from_user.id)
    if not is_sender_admin:
        await message.reply_text("**❌ Only admins can use this command!**")
        return

    message_text = " ".join(message.command[1:]) if len(message.command) > 1 else "Admin attention required!"
    chat_id = message.chat.id

    try:
        admins = [admin async for admin in client.get_chat_members(chat_id, filter=enums.ChatMembersFilter.ADMINISTRATORS)]
        tagged_admins = []
        for admin in admins:
            if not admin.user.is_bot:
                tagged_admins.append(f"👑 {admin.user.mention}")

        if not tagged_admins:
            await message.reply_text("**No admins found.**", parse_mode=enums.ParseMode.MARKDOWN)
            return

        tag_message_text = " ".join(tagged_admins)
        sent_message = await message.reply_text(
            f"{tag_message_text}\n\n{message_text}",
            parse_mode=enums.ParseMode.HTML,
            disable_web_page_preview=True
        )
        
        if chat_id not in TAG_MESSAGES:
            TAG_MESSAGES[chat_id] = []
        TAG_MESSAGES[chat_id].append(sent_message.id)

    except Exception as e:
        await message.reply_text(f"**Error: {e}**")

@client.on_message(filters.command("tagstop") & filters.group)
async def tag_stop(client: Client, message: Message) -> None:
    chat_id = message.chat.id
    is_sender_admin = await is_group_admin(chat_id, message.from_user.id)
    if not is_sender_admin:
        await message.reply_text("**❌ Only admins can use this command!**")
        return

    if chat_id in ONGOING_TAGGING_TASKS:
        try:
            task = ONGOING_TAGGING_TASKS.pop(chat_id)
            task.cancel()
            await message.reply_text("**✅ Tagging stopped successfully!**")
        except Exception as e:
            await message.reply_text(f"**Error: {e}**")
        return

    if chat_id not in TAG_MESSAGES or not TAG_MESSAGES[chat_id]:
        await message.reply_text("**No tagging messages to delete.**")
        return

    try:
        await client.delete_messages(chat_id, TAG_MESSAGES[chat_id])
        TAG_MESSAGES.pop(chat_id)
        await message.reply_text("**✅ All tagging messages deleted!**")
    except Exception as e:
        await message.reply_text(f"**Error: {e}**")

# --- Admin Commands ---
@client.on_message(filters.command("stats") & filters.user(ADMIN_USER_IDS))
async def stats(client: Client, message: Message) -> None:
    total_groups = 0
    total_users = 0
    
    if db is not None:
        try:
            if db.groups is not None:
                total_groups = db.groups.count_documents({})
            if db.users is not None:
                total_users = db.users.count_documents({})
        except Exception as e:
            logger.error(f"Error fetching stats: {e}")

    stats_message = (
        f"📊 **Bot Statistics**\n\n"
        f"• **Total Users:** {total_users}\n"
        f"• **Total Groups:** {total_groups}\n"
        f"• **Uptime:** {str(datetime.now() - bot_start_time).split('.')[0]}\n"
        f"• **Last Updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    await message.reply_text(stats_message, parse_mode=enums.ParseMode.MARKDOWN)

@client.on_message(filters.command("addabuse") & filters.user(ADMIN_USER_IDS))
async def add_abuse_word(client: Client, message: Message) -> None:
    if len(message.command) < 2:
        await message.reply_text("**Usage:** `/addabuse <word>`", parse_mode=enums.ParseMode.MARKDOWN)
        return
    
    word_to_add = " ".join(message.command[1:]).lower().strip()
    
    if profanity_filter is not None:
        try:
            if await profanity_filter.add_bad_word(word_to_add):
                await message.reply_text(f"✅ **Added:** `{word_to_add}`", parse_mode=enums.ParseMode.MARKDOWN)
            else:
                await message.reply_text(f"ℹ️ **Already exists:** `{word_to_add}`", parse_mode=enums.ParseMode.MARKDOWN)
        except Exception as e:
            await message.reply_text(f"**Error:** {e}")
    else:
        await message.reply_text("**Profanity filter not available**")

@client.on_message(filters.command("checkperms") & filters.group)
async def check_permissions(client: Client, message: Message):
    if not await is_group_admin(message.chat.id, message.from_user.id):
        await message.reply_text("**❌ Only admins can use this command!**")
        return

    chat = message.chat
    try:
        bot_member = await client.get_chat_member(chat.id, client.me.id)
        perms = bot_member.privileges

        message_text = (
            f"**🔍 Bot Permissions in {chat.title}**\n\n"
            f"✅ **Delete Messages:** {perms.can_delete_messages}\n"
            f"✅ **Restrict Members:** {perms.can_restrict_members}\n"
            f"✅ **Pin Messages:** {perms.can_pin_messages}\n"
            f"✅ **Send Messages:** {perms.can_post_messages}\n"
        )

        await message.reply_text(message_text, parse_mode=enums.ParseMode.MARKDOWN)
    except Exception as e:
        await message.reply_text(f"**Error:** {e}")

# --- Broadcast System ---
@client.on_message(filters.command("broadcast") & filters.user(ADMIN_USER_IDS) & filters.private)
async def broadcast_command(client: Client, message: Message) -> None:
    await message.reply_text("**📢 Send your broadcast message:**")
    BROADCAST_MESSAGE[message.from_user.id] = "waiting_for_message"

@client.on_message(filters.private & filters.user(ADMIN_USER_IDS) & ~filters.command([]))
async def handle_broadcast_message(client: Client, message: Message) -> None:
    user = message.from_user

    if BROADCAST_MESSAGE.get(user.id) != "waiting_for_message":
        return

    BROADCAST_MESSAGE[user.id] = message

    keyboard = [
        [InlineKeyboardButton("✅ Send Now", callback_data="confirm_broadcast")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_broadcast")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await message.reply_text("**Confirm broadcast?**", reply_markup=reply_markup)
    except Exception as e:
        await message.reply_text(f"**Error:** {e}")
        BROADCAST_MESSAGE.pop(user.id, None)

# --- Message Handlers ---
@client.on_message(filters.group & filters.text & ~filters.via_bot)
async def handle_all_messages(client: Client, message: Message) -> None:
    user = message.from_user
    chat = message.chat
    message_text = message.text

    if not user:
        return
    if await is_group_admin(chat.id, user.id) or is_whitelisted_sync(chat.id, user.id):
        return

    settings = get_group_settings(chat_id)

    # Check for abuse words
    if settings.get("delete_abuse", True) and profanity_filter is not None and profanity_filter.contains_profanity(message_text):
        limit = settings['abuse_warn_limit']
        abuse_count = increment_abuse_warning_sync(chat.id, user.id)
        
        if abuse_count >= limit:
            penalty = settings['abuse_penalty']
            try:
                if penalty == "mute":
                    await client.restrict_chat_member(chat.id, user.id, ChatPermissions())
                    await handle_incident(client, chat.id, user, "Abuse", message, "abuse_mute")
                else:
                    await client.ban_chat_member(chat.id, user.id)
                    await client.send_message(chat.id, f"**{user.first_name} banned for repeated abuse**", parse_mode=enums.ParseMode.MARKDOWN)
            except errors.ChatAdminRequired:
                pass
        else:
            await handle_incident(client, chat.id, user, "Abuse", message, "abuse_warn")
        return

    # Check for links/usernames
    if settings.get("delete_links_usernames", True) and URL_PATTERN.search(message_text):
        await handle_incident(client, chat.id, user, "Link/Username", message, "link_or_username")
        return
        
    # Check bio for links
    if settings.get("delete_biolink", True) and await check_and_delete_biolink(client, message):
        return

async def check_and_delete_biolink(client: Client, message: Message):
    user = message.from_user
    chat_id = message.chat.id

    if await is_group_admin(chat_id, user.id) or is_whitelisted_sync(chat_id, user.id):
        return False
    
    try:
        user_profile = await client.get_chat(user.id)
        user_bio = user_profile.bio or ""
        
        if URL_PATTERN.search(user_bio):
            settings = get_group_settings(chat_id)
            limit = settings['biolink_warn_limit']
            count = increment_warning_sync(chat_id, user.id)
            
            if count >= limit:
                penalty = settings['biolink_penalty']
                try:
                    if penalty == "mute":
                        await client.restrict_chat_member(chat_id, user.id, ChatPermissions())
                        await handle_incident(client, chat_id, user, "Bio-link", message, "biolink_mute")
                    else:
                        await client.ban_chat_member(chat_id, user.id)
                        await client.send_message(chat_id, f"**{user.first_name} banned for bio-link**", parse_mode=enums.ParseMode.MARKDOWN)
                except errors.ChatAdminRequired:
                    pass
            else:
                await handle_incident(client, chat_id, user, "Bio-link", message, "biolink_warn")
            return True
        return False
    except Exception:
        return False

@client.on_edited_message(filters.text & filters.group & ~filters.via_bot)
async def handle_edited_messages(client: Client, edited_message: Message) -> None:
    if not edited_message or not edited_message.text:
        return

    user = edited_message.from_user
    chat = edited_message.chat

    if not user:
        return

    if await is_group_admin(chat.id, user.id) or is_whitelisted_sync(chat.id, user.id):
        return
    
    settings = get_group_settings(chat.id)
    if settings.get("delete_edited", True):
        await handle_incident(client, chat.id, user, "Edited message", edited_message, "edited_message_deleted")

# --- Callback Query Handler ---
@client.on_callback_query()
async def callback_handler(client: Client, callback_query: CallbackQuery) -> None:
    data = callback_query.data
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id

    # Admin check
    if chat_id < 0 and data not in ["close", "help_menu", "other_bots", "donate_info", "back_to_main_menu"]:
        if not await is_group_admin(chat_id, user_id):
            await callback_query.answer("❌ Only admins can change settings!", show_alert=True)
            return

    await callback_query.answer()

    # Settings callbacks
    if data == "back_settings":
        await show_settings_menu(client, callback_query)
    
    elif data == "settings_biolink":
        await show_biolink_settings(client, callback_query)
    
    elif data == "settings_abuse":
        await show_abuse_settings(client, callback_query)
    
    elif data == "settings_messages":
        await show_message_settings(client, callback_query)
    
    elif data.startswith("toggle_"):
        parts = data.split('_')
        setting_type = parts[1]
        settings = get_group_settings(chat_id)
        current = settings.get(setting_type, True)
        update_group_setting(chat_id, setting_type, not current)
        
        if setting_type == "delete_biolink":
            await show_biolink_settings(client, callback_query)
        elif setting_type == "delete_abuse":
            await show_abuse_settings(client, callback_query)
        elif setting_type in ["delete_edited", "delete_links_usernames"]:
            await show_message_settings(client, callback_query)
    
    elif data.startswith("change_") and data.endswith("_limit"):
        setting_type = data.split('_')[1]
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("3", callback_data=f"set_limit_{setting_type}_3")],
            [InlineKeyboardButton("4", callback_data=f"set_limit_{setting_type}_4")],
            [InlineKeyboardButton("5", callback_data=f"set_limit_{setting_type}_5")],
            [InlineKeyboardButton("🔙 Back", callback_data=f"settings_{setting_type.replace('_warn_limit', '')}")]
        ])
        await callback_query.message.edit_text(
            f"**⚠️ Select warning limit for {setting_type.split('_')[0]}:**",
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
    
    elif data.startswith("change_") and data.endswith("_penalty"):
        setting_type = data.split('_')[1]
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔇 MUTE", callback_data=f"set_penalty_{setting_type}_mute")],
            [InlineKeyboardButton("🔨 BAN", callback_data=f"set_penalty_{setting_type}_ban")],
            [InlineKeyboardButton("🔙 Back", callback_data=f"settings_{setting_type.replace('_penalty', '')}")]
        ])
        await callback_query.message.edit_text(
            f"**🔨 Select penalty for {setting_type.replace('_penalty', '')}:**",
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

    # Original callbacks
    elif data == "close":
        try:
            await callback_query.message.delete()
        except:
            pass
    elif data == "help_menu":
        help_text = (
            "**📋 Bot Help Menu**\n\n"
            "**Features:**\n"
            "• Auto-delete bio-links\n"
            "• Profanity filter\n"
            "• Edited message deletion\n"
            "• Link/username removal\n"
            "• Warning system\n\n"
            "**Commands:**\n"
            "`/start` - Start the bot\n"
            "`/settings` - Open settings\n"
            "`/config` - Configure settings\n"
            "`/free/unfree/freelist` - Manage whitelist\n"
            "`/tagall/onlinetag/admin/tagstop` - Tagging commands\n"
            "`/checkperms` - Check permissions\n"
            "`/stats` - View statistics"
        )
        keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="back_to_main_menu")]]
        await callback_query.message.edit_text(help_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=enums.ParseMode.MARKDOWN)

    elif data == "other_bots":
        other_bots_text = (
            "**🤖 Our Other Bots:**\n\n"
            "• **@asflter_bot** - Movies & Webseries Bot\n"
            "• **@askiangelbot** - Chat & Management Bot"
        )
        keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="back_to_main_menu")]]
        await callback_query.message.edit_text(other_bots_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=enums.ParseMode.MARKDOWN)

    elif data == "donate_info":
        donate_text = (
            "**💖 Support Us**\n\n"
            "If you like this bot, consider supporting:\n"
            "• UPI: `arsadsaifi8272@ibl`\n\n"
            "Thank you!"
        )
        keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="back_to_main_menu")]]
        await callback_query.message.edit_text(donate_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=enums.ParseMode.MARKDOWN)

    elif data == "back_to_main_menu":
        bot_info = await client.get_me()
        bot_name = bot_info.first_name
        bot_username = bot_info.username
        add_to_group_url = f"https://t.me/{bot_username}?startgroup=true"

        welcome_message = (
            f"👋 **Hello!**\n\n"
            f"I'm **{bot_name}**, your group moderation bot!"
        )
        
        keyboard = [
            [InlineKeyboardButton("➕ Add Me To Your Group", url=add_to_group_url)],
            [InlineKeyboardButton("❓ Help", callback_data="help_menu"), InlineKeyboardButton("🤖 Other Bots", callback_data="other_bots")],
            [InlineKeyboardButton("📢 Update Channel", url="https://t.me/asbhai_bsr"), InlineKeyboardButton("💖 Donate", callback_data="donate_info")]
        ]
        await callback_query.message.edit_text(welcome_message, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=enums.ParseMode.MARKDOWN)

# --- Flask App ---
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

    logger.info("Complete Bot with All Features is starting...")
    client.run()
    logger.info("Bot stopped")
