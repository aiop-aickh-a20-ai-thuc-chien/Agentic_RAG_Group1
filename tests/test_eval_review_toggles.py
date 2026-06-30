"""Per-run retrieval toggle overrides for the eval-review run endpoint."""

from __future__ import annotations

import os

import pytest

from agentic_rag.eval_review import RunConfig, _temp_toggle_env, get_eval_flags


def test_temp_toggle_env_applies_then_restores(monkeypatch: pytest.MonkeyPatch) -> None:
    # Clean slate — importing api.py elsewhere loads .env into os.environ session-wide.
    for name in (
        "HARD_FILTER_ENABLED",
        "METADATA_BOOSTING_ENABLED",
        "RETRIEVAL_QUESTION_INDEX_ENABLED",
        "ENTITY_PREFILTER_LLM",
        "QUESTION_MIN_SCORE",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HARD_FILTER_ENABLED", "true")

    config = RunConfig(
        run_ragas=False,
        hard_filter_enabled=False,  # override an existing value
        question_index_enabled=True,  # override an unset value
        # metadata_boosting_enabled / entity_prefilter_llm left None -> untouched
    )

    with _temp_toggle_env(config):
        assert os.environ["HARD_FILTER_ENABLED"] == "false"
        assert os.environ["RETRIEVAL_QUESTION_INDEX_ENABLED"] == "true"
        # None fields must not be written
        assert "METADATA_BOOSTING_ENABLED" not in os.environ

    # restored: previously-set value comes back, previously-unset is removed
    assert os.environ["HARD_FILTER_ENABLED"] == "true"
    assert "RETRIEVAL_QUESTION_INDEX_ENABLED" not in os.environ


def test_temp_toggle_env_noop_when_all_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HARD_FILTER_ENABLED", "true")
    with _temp_toggle_env(RunConfig()):
        assert os.environ["HARD_FILTER_ENABLED"] == "true"
    assert os.environ["HARD_FILTER_ENABLED"] == "true"


def test_get_eval_flags_reads_env_with_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HARD_FILTER_ENABLED", "false")
    monkeypatch.delenv("METADATA_BOOSTING_ENABLED", raising=False)  # default True
    monkeypatch.delenv("RETRIEVAL_QUESTION_INDEX_ENABLED", raising=False)  # default False
    monkeypatch.setenv("ENTITY_PREFILTER_LLM", "true")

    flags = get_eval_flags()

    assert flags.hard_filter_enabled is False
    assert flags.metadata_boosting_enabled is True
    assert flags.question_index_enabled is False
    assert flags.entity_prefilter_llm is True
