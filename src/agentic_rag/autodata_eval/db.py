"""Database connection pool for eval pipeline (Neon PostgreSQL)."""

from __future__ import annotations

import functools
import os
import re
from collections.abc import Callable, Generator
from contextlib import contextmanager
from typing import Any, cast

import psycopg
from psycopg.rows import DictRow, dict_row

DbConnection = psycopg.Connection[DictRow]


def retry_on_operational_error[T](fn: Callable[..., T]) -> Callable[..., T]:
    """Retry once on psycopg.OperationalError (Neon idle-timeout / dropped connection)."""

    @functools.wraps(fn)
    def wrapper(*args: object, **kwargs: object) -> T:
        for attempt in range(2):
            try:
                return fn(*args, **kwargs)
            except psycopg.OperationalError:
                if attempt == 1:
                    raise
        raise AssertionError("unreachable")

    return wrapper


def _build_conninfo() -> str:
    raw = os.environ.get("NEON_CONNECTION", "")
    if not raw:
        raise RuntimeError(
            "NEON_CONNECTION is not set. "
            "Tạo project tại neon.tech rồi thêm NEON_CONNECTION vào .env"
        )
    return re.sub(r"^postgresql\+psycopg://", "postgresql://", raw)


_conninfo: str | None = None


def _get_conninfo() -> str:
    global _conninfo
    if _conninfo is None:
        _conninfo = _build_conninfo()
    return _conninfo


@contextmanager
def get_conn() -> Generator[DbConnection, None, None]:
    # Retry connect once on stale connection (Neon idle timeout).
    # Retry wraps only psycopg.connect(), NOT the yield — yielding twice
    # inside a @contextmanager raises RuntimeError.
    conn: DbConnection | None = None
    for attempt in range(2):
        try:
            conn = cast(
                DbConnection,
                psycopg.connect(
                    _get_conninfo(),
                    row_factory=cast(Any, dict_row),
                    keepalives=1,
                    keepalives_idle=10,
                    keepalives_interval=2,
                    keepalives_count=5,
                ),
            )
            break
        except psycopg.OperationalError:
            if attempt == 1:
                raise
    if conn is None:
        raise AssertionError("unreachable")
    with conn:
        yield conn
