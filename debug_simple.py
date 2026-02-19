
import re

# Mock nlp_utils
CATEGORY_KEYWORDS = {
    "drinks": {"keywords": ["drink", "drinks", "pepsi", "water"], "category_id": "drinks"},
    "burgers": {"keywords": ["burger", "burgers", "zinger"], "category_id": "burgers"}
}

def detect_category_from_text(text):
    text = text.lower()
    for cat, data in CATEGORY_KEYWORDS.items():
        for kw in data["keywords"]:
            if kw in text:
                return data["category_id"]
    return None

def looks_like_multi_item_text(msg: str) -> bool:
    if not msg: return False
    # Simplified mock of app.py logic
    # Real logic checks for digits OR "and"
    if " and " in msg.lower(): return True
    if any(char.isdigit() for char in msg): return True
    return False

# MOCK WA_GREETINGS from app.py
WA_GREETINGS = ["hi", "hello"]

def is_wa_greeting(text: str) -> bool:
    t = text.strip().lower()
    if t in WA_GREETINGS: return True
    for g in WA_GREETINGS:
        if t.startswith(g + " "): return True
    return False

# MOCK detect_intent from nlp_utils.py (simplified)
def detect_intent(text):
    # This logic must match nlp_utils.py priority
    text_lower = text.lower()
    
    # 1. Greeting
    if is_wa_greeting(text): return "greeting"
    
    # ... other intents ...
    
    # 4. Order Intent
    if "want to order" in text_lower: return "order_start"
    
    return "unknown"

print("--- DEBUG SIMPLE ---\n")

messages = [
    "I want to order burgers",
    "I want to order burgers and meals",
    "Do you have drinks?"
]

for msg in messages:
    print(f"MSG: '{msg}'")
    intent = detect_intent(msg)
    print(f"  Intent: {intent}")
    
    is_multi = looks_like_multi_item_text(msg)
    print(f"  Multi-Item: {is_multi}")
    
    cat = detect_category_from_text(msg)
    print(f"  Category: {cat}")
    
    # Simulate app.py logic
    if intent == "order_start":
        if is_multi:
            print("  ACTION: Fallthrough (Multi-Item)")
        elif cat:
            print(f"  ACTION: Open Category ({cat})")
        else:
            print("  ACTION: Generic Menu")
            
    print("-" * 30)
