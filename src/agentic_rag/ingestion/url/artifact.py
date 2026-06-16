"""Artifact persistence for URL ingestion."""

from __future__ import annotations

import json
from collections.abc import Iterable
from html import escape as html_escape
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.url.chunking import short_hash, slugify
from agentic_rag.ingestion.url.parser import Asset, PageMetadata


class DebugArtifact(BaseModel):
    """A debug artifact that can be written to a local directory."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    content: str


class IngestionArtifacts(BaseModel):
    """Paths for persisted URL ingestion artifacts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_dir: Path
    markdown_path: Path
    chunks_path: Path
    manifest_path: Path
    source_html_path: Path | None = None
    cleaned_html_path: Path | None = None
    parsed_sections_path: Path | None = None
    extracted_markdown_path: Path | None = None
    quality_path: Path | None = None


def persist_debug_artifacts(
    output_dir: str | Path | None,
    artifacts: Iterable[DebugArtifact],
) -> tuple[Path, ...]:
    """Write debug artifacts and return their paths."""

    if output_dir is None:
        return ()

    artifact_dir = Path(output_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    written_paths: list[Path] = []
    for artifact in artifacts:
        output_path = artifact_dir / _validate_artifact_name(artifact.name)
        output_path.write_text(artifact.content, encoding="utf-8")
        written_paths.append(output_path)
    return tuple(written_paths)


def persist_ingestion_artifacts(
    *,
    data_dir: str | Path | None,
    input_type: str,
    source: str,
    source_url: str | None,
    parser: str,
    run_id: str,
    created_at: str,
    markdown: str,
    chunks: Iterable[Chunk],
    original_url: str | None = None,
    final_url: str | None = None,
    canonical_url: str | None = None,
    page_metadata: PageMetadata | None = None,
    assets: Iterable[Asset] = (),
    source_html: str | None = None,
    source_html_stage: str | None = None,
    parsed_sections: str | None = None,
    extracted_markdown: str | None = None,
) -> IngestionArtifacts | None:
    """Persist staged URL ingestion artifacts for one run."""

    if data_dir is None:
        return None

    artifact_root = Path(data_dir) / "artifacts"
    run_dir = artifact_root / _source_slug(source) / slugify(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    chunk_list = list(chunks)
    source_html_path = _write_optional_text(run_dir / "source.html", source_html)
    cleaned_html_path = _write_optional_text(
        run_dir / "cleaned.html",
        _cleaned_html_document(
            markdown,
            source=source,
            source_url=source_url,
            page_metadata=page_metadata,
        ),
    )
    parsed_sections_path = _write_optional_text(
        run_dir / "parsed_sections.txt",
        parsed_sections,
    )
    extracted_markdown_path = _write_optional_text(
        run_dir / "extracted.md",
        extracted_markdown,
    )
    markdown_path = run_dir / "parsed.md"
    chunks_path = run_dir / "chunks.jsonl"
    quality_path = _write_quality_artifact(run_dir / "quality.json", chunk_list)
    manifest_path = run_dir / "manifest.json"

    markdown_path.write_text(markdown.rstrip() + "\n", encoding="utf-8")
    chunks_path.write_text(_serialize_chunks_jsonl(chunk_list), encoding="utf-8")

    manifest = {
        "artifact_schema_version": 2,
        "input_type": input_type,
        "input_source": source,
        "input_url": source_url,
        "original_url": original_url,
        "final_url": final_url,
        "canonical_url": canonical_url,
        "parser": parser,
        "run_id": run_id,
        "created_at": created_at,
        "page_metadata": _page_metadata_dict(page_metadata),
        "assets": [_asset_dict(asset) for asset in assets],
        "artifact_root": _path_text(artifact_root),
        "run_dir": _path_text(run_dir),
        "source_html_stage": source_html_stage,
        "source_html_path": _path_text_optional(source_html_path),
        "cleaned_html_path": _path_text_optional(cleaned_html_path),
        "parsed_sections_path": _path_text_optional(parsed_sections_path),
        "extracted_markdown_path": _path_text_optional(extracted_markdown_path),
        "markdown_path": _path_text(markdown_path),
        "chunks_path": _path_text(chunks_path),
        "quality_path": _path_text_optional(quality_path),
        "manifest_path": _path_text(manifest_path),
        "stage_paths": {
            "source_html": _path_text_optional(source_html_path),
            "cleaned_html": _path_text_optional(cleaned_html_path),
            "parsed_sections": _path_text_optional(parsed_sections_path),
            "extracted_markdown": _path_text_optional(extracted_markdown_path),
            "cleaned_markdown": _path_text(markdown_path),
            "quality": _path_text_optional(quality_path),
            "chunks": _path_text(chunks_path),
        },
        "chunk_count": len(chunk_list),
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return IngestionArtifacts(
        run_dir=run_dir,
        markdown_path=markdown_path,
        chunks_path=chunks_path,
        manifest_path=manifest_path,
        source_html_path=source_html_path,
        cleaned_html_path=cleaned_html_path,
        parsed_sections_path=parsed_sections_path,
        extracted_markdown_path=extracted_markdown_path,
        quality_path=quality_path,
    )


def _validate_artifact_name(name: str) -> str:
    if not name or Path(name).name != name:
        raise ValueError("Debug artifact name must be a plain file name.")
    return name


def _serialize_chunks_jsonl(chunks: Iterable[Chunk]) -> str:
    lines = [json.dumps(chunk.model_dump(mode="json"), ensure_ascii=False) for chunk in chunks]
    return "\n".join(lines) + ("\n" if lines else "")


def _write_optional_text(path: Path, content: str | None) -> Path | None:
    if content is None:
        return None
    path.write_text(content.rstrip() + "\n", encoding="utf-8")
    return path


def _cleaned_html_document(
    markdown: str,
    *,
    source: str,
    source_url: str | None,
    page_metadata: PageMetadata | None,
) -> str:
    title = page_metadata.og_title if page_metadata is not None else None
    if not title:
        title = source_url or source
    language = page_metadata.language if page_metadata is not None else None
    if not language:
        language = "und"
    body = _markdown_to_clean_html(markdown)
    return "\n".join(
        [
            "<!doctype html>",
            f'<html lang="{html_escape(language, quote=True)}">',
            "<head>",
            '  <meta charset="utf-8">',
            f"  <title>{html_escape(title)}</title>",
            f'  <meta name="source" content="{html_escape(source, quote=True)}">',
            (
                '  <meta name="source-url" '
                f'content="{html_escape(source_url or "", quote=True)}">'
            ),
            "</head>",
            '<body data-artifact-stage="cleaned_html">',
            "<main>",
            body,
            "</main>",
            "</body>",
            "</html>",
        ]
    )


def _markdown_to_clean_html(markdown: str) -> str:
    lines = markdown.splitlines()
    output: list[str] = []
    paragraph: list[str] = []
    list_items: list[str] = []
    table_rows: list[list[str]] = []
    in_code = False
    code_lines: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            output.append(f"<p>{html_escape(' '.join(paragraph))}</p>")
            paragraph.clear()

    def flush_list() -> None:
        if list_items:
            output.append("<ul>")
            output.extend(f"  <li>{item}</li>" for item in list_items)
            output.append("</ul>")
            list_items.clear()

    def flush_table() -> None:
        if table_rows:
            output.extend(_table_html(table_rows))
            table_rows.clear()

    def flush_code() -> None:
        if code_lines:
            output.append("<pre><code>")
            output.append(html_escape("\n".join(code_lines)))
            output.append("</code></pre>")
            code_lines.clear()

    for raw_line in lines:
        line = raw_line.strip()
        if line.startswith("```"):
            flush_paragraph()
            flush_list()
            flush_table()
            if in_code:
                flush_code()
            in_code = not in_code
            continue
        if in_code:
            code_lines.append(raw_line)
            continue
        if not line:
            flush_paragraph()
            flush_list()
            flush_table()
            continue
        if _is_table_line(line):
            flush_paragraph()
            flush_list()
            if not _is_table_separator(line):
                table_rows.append(_table_cells(line))
            continue
        flush_table()
        heading_level = _heading_level(line)
        if heading_level is not None:
            flush_paragraph()
            flush_list()
            text = line[heading_level + 1 :].strip()
            output.append(f"<h{heading_level}>{html_escape(text)}</h{heading_level}>")
            continue
        if line.startswith("- "):
            flush_paragraph()
            list_items.append(html_escape(line[2:].strip()))
            continue
        flush_list()
        paragraph.append(line)
    flush_paragraph()
    flush_list()
    flush_table()
    if in_code:
        flush_code()
    return "\n".join(output)


def _heading_level(line: str) -> int | None:
    stripped = line.lstrip("#")
    level = len(line) - len(stripped)
    if 1 <= level <= 6 and stripped.startswith(" "):
        return level
    return None


def _is_table_line(line: str) -> bool:
    return line.startswith("|") and line.endswith("|")


def _is_table_separator(line: str) -> bool:
    cells = _table_cells(line)
    return bool(cells) and all(
        set(cell.replace(":", "").strip()) <= {"-"} for cell in cells
    )


def _table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip("|").split("|")]


def _table_html(rows: list[list[str]]) -> list[str]:
    if not rows:
        return []
    output = ["<table>"]
    for index, row in enumerate(rows):
        tag = "th" if index == 0 else "td"
        output.append("  <tr>")
        output.extend(f"    <{tag}>{html_escape(cell)}</{tag}>" for cell in row)
        output.append("  </tr>")
    output.append("</table>")
    return output


def _write_quality_artifact(path: Path, chunks: list[Chunk]) -> Path | None:
    payload = _quality_payload(chunks)
    if payload is None:
        return None
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _quality_payload(chunks: list[Chunk]) -> dict[str, Any] | None:
    if not chunks:
        return None
    metadata = chunks[0].metadata
    url_quality = metadata.get("url_quality")
    url_quality_gate = metadata.get("url_quality_gate")
    if not isinstance(url_quality, dict) and not isinstance(url_quality_gate, dict):
        return None
    return {
        "chunk_count": len(chunks),
        "page_type": metadata.get("page_type"),
        "render_required": metadata.get("render_required"),
        "parser": (
            url_quality_gate.get("parser") if isinstance(url_quality_gate, dict) else None
        ),
        "url_quality": url_quality if isinstance(url_quality, dict) else None,
        "url_quality_gate": url_quality_gate if isinstance(url_quality_gate, dict) else None,
    }


def _page_metadata_dict(metadata: PageMetadata | None) -> dict[str, str | None]:
    if metadata is None:
        return {}
    return metadata.model_dump(mode="json")


def _asset_dict(asset: Asset) -> dict[str, Any]:
    return asset.model_dump(mode="json")


def _source_slug(source: str) -> str:
    slug = slugify(source)[:80].strip("-") or "source"
    return f"{slug}_{short_hash(source)}"


def _path_text(path: Path) -> str:
    resolved_path = path.resolve(strict=False)
    try:
        return resolved_path.relative_to(Path.cwd().resolve(strict=False)).as_posix()
    except ValueError:
        return resolved_path.as_posix()


def _path_text_optional(path: Path | None) -> str | None:
    return _path_text(path) if path is not None else None
