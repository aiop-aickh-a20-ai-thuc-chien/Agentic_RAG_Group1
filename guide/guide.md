# URL Ingestion Improvement Strategy

## Preventing Incorrect Fallback to Built-in Parser for React / Dynamic Websites

## Problem Statement

The current URL ingestion pipeline prioritizes latency over content quality.

Current flow:

```text
Rendered Parser (Playwright / Crawl4AI)
        ↓ timeout
Built-in Parser Fallback
        ↓
Accept Result
```

This approach works reasonably well for:

* Blog articles
* News pages
* Static documentation
* Policy pages

However, it performs poorly for:

* React applications
* Next.js applications
* Product catalogs
* Interactive e-commerce pages
* Dynamic tabs and accordions
* JavaScript-rendered specifications

As a result:

* Product cards are missing
* Prices are missing
* Specifications are missing
* CTA actions are missing
* Chunk quality decreases
* Retrieval quality decreases
* Duplicate detection becomes less accurate
* Conflict detection becomes less accurate

---

# Root Cause

The fallback decision is currently based on:

```text
Latency
```

instead of:

```text
Content Quality
```

Example:

```text
Playwright timeout
    ↓
Built-in parser succeeds
    ↓
Page accepted
```

Even if the built-in parser only extracts:

```html
<div id="root"></div>
```

or

```html
<div id="__next"></div>
```

the page may still be accepted.

This creates low-quality chunks and noisy embeddings.

---

# Recommended Architecture

## Quality-Gated Fallback

Replace:

```text
Rendered Timeout
    ↓
Accept Built-in Result
```

with:

```text
Rendered Timeout
    ↓
Evaluate Quality Score
    ↓
Accept or Reject
```

Pipeline:

```text
1. Static Fetch
2. Detect Page Type
3. Evaluate Content Quality
4. Choose Parser
5. Validate Output
6. Accept / Retry / Mark Partial
```

---

# Step 1: Static HTML Detection

Fetch raw HTML first.

Detect:

```python
react_signals = [
    "__NEXT_DATA__",
    "data-reactroot",
    "window.__INITIAL_STATE__",
    "id='root'",
    "id='__next'",
]
```

Signals indicating JavaScript-heavy pages:

* Empty root containers
* Large JavaScript bundles
* Few visible text nodes
* Client-side rendering markers

If detected:

```text
Needs Rendered Parser
```

---

# Step 2: Page Classification

Classify URLs before crawling.

Example:

```text
Article
Policy
FAQ
Product Detail
Product Listing
Vehicle Configurator
Booking Flow
Interactive Application
```

Examples:

```text
vinfastauto.com/tin-tuc/*
    → Article

vinfastauto.com/privacy-policy
    → Policy

shop.vinfastauto.com/*
    → Product Detail

dat-coc-xe*
    → Booking Flow
```

---

# Step 3: Quality Score

Before accepting built-in output, compute:

```python
quality_score = (
    has_title * 1
    + has_headings * 1
    + has_main_content * 2
    + has_product_names * 2
    + has_prices * 2
    + has_specs * 2
    - has_cookie_banner * 1
    - has_navigation_noise * 1
    - has_react_shell * 3
)
```

Example thresholds:

```text
>= 7     Accept
4-6      Partial
< 4      Reject
```

---

# Step 4: Parser Selection Strategy

## Static Pages

Use:

```text
Trafilatura
Readability
Built-in HTML Parser
```

Suitable for:

* Articles
* News
* Documentation
* Policies

---

## Dynamic Pages

Use:

```text
Playwright
Crawl4AI Rendered HTML
```

Suitable for:

* Product Detail Pages
* Product Listings
* Tabs
* Accordions
* React Applications

````

---

# Step 5: Latency Budget by Page Type

Avoid one global timeout.

Recommended:

```python
TIMEOUTS = {
    "article": 8,
    "policy": 8,
    "faq": 10,
    "product_detail": 20,
    "product_listing": 25,
    "booking_flow": 35,
}
````

Reason:

Product pages contain business-critical information.

Waiting slightly longer is better than indexing incomplete data.

---

# Step 6: Render Cache

Never render the same page repeatedly.

Store:

```text
raw.html
rendered.html
parsed.md
chunks.jsonl
manifest.json
```

Flow:

```text
URL
 ↓
Render Once
 ↓
Cache HTML
 ↓
Reuse For Parsing
```

Benefits:

* Reduced latency
* Reduced browser cost
* Deterministic testing
* Easier debugging

---

# Step 7: Retry Strategy

Instead of:

```text
Playwright timeout
 ↓
Fallback
```

Use:

```text
Playwright timeout
 ↓
Lightweight retry
 ↓
Quality evaluation
 ↓
Fallback if acceptable
```

Retry options:

* Disable image loading
* Disable video loading
* Disable fonts
* Reduce wait conditions
* Use DOMContentLoaded instead of NetworkIdle

---

# Step 8: Reject Low-Quality Fallbacks

For React pages:

```python
if (
    page_type == "product"
    and not has_product_entities
):
    reject_builtin_result()
```

Example:

Reject:

```html
<div id="root"></div>
```

Accept:

```html
VF 8
Price: 819.180.000 VNĐ
Range: 500 km
Seats: 5
```

---

# Impact on Duplicate Detection

Better rendering produces:

```text
Cleaner entities
More complete specifications
More accurate metadata
```

Benefits:

* Better metadata blocking
* Better embedding similarity
* Fewer false duplicates
* Fewer missed duplicates

---

# Impact on Retrieval Relevance

Current situation:

```text
React Shell
 ↓
Poor Chunks
 ↓
Weak Embeddings
 ↓
Bad Retrieval
```

Improved:

```text
Rendered DOM
 ↓
Entity-Aware Chunks
 ↓
Rich Metadata
 ↓
Strong Embeddings
 ↓
Better Retrieval
```

Expected improvements:

| Metric                       | Current                   | Improved                   |
| ---------------------------- | ------------------------- | -------------------------- |
| Recall@5                     | Medium                    | High                       |
| MRR@5                        | Medium                    | High                       |
| Duplicate Detection Accuracy | Medium                    | High                       |
| Conflict Detection Accuracy  | Medium                    | High                       |
| Chunk Quality                | Medium                    | High                       |
| Storage Efficiency           | Medium                    | High                       |
| Latency                      | Slightly Higher per Crawl | Lower Overall due to Cache |

---

# Final Recommendation

Do not fallback based on timeout alone.

Use:

```text
Page Type Detection
    ↓
Parser Selection
    ↓
Quality Score
    ↓
Accept / Reject
```

Rule:

```text
Static Pages
    → Built-in Parser

Dynamic Product Pages
    → Rendered Parser Required

Fallback
    → Only if Quality Score Passes
```

The most important change is:

```text
Latency-based fallback
        ↓
Quality-based fallback
```

This prevents React shells from entering the Knowledge Base and significantly improves chunk quality, retrieval relevance, duplicate detection, and conflict detection.

---

# Implementation Status In URL Ingestion

The URL ingestion package now follows the quality-first direction from this
guide:

* Static HTML is fetched first so page type and React/Next/root-container
  signals can be inspected before accepting parser output.
* `quality/strategy.py` classifies page type, records latency budget metadata,
  scores static/rendered candidates, and emits `url_quality_gate`.
* Product detail, product listing, homepage product listing, booking, vehicle
  configurator, and dynamic application pages require a rendered parser attempt
  when browser extraction is enabled.
* Page-type latency budgets now feed the Playwright `timeout_seconds` setting,
  so product/dynamic pages receive more rendering time than simple static pages.
* Rendered extraction now retries failed `load` waits with a lighter
  `domcontentloaded` strategy.
* Verification runs now use a report-local render cache for rendered Markdown,
  rendered HTML, extractor payload, and manifest files.
* Static fallback is marked rejected or partial when rendering is disabled or
  fails and the extracted content does not pass the quality gate.
* The selected candidate is the higher-quality parser output; latency is a
  secondary concern after content completeness.
* Product and vehicle pages now emit structured product-spec metadata in URL
  chunks, including model name, price, driving range, battery capacity, charging
  time, power, torque, max speed, warranty, dimensions, and ground clearance
  when visible in the parsed page.
* URL ingestion currently supports HTTP(S) HTML pages, static article/policy/FAQ
  pages, rendered product/listing/homepage/configurator/booking/dynamic pages,
  direct HTML fixture input, and plain text chunking. PDF URLs and PDF
  responses are rejected here and should be diverted to PDF ingestion.
* Script/database/vector-store reminders now live in
  `src/agentic_rag/ingestion/url/TODO_scripts.md`.
* Duplicate and conflict handoff reminders now live in
  `src/agentic_rag/ingestion/url/TODO_dedup.md`, while implementation decisions
  stay in `dedup_detect` and `knowledge_quality`.
* Conflict detection remains owned by the `knowledge_quality` prototype; this
  URL-ingestion pass only documents the metadata handoff and fixture TODOs in
  `src/agentic_rag/ingestion/url/TODO.md`.
* The 2026-06-13 verification subset passed: 12 selected URLs, including 10
  prior failures and 2 prior passes, processed with 12 passed, 0 failed, and 0
  errors. See `guide/reports/url_ingestion_verification_subset_complete_final2/`.

Remaining follow-up:

* Extend golden-data evaluation with quality-gate expectations for dynamic
  product pages.
* Run the full 322-link corpus again after this subset pass to measure broad
  impact.
