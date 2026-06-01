"""Environment-backed configuration for the RAGFlow integration."""

from __future__ import annotations

import os
from dataclasses import dataclass

from agentic_rag.runtime_env import load_local_env


class RAGFlowConfigurationError(RuntimeError):
    """Raised when RAGFlow is selected but required settings are missing."""


@dataclass(frozen=True)
class RAGFlowConfig:
    """Connection and retrieval defaults for a RAGFlow service."""

    base_url: str
    api_key: str
    dataset_id: str
    timeout_seconds: float = 60.0
    page_size: int = 5
    similarity_threshold: float = 0.2
    vector_similarity_weight: float = 0.3
    top_k: int = 1024
    keyword: bool = False

    @classmethod
    def from_env(cls) -> RAGFlowConfig:
        """Build config from process environment variables."""

        load_local_env()
        base_url = os.getenv("RAGFLOW_BASE_URL", "").strip().rstrip("/")
        api_key = os.getenv("RAGFLOW_API_KEY", "").strip()
        dataset_id = os.getenv("RAGFLOW_DATASET_ID", "").strip()

        missing = [
            name
            for name, value in (
                ("RAGFLOW_BASE_URL", base_url),
                ("RAGFLOW_API_KEY", api_key),
                ("RAGFLOW_DATASET_ID", dataset_id),
            )
            if not value
        ]
        if missing:
            joined = ", ".join(missing)
            raise RAGFlowConfigurationError(f"Missing RAGFlow config: {joined}")

        return cls(
            base_url=base_url,
            api_key=api_key,
            dataset_id=dataset_id,
            timeout_seconds=_float_env("RAGFLOW_TIMEOUT_SECONDS", 60.0),
            page_size=_int_env("RAGFLOW_PAGE_SIZE", 5),
            similarity_threshold=_float_env("RAGFLOW_SIMILARITY_THRESHOLD", 0.2),
            vector_similarity_weight=_float_env("RAGFLOW_VECTOR_SIMILARITY_WEIGHT", 0.3),
            top_k=_int_env("RAGFLOW_TOP_K", 1024),
            keyword=_bool_env("RAGFLOW_KEYWORD", False),
        )


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}
