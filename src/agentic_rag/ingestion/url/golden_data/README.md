# URL Golden Data

Use this folder for curated URL-ingestion samples that make parser and chunking
quality easy to review.

Golden data should be small, deterministic, and safe to commit. Prefer static
HTML fixtures over live URLs when the goal is a repeatable test. Use live URLs
only as source notes or manual review references.

## VinFast Evaluation Set

The active VinFast URL evaluation inputs are:

- `Link_data.txt`: one URL per line. This is the source URL list used for crawl
  and ingestion evaluation.
- `vinfast_url_golden_samples.json`: expectations for the URLs in
  `Link_data.txt`, following the same broad shape as
  `template/expected_chunks.json`.
- `ground_truth_manifest.json`: maps strict JSON ground truth files to their
  target URLs and judge prompts.
- `vinfast_vf9_rolling_cost_ground_truth.json`: state-only ground truth for the
  dynamic deposit configurator URL with `modelId=Products-Car-VF3`.
- `trang_vinfast_vn.json`: homepage ground truth for `https://vinfastauto.com/vn_vi`,
  including hidden or easy-to-miss UI data.
- `promt_judge_VF9_rolling_cost.txt` and `judge_prompt_trang_vinfast_vn.txt`:
  child judge prompts for comparing model extraction output and generated
  Markdown against those JSON ground truth files.

The child judge prompts expect three filled blocks:

- `<GROUND_TRUTH>`: the curated JSON ground truth.
- `<MODEL_OUTPUT>`: JSON extracted by the URL ingestion pipeline.
- `<MARKDOWN_OUTPUT>`: structured Markdown constructed from JSON/state/hidden
  data for downstream chunking and RAG.

Use `Link_data.txt` as the run list and `vinfast_url_golden_samples.json` as the
assertion guide. The golden JSON intentionally uses broad checks first:

- required metadata keys,
- required text snippets,
- optional diagnostic snippets,
- product/spec metadata checks for model, price, range, battery, and charging
  fields when the sample needs structured product validation,
- forbidden boilerplate snippets,
- normalization checks,
- disabled entity-boundary checks that can be enabled after stable fixture
  capture.

Do not treat live URL content as fully deterministic. When a live page becomes
important enough to protect with strict assertions, capture a static fixture
under a scenario folder and tighten expectations there.

## Suggested Sample Layout

Copy `template/` into a new folder named after the scenario:

```text
golden_data/
  Link_data.txt
  vinfast_url_golden_samples.json
  template/
  advanced_template/
  vehicle_cards/
  faq_section/
  comparison_table/
```

Each sample should include:

- `source.html`: static HTML input.
- `expected_chunks.json`: expected chunk text and metadata checks.
- `review.md`: human-readable notes about what the sample is testing.

Use `advanced_template/advanced_scorecard.json` when you need weighted scoring
on top of the base pass/fail evaluator. Advanced scoring should not replace the
base evaluator; it should start from the base result and then explain quality by
dimension.

## What To Capture

Good samples should cover one behavior clearly:

- product or vehicle cards must stay separate,
- FAQ question/answer pairs must stay together,
- comparison tables should preserve headers and row identity,
- policy sections should preserve section paths,
- noisy navigation/footer/cookie text should not dominate chunks,
- dynamic-page content should have a static equivalent for deterministic tests.

## Test Guidance

Tests can load `source.html`, call `load_html_with_artifacts()`, and compare the
result with `expected_chunks.json`.

Evaluation tools can load `Link_data.txt`, run each URL through
`load_url_with_artifacts()`, and compare each output with matching entries in
`vinfast_url_golden_samples.json`.

Keep assertions focused:

- chunk count,
- required text snippets,
- product/spec metadata checks,
- forbidden boilerplate snippets,
- required metadata keys,
- entity or section boundaries.

Avoid asserting the full exact chunk text unless the sample is intentionally
small. Exact full-text assertions become brittle when cleanup rules improve.

## Advanced Scoring

The advanced template is for score reports, not raw ingestion snapshots.

Recommended flow:

1. Run the base evaluator from `agentic_rag.ingestion.url.evaluation`.
2. Fail the sample immediately if any base `severity="error"` check fails.
3. If the base result passes, apply weighted dimensions from
   `advanced_template/advanced_scorecard.json`.
4. Write generated score reports outside source, such as `guide/reports/`.

Use advanced scoring to compare parser/chunker changes across runs while keeping
the committed golden data stable.
