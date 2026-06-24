# Guide Learning Map

Use this folder as a learning workspace for ingestion, retrieval, evaluation, and
review tooling. Start with the focused guides below before opening generated
reports or demo outputs.

## Recommended Path

1. Read `guide/url-ingestion-guide.md` to understand how a URL becomes Markdown
   and shared `Chunk` objects.
2. Read `guide/url-css-html-dynamic-markdown-guide.md` when visual HTML, CSS,
   or JavaScript behavior affects Markdown extraction.
3. Read `guide/duplicate-detection-guide.md` to understand how duplicate signals
   are detected and attached as metadata.
4. Read `guide/knowledge-quality-conflict-detection-guide.md` to understand how
   contradictory facts are detected after ingestion.
5. Use `guide/agentic-rag-pipeline-report.md` when you need the full pipeline
   context across API, ingestion, retrieval, generation, and evaluation.
6. Use demos only after reading the guide for the topic you are testing.

## Focus Areas

| Goal | Start Here | Deeper References |
| --- | --- | --- |
| Learn URL ingestion | `guide/url-ingestion-guide.md` | `src/agentic_rag/ingestion/url/README.md`, `guide/demo/url-golden-review-react/README.md`, `guide/demo/url-crawl-review/README.md` |
| Preserve CSS/HTML/JS meaning in URL Markdown | `guide/url-css-html-dynamic-markdown-guide.md` | `guide/url-css-html-dynamic-implementation-decision-plan.md`, `src/agentic_rag/ingestion/url/TODO_rulebased.md`, `src/agentic_rag/ingestion/url/TODO_LLM.md`, `src/agentic_rag/ingestion/url/interactions/README.md` |
| Plan DOM-aware URL chunking | `guide/dom-aware-chunking-strategy.md` | `src/agentic_rag/ingestion/url/TODO.md`, `src/agentic_rag/ingestion/url/TODO_scripts.md` |
| Learn duplicate detection | `guide/duplicate-detection-guide.md` | `src/agentic_rag/ingestion/url/TODO_dedup.md`, `src/agentic_rag/ingestion/dedup_detect/README.md`, `guide/dedup-detect-implementation-report.md` |
| Learn conflict detection | `guide/knowledge-quality-conflict-detection-guide.md` | `src/agentic_rag/ingestion/url/TODO.md`, `tests/test_ingestion_knowledge_quality_v2.py` |
| Understand the full RAG flow | `guide/agentic-rag-pipeline-report.md` | `docs/module-contracts.md` |
| Build evaluation data | `guide/reports/evaluation_data_guide.md` | `guide/reports/auto_data_tool/README.md` |

## Folder Notes

- `guide/demo/url-golden-review-react/` is the current URL ingestion
  golden-data React demo.
- `guide/demo/` contains local review apps and scripts. Treat `output/`
  subfolders as generated review artifacts.
- `guide/research/` contains exploratory notes and external research summaries.
- `guide/reports/` contains evaluation-data tooling and report assets. Treat
  live crawl outputs and render caches as generated verification artifacts.
- `guide/results/`, `guide/report/`, and `guide/test_logs/` are historical or
  generated result folders.

Keep new learning material small and task-oriented. Put broad implementation
findings in a report, but link to them from the focused guide instead of making
the first reading path longer.
