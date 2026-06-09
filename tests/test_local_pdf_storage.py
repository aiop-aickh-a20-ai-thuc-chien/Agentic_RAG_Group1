import json
from pathlib import Path
from typing import Any

import pytest

from agentic_rag.core.contracts import Chunk
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
    ) -> None:
        self.objects: dict[str, bytes] = {}
        self.page_size = page_size
        self.omit_continuation_token = omit_continuation_token
        self.delete_batch_sizes: list[int] = []
        self.list_call_count = 0

    def put_object(self, *, Bucket: str, Key: str, Body: bytes | str, **_: object) -> None:
        self.objects[Key] = Body.encode() if isinstance(Body, str) else Body

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, object]:
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
        self.delete_batch_sizes.append(len(Delete["Objects"]))
        for item in Delete["Objects"]:
            self.objects.pop(str(item["Key"]), None)


class FakeBody:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload


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
    markdown_path.write_text("# Warranty\nPin VF8", encoding="utf-8", newline="\n")
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
    assert "sources/doc-1/manifest.json" in client.objects
    assert "sources/doc-1/chunks/chunks.jsonl" in client.objects


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

    with pytest.raises(RuntimeError, match="continuation token"):
        store.list_documents()
