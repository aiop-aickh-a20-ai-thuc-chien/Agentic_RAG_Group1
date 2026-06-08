# Fix: Low-Content Shell HTML + 10-Minute Crawl Timeout

**Applies to:** `crawler.py` — Crawl4AI main / secondary / last retry flow  
**Symptom:** `max_child_pages=5` on `https://vinfastauto.com/vn_vi` takes 10+ minutes.
Every URL logs `"main: Crawl4AI returned low-content shell HTML"` and
`"secondary: Crawl4AI returned low-content shell HTML"` before recovering on `last`.  
**Status of content:** ✅ Content is fine — all URLs recovered with good chunks.
The errors are expected retry-gate signals, not failures.  
**Problem:** The `secondary` attempt uses `networkidle` and waits its full timeout
(~90 s) before the shell gate discards it — on every URL, every run.

---

## Why It Is Slow

VinFast pages (`vinfastauto.com`, `shop.vinfastauto.com`) run background
Admicro trackers, five Facebook pixels, and a chat widget that keep the network
permanently busy. `networkidle` never fires — it sits until `page_timeout` expires.

The retry math for 6 URLs (1 seed + 5 children):

```
main      shell gate fires after ~30 s   × 6 URLs =  ~3 min
secondary networkidle times out at ~90 s  × 6 URLs =  ~9 min   ← the problem
last      succeeds in ~20 s               × 6 URLs =  ~2 min
─────────────────────────────────────────────────────────────
Total                                               ~14 min
```

The `secondary` attempt wastes ~9 minutes waiting for a result it always discards.

---

## Fix 1 — Cut the `secondary` Attempt Timeout (apply first, biggest gain)

**File:** `src/agentic_rag/ingestion/url/crawler.py`

Find the `secondary` attempt config block and reduce both timeouts:

```python
# BEFORE
secondary_config = CrawlerRunConfig(
    wait_until="networkidle",
    page_timeout=90_000,
    delay_before_return_html=10.0,
    ...
)

# AFTER — fast-fail the shell; last will do the real work
secondary_config = CrawlerRunConfig(
    wait_until="networkidle",
    page_timeout=20_000,          # was ~90 000 — cut to 20 s
    delay_before_return_html=2.0,  # was 10.0 — reduce; shell appears immediately
    ...
)
```

**Why this is safe:** The shell-detection gate already discards the `secondary`
result for VinFast pages. Waiting 90 s for a result you throw away is wasted time.
20 s is enough for the shell to load and be detected.

**Expected saving:** ~70 s × 6 URLs ≈ **7 minutes off every VinFast run.**

---

## Fix 2 — Session-Level Domain Shell Cache (apply second, skips wasted attempts)

After the seed URL's `main` attempt returns a shell, every child URL from the
same domain will do the same. Skip straight to `last` for them.

**File:** `src/agentic_rag/ingestion/url/crawler.py`

Add a session-scoped set at the top of the crawl function (or pass it in):

```python
# At module or session scope — reset per load_url_chunks() call
_shell_domains: set[str] = set()


def _attempts_for_url(url: str) -> list[str]:
    """
    Return the ordered attempt names to run for this URL.
    If the domain already returned a shell this session, skip main + secondary.
    """
    domain = urlparse(url).netloc
    if domain in _shell_domains:
        return ["last"]
    return ["main", "secondary", "last"]


def _record_shell_domain(url: str, attempt: str) -> None:
    """
    Call this when the shell gate fires on 'main'.
    Records the domain so child URLs skip straight to 'last'.
    """
    if attempt == "main":
        _shell_domains.add(urlparse(url).netloc)
```

In the retry loop, call `_record_shell_domain` right after the shell is detected:

```python
for attempt_name in _attempts_for_url(url):
    result = await _run_attempt(url, attempt_name, config)

    if _is_shell(result):
        attempt_errors.append(f"{attempt_name}: Crawl4AI returned low-content shell HTML")
        _record_shell_domain(url, attempt_name)   # ← add this line
        continue

    if result.success and result.html:
        break   # use this result
```

**Expected saving:** For a 6-URL VinFast run where the seed fires first:
5 child URLs × (skip main ~30 s + skip secondary ~20 s) ≈ **4 minutes saved**
on top of Fix 1.

---

## Fix 3 — Shell Detection Threshold (guard against accepting marginal shells)

The current shell gate checks: `< 3 links AND near-zero visible text`.
Tighten it slightly so a page with 2 links and one promo line is still rejected:

```python
def _is_shell(result: CrawlResult) -> bool:
    """
    Returns True when the crawl result is a low-content loading/promo shell
    that should be discarded and retried.

    Criteria (all repo-validated against VinFast homepage):
    - HTML was returned (result.html is not empty)
    - Visible text is very short  (< 200 characters after stripping tags)
    - Internal links are very few (< 5 anchors in the rendered DOM)
    """
    if not result.html:
        return False   # empty HTML is a different error — not a shell

    visible_text = _strip_tags(result.html)
    link_count   = len(result.links.get("internal", []))

    return len(visible_text.strip()) < 200 or link_count < 5
```

> **Note:** The threshold values `200 chars` and `5 links` come from the Worklog
> observation that VinFast `main`/`secondary` shells had "almost no visible text
> and fewer than three links". The values here are slightly more conservative to
> catch marginal shells. Tune if legitimate thin pages are incorrectly rejected.

---

## Fix 4 — Reset `_shell_domains` Between Top-Level Calls

Make sure the session cache does not leak between independent `load_url_chunks()`
calls (e.g. if the same server process handles multiple user requests):

```python
def load_url_chunks(
    url: str,
    *,
    max_child_pages: int = 0,
    ...
) -> list[Chunk]:
    # Reset the session shell cache for this top-level call
    _shell_domains.clear()
    ...
```

---

## Test Cases to Add

Add these to `src/agentic_rag/ingestion/url/tests/` — all faked, no live URLs.

```python
# test_crawler_shell_timeout.py

def make_shell_result(url: str) -> CrawlResult:
    """Fake CrawlResult that looks like a VinFast loading shell."""
    r = CrawlResult()
    r.url = url
    r.success = True
    r.html = "<html><body><title>VinFast</title><p>Ưu đãi chỉ tới 31/12!</p></body></html>"
    r.links = {"internal": [], "external": []}
    return r

def make_good_result(url: str) -> CrawlResult:
    """Fake CrawlResult with real content."""
    r = CrawlResult()
    r.url = url
    r.success = True
    r.html = "<html><body>" + "<a href='/page'>link</a>" * 10 + "<p>" + "content " * 100 + "</p></body></html>"
    r.links = {"internal": [f"{url}/page{i}" for i in range(8)], "external": []}
    return r


@pytest.mark.asyncio
async def test_secondary_does_not_wait_full_timeout_on_shell(mock_crawl4ai):
    """
    secondary attempt must be bounded by its reduced page_timeout (20 s),
    not the old 90 s timeout.
    Verified by checking the config passed to arun() for the secondary attempt.
    """
    mock_crawl4ai.side_effect = [make_shell_result(URL), make_shell_result(URL), make_good_result(URL)]
    _, meta = await _crawl_url_with_crawl4ai(URL)

    secondary_call_config = mock_crawl4ai.call_args_list[1][1]["config"]
    assert secondary_call_config.page_timeout <= 25_000, (
        f"secondary page_timeout should be ≤ 25 000 ms, got {secondary_call_config.page_timeout}"
    )


@pytest.mark.asyncio
async def test_child_url_skips_main_secondary_after_seed_shell(mock_crawl4ai):
    """
    After seed URL returns a shell on main, child URLs from the same domain
    must skip directly to the last attempt (only one arun() call per child).
    """
    seed_url  = "https://vinfastauto.com/vn_vi"
    child_url = "https://vinfastauto.com/vn_vi/ve-chung-toi"

    _shell_domains.clear()

    # Seed: main=shell, secondary=shell, last=good
    mock_crawl4ai.side_effect = [
        make_shell_result(seed_url),
        make_shell_result(seed_url),
        make_good_result(seed_url),
        make_good_result(child_url),   # child: only last attempt should run
    ]

    await _crawl_url_with_crawl4ai(seed_url)
    await _crawl_url_with_crawl4ai(child_url)

    # Seed used 3 calls; child should use only 1 (last)
    assert mock_crawl4ai.call_count == 4, (
        f"Expected 4 total arun() calls (3 seed + 1 child), got {mock_crawl4ai.call_count}"
    )


@pytest.mark.asyncio
async def test_shell_domains_cleared_between_top_level_calls(mock_crawl4ai):
    """
    _shell_domains must not leak between independent load_url_chunks() calls.
    """
    _shell_domains.add("vinfastauto.com")

    # Simulate a new top-level call — domain cache must be cleared
    load_url_chunks("https://vinfastauto.com/vn_vi", max_child_pages=0)

    assert "vinfastauto.com" not in _shell_domains, (
        "_shell_domains was not cleared at the start of load_url_chunks()"
    )


def test_is_shell_rejects_promo_page():
    """Shell detector must reject the VinFast promo shell."""
    result = make_shell_result("https://vinfastauto.com/vn_vi")
    assert _is_shell(result) is True


def test_is_shell_accepts_good_page():
    """Shell detector must not reject a page with real content."""
    result = make_good_result("https://vinfastauto.com/vn_vi")
    assert _is_shell(result) is False
```

---

## Expected Outcome After All Fixes

| Metric | Before | After |
|---|---|---|
| Time for seed + 5 children | ~14 min | ~2–3 min |
| `secondary` timeout per URL | ~90 s | ~20 s |
| Shell detection on child URLs | 3 attempts each | 1 attempt (`last` only) |
| Content quality | ✅ Good (unchanged) | ✅ Good (unchanged) |
| `review_status` | `recovered` | `recovered` (unchanged) |
| Attempt errors logged | `main: shell, secondary: shell` | `main: shell` (seed only) |

The "low-content shell HTML" messages will still appear in logs for the seed URL's
`main` attempt — this is correct behaviour and should not be suppressed. The
`recovered` review status is the right label for this crawl pattern.

---

## Do Not Change

- **Shell detection gate itself** — it is correct and intentional.
- **`last` attempt config** — it works and produces good content.
- **Outer fallback order** (Crawl4AI → Trafilatura → urllib) — not involved.
- **`review_status: recovered`** — accurate label; do not change to `success`.
- **Parser selection** (`trafilatura_quality_check_selected_for_lower_noise`) — the
  Trafilatura parser winning over crawl4ai_primary for lower noise is correct
  behaviour for VinFast's link-heavy rendered output.
