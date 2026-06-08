# Crawler Tool Research

Use this reference when choosing between Crawl4AI, Crawlee, Playwright, and
Scrapling for URL ingestion strategy.

Sources checked on 2026-06-07:

- Crawlee JavaScript Playwright crawler:
  https://crawlee.dev/js/api/playwright-crawler
- Crawlee Python Playwright crawler guide:
  https://crawlee.dev/python/docs/guides/playwright-crawler
- Crawlee Python PlaywrightCrawler API:
  https://crawlee.dev/python/api/class/PlaywrightCrawler
- Playwright Python navigation docs:
  https://playwright.dev/python/docs/navigations
- Playwright Python Page API:
  https://playwright.dev/python/docs/api/class-page
- Scrapling fetcher basics:
  https://scrapling.readthedocs.io/en/latest/fetching/choosing.html
- Scrapling DynamicFetcher:
  https://scrapling.readthedocs.io/en/latest/fetching/dynamic.html
- Scrapling StealthyFetcher:
  https://scrapling.readthedocs.io/en/latest/fetching/stealthy.html

## Crawlee

Best use: managed multi-URL crawling with request queues, crawl depth, retries,
concurrency, browser pool lifecycle hooks, and robots/proxy/session controls.

Repo fit:

- Good future candidate for replacing repo-native child-page loops with a real
  crawl frontier.
- Good when `max_child_pages` grows beyond a small review run.
- Not needed just to improve parser selection because parser selection happens
  after HTML/Markdown is already fetched.

Notes:

- JavaScript `PlaywrightCrawler` supports static lists and dynamic queues.
- Crawlee Python now has `PlaywrightCrawler`, `max_crawl_depth`,
  `max_requests_per_crawl`, `respect_robots_txt_file`, `retry_on_blocked`,
  navigation timeout, request-handler timeout, and concurrency settings.
- Crawlee docs say browser-based crawlers are slower than HTTP-based crawlers,
  but useful for JS-heavy sites.

## Playwright

Best use: targeted readiness and interactive probes.

Repo fit:

- Use inside Crawl4AI `js_code` or separate probe helpers when the page needs a
  precise condition before snapshotting.
- Prefer selectors and page-state conditions over generic waits.
- Use diagnostics to capture hydration/shell symptoms.

Important guidance:

- Playwright navigation defaults to waiting for `load`.
- Modern pages continue work after `load`; there is no universal loaded state.
- The Page API marks `networkidle` as discouraged; rely on web assertions or
  explicit page-state checks instead.

Recommended readiness probes:

- minimum visible word count,
- minimum internal anchor count,
- required heading/product card/listing count,
- article body selector,
- known global data object,
- XHR response capture when DOM text is thin but API data is available.

## Scrapling

Best use: Python-side fetcher ladder when static HTTP is insufficient and
Crawl4AI/Playwright probes are unreliable.

Repo fit:

- Candidate optional dependency, not a first move.
- `Fetcher` is fastest for basic HTTP pages.
- `DynamicFetcher` is for JavaScript pages and small/mid protections.
- `StealthyFetcher` is for harder protections and browser reuse through
  sessions.

Important constraints:

- Do not add Scrapling just because a page is `recovered`; recovered parser
  selection may already be healthy.
- Do not use stealth mode to bypass robots or policy boundaries.
- If evaluated, wrap behind optional imports and deterministic fake tests.

## Decision Matrix

| Problem | Preferred next move |
|---|---|
| Child pages are slow due repeated shells | per-session shell cache and shorter retry timeout |
| Seed discovers too few URLs | improve link extraction, sitemap probe, or Crawlee frontier |
| Crawl succeeds but parser switches | tune content-quality scoring |
| Rendered DOM is shell but static HTML is good | static HTML fallback |
| Rendered HTML exists but Markdown is noisy | builtin parser from rendered HTML |
| Article page has navigation noise | Trafilatura quality fallback |
| JS state hidden behind interaction | Playwright probe or XHR capture |
| Large multi-page crawl needed | Crawlee or Crawl4AI `arun_many()` dispatcher |
| Hard anti-bot blocks after normal retries | evaluate Scrapling StealthyFetcher with approval |

## Repo Strategy

Keep the current stack as the default:

```text
Crawl4AI attempts -> source snapshot gate -> parser candidate scoring -> chunks
static/trafilatura fallback only when quality gates say it is needed
```

Add new tools only behind optional adapters and only after a report shows the
existing stack cannot produce usable chunks.
