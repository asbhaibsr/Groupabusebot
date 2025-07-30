# profanity_filter.py

import os
# from pymongo import MongoClient # Uncomment if fetching bad words from MongoDB

class ProfanityFilter:
    def __init__(self, mongo_uri=None):
        """
        ProfanityFilter ko initialize karta hai.
        Agar MongoDB URI provide kiya gaya hai, toh wahan se gaaliyon ki list load karega.
        """
        self.bad_words = []
        if mongo_uri:
            # self.client = MongoClient(mongo_uri)
            # self.db = self.client.your_database_name # Apne database ka naam yahan dein
            # self.bad_words_collection = self.db.bad_words # Apne collection ka naam yahan dein
            self._load_bad_words_from_db()
        else:
            # Agar MongoDB nahi hai, toh ek default list use karein (testing ke liye)
            self._load_default_bad_words()

    def _load_bad_words_from_db(self):
        """
        MongoDB se gaaliyon ki list load karta hai.
        """
        # Ye placeholder hai. Real code mein MongoDB se fetch karein
        # try:
        #     for doc in self.bad_words_collection.find({}):
        #         self.bad_words.append(doc['word'].lower())
        #     print("Bad words loaded from MongoDB.")
        # except Exception as e:
        #     print(f"Error loading bad words from MongoDB: {e}. Using default list.")
        self.bad_words = ["gaali1", "gaali2", "chutiya", "randi", "behenchod"] # Fallback/Example
            
    def _load_default_bad_words(self):
        """
        Default gaaliyon ki list load karta hai (agar MongoDB configure na ho).
        """
        self.bad_words = [
            "chutiya", "randi", "behenchod", "madarchod", "saala", "kutta", 
            "bhosdike", "harami", "fuck", "shit", "bitch", "asshole", "bastard"
        ]
        print("Default bad words loaded.")

    def contains_profanity(self, text: str) -> bool:
        """
        Check karta hai ki diye gaye text mein koi gaali hai ya nahi.
        """
        text_lower = text.lower()
        for word in self.bad_words:
            if word in text_lower:
                return True
        return False

# Example usage (testing ke liye)
if __name__ == "__main__":
    filter = ProfanityFilter(mongo_uri=os.getenv("MONGO_DB_URI")) 
    
    print(f"Is 'teri randi' abusive? {filter.contains_profanity('teri randi')}")
    print(f"Is 'hello world' abusive? {filter.contains_profanity('hello world')}")
