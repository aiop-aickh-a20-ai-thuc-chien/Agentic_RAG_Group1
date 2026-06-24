# URL Dedup Detection Review

This guide-only demo connects URL ingestion, URL chunking, and
`ingestion.dedup_detect` without changing any code under `src/agentic_rag`.

Use it when you want to send multiple URLs, inspect the chunks created from
those URLs, and see which chunks look duplicated or near-duplicated.

## What It Does

For each URL:

1. Calls `load_url_with_artifacts()`.
2. Saves URL ingestion artifacts under `output/artifacts/`.
3. Collects all chunks across all URLs.
4. Runs duplicate detection over those chunks.
5. Writes:
   - `output/metadata_contract.json`
   - `output/chunks_with_dedup.jsonl`
   - `output/dedup_report.json`
   - `output/dedup_review.md`

By default, it runs:

- Layer 1: exact normalized text SHA-256.
- Layer 2: SimHash near-duplicate detection.

Layer 3 embedding similarity is optional because it may require model downloads
or API credentials.

## Run With URLs

```powershell
uv run python guide/demo/dedup-detect-url-review/run_url_dedup_review.py `
  https://vinfastauto.com/vn_vi `
  https://vinfastauto.com/vn_vi/ve-chung-toi `
  https://shop.vinfastauto.com/vn_vi/dat-coc-xe-dien-vf3.html
```

## Run With A URL File

Create a plain text file with one URL per line:

```text
https://vinfastauto.com/vn_vi
https://vinfastauto.com/vn_vi/ve-chung-toi
https://shop.vinfastauto.com/vn_vi/dat-coc-xe-dien-vf3.html
```

Then run:

```powershell
uv run python guide/demo/dedup-detect-url-review/run_url_dedup_review.py `
  --urls-file guide/demo/dedup-detect-url-review/urls.example.txt
```

## Optional Embedding Layer

Layer 3 uses the same embedding runtime as the project. Configure `.env` with
the shared embedding variables:

```env
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
EMBEDDING_API_BASE=
EMBEDDING_API_KEY=
EMBEDDING_DIMENSIONS=
EMBEDDING_TIMEOUT_SECONDS=60
```

If you want the demo to use an API key, `OPENAI_API_KEY` alone is not enough.
The embedding resolver reads `EMBEDDING_API_KEY`, not `OPENAI_API_KEY`.

Example OpenAI embedding setup:

```env
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_API_BASE=
EMBEDDING_API_KEY=your_openai_api_key
EMBEDDING_DIMENSIONS=
EMBEDDING_TIMEOUT_SECONDS=60
```

If you already have `OPENAI_API_KEY` in `.env`, copy that value into
`EMBEDDING_API_KEY` or set `EMBEDDING_API_KEY` to the same secret in your local
environment. Dedup detection will then use that shared embedding client.

Then run:

```powershell
uv run python guide/demo/dedup-detect-url-review/run_url_dedup_review.py `
  --enable-embedding `
  --embedding-threshold 0.92 `
  --urls-file guide/demo/dedup-detect-url-review/urls.example.txt
```

## Useful Options

```powershell
uv run python guide/demo/dedup-detect-url-review/run_url_dedup_review.py --help
```

Important flags:

- `--no-browser`: skip Playwright/browser extraction and use the static URL path.
- `--simhash-threshold`: tune Layer 2 sensitivity.
- `--enable-embedding`: enable Layer 3 semantic similarity.
- `--embedding-threshold`: tune Layer 3 cosine similarity.
- `--output-dir`: write outputs somewhere else.

## Reading The Output

Start with `output/dedup_review.md`.

The report shows:

- metadata contract readiness (`source_type` is required, `document_type` is optional).
- URL ingestion success/failure.
- Chunk counts per URL.
- duplicate count per layer.
- match pairs with scores and short text previews.

Use `output/metadata_contract.json` when you need a machine-readable check of
which chunks are missing required shared metadata before dedup review.

Then inspect `output/chunks_with_dedup.jsonl` for the full chunk metadata.
Chunks with duplicate signals get `metadata.deduplication`.

If the JSONL file is too hard to read, render it as Markdown and HTML:

```powershell
uv run python guide/demo/dedup-detect-url-review/view_chunks.py
```

This writes:

- `output/chunks_readable.md`
- `output/chunks_readable.html`

## Threshold Confusion Matrix

Use `golden_samples.json` to label expected duplicate and non-duplicate chunk
pairs. The starter file was created from `urls.example.txt` output and should be
edited after manual review.

Run Layer 1 + Layer 2 threshold evaluation:

```powershell
uv run python guide/demo/dedup-detect-url-review/evaluate_thresholds.py
```

Run all three layers, including embedding similarity:

```powershell
uv run python guide/demo/dedup-detect-url-review/evaluate_thresholds.py `
  --enable-embedding `
  --layer3-thresholds 0.86 0.88 0.90 0.92 0.94 0.96 0.98
```

This writes:

- `output/threshold_confusion_report.md`
- `output/threshold_confusion_report.json`

The report includes the best threshold by F1 and the pair IDs for FP and FN
errors.

## OpenAI Judgement For Threshold Choices

After generating `output/threshold_confusion_report.md`, use the configured
project LLM to judge which threshold is best, optimized, compromised, and worst:

```powershell
uv run python guide/demo/dedup-detect-url-review/judge_threshold_report.py
```

This uses the `evaluation` LLM role. If `EVALUATION_LLM_*` is blank, the project
falls back to the shared `LLM_PROVIDER`, `LLM_MODEL`, and `LLM_API_KEY` settings.

It writes:

- `output/threshold_llm_judgement.md`
- `output/threshold_llm_judgement.json`

The demo is intentionally diagnostic. It does not merge, delete, or resolve
duplicates.
