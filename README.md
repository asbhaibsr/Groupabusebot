<p align="center">
  <img src="https://readme-typing-svg.demolab.com?font=Fira+Code&size=28&duration=2500&pause=1200&center=true&vCenter=true&width=435&lines=🚫+Group+Abuse+Filter+Bot+🚫;⚡+Clean+Telegram+Groups+with+One+Bot!;🛡️+Auto+Remove+Bad+Words;☁️+Deploy+on+Koyeb+in+1+Click!">
</p>

<p align="center">
  <a href="https://t.me/asbhaibsr">
    <img src="https://img.shields.io/badge/👤 Owner-%40asbhaibsr-blue?style=for-the-badge&logo=telegram" />
  </a>
  <a href="https://t.me/asbhai_bsr">
    <img src="https://img.shields.io/badge/📢 Updates-%40asbhai__bsr-orange?style=for-the-badge&logo=telegram" />
  </a>
</p>

---

## ✨ Features

- ✅ Auto-detect and delete abusive messages
- 🔐 Real-time monitoring of group chats
- 🧠 Works with MongoDB + Logging system
- 🔁 Deployable on **Koyeb**, **Render**, etc.
- 👑 Admin-only commands for control and moderation

---

## 🚀 Deploy to Koyeb

1. Fork this repo
2. Go to [Koyeb Dashboard](https://app.koyeb.com/)
3. Create New App:
   - Source: GitHub (your fork)
   - Buildpack: `python`
4. Set environment variables:
   ```
   TELEGRAM_BOT_TOKEN = <your_bot_token>
   MONGO_DB_URI = <your_mongo_connection_uri>
   GROUP_ADMIN_USERNAME = yourgroupadmin
   ```
5. Click **Deploy** 🎉

---

## 🛠 Manual Setup

```bash
git clone https://github.com/yourusername/Groupabusebot.git
cd Groupabusebot
pip install -r requirements.txt
```

Edit `main.py` and set your tokens if not using `.env`.

```bash
python main.py
```

---

## 💬 Telegram Bot Commands

> All commands below are available to **admin users only**:

```
/start              - Check bot is online
/stats             - Get usage stats
/broadcast <msg>   - Send message to all users
/addabuse <word>   - Add abusive word to filter
/delabuse <word>   - Remove word from filter
/listabuse         - Show blocked words
/help              - Show help message
```

---

## 📦 Logs and Usage Flow

| Type      | Where it goes | Description |
|-----------|---------------|-------------|
| **Logs**  | `LOG_CHANNEL_ID` | Bot logs (user joins, commands) |
| **Cases** | `CASE_CHANNEL_ID` | Any abusive message detected goes here |
| **Warnings** | Group itself | User gets warned + message deleted |
| **Admin Alerts** | Logs & Mention | Admins get pinged in critical events |

🧪 You can change log/case channels from `main.py` or set them via environment variables.

---

## 🧾 File Breakdown

| File | Purpose |
|------|---------|
| `main.py` | Core bot logic |
| `profanity_filter.py` | Bad word filtering |
| `requirements.txt` | Python packages |
| `.env (optional)` | Store your secrets for Koyeb/local |

---

## 🙋‍♂️ Support & Contact

<p align="center">
  <a href="https://t.me/asbhaibsr">
    <img src="https://img.shields.io/badge/👨‍💻 Contact-%40asbhaibsr-blue?style=for-the-badge&logo=telegram" />
  </a>
  <a href="https://t.me/asbhai_bsr">
    <img src="https://img.shields.io/badge/📢 Update+Channel-%40asbhai__bsr-orange?style=for-the-badge&logo=telegram" />
  </a>
</p>

---

## 🧡 Like This Project?

Give it a ⭐️ on GitHub and share with your friends.

> Made with 💻 by [@asbhaibsr](https://t.me/asbhaibsr)
