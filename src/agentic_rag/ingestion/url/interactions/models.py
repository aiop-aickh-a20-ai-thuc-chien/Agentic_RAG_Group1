"""Contracts for rule-based URL interaction capture."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Availability = Literal["available", "disabled", "unknown"]
EvidenceSource = Literal["dom", "network", "dom+network", "unknown"]
PanelRole = Literal["left_panel", "center_visual", "right_panel", "unknown"]
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
    panel_role: PanelRole = "unknown"
    panel_id: str | None = None
    disabled: bool = False
    attributes: dict[str, str] = Field(default_factory=dict)
    skipped_reason: str | None = None


class InteractionPanelSnapshot(BaseModel):
    """One bounded panel snapshot before or after an interaction."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    snapshot_id: str
    panel_role: PanelRole
    panel_id: str
    interaction_step: str
    captured_at: str
    source_control_id: str | None = None
    text: str = ""
    text_hash: str | None = None
    price_values: list[str] = Field(default_factory=list)
    specifications: dict[str, str] = Field(default_factory=dict)
    image_urls: list[str] = Field(default_factory=list)
    table_count: int = Field(default=0, ge=0)
    node_signatures: list[str] = Field(default_factory=list)
    screenshot_path: str | None = None


class InteractionPanelDiff(BaseModel):
    """Source-backed before/after changes for one clicked control."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    diff_id: str
    source_control_id: str
    control_label: str
    control_group: str
    changed_panels: list[PanelRole] = Field(default_factory=list)
    changed_fields: list[str] = Field(default_factory=list)
    before_snapshot_refs: list[str] = Field(default_factory=list)
    after_snapshot_refs: list[str] = Field(default_factory=list)
    panel_changes: dict[str, dict[str, list[str]]] = Field(default_factory=dict)
    dom_gain: int = 0
    api_gain: int = 0
    entity_gain: int = 0
    gain_score: int = 0
    information_gain: dict[str, object] = Field(default_factory=dict)


class InteractionStateRecord(BaseModel):
    """One captured product/configurator state backed by DOM or network evidence."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    state_id: str
    parent_state_id: str | None = None
    interaction_step: str | None = None
    edition_id: str | None = None
    seat_configuration: str | None = None
    exterior_id: str | None = None
    interior_id: str | None = None
    section_id: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    settle_outcome: str | None = None
    requested_url: str
    final_url: str | None = None
    model_id: str | None = None
    model_name: str | None = None
    option_group: str
    option_label: str
    source_control_id: str | None = None
    panel_role: PanelRole = "unknown"
    panel_id: str | None = None
    variant_options: dict[str, str] = Field(default_factory=dict)
    price: str | None = None
    currency: str | None = None
    price_source: PriceSource = "unknown"
    specifications: dict[str, str] = Field(default_factory=dict)
    image_url: str | None = None
    availability: Availability = "unknown"
    evidence_source: EvidenceSource = "unknown"
    captured_at: str
    changed_panels: list[PanelRole] = Field(default_factory=list)
    changed_fields: list[str] = Field(default_factory=list)
    before_snapshot_ref: str | None = None
    after_snapshot_ref: str | None = None
    state_diff_ref: str | None = None
    gain_score: int = 0
    information_gain: dict[str, object] = Field(default_factory=dict)
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
        if self.specifications:
            specs = "; ".join(
                f"{key.replace('_', ' ')}: {value}"
                for key, value in sorted(self.specifications.items())
            )
            parts.append(f"specs: {specs}")
        if self.image_url:
            parts.append(f"image: {self.image_url}")
        if self.availability != "unknown":
            parts.append(f"availability: {self.availability}")
        return " - ".join(parts)

    def to_metadata_summary(self) -> dict[str, object]:
        """Return compact metadata safe to duplicate across chunks."""

        return {
            "state_id": self.state_id,
            "parent_state_id": self.parent_state_id,
            "interaction_step": self.interaction_step,
            "edition_id": self.edition_id,
            "seat_configuration": self.seat_configuration,
            "exterior_id": self.exterior_id,
            "interior_id": self.interior_id,
            "section_id": self.section_id,
            "evidence_refs": self.evidence_refs,
            "settle_outcome": self.settle_outcome,
            "model_id": self.model_id,
            "model_name": self.model_name,
            "option_group": self.option_group,
            "option_label": self.option_label,
            "source_control_id": self.source_control_id,
            "panel_role": self.panel_role,
            "panel_id": self.panel_id,
            "variant_options": self.variant_options,
            "price": self.price,
            "currency": self.currency,
            "specifications": self.specifications,
            "image_url": self.image_url,
            "availability": self.availability,
            "evidence_source": self.evidence_source,
            "changed_panels": self.changed_panels,
            "changed_fields": self.changed_fields,
            "before_snapshot_ref": self.before_snapshot_ref,
            "after_snapshot_ref": self.after_snapshot_ref,
            "state_diff_ref": self.state_diff_ref,
            "gain_score": self.gain_score,
            "information_gain": self.information_gain,
        }


class ReadinessReport(BaseModel):
    """Deterministic evidence required before configurator traversal."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ready: bool
    target_model_id: str
    model_id_matches: bool
    hero_evidence_present: bool
    edition_controls_present: bool
    configuration_panel_present: bool
    missing: list[str] = Field(default_factory=list)


class SectionVisit(BaseModel):
    """Outcome of visiting one complete-page section anchor."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    section_id: str
    reached: bool
    lazy_content_appeared: bool = False
    evidence_ref: str | None = None


class StateTransition(BaseModel):
    """Manifest entry for an accepted state transition."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    parent_state_id: str | None = None
    state_id: str
    interaction_step: str
    edition_id: str | None = None
    seat_configuration: str | None = None
    exterior_id: str | None = None
    interior_id: str | None = None
    section_id: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    settle_outcome: str
    evidence_alias_of: str | None = None


class TraversalIssue(BaseModel):
    """One explicit reason a state graph capture is incomplete or unsafe."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    detail: str
    state_id: str | None = None
    control_id: str | None = None
    section_id: str | None = None


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
    panel_snapshots: list[InteractionPanelSnapshot] = Field(default_factory=list)
    panel_diffs: list[InteractionPanelDiff] = Field(default_factory=list)
    readiness: ReadinessReport | None = None
    section_visits: list[SectionVisit] = Field(default_factory=list)
    transitions: list[StateTransition] = Field(default_factory=list)
    traversal_issues: list[TraversalIssue] = Field(default_factory=list)
    traversal_complete: bool = False


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
    panel_snapshots_path: Path | None = None
    panel_diffs_path: Path | None = None
