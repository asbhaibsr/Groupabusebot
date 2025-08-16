import logging
import asyncio
from pyrogram import Client, enums, errors
from pyrogram.types import Message, ChatPermissions, InlineKeyboardMarkup, InlineKeyboardButton
from database import get_warn_settings, increment_warning_sync, get_notification_delete_time
from config import LOG_CHANNEL_ID, ADMIN_USER_IDS, URL_PATTERN
from datetime import datetime
from pyrogram.errors import BadRequest, Forbidden, FloodWait

logger = logging.getLogger(__name__)

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_USER_IDS

async def is_group_admin(client: Client, chat_id: int, user_id: int) -> bool:
    try:
        member = await client.get_chat_member(chat_id, user_id)
        return member.status in [enums.ChatMemberStatus.OWNER, enums.ChatMemberStatus.ADMINISTRATOR]
    except (BadRequest, Forbidden):
        return False
    except Exception as e:
        logger.error(f"Error checking admin status for user {user_id} in chat {chat_id}: {e}")
        return False

async def log_to_channel(client: Client, text: str, parse_mode: enums.ParseMode = None) -> None:
    if not LOG_CHANNEL_ID or LOG_CHANNEL_ID == -1:
        logger.warning("LOG_CHANNEL_ID is not set or invalid, cannot log to channel.")
        return
    try:
        await client.send_message(chat_id=LOG_CHANNEL_ID, text=text, parse_mode=parse_mode)
    except Forbidden:
        logger.error(f"Bot does not have permissions to send messages to log channel {LOG_CHANNEL_ID}.")
    except BadRequest as e:
        logger.error(f"Cannot send to log channel: {e}. Channel may not exist or bot lacks permissions.")
    except Exception as e:
        logger.error(f"Error logging to channel: {e}")

async def handle_incident(client, db, chat_id, user, reason, original_message: Message, case_type, category=None):
    original_message_id = original_message.id
    full_name = f"{user.first_name}{(' ' + user.last_name) if user.last_name else ''}"
    user_mention_text = f"<a href='tg://user?id={user.id}'>{full_name}</a>"

    try:
        await client.delete_messages(chat_id=chat_id, message_ids=original_message_id)
        logger.info(f"Deleted {reason} message from {user.username or user.mention} ({user.id}) in {chat_id}.")
    except Exception as e:
        logger.error(f"Error deleting message in {chat_id}: {e}. Make sure the bot has 'Delete Messages' admin permission.")

    notification_text = ""
    keyboard = []
    
    warn_limit, punishment = get_warn_settings(chat_id, category) if category else (3, "mute")

    if case_type == "edited_message_deleted":
        notification_text = f"<b>📝 Edited Message Deleted!</b>\n\nHey {user_mention_text}, your edited message was removed as editing messages to circumvent rules is not allowed."
        keyboard = [[InlineKeyboardButton("🗑️ Close", callback_data="close")]]

    elif case_type == "warn":
        count = increment_warning_sync(chat_id, user.id, category)
        notification_text = f"<b>🚫 Hey {user_mention_text}, your message was removed!</b>\n\nReason: {reason}\n<b>This is your warning number {count}/{warn_limit}.</b>"
        keyboard = [[InlineKeyboardButton("🗑️ Close", callback_data="close")]]
        
    elif case_type == "punished":
        if punishment == "mute":
             await client.restrict_chat_member(chat_id, user.id, ChatPermissions())
             notification_text = f"<b>🚫 Hey {user_mention_text}, you have been muted!</b>\n\nYou reached the maximum warning limit ({warn_limit}) for violating rules."
             keyboard = [[InlineKeyboardButton("Unmute ✅", callback_data=f"unmute_{user.id}_{chat_id}"), InlineKeyboardButton("🗑️ Close", callback_data="close")]]
        else:
            await client.ban_chat_member(chat_id, user.id)
            notification_text = f"<b>🚫 Hey {user_mention_text}, you have been banned!</b>\n\nYou reached the maximum warning limit ({warn_limit}) for violating rules."
            keyboard = [[InlineKeyboardButton("🗑️ Close", callback_data="close")]]

    if notification_text:
        try:
            sent_notification = await client.send_message(
                chat_id=chat_id,
                text=notification_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=enums.ParseMode.HTML
            )
            logger.info(f"Incident notification sent for user {user.id} in chat {chat_id}.")
            delete_time_minutes = get_notification_delete_time(chat_id)
            if delete_time_minutes > 0:
                await asyncio.sleep(delete_time_minutes * 60)
                try:
                    await client.delete_messages(chat_id=chat_id, message_ids=sent_notification.id)
                except Exception as e:
                    logger.error(f"Error deleting timed notification: {e}")

        except Exception as e:
            logger.error(f"Error sending notification in chat {chat_id}: {e}. Make sure bot has 'Post Messages' permission.")

async def broadcast_to_all(client: Client, db, message: Message):
    if db is None:
        return
    success_count, fail_count = 0, 0
    
    # Send to all users
    try:
        users = db.users.find({}, {"user_id": 1})
        for user_doc in users:
            try:
                await message.copy(user_doc["user_id"])
                success_count += 1
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Failed to send broadcast to user {user_doc['user_id']}: {e}")
                fail_count += 1
    except Exception as e:
        logger.error(f"Error fetching users for broadcast: {e}")

    # Send to all groups
    try:
        groups = db.groups.find({}, {"chat_id": 1})
        for group_doc in groups:
            try:
                await message.copy(group_doc["chat_id"])
                success_count += 1
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Failed to send broadcast to group {group_doc['chat_id']}: {e}")
                fail_count += 1
    except Exception as e:
        logger.error(f"Error fetching groups for broadcast: {e}")

    broadcast_report = f"<b>📢 Broadcast Complete!</b>\n\n✅ Sent to: {success_count} chats.\n❌ Failed to send to: {fail_count} chats."
    await client.send_message(message.from_user.id, broadcast_report, parse_mode=enums.ParseMode.HTML)
    logger.info(f"Broadcast finished. Success: {success_count}, Fail: {fail_count}")
