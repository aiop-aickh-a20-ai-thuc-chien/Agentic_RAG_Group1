"""Small HTTP client for RAGFlow document, chunk, and retrieval APIs."""

from __future__ import annotations

import json
import mimetypes
import uuid
from collections.abc import Mapping
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from agentic_rag.integrations.ragflow.config import RAGFlowConfig

JsonObject = dict[str, Any]


class RAGFlowClientError(RuntimeError):
    """Raised when RAGFlow returns a non-successful response."""


class RAGFlowClient:
    """HTTP wrapper over the RAGFlow APIs needed by the local pipeline."""

    def __init__(self, config: RAGFlowConfig) -> None:
        self._config = config

    def upload_document(
        self,
        *,
        filename: str,
        content: bytes,
        content_type: str | None = None,
        dataset_id: str | None = None,
    ) -> JsonObject:
        """Upload one document to a dataset and return the created document payload."""

        target_dataset_id = dataset_id or self._config.dataset_id
        body, boundary = _multipart_file_body(
            field_name="file",
            filename=filename,
            content=content,
            content_type=content_type or _guess_content_type(filename),
        )
        payload = self._request(
            "POST",
            f"/api/v1/datasets/{target_dataset_id}/documents",
            body=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        documents = _extract_payload_list(payload, "data")
        if not documents:
            raise RAGFlowClientError("RAGFlow upload response did not include a document.")
        return documents[0]

    def parse_documents(
        self,
        *,
        document_ids: list[str],
        dataset_id: str | None = None,
    ) -> JsonObject:
        """Start RAGFlow parsing/chunking for uploaded documents."""

        target_dataset_id = dataset_id or self._config.dataset_id
        return self._request_json(
            "POST",
            f"/api/v1/datasets/{target_dataset_id}/chunks",
            {"document_ids": document_ids},
        )

    def list_chunks(
        self,
        *,
        document_id: str,
        dataset_id: str | None = None,
        keywords: str | None = None,
        page: int = 1,
        page_size: int | None = None,
        chunk_id: str | None = None,
    ) -> JsonObject:
        """Return raw RAGFlow chunks for one document."""

        target_dataset_id = dataset_id or self._config.dataset_id
        query: dict[str, object] = {
            "page": page,
            "page_size": page_size or self._config.page_size,
        }
        if keywords:
            query["keywords"] = keywords
        if chunk_id:
            query["id"] = chunk_id

        return self._request_json(
            "GET",
            f"/api/v1/datasets/{target_dataset_id}/documents/{document_id}/chunks",
            query=query,
        )

    def retrieve(
        self,
        *,
        question: str,
        dataset_ids: list[str] | None = None,
        document_ids: list[str] | None = None,
        page: int = 1,
        page_size: int | None = None,
    ) -> JsonObject:
        """Retrieve raw RAGFlow chunks without asking RAGFlow to generate an answer."""

        body: JsonObject = {
            "question": question,
            "dataset_ids": dataset_ids or [self._config.dataset_id],
            "page": page,
            "page_size": page_size or self._config.page_size,
            "similarity_threshold": self._config.similarity_threshold,
            "vector_similarity_weight": self._config.vector_similarity_weight,
            "top_k": self._config.top_k,
            "keyword": self._config.keyword,
        }
        if document_ids:
            body["document_ids"] = document_ids

        return self._request_json("POST", "/api/v1/retrieval", body)

    def _request_json(
        self,
        method: str,
        path: str,
        body: Mapping[str, object] | None = None,
        *,
        query: Mapping[str, object] | None = None,
    ) -> JsonObject:
        request_body: bytes | None = None
        headers: dict[str, str] = {}
        if method != "GET" and body is not None:
            request_body = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        if query:
            path = f"{path}?{urlencode(query)}"

        return self._request(method, path, body=request_body, headers=headers)

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> JsonObject:
        request_headers = {
            "Authorization": f"Bearer {self._config.api_key}",
            **dict(headers or {}),
        }
        request = Request(
            f"{self._config.base_url}{path}",
            data=body,
            headers=request_headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=self._config.timeout_seconds) as response:
                raw = response.read().decode()
        except HTTPError as exc:
            message = exc.read().decode(errors="replace")
            raise RAGFlowClientError(f"RAGFlow HTTP {exc.code}: {message}") from exc
        except URLError as exc:
            raise RAGFlowClientError(f"Cannot connect to RAGFlow: {exc.reason}") from exc

        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            raise RAGFlowClientError("RAGFlow returned non-JSON response.") from exc

        if not isinstance(payload, dict):
            raise RAGFlowClientError("RAGFlow returned an unexpected response shape.")

        code = payload.get("code")
        if code not in (None, 0):
            message = payload.get("message", "unknown error")
            raise RAGFlowClientError(f"RAGFlow error {code}: {message}")

        return payload


def _multipart_file_body(
    *,
    field_name: str,
    filename: str,
    content: bytes,
    content_type: str,
) -> tuple[bytes, str]:
    boundary = f"----agentic-rag-{uuid.uuid4().hex}"
    lines = [
        f"--{boundary}\r\n".encode(),
        (
            f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
        ).encode(),
        f"Content-Type: {content_type}\r\n\r\n".encode(),
        content,
        b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ]
    return b"".join(lines), boundary


def _guess_content_type(filename: str) -> str:
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


def _extract_payload_list(payload: Mapping[str, object], key: str) -> list[JsonObject]:
    value = payload.get(key)
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return [value]
    return []
