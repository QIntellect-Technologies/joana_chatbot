
import re

def check_hi():
    with open("app.py", "r", encoding="utf-8") as f:
        content = f.read()

    # Extract the list roughly
    start = content.find("IRRELEVANT_TERMS = [")
    if start == -1:
        print("Could not find list start")
        return

    # Find end of list (assuming it ends with "]" at start of line or similar)
    # We can just grab a large chunk
    chunk = content[start:]
    # Parse items
    # Look for strings inside quotes
    items = re.findall(r'"([^"]+)"', chunk)
    
    test_words = ["finish", "cancel", "complete", "add more"]
    print(f"Checking {len(items)} items against {test_words}...")
    
    for word in test_words:
        print(f"--- Checking '{word}' ---")
        for k in items:
            if k in word:
                print(f"MATCH FOUND for '{word}': '{k}'")
            
if __name__ == "__main__":
    check_hi()
