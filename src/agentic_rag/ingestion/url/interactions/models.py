"""Contracts for rule-based URL interaction capture."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Availability = Literal["available", "disabled", "unknown"]
EvidenceSource = Literal["dom", "network", "dom+network", "unknown"]
PriceSource = Literal["dom", "network", "json_state", "mixed", "not_visible", "unknown"]


class InteractionOptions(BaseModel):
    """Runtime limits for deterministic UI interaction capture."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_states: int = Field(default=30, gt=0)
    timeout_seconds: int = Field(default=45, gt=0)
    wait_until: Literal["domcontentloaded", "load", "networkidle"] = "networkidle"
    settle_after_click_ms: int = Field(default=500, ge=0)
    capture_screenshots: bool = False


class InteractionProfile(BaseModel):
    """Static signals that identify whether a page needs UI-state capture."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    requested_url: str
    final_url: str | None = None
    page_type: str
    interaction_required: bool
    reasons: list[str] = Field(default_factory=list)
    url_query_params: dict[str, str] = Field(default_factory=dict)
    model_id: str | None = None


class InteractionControl(BaseModel):
    """A safe option-like UI control discovered on a rendered page or HTML fixture."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    control_id: str
    label: str
    group: str
    selector: str | None = None
    disabled: bool = False
    attributes: dict[str, str] = Field(default_factory=dict)
    skipped_reason: str | None = None


class InteractionStateRecord(BaseModel):
    """One captured product/configurator state backed by DOM or network evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    state_id: str
    requested_url: str
    final_url: str | None = None
    model_id: str | None = None
    model_name: str | None = None
    option_group: str
    option_label: str
    variant_options: dict[str, str] = Field(default_factory=dict)
    price: str | None = None
    currency: str | None = None
    price_source: PriceSource = "unknown"
    image_url: str | None = None
    availability: Availability = "unknown"
    evidence_source: EvidenceSource = "unknown"
    captured_at: str
    dom_evidence: dict[str, str] = Field(default_factory=dict)
    network_evidence: dict[str, str] = Field(default_factory=dict)

    def to_chunk_text(self) -> str:
        """Render a retrieval-friendly sentence for the captured state."""

        parts: list[str] = []
        product_name = self.model_name or self.model_id or "Unknown product"
        parts.append(str(product_name))
        if self.option_group != "default" or self.option_label != "default":
            parts.append(f"{self.option_group}: {self.option_label}")
        if self.price:
            parts.append(f"price: {self.price}")
        if self.image_url:
            parts.append(f"image: {self.image_url}")
        if self.availability != "unknown":
            parts.append(f"availability: {self.availability}")
        return " - ".join(parts)

    def to_metadata_summary(self) -> dict[str, object]:
        """Return compact metadata safe to duplicate across chunks."""

        return {
            "state_id": self.state_id,
            "model_id": self.model_id,
            "model_name": self.model_name,
            "option_group": self.option_group,
            "option_label": self.option_label,
            "variant_options": self.variant_options,
            "price": self.price,
            "currency": self.currency,
            "image_url": self.image_url,
            "availability": self.availability,
            "evidence_source": self.evidence_source,
        }


class InteractionCaptureResult(BaseModel):
    """Output from rule-based interaction capture."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    profile: InteractionProfile
    states: list[InteractionStateRecord] = Field(default_factory=list)
    controls: list[InteractionControl] = Field(default_factory=list)
    skipped_controls: list[InteractionControl] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    source_html: str | None = None
    network_payloads: list[dict[str, object]] = Field(default_factory=list)


class InteractionArtifacts(BaseModel):
    """Paths for persisted rule-based interaction artifacts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_dir: Path
    states_path: Path
    chunks_path: Path
    manifest_path: Path
    source_html_path: Path | None = None
    image_snapshots_path: Path | None = None
    network_payloads_path: Path | None = None
