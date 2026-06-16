"""Run a local PDF ingestion review and write inspection artifacts."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.dedup_detect import chunk_metadata_contract_summary
from agentic_rag.ingestion.pdf import (
    LoadedPdfDocument,
    load_pdf_with_markdown,
    save_loaded_pdf_ingestion_artifacts,
)

DEFAULT_OUTPUT_DIR = Path("guide/demo/pdf-review/output")


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    pdf_path = Path(args.pdf_path)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        loaded = load_pdf_with_markdown(
            str(pdf_path),
            pipeline_name=args.pipeline,
            strategy_name=args.strategy,
            parser_name=args.parser,
            chunker_name=args.chunker,
        )
        artifact_manifest = save_loaded_pdf_ingestion_artifacts(
            pdf_path,
            loaded,
            output_root=output_dir / "artifacts",
            run_id=args.run_id,
        )
        summary = _review_summary(
            pdf_path=pdf_path,
            loaded=loaded,
            artifacts=artifact_manifest.model_dump(mode="json"),
            max_chunks=args.max_chunks,
        )
    except Exception as exc:
        summary = _error_summary(pdf_path=pdf_path, exc=exc)

    summary_path = output_dir / "review_summary.json"
    report_path = output_dir / "review_report.md"
    _write_json(summary_path, summary)
    report_path.write_text(_review_markdown(summary), encoding="utf-8")

    print(f"Wrote PDF review summary to {summary_path}")
    print(f"Wrote PDF review report to {report_path}")
    return 0 if summary["review_status"] == "pass" else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Review one local PDF through the current PDF ingestion path."
    )
    parser.add_argument("pdf_path", help="Path to a local PDF file.")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help=f"Directory for review outputs. Default: {DEFAULT_OUTPUT_DIR}",
    )
    parser.add_argument("--run-id", default=None, help="Optional stable artifact run id.")
    parser.add_argument("--pipeline", default=None, help="PDF parser pipeline override.")
    parser.add_argument("--strategy", default=None, help="PDF parser strategy override.")
    parser.add_argument("--parser", default=None, help="Legacy parser alias.")
    parser.add_argument(
        "--chunker",
        default="deterministic",
        help="PDF chunker name. Default: deterministic.",
    )
    parser.add_argument(
        "--max-chunks",
        type=int,
        default=10,
        help="Maximum chunk previews in the report. Default: 10.",
    )
    return parser


def _review_summary(
    *,
    pdf_path: Path,
    loaded: LoadedPdfDocument,
    artifacts: dict[str, Any],
    max_chunks: int,
) -> dict[str, Any]:
    metadata_contract = chunk_metadata_contract_summary(loaded.chunks)
    checks = {
        "has_markdown": bool(loaded.markdown.strip()),
        "has_chunks": bool(loaded.chunks),
        "metadata_contract_passed": metadata_contract["missing_required_count"] == 0,
    }
    return {
        "review_status": "pass" if all(checks.values()) else "fail",
        "created_at": datetime.now(UTC).isoformat(),
        "pdf_path": str(pdf_path),
        "pipeline": loaded.pipeline,
        "strategy": loaded.strategy,
        "parser": loaded.parser,
        "chunker": loaded.chunker,
        "requested_chunker": loaded.requested_chunker,
        "chunking_fallback_reason": loaded.chunking_fallback_reason,
        "markdown_chars": len(loaded.markdown),
        "markdown_preview": loaded.markdown[:1200],
        "chunk_count": len(loaded.chunks),
        "metadata_contract": metadata_contract,
        "checks": checks,
        "artifacts": artifacts,
        "chunk_previews": [_chunk_preview(chunk) for chunk in loaded.chunks[:max_chunks]],
    }


def _error_summary(*, pdf_path: Path, exc: Exception) -> dict[str, Any]:
    return {
        "review_status": "fail",
        "created_at": datetime.now(UTC).isoformat(),
        "pdf_path": str(pdf_path),
        "error_type": exc.__class__.__name__,
        "error": str(exc),
        "checks": {
            "has_markdown": False,
            "has_chunks": False,
            "metadata_contract_passed": False,
        },
        "metadata_contract": {},
        "artifacts": {},
        "chunk_previews": [],
    }


def _chunk_preview(chunk: Chunk) -> dict[str, Any]:
    metadata = chunk.metadata
    return {
        "chunk_id": chunk.chunk_id,
        "text_preview": chunk.text[:700],
        "source_type": metadata.get("source_type"),
        "updated_date": metadata.get("updated_date"),
        "updated_date_source": metadata.get("updated_date_source"),
        "created_date": metadata.get("created_date"),
        "language": metadata.get("language"),
        "document_type": metadata.get("document_type"),
        "page": metadata.get("page"),
        "page_number": metadata.get("page_number"),
        "heading": metadata.get("heading") or metadata.get("section"),
        "breadcrumb": metadata.get("breadcrumb"),
        "token_count": metadata.get("token_count"),
    }


def _review_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# PDF Review Report",
        "",
        f"- status: {summary.get('review_status')}",
        f"- pdf: {summary.get('pdf_path')}",
        f"- parser: {summary.get('parser')}",
        f"- chunker: {summary.get('chunker')}",
        f"- markdown_chars: {summary.get('markdown_chars')}",
        f"- chunk_count: {summary.get('chunk_count')}",
        "",
        "## Checks",
        "",
    ]
    checks = summary.get("checks") or {}
    for key, value in checks.items():
        lines.append(f"- {key}: {value}")

    metadata_contract = summary.get("metadata_contract") or {}
    lines.extend(
        [
            "",
            "## Metadata Contract",
            "",
            f"- required_fields: {metadata_contract.get('required_fields')}",
            f"- missing_required_count: {metadata_contract.get('missing_required_count')}",
            f"- source_type_counts: {metadata_contract.get('source_type_counts')}",
            f"- document_type_counts: {metadata_contract.get('document_type_counts')}",
            "",
            "## Artifacts",
            "",
        ]
    )
    artifacts = summary.get("artifacts") or {}
    for key in (
        "run_dir",
        "markdown_path",
        "chunks_path",
        "chunks_markdown_path",
        "manifest_path",
    ):
        if artifacts.get(key):
            lines.append(f"- {key}: {artifacts[key]}")

    if summary.get("error"):
        lines.extend(["", "## Error", "", f"- {summary.get('error_type')}: {summary['error']}"])

    lines.extend(["", "## Chunk Previews", ""])
    for chunk in summary.get("chunk_previews") or []:
        lines.extend(
            [
                f"### {chunk['chunk_id']}",
                "",
                f"- source_type: {chunk.get('source_type')}",
                f"- updated_date: {chunk.get('updated_date')}",
                f"- updated_date_source: {chunk.get('updated_date_source')}",
                f"- created_date: {chunk.get('created_date')}",
                f"- language: {chunk.get('language')}",
                f"- page_number: {chunk.get('page_number')}",
                f"- heading: {chunk.get('heading')}",
                "",
                "```text",
                str(chunk.get("text_preview") or "").strip(),
                "```",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
