"""Knowledge-quality method selection and domain errors."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

AVAILABLE_KNOWLEDGE_QUALITY_METHODS: Final[tuple[str, ...]] = (
    "deterministic_v1",
    "metadata_rules",
    "semantic_rules",
    "semantic_verifier",
    "agentic_review",
)
DEFAULT_KNOWLEDGE_QUALITY_METHODS: Final[tuple[str, ...]] = ("deterministic_v1",)
MODEL_BACKED_KNOWLEDGE_QUALITY_METHODS: Final[frozenset[str]] = frozenset(
    {"semantic_verifier", "agentic_review"}
)


class KnowledgeQualityMethodError(ValueError):
    """Base class for invalid knowledge-quality method requests."""


class UnknownKnowledgeQualityMethodError(KnowledgeQualityMethodError):
    """Raised when a requested method is not registered."""


class KnowledgeQualityConfigurationError(KnowledgeQualityMethodError):
    """Raised when an opt-in method lacks required runtime configuration."""


class KnowledgeQualityInvocationError(RuntimeError):
    """Raised when an opt-in model method cannot produce a valid result."""


def parse_knowledge_quality_methods(
    methods: str | Sequence[str] | None,
) -> list[str]:
    """Normalize a method query while preserving caller order."""

    requested = methods.split(",") if isinstance(methods, str) else list(methods or [])

    normalized: list[str] = []
    for raw_name in requested:
        name = raw_name.strip()
        if not name or name in normalized:
            continue
        if name not in AVAILABLE_KNOWLEDGE_QUALITY_METHODS:
            available = ", ".join(AVAILABLE_KNOWLEDGE_QUALITY_METHODS)
            raise UnknownKnowledgeQualityMethodError(
                f"Unknown knowledge-quality method {name!r}. Available methods: {available}."
            )
        normalized.append(name)
    return normalized or list(DEFAULT_KNOWLEDGE_QUALITY_METHODS)
