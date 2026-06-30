# Semantic Layer

Target home for embedding-similarity duplicate detection.

Responsibilities:

- Compare precomputed or runtime embedding vectors.
- Use high thresholds by default.
- Mark semantic matches as review signals unless a resolver policy has validated
  conflict checks.

Future safeguards should inspect entity names, dates, prices, numbers, and
technical specifications before any automatic action.

Current code: `src/agentic_rag/ingestion/dedup_detect/embedding.py`.
