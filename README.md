<h1 align="center">
  <img src="https://readme-typing-svg.herokuapp.com?font=Fira+Code&size=30&pause=1000&center=true&vCenter=true&width=435&lines=🚫+Group+Abuse+Filter+Bot+🚫;Keep+your+Telegram+groups+clean+and+safe!">
</h1>

<p align="center">
  <b>A smart Telegram bot that automatically detects and removes abusive messages from groups using a profanity filter.</b><br><br>
  <a href="https://t.me/asbhaibsr">
    <img src="https://img.shields.io/badge/👤 Owner-%40asbhaibsr-blue?style=for-the-badge&logo=telegram" />
  </a>
  <a href="https://t.me/asbhai_bsr">
    <img src="https://img.shields.io/badge/📢 Updates-%40asbhai__bsr-orange?style=for-the-badge&logo=telegram" />
  </a>
</p>

---

## ✨ Features

- 🧠 Automatically filters abusive and profane messages
- 🧹 Auto-delete messages with bad words in real time
- 🛡️ Protects Telegram group members
- ⚡️ Simple setup and blazing fast
- ☁️ Ready to deploy on **Koyeb**, **Render**, **Railway**, etc.

---

## 🚀 Deploy to Koyeb

1. Fork this repository
2. Go to [Koyeb](https://app.koyeb.com/)
3. Click **Create App**
4. Choose:
   - GitHub → your forked repo
   - Buildpack: `python`
   - Add this environment variable:
     ```
     BOT_TOKEN = your_telegram_bot_token
     ```
5. Deploy 🚀

---

## 🛠 Manual Setup (Local)

```bash
git clone https://github.com/yourusername/Groupabusebot.git
cd Groupabusebot
pip install -r requirements.txt
```

Edit `main.py` and paste your Telegram Bot token:
```python
updater = Updater("YOUR_BOT_TOKEN", use_context=True)
```

Run it:
```bash
python main.py
```

---

## 🧩 File Structure

| File | Purpose |
|------|---------|
| `main.py` | Main bot logic and message handling |
| `profanity_filter.py` | Word filter logic and abusive words |
| `requirements.txt` | Python package list |

---

## 📞 Contact & Support

<p align="center">
  <a href="https://t.me/asbhaibsr">
    <img src="https://img.shields.io/badge/👨‍💻 Contact-%40asbhaibsr-blue?style=for-the-badge&logo=telegram" />
  </a>
  <a href="https://t.me/asbhai_bsr">
    <img src="https://img.shields.io/badge/📢 Update+Channel-%40asbhai__bsr-orange?style=for-the-badge&logo=telegram" />
  </a>
</p>

---

## 💖 Support This Project

If you like this bot, give it a ⭐️ on GitHub, share it with others, or contribute to improve it!

---

> Made with ❤️ by [@asbhaibsr](https://t.me/asbhaibsr)
