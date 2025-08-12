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

# Load environment variables
load_dotenv()

# --- Configuration ---
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
LOG_CHANNEL_ID = -1002352329534
MONGO_DB_URI = os.getenv("MONGO_DB_URI")
ADMIN_USER_IDS = [7315805581]

bot_start_time = datetime.now()
BROADCAST_MESSAGE = {}
URL_PATTERN = re.compile(r'\b(?:https?://|www\.|t\.me/|telegra\.ph/)[^\s]+\b|@\w+', re.IGNORECASE)

# --- Variables ---
TAG_MESSAGES = {}
ONGOING_TAGGING_TASKS = {}
EMOJIS = ['😀', '😃', '😄', '😁', '😆', '😅', '🤣', '😂', '🙂', '🙃', '😉', '😊', '😇', '🥰', '😍']

# --- Logging ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- Client ---
client = Client(
    "my_bot_session",
    bot_token=TELEGRAM_BOT_TOKEN,
    api_id=API_ID,
    api_hash=API_HASH
)

mongo_client = None
db = None
profanity_filter = None

# --- MongoDB ---
def init_mongodb():
    global mongo_client, db, profanity_filter
    if MONGO_DB_URI is None:
        logger.error("MONGO_DB_URI not set")
        profanity_filter = ProfanityFilter(mongo_uri=None)
        return

    try:
        mongo_client = MongoClient(MONGO_DB_URI)
        db = mongo_client.get_database("asfilter")
        
        db.groups.create_index("chat_id", unique=True)
        db.users.create_index("user_id", unique=True)
        db.warnings.create_index([("user_id", 1), ("chat_id", 1)], unique=True)
        db.settings.create_index("chat_id", unique=True)
        db.whitelist.create_index([("chat_id", 1), ("user_id", 1)], unique=True)
        
        profanity_filter = ProfanityFilter(mongo_uri=MONGO_DB_URI)
        logger.info("MongoDB initialized")
    except Exception as e:
        logger.error(f"MongoDB error: {e}")
        profanity_filter = ProfanityFilter(mongo_uri=None)

# --- Helper Functions ---
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_USER_IDS

async def is_group_admin(chat_id: int, user_id: int) -> bool:
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in [enums.ChatMemberStatus.OWNER, enums.ChatMemberStatus.ADMINISTRATOR]
    except:
        return False

async def log_to_channel(text: str, parse_mode=None) -> None:
    if not LOG_CHANNEL_ID:
        return
    try:
        await client.send_message(chat_id=LOG_CHANNEL_ID, text=text, parse_mode=parse_mode)
    except:
        pass

# --- Settings System ---
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

# --- Warning Functions ---
def get_warnings_sync(user_id: int, chat_id: int):
    if db is None:
        return 0
    warnings_doc = db.warnings.find_one({"user_id": user_id, "chat_id": chat_id})
    return warnings_doc.get("count", 0) if warnings_doc else 0

def increment_warning_sync(chat_id, user_id):
    if db is None:
        return 1
    warnings_doc = db.warnings.find_one_and_update(
        {"chat_id": chat_id, "user_id": user_id},
        {"$inc": {"count": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER
    )
    return warnings_doc.get("count", 1)

def reset_warnings_sync(chat_id, user_id):
    if db is None:
        return
    db.warnings.delete_one({"chat_id": chat_id, "user_id": user_id})

def get_abuse_warnings_sync(user_id: int, chat_id: int):
    if db is None:
        return 0
    warnings_doc = db.warnings.find_one({"user_id": user_id, "chat_id": chat_id})
    return warnings_doc.get("abuse_count", 0) if warnings_doc else 0

def increment_abuse_warning_sync(chat_id, user_id):
    if db is None:
        return 1
    warnings_doc = db.warnings.find_one_and_update(
        {"chat_id": chat_id, "user_id": user_id},
        {"$inc": {"abuse_count": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER
    )
    return warnings_doc.get("abuse_count", 1)

# --- Whitelist Functions ---
def is_whitelisted_sync(chat_id, user_id):
    if db is None:
        return False
    return db.whitelist.find_one({"chat_id": chat_id, "user_id": user_id}) is not None

def add_whitelist_sync(chat_id, user_id):
    if db is None:
        return
    db.whitelist.update_one({"chat_id": chat_id, "user_id": user_id}, {"$set": {"timestamp": datetime.now()}}, upsert=True)

def remove_whitelist_sync(chat_id, user_id):
    if db is None:
        return
    db.whitelist.delete_one({"chat_id": chat_id, "user_id": user_id})

def get_whitelist_sync(chat_id):
    if db is None:
        return []
    return [doc["user_id"] for doc in db.whitelist.find({"chat_id": chat_id})]

# --- Settings Menu Functions ---
async def show_settings_menu(client, message_or_query):
    if isinstance(message_or_query, CallbackQuery):
        chat_id = message_or_query.message.chat.id
        message = message_or_query.message
    else:
        chat_id = message_or_query.chat.id
        message = message_or_query

    if not await is_group_admin(chat_id, message_or_query.from_user.id):
        await message_or_query.reply_text("Only admins can access settings!")
        return

    settings = get_group_settings(chat_id)
    
    text = "⚙️ Bot Settings\n\nChoose what to configure:"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚨 Bio-Link Protection", callback_data="settings_biolink")],
        [InlineKeyboardButton("🚫 Abuse Detection", callback_data="settings_abuse")],
        [InlineKeyboardButton("📝 Message Controls", callback_data="settings_messages")],
        [InlineKeyboardButton("❌ Close", callback_data="close")]
    ])

    if isinstance(message_or_query, CallbackQuery):
        await message.edit_text(text, reply_markup=keyboard)
    else:
        await message.reply_text(text, reply_markup=keyboard)

async def show_biolink_settings(client, callback_query):
    chat_id = callback_query.message.chat.id
    settings = get_group_settings(chat_id)
    
    status = "ON" if settings.get("delete_biolink", True) else "OFF"
    limit = settings.get("biolink_warn_limit", 3)
    penalty = settings.get("biolink_penalty", "mute").upper()
    
    text = f"🚨 Bio-Link Settings\n\nStatus: {status}\nWarn Limit: {limit}\nPenalty: {penalty}"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"Toggle ({status})", callback_data="toggle_delete_biolink")],
        [InlineKeyboardButton(f"Warn Limit: {limit}", callback_data="change_biolink_limit")],
        [InlineKeyboardButton(f"Penalty: {penalty}", callback_data="change_biolink_penalty")],
        [InlineKeyboardButton("Back", callback_data="back_settings")]
    ])
    
    await callback_query.message.edit_text(text, reply_markup=keyboard)

async def show_abuse_settings(client, callback_query):
    chat_id = callback_query.message.chat.id
    settings = get_group_settings(chat_id)
    
    status = "ON" if settings.get("delete_abuse", True) else "OFF"
    limit = settings.get("abuse_warn_limit", 3)
    penalty = settings.get("abuse_penalty", "mute").upper()
    
    text = f"🚫 Abuse Detection\n\nStatus: {status}\nWarn Limit: {limit}\nPenalty: {penalty}"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"Toggle ({status})", callback_data="toggle_delete_abuse")],
        [InlineKeyboardButton(f"Warn Limit: {limit}", callback_data="change_abuse_limit")],
        [InlineKeyboardButton(f"Penalty: {penalty}", callback_data="change_abuse_penalty")],
        [InlineKeyboardButton("Back", callback_data="back_settings")]
    ])
    
    await callback_query.message.edit_text(text, reply_markup=keyboard)

async def show_message_controls(client, callback_query):
    chat_id = callback_query.message.chat.id
    settings = get_group_settings(chat_id)
    
    edited_status = "ON" if settings.get("delete_edited", True) else "OFF"
    links_status = "ON" if settings.get("delete_links_usernames", True) else "OFF"
    
    text = f"📝 Message Controls\n\nDelete Edited: {edited_status}\nDelete Links: {links_status}"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"Edited ({edited_status})", callback_data="toggle_delete_edited")],
        [InlineKeyboardButton(f"Links ({links_status})", callback_data="toggle_delete_links_usernames")],
        [InlineKeyboardButton("Back", callback_data="back_settings")]
    ])
    
    await callback_query.message.edit_text(text, reply_markup=keyboard)

# --- Handle Incident ---
async def handle_incident(client: Client, chat_id, user, reason, original_message: Message, case_type):
    original_message_id = original_message.id
    full_name = f"{user.first_name}{(' ' + user.last_name) if user.last_name else ''}"
    user_mention = f"<a href='tg://user?id={user.id}'>{full_name}</a>"

    try:
        await client.delete_messages(chat_id=chat_id, message_ids=original_message_id)
    except Exception as e:
        logger.error(f"Error deleting message: {e}")

    settings = get_group_settings(chat_id)
    notification_text = ""
    keyboard = []

    if case_type == "edited_message_deleted":
        notification_text = f"✏️ Edited message removed\n\n{user_mention}, editing messages to bypass rules is not allowed."
        keyboard = [[InlineKeyboardButton("Close", callback_data="close")]]
    
    elif case_type == "abuse_warn":
        abuse_count = get_abuse_warnings_sync(user.id, chat_id)
        limit = settings['abuse_warn_limit']
        notification_text = f"🚫 Inappropriate language detected\n\n{user_mention}, warning {abuse_count}/{limit}"
        keyboard = [[InlineKeyboardButton("Close", callback_data="close")]]

    elif case_type == "abuse_mute":
        notification_text = f"🔇 {user_mention} muted for repeated inappropriate language"
        keyboard = [[InlineKeyboardButton("Unmute", callback_data=f"unmute_{user.id}_{chat_id}"), InlineKeyboardButton("Close", callback_data="close")]]

    elif case_type == "link_or_username":
        notification_text = f"🔗 Link removed\n\n{user_mention}, external links are not allowed here."
        keyboard = [[InlineKeyboardButton("Close", callback_data="close")]]
    
    elif case_type == "biolink_warn":
        count = increment_warning_sync(chat_id, user.id)
        limit = settings['biolink_warn_limit']
        notification_text = f"🚨 Bio-link detected\n\n{user_mention}, warning {count}/{limit}\nPlease remove link from bio."
        keyboard = [[InlineKeyboardButton("Whitelist", callback_data=f"whitelist_{user.id}"), InlineKeyboardButton("Close", callback_data="close")]]
        
    elif case_type == "biolink_mute":
        notification_text = f"🔇 {user_mention} muted for bio-link violation"

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

# --- Commands ---
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
            f"👋 Hello {user.mention}!\n\n"
            f"I'm {bot_name}, your group moderation bot.\n"
            f"I help keep your groups clean and safe!"
        )

        keyboard = [
            [InlineKeyboardButton("➕ Add Me To Your Group", url=add_to_group_url)],
            [InlineKeyboardButton("❓ Help", callback_data="help_menu")],
            [InlineKeyboardButton("📢 Updates", url="https://t.me/asbhai_bsr")]
        ]
        
        await message.reply_text(welcome_message, reply_markup=InlineKeyboardMarkup(keyboard))

    elif chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        await message.reply_text(f"Hello! I'm {bot_info.first_name}, your group moderation bot.")

@client.on_message(filters.command("help"))
async def help_handler(client: Client, message: Message):
    help_text = (
        "📋 Available Commands:\n\n"
        "⚙️ /settings - Open settings menu\n"
        "📢 /tagall <message> - Tag all members\n"
        "🟢 /onlinetag <message> - Tag online members\n"
        "👑 /admin <message> - Tag admins\n"
        "🛑 /tagstop - Stop tagging\n"
        "🔍 /checkperms - Check bot permissions\n"
        "📊 /stats - Bot statistics (admin only)\n"
        "📝 /addabuse <word> - Add abuse word (admin only)"
    )
    await message.reply_text(help_text)

@client.on_message(filters.group & filters.command("settings"))
async def settings_command(client: Client, message: Message):
    if not await is_group_admin(message.chat.id, message.from_user.id):
        await message.reply_text("Only admins can use this command!")
        return
    await show_settings_menu(client, message)

@client.on_message(filters.command("checkperms") & filters.group)
async def check_permissions(client: Client, message: Message):
    if not await is_group_admin(message.chat.id, message.from_user.id):
        await message.reply_text("Only admins can use this command!")
        return

    try:
        bot_member = await client.get_chat_member(message.chat.id, client.me.id)
        perms = bot_member.privileges
        message_text = (
            f"🔍 Bot Permissions:\n"
            f"Delete Messages: {perms.can_delete_messages}\n"
            f"Restrict Members: {perms.can_restrict_members}\n"
            f"Send Messages: {perms.can_post_messages}"
        )
        await message.reply_text(message_text)
    except Exception as e:
        await message.reply_text(f"Error: {e}")

@client.on_message(filters.command("addabuse") & filters.user(ADMIN_USER_IDS))
async def add_abuse_word(client: Client, message: Message) -> None:
    if len(message.command) < 2:
        await message.reply_text("Usage: /addabuse <word>")
        return
    
    word_to_add = " ".join(message.command[1:]).lower()
    if profanity_filter and await profanity_filter.add_bad_word(word_to_add):
        await message.reply_text(f"Added: {word_to_add}")
    else:
        await message.reply_text("Failed to add word")

@client.on_message(filters.command("stats") & filters.user(ADMIN_USER_IDS))
async def stats(client: Client, message: Message) -> None:
    total_groups = db.groups.count_documents({}) if db else 0
    total_users = db.users.count_documents({}) if db else 0
    
    stats_message = (
        f"📊 Bot Statistics:\n\n"
        f"Total Groups: {total_groups}\n"
        f"Total Users: {total_users}\n"
        f"Uptime: {str(datetime.now() - bot_start_time).split('.')[0]}"
    )
    await message.reply_text(stats_message)

# --- Tagging Commands ---
@client.on_message(filters.command("tagall") & filters.group)
async def tag_all(client: Client, message: Message) -> None:
    if not await is_group_admin(message.chat.id, message.from_user.id):
        await message.reply_text("Only admins can use this command!")
        return

    chat_id = message.chat.id
    message_text = " ".join(message.command[1:]) if len(message.command) > 1 else ""
    
    try:
        members = []
        async for member in client.get_chat_members(chat_id):
            if not member.user.is_bot:
                members.append(member.user.mention)

        if members:
            tag_text = " ".join(members[:20])  # Limit to 20 members
            if message_text:
                tag_text += f"\n\n{message_text}"
            await message.reply_text(tag_text)
        else:
            await message.reply_text("No members to tag")
    except Exception as e:
        await message.reply_text(f"Error: {e}")

@client.on_message(filters.command("onlinetag") & filters.group)
async def online_tag(client: Client, message: Message) -> None:
    if not await is_group_admin(message.chat.id, message.from_user.id):
        await message.reply_text("Only admins can use this command!")
        return

    chat_id = message.chat.id
    message_text = " ".join(message.command[1:]) if len(message.command) > 1 else ""
    
    try:
        online_members = []
        async for member in client.get_chat_members(chat_id):
            if not member.user.is_bot and member.user.status in [enums.UserStatus.ONLINE, enums.UserStatus.RECENTLY]:
                online_members.append(member.user.mention)

        if online_members:
            tag_text = " ".join(online_members[:20])  # Limit to 20 members
            if message_text:
                tag_text += f"\n\n{message_text}"
            await message.reply_text(tag_text)
        else:
            await message.reply_text("No online members")
    except Exception as e:
        await message.reply_text(f"Error: {e}")

@client.on_message(filters.command("admin") & filters.group)
async def tag_admins(client: Client, message: Message) -> None:
    if not await is_group_admin(message.chat.id, message.from_user.id):
        await message.reply_text("Only admins can use this command!")
        return

    message_text = " ".join(message.command[1:]) if len(message.command) > 1 else ""
    
    try:
        admins = []
        async for admin in client.get_chat_members(message.chat.id, filter=enums.ChatMembersFilter.ADMINISTRATORS):
            if not admin.user.is_bot:
                admins.append(f"👑 {admin.user.mention}")

        if admins:
            tag_text = " ".join(admins)
            if message_text:
                tag_text += f"\n\n{message_text}"
            await message.reply_text(tag_text)
    except Exception as e:
        await message.reply_text(f"Error: {e}")

@client.on_message(filters.command("tagstop") & filters.group)
async def tag_stop(client: Client, message: Message) -> None:
    if not await is_group_admin(message.chat.id, message.from_user.id):
        await message.reply_text("Only admins can use this command!")
        return
    await message.reply_text("Tagging stopped!")

# --- Message Handlers ---
@client.on_message(filters.group & filters.text & ~filters.via_bot)
async def handle_all_messages(client: Client, message: Message) -> None:
    user = message.from_user
    chat = message.chat  # ✅ Fixed variable name
    message_text = message.text

    if not user or await is_group_admin(chat.id, user.id) or is_whitelisted_sync(chat.id, user.id):
        return

    settings = get_group_settings(chat.id)  # ✅ Fixed variable name

    # Abuse detection
    if settings.get("delete_abuse", True) and profanity_filter and profanity_filter.contains_profanity(message_text):
        limit = settings['abuse_warn_limit']
        abuse_count = increment_abuse_warning_sync(chat.id, user.id)
        
        if abuse_count >= limit:
            penalty = settings['abuse_penalty']
            try:
                if penalty == "mute":
                    await client.restrict_chat_member(chat.id, user.id, ChatPermissions())
                    await handle_incident(client, chat.id, user, "abuse", message, "abuse_mute")
                else:
                    await client.ban_chat_member(chat.id, user.id)
            except:
                pass
        else:
            await handle_incident(client, chat.id, user, "abuse", message, "abuse_warn")
        return

    # Link/username detection
    if settings.get("delete_links_usernames", True) and URL_PATTERN.search(message_text):
        await handle_incident(client, chat.id, user, "link/username", message, "link_or_username")
        return
        
    # Bio link detection
    if settings.get("delete_biolink", True) and await check_bio_link(client, message):
        return

async def check_bio_link(client: Client, message: Message):
    user = message.from_user
    chat = message.chat  # ✅ Fixed variable name
    
    if await is_group_admin(chat.id, user.id) or is_whitelisted_sync(chat.id, user.id):
        return False
    
    try:
        user_profile = await client.get_chat(user.id)
        user_bio = user_profile.bio or ""
        
        if URL_PATTERN.search(user_bio):
            settings = get_group_settings(chat.id)  # ✅ Fixed variable name
            limit = settings['biolink_warn_limit']
            count = increment_warning_sync(chat.id, user.id)
            
            if count >= limit:
                penalty = settings['biolink_penalty']
                try:
                    if penalty == "mute":
                        await client.restrict_chat_member(chat.id, user.id, ChatPermissions())
                        await handle_incident(client, chat.id, user, "bio-link", message, "biolink_mute")
                    else:
                        await client.ban_chat_member(chat.id, user.id)
                except:
                    pass
            else:
                await handle_incident(client, chat.id, user, "bio-link", message, "biolink_warn")
            return True
    except:
        return False

@client.on_edited_message(filters.text & filters.group & ~filters.via_bot)
async def handle_edited_messages(client: Client, edited_message: Message) -> None:
    if not edited_message or not edited_message.text:
        return

    user = edited_message.from_user
    chat = edited_message.chat  # ✅ Fixed variable name

    if not user or await is_group_admin(chat.id, user.id) or is_whitelisted_sync(chat.id, user.id):
        return
    
    settings = get_group_settings(chat.id)  # ✅ Fixed variable name
    if settings.get("delete_edited", True):
        await handle_incident(client, chat.id, user, "edited message", edited_message, "edited_message_deleted")

# --- Callback Handler ---
@client.on_callback_query()
async def callback_handler(client: Client, callback_query: CallbackQuery) -> None:
    data = callback_query.data
    user_id = callback_query.from_user.id
    chat_id = callback_query.message.chat.id

    if chat_id < 0 and not await is_group_admin(chat_id, user_id):
        await callback_query.answer("Only admins can change settings!", show_alert=True)
        return

    await callback_query.answer()

    settings = get_group_settings(chat_id)

    if data == "back_settings":
        await show_settings_menu(client, callback_query)
    
    elif data == "settings_biolink":
        await show_biolink_settings(client, callback_query)
    
    elif data == "settings_abuse":
        await show_abuse_settings(client, callback_query)
    
    elif data == "settings_messages":
        await show_message_controls(client, callback_query)
    
    elif data.startswith("toggle_"):
        setting_key = data.replace("toggle_", "")
        current = settings.get(setting_key, True)
        update_group_setting(chat_id, setting_key, not current)
        
        if setting_key == "delete_biolink":
            await show_biolink_settings(client, callback_query)
        elif setting_key == "delete_abuse":
            await show_abuse_settings(client, callback_query)
        elif setting_key in ["delete_edited", "delete_links_usernames"]:
            await show_message_controls(client, callback_query)
    
    elif data.startswith("change_") and data.endswith("_limit"):
        setting_type = data.split('_')[1]
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("3", callback_data=f"set_{setting_type}_limit_3")],
            [InlineKeyboardButton("4", callback_data=f"set_{setting_type}_limit_4")],
            [InlineKeyboardButton("5", callback_data=f"set_{setting_type}_limit_5")],
            [InlineKeyboardButton("Back", callback_data=f"settings_{setting_type.replace('_warn_limit', '')}")]
        ])
        await callback_query.message.edit_text(f"Select {setting_type.replace('_warn_limit', '')} warning limit:", reply_markup=keyboard)
    
    elif data.startswith("set_") and "_limit_" in data:
        parts = data.split('_')
        setting_type = parts[1]
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
            [InlineKeyboardButton("MUTE", callback_data=f"set_{setting_type}_penalty_mute")],
            [InlineKeyboardButton("BAN", callback_data=f"set_{setting_type}_penalty_ban")],
            [InlineKeyboardButton("Back", callback_data=f"settings_{setting_type.replace('_penalty', '')}")]
        ])
        await callback_query.message.edit_text(f"Select {setting_type.replace('_penalty', '')} penalty:", reply_markup=keyboard)
    
    elif data.startswith("set_") and "_penalty_" in data:
        parts = data.split('_')
        setting_type = parts[1]
        penalty = parts[3]
        
        if setting_type == "biolink":
            update_group_setting(chat_id, "biolink_penalty", penalty)
            await show_biolink_settings(client, callback_query)
        elif setting_type == "abuse":
            update_group_setting(chat_id, "abuse_penalty", penalty)
            await show_abuse_settings(client, callback_query)

    elif data == "close":
        try:
            await callback_query.message.delete()
        except:
            pass

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

    logger.info("Bot starting...")
    client.run()
