import asyncio
import random
import logging
from datetime import datetime, timedelta
from pyrogram import Client, enums
from pyrogram.errors import Forbidden, BadRequest
from pymongo import MongoClient

# Set up logging
logger = logging.getLogger(__name__)

# Reminder settings
REMINDER_INTERVAL_HOURS = 2  # Interval for sending group activity reminders (in hours)
USERS_TO_TAG_COUNT = 5       # Number of online users to tag

# List of engaging messages
REMINDER_MESSAGES = {
    "funny": [
        "𝕊𝕒𝕓 𝕝𝕠𝕘 𝕚𝕥𝕟𝕖 𝕤𝕙𝕒𝕟𝕥 𝕜𝕪𝕦𝕟 𝕙𝕒𝕚𝕟? 𝕂𝕪𝕒 𝕞𝕒𝕚𝕟 𝕒𝕜𝕖𝕝𝕖 𝕓𝕒𝕒𝕥 𝕜𝕒𝕣 𝕣𝕒𝕙𝕒 𝕙𝕠𝕠𝕟? 😅",
        "𝙆𝙤𝙞 𝙝𝙖𝙞 𝙮𝙖𝙝𝙖𝙣? 𝙔𝙖 𝙨𝙖𝙗 𝙏𝙚𝙡𝙚𝙜𝙧𝙖𝙢 𝙗𝙖𝙣𝙙 𝙠𝙖𝙧𝙠𝙚 𝙨𝙤 𝙜𝙖𝙮𝙚 𝙝𝙖𝙞𝙣? 😴",
        "ꜰɪʀ ꜱᴇ ɢʀᴏᴜᴘ ᴍᴇ ᴄʜᴜᴘ ᴄʜᴀᴀᴘ ᴋᴀʏꜱᴇ ʙᴀᴀᴛ ᴋᴀʀᴇᴇ? 🤫",
        "𝒜𝒶𝒿 𝓉𝑜 𝒷𝒽𝒶𝑔𝓌𝒶𝓃 𝒿𝒾 𝓃𝑒𝓈𝒽𝒶 𝓁𝒶𝑔𝒶𝓎𝑒 𝒽𝒶𝒾𝓃 𝓀𝓎𝒶? 😵‍💫",
        "𝐈𝐬 𝐠𝐫𝐨𝐮𝐩 𝐦𝐞 𝐤𝐨𝐢 𝐣𝐢𝐧𝐝𝐚 𝐡𝐚𝐢 𝐲𝐚 𝐬𝐚𝐛 𝐦𝐮𝐦𝐦𝐲 𝐤𝐞 𝐝𝐮𝐝𝐡 𝐩𝐞𝐞𝐤𝐞 𝐬𝐨 𝙜𝙖𝙮𝙚? 🍼",
        "𝓘𝓽𝓷𝓲 𝓼𝓪𝓷𝓽𝓪 𝓴𝔂𝓸𝓷 𝓱𝓪𝓲? 𝓚𝓸𝓲 𝓽𝓸 𝓱𝓪𝓼𝓪𝓸 𝔂𝓪𝓪𝓻! 😆",
        "𝖄𝖔𝖚 𝖐𝖓𝖔𝖜 𝖜𝖍𝖆𝖙'𝖘 𝖗𝖆𝖗𝖊? 𝕿𝖍𝖎𝖘 𝖌𝖗𝖔𝖚𝖕'𝖘 𝖆𝖈𝖙𝖎𝖛𝖎𝖙𝖞! 🦄",
        "Ａｒｅ　ｙｏｕ　ｇｕｙｓ　ｄｅａｄ　ｏｒ　ｊｕｓｔ　ｐｌａｙｉｎｇ　ｄｅａｄ？ 💀"
    ],
    "romantic": [
        "𝔄𝔞𝔭𝔨𝔢 𝔟𝔦𝔫𝔞 𝔶𝔢𝔥 𝔤𝔯𝔬𝔲𝔭 𝔨𝔦𝔱𝔫𝔞 𝔰𝔬𝔬𝔫𝔞 𝔩𝔞𝔤𝔱𝔞 𝔥𝔞𝔦. 𝔎𝔬𝔦 𝔱𝔬 𝔢𝔨 𝔯𝔬𝔪𝔞𝔫𝔱𝔦𝔠 𝔪𝔢𝔰𝔰𝔞𝔤𝔢 𝔨𝔞𝔯𝔬! ❤️",
        "𝙆𝙞𝙨𝙞 𝙠𝙤 𝙥𝙧𝙤𝙥𝙤𝙨𝙚 𝙠𝙖𝙧𝙣𝙚 𝙠𝙖 𝙢𝙤𝙤𝙙 𝙝𝙖𝙞? 𝙔𝙚𝙝 𝙜𝙧𝙤𝙪𝙥 𝙖𝙖𝙥𝙠𝙞 𝙝𝙚𝙡𝙥 𝙠𝙖𝙧 𝙨𝙖𝙠𝙩𝙖 𝙝𝙖𝙞! 💍",
        "ʏᴏᴜ'ʀᴇ ʟɪᴋᴇ ᴍʏ ᴘʜᴏɴᴇ ʙᴀᴛᴛᴇʀʏ - ʏᴏᴜ ᴄʜᴀʀɢᴇ ᴍʏ ʟɪꜰᴇ! 🔋❤️",
        "𝒯𝓊𝓂 𝒽𝒶𝓇 𝓌𝒶𝓀𝓉 𝓂𝑒𝓇𝑒 𝒹𝒽𝒶𝒹𝓀𝒶𝓃𝑜 𝓂𝑒 𝒽𝑜. 𝒮𝒶𝓂𝒿𝒽𝑒? 💓",
        "𝐘𝐨𝐮 + 𝐌𝐞 = 𝐅𝐨𝐫𝐞𝐯𝐞𝐫 ❤️ 𝐀𝐠𝐫𝐞𝐞? 😘",
        "𝓘 𝔀𝓪𝓷𝓽 𝓽𝓸 𝓫𝓮 𝔂𝓸𝓾𝓻 𝓯𝓪𝓿𝓸𝓻𝓲𝓽𝓮 𝓱𝓪𝓫𝓲𝓽... 𝓐𝓷𝓭 𝓽𝓱𝓮𝓷 𝓘 𝔀𝓪𝓷𝓽 𝓽𝓸 𝓻𝓾𝓲𝓷 𝓲𝓽. 😈",
        "𝖂𝖍𝖞 𝖉𝖔 𝖈𝖔𝖒𝖕𝖚𝖙𝖊𝖗𝖘 𝖘𝖚𝖈𝖐 𝖆𝖙 𝖋𝖑𝖎𝖗𝖙𝖎𝖓𝖌? 𝕭𝖊𝖈𝖆𝖚𝖘𝖊 𝖙𝖍𝖊𝖞 𝖍𝖆𝖛𝖊 𝖓𝖔 𝖍𝖆𝖗𝖉 𝖉𝖗𝖎𝖛𝖊! 😉",
        "Ａｒｅ　ｙｏｕ　ａ　ｍａｇｎｅｔ？ 🧲 Ｂｅｃａｕｓｅ　Ｉ'ｍ　ａｔｔｒａｃｔｅｄ　ｔｏ　ｙｏｕ！ 💫"
    ],
    "commands": [
        "ℕ𝕒𝕪𝕖 𝕦𝕤𝕖𝕣𝕤 𝕜𝕖 𝕝𝕚𝕖: 𝕓𝕠𝕥 𝕜𝕚 𝕔𝕠𝕞𝕞𝕒𝕟𝕕𝕤 𝕛𝕒𝕟𝕟𝕖 𝕜𝕖 𝕝𝕚𝕪𝕖 `/help` 𝕥𝕪𝕡𝕖 𝕜𝕒𝕣𝕖𝕚𝕟. 🤖",
        "𝘽𝙤𝙧𝙚𝙙 𝙝𝙤 𝙧𝙖𝙝𝙚 𝙝𝙤? 𝘾𝙝𝙖𝙡𝙤, 𝙜𝙖𝙢𝙚 𝙠𝙝𝙚𝙡𝙩𝙚 𝙝𝙖𝙞𝙣! `/tictac` 𝙘𝙤𝙢𝙢𝙖𝙣𝙙 𝙨𝙚 𝙨𝙝𝙪𝙧𝙪 𝙠𝙖𝙧𝙤. 🎮",
        "ɴᴇᴡ ᴜᴘᴅᴀᴛᴇꜱ! ᴛʏᴘᴇ `/update` ꜰᴏʀ ʟᴀᴛᴇꜱᴛ ꜰᴇᴀᴛᴜʀᴇꜱ. 🆕",
        "𝒜𝒶𝓅 𝒷𝑜𝓉 𝓈𝑒 𝓅𝓇𝑜𝓂𝑜𝓉𝑒 𝒽𝑜𝓈𝒶𝓀𝓉𝑒 𝒽𝒶𝒾𝓃? 𝒯𝓎𝓅𝑒 `/promote` ⬆️",
        "𝐖𝐚𝐧𝐭 𝐭𝐨 𝐬𝐞𝐞 𝐜𝐨𝐨𝐥 𝐬𝐭𝐢𝐜𝐤𝐞𝐫𝐬? 𝐓𝐲𝐩𝐞 `/sticker` 🎭",
        "𝓘𝓼 𝓼𝓾𝓼𝓲𝓬 𝓽𝓱𝓮 𝓯𝓸𝓸𝓭 𝓸𝓯 𝓵𝓸𝓿𝓮? 𝓟𝓵𝓪𝔂 𝓼𝓸𝓶𝓮 𝔀𝓲𝓱 `/play` 🎵",
        "𝕿𝖞𝖕𝖊 `/joke` 𝖋𝖔𝖗 𝖆 𝖉𝖆𝖎𝖑𝖞 𝖉𝖔𝖘𝖊 𝖔𝖋 𝖑𝖆𝖚𝖌𝖍𝖙𝖊𝖗! 🤣",
        "Ｔｙｐｅ　`/quote`　ｆｆｆｆｆｆ　ａ　ｄａｉｌｙ　ｍｏｔｉｖａｔｉｏｎａｌ　ｑｕｏｔｅ！ 💪"
    ],
    "general": [
        "𝔄𝔞𝔧 𝔨𝔞 𝔡𝔦𝔫 𝔨𝔞𝔦𝔰𝔞 𝔯𝔞𝔥𝔞 𝔰𝔞𝔟𝔨𝔞? 𝔎𝔬𝔦 𝔦𝔫𝔱𝔢𝔯𝔢𝔰𝔱𝔦𝔫𝔤 𝔰𝔱𝔬𝔯𝔶 𝔥𝔞𝔦? 📖",
        "𝘼𝙥𝙣𝙚 𝙛𝙖𝙫𝙤𝙧𝙞𝙩𝙚 𝙥𝙤𝙚𝙢/𝙨𝙝𝙖𝙮𝙖𝙧𝙞 𝙨𝙝𝙖𝙧𝙚 𝙠𝙖𝙧𝙤 𝙟𝙖𝙨𝙖𝙣𝙙 𝙠𝙖𝙧𝙣𝙚 𝙬𝙖𝙡𝙤𝙣 𝙠𝙚 𝙡𝙞𝙮𝙚. ✍️",
        "ᴡʜᴀᴛ'ꜱ ʏᴏᴜʀ ꜰᴀᴠᴏʀɪᴛᴇ ᴍᴏᴍᴇɴᴛ ꜰʀᴏᴍ ᴛʜɪꜱ ᴡᴇᴇᴋ? 🗓️",
        "𝒯𝑒𝓁𝓁 𝓊𝓈 𝓈𝑜𝓂𝑒𝓉𝒽𝒾𝓃𝑔 𝒶𝒷𝑜𝓊𝓉 𝓎𝑜𝓊𝓇𝓈𝑒𝒻 𝓌𝑒 𝒹𝑜𝓃'𝓉 𝓀𝓃𝑜𝓌! 🤫",
        "𝐖𝐡𝐚𝐭'𝐬 𝐭𝐡𝐞 𝐦𝐨𝐬𝐭 𝐚𝐝𝐯𝐞𝐧𝐭𝐮𝐫𝐨𝐮𝐬 𝐭𝐡𝐢𝐧𝐠 𝐲𝐨𝐮'𝐯𝐞 𝐞𝐯𝐞𝐫 𝐝𝐨𝐧𝐞? 🚀",
        "𝓗𝓸𝔀 𝔀𝓪𝓼 𝔂𝓸𝓾𝓻 𝓭𝓪𝔂? 𝓢𝓱𝓪𝓻𝓮 𝔂𝓸𝓾𝓻 𝓱𝓲𝓰𝓱𝓼 𝓪𝓷𝓭 𝓵𝓸𝔀𝓼! ☀️🌧️",
        "𝕯𝖔 𝖞𝖔𝖚 𝖍𝖆𝖛𝖊 𝖆 𝖉𝖆𝖎𝖑𝖞 𝖗𝖔𝖚𝖙𝖎𝖓𝖊? 𝕾𝖍𝖆𝖗𝖊 𝖎𝖙 𝖜𝖎𝖙𝖍 𝖚𝖘! ⏰",
        "Ｗｈｙｔ　ｄｏ　ｙｏｕ　ｄｏ　ｗｈｅｎ　ｙｏｕ　ｆｅｅｌ　ｂｏｒｅｄ？　Ｔｅｌｌ　ｕｓ　ｙｏｕｒ　ｗａｙｓ！ 🎨"
    ],
    "motivational": [
        "𝕋𝕠𝕕𝕒𝕪 𝕚𝕤 𝕒 𝕘𝕣𝕖𝕒𝕥 𝕕𝕒𝕪 𝕥𝕠 𝕓𝕠 𝕤𝕠𝕞𝕖𝕥𝕙𝕚𝕟𝕘 𝕒𝕞𝕒𝕫𝕚𝕟𝕘! ✨",
        "𝘿𝙤𝙣'𝙩 𝙨𝙩𝙤𝙥 𝙬𝙝𝙚𝙣 𝙮𝙤𝙪'𝙧𝙚 𝙩𝙞𝙧𝙚𝙙. 𝙎𝙩𝙤𝙥 𝙬𝙝𝙚𝙣 𝙮𝙤𝙪'𝙧𝙚 𝙙𝙤𝙣𝙚. 💪",
        "ʏᴏᴜʀ ᴏɴʟʏ ʟɪᴍɪᴛ ɪs ʏᴏᴜʀꜱᴇʟꜰ - ʙʀᴇᴀᴋ ꜰʀᴇᴇ! 🦅",
        "𝒯𝒽𝑒 𝒷𝑒𝓈𝓉 𝓌𝒶𝓎 𝓉𝑜 𝓅𝓇𝑒𝒹𝒾𝒸𝓉 𝓉𝒽𝑒 𝒻𝓊𝓊𝓇𝑒 𝒾𝓈 𝓉𝑜 𝒸𝓇𝑒𝒶𝓉𝑒 𝒾𝓉. 🚀",
        "𝐒𝐮𝐜𝐜𝐞𝐬𝐬 𝐢𝐬 𝐧𝐨𝐭 𝐟𝐢𝐧𝐚𝐥, 𝐟𝐚𝐢𝐥𝐮𝐫𝐞 𝐢𝐬 𝐧𝐨𝐭 𝐟𝐚𝐭𝐚𝐥: 𝐈𝐭 𝐢𝐬 𝐭𝐡𝐞 𝐜𝐨𝐮𝐫𝐚𝐠𝐞 𝐭𝐨 𝐜𝐨𝐧𝐭𝐢𝐧𝐮𝐞 𝐭𝐡𝐚𝐭 𝐜𝐨𝐮𝐧𝐭𝐬. 🏆",
        "𝓣𝓱𝓮 𝓸𝓷𝔂 𝓹𝓮𝓻𝓼𝓸𝓷 𝔂𝓸𝓾 𝓼𝓱𝓸𝓾𝓵𝓭 𝓽𝔂 𝓽𝓸 𝓫𝓮 𝓫𝓮𝓽𝓮 𝓽𝓱𝓪𝓷 𝓲𝓼 𝓽𝓱𝓮 𝓹𝓮𝓼𝓷 𝔂𝓸𝓾 𝔀𝓮𝓻𝓮 𝔂𝓮𝓼𝓽𝓮𝓻𝓭𝓪𝔂. 🌟",
        "𝖄𝖔𝖚 𝖆𝖗𝖊 𝖈𝖆𝖕𝖆𝖇𝖑𝖊 𝖔𝖋 𝖆𝖒𝖆𝖟𝖎𝖓𝖌 𝖙𝖍𝖎𝖓𝖌𝖘! 𝕭𝖊𝖑𝖎𝖊𝖛𝖊 𝖎𝖓 𝖞𝖔𝖚𝖗𝖘𝖊𝖑𝖋. 💫",
        "Ｄｏｎ'ｔ　ｗａｉｔ　ｆｆｆｆｆ　ｔｈｅ　ｐｅｒｆｅｃｔ　ｍｏｍｅｎｔ．　Ｔａｋｅ　ｔｈｅ　ｍｏｍｅｎｔ　ａｎｄ　ｍａｋｅ　ｉｔ　ｐｅｒｆｅｃｔ． 🌈"
    ],
    "group": [
        "𝔊𝔯𝔬𝔲𝔭 𝔪𝔢𝔪𝔟𝔢𝔯𝔰, 𝔞𝔞𝔧 𝔨𝔦 𝔪𝔢𝔢𝔱𝔦𝔫𝔤 𝔰𝔥𝔲𝔯𝔲 𝔨𝔞𝔯𝔱𝔢 𝔥𝔞𝔦𝔫! 🎤",
        "𝙃𝙚𝙮 𝙥𝙚𝙤𝙥𝙡𝙚! 𝙇𝙚𝙩's 𝙢𝙖𝙠𝙚 𝙩𝙝𝙞𝙨 𝙜𝙧𝙤𝙪𝙥 𝙢𝙤𝙧𝙚 𝙖𝙘𝙩𝙞𝙫𝙚. 𝙒𝙝𝙤'𝙨 𝙞𝙣? 💬",
        "ɢʀᴏᴜᴘ ɢᴏᴀʟ: 100+ ᴍᴇꜱꜱᴀɢᴇꜱ ᴛᴏᴅᴀʏ! ᴄᴀɴ ᴡᴇ ᴅᴏ ɪᴛ? 💯",
        "𝒢𝓇𝑜𝓊𝓅 𝓇𝓊𝓁𝑒𝓈 𝓇𝑒𝓂𝒾𝓃𝒹𝑒𝓇: 𝐵𝑒 𝓀𝒾𝓃𝒹, 𝒷𝑒 𝒶𝒸𝓉𝒾𝓋𝑒, 𝒶𝓃𝒹 𝒽𝒶𝓋𝓋𝑒 𝒻𝓊𝓃! 🤝",
        "𝐋𝐞𝐭'𝐬 𝐰𝐞𝐥𝐜𝐨𝐦𝐞 𝐨𝐮𝐫 𝐧𝐞𝐰 𝐦𝐞𝐦𝐛𝐞𝐫𝐬! 𝐒𝐚𝐲 𝐡𝐢! 👋",
        "𝓦𝓱𝓪𝓽'𝓼 𝔂𝓸 𝓯𝓯𝓯𝓯𝓯 𝓽 𝓭𝓲𝓼𝓬𝓾𝓼𝓼 𝓽𝓸𝓭𝓪𝓽? 𝓛𝓮𝓽'𝓼 𝓫𝓻𝓪𝓲𝓷𝓼𝓽𝓸𝓻𝓶! 💡",
        "𝕿𝖍𝖎𝖘 𝖌𝖗𝖔𝖚𝖕 𝖎𝖘 𝖆𝖇𝖔𝖚𝖙 𝖙𝖔 𝖍𝖎𝖙 500+ 𝖒𝖊𝖒𝖇𝖊𝖗𝖘! 𝖀𝖘𝖊 `/invite` 𝖙𝖔 𝖇𝖗𝖎𝖓𝖌 𝖋𝖗𝖎𝖊𝖓𝖉𝖘. 🚀",
        "Ｌｅｔ'ｓ　ｐｌａｙ　ａ　ｇａｍｅ！　Ｔｙｐｅ　`/game`　ｔｏ　ｓｅｅ　ｏｕｒ　ｇｒｏｕｐ　ｇａｍｅｓ． 🎲"
    ]
}

def get_random_message():
    """Fetches a random message from the dictionary."""
    message_type = random.choice(list(REMINDER_MESSAGES.keys()))
    return random.choice(REMINDER_MESSAGES[message_type])

async def send_random_reminder(client: Client, db: MongoClient):
    """Sends a random reminder to all active groups."""
    if db is None:
        logger.warning("MongoDB not connected. Cannot send group activity reminders.")
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
                logger.info(f"Sent group activity reminder to group {chat_id}")
                
                await asyncio.sleep(5)  # Add a small delay between groups to avoid FloodWait
        except Exception as e:
            logger.error(f"Error sending group activity reminder to chat {chat_id}: {e}")

async def reminder_scheduler(client: Client, db: MongoClient):
    """Schedules both user-set and group activity reminders."""
    logger.info("Reminder scheduler started.")
    
    group_reminder_task = None
    
    while True:
        try:
            # Check for and send user-set reminders every minute
            if db is not None:
                current_time = datetime.now()
                reminders_to_send = db.reminders.find({"due_time": {"$lte": current_time}})
                
                for reminder in reminders_to_send:
                    user_id = reminder['user_id']
                    chat_id = reminder['chat_id']
                    text = reminder['text']
                    
                    try:
                        await client.send_message(chat_id, f"⏰ Reminder for <a href='tg://user?id={user_id}'>you</a>: {text}", parse_mode=enums.ParseMode.HTML)
                        logger.info(f"User-set reminder sent to user {user_id} in chat {chat_id}.")
                        db.reminders.delete_one({"_id": reminder['_id']})
                    except (Forbidden, BadRequest) as e:
                        logger.error(f"Failed to send user-set reminder to chat {chat_id}: {e}")
                        db.reminders.delete_one({"_id": reminder['_id']})
                    except Exception as e:
                        logger.error(f"An unexpected error occurred while sending user-set reminder: {e}")
            
            # Start the group activity reminder task if it's not already running
            if group_reminder_task is None or group_reminder_task.done():
                group_reminder_task = asyncio.create_task(send_random_reminder(client, db))
            
            await asyncio.sleep(60) # Wait for 1 minute before next check
            
        except Exception as e:
            logger.error(f"An error occurred in the reminder scheduler: {e}")
