# Debug script to check line content
with open(r'e:\Imran Projects\QIntellect Projects\Deployed_Cpanel\joana_chatbot\app.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Check around line 6320
for i in range(6315, 6325):
    if i < len(lines):
        print(f'Line {i+1}: {repr(lines[i][:100])}')
