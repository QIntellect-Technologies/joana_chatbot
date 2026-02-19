
import sys
import os
import re

# Mock nlp_utils
def detect_category_from_text(text):
    text = text.lower()
    if "burger" in text: return "burgers"
    return None

def detect_intent(text):
    text_lower = text.lower()
    patterns = ["order", "i want to order"]
    for p in patterns:
        if p in text_lower: return "order_start"
    return "unknown"

def looks_like_multi_item_text(msg: str) -> bool:
    t = msg.lower()
    if " and " in t: return True
    if any(c.isdigit() for c in t): return True
    return False

# THE LOGIC FROM app.py
def process_logic(msg):
    msg_l = msg.lower()
    intent = detect_intent(msg)
    is_multi_item = looks_like_multi_item_text(msg)
    has_digits = any(c.isdigit() for c in msg)
    detected_cat = detect_category_from_text(msg)
    
    print(f"MSG: '{msg}'")
    print(f"  Intent: {intent}")
    print(f"  Multi-Item: {is_multi_item}")
    print(f"  Has Digits: {has_digits}")
    print(f"  Detected Cat: {detected_cat}")
    
    # 0. The Category Trigger I added
    if (intent == "menu" or intent == "order_start") and not (False): # from_button=False
        # 1.5 Check if generically asking for categories
        if not detected_cat and "category" in msg_l: # simplified is_asking_for_categories
            return "ACTION: show_categories_ui"

        # 2. DECISION LOGIC (The problematic part)
        if is_multi_item and not has_digits and detected_cat:
            return f"ACTION: open_category ({detected_cat})"
            
    if is_multi_item:
        return "ACTION: multi_item_handler"
        
    return "ACTION: standard_flow"

print(process_logic("one chicken burger and one beef burger"))
print("-" * 20)
print(process_logic("burgers and meals"))
