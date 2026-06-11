"""Curated Knowledge Quality V2 case studies for deterministic demos and docs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agentic_rag.core.contracts import Chunk

RequiredMethod = Literal[
    "deterministic_v1",
    "metadata_rules",
    "semantic_rules",
    "semantic_verifier",
    "agentic_review",
]

CaseType = Literal[
    "exact_duplicate",
    "near_duplicate",
    "numeric",
    "temporal",
    "policy",
    "entity_relation",
    "causal",
    "exception",
    "recommendation",
    "equivalent_paraphrase",
    "metadata_supersession",
]

REQUIRED_METHODS: tuple[RequiredMethod, ...] = (
    "deterministic_v1",
    "metadata_rules",
    "semantic_rules",
    "semantic_verifier",
    "agentic_review",
)


class _CaseModel(BaseModel):
    """Frozen strict base config for knowledge-quality case studies."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class KnowledgeQualityCase(_CaseModel):
    """One curated sidecar case for knowledge-quality conflict detection."""

    case_id: str
    conflict_type: CaseType
    chunks: tuple[Chunk, ...]
    expected_methods: tuple[RequiredMethod, ...] = Field(default_factory=tuple)
    expected_conflict: bool
    notes: str


def _chunk(chunk_id: str, text: str, **metadata: object) -> Chunk:
    return Chunk(chunk_id=chunk_id, text=text, metadata=dict(metadata))


_QUALITY_CASE_CHUNKS: dict[str, tuple[Chunk, ...]] = {
    "exact_duplicate": (
        _chunk(
            "kqv2_exact_duplicate_a",
            "Pin VF 8 duoc bao hanh 8 nam hoac 160.000 km.",
            source="warranty-a.txt",
            document_id="kqv2_warranty_a",
        ),
        _chunk(
            "kqv2_exact_duplicate_b",
            "Pin VF 8 duoc bao hanh 8 nam hoac 160.000 km.",
            source="warranty-b.txt",
            document_id="kqv2_warranty_b",
        ),
    ),
    "near_duplicate": (
        _chunk(
            "kqv2_near_duplicate_a",
            "Pin VF 8 duoc bao hanh 8 nam hoac 160.000 km.",
            source="warranty-near-a.txt",
            document_id="kqv2_warranty_near_a",
        ),
        _chunk(
            "kqv2_near_duplicate_b",
            "Pin VF 8 duoc bao hanh 8 nam hoac 160000 kilomet.",
            source="warranty-near-b.txt",
            document_id="kqv2_warranty_near_b",
        ),
    ),
    "numeric": (
        _chunk(
            "kqv2_numeric_a",
            "VF 9 co gia niem yet 1,2 ty dong.",
            source="price-a.txt",
            document_id="kqv2_price_a",
        ),
        _chunk(
            "kqv2_numeric_b",
            "VF 9 co gia niem yet 1,5 ty dong.",
            source="price-b.txt",
            document_id="kqv2_price_b",
        ),
    ),
    "temporal": (
        _chunk(
            "kqv2_temporal_a",
            "VF 8 charging policy requires station charging.",
            source="policy-old.txt",
            document_id="kqv2_policy_old",
            entity="VF 8",
            attribute="charging_policy",
            value="station_only",
            version="1",
            published_at="2025-01-01",
            effective_date="2025-01-01",
        ),
        _chunk(
            "kqv2_temporal_b",
            "VF 8 charging policy permits home or station charging.",
            source="policy-new.txt",
            document_id="kqv2_policy_new",
            entity="VF 8",
            attribute="charging_policy",
            value="home_or_station",
            version="2",
            published_at="2026-01-01",
            effective_date="2026-01-01",
        ),
    ),
    "policy": (
        _chunk(
            "kqv2_policy_a",
            "Nguoi dung duoc phep tai ve tai lieu ngoai tuyen.",
            source="policy-allow.txt",
            document_id="kqv2_policy_allow",
        ),
        _chunk(
            "kqv2_policy_b",
            "Nguoi dung khong duoc tai ve tai lieu ngoai tuyen.",
            source="policy-deny.txt",
            document_id="kqv2_policy_deny",
        ),
    ),
    "entity_relation": (
        _chunk(
            "kqv2_entity_relation_a",
            "Tru so chinh cua VinFast nam tai Hai Phong.",
            source="org-a.txt",
            document_id="kqv2_org_a",
            entity="VinFast",
            attribute="headquarters",
            value="Hai Phong",
            effective_date="2026-01-01",
        ),
        _chunk(
            "kqv2_entity_relation_b",
            "Tru so chinh cua VinFast nam tai Ha Noi.",
            source="org-b.txt",
            document_id="kqv2_org_b",
            entity="VinFast",
            attribute="headquarters",
            value="Ha Noi",
            effective_date="2026-01-01",
        ),
    ),
    "causal": (
        _chunk(
            "kqv2_causal_a",
            "VF 8 battery degradation is caused by frequent fast charging.",
            source="cause-a.txt",
            document_id="kqv2_cause_a",
        ),
        _chunk(
            "kqv2_causal_b",
            "VF 8 battery degradation is not caused by frequent fast charging.",
            source="cause-b.txt",
            document_id="kqv2_cause_b",
        ),
    ),
    "exception": (
        _chunk(
            "kqv2_exception_a",
            "All vehicles, including demo vehicles, must register for periodic maintenance.",
            source="rule-a.txt",
            document_id="kqv2_rule_a",
        ),
        _chunk(
            "kqv2_exception_b",
            "Demo vehicles are exempt from periodic maintenance registration.",
            source="rule-b.txt",
            document_id="kqv2_rule_b",
        ),
    ),
    "recommendation": (
        _chunk(
            "kqv2_recommendation_a",
            "VF 8 owners should use fast charging every day.",
            source="recommend-a.txt",
            document_id="kqv2_recommend_a",
        ),
        _chunk(
            "kqv2_recommendation_b",
            "VF 8 owners should not use fast charging every day.",
            source="recommend-b.txt",
            document_id="kqv2_recommend_b",
        ),
    ),
    "equivalent_paraphrase": (
        _chunk(
            "kqv2_equivalent_paraphrase_a",
            "VF 8 has a maximum driving range of 400 km.",
            source="range-a.txt",
            document_id="kqv2_range_a",
        ),
        _chunk(
            "kqv2_equivalent_paraphrase_b",
            "A single charge lets the VinFast VF 8 travel as far as 400 kilometres.",
            source="range-b.txt",
            document_id="kqv2_range_b",
        ),
    ),
    "metadata_supersession": (
        _chunk(
            "kqv2_metadata_supersession_a",
            "Chinh sach cu van con duoc luu truu.",
            source="legacy-policy.txt",
            document_id="kqv2_legacy_policy",
            entity="VF 8",
            attribute="charging_policy",
            value="station_only",
            version="2025.01",
            effective_date="2025-01-01",
        ),
        _chunk(
            "kqv2_metadata_supersession_b",
            "Chinh sach moi da thay the chinh sach cu.",
            source="current-policy.txt",
            document_id="kqv2_current_policy",
            entity="VF 8",
            attribute="charging_policy",
            value="home_or_station",
            version="2026.01",
            effective_date="2026-01-01",
            supersedes="kqv2_legacy_policy",
        ),
    ),
}


def build_knowledge_quality_case_studies() -> tuple[KnowledgeQualityCase, ...]:
    """Return the curated stable case set in canonical order."""

    return (
        KnowledgeQualityCase(
            case_id="case_exact_duplicate_v1",
            conflict_type="exact_duplicate",
            chunks=_QUALITY_CASE_CHUNKS["exact_duplicate"],
            expected_methods=("deterministic_v1",),
            expected_conflict=True,
            notes="Exact duplicate chunks with matching wording and metadata shape.",
        ),
        KnowledgeQualityCase(
            case_id="case_near_duplicate_v1",
            conflict_type="near_duplicate",
            chunks=_QUALITY_CASE_CHUNKS["near_duplicate"],
            expected_methods=("deterministic_v1",),
            expected_conflict=True,
            notes="Near duplicate wording with the same underlying fact.",
        ),
        KnowledgeQualityCase(
            case_id="case_numeric_conflict_v1",
            conflict_type="numeric",
            chunks=_QUALITY_CASE_CHUNKS["numeric"],
            expected_methods=("deterministic_v1", "semantic_verifier"),
            expected_conflict=True,
            notes="Numeric pricing disagreement for the same product.",
        ),
        KnowledgeQualityCase(
            case_id="case_temporal_conflict_v1",
            conflict_type="temporal",
            chunks=_QUALITY_CASE_CHUNKS["temporal"],
            expected_methods=("metadata_rules", "semantic_verifier"),
            expected_conflict=True,
            notes="Older policy versus newer policy with effective dates in metadata.",
        ),
        KnowledgeQualityCase(
            case_id="case_policy_conflict_v1",
            conflict_type="policy",
            chunks=_QUALITY_CASE_CHUNKS["policy"],
            expected_methods=("semantic_rules", "semantic_verifier"),
            expected_conflict=True,
            notes="Allow versus forbid for the same action and context.",
        ),
        KnowledgeQualityCase(
            case_id="case_entity_relation_conflict_v1",
            conflict_type="entity_relation",
            chunks=_QUALITY_CASE_CHUNKS["entity_relation"],
            expected_methods=("metadata_rules", "semantic_verifier", "agentic_review"),
            expected_conflict=True,
            notes="Same entity with incompatible headquarters location claims.",
        ),
        KnowledgeQualityCase(
            case_id="case_causal_conflict_v1",
            conflict_type="causal",
            chunks=_QUALITY_CASE_CHUNKS["causal"],
            expected_methods=("semantic_verifier", "agentic_review"),
            expected_conflict=True,
            notes="Conflicting cause statements for the same battery symptom.",
        ),
        KnowledgeQualityCase(
            case_id="case_exception_conflict_v1",
            conflict_type="exception",
            chunks=_QUALITY_CASE_CHUNKS["exception"],
            expected_methods=("semantic_verifier", "agentic_review"),
            expected_conflict=True,
            notes="General rule contradicted by a documented exception.",
        ),
        KnowledgeQualityCase(
            case_id="case_recommendation_conflict_v1",
            conflict_type="recommendation",
            chunks=_QUALITY_CASE_CHUNKS["recommendation"],
            expected_methods=("semantic_rules", "semantic_verifier", "agentic_review"),
            expected_conflict=True,
            notes="Different charging recommendations for the same usage context.",
        ),
        KnowledgeQualityCase(
            case_id="case_equivalent_paraphrase_non_conflict_v1",
            conflict_type="equivalent_paraphrase",
            chunks=_QUALITY_CASE_CHUNKS["equivalent_paraphrase"],
            expected_methods=(
                "deterministic_v1",
                "semantic_rules",
                "semantic_verifier",
                "agentic_review",
            ),
            expected_conflict=False,
            notes="Paraphrased statements preserve the same meaning and polarity.",
        ),
        KnowledgeQualityCase(
            case_id="case_metadata_supersession_non_conflict_v1",
            conflict_type="metadata_supersession",
            chunks=_QUALITY_CASE_CHUNKS["metadata_supersession"],
            expected_methods=("metadata_rules", "semantic_verifier", "agentic_review"),
            expected_conflict=False,
            notes="A newer document metadata entry supersedes the older one cleanly.",
        ),
    )


def render_knowledge_quality_case_studies_markdown(
    cases: tuple[KnowledgeQualityCase, ...] | list[KnowledgeQualityCase],
) -> str:
    """Render the curated cases as a deterministic Markdown table."""

    rows = [
        "| case_id | conflict_type | expected_methods | expected_conflict | chunks | notes |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for case in cases:
        methods = ", ".join(case.expected_methods) or "-"
        chunks = ", ".join(chunk.chunk_id for chunk in case.chunks) or "-"
        rows.append(
            "| "
            f"{_escape_markdown_cell(case.case_id)} | "
            f"{_escape_markdown_cell(case.conflict_type)} | "
            f"{_escape_markdown_cell(methods)} | "
            f"{str(case.expected_conflict).lower()} | "
            f"{_escape_markdown_cell(chunks)} | "
            f"{_escape_markdown_cell(case.notes)} |"
        )
    return "\n".join(rows)


def _escape_markdown_cell(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>")
