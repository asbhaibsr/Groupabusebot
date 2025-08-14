import asyncio
import random
from pyrogram import Client, enums
from pymongo import MongoClient
import logging

# Set up logging
logger = logging.getLogger(__name__)

# Reminder settings
REMINDER_INTERVAL_HOURS = 2  # Interval for sending reminders (in hours)
USERS_TO_TAG_COUNT = 5       # Number of online users to tag

# List of engaging messages
REMINDER_MESSAGES = {
    "funny": [
        "Sab log itne shant kyun hain? Kya main akele baat kar raha hoon? 😅",
        "Koi hai yahan? Ya sab Telegram band karke so gaye hain? 😴",
        "Ek baat batao, agar main insan hota to kya abhi bhi aap log mujhe use karte? 🤔"
    ],
    "romantic": [
        "Aapke bina yeh group kitna soona lagta hai. Koi to kuch romantic baatein karo na! ❤️",
        "Kisi ko propose karne ka mood hai? Yeh group aapki help kar sakta hai! 😉",
        "Har love story ki shuruat dosti se hoti hai, to chalo dosti karte hain. 👋"
    ],
    "commands": [
        "Naye users ke liye: bot ki commands janne ke liye `/help` type karein. 🤖",
        "Bored ho rahe ho? Chalo, game khelte hain! `/tictac` command se shuru karo. 🕹️",
        "Aap group settings change karna chahte hain? `/settings` command use karein. ⚙️"
    ],
    "general": [
        "Aaj ka din kaisa raha sabka? Koi interesting story hai? 💬",
        "Apne favorite movie/gaane/show ke baare mein batao. 🎬",
        "Group mein conversation shuru karne ke liye koi idea chahiye? Bas pucho! 💡"
    ]
}

def get_random_message():
    """Fetches a random message from the dictionary."""
    message_type = random.choice(list(REMINDER_MESSAGES.keys()))
    return random.choice(REMINDER_MESSAGES[message_type])

async def send_random_reminder(client: Client, db: MongoClient):
    """Sends a random reminder to all active groups."""
    if db is None:
        logger.warning("MongoDB not connected. Cannot send reminders.")
        return

    try:
        active_groups = [doc['chat_id'] for doc in db.groups.find({})]
    except Exception as e:
        logger.error(f"Error fetching active groups from DB: {e}")
        return

    for chat_id in active_groups:
        try:
            bot_member = await client.get_chat_member(chat_id, client.me.id)
            if bot_member.status == enums.ChatMemberStatus.ADMINISTRATOR:
                
                online_members = []
                # Pyrogram's `get_chat_members` is an async iterator
                async for member in client.get_chat_members(chat_id):
                    if not member.user.is_bot:
                        online_members.append(member.user)
                
                # Shuffle the list and select a few members to tag
                random.shuffle(online_members)
                members_to_tag = online_members[:USERS_TO_TAG_COUNT]
                
                mentions = " ".join([f"<a href='tg://user?id={user.id}'>{user.first_name}</a>" for user in members_to_tag])
                
                random_message = get_random_message()
                final_message = f"{mentions}\n\n{random_message}" if mentions else random_message
                
                await client.send_message(chat_id, final_message, parse_mode=enums.ParseMode.HTML)
                logger.info(f"Sent reminder to group {chat_id}")
                
                await asyncio.sleep(5)  # Add a small delay between groups to avoid FloodWait
        except Exception as e:
            logger.error(f"Error sending random reminder to chat {chat_id}: {e}")

async def reminder_scheduler(client: Client, db: MongoClient):
    """Schedules the reminder to run at a fixed interval."""
    while True:
        await asyncio.sleep(REMINDER_INTERVAL_HOURS * 3600)  # Wait for the set interval
        logger.info("Reminder scheduler started...")
        await send_random_reminder(client, db)
