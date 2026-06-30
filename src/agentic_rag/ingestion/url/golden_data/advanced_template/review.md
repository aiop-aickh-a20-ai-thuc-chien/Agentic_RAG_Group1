# Advanced URL Scorecard Template

Use this folder when the base evaluator is not enough and you want a ranked
quality score for URL ingestion.

The base evaluator in `agentic_rag.ingestion.url.evaluation` is still the first
gate. It answers:

```text
Did this URL ingestion output pass the required golden checks?
```

The advanced scorecard answers:

```text
How good is the passed output, and where did it lose quality?
```

## Files

- `advanced_scorecard.json`: weighted scoring contract.

## Recommended Flow

1. Run `evaluate_sample()` from `src/agentic_rag/ingestion/url/evaluation`.
2. If the base result has failing `severity="error"` checks, mark the advanced
   result as failed.
3. If the base result passes, calculate the weighted dimensions from
   `advanced_scorecard.json`.
4. Store the score and dimension details in generated reports outside source,
   such as `guide/reports/` or `guide/demo/`.

## Scoring Meaning

- `85-100`: pass, good enough for URL ingestion regression checks.
- `70-84.99`: review, usable but needs human inspection.
- `<70`: fail, ingestion quality is too weak for this sample.

## When To Enrich A Sample

Add advanced overrides when a page needs stricter review:

- product/listing pages where entity boundaries matter,
- pages with repeated UI blocks,
- pages where optional snippets should become required,
- pages where metadata fidelity is critical,
- pages used as regression anchors for DOM-aware chunking.

Keep live URL scoring broad. For strict assertions, capture a static fixture and
use the normal `template/` folder shape.
