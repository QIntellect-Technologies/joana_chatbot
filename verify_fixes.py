
import re

# ==========================================
# 1. TEST SPICY LOGIC (Simulating app.py)
# ==========================================
def detect_spicy_nonspicy(msg: str):
    text = msg.lower().replace("_", " ").replace("-", " ")
    nonspicy_keywords_en = [
        "non spicy", "non-spicy", "no spicy", "without spicy", "without spice",
        "not spicy", "mild", "regular", "normal", "classic", "original"
    ]
    nonspicy_keywords_ar = ["بدون حار", "بدون حر", "عادي", "بدون"]
    nonspicy_flag = any(k in text for k in nonspicy_keywords_en + nonspicy_keywords_ar)

    spicy_keywords = ["spicy", "hot", "حار"]
    spicy_flag = any(k in text for k in spicy_keywords) and not nonspicy_flag
    return spicy_flag, nonspicy_flag

print("--- TEST 1: Regular Zinger (Spicy Check) ---")
msg = "regular zinger burger"
spicy, nonspicy = detect_spicy_nonspicy(msg)
print(f"Message: '{msg}' -> Spicy: {spicy}, Non-Spicy: {nonspicy}")
# Expect: Spicy=False, Non-Spicy=True


# ==========================================
# 2. TEST DELIVERY INTENT (Simonlating nlp_utils.py)
# ==========================================
DELIVERY_PATTERNS = [
    "delivery", "do you deliver", "is there delivery", "have delivery",
    "shipping", "ship", "deliver", "home delivery",
]

def detect_intent(text):
    text_lower = text.lower()
    for pattern in DELIVERY_PATTERNS:
        if pattern in text_lower:
            return "delivery"
    return "unknown"

print("\n--- TEST 2: Delivery Intent ---")
msg2 = "Is there delivery available?"
intent = detect_intent(msg2)
print(f"Message: '{msg2}' -> Intent: {intent}")
# Expect: delivery


# ==========================================
# 3. TEST CANCELLATION RESOLUTION (Simulating match logic)
# ==========================================
def resolve_menu_item(name):
    # Mock resolution
    if "zinger" in name.lower():
        return "zinger_burger_key", 1.0
    if "tortilla" in name.lower():
        return "tortilla_wrap_key", 1.0
    return None, 0.0

def test_cancel_match(cancel_item, order_item):
    print(f"Comparing Cancel '{cancel_item}' vs Order '{order_item}'...")
    
    # 1. Resolve Cancel Item
    cancel_key, _ = resolve_menu_item(cancel_item)
    
    # 2. Resolve Order Item
    order_key, _ = resolve_menu_item(order_item)
    
    match_found = False
    if cancel_key and order_key and cancel_key == order_key:
        match_found = True
    elif order_item.lower() == cancel_item.lower():
        match_found = True
        
    return match_found

print("\n--- TEST 3: Cancel Match Logic ---")
match = test_cancel_match("Tortilla Zinger", "Tortilla Zinger Meal")
print(f"Match Result: {match}")
# Expect: True (because both resolve to same key/mock)
