import re
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

html_path = r"e:\VINSMART_Future_Thuc_Tap\Agentic_RAG_Project\Agentic_RAG_Group1\guide_2\demo\motorcycle\artifacts\https-shop-vinfastauto-com-vn-vi-dat-mua-xe-may-dien-vinfast_dd5430051b94\url-ingestion\source.html"
out_path = r"e:\VINSMART_Future_Thuc_Tap\Agentic_RAG_Project\Agentic_RAG_Group1\tmp\js_data_output.txt"

with open(html_path, "r", encoding="utf-8") as f:
    html = f.read()

# Let's search for script tags
script_pattern = re.compile(r'<script[^>]*>(.*?)</script>', re.DOTALL)
scripts = script_pattern.findall(html)

results = []

for idx, content in enumerate(scripts):
    # Check if this script contains product info
    if any(term in content for term in ["Products-Scooter-EVO", "Products-Scooter-EVOLITE", "Products-Scooter-EVOGRAND"]):
        results.append(f"\n================ Script {idx} (len {len(content)}) ================\n")
        # Write first 50 lines or matching blocks
        lines = content.splitlines()
        for l_idx, line in enumerate(lines):
            results.append(f"Line {l_idx+1}: {line.strip()}\n")

with open(out_path, "w", encoding="utf-8") as f:
    f.writelines(results)

print("JS Data search completed successfully.")
