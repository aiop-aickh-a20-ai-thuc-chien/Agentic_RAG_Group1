"""Debug artifact persistence for PDF ingestion."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from agentic_rag.core.contracts import Chunk

from .chunkers import DoclingPageAwareChunker
from .loader import (
    LoadedPdfDocument,
    _chunks_from_chunking_input,
    _chunks_from_markdown,
    _safe_chunk_id_part,
    _validate_pdf_path,
)
from .models import PdfChunkingInput
from .parser import DoclingMarkdownParser, PdfMarkdownParser
from .registry import resolve_pdf_parser

DEFAULT_PDF_ARTIFACT_ROOT = Path(__file__).resolve().parent / ".data" / "artifacts"


class _PdfArtifactModel(BaseModel):
    """Base config for PDF artifact metadata."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class PdfIngestionArtifactManifest(_PdfArtifactModel):
    """Metadata describing one persisted PDF ingestion artifact run."""

    artifact_schema_version: int = 1
    input_path: str
    parser: str
    pipeline: str | None = None
    strategy: str | None = None
    chunker: str | None = None
    run_id: str
    created_at: str
    artifact_root: str
    run_dir: str
    markdown_path: str
    chunks_path: str
    chunks_markdown_path: str
    manifest_path: str
    chunk_count: int


class PdfElementArtifact(_PdfArtifactModel):
    """Metadata for one parser-native PDF asset persisted for later processing."""

    element_id: str
    kind: Literal["image", "table", "chart"]
    page: int | None
    pages: list[int] = Field(default_factory=list)
    page_range: list[int] | None = None
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
    chunks_markdown_path: str
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


def save_loaded_pdf_ingestion_artifacts(
    path: str | Path,
    loaded: LoadedPdfDocument,
    *,
    output_root: str | Path | None = None,
    run_id: str | None = None,
) -> PdfIngestionArtifactManifest:
    """Save already parsed/chunked PDF output using the standard debug artifact layout."""

    pdf_path = Path(path)
    _validate_pdf_path(pdf_path)

    artifact_root = Path(output_root) if output_root is not None else DEFAULT_PDF_ARTIFACT_ROOT
    resolved_run_id = _safe_run_id(run_id)
    run_dir = artifact_root / _safe_chunk_id_part(pdf_path.stem) / resolved_run_id
    run_dir.mkdir(parents=True, exist_ok=False)

    markdown_path = run_dir / "parsed.md"
    chunks_path = run_dir / "chunks.jsonl"
    chunks_markdown_path = run_dir / "chunks.md"
    manifest_path = run_dir / "manifest.json"

    markdown_path.write_text(loaded.markdown, encoding="utf-8")
    _write_chunks_jsonl(chunks_path, loaded.chunks)
    _write_chunks_markdown(chunks_markdown_path, loaded.chunks)

    manifest = PdfIngestionArtifactManifest(
        input_path=str(pdf_path),
        parser=loaded.parser,
        pipeline=loaded.pipeline,
        strategy=loaded.strategy,
        chunker=loaded.chunker,
        run_id=resolved_run_id,
        created_at=datetime.now(UTC).isoformat(),
        artifact_root=str(artifact_root),
        run_dir=str(run_dir),
        markdown_path=str(markdown_path),
        chunks_path=str(chunks_path),
        chunks_markdown_path=str(chunks_markdown_path),
        manifest_path=str(manifest_path),
        chunk_count=len(loaded.chunks),
    )
    _write_model_json(manifest_path, manifest)
    return manifest


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
    chunks_markdown_path = run_dir / "chunks.md"
    manifest_path = run_dir / "manifest.json"

    markdown_path.write_text(parse_result.markdown, encoding="utf-8")
    _write_chunks_jsonl(chunks_path, chunks)
    _write_chunks_markdown(chunks_markdown_path, chunks)

    manifest = PdfIngestionArtifactManifest(
        input_path=str(path),
        parser=parse_result.parser,
        run_id=resolved_run_id,
        created_at=datetime.now(UTC).isoformat(),
        artifact_root=str(artifact_root),
        run_dir=str(run_dir),
        markdown_path=str(markdown_path),
        chunks_path=str(chunks_path),
        chunks_markdown_path=str(chunks_markdown_path),
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
    chunks_markdown_path = run_dir / "chunks.md"
    manifest_path = run_dir / "manifest.json"
    elements_path = run_dir / "elements.jsonl"

    _write_referenced_image_markdown(
        doc=doc,
        markdown_path=markdown_path,
        fallback_markdown=markdown,
    )

    chunks = _chunks_from_chunking_input(
        path,
        PdfChunkingInput(
            markdown=markdown,
            parser="docling",
            source_path=str(path),
            native_document=doc,
        ),
        chunker=DoclingPageAwareChunker(),
    )
    elements = _extract_multimodal_elements(
        doc,
        safe_file_stem=safe_file_stem,
        images_dir=images_dir,
        tables_dir=tables_dir,
        charts_dir=charts_dir,
    )
    mapped_elements = _map_elements_to_chunks_by_page(chunks, elements)
    enriched_chunks = _enrich_chunks_with_assets(chunks, mapped_elements)

    _write_chunks_jsonl(chunks_path, enriched_chunks)
    _write_chunks_markdown(chunks_markdown_path, enriched_chunks)
    _write_elements_jsonl(elements_path, mapped_elements)

    manifest = PdfMultimodalArtifactManifest(
        input_path=str(path),
        parser="docling",
        run_id=resolved_run_id,
        created_at=datetime.now(UTC).isoformat(),
        artifact_root=str(artifact_root),
        run_dir=str(run_dir),
        markdown_path=str(markdown_path),
        chunks_path=str(chunks_path),
        chunks_markdown_path=str(chunks_markdown_path),
        manifest_path=str(manifest_path),
        elements_path=str(elements_path),
        assets_dir=str(assets_dir),
        chunk_count=len(enriched_chunks),
        element_count=len(mapped_elements),
        image_count=sum(element.kind == "image" for element in mapped_elements),
        table_count=sum(element.kind == "table" for element in mapped_elements),
        chart_count=sum(element.kind == "chart" for element in mapped_elements),
    )
    _write_model_json(manifest_path, manifest)
    return manifest


def _extract_multimodal_elements(
    doc: Any,
    *,
    safe_file_stem: str,
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
                pages=_item_pages(item),
                page_range=_item_page_range(item),
                source_ref=_item_source_ref(item, fallback=element_id),
                asset_paths=asset_paths,
                text=text,
                chunk_ids=[],
            )
        )

    return elements


def _write_referenced_image_markdown(
    *,
    doc: Any,
    markdown_path: Path,
    fallback_markdown: str,
) -> None:
    save_as_markdown = getattr(doc, "save_as_markdown", None)
    if not callable(save_as_markdown):
        markdown_path.write_text(fallback_markdown, encoding="utf-8")
        return

    from importlib import import_module

    image_ref_mode_name = "ImageRefMode"
    image_ref_mode = getattr(
        import_module("docling_core.types.doc.document"),
        image_ref_mode_name,
    )

    cast(Callable[..., object], save_as_markdown)(
        markdown_path,
        artifacts_dir=Path("assets/images"),
        image_mode=image_ref_mode.REFERENCED,
    )


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
    pages = _item_pages(item)
    return pages[0] if pages else None


def _item_pages(item: Any) -> list[int]:
    provenance = getattr(item, "prov", None)
    if not provenance:
        return []
    pages: list[int] = []
    for item_provenance in provenance:
        page_no = getattr(item_provenance, "page_no", None)
        if isinstance(page_no, int) and page_no not in pages:
            pages.append(page_no)
    return sorted(pages)


def _item_page_range(item: Any) -> list[int] | None:
    pages = _item_pages(item)
    if not pages:
        return None
    return [pages[0], pages[-1]]


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

    elements_by_chunk_id: dict[str, list[PdfElementArtifact]] = {}
    for element in elements:
        for chunk_id in element.chunk_ids:
            elements_by_chunk_id.setdefault(chunk_id, []).append(element)

    enriched_chunks: list[Chunk] = []
    for chunk in chunks:
        chunk_elements = elements_by_chunk_id.get(chunk.chunk_id, [])
        metadata: dict[str, Any] = dict(chunk.metadata)
        metadata.update(
            {
                "asset_ids": [element.element_id for element in chunk_elements],
                "has_image": any(element.kind == "image" for element in chunk_elements),
                "has_table": any(element.kind == "table" for element in chunk_elements),
                "has_chart": any(element.kind == "chart" for element in chunk_elements),
            }
        )
        enriched_chunks.append(chunk.model_copy(update={"metadata": metadata}))
    return enriched_chunks


def _map_elements_to_chunks_by_page(
    chunks: list[Chunk],
    elements: list[PdfElementArtifact],
) -> list[PdfElementArtifact]:
    chunk_ids_by_page: dict[int, list[str]] = {}
    for chunk in chunks:
        for page in _metadata_pages(chunk.metadata):
            chunk_ids_by_page.setdefault(page, []).append(chunk.chunk_id)

    mapped_elements: list[PdfElementArtifact] = []
    for element in elements:
        chunk_ids: list[str] = []
        for page in _element_pages(element):
            for chunk_id in chunk_ids_by_page.get(page, []):
                if chunk_id not in chunk_ids:
                    chunk_ids.append(chunk_id)
        mapped_elements.append(element.model_copy(update={"chunk_ids": chunk_ids}))
    return mapped_elements


def _metadata_pages(metadata: dict[str, Any]) -> list[int]:
    pages = metadata.get("pages")
    if isinstance(pages, list):
        resolved_pages = [page for page in pages if isinstance(page, int)]
        if resolved_pages:
            return sorted(set(resolved_pages))

    page_range = metadata.get("page_range")
    if (
        isinstance(page_range, list)
        and len(page_range) == 2
        and isinstance(page_range[0], int)
        and isinstance(page_range[1], int)
    ):
        start, end = sorted((page_range[0], page_range[1]))
        return list(range(start, end + 1))

    page = metadata.get("page")
    return [page] if isinstance(page, int) else []


def _element_pages(element: PdfElementArtifact) -> list[int]:
    if element.pages:
        return sorted(set(element.pages))
    if element.page_range is not None and len(element.page_range) == 2:
        start, end = sorted((element.page_range[0], element.page_range[1]))
        return list(range(start, end + 1))
    return [element.page] if element.page is not None else []


def _write_chunks_jsonl(path: Path, chunks: list[Chunk]) -> None:
    with path.open("w", encoding="utf-8") as chunks_file:
        for chunk in chunks:
            chunks_file.write(json.dumps(chunk.model_dump(mode="json"), ensure_ascii=False))
            chunks_file.write("\n")


def _write_chunks_markdown(path: Path, chunks: list[Chunk]) -> None:
    lines = ["# PDF Chunks", ""]
    for chunk in chunks:
        lines.extend(
            [
                f"## {chunk.chunk_id}",
                "",
                f"- section: {_metadata_text(chunk.metadata.get('section'))}",
                f"- page: {_metadata_text(chunk.metadata.get('page'))}",
                f"- parser: {_metadata_text(chunk.metadata.get('parser'))}",
                f"- chunking_method: {_metadata_text(chunk.metadata.get('chunking_method'))}",
                "",
                chunk.text.strip(),
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def _metadata_text(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


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
