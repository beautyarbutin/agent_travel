import json
import re

with open(r'C:\Users\86173\Desktop\新建 文本文档 (2).txt', 'r', encoding='utf-8') as f:
    text = f.read()

# Fix common issues
text = text.replace('"tags":,', '"tags": [],')

# We'll use a regex to find all objects that look like spots and extract them into a list
pattern = re.compile(r'\{\s*"id":\s*"spot_[^"]*".*?\}', re.DOTALL)
matches = pattern.findall(text)

valid_spots = []
for m in matches:
    # Some matches might still have trailing commas or incomplete JSON syntax internally
    # Let's try to parse each one individually
    try:
        spot = json.loads(m)
        valid_spots.append(spot)
    except Exception as e:
        # Try some light fixing
        fixed = m.strip()
        if fixed.endswith(','):
            fixed = fixed[:-1]
        try:
            spot = json.loads(fixed)
            valid_spots.append(spot)
        except Exception as e2:
            print(f"Skipping a spot due to error: {e2}")

with open('d:/20251224/AI_Study/OpenAgents/data/new_guides.json', 'w', encoding='utf-8') as f:
    json.dump(valid_spots, f, ensure_ascii=False, indent=2)

print(f"Successfully wrote {len(valid_spots)} items to new_guides.json")
