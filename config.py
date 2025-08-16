import os
import re
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", -1002717243409))
ADMIN_USER_IDS = [7315805581]
MONGO_DB_URI = os.getenv("MONGO_DB_URI")

DEFAULT_WARNING_LIMIT = 3
DEFAULT_PUNISHMENT = "mute"
DEFAULT_DELETE_TIME = 0
URL_PATTERN = re.compile(r'\b(?:https?://|www\.|t\.me/|telegra\.ph/)[^\s]+\b|@\w+', re.IGNORECASE)
