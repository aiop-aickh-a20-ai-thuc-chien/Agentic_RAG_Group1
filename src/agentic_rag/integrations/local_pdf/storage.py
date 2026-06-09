"""Persistent storage adapters for local source ingestion."""

from __future__ import annotations

import contextlib
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict

from agentic_rag.core.contracts import Chunk


class _LocalPdfStorageModel(BaseModel):
    """Base model for immutable local source storage DTOs."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class StoredSourceDocument(_LocalPdfStorageModel):
    """Stored source document metadata plus its chunk count."""

    document_id: str
    dataset_id: str
    name: str
    source_type: str
    source: str
    total_chunks: int
    metadata: dict[str, object]


class StoredRawSource(_LocalPdfStorageModel):
    """Raw source bytes plus the content type needed by the API response."""

    content: bytes
    content_type: str
    name: str


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

    def read_chunks_for_documents(self, document_ids: list[str]) -> list[Chunk]:
        """Return chunks for multiple documents in one query."""

    def list_documents(self) -> list[StoredSourceDocument]:
        """Return stored source document metadata."""

    def delete_document(self, document_id: str) -> None:
        """Delete one source document and all its chunks."""

    def delete_all_documents(self) -> int:
        """Delete all source documents and chunks. Returns number of deleted documents."""


_LIST_CACHE_TTL = 60  # seconds
_list_cache: dict[str, tuple[float, list[StoredSourceDocument]]] = {}


class S3LocalSourceStore:
    """Store source documents, chunks, and artifacts in S3-compatible object storage."""

    def __init__(self, *, bucket: str, prefix: str = "", client: Any | None = None) -> None:
        if not bucket.strip():
            raise ValueError("S3 source store requires AWS_S3_BUCKET.")
        self._bucket = bucket.strip()
        self._prefix = _normalize_s3_prefix(prefix)
        self._client: Any = client or _s3_client_from_env()
        self._cache_key = f"{self._bucket}/{self._prefix}"

    @classmethod
    def from_env(cls) -> S3LocalSourceStore:
        """Create an S3 source store from environment variables."""

        import os

        return cls(
            bucket=os.getenv("AWS_S3_BUCKET", "").strip(),
            prefix=os.getenv("AWS_S3_PREFIX", "").strip(),
        )

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
        base_key = self._document_prefix(document_id)
        raw_key = self._write_raw_source(
            base_key=base_key,
            source_type=source_type,
            source=source,
            raw_path=raw_path,
        )
        markdown_key = None
        if markdown_path is not None and markdown_path.exists():
            markdown_key = f"{base_key}/parsed/document.md"
            self._put_bytes(
                markdown_key,
                markdown_path.read_bytes(),
                content_type="text/markdown; charset=utf-8",
            )

        chunks_key = f"{base_key}/chunks/chunks.jsonl"
        chunks_payload = "\n".join(chunk.model_dump_json() for chunk in chunks)
        self._put_bytes(
            chunks_key,
            f"{chunks_payload}\n".encode() if chunks_payload else b"",
            content_type="application/x-ndjson; charset=utf-8",
        )

        now = datetime.now(UTC).isoformat()
        manifest = {
            "document_id": document_id,
            "dataset_id": dataset_id,
            "provider": "local_pdf",
            "name": name,
            "source_type": source_type,
            "source": source,
            "total_chunks": len(chunks),
            "created_at": now,
            "updated_at": now,
            "raw_key": raw_key,
            "markdown_key": markdown_key,
            "chunks_key": chunks_key,
            "metadata": metadata,
        }
        self._put_json(f"{base_key}/manifest.json", manifest)
        self._invalidate_list_cache()

    def read_chunks(self, document_id: str) -> list[Chunk]:
        manifest = self._read_manifest(document_id)
        if manifest is None:
            return []
        chunks_key = _manifest_text(manifest, "chunks_key")
        if not chunks_key:
            return []
        return _chunks_from_jsonl(self._get_bytes(chunks_key).decode())

    def read_all_chunks(self) -> list[Chunk]:
        return [
            chunk
            for document in self.list_documents()
            for chunk in self.read_chunks(document.document_id)
        ]

    def read_chunks_for_documents(self, document_ids: list[str]) -> list[Chunk]:
        return [chunk for document_id in document_ids for chunk in self.read_chunks(document_id)]

    def _invalidate_list_cache(self) -> None:
        _list_cache.pop(self._cache_key, None)

    def list_documents(self) -> list[StoredSourceDocument]:
        now = time.monotonic()
        cached = _list_cache.get(self._cache_key)
        if cached is not None and (now - cached[0]) < _LIST_CACHE_TTL:
            return cached[1]

        manifest_keys = [
            key for key in self._list_keys(self._prefix) if key.endswith("/manifest.json")
        ]

        def _fetch(key: str) -> StoredSourceDocument | None:
            try:
                manifest = json.loads(self._get_bytes(key).decode())
                return (
                    _stored_document_from_manifest(manifest) if isinstance(manifest, dict) else None
                )
            except Exception:
                return None

        documents: list[StoredSourceDocument] = []
        with ThreadPoolExecutor(max_workers=_S3_MAX_CONNECTIONS) as pool:
            futures = {pool.submit(_fetch, key): key for key in manifest_keys}
            for fut in as_completed(futures):
                result = fut.result()
                if result is not None:
                    documents.append(result)

        sorted_docs = sorted(
            documents,
            key=lambda document: str(document.metadata.get("updated_at") or ""),
            reverse=True,
        )
        _list_cache[self._cache_key] = (time.monotonic(), sorted_docs)
        return sorted_docs

    def read_markdown(self, document_id: str) -> str:
        manifest = self._read_manifest(document_id)
        if manifest is None:
            return ""
        markdown_key = _manifest_text(manifest, "markdown_key")
        if not markdown_key:
            return ""
        return self._get_bytes(markdown_key).decode()

    def read_raw(self, document_id: str) -> StoredRawSource:
        manifest = self._read_manifest(document_id)
        if manifest is None:
            raise ValueError(f"Raw source file is not available: {document_id}")
        raw_key = _manifest_text(manifest, "raw_key")
        if not raw_key:
            raise ValueError(f"Raw source file is not available: {document_id}")
        source_type = _manifest_text(manifest, "source_type") or "pdf"
        return StoredRawSource(
            content=self._get_bytes(raw_key),
            content_type=_content_type_for_source(source_type),
            name=_manifest_text(manifest, "name") or document_id,
        )

    def delete_document(self, document_id: str) -> None:
        prefix = f"{self._document_prefix(document_id)}/"
        keys = self._list_keys(prefix)
        if keys:
            self._delete_keys(keys)
        self._invalidate_list_cache()

    def delete_all_documents(self) -> int:
        keys = self._list_keys(self._prefix)
        manifest_keys = [key for key in keys if key.endswith("/manifest.json")]
        if keys:
            self._delete_keys(keys)
        self._invalidate_list_cache()
        return len(manifest_keys)

    def _document_prefix(self, document_id: str) -> str:
        safe_document_id = _safe_s3_segment(document_id)
        return f"{self._prefix}{safe_document_id}" if self._prefix else safe_document_id

    def _read_manifest(self, document_id: str) -> dict[str, object] | None:
        key = f"{self._document_prefix(document_id)}/manifest.json"
        try:
            payload = json.loads(self._get_bytes(key).decode())
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None

    def _write_raw_source(
        self,
        *,
        base_key: str,
        source_type: str,
        source: str,
        raw_path: Path | None,
    ) -> str:
        suffix = "source.pdf" if source_type == "pdf" else "source.txt"
        raw_key = f"{base_key}/raw/{suffix}"
        if raw_path is not None and raw_path.exists():
            payload = raw_path.read_bytes()
        else:
            payload = source.encode()
        self._put_bytes(raw_key, payload, content_type=_content_type_for_source(source_type))
        return raw_key

    def _put_json(self, key: str, payload: dict[str, object]) -> None:
        self._put_bytes(
            key,
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode(),
            content_type="application/json; charset=utf-8",
        )

    def _put_bytes(self, key: str, payload: bytes, *, content_type: str) -> None:
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=payload,
            ContentType=content_type,
        )

    def _get_bytes(self, key: str) -> bytes:
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        body = response["Body"]
        payload = body.read()
        return payload if isinstance(payload, bytes) else bytes(payload)

    def _list_keys(self, prefix: str) -> list[str]:
        keys: list[str] = []
        continuation_token: str | None = None
        while True:
            kwargs = {"Bucket": self._bucket, "Prefix": prefix}
            if continuation_token is not None:
                kwargs["ContinuationToken"] = continuation_token
            response = self._client.list_objects_v2(**kwargs)
            if not isinstance(response, dict):
                return keys
            contents = response.get("Contents", [])
            if isinstance(contents, list):
                keys.extend(
                    str(item["Key"])
                    for item in contents
                    if isinstance(item, dict) and "Key" in item
                )
            if not response.get("IsTruncated"):
                return keys
            raw_token = response.get("NextContinuationToken")
            if not isinstance(raw_token, str) or not raw_token:
                raise RuntimeError(
                    "S3 returned a truncated object listing without a continuation token."
                )
            continuation_token = raw_token

    def _delete_keys(self, keys: list[str]) -> None:
        for start in range(0, len(keys), 1000):
            batch = keys[start : start + 1000]
            self._client.delete_objects(
                Bucket=self._bucket,
                Delete={"Objects": [{"Key": key} for key in batch]},
            )


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
            kwargs={"prepare_threshold": None},
        )
        self._ensure_schema()

    def close(self) -> None:
        """Close the connection pool gracefully."""
        with contextlib.suppress(Exception):
            self._pool.close()

    def __del__(self) -> None:
        with contextlib.suppress(Exception):
            self._pool.close(timeout=1.0)

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

    def delete_all_documents(self) -> int:
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"delete from {self._documents_table}")
                count = cur.rowcount or 0
            conn.commit()
        return count

    def read_chunks(self, document_id: str) -> list[Chunk]:
        return self._read_chunks(where_sql="where document_id = %s", params=(document_id,))

    def read_all_chunks(self) -> list[Chunk]:
        return self._read_chunks(where_sql="", params=())

    def read_chunks_for_documents(self, document_ids: list[str]) -> list[Chunk]:
        if not document_ids:
            return []
        placeholders = ", ".join(["%s"] * len(document_ids))
        return self._read_chunks(
            where_sql=f"where document_id in ({placeholders})",
            params=tuple(document_ids),
        )

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


_S3_MAX_CONNECTIONS = 50


def _s3_client_from_env() -> Any:
    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:
        raise RuntimeError("LOCAL_SOURCE_STORE=s3 requires boto3 to be installed.") from exc

    return boto3.client("s3", config=Config(max_pool_connections=_S3_MAX_CONNECTIONS))  # type: ignore[no-untyped-call]


def _normalize_s3_prefix(prefix: str) -> str:
    normalized = prefix.strip().strip("/")
    return f"{normalized}/" if normalized else ""


def _safe_s3_segment(value: str) -> str:
    import re

    cleaned = re.sub(r"[^A-Za-z0-9._:-]+", "-", value.strip()).strip("-")
    if not cleaned:
        raise ValueError("S3 document id cannot be empty.")
    return cleaned


def _manifest_text(manifest: dict[str, object], key: str) -> str | None:
    value = manifest.get(key)
    return value if isinstance(value, str) and value else None


def _stored_document_from_manifest(manifest: dict[str, object]) -> StoredSourceDocument:
    metadata = manifest.get("metadata")
    document_metadata = dict(metadata) if isinstance(metadata, dict) else {}
    updated_at = manifest.get("updated_at")
    if isinstance(updated_at, str):
        document_metadata.setdefault("updated_at", updated_at)
    total_chunks = manifest.get("total_chunks")
    return StoredSourceDocument(
        document_id=str(manifest.get("document_id") or ""),
        dataset_id=str(manifest.get("dataset_id") or ""),
        name=str(manifest.get("name") or ""),
        source_type=str(manifest.get("source_type") or ""),
        source=str(manifest.get("source") or ""),
        total_chunks=total_chunks if isinstance(total_chunks, int) else 0,
        metadata=document_metadata,
    )


def _chunks_from_jsonl(payload: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    for line in payload.splitlines():
        stripped = line.strip()
        if stripped:
            chunks.append(Chunk.model_validate_json(stripped))
    return chunks


def _content_type_for_source(source_type: str) -> str:
    if source_type == "pdf":
        return "application/pdf"
    return "text/plain; charset=utf-8"


def _storage_chunk_id(*, chunk: Chunk, fallback_index: int) -> str:
    raw = chunk.metadata.get("storage_chunk_id")
    if isinstance(raw, str) and raw:
        return raw
    ingestion_id = chunk.metadata.get("chunk_id")
    if isinstance(ingestion_id, str) and ingestion_id:
        return ingestion_id
    document_id = str(chunk.metadata.get("document_id") or "document")
    return f"{document_id}:{fallback_index:04d}"


def _chunk_index(*, chunk: Chunk, fallback_index: int) -> int:
    value = chunk.metadata.get("chunk_index")
    if isinstance(value, bool):
        return fallback_index
    if isinstance(value, int):
        return value
    return fallback_index
