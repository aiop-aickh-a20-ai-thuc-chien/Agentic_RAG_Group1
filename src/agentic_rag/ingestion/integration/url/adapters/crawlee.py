"""Crawlee/static acquisition adapters."""

from __future__ import annotations

from agentic_rag.ingestion.integration.url.models import (
    UrlAcquisitionResult,
    UrlEvidenceRef,
    UrlIntegrationInput,
)
from agentic_rag.ingestion.url.chunking import short_hash
from agentic_rag.ingestion.url.extractor import extract_markdown_with_crawlee


def acquire_supplied_html(request: UrlIntegrationInput) -> UrlAcquisitionResult:
    if request.html is None:
        raise ValueError("Supplied-HTML acquisition requires request.html.")
    evidence_id = f"raw_html_{short_hash(request.html)}"
    return UrlAcquisitionResult(
        requested_url=request.requested_url,
        final_url=request.requested_url,
        raw_html=request.html,
        evidence=(
            UrlEvidenceRef(
                evidence_id=evidence_id,
                kind="raw_html",
                artifact_ref=f"memory://{evidence_id}",
                strategy="supplied-html",
                content_hash=short_hash(request.html),
            ),
        ),
    )


def acquire_with_crawlee(request: UrlIntegrationInput) -> UrlAcquisitionResult:
    # TODO [guide_2/TODO.md Priority 1 §1 – Preserve query params through render]:
    # Ensure the full URL including query params (e.g. `modelId=Products-Car-VF9`)
    # is forwarded to Crawlee and survives the render/fetch cycle unchanged.
    # The `final_url` returned by Crawlee should equal `request.requested_url`
    # when no redirect occurs. Log a warning if query params are lost.
    # Reference: guide_2/TODO.md Priority 1, item 1 (checked)
    #
    # TODO [guide_2/TODO.md Priority 4 – Crawlee sleep/retry settling]:
    # Add Crawlee sleep/retry logic that:
    #   - Sleeps until configurator network payloads are settled.
    #   - Recounts `timeout_seconds` when a bounded timeout is supplied.
    #   - Allows an explicit unbounded wait mode when `timeout_seconds=None`.
    # Reference: guide_2/TODO.md Priority 4 (checked items at end of file)
    extracted = extract_markdown_with_crawlee(
        request.requested_url,
        timeout_seconds=request.timeout_seconds,
        max_requests_per_crawl=1,
    )
    rendered_html = extracted.rendered_html or ""
    evidence_id = f"rendered_html_{short_hash(rendered_html)}"
    return UrlAcquisitionResult(
        requested_url=request.requested_url,
        final_url=extracted.final_url or request.requested_url,
        rendered_html=rendered_html,
        evidence=(
            UrlEvidenceRef(
                evidence_id=evidence_id,
                kind="rendered_html",
                artifact_ref=f"memory://{evidence_id}",
                strategy="crawlee",
                content_hash=short_hash(rendered_html),
            ),
        ),
        parser_markdown=extracted.markdown,
        parser_name=extracted.parser_name,
    )

