"""How many chunks each canonical entity would filter to (from Neon).

Counts chunks whose ``entities_canonical`` contains each canonical value — i.e.
exactly what a Qdrant ``MatchAny`` pre-filter on that canonical would return.

    uv run python scripts/dump_canonical_coverage.py

Writes entity_canonical_coverage.md and prints the top entries.
"""
# ruff: noqa: E402  (report util: stdout reconfigure before imports; long Vietnamese strings)

from __future__ import annotations

import json
import os
import re
import sys
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
OUT_PATH = Path("src/agentic_rag/ingestion/metadata/entity_canonical_coverage.md")


def _conn() -> str:
    raw = os.getenv("LOCAL_SOURCE_POSTGRES_CONNECTION", "")
    return re.sub(r"^postgresql\+psycopg://", "postgresql://", raw)


def main() -> None:
    # type per canonical (from the map) for annotation
    entity_map = json.loads(MAP_PATH.read_text(encoding="utf-8"))["map"]
    canon_type: dict[str, str] = {}
    for entry in entity_map.values():
        canon_type.setdefault(entry["canonical"], entry["type"])

    with psycopg.connect(_conn()) as conn:
        total_chunks = conn.execute("select count(*) from local_rag_chunks").fetchone()[0]
        rows = conn.execute(
            """
            select canon, count(*) as n
            from local_rag_chunks,
                 jsonb_array_elements_text(metadata->'entities_canonical') as canon
            group by canon
            order by n desc, canon
            """
        ).fetchall()

    lines = [
        "# Canonical Entity → Chunk Coverage",
        "",
        f"- Total chunks: **{total_chunks}**",
        f"- Distinct canonical entities used as filters: **{len(rows)}**",
        "",
        "Số chunk mỗi canonical lọc ra (filter `entities_canonical` chứa giá trị đó).",
        "",
        "| canonical | type | #chunks | % corpus |",
        "|-----------|------|---------|----------|",
    ]
    for canon, n in rows:
        etype = canon_type.get(canon, "?")
        lines.append(f"| {canon} | {etype} | {n} | {100 * n / total_chunks:.1f}% |")
    OUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT_PATH}  ({len(rows)} canonical)\n")

    print(f"Total chunks: {total_chunks}")
    print("\nTop 40 canonical by chunk coverage:")
    print(f"  {'#chunks':>7}  {'%':>5}  canonical [type]")
    for canon, n in rows[:40]:
        etype = canon_type.get(canon, "?")
        print(f"  {n:>7}  {100 * n / total_chunks:>4.1f}%  {canon} [{etype}]")


if __name__ == "__main__":
    main()
