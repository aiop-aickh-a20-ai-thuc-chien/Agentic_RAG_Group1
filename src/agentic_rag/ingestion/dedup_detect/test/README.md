# Dedup Similarity Threshold Test

This folder is a manual experiment harness for Layer 3 embedding similarity.
It is not a CI test because it can download/load a sentence-transformers model.

Default model:

```text
sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
```

The script resolves the model in this order:

1. `DEDUP_DETECT_SENTENCE_TRANSFORMER_MODEL`
2. `EMBEDDING_MODEL`
3. `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`

## Install Local Model Dependencies

From the repo root:

```powershell
uv sync --extra local-models
```

The first run may download the model from Hugging Face unless it is already
cached locally.

## Run Threshold Sweep

```powershell
uv run python src/agentic_rag/ingestion/dedup_detect/test/threshold_sweep.py
```

This writes:

```text
src/agentic_rag/ingestion/dedup_detect/test/output/threshold_sweep_report.json
src/agentic_rag/ingestion/dedup_detect/test/output/threshold_sweep_report.md
```

If the first run takes too long, the model is probably downloading or warming up.
After downloading once, rerun with local cache only:

```powershell
uv run python src/agentic_rag/ingestion/dedup_detect/test/threshold_sweep.py --local-files-only
```

## Custom Model

With `.env`:

```powershell
DEDUP_DETECT_SENTENCE_TRANSFORMER_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
```

With CLI override:

```powershell
uv run python src/agentic_rag/ingestion/dedup_detect/test/threshold_sweep.py `
  --model sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
```

CPU tuning:

```powershell
uv run python src/agentic_rag/ingestion/dedup_detect/test/threshold_sweep.py `
  --device cpu `
  --batch-size 8
```

## Custom Dataset

The default dataset is `sample_pairs.jsonl`.

Each line:

```json
{"pair_id":"near-01","left":"...","right":"...","label":"near_duplicate"}
```

Allowed labels:

- `duplicate`
- `near_duplicate`
- `different`

For threshold optimization, `duplicate` and `near_duplicate` count as positive
pairs. `different` counts as negative.

## How To Choose Threshold

The script sweeps cosine thresholds and recommends the threshold with the best
F1 score. If two thresholds tie, it chooses the higher threshold to reduce false
positives.

Baseline run on 2026-06-10 with
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` and
`sample_pairs.jsonl`:

- Recommended threshold: `0.88`
- F1: `1.0`
- Precision: `1.0`
- Recall: `1.0`
- Lowest positive sample score: `0.881452`
- Highest negative sample score: `0.305683`

Suggested interpretation:

| Threshold | Meaning |
| ---: | --- |
| `>= 0.95` | Strict duplicate/near-duplicate candidate. |
| `0.90-0.94` | Good review candidate range for noisy PDF/URL chunks. |
| `< 0.90` | Broad semantic similarity, more false positives likely. |

Do not silently delete chunks from embedding similarity alone. Use it as review
metadata until the threshold is validated on real project documents.
