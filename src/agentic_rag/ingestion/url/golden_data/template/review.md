# Template Review Notes

## Scenario

Describe the URL-ingestion behavior this sample is meant to protect.

Example:

- Product cards should keep entity boundaries.
- Navigation and footer text should not dominate chunks.
- Canonical URL metadata should be preserved.

## Source

- Static fixture: `source.html`
- Original live URL, if any: `https://example.com/sample-fixture`
- Captured date: `YYYY-MM-DD`

## Expected Behavior

- The parser should extract readable main content.
- The chunker should keep useful section context.
- Metadata should include source, source type, title, section path, and content
  hash.

## Known Limitations

Document any behavior that is not supported yet.

Example:

- DOM-aware product-card splitting is planned but not enabled.
- Full table row chunking is planned but not enabled.

## How To Enrich This Sample

1. Replace `source.html` with a focused static fixture.
2. Update `expected_chunks.json` with required and forbidden snippets.
3. Add entity or section boundary checks.
4. Add a focused test that loads this folder and validates the expectations.
