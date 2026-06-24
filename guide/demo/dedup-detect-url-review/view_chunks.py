"""Create readable chunk views from chunks_with_dedup.jsonl."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any

DEFAULT_INPUT = Path(__file__).resolve().parent / "output" / "chunks_with_dedup.jsonl"


def main() -> None:
    args = _parse_args()
    chunks = _read_jsonl(args.input)
    if not chunks:
        raise SystemExit(f"No chunks found in {args.input}")

    markdown_path = args.output_dir / "chunks_readable.md"
    html_path = args.output_dir / "chunks_readable.html"
    args.output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(_render_markdown(chunks), encoding="utf-8")
    html_path.write_text(_render_html(chunks), encoding="utf-8")

    print(f"Wrote {markdown_path}")
    print(f"Wrote {html_path}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render chunks_with_dedup.jsonl as readable Markdown and HTML."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help="Path to chunks_with_dedup.jsonl.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_INPUT.parent,
        help="Directory where readable chunk views are written.",
    )
    return parser.parse_args()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            chunks.append(json.loads(stripped))
    return chunks


def _render_markdown(chunks: list[dict[str, Any]]) -> str:
    lines = [
        "# Readable URL Dedup Chunks",
        "",
        f"Chunk count: {len(chunks)}",
        "",
        "## Index",
        "",
        "| # | Duplicate | Source | Section | Chunk ID |",
        "| ---: | --- | --- | --- | --- |",
    ]
    for index, chunk in enumerate(chunks, start=1):
        metadata = _metadata(chunk)
        dedup = metadata.get("deduplication") or {}
        source = (
            metadata.get("review_input_url") or metadata.get("url") or metadata.get("source") or ""
        )
        section = metadata.get("section") or ""
        duplicate = "yes" if dedup.get("has_duplicate") else "no"
        lines.append(
            "| "
            f"{index} | {duplicate} | {_escape_table(str(source))} | "
            f"{_escape_table(str(section))} | {_escape_table(str(chunk.get('chunk_id', '')))} |"
        )

    lines.append("")
    lines.append("## Chunks")
    lines.append("")
    for index, chunk in enumerate(chunks, start=1):
        metadata = _metadata(chunk)
        dedup = metadata.get("deduplication") or {}
        lines.extend(
            [
                f"### Chunk {index}",
                "",
                f"- chunk_id: `{chunk.get('chunk_id', '')}`",
                f"- source: {metadata.get('review_input_url') or metadata.get('url') or metadata.get('source') or ''}",
                f"- section: {metadata.get('section') or ''}",
                f"- duplicate: {bool(dedup.get('has_duplicate'))}",
                f"- detected_layers: {', '.join(dedup.get('detected_layers') or [])}",
                "",
                "```text",
                str(chunk.get("text", "")).strip(),
                "```",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def _render_html(chunks: list[dict[str, Any]]) -> str:
    cards = []
    for index, chunk in enumerate(chunks, start=1):
        metadata = _metadata(chunk)
        dedup = metadata.get("deduplication") or {}
        source = (
            metadata.get("review_input_url") or metadata.get("url") or metadata.get("source") or ""
        )
        section = metadata.get("section") or ""
        layers = ", ".join(dedup.get("detected_layers") or [])
        duplicate = bool(dedup.get("has_duplicate"))
        cards.append(
            f"""
<article class="chunk {"duplicate" if duplicate else ""}">
  <header>
    <h2>Chunk {index}</h2>
    <span class="badge">{"duplicate" if duplicate else "unique"}</span>
  </header>
  <dl>
    <dt>Chunk ID</dt><dd><code>{html.escape(str(chunk.get("chunk_id", "")))}</code></dd>
    <dt>Source</dt><dd>{html.escape(str(source))}</dd>
    <dt>Section</dt><dd>{html.escape(str(section))}</dd>
    <dt>Layers</dt><dd>{html.escape(layers)}</dd>
  </dl>
  <pre>{html.escape(str(chunk.get("text", "")).strip())}</pre>
</article>
""".strip()
        )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Readable URL Dedup Chunks</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; line-height: 1.45; }}
    .summary {{ margin-bottom: 16px; }}
    .chunk {{ border: 1px solid #d0d7de; border-radius: 8px; padding: 16px; margin: 16px 0; }}
    .chunk.duplicate {{ border-color: #d29922; background: #fff8c5; }}
    header {{ display: flex; justify-content: space-between; gap: 12px; align-items: center; }}
    h1, h2 {{ margin: 0 0 12px; }}
    .badge {{ border: 1px solid #d0d7de; border-radius: 999px; padding: 2px 10px; font-size: 12px; }}
    dl {{ display: grid; grid-template-columns: 120px 1fr; gap: 6px 12px; }}
    dt {{ font-weight: 700; }}
    dd {{ margin: 0; overflow-wrap: anywhere; }}
    pre {{ white-space: pre-wrap; overflow-wrap: anywhere; background: #f6f8fa; padding: 12px; border-radius: 6px; }}
  </style>
</head>
<body>
  <h1>Readable URL Dedup Chunks</h1>
  <p class="summary">Chunk count: {len(chunks)}</p>
  {"".join(cards)}
</body>
</html>
"""


def _metadata(chunk: dict[str, Any]) -> dict[str, Any]:
    metadata = chunk.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


if __name__ == "__main__":
    main()
