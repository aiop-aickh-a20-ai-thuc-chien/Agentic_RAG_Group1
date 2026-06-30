# Metadata Blocking

Planned L2 candidate generation lives here.

This layer should reduce duplicate-review cost by grouping chunks with shared
metadata before any LLM review runs. Candidate blocks should use stable fields
such as `source_type`, `document_type`, domain or source family,
`canonical_url`, `file_name`, `product_model`, `language`, `heading`, `section`,
and stable entity keys when available.

Rules:

- Keep L1 SHA-256 exact matching in `exact.py`.
- Do not compare all chunks with an LLM.
- Cap overly broad blocks before review.
- Preserve all candidate evidence for downstream review.
- Do not detect factual conflicts here; that belongs in `knowledge_quality`.
