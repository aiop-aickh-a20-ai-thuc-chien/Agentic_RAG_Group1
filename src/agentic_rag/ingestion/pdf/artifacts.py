"""Debug artifact persistence for PDF ingestion."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.pdf.loader import (
    _chunks_from_markdown,
    _safe_chunk_id_part,
    _validate_pdf_path,
)
from agentic_rag.ingestion.pdf.parser import DoclingMarkdownParser, PdfMarkdownParser
from agentic_rag.ingestion.pdf.registry import resolve_pdf_parser

DEFAULT_PDF_ARTIFACT_ROOT = Path(__file__).resolve().parent / ".data" / "artifacts"


class _PdfArtifactModel(BaseModel):
    """Base config for PDF artifact metadata."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class PdfIngestionArtifactManifest(_PdfArtifactModel):
    """Metadata describing one persisted PDF ingestion artifact run."""

    artifact_schema_version: int = 1
    input_path: str
    parser: str
    run_id: str
    created_at: str
    artifact_root: str
    run_dir: str
    markdown_path: str
    chunks_path: str
    manifest_path: str
    chunk_count: int


class PdfElementArtifact(_PdfArtifactModel):
    """Metadata for one parser-native PDF asset persisted for later processing."""

    element_id: str
    kind: Literal["image", "table", "chart"]
    page: int | None
    source_ref: str
    asset_paths: list[str]
    text: str | None = None
    chunk_ids: list[str]


class PdfMultimodalArtifactManifest(_PdfArtifactModel):
    """Metadata describing one persisted multimodal PDF artifact run."""

    artifact_schema_version: int = 2
    input_path: str
    parser: str
    run_id: str
    created_at: str
    artifact_root: str
    run_dir: str
    markdown_path: str
    chunks_path: str
    manifest_path: str
    elements_path: str
    assets_dir: str
    chunk_count: int
    element_count: int
    image_count: int
    table_count: int
    chart_count: int


def save_pdf_ingestion_artifacts(
    path: str,
    *,
    output_root: str | Path | None = None,
    run_id: str | None = None,
    parser_name: str = "docling",
) -> PdfIngestionArtifactManifest:
    """Parse a PDF, chunk it, and save debug artifacts for evaluation."""

    return _save_pdf_ingestion_artifacts(
        Path(path),
        resolve_pdf_parser(parser_name),
        output_root=output_root,
        run_id=run_id,
    )


def save_pdf_multimodal_artifacts(
    path: str,
    *,
    output_root: str | Path | None = None,
    run_id: str | None = None,
) -> PdfMultimodalArtifactManifest:
    """Parse a PDF and save text, chunk, and raw multimodal debug artifacts."""

    pdf_path = Path(path)
    _validate_pdf_path(pdf_path)
    parsed = DoclingMarkdownParser().parse_to_document(pdf_path)
    return _save_pdf_multimodal_artifacts_from_document(
        pdf_path,
        markdown=parsed.markdown,
        doc=parsed.document,
        output_root=output_root,
        run_id=run_id,
    )


def _save_pdf_ingestion_artifacts(
    path: Path,
    parser: PdfMarkdownParser,
    *,
    output_root: str | Path | None = None,
    run_id: str | None = None,
) -> PdfIngestionArtifactManifest:
    _validate_pdf_path(path)

    parse_result = parser.parse(path)
    chunks = _chunks_from_markdown(
        path,
        parse_result.markdown,
        parser_name=parse_result.parser,
    )

    artifact_root = Path(output_root) if output_root is not None else DEFAULT_PDF_ARTIFACT_ROOT
    resolved_run_id = _safe_run_id(run_id)
    run_dir = artifact_root / _safe_chunk_id_part(path.stem) / resolved_run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    markdown_path = run_dir / "parsed.md"
    chunks_path = run_dir / "chunks.jsonl"
    manifest_path = run_dir / "manifest.json"

    markdown_path.write_text(parse_result.markdown, encoding="utf-8")
    _write_chunks_jsonl(chunks_path, chunks)

    manifest = PdfIngestionArtifactManifest(
        input_path=str(path),
        parser=parse_result.parser,
        run_id=resolved_run_id,
        created_at=datetime.now(UTC).isoformat(),
        artifact_root=str(artifact_root),
        run_dir=str(run_dir),
        markdown_path=str(markdown_path),
        chunks_path=str(chunks_path),
        manifest_path=str(manifest_path),
        chunk_count=len(chunks),
    )
    _write_model_json(manifest_path, manifest)
    return manifest


def _save_pdf_multimodal_artifacts_from_document(
    path: Path,
    *,
    markdown: str,
    doc: Any,
    output_root: str | Path | None = None,
    run_id: str | None = None,
) -> PdfMultimodalArtifactManifest:
    _validate_pdf_path(path)

    artifact_root = Path(output_root) if output_root is not None else DEFAULT_PDF_ARTIFACT_ROOT
    resolved_run_id = _safe_run_id(run_id)
    safe_file_stem = _safe_chunk_id_part(path.stem)
    run_dir = artifact_root / safe_file_stem / resolved_run_id
    assets_dir = run_dir / "assets"
    images_dir = assets_dir / "images"
    tables_dir = assets_dir / "tables"
    charts_dir = assets_dir / "charts"
    for directory in (images_dir, tables_dir, charts_dir):
        directory.mkdir(parents=True, exist_ok=False)

    markdown_path = run_dir / "parsed.md"
    chunks_path = run_dir / "chunks.jsonl"
    manifest_path = run_dir / "manifest.json"
    elements_path = run_dir / "elements.jsonl"

    markdown_path.write_text(markdown, encoding="utf-8")

    chunks = _chunks_from_markdown(path, markdown)
    first_chunk_id = chunks[0].chunk_id if chunks else None
    elements = _extract_multimodal_elements(
        doc,
        safe_file_stem=safe_file_stem,
        first_chunk_id=first_chunk_id,
        images_dir=images_dir,
        tables_dir=tables_dir,
        charts_dir=charts_dir,
    )
    enriched_chunks = _enrich_chunks_with_assets(chunks, elements)

    _write_chunks_jsonl(chunks_path, enriched_chunks)
    _write_elements_jsonl(elements_path, elements)

    manifest = PdfMultimodalArtifactManifest(
        input_path=str(path),
        parser="docling",
        run_id=resolved_run_id,
        created_at=datetime.now(UTC).isoformat(),
        artifact_root=str(artifact_root),
        run_dir=str(run_dir),
        markdown_path=str(markdown_path),
        chunks_path=str(chunks_path),
        manifest_path=str(manifest_path),
        elements_path=str(elements_path),
        assets_dir=str(assets_dir),
        chunk_count=len(enriched_chunks),
        element_count=len(elements),
        image_count=sum(element.kind == "image" for element in elements),
        table_count=sum(element.kind == "table" for element in elements),
        chart_count=sum(element.kind == "chart" for element in elements),
    )
    _write_model_json(manifest_path, manifest)
    return manifest


def _extract_multimodal_elements(
    doc: Any,
    *,
    safe_file_stem: str,
    first_chunk_id: str | None,
    images_dir: Path,
    tables_dir: Path,
    charts_dir: Path,
) -> list[PdfElementArtifact]:
    elements: list[PdfElementArtifact] = []
    kind_counts: dict[Literal["image", "table", "chart"], int] = {
        "image": 0,
        "table": 0,
        "chart": 0,
    }

    for item in _iter_docling_items(doc):
        kind = _element_kind(item)
        if kind is None:
            continue

        kind_counts[kind] += 1
        element_id = f"pdf_{safe_file_stem}_{kind}_{kind_counts[kind]:04d}"
        asset_paths: list[str] = []
        text: str | None = None

        if kind == "image":
            image_path = images_dir / f"{element_id}.png"
            if _write_item_image(item, doc, image_path):
                asset_paths.append(str(image_path))
        elif kind == "chart":
            chart_path = charts_dir / f"{element_id}.png"
            if _write_item_image(item, doc, chart_path):
                asset_paths.append(str(chart_path))
        else:
            text = _item_markdown(item, doc)
            if text is not None:
                markdown_path = tables_dir / f"{element_id}.md"
                markdown_path.write_text(text, encoding="utf-8")
                asset_paths.append(str(markdown_path))

            csv_path = tables_dir / f"{element_id}.csv"
            if _write_table_csv(item, doc, csv_path):
                asset_paths.append(str(csv_path))

            table_image_path = tables_dir / f"{element_id}.png"
            if _write_item_image(item, doc, table_image_path):
                asset_paths.append(str(table_image_path))

        elements.append(
            PdfElementArtifact(
                element_id=element_id,
                kind=kind,
                page=_item_page(item),
                source_ref=_item_source_ref(item, fallback=element_id),
                asset_paths=asset_paths,
                text=text,
                chunk_ids=[first_chunk_id] if first_chunk_id is not None else [],
            )
        )

    return elements


def _iter_docling_items(doc: Any) -> list[Any]:
    iterate_items = getattr(doc, "iterate_items", None)
    if not callable(iterate_items):
        return []

    try:
        raw_items = iterate_items(traverse_pictures=True)
    except TypeError:
        raw_items = iterate_items()

    items: list[Any] = []
    for entry in raw_items:
        if isinstance(entry, tuple):
            items.append(entry[0])
        else:
            items.append(entry)
    return items


def _element_kind(item: Any) -> Literal["image", "table", "chart"] | None:
    label = getattr(item, "label", "")
    label_value = getattr(label, "value", label)
    normalized_label = str(label_value).lower()
    if normalized_label.endswith("picture"):
        return "image"
    if normalized_label.endswith("chart"):
        return "chart"
    if normalized_label.endswith("table"):
        return "table"
    return None


def _item_page(item: Any) -> int | None:
    provenance = getattr(item, "prov", None)
    if not provenance:
        return None
    page_no = getattr(provenance[0], "page_no", None)
    if isinstance(page_no, int):
        return page_no
    return None


def _item_source_ref(item: Any, *, fallback: str) -> str:
    source_ref = getattr(item, "self_ref", None)
    if source_ref is None:
        return fallback
    return str(source_ref)


def _item_markdown(item: Any, doc: Any) -> str | None:
    markdown = _call_item_method(item, "export_to_markdown", doc)
    if isinstance(markdown, str):
        return markdown
    return None


def _write_table_csv(item: Any, doc: Any, path: Path) -> bool:
    dataframe = _call_item_method(item, "export_to_dataframe", doc)
    if dataframe is None:
        return False

    to_csv = getattr(dataframe, "to_csv", None)
    if not callable(to_csv):
        return False

    cast(Callable[..., object], to_csv)(path, index=False)
    return path.exists()


def _write_item_image(item: Any, doc: Any, path: Path) -> bool:
    image = _call_item_method(item, "get_image", doc)
    if image is None:
        return False

    save = getattr(image, "save", None)
    if not callable(save):
        return False

    cast(Callable[[Path], object], save)(path)
    return path.exists()


def _call_item_method(item: Any, method_name: str, doc: Any) -> Any:
    method = getattr(item, method_name, None)
    if not callable(method):
        return None

    try:
        return method(doc)
    except TypeError:
        return method()


def _enrich_chunks_with_assets(
    chunks: list[Chunk], elements: list[PdfElementArtifact]
) -> list[Chunk]:
    if not chunks:
        return []

    asset_ids = [element.element_id for element in elements]
    has_image = any(element.kind == "image" for element in elements)
    has_table = any(element.kind == "table" for element in elements)
    has_chart = any(element.kind == "chart" for element in elements)

    enriched_first_metadata: dict[str, Any] = dict(chunks[0].metadata)
    enriched_first_metadata.update(
        {
            "asset_ids": asset_ids,
            "has_image": has_image,
            "has_table": has_table,
            "has_chart": has_chart,
        }
    )

    enriched_chunks = [chunks[0].model_copy(update={"metadata": enriched_first_metadata})]
    for chunk in chunks[1:]:
        metadata: dict[str, Any] = dict(chunk.metadata)
        metadata.update(
            {
                "asset_ids": [],
                "has_image": False,
                "has_table": False,
                "has_chart": False,
            }
        )
        enriched_chunks.append(chunk.model_copy(update={"metadata": metadata}))
    return enriched_chunks


def _write_chunks_jsonl(path: Path, chunks: list[Chunk]) -> None:
    with path.open("w", encoding="utf-8") as chunks_file:
        for chunk in chunks:
            chunks_file.write(json.dumps(chunk.model_dump(mode="json"), ensure_ascii=False))
            chunks_file.write("\n")


def _write_elements_jsonl(path: Path, elements: list[PdfElementArtifact]) -> None:
    with path.open("w", encoding="utf-8") as elements_file:
        for element in elements:
            elements_file.write(json.dumps(element.model_dump(mode="json"), ensure_ascii=False))
            elements_file.write("\n")


def _write_model_json(path: Path, model: BaseModel) -> None:
    path.write_text(
        json.dumps(model.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _safe_run_id(run_id: str | None) -> str:
    if run_id is None:
        return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return _safe_chunk_id_part(run_id)
