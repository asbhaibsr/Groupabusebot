import os
import time
from datetime import datetime, timedelta
import threading
import asyncio
import logging
import re
from pymongo import MongoClient
from pyrogram import Client, filters, enums
from pyrogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    ChatPermissions, BotCommand
)
from pyrogram.errors import BadRequest, Forbidden

from flask import Flask, request, jsonify

# Custom module import
# Ensure this file (profanity_filter.py) is present in your deployment
# NOTE: You will need to install tgcrypto for better performance:
# pip install tgcrypto
from profanity_filter import ProfanityFilter

# --- Configuration ---
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
LOG_CHANNEL_ID = -1002352329534
CASE_CHANNEL_ID = -1002717243409
CASE_CHANNEL_USERNAME = "AbusersDetector"
MONGO_DB_URI = os.getenv("MONGO_DB_URI")
ADMIN_USER_IDS = [7315805581]

bot_start_time = datetime.now()
BROADCAST_MESSAGE = {}
URL_PATTERN = re.compile(r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+')
TAG_EMOJIS = ["🎉", "✨", "💫", "🌟", "🎈", "🎊", "🔥", "💖", "⚡️", "🌈"]
TAG_MESSAGES = {}

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
        logger.error("MONGO_DB_URI environment variable is not set. Cannot connect to MongoDB. Profanity filter will use default list.")
        profanity_filter = ProfanityFilter(mongo_uri=None)
        return

    try:
        mongo_client = MongoClient(MONGO_DB_URI)
        db = mongo_client.get_database("asfilter")

        try:
            collection_names = db.list_collection_names()
        except AttributeError:
            collection_names = db.list_collections_names()

        if "groups" not in collection_names:
            db.create_collection("groups")
        db.groups.create_index("chat_id", unique=True)

        if "users" not in collection_names:
            db.create_collection("users")
        db.users.create_index("user_id", unique=True)
        
        if "incidents" not in collection_names:
            db.create_collection("incidents")
        db.incidents.create_index("case_id", unique=True)
        
        if "biolink_exceptions" not in collection_names:
            db.create_collection("biolink_exceptions")
        db.biolink_exceptions.create_index("user_id", unique=True)
        
        if "warnings" not in collection_names:
            db.create_collection("warnings")
        db.warnings.create_index([("user_id", 1), ("chat_id", 1)], unique=True)
        
        profanity_filter = ProfanityFilter(mongo_uri=MONGO_DB_URI)
        logger.info("MongoDB connection and collections initialized successfully. Profanity filter is ready.")
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB or initialize collections: {e}. Profanity filter will use default list.")
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
        # Handle different Pyrogram versions' ChatMemberStatus representation
        if isinstance(member.status, enums.ChatMemberStatus):
            return member.status in [enums.ChatMemberStatus.CREATOR, enums.ChatMemberStatus.ADMINISTRATOR]
        else:
            # Fallback for older Pyrogram versions
            return member.status in ["creator", "administrator"]
    except (BadRequest, Forbidden):
        return False
    except Exception as e:
        logger.error(f"Error checking admin status for user {user_id} in chat {chat_id}: {e}")
        return False

async def log_to_channel(text: str, parse_mode: enums.ParseMode = None) -> None:
    """Sends a log message to the predefined LOG_CHANNEL_ID."""
    if LOG_CHANNEL_ID is not None:
        try:
            await client.send_message(chat_id=LOG_CHANNEL_ID, text=text, parse_mode=parse_mode)
        except Exception as e:
            logger.error(f"Error logging to channel {LOG_CHANNEL_ID}: {e}")
    else:
        logger.warning("LOG_CHANNEL_ID is not set, cannot log to channel.")

async def handle_incident(client: Client, chat_id, user, reason, original_message: Message, case_type, case_id=None):
    """Common function to handle all incidents (abuse, bio link, edited message)."""
    original_message_id = original_message.id
    message_text = original_message.text or "No text content"
    if not case_id:
        case_id = str(int(datetime.now().timestamp() * 1000))

    try:
        await client.delete_messages(chat_id=chat_id, message_ids=original_message_id)
        logger.info(f"Deleted {reason} message from {user.username or user.full_name} ({user.id}) in {chat_id}.")
    except Exception as e:
        logger.error(f"Error deleting message in {chat_id}: {e}. Make sure the bot has 'Delete Messages' admin permission.")

    sent_details_msg = None
    forwarded_message_id = None
    case_detail_url = f"https://t.me/{CASE_CHANNEL_USERNAME}"

    try:
        details_message_text = (
            f"🚨 <b>नया उल्लंघन ({case_type.upper()})</b> 🚨\n\n"
            f"<b>📍 ग्रुप:</b> {original_message.chat.title} (<code>{chat_id}</code>)\n"
            f"<b>👤 यूज़र:</b> {user.mention} (<code>{user.id}</code>)\n"
            f"<b>📝 यूज़रनेम:</b> @{user.username if user.username else 'N/A'}\n"
            f"<b>⏰ समय:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}\n"
            f"<b>🆔 केस ID:</b> <code>{case_id}</code>\n\n"
            f"<b>➡️ कारण:</b> {reason}\n"
            f"<b>➡️ मूल मैसेज:</b> ||{message_text}||\n"
        )
        sent_details_msg = await client.send_message(
            chat_id=CASE_CHANNEL_ID,
            text=details_message_text,
            parse_mode=enums.ParseMode.HTML
        )
        forwarded_message_id = sent_details_msg.id

        if sent_details_msg:
            channel_link_id = str(CASE_CHANNEL_ID).replace('-100', '')
            case_detail_url = f"https://t.me/c/{channel_link_id}/{sent_details_msg.id}"
            logger.info(f"Incident content sent to case channel with spoiler. URL: {case_detail_url}")

    except Exception as e:
        logger.error(f"Error sending incident details to case channel: {e}")

    if db is not None and db.incidents is not None:
        try:
            db.incidents.insert_one({
                "case_id": case_id,
                "user_id": user.id,
                "user_name": user.full_name,
                "user_username": user.username,
                "chat_id": chat_id,
                "chat_title": original_message.chat.title,
                "original_message_id": original_message_id,
                "abusive_content": message_text,
                "timestamp": datetime.now(),
                "status": "pending_review",
                "case_channel_message_id": forwarded_message_id,
                "reason": reason
            })
            logger.info(f"Incident {case_id} logged in DB.")
        except Exception as e:
            logger.error(f"Error logging incident {case_id} to DB: {e}")

    notification_message = (
        f"🚨 <b>Group mein Niyam Ulanghan!</b>\n\n"
        f"➡️ <b>User:</b> {user.mention}\n"
        f"➡️ <b>Reason:</b> \"{reason} ki wajah se message hata diya gaya hai।\"\n\n"
        f"➡️ <b>Case ID:</b> <code>{case_id}</code>"
    )

    keyboard = [
        [
            InlineKeyboardButton("👤 User Profile", url=f"tg://user?id={user.id}"),
            InlineKeyboardButton("🔧 Admin Actions", callback_data=f"admin_actions_menu_{user.id}_{chat_id}")
        ],
        [
            InlineKeyboardButton("📄 View Case Details", url=case_detail_url)
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await client.send_message(
            chat_id=chat_id,
            text=notification_message,
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML
        )
        logger.info(f"Incident notification sent for user {user.id} in chat {chat_id}.")
    except Exception as e:
        logger.error(f"Error sending notification in chat {chat_id}: {e}. Make sure bot has 'Post Messages' permission.")
        try:
            await client.send_message(
                chat_id=chat_id,
                text=f"User {user.id} ka message hata diya gaya hai. Karan: {reason}",
                parse_mode=enums.ParseMode.HTML
            )
        except Exception as simple_e:
            logger.error(f"Couldn't send even simple notification in chat {chat_id}: {simple_e}")

# --- Bot Commands Handlers ---
@client.on_message(filters.command("start"))
async def start(client: Client, message: Message) -> None:
    user = message.from_user
    chat = message.chat
    bot_info = await client.get_me()
    bot_name = bot_info.first_name
    bot_username = bot_info.username

    if chat.type == enums.ChatType.PRIVATE:
        welcome_message = (
            f"👋 <b>Namaste {user.first_name}!</b>\n\n"
            f"Mai <b>{bot_name}</b> hun, aapka group moderator bot. "
            f"Mai aapke groups ko saaf suthra rakhne mein madad karta hun, "
            f"gaaliyon wale messages ko delete karta hun aur zaroorat padne par warning bhi deta hun.\n\n"
            f"<b>Mere features:</b>\n"
            f"• Gaali detection aur deletion\n"
            f"• User warnings aur actions (Mute, Ban, Kick)\n"
            f"• Incident logging\n\n"
            f"Agar aapko koi madad chahiye, toh niche diye gaye buttons ka upyog karein."
        )
        keyboard = [
            [InlineKeyboardButton("❓ Help", callback_data="help_menu"), InlineKeyboardButton("🤖 Other Bots", callback_data="other_bots")],
            [InlineKeyboardButton("📢 Update Channel", url="https://t.me/asbhai_bsr"), InlineKeyboardButton("💖 Donate", callback_data="donate_info")],
            [InlineKeyboardButton("📈 **Promotion**", url="https://t.me/asprmotion")]
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
            f"User: {user.mention} (<code>{user.id}</code>)\n"
            f"Username: @{user.username if user.username else 'N/A'}\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}"
        )
        await log_to_channel(log_message, parse_mode=enums.ParseMode.HTML)

    elif chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP]:
        try:
            bot_member = await client.get_chat_member(chat.id, bot_info.id)
            add_to_group_url = f"https://t.me/{bot_username}?startgroup=true"
            
            if await is_group_admin(chat.id, bot_info.id):
                group_start_message = f"Hello! Main <b>{bot_name}</b> hun, aapka group moderation bot. Main aapke group ko saaf suthra rakhne mein madad karunga."
            else:
                group_start_message = f"Hello! Main <b>{bot_name}</b> hun. Is group mein moderation ke liye, kripya mujhe <b>admin</b> banayein aur <b>'Delete Messages'</b>, <b>'Restrict Users'</b>, <b>'Post Messages'</b> ki permissions dein."
            
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
                        {"$set": {"title": chat.title, "type": chat.type, "last_active": datetime.now()}},
                        upsert=True
                    )
                except Exception as e:
                    logger.error(f"Error saving group {chat.id} to DB: {e}")
        except Exception as e:
            logger.error(f"Error handling start in group: {e}")


@client.on_message(filters.command("stats") & filters.user(ADMIN_USER_IDS))
async def stats(client: Client, message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.reply_text("Aapke paas is command ko use karne ki permission nahi hai.")
        return

    total_groups = 0
    total_users = 0
    total_incidents = 0
    if db is not None:
        try:
            if db.groups is not None:
                total_groups = db.groups.count_documents({})
            if db.users is not None:
                total_users = db.users.count_documents({})
            if db.incidents is not None:
                total_incidents = db.incidents.count_documents({})
        except Exception as e:
            logger.error(f"Error fetching stats from DB: {e}")
            await message.reply_text(f"Stats fetch karte samay error hui: {e}")
            return

    stats_message = (
        f"📊 <b>Bot Status:</b>\n\n"
        f"• Total Unique Users (via /start in private chat): {total_users}\n"
        f"• Total Groups Managed: {total_groups}\n"
        f"• Total Incidents Logged: {total_incidents}\n"
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

async def confirm_broadcast(client: Client, query: CallbackQuery) -> None:
    await query.answer()
    user_id = query.from_user.id

    if not is_admin(user_id) or BROADCAST_MESSAGE.get(user_id) is None:
        await query.edit_message_text("Invalid action or broadcast message not found.")
        return

    broadcast_msg = BROADCAST_MESSAGE.pop(user_id)
    if broadcast_msg and broadcast_msg != "waiting_for_message":
        if db is None:
            await query.edit_message_text("Broadcast ke liye MongoDB collections available nahi hai. Broadcast nahi kar sakte.")
            logger.error("MongoDB collections not available for broadcast.")
            return

        target_chats = []
        
        group_ids = []
        try:
            if db.groups is not None:
                for doc in db.groups.find({}, {"chat_id": 1}):
                    group_ids.append(doc['chat_id'])
        except Exception as e:
            logger.error(f"Error fetching group IDs from DB for broadcast: {e}")
            group_ids = []

        user_ids = []
        try:
            if db.users is not None:
                for doc in db.users.find({}, {"user_id": 1}):
                    if doc['user_id'] != user_id: 
                        user_ids.append(doc['user_id'])
        except Exception as e:
            logger.error(f"Error fetching user IDs from DB for broadcast: {e}")
            user_ids = []
        
        target_chats.extend(group_ids)
        target_chats.extend(user_ids)

        if not target_chats:
            await query.edit_message_text("Broadcast ke liye koi target group/user IDs database mein nahi mile. Kripya ensure karein bot groups mein added hai aur users ne bot ko start kiya hai.")
            logger.warning(f"Admin {user_id} tried to broadcast but no target chat IDs found in DB.")
            return

        success_count = 0
        fail_count = 0
        
        await query.edit_message_text(f"📢 Broadcast shuru ho raha hai...\n\nTotal targets: {len(target_chats)}")

        for chat_id in target_chats:
            try:
                await client.copy_message(
                    chat_id=chat_id,
                    from_chat_id=broadcast_msg.chat.id,
                    message_id=broadcast_msg.id
                )
                success_count += 1
                await asyncio.sleep(0.1)
            except Forbidden:
                logger.warning(f"Broadcast failed to {chat_id} (Forbidden: Bot was blocked by user or kicked from group).")
                fail_count += 1
            except BadRequest as e:
                logger.warning(f"Broadcast failed to {chat_id} (BadRequest: {e}).")
                fail_count += 1
            except Exception as e:
                logger.error(f"Failed to broadcast to {chat_id} (Unknown error: {e}).")
                fail_count += 1

        await query.message.reply_text(f"✅ Broadcast Complete!\n\nSuccessfully sent to: {success_count} chats\nFailed to send: {fail_count}")
        logger.info(f"Broadcast initiated by {user_id} completed. Success: {success_count}, Failed: {fail_count}.")
    else:
        await query.edit_message_text("Broadcast message not found.")

async def cancel_broadcast(client: Client, query: CallbackQuery) -> None:
    await query.answer()
    user_id = query.from_user.id
    
    if user_id in BROADCAST_MESSAGE:
        BROADCAST_MESSAGE.pop(user_id)
    
    await query.edit_message_text("❌ Broadcast cancel kar diya gaya hai.")


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
            if profanity_filter.add_bad_word(word_to_add):
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
                f"Added by: {message.from_user.mention} (<code>{message.from_user.id}</code>)\n"
                f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}"
            )
            await log_to_channel(log_message, parse_mode=enums.ParseMode.HTML)
            logger.info(f"Bot joined group: {chat.title} ({chat.id}) added by {message.from_user.id}.")

            if db is not None and db.groups is not None:
                try:
                    db.groups.update_one(
                        {"chat_id": chat.id},
                        {"$set": {"title": chat.title, "type": chat.type, "last_active": datetime.now()}},
                        upsert=True
                    )
                except Exception as e:
                    logger.error(f"Error saving group {chat.id} to DB: {e}")

            try:
                if await is_group_admin(chat.id, bot_info.id):
                    await message.reply_text(
                        f"Hello! Main <b>{bot_info.first_name}</b> hun, aur ab main is group mein moderation karunga.\n"
                        f"Kripya सुनिश्चित karein ki mere paas <b>'Delete Messages'</b>, <b>'Restrict Users'</b> aur <b>'Post Messages'</b> ki admin permissions hain takki main apna kaam theek se kar sakoon."
                        , parse_mode=enums.ParseMode.HTML)
                    logger.info(f"Bot confirmed admin status in {chat.title} ({chat.id}).")
                else:
                    await message.reply_text(
                        f"Hello! Main <b>{bot_info.first_name}</b> hun. Is group mein moderation ke liye, kripya mujhe <b>admin</b> banayein aur <b>'Delete Messages'</b>, <b>'Restrict Users'</b>, <b>'Post Messages'</b> ki permissions dein."
                        , parse_mode=enums.ParseMode.HTML)
                    logger.warning(f"Bot is not admin in {chat.title} ({chat.id}). Functionality will be limited.")
            except Exception as e:
                logger.error(f"Error during bot's self-introduction in {chat.title} ({chat.id}): {e}")

# --- Tagging Commands ---
@client.on_message(filters.command("tagall") & filters.group)
async def tag_all(client: Client, message: Message) -> None:
    is_sender_admin = await is_group_admin(message.chat.id, message.from_user.id)
    if not is_sender_admin:
        await message.reply_text("Aapke paas is command ko use karne ki permission nahi hai.")
        return
    
    chat_id = message.chat.id
    
    try:
        members_count = await client.get_chat_members_count(chat_id)
        message_text = " ".join(message.command[1:]) if len(message.command) > 1 else "<b>Attention Everyone!</b>"
        
        final_message = f"<b>Is group mein {members_count} members hain.</b>\n\n<b>Message:</b> {message_text}"
        
        sent_message = await message.reply_text(
            final_message,
            parse_mode=enums.ParseMode.HTML
        )
        
        if chat_id not in TAG_MESSAGES:
            TAG_MESSAGES[chat_id] = []
        TAG_MESSAGES[chat_id].append(sent_message.id)
        
    except Exception as e:
        logger.error(f"Error in /tagall command: {e}")
        await message.reply_text(f"Tag karte samay error hui: {e}")

@client.on_message(filters.command("onlinetag") & filters.group)
async def tag_online(client: Client, message: Message) -> None:
    is_sender_admin = await is_group_admin(message.chat.id, message.from_user.id)
    if not is_sender_admin:
        await message.reply_text("Aapke paas is command ko use karne ki permission nahi hai.")
        return
        
    try:
        online_message = "<b>Online users ko tag karne ki suvidha ab Telegram API mein nahi hai.</b>"
        await message.reply_text(online_message, parse_mode=enums.ParseMode.HTML)
        
    except Exception as e:
        logger.error(f"Error in /onlinetag command: {e}")
        await message.reply_text(f"Online members ko tag karte samay error hui: {e}")


@client.on_message(filters.command("admin") & filters.group)
async def tag_admins(client: Client, message: Message) -> None:
    is_sender_admin = await is_group_admin(message.chat.id, message.from_user.id)
    if not is_sender_admin:
        await message.reply_text("Aapke paas is command ko use karne ki permission nahi hai.")
        return
        
    message_text = " ".join(message.command[1:]) if len(message.command) > 1 else "<b>Admins, attention please!</b>"
    chat_id = message.chat.id

    try:
        admins = [admin async for admin in client.get_chat_members(chat_id, filter=enums.ChatMembersFilter.ADMINISTRATORS)]
        tagged_admins = [admin.user.mention for admin in admins if not admin.user.is_bot]
        
        if not tagged_admins:
            await message.reply_text("Is group mein koi admins nahi hain jinhe tag kiya ja sake.")
            return
            
        tag_message_text = " ".join(f"👑 {admin}" for admin in tagged_admins)
        
        if chat_id not in TAG_MESSAGES:
            TAG_MESSAGES[chat_id] = []

        sent_message = await message.reply_text(
            f"{tag_message_text}\n\n<b>Message:</b> {message_text}",
            parse_mode=enums.ParseMode.HTML
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

    if chat_id not in TAG_MESSAGES or not TAG_MESSAGES[chat_id]:
        await message.reply_text("कोई भी टैगिंग मैसेज नहीं मिला जिसे रोका जा सके।")
        return

    try:
        await client.delete_messages(chat_id, TAG_MESSAGES[chat_id])
        TAG_MESSAGES.pop(chat_id)

        bot_info = await client.get_me()
        bot_username = bot_info.username
        add_to_group_url = f"https://t.me/{bot_username}?startgroup=true"
        
        final_message_text = "<b>यह टैगिंग खत्म हो गया है।</b>"
        
        keyboard = [
            [InlineKeyboardButton("➕ <b>मुझे ग्रुप में जोड़ें</b>", url=add_to_group_url)],
            [InlineKeyboardButton("📢 अपडेट चैनल", url="https://t.me/asbhai_bsr")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await message.reply_text(
            final_message_text,
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML
        )
        logger.info(f"Admin {message.from_user.id} stopped tagging in chat {chat_id}.")

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
            f"<b>✅ मैसेज भेज सकता है:</b> {perms.can_send_messages}\n"
        )
        
        await message.reply_text(message_text, parse_mode=enums.ParseMode.HTML)
        logger.info(f"Admin {message.from_user.id} requested permissions check in chat {chat.id}.")
    except Exception as e:
        logger.error(f"अनुमतियाँ जाँचते समय एक error हुई: {e}")
        await message.reply_text(f"अनुमतियाँ जाँचते समय एक error हुई: {e}")


# --- Helper functions for warnings and biolink exceptions ---
async def get_warnings(user_id: int, chat_id: int):
    if db is None or db.warnings is None:
        return 0
    warnings_doc = db.warnings.find_one({"user_id": user_id, "chat_id": chat_id})
    return warnings_doc.get("count", 0) if warnings_doc else 0

async def increment_warnings(user_id: int, chat_id: int):
    if db is None or db.warnings is None:
        return 1
    warnings_doc = db.warnings.find_one_and_update(
        {"user_id": user_id, "chat_id": chat_id},
        {"$inc": {"count": 1}, "$set": {"last_warned": datetime.now()}},
        upsert=True,
        return_document='after'
    )
    return warnings_doc['count'] if warnings_doc else 1

async def reset_warnings(user_id: int, chat_id: int):
    if db is None or db.warnings is None:
        return
    db.warnings.delete_one({"user_id": user_id, "chat_id": chat_id})

async def is_biolink_whitelisted(user_id: int) -> bool:
    if db is None or db.biolink_exceptions is None:
        return False
    return db.biolink_exceptions.find_one({"user_id": user_id}) is not None

async def add_biolink_whitelist(user_id: int):
    if db is None or db.biolink_exceptions is None:
        return
    db.biolink_exceptions.update_one({"user_id": user_id}, {"$set": {"timestamp": datetime.now()}}, upsert=True)

async def remove_biolink_whitelist(user_id: int):
    if db is None or db.biolink_exceptions is None:
        return
    db.biolink_exceptions.delete_one({"user_id": user_id})


# --- Core Message Handler (Profanity, Bio Link, URL in message) ---
@client.on_message(filters.text & filters.group & ~filters.command([]) & ~filters.via_bot)
async def handle_all_messages(client: Client, message: Message) -> None:
    user = message.from_user
    chat = message.chat
    message_text = message.text

    is_sender_admin = await is_group_admin(chat.id, user.id)

    # Check for profanity
    if profanity_filter is not None and profanity_filter.contains_profanity(message_text):
        await handle_incident(client, chat.id, user, "गाली-गलौज (Profanity)", message, "abuse")
        return

    # Check for URLs directly in the message
    if URL_PATTERN.search(message_text) and not is_sender_admin:
        await handle_incident(client, chat.id, user, "मैसेज में लिंक (Link in Message)", message, "link_in_message")
        return

    # Check for bio link if the user is not an admin
    if not is_sender_admin and not await is_biolink_whitelisted(user.id):
        try:
            user_profile = await client.get_chat(user.id)
            user_bio = user_profile.bio or ""
            if URL_PATTERN.search(user_bio):
                try:
                    await message.delete()
                    logger.info(f"Deleted message from user with bio link: {user.id}")
                except Exception as e:
                    logger.error(f"Could not delete message for user {user.id}: {e}")
                    
                warn_count = await increment_warnings(user.id, chat.id)
                warn_limit = 3
                
                if db is not None and db.warnings is not None:
                    warnings_doc = db.warnings.find_one({"user_id": user.id, "chat_id": chat.id})
                    last_sent_message_id = warnings_doc.get("last_sent_message_id") if warnings_doc else None

                warning_text = (
                    "<b>🚨 Chetavni</b> 🚨\n\n"
                    f"👤 <b>User:</b> {user.mention} (<code>{user.id}</code>)\n"
                    "❌ <b>Karan:</b> Bio mein link mila\n"
                    f"⚠️ <b>Chetavni:</b> {warn_count}/{warn_limit}\n\n"
                    "<b>Notice: Kripya apne bio se links hata dein.</b>"
                )
                
                keyboard = [
                    [
                        InlineKeyboardButton("❌ Chetavni Cancel", callback_data=f"cancel_warn_{user.id}_{chat.id}"),
                        InlineKeyboardButton("✅ Bio Link Approve", callback_data=f"approve_bio_{user.id}_{chat.id}")
                    ],
                    [InlineKeyboardButton("🗑️ Band Karen", callback_data=f"close_message_{message.id}")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                sent_message = await message.reply_text(warning_text, reply_markup=reply_markup, parse_mode=enums.ParseMode.HTML)
                
                if db is not None and db.warnings is not None:
                    db.warnings.update_one(
                        {"user_id": user.id, "chat_id": chat.id},
                        {"$set": {"last_sent_message_id": sent_message.id}}
                    )

                if warn_count >= warn_limit:
                    try:
                        await client.restrict_chat_member(
                            chat_id=chat.id,
                            user_id=user.id,
                            permissions=ChatPermissions(can_send_messages=False)
                        )
                        await remove_biolink_whitelist(user.id)
                        await reset_warnings(user.id, chat.id)
                        
                        mute_text = (
                            f"<b>{user.mention}</b> ko <b>mute</b> kar diya gaya hai kyunki unhone bio link ke liye {warn_limit} warnings cross kar di hain."
                        )
                        await sent_message.edit_text(mute_text, parse_mode=enums.ParseMode.HTML, reply_markup=None)
                    except Exception as e:
                        logger.error(f"Error muting user {user.id} after warnings: {e}")
                        await sent_message.edit_text(
                            f"Bot ke paas {user.mention} ko mute karne ki permission nahi hai.",
                            parse_mode=enums.ParseMode.HTML
                        )
                return
        except BadRequest as e:
            logger.warning(f"Could not get chat info for user {user.id}: {e}")
        except Exception as e:
            logger.error(f"Error checking user bio for user {user.id} in chat {chat.id}: {e}")
    else:
        if await get_warnings(user.id, chat.id) > 0:
            await reset_warnings(user.id, chat.id)
            logger.info(f"Warnings reset for user {user.id} as their bio is clean.")


# --- Handler for Edited Messages ---
@client.on_edited_message(filters.text & filters.group & ~filters.via_bot)
async def handle_edited_messages(client: Client, edited_message: Message) -> None:
    if not edited_message:
        return

    user = edited_message.from_user
    chat = edited_message.chat
    
    is_sender_admin = await is_group_admin(chat.id, user.id)
    if not is_sender_admin:
        try:
            await edited_message.delete()
            logger.info(f"Deleted edited message from non-admin user {user.id} in chat {chat.id}.")
        except Exception as e:
            logger.error(f"Error deleting edited message in {chat.id}: {e}. Bot needs 'Delete Messages' permission.")
            
        notification_message = f"🚨 {user.mention} ne ek message edit kiya jo delete kar diya gaya hai."
        
        keyboard = [
            [
                InlineKeyboardButton("👤 User Profile", url=f"tg://user?id={user.id}"),
                InlineKeyboardButton("🔧 Admin Actions", callback_data=f"admin_actions_menu_{user.id}_{chat.id}")
            ],
            [
                InlineKeyboardButton("🗑️ Band Karen", callback_data=f"close_message_{edited_message.id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        try:
            await client.send_message(chat.id, notification_message, reply_markup=reply_markup, parse_mode=enums.ParseMode.HTML)
        except Exception as e:
            logger.error(f"Error sending edited message notification in chat {chat.id}: {e}")


# --- Callback Query Handlers ---
@client.on_callback_query()
async def button_callback_handler(client: Client, query: CallbackQuery) -> None:
    data = query.data
    user_id = query.from_user.id
    chat_id = query.message.chat.id
    
    if query.message.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP] and not data.startswith(('help_menu', 'other_bots', 'donate_info', 'back_to_main_menu')):
        is_current_group_admin = await is_group_admin(chat_id, user_id)
        if not is_current_group_admin:
            await query.answer("❌ Aapke paas is action ko karne ki permission nahi hai. Aap group admin nahi hain.", show_alert=True)
            logger.warning(f"Non-admin user {user_id} tried to use admin button in chat {chat_id}.")
            return
    
    await query.answer()

    if data == "help_menu":
        help_text = (
            "<b>Bot Help Menu:</b>\n\n"
            "<b>• Gaali detection:</b> Automatic message deletion for profanity.\n"
            "<b>• Bio Link Detection:</b> Automatically deletes messages from users with links in their bio (Admins are exempt).\n"
            "<b>• Edited Message Deletion:</b> Deletes any edited message from non-admins to prevent rule-breaking edits.\n"
            "<b>• Admin Actions:</b> Mute, ban, kick users directly from the group notification.\n"
            "<b>• Incident Logging:</b> All violations are logged in a dedicated case channel.\n\n"
            "<b>Commands:</b>\n"
            "• <code>/start</code>: Bot ko start karein (private aur group mein).\n"
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
        await query.edit_message_text(help_text, reply_markup=reply_markup, parse_mode=enums.ParseMode.HTML)

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
        await query.edit_message_text(other_bots_text, reply_markup=reply_markup, parse_mode=enums.ParseMode.HTML)

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
        await query.edit_message_text(donate_text, reply_markup=reply_markup, parse_mode=enums.ParseMode.HTML)

    elif data == "back_to_main_menu":
        bot_info = await client.get_me()
        bot_name = bot_info.first_name
        welcome_message = (
            f"👋 <b>Namaste {query.from_user.first_name}!</b>\n\n"
            f"Mai <b>{bot_name}</b> hun, aapka group moderator bot. "
            f"Mai aapke groups ko saaf suthra rakhne mein madad karta hun, "
            f"gaaliyon wale messages ko delete karta hun aur zaroorat padne par warning bhi deta hun.\n\n"
            f"<b>Mere features:</b>\n"
            f"• Gaali detection aur deletion\n"
            f"• User warnings aur actions (Mute, Ban, Kick)\n"
            f"• Incident logging\n\n"
            f"Agar aapko koi madad chahiye, toh niche diye gaye buttons ka upyog karein."
        )
        keyboard = [
            [InlineKeyboardButton("❓ Help", callback_data="help_menu"), InlineKeyboardButton("🤖 Other Bots", callback_data="other_bots")],
            [InlineKeyboardButton("📢 Update Channel", url="https://t.me/asbhai_bsr"), InlineKeyboardButton("💖 Donate", callback_data="donate_info")],
            [InlineKeyboardButton("📈 <b>Promotion</b>", url="https://t.me/asprmotion")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(welcome_message, reply_markup=reply_markup, parse_mode=enums.ParseMode.HTML)

    elif data.startswith("admin_actions_menu_"):
        parts = data.split('_')
        target_user_id = int(parts[3])
        group_chat_id = int(parts[4])
        
        target_user = await client.get_chat_member(group_chat_id, target_user_id)
        target_user_name = target_user.user.full_name
        
        is_biolink_approved = db is not None and db.biolink_exceptions is not None and db.biolink_exceptions.find_one({"user_id": target_user_id})

        actions_text = (
            f"<b>{target_user_name}</b> ({target_user_id}) ke liye actions:\n"
            f"Group: {query.message.chat.title}"
        )
        actions_keyboard = [
            [InlineKeyboardButton("🔇 Mute (30 min)", callback_data=f"mute_{target_user_id}_{group_chat_id}_30m")],
            [InlineKeyboardButton("🔇 Mute (1 hr)", callback_data=f"mute_{target_user_id}_{group_chat_id}_1h")],
            [InlineKeyboardButton("🔇 Mute (24 hr)", callback_data=f"mute_{target_user_id}_{group_chat_id}_24h")],
            [InlineKeyboardButton("🚫 Ban", callback_data=f"ban_{target_user_id}_{group_chat_id}")],
            [InlineKeyboardButton("🦵 Kick", callback_data=f"kick_{target_user_id}_{group_chat_id}")],
            [InlineKeyboardButton("❗ Warn", callback_data=f"warn_{target_user_id}_{group_chat_id}")],
        ]
        
        if is_biolink_approved:
            actions_keyboard.append([InlineKeyboardButton("✅ Approved Bio User", callback_data=f"unapprove_bio_{target_user_id}_{group_chat_id}")])
        else:
            actions_keyboard.append([InlineKeyboardButton("✍️ Approved Bio User", callback_data=f"approve_bio_{target_user_id}_{group_chat_id}")])

        actions_keyboard.append([InlineKeyboardButton("⬅️ Back to Notification", callback_data=f"back_to_notification_{target_user_id}_{group_chat_id}")])
        
        reply_markup = InlineKeyboardMarkup(actions_keyboard)
        await query.edit_message_text(actions_text, reply_markup=reply_markup, parse_mode=enums.ParseMode.HTML)

    elif data.startswith("approve_bio_"):
        target_user_id = int(data.split('_')[2])
        await add_biolink_whitelist(target_user_id)
        await reset_warnings(target_user_id, chat_id)
        
        target_user = await client.get_chat_member(chat_id, target_user_id)
        mention = target_user.user.mention

        keyboard = [
            [
                InlineKeyboardButton("🚫 Bio Link Unapprove", callback_data=f"unapprove_bio_{target_user_id}_{chat_id}"),
                InlineKeyboardButton("🗑️ Band Karen", callback_data=f"close_message_{query.message.id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"✅ {mention} (<code>{target_user_id}</code>) ko bio link exceptions list mein add kar diya gaya hai.",
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML
        )
        return

    elif data.startswith("unapprove_bio_"):
        target_user_id = int(data.split('_')[2])
        await remove_biolink_whitelist(target_user_id)

        target_user = await client.get_chat_member(chat_id, target_user_id)
        mention = target_user.user.mention
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Bio Link Approve", callback_data=f"approve_bio_{target_user_id}_{chat_id}"),
                InlineKeyboardButton("🗑️ Band Karen", callback_data=f"close_message_{query.message.id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"❌ {mention} (<code>{target_user_id}</code>) ko bio link exceptions list se hata diya gaya hai.",
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML
        )
        return

    elif data.startswith("close_message_"):
        message_id_to_delete = int(data.split('_')[2])
        try:
            await client.delete_messages(chat_id, message_id_to_delete)
        except Exception as e:
            await query.answer("❌ Message delete karne mein error hui.", show_alert=True)
            logger.error(f"Error deleting message {message_id_to_delete}: {e}")

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
                await query.edit_message_text("Invalid mute duration.")
                return

            permissions = ChatPermissions(can_send_messages=False)
            await client.restrict_chat_member(
                chat_id=group_chat_id,
                user_id=target_user_id,
                permissions=permissions,
                until_date=until_date
            )
            target_user = await client.get_chat_member(group_chat_id, target_user_id)
            await query.edit_message_text(f"✅ {target_user.user.mention} ko {duration_str} ke liye mute kar diya gaya hai.", parse_mode=enums.ParseMode.HTML)
            logger.info(f"Admin {user_id} muted user {target_user_id} in chat {group_chat_id} for {duration_str}.")
        except Exception as e:
            await query.edit_message_text(f"Mute karte samay error hui: {e}")
            logger.error(f"Error muting user {target_user_id} in {group_chat_id}: {e}")

    elif data.startswith("ban_"):
        parts = data.split('_')
        target_user_id = int(parts[1])
        group_chat_id = int(parts[2])
        try:
            await client.ban_chat_member(chat_id=group_chat_id, user_id=target_user_id)
            target_user = await client.get_chat_member(group_chat_id, target_user_id)
            await query.edit_message_text(f"✅ {target_user.user.mention} ko group se ban kar diya gaya hai.", parse_mode=enums.ParseMode.HTML)
            logger.info(f"Admin {user_id} banned user {target_user_id} from chat {group_chat_id}.")
        except Exception as e:
            await query.edit_message_text(f"Ban karte samay error hui: {e}")
            logger.error(f"Error banning user {target_user_id} from {group_chat_id}: {e}")

    elif data.startswith("kick_"):
        parts = data.split('_')
        target_user_id = int(parts[1])
        group_chat_id = int(parts[2])
        try:
            await client.unban_chat_member(chat_id=group_chat_id, user_id=target_user_id, only_if_banned=False)
            target_user = await client.get_chat_member(group_chat_id, target_user_id)
            await query.edit_message_text(f"✅ {target_user.user.mention} ko group se nikal diya gaya hai.", parse_mode=enums.ParseMode.HTML)
            logger.info(f"Admin {user_id} kicked user {target_user_id} from chat {group_chat_id}.")
        except Exception as e:
            await query.edit_message_text(f"Kick karte samay error hui: {e}")
            logger.error(f"Error kicking user {target_user_id} from {group_chat_id}: {e}")

    elif data.startswith("warn_"):
        parts = data.split('_')
        target_user_id = int(parts[1])
        group_chat_id = int(parts[2])

        if db is None or db.warnings is None:
            await query.edit_message_text("Database connection available nahi hai. Chetavni nahi de sakte.")
            return

        try:
            target_user = await client.get_chat_member(group_chat_id, target_user_id)
            
            warnings_doc = db.warnings.find_one_and_update(
                {"user_id": target_user_id, "chat_id": group_chat_id},
                {"$inc": {"count": 1}, "$set": {"last_warned": datetime.now()}},
                upsert=True,
                return_document='after'
            )
            warn_count = warnings_doc['count'] if warnings_doc else 1
            
            warn_message = (
                f"🚨 <b>Chetavni</b>\n\n"
                f"➡️ {target_user.user.mention}, aapko group ke niyam todne ke liye chetavni di jaati hai. Please group ke rules follow karein.\n\n"
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
                    f"❌ <b>Permanent Mute</b>\n\n"
                    f"➡️ {target_user.user.mention}, aapko 3 warnings mil chuki hain. Isliye aapko group mein permanent mute kar diya gaya hai."
                )
                await client.send_message(chat_id=group_chat_id, text=permanent_mute_message, parse_mode=enums.ParseMode.HTML)
                await query.edit_message_text(f"✅ {target_user.user.mention} ko {warn_count} chetavaniyan milne ke baad permanent mute kar diya gaya hai.", parse_mode=enums.ParseMode.HTML)
                logger.info(f"User {target_user_id} was permanently muted after 3 warnings in chat {group_chat_id}.")
            else:
                await query.edit_message_text(f"✅ {target_user.user.mention} ko chetavni bhej di gayi hai. Warnings: {warn_count}/3.", parse_mode=enums.ParseMode.HTML)
                logger.info(f"Admin {user_id} warned user {target_user_id} in chat {group_chat_id}. Current warnings: {warn_count}.")
                
        except Exception as e:
            await query.edit_message_text(f"Chetavni bhejte samay error hui: {e}")
            logger.error(f"Error warning user {target_user_id} in {group_chat_id}: {e}")

    elif data.startswith("back_to_notification_"):
        parts = data.split('_')
        target_user_id = int(parts[4])
        group_chat_id = int(parts[5])

        incident_data = None
        if db is not None and db.incidents is not None:
            incident_data = db.incidents.find_one({
                "chat_id": group_chat_id,
                "user_id": target_user_id
            }, sort=[("timestamp", -1)])

        case_id_value = incident_data["case_id"] if incident_data else "N/A"
        reason = incident_data["reason"] if incident_data else "Ulanghan"
        case_channel_message_id = incident_data.get("case_channel_message_id") if incident_data else None
        
        if case_channel_message_id:
            channel_link_id = str(CASE_CHANNEL_ID).replace('-100', '')
            case_detail_url = f"https://t.me/c/{channel_link_id}/{case_channel_message_id}"
        else:
            case_detail_url = f"https://t.me/{CASE_CHANNEL_USERNAME}"

        user_obj = await client.get_chat_member(group_chat_id, target_user_id)

        notification_message = (
            f"🚨 <b>Group mein Niyam Ulanghan!</b>\n\n"
            f"➡️ <b>User:</b> {user_obj.user.mention}\n"
            f"➡️ <b>Reason:</b> \"{reason} ki wajah se message hata diya gaya hai।\"\n\n"
            f"➡️ <b>Case ID:</b> <code>{case_id_value}</code>"
        )

        keyboard = [
            [
                InlineKeyboardButton("👤 User Profile", url=f"tg://user?id={target_user_id}"),
                InlineKeyboardButton("🔧 Admin Actions", callback_data=f"admin_actions_menu_{target_user_id}_{group_chat_id}")
            ],
            [
                InlineKeyboardButton("📄 View Case Details", url=case_detail_url)
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(notification_message, reply_markup=reply_markup, parse_mode=enums.ParseMode.HTML)

    elif data == "confirm_broadcast":
        await confirm_broadcast(client, query)
    elif data == "cancel_broadcast":
        await cancel_broadcast(client, query)

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
    logger.info("Bot stopped.")
