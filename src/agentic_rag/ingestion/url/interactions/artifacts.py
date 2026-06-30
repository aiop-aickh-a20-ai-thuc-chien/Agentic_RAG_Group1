"""Artifact persistence for rule-based interaction capture."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.url.chunking import short_hash, slugify
from agentic_rag.ingestion.url.interactions.models import (
    InteractionArtifacts,
    InteractionCaptureResult,
)


def persist_interaction_artifacts(
    *,
    data_dir: str | Path | None,
    source: str,
    run_id: str,
    result: InteractionCaptureResult,
    chunks: Iterable[Chunk] = (),
) -> InteractionArtifacts | None:
    """Persist normalized interaction states and generated chunks for review."""

    if data_dir is None:
        return None

    run_dir = Path(data_dir) / "artifacts" / _source_slug(source) / slugify(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    chunk_list = list(chunks)
    source_html_path = _write_optional_text(run_dir / "source.html", result.source_html)
    states_path = run_dir / "interaction_states.json"
    image_snapshots_path = _write_image_snapshots(run_dir / "image_snapshots.json", result)
    chunks_path = run_dir / "chunks.jsonl"
    manifest_path = run_dir / "manifest.json"
    network_path = _write_network_payloads(run_dir / "network_payloads.jsonl", result)
    panel_snapshots_path = _write_panel_snapshots(run_dir / "panel_snapshots.json", result)
    panel_diffs_path = _write_panel_diffs(run_dir / "panel_diffs.json", result)

    states_payload = {
        "profile": result.profile.model_dump(mode="json"),
        "controls": [control.model_dump(mode="json") for control in result.controls],
        "skipped_controls": [
            control.model_dump(mode="json") for control in result.skipped_controls
        ],
        "states": _state_payloads_with_snapshot_refs(result),
        "readiness": (
            result.readiness.model_dump(mode="json") if result.readiness is not None else None
        ),
        "section_visits": [visit.model_dump(mode="json") for visit in result.section_visits],
        "transitions": [transition.model_dump(mode="json") for transition in result.transitions],
        "traversal_issues": [issue.model_dump(mode="json") for issue in result.traversal_issues],
        "traversal_complete": result.traversal_complete,
        "errors": result.errors,
    }
    states_path.write_text(
        json.dumps(states_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    chunks_path.write_text(_serialize_chunks_jsonl(chunk_list), encoding="utf-8")
    manifest = {
        "artifact_schema_version": 1,
        "artifact_type": "url_interaction_capture",
        "input_source": source,
        "requested_url": result.profile.requested_url,
        "final_url": result.profile.final_url,
        "page_type": result.profile.page_type,
        "interaction_required": result.profile.interaction_required,
        "run_id": run_id,
        "run_dir": _path_text(run_dir),
        "state_count": len(result.states),
        "control_count": len(result.controls),
        "skipped_control_count": len(result.skipped_controls),
        "panel_snapshot_count": len(result.panel_snapshots),
        "panel_diff_count": len(result.panel_diffs),
        "transition_count": len(result.transitions),
        "traversal_complete": result.traversal_complete,
        "traversal_issue_count": len(result.traversal_issues),
        "chunk_count": len(chunk_list),
        "source_html_path": _path_text_optional(source_html_path),
        "states_path": _path_text(states_path),
        "image_snapshots_path": _path_text_optional(image_snapshots_path),
        "network_payloads_path": _path_text_optional(network_path),
        "panel_snapshots_path": _path_text_optional(panel_snapshots_path),
        "panel_diffs_path": _path_text_optional(panel_diffs_path),
        "chunks_path": _path_text(chunks_path),
        "manifest_path": _path_text(manifest_path),
        "stage_paths": {
            "source_html": _path_text_optional(source_html_path),
            "interaction_states": _path_text(states_path),
            "image_snapshots": _path_text_optional(image_snapshots_path),
            "network_payloads": _path_text_optional(network_path),
            "panel_snapshots": _path_text_optional(panel_snapshots_path),
            "panel_diffs": _path_text_optional(panel_diffs_path),
            "chunks": _path_text(chunks_path),
        },
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return InteractionArtifacts(
        run_dir=run_dir,
        states_path=states_path,
        chunks_path=chunks_path,
        manifest_path=manifest_path,
        source_html_path=source_html_path,
        image_snapshots_path=image_snapshots_path,
        network_payloads_path=network_path,
        panel_snapshots_path=panel_snapshots_path,
        panel_diffs_path=panel_diffs_path,
    )


def _serialize_chunks_jsonl(chunks: Iterable[Chunk]) -> str:
    lines = [json.dumps(chunk.model_dump(mode="json"), ensure_ascii=False) for chunk in chunks]
    return "\n".join(lines) + ("\n" if lines else "")


def _write_optional_text(path: Path, content: str | None) -> Path | None:
    if content is None:
        return None
    path.write_text(content.rstrip() + "\n", encoding="utf-8")
    return path


def _write_network_payloads(
    path: Path,
    result: InteractionCaptureResult,
) -> Path | None:
    if not result.network_payloads:
        return None
    lines = [
        json.dumps(_json_safe(payload), ensure_ascii=False) for payload in result.network_payloads
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_panel_snapshots(
    path: Path,
    result: InteractionCaptureResult,
) -> Path | None:
    if not result.panel_snapshots:
        return None
    payload = {
        "snapshot_schema_version": 1,
        "artifact_role": "panel_snapshots",
        "requested_url": result.profile.requested_url,
        "final_url": result.profile.final_url,
        "snapshots": [snapshot.model_dump(mode="json") for snapshot in result.panel_snapshots],
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _write_panel_diffs(
    path: Path,
    result: InteractionCaptureResult,
) -> Path | None:
    if not result.panel_diffs:
        return None
    payload = {
        "diff_schema_version": 1,
        "artifact_role": "panel_diffs",
        "requested_url": result.profile.requested_url,
        "final_url": result.profile.final_url,
        "diffs": [diff.model_dump(mode="json") for diff in result.panel_diffs],
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _write_image_snapshots(
    path: Path,
    result: InteractionCaptureResult,
) -> Path | None:
    snapshots = _image_snapshot_refs(result)
    if not snapshots:
        return None
    payload = {
        "snapshot_schema_version": 1,
        "artifact_role": "selected_product_image_references",
        "requested_url": result.profile.requested_url,
        "final_url": result.profile.final_url,
        "snapshots": snapshots,
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _state_payloads_with_snapshot_refs(
    result: InteractionCaptureResult,
) -> list[dict[str, object]]:
    snapshot_by_state = {
        snapshot["state_id"]: snapshot for snapshot in _image_snapshot_refs(result)
    }
    payloads: list[dict[str, object]] = []
    for state in result.states:
        payload = state.model_dump(mode="json")
        snapshot = snapshot_by_state.get(state.state_id)
        if snapshot is not None:
            payload["image_snapshot_ref"] = snapshot["snapshot_id"]
        payloads.append(payload)
    return payloads


def _image_snapshot_refs(
    result: InteractionCaptureResult,
) -> list[dict[str, object]]:
    snapshots: list[dict[str, object]] = []
    seen: set[str] = set()
    for state in result.states:
        if not state.image_url:
            continue
        snapshot_id = f"image_snapshot_{state.state_id}"
        if snapshot_id in seen:
            continue
        seen.add(snapshot_id)
        screenshots = _screenshot_paths(state.dom_evidence)
        snapshots.append(
            {
                "snapshot_id": snapshot_id,
                "state_id": state.state_id,
                "state_label": state.option_label,
                "option_group": state.option_group,
                "option_label": state.option_label,
                "variant_options": state.variant_options,
                "model_id": state.model_id,
                "model_name": state.model_name,
                "image_url": state.image_url,
                "image_source": state.evidence_source,
                "price": state.price,
                "currency": state.currency,
                "screenshot_paths": screenshots,
                "has_screenshot": bool(screenshots),
                "local_image_path": None,
                "note": (
                    "Reference only; ingestion does not download remote images. "
                    "Use image_url or screenshot_paths for frontend review."
                ),
            }
        )
    return snapshots


def _screenshot_paths(dom_evidence: dict[str, str]) -> list[str]:
    paths: list[str] = []
    for key in ("screenshot_path", "page_screenshot_path", "snapshot_path"):
        value = dom_evidence.get(key)
        if value:
            paths.append(value)
    return paths


def _json_safe(value: object) -> object:
    try:
        json.dumps(value)
    except TypeError:
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


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


__all__ = ["persist_interaction_artifacts"]
