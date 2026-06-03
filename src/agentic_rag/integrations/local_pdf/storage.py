"""Persistent storage adapters for local source ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from psycopg.types.json import Jsonb

from agentic_rag.core.contracts import Chunk


@dataclass(frozen=True)
class StoredSourceDocument:
    """Stored source document metadata plus its chunk count."""

    document_id: str
    dataset_id: str
    name: str
    source_type: str
    source: str
    total_chunks: int
    metadata: dict[str, object]


class LocalSourceStore(Protocol):
    """Persistence boundary for locally ingested source documents and chunks."""

    def write_document(
        self,
        *,
        document_id: str,
        dataset_id: str,
        name: str,
        source_type: str,
        source: str,
        raw_path: Path | None,
        markdown_path: Path | None,
        metadata: dict[str, object],
        chunks: list[Chunk],
    ) -> None:
        """Persist one source document and its chunks."""

    def read_chunks(self, document_id: str) -> list[Chunk]:
        """Return chunks for one document."""

    def read_all_chunks(self) -> list[Chunk]:
        """Return chunks for all stored documents."""

    def list_documents(self) -> list[StoredSourceDocument]:
        """Return stored source document metadata."""

    def delete_document(self, document_id: str) -> None:
        """Delete one source document and all its chunks."""


class PostgresLocalSourceStore:
    """Store local documents/chunks in Postgres while files remain on disk."""

    def __init__(self, *, connection: str, table_prefix: str = "local_rag") -> None:
        if not connection.strip():
            raise ValueError("Postgres source store requires a connection string.")
        self._connection = connection
        self._psycopg_connection = _psycopg_connection_string(connection)
        self._documents_table = _safe_table_name(f"{table_prefix}_documents")
        self._chunks_table = _safe_table_name(f"{table_prefix}_chunks")
        from psycopg_pool import ConnectionPool

        self._pool = ConnectionPool(
            self._psycopg_connection,
            min_size=1,
            max_size=4,
            open=True,
        )
        self._ensure_schema()

    def write_document(
        self,
        *,
        document_id: str,
        dataset_id: str,
        name: str,
        source_type: str,
        source: str,
        raw_path: Path | None,
        markdown_path: Path | None,
        metadata: dict[str, object],
        chunks: list[Chunk],
    ) -> None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    insert into {self._documents_table}
                        (document_id, dataset_id, name, source_type, source,
                         raw_path, markdown_path, metadata, updated_at)
                    values (%s, %s, %s, %s, %s, %s, %s, %s, now())
                    on conflict (document_id) do update set
                        dataset_id = excluded.dataset_id,
                        name = excluded.name,
                        source_type = excluded.source_type,
                        source = excluded.source,
                        raw_path = excluded.raw_path,
                        markdown_path = excluded.markdown_path,
                        metadata = excluded.metadata,
                        updated_at = now()
                    """,
                    (
                        document_id,
                        dataset_id,
                        name,
                        source_type,
                        source,
                        str(raw_path) if raw_path is not None else None,
                        str(markdown_path) if markdown_path is not None else None,
                        Jsonb(metadata),
                    ),
                )
                cur.execute(
                    f"delete from {self._chunks_table} where document_id = %s",
                    (document_id,),
                )
                if chunks:
                    rows = [
                        (
                            _storage_chunk_id(chunk=chunk, fallback_index=index),
                            document_id,
                            chunk.chunk_id,
                            _chunk_index(chunk=chunk, fallback_index=index),
                            chunk.text,
                            Jsonb(chunk.metadata),
                        )
                        for index, chunk in enumerate(chunks, start=1)
                    ]
                    placeholders = ", ".join(["(%s, %s, %s, %s, %s, %s)"] * len(rows))
                    flat_values = [v for row in rows for v in row]
                    cur.execute(
                        f"""
                        insert into {self._chunks_table}
                            (storage_chunk_id, document_id, chunk_id, chunk_index, text, metadata)
                        values {placeholders}
                        """,
                        flat_values,
                    )
            conn.commit()

    def delete_document(self, document_id: str) -> None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"delete from {self._documents_table} where document_id = %s",
                    (document_id,),
                )
                if cur.rowcount == 0:
                    raise ValueError(f"Document {document_id!r} not found in store.")
            conn.commit()

    def read_chunks(self, document_id: str) -> list[Chunk]:
        return self._read_chunks(where_sql="where document_id = %s", params=(document_id,))

    def read_all_chunks(self) -> list[Chunk]:
        return self._read_chunks(where_sql="", params=())

    def list_documents(self) -> list[StoredSourceDocument]:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                select
                    d.document_id,
                    d.dataset_id,
                    d.name,
                    d.source_type,
                    d.source,
                    d.metadata,
                    count(c.storage_chunk_id) as chunk_count
                from {self._documents_table} d
                left join {self._chunks_table} c on c.document_id = d.document_id
                group by d.document_id, d.dataset_id, d.name, d.source_type, d.source, d.metadata
                order by max(coalesce(c.created_at, d.created_at)) desc, d.created_at desc
                """
            )
            rows = cur.fetchall()

        return [
            StoredSourceDocument(
                document_id=str(document_id),
                dataset_id=str(dataset_id),
                name=str(name),
                source_type=str(source_type),
                source=str(source),
                total_chunks=int(total_chunks),
                metadata=dict(metadata) if isinstance(metadata, dict) else {},
            )
            for document_id, dataset_id, name, source_type, source, metadata, total_chunks in rows
        ]

    def _ensure_schema(self) -> None:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    create table if not exists {self._documents_table} (
                        document_id text primary key,
                        dataset_id text not null,
                        name text not null,
                        source_type text not null,
                        source text not null,
                        raw_path text,
                        markdown_path text,
                        metadata jsonb not null default '{{}}'::jsonb,
                        created_at timestamptz not null default now(),
                        updated_at timestamptz not null default now()
                    )
                    """
                )
                cur.execute(
                    f"""
                    create table if not exists {self._chunks_table} (
                        storage_chunk_id text primary key,
                        document_id text not null references {self._documents_table}(document_id)
                            on delete cascade,
                        chunk_id text not null,
                        chunk_index integer not null,
                        text text not null,
                        metadata jsonb not null default '{{}}'::jsonb,
                        created_at timestamptz not null default now()
                    )
                    """
                )
                cur.execute(
                    f"""
                    create index if not exists {self._chunks_table}_document_idx
                    on {self._chunks_table} (document_id, chunk_index)
                    """
                )
                cur.execute(
                    f"""
                    create index if not exists {self._chunks_table}_metadata_idx
                    on {self._chunks_table} using gin (metadata)
                    """
                )
            conn.commit()

    def _read_chunks(self, *, where_sql: str, params: tuple[object, ...]) -> list[Chunk]:
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                select chunk_id, text, metadata, storage_chunk_id
                from {self._chunks_table}
                {where_sql}
                order by document_id, chunk_index, storage_chunk_id
                """,
                params,
            )
            rows = cur.fetchall()

        chunks: list[Chunk] = []
        for chunk_id, text, metadata, storage_chunk_id in rows:
            chunk_metadata = dict(metadata) if isinstance(metadata, dict) else {}
            chunk_metadata.setdefault("storage_chunk_id", str(storage_chunk_id))
            chunks.append(
                Chunk(
                    chunk_id=str(chunk_id),
                    text=str(text),
                    metadata=chunk_metadata,
                )
            )
        return chunks


def _safe_table_name(value: str) -> str:
    import re

    if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", value):
        raise ValueError(f"Unsafe Postgres table name: {value}")
    return value


def _psycopg_connection_string(connection: str) -> str:
    if connection.startswith("postgresql+psycopg://"):
        return f"postgresql://{connection.removeprefix('postgresql+psycopg://')}"
    if connection.startswith("postgres+psycopg://"):
        return f"postgres://{connection.removeprefix('postgres+psycopg://')}"
    return connection


def _storage_chunk_id(*, chunk: Chunk, fallback_index: int) -> str:
    raw = chunk.metadata.get("storage_chunk_id")
    if isinstance(raw, str) and raw:
        return raw
    document_id = str(chunk.metadata.get("document_id") or "document")
    return f"{document_id}:{fallback_index:04d}"


def _chunk_index(*, chunk: Chunk, fallback_index: int) -> int:
    value = chunk.metadata.get("chunk_index")
    if isinstance(value, bool):
        return fallback_index
    if isinstance(value, int):
        return value
    return fallback_index
