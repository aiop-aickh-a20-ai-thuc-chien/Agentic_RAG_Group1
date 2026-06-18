"""Demo the runtime entity normalizer (Phase 2). No store, no LLM — pure lookup.

    uv run python scripts/demo_entity_normalizer.py

Edit the lists below to try your own inputs.
"""
# ruff: noqa: E402, E501  (demo util: stdout reconfigure before imports; long Vietnamese strings)

import sys

sys.stdout.reconfigure(encoding="utf-8")

from agentic_rag.ingestion.metadata import (
    detect_in_query,
    filterable_canonicals,
    normalize,
    normalize_all,
)

VARIANTS = ["VF8", "VinFast VF 8", "Thảm Cốp 3D VF 7", "TP.HCM", "KlaraS", "EVO GRAND", "pin", "xe điện"]
QUERIES = [
    "pin VF8 mấy kWh",
    "VinFast VF 8 giá bao nhiêu",
    "Theon chạy được bao xa",
    "trạm sạc ở TP.HCM và Hà Nội",
    "chính sách bảo hành thế nào",   # no entity -> []
    "so sánh VF 8 với VF 9",
    "thẩm mỹ viện gần đây",          # must NOT false-match location "Mỹ"
]

print("=== normalize() — variant -> canonical ===")
for raw in VARIANTS:
    print(f"  {raw!r:25} -> {normalize(raw)!r}")

print("\n=== normalize_all() — list -> deduped canonicals ===")
print("  ", normalize_all(["VF8", "VinFast VF 8", "Thảm Cốp 3D VF 8", "Hà Nội"]))

print("\n=== detect_in_query() — entities found in a user query ===")
for q in QUERIES:
    print(f"  {q!r:35} -> {detect_in_query(q)}")

print("\n=== filterable menu sizes ===")
for etype, items in filterable_canonicals().items():
    print(f"  {etype:12} {len(items)}")
