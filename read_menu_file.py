
import pandas as pd
import os

menu_path = os.path.join("static", "Menu.xlsx")
print(f"Reading {menu_path}...")

try:
    df = pd.read_excel(menu_path)
    print("Columns:", df.columns.tolist())
    
    print("\n--- ZINGER ITEMS ---")
    for idx, row in df.iterrows():
        en = str(row.get("name_en", "")).lower()
        if "zinger" in en:
            print(f"Row {idx}: {row.get('name_en')} | Cat: {row.get('category')} | ID: {row.get('id')}")

    print("\n--- TORTILLA ITEMS ---")
    for idx, row in df.iterrows():
        en = str(row.get("name_en", "")).lower()
        if "tortilla" in en:
            print(f"Row {idx}: {row.get('name_en')} | Cat: {row.get('category')}")

    print("\n--- CHICKEN BURGERS ---")
    for idx, row in df.iterrows():
        en = str(row.get("name_en", "")).lower()
        if "chicken" in en and "burger" in en:
            print(f"Row {idx}: {row.get('name_en')} | Cat: {row.get('category')}")

except Exception as e:
    print(f"Error reading file: {e}")
