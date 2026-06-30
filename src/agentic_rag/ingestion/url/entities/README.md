# Entities

Target home for entity extraction from DOM blocks.

Responsibilities:

- Convert semantic blocks into structured entity candidates.
- Preserve entity boundaries before chunk generation.
- Generate retrieval text from structured fields.
- Keep structured values in `Chunk.metadata`.

Example entity types:

- vehicle
- product
- course
- job
- FAQ item
- policy section
- comparison row
