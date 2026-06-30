"""Quality-first parser selection for URL ingestion."""

from __future__ import annotations

import re
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.url.quality.diagnostics import UrlQualityReport

QualityGateStatus = Literal["accepted", "partial", "rejected"]
ParserKind = Literal["static", "rendered"]

_RENDER_REQUIRED_PAGE_TYPES = {
    "booking_flow",
    "dynamic_application",
    "homepage_product_listing",
    "interactive_application",
    "product_detail",
    "product_listing",
    "vehicle_configurator",
}
_LATENCY_BUDGETS_SECONDS = {
    "article": 8,
    "policy": 8,
    "faq": 10,
    "product_detail": 20,
    "homepage_product_listing": 25,
    "product_listing": 25,
    "vehicle_configurator": 35,
    "booking_flow": 35,
    "interactive_application": 35,
    "dynamic_application": 35,
    "generic": 8,
}
_DYNAMIC_SIGNAL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("next_data", re.compile(r"__NEXT_DATA__", re.I)),
    ("react_root_attr", re.compile(r"data-reactroot", re.I)),
    ("initial_state", re.compile(r"window\.__INITIAL_STATE__", re.I)),
    ("root_container", re.compile(r"id=[\"']root[\"']", re.I)),
    ("next_container", re.compile(r"id=[\"']__next[\"']", re.I)),
    (
        "empty_root_container",
        re.compile(r"<[^>]+id=[\"'](?:root|__next)[\"'][^>]*>\s*</[^>]+>", re.I),
    ),
    ("next_static_bundle", re.compile(r"/_next/static/", re.I)),
)
_MODEL_RE = re.compile(r"\b(?:vinfast\s+)?vf\s*-?\s*[0-9][a-z0-9]*(?:\s+plus)?\b", re.I)
_PRICE_RE = re.compile(r"\b\d[\d.,]*\s*(?:vnd|vn\u0111|\u20ab|dong|usd|\$)\b", re.I)
_SPEC_RE = re.compile(
    r"\b(?:range|km|battery|pin|charging|sac|seats?|cho|capacity|cong suat|"
    r"torque|momen|kich thuoc|wheelbase|dong co)\b",
    re.I,
)
_NOISE_RE = re.compile(
    r"\b(cookie|copyright|privacy|terms of use|legal disclaimer|hotline|support|"
    r"all rights reserved|dang ky nhan tin|newsletter)\b",
    re.I,
)
_VINFAST_PRODUCT_SLUG_RE = re.compile(
    r"^(?:"
    r"vf-\d+|vf-e34|vf-energy|"
    r"limo-green|miniio-green|minio-green|herio-green|nerio-green|ec-van|"
    r"feliz|klara|vento|theon|evo|motio"
    r")(?:/)?$",
    re.I,
)


class UrlPageProfile(BaseModel):
    """Static page signals used before choosing the parser path."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    page_type: str
    requires_rendered_parser: bool
    dynamic_signals: list[str] = Field(default_factory=list)
    latency_budget_seconds: int
    reasons: list[str] = Field(default_factory=list)


class UrlQualityGate(BaseModel):
    """Decision metadata for one parser candidate."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    parser: ParserKind
    status: QualityGateStatus
    accepted: bool
    score: int
    reason: str
    page_type: str
    requires_rendered_parser: bool
    dynamic_signals: list[str] = Field(default_factory=list)
    latency_budget_seconds: int
    browser_error: str | None = None


def detect_page_profile(url: str, html: str) -> UrlPageProfile:
    """Classify a URL and static HTML before accepting parser output."""

    page_type = _classify_page_type(url)
    dynamic_signals = _dynamic_signals(html)
    reasons: list[str] = []
    if page_type in _RENDER_REQUIRED_PAGE_TYPES:
        reasons.append(f"page_type_requires_render:{page_type}")
    if dynamic_signals:
        reasons.append("dynamic_html_signals")
        if page_type == "generic":
            page_type = "dynamic_application"
    requires_rendered_parser = page_type in _RENDER_REQUIRED_PAGE_TYPES or bool(dynamic_signals)
    return UrlPageProfile(
        page_type=page_type,
        requires_rendered_parser=requires_rendered_parser,
        dynamic_signals=dynamic_signals,
        latency_budget_seconds=_LATENCY_BUDGETS_SECONDS.get(page_type, 8),
        reasons=reasons,
    )


def evaluate_quality_gate(
    *,
    parser: ParserKind,
    profile: UrlPageProfile,
    report: UrlQualityReport,
    chunks: list[Chunk],
    browser_error: str | None = None,
) -> UrlQualityGate:
    """Score parser output and decide whether it is acceptable."""

    score = score_url_quality(profile=profile, report=report, chunks=chunks)
    status = _status_for_score(score=score, profile=profile, report=report, chunks=chunks)
    reason = _reason_for_status(status=status, parser=parser, profile=profile, report=report)
    return UrlQualityGate(
        parser=parser,
        status=status,
        accepted=status == "accepted",
        score=score,
        reason=reason,
        page_type=profile.page_type,
        requires_rendered_parser=profile.requires_rendered_parser,
        dynamic_signals=profile.dynamic_signals,
        latency_budget_seconds=profile.latency_budget_seconds,
        browser_error=browser_error,
    )


def score_url_quality(
    *,
    profile: UrlPageProfile,
    report: UrlQualityReport,
    chunks: list[Chunk],
) -> int:
    """Compute a compact quality score using the guide's quality-first signals."""

    text = "\n\n".join(chunk.text for chunk in chunks)
    metadata = [chunk.metadata for chunk in chunks]
    score = 0
    if any(chunk.metadata.get("title") for chunk in chunks):
        score += 1
    if report.heading_count > 0:
        score += 1
    if report.markdown_word_count >= 40 and report.useful_chunk_count > 0:
        score += 2
    elif report.markdown_word_count >= 20 and report.useful_chunk_count > 0:
        score += 1
    if _has_product_entities(text, metadata):
        score += 2
    if _PRICE_RE.search(text):
        score += 2
    if _SPEC_RE.search(text):
        score += 2
    if report.boilerplate_hit_count >= 3 or _NOISE_RE.search(text):
        score -= 1
    if _is_react_shell(profile=profile, report=report, chunks=chunks):
        score -= 3

    # Calculate cross-model contamination penalty
    model_counts: dict[str, int] = {}
    for chunk in chunks:
        model = chunk.metadata.get("product_model") or chunk.metadata.get("entity_name")
        if isinstance(model, str):
            from agentic_rag.ingestion.url.entities.extractor import _MODEL_RE, _format_model_name
            match = _MODEL_RE.search(model)
            if match:
                formatted = _format_model_name(match.group(0))
                model_counts[formatted] = model_counts.get(formatted, 0) + 1

    if len(model_counts) > 1:
        total_matched_chunks = sum(model_counts.values())
        if total_matched_chunks > 0:
            dominant_model = max(model_counts, key=model_counts.get)
            dominant_count = model_counts[dominant_model]
            other_count = total_matched_chunks - dominant_count
            contamination_ratio = other_count / total_matched_chunks
            if contamination_ratio > 0.20:
                score -= 2
    return max(score, 0)


def should_try_rendered_parser(profile: UrlPageProfile, static_gate: UrlQualityGate) -> bool:
    """Return whether quality should be improved with a rendered parser."""

    if profile.requires_rendered_parser:
        return True
    return static_gate.status != "accepted"


def better_quality_gate(left: UrlQualityGate, right: UrlQualityGate) -> UrlQualityGate:
    """Return the stronger gate, preferring quality over latency."""

    left_key = (_status_rank(left.status), left.score)
    right_key = (_status_rank(right.status), right.score)
    return left if left_key >= right_key else right


def attach_quality_gate_metadata(chunks: list[Chunk], gate: UrlQualityGate) -> list[Chunk]:
    """Attach parser-selection diagnostics to chunk metadata."""

    payload = gate.model_dump()
    return [
        chunk.model_copy(
            update={
                "metadata": {
                    **chunk.metadata,
                    "page_type": gate.page_type,
                    "document_type": gate.page_type,
                    "url_status": gate.status,
                    "render_required": gate.requires_rendered_parser,
                    "url_quality_gate": payload,
                }
            }
        )
        for chunk in chunks
    ]


def _classify_page_type(url: str) -> str:
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    path = parsed.path.lower().strip("/")
    if "dat-coc" in path or "booking" in path:
        return "booking_flow"
    if "cau-hoi-thuong-gap" in path or "faq" in path:
        return "faq"
    if any(
        marker in path
        for marker in (
            "privacy",
            "terms",
            "policy",
            "chinh-sach",
            "dieu-khoan",
            "bao-hanh",
            "phap-ly",
        )
    ):
        return "policy"
    if "configurator" in path or "cau-hinh" in path:
        return "vehicle_configurator"
    if "shop.vinfastauto.com" in domain:
        if path.endswith(".html"):
            return "product_detail"
        return "product_listing"
    if "vinfastauto.com" in domain and path in {"", "vn_vi", "vn_en", "vi", "en"}:
        return "homepage_product_listing"
    if "vinfastauto.com" in domain and _is_vinfast_product_path(path):
        return "product_detail"
    if "tin-tuc" in path or "news" in path or "blog" in path:
        return "article"
    return "generic"


def _is_vinfast_product_path(path: str) -> bool:
    slug = path.rsplit("/", 1)[-1]
    return bool(_VINFAST_PRODUCT_SLUG_RE.match(slug))


def _dynamic_signals(html: str) -> list[str]:
    return [name for name, pattern in _DYNAMIC_SIGNAL_PATTERNS if pattern.search(html)]


def _status_for_score(
    *,
    score: int,
    profile: UrlPageProfile,
    report: UrlQualityReport,
    chunks: list[Chunk],
) -> QualityGateStatus:
    if report.verdict == "empty" or not chunks:
        return "rejected"
    if score >= 7:
        return "accepted"
    if report.verdict == "useful" and not profile.requires_rendered_parser:
        return "accepted"
    if score >= 4:
        return "partial"
    return "rejected"


def _reason_for_status(
    *,
    status: QualityGateStatus,
    parser: ParserKind,
    profile: UrlPageProfile,
    report: UrlQualityReport,
) -> str:
    if status == "accepted":
        if profile.requires_rendered_parser and parser == "rendered":
            return "rendered_parser_satisfied_quality_gate"
        return "parser_output_satisfied_quality_gate"
    if status == "partial":
        return "parser_output_marked_partial_for_review"
    if report.issues:
        return "parser_output_rejected:" + ",".join(report.issues[:4])
    return "parser_output_rejected:low_url_signal"


def _has_product_entities(text: str, metadata: list[dict[str, object]]) -> bool:
    if _MODEL_RE.search(text):
        return True
    for item in metadata:
        entity_types = item.get("entity_types")
        if isinstance(entity_types, dict) and (
            entity_types.get("vehicle") or entity_types.get("product")
        ):
            return True
        if item.get("entity_type") in {"vehicle", "product"}:
            return True
    return False


def _is_react_shell(
    *,
    profile: UrlPageProfile,
    report: UrlQualityReport,
    chunks: list[Chunk],
) -> bool:
    if not profile.dynamic_signals:
        return False
    if report.markdown_word_count < 20:
        return True
    return not any(_MODEL_RE.search(chunk.text) or _PRICE_RE.search(chunk.text) for chunk in chunks)


def _status_rank(status: QualityGateStatus) -> int:
    return {"rejected": 0, "partial": 1, "accepted": 2}[status]


__all__ = [
    "ParserKind",
    "QualityGateStatus",
    "UrlPageProfile",
    "UrlQualityGate",
    "attach_quality_gate_metadata",
    "better_quality_gate",
    "detect_page_profile",
    "evaluate_quality_gate",
    "score_url_quality",
    "should_try_rendered_parser",
]
