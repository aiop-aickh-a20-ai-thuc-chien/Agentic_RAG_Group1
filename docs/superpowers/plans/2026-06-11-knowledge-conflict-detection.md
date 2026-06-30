# Conflict-First Knowledge Quality Detection Plan

## Summary

Build the conflict-detection slice for backlog
[agentic-rag-notebooks#51](https://github.com/aiop-aickh-a20-ai-thuc-chien/agentic-rag-notebooks/issues/51),
using
[#164](https://github.com/aiop-aickh-a20-ai-thuc-chien/agentic-rag-notebooks/issues/164)
as the research and metadata framing. The v1 target is conflict-first: implement
enough duplicate detection to satisfy backlog compatibility, but optimize design,
tests, UI, and evaluation around same-topic factual conflicts.

Research direction: use a layered, cost-gated pipeline. This matches recent work
such as ConflictRAG, DRAGged into Conflicts, TruthfulRAG, MiniCheck, LSHBloom,
and ARES-style RAG evaluation. Default runtime is offline-first: deterministic
rules, current local chunks, and no paid or network LLM calls.

## Key Changes

- Add real implementations under `src/agentic_rag/ingestion/knowledge_quality/`:
  - Scanner: exact duplicate via normalized text hash; near duplicate via
    token-shingle similarity.
  - Extractor: deterministic Vietnamese/English numeric facts for `price`,
    `date`, `duration`, and `distance_km`, with entity detection for VinFast/VF
    model names.
  - Verifier: rule-based conflict detection for same
    `entity + attribute + scope` with incompatible normalized values.
  - Arbiter/reporting: severity, suggested action, and Markdown/JSON summaries.

- Extend public contracts without changing existing `Chunk`, `SearchResult`, or
  `Answer` behavior:
  - Add frozen Pydantic models: `KnowledgeQualityFact`,
    `KnowledgeQualityFinding`, `KnowledgeQualityReport`.
  - Findings use stable fields: `finding_id`, `kind`, `severity`, `status`,
    `chunk_ids`, `fact_ids`, `summary`, `suggested_action`, `confidence`,
    `metadata`.
  - Store annotations inside `Chunk.metadata["knowledge_quality"]`; keep
    source-specific and flexible data inside metadata, not new top-level `Chunk`
    fields.

- Integrate at the existing local ingestion boundary:
  - Run quality analysis in `LocalPdfEvidenceProvider` after PDF/URL/text chunks
    receive local metadata and before chunks are persisted/indexed.
  - Compare new chunks against already stored local chunks, excluding re-uploaded
    chunks from the same `document_id`.
  - Persist annotations through current JSONL/S3/Postgres chunk metadata; do not
    add a new database table for v1.
  - Do not modify `src/agentic_rag/retrieval/search.py`.

- Add FastAPI review endpoints:
  - `GET /sources/{document_id}/quality`: findings and extracted facts for one
    document.
  - `GET /knowledge-quality?document_ids=...`: aggregate findings for
    selected/all local documents.
  - `POST /knowledge-quality/scan`: re-scan current local KB and return a fresh
    report.
  - For non-`local_pdf` providers, return a clear unsupported response instead
    of partial RAGFlow behavior.

- Add existing Next.js UI integration:
  - Add a `Quality` tab to the citation-chat source debug view.
  - Add source-list badges for duplicate/conflict counts.
  - Show conflict cards with chunk IDs, source names, extracted spans,
    normalized values, severity, and suggested action.
  - Do not create a separate Streamlit/Gradio app.

- Add docs and demo assets:
  - Add `docs/knowledge-quality-conflict-detection.md` covering research
    summary, architecture, commands, and Q&A points.
  - Update README/offline-ingestion guide with `GET /knowledge-quality` and demo
    steps.
  - Add a small sample KB fixture with exact duplicate, near duplicate,
    warranty-duration conflict, price conflict, and km/range conflict.
  - Add a short evaluation report template suitable for the 5-10 slide demo.

## Multi-Agent Workflow

- Use implementation subagents only for disjoint work:
  - Backend contracts/core detector.
  - Provider/API integration.
  - Frontend source-debug UI.
  - Evaluation/docs.
- Keep the runtime design as a staged pipeline, not a heavy multi-agent
  LangGraph feature:
  - Scanner narrows candidates.
  - Extractor normalizes facts.
  - Verifier assigns rule verdicts.
  - Arbiter chooses severity/action.
  - Curator emits review output.
- Optional future LLM verifier can use the existing `INGESTION_LLM_*` profile,
  disabled by default.

## Test Plan

- Unit tests:
  - Exact duplicate and near-duplicate detection.
  - Numeric fact extraction for price, date, duration, and km.
  - Conflict detection when same entity/attribute has incompatible values.
  - No conflict when equivalent values are formatted differently.
  - Pydantic contract validation and package exports.

- Integration tests:
  - Local text/PDF/URL upload annotates chunks before storage/indexing.
  - JSONL/S3/Postgres-compatible metadata round-trips through existing store
    interfaces.
  - `/sources/{document_id}/quality`, `/knowledge-quality`, and
    `/knowledge-quality/scan` return stable response shapes.
  - Source debug response remains backward compatible.

- UI checks:
  - `frontend` build passes.
  - Source list shows quality badges without layout breakage.
  - Source debug `Quality` tab renders empty, duplicate, and conflict states.

- Verification commands:
  - `uv run ruff format --check .`
  - `uv run ruff check .`
  - `uv run mypy`
  - `uv run pytest -q`
  - `cd frontend && npm run build`

## Assumptions

- Branch should be `feature/knowledge-conflict-detection`.
- Do not stage unrelated existing dirty files under `docs/superpowers/` unless
  explicitly requested.
- V1 must work without API keys, network model calls, or external vector
  database.
- Duplicate auto-resolve, version-aware resolution, and LLM/NLI verification are
  future enhancements unless needed for a narrow demo fallback.
