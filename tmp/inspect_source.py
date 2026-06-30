import json
import re
import sys

# Ensure stdout uses utf-8 (though writing to file is safer)
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

html_path = r"e:\VINSMART_Future_Thuc_Tap\Agentic_RAG_Project\Agentic_RAG_Group1\guide_2\demo\motorcycle\artifacts\https-shop-vinfastauto-com-vn-vi-dat-mua-xe-may-dien-vinfast_dd5430051b94\url-ingestion\source.html"
out_path = r"e:\VINSMART_Future_Thuc_Tap\Agentic_RAG_Project\Agentic_RAG_Group1\tmp\inspect_output.txt"

with open(html_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

output_lines = [f"Total lines: {len(lines)}\n"]

search_terms = ["Evo 200", "Evo 200 Lite", "Evo Lite", "Evo Grand", "Evo Grand Lite", "REQ", "WHR", "GNV", "VF-ZFG"]

for idx, line in enumerate(lines):
    matched_terms = []
    for term in search_terms:
        if term.lower() in line.lower():
            matched_terms.append(term)
    if matched_terms:
        output_lines.append(f"Line {idx+1} matches terms {matched_terms}:\n")
        start = max(0, idx - 4)
        end = min(len(lines), idx + 10)
        for j in range(start, end):
            output_lines.append(f"  {j+1}: {lines[j].strip()}\n")
        output_lines.append("-" * 80 + "\n")

with open(out_path, "w", encoding="utf-8") as f:
    f.writelines(output_lines)

print("Inspection completed successfully.")
