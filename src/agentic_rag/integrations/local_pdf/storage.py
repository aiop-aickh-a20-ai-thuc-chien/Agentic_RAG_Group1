"""Persistent storage adapters for local source ingestion."""

from __future__ import annotations

import contextlib
import json
import threading
import time
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict

from agentic_rag.core.contracts import Chunk


class S3StorageError(RuntimeError):
    """Safe failure raised when an S3 storage operation cannot complete."""

    def __init__(self, *, operation: str, key: str) -> None:
        self.operation = operation
        self.key = key
        super().__init__(f"S3 storage operation failed: {operation} for key {key!r}.")


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


class S3CanonicalChunks(_LocalPdfStorageModel):
    """Chunks tied to one stable canonical S3 manifest observation."""

    chunks: list[Chunk]
    manifest_payload: bytes
    manifest_etag: str


class StoredSourceSnapshot(_LocalPdfStorageModel):
    """Portable source-store snapshot used to restore a failed replacement."""

    document_id: str
    dataset_id: str
    name: str
    source_type: str
    source: str
    raw_path: str | None
    markdown_path: str | None
    metadata: dict[str, object]
    chunks: list[Chunk]


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
_document_locks: dict[str, threading.Lock] = {}
_document_locks_guard = threading.Lock()


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
        transaction_id: str | None = None,
    ) -> None:
        base_key = self._document_prefix(document_id)
        write_transaction_id = transaction_id or uuid.uuid4().hex
        artifact_base_key = f"{base_key}/versions/{write_transaction_id}"
        raw_key = self._write_raw_source(
            base_key=artifact_base_key,
            source_type=source_type,
            source=source,
            raw_path=raw_path,
        )
        markdown_key = None
        if markdown_path is not None and markdown_path.exists():
            markdown_key = f"{artifact_base_key}/parsed/document.md"
            self._put_bytes(
                markdown_key,
                markdown_path.read_bytes(),
                content_type="text/markdown; charset=utf-8",
            )

        chunks_key = f"{artifact_base_key}/chunks/chunks.jsonl"
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
            "write_transaction_id": write_transaction_id,
        }
        self._put_json(f"{base_key}/manifest.json", manifest)
        self._invalidate_list_cache()

    @contextlib.contextmanager
    def document_write_lock(self, document_id: str) -> Iterator[None]:
        """Serialize replacement transactions for one S3 document in this process."""

        lock_key = f"{self._cache_key}/{_safe_s3_segment(document_id)}"
        with _document_locks_guard:
            lock = _document_locks.setdefault(lock_key, threading.Lock())
        with lock:
            yield

    def read_chunks(self, document_id: str) -> list[Chunk]:
        manifest = self._read_manifest(document_id)
        if manifest is None:
            return []
        chunks_key = _manifest_text(manifest, "chunks_key")
        if not chunks_key:
            return []
        payload = self._get_bytes(chunks_key)
        return _chunks_from_jsonl(payload.decode()) if payload is not None else []

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
            payload = self._get_bytes(key)
            if payload is None:
                return None
            manifest = json.loads(payload.decode())
            return _stored_document_from_manifest(manifest) if isinstance(manifest, dict) else None

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
        payload = self._get_bytes(markdown_key)
        return payload.decode() if payload is not None else ""

    def read_raw(self, document_id: str) -> StoredRawSource:
        manifest = self._read_manifest(document_id)
        if manifest is None:
            raise ValueError(f"Raw source file is not available: {document_id}")
        raw_key = _manifest_text(manifest, "raw_key")
        if not raw_key:
            raise ValueError(f"Raw source file is not available: {document_id}")
        source_type = _manifest_text(manifest, "source_type") or "pdf"
        payload = self._get_bytes(raw_key)
        if payload is None:
            raise ValueError(f"Raw source file is not available: {document_id}")
        return StoredRawSource(
            content=payload,
            content_type=_content_type_for_source(source_type),
            name=_manifest_text(manifest, "name") or document_id,
        )

    def mark_document_orphaned(self, document_id: str, *, reason: str) -> None:
        """Mark a stored document for admin cleanup without deleting S3 objects."""

        manifest = self._read_manifest(document_id)
        if manifest is None:
            raise ValueError(f"Document not found: {document_id}")

        metadata = manifest.get("metadata")
        document_metadata = dict(metadata) if isinstance(metadata, dict) else {}
        now = datetime.now(UTC).isoformat()
        document_metadata.update(
            {
                "source_index_status": "orphaned",
                "source_index_reason": reason,
                "source_index_updated_at": now,
            }
        )
        manifest["metadata"] = document_metadata
        manifest["updated_at"] = now
        self._put_json(f"{self._document_prefix(document_id)}/manifest.json", manifest)
        self._invalidate_list_cache()

    def mark_document_orphaned_if_current(
        self,
        document_id: str,
        *,
        transaction_id: str,
        reason: str,
    ) -> bool:
        """Mark an orphan only while this transaction still owns the manifest."""

        manifest_key = f"{self._document_prefix(document_id)}/manifest.json"
        state = self._get_object_state(manifest_key)
        if state is None:
            return False
        payload, etag = state
        manifest = _manifest_from_bytes(payload)
        if _manifest_transaction_id(manifest) != transaction_id:
            return False

        metadata = manifest.get("metadata")
        document_metadata = dict(metadata) if isinstance(metadata, dict) else {}
        now = datetime.now(UTC).isoformat()
        document_metadata.update(
            {
                "source_index_status": "orphaned",
                "source_index_reason": reason,
                "source_index_updated_at": now,
            }
        )
        manifest["metadata"] = document_metadata
        manifest["updated_at"] = now
        try:
            self._put_json(manifest_key, manifest, if_match=etag)
        except S3StorageError as error:
            if _is_precondition_failed_error(error.__cause__):
                return False
            raise
        self._invalidate_list_cache()
        return True

    def snapshot_document(self, document_id: str) -> dict[str, bytes] | None:
        """Capture an existing document prefix for rollback during a replacement write."""

        prefix = f"{self._document_prefix(document_id)}/"
        keys = self._list_keys(prefix)
        manifest_key = f"{prefix}manifest.json"
        if manifest_key not in keys:
            return None

        snapshot: dict[str, bytes] = {}
        for key in keys:
            payload = self._get_bytes(key)
            if payload is None:
                raise S3StorageError(operation="snapshot_document", key=key)
            snapshot[key] = payload
        return snapshot

    def restore_document(self, document_id: str, snapshot: dict[str, bytes]) -> None:
        """Republish a snapshot without deleting the current prefix first."""

        prefix = f"{self._document_prefix(document_id)}/"
        manifest_key = f"{prefix}manifest.json"
        manifest_payload = snapshot.get(manifest_key)
        if manifest_payload is None:
            raise S3StorageError(operation="restore_document", key=manifest_key)

        for key, payload in snapshot.items():
            if key == manifest_key:
                continue
            self._put_bytes(key, payload, content_type=_content_type_for_key(key))

        # Publish the restored view only after every referenced artifact is durable.
        self._put_bytes(
            manifest_key,
            manifest_payload,
            content_type=_content_type_for_key(manifest_key),
        )
        self._invalidate_list_cache()

    def restore_document_if_current(
        self,
        document_id: str,
        snapshot: dict[str, bytes],
        *,
        transaction_id: str,
    ) -> bool:
        """Restore a snapshot only if this transaction still owns the manifest."""

        prefix = f"{self._document_prefix(document_id)}/"
        manifest_key = f"{prefix}manifest.json"
        manifest_payload = snapshot.get(manifest_key)
        if manifest_payload is None:
            raise S3StorageError(operation="restore_document", key=manifest_key)

        state = self._get_object_state(manifest_key)
        if state is None:
            return False
        current_payload, etag = state
        current_manifest = _manifest_from_bytes(current_payload)
        if _manifest_transaction_id(current_manifest) != transaction_id:
            return False

        for key, payload in snapshot.items():
            if key != manifest_key:
                self._put_bytes(key, payload, content_type=_content_type_for_key(key))
        try:
            self._put_bytes(
                manifest_key,
                manifest_payload,
                content_type=_content_type_for_key(manifest_key),
                if_match=etag,
            )
        except S3StorageError as error:
            if _is_precondition_failed_error(error.__cause__):
                return False
            raise
        with contextlib.suppress(Exception):
            self.cleanup_transaction_stage(document_id, transaction_id=transaction_id)
        self._invalidate_list_cache()
        return True

    def snapshot_is_current(
        self,
        document_id: str,
        snapshot: dict[str, bytes],
    ) -> bool:
        """Return whether the canonical manifest still equals a prior snapshot."""

        manifest_key = f"{self._document_prefix(document_id)}/manifest.json"
        expected = snapshot.get(manifest_key)
        return expected is not None and self._get_bytes(manifest_key) == expected

    def transaction_is_current(self, document_id: str, *, transaction_id: str) -> bool:
        """Return whether a transaction currently owns the canonical manifest."""

        manifest = self._read_manifest(document_id)
        return _manifest_transaction_id(manifest) == transaction_id

    def read_stable_canonical_chunks(self, document_id: str) -> S3CanonicalChunks | None:
        """Read canonical chunks only when the manifest stays stable across the read."""

        manifest_key = f"{self._document_prefix(document_id)}/manifest.json"
        initial_state = self._get_object_state(manifest_key)
        if initial_state is None:
            return None
        manifest_payload, manifest_etag = initial_state
        manifest = _manifest_from_bytes(manifest_payload)
        chunks_key = _manifest_text(manifest, "chunks_key")
        if chunks_key is None:
            return None
        chunks_payload = self._get_bytes(chunks_key)
        if chunks_payload is None:
            return None
        if not self.canonical_manifest_matches(
            document_id,
            manifest_payload=manifest_payload,
            manifest_etag=manifest_etag,
        ):
            return None
        return S3CanonicalChunks(
            chunks=_chunks_from_jsonl(chunks_payload.decode()),
            manifest_payload=manifest_payload,
            manifest_etag=manifest_etag,
        )

    def canonical_manifest_matches(
        self,
        document_id: str,
        *,
        manifest_payload: bytes,
        manifest_etag: str,
    ) -> bool:
        """Check that the canonical manifest still matches a stable-read token."""

        manifest_key = f"{self._document_prefix(document_id)}/manifest.json"
        state = self._get_object_state(manifest_key)
        return state is not None and state == (manifest_payload, manifest_etag)

    def cleanup_transaction_stage(self, document_id: str, *, transaction_id: str) -> None:
        """Delete one transaction's stage unless its manifest is still active."""

        base_key = self._document_prefix(document_id)
        document_keys = self._list_keys(f"{base_key}/")
        manifest_key = f"{base_key}/manifest.json"
        if manifest_key in document_keys:
            manifest = self._read_manifest(document_id)
            if _manifest_transaction_id(manifest) == transaction_id:
                return
        version_prefix = f"{base_key}/versions/{_safe_s3_segment(transaction_id)}/"
        keys = [key for key in document_keys if key.startswith(version_prefix)]
        if keys:
            self._delete_keys(keys)

    def cleanup_snapshot_versions_if_current(
        self,
        document_id: str,
        snapshot: dict[str, bytes],
        *,
        transaction_id: str,
    ) -> bool:
        """Delete only prior manifest versions while this transaction remains current."""

        base_key = self._document_prefix(document_id)
        manifest_key = f"{base_key}/manifest.json"
        prior_manifest_payload = snapshot.get(manifest_key)
        if prior_manifest_payload is None:
            return False

        prior_manifest = _manifest_from_bytes(prior_manifest_payload)
        versions_prefix = f"{base_key}/versions/"
        prior_version_prefixes = _manifest_version_prefixes(
            prior_manifest,
            versions_prefix=versions_prefix,
        )
        current_version_prefix = f"{versions_prefix}{_safe_s3_segment(transaction_id)}/"
        prior_version_prefixes.discard(current_version_prefix)
        if not prior_version_prefixes:
            return self.transaction_is_current(
                document_id,
                transaction_id=transaction_id,
            )

        keys = self._list_keys(versions_prefix)
        stale_keys = [
            key for key in keys if any(key.startswith(prefix) for prefix in prior_version_prefixes)
        ]
        if not self.transaction_is_current(
            document_id,
            transaction_id=transaction_id,
        ):
            return False
        if stale_keys:
            self._delete_keys(stale_keys)
        return True

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
        raw_payload = self._get_bytes(key)
        if raw_payload is None:
            return None
        payload = json.loads(raw_payload.decode())
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

    def _put_json(
        self,
        key: str,
        payload: dict[str, object],
        *,
        if_match: str | None = None,
    ) -> None:
        self._put_bytes(
            key,
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode(),
            content_type="application/json; charset=utf-8",
            if_match=if_match,
        )

    def _put_bytes(
        self,
        key: str,
        payload: bytes,
        *,
        content_type: str,
        if_match: str | None = None,
    ) -> None:
        try:
            kwargs: dict[str, object] = {
                "Bucket": self._bucket,
                "Key": key,
                "Body": payload,
                "ContentType": content_type,
            }
            if if_match is not None:
                kwargs["IfMatch"] = if_match
            self._client.put_object(
                **kwargs,
            )
        except Exception as error:
            raise S3StorageError(operation="put_object", key=key) from error

    def _get_bytes(self, key: str) -> bytes | None:
        state = self._get_object_state(key)
        return state[0] if state is not None else None

    def _get_object_state(self, key: str) -> tuple[bytes, str] | None:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
            body = response["Body"]
            payload = body.read()
        except Exception as error:
            if _is_missing_s3_object_error(error):
                return None
            raise S3StorageError(operation="get_object", key=key) from error
        etag = response.get("ETag")
        normalized_etag = etag if isinstance(etag, str) and etag else _MISSING_ETAG_GUARD
        data = payload if isinstance(payload, bytes) else bytes(payload)
        return data, normalized_etag

    def _list_keys(self, prefix: str) -> list[str]:
        keys: list[str] = []
        continuation_token: str | None = None
        while True:
            kwargs = {"Bucket": self._bucket, "Prefix": prefix}
            if continuation_token is not None:
                kwargs["ContinuationToken"] = continuation_token
            try:
                response = self._client.list_objects_v2(**kwargs)
            except Exception as error:
                raise S3StorageError(operation="list_objects_v2", key=prefix) from error
            if not isinstance(response, dict):
                raise S3StorageError(operation="list_objects_v2", key=prefix) from None
            contents = response.get("Contents", [])
            if not isinstance(contents, list):
                raise S3StorageError(operation="list_objects_v2", key=prefix) from None
            if isinstance(contents, list):
                for item in contents:
                    key = item.get("Key") if isinstance(item, dict) else None
                    if not isinstance(key, str) or not key:
                        raise S3StorageError(operation="list_objects_v2", key=prefix) from None
                    keys.append(key)
            if not response.get("IsTruncated"):
                return keys
            raw_token = response.get("NextContinuationToken")
            if not isinstance(raw_token, str) or not raw_token:
                raise S3StorageError(operation="list_objects_v2", key=prefix) from None
            continuation_token = raw_token

    def _delete_keys(self, keys: list[str]) -> None:
        for start in range(0, len(keys), 1000):
            batch = keys[start : start + 1000]
            try:
                response = self._client.delete_objects(
                    Bucket=self._bucket,
                    Delete={"Objects": [{"Key": key} for key in batch]},
                )
            except Exception as error:
                raise S3StorageError(operation="delete_objects", key=batch[0]) from error
            if isinstance(response, dict) and response.get("Errors"):
                error_key = batch[0]
                raw_errors = response.get("Errors")
                if isinstance(raw_errors, list) and raw_errors:
                    raw_key = raw_errors[0].get("Key") if isinstance(raw_errors[0], dict) else None
                    if isinstance(raw_key, str) and raw_key:
                        error_key = raw_key
                raise S3StorageError(operation="delete_objects", key=error_key) from None


class PostgresLocalSourceStore:
    """Store local documents/chunks in Postgres while files remain on disk."""

    def __init__(self, *, connection: str, table_prefix: str = "local_rag") -> None:
        if not connection.strip():
            raise ValueError("Postgres source store requires a connection string.")
        self._documents_table = _safe_table_name(f"{table_prefix}_documents")
        self._chunks_table = _safe_table_name(f"{table_prefix}_chunks")
        from psycopg_pool import ConnectionPool

        self._pool = ConnectionPool(
            _psycopg_connection_string(connection),
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

    def snapshot_document(self, document_id: str) -> StoredSourceSnapshot | None:
        """Capture one document and its chunks before a replacement write."""

        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                select document_id, dataset_id, name, source_type, source,
                       raw_path, markdown_path, metadata
                from {self._documents_table}
                where document_id = %s
                """,
                (document_id,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        (
            stored_document_id,
            dataset_id,
            name,
            source_type,
            source,
            raw_path,
            markdown_path,
            metadata,
        ) = row
        return StoredSourceSnapshot(
            document_id=str(stored_document_id),
            dataset_id=str(dataset_id),
            name=str(name),
            source_type=str(source_type),
            source=str(source),
            raw_path=str(raw_path) if raw_path is not None else None,
            markdown_path=str(markdown_path) if markdown_path is not None else None,
            metadata=dict(metadata) if isinstance(metadata, dict) else {},
            chunks=self.read_chunks(document_id),
        )

    def restore_document(self, document_id: str, snapshot: StoredSourceSnapshot) -> None:
        """Restore a snapshot captured before a failed replacement write."""

        if snapshot.document_id != document_id:
            raise ValueError("Source snapshot document_id does not match restore target.")
        self.write_document(
            document_id=snapshot.document_id,
            dataset_id=snapshot.dataset_id,
            name=snapshot.name,
            source_type=snapshot.source_type,
            source=snapshot.source,
            raw_path=Path(snapshot.raw_path) if snapshot.raw_path is not None else None,
            markdown_path=Path(snapshot.markdown_path)
            if snapshot.markdown_path is not None
            else None,
            metadata=snapshot.metadata,
            chunks=snapshot.chunks,
        )

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
_S3_MISSING_OBJECT_CODES = frozenset({"404", "NoSuchKey", "NotFound"})
_MISSING_ETAG_GUARD = '"missing-etag-cannot-match"'


def _is_missing_s3_object_error(error: Exception) -> bool:
    response = getattr(error, "response", None)
    if not isinstance(response, dict):
        return False
    error_payload = response.get("Error")
    if not isinstance(error_payload, dict):
        return False
    code = error_payload.get("Code")
    return isinstance(code, str) and code in _S3_MISSING_OBJECT_CODES


def _is_precondition_failed_error(error: BaseException | None) -> bool:
    response = getattr(error, "response", None)
    if not isinstance(response, dict):
        return False
    error_payload = response.get("Error")
    if not isinstance(error_payload, dict):
        return False
    return error_payload.get("Code") in {"PreconditionFailed", "412"}


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


def _manifest_from_bytes(payload: bytes) -> dict[str, object]:
    manifest = json.loads(payload.decode())
    if not isinstance(manifest, dict):
        raise ValueError("S3 document manifest must be a JSON object.")
    return manifest


def _manifest_transaction_id(manifest: dict[str, object] | None) -> str | None:
    if manifest is None:
        return None
    return _manifest_text(manifest, "write_transaction_id")


def _manifest_version_prefixes(
    manifest: dict[str, object],
    *,
    versions_prefix: str,
) -> set[str]:
    prefixes: set[str] = set()
    for key_name in ("raw_key", "markdown_key", "chunks_key"):
        artifact_key = _manifest_text(manifest, key_name)
        if artifact_key is None or not artifact_key.startswith(versions_prefix):
            continue
        version, separator, _ = artifact_key.removeprefix(versions_prefix).partition("/")
        if version and separator:
            prefixes.add(f"{versions_prefix}{version}/")
    return prefixes


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


def _content_type_for_key(key: str) -> str:
    if key.endswith("/manifest.json"):
        return "application/json; charset=utf-8"
    if key.endswith("/chunks/chunks.jsonl"):
        return "application/x-ndjson; charset=utf-8"
    if key.endswith(".md"):
        return "text/markdown; charset=utf-8"
    if key.endswith(".pdf"):
        return "application/pdf"
    if key.endswith(".txt"):
        return "text/plain; charset=utf-8"
    return "application/octet-stream"


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
