import json
import re
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

chunks_paths = [
    r"e:\VINSMART_Future_Thuc_Tap\Agentic_RAG_Project\Agentic_RAG_Group1\guide_2\demo\motorcycle\artifacts\https-shop-vinfastauto-com-vn-vi-dat-mua-xe-may-dien-vinfast_dd5430051b94\url-ingestion\chunks.jsonl",
    r"e:\VINSMART_Future_Thuc_Tap\Agentic_RAG_Project\Agentic_RAG_Group1\guide_2\demo\motorcycle\artifacts\https-shop-vinfastauto-com-vn-vi-dat-mua-xe-may-dien-vinfast_dd5430051b94\url-ingestion-interactions\chunks.jsonl"
]

out_path = r"e:\VINSMART_Future_Thuc_Tap\Agentic_RAG_Project\Agentic_RAG_Group1\tmp\chunks_search_results.txt"

search_terms = ["Evo", "Lite", "Grand", "EVOLITE", "EVOGRAND"]

results = []
results.append("=== Chunks Search Results ===\n")

for chunks_path in chunks_paths:
    results.append(f"\nScanning: {chunks_path}\n")
    print(f"Scanning {chunks_path}...")
    count = 0
    match_count = 0

    with open(chunks_path, "r", encoding="utf-8") as f:
        for line in f:
            count += 1
            if not line.strip():
                continue
            try:
                chunk = json.loads(line)
                text = chunk.get("text", "")
                
                matched = []
                for term in search_terms:
                    if term.lower() in text.lower():
                        matched.append(term)
                
                if matched:
                    match_count += 1
                    metadata = chunk.get("metadata", {})
                    results.append(f"\nChunk {count} matched terms {matched}:\n")
                    results.append(f"  ID: {chunk.get('chunk_id')}\n")
                    results.append(f"  Section: {metadata.get('section')}\n")
                    results.append(f"  Text: {text.strip()}\n")
                    results.append("-" * 60 + "\n")
            except Exception as e:
                continue

    print(f"Scanned {count} chunks. Found {match_count} matches.")
    results.append(f"Scanned {count} chunks. Found {match_count} matches.\n")

with open(out_path, "w", encoding="utf-8") as f:
    f.writelines(results)

print("Search completed.")
