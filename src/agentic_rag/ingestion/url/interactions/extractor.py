"""Rule-based interaction-state extraction from HTML and JSON payloads."""

from __future__ import annotations

import json
import re
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
        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                text=text,
                metadata={
                    "chunk_id": chunk_id,
                    "source": chunk_source,
                    "source_type": source_type,
                    "url": result.profile.final_url or result.profile.requested_url,
                    "requested_url": result.profile.requested_url,
                    "url_query_params": result.profile.url_query_params,
                    "section": "interaction_states",
                    "heading": "interaction_states",
                    "breadcrumb": ["interaction_states"],
                    "title": state.model_name,
                    "fetched_at": captured_at,
                    "captured_at": state.captured_at,
                    "updated_date": captured_at,
                    "updated_date_source": "ingestion_start",
                    "page_hash": page_hash,
                    "content_hash": short_hash(normalized_text),
                    "dedupe_hash": short_hash(normalize_for_dedupe_hash(text)),
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
                    "product_model": state.model_name or state.model_id,
                    "product_price": state.price,
                    "variant_id": state.state_id,
                    "variant_options": state.variant_options,
                    "image_url": state.image_url,
                    "price_source": state.price_source,
                    "evidence_source": state.evidence_source,
                    "attribute_group": "pricing_specs" if state.price else "product_variant",
                    "is_noise": False,
                    "retrieval_weight": 1.4 if state.price else 1.1,
                },
            )
        )
    return chunks


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
        attrs = dict(self._current_control["attrs"])
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
    price = _value_by_keys(candidate, ("price", "displayPrice", "finalPrice", "salePrice"))
    image_url = _value_by_keys(candidate, ("image", "imageUrl", "image_url", "thumbnail", "url"))
    label = _value_by_keys(candidate, ("color", "colorName", "optionLabel", "variantName", "name"))
    group = _value_by_keys(candidate, ("optionGroup", "group", "type", "category")) or "variant"
    model_name = _value_by_keys(candidate, ("modelName", "productName", "model", "title"))
    candidate_model_id = _value_by_keys(candidate, ("modelId", "productId", "sku"))
    if price is None and image_url is None:
        return None
    option_label = label or model_name or candidate_model_id or "network_state"
    normalized_image = urljoin(final_url or requested_url, image_url) if image_url else None
    return _build_state(
        requested_url=requested_url,
        final_url=final_url,
        model_id=candidate_model_id or fallback_model_id,
        model_name=model_name,
        option_group=slugify(group) or "variant",
        option_label=option_label,
        price=price,
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
    dom_evidence: dict[str, str] | None = None,
    network_evidence: dict[str, str] | None = None,
) -> InteractionStateRecord:
    normalized_group = slugify(option_group) or "variant"
    normalized_label = normalize_space(option_label) or "unknown"
    variant_options = {} if normalized_group == "default" else {normalized_group: normalized_label}
    state_key = "|".join(
        part or ""
        for part in (
            requested_url,
            model_id,
            model_name,
            normalized_group,
            normalized_label,
            normalize_space(price or ""),
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
        image_url=image_url,
        availability=availability,
        evidence_source=evidence_source,
        captured_at=captured_at,
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
        }
    )
    has_label = bool(
        lowered_keys
        & {
            "color",
            "colorname",
            "optionlabel",
            "variantname",
            "name",
            "modelname",
            "productname",
            "sku",
        }
    )
    return has_fact and has_label


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
    folded = value.lower()
    replacements = {
        "\u0111": "d",
        "\u0110": "d",
        "\u00e1": "a",
        "\u00e0": "a",
        "\u1ea3": "a",
        "\u00e3": "a",
        "\u1ea1": "a",
        "\u1eaf": "a",
        "\u1eb1": "a",
        "\u1eb3": "a",
        "\u1eb5": "a",
        "\u1eb7": "a",
        "\u1ea5": "a",
        "\u1ea7": "a",
        "\u1ea9": "a",
        "\u1eab": "a",
        "\u1ead": "a",
        "\u00e9": "e",
        "\u00e8": "e",
        "\u1ebb": "e",
        "\u1ebd": "e",
        "\u1eb9": "e",
        "\u00ed": "i",
        "\u00ec": "i",
        "\u1ec9": "i",
        "\u0129": "i",
        "\u1ecb": "i",
        "\u00f3": "o",
        "\u00f2": "o",
        "\u1ecf": "o",
        "\u00f5": "o",
        "\u1ecd": "o",
        "\u00fa": "u",
        "\u00f9": "u",
        "\u1ee7": "u",
        "\u0169": "u",
        "\u1ee5": "u",
    }
    for source, target in replacements.items():
        folded = folded.replace(source, target)
    return folded


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


__all__ = [
    "build_interaction_chunks",
    "extract_interaction_states_from_html",
]
