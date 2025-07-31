import os
import time
from datetime import datetime, timedelta
import threading
import asyncio
import logging
from pymongo import MongoClient
from telegram.error import BadRequest, Forbidden, TelegramError

from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions, WebAppInfo, constants
from telegram.ext import (
    CommandHandler, MessageHandler, filters, CallbackContext,
    CallbackQueryHandler, Application
)

# Custom module import
# Ensure this file (profanity_filter.py) is present in your deployment
from profanity_filter import ProfanityFilter

# --- Configuration ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
# Log Channel ID - Bot ke saare logs yahan aayenge
LOG_CHANNEL_ID = -1002352329534 # Replace with your actual Log Channel ID
# Case Channel ID - Jab koi gaali dega, uski details yahan aayengi
CASE_CHANNEL_ID = -1002717243409 # Replace with your actual Case Channel ID
CASE_CHANNEL_USERNAME = "AbusersDetector" # Replace with your actual Case Channel Username (without @)
MONGO_DB_URI = os.getenv("MONGO_DB_URI")
# Admin username to mention in group warning messages
GROUP_ADMIN_USERNAME = os.getenv("GROUP_ADMIN_USERNAME", "admin") # Change 'admin' to your group admin's username or a placeholder

# List of user IDs who are bot admins (can use /stats, /broadcast, /addabuse etc.)
ADMIN_USER_IDS = [7315805581] # Replace with your Telegram User ID(s)

bot_start_time = datetime.now()
BROADCAST_MESSAGE = {}

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

        # Create collections if they don't exist and ensure indexes
        collection_names = db.list_collection_names()

        if "groups" not in collection_names:
            db.create_collection("groups")
        db.groups.create_index("chat_id", unique=True)
        logger.info("MongoDB 'groups' collection unique index created/verified.")

        if "users" not in collection_names: # FIX STARTS HERE (Ensuring 'users' collection exists)
            db.create_collection("users")
        db.users.create_index("user_id", unique=True)
        logger.info("MongoDB 'users' collection unique index created/verified.") # FIX ENDS HERE

        if "incidents" not in collection_names:
            db.create_collection("incidents")
        db.incidents.create_index("case_id", unique=True)
        logger.info("MongoDB 'incidents' collection unique index created/verified.")

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

async def is_group_admin(chat_id: int, user_id: int, context: CallbackContext) -> bool:
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

# --- Bot Commands Handlers ---
async def start(update: Update, context: CallbackContext) -> None:
    """Handles the /start command."""
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
            [InlineKeyboardButton("❓ Help", callback_data="help_menu")],
            [InlineKeyboardButton("🤖 Other Bots", callback_data="other_bots")],
            [InlineKeyboardButton("📢 Update Channel", url="https://t.me/asbhai_bsr")],
            [InlineKeyboardButton("💖 Donate", callback_data="donate_info")],
            [InlineKeyboardButton("📈 Promotion", url="https://t.me/asprmotion")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            text=welcome_message,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        logger.info(f"User {user.first_name} ({user.id}) started the bot in private chat.")

        if db is not None and db.users is not None:
            try:
                db.users.update_one(
                    {"user_id": user.id},
                    {"$set": {"first_name": user.first_name, "username": user.username, "last_interaction": datetime.now()}},
                    upsert=True
                )
                logger.info(f"User {user.id} data updated/added in DB (from start command).")
            except Exception as e:
                logger.error(f"Error saving user {user.id} to DB (from start command): {e}")
        else:
            logger.warning("MongoDB 'users' collection not available. User data not saved (from start command).")

        log_message = (
            f"<b>✨ New User Started Bot:</b>\n"
            f"User: {user.mention_html()} (<code>{user.id}</code>)\n"
            f"Username: @{user.username if user.username else 'N/A'}\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}"
        )
        await log_to_channel(log_message, parse_mode='HTML')

    elif chat.type in ['group', 'supergroup']:
        bot_member = await chat.get_member(bot_info.id)
        if bot_member.status in ['administrator', 'creator']:
            group_start_message = (
                f"Hello! Main <b>{bot_name}</b> hun, aapka group moderation bot. "
                f"Main aapke group ko saaf suthra rakhne mein madad karunga."
            )
        else:
            group_start_message = (
                f"Hello! Main <b>{bot_name}</b> hun. Is group mein moderation ke liye, kripya mujhe <b>admin</b> banayein aur <b>'Delete Messages'</b>, <b>'Restrict Users'</b>, <b>'Post Messages'</b> ki permissions dein."
            )

        add_to_group_url = f"https://t.me/{bot_username}?startgroup=true"

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

async def stats(update: Update, context: CallbackContext) -> None:
    """Sends bot usage statistics to authorized admins."""
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
    logger.info(f"Admin {update.effective_user.id} requested stats. Groups: {total_groups}, Users: {total_users}, Incidents: {total_incidents}.")

async def broadcast_command(update: Update, context: CallbackContext) -> None:
    """Initiates the broadcast process for admins."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Aapke paas is command ko use karne ki permission nahi hai.")
        return
    if update.message.chat.type != 'private':
        await update.message.reply_text("Broadcast command sirf private chat mein hi shuru ki ja sakti hai.")
        return
    await update.message.reply_text("Kripya apna message bhejein jo sabhi groups aur users par broadcast karna hai.")
    BROADCAST_MESSAGE[update.effective_user.id] = None # Mark as waiting for message
    logger.info(f"Admin {update.effective_user.id} initiated broadcast.")

async def confirm_broadcast(update: Update, context: CallbackContext) -> None:
    """Confirms and executes the broadcast."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if not is_admin(user_id) or BROADCAST_MESSAGE.get(user_id) is None:
        await query.edit_message_text("Invalid action or broadcast message not found.")
        return

    broadcast_msg = BROADCAST_MESSAGE.pop(user_id)
    if broadcast_msg:
        if db is None:
            await query.edit_message_text("Broadcast ke liye MongoDB collections available nahi hai. Broadcast nahi kar sakte.")
            logger.error("MongoDB collections not available for broadcast.")
            return

        target_chats = []
        
        # Fetch group IDs
        group_ids = []
        try:
            if db.groups is not None:
                for doc in db.groups.find({}, {"chat_id": 1}):
                    group_ids.append(doc['chat_id'])
            logger.info(f"Fetched {len(group_ids)} group IDs from DB for broadcast.")
        except Exception as e:
            logger.error(f"Error fetching group IDs from DB for broadcast: {e}")
            group_ids = [] # Ensure it's an empty list on error

        # Fetch user IDs (private chats)
        user_ids = []
        try:
            if db.users is not None:
                for doc in db.users.find({}, {"user_id": 1}):
                    # Ensure we don't try to send to the bot admin who initiated broadcast or other special users
                    if doc['user_id'] != user_id: 
                        user_ids.append(doc['user_id'])
            logger.info(f"Fetched {len(user_ids)} user IDs from DB for broadcast.")
        except Exception as e:
            logger.error(f"Error fetching user IDs from DB for broadcast: {e}")
            user_ids = [] # Ensure it's an empty list on error
        
        target_chats.extend(group_ids)
        target_chats.extend(user_ids)

        if not target_chats:
            await query.edit_message_text("Broadcast ke liye koi target group/user IDs database mein nahi mile. Kripya ensure karein bot groups mein added hai aur users ne bot ko start kiya hai.")
            logger.warning(f"Admin {user_id} tried to broadcast but no target chat IDs found in DB.")
            return

        success_count = 0
        fail_count = 0

        await query.message.reply_text(f"Broadcast shuru ho raha hai. Sabhi groups aur users mein bheja ja raha hai... (Total targets: {len(target_chats)})")

        for chat_id in target_chats:
            try:
                # Use copy_message as it handles various message types (text, photo, video, etc.)
                await context.bot.copy_message(
                    chat_id=chat_id,
                    from_chat_id=broadcast_msg.chat.id,
                    message_id=broadcast_msg.message_id
                )
                success_count += 1
                await asyncio.sleep(0.1) # Small delay to avoid FloodWait
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

        await query.message.reply_text(f"Broadcast complete! Successfully sent to {success_count} chats. Failed: {fail_count}.")
        logger.info(f"Broadcast initiated by {user_id} completed. Success: {success_count}, Failed: {fail_count}.")
    else:
        await query.edit_message_text("Broadcast message not found.")


async def add_abuse_word(update: Update, context: CallbackContext) -> None:
    """Allows bot admins to add custom abuse words to the filter."""
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


async def welcome_new_member(update: Update, context: CallbackContext) -> None:
    """Welcomes new members and handles bot's addition to a group."""
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
                    logger.info(f"Group {chat.id} data updated/added in DB (from bot joining).")
                except Exception as e:
                    logger.error(f"Error saving group {chat.id} to DB (from bot joining): {e}")
            else:
                logger.warning("MongoDB 'groups' collection not available. Group data not saved (from bot joining).")

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

# --- Core Message Handler (Profanity Detection and Action) ---
async def handle_all_messages(update: Update, context: CallbackContext) -> None:
    """Processes all incoming messages for profanity and handles broadcast replies."""
    user = update.message.from_user
    chat = update.message.chat
    message_text = update.message.text # Original message text

    # Handle broadcast message input from admin
    if is_admin(user.id) and user.id in BROADCAST_MESSAGE and BROADCAST_MESSAGE[user.id] is None:
        if update.message.text or update.message.photo or update.message.video or update.message.document:
            BROADCAST_MESSAGE[user.id] = update.message
            await update.message.reply_text(
                "Message received. Kya aap ise broadcast karna chahenge?",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Yes, Broadcast!", callback_data="confirm_broadcast")]])
            )
        else:
            await update.message.reply_text("Kripya ek text message, photo, video, ya document bhejein broadcast karne ke liye.")
        return

    # Process messages for profanity only in groups/supergroups
    # and ignore messages sent by other bots (including Telegram's own service messages if via_bot is set)
    if chat.type in ['group', 'supergroup'] and message_text and not update.message.via_bot:
        if profanity_filter is not None and profanity_filter.contains_profanity(message_text):
            original_message_id = update.message.message_id

            # --- 1. Message delete karne ki koshish karein ---
            try:
                await context.bot.delete_message(chat_id=chat.id, message_id=original_message_id)
                logger.info(f"Deleted abusive message from {user.username or user.full_name} ({user.id}) in {chat.title} ({chat.id}).")
            except Exception as e:
                logger.error(f"Error deleting message in {chat.title} ({chat.id}): {e}. Make sure the bot has 'Delete Messages' admin permission.")

            case_id_value = str(int(datetime.now().timestamp() * 1000))

            sent_details_msg = None
            forwarded_message_id = None # Store the ID of the message sent to case channel
            case_detail_url = f"https://t.me/{CASE_CHANNEL_USERNAME}" # Fallback URL

            try:
                # --- 2. Case Channel Mein Detail Message Bhejेंगे (Gaali ke Spoiler ke Saath) ---
                details_message_text = (
                    f"🚨 <b>नया उल्लंघन (Violation)</b> 🚨\n\n"
                    f"<b>📍 ग्रुप:</b> {chat.title} (<code>{chat.id}</code>)\n"
                    f"<b>👤 यूज़र:</b> {user.mention_html()} (<code>{user.id}</code>)\n"
                    f"<b>📝 यूज़रनेम:</b> @{user.username if user.username else 'N/A'}\n"
                    f"<b>⏰ समय:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}\n"
                    f"<b>🆔 केस ID:</b> <code>{case_id_value}</code>\n\n"
                    # --- YAHAN BADLAV KIYA GAYA HAI ---
                    # Original message content ko spoiler format mein add karein
                    f"<b>➡️ मूल मैसेज:</b> ||{message_text}||\n"
                )
                sent_details_msg = await context.bot.send_message(
                    chat_id=CASE_CHANNEL_ID,
                    text=details_message_text,
                    parse_mode='HTML' # HTML parse mode is needed for ||spoiler|| syntax
                )
                forwarded_message_id = sent_details_msg.message_id # Yeh message hi hamara "forwarded" message hai

                # Direct link to the message in the case channel
                if sent_details_msg:
                    # Telegram channel links format: t.me/c/CHANNEL_ID_WITHOUT_100/MESSAGE_ID
                    # CASE_CHANNEL_ID is typically -100xxxxxxxxxx. Remove -100.
                    channel_link_id = str(CASE_CHANNEL_ID).replace('-100', '')
                    case_detail_url = f"https://t.me/c/{channel_link_id}/{sent_details_msg.message_id}"
                    logger.info(f"Abusive message content sent to case channel with spoiler. Generated URL: {case_detail_url}")
                else:
                    logger.warning("Details message object is None after send_message call. Falling back to default channel URL.")
                    case_detail_url = f"https://t.me/{CASE_CHANNEL_USERNAME}"

            except Forbidden as e:
                logger.error(f"TelegramError (Forbidden) in handle_all_messages: {e}. Bot does not have permission to send messages to channel {CASE_CHANNEL_ID}. Please check 'Post Messages' admin permission.")
                case_detail_url = f"https://t.me/{CASE_CHANNEL_USERNAME}"
            except BadRequest as e:
                logger.error(f"TelegramError (BadRequest) in handle_all_messages: {e}. This might be due to an invalid CASE_CHANNEL_ID or formatting issue. Please verify.")
                case_detail_url = f"https://t.me/{CASE_CHANNEL_USERNAME}"
            except TelegramError as e:
                logger.error(f"General TelegramError in handle_all_messages: {e}. Ensure bot is admin in case channel ({CASE_CHANNEL_ID}) and has 'Post Messages' permission, and bot token is valid.")
                case_detail_url = f"https://t.me/{CASE_CHANNEL_USERNAME}"
            except Exception as e:
                logger.error(f"An unexpected error occurred during message processing in handle_all_messages: {e}")
                case_detail_url = f"https://t.me/{CASE_CHANNEL_USERNAME}"

            # --- 3. Log the incident in MongoDB ---
            if db is not None and db.incidents is not None:
                try:
                    db.incidents.insert_one({
                        "case_id": case_id_value,
                        "user_id": user.id,
                        "user_name": user.full_name,
                        "user_username": user.username,
                        "chat_id": chat.id,
                        "chat_title": chat.title,
                        "original_message_id": original_message_id,
                        "abusive_content": message_text, # Original message content (for records)
                        "timestamp": datetime.now(),
                        "status": "pending_review",
                        "case_channel_message_id": forwarded_message_id # Store ID of the message sent with spoiler text
                    })
                    logger.info(f"Incident {case_id_value} logged in DB.")
                except Exception as e:
                    logger.error(f"Error logging incident {case_id_value} to DB: {e}")

            # --- 4. Send notification to the original group with the direct link ---
            notification_message = (
                f"⛔ <b>Group Niyam Ulanghan</b>\n\n"
                f"{user.mention_html()} (<code>{user.id}</code>) ne aise shabdon ka istemaal kiya hai jo group ke niyam ke khilaaf hain. Message ko hata diya gaya hai.\n\n"
                f"@{GROUP_ADMIN_USERNAME}, kripya sadasya ke vyavhaar ki samiksha karein.\n\n"
                f"<b>Case ID:</b> <code>{case_id_value}</code>"
            )

            keyboard = [
                [
                    InlineKeyboardButton("👤 User Profile", url=f"tg://user?id={user.id}"),
                    InlineKeyboardButton("🔧 Admin Actions", callback_data=f"admin_actions_menu_{user.id}_{chat.id}")
                ],
                [
                    InlineKeyboardButton("📄 View Case Details", url=case_detail_url)
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            try:
                # Send the notification message in the original group
                await context.bot.send_message(
                    chat_id=chat.id,
                    text=notification_message,
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )

                # --- YAHAN SE 'Check Case ⬆️' WALA EXTRA MESSAGE HATA DIYA HAI ---
                logger.info(f"Abusive message detected and handled for user {user.id} in chat {chat.id}. Case ID: {case_id_value}. Notification sent (without 'Check Case ⬆️').")
            except Exception as e:
                logger.error(f"Error sending profanity notification in chat {chat.id}: {e}. Make sure bot has 'Post Messages' permission.")
        elif profanity_filter is None:
            logger.warning("Profanity filter not initialized. Skipping profanity check in group.")

# --- Callback Query Handlers ---
async def button_callback_handler(update: Update, context: CallbackContext) -> None:
    """Handles all inline keyboard button presses."""
    query = update.callback_query
    await query.answer() # Acknowledge the button press

    data = query.data
    user_id = query.from_user.id
    chat_id = query.message.chat_id

    # --- Check if the user clicking the button is an admin of the group where the message originated ---
    # This is crucial for security to prevent non-admins from using moderation buttons
    if query.message.chat.type in ['group', 'supergroup']:
        is_current_group_admin = await is_group_admin(chat_id, user_id, context)
        if not is_current_group_admin:
            await query.edit_message_text("Aapke paas is action ko karne ki permission nahi hai. Aap group admin nahi hain.")
            logger.warning(f"Non-admin user {user_id} tried to use admin button in chat {chat_id}.")
            return
    elif query.message.chat.type == 'private' and not is_admin(user_id):
        # Allow bot admins to use broadcast confirm in private chat
        # This condition already handles non-bot-admins in private chat for other buttons
        # For 'confirm_broadcast' specifically, this check is handled within that function.
        # For other private chat buttons, it's generally fine for non-admins to click unless specific logic is needed.
        pass # Keep this for now, if you add admin-only buttons in private chat later, re-evaluate.


    # --- Handle specific callbacks ---
    if data == "help_menu":
        help_text = (
            "<b>Bot Help Menu:</b>\n\n"
            "• Gaali detection: Automatic message deletion for profanity.\n"
            "• Admin Actions: Mute, ban, kick users directly from the group notification.\n"
            "• Incident Logging: All violations are logged in a dedicated case channel.\n\n"
            "<b>Commands:</b>\n"
            "• `/start`: Bot ko start karein (private aur group mein).\n"
            "• `/stats`: Bot usage stats dekhein (sirf bot admins ke liye).\n"
            "• `/broadcast`: Sabhi groups mein message bhejein (sirf bot admins ke liye).\n"
            f"• `/addabuse &lt;shabd&gt;`: Custom gaali wala shabd filter mein add karein (sirf bot admins ke liye)." # FIXED: Escaped < and >
        )
        keyboard = [
            [InlineKeyboardButton("⬅️ Back", callback_data="back_to_main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(help_text, reply_markup=reply_markup, parse_mode='HTML')

    elif data == "other_bots":
        other_bots_text = (
            "<b>Mere kuch aur bots:</b>\n\n"
            "• <b>Movies & Webseries:</b> @asflter_bot\n"
            "  <i>Ye hai sabhi movies, webseries, anime, Korean drama, aur sabhi TV show sabhi languages mein yahan milte hain.</i>\n\n"
            "• <b>Chat Bot:</b> @askiangelbot\n"
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
            "• UPI: `arsadsaifi8272@ibl`\n\n"
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
            [InlineKeyboardButton("❓ Help", callback_data="help_menu")],
            [InlineKeyboardButton("🤖 Other Bots", callback_data="other_bots")],
            [InlineKeyboardButton("📢 Update Channel", url="https://t.me/asbhai_bsr")],
            [InlineKeyboardButton("💖 Donate", callback_data="donate_info")],
            [InlineKeyboardButton("📈 Promotion", url="https://t.me/asprmotion")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(welcome_message, reply_markup=reply_markup, parse_mode='HTML')

    elif data.startswith("admin_actions_menu_"):
        parts = data.split('_')
        target_user_id = int(parts[3])
        group_chat_id = int(parts[4])
        
        # Fetch target user's details for display
        target_user = await context.bot.get_chat_member(group_chat_id, target_user_id)
        target_user_name = target_user.user.full_name
        
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
            [InlineKeyboardButton("⬅️ Back to Notification", callback_data=f"back_to_notification_{target_user_id}_{group_chat_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(actions_keyboard)
        await query.edit_message_text(actions_text, reply_markup=reply_markup, parse_mode='HTML')

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

            # Set user permissions to send no messages
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
            # await context.bot.kick_chat_member(chat_id=group_chat_id, user_id=target_user_id) # Deprecated
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
        try:
            target_user = await context.bot.get_chat_member(group_chat_id, target_user_id)
            warn_message = f"❗ Warning ❗\n\n{target_user.user.mention_html()}, aapko group ke niyam todne ke liye chetavni di jaati hai. Kripya niyam follow karein."
            await context.bot.send_message(chat_id=group_chat_id, text=warn_message, parse_mode='HTML')
            await query.edit_message_text(f"✅ {target_user.user.mention_html()} ko chetavni bhej di gayi hai.", parse_mode='HTML')
            logger.info(f"Admin {user_id} warned user {target_user_id} in chat {group_chat_id}.")
        except Exception as e:
            await query.edit_message_text(f"Chetavni bhejte samay error hui: {e}")
            logger.error(f"Error warning user {target_user_id} in {group_chat_id}: {e}")

    elif data.startswith("back_to_notification_"):
        parts = data.split('_')
        target_user_id = int(parts[4]) # This user ID is from the original notification
        group_chat_id = int(parts[5]) # This chat ID is from the original notification

        # Reconstruct the original notification message and keyboard
        # Fetch incident details from DB using chat_id and user_id to get the case_id and case_detail_url
        incident_data = None
        if db and db.incidents:
            incident_data = db.incidents.find_one({
                "chat_id": group_chat_id,
                "user_id": target_user_id
            }, sort=[("timestamp", -1)]) # Get the latest incident for this user in this chat

        case_id_value = incident_data["case_id"] if incident_data else "N/A"
        # Re-derive case_detail_url using the stored case_channel_message_id
        case_channel_message_id = incident_data.get("case_channel_message_id") if incident_data else None
        
        if case_channel_message_id:
            channel_link_id = str(CASE_CHANNEL_ID).replace('-100', '')
            case_detail_url = f"https://t.me/c/{channel_link_id}/{case_channel_message_id}"
        else:
            case_detail_url = f"https://t.me/{CASE_CHANNEL_USERNAME}"


        user_obj = await context.bot.get_chat_member(group_chat_id, target_user_id)

        notification_message = (
            f"⛔ <b>Group Niyam Ulanghan</b>\n\n"
            f"{user_obj.user.mention_html()} (<code>{target_user_id}</code>) ne aise shabdon ka istemaal kiya hai jo group ke niyam ke khilaaf hain. Message ko hata diya gaya hai.\n\n"
            f"@{GROUP_ADMIN_USERNAME}, kripya sadasya ke vyavhaar ki samiksha karein.\n\n"
            f"<b>Case ID:</b> <code>{case_id_value}</code>"
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
    """Initializes and runs the Telegram bot."""
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

        # Message Handlers
        application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
        # This handles ALL text messages in groups/supergroups for profanity detection
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & (filters.ChatType.GROUP | filters.ChatType.SUPERGROUP), handle_all_messages))
        # This handles admin's broadcast message input in private chat
        # Modified to accept all message types for broadcast
        application.add_handler(MessageHandler(
            (filters.TEXT | filters.PHOTO | filters.VIDEO | filters.Document.ALL) & # Corrected filters.DOCUMENT to filters.Document.ALL
            filters.ChatType.PRIVATE & 
            filters.User(user_id=ADMIN_USER_IDS), 
            handle_all_messages
        ))


        # Callback Query Handler for inline buttons
        application.add_handler(CallbackQueryHandler(button_callback_handler))

        logger.info("Bot is starting polling...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")

# --- Entry Point ---
if __name__ == "__main__":
    init_mongodb() # Initialize MongoDB connection and profanity filter
    flask_thread = threading.Thread(target=run_flask_app)
    flask_thread.daemon = True # Allow main program to exit even if thread is running
    flask_thread.start()
    run_bot()

