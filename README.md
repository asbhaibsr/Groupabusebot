<!-- -------------- README.md -------------- -->
<!-- Paste this entire block into your repo root as README.md -->

<h1 align="center">
  <img src="https://telegra.ph/file/8ddd3c6c3b7a02a0f1f6c.jpg" width="120" style="border-radius:50%;" /><br/>
  <b>AS-FILTER-BOT</b>
</h1>

<p align="center">
  <a href="https://t.me/asbhai_bsr"><img src="https://img.shields.io/badge/📢-Update_Channel-blue.svg?style=flat&logo=telegram" /></a>
  <a href="https://t.me/askiangelbot"><img src="https://img.shields.io/badge/🤖-Support_Group-blue.svg?style=flat&logo=telegram" /></a>
  <a href="https://github.com/"><img src="https://img.shields.io/badge/⭐-Star_Repo-green.svg?style=flat&logo=github" /></a>
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

## ​ Keys & Env Variables
| Key                 | Sample                                                                  |
|---------------------|-------------------------------------------------------------------------|
| `API_ID`            | `123456`                                                                 |
| `API_HASH`          | `abcdef123456...`                                                        |
| `TELEGRAM_BOT_TOKEN`| `123456:ABC-DEF...`                                                      |
| `MONGO_DB_URI`      | `mongodb+srv://user:pass@cluster0.x.mongodb.net/?retryWrites=true&w=majority` |
| `LOG_CHANNEL_ID`    | `-1002717243409`                                                         |

> Tip: Create bot → [@BotFather](https://t.me/BotFather) • Get API ID / HASH → [my.telegram.org](https://my.telegram.org)

---

## ​​ Bot Commands (Copy Friendly)

| Command         | Usage                      |
|-----------------|---------------------------|
| **Start**       | `/start`                  |
| **Help**        | `/help`                   |
| **Settings**    | `/settings`               |
| **Whitelist**   | `/free` (reply)           |
| **Un-Whitelist**| `/unfree` (reply)         |
| **Whitelist List**| `/freelist`            |
| **Tic Tac Toe** | `/tictac @user1 @user2`   |
| **Lock Message**| `/lock @username <msg>`   |
| **Secret Chat** | `/secretchat @user <msg>` |
| **Tag All**     | `/tagall Good morning`    |
| **Tag Online**  | `/onlinetag Join fast`    |
| **Tag Admins**  | `/admin need help`        |
| **Stop Tags**   | `/tagstop`                |
| **Check Perms** | `/checkperms`             |
| **Add Abuse**   | `/addabuse <word>`        |
| **Stats**       | `/stats` (owner only)     |
| **Broadcast**   | `/broadcast` (owner only) |
| **Clean DB**    | `/cleartempdata` (owner only) |

---

## ​ Contact & Support

| Purpose             | Link                                   |
|---------------------|----------------------------------------|
| **Update Channel**  | https://t.me/asbhai_bsr                |
| **Support Group**   | https://t.me/askiangelbot              |
| **Donation (UPI)**  | `arsadsaifi8272@ibl`                  |
| **Developer**       | https://t.me/asprmotion               |

---

## ​ License

MIT © [AS Bhai](https://github.com/asbhai) – feel free to fork & modify.

---

<style>
  button {
    background: #1e88e5;
    color: #fff;
    border: none;
    padding: 4px 10px;
    border-radius: 4px;
    cursor: pointer;
    font-size: 13px;
  }
  button:hover {
    background: #1565c0;
  }
</style>

<!-- -------------- END README.md -------------- -->
