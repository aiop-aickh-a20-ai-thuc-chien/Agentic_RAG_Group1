"""Build the entity filter allowlist: canonicals worth pre-filtering on.

PHASE 4-A. A canonical is "filter-worthy" only if it covers enough chunks —
filtering on a 1-chunk entity barely narrows anything and risks over-restriction,
while the dense/sparse retrieval finds it anyway. Below the threshold we simply
don't pre-filter (full hybrid search still runs), so a high bar is safe.

Reads chunk coverage from Neon (``entities_canonical``) and writes
``entity_filter_allowlist.json`` = the canonicals with coverage STRICTLY GREATER
than ``--min-chunks`` (default 10).

    uv run python scripts/build_filter_allowlist.py            # > 10 chunks
    uv run python scripts/build_filter_allowlist.py --min-chunks 5
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")

OUT_PATH = Path("src/agentic_rag/ingestion/metadata/entity_filter_allowlist.json")


def _conn() -> str:
    raw = os.getenv("LOCAL_SOURCE_POSTGRES_CONNECTION", "")
    return re.sub(r"^postgresql\+psycopg://", "postgresql://", raw)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build entity_filter_allowlist.json from Neon coverage."
    )
    parser.add_argument(
        "--min-chunks", type=int, default=10, help="Keep canonicals with coverage STRICTLY > this."
    )
    parser.add_argument("--output", type=Path, default=OUT_PATH)
    args = parser.parse_args()

    load_dotenv()
    try:
        from agentic_rag.runtime_env import load_local_env

        load_local_env()
    except Exception:
        pass

    import psycopg

    with psycopg.connect(_conn()) as conn:
        rows = conn.execute(
            """
            select canon, count(*) as n
            from local_rag_chunks,
                 jsonb_array_elements_text(metadata->'entities_canonical') as canon
            group by canon
            having count(*) > %s
            order by n desc, canon
            """,
            (args.min_chunks,),
        ).fetchall()

    canonicals = [canon for canon, _ in rows]
    payload = {
        "threshold": args.min_chunks,
        "note": f"canonicals with chunk coverage strictly greater than {args.min_chunks}",
        "count": len(canonicals),
        "coverage": dict(rows),
        "canonicals": canonicals,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Wrote {args.output}")
    print(f"  threshold: coverage > {args.min_chunks}")
    print(f"  kept: {len(canonicals)} canonicals")
    print("  " + ", ".join(f"{c}({n})" for c, n in rows))


if __name__ == "__main__":
    main()
