# URL Ingestion

This module turns a URL or HTML document into clean Markdown, RAG-ready chunks,
and optional local artifacts for inspection.

The implementation is intentionally bounded to URL/HTML ingestion. PDF URLs or
PDF responses are rejected here and should be routed to the PDF ingestion module.

## Module Map

- `loader.py`: public ingestion boundary for URL, HTML, and text inputs.
- `crawler.py`: Crawl4AI adapter used as the preferred live URL crawler.
- `probe.py`: optional interactive-state probes for dynamic pages whose
  important data is stored in JavaScript state rather than visible Markdown.
- `parser.py`: stdlib HTML parser that extracts headings, body text, metadata,
  links, images, and other page assets.
- `extractor.py`: Crawlee/Playwright and Trafilatura adapters used for
  priority quality gates, lightweight fallback fetching, and main-content
  Markdown extraction.
- `chunking/`: deterministic Markdown chunking strategies.
- `artifact.py`: persistence for `parsed.md`, `chunks.jsonl`, and
  `manifest.json`.
- `benchmarking/`: small local parser benchmark helpers.
- `tests/`: URL ingestion unit tests.
- `data/`: local generated artifacts. This is for inspection and should not be
  treated as the committed source of truth.

## Parse Strategy

The default URL path is:

1. `load_url_with_artifacts(url)` validates that the input is an absolute HTTP
   or HTTPS URL and rejects PDF inputs.
2. The page is fetched with Crawl4AI first so rendered/dynamic pages, card-heavy
   layouts, browser-discovered links, and structured table output can be
   captured.
3. Crawl4AI itself now has three runtime attempts before the loader switches
   strategy:
   - `main`: the full SPA-aware crawl with robots checks, rendered Markdown,
     React/accordion/tabs JS probing, user simulation, and the URL-aware wait
     selector.
   - `secondary`: a short bounded browser retry using `networkidle` and the same
     Markdown generator/exclusion policy for pages whose first wait strategy
     times out or returns empty HTML. This attempt intentionally uses a much
     shorter timeout than `main`; tracker-heavy SPAs can keep the network active
     forever, so `networkidle` must not be allowed to dominate child-page runs.
   - `last`: the minimal Crawl4AI retry with cache bypass and Markdown
     generation only, used as the final browser-backed attempt before leaving
     Crawl4AI.
4. Crawl diagnostics record the selected attempt, configured attempt count,
   skipped attempts, attempt errors, attempt duration, and wait target in
   `raw_crawler_result`. This gives the review app enough information to explain
   why a page used the secondary or last browser retry.
   Crawl4AI link groups are combined with raw HTML `<a href>` extraction so
   navigation/footer links remain discoverable even when the crawler's structured
   link groups are sparse.
5. If all Crawl4AI attempts are unavailable or fail, the loader tries Trafilatura's lightweight
   URL fetcher next.
6. If Trafilatura fetch returns empty HTML or fails, the loader falls back to the
   deterministic `urllib` fetch path with the project user agent.
7. `parse_html()` extracts structured page metadata and section boundaries from
   the HTML.
8. Crawl4AI generates primary cleaned Markdown with common VinFast/SFCC noise
   selectors removed. It also builds an optional BM25-filtered Markdown view with
   an English/Vietnamese vehicle query and stemming disabled so Vietnamese words
   are not mangled.
9. Crawlee + Playwright runs as the priority rendered quality gate when a source
   URL is available. It reuses the project DOM walker and normalizer while
   letting Crawlee own browser setup, request blocking, timeouts, and retry
   boundaries. Trafilatura remains the lightweight precision check after
   Crawlee. Crawl4AI remains the selected parser when its primary Markdown is
   usable; Crawlee, Trafilatura, or the Crawl4AI BM25 view is selected when the
   primary Crawl4AI output fails the quality check or when another candidate has
   enough content with materially lower image/link/boilerplate noise.
10. Candidate Markdown is scored for useful content, headings, title match, price
   values, image/link density, and boilerplate risk. Price score is capped so a
   long gallery/listing page with many prices does not automatically beat a
   cleaner main-content extraction. The selected parser and candidate scores are
   stored in `Chunk.metadata["markdown_quality"]`.
11. Each chunk also records `Chunk.metadata["review_status"]` so reviewers can
   distinguish crawl/runtime health from content-quality recovery:
   - `success`: Crawl4AI primary content was selected without retry/fallback.
   - `recovered`: ingestion produced chunks after a browser retry, fallback
     fetch, BM25 view, Trafilatura extraction, or lower-noise parser selection.
   - `partial`: the browser result loaded, but the primary Crawl4AI content
     failed quality checks and should be reviewed as incomplete or low signal.
   - `fail`: used by review tooling when no document/chunks are produced.
12. Crawl4AI table output is appended as `# Structured Page Data` Markdown when
   available. Chunks from this supplement use
   `Chunk.metadata["content_origin"] == "structured_parse"`.
13. The loader removes common script/config/cookie/login/cart/menu boilerplate
   from Markdown.
14. Supported interactive pages are probed for important JS state that is not
   reliably visible in the default rendered page.
15. VinFast vehicle price-card text is normalized so current prices and old
   crossed prices remain explicit in Markdown.
16. The loader chunks global Markdown with heading-aware metadata and enriches
   each `Chunk.metadata` with URL metadata such as original URL, final URL,
   canonical URL, language, author, description, crawler name, parser name,
   source URL, section path, asset count, and dedupe hash.
17. Each chunk records `chunk_quality` and `is_usable_for_retrieval` so review
   tools can flag pages that technically produced chunks but only low-signal
   promo/title text.
18. Parser sections and URL chunks also record `evidence_diagnostics`,
   `has_duplicate_evidence`, and `has_possible_conflict`. These deterministic
   hints help review tools separate repeated carousel/listing text from chunks
   that may contain conflicting prices, specs, dates, or other numeric facts.
19. `chunk_quality["structural_clarity"]` and top-level metadata
   `has_structural_confusion` / `needs_table_reconstruction` flag chunks that
   contain many useful-looking numbers but were flattened from cards or tables.
   Severe flattened numeric tables and repeated phrase blocks are marked not
   usable for retrieval until the parser reconstructs clearer rows/cards.

Crawl4AI is preferred for the first live URL crawl because it can capture
rendered content that static HTML fetches often miss. Crawlee + Playwright is
the priority secondary parser/quality gate because it can produce an independent
rendered DOM extraction with faster request blocking and explicit browser
timeouts. Trafilatura remains useful as the lightweight fetch fallback,
precision quality check, and fallback extractor. `urllib` is the final
deterministic fetch fallback, and the builtin parser remains the deterministic
parser fallback for local HTML and tests.

Install/update the Crawlee browser runtime after syncing dependencies:

```text
uv sync
uv run playwright install chromium
```

If Crawl4AI succeeds but returns title-only content, URL ingestion treats that
as a quality failure and falls back to Trafilatura fetch before returning
chunks. The internal Crawl4AI attempts handle browser/runtime instability first;
the Trafilatura and `urllib` fallbacks handle cases where browser crawling still
cannot produce useful source content.

If Crawl4AI returns a rendered loading/promo shell with too few links and too
little useful text, ingestion now treats that as a rendered-source failure and
uses static HTML via `urllib`. This keeps pages such as the VinFast homepage
usable when the raw server HTML contains product cards and links but the browser
snapshot was captured before the React/Drupal page opened fully. The static HTML
result becomes the recovery baseline for tuning Crawl4AI and builtin parsing:
rendered HTML should be selected only when it adds useful hydrated content rather
than replacing the static page with a low-signal shell.

For one seed-plus-child crawl session, the crawler also remembers domains that
returned a low-content shell on the `main` attempt. Later URLs from that same
domain can skip directly to `last`, and the raw metadata records this in
`crawl_attempts_skipped`. Normal top-level ingestion calls reset this shell
domain cache so one user's failed rendered snapshot does not affect an
independent request in a long-running server.

## Crawl Attempts Versus Parser Quality

`crawl_attempt` and `review_status` answer different questions:

- `crawl_attempt` says which browser strategy produced the HTML/Markdown source:
  `main`, `secondary`, or `last`.
- `review_status` says whether the selected content was direct primary content,
  recovered content, partial content, or a failure for review.

For example, a page can show:

```text
crawl_attempt = main
review_status = recovered
fallback_reason = content_quality_selected_for_lower_noise
```

This means Crawl4AI `main` successfully loaded useful rendered HTML, but the
quality selector chose a cleaner parser candidate such as the builtin HTML
parser or Trafilatura. This is not a browser retry failure.

Use this quick interpretation table:

| Report signal | Interpretation |
| --- | --- |
| `crawl_attempt_errors` has values | Browser attempt problem or shell gate fired. |
| `crawl_attempt=main`, `review_status=success` | Crawl4AI primary Markdown was selected directly. |
| `crawl_attempt=main`, `review_status=recovered` | Crawl worked; parser/content-quality fallback won. |
| `crawl_attempt=last`, `review_status=recovered` | Earlier browser attempts were rejected; final browser recovery worked. |
| `static_html_recovery=True` | Static HTML was better than rendered browser HTML. |
| `usable_chunk_count=0` | Treat as review failure even if HTML was fetched. |

## Interactive Probes

Some pages expose important content only after user interaction, for example a
vehicle configurator where each button changes the selected variant, color, and
price. A frontend may only send one pasted URL, so URL ingestion must extract
that state itself when possible.

`probe.py` currently includes a narrow VinFast configurator probe for URLs like:

```text
https://shop.vinfastauto.com/vn_vi/dat-coc-o-to-dien-vinfast.html?modelId=Products-Car-VF9
```

The probe reads `window.carDeposit.products` through the rendered browser page
and appends chunkable Markdown such as:

```md
## VinFast configurator price options

### VF 9 Plus tuy chon 7 cho

- Probe source: window.carDeposit.products.Products-Car-VF9.NE3MV.
- Probe relation: this record represents one selectable configurator state.
- Price rule: final price / gia cuoi cung = base price of this exact variant + selected option delta; do not reuse a price from another variant.
- VF 9 Plus tuy chon 7 cho: base price / gia co ban / Gia xe kem pin 1.699.000.000 VND.
- VF 9 Plus tuy chon 7 cho + Mau nang cao: final price / gia cuoi cung / Gia xe kem pin 1.699.000.000 VND + 12.000.000 VND = 1.711.000.000 VND (option delta / phu phi mau nang cao + 12.000.000 VND).

### VF 9 Eco

- Probe source: window.carDeposit.products.Products-Car-VF9.NE3LV.
- Probe relation: this record represents one selectable configurator state.
- VF 9 Eco: Gia xe kem pin 1.499.000.000 VND.

## VinFast configurator notes

- Quang duong ... NEDC ...
```

If the JavaScript state only gives a short edition label such as `Plus tuy chon
7 cho`, ingestion prefixes the model inferred from `modelId`, for example
`VF 9 Plus tuy chon 7 cho`. This keeps retrieval/generation unchanged while
giving RAG clearer chunks for interactive product state.
The H3 headings make each variant become a separate section/chunk where possible,
and the note section keeps repeated NEDC disclaimers deduped for review.

## Child Pages

`load_url_with_artifacts()` and `load_url_chunks()` support `max_child_pages`.
When this is greater than zero, the loader follows same-origin links discovered
by Crawl4AI and combines parent/child chunks.

Child crawling intentionally skips:

- external domains,
- PDF links,
- the original URL,
- duplicate normalized chunk text.

During one seed/child session, repeated low-content shell behavior is also
cached by domain. If the seed page proves that `main` returns a rendered shell,
same-domain child pages can skip `main` and `secondary` and go straight to
`last`. This keeps `max_child_pages=5` review runs from spending most of their
time on predictable shell attempts. The skipped attempt names are recorded in
`raw_crawler_result["crawl_attempts_skipped"]`.

This is useful for listing/card pages where the parent page links to product or
article detail pages. Keep `max_child_pages=0` for deterministic single-page
ingestion. For human review or frontend demos where a pasted landing/listing URL
is expected to gather enough product/article detail, pass an explicit value such
as `max_child_pages=10` from the caller rather than changing the ingestion
default.

## Crawl Strategy Research

The current default stack remains:

```text
Crawl4AI attempts -> source snapshot gate -> parser candidate scoring -> chunks
```

Additional crawler frameworks should be evaluated only when this stack cannot
produce usable chunks:

- Crawlee + Playwright is now the priority secondary quality gate. Its queue,
  concurrency, depth-limit, and retry features are still candidates for a larger
  crawl-frontier rewrite.
- Playwright-style readiness checks are preferred for exact page-state probes;
  avoid long generic `networkidle` waits on SPAs with trackers.
- Scrapling may be evaluated as an optional Python fetcher ladder for dynamic or
  protected pages, but should not be added just because a page is `recovered` by
  a healthy parser fallback.

The repo-local strategy note lives at:

```text
guide/crawl-strategy-skill/
guide/research/crawlee-playwright-scrapling-strategy.md
```

## Crawl Review Evaluation

After running `guide/demo/url-crawl-review/run_review.py` or the browser demo,
score the payload with deterministic checks and an OpenAI review:

```bash
uv run python guide/demo/url-crawl-review/evaluate_review.py --input guide/demo/url-crawl-review/output/crawl_review_payload.json --output guide/demo/url-crawl-review/output/crawl_review_evaluation.json
```

The evaluator reads `OPENAI_API_KEY` from the process environment or from `.env`.
It writes JSON with:

- local document scores,
- usable chunk ratios,
- parser/fallback flags,
- OpenAI evaluator scores and recommended tuning actions.

For a no-network/local-only pass:

```bash
uv run python guide/demo/url-crawl-review/evaluate_review.py --offline
```

## Chunking Strategy

The default chunking method is `hierarchical-markdown-probe-aware-overlap`.

The strategy is designed for Markdown:

1. Split global Markdown into heading-scoped sections.
2. Preserve heading context in chunk text and store `section_level` plus
   `section_path` in chunk metadata.
3. Pack paragraphs under each section with a token budget.
4. Count tokens with `tiktoken` when available, falling back to word counts.
5. For URL ingestion, avoid paragraph overlap by default to reduce duplicated
   evidence in retrieval results.
6. If one paragraph is too large, split it into sentences with `pysbd`.
7. Detect Vietnamese text with a lightweight diacritic heuristic and use the
   Vietnamese `pysbd` segmenter; otherwise use English.
8. If sentence segmentation is unavailable, fall back to regex and word splitting.
9. Add lightweight search aliases for VinFast model names such as `VF9`, `VF 9`,
   `VinFast VF9`, and `xe VF 9` so retrieval can match common multilingual query
   forms without changing retrieval code. These aliases are stored in
   `Chunk.metadata["search_aliases"]`, not prepended to `Chunk.text`, to avoid
   making many chunks look artificially similar. Aliases are deduplicated before
   they are written to metadata.

This keeps chunks more useful for RAG than character slicing because headings,
section paths, paragraphs, and sentence boundaries are less likely to be broken.

Each chunk also records continuation metadata:

- `chunk_group_id`: stable group for chunks from the same source and section path.
- `chunk_group_index`: 1-based position inside that group.
- `chunk_group_size`: total chunks in the group.
- `previous_chunk_id`: previous chunk in the same group, when present.
- `next_chunk_id`: next chunk in the same group, when present.
- `is_continuation`: whether this chunk starts after an earlier chunk.
- `continues_to_next`: whether this chunk has a following chunk.

This lets reviewers and downstream RAG code understand whether a chunk is a
standalone section or a continuation of a longer section.

## Image References

Image/PDF/iframe/object assets are kept in the manifest. For image review, URL
chunks also receive `image_references` metadata when an image appears relevant to
the chunk text through alt/title overlap.

Example metadata:

```json
{
  "image_reference_count": 1,
  "image_references": [
    {
      "kind": "image",
      "url": "https://example.edu/vf9-exterior.jpg",
      "alt": "VF 9 exterior",
      "title": "VF 9 body image",
      "target_url": "https://example.edu/vf9-detail",
      "reference_reason": "alt_or_title_overlap"
    }
  ]
}
```

This avoids repeating image alt text inside chunk text while still giving human
reviewers and evaluation scripts a clear reference signal.

## Human Review And Citation Checks

The temporary review app under `guide/demo/url-ingestion-review-app` can be used
to paste a URL and inspect `parsed.md`, `chunks.jsonl`, `manifest.json`, probe
chunks, and generated Q&A checks.

The **Q&A Checks** tab is deterministic. It does not call the generation module.
It verifies whether expected review questions can be derived directly from the
produced chunks and reports the matching `citation_chunk_id`. A found check means
one chunk contains the required evidence terms. A missing check means parsing,
probing, or chunking needs more work before that question is reliable for RAG.

The review app does not require PostgreSQL. It persists local per-run artifacts
for human review. Add a database only when the product needs shared multi-user
history, queryable review records, or analytics across many runs.

## Price And Product Cleanup

The loader includes URL-side cleanup for vehicle price cards. For example, a raw
rendered card like:

```md
VF 9 Eco
Gia ban tu
1.229.180.000
VND
1.499.000.000
VND
```

is normalized into:

```md
- VF 9 Eco: Gia ban tu 1.229.180.000 VND; gia niem yet cu ~~1.499.000.000 VND~~.
```

This makes RAG evidence clearer because current price and old/listed price are
not collapsed into one ambiguous number sequence.

Product/accessory listing links with embedded prices are also normalized. A raw
rendered link like:

```md
[ Tham Cop 3D VF 6 990.000 VND ](https://shop.example/p1.html "Tham Cop")
```

becomes:

```md
- Tham Cop 3D VF 6: gia ban hien tai / current price 990.000 VND. Link: https://shop.example/p1.html
```

This makes each product price explicitly a current sale price instead of an
unlabeled number inside a card/gallery chunk.

## Handoff To Non-Ingestion Owners

Review outputs under `guide/demo/url-ingestion-human-review/output` and
`guide/demo/url-ingestion-comparison-review/output` identified follow-up work
outside `src/agentic_rag/ingestion`. URL ingestion now emits clearer Markdown and
metadata, but downstream modules need to consume that signal.

Prepared handoff comment:

```text
guide/reports/url_ingestion_external_owner_comment.md
```

Short version for the outside owner:

- Retrieval should index or query against `Chunk.metadata["search_aliases"]`
  and inspect `metadata["content_origin"] == "interactive_probe"` for dynamic
  configurator evidence.
- Generation should answer configurator price questions from the explicit
  `base price + option delta = final price` probe lines. If only a delta is
  retrieved without the matching variant base price, the answer should ask for
  more evidence instead of borrowing a price from another variant.
- Frontend/demo callers should expose `max_child_pages` and use a review default
  such as `10` for landing/listing pages, while keeping API-level ingestion
  default deterministic.
- Evaluation should add cases for `VF 9 Plus tuy chon 7 cho + mau nang cao`
  expecting `1.711.000.000 VND`, and `VF 9 Plus tuy chon ghe co truong + mau
  nang cao` expecting `1.743.000.000 VND`.

## Artifacts

When `data_artifact_dir` is provided, ingestion writes:

- `parsed.md`: cleaned Markdown used for inspection.
- `chunks.jsonl`: serialized shared `Chunk` records.
- `manifest.json`: run metadata, source metadata, artifact paths, parser name,
  and chunk count.

Example:

```python
from pathlib import Path

from agentic_rag.ingestion.url.loader import load_url_with_artifacts

document = load_url_with_artifacts(
    "https://example.com/article",
    data_artifact_dir=Path("src/agentic_rag/ingestion/url/data"),
    run_id="example-url-run",
)

print(len(document.chunks))
print(document.artifacts.run_dir if document.artifacts else None)
```

## RAG Suitability

URL chunks use the shared `agentic_rag.core.contracts.Chunk` contract. This makes
them directly usable by retrieval and generation modules without importing
private URL ingestion details.

For RAG, inspect:

- chunk text readability,
- section metadata,
- URL/canonical URL metadata,
- chunk length distribution,
- whether top retrieval results contain content rather than boilerplate.

If retrieval ranks footer, cookie, script, or related-post chunks too highly,
improve ingestion-side filtering before changing retrieval or generation.

## Known Follow-up

Some configurator pages need stronger structured contracts beyond Markdown probe
records. For a stronger contract, add a shared configurator/commerce record that
emits fields such as:

- variant code,
- variant label,
- base price,
- color price delta,
- final price,
- availability,
- asset/reference links.

Image alt text and color assets should be stored as metadata or reference links
when possible, instead of repeated heavily inside chunk text.

## Quality Gate

Run the module tests after changing URL ingestion:

```bash
uv run pytest src/agentic_rag/ingestion/url/tests -q
```

Run the project gate before opening or updating a PR:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest -q
```
