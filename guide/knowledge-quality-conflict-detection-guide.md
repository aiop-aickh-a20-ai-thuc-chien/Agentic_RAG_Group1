# Knowledge Quality Conflict Detection Guide

This guide explains the prototype conflict-detection path in
`src/agentic_rag/ingestion/knowledge_quality`.

Conflict detection answers a different question than duplicate detection:

```text
Duplicate detection: Are these chunks the same or too similar?
Conflict detection: Do these chunks make incompatible claims?
```

## Where It Lives

| Path | Purpose |
| --- | --- |
| `src/agentic_rag/ingestion/knowledge_quality/detectors.py` | Deterministic fact extraction and report assembly |
| `src/agentic_rag/ingestion/knowledge_quality/rules.py` | Metadata and semantic rule checks |
| `src/agentic_rag/ingestion/knowledge_quality/model_methods.py` | Optional LLM-backed contradiction verification |
| `src/agentic_rag/ingestion/knowledge_quality/registry.py` | Method selection and validation |
| `src/agentic_rag/ingestion/url/TODO.md` | URL-owned product-spec handoff and conflict-fixture TODOs |

## Boundary

Knowledge quality consumes `Chunk` objects and returns
`KnowledgeQualityReport` or annotated chunk metadata. It should not parse URLs,
parse PDFs, delete duplicates, or choose the final trusted value.

```text
URL/PDF ingestion
  -> Chunk text and metadata
  -> dedup_detect duplicate signals
  -> knowledge_quality conflict findings
  -> review or policy resolution
```

## URL Product Specs Handoff

URL ingestion now emits product and vehicle facts in `Chunk.metadata`, including:

- `product_specs`
- `product_model`
- `product_price`
- `driving_range`
- `battery_capacity`
- `charging_time`

Conflict detection should prefer these structured fields before regex scanning
the chunk text. This improves precision for pages where the visible prose is
clean but the same value appears in several formats.

Recommended mapping:

| URL metadata | Knowledge-quality attribute |
| --- | --- |
| `product_price`, `product_specs.price` | `price` |
| `driving_range`, `product_specs.driving_range` | `distance_km` |
| `battery_capacity` | `battery_capacity_kwh` |
| `charging_time` | `charging_time` |
| `product_specs.power` | `power_kw` |
| `product_specs.torque` | `torque_nm` |
| `product_specs.max_speed` | `max_speed_kmh` |
| `product_specs.warranty` | `warranty_duration` |

## What Counts As A Conflict

Useful first-pass conflict types:

- Numeric conflicts: different prices, range values, battery capacity, charging
  times, warranty durations, or service intervals for the same entity.
- Temporal conflicts: older and newer policies both appear active.
- Policy conflicts: one chunk says an action is required or supported while
  another says it is optional or unsupported.
- Entity-relation conflicts: a value is attached to the wrong model or product.
- Recommendation conflicts: one source recommends an action while another warns
  against it.

## What Should Not Be A Conflict

- Exact or near duplicates. Those belong to `dedup_detect`.
- Stale values that are explicitly superseded and can be ranked by date.
- Different trims, markets, currencies, or conditions when the chunks identify
  different entities.
- Missing values. Missing data should be a quality warning, not a contradiction.

## Quality-First Flow

For VinFast-style URL ingestion, quality-first conflict detection depends on
good upstream extraction:

1. URL ingestion renders product pages when needed.
2. URL chunks preserve entity names, section paths, hashes, and product specs.
3. Duplicate detection marks repeated chunks so conflict detection can skip or
   down-rank duplicate candidates.
4. Knowledge quality compares facts inside entity and attribute blocks.
5. Findings keep evidence spans, source URLs, normalized values, and suggested
   review actions.

## Verification

Start with deterministic tests:

```powershell
uv run pytest tests/test_ingestion_knowledge_quality.py tests/test_ingestion_knowledge_quality_v2.py -q
```

When URL product specs change, also run:

```powershell
uv run pytest src/agentic_rag/ingestion/url/tests/test_dom_entities_metadata.py src/agentic_rag/ingestion/url/tests/test_loader.py -q
```

Use live URL reports only after deterministic fixtures pass.

## Next Step

Use the URL-owned TODO in `src/agentic_rag/ingestion/url/TODO.md` to prepare
product-spec fixtures and handoff metadata. The conflict detector can then
consume those fields from `knowledge_quality` without this task editing the
prototype package.
