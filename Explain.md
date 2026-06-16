# Shared Metadata Date Rules

This note explains the shared date fields used by URL ingestion, PDF ingestion,
dedup detection, and rule-based metadata checks.

## Meaning

| Field | Required? | Meaning | Owner |
| --- | --- | --- | --- |
| `source_type` | Required | Source family such as `url`, `html`, `text`, or `pdf`. | Ingestion loader |
| `updated_date` | Required | Time this system starts ingesting/crawling/loading the source. | URL/PDF ingestion |
| `created_date` | Optional | Source modified date found inside the URL/PDF data. | URL/PDF parser |
| `language` | Optional | Language found from source data. | URL/PDF parser or enrichment |
| `document_type` | Optional | Page/document type when safely inferred. | URL/PDF enrichment |

## Important Distinction

`updated_date` is not the website's modified date and not the PDF file's
filesystem modified time. It is the start time of our ingestion job.

For URL ingestion:

```text
updated_date = time URL crawl starts
updated_date_source = ingestion_start
```

For PDF ingestion:

```text
updated_date = time PDF load starts
updated_date_source = ingestion_start
```

`created_date` is only added when the source itself exposes a trusted modified
date. For example, URL ingestion can map an HTML tag like
`article:modified_time` into:

```text
created_date = source modified date from page metadata
created_date_source = page_modified_metadata
```

If URL/PDF ingestion cannot find a source modified date, leave `created_date`
absent. Do not fill it with crawl time, upload time, or filesystem time.

## About `fetched_at`

`fetched_at` is URL-local debug metadata. It can stay in URL artifacts and review
demos, but it is not part of the shared metadata schema. Shared consumers should
use `updated_date`.

## Rule-Based Integration

Rule-based code should validate:

```python
required = ["source_type", "updated_date"]
optional = ["created_date", "language", "document_type"]
```

When comparing freshness or conflicts:

- Use `created_date` only when it exists, because it comes from source data.
- Use `updated_date` to know when this system ingested the source.
- Do not treat `updated_date` as proof that the source content changed on that
  date.
