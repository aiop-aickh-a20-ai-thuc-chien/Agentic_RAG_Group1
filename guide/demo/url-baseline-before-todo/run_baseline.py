"""Capture current URL ingestion output before TODO-driven changes."""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.url import load_url_with_artifacts
from agentic_rag.ingestion.url.chunking import is_usable_chunk_text, slugify

DEFAULT_URLS = (
    "https://vinfastauto.com/vn_vi",
    "https://vinfastauto.com/vn_vi/hop-dong-va-chinh-sach/chinh-sach",
    "https://shop.vinfastauto.com/vn_vi/dat-mua-xe-may-dien-vinfast",
)

DEFAULT_OUTPUT_DIR = Path("guide/demo/url-baseline-before-todo/output/base_current")
DEFAULT_RUN_ID = "baseline_before_todo"


def main() -> int:
    args = _parse_args()
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    started_at = _utc_now()
    for index, url in enumerate(args.urls, start=1):
        result = _capture_url(
            url,
            index=index,
            output_dir=output_dir,
            run_id=args.run_id,
            use_browser_extractor=not args.no_browser,
        )
        results.append(result)

    summary = {
        "demo": "url-baseline-before-todo",
        "purpose": (
            "Base current URL ingestion results before implementing "
            "src/agentic_rag/ingestion/url/TODO.md live-case changes."
        ),
        "started_at": started_at,
        "finished_at": _utc_now(),
        "run_id": args.run_id,
        "use_browser_extractor": not args.no_browser,
        "urls": list(args.urls),
        "result_count": len(results),
        "success_count": sum(1 for item in results if item["status"] == "success"),
        "error_count": sum(1 for item in results if item["status"] == "error"),
        "results": results,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "summary.md").write_text(_summary_markdown(summary), encoding="utf-8")
    print(f"Wrote URL baseline to {output_dir}")
    return 0 if summary["error_count"] == 0 else 1


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory. Default: {DEFAULT_OUTPUT_DIR}",
    )
    parser.add_argument(
        "--run-id",
        default=DEFAULT_RUN_ID,
        help=f"Stable artifact run id. Default: {DEFAULT_RUN_ID}",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Disable rendered Playwright extraction and capture static baseline only.",
    )
    parser.add_argument(
        "urls",
        nargs="*",
        default=list(DEFAULT_URLS),
        help="URLs to capture. Defaults to the three TODO live VinFast cases.",
    )
    return parser.parse_args()


def _capture_url(
    url: str,
    *,
    index: int,
    output_dir: Path,
    run_id: str,
    use_browser_extractor: bool,
) -> dict[str, Any]:
    url_dir = output_dir / f"url_{index:02d}_{_url_slug(url)}"
    url_dir.mkdir(parents=True, exist_ok=True)
    try:
        loaded = load_url_with_artifacts(
            url,
            data_artifact_dir=url_dir,
            debug_artifact_dir=url_dir / "debug",
            render_cache_dir=output_dir / "render_cache",
            run_id=run_id,
            use_browser_extractor=use_browser_extractor,
        )
    except Exception as exc:
        result = {
            "status": "error",
            "url": url,
            "error_type": exc.__class__.__name__,
            "error": str(exc),
            "output_dir": _path_text(url_dir),
        }
        _write_result(url_dir, result)
        return result

    chunks = loaded.chunks
    manifest = _artifact_manifest(loaded.artifacts.manifest_path if loaded.artifacts else None)
    result = {
        "status": "success",
        "url": url,
        "output_dir": _path_text(url_dir),
        "markdown_char_count": len(loaded.markdown),
        "markdown_word_count": _word_count(loaded.markdown),
        "markdown_preview": _preview(loaded.markdown, max_chars=1200),
        "chunk_count": len(chunks),
        "usable_chunk_count": sum(1 for chunk in chunks if is_usable_chunk_text(chunk.text)),
        "artifact_paths": _artifact_paths(loaded.artifacts),
        "manifest": manifest,
        "asset_count": len(manifest.get("assets", [])) if isinstance(manifest, dict) else 0,
        "pdf_asset_count": _asset_count(manifest, kind="pdf"),
        "metadata_summary": _metadata_summary(chunks),
        "todo_gap_summary": _todo_gap_summary(chunks, manifest),
        "chunk_previews": [_chunk_preview(chunk) for chunk in chunks[:10]],
    }
    _write_result(url_dir, result)
    return result


def _metadata_summary(chunks: list[Chunk]) -> dict[str, Any]:
    if not chunks:
        return {}
    first_metadata = chunks[0].metadata
    return {
        "first_chunk_source": first_metadata.get("source"),
        "first_chunk_source_type": first_metadata.get("source_type"),
        "first_chunk_url": first_metadata.get("url"),
        "first_chunk_document_type": first_metadata.get("document_type"),
        "first_chunk_page_type": first_metadata.get("page_type"),
        "first_chunk_url_status": first_metadata.get("url_status"),
        "first_chunk_render_required": first_metadata.get("render_required"),
        "first_chunk_quality_gate": first_metadata.get("url_quality_gate"),
        "document_type_counts": _count_metadata_values(chunks, "document_type"),
        "page_type_counts": _count_metadata_values(chunks, "page_type"),
        "source_type_counts": _count_metadata_values(chunks, "source_type"),
        "section_kind_counts": _count_metadata_values(chunks, "section_kind"),
        "section_origin_counts": _count_metadata_values(chunks, "section_origin"),
        "has_product_specs": any(bool(chunk.metadata.get("product_specs")) for chunk in chunks),
        "has_interaction_state": any("interaction_state" in chunk.metadata for chunk in chunks),
    }


def _todo_gap_summary(chunks: list[Chunk], manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "has_section_kind": any("section_kind" in chunk.metadata for chunk in chunks),
        "has_section_origin": any("section_origin" in chunk.metadata for chunk in chunks),
        "has_evidence_source": any("evidence_source" in chunk.metadata for chunk in chunks),
        "has_interaction_state": any("interaction_state" in chunk.metadata for chunk in chunks),
        "has_pdf_assets": _asset_count(manifest, kind="pdf") > 0,
        "pdf_asset_count": _asset_count(manifest, kind="pdf"),
        "note": (
            "These flags describe the current baseline before TODO.md changes. "
            "Expected future improvements include PDF-link routing and "
            "static/dynamic section provenance."
        ),
    }


def _chunk_preview(chunk: Chunk) -> dict[str, Any]:
    metadata = chunk.metadata
    return {
        "chunk_id": chunk.chunk_id,
        "is_usable": is_usable_chunk_text(chunk.text),
        "text_preview": _preview(chunk.text, max_chars=800),
        "metadata": {
            "source": metadata.get("source"),
            "source_type": metadata.get("source_type"),
            "url": metadata.get("url"),
            "document_type": metadata.get("document_type"),
            "page_type": metadata.get("page_type"),
            "section": metadata.get("section"),
            "heading": metadata.get("heading"),
            "breadcrumb": metadata.get("breadcrumb"),
            "url_status": metadata.get("url_status"),
            "render_required": metadata.get("render_required"),
            "section_kind": metadata.get("section_kind"),
            "section_origin": metadata.get("section_origin"),
            "evidence_source": metadata.get("evidence_source"),
            "product_model": metadata.get("product_model"),
            "product_price": metadata.get("product_price"),
            "driving_range": metadata.get("driving_range"),
            "interaction_state": metadata.get("interaction_state"),
            "asset_ids": metadata.get("asset_ids"),
        },
    }


def _artifact_paths(artifacts: object | None) -> dict[str, str | None]:
    if artifacts is None:
        return {}
    names = (
        "run_dir",
        "markdown_path",
        "chunks_path",
        "manifest_path",
        "source_html_path",
        "cleaned_html_path",
        "parsed_sections_path",
        "extracted_markdown_path",
        "quality_path",
    )
    return {name: _path_text(getattr(artifacts, name)) for name in names}


def _artifact_manifest(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _asset_count(manifest: dict[str, Any], *, kind: str) -> int:
    assets = manifest.get("assets", []) if isinstance(manifest, dict) else []
    if not isinstance(assets, list):
        return 0
    return sum(1 for asset in assets if isinstance(asset, dict) and asset.get("kind") == kind)


def _count_metadata_values(chunks: list[Chunk], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for chunk in chunks:
        value = chunk.metadata.get(key)
        label = str(value) if value not in (None, "") else "missing"
        counts[label] = counts.get(label, 0) + 1
    return dict(sorted(counts.items()))


def _write_result(url_dir: Path, result: dict[str, Any]) -> None:
    (url_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _summary_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# URL Baseline Before TODO Changes",
        "",
        f"- Started at: {summary['started_at']}",
        f"- Finished at: {summary['finished_at']}",
        f"- Run id: `{summary['run_id']}`",
        f"- Browser extraction enabled: `{summary['use_browser_extractor']}`",
        f"- Success count: {summary['success_count']}",
        f"- Error count: {summary['error_count']}",
        "",
        "## Results",
        "",
    ]
    for item in summary["results"]:
        lines.extend(_result_markdown(item))
    return "\n".join(lines).rstrip() + "\n"


def _result_markdown(item: dict[str, Any]) -> list[str]:
    lines = [f"### {item['url']}", ""]
    lines.append(f"- Status: `{item['status']}`")
    lines.append(f"- Output dir: `{item['output_dir']}`")
    if item["status"] == "error":
        lines.append(f"- Error: `{item['error_type']}: {item['error']}`")
        lines.append("")
        return lines
    metadata = item["metadata_summary"]
    gaps = item["todo_gap_summary"]
    lines.extend(
        [
            f"- Markdown words: {item['markdown_word_count']}",
            f"- Chunks: {item['chunk_count']}",
            f"- Usable chunks: {item['usable_chunk_count']}",
            f"- Assets: {item['asset_count']}",
            f"- PDF assets: {item['pdf_asset_count']}",
            f"- Source type counts: `{metadata.get('source_type_counts')}`",
            f"- Document type counts: `{metadata.get('document_type_counts')}`",
            f"- Page type counts: `{metadata.get('page_type_counts')}`",
            f"- Has product specs: `{metadata.get('has_product_specs')}`",
            f"- Has interaction state: `{metadata.get('has_interaction_state')}`",
            f"- Has section_kind: `{gaps.get('has_section_kind')}`",
            f"- Has section_origin: `{gaps.get('has_section_origin')}`",
            f"- Has evidence_source: `{gaps.get('has_evidence_source')}`",
            "",
        ]
    )
    return lines


def _url_slug(url: str) -> str:
    return slugify(url)[:60].strip("-") or "url"


def _preview(text: str, *, max_chars: int) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= max_chars:
        return compact
    return f"{compact[: max_chars - 3]}..."


def _word_count(text: str) -> int:
    return len(re.findall(r"\w+", text, flags=re.UNICODE))


def _path_text(path: object | None) -> str | None:
    if path is None:
        return None
    path_obj = Path(path)
    resolved = path_obj.resolve(strict=False)
    try:
        return resolved.relative_to(Path.cwd().resolve(strict=False)).as_posix()
    except ValueError:
        return resolved.as_posix()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
