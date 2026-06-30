# Orchestration

Target home for layer ordering and report aggregation.

Responsibilities:

- Run exact checks before lexical checks.
- Exclude pairs already found by earlier layers.
- Run semantic checks last and only when configured.
- Return one stable `DedupReport`.

Current code: `src/agentic_rag/ingestion/dedup_detect/pipeline.py`.
