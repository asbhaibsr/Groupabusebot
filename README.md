<h1 align="center">🚫 Group Abuse Filter Bot 🚫</h1>

<p align="center"><i>Clean your Telegram groups automatically using smart word filters and admin tools.</i></p>

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
- ☁️ Deployable on Koyeb, Render, Railway
- 👑 Admin-only commands for full control

---

## 🚀 Deploy to Koyeb

1. **Fork this repo**
2. Go to [Koyeb Dashboard](https://app.koyeb.com/)
3. Click "Create App"
4. Connect GitHub and select your repo
5. Set build type as `Python`
6. Add the following environment variables:

```
TELEGRAM_BOT_TOKEN=your_bot_token
MONGO_DB_URI=your_mongodb_connection
GROUP_ADMIN_USERNAME=your_admin_username
```

7. Click **Deploy** — done! 🚀

---

## 🛠 Manual Setup (Local)

```bash
git clone https://github.com/yourusername/Groupabusebot.git
cd Groupabusebot
pip install -r requirements.txt
```

Edit your token inside `main.py` or use environment variables.

Then run:

```bash
python main.py
```

---

## 💬 Admin Commands

> Only allowed for users listed in `ADMIN_USER_IDS` inside `main.py`

```
/start              - Check if bot is working
/help               - Show help message
/stats              - View bot stats
/broadcast <msg>    - Send a message to all users
/addabuse <word>    - Add abusive word to blocklist
/delabuse <word>    - Remove a word from blocklist
/listabuse          - Show current blocked words
```

---

## 📦 Logs & Case Handling

| Type        | Sent To           | Description |
|-------------|-------------------|-------------|
| Logs        | `LOG_CHANNEL_ID`  | All general bot actions |
| Abuse Cases | `CASE_CHANNEL_ID` | Messages with abuse |
| Warning     | In Group Chat     | User warned, message deleted |
| Admin Ping  | In Group          | Admin mentioned if needed |

You can configure all IDs inside `main.py` or through Koyeb env variables.

---

## 🧾 File Structure

| File                | Description                          |
|---------------------|--------------------------------------|
| `main.py`           | Main bot logic                       |
| `profanity_filter.py` | Words list and filter logic        |
| `requirements.txt`  | Python dependencies                  |
| `.env` (optional)   | Store secrets for local dev or Koyeb |

---

## 🙋‍♂️ Contact & Support

<p align="center">
  <a href="https://t.me/asbhaibsr">
    <img src="https://img.shields.io/badge/👨‍💻 Contact-%40asbhaibsr-blue?style=for-the-badge&logo=telegram" />
  </a>
  <a href="https://t.me/asbhai_bsr">
    <img src="https://img.shields.io/badge/📢 Update+Channel-%40asbhai__bsr-orange?style=for-the-badge&logo=telegram" />
  </a>
</p>

---

## ⭐️ Like This Project?

Star the repo, share with friends, or contribute!

> Made with ❤️ by [@asbhaibsr](https://t.me/asbhaibsr)
