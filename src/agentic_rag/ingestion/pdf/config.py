"""Configuration for local PDF ingestion."""

from __future__ import annotations

import os
from typing import Self

from pydantic import BaseModel, ConfigDict

from agentic_rag.ingestion.pdf.chunkers import DEFAULT_MARKDOWN_CHUNKER
from agentic_rag.ingestion.pdf.parser import DEFAULT_PDF_PARSER
from agentic_rag.runtime_env import load_local_env


class PdfIngestionConfig(BaseModel):
    """PDF parser and chunker selection for local ingestion."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    parser_name: str = DEFAULT_PDF_PARSER
    chunker_name: str = DEFAULT_MARKDOWN_CHUNKER

    @classmethod
    def from_env(cls) -> Self:
        """Build PDF ingestion config from local environment variables."""

        load_local_env()
        return cls(
            parser_name=_env_text("LOCAL_PDF_PARSER", DEFAULT_PDF_PARSER),
            chunker_name=_env_text("LOCAL_PDF_CHUNKER", DEFAULT_MARKDOWN_CHUNKER),
        )


def _env_text(name: str, default: str) -> str:
    raw = os.getenv(name, "").strip()
    return raw or default
