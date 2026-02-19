
import re

# Simulate helpers from app.py
def has_explicit_quantity(text: str) -> bool:
    if not text: return False
    t = text.lower()
    if re.search(r"\d+", t): return True
    eng_nums = ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
    if any(re.search(r"\b" + n + r"\b", t) for n in eng_nums): return True
    ar_nums = ["واحد", "اثنين", "ثلاثة"]
    if any(n in t for n in ar_nums): return True
    return False

def has_non_generic_menu_item(text: str) -> bool:
    t = text.lower()
    menu_items = ["chicken burger", "beef burger", "zinger", "fries"] # simplified
    return any(item in t for item in menu_items)

def looks_like_multi_item_text(text: str) -> bool:
    t = text.lower()
    if " and " in t: return True
    if has_explicit_quantity(text): return True
    return False

def detect_category_from_text(text: str) -> str:
    t = text.lower()
    if "burger" in t: return "burgers"
    if "meal" in t: return "meals"
    if "drink" in t: return "drinks"
    return None

def test_logic(msg):
    is_multi_item = looks_like_multi_item_text(msg)
    has_qty = has_explicit_quantity(msg)
    has_specific = has_non_generic_menu_item(msg)
    detected_cat = detect_category_from_text(msg)
    
    # Simulate chat() logic
    if is_multi_item and not has_qty and not has_specific and detected_cat:
        return f"OPEN_CATEGORY: {detected_cat}"
    
    if is_multi_item:
        return "MULTI_ITEM_HANDLER"
        
    if detected_cat:
        return f"OPEN_CATEGORY: {detected_cat}"
        
    return "UNKNOWN"

tests = [
    ("one chicken burger and one beef burger", "MULTI_ITEM_HANDLER"),
    ("burgers and meals", "OPEN_CATEGORY: burgers"),
    ("I want to order burgers", "OPEN_CATEGORY: burgers"),
    ("I want 2 burgers", "MULTI_ITEM_HANDLER"),
    ("chicken burger and beef burger", "MULTI_ITEM_HANDLER"),
    ("Do you have drinks?", "OPEN_CATEGORY: drinks")
]

print("--- REFINED LOGIC TEST ---")
all_pass = True
for msg, expected in tests:
    result = test_logic(msg)
    status = "PASS" if result == expected else "FAIL"
    print(f"MSG: '{msg}'\n  RESULT: {result}\n  EXP:    {expected}\n  STATUS: {status}")
    if status == "FAIL": all_pass = False
    print("-" * 20)

if all_pass:
    print("ALL TESTS PASSED!")
else:
    print("SOME TESTS FAILED!")
