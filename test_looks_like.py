
import re

def is_cancel_text(msg):
    # Mock
    return False

def _normalize_digits(t):
    return t

def looks_like_multi_item_text(msg: str) -> bool:
    if not msg:
        return False

    # ✅ CRITICAL GUARD: cancel/remove/delete text should never be treated as "multi-item add"
    if is_cancel_text(msg):
        return False

    # ✅ Keep original for Arabic separator detection
    original = (msg or "").strip()
    
    # ✅ VOICE FIX: Remove leading 'and', 'w' (common in continuation voice notes)
    # e.g. "and five juices" -> "five juices"
    original = re.sub(r"^(and|w|wa|\u0648)\s+", "", original, flags=re.IGNORECASE).strip()
    
    t = original.lower()
    t = _normalize_digits(t)

    # normalize separators
    t = re.sub(r"[,\n;]+", " , ", t)
    t = re.sub(r"\s+", " ", t).strip()

    # ✅ require at least one letter (english/ar) or menu-ish word
    # prevents "12 2025 30" from being treated as order
    has_word = bool(re.search(r"[a-z\u0600-\u06FF]", t))
    if not has_word:
        return False

    # ✅ CRITICAL FIX: Check for Arabic separator in ORIGINAL text (before lower())
    # Arabic "و" (and) might be affected by lower() in some environments
    has_arabic_separator = " و " in original or "و" in original or " و" in original
    
    # ✅ Count Arabic number words (واحد، اثنين، ثلاثة، أربعة، etc.)
    # Added English number words check too
    has_english_num_word = bool(re.search(r"\b(one|two|three|four|five|six|seven|eight|nine|ten)\b", t))
    has_digit = bool(re.search(r"\d+", t))
    
    # Explicit "and" check
    if " and " in t or has_arabic_separator:
        return True
        
    # Number (digit or word) + Text pattern check
    # e.g. "Five burgers", "2 coffee"
    if (has_digit or has_english_num_word):
        # Allow if it looks like typical order: "qty item"
        if re.search(r"\b(one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+[a-z\u0600-\u06FF]+", t):
            return True

    return False

msg = "I want to order burgers"
print(f"Message: '{msg}'")
res = looks_like_multi_item_text(msg)
print(f"Result: {res}")
