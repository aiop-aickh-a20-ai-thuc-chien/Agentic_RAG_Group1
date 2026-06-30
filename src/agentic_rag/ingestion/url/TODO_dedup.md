# URL Ingestion TODO - Dedup Handoff

URL ingestion should provide clean text, stable chunks, and metadata that make
duplicate detection easier. The dedup decision still belongs in
`src/agentic_rag/ingestion/dedup_detect`, and fact-conflict decisions belong in
`src/agentic_rag/ingestion/knowledge_quality`.

## URL-Owned Handoff Fields

- `page_hash`: stable hash of normalized page Markdown.
- `content_hash`: stable hash of normalized chunk text.
- `dedupe_hash`: aggressively normalized chunk hash for exact duplicate
  blocking.
- `normalized_text`: normalized chunk text used for hash/debug inspection.
- `domain`, `source_url`, `original_url`, `final_url`, and `canonical_url`:
  source identity and redirect/canonical context.
- `language`, `published_at`, `captured_at`, and `fetched_at`: temporal and
  locale context for downstream blocking and conflict checks.
- `page_type`, `extractor_page_type`, and `url_quality_gate`: parser-selection
  and quality context.
- `section`, `section_path`, `dom_path`, `chunk_type`, and `attribute_group`:
  local structure hints for chunk comparison.
- `entity_type`, `entity_name`, `entity_hash`, and `vehicle_segment`: entity
  blocking hints.
- `product_specs`, `product_model`, `product_price`, `driving_range`,
  `battery_capacity`, and `charging_time`: structured product facts for later
  dedup/conflict workflows.
- `is_noise` and `retrieval_weight`: local ranking/noise hints.

## TODO

1. Build deterministic URL fixtures for duplicate product cards, listings,
   articles, policies, FAQ items, and repeated footer/navigation chunks.
2. Verify exact duplicate detection can use `dedupe_hash` without re-parsing URL
   text.
3. Verify near-duplicate blocking can use `domain`, `page_type`,
   `entity_type`, `entity_name`, `attribute_group`, and `language`.
4. Make sure product variants and trims are not merged simply because they share
   one model family or page template.
5. Send stale or conflicting product facts to `knowledge_quality`; do not solve
   conflict detection in URL ingestion.
6. Keep duplicate-candidate metadata additive so the shared `Chunk` contract and
   URL loader outputs remain stable.

