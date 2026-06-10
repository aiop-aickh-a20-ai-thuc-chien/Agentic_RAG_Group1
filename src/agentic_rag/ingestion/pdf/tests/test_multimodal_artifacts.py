from pathlib import Path
from typing import ClassVar

from PIL import Image

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.pdf.artifacts import (
    PdfElementArtifact,
    _map_elements_to_chunks_by_page,
    _save_pdf_multimodal_artifacts_from_document,
)


class FakeProvenance:
    def __init__(self, page_no: int) -> None:
        self.page_no = page_no


class FakeTextItem:
    label = "text"

    def __init__(self, text: str, page_no: int) -> None:
        self.text = text
        self.prov = [FakeProvenance(page_no=page_no)]


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
        return [
            (FakeTextItem("# Page 2\nImage context.", page_no=2), 0),
            (FakeImageItem(), 0),
            (FakeTextItem("# Page 3\nChart context.", page_no=3), 0),
            (FakeChartItem(), 0),
            (FakeTextItem("# Page 4\nTable context.", page_no=4), 0),
            (FakeTableItem(), 0),
        ]

    def save_as_markdown(
        self,
        filename: str | Path,
        artifacts_dir: Path | None = None,
        **kwargs: object,
    ) -> None:
        assert artifacts_dir == Path("assets/images")
        image_dir = Path(filename).parent / artifacts_dir
        image_dir.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (8, 8), color="red").save(image_dir / "image_000000_fake.png")
        Path(filename).write_text(
            "# Intro\n\n![Image](assets/images/image_000000_fake.png)",
            encoding="utf-8",
        )


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
    assert (run_dir / "assets" / "images" / "image_000000_fake.png").exists()
    assert (run_dir / "assets" / "charts" / "pdf_mixed_chart_0001.png").exists()
    assert (run_dir / "assets" / "tables" / "pdf_mixed_table_0001.md").exists()
    assert (run_dir / "assets" / "tables" / "pdf_mixed_table_0001.csv").exists()
    assert (run_dir / "assets" / "tables" / "pdf_mixed_table_0001.png").exists()
    assert (run_dir / "parsed.md").read_text(encoding="utf-8") == (
        "# Intro\n\n![Image](assets/images/image_000000_fake.png)"
    )

    elements = [
        PdfElementArtifact.model_validate_json(line)
        for line in (run_dir / "elements.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [element.kind for element in elements] == ["image", "chart", "table"]
    assert [element.page for element in elements] == [2, 3, 4]
    assert elements[2].text == "| A | B |\n|---|---|\n| 1 | 2 |"

    chunks = [
        Chunk.model_validate_json(line)
        for line in (run_dir / "chunks.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    chunks_by_page = {chunk.metadata["page"]: chunk for chunk in chunks}
    assert set(chunks_by_page) == {2, 3, 4}
    assert elements[0].chunk_ids == [chunks_by_page[2].chunk_id]
    assert elements[1].chunk_ids == [chunks_by_page[3].chunk_id]
    assert elements[2].chunk_ids == [chunks_by_page[4].chunk_id]
    assert chunks_by_page[2].metadata["asset_ids"] == [elements[0].element_id]
    assert chunks_by_page[2].metadata["has_image"] is True
    assert chunks_by_page[2].metadata["has_chart"] is False
    assert chunks_by_page[3].metadata["asset_ids"] == [elements[1].element_id]
    assert chunks_by_page[3].metadata["has_chart"] is True
    assert chunks_by_page[4].metadata["asset_ids"] == [elements[2].element_id]
    assert chunks_by_page[4].metadata["has_table"] is True


def test_map_elements_to_chunks_by_page_leaves_unmatched_assets_unassigned() -> None:
    chunk = Chunk(
        chunk_id="pdf_source_c0001",
        text="Page 2 text.",
        metadata={"page": 2},
    )
    element = PdfElementArtifact(
        element_id="pdf_source_image_0001",
        kind="image",
        page=5,
        source_ref="#/pictures/0",
        asset_paths=[],
        chunk_ids=["legacy_first_chunk"],
    )

    mapped = _map_elements_to_chunks_by_page([chunk], [element])

    assert mapped[0].chunk_ids == []


def test_map_elements_to_chunks_by_page_uses_page_range_intersection() -> None:
    chunks = [
        Chunk(
            chunk_id="pdf_source_c0001",
            text="Page 2 text.",
            metadata={"page": 2, "pages": [2], "page_range": [2, 2]},
        ),
        Chunk(
            chunk_id="pdf_source_c0002",
            text="Page 3 text.",
            metadata={"page": 3, "pages": [3], "page_range": [3, 3]},
        ),
        Chunk(
            chunk_id="pdf_source_c0004",
            text="Page 4 text.",
            metadata={"page": 4, "pages": [4], "page_range": [4, 4]},
        ),
    ]
    element = PdfElementArtifact(
        element_id="pdf_source_table_0001",
        kind="table",
        page=2,
        pages=[2, 3],
        page_range=[2, 3],
        source_ref="#/tables/0",
        asset_paths=[],
        chunk_ids=[],
    )

    mapped = _map_elements_to_chunks_by_page(chunks, [element])

    assert mapped[0].chunk_ids == ["pdf_source_c0001", "pdf_source_c0002"]
