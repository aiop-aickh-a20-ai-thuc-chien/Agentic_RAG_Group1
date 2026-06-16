"""URL-local ingestion quality diagnostics."""

from agentic_rag.ingestion.url.quality.diagnostics import (
    QualityVerdict,
    UrlQualityReport,
    analyze_url_quality,
    attach_quality_metadata,
)
from agentic_rag.ingestion.url.quality.strategy import (
    ParserKind,
    QualityGateStatus,
    UrlPageProfile,
    UrlQualityGate,
    attach_quality_gate_metadata,
    better_quality_gate,
    detect_page_profile,
    evaluate_quality_gate,
    score_url_quality,
    should_try_rendered_parser,
)

__all__ = [
    "ParserKind",
    "QualityGateStatus",
    "QualityVerdict",
    "UrlPageProfile",
    "UrlQualityGate",
    "UrlQualityReport",
    "analyze_url_quality",
    "attach_quality_gate_metadata",
    "attach_quality_metadata",
    "better_quality_gate",
    "detect_page_profile",
    "evaluate_quality_gate",
    "score_url_quality",
    "should_try_rendered_parser",
]
