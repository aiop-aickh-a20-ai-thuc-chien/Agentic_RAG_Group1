import re
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

html_path = r"e:\VINSMART_Future_Thuc_Tap\Agentic_RAG_Project\Agentic_RAG_Group1\guide_2\demo\motorcycle\artifacts\https-shop-vinfastauto-com-vn-vi-dat-mua-xe-may-dien-vinfast_dd5430051b94\url-ingestion\source.html"
out_path = r"e:\VINSMART_Future_Thuc_Tap\Agentic_RAG_Project\Agentic_RAG_Group1\tmp\find_colors_output.txt"

with open(html_path, "r", encoding="utf-8") as f:
    html = f.read()

print("File loaded. Searching...")

# Pattern for slide-item: <li class="slide-item " data-name="Đỏ Tươi" data-item="REQ" data-pid="VF-ZFG-ESNEALHH-REQ">
pattern = re.compile(r'<li\s+[^>]*class="[^"]*slide-item[^"]*"[^>]*>')
slide_items = pattern.findall(html)
print(f"Found {len(slide_items)} slide-item elements")

results = []
results.append(f"Found {len(slide_items)} slide-item elements:\n")

for idx, item in enumerate(slide_items):
    # Extract data attributes using regex
    name_match = re.search(r'data-name="([^"]*)"', item)
    item_match = re.search(r'data-item="([^"]*)"', item)
    pid_match = re.search(r'data-pid="([^"]*)"', item)
    
    name = name_match.group(1) if name_match else "None"
    code = item_match.group(1) if item_match else "None"
    pid = pid_match.group(1) if pid_match else "None"
    
    results.append(f"Item {idx}: name='{name}', code='{code}', pid='{pid}', html='{item.strip()}'\n")

# Let's search for script tags containing JSON or javascript models data
# For example, look for variables that might contain "VF-ZFG-"
script_pattern = re.compile(r'<script[^>]*>(.*?)</script>', re.DOTALL)
scripts = script_pattern.findall(html)
print(f"Found {len(scripts)} scripts")
results.append(f"\nFound {len(scripts)} scripts\n")

for idx, content in enumerate(scripts):
    if "VF-ZFG" in content or "EVOLITE" in content or "EVOGRAND" in content or "colorItemList" in content or "color" in content:
        results.append(f"\n--- Script {idx} (len {len(content)}) ---\n")
        # Find if it contains any product json structure
        # print the lines matching model info
        lines = content.splitlines()
        for l_idx, line in enumerate(lines):
            if any(term in line for term in ["VF-ZFG", "EVOLITE", "EVOGRAND", "colorItemList", "price", "Products-Scooter"]):
                results.append(f"  Line {l_idx+1}: {line.strip()[:200]}\n")

with open(out_path, "w", encoding="utf-8") as f:
    f.writelines(results)

print("Color search completed successfully.")
