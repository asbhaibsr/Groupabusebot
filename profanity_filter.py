import os
from pymongo import MongoClient

class ProfanityFilter:
    def __init__(self, mongo_uri=None):
        """
        ProfanityFilter ko initialize karta hai.
        Agar MongoDB URI provide kiya gaya hai, toh wahan se gaaliyon ki list load karega.
        """
        self.bad_words = []
        if mongo_uri:
            try:
                self.client = MongoClient(mongo_uri)
                # !! IMPORTANT: Apne database ka naam yahan dein (e.g., "mydatabase")
                self.db = self.client.get_database("asfilter") # <-- APNE DATABASE KA NAAM YAHAN DALEN
                # !! IMPORTANT: Apne collection ka naam yahan dein (e.g., "profane_words")
                self.bad_words_collection = self.db.get_collection("bad_words") # <-- APNE COLLECTION KA NAAM YAHAN DALEN
                self._load_bad_words_from_db()
            except Exception as e:
                print(f"Error connecting to MongoDB or loading bad words: {e}. Using default list.")
                self._load_default_bad_words()
        else:
            self._load_default_bad_words()

    def _load_bad_words_from_db(self):
        """
        MongoDB se gaaliyon ki list load karta hai.
        """
        try:
            # सुनिश्चित करें कि आपके collection में documents में 'word' field है
            # उदाहरण के लिए, आपके कलेक्शन में डॉक्यूमेंट्स ऐसे हो सकते हैं: {"word": "chutiya"}
            cursor = self.bad_words_collection.find({})
            for doc in cursor:
                if 'word' in doc and isinstance(doc['word'], str):
                    self.bad_words.append(doc['word'].lower())
            print(f"Bad words loaded from MongoDB: {len(self.bad_words)} words.")
            if not self.bad_words: # If no words loaded from DB, log a warning
                print("WARNING: No bad words loaded from MongoDB. Is the collection empty or 'word' field missing?")
        except Exception as e:
            print(f"Error loading bad words from MongoDB: {e}. Using default list.")
            self._load_default_bad_words() # Fallback to default if DB load fails
            
    def _load_default_bad_words(self):
        """
        Default gaaliyon ki list load karta hai (agar MongoDB configure na ho).
        """
        self.bad_words = [
            "chutiya", "randi", "behenchod", "madarchod", "saala", "kutta", 
            "bhosdike", "harami", "fuck", "shit", "bitch", "asshole", "bastard"
        ]
        print(f"Default bad words loaded: {len(self.bad_words)} words.")

    def contains_profanity(self, text: str) -> bool:
        """
        Check karta hai ki diye गए text mein koi gaali hai ya nahi.
        """
        text_lower = text.lower()
        for word in self.bad_words:
            # Simple 'in' check. For more robust filtering (e.g., avoiding 'ass' in 'class'),
            # you might need regular expressions with word boundaries.
            if word in text_lower:
                return True
        return False

# Example usage (testing ke liye)
if __name__ == "__main__":
    # जब आप इसे सीधे रन करते हैं, तो MONGO_DB_URI को सेट करना होगा
    # उदाहरण: export MONGO_DB_URI="mongodb+srv://user:pass@cluster.mongodb.net/mydatabase?retryWrites=true&w=majority"
    filter = ProfanityFilter(mongo_uri=os.getenv("MONGO_DB_URI")) 
    
    print(f"Is 'teri randi' abusive? {filter.contains_profanity('teri randi')}")
    print(f"Is 'hello world' abusive? {filter.contains_profanity('hello world')}")
    print(f"Is 'what a chutiya bot' abusive? {filter.contains_profanity('what a chutiya bot')}")
