"""PDF parser registry for parser comparison workflows."""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel, ConfigDict

from .models import PdfParserCapabilities
from .parser import (
    DEFAULT_PDF_PARSER,
    DoclingMarkdownParser,
    PdfMarkdownParser,
)


class PdfParserDefinition(BaseModel):
    """Registered PDF parser adapter factory and capability metadata."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    name: str
    factory: Callable[[], PdfMarkdownParser]
    capabilities: PdfParserCapabilities


_PDF_PARSER_REGISTRY: dict[str, PdfParserDefinition] = {
    DEFAULT_PDF_PARSER: PdfParserDefinition(
        name=DEFAULT_PDF_PARSER,
        factory=DoclingMarkdownParser,
        capabilities=PdfParserCapabilities(
            supports_markdown=True,
            supports_assets=True,
            supports_page_metadata=False,
            supports_tables=True,
            supports_images=True,
        ),
    )
}


def resolve_pdf_parser(parser_name: str | None = None) -> PdfMarkdownParser:
    """Resolve a supported parser name to a fresh parser adapter instance."""

    normalized_name = _normalize_parser_name(parser_name)
    definition = _PDF_PARSER_REGISTRY.get(normalized_name)
    if definition is None:
        raise ValueError(
            "Unsupported PDF parser: "
            f"{parser_name}. Supported parsers: {', '.join(supported_pdf_parsers())}."
        )
    return definition.factory()


def supported_pdf_parsers() -> tuple[str, ...]:
    """Return registered parser names in stable order."""

    return tuple(sorted(_PDF_PARSER_REGISTRY))


def parser_capabilities(parser_name: str | None = None) -> PdfParserCapabilities:
    """Return capability metadata for a registered parser."""

    normalized_name = _normalize_parser_name(parser_name)
    definition = _PDF_PARSER_REGISTRY.get(normalized_name)
    if definition is None:
        raise ValueError(
            "Unsupported PDF parser: "
            f"{parser_name}. Supported parsers: {', '.join(supported_pdf_parsers())}."
        )
    return definition.capabilities


def _normalize_parser_name(parser_name: str | None) -> str:
    if parser_name is None:
        return DEFAULT_PDF_PARSER
    return parser_name.strip().lower().replace("_", "-")
