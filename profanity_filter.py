import re
import logging
from datetime import datetime
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure

logger = logging.getLogger(__name__)

class ProfanityFilter:
    def __init__(self, mongo_uri=None):
        self.bad_words = self._load_default_bad_words() # Default list se load karega
        self.mongo_client = None
        self.db = None
        self.collection = None

        if mongo_uri:
            try:
                self.mongo_client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
                self.db = self.mongo_client.get_database("asfilter")
                self.collection = self.db.get_collection("bad_words")
                # Ensure a unique index on the 'word' field for the collection
                if "bad_words" not in self.db.list_collection_names():
                    self.db.create_collection("bad_words")
                self.collection.create_index("word", unique=True)
                logger.info("MongoDB 'bad_words' collection unique index created/verified.")
                
                # MongoDB से additional words लोड करें, अगर कोई हैं
                self._load_additional_bad_words_from_db()

            except ConnectionFailure as e:
                logger.error(f"MongoDB connection failed: {e}. Using default profanity list.")
                self.mongo_client = None
                self.db = None
                self.collection = None
            except OperationFailure as e:
                logger.error(f"MongoDB operation failed (e.g., auth error): {e}. Using default profanity list.")
                self.mongo_client = None
                self.db = None
                self.collection = None
            except Exception as e:
                logger.error(f"An unexpected error occurred during MongoDB initialization: {e}. Using default profanity list.")
                self.mongo_client = None
                self.db = None
                self.collection = None
        else:
            logger.warning("No MongoDB URI provided. Using default profanity list only.")
        
        logger.info(f"Profanity filter initialized with {len(self.bad_words)} bad words.")

    def _load_default_bad_words(self):
        # यहाँ अपनी अपशब्दों की सूची जोड़ें
        default_list = [
            "bhadve", "bsdk", "madarchod", "behenchod", "randi", "saala", "saali", "gaand", "harami", 
            "kutte", "kutte ki aulad", "chutiya", "lund", "chod", "maadarjaat", "bhosdike", 
            "penchod", "mc", "bc", "gaandu", "gand", "chut", "madarchod", "behenchod",
            # और अधिक शब्द यहाँ जोड़ें
        ]
        return set(default_list)

    def _load_additional_bad_words_from_db(self):
        """Loads additional bad words from MongoDB and adds them to the existing set."""
        if self.collection:
            try:
                db_words = [doc['word'] for doc in self.collection.find({}) if 'word' in doc]
                self.bad_words.update(db_words)
                logger.info(f"Loaded {len(db_words)} additional bad words from MongoDB.")
            except Exception as e:
                logger.error(f"Error loading additional bad words from MongoDB: {e}")
        else:
            logger.warning("MongoDB collection not available to load additional bad words.")

    def add_bad_word(self, word: str) -> bool:
        """Adds a bad word to the filter and, if connected, to MongoDB.
        Returns True if added, False if already exists."""
        normalized_word = word.lower().strip()
        if normalized_word not in self.bad_words:
            self.bad_words.add(normalized_word)
            if self.collection: # Agar MongoDB connect hai to wahan bhi add kar do
                try:
                    self.collection.update_one(
                        {"word": normalized_word},
                        {"$set": {"added_at": datetime.utcnow()}},
                        upsert=True
                    )
                    logger.info(f"Added bad word '{normalized_word}' to MongoDB.")
                except Exception as e:
                    logger.error(f"Error adding word '{normalized_word}' to MongoDB: {e}")
            return True
        return False

    def contains_profanity(self, text: str) -> bool:
        if not text:
            return False
        text = text.lower()
        for word in self.bad_words:
            # Use word boundaries to match whole words
            if re.search(r'\b' + re.escape(word) + r'\b', text):
                return True
        return False
