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
    
    text_lower = text.lower().strip()
    
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