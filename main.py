# main.py

import os
import threading
import time
from datetime import datetime, timedelta

from flask import Flask, request, jsonify
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import (
    CommandHandler, MessageHandler, filters, CallbackContext,
    CallbackQueryHandler, Application # Updater हटा दिया
)

# Custom module import
from profanity_filter import ProfanityFilter

# --- Configuration ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CASE_CHANNEL_ID = os.getenv("CASE_CHANNEL_ID") # Case logging ke liye
LOG_CHANNEL_ID = os.getenv("LOG_CHANNEL_ID")   # Naye user/group join ke logs ke liye
MONGO_DB_URI = os.getenv("MONGO_DB_URI") # MongoDB connection string
GROUP_ADMIN_USERNAME = os.getenv("GROUP_ADMIN_USERNAME", "admin") # Default @admin, change if needed for specific group admin tag
PORT = int(os.getenv("PORT", 5000)) # Koyeb environment variable se PORT lete hain
WEBHOOK_URL = os.getenv("WEBHOOK_URL") # Koyeb URL environment variable

# Admin User IDs (Jinhe broadcast/stats commands ka access hoga)
ADMIN_USER_IDS = [int(admin_id) for admin_id in os.getenv("ADMIN_USER_IDS", "").split(',') if admin_id]

# Flask App Initialization
app = Flask(__name__)

# Telegram Bot Setup
# Application को ग्लोबली इनिशियलाइज़ करें
application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
telegram_bot = application.bot # application से बॉट ऑब्जेक्ट प्राप्त करें

# Profanity Filter ko initialize karein
profanity_filter = ProfanityFilter(mongo_uri=MONGO_DB_URI)

# MongoDB setup (basic placeholder - uncomment and configure properly)
# from pymongo import MongoClient
# client = MongoClient(MongoClient, connect=False)(MONGO_DB_URI) # connect=False to avoid blocking
# db = client.your_database_name # Apne database ka naam yahan dein
# users_collection = db.users # Users ki details (broadcast ke liye)
# incidents_collection = db.incidents # Gaali incidents ke liye
# groups_collection = db.groups # Groups ki details (jismein bot added hai)

# Global variable to store broadcast message (temporary, for simple broadcast)
BROADCAST_MESSAGE = {} # {admin_user_id: message_object}

# Bot start time record karein
bot_start_time = datetime.now()

# --- Helper Functions ---
def is_admin(user_id: int) -> bool:
    """Check karta hai ki user admin hai ya nahi."""
    return user_id in ADMIN_USER_IDS

async def log_to_channel(text: str, parse_mode: str = None) -> None:
    """Log channel par message bheje ga."""
    if LOG_CHANNEL_ID:
        try:
            await telegram_bot.send_message(chat_id=LOG_CHANNEL_ID, text=text, parse_mode=parse_mode)
        except Exception as e:
            print(f"Error logging to channel: {e}")

# --- Bot Commands Handlers ---
async def start(update: Update, context: CallbackContext) -> None:
    """/start command ka handler."""
    user = update.message.from_user
    bot_info = await context.bot.get_me()
    bot_name = bot_info.first_name

    welcome_message = (
        f"👋 **Namaste {user.first_name}!**\n\n"
        f"Mai **{bot_name}** hun, aapka group moderator bot. "
        f"Mai aapke groups ko saaf suthra rakhne mein madad karta hun, "
        f"gaaliyon wale messages ko delete karta hun aur zaroorat padne par warning bhi deta hun.\n\n"
        f"**Mere features:**\n"
        f"• Gaali detection aur deletion\n"
        f"• User warnings aur actions (Mute, Ban, Kick)\n"
        f"• Incident logging\n\n"
        f"Agar aapko koi madad chahiye, toh niche diye gaye buttons ka upyog karein."
    )

    keyboard = [
        [InlineKeyboardButton("❓ Help", callback_data="help_menu")],
        [InlineKeyboardButton("🤖 Other Bots", callback_data="other_bots")], # Updated for clarity
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
    
async def stats(update: Update, context: CallbackContext) -> None:
    """/stats command ka handler."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Aapke paas is command ko use karne ki permission nahi hai.")
        return

    stats_message = (
        f"📊 **Bot Status:**\n\n"
        f"• Total Users (Approx): 1000+ (dummy)\n"
        f"• Total Groups (Approx): 100+ (dummy)\n"
        f"• Total Incidents Logged (Approx): 500+ (dummy)\n"
        f"• Uptime: {str(datetime.now() - bot_start_time).split('.')[0]} \n"
        f"• Last Check: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}"
    )
    await update.message.reply_text(stats_message, parse_mode='Markdown')

async def broadcast_command(update: Update, context: CallbackContext) -> None:
    """/broadcast command ka handler."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Aapke paas is command ko use karne ki permission nahi hai.")
        return
    
    await update.message.reply_text("Kripya apna message bhejein jo sabhi groups par broadcast karna hai.")
    BROADCAST_MESSAGE[update.effective_user.id] = None

async def handle_broadcast_message(update: Update, context: CallbackContext) -> None:
    """Broadcast message ko handle karega."""
    user_id = update.effective_user.id
    if is_admin(user_id) and user_id in BROADCAST_MESSAGE and BROADCAST_MESSAGE[user_id] is None:
        BROADCAST_MESSAGE[user_id] = update.message
        await update.message.reply_text("Message received. Kya aap ise broadcast karna chahenge?",
                                  reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Yes, Broadcast!", callback_data="confirm_broadcast")]]))
    else:
        await handle_message(update, context)


async def confirm_broadcast(update: Update, context: CallbackContext) -> None:
    """Broadcast confirmation ko handle karega."""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if not is_admin(user_id) or not BROADCAST_MESSAGE.get(user_id):
        await query.edit_message_text("Invalid action or session expired.")
        return
        
    broadcast_msg = BROADCAST_MESSAGE.pop(user_id)
    
    if broadcast_msg:
        dummy_group_ids = [
            -1001234567890, # Replace with actual group IDs where your bot is present
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
                print(f"Failed to broadcast to {chat_id}: {e}")
        
        await query.edit_message_text(f"Broadcast complete! Successfully sent to {success_count} groups. Failed: {fail_count}.")
    else:
        await query.edit_message_text("Broadcast message not found.")


async def welcome_new_member(update: Update, context: CallbackContext) -> None:
    """Naye member ke join hone par log karega."""
    new_members = update.message.new_chat_members
    chat = update.message.chat

    for member in new_members:
        if member.id == context.bot.get_me().id:
            log_message = (
                f"**🤖 Bot Joined Group:**\n"
                f"Group Name: `{chat.title}`\n"
                f"Group ID: `{chat.id}`\n"
                f"Members: {await chat.get_member_count()}"
            )
            await log_to_channel(log_message, parse_mode='Markdown')
        else:
            log_message = (
                f"**➕ Naya User Joined:**\n"
                f"User: {member.mention_html()} (`{member.id}`)\n"
                f"Group: `{chat.title}` (`{chat.id}`)"
            )
            await log_to_channel(log_message, parse_mode='HTML')

async def handle_message(update: Update, context: CallbackContext) -> None:
    """
    Har message ko process karega, gaaliyon ko detect karega aur action lega.
    """
    message_text = update.message.text
    user = update.message.from_user
    chat = update.message.chat
    
    if is_admin(user.id) and user.id in BROADCAST_MESSAGE and BROADCAST_MESSAGE[user.id] is None:
        await handle_broadcast_message(update, context)
        return

    if message_text and profanity_filter.contains_profanity(message_text):
        try:
            await context.bot.delete_message(chat_id=chat.id, message_id=update.message.message_id)
            print(f"Deleted abusive message from {user.username or user.full_name} in {chat.title or chat.type}.")
        except Exception as e:
            print(f"Error deleting message: {e}. Check bot's admin permissions to delete messages.")

        abuse_no = str(abs(hash(f"{user.id}-{chat.id}-{update.message.message_id}")))[:6]

        notification_message = (
            f"⛔ **Group Niyam Ulanghan**\n\n"
            f"{user.mention_html()} (`{user.id}`) ne aise shabdon ka istemaal kiya hai jo group ke niyam ke khilaaf hain. Message ko hata diya gaya hai.\n\n"
            f"@{GROUP_ADMIN_USERNAME}, kripya sadasya ke vyavhaar ki samiksha karein.\n\n"
            f"Case ID: `{abuse_no}`"
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
            text="*Check Case* ⬆️",
            reply_to_message_id=sent_notification.message_id,
            parse_mode='Markdown'
        )


async def button_callback_handler(update: Update, context: CallbackContext) -> None:
    """Button callbacks ko handle karega."""
    query = update.callback_query
    await query.answer()

    data = query.data
    
    # Check if the user is an admin for sensitive actions
    if data.startswith(("admin_actions_menu_", "mute_", "ban_", "kick_", "warn_user_", "view_case_")):
        if query.message.chat_id < 0: # It's a group chat
            try:
                member = await context.bot.get_chat_member(chat_id=query.message.chat_id, user_id=query.from_user.id)
                if not (member.status == 'administrator' or member.status == 'creator'):
                    await query.edit_message_text("Aapke paas is action ko perform karne ki permission nahi hai.")
                    return
            except Exception:
                await query.edit_message_text("Aapke paas is action ko perform karne ki permission nahi hai. Bot ko 'Get Group Info' permission ki zaroorat ho sakti hai.")
                return
        elif query.message.chat_id > 0 and not is_admin(query.from_user.id): # Private chat but not a super admin
            await query.edit_message_text("Aapke paas is action ko perform karne ki permission nahi hai.")
            return

    # --- Main Menu Options ---
    if data == "help_menu":
        help_text = (
            f"**Bot Help:**\n\n"
            f"• Gaaliyon wale messages delete kiye jayenge.\n"
            f"• Admins user par action le sakte hain (mute, ban, kick, warn).\n"
            f"• /start - Bot ka welcome message.\n"
            f"• /stats - Bot ka status (Admins only).\n"
            f"• /broadcast - Sabhi groups par message bhejen (Admins only).\n\n"
            f"Agar aapko aur madad chahiye, toh @asbhaibsr se contact karein."
        )
        keyboard = [[InlineKeyboardButton("⬅️ Back to Main", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(help_text, reply_markup=reply_markup, parse_mode='Markdown')

    elif data == "other_bots":
        # Corrected Markdown for links and proper formatting
        other_bots_text = (
            f"**🤖 Hamare Dusre Bots:**\n\n"
            f"• @asfilter_bot: Ek movie search bot hai jo aapko movies dhundhne mein madad karega.\n"
            f"• @askiangelbot: Ye ek baat karne wala bot hai, aap group par isse baat kar sakte hain."
        )
        keyboard = [[InlineKeyboardButton("⬅️ Back to Main", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(other_bots_text, reply_markup=reply_markup, parse_mode='Markdown')

    elif data == "donate_info":
        donate_text = (
            f"💖 **Dosto, agar aapko hamara bot aapke group ke liye accha lagta hai, "
            f"toh aap yahan thode se paise donate kar sakte hain jisse ye bot aage ke liye bana rahe.**\n\n"
            f"**UPI ID:** `arsadsaifi8272@ibl`\n\n"
            f"Aapki madad ke liye dhanyawaad!"
        )
        keyboard = [[InlineKeyboardButton("⬅️ Back to Main", callback_data="main_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(donate_text, reply_markup=reply_markup, parse_mode='Markdown')

    elif data == "main_menu":
        # Start command ka welcome message dobara bhejein
        user = query.from_user
        bot_info = await context.bot.get_me()
        bot_name = bot_info.first_name

        welcome_message = (
            f"👋 **Namaste {user.first_name}!**\n\n"
            f"Mai **{bot_name}** hun, aapka group moderator bot. "
            f"Mai aapke groups ko saaf suthra rakhne mein madad karta hun, "
            f"gaaliyon wale messages ko delete karta hun aur zaroorat padne par warning bhi deta hun.\n\n"
            f"**Mere features:**\n"
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


    # --- Admin Actions ---
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
                action_text = f"User **{user_id}** ko **permanently mute** kiya gaya hai."
            elif duration_seconds == 86400:
                action_text = f"User **{user_id}** ko **1 din** ke liye mute kiya gaya hai."
            elif duration_seconds == 2592000:
                action_text = f"User **{user_id}** ko **1 mahine** ke liye mute kiya gaya hai."
            elif duration_seconds == 7776000:
                action_text = f"User **{user_id}** ko **3 mahine** ke liye mute kiya gaya hai."
            elif duration_seconds == 15552000:
                action_text = f"User **{user_id}** ko **6 mahine** ke liye mute kiya gaya hai."
            else:
                action_text = f"User **{user_id}** ko **{duration_seconds} seconds** ke liye mute kiya gaya hai."

            await query.edit_message_text(action_text, parse_mode='Markdown')
        except Exception as e:
            await query.edit_message_text(f"Mute karte samay error hui: {e}")

    elif data.startswith("ban_"):
        parts = data.split('_')
        user_id = int(parts[1])
        chat_id = int(parts[2])
        try:
            await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
            await query.edit_message_text(f"User **{user_id}** ko group se **ban** kiya gaya hai.", parse_mode='Markdown')
        except Exception as e:
            await query.edit_message_text(f"Ban karte samay error hui: {e}")

    elif data.startswith("kick_"):
        parts = data.split('_')
        user_id = int(parts[1])
        chat_id = int(parts[2])
        try:
            await context.bot.kick_chat_member(chat_id=chat_id, user_id=user_id)
            await query.edit_message_text(f"User **{user_id}** ko group se **kick** kiya gaya hai.", parse_mode='Markdown')
        except Exception as e:
            await query.edit_message_text(f"Kick karte samay error hui: {e}")

    elif data.startswith("warn_user_"):
        parts = data.split('_')
        user_id = int(parts[2])
        chat_id = int(parts[3])

        try:
            user_info = await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
            warning_text_by_admin = (
                f"⚠️ **{user_info.user.first_name}**, aapne galat shabdon ka prayog kiya hai!\n\n"
                f"**🚨 Aisa dobara na karein, warna kadi kaarwayi ki ja sakti hai. 🚨**\n\n"
                f"Group ke niyam todne par aapko ban, mute, ya kick kiya ja sakta hai."
            )
            await context.bot.send_message(chat_id=chat_id, text=warning_text_by_admin, parse_mode='HTML')
            await query.edit_message_text(f"User **{user_id}** ko ek aur warning message bheja gaya hai.", parse_mode='Markdown')
        except Exception as e:
            await query.edit_message_text(f"Warning message bhejte samay error hui: {e}")


    elif data.startswith("view_case_"):
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
                f"**🚨 Naya Incident Case 🚨**\n\n"
                f"**Case Number:** `{case_number}`\n"
                f"**User:** {user_info.user.mention_html()} (`{user_info.user.id}`)\n"
                f"**Group:** {group_chat.title} (`{group_chat.id}`)\n"
                f"**Samay:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}\n\n"
                f"**Mool Message:**\n"
                f"```\n{original_abusive_content}\n```"
            )
            
            sent_case_message = await context.bot.send_message(
                chat_id=CASE_CHANNEL_ID,
                text=case_details_message,
                parse_mode='HTML'
            )
            
            case_channel_link = f"https://t.me/c/{str(CASE_CHANNEL_ID).replace('-100', '')}/{sent_case_message.message_id}"
            
            await query.edit_message_text(
                text=f"✅ Abuse Details successfully forwarded to the case channel.\n\n"
                     f"Case Link: [View Details]({case_channel_link})",
                parse_mode='Markdown',
                disable_web_page_preview=True
            )
        except Exception as e:
            await query.edit_message_text(f"Abuse Details forward karte samay error hui: {e}")
            print(f"Error forwarding case: {e}")

# --- Koyeb Health Check and Webhook Endpoint ---
@app.route('/')
def health_check():
    """Koyeb health checks ke liye simple endpoint."""
    return "Bot is healthy!", 200

@app.route('/telegram', methods=['POST'])
async def telegram_webhook():
    """Telegram webhook updates ko process karega."""
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), telegram_bot)
        # application के अपडेट को प्रोसेस करें
        await application.process_update(update)
        return 'ok'
    return 'Bad Request'

# --- Main Execution ---
if __name__ == '__main__':
    # Dispatcher को कॉन्फ़िगर करें
    dispatcher = application

    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("stats", stats))
    dispatcher.add_handler(CommandHandler("broadcast", broadcast_command))
    dispatcher.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member))
    dispatcher.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    dispatcher.add_handler(CallbackQueryHandler(button_callback_handler))
    dispatcher.add_handler(CallbackQueryHandler(view_case_details_forward, pattern=r'^view_case_'))

    # Telegram बॉट को वेबहुक URL सेट करने के लिए एक बार शुरू करें
    # यह सिर्फ़ डिप्लॉयमेंट के समय होना चाहिए, हर बार Flask सर्वर स्टार्ट होने पर नहीं।
    # Koyeb में, यह सुनिश्चित करने के लिए कि बॉट टोकन और WEBHOOK_URL सेट हैं, आप इसे
    # एक अलग Koyeb डिप्लॉयमेंट कमांड में या Koyeb के Init Command में चला सकते हैं।
    # यहाँ, हम इसे `if __name__ == '__main__':` ब्लॉक में रखेंगे, लेकिन ध्यान दें
    # कि यह हर बार ऐप के फिर से शुरू होने पर चलेगा।
    async def set_webhook_on_startup():
        print(f"Setting webhook to {WEBHOOK_URL}/telegram")
        try:
            await telegram_bot.set_webhook(url=f"{WEBHOOK_URL}/telegram")
            print("Webhook set successfully!")
        except Exception as e:
            print(f"Error setting webhook: {e}")

    # Flask ऐप को एक अलग थ्रेड में चलाएं
    flask_thread = threading.Thread(target=lambda: app.run(host='0.0.0.0', port=PORT))
    flask_thread.start()

    # वेबहुक सेट करें (इसे async होने के कारण एक asyncio इवेंट लूप में चलाने की आवश्यकता है)
    import asyncio
    asyncio.run(set_webhook_on_startup())

    print("Telegram Bot is running in webhook mode.")
    # Flask ऐप अब अनुरोधों की प्रतीक्षा कर रहा है।
    # polling_action_cb अब उपयोग नहीं किया जाता है क्योंकि हम वेबहुक का उपयोग कर रहे हैं।
    # application.run_polling() भी उपयोग नहीं किया जाता है।
