"""Artifact persistence for URL ingestion."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.url.chunking import short_hash, slugify
from agentic_rag.ingestion.url.parser import Asset, PageMetadata


@dataclass(frozen=True)
class DebugArtifact:
    """A debug artifact that can be written to a local directory."""

    name: str
    content: str


@dataclass(frozen=True)
class IngestionArtifacts:
    """Paths for persisted URL ingestion artifacts."""

    run_dir: Path
    markdown_path: Path
    chunks_path: Path
    manifest_path: Path


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
) -> IngestionArtifacts | None:
    """Persist parsed Markdown, chunks JSONL, and manifest for one URL run."""

    if data_dir is None:
        return None

    artifact_root = Path(data_dir) / "artifacts"
    run_dir = artifact_root / _source_slug(source) / slugify(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    chunk_list = list(chunks)
    markdown_path = run_dir / "parsed.md"
    chunks_path = run_dir / "chunks.jsonl"
    manifest_path = run_dir / "manifest.json"

    markdown_path.write_text(markdown.rstrip() + "\n", encoding="utf-8")
    chunks_path.write_text(_serialize_chunks_jsonl(chunk_list), encoding="utf-8")

    manifest = {
        "artifact_schema_version": 1,
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
        "markdown_path": _path_text(markdown_path),
        "chunks_path": _path_text(chunks_path),
        "manifest_path": _path_text(manifest_path),
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
    )


def _validate_artifact_name(name: str) -> str:
    if not name or Path(name).name != name:
        raise ValueError("Debug artifact name must be a plain file name.")
    return name


def _serialize_chunks_jsonl(chunks: Iterable[Chunk]) -> str:
    lines = [json.dumps(chunk.model_dump(mode="json"), ensure_ascii=False) for chunk in chunks]
    return "\n".join(lines) + ("\n" if lines else "")


def _page_metadata_dict(metadata: PageMetadata | None) -> dict[str, str | None]:
    if metadata is None:
        return {}
    return asdict(metadata)


def _asset_dict(asset: Asset) -> dict[str, Any]:
    return asdict(asset)


def _source_slug(source: str) -> str:
    slug = slugify(source)[:80].strip("-") or "source"
    return f"{slug}_{short_hash(source)}"


def _path_text(path: Path) -> str:
    resolved_path = path.resolve(strict=False)
    try:
        return resolved_path.relative_to(Path.cwd().resolve(strict=False)).as_posix()
    except ValueError:
        return resolved_path.as_posix()
