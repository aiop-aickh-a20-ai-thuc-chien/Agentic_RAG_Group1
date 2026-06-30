import re
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

html_path = r"e:\VINSMART_Future_Thuc_Tap\Agentic_RAG_Project\Agentic_RAG_Group1\guide_2\demo\motorcycle\artifacts\https-shop-vinfastauto-com-vn-vi-dat-mua-xe-may-dien-vinfast_dd5430051b94\url-ingestion\source.html"
out_path = r"e:\VINSMART_Future_Thuc_Tap\Agentic_RAG_Project\Agentic_RAG_Group1\tmp\ajax_urls.txt"

with open(html_path, "r", encoding="utf-8") as f:
    html = f.read()

# Let's search for URLs or paths starting with /on/demandware.store or containing CartBike or SelectModel
ajax_urls = re.findall(r'["\'](/on/demandware.store/[^"\']+)["\']', html)
print(f"Found {len(ajax_urls)} unique demandware URLs:")

results = []
results.append(f"Found {len(ajax_urls)} unique demandware URLs:\n")
for url in sorted(list(set(ajax_urls))):
    results.append(f"  {url}\n")

# Let's also look for script tags that contain "url" or "ajax" or "fetch" or "get" along with "Select" or "Model" or "Cart"
script_pattern = re.compile(r'<script[^>]*>(.*?)</script>', re.DOTALL)
scripts = script_pattern.findall(html)
results.append(f"\nSearching fetch/ajax details in scripts:\n")

for idx, content in enumerate(scripts):
    if any(term in content for term in ["$.ajax", "fetch(", "url:", "endpoint", "CartBike"]):
        results.append(f"\n--- Script {idx} has ajax/fetch keyword ---\n")
        lines = content.splitlines()
        for l_idx, line in enumerate(lines):
            if any(term in line for term in ["ajax", "fetch", "url", "endpoint", "CartBike", "SelectProduct", "getProduct"]):
                results.append(f"  Line {l_idx+1}: {line.strip()}\n")

with open(out_path, "w", encoding="utf-8") as f:
    f.writelines(results)

print("Ajax search completed successfully.")
