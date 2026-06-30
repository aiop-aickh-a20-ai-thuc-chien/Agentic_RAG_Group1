"""Stable metadata block-key construction."""

from __future__ import annotations

from collections.abc import Mapping
from urllib.parse import urlsplit

EMPTY_BUCKET = "<empty>"
STATIC_BLOCK_FIELDS = (
    "source_type",
    "document_type",
    "domain",
    "product_model",
    "language",
    "heading",
    "section",
)
DYNAMIC_BLOCK_FIELDS = (
    "product_model",
    "scope_type",
    "attribute_group",
    "language",
    "ancestor_scope_path",
)


def normalize_block_value(value: object) -> str:
    """Normalize metadata values into deterministic, explicit buckets."""

    if isinstance(value, (list, tuple, set)):
        text = ",".join(sorted(str(item).strip().casefold() for item in value if str(item).strip()))
    else:
        text = " ".join(str(value or "").split()).casefold()
    return text or EMPTY_BUCKET


def metadata_block_key(metadata: Mapping[str, object]) -> str:
    """Return a source-neutral block key, with stricter dynamic-state ancestry."""

    enriched = dict(metadata)
    if not enriched.get("domain"):
        url = str(enriched.get("canonical_url") or enriched.get("url") or "")
        enriched["domain"] = urlsplit(url).hostname or None
    scope_path = str(enriched.get("scope_path") or "")
    if scope_path:
        enriched["ancestor_scope_path"] = scope_path.rpartition("/")[0] or EMPTY_BUCKET
        fields: tuple[str, ...] = DYNAMIC_BLOCK_FIELDS
        prefix = "dynamic"
    else:
        fields = STATIC_BLOCK_FIELDS
        prefix = "static"
    entity_key = enriched.get("entity_key") or enriched.get("stable_entity_key")
    values = [f"{field}={normalize_block_value(enriched.get(field))}" for field in fields]
    if entity_key:
        values.append(f"entity={normalize_block_value(entity_key)}")
    return "|".join((prefix, *values))
