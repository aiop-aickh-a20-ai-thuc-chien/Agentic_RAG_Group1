import re
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

html_path = r"e:\VINSMART_Future_Thuc_Tap\Agentic_RAG_Project\Agentic_RAG_Group1\guide_2\demo\motorcycle\artifacts\https-shop-vinfastauto-com-vn-vi-dat-mua-xe-may-dien-vinfast_dd5430051b94\url-ingestion\source.html"

with open(html_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

for idx, line in enumerate(lines):
    if "Page-GetAllProduct" in line:
        print(f"Line {idx+1}: {line.strip()}")
        # print 5 lines before and after
        start = max(0, idx - 5)
        end = min(len(lines), idx + 6)
        for j in range(start, end):
            print(f"  {j+1}: {lines[j].strip()[:200]}")
        print("-" * 50)
