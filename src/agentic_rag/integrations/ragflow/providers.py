"""RAGFlow providers that expose separate chunk and retrieval boundaries."""

from __future__ import annotations

import re
from dataclasses import dataclass

from agentic_rag.core.contracts import Chunk, SearchResult
from agentic_rag.integrations.ragflow.adapters import (
    chunk_from_ragflow_payload,
    search_result_from_ragflow_hit,
)
from agentic_rag.integrations.ragflow.client import RAGFlowClient


@dataclass(frozen=True)
class RAGFlowUploadedDocument:
    """Normalized upload result returned to the UI/API layer."""

    document_id: str
    name: str
    dataset_id: str
    parse_started: bool
    trace: dict[str, object] | None = None


@dataclass(frozen=True)
class RAGFlowDocumentChunks:
    """One page of normalized chunks plus RAGFlow's full chunk count."""

    chunks: list[Chunk]
    total_chunks: int


class RAGFlowEvidenceProvider:
    """Use RAGFlow for ingestion/chunk/retrieval while keeping local generation."""

    def __init__(self, client: RAGFlowClient, *, dataset_id: str) -> None:
        self._client = client
        self._dataset_id = dataset_id

    def upload_document(
        self,
        *,
        filename: str,
        content: bytes,
        content_type: str | None = None,
        start_parse: bool = True,
    ) -> RAGFlowUploadedDocument:
        """Upload a document and optionally start RAGFlow parsing/chunking."""

        raw_document = self._client.upload_document(
            filename=filename,
            content=content,
            content_type=content_type,
            dataset_id=self._dataset_id,
        )
        document_id = _required_text(raw_document, "id")
        parse_started = False
        if start_parse:
            self._client.parse_documents(
                document_ids=[document_id],
                dataset_id=self._dataset_id,
            )
            parse_started = True

        return RAGFlowUploadedDocument(
            document_id=document_id,
            name=_optional_text(raw_document, "name") or filename,
            dataset_id=_optional_text(raw_document, "dataset_id") or self._dataset_id,
            parse_started=parse_started,
        )

    def import_url_document(
        self,
        *,
        url: str,
        start_parse: bool = True,
    ) -> RAGFlowUploadedDocument:
        """Let RAGFlow fetch a URL, then index the parsed markdown in the dataset."""

        raw_attachment = self._client.upload_runtime_url(url=url)
        attachment_id = _required_text(raw_attachment, "id")
        parsed_markdown = self._client.download_runtime_attachment(
            attachment_id=attachment_id,
            ext="markdown",
        )
        if not parsed_markdown.strip():
            raise ValueError("RAGFlow parsed the URL but returned empty markdown.")

        filename = _markdown_filename(_optional_text(raw_attachment, "name") or url)
        content = _markdown_with_source_url(url=url, parsed_markdown=parsed_markdown)
        return self.upload_document(
            filename=filename,
            content=content,
            content_type="text/markdown; charset=utf-8",
            start_parse=start_parse,
        )

    def list_document_chunks(
        self,
        *,
        document_id: str,
        page: int = 1,
        page_size: int | None = None,
        keywords: str | None = None,
    ) -> list[Chunk]:
        """Return RAGFlow chunks normalized to the shared `Chunk` contract."""

        return self.document_chunks(
            document_id=document_id,
            page=page,
            page_size=page_size,
            keywords=keywords,
        ).chunks

    def document_chunks(
        self,
        *,
        document_id: str,
        page: int = 1,
        page_size: int | None = None,
        keywords: str | None = None,
    ) -> RAGFlowDocumentChunks:
        """Return normalized chunks and the full chunk count for one document."""

        payload = self._client.list_chunks(
            document_id=document_id,
            dataset_id=self._dataset_id,
            keywords=keywords,
            page=page,
            page_size=page_size,
        )
        data = payload.get("data")
        if not isinstance(data, dict):
            return RAGFlowDocumentChunks(chunks=[], total_chunks=0)

        raw_doc = data.get("doc")
        doc_metadata = _document_metadata(raw_doc)
        raw_chunks = data.get("chunks")
        if not isinstance(raw_chunks, list):
            total_chunks = _chunk_count_from_payload(data=data, raw_doc=raw_doc, fallback=0)
            return RAGFlowDocumentChunks(chunks=[], total_chunks=total_chunks)

        chunks: list[Chunk] = []
        for raw_chunk in raw_chunks:
            if not isinstance(raw_chunk, dict):
                continue
            merged_payload = {**raw_chunk, "metadata": {**doc_metadata, **raw_chunk}}
            chunks.append(chunk_from_ragflow_payload(merged_payload))

        total_chunks = _chunk_count_from_payload(
            data=data,
            raw_doc=raw_doc,
            fallback=len(chunks),
        )
        return RAGFlowDocumentChunks(chunks=chunks, total_chunks=total_chunks)

    def retrieve(
        self,
        *,
        question: str,
        document_ids: list[str] | None = None,
        page_size: int | None = None,
    ) -> list[SearchResult]:
        """Retrieve evidence chunks from RAGFlow without using RAGFlow chat generation."""

        payload = self._client.retrieve(
            question=question,
            dataset_ids=[self._dataset_id],
            document_ids=document_ids,
            page_size=page_size,
        )
        data = payload.get("data")
        if not isinstance(data, dict):
            return []

        doc_names = _document_names_by_id(data.get("doc_aggs"))
        raw_chunks = data.get("chunks")
        if not isinstance(raw_chunks, list):
            return []

        results: list[SearchResult] = []
        for rank, raw_chunk in enumerate(raw_chunks, start=1):
            if not isinstance(raw_chunk, dict):
                continue
            source = doc_names.get(_optional_text(raw_chunk, "document_id") or "")
            metadata = {
                "source": source,
                "document_name": source,
                "dataset_id": self._dataset_id,
                **raw_chunk,
            }
            results.append(
                search_result_from_ragflow_hit(
                    {**raw_chunk, "metadata": metadata},
                    rank=rank,
                    retriever="ragflow",
                )
            )
        return results


def _required_text(payload: dict[str, object], key: str) -> str:
    value = _optional_text(payload, key)
    if not value:
        raise ValueError(f"RAGFlow payload is missing required field: {key}")
    return value


def _optional_text(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _optional_int(payload: dict[str, object], key: str) -> int | None:
    value = payload.get(key)
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, float) and value.is_integer():
        return max(int(value), 0)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _chunk_count_from_payload(
    *,
    data: dict[str, object],
    raw_doc: object,
    fallback: int,
) -> int:
    for key in ("total", "total_chunks", "chunk_count"):
        value = _optional_int(data, key)
        if value is not None:
            return value

    if isinstance(raw_doc, dict):
        for key in ("chunk_count", "chunk_num", "total_chunks"):
            value = _optional_int(raw_doc, key)
            if value is not None:
                return value

    return fallback


def _document_metadata(raw_doc: object) -> dict[str, object]:
    if not isinstance(raw_doc, dict):
        return {}

    name = _optional_text(raw_doc, "name") or _optional_text(raw_doc, "location")
    metadata: dict[str, object] = {
        "document_id": raw_doc.get("id"),
        "dataset_id": raw_doc.get("dataset_id") or raw_doc.get("knowledgebase_id"),
        "source": name,
        "document_name": name,
        "file_name": name,
        "source_type": "ragflow",
    }
    return {key: value for key, value in metadata.items() if value is not None}


def _document_names_by_id(raw_doc_aggs: object) -> dict[str, str]:
    if not isinstance(raw_doc_aggs, list):
        return {}

    names: dict[str, str] = {}
    for raw_doc in raw_doc_aggs:
        if not isinstance(raw_doc, dict):
            continue
        doc_id = _optional_text(raw_doc, "doc_id")
        doc_name = _optional_text(raw_doc, "doc_name")
        if doc_id and doc_name:
            names[doc_id] = doc_name
    return names


def _markdown_filename(name: str) -> str:
    stem = name.rsplit(".", 1)[0]
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem.strip()).strip("-._")
    if not stem:
        stem = "ragflow-url-source"
    return f"{stem[:96]}.md"


def _markdown_with_source_url(*, url: str, parsed_markdown: bytes) -> bytes:
    if parsed_markdown.startswith(b"Source URL:"):
        return parsed_markdown
    return f"Source URL: {url}\n\n".encode() + parsed_markdown
