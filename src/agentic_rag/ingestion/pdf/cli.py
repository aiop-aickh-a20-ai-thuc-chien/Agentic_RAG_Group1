"""Command line interface for local PDF parser inspection."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from agentic_rag.ingestion.pdf.artifacts import save_loaded_pdf_ingestion_artifacts
from agentic_rag.ingestion.pdf.config import PdfIngestionConfig
from agentic_rag.ingestion.pdf.loader import LoadedPdfDocument, load_pdf_with_markdown


def main(argv: Sequence[str] | None = None) -> int:
    """Run local PDF parser helper commands."""

    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "parse":
        return _parse_pdf(args)
    parser.print_help()
    return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pdf-parser",
        description="Local PDF parser inspection helpers.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    parse_parser = subparsers.add_parser(
        "parse",
        help="Parse one local PDF file and emit JSON summary output.",
    )
    parse_parser.add_argument("path", type=Path, help="Path to a local PDF file.")
    parse_parser.add_argument("--pipeline", dest="pipeline_name")
    parse_parser.add_argument("--strategy", dest="strategy_name")
    parse_parser.add_argument("--parser", dest="parser_name")
    parse_parser.add_argument("--chunker", dest="chunker_name")
    parse_parser.add_argument("--include-markdown", action="store_true")
    parse_parser.add_argument("--max-chunks", type=int, default=None)
    parse_parser.add_argument("--output-json", action="store_true")
    parse_parser.add_argument(
        "--write-artifacts",
        action="store_true",
        help="Write parsed.md, chunks.jsonl, chunks.md, and manifest.json for local debugging.",
    )
    parse_parser.add_argument("--output-root", type=Path)
    parse_parser.add_argument("--run-id")
    return parser


def _parse_pdf(args: argparse.Namespace) -> int:
    config = PdfIngestionConfig.from_env()
    pipeline_name = args.pipeline_name or config.pipeline_name
    strategy_name = args.strategy_name or config.strategy_name
    parser_name = args.parser_name
    chunker_name = args.chunker_name or config.chunker_name

    loaded = load_pdf_with_markdown(
        str(args.path),
        parser_name=parser_name,
        pipeline_name=pipeline_name,
        strategy_name=strategy_name,
        chunker_name=chunker_name,
    )
    if args.write_artifacts and not args.output_json:
        manifest = save_loaded_pdf_ingestion_artifacts(
            args.path,
            loaded,
            output_root=args.output_root,
            run_id=args.run_id,
        )
        print(f"Wrote parser artifacts to {manifest.run_dir}")
        return 0

    payload = _loaded_pdf_payload(
        path=args.path,
        loaded=loaded,
        include_markdown=args.include_markdown,
        max_chunks=args.max_chunks,
    )
    if args.write_artifacts:
        payload["artifacts"] = save_loaded_pdf_ingestion_artifacts(
            args.path,
            loaded,
            output_root=args.output_root,
            run_id=args.run_id,
        ).model_dump(mode="json")
    _write_payload(
        payload,
        force_json=args.output_json,
    )
    return 0


def _loaded_pdf_payload(
    *,
    path: Path,
    loaded: LoadedPdfDocument,
    include_markdown: bool,
    max_chunks: int | None,
) -> dict[str, Any]:
    chunks = loaded.chunks if max_chunks is None else loaded.chunks[:max_chunks]
    payload: dict[str, Any] = {
        "path": str(path),
        "pipeline": loaded.pipeline,
        "strategy": loaded.strategy,
        "parser": loaded.parser,
        "chunker": loaded.chunker,
        "markdown_chars": len(loaded.markdown),
        "chunk_count": len(loaded.chunks),
        "returned_chunk_count": len(chunks),
        "chunks": [chunk.model_dump(mode="json") for chunk in chunks],
    }
    if include_markdown:
        payload["markdown"] = loaded.markdown
    else:
        payload["markdown_preview"] = loaded.markdown[:1000]
    return payload


def _write_payload(
    payload: dict[str, Any],
    *,
    force_json: bool,
) -> None:
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    if force_json:
        print(serialized)
        return
    print(serialized)


if __name__ == "__main__":
    raise SystemExit(main())
