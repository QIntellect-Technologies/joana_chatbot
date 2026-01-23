import re

def extract_qty_for_generic(msg: str, keyword_base: str) -> int:
    """e.g. '2 burgers' -> 2"""
    if keyword_base == "sandwich":
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
    
    pat2 = keyword_base + r"[a-z]*\s*(\d+)"
    m2 = re.search(pat2, msg.lower())
    if m2:
        return int(m2.group(1))
    
    return 1

msg4 = "5 burgers, 4 wraps"
qty4 = extract_qty_for_generic(msg4, "sandwich")
print(f"Msg: '{msg4}', Keyword: 'sandwich', Qty: {qty4}")

msg5 = "5 burgers 4 wraps"
qty5 = extract_qty_for_generic(msg5, "sandwich")
print(f"Msg: '{msg5}', Keyword: 'sandwich', Qty: {qty5}")
