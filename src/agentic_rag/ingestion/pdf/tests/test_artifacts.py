import json
from pathlib import Path

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.pdf.artifacts import _save_pdf_ingestion_artifacts


class FakeParser:
    def __init__(self, markdown: str) -> None:
        self.markdown = markdown
        self.seen_path: Path | None = None

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
    assert manifest.manifest_path == str(run_dir / "manifest.json")
    assert manifest.chunk_count == 2
    assert manifest.parser == "docling"
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

    manifest_payload = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest_payload == manifest.model_dump(mode="json")
