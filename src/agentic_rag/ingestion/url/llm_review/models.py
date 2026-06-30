"""Strict schemas for URL-local LLM artifact review."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class UrlLlmReviewEvidence(BaseModel):
    """One bounded evidence slice passed to the URL review LLM."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_id: str
    evidence_source: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class UrlLlmReviewInput(BaseModel):
    """Input for reviewing URL visual/dynamic artifacts with an LLM."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    task: str
    markdown: str = ""
    evidence: list[UrlLlmReviewEvidence] = Field(default_factory=list)
    current_metadata: dict[str, Any] = Field(default_factory=dict)


class UrlLlmReviewOutput(BaseModel):
    """Structured LLM output before deterministic validation."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    proposed_markdown: str = ""
    semantic_role: str = "generated_artifact"
    field_mapping: dict[str, str] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    needs_human_review: bool = True
    unvalidated_facts: list[str] = Field(default_factory=list)


__all__ = [
    "UrlLlmReviewEvidence",
    "UrlLlmReviewInput",
    "UrlLlmReviewOutput",
]
