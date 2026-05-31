"""Tiny local `.env` loader for development runs."""

from __future__ import annotations

import os
from pathlib import Path

_LOADED = False


def load_local_env(path: str = ".env") -> None:
    """Load simple KEY=VALUE pairs from a local env file if it exists.

    Existing process environment variables win over values from the file.
    This keeps local development ergonomic without adding another runtime
    dependency just to read `.env`.
    """

    global _LOADED
    if _LOADED:
        return

    env_path = Path(path)
    if not env_path.exists():
        _LOADED = True
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = _clean_env_value(value.strip())
        if key and key not in os.environ:
            os.environ[key] = value

    _LOADED = True


def _clean_env_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
