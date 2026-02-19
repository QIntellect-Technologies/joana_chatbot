
import re

# ==========================================
# MOCKING DEPENDENCIES
# ==========================================

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

def detect_qty(text):
    match = re.search(r"\b(\d+)\b", text)
    if match:
        return int(match.group(1))
    return None

def find_menu_item(text):
    # Mock finding item
    if "tortilla zinger" in text.lower():
        return "Tortilla Zinger"
    return None

def is_cancel_text(text):
    return "cancel" in text.lower()

def normalize_digits(t): return t

# ==========================================
# TEST LOGIC COPIED FROM APP.PY
# ==========================================

def parse_cancel_request(msg: str, lang: str):
    if not msg: return None
    text = msg.strip()
    # if not is_cancel_text(text): return None # specific to app.py loop

    qty = None
    q = detect_qty(text)
    # Simplified regex logic from app.py
    if q:
        qty = max(int(q), 1)
    else:
        qty = 1 

    # Spicy checks simplified
    spicy_flag = "spicy" in text.lower() and "non" not in text.lower()
    
    cleaned = text.lower().replace("cancel", "").replace("spicy", "").replace(str(qty), "").strip()
    item = find_menu_item(cleaned)
    
    return {"qty": qty, "item": item, "spicy": spicy_flag}

def apply_cancel_on_order(state, cancel_req):
    order = state.get("order") or []
    item = cancel_req.get("item")
    qty = cancel_req.get("qty")
    spicy_req = cancel_req.get("spicy")
    
    # simplified matching logic
    matches = []
    for idx, line in enumerate(order):
        if (line.get("item") or "").lower() != item.lower():
            continue
        if spicy_req and not line.get("spicy"):
            continue
        matches.append((idx, line))

    print(f"DEBUG: Found {len(matches)} matches for item '{item}' (Spicy={spicy_req})")

    remaining_to_cancel = int(qty)
    removed_count = 0
    
    # Sorting matches logic from app.py
    # for idx, line in sorted(matches, key=lambda x: x[0]): # logic from app.py
    
    # SIMULATING APP.PY LOGIC:
    for idx, line in matches: 
        if remaining_to_cancel <= 0:
            break
        line_qty = int(line.get("qty", 0))
        
        if remaining_to_cancel >= line_qty:
            remaining_to_cancel -= line_qty
            line["_to_remove"] = True
            removed_count += line_qty
        else:
            line["qty"] -= remaining_to_cancel
            removed_count += remaining_to_cancel
            remaining_to_cancel = 0
            
    return removed_count

# ==========================================
# RUN TESTS
# ==========================================

print("--- TEST 1: Category Detection ---")
msg = "Do you have drinks?"
cat = detect_category_from_text(msg)
print(f"Message: '{msg}' -> Detected Category: {cat}")
# Expect: drinks

print("\n--- TEST 2: Cancel Parsing ---")
msg2 = "cancel 2 spicy tortilla zinger"
parsed = parse_cancel_request(msg2, "en")
print(f"Message: '{msg2}' -> Parsed: {parsed}")
# Expect: qty=2, item='Tortilla Zinger', spicy=True

print("\n--- TEST 3: Apply Cancel Logic ---")
# Setup order state with 2 separate lines of 1 spicy tortilla zinger each
state = {
    "order": [
        {"item": "Tortilla Zinger", "qty": 1, "spicy": 1},
        {"item": "Tortilla Zinger", "qty": 1, "spicy": 1},
        {"item": "Beef Burger", "qty": 1, "spicy": 0}
    ]
}
removed = apply_cancel_on_order(state, parsed)
print(f"Requested Cancel Qty: {parsed['qty']}")
print(f"Actually Removed Qty: {removed}")
# Expect: 2
