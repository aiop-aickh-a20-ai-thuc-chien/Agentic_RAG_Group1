# Quality

Target home for URL-local quality diagnostics.

Responsibilities:

- Score parsed Markdown usefulness.
- Detect boilerplate-heavy, low-signal, or loading-shell output.
- Explain whether browser rendering or static fallback produced the chunk text.
- Provide diagnostics for review demos and artifact manifests.

Cross-document duplicate detection belongs in `ingestion.dedup_detect`.
Conflict detection belongs in `ingestion.knowledge_quality`.
