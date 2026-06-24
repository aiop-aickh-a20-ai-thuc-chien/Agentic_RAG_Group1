# DOM-Aware Chunking Strategy for RAG Ingestion

## Purpose

This document defines a DOM-aware chunking strategy for ingestion pipelines handling modern websites containing product cards, listings, tables, FAQs, and interactive UI components.

The goal is to preserve semantic entity boundaries before chunking, enabling higher-quality retrieval, duplicate detection, conflict detection, metadata enrichment, and future knowledge graph construction.

---

# Problem Statement

Traditional ingestion pipelines often follow:

```text
HTML
→ Markdown
→ Text Chunking
→ Embedding
```

While effective for articles and documentation pages, this approach fails for structured websites.

Example:

```text
VF 8 All New
D-SUV
5 seats
480-500 km
849.150.000 VNĐ

VF 7
C-SUV
5 seats
431-496 km
799.000.000 VNĐ
```

A traditional chunker may combine multiple vehicles into a single chunk.

Consequences:

* Entity boundary loss
* Incorrect retrieval
* Duplicate detection degradation
* Conflict detection degradation
* Attribute contamination between entities

Example failure:

```text
Question:
What is the price of VF 8?

Retrieved chunk:
VF 8
VF 7
VF 6

LLM returns VF 7 price instead of VF 8 price.
```

---

# Design Principle

Chunk by semantic entity rather than token count.

Preferred pipeline:

```text
HTML
→ DOM Analysis
→ Semantic Block Detection
→ Entity Extraction
→ Chunk Generation
→ Embedding
```

Avoid:

```text
HTML
→ Markdown
→ Token Splitter
→ Embedding
```

Entity boundaries are more important than token boundaries.

---

# Retrieval And Generation Fit

The current retrieval and generation modules make chunk quality very direct:

* BM25 search tokenizes only `Chunk.text`.
* Dense search embeds only `Chunk.text`.
* Qdrant keeps selected payload metadata such as `document_id`,
  `source_type`, `source`, `url`, `page`, `section`, and nested `metadata`.
* Evidence context exposes `source`, `page`, `section` or `section_path`,
  inferred metadata, `chunk_id`, score, and normalized chunk text.
* Generation answers only from evidence and validates citations against
  retrieved chunk metadata.

Therefore every URL chunk should be both readable and citable.

Good chunk text:

```text
VF 8 All New is a D-SUV electric vehicle with 5 seats, a range of
480-500 km, and a listed price of 849.150.000 VND.
```

Good citation metadata:

```json
{
  "source": "https://example.com/vf8",
  "url": "https://example.com/vf8",
  "section": "Product specs",
  "chunk_id": "url:vf8:specs",
  "entity_name": "VF 8 All New"
}
```

Avoid isolated values:

```text
849.150.000 VND
```

Prefer self-contained facts:

```text
VF 8 All New listed price: 849.150.000 VND.
```

The text carries retrieval signal. Metadata makes the same evidence filterable,
traceable, and valid for citation checks.

---

# Chunk Classification

## Product Card

Examples:

* Vehicles
* Accessories
* Phones
* Insurance Packages
* Appliances

Each product card becomes one chunk.

Example:

```json
{
  "chunk_type": "product_card",
  "entity_name": "VF 8 All New"
}
```

---

## Vehicle Card

Examples:

```text
VF 3
VF 5
VF 6
VF 7
VF 8
VF 9
```

Each vehicle must become an independent chunk.

Never merge multiple vehicle models into a single chunk.

---

## Course Card

Examples:

```text
Artificial Intelligence
Business Administration
Computer Science
```

Each course becomes one chunk.

---

## Job Card

Examples:

```text
AI Engineer
Backend Engineer
Product Manager
```

Each job posting becomes one chunk.

---

## FAQ Item

Examples:

```text
Question
Answer
```

Each FAQ pair becomes one chunk.

Do not merge all FAQs into a single chunk.

---

## Policy Section

Examples:

```text
Warranty Policy
Battery Policy
Scholarship Policy
Admissions Requirements
```

Each policy section becomes one chunk.

---

## Comparison Tables

Store both:

### Table Chunk

```json
{
  "chunk_type": "comparison_table"
}
```

### Row Chunk

```json
{
  "chunk_type": "comparison_row"
}
```

This supports both overview retrieval and attribute-level retrieval.

Each row chunk must repeat the table context, row entity, column label, and
value. Do not split headers away from values.

Example row text:

```text
Comparison table: VF 8 Eco has driving range 471 km under the listed standard.
```

Example metadata:

```json
{
  "chunk_type": "comparison_row",
  "entity_name": "VF 8 Eco",
  "attribute_group": "driving_range",
  "section": "Technical specifications"
}
```

---

# DOM-Aware Block Detection

The ingestion system should identify repeated semantic blocks before chunking.

Example:

```html
<div class="vehicle-card">
    ...
</div>

<div class="vehicle-card">
    ...
</div>

<div class="vehicle-card">
    ...
</div>
```

Expected result:

```text
vehicle-card #1
vehicle-card #2
vehicle-card #3
```

Three independent chunks.

---

# Repeated Subtree Detection

The system should identify repeated DOM structures.

Example:

```html
<div class="product-card">
    ...
</div>
```

Repeated twenty times.

Inference:

```text
This is a product listing section.
```

Each repeated subtree becomes a candidate entity.

---

# Entity Extraction

Convert each DOM block into a structured representation.

Input:

```text
VF 8 All New
D-SUV
5 seats
480-500 km
849.150.000 VNĐ
```

Output:

```json
{
  "entity_type": "vehicle",
  "entity_name": "VF 8 All New",
  "vehicle_type": "D-SUV",
  "seats": "5",
  "range": "480-500 km",
  "price": "849.150.000 VNĐ"
}
```

---

# Dual Representation Strategy

Store both structured and textual representations.

## Structured Representation

```json
{
  "name": "VF 8 All New",
  "price": "849.150.000 VNĐ",
  "range": "480-500 km"
}
```

## Retrieval Text

```text
VF 8 All New is a D-SUV electric vehicle with 5 seats and a range of 480-500 km. Price starts at 849.150.000 VNĐ.
```

Benefits:

### Structured Data

Supports:

* Duplicate detection
* Conflict detection
* Metadata filtering
* Analytics
* Knowledge graph generation

### Retrieval Text

Supports:

* Embedding retrieval
* BM25 retrieval
* Hybrid retrieval
* Grounded generation fallback when no LLM is configured

Retrieval text should include:

* entity name or page subject
* attribute label
* exact value with unit or currency
* source section context
* important aliases, such as `VF8` and `VF 8`, when the page uses one form but
  users may query another

---

# Chunk Schema

```json
{
  "chunk_id": "",
  "chunk_type": "",
  "entity_type": "",
  "entity_name": "",
  "source_url": "",
  "section_path": [],
  "embedding_text": "",
  "structured_data": {},
  "metadata": {}
}
```

---

# Metadata Requirements

Each chunk should include:

```json
{
  "source_url": "",
  "page_title": "",
  "section_path": [],
  "dom_path": "",
  "chunk_type": "",
  "entity_type": "",
  "entity_name": "",
  "crawl_timestamp": "",
  "last_modified": ""
}
```

Recommended additions:

```json
{
  "language": "",
  "canonical_url": "",
  "content_hash": "",
  "dom_hash": "",
  "entity_hash": ""
}
```

Citation-critical metadata:

```json
{
  "source": "",
  "url": "",
  "page": null,
  "section": "",
  "section_path": [],
  "document_id": "",
  "source_type": ""
}
```

Retrieval-critical metadata:

```json
{
  "document_type": "",
  "product_model": "",
  "entity_name": "",
  "entity_type": "",
  "attribute_group": "",
  "retrieval_weight": 1.0,
  "is_noise": false
}
```

Dynamic-page provenance metadata:

```json
{
  "section_kind": "static | dynamic | generated",
  "section_origin": "source_data_static | source_data_rendered | dynamic_interaction | dynamic_state_payload | generated_artifact",
  "evidence_source": "raw_html | rendered_dom | dom_after_interaction | json_state | network_payload | data_attribute | ingestion_adapter",
  "interaction_step": null
}
```

Generated organization text should not be treated as source evidence unless
child chunks point to source-backed DOM, JSON, network, or data-attribute
evidence.

---

# Recommended Chunk Types For URL Ingestion

Use several complementary chunk types instead of one token splitter:

* `page_overview`: title, purpose, canonical source, and major sections.
* `section`: one heading or policy/article section with coherent body text.
* `entity_card`: one product, vehicle, FAQ item, policy link, or repeated card.
* `table_overview`: table title, entities compared, and attribute groups.
* `table_row`: one entity row with repeated headers and exact values.
* `spec_fact`: one answerable fact such as price, range, charging time, battery
  capacity, warranty, or availability.
* `dynamic_state`: facts captured after a safe interaction.
* `asset_reference`: PDF, image, or snapshot reference that should be routed or
  reviewed separately.

For product pages, prefer this shape:

```text
1. Page overview chunk
2. One chunk per visible product/model/card
3. One chunk per important spec group
4. One chunk per exact spec fact when the fact is frequently queried
5. Separate dynamic chunks for variant/color/price/image states
```

This gives retrieval enough broad context for overview questions and enough
small exact chunks for price/spec queries.

---

# Duplicate Detection Benefits

Entity chunks improve duplicate detection.

Instead of comparing:

```text
Large mixed chunk
vs
Large mixed chunk
```

Compare:

```text
Vehicle
vs
Vehicle
```

Higher precision and lower false positives.

---

# Conflict Detection Benefits

Example:

```text
VF 8 price = 849M

VF 8 price = 899M
```

Because both chunks share:

```json
{
  "entity_name": "VF 8 All New"
}
```

the system can detect a conflict.

Potential conflict attributes:

* Price
* Date
* Warranty
* Mileage
* Capacity
* Scholarship amount
* Admissions deadline

---

# Future Knowledge Graph Compatibility

Entity-based chunks can later be converted into graph relationships.

Example:

```text
VF 8
 ├── Price
 ├── Range
 ├── Seats
 └── Vehicle Type
```

without reprocessing the original HTML.

---

# Recommended Rule

Always prefer:

```text
DOM Block
→ Entity
→ Chunk
```

Over:

```text
DOM Block
→ Markdown
→ Token Splitter
→ Chunk
```

Entity boundaries must be preserved before chunk generation.
