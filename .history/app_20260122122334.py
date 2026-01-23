import json
import os
import re
import tempfile
import requests
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
from flask import Flask, render_template, request, jsonify, session
from nlp_utils import detect_intent, detect_language
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()


import re
def extract_qty_from_text(text: str):
    if not text:
        return None
    m = re.search(r"\b(\d{1,3})\b", text)
    if not m:
        return None
    q = int(m.group(1))
    return q if q > 0 else None
    
    
        
import re

# =========================================================
# ✅ 1) INTELLIGENT MULTI-ITEM HANDLER WITH OPENAI
#    Handles natural language, typos, generic vs specific items
# =========================================================
def handle_multi_item_text(msg_raw, s, MENU, lang):
    """
    INTELLIGENT MULTI-ITEM ORDER HANDLER
    Uses OpenAI to parse natural language orders with:
    - Typo tolerance (cofee→coffee, burgur→burger)
    - Generic vs specific item detection
    - Queue-based step-by-step processing
    - Smart question avoidance (don't ask what we already know)
    """
    # keep lang on state for downstream helpers
    s["lang"] = lang
    
    # ✅ USE NEW INTELLIGENT PARSER
    parsed = parse_intelligent_order(msg_raw, lang)
    all_items = parsed.get("items") or []
    
    print(f"📋 LLM PARSER OUTPUT: {len(all_items)} items extracted from '{msg_raw[:50]}...'")
    print(f"   Items: {all_items}")
    
    if not all_items:
        # Fallback to old detection if LLM returns nothing
        bs_generics = detect_generic_requests_ordered(msg_raw)
        food_generics = detect_food_generic_requests_ordered(msg_raw)
        generics = (food_generics or []) + (bs_generics or [])
    else:
        # Build queue from LLM parse result
        generics = []
        for item in all_items:
            if item.get("type") == "generic":
                generics.append({
                    "kind": item.get("category"),
                    "qty": item.get("qty", 1)
                })
        
        # ✅ CRITICAL FALLBACK: If user said "wraps" but LLM didn't extract sandwich, force add it
        msg_lower = msg_raw.lower()
        has_wrap_word = bool(re.search(r'\b(wrap|wraps|tortilla|tortillas)\b', msg_lower))
        has_sandwich_in_generics = any(g.get("kind") == "sandwich" for g in generics)
        
        if has_wrap_word and not has_sandwich_in_generics:
            # Extract quantity for wraps
            wrap_qty = 1
            match = re.search(r'(\d+)\s*(wrap|wraps|tortilla)', msg_lower)
            if match:
                wrap_qty = int(match.group(1))
            
            print(f"⚠️ FALLBACK: LLM missed wraps! Adding sandwich(qty={wrap_qty}) to generics")
            generics.append({"kind": "sandwich", "qty": wrap_qty})
        
        # ✅ CRITICAL FALLBACK: If user said "wraps" but LLM didn't extract sandwich, force add it
        msg_lower = msg_raw.lower()
        has_wrap_word = bool(re.search(r'\b(wrap|wraps|tortilla|tortillas)\b', msg_lower))
        has_sandwich_in_generics = any(g.get("kind") == "sandwich" for g in generics)
        
        if has_wrap_word and not has_sandwich_in_generics:
            # Extract quantity for wraps
            wrap_qty = 1
            match = re.search(r'(\d+)\s*(wrap|wraps|tortilla)', msg_lower)
            if match:
                wrap_qty = int(match.group(1))
            
            print(f"⚠️ FALLBACK: LLM missed wraps! Adding sandwich(qty={wrap_qty}) to generics")
            generics.append({"kind": "sandwich", "qty": wrap_qty})

    # ✅ normalize generics => always dicts
    norm = []
    for g in (generics or []):
        if isinstance(g, dict):
            norm.append(g)
        elif isinstance(g, str):
            norm.append({"kind": g, "qty": 1})
    generics = norm

    # ✅ merge duplicates by kind to avoid double prompts
    merged = []
    seen = {}
    for g in generics:
        kind = (g.get("kind") or "").strip().lower()
        qty = int(g.get("qty") or 1)
        if kind in seen:
            merged[seen[kind]]["qty"] += qty
        else:
            seen[kind] = len(merged)
            merged.append({"kind": kind, "qty": qty})
    generics = merged

    # ✅ PROCESS SPECIFIC ITEMS FIRST (auto-add with NO extra questions)
    specific_items = [it for it in all_items if it.get("type") == "specific"]
    added_lines = []
    
    for idx, spec in enumerate(specific_items):
        name = spec.get("name", "").strip()
        qty = spec.get("qty", 1)
        spicy = spec.get("spicy", "any")
        category = spec.get("category", "")
        
        # Resolve to MENU key
        resolved, _ = resolve_menu_item(name)
        if not resolved:
            continue
        
        price, cat = get_price_and_category(resolved)
        if price is None or price <= 0:
            continue
        
        # ✅ LARGE ORDER VERIFICATION (100+ items)
        if qty >= 100:
            # Store pending large order in session
            s["stage"] = "confirm_large_order"
            s["pending_large_order"] = {
                "item": resolved,
                "qty": qty,
                "spicy": 0,
                "nonspicy": 0,
                "price": float(price),
                "subtotal": qty * float(price),
                "category": cat
            }
            
            # ✅ CRITICAL: Save remaining items to process after confirmation
            remaining_specific = specific_items[idx + 1:]  # Items after this one
            s["pending_items_queue"] = {
                "specific": remaining_specific,
                "generics": generics,  # Also save generics
                "added_lines": added_lines  # Lines added so far
            }
            
            info = MENU.get(resolved, {})
            display_name = info.get("name_ar") if lang == "ar" else (info.get("name_en") or resolved).title()
            
            confirm_msg = (
                f"⚠️ تريد طلب *{qty} {display_name}*\n\n"
                f"هذه كمية كبيرة جداً! هل أنت متأكد؟\n\n"
                f"💰 الإجمالي: {qty * float(price):.2f} SAR\n\n"
                f"اكتب 'نعم' للتأكيد أو 'لا' للإلغاء"
                if lang == "ar" else
                f"⚠️ You want to order *{qty} {display_name}*\n\n"
                f"This is a very large quantity! Are you sure?\n\n"
                f"💰 Total: {qty * float(price):.2f} SAR\n\n"
                f"Type 'yes' to confirm or 'no' to cancel"
            )
            
            return make_chat_response(confirm_msg, lang)
        
        # ✅ AUTO-ADD specific items (Coffee, Pepsi, etc.) - NO QUESTIONS
        if cat not in ("burgers_meals", "sandwiches"):
            s.setdefault("order", [])
            s["order"].append({
                "item": resolved,
                "qty": qty,
                "spicy": 0,
                "nonspicy": 0,
                "price": float(price),
                "subtotal": qty * float(price)
            })
            info = MENU.get(resolved, {})
            display_name = info.get("name_ar") if lang == "ar" else (info.get("name_en") or resolved).title()
            added_lines.append(f"{qty} {display_name}")
        
        # ✅ Burgers with spicy info → add directly WITHOUT asking
        elif cat == "burgers_meals" and spicy in ("spicy", "non-spicy", "nonspicy"):
            # ✅ LARGE ORDER VERIFICATION (100+ items)
            if qty >= 100:
                s["stage"] = "confirm_large_order"
                is_spicy = 1 if spicy == "spicy" else 0
                is_nonspicy = 1 if spicy in ("non-spicy", "nonspicy") else 0
                s["pending_large_order"] = {
                    "item": resolved,
                    "qty": qty,
                    "spicy": is_spicy,
                    "nonspicy": is_nonspicy,
                    "price": float(price),
                    "subtotal": qty * float(price),
                    "category": cat
                }
                
                # ✅ CRITICAL: Save remaining items to process after confirmation
                remaining_specific = specific_items[idx + 1:]  # Items after this one
                s["pending_items_queue"] = {
                    "specific": remaining_specific,
                    "generics": generics,  # Also save generics
                    "added_lines": added_lines  # Lines added so far
                }
                
                info = MENU.get(resolved, {})
                display_name = info.get("name_ar") if lang == "ar" else (info.get("name_en") or resolved).title()
                spicy_text = "حار" if is_spicy else "غير حار"
                spicy_text_en = "Spicy" if is_spicy else "Non-Spicy"
                
                confirm_msg = (
                    f"⚠️ تريد طلب *{qty} {display_name}* ({spicy_text})\n\n"
                    f"هذه كمية كبيرة جداً! هل أنت متأكد؟\n\n"
                    f"💰 الإجمالي: {qty * float(price):.2f} SAR\n\n"
                    f"اكتب 'نعم' للتأكيد أو 'لا' للإلغاء"
                    if lang == "ar" else
                    f"⚠️ You want to order *{qty} {display_name}* ({spicy_text_en})\n\n"
                    f"This is a very large quantity! Are you sure?\n\n"
                    f"💰 Total: {qty * float(price):.2f} SAR\n\n"
                    f"Type 'yes' to confirm or 'no' to cancel"
                )
                
                return make_chat_response(confirm_msg, lang)
            
            s.setdefault("order", [])
            is_spicy = 1 if spicy == "spicy" else 0
            is_nonspicy = 1 if spicy in ("non-spicy", "nonspicy") else 0
            s["order"].append({
                "item": resolved,
                "qty": qty,
                "spicy": is_spicy,
                "nonspicy": is_nonspicy,
                "price": float(price),
                "subtotal": qty * float(price)
            })
            info = MENU.get(resolved, {})
            display_name = info.get("name_ar") if lang == "ar" else (info.get("name_en") or resolved).title()
            spicy_label = " (Spicy)" if is_spicy else " (Non-Spicy)" if is_nonspicy else ""
            added_lines.append(f"{qty} {display_name}{spicy_label}")
        
        # ✅ Burgers WITHOUT spicy preference → queue for asking
        elif cat == "burgers_meals":
            s.setdefault("spice_queue", [])
            s["spice_queue"].append({"item": resolved, "qty": qty})

    # ✅ ADD ALL GENERICS TO QUEUE (priority: burgers/sandwiches FIRST for better UX, then food items)
    food_only = [
        g for g in (generics or [])
        if g.get("kind") in ("meals", "juices", "drinks", "snacks_sides")
    ]
    
    bs_only = [
        g for g in (generics or [])
        if (g.get("kind") in ("burger", "sandwich"))
    ]

    # ✅ CRITICAL FIX: Add BOTH to queue in priority order (burgers/sandwiches FIRST, then food)
    # This matches user expectations: "5 burgers and 5 sides" → process burgers first
    all_generics_ordered = bs_only + food_only
    
    # ✅ DEBUG: Log queue to track quantity issues
    print("DEBUG: Generics queue being added:", all_generics_ordered)
    
    if all_generics_ordered:
        s.setdefault("generic_queue", [])
        s["generic_queue"].extend(all_generics_ordered)
        
        # Start processing first generic from queue
        prompt = _start_next_generic_from_queue(s, MENU, lang)
        session["state"] = s

        if prompt:
            prefix = (
                ("تمت إضافة: " + "، ".join(added_lines) + "<br><br>")
                if added_lines and lang == "ar"
                else ("Added: " + ", ".join(added_lines) + "<br><br>" if added_lines else "")
            )
            return make_chat_response(prefix + prompt, lang)

    # prefix (show what was added before asking next question)
    prefix = (
        ("تمت إضافة: " + "، ".join(added_lines) + "<br><br>")
        if added_lines and lang == "ar"
        else ("Added: " + ", ".join(added_lines) + "<br><br>" if added_lines else "")
    )

    # ✅ OLD BURGER/SANDWICH SPECIFIC HANDLING (now redundant, kept for safety)
    # This section should never execute if all_generics_ordered worked
    bs_only_fallback = [
        g for g in (generics or [])
        if (g.get("kind") in ("burger", "sandwich")) and g not in all_generics_ordered
    ]

    if bs_only_fallback:
        s.setdefault("generic_queue", [])
        s["generic_queue"].extend(bs_only_fallback)
        nxt = s["generic_queue"].pop(0)

        s["last_qty"] = int(nxt.get("qty") or 1)
        print(f"🔍 DEBUG [generic_queue pop]: Setting last_qty={s['last_qty']} for kind={nxt.get('kind')}")
        s["last_item"] = None

        if nxt.get("kind") == "burger":
            s["stage"] = "await_specific_burger"
            s["burger_page"] = 0
            ask = (
                f"لديك {s['last_qty']} برجر. اختر نوع البرجر."
                if lang == "ar"
                else f"You ordered {s['last_qty']} burger(s). Please choose which burger."
            )
        else:
            s["stage"] = "await_specific_sandwich"
            s["sand_page"] = 0
            ask = (
                f"لديك {s['last_qty']} ساندويتش. اختر نوع الساندويتش."
                if lang == "ar"
                else f"You ordered {s['last_qty']} sandwich(es). Please choose which sandwich."
            )

        session["state"] = s
        return make_chat_response(prefix + ask, lang)

    # ✅ If we have burgers needing spice → ask spice NOW
    if s.get("spice_queue"):
        nxt = s["spice_queue"].pop(0)
        s["last_item"] = nxt["item"]
        s["last_qty"] = int(nxt.get("qty") or 1)
        s["stage"] = "await_spice"
        session["state"] = s

        ask_spice = (
            f"بالنسبة لـ {s['last_qty']} {s['last_item']}، هل تفضلها حارة أم بدون حار؟"
            if lang == "ar"
            else f"For your {s['last_qty']} {s['last_item'].title()}, would you like them spicy or non-spicy?"
        )
        return make_chat_response(prefix + ask_spice, lang)

    # ✅ If we have PENDING GENERIC QUEUE items → process them now
    # This ensures we don't drop items if user just filled a specific request
    prompt = _start_next_generic_from_queue(s, MENU, lang)
    if prompt:
        session["state"] = s
        return make_chat_response(prefix + prompt, lang)

    # ✅ If nothing to process, show error (ONLY if no items added AND no generics present)
    if not added_lines and not generics and not s.get("order"):
        msg = (
            "I couldn't understand your order. Please type 'menu' to see the menu."
            if lang == "en" else
            "لم أفهم طلبك. اكتب 'menu' لعرض القائمة."
        )
        session["state"] = s
        return make_chat_response(msg, lang)

    # ✅ Otherwise show summary with smart confirmation
    summary, total = build_order_summary_and_total(s.get("order") or [], lang)
    s["total"] = total
    s["stage"] = "add_more"
    session["state"] = s

    reply = (
        "✅ ملخص الطلب:<br>" + "<br>".join(summary) + f"<br><br><b>الإجمالي: {total:.2f} {CURRENCY_AR}</b><br><br>هل ترغب في إضافة شيء آخر أم تريد إتمام الطلب؟"
        if lang == "ar"
        else "✅ Order Summary:<br>" + "<br>".join(summary) + f"<br><br><b>Total: {total:.2f} {CURRENCY}</b><br><br>Would you like to add more items or place the order?"
    )
    return make_chat_response(prefix + reply, lang)



def _normalize_digits(s: str) -> str:
    if not s:
        return ""
    # Arabic-Indic digits -> Western
    trans = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
    return s.translate(trans)

def extract_generic_qty_any(text: str, forms):
    """
    forms: list of keywords like ["meal", "meals"]
    Matches:
      - "4 meals" / "meals 4"
      - Arabic digits too (after normalize)
    """
    if not text:
        return None
    t = _normalize_digits(text.lower())

    for kw in forms:
        kw_esc = re.escape(kw)

        # 4 meals
        m = re.search(rf"\b(\d{{1,3}})\s*{kw_esc}\b", t)
        if m:
            q = int(m.group(1))
            return q if q > 0 else None

        # meals 4
        m = re.search(rf"\b{kw_esc}\s*(\d{{1,3}})\b", t)
        if m:
            q = int(m.group(1))
            return q if q > 0 else None

    return None
    
def _norm_text(s: str) -> str:
    s = (s or "").lower().strip()
    s = _normalize_digits(s)
    s = re.sub(r"\s+", " ", s)                  # multi spaces -> one
    s = re.sub(r"[^\w\s\u0600-\u06FF]", "", s)  # remove punctuation (keep arabic)
    return s.strip()


def detect_food_generic_requests_ordered(text: str):
    """
    Returns list of dicts: [{"kind":"meals","qty":2}, {"kind":"drinks","qty":1}, ...]
    Order preserved by first appearance in text.
    """
    if not text:
        return []

    t = _normalize_digits(text.lower())

    specs = [
        ("meals",  ["meal", "meals"]),
        ("juices", ["juice", "juices"]),
        ("drinks", ["drink", "drinks", "coffee", "tea", "pepsi", "water", "cola", "soda", "soft drink", "softdrink"]),
    ]

    hits = []
    for kind, forms in specs:
        # detect keyword existence
        if any(f in t for f in forms):
            qty = extract_generic_qty_any(t, forms) or 1
            pos = min([t.find(f) for f in forms if t.find(f) != -1] or [10**9])
            hits.append((pos, {"kind": kind, "qty": int(qty)}))

    hits.sort(key=lambda x: x[0])
    return [h[1] for h in hits]

def _menu_keys_by_category(MENU: dict, cat: str):
    cat = (cat or "").strip().lower()
    out = []
    for k, info in (MENU or {}).items():
        c = (info.get("category") or "").strip().lower()
        if c == cat:
            out.append(k)
    return out

def _format_category_page(MENU: dict, cat: str, lang: str, page: int = 0, page_size: int = 8, exclude_items: list = None):
    """
    Format a category page, optionally excluding already-ordered items.
    exclude_items: list of menu keys to exclude from display
    """
    keys = _menu_keys_by_category(MENU, cat)
    if not keys:
        return None, None, 0

    # Filter out already-ordered items (case-insensitive comparison)
    if exclude_items:
        exclude_lower = [item.lower() for item in exclude_items if item]
        keys = [k for k in keys if k.lower() not in exclude_lower]
    
    if not keys:
        return None, None, 0

    start = page * page_size
    chunk = keys[start:start+page_size]

    lines = []
    for i, key in enumerate(chunk, start=1):
        info = MENU.get(key, {})
        nm = (info.get("name_ar") if lang == "ar" else info.get("name_en")) or key
        price = info.get("price")
        if price is not None:
            lines.append(f"{i}) {nm} - {price} SAR")
        else:
            lines.append(f"{i}) {nm}")

    has_more = (start + page_size) < len(keys)
    text = "\n".join(lines)

    if lang == "ar":
        footer = "\n\nاكتب الرقم أو الاسم. واكتب (more) لعرض المزيد." if has_more else "\n\nاكتب الرقم أو الاسم."
    else:
        footer = "\n\nType the number or name. Type (more) for next." if has_more else "\n\nType the number or name."

    return text + footer, chunk, len(keys)





def _start_next_generic_from_queue(s: dict, MENU: dict, lang: str):
    """
    Pops next generic (burger/sandwich/meals/juices/drinks) and shows appropriate prompt.
    Excludes already-ordered items from the menu display.
    """
    q = s.get("generic_queue") or []
    if not q:
        return None

    first = q.pop(0)
    s["generic_queue"] = q  # save back

    kind = (first.get("kind") or "").strip().lower()
    qty  = int(first.get("qty") or 1)

    # store qty for selected specific item
    s["last_qty"] = qty
    s["last_kind"] = kind
    s["cat_page"] = 0
    
    # ✅ Get already-ordered items to exclude from menu
    ordered_items = [item.get("item") for item in s.get("order", []) if item.get("item")]

    if kind == "burger":
        s["stage"] = "await_specific_burger"
        s["burger_page"] = 0
        ask_next = (
            f"لديك {qty} برجر. اختر نوع البرجر:"
            if lang == "ar"
            else f"You ordered {qty} burger(s). Please choose which burger:"
        )
        return ask_next

    if kind == "sandwich":
        s["stage"] = "await_specific_sandwich"
        s["sand_page"] = 0
        ask_next = (
            f"لديك {qty} ساندويتش. اختر نوع الساندويتش:"
            if lang == "ar"
            else f"You ordered {qty} sandwich(es). Please choose which sandwich:"
        )
        return ask_next

    if kind == "meals":
        s["stage"] = "await_specific_meal_text"
        title = "Select a meal:" if lang != "ar" else "اختاري وجبة:"
        body, chunk, _ = _format_category_page(MENU, "meals", lang, page=0)
        s["last_page_keys"] = chunk or []
        return f"{title}\n{body}"

    if kind == "juices":
        s["stage"] = "await_specific_juice_text"
        title = "Select a juice:" if lang != "ar" else "اختاري عصير:"
        body, chunk, _ = _format_category_page(MENU, "juices", lang, page=0)
        s["last_page_keys"] = chunk or []
        return f"{title}\n{body}"

    if kind == "drinks":
        s["stage"] = "await_specific_drink_text"
        title = "Select a drink:" if lang != "ar" else "اختاري مشروب:"
        # ✅ Exclude already-ordered drinks (e.g., coffee)
        body, chunk, _ = _format_category_page(MENU, "drinks", lang, page=0, exclude_items=ordered_items)
        s["last_page_keys"] = chunk or []
        return f"{title}\n{body}"

    if kind == "snacks_sides":
        s["stage"] = "await_specific_side_text"
        title = "Select a side/snack:" if lang != "ar" else "اختاري مقبلات/جانبي:"
        body, chunk, _ = _format_category_page(MENU, "snacks_sides", lang, page=0)
        s["last_page_keys"] = chunk or []
        return f"{title}\n{body}"

    # If unknown kind, skip and try next
    return _start_next_generic_from_queue(s, MENU, lang)
    
    
    
def _resolve_text_pick_to_menu_key(MENU: dict, keys_page: list, user_text: str, lang: str):
    if not user_text:
        return None

    t = _normalize_digits(user_text.strip().lower())

    # number pick
    m = re.fullmatch(r"\d{1,3}", t)
    if m:
        idx = int(t)
        if 1 <= idx <= len(keys_page):
            return keys_page[idx - 1]
        return None

    # name pick (en/ar)
    for k, info in (MENU or {}).items():
        en = (info.get("name_en") or "").strip().lower()
        ar = (info.get("name_ar") or "").strip().lower()
        if t == en or t == ar:
            return k

    return None


def _resolve_text_pick_to_menu_key_any_in_category(MENU: dict, category: str, user_text: str):
    """
    Search for a menu item by name (en/ar) within a specific category.
    Returns menu key if found, None otherwise.
    """
    if not user_text:
        return None

    t = _normalize_digits(user_text.strip().lower())

    # Search for exact name match within the category
    for k, info in (MENU or {}).items():
        cat = (info.get("category") or info.get("cat") or info.get("Category") or "").strip().lower()
        if cat != category.lower():
            continue
            
        en = (info.get("name_en") or "").strip().lower()
        ar = (info.get("name_ar") or "").strip().lower()
        if t == en or t == ar:
            return k

    return None


# ---------------------------------------
# Generic category aliases (user text -> canonical kind)
# ---------------------------------------
GENERIC_ALIASES = {
    # meals
    "meal": "meals", "meals": "meals",
    # juices
    "juice": "juices", "juices": "juices",
    # drinks
    "drink": "drinks", "drinks": "drinks",
    "soda": "drinks", "cola": "drinks", "softdrink": "drinks", "soft drink": "drinks",
}

# Stage mapping per kind
KIND_TO_STAGE = {
    "meals":  "await_specific_meal",
    "juices": "await_specific_juice",
    "drinks": "await_specific_drink",

    # ✅ add these
    "burger": "await_specific_burger",
    "sandwich": "await_specific_sandwich",
}


# Menu category mapping (aapke Excel categories -> your internal naming)
# IMPORTANT: yahan aap apne actual category names match karein.
# Example: if your MENU stores category as "Meals" or "meals" etc.
CANON_MENU_CATS = {
    "meals":  {"meals", "meal", "Meals"},
    "juices": {"juices", "juice", "Juices"},
    "drinks": {"drinks", "drink", "Drinks"},
}

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())

def _extract_qty_near_keyword(t: str, keyword: str):
    """
    Matches:
      2 meals
      meals 2
      (qty missing -> None)
    """
    t = _norm(t)
    kw = re.escape(keyword)

    # 2 meals
    m = re.search(rf"\b(\d{{1,3}})\s*{kw}\b", t)
    if m:
        q = int(m.group(1))
        return q if q > 0 else None

    # meals 2
    m = re.search(rf"\b{kw}\s*(\d{{1,3}})\b", t)
    if m:
        q = int(m.group(1))
        return q if q > 0 else None

    return None

def detect_food_generic_requests_ordered(text: str):
    """
    Returns generics IN ORDER OF APPEARANCE:
      [{"kind":"meals","qty":None}, {"kind":"juices","qty":2}, ...]
    qty=None means: user did NOT provide quantity and we must ask later.
    """
    t = _norm(text)
    if not t:
        return []

    hits = []

    for alias, kind in GENERIC_ALIASES.items():
        for m in re.finditer(rf"\b{re.escape(alias)}\b", t):
            pos = m.start()
            qty = _extract_qty_near_keyword(t, alias)   # None if missing
            hits.append((pos, kind, qty))

    if not hits:
        return []

    hits.sort(key=lambda x: x[0])

    merged = []
    seen = set()
    for _, kind, qty in hits:
        if kind in seen:
            continue
        seen.add(kind)
        merged.append({"kind": kind, "qty": qty})  # ✅ keep None
    return merged


def _menu_items_for_kind(MENU: dict, kind: str):
    """
    Returns list of tuples: (menu_key, display_name)
    Uses MENU[menu_key]["name_en"] if available, else menu_key.
    Filters strictly by category in CANON_MENU_CATS.
    """
    allowed = CANON_MENU_CATS.get(kind, set())
    out = []

    for k, info in (MENU or {}).items():
        # Determine category
        cat = (info.get("category") or info.get("cat") or info.get("Category") or "")
        cat = str(cat).strip().lower()


        if cat not in allowed:
            continue

        disp = (info.get("name_en") or info.get("name") or k)
        disp = str(disp).strip()
        out.append((k, disp))

    # Stable ordering
    out.sort(key=lambda x: x[1].lower())
    return out

def _render_pick_list(MENU: dict, kind: str, qty: int, lang: str):
    """
    Returns:
      msg_text, options_keys, options_disp
    """
    items = _menu_items_for_kind(MENU, kind)
    if not items:
        if lang == "ar":
            return "لا توجد عناصر متاحة في هذه الفئة حاليا.", [], []
        return "No items available in this category right now.", [], []

    # Keep list not too long; still text-based stable UX
    max_show = 20
    shown = items[:max_show]

    title_map = {
        "meals":  ("Meals me se 1 select karein", "اختر وجبة واحدة"),
        "juices": ("Juices me se 1 select karein", "اختر عصيرًا واحدًا"),
        "drinks": ("Drinks me se 1 select karein", "اختر مشروبًا واحدًا"),
    }
    title_en, title_ar = title_map.get(kind, ("Select one item", "اختر عنصرًا واحدًا"))

    if lang == "ar":
        lines = [f"{title_ar} (الكمية: {qty}):"]
    else:
        lines = [f"{title_en} (qty: {qty}):"]

    for i, (_, disp) in enumerate(shown, start=1):
        lines.append(f"{i}) {disp}")

    if len(items) > max_show:
        if lang == "ar":
            lines.append("اكتب الاسم بالضبط (حتى لو لم يظهر في القائمة المختصرة).")
        else:
            lines.append("You can also type the exact name (even if not shown in the short list).")

    keys = [k for k, _ in items]          # full keys for validation by name too
    disp_all = [d for _, d in items]      # full display list
    return "\n".join(lines), keys, disp_all

def _resolve_selection_to_menu_key(MENU: dict, kind: str, user_input: str, options_disp_all: list, options_keys_all: list):
    """
    Accepts number OR name.
    Returns resolved menu_key or None.
    """
    txt = (user_input or "").strip()
    if not txt:
        return None

    # Number selection (from the rendered *short list* needs stored 'last_short_keys')
    if re.fullmatch(r"\d{1,3}", txt):
        return "__NUM__:" + txt  # resolved later using last_short_keys

    # Name selection: match against name_en (case-insensitive) OR exact MENU key
    t = txt.lower()

    # Direct key match
    if t in {str(k).lower(): k for k in options_keys_all}.keys():
        for k in options_keys_all:
            if str(k).lower() == t:
                return k

    # Display name match
    for k, info in MENU.items():
        cat = (info.get("category") or info.get("cat") or info.get("Category") or "")
        if str(cat).strip() not in CANON_MENU_CATS.get(kind, set()):
            continue
        nm = (info.get("name_en") or info.get("name") or "").strip().lower()
        if nm and nm == t:
            return k

    return None

def _add_line_item(s: dict, menu_key: str, qty: int, note: str = ""):
    s.setdefault("order", [])

    price, _cat = get_price_and_category(menu_key)
    if price is None:
        price = 0

    s["order"].append({
        "item": menu_key,
        "qty": int(qty or 1),
        "spicy": 0,
        "nonspicy": 0,
        "price": float(price),
        "subtotal": float(price) * int(qty or 1),
        "note": note or "",
    })


def _start_next_generic(s: dict, MENU: dict, lang: str):
    q = s.get("generic_queue") or []
    if not q:
        s["stage"] = "add_more"
        for k in (
            "last_qty", "last_kind", "last_qty_missing",
            "last_options_keys_all", "last_options_disp_all", "last_short_keys"
        ):
            s.pop(k, None)
        return None

    nxt = q.pop(0)
    s["generic_queue"] = q

    kind = (nxt.get("kind") or "").strip().lower()
    qty_raw = nxt.get("qty")  # may be None

    stage = KIND_TO_STAGE.get(kind)
    if not stage:
        return _start_next_generic(s, MENU, lang)

    s["stage"] = stage
    s["last_kind"] = kind

    # ✅ qty handling
    s["last_qty_missing"] = (qty_raw is None)
    s["last_qty"] = int(qty_raw) if qty_raw is not None else 0

    # ✅ always compute a safe qty to show/use
    qty = int(s.get("last_qty") or 1)

    # ✅ burger/sandwich: webhook will show buttons based on stage
    if kind == "burger":
        s["burger_page"] = 0
        return (
            f"لديك {qty} برجر. اختر نوع البرجر."
            if lang == "ar"
            else f"You ordered {qty} burger(s). Please choose which burger."
        )

    if kind == "sandwich":
        s["sand_page"] = 0
        return (
            f"لديك {qty} ساندويتش. اختر نوع الساندويتش."
            if lang == "ar"
            else f"You ordered {qty} sandwich(es). Please choose which sandwich."
        )

    # ✅ meals/juices/drinks: render text list
    msg, keys_all, disp_all = _render_pick_list(MENU, kind, qty, lang)
    s["last_options_keys_all"] = keys_all
    s["last_options_disp_all"] = disp_all

    short_items = _menu_items_for_kind(MENU, kind)[:20]
    s["last_short_keys"] = [k for k, _ in short_items]

    return msg


# ---------------------------
# ENV VARIABLES
# ---------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
FLASK_SECRET = os.getenv("FLASK_SECRET_KEY", "joana_fastfood_secret")

# WhatsApp Cloud API envs
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
WHATSAPP_VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "joana-verify-token-123")
WHATSAPP_API_BASE = "https://graph.facebook.com/v21.0"

# Deepgram API key (for online STT)
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")

# Supabase REST envs
SUPABASE_PROJECT_URL = os.getenv("SUPABASE_PROJECT_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")  # not used in backend, kept
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_REST_URL = (
    SUPABASE_PROJECT_URL.rstrip("/") + "/rest/v1" if SUPABASE_PROJECT_URL else None
)

# Optional: if your customers table has last_seen_utc/local columns, set this to "1"
CUSTOMERS_HAS_LAST_SEEN = os.getenv("CUSTOMERS_HAS_LAST_SEEN", "0") == "1"

# Cron secret
CRON_SECRET = os.getenv("CRON_SECRET", "joana-cron-secret")


def _mask(val: str | None) -> str:
    """Return a safe diagnostic string without exposing secrets."""
    if not val:
        return "missing"
    tail = val[-4:] if len(val) >= 4 else "****"
    return f"len={len(val)}, tail=***{tail}"

# ---------------------------
# Flask Config
# ---------------------------
app = Flask(__name__, static_folder="static", template_folder="templates")
app.secret_key = FLASK_SECRET

if not OPENAI_API_KEY:
    print("Warning: OPENAI_API_KEY is not set; OpenAI requests will fail until it is configured.")
    client = None
else:
    tail = OPENAI_API_KEY[-4:] if len(OPENAI_API_KEY) >= 4 else "****"
    print(f"OPENAI_API_KEY detected (length={len(OPENAI_API_KEY)}, masked=***{tail})")
    client = OpenAI(api_key=OPENAI_API_KEY)


def log_env_summary():
    print(
        "ENV STATUS ->",
        f"OPENAI_API_KEY={_mask(OPENAI_API_KEY)} |",
        f"SUPABASE_SERVICE_ROLE_KEY={_mask(SUPABASE_SERVICE_ROLE_KEY)} |",
        f"WHATSAPP_TOKEN={_mask(WHATSAPP_TOKEN)} |",
        f"DEEPGRAM_API_KEY={_mask(DEEPGRAM_API_KEY)}",
    )


# Log key env presence (masked) at startup
log_env_summary()

# NOTE: In production, change redirect to your domain (not 127.0.0.1)
PAYMENT_URL = (
    "https://starlit-sopapillas-520aa2.netlify.app/"
    "?redirect=http://127.0.0.1:5000/thankyou"
)
CURRENCY = "SAR"
CURRENCY_AR = "ريال سعودي"

FEEDBACK_DELAY_MINUTES = 2  # Feedback sent 2 minutes after payment

# ---------------------------
# Paths / Directories
# ---------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
MENU_FILE = os.path.join(DATA_DIR, "Menu.xlsx")
BRANCHES_FILE = os.path.join(DATA_DIR, "Branches.xlsx")

# Runtime stores
WHATSAPP_SESSIONS = {}   # phone -> {"state": {...}, "messages": [...], "lang": "en"/"ar"}
WA_CATEGORY_STATE = {}   # phone -> {"category": str, "index": int}
FEEDBACK_PENDING = {}    # phone -> {"order_id": int, "rating": str, "awaiting_remarks": bool}

# =========================================================
# WhatsApp Cloud SEND HELPERS
# =========================================================
def send_whatsapp_text(to_number: str, text: str):
    if not (WHATSAPP_TOKEN and WHATSAPP_PHONE_NUMBER_ID):
        print("WHATSAPP_TOKEN/PHONE_NUMBER_ID missing, cannot send WhatsApp message.")
        return

    url = f"{WHATSAPP_API_BASE}/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": text},
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        print("CLOUD SEND:", resp.status_code, resp.text)
    except Exception as e:
        print("Error sending WhatsApp:", repr(e))


def send_whatsapp_image(to_number: str, image_url: str, caption: str = ""):
    if not (WHATSAPP_TOKEN and WHATSAPP_PHONE_NUMBER_ID):
        print("WHATSAPP_TOKEN/PHONE_NUMBER_ID missing, cannot send WhatsApp image.")
        return False

    url = f"{WHATSAPP_API_BASE}/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "image",
        "image": {"link": image_url, "caption": caption},
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        print("CLOUD IMAGE:", resp.status_code, resp.text)
        return resp.status_code == 200
    except Exception as e:
        print("Error sending image:", repr(e))
        return False


def send_whatsapp_quick_buttons(to_number: str, body_text: str, buttons: list):
    if not (WHATSAPP_TOKEN and WHATSAPP_PHONE_NUMBER_ID):
        print("WHATSAPP_TOKEN/PHONE_NUMBER_ID missing, cannot send buttons.")
        return False

    url = f"{WHATSAPP_API_BASE}/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}

    cloud_buttons = []
    for b in buttons[:3]:
        raw_title = str(b.get("title", "") or "").strip()
        title = raw_title if raw_title else "Button"
        if len(title) > 20:
            title = title[:17].rstrip() + "..."
        button_id = str(b.get("id") or title)
        cloud_buttons.append({"type": "reply", "reply": {"id": button_id, "title": title}})

    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body_text},
            "action": {"buttons": cloud_buttons},
        },
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        print("CLOUD BUTTONS:", resp.status_code, resp.text)
        resp.raise_for_status()
        return True
    except Exception as e:
        print("Error sending buttons:", repr(e))
        return False

# =========================================================
# FEEDBACK HELPERS
# =========================================================
def build_feedback_question_and_buttons(lang: str):
    lang = (lang or "en").lower()
    if lang.startswith("ar"):
        question = "كيف كانت تجربتك مع مطعم جوانا للوجبات السريعة؟"
        buttons = [
            {"id": "feedback_excellent", "title": "ممتاز"},
            {"id": "feedback_satisfied", "title": "مرضي"},
            {"id": "feedback_not_satisfied", "title": "غير مرضي"},
        ]
    else:
        question = "How was your experience with Joana Fast Food?"
        buttons = [
            {"id": "feedback_excellent", "title": "Excellent"},
            {"id": "feedback_satisfied", "title": "Satisfied"},
            {"id": "feedback_not_satisfied", "title": "Not satisfied"},
        ]
    return question, buttons

# =========================================================
# SUPABASE HELPERS
# =========================================================
def supabase_headers(prefer: str | None = None) -> dict:
    if not (SUPABASE_REST_URL and SUPABASE_SERVICE_ROLE_KEY):
        raise RuntimeError("Supabase REST env vars not configured")
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def normalize_wh_number(raw: str) -> str:
    if not raw:
        return ""
    raw = str(raw).strip()
    return raw[1:] if raw.startswith("+") else raw


def get_dual_timestamp(local_timezone: str = "Asia/Karachi") -> dict:
    utc_now = datetime.now(tz=ZoneInfo("UTC"))
    local_now = utc_now.astimezone(ZoneInfo(local_timezone))
    return {
        "utc_timestamp": utc_now.isoformat(),
        "local_timestamp": local_now.isoformat(),
        "timezone_used": local_timezone,
    }


# =========================================================
# ✅ FIXED: preserve created_at on returning customers
# ✅ FIXED: last_seen_* optional (avoid PGRST204)
# =========================================================
def upsert_customer(
    phone_number: str,
    whatsapp_name: str | None = None,
    lang: str | None = None
) -> int | None:
    phone_number = normalize_wh_number(phone_number)

    if not SUPABASE_REST_URL:
        print("Supabase REST not configured; upsert_customer skipped.")
        return None

    ts = get_dual_timestamp()

    # 1) If exists -> PATCH mutable fields (DO NOT overwrite created_at_*)
    try:
        url_get = f"{SUPABASE_REST_URL}/customers"
        params = {
            "select": "id",
            "phone_number": f"eq.{phone_number}",
            "limit": 1,
        }

        r = requests.get(
            url_get,
            headers=supabase_headers(),
            params=params,
            timeout=20,
        )
        r.raise_for_status()
        rows = r.json() or []

        if rows:
            cust_id = rows[0]["id"]

            patch_url = f"{SUPABASE_REST_URL}/customers?id=eq.{cust_id}"
            patch_payload = {}

            # only update if value exists (avoid overwriting with NULL)
            if whatsapp_name and str(whatsapp_name).strip():
                patch_payload["whatsapp_name"] = str(whatsapp_name).strip()

            if lang and lang in ("en", "ar"):
                patch_payload["preferred_language"] = lang

            # always update last seen
            patch_payload["last_seen_at"] = ts["utc_timestamp"]

            pr = requests.patch(
                patch_url,
                headers=supabase_headers("return=minimal"),
                json=patch_payload,
                timeout=20,
            )
            print("Supabase customers patch:", pr.status_code, pr.text)
            pr.raise_for_status()

            return cust_id

    except Exception as e:
        print("Supabase customers get/patch error:", repr(e))

    # 2) Not found -> INSERT with created_at_*
    try:
        url_ins = f"{SUPABASE_REST_URL}/customers"
        payload_obj = {
            "phone_number": phone_number,
            "whatsapp_name": whatsapp_name,
            "preferred_language": lang,
            "created_at_utc": ts["utc_timestamp"],
            "created_at_local": ts["local_timestamp"],
            "last_seen_at": ts["utc_timestamp"],  # ✅ first seen
        }
        if CUSTOMERS_HAS_LAST_SEEN:
            payload_obj["last_seen_utc"] = ts["utc_timestamp"]
            payload_obj["last_seen_local"] = ts["local_timestamp"]

        resp = requests.post(
            url_ins,
            headers=supabase_headers("return=representation"),
            json=[payload_obj],
            timeout=20,
        )
        print("Supabase customers insert:", resp.status_code, resp.text)
        resp.raise_for_status()

        rows = resp.json() or []
        return rows[0]["id"] if rows else None

    except Exception as e:
        print("Supabase customers insert error:", repr(e))
        return None


def save_message(customer_id, order_id, direction, message_type, text, audio_url, is_voice, language, raw_payload):
    if customer_id is None or not SUPABASE_REST_URL:
        return
    url = f"{SUPABASE_REST_URL}/messages"
    ts = get_dual_timestamp()
    payload = [{
        "customer_id": customer_id,
        "order_id": order_id,
        "direction": direction,
        "message_type": message_type,
        "text": text,
        "audio_url": audio_url,
        "is_voice": is_voice,
        "language": language,
        "raw_payload": json.dumps(raw_payload) if raw_payload else None,
        "sent_at_utc": ts["utc_timestamp"],
        "sent_at_local": ts["local_timestamp"],
    }]
    try:
        resp = requests.post(url, headers=supabase_headers("return=minimal"), json=payload, timeout=20)
        print("Supabase save_message:", resp.status_code, resp.text)
        resp.raise_for_status()
    except Exception as e:
        print("Supabase save_message error:", repr(e))


# =========================================================
# ✅ FIXED: feedback timestamps (avoid null)
# =========================================================
def create_order_feedback(order_id: int, rating: str, remarks: str | None = None):
    if not order_id or not SUPABASE_REST_URL:
        return
    url = f"{SUPABASE_REST_URL}/order_feedback"
    ts = get_dual_timestamp()
    payload = [{
        "order_id": order_id,
        "rating": rating,
        "remarks": remarks or None,
        "created_at_utc": ts["utc_timestamp"],
        "created_at_local": ts["local_timestamp"],
    }]
    try:
        resp = requests.post(url, headers=supabase_headers("return=minimal"), json=payload, timeout=20)
        print("Supabase order_feedback:", resp.status_code, resp.text)
        resp.raise_for_status()
    except Exception as e:
        print("Supabase order_feedback error:", repr(e))


def cancel_order_in_db(order_id: int | None) -> None:
    if not order_id or not SUPABASE_REST_URL:
        return
    url = f"{SUPABASE_REST_URL}/orders?id=eq.{order_id}"
    payload = {"status": "cancelled"}
    try:
        resp = requests.patch(url, headers=supabase_headers("return=minimal"), json=payload, timeout=20)
        print("Supabase cancel_order:", resp.status_code, resp.text)
        resp.raise_for_status()
    except Exception as e:
        print("Supabase cancel_order error:", repr(e))


def update_order_payment(order_id: int | None, method: str, status: str) -> None:
    if not order_id or not SUPABASE_REST_URL:
        return
    url = f"{SUPABASE_REST_URL}/orders?id=eq.{order_id}"
    ts = get_dual_timestamp()
    payload = {
        "payment_method": method,
        "payment_status": status,
        "payment_time_utc": ts["utc_timestamp"],
    }
    try:
        resp = requests.patch(url, headers=supabase_headers("return=minimal"), json=payload, timeout=20)
        print("Supabase update_payment:", resp.status_code, resp.text)
        resp.raise_for_status()
    except Exception as e:
        print("Supabase update_payment error:", repr(e))

def save_feedback(order_id: int | None, rating: str, comment: str) -> None:
    """Save customer feedback to Supabase"""
    if not order_id or not SUPABASE_REST_URL:
        return
    
    url = f"{SUPABASE_REST_URL}/order_feedback"
    ts = get_dual_timestamp()
    payload = {
        "order_id": order_id,
        "rating": rating,
        "comment": comment,
        "feedback_time_utc": ts["utc_timestamp"],
        "feedback_time_sa": ts["sa_timestamp"],
    }
    try:
        resp = requests.post(url, headers=supabase_headers("return=minimal"), json=payload, timeout=20)
        print(f"Supabase save_feedback: {resp.status_code}")
        resp.raise_for_status()
    except Exception as e:
        print(f"Supabase save_feedback error: {repr(e)}")


# =========================================================
# ✅ Schedule feedback ONLY after payment (cash or paid)
# =========================================================
def schedule_feedback_after_payment(order_id: int | None) -> None:
    if not order_id or not SUPABASE_REST_URL:
        if not order_id:
            print("❌ Cannot schedule feedback: order_id is None!")
        return

    utc_now = datetime.now(tz=ZoneInfo("UTC"))
    feedback_due = utc_now + timedelta(minutes=FEEDBACK_DELAY_MINUTES)

    url = f"{SUPABASE_REST_URL}/orders?id=eq.{order_id}"
    payload = {
        "feedback_due_at_utc": feedback_due.isoformat(),
        "feedback_sent": False,
    }

    try:
        resp = requests.patch(url, headers=supabase_headers("return=minimal"), json=payload, timeout=20)
        print(f"✅ Feedback scheduled for order {order_id} at {feedback_due.strftime('%H:%M:%S')} UTC ({FEEDBACK_DELAY_MINUTES} min from now)")
        print("Supabase schedule_feedback:", resp.status_code, resp.text)
        resp.raise_for_status()
    except Exception as e:
        print("Supabase schedule_feedback error:", repr(e))
        
        



def canonical_category(raw_category: str, name_en: str = "") -> str:
    c = (raw_category or "").strip().lower()
    n = (name_en or "").strip().lower()

    # ---------
    # Direct category from Excel (preferred)
    # ---------
    if c in ("meals", "meal"):
        return "meals"
    if c in ("juices", "juice"):
        return "juices"
    if c in ("drinks", "drink", "beverages", "beverage"):
        return "drinks"

    # Keep your existing main buckets too (optional)
    if c in ("burgers_meals", "burger_meals", "burgers", "burger"):
        return "burgers_meals"
    if c in ("sandwiches", "sandwich", "wraps", "wrap", "tortilla"):
        return "sandwiches"
    if c in ("snacks_sides", "snacks", "snack", "sides", "side"):
        return "snacks_sides"

    # ---------
    # Fallback inference from item name (when Excel category missing/wrong)
    # ---------
    if any(k in n for k in ("juice", "orange", "mango", "cocktail")):
        return "juices"

    if any(k in n for k in ("cola", "coke", "pepsi", "sprite", "7up", "water", "coffee", "tea")):
        return "drinks"

    # If user typed/Excel category says "meal" in name but category missing
    if " meal" in n or n.endswith("meal"):
        return "meals"

    # Otherwise keep empty/other
    return c or ""


# =========================================================
# EXCEL LOADERS
# =========================================================
ALL_MENU_ITEM_NAMES_LOWER = set()
NAME_TO_KEY = {}

def load_menu():
    try:
        df_raw = pd.read_excel(MENU_FILE, header=None, sheet_name=0)

        header_row_index = None
        for i, row in df_raw.iterrows():
            row_text = " ".join([str(x).strip().lower() for x in row.values if str(x) != "nan"])
            if "name_en" in row_text and "price" in row_text:
                header_row_index = i
                break

        if header_row_index is None:
            print("⚠ Could not find header row containing 'name_en' and 'price'.")
            return {}

        df = pd.read_excel(MENU_FILE, header=header_row_index, sheet_name=0)
        df.columns = [str(c).strip().lower() for c in df.columns]

        required = ["name_en", "price"]
        for col in required:
            if col not in df.columns:
                raise Exception(f"Missing required column: {col}. Found: {list(df.columns)}")

        cat_col = "category" if "category" in df.columns else None
        ar_col  = "name_ar"  if "name_ar" in df.columns else None
        id_col  = "id"       if "id" in df.columns else None

        menu = {}

        for _, row in df.iterrows():
            en = str(row.get("name_en", "")).strip()
            if not en or en.lower() == "nan":
                continue

            en_key = en.strip().lower()

            price = row.get("price", None)
            try:
                price = float(price)
            except Exception:
                continue

            raw_cat = str(row.get(cat_col, "")).strip() if cat_col else ""
            cat_final = canonical_category(raw_cat, en)
            cat_final = str(cat_final).strip().lower()

            ar = str(row.get(ar_col, "")).strip() if ar_col else ""
            if ar.lower() == "nan":
                ar = ""

            excel_id = None
            if id_col:
                v = row.get(id_col, None)
                try:
                    if pd.notna(v):
                        excel_id = int(v)
                except Exception:
                    excel_id = None

            menu[en_key] = {
                "id": excel_id,
                "price": price,
                "category": cat_final,
                "name_en": en,
                "name_ar": ar or en,
            }

        # ✅ THIS MUST BE OUTSIDE THE LOOP
        print(f"✅ Loaded {len(menu)} menu items.")

        # ✅ Build global name indexes
        global ALL_MENU_ITEM_NAMES_LOWER, NAME_TO_KEY
        ALL_MENU_ITEM_NAMES_LOWER = set()
        NAME_TO_KEY = {}

        for k, info in menu.items():
            en = _norm_text(info.get("name_en") or "")
            ar = _norm_text(info.get("name_ar") or "")

            if en:
                ALL_MENU_ITEM_NAMES_LOWER.add(en)
                NAME_TO_KEY[en] = k
            if ar:
                ALL_MENU_ITEM_NAMES_LOWER.add(ar)
                NAME_TO_KEY[ar] = k

        return menu

    except Exception as e:
        print("Menu load failed:", repr(e))
        return {}


def load_branches():
    try:
        df_raw = pd.read_excel(BRANCHES_FILE, header=None)
        header_row_index = None
        for i, row in df_raw.iterrows():
            row_l = [str(c).lower() for c in row]
            if any("branch" in c for c in row_l) and any("address" in c for c in row_l):
                header_row_index = i
                break
        if header_row_index is None:
            header_row_index = 0

        df = pd.read_excel(BRANCHES_FILE, header=header_row_index)

        name_col = next((c for c in df.columns if "branch" in str(c).lower()), None)
        addr_col = next((c for c in df.columns if "address" in str(c).lower()), None)
        phone_col = next((c for c in df.columns if "phone" in str(c).lower() or "number" in str(c).lower()), None)

        branches = []
        for _, row in df.iterrows():
            branches.append({
                "Branch Name": str(row.get(name_col, "")).strip(),
                "Address / Area": str(row.get(addr_col, "")).strip(),
                "Phone Number": str(row.get(phone_col, "")).strip(),
            })
        branches = [b for b in branches if (b["Branch Name"] or b["Address / Area"] or b["Phone Number"])]
        print(f"✅ Loaded {len(branches)} branches.")
        return branches
    except Exception as e:
        print("❌ Branch load failed:", repr(e))
        return []

MENU = load_menu()
BRANCHES = load_branches()

# =========================================================
# UI / MESSAGE HELPERS
# =========================================================
def build_branches_message(lang: str = "en") -> str:
    lines = []
    for b in BRANCHES[:6]:
        name = b.get("Branch Name", "")
        addr = b.get("Address / Area", "")
        phone = b.get("Phone Number", "")
        if phone:
            lines.append(f"- {name} – {addr} | {phone}")
    branches_text = "\n".join(lines) if lines else ("Branches info not available." if lang != "ar" else "معلومات الفروع غير متوفرة.")

    if lang == "ar":
        return (
            "مرحباً بك في مطعم جوانا للوجبات السريعة!\n\n"
            "الفروع:\n"
            f"{branches_text}\n\n"
            "من فضلك اختر طريقة الطلب:"
        )
    return (
        "Welcome to JOANA Fast Food!\n\n"
        "Branches:\n"
        f"{branches_text}\n\n"
        "Please choose an option:"
    )


def html_to_whatsapp(text: str) -> str:
    if not text:
        return ""
    text = text.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")

    def replace_anchor(match):
        full_tag = match.group(0)
        label = match.group(1).strip()
        href_match = re.search(r'href=[\'"]([^\'"]+)[\'"]', full_tag, flags=re.IGNORECASE)
        if not href_match:
            return label
        url = href_match.group(1).strip()
        if url.startswith("tel:"):
            return label
        return f"{label}: {url}"

    text = re.sub(r"<a[^>]*>(.*?)</a>", replace_anchor, text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()

# =========================================================
# GREETINGS
# =========================================================
WA_GREETINGS = [
    "hi", "hello", "hey", "salam", "slam", "asalam", "assalam",
    "assalam o alaikum", "assalamu alaikum", "السلام عليكم", "مرحبا",
]

def is_wa_greeting(text: str) -> bool:
    if not text:
        return False
    t = text.strip().lower()
    t = re.sub(r"[^\w\u0600-\u06FF ]+", "", t)
    return t in WA_GREETINGS

# =========================================================
# BASIC UTILITIES
# =========================================================
def polite_check(text):
    bad = ["idiot", "stupid", "لعنة", "غبي"]
    return any(w in (text or "").lower() for w in bad)


def _normalize_digits(txt: str) -> str:
    if not txt:
        return ""
    arabic_digit_map = {"٠":"0","١":"1","٢":"2","٣":"3","٤":"4","٥":"5","٦":"6","٧":"7","٨":"8","٩":"9"}
    for ar, en in arabic_digit_map.items():
        txt = txt.replace(ar, en)
    return txt


def detect_qty(msg: str) -> int:
    """Smart quantity detection with natural language support"""
    if not msg:
        return 1
    text = msg.lower().strip()
    text = _normalize_digits(text)
    
    # Natural language quantities (English & Arabic)
    natural_qty = {
        "a ": 1, "an ": 1, "one ": 1, "واحد": 1,
        "couple": 2, "two": 2, "اثنين": 2, "اتنين": 2,
        "few": 3, "some": 3, "several": 3, "بعض": 3,
        "many": 5, "كثير": 5,
        "dozen": 12, "دزينة": 12,
    }
    
    for phrase, qty in natural_qty.items():
        if phrase in text:
            return qty
    
    # Numeric detection
    m = re.search(r"\b(\d+)\b", text)
    if m:
        try:
            q = int(m.group(1))
            return q if q > 0 else 1
        except Exception:
            pass

    number_words_en = {"one":1,"two":2,"three":3,"four":4,"five":5,"six":6,"seven":7,"eight":8,"nine":9,"ten":10}
    for word, value in number_words_en.items():
        if re.search(r"\b" + re.escape(word) + r"\b", text):
            return value

    number_words_ar = {
        "واحد":1,"واحدة":1,"اثنين":2,"اتنين":2,"ثنين":2,
        "ثلاثة":3,"ثلاث":3,"اربعة":4,"أربعة":4,"خمسة":5,"ستة":6,"سبعة":7,"ثمانية":8,"تسعة":9,"عشرة":10,
    }
    for word, value in number_words_ar.items():
        if word in text:
            return value

    return 1


def extract_qty_for_generic(msg: str, kind: str) -> int:
    if not msg:
        return 1

    text = _normalize_digits(msg.lower())

    if kind == "sandwich":
        keys = [r"sandwich(?:es)?", r"ساندويتش", r"سندوتش"]
    else:
        keys = [r"burger(?:s)?", r"برجر", r"برغر"]

    key_pat = "(" + "|".join(keys) + ")"

    # ✅ FIX: Handle "2beef burger" (no space between number and word)
    # Pattern 1: "6 sandwich" OR "6sandwich" (with or without space)
    m1 = re.search(r"\b(\d+)\s*" + key_pat, text)
    if m1:
        return max(int(m1.group(1)), 1)

    # Pattern 2: "sandwich 6"
    m2 = re.search(key_pat + r"\s*\b(\d+)\b", text)
    if m2:
        return max(int(m2.group(2)), 1)

    return detect_qty(text) or 1


# ✅ NEW: detect generic burger/sandwich/meals/juices/drinks in text (ordered)
def detect_generic_requests_ordered(msg: str):
    """
    Returns ordered list like:
    [{"kind":"meals","qty":2}, {"kind":"juices","qty":1}, {"kind":"burger","qty":2}, {"kind":"sandwich","qty":1}]
    Only GENERIC (no specific item).
    """
    if not msg:
        return []

    raw = msg
    t = _normalize_digits(msg.lower())
    out = []

    def add(kind, pos):
        # burgers/sandwich: only if NO specific item exists (your existing helpers)
        if kind == "burger" and not msg_has_specific_burger(raw):
            out.append({"kind": "burger", "qty": extract_qty_for_generic(raw, "burger"), "pos": pos})
            return

        if kind == "sandwich" and not msg_has_specific_sandwich(raw):
            out.append({"kind": "sandwich", "qty": extract_qty_for_generic(raw, "sandwich"), "pos": pos})
            return

        # meals/juices/drinks: only if NO specific menu item name is present in the message
        if kind in ("meals", "juices", "drinks"):
            try:
                names = ALL_MENU_ITEM_NAMES_LOWER or set()
            except Exception:
                names = set()

            has_item_name = any(n and (n in t) for n in names)
            if not has_item_name:
                keyword = "meal" if kind == "meals" else ("juice" if kind == "juices" else "drink")
                out.append({"kind": kind, "qty": extract_qty_for_generic(raw, keyword), "pos": pos})
            return

    # -----------------------
    # burgers
    # -----------------------
    for k in ["burger", "burgers"]:
        p = t.find(k)
        if p != -1:
            add("burger", p)
            break
    if "برجر" in raw or "برغر" in raw:
        add("burger", raw.find("برجر") if "برجر" in raw else raw.find("برغر"))

    # -----------------------
    # sandwiches (including wraps/tortillas)
    # -----------------------
    for k in ["sandwich", "sandwiches", "wrap", "wraps", "tortilla", "tortillas"]:
        p = t.find(k)
        if p != -1:
            add("sandwich", p)
            break
    if "ساندويتش" in raw or "سندوتش" in raw:
        add("sandwich", raw.find("ساندويتش") if "ساندويتش" in raw else raw.find("سندوتش"))

    # -----------------------
    # meals (generic)
    # -----------------------
    for k in ["meal", "meals"]:
        p = t.find(k)
        if p != -1:
            add("meals", p)
            break
    if "وجبة" in raw or "وجبات" in raw:
        add("meals", raw.find("وجبة") if "وجبة" in raw else raw.find("وجبات"))

    # -----------------------
    # juices (generic)
    # -----------------------
    for k in ["juice", "juices"]:
        p = t.find(k)
        if p != -1:
            add("juices", p)
            break
    if "عصير" in raw or "عصائر" in raw:
        add("juices", raw.find("عصير") if "عصير" in raw else raw.find("عصائر"))

    # -----------------------
    # drinks (generic)
    # -----------------------
    for k in ["drink", "drinks", "soft drink", "soft drinks", "soda"]:
        p = t.find(k)
        if p != -1:
            add("drinks", p)
            break
    if "مشروب" in raw or "مشروبات" in raw:
        add("drinks", raw.find("مشروب") if "مشروب" in raw else raw.find("مشروبات"))

    out.sort(key=lambda x: x["pos"])
    for x in out:
        x.pop("pos", None)

    # qty normalization
    for x in out:
        try:
            x["qty"] = int(x.get("qty") or 1)
        except Exception:
            x["qty"] = 1

    return out


def get_price_and_category(name):
    key = (name or "").strip().lower()
    entry = MENU.get(key)

    # ✅ MENU me nahi mila
    if not entry:
        return None, ""

    try:
        price = float(entry.get("price"))
    except Exception:
        price = None

    return price, (entry.get("category") or "")

# =========================================================
# ORDER SUMMARY
# =========================================================
def build_order_summary_and_total(order_items, lang):
    total = sum(i.get("subtotal", 0) for i in order_items)
    summary = []

    for i in order_items:
        item_key = i["item"]
        info = MENU.get(item_key.lower(), {})

        name_en = (info.get("name_en") or item_key).strip()
        name_ar = (info.get("name_ar") or name_en).strip()
        base_name = name_ar if lang == "ar" else name_en
        category = info.get("category")

        if category == "burgers_meals":
            if lang == "ar":
                hot_word = "حار"
                mild_word = "بدون حار"
                if i.get("spicy"):
                    label = base_name if hot_word in base_name else f"{base_name} {hot_word}"
                elif i.get("nonspicy"):
                    label = base_name if (mild_word in base_name or "عادي" in base_name) else f"{base_name} {mild_word}"
                else:
                    label = base_name
            else:
                lower = base_name.lower()
                if i.get("spicy"):
                    label = base_name.title() if "spicy" in lower else f"Spicy {base_name.title()}"
                elif i.get("nonspicy"):
                    label = base_name.title() if ("non-spicy" in lower or "mild" in lower) else f"Non-spicy {base_name.title()}"
                else:
                    label = base_name.title()
        else:
            label = base_name if lang == "ar" else base_name.title()

        summary.append(f"{i['qty']} {label}")

    return summary, total


def build_single_item_line(item, lang):
    item_key = item["item"]
    info = MENU.get(item_key.lower(), {})

    name_en = (info.get("name_en") or item_key).strip()
    name_ar = (info.get("name_ar") or name_en).strip()
    base_name = name_ar if lang == "ar" else name_en
    category = info.get("category")

    if category == "burgers_meals":
        if lang == "ar":
            hot_word = "حار"
            mild_word = "بدون حار"
            if item.get("spicy"):
                label = base_name if hot_word in base_name else f"{base_name} {hot_word}"
            elif item.get("nonspicy"):
                label = base_name if (mild_word in base_name or "عادي" in base_name) else f"{base_name} {mild_word}"
            else:
                label = base_name
        else:
            lower = base_name.lower()
            if item.get("spicy"):
                label = base_name.title() if "spicy" in lower else f"Spicy {base_name.title()}"
            elif item.get("nonspicy"):
                label = base_name.title() if ("non-spicy" in lower or "mild" in lower) else f"Non-spicy {base_name.title()}"
            else:
                label = base_name.title()
    else:
        label = base_name if lang == "ar" else base_name.title()

    return f"{item['qty']} {label}"


def add_item_to_order_summary(state: dict, item_key: str, qty: int, price: float, spicy: int = 0, nonspicy: int = 0):
    """Append a menu item to the in-memory order and keep totals updated."""
    state.setdefault("order", [])

    try:
        qty_int = max(int(qty), 1)
    except Exception:
        qty_int = 1

    try:
        price_f = float(price)
    except Exception:
        price_f = 0.0

    line = {
        "item": (item_key or "").strip().lower(),
        "qty": qty_int,
        "spicy": 1 if spicy else 0,
        "nonspicy": 1 if nonspicy else 0,
        "price": price_f,
        "subtotal": qty_int * price_f,
    }
    state["order"].append(line)

    # Keep running total handy
    _, total = build_order_summary_and_total(state.get("order") or [], state.get("lang", "en"))
    state["total"] = total

# =========================================================
# ✅ (kept) MULTI-ITEM TEXT ORDER HELPERS (LLM extraction)
# =========================================================
# =========================================================
# ✅ FULL FIX — COPY/PASTE READY
# Fixes:
# 1) "cancel 1 burger and 1 fries" will NOT trigger multi-item add
# 2) Multi-item detection becomes stricter (requires items/words, not just numbers)
# 3) Avoid false-positive when user sends "2025 12 30" etc.
# =========================================================

def looks_like_multi_item_text(msg: str) -> bool:
    if not msg:
        return False

    # ✅ CRITICAL GUARD: cancel/remove/delete text should never be treated as "multi-item add"
    if is_cancel_text(msg):
        return False

    # ✅ Keep original for Arabic separator detection
    original = (msg or "").strip()
    
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
    has_arabic_separator = " و " in original or "و" in original
    
    # ✅ if it contains classic separators (English OR Arabic), it is likely multi-item
    if any(sep in t for sep in [" and ", " & ", " + ", " ثم ", " , "]) or has_arabic_separator:
        # BUT still require at least one qty
        if re.search(r"\b\d+\b", t):
            return True

    # ✅ NEW: Detect patterns like "2beef burger" (number directly attached to word)
    # This catches typos where user forgets space between quantity and item
    if re.search(r"\d+[a-z]", t):  # digit followed immediately by letter
        return True

    # ✅ fallback: two+ quantities AND at least one word
    nums = re.findall(r"\b\d+\b", t)
    if len(nums) >= 2:
        return True

    return False


def add_extracted_items_to_state(s: dict, extracted: list, lang: str):
    """
    extracted: [{"name": "<english_menu_name>", "qty": 2, "spicy": "spicy/non-spicy/any"}]
    returns: (added_lines, queued_spice_list)
    """
    added_lines = []
    queued = []

    s.setdefault("spice_queue", [])
    s.setdefault("order", [])

    for it in (extracted or []):
        raw_name = (it.get("name") or "").strip().lower()
        if not raw_name:
            continue

        # ✅ RESOLVE THROUGH MENU (map raw/alias -> exact MENU key)
        resolved, conf = resolve_menu_item(raw_name)
        if not resolved:
            continue

        name = resolved

        try:
            qty = int(it.get("qty") or 1)
        except Exception:
            qty = 1
        qty = max(qty, 1)

        spicy_pref = (it.get("spicy") or "any").strip().lower()

        price, category = get_price_and_category(name)
        if price <= 0:
            continue

        # burgers/meals need spice
        if category == "burgers_meals":
            if spicy_pref in ("spicy", "hot"):
                s["order"].append({
                    "item": name, "qty": qty, "spicy": 1, "nonspicy": 0,
                    "price": price, "subtotal": qty * price
                })
                added_lines.append(build_single_item_line({
                    "item": name, "qty": qty, "spicy": 1, "nonspicy": 0
                }, lang))

            elif spicy_pref in ("non-spicy", "nonspicy", "mild", "not spicy", "no spicy"):
                s["order"].append({
                    "item": name, "qty": qty, "spicy": 0, "nonspicy": 1,
                    "price": price, "subtotal": qty * price
                })
                added_lines.append(build_single_item_line({
                    "item": name, "qty": qty, "spicy": 0, "nonspicy": 1
                }, lang))

            else:
                # ✅ queue spice question
                s["spice_queue"].append({"item": name, "qty": qty})
                queued.append({"item": name, "qty": qty})
            continue

        # non-burger: direct add
        s["order"].append({
            "item": name, "qty": qty, "spicy": 0, "nonspicy": 0,
            "price": price, "subtotal": qty * price
        })
        added_lines.append(build_single_item_line({
            "item": name, "qty": qty, "spicy": 0, "nonspicy": 0
        }, lang))

    summary, total = build_order_summary_and_total(s["order"], lang)
    s["total"] = total
    return added_lines, queued


# =========================================================
# SPICE DETECTION + SPLIT
# =========================================================
def detect_spicy_nonspicy(msg: str):
    if not msg:
        return False, False
    text = msg.lower().replace("_", " ").replace("-", " ")
    nonspicy_keywords_en = [
        "non spicy", "non-spicy", "no spicy", "without spicy", "without spice",
        "not spicy", "mild",
    ]
    nonspicy_keywords_ar = ["بدون حار", "بدون حر", "عادي", "بدون"]
    nonspicy_flag = any(k in text for k in nonspicy_keywords_en + nonspicy_keywords_ar)

    spicy_keywords = ["spicy", "hot", "حار"]
    spicy_flag = any(k in text for k in spicy_keywords) and not nonspicy_flag
    return spicy_flag, nonspicy_flag


AR_NUM_WORDS = {
    "واحد": 1, "واحدة": 1,
    "اثنان": 2, "اثنين": 2, "اثنتان": 2, "اتنين": 2, "ثنين": 2,
    "ثلاثة": 3, "ثلاث": 3,
    "أربعة": 4, "اربعة": 4, "اربع": 4,
    "خمسة": 5,
    "ستة": 6,
    "سبعة": 7,
    "ثمانية": 8,
    "تسعة": 9,
    "عشرة": 10,
}

def _replace_arabic_number_words(text: str) -> str:
    if not text:
        return ""
    for w, n in AR_NUM_WORDS.items():
        text = re.sub(rf"(?<!\S){re.escape(w)}(?!\S)", str(n), text)
    return text


def parse_spice_split(msg: str, total_qty: int):
    text = (msg or "").lower().replace("-", " ").replace("_", " ").strip()
    text = _normalize_digits(text)
    text = _replace_arabic_number_words(text)

    spicy_words = ["spicy", "hot", "حار", "حارة", "حارين"]
    nonspicy_words = [
        "non spicy", "nonspicy", "non-spicy", "no spicy",
        "not spicy", "without spicy", "without spice", "mild",
        "بدون حار", "غير حار", "غير حارين", "عادي", "بدون"
    ]

    # ✅ Handle "half" keyword (50/50 split)
    half_keywords = ["half", "نص", "نصف"]
    has_half = any(h in text for h in half_keywords)
    
    nums = [int(x) for x in re.findall(r"\b\d+\b", text)]
    has_non = any(w in text for w in nonspicy_words)
    has_spicy = any(w in text for w in spicy_words)  # ✅ FIXED: Don't exclude if has_non
    
    print(f"🔍 parse_spice_split: msg='{msg}', total_qty={total_qty}")
    print(f"   nums={nums}, has_spicy={has_spicy}, has_non={has_non}")
    
    # ✅ If user says "half spicy and half non spicy", split evenly
    if has_half and has_spicy and has_non:
        half_qty = total_qty // 2
        remainder = total_qty % 2
        # Give remainder to spicy
        result = (half_qty + remainder, half_qty)
        print(f"   → Half split: {result}")
        return result

    # ✅ CRITICAL: Check for split request FIRST (both spicy AND non-spicy mentioned)
    if has_spicy and has_non and len(nums) >= 2:
        n1, n2 = nums[0], nums[1]
        spicy_pos = min([text.find(w) for w in spicy_words if text.find(w) != -1] or [9999])
        non_pos = min([text.find(w) for w in nonspicy_words if text.find(w) != -1] or [9999])

        print(f"   spicy_pos={spicy_pos}, non_pos={non_pos}")
        
        if spicy_pos < non_pos:
            spicy_q, non_q = n1, n2
        else:
            non_q, spicy_q = n1, n2

        spicy_q = min(spicy_q, total_qty)
        non_q = min(non_q, total_qty - spicy_q)
        result = (spicy_q, non_q)
        print(f"   → Split result: {result}")
        return result

    if has_spicy and nums:
        spicy_q = min(nums[0], total_qty)
        result = (spicy_q, total_qty - spicy_q)
        print(f"   → Spicy only: {result}")
        return result

    if has_non and nums:
        non_q = min(nums[0], total_qty)
        result = (total_qty - non_q, non_q)
        print(f"   → Non-spicy only: {result}")
        return result
    
    print(f"   → No split pattern matched, returning None")
    return None

    if has_spicy:
        return total_qty, 0
    if has_non:
        return 0, total_qty

    return None

# =========================================================
# MENU ITEM FINDING (EN + AR)
# =========================================================
def normalize_arabic_variants(s: str) -> str:
    if not s:
        return ""
    s = s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    s = s.replace("ة", "ه")
    s = s.replace("ى", "ي")
    s = s.replace("برغر", "برجر")
    return s


def fix_common_typos(s: str) -> str:
    """Fix common English typos for intelligent understanding"""
    if not s:
        return ""
    s_lower = s.lower()
    typo_map = {
        "burgur": "burger", "burgr": "burger", "burgir": "burger",
        "cofee": "coffee", "coffe": "coffee", "coffy": "coffee",
        "sandwitch": "sandwich", "sandwish": "sandwich",
        "pesi": "pepsi", "pepi": "pepsi",
        "wrasp": "wraps", "warp": "wrap",
        "chiken": "chicken", "checken": "chicken",
        "beff": "beef", "beaf": "beef",
        "french fry": "french fries",
        "onon ring": "onion rings",
    }
    for typo, correct in typo_map.items():
        if typo in s_lower:
            s = re.sub(r'\b' + re.escape(typo) + r'\b', correct, s, flags=re.IGNORECASE)
    return s


def check_if_irrelevant_question(msg: str, lang: str = "en") -> dict:
    """
    Detect if user's question is irrelevant to food ordering.
    Uses both pattern matching AND AI for robust detection.
    Returns: {"is_irrelevant": bool, "polite_response": str}
    """
    if not msg:
        return {"is_irrelevant": False, "polite_response": None}
    
    msg_lower = msg.lower().strip()
    
    # ✅ Quick check for obvious food ordering keywords - skip AI if clearly ordering
    food_keywords = [
        "burger", "sandwich", "coffee", "drink", "meal", "wrap", "fries",
        "pepsi", "water", "juice", "chicken", "beef", "order", "menu", "price",
        "برجر", "ساندويتش", "قهوة", "مشروب", "وجبة", "بطاطس", "دجاج", "طلب", "قائمة", "سعر"
    ]
    if any(keyword in msg_lower for keyword in food_keywords):
        return {"is_irrelevant": False, "polite_response": None}
    
    # ✅ PATTERN-BASED DETECTION (Fast, no API needed)
    # Detect common irrelevant topics
    irrelevant_patterns = [
        # Technical issues
        r"\b(laptop|computer|pc|phone|mobile|device|wifi|internet|network|bluetooth)\b.*\b(not work|problem|issue|fix|repair|broken|error)\b",
        r"\b(fix|repair|solve|resolve|help).*\b(laptop|computer|pc|phone|device)\b",
        # Questions about non-food topics
        r"\b(how to|guide|teach|explain).*\b(bomb|weapon|hack|illegal)\b",
        r"\b(weather|news|politics|sports|game|movie|music)\b",
        # Health/medical (not food-related)
        r"\b(doctor|medicine|hospital|sick|disease|treatment)\b",
        # Career/education
        r"\b(job|career|salary|university|study|exam)\b",
    ]
    
    for pattern in irrelevant_patterns:
        if re.search(pattern, msg_lower, re.IGNORECASE):
            print(f"🚫 Pattern-based irrelevant detection: matched '{pattern}'")
            polite_msg = (
                "شكراً لتواصلك معنا! 😊\n\n"
                "للأسف، أنا مساعد ذكي متخصص في طلبات الطعام من مطعم جوانا فقط.\n"
                "لا أستطيع المساعدة في هذا الموضوع، لكن يسعدني مساعدتك في طلب طعام لذيذ! 🍔☕\n\n"
                "دعني أريك قائمتنا 👇"
                if lang == "ar" else
                "Thank you for reaching out! 😊\n\n"
                "Unfortunately, I'm an AI assistant specialized in food orders from Joana Fast Food only.\n"
                "I can't help with that topic, but I'd love to help you order delicious food! 🍔☕\n\n"
                "Let me show you our menu 👇"
            )
            return {"is_irrelevant": True, "polite_response": polite_msg}
    
    # ✅ AI-POWERED DETECTION (Fallback for complex cases)
    if not client:
        return {"is_irrelevant": False, "polite_response": None}
    
    system_prompt = (
        "You are an intelligent classifier for Joana Fast Food chatbot.\\n\\n"
        "Your job is to determine if a user's message is IRRELEVANT to food ordering.\\n\\n"
        "IRRELEVANT means:\\n"
        "- Technical questions (laptop, phone, computer issues)\\n"
        "- Harmful/dangerous requests (bombs, weapons, illegal activities)\\n"
        "- General knowledge questions not about food\\n"
        "- Personal advice (relationships, health, career)\\n"
        "- Off-topic conversations\\n\\n"
        "RELEVANT means:\\n"
        "- Questions about menu items, prices, ingredients\\n"
        "- Ordering food, modifying orders\\n"
        "- Restaurant location, hours, delivery\\n"
        "- Greetings, thanks, feedback about food\\n\\n"
        "Respond with JSON ONLY:\\n"
        '{"is_irrelevant": true/false, "polite_response": "sweet friendly message in user language"}\\n\\n'
        "If irrelevant, polite_response should:\\n"
        "- Be VERY sweet, warm, and friendly\\n"
        "- Acknowledge their question kindly\\n"
        "- Politely explain you can only help with food orders\\n"
        "- Warmly invite them to explore the menu\\n"
        f"- Use {'Arabic' if lang == 'ar' else 'English'} language\\n"
        "- Use emojis to keep it friendly (😊, 🍔, ☕)\\n\\n"
        "If relevant, set is_irrelevant to false and polite_response to null."
    )
    
    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": msg}
            ],
            temperature=0.3,
            max_tokens=200,
            timeout=5,  # ✅ 5 second timeout to prevent hanging
        )
        
        response_text = (res.choices[0].message.content or "").strip()
        
        # Parse JSON response
        import json
        # Extract JSON from markdown code blocks if present
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()
        
        result = json.loads(response_text)
        print(f"🤖 AI Irrelevant Check: {result}")
        return result
        
    except Exception as e:
        print(f"❌ AI irrelevant check error: {repr(e)}")
        # Fail open - assume relevant if AI fails
        return {"is_irrelevant": False, "polite_response": None}


def find_menu_item(msg: str):
    text_raw = (msg or "").strip().lower()
    if not text_raw:
        return None

    generic_only = bool(
        re.fullmatch(r"\d*\s*(sandwich|sandwiches|burger|burgers)\s*", text_raw)
    )
    if generic_only:
        return None

    if re.search(r"\b(sandwich|sandwiches)\b", text_raw):
        specific_hint_words = ["egg", "chicken", "shaksouka", "kibdah", "tuna", "kebab", "kudu"]
        if not any(w in text_raw for w in specific_hint_words):
            return None

    if re.search(r"\b(burger|burgers)\b", text_raw):
        specific_hint_words = ["beef", "chicken", "zinger"]
        if not any(w in text_raw for w in specific_hint_words):
            return None

    if text_raw in MENU:
        return text_raw

    def has_arabic(s2: str) -> bool:
        return any("\u0600" <= ch <= "\u06ff" for ch in s2)

    is_arabic = has_arabic(text_raw)
    text = normalize_arabic_variants(text_raw) if is_arabic else text_raw
    candidates = []

    if is_arabic:
        for name in MENU.keys():
            name_l = str(name).strip().lower()
            if not name_l or not has_arabic(name_l):
                continue
            name_norm = normalize_arabic_variants(name_l)
            if name_norm and name_norm in text:
                candidates.append(name_l)
    else:
        for name in MENU.keys():
            name_l = str(name).strip().lower()
            if not name_l:
                continue
            pattern = r"\b" + re.escape(name_l) + r"s?\b"
            if re.search(pattern, text):
                candidates.append(name_l)

    if not candidates:
        return None

    candidates.sort(key=len, reverse=True)
    return candidates[0]
    
def is_non_menu_item_request(msg: str) -> bool:
    """
    Check if user is requesting items NOT on the Joana menu.
    Returns True if user mentions common non-menu items.
    """
    if not msg:
        return False
    
    msg_lower = msg.lower().strip()
    
    # ✅ List of items NOT on Joana menu (common requests to reject)
    non_menu_items = [
        "pizza", "بيتزا", "pizzas",
        "pasta", "باستا", "spaghetti",
        "tacos", "taco", "تاكو",
        "sushi", "سوشي",
        "ramen", "راميل",
        "noodles", "نودلز",
        "biryani", "برياني",
        "shawarma", "شاورما",  # if not in menu
        "kabsa", "كبسة",  # if not in menu
    ]
    
    # Check if any non-menu item is mentioned
    for item in non_menu_items:
        if re.search(r"\b" + re.escape(item) + r"s?\b", msg_lower):
            return True
    
    return False


def resolve_menu_item(raw: str):
    if not raw:
        return None, 0.0

    t = normalize_arabic_variants(raw.lower())
    t = re.sub(r"\s+", " ", t)

    # exact match
    if t in MENU:
        return t, 1.0

    # longest substring match
    best = None
    best_len = 0
    for k in MENU.keys():
        kk = normalize_arabic_variants(k)
        if kk in t and len(kk) > best_len:
            best = k
            best_len = len(kk)

    if best:
        return best, 0.9

    return None, 0.0


def get_items_by_category(category: str):
    items_map = {}
    for key, info in MENU.items():
        if info.get("category") != category:
            continue
        en = (info.get("name_en") or key).strip().lower()
        ar = (info.get("name_ar") or en).strip()
        items_map[en] = {"en": en, "ar": ar}
    return list(items_map.values())

# =========================================================
# NON-GENERIC ITEM HELPERS
# =========================================================
def has_non_generic_menu_item(msg: str) -> bool:
    if not msg or not MENU:
        return False

    text = _normalize_digits(msg.lower())
    seen_en = set()

    for _, info in MENU.items():
        cat = (info.get("category") or "").lower()
        if cat in ("burgers_meals", "sandwiches"):
            continue

        en = (info.get("name_en") or "").strip().lower()
        ar = (info.get("name_ar") or "").strip().lower()

        if not en or en in seen_en:
            continue
        seen_en.add(en)

        if re.search(r"\b" + re.escape(en) + r"s?\b", text):
            return True
        if ar and ar != "nan" and ar in text:
            return True

    return False


def add_non_generic_items_to_order(state: dict, msg: str, lang: str):
    text = _normalize_digits(msg.lower())
    to_add = {}
    added_lines = []

    seen_en = set()

    for _, info in MENU.items():
        cat = (info.get("category") or "").lower()
        if cat in ("burgers_meals", "sandwiches"):
            continue

        en = (info.get("name_en") or "").strip().lower()
        ar = (info.get("name_ar") or "").strip().lower()

        if not en or en in seen_en:
            continue
        seen_en.add(en)

        matched = False
        qty = None

        if re.search(r"\b" + re.escape(en) + r"s?\b", text):
            matched = True
            m = re.search(r"\b(\d+)\b\s+" + re.escape(en), text)
            qty = int(m.group(1)) if m else 1

        if not matched and ar and ar != "nan" and ar in text:
            matched = True
            m = re.search(r"\b(\d+)\b\s*" + re.escape(ar), text)
            qty = int(m.group(1)) if m else 1

        if matched:
            to_add[en] = to_add.get(en, 0) + max(1, qty or 1)

    for en, qty in to_add.items():
        # ✅ resolve correct MENU key (coffee / pepsi / variants)
        resolved = en
        if en.lower() not in MENU:
            # try to match by name_en
            for k, info in MENU.items():
                if (info.get("name_en") or "").lower() == en.lower():
                    resolved = k
                    break

        price, _ = get_price_and_category(resolved)
        if price is None or price <= 0:
            print("⚠ Skipped item (price missing):", en)
            continue

        state["order"].append({
            "item": resolved,
            "qty": qty,
            "spicy": 0,
            "nonspicy": 0,
            "price": float(price),
            "subtotal": qty * float(price)
        })

        # ✅ build user-facing added lines from resolved menu info
        info = MENU.get(resolved, {}) or {}
        name = info.get("name_ar") if lang == "ar" else (info.get("name_en") or resolved).title()
        added_lines.append(f"{qty} {name}")

    if added_lines:
        summary, total = build_order_summary_and_total(state["order"], lang)
        state["total"] = total
        return added_lines, True

    return [], False

# =========================================================
# GENERIC BURGER/SANDWICH HELPERS
# =========================================================
def msg_has_generic_burger_word(msg: str) -> bool:
    if not msg:
        return False
    t = msg.lower()
    return bool(re.search(r"\b(burger|burgers)\b", t) or "برجر" in t or "برغر" in t)

def msg_has_specific_burger(msg: str) -> bool:
    if not msg or not MENU:
        return False
    text = msg.lower()
    for k, info in MENU.items():
        if info.get("category") == "burgers_meals":
            name = (info.get("name_en") or k).strip().lower()
            if name and re.search(r"\b" + re.escape(name) + r"\b", text):
                return True
    return False

def msg_has_generic_sandwich_word(msg: str) -> bool:
    if not msg:
        return False
    t = msg.lower()
    return bool(re.search(r"\b(sandwich|sandwiches|wrap|wraps|tortilla|tortillas)\b", t) or "ساندويتش" in msg or "سندوتش" in msg)

def msg_has_specific_sandwich(msg: str) -> bool:
    if not msg or not MENU:
        return False
    text = msg.lower()
    for k, info in MENU.items():
        if info.get("category") == "sandwiches":
            name = (info.get("name_en") or k).strip().lower()
            if name and re.search(r"\b" + re.escape(name) + r"\b", text):
                return True
    return False

def _unique_menu_items_by_category(category: str):
    items = []
    seen = set()
    for k, info in MENU.items():
        if info.get("category") != category:
            continue
        en = (info.get("name_en") or k).strip().lower()
        if not en or en in seen:
            continue
        seen.add(en)
        ar = (info.get("name_ar") or en).strip()
        items.append({"en": en, "ar": ar})
    return items


def send_specific_burger_buttons(user_number: str, lang: str):
    ctx = WHATSAPP_SESSIONS.get(user_number, {})
    s = ctx.get("state") or {}
    page = int(s.get("burger_page") or 0)

    items = _unique_menu_items_by_category("burgers_meals")
    if not items:
        send_whatsapp_text(user_number, "No burgers found." if lang != "ar" else "لا توجد أصناف برجر حالياً.")
        return

    start = page * 2
    slice_items = items[start:start + 2]
    if not slice_items:
        s["burger_page"] = 0
        ctx["state"] = s
        WHATSAPP_SESSIONS[user_number] = ctx
        start = 0
        slice_items = items[0:2]

    buttons = []
    for it in slice_items:
        title = it["ar"] if lang == "ar" else it["en"].title()
        buttons.append({"id": f"pick_burger_{it['en']}", "title": title})

    if start + 2 < len(items):
        buttons.append({"id": "burger_more", "title": "المزيد" if lang == "ar" else "More"})

    qty = int(s.get("last_qty", 1) or 1)
    body = (f"لديك {qty} برجر. اختر نوع البرجر:" if lang == "ar"
            else f"You ordered {qty} burger(s). Please choose which burger:")

    send_whatsapp_quick_buttons(user_number, body, buttons)


def send_specific_sandwich_buttons(user_number: str, lang: str):
    ctx = WHATSAPP_SESSIONS.get(user_number, {})
    s = ctx.get("state") or {}
    page = int(s.get("sand_page") or 0)

    items = _unique_menu_items_by_category("sandwiches")
    if not items:
        send_whatsapp_text(user_number, "No sandwiches found." if lang != "ar" else "لا توجد أصناف ساندويتش حالياً.")
        return

    start = page * 2
    slice_items = items[start:start + 2]
    if not slice_items:
        s["sand_page"] = 0
        ctx["state"] = s
        WHATSAPP_SESSIONS[user_number] = ctx
        start = 0
        slice_items = items[0:2]

    buttons = []
    for it in slice_items:
        title = it["ar"] if lang == "ar" else it["en"].title()
        buttons.append({"id": f"pick_sandwich_{it['en']}", "title": title})

    if start + 2 < len(items):
        buttons.append({"id": "sand_more", "title": "المزيد" if lang == "ar" else "More"})

    qty = int(s.get("last_qty", 1) or 1)
    body = (f"لديك {qty} ساندويتش. اختر نوع الساندويتش:" if lang == "ar"
            else f"You ordered {qty} sandwich(es). Please choose which sandwich:")

    send_whatsapp_quick_buttons(user_number, body, buttons)

# =========================================================
# MULTI-INTENT ROUTER HELPERS
# =========================================================
BUTTON_ALIASES = {
    "payment_add_more": "add_more_items",
    "payment_proceed": "done",
    "pay_cash": "cash",
    "pay_online": "online payment",
    "finish_order": "done",
    "finish order": "done",
    "add_more_items": "add_more_items",
    "add more items": "add_more_items",
    "order_text": "order_text",
    "order_voice": "order_voice",
    "feedback_excellent": "excellent",
    "feedback_satisfied": "satisfied",
    "feedback_not_satisfied": "not satisfied",
}

def normalize_user_text(msg_raw: str):
    msg_norm = (msg_raw or "").strip()
    msg_norm = re.sub(r"\s+", " ", msg_norm).strip()
    msg_l = msg_norm.lower()

    typed_button_like = False
    if msg_l in BUTTON_ALIASES:
        msg_norm = BUTTON_ALIASES[msg_l]
        msg_l = msg_norm.lower()
        typed_button_like = True

    if msg_l.startswith("item_"):
        typed_button_like = True

    return msg_norm, msg_l, typed_button_like


def merge_replies(*parts):
    cleaned = [p for p in parts if p and str(p).strip()]
    return "<br><br>".join(cleaned).strip()

# =========================================================
# CANCEL HELPERS
# =========================================================
CANCEL_KEYWORDS_EN = ["cancel", "remove", "delete", "drop"]
CANCEL_KEYWORDS_AR = ["إلغاء", "الغاء", "احذف", "حذف", "شيل", "الغِ", "الغ", "كنسل"]

def is_cancel_text(msg: str) -> bool:
    t = (msg or "").lower()
    if any(k in t for k in CANCEL_KEYWORDS_EN):
        return True
    return any(k in (msg or "") for k in CANCEL_KEYWORDS_AR)

def split_cancel_parts(text: str):
    t = (text or "").strip()
    if not t:
        return []
    if not is_cancel_text(t):
        return [t]

    lower = t.lower()
    cancel_kw = "cancel"

    for k in CANCEL_KEYWORDS_EN:
        if re.search(r"\b" + re.escape(k) + r"\b", lower):
            cancel_kw = k
            break
    for k in CANCEL_KEYWORDS_AR:
        if k in t:
            cancel_kw = k
            break

    cleaned = re.sub(r"^\s*(cancel|remove|delete|drop)\b", "", t, flags=re.IGNORECASE).strip()
    for k in CANCEL_KEYWORDS_AR:
        if cleaned.startswith(k):
            cleaned = cleaned[len(k):].strip()
            break

    if not cleaned:
        return [t]

    split_seps = [" and ", " aur ", " then ", " و ", " ثم ", ",", ";", "&", " plus "]
    parts = [cleaned]

    for sep in split_seps:
        new_parts = []
        for p in parts:
            if sep.lower() in p.lower():
                if sep in [",", ";", "&"]:
                    new_parts.extend([x.strip() for x in p.split(sep) if x.strip()])
                else:
                    new_parts.extend([x.strip() for x in re.split(re.escape(sep), p, flags=re.IGNORECASE) if x.strip()])
            else:
                new_parts.append(p)
        parts = new_parts

    out = []
    for p in parts:
        p = p.strip()
        if p:
            out.append(f"{cancel_kw} {p}".strip())
    return out
    
    
    
# =========================
# PRICE / TOTAL INTENT HELPERS
# =========================

def is_price_query(msg: str) -> bool:
    t = (msg or "").lower()
    return any(k in t for k in [
        "price", "cost", "rate", "how much",
        "kitna", "kitni", "daam", "dam",
        "قیمت", "سعر", "بكم", "كم"
    ])


def is_total_bill_query(msg: str) -> bool:
    t = (msg or "").lower()
    return any(k in t for k in [
        "total", "total bill", "bill", "amount", "invoice",
        "المجموع", "الإجمالي", "فاتورة", "الحساب"
    ])


def extract_item_for_price_query(msg: str) -> str:
    t = _normalize_digits((msg or "").lower())
    t = re.sub(r"\b(price|cost|rate|how\s*much|total|bill|amount)\b", " ", t)
    t = re.sub(r"\b(kitna|kitni|daam|dam)\b", " ", t)
    t = re.sub(r"\b\d+\b", " ", t)
    t = re.sub(r"[^\w\u0600-\u06FF\s]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def compute_order_total(state: dict) -> float:
    return sum(
        int(i.get("qty", 1)) * float(i.get("price", 0))
        for i in (state.get("order") or [])
    )

    

def extract_cancel_requests_from_text(msg_raw: str):
    text = (msg_raw or "").lower()
    text = _normalize_digits(text)

    # remove cancel keywords
    text = re.sub(r"\b(cancel|remove|delete|drop)\b", " ", text)
    for k in CANCEL_KEYWORDS_AR:
        text = text.replace(k, " ")

    # normalize separators (and / aur / و / ,)
    text = text.replace(" & ", " ")
    text = text.replace(" و ", " ")
    text = re.sub(r"\b(and|aur|then)\b", " ", text)
    text = re.sub(r"[,+/;]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    pairs = re.findall(r"(\d+)\s+(.+?)(?=\s+\d+\s+|$)", text)

    out = []
    for qty_s, item_s in pairs:
        qty = int(qty_s)
        item_name = find_menu_item(item_s.strip())
        if qty > 0 and item_name:
            out.append({
                "qty": qty,
                "item": item_name,
                "spicy": False,
                "nonspicy": False
            })

    return out




def parse_cancel_request(msg: str, lang: str):
    if not msg:
        return None
    text = msg.strip()
    if not is_cancel_text(text):
        return None

    qty = None
    q = detect_qty(text)
    has_digit = bool(re.search(r"\d+", _normalize_digits(text)))
    has_word_en = bool(re.search(r"\b(one|two|three|four|five|six|seven|eight|nine|ten)\b", text.lower()))
    has_word_ar = any(w in text for w in [
        "واحد","واحدة","اثنين","اتنين","ثنين",
        "ثلاثة","ثلاث","اربعة","أربعة","خمسة",
        "ستة","سبعة","ثمانية","تسعة","عشرة"
    ])
    if has_digit or has_word_en or has_word_ar:
        qty = max(int(q), 1) if q else 1

    lines = re.split(r"[\n,]+", text.lower())
    spicy_qty = 0
    nonspicy_qty = 0

    for line in lines:
        qty_line = detect_qty(line) or 0
        if "spicy" in line and "non" not in line:
            spicy_qty += qty_line
        if "non" in line and "spicy" in line:
            nonspicy_qty += qty_line

    if spicy_qty == 0 and nonspicy_qty == 0:
        spicy_flag, nonspicy_flag = detect_spicy_nonspicy(text)
    else:
        spicy_flag = spicy_qty > 0
        nonspicy_flag = nonspicy_qty > 0

    cleaned = text
    for k in CANCEL_KEYWORDS_EN:
        cleaned = re.sub(r"\b" + re.escape(k) + r"\b", " ", cleaned, flags=re.IGNORECASE)
    for k in CANCEL_KEYWORDS_AR:
        cleaned = cleaned.replace(k, " ")

    cleaned = re.sub(r"\d+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    item = find_menu_item(cleaned) or find_menu_item(text)
    return {"qty": qty, "item": item, "spicy": spicy_flag, "nonspicy": nonspicy_flag}

# ============================
# ✅ UPDATED apply_cancel_on_order (FULL BLOCK)
# - Adds return_parts support
# ============================
def apply_cancel_on_order(state: dict, cancel_req: dict, lang: str, return_parts: bool = False):
    order = state.get("order") or []
    if not order:
        msg = "لا يوجد طلب لإلغائه." if lang == "ar" else "There is no active order to cancel."
        return False, msg

    item = cancel_req.get("item")
    qty = cancel_req.get("qty")  # None => remove all
    spicy_req = bool(cancel_req.get("spicy"))
    nonspicy_req = bool(cancel_req.get("nonspicy"))

    if not item:
        msg = (
            "من فضلك اكتب اسم الصنف الذي تريد إلغاءه (مثال: إلغاء 2 برجر دجاج)."
            if lang == "ar"
            else "Please type the item you want to cancel (e.g., cancel 2 chicken burger)."
        )
        return False, msg

    matches = []
    for idx, line in enumerate(order):
        if (line.get("item") or "").lower() != item.lower():
            continue
        matches.append((idx, line))

    if not matches:
        msg = "لم أجد هذا الصنف في طلبك." if lang == "ar" else "I couldn't find that item in your order."
        return False, msg

    if spicy_req or nonspicy_req:
        filtered = []
        for idx, line in matches:
            if spicy_req and line.get("spicy"):
                filtered.append((idx, line))
            if nonspicy_req and line.get("nonspicy"):
                filtered.append((idx, line))
        if filtered:
            matches = filtered

    # ============================
    # ✅ Remove ALL matching lines
    # ============================
    if qty is None:
        removed_lines = []
        for idx, line in sorted(matches, key=lambda x: x[0], reverse=True):
            removed_lines.append(build_single_item_line(line, lang))
            order.pop(idx)

        state["order"] = order
        summary, total = build_order_summary_and_total(order, lang)
        state["total"] = total

        msg = (
            "تم إلغاء الصنف من طلبك.<br>"
            + "<br>".join(removed_lines)
            + (
                "<br><br>ملخص الطلب:<br>"
                + "<br>".join(summary)
                + f"<br><br><b>الإجمالي: {total:.2f} {CURRENCY_AR}</b>"
                if order
                else "<br><br>تم إلغاء الطلب بالكامل."
            )
            if lang == "ar"
            else
            "Removed item(s) from your order:<br>"
            + "<br>".join(removed_lines)
            + (
                "<br><br>Updated order:<br>"
                + "<br>".join(summary)
                + f"<br><br><b>Total: {total:.2f} {CURRENCY}</b>"
                if order
                else "<br><br>Your order is now empty."
            )
        )

        # ✅ NEW: return parts optionally
        if return_parts:
            return True, {
                "removed_lines": removed_lines,
                "order_empty": not bool(order)
            }

        return True, msg

    # ============================
    # ✅ Remove qty from matching
    # ============================
    remaining_to_cancel = int(qty)
    removed_lines = []

    for idx, line in sorted(matches, key=lambda x: x[0]):
        if remaining_to_cancel <= 0:
            break
        line_qty = int(line.get("qty", 0) or 0)
        if line_qty <= 0:
            continue

        if remaining_to_cancel >= line_qty:
            removed_lines.append(build_single_item_line(line, lang))
            remaining_to_cancel -= line_qty
            line["_to_remove"] = True
        else:
            removed_qty_here = remaining_to_cancel
            new_qty = line_qty - removed_qty_here
            line["qty"] = new_qty
            line["subtotal"] = float(line.get("price", 0)) * new_qty
            removed_lines.append(
                (f"{removed_qty_here} " + (MENU.get(item.lower(), {}).get("name_ar", item) if lang == "ar" else item.title()))
            )
            remaining_to_cancel = 0

    new_order = []
    for line in order:
        if line.get("_to_remove"):
            continue
        line.pop("_to_remove", None)
        new_order.append(line)

    state["order"] = new_order
    summary, total = build_order_summary_and_total(new_order, lang)
    state["total"] = total

    # ============================
    # ✅ If order became empty
    # ============================
    if not new_order:
        msg = (
            "تم إلغاء الأصناف المطلوبة وأصبح الطلب فارغاً. تم إلغاء الطلب."
            if lang == "ar"
            else "Cancelled the requested quantities. Your order is now empty and has been cancelled."
        )

        # ✅ NEW: return parts optionally
        if return_parts:
            return True, {
                "removed_lines": removed_lines,
                "order_empty": True
            }

        return True, msg

    # ============================
    # ✅ Still has items
    # ============================
    msg = (
        "تم إلغاء الكمية المطلوبة:<br>"
        + "<br>".join(removed_lines)
        + "<br><br>ملخص الطلب:<br>"
        + "<br>".join(summary)
        + f"<br><br><b>الإجمالي: {total:.2f} {CURRENCY_AR}</b><br>"
        + "هل ترغب في المتابعة إلى الدفع؟"
        if lang == "ar"
        else
        "Cancelled the requested quantities:<br>"
        + "<br>".join(removed_lines)
        + "<br><br>Updated order:<br>"
        + "<br>".join(summary)
        + f"<br><br><b>Total: {total:.2f} {CURRENCY}</b><br>"
        + "Would you like to proceed with payment?"
    )

    # ✅ NEW: return parts optionally
    if return_parts:
        return True, {
            "removed_lines": removed_lines,
            "order_empty": not bool(new_order)
        }

    return True, msg


# =========================================================
# CATEGORY UI SENDING
# =========================================================
def send_category_buttons(user_number: str, lang: str = "en", show_image: bool = True):
    caption = "Here is our menu" if lang == "en" else "هذه قائمتنا"
    if show_image:
        image_url = "https://qintellecttechnologies.com/joana_chatbot/static/menu.PNG"
        send_whatsapp_image(user_number, image_url, caption=caption)

    if lang == "ar":
        body = "من فضلك اختر الفئة:"
        buttons = [
            {"id": "cat_burgers_meals", "title": "برجر ووجبات"},
            {"id": "cat_sandwiches", "title": "ساندويتش"},
            {"id": "cat_snacks_sides", "title": "وجبات خفيفة"},
        ]
    else:
        body = "Please choose a category:"
        buttons = [
            {"id": "cat_burgers_meals", "title": "Burgers & Meals"},
            {"id": "cat_sandwiches", "title": "Sandwiches & Wraps"},
            {"id": "cat_snacks_sides", "title": "Snacks & Sides"},
        ]
    send_whatsapp_quick_buttons(user_number, body, buttons)


def send_items_for_category(user_number: str, category: str, lang: str = "en"):
    items = get_items_by_category(category)
    if not items:
        send_whatsapp_text(user_number, "No items found in this category yet." if lang != "ar" else "لا توجد أصناف في هذه الفئة حالياً.")
        return

    state = WA_CATEGORY_STATE.get(user_number, {"category": category, "index": 0})
    index = state.get("index", 0)
    if state.get("category") != category:
        index = 0

    slice_items = items[index : index + 2]
    buttons = []
    for item in slice_items:
        en_name = item["en"]
        ar_name = item["ar"]
        title = ar_name if lang == "ar" else en_name.title()
        buttons.append({"id": f"item_{en_name}", "title": title})

    if index + 2 < len(items):
        more_title = "المزيد من الأصناف" if lang == "ar" else "More items"
        buttons.append({"id": "more_items", "title": more_title})

    body = (
        "اختر الصنف ثم اكتب الكمية المطلوبة (مثال: 12)."
        if lang == "ar"
        else "Choose an item, then type the quantity you want (e.g., 12)."
    )
    send_whatsapp_quick_buttons(user_number, body, buttons)
    WA_CATEGORY_STATE[user_number] = {"category": category, "index": index}


def send_payment_buttons(user_number: str, body: str, lang: str, has_order: bool):
    if not has_order:
        send_whatsapp_text(user_number, body)
        return

    if lang == "ar":
        buttons = [
            {"id": "payment_proceed", "title": "المتابعة إلى الدفع"},
            {"id": "payment_add_more", "title": "إضافة أصناف أخرى"},
            {"id": "payment_cancel", "title": "إلغاء الطلب"},
        ]
    else:
        buttons = [
            {"id": "payment_proceed", "title": "Proceed to payment"},
            {"id": "payment_add_more", "title": "Add more items"},
            {"id": "payment_cancel", "title": "Cancel order"},
        ]
    send_whatsapp_quick_buttons(user_number, body, buttons)

def build_item_name_only(item: dict, lang: str) -> str:
    item_key = (item.get("item") or "").lower()
    info = MENU.get(item_key, {}) if MENU else {}

    name_en = (info.get("name_en") or item_key).strip()
    name_ar = (info.get("name_ar") or name_en).strip()

    base_name = name_ar if lang == "ar" else name_en
    category = info.get("category")

    if category == "burgers_meals":
        if lang == "ar":
            if item.get("spicy"):
                return f"{base_name} حار"
            if item.get("nonspicy"):
                return f"{base_name} بدون حار"
            return base_name
        else:
            if item.get("spicy"):
                return f"Spicy {base_name.title()}"
            if item.get("nonspicy"):
                return f"Non-spicy {base_name.title()}"
            return base_name.title()

    return base_name if lang == "ar" else base_name.title()


def send_cancel_item_buttons(user_number: str, lang: str):
    ctx = WHATSAPP_SESSIONS.get(user_number, {})
    s = ctx.get("state") or {}
    order = s.get("order") or []

    if not order:
        send_whatsapp_text(user_number, "لا يوجد أي صنف في الطلب لإلغائه." if lang == "ar" else "There is no item in your order to cancel.")
        return

    page = int(s.get("cancel_page") or 0)
    start = page * 2
    slice_items = order[start:start + 2]

    if not slice_items:
        s["cancel_page"] = 0
        ctx["state"] = s
        WHATSAPP_SESSIONS[user_number] = ctx
        start = 0
        slice_items = order[0:2]

    # Build buttons for items to cancel
    header = "اختر الصنف الذي تريد إلغاءه:" if lang == "ar" else "Which item would you like to cancel?"

    buttons = []
    for item in slice_items:
        title = build_item_name_only(item, lang)
        if len(title) > 20:
            title = title[:17].rstrip() + "..."
        real_index = order.index(item)
        buttons.append({"id": f"cancel_item_{real_index}", "title": title})

    if start + 2 < len(order):
        buttons.append({"id": "cancel_more", "title": "المزيد" if lang == "ar" else "More"})

    send_whatsapp_quick_buttons(user_number, header, buttons)

# =========================================================
# LLM HELPERS
# =========================================================
def build_menu_context():
    if not MENU:
        return "Current restaurant menu is empty."
    lines = []
    for name, info in MENU.items():
        if not re.search(r"[A-Za-z]", name):
            continue
        price = info.get("price", 0.0)
        category = info.get("category", "") or ""
        lines.append(f"- {name} | price: {price:.2f} {CURRENCY} | category: {category}")
    if not lines:
        return "Current restaurant menu is empty."
    return "Current restaurant menu (items, prices, categories):\n" + "\n".join(lines)


def get_llm_reply(msg, lang="en"):
    lang_name = "English" if lang == "en" else "Arabic"
    sys_prompt = (
        "You are Joana, an intelligent AI assistant for JOANA Fast Food.\n\n"
        "PERSONALITY:\n"
        "- Friendly, helpful, and professional\n"
        "- Natural conversational style (not robotic)\n"
        "- Proactive - suggest popular items, combos, deals\n"
        "- Patient - handle typos, unclear requests gracefully\n\n"
        "INTELLIGENCE RULES:\n"
        "1. CONTEXT AWARENESS: Remember what user ordered, suggest related items\n"
        "2. SMART INTERPRETATION: 'a burger' = 1, 'few burgers' = 2-3, 'some' = 3-4\n"
        "3. TYPO TOLERANCE: cofee→coffee, burgur→burger, pesi→pepsi\n"
        "4. MULTI-LANGUAGE: Handle Arabic, English, or mixed seamlessly\n"
        "5. PROACTIVE HELP: If user seems confused, offer menu/categories\n"
        "6. SMART SUGGESTIONS: 'Want fries with that?', 'Add a drink?'\n\n"
        "RESPONSE GUIDELINES:\n"
        "- For IRRELEVANT questions: 'Sorry, I can only help with food orders. Let me show you our menu!'\n"
        "- For OFF-MENU requests: Politely say 'Sorry, I can only help with our menu items. Please choose from the menu.' and guide them back to the categories.\n"
        "- For UNCLEAR requests: Ask clarifying question, then suggest options\n"
        "- For PARTIAL orders: Complete the thought ('3 burgers... and what else?')\n"
        "- Always guide next step naturally\n\n"
        "JOANA INFO:\n"
        "- Open 24/7, takeaway only\n"
        "- Fast service, quality food\n"
        "- Multiple branches in Riyadh\n\n"
        f"Always respond in {lang_name} with natural, conversational tone.\n"
    )
    context = build_menu_context()
    messages = [{"role": "system", "content": sys_prompt}, {"role": "system", "content": context}]
    for m in session.get("messages", []):
        messages.append(m)
    messages.append({"role": "user", "content": msg})

    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.5,
            max_tokens=250,
        )
        return (res.choices[0].message.content or "").strip()
    except Exception as e:
        print("LLM error:", repr(e))
        return "Sorry, something went wrong." if lang == "en" else "عذراً، حدث خطأ ما."


def build_llm_menu_list() -> str:
    if not MENU:
        return ""
    names = set()
    for _key, info in MENU.items():
        nm = (info.get("name_en") or "").strip()
        if nm:
            names.add(nm)
    return ", ".join(sorted(names))


def parse_intelligent_order(msg: str, lang: str = "en") -> dict:
    """
    Smart LLM-based order parser that handles:
    - Wrong spellings (cofee → coffee, burgur → burger)
    - Generic vs specific items ("burger" vs "beef burger")
    - Multiple items in one sentence
    - Extracts quantities and preferences
    
    Returns: {
        "items": [
            {"type": "specific", "name": "Coffee", "qty": 3, "category": "drinks"},
            {"type": "generic", "category": "burger", "qty": 2},
            {"type": "specific", "name": "Beef Burger", "qty": 1, "spicy": "spicy"}
        ]
    }
    """
    if not msg or not MENU or not client:
        return {"items": []}
    
    try:
        # Build comprehensive menu context with categories (INCLUDING Arabic names!)
        menu_by_category = {}
        for key, info in MENU.items():
            cat = (info.get("category") or "").strip().lower()
            name_en = (info.get("name_en") or key).strip()
            name_ar = (info.get("name_ar") or "").strip()
            
            # ✅ Include BOTH English and Arabic names for better matching
            display_name = f"{name_en} ({name_ar})" if name_ar else name_en
            
            if cat not in menu_by_category:
                menu_by_category[cat] = []
            menu_by_category[cat].append(display_name)
        
        menu_context = "\n".join([
            f"- {cat}: {', '.join(items[:15])}"
            for cat, items in menu_by_category.items() if items
        ])
        
        system_prompt = (
            "You are an intelligent restaurant order parser for JOANA Fast Food.\n\n"
            "MENU BY CATEGORY:\n"
            f"{menu_context}\n\n"
            "TASK: Parse customer's natural language order (may have typos, ARABIC or ENGLISH or mixed).\n\n"
            "⚠️ CRITICAL RULES (FOLLOW EXACTLY - DO NOT SKIP ANY ITEMS!):\n"
            "\n"
            "RULE 1 - WRAPS = SANDWICHES (MANDATORY!):\n"
            "When user says: wrap, wraps, tortilla, tortillas → MUST use category=\"sandwich\"\n"
            "⚠️ NEVER ignore wraps! NEVER skip wraps! ALWAYS extract them as sandwich category!\n"
            "\n"
            "RULE 2 - SIDES/SNACKS:\n"
            "'sides', 'snacks', 'side' → category=\"snacks_sides\"\n"
            "\n"
            "RULE 3 - ARABIC SUPPORT & TYPO TOLERANCE:\n"
            "⚠️ Be EXTREMELY tolerant of Arabic spelling variations!\n"
            "Convert Arabic numerals (١٢٣٤٥) to English (12345)\n"
            "MATCH similar Arabic words even with slight differences:\n"
            "  - 'تورتيلا' should match 'تورتيا' (tortilla variations)\n"
            "  - 'بوفك' should match 'فشار' (popcorn variations)\n"
            "  - 'برغر' should match 'برجر' (burger variations)\n"
            "Generic categories (English OR Arabic):\n"
            "  - burger/burgers/برجر/برغر → category=\"burger\"\n"
            "  - sandwich/ساندويتش/wrap/wraps/تورتيلا/تورتيا → category=\"sandwich\"\n"
            "  - drink/مشروب/juice/عصير/meal/وجبة → respective categories\n"
            "⚠️ When user mentions Arabic item name, find closest match in menu context above!\n"
            "Example: 'ساندويتش شكشوكة' → match 'Sandwiches Shashukah'\n"
            "\n"
            "RULE 4 - SPECIFIC ITEMS:\n"
            "If user mentions specific item name → type=\"specific\"\n"
            "Examples: 'chicken'/'دجاج' → \"Chicken Burger\", 'sweet corn'/'ذرة حلوة' → \"Sweet Corn\"\n"
            "Coffee/Tea/Water/Pepsi are SPECIFIC items under drinks category\n"
            "\n"
            "RULE 5 - QUANTITY INTELLIGENCE:\n"
            "⚠️ ALWAYS extract quantity when explicitly mentioned!\n"
            "'2 burgers' → qty=2, '5 coffee' → qty=5, '10 drinks' → qty=10\n"
            "If NO quantity mentioned, use qty=1 as default\n"
            "Be precise with numbers: '10 burgers and 5 wraps' → burger qty=10, sandwich qty=5\n"
            "\n"
            "RULE 6 - MENU HIERARCHY AWARENESS:\n"
            "⚠️ Coffee is a SPECIFIC drink, not a separate category!\n"
            "When user says '3 coffees and 2 drinks':\n"
            "  → Extract Coffee as specific item (qty=3, category=drinks)\n"
            "  → Extract drinks as generic (qty=2) for OTHER drinks (NOT coffee again!)\n"
            "This prevents duplicate counting of the same item.\n"
            "\n"
            "RULE 7 - EXTRACT ALL ITEMS:\n"
            "Multi-item orders: Extract EVERY item mentioned (DO NOT DROP ANY!)\n"
            "\n"
            "RULE 8 - PRESERVE QUANTITIES:\n"
            "Keep exact quantities from user input\n"
            "\n"
            "RULE 9 - SPICE PREFERENCES:\n"
            "Detect: spicy/non-spicy/حار/بدون حار for burgers\n"
            "\n"
            "═══════════════════════════════════════════════════════════\n"
            "FEW-SHOT EXAMPLES (FOLLOW THESE PATTERNS EXACTLY!):\n"
            "═══════════════════════════════════════════════════════════\n"
            "\n"
            "EXAMPLE 1:\n"
            "Input: \"3 burgers and 2 wraps and 4 coffee\"\n"
            "Output:\n"
            "{\n"
            "  \"items\": [\n"
            "    {\"type\": \"generic\", \"category\": \"burger\", \"qty\": 3},\n"
            "    {\"type\": \"generic\", \"category\": \"sandwich\", \"qty\": 2},\n"
            "    {\"type\": \"specific\", \"name\": \"Coffee\", \"qty\": 4, \"category\": \"drinks\"}\n"
            "  ]\n"
            "}\n"
            "✅ Correct: THREE items extracted (wraps → sandwich!)\n"
            "\n"
            "EXAMPLE 2:\n"
            "Input: \"10 burgers and 5 wraps and 3 coffee\"\n"
            "Output:\n"
            "{\n"
            "  \"items\": [\n"
            "    {\"type\": \"generic\", \"category\": \"burger\", \"qty\": 10},\n"
            "    {\"type\": \"generic\", \"category\": \"sandwich\", \"qty\": 5},\n"
            "    {\"type\": \"specific\", \"name\": \"Coffee\", \"qty\": 3, \"category\": \"drinks\"}\n"
            "  ]\n"
            "}\n"
            "✅ Correct: THREE items, wraps → sandwich with qty=5\n"
            "\n"
            "EXAMPLE 3 (Coffee + Drinks hierarchy):\n"
            "Input: \"2 burgers, 3 coffees, and 2 drinks\"\n"
            "Output:\n"
            "{\n"
            "  \"items\": [\n"
            "    {\"type\": \"generic\", \"category\": \"burger\", \"qty\": 2},\n"
            "    {\"type\": \"specific\", \"name\": \"Coffee\", \"qty\": 3, \"category\": \"drinks\"},\n"
            "    {\"type\": \"generic\", \"category\": \"drinks\", \"qty\": 2}\n"
            "  ]\n"
            "}\n"
            "✅ Correct: Coffee is specific, drinks is generic (for selecting OTHER drinks)\n"
            "\n"
            "EXAMPLE 4 (Natural language quantities):\n"
            "Input: \"a burger, few coffees, and some water\"\n"
            "Output:\n"
            "{\n"
            "  \"items\": [\n"
            "    {\"type\": \"generic\", \"category\": \"burger\", \"qty\": 1},\n"
            "    {\"type\": \"specific\", \"name\": \"Coffee\", \"qty\": 3, \"category\": \"drinks\"},\n"
            "    {\"type\": \"specific\", \"name\": \"Water\", \"qty\": 3, \"category\": \"drinks\"}\n"
            "  ]\n"
            "}\n"
            "✅ Correct: 'a'=1, 'few'=3, 'some'=3 (smart quantity detection)\n"
            "\n"
            "EXAMPLE 5 (Arabic with typo tolerance):\n"
            "Input: \"١ تورتيلا دجاج جامبو\"\n"
            "Output:\n"
            "{\n"
            "  \"items\": [\n"
            "    {\"type\": \"specific\", \"name\": \"Tortilla Chicken Jambo\", \"qty\": 1, \"category\": \"burgers_meals\"}\n"
            "  ]\n"
            "}\n"
            "✅ Correct: Matched 'تورتيلا' (typo) to 'تورتيا' in menu, converted ١ to 1\n"
            "\n"
            "EXAMPLE 6 (Arabic multi-item):\n"
            "Input: \"٤ ساندويتش شكشوكة و ٥ قهوة\"\n"
            "Output:\n"
            "{\n"
            "  \"items\": [\n"
            "    {\"type\": \"specific\", \"name\": \"Sandwiches Shashukah\", \"qty\": 4, \"category\": \"sandwiches\"},\n"
            "    {\"type\": \"specific\", \"name\": \"Coffee\", \"qty\": 5, \"category\": \"drinks\"}\n"
            "  ]\n"
            "}\n"
            "✅ Correct: Arabic numbers converted, TWO items extracted\n"
            "\n"
            "EXAMPLE 7 (Typos and informal):\n"
            "Input: \"2 burgurs and cofee plz\"\n"
            "Output:\n"
            "{\n"
            "  \"items\": [\n"
            "    {\"type\": \"generic\", \"category\": \"burger\", \"qty\": 2},\n"
            "    {\"type\": \"specific\", \"name\": \"Coffee\", \"qty\": 1, \"category\": \"drinks\"}\n"
            "  ]\n"
            "}\n"
            "✅ Correct: Fixed typos (burgurs→burger, cofee→coffee), ignored 'plz'\n"
            "\n"
            "EXAMPLE 8:\n"
            "Input: \"2 burgers, 3 coffees, and 2 drinks\"\n"
            "Output:\n"
            "{\n"
            "  \"items\": [\n"
            "    {\"type\": \"generic\", \"category\": \"burger\", \"qty\": 2},\n"
            "    {\"type\": \"specific\", \"name\": \"Coffee\", \"qty\": 3, \"category\": \"drinks\"},\n"
            "    {\"type\": \"generic\", \"category\": \"drinks\", \"qty\": 2}\n"
            "  ]\n"
            "}\n"
            "✅ Correct: Coffee is specific, drinks is generic (for selecting OTHER drinks)\n"
            "\n"
            "EXAMPLE 9:\n"
            "Input: \"5 burgers and 5 sides\"\n"
            "Output:\n"
            "{\n"
            "  \"items\": [\n"
            "    {\"type\": \"generic\", \"category\": \"burger\", \"qty\": 5},\n"
            "    {\"type\": \"generic\", \"category\": \"snacks_sides\", \"qty\": 5}\n"
            "  ]\n"
            "}\n"
            "✅ Correct: TWO items extracted\n"
            "\n"
            "EXAMPLE 10:\n"
            "Input: \"2 wraps\"\n"
            "Output:\n"
            "{\n"
            "  \"items\": [\n"
            "    {\"type\": \"generic\", \"category\": \"sandwich\", \"qty\": 2}\n"
            "  ]\n"
            "}\n"
            "✅ Correct: wraps → sandwich category\n"
            "\n"
            "EXAMPLE 11 (Arabic):\n"
            "Input: \"٤ برجر و ٥ ساندويتش و ٣ ذرة\"\n"
            "Output:\n"
            "{\n"
            "  \"items\": [\n"
            "    {\"type\": \"generic\", \"category\": \"burger\", \"qty\": 4},\n"
            "    {\"type\": \"generic\", \"category\": \"sandwich\", \"qty\": 5},\n"
            "    {\"type\": \"specific\", \"name\": \"Sweet Corn\", \"qty\": 3, \"category\": \"snacks_sides\"}\n"
            "  ]\n"
            "}\n"
            "✅ Correct: Arabic numbers converted, THREE items\n"
            "\n"
            "═══════════════════════════════════════════════════════════\n\n"
            "OUTPUT FORMAT (JSON ONLY - NO EXPLANATIONS!):\n"
            "{\n"
            "  \"items\": [\n"
            "    {\"type\": \"generic\", \"category\": \"sandwich\", \"qty\": 5},\n"
            "    {\"type\": \"specific\", \"name\": \"Coffee\", \"qty\": 3, \"category\": \"drinks\"},\n"
            "    {\"type\": \"specific\", \"name\": \"Beef Burger\", \"qty\": 1, \"spicy\": \"spicy\", \"category\": \"burgers_meals\"}\n"
            "  ]\n"
            "}\n\n"
            "VALID category VALUES:\n"
            "- burgers_meals, sandwiches, drinks, meals, juices, snacks_sides\n"
            "\n"
            "VALIDATION CHECKLIST (verify before returning):\n"
            "✓ Count items in input (by 'and' or 'و') → output must have same count\n"
            "✓ If input contains 'wrap' or 'wraps' → output MUST include sandwich category\n"
            "✓ All quantities preserved exactly\n"
            "✓ Arabic numbers converted to English\n"
            "✓ Valid JSON syntax\n"
            "\n"
            "Return ONLY the JSON object. No explanations, no comments."
        )
        
        res = client.chat.completions.create(
            model="gpt-4o",  # ✅ UPGRADED from gpt-4o-mini for better accuracy
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": msg}
            ],
            temperature=0.1,  # ✅ Lower temp for more consistent extraction
            max_tokens=500,   # ✅ Increased for complex orders
        )
        
        raw = (res.choices[0].message.content or "").strip()
        print("LLM order parse raw:", raw[:200])
        
        first = raw.find("{")
        last = raw.rfind("}")
        if first == -1 or last == -1:
            return {"items": []}
        
        data = json.loads(raw[first:last+1])
        items = data.get("items") or []
        
        # ✅ DEBUG: Log extracted items before cleaning
        print("LLM extracted items (before normalization):", items)
        
        # Validate and normalize
        cleaned = []
        for it in items:
            item_type = (it.get("type") or "").strip().lower()
            qty = max(int(it.get("qty") or 1), 1)
            
            if item_type == "generic":
                category = (it.get("category") or "").strip().lower()
                
                # Normalize category names
                if category in ["burger", "burgers", "برجر"]:
                    category = "burger"
                elif category in ["sandwich", "sandwiches", "wrap", "wraps", "tortilla", "tortillas", "ساندويتش"]:
                    category = "sandwich"  # ✅ CRITICAL: wraps → sandwich
                elif category in ["meal", "meals", "وجبة"]:
                    category = "meals"
                elif category in ["juice", "juices", "عصير"]:
                    category = "juices"
                elif category in ["drink", "drinks", "beverage", "مشروب"]:
                    category = "drinks"
                elif category in ["snack", "snacks", "side", "sides", "snacks_sides"]:
                    category = "snacks_sides"
                
                cleaned.append({
                    "type": "generic",
                    "category": category,
                    "qty": qty
                })
            
            elif item_type == "specific":
                name = str(it.get("name") or "").strip()
                if not name:
                    continue
                
                category = (it.get("category") or "").strip().lower()
                spicy = (it.get("spicy") or "any").strip().lower()
                
                cleaned.append({
                    "type": "specific",
                    "name": name,
                    "qty": qty,
                    "category": category,
                    "spicy": spicy
                })
        
        # ✅ DEBUG: Log cleaned items
        print("LLM cleaned items:", cleaned)
        return {"items": cleaned}
    
    except Exception as e:
        print("parse_intelligent_order error:", repr(e))
        return {"items": []}


def extract_items_with_llm(msg: str, lang: str = "en") -> list:
    """Legacy wrapper - converts new format to old format for compatibility"""
    result = parse_intelligent_order(msg, lang)
    items = result.get("items") or []
    
    # Convert to old format (specific items only)
    legacy = []
    for it in items:
        if it.get("type") == "specific":
            legacy.append({
                "name": it.get("name"),
                "qty": it.get("qty", 1),
                "spicy": it.get("spicy", "any")
            })
    return legacy

# =========================================================
# VOICE TRANSCRIPTION (Cloud + Deepgram)
# =========================================================
whisper_model = None  # optional offline fallback

def transcribe_audio_from_cloud(media_id: str) -> str:
    if not media_id:
        return ""
    if not WHATSAPP_TOKEN:
        return ""

    meta_url = f"{WHATSAPP_API_BASE}/{media_id}"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}
    temp_path = None

    try:
        meta_resp = requests.get(meta_url, headers=headers, timeout=30)
        meta_resp.raise_for_status()
        meta = meta_resp.json()
        file_url = meta.get("url")
        if not file_url:
            return ""

        file_resp = requests.get(file_url, headers=headers, timeout=60)
        file_resp.raise_for_status()
        audio_bytes = file_resp.content

        if DEEPGRAM_API_KEY:
            try:
                dg_headers = {"Authorization": f"Token {DEEPGRAM_API_KEY}", "Content-Type": "audio/ogg"}
                dg_params = {"model": "whisper", "language": "ar", "smart_format": "true"}
                dg_url = "https://api.deepgram.com/v1/listen"
                dg_resp = requests.post(dg_url, headers=dg_headers, params=dg_params, data=audio_bytes, timeout=60)
                dg_resp.raise_for_status()
                dg_data = dg_resp.json()

                channels = dg_data.get("results", {}).get("channels", [])
                if channels:
                    alts = channels[0].get("alternatives", [])
                    for alt in alts:
                        t = (alt.get("transcript") or "").strip()
                        if t:
                            return t
            except Exception as e:
                print("Deepgram error:", repr(e))

        if whisper_model:
            try:
                with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
                    f.write(audio_bytes)
                    temp_path = f.name
                result = whisper_model.transcribe(temp_path)
                return (result.get("text") or "").strip()
            except Exception as e:
                print("Whisper fallback error:", repr(e))

        return ""
    except Exception as e:
        print("Voice transcription error:", repr(e))
        return ""
    finally:
        if temp_path:
            try:
                os.remove(temp_path)
            except Exception:
                pass

# =========================================================
# DB: CREATE ORDER + ITEMS
# =========================================================
def create_order_in_db(customer_id: int, state: dict, lang: str, branch_name: str | None = None) -> int | None:
    if customer_id is None or not SUPABASE_REST_URL:
        return None
    order_items_state = state.get("order") or []
    total = state.get("total", 0)
    if not order_items_state:
        return None

    subtotal = sum(i["subtotal"] for i in order_items_state)
    total_amount = float(total or subtotal)

    try:
        url_max = f"{SUPABASE_REST_URL}/orders"
        params = {
            "select": "order_number_for_customer",
            "customer_id": f"eq.{customer_id}",
            "order": "order_number_for_customer.desc",
            "limit": 1,
        }
        resp_max = requests.get(url_max, headers=supabase_headers(), params=params, timeout=20)
        resp_max.raise_for_status()
        rows = resp_max.json()
        next_order_num = (rows[0].get("order_number_for_customer") or 0) + 1 if rows else 1
    except Exception as e:
        print("Supabase fetch max order_number error:", repr(e))
        next_order_num = 1

    summary_lines, _ = build_order_summary_and_total(order_items_state, lang)
    raw_summary = "\n".join(summary_lines)

    ts = get_dual_timestamp()

    # IMPORTANT: feedback_due_at_utc is set AFTER payment selection
    feedback_due_at_utc = None
    feedback_sent = True

    url_orders = f"{SUPABASE_REST_URL}/orders"
    order_payload = [{
        "customer_id": customer_id,
        "order_number_for_customer": next_order_num,
        "status": "confirmed",
        "order_type": "takeaway",
        "branch_name": branch_name,
        "subtotal_amount": float(subtotal),
        "discount_amount": 0,
        "tax_amount": 0,
        "total_amount": float(total_amount),
        "payment_method": None,
        "payment_status": "unpaid",
        "channel": "whatsapp",
        "raw_order_summary": raw_summary,
        "created_at_utc": ts["utc_timestamp"],
        "created_at_local": ts["local_timestamp"],
        "feedback_due_at_utc": feedback_due_at_utc,
        "feedback_sent": feedback_sent,
    }]
    try:
        resp_order = requests.post(
            url_orders,
            headers=supabase_headers("return=representation"),
            json=order_payload,
            timeout=20
        )
        resp_order.raise_for_status()
        order_rows = resp_order.json()
        if not order_rows:
            return None
        order_id = order_rows[0]["id"]
    except Exception as e:
        print("Supabase insert order error:", repr(e))
        return None

    # =========================================
    # INSERT ORDER ITEMS
    # =========================================
    url_items = f"{SUPABASE_REST_URL}/order_items"

    items_payload = []

    for item in order_items_state:
        menu_entry = MENU.get((item.get("item") or "").lower(), {}) if MENU else {}

        # ✅ Guard: skip if Excel id missing
        menu_id = menu_entry.get("id")
        if not menu_id:
            print("⚠ Missing Excel id for item:", item.get("item"))
            continue

        items_payload.append({
            "order_id": order_id,

            # ✅ FK from Excel
            "menu_items_id": menu_id,

            "item_name_en": menu_entry.get("name_en") or item.get("item"),
            "item_name_ar": menu_entry.get("name_ar") or item.get("item"),
            "category": menu_entry.get("category"),

            "quantity": int(item.get("qty") or 1),
            "is_spicy": bool(item.get("spicy")),
            "is_non_spicy": bool(item.get("nonspicy")),
            "unit_price": float(item.get("price") or 0),
            "subtotal": float(item.get("subtotal") or 0),
        })

    if items_payload:
        try:
            resp_items = requests.post(
                url_items,
                headers=supabase_headers("return=minimal"),
                json=items_payload,
                timeout=20
            )
            resp_items.raise_for_status()
        except Exception as e:
            print("Supabase insert order_items error:", repr(e))

    return order_id


# =========================================================
# ROUTES
# =========================================================
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/thankyou")
def thankyou():
    order_id = request.args.get("order_id")
    try:
        order_id = int(order_id) if order_id else None
    except Exception:
        order_id = None

    if order_id:
        update_order_payment(order_id, method="online", status="paid")
        schedule_feedback_after_payment(order_id)

    return "Thank you! Payment received."


def send_feedback_reminders_internal():
    """Internal function to send feedback reminders (called by background thread and cron endpoint)"""
    if not SUPABASE_REST_URL:
        return 0

    now_utc = datetime.now(tz=ZoneInfo("UTC"))
    url = f"{SUPABASE_REST_URL}/orders"
    params = {
        "select": "id,customer_id,feedback_due_at_utc,feedback_sent,payment_status",
        "feedback_sent": "eq.false",
        "payment_status": "in.(unpaid,pending,paid)",
        "feedback_due_at_utc": f"lte.{now_utc.isoformat()}",
    }

    try:
        resp = requests.get(url, headers=supabase_headers(), params=params, timeout=20)
        resp.raise_for_status()
        orders = resp.json() or []
    except Exception as e:
        print("❌ Supabase feedback fetch error:", repr(e))
        return 0

    if not orders:
        return 0

    sent_count = 0
    processed_customers = set()
    for row in orders:
        order_id = row.get("id")
        customer_id = row.get("customer_id")
        if not customer_id or customer_id in processed_customers:
            continue
        processed_customers.add(customer_id)

        cust_url = f"{SUPABASE_REST_URL}/customers"
        cust_params = {"select": "id,phone_number,preferred_language", "id": f"eq.{customer_id}"}

        try:
            cust_resp = requests.get(cust_url, headers=supabase_headers(), params=cust_params, timeout=20)
            cust_resp.raise_for_status()
            cust_rows = cust_resp.json() or []
            if not cust_rows:
                continue
            customer = cust_rows[0]
            phone = customer.get("phone_number")
            pref_lang = (customer.get("preferred_language") or "en").lower()
        except Exception:
            continue

        if not phone:
            continue

        phone_number = normalize_wh_number(phone)
        question, buttons = build_feedback_question_and_buttons(pref_lang)

        send_ok = send_whatsapp_quick_buttons(phone_number, question, buttons)
        if not send_ok:
            continue

        FEEDBACK_PENDING[phone_number] = {"order_id": order_id, "rating": None, "awaiting_remarks": False}
        sent_count += 1

        patch_url = f"{SUPABASE_REST_URL}/orders?id=eq.{order_id}"
        patch_body = {"feedback_sent": True}
        try:
            requests.patch(patch_url, headers=supabase_headers("return=minimal"), json=patch_body, timeout=20)
            print(f"✅ Feedback sent to {phone_number} for order {order_id}")
        except Exception:
            pass

    return sent_count


@app.route("/cron/send-feedback-reminders")
def cron_send_feedback_reminders():
    """External cron endpoint for feedback reminders"""
    key = request.args.get("key")
    if key != CRON_SECRET:
        return "Forbidden", 403

    sent_count = send_feedback_reminders_internal()
    if sent_count > 0:
        return f"done - sent {sent_count} reminders", 200
    return "no pending", 200


# =========================================================
# BACKGROUND FEEDBACK SCHEDULER
# =========================================================
def feedback_scheduler_loop():
    """Background thread that checks for pending feedback every 30 seconds"""
    print("🔄 Feedback scheduler thread started (checks every 30 seconds)")
    while True:
        try:
            time.sleep(30)  # Check every 30 seconds
            sent_count = send_feedback_reminders_internal()
            if sent_count > 0:
                print(f"📤 Background scheduler: Sent {sent_count} feedback reminder(s)")
        except Exception as e:
            print(f"❌ Feedback scheduler error: {repr(e)}")


def start_feedback_scheduler():
    """Start the background feedback scheduler thread"""
    thread = threading.Thread(target=feedback_scheduler_loop, daemon=True)
    thread.start()


# Start the background scheduler when app initializes
start_feedback_scheduler()

# =========================================================
# WHATSAPP CLOUD WEBHOOK
# =========================================================
@app.route("/whatsapp/webhook", methods=["GET", "POST"])
def whatsapp_webhook():
    # VERIFY (GET)
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        if mode == "subscribe" and token == WHATSAPP_VERIFY_TOKEN:
            return challenge, 200
        return "Forbidden", 403

    data = request.get_json(force=True) or {}
    entry_list = data.get("entry") or []
    if not entry_list:
        return "ok", 200
    changes = entry_list[0].get("changes") or []
    if not changes:
        return "ok", 200
    value = changes[0].get("value") or {}

    if value.get("statuses"):
        return "ok", 200

    contacts = value.get("contacts") or []
    wa_name = None
    if contacts:
        wa_name = (contacts[0].get("profile") or {}).get("name")

    messages = value.get("messages") or []
    if not messages:
        return "ok", 200

    msg_obj = messages[0]
    user_number = normalize_wh_number(msg_obj.get("from"))
    msg_type = msg_obj.get("type")
    if not user_number:
        return "ok", 200

    ctx = WHATSAPP_SESSIONS.get(user_number, {})
    stored_lang = (ctx.get("lang") or "").lower()

    is_voice = False
    from_button = False
    user_text = ""
    button_id = ""
    button_title = ""

    # Parse message
    if msg_type == "interactive":
        from_button = True
        interactive = msg_obj.get("interactive") or {}
        i_type = interactive.get("type")

        if i_type == "button_reply":
            btn = interactive.get("button_reply") or {}
            button_id = str(btn.get("id") or "")
            button_title = str(btn.get("title") or "")

        if not button_id:
            return "ok", 200

    elif msg_type in ("audio", "voice"):
        audio_obj = msg_obj.get("audio") or msg_obj.get("voice") or {}
        media_id = audio_obj.get("id")
        text_from_voice = transcribe_audio_from_cloud(media_id)
        if not text_from_voice:
            lang_for_fallback = stored_lang if stored_lang in ("en", "ar") else "en"
            fallback_msg = (
                "عذراً، لم أستطع فهم الرسالة الصوتية. اكتب طلبك نصاً"
                if lang_for_fallback == "ar"
                else "Sorry, I couldn’t understand that voice message. Please type your order."
            )
            send_whatsapp_text(user_number, fallback_msg)
            return "ok", 200
        user_text = text_from_voice
        is_voice = True

    else:
        txt = msg_obj.get("text") or {}
        user_text = str(txt.get("body") or "") if isinstance(txt, dict) else str(txt or "")

    user_text = str(user_text or "")

    # ------------------------
    # Language decide (FIXED)
    # ------------------------
    def contains_arabic(txt: str) -> bool:
        return any("\u0600" <= ch <= "\u06ff" for ch in (txt or ""))

    def is_number_only(txt: str) -> bool:
        if not txt:
            return False
        t = txt.strip()
        return _normalize_digits(t).replace(".", "").isdigit()

    lang_probe_text = user_text
    if from_button:
        lang_probe_text = (button_title or button_id or user_text or "")

    if from_button and stored_lang in ("en", "ar"):
        lang = stored_lang
    else:
        if contains_arabic(lang_probe_text):
            lang = "ar"
        elif is_number_only(lang_probe_text) and stored_lang in ("en", "ar"):
            lang = stored_lang
        else:
            lang = detect_language(lang_probe_text or "") or "en"

    ctx["lang"] = lang
    WHATSAPP_SESSIONS[user_number] = ctx

    # Customer + message log
    customer_id = upsert_customer(user_number, whatsapp_name=wa_name, lang=lang)
    save_message(
        customer_id=customer_id,
        order_id=None,
        direction="user_to_bot",
        message_type="audio" if is_voice else "text",
        text=(button_id if from_button else user_text),
        audio_url=None,
        is_voice=is_voice,
        language=lang,
        raw_payload=data,
    )

    # ✅ NEW ORDER REQUEST - Check FIRST before any other processing
    # This catches "I want to order more", "new order", etc. at ANY stage
    if not from_button:  # Only for text messages, not button clicks
        user_text_lower = user_text.lower().strip()
        
        # Check if message looks like it contains actual food items
        food_keywords = [
            "burger", "sandwich", "coffee", "drink", "meal", "wrap", "side", "fries",
            "pepsi", "water", "juice", "chicken", "beef", "snack",
            "برجر", "ساندويتش", "قهوة", "مشروب", "وجبة", "بطاطس", "دجاج"
        ]
        has_food_items = any(food in user_text_lower for food in food_keywords)
        
        # Only trigger new order if keywords match AND no food items mentioned
        # This prevents "I want to order burger" from triggering new order
        new_order_keywords = [
            "new order", "start new order", "another order", "start again",
            "order more", "want to order more", "order again", "place new order",
            "one more order", "add one more order",
            "طلب جديد", "طلب آخر", "أبدأ من جديد", "طلب جديد من فضلك", "طلب مرة أخرى"
        ]
        
        # Match keyword but EXCLUDE if food items are mentioned (it's likely a real order)
        if any(keyword in user_text_lower for keyword in new_order_keywords) and not has_food_items:
            # Reset session completely
            WHATSAPP_SESSIONS[user_number] = {
                "state": {"stage": None, "order": [], "total": 0, "last_item": None, "last_qty": 0, 
                         "last_confirmed_item": None, "pending_item": None, "spice_queue": [], "generic_queue": []},
                "messages": [],
                "lang": lang,
            }
            reply = (
                "تم بدء طلب جديد! 🎉\n\nماذا تريد أن تطلب؟\n\n" + build_branches_message("ar")
                if lang == "ar" else
                "New order started! 🎉\n\nWhat would you like to order?\n\n" + build_branches_message("en")
            )
            send_whatsapp_text(user_number, reply)
            return "ok", 200

    # burger_more / sand_more pagination
    if from_button and button_id == "burger_more":
        ctx_b = WHATSAPP_SESSIONS.get(user_number, {})
        st_b = ctx_b.get("state") or {}
        st_b["burger_page"] = int(st_b.get("burger_page") or 0) + 1
        ctx_b["state"] = st_b
        WHATSAPP_SESSIONS[user_number] = ctx_b
        send_specific_burger_buttons(user_number, lang)
        return "ok", 200

    if from_button and button_id == "sand_more":
        ctx_s = WHATSAPP_SESSIONS.get(user_number, {})
        st_s = ctx_s.get("state") or {}
        st_s["sand_page"] = int(st_s.get("sand_page") or 0) + 1
        ctx_s["state"] = st_s
        WHATSAPP_SESSIONS[user_number] = ctx_s
        send_specific_sandwich_buttons(user_number, lang)
        return "ok", 200

    # Feedback buttons
    if from_button and button_id in ("feedback_excellent", "feedback_satisfied", "feedback_not_satisfied"):
        fb_state = FEEDBACK_PENDING.get(user_number) or {}
        order_id_fb = fb_state.get("order_id")
        lang_norm = (WHATSAPP_SESSIONS.get(user_number, {}).get("lang") or lang or "en").lower()

        if lang_norm.startswith("ar"):
            rating = "ممتاز" if button_id == "feedback_excellent" else ("مرضي" if button_id == "feedback_satisfied" else "غير مرضي")
            positive_q = "ما هو الصنف الذي أعجبك أكثر؟"
            negative_q = "ما هو الصنف الذي لم يعجبك أو ما الذي يمكننا تحسينه؟"
        else:
            rating = "excellent" if button_id == "feedback_excellent" else ("satisfied" if button_id == "feedback_satisfied" else "not_satisfied")
            positive_q = "Which item did you like the most?"
            negative_q = "Which item didn’t you like, or what could we improve?"

        # Set up follow-up based on sentiment
        if button_id in ("feedback_excellent", "feedback_satisfied"):
            FEEDBACK_PENDING[user_number] = {"order_id": order_id_fb, "rating": rating, "awaiting_remarks": True}
            send_whatsapp_text(user_number, positive_q)
            return "ok", 200

        # Not satisfied
        FEEDBACK_PENDING[user_number] = {"order_id": order_id_fb, "rating": rating, "awaiting_remarks": True}
        send_whatsapp_text(user_number, negative_q)
        return "ok", 200

    # Feedback remarks
    fb_pending = FEEDBACK_PENDING.get(user_number)
    if fb_pending and (not from_button) and fb_pending.get("awaiting_remarks"):
        remarks = (user_text or "").strip()
        rating = fb_pending.get("rating") or "satisfied"
        order_id_fb = fb_pending.get("order_id")
        create_order_feedback(order_id_fb, rating, remarks)
        FEEDBACK_PENDING.pop(user_number, None)
        send_whatsapp_text(user_number, "شكرًا لملاحظاتك!" if lang == "ar" else "Thank you for your feedback!")
        return "ok", 200

    # payment_cancel OR cancel_order_btn -> show cancel options
    if from_button and button_id in ("payment_cancel", "cancel_order_btn"):
        ctx_c = WHATSAPP_SESSIONS.get(user_number, {})
        s_c = ctx_c.get("state") or {"stage": None, "order": [], "total": 0, "last_item": None, "last_qty": 0, "last_confirmed_item": None, "pending_item": None, "spice_queue": [], "generic_queue": []}
        order = s_c.get("order") or []

        if not order:
            send_whatsapp_text(user_number, "لا يوجد طلب حالي لإلغائه." if lang == "ar" else "There is no active order to cancel.")
            return "ok", 200

        s_c["stage_prev"] = s_c.get("stage")
        s_c["stage"] = "cancel_choice"
        ctx_c["state"] = s_c
        ctx_c["lang"] = lang
        WHATSAPP_SESSIONS[user_number] = ctx_c

        body = "ماذا تريد أن تفعل بالطلب؟" if lang == "ar" else "What would you like to do?"
        buttons = (
            [{"id": "cancel_entire", "title": "إلغاء الطلب بالكامل"}, {"id": "cancel_item", "title": "إلغاء صنف معين"}]
            if lang == "ar"
            else [{"id": "cancel_entire", "title": "Entire order"}, {"id": "cancel_item", "title": "Specific item"}]
        )
        send_whatsapp_quick_buttons(user_number, body, buttons)
        return "ok", 200

    # Cancel handlers: cancel_entire / cancel_item / cancel_more / cancel_item_<idx>
    if from_button and (
        button_id in ("cancel_entire", "cancel_item", "cancel_more")
        or button_id.startswith("cancel_item_")
    ):
        ctx_c = WHATSAPP_SESSIONS.get(user_number, {})
        s_c = ctx_c.get("state") or {"stage": None, "order": [], "total": 0, "spice_queue": [], "generic_queue": []}
        order = s_c.get("order") or []

        if button_id == "cancel_entire":
            if not order:
                send_whatsapp_text(user_number, "لا يوجد طلب." if lang == "ar" else "There is no active order.")
                return "ok", 200

            cancel_order_in_db(s_c.get("order_id"))

            ctx_c["state"] = {"stage": None, "order": [], "total": 0, "last_item": None, "last_qty": 0, "last_confirmed_item": None, "pending_item": None, "spice_queue": [], "generic_queue": []}
            WHATSAPP_SESSIONS[user_number] = ctx_c

            cancel_msg = (
                "✅ تم إلغاء طلبك بنجاح.\n\n"
                "لا تقلق! يمكنك عرض قائمتنا أو تقديم طلب جديد في أي وقت. 🍔☕"
                if lang == "ar" else
                "✅ Your order has been canceled successfully.\n\n"
                "No worries! You can view our menu or place a new order anytime. 🍔☕"
            )
            send_whatsapp_text(user_number, cancel_msg)
            return "ok", 200

        if button_id == "cancel_item":
            if not order:
                send_whatsapp_text(user_number, "لا يوجد أي صنف." if lang == "ar" else "There is no item to cancel.")
                return "ok", 200

            s_c["stage"] = "cancel_item_select"
            s_c["cancel_page"] = 0
            ctx_c["state"] = s_c
            WHATSAPP_SESSIONS[user_number] = ctx_c

            send_cancel_item_buttons(user_number, lang)
            return "ok", 200

        if button_id == "cancel_more":
            if not order:
                send_whatsapp_text(user_number, "لا يوجد أي صنف." if lang == "ar" else "There is no item to cancel.")
                return "ok", 200

            s_c["stage"] = "cancel_item_select"
            s_c["cancel_page"] = int(s_c.get("cancel_page") or 0) + 1
            ctx_c["state"] = s_c
            WHATSAPP_SESSIONS[user_number] = ctx_c

            send_cancel_item_buttons(user_number, lang)
            return "ok", 200

        if button_id.startswith("cancel_item_"):
            try:
                idx = int(button_id.split("_")[-1])
            except Exception:
                idx = -1

            if idx < 0 or idx >= len(order):
                send_whatsapp_text(user_number, "حصل خطأ، حاول مرة أخرى." if lang == "ar" else "Something went wrong, please try again.")
                return "ok", 200

            s_c["stage"] = "cancel_qty_button"
            s_c["cancel_item_idx"] = idx
            ctx_c["state"] = s_c
            WHATSAPP_SESSIONS[user_number] = ctx_c

            item_line = build_single_item_line(order[idx], lang)
            ask = (
                f"كم كمية الإلغاء لـ {item_line}؟ (اكتب رقم فقط)"
                if lang == "ar"
                else f"How many would you like to cancel for {item_line}? (Type a number)"
            )
            send_whatsapp_text(user_number, ask)
            return "ok", 200

    # Qty typed for cancel_qty_button
    ctx_q = WHATSAPP_SESSIONS.get(user_number, {})
    s_q = ctx_q.get("state") or {}

    if (not from_button) and s_q.get("stage") == "cancel_qty_button" and s_q.get("cancel_item_idx") is not None:
        try:
            idx = int(s_q.get("cancel_item_idx"))
        except Exception:
            idx = -1

        order = s_q.get("order") or []
        qty = detect_qty(user_text) or 1
        qty = max(int(qty), 1)

        if idx < 0 or idx >= len(order):
            send_whatsapp_text(user_number, "حصل خطأ، حاول مرة أخرى." if lang == "ar" else "Something went wrong.")
            return "ok", 200

        item = order[idx]
        cancel_req = {"item": item["item"], "qty": qty, "spicy": item.get("spicy"), "nonspicy": item.get("nonspicy")}
        ok, reply = apply_cancel_on_order(s_q, cancel_req, lang)

        s_q.pop("cancel_item_idx", None)

        if s_q.get("order"):
            s_q["stage"] = "payment"
            ctx_q["state"] = s_q
            WHATSAPP_SESSIONS[user_number] = ctx_q
            send_payment_buttons(user_number, html_to_whatsapp(reply), lang, has_order=True)
            return "ok", 200

        ctx_q["state"] = {"stage": None, "order": [], "total": 0, "last_item": None, "last_qty": 0, "last_confirmed_item": None, "pending_item": None, "spice_queue": [], "generic_queue": []}
        WHATSAPP_SESSIONS[user_number] = ctx_q
        send_whatsapp_text(user_number, html_to_whatsapp(reply))
        return "ok", 200

    # ✅ SMART GREETING - Show welcome for casual messages, process orders directly
    # Check if this is first interaction (no session or empty session)
    ctx_check = WHATSAPP_SESSIONS.get(user_number, {})
    s_check = ctx_check.get("state") or {}
    is_first_interaction = (
        not ctx_check or 
        not s_check or 
        s_check.get("stage") is None or
        s_check.get("stage") == "branch"
    )

    # 🚫 EARLY GUARD: Abusive queries
    msg_low_guard = (user_text or "").lower()
    abusive_keywords = [
        "stupid", "idiot", "dumb", "shut up", "fuck", "shit", "bitch",
        "لعن", "قذر", "تافه"
    ]
    is_abusive_guard = any(k in msg_low_guard for k in abusive_keywords)

    if not from_button and is_abusive_guard:
        reply_guard = (
            "آسف، لا يمكنني المساعدة في ذلك. يمكن طلب عناصر القائمة فقط. الرجاء الاختيار من القائمة."
            if lang == "ar" else
            "Sorry, I can't assist with that. Only menu items can be ordered. Please choose from the menu."
        )
        send_category_buttons(user_number, lang, show_image=False)
        WHATSAPP_SESSIONS[user_number] = {
            "state": s_check or {"stage": None, "order": [], "total": 0, "last_item": None, "last_qty": 0, "last_confirmed_item": None, "pending_item": None, "spice_queue": [], "generic_queue": []},
            "messages": [],
            "lang": lang,
        }
        return "ok", 200
    
    # 🤖 GLOBAL AI-POWERED FOOD INTENT DETECTION
    # Use OpenAI to detect if user is trying to order food (including off-menu items)
    # This catches requests like "1 pizza", "2 pasta", etc. BEFORE greeting logic
    if not from_button and is_first_interaction and user_text and len(user_text.strip()) > 2:
        # Quick check: has numbers or food-related words
        has_numbers = any(char.isdigit() for char in user_text)
        common_greetings = ["hi", "hello", "hey", "salam", "مرحبا", "السلام"]
        is_likely_greeting = any(g in user_text.lower() for g in common_greetings)
        
        # Only use AI if it has numbers OR not a clear greeting
        if has_numbers or not is_likely_greeting:
            try:
                # Use LLM to classify intent
                classify_prompt = (
                    f"Classify this message as either 'FOOD_ORDER' or 'GREETING':\n"
                    f"Message: {user_text}\n\n"
                    f"Rules:\n"
                    f"- If message mentions food items (burger, pizza, pasta, coffee, sandwich, etc.) with or without quantities → FOOD_ORDER\n"
                    f"- If message is casual greeting (hi, hello, hey) → GREETING\n"
                    f"- If unsure but has numbers + food words → FOOD_ORDER\n\n"
                    f"Respond with ONLY one word: FOOD_ORDER or GREETING"
                )
                
                classify_res = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": classify_prompt}],
                    temperature=0,
                    max_tokens=10
                )
                classification = (classify_res.choices[0].message.content or "").strip().upper()
                
                if "FOOD_ORDER" in classification:
                    # It's a food order attempt - let LLM handle it with full context
                    # This will intelligently respond to off-menu items
                    WHATSAPP_SESSIONS[user_number] = {
                        "state": {"stage": None, "order": [], "total": 0, "last_item": None, "last_qty": 0, 
                                 "last_confirmed_item": None, "pending_item": None, "spice_queue": [], "generic_queue": []},
                        "messages": [],
                        "lang": lang,
                    }
                    # Fall through to main processing (will use LLM if item not in menu)
                else:
                    # It's a greeting - show welcome
                    pass  # Continue to greeting logic below
                    
            except Exception as e:
                print(f"AI intent classification error: {repr(e)}")
                # On error, fall back to original logic
        
    # 🧠 INTELLIGENT ORDER/MENU DETECTION - Check if message is order or menu request
    def looks_like_order_or_menu(text: str) -> bool:
        """Detect if text looks like a food order OR menu request"""
        if not text:
            return False
        text_lower = text.lower()
        
        # ✅ Check for menu request keywords
        menu_keywords = [
            "menu", "price", "list", "show", "what do you have", "what you have",
            "قائمة", "اسعار", "سعر", "عرض", "اظهر", "ماذا لديك"
        ]
        has_menu_keyword = any(keyword in text_lower for keyword in menu_keywords)
        
        # Has numbers (quantity indicator)
        has_numbers = any(char.isdigit() for char in text)
        
        # Has food keywords
        food_keywords = [
            "burger", "sandwich", "coffee", "drink", "meal", "wrap", "side", "fries",
            "pepsi", "water", "juice", "chicken", "beef", "snack",
            "برجر", "ساندويتش", "قهوة", "مشروب", "وجبة", "بطاطس", "دجاج"
        ]
        has_food_keyword = any(keyword in text_lower for keyword in food_keywords)
        
        # If has menu keywords, OR (numbers AND food keywords), it's an order/menu request
        return has_menu_keyword or (has_numbers and has_food_keyword)
    
    # ✅ CRITICAL: Check for non-menu items BEFORE welcome message logic
    # This prevents "pizza" from triggering welcome instead of rejection
    if not from_button and is_non_menu_item_request(user_text):
        print(f"⚠️ NON-MENU ITEM DETECTED (pre-welcome): '{user_text}'")
        
        # Initialize session if needed (first interaction)
        if user_number not in WHATSAPP_SESSIONS or not WHATSAPP_SESSIONS[user_number]:
            WHATSAPP_SESSIONS[user_number] = {
                "state": {"stage": None, "order": [], "total": 0, "last_item": None, "last_qty": 0, 
                         "last_confirmed_item": None, "pending_item": None, "spice_queue": [], "generic_queue": []},
                "messages": [],
                "lang": lang,
            }
        
        # Send polite rejection with menu redirect
        rejection_msg = (
            "عذراً، لا يمكنني مساعدتك في ذلك. يمكنك السؤال بحرية عن قائمة JOANA، وسأكون سعيداً بإرشادك.\n\n"
            "📋 يرجى الاختيار من قائمتنا:"
            if lang == "ar" else
            "Sorry, I can't assist with that. You can freely ask about Joana's menu, and I'll be happy to guide you.\n\n"
            "📋 Please choose from our menu:"
        )
        
        send_whatsapp_text(user_number, rejection_msg)
        # Show category buttons to redirect
        send_category_buttons(user_number, lang, show_image=True)
        return "ok", 200
    
    # Show welcome ONLY if: (1) first interaction with casual/greeting text, OR (2) greeting keywords anytime
    # BUT skip welcome if it looks like an order or menu request!
    if not from_button and (is_first_interaction or is_wa_greeting(user_text)):
        # If it looks like an order/menu request, DON'T show welcome - let it be processed
        if is_first_interaction and looks_like_order_or_menu(user_text):
            # Initialize session but don't show welcome - let order/menu processing handle it
            WHATSAPP_SESSIONS[user_number] = {
                "state": {"stage": None, "order": [], "total": 0, "last_item": None, "last_qty": 0, 
                         "last_confirmed_item": None, "pending_item": None, "spice_queue": [], "generic_queue": []},
                "messages": [],
                "lang": lang,
            }
            # Don't return - continue to order/menu processing below
        else:
            # It's a greeting/casual message - show welcome
            display_name = (wa_name or "").strip() or ("عميل" if lang == "ar" else "Customer")
            buttons = (
                [{"id": "order_text", "title": "الطلب عبر الرسائل"}, {"id": "order_voice", "title": "الطلب عبر الصوت"}]
                if lang == "ar"
                else [{"id": "order_text", "title": "Order via text"}, {"id": "order_voice", "title": "Order via voice"}]
            )
            body = (f"مرحباً *{display_name}*!\n\n" + build_branches_message("ar")) if lang == "ar" else (f"Welcome *{display_name}*!\n\n" + build_branches_message("en"))

            WHATSAPP_SESSIONS[user_number] = {
                "state": {"stage": "branch", "order": [], "total": 0, "last_item": None, "last_qty": 0, "last_confirmed_item": None, "pending_item": None, "spice_queue": [], "generic_queue": []},
                "messages": [],
                "lang": lang,
            }
            send_whatsapp_quick_buttons(user_number, body, buttons)
            return "ok", 200

    # Button routing
    if from_button:
        if button_id.startswith(("item_", "cat_", "pick_burger_", "pick_sandwich_", "spice_", "payment_", "pay_", "order_")) or button_id in ("more_items", "finish_order", "add_more_items", "burger_more", "sand_more"):
            user_text = button_id
        else:
            user_text = button_title or button_id or ""

    clean = (user_text or "").strip().lower()

    if clean == "order_text":
        send_category_buttons(user_number, lang, show_image=True)
        return "ok", 200

    if clean == "order_voice":
        send_whatsapp_text(user_number, "من فضلك أرسل طلبك كرسالة صوتية" if lang == "ar" else "Please send your order as a voice message")
        return "ok", 200

    if clean == "cat_burgers_meals":
        WA_CATEGORY_STATE[user_number] = {"category": "burgers_meals", "index": 0}
        send_items_for_category(user_number, "burgers_meals", lang)
        return "ok", 200

    if clean == "cat_sandwiches":
        WA_CATEGORY_STATE[user_number] = {"category": "sandwiches", "index": 0}
        send_items_for_category(user_number, "sandwiches", lang)
        return "ok", 200

    if clean == "cat_snacks_sides":
        WA_CATEGORY_STATE[user_number] = {"category": "snacks_sides", "index": 0}
        send_items_for_category(user_number, "snacks_sides", lang)
        return "ok", 200

    if clean == "more_items" and user_number in WA_CATEGORY_STATE:
        st = WA_CATEGORY_STATE.get(user_number, {})
        cat = st.get("category")
        if cat:
            items = get_items_by_category(cat)
            new_index = st.get("index", 0) + 2
            if new_index >= len(items):
                new_index = 0
            WA_CATEGORY_STATE[user_number] = {"category": cat, "index": new_index}
            send_items_for_category(user_number, cat, lang)
            return "ok", 200

    # ✅ Handle spice button clicks
    if from_button and button_id in ("spice_spicy", "spice_non_spicy"):
        # Convert button ID to text that the spice handler understands
        user_text = "spicy" if button_id == "spice_spicy" else "non-spicy"
        # Fall through to main chat handler with the converted text
        # The await_spice stage handler will process it correctly

    if clean in ["add_more_items", "add more items", "إضافة أصناف أخرى", "اضافة اصناف اخرى", "payment_add_more"]:
        sess = WHATSAPP_SESSIONS.get(user_number, {})
        st = sess.get("state") or {}
        
        # ✅ CRITICAL FIX: Check if there are items in generic_queue first!
        # If user said "3 sandwiches and 3 meals", after sandwiches are done,
        # clicking "Add more items" should process the meals queue, not ask category
        if st.get("generic_queue"):
            print(f"🔍 DEBUG [add_more_items button]: generic_queue has {len(st['generic_queue'])} items remaining, processing next...")
            # Process the next item from the queue instead of showing category menu
            user_text = "continue queue"  # This will trigger queue processing in main handler
            # Fall through to main brain bridge
        else:
            # No queue items, show category selection
            st["stage"] = "add_more"
            sess["state"] = st
            sess["lang"] = lang
            WHATSAPP_SESSIONS[user_number] = sess
            send_category_buttons(user_number, lang, show_image=False)
            return "ok", 200

    if clean == "finish_order" or clean == "finish order" or clean == "إنهاء الطلب" or clean == "انهاء الطلب":
        user_text = "done"

    if clean == "payment_cash":
        user_text = "cash"

    if clean == "payment_online":
        user_text = "online"

    if clean == "payment_proceed":
        user_text = "yes"

    # Main brain bridge
    try:
        result = process_whatsapp_message(
            user_number,
            user_text,
            lang,
            is_voice=is_voice,
            from_button=from_button,
            customer_id=customer_id,
        )

        reply_html = result.get("reply") or ("Sorry, something went wrong." if lang == "en" else "عذراً، حدث خطأ ما.")
        reply_text = html_to_whatsapp(reply_html)

        stage = result.get("stage")
        order = result.get("order") or []

        if result.get("menu"):
            image_url = "https://qintellecttechnologies.com/joana_chatbot/static/menu.PNG"
            send_whatsapp_image(user_number, image_url, caption=("Here is our menu" if lang == "en" else "هذه قائمتنا"))

        if stage == "await_specific_burger":
            ctx_b = WHATSAPP_SESSIONS.get(user_number, {})
            st_b = ctx_b.get("state") or {}
            if st_b.get("burger_page") is None:
                st_b["burger_page"] = 0
                ctx_b["state"] = st_b
                WHATSAPP_SESSIONS[user_number] = ctx_b
            send_specific_burger_buttons(user_number, lang)
            return "ok", 200

        if stage == "await_specific_sandwich":
            ctx_s = WHATSAPP_SESSIONS.get(user_number, {})
            st_s = ctx_s.get("state") or {}
            if st_s.get("sand_page") is None:
                st_s["sand_page"] = 0
                ctx_s["state"] = st_s
                WHATSAPP_SESSIONS[user_number] = ctx_s
            send_specific_sandwich_buttons(user_number, lang)
            return "ok", 200

        if stage == "await_spice":
            buttons = (
                [{"id": "spice_spicy", "title": "حار"}, {"id": "spice_non_spicy", "title": "بدون حار"}, {"id": "cancel_order_btn", "title": "إلغاء"}]
                if lang == "ar"
                else [{"id": "spice_spicy", "title": "Spicy"}, {"id": "spice_non_spicy", "title": "Non-spicy"}, {"id": "cancel_order_btn", "title": "Cancel"}]
            )
            send_whatsapp_quick_buttons(user_number, reply_text, buttons)
            return "ok", 200

        if stage == "add_more" and order:
            buttons = (
                [{"id": "add_more_items", "title": "إضافة أصناف"}, {"id": "cancel_order_btn", "title": "إلغاء"}, {"id": "finish_order", "title": "إنهاء"}]
                if lang == "ar"
                else [{"id": "add_more_items", "title": "Add more"}, {"id": "cancel_order_btn", "title": "Cancel"}, {"id": "finish_order", "title": "Finish"}]
            )
            send_whatsapp_quick_buttons(user_number, reply_text, buttons)
            return "ok", 200

        if stage == "payment" and order:
            send_payment_buttons(user_number, reply_text, lang, has_order=True)
            return "ok", 200

        # ✅ REMOVED: choose_payment stage interceptor
        # Let the chat handler process the actual payment method selection
        # The buttons were already sent when entering choose_payment stage
        
        # ✅ Payment method buttons - show Cash/Online buttons when order summary is displayed
        if stage == "choose_payment" and order:
            buttons = (
                [{"id": "payment_cash", "title": "نقدي"}, {"id": "payment_online", "title": "دفع إلكتروني"}]
                if lang == "ar"
                else [{"id": "payment_cash", "title": "Cash"}, {"id": "payment_online", "title": "Online"}]
            )
            send_whatsapp_quick_buttons(user_number, reply_text, buttons)
            return "ok", 200
        
        # ✅ REMOVED: await_feedback stage interceptor
        # Feedback is now scheduled to appear 1 minute after payment via schedule_feedback_after_payment()
        # This allows the receipt to be displayed first, then feedback comes later

        send_whatsapp_text(user_number, reply_text)
        save_message(
            customer_id=customer_id,
            order_id=None,
            direction="bot_to_user",
            message_type="text",
            text=reply_text,
            audio_url=None,
            is_voice=False,
            language=lang,
            raw_payload=None,
        )
        return "ok", 200

    except Exception as e:
        print("Error in whatsapp_webhook:", repr(e))
        send_whatsapp_text(user_number, "Sorry, something went wrong." if lang == "en" else "عذراً، حدث خطأ ما.")
        return "ok", 200

# =========================================================
# INTERNAL CHAT BRIDGE
# =========================================================
def process_whatsapp_message(
    user_number: str,
    user_text: str,
    user_lang_hint: str | None = None,
    is_voice: bool = False,
    from_button: bool = False,
    customer_id: int | None = None,
) -> dict:
    ctx = WHATSAPP_SESSIONS.get(user_number, {})
    prev_state = ctx.get("state")
    prev_messages = ctx.get("messages")

    with app.test_request_context(
        "/api/chat",
        method="POST",
        json={
            "message": user_text,
            "is_voice": is_voice,
            "lang_hint": user_lang_hint,
            "from_button": from_button,
            "customer_id": customer_id,
        },
    ):
        if prev_state is not None:
            session["state"] = prev_state
        if prev_messages is not None:
            session["messages"] = prev_messages

        resp = chat()

        WHATSAPP_SESSIONS[user_number] = {
            "state": session.get("state"),
            "messages": session.get("messages"),
            "lang": user_lang_hint or ctx.get("lang"),
        }

        resp_obj = resp[0] if isinstance(resp, tuple) else resp
        data = resp_obj.get_json() or {}
        return data


def make_chat_response(reply, lang, menu=None):
    s = session.get("state", {"stage": None, "order": [], "total": 0})
    payload = {
        "reply": reply,
        "lang": lang,
        "stage": s.get("stage"),
        "order": s.get("order"),
        "total": s.get("total", 0),
    }
    if menu:
        payload["menu"] = menu
    return jsonify(payload)

# =========================================================
# /api/chat  (MAIN BRAIN)
# =========================================================
@app.route("/api/chat", methods=["POST"])
def chat():
    global MENU, BRANCHES

    MENU = load_menu()
    BRANCHES = load_branches()

    s = session.get("state") or {"stage": None, "order": [], "total": 0}
    s.setdefault("order", [])
    s.setdefault("total", 0)
    s.setdefault("last_item", None)
    s.setdefault("last_qty", 0)
    s.setdefault("last_confirmed_item", None)
    s.setdefault("pending_item", None)
    s.setdefault("spice_queue", [])
    s.setdefault("generic_queue", [])  # ✅ NEW
    session["state"] = s
    session["messages"] = session.get("messages", [])

    data = request.get_json(force=True) or {}
    msg_raw = (data.get("message") or "").strip()
    is_voice = bool(data.get("is_voice", False))
    lang_hint = data.get("lang_hint")
    from_button = bool(data.get("from_button", False))
    customer_id = data.get("customer_id")

    lang = detect_language(msg_raw)
    if any("\u0600" <= ch <= "\u06ff" for ch in msg_raw):
        lang = "ar"
    if lang_hint in ("en", "ar"):
        lang = lang_hint

    msg_norm, msg_norm_l, typed_button_like = normalize_user_text(msg_raw)
    if typed_button_like and msg_norm_l.startswith("item_"):
        from_button = True

    msg_raw = msg_norm
    msg = msg_norm
    msg_l = msg_norm_l

    intent = detect_intent(msg)
    session["messages"].append({"role": "user", "content": msg})
    
    # ✅ DEBUG: Log the key decision variables BEFORE multi-item check
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"📍 ROUTING DECISION POINT:")
    print(f"   msg_raw: '{msg_raw}'")
    print(f"   stage: {s.get('stage')}")
    print(f"   from_button: {from_button}")
    print(f"   is_cancel: {is_cancel_text(msg_raw)}")
    print(f"   stage in (None, 'add_more'): {s.get('stage') in (None, 'add_more')}")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    
    # ✅ STRICT MENU ENFORCEMENT: Reject non-menu items at ANY stage
    if not from_button and is_non_menu_item_request(msg_raw):
        print(f"⚠️ NON-MENU ITEM DETECTED: '{msg_raw}'")
        
        # Build polite rejection with menu redirect
        rejection_msg = (
            "عذراً، لا يمكنني مساعدتك في ذلك. يمكنك السؤال بحرية عن قائمة JOANA، وسأكون سعيداً بإرشادك.\n\n"
            "📋 يرجى الاختيار من قائمتنا:"
            if lang == "ar" else
            "Sorry, I can't assist with that. You can freely ask about Joana's menu, and I'll be happy to guide you.\n\n"
            "📋 Please choose from our menu:"
        )
        
        # Show category buttons to redirect user
        return make_chat_response(rejection_msg, lang)
    
    # ✅ HANDLE "continue queue" trigger from add_more_items button
    if msg_l == "continue queue":
        print("🔍 DEBUG [continue queue]: Processing next item from generic_queue")
        prompt = _start_next_generic_from_queue(s, MENU, lang)
        if prompt:
            session["state"] = s
            return make_chat_response(prompt, lang)
        # If no queue items, fall through to normal flow
        msg_l = "menu"  # Trigger category selection
    
    # -------------------------
    # BURGER TEXT STAGE (Handling user typed specific burger)
    # -------------------------
    if s.get("stage") == "await_specific_burger" and not msg_l.startswith("pick_burger_"):
        # Let 'cancel' fall through
        if not is_cancel_text(msg_raw):
            # ✅ ESCAPE HATCH: if user sends multi-item while in selection stage
            if (not from_button) and msg_raw and looks_like_multi_item_text(msg_raw):
                s["stage"] = None
                session["state"] = s
                return handle_multi_item_text(msg_raw, s, MENU, lang)

            # Try to find a burger in the text
            picked_key = None
            t = _norm_text(msg_raw)
            
            # 1. Search by exact name in MENU
            for k, info in MENU.items():
                if (info.get("category") or "") == "burgers_meals":
                    en = (info.get("name_en") or "").lower()
                    ar = (info.get("name_ar") or "").lower()
                    if en in t or ar in t:
                        picked_key = k
                        break
            
            if picked_key:
                # We found a specific burger. 
                # We assume the user wants to fulfill the pending generic qty with this specific burger,
                # UNLESS they specified a new qty in the text.
                # Simple approach: Use pending qty.
                qty = int(s.get("last_qty") or 1)
                print(f"🔍 DEBUG [burger text selection]: User typed '{msg_raw}', picked_key={picked_key}, qty from last_qty={qty}")
                
                # Update state to await spice
                s["last_item"] = picked_key
                s["last_qty"] = qty
                s["stage"] = "await_spice"
                session["state"] = s
                
                p_name = picked_key
                ask = (f"بالنسبة لـ {qty} {p_name}، هل تفضلها حارة أم بدون حار؟" if lang == "ar" else f"For your {qty} {p_name.title()}, would you like them spicy or non-spicy?")
                return make_chat_response(ask, lang)

            # If strictly waiting for burger and input is not cancel/multi
            # Use LLM to handle off-menu requests intelligently
            if "menu" not in msg_l:
                reply = get_llm_reply(msg_raw, lang)
                guide = (
                    "\n\nمن فضلك اختر برجر من القائمة. 🍔"
                    if lang == "ar" else
                    "\n\nPlease choose a burger from our menu. 🍔"
                )
                return make_chat_response(merge_replies(reply, guide), lang)

    # -------------------------
    # SANDWICH TEXT STAGE (Handling user typed specific sandwich)
    # -------------------------
    if s.get("stage") == "await_specific_sandwich" and not msg_l.startswith("pick_sandwich_"):
        if not is_cancel_text(msg_raw):
            # ✅ ESCAPE HATCH
            if (not from_button) and msg_raw and looks_like_multi_item_text(msg_raw):
                s["stage"] = None
                session["state"] = s
                return handle_multi_item_text(msg_raw, s, MENU, lang)

            # Try to find a sandwich in the text
            picked_key = None
            t = _norm_text(msg_raw)
            
            for k, info in MENU.items():
                if (info.get("category") or "") == "sandwiches":
                    en = (info.get("name_en") or "").lower()
                    ar = (info.get("name_ar") or "").lower()
                    if en in t or ar in t:
                        picked_key = k
                        break
            
            if picked_key:
                qty = int(s.get("last_qty") or 1)
                info = MENU.get(picked_key) or {}
                price = float(info.get("price") or 0)
                
                add_item_to_order_summary(s, picked_key, qty, price)
                
                # Check next in queue
                prompt = _start_next_generic_from_queue(s, MENU, lang)
                if prompt:
                    session["state"] = s
                    return make_chat_response(prompt, lang)
                
                s["stage"] = "add_more"
                summary, total = build_order_summary_and_total(s["order"], lang)
                s["total"] = total
                session["state"] = s
                
                reply = (
                    f"{picked_key} ×{qty} added.<br>Order summary:<br>" + "<br>".join(summary) + "<br><br>Anything else?"
                    if lang != "ar"
                    else f"تم إضافة {picked_key} ×{qty}.<br>ملخص الطلب:<br>" + "<br>".join(summary) + "<br><br>أي شيء آخر؟"
                )
                return make_chat_response(reply, lang)

            # Use LLM to handle off-menu requests intelligently
            if "menu" not in msg_l:
                reply = get_llm_reply(msg_raw, lang)
                guide = (
                    "\n\nمن فضلك اختر ساندوتش من القائمة. 🥪"
                    if lang == "ar" else
                    "\n\nPlease choose a sandwich from our menu. 🥪"
                )
                return make_chat_response(merge_replies(reply, guide), lang)

    # -------------------------
    # meals text stage
    # -------------------------
    if s.get("stage") == "await_specific_meal_text":
        user_pick = (msg_raw or "").strip().lower()
        picked_key = None  # safety

        # ✅ ESCAPE HATCH: if user sends multi-item while in selection stage
        if (not from_button) and msg_raw and looks_like_multi_item_text(msg_raw):
            s["stage"] = None
            session["state"] = s
            return handle_multi_item_text(msg_raw, s, MENU, lang)

        if user_pick == "more":
            s["cat_page"] = int(s.get("cat_page") or 0) + 1
            body, chunk, _ = _format_category_page(MENU, "meals", lang, page=s["cat_page"])
            s["last_page_keys"] = chunk or []

            if not body:
                s["cat_page"] = 0
                body, chunk, _ = _format_category_page(MENU, "meals", lang, page=0)
                s["last_page_keys"] = chunk or []

            title = "Select a meal:" if lang != "ar" else "اختاري وجبة:"
            session["state"] = s
            return make_chat_response(f"{title}\n{body}", lang)

        # detect a MEALS item name inside a long sentence
        t = _norm_text(msg_raw or "")
        for name, key in (NAME_TO_KEY or {}).items():
            if name and (name in t):
                info = MENU.get(key) or {}
                if (info.get("category") or "").strip().lower() == "meals":
                    picked_key = key
                    break

        # fallback: page resolver (number or name from current page)
        if not picked_key:
            picked_key = _resolve_text_pick_to_menu_key(
                MENU,
                s.get("last_page_keys") or [],
                msg_raw,
                lang
            )

        # fallback: search whole category if not on current page
        if not picked_key:
            picked_key = _resolve_text_pick_to_menu_key_any_in_category(
                MENU, "meals", msg_raw
            )

        if not picked_key:
            title = "Select a meal:" if lang != "ar" else "اختاري وجبة:"
            body, chunk, _ = _format_category_page(
                MENU, "meals", lang, page=int(s.get("cat_page") or 0)
            )
            s["last_page_keys"] = chunk or []
            session["state"] = s
            return make_chat_response(
                f"Invalid selection. Type number/name or 'more'.\n\n{title}\n{body}"
                if lang != "ar"
                else f"اختيار غير صحيح. اكتبي الرقم/الاسم أو more.\n\n{title}\n{body}",
                lang
            )

        qty = int(s.get("last_qty") or 1)

        info = MENU.get(picked_key) or {}
        try:
            price = float(info.get("price") or 0)
        except Exception:
            price = 0

        if price <= 0:
            return make_chat_response(
                "Invalid item price. Please pick again."
                if lang != "ar"
                else "سعر غير صحيح. اختاري مرة أخرى.",
                lang
            )

        add_item_to_order_summary(s, picked_key, qty, price)

        prompt = _start_next_generic_from_queue(s, MENU, lang)
        session["state"] = s
        if prompt:
            return make_chat_response(prompt, lang)

        s["stage"] = "add_more"
        session["state"] = s
        return make_chat_response(
            "Added. Anything else?"
            if lang != "ar"
            else "تمت الإضافة. هل تريدين شيئاً آخر؟",
            lang
        )

    # -------------------------
    # juices text stage
    # -------------------------
    if s.get("stage") == "await_specific_juice_text":
        user_pick = (msg_raw or "").strip().lower()
        picked_key = None  # safety

        # ✅ ESCAPE HATCH: if user sends multi-item while in selection stage
        if (not from_button) and msg_raw and looks_like_multi_item_text(msg_raw):
            s["stage"] = None
            session["state"] = s
            return handle_multi_item_text(msg_raw, s, MENU, lang)

        if user_pick == "more":
            s["cat_page"] = int(s.get("cat_page") or 0) + 1
            body, chunk, _ = _format_category_page(MENU, "juices", lang, page=s["cat_page"])
            s["last_page_keys"] = chunk or []

            if not body:
                s["cat_page"] = 0
                body, chunk, _ = _format_category_page(MENU, "juices", lang, page=0)
                s["last_page_keys"] = chunk or []

            title = "Select a juice:" if lang != "ar" else "اختاري عصير:"
            session["state"] = s
            return make_chat_response(f"{title}\n{body}", lang)

        # detect a JUICES item name inside a long sentence
        t = _norm_text(msg_raw or "")
        for name, key in (NAME_TO_KEY or {}).items():
            if name and (name in t):
                info = MENU.get(key) or {}
                if (info.get("category") or "").strip().lower() == "juices":
                    picked_key = key
                    break

        # fallback: page resolver (number or name from current page)
        if not picked_key:
            picked_key = _resolve_text_pick_to_menu_key(
                MENU,
                s.get("last_page_keys") or [],
                msg_raw,
                lang
            )

        # fallback: search whole category if not on current page
        if not picked_key:
            picked_key = _resolve_text_pick_to_menu_key_any_in_category(
                MENU, "juices", msg_raw
            )

        if not picked_key:
            title = "Select a juice:" if lang != "ar" else "اختاري عصير:"
            body, chunk, _ = _format_category_page(
                MENU, "juices", lang, page=int(s.get("cat_page") or 0)
            )
            s["last_page_keys"] = chunk or []
            session["state"] = s
            return make_chat_response(
                f"Invalid selection. Type number/name or 'more'.\n\n{title}\n{body}"
                if lang != "ar"
                else f"اختيار غير صحيح. اكتبي الرقم/الاسم أو more.\n\n{title}\n{body}",
                lang
            )

        qty = int(s.get("last_qty") or 1)

        info = MENU.get(picked_key) or {}
        try:
            price = float(info.get("price") or 0)
        except Exception:
            price = 0

        if price <= 0:
            return make_chat_response(
                "Invalid item price. Please pick again."
                if lang != "ar"
                else "سعر غير صحيح. اختاري مرة أخرى.",
                lang
            )

        add_item_to_order_summary(s, picked_key, qty, price)

        prompt = _start_next_generic_from_queue(s, MENU, lang)
        session["state"] = s
        if prompt:
            return make_chat_response(prompt, lang)

        s["stage"] = "add_more"
        session["state"] = s
        return make_chat_response(
            "Added. Anything else?"
            if lang != "ar"
            else "تمت الإضافة. هل تريدين شيئاً آخر؟",
            lang
        )

    # -------------------------
    # drinks text stage
    # -------------------------
    if s.get("stage") == "await_specific_drink_text":
        user_pick = (msg_raw or "").strip().lower()
        picked_key = None  # safety

        # ✅ ESCAPE HATCH: if user sends multi-item while in selection stage
        if (not from_button) and msg_raw and looks_like_multi_item_text(msg_raw):
            s["stage"] = None
            session["state"] = s
            return handle_multi_item_text(msg_raw, s, MENU, lang)

        if user_pick == "more":
            s["cat_page"] = int(s.get("cat_page") or 0) + 1
            body, chunk, _ = _format_category_page(MENU, "drinks", lang, page=s["cat_page"])
            s["last_page_keys"] = chunk or []

            if not body:
                s["cat_page"] = 0
                body, chunk, _ = _format_category_page(MENU, "drinks", lang, page=0)
                s["last_page_keys"] = chunk or []

            title = "Select a drink:" if lang != "ar" else "اختاري مشروب:"
            session["state"] = s
            return make_chat_response(f"{title}\n{body}", lang)

        # detect a DRINKS item name inside a long sentence
        t = _norm_text(msg_raw or "")
        for name, key in (NAME_TO_KEY or {}).items():
            if name and (name in t):
                info = MENU.get(key) or {}
                if (info.get("category") or "").strip().lower() == "drinks":
                    picked_key = key
                    break

        # fallback: page resolver (number or name from current page)
        if not picked_key:
            picked_key = _resolve_text_pick_to_menu_key(
                MENU,
                s.get("last_page_keys") or [],
                msg_raw,
                lang
            )

        # fallback: search whole category if not on current page
        if not picked_key:
            picked_key = _resolve_text_pick_to_menu_key_any_in_category(
                MENU, "drinks", msg_raw
            )

        if not picked_key:
            title = "Select a drink:" if lang != "ar" else "اختاري مشروب:"
            body, chunk, _ = _format_category_page(
                MENU, "drinks", lang, page=int(s.get("cat_page") or 0)
            )
            s["last_page_keys"] = chunk or []
            session["state"] = s
            return make_chat_response(
                f"Invalid selection. Type number/name or 'more'.\n\n{title}\n{body}"
                if lang != "ar"
                else f"اختيار غير صحيح. اكتبي الرقم/الاسم أو more.\n\n{title}\n{body}",
                lang
            )

        qty = int(s.get("last_qty") or 1)

        info = MENU.get(picked_key) or {}
        try:
            price = float(info.get("price") or 0)
        except Exception:
            price = 0

        if price <= 0:
            return make_chat_response(
                "Invalid item price. Please pick again."
                if lang != "ar"
                else "سعر غير صحيح. اختاري مرة أخرى.",
                lang
            )

        add_item_to_order_summary(s, picked_key, qty, price)

        prompt = _start_next_generic_from_queue(s, MENU, lang)
        session["state"] = s
        if prompt:
            return make_chat_response(prompt, lang)

        s["stage"] = "add_more"
        session["state"] = s
        return make_chat_response(
            "Added. Anything else?"
            if lang != "ar"
            else "تمت الإضافة. هل تريدين شيئاً آخر؟",
            lang
        )

    # -------------------------
    # snacks_sides text stage
    # -------------------------
    if s.get("stage") == "await_specific_side_text":
        user_pick = (msg_raw or "").strip().lower()
        picked_key = None  # safety

        # ✅ ESCAPE HATCH
        if (not from_button) and msg_raw and looks_like_multi_item_text(msg_raw):
            s["stage"] = None
            session["state"] = s
            return handle_multi_item_text(msg_raw, s, MENU, lang)

        if user_pick == "more":
            s["cat_page"] = int(s.get("cat_page") or 0) + 1
            body, chunk, _ = _format_category_page(MENU, "snacks_sides", lang, page=s["cat_page"])
            s["last_page_keys"] = chunk or []

            if not body:
                s["cat_page"] = 0
                body, chunk, _ = _format_category_page(MENU, "snacks_sides", lang, page=0)
                s["last_page_keys"] = chunk or []

            title = "Select a side/snack:" if lang != "ar" else "اختاري مقبلات/جانبي:"
            session["state"] = s
            return make_chat_response(f"{title}\n{body}", lang)

        # detect a SIDES item name inside a long sentence
        t = _norm_text(msg_raw or "")
        for name, key in (NAME_TO_KEY or {}).items():
            if name and (name in t):
                info = MENU.get(key) or {}
                if (info.get("category") or "").strip().lower() == "snacks_sides":
                    picked_key = key
                    break

        # fallback: page resolver (number or name from current page)
        if not picked_key:
            picked_key = _resolve_text_pick_to_menu_key(
                MENU,
                s.get("last_page_keys") or [],
                msg_raw,
                lang
            )

        # fallback: search whole category if not on current page
        if not picked_key:
            picked_key = _resolve_text_pick_to_menu_key_any_in_category(
                MENU, "snacks_sides", msg_raw
            )

        if not picked_key:
            title = "Select a side/snack:" if lang != "ar" else "اختاري مقبلات/جانبي:"
            body, chunk, _ = _format_category_page(
                MENU, "snacks_sides", lang, page=int(s.get("cat_page") or 0)
            )
            s["last_page_keys"] = chunk or []
            session["state"] = s
            return make_chat_response(
                f"Invalid selection. Type number/name or 'more'.\n\n{title}\n{body}"
                if lang != "ar"
                else f"اختيار غير صحيح. اكتبي الرقم/الاسم أو more.\n\n{title}\n{body}",
                lang
            )

        qty = int(s.get("last_qty") or 1)

        info = MENU.get(picked_key) or {}
        try:
            price = float(info.get("price") or 0)
        except Exception:
            price = 0

        if price <= 0:
            return make_chat_response(
                "Invalid item price. Please pick again."
                if lang != "ar"
                else "سعر غير صحيح. اختاري مرة أخرى.",
                lang
            )

        add_item_to_order_summary(s, picked_key, qty, price)

        prompt = _start_next_generic_from_queue(s, MENU, lang)
        session["state"] = s
        if prompt:
            return make_chat_response(prompt, lang)

        s["stage"] = "add_more"
        session["state"] = s
        return make_chat_response(
            "Added. Anything else?"
            if lang != "ar"
            else "تمت الإضافة. هل تريدين شيئاً آخر؟",
            lang
        )

    
     # ---------------------------------------------------------
    # Canonical message text (TEXT + BUTTON safe)
    # ---------------------------------------------------------
    msg_raw = (msg_raw or "").strip()

    # =========================================================
    # ✅ AWAIT QUANTITY (place right after msg_raw strip)
    # =========================================================
    if s.get("stage") == "await_quantity":
        q = extract_qty_from_text(msg_raw)

        if not q:
            session["state"] = s
            return make_chat_response(
                "Please tell me the quantity (e.g. 1, 2, 3)."
                if lang != "ar"
                else "براہِ کرم مقدار بتائیں (مثلاً 1، 2، 3).",
                lang
            )

        item = s.pop("pending_item", None)
        if not item:
            s["stage"] = "add_more"
            session["state"] = s
            return make_chat_response(
                "Please select an item again."
                if lang != "ar"
                else "براہِ کرم دوبارہ آئٹم منتخب کریں۔",
                lang
            )

        add_item_to_order(item, q)
        s["stage"] = "add_more"
        session["state"] = s
        return show_order_summary_and_add_more_buttons(lang)


    # =========================================================
    # ✅ GENERIC CATEGORY SELECTION HANDLER (Meals/Juices/Drinks)
    # =========================================================
    if s.get("stage") in ("await_specific_meal", "await_specific_juice", "await_specific_drink"):

        user_pick = (msg_raw or "").strip()

        kind = (s.get("last_kind") or "").strip().lower()

        keys_all   = s.get("last_options_keys_all") or []
        disp_all   = s.get("last_options_disp_all") or []
        short_keys = s.get("last_short_keys") or []

        resolved = _resolve_selection_to_menu_key(
            MENU, kind, user_pick, disp_all, keys_all
        )

        # number selection (1,2,3) from short list
        if isinstance(resolved, str) and resolved.startswith("__NUM__:"):
            try:
                idx = int(resolved.split(":")[1])
            except Exception:
                idx = 0

            resolved = short_keys[idx - 1] if (1 <= idx <= len(short_keys)) else None

        # invalid selection → re-show list
        if not resolved:
            qty_hint = int(s.get("last_qty") or 0)
            msg_list, _, _ = _render_pick_list(
                MENU, kind, (qty_hint if qty_hint > 0 else 1), lang
            )
            session["state"] = s
            return make_chat_response(
                ("This item is not available in this category.\n\n" + msg_list)
                if lang != "ar"
                else ("یہ آئٹم اس کیٹیگری میں دستیاب نہیں ہے۔\n\n" + msg_list),
                lang
            )

        # ✅ If qty was missing when user typed "meals/juice/drinks" -> ask quantity now
        if s.get("last_qty_missing"):
            s["pending_item"] = resolved
            s["stage"] = "await_qty"   # ✅ use ONE name everywhere
            session["state"] = s
            return make_chat_response(
                "How many would you like? (e.g. 1, 2, 3)"
                if lang != "ar"
                else "کتنی مقدار چاہیے؟ (مثال: 1، 2، 3)",
                lang
            )

        # ✅ qty exists -> add directly
        qty = int(s.get("last_qty") or 1)
        add_item_to_order(resolved, qty)
        s["stage"] = "add_more"
        session["state"] = s
        return show_order_summary_and_add_more_buttons(lang)


            
        # ==============================
        # ✅ QTY GUARD (PASTE HERE)
        # ==============================
        picked = (msg_raw or "").strip()
        qty = extract_qty_from_text(picked)

        if qty is None:
            s["pending_item"] = resolved
            s["stage"] = "await_quantity"
            return make_chat_response(
                "How many would you like?"
                if lang != "ar"
                else "کتنی مقدار چاہیے؟",
                lang
            )

        _add_line_item(s, MENU, resolved, qty)
        s["stage"] = "add_more"
        return show_order_summary_and_add_more_buttons(lang)


        _add_line_item(s, resolved, qty)

        next_msg = _start_next_generic(s, MENU, lang)
        if next_msg:
            session["state"] = s
            return make_chat_response(
                f"Added x{qty}\n\n{next_msg}", lang
            )

        # queue finished
        s["stage"] = "add_more"
        session["state"] = s
        return make_chat_response(
            "Items add ho gaye. Aur add karna hai ya confirm?",
            lang
        )

    
    
     # =========================================================
    # 🔒 INTENT PRECEDENCE GUARD (PRICE / TOTAL / CANCEL)
    # =========================================================
    msg_txt = (msg_raw or "").strip()

    # 1️⃣ CANCEL — highest priority
    if is_cancel_text(msg_txt):
        intent = "cancel"

    # 2️⃣ PRICE QUERY — READ ONLY
    elif is_price_query(msg_txt):
        item_q = extract_item_for_price_query(msg_txt)
        mi = find_menu_item(item_q)

        if not mi:
            return make_chat_response(
                "Please type the exact item name to check price."
                if lang != "ar"
                else "من فضلك اكتب اسم الصنف لمعرفة السعر.",
                lang
            )

        info = MENU.get(mi, {})
        price = info.get("price", 0)
        name = info.get("name_ar") if lang == "ar" else info.get("name_en")

        return make_chat_response(
            f"{name} price is {price} SAR."
            if lang != "ar"
            else f"سعر {name} هو {price} ريال.",
            lang
        )

    # 2️⃣.5️⃣ CHECKOUT / COMPLETE ORDER / PAYMENT
    # ✅ CRITICAL: Only trigger finish order if NOT already in payment selection stage
    elif s.get("stage") != "choose_payment" and s.get("order") and any(k in msg_txt.lower() for k in ["place order", "place the order", "complete", "finish", "checkout", "check out", "payment", "pay", "done", "proceed"]):
        summary, total = build_order_summary_and_total(s.get("order") or [], lang)
        s["total"] = total
        
        # ✅ CREATE ORDER IN DATABASE
        if not s.get("order_id"):
            order_id = create_order_in_db(customer_id, s, lang)
            s["order_id"] = order_id
            print(f"📝 Order created in DB: order_id={order_id}")
        
        s["stage"] = "choose_payment"
        session["state"] = s
        
        summary_text = (
            "✅ ملخص الطلب:<br>" + "<br>".join(summary) + f"<br><br><b>الإجمالي: {total:.2f} ريال</b><br><br>اختر طريقة الدفع:"
            if lang == "ar" else
            "✅ Order Summary:<br>" + "<br>".join(summary) + f"<br><br><b>Total: {total:.2f} SAR</b><br><br>Choose payment method:"
        )
        return make_chat_response(summary_text, lang)

    # 3️⃣ TOTAL BILL — READ ONLY
    elif is_total_bill_query(msg_txt):
        total = compute_order_total(s)
        msg = (
            f"Your current total is {total:.2f} SAR.\nType 'checkout' or 'pay' to proceed."
            if lang != "ar"
            else f"إجمالي طلبك الحالي هو {total:.2f} ريال.\nاكتب 'دفع' أو 'انهاء' للمتابعة."
        )
        return make_chat_response(msg, lang)

    # =========================================================
    # ❌ BLOCK ADDING ITEMS AFTER ORDER CONFIRMATION
    # (allow: payment keywords, cancel, total, price queries)
    # =========================================================
    # Check if message contains payment method keywords
    is_payment_keyword = (
        any(x in msg_l for x in ["cash", "cod", "online", "online payment", "pay online", "card", "visa", "master", "debit", "mada"])
        or any(x in msg for x in ["نقد", "نقدا", "مدى", "إلكتروني", "دفع", "كرت"])
    )
    
    if (
        not from_button
        and s.get("stage") in ("payment", "choose_payment")
        and not is_cancel_text(msg_raw)
        and not is_price_query(msg_raw)
        and not is_total_bill_query(msg_raw)
        and not is_payment_keyword  # ✅ Allow payment method keywords to pass through
    ):
        return make_chat_response(
            "Your order is already confirmed. Please proceed to payment or type cancel to modify it."
            if lang != "ar"
            else "تم تأكيد طلبك. من فضلك تابع الدفع أو اكتب (إلغاء) لتعديل الطلب.",
            lang
        )

    # quick menu
    if "menu" in msg_l or "send menu" in msg_l or "price list" in msg_l:
        intent = "menu"

    if polite_check(msg):
        return make_chat_response(
            "Please speak politely." if lang == "en" else "من فضلك تحدث بأدب.",
            lang
        )

    if intent == "menu":
        reply = "Here’s our menu! Please place your order." if lang == "en" else "هذه قائمتنا! من فضلك ضع طلبك."
        return make_chat_response(reply, lang, menu="/static/menu.PNG")


    # =========================================================
    # ✅ MULTI-ITEM TEXT (ADD NON-BURGER + HANDLE SPECIFIC ITEMS + GENERIC PICK FIRST)
    # =========================================================
 
    # ✅ CRITICAL FIX: Allow multi-item orders from 'branch' stage too!
    # When user clicks "Order via text", they see menu/categories, but stage might be 'branch'
    if (not from_button) and s.get("stage") in (None, "add_more", "branch") and (not is_cancel_text(msg_raw)):
        print(f"🔍 DEBUG [multi-item check]: stage={s.get('stage')}, from_button={from_button}, is_cancel={is_cancel_text(msg_raw)}")
        print(f"🔍 DEBUG [multi-item check]: msg_raw='{msg_raw}', looks_like_multi={looks_like_multi_item_text(msg_raw)}")
        if looks_like_multi_item_text(msg_raw):
            print(f"✅ DEBUG: Calling handle_multi_item_text for '{msg_raw}'")
            return handle_multi_item_text(msg_raw, s, MENU, lang)


            # # 1) detect GENERIC burger/sandwich (no specific name)
            # bs_generics = detect_generic_requests_ordered(msg_raw)

            # # 1b) detect GENERIC meals / juices / drinks
            # food_generics = detect_food_generic_requests_ordered(msg_raw)

            # # combine both
            # generics = (food_generics or []) + (bs_generics or [])

            # # ✅ normalize generics => always dicts
            # norm = []
            # for g in (generics or []):
            #     if isinstance(g, dict):
            #         norm.append(g)
            #     elif isinstance(g, str):
            #         norm.append({"kind": g, "qty": 1})
            # generics = norm

            # # ✅ FOOD GENERICS FIRST → TEXT LIST (no buttons)
            # food_only = [
            #     g for g in (generics or [])
            #     if g.get("kind") in ("meals", "juices", "drinks")
            # ]

            # if food_only:
            #     s["generic_queue"] = list(food_only)

            #     prompt = _start_next_generic_from_queue(s, MENU, lang)
            #     session["state"] = s

            #     if prompt:
            #         return make_chat_response(prompt, lang)



            # # 2) add NON-burger items only (drinks/sides/etc.)
            # added_lines, _ = add_non_generic_items_to_order(s, msg_raw, lang)

            # # 3) ALSO extract SPECIFIC items via LLM
            # extracted = extract_items_with_llm(msg_raw, lang) or []

            # # prevent double add for non-generic already added via regex
            # already_added = set()
            # for line in (s.get("order") or []):
            #     already_added.add(((line.get("item") or "").strip().lower()))

            # extracted_filtered = []
            # for it in extracted:
            #     nm = (it.get("name") or "").strip()
            #     if not nm:
            #         continue
            #     if nm.lower() in already_added:
            #         continue
            #     extracted_filtered.append(it)

            # # ✅ 3.5) Detect invalid items returned by LLM (not in MENU)
            # invalid_names = []
            # valid_filtered = []
            # for it in extracted_filtered:
            #     nm = (it.get("name") or "").strip()
            #     if not nm:
            #         continue
            #     if not find_menu_item(nm):
            #         invalid_names.append(nm)
            #         continue
            #     valid_filtered.append(it)
            # extracted_filtered = valid_filtered

            # # ✅ IMPORTANT: If generic burger/sandwich exists in the message,
            # # do NOT let LLM add/queue burgers or sandwiches (avoid double spice prompts)
            # if generics and extracted_filtered:
            #     keep = []
            #     for it in extracted_filtered:
            #         nm = (it.get("name") or "").strip().lower()
            #         _price, cat = get_price_and_category(nm)
            #         if cat not in ("burgers_meals", "sandwiches"):
            #             keep.append(it)
            #     extracted_filtered = keep

            # # 3.6) Add valid extracted items to state (and maybe spice_queue)
            # added2, _queued = add_extracted_items_to_state(s, extracted_filtered, lang)
            # if added2:
            #     added_lines.extend(added2)

            # # ✅ STOP if invalid items exist (IMPORTANT)
            # if invalid_names:
            #     bad = ", ".join(invalid_names[:3])
            #     msg = (
            #         f"I couldn't find these items in the menu: {bad}. "
            #         f"Please type the correct name or write 'menu' to see the menu."
            #         if lang == "en" else
            #         f"لم أجد هذه الأصناف في القائمة: {bad}. "
            #         f"اكتب الاسم الصحيح أو اكتب 'menu' لعرض القائمة."
            #     )
            #     session["state"] = s
            #     return make_chat_response(msg, lang)

            # # ✅ NOTHING MATCHED guard (avoid showing summary/bill)
            # if (not added_lines) and (not extracted_filtered) and (not generics):
            #     msg = (
            #         "I couldn't find any of those items in the menu. Please type 'menu' to see the menu."
            #         if lang == "en" else
            #         "لم أجد هذه الأصناف في القائمة. اكتب 'menu' لعرض القائمة."
            #     )
            #     session["state"] = s
            #     return make_chat_response(msg, lang)

            #             # prefix (show what was added before asking next question)
            # prefix = (
            #     ("تمت إضافة: " + "، ".join(added_lines) + "<br><br>")
            #     if added_lines and lang == "ar"
            #     else ("Added: " + ", ".join(added_lines) + "<br><br>" if added_lines else "")
            # )

            # # # =========================================================
            # # # ✅ GENERIC QUEUE: meals / juices / drinks (one-by-one)
            # # # ✅ NOTE: generics already computed above (do NOT recompute)
            # # # =========================================================
            # # food_generics = [
            # #     g for g in (generics or [])
            # #     if (g.get("kind") in ("meals", "juices", "drinks"))
            # # ]

            # # if food_generics:
            # #     s["generic_queue"] = list(food_generics)

            # #     pick_msg = _start_next_generic(s, MENU, lang)
            # #     if pick_msg:
            # #         session["state"] = s
            # #         return make_chat_response(prefix + pick_msg, lang)

            # # =========================================================
            # # ✅ GENERIC burger/sandwich (same old flow) — ONLY for these kinds
            # # =========================================================
            # bs_generics = [
            #     g for g in (generics or [])
            #     if (g.get("kind") in ("burger", "sandwich"))
            # ]


            # # 4) If generic exists → ASK WHICH ONE FIRST (same old flow)
            # # ✅ BURGER / SANDWICH GENERICS ONLY
            # if bs_generics:

            #     s.setdefault("generic_queue", [])          # ✅ FIX
            #     s["generic_queue"].extend(generics)
            #     nxt = s["generic_queue"].pop(0)

            #     s["last_qty"] = int(nxt.get("qty") or 1)
            #     s["last_item"] = None

            #     if nxt.get("kind") == "burger":
            #         s["stage"] = "await_specific_burger"
            #         s["burger_page"] = 0
            #         ask = (
            #             f"لديك {s['last_qty']} برجر. اختر نوع البرجر."
            #             if lang == "ar"
            #             else f"You ordered {s['last_qty']} burger(s). Please choose which burger."
            #         )
            #     else:
            #         s["stage"] = "await_specific_sandwich"
            #         s["sand_page"] = 0
            #         ask = (
            #             f"لديك {s['last_qty']} ساندويتش. اختر نوع الساندويتش."
            #             if lang == "ar"
            #             else f"You ordered {s['last_qty']} sandwich(es). Please choose which sandwich."
            #         )

            #     session["state"] = s
            #     return make_chat_response(prefix + ask, lang)

            # # 5) If we have burgers needing spice (from LLM extraction) → ask spice NOW
            # if s.get("spice_queue"):
            #     nxt = s["spice_queue"].pop(0)
            #     s["last_item"] = nxt["item"]
            #     s["last_qty"] = int(nxt.get("qty") or 1)
            #     s["stage"] = "await_spice"
            #     session["state"] = s

            #     ask_spice = (
            #         f"بالنسبة لـ {s['last_qty']} {s['last_item']}، هل تفضلها حارة أم بدون حار؟"
            #         if lang == "ar"
            #         else f"For your {s['last_qty']} {s['last_item'].title()}, would you like them spicy or non-spicy?"
            #     )
            #     return make_chat_response(prefix + ask_spice, lang)

            # # 6) Otherwise summary
            # summary, total = build_order_summary_and_total(s.get("order") or [], lang)
            # s["total"] = total
            # s["stage"] = "add_more"
            # session["state"] = s

            # reply = (
            #     "ملخص الطلب:<br>" + "<br>".join(summary) + "<br><br>هل ترغب في إضافة شيء آخر؟"
            #     if lang == "ar"
            #     else "Order summary:<br>" + "<br>".join(summary) + "<br><br>Would you like to add anything else?"
            # )
            # return make_chat_response(reply, lang)

    # ✅ LARGE ORDER CONFIRMATION - Handle user response to large quantity warning
    if s.get("stage") == "confirm_large_order":
        pending = s.get("pending_large_order")
        if not pending:
            s["stage"] = None
            session["state"] = s
            return make_chat_response("خطأ: لا يوجد طلب معلق" if lang == "ar" else "Error: No pending order", lang)
        
        msg_clean = msg_raw.lower().strip()
        
        # User confirmed - add the large order
        if any(confirm in msg_clean for confirm in ["yes", "y", "نعم", "تأكيد", "موافق", "ok"]):
            s.setdefault("order", [])
            s["order"].append(pending)
            
            info = MENU.get(pending["item"], {})
            display_name = info.get("name_ar") if lang == "ar" else (info.get("name_en") or pending["item"]).title()
            
            # ✅ PROCESS REMAINING QUEUED ITEMS
            pending_queue = s.pop("pending_items_queue", None)
            s.pop("pending_large_order", None)
            
            if pending_queue:
                # Continue processing remaining items from the original order
                # Re-call handle_multi_item_text with remaining items
                # Build a synthetic message to represent remaining items
                remaining_specific = pending_queue.get("specific", [])
                remaining_generics = pending_queue.get("generics", [])
                
                # Build queue for generics
                for gen in remaining_generics:
                    s.setdefault("generic_queue", [])
                    s["generic_queue"].append(gen)
                
                # Process remaining specific items
                for spec in remaining_specific:
                    name = spec.get("name", "").strip()
                    qty = spec.get("qty", 1)
                    spicy_info = spec.get("spicy", "any")
                    category = spec.get("category", "")
                    
                    # ✅ Use functions directly (already defined in same file)
                    resolved, _ = resolve_menu_item(name)
                    if not resolved:
                        continue
                    
                    price, cat = get_price_and_category(resolved)
                    if price is None or price <= 0:
                        continue
                    
                    # ✅ Handle burgers WITHOUT spicy info - need to ask
                    if cat == "burgers_meals" and spicy_info == "any":
                        # Queue this burger for spice selection
                        s.setdefault("spice_queue", [])
                        s["spice_queue"].append({"item": resolved, "qty": qty})
                        continue
                    
                    # Check if this is also a large order
                    if qty >= 100:
                        # Set up next large order confirmation
                        s["stage"] = "confirm_large_order"
                        is_spicy = 1 if spicy_info == "spicy" else 0
                        is_nonspicy = 1 if spicy_info in ("non-spicy", "nonspicy") else 0
                        s["pending_large_order"] = {
                            "item": resolved,
                            "qty": qty,
                            "spicy": is_spicy,
                            "nonspicy": is_nonspicy,
                            "price": float(price),
                            "subtotal": qty * float(price),
                            "category": cat
                        }
                        
                        # Save remaining items AFTER this one
                        idx = remaining_specific.index(spec)
                        still_remaining = remaining_specific[idx + 1:]
                        s["pending_items_queue"] = {
                            "specific": still_remaining,
                            "generics": remaining_generics,
                            "added_lines": []
                        }
                        
                        session["state"] = s
                        
                        info2 = MENU.get(resolved, {})
                        display_name2 = info2.get("name_ar") if lang == "ar" else (info2.get("name_en") or resolved).title()
                        spicy_text = "حار" if is_spicy else "غير حار" if is_nonspicy else ""
                        spicy_text_en = "Spicy" if is_spicy else "Non-Spicy" if is_nonspicy else ""
                        spicy_suffix = f" ({spicy_text})" if spicy_text else ""
                        spicy_suffix_en = f" ({spicy_text_en})" if spicy_text_en else ""
                        
                        confirm_msg = (
                            f"⚠️ تريد طلب *{qty} {display_name2}*{spicy_suffix}\n\n"
                            f"هذه كمية كبيرة جداً! هل أنت متأكد؟\n\n"
                            f"💰 الإجمالي: {qty * float(price):.2f} SAR\n\n"
                            f"اكتب 'نعم' للتأكيد أو 'لا' للإلغاء"
                            if lang == "ar" else
                            f"⚠️ You want to order *{qty} {display_name2}*{spicy_suffix_en}\n\n"
                            f"This is a very large quantity! Are you sure?\n\n"
                            f"💰 Total: {qty * float(price):.2f} SAR\n\n"
                            f"Type 'yes' to confirm or 'no' to cancel"
                        )
                        
                        return make_chat_response(confirm_msg, lang)
                    else:
                        # Normal quantity - add directly with proper spicy info
                        is_spicy = 1 if spicy_info == "spicy" else 0
                        is_nonspicy = 1 if spicy_info in ("non-spicy", "nonspicy") else 0
                        s["order"].append({
                            "item": resolved,
                            "qty": qty,
                            "spicy": is_spicy,
                            "nonspicy": is_nonspicy,
                            "price": float(price),
                            "subtotal": qty * float(price)
                        })
                
                # ✅ After all specific items processed, handle spice queue or generics
                # Check if there are burgers waiting for spice selection
                if s.get("spice_queue"):
                    nxt = s["spice_queue"].pop(0)
                    s["last_item"] = nxt["item"]
                    s["last_qty"] = nxt["qty"]
                    s["stage"] = "await_spice"
                    session["state"] = s
                    
                    ask_msg = (
                        f"بالنسبة لـ {nxt['qty']} {nxt['item']}، هل تفضلها حارة أم بدون حار؟"
                        if lang == "ar"
                        else f"For your {nxt['qty']} {nxt['item'].title()}, spicy or non-spicy?"
                    )
                    return make_chat_response(ask_msg, lang)
                
                # ✅ No spice queue - check for generic queue
                prompt = _start_next_generic_from_queue(s, MENU, lang)
                if prompt:
                    session["state"] = s
                    # Don't show order summary yet - user needs to select items
                    return make_chat_response(prompt, lang)
            
            summary, total = build_order_summary_and_total(s["order"], lang)
            s["total"] = total
            s["stage"] = "add_more"
            session["state"] = s
            
            reply = (
                f"✅ تمت إضافة {pending['qty']} {display_name}<br><br>"
                "طلبك الحالي:<br>" + "<br>".join(summary) + "<br><br>هل ترغب في إضافة شيء آخر؟"
                if lang == "ar" else
                f"✅ Added {pending['qty']} {display_name}<br><br>"
                "Your order:<br>" + "<br>".join(summary) + "<br><br>Would you like to add anything else?"
            )
            return make_chat_response(reply, lang)
        
        # User cancelled - remove pending order
        elif any(cancel in msg_clean for cancel in ["no", "n", "لا", "cancel", "إلغاء"]):
            s["stage"] = "add_more"
            s.pop("pending_large_order", None)
            session["state"] = s
            
            reply = (
                "❌ تم إلغاء الطلب الكبير.<br>هل ترغب في طلب شيء آخر؟"
                if lang == "ar" else
                "❌ Large order cancelled.<br>Would you like to order something else?"
            )
            return make_chat_response(reply, lang)
        
        # Invalid response - ask again
        else:
            reply = (
                "من فضلك اكتب 'نعم' للتأكيد أو 'لا' للإلغاء"
                if lang == "ar" else
                "Please type 'yes' to confirm or 'no' to cancel"
            )
            return make_chat_response(reply, lang)
    
            
     # ✅ Cancel screen: allow BOTH button + text selection
    # treat user types "coffee" or "1 coffee" or "1" while cancel UI open,
    # treat as CANCEL, not ADD.
    if (not from_button) and s.get("stage") in ("cancel_choice", "cancel_item_select"):

        # ✅ EXIT cancel flow if user wants to proceed to payment
        low = (msg_raw or "").lower()
        if any(k in low for k in ["pay", "payment", "proceed", "checkout", "continue", "yes"]):
            s["stage"] = "choose_payment"
            session["state"] = s
            return make_chat_response(
                ("اختر طريقة الدفع: كاش أو أونلاين" if lang == "ar"
                 else "Choose payment method: Cash or Online."),
                lang
            )

        order = s.get("order") or []
        txt = (msg_raw or "").strip()

        # 1) number-only => treat as index from list (1-based)
        if re.fullmatch(r"\d+", _normalize_digits(txt)) and order:
            idx = int(_normalize_digits(txt)) - 1
            if 0 <= idx < len(order):
                item = order[idx]
                cancel_req = {
                    "item": item["item"],
                    "qty": 1,
                    "spicy": item.get("spicy"),
                    "nonspicy": item.get("nonspicy"),
                }
                ok, reply = apply_cancel_on_order(s, cancel_req, lang)
                session["state"] = s
                return make_chat_response(reply, lang)

        # ... continue your other cancel parsing cases here ...

        # 2) item name with optional qty => force cancel parsing
        cancel_req = parse_cancel_request("cancel " + txt, lang)
        if cancel_req and cancel_req.get("item"):
            ok, reply = apply_cancel_on_order(s, cancel_req, lang)
            session["state"] = s
            return make_chat_response(reply, lang)

        help_msg = (
            "Type item number (e.g., 1) or item name (e.g., coffee) to cancel."
            if lang != "ar"
            else "اكتب رقم الصنف (مثال: 1) أو اسم الصنف (مثال: قهوة) للإلغاء."
        )
        return make_chat_response(help_msg, lang)


    # CANCEL by text
    if s.get("order") and is_cancel_text(msg_raw) and s.get("stage") in ("payment", "choose_payment", "add_more", "cancel_choice", "cancel_item_select"):
        # ✅ Check if user wants to cancel ENTIRE order
        entire_order_keywords = [
            "cancel my entire order", "cancel entire order", "cancel my order", 
            "cancel the entire order", "cancel the order", "cancel all",
            "إلغاء الطلب بالكامل", "إلغاء طلبي", "إلغاء الطلب", "الغي كل شي"
        ]
        msg_lower = msg_raw.lower()
        is_entire_cancel = any(kw in msg_lower for kw in entire_order_keywords)
        
        if is_entire_cancel:
            # Cancel entire order immediately
            cancel_order_in_db(s.get("order_id"))
            session["state"] = {"stage": None, "order": [], "total": 0, "last_item": None, "last_qty": 0, "last_confirmed_item": None, "pending_item": None, "spice_queue": [], "generic_queue": []}
            reply = (
                "✅ تم إلغاء طلبك بالكامل.\n\n"
                "إذا كنت ترغب في تقديم طلب جديد أو عرض قائمتنا، فلا تتردد في المتابعة. 🍔☕"
                if lang == "ar" else
                "✅ Your entire order has been canceled.\n\n"
                "If you'd like to place a new order or view our menu, please feel free to continue. 🍔☕"
            )
            return make_chat_response(reply, lang)
        
        # Otherwise, process item-specific cancellation
        parts = split_cancel_parts(msg_raw)
        cancel_msgs = []
        for part in parts:
            cancel_req = parse_cancel_request(part, lang)
            ok, one_msg = apply_cancel_on_order(s, cancel_req or {}, lang)
            cancel_msgs.append(one_msg)

        session["state"] = s
        if not s.get("order"):
            session["state"] = {"stage": None, "order": [], "total": 0, "last_item": None, "last_qty": 0, "last_confirmed_item": None, "pending_item": None, "spice_queue": [], "generic_queue": []}
            return make_chat_response("<br><br>".join(cancel_msgs), lang)

        s["stage"] = "choose_payment"
        session["state"] = s
        return make_chat_response("<br><br>".join(cancel_msgs), lang)

    # ITEM BUTTON FLOW (item_<name>) -> ask qty
    if from_button and msg_l.startswith("item_"):
        chosen = msg_l.replace("item_", "").strip()
        mapped = find_menu_item(chosen) or chosen
        s["pending_item"] = mapped
        s["stage"] = "await_qty"
        session["state"] = s
        ask = (f"كم الكمية المطلوبة لـ {mapped}؟ (مثال: 12)" if lang == "ar" else f"How many {mapped.title()} would you like? (e.g., 12)")
        return make_chat_response(ask, lang)

    if s.get("stage") == "await_qty" and s.get("pending_item"):
        pending = s.get("pending_item")
        qty = detect_qty(msg_raw)
        qty = qty if qty > 0 else 1

        price, category = get_price_and_category(pending)
        if price <= 0:
            mapped = find_menu_item(msg_raw) or find_menu_item(pending) or pending
            price, category = get_price_and_category(mapped)
            pending = mapped

        s["last_item"] = pending
        s["last_qty"] = qty
        s["pending_item"] = None

        # ✅ CRITICAL FIX: Actually ADD the item to the order!
        if category == "burgers_meals":
            # For burgers, queue for spice question - will be added after spice selection
            s["stage"] = "await_spice"
            session["state"] = s
            reply = (f"بالنسبة لـ {qty} {pending}، هل تفضلها حارة أم بدون حار؟" if lang == "ar" else f"For your {qty} {pending.title()}, would you like them spicy or non-spicy?")
            return make_chat_response(reply, lang)
        else:
            # Non-burger items: add directly to order
            s["order"].append({
                "item": pending,
                "qty": qty,
                "spicy": 0,
                "nonspicy": 0,
                "price": price,
                "subtotal": qty * price
            })

        # ✅ PROCEED TO NEXT IN GENERIC QUEUE
        s["pending_item"] = None
        s["last_item"] = None
        s["last_qty"] = 0
        prompt = _start_next_generic_from_queue(s, MENU, lang)
        if prompt:
            session["state"] = s
            return make_chat_response(prompt, lang)


        s["stage"] = "add_more"
        summary, total = build_order_summary_and_total(s["order"], lang)
        s["total"] = total
        session["state"] = s

        reply = (
            "✅ ملخص الطلب:<br>" + "<br>".join(summary) + f"<br><br><b>الإجمالي: {total:.2f} {CURRENCY_AR}</b><br><br>هل ترغب في إضافة شيء آخر أم تريد إتمام الطلب؟"
            if lang == "ar"
            else "✅ Order Summary:<br>" + "<br>".join(summary) + f"<br><br><b>Total: {total:.2f} {CURRENCY}</b><br><br>Would you like to add more items or place the order?"
        )
        return make_chat_response(reply, lang)

    # pick burger button
    if msg_l.startswith("pick_burger_"):
        chosen = msg_l.replace("pick_burger_", "").strip()
        qty = int(s.get("last_qty", 1) or 1)
        print(f"🔍 DEBUG [pick_burger button]: chosen={chosen}, qty from last_qty={qty}, s.get('last_qty')={s.get('last_qty')}")
        price, category = get_price_and_category(chosen)
        if category != "burgers_meals":
            reply = "من فضلك اختر برجر صحيح من القائمة." if lang == "ar" else "Please choose a valid burger from the menu."
            return make_chat_response(reply, lang)
        s["last_item"] = chosen
        s["last_qty"] = qty
        s["stage"] = "await_spice"
        session["state"] = s
        reply = (f"بالنسبة لـ {qty} {chosen}، هل تفضلها حارة أم بدون حار؟" if lang == "ar" else f"For your {qty} {chosen.title()}, would you like them spicy or non-spicy?")
        return make_chat_response(reply, lang)

    # pick sandwich button
    if msg_l.startswith("pick_sandwich_"):
        chosen = msg_l.replace("pick_sandwich_", "").strip()
        qty = int(s.get("last_qty", 1) or 1)
        price, category = get_price_and_category(chosen)
        if category != "sandwiches":
            reply = "من فضلك اختر ساندوتش صحيح من القائمة." if lang == "ar" else "Please choose a valid sandwich from the menu."
            return make_chat_response(reply, lang)

        s["order"].append({"item": chosen, "qty": qty, "spicy": 0, "nonspicy": 0, "price": price, "subtotal": qty * price})
        s["last_confirmed_item"] = {"item": chosen, "qty": qty, "spicy": 0, "nonspicy": 0, "price": price}
        s["last_item"] = None
        s["last_qty"] = 0

        # ✅ PROCEED TO NEXT IN GENERIC QUEUE
        prompt = _start_next_generic_from_queue(s, MENU, lang)
        if prompt:
            session["state"] = s
            return make_chat_response(prompt, lang)

        s["stage"] = "add_more"
        summary, total = build_order_summary_and_total(s["order"], lang)
        s["total"] = total
        session["state"] = s

        reply = (
            f"{chosen} ×{qty} تمت إضافته إلى طلبك.<br>هل ترغب في إضافة شيء آخر؟"
            if lang == "ar"
            else f"{chosen.title()} ×{qty} added to your order.<br>Would you like to add anything else?"
        )
        return make_chat_response(reply, lang)

    # Spice follow-up
    if s.get("stage") == "await_spice" and s.get("last_item"):
        last_item = s["last_item"]
        last_qty = int(s.get("last_qty", 1) or 1)
        print(f"🔍 DEBUG [spice response]: User said '{msg}', last_item={last_item}, last_qty={last_qty}, s.get('last_qty')={s.get('last_qty')}")
        
        # ✅ CRITICAL FIX: Check if user is trying to order a NEW item instead of answering spice question
        # If the message contains quantity + menu item (e.g., "2 pizza", "1 burger"), treat it as new order
        msg_lower = msg.lower().strip()
        
        # ✅ FIRST: Check if it's a non-menu item request (like pizza)
        if is_non_menu_item_request(msg):
            # Complete current burger with default non-spicy
            price, _ = get_price_and_category(last_item)
            s["order"].append({"item": last_item, "qty": last_qty, "spicy": 0, "nonspicy": 1, "price": price, "subtotal": last_qty * price})
            s["last_confirmed_item"] = {"item": last_item, "qty": last_qty, "spicy": 0, "nonspicy": 1, "price": price}
            s["last_item"] = None
            s["last_qty"] = 0
            s["stage"] = None
            session["state"] = s
            
            # Return rejection message
            rejection_msg = (
                "عذراً، لا يمكنني مساعدتك في ذلك. يمكنك السؤال بحرية عن قائمة JOANA، وسأكون سعيداً بإرشادك.\n\n"
                "📋 يرجى الاختيار من قائمتنا:"
                if lang == "ar" else
                "Sorry, I can't assist with that. You can freely ask about Joana's menu, and I'll be happy to guide you.\n\n"
                "📋 Please choose from our menu:"
            )
            return make_chat_response(rejection_msg, lang)
        
        # ✅ Check if this looks like answering spice question vs new order
        # Common spice-related words that should NOT trigger new order detection
        spice_keywords = ["spicy", "non spicy", "nonspicy", "non-spicy", "hot", "mild", 
                         "حار", "حارة", "بدون حار", "غير حار", "عادي"]
        is_spice_answer = any(keyword in msg_lower for keyword in spice_keywords)
        
        # Check if this looks like a new order (has quantity + item name)
        is_new_order = False
        if not is_spice_answer:  # ✅ Only check for new order if NOT answering spice question
            if looks_like_multi_item_text(msg):
                is_new_order = True
            else:
                # Also check for simple quantity + item patterns like "2 pizza", "1 burger"
                qty_match = re.search(r'(\d+)\s*([a-z\u0600-\u06FF]+)', msg_lower)
                if qty_match:
                    qty_part = qty_match.group(1)
                    item_part = qty_match.group(2)
                    # Check if item_part matches any menu item
                    resolved, _ = resolve_menu_item(item_part)
                    if resolved:
                        is_new_order = True
        
        # If it's a new order request, don't treat it as spice response - let it fall through
        if is_new_order:
            # First, complete the current spice question with default (non-spicy)
            price, _ = get_price_and_category(last_item)
            s["order"].append({"item": last_item, "qty": last_qty, "spicy": 0, "nonspicy": 1, "price": price, "subtotal": last_qty * price})
            s["last_confirmed_item"] = {"item": last_item, "qty": last_qty, "spicy": 0, "nonspicy": 1, "price": price}
            s["last_item"] = None
            s["last_qty"] = 0
            s["stage"] = None  # Reset stage so it can be processed as new order
            session["state"] = s
            # Don't return here - let the message be processed as a new order below
        else:
            # Normal spice response processing
            price, _ = get_price_and_category(last_item)

            split = parse_spice_split(msg, last_qty)
            if split:
                spicy_q, non_q = split
            else:
                spicy_flag, nonspicy_flag = detect_spicy_nonspicy(msg)
                if spicy_flag:
                    spicy_q, non_q = last_qty, 0
                elif nonspicy_flag:
                    spicy_q, non_q = 0, last_qty
                else:
                    spicy_q, non_q = 0, last_qty

            if spicy_q > 0:
                s["order"].append({"item": last_item, "qty": spicy_q, "spicy": 1, "nonspicy": 0, "price": price, "subtotal": spicy_q * price})
            if non_q > 0:
                s["order"].append({"item": last_item, "qty": non_q, "spicy": 0, "nonspicy": 1, "price": price, "subtotal": non_q * price})

            s["last_confirmed_item"] = {"item": last_item, "qty": last_qty, "spicy": 1 if spicy_q > 0 else 0, "nonspicy": 1 if non_q > 0 else 0, "price": price}

            s["last_item"] = None
            s["last_qty"] = 0

            summary, total = build_order_summary_and_total(s["order"], lang)
            s["total"] = total

            # ✅ if more burgers queued for spice, ask next immediately
            if s.get("spice_queue"):
                nxt = s["spice_queue"].pop(0)
                s["last_item"] = nxt["item"]
                s["last_qty"] = nxt["qty"]
                s["stage"] = "await_spice"
                session["state"] = s

                ask_next = (
                    f"تمت إضافة الصنف.<br><br>بالنسبة لـ {nxt['qty']} {nxt['item']}، هل تفضلها حارة أم بدون حار؟"
                    if lang == "ar"
                    else f"Added.<br><br>For your {nxt['qty']} {nxt['item'].title()}, spicy or non-spicy?"
                )
                return make_chat_response(ask_next, lang)

            # ✅ PROCEED TO NEXT IN GENERIC QUEUE
            prompt = _start_next_generic_from_queue(s, MENU, lang)
            if prompt:
                session["state"] = s
                return make_chat_response(prompt, lang)

            s["stage"] = "add_more"
            session["state"] = s

            reply = (
                "تمت إضافة الصنف. ملخص الطلب:<br>" + "<br>".join(summary) + "<br><br>هل ترغب في إضافة شيء آخر؟"
                if lang == "ar"
                else "Added. Updated order:<br>" + "<br>".join(summary) + "<br><br>Would you like to add anything else?"
            )
            return make_chat_response(reply, lang)

    # =====================================================
    # Generic guard (coffee + sandwich etc.)
    # =====================================================
    has_other_menu_item = has_non_generic_menu_item(msg)
    has_generic_burg = msg_has_generic_burger_word(msg) and (not msg_has_specific_burger(msg))
    has_generic_sand = msg_has_generic_sandwich_word(msg) and (not msg_has_specific_sandwich(msg))

    if (has_generic_burg or has_generic_sand) and has_other_menu_item:
        added_lines, added_any = add_non_generic_items_to_order(s, msg, lang)
        session["state"] = s

        prefix = ""
        if added_any:
            prefix = (
                ("تمت إضافة: " + "، ".join(added_lines) + "<br><br>")
                if lang == "ar"
                else ("Added: " + ", ".join(added_lines) + "<br><br>")
            )

        if has_generic_burg:
            qty_guess = extract_qty_for_generic(msg, "burger")
            s["stage"] = "await_specific_burger"
            s["last_qty"] = qty_guess
            s["last_item"] = None
            s["burger_page"] = 0
            session["state"] = s

            reply = prefix + (
                f"لديك {qty_guess} برجر. اختر نوع البرجر من الأزرار."
                if lang == "ar"
                else f"You ordered {qty_guess} burger(s). Please choose which burger from the buttons."
            )
            return make_chat_response(reply, lang)

        if has_generic_sand:
            qty_guess = extract_qty_for_generic(msg, "sandwich")
            s["stage"] = "await_specific_sandwich"
            s["last_qty"] = qty_guess
            s["last_item"] = None
            s["sand_page"] = 0
            session["state"] = s

            reply = prefix + (
                f"لديك {qty_guess} ساندويتش. اختر نوع الساندويتش من الأزرار."
                if lang == "ar"
                else f"You ordered {qty_guess} sandwich(es). Please choose which sandwich from the buttons."
            )
            return make_chat_response(reply, lang)

    if msg_has_generic_burger_word(msg) and not msg_has_specific_burger(msg):
        qty_guess = extract_qty_for_generic(msg, "burger")
        s["stage"] = "await_specific_burger"
        s["last_qty"] = qty_guess
        s["last_item"] = None
        s["burger_page"] = 0
        session["state"] = s

        reply = (
            f"لديك {qty_guess} برجر. اختر نوع البرجر من الأزرار."
            if lang == "ar"
            else f"You ordered {qty_guess} burger(s). Please choose which burger from the buttons."
        )
        return make_chat_response(reply, lang)

    if msg_has_generic_sandwich_word(msg) and not msg_has_specific_sandwich(msg):
        qty_guess = extract_qty_for_generic(msg, "sandwich")
        s["stage"] = "await_specific_sandwich"
        s["last_qty"] = qty_guess
        s["last_item"] = None
        s["sand_page"] = 0
        session["state"] = s

        reply = (
            f"لديك {qty_guess} ساندويتش. اختر نوع الساندويتش من الأزرار."
            if lang == "ar"
            else f"You ordered {qty_guess} sandwich(es). Please choose which sandwich from the buttons."
        )
        return make_chat_response(reply, lang)

    # \ud83d\udca1 INTELLIGENT TYPO CORRECTION - Fix common mistakes before processing\n    msg = fix_common_typos(msg)
    msg_l = msg.lower().strip()
    
    # Single item fallback
    found = find_menu_item(msg)
    if found:
        qty = detect_qty(msg) or 1
        price, category = get_price_and_category(found)
        spicy_flag, nonspicy_flag = detect_spicy_nonspicy(msg)

        if category == "burgers_meals" and not (spicy_flag or nonspicy_flag):
            s["last_item"] = found
            s["last_qty"] = qty
            s["stage"] = "await_spice"
            session["state"] = s

            reply = (
                f"هل ترغب أن يكون {found} حارًا أم بدون حار؟"
                if lang == "ar"
                else f"Would you like your {found.title()} spicy or non-spicy?"
            )
            return make_chat_response(reply, lang)

        spicy = 1 if (category == "burgers_meals" and spicy_flag) else 0
        nonspicy = 1 if (category == "burgers_meals" and (nonspicy_flag or not spicy_flag)) else 0

        s["order"].append(
            {
                "item": found,
                "qty": qty,
                "spicy": spicy,
                "nonspicy": nonspicy,
                "price": price,
                "subtotal": qty * price,
            }
        )

        summary, total = build_order_summary_and_total(s["order"], lang)
        s["total"] = total
        s["stage"] = "add_more"
        session["state"] = s

        reply = (
            "تمت إضافة الصنف إلى طلبك:<br>" + "<br>".join(summary) + "<br><br>هل ترغب في إضافة شيء آخر؟"
            if lang == "ar"
            else "Added to your order:<br>" + "<br>".join(summary) + "<br><br>Would you like to add anything else?"
        )
        return make_chat_response(reply, lang)

    # DONE -> payment
    done_keywords_en = ["no", "done", "that's all", "that all", "finish", "finish order"]
    done_keywords_ar = ["خلص", "انتهى", "كفاية", "إنهاء الطلب", "انهاء الطلب"]

    if any(x in msg_l for x in done_keywords_en) or any(x in msg for x in done_keywords_ar):
        if s.get("order"):
            summary, total = build_order_summary_and_total(s["order"], lang)
            s["total"] = total

            order_id = create_order_in_db(customer_id, s, lang)
            s["order_id"] = order_id
            s["stage"] = "payment"
            session["state"] = s

            reply = (
                "تم تأكيد طلبك!<br>" + "<br>".join(summary) + f"<br><br><b>الإجمالي: {total:.2f} {CURRENCY_AR}</b><br>هل ترغب في المتابعة إلى الدفع؟"
                if lang == "ar"
                else "Your order is confirmed!<br>" + "<br>".join(summary) + f"<br><br><b>Total: {total:.2f} {CURRENCY}</b><br>Would you like to proceed with payment?"
            )
            return make_chat_response(reply, lang)

    # payment -> choose_payment
    if s.get("stage") == "payment" and (
        any(x in msg_l for x in ["yes", "sure", "ok", "okay", "proceed", "go ahead"])
        or any(x in msg for x in ["تمام", "نعم", "أكيد", "المتابعة", "تابع", "ادفع", "إلى الدفع"])
    ):
        # ✅ SAFETY: Ensure order exists in database before payment
        if not s.get("order_id"):
            order_id = create_order_in_db(customer_id, s, lang)
            s["order_id"] = order_id
            print(f"⚠️ Order created during payment transition: order_id={order_id}")
        
        s["stage"] = "choose_payment"
        session["state"] = s
        reply = (
            "كيف ترغب في الدفع؟<br><b> نقدي </b> أو <b> الدفع عبر الإنترنت</b>؟"
            if lang == "ar"
            else "How would you like to pay?<br><b>Cash</b> or <b>Online Payment</b>?"
        )
        return make_chat_response(reply, lang)

    # choose payment method
    if s.get("stage") == "choose_payment":
        if any(x in msg_l for x in ["cash", "cod"]) or any(x in msg for x in ["نقد", "نقدا"]):
            order_id = s.get("order_id")
            update_order_payment(order_id, method="cash", status="unpaid")
            schedule_feedback_after_payment(order_id)

            # ✅ BUILD RECEIPT
            summary, total = build_order_summary_and_total(s.get("order") or [], lang)
            receipt = (
                "✅ <b>إيصال الطلب</b><br><br>"
                "━━━━━━━━━━━━━━━━━━━━━━<br>"
                "<b>📋 الطلب:</b><br>" + "<br>".join(summary) + "<br><br>"
                "━━━━━━━━━━━━━━━━━━━━━━<br>"
                f"<b>💰 الإجمالي:</b> {total:.2f} {CURRENCY_AR}<br>"
                f"<b>💵 طريقة الدفع:</b> نقدي<br>"
                "<b>⏱️ وقت التجهيز:</b> 20-30 دقيقة<br><br>"
                "شكراً لطلبك! 🙏"
                if lang == "ar" else
                "✅ <b>ORDER RECEIPT</b><br><br>"
                "━━━━━━━━━━━━━━━━━━━━━━<br>"
                "<b>📋 Order:</b><br>" + "<br>".join(summary) + "<br><br>"
                "━━━━━━━━━━━━━━━━━━━━━━<br>"
                f"<b>💰 Total:</b> {total:.2f} {CURRENCY}<br>"
                "<b>💵 Payment Method:</b> Cash<br>"
                "<b>⏱️ Preparation Time:</b> 20-30 minutes<br><br>"
                "Thank you for your order! 🙏"
            )
            
            session["state"] = {"stage": "await_feedback", "order_id": order_id, "order": [], "total": 0, "last_item": None, "last_qty": 0, "last_confirmed_item": None, "pending_item": None, "spice_queue": [], "generic_queue": []}
            return make_chat_response(receipt, lang)

        if any(x in msg_l for x in ["online", "online payment", "pay online", "card", "visa", "master", "debit", "mada"]) or any(x in msg for x in ["مدى", "إلكتروني", "دفع", "كرت"]):
            order_id = s.get("order_id")
            total = float(s.get("total", 0.0) or 0.0)
            update_order_payment(order_id, method="online", status="pending")
            schedule_feedback_after_payment(order_id)

            pay_url = f"{PAYMENT_URL}&order_id={order_id}"
            
            # ✅ BUILD RECEIPT with prominent payment link
            summary, _ = build_order_summary_and_total(s.get("order") or [], lang)
            reply = (
                "✅ <b>إيصال الطلب</b><br><br>"
                "━━━━━━━━━━━━━━━━━━━━━━<br>"
                "<b>📋 الطلب:</b><br>" + "<br>".join(summary) + "<br><br>"
                "━━━━━━━━━━━━━━━━━━━━━━<br>"
                f"<b>💰 الإجمالي:</b> {total:.2f} {CURRENCY_AR}<br>"
                "<b>💳 طريقة الدفع:</b> أونلاين<br>"
                "<b>⏱️ وقت التجهيز:</b> 20-30 دقيقة<br><br>"
                "━━━━━━━━━━━━━━━━━━━━━━<br>"
                f"<b>👇 اضغط على الرابط لإتمام الدفع:</b><br>"
                f"<a href='{pay_url}'>{pay_url}</a><br><br>"
                "شكراً لطلبك! 🙏"
                if lang == "ar" else
                "✅ <b>ORDER RECEIPT</b><br><br>"
                "━━━━━━━━━━━━━━━━━━━━━━<br>"
                "<b>📋 Order:</b><br>" + "<br>".join(summary) + "<br><br>"
                "━━━━━━━━━━━━━━━━━━━━━━<br>"
                f"<b>💰 Total:</b> {total:.2f} {CURRENCY}<br>"
                "<b>💳 Payment Method:</b> Online<br>"
                "<b>⏱️ Preparation Time:</b> 20-30 minutes<br><br>"
                "━━━━━━━━━━━━━━━━━━━━━━<br>"
                f"<b>👇 Click the link below to complete payment:</b><br>"
                f"<a href='{pay_url}'>{pay_url}</a><br><br>"
                "Thank you for your order! 🙏"
            )
            session["state"] = {"stage": "await_feedback", "order_id": order_id, "order": [], "total": 0, "last_item": None, "last_qty": 0, "last_confirmed_item": None, "pending_item": None, "spice_queue": [], "generic_queue": []}
            return make_chat_response(reply, lang)

        reply = "يرجى اختيار طريقة الدفع الصحيحة - نقدًا أو عبر الإنترنت" if lang == "ar" else "Please select a valid payment method — Cash or Online."
        return make_chat_response(reply, lang)

    # ✅ FEEDBACK COLLECTION AFTER PAYMENT
    if s.get("stage") == "await_feedback":
        # Check if user is providing rating
        if any(x in msg_l for x in ["excellent", "ممتاز", "رائع"]):
            order_id = s.get("order_id")
            save_feedback(order_id, rating="excellent", comment=msg)
            reply = (
                "شكراً على تقييمك الممتاز! 🌟🌟🌟🌟🌟<br>نتطلع لخدمتك مرة أخرى!"
                if lang == "ar" else
                "Thank you for your excellent rating! 🌟🌟🌟🌟🌟<br>We look forward to serving you again!"
            )
            session["state"] = {"stage": None, "order": [], "total": 0}
            return make_chat_response(reply, lang)
        
        elif any(x in msg_l for x in ["satisfied", "راض", "جيد", "good"]):
            order_id = s.get("order_id")
            save_feedback(order_id, rating="satisfied", comment=msg)
            reply = (
                "شكراً على تقييمك! 😊<br>نسعد بخدمتك دائماً!"
                if lang == "ar" else
                "Thank you for your rating! 😊<br>We're happy to serve you!"
            )
            session["state"] = {"stage": None, "order": [], "total": 0}
            return make_chat_response(reply, lang)
        
        elif any(x in msg_l for x in ["not satisfied", "unsatisfied", "bad", "غير راض", "سيء"]):
            order_id = s.get("order_id")
            save_feedback(order_id, rating="not_satisfied", comment=msg)
            reply = (
                "نأسف لعدم رضاك. 😔<br>يرجى مشاركة ملاحظاتك لنتحسن:"
                if lang == "ar" else
                "We're sorry you weren't satisfied. 😔<br>Please share your feedback so we can improve:"
            )
            s["stage"] = "await_feedback_comment"
            session["state"] = s
            return make_chat_response(reply, lang)
        
        # If just text (not rating), treat as written feedback
        elif len(msg.strip()) > 5:
            order_id = s.get("order_id")
            save_feedback(order_id, rating="comment", comment=msg)
            reply = (
                "شكراً على ملاحظاتك! 📝<br>نقدّر وقتك ونسعى للتحسين المستمر."
                if lang == "ar" else
                "Thank you for your feedback! 📝<br>We appreciate your time and strive for continuous improvement."
            )
            session["state"] = {"stage": None, "order": [], "total": 0}
            return make_chat_response(reply, lang)
    
    # ✅ COLLECT DETAILED FEEDBACK COMMENT
    if s.get("stage") == "await_feedback_comment":
        order_id = s.get("order_id")
        # Append comment to existing feedback
        save_feedback(order_id, rating="not_satisfied", comment=msg)
        reply = (
            "شكراً على وقتك! سنعمل على التحسين. 🙏"
            if lang == "ar" else
            "Thank you for your time! We'll work on improving. 🙏"
        )
        session["state"] = {"stage": None, "order": [], "total": 0}
        return make_chat_response(reply, lang)

    # ✅ INTELLIGENT FALLBACK - Context-aware guidance
    # Refresh session to get latest order state
    fresh_session = WHATSAPP_SESSIONS.get(user_number, {})
    fresh_state = fresh_session.get("state") or {}
    order_count = len(fresh_state.get("order", []))

    # 🚫 Guard against abusive queries only
    msg_low = (msg or "").lower()
    abusive_keywords = [
        "stupid", "idiot", "dumb", "shut up", "fuck", "shit", "bitch",
        "لعن", "قذر", "تافه"
    ]
    is_abusive = any(k in msg_low for k in abusive_keywords)

    if is_abusive:
        reply = (
            "آسف، لا يمكنني المساعدة في ذلك. يمكن طلب عناصر القائمة فقط. الرجاء الاختيار من القائمة."
            if lang == "ar" else
            "Sorry, I can't assist with that. Only menu items can be ordered. Please choose from the menu."
        )
        # Show category buttons again
        send_category_buttons(user_number, lang, show_image=False)
        session["state"] = s
        return make_chat_response(reply, lang)

    # Smart LLM with context
    reply = get_llm_reply(msg, lang)
    
    # Context-aware suggestions
    if order_count > 0:
        guide = (
            f"لديك {order_count} صنف في طلبك. هل تريد إضافة المزيد؟ 🍔☕\n"
            "أو اكتب 'إنهاء' لإكمال الطلب."
            if lang == "ar" else
            f"You have {order_count} item(s) in your cart. Want to add more? 🍔☕\n"
            "Or type 'finish' to complete your order."
        )
    else:
        guide = (
            "🍔 برجر | 🥪 ساندويتش | ☕ قهوة | 🍹 مشروبات<br>"
            "اكتب ما تريد (مثال: 2 برجر و 3 قهوة)"
            if lang == "ar" else
            "🍔 Burgers | 🥪 Sandwiches | ☕ Coffee | 🍹 Drinks<br>"
            "Type what you want (e.g., 2 burgers and 3 coffee)"
        )
    
    reply = merge_replies(reply, guide)
    return make_chat_response(reply, lang)

# =========================================================
# RUN (LOCAL)
# =========================================================
if __name__ == "__main__":
    app.run(debug=True)
