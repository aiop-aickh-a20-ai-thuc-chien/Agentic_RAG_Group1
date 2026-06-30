"""Semantic VinFast product chunks mapped to the shared Chunk contract."""

from __future__ import annotations

import json
from collections.abc import Mapping

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.integration.url.vinfast.models import VinFastProduct

_CATEGORIES: dict[str, tuple[str, ...]] = {
    "range_charging": (
        "range_km",
        "charging_time_min",
        "charging_time",
        "battery_capacity",
    ),
    "safety": ("safety", "adas", "airbag"),
    "dimensions": ("dimensions", "length", "width", "height", "weight", "cargo"),
    "interior": ("interior", "screen", "comfort", "infotainment"),
}


def product_chunks(product: VinFastProduct) -> list[Chunk]:
    """Create one pricing chunk plus non-empty semantic specification chunks."""

    grouped = _group_specs(product.specs)
    chunks: list[Chunk] = []
    for category, values in grouped.items():
        if not values:
            continue
        chunks.append(_chunk(product, category, values))
    pricing = {
        "base_price_vnd": product.base_price_vnd,
        "battery_subscription": product.battery_subscription,
        "promotions": product.promotions,
    }
    chunks.append(_chunk(product, "pricing", pricing))
    return chunks


def _group_specs(specs: Mapping[str, object]) -> dict[str, dict[str, object]]:
    output: dict[str, dict[str, object]] = {category: {} for category in _CATEGORIES}
    output["other"] = {}
    for key, value in specs.items():
        lowered = key.casefold()
        category = next(
            (
                name
                for name, markers in _CATEGORIES.items()
                if any(marker in lowered for marker in markers)
            ),
            "other",
        )
        output[category][key] = value
    return output


def _chunk(product: VinFastProduct, category: str, values: object) -> Chunk:
    battery_option = "Thuê pin" if product.battery_subscription else "Mua pin"
    chunk_id = f"{product.chunk_id}-{category}"
    text = (
        f"{product.model_name} {product.variant or ''} - {battery_option} - {category}: "
        f"{json.dumps(values, ensure_ascii=False, sort_keys=True)}"
    ).strip()
    return Chunk(
        chunk_id=chunk_id,
        text=text,
        metadata={
            "source": product.source_url,
            "source_type": "url",
            "url": product.source_url,
            "model": product.model_name,
            "variant": product.variant,
            "battery_option": battery_option,
            "category": category,
            "scraped_at": product.scraped_at.isoformat(),
            "chunk_id": chunk_id,
            "product_chunk_id": product.chunk_id,
        },
    )
