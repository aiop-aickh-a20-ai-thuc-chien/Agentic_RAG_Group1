"""Docling HTML/layout adapter using its public conversion API."""

from __future__ import annotations

from agentic_rag.ingestion.integration.url.models import (
    UrlAcquisitionResult,
    UrlIntegrationInput,
    UrlStrategyOutput,
    UrlStructuredSection,
)


def extract_with_docling(
    request: UrlIntegrationInput, acquisition: UrlAcquisitionResult
) -> UrlStrategyOutput:
    html = acquisition.rendered_html or acquisition.raw_html or ""
    if not html:
        return UrlStrategyOutput(
            strategy="docling-html",
            unresolved_gaps=("html_missing",),
            warnings=("Docling HTML parsing skipped because HTML is unavailable.",),
        )
    try:
        from docling.datamodel.base_models import InputFormat
        from docling.document_converter import DocumentConverter

        result = DocumentConverter(allowed_formats=[InputFormat.HTML]).convert_string(
            html,
            format=InputFormat.HTML,
            name="rendered-page.html",
        )
        markdown = str(result.document.export_to_markdown()).strip()
    except (ImportError, ModuleNotFoundError) as exc:
        raise RuntimeError("Docling is not installed for the docling-html strategy.") from exc
    except Exception as exc:
        raise RuntimeError("Docling failed to parse acquired HTML.") from exc

    source_refs = tuple(item.evidence_id for item in acquisition.evidence)
    section = UrlStructuredSection(
        section_id="docling-layout",
        heading=None,
        markdown=markdown,
        reading_order=0,
        evidence_refs=source_refs,
    )
    return UrlStrategyOutput(
        strategy="docling-html",
        markdown=markdown,
        sections=(section,) if markdown else (),
        unresolved_gaps=() if markdown else ("docling_markdown_empty",),
        metadata={"native_document_type": type(result.document).__name__},
    )
