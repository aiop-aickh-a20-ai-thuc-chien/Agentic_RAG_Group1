# VinFast URL Golden Evaluation

This note explains how to use the VinFast golden data in this folder.

## Files

- `Link_data.txt`: URL run list, one URL per line.
- `vinfast_url_golden_samples.json`: expectations for URL ingestion output.

## Expected Flow

```text
Link_data.txt
  -> load each URL with URL ingestion
  -> collect markdown, chunks, and metadata
  -> match URL to vinfast_url_golden_samples.json sample
  -> evaluate chunk count, snippets, metadata, and normalization checks
```

## Assertion Levels

Start with loose checks:

- `min_chunk_count`
- `max_chunk_count`
- `required_metadata_keys`
- `required_text_snippets`
- `product_spec_checks`
- `forbidden_text_snippets`
- `normalization_checks`

Use `optional_text_snippets` for diagnostics and review notes, not hard failure.
Use optional `product_spec_checks` first for live pages where prices or specs
may change, then make them required after a stable static fixture exists.

Enable `entity_boundary_checks` only after the page has a stable static fixture
or DOM-aware chunking is implemented for that page type.

## When To Add Static Fixtures

Create a scenario folder from `template/` when a URL exposes a behavior that
should be deterministic:

- product cards are merged incorrectly,
- FAQ items are split incorrectly,
- comparison-table rows lose headers,
- footer/navigation text dominates chunks,
- canonical URL or language metadata is missing.

Live pages can change. Static fixtures are the source of truth for strict tests.
