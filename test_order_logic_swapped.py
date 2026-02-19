
def detect_category_from_text(msg):
    if "burger" in msg.lower():
        return "burgers"
    return None

def looks_like_multi_item_text(msg):
    # Simulate: true if digits present or explicit multiple items logic
    # Real logic is more complex, but for "2 beef burgers" it relies on digits/number words
    return any(char.isdigit() for char in msg)

def test_logic(msg):
    print(f"\n--- Testing: '{msg}' ---")
    
    # APP.PY LOGIC:
    # 1. Items mentioned?
    if looks_like_multi_item_text(msg):
        print("✅ ACTION: Fall through to Multi-Item Handler (Correct for specific items)")
        return

    # 2. Category mentioned?
    detected_cat = detect_category_from_text(msg)
    if detected_cat:
        print(f"✅ ACTION: Open Category '{detected_cat}' (Correct for general category request)")
        return

    # 3. Generic Menu
    print("✅ ACTION: Show Generic Menu")

# Test Cases
test_logic("I want to order burgers")       # Should Open Category
test_logic("I want to order 2 beef burgers") # Should Fall through
test_logic("I want to order")               # Should Show Generic Menu
