"""Build an entity canonicalization map: lexical clustering + LLM per cluster.

PHASE 1 of entity normalization. READ-ONLY w.r.t. the stores: reads the distinct
``entities`` strings from Neon, groups variants with cheap lexical clustering,
then asks the LLM to canonicalize WITHIN each cluster, and writes a static
``entity_map.json``. It NEVER mutates Neon or Qdrant.

Pipeline (standard entity-resolution shape: Blocking -> Matching -> Clustering):

    1. BLOCKING (swappable seam ``build_candidate_graph``): TF-IDF char n-gram
       cosine >= threshold. Groups surface-form variants by shared characters.
       At large scale, swap this one function for MinHash-LSH (datasketch) — the
       rest is unchanged.
    2. CLUSTER: connected components (single-linkage) on the similarity graph.
       HIGH RECALL on purpose: over-grouping is harmless (the LLM splits within a
       cluster); under-grouping is the only real risk, so we group generously.
    3. MATCHING (LLM per cluster, run in parallel): the LLM sees a whole cluster
       and assigns each member its canonical + type. Because the digit signal
       ("VF 8" vs "VF 3") is decided by the LLM — not by string similarity — the
       clustering's inability to tell digits apart does not matter.

Variants of one entity land in the SAME cluster -> SAME LLM call -> consistent
canonical (no cross-batch divergence like "EVO GRAND" vs "Evo Grand").

Run (inspect clusters only — tune --threshold cheaply, NO LLM):
    uv run python scripts/build_entity_map.py --inspect-clusters

Run (full build):
    uv run python scripts/build_entity_map.py

Run (incremental — only NEW strings not already in the map):
    uv run python scripts/build_entity_map.py --incremental
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

# Canonical output lives inside the package so it ships and is importable.
DEFAULT_OUTPUT = Path("src/agentic_rag/ingestion/metadata/entity_map.json")

# Entity types. Only the *_model and location types are useful for hard-filter;
# brand/generic are recorded so the runtime knows NOT to filter on them.
ENTITY_TYPES = (
    "car_model",
    "ebike_model",
    "location",
    "brand",
    "accessory",
    "contact",
    "generic",
    "other",
)
FILTERABLE_TYPES = ("car_model", "ebike_model", "location")

# A cluster larger than this is sub-chunked before going to the LLM (keeps the
# call bounded). Safe to split: each member maps to its own model independently,
# so splitting an accessory mega-cluster cannot cause canonical divergence.
MAX_GROUP = 60

SYSTEM_MESSAGE = (
    "Bạn là bộ chuẩn hóa thực thể (entity canonicalization) cho hệ thống RAG "
    "tiếng Việt về xe điện VinFast. Chỉ trả về DUY NHẤT một JSON array đúng "
    "schema, không giải thích, không markdown, không code fence."
)


class EntityMapping(BaseModel):
    """One canonical mapping produced by the LLM."""

    model_config = ConfigDict(extra="ignore")

    raw: str
    canonical: str = ""
    type: str = "other"

    @field_validator("raw", "canonical", mode="before")
    @classmethod
    def _strip(cls, value: object) -> str:
        return str(value or "").strip()

    @field_validator("type", mode="before")
    @classmethod
    def _coerce_type(cls, value: object) -> str:
        candidate = str(value or "").strip().lower()
        return candidate if candidate in ENTITY_TYPES else "other"


def _conn() -> str:
    raw = os.getenv("LOCAL_SOURCE_POSTGRES_CONNECTION", "").strip()
    if not raw:
        raise SystemExit("LOCAL_SOURCE_POSTGRES_CONNECTION is not set.")
    return re.sub(r"^postgresql\+psycopg://", "postgresql://", raw)


def load_entities() -> Counter[str]:
    """Read all entity strings from Neon with their occurrence counts."""
    import psycopg

    counter: Counter[str] = Counter()
    with psycopg.connect(_conn()) as conn:
        rows = conn.execute(
            "SELECT metadata->'entities' FROM local_rag_chunks "
            "WHERE metadata->'entities' IS NOT NULL"
        ).fetchall()
    for (entities,) in rows:
        if not entities:
            continue
        for ent in entities:
            text = str(ent).strip()
            if text:
                counter[text] += 1
    return counter


# --------------------------------------------------------------------------
# BLOCKING + CLUSTERING (swappable seam)
# --------------------------------------------------------------------------
def build_candidate_graph(strings: list[str], threshold: float):
    """Return connected-component labels for the strings (lexical clustering).

    THE SWAPPABLE SEAM. TF-IDF char n-gram cosine >= threshold -> single-linkage
    connected components. Full O(n^2) cosine is fine up to ~50k strings; beyond
    that, replace the body with MinHash-LSH candidate generation — same return.
    """
    import numpy as np
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import connected_components
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
    matrix = vectorizer.fit_transform(strings)
    similarity = cosine_similarity(matrix)
    adjacency = similarity >= threshold
    np.fill_diagonal(adjacency, False)
    _, labels = connected_components(csr_matrix(adjacency), directed=False)
    return labels


def cluster_entities(entities: list[tuple[str, int]], threshold: float) -> list[list[int]]:
    """Group entity indices into clusters by lexical similarity."""
    strings = [raw for raw, _ in entities]
    labels = build_candidate_graph(strings, threshold)
    clusters: dict[int, list[int]] = {}
    for index, label in enumerate(labels):
        clusters.setdefault(int(label), []).append(index)
    return list(clusters.values())


# --------------------------------------------------------------------------
# MATCHING (LLM per group)
# --------------------------------------------------------------------------
def build_prompt(group: list[tuple[str, int]]) -> str:
    """Render the canonicalization prompt for one group of (entity, count)."""
    types = "|".join(ENTITY_TYPES)
    items = [{"raw": raw, "count": count} for raw, count in group]
    lines = [
        "<task>",
        "Các chuỗi sau CÓ THỂ là biến thể của cùng một thực thể, hoặc là các thực",
        "thể KHÁC nhau. Với MỖI chuỗi, trả về dạng chuẩn (canonical) + type.",
        "</task>",
        "",
        "<rules>",
        "- GIỮ NGUYÊN chữ số model: 'VF 8' và 'VF 3' là HAI thực thể khác nhau.",
        "- Bỏ tiền tố thương hiệu thừa: 'VinFast VF 8' -> 'VF 8'.",
        "- Chuẩn hóa khoảng trắng/hoa thường: 'VF8','EVO GRAND' -> 'VF 8','Evo Grand'.",
        "- Phụ kiện kèm tên xe -> canonical là MODEL: 'Thảm Cốp 3D VF 7' -> 'VF 7' (car_model).",
        "- Phiên bản/trim -> gộp model gốc: 'VF 8 Plus','VF 8 Eco' -> 'VF 8'.",
        "- Xe máy điện gộp về dòng chính: 'Theon' -> 'Theon S'.",
        "- Địa điểm chuẩn hóa: 'TP. HCM','TP Hồ Chí Minh' -> 'Hồ Chí Minh' (location).",
        "- Quá chung chung ('VinFast','xe điện','pin') -> GIỮ NGUYÊN, type=brand/generic.",
        "- Dùng count làm gợi ý: dạng phổ biến hơn thường là canonical.",
        "</rules>",
        "",
        f"<types>{types}</types>",
        "",
        "<input>",
        json.dumps(items, ensure_ascii=False),
        "</input>",
        "",
        "<output_schema>",
        "Trả về DUY NHẤT một JSON array, mỗi candidate đúng một phần tử:",
        f'{{"raw":"<nguyên văn>","canonical":"<dạng chuẩn>","type":"<một trong: {types}>"}}',
        "Số phần tử PHẢI bằng số input, giữ nguyên field raw.",
        "</output_schema>",
    ]
    return "\n".join(lines)


def _extract_json_array(text: str) -> list[dict] | None:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    candidates = [stripped]
    first = stripped.find("[")
    last = stripped.rfind("]")
    if first >= 0 and last > first:
        candidates.append(stripped[first : last + 1])
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, list):
            return payload
    return None


def canonicalize_group(group: list[tuple[str, int]], *, client) -> list[EntityMapping]:
    """One LLM call for one group; identity fallback for dropped/invalid items."""
    from agentic_rag.core.contracts import LLMCompletionInput
    from agentic_rag.model_runtime.errors import ModelInvocationError

    request = LLMCompletionInput(
        prompt=build_prompt(group),
        system_message=SYSTEM_MESSAGE,
        temperature=0.0,
    )
    parsed: list[dict] | None = None
    for attempt in range(1, 4):
        try:
            response = client.complete(request)
            parsed = _extract_json_array(response.text)
            if parsed is not None:
                break
        except ModelInvocationError:
            pass
        time.sleep(2.0 * attempt)

    by_raw: dict[str, EntityMapping] = {}
    for item in parsed or []:
        if not isinstance(item, dict):
            continue
        try:
            mapping = EntityMapping.model_validate(item)
        except ValidationError:
            continue
        if mapping.raw:
            by_raw[mapping.raw] = mapping

    result: list[EntityMapping] = []
    for raw, _count in group:
        mapping = by_raw.get(raw)
        if mapping is None or not mapping.canonical:
            result.append(EntityMapping(raw=raw, canonical=raw, type="other"))
        else:
            result.append(mapping)
    return result


def form_groups(
    clusters: list[list[int]], entities: list[tuple[str, int]], batch_size: int
) -> list[list[tuple[str, int]]]:
    """Turn clusters into LLM call-groups.

    Multi-member clusters become groups (sub-chunked if larger than MAX_GROUP);
    singletons are pooled and chunked into batches (they have no variants
    elsewhere, so batching them cannot cause canonical divergence).
    """
    groups: list[list[tuple[str, int]]] = []
    singletons: list[tuple[str, int]] = []
    for cluster in clusters:
        if len(cluster) == 1:
            singletons.append(entities[cluster[0]])
            continue
        members = [entities[i] for i in cluster]
        for start in range(0, len(members), MAX_GROUP):
            groups.append(members[start : start + MAX_GROUP])
    for start in range(0, len(singletons), batch_size):
        groups.append(singletons[start : start + batch_size])
    return groups


# --------------------------------------------------------------------------
# Inspect / output
# --------------------------------------------------------------------------
def inspect_clusters(clusters: list[list[int]], entities: list[tuple[str, int]]) -> None:
    sizes = sorted((len(c) for c in clusters), reverse=True)
    multi = [c for c in clusters if len(c) > 1]
    singles = sum(1 for c in clusters if len(c) == 1)
    print(f"  total clusters    : {len(clusters):,}")
    print(f"  multi-member      : {len(multi):,}")
    print(f"  singletons        : {singles:,}")
    print(f"  largest cluster   : {sizes[0] if sizes else 0}")
    buckets = Counter(
        "1" if s == 1 else "2-5" if s <= 5 else "6-20" if s <= 20 else "21+" for s in sizes
    )
    print(f"  size distribution : {dict(buckets)}")
    print("\n  Top 15 biggest clusters:")
    for cluster in sorted(multi, key=len, reverse=True)[:15]:
        members = sorted(entities[i][0] for i in cluster)
        sample = ", ".join(members[:8])
        more = "" if len(members) <= 8 else f" (+{len(members) - 8})"
        print(f"    [{len(cluster):>3}] {sample}{more}")


def consolidate_types(entity_map: dict[str, dict]) -> int:
    """Give every variant of a canonical ONE type (in place). Returns #changed.

    The LLM assigns type per cluster, so the same canonical can end up with
    different types across its variants (e.g. "VF 8" as car_model, but
    "Thảm Cốp 3D VF 8" as accessory). That makes accessory-named variants
    non-filterable, so a chunk mentioning only the accessory is missed by the
    "VF 8" filter. We pick one type per canonical — preferring a filterable type
    when ANY variant has it — so all variants of a model become filterable.
    """
    type_counts: dict[str, Counter[str]] = {}
    for entry in entity_map.values():
        type_counts.setdefault(entry["canonical"], Counter())[entry["type"]] += 1

    chosen: dict[str, str] = {}
    for canonical, counts in type_counts.items():
        pick = next((t for t in FILTERABLE_TYPES if t in counts), None)
        chosen[canonical] = pick or counts.most_common(1)[0][0]

    changed = 0
    for entry in entity_map.values():
        target = chosen[entry["canonical"]]
        if entry["type"] != target:
            entry["type"] = target
            changed += 1
    return changed


def _write_output(output: Path, entity_map: dict[str, dict]) -> dict[str, list[str]]:
    consolidate_types(entity_map)
    groups: dict[str, list[str]] = {}
    for raw, entry in entity_map.items():
        groups.setdefault(entry["canonical"], []).append(raw)
    payload = {
        "version": "entity-map-v3",
        "source": "lexical-cluster + llm-canonicalization",
        "stats": {
            "raw_strings": len(entity_map),
            "canonical_entities": len(groups),
            "filterable_types": list(FILTERABLE_TYPES),
        },
        "map": dict(sorted(entity_map.items())),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return groups


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build entity_map.json via lexical clustering + LLM."
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.4,
        help="Cosine threshold for clustering (lower = group more).",
    )
    parser.add_argument("--batch-size", type=int, default=60, help="Singletons per LLM call.")
    parser.add_argument("--concurrency", type=int, default=6, help="Parallel LLM calls.")
    parser.add_argument(
        "--limit", type=int, default=None, help="Process at most N distinct entities."
    )
    parser.add_argument(
        "--incremental", action="store_true", help="Only map strings not already in the output map."
    )
    parser.add_argument(
        "--inspect-clusters",
        action="store_true",
        help="Cluster + print distribution; NO LLM, no write.",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Count entities only; no clustering, no LLM."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    load_dotenv()
    try:
        from agentic_rag.runtime_env import load_local_env

        load_local_env()
    except Exception:
        pass

    counter = load_entities()
    print(f"Distinct entities in Neon: {len(counter):,}")

    existing: dict[str, dict] = {}
    if args.incremental and args.output.exists():
        existing = json.loads(args.output.read_text(encoding="utf-8")).get("map", {})
        print(f"Existing map entries: {len(existing):,} (incremental)")

    entities = [(raw, count) for raw, count in counter.most_common() if raw not in existing]
    if args.limit is not None:
        entities = entities[: args.limit]
    print(f"To process: {len(entities):,}")

    if args.dry_run:
        print("[dry-run] stopping before clustering.")
        return
    if not entities:
        print("Nothing to do.")
        return

    print(f"\nClustering (threshold={args.threshold}) ...")
    clusters = cluster_entities(entities, args.threshold)
    inspect_clusters(clusters, entities)

    if args.inspect_clusters:
        print("\n[inspect-clusters] stopping before any LLM call.")
        return

    from agentic_rag.model_runtime.factory import get_llm_client

    client = get_llm_client("ingestion")
    if client is None:
        raise SystemExit("No ingestion LLM configured (INGESTION_LLM_* / LLM_*).")

    groups = form_groups(clusters, entities, args.batch_size)
    print(f"\nCanonicalizing {len(groups)} groups with {args.concurrency} workers ...")
    entity_map: dict[str, dict] = dict(existing)
    started = time.perf_counter()
    done = 0
    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as pool:
        futures = {pool.submit(canonicalize_group, g, client=client): g for g in groups}
        for future in as_completed(futures):
            done += 1
            for mapping in future.result():
                entity_map[mapping.raw] = {"canonical": mapping.canonical, "type": mapping.type}
            print(f"  group {done}/{len(groups)} done")

    canonical_groups = _write_output(args.output, entity_map)
    elapsed = round(time.perf_counter() - started, 1)
    print(f"\nWrote {args.output}")
    print(f"  raw strings       : {len(entity_map):,}")
    print(f"  canonical entities: {len(canonical_groups):,}")
    print(f"  elapsed           : {elapsed}s")

    print("\nTop canonical entities by #variants:")
    top = sorted(canonical_groups.items(), key=lambda kv: -len(kv[1]))[:20]
    for canonical, variants in top:
        sample = ", ".join(sorted(variants)[:6])
        more = "" if len(variants) <= 6 else f" (+{len(variants) - 6})"
        print(f"  {canonical!r:28} <- {len(variants):>3}: {sample}{more}")


if __name__ == "__main__":
    main()
