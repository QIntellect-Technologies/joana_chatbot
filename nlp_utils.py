# -----------------------------
# Joana Fast Food Chatbot — NLP Utility Functions
# -----------------------------
import os
import re
from difflib import get_close_matches

import pandas as pd

# -----------------------------
# Paths
# -----------------------------
# Always use absolute paths on cPanel
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # <-- NOTE: __file, not _file
DATA_DIR = os.path.join(BASE_DIR, "data")
MENU_FILE = os.path.join(DATA_DIR, "Menu.xlsx")        # Same file as app.py uses


# --- Intent Dictionary (Improved + Clean) ---
INTENTS = {
    "greeting": [
        "hello",
        "hi",
        "hey",
        "good morning",
        "good evening",
        "مرحبا",
        "أهلاً",
        "اهلا",
        "هلا",
        "السلام",
        "السلام عليكم",
    ],
    "menu": ["menu", "show menu", "list", "قائمة", "القائمة"],
    "order_start": ["order", "buy", "أريد الطلب", "أطلب", "طلب", "ابغى", "أبغى"],
    "add_item": [
        "add",
        "zinger",
        "burger",
        "fries",
        "drink",
        "زنجر",
        "برغر",
        "بطاطس",
        "مشروب",
    ],
    "confirm": ["confirm", "ok", "تمام", "خلاص", "اعتمد", "اكيد", "نعم"],
    "payment": [
        "pay",
        "payment",
        "cash",
        "online",
        "card",
        "دفع",
        "بطاقة",
        "كاش",
        "نقد",
        "مدى",
    ],
    "branch": [
        "branch",
        "call",
        "address",
        "location",
        "فرع",
        "موقع",
        "مكان",
        "رقم",
        "اتصل",
    ],
    "timing": ["time", "open", "timing", "closing", "متى", "وقت", "ساعات العمل"],
    "abuse": ["stupid", "idiot", "fuck", "shit", "غبي", "تافه", "لعنة", "اخرس"],
}


# --- Load Menu Items from Excel ---
def load_menu_items():
    """
    Load English item names from the same Excel file the main app uses.
    This is only for intent detection (is this message probably a menu item?).
    """
    try:
        # Find the header row the same way app.py does, so cPanel Excel uploads work.
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
            (
                c
                for c in df.columns
                if c == "name_en" or "english" in c or "item" in c
            ),
            None,
        )
        if not english_col:
            english_col = df.columns[0]  # fallback to first column to avoid hard failure
            print("⚠ Could not find explicit English/item column; using first column instead.")

        items = [str(x).strip().lower() for x in df[english_col].dropna()]
        print(f"✅ nlp_utils: loaded {len(items)} menu items for intent detection.")
        return items

    except Exception as e:
        print("⚠ Menu load failed in nlp_utils:", e)
        return []


MENU_ITEMS = load_menu_items()


# --- Intent Detection (smart + safe) ---
def detect_intent(text: str) -> str:
    """
    Detects user intent:
    - First checks if sentence looks like a menu item
    - Then matches known intent keywords
    - Falls back to 'unknown'
    """
    text_lower = text.lower().strip()

    # 1) Check if message closely matches a menu item
    if MENU_ITEMS:
        match = get_close_matches(text_lower, MENU_ITEMS, n=1, cutoff=0.65)
        if match:
            return "add_item"

    # 2) Keyword-based intent detection
    for intent, keywords in INTENTS.items():
        for kw in keywords:
            if kw in text_lower:
                return intent

    return "unknown"


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