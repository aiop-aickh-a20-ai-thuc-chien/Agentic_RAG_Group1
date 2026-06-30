import re
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

html_path = r"e:\VINSMART_Future_Thuc_Tap\Agentic_RAG_Project\Agentic_RAG_Group1\guide_2\demo\motorcycle\artifacts\https-shop-vinfastauto-com-vn-vi-dat-mua-xe-may-dien-vinfast_dd5430051b94\url-ingestion\source.html"
out_path = r"e:\VINSMART_Future_Thuc_Tap\Agentic_RAG_Project\Agentic_RAG_Group1\tmp\js_objects.txt"

with open(html_path, "r", encoding="utf-8") as f:
    html = f.read()

# Let's find script tags containing 'window.vinfast' or 'window.leasingServices'
script_pattern = re.compile(r'<script[^>]*>(.*?)</script>', re.DOTALL)
scripts = script_pattern.findall(html)

results = []

for idx, content in enumerate(scripts):
    if "window.vinfast" in content or "window.leasingServices" in content or "window.allBikes" in content or "window.products" in content:
        results.append(f"\n================ Script {idx} (len {len(content)}) ================\n")
        # Split into lines and write all lines
        for l_idx, line in enumerate(content.splitlines()):
            # We want to format json if it is one long line
            if len(line) > 1000:
                results.append(f"  Line {l_idx+1} (long line, length {len(line)}): {line[:1000]}...\n")
                # Let's extract object structures if we can
                # E.g. find keys
                keys = re.findall(r'"([^"]+)":', line[:20000])
                results.append(f"    Sample keys: {list(set(keys))[:30]}\n")
            else:
                results.append(f"  Line {l_idx+1}: {line}\n")

with open(out_path, "w", encoding="utf-8") as f:
    f.writelines(results)

print("JS objects search completed successfully.")
