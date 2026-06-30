from agentic_rag.ingestion.integration.url import (
    UrlEvidenceFact,
    UrlEvidenceRef,
    UrlIntegrationAdapters,
    UrlIntegrationConfig,
    UrlIntegrationInput,
    UrlStrategyOutput,
    integrate_url,
    supported_url_integration_strategies,
    url_strategy_capabilities,
)
from agentic_rag.ingestion.integration.url.reconciliation import reconcile_strategy_outputs
from agentic_rag.ingestion.integration.url.validation import validate_evidence_links


def test_registry_exposes_pipeline_capabilities() -> None:
    assert "crawlee" in supported_url_integration_strategies()
    assert url_strategy_capabilities("docling_html").supports_reading_order is True
    assert url_strategy_capabilities("vlm-region").requires_credentials is True


def test_static_html_uses_deterministic_path_without_browser_or_vlm() -> None:
    result = integrate_url(
        UrlIntegrationInput(
            requested_url="https://example.test/article",
            html=(
                "<html><head><title>Guide</title></head>"
                "<body><h1>Guide</h1><p>Useful text.</p></body></html>"
            ),
        ),
        config=UrlIntegrationConfig(
            render_policy="never", interaction_policy="never", vlm_policy="never"
        ),
    )

    assert result.status == "complete"
    assert result.chunking_input is not None
    assert "Useful text" in result.chunking_input.markdown
    selected = [
        trace.strategy
        for trace in result.payload.strategy_trace
        if trace.status == "selected"
    ]
    assert selected == [
        "supplied-html",
        "beautifulsoup",
    ]


def test_visual_gap_routes_only_to_injected_vlm_and_validates_citation() -> None:
    def vision(request, acquisition):
        del request, acquisition
        evidence = UrlEvidenceRef(
            evidence_id="chart-region-1",
            kind="screenshot",
            artifact_ref="artifacts/chart.png",
            strategy="vlm-region",
            origin="visually_inferred",
        )
        fact = UrlEvidenceFact(
            subject="Sales chart",
            attribute="2026 value",
            value="42",
            evidence_refs=(evidence.evidence_id,),
            extraction_strategy="vlm-region",
            confidence=0.9,
            origin="visually_inferred",
        )
        return UrlStrategyOutput(strategy="vlm-region", evidence=(evidence,), facts=(fact,))

    result = integrate_url(
        UrlIntegrationInput(
            requested_url="https://example.test/chart",
            html="<html><body><h1>Sales</h1><canvas></canvas></body></html>",
        ),
        config=UrlIntegrationConfig(
            render_policy="never", interaction_policy="never", vlm_policy="auto"
        ),
        adapters=UrlIntegrationAdapters(vision=vision),
    )

    assert result.payload.facts[0].validation_status == "validated"
    assert result.payload.facts[0].evidence_refs == ("chart-region-1",)


def test_direct_pdf_url_returns_handoff() -> None:
    result = integrate_url(
        UrlIntegrationInput(requested_url="https://example.test/policy.pdf")
    )

    assert result.status == "routed_to_pdf"
    assert result.pdf_handoff_url == "https://example.test/policy.pdf"
    assert result.chunking_input is None


def test_reconciliation_preserves_conflicting_values_for_review() -> None:
    evidence = tuple(
        UrlEvidenceRef(
            evidence_id=f"evidence-{index}",
            kind="dom_region",
            artifact_ref=f"memory://{index}",
            strategy="test",
        )
        for index in (1, 2)
    )
    facts = tuple(
        UrlEvidenceFact(
            subject="VF 9",
            attribute="price",
            value=value,
            evidence_refs=(evidence[index].evidence_id,),
            extraction_strategy="test",
            confidence=1.0,
        )
        for index, value in enumerate(("1.5 billion VND", "1.6 billion VND"))
    )

    _, reconciled, _, conflicts = reconcile_strategy_outputs(
        [UrlStrategyOutput(strategy="test", facts=facts, evidence=evidence)]
    )

    assert len(reconciled) == 2
    assert conflicts[0].values == ("1.5 billion VND", "1.6 billion VND")


def test_validation_rejects_uncited_visual_fact() -> None:
    fact = UrlEvidenceFact(
        subject="Chart",
        attribute="value",
        value="42",
        evidence_refs=(),
        extraction_strategy="vlm-region",
        confidence=0.9,
        origin="visually_inferred",
    )

    accepted, rejected = validate_evidence_links((), (fact,), ())

    assert accepted == ()
    assert rejected[0].validation_status == "rejected"
