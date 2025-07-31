import os
from pymongo import MongoClient
import logging

logger = logging.getLogger(__name__)

class ProfanityFilter:
    def __init__(self, mongo_uri=None):
        self.bad_words = []
        self.client = None
        self.db = None
        self.bad_words_collection = None

        if mongo_uri:
            try:
                self.client = MongoClient(mongo_uri)
                self.db = self.client.get_database("asfilter")
                self.bad_words_collection = self.db.get_collection("bad_words")
                self._load_bad_words_from_db()
            except Exception as e:
                logger.error(f"Error connecting to MongoDB or loading bad words: {e}. Using default list.")
                self._load_default_bad_words()
        else:
            logger.warning("MONGO_DB_URI not provided. Using default bad words list.")
            self._load_default_bad_words()

    def _load_bad_words_from_db(self):
        try:
            self.bad_words = [] 
            cursor = self.bad_words_collection.find({})
            for doc in cursor:
                if 'word' in doc and isinstance(doc['word'], str):
                    self.bad_words.append(doc['word'].lower())
            logger.info(f"Bad words loaded from MongoDB: {len(self.bad_words)} words.")
            if not self.bad_words:
                logger.warning("WARNING: No bad words loaded from MongoDB. Is the collection empty or 'word' field missing?")
        except Exception as e:
            logger.error(f"Error loading bad words from MongoDB: {e}. Using default list.")
            self._load_default_bad_words()
            
    def _load_default_bad_words(self):
        self.bad_words = [
            "chutiya", "randi", "behenchod", "madarchod", "saala", "kutta", 
            "bhosdike", "harami", "fuck", "shit", "bitch", "asshole", "bastard"
        ]
        logger.info(f"Default bad words loaded: {len(self.bad_words)} words.")

    def contains_profanity(self, text: str) -> bool:
        text_lower = text.lower()
        for word in self.bad_words:
            if word in text_lower:
                return True
        return False

    def add_bad_word(self, word: str) -> bool:
        """MongoDB mein ek naya abusive word jorta hai aur list ko update karta hai."""
        word_lower = word.lower()
        if word_lower in self.bad_words:
            return False # Already exists

        if self.bad_words_collection:
            try:
                if self.bad_words_collection.count_documents({"word": word_lower}) == 0:
                    self.bad_words_collection.insert_one({"word": word_lower})
                    self.bad_words.append(word_lower)
                    logger.info(f"Added '{word_lower}' to MongoDB and in-memory list.")
                    return True
                else:
                    logger.info(f"Word '{word_lower}' already exists in MongoDB.")
                    return False
            except Exception as e:
                logger.error(f"Error adding word '{word_lower}' to MongoDB: {e}")
                return False
        else:
            logger.warning("MongoDB connection not available. Cannot add word to DB. Adding to in-memory list only.")
            if word_lower not in self.bad_words:
                self.bad_words.append(word_lower)
                return True
            return False

if __name__ == "__main__":
    # Test with a dummy MongoDB URI or ensure MONGO_DB_URI is set in environment
    filter = ProfanityFilter(mongo_uri=os.getenv("MONGO_DB_URI", "mongodb://localhost:27017/asfilter")) 
    
    print(f"Is 'teri randi' abusive? {filter.contains_profanity('teri randi')}")
    print(f"Is 'hello world' abusive? {filter.contains_profanity('hello world')}")
    print(f"Is 'what a chutiya bot' abusive? {filter.contains_profanity('what a chutiya bot')}")

    # Test adding a word
    new_word = "testgaali"
    if filter.add_bad_word(new_word):
        print(f"'{new_word}' added. Is it abusive now? {filter.contains_profanity(new_word)}")
    else:
        print(f"Failed to add '{new_word}' or it already exists.")

    # Test adding an existing word
    if filter.add_bad_word(new_word):
        print(f"'{new_word}' added again (should be False).")
    else:
        print(f"'{new_word}' already exists.")
