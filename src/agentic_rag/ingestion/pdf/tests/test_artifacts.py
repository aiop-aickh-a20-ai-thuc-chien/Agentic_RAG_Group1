import json
from pathlib import Path

from pytest import MonkeyPatch

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.pdf import LoadedPdfDocument
from agentic_rag.ingestion.pdf.artifacts import (
    _save_pdf_ingestion_artifacts,
    save_loaded_pdf_ingestion_artifacts,
    save_pdf_ingestion_artifacts,
)
from agentic_rag.ingestion.pdf.models import PdfParseResult


class FakeParser:
    parser_name = "fake-parser"

    def __init__(self, markdown: str) -> None:
        self.markdown = markdown
        self.seen_path: Path | None = None

    def parse(self, path: Path) -> PdfParseResult:
        self.seen_path = path
        return PdfParseResult(
            parser=self.parser_name,
            source_path=str(path),
            markdown=self.markdown,
        )

    def parse_to_markdown(self, path: Path) -> str:
        self.seen_path = path
        return self.markdown


def test_save_pdf_ingestion_artifacts_writes_markdown_chunks_and_manifest(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "VinFast Warranty.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    output_root = tmp_path / "artifacts"
    parser = FakeParser("# Warranty\nPin duoc bao hanh 8 nam.\n\n## Battery\nDieu kien ap dung.")

    manifest = _save_pdf_ingestion_artifacts(
        pdf_path,
        parser,
        output_root=output_root,
        run_id="manual-run",
    )

    run_dir = output_root / "vinfast_warranty" / "manual_run"
    assert manifest.run_dir == str(run_dir)
    assert manifest.markdown_path == str(run_dir / "parsed.md")
    assert manifest.chunks_path == str(run_dir / "chunks.jsonl")
    assert manifest.chunks_markdown_path == str(run_dir / "chunks.md")
    assert manifest.manifest_path == str(run_dir / "manifest.json")
    assert manifest.chunk_count == 2
    assert manifest.parser == "fake-parser"
    assert parser.seen_path == pdf_path

    assert (run_dir / "parsed.md").read_text(encoding="utf-8") == parser.markdown

    chunk_lines = (run_dir / "chunks.jsonl").read_text(encoding="utf-8").splitlines()
    chunks = [Chunk.model_validate(json.loads(line)) for line in chunk_lines]
    assert [chunk.chunk_id for chunk in chunks] == [
        "pdf_vinfast_warranty_c0001",
        "pdf_vinfast_warranty_c0002",
    ]
    assert chunks[0].metadata["section"] == "Warranty"
    assert chunks[1].metadata["section"] == "Battery"
    assert chunks[0].metadata["parser"] == "fake-parser"

    chunks_markdown = (run_dir / "chunks.md").read_text(encoding="utf-8")
    assert "# PDF Chunks" in chunks_markdown
    assert "## pdf_vinfast_warranty_c0001" in chunks_markdown
    assert "- section: Warranty" in chunks_markdown
    assert "- parser: fake-parser" in chunks_markdown
    assert "Pin duoc bao hanh 8 nam." in chunks_markdown

    manifest_payload = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest_payload == manifest.model_dump(mode="json")


def test_save_pdf_ingestion_artifacts_uses_selected_parser(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    pdf_path = tmp_path / "selected.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    output_root = tmp_path / "artifacts"

    monkeypatch.setattr(
        "agentic_rag.ingestion.pdf.artifacts.resolve_pdf_parser",
        lambda parser_name: FakeParser("# Selected\nNoi dung."),
    )

    manifest = save_pdf_ingestion_artifacts(
        str(pdf_path),
        output_root=output_root,
        run_id="selected-run",
        parser_name="docling",
    )

    assert manifest.parser == "fake-parser"


def test_save_loaded_pdf_ingestion_artifacts_reuses_loaded_output(tmp_path: Path) -> None:
    pdf_path = tmp_path / "Pipeline Test.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    output_root = tmp_path / "artifacts"
    loaded = LoadedPdfDocument(
        markdown="# Loaded\nNoi dung da parse.",
        chunks=[
            Chunk(
                chunk_id="pdf_pipeline_test_c0001",
                text="Noi dung da parse.",
                metadata={
                    "source": str(pdf_path),
                    "source_type": "internal",
                    "file_name": "Pipeline Test.pdf",
                    "section": "Loaded",
                },
            )
        ],
        parser="docling",
        pipeline="ocr",
        strategy="docling",
        chunker="deterministic",
    )

    manifest = save_loaded_pdf_ingestion_artifacts(
        pdf_path,
        loaded,
        output_root=output_root,
        run_id="cli-run",
    )

    run_dir = output_root / "pipeline_test" / "cli_run"
    assert manifest.run_dir == str(run_dir)
    assert manifest.parser == "docling"
    assert manifest.pipeline == "ocr"
    assert manifest.strategy == "docling"
    assert manifest.chunker == "deterministic"
    assert manifest.chunk_count == 1
    assert (run_dir / "parsed.md").read_text(encoding="utf-8") == loaded.markdown
    assert manifest.chunks_markdown_path == str(run_dir / "chunks.md")

    chunk_lines = (run_dir / "chunks.jsonl").read_text(encoding="utf-8").splitlines()
    chunks = [Chunk.model_validate(json.loads(line)) for line in chunk_lines]
    assert chunks == loaded.chunks

    chunks_markdown = (run_dir / "chunks.md").read_text(encoding="utf-8")
    assert "## pdf_pipeline_test_c0001" in chunks_markdown
    assert "- section: Loaded" in chunks_markdown
    assert "Noi dung da parse." in chunks_markdown

    manifest_payload = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest_payload == manifest.model_dump(mode="json")
