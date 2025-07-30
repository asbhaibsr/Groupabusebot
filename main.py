# main.py

import os
import threading
import time
from datetime import datetime, timedelta

from flask import Flask, request, jsonify
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, filters, CallbackContext,  # 'Filters' ko 'filters' se replace kiya
    CallbackQueryHandler, Application, TypeHandler # 'ErrorHandler' ko hata diya, aur naye imports add kiye
)

# Custom module import
from profanity_filter import ProfanityFilter

# --- Configuration ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CASE_CHANNEL_ID = os.getenv("CASE_CHANNEL_ID") # Case logging ke liye
LOG_CHANNEL_ID = os.getenv("LOG_CHANNEL_ID")   # Naye user/group join ke logs ke liye
MONGO_DB_URI = os.getenv("MONGO_DB_URI") # MongoDB connection string
GROUP_ADMIN_USERNAME = os.getenv("GROUP_ADMIN_USERNAME", "admin") # Default @admin, change if needed for specific group admin tag

# Admin User IDs (Jinhe broadcast/stats commands ka access hoga)
ADMIN_USER_IDS = [int(admin_id) for admin_id in os.getenv("ADMIN_USER_IDS", "").split(',') if admin_id]
# Example: ADMIN_USER_IDS = [123456789, 987654321]

# Flask App Initialization
app = Flask(__name__)

# --- Health Check Endpoint for Koyeb ---
@app.route('/')
def health_check():
    """
    Koyeb ke health checks ke liye simple endpoint.
    Ye sirf 200 OK status return karega.
    """
    return "Bot is healthy!", 200

# --- Telegram Bot Setup ---
telegram_bot = Bot(token=TELEGRAM_BOT_TOKEN)

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
# Real-world scenarios will use FSM (Finite State Machine) or more robust state management
BROADCAST_MESSAGE = {} # {admin_user_id: message_object}

# --- Helper Functions ---
def is_admin(user_id: int) -> bool:
    """Check karta hai ki user admin hai ya nahi."""
    return user_id in ADMIN_USER_IDS

def log_to_channel(text: str, parse_mode: str = None) -> None:
    """Log channel par message bheje ga."""
    if LOG_CHANNEL_ID:
        try:
            telegram_bot.send_message(chat_id=LOG_CHANNEL_ID, text=text, parse_mode=parse_mode)
        except Exception as e:
            print(f"Error logging to channel: {e}")

# --- Bot Commands Handlers ---
def start(update: Update, context: CallbackContext) -> None:
    """/start command ka handler."""
    user = update.message.from_user
    bot_name = context.bot.get_me().first_name # Bot ka naam dynamically fetch karein

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
        [InlineKeyboardButton("📢 Update Channel", url="https://t.me/asbhai_bsr")],
        [InlineKeyboardButton("🤖 Other Bots", callback_data="other_bots")],
        [InlineKeyboardButton("💖 Donate", callback_data="donate_info")],
        [InlineKeyboardButton("📈 Promotion", url="https://t.me/asprmotion")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    update.message.reply_text(
        text=welcome_message,
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
    
    # User ko MongoDB mein store/update karein
    # users_collection.update_one(
    #     {"user_id": user.id},
    #     {"$set": {"username": user.username, "first_name": user.first_name, "last_name": user.last_name, "last_interaction": datetime.now()}},
    #     upsert=True
    # )

def stats(update: Update, context: CallbackContext) -> None:
    """/stats command ka handler."""
    if not is_admin(update.effective_user.id):
        update.message.reply_text("Aapke paas is command ko use karne ki permission nahi hai.")
        return

    # Real stats MongoDB se fetch honge
    # total_users = users_collection.count_documents({}) if 'users_collection' in globals() else 0
    # total_groups = groups_collection.count_documents({}) if 'groups_collection' in globals() else 0
    # total_incidents = incidents_collection.count_documents({}) if 'incidents_collection' in globals() else 0

    stats_message = (
        f"📊 **Bot Status:**\n\n"
        f"• Total Users (Approx): 1000+ (dummy)\n"
        f"• Total Groups (Approx): 100+ (dummy)\n"
        f"• Total Incidents Logged (Approx): 500+ (dummy)\n"
        f"• Uptime: {str(datetime.now() - bot_start_time).split('.')[0]} \n" # Bot start time global var se
        f"• Last Check: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}"
    )
    update.message.reply_text(stats_message, parse_mode='Markdown')

def broadcast_command(update: Update, context: CallbackContext) -> None:
    """/broadcast command ka handler."""
    if not is_admin(update.effective_user.id):
        update.message.reply_text("Aapke paas is command ko use karne ki permission nahi hai.")
        return
    
    update.message.reply_text("Kripya apna message bhejein jo sabhi groups par broadcast karna hai.")
    # State set karein ki next message broadcast message hoga
    BROADCAST_MESSAGE[update.effective_user.id] = None # Flag to indicate awaiting broadcast message

def handle_broadcast_message(update: Update, context: CallbackContext) -> None:
    """Broadcast message ko handle karega."""
    user_id = update.effective_user.id
    if is_admin(user_id) and user_id in BROADCAST_MESSAGE and BROADCAST_MESSAGE[user_id] is None:
        BROADCAST_MESSAGE[user_id] = update.message # Message ko store karein
        update.message.reply_text("Message received. Kya aap ise broadcast karna chahenge?",
                                  reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Yes, Broadcast!", callback_data="confirm_broadcast")]]))
    else:
        # Agar admin nahi hai ya state sahi nahi hai, toh normal message handler ko jaane dein
        handle_message(update, context)


def confirm_broadcast(update: Update, context: CallbackContext) -> None:
    """Broadcast confirmation ko handle karega."""
    query = update.callback_query
    query.answer()
    
    user_id = query.from_user.id
    if not is_admin(user_id) or not BROADCAST_MESSAGE.get(user_id):
        query.edit_message_text("Invalid action or session expired.")
        return
        
    broadcast_msg = BROADCAST_MESSAGE.pop(user_id) # Message ko retrieve aur remove karein
    
    if broadcast_msg:
        # Saare groups ko fetch karein jismein bot added hai
        # group_ids = [group['chat_id'] for group in groups_collection.find({})]
        
        # Dummy group IDs for testing
        dummy_group_ids = [
            -1001234567890, # Replace with actual group IDs where your bot is present
            # -1009876543210
        ]
        
        success_count = 0
        fail_count = 0
        for chat_id in dummy_group_ids: # Real mein group_ids use hoga
            try:
                # Message ko forward karein jisse formatting/media intact rahe
                context.bot.copy_message(
                    chat_id=chat_id,
                    from_chat_id=broadcast_msg.chat_id,
                    message_id=broadcast_msg.message_id
                )
                success_count += 1
                time.sleep(0.1) # Flood limits se bachne ke liye
            except Exception as e:
                fail_count += 1
                print(f"Failed to broadcast to {chat_id}: {e}")
        
        query.edit_message_text(f"Broadcast complete! Successfully sent to {success_count} groups. Failed: {fail_count}.")
    else:
        query.edit_message_text("Broadcast message not found.")


def welcome_new_member(update: Update, context: CallbackContext) -> None:
    """Naye member ke join hone par log karega."""
    new_members = update.message.new_chat_members
    chat = update.message.chat

    for member in new_members:
        if member.id == context.bot.get_me().id:
            # Bot khud group join hua hai
            log_message = (
                f"**🤖 Bot Joined Group:**\n"
                f"Group Name: `{chat.title}`\n"
                f"Group ID: `{chat.id}`\n"
                f"Members: {chat.get_member_count()}"
            )
            log_to_channel(log_message, parse_mode='Markdown')
            # groups_collection.update_one({"chat_id": chat.id}, {"$set": {"title": chat.title, "last_joined": datetime.now()}}, upsert=True)
        else:
            # Koi naya user group join hua hai
            log_message = (
                f"**➕ Naya User Joined:**\n"
                f"User: {member.mention_html()} (`{member.id}`)\n"
                f"Group: `{chat.title}` (`{chat.id}`)"
            )
            log_to_channel(log_message, parse_mode='HTML')
            # users_collection.update_one(
            #     {"user_id": member.id},
            #     {"$set": {"username": member.username, "first_name": member.first_name, "last_name": member.last_name, "last_seen_in_group": datetime.now()}},
            #     upsert=True
            # )

def handle_message(update: Update, context: CallbackContext) -> None:
    """
    Har message ko process karega, gaaliyon ko detect karega aur action lega.
    """
    message_text = update.message.text
    user = update.message.from_user
    chat = update.message.chat
    
    # Agar user admin hai aur broadcast message ki state set hai, toh broadcast handler ko call karein
    if is_admin(user.id) and user.id in BROADCAST_MESSAGE and BROADCAST_MESSAGE[user.id] is None:
        handle_broadcast_message(update, context)
        return # Important: Yahan se return karein takki normal message handling na ho

    if message_text and profanity_filter.contains_profanity(message_text):
        # Message delete karein
        try:
            context.bot.delete_message(chat_id=chat.id, message_id=update.message.message_id)
            print(f"Deleted abusive message from {user.username or user.full_name} in {chat.title or chat.type}.")
        except Exception as e:
            print(f"Error deleting message: {e}")

        # Generate a unique abuse number (for display)
        abuse_no = str(abs(hash(f"{user.id}-{chat.id}-{update.message.message_id}")))[:6] # Short unique ID

        # New style notification message for the group
        notification_message = (
            f"⛔ **Group Niyam Ulanghan**\n\n"
            f"{user.mention_html()} (`{user.id}`) ne aise shabdon ka istemaal kiya hai jo group ke niyam ke khilaaf hain. Message ko hata diya gaya hai.\n\n"
            f"@{GROUP_ADMIN_USERNAME}, kripya sadasya ke vyavhaar ki samiksha karein.\n\n"
            f"Case ID: `{abuse_no}`"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("👤 User Profile", url=f"tg://user?id={user.id}"), # Direct link to user's profile
                InlineKeyboardButton("🔧 Admin Actions", callback_data=f"admin_actions_menu_{user.id}_{chat.id}")
            ],
            [
                InlineKeyboardButton("📄 View Abuse Details", callback_data=f"view_case_{user.id}_{chat.id}_{update.message.message_id}_{abuse_no}") # Pass abuse_no
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        sent_notification = context.bot.send_message(
            chat_id=chat.id,
            text=notification_message,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        
        # MongoDB mein incident log karein (uncomment and implement)
        # incident_id = incidents_collection.insert_one({
        #     "user_id": user.id,
        #     "username": user.username,
        #     "chat_id": chat.id,
        #     "chat_title": chat.title,
        #     "abusive_message_content": message_text,
        #     "timestamp": datetime.now(),
        #     "warning_message_id": sent_notification.message_id,
        #     "case_status": "open",
        #     "action_taken": None,
        #     "abuse_number": abuse_no # Store abuse number
        # }).inserted_id
        
        context.bot.send_message(
            chat_id=chat.id,
            text="*Check Case* ⬆️",
            reply_to_message_id=sent_notification.message_id,
            parse_mode='Markdown'
        )


def button_callback_handler(update: Update, context: CallbackContext) -> None:
    """Button callbacks ko handle karega."""
    query = update.callback_query
    query.answer()

    data = query.data
    
    # Admin check for sensitive actions
    if data.startswith(("admin_actions_menu_", "mute_", "ban_", "kick_", "warn_user_", "view_case_")):
        # For group specific actions, ensure the user clicking is an admin of that group
        if query.message.chat_id < 0: # It's a group chat
            try:
                member = context.bot.get_chat_member(chat_id=query.message.chat_id, user_id=query.from_user.id)
                if not (member.status == 'administrator' or member.status == 'creator'):
                    query.edit_message_text("Aapke paas is action ko perform karne ki permission nahi hai.")
                    return
            except Exception:
                query.edit_message_text("Aapke paas is action ko perform karne ki permission nahi hai. Bot ko 'Get Group Info' permission ki zaroorat ho sakti hai.")
                return
        elif query.message.chat_id > 0 and not is_admin(query.from_user.id): # Private chat but not a super admin
            query.edit_message_text("Aapke paas is action ko perform karne ki permission nahi hai.")
            return

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
        query.edit_message_text(help_text, parse_mode='Markdown')

    elif data == "other_bots":
        other_bots_text = (
            f"**🤖 Hamare Dusre Bots:**\n\n"
            f"• @asfilter_bot: Ek movie search bot hai jo aapko movies dhundhne mein madad karega.\n"
            f"• @askiangelbot: Ye ek baat karne wala bot hai, aap group par isse baat kar sakte hain."
        )
        query.edit_message_text(other_bots_text, parse_mode='Markdown')

    elif data == "donate_info":
        donate_text = (
            f"💖 **Dosto, agar aapko hamara bot aapke group ke liye accha lagta hai, "
            f"toh aap yahan thode se paise donate kar sakte hain jisse ye bot aage ke liye bana rahe.**\n\n"
            f"**UPI ID:** `arsadsaifi8272@ibl`\n\n"
            f"Aapki madad ke liye dhanyawaad!"
        )
        query.edit_message_text(donate_text, parse_mode='Markdown')
        
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
        query.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(action_keyboard))

    elif data.startswith("mute_time_"):
        parts = data.split('_')
        user_id = int(parts[2])
        chat_id = int(parts[3])

        mute_time_keyboard = [
            [
                InlineKeyboardButton("1 Day", callback_data=f"mute_{user_id}_{chat_id}_{86400}"), # 24 hours
                InlineKeyboardButton("1 Month", callback_data=f"mute_{user_id}_{chat_id}_{2592000}") # 30 days
            ],
            [
                InlineKeyboardButton("3 Months", callback_data=f"mute_{user_id}_{chat_id}_{7776000}"), # 90 days
                InlineKeyboardButton("6 Months", callback_data=f"mute_{user_id}_{chat_id}_{15552000}") # 180 days
            ],
            [
                InlineKeyboardButton("Permanent", callback_data=f"mute_{user_id}_{chat_id}_0") # Forever mute
            ]
        ]
        query.edit_message_text(
            text=f"Kitne samay ke liye mute karna hai {user_id} ko?",
            reply_markup=InlineKeyboardMarkup(mute_time_keyboard)
        )

    elif data.startswith("mute_") and len(data.split('_')) == 4: # Actual mute action
        parts = data.split('_')
        user_id = int(parts[1])
        chat_id = int(parts[2])
        duration_seconds = int(parts[3])
        
        try:
            permissions = ChatPermissions(can_send_messages=False)
            until_date = datetime.now() + timedelta(seconds=duration_seconds) if duration_seconds > 0 else 0
            
            context.bot.restrict_chat_member(
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

            query.edit_message_text(action_text, parse_mode='Markdown')
            # incidents_collection.update_one({"user_id": user_id, "warning_message_id": query.message.reply_to_message.message_id}, {"$set": {"action_taken": "muted", "mute_duration": duration_seconds}})
        except Exception as e:
            query.edit_message_text(f"Mute karte samay error hui: {e}")

    elif data.startswith("ban_"):
        parts = data.split('_')
        user_id = int(parts[1])
        chat_id = int(parts[2])
        try:
            context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
            query.edit_message_text(f"User **{user_id}** ko group se **ban** kiya gaya hai.", parse_mode='Markdown')
            # incidents_collection.update_one({"user_id": user_id, "warning_message_id": query.message.reply_to_message.message_id}, {"$set": {"action_taken": "banned"}})
        except Exception as e:
            query.edit_message_text(f"Ban karte samay error hui: {e}")

    elif data.startswith("kick_"):
        parts = data.split('_')
        user_id = int(parts[1])
        chat_id = int(parts[2])
        try:
            context.bot.kick_chat_member(chat_id=chat_id, user_id=user_id)
            # Kick ke baad user re-join kar sakta hai. Agar permanent ban chahiye toh `ban_chat_member` use karein.
            query.edit_message_text(f"User **{user_id}** ko group se **kick** kiya gaya hai.", parse_mode='Markdown')
            # incidents_collection.update_one({"user_id": user_id, "warning_message_id": query.message.reply_to_message.message_id}, {"$set": {"action_taken": "kicked"}})
        except Exception as e:
            query.edit_message_text(f"Kick karte samay error hui: {e}")

    elif data.startswith("warn_user_"):
        parts = data.split('_')
        user_id = int(parts[2])
        chat_id = int(parts[3])

        try:
            # User ko warning message bhejein (yahan group mein hi warning di ja rahi hai)
            user_info = context.bot.get_chat_member(chat_id=chat_id, user_id=user_id).user
            warning_text_by_admin = (
                f"⚠️ **{user_info.first_name}**, aapne galat shabdon ka prayog kiya hai!\n\n"
                f"**🚨 Aisa dobara na karein, warna kadi kaarwayi ki ja sakti hai. 🚨**\n\n"
                f"Group ke niyam todne par aapko ban, mute, ya kick kiya ja sakta hai."
            )
            context.bot.send_message(chat_id=chat_id, text=warning_text_by_admin, parse_mode='HTML')
            query.edit_message_text(f"User **{user_id}** ko ek aur warning message bheja gaya hai.", parse_mode='Markdown')
            # incidents_collection.update_one({"user_id": user_id, "warning_message_id": query.message.reply_to_message.message_id}, {"$set": {"action_taken": "warned_again"}})
        except Exception as e:
            query.edit_message_text(f"Warning message bhejte samay error hui: {e}")


    elif data.startswith("view_case_"):
        parts = data.split('_')
        user_id_for_case = int(parts[2])
        group_id_for_case = int(parts[3])
        original_message_id = int(parts[4])
        abuse_no_from_callback = parts[5] # Get abuse number from callback data

        original_abusive_content = "Original message content not available (deleted or not logged)."
        # Agar aap MongoDB use kar rahe hain, toh yahan se abusive content fetch kar sakte hain
        # incident = incidents_collection.find_one({"user_id": user_id_for_case, "chat_id": group_id_for_case, "abuse_number": abuse_no_from_callback})
        # if incident and "abusive_message_content" in incident:
        #     original_abusive_content = incident["abusive_message_content"]

        # Case number already generated in handle_message, use the one from callback
        case_number = "CASE-" + abuse_no_from_callback
        
        try:
            group_chat = context.bot.get_chat(chat_id=group_id_for_case)
            user_info = context.bot.get_chat_member(chat_id=group_id_for_case, user_id=user_id_for_case).user
            
            case_details_message = (
                f"**🚨 Naya Incident Case 🚨**\n\n"
                f"**Case Number:** `{case_number}`\n"
                f"**User:** {user_info.mention_html()} (`{user_info.id}`)\n"
                f"**Group:** {group_chat.title} (`{group_chat.id}`)\n"
                f"**Samay:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}\n\n"
                f"**Mool Message:**\n"
                f"```\n{original_abusive_content}\n```"
            )
            
            sent_case_message = context.bot.send_message( # Store the sent message object
                chat_id=CASE_CHANNEL_ID,
                text=case_details_message,
                parse_mode='HTML'
            )
            
            # Direct link to the forwarded message in the case channel
            case_channel_link = f"https://t.me/c/{str(CASE_CHANNEL_ID).replace('-100', '')}/{sent_case_message.message_id}"
            
            query.edit_message_text(
                text=f"✅ Abuse Details successfully forwarded to the case channel.\n\n"
                     f"Case Link: [View Details]({case_channel_link})",
                parse_mode='Markdown',
                disable_web_page_preview=True # To avoid showing a preview of the channel link
            )
            
            # incidents_collection.update_one({"user_id": user_id_for_case, "abuse_number": abuse_no_from_callback}, {"$set": {"case_status": "forwarded", "case_channel_message_id": sent_case_message.message_id}})
        except Exception as e:
            query.edit_message_text(f"Abuse Details forward karte samay error hui: {e}")
            print(f"Error forwarding case: {e}")

# Error Handler ab yahan se hata diya gaya hai, ise main polling loop mein manage kiya jayega.
# def error_handler(update: object, context: CallbackContext) -> None:
#     """Log Errors caused by Updates."""
#     print(f'Update {update} caused error {context.error}')

# --- Bot Polling Thread ---
bot_start_time = datetime.now() # Bot ka start time record karein

def run_telegram_bot():
    """Telegram bot ko run karega polling mode mein."""
    # Updater ki jagah Application.builder().build() ka upyog karein
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    dispatcher = application # Dispatcher ab Application object hi hai

    # Command Handlers
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("stats", stats))
    dispatcher.add_handler(CommandHandler("broadcast", broadcast_command))


    # Message Handler (text messages, not commands)
    # Naye members ke liye handler
    dispatcher.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, welcome_new_member)) # 'Filters' ko 'filters' se replace kiya
    
    # Abusive messages aur broadcast message response ke liye
    dispatcher.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)) # 'Filters' ko 'filters' se replace kiya
    
    # Callback Query Handler (buttons ke liye)
    dispatcher.add_handler(CallbackQueryHandler(button_callback_handler))

    # Error handling directly Application.run_polling() mein manage hota hai.
    # dispatcher.add_handler(ErrorHandler(error_handler)) # Is line ko hata diya

    # Bot ko start karein
    print("Starting Telegram Bot...")
    application.run_polling(drop_pending_updates=True) # Updater ki jagah application.run_polling()
    # application.run_polling() automatically keyboard interrupts (Ctrl+C) ko handle karta hai
    # updater.idle() ki zaroorat nahi hai
    

# --- Main Execution ---
if __name__ == '__main__':
    # Flask server ko alag thread mein run karein
    flask_thread = threading.Thread(target=lambda: app.run(host='0.0.0.0', port=os.getenv("PORT", 5000)))
    flask_thread.start()

    # Telegram bot ko main thread mein run karein
    run_telegram_bot()
