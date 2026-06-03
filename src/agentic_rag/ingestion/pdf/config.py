"""Configuration for local PDF ingestion."""

from __future__ import annotations

import os
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, model_validator

from agentic_rag.ingestion.pdf.chunkers import DEFAULT_MARKDOWN_CHUNKER
from agentic_rag.ingestion.pdf.pipelines import DEFAULT_PDF_PIPELINE, DEFAULT_PDF_STRATEGY
from agentic_rag.runtime_env import load_local_env


class PdfIngestionConfig(BaseModel):
    """PDF parser pipeline, strategy, and chunker selection for local ingestion."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pipeline_name: str = DEFAULT_PDF_PIPELINE
    strategy_name: str = DEFAULT_PDF_STRATEGY
    chunker_name: str = DEFAULT_MARKDOWN_CHUNKER

    def __init__(
        self,
        *,
        pipeline_name: str = DEFAULT_PDF_PIPELINE,
        strategy_name: str | None = None,
        parser_name: str | None = None,
        chunker_name: str = DEFAULT_MARKDOWN_CHUNKER,
    ) -> None:
        super().__init__(
            pipeline_name=pipeline_name,
            strategy_name=strategy_name or parser_name or DEFAULT_PDF_STRATEGY,
            chunker_name=chunker_name,
        )

    @model_validator(mode="before")
    @classmethod
    def _normalize_legacy_parser_name(cls, data: Any) -> Any:
        if not isinstance(data, dict) or "parser_name" not in data:
            return data

        normalized = dict(data)
        parser_name = normalized.pop("parser_name")
        normalized.setdefault("strategy_name", parser_name)
        return normalized

    @property
    def parser_name(self) -> str:
        """Backward-compatible parser name for older callers and traces."""

        return self.strategy_name

    @classmethod
    def from_env(cls) -> Self:
        """Build PDF ingestion config from local environment variables."""

        load_local_env()
        legacy_parser = _env_text("LOCAL_PDF_PARSER", DEFAULT_PDF_STRATEGY)
        strategy_name = _env_text("LOCAL_PDF_STRATEGY", legacy_parser)
        return cls(
            pipeline_name=_env_text(
                "LOCAL_PDF_PIPELINE", _pipeline_for_legacy_parser(strategy_name)
            ),
            strategy_name=strategy_name,
            chunker_name=_env_text("LOCAL_PDF_CHUNKER", DEFAULT_MARKDOWN_CHUNKER),
        )


def _pipeline_for_legacy_parser(parser_name: str) -> str:
    if parser_name.strip().lower().replace("_", "-") == DEFAULT_PDF_STRATEGY:
        return DEFAULT_PDF_PIPELINE
    return DEFAULT_PDF_PIPELINE


def _env_text(name: str, default: str) -> str:
    raw = os.getenv(name, "").strip()
    return raw or default
