"""Optional APScheduler wiring kept outside the core ingestion path."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from importlib import import_module
from typing import Any


def daily_scheduler(
    run_pipeline: Callable[[], Awaitable[None]],
    *,
    hour: int = 2,
    timezone: str = "Asia/Ho_Chi_Minh",
) -> Any:
    """Create (but do not start) a daily AsyncIOScheduler."""

    if not 0 <= hour <= 23:
        raise ValueError("hour must be between 0 and 23")
    try:
        scheduler_type = import_module("apscheduler.schedulers.asyncio").AsyncIOScheduler
    except (ImportError, AttributeError) as exc:
        raise RuntimeError(
            "APScheduler is required; install the project with the vinfast-pipeline extra"
        ) from exc
    scheduler = scheduler_type(timezone=timezone)
    scheduler.add_job(run_pipeline, "cron", hour=hour, id="vinfast-daily", replace_existing=True)
    return scheduler
