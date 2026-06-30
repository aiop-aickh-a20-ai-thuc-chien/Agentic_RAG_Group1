"""Strict contracts for multi-strategy URL ingestion."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from agentic_rag.ingestion.chunking import ChunkingInput

UrlStage = Literal["acquisition", "dom", "layout", "interaction", "vision", "structuring"]
EvidenceKind = Literal[
    "raw_html",
    "rendered_html",
    "dom_region",
    "json_state",
    "network_payload",
    "screenshot",
    "image",
    "table",
    "chart",
    "vlm_response",
]
EvidenceOrigin = Literal["source_backed", "visually_inferred", "generated_review"]
ValidationStatus = Literal["validated", "unvalidated", "rejected"]
RunStatus = Literal["complete", "partial", "failed", "routed_to_pdf"]


class _IntegrationModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class UrlStrategyCapabilities(_IntegrationModel):
    stage: UrlStage
    strategy: str
    supports_static_html: bool = False
    supports_rendered_html: bool = False
    supports_network_payloads: bool = False
    supports_interactions: bool = False
    supports_tables: bool = False
    supports_images: bool = False
    supports_charts: bool = False
    supports_state_provenance: bool = False
    supports_reading_order: bool = False
    supports_structured_output: bool = False
    requires_browser: bool = False
    requires_network: bool = False
    requires_credentials: bool = False
    estimated_cost_class: Literal["low", "medium", "high"] = "low"
    latency_class: Literal["low", "medium", "high"] = "low"


class UrlIntegrationInput(_IntegrationModel):
    requested_url: str
    html: str | None = None
    page_profile: str | None = None
    allowed_strategies: tuple[str, ...] = ()
    expected_entity: str | None = None
    include_interactions: bool = False
    max_states: int = Field(default=30, gt=0)
    max_sections: int = Field(default=100, gt=0)
    timeout_seconds: int = Field(default=45, gt=0)
    artifact_budget: int = Field(default=100, gt=0)
    vlm_region_budget: int = Field(default=8, ge=0)


class UrlEvidenceRef(_IntegrationModel):
    evidence_id: str
    kind: EvidenceKind
    artifact_ref: str
    strategy: str
    origin: EvidenceOrigin = "source_backed"
    selector: str | None = None
    dom_path: str | None = None
    state_path: str | None = None
    section_id: str | None = None
    state_id: str | None = None
    bounding_box: tuple[int, int, int, int] | None = None
    content_hash: str | None = None
    captured_at: str | None = None


class UrlEvidenceFact(_IntegrationModel):
    subject: str
    attribute: str
    value: str
    unit: str | None = None
    relation: str | None = None
    section_id: str | None = None
    state_id: str | None = None
    scope_path: str | None = None
    evidence_refs: tuple[str, ...]
    extraction_strategy: str
    confidence: float = Field(ge=0.0, le=1.0)
    validation_status: ValidationStatus = "unvalidated"
    origin: EvidenceOrigin = "source_backed"


class UrlStructuredSection(_IntegrationModel):
    section_id: str
    heading: str | None = None
    markdown: str
    reading_order: int = Field(ge=0)
    evidence_refs: tuple[str, ...]
    state_id: str | None = None
    scope_path: str | None = None


class UrlConflictCandidate(_IntegrationModel):
    subject: str
    attribute: str
    values: tuple[str, ...]
    fact_indexes: tuple[int, ...]
    reason: str


class UrlStrategyTrace(_IntegrationModel):
    stage: UrlStage
    strategy: str
    status: Literal["selected", "skipped", "failed"]
    reason: str
    duration_ms: int = Field(default=0, ge=0)
    input_evidence_ids: tuple[str, ...] = ()
    output_evidence_ids: tuple[str, ...] = ()
    error: str | None = None


class UrlAcquisitionResult(_IntegrationModel):
    requested_url: str
    final_url: str
    raw_html: str | None = None
    rendered_html: str | None = None
    framework_state: dict[str, Any] = Field(default_factory=dict)
    network_payload_refs: tuple[str, ...] = ()
    evidence: tuple[UrlEvidenceRef, ...] = ()
    parser_markdown: str | None = None
    parser_name: str | None = None


class UrlStrategyOutput(_IntegrationModel):
    strategy: str
    markdown: str = ""
    sections: tuple[UrlStructuredSection, ...] = ()
    facts: tuple[UrlEvidenceFact, ...] = ()
    evidence: tuple[UrlEvidenceRef, ...] = ()
    unresolved_gaps: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    metadata: dict[str, Any] = Field(default_factory=dict)


class UrlValidatedPayload(_IntegrationModel):
    requested_url: str
    final_url: str
    canonical_url: str | None = None
    sections: tuple[UrlStructuredSection, ...] = ()
    facts: tuple[UrlEvidenceFact, ...] = ()
    evidence: tuple[UrlEvidenceRef, ...] = ()
    conflicts: tuple[UrlConflictCandidate, ...] = ()
    unresolved_gaps: tuple[str, ...] = ()
    rejected_claims: tuple[UrlEvidenceFact, ...] = ()
    strategy_trace: tuple[UrlStrategyTrace, ...] = ()
    warnings: tuple[str, ...] = ()


class UrlIntegrationResult(_IntegrationModel):
    status: RunStatus
    payload: UrlValidatedPayload
    chunking_input: ChunkingInput | None = None
    pdf_handoff_url: str | None = None

