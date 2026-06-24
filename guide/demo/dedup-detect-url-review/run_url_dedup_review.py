"""Guide-only URL ingestion + dedup detection review.

This script intentionally lives under guide/ so URL ingestion and dedup detection
can be tested together without changing src/agentic_rag.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
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
from agentic_rag.ingestion.url.loader import load_url_with_artifacts

DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "output"


@dataclass(frozen=True)
class UrlIngestionSummary:
    """Small serializable summary for one URL ingestion attempt."""

    index: int
    url: str
    ok: bool
    chunk_count: int
    markdown_chars: int
    parser: str | None = None
    artifact_dir: str | None = None
    error: str | None = None


def main() -> None:
    args = _parse_args()
    urls = _load_urls(args.urls, urls_file=args.urls_file)
    if not urls:
        raise SystemExit("Provide at least one URL or --urls-file.")

    output_dir = args.output_dir
    artifact_dir = output_dir / "artifacts"
    debug_dir = output_dir / "debug"
    output_dir.mkdir(parents=True, exist_ok=True)

    summaries: list[UrlIngestionSummary] = []
    chunks: list[Chunk] = []

    for index, url in enumerate(urls, start=1):
        run_id = f"url-dedup-review-{index}"
        try:
            loaded = load_url_with_artifacts(
                url,
                debug_artifact_dir=debug_dir,
                data_artifact_dir=artifact_dir,
                run_id=run_id,
                use_browser_extractor=not args.no_browser,
            )
        except Exception as exc:
            summaries.append(
                UrlIngestionSummary(
                    index=index,
                    url=url,
                    ok=False,
                    chunk_count=0,
                    markdown_chars=0,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
            continue

        source_chunks = [
            _with_review_metadata(chunk, input_url=url, url_index=index) for chunk in loaded.chunks
        ]
        chunks.extend(source_chunks)
        summaries.append(
            UrlIngestionSummary(
                index=index,
                url=url,
                ok=True,
                chunk_count=len(source_chunks),
                markdown_chars=len(loaded.markdown),
                parser=_artifact_parser(loaded.artifacts),
                artifact_dir=_artifact_dir(loaded.artifacts),
            )
        )

    config = DedupConfig(
        enable_exact=not args.disable_exact,
        enable_simhash=not args.disable_simhash,
        enable_embedding=args.enable_embedding,
        simhash_hamming_threshold=args.simhash_threshold,
        embedding_similarity_threshold=args.embedding_threshold,
        embedding_method="configured-project-embedding" if args.enable_embedding else None,
    )
    documents = documents_from_chunks(chunks)
    report = detect_duplicates(documents, config=config)
    enriched_chunks = add_duplicate_metadata_to_chunks(chunks, report)
    metadata_contract = chunk_metadata_contract_summary(chunks)

    _write_jsonl(output_dir / "chunks_with_dedup.jsonl", enriched_chunks)
    _write_json(output_dir / "metadata_contract.json", metadata_contract)
    _write_json(
        output_dir / "dedup_report.json",
        {
            "urls": [summary.__dict__ for summary in summaries],
            "metadata_contract": metadata_contract,
            "config": config.model_dump(mode="json"),
            "dedup_report": report.model_dump(mode="json"),
        },
    )
    _write_markdown_review(
        output_dir / "dedup_review.md",
        summaries=summaries,
        chunks=enriched_chunks,
        config=config,
        report=report,
        metadata_contract=metadata_contract,
    )

    print(f"Wrote {output_dir / 'dedup_review.md'}")
    print(f"Wrote {output_dir / 'metadata_contract.json'}")
    print(f"Wrote {output_dir / 'dedup_report.json'}")
    print(f"Wrote {output_dir / 'chunks_with_dedup.jsonl'}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest multiple URLs, chunk them, and run dedup detection."
    )
    parser.add_argument("urls", nargs="*", help="URL values to ingest.")
    parser.add_argument(
        "--urls-file",
        type=Path,
        help="Plain text file with one URL per line. Blank lines and # comments are ignored.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for review outputs.",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Skip browser extraction and use the static URL ingestion path.",
    )
    parser.add_argument(
        "--disable-exact",
        action="store_true",
        help="Disable Layer 1 exact duplicate detection.",
    )
    parser.add_argument(
        "--disable-simhash",
        action="store_true",
        help="Disable Layer 2 SimHash near-duplicate detection.",
    )
    parser.add_argument(
        "--simhash-threshold",
        type=int,
        default=6,
        help="Layer 2 SimHash Hamming distance threshold.",
    )
    parser.add_argument(
        "--enable-embedding",
        action="store_true",
        help="Enable Layer 3 embedding similarity using project EMBEDDING_* config.",
    )
    parser.add_argument(
        "--embedding-threshold",
        type=float,
        default=0.92,
        help="Layer 3 cosine similarity threshold.",
    )
    return parser.parse_args()


def _load_urls(urls: list[str], *, urls_file: Path | None) -> list[str]:
    loaded_urls = [url.strip() for url in urls if url.strip()]
    if urls_file is None:
        return _dedupe_preserve_order(loaded_urls)

    file_urls: list[str] = []
    for line in urls_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        file_urls.append(stripped)
    return _dedupe_preserve_order([*loaded_urls, *file_urls])


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _with_review_metadata(chunk: Chunk, *, input_url: str, url_index: int) -> Chunk:
    return chunk.model_copy(
        update={
            "metadata": {
                **chunk.metadata,
                "review_input_url": input_url,
                "review_url_index": url_index,
            }
        }
    )


def _artifact_parser(artifacts: Any) -> str | None:
    manifest = getattr(artifacts, "manifest", None)
    if manifest is None:
        return None
    parser = getattr(manifest, "parser", None)
    return str(parser) if parser else None


def _artifact_dir(artifacts: Any) -> str | None:
    if artifacts is None:
        return None
    manifest_path = getattr(artifacts, "manifest_path", None)
    if manifest_path is None:
        return None
    return str(Path(manifest_path).parent)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _write_jsonl(path: Path, chunks: list[Chunk]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for chunk in chunks:
            handle.write(json.dumps(chunk.model_dump(mode="json"), ensure_ascii=False))
            handle.write("\n")


def _write_markdown_review(
    path: Path,
    *,
    summaries: list[UrlIngestionSummary],
    chunks: list[Chunk],
    config: DedupConfig,
    report: Any,
    metadata_contract: dict[str, Any],
) -> None:
    chunk_by_id = {chunk.chunk_id: chunk for chunk in chunks}
    lines = [
        "# URL Dedup Detection Review",
        "",
        "## Inputs",
        "",
        f"- URL count: {len(summaries)}",
        f"- Total chunks: {len(chunks)}",
        f"- Exact enabled: {config.enable_exact}",
        f"- SimHash enabled: {config.enable_simhash}",
        f"- Embedding enabled: {config.enable_embedding}",
        f"- SimHash threshold: {config.simhash_hamming_threshold}",
        f"- Embedding threshold: {config.embedding_similarity_threshold}",
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
        "## URL Ingestion Summary",
        "",
        "| # | Status | Chunks | Markdown chars | Parser | URL |",
        "| ---: | --- | ---: | ---: | --- | --- |",
    ]
    for summary in summaries:
        status = "ok" if summary.ok else "failed"
        parser = summary.parser or ""
        lines.append(
            "| "
            f"{summary.index} | {status} | {summary.chunk_count} | "
            f"{summary.markdown_chars} | {_escape_table(parser)} | "
            f"{_escape_table(summary.url)} |"
        )
        if summary.error:
            lines.append(f"|  | error |  |  | {_escape_table(summary.error)} |  |")

    lines.extend(
        [
            "",
            "## Duplicate Counts",
            "",
            f"- Exact matches: {len(report.exact_matches)}",
            f"- SimHash matches: {len(report.simhash_matches)}",
            f"- Embedding matches: {len(report.embedding_matches)}",
            "",
        ]
    )
    _append_match_section(lines, "Exact Matches", report.exact_matches, chunk_by_id)
    _append_match_section(lines, "SimHash Matches", report.simhash_matches, chunk_by_id)
    _append_match_section(
        lines,
        "Embedding Matches",
        report.embedding_matches,
        chunk_by_id,
    )
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def _format_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "none"
    return ", ".join(f"{key}={value}" for key, value in counts.items())


def _append_match_section(
    lines: list[str],
    title: str,
    matches: list[Any],
    chunk_by_id: dict[str, Chunk],
) -> None:
    lines.extend(
        [
            f"## {title}",
            "",
        ]
    )
    if not matches:
        lines.extend(["No matches.", ""])
        return
    lines.extend(
        [
            (
                "| Layer | Score | Distance | Left chunk | Right chunk | "
                "Left preview | Right preview |"
            ),
            "| --- | ---: | ---: | --- | --- | --- | --- |",
        ]
    )
    for match in matches[:100]:
        left = chunk_by_id.get(match.document_id)
        right = chunk_by_id.get(match.duplicate_document_id)
        lines.append(
            "| "
            f"{match.layer} | {match.score:.4f} | {match.distance or ''} | "
            f"{_escape_table(match.document_id)} | "
            f"{_escape_table(match.duplicate_document_id)} | "
            f"{_escape_table(_preview(left.text if left else ''))} | "
            f"{_escape_table(_preview(right.text if right else ''))} |"
        )
    if len(matches) > 100:
        lines.append("")
        lines.append(f"Only showing first 100 of {len(matches)} matches.")
    lines.append("")


def _preview(text: str, limit: int = 180) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: limit - 3]}..."


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


if __name__ == "__main__":
    main()
