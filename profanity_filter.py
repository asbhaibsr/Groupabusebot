import re
import logging
import asyncio
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConnectionFailure, OperationFailure

logger = logging.getLogger(__name__)

class ProfanityFilter:
    def __init__(self, mongo_uri=None):
        self.bad_words = self._load_default_bad_words()
        self.mongo_client = None
        self.db = None
        self.collection = None
        self.mongo_uri = mongo_uri

        if self.mongo_uri:
            pass
        else:
            logger.warning("No MongoDB URI provided. Using default profanity list only.")

        logger.info(f"Profanity filter initialized with {len(self.bad_words)} bad words.")

    async def init_async_db(self):
        """Asynchronously initializes the MongoDB connection and loads words."""
        if not self.mongo_uri:
            return

        try:
            self.mongo_client = AsyncIOMotorClient(self.mongo_uri, serverSelectionTimeoutMS=5000)
            self.db = self.mongo_client.get_database("asfilter")
            self.collection = self.db.get_collection("bad_words")

            collection_names = await self.db.list_collection_names()
            if "bad_words" not in collection_names:
                await self.db.create_collection("bad_words")
                logger.info("MongoDB 'bad_words' collection created.")
            
            await self.collection.create_index("word", unique=True)
            logger.info("MongoDB 'bad_words' collection unique index created/verified.")
            
            await self._load_additional_bad_words_from_db()

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

    def _load_default_bad_words(self):
        # MASSIVE comprehensive list of profanity in Hindi, English, and all variations
        default_list = [
            # ===== CORE HINDI PROFANITY =====
            "bhadve", "bhadwe", "bhadva", "bhadvaa", "bhadvon", "bhadvonka",
            "bhosdike", "bhosdiwale", "bhosad", "bhosada", "bhosdi", "bhosdika",
            "bhosdike", "bhosdiwala", "bhosadpappu", "bhosadpappu",
            "bsdk", "bsdka", "bsdke", "bsdi", "bsdiwale", "bsdiwala", "bsdwala",
            "bsdwale", "bsdki", "bsdko",
            "madarchod", "madrchod", "madherchod", "maderchod", "madarjaat",
            "madarjat", "maderjaat", "madarch*d", "madrch*d", "maderch*d",
            "behenchod", "behenchhod", "behenchud", "behenchood", "behenkelode",
            "behenkelund", "behench*d", "behnchod", "bhenchod", "bhench*d",
            "randi", "rand", "randiwa", "randikhana", "randikhane", "randi ka",
            "randi ki", "randibaaz", "randipana", "randi_pana",
            "saala", "sala", "saale", "sale", "saali", "sali", "saalya", "salya",
            "saale_kutte", "saali_kutiya",
            "gaand", "gand", "gaandu", "gandu", "gaandfat", "gandfat", "gaand mara",
            "gand mara", "gaandmasti", "gandmasti", "gaand_me_dum", "gand_me_dum",
            "harami", "haraami", "haramkhor", "haramkhor", "harami ki aulad",
            "haramzada", "haramzadi", "haramkhor", "haramkhori",
            "kutte", "kutta", "kutti", "kuttiya", "kutte ka", "kutte ke",
            "kutte ki aulad", "kutteki_aulad", "kutiya_ki_aulad",
            "chutiya", "chutia", "chutiye", "chutiyapa", "chut", "choot", "chutad",
            "chootad", "chutiyapanti", "chutiyagiri", "chutiya_giri",
            "lund", "laund", "loda", "lode", "loduu", "land", "lauda", "laude",
            "lund_chus", "lund_chusa", "lund_kha", "lund_le",
            "chod", "chhod", "chood", "chud", "chudai", "chudail", "chudasi",
            "chudwa", "chudwayega", "chudwaunga", "chudwana", "chudwane",
            "penchod", "penchhod", "pencood", "penchud", "pensod",
            "mc", "bc", "bkl", "lodu", "lawde", "lawda", "loda", "lodu",
            "gandu", "gaandu", "gandfat", "gaandfat", "gandmasti", "gaandmasti",
            "chakke", "chakka", "hijda", "hijde", "hijra", "hijre", "hijde",
            "kamine", "kaminey", "kamina", "kamini", "kamina_pan", "kaminepan",

            # ===== ENGLISH PROFANITY =====
            "fuck", "fucker", "fucking", "motherfucker", "motherfucking", "fuckface",
            "fuckboy", "fuckgirl", "fuckoff", "fuckyou", "fuck u", "fuk", "fuking",
            "fuker", "fucc", "fucck", "fukk", "fukka", "fukker",
            "shit", "shite", "shithead", "shitter", "bullshit", "shitface", "shitbag",
            "shitty", "shitt", "shite", "shittiest", "shittier",
            "asshole", "ass", "arse", "arsehole", "asshat", "asswipe", "assclown",
            "asslicker", "ass_kisser", "assface", "assbag",
            "bitch", "bitches", "bitching", "bitchy", "biatch", "bich", "beetch",
            "bitchass", "bitchy", "bitchslap",
            "bastard", "bastards", "basted", "bastid", "basterd", "basturd", "bastardo",
            "dick", "dickhead", "dickface", "dickwad", "dickweed", "dickbag", "dickish",
            "dickless", "dicklicker", "dick_for_brains",
            "pussy", "pussies", "pusy", "puzzy", "pussi", "pusi", "pussie", "pussyhole",
            "cunt", "cunts", "cuntface", "cunty", "cuntbag", "cuntish", "cunthead",
            "whore", "whores", "whoring", "hagees", "aand", "hoes", "hoebag", "hoeski",
            "slut", "sluts", "slutty", "slutbag", "slutface", "slutshaming", "slutwalk",
            "cock", "cocks", "cocky", "cockface", "cockhead", "cocksucker", "cockwomble",
            "wanker", "wank", "wanking", "wankered", "wankstain", "wanky", "wankjob",
            "twat", "twats", "twatty", "twatwaffle", "twatface", "twathead", "twatish",

            # ===== HINGLISH MIXED =====
            "fuck bhenchod", "bhenchod fuck", "madarchod fuck", "fuck madarchod",
            "bhosdiwala fuck", "fuck bhosdiwala", "randi ka bacha", "randi ki aulad",
            "chutiya fuck", "fuck chutiya", "lund chus", "gaand mara", "ass gaand",
            "bitch saali", "saali bitch", "whore randi", "randi whore",

            # ===== ABBREVIATIONS & NUMBER SUBSTITUTIONS =====
            "fck", "fcuk", "fuk", "fku", "f*ck", "f**k", "f***", "f##k", "f00k",
            "sh1t", "sh!t", "sht", "s**t", "sh*t", "sh**", "sh##", "sh00t",
            "b1tch", "b!tch", "btch", "b**ch", "b*tch", "bi*ch", "b00ch",
            "a55", "a55h0l3", "a$$", "a**", "a*s", "@$$", "@**", "@ss", "a55hole",
            "d1ck", "d!ck", "dck", "d**k", "d*ck", "di*k", "d00k",
            "p0rn", "pr0n", "p*rn", "p**n", "p00n", "p0rn", "prn",
            "m0therfucker", "m0th3rfucker", "mthrfcker", "mthr_fckr",
            "b3h3nch0d", "b3hench0d", "bhench0d", "behench0d",
            "madarch0d", "m4d4rch0d", "m4darch0d", "madrch0d",

            # ===== CREATIVE MISSPELLINGS =====
            "phuck", "phuk", "phacker", "phucker", "phucc", "phucck", "phukk",
            "sheeet", "shiet", "shytt", "shite", "shyte", "shitt", "shyte",
            "beech", "beotch", "biyotch", "biznitch", "bizatch", "bizzle", "bytch",
            "azz", "azzhole", "azzh0le", "azzhole", "@zz", "@zzh0le", "@sshole",
            "dikk", "dikkhead", "dikkhed", "dikhed", "dikhead", "dikhed", "dicc",
            "kunt", "qunt", "cwnt", "c*nt", "c**t", "c00nt", "k00nt", "c_nt",
            "phaggot", "faggit", "faggitt", "fagot", "fagget", "faggit",

            # ===== REVERSED WORDS =====
            "kcuf", "tihs", "hctib", "kcid", "yssip", "tnuc", "erohw", "tuls", "kcoj",
            "odhcab", "odhcam", "odhceb", "odhcram", "odhcuf", "odhcus", "odhcut",
            "evird", "kcilc", "kcilb", "kcilf", "kcils", "kcilw", "kcilg",

            # ===== COMMON PHRASES =====
            "teri maa ki chut", "teri maa ka bhosda", "maa chuda", "behen ka loda",
            "bhosdi ke", "gaand mein dam", "lund lele", "chut marike",
            "fuck off", "fuck you", "go to hell", "screw you", "suck my dick",
            "lick my ass", "kiss my ass", "eat shit", "shit happens", "bull shit",
            "bhen k lode", "maa k lode", "chut k dhakkan", "gaand k dhakkan",

            # ===== REGIONAL VARIATIONS =====
            "lauda", "laude", "laudo", "lawda", "lawde", "lawdo", "loda", "lode", "lodo",
            "chodu", "choda", "chode", "chodi", "chodu", "choddi", "chodke", "chodh",
            "gandu", "gando", "gandi", "gand", "gaand", "gandfat", "gandmasti",
            "bhenchod", "bhenchhod", "bhenchud", "bhenchood", "bhenkelode",
            "bhenkelund", "bhenkilodi", "bhenkilora",

            # ===== URDU/ISLAMIC SLANG =====
            "haramzada", "haramzadi", "haramkhor", "haramkhori", "haram ki aulad",
            "kamina", "kamine", "kaminey", "kamina_pan", "kaminepan", "kamini",

            # ===== SOUTH INDIAN SLANG =====
            "punda", "pundai", "mayir", "mayiru", "poolu", "pooley", "kunji",
            "thevdiya", "thevdiyaa", "thevdiyapaya", "thevdiyapaiya", "thevdiyapulla",

            # ===== CREATIVE COMBINATIONS =====
            "lundtop", "chuttop", "gandtop", "bhosdatop", "madartop", "behntop",
            "gand_mara", "gaand_mara", "lund_chus", "chut_marani", "bhosdi_ke",
            "mother_lover", "sister_fucker", "brother_fucker", "father_fucker",

            # ===== SYMBOL & NUMBER VARIATIONS =====
            "f_u_c_k", "f-u-c-k", "f.u.c.k", "f@ck", "f#ck", "f$ck", "f%ck", "f&ck",
            "sh!t", "sh1t", "sh1tty", "sh1thead", "sh1tbag", "sh1tfaced",
            "b1tch", "b!tch", "b1tchy", "b1tches", "b1tchface", "b1tchass",
            "a55", "a55h0le", "a55h0l3", "a55wipe", "a55hat", "a55clown",
            "d1ck", "d!ck", "d1ckhead", "d1ckface", "d1ckwad", "d1ckweed",
            "c0ck", "c0cksucker", "c0ckhead", "c0ckface", "c0cky",
            "p0rn", "pr0n", "p0rnstar", "pr0nstar", "p0rnhub", "pr0nhub",

            # ===== START/END VARIATIONS =====
            "hase_gandu", "start_gandu", "0_gandu", "o_gandu", "gandu_hase",
            "hase_bhosdi", "start_bhosdi", "0_bhosdi", "o_bhosdi", "bhosdi_hase",
            "hase_chutiya", "start_chutiya", "0_chutiya", "o_chutiya", "chutiya_hase",
            "hase_madar", "start_madar", "0_madar", "o_madar", "madar_hase",
            "hase_lund", "start_lund", "0_lund", "o_lund", "lund_hase",

            # ===== ULTE-SIDHE FLIPPY WORDS =====
            "uʞɔnɟ", "ʇıɥs", "ɥɔʇıq", "ʞɔıp", "ʎssnd", "ʇnnu", "ʍoɹɥʍ", "ʇnls",
            "ʎɐʇʇɐq", "ɐqɐɯ", "ɐɹɐʇsɐq", "ɐɹɐʇsɐq", "ɐɹɐʇsɐq", "ɐɹɐʇsɐq",
            "ɐɹɐʇsɐq", "ɐɹɐʇsɐq", "ɐɹɐʇsɐq", "ɐɹɐʇsɐq", "ɐɹɐʇsɐq",

            # ===== EMOTICON/ASCII VARIATIONS =====
            "8==D", "8===D", "8====D", "8=====D", "8======D",
            "(.)(.)", "( . Y . )", "( o Y o )", "( . ) ( . )",
            "(_!_)", "(_|_)", "(_o_)", "(_O_)", "(_0_)",

            # ===== COMMON INSULTS =====
            "sucker", "loser", "idiot", "moron", "retard", "dumbass", "stupid",
            "jerk", "scumbag", "douche", "douchebag", "pig", "swine", "animal",
            "dog", "swear", "abuse", "badword", "gaali", "gali", "abusive",
            "nigga", "nigger", "negro", "cracker", "honkey", "spic", "chink",
            "gook", "kike", "wop", "dago", "kyke", "heeb", "mick", "paddy",
            "turd", "turdface", "turdbrain", "turdhead", "turdlicker",
            "scrotum", "scrot", "scrote", "scrotface", "nutjob", "nutcase",
            "wanksta", "wankster", "wankjob", "wanktard", "wankshaft",
            "cumdumpster", "cumdump", "cumslut", "cumwhore", "cumface",
            "jizz", "jizzface", "jizzhead", "jizzbag", "jizzstain",
            "spunk", "spunkface", "spunkhead", "spunkstain", "spunkdumpster",
            "tosser", "tosspot", "tossbag", "tossface", "tosshead",
            "prick", "prickhead", "prickface", "prickwad", "prickweed",
            "knob", "knobhead", "knobface", "knobend", "knobjockey",
            "bellend", "bellendhead", "bellendface", "bellendwad",
            "fanny", "fannyhead", "fannyface", "fannywad", "fannybandit",
            "minge", "mingehead", "mingeface", "mingewad", "mingebag",
            "berk", "berkhead", "berkface", "berkwad", "berkbrain",
            "plonker", "plonkhead", "plonkface", "plonkwad", "plonkbrain",
            "git", "gitt", "githead", "gitface", "gitwad", "gitbrain",
            "pillock", "pillockhead", "pillockface", "pillockwad", "pillockbrain",
            "numpty", "numptyhead", "numptyface", "numptywad", "numptybrain",
            "muppet", "muppethead", "muppetface", "muppetwad", "muppetbrain",
            "twit", "twithead", "twitface", "twitwad", "twitbrain",
            "nonce", "noncehead", "nonceface", "noncewad", "noncebrain",
            "gobshite", "gobshit", "gobshitehead", "gobshiteface",
            "arsebandit", "arsewipe", "arsehead", "arseface", "arseclown",
            "bollocks", "bollock", "bollockhead", "bollockface", "bollockbrain",
            "bugger", "buggerhead", "buggerface", "buggerwad", "buggerbrain",
            "bloody", "bloodyhell", "bloodynora", "bloodyhell", "bloodyhell",
            "sod", "sodoff", "sodhead", "sodface", "sodbrain", "sodding",
            "blimey", "blimeyhell", "blimeynora", "blimeyhell", "blimeyhell",
            "crikey", "crikeyhell", "crikeynora", "crikeyhell", "crikeyhell",
            "cripes", "cripeshell", "cripesnora", "cripeshell", "cripeshell",
            "gordonbennett", "gordonbennetthead", "gordonbennettface",
            "streuth", "streuthhead", "streuthface", "streuthwad", "streuthbrain",
            "blighter", "blighterhead", "blighterface", "blighterwad", "blighterbrain",
            "bounder", "bounderhead", "bounderface", "bounderwad", "bounderbrain",
            "cad", "cadhead", "cadface", "cadwad", "cadbrain", "caddish",
            "rotter", "rotterhead", "rotterface", "rotterwad", "rotterbrain",
            "scoundrel", "scoundrelhead", "scoundrelface", "scoundrelwad", "scoundrelbrain",
            "blackguard", "blackguardhead", "blackguardface", "blackguardwad", "blackguardbrain",
            "neerdowell", "neerdowellhead", "neerdowellface", "neerdowellwad", "neerdowellbrain",
            "goodfornothing", "goodfornothinghead", "goodfornothingface",
            "wastrel", "wastrelhead", "wastrelface", "wastrelwad", "wastrelbrain",
            "layabout", "layabouthead", "layaboutface", "layaboutwad", "layaboutbrain",
            "loafer", "loaferhead", "loaferface", "loaferwad", "loaferbrain",
            "slacker", "slackerhead", "slackerface", "slackerwad", "slackerbrain",
            "shirker", "shirkerhead", "shirkerface", "shirkerwad", "shirkerbrain",
            "skiver", "skiverhead", "skiverface", "skiverwad", "skiverbrain",
            "malingerer", "malingererhead", "malingererface", "malingererwad", "malingererbrain",
            "goldbricker", "goldbrickerhead", "goldbrickerface", "goldbrickerwad", "goldbrickerbrain",
            "sluggard", "sluggardhead", "sluggardface", "sluggardwad", "sluggardbrain",
            "slugabed", "slugabedhead", "slugabedface", "slugabedwad", "slugabedbrain",
            "drone", "dronehead", "droneface", "dronewad", "dronebrain",
            "idler", "idlerhead", "idlerface", "idlerwad", "idlerbrain",
            "dawdler", "dawdlerhead", "dawdlerface", "dawdlwad", "dawdlerbrain",
            "laggard", "laggardhead", "laggardface", "laggardwad", "laggardbrain",
            "slowcoach", "slowcoachhead", "slowcoachface", "slowcoachwad", "slowcoachbrain",
            "stickinthemud", "stickinthemudhead", "stickinthemudface",
            "fuddy-duddy", "fuddyduddy", "fuddy-duddyhead", "fuddy-duddyface",
            "oldfuddy-duddy", "oldfuddyduddy", "oldfuddy-duddyhead", "oldfuddy-duddyface",
            "fogey", "fogeyhead", "fogeyface", "fogeywad", "fogeybrain", "oldfogey",
            "fossil", "fossilhead", "fossilface", "fossilwad", "fossilbrain", "oldfossil",
            "relic", "relichead", "relicface", "relicwad", "relicbrain", "oldrelic",
            "dinosaur", "dino", "dinohead", "dinoface", "dinowad", "dinobrain", "olddinosaur",
            "antiquated", "antiquatedhead", "antiquatedface", "antiquatedwad", "antiquatedbrain",
            "obsolete", "obsoletehead", "obsoleteface", "obsoletewad", "obsoletebrain",
            "outmoded", "outmodedhead", "outmodedface", "outmodedwad", "outmodedbrain",
            "outdated", "outdatedhead", "outdatedface", "outdatedwad", "outdatedbrain",
            "superannuated", "superannuatedhead", "superannuatedface", "superannuatedwad", "superannuatedbrain",
            "antediluvian", "antediluvianhead", "antediluvianface", "antediluvianwad", "antediluvianbrain",
            "medieval", "medievalhead", "medievalface", "medievalwad", "medievalbrain",
            "primitive", "primitivehead", "primitiveface", "primitivewad", "primitivebrain",
            "primeval", "primevalhead", "primevalface", "primevalwad", "primevalbrain",
            "ancient", "ancienthead", "ancientface", "ancientwad", "ancientbrain",
            "archaic", "archaichead", "archaicface", "archaicwad", "archaicbrain",
            "bygone", "bygonehead", "bygoneface", "bygonewad", "bygonebrain",
            "passé", "passe", "passéhead", "passehead", "passéface", "passeface",
            "old-hat", "oldhat", "old-hathead", "oldhathead", "old-hatface", "oldhatface",
            "behindthetimes", "behindthetimeshead", "behindthetimesface",
            "outoftouch", "outoftouchhead", "outoftouchface",
            "outofdate", "outofdatehead", "outofdateface",
            "outofstep", "outofstephead", "outofstepface",
            "outofsync", "outofsynchead", "outofsyncface",
            "outofline", "outlinehead", "outlineface",
            "outoforder", "outoforderhead", "outoforderface",
            "outofwhack", "outofwhackhead", "outofwhackface",
            "outofkilter", "outofkilterhead", "outofkilterface",
            "outofjoint", "outofjointhead", "outofjointface",
            "outofsorts", "outofsortshead", "outofsortsface",
            "outoffashion", "outoffashionhead", "outoffashionface",
            "outofstyle", "outofstylehead", "outofstyleface",
            "outofvogue", "outofvoguehead", "outofvogueface",
            "outofseason", "outofseasonhead", "outofseasonface",
            "outofprint", "outofprinthead", "outofprintface",
            "outofstock", "outofstockhead", "outofstockface",
            "outofsupply", "outofsupplyhead", "outofsupplyface",
            "outofcirculation", "outofcirculationhead", "outofcirculationface",
            "outofcommission", "outofcommissionhead", "outofcommissionface",
            "outofservice", "outofservicehead", "outofserviceface",
            "outofaction", "outofactionhead", "outofactionface",
            "outofplay", "outofplayhead", "outofplayface",
            "outofbounds", "outofboundshead", "outofboundsface",
            "outofreach", "outofreachhead", "outofreachface",
            "outofsight", "outofsighthead", "outofsightface",
            "outofmind", "outofmindhead", "outofmindface",
            "outofcontrol", "outofcontrolhead", "outofcontrolface",
            "outofhand", "outofhandhead", "outofhandface",
            "outofpocket", "outofpockethead", "outofpocketface",
            "outofpocket", "outofpockethead", "outofpocketface",
            "outofthequestion", "outofthequestionhead", "outofthequestionface",
            "outoftheordinary", "outoftheordinaryhead", "outoftheordinaryface",
            "outoftheway", "outofthewayhead", "outofthewayface",
            "outofthewoods", "outofthewoodshead", "outofthewoodsface",
            "outoftheblue", "outofthebluehead", "outoftheblueface",
            "outofthebox", "outoftheboxhead", "outoftheboxface",
            "outofthecloset", "outoftheclosethead", "outoftheclosetface",
            "outoftheloop", "outoftheloophhead", "outoftheloopface",
            "outofthepicture", "outofthepicturehead", "outofthepictureface",
            "outofthequestion", "outofthequestionhead", "outofthequestionface",
            "outoftheordinary", "outoftheordinaryhead", "outoftheordinaryface",
            "outoftheway", "outofthewayhead", "outofthewayface",
            "outofthewoods", "outofthewoodshead", "outofthewoodsface",
            "outoftheblue", "outofthebluehead", "outoftheblueface",
            "outofthebox", "outoftheboxhead", "outoftheboxface",
            "outofthecloset", "outoftheclosethead", "outoftheclosetface",
            "outoftheloop", "outoftheloophhead", "outoftheloopface",
            "outofthepicture", "outofthepicturehead", "outofthepictureface"
        ]
        
        # Generate additional variations (spaces, underscores, hyphens, etc.)
        additional_variations = []
        for word in default_list:
            if ' ' in word:
                additional_variations.extend([
                    word.replace(' ', ''),
                    word.replace(' ', '_'),
                    word.replace(' ', '-'),
                    word.replace(' ', '.'),
                    word.replace(' ', '*'),
                    word.replace(' ', '0'),
                    word.replace(' ', 'o'),
                    word.replace(' ', '@'),
                    word.replace(' ', '#'),
                    word.replace(' ', '$'),
                    word.replace(' ', '%'),
                    word.replace(' ', '&'),
                    word.replace(' ', '+'),
                    word.replace(' ', '='),
                    word.replace(' ', '!'),
                    word.replace(' ', '?'),
                    word.replace(' ', '~'),
                    word.replace(' ', '`'),
                    word.replace(' ', '|'),
                    word.replace(' ', '\\'),
                    word.replace(' ', '/'),
                    word.replace(' ', ':'),
                    word.replace(' ', ';'),
                    word.replace(' ', '<'),
                    word.replace(' ', '>'),
                    word.replace(' ', '"'),
                    word.replace(' ', "'"),
                    word.replace(' ', '('),
                    word.replace(' ', ')'),
                    word.replace(' ', '['),
                    word.replace(' ', ']'),
                    word.replace(' ', '{'),
                    word.replace(' ', '}'),
                ])
        
        # Generate leet speak variations
        leet_variations = []
        leet_map = {
            'a': '@', 'e': '3', 'i': '1', 'o': '0', 's': '$', 't': '7', 'l': '1',
            'A': '@', 'E': '3', 'I': '1', 'O': '0', 'S': '$', 'T': '7', 'L': '1'
        }
        
        for word in default_list:
            leet_word = word
            for char, replacement in leet_map.items():
                leet_word = leet_word.replace(char, replacement)
            if leet_word != word:
                leet_variations.append(leet_word)
        
        default_list.extend(additional_variations)
        default_list.extend(leet_variations)
        
        # Remove duplicates and convert to set
        return set(default_list)

    async def _load_additional_bad_words_from_db(self):
        """Asynchronously loads additional bad words from MongoDB and adds them to the existing set."""
        if self.collection: 
            try:
                cursor = self.collection.find({})
                db_words = [doc['word'] for doc in await cursor.to_list(length=None) if 'word' in doc]
                self.bad_words.update(db_words)
                logger.info(f"Loaded {len(db_words)} additional bad words from MongoDB.")
            except Exception as e:
                logger.error(f"Error loading additional bad words from MongoDB: {e}")
        else:
            logger.warning("MongoDB collection not available to load additional bad words.")

    async def add_bad_word(self, word: str) -> bool:
        """Asynchronously adds a bad word to the filter and, if connected, to MongoDB."""
        normalized_word = word.lower().strip()
        if normalized_word not in self.bad_words:
            self.bad_words.add(normalized_word)
            if self.collection:
                try:
                    await self.collection.update_one(
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
