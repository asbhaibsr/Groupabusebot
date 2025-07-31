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
                # 'asfilter' डेटाबेस को गेट करें
                self.db = self.client.get_database("asfilter")
                # 'bad_words' कलेक्शन को गेट करें
                self.bad_words_collection = self.db.get_collection("bad_words")
                # Ensure unique index on 'word' to prevent duplicates
                self.bad_words_collection.create_index("word", unique=True)
                logger.info("MongoDB 'bad_words' collection unique index created/verified.")
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
            # सुनिश्चित करें कि 'word' फ़ील्ड मौजूद है और स्ट्रिंग है
            cursor = self.bad_words_collection.find({"word": {"$type": "string"}})
            for doc in cursor:
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
        if not text: # Handle empty text
            return False
        text_lower = text.lower()
        for word in self.bad_words:
            # Check for whole words to avoid false positives (e.g., "scunthorpe")
            # Using regex with word boundaries might be more robust for production
            if f" {word} " in f" {text_lower} " or text_lower.startswith(f"{word} ") or text_lower.endswith(f" {word}") or text_lower == word:
                return True
        return False

    def add_bad_word(self, word: str) -> bool:
        """MongoDB mein ek naya abusive word jorta hai aur list ko update karta hai."""
        word_lower = word.lower().strip()
        if not word_lower: # Don't add empty strings
            return False

        if word_lower in self.bad_words:
            logger.info(f"Word '{word_lower}' already exists in in-memory list.")
            return False # Already exists in in-memory list

        if self.bad_words_collection:
            try:
                # Insert the word, upsert=True is implicitly handled by unique index and update_one
                # Or use insert_one and handle DuplicateKeyError
                self.bad_words_collection.insert_one({"word": word_lower})
                self.bad_words.append(word_lower) # Add to in-memory list after successful DB insert
                logger.info(f"Added '{word_lower}' to MongoDB and in-memory list.")
                return True
            except Exception as e:
                if "duplicate key error" in str(e):
                    logger.info(f"Word '{word_lower}' already exists in MongoDB (duplicate key error).")
                    if word_lower not in self.bad_words: # Ensure it's in memory even if DB had it
                        self.bad_words.append(word_lower)
                    return False
                else:
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
    # Make sure to set MONGO_DB_URI in your environment variables for production
    filter_instance = ProfanityFilter(mongo_uri=os.getenv("MONGO_DB_URI", "mongodb://localhost:27017/asfilter")) 
    
    print(f"Is 'teri randi' abusive? {filter_instance.contains_profanity('teri randi')}")
    print(f"Is 'hello world' abusive? {filter_instance.contains_profanity('hello world')}")
    print(f"Is 'what a chutiya bot' abusive? {filter_instance.contains_profanity('what a chutiya bot')}")
    print(f"Is 'randi' abusive? {filter_instance.contains_profanity('randi')}")
    print(f"Is 'gandhi' abusive (should be False)? {filter_instance.contains_profanity('gandhi')}") # Test for partial match avoidance

    # Test adding a word
    new_test_word = "nayasabdk"
    if filter_instance.add_bad_word(new_test_word):
        print(f"'{new_test_word}' added. Is it abusive now? {filter_instance.contains_profanity(new_test_word)}")
    else:
        print(f"Failed to add '{new_test_word}' or it already exists.")

    # Test adding an existing word
    if filter_instance.add_bad_word(new_test_word):
        print(f"'{new_test_word}' added again (should be False).")
    else:
        print(f"'{new_test_word}' already exists.")

