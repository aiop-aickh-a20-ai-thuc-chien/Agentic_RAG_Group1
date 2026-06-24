# URL Artifact Review Demo

This demo checks **one URL only**. It does not discover child pages and it does
not crawl links from the page. The goal is to inspect what the current URL
ingestion pipeline actually extracted from a URL.

It runs `src/agentic_rag/ingestion/url/load_url_with_artifacts` and shows:

- `source.html`: raw/static or rendered HTML selected by ingestion.
- `cleaned.html`: semantic HTML rebuilt from final cleaned Markdown so reviewers
  can inspect the exact content shape used to create chunks.
- `parsed_sections.txt`: section text parsed from the HTML.
- `extracted.md`: extractor Markdown before final cleanup.
- `parsed.md`: cleaned Markdown used for chunking.
- `quality.json`: URL quality and quality-gate metadata.
- `chunks.jsonl`: serialized `Chunk` contracts.
- `manifest.json`: parser, URLs, page metadata, assets, and artifact paths.
- Dedup review: exact and SimHash duplicate detection over generated chunks,
  including per-chunk `dedupe_text`, `dedupe_hash`, and duplicate-candidate
  metadata when repeated content is found.

It can also run `src/agentic_rag/ingestion/url/interactions` for booking or
configurator pages. The demo shows the interaction artifacts separately and
also appends promoted `dynamic_state` chunks into the main chunk list:

- normal chunks show the relevant semantic content used by RAG;
- promoted dynamic chunks show interaction-dependent state changes in the same
  review list as normal chunks;
- the dynamic viewer groups safe controls and snapshots into left controls,
  center visual/product preview, and right summary panels;
- interaction debug chunks show one raw record per captured JavaScript/button
  state and are filtered from normal RAG;
- promoted dynamic chunks show only validated changed facts that are usable by
  RAG;
- raw interaction chunks are marked `interaction_debug`,
  `retrieval_visibility=debug_only`, and `metadata_prefilter_exclude=true`;
- promoted chunks are marked `dynamic_state`, `retrieval_visibility=normal`,
  `metadata_prefilter_exclude=false`, and `trusted_for_retrieval=true`.

Run the browser demo from the repository root:

```bash
node guide/demo/url-crawl-review/server.js
```

Then open:

```text
http://127.0.0.1:8782
```

The form defaults to:

```text
https://vinfastauto.com/vn_vi/ve-chung-toi
```

Use **Static fetch only** when you want to see what the non-browser path produces
without Playwright/rendered recovery.

Keep **Capture dynamic interactions when needed** enabled for pages such as:

```text
https://shop.vinfastauto.com/vn_vi/dat-coc-o-to-dien-vinfast.html?modelId=Products-Car-VF9
```

The dynamic panel will show whether the page was detected as interactive, how
many states/controls were captured, which panels changed after safe clicks, the
debug-only chunks created for each interaction state, and any promoted semantic
chunks created from validated changed facts.

CLI usage:

```bash
uv run python guide/demo/url-crawl-review/run_review.py https://vinfastauto.com/vn_vi/ve-chung-toi
```

CLI usage with dynamic interaction capture:

```bash
uv run python guide/demo/url-crawl-review/run_review.py \
  "https://shop.vinfastauto.com/vn_vi/dat-coc-o-to-dien-vinfast.html?modelId=Products-Car-VF9" \
  --include-interactions
```

Static-only CLI usage:

```bash
uv run python guide/demo/url-crawl-review/run_review.py https://vinfastauto.com/vn_vi/ve-chung-toi --no-browser
```

Outputs are written under:

```text
guide/demo/url-crawl-review/output/
```

The browser API writes:

```text
guide/demo/url-crawl-review/output/artifact_review_payload.json
guide/demo/url-crawl-review/output/artifact_review.md
```

The payload includes a `deduplication` object shaped like:

```json
{
  "summary": {
    "document_count": 3,
    "exact_match_count": 1,
    "simhash_match_count": 0,
    "duplicate_candidate_count": 1,
    "layers_enabled": ["exact_sha256", "simhash"]
  },
  "matches": [
    {
      "layer": "exact_sha256",
      "document_id": "url_source_main_c001",
      "duplicate_document_id": "url_source_main_c002"
    }
  ],
  "duplicate_chunks": [
    {
      "chunk_id": "url_source_main_c002",
      "deduplication": {
        "status": "duplicate_candidate",
        "primary_layer": "exact_sha256",
        "canonical_chunk_id": "url_source_main_c001"
      }
    }
  ]
}
```

Score the artifact payload with deterministic checks:

```bash
uv run python guide/demo/url-crawl-review/evaluate_review.py
```

Verify Markdown against saved static and dynamic HTML artifacts:

```bash
uv run python guide/demo/url-crawl-review/verify_static_dynamic_artifacts.py \
  --markdown guide/demo/url-crawl-review/output/artifacts/artifacts/<source>/<run>/parsed.md \
  --html static=guide/demo/url-crawl-review/output/artifacts/artifacts/<source>/<run>/source.html \
  --html dynamic=guide/reports/url_ingestion_verification_subset_final/render_cache/<id>/rendered.html \
  --output guide/demo/url-crawl-review/output/static_dynamic_verification.md
```

This verifier is offline. It parses each HTML artifact into DOM sections with
CSS-like selectors, maps Markdown sections back to the best HTML evidence, and
reports values that appear, disappear, or move between static and dynamic HTML.
Use it to check JavaScript-updated sections such as price, model, range, color,
image, and option blocks before deciding whether a rule-based extractor or LLM
fallback should own the section.

Health check:

```text
http://127.0.0.1:8782/api/health
```

If `uv` is not on the PATH visible to Node, set it explicitly before starting:

```powershell
$env:UV="C:\Users\Admin\.local\bin\uv.exe"
node guide/demo/url-crawl-review/server.js
```

The Python fallback server uses the same single-URL payload:

```bash
uv run python guide/demo/url-crawl-review/server.py
```
