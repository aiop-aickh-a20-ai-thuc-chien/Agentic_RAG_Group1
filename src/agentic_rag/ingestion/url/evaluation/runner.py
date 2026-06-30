"""Run base URL ingestion evaluation from golden URL lists."""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from agentic_rag.ingestion.url.evaluation.scoring import (
    UrlEvaluationCheck,
    UrlGoldenDataset,
    UrlSampleEvaluation,
    evaluate_sample,
    find_sample_for_url,
    load_golden_dataset,
)
from agentic_rag.ingestion.url.loader import LoadedUrlDocument, load_url_with_artifacts

DEFAULT_GOLDEN_DATA_DIR = Path(__file__).resolve().parents[1] / "golden_data"
DEFAULT_URL_LIST_PATH = DEFAULT_GOLDEN_DATA_DIR / "Link_data.txt"
DEFAULT_GOLDEN_PATH = DEFAULT_GOLDEN_DATA_DIR / "vinfast_url_golden_samples.json"
DEFAULT_REPORT_DIR = Path("guide/reports/url_ingestion_base_evaluation")

UrlLoader = Callable[[str], LoadedUrlDocument]


class UrlEvaluationRunItem(BaseModel):
    """Persisted result for one URL in a long evaluation run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    index: int
    url: str
    status: str
    elapsed_seconds: float
    sample_id: str | None = None
    document_chunk_count: int = 0
    evaluation: UrlSampleEvaluation | None = None
    error: str | None = None


class UrlEvaluationRunSummary(BaseModel):
    """Persisted summary for one base URL evaluation run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    started_at: str
    completed_at: str
    url_count: int
    processed_count: int
    passed_count: int
    failed_count: int
    error_count: int
    skipped_count: int
    output_dir: str
    results_jsonl: str
    summary_json: str
    summary_markdown: str
    use_browser_extractor: bool
    golden_path: str
    url_list_path: str


def read_url_list(path: str | Path) -> list[str]:
    """Read one URL per line, ignoring blanks and comments."""

    urls: list[str] = []
    for raw_line in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        urls.append(line)
    return urls


def run_base_url_evaluation(
    *,
    url_list_path: str | Path = DEFAULT_URL_LIST_PATH,
    golden_path: str | Path = DEFAULT_GOLDEN_PATH,
    output_dir: str | Path = DEFAULT_REPORT_DIR,
    use_browser_extractor: bool = True,
    limit: int | None = None,
    start_index: int = 1,
    resume: bool = True,
    loader: UrlLoader | None = None,
) -> UrlEvaluationRunSummary:
    """Crawl URLs, evaluate outputs, and write resumable base evaluation reports."""

    started_at = _utc_now()
    dataset = load_golden_dataset(golden_path)
    urls = read_url_list(url_list_path)
    selected_urls = _selected_urls(urls, start_index=start_index, limit=limit)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    results_jsonl = output_path / "base_results.jsonl"
    summary_json = output_path / "base_summary.json"
    summary_markdown = output_path / "base_summary.md"
    completed_urls = _completed_urls(results_jsonl) if resume else set()
    if not resume and results_jsonl.exists():
        results_jsonl.unlink()
    loader_fn = loader or _default_loader(
        use_browser_extractor=use_browser_extractor,
        render_cache_dir=output_path / "render_cache",
    )

    for offset, url in enumerate(selected_urls, start=start_index):
        if url in completed_urls:
            continue
        item = _evaluate_one_url(
            index=offset,
            url=url,
            dataset=dataset,
            loader=loader_fn,
        )
        _append_jsonl(results_jsonl, item.model_dump(mode="json"))

    items = _read_result_items(results_jsonl)
    summary = _build_summary(
        items=items,
        started_at=started_at,
        completed_at=_utc_now(),
        url_count=len(selected_urls),
        output_dir=output_path,
        results_jsonl=results_jsonl,
        summary_json=summary_json,
        summary_markdown=summary_markdown,
        use_browser_extractor=use_browser_extractor,
        golden_path=Path(golden_path),
        url_list_path=Path(url_list_path),
    )
    summary_json.write_text(
        json.dumps(summary.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    summary_markdown.write_text(_summary_markdown(summary, items), encoding="utf-8")
    return summary


def _default_loader(
    *,
    use_browser_extractor: bool,
    render_cache_dir: Path | None = None,
) -> UrlLoader:
    def load(url: str) -> LoadedUrlDocument:
        return load_url_with_artifacts(
            url,
            use_browser_extractor=use_browser_extractor,
            render_cache_dir=render_cache_dir,
        )

    return load


def _evaluate_one_url(
    *,
    index: int,
    url: str,
    dataset: UrlGoldenDataset,
    loader: UrlLoader,
) -> UrlEvaluationRunItem:
    started = time.perf_counter()
    sample = find_sample_for_url(dataset, url)
    if sample is None:
        return UrlEvaluationRunItem(
            index=index,
            url=url,
            status="failed",
            elapsed_seconds=_elapsed(started),
            error="No golden sample exists for URL.",
        )
    try:
        loaded = loader(url)
        evaluation = evaluate_sample(sample, markdown=loaded.markdown, chunks=loaded.chunks)
    except Exception as exc:
        return UrlEvaluationRunItem(
            index=index,
            url=url,
            status="error",
            elapsed_seconds=_elapsed(started),
            sample_id=sample.sample_id,
            error=f"{type(exc).__name__}: {exc}",
        )
    return UrlEvaluationRunItem(
        index=index,
        url=url,
        status="passed" if evaluation.passed else "failed",
        elapsed_seconds=_elapsed(started),
        sample_id=sample.sample_id,
        document_chunk_count=len(loaded.chunks),
        evaluation=evaluation,
    )


def _selected_urls(urls: list[str], *, start_index: int, limit: int | None) -> list[str]:
    if start_index < 1:
        raise ValueError("start_index must be >= 1.")
    selected = urls[start_index - 1 :]
    if limit is not None:
        if limit < 1:
            raise ValueError("limit must be >= 1.")
        selected = selected[:limit]
    return selected


def _completed_urls(path: Path) -> set[str]:
    if not path.exists():
        return set()
    completed: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        url = payload.get("url")
        if isinstance(url, str) and url:
            completed.add(url)
    return completed


def _read_result_items(path: Path) -> list[UrlEvaluationRunItem]:
    if not path.exists():
        return []
    items: list[UrlEvaluationRunItem] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            items.append(UrlEvaluationRunItem.model_validate_json(line))
    return items


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False))
        handle.write("\n")


def _build_summary(
    *,
    items: list[UrlEvaluationRunItem],
    started_at: str,
    completed_at: str,
    url_count: int,
    output_dir: Path,
    results_jsonl: Path,
    summary_json: Path,
    summary_markdown: Path,
    use_browser_extractor: bool,
    golden_path: Path,
    url_list_path: Path,
) -> UrlEvaluationRunSummary:
    passed_count = sum(1 for item in items if item.status == "passed")
    failed_count = sum(1 for item in items if item.status == "failed")
    error_count = sum(1 for item in items if item.status == "error")
    skipped_count = max(url_count - len(items), 0)
    return UrlEvaluationRunSummary(
        started_at=started_at,
        completed_at=completed_at,
        url_count=url_count,
        processed_count=len(items),
        passed_count=passed_count,
        failed_count=failed_count,
        error_count=error_count,
        skipped_count=skipped_count,
        output_dir=str(output_dir),
        results_jsonl=str(results_jsonl),
        summary_json=str(summary_json),
        summary_markdown=str(summary_markdown),
        use_browser_extractor=use_browser_extractor,
        golden_path=str(golden_path),
        url_list_path=str(url_list_path),
    )


def _summary_markdown(
    summary: UrlEvaluationRunSummary,
    items: Sequence[UrlEvaluationRunItem],
) -> str:
    lines = [
        "# URL Ingestion Base Evaluation",
        "",
        f"- Started: `{summary.started_at}`",
        f"- Completed: `{summary.completed_at}`",
        f"- URLs selected: `{summary.url_count}`",
        f"- Processed: `{summary.processed_count}`",
        f"- Passed: `{summary.passed_count}`",
        f"- Failed: `{summary.failed_count}`",
        f"- Errors: `{summary.error_count}`",
        f"- Skipped: `{summary.skipped_count}`",
        f"- Browser extractor: `{summary.use_browser_extractor}`",
        "",
        "## Failing Or Error Samples",
        "",
    ]
    failing_items = [item for item in items if item.status != "passed"]
    if not failing_items:
        lines.append("No failing or error samples.")
    else:
        lines.extend(
            [
                "| # | Status | Score | URL | Main Errors |",
                "| ---: | --- | ---: | --- | --- |",
            ]
        )
        for item in failing_items[:200]:
            score = item.evaluation.score if item.evaluation is not None else 0.0
            error_summary = _item_error_summary(item)
            lines.append(
                f"| {item.index} | {item.status} | {score:.3f} | {item.url} | {error_summary} |"
            )
    lines.extend(
        [
            "",
            "## Output Files",
            "",
            f"- Results JSONL: `{summary.results_jsonl}`",
            f"- Summary JSON: `{summary.summary_json}`",
            f"- Summary Markdown: `{summary.summary_markdown}`",
            "",
        ]
    )
    return "\n".join(lines)


def _item_error_summary(item: UrlEvaluationRunItem) -> str:
    if item.error:
        return item.error.replace("|", "\\|")
    if item.evaluation is None:
        return ""
    error_checks = item.evaluation.errors[:5]
    return "; ".join(_check_summary(check) for check in error_checks).replace("|", "\\|")


def _check_summary(check: UrlEvaluationCheck) -> str:
    snippet = check.details.get("snippet")
    if isinstance(snippet, str):
        return f"{check.name}: {snippet}"
    return check.name


def _elapsed(started: float) -> float:
    return round(time.perf_counter() - started, 3)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint for long URL base evaluation runs."""

    parser = argparse.ArgumentParser(description="Run URL ingestion base golden evaluation.")
    parser.add_argument("--url-list", default=str(DEFAULT_URL_LIST_PATH))
    parser.add_argument("--golden", default=str(DEFAULT_GOLDEN_PATH))
    parser.add_argument("--output-dir", default=str(DEFAULT_REPORT_DIR))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--start-index", type=int, default=1)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args(argv)

    summary = run_base_url_evaluation(
        url_list_path=args.url_list,
        golden_path=args.golden,
        output_dir=args.output_dir,
        use_browser_extractor=not args.no_browser,
        limit=args.limit,
        start_index=args.start_index,
        resume=not args.no_resume,
    )
    print(
        "URL base evaluation complete: "
        f"processed={summary.processed_count} "
        f"passed={summary.passed_count} "
        f"failed={summary.failed_count} "
        f"errors={summary.error_count} "
        f"summary={summary.summary_markdown}"
    )
    return 0 if summary.failed_count == 0 and summary.error_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
