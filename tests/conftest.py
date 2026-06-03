"""Shared test configuration and fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _test_env_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate tests from .env settings that affect pipeline behavior."""
    monkeypatch.setenv("AGENT_MODE", "false")
    monkeypatch.setenv("LANGSMITH_TRACE_MODE", "custom")
