"""Atomic change tracking, versioned snapshots, and failed-URL logging."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from agentic_rag.core.contracts import Chunk


def content_hash(data: object) -> str:
    """Hash canonical JSON so key ordering cannot create false changes."""

    encoded = json.dumps(
        _json_value(data), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class ChangeStore:
    """Persist hashes and snapshots, returning whether re-ingestion is needed."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.hash_path = self.root / "hashes.json"

    def record(self, key: str, data: object, *, captured_at: datetime | None = None) -> bool:
        digest = content_hash(data)
        hashes = self._load_hashes()
        if hashes.get(key) == digest:
            return False
        hashes[key] = digest
        self.root.mkdir(parents=True, exist_ok=True)
        _atomic_json_write(self.hash_path, hashes)
        timestamp = captured_at or datetime.now(UTC)
        safe_key = re.sub(r"[^a-zA-Z0-9_-]+", "_", key).strip("_") or "snapshot"
        snapshot = self.root / f"{safe_key}_{timestamp:%Y-%m-%d}.json"
        _atomic_json_write(snapshot, _json_value(data))
        return True

    def has_changed(self, key: str, data: object) -> bool:
        """Check a digest without advancing state before an external write succeeds."""

        return self._load_hashes().get(key) != content_hash(data)

    def _load_hashes(self) -> dict[str, str]:
        if not self.hash_path.exists():
            return {}
        try:
            value = json.loads(self.hash_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(value, dict):
            return {}
        return {str(key): str(digest) for key, digest in value.items()}


class FailedUrlLog:
    """Append machine-readable terminal crawl failures to JSONL."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append(self, url: str, reason: str, *, failed_at: datetime | None = None) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "url": url,
            "reason": reason,
            "failed_at": (failed_at or datetime.now(UTC)).isoformat(),
        }
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")


def upsert_changed_chunks(
    chunks: list[Chunk],
    change_store: ChangeStore,
    *,
    writer: Callable[[list[Chunk]], dict[str, object]] | None = None,
) -> dict[str, object]:
    """Gate persistent vector writes on stable chunk content hashes."""

    changed = [chunk for chunk in chunks if change_store.has_changed(chunk.chunk_id, chunk.text)]
    if writer is None:
        from agentic_rag.retrieval.search import upsert_dense_embeddings

        writer = upsert_dense_embeddings
    if not changed:
        return {"enabled": True, "chunk_count": 0, "skipped": len(chunks)}
    trace = writer(changed)
    for chunk in changed:
        change_store.record(chunk.chunk_id, chunk.text)
    return {**trace, "skipped": len(chunks) - len(changed)}


def _atomic_json_write(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _json_value(value: object) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_value(item) for item in value]
    return value
