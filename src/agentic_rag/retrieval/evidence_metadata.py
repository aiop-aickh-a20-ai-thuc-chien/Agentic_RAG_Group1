"""Helpers for exposing source metadata in evidence prompts."""

from __future__ import annotations

import re
from typing import Any

_MODEL_RE = re.compile(r"\bVF[\s-]?(3|5|6|7|8|9)\b", re.IGNORECASE)
_GREEN_MODEL_RE = re.compile(
    r"\b(minio|herio|nerio|limo)[\s-]?green\b",
    re.IGNORECASE,
)
_EC_VAN_RE = re.compile(r"\b(?:ec[\s-]?van|vinfast[\s-]?ecvan)\b", re.IGNORECASE)

_VEHICLE_PAGE_PATTERNS = (
    "dat-coc-xe-dien-vf",
    "dat-coc-xe-vf",
    "dat-coc-o-to-dien-vinfast",
    "dat-coc-bo-sung-o-to-dien",
    "vinfast-cars-deposit",
)

_ACCESSORY_PAGE_PATTERNS = (
    "phu-kien",
    "bo-sac",
    "op-lung",
    "tham-lot",
    "o-to-dien/phu-kien",
    "vinfast-accessories",
    "charge-accessories",
    "green-accessories",
    "greenaccessories",
    "green-charge",
    "greencharge",
    "thanh-pho-xanh",
    "v-green",
    "vgreen",
    "mua-phu-kien",
    "accessory",
    "accessories",
    "lifestyle",
    "quat-tang",
    "gift",
    "merchandise",
    "clutch",
    "backpack",
    "thermos",
    "embroideredcap",
    "embroideredpolo",
    "embroideredtshirt",
    "scalemodels",
    "silkscarf",
)
_ACCESSORY_CATEGORY_RE = re.compile(r"/(?:500[1-9]|5010|6001)(?:$|[\s/?#])")


def format_prompt_metadata(metadata: Any) -> str:
    """Return compact source metadata for evidence prompt lines."""

    fields = _prompt_metadata_fields(metadata)
    if not fields:
        return ""
    return "; metadata=" + ", ".join(f"{key}={value}" for key, value in fields)


def _prompt_metadata_fields(metadata: Any) -> list[tuple[str, str]]:
    fields: list[tuple[str, str]] = []

    page_type = infer_page_type(metadata)
    price_type = infer_price_type(metadata, page_type=page_type)
    vehicle_model = infer_vehicle_model(metadata)

    _append_metadata_field(fields, "page_type", page_type)
    _append_metadata_field(fields, "price_type", price_type)
    _append_metadata_field(fields, "vehicle_model", vehicle_model)
    return fields


def infer_page_type(metadata: Any) -> str:
    """Infer a coarse source type from URL/title metadata."""

    source_type = (_metadata_text(metadata, "source_type") or "").strip().lower()
    if source_type and source_type != "url":
        return source_type

    haystack = _source_haystack(metadata)
    if _looks_like_accessory_page(haystack):
        return "accessory_page"
    if any(pattern in haystack for pattern in _VEHICLE_PAGE_PATTERNS):
        return "vehicle_page"
    if "cau-hoi-thuong-gap" in haystack:
        return "faq"
    if "tin-tuc" in haystack or "thong-bao" in haystack:
        return "news"
    if "trạm sạc" in haystack or "tram-sac" in haystack or "sac-pin" in haystack:
        return "charging"
    if "chinh-sach" in haystack or "dieu-khoan" in haystack or "bao-hanh" in haystack:
        return "policy_or_service"
    return source_type or "unknown"


def infer_price_type(metadata: Any, *, page_type: str | None = None) -> str:
    """Infer whether prices in the source likely refer to a vehicle or accessory."""

    resolved_page_type = page_type or infer_page_type(metadata)
    if resolved_page_type == "vehicle_page":
        return "vehicle_price"
    if resolved_page_type == "accessory_page":
        return "accessory_price"
    return "unknown"


def infer_vehicle_model(metadata: Any) -> str | None:
    """Infer VinFast vehicle model labels from URL/title-like metadata."""

    haystack = _source_haystack(metadata)
    match = _MODEL_RE.search(haystack)
    if match:
        return f"VF {match.group(1)}"

    green_match = _GREEN_MODEL_RE.search(haystack)
    if green_match:
        return f"{green_match.group(1).title()} Green"

    if _EC_VAN_RE.search(haystack):
        return "EC Van"
    return None


def _looks_like_accessory_page(haystack: str) -> bool:
    return _ACCESSORY_CATEGORY_RE.search(haystack) is not None or any(
        pattern in haystack for pattern in _ACCESSORY_PAGE_PATTERNS
    )


def _source_haystack(metadata: Any) -> str:
    values = [
        _metadata_text(metadata, key)
        for key in (
            "url",
            "source",
            "canonical_url",
            "final_url",
            "original_url",
            "title",
            "section",
            "description",
        )
    ]
    return " ".join(value for value in values if value).lower()


def _append_metadata_field(
    fields: list[tuple[str, str]],
    key: str,
    value: object | None,
) -> None:
    if value is None:
        return
    text = str(value).strip()
    if not text:
        return
    fields.append((key, _sanitize_metadata_value(text)))


def _metadata_text(metadata: Any, key: str) -> str | None:
    value = metadata.get(key)
    if value is None:
        return None
    return str(value)


def _sanitize_metadata_value(value: str) -> str:
    return " ".join(value.split()).replace(";", ",")
