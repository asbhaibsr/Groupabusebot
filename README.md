
<h1 align="center">
  <img src="https://telegra.ph/file/8ddd3c6c3b7a02a0f1f6c.jpg" width="120" style="border-radius:50%;"/><br/>
  <b>AS-FILTER-BOT</b>
</h1>

<p align="center">
  <a href="https://t.me/asbhai_bsr"><img src="https://img.shields.io/badge/📢-Update_Channel-blue.svg?style=flat&logo=telegram"/></a>
  <a href="https://t.me/askiangelbot"><img src="https://img.shields.io/badge/🤖-Support_Group-blue.svg?style=flat&logo=telegram"/></a>
  <a href="https://github.com/"><img src="https://img.shields.io/badge/⭐-Star_Repo-green.svg?style=flat&logo=github"/></a>
</p>

<h3 align="center"><span id="typewriter"></span></h3>

<script>
const phrases=["Smart Group Moderation Bot ✨","Auto Delete Bio-Link / Abuse / Links 🔗","Zero Katte Tic Tac Toe Game 🎮","Tag All / Online / Admins 🎯","Whitelist & Warn System ⚠️","24×7 Flask Health Check 🩺"];
let i=0,j=0,dir=1;
const el=document.getElementById("typewriter");
(function type(){
  el.textContent=phrases[i].slice(0,j);
  j+=dir;
  if(j>phrases[i].length){dir=-1;setTimeout(type,850);return;}
  if(j<0){dir=1;i=(i+1)%phrases.length;setTimeout(type,300);return;}
  setTimeout(type,60);
})();
</script>

---

## ​ 1-Click Deploy
| Platform | Button |
|----------|--------|
| **Koyeb** | [![Deploy to Koyeb](https://www.koyeb.com/static/images/deploy/button.svg)](https://app.koyeb.com/deploy?type=docker&image=docker.io/library/python:3.11&env[PORT]=8000&env[MONGO_DB_URI]=&env[API_ID]=&env[API_HASH]=&env[TELEGRAM_BOT_TOKEN]=&name=as-filter-bot&run_command=python%20main.py) |
| **Railway** | [![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/template?template=https%3A%2F%2Fgithub.com%2Fyourname%2Fas-filter-bot&envs=MONGO_DB_URI,API_ID,API_HASH,TELEGRAM_BOT_TOKEN&optionalEnvs=LOG_CHANNEL_ID) |

---

## ​ Features In Detail
| # | Feature | Command / Action | Description |
|--|--|--|--|
| 1 | **Auto Bio-Link Delete** | on join / every message | Removes users whose bio contains any link & warns |
| 2 | **Abuse Word Filter** | `/addabuse <word>` (admin) | Adds custom slangs; deletes + warns |
| 3 | **Link / Username Filter** | auto | Deletes Telegram links (`t.me`, `www.`, etc.) |
| 4 | **Edited Message Nuker** | auto | Deletes edited messages to prevent bypass |
| 5 | **Whitelist System** | `/free`, `/unfree`, `/freelist` | Exclude trusted users |
| 6 | **Warn → Mute → Ban** | configurable | Set limits & punishment via buttons |
| 7 | **Tagging Suite** | `/tagall`, `/onlinetag`, `/admin`, `/tagstop` | Tag everyone / online / admins |
| 8 | **Tic Tac Toe Game** | `/tictac @user1 @user2` | Play zero-katta inside group |
| 9 | **Lock & Secret Chat** | `/lock @user msg`, `/secretchat @user msg` | Send message visible only to one user |
| 10 | **Flask Health API** | `/` (port 8000) | Uptime endpoint for Koyeb / Render |
| 11 | **Broadcast & Stats** | `/broadcast` (owner) & `/stats` | Owner-only tools |
| 12 | **Cleanup Tool** | `/cleartempdata` | Clear memory & stale DB records |

---

## ​​ Installation

```bash
git clone https://github.com/yourname/as-filter-bot.git 
cd as-filter-bot
pip install -r requirements.txt
cp sample.env .env
nano .env
````

| Key                  | Sample                                                                        |
| -------------------- | ----------------------------------------------------------------------------- |
| `API_ID`             | `123456`                                                                      |
| `API_HASH`           | `abcdef123456...`                                                             |
| `TELEGRAM_BOT_TOKEN` | `123456:ABC-DEF...`                                                           |
| `MONGO_DB_URI`       | `mongodb+srv://user:pass@cluster0.x.mongodb.net/?retryWrites=true&w=majority` |
| `LOG_CHANNEL_ID`     | `-1002717243409`                                                              |

> **Tip:** Create bot → [@BotFather](https://t.me/BotFather) • Get API ID / HASH → [my.telegram.org](https://my.telegram.org)

```bash
python main.py
```

---

## &#x20;Bot Commands (Copy Friendly)

| Command            | Usage                                                                                                                            |
| ------------------ | -------------------------------------------------------------------------------------------------------------------------------- |
| **Start**          | <button onclick="navigator.clipboard.writeText('/start')">Copy</button> `/start`                                                 |
| **Help**           | <button onclick="navigator.clipboard.writeText('/help')">Copy</button> `/help`                                                   |
| **Settings**       | <button onclick="navigator.clipboard.writeText('/settings')">Copy</button> `/settings`                                           |
| **Whitelist**      | <button onclick="navigator.clipboard.writeText('/free')">Copy</button> `/free` (reply)                                           |
| **Un-Whitelist**   | <button onclick="navigator.clipboard.writeText('/unfree')">Copy</button> `/unfree` (reply)                                       |
| **Whitelist List** | <button onclick="navigator.clipboard.writeText('/freelist')">Copy</button> `/freelist`                                           |
| **Tic Tac Toe**    | <button onclick="navigator.clipboard.writeText('/tictac @user1 @user2')">Copy</button> `/tictac @user1 @user2`                   |
| **Lock Message**   | <button onclick="navigator.clipboard.writeText('/lock @username secret message')">Copy</button> `/lock @username secret message` |
| **Secret Chat**    | <button onclick="navigator.clipboard.writeText('/secretchat @username hi')">Copy</button> `/secretchat @username hi`             |
| **Tag All**        | <button onclick="navigator.clipboard.writeText('/tagall Good morning')">Copy</button> `/tagall Good morning`                     |
| **Tag Online**     | <button onclick="navigator.clipboard.writeText('/onlinetag Join fast')">Copy</button> `/onlinetag Join fast`                     |
| **Tag Admins**     | <button onclick="navigator.clipboard.writeText('/admin need help')">Copy</button> `/admin need help`                             |
| **Stop Tags**      | <button onclick="navigator.clipboard.writeText('/tagstop')">Copy</button> `/tagstop`                                             |
| **Check Perms**    | <button onclick="navigator.clipboard.writeText('/checkperms')">Copy</button> `/checkperms`                                       |
| **Add Abuse**      | <button onclick="navigator.clipboard.writeText('/addabuse word')">Copy</button> `/addabuse word`                                 |
| **Stats**          | <button onclick="navigator.clipboard.writeText('/stats')">Copy</button> `/stats` (owner only)                                    |
| **Broadcast**      | <button onclick="navigator.clipboard.writeText('/broadcast')">Copy</button> `/broadcast` (owner only)                            |
| **Clean DB**       | <button onclick="navigator.clipboard.writeText('/cleartempdata')">Copy</button> `/cleartempdata` (owner only)                    |

---

## &#x20;Contact & Support

| Purpose            | Link                                                                                                         |
| ------------------ | ------------------------------------------------------------------------------------------------------------ |
| **Update Channel** | <a href="https://t.me/asbhai_bsr"><button>📢 Join</button></a>                                               |
| **Support Group**  | <a href="https://t.me/askiangelbot"><button>🤖 Get Help</button></a>                                         |
| **Donation (UPI)** | <button onclick="navigator.clipboard.writeText('arsadsaifi8272@ibl')">Copy UPI</button> `arsadsaifi8272@ibl` |
| **Developer**      | <a href="https://t.me/asprmotion"><button>💬 DM</button></a>                                                 |

---

## &#x20;License

MIT © [AS Bhai](https://github.com/asbhai) – feel free to fork & modify.

---

<style>
button{background:#1e88e5;color:#fff;border:none;padding:4px 10px;border-radius:4px;cursor:pointer;font-size:13px}
button:hover{background:#1565c0}
</style>

<!-- -------------- END README.md -------------- -->

```

---
