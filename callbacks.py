import logging
from pyrogram import Client, filters, enums, errors
from pyrogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import MessageNotModified
import asyncio
from datetime import datetime

from utils import is_group_admin, handle_incident, broadcast_to_all
from database import (
    get_group_settings, update_group_setting, get_warn_settings,
    update_warn_settings, get_whitelist_sync, add_whitelist_sync,
    remove_whitelist_sync, reset_warnings_sync, update_notification_delete_time,
    get_notification_delete_time
)
from handlers import show_settings_main_menu, show_on_off_settings, show_warn_punishment_settings, show_notification_delete_time_menu, show_game_settings
from game_logic import TIC_TAC_TOE_GAMES, TIC_TAC_TOE_TASK, check_win, check_draw, get_tictac_keyboard, end_tictactoe_game

logger = logging.getLogger(__name__)

def setup_all_callbacks(client, db, LOCKED_MESSAGES, SECRET_CHATS, TIC_TAC_TOE_GAMES, TIC_TAC_TOE_TASK, BROADCAST_MESSAGE, profanity_filter):

    @client.on_callback_query()
    async def callback_handler(client: Client, query: CallbackQuery):
        data, user_id, chat_id = query.data, query.from_user.id, query.message.chat.id

        if query.message.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP] and data not in ["close", "help_menu", "other_bots", "donate_info", "back_to_main_menu"] and not data.startswith(('show_', 'toggle_', 'config_', 'setwarn_', 'tictac_', 'show_lock_', 'show_secret_', 'freelist_settings', 'toggle_punishment_', 'freelist_show', 'whitelist_', 'unwhitelist_', 'tictac_new_game_starter_','set_notif_time_')):
            if not await is_group_admin(client, chat_id, user_id):
                return await query.answer("❌ Aapke paas is action ko karne ki permission nahi hai. Aap group admin nahi hain.", show_alert=True)
        else:
            await query.answer()

        if data == "close":
            try: await query.message.delete()
            except MessageNotModified: pass
            return

        if data == "confirm_broadcast" and user_id in BROADCAST_MESSAGE:
            broadcast_message = BROADCAST_MESSAGE[user_id]
            if broadcast_message != "waiting_for_message":
                await query.message.edit_text("📢 Broadcast shuru ho raha hai...", reply_markup=None)
                await broadcast_to_all(client, db, broadcast_message)
            else: await query.answer("Invalid broadcast state. Please try /broadcast again.", show_alert=True)
            return

        if data == "cancel_broadcast" and user_id in BROADCAST_MESSAGE:
            BROADCAST_MESSAGE.pop(user_id, None)
            await query.message.edit_text("❌ Broadcast cancel kar diya gaya hai.")
            return

        if data == "help_menu":
            help_text = "<b>🛠️ Bot Commands & Usage</b>\n\n<b>Private Message Commands:</b>\n`/lock <@username> <message>` - Message ko lock karein taaki sirf mention kiya gaya user hi dekh sake. (Group mein hi kaam karega)\n`/secretchat <@username> <message>` - Ek secret message bhejein, jo group mein sirf ek pop-up mein dikhega. (Group mein hi kaam karega)\n\n<b>Tic Tac Toe Game:</b>\n`/tictac @user1 @user2` - Do users ke saath Tic Tac Toe game shuru karein. Ek baar mein ek hi game chalega.\n\n<b>BioLink Protector Commands:</b>\n`/free` – whitelist a user (reply or user/id)\n`/unfree` – remove from whitelist\n`/freelist` – list all whitelisted users\n\n<b>General Moderation Commands:</b>\n• <code>/settings</code>: Bot ki settings kholen (Group Admins only).\n• <code>/stats</code>: Bot usage stats dekhein (sirf bot admins ke liye).\n• <code>/broadcast</code>: Sabhi groups mein message bhejein (sirf bot admins ke liye).\n• <code>/addabuse &lt;shabd&gt;</code>: Custom gaali wala shabd filter mein add karein (sirf bot admins ke liye).\n• <code>/checkperms</code>: Group mein bot ki permissions jaanchein (sirf group admins ke liye).\n• <code>/cleartempdata</code>: Bot ka temporary aur bekar data saaf karein (sirf bot admins ke liye).\n\n<b>When someone with a URL in their bio or a link in their message posts, I’ll:</b>\n 1. ⚠️ Warn them\n 2. 🔇 Mute if they exceed limit\n 3. 🔨 Ban if set to ban\n\n<b>Use the inline buttons on warnings to cancel or whitelist</b>"
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="back_to_main_menu")], [InlineKeyboardButton("🗑️ Close", callback_data="close")]])
            await query.message.edit_text(help_text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)
            return

        if data == "other_bots":
            other_bots_text = "🤖 <b>Mere Dusre Bots:</b>\n\nMovies, webseries, anime, etc. dekhne ke liye sabse best bot: \n➡️ @asfilter_bot\n\nGroup par chat ke liye bot chahiye jo aapke group par aadmi ki tarah baatein kare, logon ka manoranjan kare, aur isme kai commands aur tagde features bhi hain. Isme har mahine paise jeetne ka leaderboard bhi hai: \n➡️ @askiangelbot"
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="back_to_main_menu")], [InlineKeyboardButton("🗑️ Close", callback_data="close")]])
            await query.message.edit_text(other_bots_text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML, disable_web_page_preview=True)
            return
            
        if data == "donate_info":
            donate_text = "💖 <b>Humein Support Karein!</b>\n\nAgar aapko mera kaam pasand aaya hai, toh aap humein support kar sakte hain. Aapka chhota sa daan bhi bahut madad karega!\n\n<b>UPI ID:</b> <code>arsadsaifi8272@ibl</code>\n\n<b>Thank you for your support!</b>"
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="back_to_main_menu")], [InlineKeyboardButton("🗑️ Close", callback_data="close")]])
            await query.message.edit_text(donate_text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)
            return

        if data == "back_to_main_menu":
            bot_info = await client.get_me()
            bot_name, bot_username = bot_info.first_name, bot_info.username
            add_to_group_url = f"https://t.me/{bot_username}?startgroup=true"
            welcome_message = f"👋 <b>Namaste {query.from_user.first_name}!</b>\n\nMai <b>{bot_name}</b> hun, aapka group moderator bot. Mai aapke groups ko saaf suthra rakhne mein madad karta hun."
            keyboard = [[InlineKeyboardButton("➕ Add Me To Your Group", url=add_to_group_url)], [InlineKeyboardButton("❓ Help", callback_data="help_menu"), InlineKeyboardButton("🤖 Other Bots", callback_data="other_bots")], [InlineKeyboardButton("📢 Update Channel", url="https://t.me/asbhai_bsr"), InlineKeyboardButton("💖 Donate", callback_data="donate_info")], [InlineKeyboardButton("📈 Promotion", url="https://t.me/asprmotion")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.message.edit_text(text=welcome_message, reply_markup=reply_markup, parse_mode=enums.ParseMode.HTML, disable_web_page_preview=True)
            return

        if data == "show_settings_main_menu": await show_settings_main_menu(client, query)
        if data == "show_onoff_settings": await show_on_off_settings(client, query)
        if data == "show_warn_punishment_settings": await show_warn_punishment_settings(client, query)
        if data == "show_game_settings": await show_game_settings(client, query)
        if data == "show_notification_delete_time_menu": await show_notification_delete_time_menu(client, query)
        if data.startswith("set_notif_time_"):
            update_notification_delete_time(chat_id, int(data.split('_')[-1]))
            await show_notification_delete_time_menu(client, query)
            return
        if data == "freelist_settings":
            ids = get_whitelist_sync(chat_id)
            text = "<b>⚠️ No users are whitelisted in this group.</b>" if not ids else "<b>📋 Whitelisted Users:</b>\n\n" + "".join([f"{i}: <a href='tg://user?id={uid}'>{user.first_name}</a> [`{uid}`]\n" if (user:=await client.get_users(uid)) else f"{i}: [User not found] [`{uid}`]\n" for i, uid in enumerate(ids, 1)])
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="show_settings_main_menu")], [InlineKeyboardButton("🗑️ Close", callback_data="close")]])
            await query.message.edit_text(text, reply_markup=keyboard, parse_mode=enums.ParseMode.HTML, disable_web_page_preview=True)
            return
        if data.startswith("toggle_"):
            setting_key = data.split('toggle_', 1)[1]
            settings = get_group_settings(chat_id)
            update_group_setting(chat_id, setting_key, not settings.get(setting_key, True))
            await show_on_off_settings(client, query)
            return
        if data.startswith("config_"):
            category = data.split('_')[1]
            warn_limit, punishment = get_warn_settings(chat_id, category)
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"Set Warn Limit ({warn_limit})", callback_data=f"set_warn_limit_{category}")], [InlineKeyboardButton(f"Punish: Mute {'✅' if punishment == 'mute' else ''}", callback_data=f"set_punishment_mute_{category}"), InlineKeyboardButton(f"Punish: Ban {'✅' if punishment == 'ban' else ''}", callback_data=f"set_punishment_ban_{category}")], [InlineKeyboardButton("⬅️ Back", callback_data="show_warn_punishment_settings")]])
            await query.message.edit_text(f"<b>⚙️ Configure {category.capitalize()} Warnings:</b>", reply_markup=kb, parse_mode=enums.ParseMode.HTML)
            return
        if data.startswith("set_warn_limit_"):
            category = data.split('_')[-1]
            warn_limit, _ = get_warn_settings(chat_id, category)
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"3 {'✅' if warn_limit == 3 else ''}", callback_data=f"set_limit_{category}_3"), InlineKeyboardButton(f"4 {'✅' if warn_limit == 4 else ''}", callback_data=f"set_limit_{category}_4"), InlineKeyboardButton(f"5 {'✅' if warn_limit == 5 else ''}", callback_data=f"set_limit_{category}_5")], [InlineKeyboardButton("⬅️ Back", callback_data=f"config_{category}")]])
            await query.message.edit_text(f"<b>{category.capitalize()} Warn Limit:</b>\nSelect the number of warnings before a user is punished.", reply_markup=kb, parse_mode=enums.ParseMode.HTML)
            return
        if data.startswith("set_limit_"):
            category, limit = data.split('_')[2], int(data.split('_')[3])
            update_warn_settings(chat_id, category, limit=limit)
            await query.message.edit_text(f"✅ {category.capitalize()} warning limit set to {limit}.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data=f"config_{category}")]]) , parse_mode=enums.ParseMode.HTML)
            return
        if data.startswith("set_punishment_"):
            punishment, category = data.split('_')[2], data.split('_')[3]
            update_warn_settings(chat_id, category, punishment=punishment)
            await query.message.edit_text(f"✅ {category.capitalize()} punishment set to {punishment.capitalize()}.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data=f"config_{category}")]]) , parse_mode=enums.ParseMode.HTML)
            return
        if data == "back_to_settings_main_menu":
            await show_settings_main_menu(client, query)
            return
        if data == "start_tictactoe_from_settings":
            if chat_id in TIC_TAC_TOE_GAMES: return await query.answer("Ek game pehle se hi chal raha hai.", show_alert=True)
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(f"Join Game", callback_data=f"tictac_join_game_{user_id}")]])
            await query.message.edit_text(f"<b>Tic Tac Toe Game Start</b>\n\n<a href='tg://user?id={user_id}'>{query.from_user.first_name}</a> ne ek Tic Tac Toe game shuru kiya hai!\nEk aur player ke join karne ka intezaar hai.", reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)
            return
        if data.startswith("show_lock_"):
            lock_id = data.split('_', 2)[2]
            locked_message_data = LOCKED_MESSAGES.get(lock_id)
            if not locked_message_data: return await query.answer("This message has been unlocked or is no longer available.", show_alert=True)
            if user_id != locked_message_data['target_id']: return await query.answer("This message is not for you.", show_alert=True)
            sender_name = (await client.get_users(locked_message_data['sender_id'])).first_name
            target_name = query.from_user.first_name
            await query.message.edit_text(f"**🔓 Unlocked Message:**\n\n**From:** {sender_name}\n**To:** {target_name}\n\n**Message:**\n{locked_message_data['text']}\n\nThis message will self-destruct in 1 minute.")
            LOCKED_MESSAGES.pop(lock_id)
            await asyncio.sleep(60)
            try: await query.message.delete()
            except Exception: pass
            return
        if data.startswith("show_secret_"):
            secret_chat_id = data.split('_', 2)[2]
            secret_chat_data = SECRET_CHATS.get(secret_chat_id)
            if not secret_chat_data: return await query.answer("This secret message is no longer available.", show_alert=True)
            if user_id != secret_chat_data['target_id']: return await query.answer("This secret message is not for you.", show_alert=True)
            sender_name = (await client.get_users(secret_chat_data['sender_id'])).first_name
            secret_message_text = f"From: {sender_name}\n\nMessage: {secret_chat_data['message']}"
            await query.answer(secret_message_text, show_alert=True)
            SECRET_CHATS.pop(secret_chat_id)
            return
        if data.startswith("tictac_"):
            game_state = TIC_TAC_TOE_GAMES.get(chat_id)
            if not game_state:
                user = query.from_user
                keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Join Game", callback_data=f"tictac_join_game_{user.id}")]])
                await client.send_message(chat_id, f"**Yeh game abhi active nahi hai.**\n\n<a href='tg://user?id={user.id}'>{user.first_name}</a> ne ek naya game shuru kiya hai!\nEk aur player ke join karne ka intezaar hai.", reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)
                return await query.answer("Yeh game abhi active nahi hai, naya game shuru kiya ja raha hai.", show_alert=True)
            if user_id not in game_state['players']:
                return await query.answer("Aap is game ke player nahi hain.", show_alert=True)
            if user_id != game_state['current_turn_id']:
                return await query.answer(f"It's not your turn, {query.from_user.first_name}!", show_alert=True)
            button_index_str = data.split('_')[1]
            if button_index_str == 'noop': return await query.answer("Game khatam ho chuka hai, kripya naya game shuru karein.", show_alert=True)
            button_index = int(button_index_str)
            board = game_state['board']
            if board[button_index] != "➖": return await query.answer("Yeh jagah pehle se hi bhari hui hai.", show_alert=True)
            player_mark = game_state['players'][user_id]
            board[button_index] = player_mark
            game_state['last_active'] = datetime.now()
            if chat_id in TIC_TAC_TOE_TASK: TIC_TAC_TOE_TASK[chat_id].cancel()
            async def inactivity_check():
                await asyncio.sleep(300)
                if chat_id in TIC_TAC_TOE_GAMES and (datetime.now() - TIC_TAC_TOE_GAMES[chat_id]['last_active']).total_seconds() >= 300:
                    await end_tictactoe_game(client, chat_id)
            TIC_TAC_TOE_TASK[chat_id] = asyncio.create_task(inactivity_check())
            winner = check_win(board)
            if winner:
                winner_name = game_state['player_names'][user_id]
                final_text = f"🎉 **{winner_name} wins the game!** 🎉\n\n"
                keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Join New Game", callback_data=f"tictac_new_game_starter_{user_id}")], [InlineKeyboardButton("🗑️ Close", callback_data="close")]])
                await query.message.edit_text(final_text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)
                del TIC_TAC_TOE_GAMES[chat_id]
                return
            if check_draw(board):
                final_text = "🤝 **Game is a draw!** 🤝\n\n"
                keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Join New Game", callback_data=f"tictac_new_game_starter_{user_id}")], [InlineKeyboardButton("🗑️ Close", callback_data="close")]])
                await query.message.edit_text(final_text, reply_markup=keyboard, parse_mode=enums.ParseMode.MARKDOWN)
                del TIC_TAC_TOE_GAMES[chat_id]
                return
            other_player_id = [p for p in game_state['players'] if p != user_id][0]
            game_state['current_turn_id'] = other_player_id
            current_player_name = game_state['player_names'][other_player_id]
            updated_text = f"**Tic Tac Toe (Zero Katte) Game!**\n\n**Player 1:** {game_state['player_names'][list(game_state['players'].keys())[0]]} (❌)\n**Player 2:** {game_state['player_names'][list(game_state['players'].keys())[1]]} (⭕)\n\n**Current Turn:** {current_player_name}"
            await query.message.edit_text(updated_text, reply_markup=get_tictac_keyboard(board), parse_mode=enums.ParseMode.MARKDOWN)
            return
        if data.startswith("tictac_join_game_"):
            joiner_id, starter_id = user_id, int(data.split("_")[-1])
            if chat_id in TIC_TAC_TOE_GAMES: return await query.answer("Ek game pehle hi chal raha hai.", show_alert=True)
            if joiner_id == starter_id: return await query.answer("Aap pehle se hi player 1 hain. Kripya kisi aur ko join karne dein.", show_alert=True)
            starter_user, joiner_user = await client.get_users(starter_id), query.from_user
            players = [starter_user, joiner_user]
            random.shuffle(players)
            board = ["➖"] * 9
            TIC_TAC_TOE_GAMES[chat_id] = {'players': {players[0].id: '❌', players[1].id: '⭕'}, 'player_names': {players[0].id: players[0].first_name, players[1].id: players[1].first_name}, 'board': board, 'current_turn_id': players[0].id, 'message_id': query.message.id, 'last_active': datetime.now()}
            async def inactivity_check():
                await asyncio.sleep(300)
                if chat_id in TIC_TAC_TOE_GAMES and (datetime.now() - TIC_TAC_TOE_GAMES[chat_id]['last_active']).total_seconds() >= 300:
                    await end_tictactoe_game(client, chat_id)
            TIC_TAC_TOE_TASK[chat_id] = asyncio.create_task(inactivity_check())
            initial_text = f"**Tic Tac Toe (Zero Katte) Game!**\n\n**Player 1:** {TIC_TAC_TOE_GAMES[chat_id]['player_names'][players[0].id]} (❌)\n**Player 2:** {TIC_TAC_TOE_GAMES[chat_id]['player_names'][players[1].id]} (⭕)\n\n**Current Turn:** {TIC_TAC_TOE_GAMES[chat_id]['player_names'][players[0].id]}"
            await query.message.edit_text(initial_text, reply_markup=get_tictac_keyboard(board), parse_mode=enums.ParseMode.MARKDOWN)
            return
        if data.startswith("tictac_new_game_starter_"):
            starter_id = int(data.split('_')[-1])
            if chat_id in TIC_TAC_TOE_GAMES: return await query.answer("Ek game pehle hi chal raha hai.", show_alert=True)
            starter_user = await client.get_users(starter_id)
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Join Game", callback_data=f"tictac_join_game_{starter_id}")]])
            await client.send_message(chat_id, f"<b>Tic Tac Toe Game Start</b>\n\n<a href='tg://user?id={starter_user.id}'>{starter_user.first_name}</a> ne ek Tic Tac Toe game shuru kiya hai!\nEk aur player ke join karne ka intezaar hai.", reply_markup=keyboard, parse_mode=enums.ParseMode.HTML)
            await query.message.delete()
            return
        if data.startswith("unmute_"):
            target_id, group_chat_id = int(data.split('_')[1]), int(data.split('_')[2])
            try:
                await client.restrict_chat_member(group_chat_id, target_id, ChatPermissions(can_send_messages=True))
                reset_warnings_sync(group_chat_id, target_id, "abuse")
                reset_warnings_sync(group_chat_id, target_id, "biolink")
                user_obj = await client.get_chat_member(group_chat_id, target_id)
                user_mention = f"<a href='tg://user?id={target_id}'>{user_obj.user.first_name}</a>"
                kb = InlineKeyboardMarkup([[InlineKeyboardButton("Whitelist ✅", callback_data=f"whitelist_{target_id}"), InlineKeyboardButton("🗑️ Close", callback_data="close")]])
                await query.message.edit_text(f"<b>✅ {user_mention} unmuted!</b>", reply_markup=kb, parse_mode=enums.ParseMode.HTML)
            except errors.ChatAdminRequired: await query.message.edit_text("<b>I don't have permission to unmute users.</b>", parse_mode=enums.ParseMode.HTML)
            return
        if data.startswith("cancel_warn_"):
            target_id = int(data.split("_")[-1])
            reset_warnings_sync(chat_id, target_id, "biolink")
            reset_warnings_sync(chat_id, target_id, "abuse")
            user_obj = await client.get_chat_member(chat_id, target_id)
            full_name = f"{user_obj.user.first_name}{(' ' + user_obj.user.last_name) if user_obj.user.last_name else ''}"
            mention = f"<a href='tg://user?id={target_id}'>{full_name}</a>"
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("Whitelist✅", callback_data=f"whitelist_{target_id}"), InlineKeyboardButton("🗑️ Close", callback_data="close")]])
            await query.message.edit_text(f"<b>✅ {mention} (`{target_id}`) has no more warnings!</b>", reply_markup=kb, parse_mode=enums.ParseMode.HTML)
            return
        if data.startswith("whitelist_"):
            target_id = int(data.split("_")[1])
            add_whitelist_sync(chat_id, target_id)
            reset_warnings_sync(chat_id, target_id, "biolink")
            reset_warnings_sync(chat_id, target_id, "abuse")
            user = await client.get_chat_member(chat_id, target_id)
            full_name = f"{user.first_name}{(' ' + user.last_name) if user.last_name else ''}"
            mention = f"<a href='tg://user?id={target_id}'>{full_name}</a>"
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("🚫 Unwhitelist", callback_data=f"unwhitelist_{target_id}"), InlineKeyboardButton("🗑️ Close", callback_data="close")]])
            await query.message.edit_text(f"<b>✅ {mention} has been whitelisted!</b>", reply_markup=kb, parse_mode=enums.ParseMode.HTML)
            return
        if data.startswith("unwhitelist_"):
            target_id = int(data.split("_")[1])
            remove_whitelist_sync(chat_id, target_id)
            user = await client.get_chat_member(chat_id, target_id)
            full_name = f"{user.first_name}{(' ' + user.last_name) if user.last_name else ''}"
            mention = f"<a href='tg://user?id={target_id}'>{full_name}</a>"
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("Whitelist✅", callback_data=f"whitelist_{target_id}"), InlineKeyboardButton("🗑️ Close", callback_data="close")]])
            await query.message.edit_text(f"<b>❌ {mention} has been removed from whitelist.</b>", reply_markup=kb, parse_mode=enums.ParseMode.HTML)
            return
