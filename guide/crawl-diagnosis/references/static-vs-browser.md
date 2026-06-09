# Static vs Browser Decision Matrix

When to use `httpx` (static HTML) vs Crawl4AI headless browser.
Always prefer static when it is sufficient — browsers are slower,
heavier, and trigger bot-detection more aggressively.

---

## Decision Function

```python
from urllib.parse import urlparse
import re

# URL patterns that are always static — skip the browser entirely
ALWAYS_STATIC_PATTERNS = [
    r"/robots\.txt$",
    r"/sitemap.*\.xml",
    r"\.xml$",
    r"\.json$",
    r"\.csv$",
    r"\.txt$",
    r"/feed/?$",
    r"/rss/?$",
    r"/api/",
    r"\.atom$",
]

# URL patterns that always require a browser
ALWAYS_BROWSER_PATTERNS = [
    r"/#",                   # hash-routed SPA
    r"\?lang=",              # JS-driven locale switch
    r"/vn_vi",               # VinFast locale path — JS-rendered
    r"/en_us",
    r"\.react\.",
    r"/__next/",             # Next.js specific paths
]

# Content-type values that mean static is fine
STATIC_CONTENT_TYPES = {
    "application/json",
    "application/xml",
    "text/xml",
    "text/plain",
    "application/rss+xml",
    "application/atom+xml",
}

def should_use_static(
    url: str,
    *,
    content_type: str | None = None,        # from HEAD request if available
    prior_diagnosis: "CrawlDiagnosis | None" = None,
) -> bool:
    """
    Decide whether to use static httpx fetch vs headless browser.

    Evaluation order:
    1. URL pattern hard rules (fastest — no network needed)
    2. Content-type from HEAD request (if provided)
    3. Prior diagnosis signals (if a crawl was already attempted)
    4. Default to browser (safe fallback)
    """

    # ── 1. URL pattern hard rules ────────────────────────────────────────────
    path = urlparse(url).path.lower()
    full = url.lower()

    for pattern in ALWAYS_STATIC_PATTERNS:
        if re.search(pattern, full):
            return True   # definitely static

    for pattern in ALWAYS_BROWSER_PATTERNS:
        if re.search(pattern, full):
            return False  # definitely needs browser

    # ── 2. Content-type from HEAD (optional fast probe) ──────────────────────
    if content_type:
        base_type = content_type.split(";")[0].strip().lower()
        if base_type in STATIC_CONTENT_TYPES:
            return True
        if "text/html" in base_type:
            pass  # HTML could be SPA — continue evaluation

    # ── 3. Prior diagnosis signals ───────────────────────────────────────────
    if prior_diagnosis:
        signals = prior_diagnosis.signals

        # Already rich at load tier with no bot signals → static will work
        if (signals.selected_token_count > 500
                and signals.wait_until_target == "load"
                and not signals.has_recaptcha
                and not signals.has_gtm
                and signals.primary_score > 0):
            return True

        # Bot signals or thin result at load tier → browser required
        if signals.has_recaptcha or signals.has_admicro:
            return False
        if signals.primary_score < 0:
            return False

    # ── 4. Default to browser ────────────────────────────────────────────────
    # When in doubt, use the browser — static fetch failing silently is worse
    # than a slower but correct browser render.
    return False
```

---

## HEAD Request Probe (Optional Fast Path)

Before committing to a full browser crawl, a cheap HEAD request can reveal
if the page is static:

```python
import httpx

async def probe_content_type(url: str) -> str | None:
    """
    Send a HEAD request to check content-type before deciding render strategy.
    Returns content-type string or None if probe fails.
    Cost: ~50ms vs ~5000ms for a browser render.
    """
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=8) as client:
            r = await client.head(url, headers={"User-Agent": "Mozilla/5.0"})
            return r.headers.get("content-type", "")
    except Exception:
        return None


async def decide_render_strategy(
    url: str,
    prior_diagnosis: "CrawlDiagnosis | None" = None,
    *,
    do_head_probe: bool = True,
) -> str:
    """
    Returns "static_html" | "load" | "networkidle" | "networkidle+scroll" | "managed_browser"

    Uses cheapest available signal first:
    1. URL pattern check (no network)
    2. HEAD probe for content-type (one cheap request)
    3. Prior diagnosis if available
    4. Default to "networkidle" (safe for most HTML pages)
    """
    # URL pattern first — no network cost
    if re.search(r"/robots\.txt$|/sitemap.*\.xml|\.xml$|\.json$", url.lower()):
        return "static_html"

    # HEAD probe
    content_type = None
    if do_head_probe:
        content_type = await probe_content_type(url)
        if content_type:
            base = content_type.split(";")[0].strip().lower()
            if base in STATIC_CONTENT_TYPES:
                return "static_html"

    # Prior diagnosis
    if prior_diagnosis:
        from .issue_rules import recommend_tier, detect_issues
        recommended, _ = recommend_tier(prior_diagnosis.issues, prior_diagnosis.signals)
        return recommended.value

    # Default: networkidle is safer than load for unknown HTML pages
    return "networkidle"
```

---

## Decision Matrix (Quick Reference)

| Condition | Use static? | Use browser tier |
|---|---|---|
| URL ends in `.xml`, `.json`, `.txt` | ✅ Yes | — |
| URL is `/robots.txt` or `/sitemap` | ✅ Yes | — |
| URL is a known API endpoint | ✅ Yes | — |
| Content-Type is `application/json` | ✅ Yes | — |
| Prior crawl: tokens > 500, no bot signals | ✅ Yes | — |
| URL contains `/#`, `?lang=`, `/vn_vi` | ❌ No | Tier 2+ |
| Prior crawl: reCAPTCHA detected | ❌ No | Tier 4 |
| Prior crawl: primary_score < 0 | ❌ No | Tier 2+ |
| Prior crawl: wait_until=load, tokens < 50 | ❌ No | Tier 2+ |
| Google Tag Manager iframe in assets | ❌ No | Tier 2+ |
| Unknown new URL, no prior data | ❌ No | Tier 2 (safe default) |

---

## Integration with the Crawl Pipeline

```python
async def smart_crawl(url: str, prior_manifest: dict | None = None,
                       prior_chunks: list | None = None) -> tuple[str, CrawlDiagnosis]:
    """
    Full pipeline: decide strategy → crawl → diagnose → escalate if needed.
    """
    from .signal_decoder import extract_signals, score_crawl_result
    from .render_tiers import crawl_with_diagnosis

    # Build prior diagnosis if we have prior crawl data
    prior_diag = None
    if prior_manifest and prior_chunks:
        signals = extract_signals(prior_manifest, prior_chunks)
        score, verdict, _ = score_crawl_result(signals)
        prior_diag = CrawlDiagnosis(signals=signals, quality_score=score,
                                     verdict=verdict, ...)

    # Decide starting strategy
    start_strategy = await decide_render_strategy(url, prior_diag)

    if start_strategy == "static_html":
        html = await fetch_static(url)
        return html, _static_diagnosis(url)

    start_tier = ["load", "networkidle", "networkidle+scroll", "managed_browser"]\
                 .index(start_strategy) + 1

    return await crawl_with_diagnosis(
        url,
        manifest=prior_manifest,
        chunks=prior_chunks,
        start_tier=start_tier,
        quality_threshold=70,
    )
```
