"""Dedicated APScheduler owner for the VinFast ingestion job."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from importlib import import_module
from typing import Any, cast

from agentic_rag.ingestion.integration.url.vinfast.scheduler import daily_scheduler

PipelineJob = Callable[[], Awaitable[None]]


def start_scheduler(
    run_pipeline: PipelineJob,
    *,
    hour: int = 2,
    timezone: str = "Asia/Ho_Chi_Minh",
    scheduler_factory: Callable[..., Any] = daily_scheduler,
) -> Any:
    """Create and start the one scheduler owned by this worker process."""

    scheduler = scheduler_factory(run_pipeline, hour=hour, timezone=timezone)
    scheduler.start()
    return scheduler


def _load_job(path: str) -> PipelineJob:
    module_name, separator, attribute = path.partition(":")
    if not separator or not module_name or not attribute:
        raise ValueError("VINFAST_PIPELINE_JOB must use module:function format")
    job = getattr(import_module(module_name), attribute)
    if not callable(job):
        raise TypeError("VINFAST_PIPELINE_JOB must resolve to a callable")
    return cast(PipelineJob, job)


async def _serve() -> None:
    job_path = os.environ.get("VINFAST_PIPELINE_JOB", "").strip()
    if not job_path:
        raise RuntimeError("VINFAST_PIPELINE_JOB is required for the dedicated worker")
    hour = int(os.environ.get("VINFAST_PIPELINE_HOUR", "2"))
    timezone = os.environ.get("VINFAST_PIPELINE_TIMEZONE", "Asia/Ho_Chi_Minh")
    scheduler = start_scheduler(_load_job(job_path), hour=hour, timezone=timezone)
    try:
        await asyncio.Event().wait()
    finally:
        scheduler.shutdown(wait=False)


def main() -> None:
    """Run the scheduler until the worker receives cancellation or termination."""

    asyncio.run(_serve())


if __name__ == "__main__":
    main()
