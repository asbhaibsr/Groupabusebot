import os
import time
from datetime import datetime, timedelta
import threading
import asyncio
import logging
from pymongo import MongoClient
from telegram.error import BadRequest, TelegramError # Import specific Telegram errors

from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions, WebAppInfo
from telegram.ext import (
    CommandHandler, MessageHandler, filters, CallbackContext,
    CallbackQueryHandler, Application
)

# Custom module import
from profanity_filter import ProfanityFilter

# --- Configuration (Hardcoded as per request, but MONGO_DB_URI & TELEGRAM_BOT_TOKEN remain env vars for security) ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
LOG_CHANNEL_ID = -1002352329534 # Your specified Log Channel ID
CASE_CHANNEL_ID = -1002717243409 # Your specified Case Channel ID
CASE_CHANNEL_USERNAME = "AbusersDetector" # Your specified Case Channel Username for linking
MONGO_DB_URI = os.getenv("MONGO_DB_URI") # MongoDB URI still from environment for security
GROUP_ADMIN_USERNAME = os.getenv("GROUP_ADMIN_USERNAME", "admin") # Default to 'admin' if not set

# Admin User IDs (आपका दिया गया ID)
ADMIN_USER_IDS = [7315805581] 

# Bot start time record करे
bot_start_time = datetime.now()

# Global variable to store broadcast message
BROADCAST_MESSAGE = {} # key: user_id, value: telegram.Message object (or None for pending)

# Logging configuration
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Flask App Initialization ---
app = Flask(__name__)

# --- Telegram Bot Setup ---
application = None
mongo_client = None
db = None # MongoDB database instance

# Profanity Filter को initialize करें (इसे init_mongodb में सही तरीके से सेट किया जाएगा)
profanity_filter = None 

# --- MongoDB Initialization ---
def init_mongodb():
    global mongo_client, db, profanity_filter
    if MONGO_DB_URI is None: # Correct check for None
        logger.error("MONGO_DB_URI environment variable is not set. Cannot connect to MongoDB. Profanity filter will use default list.")
        profanity_filter = ProfanityFilter(mongo_uri=None) # Fallback to default list
        return

    try:
        mongo_client = MongoClient(MONGO_DB_URI)
        db = mongo_client.get_database("asfilter")
        
        # Ensure 'groups' collection has a unique index on chat_id
        if "groups" not in db.list_collection_names():
            db.create_collection("groups")
        db.groups.create_index("chat_id", unique=True)
        logger.info("MongoDB 'groups' collection unique index created/verified.")

        # Ensure 'users' collection has a unique index on user_id
        if "users" not in db.list_collection_names():
            db.create_collection("users")
        db.users.create_index("user_id", unique=True)
        logger.info("MongoDB 'users' collection unique index created/verified.")

        # Ensure 'incidents' collection for logging cases
        if "incidents" not in db.list_collection_names():
            db.create_collection("incidents")
        db.incidents.create_index("case_id", unique=True)
        logger.info("MongoDB 'incidents' collection unique index created/verified.")

        # Initialize profanity filter AFTER DB connection is established
        profanity_filter = ProfanityFilter(mongo_uri=MONGO_DB_URI)
        logger.info("MongoDB connection and collections initialized successfully. Profanity filter is ready.")
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB or initialize collections: {e}. Profanity filter will use default list.")
        # If MongoDB fails, profanity_filter will use default list
        profanity_filter = ProfanityFilter(mongo_uri=None) # Fallback to default list
        logger.warning("Falling back to default profanity list due to MongoDB connection error.")

# --- Helper Functions ---
def is_admin(user_id: int) -> bool:
    """Checks if a user is a global bot admin."""
    return user_id in ADMIN_USER_IDS

async def is_group_admin(chat_id: int, user_id: int, context: CallbackContext) -> bool:
    """Checks if a user is an admin in a given group chat."""
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in ['creator', 'administrator']
    except Exception as e:
        logger.error(f"Error checking admin status for user {user_id} in chat {chat_id}: {e}")
        return False

async def log_to_channel(text: str, parse_mode: str = None) -> None:
    """Logs messages to a designated Telegram channel."""
    if application is not None and LOG_CHANNEL_ID is not None:
        try:
            await application.bot.send_message(chat_id=LOG_CHANNEL_ID, text=text, parse_mode=parse_mode)
        except Exception as e:
            logger.error(f"Error logging to channel {LOG_CHANNEL_ID}: {e}")
    else:
        logger.warning("Application not initialized or LOG_CHANNEL_ID is not set, cannot log to channel.") 

# --- Bot Commands Handlers ---

async def start(update: Update, context: CallbackContext) -> None:
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

        # Store user info in DB if not already present, only for private chats
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
        
        # Log to channel when user starts bot in private
        log_message = (
            f"<b>✨ New User Started Bot:</b>\n"
            f"User: {user.mention_html()} (<code>{user.id}</code>)\n"
            f"Username: @{user.username if user.username else 'N/A'}\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}"
        )
        await log_to_channel(log_message, parse_mode='HTML')

    elif chat.type in ['group', 'supergroup']: # Handle /start in groups
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
        
        # Construct the "Add to Group" URL
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
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Aapke paas is command ko use karne ki permission nahi hai.")
        return
    if update.message.chat.type != 'private':
        await update.message.reply_text("Broadcast command sirf private chat mein hi shuru ki ja sakti hai.")
        return
    await update.message.reply_text("Kripya apna message bhejein jo sabhi groups par broadcast karna hai.")
    BROADCAST_MESSAGE[update.effective_user.id] = None # Mark as waiting for message
    logger.info(f"Admin {update.effective_user.id} initiated broadcast.")

async def confirm_broadcast(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if not is_admin(user_id) or BROADCAST_MESSAGE.get(user_id) is None:
        await query.edit_message_text("Invalid action or broadcast message not found.")
        return

    broadcast_msg = BROADCAST_MESSAGE.pop(user_id)
    if broadcast_msg:
        if db is None or db.groups is None:
            await query.edit_message_text("Broadcast ke liye MongoDB groups collection available nahi hai. Broadcast nahi kar sakte.")
            logger.error("MongoDB 'groups' collection not available for broadcast.")
            return

        target_groups = []
        try:
            if db.groups is not None: 
                for doc in db.groups.find({}, {"chat_id": 1}):
                    target_groups.append(doc['chat_id'])
            logger.info(f"Fetched {len(target_groups)} group IDs from DB for broadcast.")
        except Exception as e:
            await query.edit_message_text(f"Groups retrieve karte samay error hui: {e}")
            logger.error(f"Error fetching group IDs from DB for broadcast: {e}")
            return

        if not target_groups:
            await query.edit_message_text("Broadcast ke liye koi target group/channel IDs database mein nahi mile. Kripya ensure karein bot groups mein added hai aur DB mein entries hain.")
            logger.warning(f"Admin {user_id} tried to broadcast but no target chat IDs found in DB.")
            return

        success_count = 0
        fail_count = 0
        
        for chat_id in target_groups:
            try:
                await context.bot.copy_message(
                    chat_id=chat_id,
                    from_chat_id=broadcast_msg.chat.id,
                    message_id=broadcast_msg.message_id
                )
                success_count += 1
                await asyncio.sleep(0.1)
            except Exception as e:
                fail_count += 1
                logger.error(f"Failed to broadcast to {chat_id}: {e}")

        await query.edit_message_text(f"Broadcast complete! Successfully sent to {success_count} groups/channels. Failed: {fail_count}.")
        logger.info(f"Broadcast initiated by {user_id} completed. Success: {success_count}, Failed: {fail_count}.")
    else:
        await query.edit_message_text("Broadcast message not found.")


async def add_abuse_word(update: Update, context: CallbackContext) -> None:
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
    new_members = update.message.new_chat_members
    chat = update.message.chat
    bot_info = await context.bot.get_me() 

    for member in new_members:
        if member.id == bot_info.id:
            # Bot group mein add hua hai
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

            # Store group info in DB
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

            # Bot admin status check and potential initial setup messages
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


async def handle_all_messages(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    chat = update.message.chat
    message_text = update.message.text

    # Handle broadcast message input from admin
    if is_admin(user.id) and user.id in BROADCAST_MESSAGE and BROADCAST_MESSAGE[user.id] is None:
        if update.message.text:
            BROADCAST_MESSAGE[user.id] = update.message
            await update.message.reply_text(
                "Message received. Kya aap ise broadcast karna chahenge?",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Yes, Broadcast!", callback_data="confirm_broadcast")]])
            )
        else:
            await update.message.reply_text("Kripya ek text message bhejein broadcast karne ke liye.")
        return # Stop further processing for broadcast input

    # Process messages for profanity only in groups/supergroups
    if chat.type in ['group', 'supergroup'] and message_text and not update.message.via_bot:
        if profanity_filter is not None and profanity_filter.contains_profanity(message_text):
            try:
                original_message_content = message_text
                await context.bot.delete_message(chat_id=chat.id, message_id=update.message.message_id)
                logger.info(f"Deleted abusive message from {user.username or user.full_name} ({user.id}) in {chat.title} ({chat.id}).")
            except Exception as e:
                logger.error(f"Error deleting message in {chat.title} ({chat.id}): {e}. Make sure the bot has 'Delete Messages' admin permission.")
                original_message_content = message_text # Still use original text if deletion failed
                
            case_id_value = str(int(datetime.now().timestamp() * 1000))

            if db is not None and db.incidents is not None:
                try:
                    db.incidents.insert_one({
                        "case_id": case_id_value,
                        "user_id": user.id,
                        "user_name": user.full_name,
                        "user_username": user.username,
                        "chat_id": chat.id,
                        "chat_title": chat.title,
                        "original_message_id": update.message.message_id,
                        "abusive_content": original_message_content,
                        "timestamp": datetime.now(),
                        "status": "pending_review"
                    })
                    logger.info(f"Incident {case_id_value} logged in DB.")
                except Exception as e:
                    logger.error(f"Error logging incident {case_id_value} to DB: {e}")

            forwarded_message = None
            case_detail_url = f"https://t.me/{CASE_CHANNEL_USERNAME}" # Fallback if direct link fails

            try:
                # 1. Forward the original message to the case channel using its numeric ID
                forwarded_message = await context.bot.forward_message(
                    chat_id=CASE_CHANNEL_ID,
                    from_chat_id=chat.id,
                    message_id=update.message.message_id
                )
                
                # 2. Construct the direct link to the forwarded message in the case channel
                # This format works for both public and private channels by removing '-100' prefix
                # from the chat ID and combining it with the message ID.
                channel_link_id = str(CASE_CHANNEL_ID).replace('-100', '')
                case_detail_url = f"https://t.me/c/{channel_link_id}/{forwarded_message.message_id}"
                
                logger.info(f"Original abusive message forwarded to case channel. Generated URL: {case_detail_url}")
            except TelegramError as e:
                logger.error(f"Error forwarding message to case channel: {e}. Ensure bot is admin in case channel and has 'Post Messages' permission.")
                # If forwarding fails, the fallback URL remains the channel's general link.
            
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
                    InlineKeyboardButton("📄 View Case Details", url=case_detail_url) # Use the generated direct link
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            try:
                sent_notification = await context.bot.send_message(
                    chat_id=chat.id,
                    text=notification_message,
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
                await context.bot.send_message(
                    chat_id=chat.id,
                    text="<b>Check Case</b> ⬆️",
                    reply_to_message_id=sent_notification.message_id,
                    parse_mode='HTML'
                )
                logger.info(f"Abusive message detected and handled for user {user.id} in chat {chat.id}. Case ID: {case_id_value}. Notification sent.")
            except Exception as e:
                logger.error(f"Error sending profanity notification in chat {chat.id}: {e}. Make sure bot has 'Post Messages' permission.")
        elif profanity_filter is None:
            logger.warning("Profanity filter not initialized. Skipping profanity check in group.")

async def button_callback_handler(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data

    # Centralized Permission check for admin actions (mute, ban, kick, warn, admin_actions_menu)
    if data.startswith(("admin_actions_menu_", "mute_", "ban_", "kick_", "warn_user_")):
        if query.message.chat.type in ['group', 'supergroup']:
            user_is_group_admin = await is_group_admin(query.message.chat_id, query.from_user.id, context)
        else:
            user_is_group_admin = False

        if not user_is_group_admin and not is_admin(query.from_user.id):
            await query.edit_message_text("Aapke paas is action ko perform karne ki permission nahi hai.")
            return

    if data == "help_menu":
        help_text = (
            f"<b>Bot Help:</b>\n\n"
            f"• Gaaliyon wale messages delete kiye jayenge.\n"
            f"• Admins user par action le sakte hain (mute, ban, kick, warn).\n"
            f"• /start - Bot ka welcome message.\n"
            f"• /stats - Bot ka status (Admins only).\n"
            f"• /broadcast - Sabhi groups par message bhejen (Admins only).\n"
            f"• /addabuse - MongoDB mein naya gaali shabd jodein (Admins only).\n\n"
            f"Agar aapko aur madad chahiye, toh @{GROUP_ADMIN_USERNAME} se contact karein."
        )
        keyboard = [[InlineKeyboardButton("⬅️ Back to Main", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(help_text, reply_markup=reply_markup, parse_mode='HTML')
    elif data == "other_bots":
        other_bots_text = (
            f"<b>🤖 Hamare Dusre Bots:</b>\n\n"
            f"• <a href='https://t.me/asfilter_bot'>@asfilter_bot</a>: Ek movie search bot hai jo aapko movies dhundhne mein madad karega.\n"
            f"• <a href='https://t.me/askiangelbot'>@askiangelbot</a>: Ye ek baat karne wala bot hai, aap group par isse baat kar sakte hain."
        )
        keyboard = [[InlineKeyboardButton("⬅️ Back to Main", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(other_bots_text, reply_markup=reply_markup, parse_mode='HTML')
    elif data == "donate_info":
        donate_text = (
            f"💖 <b>Dosto, agar aapko hamara bot aapke group ke liye accha lagta hai, "
            f"toh aap yahan thode se paise donate kar sakte hain jisse ye bot aage ke liye bana rahe.</b>\n\n"
            f"<b>UPI ID:</b> <code>arsadsaifi8272@ibl</code>\n\n"
            f"Aapki madad ke liye dhanyawaad!"
        )
        keyboard = [[InlineKeyboardButton("⬅️ Back to Main", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(donate_text, reply_markup=reply_markup, parse_mode='HTML')
    elif data == "main_menu":
        user = query.from_user
        bot_info = await context.bot.get_me() 
        bot_name = bot_info.first_name
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
        await query.edit_message_text(welcome_message, reply_markup=reply_markup, parse_mode='HTML')
    elif data.startswith("admin_actions_menu_"):
        parts = data.split('_')
        user_id_to_act = int(parts[3])
        chat_id_for_action = int(parts[4])
        
        try:
            target_user = await context.bot.get_chat_member(chat_id=chat_id_for_action, user_id=user_id_to_act)
            target_username = target_user.user.full_name
        except Exception:
            target_username = f"User {user_id_to_act}"

        action_keyboard = [
            [
                InlineKeyboardButton(f"🔇 Mute {target_username}", callback_data=f"mute_time_{user_id_to_act}_{chat_id_for_action}"),
                InlineKeyboardButton(f"🚫 Ban {target_username}", callback_data=f"ban_{user_id_to_act}_{chat_id_for_action}")
            ],
            [
                InlineKeyboardButton(f"Kick {target_username}", callback_data=f"kick_{user_id_to_act}_{chat_id_for_action}"),
                InlineKeyboardButton(f"❗ Warn {target_username}", callback_data=f"warn_user_{user_id_to_act}_{chat_id_for_action}")
            ]
        ]
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(action_keyboard))
    elif data.startswith("mute_time_"):
        parts = data.split('_')
        user_id = int(parts[2])
        chat_id = int(parts[3])

        try:
            target_user = await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
            target_username = target_user.user.full_name
        except Exception:
            target_username = f"User {user_id}"

        mute_time_keyboard = [
            [
                InlineKeyboardButton("1 Day", callback_data=f"mute_{user_id}_{chat_id}_{86400}"),
                InlineKeyboardButton("1 Month", callback_data=f"mute_{user_id}_{chat_id}_{2592000}")
            ],
            [
                InlineKeyboardButton("3 Months", callback_data=f"mute_{user_id}_{chat_id}_{7776000}"),
                InlineKeyboardButton("6 Months", callback_data=f"mute_{user_id}_{chat_id}_{15552000}")
            ],
            [
                InlineKeyboardButton("Permanent", callback_data=f"mute_{user_id}_{chat_id}_0")
            ]
        ]
        await query.edit_message_text(
            text=f"Kitne samay ke liye mute karna hai {target_username} ko?",
            reply_markup=InlineKeyboardMarkup(mute_time_keyboard)
        )
    elif data.startswith("mute_") and len(data.split('_')) == 4:
        parts = data.split('_')
        user_id = int(parts[1])
        chat_id = int(parts[2])
        duration_seconds = int(parts[3])
        try:
            permissions = ChatPermissions(can_send_messages=False)
            until_date = datetime.now() + timedelta(seconds=duration_seconds) if duration_seconds > 0 else None
            await context.bot.restrict_chat_member(
                chat_id=chat_id, 
                user_id=user_id, 
                permissions=permissions, 
                until_date=until_date
            )
            try:
                target_user = await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
                user_display_name = target_user.user.full_name
            except Exception:
                user_display_name = f"User {user_id}"

            if duration_seconds == 0:
                action_text = f"User <b>{user_display_name}</b> ko <b>permanently mute</b> kiya gaya hai."
            elif duration_seconds == 86400:
                action_text = f"User <b>{user_display_name}</b> ko <b>1 din</b> ke liye mute kiya gaya hai."
            elif duration_seconds == 2592000:
                action_text = f"User <b>{user_display_name}</b> ko <b>1 mahine</b> ke liye mute kiya gaya hai."
            elif duration_seconds == 7776000:
                action_text = f"User <b>{user_display_name}</b> ko <b>3 mahine</b> ke liye mute kiya gaya hai."
            elif duration_seconds == 15552000:
                action_text = f"User <b>{user_display_name}</b> ko <b>6 mahine</b> ke liye mute kiya gaya hai."
            else:
                action_text = f"User <b>{user_display_name}</b> ko <b>{duration_seconds} seconds</b> ke liye mute kiya gaya hai."

            await query.edit_message_text(action_text, parse_mode='HTML')
            logger.info(f"User {user_id} muted in chat {chat_id} by admin {query.from_user.id}.")
        except Exception as e:
            await query.edit_message_text(f"Mute karte samay error hui: {e}")
            logger.error(f"Error muting user {user_id} in chat {chat_id}: {e}")

    elif data.startswith("ban_"):
        parts = data.split('_')
        user_id = int(parts[1])
        chat_id = int(parts[2])
        try:
            try:
                target_user = await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
                user_display_name = target_user.user.full_name
            except Exception:
                user_display_name = f"User {user_id}"

            await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
            await query.edit_message_text(f"User <b>{user_display_name}</b> ko group se <b>ban</b> kiya gaya hai.", parse_mode='HTML')
            logger.info(f"User {user_id} banned from chat {chat_id} by admin {query.from_user.id}.")
        except Exception as e:
            await query.edit_message_text(f"Ban karte samay error hui: {e}")
            logger.error(f"Error banning user {user_id} in chat {chat_id}: {e}")

    elif data.startswith("kick_"):
        parts = data.split('_')
        user_id = int(parts[1])
        chat_id = int(parts[2])
        try:
            try:
                target_user = await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
                user_display_name = target_user.user.full_name
            except Exception:
                user_display_name = f"User {user_id}"

            await context.bot.kick_chat_member(chat_id=chat_id, user_id=user_id)
            await context.bot.unban_chat_member(chat_id=chat_id, user_id=user_id) # Unban immediately so they can rejoin if invited
            await query.edit_message_text(f"User <b>{user_display_name}</b> ko group se <b>kick</b> kiya gaya hai.", parse_mode='HTML')
            logger.info(f"User {user_id} kicked from chat {chat_id} by admin {query.from_user.id}.")
        except Exception as e:
            await query.edit_message_text(f"Kick karte samay error hui: {e}")
            logger.error(f"Error kicking user {user_id} in chat {chat_id}: {e}")

    elif data.startswith("warn_user_"):
        parts = data.split('_')
        user_id = int(parts[2])
        chat_id = int(parts[3])
        try:
            user_info = await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
            warning_text_by_admin = (
                f"⚠️ <b>{user_info.user.first_name}</b>, aapne galat shabdon ka prayog kiya hai!\n\n"
                f"<b>🚨 Aisa dobara na karein, warna kadi kaarwayi ki ja sakti hai. 🚨</b>\n\n"
                f"Group ke niyam todne par aapko ban, mute, ya kick kiya ja sakta hai."
            )
            await context.bot.send_message(chat_id=chat_id, text=warning_text_by_admin, parse_mode='HTML')
            
            try:
                target_user = await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
                user_display_name = target_user.user.full_name
            except Exception:
                user_display_name = f"User {user_id}"

            await query.edit_message_text(f"User <b>{user_display_name}</b> ko ek warning message bheja gaya hai.", parse_mode='HTML')
            logger.info(f"User {user_id} warned in chat {chat_id} by admin {query.from_user.id}.")
        except Exception as e:
            await query.edit_message_text(f"Warning message bhejte samay error hui: {e}")
            logger.error(f"Error warning user {user_id} in chat {chat_id}: {e}")

# --- Flask Health Check Endpoint ---
@app.route('/')
def health_check():
    """Koyeb health checks ke liye simple endpoint."""
    return "Bot is healthy!", 200

# --- Function to run Flask in a separate thread ---
def run_flask_app():
    """Flask application ko ek alag thread mein chalata hai."""
    PORT = int(os.environ.get("PORT", 8080)) # Koyeb uses PORT env variable
    logger.info(f"Flask application starting on port {PORT} in a separate thread for health checks...")
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)

def run_bot():
    """Telegram bot को चलाने के लिए मुख्य फंक्शन"""
    global application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Handlers जोड़ें
    dispatcher = application
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("stats", stats))
    dispatcher.add_handler(CommandHandler("broadcast", broadcast_command))
    dispatcher.add_handler(CommandHandler("addabuse", add_abuse_word)) 
    
    # Message handler for all text messages (including broadcast input)
    dispatcher.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_all_messages))
    
    # Handler for new chat members (bot joining groups and new users joining)
    dispatcher.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    
    # Callback handlers for inline keyboard buttons
    dispatcher.add_handler(CallbackQueryHandler(button_callback_handler))

    logger.info("Starting Telegram Bot in long polling mode...")
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    init_mongodb() # Initialize MongoDB before starting bot and flask

    # Flask को अलग थ्रेड में चलाएं
    flask_thread = threading.Thread(target=run_flask_app)
    flask_thread.daemon = True # Daemon threads automatically exit when the main program exits
    flask_thread.start()

    # Telegram बॉट को मुख्य थ्रेड में चलाएं
    run_bot()
