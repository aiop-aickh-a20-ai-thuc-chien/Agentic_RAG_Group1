"""Manifest models for the Vietnamese public-PDF parser benchmark."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PDF_MODULE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[5]
PDF_MODULE_RELATIVE_ROOT = Path("src/agentic_rag/ingestion/pdf")
DEFAULT_MANIFEST_PATH = PDF_MODULE_ROOT / "benchmarking/manifest.json"
_DOC_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")


class _BenchmarkModel(BaseModel):
    """Shared strict configuration for PDF benchmark metadata."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class PdfBenchmarkDocument(_BenchmarkModel):
    """A public Vietnamese PDF candidate used to benchmark parser quality."""

    doc_id: str
    title: str
    domain: str
    language: str = "vi"
    source_url: str
    licensing_note: str
    expected_features: list[str]
    expected_snippets: list[str] = Field(default_factory=list)
    review_notes: list[str] = Field(default_factory=list)

    @field_validator("doc_id")
    @classmethod
    def validate_doc_id(cls, value: str) -> str:
        if not _DOC_ID_PATTERN.fullmatch(value):
            raise ValueError("doc_id must be lowercase snake_case")
        return value

    @field_validator("source_url")
    @classmethod
    def validate_source_url(cls, value: str) -> str:
        if not value.startswith(("https://", "http://")):
            raise ValueError("source_url must be an HTTP(S) URL")
        return value

    @field_validator("expected_features")
    @classmethod
    def validate_expected_features(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("expected_features must not be empty")
        return value


class PdfBenchmarkManifest(_BenchmarkModel):
    """Collection of public PDF references and PDF-local benchmark settings."""

    version: int
    download_dir: Path
    documents: list[PdfBenchmarkDocument]

    @field_validator("download_dir")
    @classmethod
    def validate_download_dir(cls, value: Path) -> Path:
        if value.is_absolute() or ".." in value.parts:
            raise ValueError(
                "download_dir must be a relative path inside src/agentic_rag/ingestion/pdf"
            )
        if not value.is_relative_to(PDF_MODULE_RELATIVE_ROOT):
            raise ValueError("download_dir must stay inside src/agentic_rag/ingestion/pdf")
        return value

    @model_validator(mode="after")
    def validate_unique_doc_ids(self) -> Self:
        seen: set[str] = set()
        duplicates: set[str] = set()
        for document in self.documents:
            if document.doc_id in seen:
                duplicates.add(document.doc_id)
            seen.add(document.doc_id)
        if duplicates:
            duplicate_list = ", ".join(sorted(duplicates))
            raise ValueError(f"duplicate doc_id values: {duplicate_list}")
        return self


def load_pdf_benchmark_manifest(path: str | Path = DEFAULT_MANIFEST_PATH) -> PdfBenchmarkManifest:
    """Load and validate the PDF-local public benchmark manifest."""

    manifest_path = Path(path)
    raw_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return PdfBenchmarkManifest.model_validate(raw_manifest)


def resolve_pdf_download_path(
    document: PdfBenchmarkDocument,
    manifest: PdfBenchmarkManifest,
    *,
    repo_root: Path = REPO_ROOT,
) -> Path:
    """Return the ignored local file path for a benchmark PDF."""

    return repo_root / manifest.download_dir / f"{document.doc_id}.pdf"
