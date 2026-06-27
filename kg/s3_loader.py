"""Read already-chunked documents FROM S3 into kg.schema.Document.

READ-ONLY: this module only calls list_objects_v2 + get_object. It NEVER writes
to S3 (no put/delete). Greenfield (boto3 only, no dependency on existing code).

S3 layout (as written by the project's source store):
    {prefix}{document_id}/manifest.json
    {prefix}{document_id}/chunks/chunks.jsonl     # one Chunk JSON per line

Env: AWS_S3_BUCKET, AWS_S3_PREFIX + standard AWS creds
     (AWS_PROFILE or AWS_ACCESS_KEY_ID/SECRET, AWS_DEFAULT_REGION).
"""

from __future__ import annotations

import json
import os

from kg.schema import Chunk, Document


def _s3_client():
    import boto3
    from botocore.config import Config

    return boto3.client("s3", config=Config(max_pool_connections=50))


def _norm_prefix(p: str) -> str:
    p = (p or "").strip().strip("/")
    return f"{p}/" if p else ""


def _list_chunk_keys(client, bucket: str, prefix: str) -> list[str]:
    """List every '<doc>/chunks/chunks.jsonl' key under the prefix (read-only)."""
    keys: list[str] = []
    token: str | None = None
    while True:
        kwargs = {"Bucket": bucket, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        resp = client.list_objects_v2(**kwargs)
        for item in resp.get("Contents", []):
            key = item.get("Key", "")
            if key.endswith("/chunks/chunks.jsonl"):
                keys.append(key)
        if not resp.get("IsTruncated"):
            break
        token = resp.get("NextContinuationToken")
        if not token:
            break
    return sorted(keys)


_DEDUP_KEY = "deduplication"


def _dedup_drop_layers() -> set[str]:
    """Which dedup layers to EXCLUDE. Default = exact (L1) only; near-dups (simhash,
    embedding_similarity) are kept since they may carry unique info."""
    raw = os.getenv("KG_DEDUP_LAYERS", "exact_sha256")
    return {x.strip() for x in raw.split(",") if x.strip()}


def _passes_dedup(d: dict, drop_layers: set[str]) -> bool:
    """Keep a chunk unless it is flagged a duplicate at one of `drop_layers`.

    The dedup result lives in chunk metadata: only the DUPLICATE side carries
    `deduplication`; canonical/unique chunks have no such key (so they pass). If a
    corpus was never deduped, no key is present and everything passes (graceful)."""
    meta = d.get("metadata") or {}
    dd = meta.get(_DEDUP_KEY)
    if not dd or not dd.get("has_duplicate"):
        return True
    return not (set(dd.get("detected_layers", [])) & drop_layers)


def _chunk_from_json(d: dict, fallback_doc: str) -> Chunk:
    meta = d.get("metadata") or {}
    doc_id = str(meta.get("document_id") or fallback_doc)
    section_path = meta.get("section_path") or []
    heading = meta.get("heading") or meta.get("section")
    return Chunk(
        doc_id=doc_id,
        chunk_id=str(d.get("chunk_id") or ""),
        text=str(d.get("text") or ""),
        section_path=tuple(str(x) for x in section_path),
        heading=str(heading) if heading else None,
    )


def load_documents_from_s3(
    bucket: str | None = None,
    prefix: str | None = None,
    limit: int | None = None,
    client=None,
) -> list[Document]:
    """Return Documents read from S3. `limit` = max number of documents (small slice)."""
    bucket = (bucket or os.getenv("AWS_S3_BUCKET", "")).strip()
    if not bucket:
        raise ValueError("AWS_S3_BUCKET is not set.")
    prefix = _norm_prefix(prefix if prefix is not None else os.getenv("AWS_S3_PREFIX", ""))
    client = client or _s3_client()

    keys = _list_chunk_keys(client, bucket, prefix)
    if limit:
        keys = keys[:limit]

    drop_layers = _dedup_drop_layers()
    documents: list[Document] = []
    seen = dropped = 0
    for key in keys:
        rel = key[len(prefix) :] if prefix and key.startswith(prefix) else key
        fallback_doc = rel.split("/chunks/")[0]
        body = client.get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8")
        records = [json.loads(line) for line in body.splitlines() if line.strip()]
        seen += len(records)
        kept = [d for d in records if _passes_dedup(d, drop_layers)]
        dropped += len(records) - len(kept)
        chunks = [_chunk_from_json(d, fallback_doc) for d in kept]
        if chunks:
            documents.append(Document(doc_id=chunks[0].doc_id, title=fallback_doc, chunks=chunks))
    if dropped:
        print(f"[dedup] skipped {dropped}/{seen} duplicate chunks (layers={sorted(drop_layers)})")
    return documents
