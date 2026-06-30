# URL Metadata Explained

This guide explains how to use `Chunk.metadata` emitted by URL ingestion.
The shared `Chunk` contract stays small:

```python
Chunk(
    chunk_id="...",
    text="...",
    metadata={...},
)
```

All URL-specific details live inside `metadata`. Downstream retrieval,
deduplication, conflict detection, evaluation, and frontend tools should read
metadata with `.get(...)` because some fields are only present for certain input
types, parser paths, or page types.

## Where Metadata Comes From

URL ingestion adds metadata in layers:

| Layer | File | What it adds |
| --- | --- | --- |
| Base chunking | `loader.py`, `chunking/` | source, title, section, hashes, token counts, section paths |
| URL enrichment | `metadata/enrichment.py` | URL identity, language, DOM/entity hints, product specs, noise/ranking hints |
| Quality diagnostics | `quality/diagnostics.py` | `url_quality` parse/chunk quality report |
| Quality gate | `quality/strategy.py` | `url_quality_gate`, `render_required`, final parser/page-type decision |
| Artifacts | `artifact.py` | `cleaned.html`, `parsed.md`, `chunks.jsonl`, `manifest.json` for inspection outside the chunk |

The final metadata is additive. URL ingestion should not decide duplicate merges
or fact conflicts; it should provide enough metadata for the dedicated
`dedup_detect` and `knowledge_quality` packages to make those decisions later.

## Field Groups

### Source And Citation Fields

Use these fields to trace a chunk back to its page.

| Field | Meaning | Typical use |
| --- | --- | --- |
| `source` | Loader source used to build the chunk | Exact URL/path/source label and citation fallback |
| `source_type` | Shared source category: `official`, `internal`, `partner`, `news`, `community`, or `unknown` | Filter by source trust/origin category |
| `url` | Best citation URL after canonical/final URL handling | Show in citations and review UI |
| `domain` | URL domain | Domain filters and grouping |
| `original_url` | URL requested by the caller | Debug redirects and query-param-sensitive pages |
| `canonical_url` | Page-declared canonical URL when present | Canonical grouping and citation checks |
| `title` | Parsed page title or extracted title | Result labels and snippet headings |
| `language` | HTML/page language when detected | Language filters and conflict grouping |
| `author` | Page author metadata when present | Article attribution |
| `published_at` | Page publish time when present | Freshness/conflict checks |
| `fetched_at` | Time the chunk was produced | Crawl recency |
| `captured_at` | URL metadata copy of `fetched_at` | Conflict and golden checks |

Use `url` for user-facing citation links. Use `original_url` when the exact
requested URL matters, such as query params that open a FAQ section. Use
`canonical_url` for grouping, but do not assume it preserves query params.

### Structure Fields

Use these fields to preserve page and section context.

| Field | Meaning | Typical use |
| --- | --- | --- |
| `section` | Current Markdown heading or logical section | Display labels and section filters |
| `section_level` | Markdown heading depth | Hierarchical UI display |
| `section_path` | Heading path as a list | Build breadcrumbs and parent-child context |
| `full_path` | Full chunk path from chunker when available | Debug chunk placement |
| `depth` | Chunk depth from chunker when available | Parent/child ranking |
| `part_index` / `part_total` | Split part inside a long section when available | Recombine or sort sibling chunks |
| `chunk_part_index` / `chunk_part_total` | Paragraph chunk split indices for simple text path | Recombine or sort simple text chunks |
| `chunk_token_count` | Estimated token count for the chunk | Token budgeting and chunk-shape checks |

For retrieval display, combine `title`, `section_path`, and the first lines of
`text`. For evaluation, use section fields to detect orphan chunks or broken
table/spec rows.

### Hash And Duplicate Fields

Use these fields for exact and near-duplicate blocking.

| Field | Meaning | Typical use |
| --- | --- | --- |
| `page_hash` | Stable hash of normalized parsed page Markdown | Detect same page snapshot |
| `content_hash` | Stable hash of normalized chunk text | Exact same chunk content |
| `dedupe_hash` | More aggressively normalized chunk hash | Exact duplicate blocking across templates |
| `normalized_text` | Normalized text used for hash/debug inspection | Debug why hashes match |
| `url_source_hash` | Short hash of best URL identity | Stable source grouping |

Recommended flow:

1. Use `dedupe_hash` for exact duplicate candidates.
2. Use `content_hash` when you need a stricter content match.
3. Use `page_hash` to group chunks from the same parsed page snapshot.
4. Use `domain`, `page_type`, `entity_type`, and `attribute_group` for
   near-duplicate blocking before expensive similarity checks.

### Page-Type And Parser Fields

Use these fields to understand why static or rendered parsing was selected.

| Field | Meaning | Typical use |
| --- | --- | --- |
| `page_type` | Final page type after quality gate when available | Routing, indexing policy, evaluation |
| `extractor_page_type` | Extractor/normalizer content type | Debug extractor behavior |
| `render_required` | Whether profile required browser rendering | Latency and parser diagnostics |
| `url_quality_gate` | Parser-selection decision payload | Accept/reject/retry/debug |
| `url_quality` | Parse/chunk quality report | Noise, empty, or low-signal diagnostics |

`url_quality_gate` contains:

```json
{
  "parser": "static",
  "status": "accepted",
  "accepted": true,
  "score": 7,
  "reason": "parser_output_satisfied_quality_gate",
  "page_type": "generic",
  "requires_rendered_parser": false,
  "dynamic_signals": [],
  "latency_budget_seconds": 8,
  "browser_error": null
}
```

`url_quality` contains:

```json
{
  "verdict": "useful",
  "markdown_word_count": 240,
  "heading_count": 3,
  "chunk_count": 4,
  "boilerplate_hit_count": 0,
  "useful_chunk_count": 4,
  "issues": []
}
```

When `url_quality_gate.accepted` is false, do not silently index the chunks as
normal evidence. Either send them to a review queue, keep them only as debug
artifacts, or index them with a low weight and an explicit warning.

### DOM And Entity Fields

Use these fields to preserve product/card/FAQ/table boundaries.

| Field | Meaning | Typical use |
| --- | --- | --- |
| `semantic_block_count` | Number of detected semantic DOM blocks | Parser/debug health |
| `semantic_block_types` | Counts by DOM block type | Page-shape diagnostics |
| `entity_count` | Number of extracted URL entities | Entity coverage |
| `entity_types` | Counts by entity type | Product/FAQ/table routing |
| `entity_names` | Entity names found on the page | Search facets and review |
| `entity_type` | Best entity type for this chunk | Blocking and retrieval boosting |
| `entity_name` | Best entity name for this chunk | Entity-specific citation and conflict grouping |
| `entity_hash` | Stable hash of entity type/name | Duplicate and conflict blocking |
| `vehicle_segment` | Vehicle class/segment when detected | Product filters |
| `attribute_group` | Fact group such as pricing, battery, FAQ, policy | Retrieval boosting and conflict routing |

Recommended usage:

- Boost chunks with `entity_type in {"vehicle", "product"}` for product
  questions.
- For FAQ questions, prefer `attribute_group == "faq"` or `entity_type ==
  "faq_item"`.
- For policy questions, prefer `attribute_group == "policy_terms"` or
  `page_type == "policy"`.
- For conflict detection, group by `entity_hash` or by normalized
  `entity_name` plus `domain` and `language`.

### Product Spec Fields

Use these fields for exact product facts.

| Field | Meaning | Typical use |
| --- | --- | --- |
| `product_specs` | Structured product facts detected for the chunk | Exact-value retrieval and conflict checks |
| `product_spec_fields` | Sorted keys present in `product_specs` | Fast filtering |
| `product_model` | Shortcut for `product_specs["model_name"]` | Model grouping |
| `product_price` | Shortcut for `product_specs["price"]` | Price retrieval/conflict checks |
| `driving_range` | Shortcut for `product_specs["driving_range"]` | Range retrieval/conflict checks |
| `battery_capacity` | Shortcut for `product_specs["battery_capacity"]` | Battery retrieval/conflict checks |
| `charging_time` | Shortcut for `product_specs["charging_time"]` | Charging retrieval/conflict checks |

Use `product_specs` as metadata filters, but still cite the chunk text when
answering a user. Metadata is a structured hint; the chunk text remains the
evidence shown to retrieval/generation.

### Noise And Ranking Fields

Use these fields to keep retrieval quality high.

| Field | Meaning | Typical use |
| --- | --- | --- |
| `is_noise` | URL-local guess that chunk is low-value boilerplate | Drop or downrank |
| `retrieval_weight` | Local ranking hint, usually `0.2`, `1.0`, `1.1`, or `1.2` | Score multiplier or rerank feature |

Recommended baseline:

```python
def is_indexable_url_chunk(chunk: Chunk) -> bool:
    metadata = chunk.metadata
    gate = metadata.get("url_quality_gate") or {}
    if metadata.get("is_noise") is True:
        return False
    if metadata.get("retrieval_weight", 1.0) < 0.5:
        return False
    if gate and gate.get("status") == "rejected":
        return False
    return True
```

## Common Recipes

### 1. Build A Citation

```python
def citation_from_url_chunk(chunk: Chunk) -> dict[str, str | None]:
    metadata = chunk.metadata
    return {
        "source": metadata.get("url") or metadata.get("source"),
        "chunk_id": chunk.chunk_id,
        "title": metadata.get("title"),
        "section": metadata.get("section"),
        "url": metadata.get("url"),
    }
```

Prefer `metadata["url"]` for the link shown to users. Keep `chunk_id` so the
answer can be traced back to a persisted `chunks.jsonl` record.

### 2. Filter Retrieval Candidates

```python
def url_retrieval_score_multiplier(chunk: Chunk) -> float:
    metadata = chunk.metadata
    if metadata.get("is_noise") is True:
        return 0.0
    weight = metadata.get("retrieval_weight")
    return float(weight) if isinstance(weight, int | float) else 1.0
```

Use the multiplier after BM25/dense scoring, or pass it as a reranker feature.
Do not remove low-weight chunks from debug reports; they are useful for finding
normalization gaps.

### 3. Route Product Questions

```python
def is_product_fact_chunk(chunk: Chunk) -> bool:
    metadata = chunk.metadata
    return bool(
        metadata.get("product_specs")
        or metadata.get("entity_type") in {"vehicle", "product"}
        or metadata.get("attribute_group") in {"pricing_specs", "battery_range"}
    )
```

For questions about model name, price, driving range, battery capacity, or
charging time, filter or boost chunks with `product_specs` first.

### 4. Send Facts To Conflict Detection

```python
def product_fact_records(chunk: Chunk) -> list[dict[str, object]]:
    metadata = chunk.metadata
    specs = metadata.get("product_specs") or {}
    if not isinstance(specs, dict):
        return []
    return [
        {
            "entity_name": metadata.get("entity_name") or metadata.get("product_model"),
            "field": field,
            "value": value,
            "source_url": metadata.get("url"),
            "canonical_url": metadata.get("canonical_url"),
            "captured_at": metadata.get("captured_at"),
            "chunk_id": chunk.chunk_id,
        }
        for field, value in specs.items()
    ]
```

URL ingestion should produce these records, but `knowledge_quality` should
decide whether values conflict.

### 5. Use Golden Evaluation Metadata Checks

Golden samples can require metadata keys and product spec checks:

```json
{
  "required_metadata_keys": [
    "source",
    "source_type",
    "title",
    "section",
    "content_hash",
    "canonical_url",
    "captured_at",
    "language",
    "domain",
    "page_type"
  ],
  "product_spec_checks": [
    {
      "name": "price present",
      "field": "price",
      "required": true
    }
  ]
}
```

Use golden metadata checks for stable contract fields. Avoid requiring fields
that are not expected on every page type, such as `product_price` on generic
articles.

## Field Availability Notes

- `load_url_with_artifacts()` attaches quality-gate metadata. Direct
  `load_html_with_artifacts()` may not have `url_quality_gate`.
- `page_type` can come from URL quality profiling for live URLs, or from DOM
  enrichment for direct HTML inputs.
- `canonical_url`, `language`, `author`, and `published_at` may be `None` when
  the page does not declare them.
- `product_specs` is empty for non-product pages and for product pages where
  facts are not visible or not yet extracted.
- `url_quality` and `url_quality_gate` are diagnostic metadata. Use them to
  decide indexing/review policy, but keep `parsed.md` and artifacts for deeper
  debugging.
- `final_url` and full artifact paths are stored in `manifest.json`, not always
  on each chunk. Use `document.artifacts.manifest_path` when you need full run
  diagnostics. With `data_artifact_dir`, the manifest links staged files:
  `source.html`, `cleaned.html`, `parsed_sections.txt`, `extracted.md`, final
  `parsed.md`, `quality.json`, and `chunks.jsonl`.

## Practical Defaults

For a first retrieval pipeline:

1. Index chunks where `is_noise` is not true and
   `url_quality_gate.status != "rejected"`.
2. Store `url`, `title`, `section`, `section_path`, `domain`, `language`,
   `page_type`, `content_hash`, and `dedupe_hash` as filterable metadata.
3. Store `product_specs`, `entity_name`, `entity_type`, and `attribute_group`
   as filterable metadata for product/spec questions.
4. Use `retrieval_weight` as a score multiplier.
5. Use `dedupe_hash` and `content_hash` before indexing to avoid repeated UI
   or duplicate product-card chunks.
6. Persist artifacts for failed, partial, or low-signal pages so the frontend
   and golden review demo can explain why a page passed or failed.

## What Not To Do

- Do not add URL-specific metadata as top-level `Chunk` fields.
- Do not treat `canonical_url` as the exact requested URL.
- Do not merge duplicate/conflict records inside URL ingestion.
- Do not answer from metadata alone when chunk text is missing.
- Do not silently index chunks whose quality gate is `rejected`.
