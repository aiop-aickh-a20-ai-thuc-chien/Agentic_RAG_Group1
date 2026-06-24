# RAG Ingestion Architecture Notes (for Codex)

## Goal

Build a high-quality ingestion pipeline for dynamic websites where:

- Playwright discovers content hidden behind interactions.
- API responses are captured and preserved.
- Structured data is extracted before chunking.
- LLM is used primarily for organization/enrichment rather than raw extraction.

---

## High-Level Pipeline

```text
URL
 ↓
Playwright
 ↓
DOM States
 + API Responses
 + Interaction States
 ↓
Evidence Store
 ↓
Entity Extraction
 ↓
Canonical Knowledge JSON
 ↓
Markdown Generation
 ↓
Chunking
 ↓
Embeddings
 ↓
Vector Database
```

---

## Playwright Responsibilities

Collect:

- Initial DOM
- Variant switches
- Tabs
- Accordions
- Dropdown selections
- Infinite scroll content
- Network/API responses

Examples:

```text
VF8 Eco
VF8 Plus
VF8 Lux
```

Each interaction may reveal new information.

Do not rely on a single final rendered page.

---

## API Responses Are First-Class Data

Priority:

```text
API Response
    >
Structured DOM
    >
Free Text
    >
OCR
```

Example:

```json
{
  "variant": "Plus",
  "price": 849150000,
  "range": 500,
  "battery_kwh": 87.7
}
```

API responses often contain:

- More fields
- Better typing
- Hidden attributes
- Canonical identifiers

Store them as evidence.

---

## Evidence Store

Preserve raw data.

Example:

```json
{
  "source": "api",
  "endpoint": "/vehicle/vf8",
  "payload": {...}
}
```

Never make the LLM output the only source of truth.

---

## Entity Extraction

Use multiple layers.

### Dictionary

Examples:

```json
{
  "VinFast": "brand",
  "VF 8": "vehicle_model"
}
```

### Regex

Examples:

Price:

```regex
\d{1,3}(?:\.\d{3})+\s*VNĐ
```

Range:

```regex
\d+\s*km
```

Battery:

```regex
\d+(\.\d+)?\s*kWh
```

### DOM-Aware Mapping

Convert:

```html
<div class="label">Range</div>
<div class="value">500 km</div>
```

Into:

```json
{
  "range_km": 500
}
```

---

## LLM Role

Preferred:

### Organizer

Input:

```json
{
  "variant": "Plus",
  "price": 849150000,
  "range": 500
}
```

Output:

```json
{
  "brand": "VinFast",
  "model": "VF 8",
  "variant": "Plus",
  "pricing": {
    "sale_price_vnd": 849150000
  },
  "specifications": {
    "range_km": 500
  }
}
```

### Enricher

Adds:

- Canonical names
- Categories
- Metadata
- Topic labels

### State Merger

Combines:

- DOM state A
- DOM state B
- API state C

Into one knowledge object.

---

## Avoid Excessive LLM Usage

Less efficient:

```text
HTML
 ↓
LLM
 ↓
Extraction
 ↓
LLM
 ↓
Metadata
 ↓
LLM
 ↓
Markdown
```

Preferred:

```text
Playwright
 ↓
Extraction Rules
 ↓
Canonical JSON
 ↓
Single LLM Organization Pass
 ↓
Markdown
```

---

## Canonical Knowledge JSON

This should become the primary artifact.

Example:

```json
{
  "brand": "VinFast",
  "model": "VF 8",
  "variant": "Plus",
  "price_vnd": 849150000,
  "range_km": 500,
  "battery_kwh": 87.7,
  "seats": 5
}
```

Everything else can be generated from this.

---

## Markdown Generation

Generate semantic markdown.

Example:

```md
# VinFast VF 8 Plus

## Specifications

| Field | Value |
|---------|---------|
| Range | 500 km |
| Battery | 87.7 kWh |
| Seats | 5 |

## Pricing

849.150.000 VNĐ
```

Do not preserve raw div structure.

Preserve:

- Headings
- Tables
- Lists
- Tabs (as sections)
- Accordions (as sections)

---

## Chunking Strategy

Preferred:

```text
Heading-Based Chunking
 ↓
Token Splitter (only if needed)
```

Not:

```text
Raw Token Chunking
```

Metadata example:

```json
{
  "url": "...",
  "heading_path": [
    "VF 8",
    "Specifications",
    "Battery"
  ]
}
```

---

## Recommended Architecture

```text
Playwright
 ↓
DOM States
 + API Responses
 ↓
Evidence Store
 ↓
Dictionary
 + Regex
 + DOM-Aware Extraction
 ↓
Canonical Knowledge JSON
 ↓
LLM Organizer
 ↓
Markdown Generator
 ↓
Chunking
 ↓
Embedding
 ↓
Retrieval
```
