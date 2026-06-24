from __future__ import annotations

import argparse
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.dedup_detect import (
    DedupConfig,
    add_duplicate_metadata_to_chunks,
    detect_duplicates,
    documents_from_chunks,
)
from agentic_rag.ingestion.url.chunking import is_usable_chunk_text
from agentic_rag.ingestion.url.interactions import (
    InteractionArtifacts,
    InteractionOptions,
    LoadedInteractionDocument,
    detect_interaction_profile,
    load_url_interactions_with_artifacts,
)
from agentic_rag.ingestion.url.loader import LoadedUrlDocument, load_url_with_artifacts

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_DIR = Path("guide/demo/url-crawl-review/output")
DEFAULT_RUN_ID = "url-crawl-review"
PREVIEW_LIMIT = 16000

ARTIFACT_STAGES: tuple[tuple[str, str, str], ...] = (
    (
        "source_html",
        "Source HTML",
        "Raw or rendered HTML snapshot selected by URL ingestion.",
    ),
    (
        "parsed_sections",
        "Parsed Sections",
        "Visible section text after DOM parsing and before Markdown cleanup.",
    ),
    (
        "extracted_markdown",
        "Extracted Markdown",
        "Markdown produced by the extractor before final URL noise cleanup.",
    ),
    (
        "cleaned_html",
        "Cleaned HTML",
        "Semantic HTML rebuilt from final cleaned Markdown, aligned with chunk input.",
    ),
    (
        "cleaned_markdown",
        "Cleaned Markdown",
        "Final parsed.md content used for chunking.",
    ),
    (
        "quality",
        "Quality JSON",
        "URL quality report and quality-gate decision copied from chunk metadata.",
    ),
    (
        "chunks",
        "Chunks JSONL",
        "Serialized Chunk contracts generated from cleaned Markdown.",
    ),
    (
        "manifest",
        "Manifest JSON",
        "Run metadata, parser choice, page metadata, assets, and artifact paths.",
    ),
)

INTERACTION_ARTIFACT_STAGES: tuple[tuple[str, str, str], ...] = (
    (
        "interaction_states",
        "Interaction States",
        "Captured dynamic states from safe JavaScript/UI interaction review.",
    ),
    (
        "interaction_chunks",
        "Interaction Chunks",
        "Debug-only and promoted Chunk contracts generated from captured interaction states.",
    ),
    (
        "interaction_panel_snapshots",
        "Interaction Panel Snapshots",
        "Baseline and before/after snapshots for left, center, right, and unknown panels.",
    ),
    (
        "interaction_panel_diffs",
        "Interaction Panel Diffs",
        "Changed panels and changed fields detected after safe option clicks.",
    ),
    (
        "interaction_manifest",
        "Interaction Manifest",
        "Interaction capture metadata, errors, controls, and artifact paths.",
    ),
    (
        "interaction_source_html",
        "Interaction Source HTML",
        "Rendered HTML snapshot used by interaction capture.",
    ),
    (
        "interaction_network_payloads",
        "Interaction Network Payloads",
        "Bounded JSON/network payload evidence captured during interaction review.",
    ),
)


def main() -> None:
    args = _parse_args()
    payload = run_single_url_review(
        args.url,
        output_dir=Path(args.output_dir),
        use_browser_extractor=not args.no_browser,
        include_interactions=args.include_interactions,
    )
    if args.json_output:
        json_output_path = Path(args.json_output)
        json_output_path.parent.mkdir(parents=True, exist_ok=True)
        json_output_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(payload.get("report_path") or json.dumps(payload, ensure_ascii=False))


def run_single_url_review(
    url: str,
    *,
    output_dir: Path,
    use_browser_extractor: bool = True,
    include_interactions: bool = False,
) -> dict[str, Any]:
    """Run URL ingestion for exactly one URL and return artifact-focused payload."""

    output_dir.mkdir(parents=True, exist_ok=True)
    started_at = _utc_now()
    started = time.perf_counter()
    document: LoadedUrlDocument | None = None
    error: str | None = None
    try:
        document = load_url_with_artifacts(
            url,
            data_artifact_dir=output_dir,
            render_cache_dir=output_dir / "render_cache",
            run_id=DEFAULT_RUN_ID,
            use_browser_extractor=use_browser_extractor,
        )
    except Exception as exc:  # pragma: no cover - exercised by live demo failures.
        error = f"{type(exc).__name__}: {exc}"
    interaction_payload = _interaction_payload(
        url,
        output_dir=output_dir,
        include_interactions=include_interactions,
        use_browser_extractor=use_browser_extractor,
    )

    elapsed_seconds = round(time.perf_counter() - started, 3)
    payload = build_payload(
        url=url,
        document=document,
        error=error,
        interaction=interaction_payload,
        started_at=started_at,
        elapsed_seconds=elapsed_seconds,
        use_browser_extractor=use_browser_extractor,
        include_interactions=include_interactions,
    )
    report_path = output_dir / "artifact_review.md"
    report_path.write_text(build_report(payload), encoding="utf-8")
    payload["report_path"] = _display_path(report_path)
    return payload


def build_payload(
    *,
    url: str,
    document: LoadedUrlDocument | None,
    error: str | None,
    interaction: dict[str, Any],
    started_at: str,
    elapsed_seconds: float,
    use_browser_extractor: bool,
    include_interactions: bool,
) -> dict[str, Any]:
    manifest = _manifest_payload(document)
    quality = _quality_payload(document, manifest)
    dedup = _dedup_payload(document)
    chunks = _chunk_items(document, manifest=manifest, dedup=dedup)
    chunks = _with_interaction_promoted_chunks(chunks, interaction)
    artifact_items = _artifact_items(document, manifest)
    metadata = _first_chunk_metadata(document)
    summary = _summary(
        url=url,
        document=document,
        manifest=manifest,
        quality=quality,
        chunks=chunks,
        artifact_items=artifact_items,
        metadata=metadata,
        error=error,
        use_browser_extractor=use_browser_extractor,
        include_interactions=include_interactions,
        interaction=interaction,
        dedup=dedup,
    )
    return {
        "payload_schema_version": 2,
        "demo": "url-crawl-review",
        "mode": "single_url_artifact_review",
        "url": url,
        "status": summary["status"],
        "error": error,
        "created_at": started_at,
        "elapsed_seconds": elapsed_seconds,
        "use_browser_extractor": use_browser_extractor,
        "include_interactions": include_interactions,
        "summary": summary,
        "interaction": interaction,
        "artifacts": artifact_items,
        "quality": quality,
        "deduplication": dedup,
        "manifest": manifest,
        "chunks": chunks,
        "markdown": document.markdown if document is not None else "",
        "first_chunk_metadata": metadata,
        "report_path": None,
    }


def build_report(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    lines = [
        "# URL Artifact Review",
        "",
        f"- URL: `{payload.get('url', '')}`",
        f"- Status: `{payload.get('status', '')}`",
        f"- Browser extractor: `{payload.get('use_browser_extractor')}`",
        f"- Elapsed seconds: `{payload.get('elapsed_seconds')}`",
        f"- Artifact directory: `{summary.get('artifact_dir') or ''}`",
        "",
        "## Summary",
        "",
    ]
    for key in (
        "chunk_count",
        "usable_chunk_count",
        "markdown_length",
        "parser",
        "source_html_stage",
        "page_type",
        "quality_status",
        "quality_verdict",
        "render_required",
        "valuable_chunk_count",
        "product_fact_chunk_count",
        "entity_chunk_count",
        "noise_chunk_count",
        "average_retrieval_weight",
        "has_valuable_chunks",
        "dedup_exact_match_count",
        "dedup_simhash_match_count",
        "dedup_duplicate_candidate_count",
        "include_interactions",
        "interaction_required",
        "interaction_attempted",
        "interaction_state_count",
        "interaction_debug_chunk_count",
        "interaction_promoted_chunk_count",
        "interaction_panel_snapshot_count",
        "interaction_panel_diff_count",
        "interaction_error",
        "interaction_skipped_reason",
    ):
        lines.append(f"- {key}: `{summary.get(key)}`")

    if payload.get("error"):
        lines.extend(["", "## Error", "", f"```text\n{payload['error']}\n```"])

    lines.extend(
        [
            "",
            "## Artifact Files",
            "",
            "| Stage | Exists | Size | Path |",
            "| --- | --- | ---: | --- |",
        ]
    )
    for artifact in payload.get("artifacts", []):
        if not isinstance(artifact, dict):
            continue
        lines.append(
            "| "
            + " | ".join(
                [
                    _escape_table(str(artifact.get("label") or artifact.get("key") or "")),
                    "yes" if artifact.get("exists") else "no",
                    str(artifact.get("size_bytes") or 0),
                    _escape_table(str(artifact.get("path") or "")),
                ]
            )
            + " |"
        )

    lines.extend(["", "## Quality", "", "```json"])
    lines.append(json.dumps(payload.get("quality") or {}, ensure_ascii=False, indent=2))
    lines.extend(["```", "", "## Deduplication", ""])
    dedup = payload.get("deduplication")
    dedup = dedup if isinstance(dedup, dict) else {}
    lines.append("```json")
    lines.append(json.dumps(dedup.get("summary") or {}, ensure_ascii=False, indent=2))
    lines.append("```")
    duplicate_chunks = dedup.get("duplicate_chunks")
    duplicate_chunks = duplicate_chunks if isinstance(duplicate_chunks, list) else []
    if duplicate_chunks:
        lines.extend(["", "### Duplicate Candidates", ""])
        for item in duplicate_chunks[:12]:
            if not isinstance(item, dict):
                continue
            metadata = item.get("deduplication")
            metadata = metadata if isinstance(metadata, dict) else {}
            lines.append(
                f"- `{item.get('chunk_id')}` duplicates "
                f"`{metadata.get('canonical_chunk_id')}` via "
                f"`{metadata.get('primary_layer')}`; "
                f"layers `{metadata.get('detected_layers')}`"
            )
    lines.extend(["", "## First Chunks", ""])
    chunks = payload.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        lines.append("(no chunks)")
    else:
        for chunk in chunks[:8]:
            if not isinstance(chunk, dict):
                continue
            preview = " ".join(str(chunk.get("text") or "").split())[:240]
            lines.append(
                f"- `{chunk.get('chunk_id')}` | section `{chunk.get('section')}` | "
                f"usable `{chunk.get('is_usable_for_retrieval')}`: {preview}"
            )
    interaction = payload.get("interaction")
    interaction = interaction if isinstance(interaction, dict) else {}
    lines.extend(["", "## Dynamic Interaction Debug Chunks", ""])
    lines.append(f"- enabled: `{interaction.get('enabled')}`")
    lines.append(f"- attempted: `{interaction.get('attempted')}`")
    lines.append(f"- skipped_reason: `{interaction.get('skipped_reason')}`")
    lines.append(f"- error: `{interaction.get('error')}`")
    promoted_chunks = interaction.get("promoted_chunks")
    promoted_chunks = promoted_chunks if isinstance(promoted_chunks, list) else []
    if promoted_chunks:
        lines.append("")
        lines.append("### Promoted semantic chunks")
        lines.append("")
        for chunk in promoted_chunks[:12]:
            if not isinstance(chunk, dict):
                continue
            metadata = chunk.get("metadata")
            metadata = metadata if isinstance(metadata, dict) else {}
            preview = " ".join(str(chunk.get("text") or "").split())[:240]
            lines.append(
                f"- `{chunk.get('chunk_id')}` | type `{metadata.get('chunk_type')}` | "
                f"filtered `{metadata.get('metadata_prefilter_exclude')}`: {preview}"
            )
    interaction_chunks = interaction.get("debug_chunks") or interaction.get("chunks")
    if not isinstance(interaction_chunks, list) or not interaction_chunks:
        lines.append("")
        lines.append("(no interaction debug chunks)")
    else:
        lines.append("")
        lines.append("### Debug-only chunks")
        lines.append("")
        for chunk in interaction_chunks[:12]:
            if not isinstance(chunk, dict):
                continue
            metadata = chunk.get("metadata")
            metadata = metadata if isinstance(metadata, dict) else {}
            preview = " ".join(str(chunk.get("text") or "").split())[:240]
            lines.append(
                f"- `{chunk.get('chunk_id')}` | type `{metadata.get('chunk_type')}` | "
                f"filtered `{metadata.get('metadata_prefilter_exclude')}`: {preview}"
            )
    return "\n".join(lines).rstrip() + "\n"


def _summary(
    *,
    url: str,
    document: LoadedUrlDocument | None,
    manifest: dict[str, Any],
    quality: dict[str, Any],
    chunks: list[dict[str, Any]],
    artifact_items: list[dict[str, Any]],
    metadata: dict[str, Any],
    error: str | None,
    use_browser_extractor: bool,
    include_interactions: bool,
    interaction: dict[str, Any],
    dedup: dict[str, Any],
) -> dict[str, Any]:
    url_quality = quality.get("url_quality") if isinstance(quality, dict) else None
    quality_gate = quality.get("url_quality_gate") if isinstance(quality, dict) else None
    quality_report = url_quality if isinstance(url_quality, dict) else {}
    gate = quality_gate if isinstance(quality_gate, dict) else {}
    value_summary = _chunk_value_summary(chunks)
    dedup_summary = dedup.get("summary") if isinstance(dedup.get("summary"), dict) else {}
    return {
        "url": url,
        "status": _review_status(document=document, error=error),
        "error": error,
        "chunk_count": len(document.chunks) if document is not None else 0,
        "usable_chunk_count": sum(
            1
            for chunk in (document.chunks if document is not None else [])
            if _is_chunk_usable(chunk)
        ),
        "markdown_length": len(document.markdown) if document is not None else 0,
        "artifact_dir": _artifact_dir(document),
        "artifact_count": sum(1 for item in artifact_items if item.get("exists")),
        "parser": manifest.get("parser") or gate.get("parser") or metadata.get("parser"),
        "source_html_stage": manifest.get("source_html_stage"),
        "page_type": metadata.get("page_type") or gate.get("page_type"),
        "render_required": metadata.get("render_required") or gate.get("requires_rendered_parser"),
        "quality_status": gate.get("status"),
        "quality_verdict": quality_report.get("verdict"),
        "quality_reason": gate.get("reason"),
        "browser_error": gate.get("browser_error"),
        "use_browser_extractor": use_browser_extractor,
        "include_interactions": include_interactions,
        "interaction_required": _interaction_required(interaction),
        "interaction_attempted": interaction.get("attempted"),
        "interaction_state_count": interaction.get("state_count"),
        "interaction_debug_chunk_count": interaction.get("debug_chunk_count"),
        "interaction_promoted_chunk_count": interaction.get("promoted_chunk_count"),
        "interaction_panel_snapshot_count": interaction.get("panel_snapshot_count"),
        "interaction_panel_diff_count": interaction.get("panel_diff_count"),
        "interaction_error": interaction.get("error"),
        "interaction_skipped_reason": interaction.get("skipped_reason"),
        "chunk_sections": _sections_from_chunks(chunks),
        "dedup_exact_match_count": dedup_summary.get("exact_match_count", 0),
        "dedup_simhash_match_count": dedup_summary.get("simhash_match_count", 0),
        "dedup_duplicate_candidate_count": dedup_summary.get("duplicate_candidate_count", 0),
        **value_summary,
    }


def _artifact_items(
    document: LoadedUrlDocument | None,
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    manifest_paths = manifest.get("stage_paths")
    stage_paths = manifest_paths if isinstance(manifest_paths, dict) else {}
    fallback_paths = _fallback_artifact_paths(document)
    items: list[dict[str, Any]] = []
    for key, label, description in ARTIFACT_STAGES:
        path_text = stage_paths.get(key) if isinstance(stage_paths.get(key), str) else None
        if key == "manifest":
            path_text = str(manifest.get("manifest_path") or path_text or "")
        path_text = path_text or fallback_paths.get(key)
        items.append(_artifact_item(key, label, description, path_text))
    return items


def _interaction_payload(
    url: str,
    *,
    output_dir: Path,
    include_interactions: bool,
    use_browser_extractor: bool,
) -> dict[str, Any]:
    profile = detect_interaction_profile(url)
    base: dict[str, Any] = {
        "enabled": include_interactions,
        "attempted": False,
        "skipped_reason": None,
        "error": None,
        "profile": profile.model_dump(mode="json"),
        "state_count": 0,
        "control_count": 0,
        "skipped_control_count": 0,
        "chunk_count": 0,
        "debug_chunk_count": 0,
        "promoted_chunk_count": 0,
        "panel_snapshot_count": 0,
        "panel_diff_count": 0,
        "states": [],
        "controls": [],
        "skipped_controls": [],
        "chunks": [],
        "debug_chunks": [],
        "promoted_chunks": [],
        "panel_snapshots": [],
        "panel_diffs": [],
        "artifacts": [],
    }
    if not include_interactions:
        base["skipped_reason"] = "interaction_capture_disabled"
        return base
    if not use_browser_extractor:
        base["skipped_reason"] = "browser_extractor_disabled"
        return base
    if not profile.interaction_required:
        base["skipped_reason"] = "interaction_profile_not_required"
        return base

    base["attempted"] = True
    try:
        document = load_url_interactions_with_artifacts(
            url,
            data_artifact_dir=output_dir,
            run_id=f"{DEFAULT_RUN_ID}-interactions",
            options=InteractionOptions(max_states=12),
        )
    except Exception as exc:  # pragma: no cover - live browser failures are environment-specific.
        base["error"] = f"{type(exc).__name__}: {exc}"
        return base

    base.update(_interaction_document_payload(document))
    return base


def _interaction_document_payload(document: LoadedInteractionDocument) -> dict[str, Any]:
    chunk_items = [_chunk_item(chunk, manifest={}) for chunk in document.chunks[:80]]
    debug_chunks = [
        chunk
        for chunk in chunk_items
        if (chunk.get("metadata") or {}).get("chunk_type") == "interaction_debug"
    ]
    promoted_chunks = [
        chunk
        for chunk in chunk_items
        if (chunk.get("metadata") or {}).get("chunk_type") == "dynamic_state"
    ]
    return {
        "profile": document.result.profile.model_dump(mode="json"),
        "state_count": len(document.result.states),
        "control_count": len(document.result.controls),
        "skipped_control_count": len(document.result.skipped_controls),
        "panel_snapshot_count": len(document.result.panel_snapshots),
        "panel_diff_count": len(document.result.panel_diffs),
        "chunk_count": len(document.chunks),
        "debug_chunk_count": len(debug_chunks),
        "promoted_chunk_count": len(promoted_chunks),
        "states": [state.model_dump(mode="json") for state in document.result.states[:80]],
        "controls": [control.model_dump(mode="json") for control in document.result.controls[:80]],
        "skipped_controls": [
            control.model_dump(mode="json") for control in document.result.skipped_controls[:80]
        ],
        "chunks": chunk_items,
        "debug_chunks": debug_chunks,
        "promoted_chunks": promoted_chunks,
        "panel_snapshots": [
            snapshot.model_dump(mode="json") for snapshot in document.result.panel_snapshots[:160]
        ],
        "panel_diffs": [diff.model_dump(mode="json") for diff in document.result.panel_diffs[:80]],
        "artifacts": _interaction_artifact_items(document.artifacts),
    }


def _interaction_artifact_items(
    artifacts: InteractionArtifacts | None,
) -> list[dict[str, Any]]:
    path_map: dict[str, Path | None] = {}
    if artifacts is not None:
        path_map = {
            "interaction_states": artifacts.states_path,
            "interaction_chunks": artifacts.chunks_path,
            "interaction_manifest": artifacts.manifest_path,
            "interaction_source_html": artifacts.source_html_path,
            "interaction_network_payloads": artifacts.network_payloads_path,
            "interaction_panel_snapshots": artifacts.panel_snapshots_path,
            "interaction_panel_diffs": artifacts.panel_diffs_path,
        }
    items: list[dict[str, Any]] = []
    for key, label, description in INTERACTION_ARTIFACT_STAGES:
        path = path_map.get(key)
        items.append(_artifact_item(key, label, description, _display_path(path) if path else None))
    return items


def _interaction_required(interaction: dict[str, Any]) -> bool:
    profile = interaction.get("profile")
    if not isinstance(profile, dict):
        return False
    return bool(profile.get("interaction_required"))


def _with_interaction_promoted_chunks(
    chunks: list[dict[str, Any]],
    interaction: dict[str, Any],
) -> list[dict[str, Any]]:
    promoted_chunks = interaction.get("promoted_chunks")
    if not isinstance(promoted_chunks, list) or not promoted_chunks:
        return chunks
    seen = {str(chunk.get("chunk_id")) for chunk in chunks}
    output = list(chunks)
    for chunk in promoted_chunks:
        if not isinstance(chunk, dict):
            continue
        chunk_id = str(chunk.get("chunk_id") or "")
        if not chunk_id or chunk_id in seen:
            continue
        output.append(chunk)
        seen.add(chunk_id)
    return output


def _dedup_payload(document: LoadedUrlDocument | None) -> dict[str, Any]:
    if document is None or not document.chunks:
        return _empty_dedup_payload()
    documents = documents_from_chunks(document.chunks)
    report = detect_duplicates(
        documents,
        config=DedupConfig(enable_exact=True, enable_simhash=True, enable_embedding=False),
    )
    enriched_chunks = add_duplicate_metadata_to_chunks(list(document.chunks), report)
    duplicate_items: list[dict[str, Any]] = []
    dedup_metadata_by_chunk: dict[str, dict[str, Any]] = {}
    for chunk in enriched_chunks:
        metadata = _metadata_dict(chunk.metadata)
        deduplication = metadata.get("deduplication")
        if not isinstance(deduplication, dict):
            continue
        dedup_metadata_by_chunk[chunk.chunk_id] = deduplication
        duplicate_items.append(
            {
                "chunk_id": chunk.chunk_id,
                "section": metadata.get("section"),
                "dedupe_hash": metadata.get("dedupe_hash"),
                "dedup_text_source": metadata.get("dedup_text_source"),
                "deduplication": deduplication,
                "text_preview": " ".join(chunk.text.split())[:240],
            }
        )
    return {
        "summary": {
            "document_count": report.document_count,
            "exact_match_count": len(report.exact_matches),
            "simhash_match_count": len(report.simhash_matches),
            "embedding_match_count": len(report.embedding_matches),
            "duplicate_candidate_count": len(duplicate_items),
            "layers_enabled": ["exact_sha256", "simhash"],
            "embedding_enabled": False,
        },
        "matches": [match.model_dump(mode="json") for match in report.matches],
        "duplicate_chunks": duplicate_items,
        "metadata_by_chunk_id": dedup_metadata_by_chunk,
    }


def _empty_dedup_payload() -> dict[str, Any]:
    return {
        "summary": {
            "document_count": 0,
            "exact_match_count": 0,
            "simhash_match_count": 0,
            "embedding_match_count": 0,
            "duplicate_candidate_count": 0,
            "layers_enabled": ["exact_sha256", "simhash"],
            "embedding_enabled": False,
        },
        "matches": [],
        "duplicate_chunks": [],
        "metadata_by_chunk_id": {},
    }


def _fallback_artifact_paths(document: LoadedUrlDocument | None) -> dict[str, str]:
    if document is None or document.artifacts is None:
        return {}
    artifacts = document.artifacts
    path_map = {
        "source_html": artifacts.source_html_path,
        "cleaned_html": artifacts.cleaned_html_path,
        "parsed_sections": artifacts.parsed_sections_path,
        "extracted_markdown": artifacts.extracted_markdown_path,
        "cleaned_markdown": artifacts.markdown_path,
        "quality": artifacts.quality_path,
        "chunks": artifacts.chunks_path,
        "manifest": artifacts.manifest_path,
    }
    return {key: _display_path(path) for key, path in path_map.items() if path is not None}


def _artifact_item(
    key: str,
    label: str,
    description: str,
    path_text: str | None,
) -> dict[str, Any]:
    path = _resolve_artifact_path(path_text) if path_text else None
    exists = path.exists() if path is not None else False
    preview = ""
    line_count = 0
    size_bytes = 0
    if exists and path is not None and path.is_file():
        size_bytes = path.stat().st_size
        text = path.read_text(encoding="utf-8", errors="replace")
        line_count = text.count("\n") + (1 if text else 0)
        preview = _truncate(text, PREVIEW_LIMIT)
    return {
        "key": key,
        "label": label,
        "description": description,
        "path": _display_path(path) if path is not None else path_text,
        "exists": exists,
        "size_bytes": size_bytes,
        "line_count": line_count,
        "preview": preview,
        "truncated": bool(preview) and exists and size_bytes > len(preview.encode("utf-8")),
    }


def _manifest_payload(document: LoadedUrlDocument | None) -> dict[str, Any]:
    if document is None or document.artifacts is None:
        return {}
    return _read_json_file(document.artifacts.manifest_path)


def _quality_payload(
    document: LoadedUrlDocument | None,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    path_text = None
    stage_paths = manifest.get("stage_paths")
    if isinstance(stage_paths, dict):
        raw_path = stage_paths.get("quality")
        path_text = raw_path if isinstance(raw_path, str) else None
    if path_text is None and document is not None and document.artifacts is not None:
        quality_path = document.artifacts.quality_path
        path_text = _display_path(quality_path) if quality_path is not None else None
    if path_text:
        payload = _read_json_file(_resolve_artifact_path(path_text))
        if payload:
            return payload
    if document is None or not document.chunks:
        return {}
    metadata = document.chunks[0].metadata
    return {
        "chunk_count": len(document.chunks),
        "page_type": metadata.get("page_type"),
        "render_required": metadata.get("render_required"),
        "url_quality": metadata.get("url_quality"),
        "url_quality_gate": metadata.get("url_quality_gate"),
    }


def _chunk_items(
    document: LoadedUrlDocument | None,
    *,
    manifest: dict[str, Any],
    dedup: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if document is None:
        return []
    return [
        _chunk_item(chunk, manifest=manifest, dedup=dedup or {}) for chunk in document.chunks[:80]
    ]


def _chunk_item(
    chunk: Chunk,
    *,
    manifest: dict[str, Any],
    dedup: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = _metadata_dict(chunk.metadata)
    dedup_metadata = _dedup_metadata_for_chunk(chunk.chunk_id, dedup or {})
    if dedup_metadata is not None:
        metadata = {**metadata, "deduplication": dedup_metadata}
    image_urls = _chunk_image_urls(chunk, manifest=manifest)
    return {
        "chunk_id": chunk.chunk_id,
        "section": metadata.get("section"),
        "section_path": metadata.get("section_path"),
        "is_usable_for_retrieval": _is_chunk_usable(chunk),
        "is_noise": metadata.get("is_noise"),
        "retrieval_weight": metadata.get("retrieval_weight"),
        "chunk_type": metadata.get("chunk_type"),
        "retrieval_visibility": metadata.get("retrieval_visibility"),
        "metadata_prefilter_exclude": metadata.get("metadata_prefilter_exclude"),
        "trusted_for_retrieval": metadata.get("trusted_for_retrieval"),
        "semantic_application_status": metadata.get("semantic_application_status"),
        "chunk_token_count": metadata.get("chunk_token_count"),
        "content_hash": metadata.get("content_hash"),
        "dedupe_text": metadata.get("dedupe_text"),
        "dedupe_hash": metadata.get("dedupe_hash"),
        "dedup_text_source": metadata.get("dedup_text_source"),
        "deduplication": dedup_metadata,
        "url": metadata.get("url"),
        "product_specs": metadata.get("product_specs"),
        "entity_type": metadata.get("entity_type"),
        "entity_name": metadata.get("entity_name"),
        "attribute_group": metadata.get("attribute_group"),
        "image_url": image_urls[0] if image_urls else metadata.get("image_url"),
        "image_urls": image_urls,
        "image_snapshot_ref": metadata.get("image_snapshot_ref"),
        "image_snapshot_refs": metadata.get("image_snapshot_refs") or [],
        "text": chunk.text,
        "metadata": metadata,
    }


def _dedup_metadata_for_chunk(chunk_id: str, dedup: dict[str, Any]) -> dict[str, Any] | None:
    metadata_by_chunk = dedup.get("metadata_by_chunk_id")
    if not isinstance(metadata_by_chunk, dict):
        return None
    metadata = metadata_by_chunk.get(chunk_id)
    return metadata if isinstance(metadata, dict) else None


def _chunk_image_urls(chunk: Chunk, *, manifest: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    metadata = chunk.metadata
    _add_url(urls, metadata.get("image_url"))
    interaction_state = metadata.get("interaction_state")
    if isinstance(interaction_state, dict):
        _add_url(urls, interaction_state.get("image_url"))
    interaction_states = metadata.get("interaction_states")
    if isinstance(interaction_states, list):
        for state in interaction_states:
            if isinstance(state, dict):
                _add_url(urls, state.get("image_url"))
    for url in _markdown_image_urls(chunk.text):
        _add_url(urls, url)
    if _chunk_can_use_page_assets(chunk):
        for url in _manifest_image_urls(manifest):
            _add_url(urls, url)
    return urls[:4]


def _chunk_can_use_page_assets(chunk: Chunk) -> bool:
    section = str(chunk.metadata.get("section") or "").lower()
    text = chunk.text.lower()
    markers = ("visual", "image", "media", "photo", "hinh", "anh")
    return any(marker in section or marker in text[:160] for marker in markers)


def _manifest_image_urls(manifest: dict[str, Any]) -> list[str]:
    assets = manifest.get("assets")
    if not isinstance(assets, list):
        return []
    urls: list[str] = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        if asset.get("kind") != "image":
            continue
        _add_url(urls, asset.get("url"))
    return urls


def _markdown_image_urls(text: str) -> list[str]:
    return re.findall(r"!\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)", text)


def _add_url(urls: list[str], value: object) -> None:
    if not isinstance(value, str):
        return
    url = value.strip()
    if not url or url in urls:
        return
    if not re.match(r"^https?://", url, flags=re.IGNORECASE) and not url.startswith("/"):
        return
    urls.append(url)


def _review_status(*, document: LoadedUrlDocument | None, error: str | None) -> str:
    if error or document is None or not document.chunks:
        return "fail"
    usable_count = sum(1 for chunk in document.chunks if _is_chunk_usable(chunk))
    if usable_count == 0:
        return "fail"
    metadata = _first_chunk_metadata(document)
    gate = metadata.get("url_quality_gate")
    if isinstance(gate, dict) and gate.get("accepted") is False:
        return "partial"
    quality = metadata.get("url_quality")
    if isinstance(quality, dict) and quality.get("verdict") == "low_signal":
        return "partial"
    return "success"


def _is_chunk_usable(chunk: Chunk) -> bool:
    if chunk.metadata.get("is_noise") is True:
        return False
    if chunk.metadata.get("metadata_prefilter_exclude") is True:
        return False
    if chunk.metadata.get("retrieval_visibility") == "debug_only":
        return False
    if chunk.metadata.get("trusted_for_retrieval") is False:
        return False
    retrieval_weight = chunk.metadata.get("retrieval_weight")
    if isinstance(retrieval_weight, int | float) and retrieval_weight < 0.5:
        return False
    value = chunk.metadata.get("is_usable_for_retrieval")
    if isinstance(value, bool):
        return value
    return is_usable_chunk_text(chunk.text)


def _first_chunk_metadata(document: LoadedUrlDocument | None) -> dict[str, Any]:
    if document is None or not document.chunks:
        return {}
    return _metadata_dict(document.chunks[0].metadata)


def _metadata_dict(metadata: Any) -> dict[str, Any]:
    if isinstance(metadata, BaseModel):
        return metadata.model_dump(mode="json", exclude_none=True)
    if isinstance(metadata, dict):
        return dict(metadata)
    return dict(metadata) if hasattr(metadata, "items") else {}


def _sections_from_chunks(chunks: list[dict[str, Any]]) -> list[str]:
    sections: list[str] = []
    for chunk in chunks:
        section = str(chunk.get("section") or "")
        if section and section not in sections:
            sections.append(section)
    return sections[:20]


def _chunk_value_summary(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    if not chunks:
        return {
            "valuable_chunk_count": 0,
            "product_fact_chunk_count": 0,
            "entity_chunk_count": 0,
            "noise_chunk_count": 0,
            "average_retrieval_weight": 0.0,
            "has_valuable_chunks": False,
        }
    valuable_count = 0
    product_fact_count = 0
    entity_count = 0
    noise_count = 0
    weights: list[float] = []
    for chunk in chunks:
        metadata = chunk.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        weight = metadata.get("retrieval_weight", chunk.get("retrieval_weight"))
        numeric_weight = float(weight) if isinstance(weight, int | float) else 1.0
        weights.append(numeric_weight)
        usable = chunk.get("is_usable_for_retrieval") is True
        is_noise = metadata.get("is_noise", chunk.get("is_noise")) is True
        has_entity = bool(metadata.get("entity_type") or metadata.get("entity_name"))
        product_specs = metadata.get("product_specs")
        has_product_specs = isinstance(product_specs, dict) and bool(product_specs)
        has_product_fact = bool(
            has_product_specs
            or metadata.get("product_model")
            or metadata.get("product_price")
            or metadata.get("driving_range")
            or metadata.get("battery_capacity")
            or metadata.get("charging_time")
        )
        if is_noise:
            noise_count += 1
        if has_entity:
            entity_count += 1
        if has_product_fact:
            product_fact_count += 1
        if usable and not is_noise and numeric_weight >= 1.0:
            valuable_count += 1
    return {
        "valuable_chunk_count": valuable_count,
        "product_fact_chunk_count": product_fact_count,
        "entity_chunk_count": entity_count,
        "noise_chunk_count": noise_count,
        "average_retrieval_weight": round(sum(weights) / len(weights), 3),
        "has_valuable_chunks": valuable_count > 0,
    }


def _artifact_dir(document: LoadedUrlDocument | None) -> str:
    if document is None or document.artifacts is None:
        return ""
    return _display_path(document.artifacts.run_dir)


def _read_json_file(path: str | Path) -> dict[str, Any]:
    resolved_path = _resolve_artifact_path(path)
    if not resolved_path.exists():
        return {}
    try:
        value = json.loads(resolved_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _resolve_artifact_path(path: str | Path | None) -> Path:
    if path is None:
        return Path("")
    raw_path = Path(path)
    if raw_path.is_absolute():
        return raw_path
    repo_path = REPO_ROOT / raw_path
    if repo_path.exists():
        return repo_path
    return raw_path


def _display_path(path: str | Path | None) -> str:
    if path is None:
        return ""
    raw_path = Path(path)
    try:
        return raw_path.resolve(strict=False).relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return raw_path.as_posix()


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "\n\n... truncated ..."


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect URL ingestion artifacts for exactly one URL. "
            "This demo does not discover or crawl child pages."
        ),
    )
    parser.add_argument("url", help="URL to fetch, parse, clean, and chunk.")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory for artifact_review.md, payload JSON, and ingestion artifacts.",
    )
    parser.add_argument(
        "--json-output",
        default="",
        help="Optional JSON payload output path for the browser server.",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Disable browser rendering and inspect the static-fetch path only.",
    )
    parser.add_argument(
        "--include-interactions",
        action="store_true",
        help="Also run safe dynamic interaction capture when the URL profile requires it.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
