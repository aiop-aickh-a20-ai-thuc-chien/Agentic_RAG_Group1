import importlib
from pathlib import Path

from agentic_rag.core import Answer, Chunk, Citation, SearchResult


def test_core_re_exports_shared_contracts() -> None:
    chunk = Chunk(chunk_id="url_001_smain_c01", text="Sample.", metadata={})
    result = SearchResult(chunk=chunk, score=1.0, rank=1, retriever="hybrid")
    citation = Citation(source="sample.txt", chunk_id=chunk.chunk_id)
    answer = Answer(answer="Sample.", status="answered", citations=[citation])

    assert result.chunk == chunk
    assert answer.citations == [citation]


def test_pdf_and_url_ingestion_are_separate_packages() -> None:
    pdf_module = importlib.import_module("agentic_rag.ingestion.pdf")
    url_module = importlib.import_module("agentic_rag.ingestion.url")

    assert hasattr(pdf_module, "__path__")
    assert hasattr(url_module, "__path__")


def test_production_code_does_not_use_dataclasses() -> None:
    source_root = Path(__file__).resolve().parents[1] / "src"
    offenders: list[str] = []
    for path in source_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "@dataclass" in text or "from dataclasses" in text or "import dataclasses" in text:
            offenders.append(path.relative_to(source_root).as_posix())

    assert offenders == []
