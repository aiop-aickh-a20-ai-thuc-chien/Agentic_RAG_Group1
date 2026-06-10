from pathlib import Path

import pytest

from agentic_rag.ingestion.pdf import parser


class FakeDocument:
    def export_to_markdown(self) -> str:
        return "# Title\nContent"


class FakeResult:
    document = FakeDocument()


class FakeConverter:
    seen_path: Path | None = None

    def convert(self, path: Path) -> FakeResult:
        self.__class__.seen_path = path
        return FakeResult()


class FailingConverter:
    def convert(self, path: Path) -> FakeResult:
        raise ValueError(f"cannot parse {path.name}")


def test_docling_parser_returns_exported_markdown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(parser, "DocumentConverter", FakeConverter)
    pdf_path = Path("sample.pdf")

    markdown = parser.DoclingMarkdownParser().parse_to_markdown(pdf_path)

    assert markdown == "# Title\nContent"
    assert FakeConverter.seen_path == pdf_path


def test_docling_parser_returns_normalized_parse_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(parser, "DocumentConverter", FakeConverter)
    pdf_path = Path("sample.pdf")

    result = parser.DoclingMarkdownParser().parse(pdf_path)

    assert result.parser == "docling"
    assert result.source_path == "sample.pdf"
    assert result.markdown == "# Title\nContent"
    assert result.assets == []
    assert result.warnings == []


def test_docling_parser_wraps_conversion_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(parser, "DocumentConverter", FailingConverter)
    pdf_path = Path("broken.pdf")

    with pytest.raises(RuntimeError, match=r"broken\.pdf"):
        parser.DoclingMarkdownParser().parse_to_markdown(pdf_path)
