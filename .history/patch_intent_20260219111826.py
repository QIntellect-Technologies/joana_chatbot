# Temporary patch script to add intent handling
import re

with open(r'e:\Imran Projects\QIntellect Projects\Deployed_Cpanel\joana_chatbot\app.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = '''    if intent == "menu":
        reply = "Here's our menu! Please place your order." if lang == "en" else "هذه قائمتنا! من فضلك ضع طلبك."
        return make_chat_response(reply, lang, menu="/static/menu.PNG")


    # =========================================================
    # ✅ MULTI-ITEM TEXT'''

new = '''    if intent == "menu":
        reply = "Here's our menu! Please place your order." if lang == "en" else "هذه قائمتنا! من فضلك ضع طلبك."
        return make_chat_response(reply, lang, menu="/static/menu.PNG")

    # ✅ GREETING INTENT - Handle "hi", "how are you", etc.
    if intent == "greeting":
        greeting_reply = (
            "أهلاً وسهلاً! 👋 أنا مساعدك الذكي في مطعم JOANA!\\n\\n"
            "كيف يمكنني مساعدتك اليوم؟ 🍔\\n"
            "• اكتب 'menu' لعرض القائمة\\n"
            "• أو أخبرني ماذا تريد أن تطلب!"
            if lang == "ar" else
            "Hello! 👋 I'm your JOANA Fast Food assistant!\\n\\n"
            "How can I help you today? 🍔\\n"
            "• Type 'menu' to see our menu\\n"
            "• Or tell me what you'd like to order!"
        )
        return make_chat_response(greeting_reply, lang)

    # ✅ ORDER_START INTENT - Handle "I want to order", "can I order", etc.
    if intent == "order_start":
        order_start_reply = (
            "بالتأكيد! يمكنك الطلب الآن! 🎉\\n\\n"
            "📋 هذه قائمتنا! اختر ما تريد:"
            if lang == "ar" else
            "Of course! You can order now! 🎉\\n\\n"
            "📋 Here's our menu! Choose what you'd like:"
        )
        return make_chat_response(order_start_reply, lang, menu="/static/menu.PNG")


    # =========================================================
    # ✅ MULTI-ITEM TEXT'''

if old in content:
    content = content.replace(old, new)
    with open(r'e:\Imran Projects\QIntellect Projects\Deployed_Cpanel\joana_chatbot\app.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('SUCCESS')
else:
    print('NOT FOUND - searching for similar pattern...')
    # Try to find what we're looking for
    import re
    match = re.search(r'if intent == "menu":', content)
    if match:
        print(f'Found "if intent == menu" at position {match.start()}')
        # Show surrounding context
        start = max(0, match.start() - 50)
        end = min(len(content), match.end() + 200)
        print(f'Context: {repr(content[start:end])}')
