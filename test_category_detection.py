
import sys
import os

# Add current directory to path so we can import nlp_utils
sys.path.append(os.getcwd())

from nlp_utils import detect_category_from_text, detect_intent, CATEGORY_KEYWORDS

msg = "I want to order burgers"
print(f"Message: '{msg}'")

print("Checking CATEGORY_KEYWORDS['burgers']...")
print(CATEGORY_KEYWORDS.get('burgers'))

cat = detect_category_from_text(msg)
print(f"Detected Category: {cat}")

intent = detect_intent(msg)
print(f"Detected Intent: {intent}")
