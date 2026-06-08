# Signal Decoder Reference

Extract and interpret diagnostic signals from `manifest.json`, `chunks.jsonl`,
and `crawl_review.md`. This is always the first step in diagnosis.

---

## 1. Data Models

```python
from pydantic import BaseModel
from enum import Enum
from typing import Any

class RenderTier(str, Enum):
    STATIC_HTML       = "static_html"       # Tier 0
    LOAD              = "load"              # Tier 1 — Crawl4AI default
    NETWORKIDLE       = "networkidle"       # Tier 2
    NETWORKIDLE_SCROLL = "networkidle+scroll"  # Tier 3
    MANAGED_BROWSER   = "managed_browser"  # Tier 4

class IssueType(str, Enum):
    SPA_NOT_WAITED      = "spa_not_waited"
    LAZY_LOAD_MISSED    = "lazy_load_missed"
    BOT_DETECTION       = "bot_detection"
    REDIRECT_CONTEXT    = "redirect_context"
    TIMEOUT_EARLY_EXIT  = "timeout_early_exit"
    RETRY_SHORT_CIRCUIT = "retry_short_circuit"
    STATIC_SUFFICIENT   = "static_sufficient"
    UNKNOWN_THIN        = "unknown_thin"

class CrawlSignals(BaseModel):
    # From chunk metadata
    url: str
    status_code: int
    wait_until_target: str             # "load" | "networkidle" | etc.
    crawl_attempt_duration_seconds: float
    crawl_attempt_count: int
    configured_crawl_attempt_count: int
    crawler: str                       # "crawl4ai" | "trafilatura" | "urllib"
    crawler_error: str | None

    # From markdown_quality
    selected_role: str                 # "crawl4ai_primary" | "builtin_fallback" | ...
    fallback_reason: str | None
    selected_token_count: int
    primary_score: int                 # score of crawl4ai_primary candidate
    all_candidates: list[dict]         # full candidates list

    # From manifest assets
    has_recaptcha: bool
    has_gtm: bool                      # Google Tag Manager
    has_facebook_pixel: bool
    has_admicro: bool                  # Vietnamese ad network — common bot signal
    iframe_count: int
    asset_urls: list[str]

    # From manifest page_metadata
    og_title: str | None
    og_url: str | None
    language: str | None
    canonical_url: str | None
    final_url: str

    # Derived
    chunk_count: int
    total_tokens: int                  # sum across all chunks

class CrawlDiagnosis(BaseModel):
    signals: CrawlSignals
    quality_score: int                 # 0–100
    verdict: str                       # "good" | "marginal" | "poor"
    render_tier: RenderTier            # tier that was used
    issues: list[IssueType]
    recommended_tier: RenderTier
    recommended_config: dict[str, Any]
    bot_signals: list[str]             # human-readable list of detected bot signals
```

---

## 2. Signal Extractor

```python
import json
from pathlib import Path

def extract_signals(
    manifest: dict,
    chunks: list[dict],
) -> CrawlSignals:
    """
    Extract all diagnostic signals from manifest.json and chunks.jsonl.
    Reads every field that matters for diagnosis — never skips fields.
    """
    # --- From first chunk metadata (most fields live here) ---
    meta = chunks[0]["metadata"] if chunks else {}
    mq   = meta.get("markdown_quality", {})
    candidates = mq.get("candidates", [])

    # Find crawl4ai_primary candidate score
    primary_score = next(
        (c["score"] for c in candidates if c["role"] == "crawl4ai_primary"),
        0
    )
    selected_token_count = next(
        (c["token_count"] for c in candidates
         if c["role"] == mq.get("selected_role", "")),
        0
    )

    # --- From manifest assets ---
    assets     = manifest.get("assets", [])
    asset_urls = [a.get("url", "") for a in assets]

    bot_signals = []
    has_recaptcha     = any("recaptcha" in u for u in asset_urls)
    has_gtm           = any("googletagmanager" in u for u in asset_urls)
    has_facebook_pixel = any("facebook.com/tr" in u for u in asset_urls)
    has_admicro       = any("admicro" in u for u in asset_urls)

    if has_recaptcha:      bot_signals.append("reCAPTCHA iframe detected")
    if has_gtm:            bot_signals.append("Google Tag Manager iframe")
    if has_facebook_pixel: bot_signals.append(f"Facebook Pixel ({sum(1 for u in asset_urls if 'facebook.com/tr' in u)} pixels)")
    if has_admicro:        bot_signals.append("Admicro tracking iframe (Vietnamese ad network)")

    # --- Aggregate token count across all chunks ---
    total_tokens = sum(
        c["metadata"].get("chunk_token_count", 0) for c in chunks
    )

    return CrawlSignals(
        url=meta.get("url", manifest.get("input_url", "")),
        status_code=meta.get("status_code", 0),
        wait_until_target=meta.get("wait_until_target", "load"),
        crawl_attempt_duration_seconds=meta.get("crawl_attempt_duration_seconds", 0),
        crawl_attempt_count=meta.get("crawl_attempt_count", 1),
        configured_crawl_attempt_count=meta.get("configured_crawl_attempt_count", 1),
        crawler=meta.get("crawler", "unknown"),
        crawler_error=meta.get("crawler_error"),

        selected_role=mq.get("selected_role", ""),
        fallback_reason=mq.get("fallback_reason"),
        selected_token_count=selected_token_count,
        primary_score=primary_score,
        all_candidates=candidates,

        has_recaptcha=has_recaptcha,
        has_gtm=has_gtm,
        has_facebook_pixel=has_facebook_pixel,
        has_admicro=has_admicro,
        iframe_count=sum(1 for a in assets if a.get("kind") == "iframe"),
        asset_urls=asset_urls,

        og_title=manifest.get("page_metadata", {}).get("og_title"),
        og_url=manifest.get("page_metadata", {}).get("og_url"),
        language=manifest.get("page_metadata", {}).get("language"),
        canonical_url=manifest.get("canonical_url"),
        final_url=manifest.get("final_url", ""),

        chunk_count=len(chunks),
        total_tokens=total_tokens,
    )
```

---

## 3. Quality Scorer

```python
def score_crawl_result(signals: CrawlSignals) -> tuple[int, str]:
    """
    Score a crawl result 0–100. Returns (score, verdict).
    Deductions are cumulative — a page can score 0 if everything is wrong.
    """
    score = 100
    deductions = []

    if signals.selected_token_count < 50:
        score -= 40
        deductions.append(f"−40: token_count={signals.selected_token_count} (< 50, near-empty)")
    elif signals.selected_token_count < 200:
        score -= 20
        deductions.append(f"−20: token_count={signals.selected_token_count} (< 200, thin)")

    if signals.selected_role == "builtin_fallback":
        score -= 20
        deductions.append("−20: selected_role=builtin_fallback (all real parsers failed)")

    if signals.primary_score < 0:
        score -= 15
        deductions.append(f"−15: crawl4ai_primary score={signals.primary_score} (negative)")

    if signals.status_code in (301, 302):
        score -= 10
        deductions.append(f"−10: status_code={signals.status_code} (redirect)")

    if signals.wait_until_target == "load":
        score -= 10
        deductions.append("−10: wait_until=load (SPA content likely not rendered)")

    if signals.has_recaptcha:
        score -= 15
        deductions.append("−15: reCAPTCHA detected (bot-detection active)")

    if signals.crawl_attempt_duration_seconds > 30:
        score -= 5
        deductions.append(f"−5: duration={signals.crawl_attempt_duration_seconds:.1f}s (> 30s, likely timed out)")

    if signals.crawl_attempt_count < signals.configured_crawl_attempt_count:
        score -= 5
        deductions.append(f"−5: only {signals.crawl_attempt_count}/{signals.configured_crawl_attempt_count} attempts made")

    score = max(0, score)

    if score >= 70:
        verdict = "good"
    elif score >= 40:
        verdict = "marginal"
    else:
        verdict = "poor"

    return score, verdict, deductions


def explain_score(signals: CrawlSignals) -> str:
    """Human-readable diagnosis summary — use in logs and DiagnosisReport."""
    score, verdict, deductions = score_crawl_result(signals)
    lines = [
        f"Quality Score: {score}/100 ({verdict.upper()})",
        f"URL: {signals.url}",
        f"Render tier used: {signals.wait_until_target}",
        f"Token count: {signals.selected_token_count} (selected parser)",
        f"Parser role: {signals.selected_role}",
        "",
        "Deductions:",
    ]
    lines += [f"  {d}" for d in deductions] or ["  (none)"]

    if signals.bot_signals:
        lines += ["", "Bot-detection signals:"]
        lines += [f"  • {s}" for s in signals.bot_signals]

    lines += ["", f"Recommended next step: see render-tiers.md for tier escalation"]
    return "\n".join(lines)
```

---

## 4. Full Entry Point

```python
def score_crawl_result(manifest: dict, chunks: list[dict]) -> CrawlDiagnosis:
    """
    Top-level function called by the crawl pipeline after every crawl.
    Returns a full CrawlDiagnosis ready for render-tier escalation.
    """
    from .issue_rules import detect_issues, recommend_tier

    signals = extract_signals(manifest, chunks)
    score, verdict, _ = score_crawl_result(signals)
    issues = detect_issues(signals)
    recommended_tier, recommended_config = recommend_tier(issues, signals)

    return CrawlDiagnosis(
        signals=signals,
        quality_score=score,
        verdict=verdict,
        render_tier=RenderTier(signals.wait_until_target),
        issues=issues,
        recommended_tier=recommended_tier,
        recommended_config=recommended_config,
        bot_signals=signals.bot_signals,
    )
```

---

## 5. Loading from Files

```python
def load_from_files(
    manifest_path: str,
    chunks_path: str,
) -> CrawlDiagnosis:
    """Load manifest.json and chunks.jsonl from disk and run diagnosis."""
    with open(manifest_path) as f:
        manifest = json.load(f)
    with open(chunks_path) as f:
        chunks = [json.loads(line) for line in f if line.strip()]
    return score_crawl_result(manifest, chunks)


# CLI usage:
# python -m crawler.diagnosis manifest.json chunks.jsonl
if __name__ == "__main__":
    import sys
    diag = load_from_files(sys.argv[1], sys.argv[2])
    signals = diag.signals
    print(explain_score(signals))
```
