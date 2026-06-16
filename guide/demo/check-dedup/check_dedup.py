"""Offline shared-metadata + dedup smoke test."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.dedup_detect import (
    DedupConfig,
    add_duplicate_metadata_to_chunks,
    chunk_metadata_contract_summary,
    detect_duplicates,
    documents_from_chunks,
)

DEFAULT_INPUT = Path(__file__).resolve().parent / "sample_chunks.jsonl"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def main() -> None:
    args = _parse_args()
    chunks = _read_chunks(args.input)
    metadata_contract = chunk_metadata_contract_summary(chunks)
    report = detect_duplicates(
        documents_from_chunks(chunks),
        config=DedupConfig(
            enable_exact=True,
            enable_simhash=True,
            enable_embedding=False,
            simhash_hamming_threshold=args.simhash_threshold,
        ),
    )
    enriched_chunks = add_duplicate_metadata_to_chunks(chunks, report)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    _write_json(args.output_dir / "metadata_contract.json", metadata_contract)
    _write_json(args.output_dir / "dedup_report.json", report.model_dump(mode="json"))
    _write_jsonl(args.output_dir / "chunks_with_dedup.jsonl", enriched_chunks)
    (args.output_dir / "check_dedup_report.md").write_text(
        _render_markdown(
            chunks=enriched_chunks,
            metadata_contract=metadata_contract,
            report=report,
        ),
        encoding="utf-8",
    )

    print(f"Wrote {args.output_dir / 'check_dedup_report.md'}")
    print(f"Wrote {args.output_dir / 'metadata_contract.json'}")
    print(f"Wrote {args.output_dir / 'dedup_report.json'}")
    print(f"Wrote {args.output_dir / 'chunks_with_dedup.jsonl'}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check shared metadata and dedup detection on sample chunks."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--simhash-threshold", type=int, default=6)
    return parser.parse_args()


def _read_chunks(path: Path) -> list[Chunk]:
    chunks: list[Chunk] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            chunks.append(Chunk.model_validate(json.loads(stripped)))
    return chunks


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, chunks: list[Chunk]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for chunk in chunks:
            handle.write(json.dumps(chunk.model_dump(mode="json"), ensure_ascii=False))
            handle.write("\n")


def _render_markdown(*, chunks: list[Chunk], metadata_contract: dict[str, Any], report: Any) -> str:
    lines = [
        "# Check Dedup Report",
        "",
        "## Metadata Contract",
        "",
        f"- Required fields: {', '.join(metadata_contract['required_fields'])}",
        (
            f"- Valid chunks: {metadata_contract['valid_chunk_count']} / "
            f"{metadata_contract['chunk_count']}"
        ),
        f"- Missing required metadata: {metadata_contract['missing_required_count']}",
        f"- Source types: {_format_counts(metadata_contract['source_type_counts'])}",
        f"- Document types: {_format_counts(metadata_contract['document_type_counts'])}",
        "",
    ]
    if metadata_contract["issues"]:
        lines.extend(["### Issues", ""])
        for issue in metadata_contract["issues"]:
            lines.append(f"- `{issue['chunk_id']}` missing: {', '.join(issue['missing_required'])}")
        lines.append("")
    lines.extend(
        [
            "## Duplicate Counts",
            "",
            f"- Exact matches: {len(report.exact_matches)}",
            f"- SimHash matches: {len(report.simhash_matches)}",
            f"- Embedding matches: {len(report.embedding_matches)}",
            "",
            "## Chunks",
            "",
            "| Chunk ID | Source type | Document type | Duplicate | Text |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for chunk in chunks:
        metadata = chunk.metadata
        dedup = metadata.get("deduplication") or {}
        lines.append(
            "| "
            f"{_escape(str(chunk.chunk_id))} | "
            f"{_escape(str(metadata.get('source_type') or 'missing'))} | "
            f"{_escape(str(metadata.get('document_type') or 'missing'))} | "
            f"{'yes' if dedup.get('has_duplicate') else 'no'} | "
            f"{_escape(_preview(chunk.text))} |"
        )
    return "\n".join(lines).strip() + "\n"


def _format_counts(counts: dict[str, int]) -> str:
    return ", ".join(f"{key}={value}" for key, value in counts.items()) if counts else "none"


def _preview(text: str, limit: int = 120) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3]}..."


def _escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


if __name__ == "__main__":
    main()
