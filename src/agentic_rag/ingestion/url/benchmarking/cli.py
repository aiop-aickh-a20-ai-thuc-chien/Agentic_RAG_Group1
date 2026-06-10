"""Command line interface for local URL and HTML benchmark helpers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from agentic_rag.ingestion.url.benchmarking.custom_benchmark import (
    parse_html_builtin,
    report_to_dict,
    run_custom_benchmark,
)


def main(argv: list[str] | None = None) -> int:
    """Run URL ingestion benchmark helper commands."""

    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    custom_parser = subparsers.add_parser(
        "custom",
        help="Run built-in custom HTML parser benchmark cases.",
    )
    custom_parser.add_argument("--parser", default="builtin", choices=["builtin"])
    custom_parser.add_argument("--output", type=Path, help="Optional JSON output file.")

    parse_parser = subparsers.add_parser(
        "parse-html",
        help="Parse one local HTML file and emit benchmark-friendly JSON output.",
    )
    parse_parser.add_argument("--html-file", type=Path, required=True)
    parse_parser.add_argument("--source-url", default=None)
    parse_parser.add_argument("--output", type=Path, help="Optional JSON output file.")

    args = parser.parse_args(argv)
    if args.command == "custom":
        payload = report_to_dict(run_custom_benchmark(parser_name=args.parser))
    elif args.command == "parse-html":
        payload = _parse_html_file(args.html_file, args.source_url)
    else:
        parser.error(f"Unsupported command: {args.command}")

    _write_payload(payload, args.output)
    return 0


def _parse_html_file(path: Path, source_url: str | None) -> dict[str, Any]:
    html = path.read_text(encoding="utf-8")
    output = parse_html_builtin(html)
    return {
        "parser": output.parser,
        "source": source_url or str(path),
        "source_type": "html",
        "extracted_chars": len(output.text),
        "sections": list(output.sections),
        "text": output.text,
    }


def _write_payload(payload: dict[str, Any], output_path: Path | None) -> None:
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    if output_path is None:
        print(serialized)
        return
    output_path.write_text(serialized + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
