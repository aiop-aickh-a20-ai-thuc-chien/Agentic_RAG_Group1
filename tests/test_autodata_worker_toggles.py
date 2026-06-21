"""Per-run retrieval toggle overrides applied by the autodata_eval worker."""

from __future__ import annotations

import os

import pytest

from agentic_rag.autodata_eval.worker import _toggle_env_overrides

_ALL_FLAG_ENVS = [
    "HARD_FILTER_ENABLED",
    "METADATA_BOOSTING_ENABLED",
    "RETRIEVAL_QUESTION_INDEX_ENABLED",
    "ENTITY_PREFILTER_LLM",
    "QUESTION_MIN_SCORE",
]


def test_toggle_env_overrides_apply_then_restore(monkeypatch: pytest.MonkeyPatch) -> None:
    # Start from a known-clean slate (other test modules may import api.py, which
    # loads .env into os.environ for the whole session).
    for name in _ALL_FLAG_ENVS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HARD_FILTER_ENABLED", "true")

    run_config = {
        "exclude_dedup_layers": ["exact_sha256"],  # unrelated key -> ignored
        "hard_filter_enabled": False,
        "question_index_enabled": True,
        "question_min_score": 0.7,  # numeric -> stringified
        # metadata_boosting_enabled / entity_prefilter_llm absent -> untouched
    }

    with _toggle_env_overrides(run_config):
        assert os.environ["HARD_FILTER_ENABLED"] == "false"
        assert os.environ["RETRIEVAL_QUESTION_INDEX_ENABLED"] == "true"
        assert os.environ["QUESTION_MIN_SCORE"] == "0.7"
        assert "METADATA_BOOSTING_ENABLED" not in os.environ

    assert os.environ["HARD_FILTER_ENABLED"] == "true"  # restored
    assert "RETRIEVAL_QUESTION_INDEX_ENABLED" not in os.environ  # removed
    assert "QUESTION_MIN_SCORE" not in os.environ


def test_toggle_env_overrides_noop_when_no_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HARD_FILTER_ENABLED", "true")
    with _toggle_env_overrides({"exclude_dedup_layers": []}):
        assert os.environ["HARD_FILTER_ENABLED"] == "true"
    assert os.environ["HARD_FILTER_ENABLED"] == "true"
