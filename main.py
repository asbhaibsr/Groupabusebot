import os
import time
from datetime import datetime, timedelta
import threading
import asyncio
import logging
import re
from pymongo import MongoClient
from telegram.error import BadRequest, Forbidden, TelegramError

from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions, constants
from telegram.ext import (
    CommandHandler, MessageHandler, filters, ContextTypes,
    CallbackQueryHandler, Application
)

# Custom module import
# Ensure this file (profanity_filter.py) is present in your deployment
from profanity_filter import ProfanityFilter

# --- Configuration ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
LOG_CHANNEL_ID = -1002352329534
CASE_CHANNEL_ID = -1002717243409
CASE_CHANNEL_USERNAME = "AbusersDetector"
MONGO_DB_URI = os.getenv("MONGO_DB_URI")
GROUP_ADMIN_USERNAME = os.getenv("GROUP_ADMIN_USERNAME", "admin")
ADMIN_USER_IDS = [7315805581]

bot_start_time = datetime.now()
BROADCAST_MESSAGE = {}
URL_PATTERN = re.compile(r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+')
# Emojis for tagging users
TAG_EMOJIS = ["🎉", "✨", "💫", "🌟", "🎈", "🎊", "🔥", "💖", "⚡️", "🌈"]

# Global variable to store tag messages
TAG_MESSAGES = {}

# --- Logging Setup ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
application = None
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

        collection_names = db.list_collection_names()

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
        
        # New collection for warnings
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

async def is_group_admin(chat_id: int, user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Checks if the given user_id is an admin in the specified chat."""
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in ['creator', 'administrator']
    except Exception as e:
        logger.error(f"Error checking admin status for user {user_id} in chat {chat_id}: {e}")
        return False

async def log_to_channel(text: str, parse_mode: str = None) -> None:
    """Sends a log message to the predefined LOG_CHANNEL_ID."""
    if application is not None and LOG_CHANNEL_ID is not None:
        try:
            await application.bot.send_message(chat_id=LOG_CHANNEL_ID, text=text, parse_mode=parse_mode)
        except Exception as e:
            logger.error(f"Error logging to channel {LOG_CHANNEL_ID}: {e}")
    else:
        logger.warning("Application not initialized or LOG_CHANNEL_ID is not set, cannot log to channel.")

async def notify_all_admins(chat_id: int, message: str, context: ContextTypes.DEFAULT_TYPE, reply_markup=None):
    """Notifies all admins in a group about an incident."""
    try:
        admins = await context.bot.get_chat_administrators(chat_id)
        for admin in admins:
            if not admin.user.is_bot:
                try:
                    await context.bot.send_message(
                        chat_id=admin.user.id,
                        text=message,
                        reply_markup=reply_markup,
                        parse_mode='HTML'
                    )
                except Exception as e:
                    logger.error(f"Could not send admin notification to {admin.user.id}: {e}")
    except Exception as e:
        logger.error(f"Error getting admins for chat {chat_id}: {e}")

async def handle_incident(context: ContextTypes.DEFAULT_TYPE, chat_id, user, reason, original_message, case_type, case_id=None):
    """Common function to handle all incidents (abuse, bio link, edited message)."""
    original_message_id = original_message.message_id
    message_text = original_message.text or "No text content"
    if not case_id:
        case_id = str(int(datetime.now().timestamp() * 1000))

    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=original_message_id)
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
            f"<b>👤 यूज़र:</b> {user.mention_html()} (<code>{user.id}</code>)\n"
            f"<b>📝 यूज़रनेम:</b> @{user.username if user.username else 'N/A'}\n"
            f"<b>⏰ समय:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}\n"
            f"<b>🆔 केस ID:</b> <code>{case_id}</code>\n\n"
            f"<b>➡️ कारण:</b> {reason}\n"
            f"<b>➡️ मूल मैसेज:</b> ||{message_text}||\n"
        )
        sent_details_msg = await context.bot.send_message(
            chat_id=CASE_CHANNEL_ID,
            text=details_message_text,
            parse_mode='HTML'
        )
        forwarded_message_id = sent_details_msg.message_id

        if sent_details_msg:
            channel_link_id = str(CASE_CHANNEL_ID).replace('-100', '')
            case_detail_url = f"https://t.me/c/{channel_link_id}/{sent_details_msg.message_id}"
            logger.info(f"Incident content sent to case channel with spoiler. URL: {case_detail_url}")

    except Exception as e:
        logger.error(f"Error sending incident details to case channel: {e}")

    if db and db.incidents:
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

    # Enhanced notification message
    notification_message = (
        f"🚨 **Group mein Niyam Ulanghan!**\n\n"
        f"➡️ <b>User:</b> {user.mention_html()}\n"
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
        await context.bot.send_message(
            chat_id=chat_id,
            text=notification_message,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        logger.info(f"Incident notification sent for user {user.id} in chat {chat.id}.")
    except Exception as e:
        logger.error(f"Error sending notification in chat {chat.id}: {e}. Make sure bot has 'Post Messages' permission.")
        # Fallback to a simpler message if HTML parsing fails or other issues occur
        try:
            await context.bot.send_message(
                chat_id=chat.id,
                text=f"User {user.id} ka message hata diya gaya hai. Karan: {reason}"
            )
        except Exception as simple_e:
            logger.error(f"Couldn't send even simple notification in chat {chat.id}: {simple_e}")

# --- Bot Commands Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.message.from_user
    chat = update.message.chat

    bot_info = await context.bot.get_me()
    bot_name = bot_info.first_name
    bot_username = bot_info.username

    if chat.type == 'private':
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
        await update.message.reply_text(
            text=welcome_message,
            reply_markup=reply_markup,
            parse_mode='HTML',
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
            f"User: {user.mention_html()} (<code>{user.id}</code>)\n"
            f"Username: @{user.username if user.username else 'N/A'}\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}"
        )
        await log_to_channel(log_message, parse_mode='HTML')

    elif chat.type in ['group', 'supergroup']:
        bot_member = await chat.get_member(bot_info.id)
        add_to_group_url = f"https://t.me/{bot_username}?startgroup=true"
        
        if bot_member.status in ['administrator', 'creator']:
            group_start_message = f"Hello! Main <b>{bot_name}</b> hun, aapka group moderation bot. Main aapke group ko saaf suthra rakhne mein madad karunga."
        else:
            group_start_message = f"Hello! Main <b>{bot_name}</b> hun. Is group mein moderation ke liye, kripya mujhe <b>admin</b> banayein aur <b>'Delete Messages'</b>, <b>'Restrict Users'</b>, <b>'Post Messages'</b> ki permissions dein."
        
        group_keyboard = [
            [InlineKeyboardButton("➕ Add Me To Your Group", url=add_to_group_url)],
            [InlineKeyboardButton("📢 Update Channel", url="https://t.me/asbhai_bsr")]
        ]
        reply_markup = InlineKeyboardMarkup(group_keyboard)

        await update.message.reply_text(
            text=group_start_message,
            reply_markup=reply_markup,
            parse_mode='HTML'
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

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Aapke paas is command ko use karne ki permission nahi hai.")
        return

    total_groups = 0
    total_users = 0
    total_incidents = 0
    if db is not None:
        try:
            total_groups = db.groups.count_documents({}) if db.groups is not None else 0
            total_users = db.users.count_documents({}) if db.users is not None else 0
            total_incidents = db.incidents.count_documents({}) if db.incidents is not None else 0
        except Exception as e:
            logger.error(f"Error fetching stats from DB: {e}")
            await update.message.reply_text(f"Stats fetch karte samay error hui: {e}")
            return

    stats_message = (
        f"📊 <b>Bot Status:</b>\n\n"
        f"• Total Unique Users (via /start in private chat): {total_users}\n"
        f"• Total Groups Managed: {total_groups}\n"
        f"• Total Incidents Logged: {total_incidents}\n"
        f"• Uptime: {str(datetime.now() - bot_start_time).split('.')[0]} \n"
        f"• Last Check: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}"
    )
    await update.message.reply_text(stats_message, parse_mode='HTML')
    logger.info(f"Admin {update.effective_user.id} requested stats.")

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Aapke paas is command ko use karne ki permission nahi hai.")
        return
    if update.message.chat.type != 'private':
        await update.message.reply_text("Broadcast command sirf private chat mein hi shuru ki ja sakti hai.")
        return
    
    await update.message.reply_text("📢 Broadcast shuru karne ke liye, kripya apna message bhejein:")
    BROADCAST_MESSAGE[update.effective_user.id] = "waiting_for_message"
    logger.info(f"Admin {update.effective_user.id} initiated broadcast.")

async def handle_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.message.from_user
    
    if not is_admin(user.id):
        return
    
    if BROADCAST_MESSAGE.get(user.id) != "waiting_for_message":
        return
    
    BROADCAST_MESSAGE[user.id] = update.message
    
    keyboard = [
        [InlineKeyboardButton("✅ Yes, Broadcast Now", callback_data="confirm_broadcast")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_broadcast")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await update.message.reply_text(
            "Kya aap is message ko sabhi groups aur users ko bhejna chahte hain?",
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Error sending broadcast confirmation message to {user.id}: {e}")
        await update.message.reply_text("Broadcast confirmation message bhejne mein error aaya.")
        BROADCAST_MESSAGE.pop(user.id, None)

async def confirm_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
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
                await context.bot.copy_message(
                    chat_id=chat_id,
                    from_chat_id=broadcast_msg.chat.id,
                    message_id=broadcast_msg.message_id
                )
                success_count += 1
                await asyncio.sleep(0.1)
            except Forbidden:
                logger.warning(f"Broadcast failed to {chat_id} (Forbidden: Bot was blocked by user or kicked from group).")
                fail_count += 1
            except BadRequest as e:
                logger.warning(f"Broadcast failed to {chat_id} (BadRequest: {e}).")
                fail_count += 1
            except TelegramError as e:
                logger.warning(f"Broadcast failed to {chat_id} (TelegramError: {e}).")
                fail_count += 1
            except Exception as e:
                logger.error(f"Failed to broadcast to {chat_id} (Unknown error: {e}).")
                fail_count += 1

        await query.message.reply_text(f"✅ Broadcast Complete!\n\nSuccessfully sent to: {success_count} chats\nFailed to send: {fail_count}")
        logger.info(f"Broadcast initiated by {user_id} completed. Success: {success_count}, Failed: {fail_count}.")
    else:
        await query.edit_message_text("Broadcast message not found.")

async def cancel_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if user_id in BROADCAST_MESSAGE:
        BROADCAST_MESSAGE.pop(user_id)
    
    await query.edit_message_text("❌ Broadcast cancel kar diya gaya hai.")

async def add_abuse_word(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Aapke paas is command ko use karne ki permission nahi hai.")
        return
    if not context.args:
        await update.message.reply_text("Kripya woh shabd dein jise aap add karna chahte hain. Upyog: `/addabuse <shabd>`")
        return
    word_to_add = " ".join(context.args).lower().strip()
    if not word_to_add:
        await update.message.reply_text("Kripya ek valid shabd dein.")
        return
    if profanity_filter is not None:
        try:
            if profanity_filter.add_bad_word(word_to_add):
                await update.message.reply_text(f"✅ Shabd '`{word_to_add}`' safaltapoorvak jod diya gaya hai\\.", parse_mode='MarkdownV2')
                logger.info(f"Admin {update.effective_user.id} added abuse word: {word_to_add}.")
            else:
                await update.message.reply_text(f"Shabd '`{word_to_add}`' pehle se hi list mein maujood hai\\.", parse_mode='MarkdownV2')
        except Exception as e:
            await update.message.reply_text(f"Shabd jodte samay error hui: {e}")
            logger.error(f"Error adding abuse word {word_to_add}: {e}")
    else:
        await update.message.reply_text("Profanity filter initialize nahi hua hai. MongoDB connection mein problem ho sakti hai.")
        logger.error("Profanity filter not initialized, cannot add abuse word.")

async def welcome_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    new_members = update.message.new_chat_members
    chat = update.message.chat
    bot_info = await context.bot.get_me()

    for member in new_members:
        if member.id == bot_info.id:
            log_message = (
                f"<b>🤖 Bot Joined Group:</b>\n"
                f"Group Name: <code>{chat.title}</code>\n"
                f"Group ID: <code>{chat.id}</code>\n"
                f"Members: {await chat.get_member_count()}\n"
                f"Added by: {update.message.from_user.mention_html()} (<code>{update.message.from_user.id}</code>)\n"
                f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}"
            )
            await log_to_channel(log_message, parse_mode='HTML')
            logger.info(f"Bot joined group: {chat.title} ({chat.id}) added by {update.message.from_user.id}.")

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
                bot_member = await chat.get_member(bot_info.id)
                if bot_member.status in ['administrator', 'creator']:
                    await chat.send_message(
                        f"Hello! Main <b>{bot_info.first_name}</b> hun, aur ab main is group mein moderation karunga.\n"
                        f"Kripya सुनिश्चित karein ki mere paas <b>'Delete Messages'</b>, <b>'Restrict Users'</b> aur <b>'Post Messages'</b> ki admin permissions hain takki main apna kaam theek se kar sakoon."
                        , parse_mode='HTML')
                    logger.info(f"Bot confirmed admin status in {chat.title} ({chat.id}).")
                else:
                    await chat.send_message(
                        f"Hello! Main <b>{bot_info.first_name}</b> hun. Is group mein moderation ke liye, kripya mujhe <b>admin</b> banayein aur <b>'Delete Messages'</b>, <b>'Restrict Users'</b>, <b>'Post Messages'</b> ki permissions dein."
                        , parse_mode='HTML')
                    logger.warning(f"Bot is not admin in {chat.title} ({chat.id}). Functionality will be limited.")
            except Exception as e:
                logger.error(f"Error during bot's self-introduction in {chat.title} ({chat.id}): {e}")

# --- Tagging Commands ---
async def tag_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message.chat.type not in ['group', 'supergroup']:
        await update.message.reply_text("Yeh command sirf groups mein kaam karti hai.")
        return
    
    is_sender_admin = await is_group_admin(update.message.chat_id, update.effective_user.id, context)
    if not is_sender_admin:
        await update.message.reply_text("Aapke paas is command ko use karne ki permission nahi hai.")
        return
    
    chat_id = update.message.chat_id
    
    try:
        members_count = await context.bot.get_chat_member_count(chat_id)
        message_text = " ".join(context.args) if context.args else "**Attention Everyone!**"
        
        final_message = f"**Is group mein {members_count} members hain.**\n\n**Message:** {message_text}"
        
        sent_message = await update.message.reply_text(
            final_message,
            parse_mode='MarkdownV2'
        )
        
        if chat_id not in TAG_MESSAGES:
            TAG_MESSAGES[chat_id] = []
        TAG_MESSAGES[chat_id].append(sent_message.message_id)
        
    except Exception as e:
        logger.error(f"Error in /tagall command: {e}")
        await update.message.reply_text(f"Tag karte samay error hui: {e}")

async def tag_online(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message.chat.type not in ['group', 'supergroup']:
        await update.message.reply_text("Yeh command sirf groups mein kaam karti hai.")
        return

    is_sender_admin = await is_group_admin(update.message.chat_id, update.effective_user.id, context)
    if not is_sender_admin:
        await update.message.reply_text("Aapke paas is command ko use karne ki permission nahi hai.")
        return
        
    chat_id = update.message.chat_id
    
    try:
        # Online users ko tag karne ke liye bhi koi direct method available nahi hai
        online_message = "**Online users ko tag karne ki suvidha ab Telegram API mein nahi hai.**"
        await update.message.reply_text(online_message, parse_mode='MarkdownV2')
        
    except Exception as e:
        logger.error(f"Error in /onlinetag command: {e}")
        await update.message.reply_text(f"Online members ko tag karte samay error hui: {e}")


async def tag_admins(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message.chat.type not in ['group', 'supergroup']:
        await update.message.reply_text("Yeh command sirf groups mein kaam karti hai.")
        return
        
    message_text = " ".join(context.args) if context.args else "**Admins, attention please!**"
    chat_id = update.message.chat_id

    try:
        admins = await context.bot.get_chat_administrators(chat_id)
        tagged_admins = [admin.user.mention_html() for admin in admins if not admin.user.is_bot]
        
        if not tagged_admins:
            await update.message.reply_text("Is group mein koi admins nahi hain jinhe tag kiya ja sake.")
            return
            
        tag_message_text = " ".join(f"👑 {admin}" for admin in tagged_admins)
        
        if chat_id not in TAG_MESSAGES:
            TAG_MESSAGES[chat_id] = []

        sent_message = await update.message.reply_text(
            f"{tag_message_text}\n\n**Message:** {message_text}",
            parse_mode='HTML'
        )
        TAG_MESSAGES[chat_id].append(sent_message.message_id)
        
    except Exception as e:
        logger.error(f"Error in /admin command: {e}")
        await update.message.reply_text(f"Admins ko tag karte samay error hui: {e}")

async def tag_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message.chat.type not in ['group', 'supergroup']:
        await update.message.reply_text("Yeh command sirf groups mein kaam karti hai.")
        return
    
    chat_id = update.message.chat_id
    is_sender_admin = await is_group_admin(chat_id, update.effective_user.id, context)
    if not is_sender_admin:
        await update.message.reply_text("Aapke paas is command ko use karne ki permission nahi hai.")
        return

    if chat_id not in TAG_MESSAGES or not TAG_MESSAGES[chat_id]:
        await update.message.reply_text("कोई भी टैगिंग मैसेज नहीं मिला जिसे रोका जा सके।")
        return

    try:
        for message_id in TAG_MESSAGES[chat_id]:
            try:
                await context.bot.delete_message(chat_id, message_id)
            except Exception as e:
                logger.warning(f"Failed to delete tag message {message_id} in {chat_id}: {e}")
        
        TAG_MESSAGES.pop(chat_id)

        bot_info = await context.bot.get_me()
        bot_username = bot_info.username
        add_to_group_url = f"https://t.me/{bot_username}?startgroup=true"
        
        final_message_text = "**यह टैगिंग खत्म हो गया है।**"
        
        keyboard = [
            [InlineKeyboardButton("➕ **मुझे ग्रुप में जोड़ें**", url=add_to_group_url)],
            [InlineKeyboardButton("📢 अपडेट चैनल", url="https://t.me/asbhai_bsr")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            final_message_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        logger.info(f"Admin {update.effective_user.id} stopped tagging in chat {chat_id}.")

    except Exception as e:
        logger.error(f"Error in /tagstop command: {e}")
        await update.message.reply_text(f"टैगिंग रोकते समय एक error हुई: {e}")

# --- New Command to check bot permissions ---
async def check_permissions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in ['group', 'supergroup']:
        await update.message.reply_text("यह कमांड केवल ग्रुप्स में काम करती है।")
        return
    
    if not await is_group_admin(chat.id, update.effective_user.id, context):
        await update.message.reply_text("आप ग्रुप एडमिन नहीं हैं, इसलिए आप यह कमांड का उपयोग नहीं कर सकते।")
        return
        
    try:
        bot_member = await chat.get_member(context.bot.id)
        perms = bot_member.permissions
        
        message = (
            f"<b>{chat.title}</b> में बॉट की अनुमतियाँ (Permissions):\n\n"
            f"<b>✅ मैसेज हटा सकता है:</b> {perms.can_delete_messages}\n"
            f"<b>✅ सदस्यों को प्रतिबंधित कर सकता है:</b> {perms.can_restrict_members}\n"
            f"<b>✅ मैसेज पिन कर सकता है:</b> {perms.can_pin_messages}\n"
            f"<b>✅ मैसेज भेज सकता है:</b> {perms.can_send_messages}\n"
        )
        
        await update.message.reply_text(message, parse_mode='HTML')
        logger.info(f"Admin {update.effective_user.id} requested permissions check in chat {chat.id}.")
    except Exception as e:
        logger.error(f"Error checking permissions in chat {chat.id}: {e}")
        await update.message.reply_text(f"अनुमतियाँ जाँचते समय एक error हुई: {e}")


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
        return_document=True
    )
    return warnings_doc['count']

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
async def handle_all_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    user = message.from_user
    chat = message.chat
    message_text = message.text

    if is_admin(user.id) and BROADCAST_MESSAGE.get(user.id) == "waiting_for_message":
        await handle_broadcast_message(update, context)
        return

    if chat.type not in ['group', 'supergroup'] or message.via_bot:
        return
        
    is_sender_admin = await is_group_admin(chat.id, user.id, context)

    # Check for profanity
    if profanity_filter is not None and profanity_filter.contains_profanity(message_text):
        await handle_incident(context, chat.id, user, "गाली-गलौज (Profanity)", message, "abuse")
        return

    # Check for URLs directly in the message
    if URL_PATTERN.search(message_text) and not is_sender_admin:
        await handle_incident(context, chat.id, user, "मैसेज में लिंक (Link in Message)", message, "link_in_message")
        return

    # Ab bio link check karne ka code yahan aayega
    # Pehle checks ko yahan rakhte hain
    if not is_sender_admin and not await is_biolink_whitelisted(user.id):
        try:
            user_profile = await context.bot.get_chat(user.id)
            user_bio = user_profile.bio or ""
            if URL_PATTERN.search(user_bio):
                try:
                    await message.delete()
                    logger.info(f"Deleted message from user with bio link: {user.id}")
                except Exception as e:
                    logger.error(f"Could not delete message for user {user.id}: {e}")
                    
                # Warning system ka logic
                warn_count = await increment_warnings(user.id, chat.id)
                warn_limit = 3 # Aap isse badal sakte hain
                
                # Check for existing warning message
                warnings_doc = db.warnings.find_one({"user_id": user.id, "chat_id": chat.id})
                last_sent_message_id = warnings_doc.get("last_sent_message_id") if warnings_doc else None

                warning_text = (
                    "**🚨 Chetavni** 🚨\n\n"
                    f"👤 **User:** {user.mention_html()} (`{user.id}`)\n"
                    "❌ **Karan:** Bio mein link mila\n"
                    f"⚠️ **Chetavni:** {warn_count}/{warn_limit}\n\n"
                    "**Notice: Kripya apne bio se links hata dein.**"
                )
                
                # Buttons
                keyboard = [
                    [
                        InlineKeyboardButton("❌ Chetavni Cancel", callback_data=f"cancel_warn_{user.id}"),
                        InlineKeyboardButton("✅ Bio Link Approve", callback_data=f"approve_bio_{user.id}_{chat.id}")
                    ],
                    [InlineKeyboardButton("🗑️ Band Karen", callback_data=f"close_message_{message.message_id}")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                sent_message = await message.reply_text(warning_text, reply_markup=reply_markup, parse_mode='HTML')
                
                # Update the warning message ID in the database for later editing
                db.warnings.update_one(
                    {"user_id": user.id, "chat_id": chat.id},
                    {"$set": {"last_sent_message_id": sent_message.message_id}}
                )

                if warn_count >= warn_limit:
                    try:
                        await context.bot.restrict_chat_member(
                            chat_id=chat.id,
                            user_id=user.id,
                            permissions=ChatPermissions(can_send_messages=False)
                        )
                        # Remove the bio link exception if any existed
                        await remove_biolink_whitelist(user.id)
                        await reset_warnings(user.id, chat.id)
                        
                        mute_text = (
                            f"**{user.mention_html()}** ko **mute** kar diya gaya hai kyunki unhone bio link ke liye {warn_limit} warnings cross kar di hain."
                        )
                        await sent_message.edit_text(mute_text, parse_mode='HTML', reply_markup=None)
                    except Exception as e:
                        logger.error(f"Error muting user {user.id} after warnings: {e}")
                        await sent_message.edit_text(
                            f"Bot ke paas {user.mention_html()} ko mute karne ki permission nahi hai.",
                            parse_mode='HTML'
                        )
                return
        except BadRequest as e:
            logger.warning(f"Could not get chat info for user {user.id}: {e}")
        except Exception as e:
            logger.error(f"Error checking user bio for user {user.id} in chat {chat.id}: {e}")
    else:
        # Agar user ka bio sahi hai, toh uski warnings reset kar do
        if await get_warnings(user.id, chat.id) > 0:
            await reset_warnings(user.id, chat.id)
            logger.info(f"Warnings reset for user {user.id} as their bio is clean.")


# --- Handler for Edited Messages ---
async def handle_edited_messages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    edited_message = update.edited_message
    if not edited_message or edited_message.chat.type not in ['group', 'supergroup'] or edited_message.via_bot:
        return

    user = edited_message.from_user
    chat = edited_message.chat
    
    # Check if the user is an admin before handling edited message
    is_sender_admin = await is_group_admin(chat.id, user.id, context)
    if not is_sender_admin:
        try:
            await edited_message.delete()
            logger.info(f"Deleted edited message from non-admin user {user.id} in chat {chat.id}.")
        except Exception as e:
            logger.error(f"Error deleting edited message in {chat.id}: {e}. Bot needs 'Delete Messages' permission.")
            
        # Iske baad aap chahe toh notification bhej sakte hain
        notification_message = f"🚨 {user.mention_html()} ne ek message edit kiya jo delete kar diya gaya hai."
        await context.bot.send_message(chat_id, notification_message, parse_mode='HTML')


# --- Callback Query Handlers ---
async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = query.from_user.id
    chat_id = query.message.chat_id

    # Check for admin status if the action is group-related
    if query.message.chat.type in ['group', 'supergroup'] and not data.startswith(('help_menu', 'other_bots', 'donate_info', 'back_to_main_menu')):
        is_current_group_admin = await is_group_admin(chat_id, user_id, context)
        if not is_current_group_admin:
            await query.edit_message_text("Aapke paas is action ko karne ki permission nahi hai. Aap group admin nahi hain.")
            logger.warning(f"Non-admin user {user_id} tried to use admin button in chat {chat_id}.")
            return

    if data == "help_menu":
        help_text = (
            "<b>Bot Help Menu:</b>\n\n"
            "<b>• Gaali detection:</b> Automatic message deletion for profanity.\n"
            "<b>• Bio Link Detection:</b> Automatically deletes messages from users with links in their bio (Admins are exempt).\n"
            "<b>• Edited Message Deletion:</b> Deletes any edited message from non-admins to prevent rule-breaking edits.\n"
            "<b>• Admin Actions:</b> Mute, ban, kick users directly from the group notification.\n"
            "<b>• Incident Logging:</b> All violations are logged in a dedicated case channel.\n\n"
            "<b>Commands:</b>\n"
            "• `/start`: Bot ko start karein (private aur group mein).\n"
            "• `/stats`: Bot usage stats dekhein (sirf bot admins ke liye).\n"
            "• `/broadcast`: Sabhi groups mein message bhejein (sirf bot admins ke liye).\n"
            f"• `/addabuse &lt;shabd&gt;`: Custom gaali wala shabd filter mein add karein (sirf bot admins ke liye).\n"
            f"• `/checkperms`: Group mein bot ki permissions jaanchein (sirf group admins ke liye).\n"
            "• `/tagall &lt;message&gt;`: Sabhi members ko tag karne ki koshish (Online members ko message bheja ja sakta hai).\n"
            "• `/admin &lt;message&gt;`: Sirf group admins ko tag karein.\n"
            "• `/tagstop`: Saare tagging messages ko delete kar dein."
        )
        keyboard = [
            [InlineKeyboardButton("⬅️ Back", callback_data="back_to_main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(help_text, reply_markup=reply_markup, parse_mode='HTML')

    elif data == "other_bots":
        other_bots_text = (
            "<b>Mere kuch aur bots:</b>\n\n"
            "• <b>Movies & Webseries:</b> <a href='https://t.me/asflter_bot'>@asflter_bot</a>\n"
            "  <i>Ye hai sabhi movies, webseries, anime, Korean drama, aur sabhi TV show sabhi languages mein yahan milte hain.</i>\n\n"
            "• <b>Chat Bot:</b> <a href='https://t.me/askiangelbot'>@askiangelbot</a>\n"
            "  <i>Ye bot group par chat karti hai aur isme acche acche group manage karne ke liye commands hain.</i>\n"
        )
        keyboard = [
            [InlineKeyboardButton("⬅️ Back", callback_data="back_to_main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(other_bots_text, reply_markup=reply_markup, parse_mode='HTML')

    elif data == "donate_info":
        donate_text = (
            "<b>💖 Bot ko support karein!</b>\n\n"
            "Agar aapko ye bot pasand aaya hai to aap humein kuch paisa de sakte hain "
            "jisse hum is bot ko aage tak chalate rahein.\n\n"
            "<b>Donation Methods:</b>\n"
            "• UPI: <code>arsadsaifi8272@ibl</code>\n\n"
            "Aapka har sahyog value karta hai! Dhanyawad!"
        )
        keyboard = [
            [InlineKeyboardButton("⬅️ Back", callback_data="back_to_main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(donate_text, reply_markup=reply_markup, parse_mode='HTML')

    elif data == "back_to_main_menu":
        bot_info = await context.bot.get_me()
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
            [InlineKeyboardButton("📈 **Promotion**", url="https://t.me/asprmotion")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(welcome_message, reply_markup=reply_markup, parse_mode='HTML')

    elif data.startswith("admin_actions_menu_"):
        parts = data.split('_')
        target_user_id = int(parts[3])
        group_chat_id = int(parts[4])
        
        target_user = await context.bot.get_chat_member(group_chat_id, target_user_id)
        target_user_name = target_user.user.full_name
        
        # Check if the user is already an exception
        is_biolink_approved = db and db.biolink_exceptions and db.biolink_exceptions.find_one({"user_id": target_user_id})

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
        
        # Add the new button for bio-link approval
        if is_biolink_approved:
            actions_keyboard.append([InlineKeyboardButton("✅ Approved Bio User", callback_data=f"unapprove_bio_{target_user_id}_{group_chat_id}")])
        else:
            actions_keyboard.append([InlineKeyboardButton("✍️ Approved Bio User", callback_data=f"approve_bio_{target_user_id}_{group_chat_id}")])

        actions_keyboard.append([InlineKeyboardButton("⬅️ Back to Notification", callback_data=f"back_to_notification_{target_user_id}_{group_chat_id}")])
        
        reply_markup = InlineKeyboardMarkup(actions_keyboard)
        await query.edit_message_text(actions_text, reply_markup=reply_markup, parse_mode='HTML')

    elif data.startswith("approve_bio_"):
        if not is_current_group_admin:
            await query.edit_message_text("❌ Aapke paas is action ko karne ki permission nahi hai.")
            return

        target_user_id = int(data.split('_')[2])
        await add_biolink_whitelist(target_user_id)
        await reset_warnings(target_user_id, chat_id)
        
        target_user = await context.bot.get_chat_member(chat_id, target_user_id)
        mention = target_user.user.mention_html()

        keyboard = [
            [
                InlineKeyboardButton("🚫 Bio Link Unapprove", callback_data=f"unapprove_bio_{target_user_id}_{chat_id}"),
                InlineKeyboardButton("🗑️ Band Karen", callback_data=f"close_message_{query.message.message_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"✅ {mention} (`{target_user_id}`) ko bio link exceptions list mein add kar diya gaya hai.",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        return

    elif data.startswith("unapprove_bio_"):
        if not is_current_group_admin:
            await query.edit_message_text("❌ Aapke paas is action ko karne ki permission nahi hai.")
            return

        target_user_id = int(data.split('_')[2])
        await remove_biolink_whitelist(target_user_id)

        target_user = await context.bot.get_chat_member(chat_id, target_user_id)
        mention = target_user.user.mention_html()
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Bio Link Approve", callback_data=f"approve_bio_{target_user_id}_{chat_id}"),
                InlineKeyboardButton("🗑️ Band Karen", callback_data=f"close_message_{query.message.message_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"❌ {mention} (`{target_user_id}`) ko bio link exceptions list se hata diya gaya hai.",
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        return

    elif data.startswith("close_message_"):
        if not is_current_group_admin:
            await query.answer("❌ Aapke paas is action ko karne ki permission nahi hai.")
            return
        
        message_id_to_delete = int(data.split('_')[2])
        try:
            await context.bot.delete_message(chat_id, message_id_to_delete)
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
            await context.bot.restrict_chat_member(
                chat_id=group_chat_id,
                user_id=target_user_id,
                permissions=permissions,
                until_date=until_date
            )
            target_user = await context.bot.get_chat_member(group_chat_id, target_user_id)
            await query.edit_message_text(f"✅ {target_user.user.mention_html()} ko {duration_str} ke liye mute kar diya gaya hai.", parse_mode='HTML')
            logger.info(f"Admin {user_id} muted user {target_user_id} in chat {group_chat_id} for {duration_str}.")
        except Exception as e:
            await query.edit_message_text(f"Mute karte samay error hui: {e}")
            logger.error(f"Error muting user {target_user_id} in {group_chat_id}: {e}")

    elif data.startswith("ban_"):
        parts = data.split('_')
        target_user_id = int(parts[1])
        group_chat_id = int(parts[2])
        try:
            await context.bot.ban_chat_member(chat_id=group_chat_id, user_id=target_user_id)
            target_user = await context.bot.get_chat_member(group_chat_id, target_user_id)
            await query.edit_message_text(f"✅ {target_user.user.mention_html()} ko group se ban kar diya gaya hai.", parse_mode='HTML')
            logger.info(f"Admin {user_id} banned user {target_user_id} from chat {group_chat_id}.")
        except Exception as e:
            await query.edit_message_text(f"Ban karte samay error hui: {e}")
            logger.error(f"Error banning user {target_user_id} from {group_chat_id}: {e}")

    elif data.startswith("kick_"):
        parts = data.split('_')
        target_user_id = int(parts[1])
        group_chat_id = int(parts[2])
        try:
            await context.bot.unban_chat_member(chat_id=group_chat_id, user_id=target_user_id, only_if_banned=False)
            target_user = await context.bot.get_chat_member(group_chat_id, target_user_id)
            await query.edit_message_text(f"✅ {target_user.user.mention_html()} ko group se nikal diya gaya hai.", parse_mode='HTML')
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
            target_user = await context.bot.get_chat_member(group_chat_id, target_user_id)
            
            # Update warning count for the user
            warnings_doc = db.warnings.find_one_and_update(
                {"user_id": target_user_id, "chat_id": group_chat_id},
                {"$inc": {"count": 1}, "$set": {"last_warned": datetime.now()}},
                upsert=True,
                return_document=True
            )
            warn_count = warnings_doc['count'] if warnings_doc else 1
            
            warn_message = (
                f"🚨 **Chetavni**\n\n"
                f"➡️ {target_user.user.mention_html()}, aapko group ke niyam todne ke liye chetavni di jaati hai. Please group ke rules follow karein.\n\n"
                f"➡️ <b>Yeh aapki {warn_count}vi chetavni hai.</b>"
            )
            
            await context.bot.send_message(chat_id=group_chat_id, text=warn_message, parse_mode='HTML')
            
            # Check if user has reached 3 warnings
            if warn_count >= 3:
                permissions = ChatPermissions(can_send_messages=False, can_send_media_messages=False, can_send_polls=False, can_send_other_messages=False)
                await context.bot.restrict_chat_member(
                    chat_id=group_chat_id,
                    user_id=target_user_id,
                    permissions=permissions
                )
                permanent_mute_message = (
                    f"❌ **Permanent Mute**\n\n"
                    f"➡️ {target_user.user.mention_html()}, aapko 3 warnings mil chuki hain. Isliye aapko group mein permanent mute kar diya gaya hai."
                )
                await context.bot.send_message(chat_id=group_chat_id, text=permanent_mute_message, parse_mode='HTML')
                await query.edit_message_text(f"✅ {target_user.user.mention_html()} ko {warn_count} chetavaniyan milne ke baad permanent mute kar diya gaya hai.", parse_mode='HTML')
                logger.info(f"User {target_user_id} was permanently muted after 3 warnings in chat {group_chat_id}.")
            else:
                await query.edit_message_text(f"✅ {target_user.user.mention_html()} ko chetavni bhej di gayi hai. Warnings: {warn_count}/3.", parse_mode='HTML')
                logger.info(f"Admin {user_id} warned user {target_user_id} in chat {group_chat_id}. Current warnings: {warn_count}.")
                
        except Exception as e:
            await query.edit_message_text(f"Chetavni bhejte samay error hui: {e}")
            logger.error(f"Error warning user {target_user_id} in {group_chat_id}: {e}")

    elif data.startswith("back_to_notification_"):
        parts = data.split('_')
        target_user_id = int(parts[4])
        group_chat_id = int(parts[5])

        incident_data = None
        if db and db.incidents:
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

        user_obj = await context.bot.get_chat_member(group_chat_id, target_user_id)

        notification_message = (
            f"🚨 **Group mein Niyam Ulanghan!**\n\n"
            f"➡️ <b>User:</b> {user_obj.user.mention_html()}\n"
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
        await query.edit_message_text(notification_message, reply_markup=reply_markup, parse_mode='HTML')

    elif data == "confirm_broadcast":
        await confirm_broadcast(update, context)
    elif data == "cancel_broadcast":
        await cancel_broadcast(update, context)


# --- Flask App for Health Check ---
@app.route('/')
def health_check():
    """Simple health check endpoint for Koyeb."""
    return jsonify({"status": "healthy", "bot_running": application is not None, "mongodb_connected": db is not None}), 200

def run_flask_app():
    """Runs the Flask application."""
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)

# --- Main Bot Runner ---
def run_bot():
    global application
    if TELEGRAM_BOT_TOKEN is None:
        logger.error("TELEGRAM_BOT_TOKEN environment variable is not set. Bot cannot start.")
        return

    try:
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

        # Command Handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("stats", stats))
        application.add_handler(CommandHandler("broadcast", broadcast_command))
        application.add_handler(CommandHandler("addabuse", add_abuse_word))
        application.add_handler(CommandHandler("tagall", tag_all))
        application.add_handler(CommandHandler("onlinetag", tag_online))
        application.add_handler(CommandHandler("admin", tag_admins))
        application.add_handler(CommandHandler("tagstop", tag_stop))
        application.add_handler(CommandHandler("checkperms", check_permissions))


        # Message Handlers
        application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND & (filters.ChatType.GROUP | filters.ChatType.SUPERGROUP),
            handle_all_messages
        ))
        application.add_handler(MessageHandler(
            (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL) &
            filters.ChatType.PRIVATE & 
            filters.User(user_id=ADMIN_USER_IDS), 
            handle_broadcast_message
        ))
        # Edited Message Handler
        application.add_handler(MessageHandler(
            filters.Update.EDITED_MESSAGE,
            handle_edited_messages
        ))

        # Callback Query Handler for inline buttons
        application.add_handler(CallbackQueryHandler(button_callback_handler))

        logger.info("Bot is starting polling...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")

# --- Entry Point ---
if __name__ == "__main__":
    init_mongodb()
    flask_thread = threading.Thread(target=run_flask_app)
    flask_thread.daemon = True
    flask_thread.start()
    run_bot()
