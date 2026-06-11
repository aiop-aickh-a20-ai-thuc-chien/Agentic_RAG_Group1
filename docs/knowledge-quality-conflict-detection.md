# Knowledge Quality: Conflict Detection

This feature adds an offline-first review layer for source quality before RAG
answers are generated. V1 focuses on conflicts between ingested chunks, with
duplicate detection included as a cheap compatibility and hygiene signal.

## Research Framing

Recent conflict-aware RAG work points to a staged pipeline instead of a single
expensive judge call:

- [ConflictRAG](https://arxiv.org/abs/2605.17301) uses a cost-gated detector
  plus selective refinement before generation.
- [DRAGged into Conflicts](https://arxiv.org/abs/2506.08500) frames conflict
  categories and shows that explicitly surfacing conflict type improves answer
  behavior.
- [TruthfulRAG](https://ojs.aaai.org/index.php/AAAI/article/view/40489/44450)
  turns factual claims into graph-style triples before reasoning over external
  evidence.
- [MiniCheck](https://arxiv.org/abs/2404.10774) shows why small fact-checking
  models are a practical middle ground for future verifier stages.
- [LSHBloom](https://arxiv.org/abs/2411.04257) keeps near-duplicate detection
  cheap at large scale by building on locality-sensitive hashing.
- [ARES](https://aclanthology.org/2024.naacl-long.20/) motivates component-level
  RAG evaluation rather than only end-answer scoring.

For this repo, v1 keeps the same architecture but uses deterministic local
rules:

```text
chunks
-> scanner: exact duplicate hash + token-shingle near duplicate
-> extractor: local numeric/date facts
-> verifier: same entity + attribute + unit with incompatible values
-> arbiter: severity, confidence, suggested action
-> curator: chunk metadata + API report + UI review
```

No external LLM, embedding API, vector database, or network call is required for
quality detection.

## Contracts

The shared contracts live in `src/agentic_rag/core/contracts.py`:

- `KnowledgeQualityFact`: normalized fact extracted from a chunk.
- `KnowledgeQualityFinding`: duplicate or conflict finding across chunks.
- `KnowledgeQualityReport`: facts, findings, and scan metadata.

Existing `Chunk`, `SearchResult`, and `Answer` models are unchanged. Per-chunk
summaries are stored under `Chunk.metadata["knowledge_quality"]`:

```json
{
  "duplicate_count": 0,
  "conflict_count": 1,
  "fact_count": 1,
  "finding_ids": ["kq-..."],
  "fact_ids": ["fact-..."]
}
```

## Local Provider Flow

`LocalPdfEvidenceProvider` runs quality detection after PDF/URL/text chunks get
local metadata and before chunks are written to JSONL/S3/Postgres or indexed.
The upload path compares new chunks against already stored chunks, excluding old
chunks from the same `document_id` so re-uploading a source does not conflict
with itself.

Fresh reports are computed from stored chunks:

```bash
curl http://127.0.0.1:8000/knowledge-quality
curl "http://127.0.0.1:8000/knowledge-quality?document_ids=text_base"
curl http://127.0.0.1:8000/sources/text_base/quality
curl -X POST http://127.0.0.1:8000/knowledge-quality/scan
```

The scan endpoint refreshes persisted `knowledge_quality` summaries for local
JSONL chunks. For cloud stores it still returns a fresh report; upload-time
annotations are already stored with the chunks.

Non-local providers return a clear unsupported response. V1 does not attempt to
inspect RAGFlow internals.

## Demo KB

`sample_knowledge_quality_chunks()` in `agentic_rag.testing.fixtures` contains
eight chunks:

| Case | Signal |
| --- | --- |
| `quality_warranty_a_c0001` + `quality_warranty_copy_c0001` | exact duplicate |
| `quality_warranty_near_c0001` | near duplicate |
| `quality_warranty_conflict_c0001` | warranty duration conflict |
| `quality_price_a_c0001` + `quality_price_b_c0001` | price conflict |
| `quality_range_a_c0001` + `quality_range_b_c0001` | distance/range conflict |

Quick local demo with API uploads:

```bash
curl -X POST http://127.0.0.1:8000/sources/text \
  -H "Content-Type: application/json" \
  -d '{"title":"Base","text":"VF8 duoc bao hanh 8 nam."}'

curl -X POST http://127.0.0.1:8000/sources/text \
  -H "Content-Type: application/json" \
  -d '{"title":"Update","text":"VF8 duoc bao hanh 6 nam."}'

curl http://127.0.0.1:8000/knowledge-quality
```

The citation-chat source debug panel includes a `Quality` tab that renders empty,
duplicate, and conflict states from `/sources/{document_id}/quality`.

## Evaluation Template

Use this as the short report for a 5-10 slide demo:

```markdown
# Knowledge Quality Evaluation

## Dataset
- Sources:
- Chunk count:
- Known duplicate pairs:
- Known conflict pairs:

## Detector Settings
- Method: deterministic_offline
- Near duplicate threshold:
- Fact attributes enabled: price, date, duration, distance_km

## Results
| Metric | Value | Notes |
| --- | --- | --- |
| Exact duplicate findings | | |
| Near duplicate findings | | |
| Conflict findings | | |
| False positives reviewed | | |
| Missed known conflicts | | |

## Review Notes
- Most useful finding:
- Most common false positive:
- Next improvement:
```

## Q&A Points

- Why offline first? Enterprise source review must work without API keys,
  outbound network access, or paid model calls.
- Why chunk metadata instead of a new table? It keeps v1 compatible with JSONL,
  S3, Postgres, source debug, and current retrieval code.
- Why not modify retrieval? Conflict detection is source quality review. Answer
  generation can consume the same chunks while reviewers inspect quality signals.
- What is the future LLM path? Add an optional verifier after deterministic
  candidate generation, using a cheaper model profile and only on ambiguous
  findings.
