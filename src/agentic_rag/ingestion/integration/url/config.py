"""Environment-backed URL integration configuration."""

from __future__ import annotations

import os
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict

from agentic_rag.runtime_env import load_local_env


class UrlIntegrationConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    acquisition_strategy: str = "crawlee"
    dom_strategy: str = "beautifulsoup"
    layout_strategy: str = "docling-html"
    render_policy: Literal["never", "auto", "always"] = "auto"
    interaction_policy: Literal["never", "auto", "always"] = "auto"
    vlm_policy: Literal["never", "auto", "always"] = "never"

    @classmethod
    def from_env(cls) -> Self:
        load_local_env()
        return cls(
            acquisition_strategy=_text("URL_INTEGRATION_ACQUISITION", "crawlee"),
            dom_strategy=_text("URL_INTEGRATION_DOM", "beautifulsoup"),
            layout_strategy=_text("URL_INTEGRATION_LAYOUT", "docling-html"),
            render_policy=_policy("URL_INTEGRATION_RENDER_POLICY", "auto"),
            interaction_policy=_policy("URL_INTEGRATION_INTERACTION_POLICY", "auto"),
            vlm_policy=_policy("URL_INTEGRATION_VLM_POLICY", "never"),
        )


def _text(name: str, default: str) -> str:
    return os.getenv(name, "").strip() or default


def _policy(name: str, default: str) -> Literal["never", "auto", "always"]:
    value = _text(name, default).lower()
    if value not in {"never", "auto", "always"}:
        raise ValueError(f"{name} must be never, auto, or always.")
    return value  # type: ignore[return-value]

