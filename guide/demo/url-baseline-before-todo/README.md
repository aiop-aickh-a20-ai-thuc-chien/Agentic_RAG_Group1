# URL Baseline Before TODO Changes

This demo captures the current URL ingestion output before implementing the
static/dynamic section and PDF-policy-list TODO items in
`src/agentic_rag/ingestion/url/TODO.md`.

Use it to compare the current baseline with later changes.

## URLs

The default run checks:

- `https://vinfastauto.com/vn_vi`
- `https://vinfastauto.com/vn_vi/hop-dong-va-chinh-sach/chinh-sach`
- `https://shop.vinfastauto.com/vn_vi/dat-mua-xe-may-dien-vinfast`

## Run

From the repository root:

```powershell
uv run python guide/demo/url-baseline-before-todo/run_baseline.py
```

Optional:

```powershell
uv run python guide/demo/url-baseline-before-todo/run_baseline.py --no-browser
```

## Output

Default output path:

```text
guide/demo/url-baseline-before-todo/output/base_current/
```

The run writes:

- `summary.json`: machine-readable baseline summary.
- `summary.md`: human-readable comparison report.
- `url_XX_<slug>/result.json`: per-URL result snapshot.
- `url_XX_<slug>/artifacts/...`: current URL ingestion artifacts such as
  `source.html`, `cleaned.html`, `parsed.md`, `chunks.jsonl`, `quality.json`,
  and `manifest.json` when available.

## What To Compare Later

For the policy list URL, compare:

- whether PDF links are discoverable in `assets`;
- whether list-page context remains as URL chunks;
- whether PDF content is routed to PDF ingestion instead of HTML parsing.

For the JavaScript order page, compare:

- whether current baseline lacks `section_kind` / `section_origin`;
- whether later output separates static source-backed sections from dynamic
  interaction/state sections;
- whether dynamic facts have deterministic evidence metadata.
