
def detect_category_from_text(msg):
    if "burger" in msg.lower():
        return "burgers"
    return None

def looks_like_multi_item_text(msg):
    # Simulate: true if digits present
    return any(char.isdigit() for char in msg)

def test_logic(msg):
    print(f"\n--- Testing: '{msg}' ---")
    
    # 1. Category Detection
    detected_cat = detect_category_from_text(msg)
    if detected_cat:
        print(f"✅ ACTION: Open Category '{detected_cat}'")
        return

    # 2. Multi-Item Check
    if looks_like_multi_item_text(msg):
        print("✅ ACTION: Fall through to Multi-Item Handler")
        return

    # 3. Generic Menu
    print("✅ ACTION: Show Generic Menu")

# Test Cases
test_logic("I want to order burgers")
test_logic("I want to order 2 beef burgers")
test_logic("I want to order")
