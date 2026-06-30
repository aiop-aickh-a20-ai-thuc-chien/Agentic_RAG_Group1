# VinFast chunking retrieval benchmark

## Scope

- 20 Vietnamese questions covering VF3 and VF9 pricing, range, charging,
  drivetrain, warranty, and promotions.
- Source facts were captured from the live VinFast VF3 and VF9 deposit pages on
  2026-06-22 and reduced to deterministic fixtures in
  `vinfast_chunking_benchmark.py`.
- The complete question-to-answer ground truth is stored in
  `vinfast_chunking_questions.json`.
- Retrieval uses the repository's pinned `rank-bm25` implementation and reports
  whether the expected answer occurs in the top three evidence chunks.

## Compared strategies

1. Flat baseline: canonical product JSON divided into fixed 180-character
   windows without semantic categories.
2. Semantic: `product_chunks()` groups range/charging, safety, dimensions,
   interior, pricing, and remaining specifications. The searchable text also
   includes the battery purchase/subscription label.

## Result

| Strategy | Chunks | Recall@3 |
| --- | ---: | ---: |
| Flat JSON windows | 7 | 0.450 |
| Semantic category chunks | 5 | 1.000 |

Semantic chunking improves recall@3 by **0.550 absolute** on this grounded
question set while producing fewer chunks. Run the benchmark with:

```powershell
uv run python benchmark/vinfast_chunking_benchmark.py
```

This benchmark is intentionally deterministic and does not call Neon or an LLM.
It measures lexical retrieval behavior; a separate dense/hybrid benchmark is
still appropriate when the production corpus is large enough.
