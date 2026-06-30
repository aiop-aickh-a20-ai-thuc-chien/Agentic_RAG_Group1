"""[2] STAGE — append-only raw-triple store.

Decouples EXTRACT (per-document, incremental, can run at ingest) from
CANONICALIZE (batch, needs a global view). In production this is a SQLite/Neon
table keyed on triple_id; here it is an in-memory list. Per-document delete keeps
the graph an eventually-consistent projection (handles re-ingest / GDPR erasure).
"""

from __future__ import annotations

from kg.embeddings import norm_text
from kg.schema import Chunk, OpenTriple, StagedTriple, content_id


class StagingStore:
    def __init__(self) -> None:
        self.rows: list[StagedTriple] = []
        self._seen: set[str] = set()

    def add(self, chunk: Chunk, triples: list[OpenTriple]) -> int:
        added = 0
        for t in triples:
            tid = content_id(
                "stg",
                "|".join(
                    [
                        chunk.chunk_id,
                        norm_text(t.subject),
                        norm_text(t.predicate),
                        norm_text(t.object),
                    ]
                ),
            )
            if tid in self._seen:
                continue
            self._seen.add(tid)
            self.rows.append(
                StagedTriple(
                    triple_id=tid,
                    doc_id=chunk.doc_id,
                    chunk_id=chunk.chunk_id,
                    subject=t.subject,
                    predicate=t.predicate,
                    object=t.object,
                    subject_type=t.subject_type,
                    object_type=t.object_type,
                    evidence=t.evidence,
                )
            )
            added += 1
        return added

    def all(self) -> list[StagedTriple]:
        return list(self.rows)

    def delete_document(self, doc_id: str) -> int:
        removed = [r for r in self.rows if r.doc_id == doc_id]
        self.rows = [r for r in self.rows if r.doc_id != doc_id]
        self._seen -= {r.triple_id for r in removed}
        return len(removed)
