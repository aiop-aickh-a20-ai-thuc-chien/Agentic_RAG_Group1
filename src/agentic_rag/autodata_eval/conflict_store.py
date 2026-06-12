"""Neon-backed index of knowledge-quality conflict findings for the internal Conflict page.

Tách bạch với dedup: dedup lo chunk TRÙNG (``dedup_store``), module này chỉ lo chunk
MÂU THUẪN (kind="conflict" do ``ingestion.knowledge_quality`` sinh ra). Findings tất
định (tầng số ``deterministic_v1``) được mirror vào Postgres để trang review phân trang
+ lọc tức thì, giống đúng pattern ``dedup_store`` dùng với Neon.

Rows được ghi bởi script scan toàn corpus (full replace) và khi xoá document. Reads
không bao giờ chạm S3.
"""

from __future__ import annotations

from typing import Any

from agentic_rag.autodata_eval.db import get_conn

_TABLE = "knowledge_quality_findings"
_STATS_TABLE = "knowledge_quality_corpus_stats"

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
    "conflict_type",
    "attribute",
    "entity",
    "severity",
    "confidence",
    "summary",
    "suggested_action",
    "review_status",
    "left_chunk_id",
    "left_document_id",
    "left_document_name",
    "left_source_type",
    "left_source",
    "left_section",
    "left_page",
    "left_text",
    "left_value",
    "right_chunk_id",
    "right_document_id",
    "right_document_name",
    "right_source_type",
    "right_source",
    "right_section",
    "right_page",
    "right_text",
    "right_value",
)

_CREATE_TABLE = f"""
CREATE TABLE IF NOT EXISTS {_TABLE} (
  id                   TEXT PRIMARY KEY,
  conflict_type        TEXT NOT NULL DEFAULT 'numeric',
  attribute            TEXT,
  entity               TEXT,
  severity             TEXT NOT NULL DEFAULT 'warning',
  confidence           DOUBLE PRECISION,
  summary              TEXT,
  suggested_action     TEXT,
  review_status        TEXT NOT NULL DEFAULT 'pending',
  left_chunk_id        TEXT NOT NULL,
  left_document_id     TEXT,
  left_document_name   TEXT,
  left_source_type     TEXT,
  left_source          TEXT,
  left_section         TEXT,
  left_page            TEXT,
  left_text            TEXT,
  left_value           TEXT,
  right_chunk_id       TEXT NOT NULL,
  right_document_id    TEXT,
  right_document_name  TEXT,
  right_source_type    TEXT,
  right_source         TEXT,
  right_section        TEXT,
  right_page           TEXT,
  right_text           TEXT,
  right_value          TEXT,
  created_at           TIMESTAMPTZ DEFAULT NOW()
)
"""

_CREATE_INDEXES = (
    f"CREATE INDEX IF NOT EXISTS idx_kqf_conflict_type ON {_TABLE}(conflict_type)",
    f"CREATE INDEX IF NOT EXISTS idx_kqf_attribute ON {_TABLE}(attribute)",
    f"CREATE INDEX IF NOT EXISTS idx_kqf_left_document ON {_TABLE}(left_document_id)",
    f"CREATE INDEX IF NOT EXISTS idx_kqf_right_document ON {_TABLE}(right_document_id)",
    f"CREATE INDEX IF NOT EXISTS idx_kqf_review_status ON {_TABLE}(review_status)",
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
    update_columns = [c for c in _COLUMNS if c != "id"]
    update_sql = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_columns)
    cur.executemany(
        f"""
        INSERT INTO {_TABLE} ({columns_sql})
        VALUES ({placeholders})
        ON CONFLICT (id) DO UPDATE SET {update_sql}
        """,
        [tuple(row.get(column) for column in _COLUMNS) for row in rows],
    )


def replace_all_findings(rows: list[dict[str, Any]]) -> int:
    """Replace the entire conflict index (used by the full corpus scan)."""

    with get_conn() as conn:
        with conn.cursor() as cur:
            _ensure_schema(cur)
            cur.execute(f"DELETE FROM {_TABLE}")
            _insert_rows(cur, rows)
        conn.commit()
    return len(rows)


def delete_document_findings(document_id: str) -> None:
    """Remove every conflict row referencing a deleted document (either side)."""

    with get_conn() as conn:
        with conn.cursor() as cur:
            _ensure_schema(cur)
            cur.execute(
                f"DELETE FROM {_TABLE} WHERE left_document_id = %s OR right_document_id = %s",
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
    """Return last-known corpus totals written by the scan, or zeros."""

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


def flagged_chunk_ids() -> list[str]:
    """Return distinct chunk ids that appear on either side of any conflict.

    Powers the optional "ẩn chunk mâu thuẫn" filter. Returns an empty list on any
    error so the UI degrades to "no filtering". (Ở eval KHÔNG nên ẩn — chunk mâu
    thuẫn là test case quý.)
    """

    found: set[str] = set()
    try:
        with get_conn() as conn, conn.cursor() as cur:
            _ensure_schema(cur)
            cur.execute(f"SELECT left_chunk_id, right_chunk_id FROM {_TABLE}")
            for row in cur.fetchall():
                for value in (row.get("left_chunk_id"), row.get("right_chunk_id")):
                    if value:
                        found.add(value)
    except Exception:
        pass
    return sorted(found)


def _filter_clause(
    *,
    conflict_type: str | None,
    attribute: str | None,
    status: str | None,
    q: str | None,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if conflict_type:
        clauses.append("conflict_type = %s")
        params.append(conflict_type.strip().lower())
    if attribute:
        clauses.append("attribute = %s")
        params.append(attribute.strip().lower())
    if status:
        clauses.append("lower(review_status) = %s")
        params.append(status.strip().lower())
    if q and q.strip():
        like = f"%{q.strip()}%"
        clauses.append(
            "(left_text ILIKE %s OR right_text ILIKE %s OR entity ILIKE %s "
            "OR left_document_name ILIKE %s OR right_document_name ILIKE %s "
            "OR summary ILIKE %s)"
        )
        params.extend([like, like, like, like, like, like])
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where_sql, params


def query_findings(
    *,
    conflict_type: str | None = None,
    attribute: str | None = None,
    status: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Return a filtered, paginated page plus global counts by attribute."""

    resolved_limit = max(min(limit, 500), 1)
    resolved_offset = max(offset, 0)
    where_sql, params = _filter_clause(
        conflict_type=conflict_type,
        attribute=attribute,
        status=status,
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
            ORDER BY confidence DESC NULLS LAST, entity, id
            LIMIT %s OFFSET %s
            """,
            [*params, resolved_limit, resolved_offset],
        )
        rows = cur.fetchall()

        cur.execute(
            f"""
            SELECT
                COUNT(*) AS findings,
                COUNT(DISTINCT entity) AS entities,
                COUNT(*) FILTER (WHERE attribute = 'warranty_duration') AS warranty_duration,
                COUNT(*) FILTER (WHERE attribute = 'duration') AS duration,
                COUNT(*) FILTER (WHERE attribute = 'price') AS price,
                COUNT(*) FILTER (WHERE attribute = 'distance_km') AS distance_km,
                COUNT(*) FILTER (WHERE attribute = 'date') AS date
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
            "findings": int(counts_row.get("findings") or 0),
            "entities": int(counts_row.get("entities") or 0),
            "warranty_duration": int(counts_row.get("warranty_duration") or 0),
            "duration": int(counts_row.get("duration") or 0),
            "price": int(counts_row.get("price") or 0),
            "distance_km": int(counts_row.get("distance_km") or 0),
            "date": int(counts_row.get("date") or 0),
            "corpus_chunks": corpus["chunk_count"],
            "corpus_documents": corpus["document_count"],
        },
    }


def _row_to_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "conflict_type": row["conflict_type"],
        "attribute": row.get("attribute"),
        "entity": row.get("entity"),
        "severity": row["severity"],
        "confidence": row.get("confidence"),
        "summary": row.get("summary"),
        "suggested_action": row.get("suggested_action"),
        "review_status": row["review_status"],
        "left": _row_side(row, "left"),
        "right": _row_side(row, "right"),
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
        "value": row.get(f"{side}_value"),
    }
