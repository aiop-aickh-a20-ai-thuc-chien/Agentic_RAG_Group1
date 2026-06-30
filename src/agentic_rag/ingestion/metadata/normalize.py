from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any

from agentic_rag.ingestion.metadata.entity_normalizer import normalize_filterable
from agentic_rag.ingestion.metadata.schema import (
    DOCUMENT_TYPE_VALUES,
    LANGUAGE_VALUES,
    SOURCE_TYPE_VALUES,
    infer_source_type,
)

KNOWN_MODELS: list[str] = []

_LIST_FIELDS = frozenset(
    {
        "product_model",
        "topic_tags",
        "keywords",
        "questions",
        "entities",
        "entities_canonical",
    }
)
_DATE_ALIAS_GROUPS: tuple[tuple[str, ...], ...] = (
    ("updated_date", "fetched_at", "captured_at", "ingested_at", "ingestion_at"),
    ("created_date", "published_at"),
)


def normalize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Return a normalized copy of chunk metadata.

    The normalizer keeps source-specific extras, but makes shared fields stable
    enough for storage, Qdrant payload indexes, and retrieval filters.
    """

    normalized = dict(metadata)
    _normalize_list_fields(normalized)
    _normalize_enums(normalized)
    _normalize_dates(normalized)
    _normalize_entities(normalized)
    _drop_blank_values(normalized)
    return normalized


def normalize_product_models(models: list[str] | str | None) -> list[str]:
    """Normalize product model metadata to a deduped list."""

    return _string_list(models)


def build_response_format() -> Any:
    """Stub function to build response format."""
    return None


def _normalize_list_fields(metadata: dict[str, Any]) -> None:
    for field in _LIST_FIELDS:
        if field in metadata:
            metadata[field] = _string_list(metadata.get(field))
    # URL rule extraction often stores one scalar model alias.
    if "product_model" not in metadata and metadata.get("model_name"):
        metadata["product_model"] = _string_list(metadata.get("model_name"))


def _normalize_enums(metadata: dict[str, Any]) -> None:
    source_type = _lower_text(metadata.get("source_type"))
    if source_type not in SOURCE_TYPE_VALUES:
        source_type = infer_source_type(_first_text(metadata, ("source", "url", "file_name")))
    metadata["source_type"] = source_type

    document_type = _lower_text(metadata.get("document_type"))
    if document_type and document_type not in DOCUMENT_TYPE_VALUES:
        document_type = "unknown"
    if document_type:
        metadata["document_type"] = document_type

    language = _lower_text(metadata.get("language"))
    if language and language not in LANGUAGE_VALUES:
        language = "unknown"
    if language:
        metadata["language"] = language


def _normalize_dates(metadata: dict[str, Any]) -> None:
    for aliases in _DATE_ALIAS_GROUPS:
        canonical = aliases[0]
        value = _first_text(metadata, aliases)
        if value:
            normalized = _normalize_datetime_text(value)
            metadata[canonical] = normalized
            for alias in aliases[1:]:
                if metadata.get(alias) in {None, ""}:
                    metadata[alias] = normalized


def _normalize_entities(metadata: dict[str, Any]) -> None:
    entities = _string_list(metadata.get("entities"))
    if entities:
        metadata["entities"] = entities
    canonicals = _string_list(metadata.get("entities_canonical"))
    inferred = normalize_filterable(entities) if entities else []
    merged = _dedupe([*canonicals, *inferred])
    if merged:
        metadata["entities_canonical"] = merged


def _drop_blank_values(metadata: dict[str, Any]) -> None:
    for key in list(metadata):
        value = metadata[key]
        if value == "":
            metadata[key] = None


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_items: Iterable[object] = re_split_list(value)
    elif isinstance(value, Mapping):
        raw_items = value.values()
    elif isinstance(value, Iterable):
        raw_items = value
    else:
        raw_items = (value,)
    return _dedupe(str(item).strip() for item in raw_items if str(item).strip())


def re_split_list(value: str) -> list[str]:
    separators = ("\n", ";", "|")
    if any(separator in value for separator in separators):
        import re

        return [part for part in re.split(r"[\n;|]+", value) if part.strip()]
    return [value.strip()] if value.strip() else []


def _dedupe(values: Iterable[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            output.append(value)
    return output


def _lower_text(value: object) -> str:
    return str(value).strip().lower() if isinstance(value, str) else ""


def _first_text(metadata: Mapping[str, Any], keys: Iterable[str]) -> str | None:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _normalize_datetime_text(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return stripped
    try:
        parsed = datetime.fromisoformat(stripped.replace("Z", "+00:00"))
    except ValueError:
        return stripped
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.isoformat()
