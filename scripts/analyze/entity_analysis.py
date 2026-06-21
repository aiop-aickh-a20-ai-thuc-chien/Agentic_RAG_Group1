"""Entity Analysis — phân tích entities LLM-extracted trong corpus.

Chạy:
    uv run python scripts/analyze/entity_analysis.py

Sections:
  1. Frequency distribution — entity nào xuất hiện nhiều nhất
  2. Per-chunk count distribution — mỗi chunk có bao nhiêu entity
  3. Similarity clustering — tìm các entity "cùng nghĩa" nhưng viết khác nhau
  4. VinFast model detection — kiểm tra độ nhất quán tên model
  5. Proposed canonical mapping — gợi ý chuẩn hóa
"""

from __future__ import annotations

import os
import re
import sys
from collections import Counter, defaultdict
from difflib import SequenceMatcher

import pandas as pd
from dotenv import load_dotenv
from tabulate import tabulate

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()

# ---------------------------------------------------------------------------
# Load env + connect
# ---------------------------------------------------------------------------
try:
    from agentic_rag.runtime_env import load_local_env
    load_local_env()
except Exception:
    pass

import psycopg  # noqa: E402

_CONN = re.sub(
    r"^postgresql\+psycopg://",
    "postgresql://",
    os.getenv("LOCAL_SOURCE_POSTGRES_CONNECTION", ""),
)
if not _CONN:
    sys.exit("LOCAL_SOURCE_POSTGRES_CONNECTION not set")


def _load_data() -> pd.DataFrame:
    with psycopg.connect(_CONN) as conn:
        rows = conn.execute(
            """
            SELECT
              metadata->>'chunk_id'       AS chunk_id,
              metadata->>'document_type'  AS document_type,
              metadata->'entities'        AS entities,
              metadata->'keywords'        AS keywords,
              LEFT(text, 80)              AS text_preview
            FROM local_rag_chunks
            WHERE metadata->'entities' IS NOT NULL
            """
        ).fetchall()
    return pd.DataFrame(rows, columns=["chunk_id", "document_type", "entities", "keywords", "text_preview"])


# ---------------------------------------------------------------------------
# Section 1 — Frequency distribution
# ---------------------------------------------------------------------------
def section_frequency(df: pd.DataFrame) -> list[str]:
    """Đếm tần suất mỗi entity string (raw, chưa normalize)."""
    counter: Counter[str] = Counter()
    for ents in df["entities"]:
        if ents:
            for e in ents:
                counter[str(e).strip()] += 1

    top = counter.most_common(50)
    rows = [{"entity": e, "count": c, "pct_chunks": f"{100*c/len(df):.1f}%"} for e, c in top]
    return rows


# ---------------------------------------------------------------------------
# Section 2 — Per-chunk entity count
# ---------------------------------------------------------------------------
def section_per_chunk_count(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["n_entities"] = df["entities"].apply(lambda x: len(x) if x else 0)
    dist = df["n_entities"].value_counts().sort_index().reset_index()
    dist.columns = ["n_entities", "chunks"]
    dist["pct"] = (dist["chunks"] / len(df) * 100).round(1).astype(str) + "%"
    return dist


# ---------------------------------------------------------------------------
# Section 3 — Similarity clustering
# ---------------------------------------------------------------------------
def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def section_clustering(df: pd.DataFrame, threshold: float = 0.75) -> list[dict]:
    """Cluster entity strings với similarity >= threshold.
    Dùng greedy single-linkage: mỗi string vào cluster đầu tiên mà nó gần."""
    counter: Counter[str] = Counter()
    for ents in df["entities"]:
        if ents:
            for e in ents:
                counter[str(e).strip()] += 1

    # Only cluster entities appearing >= 2 times (noise filter)
    strings = [s for s, c in counter.items() if c >= 2]

    clusters: list[list[str]] = []
    assigned: set[str] = set()

    for s in sorted(strings, key=lambda x: -counter[x]):  # most frequent first
        if s in assigned:
            continue
        cluster = [s]
        assigned.add(s)
        for t in strings:
            if t not in assigned and _similarity(s, t) >= threshold:
                cluster.append(t)
                assigned.add(t)
        if len(cluster) > 1:
            clusters.append(cluster)

    results = []
    for cluster in sorted(clusters, key=lambda c: -sum(counter[s] for s in c)):
        canonical = max(cluster, key=lambda s: counter[s])  # most frequent = canonical
        results.append({
            "canonical (most frequent)": canonical,
            "variants": " | ".join(s for s in cluster if s != canonical),
            "total_occurrences": sum(counter[s] for s in cluster),
        })
    return results


# ---------------------------------------------------------------------------
# Section 4 — VinFast model detection
# ---------------------------------------------------------------------------
_VF_PATTERN = re.compile(
    r"\bVF[\s\-]?(e?3[45]?|[3-9]|Wild|DrgnFly|Lux[A-Z]|e34)\b",
    re.IGNORECASE,
)

_VF_CANONICAL = {
    "vf e34": "VF e34", "vfe34": "VF e34",
    "vf3": "VF 3", "vf 3": "VF 3",
    "vf5": "VF 5", "vf 5": "VF 5",
    "vf6": "VF 6", "vf 6": "VF 6",
    "vf7": "VF 7", "vf 7": "VF 7",
    "vf8": "VF 8", "vf 8": "VF 8",
    "vf9": "VF 9", "vf 9": "VF 9",
    "vf wild": "VF Wild",
    "vf drgnfly": "VF DrgnFly",
}


def _to_canonical_model(raw: str) -> str | None:
    key = raw.lower().replace("-", " ").strip()
    if key in _VF_CANONICAL:
        return _VF_CANONICAL[key]
    m = _VF_PATTERN.search(raw)
    if m:
        return f"VF {m.group(1).strip()}"
    return None


def section_model_normalization(df: pd.DataFrame) -> pd.DataFrame:
    """Tìm tất cả entity có vẻ là tên model VF, group theo canonical."""
    model_counter: dict[str, Counter] = defaultdict(Counter)
    for ents in df["entities"]:
        if not ents:
            continue
        for e in ents:
            s = str(e).strip()
            canonical = _to_canonical_model(s)
            if canonical:
                model_counter[canonical][s] += 1

    rows = []
    for canonical, variants in sorted(model_counter.items()):
        total = sum(variants.values())
        variant_str = ", ".join(f'"{v}"×{c}' for v, c in variants.most_common())
        rows.append({
            "canonical": canonical,
            "total": total,
            "variants_found": variant_str,
            "normalized?": "✓" if len(variants) == 1 else "⚠ inconsistent",
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Section 5 — Entities with no VinFast model (free-form)
# ---------------------------------------------------------------------------
def section_freeform_entities(df: pd.DataFrame, top_n: int = 30) -> list[dict]:
    """Entity không phải tên model VF — địa điểm, phụ kiện, khác."""
    counter: Counter[str] = Counter()
    for ents in df["entities"]:
        if not ents:
            continue
        for e in ents:
            s = str(e).strip()
            if not _to_canonical_model(s) and s.lower() not in ("vinfast", "vf", ""):
                counter[s] += 1
    return [{"entity": e, "count": c} for e, c in counter.most_common(top_n)]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def _summary_stats(df: pd.DataFrame) -> dict:
    counter: Counter[str] = Counter()
    for ents in df["entities"]:
        if ents:
            for e in ents:
                counter[str(e).strip()] += 1
    return {
        "total_chunks": len(df),
        "chunks_with_entities": int(df["entities"].apply(bool).sum()),
        "total_entity_occurrences": sum(counter.values()),
        "distinct_entity_strings": len(counter),
        "entities_appearing_once": sum(1 for c in counter.values() if c == 1),
        "entities_appearing_2_to_5": sum(1 for c in counter.values() if 2 <= c <= 5),
        "entities_appearing_6_plus": sum(1 for c in counter.values() if c >= 6),
    }


def main() -> None:
    print("Loading data from Neon...")
    df = _load_data()
    print(f"Loaded {len(df):,} chunks with entities\n")

    # --- 0. Summary ---
    print("=" * 70)
    print("SECTION 0 — Corpus summary statistics")
    print("=" * 70)
    stats = _summary_stats(df)
    for k, v in stats.items():
        print(f"  {k:<40} {v:,}")
    print()

    # --- 1. Frequency ---
    print("=" * 70)
    print("SECTION 1 — Top 50 most frequent entities (raw)")
    print("=" * 70)
    freq_rows = section_frequency(df)
    print(tabulate(freq_rows[:50], headers="keys", tablefmt="github"))
    print()

    # --- 2. Per-chunk count ---
    print("=" * 70)
    print("SECTION 2 — Entity count per chunk distribution")
    print("=" * 70)
    dist = section_per_chunk_count(df)
    print(tabulate(dist.to_dict("records"), headers="keys", tablefmt="github"))
    avg = df["entities"].apply(lambda x: len(x) if x else 0).mean()
    print(f"\n  avg entities/chunk = {avg:.2f}")
    print()

    # --- 3. Clustering ---
    print("=" * 70)
    print("SECTION 3 — Similar entity clusters (similarity >= 0.75)")
    print("  Mỗi cluster là các chuỗi 'cùng nghĩa' nhưng viết khác nhau")
    print("  Canonical = string xuất hiện nhiều nhất trong cluster")
    print("=" * 70)
    clusters = section_clustering(df, threshold=0.75)
    if clusters:
        print(tabulate(clusters[:40], headers="keys", tablefmt="github"))
    else:
        print("  Không tìm thấy cluster nào (entities đã nhất quán)")
    print()

    # --- 4. VinFast model normalization ---
    print("=" * 70)
    print("SECTION 4 — VinFast model names: canonical vs variants")
    print("  ✓ = chỉ 1 dạng viết   ⚠ = nhiều dạng viết khác nhau")
    print("=" * 70)
    model_df = section_model_normalization(df)
    if not model_df.empty:
        print(tabulate(model_df.to_dict("records"), headers="keys", tablefmt="github"))
    else:
        print("  Không tìm thấy tên model VF nào trong entities")
    print()

    # --- 5. Free-form entities ---
    print("=" * 70)
    print("SECTION 5 — Top free-form entities (non-model, non-VinFast brand)")
    print("  Đây là địa điểm, phụ kiện, khái niệm kỹ thuật...")
    print("=" * 70)
    freeform = section_freeform_entities(df, top_n=30)
    print(tabulate(freeform, headers="keys", tablefmt="github"))
    print()

    print("Done.")


if __name__ == "__main__":
    main()
