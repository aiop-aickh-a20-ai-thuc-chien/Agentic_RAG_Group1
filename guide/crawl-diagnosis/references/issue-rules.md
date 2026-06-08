# Issue Rules Reference

Full decision tree for detecting issue types from diagnostic signals,
and mapping them to recommended render tiers.

---

## 1. Issue Detection (Evaluated in Priority Order)

```python
from .signal_decoder import CrawlSignals, IssueType, RenderTier

def detect_issues(signals: CrawlSignals) -> list[IssueType]:
    """
    Evaluate all issue rules in priority order.
    Multiple issues can be detected simultaneously.
    Returns a list ordered from highest-priority to lowest.
    """
    issues = []

    # ── Rule 1: SPA not waited ────────────────────────────────────────────────
    # Strongest signal: load was used AND the primary parser scored negative.
    # This means the JS bundle hadn't run when the snapshot was taken.
    if (signals.wait_until_target == "load"
            and signals.primary_score < 0
            and signals.selected_token_count < 100):
        issues.append(IssueType.SPA_NOT_WAITED)

    # ── Rule 2: Bot detection ─────────────────────────────────────────────────
    # reCAPTCHA is the clearest signal. Admicro + Facebook Pixel together
    # also suggest the page fingerprints headless browsers.
    if signals.has_recaptcha:
        issues.append(IssueType.BOT_DETECTION)
    elif signals.has_admicro and signals.has_facebook_pixel and signals.selected_token_count < 100:
        issues.append(IssueType.BOT_DETECTION)

    # ── Rule 3: Redirect lost JS context ─────────────────────────────────────
    # A 301/302 with thin content suggests the redirect dropped the browser's
    # JS session. Re-crawling the final_url directly often fixes this.
    if (signals.status_code in (301, 302)
            and signals.selected_token_count < 50
            and signals.final_url != signals.url):
        issues.append(IssueType.REDIRECT_CONTEXT)

    # ── Rule 4: Timeout / early exit ─────────────────────────────────────────
    # >30s on a single page with thin content = the crawler hung waiting for
    # JS but gave up before the SPA finished rendering.
    if (signals.crawl_attempt_duration_seconds > 30
            and signals.selected_token_count < 100):
        issues.append(IssueType.TIMEOUT_EARLY_EXIT)

    # ── Rule 5: Retries short-circuited ──────────────────────────────────────
    # If fewer attempts were made than configured, the retry logic treated
    # a non-error (e.g. 3xx) as terminal. Force retry at escalated tier.
    if signals.crawl_attempt_count < signals.configured_crawl_attempt_count:
        issues.append(IssueType.RETRY_SHORT_CIRCUIT)

    # ── Rule 6: Lazy-load missed ──────────────────────────────────────────────
    # Only detected AFTER SPA_NOT_WAITED is resolved (i.e. networkidle was used)
    # but content is still thin. Carousels and below-fold sections need scroll.
    if (signals.wait_until_target in ("networkidle", "networkidle+scroll")
            and signals.selected_token_count < 100
            and IssueType.BOT_DETECTION not in issues):
        issues.append(IssueType.LAZY_LOAD_MISSED)

    # ── Rule 7: Static HTML sufficient ────────────────────────────────────────
    # Pages that are pure server-rendered HTML should skip the browser entirely.
    # Detect: high token count at load tier, no SPA signals, no bot signals.
    if (signals.selected_token_count > 500
            and signals.wait_until_target == "load"
            and not signals.has_recaptcha
            and not signals.has_gtm
            and signals.primary_score > 0):
        issues.append(IssueType.STATIC_SUFFICIENT)

    # ── Rule 8: Unknown thin ─────────────────────────────────────────────────
    # Catch-all: thin content but no clear diagnosis.
    if (not issues
            and signals.selected_token_count < 100):
        issues.append(IssueType.UNKNOWN_THIN)

    return issues
```

---

## 2. Tier Recommender

```python
# Priority order for issue-to-tier mapping.
# If multiple issues are present, the highest tier wins.
ISSUE_TIER_MAP: dict[IssueType, RenderTier] = {
    IssueType.SPA_NOT_WAITED:      RenderTier.NETWORKIDLE,
    IssueType.LAZY_LOAD_MISSED:    RenderTier.NETWORKIDLE_SCROLL,
    IssueType.BOT_DETECTION:       RenderTier.MANAGED_BROWSER,
    IssueType.REDIRECT_CONTEXT:    RenderTier.NETWORKIDLE,
    IssueType.TIMEOUT_EARLY_EXIT:  RenderTier.NETWORKIDLE,
    IssueType.RETRY_SHORT_CIRCUIT: RenderTier.NETWORKIDLE,
    IssueType.STATIC_SUFFICIENT:   RenderTier.STATIC_HTML,
    IssueType.UNKNOWN_THIN:        RenderTier.NETWORKIDLE,
}

TIER_ORDER = [
    RenderTier.STATIC_HTML,
    RenderTier.LOAD,
    RenderTier.NETWORKIDLE,
    RenderTier.NETWORKIDLE_SCROLL,
    RenderTier.MANAGED_BROWSER,
]

def recommend_tier(
    issues: list[IssueType],
    signals: CrawlSignals,
) -> tuple[RenderTier, dict]:
    """
    Given detected issues, return the recommended render tier and
    the concrete config dict to pass to _build_run_config().

    Takes the highest tier across all issues — never downgrades.
    """
    if not issues:
        # No issues = current tier was fine
        return RenderTier(signals.wait_until_target), {}

    # Special case: STATIC_SUFFICIENT overrides everything downward
    if issues == [IssueType.STATIC_SUFFICIENT]:
        return RenderTier.STATIC_HTML, {"use_browser": False}

    # For all other issues, take the maximum tier
    recommended = max(
        (ISSUE_TIER_MAP[i] for i in issues if i != IssueType.STATIC_SUFFICIENT),
        key=lambda t: TIER_ORDER.index(t),
        default=RenderTier.NETWORKIDLE,
    )

    config = _build_config_for_tier(recommended, signals)
    return recommended, config


def _build_config_for_tier(tier: RenderTier, signals: CrawlSignals) -> dict:
    """
    Build the concrete Crawl4AI config changes for a given render tier.
    Always cumulative — higher tiers include all lower tier settings.
    """
    base = {
        "follow_redirects": True,
        "page_timeout": 60000,
    }

    if tier == RenderTier.STATIC_HTML:
        return {"use_browser": False}

    if tier == RenderTier.LOAD:
        return {**base, "wait_until": "load"}

    if tier == RenderTier.NETWORKIDLE:
        return {
            **base,
            "wait_until": "networkidle",
            # Crawl the final_url directly if there was a redirect
            "url_override": signals.final_url if signals.status_code in (301, 302) else None,
        }

    if tier == RenderTier.NETWORKIDLE_SCROLL:
        return {
            **base,
            "wait_until": "networkidle",
            "js_code": _SCROLL_JS,
            "wait_for": "css:h2, css:[class*='product'], css:[class*='car'], css:[class*='vehicle']",
        }

    if tier == RenderTier.MANAGED_BROWSER:
        return {
            **base,
            "wait_until": "networkidle",
            "js_code": _SCROLL_JS,
            "use_managed_browser": True,
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "headers": {
                "Accept-Language": _accept_language_for(signals.language),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Referer": "https://www.google.com/",
            },
        }

    return base


def _accept_language_for(language: str | None) -> str:
    """Return locale-appropriate Accept-Language header — not hardcoded."""
    LANG_HEADERS = {
        "vi": "vi-VN,vi;q=0.9,en;q=0.8",
        "en": "en-US,en;q=0.9",
        "th": "th-TH,th;q=0.9,en;q=0.8",
        "id": "id-ID,id;q=0.9,en;q=0.8",
        "ja": "ja-JP,ja;q=0.9,en;q=0.8",
        "ko": "ko-KR,ko;q=0.9,en;q=0.8",
        "zh": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    return LANG_HEADERS.get(language or "en", "en-US,en;q=0.9")


_SCROLL_JS = """
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
```

---

## 3. Diagnosis Examples

### VinFast (`vinfastauto.com/vn_vi`) — the reference case

```
Signals:
  status_code=301, wait_until=load, primary_score=-294
  token_count=6, selected_role=builtin_fallback
  has_recaptcha=True, has_admicro=True, has_facebook_pixel=True (5 pixels)
  duration=35.75s, attempts=1/3

Issues detected (in order):
  1. SPA_NOT_WAITED      → wait_until=load on React/Next.js page
  2. BOT_DETECTION       → reCAPTCHA + Admicro + 5 Facebook pixels
  3. REDIRECT_CONTEXT    → 301 with only 6 tokens
  4. TIMEOUT_EARLY_EXIT  → 35s, thin result

Highest tier: BOT_DETECTION → MANAGED_BROWSER

Config to apply:
  wait_until=networkidle, page_timeout=60000, follow_redirects=True
  js_code=SCROLL_JS, use_managed_browser=True
  user_agent=Chrome/122, Accept-Language=vi-VN,vi;q=0.9,en;q=0.8
  url_override=https://vinfastauto.com/vn_vi (crawl final_url directly)
```

### A static news article — should use Tier 0

```
Signals:
  status_code=200, wait_until=load, primary_score=850
  token_count=1200, selected_role=crawl4ai_primary
  has_recaptcha=False, has_gtm=False

Issues detected:
  1. STATIC_SUFFICIENT  → rich content already at load tier, no bot signals

Recommended tier: STATIC_HTML
Config: use_browser=False  (httpx only — no headless browser needed)
```
