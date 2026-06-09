"""Database connection pool for eval pipeline (Neon PostgreSQL)."""

from __future__ import annotations

import os
import re
from contextlib import contextmanager
from typing import Generator

import psycopg
from psycopg.rows import dict_row


def _build_conninfo() -> str:
    raw = os.environ.get("NEON_CONNECTION", "")
    if not raw:
        raise RuntimeError(
            "NEON_CONNECTION is not set. "
            "Tạo project tại neon.tech rồi thêm NEON_CONNECTION vào .env"
        )
    # Strip SQLAlchemy dialect prefix nếu có
    return re.sub(r"^postgresql\+psycopg://", "postgresql://", raw)


_conninfo: str | None = None


def _get_conninfo() -> str:
    global _conninfo
    if _conninfo is None:
        _conninfo = _build_conninfo()
    return _conninfo


@contextmanager
def get_conn() -> Generator[psycopg.Connection, None, None]:
    with psycopg.connect(_get_conninfo(), row_factory=dict_row) as conn:
        yield conn
