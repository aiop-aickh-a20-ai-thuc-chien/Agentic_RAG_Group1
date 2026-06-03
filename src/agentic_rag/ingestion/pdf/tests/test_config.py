from pytest import MonkeyPatch

from agentic_rag.ingestion.pdf.config import PdfIngestionConfig


def test_pdf_ingestion_config_defaults_to_docling_and_deterministic() -> None:
    config = PdfIngestionConfig()

    assert config.parser_name == "docling"
    assert config.chunker_name == "deterministic"


def test_pdf_ingestion_config_reads_parser_and_chunker_from_env(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCAL_PDF_PARSER", "docling")
    monkeypatch.setenv("LOCAL_PDF_CHUNKER", "docling-hybrid")

    config = PdfIngestionConfig.from_env()

    assert config.parser_name == "docling"
    assert config.chunker_name == "docling-hybrid"
