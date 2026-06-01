# URL Benchmarking Summary Report

## Scope

This report checks the current URL/HTML benchmarking helpers in:

- `src/agentic_rag/ingestion/url/benchmarking/custom_benchmark.py`
- `src/agentic_rag/ingestion/url/benchmarking/cli.py`
- `src/agentic_rag/ingestion/url/tests/benchmarking`

## Current Status

Benchmarking is OK as a Sprint 1 deterministic baseline.

Verification:

```text
uv run pytest src/agentic_rag/ingestion/url/tests/benchmarking -q
5 passed in 0.40s
```

Current benchmark CLI output:

```json
{
  "parser": "builtin-html-parser",
  "average_score": 1.0,
  "results": [
    {
      "case_id": "article_with_navigation_noise",
      "parser": "builtin-html-parser",
      "extracted_chars": 67,
      "matched_terms": ["Admissions Guide", "transcripts", "interview"],
      "missing_terms": [],
      "detected_sections": ["Admissions Guide"],
      "score": 1.0
    },
    {
      "case_id": "docs_page_with_code_noise",
      "parser": "builtin-html-parser",
      "extracted_chars": 122,
      "matched_terms": ["Installation", "uv sync", "Quality Gate", "pytest"],
      "missing_terms": [],
      "detected_sections": ["Installation", "Quality Gate"],
      "score": 1.0
    }
  ]
}
```

## What Benchmarking Uses

### Parser Under Test

The benchmark currently tests only one parser:

- `builtin-html-parser`
- implemented with Python stdlib `html.parser.HTMLParser`
- removes common boilerplate tags:
  - `script`
  - `style`
  - `nav`
  - `footer`
  - `header`
  - `aside`
- detects section headings:
  - `h1`
  - `h2`
  - `h3`

### Benchmark Cases

There are two small local HTML fixtures:

1. `article_with_navigation_noise`
   - checks that nav/footer text is removed
   - checks that article terms remain
   - checks that an `h1` section is detected

2. `docs_page_with_code_noise`
   - checks that header/script noise is removed
   - checks that docs content remains
   - checks that `h1` and `h2` sections are detected

### Scoring

Each case calculates:

- `matched_terms`
- `missing_terms`
- `detected_sections`
- `extracted_chars`
- `score`

The score is weighted:

- 80 percent expected term match
- 20 percent expected section match

Formula:

```text
score = (term_score * 0.8) + (section_score * 0.2)
```

## Is custom_benchmark.py From An Online Benchmark?

No.

`custom_benchmark.py` is not copied from an official online benchmark such as OmniDocBench, MTEB, BEIR, RAGAS, or a public URL extraction benchmark.

It is a project-specific custom benchmark designed for this URL ingestion task. The algorithm is a lightweight heuristic benchmark:

1. define local HTML fixtures
2. define expected key terms
3. define expected section headings
4. run the parser
5. compare extracted text and detected sections
6. compute a weighted score

The idea is inspired by common information extraction evaluation patterns, especially:

- expected-term recall
- section/header detection
- boilerplate removal checks
- deterministic local fixtures for regression testing

It should be treated as a smoke/regression benchmark, not as a formal academic benchmark.

## Does It Need To Be Updated?

Not required before merging the baseline URL ingestion work.

Recommended updates for the next iteration:

1. Add Vietnamese HTML fixtures.
2. Add cases with malformed HTML.
3. Add cases with repeated navigation/footer text.
4. Add cases with nested headings and product/spec tables.
5. Add parser candidates:
   - stdlib baseline
   - `trafilatura`
   - BeautifulSoup/readability fallback
6. Save benchmark outputs to a stable artifact folder when running real comparisons.
7. Add quality fields for:
   - encoding correctness
   - boilerplate leakage
   - section quality
   - Markdown suitability
   - runtime

## Decision

Keep the current benchmarking helper as the lightweight baseline. It is useful for local regression testing and for comparing parser behavior later. The next meaningful update should happen when `trafilatura` or another parser adapter is added.
