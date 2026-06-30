html_path = r"e:\VINSMART_Future_Thuc_Tap\Agentic_RAG_Project\Agentic_RAG_Group1\guide_2\demo\motorcycle\artifacts\https-shop-vinfastauto-com-vn-vi-dat-mua-xe-may-dien-vinfast_dd5430051b94\url-ingestion\source.html"
out_path = r"e:\VINSMART_Future_Thuc_Tap\Agentic_RAG_Project\Agentic_RAG_Group1\tmp\inspected_details.txt"

with open(html_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

ranges = [
    (1340, 1480),
    (1580, 1680),
    (1770, 1810),
    (20480, 20550),
]

output = []
for start, end in ranges:
    output.append(f"=== Range {start} to {end} ===\n")
    for idx in range(start - 1, min(end, len(lines))):
        output.append(f"Line {idx+1}: {lines[idx]}")
    output.append("="*40 + "\n\n")

with open(out_path, "w", encoding="utf-8") as f:
    f.writelines(output)

print("Ranges written successfully")
