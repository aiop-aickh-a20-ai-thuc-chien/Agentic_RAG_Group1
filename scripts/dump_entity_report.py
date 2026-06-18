"""Generate ONE complete entity-normalization statistics report.

    uv run python scripts/dump_entity_report.py

Reads entity_map.json (the map) + Neon (chunk coverage) and writes
``entity_normalization_report.md`` with every stat in one place.
"""
# ruff: noqa: E402, E501  (report util: stdout reconfigure before imports; long Vietnamese strings)

from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv

load_dotenv()
try:
    from agentic_rag.runtime_env import load_local_env

    load_local_env()
except Exception:
    pass

import psycopg

MAP_PATH = Path("src/agentic_rag/ingestion/metadata/entity_map.json")
OUT_PATH = Path("src/agentic_rag/ingestion/metadata/entity_normalization_report.md")

FILTERABLE = ("car_model", "ebike_model", "location")
TYPE_ORDER = [*FILTERABLE, "brand", "accessory", "contact", "generic", "other"]


def _conn() -> str:
    return re.sub(
        r"^postgresql\+psycopg://",
        "postgresql://",
        os.getenv("LOCAL_SOURCE_POSTGRES_CONNECTION", ""),
    )


def main() -> None:
    data = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    entity_map = data["map"]

    # variants per canonical + type per canonical (first seen)
    variants: Counter[str] = Counter()
    canon_type: dict[str, str] = {}
    raw_by_type: Counter[str] = Counter()
    for entry in entity_map.values():
        variants[entry["canonical"]] += 1
        canon_type.setdefault(entry["canonical"], entry["type"])
        raw_by_type[entry["type"]] += 1

    canon_by_type: dict[str, set[str]] = defaultdict(set)
    for canonical, etype in canon_type.items():
        canon_by_type[etype].add(canonical)

    # chunk coverage from Neon
    with psycopg.connect(_conn()) as conn:
        total_chunks = conn.execute("select count(*) from local_rag_chunks").fetchone()[0]
        cov_rows = conn.execute(
            """
            select canon, count(*) as n
            from local_rag_chunks,
                 jsonb_array_elements_text(metadata->'entities_canonical') as canon
            group by canon order by n desc, canon
            """
        ).fetchall()
        chunks_with_any = conn.execute(
            "select count(*) from local_rag_chunks "
            "where jsonb_array_length(metadata->'entities_canonical') > 0"
        ).fetchone()[0]
    coverage = dict(cov_rows)

    L: list[str] = []
    a = L.append

    a("# Entity Normalization — Báo cáo thống kê hoàn chỉnh")
    a("")
    a("## 1. Tổng quan")
    a("")
    a(f"- Raw entity (cách viết thô): **{len(entity_map)}**")
    a(f"- Canonical (sau chuẩn hóa): **{len(variants)}**")
    a(
        f"- Tỉ lệ gộp: {len(entity_map)}/{len(variants)} = **{len(entity_map) / len(variants):.2f}** variant/canonical"
    )
    a(f"- Tổng chunk trong corpus: **{total_chunks}**")
    a(
        f"- Chunk có ≥1 entity filterable: **{chunks_with_any}** ({100 * chunks_with_any / total_chunks:.1f}%)"
    )
    a(f"- Canonical thực sự lọc ra chunk: **{len(coverage)}**")
    a("")

    a("## 2. Theo type")
    a("")
    a("| type | raw | canonical | filterable |")
    a("|------|-----|-----------|------------|")
    for t in TYPE_ORDER:
        if raw_by_type.get(t):
            flag = "✅" if t in FILTERABLE else "—"
            a(f"| {t} | {raw_by_type[t]} | {len(canon_by_type.get(t, set()))} | {flag} |")
    a("")

    a("## 3. Phân bố số variant / canonical")
    a("")
    dist = Counter(variants.values())
    a("| #variants | #canonical |")
    a("|-----------|------------|")
    for n in sorted(dist):
        a(f"| {n} | {dist[n]} |")
    a("")
    a(f"> {dist.get(1, 0)}/{len(variants)} canonical chỉ có 1 cách viết (không gộp gì).")
    a("")

    a("## 4. Coverage — mỗi canonical lọc ra bao nhiêu chunk")
    a("")
    a(
        f"Số canonical lọc ra ≥1 chunk: **{len(coverage)}**. (Filter `entities_canonical` chứa giá trị.)"
    )
    a("")
    a("| canonical | type | #chunks | % corpus |")
    a("|-----------|------|---------|----------|")
    for canon, n in cov_rows:
        a(f"| {canon} | {canon_type.get(canon, '?')} | {n} | {100 * n / total_chunks:.1f}% |")
    a("")

    a("## 5. Menu canonical filterable (dùng cho query filter)")
    a("")
    for t in FILTERABLE:
        items = sorted(canon_by_type.get(t, set()))
        a(f"### {t} ({len(items)})")
        a("")
        a(", ".join(items))
        a("")

    a("## 6. Ghi chú")
    a("")
    a(
        "- **Non-filterable** (brand/generic/contact/other): cố tình loại khỏi filter "
        "(vd 'VinFast' 75% chunk, 'pin', 'xe điện') — không phải rác, chỉ không dùng pre-filter."
    )
    a(
        "- **Đuôi dài** (canonical ít chunk): hiếm nhưng hợp lệ; vô hại, chỉ trigger khi query nhắc tới."
    )
    a(
        "- **Lưu ý type:** một canonical có thể hiện sai type ở vài chỗ (vd 'Lux A2.0') do type "
        "được LLM gán theo cụm — số coverage vẫn đúng."
    )

    OUT_PATH.write_text("\n".join(L), encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    print(f"  raw={len(entity_map)} canonical={len(variants)} filterable_canonical={len(coverage)}")
    print(f"  chunks={total_chunks} with_entity={chunks_with_any}")


if __name__ == "__main__":
    main()
