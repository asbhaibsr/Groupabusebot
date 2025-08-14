<!-- README.md – FULL SINGLE FILE -->
<!-- Select ALL lines and paste into repo root -->

# 🎭 AS-FILTER-BOT – Ultimate Telegram Group Moderator

> Smart Auto-Moderation • Tic Tac Toe • Tagging • Whitelist • Flask Health • One-Click Deploy

---

## ⚡️ One-Click Deploy

| Platform | 1-Click |
|----------|---------|
| **Koyeb** | [![Deploy to Koyeb](https://www.koyeb.com/static/images/deploy/button.svg)](https://app.koyeb.com/deploy?type=docker&image=docker.io/library/python:3.11&env[PORT]=8000&env[MONGO_DB_URI]=&env[API_ID]=&env[API_HASH]=&env[TELEGRAM_BOT_TOKEN]=&name=as-filter-bot&run_command=python%20main.py) |
| **Railway** | [![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/template?template=https%3A%2F%2Fgithub.com%2Fyourname%2Fas-filter-bot&envs=MONGO_DB_URI,API_ID,API_HASH,TELEGRAM_BOT_TOKEN&optionalEnvs=LOG_CHANNEL_ID) |

---

## 📜 Quick Start (Copy-Paste Friendly)

1. **Clone & install**
   ```bash
   git clone https://github.com/yourname/as-filter-bot.git
   cd as-filter-bot
   pip install -r requirements.txt
   Environment Variables
Create .env and fill:
Copy
API_ID=123456
API_HASH=abcdef123456...
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
MONGO_DB_URI=mongodb+srv://user:pass@cluster0.x.mongodb.net/?retryWrites=true&w=majority
LOG_CHANNEL_ID=-1002717243409
Tip: bot → @BotFather • API → my.telegram.org
Run
bash
Copy
python main.py
🎯 All Bot Commands (Copy Buttons)
Table
Copy
Action	Command
Start bot	<button onclick="navigator.clipboard.writeText('/start')"> /start
Help	<button onclick="navigator.clipboard.writeText('/help')"> /help
Settings	<button onclick="navigator.clipboard.writeText('/settings')"> /settings
Whitelist user	<button onclick="navigator.clipboard.writeText('/free')"> /free (reply)
Un-whitelist	<button onclick="navigator.clipboard.writeText('/unfree')"> /unfree (reply)
Whitelist list	<button onclick="navigator.clipboard.writeText('/freelist')"> /freelist
Tic Tac Toe	<button onclick="navigator.clipboard.writeText('/tictac @user1 @user2')"> /tictac @user1 @user2
Lock message	<button onclick="navigator.clipboard.writeText('/lock @user secret')"> /lock @user secret
Secret chat	<button onclick="navigator.clipboard.writeText('/secretchat @user hi')"> /secretchat @user hi
Tag all	<button onclick="navigator.clipboard.writeText('/tagall message')"> /tagall message
Tag online	<button onclick="navigator.clipboard.writeText('/onlinetag message')"> /onlinetag message
Tag admins	<button onclick="navigator.clipboard.writeText('/admin message')"> /admin message
Stop tags	<button onclick="navigator.clipboard.writeText('/tagstop')"> /tagstop
Check bot perms	<button onclick="navigator.clipboard.writeText('/checkperms')"> /checkperms
Add abuse word	<button onclick="navigator.clipboard.writeText('/addabuse word')"> /addabuse word
Stats	<button onclick="navigator.clipboard.writeText('/stats')"> /stats
Broadcast	<button onclick="navigator.clipboard.writeText('/broadcast')"> /broadcast
Clean temp data	<button onclick="navigator.clipboard.writeText('/cleartempdata')"> /cleartempdata
🌟 Features List
Table
Copy
#	Feature	Auto / Command	What it does
1	Auto Bio-Link Delete	auto on join/msg	Removes users whose bio has links
2	Abuse Word Filter	/addabuse	Deletes custom slangs + warns
3	Link/Username Filter	auto	Deletes t.me, www, @user
4	Edited Message Nuker	auto	Deletes edits to stop bypass
5	Warn → Mute → Ban	configurable	Limit & punishment via buttons
6	Whitelist System	/free / /unfree	Exclude trusted users
7	Tagging Suite	/tagall /onlinetag /admin /tagstop	Tag everyone / online / admins
8	Tic Tac Toe Game	/tictac	Play zero-katta in group
9	Lock & Secret Chat	/lock / /secretchat	Show msg to only one user
10	Flask Health API	/ (port 8000)	Uptime check for Koyeb/Render
11	Broadcast & Stats	/broadcast /stats	Owner-only tools
12	Cleanup Tool	/cleartempdata	Wipe memory & stale DB rows
📞 Contact & Support
Update Channel → https://t.me/asbhai_bsr
Support Group → https://t.me/askiangelbot
Donation (UPI) → arsadsaifi8272@ibl
Developer → https://t.me/asprmotion
🪪 License
MIT © AS Bhai – fork & modify freely.
<style>
button{background:#1e88e5;color:#fff;border:none;padding:4px 10px;border-radius:4px;cursor:pointer;font-size:13px}
button:hover{background:#1565c0}
</style>
