# Policy

Target home for duplicate-resolution policy.

The current package is detection-only. Policy code should not be added until the
team agrees on how duplicate signals affect ingestion.

Conflict detection is owned by `agentic_rag.ingestion.knowledge_quality`, not by
this package. Dedup policy may consult knowledge-quality reports in the future,
but it should not reimplement conflict rules.

Starting policy:

- Exact duplicates: safe to mark.
- Lexical near-duplicates: mark conservatively for review.
- Semantic near-duplicates: review-only unless knowledge-quality conflict checks
  pass.

Never auto-delete or auto-merge chunks only because embedding similarity is
high. Similar topics can still contain different facts, numbers, prices, dates,
or technical specifications.
