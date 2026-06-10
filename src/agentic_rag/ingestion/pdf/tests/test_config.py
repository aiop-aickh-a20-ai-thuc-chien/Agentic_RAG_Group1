from pytest import MonkeyPatch

from agentic_rag.ingestion.pdf.config import PdfIngestionConfig


def test_pdf_ingestion_config_defaults_to_ocr_docling_deterministic() -> None:
    config = PdfIngestionConfig()

    assert config.pipeline_name == "ocr"
    assert config.strategy_name == "docling"
    assert config.parser_name == "docling"
    assert config.chunker_name == "deterministic"


def test_pdf_ingestion_config_accepts_legacy_parser_constructor_arg() -> None:
    config = PdfIngestionConfig(parser_name="docling", chunker_name="deterministic")

    assert config.pipeline_name == "ocr"
    assert config.strategy_name == "docling"
    assert config.parser_name == "docling"
    assert config.chunker_name == "deterministic"


def test_pdf_ingestion_config_reads_pipeline_strategy_and_chunker_from_env(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("LOCAL_PDF_PIPELINE", "vlm")
    monkeypatch.setenv("LOCAL_PDF_STRATEGY", "mineru")
    monkeypatch.setenv("LOCAL_PDF_CHUNKER", "docling-hybrid")

    config = PdfIngestionConfig.from_env()

    assert config.pipeline_name == "vlm"
    assert config.strategy_name == "mineru"
    assert config.parser_name == "mineru"
    assert config.chunker_name == "docling-hybrid"


def test_pdf_ingestion_config_keeps_legacy_parser_env(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.delenv("LOCAL_PDF_PIPELINE", raising=False)
    monkeypatch.delenv("LOCAL_PDF_STRATEGY", raising=False)
    monkeypatch.setenv("LOCAL_PDF_PARSER", "docling")
    monkeypatch.setenv("LOCAL_PDF_CHUNKER", "deterministic")

    config = PdfIngestionConfig.from_env()

    assert config.pipeline_name == "ocr"
    assert config.strategy_name == "docling"
    assert config.parser_name == "docling"
    assert config.chunker_name == "deterministic"
