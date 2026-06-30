# LLM Duplicate Review

Planned L2 duplicate review lives here.

The LLM should only evaluate candidates produced by metadata blocking. It should
classify candidate pairs or small groups as `duplicate`, `not_duplicate`, or
`needs_review`, then return confidence, reason, compared metadata fields, and
cited chunk IDs.

Rules:

- Do not run before metadata blocking.
- Do not compare unrelated chunks.
- Do not delete or merge chunks.
- Do not decide which fact is correct when chunks conflict.
- Keep prompts and outputs deterministic enough for evaluation.
