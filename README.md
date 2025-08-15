# Group Guardian Bot

![GG Logo](https://via.placeholder.com/56x56/5b9cff/09111a?text=GG)  
Telegram group moderation bot — abuse/link filter, warn→mute→ban, tagging, games & more.

- **Python 3.11+** · **Pyrogram** · **MongoDB** · **Koyeb Ready**

## ✨ Features

| #  | Feature               | Command / Action               | Description |
|----|-----------------------|--------------------------------|-------------|
| 1  | Auto Bio-Link Delete  | On join / every message        | Users whose bio contains links are auto-removed |
| 2  | Abuse Word Filter     | `/addabuse <word>`             | Deletes abusive words + warns user |
| 3  | Link/Username Filter  | Automatic                      | Blocks `t.me`, `http(s)://`, and usernames |
| 4  | Edited Message Nuker  | Automatic                      | Deletes edited messages to prevent bypass |
| 5  | Whitelist System      | `/free`, `/unfree`, `/freelist`| Trusted members excluded from filters |
| 6  | Warn → Mute → Ban     | Configurable                   | Escalating punishments after limits |
| 7  | Tagging Suite         | `/tagall`, `/onlinetag`, `/admin`, `/tagstop` | Mention everyone/online/admins |
| 8  | Tic Tac Toe           | `/tictac @user1 @user2`        | Play inside the group |
| 9  | Lock & Secret Chat    | `/lock @user msg`, `/secretchat @user msg` | Private-like messaging in group |
| 10 | Flask Health API      | `GET /` (port 8000)            | Uptime monitoring |
| 11 | Broadcast & Stats     | `/broadcast`, `/stats` (owner)  | Owner utilities |
| 12 | Cleanup Tool          | `/cleartempdata`               | Clear old temp data |

## 🚀 Deployment

### 1-Click Deploy
[![Deploy to Koyeb](https://img.shields.io/badge/Koyeb-121a26?style=for-the-badge&logo=koyeb&logoColor=5b9cff)](https://app.koyeb.com/deploy?type=docker&image=docker.io/library/python:3.11&env[PORT]=8000&env[MONGO_DB_URI]=&env[API_ID]=&env[API_HASH]=&env[TELEGRAM_BOT_TOKEN]=&name=group-guardian-bot&run_command=python%20main.py)
[![Deploy on Railway](https://img.shields.io/badge/Railway-121a26?style=for-the-badge&logo=railway&logoColor=5b9cff)](https://railway.app/new/template?template=https%3A%2F%2Fgithub.com%2Fyourname%2Fgroup-guardian-bot)

*Set required env vars during deploy. Health check runs on `PORT=8000`.*

### Local Setup
```bash
git clone https://github.com/yourname/group-guardian-bot.git
cd group-guardian-bot
pip install -r requirements.txt
