import re

def extract_qty_for_generic(msg: str, keyword_base: str) -> int:
    """e.g. '2 burgers' -> 2"""
    # handle sandwich/wraps logic if needed
    if keyword_base == "sandwich":
        # pattern for sandwich OR wrap
        pat = r"(\d+)\s*(?:sandwiches|sandwich|sandwhich|wraps|wrap)"
        m = re.search(pat, msg.lower())
        if m: return int(m.group(1))
        
        pat2 = r"(?:sandwiches|sandwich|sandwhich|wraps|wrap)[a-z]*\s*(\d+)"
        m2 = re.search(pat2, msg.lower())
        if m2: return int(m2.group(1))
    
    pat = r"(\d+)\s*" + keyword_base
    m = re.search(pat, msg.lower())
    if m: 
        return int(m.group(1))
    
    # suffix case "burgers 2"
    pat2 = keyword_base + r"[a-z]*\s*(\d+)"
    m2 = re.search(pat2, msg.lower())
    if m2:
        return int(m2.group(1))
    
    return 1

msg = "5 burgers and 4 wraps"
qty = extract_qty_for_generic(msg, "sandwich")
print(f"Msg: '{msg}', Keyword: 'sandwich', Qty: {qty}")

msg2 = "5 burgers and 4 sandwiches"
qty2 = extract_qty_for_generic(msg2, "sandwich")
print(f"Msg: '{msg2}', Keyword: 'sandwich', Qty: {qty2}")

msg3 = "2 beef and 3 chicken"
qty3 = extract_qty_for_generic(msg3, "sandwich")
print(f"Msg: '{msg3}', Keyword: 'sandwich', Qty: {qty3}")
