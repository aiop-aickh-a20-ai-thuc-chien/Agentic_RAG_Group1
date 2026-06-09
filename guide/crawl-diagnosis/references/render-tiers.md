# Render Tiers Reference

Concrete Crawl4AI configuration for each render tier and the full
quality-gated escalation loop.

---

## Tier Configs

### Tier 0 — Static HTML (`httpx`, no browser)

Use when `STATIC_SUFFICIENT` is detected or URL is known static
(sitemap, robots.txt, JSON API, XML feed).

```python
import httpx
from bs4 import BeautifulSoup

async def fetch_static(url: str) -> str:
    """
    Pure HTTP fetch — no browser, no JS execution.
    Fastest option; fails silently if page requires JS.
    """
    async with httpx.AsyncClient(
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html,application/xhtml+xml",
        },
        follow_redirects=True,
        timeout=15,
    ) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.text

STATIC_URL_PATTERNS = [
    r"\.xml$", r"\.json$", r"\.txt$",
    r"/robots\.txt", r"/sitemap",
    r"/api/", r"/feed",
]

def is_static_url(url: str) -> bool:
    import re
    return any(re.search(p, url) for p in STATIC_URL_PATTERNS)
```

---

### Tier 1 — Browser, `wait_until: load` (Crawl4AI default)

The repo baseline. Sufficient for server-rendered pages that don't need JS.

```python
from crawl4ai import CrawlerRunConfig, BrowserConfig

TIER1_CONFIG = CrawlerRunConfig(
    wait_until="load",
    page_timeout=30000,
    follow_redirects=True,
    check_robots_txt=True,
    generate_markdown=True,
)
```

---

### Tier 2 — `wait_until: networkidle`

Use for SPAs (React, Next.js, Vue) where JS renders the content after load.
Fixes: `SPA_NOT_WAITED`, `REDIRECT_CONTEXT`, `TIMEOUT_EARLY_EXIT`,
`RETRY_SHORT_CIRCUIT`, `UNKNOWN_THIN`.

```python
TIER2_CONFIG = CrawlerRunConfig(
    wait_until="networkidle",    # wait until no network requests for 500ms
    page_timeout=60000,          # 60s — SPAs need more time
    follow_redirects=True,
    check_robots_txt=True,
    generate_markdown=True,
)
```

---

### Tier 3 — `networkidle` + JS scroll injection

Use when networkidle catches the initial render but below-fold content
(carousels, lazy-loaded car cards) is still missing.
Fixes: `LAZY_LOAD_MISSED`.

```python
SCROLL_JS = """
await new Promise(resolve => {
    let totalHeight = 0;
    const distance = 300;
    const timer = setInterval(() => {
        window.scrollBy(0, distance);
        totalHeight += distance;
        if (totalHeight >= document.body.scrollHeight) {
            clearInterval(timer);
            resolve();
        }
    }, 200);
});
"""

TIER3_CONFIG = CrawlerRunConfig(
    wait_until="networkidle",
    page_timeout=60000,
    follow_redirects=True,
    check_robots_txt=True,
    generate_markdown=True,
    js_code=SCROLL_JS,
    # Wait for a content selector that only appears post-render
    # Selector is generic — do NOT hardcode site-specific class names
    wait_for="css:h2, css:article, css:[class*='product'], css:[class*='car'], css:[class*='item']",
)
```

---

### Tier 4 — Managed browser (most human-like)

Use when bot-detection (reCAPTCHA, fingerprinting) is blocking content.
Most resource-intensive — only escalate here when Tier 3 still fails.
Fixes: `BOT_DETECTION`.

```python
from crawl4ai import BrowserConfig

def build_tier4_config(language: str | None = None) -> tuple[CrawlerRunConfig, BrowserConfig]:
    """
    Builds managed browser config with locale-appropriate headers.
    Language is detected from manifest — not hardcoded.
    """
    from .issue_rules import _accept_language_for, SCROLL_JS

    browser_config = BrowserConfig(
        headless=True,
        use_managed_browser=True,    # persistent browser profile — less bot-like
        java_script_enabled=True,
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        headers={
            "Accept-Language": _accept_language_for(language),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": "https://www.google.com/",  # appear to come from search
        },
    )

    run_config = CrawlerRunConfig(
        wait_until="networkidle",
        page_timeout=90000,           # 90s — reCAPTCHA can take 30s alone
        follow_redirects=True,
        check_robots_txt=True,
        generate_markdown=True,
        js_code=SCROLL_JS,
        wait_for="css:h2, css:article, css:[class*='product']",
    )

    return run_config, browser_config
```

---

## Full Escalation Loop

```python
from crawl4ai import AsyncWebCrawler
from .signal_decoder import extract_signals, score_crawl_result, CrawlDiagnosis
from .issue_rules import detect_issues, recommend_tier, _build_config_for_tier
from .static_vs_browser import should_use_static

TIER_CONFIGS = {
    "static_html":        None,           # handled separately
    "load":               TIER1_CONFIG,
    "networkidle":        TIER2_CONFIG,
    "networkidle+scroll": TIER3_CONFIG,
    "managed_browser":    None,           # built dynamically with build_tier4_config()
}

async def crawl_with_diagnosis(
    url: str,
    manifest: dict | None = None,
    chunks: list[dict] | None = None,
    *,
    quality_threshold: int = 70,
    max_tier: int = 4,              # 0=static, 1=load, 2=networkidle, 3=scroll, 4=managed
    start_tier: int = 1,            # override to skip tiers when already known
) -> tuple[str, CrawlDiagnosis]:
    """
    Crawl with automatic quality-gated tier escalation.

    If manifest + chunks are provided (from a prior crawl attempt), diagnosis
    starts from those — avoids an extra crawl at the baseline tier.

    Returns: (best_html, final_diagnosis)
    """
    TIER_NAMES = ["static_html", "load", "networkidle", "networkidle+scroll", "managed_browser"]

    # --- Pre-check: should we use static HTML at all? ---
    if should_use_static(url):
        html = await fetch_static(url)
        # Build a synthetic diagnosis
        return html, CrawlDiagnosis(
            quality_score=90, verdict="good",
            render_tier="static_html", issues=[], recommended_tier="static_html",
            recommended_config={}, bot_signals=[], accepted=True,
            tiers_attempted=["static_html"],
        )

    current_tier = start_tier
    best_html = ""
    best_diagnosis = None
    tiers_attempted = []

    # --- If prior crawl data given, diagnose it first ---
    if manifest and chunks:
        signals = extract_signals(manifest, chunks)
        score, verdict, _ = score_crawl_result(signals)
        issues = detect_issues(signals)
        recommended, config = recommend_tier(issues, signals)
        best_diagnosis = CrawlDiagnosis(
            signals=signals, quality_score=score, verdict=verdict,
            render_tier="load", issues=issues,
            recommended_tier=recommended, recommended_config=config,
            bot_signals=signals.bot_signals, accepted=(score >= quality_threshold),
            tiers_attempted=["load"],
        )
        if score >= quality_threshold:
            return best_html, best_diagnosis  # prior result was good enough
        # Start escalation at recommended tier
        current_tier = TIER_NAMES.index(recommended.value)

    # --- Escalation loop ---
    async with AsyncWebCrawler() as crawler:
        while current_tier <= max_tier:
            tier_name = TIER_NAMES[current_tier]
            tiers_attempted.append(tier_name)

            # Build config for this tier
            if tier_name == "managed_browser":
                lang = best_diagnosis.signals.language if best_diagnosis else None
                run_config, browser_config = build_tier4_config(lang)
                result = await crawler.arun(url, config=run_config,
                                             browser_config=browser_config)
            else:
                run_config = TIER_CONFIGS[tier_name]
                result = await crawler.arun(url, config=run_config)

            # Score the new result
            # (In real repo: save result to temp manifest/chunks, then score)
            new_score = _quick_score(result)

            if new_score >= quality_threshold:
                # Accepted — return
                return result.html, CrawlDiagnosis(
                    quality_score=new_score, verdict="good",
                    render_tier=tier_name, issues=[],
                    recommended_tier=tier_name, recommended_config={},
                    bot_signals=[], accepted=True,
                    tiers_attempted=tiers_attempted,
                )

            current_tier += 1

    # All tiers exhausted — return best we got with "poor" verdict
    return best_html, CrawlDiagnosis(
        quality_score=new_score, verdict="poor",
        render_tier=tier_name, issues=best_diagnosis.issues if best_diagnosis else [],
        recommended_tier="managed_browser",
        recommended_config={"note": "All tiers exhausted — manual review required"},
        bot_signals=best_diagnosis.bot_signals if best_diagnosis else [],
        accepted=False,
        tiers_attempted=tiers_attempted,
    )


def _quick_score(result) -> int:
    """
    Fast score from a live CrawlResult — no manifest file needed.
    Uses markdown length as a proxy for token count.
    """
    if not result.success:
        return 0
    md_len = len(result.markdown or "")
    if md_len > 2000:   return 90
    if md_len > 500:    return 65
    if md_len > 100:    return 40
    return 10
```

---

## Escalation Decision Table

Quick reference for which tier to jump to given current tier + issue:

| Current tier | Issue | Jump to |
|---|---|---|
| load | SPA_NOT_WAITED | networkidle |
| load | BOT_DETECTION | managed_browser |
| load | REDIRECT_CONTEXT | networkidle (on final_url) |
| networkidle | LAZY_LOAD_MISSED | networkidle+scroll |
| networkidle | BOT_DETECTION | managed_browser |
| networkidle+scroll | BOT_DETECTION | managed_browser |
| any | STATIC_SUFFICIENT | static_html (downgrade) |
| managed_browser | still poor | Log + flag for manual review |
