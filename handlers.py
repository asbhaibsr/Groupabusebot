import logging
import asyncio
import re
import time
from datetime import datetime
from pyrogram import Client, filters, enums, errors
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ChatPermissions
from pyrogram.errors import BadRequest, Forbidden, MessageNotModified, ChatAdminRequired
import random

from utils import is_admin, is_group_admin, handle_incident, log_to_channel, broadcast_to_all
from database import get_warn_settings, increment_warning_sync, get_warnings_sync, is_whitelisted_sync, get_group_settings, update_group_setting, update_notification_delete_time, get_whitelist_sync, remove_whitelist_sync, reset_warnings_sync
from config import ADMIN_USER_IDS, URL_PATTERN
from game_logic import TIC_TAC_TOE_GAMES, TIC_TAC_TOE_TASK, check_win, check_draw, get_tictac_keyboard, end_tictactoe_game

logger = logging.getLogger(__name__)

def setup_all_handlers(client, db, LOCKED_MESSAGES, SECRET_CHATS, TIC_TAC_TOE_GAMES, TIC_TAC_TOE_TASK, BROADCAST_MESSAGE, profanity_filter):

    @client.on_message(filters.command("start"))
    async def start(client: Client, message: Message):
        user = message.from_user
        chat = message.chat
        bot_info = await client.get_me()
        bot_name = bot_info.first_name
        bot_username = bot_info.username
        add_to_group_url = f"https://t.me/{bot_username}?startgroup=true"

        if chat.type == enums.ChatType.PRIVATE:
            welcome_message = f"👋 <b>Namaste {user.first_name}!</b>\n\nMai <b>{bot_name}</b> hun, aapka group moderator bot. Mai aapke groups ko saaf suthra rakhne mein madad karta hun."
            keyboard = [[InlineKeyboardButton("➕ Add Me To Your Group", url=add_to_group_url)], [InlineKeyboardButton("❓ Help", callback_data="help_menu"), InlineKeyboardButton("🤖 Other Bots", callback_data="other_bots")], [InlineKeyboardButton("📢 Update Channel", url="https://t.me/asbhai_bsr"), InlineKeyboardButton("💖 Donate", callback_data="donate_info")], [InlineKeyboardButton("📈 Promotion", url="https://t.me/asprmotion")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await message.reply_text(text=welcome_message, reply_markup=reply_markup, parse_mode=enums.ParseMode.HTML, disable_web_page_preview=True)
            if db:
                db.users.update_one({"user_id": user.id}, {"$set": {"first_name": user.first_name, "username": user.username, "last_interaction": datetime.now()}}, upsert=True)
            log_message = f"<b>✨ New User Started Bot:</b>\nUser: {user.first_name} (`{user.id}`)\nUsername: @{user.username if user.username else 'N/A'}\nTime: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}"
            await log_to_channel(client, log_message, parse_mode=enums.ParseMode.HTML)
        else:
            try:
                if await is_group_admin(client, chat.id, bot_info.id):
                    group_start_message = f"Hello! Main <b>{bot_info.first_name}</b> hun, aapka group moderation bot. Main aapke group ko saaf suthra rakhne mein madad karunga."
                    group_keyboard = [[InlineKeyboardButton("➕ Add Me To Your Group", url=add_to_group_url)], [InlineKeyboardButton("🔧 Bot Settings", callback_data="show_settings_main_menu")], [InlineKeyboardButton("📢 Update Channel", url="https://t.me/asbhai_bsr")]]
                else:
                    group_start_message = f"Hello! Main <b>{bot_info.first_name}</b> hun. Is group mein moderation ke liye, kripya mujhe <b>admin</b> banayein aur <b>'Delete Messages'</b>, <b>'Restrict Users'</b>, <b>'Post Messages'</b> ki permissions dein."
                    group_keyboard = [[InlineKeyboardButton("➕ Add Me To Your Group", url=add_to_group_url)], [InlineKeyboardButton("📢 Update Channel", url="https://t.me/asbhai_bsr")]]
                reply_markup = InlineKeyboardMarkup(group_keyboard)
                await message.reply_text(text=group_start_message, reply_markup=reply_markup, parse_mode=enums.ParseMode.HTML)
                if db:
                    db.groups.update_one({"chat_id": chat.id}, {"$set": {"title": chat.title, "type": chat.type.value, "last_active": datetime.now()}}, upsert=True)
            except Exception as e:
                logger.error(f"Error handling start in group: {e}")

    @client.on_message(filters.command("help"))
    async def help_handler(client: Client, message: Message):
        chat_id = message.chat.id
        help_text = "<b>🛠️ Bot Commands & Usage</b>\n\n<b>Private Message Commands:</b>\n`/lock <@username> <message>` - Message ko lock karein taaki sirf mention kiya gaya user hi dekh sake. (Group mein hi kaam karega)\n`/secretchat <@username> <message>` - Ek secret message bhejein, jo group mein sirf ek pop-up mein dikhega. (Group mein hi kaam karega)\n\n<b>Tic Tac Toe Game:</b>\n`/tictac @user1 @user2` - Do users ke saath Tic Tac Toe game shuru karein. Ek baar mein ek hi game chalega.\n\n<b>BioLink Protector Commands:</b>\n`/free` – whitelist a user (reply or user/id)\n`/unfree` – remove from whitelist\n`/freelist` – list all whitelisted users\n\n<b>General Moderation Commands:</b>\n• <code>/settings</code>: Bot ki settings kholen (Group Admins only).\n• <code>/stats</code>: Bot usage stats dekhein (sirf bot admins ke liye).\n• <code>/broadcast</code>: Sabhi groups mein message bhejein (sirf bot admins ke liye).\n• <code>/addabuse &lt;shabd&gt;</code>: Custom gaali wala shabd filter mein add karein (sirf bot admins ke liye).\n• <code>/checkperms</code>: Group mein bot ki permissions jaanchein (sirf group admins ke liye).\n• <code>/cleartempdata</code>: Bot ka temporary aur bekar data saaf karein (sirf bot admins ke liye).\n\n<b>When someone with a URL in their bio or a link in their message posts, I’ll:</b>\n 1. ⚠️ Warn them\n 2. 🔇 Mute if they exceed limit\n 3. 🔨 Ban if set to ban\n\n<b>Use the inline buttons on warnings to cancel or whitelist</b>"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🗑️ Close", callback_data="close")]])
        await client.send_message(chat_id, help_text, reply_markup=kb, parse_mode=enums.ParseMode.HTML)

    @client.on_message(filters.group & filters.command("lock"))
    async def lock_message_handler(client: Client, message: Message):
        if len(message.command) < 3:
            return await message.reply_text("Kripya user ko mention karein aur message likhein. Upyog: `/lock <@username> <message>`")
        target_mention = message.command[1]
        message_content = " ".join(message.command[2:])
        if not target_mention.startswith('@'):
            return await message.reply_text("Kripya us user ko mention karein jise aap message dikhana chahte hain.")
        if not message_content:
            return await message.reply_text("Kripya lock karne ke liye message bhi likhein.")
        sender_user = message.from_user
        target_user = await client.get_users(target_mention)
        lock_id = f"{message.chat.id}_{sender_user.id}_{target_user.id}_{int(time.time())}"
        LOCKED_MESSAGES[lock_id] = {'text': message_content, 'sender_id': sender_user.id, 'target_id': target_user.id, 'chat_id': message.chat.id}
        await message.delete()
        sender_name = f"{sender_user.first_name}{(' ' + sender_user.last_name) if sender_user.last_name else ''}"
        target_name = f"{target_user.first_name}{(' ' + target_user.last_name) if target_user.last_name else ''}"
        unlock_button = InlineKeyboardMarkup([[InlineKeyboardButton("Show Message", callback_data=f"show_lock_{lock_id}")]])
        await client.send_message(chat_id=message.chat.id, text=f"Hey <a href='tg://user?id={target_user.id}'>{target_name}</a>, aapko is <a href='tg://user?id={sender_user.id}'>{sender_name}</a> ne ek lock message bheja hai. Message dekhne ke liye niche button par click kare.", reply_markup=unlock_button, parse_mode=enums.ParseMode.HTML)

    @client.on_message(filters.group & filters.command("secretchat"))
    async def secret_chat_command(client: Client, message: Message):
        if len(message.command) < 3:
            return await message.reply_text("Kripya user ko mention karein aur message likhein. Upyog: `/secretchat <@username> <message>`")
        target_mention = message.command[1]
        secret_message = " ".join(message.command[2:])
        if not target_mention.startswith('@'):
            return await message.reply_text("Kripya us user ko mention karein jise aap secret message bhejna chahte hain.")
        target_user = await client.get_users(target_mention)
        sender_user = message.from_user
        secret_chat_id = f"{message.chat.id}_{sender_user.id}_{target_user.id}_{int(time.time())}"
        SECRET_CHATS[secret_chat_id] = {'message': secret_message, 'sender_id': sender_user.id, 'target_id': target_user.id, 'chat_id': message.chat.id}
        await message.delete()
        sender_name = f"{sender_user.first_name}{(' ' + sender_user.last_name) if sender_user.last_name else ''}"
        target_name = f"{target_user.first_name}{(' ' + target_user.last_name) if target_user.last_name else ''}"
        notification_text = f"Hey <a href='tg://user?id={target_user.id}'>{target_name}</a>, aapko ek secret message bheja gaya hai.\nIse dekhne ke liye niche button par click karein."
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Show Message", callback_data=f"show_secret_{secret_chat_id}")]])
        await client.send_message(chat_id=message.chat.id, text=notification_text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)

    @client.on_message(filters.group & filters.command("tictac"))
    async def tictac_game_start_command(client: Client, message: Message):
        chat_id = message.chat.id
        if chat_id in TIC_TAC_TOE_GAMES:
            return await message.reply_text("Ek Tic Tac Toe game pehle se hi chal raha hai. Kripya uske khatam hone ka intezaar karein.")
        sender = message.from_user
        if len(message.command) > 1 and message.command[1].startswith('@'):
            mentions = [mention for mention in message.command[1:] if mention.startswith('@')]
            if len(mentions) != 2:
                return await message.reply_text("Game shuru karne ke liye do users ko mention karein.\nUpyog: `/tictac @user1 @user2`")
            user1 = await client.get_users(mentions[0])
            user2 = await client.get_users(mentions[1])
            players = [user1, user2]
            random.shuffle(players)
            board = ["➖"] * 9
            TIC_TAC_TOE_GAMES[chat_id] = {'players': {players[0].id: '❌', players[1].id: '⭕'}, 'player_names': {players[0].id: players[0].first_name, players[1].id: players[1].first_name}, 'board': board, 'current_turn_id': players[0].id, 'message_id': None, 'last_active': datetime.now()}
            async def inactivity_check():
                await asyncio.sleep(300)
                if chat_id in TIC_TAC_TOE_GAMES and (datetime.now() - TIC_TAC_TOE_GAMES[chat_id]['last_active']).total_seconds() >= 300:
                    await end_tictactoe_game(client, chat_id)
            TIC_TAC_TOE_TASK[chat_id] = asyncio.create_task(inactivity_check())
            initial_text = f"**Tic Tac Toe (Zero Katte) Game!**\n\n**Player 1:** {TIC_TAC_TOE_GAMES[chat_id]['player_names'][players[0].id]} (❌)\n**Player 2:** {TIC_TAC_TOE_GAMES[chat_id]['player_names'][players[1].id]} (⭕)\n\n**Current Turn:** {TIC_TAC_TOE_GAMES[chat_id]['player_names'][players[0].id]}"
            sent_message = await message.reply_text(initial_text, reply_markup=get_tictac_keyboard(board), parse_mode=enums.ParseMode.MARKDOWN)
            TIC_TAC_TOE_GAMES[chat_id]['message_id'] = sent_message.id
        else:
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(f"Join Game", callback_data=f"tictac_join_game_{sender.id}")]])
            await message.reply_text(f"<b>Tic Tac Toe Game Start</b>\n\n<a href='tg://user?id={sender.id}'>{sender.first_name}</a> ne ek Tic Tac Toe game shuru kiya hai!\nEk aur player ke join karne ka intezaar hai.", reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)

    @client.on_message(filters.group & filters.command("settings"))
    async def settings_command_handler(client: Client, message: Message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        if not await is_group_admin(client, chat_id, user_id):
            return await message.reply_text("Aap group admin nahi hain, is command ka upyog nahi kar sakte.")
        await show_settings_main_menu(client, message)

    @client.on_message(filters.group & filters.command("free"))
    async def command_free(client: Client, message: Message):
        chat_id, user_id = message.chat.id, message.from_user.id
        if not await is_group_admin(client, chat_id, user_id):
            return await message.reply_text("Aap group admin nahi hain.")
        target = message.reply_to_message.from_user if message.reply_to_message else (await client.get_users(int(message.command[1]) if message.command[1].isdigit() else message.command[1]) if len(message.command) > 1 else None)
        if not target:
            return await client.send_message(chat_id, "<b>Reply or use /free user or id to whitelist someone.</b>", parse_mode=enums.ParseMode.HTML)
        add_whitelist_sync(chat_id, target.id)
        reset_warnings_sync(chat_id, target.id, "biolink")
        reset_warnings_sync(chat_id, target.id, "abuse")
        full_name = f"{target.first_name}{(' ' + target.last_name) if target.last_name else ''}"
        text = f"<b>✅ {full_name} has been added to the whitelist</b>"
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🚫 Unwhitelist", callback_data=f"unwhitelist_{target.id}"), InlineKeyboardButton("🗑️ Close", callback_data="close")]])
        await client.send_message(chat_id, text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)

    @client.on_message(filters.group & filters.command("unfree"))
    async def command_unfree(client: Client, message: Message):
        chat_id, user_id = message.chat.id, message.from_user.id
        if not await is_group_admin(client, chat_id, user_id):
            return await message.reply_text("Aap group admin nahi hain.")
        target = message.reply_to_message.from_user if message.reply_to_message else (await client.get_users(int(message.command[1]) if message.command[1].isdigit() else message.command[1]) if len(message.command) > 1 else None)
        if not target:
            return await client.send_message(chat_id, "<b>Reply or use /unfree user or id to unwhitelist someone.</b>", parse_mode=enums.ParseMode.HTML)
        full_name = f"{target.first_name}{(' ' + target.last_name) if target.last_name else ''}"
        if is_whitelisted_sync(chat_id, target.id):
            remove_whitelist_sync(chat_id, target.id)
            text = f"<b>🚫 {full_name} has been removed from the whitelist</b>"
        else:
            text = f"<b>ℹ️ {full_name} is not whitelisted.</b>"
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Whitelist", callback_data=f"whitelist_{target.id}"), InlineKeyboardButton("🗑️ Close", callback_data="close")]])
        await client.send_message(chat_id, text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)

    @client.on_message(filters.group & filters.command("freelist"))
    async def command_freelist(client: Client, message: Message):
        chat_id, user_id = message.chat.id, message.from_user.id
        if not await is_group_admin(client, chat_id, user_id):
            return await message.reply_text("Aap group admin nahi hain.")
        ids = get_whitelist_sync(chat_id)
        if not ids:
            return await client.send_message(chat_id, "<b>⚠️ No users are whitelisted in this group.</b>", parse_mode=enums.ParseMode.HTML)
        text = "<b>📋 Whitelisted Users:</b>\n\n"
        for i, uid in enumerate(ids, start=1):
            try:
                user = await client.get_users(uid)
                text += f"{i}: {user.first_name} (`{uid}`)\n"
            except:
                text += f"{i}: [User not found] (`{uid}`)\n"
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🗑️ Close", callback_data="close")]])
        await client.send_message(chat_id, text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)

    @client.on_message(filters.command("stats") & filters.user(ADMIN_USER_IDS))
    async def stats(client: Client, message: Message):
        if not is_admin(message.from_user.id): return
        total_groups = db.groups.count_documents({}) if db else 0
        total_users = db.users.count_documents({}) if db else 0
        stats_message = f"📊 <b>Bot Status:</b>\n\n• Total Unique Users (via /start in private chat): {total_users}\n• Total Groups Managed: {total_groups}\n• Uptime: {str(datetime.now() - start_time).split('.')[0]} \n• Last Check: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}"
        await message.reply_text(stats_message, parse_mode=enums.ParseMode.HTML)

    @client.on_message(filters.command("broadcast") & filters.user(ADMIN_USER_IDS) & filters.private)
    async def broadcast_command(client: Client, message: Message):
        if not is_admin(message.from_user.id): return
        await message.reply_text("📢 Broadcast shuru karne ke liye, kripya apna message bhejein:")
        BROADCAST_MESSAGE[message.from_user.id] = "waiting_for_message"
    
    @client.on_message(filters.private & filters.user(ADMIN_USER_IDS) & ~filters.command([]))
    async def handle_broadcast_message(client: Client, message: Message):
        user = message.from_user
        if BROADCAST_MESSAGE.get(user.id) != "waiting_for_message": return
        BROADCAST_MESSAGE[user.id] = message
        keyboard = [[InlineKeyboardButton("✅ Yes, Broadcast Now", callback_data="confirm_broadcast")], [InlineKeyboardButton("❌ Cancel", callback_data="cancel_broadcast")]]
        await message.reply_text("Kya aap is message ko sabhi groups aur users ko bhejna chahte hain?", reply_markup=InlineKeyboardMarkup(keyboard))

    @client.on_message(filters.command("addabuse") & filters.user(ADMIN_USER_IDS))
    async def add_abuse_word(client: Client, message: Message):
        if not is_admin(message.from_user.id): return
        if len(message.command) < 2: return await message.reply_text("Kripya woh shabd dein jise aap add karna chahte hain. Upyog: <code>/addabuse &lt;shabd&gt;</code>", parse_mode=enums.ParseMode.HTML)
        word_to_add = " ".join(message.command[1:]).lower().strip()
        if profanity_filter and await profanity_filter.add_bad_word(word_to_add):
            await message.reply_text(f"✅ Shabd <code>{word_to_add}</code> safaltapoorvak jod diya gaya hai.", parse_mode=enums.ParseMode.HTML)
        else:
            await message.reply_text(f"Shabd <code>{word_to_add}</code> pehle se hi list mein maujood hai.", parse_mode=enums.ParseMode.HTML)

    @client.on_message(filters.command("cleartempdata") & filters.user(ADMIN_USER_IDS))
    async def clear_temp_data(client: Client, message: Message):
        if not is_admin(message.from_user.id): return
        status_msg = await message.reply_text("🧹 Safai shuru ho rahi hai... Kripya intezaar karein.")
        in_memory_cleared = {"Tic Tac Toe Games": len(TIC_TAC_TOE_GAMES), "Locked Messages": len(LOCKED_MESSAGES), "Secret Chats": len(SECRET_CHATS)}
        TIC_TAC_TOE_GAMES.clear()
        LOCKED_MESSAGES.clear()
        SECRET_CHATS.clear()
        report_text = "<b>📊 Safai Report</b>\n\n<b>In-Memory Data Cleared:</b>\n"
        for key, value in in_memory_cleared.items():
            if value > 0: report_text += f"• {key}: {value} entries\n"
        await status_msg.edit_text(report_text, parse_mode=enums.ParseMode.HTML)
        if db:
            await status_msg.edit_text("🧠 In-memory data saaf ho gaya hai. Ab database check kiya jaa raha hai...")
            inactive_groups, total_groups = 0, 0
            group_ids = [g["chat_id"] for g in db.groups.find({}, {"chat_id": 1})]
            total_groups = len(group_ids)
            for i, chat_id in enumerate(group_ids):
                if i % 20 == 0: await status_msg.edit_text(f"🔍 Database check ho raha hai... [{i}/{total_groups}]")
                try:
                    await client.get_chat(chat_id)
                    await asyncio.sleep(0.1)
                except (Forbidden, BadRequest, ChatAdminRequired, ValueError):
                    db.groups.delete_one({"chat_id": chat_id})
                    db.settings.delete_one({"chat_id": chat_id})
                    db.warn_settings.delete_one({"chat_id": chat_id})
                    db.whitelist.delete_many({"chat_id": chat_id})
                    db.warnings.delete_many({"chat_id": chat_id})
                    inactive_groups += 1
            report_text += "\n<b>Database Data Cleared:</b>\n"
            report_text += f"• Kul groups check kiye gaye: {total_groups}\n"
            report_text += f"• Inactive groups ka data hataya gaya: {inactive_groups}\n"
        report_text += "\n\n✅ Safai poori hui!"
        await status_msg.edit_text(report_text, parse_mode=enums.ParseMode.HTML)

    @client.on_message(filters.new_chat_members)
    async def welcome_new_member(client: Client, message: Message):
        new_members = message.new_chat_members
        chat = message.chat
        bot_info = await client.get_me()
        for member in new_members:
            if member.id == bot_info.id:
                log_message = f"<b>🤖 Bot Joined Group:</b>\nGroup Name: <code>{chat.title}</code>\nGroup ID: <code>{chat.id}</code>\nMembers: {await client.get_chat_members_count(chat.id)}\nAdded by: {message.from_user.first_name} (`{message.from_user.id}`)\nTime: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}"
                await log_to_channel(client, log_message, parse_mode=enums.ParseMode.HTML)
                if db:
                    db.groups.update_one({"chat_id": chat.id}, {"$set": {"title": chat.title, "type": chat.type.value, "last_active": datetime.now()}}, upsert=True)
                if await is_group_admin(client, chat.id, bot_info.id):
                    welcome_text = f"Hello! Main <b>{bot_info.first_name}</b> hun, aur ab main is group mein moderation karunga.\nKripya सुनिश्चित karein ki mere paas <b>'Delete Messages'</b>, <b>'Restrict Users'</b> aur <b>'Post Messages'</b> ki admin permissions hain."
                    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔧 Bot Settings", callback_data="show_settings_main_menu")]])
                    await message.reply_text(welcome_text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)
                else:
                    await message.reply_text(f"Hello! Main <b>{bot_info.first_name}</b> hun. Is group mein moderation ke liye, kripya mujhe <b>admin</b> banayein aur <b>'Delete Messages'</b>, <b>'Restrict Users'</b>, <b>'Post Messages'</b> ki permissions dein.", parse_mode=enums.ParseMode.HTML)
            else:
                log_message = f"<b>🆕 New Member Joined:</b>\nGroup: <code>{chat.title}</code>\nGroup ID: <code>{chat.id}</code>\nUser: {member.first_name} (`{member.id}`)\nUsername: @{member.username if member.username else 'N/A'}\nTime: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}"
                await log_to_channel(client, log_message, parse_mode=enums.ParseMode.HTML)
                if not await is_group_admin(client, chat.id, member.id) and not is_whitelisted_sync(chat.id, member.id):
                    user_profile = await client.get_chat(member.id)
                    bio = user_profile.bio or ""
                    settings = get_group_settings(chat.id)
                    if settings.get("delete_biolink", True) and URL_PATTERN.search(bio):
                        warn_limit, punishment = get_warn_settings(chat.id, "biolink")
                        count = get_warnings_sync(member.id, chat.id, "biolink") + 1
                        case_type = "punished" if count >= warn_limit else "warn"
                        await handle_incident(client, db, chat.id, member, "bio-link", message, case_type, category="biolink")

    @client.on_message(filters.left_chat_member)
    async def left_member_handler(client: Client, message: Message):
        left_member = message.left_chat_member
        bot_info = await client.get_me()
        chat = message.chat
        if left_member and left_member.id == bot_info.id:
            log_message = f"<b>❌ Bot Left Group:</b>\nGroup Name: <code>{chat.title}</code>\nGroup ID: <code>{chat.id}</code>\nRemoved by: {message.from_user.first_name} (`{message.from_user.id}`)\nTime: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}"
            await log_to_channel(client, log_message, parse_mode=enums.ParseMode.HTML)
        else:
            log_message = f"<b>➡️ Member Left:</b>\nGroup: <code>{chat.title}</code>\nGroup ID: <code>{chat.id}</code>\nUser: {left_member.first_name} (`{left_member.id}`)\nUsername: @{left_member.username if left_member.username else 'N/A'}\nTime: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}"
            await log_to_channel(client, log_message, parse_mode=enums.ParseMode.HTML)

    @client.on_message(filters.group & filters.text & ~filters.via_bot)
    async def handle_all_messages(client: Client, message: Message):
        user = message.from_user
        chat = message.chat
        if not user or await is_group_admin(client, chat.id, user.id) or is_whitelisted_sync(chat.id, user.id):
            return
        settings = get_group_settings(chat.id)
        if settings.get("delete_abuse", True) and profanity_filter and profanity_filter.contains_profanity(message.text):
            warn_limit, punishment = get_warn_settings(chat.id, "abuse")
            count = get_warnings_sync(user.id, chat.id, "abuse") + 1
            case_type = "punished" if count >= warn_limit else "warn"
            return await handle_incident(client, db, chat.id, user, "Abusive word", message, case_type, category="abuse")
        if settings.get("delete_links_usernames", True) and URL_PATTERN.search(message.text):
            return await handle_incident(client, db, chat.id, user, "Link or Username in Message", message, "link_or_username")
        if settings.get("delete_biolink", True):
            user_profile = await client.get_chat(user.id)
            user_bio = user_profile.bio or ""
            if URL_PATTERN.search(user_bio):
                warn_limit, punishment = get_warn_settings(chat.id, "biolink")
                count = get_warnings_sync(user.id, chat.id, "biolink") + 1
                case_type = "punished" if count >= warn_limit else "warn"
                return await handle_incident(client, db, chat.id, user, "bio-link", message, case_type, category="biolink")
            
    @client.on_edited_message(filters.text & filters.group & ~filters.via_bot)
    async def handle_edited_messages(client: Client, edited_message: Message):
        if not edited_message or not edited_message.text or not edited_message.edit_date: return
        user = edited_message.from_user
        chat = edited_message.chat
        if not user or await is_group_admin(client, chat.id, user.id) or is_whitelisted_sync(chat.id, user.id): return
        settings = get_group_settings(chat.id)
        if settings.get("delete_edited", True):
            await handle_incident(client, db, chat.id, user, "Edited message deleted", edited_message, "edited_message_deleted")

    async def show_settings_main_menu(client, message):
        chat_id = message.message.chat.id if isinstance(message, CallbackQuery) else message.chat.id
        settings_text = "⚙️ <b>Bot Settings Menu:</b>\n\nYahan aap group moderation features ko configure kar sakte hain."
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ On/Off Settings", callback_data="show_onoff_settings")],
            [InlineKeyboardButton("📋 Warn & Punishment Settings", callback_data="show_warn_punishment_settings")],
            [InlineKeyboardButton("📝 Whitelist List", callback_data="freelist_settings")],
            [InlineKeyboardButton("⏱️ Notification Delete Time", callback_data="show_notification_delete_time_menu")],
            [InlineKeyboardButton("🕹️ Game Settings", callback_data="show_game_settings")],
            [InlineKeyboardButton("🗑️ Close", callback_data="close")]
        ])
        if isinstance(message, CallbackQuery):
            await message.message.edit_text(settings_text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)
        else:
            await message.reply_text(settings_text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)
            
    async def show_on_off_settings(client, message):
        chat_id = message.message.chat.id if isinstance(message, CallbackQuery) else message.chat.id
        settings = get_group_settings(chat_id)
        biolink_status = "✅ On" if settings.get("delete_biolink", True) else "❌ Off"
        abuse_status = "✅ On" if settings.get("delete_abuse", True) else "❌ Off"
        edited_status = "✅ On" if settings.get("delete_edited", True) else "❌ Off"
        links_usernames_status = "✅ On" if settings.get("delete_links_usernames", True) else "❌ Off" 
        settings_text = "⚙️ <b>On/Off Settings:</b>\n\nYahan aap group moderation features ko chalu/band kar sakte hain."
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"🚨 Bio-Link Detected - {biolink_status}", callback_data="toggle_delete_biolink")],
            [InlineKeyboardButton(f"🚨 Abuse Detected - {abuse_status}", callback_data="toggle_delete_abuse")],
            [InlineKeyboardButton(f"📝 Edited Message Deleted - {edited_status}", callback_data="toggle_delete_edited")],
            [InlineKeyboardButton(f"🔗 Link/Username Removed - {links_usernames_status}", callback_data="toggle_delete_links_usernames")],
            [InlineKeyboardButton("⬅️ Back", callback_data="back_to_settings_main_menu")]
        ])
        if isinstance(message, CallbackQuery): await message.message.edit_text(settings_text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)
        else: await message.reply_text(settings_text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)

    async def show_warn_punishment_settings(client, message):
        chat_id = message.message.chat.id if isinstance(message, CallbackQuery) else message.chat.id
        biolink_limit, biolink_punishment = get_warn_settings(chat_id, "biolink")
        abuse_limit, abuse_punishment = get_warn_settings(chat_id, "abuse")
        settings_text = "<b>📋 Warn & Punishment Settings:</b>\n\nYahan aap warning limit aur punishment set kar sakte hain."
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"🚨 Bio-Link ({biolink_limit} warns)", callback_data="config_biolink")],
            [InlineKeyboardButton(f"Punish: {biolink_punishment.capitalize()}", callback_data="toggle_punishment_biolink")],
            [InlineKeyboardButton(f"🚨 Abuse ({abuse_limit} warns)", callback_data="config_abuse")],
            [InlineKeyboardButton(f"Punish: {abuse_punishment.capitalize()}", callback_data="toggle_punishment_abuse")],
            [InlineKeyboardButton("⬅️ Back", callback_data="back_to_settings_main_menu")]
        ])
        if isinstance(message, CallbackQuery): await message.message.edit_text(settings_text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)
        else: await message.reply_text(settings_text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)

    async def show_notification_delete_time_menu(client, message):
        chat_id = message.message.chat.id if isinstance(message, CallbackQuery) else message.chat.id
        delete_time = get_notification_delete_time(chat_id)
        status_text = f"<b>⏱️ Notification Delete Time:</b>\n\nChoose how long warning/punishment notifications will stay before being automatically deleted.\n\n<b>Current setting:</b> {'Off' if delete_time == 0 else f'{delete_time} min'}"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(f"Off {'✅' if delete_time == 0 else ''}", callback_data="set_notif_time_0")],
            [InlineKeyboardButton(f"1 min {'✅' if delete_time == 1 else ''}", callback_data="set_notif_time_1"), InlineKeyboardButton(f"5 min {'✅' if delete_time == 5 else ''}", callback_data="set_notif_time_5")],
            [InlineKeyboardButton(f"10 min {'✅' if delete_time == 10 else ''}", callback_data="set_notif_time_10"), InlineKeyboardButton(f"1 hour {'✅' if delete_time == 60 else ''}", callback_data="set_notif_time_60")],
            [InlineKeyboardButton("⬅️ Back", callback_data="back_to_settings_main_menu")]
        ])
        if isinstance(message, CallbackQuery): await message.message.edit_text(status_text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)
        else: await message.reply_text(status_text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)

    async def show_game_settings(client, message):
        chat_id = message.message.chat.id if isinstance(message, CallbackQuery) else message.chat.id
        game_status_text = "<b>🕹️ Game Settings:</b>\n\nYahan aap games se related settings dekh sakte hain."
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Tic Tac Toe Game Start", callback_data="start_tictactoe_from_settings")], [InlineKeyboardButton("⬅️ Back", callback_data="back_to_settings_main_menu")]])
        if isinstance(message, CallbackQuery): await message.message.edit_text(game_status_text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)
        else: await message.reply_text(game_status_text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)

    @client.on_message(filters.command("checkperms") & filters.group)
    async def check_permissions(client: Client, message: Message):
        chat = message.chat
        bot_id = client.me.id
        if not await is_group_admin(client, chat.id, message.from_user.id):
            return await message.reply_text("Aap group admin nahi hain, isliye aap yeh command ka upyog nahi kar sakte.")
        try:
            bot_member = await client.get_chat_member(chat.id, bot_id)
            if bot_member.status != enums.ChatMemberStatus.ADMINISTRATOR:
                return await message.reply_text("Bot is not an admin in this group. Please make the bot an admin.")
            perms = bot_member.privileges
            message_text = f"<b>{chat.title} mein bot ki anumatiyan (Permissions):</b>\n\n<b>Can Delete Messages:</b> {'✅ Yes' if perms.can_delete_messages else '❌ No'}\n<b>Can Restrict Members:</b> {'✅ Yes' if perms.can_restrict_members else '❌ No'}\n<b>Can Pin Messages:</b> {'✅ Yes' if perms.can_pin_messages else '❌ No'}\n<b>Can Post Messages:</b> {'✅ Yes' if perms.can_post_messages else '❌ No'}"
            await message.reply_text(message_text, parse_mode=enums.ParseMode.HTML)
        except Exception as e:
            logger.error(f"Anumatiyan jaanchte samay ek error hui: {e}")
            await message.reply_text(f"Anumatiyan jaanchte samay ek error hui: {e}")
