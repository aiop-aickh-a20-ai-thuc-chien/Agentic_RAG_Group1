"""Dump entity_map.json into a human-readable grouped report for review.

Writes ``entity_map_groups.md`` next to the map: each canonical entity followed
by every raw variant that maps to it, grouped by type, sorted by variant count.

    uv run python scripts/dump_entity_groups.py
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

MAP_PATH = Path("src/agentic_rag/ingestion/metadata/entity_map.json")
OUT_PATH = Path("src/agentic_rag/ingestion/metadata/entity_map_groups.md")

FILTERABLE = ("car_model", "ebike_model", "location")


def main() -> None:
    data = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    entity_map = data["map"]

    # canonical -> {type, variants}
    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for raw, entry in entity_map.items():
        groups[(entry["canonical"], entry["type"])].append(raw)

    by_type: dict[str, list[tuple[str, list[str]]]] = defaultdict(list)
    for (canonical, etype), variants in groups.items():
        by_type[etype].append((canonical, sorted(variants)))

    lines: list[str] = [
        "# Entity Map — Canonical Groups",
        "",
        f"- Raw strings: **{data['stats']['raw_strings']}**",
        f"- Canonical entities: **{data['stats']['canonical_entities']}**",
        f"- Source: `{data.get('source', '')}`",
        "",
        "Mỗi canonical theo sau là các variant gộp vào nó. "
        "Type lọc được (dùng cho filter): " + ", ".join(f"`{t}`" for t in FILTERABLE) + ".",
        "",
    ]

    # Filterable types first (most important to review), then the rest.
    type_order = [*FILTERABLE, "brand", "accessory", "contact", "generic", "other"]
    for etype in type_order:
        items = by_type.get(etype)
        if not items:
            continue
        items.sort(key=lambda kv: (-len(kv[1]), kv[0].lower()))
        n_canon = len(items)
        n_raw = sum(len(v) for _, v in items)
        flag = " ✅ FILTERABLE" if etype in FILTERABLE else ""
        lines.append(f"## {etype} — {n_canon} canonical / {n_raw} variants{flag}")
        lines.append("")
        for canonical, variants in items:
            if len(variants) == 1 and variants[0] == canonical:
                lines.append(f"- **{canonical}**")
            else:
                lines.append(f"- **{canonical}**  ←  {', '.join(variants)}")
        lines.append("")

    OUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    for etype in type_order:
        items = by_type.get(etype, [])
        if items:
            n_raw = sum(len(v) for _, v in items)
            print(f"  {etype:12} {len(items):>4} canonical / {n_raw:>4} variants")


if __name__ == "__main__":
    main()
