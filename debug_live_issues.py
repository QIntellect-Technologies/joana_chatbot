
import sys
import os

# Mock dependencies to allow importing app/nlp_utils without full environment
try:
    import pandas as pd
except ImportError:
    from unittest.mock import MagicMock
    sys.modules["pandas"] = MagicMock()

# Add current dir
sys.path.append(os.getcwd())

from nlp_utils import detect_intent, detect_category_from_text
from app import looks_like_multi_item_text, is_wa_greeting

# Test Cases
messages = [
    "I want to order burgers",
    "I want to order burgers and meals",
    "Do you have drinks?"
]

print("--- DEBUGGING LIVE ISSUES ---\n")

for msg in messages:
    print(f"MSG: '{msg}'")
    
    # 1. Intent Detection
    intent = detect_intent(msg)
    print(f"  Intent: {intent}")
    
    # 2. Greeting Check (app.py often checks this separate/first)
    is_greeting = is_wa_greeting(msg)
    print(f"  Is Greeting: {is_greeting}")
    
    # 3. Multi-Item Check
    is_multi = looks_like_multi_item_text(msg)
    print(f"  Looks Like Multi-Item: {is_multi}")
    
    # 4. Category Detection
    cat = detect_category_from_text(msg)
    print(f"  Detected Category: {cat}")
    
    print("-" * 30)
