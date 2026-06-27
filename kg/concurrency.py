"""Tiny concurrency helper for the OFFLINE build.

Every stage is I/O-bound: it blocks on an OpenAI HTTP round-trip while the CPU
idles. A thread pool overlaps those waits (the GIL is released during the socket
read), turning N sequential round-trips into ceil(N / workers) waves.

Order is PRESERVED, so the staging view — and therefore the content-addressed
ids — stays byte-for-byte identical to the sequential path. Workers come from
$KG_WORKERS (default 8); set it to 1 to fall back to a plain sequential map.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor


def workers(default: int = 8) -> int:
    try:
        return max(1, int(os.getenv("KG_WORKERS", str(default))))
    except ValueError:
        return default


def pmap[T, R](fn: Callable[[T], R], items: list[T], max_workers: int | None = None) -> list[R]:
    """Map `fn` over `items` concurrently, returning results IN ORDER.

    With <=1 worker or <=1 item it runs inline (identical to a sequential map).
    Exceptions propagate exactly like `map` — the first one raised wins.
    """
    n = max_workers if max_workers is not None else workers()
    if n <= 1 or len(items) <= 1:
        return [fn(x) for x in items]
    with ThreadPoolExecutor(max_workers=n) as ex:
        return list(ex.map(fn, items))
