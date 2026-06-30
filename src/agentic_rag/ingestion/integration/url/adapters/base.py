"""Injectable adapter protocols for URL integration."""

from __future__ import annotations

from typing import Protocol

from agentic_rag.ingestion.integration.url.models import (
    UrlAcquisitionResult,
    UrlIntegrationInput,
    UrlStrategyOutput,
)


class AcquisitionAdapter(Protocol):
    def __call__(self, request: UrlIntegrationInput) -> UrlAcquisitionResult: ...


class ExtractionAdapter(Protocol):
    def __call__(
        self, request: UrlIntegrationInput, acquisition: UrlAcquisitionResult
    ) -> UrlStrategyOutput: ...

