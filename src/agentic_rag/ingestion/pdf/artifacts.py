"""Debug artifact persistence for PDF ingestion."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from agentic_rag.ingestion.pdf.loader import (
    _chunks_from_markdown,
    _safe_chunk_id_part,
    _validate_pdf_path,
)
from agentic_rag.ingestion.pdf.parser import DoclingMarkdownParser, PdfMarkdownParser

DEFAULT_PDF_ARTIFACT_ROOT = Path(__file__).resolve().parent / ".data" / "artifacts"


class _PdfArtifactModel(BaseModel):
    """Base config for PDF artifact metadata."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class PdfIngestionArtifactManifest(_PdfArtifactModel):
    """Metadata describing one persisted PDF ingestion artifact run."""

    artifact_schema_version: int = 1
    input_path: str
    parser: str
    run_id: str
    created_at: str
    artifact_root: str
    run_dir: str
    markdown_path: str
    chunks_path: str
    manifest_path: str
    chunk_count: int


def save_pdf_ingestion_artifacts(
    path: str,
    *,
    output_root: str | Path | None = None,
    run_id: str | None = None,
) -> PdfIngestionArtifactManifest:
    """Parse a PDF, chunk it, and save debug artifacts for evaluation."""

    return _save_pdf_ingestion_artifacts(
        Path(path),
        DoclingMarkdownParser(),
        output_root=output_root,
        run_id=run_id,
    )


def _save_pdf_ingestion_artifacts(
    path: Path,
    parser: PdfMarkdownParser,
    *,
    output_root: str | Path | None = None,
    run_id: str | None = None,
) -> PdfIngestionArtifactManifest:
    _validate_pdf_path(path)

    markdown = parser.parse_to_markdown(path)
    chunks = _chunks_from_markdown(path, markdown)

    artifact_root = Path(output_root) if output_root is not None else DEFAULT_PDF_ARTIFACT_ROOT
    resolved_run_id = _safe_run_id(run_id)
    run_dir = artifact_root / _safe_chunk_id_part(path.stem) / resolved_run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    markdown_path = run_dir / "parsed.md"
    chunks_path = run_dir / "chunks.jsonl"
    manifest_path = run_dir / "manifest.json"

    markdown_path.write_text(markdown, encoding="utf-8")
    with chunks_path.open("w", encoding="utf-8") as chunks_file:
        for chunk in chunks:
            chunks_file.write(json.dumps(chunk.model_dump(mode="json"), ensure_ascii=False))
            chunks_file.write("\n")

    manifest = PdfIngestionArtifactManifest(
        input_path=str(path),
        parser="docling",
        run_id=resolved_run_id,
        created_at=datetime.now(UTC).isoformat(),
        artifact_root=str(artifact_root),
        run_dir=str(run_dir),
        markdown_path=str(markdown_path),
        chunks_path=str(chunks_path),
        manifest_path=str(manifest_path),
        chunk_count=len(chunks),
    )
    manifest_path.write_text(
        json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def _safe_run_id(run_id: str | None) -> str:
    if run_id is None:
        return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return _safe_chunk_id_part(run_id)
