"""Neon-backed index of duplicate candidates for the internal Dedup page.

The authoritative dedup result lives in each chunk's metadata (S3). Re-deriving
the review list from a full S3 scan takes minutes, so this module mirrors the
candidates into a Postgres table that the review endpoint can paginate and
filter instantly — the same pattern the other internal pages use against Neon.

Rows are written by ingestion (per document), the backfill (full replace), and
the manual rebuild. Reads never touch S3.
"""

from __future__ import annotations

from typing import Any

from agentic_rag.autodata_eval.db import get_conn

_TABLE = "dedup_candidates"
_STATS_TABLE = "dedup_corpus_stats"

_CREATE_STATS = f"""
CREATE TABLE IF NOT EXISTS {_STATS_TABLE} (
  id              TEXT PRIMARY KEY DEFAULT 'singleton',
  chunk_count     INTEGER NOT NULL DEFAULT 0,
  document_count  INTEGER NOT NULL DEFAULT 0,
  updated_at      TIMESTAMPTZ DEFAULT NOW()
)
"""

_COLUMNS = (
    "id",
    "layer",
    "score",
    "distance",
    "reason",
    "group_id",
    "status",
    "review_status",
    "duplicate_chunk_id",
    "duplicate_document_id",
    "duplicate_document_name",
    "duplicate_source_type",
    "duplicate_source",
    "duplicate_section",
    "duplicate_page",
    "duplicate_text",
    "canonical_chunk_id",
    "canonical_document_id",
    "canonical_document_name",
    "canonical_source_type",
    "canonical_source",
    "canonical_section",
    "canonical_page",
    "canonical_text",
)

_CREATE_TABLE = f"""
CREATE TABLE IF NOT EXISTS {_TABLE} (
  id                      TEXT PRIMARY KEY,
  layer                   TEXT NOT NULL,
  score                   DOUBLE PRECISION,
  distance                INTEGER,
  reason                  TEXT,
  group_id                TEXT,
  status                  TEXT NOT NULL DEFAULT 'duplicate_candidate',
  review_status           TEXT NOT NULL DEFAULT 'pending',
  duplicate_chunk_id      TEXT NOT NULL,
  duplicate_document_id   TEXT,
  duplicate_document_name TEXT,
  duplicate_source_type   TEXT,
  duplicate_source        TEXT,
  duplicate_section       TEXT,
  duplicate_page          TEXT,
  duplicate_text          TEXT,
  canonical_chunk_id      TEXT,
  canonical_document_id   TEXT,
  canonical_document_name TEXT,
  canonical_source_type   TEXT,
  canonical_source        TEXT,
  canonical_section       TEXT,
  canonical_page          TEXT,
  canonical_text          TEXT,
  created_at              TIMESTAMPTZ DEFAULT NOW()
)
"""

_CREATE_INDEXES = (
    f"CREATE INDEX IF NOT EXISTS idx_dedup_layer ON {_TABLE}(layer)",
    f"CREATE INDEX IF NOT EXISTS idx_dedup_dup_document ON {_TABLE}(duplicate_document_id)",
    f"CREATE INDEX IF NOT EXISTS idx_dedup_canon_document ON {_TABLE}(canonical_document_id)",
    f"CREATE INDEX IF NOT EXISTS idx_dedup_review_status ON {_TABLE}(review_status)",
)


def _ensure_schema(cur: Any) -> None:
    cur.execute(_CREATE_TABLE)
    for statement in _CREATE_INDEXES:
        cur.execute(statement)


def _insert_rows(cur: Any, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    columns_sql = ", ".join(_COLUMNS)
    placeholders = ", ".join(["%s"] * len(_COLUMNS))
    cur.executemany(
        f"""
        INSERT INTO {_TABLE} ({columns_sql})
        VALUES ({placeholders})
        ON CONFLICT (id) DO UPDATE SET
            layer = EXCLUDED.layer,
            score = EXCLUDED.score,
            distance = EXCLUDED.distance,
            reason = EXCLUDED.reason,
            group_id = EXCLUDED.group_id,
            status = EXCLUDED.status,
            review_status = EXCLUDED.review_status,
            duplicate_document_id = EXCLUDED.duplicate_document_id,
            duplicate_document_name = EXCLUDED.duplicate_document_name,
            duplicate_source_type = EXCLUDED.duplicate_source_type,
            duplicate_source = EXCLUDED.duplicate_source,
            duplicate_section = EXCLUDED.duplicate_section,
            duplicate_page = EXCLUDED.duplicate_page,
            duplicate_text = EXCLUDED.duplicate_text,
            canonical_chunk_id = EXCLUDED.canonical_chunk_id,
            canonical_document_id = EXCLUDED.canonical_document_id,
            canonical_document_name = EXCLUDED.canonical_document_name,
            canonical_source_type = EXCLUDED.canonical_source_type,
            canonical_source = EXCLUDED.canonical_source,
            canonical_section = EXCLUDED.canonical_section,
            canonical_page = EXCLUDED.canonical_page,
            canonical_text = EXCLUDED.canonical_text
        """,
        [tuple(row.get(column) for column in _COLUMNS) for row in rows],
    )


def replace_all_candidates(rows: list[dict[str, Any]]) -> int:
    """Replace the entire candidate index (used by the full backfill/rebuild)."""

    with get_conn() as conn:
        with conn.cursor() as cur:
            _ensure_schema(cur)
            cur.execute(f"DELETE FROM {_TABLE}")
            _insert_rows(cur, rows)
        conn.commit()
    return len(rows)


def replace_document_candidates(document_id: str, rows: list[dict[str, Any]]) -> int:
    """Replace candidate rows whose flagged side belongs to one document.

    Called after an (re-)upload: the new document's chunks are always the
    duplicate/candidate side, so clearing by ``duplicate_document_id`` keeps a
    re-upload from leaving stale rows behind.
    """

    with get_conn() as conn:
        with conn.cursor() as cur:
            _ensure_schema(cur)
            cur.execute(
                f"DELETE FROM {_TABLE} WHERE duplicate_document_id = %s",
                (document_id,),
            )
            _insert_rows(cur, rows)
        conn.commit()
    return len(rows)


def delete_document_candidates(document_id: str) -> None:
    """Remove every candidate row referencing a deleted document (either side)."""

    with get_conn() as conn:
        with conn.cursor() as cur:
            _ensure_schema(cur)
            cur.execute(
                f"DELETE FROM {_TABLE} "
                "WHERE duplicate_document_id = %s OR canonical_document_id = %s",
                (document_id, document_id),
            )
        conn.commit()


def upsert_corpus_stats(chunk_count: int, document_count: int) -> None:
    """Persist total corpus size so the review page can show it without hitting S3."""

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(_CREATE_STATS)
            cur.execute(
                f"""
                INSERT INTO {_STATS_TABLE} (id, chunk_count, document_count, updated_at)
                VALUES ('singleton', %s, %s, NOW())
                ON CONFLICT (id) DO UPDATE SET
                    chunk_count    = EXCLUDED.chunk_count,
                    document_count = EXCLUDED.document_count,
                    updated_at     = EXCLUDED.updated_at
                """,
                (chunk_count, document_count),
            )
        conn.commit()


def get_corpus_stats() -> dict[str, int]:
    """Return last-known corpus totals written by rebuild/backfill, or zeros."""

    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute(_CREATE_STATS)
            cur.execute(
                f"SELECT chunk_count, document_count FROM {_STATS_TABLE} WHERE id = 'singleton'"
            )
            row = cur.fetchone()
            if row:
                return {
                    "chunk_count": int(row["chunk_count"]),
                    "document_count": int(row["document_count"]),
                }
    except Exception:
        pass
    return {"chunk_count": 0, "document_count": 0}


def flagged_chunk_ids_by_layer() -> dict[str, list[str]]:
    """Return duplicate chunk ids grouped by the layer that flagged them.

    Powers the dataset import filter: a question whose ground-truth chunk is in
    one of these lists can be hidden when that layer is toggled. Returns empty
    lists on any error so the UI degrades to "no filtering".
    """

    result: dict[str, list[str]] = {
        "exact_sha256": [],
        "simhash": [],
        "embedding_similarity": [],
    }
    try:
        with get_conn() as conn, conn.cursor() as cur:
            _ensure_schema(cur)
            cur.execute(
                f"SELECT layer, duplicate_chunk_id FROM {_TABLE} "
                "WHERE duplicate_chunk_id IS NOT NULL"
            )
            for row in cur.fetchall():
                layer = row["layer"]
                if layer in result:
                    result[layer].append(row["duplicate_chunk_id"])
    except Exception:
        pass
    return result


def _filter_clause(
    *,
    layer: str | None,
    status: str | None,
    source_type: str | None,
    q: str | None,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if layer:
        clauses.append("layer = %s")
        params.append(layer.strip().lower())
    if status:
        clauses.append("(lower(review_status) = %s OR lower(status) = %s)")
        params.extend([status.strip().lower(), status.strip().lower()])
    if source_type:
        clauses.append("lower(duplicate_source_type) = %s")
        params.append(source_type.strip().lower())
    if q and q.strip():
        like = f"%{q.strip()}%"
        clauses.append(
            "(duplicate_text ILIKE %s OR duplicate_document_name ILIKE %s "
            "OR duplicate_chunk_id ILIKE %s OR canonical_text ILIKE %s "
            "OR canonical_document_name ILIKE %s)"
        )
        params.extend([like, like, like, like, like])
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where_sql, params


def query_candidates(
    *,
    layer: str | None = None,
    status: str | None = None,
    source_type: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Return a filtered, paginated page plus global per-layer counts."""

    resolved_limit = max(min(limit, 500), 1)
    resolved_offset = max(offset, 0)
    where_sql, params = _filter_clause(
        layer=layer,
        status=status,
        source_type=source_type,
        q=q,
    )

    corpus = get_corpus_stats()
    with get_conn() as conn, conn.cursor() as cur:
        _ensure_schema(cur)
        cur.execute(f"SELECT COUNT(*) AS total FROM {_TABLE} {where_sql}", params)
        total_row = cur.fetchone()
        total = int(total_row["total"]) if total_row else 0

        cur.execute(
            f"""
            SELECT * FROM {_TABLE}
            {where_sql}
            ORDER BY
                CASE layer
                    WHEN 'exact_sha256' THEN 0
                    WHEN 'simhash' THEN 1
                    WHEN 'embedding_similarity' THEN 2
                    ELSE 3
                END,
                score DESC NULLS LAST,
                id
            LIMIT %s OFFSET %s
            """,
            [*params, resolved_limit, resolved_offset],
        )
        rows = cur.fetchall()

        # Chunk-level cascade guarantees each chunk appears in exactly one layer,
        # so DISTINCT chunk counts per layer are naturally mutually exclusive.
        cur.execute(
            f"""
            SELECT
                COUNT(*) AS pairs,
                COUNT(DISTINCT duplicate_chunk_id) AS unique_candidates,
                COUNT(*) FILTER (WHERE layer = 'exact_sha256') AS exact,
                COUNT(*) FILTER (WHERE layer = 'simhash') AS simhash,
                COUNT(*) FILTER (WHERE layer = 'embedding_similarity') AS embedding,
                COUNT(DISTINCT duplicate_chunk_id)
                    FILTER (WHERE layer = 'exact_sha256') AS exact_chunks,
                COUNT(DISTINCT duplicate_chunk_id)
                    FILTER (WHERE layer = 'simhash') AS simhash_chunks,
                COUNT(DISTINCT duplicate_chunk_id)
                    FILTER (WHERE layer = 'embedding_similarity') AS embedding_chunks
            FROM {_TABLE}
            """
        )
        counts_row = cur.fetchone() or {}

    return {
        "items": [_row_to_item(row) for row in rows],
        "total": total,
        "limit": resolved_limit,
        "offset": resolved_offset,
        "counts": {
            "pairs": int(counts_row.get("pairs") or 0),
            "unique_candidates": int(counts_row.get("unique_candidates") or 0),
            "exact": int(counts_row.get("exact") or 0),
            "simhash": int(counts_row.get("simhash") or 0),
            "embedding": int(counts_row.get("embedding") or 0),
            "exact_chunks": int(counts_row.get("exact_chunks") or 0),
            "simhash_chunks": int(counts_row.get("simhash_chunks") or 0),
            "embedding_chunks": int(counts_row.get("embedding_chunks") or 0),
            "corpus_chunks": corpus["chunk_count"],
            "corpus_documents": corpus["document_count"],
        },
    }


def _row_to_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "status": row["status"],
        "review_status": row["review_status"],
        "layer": row["layer"],
        "score": row["score"],
        "distance": row["distance"],
        "reason": row["reason"],
        "group_id": row["group_id"],
        "canonical": _row_side(row, "canonical"),
        "duplicate": _row_side(row, "duplicate"),
    }


def _row_side(row: dict[str, Any], side: str) -> dict[str, Any] | None:
    chunk_id = row.get(f"{side}_chunk_id")
    if not chunk_id:
        return None
    return {
        "chunk_id": chunk_id,
        "document_id": row.get(f"{side}_document_id"),
        "document_name": row.get(f"{side}_document_name"),
        "source_type": row.get(f"{side}_source_type"),
        "source": row.get(f"{side}_source"),
        "page": row.get(f"{side}_page"),
        "section": row.get(f"{side}_section"),
        "text": row.get(f"{side}_text") or "",
        "metadata": {},
    }
