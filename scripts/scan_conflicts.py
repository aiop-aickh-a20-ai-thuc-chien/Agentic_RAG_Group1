"""Scan ingested local chunks for knowledge-quality conflicts and index them in Neon.

Tách bạch với dedup: chỉ phát hiện MÂU THUẪN số liệu (warranty/price/distance) giữa
các chunk, KHÔNG đụng trùng lặp (dedup cascade lo). Chạy SAU dedup: bỏ chunk đã bị
đánh dấu trùng trước khi xét.

Dùng pass conflict gọn riêng (không gọi ``analyze_chunks``) để:
- bỏ hẳn bước near-duplicate O(n²) vốn bị vứt đi → nhanh hơn nhiều;
- không sinh hàng triệu "mâu thuẫn global" rồi mới lọc.
Bộ lọc nhiễu: bỏ thuộc tính ``date`` (regex bắt nhầm mọi số 4 chữ số), bỏ entity
"global" (không nhận ra xe cụ thể), và yêu cầu 2 câu chứa số phải cùng ngữ cảnh
(span Jaccard ≥ ngưỡng) — tránh ghép giá của 2 biến thể xe khác nhau.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from typing import Any

from dotenv import load_dotenv

from agentic_rag.autodata_eval import conflict_store
from agentic_rag.core.contracts import Chunk, KnowledgeQualityFact
from agentic_rag.generation.evidence import (
    configured_evidence_provider_name,
    source_provider_from_env,
)

# Tái dùng bộ trích fact đã được kiểm chứng của module knowledge_quality (regex
# entity VF*, chuẩn hoá năm→tháng, triệu/tỷ→VND...). Hàm private nhưng ổn định;
# import ở đây để khỏi viết lại ~100 dòng regex.
from agentic_rag.ingestion.knowledge_quality.detectors import _extract_facts
from agentic_rag.integrations.local_pdf.providers import LocalPdfEvidenceProvider
from agentic_rag.runtime_env import load_local_env

# Bỏ 'date' (nhiễu nhất). Giữ các thuộc tính số đáng tin.
_ALLOWED_ATTRIBUTES = {"warranty_duration", "duration", "price", "distance_km"}
# 2 câu chứa số phải đủ giống nhau mới coi là nói về cùng một việc.
_SPAN_JACCARD_MIN = 0.34
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scan local chunks for conflicts and index them in Neon.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Detect and print the summary without writing to Neon.",
    )
    args = parser.parse_args()

    load_dotenv()
    load_local_env()
    provider_name = configured_evidence_provider_name()
    provider = source_provider_from_env()
    if provider_name != "local_pdf" or not isinstance(provider, LocalPdfEvidenceProvider):
        raise SystemExit("Conflict scan is only supported when EVIDENCE_PROVIDER=local_pdf.")

    all_chunks = provider._cached_all_chunks(refresh=True)
    chunks = [c for c in all_chunks if not _is_dedup_flagged(c)]
    document_count = len(
        {c.metadata.get("document_id") for c in chunks if c.metadata.get("document_id")}
    )

    rows = _detect_conflict_rows(chunks)

    summary = {
        "dry_run": args.dry_run,
        "corpus_chunks": len(all_chunks),
        "chunks_after_dedup": len(chunks),
        "document_count": document_count,
        "conflict_rows": len(rows),
        "by_attribute": _count_by_attribute(rows),
    }

    if not args.dry_run:
        conflict_store.replace_all_findings(rows)
        conflict_store.upsert_corpus_stats(chunk_count=len(chunks), document_count=document_count)

    print(json.dumps(summary, ensure_ascii=False, indent=2))


def _detect_conflict_rows(chunks: list[Chunk]) -> list[dict[str, Any]]:
    chunk_by_id = {chunk.chunk_id: chunk for chunk in chunks}
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for (_entity_key, attribute, _unit), group in _group_facts(chunks).items():
        for left, right in _conflicting_pairs(group):
            pair = tuple(sorted([left.chunk_id, right.chunk_id]))
            key = (pair[0], pair[1], attribute)
            if key in seen:
                continue
            seen.add(key)
            rows.append(_build_row(attribute, left, right, chunk_by_id))
    return rows


def _group_facts(
    chunks: list[Chunk],
) -> dict[tuple[str, str, str | None], list[KnowledgeQualityFact]]:
    """Trích fact, bỏ entity 'global' + thuộc tính ngoài danh sách, gom theo nhóm so sánh."""
    groups: dict[tuple[str, str, str | None], list[KnowledgeQualityFact]] = defaultdict(list)
    for fact in _extract_facts(chunks):
        if fact.entity.strip().lower() == "global" or fact.attribute not in _ALLOWED_ATTRIBUTES:
            continue
        groups[(_normalize_entity(fact.entity), fact.attribute, fact.unit)].append(fact)
    return groups


def _conflicting_pairs(
    group: list[KnowledgeQualityFact],
) -> list[tuple[KnowledgeQualityFact, KnowledgeQualityFact]]:
    """Các cặp fact (khác chunk) có giá trị mâu thuẫn VÀ cùng ngữ cảnh (span đủ giống)."""
    pairs: list[tuple[KnowledgeQualityFact, KnowledgeQualityFact]] = []
    for index, left in enumerate(group):
        for right in group[index + 1 :]:
            if left.chunk_id == right.chunk_id:
                continue
            if not _values_conflict(left.normalized_value, right.normalized_value):
                continue
            if _jaccard(_tokens(left.span), _tokens(right.span)) < _SPAN_JACCARD_MIN:
                continue
            pairs.append((left, right))
    return pairs


def _build_row(
    attribute: str,
    left: KnowledgeQualityFact,
    right: KnowledgeQualityFact,
    chunk_by_id: dict[str, Chunk],
) -> dict[str, Any]:
    entity = left.entity
    finding_id = (
        "kq-"
        + hashlib.sha1(
            f"{entity}:{attribute}:{left.chunk_id}|{right.chunk_id}".encode()
        ).hexdigest()[:12]
    )
    row: dict[str, Any] = {
        "id": finding_id,
        "conflict_type": "numeric",
        "attribute": attribute,
        "entity": entity,
        "severity": "warning",
        "confidence": 0.95,
        "summary": f"{entity} mâu thuẫn {attribute}: {left.value} vs {right.value}.",
        "suggested_action": "Xem lại 2 nguồn; ưu tiên bản mới hoặc nguồn uy tín hơn.",
        "review_status": "pending",
    }
    row.update(_side_payload("left", left, chunk_by_id))
    row.update(_side_payload("right", right, chunk_by_id))
    return row


def _side_payload(
    side: str,
    fact: KnowledgeQualityFact,
    chunk_by_id: dict[str, Chunk],
) -> dict[str, Any]:
    chunk = chunk_by_id.get(fact.chunk_id)
    metadata = chunk.metadata if chunk is not None else {}
    return {
        f"{side}_chunk_id": fact.chunk_id,
        f"{side}_document_id": _text(metadata.get("document_id")),
        f"{side}_document_name": _text(metadata.get("document_name") or metadata.get("file_name")),
        f"{side}_source_type": _text(metadata.get("source_type")),
        f"{side}_source": _text(metadata.get("source") or metadata.get("url")),
        f"{side}_section": _text(metadata.get("section")),
        f"{side}_page": _text(metadata.get("page")),
        f"{side}_text": (chunk.text if chunk is not None else fact.span) or "",
        f"{side}_value": fact.value,
    }


def _count_by_attribute(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[str(row.get("attribute"))] += 1
    return dict(counts)


def _is_dedup_flagged(chunk: Chunk) -> bool:
    """True nếu chunk đã bị dedup đánh dấu trùng (có primary_layer)."""
    dedup = chunk.metadata.get("deduplication")
    return isinstance(dedup, dict) and bool(dedup.get("primary_layer"))


def _values_conflict(left: float | str, right: float | str) -> bool:
    if isinstance(left, float | int) and isinstance(right, float | int):
        tolerance = max(abs(float(left)), abs(float(right)), 1.0) * 0.01
        return abs(float(left) - float(right)) > tolerance
    return str(left) != str(right)


def _normalize(value: str) -> str:
    value = value.casefold().replace("đ", "d")
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", without_marks).split())


def _normalize_entity(value: str) -> str:
    return _normalize(value).replace(" ", "")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(_normalize(text)))


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


if __name__ == "__main__":
    main()
