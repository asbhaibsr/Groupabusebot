import re
import logging
import asyncio
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConnectionFailure, OperationFailure

# Configure logging at the module level for consistency
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
# You can add a handler here if you want to see the logs
# For example:
# handler = logging.StreamHandler()
# formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# handler.setFormatter(formatter)
# logger.addHandler(handler)

class ProfanityFilter:
    """
    An asynchronous profanity filter that uses a default word list and
    can be extended with a MongoDB database for dynamic word management.
    """
    
    def __init__(self, mongo_uri: str = None):
        """
        Initializes the ProfanityFilter.

        Args:
            mongo_uri (str): The MongoDB connection URI. If not provided,
                             only the default list is used.
        """
        self.bad_words = self._load_default_bad_words()
        self.mongo_client = None
        self.db = None
        self.collection = None
        self.mongo_uri = mongo_uri

        if not self.mongo_uri:
            logger.warning("No MongoDB URI provided. Using default profanity list only.")
        else:
            logger.info("MongoDB URI provided. Will attempt to connect asynchronously.")

    async def initialize(self):
        """
        Asynchronously initializes the MongoDB connection and loads words from the database.
        This method must be called after creating the ProfanityFilter instance.
        """
        if not self.mongo_uri:
            return

        try:
            self.mongo_client = AsyncIOMotorClient(self.mongo_uri, serverSelectionTimeoutMS=5000)
            
            # Check connection by calling a server command
            await self.mongo_client.admin.command('ping')
            
            self.db = self.mongo_client.get_database("asfilter")
            self.collection = self.db.get_collection("bad_words")

            # Ensure collection and unique index exist in a robust way
            try:
                # Use await on create_index
                await self.collection.create_index("word", unique=True)
                logger.info("MongoDB 'bad_words' collection unique index created/verified.")
            except OperationFailure as e:
                # This could happen if the index already exists with different options
                logger.warning(f"Could not create index. It may already exist: {e}")
            
            await self._load_additional_bad_words_from_db()
            logger.info(f"Profanity filter initialized with {len(self.bad_words)} bad words.")

        except ConnectionFailure as e:
            logger.error(f"MongoDB connection failed: {e}. Using default profanity list.")
            self.mongo_client = None
            self.db = None
            self.collection = None
        except Exception as e:
            logger.error(f"An unexpected error occurred during MongoDB initialization: {e}. Using default profanity list.")
            self.mongo_client = None
            self.db = None
            self.collection = None
    
    async def shutdown(self):
        """Closes the MongoDB connection gracefully."""
        if self.mongo_client:
            self.mongo_client.close()
            logger.info("MongoDB connection closed.")

    def _load_default_bad_words(self) -> set:
        """
        Loads a comprehensive default list of profanity and its variations.
        """
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
            "whore", "whores", "whoring", "hagees", "aand", "hoes", "hoebag", "hoeski",
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
        
        # A more efficient way to handle variations is to process them once
        # instead of extending the list with redundant variations.
        word_set = set(default_list)
        
        # Create variations of multi-word phrases
        phrase_variations = set()
        for word in word_set:
            if ' ' in word:
                phrase_variations.add(word.replace(' ', ''))
                phrase_variations.add(word.replace(' ', '_'))
                phrase_variations.add(word.replace(' ', '-'))
                phrase_variations.add(word.replace(' ', '.'))
                # Using * as a separator in the regex is a more complex approach,
                # but for simplicity and performance, this is a good start.

        word_set.update(phrase_variations)
        return word_set

    async def _load_additional_bad_words_from_db(self):
        """Asynchronously loads additional bad words from MongoDB and adds them."""
        if not self.collection:
            logger.warning("MongoDB collection not available to load additional bad words.")
            return

        try:
            # Use find to get a cursor, then to_list to fetch all documents
            cursor = self.collection.find({})
            db_words = [doc['word'] for doc in await cursor.to_list(length=None) if 'word' in doc]
            self.bad_words.update(db_words)
            logger.info(f"Loaded {len(db_words)} additional bad words from MongoDB.")
        except Exception as e:
            logger.error(f"Error loading additional bad words from MongoDB: {e}")

    async def add_bad_word(self, word: str) -> bool:
        """
        Asynchronously adds a new bad word to the filter and the MongoDB collection.
        Returns True if the word was added, False otherwise.
        """
        normalized_word = word.lower().strip()
        if not normalized_word:
            return False
            
        if normalized_word in self.bad_words:
            return False

        self.bad_words.add(normalized_word)
        
        if self.collection:
            try:
                # Use update_one with upsert=True to either insert or update
                await self.collection.update_one(
                    {"word": normalized_word},
                    {"$set": {"added_at": datetime.utcnow()}},
                    upsert=True
                )
                logger.info(f"Added bad word '{normalized_word}' to MongoDB.")
            except Exception as e:
                logger.error(f"Error adding word '{normalized_word}' to MongoDB: {e}")
        return True

    def contains_profanity(self, text: str) -> bool:
        """
        Checks if a string contains any profanity from the word list.
        It's a synchronous method as the check is in-memory.
        """
        if not text:
            return False
        
        # Normalize the text once to a single, lowercase, non-punctuated string.
        # This simplifies the regex and improves performance.
        normalized_text = text.lower()
        
        for word in self.bad_words:
            # Create a regex pattern to find the word as a standalone word.
            # This helps avoid the "Scunthorpe problem" (e.g., "ass" in "class").
            pattern = r'\b' + re.escape(word) + r'\b'
            if re.search(pattern, normalized_text):
                return True
        return False
