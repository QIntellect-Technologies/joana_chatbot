
import sys
import os

# Mock pandas to avoid import errors in nlp_utils if it imports pandas
import sys
from unittest.mock import MagicMock
sys.modules["pandas"] = MagicMock()

# Mock other potential heavy dependencies if needed
# ...

# Add current directory to path
sys.path.append(os.getcwd())

# ---------------------------------------------------------
# COPY PASTE RELEVANT FUNCTIONS FROM nlp_utils.py TO TEST
# (Because nlp_utils.py likely imports pandas at top level)
# ---------------------------------------------------------

CATEGORY_KEYWORDS = {
    "burgers": {
        "keywords": [
            "burger", "burgers", "buger", "bugger", "burgr", "burgar", "burguer",
            "beef burger", "chicken burger", "zinger", "crispy",
            "برجر", "البرجر", "برجرات", "برقر", "زنجر", "كرسبي"
        ],
        "category_id": "burgers"
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

def detect_category_from_text(text: str) -> str | None:
    if not text:
        return None
    
    text_lower = text.lower().strip()
    
    for category, data in CATEGORY_KEYWORDS.items():
        for keyword in data["keywords"]:
            if keyword.lower() in text_lower:
                return data["category_id"]
    return None

msg = "I want to order burgers"
print(f"Message: '{msg}'")

print("Checking CATEGORY_KEYWORDS['burgers']...")
# print(CATEGORY_KEYWORDS.get('burgers'))

cat = detect_category_from_text(msg)
print(f"Detected Category: {cat}")

msg2 = "I want to order beef burger"
cat2 = detect_category_from_text(msg2)
print(f"Message: '{msg2}' -> Category: {cat2}")
