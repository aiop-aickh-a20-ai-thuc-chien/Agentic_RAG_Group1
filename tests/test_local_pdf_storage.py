import json
from pathlib import Path
from typing import Any

import pytest

from agentic_rag.core.contracts import Chunk
from agentic_rag.integrations.local_pdf import storage as storage_module
from agentic_rag.integrations.local_pdf.storage import (
    S3LocalSourceStore,
    _psycopg_connection_string,
)


class FakeS3Client:
    def __init__(
        self,
        *,
        page_size: int | None = None,
        omit_continuation_token: bool = False,
        get_errors: dict[str, Exception] | None = None,
        list_error: Exception | None = None,
        list_response: object | None = None,
        put_error: Exception | None = None,
        delete_error: Exception | None = None,
        delete_response_errors: list[dict[str, object]] | None = None,
    ) -> None:
        self.objects: dict[str, bytes] = {}
        self.page_size = page_size
        self.omit_continuation_token = omit_continuation_token
        self.get_errors = get_errors or {}
        self.list_error = list_error
        self.list_response = list_response
        self.put_error = put_error
        self.delete_error = delete_error
        self.delete_response_errors = delete_response_errors
        self.delete_batch_sizes: list[int] = []
        self.list_call_count = 0

    def put_object(self, *, Bucket: str, Key: str, Body: bytes | str, **_: object) -> None:
        if self.put_error is not None:
            raise self.put_error
        self.objects[Key] = Body.encode() if isinstance(Body, str) else Body

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
        if error := self.get_errors.get(Key):
            raise error
        if Key not in self.objects:
            raise KeyError(Key)
        return {"Body": FakeBody(self.objects[Key])}

    def list_objects_v2(
        self,
        *,
        Bucket: str,
        Prefix: str,
        ContinuationToken: str | None = None,
        **_: object,
    ) -> dict[str, object]:
        self.list_call_count += 1
        if self.list_error is not None:
            raise self.list_error
        if self.list_response is not None:
            return self.list_response  # type: ignore[return-value]
        keys = [key for key in sorted(self.objects) if key.startswith(Prefix)]
        start = int(ContinuationToken or 0)
        page_size = self.page_size or len(keys) or 1
        page = keys[start : start + page_size]
        next_start = start + len(page)
        response: dict[str, object] = {
            "Contents": [{"Key": key} for key in page],
            "IsTruncated": next_start < len(keys),
        }
        if next_start < len(keys) and not self.omit_continuation_token:
            response["NextContinuationToken"] = str(next_start)
        return response

    def delete_object(self, *, Bucket: str, Key: str) -> None:
        self.objects.pop(Key, None)

    def delete_objects(self, *, Bucket: str, Delete: dict[str, Any]) -> None:
        if self.delete_error is not None:
            raise self.delete_error
        if self.delete_response_errors is not None:
            return {"Errors": self.delete_response_errors}  # type: ignore[return-value]
        self.delete_batch_sizes.append(len(Delete["Objects"]))
        for item in Delete["Objects"]:
            self.objects.pop(str(item["Key"]), None)


class FakeBody:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload


class FakeS3ClientError(Exception):
    def __init__(self, code: str, status_code: int, detail: str = "SECRET") -> None:
        super().__init__(detail)
        self.response = {
            "Error": {"Code": code, "Message": detail},
            "ResponseMetadata": {"HTTPStatusCode": status_code},
        }


class FakeCredentialOrNetworkError(Exception):
    pass


def test_s3_storage_error_is_a_runtime_error() -> None:
    error_type = getattr(storage_module, "S3StorageError", object)

    assert issubclass(error_type, RuntimeError)


@pytest.mark.parametrize(
    "error",
    [
        FakeS3ClientError("NoSuchKey", 404),
        FakeS3ClientError("404", 404),
    ],
    ids=["no-such-key", "404-code"],
)
def test_s3_reads_treat_recognized_missing_manifest_as_missing(error: Exception) -> None:
    manifest_key = "sources/doc-1/manifest.json"
    client = FakeS3Client(get_errors={manifest_key: error})
    store = S3LocalSourceStore(bucket="rag-bucket", prefix="sources", client=client)

    assert store.read_chunks("doc-1") == []
    assert store.read_markdown("doc-1") == ""
    with pytest.raises(ValueError, match="Raw source file is not available"):
        store.read_raw("doc-1")


@pytest.mark.parametrize(
    "method_name, artifact_key, expected",
    [
        ("read_chunks", "sources/doc-1/chunks/chunks.jsonl", []),
        ("read_markdown", "sources/doc-1/parsed/document.md", ""),
        ("read_raw", "sources/doc-1/raw/source.pdf", ValueError),
    ],
)
def test_s3_reads_treat_recognized_missing_artifact_as_missing(
    method_name: str,
    artifact_key: str,
    expected: object,
) -> None:
    manifest_key = "sources/doc-1/manifest.json"
    client = FakeS3Client(get_errors={artifact_key: FakeS3ClientError("NoSuchKey", 404)})
    client.objects[manifest_key] = json.dumps(
        {
            "document_id": "doc-1",
            "name": "source.pdf",
            "source_type": "pdf",
            "chunks_key": "sources/doc-1/chunks/chunks.jsonl",
            "markdown_key": "sources/doc-1/parsed/document.md",
            "raw_key": "sources/doc-1/raw/source.pdf",
        }
    ).encode()
    store = S3LocalSourceStore(bucket="rag-bucket", prefix="sources", client=client)

    method = getattr(store, method_name)
    if isinstance(expected, type) and issubclass(expected, Exception):
        with pytest.raises(expected, match="Raw source file is not available"):
            method("doc-1")
    else:
        assert method("doc-1") == expected


@pytest.mark.parametrize(
    "error",
    [
        FakeS3ClientError("AccessDenied", 403),
        FakeCredentialOrNetworkError("missing credentials SECRET"),
        FakeCredentialOrNetworkError("partial credentials SECRET"),
        FakeS3ClientError("ExpiredToken", 400),
        FakeS3ClientError("PermanentRedirect", 301),
        FakeS3ClientError("NoSuchBucket", 404),
        FakeCredentialOrNetworkError("endpoint connection failed SECRET"),
    ],
    ids=[
        "access-denied",
        "missing-credentials",
        "partial-credentials",
        "expired-token",
        "wrong-region",
        "missing-bucket",
        "network-error",
    ],
)
def test_s3_manifest_read_wraps_operational_failures_without_secret_leakage(
    error: Exception,
) -> None:
    manifest_key = "sources/doc-1/manifest.json"
    client = FakeS3Client(get_errors={manifest_key: error})
    store = S3LocalSourceStore(bucket="rag-bucket", prefix="sources", client=client)

    with pytest.raises(storage_module.S3StorageError) as exc_info:
        store.read_chunks("doc-1")

    message = str(exc_info.value)
    assert "get_object" in message
    assert manifest_key in message
    assert "SECRET" not in message
    assert exc_info.value.__cause__ is error


@pytest.mark.parametrize(
    "method_name, artifact_key",
    [
        ("read_chunks", "sources/doc-1/chunks/chunks.jsonl"),
        ("read_markdown", "sources/doc-1/parsed/document.md"),
        ("read_raw", "sources/doc-1/raw/source.pdf"),
    ],
)
def test_s3_artifact_reads_do_not_suppress_access_denied(
    method_name: str,
    artifact_key: str,
) -> None:
    manifest_key = "sources/doc-1/manifest.json"
    client = FakeS3Client(get_errors={artifact_key: FakeS3ClientError("AccessDenied", 403)})
    client.objects[manifest_key] = json.dumps(
        {
            "document_id": "doc-1",
            "name": "source.pdf",
            "source_type": "pdf",
            "chunks_key": "sources/doc-1/chunks/chunks.jsonl",
            "markdown_key": "sources/doc-1/parsed/document.md",
            "raw_key": "sources/doc-1/raw/source.pdf",
        }
    ).encode()
    store = S3LocalSourceStore(bucket="rag-bucket", prefix="sources", client=client)

    with pytest.raises(storage_module.S3StorageError, match=artifact_key):
        getattr(store, method_name)("doc-1")


def test_s3_listing_wraps_operational_failures() -> None:
    error = FakeS3ClientError("AccessDenied", 403)
    client = FakeS3Client(list_error=error)
    store = S3LocalSourceStore(bucket="rag-bucket", prefix="sources", client=client)

    with pytest.raises(storage_module.S3StorageError) as exc_info:
        store.list_documents()

    assert "list_objects_v2" in str(exc_info.value)
    assert "sources/" in str(exc_info.value)
    assert "SECRET" not in str(exc_info.value)
    assert exc_info.value.__cause__ is error


def test_s3_document_listing_skips_only_missing_manifests() -> None:
    missing_key = "sources/doc-missing/manifest.json"
    denied_key = "sources/doc-denied/manifest.json"
    client = FakeS3Client(
        get_errors={
            missing_key: FakeS3ClientError("NoSuchKey", 404),
            denied_key: FakeS3ClientError("AccessDenied", 403),
        }
    )
    client.objects[missing_key] = b"{}"
    client.objects[denied_key] = b"{}"
    store = S3LocalSourceStore(bucket="rag-bucket", prefix="sources", client=client)

    with pytest.raises(storage_module.S3StorageError, match=denied_key):
        store.list_documents()


def test_psycopg_connection_string_accepts_sqlalchemy_psycopg_scheme() -> None:
    assert (
        _psycopg_connection_string("postgresql+psycopg://user:pass@example.com/db")
        == "postgresql://user:pass@example.com/db"
    )


def test_s3_source_store_persists_manifest_chunks_markdown_and_raw_file(
    tmp_path: Path,
) -> None:
    client = FakeS3Client()
    raw_path = tmp_path / "source.pdf"
    markdown_path = tmp_path / "source.md"
    raw_path.write_bytes(b"%PDF-1.4")
    markdown_path.write_text("# Warranty\nPin VF8", encoding="utf-8")
    chunk = Chunk(
        chunk_id="chunk-1",
        text="Pin VF8",
        metadata={"document_id": "doc-1", "storage_chunk_id": "doc-1:0001"},
    )
    store = S3LocalSourceStore(bucket="rag-bucket", prefix="sources", client=client)

    store.write_document(
        document_id="doc-1",
        dataset_id="local_pdf",
        name="warranty.pdf",
        source_type="pdf",
        source="warranty.pdf",
        raw_path=raw_path,
        markdown_path=markdown_path,
        metadata={"parser": "docling"},
        chunks=[chunk],
    )

    documents = store.list_documents()

    assert documents[0].document_id == "doc-1"
    assert documents[0].total_chunks == 1
    assert documents[0].metadata["parser"] == "docling"
    assert store.read_chunks("doc-1") == [chunk]
    assert store.read_all_chunks() == [chunk]
    assert store.read_chunks_for_documents(["doc-1"]) == [chunk]
    assert store.read_markdown("doc-1") == "# Warranty\nPin VF8"
    assert store.read_raw("doc-1").content == b"%PDF-1.4"
    assert store.read_raw("doc-1").content_type == "application/pdf"
    manifest = json.loads(client.objects["sources/doc-1/manifest.json"].decode())
    assert manifest["chunks_key"] in client.objects
    assert "/versions/" in manifest["chunks_key"]


def test_s3_source_store_marks_document_orphaned_without_delete(tmp_path: Path) -> None:
    client = FakeS3Client()
    raw_path = tmp_path / "source.txt"
    raw_path.write_text("source", encoding="utf-8")
    store = S3LocalSourceStore(bucket="rag-bucket", prefix="sources", client=client)
    store.write_document(
        document_id="doc-1",
        dataset_id="local_pdf",
        name="note.txt",
        source_type="text",
        source="note.txt",
        raw_path=raw_path,
        markdown_path=None,
        metadata={"parser": "text"},
        chunks=[],
    )

    store.mark_document_orphaned("doc-1", reason="qdrant_upsert_failed")

    manifest_key = "sources/doc-1/manifest.json"
    manifest = json.loads(client.objects[manifest_key].decode())
    assert manifest["document_id"] == "doc-1"
    assert manifest["name"] == "note.txt"
    assert manifest["metadata"]["parser"] == "text"
    assert manifest["metadata"]["source_index_status"] == "orphaned"
    assert manifest["metadata"]["source_index_reason"] == "qdrant_upsert_failed"
    assert isinstance(manifest["metadata"]["source_index_updated_at"], str)
    assert isinstance(manifest["updated_at"], str)
    assert client.delete_batch_sizes == []


def test_s3_source_store_wraps_operational_write_errors(tmp_path: Path) -> None:
    error = FakeS3ClientError("AccessDenied", 403)
    client = FakeS3Client(put_error=error)
    raw_path = tmp_path / "source.txt"
    raw_path.write_text("source", encoding="utf-8")
    store = S3LocalSourceStore(bucket="rag-bucket", prefix="sources", client=client)

    with pytest.raises(storage_module.S3StorageError) as exc_info:
        store.write_document(
            document_id="doc-1",
            dataset_id="local_pdf",
            name="note.txt",
            source_type="text",
            source="note.txt",
            raw_path=raw_path,
            markdown_path=None,
            metadata={},
            chunks=[],
        )

    assert "put_object" in str(exc_info.value)
    assert "sources/doc-1/versions/" in str(exc_info.value)
    assert "/raw/source.txt" in str(exc_info.value)
    assert "SECRET" not in str(exc_info.value)
    assert exc_info.value.__cause__ is error


def test_s3_source_store_cleanup_deletes_only_owned_transaction_stage(
    tmp_path: Path,
) -> None:
    client = FakeS3Client()
    raw_path = tmp_path / "source.txt"
    store = S3LocalSourceStore(bucket="rag-bucket", prefix="sources", client=client)

    raw_path.write_text("active", encoding="utf-8")
    store.write_document(
        document_id="doc-1",
        dataset_id="local_pdf",
        name="note.txt",
        source_type="text",
        source="note.txt",
        raw_path=raw_path,
        markdown_path=None,
        metadata={},
        chunks=[Chunk(chunk_id="chunk-1", text="active", metadata={})],
        transaction_id="active",
    )
    client.objects["sources/doc-1/versions/owned/chunks/chunks.jsonl"] = b"owned"
    client.objects["sources/doc-1/versions/concurrent/chunks/chunks.jsonl"] = b"concurrent"

    store.cleanup_transaction_stage("doc-1", transaction_id="owned")

    assert "sources/doc-1/versions/owned/chunks/chunks.jsonl" not in client.objects
    assert "sources/doc-1/versions/concurrent/chunks/chunks.jsonl" in client.objects
    assert store.read_chunks("doc-1")[0].text == "active"


def test_s3_source_store_post_commit_cleanup_preserves_concurrent_stage(
    tmp_path: Path,
) -> None:
    client = FakeS3Client()
    raw_path = tmp_path / "source.txt"
    store = S3LocalSourceStore(bucket="rag-bucket", prefix="sources", client=client)

    raw_path.write_text("prior", encoding="utf-8")
    store.write_document(
        document_id="doc-1",
        dataset_id="local_pdf",
        name="note.txt",
        source_type="text",
        source="note.txt",
        raw_path=raw_path,
        markdown_path=None,
        metadata={},
        chunks=[Chunk(chunk_id="chunk-1", text="prior", metadata={})],
        transaction_id="prior",
    )
    snapshot = store.snapshot_document("doc-1")
    assert snapshot is not None

    raw_path.write_text("current", encoding="utf-8")
    store.write_document(
        document_id="doc-1",
        dataset_id="local_pdf",
        name="note.txt",
        source_type="text",
        source="note.txt",
        raw_path=raw_path,
        markdown_path=None,
        metadata={},
        chunks=[Chunk(chunk_id="chunk-1", text="current", metadata={})],
        transaction_id="current",
    )
    concurrent_key = "sources/doc-1/versions/concurrent/chunks/chunks.jsonl"
    client.objects[concurrent_key] = b"concurrent"

    cleaned = store.cleanup_snapshot_versions_if_current(
        "doc-1",
        snapshot,
        transaction_id="current",
    )

    assert cleaned is True
    assert not any(key.startswith("sources/doc-1/versions/prior/") for key in client.objects)
    assert any(key.startswith("sources/doc-1/versions/current/") for key in client.objects)
    assert concurrent_key in client.objects
    assert store.read_chunks("doc-1")[0].text == "current"


def test_s3_restore_failure_preserves_current_prefix_and_can_be_retried(
    tmp_path: Path,
) -> None:
    client = FakeS3Client()
    raw_path = tmp_path / "source.txt"
    raw_path.write_text("original", encoding="utf-8")
    original_chunk = Chunk(chunk_id="chunk-1", text="original", metadata={})
    replacement_chunk = Chunk(chunk_id="chunk-1", text="replacement", metadata={})
    store = S3LocalSourceStore(bucket="rag-bucket", prefix="sources", client=client)
    store.write_document(
        document_id="doc-1",
        dataset_id="local_pdf",
        name="note.txt",
        source_type="text",
        source="note.txt",
        raw_path=raw_path,
        markdown_path=None,
        metadata={},
        chunks=[original_chunk],
    )
    snapshot = store.snapshot_document("doc-1")
    assert snapshot is not None

    raw_path.write_text("replacement", encoding="utf-8")
    store.write_document(
        document_id="doc-1",
        dataset_id="local_pdf",
        name="note.txt",
        source_type="text",
        source="note.txt",
        raw_path=raw_path,
        markdown_path=None,
        metadata={},
        chunks=[replacement_chunk],
    )
    before_failed_restore = dict(client.objects)
    client.put_error = FakeS3ClientError("AccessDenied", 403)

    with pytest.raises(storage_module.S3StorageError, match="put_object"):
        store.restore_document("doc-1", snapshot)

    assert client.objects == before_failed_restore
    assert client.delete_batch_sizes == []

    client.put_error = None
    store.restore_document("doc-1", snapshot)

    assert all(client.objects[key] == payload for key, payload in snapshot.items())
    assert store.read_chunks("doc-1") == [original_chunk]


def test_s3_source_store_deletes_one_document_prefix(tmp_path: Path) -> None:
    client = FakeS3Client()
    raw_path = tmp_path / "source.txt"
    raw_path.write_text("source", encoding="utf-8")
    store = S3LocalSourceStore(bucket="rag-bucket", prefix="sources", client=client)
    store.write_document(
        document_id="doc-1",
        dataset_id="local_pdf",
        name="note.txt",
        source_type="text",
        source="note.txt",
        raw_path=raw_path,
        markdown_path=None,
        metadata={},
        chunks=[],
    )

    store.delete_document("doc-1")

    assert not any(key.startswith("sources/doc-1/") for key in client.objects)


def test_s3_source_store_wraps_operational_delete_errors(tmp_path: Path) -> None:
    error = FakeS3ClientError("AccessDenied", 403)
    client = FakeS3Client(delete_error=error)
    raw_path = tmp_path / "source.txt"
    raw_path.write_text("source", encoding="utf-8")
    store = S3LocalSourceStore(bucket="rag-bucket", prefix="sources", client=client)
    store.write_document(
        document_id="doc-1",
        dataset_id="local_pdf",
        name="note.txt",
        source_type="text",
        source="note.txt",
        raw_path=raw_path,
        markdown_path=None,
        metadata={},
        chunks=[],
    )

    with pytest.raises(storage_module.S3StorageError) as exc_info:
        store.delete_document("doc-1")

    assert "delete_objects" in str(exc_info.value)
    assert "sources/doc-1/" in str(exc_info.value)
    assert "SECRET" not in str(exc_info.value)
    assert exc_info.value.__cause__ is error


def test_s3_source_store_wraps_delete_response_errors(tmp_path: Path) -> None:
    client = FakeS3Client(
        delete_response_errors=[{"Key": "sources/doc-1/raw/source.txt", "Code": "AccessDenied"}]
    )
    raw_path = tmp_path / "source.txt"
    raw_path.write_text("source", encoding="utf-8")
    store = S3LocalSourceStore(bucket="rag-bucket", prefix="sources", client=client)
    store.write_document(
        document_id="doc-1",
        dataset_id="local_pdf",
        name="note.txt",
        source_type="text",
        source="note.txt",
        raw_path=raw_path,
        markdown_path=None,
        metadata={},
        chunks=[],
    )

    with pytest.raises(storage_module.S3StorageError) as exc_info:
        store.delete_document("doc-1")

    assert "delete_objects" in str(exc_info.value)
    assert "sources/doc-1/raw/source.txt" in str(exc_info.value)


def test_s3_source_store_lists_documents_across_all_pages() -> None:
    client = FakeS3Client(page_size=1000)
    for index in range(1001):
        document_id = f"doc-{index:04d}"
        client.objects[f"sources/{document_id}/manifest.json"] = json.dumps(
            {
                "document_id": document_id,
                "dataset_id": "local_pdf",
                "name": f"{document_id}.txt",
                "source_type": "text",
                "source": f"{document_id}.txt",
                "total_chunks": 0,
                "metadata": {},
            }
        ).encode()
    store = S3LocalSourceStore(bucket="rag-bucket", prefix="sources", client=client)

    documents = store.list_documents()

    assert len(documents) == 1001
    assert {document.document_id for document in documents} == {
        f"doc-{index:04d}" for index in range(1001)
    }


def test_s3_source_store_deletes_paginated_prefix_in_s3_sized_batches() -> None:
    client = FakeS3Client(page_size=400)
    for index in range(1001):
        client.objects[f"sources/doc-1/artifacts/{index:04d}.json"] = b"{}"
    store = S3LocalSourceStore(bucket="rag-bucket", prefix="sources", client=client)

    store.delete_document("doc-1")

    assert not client.objects
    assert client.delete_batch_sizes == [1000, 1]


def test_s3_source_store_delete_all_lists_prefix_once() -> None:
    client = FakeS3Client(page_size=2)
    for index in range(3):
        client.objects[f"sources/doc-{index}/manifest.json"] = b"{}"
    store = S3LocalSourceStore(bucket="rag-bucket", prefix="sources", client=client)

    deleted_count = store.delete_all_documents()

    assert deleted_count == 3
    assert client.list_call_count == 2
    assert not client.objects


def test_s3_source_store_rejects_truncated_page_without_continuation_token() -> None:
    client = FakeS3Client(page_size=1, omit_continuation_token=True)
    client.objects["sources/doc-1/manifest.json"] = b"{}"
    client.objects["sources/doc-2/manifest.json"] = b"{}"
    store = S3LocalSourceStore(bucket="rag-bucket", prefix="sources", client=client)

    with pytest.raises(storage_module.S3StorageError, match="list_objects_v2"):
        store.list_documents()


@pytest.mark.parametrize(
    "list_response",
    [
        object(),
        {"Contents": "not-a-list", "IsTruncated": False},
        {"Contents": [{"Key": 123}], "IsTruncated": False},
        {"Contents": [{}], "IsTruncated": False},
    ],
)
def test_s3_source_store_wraps_malformed_list_response(list_response: object) -> None:
    client = FakeS3Client(list_response=list_response)
    store = S3LocalSourceStore(bucket="rag-bucket", prefix="sources", client=client)

    with pytest.raises(storage_module.S3StorageError) as exc_info:
        store.list_documents()

    assert "list_objects_v2" in str(exc_info.value)
    assert "sources/" in str(exc_info.value)
