# Insert intent handlers after line 6320
with open(r'e:\Imran Projects\QIntellect Projects\Deployed_Cpanel\joana_chatbot\app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the line with "return make_chat_response(reply, lang, menu=" 
insert_after = None
for i, line in enumerate(lines):
    if 'return make_chat_response(reply, lang, menu="/static/menu.PNG")' in line and 'if intent == "menu"' in lines[i-2]:
        insert_after = i
        break

if insert_after is None:
    print("Could not find insertion point!")
    exit(1)

print(f"Found insertion point at line {insert_after + 1}")

new_code = '''
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

'''

# Insert after the target line (keeping the blank lines)
lines.insert(insert_after + 1, new_code)

with open(r'e:\Imran Projects\QIntellect Projects\Deployed_Cpanel\joana_chatbot\app.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("SUCCESS - Intent handlers added!")
