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
                # यहाँ त्रुटि पकड़ी जा रही थी क्योंकि self.collection को सीधे if में उपयोग किया गया था
                logger.error(f"An unexpected error occurred during MongoDB initialization: {e}. Using default profanity list.")
                self.mongo_client = None
                self.db = None
                self.collection = None
        else:
            logger.warning("No MongoDB URI provided. Using default profanity list only.")
        
        logger.info(f"Profanity filter initialized with {len(self.bad_words)} bad words.")

    def _load_default_bad_words(self):
        # Comprehensive list of profanity in Hindi, English, and variations
        default_list = [
            # Common Hindi profanity and variations
            "bhadve", "bhadwe", "bhadva", "bhadvaa", "bhosdike", "bhosdiwale", "bhosad", "bhosada", 
            "bsdk", "bsdka", "bsdke", "bsdi", "bsdiwale", "bsdiwala", "bsdwala", "bsdwale",
            "madarchod", "madrchod", "madherchod", "maderchod", "madarjaat", "madarjat", "maderjaat",
            "behenchod", "behenchhod", "behenchud", "behenchood", "behenkelode", "behenkelund",
            "randi", "rand", "randiwa", "randikhana", "randikhane", "randi ka", "randi ki",
            "saala", "sala", "saale", "sale", "saali", "sali", "saalya", "salya",
            "gaand", "gand", "gaandu", "gandu", "gaandfat", "gandfat", "gaand mara", "gand mara",
            "harami", "haraami", "haramkhor", "haramkhor", "harami ki aulad",
            "kutte", "kutta", "kutti", "kuttiya", "kutte ka", "kutte ke", "kutte ki aulad",
            "chutiya", "chutia", "chutiye", "chutiyapa", "chut", "choot", "chutad", "chootad",
            "lund", "lund", "laund", "loda", "lode", "loduu", "land", "lauda", "laude",
            "chod", "chhod", "chood", "chud", "chudai", "chudail", "chudasi", "chudwa",
            "penchod", "penchhod", "pencood", "penchud", "pensod",
            "mc", "bc", "bkl", "lodu", "lawde", "lawda", "loda", "lodu",
            "gandu", "gaandu", "gandfat", "gaandfat", "gandmasti", "gaandmasti",
            "chakke", "chakka", "hijda", "hijde", "hijra", "hijre",
            "nautankibaaz", "nautanki", "natakbaaz", "natak",
            "kamine", "kaminey", "kamina", "kamini",
            
            # English profanity and variations
            "fuck", "fucker", "fucking", "motherfucker", "motherfucking", "fuckface", "fuckboy", 
            "fuckgirl", "fuckoff", "fuckyou", "fuck u", "fuk", "fuking", "fuker", "fucc", "fucck",
            "shit", "shite", "shithead", "shitter", "bullshit", "shitface", "shitbag", "shitty",
            "asshole", "ass", "arse", "arsehole", "asshat", "asswipe", "assclown", "asslicker",
            "bitch", "bitches", "bitching", "bitchy", "biatch", "bich", "beetch", "bitchass",
            "bastard", "bastards", "basted", "bastid", "basterd", "basturd",
            "dick", "dickhead", "dickface", "dickwad", "dickweed", "dickbag", "dickish", "dickless",
            "pussy", "pussies", "pusy", "puzzy", "pussi", "pusi", "pussie",
            "cunt", "cunts", "cuntface", "cunty", "cuntbag", "cuntish", "cunthead",
            "whore", "whores", "whoring", "ho", "hoe", "hoes", "hoebag", "hoeski",
            "slut", "sluts", "slutty", "slutbag", "slutface", "slutshaming", "slutwalk",
            "cock", "cocks", "cocky", "cockface", "cockhead", "cocksucker", "cockwomble",
            "wanker", "wank", "wanking", "wankered", "wankstain", "wanky", "wankjob",
            "twat", "twats", "twatty", "twatwaffle", "twatface", "twathead", "twatish",
            
            # Mixed/Hinglish profanity
            "fuck bhenchod", "bhenchod fuck", "madarchod fuck", "fuck madarchod",
            "bhosdiwala fuck", "fuck bhosdiwala", "randi ka bacha", "randi ki aulad",
            "chutiya fuck", "fuck chutiya", "lund chus", "gaand mara", "ass gaand",
            "bitch saali", "saali bitch", "whore randi", "randi whore",
            
            # Common abbreviations and number substitutions
            "fck", "fcuk", "fuk", "fku", "f*ck", "f**k", "f***", "f##k", "f00k",
            "sh1t", "sh!t", "sht", "s**t", "sh*t", "sh**", "sh##", "sh00t",
            "b1tch", "b!tch", "btch", "b**ch", "b*tch", "bi*ch", "b00ch",
            "a55", "a$$", "a**", "a*s", "@$$", "@**", "@ss", "a55hole",
            "d1ck", "d!ck", "dck", "d**k", "d*ck", "di*k", "d00k",
            "p0rn", "pr0n", "p*rn", "p**n", "p00n", "p0rn", "prn",
            
            # Creative misspellings and variations
            "phuck", "phuk", "phacker", "phucker", "phucc", "phucck",
            "sheeet", "shiet", "shytt", "shite", "shyte", "shitt",
            "beech", "beotch", "biyotch", "biznitch", "bizatch", "bizzle",
            "azz", "azzhole", "azzh0le", "azzhole", "@zz", "@zzh0le",
            "dikk", "dikkhead", "dikkhed", "dikhed", "dikhead", "dikhed",
            "kunt", "qunt", "cwnt", "c*nt", "c**t", "c00nt", "k00nt",
            
            # Reversed words
            "kcuf", "tihs", "hctib", "kcid", "yssip", "tnuc", "erohw", "tuls", "kcoj",
            "odhcab", "odhcam", "odhceb", "odhcram", "odhcuf", "odhcus", "odhcut",
            
            # Common phrases
            "teri maa ki chut", "teri maa ka bhosda", "maa chuda", "behen ka loda",
            "bhosdi ke", "gaand mein dam", "lund lele", "chut marike",
            "fuck off", "fuck you", "go to hell", "screw you", "suck my dick",
            "lick my ass", "kiss my ass", "eat shit", "shit happens", "bull shit",
            
            # Regional variations
            "lauda", "laude", "laudo", "lawda", "lawde", "lawdo", "loda", "lode", "lodo",
            "chodu", "choda", "chode", "chodi", "chodu", "choddi", "chodke",
            "gandu", "gando", "gandi", "gand", "gaand", "gandfat", "gandmasti",
            "bhenchod", "bhenchhod", "bhenchud", "bhenchood", "bhenkelode",
            
            # Add more as needed
            "sucker", "loser", "idiot", "moron", "retard", "dumbass", "stupid",
            "jerk", "scumbag", "douche", "douchebag", "pig", "swine", "animal",
            "dog", "swear", "abuse", "badword", "gaali", "gali", "abusive"
        ]
        
        # Add variations with spaces replaced by special characters
        additional_variations = []
        for word in default_list:
            if ' ' in word:
                additional_variations.append(word.replace(' ', ''))
                additional_variations.append(word.replace(' ', '_'))
                additional_variations.append(word.replace(' ', '-'))
                additional_variations.append(word.replace(' ', '.'))
                additional_variations.append(word.replace(' ', '*'))
        
        default_list.extend(additional_variations)
        
        return set(default_list)

    def _load_additional_bad_words_from_db(self):
        """Loads additional bad words from MongoDB and adds them to the existing set."""
        if self.collection is not None: 
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
            if self.collection is not None: # Agar MongoDB connect hai to wahan bhi add kar do
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
