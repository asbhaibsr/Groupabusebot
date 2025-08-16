import logging
from pymongo import MongoClient, ReturnDocument
from datetime import datetime
from profanity_filter import ProfanityFilter
from config import DEFAULT_WARNING_LIMIT, DEFAULT_PUNISHMENT, DEFAULT_DELETE_TIME

logger = logging.getLogger(__name__)
db = None

def init_mongodb(mongo_uri):
    global db
    profanity_filter = None
    if mongo_uri is None:
        logger.error("MONGO_DB_URI environment variable is not set. Cannot connect to MongoDB.")
        profanity_filter = ProfanityFilter(mongo_uri=None)
        return None, profanity_filter

    try:
        mongo_client = MongoClient(mongo_uri)
        db = mongo_client.get_database("asfilter")
        db.groups.create_index("chat_id", unique=True)
        db.users.create_index("user_id", unique=True)
        db.warnings.create_index([("user_id", 1), ("chat_id", 1)], unique=True)
        db.config.create_index("chat_id", unique=True)
        db.whitelist.create_index([("chat_id", 1), ("user_id", 1)], unique=True)
        db.biolink_exceptions.create_index([("chat_id", 1), ("user_id", 1)], unique=True)
        db.settings.create_index("chat_id", unique=True)
        db.warn_settings.create_index("chat_id", unique=True)
        db.notification_settings.create_index("chat_id", unique=True)

        profanity_filter = ProfanityFilter(mongo_uri=mongo_uri)
        logger.info("MongoDB connection and collections initialized successfully.")
        return db, profanity_filter
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB or initialize collections: {e}.")
        profanity_filter = ProfanityFilter(mongo_uri=None)
        logger.warning("Falling back to default profanity list.")
        return None, profanity_filter

def get_warn_settings(chat_id, category):
    if db is None: return DEFAULT_WARNING_LIMIT, DEFAULT_PUNISHMENT
    settings = db.warn_settings.find_one({"chat_id": chat_id})
    if not settings or category not in settings:
        return DEFAULT_WARNING_LIMIT, DEFAULT_PUNISHMENT
    return settings[category].get("limit", DEFAULT_WARNING_LIMIT), settings[category].get("punishment", DEFAULT_PUNISHMENT)

def update_warn_settings(chat_id, category, limit=None, punishment=None):
    if db is None: return
    update_doc = {}
    if limit is not None: update_doc[f"{category}.limit"] = limit
    if punishment: update_doc[f"{category}.punishment"] = punishment
    db.warn_settings.update_one({"chat_id": chat_id}, {"$set": update_doc}, upsert=True)

def get_group_settings(chat_id):
    if db is None:
        return {"delete_biolink": True, "delete_abuse": True, "delete_edited": True, "delete_links_usernames": True}
    settings = db.settings.find_one({"chat_id": chat_id})
    if not settings:
        default_settings = {"chat_id": chat_id, "delete_biolink": True, "delete_abuse": True, "delete_edited": True, "delete_links_usernames": True}
        db.settings.insert_one(default_settings)
        return default_settings
    return settings

def update_group_setting(chat_id, setting_key, setting_value):
    if db is None: return
    db.settings.update_one({"chat_id": chat_id}, {"$set": {setting_key: setting_value}}, upsert=True)

def get_notification_delete_time(chat_id):
    if db is None: return DEFAULT_DELETE_TIME
    settings = db.notification_settings.find_one({"chat_id": chat_id})
    return settings.get("delete_time", DEFAULT_DELETE_TIME) if settings else DEFAULT_DELETE_TIME

def update_notification_delete_time(chat_id, time_in_minutes):
    if db is None: return
    db.notification_settings.update_one({"chat_id": chat_id}, {"$set": {"delete_time": time_in_minutes}}, upsert=True)

def is_whitelisted_sync(chat_id, user_id):
    if db is None: return False
    return db.whitelist.find_one({"chat_id": chat_id, "user_id": user_id}) is not None

def add_whitelist_sync(chat_id, user_id):
    if db is None: return
    db.whitelist.update_one({"chat_id": chat_id, "user_id": user_id}, {"$set": {"timestamp": datetime.now()}}, upsert=True)

def remove_whitelist_sync(chat_id, user_id):
    if db is None: return
    db.whitelist.delete_one({"chat_id": chat_id, "user_id": user_id})

def get_whitelist_sync(chat_id):
    if db is None: return []
    return [doc["user_id"] for doc in db.whitelist.find({"chat_id": chat_id})]

def get_warnings_sync(user_id: int, chat_id: int, category: str):
    if db is None: return 0
    warnings_doc = db.warnings.find_one({"user_id": user_id, "chat_id": chat_id})
    if warnings_doc and "counts" in warnings_doc and category in warnings_doc["counts"]:
        return warnings_doc["counts"][category]
    return 0

def increment_warning_sync(chat_id, user_id, category):
    if db is None: return 1
    warnings_doc = db.warnings.find_one_and_update(
        {"chat_id": chat_id, "user_id": user_id},
        {"$inc": {f"counts.{category}": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER
    )
    return warnings_doc["counts"][category]

def reset_warnings_sync(chat_id, user_id, category):
    if db is None: return
    db.warnings.update_one(
        {"chat_id": chat_id, "user_id": user_id},
        {"$set": {f"counts.{category}": 0}}
    )
