"""Deterministic readiness and completeness checks for scoped state capture."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence

from agentic_rag.ingestion.url.chunking import normalize_space, short_hash
from agentic_rag.ingestion.url.interactions.models import (
    InteractionCaptureResult,
    InteractionControl,
    ReadinessReport,
    StateTransition,
    TraversalIssue,
)

DEFAULT_CONFIGURATOR_SECTIONS = (
    "phien-ban",
    "ngoai-that",
    "noi-that",
    "cong-nghe",
    "dac-quyen",
    "pin-sac",
)
_OTHER_MODEL_RE = re.compile(r"\bVF\s*-?\s*(\d{1,2})\b", re.IGNORECASE)


def stable_control_identity(control: InteractionControl) -> str:
    """Choose source-backed control identity before any DOM-position fallback."""

    attributes = control.attributes
    for key in (
        "data-product-id",
        "data-variant-id",
        "data-option-id",
        "value",
        "name",
        "aria-label",
    ):
        value = normalize_space(attributes.get(key, ""))
        if value:
            return f"{control.group}:{key}:{value}"
    if control.label.strip():
        return f"{control.group}:role-label:{normalize_space(control.label)}"
    return f"{control.group}:debug:{short_hash(control.selector or control.control_id)}"


def assess_configurator_readiness(
    *,
    target_model_id: str,
    selected_model_id: str | None,
    visible_text: str,
    controls: Sequence[InteractionControl],
    configuration_panel_present: bool,
) -> ReadinessReport:
    """Require model, hero, edition controls, and configuration panel evidence."""

    target_digits = _model_digits(target_model_id)
    selected_digits = _model_digits(selected_model_id or "")
    model_id_matches = bool(target_digits and target_digits == selected_digits)
    normalized = normalize_space(visible_text).casefold()
    hero_evidence_present = bool(target_digits and f"vf {target_digits}" in normalized)
    edition_controls_present = any(
        control.group.casefold() in {"edition", "variant", "version", "trim"}
        and not control.disabled
        for control in controls
    )
    checks = {
        "model_id": model_id_matches,
        "hero_evidence": hero_evidence_present,
        "edition_controls": edition_controls_present,
        "configuration_panel": configuration_panel_present,
    }
    return ReadinessReport(
        ready=all(checks.values()),
        target_model_id=target_model_id,
        model_id_matches=model_id_matches,
        hero_evidence_present=hero_evidence_present,
        edition_controls_present=edition_controls_present,
        configuration_panel_present=configuration_panel_present,
        missing=[name for name, present in checks.items() if not present],
    )


def transition_manifest(result: InteractionCaptureResult) -> list[StateTransition]:
    """Build deterministic transition entries while preserving evidence aliases."""

    transitions: list[StateTransition] = []
    seen_fingerprints: dict[str, str] = {}
    for index, state in enumerate(result.states, start=1):
        fingerprint = short_hash(
            "|".join(
                (
                    state.model_id or "",
                    state.edition_id or "",
                    state.seat_configuration or "",
                    state.exterior_id or "",
                    state.interior_id or "",
                    state.section_id or "",
                    normalize_space(state.to_chunk_text()),
                )
            )
        )
        alias = seen_fingerprints.get(fingerprint)
        seen_fingerprints.setdefault(fingerprint, state.state_id)
        refs = list(
            dict.fromkeys(
                [
                    *state.evidence_refs,
                    *(
                        [state.before_snapshot_ref]
                        if state.before_snapshot_ref is not None
                        else []
                    ),
                    *(
                        [state.after_snapshot_ref]
                        if state.after_snapshot_ref is not None
                        else []
                    ),
                    *([state.state_diff_ref] if state.state_diff_ref is not None else []),
                ]
            )
        )
        transitions.append(
            StateTransition(
                parent_state_id=state.parent_state_id,
                state_id=state.state_id,
                interaction_step=state.interaction_step or f"state:{index}",
                edition_id=state.edition_id,
                seat_configuration=state.seat_configuration,
                exterior_id=state.exterior_id,
                interior_id=state.interior_id,
                section_id=state.section_id,
                evidence_refs=refs,
                settle_outcome=state.settle_outcome or "captured",
                evidence_alias_of=alias,
            )
        )
    return transitions


def traversal_issues(
    result: InteractionCaptureResult,
    *,
    expected_model: str,
    required_sections: Sequence[str] = DEFAULT_CONFIGURATOR_SECTIONS,
) -> list[TraversalIssue]:
    """Report incomplete traversal instead of interpreting absence as missing facts."""

    issues: list[TraversalIssue] = []
    visits = {visit.section_id: visit for visit in result.section_visits}
    for section in required_sections:
        visit = visits.get(section)
        if visit is None or not visit.reached:
            issues.append(
                TraversalIssue(
                    code="unvisited_section_anchor",
                    detail=f"Required section was not reached: {section}",
                    section_id=section,
                )
            )
    captured_control_ids = {state.source_control_id for state in result.states}
    skipped_control_ids = {control.control_id for control in result.skipped_controls}
    for control in result.controls:
        if (
            not control.disabled
            and control.control_id not in captured_control_ids
            and control.control_id not in skipped_control_ids
        ):
            issues.append(
                TraversalIssue(
                    code="unclicked_enabled_control",
                    detail="Enabled control has no capture or explicit skip outcome.",
                    control_id=control.control_id,
                )
            )
    counts = Counter(state.state_id for state in result.states)
    for state in result.states:
        if state.after_snapshot_ref is None:
            issues.append(
                TraversalIssue(
                    code="state_without_after_snapshot",
                    detail="Accepted state has no after-snapshot evidence.",
                    state_id=state.state_id,
                )
            )
        if counts[state.state_id] > 1:
            issues.append(
                TraversalIssue(
                    code="duplicate_state_id",
                    detail="State ID is not unique in the traversal.",
                    state_id=state.state_id,
                )
            )
        foreign = _foreign_models(state.to_chunk_text(), expected_model)
        if foreign:
            issues.append(
                TraversalIssue(
                    code="cross_model_contamination",
                    detail=f"State contains unrelated model facts: {', '.join(foreign)}",
                    state_id=state.state_id,
                )
            )
    return _unique_issues(issues)


def finalize_traversal(
    result: InteractionCaptureResult,
    *,
    expected_model: str,
    required_sections: Sequence[str] = DEFAULT_CONFIGURATOR_SECTIONS,
) -> InteractionCaptureResult:
    """Attach transition and completeness manifests without promoting facts."""

    transitions = transition_manifest(result)
    issues = traversal_issues(
        result, expected_model=expected_model, required_sections=required_sections
    )
    return result.model_copy(
        update={
            "transitions": transitions,
            "traversal_issues": issues,
            "traversal_complete": not issues,
        }
    )


def _model_digits(value: str) -> str | None:
    match = re.search(r"VF\D*(\d{1,2})", value, re.IGNORECASE)
    return match.group(1) if match else None


def _foreign_models(text: str, expected_model: str) -> list[str]:
    expected = _model_digits(expected_model)
    return sorted(
        {match.group(1) for match in _OTHER_MODEL_RE.finditer(text) if match.group(1) != expected}
    )


def _unique_issues(issues: Sequence[TraversalIssue]) -> list[TraversalIssue]:
    output: list[TraversalIssue] = []
    seen: set[tuple[str, str | None, str | None, str | None]] = set()
    for issue in issues:
        key = (issue.code, issue.state_id, issue.control_id, issue.section_id)
        if key not in seen:
            seen.add(key)
            output.append(issue)
    return output
