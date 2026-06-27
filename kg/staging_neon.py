"""Persistent staging + extract-cache on Neon (Postgres) — the production backend.

Drop-in for the in-memory `kg.stage.StagingStore`: same `add / all / delete_document`
surface, so `KGPipeline` doesn't change. Adds an extract-cache so each chunk is
extracted ONCE (resumable across crashes; incremental `--add` re-extracts only new
chunks). Reuses the project's Neon connection (`NEON_CONNECTION` via autodata_eval.db).

Two tables (created on first use, alongside — never touching — the existing ones):
  kg_staged            one row per staged triple  (the durable staging view)
  kg_extracted_chunks  one row per (chunk, content_hash)  (the extract cache marker)
"""

from __future__ import annotations

import hashlib

from kg.embeddings import norm_text
from kg.schema import Chunk, OpenTriple, StagedTriple, content_id

_STAGED_COLS = (
    "triple_id",
    "doc_id",
    "chunk_id",
    "subject",
    "predicate",
    "object",
    "subject_type",
    "object_type",
    "evidence",
)

_CREATE = (
    """
    CREATE TABLE IF NOT EXISTS kg_staged (
      triple_id    TEXT PRIMARY KEY,
      doc_id       TEXT NOT NULL,
      chunk_id     TEXT NOT NULL,
      subject      TEXT NOT NULL,
      predicate    TEXT NOT NULL,
      object       TEXT NOT NULL,
      subject_type TEXT DEFAULT '',
      object_type  TEXT DEFAULT '',
      evidence     TEXT DEFAULT '',
      created_at   TIMESTAMPTZ DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_kg_staged_doc ON kg_staged(doc_id)",
    "CREATE INDEX IF NOT EXISTS idx_kg_staged_chunk ON kg_staged(chunk_id)",
    """
    CREATE TABLE IF NOT EXISTS kg_extracted_chunks (
      chunk_id     TEXT NOT NULL,
      content_hash TEXT NOT NULL,
      doc_id       TEXT DEFAULT '',
      model        TEXT DEFAULT '',
      n_triples    INTEGER DEFAULT 0,
      text         TEXT DEFAULT '',
      extracted_at TIMESTAMPTZ DEFAULT NOW(),
      PRIMARY KEY (chunk_id, content_hash)
    )
    """,
)


_COUNT_STAGED = "SELECT count(*) AS c FROM kg_staged"


def chunk_hash(text: str) -> str:
    """Content hash of a chunk — the extract-cache key (changes invalidate the cache)."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


def _triple_id(chunk_id: str, t: OpenTriple) -> str:
    return content_id(
        "stg",
        "|".join([chunk_id, norm_text(t.subject), norm_text(t.predicate), norm_text(t.object)]),
    )


class NeonStagingStore:
    def __init__(self) -> None:
        self._ensure_schema()

    def _conn(self):
        from agentic_rag.autodata_eval.db import get_conn  # lazy: keeps kg/ importable

        return get_conn()

    def _ensure_schema(self) -> None:
        with self._conn() as conn, conn.cursor() as cur:
            for stmt in _CREATE:
                cur.execute(stmt)
            conn.commit()

    # ---- staging surface (same as kg.stage.StagingStore) ----------------- #
    def add(self, chunk: Chunk, triples: list[OpenTriple]) -> int:
        rows = []
        for t in triples:
            rows.append(
                (
                    _triple_id(chunk.chunk_id, t),
                    chunk.doc_id,
                    chunk.chunk_id,
                    t.subject,
                    t.predicate,
                    t.object,
                    t.subject_type,
                    t.object_type,
                    t.evidence,
                )
            )
        if not rows:
            return 0
        cols = ", ".join(_STAGED_COLS)
        ph = ", ".join(["%s"] * len(_STAGED_COLS))
        with self._conn() as conn, conn.cursor() as cur:
            before = cur.execute(_COUNT_STAGED).fetchone()["c"]
            cur.executemany(
                f"INSERT INTO kg_staged ({cols}) VALUES ({ph}) ON CONFLICT (triple_id) DO NOTHING",
                rows,
            )
            after = cur.execute(_COUNT_STAGED).fetchone()["c"]
            conn.commit()
        return after - before

    def all(self) -> list[StagedTriple]:
        with self._conn() as conn, conn.cursor() as cur:
            rows = cur.execute(
                f"SELECT {', '.join(_STAGED_COLS)} FROM kg_staged ORDER BY doc_id, chunk_id, triple_id"
            ).fetchall()
        return [StagedTriple(**{k: r[k] for k in _STAGED_COLS}) for r in rows]

    def delete_document(self, doc_id: str) -> int:
        with self._conn() as conn, conn.cursor() as cur:
            n = cur.execute("DELETE FROM kg_staged WHERE doc_id = %s", (doc_id,)).rowcount
            cur.execute("DELETE FROM kg_extracted_chunks WHERE doc_id = %s", (doc_id,))
            conn.commit()
        return n

    # ---- extract cache --------------------------------------------------- #
    def is_extracted(self, chunk_id: str, content_hash: str) -> bool:
        with self._conn() as conn, conn.cursor() as cur:
            row = cur.execute(
                "SELECT 1 FROM kg_extracted_chunks WHERE chunk_id = %s AND content_hash = %s",
                (chunk_id, content_hash),
            ).fetchone()
        return row is not None

    def mark_extracted(self, chunk: Chunk, content_hash: str, model: str, n_triples: int) -> None:
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO kg_extracted_chunks (chunk_id, content_hash, doc_id, model, n_triples, text) "
                "VALUES (%s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (chunk_id, content_hash) DO UPDATE SET "
                "n_triples = EXCLUDED.n_triples, text = EXCLUDED.text, extracted_at = NOW()",
                (chunk.chunk_id, content_hash, chunk.doc_id, model, n_triples, chunk.text),
            )
            conn.commit()

    def chunk_texts(self) -> dict[str, str]:
        """All chunk texts ever extracted — so build()'s evidence gate works over the
        whole staged set even when this run only ingested a few new docs."""
        with self._conn() as conn, conn.cursor() as cur:
            rows = cur.execute(
                "SELECT DISTINCT ON (chunk_id) chunk_id, text FROM kg_extracted_chunks "
                "ORDER BY chunk_id, extracted_at DESC"
            ).fetchall()
        return {r["chunk_id"]: r["text"] for r in rows}

    def stats(self) -> dict:
        with self._conn() as conn, conn.cursor() as cur:
            triples = cur.execute(_COUNT_STAGED).fetchone()["c"]
            chunks = cur.execute("SELECT count(*) AS c FROM kg_extracted_chunks").fetchone()["c"]
        return {"staged_triples": triples, "extracted_chunks": chunks}

    # ---- one-time backfill from a JSON staged cache ---------------------- #
    def backfill(self, staged: list[dict], chunk_texts: dict[str, str], model: str = "") -> dict:
        """Bulk-load an existing `--cache` JSON into Neon (idempotent). Makes the data
        durable + resumable without re-extracting; later `--add` only does new chunks."""
        self._ensure_schema()
        srows = [tuple(t.get(c, "") for c in _STAGED_COLS) for t in staged]
        doc_of = {t["chunk_id"]: t.get("doc_id", "") for t in staged}
        crows = [
            (cid, chunk_hash(txt), doc_of.get(cid, ""), model, 0, txt)
            for cid, txt in chunk_texts.items()
        ]
        cols = ", ".join(_STAGED_COLS)
        ph = ", ".join(["%s"] * len(_STAGED_COLS))
        with self._conn() as conn, conn.cursor() as cur:
            cur.executemany(
                f"INSERT INTO kg_staged ({cols}) VALUES ({ph}) ON CONFLICT (triple_id) DO NOTHING",
                srows,
            )
            cur.executemany(
                "INSERT INTO kg_extracted_chunks (chunk_id, content_hash, doc_id, model, n_triples, text) "
                "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (chunk_id, content_hash) DO NOTHING",
                crows,
            )
            conn.commit()
        return self.stats()
