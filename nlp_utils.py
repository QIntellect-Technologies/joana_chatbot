# -----------------------------
# Joana Fast Food Chatbot — NLP Utility Functions
# COMPREHENSIVE INTENT DETECTION SYSTEM (1000+ Variations)
# -----------------------------
import os
import re
from difflib import get_close_matches

import pandas as pd

# -----------------------------
# Paths
# -----------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
MENU_FILE = os.path.join(DATA_DIR, "Menu.xlsx")

# ============================================
# COMPREHENSIVE INTENT PATTERNS (ENGLISH)
# Handles 1000+ variations of user inputs
# ============================================

# Greeting patterns - handles hi, hello, how are you, etc.
GREETING_PATTERNS = [
    # Basic greetings
    "hi", "hello", "hey", "hii", "hiii", "hiiii", "helo", "hallo", "hullo",
    "hiya", "heya", "yo", "sup", "wassup", "whats up", "what's up", "whaddup",
    "howdy", "greetings", "salutations",
    # Time-based greetings
    "good morning", "good afternoon", "good evening", "good night", "good day",
    "morning", "afternoon", "evening", "gm", "gn",
    # How are you variations
    "how are you", "how r u", "how r you", "how are u", "how you doing",
    "how are you doing", "how is it going", "hows it going", "how's it going",
    "how you been", "how have you been", "how are things", "hows things",
    "how do you do", "whats going on", "what's going on", "what is going on",
    "hows your day", "how's your day", "hows life", "how's life",
    "you good", "you ok", "everything good", "all good", "you alright",
    "are you there", "anybody there", "anyone there", "you there",
    # Polite intros
    "nice to meet you", "pleased to meet you", "good to see you",
    # Short forms
    "hru", "wru", "wyd",
]

# Menu browsing patterns - show me, what do you have, etc.
MENU_BROWSING_PATTERNS = [
    # "Show me" variations
    "show me", "show", "display", "let me see", "lemme see", "can i see",
    "could i see", "may i see", "i want to see", "i wanna see", "wanna see",
    "show us", "display for me", "show me the", "can you show", "can u show",
    "pls show", "please show", "plz show", "plss show", "pleas show",
    # "What do you have" variations
    "what do you have", "what you have", "what u have", "what have you got",
    "what you got", "what u got", "whats available", "what is available",
    "what available", "what do u have", "what do you got", "what you have in",
    "what do you have in", "what u have in", "what have you", "what have u",
    "what options", "what are the options", "what r the options", "what choices",
    "whats there", "what is there", "what there", "what all you have",
    "what can i get", "what can i order", "what can i have",
    # "Menu" variations
    "menu", "menu of", "menu for", "the menu", "your menu", "ur menu",
    "full menu", "complete menu", "entire menu", "whole menu", "all menu",
    "menu items", "menu list", "food menu", "item menu", "items menu",
    "menue", "manu", "menuu", "menus", "menuz", "menu please", "menu pls",
    "menu?", "menu??", "menu???", "see menu", "view menu", "open menu",
    "get menu", "give menu", "send menu", "menu card", "menu options",
    # "List" variations
    "list", "list of", "list all", "list the", "listing", "listings",
    "give me list", "give list", "show list", "show me list", "can i get list",
    "send list", "send me list", "share list", "share the list",
    # "Items" variations
    "items", "item", "things", "stuff", "options", "choices", "selection",
    "selections", "products", "dishes", "foods", "food items", "menu items",
    "available items", "all items", "your items", "ur items", "the items",
    # "Categories" variations
    "categories", "category", "types", "type", "kinds", "kind", "sections",
    "section", "groups", "group", "menu categories", "food categories",
    "item categories", "all categories", "your categories", "ur categories",
    # "Browse" variations
    "browse", "browsing", "look at", "looking at", "check", "check out",
    "checking", "checking out", "explore", "exploring", "view", "viewing",
    "see", "seeing", "look through", "go through", "scroll through",
    # Question words for menu
    "what", "which", "whats", "what is", "what are", "what r",
    "tell me", "tell me about", "tell about", "info about", "information about",
    "details about", "detail about", "describe", "explain",
    # "I want to see menu" variations
    "show me the menu", "show me menu", "show the menu", "show ur menu",
    "i want to see the menu", "i want to see menu", "i wanna see the menu",
    "can i see the menu", "can i see your menu", "may i see the menu",
    "let me see the menu", "let me see your menu", "lemme see the menu",
    "id like to see the menu", "i would like to see the menu",
    "give me the menu", "give me your menu", "send me the menu",
    "send me your menu", "what is on the menu", "whats on the menu",
    "what do you have on the menu", "what items do you have",
    "what food do you have", "what food do you serve",
    "what dishes do you have", "what do you offer", "what do you sell",
    "do you have", "do you get", "have you got",
]

# Order intent patterns - I want to order, can I order, etc.
ORDER_INTENT_PATTERNS = [
    # "I want to order" variations
    "i want to order", "i wanna order", "want to order", "wanna order",
    "i want order", "i wanna order something", "i want to order something",
    "i would like to order", "id like to order", "i'd like to order",
    "i need to order", "i need to place an order", "need to order",
    "i wish to order", "wish to order",
    # "Can I order" variations
    "can i order", "can i order something", "could i order", "may i order",
    "can i place an order", "can i make an order", "can i get an order",
    "can i order here", "can i order now", "can i order please",
    "could i place an order", "may i place an order",
    # "Order" simple variations
    "order", "order now", "order please", "order pls", "order plz",
    "place order", "place an order", "make order", "make an order",
    "get order", "start order", "start my order", "start ordering",
    "begin order", "begin ordering", "new order", "create order",
    # "I want to buy" variations
    "i want to buy", "i wanna buy", "want to buy", "wanna buy",
    "i want buy", "buy", "buy something", "buy food", "buy now",
    "purchase", "purchase something", "purchase food",
    # "I'm hungry" / "I need food" variations
    "im hungry", "i am hungry", "i'm hungry", "hungry", "starving",
    "i need food", "need food", "i want food", "want food", "give me food",
    "i need something to eat", "something to eat", "want to eat",
    "i wanna eat", "feed me", "i want to eat", "looking for food",
    # "Take my order" variations
    "take my order", "take order", "accept my order", "get my order",
    "process my order", "receive my order",
    # Order with items
    "order food", "order something", "order items", "order meal",
    "order for me", "order for us",
    # Misc
    "what can i order", "what can i get", "ready to order", "lets order",
    "let's order", "ordering", "wanna get", "want to get", "i want to get",
]

# Cancel order patterns
CANCEL_ORDER_PATTERNS = [
    "cancel", "cancel order", "cancel my order", "cancel the order",
    "cancel all", "cancel everything", "cancel complete order",
    "cancel entire order", "cancel whole order", "cancellation",
    "i want to cancel", "i wanna cancel", "want to cancel",
    "stop order", "stop my order", "stop the order",
    "delete order", "delete my order", "remove order", "remove my order",
    "discard order", "discard my order", "abort order", "abort",
    "forget order", "forget it", "forget my order", "never mind",
    "nevermind", "nvm", "dont want", "don't want", "i dont want",
    "i don't want", "changed my mind", "not interested", "no thanks",
]

# Finish order patterns
FINISH_ORDER_PATTERNS = [
    "finish", "finish order", "finish my order", "complete order",
    "complete my order", "complete the order", "checkout", "check out",
    "pay", "payment", "bill", "receipt", "done", "im done", "i am done",
    "i'm done", "thats all", "that's all", "thats it", "that's it",
    "nothing else", "nothing more", "no more", "all done",
    "finalize", "finalise", "finalize order", "end order", "end my order",
    "place my order", "confirm order", "confirm my order", "submit order",
    "proceed", "proceed to payment", "proceed to checkout",
    "ready to pay", "want to pay", "wanna pay", "i want to pay",
    "total", "my total", "how much", "how much total", "order total",
    "check total", "see total", "get total", "calculate total",
]

DELIVERY_PATTERNS = [
    "delivery", "do you deliver", "is there delivery", "have delivery",
    "shipping", "ship", "deliver", "home delivery",
]

# ============================================
# COMPREHENSIVE INTENT PATTERNS (ARABIC)
# ============================================

GREETING_PATTERNS_AR = [
    # Basic greetings
    "مرحبا", "أهلاً", "اهلا", "هلا", "هاي", "هاى", "السلام", "السلام عليكم",
    "سلام", "اهلين", "هلا والله", "يا هلا", "مرحبتين", "الله بالخير",
    "صباح الخير", "صباحك سكر", "مساء الخير", "مساء النور",
    # How are you
    "كيف حالك", "كيفك", "شلونك", "شخبارك", "عامل ايه", "كيف الحال",
    "وش اخبارك", "ايش اخبارك", "شو اخبارك", "كيف صحتك", "عساك بخير",
    "ان شاء الله بخير", "زين انت", "تمام انت",
]

MENU_BROWSING_PATTERNS_AR = [
    # "Show me" variations
    "أرني", "عرض", "وريني", "فرجني", "شوف", "ابغى اشوف", "بدي شوف",
    "أريد رؤية", "ممكن اشوف", "تعرض لي", "هات", "عطني",
    # "What do you have" variations
    "ماذا لديكم", "شنو عندكم", "وش عندكم", "ايش عندكم", "شو عندكم",
    "ما هي الخيارات", "وش فيه", "ايش فيه", "ماهي الاصناف", "وش تبيعون",
    "ايش تبيعون", "شو تبيعون",
    # "Menu" variations
    "قائمة", "القائمة", "منيو", "المنيو", "لائحة الطعام",
    "قائمة الطعام", "الاصناف", "الاكل", "قائمة الاكل",
    "ليسته", "لستة", "قائمه", "لائحة", "سجل",
    # "Show me menu"
    "وريني المنيو", "أرني القائمة", "عرض المنيو", "طلع المنيو",
    "ابغى اشوف المنيو", "وين المنيو", "فين المنيو",
]

ORDER_INTENT_PATTERNS_AR = [
    # "I want to order"
    "أريد الطلب", "ابغى اطلب", "أبغى أطلب", "بدي اطلب", "اريد اطلب",
    "ابغا اطلب", "ودي اطلب", "حابب اطلب", "عايز اطلب",
    "طلب", "اطلب", "نطلب", "بطلب", "راح اطلب",
    # "Can I order"
    "ممكن اطلب", "اقدر اطلب", "هل استطيع الطلب", "ينفع اطلب",
    # Order related
    "طلب جديد", "طلبية", "ابي آخذ", "ابي اشتري", "بشتري",
    "خذ طلبي", "سجل طلبي",
]

CANCEL_ORDER_PATTERNS_AR = [
    "إلغاء", "الغاء", "إلغاء الطلب", "الغاء الطلب", "إلغاء طلبي",
    "الغاء طلبي", "كنسل", "إلغاء الكل", "الغاء الكل",
    "إلغاء الطلب بالكامل", "الغاء بالكامل", "أريد الإلغاء",
    "ابغى الغي", "بدي الغي", "توقف", "وقف", "حذف الطلب",
    "امسح الطلب", "شيل الطلب", "لا ابغى", "ما ابغى", "غيرت رايي",
    "صرف النظر", "خلاص مابي", "لا شكرا",
]

FINISH_ORDER_PATTERNS_AR = [
    "إنهاء", "انهاء", "إنهاء الطلب", "انهاء الطلب", "إتمام الطلب",
    "اتمام الطلب", "خلصت", "انتهيت", "حساب", "الحساب", "الفاتورة",
    "دفع", "سداد", "خلاص", "خلصنا", "تم الطلب", "كذا تمام",
    "بس كذا", "هذا كل شي", "هذا الطلب", "اكدي الطلب", "تاكيد الطلب",
    "المجموع", "كم المجموع", "كم الحساب", "كم الفاتورة",
]

DELIVERY_PATTERNS_AR = [
    "توصيل", "عندكم توصيل", "فيه توصيل", "توصلون", "خدمة التوصيل",
    "توصيل طلبات", "يوصل", "توصل",
]

# ============================================
# CATEGORY-SPECIFIC KEYWORDS
# ============================================

CATEGORY_KEYWORDS = {
    "burgers": {
        "keywords": [
            "burger", "burgers", "buger", "bugger", "burgr", "burgar", "burguer",
            "beef burger", "chicken burger", "zinger", "crispy",
            "برجر", "البرجر", "برجرات", "برقر", "زنجر", "كرسبي"
        ],
        "category_id": "burgers"
    },
    "sandwiches": {
        "keywords": [
            "sandwich", "sandwiches", "sandwch", "sandwhich", "sandwitch",
            "sanwich", "sandwic", "sandwiche", "kudu", "kabab", "hot dog",
            "kibdah", "egg sandwich", "chicken sandwich",
            "سندويش", "السندويشات", "سندويتش", "ساندويش", "كودو", "كباب",
            "هوت دوغ", "كبدة", "بيض", "شكشوكة"
        ],
        "category_id": "sandwiches"
    },
    "sides": {
        "keywords": [
            "side", "sides", "snack", "snacks", "appetizer", "appetizers",
            "starter", "starters", "side dish", "side dishes", "side items",
            "fries", "french fries", "nuggets", "chicken nuggets", "popcorn",
            "corn", "potato", "sweet potato", "onion rings", "samosa",
            "مقبلات", "المقبلات", "سناك", "جانبية", "بطاطس", "ناجتس",
            "بوفك", "ذرة", "حلقات البصل", "سمبوسة"
        ],
        "category_id": "sides"
    },
    "drinks": {
        "keywords": [
            "drink", "drinks", "beverage", "beverages", "soft drink",
            "cold drink", "pepsi", "water", "tea", "coffee", "juice",
            "orange juice", "cocktail", "slash", "rabia",
            "مشروب", "المشروبات", "مشروبات", "بيبسي", "ماء", "شاي",
            "قهوة", "عصير", "عصيرات", "كوكتيل", "سلاش"
        ],
        "category_id": "drinks"
    },
    "meals": {
        "keywords": [
            "meal", "meals", "meel", "meeal", "combo", "combos",
            "meal deal", "meal deals", "full meal", "complete meal",
            "وجبة", "الوجبات", "وجبات", "كومبو"
        ],
        "category_id": "meals"
    }
}

# ============================================
# TYPO CORRECTIONS DICTIONARY (ENGLISH)
# ============================================

TYPO_CORRECTIONS = {
    # ===== BURGER TYPOS =====
    "brger": "burger", "burge": "burger", "buger": "burger", "bugger": "burger",
    "burgar": "burger", "burgr": "burger", "bergar": "burger", "berger": "burger",
    "burguer": "burger", "burgor": "burger", "burgir": "burger", "burjer": "burger",
    "burga": "burger", "brgr": "burger", "bugrer": "burger", "bureger": "burger",
    "burgrer": "burger", "burgerr": "burger", "burrger": "burger", "buregr": "burger",
    "bruger": "burger", "brugr": "burger", "burher": "burger", "burgee": "burger",
    "buerger": "burger", "burgerd": "burger", "baerger": "burger", "burfer": "burger",
    "bergur": "burger", "burgar's": "burger", "burgers": "burger",
    
    # ===== CHICKEN TYPOS =====
    "chicekn": "chicken", "chiken": "chicken", "chicke": "chicken", "chickn": "chicken",
    "chciken": "chicken", "chikken": "chicken", "chickken": "chicken", "chickin": "chicken",
    "chiken": "chicken", "chickne": "chicken", "chikcen": "chicken", "chickenn": "chicken",
    "chieken": "chicken", "chikn": "chicken", "chickien": "chicken", "chickun": "chicken",
    "chickon": "chicken", "ciken": "chicken", "chekcin": "chicken", "chikin": "chicken",
    "chickan": "chicken", "chckin": "chicken", "chickeen": "chicken", "chckn": "chicken",
    "chikenn": "chicken", "chckien": "chicken", "chiccken": "chicken", "shiken": "chicken",
    "chickn": "chicken", "chekin": "chicken", "chkin": "chicken",
    
    # ===== BEEF TYPOS =====
    "beaf": "beef", "beeff": "beef", "beff": "beef", "beeef": "beef", "beaf": "beef",
    "bief": "beef", "biif": "beef", "beaf": "beef", "bef": "beef", "bef": "beef",
    "beefburger": "beef burger", "beefbuger": "beef burger", "beff burger": "beef burger",
    "beaf burger": "beef burger", "beef berger": "beef burger",
    
    # ===== COFFEE TYPOS =====
    "coffe": "coffee", "cofee": "coffee", "cofe": "coffee", "coffie": "coffee",
    "cofie": "coffee", "coffey": "coffee", "coffy": "coffee", "coffi": "coffee",
    "coffea": "coffee", "coffie": "coffee", "coffey": "coffee", "cofee": "coffee",
    "cofeee": "coffee", "coofee": "coffee", "cofffee": "coffee", "coffeee": "coffee",
    "qahwa": "coffee", "kahwa": "coffee", "kawa": "coffee", "gahwa": "coffee",
    
    # ===== WATER TYPOS =====
    "wter": "water", "watr": "water", "wwter": "water", "wateer": "water",
    "watar": "water", "watter": "water", "watre": "water", "wtaer": "water",
    "moya": "water", "maoya": "water", "mooya": "water", "maia": "water",
    "maya": "water", "moye": "water", "maai": "water", "maa": "water",
    
    # ===== WRAP/TORTILLA TYPOS =====
    "warp": "wrap", "wrpa": "wrap", "wraap": "wrap", "wrapp": "wrap", "wrop": "wrap",
    "werp": "wrap", "wreap": "wrap", "tortila": "tortilla", "tortilaa": "tortilla",
    "totrilla": "tortilla", "tortiglia": "tortilla", "totilla": "tortilla",
    "tortella": "tortilla", "tortiia": "tortilla", "trtilla": "tortilla",
    "tortya": "tortilla", "turtilla": "tortilla", "tortiyya": "tortilla",
    
    # ===== SANDWICH TYPOS =====
    "sandwhich": "sandwich", "sandwitch": "sandwich", "sanwich": "sandwich",
    "sandwch": "sandwich", "sammich": "sandwich", "sandwic": "sandwich",
    "sandwhic": "sandwich", "sadwich": "sandwich", "sandwiche": "sandwich",
    "sendwich": "sandwich", "sandwitsh": "sandwich", "sanwdich": "sandwich",
    "sandwicth": "sandwich", "sandiwch": "sandwich", "swandwich": "sandwich",
    "sandwhitch": "sandwich", "sandwch": "sandwich", "sadnwich": "sandwich",
    "sandwhichh": "sandwich", "sandwedge": "sandwich", "sandich": "sandwich",
    "sanwitch": "sandwich", "sandiwich": "sandwich", "snwich": "sandwich",
    "sandwitxh": "sandwich", "sanwdwich": "sandwich", "sandwitch": "sandwich",
    
    # ===== JUICE TYPOS =====
    "jucie": "juice", "juce": "juice", "juic": "juice", "jucei": "juice",
    "juise": "juice", "jooce": "juice", "jouce": "juice", "juse": "juice",
    "jsuce": "juice", "juiice": "juice", "juuice": "juice", "juicce": "juice",
    "asir": "juice", "aasir": "juice", "aseer": "juice", "aser": "juice",
    
    # ===== PEPSI TYPOS =====
    "pepis": "pepsi", "peps": "pepsi", "pesi": "pepsi", "pespy": "pepsi",
    "pepci": "pepsi", "pespi": "pepsi", "bepsi": "pepsi", "bebsi": "pepsi",
    "bebbsi": "pepsi", "pepsy": "pepsi", "pepsie": "pepsi", "pepsei": "pepsi",
    "pepsii": "pepsi", "pepsey": "pepsi", "pipsee": "pepsi", "peepsi": "pepsi",
    
    # ===== ZINGER TYPOS =====
    "zingr": "zinger", "zinegr": "zinger", "zenge": "zinger", "zingger": "zinger",
    "zingre": "zinger", "zinjer": "zinger", "zenger": "zinger", "sijnger": "zinger",
    "singer": "zinger", "zingeer": "zinger", "zainger": "zinger", "zingr": "zinger",
    "zingrr": "zinger", "zengerr": "zinger", "zengar": "zinger", "zingir": "zinger",
    "zenjer": "zinger", "zngr": "zinger", "zinjr": "zinger", "zienger": "zinger",
    "zinggr": "zinger", "zingerr": "zinger", "singar": "zinger", "zenjer": "zinger",
    
    # ===== KABAB/KEBAB TYPOS =====
    "kebab": "kabab", "kebap": "kabab", "kebeb": "kabab", "kabap": "kabab",
    "kabob": "kabab", "kabab": "kabab", "kabbab": "kabab", "kabeb": "kabab",
    "kebob": "kabab", "kebbab": "kabab", "cabaab": "kabab", "cabbab": "kabab",
    "kababb": "kabab", "kabaab": "kabab", "kebabb": "kabab", "kebaab": "kabab",
    "kbab": "kabab", "kbeb": "kabab", "kabba": "kabab", "kebba": "kabab",
    
    # ===== NUGGETS TYPOS =====
    "nugets": "nuggets", "nugetts": "nuggets", "nugets": "nuggets", "nugges": "nuggets",
    "nuggits": "nuggets", "nuggetes": "nuggets", "nugetes": "nuggets", "nugget": "nuggets",
    "nuggetz": "nuggets", "nuggts": "nuggets", "nuggetts": "nuggets", "nuggats": "nuggets",
    "nugggtes": "nuggets", "nuggest": "nuggets", "nuggyst": "nuggets", "nuggste": "nuggets",
    "najets": "nuggets", "najits": "nuggets", "naagets": "nuggets", "nagits": "nuggets",
    "najtes": "nuggets", "najtis": "nuggets", "naijts": "nuggets",
    
    # ===== MEAL TYPOS =====
    "meel": "meal", "meeal": "meal", "meale": "meal", "meall": "meal", "maeal": "meal",
    "mael": "meal", "meall": "meal", "mieal": "meal", "meial": "meal", "meeel": "meal",
    "mal": "meal", "mial": "meal", "maial": "meal", "meels": "meals", "mealls": "meals",
    "meaals": "meals", "melas": "meals", "meels": "meals",
    
    # ===== FRIES TYPOS =====
    "fris": "fries", "freis": "fries", "fres": "fries", "friez": "fries",
    "friies": "fries", "frie": "fries", "fryes": "fries", "frys": "fries",
    "freies": "fries", "frice": "fries", "friess": "fries", "frees": "fries",
    "freis": "fries", "frize": "fries", "fryis": "fries", "fryies": "fries",
    "french fris": "french fries", "french fres": "french fries",
    "freanch fries": "french fries", "french friez": "french fries",
    
    # ===== CRISPY TYPOS =====
    "crspy": "crispy", "crispy": "crispy", "crisp": "crispy", "crispi": "crispy",
    "crisby": "crispy", "crispie": "crispy", "crsipy": "crispy", "crsipi": "crispy",
    "crisppy": "crispy", "cryspy": "crispy", "chrsipy": "crispy", "krispi": "crispy",
    "krispe": "crispy", "krsipy": "crispy", "krspi": "crispy",
    
    # ===== BROASTED/BROSTED TYPOS =====
    "brosted": "broasted", "broastd": "broasted", "brostd": "broasted",
    "brosted": "broasted", "brsoted": "broasted", "brostid": "broasted",
    "barosted": "broasted", "barsoted": "broasted", "broastde": "broasted",
    "braosted": "broasted", "broasteed": "broasted",
    
    # ===== STEAK TYPOS =====
    "stek": "steak", "steek": "steak", "staek": "steak", "steakk": "steak",
    "steake": "steak", "staik": "steak", "stayk": "steak", "steyk": "steak",
    
    # ===== SPICY/REGULAR PREFERENCE TYPOS =====
    "spicey": "spicy", "spiciy": "spicy", "spciy": "spicy", "spicyy": "spicy",
    "spici": "spicy", "spiicy": "spicy", "spcy": "spicy", "specy": "spicy",
    "spicci": "spicy", "spycy": "spicy", "spissy": "spicy", "spicee": "spicy",
    "reguler": "regular", "regualar": "regular", "regualr": "regular",
    "regulr": "regular", "regulare": "regular", "reglar": "regular",
    "rglr": "regular", "regurlar": "regular", "regualer": "regular",
    "reglur": "regular", "regulra": "regular", "regukar": "regular",
    "reglaur": "regular", "regural": "regular", "regluar": "regular",
    
    # ===== HOT/MILD TYPOS =====
    "hott": "hot", "hoott": "hot", "hote": "hot", "hoot": "hot",
    "midl": "mild", "milld": "mild", "mildd": "mild", "miled": "mild",
    
    # ===== META COMMANDS TYPOS =====
    "menuu": "menu", "meno": "menu", "menue": "menu", "mneu": "menu",
    "meenu": "menu", "menyu": "menu", "mainu": "menu", "manu": "menu",
    "cansel": "cancel", "cancle": "cancel", "cancell": "cancel", "cnacel": "cancel",
    "cancal": "cancel", "cancil": "cancel", "cansle": "cancel", "canceel": "cancel",
    "cancelo": "cancel", "canscel": "cancel", "cacel": "cancel", "cncel": "cancel",
    "confrm": "confirm", "confrim": "confirm", "conferm": "confirm", "confirme": "confirm",
    "conferm": "confirm", "confirm": "confirm", "cnfrm": "confirm", "confrom": "confirm",
    "confim": "confirm", "confierm": "confirm", "confrmm": "confirm",
    "ordr": "order", "ordeer": "order", "oderr": "order", "ordrer": "order",
    "oderz": "order", "oredr": "order", "oder": "order", "orderr": "order",
    "ordur": "order", "ordder": "order", "ordor": "order", "ordar": "order",
    "chekout": "checkout", "chekcout": "checkout", "chekot": "checkout",
    "checkot": "checkout", "checkoutt": "checkout", "cehckout": "checkout",
    "finsh": "finish", "finissh": "finish", "finsih": "finish", "finihsh": "finish",
    "finihs": "finish", "finissh": "finish", "finnsh": "finish", "finihsh": "finish",
    "pament": "payment", "paymnet": "payment", "payemnt": "payment", "paymet": "payment",
    "paymant": "payment", "paymint": "payment", "paymment": "payment",
    
    # ===== COMMON PHRASES TYPOS =====
    "wnat": "want", "wan": "want", "waant": "want", "wnta": "want",
    "pleas": "please", "plese": "please", "pls": "please", "plz": "please",
    "pleese": "please", "pleaz": "please", "pleasee": "please",
    "thnk": "thanks", "thankss": "thanks", "thx": "thanks", "thnks": "thanks",
    "somthing": "something", "somethng": "something", "somethin": "something",
    "sumthing": "something", "smthing": "something",
    
    # ===== HOT DOG TYPOS =====
    "hotdog": "hot dog", "hog dog": "hot dog", "hot doog": "hot dog",
    "hotdg": "hot dog", "hot dgo": "hot dog", "hot dod": "hot dog",
    
    # ===== SALAD TYPOS =====
    "salda": "salad", "slaad": "salad", "sallad": "salad", "saald": "salad",
    "saled": "salad", "salat": "salad", "salade": "salad",
    
    # ===== CHEESE TYPOS =====
    "chees": "cheese", "cheees": "cheese", "chese": "cheese", "chesee": "cheese",
    "chesse": "cheese", "cheeze": "cheese", "cheesse": "cheese",
    
    # ===== ONION TYPOS =====
    "onio": "onion", "onoin": "onion", "onino": "onion", "onien": "onion",
    "oniom": "onion", "onioon": "onion", "onons": "onion",
    
    # ===== EXTRA/ADD TYPOS =====
    "extar": "extra", "exrta": "extra", "extrra": "extra", "ekstra": "extra",
    "ad": "add", "aad": "add", "addd": "add", "aadd": "add",
}

# ============================================
# TYPO CORRECTIONS DICTIONARY (ARABIC)
# ============================================

TYPO_CORRECTIONS_AR = {
    # ===== BURGER TYPOS (Arabic) =====
    "برقر": "برجر", "بورجر": "برجر", "بيرجر": "برجر", "برگر": "برجر",
    "بيرقر": "برجر", "بورقر": "برجر", "برقار": "برجر", "برجار": "برجر",
    "برجير": "برجر", "برجرر": "برجر", "بررجر": "برجر", "بورجرر": "برجر",
    
    # ===== CHICKEN TYPOS (Arabic) =====
    "دجاجه": "دجاج", "دججاج": "دجاج", "دجاجج": "دجاج", "ججاج": "دجاج",
    "دجاجة": "دجاج", "فراخ": "دجاج", "فراج": "دجاج",
    
    # ===== BEEF TYPOS (Arabic) =====
    "لحمه": "لحم", "لحمة": "لحم", "لحمم": "لحم", "لخم": "لحم",
    "بيف": "لحم", "بييف": "لحم",
    
    # ===== ZINGER TYPOS (Arabic) =====
    "زنجر": "زنجر", "زينجر": "زنجر", "زنجار": "زنجر", "زينقر": "زنجر",
    "زنقر": "زنجر", "زنجير": "زنجر", "زينجار": "زنجر", "زنجرر": "زنجر",
    "سنجر": "زنجر", "صنجر": "زنجر",
    
    # ===== CRISPY TYPOS (Arabic) =====
    "كرسبي": "كريسبي", "كريسب": "كريسبي", "كرسبى": "كريسبي",
    "كريسبى": "كريسبي", "كرزبي": "كريسبي", "كرزبى": "كريسبي",
    
    # ===== SPICY/REGULAR PREFERENCES (Arabic) =====
    "سبايسى": "سبايسي", "إسبايسي": "سبايسي", "اسبايسي": "سبايسي",
    "سبايسيي": "سبايسي", "اسبيسي": "سبايسي", "سبيسي": "سبايسي",
    "حاره": "حار", "حارة": "حار", "حارر": "حار",
    "عادى": "عادي", "عاديي": "عادي", "اعادي": "عادي",
    
    # ===== META COMMANDS (Arabic) =====
    "منيوو": "منيو", "المنيوو": "المنيو", "مينو": "منيو", "مينيو": "منيو",
    "قايمه": "قائمة", "قائمه": "قائمة", "لايحة": "قائمة", "لائحه": "قائمة",
    "الغى": "الغاء", "الغي": "الغاء", "الغاا": "الغاء", "الغااء": "الغاء",
    "كانسل": "الغاء", "كنسل": "الغاء", "كنسيل": "الغاء",
    "تاكيد": "تأكيد", "تءكيد": "تأكيد", "تاءكيد": "تأكيد",
    "اتمام": "إتمام", "انهاء": "إنهاء", "انهى": "إنهاء",
    "طلبب": "طلب", "طالب": "طلب", "الطلبب": "الطلب",
    
    # ===== PEPSI (Arabic) =====
    "بيبسى": "بيبسي", "ببسي": "بيبسي", "ببيسي": "بيبسي", "بيبيسي": "بيبسي",
    "بيببسي": "بيبسي", "بيبسيي": "بيبسي",
    
    # ===== WATER (Arabic) =====
    "مويه": "ماء", "موية": "ماء", "مويا": "ماء", "ماي": "ماء",
    "مايه": "ماء", "ماية": "ماء", "مياه": "ماء",
    
    # ===== COFFEE (Arabic) =====
    "قهوه": "قهوة", "قهوا": "قهوة", "كوفي": "قهوة", "كوفى": "قهوة",
    "كافي": "قهوة", "كافى": "قهوة",
    
    # ===== BROASTED (Arabic) =====
    "بروستد": "بروستيد", "بروستاد": "بروستيد", "بارستد": "بروستيد",
    "بروستيت": "بروستيد", "برستد": "بروستيد", "بروستت": "بروستيد",
    
    # ===== MEAL (Arabic) =====
    "وجبه": "وجبة", "وجبا": "وجبة", "وجبات": "وجبة", "وجبت": "وجبة",
    "ميل": "وجبة", "ميال": "وجبة",
    
    # ===== SANDWICH (Arabic) =====
    "سندوتش": "سندويتش", "سندويش": "سندويتش", "ساندوتش": "سندويتش",
    "سندوشة": "سندويتش", "سنويتش": "سندويتش", "سندوشه": "سندويتش",
    
    # ===== NUGGETS (Arabic) =====
    "ناجتس": "ناجتس", "ناقتس": "ناجتس", "ناجيتس": "ناجتس",
    "نجتس": "ناجتس", "نجيتس": "ناجتس", "ناقيتس": "ناجتس",
    
    # ===== FRIES (Arabic) =====
    "بطاطا": "بطاطس", "بطاط": "بطاطس", "بتاتس": "بطاطس",
    "فرايز": "بطاطس", "فرايس": "بطاطس",
    
    # ===== KABAB (Arabic) =====
    "كبابب": "كباب", "كبب": "كباب", "كباابب": "كباب", "كيباب": "كباب",
    
    # ===== JUICE (Arabic) =====
    "عصبر": "عصير", "عاصير": "عصير", "عصيير": "عصير", "عصر": "عصير",
    
    # ===== COMMON PHRASES (Arabic) =====
    "ابغا": "ابغى", "ابي": "ابغى", "ابى": "ابغى", "ابقى": "ابغى",
    "اريد": "أريد", "اربد": "أريد",
    "ممكم": "ممكن", "مكن": "ممكن", "مممكن": "ممكن",
    "شكررا": "شكرا", "شكراا": "شكرا", "ششكرا": "شكرا", "مشكور": "شكرا",
}

# ============================================
# TYPO CORRECTION FUNCTION
# ============================================

def correct_typos(text: str, language: str = "auto") -> str:
    """
    Correct common typos in user input.
    
    Args:
        text: The input text to correct
        language: "en", "ar", or "auto" (detect automatically)
    
    Returns:
        Text with common typos corrected
    """
    if not text:
        return text
    
    # Auto-detect language if needed
    if language == "auto":
        if re.search(r"[\u0600-\u06FF]", text):
            language = "ar"
        else:
            language = "en"
    
    text_lower = text.lower()
    words = text_lower.split()
    corrected_words = []
    
    # Choose the appropriate dictionary
    typo_dict = TYPO_CORRECTIONS_AR if language == "ar" else TYPO_CORRECTIONS
    
    # Also apply English corrections to Arabic text (for transliterated words)
    combined_dict = {**TYPO_CORRECTIONS, **TYPO_CORRECTIONS_AR} if language == "ar" else TYPO_CORRECTIONS
    
    for word in words:
        # Remove punctuation for matching
        word_clean = re.sub(r'[^\w\u0600-\u06FF]', '', word)
        
        if word_clean in combined_dict:
            # Preserve any punctuation
            prefix = ""
            suffix = ""
            for i, c in enumerate(word):
                if c.isalnum() or '\u0600' <= c <= '\u06FF':
                    break
                prefix += c
            for i, c in enumerate(reversed(word)):
                if c.isalnum() or '\u0600' <= c <= '\u06FF':
                    break
                suffix = c + suffix
            
            corrected_words.append(prefix + combined_dict[word_clean] + suffix)
        else:
            corrected_words.append(word)
    
    return " ".join(corrected_words)


def correct_typos_advanced(text: str) -> str:
    """
    Advanced typo correction that also handles multi-word corrections
    and context-aware fixes.
    """
    if not text:
        return text
    
    # First, do basic word-level correction
    corrected = correct_typos(text, "auto")
    
    # Then check for multi-word patterns (phrases that need fixing)
    phrase_corrections = {
        # English phrases
        "i wnat to order": "i want to order",
        "i wan order": "i want to order",
        "show menue": "show menu",
        "can i oder": "can i order",
        "cancle order": "cancel order",
        "cancle my order": "cancel my order",
        "finsh order": "finish order",
        "chiken burger": "chicken burger",
        "beff burger": "beef burger",
        "french fris": "french fries",
        "hot dgo": "hot dog",
        # Arabic phrases
        "ابغا اطلب": "ابغى اطلب",
        "ابي اطلب": "ابغى اطلب",
        "وريني المنيوو": "وريني المنيو",
        "الغي الطلب": "الغاء الطلب",
    }
    
    corrected_lower = corrected.lower()
    for wrong, right in phrase_corrections.items():
        if wrong in corrected_lower:
            # Case-insensitive replacement
            pattern = re.compile(re.escape(wrong), re.IGNORECASE)
            corrected = pattern.sub(right, corrected)
    
    return corrected


# ============================================
# SIMPLE INTENTS (for backward compatibility)
# ============================================

INTENTS = {
    "greeting": GREETING_PATTERNS + GREETING_PATTERNS_AR,
    "menu": MENU_BROWSING_PATTERNS + MENU_BROWSING_PATTERNS_AR,
    "order_start": ORDER_INTENT_PATTERNS + ORDER_INTENT_PATTERNS_AR,
    "cancel": CANCEL_ORDER_PATTERNS + CANCEL_ORDER_PATTERNS_AR,
    "finish": FINISH_ORDER_PATTERNS + FINISH_ORDER_PATTERNS_AR,
    "confirm": ["confirm", "ok", "yes", "yeah", "yep", "sure", "okay", "ok",
                "تمام", "خلاص", "اعتمد", "اكيد", "نعم", "اي", "موافق", "حسنا"],
    "payment": ["pay", "payment", "cash", "online", "card", "credit", "debit",
                "دفع", "بطاقة", "كاش", "نقد", "مدى", "فيزا"],
    "branch": ["branch", "branches", "call", "phone", "address", "location", "where",
               "فرع", "فروع", "موقع", "مكان", "رقم", "اتصل", "وين", "فين"],
    "timing": ["time", "open", "timing", "closing", "hours", "when",
               "متى", "وقت", "ساعات العمل", "مفتوح", "يقفل"],
    "abuse": ["stupid", "idiot", "fuck", "shit", "damn", "hate",
              "غبي", "تافه", "لعنة", "اخرس"],
}

# --- Load Menu Items from Excel ---
def load_menu_items():
    """
    Load English item names from the same Excel file the main app uses.
    This is only for intent detection (is this message probably a menu item?).
    """
    try:
        df_raw = pd.read_excel(MENU_FILE, header=None, sheet_name=0)

        header_row_index = None
        for i, row in df_raw.iterrows():
            row_text = " ".join([str(x).strip().lower() for x in row.values if str(x) != "nan"])
            if any(k in row_text for k in ("name_en", "english", "item")):
                header_row_index = i
                break

        if header_row_index is None:
            print("⚠ Could not find header row with name_en/english/item in menu Excel.")
            return []

        df = pd.read_excel(MENU_FILE, header=header_row_index, sheet_name=0)
        df.columns = [str(c).strip().lower() for c in df.columns]

        english_col = next(
            (c for c in df.columns if c == "name_en" or "english" in c or "item" in c),
            None,
        )
        if not english_col:
            english_col = df.columns[0]
            print("⚠ Could not find explicit English/item column; using first column instead.")

        items = [str(x).strip().lower() for x in df[english_col].dropna()]
        print(f"✅ nlp_utils: loaded {len(items)} menu items for intent detection.")
        return items

    except Exception as e:
        print("⚠ Menu load failed in nlp_utils:", e)
        return []


MENU_ITEMS = load_menu_items()


# ============================================
# FUZZY MATCHING (Levenshtein Distance)
# ============================================

def levenshtein_distance(s1: str, s2: str) -> int:
    """Calculate the Levenshtein distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def fuzzy_match(text: str, patterns: list, threshold: float = 0.7) -> bool:
    """Check if text matches any pattern with fuzzy matching."""
    text_lower = text.lower().strip()
    
    for pattern in patterns:
        pattern_lower = pattern.lower().strip()
        
        # Exact match
        if text_lower == pattern_lower or pattern_lower in text_lower:
            return True
        
        # Fuzzy match using Levenshtein
        if len(text_lower) > 2 and len(pattern_lower) > 2:
            max_len = max(len(text_lower), len(pattern_lower))
            distance = levenshtein_distance(text_lower, pattern_lower)
            similarity = 1 - (distance / max_len)
            if similarity >= threshold:
                return True
    
    return False


# ============================================
# ENHANCED INTENT DETECTION
# ============================================

def detect_intent(text: str) -> str:
    """
    Comprehensive intent detection with 1000+ patterns.
    
    Returns one of:
    - "greeting" - hi, hello, how are you
    - "menu" - show menu, what do you have
    - "order_start" - I want to order, can I order
    - "cancel" - cancel order
    - "finish" - finish order, checkout
    - "add_item" - specific menu item detected
    - "browse_category" - specific category mentioned
    - "confirm" - yes, ok, confirm
    - "payment" - payment related
    - "branch" - branch/location related
    - "timing" - timing related
    - "abuse" - offensive content
    - "unknown" - fallback
    """
    if not text:
        return "unknown"
    
    # Apply typo correction first
    text_corrected = correct_typos_advanced(text)
    text_lower = text_corrected.lower().strip()
    
    # Remove punctuation for matching
    text_clean = re.sub(r'[^\w\s\u0600-\u06FF]', '', text_lower).strip()
    
    # 1) Check for greeting patterns first (highest priority for simple greetings)
    # Only match as greeting if it's a short message or explicit greeting
    if len(text_clean.split()) <= 5:
        for pattern in GREETING_PATTERNS + GREETING_PATTERNS_AR:
            pattern_clean = re.sub(r'[^\w\s\u0600-\u06FF]', '', pattern.lower()).strip()
            if text_clean == pattern_clean or text_clean.startswith(pattern_clean + " "):
                return "greeting"
        
        # Fuzzy match for greetings with typos
        if fuzzy_match(text_clean, GREETING_PATTERNS[:20], threshold=0.8):
            return "greeting"
    
    # 2) Check for cancel patterns
    for pattern in CANCEL_ORDER_PATTERNS + CANCEL_ORDER_PATTERNS_AR:
        if pattern.lower() in text_lower:
            return "cancel"
    
    # 3) Check for finish/checkout patterns
    for pattern in FINISH_ORDER_PATTERNS + FINISH_ORDER_PATTERNS_AR:
        if pattern.lower() in text_lower:
            return "finish"

    # 3.5) Check for delivery patterns
    for pattern in DELIVERY_PATTERNS + DELIVERY_PATTERNS_AR:
        if pattern.lower() in text_lower:
            return "delivery"
    
    # 4) Check for order intent patterns
    for pattern in ORDER_INTENT_PATTERNS + ORDER_INTENT_PATTERNS_AR:
        if pattern.lower() in text_lower:
            return "order_start"
    
    # 5) Check for menu browsing patterns
    for pattern in MENU_BROWSING_PATTERNS + MENU_BROWSING_PATTERNS_AR:
        pattern_clean = re.sub(r'[^\w\s\u0600-\u06FF]', '', pattern.lower()).strip()
        if pattern_clean in text_clean or text_clean == pattern_clean:
            return "menu"
    
    # 6) Check for specific category mentions
    for category, data in CATEGORY_KEYWORDS.items():
        for keyword in data["keywords"]:
            if keyword.lower() in text_lower:
                return "browse_category"
    
    # 7) Check if message closely matches a menu item
    if MENU_ITEMS:
        match = get_close_matches(text_lower, MENU_ITEMS, n=1, cutoff=0.65)
        if match:
            return "add_item"
    
    # 8) Check other intents
    for intent, keywords in INTENTS.items():
        if intent in ["greeting", "menu", "order_start", "cancel", "finish"]:
            continue  # Already checked above
        for kw in keywords:
            if kw.lower() in text_lower:
                return intent
    
    # 9) Fuzzy matching for common phrases with typos
    # Order variations with typos
    order_fuzzy = ["i want to order", "want to order", "can i order", "order please"]
    if fuzzy_match(text_clean, order_fuzzy, threshold=0.75):
        return "order_start"
    
    # Menu variations with typos
    menu_fuzzy = ["show menu", "show me menu", "menu please", "see menu"]
    if fuzzy_match(text_clean, menu_fuzzy, threshold=0.75):
        return "menu"
    
    return "unknown"


def detect_category_from_text(text: str) -> str | None:
    """
    Detect which category the user is asking about.
    Returns category_id or None.
    """
    if not text:
        return None
    
    text_lower = text.lower().strip()
    
    for category, data in CATEGORY_KEYWORDS.items():
        for keyword in data["keywords"]:
            if keyword.lower() in text_lower:
                return data["category_id"]
    
    return None


def get_intent_details(text: str) -> dict:
    """
    Get detailed intent information including category if applicable.
    
    Returns:
    {
        "intent": "browse_category" | "order_start" | etc,
        "category": "burgers" | None,
        "confidence": 0.0-1.0,
        "matched_pattern": "the pattern that matched"
    }
    """
    intent = detect_intent(text)
    category = detect_category_from_text(text)
    
    return {
        "intent": intent,
        "category": category,
        "confidence": 1.0 if intent != "unknown" else 0.0,
        "original_text": text
    }


def detect_language(text: str) -> str:
    """
    Detect Arabic or English.
    - If any Arabic script letters are present → 'ar'
    - Otherwise default to 'en'
    """
    text = text.strip().lower()

    # 1️⃣ Detect true Arabic letters
    if re.search(r"[\u0600-\u06FF]", text):
        return "ar"

    # 2️⃣ Default English
    return "en"