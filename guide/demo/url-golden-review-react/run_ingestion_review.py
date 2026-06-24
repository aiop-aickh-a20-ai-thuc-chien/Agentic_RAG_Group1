"""Run current URL ingestion and golden scoring for the React review demo."""

from __future__ import annotations

import argparse
import json
import re
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agentic_rag.core.contracts import Chunk
from agentic_rag.ingestion.url.evaluation.runner import (
    DEFAULT_GOLDEN_PATH,
    DEFAULT_URL_LIST_PATH,
    read_url_list,
)
from agentic_rag.ingestion.url.evaluation.scoring import (
    UrlGoldenDataset,
    UrlGoldenSample,
    UrlSampleEvaluation,
    evaluate_sample,
    find_sample_for_url,
    load_golden_dataset,
)
from agentic_rag.ingestion.url.loader import LoadedUrlDocument, load_url_with_artifacts

SMOKE_URL = "https://vinfastauto.com/vn_vi/ve-chung-toi"


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint used by the local Node/React demo."""

    parser = argparse.ArgumentParser(description="Run URL ingestion golden review.")
    parser.add_argument("--url", action="append", default=[])
    parser.add_argument("--url-list", default=str(DEFAULT_URL_LIST_PATH))
    parser.add_argument("--golden", default=str(DEFAULT_GOLDEN_PATH))
    parser.add_argument("--output-dir", default="guide/demo/url-golden-review-react/output")
    parser.add_argument("--output", default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args(argv)

    dataset = load_golden_dataset(args.golden)
    urls = read_url_list(args.url_list)
    if args.list:
        payload = _catalog_payload(dataset=dataset, urls=urls, args=args)
    else:
        selected_urls = _selected_urls(args.url, urls=urls, limit=args.limit)
        payload = run_review(
            selected_urls,
            dataset=dataset,
            url_list_count=len(urls),
            args=args,
        )
    _write_payload(payload, args.output)
    return 0


def run_review(
    urls: Sequence[str],
    *,
    dataset: UrlGoldenDataset,
    url_list_count: int,
    args: argparse.Namespace,
) -> dict[str, Any]:
    """Run URL ingestion for selected URLs and return a frontend payload."""

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    results = [
        _run_one_url(
            index=index,
            url=url,
            dataset=dataset,
            output_dir=output_dir,
            use_browser_extractor=not args.no_browser,
        )
        for index, url in enumerate(urls, start=1)
    ]
    return {
        "payload_schema_version": 1,
        "created_at": _utc_now(),
        "demo": "url-golden-review-react",
        "use_browser_extractor": not args.no_browser,
        "golden": {
            "version": dataset.version,
            "description": dataset.description,
            "sample_count": len(dataset.samples),
            "url_list_count": url_list_count,
            "smoke_url": SMOKE_URL,
        },
        "summary": _summary(results),
        "results": results,
    }


def _run_one_url(
    *,
    index: int,
    url: str,
    dataset: UrlGoldenDataset,
    output_dir: Path,
    use_browser_extractor: bool,
) -> dict[str, Any]:
    started = time.perf_counter()
    sample = find_sample_for_url(dataset, url)
    try:
        document = load_url_with_artifacts(
            url,
            data_artifact_dir=output_dir,
            render_cache_dir=output_dir / "render_cache",
            run_id=f"url-golden-review-{index}",
            use_browser_extractor=use_browser_extractor,
        )
    except Exception as exc:
        return {
            "index": index,
            "url": url,
            "status": "error",
            "elapsed_seconds": _elapsed(started),
            "sample": _sample_payload(sample) if sample is not None else None,
            "evaluation": None,
            "document": None,
            "error": f"{type(exc).__name__}: {exc}",
        }

    if sample is None:
        return {
            "index": index,
            "url": url,
            "status": "unscored",
            "elapsed_seconds": _elapsed(started),
            "sample": None,
            "evaluation": None,
            "document": _document_payload(document, url=url),
            "error": (
                "No golden sample exists for this URL; ingestion diagnostics "
                "are shown without pass/fail scoring."
            ),
        }

    evaluation = evaluate_sample(sample, markdown=document.markdown, chunks=document.chunks)
    return {
        "index": index,
        "url": url,
        "status": "passed" if evaluation.passed else "failed",
        "elapsed_seconds": _elapsed(started),
        "sample": _sample_payload(sample),
        "evaluation": _evaluation_payload(evaluation),
        "document": _document_payload(document, url=url),
        "error": None,
    }


def _document_payload(document: LoadedUrlDocument, *, url: str) -> dict[str, Any]:
    chunks = document.chunks
    first_metadata = chunks[0].metadata if chunks else {}
    sections = _unique_strings(chunk.metadata.get("section") for chunk in chunks)
    quality_gate = _dict_metadata(first_metadata.get("url_quality_gate"))
    quality = _dict_metadata(first_metadata.get("url_quality"))
    manifest = _manifest_payload(document)
    return {
        "chunk_count": len(chunks),
        "usable_chunk_count": sum(1 for chunk in chunks if _is_usable_chunk(chunk)),
        "markdown_length": len(document.markdown),
        "markdown_preview": _preview(document.markdown, limit=1400),
        "sections": sections,
        "page_type": first_metadata.get("page_type"),
        "extractor_page_type": first_metadata.get("extractor_page_type"),
        "parser": manifest.get("parser") or quality_gate.get("parser"),
        "quality_gate": quality_gate,
        "url_quality": quality,
        "metadata_summary": _metadata_summary(chunks),
        "product_specs": _product_specs(chunks),
        "artifact_dir": _path_text(document.artifacts.run_dir if document.artifacts else None),
        "manifest": manifest,
        "chunks": [_chunk_payload(chunk, manifest=manifest) for chunk in chunks[:8]],
        "ve_chung_toi_recovery": _ve_chung_toi_recovery(url, sections, chunks),
    }


def _chunk_payload(chunk: Chunk, *, manifest: dict[str, Any]) -> dict[str, Any]:
    metadata = chunk.metadata
    image_urls = _chunk_image_urls(chunk, manifest=manifest)
    return {
        "chunk_id": chunk.chunk_id,
        "section": metadata.get("section"),
        "section_path": metadata.get("section_path"),
        "is_usable": _is_usable_chunk(chunk),
        "is_noise": bool(metadata.get("is_noise")),
        "retrieval_weight": metadata.get("retrieval_weight"),
        "entity_type": metadata.get("entity_type"),
        "entity_name": metadata.get("entity_name"),
        "attribute_group": metadata.get("attribute_group"),
        "product_specs": metadata.get("product_specs") or {},
        "image_url": image_urls[0] if image_urls else metadata.get("image_url"),
        "image_urls": image_urls,
        "image_snapshot_ref": metadata.get("image_snapshot_ref"),
        "image_snapshot_refs": metadata.get("image_snapshot_refs") or [],
        "interaction_state": metadata.get("interaction_state") or {},
        "interaction_states": metadata.get("interaction_states") or [],
        "text": _preview(chunk.text, limit=900),
    }


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


def _evaluation_payload(evaluation: UrlSampleEvaluation) -> dict[str, Any]:
    payload = evaluation.model_dump(mode="json")
    payload["error_checks"] = [check.model_dump(mode="json") for check in evaluation.errors]
    return payload


def _sample_payload(sample: UrlGoldenSample) -> dict[str, Any]:
    expectations = sample.expectations
    return {
        "sample_id": sample.sample_id,
        "description": sample.description,
        "source_url": sample.input.source_url or sample.input.source,
        "min_chunk_count": expectations.min_chunk_count,
        "max_chunk_count": expectations.max_chunk_count,
        "required_metadata_keys": expectations.required_metadata_keys,
        "required_text_snippets": expectations.required_text_snippets,
        "forbidden_text_snippets": expectations.forbidden_text_snippets,
        "product_spec_checks": [
            check.model_dump(mode="json") for check in expectations.product_spec_checks
        ],
    }


def _metadata_summary(chunks: Sequence[Chunk]) -> dict[str, Any]:
    if not chunks:
        return {}
    keys = (
        "url",
        "domain",
        "original_url",
        "canonical_url",
        "language",
        "captured_at",
        "page_type",
        "extractor_page_type",
        "semantic_block_count",
        "entity_count",
        "entity_types",
        "entity_names",
    )
    first_metadata = chunks[0].metadata
    summary = {key: first_metadata.get(key) for key in keys if key in first_metadata}
    summary["noise_chunk_count"] = sum(1 for chunk in chunks if chunk.metadata.get("is_noise"))
    summary["retrieval_weight_min"] = _min_numeric(
        chunk.metadata.get("retrieval_weight") for chunk in chunks
    )
    return summary


def _product_specs(chunks: Sequence[Chunk]) -> list[dict[str, str]]:
    seen: set[str] = set()
    output: list[dict[str, str]] = []
    for chunk in chunks:
        specs = chunk.metadata.get("product_specs")
        if not isinstance(specs, dict) or not specs:
            continue
        normalized = json.dumps(specs, sort_keys=True, ensure_ascii=False)
        if normalized in seen:
            continue
        seen.add(normalized)
        output.append({str(key): str(value) for key, value in specs.items()})
    return output


def _manifest_payload(document: LoadedUrlDocument) -> dict[str, Any]:
    if document.artifacts is None:
        return {}
    path = document.artifacts.manifest_path
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        return {"manifest_path": _path_text(path), "manifest_error": "not_readable"}
    except json.JSONDecodeError as exc:
        return {"manifest_path": _path_text(path), "manifest_error": str(exc)}


def _ve_chung_toi_recovery(
    url: str,
    sections: Sequence[str],
    chunks: Sequence[Chunk],
) -> dict[str, Any] | None:
    if "ve-chung-toi" not in url:
        return None
    recovery_sections = {"Page Summary", "Visual Content"} & set(sections)
    return {
        "old_demo_issue": "legacy demo accepted title-only Markdown and produced zero chunks",
        "current_check": "metadata/image-alt augmentation should create usable chunks",
        "passed": bool(chunks) and bool(recovery_sections),
        "recovery_sections": sorted(recovery_sections),
    }


def _catalog_payload(
    *,
    dataset: UrlGoldenDataset,
    urls: Sequence[str],
    args: argparse.Namespace,
) -> dict[str, Any]:
    items = []
    for index, url in enumerate(urls, start=1):
        sample = find_sample_for_url(dataset, url)
        items.append(
            {
                "index": index,
                "url": url,
                "has_golden_sample": sample is not None,
                "sample_id": sample.sample_id if sample else None,
                "description": sample.description if sample else None,
            }
        )
    return {
        "payload_schema_version": 1,
        "created_at": _utc_now(),
        "golden_path": str(Path(args.golden)),
        "url_list_path": str(Path(args.url_list)),
        "smoke_url": SMOKE_URL,
        "url_count": len(urls),
        "golden_sample_count": len(dataset.samples),
        "items": items,
    }


def _summary(results: Sequence[dict[str, Any]]) -> dict[str, int]:
    return {
        "requested": len(results),
        "passed": sum(1 for result in results if result["status"] == "passed"),
        "failed": sum(1 for result in results if result["status"] == "failed"),
        "errors": sum(1 for result in results if result["status"] == "error"),
        "unscored": sum(1 for result in results if result["status"] == "unscored"),
    }


def _selected_urls(
    raw_urls: Sequence[str],
    *,
    urls: Sequence[str],
    limit: int | None,
) -> list[str]:
    selected = [url.strip() for url in raw_urls if url.strip()]
    if not selected:
        selected = list(urls)
    if limit is not None:
        if limit < 1:
            raise ValueError("limit must be >= 1.")
        selected = selected[:limit]
    return _dedupe(selected)


def _dedupe(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def _is_usable_chunk(chunk: Chunk) -> bool:
    if chunk.metadata.get("is_noise") is True:
        return False
    retrieval_weight = chunk.metadata.get("retrieval_weight")
    if isinstance(retrieval_weight, int | float) and retrieval_weight < 0.5:
        return False
    return len(re.findall(r"\w+", chunk.text, flags=re.UNICODE)) >= 8


def _dict_metadata(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _unique_strings(values: Sequence[object]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value or value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def _min_numeric(values: Sequence[object]) -> float | None:
    numbers = [float(value) for value in values if isinstance(value, int | float)]
    return min(numbers) if numbers else None


def _preview(value: str, *, limit: int) -> str:
    value = value.strip()
    if len(value) <= limit:
        return value
    return f"{value[:limit].rstrip()}..."


def _elapsed(started: float) -> float:
    return round(time.perf_counter() - started, 3)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _path_text(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return path.resolve(strict=False).relative_to(Path.cwd().resolve(strict=False)).as_posix()
    except ValueError:
        return path.resolve(strict=False).as_posix()


def _write_payload(payload: dict[str, Any], output_path: str | None) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if output_path is None:
        print(text)
        return
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{text}\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
