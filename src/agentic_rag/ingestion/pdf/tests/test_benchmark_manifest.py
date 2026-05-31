from pathlib import Path

import pytest
from agentic_rag.ingestion.pdf.benchmarking.manifest import (
    DEFAULT_MANIFEST_PATH,
    PdfBenchmarkDocument,
    PdfBenchmarkManifest,
    load_pdf_benchmark_manifest,
    resolve_pdf_download_path,
)
from pydantic import ValidationError


def test_default_manifest_uses_public_vietnamese_sources() -> None:
    manifest = load_pdf_benchmark_manifest(DEFAULT_MANIFEST_PATH)

    assert manifest.version == 1
    assert manifest.download_dir == Path("src/agentic_rag/ingestion/pdf/.data/raw")
    assert len(manifest.documents) >= 6
    assert {document.domain for document in manifest.documents} >= {
        "government_legal",
        "academic_stem",
        "business_report",
        "education_admin",
    }
    assert all(document.language == "vi" for document in manifest.documents)
    assert all(
        document.source_url.startswith(("https://", "http://")) for document in manifest.documents
    )
    assert all(document.expected_features for document in manifest.documents)


def test_pdf_download_paths_stay_inside_pdf_module_data_dir() -> None:
    manifest = load_pdf_benchmark_manifest(DEFAULT_MANIFEST_PATH)
    document = manifest.documents[0]

    download_path = resolve_pdf_download_path(document, manifest, repo_root=Path("/repo"))

    assert download_path == (
        Path("/repo/src/agentic_rag/ingestion/pdf/.data/raw") / f"{document.doc_id}.pdf"
    )


def test_manifest_rejects_duplicate_document_ids() -> None:
    document = PdfBenchmarkDocument(
        doc_id="duplicate",
        title="Duplicate sample",
        domain="government_legal",
        language="vi",
        source_url="https://example.com/document.pdf",
        licensing_note="URL reference only.",
        expected_features=["vietnamese_diacritics"],
        expected_snippets=["Cộng hòa xã hội chủ nghĩa Việt Nam"],
    )

    with pytest.raises(ValidationError, match="duplicate doc_id"):
        PdfBenchmarkManifest(
            version=1,
            download_dir=Path("src/agentic_rag/ingestion/pdf/.data/raw"),
            documents=[document, document],
        )


def test_manifest_rejects_download_directory_outside_pdf_module() -> None:
    with pytest.raises(ValidationError, match="inside src/agentic_rag/ingestion/pdf"):
        PdfBenchmarkManifest(
            version=1,
            download_dir=Path("data/benchmarks/pdf_parser/raw"),
            documents=[],
        )
