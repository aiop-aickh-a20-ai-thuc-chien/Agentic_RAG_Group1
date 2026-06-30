"""Rule-based interaction-state extraction from HTML and JSON payloads."""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.metadata import infer_source_type
from agentic_rag.ingestion.url.chunking import (
    normalize_for_content_hash,
    normalize_for_dedupe_hash,
    normalize_space,
    short_hash,
    slugify,
)
from agentic_rag.ingestion.url.interactions.models import (
    Availability,
    EvidenceSource,
    InteractionCaptureResult,
    InteractionControl,
    InteractionOptions,
    InteractionStateRecord,
    PriceSource,
)
from agentic_rag.ingestion.url.interactions.profile import detect_interaction_profile

_PRICE_RE = re.compile(
    r"\b\d[\d.,]*(?:\s*(?:VND|VN\u0110|\u0111|dong|USD|US\$|\$)|\s*\u20ab)\b",
    re.IGNORECASE,
)
_UNSAFE_LABEL_RE = re.compile(
    r"\b("
    r"dat\s*coc|thanh\s*toan|checkout|payment|submit|buy\s*now|mua\s*ngay|"
    r"login|dang\s*nhap|register|dang\s*ky|support|hotline"
    r")\b",
    re.IGNORECASE,
)
_OPTION_CLASS_RE = re.compile(
    r"(^|[\s_-])(color|colour|swatch|variant|option|trim|battery|model|package)([\s_-]|$)",
    re.IGNORECASE,
)
_IMAGE_ATTR_KEYS = ("data-image", "data-image-url", "data-src", "src")
_PRICE_ATTR_KEYS = ("data-price", "data-display-price", "data-final-price")
_LABEL_ATTR_KEYS = ("data-option-label", "aria-label", "title", "value", "alt")
_GROUP_ATTR_KEYS = ("data-option-group", "data-group", "name")
_MODEL_ATTR_KEYS = ("data-model-name", "data-model", "data-product-name")
_SPEC_CONTAINER_KEYS = (
    "specs",
    "specifications",
    "technicalSpecs",
    "technicalSpecifications",
    "attributes",
    "properties",
    "productSpecs",
)
_SPEC_LABEL_KEYS = (
    "name",
    "label",
    "title",
    "key",
    "attribute",
    "attributeName",
    "specName",
    "displayName",
)
_SPEC_VALUE_KEYS = ("value", "displayValue", "text", "content", "description")
_MAX_SPEC_FIELDS = 24
_PROMOTABLE_GROUP_RE = re.compile(
    r"\b("
    r"model|trim|variant|version|color|colour|exterior|interior|battery|package|"
    r"finance|financing|deposit|payment|price|spec|specification|specifications|"
    r"thong\s*so|vf\s*\d|mpv\s*7"
    r")\b",
    re.IGNORECASE,
)
_SKIP_PROMOTION_LABEL_RE = re.compile(
    r"^\s*(previous|prev|next|back|forward|slide|carousel|xem\s+them|thu\s+gon)\s*$",
    re.IGNORECASE,
)


def extract_interaction_states_from_html(
    html: str,
    *,
    requested_url: str,
    final_url: str | None = None,
    captured_at: str | None = None,
    network_payloads: Iterable[Mapping[str, object]] = (),
    options: InteractionOptions | None = None,
) -> InteractionCaptureResult:
    """Extract product/configurator states from one rendered or static HTML snapshot."""

    capture_options = options or InteractionOptions()
    profile = detect_interaction_profile(requested_url, final_url=final_url, html=html)
    parser = _InteractionHtmlParser(base_url=final_url or requested_url)
    parser.feed(html)
    parser.close()
    captured = captured_at or _utc_now()
    source_payloads = [dict(payload) for payload in network_payloads]
    script_payloads = parser.json_payloads
    states: list[InteractionStateRecord] = []
    states.extend(
        _states_from_controls(
            controls=parser.controls,
            requested_url=requested_url,
            final_url=final_url,
            model_id=profile.model_id,
            model_name=parser.model_name,
            default_price=parser.default_price,
            default_image_url=parser.default_image_url,
            captured_at=captured,
        )
    )
    states.extend(
        _states_from_payloads(
            [*script_payloads, *source_payloads],
            requested_url=requested_url,
            final_url=final_url,
            model_id=profile.model_id,
            captured_at=captured,
        )
    )
    if not states and (parser.model_name or parser.default_price or parser.default_image_url):
        states.append(
            _build_state(
                requested_url=requested_url,
                final_url=final_url,
                model_id=profile.model_id,
                model_name=parser.model_name,
                option_group="default",
                option_label="default",
                price=parser.default_price,
                image_url=parser.default_image_url,
                availability="unknown",
                evidence_source="dom",
                price_source="dom" if parser.default_price else "not_visible",
                captured_at=captured,
                dom_evidence=parser.default_evidence(),
            )
        )

    deduped_states = _dedupe_states(states)[: capture_options.max_states]
    skipped_controls = [control for control in parser.controls if control.skipped_reason]
    controls = [control for control in parser.controls if not control.skipped_reason]
    return InteractionCaptureResult(
        profile=profile,
        states=deduped_states,
        controls=controls,
        skipped_controls=skipped_controls,
        source_html=html,
        network_payloads=source_payloads,
    )


def build_interaction_chunks(
    result: InteractionCaptureResult,
    *,
    source: str | None = None,
    fetched_at: str | None = None,
) -> list[Chunk]:
    """Convert captured interaction states into shared RAG chunks."""

    chunk_source = source or result.profile.final_url or result.profile.requested_url
    source_type = infer_source_type(chunk_source)
    captured_at = fetched_at or _utc_now()
    page_text = "\n".join(state.to_chunk_text() for state in result.states)
    page_hash = short_hash(normalize_for_content_hash(page_text))
    state_summaries = [state.to_metadata_summary() for state in result.states]
    image_snapshot_refs = [_image_snapshot_ref(state) for state in result.states if state.image_url]
    entity_names = _interaction_entity_names(result.states)
    chunks: list[Chunk] = []
    for index, state in enumerate(result.states, start=1):
        text = state.to_chunk_text()
        normalized_text = normalize_for_content_hash(text)
        chunk_id = f"url_interaction_{short_hash(chunk_source)}_{index:04d}"
        state_snapshot_ref = _image_snapshot_ref(state)
        metadata = {
            "chunk_id": chunk_id,
            "source": chunk_source,
            "source_type": source_type,
            "url": result.profile.final_url or result.profile.requested_url,
            "requested_url": result.profile.requested_url,
            "url_query_params": result.profile.url_query_params,
            "section": "interaction_states",
            "heading": "interaction_states",
            "breadcrumb": ["interaction_states"],
            "chunk_type": "interaction_debug",
            "section_kind": "dynamic",
            "section_origin": (
                "dynamic_state_payload"
                if state.evidence_source == "network"
                else "dynamic_interaction"
            ),
            "retrieval_visibility": "debug_only",
            "metadata_prefilter_exclude": True,
            "trusted_for_retrieval": False,
            "semantic_application_status": "unmapped",
            "debug_reason": "interaction_state_capture_unmapped",
            "panel_role": state.panel_role,
            "panel_id": state.panel_id,
            "source_control_id": state.source_control_id,
            "changed_panels": state.changed_panels,
            "changed_fields": state.changed_fields,
            "before_snapshot_ref": state.before_snapshot_ref,
            "after_snapshot_ref": state.after_snapshot_ref,
            "state_diff_ref": state.state_diff_ref,
            "gain_score": state.gain_score,
            "information_gain": state.information_gain,
            "title": state.model_name,
            "fetched_at": captured_at,
            "captured_at": state.captured_at,
            "updated_date": captured_at,
            "updated_date_source": "ingestion_start",
            "page_hash": page_hash,
            "content_hash": short_hash(normalized_text),
            "dedupe_hash": short_hash(normalize_for_dedupe_hash(text)),
            "dedupe_text": normalized_text,
            "normalized_text": normalized_text,
            "token_count": len(normalized_text.split()),
            "chunk_index": index,
            "chunk_part_index": index,
            "chunk_part_total": len(result.states),
            "page_type": result.profile.page_type,
            "document_type": result.profile.page_type,
            "entities": entity_names,
            "interaction_required": result.profile.interaction_required,
            "interaction_reasons": result.profile.reasons,
            "interaction_states": state_summaries,
            "interaction_state": state.to_metadata_summary(),
            "interaction_state_id": state.state_id,
            "image_snapshot_ref": state_snapshot_ref,
            "image_snapshot_refs": image_snapshot_refs,
            "selected_model_id": result.profile.model_id,
            "selected_product_model": _model_name_from_model_id(result.profile.model_id),
            "product_model": state.model_name or state.model_id,
            "product_price": state.price,
            "deposit_amount": _deposit_amount_for_state(state),
            "product_specs": state.specifications,
            "variant_id": state.state_id,
            "variant_options": state.variant_options,
            "image_url": state.image_url,
            "price_source": state.price_source,
            "evidence_source": state.evidence_source,
            "attribute_group": _attribute_group_for_state(state),
            "is_noise": False,
            "retrieval_weight": 1.4 if state.price else 1.25 if state.specifications else 1.1,
        }
        base_chunk = Chunk(
            chunk_id=chunk_id,
            text=text,
            metadata={
                "chunk_id": chunk_id,
                "source": chunk_source,
                "source_type": source_type,
                "updated_date": captured_at,
            },
        )
        chunks.append(base_chunk.model_copy(update={"metadata": metadata}))
    return chunks


def build_promoted_interaction_chunks(
    result: InteractionCaptureResult,
    *,
    source: str | None = None,
    fetched_at: str | None = None,
) -> list[Chunk]:
    """Promote validated dynamic facts into normal retrieval chunks."""

    chunk_source = source or result.profile.final_url or result.profile.requested_url
    source_type = infer_source_type(chunk_source)
    captured_at = fetched_at or _utc_now()
    promotable_states = [
        state for state in result.states if _state_is_promotable_dynamic_fact(state)
    ]
    page_text = "\n".join(_promoted_state_text(state) for state in promotable_states)
    page_hash = short_hash(normalize_for_content_hash(page_text))
    chunks: list[Chunk] = []
    for index, state in enumerate(promotable_states, start=1):
        text = _promoted_state_text(state)
        normalized_text = normalize_for_content_hash(text)
        chunk_id = f"url_dynamic_state_{short_hash(chunk_source)}_{index:04d}"
        state_snapshot_ref = _image_snapshot_ref(state)
        metadata = {
            "chunk_id": chunk_id,
            "source": chunk_source,
            "source_type": source_type,
            "url": result.profile.final_url or result.profile.requested_url,
            "requested_url": result.profile.requested_url,
            "url_query_params": result.profile.url_query_params,
            "section": "dynamic_interaction_facts",
            "heading": "dynamic_interaction_facts",
            "breadcrumb": ["dynamic_interaction_facts"],
            "chunk_type": "dynamic_state",
            "section_kind": "dynamic",
            "section_origin": (
                "dynamic_state_payload"
                if state.evidence_source == "network"
                else "dynamic_interaction"
            ),
            "retrieval_visibility": "normal",
            "metadata_prefilter_exclude": False,
            "trusted_for_retrieval": True,
            "semantic_application_status": "applied_to_semantic_chunk",
            "panel_role": state.panel_role,
            "panel_id": state.panel_id,
            "source_control_id": state.source_control_id,
            "changed_panels": state.changed_panels,
            "changed_fields": state.changed_fields,
            "before_snapshot_ref": state.before_snapshot_ref,
            "after_snapshot_ref": state.after_snapshot_ref,
            "state_diff_ref": state.state_diff_ref,
            "gain_score": state.gain_score,
            "information_gain": state.information_gain,
            "title": state.model_name,
            "fetched_at": captured_at,
            "captured_at": state.captured_at,
            "updated_date": captured_at,
            "updated_date_source": "ingestion_start",
            "page_hash": page_hash,
            "content_hash": short_hash(normalized_text),
            "dedupe_hash": short_hash(normalize_for_dedupe_hash(text)),
            "dedupe_text": normalized_text,
            "normalized_text": normalized_text,
            "token_count": len(normalized_text.split()),
            "chunk_index": index,
            "chunk_part_index": index,
            "chunk_part_total": len(promotable_states),
            "page_type": result.profile.page_type,
            "document_type": result.profile.page_type,
            "entities": _interaction_entity_names([state]),
            "interaction_required": result.profile.interaction_required,
            "interaction_reasons": result.profile.reasons,
            "interaction_state": state.to_metadata_summary(),
            "interaction_state_id": state.state_id,
            "image_snapshot_ref": state_snapshot_ref,
            "image_snapshot_refs": [state_snapshot_ref] if state_snapshot_ref else [],
            "selected_model_id": result.profile.model_id,
            "selected_product_model": _model_name_from_model_id(result.profile.model_id),
            "product_model": state.model_name or state.model_id,
            "product_price": state.price,
            "deposit_amount": _deposit_amount_for_state(state),
            "product_specs": state.specifications,
            "variant_id": state.state_id,
            "variant_options": state.variant_options,
            "image_url": state.image_url,
            "price_source": state.price_source,
            "evidence_source": state.evidence_source,
            "attribute_group": _attribute_group_for_state(state),
            "is_noise": False,
            "retrieval_weight": 1.8 if state.price else 1.6 if state.specifications else 1.4,
        }
        base_chunk = Chunk(
            chunk_id=chunk_id,
            text=text,
            metadata={
                "chunk_id": chunk_id,
                "source": chunk_source,
                "source_type": source_type,
                "updated_date": captured_at,
            },
        )
        chunks.append(base_chunk.model_copy(update={"metadata": metadata}))
    return chunks


def _state_is_promotable_dynamic_fact(state: InteractionStateRecord) -> bool:
    if not state.changed_fields:
        return False
    if _SKIP_PROMOTION_LABEL_RE.search(_ascii_fold(state.option_label)):
        return False
    group_text = _ascii_fold(f"{state.option_group} {state.option_label}")
    if not _PROMOTABLE_GROUP_RE.search(group_text):
        return False
    useful_fields = {
        "price",
        "image",
        "availability",
        "payment_summary",
        "specifications",
        "visible_text",
        "tables",
        "nodes",
    }
    if not any(field in useful_fields for field in state.changed_fields):
        return False
    has_visible_change = bool(state.dom_evidence.get("after_snapshot_text"))
    has_supported_fact = (
        bool(state.price or state.image_url or state.specifications)
        or ("availability" in state.changed_fields and state.availability != "unknown")
        or has_visible_change
    )
    if not has_supported_fact:
        return False
    if state.evidence_source == "network" and state.specifications:
        return True
    return not (state.evidence_source == "network" and not state.dom_evidence)


def _promoted_state_text(state: InteractionStateRecord) -> str:
    product_name = state.model_name or state.model_id or "Product"
    if state.option_group == "deposit" and state.price:
        return f"{product_name} deposit amount is {state.price} from network payload."
    group = state.option_group.replace("_", " ")
    label = state.option_label
    changed_panels = ", ".join(panel.replace("_", " ") for panel in state.changed_panels)
    subject = f"{product_name} selected {group} {label}"
    details: list[str] = []
    if state.price:
        price_panel = (
            "right-panel visible price"
            if "right_panel" in state.changed_panels
            else "visible price"
        )
        details.append(f"{price_panel} to {state.price}")
    if state.specifications:
        specs = "; ".join(
            f"{key.replace('_', ' ')} {value}"
            for key, value in sorted(state.specifications.items())
        )
        details.append(f"API-backed specifications: {specs}")
    if state.image_url:
        image_panel = (
            "center product image"
            if "center_visual" in state.changed_panels
            else "visible product image"
        )
        details.append(f"{image_panel} to {state.image_url}")
    if state.availability != "unknown":
        details.append(f"availability to {state.availability}")
    if (
        not state.price
        and not state.specifications
        and not state.image_url
        and state.dom_evidence.get("after_snapshot_text")
    ):
        details.append(
            f"visible text after interaction: {state.dom_evidence['after_snapshot_text']}"
        )
    if not details:
        details.append("visible dynamic facts")
    panel_phrase = f" across {changed_panels}" if changed_panels else ""
    return f"{subject} changes{panel_phrase}: {', '.join(details)}."


def _image_snapshot_ref(state: InteractionStateRecord) -> str | None:
    if not state.image_url:
        return None
    return f"image_snapshot_{state.state_id}"


def _interaction_entity_names(states: Iterable[InteractionStateRecord]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for state in states:
        name = state.model_name or state.model_id
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


def _attribute_group_for_state(state: InteractionStateRecord) -> str:
    if state.price or state.specifications:
        return "pricing_specs"
    return "product_variant"


def _deposit_amount_for_state(state: InteractionStateRecord) -> str | None:
    if state.option_group == "deposit":
        return state.price
    value = state.specifications.get("deposit_amount")
    return value or None


def extract_specifications_from_text(text: str) -> dict[str, str]:
    """Extract canonical product specs from visible modal/table text."""

    lines = [line for line in (_clean_text(part) for part in text.splitlines()) if line]
    specs: dict[str, str] = {}
    for index, line in enumerate(lines):
        label, value = _split_spec_line(line)
        if label and value:
            canonical_key = _canonical_spec_key(label)
            spec_text = _scalar_spec_text(value)
            if canonical_key is not None and spec_text:
                specs.setdefault(canonical_key, spec_text)
        canonical_line = _canonical_spec_key(line)
        if canonical_line is not None and index + 1 < len(lines):
            spec_text = _scalar_spec_text(lines[index + 1])
            if spec_text:
                specs.setdefault(canonical_line, spec_text)
    return _clean_specifications(specs)


class _InteractionHtmlParser(HTMLParser):
    """Small parser for option controls, prices, images, and embedded JSON state."""

    def __init__(self, *, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.controls: list[InteractionControl] = []
        self.json_payloads: list[dict[str, object]] = []
        self.model_name: str | None = None
        self.default_price: str | None = None
        self.default_image_url: str | None = None
        self._h1_parts: list[str] = []
        self._capture_h1 = False
        self._script_parts: list[str] = []
        self._capture_script = False
        self._current_control: dict[str, object] | None = None
        self._control_parts: list[str] = []
        self._control_index = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()
        attr_map = _attr_map(attrs)
        if normalized_tag == "h1":
            self._capture_h1 = True
            self._h1_parts = []
            return
        if normalized_tag == "script":
            self._capture_script = True
            self._script_parts = []
            return
        if normalized_tag == "img" and self.default_image_url is None:
            image_url = _first_attr(attr_map, _IMAGE_ATTR_KEYS)
            if image_url:
                self.default_image_url = urljoin(self.base_url, image_url)
            return
        if _is_control_tag(normalized_tag, attr_map):
            self._start_control(normalized_tag, attr_map)
            if normalized_tag == "input":
                self._finish_control()

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if normalized_tag == "h1":
            self._capture_h1 = False
            self.model_name = self.model_name or _clean_text(" ".join(self._h1_parts))
            self._h1_parts = []
            return
        if normalized_tag == "script":
            self._capture_script = False
            self._add_json_payload("".join(self._script_parts))
            self._script_parts = []
            return
        if self._current_control is not None and normalized_tag == self._current_control["tag"]:
            self._finish_control()

    def handle_data(self, data: str) -> None:
        text = _clean_text(data)
        if not text:
            return
        if self._capture_h1:
            self._h1_parts.append(text)
        if self._capture_script:
            self._script_parts.append(data)
            return
        if self._current_control is not None:
            self._control_parts.append(text)
        if self.default_price is None:
            price = _price_from_text(text)
            if price:
                self.default_price = price

    def close(self) -> None:
        super().close()
        if self._current_control is not None:
            self._finish_control()
        self.model_name = self.model_name or _clean_text(" ".join(self._h1_parts)) or None

    def default_evidence(self) -> dict[str, str]:
        evidence: dict[str, str] = {}
        if self.model_name:
            evidence["model_name"] = self.model_name
        if self.default_price:
            evidence["price"] = self.default_price
        if self.default_image_url:
            evidence["image_url"] = self.default_image_url
        return evidence

    def _start_control(self, tag: str, attrs: dict[str, str]) -> None:
        if self._current_control is not None:
            self._finish_control()
        self._current_control = {"tag": tag, "attrs": attrs}
        self._control_parts = []

    def _finish_control(self) -> None:
        if self._current_control is None:
            return
        raw_attrs = self._current_control["attrs"]
        attrs = dict(raw_attrs) if isinstance(raw_attrs, Mapping) else {}
        self._current_control = None
        text = _clean_text(" ".join(self._control_parts))
        self._control_parts = []
        label = _first_attr(attrs, _LABEL_ATTR_KEYS) or text
        if not label:
            return
        self._control_index += 1
        group = _first_attr(attrs, _GROUP_ATTR_KEYS) or _infer_group(label, attrs)
        disabled = _is_disabled(attrs)
        skipped_reason = _skip_reason(label, attrs)
        self.controls.append(
            InteractionControl(
                control_id=f"control-{self._control_index}",
                label=label,
                group=group,
                disabled=disabled,
                attributes=attrs,
                skipped_reason=skipped_reason,
            )
        )

    def _add_json_payload(self, script_text: str) -> None:
        payload = _json_from_script_text(script_text)
        if payload is not None:
            self.json_payloads.append(payload)


def _states_from_controls(
    *,
    controls: Iterable[InteractionControl],
    requested_url: str,
    final_url: str | None,
    model_id: str | None,
    model_name: str | None,
    default_price: str | None,
    default_image_url: str | None,
    captured_at: str,
) -> list[InteractionStateRecord]:
    states: list[InteractionStateRecord] = []
    for control in controls:
        if control.skipped_reason:
            continue
        attrs = control.attributes
        price = _first_attr(attrs, _PRICE_ATTR_KEYS) or default_price
        image_url = _first_attr(attrs, _IMAGE_ATTR_KEYS) or default_image_url
        if image_url:
            image_url = urljoin(final_url or requested_url, image_url)
        state_model_name = _first_attr(attrs, _MODEL_ATTR_KEYS) or model_name
        states.append(
            _build_state(
                requested_url=requested_url,
                final_url=final_url,
                model_id=model_id,
                model_name=state_model_name,
                option_group=control.group,
                option_label=control.label,
                price=price,
                image_url=image_url,
                availability="disabled" if control.disabled else "available",
                evidence_source="dom",
                price_source="dom" if price else "not_visible",
                captured_at=captured_at,
                dom_evidence={
                    "control_id": control.control_id,
                    "label": control.label,
                    **_compact_attrs(attrs),
                },
            )
        )
    return states


def _states_from_payloads(
    payloads: Iterable[Mapping[str, object]],
    *,
    requested_url: str,
    final_url: str | None,
    model_id: str | None,
    captured_at: str,
) -> list[InteractionStateRecord]:
    states: list[InteractionStateRecord] = []
    for payload in payloads:
        for candidate in _candidate_dicts(payload):
            state = _state_from_payload_candidate(
                candidate,
                requested_url=requested_url,
                final_url=final_url,
                fallback_model_id=model_id,
                captured_at=captured_at,
            )
            if state is not None:
                states.append(state)
    return states


def _state_from_payload_candidate(
    candidate: Mapping[str, object],
    *,
    requested_url: str,
    final_url: str | None,
    fallback_model_id: str | None,
    captured_at: str,
) -> InteractionStateRecord | None:
    deposit_amount = _deposit_amount_from_candidate(candidate)
    price = deposit_amount or _value_by_keys(
        candidate, ("price", "displayPrice", "finalPrice", "salePrice")
    )
    image_url = _value_by_keys(candidate, ("image", "imageUrl", "image_url", "thumbnail", "url"))
    label = _value_by_keys(candidate, ("color", "colorName", "optionLabel", "variantName", "name"))
    specifications = _specifications_from_candidate(candidate)
    if deposit_amount:
        specifications = {**specifications, "deposit_amount": deposit_amount}
    group = _value_by_keys(candidate, ("optionGroup", "group", "type", "category")) or (
        "deposit" if deposit_amount else "specifications" if specifications else "variant"
    )
    model_name = _value_by_keys(candidate, ("modelName", "productName", "model", "title"))
    candidate_model_id = _model_id_from_candidate(candidate)
    model_name = model_name or _model_name_from_model_id(candidate_model_id or fallback_model_id)
    if price is None and image_url is None and not specifications:
        return None
    option_label = (
        label
        or model_name
        or candidate_model_id
        or ("deposit_amount" if deposit_amount else None)
        or ("api_specs" if specifications else "network_state")
    )
    normalized_image = urljoin(final_url or requested_url, image_url) if image_url else None
    return _build_state(
        requested_url=requested_url,
        final_url=final_url,
        model_id=candidate_model_id or fallback_model_id,
        model_name=model_name,
        option_group=slugify(group) or "variant",
        option_label=option_label,
        price=price,
        specifications=specifications,
        image_url=normalized_image,
        availability=_availability_from_candidate(candidate),
        evidence_source="network",
        price_source="json_state" if price else "not_visible",
        captured_at=captured_at,
        network_evidence=_compact_payload(candidate),
    )


def _build_state(
    *,
    requested_url: str,
    final_url: str | None,
    model_id: str | None,
    model_name: str | None,
    option_group: str,
    option_label: str,
    price: str | None,
    image_url: str | None,
    availability: Availability,
    evidence_source: EvidenceSource,
    price_source: PriceSource,
    captured_at: str,
    specifications: dict[str, str] | None = None,
    dom_evidence: dict[str, str] | None = None,
    network_evidence: dict[str, str] | None = None,
) -> InteractionStateRecord:
    normalized_group = slugify(option_group) or "variant"
    normalized_label = normalize_space(option_label) or "unknown"
    variant_options = {} if normalized_group == "default" else {normalized_group: normalized_label}
    normalized_specs = _clean_specifications(specifications or {})
    changed_fields: list[str] = []
    if evidence_source == "network":
        if price:
            changed_fields.append("price")
        if normalized_specs:
            changed_fields.append("specifications")
        if image_url:
            changed_fields.append("image")
        if availability != "unknown":
            changed_fields.append("availability")
    state_key = "|".join(
        part or ""
        for part in (
            requested_url,
            model_id,
            model_name,
            normalized_group,
            normalized_label,
            normalize_space(price or ""),
            json.dumps(normalized_specs, sort_keys=True, ensure_ascii=True),
            normalize_space(image_url or ""),
        )
    )
    return InteractionStateRecord(
        state_id=short_hash(state_key),
        requested_url=requested_url,
        final_url=final_url,
        model_id=model_id,
        model_name=model_name,
        option_group=normalized_group,
        option_label=normalized_label,
        variant_options=variant_options,
        price=normalize_space(price or "") or None,
        currency=_currency_from_price(price),
        price_source=price_source,
        specifications=normalized_specs,
        image_url=image_url,
        availability=availability,
        evidence_source=evidence_source,
        captured_at=captured_at,
        changed_fields=changed_fields,
        dom_evidence=dom_evidence or {},
        network_evidence=network_evidence or {},
    )


def _dedupe_states(states: Iterable[InteractionStateRecord]) -> list[InteractionStateRecord]:
    seen: set[str] = set()
    output: list[InteractionStateRecord] = []
    for state in states:
        key = state.state_id
        if key in seen:
            continue
        seen.add(key)
        output.append(state)
    return output


def _candidate_dicts(value: object) -> Iterable[Mapping[str, object]]:
    if isinstance(value, Mapping):
        payload = {str(key): item for key, item in value.items()}
        if payload and _looks_like_variant_payload(payload):
            yield payload
        for child in payload.values():
            yield from _candidate_dicts(child)
    elif isinstance(value, list | tuple):
        for item in value:
            yield from _candidate_dicts(item)


def _looks_like_variant_payload(value: Mapping[str, object]) -> bool:
    lowered_keys = {str(key).lower() for key in value}
    has_fact = bool(
        lowered_keys
        & {
            "price",
            "displayprice",
            "finalprice",
            "saleprice",
            "image",
            "imageurl",
            "image_url",
            "thumbnail",
            "depositamount",
        }
    )
    has_deposit = _deposit_amount_from_candidate(value) is not None
    has_specs = any(_canonical_spec_key(str(key)) is not None for key in value) or bool(
        lowered_keys & {key.lower() for key in _SPEC_CONTAINER_KEYS}
    )
    has_label = (
        bool(
            lowered_keys
            & {
                "color",
                "colorname",
                "optionlabel",
                "variantname",
                "name",
                "modelname",
                "productname",
                "modelid",
                "productid",
                "sku",
            }
        )
        or _model_id_from_candidate(value) is not None
    )
    return (has_fact and has_label) or (has_specs and has_label) or (has_deposit and has_label)


def _specifications_from_candidate(candidate: Mapping[str, object]) -> dict[str, str]:
    specs: dict[str, str] = {}
    _collect_direct_spec_keys(candidate, specs)
    for container_key in _SPEC_CONTAINER_KEYS:
        raw = _raw_by_key(candidate, container_key)
        if raw is not None:
            _collect_spec_items(raw, specs)
    return _clean_specifications(specs)


def _collect_direct_spec_keys(
    value: Mapping[str, object],
    specs: dict[str, str],
) -> None:
    for key, raw in value.items():
        if len(specs) >= _MAX_SPEC_FIELDS:
            return
        canonical_key = _canonical_spec_key(str(key))
        if canonical_key is None:
            continue
        text = _scalar_spec_text(raw)
        if text:
            specs.setdefault(canonical_key, text)


def _collect_spec_items(value: object, specs: dict[str, str]) -> None:
    if len(specs) >= _MAX_SPEC_FIELDS:
        return
    if isinstance(value, Mapping):
        label = _value_by_keys(value, _SPEC_LABEL_KEYS)
        spec_value = _value_by_keys(value, _SPEC_VALUE_KEYS)
        if label and spec_value:
            canonical_key = _canonical_spec_key(label)
            if canonical_key is not None:
                specs.setdefault(canonical_key, spec_value)
        for key, raw in value.items():
            if len(specs) >= _MAX_SPEC_FIELDS:
                return
            canonical_key = _canonical_spec_key(str(key))
            if canonical_key is not None:
                text = _scalar_spec_text(raw)
                if text:
                    specs.setdefault(canonical_key, text)
            elif str(key).lower() in {item.lower() for item in _SPEC_CONTAINER_KEYS}:
                _collect_spec_items(raw, specs)
    elif isinstance(value, list | tuple):
        for item in value:
            _collect_spec_items(item, specs)


def _clean_specifications(value: Mapping[str, str]) -> dict[str, str]:
    cleaned: dict[str, str] = {}
    for key, raw in sorted(value.items()):
        if len(cleaned) >= _MAX_SPEC_FIELDS:
            break
        canonical_key = _canonical_spec_key(key)
        if canonical_key is None:
            continue
        text = _scalar_spec_text(raw)
        if text:
            cleaned.setdefault(canonical_key, text)
    return cleaned


def _canonical_spec_key(value: str) -> str | None:
    normalized = re.sub(r"[^a-z0-9]+", "_", _ascii_fold(value)).strip("_")
    if not normalized:
        return None
    exact_aliases = {
        "range": "driving_range",
        "range_km": "driving_range",
        "driving_range": "driving_range",
        "battery": "battery_capacity",
        "battery_capacity": "battery_capacity",
        "battery_kwh": "battery_capacity",
        "seats": "seats",
        "seat": "seats",
        "number_of_seats": "seats",
        "power": "power",
        "max_power": "power",
        "torque": "torque",
        "max_torque": "torque",
        "dimensions": "dimensions",
        "dimension": "dimensions",
        "length": "length",
        "width": "width",
        "height": "height",
        "wheelbase": "wheelbase",
        "charging_time": "charging_time",
        "fast_charging_time": "charging_time",
        "acceleration": "acceleration",
        "top_speed": "top_speed",
        "drivetrain": "drivetrain",
        "ground_clearance": "ground_clearance",
        "cargo_volume": "cargo_volume",
        "deposit_amount": "deposit_amount",
        "deposit": "deposit_amount",
    }
    if normalized in exact_aliases:
        return exact_aliases[normalized]
    contains_aliases = (
        (("quang_duong", "tam_hoat_dong", "driving_range", "range"), "driving_range"),
        (("dung_luong_pin", "battery_capacity", "battery", "pin"), "battery_capacity"),
        (("so_cho_ngoi", "number_of_seats", "seats"), "seats"),
        (("cong_suat", "max_power", "power"), "power"),
        (("mo_men", "torque"), "torque"),
        (("kich_thuoc", "dimensions", "dai_rong_cao"), "dimensions"),
        (("chieu_dai", "length"), "length"),
        (("chieu_rong", "width"), "width"),
        (("chieu_cao", "height"), "height"),
        (("chieu_dai_co_so", "wheelbase"), "wheelbase"),
        (("thoi_gian_sac", "charging_time", "charge_time"), "charging_time"),
        (("tang_toc", "acceleration"), "acceleration"),
        (("toc_do_toi_da", "top_speed"), "top_speed"),
        (("he_dan_dong", "drivetrain"), "drivetrain"),
        (("khoang_sang_gam", "ground_clearance"), "ground_clearance"),
        (("the_tich_khoang_chua_do", "cargo", "luggage"), "cargo_volume"),
        (("deposit", "dat_coc", "tien_dat_coc"), "deposit_amount"),
    )
    for needles, canonical_key in contains_aliases:
        if any(needle in normalized for needle in needles):
            return canonical_key
    return None


def _scalar_spec_text(value: object) -> str | None:
    if not isinstance(value, str | int | float | bool):
        return None
    text = normalize_space(str(value))
    if not text or text == "[redacted]" or len(text) > 160:
        return None
    lowered = text.lower()
    if lowered.startswith(("http://", "https://")):
        return None
    return text


def _raw_by_key(value: Mapping[str, object], key: str) -> object | None:
    lowered = {item.lower(): item for item in value}
    actual_key = lowered.get(key.lower())
    if actual_key is None:
        return None
    return value.get(actual_key)


def _split_spec_line(line: str) -> tuple[str | None, str | None]:
    for separator in (":", "\t", " - ", " \u2013 "):
        if separator not in line:
            continue
        left, right = line.split(separator, 1)
        left = _clean_text(left)
        right = _clean_text(right)
        if left and right:
            return left, right
    return None, None


def _value_by_keys(value: Mapping[str, object], keys: tuple[str, ...]) -> str | None:
    lowered = {key.lower(): key for key in value}
    for key in keys:
        actual_key = lowered.get(key.lower())
        if actual_key is None:
            continue
        raw = value.get(actual_key)
        if isinstance(raw, str | int | float):
            text = normalize_space(str(raw))
            if text:
                return text
    return None


def _deposit_amount_from_candidate(candidate: Mapping[str, object]) -> str | None:
    raw = _raw_by_key(candidate, "depositAmount")
    if isinstance(raw, Mapping):
        amount = _value_by_keys(raw, ("depositAmount", "amount", "value", "formatted"))
        if amount:
            return _format_vnd_amount(amount)
    amount = _value_by_keys(candidate, ("depositAmount", "deposit_amount", "deposit"))
    if amount:
        return _format_vnd_amount(amount)
    return None


def _model_id_from_candidate(candidate: Mapping[str, object]) -> str | None:
    model_id = _value_by_keys(candidate, ("modelId", "modelID", "productId", "sku"))
    if model_id:
        return model_id
    for nested_key in ("querystring", "queryString", "query"):
        raw = _raw_by_key(candidate, nested_key)
        if isinstance(raw, Mapping):
            model_id = _value_by_keys(raw, ("modelId", "modelID", "productId", "sku"))
            if model_id:
                return model_id
    return None


def _format_vnd_amount(value: str) -> str:
    text = normalize_space(value)
    if not text:
        return text
    if re.search(r"\b(?:vnd|vn\u0111|\u0111|\u20ab)\b", text, re.IGNORECASE):
        return text
    if re.fullmatch(r"\d+(?:[.,]\d+)*", text):
        return f"{text} VND"
    return text


def _model_name_from_model_id(model_id: str | None) -> str | None:
    if not model_id:
        return None
    match = re.search(r"Products-Car-VF(\d+)", model_id, re.IGNORECASE)
    if match is not None:
        return f"VF {match.group(1)}"
    return None


def _json_from_script_text(script_text: str) -> dict[str, object] | None:
    text = script_text.strip()
    if not text:
        return None
    candidates = [text]
    if "{" in text and "}" in text:
        candidates.append(text[text.find("{") : text.rfind("}") + 1])
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _attr_map(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
    return {name.lower(): value or "" for name, value in attrs}


def _is_control_tag(tag: str, attrs: dict[str, str]) -> bool:
    if tag == "button":
        return True
    if tag == "input" and attrs.get("type", "").lower() in {"radio", "button"}:
        return True
    if attrs.get("role", "").lower() == "button":
        return True
    return "data-option-group" in attrs or "data-option-label" in attrs


def _is_disabled(attrs: dict[str, str]) -> bool:
    aria_disabled = attrs.get("aria-disabled", "").lower()
    return "disabled" in attrs or aria_disabled == "true" or attrs.get("data-disabled") == "true"


def _skip_reason(label: str, attrs: dict[str, str]) -> str | None:
    if _UNSAFE_LABEL_RE.search(_ascii_fold(label)):
        return "unsafe_action_label"
    control_type = attrs.get("type", "").lower()
    if control_type in {"submit", "reset"}:
        return "unsafe_control_type"
    role = attrs.get("role", "").lower()
    class_name = attrs.get("class", "")
    has_option_attr = "data-option-group" in attrs or "data-option-label" in attrs
    if has_option_attr or _OPTION_CLASS_RE.search(class_name) or role in {"button", "radio", "tab"}:
        return None
    return "not_option_like"


def _infer_group(label: str, attrs: dict[str, str]) -> str:
    class_name = attrs.get("class", "").lower()
    label_text = _ascii_fold(label)
    if "color" in class_name or "swatch" in class_name or "mau" in label_text:
        return "color"
    if "battery" in class_name or "pin" in label_text:
        return "battery"
    if "trim" in class_name or "variant" in class_name:
        return "variant"
    return "option"


def _first_attr(attrs: dict[str, str], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = normalize_space(attrs.get(key, ""))
        if value:
            return value
    return None


def _compact_attrs(attrs: dict[str, str]) -> dict[str, str]:
    keep_keys = (
        "class",
        "role",
        "aria-label",
        "data-option-group",
        "data-option-label",
        "data-price",
        "data-image",
        "data-model-name",
    )
    return {key: attrs[key] for key in keep_keys if attrs.get(key)}


def _compact_payload(payload: Mapping[str, object]) -> dict[str, str]:
    compact: dict[str, str] = {}
    for key, value in payload.items():
        if len(compact) >= 12:
            break
        if isinstance(value, str | int | float | bool):
            compact[str(key)] = normalize_space(str(value))[:240]
    return compact


def _availability_from_candidate(candidate: Mapping[str, object]) -> Availability:
    raw = _value_by_keys(candidate, ("availability", "status", "enabled", "disabled"))
    if raw is None:
        return "unknown"
    lowered = raw.lower()
    if lowered in {"false", "disabled", "unavailable", "soldout", "sold_out"}:
        return "disabled"
    if lowered in {"true", "enabled", "available", "active"}:
        return "available"
    return "unknown"


def _price_from_text(text: str) -> str | None:
    match = _PRICE_RE.search(text)
    return normalize_space(match.group(0)) if match else None


def _currency_from_price(price: str | None) -> str | None:
    if not price:
        return None
    lowered = price.lower()
    if "$" in price or "usd" in lowered:
        return "USD"
    if "vnd" in lowered or "vn\u0111" in lowered or "\u0111" in lowered or "\u20ab" in price:
        return "VND"
    return None


def _clean_text(value: str) -> str:
    return normalize_space(value)


def _ascii_fold(value: str) -> str:
    folded = value.replace("\u0111", "d").replace("\u0110", "D")
    return unicodedata.normalize("NFKD", folded).encode("ascii", "ignore").decode("ascii").lower()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


__all__ = [
    "build_interaction_chunks",
    "build_promoted_interaction_chunks",
    "extract_interaction_states_from_html",
    "extract_specifications_from_text",
]
