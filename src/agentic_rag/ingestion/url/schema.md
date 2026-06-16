# URL Ingestion Schema

This file explains how URL ingestion maps its metadata into the general
Agentic RAG chunk schema.

Rule of thumb: URL ingestion should add metadata that can be proven from the
URL, parser, DOM, rendered state, or deterministic extractors. PDF-only,
storage-only, and LLM-only fields should stay absent until the correct process
owns them.

## Canonical Shared Fields

| Field | URL status | URL source | Process owner | Notes |
| --- | --- | --- | --- | --- |
| `source` | Required | Final source URL or HTML/text source | URL loader | Used for citations and grouping. This is the concrete URL/path/source string. |
| `source_type` | Required | Shared source category: `official`, `internal`, `partner`, `news`, `community`, or `unknown` | URL loader | Required by shared ingestion metadata. VinFast official domains map to `official`; local/manual HTML or text maps to `internal`. |
| `url` | Required for URL/HTML URL input | Canonical URL, final URL, source URL, then original URL | URL metadata | Must be exact. Do not rewrite with LLM. |
| `file_name` | Not needed for normal URL | None | PDF/file ingestion | Only add for downloaded files or file ingestion. |
| `document_type` | Optional, added when inferred | URL `page_type` / quality gate page type | URL metadata + quality gate | General alias for `page_type`. Examples: `product_detail`, `policy`, `faq`, `vehicle_or_product_page`. Do not require this for all chunks. |
| `product_model` | Added when detected | Product spec/entity extractor | URL entities | Current URL value is the primary model string for compatibility. Storage normalization may convert to list. |
| `language` | Added when available | HTML `lang` / page metadata | URL parser | Do not guess if parser cannot determine it. |
| `page_number` | Not needed for normal URL | None | PDF parser | Do not fake page numbers for web pages. |
| `section` | Added | Markdown/DOM heading | URL chunker | Existing URL-local structural field. |
| `heading` | Added | Alias of `section` | URL metadata | General schema name for rule-based integration. |
| `breadcrumb` | Added | Alias of `section_path` | URL metadata | General schema name for heading path. |
| `created_date` | Added only when exact | Source modified metadata such as `article:modified_time` | URL parser | Optional. This is source-derived modified information when the page exposes it. Do not hallucinate. |
| `created_date_source` | Added with `created_date` | `page_modified_metadata` | URL parser | Optional provenance for rule-based checks. |
| `updated_date` | Required | Ingestion/crawl start timestamp | URL loader | Required shared timestamp for when this system started ingesting the URL. |
| `updated_date_source` | Added | `ingestion_start` | URL loader | Tells consumers that `updated_date` is an ingestion timestamp, not a source freshness claim. |
| `ingested_at` | Not added by URL chunks | Storage timestamp | Storage layer | Storage should stamp this separately. |
| `summary` | Not added by base URL ingestion | None | LLM enrichment | `description` can support summaries, but is not the same field. |
| `topic_tags` | Not added by base URL ingestion | None | LLM enrichment with controlled vocabulary | Keep downstream so tags stay consistent. |
| `keywords` | Not added by base URL ingestion | None | Statistical or LLM enrichment | Add after chunking if hybrid retrieval needs it. |
| `entities` | Added | Alias of extracted entity names | URL entities | General schema list for rule-based filtering. Rich details stay in URL-local fields. |
| `quality_score` | Not added by URL ingestion | None | Rule-based/LLM quality enrichment | URL ingestion is not the owner. Use `url_status` for crawl/parser acceptance. |
| `chunk_id` | Required | Shared Chunk ID | URL chunker | Also copied into metadata for storage payloads. |
| `chunk_index` | Added | Alias of `chunk_part_index` | URL metadata | 1-based index inside the source section/state list. |
| `token_count` | Added | Alias of `chunk_token_count` | URL metadata | Approximate chunk token count for filtering/debug. |
| `document_id` | Not added by URL ingestion | None | Storage layer | Storage should stamp this after document creation. |

## URL-Local Fields Kept

These fields remain because demos, golden evaluation, dedup detection, and
debugging already use them.

| Field | Keep? | Why |
| --- | --- | --- |
| `domain` | Yes | Fast domain grouping and source filtering. |
| `original_url` | Yes | Redirect/debug trace. |
| `canonical_url` | Yes | Canonical grouping and dedup hints. |
| `title` | Yes | Display title and fallback context. |
| `published_at` | Yes | Raw parser publish date. Kept URL-local; not the shared `created_date`. |
| `fetched_at` | Yes, URL-local only | Crawl timestamp used for debugging/artifacts. Not a shared schema field. |
| `captured_at` | Yes, URL-local only | Render/interaction timestamp used for debugging/artifacts. Not a shared schema field. |
| `page_type` | Yes | URL-local page classifier. `document_type` is the shared alias. |
| `section_path` | Yes | Full heading path. `breadcrumb` is the shared alias. |
| `chunk_token_count` | Yes | Existing chunker field. `token_count` is the shared alias. |
| `chunk_part_index` / `chunk_part_total` | Yes | Existing split order fields. `chunk_index` is the shared alias. |
| `page_hash`, `content_hash`, `dedupe_hash`, `normalized_text` | Yes | Dedup and regression evaluation. |
| `url_quality` | Yes | Parser diagnostics before quality gate. |
| `url_quality_gate` | Yes | Parser acceptance/rejection and render decision. |
| `url_status` | Yes | URL-owned acceptance status: `accepted`, `partial`, or `rejected`. |
| `entity_type`, `entity_name`, `entity_names`, `entity_types`, `entity_hash` | Yes | Rich URL entity diagnostics. `entities` is the shared lightweight list. |
| `product_specs`, `product_spec_fields` | Yes | Structured product facts for rule-based checks. |
| `product_price`, `driving_range`, `battery_capacity`, `charging_time`, `vehicle_segment` | Yes | Common VinFast product facts for retrieval and conflict checks. |
| `attribute_group` | Yes | Rule-based grouping such as `pricing_specs` or `battery_range`. |
| `is_noise`, `retrieval_weight` | Yes | Retrieval filtering and scoring. |
| `interaction_*`, `variant_*`, `image_url`, `image_snapshot_ref(s)` | Yes | JavaScript interaction/state capture artifacts. |

## Field Ownership By Process

| Process | Should add | Should not add |
| --- | --- | --- |
| URL acquisition | `source`, category `source_type`, `updated_date`, `url`, `original_url`, `final_url`, fetch/render trace | `summary`, `topic_tags`, `document_id` |
| URL parser | `title`, `language`, `published_at`, source-derived `created_date`, `author`, `canonical_url`, assets | Guessed dates, PDF page numbers |
| URL chunker | `chunk_id`, `section`, `section_path`, `chunk_token_count`, hashes | LLM semantic tags |
| URL metadata/entities | `heading`, `breadcrumb`, `document_type`, `entities`, `product_model`, `product_specs` | Conflict decisions or duplicate merge results |
| URL quality gate | `url_status`, `url_quality_gate`, `render_required` | Shared `quality_score` and final storage status |
| URL interactions | `interaction_state`, `variant_options`, `product_price`, `image_snapshot_ref(s)` | Unsafe checkout/payment actions |
| Storage layer | `document_id`, `ingested_at`, Qdrant payload indexes | Parser-only raw diagnostics if not needed in storage |
| LLM enrichment | `summary`, `topic_tags`, optional `keywords`, optional entity normalization | Exact URL, exact dates, page numbers |
| PDF ingestion | `file_name`, `page_number`, PDF headings/OCR quality | URL render metadata |
| Dedup/conflict modules | Dedup primary layer, conflict status, canonical fact records | Raw crawling/parsing responsibilities |

## Minimal Rule-Based Contract

Rule-based consumers should prefer the shared names first:

```python
def evidence_label(chunk):
    metadata = chunk.metadata
    return {
        "url": metadata.get("url"),
        "document_type": metadata.get("document_type") or metadata.get("page_type"),
        "heading": metadata.get("heading") or metadata.get("section"),
        "breadcrumb": metadata.get("breadcrumb") or metadata.get("section_path"),
        "entities": metadata.get("entities") or metadata.get("entity_names") or [],
        "updated_date": metadata["updated_date"],
        "updated_date_source": metadata.get("updated_date_source"),
        "url_status": metadata.get("url_status"),
    }
```

For product facts, use URL-local fields because they are more precise:

```python
def product_fact_records(chunk):
    metadata = chunk.metadata
    specs = metadata.get("product_specs") or {}
    entity = metadata.get("entity_name") or metadata.get("product_model")
    return [
        {
            "entity": entity,
            "field": field,
            "value": value,
            "source_url": metadata.get("url"),
            "canonical_url": metadata.get("canonical_url"),
            "captured_at": metadata.get("captured_at") or metadata.get("fetched_at"),
            "chunk_id": chunk.chunk_id,
        }
        for field, value in specs.items()
    ]
```

## Not Needed In URL Ingestion

- Do not add `page_number` for normal web pages.
- Do not add `file_name` unless the URL is converted into a file ingestion job.
- Do not put transport labels such as `url`, `html`, `text`, or `pdf` into
  `source_type`. Use the shared source category enum instead.
- Do not leave `updated_date` empty. It is the ingestion start timestamp.
- Do not use `fetched_at` as a shared metadata field. It may stay URL-local for
  debug/artifact review only.
- Do not use LLMs to rewrite `url`, `source`, `created_date`, or hashes.
- Do not add top-level `quality_score`; URL ingestion only emits `url_status`
  and `url_quality_gate` diagnostics. Rule-based/LLM enrichment can add
  `quality_score` later.
- Do not add `summary`, `topic_tags`, or `keywords` in the base parser; run those
  as a separate enrichment process.
- Do not let URL ingestion decide duplicate merge or conflict resolution. It only
  emits hashes, canonical URLs, entities, and product facts for those modules.
