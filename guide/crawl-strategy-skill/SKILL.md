---
name: crawl-strategy
description: >
  Use this skill when improving URL ingestion crawl strategy, parser selection,
  content-quality scoring, shell detection, fallback ordering, or crawl demo
  diagnostics. Trigger it for tasks involving Crawl4AI attempt tuning,
  Playwright readiness rules, Crawlee queue/concurrency strategy, Scrapling
  fetcher evaluation, or explaining success/recovered/partial/fail crawl review
  results.
---

# Crawl Strategy Skill

Use this skill to update URL ingestion strategy without confusing crawler
success with parser/content-quality success.

## First Reads

Read only what is needed for the task:

- `src/agentic_rag/ingestion/url/Worklog.md`
- `src/agentic_rag/ingestion/url/crawler.py`
- `src/agentic_rag/ingestion/url/loader.py`
- `src/agentic_rag/ingestion/url/tests/`
- `guide/demo/url-crawl-review/output/crawl_review.md` when a live review exists
- `references/crawler-tool-research.md` when comparing Crawlee, Playwright, or
  Scrapling

## Diagnosis Frame

Classify every issue before changing code:

| Signal | Meaning | Preferred action |
|---|---|---|
| `crawl_attempt_errors` is non-empty | Browser attempt problem | tune attempt order, waits, timeout, shell gate |
| `crawl_attempt=main` and `review_status=recovered` | crawl worked, parser switched | tune quality scoring or accept fallback |
| `low_signal_snapshot=True` | rendered DOM is shell/thin | reject snapshot, retry, or static fallback |
| `static_html_recovery=True` | static HTML beat rendered HTML | preserve recovery; improve diagnostics |
| zero usable chunks | ingestion failure for review | fail status and inspect source snapshot |

Do not treat `recovered` as failure by default. It often means the crawler
loaded usable HTML and the selector chose a cleaner parser.

## Strategy Ladder

Prefer the cheapest reliable layer first:

1. Static HTML baseline with link extraction.
2. Crawl4AI `main`: SPA-aware rendered crawl with targeted readiness checks.
3. Crawlee + Playwright quality gate: faster secondary rendered parser using
   request blocking, bounded browser timeouts, and the repo DOM normalizer when
   builtin/Crawl4AI quality scoring is not enough.
4. Crawl4AI `secondary`: emergency bounded retry only; avoid long `networkidle`.
5. Crawl4AI `last`: minimal browser retry for over-cleaned or shell snapshots.
6. Playwright probe: targeted DOM/XHR extraction for known interactive state.
7. Scrapling `DynamicFetcher`/`StealthyFetcher`: evaluate only when Python-side
   dynamic or anti-bot recovery is needed and dependency approval is acceptable.

## Quality Selection Rules

When changing parser scoring:

- Compare candidates by token count, heading count, price/structured signals,
  boilerplate hits, link/image noise, and usable chunk count.
- Keep `crawl4ai_primary` when it has enough content and not much extra noise.
- Prefer Trafilatura for article pages when it removes navigation/listing noise.
- Prefer builtin parser over Crawl4AI Markdown when rendered HTML is rich but
  Markdown is link-heavy or malformed.
- Prefer Crawlee + Playwright over Trafilatura when the page needs an
  independent rendered DOM quality gate, especially for SPA/listing pages where
  static HTML or builtin scoring cannot confirm content completeness.
- Preserve primary candidate chunks for demo comparison when a fallback wins.
- Add or update deterministic unit tests with fake HTML/Markdown. No live URLs
  in CI.

## Crawl Attempt Rules

- Avoid using `networkidle` as a long default for SPA pages with trackers.
- Use targeted readiness checks: visible anchors, meaningful body text, product
  card count, article heading, or known data object presence.
- Keep shell signals visible in metadata instead of hiding them.
- Use per-session shell hints only inside one seed/child crawl session; reset
  hints for independent top-level ingestion calls.

## Output Expectations

When finishing a task:

- Say whether the change is crawl behavior, parser scoring, chunk quality, demo
  diagnostics, or research only.
- Report focused tests and any live crawl that was or was not run.
- If recommending a new dependency, explain why Crawl4AI/static/Trafilatura are
  insufficient first.
