import json

network_path = r"e:\VINSMART_Future_Thuc_Tap\Agentic_RAG_Project\Agentic_RAG_Group1\guide_2\demo\motorcycle\artifacts\https-shop-vinfastauto-com-vn-vi-dat-mua-xe-may-dien-vinfast_dd5430051b94\url-ingestion-interactions\network_payloads.jsonl"
out_path = r"e:\VINSMART_Future_Thuc_Tap\Agentic_RAG_Project\Agentic_RAG_Group1\tmp\network_output.txt"

payloads = []
try:
    with open(network_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                payloads.append(json.loads(line))
except Exception as e:
    print(f"Error reading network payloads: {e}")

print(f"Loaded {len(payloads)} network payloads.")

results = []
results.append(f"Loaded {len(payloads)} network payloads:\n")

for idx, p in enumerate(payloads):
    url = p.get("url")
    method = p.get("method")
    status = p.get("status")
    res_type = p.get("resource_type")
    
    results.append(f"Payload {idx}: method='{method}', url='{url}', status={status}, type='{res_type}'\n")
    
    # Check if there is response body and print if it matches terms
    body = p.get("response_body") or ""
    if any(term in str(body) for term in ["EVOLITE", "EVOGRAND", "Products-Scooter", "VF-ZFG"]):
        results.append(f"  --> MATCH FOUND in response body! URL: {url}\n")
        # Try to parse as JSON and print keys
        try:
            js = json.loads(body)
            results.append(f"  Parsed JSON keys: {list(js.keys())}\n")
            # Write a snippet
            results.append(f"  Snippet: {str(js)[:500]}\n")
        except Exception:
            results.append(f"  Raw Body Snippet: {str(body)[:500]}\n")

with open(out_path, "w", encoding="utf-8") as f:
    f.writelines(results)

print("Network scan complete")
