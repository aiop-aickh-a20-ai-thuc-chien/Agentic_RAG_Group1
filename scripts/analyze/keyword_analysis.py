"""Keyword Analysis — phân tích keywords LLM-extracted trong corpus.

Chạy:
    uv run python scripts/analyze/keyword_analysis.py

Sections:
  1. Frequency distribution — keyword nào phổ biến nhất
  2. Per-chunk count — mỗi chunk có bao nhiêu keyword
  3. Overlap with chunk text — keyword nào đã có trong text, cái nào "mới"
  4. By document_type — keyword phân bố theo loại tài liệu
  5. Unique keywords — keyword chỉ xuất hiện trong 1 chunk (rất đặc thù)
"""

from __future__ import annotations

import os
import re
import sys
from collections import Counter

import pandas as pd
from dotenv import load_dotenv
from tabulate import tabulate

sys.stdout.reconfigure(encoding="utf-8")
load_dotenv()

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
              metadata->'keywords'        AS keywords,
              text                        AS text
            FROM local_rag_chunks
            WHERE metadata->'keywords' IS NOT NULL
            """
        ).fetchall()
    return pd.DataFrame(rows, columns=["chunk_id", "document_type", "keywords", "text"])


# ---------------------------------------------------------------------------
# Section 1 — Frequency
# ---------------------------------------------------------------------------
def section_frequency(df: pd.DataFrame, top_n: int = 60) -> list[dict]:
    counter: Counter[str] = Counter()
    for kws in df["keywords"]:
        if kws:
            for k in kws:
                counter[str(k).strip().lower()] += 1
    total_chunks = len(df)
    return [
        {"keyword": k, "count": c, "in_pct_chunks": f"{100 * c / total_chunks:.1f}%"}
        for k, c in counter.most_common(top_n)
    ]


# ---------------------------------------------------------------------------
# Section 2 — Per-chunk count
# ---------------------------------------------------------------------------
def section_per_chunk_count(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["n_kw"] = df["keywords"].apply(lambda x: len(x) if x else 0)
    dist = df["n_kw"].value_counts().sort_index().reset_index()
    dist.columns = ["n_keywords", "chunks"]
    dist["pct"] = (dist["chunks"] / len(df) * 100).round(1).astype(str) + "%"
    return dist


# ---------------------------------------------------------------------------
# Section 3 — Overlap: keyword in chunk text vs "new information"
# ---------------------------------------------------------------------------
def section_overlap(df: pd.DataFrame) -> dict:
    in_text = 0
    not_in_text = 0
    new_keywords: Counter[str] = Counter()

    for _, row in df.iterrows():
        if not row["keywords"] or not row["text"]:
            continue
        text_lower = str(row["text"]).lower()
        for kw in row["keywords"]:
            kw_str = str(kw).strip()
            if kw_str.lower() in text_lower:
                in_text += 1
            else:
                not_in_text += 1
                new_keywords[kw_str.lower()] += 1

    total = in_text + not_in_text
    return {
        "total_keyword_occurrences": total,
        "already_in_text": in_text,
        "new_info_not_in_text": not_in_text,
        "pct_new": f"{100 * not_in_text / total:.1f}%" if total else "0%",
        "top_new_keywords": [{"keyword": k, "count": c} for k, c in new_keywords.most_common(20)],
    }


# ---------------------------------------------------------------------------
# Section 4 — By document_type
# ---------------------------------------------------------------------------
def section_by_doctype(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for dtype, group in df.groupby("document_type", dropna=False):
        all_kws: list[str] = []
        for kws in group["keywords"]:
            if kws:
                all_kws.extend(str(k).strip().lower() for k in kws)
        top3 = ", ".join(k for k, _ in Counter(all_kws).most_common(3))
        rows.append(
            {
                "document_type": dtype or "None",
                "chunks": len(group),
                "avg_keywords": round(len(all_kws) / max(1, len(group)), 1),
                "top_3_keywords": top3,
            }
        )
    return pd.DataFrame(rows).sort_values("chunks", ascending=False)


# ---------------------------------------------------------------------------
# Section 5 — Unique keywords (appear in only 1 chunk)
# ---------------------------------------------------------------------------
def section_unique_keywords(df: pd.DataFrame, sample: int = 30) -> tuple[int, list[str]]:
    counter: Counter[str] = Counter()
    for kws in df["keywords"]:
        if kws:
            for k in kws:
                counter[str(k).strip().lower()] += 1
    unique_all = [k for k, c in counter.items() if c == 1]
    return len(unique_all), unique_all[:sample]


def section_summary_stats(df: pd.DataFrame) -> dict:
    """Tổng hợp số liệu toàn corpus."""
    counter: Counter[str] = Counter()
    for kws in df["keywords"]:
        if kws:
            for k in kws:
                counter[str(k).strip().lower()] += 1
    total_occurrences = sum(counter.values())
    return {
        "total_chunks": len(df),
        "chunks_with_keywords": int(df["keywords"].apply(bool).sum()),
        "total_keyword_occurrences": total_occurrences,
        "distinct_keywords": len(counter),
        "keywords_appearing_once": sum(1 for c in counter.values() if c == 1),
        "keywords_appearing_2_to_5": sum(1 for c in counter.values() if 2 <= c <= 5),
        "keywords_appearing_6_plus": sum(1 for c in counter.values() if c >= 6),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    print("Loading data from Neon...")
    df = _load_data()
    print(f"Loaded {len(df):,} chunks with keywords\n")

    # --- 0. Summary stats ---
    print("=" * 70)
    print("SECTION 0 — Corpus summary statistics")
    print("=" * 70)
    stats = section_summary_stats(df)
    for k, v in stats.items():
        print(f"  {k:<40} {v:,}")
    print()

    # --- 1. Frequency ---
    print("=" * 70)
    print("SECTION 1 — Top 60 most frequent keywords")
    print("=" * 70)
    freq = section_frequency(df, top_n=60)
    print(tabulate(freq, headers="keys", tablefmt="github"))
    print()

    # --- 2. Per-chunk count ---
    print("=" * 70)
    print("SECTION 2 — Keyword count per chunk")
    print("=" * 70)
    dist = section_per_chunk_count(df)
    print(tabulate(dist.to_dict("records"), headers="keys", tablefmt="github"))
    avg = df["keywords"].apply(lambda x: len(x) if x else 0).mean()
    print(f"\n  avg keywords/chunk = {avg:.2f}")
    print()

    # --- 3. Overlap ---
    print("=" * 70)
    print("SECTION 3 — Keyword overlap with chunk text")
    print("  'new info' = keyword NOT found literally in chunk text")
    print("  → đây là keywords THÊM GIÁ TRỊ cho BM25 augmentation")
    print("=" * 70)
    overlap = section_overlap(df)
    print(f"  Total keyword occurrences : {overlap['total_keyword_occurrences']:,}")
    print(f"  Already in chunk text     : {overlap['already_in_text']:,}")
    print(
        f"  New info (not in text)    : {overlap['new_info_not_in_text']:,}  ({overlap['pct_new']})"
    )
    print()
    print("  Top 20 keywords that add NEW information (not literally in text):")
    print(tabulate(overlap["top_new_keywords"], headers="keys", tablefmt="github"))
    print()

    # --- 4. By doc type ---
    print("=" * 70)
    print("SECTION 4 — Keywords by document_type")
    print("=" * 70)
    doctype_df = section_by_doctype(df)
    print(tabulate(doctype_df.to_dict("records"), headers="keys", tablefmt="github"))
    print()

    # --- 5. Unique keywords ---
    print("=" * 70)
    print("SECTION 5 — Unique keywords (appear in exactly 1 chunk)")
    print("  → rất đặc thù, ít hữu ích cho filtering nhưng tốt cho BM25 recall")
    print("=" * 70)
    total_uniq, uniq_sample = section_unique_keywords(df, sample=30)
    print(f"  Total unique keywords (count=1): {total_uniq:,}  (showing first 30)")
    for i, k in enumerate(uniq_sample, 1):
        print(f"  {i:>3}. {k}")
    print()

    print("Done.")


if __name__ == "__main__":
    main()
