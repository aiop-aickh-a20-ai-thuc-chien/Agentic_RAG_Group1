from __future__ import annotations

from typing import Any

KNOWN_MODELS: list[str] = []


def normalize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """Stub function to normalize chunk metadata."""
    return metadata


def normalize_product_models(models: list[str] | str | None) -> list[str]:
    """Stub function to normalize product models."""
    if isinstance(models, str):
        return [models]
    return list(models) if models else []


def build_response_format() -> Any:
    """Stub function to build response format."""
    return None
