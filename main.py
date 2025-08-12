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
from pyrogram.errors import BadRequest, Forbidden, MessageNotModified, FloodWait, PeerIdInvalid
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
LOG_CHANNEL_ID = -1002717243409  # Aapka Log Channel ID
MONGO_DB_URI = os.getenv("MONGO_DB_URI")
ADMIN_USER_IDS = [7315805581]  # Apne Admin User IDs yahan daalein

bot_start_time = datetime.now()
BROADCAST_MESSAGE = {}

# Corrected regex pattern to catch all links and usernames
URL_PATTERN = re.compile(r'\b(?:https?://|www\.|t\.me/|telegra\.ph/)[^\s]+\b|@\w+', re.IGNORECASE)

# --- Tagging variables ---
TAG_MESSAGES = {}
ONGOING_TAGGING_TASKS = {}
EMOJIS = ['😀', '😃', '😄', '😁', '😆', '😅', '🤣', '😂', '🙂', '🙃', '🫠', '😉', '😊', '😇', '🥰', '😍', '🙂', '😘', '😙', '☺️', '🥲', '😋', '😛', '😜', '😝', '🤑', '🤗', '🤭', '🫢', '🫣', '😐', '🤨', '🤔', '🤐', '🫡', '🤥', '🫥', '😮‍💨', '😶‍🌫️', '🙄', '😏', '😒', '🙂‍↕️', '🫨', '🙂‍↕️', '🤥', '😔', '😪', '😴', '🤧', '😷', '🤢', '🤕', '🥶', '🥵', '😵', '🤯', '🤠', '🥳', '🙁', '🥸', '🫤', '🫤', '🤓', '😕', '🧐', '☹️', '😮', '😦', '🥺', '😲', '😳', '😥', '😰', '😧', '😢', '😭', '😱', '😡', '😣', '🥱', '😓', '😫', '😩', '😠', '🤬', '🤡', '👿', '☠️', '💀', '💀', '👺', '👽', '👹', '👾', '👻', '😺', '😸', '😹', '🙈', '😻', '😾', '😽', '😿', '🙀', '💋', '💌', '🙉', '💝', '💖', '💗', '❤️‍🩹', '💕', '❤️‍🔥', '💟', '💔', '❣️', '🧡', '💛', '🩷', '💙', '❤️', '💜', '🤎', '💫', '🩶', '💢', '🤍', '💯', '💣', '💬', '💨', '🗯', '💦', '💭', '💤', '🖕', '🫦', '👄', '👅', '🧠', '👀', '👁', '🦴', '🦷', '🤳', '👶', '🧒', '👦', '🧑', '👱', '👨', '🧔', '🧔‍♀️', '👨‍🦱', '👨‍🦳', '👨‍🦲', '👩‍🦳', '👩‍🦰', '🧑‍🦱', '👩‍🦱', '👩‍🦰', '🧑‍🦰', '🫆', '🫂', '🗣', '👥️', '👤', '🧑‍🧒', '🧑‍🧑‍🧒‍🧒', '🧑‍🧒‍🧒', '🧑‍🧑‍🧒‍🧒']

# --- Game State ---
TICTACTOE_GAMES = {}

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
        db.whitelist.create_index([("chat_id", 1), ("user_id", 1)], unique=True)
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
    """Sends a log message to the predefined LOG_CHANNEL_ID."""
    if not LOG_CHANNEL_ID:
        logger.warning("LOG_CHANNEL_ID is not set, cannot log to channel.")
        return
    
    try:
        await client.send_message(chat_id=LOG_CHANNEL_ID, text=text, parse_mode=parse_mode)
    except Exception as e:
        logger.error(f"Error logging to channel: {e}")

def get_default_feature_config(action="warn", limit=3, penalty="mute"):
    return {"enabled": True, "action": action, "limit": limit, "penalty": penalty}

def get_group_settings(chat_id):
    if db is None:
        return {
            "biolink": get_default_feature_config(),
            "abuse": get_default_feature_config(),
            "edited": {"enabled": True},
            "links_usernames": get_default_feature_config(action="ban"),
        }
    settings = db.settings.find_one({"chat_id": chat_id})
    if not settings:
        default_settings = {
            "chat_id": chat_id,
            "biolink": get_default_feature_config(),
            "abuse": get_default_feature_config(),
            "edited": {"enabled": True},
            "links_usernames": get_default_feature_config(action="ban"),
        }
        db.settings.insert_one(default_settings.copy())
        return default_settings

    # Ensure all keys exist for backward compatibility
    changed = False
    if "biolink" not in settings:
        settings["biolink"] = get_default_feature_config()
        changed = True
    if "abuse" not in settings:
        settings["abuse"] = get_default_feature_config()
        changed = True
    if "edited" not in settings:
        settings["edited"] = {"enabled": True}
        changed = True
    if "links_usernames" not in settings:
        settings["links_usernames"] = get_default_feature_config(action="ban")
        changed = True

    if changed:
        db.settings.update_one({"chat_id": chat_id}, {"$set": settings})
        
    return settings

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

def get_warnings_sync(user_id: int, chat_id: int, feature: str):
    if db is None: return 0
    warnings_doc = db.warnings.find_one({"user_id": user_id, "chat_id": chat_id})
    return warnings_doc.get(f"{feature}_count", 0) if warnings_doc else 0

def increment_warning_sync(chat_id, user_id, feature: str):
    if db is None: return 1
    warnings_doc = db.warnings.find_one_and_update(
        {"chat_id": chat_id, "user_id": user_id},
        {"$inc": {f"{feature}_count": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER
    )
    return warnings_doc.get(f"{feature}_count", 1)

def reset_warnings_sync(chat_id, user_id, feature: str = None):
    if db is None: return
    if feature:
        db.warnings.update_one(
            {"chat_id": chat_id, "user_id": user_id},
            {"$set": {f"{feature}_count": 0}}
        )
    else: # Reset all warnings for the user
        db.warnings.delete_one({"chat_id": chat_id, "user_id": user_id})

async def handle_incident(client: Client, chat_id, user, reason, original_message: Message, config: dict):
    user_mention = user.mention(style="html")

    try:
        await original_message.delete()
        logger.info(f"Deleted '{reason}' message from {user.id} in {chat_id}.")
    except Exception as e:
        logger.error(f"Error deleting message in {chat_id}: {e}.")

    action = config.get("action", "warn")
    
    notification_text = ""
    keyboard = []

    if reason == "edited":
        notification_text = (
            f"<b>📝 Edited Message Deleted!</b>\n\n"
            f"Hey {user_mention}, aapke edited message ko hata diya gaya hai. "
            f"Purane messages ko edit karna niyam ke khilaf hai."
        )
        keyboard.append([InlineKeyboardButton("🗑️ Close", callback_data="close")])

    elif action == "warn":
        limit = config.get("limit", 3)
        penalty = config.get("penalty", "mute")
        count = increment_warning_sync(chat_id, user.id, reason)
        
        notification_text = (
            f"🚨 <b>Warning for {reason.replace('_', ' ').title()}</b> 🚨\n\n"
            f"Hey {user_mention}, aapka message niyam todne ke kaaran hata diya gaya hai.\n"
            f"<b>Warning: {count}/{limit}</b>\n\n"
            f"Limit paar karne par aapko <b>{penalty}</b> kar diya jayega."
        )
        # Add cancel/whitelist buttons for biolink warnings
        if reason == "biolink":
             keyboard.append(
                 [InlineKeyboardButton("❌ Cancel Warning", callback_data=f"cancel_warn_{user.id}_{reason}"),
                  InlineKeyboardButton("✅ Whitelist", callback_data=f"whitelist_{user.id}")]
             )
        keyboard.append([InlineKeyboardButton("🗑️ Close", callback_data="close")])

        if count >= limit:
            try:
                if penalty == "mute":
                    await client.restrict_chat_member(chat_id, user.id, ChatPermissions())
                    punishment_text = f"<b>🔇 {user_mention} ko {limit} warnings ke baad mute kar diya gaya hai.</b>"
                else: # ban
                    await client.ban_chat_member(chat_id, user.id)
                    punishment_text = f"<b>🔨 {user_mention} ko {limit} warnings ke baad ban kar diya gaya hai.</b>"
                
                await client.send_message(chat_id, punishment_text, parse_mode=enums.ParseMode.HTML)
                reset_warnings_sync(chat_id, user.id, reason)

            except errors.ChatAdminRequired:
                logger.error(f"Cannot apply penalty in {chat_id}. Bot needs admin rights.")
                await client.send_message(chat_id, "Penalty nahi de sakta, kripya mujhe admin banayein.")
            except Exception as e:
                logger.error(f"Error applying penalty to {user.id} in {chat_id}: {e}")


    else: # Direct Mute or Ban
        penalty = config.get("action")
        try:
            if penalty == "mute":
                await client.restrict_chat_member(chat_id, user.id, ChatPermissions())
                notification_text = f"<b>🔇 {user_mention} ko '{reason.replace('_', ' ').title()}' ke liye seedhe mute kar diya gaya hai.</b>"
            elif penalty == "ban":
                await client.ban_chat_member(chat_id, user.id)
                notification_text = f"<b>🔨 {user_mention} ko '{reason.replace('_', ' ').title()}' ke liye seedhe ban kar diya gaya hai.</b>"
            
            keyboard.append([InlineKeyboardButton("🗑️ Close", callback_data="close")])
        except errors.ChatAdminRequired:
            logger.error(f"Cannot apply direct penalty in {chat_id}. Bot needs admin rights.")
            await client.send_message(chat_id, "Penalty nahi de sakta, kripya mujhe admin banayein.")
        except Exception as e:
            logger.error(f"Error applying direct penalty to {user.id} in {chat_id}: {e}")

    if notification_text:
        try:
            await client.send_message(
                chat_id=chat_id,
                text=notification_text,
                reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None,
                parse_mode=enums.ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"Error sending incident notification in {chat_id}: {e}.")


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
    elif chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        group_start_message = f"Hello! Main <b>{bot_info.first_name}</b> hun. Group ki settings configure karne ke liye <code>/settings</code> ka istemal karein (sirf admins)."
        await message.reply_text(group_start_message, parse_mode=enums.ParseMode.HTML)


@client.on_message(filters.command("help"))
async def help_handler(client: Client, message: Message):
    help_text = (
        "<b>🛠️ Bot Commands & Usage</b>\n\n"
        "<b>General Moderation:</b>\n"
        "• `/settings` – Sabhi moderation features (Bio, Abuse, Links) ko configure karein.\n"
        "• `/user <user>` – Kisi user ke liye Mute/Ban/Warn/Whitelist karein.\n"
        "• `/lock <msg> @user` – Kisi user ko private message bhejein.\n"
        "• `/free <user>` – Ek user ko sabhi checks se whitelist karein.\n"
        "• `/unfree <user>` – User ko whitelist se hatayein.\n"
        "• `/freelist` – Whitelisted users ki list dekhein.\n\n"
        "<b>Tagging Commands:</b>\n"
        "• `/tagall <msg>`: Sabhi members ko tag karein.\n"
        "• `/onlinetag <msg>`: Sirf online members ko tag karein.\n"
        "• `/admin <msg>`: Sirf group admins ko tag karein.\n"
        "• `/tagstop`: Tagging ko rokein aur messages delete karein.\n\n"
        "<b>Game Command:</b>\n"
        "• `/tictac @p1 @p2`: Tic-Tac-Toe game shuru karein.\n\n"
        "<b>Admin Commands:</b>\n"
        "• `/stats`: Bot ke usage stats dekhein.\n"
        "• `/broadcast`: Sabhi users/groups ko message bhejein.\n"
        "• `/addabuse <word>`: Gaaliyon ki list mein naya shabd jodein."
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🗑️ Close", callback_data="close")]])
    await client.send_message(message.chat.id, help_text, reply_markup=kb, parse_mode=enums.ParseMode.HTML)


# --- NEW SETTINGS MENU ---
@client.on_message(filters.group & filters.command("settings"))
async def settings_command_handler(client: Client, message: Message):
    if not await is_group_admin(message.chat.id, message.from_user.id):
        await message.reply_text("Aap group admin nahi hain, isliye is command ka upyog nahi kar sakte.")
        return
    await show_main_settings_menu(message)

async def show_main_settings_menu(query_or_message):
    chat_id = query_or_message.message.chat.id if isinstance(query_or_message, CallbackQuery) else query_or_message.chat.id
    settings = get_group_settings(chat_id)

    def get_status_emoji(feature_name):
        feature_config = settings.get(feature_name, {})
        return "✅ On" if feature_config.get("enabled", False) else "❌ Off"

    text = "⚙️ <b>Group Moderation Settings</b>\n\nAap yahan se bot ke alag-alag features ko control kar sakte hain."
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"🚨 Bio Link Detection ({get_status_emoji('biolink')})", callback_data="settings_biolink")],
        [InlineKeyboardButton(f"🤬 Abuse Detection ({get_status_emoji('abuse')})", callback_data="settings_abuse")],
        [InlineKeyboardButton(f"📝 Edit Message Detection ({get_status_emoji('edited')})", callback_data="settings_edited")],
        [InlineKeyboardButton(f"🔗 Link/Username Detection ({get_status_emoji('links_usernames')})", callback_data="settings_links_usernames")],
        [InlineKeyboardButton("🗑️ Close", callback_data="close")]
    ])

    try:
        if isinstance(query_or_message, CallbackQuery):
            await query_or_message.message.edit_text(text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)
        else:
            await query_or_message.reply_text(text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)
    except MessageNotModified:
        pass


# --- NEW /USER COMMAND ---
@client.on_message(filters.command("user") & filters.group)
async def user_settings_command(client: Client, message: Message):
    if not await is_group_admin(message.chat.id, message.from_user.id):
        return await message.reply("Aap group admin nahi hain.")

    target = None
    if message.reply_to_message:
        target = message.reply_to_message.from_user
    elif len(message.command) > 1:
        arg = message.command[1]
        try:
            target = await client.get_users(int(arg) if arg.isdigit() else arg)
        except Exception:
            return await message.reply("User nahi mila. Sahi User ID/Username dein ya message reply karein.")
    else:
        return await message.reply("Ek user ko manage karne ke liye, uske message par reply karein ya `/user <id/username>` ka upyog karein.")
    
    if not target:
        return await message.reply("User nahi mila.")
        
    await show_user_settings_menu(message, target.id)

async def show_user_settings_menu(query_or_message, target_id):
    chat_id = query_or_message.message.chat.id if isinstance(query_or_message, CallbackQuery) else query_or_message.chat.id
    
    try:
        target_user = await client.get_users(target_id)
        target_mention = target_user.mention(style="html")
    except Exception:
        target_mention = f"User (`{target_id}`)"

    is_whitelisted = is_whitelisted_sync(chat_id, target_id)
    whitelist_text = "✅ Revoke Full Permissions" if is_whitelisted else "❌ Grant Full Permissions"
    
    text = f"👤 <b>Managing User:</b> {target_mention}\n\nGroup ke is member ke liye action chunein."
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔇 Mute", callback_data=f"user_act_mute_{target_id}")],
        [InlineKeyboardButton("🔨 Ban", callback_data=f"user_act_ban_{target_id}")],
        [InlineKeyboardButton("🚨 Warn", callback_data=f"user_act_warn_{target_id}")],
        [InlineKeyboardButton(whitelist_text, callback_data=f"user_act_toggle_wl_{target_id}")],
        [InlineKeyboardButton("🗑️ Close", callback_data="close")]
    ])

    try:
        if isinstance(query_or_message, CallbackQuery):
            await query_or_message.message.edit_text(text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)
        else:
            await query_or_message.reply(text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)
    except MessageNotModified:
        pass

# --- NEW /LOCK COMMAND ---
@client.on_message(filters.command("lock") & filters.group)
async def lock_message_command(client: Client, message: Message):
    if not await is_group_admin(message.chat.id, message.from_user.id):
        return await message.reply("Aap group admin nahi hain.")

    target_user = None
    lock_text = ""

    if message.reply_to_message:
        target_user = message.reply_to_message.from_user
        lock_text = " ".join(message.command[1:])
        if not lock_text:
           return await message.reply("Kripya reply ke saath lock karne ke liye ek message likhein. Format: `/lock <message>`")
    else:
        if len(message.command) < 3:
            return await message.reply("Format galat hai. Upyog karein: `/lock @username <message>`")
        
        target_username = message.command[1]
        lock_text = " ".join(message.command[2:])
        try:
            target_user = await client.get_users(target_username)
        except Exception:
            return await message.reply(f"`{target_username}` naam ka user nahi mila.")

    if not target_user:
        return await message.reply("Target user nahi mila.")

    try:
        from_user_mention = message.from_user.mention(style="html")
        group_title = message.chat.title
        
        dm_text = (f"🔒 Aapko <b>{group_title}</b> group se <b>{from_user_mention}</b> dwara ek locked message bheja gaya hai:\n\n"
                   f"<blockquote>{lock_text}</blockquote>")
                   
        await client.send_message(target_user.id, dm_text, parse_mode=enums.ParseMode.HTML)
        await message.reply(f"✅ Locked message safaltapoorvak {target_user.mention(style='html')} ko bhej diya gaya hai.")
    except PeerIdInvalid:
        await message.reply(f"❌ Message nahi bhej saka. {target_user.mention(style='html')} ne shayad bot ko block kiya hai ya start nahi kiya hai.")
    except Exception as e:
        await message.reply(f"Ek error aayi: {e}")
        logger.error(f"Error in /lock command: {e}")

    await message.delete()

# --- NEW TICTACTOE GAME ---
@client.on_message(filters.command("tictac") & filters.group)
async def tictactoe_start(client: Client, message: Message):
    chat_id = message.chat.id
    
    if chat_id in TICTACTOE_GAMES:
        return await message.reply("Is group mein pehle se hi ek game chal raha hai.")

    if len(message.command) != 3 or not message.command[1].startswith('@') or not message.command[2].startswith('@'):
        return await message.reply("Game shuru karne ke liye do players ko mention karein. Format: `/tictac @player1 @player2`")

    try:
        player1 = await client.get_users(message.command[1])
        player2 = await client.get_users(message.command[2])
    except Exception:
        return await message.reply("Dono players valid hone chahiye aur group ke member hone chahiye.")
        
    if player1.id == player2.id:
        return await message.reply("Aap khud ke saath nahi khel sakte!")

    game_state = {
        "board": [[" ", " ", " "], [" ", " ", " "], [" ", " ", " "]],
        "players": {player1.id: "❌", player2.id: "⭕"},
        "player_names": {player1.id: player1.mention(style='html'), player2.id: player2.mention(style='html')},
        "current_turn": player1.id,
        "message_id": None,
    }
    TICTACTOE_GAMES[chat_id] = game_state

    board_markup = await generate_tictactoe_board(chat_id)
    turn_mention = game_state["player_names"][player1.id]
    
    sent_message = await message.reply(
        f"**Tic-Tac-Toe (Zero Kuttas)**\n\n{game_state['player_names'][player1.id]} (❌) vs {game_state['player_names'][player2.id]} (⭕)\n\n"
        f" बारी है: {turn_mention} (❌)\n\nKhelne ke liye neeche diye gaye buttons par click karein!",
        reply_markup=board_markup,
        parse_mode=enums.ParseMode.HTML
    )
    TICTACTOE_GAMES[chat_id]["message_id"] = sent_message.id

async def generate_tictactoe_board(chat_id):
    game = TICTACTOE_GAMES.get(chat_id)
    if not game:
        return None
    
    board = game["board"]
    keyboard = []
    for r_idx, row in enumerate(board):
        row_buttons = []
        for c_idx, cell in enumerate(row):
            row_buttons.append(
                InlineKeyboardButton(cell if cell != " " else "·", callback_data=f"tictac_{r_idx}_{c_idx}")
            )
        keyboard.append(row_buttons)
    
    keyboard.append([InlineKeyboardButton("❌ End Game", callback_data="tictac_end")])
    return InlineKeyboardMarkup(keyboard)

def check_tictactoe_winner(board, symbol):
    for i in range(3):
        if all(board[i][j] == symbol for j in range(3)): return True
        if all(board[j][i] == symbol for j in range(3)): return True
    if all(board[i][i] == symbol for i in range(3)): return True
    if all(board[i][2 - i] == symbol for i in range(3)): return True
    return False

def is_tictactoe_draw(board):
    return all(cell != " " for row in board for cell in row)


# --- Original Commands (free, stats, broadcast, etc.) ---
@client.on_message(filters.group & filters.command("free"))
async def command_free(client: Client, message: Message):
    if not await is_group_admin(message.chat.id, message.from_user.id):
        return await message.reply("Aap group admin nahi hain.")

    if message.reply_to_message:
        target = message.reply_to_message.from_user
    elif len(message.command) > 1:
        arg = message.command[1]
        try:
            target = await client.get_users(int(arg) if arg.isdigit() else arg)
        except Exception:
            return await message.reply("User nahi mila.")
    else:
        return await message.reply("User ko whitelist karne ke liye reply karein ya `/free <id/username>` istemal karein.")

    add_whitelist_sync(message.chat.id, target.id)
    reset_warnings_sync(message.chat.id, target.id) # Reset all warnings
    await message.reply(f"✅ {target.mention(style='html')} ko sabhi pabandiyon se chhoot de di gayi hai.")

@client.on_message(filters.group & filters.command("unfree"))
async def command_unfree(client: Client, message: Message):
    if not await is_group_admin(message.chat.id, message.from_user.id):
        return await message.reply("Aap group admin nahi hain.")

    if message.reply_to_message:
        target = message.reply_to_message.from_user
    elif len(message.command) > 1:
        arg = message.command[1]
        try:
            target = await client.get_users(int(arg) if arg.isdigit() else arg)
        except Exception:
            return await message.reply("User nahi mila.")
    else:
        return await message.reply("User ko whitelist se hatane ke liye reply karein ya `/unfree <id/username>` istemal karein.")

    remove_whitelist_sync(message.chat.id, target.id)
    await message.reply(f"❌ {target.mention(style='html')} ko whitelist se hata diya gaya hai.")

@client.on_message(filters.group & filters.command("freelist"))
async def command_freelist(client: Client, message: Message):
    if not await is_group_admin(message.chat.id, message.from_user.id):
        return await message.reply("Aap group admin nahi hain.")

    ids = get_whitelist_sync(message.chat.id)
    if not ids:
        return await message.reply("Is group mein koi whitelisted user nahi hai.")

    text = "<b>📋 Whitelisted Users:</b>\n\n"
    for i, uid in enumerate(ids, start=1):
        try:
            user = await client.get_users(uid)
            text += f"{i}: {user.mention(style='html')} (`{uid}`)\n"
        except:
            text += f"{i}: [User not found] (`{uid}`)\n"
    
    await message.reply(text, parse_mode=enums.ParseMode.HTML)

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
            logger.error(f"Error fetching stats from DB: {e}")
            await message.reply_text(f"Stats fetch karte samay error hui: {e}")
            return

    stats_message = (
        f"📊 <b>Bot Status:</b>\n\n"
        f"• Total Unique Users (via /start in private chat): {total_users}\n"
        f"• Total Groups Managed: {total_groups}\n"
        f"• Uptime: {str(datetime.now() - bot_start_time).split('.')[0]} \n"
        f"• Last Check: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    await message.reply_text(stats_message, parse_mode=enums.ParseMode.HTML)
    logger.info(f"Admin {message.from_user.id} requested stats.")

@client.on_message(filters.command("broadcast") & filters.user(ADMIN_USER_IDS) & filters.private)
async def broadcast_command(client: Client, message: Message) -> None:
    await message.reply_text("📢 Broadcast shuru karne ke liye, kripya apna message bhejein:")
    BROADCAST_MESSAGE[message.from_user.id] = "waiting_for_message"
    logger.info(f"Admin {message.from_user.id} initiated broadcast.")

@client.on_message(filters.private & filters.user(ADMIN_USER_IDS) & ~filters.command([]))
async def handle_broadcast_message(client: Client, message: Message) -> None:
    user_id = message.from_user.id
    if BROADCAST_MESSAGE.get(user_id) != "waiting_for_message":
        return

    BROADCAST_MESSAGE[user_id] = message
    keyboard = [
        [InlineKeyboardButton("✅ Yes, Broadcast Now", callback_data="confirm_broadcast")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_broadcast")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text("Kya aap is message ko sabhi groups aur users ko bhejna chahte hain?", reply_markup=reply_markup)

@client.on_message(filters.command("addabuse") & filters.user(ADMIN_USER_IDS))
async def add_abuse_word(client: Client, message: Message) -> None:
    if len(message.command) < 2:
        await message.reply_text("Kripya woh shabd dein jise aap add karna chahte hain. Upyog: <code>/addabuse &lt;shabd&gt;</code>", parse_mode=enums.ParseMode.HTML)
        return
    word_to_add = " ".join(message.command[1:]).lower().strip()
    if not word_to_add:
        await message.reply_text("Kripya ek valid shabd dein.")
        return
    if profanity_filter is not None:
        if await profanity_filter.add_bad_word(word_to_add):
            await message.reply_text(f"✅ Shabd <code>{word_to_add}</code> safaltapoorvak jod diya gaya hai.", parse_mode=enums.ParseMode.HTML)
        else:
            await message.reply_text(f"Shabd <code>{word_to_add}</code> pehle se hi list mein maujood hai.", parse_mode=enums.ParseMode.HTML)
    else:
        await message.reply_text("Profanity filter initialize nahi hua hai. MongoDB connection mein problem ho sakti hai.")


# --- Core Message Handlers (Updated for new settings) ---
@client.on_message(filters.group & ~filters.service & ~filters.via_bot & ~filters.command([
    "start", "help", "settings", "user", "lock", "tictac", "free", "unfree", 
    "freelist", "stats", "broadcast", "addabuse", "tagall", "onlinetag", 
    "admin", "tagstop", "checkperms"
]))
async def main_message_handler(client: Client, message: Message):
    if not message.from_user: return
    
    user = message.from_user
    chat_id = message.chat.id
    
    if await is_group_admin(chat_id, user.id) or is_whitelisted_sync(chat_id, user.id):
        return

    settings = get_group_settings(chat_id)

    # 1. Abuse Check
    if settings["abuse"].get("enabled") and message.text and profanity_filter.contains_profanity(message.text):
        await handle_incident(client, chat_id, user, "abuse", message, settings["abuse"])
        return

    # 2. Links/Usernames Check
    if settings["links_usernames"].get("enabled") and message.text and URL_PATTERN.search(message.text):
        await handle_incident(client, chat_id, user, "links_usernames", message, settings["links_usernames"])
        return

    # 3. Bio Link Check
    if settings["biolink"].get("enabled"):
        try:
            # This check can be resource-intensive. Run it only if other checks pass.
            user_info = await client.get_chat(user.id)
            if user_info.bio and URL_PATTERN.search(user_info.bio):
                await handle_incident(client, chat_id, user, "biolink", message, settings["biolink"])
                return
        except Exception:
            pass # Ignore if we can't get user info

@client.on_edited_message(filters.group & filters.text & ~filters.via_bot)
async def edited_message_handler(client: Client, message: Message):
    if not message.from_user: return
    
    user = message.from_user
    chat_id = message.chat.id
    
    if await is_group_admin(chat_id, user.id) or is_whitelisted_sync(chat_id, user.id):
        return
        
    settings = get_group_settings(chat_id)
    if settings["edited"].get("enabled"):
        await handle_incident(client, chat_id, user, "edited", message, {})

@client.on_message(filters.new_chat_members)
async def new_member_handler(client: Client, message: Message):
    chat_id = message.chat.id
    bot_info = await client.get_me()
    
    for new_member in message.new_chat_members:
        # Bot join logic
        if new_member.id == bot_info.id:
            await message.reply_text(f"Namaste! Is group mein moderation ke liye taiyar hun. Settings ke liye `/settings` ka upyog karein (sirf admins).")
            if db is not None: db.groups.update_one({"chat_id": chat_id}, {"$set": {"title": message.chat.title, "last_active": datetime.now()}}, upsert=True)
            continue

        # Human member join logic
        log_to_channel(f"<b>🆕 New Member Joined:</b>\nGroup: {message.chat.title} (`{chat_id}`)\nUser: {new_member.mention(style='html')} (`{new_member.id}`)")
        
        if await is_group_admin(chat_id, new_member.id) or is_whitelisted_sync(chat_id, new_member.id):
            continue

        settings = get_group_settings(chat_id)
        if settings["biolink"].get("enabled"):
            try:
                user_info = await client.get_chat(new_member.id)
                if user_info.bio and URL_PATTERN.search(user_info.bio):
                    temp_msg = await client.send_message(chat_id, f"Checking {new_member.mention(style='html')}...", disable_notification=True)
                    await handle_incident(client, chat_id, new_member, "biolink", temp_msg, settings["biolink"])
            except Exception as e:
                logger.error(f"Error checking bio for new member {new_member.id}: {e}")

@client.on_message(filters.left_chat_member)
async def left_member_handler(client: Client, message: Message):
    if message.left_chat_member.id == client.me.id:
        if db is not None: db.groups.delete_one({"chat_id": message.chat.id})
        log_to_channel(f"<b>❌ Bot Left Group:</b>\nGroup: {message.chat.title} (`{message.chat.id}`)")
    else:
        log_to_channel(f"<b>➡️ Member Left:</b>\nGroup: {message.chat.title} (`{message.chat.id}`)\nUser: {message.left_chat_member.mention(style='html')} (`{message.left_chat_member.id}`)")

# --- Tagging Commands (from original code) ---
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

                    sent_message = await message.reply_text(final_message, parse_mode=enums.ParseMode.HTML, disable_web_page_preview=True)
                    tag_messages_to_delete.append(sent_message.id)
                    await asyncio.sleep(4)
                
                TAG_MESSAGES[chat_id] = tag_messages_to_delete
                ONGOING_TAGGING_TASKS.pop(chat_id, None)

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

    except Exception as e:
        logger.error(f"Error in /tagall command: {e}")
        await message.reply_text(f"टैग करते समय error हुई: {e}")
        if chat_id in ONGOING_TAGGING_TASKS: ONGOING_TAGGING_TASKS.pop(chat_id)

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
                    if chat_id not in ONGOING_TAGGING_TASKS: return
                    chunk = online_members_to_tag[i:i + chunk_size]
                    final_message = " ".join(chunk)
                    if message_text: final_message += f"\n\n{message_text}"
                    sent_message = await message.reply_text(final_message, parse_mode=enums.ParseMode.HTML, disable_web_page_preview=True)
                    tag_messages_to_delete.append(sent_message.id)
                    await asyncio.sleep(4)
                TAG_MESSAGES[chat_id] = tag_messages_to_delete
                ONGOING_TAGGING_TASKS.pop(chat_id, None)
            except Exception as e:
                logger.error(f"Error during online tagging task: {e}")
            finally:
                if chat_id in ONGOING_TAGGING_TASKS: ONGOING_TAGGING_TASKS.pop(chat_id)
        
        task = asyncio.create_task(online_tag_task())
        ONGOING_TAGGING_TASKS[chat_id] = task
    except Exception as e:
        logger.error(f"Error in /onlinetag command: {e}")
        await message.reply_text(f"टैग करते समय error हुई: {e}")
        if chat_id in ONGOING_TAGGING_TASKS: ONGOING_TAGGING_TASKS.pop(chat_id)

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
        tagged_admins = [f"👑 {admin.user.mention(style='html')}" for admin in admins if not admin.user.is_bot]
        if not tagged_admins:
            await message.reply_text("Is group mein koi admins nahi hain jinhe tag kiya ja sake.", parse_mode=enums.ParseMode.HTML)
            return
        tag_message_text = " ".join(tagged_admins)
        if chat_id not in TAG_MESSAGES: TAG_MESSAGES[chat_id] = []
        sent_message = await message.reply_text(f"{tag_message_text}\n\n<b>Message:</b> {message_text}", parse_mode=enums.ParseMode.HTML, disable_web_page_preview=True)
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
        task = ONGOING_TAGGING_TASKS.pop(chat_id)
        task.cancel()
        await message.reply_text("टैगिंग प्रक्रिया बंद कर दी गई है।")
        logger.info(f"Admin {message.from_user.id} stopped ongoing tagging in chat {chat_id}.")

    if TAG_MESSAGES.get(chat_id):
        try:
            await client.delete_messages(chat_id, TAG_MESSAGES.pop(chat_id))
            await message.reply_text("पिछली टैगिंग के सारे मैसेज डिलीट कर दिए गए हैं।")
        except Exception as e:
            logger.error(f"Error in /tagstop command deleting messages: {e}")


# --- Callback Query Handler (Massively Updated) ---
@client.on_callback_query()
async def callback_query_handler(client: Client, query: CallbackQuery):
    data = query.data
    user_id = query.from_user.id
    message = query.message
    chat_id = message.chat.id

    # --- TicTacToe Logic ---
    if data.startswith("tictac_"):
        game = TICTACTOE_GAMES.get(chat_id)
        if not game: return await query.answer("Yeh game ab active nahi hai.", show_alert=True)
        
        is_q_admin = await is_group_admin(chat_id, user_id)
        
        if data == "tictac_end":
            if user_id in game["players"] or is_q_admin:
                del TICTACTOE_GAMES[chat_id]
                await message.edit_text("Game admin ya player dwara band kar diya gaya hai.")
            else:
                await query.answer("Aap is game ke player nahi hain.", show_alert=True)
            return

        if user_id != game["current_turn"]: return await query.answer("Yeh aapki bari nahi hai!", show_alert=True)

        _, r_str, c_str = data.split("_")
        r, c = int(r_str), int(c_str)

        if game["board"][r][c] != " ": return await query.answer("Yeh jagah pehle se hi bhari hui hai.", show_alert=True)
        
        symbol = game["players"][user_id]
        game["board"][r][c] = symbol
        
        if check_tictactoe_winner(game["board"], symbol):
            winner_mention = game["player_names"][user_id]
            end_text = f"**Game Over!**\n\n🏆 Winner hai: **{winner_mention}**! 🎉"
            await message.edit_text(end_text, reply_markup=await generate_tictactoe_board(chat_id), parse_mode=enums.ParseMode.HTML)
            del TICTACTOE_GAMES[chat_id]
        elif is_tictactoe_draw(game["board"]):
            end_text = "**Game Over!**\n\nGame draw ho gaya! 🤝"
            await message.edit_text(end_text, reply_markup=await generate_tictactoe_board(chat_id))
            del TICTACTOE_GAMES[chat_id]
        else:
            game["current_turn"] = next(p for p in game["players"] if p != user_id)
            turn_mention = game["player_names"][game["current_turn"]]
            turn_symbol = game["players"][game["current_turn"]]
            
            p1_id, p2_id = game["players"].keys()
            new_text = (f"**Tic-Tac-Toe (Zero Kuttas)**\n\n{game['player_names'][p1_id]} (❌) vs {game['player_names'][p2_id]} (⭕)\n\n"
                        f" बारी है: {turn_mention} ({turn_symbol})\n\nKhelne ke liye neeche diye gaye buttons par click karein!")
            await message.edit_text(new_text, reply_markup=await generate_tictactoe_board(chat_id), parse_mode=enums.ParseMode.HTML)
        return await query.answer()

    # --- General & Settings Logic ---
    is_q_admin = await is_group_admin(chat_id, user_id) if message.chat.type != enums.ChatType.PRIVATE else is_admin(user_id)
    
    if data == "close":
        if is_q_admin:
            try: await message.delete()
            except: pass
        else:
            await query.answer("Sirf admins hi is message ko band kar sakte hain.", show_alert=True)
        return

    # --- Private Chat Callbacks (from original code) ---
    if message.chat.type == enums.ChatType.PRIVATE:
        if data == "help_menu":
            help_text = "..." # Your private help menu text
            keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="back_to_main_menu")]]
            await message.edit_text(help_text, reply_markup=InlineKeyboardMarkup(keyboard))
        elif data == "other_bots":
            bots_text = "..." # Your other bots text
            keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="back_to_main_menu")]]
            await message.edit_text(bots_text, reply_markup=InlineKeyboardMarkup(keyboard))
        elif data == "donate_info":
            donate_text = "..." # Your donate text
            keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data="back_to_main_menu")]]
            await message.edit_text(donate_text, reply_markup=InlineKeyboardMarkup(keyboard))
        elif data == "back_to_main_menu":
            await start(client, message) # Reuse start function to show main menu
        elif data == "confirm_broadcast":
            # Your broadcast confirmation logic from original code
            pass
        elif data == "cancel_broadcast":
            await query.message.edit_text("Broadcast cancelled.")
            if BROADCAST_MESSAGE.get(user_id): BROADCAST_MESSAGE.pop(user_id)
        return await query.answer()

    # --- Group Admin Only Callbacks ---
    if not is_q_admin:
        return await query.answer("Aapke paas is action ko karne ki permission nahi hai.", show_alert=True)

    await query.answer() # Acknowledge the callback

    # Main Settings Navigation
    if data == "settings_main":
        await show_main_settings_menu(query)

    elif data.startswith("settings_"):
        feature = data.split("settings_")[1]
        settings = get_group_settings(chat_id)
        config = settings.get(feature, {})
        
        status = "✅ On" if config.get("enabled", False) else "❌ Off"
        
        if feature == "edited":
            text = f"⚙️ **Edit Message Detection**\n\nYeh non-admins dwara edit messages ko delete karta hai."
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(f"Status: {status}", callback_data=f"set_{feature}_toggle")], [InlineKeyboardButton("⬅️ Back", callback_data="settings_main")]])
        else:
            action = config.get("action", "warn")
            limit = config.get("limit", 3)
            penalty = config.get("penalty", "mute")
            
            text = f"⚙️ **{feature.replace('_', ' ').title()} Settings**\n\n`Status:` {status.strip()}\n`Action:` {action.title()}"
            if action == 'warn': text += f"\n`Warn Limit:` {limit}\n`Penalty:` {penalty.title()}"

            kb = [[InlineKeyboardButton(f"Toggle Status", callback_data=f"set_{feature}_toggle")],
                  [InlineKeyboardButton(f"Warn {'✅' if action == 'warn' else ''}", callback_data=f"set_{feature}_action_warn"),
                   InlineKeyboardButton(f"Mute {'✅' if action == 'mute' else ''}", callback_data=f"set_{feature}_action_mute"),
                   InlineKeyboardButton(f"Ban {'✅' if action == 'ban' else ''}", callback_data=f"set_{feature}_action_ban")]]
            if action == 'warn':
                kb.append([InlineKeyboardButton(f"Warn Limit: {limit}", callback_data=f"set_{feature}_limit")])
                kb.append([InlineKeyboardButton(f"Penalty: Mute {'✅' if penalty == 'mute' else ''}", callback_data=f"set_{feature}_penalty_mute"),
                           InlineKeyboardButton(f"Penalty: Ban {'✅' if penalty == 'ban' else ''}", callback_data=f"set_{feature}_penalty_ban")])
            kb.append([InlineKeyboardButton("⬅️ Back", callback_data="settings_main")])
            keyboard = InlineKeyboardMarkup(kb)
        try: await message.edit_text(text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)
        except MessageNotModified: pass

    elif data.startswith("set_"):
        parts = data.split('_'); feature, key = parts[1], parts[2]; value = parts[3] if len(parts) > 3 else None
        settings = get_group_settings(chat_id)
        
        if key == "toggle": update_group_setting(chat_id, f"{feature}.enabled", not settings[feature].get("enabled", False))
        elif key == "action": update_group_setting(chat_id, f"{feature}.action", value)
        elif key == "penalty": update_group_setting(chat_id, f"{feature}.penalty", value)
        elif key == "limit":
             kb = [[InlineKeyboardButton(f"{n} {'✅' if settings[feature].get('limit') == n else ''}", callback_data=f"set_{feature}_setlimit_{n}") for n in [3, 5, 10]],
                   [InlineKeyboardButton("⬅️ Back", callback_data=f"settings_{feature}")]]
             try: await message.edit_text("Warning limit chunein:", reply_markup=InlineKeyboardMarkup(kb))
             except MessageNotModified: pass
             return
        elif key == "setlimit": update_group_setting(chat_id, f"{feature}.limit", int(value))
        
        query.data = f"settings_{feature}" # Redraw the feature menu
        await callback_query_handler(client, query)

    # User Actions from /user command
    elif data.startswith("user_act_"):
        _, action, target_id_str = data.split("_", 2)
        target_id = int(target_id_str)
        target_mention = (await client.get_users(target_id)).mention(style='html')
        
        if action == "toggle_wl":
            if is_whitelisted_sync(chat_id, target_id): remove_whitelist_sync(chat_id, target_id); await query.answer("User ko whitelist se hata diya gaya hai.")
            else: add_whitelist_sync(chat_id, target_id); await query.answer("User ko full permissions de di gayi hain.")
            await show_user_settings_menu(query, target_id)
        elif action == "warn":
            count = increment_warning_sync(chat_id, target_id, "manual")
            await client.send_message(chat_id, f"{query.from_user.mention(style='html')} ne {target_mention} ko chetavni di hai. Kul warnings: {count}.")
            await message.delete()
        elif action == "ban":
            try: await client.ban_chat_member(chat_id, target_id); await message.edit_text(f"✅ {target_mention} ko safaltapoorvak ban kar diya gaya hai.", parse_mode=enums.ParseMode.HTML)
            except Exception as e: await message.edit_text(f"Error: {e}")
        elif action == "mute":
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("30 Min", callback_data=f"user_mute_{target_id}_30m"), InlineKeyboardButton("1 Ghanta", callback_data=f"user_mute_{target_id}_1h")],
                [InlineKeyboardButton("1 Din", callback_data=f"user_mute_{target_id}_24h"), InlineKeyboardButton("Hamesha", callback_data=f"user_mute_{target_id}_perm")],
                [InlineKeyboardButton("⬅️ Back", callback_data=f"user_back_{target_id}")]])
            await message.edit_text("Kitni der ke liye mute karna hai?", reply_markup=kb)

    elif data.startswith("user_mute_"):
        _, _, target_id_str, duration = data.split("_")
        target_id = int(target_id_str)
        target_mention = (await client.get_users(target_id)).mention(style='html')
        until_date = None
        if duration != "perm":
            value = int(duration[:-1]); unit = duration[-1]
            if unit == 'm': until_date = datetime.now() + timedelta(minutes=value)
            elif unit == 'h': until_date = datetime.now() + timedelta(hours=value)
        try:
            await client.restrict_chat_member(chat_id, target_id, ChatPermissions(), until_date=until_date)
            await message.edit_text(f"✅ {target_mention} ko safaltapoorvak mute kar diya gaya hai.", parse_mode=enums.ParseMode.HTML)
        except Exception as e: await message.edit_text(f"Error: {e}")
            
    elif data.startswith("user_back_"):
        await show_user_settings_menu(query, int(data.split('_')[2]))

    # Original Callbacks for incident messages
    elif data.startswith("cancel_warn_"):
        _, _, target_id_str, feature = data.split("_")
        target_id = int(target_id_str)
        reset_warnings_sync(chat_id, target_id, feature)
        target_mention = (await client.get_users(target_id)).mention(style='html')
        await message.edit_text(f"✅ {target_mention} ke liye warning cancel kar di gayi hai.", parse_mode=enums.ParseMode.HTML)

    elif data.startswith("whitelist_"):
        target_id = int(data.split("_")[1])
        add_whitelist_sync(chat_id, target_id)
        reset_warnings_sync(chat_id, target_id)
        target_mention = (await client.get_users(target_id)).mention(style='html')
        await message.edit_text(f"✅ {target_mention} ko whitelist kar diya gaya hai!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🚫 Unwhitelist", callback_data=f"unwhitelist_{target_id}"), InlineKeyboardButton("🗑️ Close", callback_data="close")]]), parse_mode=enums.ParseMode.HTML)

    elif data.startswith("unwhitelist_"):
        target_id = int(data.split("_")[1])
        remove_whitelist_sync(chat_id, target_id)
        target_mention = (await client.get_users(target_id)).mention(style='html')
        await message.edit_text(f"❌ {target_mention} ko whitelist se hata diya gaya hai.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Whitelist", callback_data=f"whitelist_{target_id}"), InlineKeyboardButton("🗑️ Close", callback_data="close")]]), parse_mode=enums.ParseMode.HTML)


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

    # Set commands for the bot
    async def set_bot_commands():
        await client.start()
        await client.set_bot_commands([
            BotCommand("start", "Bot ko start karein"),
            BotCommand("help", "Commands ki jaankari"),
            BotCommand("settings", "Group ki settings configure karein"),
            BotCommand("user", "User ko manage karein"),
            BotCommand("lock", "User ko private message bhejein"),
            BotCommand("tictac", "Tic-Tac-Toe game shuru karein"),
            BotCommand("tagall", "Sabhi members ko tag karein"),
            BotCommand("onlinetag", "Online members ko tag karein"),
            BotCommand("admin", "Admins ko tag karein"),
            BotCommand("tagstop", "Tagging rokein")
        ])
        await client.stop()

    # It's better to run this once separately or handle it carefully
    # loop = asyncio.get_event_loop()
    # loop.run_until_complete(set_bot_commands())

    flask_thread = threading.Thread(target=run_flask_app)
    flask_thread.daemon = True
    flask_thread.start()

    logger.info("Bot is starting...")
    client.run()
    logger.info("Bot stopped")
