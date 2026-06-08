---
name: crawl-diagnosis
description: >
  Use this skill whenever a crawl result looks empty, thin, or wrong — especially
  when: (1) a crawled page produces very few chunks or tokens (under 100 tokens),
  (2) the markdown_quality fallback_reason is "crawl4ai_primary_quality_check_failed",
  (3) a page's content is known to be rich but the crawl only returned a title or
  one promo line, (4) the status_code is 301/302 and content is missing, (5) you
  need to decide between static HTML fetch vs headless browser rendering vs
  networkidle wait, or (6) you are building or extending a crawl pipeline and need
  to embed automatic quality checks and render-strategy escalation logic. Also
  trigger this skill when the user pastes a manifest.json, chunks.jsonl, or
  crawl_review.md and asks "why is content missing" or "how do I fix the crawl".
---

# Crawl Diagnosis Skill

Diagnose why a crawl returned thin or empty content, and automatically
escalate the render strategy — from static HTML → `wait_until: load` →
`wait_until: networkidle` → scroll + JS injection → managed browser — until
quality thresholds are met.

---

## Core Principle: Quality-Gated Render Escalation

Never assume a crawl succeeded based on HTTP 200 alone. Always score the
result and escalate the render strategy if quality is insufficient.

```
static HTML → load → networkidle → networkidle + scroll → managed browser
     ↑                                                            ↑
  fastest, no JS                                         slowest, most human-like
```

---

## Step 0 — Read the Diagnostic Signals First

Before writing any code, read these fields from the crawl output:

| Field | Where | What it tells you |
|---|---|---|
| `status_code` | chunk metadata | 301/302 = redirect may have lost JS context |
| `wait_until_target` | chunk metadata | Was `"load"` used on a SPA? |
| `selected_role` | `markdown_quality` | `"builtin_fallback"` = primary parsers failed |
| `fallback_reason` | `markdown_quality` | `"crawl4ai_primary_quality_check_failed"` = near-empty render |
| `token_count` (all candidates) | `markdown_quality.candidates` | All near zero = JS-rendered content not captured |
| `score` (crawl4ai_primary) | `markdown_quality.candidates` | Negative score = empty or boilerplate HTML |
| `crawl_attempt_duration_seconds` | chunk metadata | >30s on one page = hung on JS/reCAPTCHA |
| `crawl_attempt_count` vs `configured_crawl_attempt_count` | chunk metadata | Under-retried = retry logic short-circuited |
| assets with `recaptcha` or `admicro` iframes | `manifest.json` assets | Bot-detection active |
| Facebook pixel `tr?id=` images | `manifest.json` assets | Heavy analytics = likely fingerprinted |
| `og_title` present but `og_url` null | `manifest.json.page_metadata` | Partial render — head loaded, body did not |

Read `references/signal-decoder.md` for the full signal-reading implementation.

---

## Step 1 — Score the Crawl Result

Compute a **Quality Score** from the crawl output before deciding what to do.

```python
from .signal_decoder import CrawlDiagnosis, score_crawl_result

diagnosis = score_crawl_result(manifest, chunks)
# Returns CrawlDiagnosis with:
#   .quality_score: int        (0–100)
#   .render_tier:  str         current tier used
#   .issues:       list[Issue] detected problems
#   .recommended_tier: str     what to try next
#   .recommended_config: dict  concrete config changes
```

### Quality Score Thresholds

| Score | Verdict | Action |
|---|---|---|
| ≥ 70 | ✅ Good | Accept result |
| 40–69 | ⚠️ Marginal | Log warning; attempt one tier escalation |
| < 40 | ❌ Poor | Escalate render strategy immediately |

### Score Inputs (each deducts from 100)

| Signal | Deduction | Reason |
|---|---|---|
| `token_count` of selected parser < 50 | −40 | Near-empty content |
| `token_count` < 200 | −20 | Thin content |
| `selected_role == "builtin_fallback"` | −20 | All real parsers failed |
| `score` of crawl4ai_primary < 0 | −15 | Negative quality score from parser |
| `status_code` in (301, 302) | −10 | Redirect may have broken JS context |
| `wait_until_target == "load"` | −10 | SPA not waited for |
| reCAPTCHA iframe detected in assets | −15 | Bot-detection active |
| `crawl_attempt_duration_seconds` > 30 | −5 | Likely timed out mid-render |
| `crawl_attempt_count` < `configured_crawl_attempt_count` | −5 | Retries short-circuited |

Read `references/signal-decoder.md` for the scoring implementation.

---

## Step 2 — Identify Issue Type

Map diagnostic signals to named issue types. Each issue maps to a specific fix.

```python
class IssueType(str, Enum):
    SPA_NOT_WAITED      = "spa_not_waited"        # wait_until was "load" on JS page
    LAZY_LOAD_MISSED    = "lazy_load_missed"       # content in viewport not scrolled to
    BOT_DETECTION       = "bot_detection"          # reCAPTCHA / fingerprinting
    REDIRECT_CONTEXT    = "redirect_context"       # 301/302 lost JS session
    TIMEOUT_EARLY_EXIT  = "timeout_early_exit"     # hung before render complete
    RETRY_SHORT_CIRCUIT = "retry_short_circuit"    # retries didn't fire
    STATIC_SUFFICIENT   = "static_sufficient"      # page is pure HTML, no JS needed
    UNKNOWN_THIN        = "unknown_thin"           # thin but no clear signal
```

### Issue Detection Rules (evaluated in order)

```
IF wait_until_target == "load" AND crawl4ai_primary score < 0
    → SPA_NOT_WAITED  (fix: switch to networkidle)

IF SPA_NOT_WAITED resolved but carousels/lazy sections expected
    → LAZY_LOAD_MISSED  (fix: add scroll JS injection)

IF reCAPTCHA or admicro iframe in assets
    → BOT_DETECTION  (fix: managed browser + real UA + Vietnamese Accept-Language)

IF status_code in (301, 302) AND token_count < 50
    → REDIRECT_CONTEXT  (fix: follow_redirects=True + re-crawl final_url directly)

IF crawl_attempt_duration_seconds > 30 AND token_count < 50
    → TIMEOUT_EARLY_EXIT  (fix: raise page_timeout to 60000ms)

IF crawl_attempt_count < configured_crawl_attempt_count
    → RETRY_SHORT_CIRCUIT  (fix: don't short-circuit on 3xx; retry with escalated config)

IF all parser token_counts < 10 but page has known static structure (e.g. /sitemap, /robots)
    → STATIC_SUFFICIENT  (fix: skip browser entirely, use httpx)
```

Read `references/issue-rules.md` for the full decision tree.

---

## Step 3 — Escalate the Render Strategy

Each issue type maps to a render tier. Try tiers in order; re-score after each.

```
Tier 0: static_html      → httpx.get(), no browser, fastest
Tier 1: load             → Crawl4AI default (current baseline)
Tier 2: networkidle      → waits for JS network activity to stop
Tier 3: networkidle+scroll → networkidle + JS scroll to trigger lazy-load
Tier 4: managed_browser  → persistent browser profile, most human-like
```

### Tier Selection by Issue

| Issue | Minimum tier to try | Config changes |
|---|---|---|
| `SPA_NOT_WAITED` | Tier 2: `networkidle` | `wait_until="networkidle"`, `page_timeout=60000` |
| `LAZY_LOAD_MISSED` | Tier 3: `networkidle+scroll` | + `js_code=SCROLL_JS` |
| `BOT_DETECTION` | Tier 4: `managed_browser` | + `use_managed_browser=True`, real UA, `Accept-Language: vi-VN` |
| `REDIRECT_CONTEXT` | Tier 2 on `final_url` | Crawl `final_url` directly, not original |
| `TIMEOUT_EARLY_EXIT` | Tier 2 with longer timeout | `page_timeout=90000` |
| `RETRY_SHORT_CIRCUIT` | Retry at Tier 2 | Force retry; don't treat 3xx as terminal |
| `STATIC_SUFFICIENT` | Tier 0: `static_html` | Skip browser entirely |
| `UNKNOWN_THIN` | Tier 2 first | Then Tier 3 if still thin |

Read `references/render-tiers.md` for concrete config for every tier.

---

## Step 4 — Re-Score and Accept or Continue Escalating

```python
async def crawl_with_diagnosis(
    url: str,
    *,
    max_tier: int = 4,
    quality_threshold: int = 70,
) -> tuple[CrawlResult, CrawlDiagnosis]:
    """
    Crawl a URL with automatic quality-gated tier escalation.

    1. Start at Tier 1 (load) — the repo default.
    2. Score the result.
    3. If score < quality_threshold and current_tier < max_tier:
       - Identify issues
       - Build escalated config
       - Re-crawl at next tier
       - Re-score
    4. Return the best result achieved and its final diagnosis.
    """
```

Never exceed `max_tier` — caller controls the ceiling. Log each tier attempt
and its score so the diagnosis is transparent.

Read `references/render-tiers.md` for the full implementation.

---

## Step 5 — When to Use Static HTML Instead of a Browser

Use static HTML (Tier 0 / `httpx`) when the page is known to be server-rendered.
**Do NOT default to a browser for every URL** — it is slow, resource-heavy, and
triggers bot-detection more aggressively.

### Signals that static HTML is sufficient

```python
STATIC_SUFFICIENT_SIGNALS = [
    # URL structure signals
    lambda url: urlparse(url).path in ("/robots.txt", "/sitemap.xml"),
    lambda url: url.endswith(".xml") or url.endswith(".json"),
    lambda url: "/api/" in url,

    # Content signals (from a cheap HEAD request first)
    lambda headers: "text/html" not in headers.get("content-type", ""),
    lambda headers: int(headers.get("content-length", 0)) > 500_000,  # huge = not SPA

    # Prior crawl signals (from manifest / chunks)
    lambda manifest: manifest.get("page_metadata", {}).get("og_title") is not None
                     and manifest.get("chunk_count", 0) > 5,  # was already rich
]
```

### Signals that a browser IS required

```python
BROWSER_REQUIRED_SIGNALS = [
    # Asset signals from manifest
    lambda assets: any("recaptcha" in a.get("url","") for a in assets),
    lambda assets: any("googletagmanager" in a.get("url","") for a in assets),

    # Quality signals from prior crawl
    lambda diag: diag.quality_score < 40,
    lambda diag: diag.render_tier == "load" and diag.quality_score < 70,

    # URL heuristics
    lambda url: any(kw in url for kw in ["/vn_vi", "/en_us", "/#", "?lang="]),
]
```

Read `references/static-vs-browser.md` for the full decision matrix.

---

## Output: DiagnosisReport

Every crawl should produce a `DiagnosisReport` alongside its chunks:

```python
class DiagnosisReport(BaseModel):
    url: str
    quality_score: int                 # 0–100
    verdict: str                       # "good" | "marginal" | "poor"
    render_tier_used: str              # tier that produced accepted result
    tiers_attempted: list[str]         # all tiers tried in order
    issues_detected: list[str]         # IssueType values
    token_counts: dict[str, int]       # parser → token count
    fallback_reason: str | None        # from markdown_quality
    bot_signals: list[str]             # detected anti-bot assets
    recommended_action: str            # human-readable next step if still poor
    accepted: bool                     # True if quality_threshold was met
```

---

## Reference Files

| File | When to read |
|---|---|
| `references/signal-decoder.md`   | Reading manifest + chunks to extract diagnostic signals |
| `references/issue-rules.md`      | Full issue detection decision tree |
| `references/render-tiers.md`     | Concrete Crawl4AI config for each tier + escalation loop |
| `references/static-vs-browser.md`| Full static HTML vs browser decision matrix |

---

## Anti-Patterns to Avoid

| ❌ Wrong | ✅ Correct |
|---|---|
| Accept crawl because HTTP 200 returned | Always score token count and parser quality |
| Always use `wait_until="load"` | Detect SPA signals; use `networkidle` for JS pages |
| Always use headless browser | Use static HTML for known static pages |
| Retry with the same config | Escalate render tier on each retry |
| Ignore `markdown_quality.candidates` | Read all candidate scores — they reveal what failed |
| Treat 301 as a terminal success | Re-crawl `final_url` directly with full SPA config |
| Log quality issues and continue | Gate on quality score; block acceptance if `< 40` |
