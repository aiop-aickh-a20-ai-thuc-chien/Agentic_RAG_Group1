from pathlib import Path
from typing import ClassVar

from PIL import Image

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.pdf.artifacts import (
    PdfElementArtifact,
    _save_pdf_multimodal_artifacts_from_document,
)


class FakeProvenance:
    def __init__(self, page_no: int) -> None:
        self.page_no = page_no


class FakeImageItem:
    label = "picture"
    self_ref = "#/pictures/0"
    prov: ClassVar[list[FakeProvenance]] = [FakeProvenance(page_no=2)]

    def get_image(self, doc: object, prov_index: int = 0) -> Image.Image:
        return Image.new("RGB", (8, 8), color="red")


class FakeChartItem:
    label = "chart"
    self_ref = "#/pictures/1"
    prov: ClassVar[list[FakeProvenance]] = [FakeProvenance(page_no=3)]

    def get_image(self, doc: object, prov_index: int = 0) -> Image.Image:
        return Image.new("RGB", (8, 8), color="blue")


class FakeTableItem:
    label = "table"
    self_ref = "#/tables/0"
    prov: ClassVar[list[FakeProvenance]] = [FakeProvenance(page_no=4)]

    def export_to_markdown(self, doc: object | None = None) -> str:
        return "| A | B |\n|---|---|\n| 1 | 2 |"

    def export_to_dataframe(self, doc: object | None = None) -> object:
        class FakeDataFrame:
            def to_csv(self, path: Path, index: bool = False) -> None:
                path.write_text("A,B\n1,2\n", encoding="utf-8")

        return FakeDataFrame()

    def get_image(self, doc: object, prov_index: int = 0) -> Image.Image:
        return Image.new("RGB", (8, 8), color="green")


class FakeDoclingDocument:
    def iterate_items(self, *args: object, **kwargs: object) -> list[tuple[object, int]]:
        return [(FakeImageItem(), 0), (FakeChartItem(), 0), (FakeTableItem(), 0)]


def test_save_pdf_multimodal_artifacts_writes_elements_assets_and_enriched_chunks(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "mixed.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")
    output_root = tmp_path / "artifacts"

    manifest = _save_pdf_multimodal_artifacts_from_document(
        pdf_path,
        markdown="# Intro\nText with table and image.",
        doc=FakeDoclingDocument(),
        output_root=output_root,
        run_id="run-1",
    )

    run_dir = output_root / "mixed" / "run_1"
    assert manifest.run_dir == str(run_dir)
    assert manifest.element_count == 3
    assert manifest.image_count == 1
    assert manifest.chart_count == 1
    assert manifest.table_count == 1
    assert (run_dir / "elements.jsonl").exists()
    assert (run_dir / "chunks.md").exists()
    assert (run_dir / "assets" / "images" / "pdf_mixed_image_0001.png").exists()
    assert (run_dir / "assets" / "charts" / "pdf_mixed_chart_0001.png").exists()
    assert (run_dir / "assets" / "tables" / "pdf_mixed_table_0001.md").exists()
    assert (run_dir / "assets" / "tables" / "pdf_mixed_table_0001.csv").exists()
    assert (run_dir / "assets" / "tables" / "pdf_mixed_table_0001.png").exists()

    elements = [
        PdfElementArtifact.model_validate_json(line)
        for line in (run_dir / "elements.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [element.kind for element in elements] == ["image", "chart", "table"]
    assert elements[2].text == "| A | B |\n|---|---|\n| 1 | 2 |"

    chunks = [
        Chunk.model_validate_json(line)
        for line in (run_dir / "chunks.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert chunks
    assert "asset_ids" in chunks[0].metadata
    assert isinstance(chunks[0].metadata["asset_ids"], list)
    assert isinstance(chunks[0].metadata["has_image"], bool)
    assert isinstance(chunks[0].metadata["has_table"], bool)
    assert isinstance(chunks[0].metadata["has_chart"], bool)
