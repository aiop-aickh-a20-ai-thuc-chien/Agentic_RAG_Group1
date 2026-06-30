# MinHash Layer

Planned layer for near-duplicate detection with token shingles and approximate
Jaccard similarity.

Use cases:

- Web-crawl content with copy edits.
- Pages with repeated blocks and light wording changes.
- Larger crawl sets where LSH can reduce pairwise comparisons.

Implementation notes:

- Keep disabled by default until thresholds are validated.
- Add deterministic tests for shingle generation, signature stability, and
  similarity estimates.
- Compare results against SimHash before changing ingestion policy.
