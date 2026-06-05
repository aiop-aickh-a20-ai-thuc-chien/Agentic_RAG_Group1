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
- `extractor.py`: Trafilatura adapter used for lightweight fallback fetching,
  precision-oriented quality checks, and main-content Markdown extraction.
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
3. If Crawl4AI is unavailable or fails, the loader tries Trafilatura's lightweight
   URL fetcher next.
4. If Trafilatura fetch returns empty HTML or fails, the loader falls back to the
   deterministic `urllib` fetch path with the project user agent.
5. `parse_html()` extracts structured page metadata and section boundaries from
   the HTML.
6. Crawl4AI generates primary cleaned Markdown with common VinFast/SFCC noise
   selectors removed. It also builds an optional BM25-filtered Markdown view with
   an English/Vietnamese vehicle query and stemming disabled so Vietnamese words
   are not mangled.
7. Trafilatura runs as a precision-oriented quality check. Crawl4AI remains the
   selected parser when its primary Markdown is usable; Trafilatura or the
   Crawl4AI BM25 view is selected only when the primary Crawl4AI output fails the
   quality check or when another candidate has enough content with materially
   lower image/link/boilerplate noise.
8. Candidate Markdown is scored for useful content, headings, title match, price
   values, image/link density, and boilerplate risk. Price score is capped so a
   long gallery/listing page with many prices does not automatically beat a
   cleaner main-content extraction. The selected parser and candidate scores are
   stored in `Chunk.metadata["markdown_quality"]`.
9. Crawl4AI table output is appended as `# Structured Page Data` Markdown when
   available. Chunks from this supplement use
   `Chunk.metadata["content_origin"] == "structured_parse"`.
10. The loader removes common script/config/cookie/login/cart/menu boilerplate
   from Markdown.
11. Supported interactive pages are probed for important JS state that is not
   reliably visible in the default rendered page.
12. VinFast vehicle price-card text is normalized so current prices and old
   crossed prices remain explicit in Markdown.
13. The loader chunks global Markdown with heading-aware metadata and enriches
   each `Chunk.metadata` with URL metadata such as original URL, final URL,
   canonical URL, language, author, description, crawler name, parser name,
   source URL, section path, asset count, and dedupe hash.

Crawl4AI is preferred for live URLs because it can capture rendered content that
static HTML fetches often miss. Trafilatura remains useful as the lightweight
fetch fallback, quality check, and fallback extractor. `urllib` is the final
deterministic fetch fallback, and the builtin parser remains the deterministic
parser fallback for local HTML and tests.

If Crawl4AI succeeds but returns title-only content, URL ingestion treats that
as a quality failure and falls back to Trafilatura fetch before returning
chunks. This is different from retrying the same crawl in a loop: the module
switches extraction strategy because the rendered/cleaned source is not useful
for RAG.

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

This is useful for listing/card pages where the parent page links to product or
article detail pages. Keep `max_child_pages=0` for deterministic single-page
ingestion. For human review or frontend demos where a pasted landing/listing URL
is expected to gather enough product/article detail, pass an explicit value such
as `max_child_pages=10` from the caller rather than changing the ingestion
default.

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
