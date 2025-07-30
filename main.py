# main.py

import os
import time
from datetime import datetime, timedelta
import threading
import asyncio
import logging

from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import (
    CommandHandler, MessageHandler, filters, CallbackContext,
    CallbackQueryHandler, Application
)

# Custom module import
from profanity_filter import ProfanityFilter

# --- Configuration ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CASE_CHANNEL_ID = os.getenv("CASE_CHANNEL_ID")
LOG_CHANNEL_ID = os.getenv("LOG_CHANNEL_ID")
MONGO_DB_URI = os.getenv("MONGO_DB_URI")
GROUP_ADMIN_USERNAME = os.getenv("GROUP_ADMIN_USERNAME", "admin")
PORT = int(os.getenv("PORT", 8000))

# Admin User IDs (Jinhe broadcast/stats commands ka access hoga)
ADMIN_USER_IDS = [int(admin_id) for admin_id in os.getenv("ADMIN_USER_IDS", "").split(',') if admin_id]

# Bot start time record karein
bot_start_time = datetime.now()

# Global variable to store broadcast message
BROADCAST_MESSAGE = {}

# Logging configuration
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Flask App Initialization ---
app = Flask(__name__)

# --- Telegram Bot Setup ---
# Application को globally initialize करें
application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

# Profanity Filter को initialize करें
profanity_filter = ProfanityFilter(mongo_uri=MONGO_DB_URI)

# --- Helper Functions (Same as before) ---
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_USER_IDS

async def log_to_channel(text: str, parse_mode: str = None) -> None:
    if LOG_CHANNEL_ID:
        try:
            await application.bot.send_message(chat_id=LOG_CHANNEL_ID, text=text, parse_mode=parse_mode)
        except Exception as e:
            logger.error(f"Error logging to channel: {e}")

# --- Bot Commands Handlers (Same as before) ---
async def start(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
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

    await update.message.reply_text(
        text=welcome_message,
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
    logger.info(f"User {user.first_name} ({user.id}) started the bot.")
    
async def stats(update: Update, context: CallbackContext) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Aapke paas is command ko use karne ki permission nahi hai.")
        return

    stats_message = (
        f"📊 <b>Bot Status:</b>\n\n"
        f"• Total Users (Approx): 1000+ (dummy)\n"
        f"• Total Groups (Approx): 100+ (dummy)\n"
        f"• Total Incidents Logged (Approx): 500+ (dummy)\n"
        f"• Uptime: {str(datetime.now() - bot_start_time).split('.')[0]} \n"
        f"• Last Check: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}"
    )
    await update.message.reply_text(stats_message, parse_mode='HTML')
    logger.info(f"Admin {update.effective_user.id} requested stats.")

async def broadcast_command(update: Update, context: CallbackContext) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Aapke paas is command ko use karne ki permission nahi hai.")
        return
    
    await update.message.reply_text("Kripya apna message bhejein jo sabhi groups par broadcast karna hai.")
    BROADCAST_MESSAGE[update.effective_user.id] = None
    logger.info(f"Admin {update.effective_user.id} initiated broadcast.")

async def handle_broadcast_message(update: Update, context: CallbackContext) -> None:
    user_id = update.effective_user.id
    if is_admin(user_id) and user_id in BROADCAST_MESSAGE and BROADCAST_MESSAGE[user_id] is None:
        BROADCAST_MESSAGE[user_id] = update.message
        await update.message.reply_text("Message received. Kya aap ise broadcast karna chahenge?",
                                  reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Yes, Broadcast!", callback_data="confirm_broadcast")]]))
    else:
        await handle_message(update, context)

async def confirm_broadcast(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if not is_admin(user_id) or not BROADCAST_MESSAGE.get(user_id):
        await query.edit_message_text("Invalid action or session expired.")
        return
        
    broadcast_msg = BROADCAST_MESSAGE.pop(user_id)
    
    if broadcast_msg:
        dummy_group_ids = [
            -1001234567890, # Example: Replace with a real group ID where your bot is present
            # -1009876543210 # Add more if needed
        ]
        
        success_count = 0
        fail_count = 0
        for chat_id in dummy_group_ids:
            try:
                await context.bot.copy_message(
                    chat_id=chat_id,
                    from_chat_id=broadcast_msg.chat_id,
                    message_id=broadcast_msg.message_id
                )
                success_count += 1
                time.sleep(0.1)
            except Exception as e:
                fail_count += 1
                logger.error(f"Failed to broadcast to {chat_id}: {e}")
        
        await query.edit_message_text(f"Broadcast complete! Successfully sent to {success_count} groups. Failed: {fail_count}.")
        logger.info(f"Broadcast initiated by {user_id} completed. Success: {success_count}, Failed: {fail_count}.")
    else:
        await query.edit_message_text("Broadcast message not found.")

async def welcome_new_member(update: Update, context: CallbackContext) -> None:
    new_members = update.message.new_chat_members
    chat = update.message.chat

    for member in new_members:
        if member.id == context.bot.get_me().id:
            log_message = (
                f"<b>🤖 Bot Joined Group:</b>\n"
                f"Group Name: <code>{chat.title}</code>\n"
                f"Group ID: <code>{chat.id}</code>\n"
                f"Members: {await chat.get_member_count()}"
            )
            await log_to_channel(log_message, parse_mode='HTML')
            logger.info(f"Bot joined group: {chat.title} ({chat.id})")
        else:
            log_message = (
                f"<b>➕ Naya User Joined:</b>\n"
                f"User: {member.mention_html()} (<code>{member.id}</code>)\n"
                f"Group: <code>{chat.title}</code> (<code>{chat.id}</code>)"
            )
            await log_to_channel(log_message, parse_mode='HTML')
            logger.info(f"User {member.full_name} ({member.id}) joined group {chat.title} ({chat.id}).")

async def handle_message(update: Update, context: CallbackContext) -> None:
    message_text = update.message.text
    user = update.message.from_user
    chat = update.message.chat
    
    if is_admin(user.id) and user.id in BROADCAST_MESSAGE and BROADCAST_MESSAGE[user.id] is None:
        await handle_broadcast_message(update, context)
        return

    if message_text and profanity_filter.contains_profanity(message_text):
        try:
            await context.bot.delete_message(chat_id=chat.id, message_id=update.message.message_id)
            logger.info(f"Deleted abusive message from {user.username or user.full_name} in {chat.title or chat.type}.")
        except Exception as e:
            logger.error(f"Error deleting message: {e}. Make sure the bot has 'Delete Messages' admin permission.")

        abuse_no = str(abs(hash(f"{user.id}-{chat.id}-{update.message.message_id}")))[:6]

        notification_message = (
            f"⛔ <b>Group Niyam Ulanghan</b>\n\n"
            f"{user.mention_html()} (<code>{user.id}</code>) ne aise shabdon ka istemaal kiya hai jo group ke niyam ke khilaaf hain. Message ko hata diya gaya hai.\n\n"
            f"@{GROUP_ADMIN_USERNAME}, kripya sadasya ke vyavhaar ki samiksha karein.\n\n"
            f"Case ID: <code>{abuse_no}</code>"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("👤 User Profile", url=f"tg://user?id={user.id}"),
                InlineKeyboardButton("🔧 Admin Actions", callback_data=f"admin_actions_menu_{user.id}_{chat.id}")
            ],
            [
                InlineKeyboardButton("📄 View Abuse Details", callback_data=f"view_case_{user.id}_{chat.id}_{update.message.message_id}_{abuse_no}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

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
        logger.info(f"Abusive message detected and handled for user {user.id} in chat {chat.id}. Case ID: {abuse_no}")

async def view_case_details_forward(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data
    
    if not data.startswith("view_case_"):
        await query.edit_message_text("Invalid case view request.")
        return

    if query.message.chat_id < 0:
        try:
            member = await context.bot.get_chat_member(chat_id=query.message.chat_id, user_id=query.from_user.id)
            if not (member.status == 'administrator' or member.status == 'creator'):
                await query.edit_message_text("Aapke paas is action ko perform karne ki permission nahi hai.")
                return
        except Exception:
            await query.edit_message_text("Aapke paas is action ko perform karne ki permission nahi hai. Bot ko 'Get Group Info' permission ki zaroorat ho sakti hai.")
            return
    elif query.message.chat_id > 0 and not is_admin(query.from_user.id):
        await query.edit_message_text("Aapke paas is action ko perform karne ki permission nahi hai.")
        return

    parts = data.split('_')
    user_id_for_case = int(parts[2])
    group_id_for_case = int(parts[3])
    original_message_id = int(parts[4])
    abuse_no_from_callback = parts[5]

    original_abusive_content = "Original message content not available (deleted or not logged)."
    
    case_number = "CASE-" + abuse_no_from_callback
    
    try:
        group_chat = await context.bot.get_chat(chat_id=group_id_for_case)
        user_info = await context.bot.get_chat_member(chat_id=group_id_for_case, user_id=user_id_for_case)
        
        case_details_message = (
            f"<b>🚨 Naya Incident Case 🚨</b>\n\n"
            f"<b>Case Number:</b> <code>{case_number}</code>\n"
            f"<b>User:</b> {user_info.user.mention_html()} (<code>{user_info.user.id}</code>)\n"
            f"<b>Group:</b> {group_chat.title} (<code>{group_chat.id}</code>)\n"
            f"<b>Samay:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}\n\n"
            f"<b>Mool Message:</b>\n"
            f"<code>{original_abusive_content}</code>"
        )
        
        sent_case_message = await application.bot.send_message(
            chat_id=CASE_CHANNEL_ID,
            text=case_details_message,
            parse_mode='HTML'
        )
        
        case_channel_link = f"https://t.me/c/{str(CASE_CHANNEL_ID).replace('-100', '')}/{sent_case_message.message_id}"
        
        await query.edit_message_text(
            text=f"✅ Abuse Details successfully forwarded to the case channel.\n\n"
                 f"Case Link: <a href='{case_channel_link}'>View Details</a>",
            parse_mode='HTML',
            disable_web_page_preview=True
        )
        logger.info(f"Case {case_number} forwarded for user {user_id_for_case} in group {group_id_for_case}.")
    except Exception as e:
        await query.edit_message_text(f"Abuse Details forward karte samay error hui: {e}")
        logger.error(f"Error forwarding case: {e}")

async def button_callback_handler(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data
    
    if data.startswith(("admin_actions_menu_", "mute_", "ban_", "kick_", "warn_user_", "view_case_")):
        if query.message.chat_id < 0:
            try:
                member = await context.bot.get_chat_member(chat_id=query.message.chat_id, user_id=query.from_user.id)
                if not (member.status == 'administrator' or member.status == 'creator'):
                    await query.edit_message_text("Aapke paas is action ko perform karne ki permission nahi hai.")
                    return
            except Exception:
                await query.edit_message_text("Aapke paas is action ko perform karne ki permission nahi hai. Bot ko 'Get Group Info' permission ki zaroorat ho sakti hai.")
                return
        elif query.message.chat_id > 0 and not is_admin(query.from_user.id):
            await query.edit_message_text("Aapke paas is action ko perform karne ki permission nahi hai.")
            return

    if data == "help_menu":
        help_text = (
            f"<b>Bot Help:</b>\n\n"
            f"• Gaaliyon wale messages delete kiye jayenge.\n"
            f"• Admins user par action le sakte hain (mute, ban, kick, warn).\n"
            f"• /start - Bot ka welcome message.\n"
            f"• /stats - Bot ka status (Admins only).\n"
            f"• /broadcast - Sabhi groups par message bhejen (Admins only).\n\n"
            f"Agar aapko aur madad chahiye, toh @asbhaibsr se contact karein."
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

        action_keyboard = [
            [
                InlineKeyboardButton("🔇 Mute User", callback_data=f"mute_time_{user_id_to_act}_{chat_id_for_action}"),
                InlineKeyboardButton("🚫 Ban User", callback_data=f"ban_{user_id_to_act}_{chat_id_for_action}")
            ],
            [
                InlineKeyboardButton("Kick User", callback_data=f"kick_{user_id_to_act}_{chat_id_for_action}"),
                InlineKeyboardButton("❗ Warn User", callback_data=f"warn_user_{user_id_to_act}_{chat_id_for_action}")
            ]
        ]
        await query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(action_keyboard))

    elif data.startswith("mute_time_"):
        parts = data.split('_')
        user_id = int(parts[2])
        chat_id = int(parts[3])

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
            text=f"Kitne samay ke liye mute karna hai {user_id} ko?",
            reply_markup=InlineKeyboardMarkup(mute_time_keyboard)
        )

    elif data.startswith("mute_") and len(data.split('_')) == 4:
        parts = data.split('_')
        user_id = int(parts[1])
        chat_id = int(parts[2])
        duration_seconds = int(parts[3])
        
        try:
            permissions = ChatPermissions(can_send_messages=False)
            until_date = datetime.now() + timedelta(seconds=duration_seconds) if duration_seconds > 0 else 0
            
            await context.bot.restrict_chat_member(
                chat_id=chat_id, 
                user_id=user_id, 
                permissions=permissions, 
                until_date=until_date
            )
            
            if duration_seconds == 0:
                action_text = f"User <b>{user_id}</b> ko <b>permanently mute</b> kiya gaya hai."
            elif duration_seconds == 86400:
                action_text = f"User <b>{user_id}</b> ko <b>1 din</b> ke liye mute kiya gaya hai."
            elif duration_seconds == 2592000:
                action_text = f"User <b>{user_id}</b> ko <b>1 mahine</b> ke liye mute kiya gaya hai."
            elif duration_seconds == 7776000:
                action_text = f"User <b>{user_id}</b> ko <b>3 mahine</b> ke liye mute kiya gaya hai."
            elif duration_seconds == 15552000:
                action_text = f"User <b>{user_id}</b> ko <b>6 mahine</b> ke liye mute kiya gaya hai."
            else:
                action_text = f"User <b>{user_id}</b> ko <b>{duration_seconds} seconds</b> ke liye mute kiya gaya hai."

            await query.edit_message_text(action_text, parse_mode='HTML')
            logger.info(f"User {user_id} muted in chat {chat_id} for {duration_seconds} seconds by admin {query.from_user.id}.")
        except Exception as e:
            await query.edit_message_text(f"Mute karte samay error hui: {e}")
            logger.error(f"Error muting user {user_id} in chat {chat_id}: {e}")

    elif data.startswith("ban_"):
        parts = data.split('_')
        user_id = int(parts[1])
        chat_id = int(parts[2])
        try:
            await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
            await query.edit_message_text(f"User <b>{user_id}</b> ko group se <b>ban</b> kiya gaya hai.", parse_mode='HTML')
            logger.info(f"User {user_id} banned from chat {chat_id} by admin {query.from_user.id}.")
        except Exception as e:
            await query.edit_message_text(f"Ban karte samay error hui: {e}")
            logger.error(f"Error banning user {user_id} in chat {chat_id}: {e}")

    elif data.startswith("kick_"):
        parts = data.split('_')
        user_id = int(parts[1])
        chat_id = int(parts[2])
        try:
            await context.bot.kick_chat_member(chat_id=chat_id, user_id=user_id)
            await query.edit_message_text(f"User <b>{user_id}</b> ko group se <b>kick</b> kiya gaya hai.", parse_mode='HTML')
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
            await query.edit_message_text(f"User <b>{user_id}</b> ko ek aur warning message bheja gaya hai.", parse_mode='HTML')
            logger.info(f"User {user_id} warned in chat {chat_id} by admin {query.from_user.id}.")
        except Exception as e:
            await query.edit_message_text(f"Warning message bhejte samay error hui: {e}")
            logger.error(f"Error warning user {user_id} in chat {chat_id}: {e}")

# --- Flask Health Check & Dummy Webhook Endpoint (For Koyeb) ---
@app.route('/')
def health_check():
    """Koyeb health checks ke liye simple endpoint."""
    return "Bot is healthy!", 200

# Keep a dummy /telegram endpoint to avoid 404s if Telegram tries to send updates
# but it won't be actively used by the bot in long polling mode.
@app.route('/telegram', methods=['POST'])
def dummy_telegram_webhook():
    """Dummy endpoint to catch any stray webhook requests."""
    logger.info("Received a POST request on /telegram, but bot is in long polling mode.")
    return 'ok', 200

# --- Telegram Bot Polling Function ---
def run_telegram_bot_polling():
    """Telegram बॉट को पोलिंग मोड में चलाता है."""
    # Ensure a new event loop is created and set for this thread
    new_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(new_loop)

    async def _start_polling():
        try:
            # Telegram API से किसी भी पुराने वेबहुक को हटा दें
            current_webhook = await application.bot.get_webhook_info()
            if current_webhook.url:
                logger.info(f"Existing webhook found: {current_webhook.url}. Clearing it...")
                await application.bot.set_webhook(url="")
                logger.info("Cleared any existing webhooks.")
            else:
                logger.info("No active webhook found to clear.")

            logger.info("Telegram Bot starting in long polling mode...")
            # IMPORTANT: disable_signals=True will prevent set_wakeup_fd error in sub-threads
            await application.run_polling(drop_pending_updates=True, stop_signals=()) # Set stop_signals to an empty tuple
            logger.info("Telegram Bot polling stopped.")
        except Exception as e:
            logger.error(f"Error in Telegram Bot polling thread: {e}", exc_info=True)

    # run_until_complete is the correct way to run an async function in a sync context
    new_loop.run_until_complete(_start_polling())
    new_loop.close()


# --- Main Execution ---
if __name__ == "__main__":
    # Dispatcher को कॉन्फ़िगर करें
    dispatcher = application

    # Command Handlers
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("stats", stats))
    dispatcher.add_handler(CommandHandler("broadcast", broadcast_command))

    # Message Handlers
    dispatcher.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    dispatcher.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Callback Query Handlers (buttons ke liye)
    dispatcher.add_handler(CallbackQueryHandler(button_callback_handler))
    dispatcher.add_handler(CallbackQueryHandler(view_case_details_forward, pattern=r'^view_case_'))

    # Telegram बॉट को एक अलग थ्रेड में शुरू करें
    telegram_thread = threading.Thread(target=run_telegram_bot_polling)
    telegram_thread.daemon = True # डेमन थ्रेड ताकि मुख्य प्रोग्राम बंद होने पर यह भी बंद हो जाए
    telegram_thread.start()
    
    logger.info(f"Flask application starting on port {PORT}...")
    
    # Flask Development Server को लोकल टेस्टिंग के लिए चलाएं।
    # Koyeb पर, Gunicorn इसे होस्ट करेगा, इसलिए यह लाइन Koyeb पर सीधे नहीं चलेगी।
    # Koyeb के लिए, हम Procfile में Gunicorn कमांड का उपयोग करेंगे जो 'app' ऑब्जेक्ट को ढूंढेगा।
    # लेकिन Flask को स्टार्ट करने के लिए एक एंट्री पॉइंट चाहिए।
    # हम यहां सीधे Flask के development server को चला रहे हैं, जो Koyeb पर Gunicorn से override हो जाएगा।
    try:
        app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)
    except Exception as e:
        logger.critical(f"Flask server failed to start: {e}", exc_info=True)

