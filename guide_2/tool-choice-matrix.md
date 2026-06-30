# Tool Choice Matrix

This matrix is for choosing parsing and metadata tools before implementation.

## HTML Parsing

| Option | Best use | Advantage | Weakness | Recommendation |
| --- | --- | --- | --- | --- |
| Python `html.parser` | Deterministic local parsing | Built-in, no dependency, easy tests | Limited selector support, weaker malformed HTML handling | Keep for simple static parsing |
| `selectolax` | Fast DOM extraction | Very fast, CSS selectors, practical for web pages | New dependency | Good future replacement for repeated HTML walkers |
| `lxml` | Robust DOM/XPath | Mature, powerful | Heavier dependency, sometimes more complex install | Use only if XPath/HTML recovery is needed |
| Playwright DOM JS | Rendered pages | Sees JS-rendered DOM and computed page state | Slow, browser dependency | Use for dynamic pages and verification |

## Markdown Extraction

| Option | Best use | Advantage | Weakness | Recommendation |
| --- | --- | --- | --- | --- |
| Current DOM-to-Markdown | Project-specific pages | Deterministic, controllable | Duplicates parsing rules | Keep, but share skip rules |
| `trafilatura` | Article-like pages | Good content extraction | Can drop product tables/UI facts | Keep as fallback/alternative |
| Playwright walker | Dynamic product pages | Captures rendered DOM | Slower, JS heuristic maintenance | Keep for render-required pages |

## JSON Metadata

| Option | Best use | Advantage | Weakness | Recommendation |
| --- | --- | --- | --- | --- |
| Pydantic models | Shared metadata contracts | Validation, typed boundaries | Requires explicit migrations | Use as source of truth |
| Plain dicts | Internal transient payloads | Flexible | Drifts easily | Use only at local helper boundaries |
| JSONL artifacts | Debug and offline eval | Easy diff/replay | Not indexed by itself | Keep for artifacts |

## CSS and Visual Detection

| Option | Best use | Advantage | Weakness | Recommendation |
| --- | --- | --- | --- | --- |
| Regex in `visual_semantics.py` | Inline simple facts | Fast, no dependency | Not full CSS, cannot compute cascade | Keep for old price/hidden basics |
| `tinycss2` | CSS token parsing | Correct CSS parsing | Does not compute layout/cascade alone | Add if selector parsing expands |
| Playwright computed style | User-visible truth | Captures rendered CSS state | Slow, browser-only | Use for high-value dynamic pages |

## Retrieval Metadata Usage

| Signal | Advantage | Weakness | Recommendation |
| --- | --- | --- | --- |
| `entities_canonical` hard filter | High precision for model/location queries | Needs Qdrant and backfill; can over-filter | Use with zero-result fallback |
| `document_type` boost | Helps query-type match | Depends on correct classification | Keep, trace factors |
| `keywords` BM25 augmentation | Improves sparse recall | Can add noisy terms | Keep behind env flag |
| `questions` index | Good for FAQ-style semantic matching | Extra index, not fully wired to agent path | Experiment after trace is added |
| `quality_score` | Can demote weak chunks | LLM self-score can be biased | Evaluate before ranking use |
| `retrieval_weight` | Rule-based local signal | Heuristic, may overfit VinFast pages | Use as small boost only |

