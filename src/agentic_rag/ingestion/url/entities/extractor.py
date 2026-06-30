"""Entity and product-spec extraction helpers for URL semantic blocks."""

from __future__ import annotations

import re
import unicodedata
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from pydantic import BaseModel, ConfigDict, Field

from agentic_rag.ingestion.url.chunking import normalize_space, short_hash
from agentic_rag.ingestion.url.dom import DomBlock

_PRICE_RE = re.compile(
    r"\b(?:\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)\s*"
    r"(?:vnd|vn\s*\u0111|\u20ab|dong|\u0111\u1ed3ng|\u0111|usd|\$|"
    r"tri\u1ec7u|trieu|t\u1ef7|ty)\b",
    re.I,
)
_RANGE_RE = re.compile(
    r"\b\d[\d.,]*(?:\s*-\s*\d[\d.,]*)?\s*(?:km|kilometer|kilometers)\b(?!\s*/?\s*h)",
    re.I,
)
_SEATS_RE = re.compile(r"\b\d+\s*(?:seats?|ch\u1ed7|cho)\b", re.I)
_BATTERY_RE = re.compile(r"\b\d[\d.,]*\s*kwh\b", re.I)
_CHARGING_TIME_RE = re.compile(
    r"\b\d[\d.,]*\s*(?:phut|minutes?|mins?|gio|hours?|h)\b",
    re.I,
)
_POWER_RE = re.compile(r"\b\d[\d.,]*\s*(?:kw|hp|ma\s*luc)\b", re.I)
_TORQUE_RE = re.compile(r"\b\d[\d.,]*\s*nm\b", re.I)
_MAX_SPEED_RE = re.compile(r"\b\d[\d.,]*\s*(?:km\s*/\s*h|kmh)\b", re.I)
_WARRANTY_RE = re.compile(
    r"\b\d[\d.,]*\s*(?:nam|years?|thang|months?)\b",
    re.I,
)
_DIMENSIONS_RE = re.compile(
    r"\b\d{3,5}\s*(?:x|\*)\s*\d{3,5}\s*(?:x|\*)\s*\d{3,5}\s*mm\b",
    re.I,
)
_GROUND_CLEARANCE_RE = re.compile(r"\b\d{2,4}\s*mm\b", re.I)
_MODEL_RE = re.compile(
    r"\b(?:vinfast\s+)?(?:"
    r"vf\s*-?\s*(?:e34|[0-9][a-z0-9]*(?:\s+plus)?)|"
    r"(?:limo|minio|herio|nerio)\s+green|"
    r"evo(?:\s+grand(?:\s+lite)?|\s+neo)?|"
    r"feliz(?:\s+(?:s|ii))?|theon(?:\s+s)?|vento(?:\s+s)?|klara(?:\s+s)?|"
    r"motio|impes|ludo|drgnfly|amio|viper|zgoo\s+flazz"
    r")\b",
    re.I,
)

_SPEC_DEFINITIONS: tuple[tuple[str, tuple[str, ...], re.Pattern[str]], ...] = (
    ("price", ("gia", "price", "niem yet", "ban le", "dat coc"), _PRICE_RE),
    (
        "driving_range",
        ("quang duong", "tam hoat dong", "di chuyen", "chay duoc", "range", "distance"),
        _RANGE_RE,
    ),
    ("seats", ("so cho", "cho ngoi", "seats", "hang ghe"), _SEATS_RE),
    ("battery_capacity", ("pin", "battery", "dung luong"), _BATTERY_RE),
    ("charging_time", ("sac", "charging", "charge"), _CHARGING_TIME_RE),
    ("power", ("cong suat", "power", "dong co", "motor"), _POWER_RE),
    ("torque", ("mo men", "torque"), _TORQUE_RE),
    ("max_speed", ("toc do", "speed", "van toc"), _MAX_SPEED_RE),
    ("warranty", ("bao hanh", "warranty"), _WARRANTY_RE),
    ("dimensions", ("kich thuoc", "dimensions", "dai x rong x cao"), _DIMENSIONS_RE),
    ("ground_clearance", ("khoang sang gam", "ground clearance"), _GROUND_CLEARANCE_RE),
)


class UrlEntity(BaseModel):
    """Structured entity candidate derived from a DOM block."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entity_id: str
    entity_type: str
    entity_name: str
    source_block_id: str
    dom_path: str
    retrieval_text: str
    structured_data: dict[str, object] = Field(default_factory=dict)


def extract_entities(
    blocks: list[DomBlock],
    *,
    primary_entity: str | None = None,
) -> list[UrlEntity]:
    """Extract structured entity candidates from semantic DOM blocks."""

    entities: list[UrlEntity] = []
    for block in filter_blocks_for_primary_entity(blocks, primary_entity=primary_entity):
        entity_type = _entity_type_for_block(block)
        entity_name = _entity_name_for_block(block)
        if entity_type is None or entity_name is None:
            continue
        structured_data = _structured_data_for_text(block.text)
        retrieval_text = _retrieval_text(
            entity_name=entity_name,
            entity_type=entity_type,
            text=block.text,
            structured_data=structured_data,
        )
        entities.append(
            UrlEntity(
                entity_id=f"url_entity_{short_hash(block.block_id + '|' + entity_name)}",
                entity_type=entity_type,
                entity_name=entity_name,
                source_block_id=block.block_id,
                dom_path=block.dom_path,
                retrieval_text=retrieval_text,
                structured_data=structured_data,
            )
        )
    return _deduplicate_entities(entities)


def extract_product_specs(
    text: str,
    *,
    title: str | None = None,
    url: str | None = None,
) -> dict[str, object]:
    """Extract product and vehicle specification facts from visible text."""

    specs: dict[str, object] = {}
    model_name = _model_name_for_text(text=text, title=title, url=url)
    if model_name:
        specs["model_name"] = model_name
    for key, labels, pattern in _SPEC_DEFINITIONS:
        value = _first_labeled_value(text, labels=labels, pattern=pattern)
        if value:
            specs[key] = value
    edition_specs = _extract_edition_specs(text, primary_model=model_name)
    if edition_specs:
        specs["editions"] = edition_specs
    color_specs = _extract_color_specs(text)
    if color_specs:
        specs["colors"] = color_specs
    return specs


def infer_primary_page_entity(
    *,
    title: str | None = None,
    url: str | None = None,
    text: str | None = None,
) -> str | None:
    """Infer the primary product/model the page is about."""

    return _model_name_for_text(text=text or "", title=title, url=url)


def filter_blocks_for_primary_entity(
    blocks: list[DomBlock],
    *,
    primary_entity: str | None,
) -> list[DomBlock]:
    """Drop cross-sell model blocks when a URL or h1 scopes the page to one model."""

    if not primary_entity:
        return blocks
    primary_key = _model_key(primary_entity)
    output: list[DomBlock] = []
    for block in blocks:
        block_models = {_model_key(match.group(0)) for match in _MODEL_RE.finditer(block.text)}
        if block_models and primary_key not in block_models:
            continue
        output.append(block)
    return output


def entities_summary(entities: list[UrlEntity]) -> dict[str, Any]:
    """Return compact entity diagnostics for chunk metadata."""

    counts: dict[str, int] = {}
    for entity in entities:
        counts[entity.entity_type] = counts.get(entity.entity_type, 0) + 1
    return {
        "entity_count": len(entities),
        "entity_types": counts,
        "entity_names": [entity.entity_name for entity in entities[:20]],
    }


def _entity_type_for_block(block: DomBlock) -> str | None:
    if block.block_type in {"vehicle_card", "product_card"}:
        if _MODEL_RE.search(block.text):
            return "vehicle"
        return "product"
    if block.block_type == "faq_item":
        return "faq_item"
    if block.block_type == "policy_section":
        return "policy_section"
    if block.block_type in {"comparison_table", "comparison_row"}:
        return block.block_type
    if block.block_type == "course_card":
        return "course"
    if block.block_type == "job_card":
        return "job"
    return None


def _entity_name_for_block(block: DomBlock) -> str | None:
    model_match = _MODEL_RE.search(block.text)
    if model_match is not None:
        return _format_model_name(model_match.group(0))
    if block.heading:
        return block.heading[:120]
    sentences = re.split(r"[.!?\n]", block.text)
    for sentence in sentences:
        cleaned = normalize_space(sentence)
        if 2 <= len(cleaned) <= 120:
            return cleaned
    return None


def _structured_data_for_text(text: str) -> dict[str, object]:
    return extract_product_specs(text)


def _retrieval_text(
    *,
    entity_name: str,
    entity_type: str,
    text: str,
    structured_data: dict[str, object],
) -> str:
    flat_facts = {key: value for key, value in structured_data.items() if isinstance(value, str)}
    facts = ", ".join(f"{key}: {value}" for key, value in flat_facts.items())
    prefix = f"{entity_name} ({entity_type})"
    if facts:
        prefix = f"{prefix} - {facts}"
    return normalize_space(f"{prefix}. {text}")


def _first_match(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return normalize_space(match.group(0)) if match else None


def _first_labeled_value(
    text: str,
    *,
    labels: tuple[str, ...],
    pattern: re.Pattern[str],
) -> str | None:
    for line in _candidate_lines(text):
        normalized_line = _normalize_for_matching(line)
        if any(label in normalized_line for label in labels):
            value = _first_match(pattern, line)
            if value:
                return value
    return _first_match(pattern, text)


def _extract_edition_specs(
    text: str,
    *,
    primary_model: str | None,
) -> dict[str, dict[str, str]]:
    editions: dict[str, dict[str, str]] = {}
    for line in _candidate_lines(text):
        price = _first_match(_PRICE_RE, line)
        if not price:
            continue
        edition = _edition_name_for_line(line, primary_model=primary_model)
        if edition is None:
            continue
        editions.setdefault(edition, {})["price"] = price
    return editions


def _edition_name_for_line(line: str, *, primary_model: str | None) -> str | None:
    model_match = _MODEL_RE.search(line)
    base_model = _format_model_name(model_match.group(0)) if model_match else primary_model
    normalized_line = _normalize_for_matching(line)
    edition: str | None = None
    if re.search(r"\beco\b", normalized_line):
        edition = "Eco"
    elif re.search(r"\bplus\b", normalized_line):
        edition = "Plus"
    if edition is None:
        return base_model
    if base_model:
        base_without_edition = re.sub(r"\s+(?:Eco|Plus)$", "", base_model, flags=re.I)
        return normalize_space(f"{base_without_edition} {edition}")
    return edition


def _extract_color_specs(text: str) -> dict[str, list[dict[str, str]]]:
    colors: dict[str, list[dict[str, str]]] = {"standard": [], "premium": []}
    for line in _candidate_lines(text):
        if not _looks_like_color_line(line):
            continue
        price = _first_match(_PRICE_RE, line)
        color_name = _color_name_for_line(line)
        if not color_name:
            continue
        bucket = "premium" if price and _is_surcharge_line(line) else "standard"
        entry: dict[str, str] = {"name": color_name}
        if price:
            entry["surcharge"] = price
        if entry not in colors[bucket]:
            colors[bucket].append(entry)
    return {key: value for key, value in colors.items() if value}


def _looks_like_color_line(line: str) -> bool:
    normalized = _normalize_for_matching(line)
    return any(
        marker in normalized
        for marker in (
            "mau",
            "color",
            "colour",
            "ngoai that",
            "noi that",
            "son",
        )
    )


def _is_surcharge_line(line: str) -> bool:
    normalized = _normalize_for_matching(line)
    return any(
        marker in normalized for marker in ("them", "cong", "phu phi", "surcharge", "premium", "+")
    )


def _color_name_for_line(line: str) -> str | None:
    cleaned = normalize_space(_PRICE_RE.sub("", line))
    cleaned = re.sub(
        r"(?i)\b(?:mau|màu|color|colour|ngoai that|ngoại thất|noi that|nội thất|son|premium|standard|"
        r"phu phi|phụ phí|them|thêm|cong|cộng|content)\b",
        " ",
        cleaned,
    )
    cleaned = normalize_space(cleaned.strip(":-+|, "))
    if not cleaned or len(cleaned) > 80:
        return None
    return cleaned


def _candidate_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in text.splitlines():
        cleaned = normalize_space(re.sub(r"^[#*\-\s]+", "", raw_line))
        if cleaned:
            lines.append(cleaned)
    if lines:
        return lines
    return [sentence for sentence in re.split(r"(?<=[.!?])\s+", normalize_space(text)) if sentence]


def _model_name_for_text(
    *,
    text: str,
    title: str | None,
    url: str | None,
) -> str | None:
    for candidate in _model_candidates(text=text, title=title, url=url):
        match = _MODEL_RE.search(candidate)
        if match is not None:
            return _format_model_name(match.group(0))
    return None


def _model_candidates(
    *,
    text: str,
    title: str | None,
    url: str | None,
) -> list[str]:
    candidates: list[str] = []
    if title:
        candidates.append(_clean_title(title))
    for line in _candidate_lines(text)[:8]:
        candidates.append(_clean_title(line))
    if url:
        parsed_url = urlparse(url)
        query = parse_qs(parsed_url.query)
        for values in query.values():
            candidates.extend(
                value.replace("Products-Car-", "VF ").replace("-", " ") for value in values if value
            )
        path = unquote(parsed_url.path)
        slug = path.rstrip("/").split("/")[-1]
        if slug:
            candidates.append(re.sub(r"\.html?$", "", slug, flags=re.I).replace("-", " "))
    return [candidate for candidate in candidates if candidate]


def _clean_title(title: str) -> str:
    cleaned = re.split(r"\s*[|:]\s*", normalize_space(title), maxsplit=1)[0]
    return re.sub(r"\bVinFast\b", "", cleaned, flags=re.I).strip() or normalize_space(title)


def _format_model_name(value: str) -> str:
    cleaned = normalize_space(re.sub(r"(?i)^vinfast\s+", "", value).replace("-", " "))
    compact_vf = re.fullmatch(r"(?i)vf\s*([a-z0-9]+)", cleaned)
    if compact_vf is not None and not re.search(r"\s", cleaned.strip()):
        return f"VF {compact_vf.group(1).upper()}"
    parts = cleaned.split()
    if not parts:
        return cleaned
    if parts[0].casefold() == "vf":
        tail = [part.upper() for part in parts[1:]]
        return normalize_space(" ".join(["VF", *tail]))
    formatted: list[str] = []
    for part in parts:
        lowered = part.casefold()
        if lowered in {"s", "ii"}:
            formatted.append(part.upper())
        else:
            formatted.append(part[:1].upper() + part[1:].lower())
    return normalize_space(" ".join(formatted))


def _model_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", _format_model_name(value).casefold())


def _normalize_for_matching(value: str) -> str:
    value = value.casefold().replace("\u0111", "d")
    normalized = unicodedata.normalize("NFKD", value)
    without_marks = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    return " ".join(re.sub(r"[^a-z0-9/%.,]+", " ", without_marks).split())


def _deduplicate_entities(entities: list[UrlEntity]) -> list[UrlEntity]:
    seen: set[tuple[str, str]] = set()
    output: list[UrlEntity] = []
    for entity in entities:
        key = (entity.entity_type, entity.entity_name.casefold())
        if key in seen:
            continue
        seen.add(key)
        output.append(entity)
    return output


__all__ = [
    "UrlEntity",
    "entities_summary",
    "extract_entities",
    "extract_product_specs",
    "filter_blocks_for_primary_entity",
    "infer_primary_page_entity",
]
