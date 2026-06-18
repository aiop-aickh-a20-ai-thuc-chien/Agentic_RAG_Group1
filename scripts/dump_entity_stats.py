"""Stats for entity_map.json: how many raw variants map to each canonical.

    uv run python scripts/dump_entity_stats.py

Writes entity_map_stats.md (full sorted table) and prints a summary + top 30.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

MAP_PATH = Path("src/agentic_rag/ingestion/metadata/entity_map.json")
OUT_PATH = Path("src/agentic_rag/ingestion/metadata/entity_map_stats.md")


def main() -> None:
    data = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    entity_map = data["map"]

    counts: Counter[str] = Counter()
    types: dict[str, str] = {}
    for entry in entity_map.values():
        canonical = entry["canonical"]
        counts[canonical] += 1
        types[canonical] = entry["type"]

    # distribution: how many canonicals have N variants
    dist = Counter(counts.values())

    lines: list[str] = [
        "# Entity Map — Variant Count per Canonical",
        "",
        f"- Raw strings: **{len(entity_map)}**",
        f"- Canonical entities: **{len(counts)}**",
        f"- Average variants/canonical: **{len(entity_map) / len(counts):.2f}**",
        "",
        "## Distribution (how many canonicals have N variants)",
        "",
        "| #variants | #canonicals |",
        "|-----------|-------------|",
    ]
    for n in sorted(dist):
        lines.append(f"| {n} | {dist[n]} |")

    # group by type for the full table
    by_type: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for canonical, count in counts.items():
        by_type[types[canonical]].append((canonical, count))

    type_order = [
        "car_model", "ebike_model", "location",
        "brand", "accessory", "contact", "generic", "other",
    ]
    lines.append("")
    lines.append("## Full list by type (canonical — #variants)")
    for etype in type_order:
        items = by_type.get(etype)
        if not items:
            continue
        items.sort(key=lambda kv: (-kv[1], kv[0].lower()))
        lines.append("")
        lines.append(f"### {etype} ({len(items)} canonical)")
        lines.append("")
        for canonical, count in items:
            lines.append(f"- {canonical} — {count}")

    OUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT_PATH}\n")

    print("Distribution (#variants -> #canonicals):")
    for n in sorted(dist):
        print(f"  {n:>2} variant(s): {dist[n]:>4} canonical")

    print(f"\nSingletons (1 variant): {dist.get(1, 0)} / {len(counts)} canonical")
    print("\nTop 30 canonical by #variants:")
    for canonical, count in counts.most_common(30):
        print(f"  {count:>3}  {canonical}  [{types[canonical]}]")


if __name__ == "__main__":
    main()
