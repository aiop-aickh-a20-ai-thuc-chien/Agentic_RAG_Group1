"""Global retrieval config endpoints used by the chat config page."""

from __future__ import annotations

import os

import pytest

import agentic_rag.api as api
from agentic_rag.api import RetrievalConfig

_FLAG_ENVS = [
    "HARD_FILTER_ENABLED",
    "METADATA_BOOSTING_ENABLED",
    "RETRIEVAL_QUESTION_INDEX_ENABLED",
    "ENTITY_PREFILTER_LLM",
    "QUESTION_MIN_SCORE",
]


def test_set_retrieval_config_applies_live_and_persists(
    tmp_path: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"  # type: ignore[operator]
    env_file.write_text("HARD_FILTER_ENABLED=true\n# keep comment\nOTHER=keep\n", encoding="utf-8")
    monkeypatch.setattr(api, "_ENV_FILE", env_file)
    for name in _FLAG_ENVS:
        # setenv registers the original value (even when absent) so monkeypatch
        # restores it on teardown — set_retrieval_config writes os.environ
        # directly, which would otherwise leak into later tests. Then delenv for
        # a clean slate during this test.
        monkeypatch.setenv(name, os.environ.get(name, ""))
        monkeypatch.delenv(name, raising=False)

    result = api.set_retrieval_config(
        RetrievalConfig(
            hard_filter_enabled=False,
            metadata_boosting_enabled=True,
            question_index_enabled=True,
            entity_prefilter_llm=False,
            question_min_score=0.7,
        )
    )

    # applied live (chat picks these up via os.getenv)
    assert os.environ["HARD_FILTER_ENABLED"] == "false"
    assert os.environ["RETRIEVAL_QUESTION_INDEX_ENABLED"] == "true"
    assert os.environ["QUESTION_MIN_SCORE"] == "0.7"
    assert result.hard_filter_enabled is False
    assert result.question_min_score == pytest.approx(0.7)

    # persisted, existing key updated in place + comments/other lines preserved
    text = env_file.read_text(encoding="utf-8")
    assert "HARD_FILTER_ENABLED=false" in text
    assert "RETRIEVAL_QUESTION_INDEX_ENABLED=true" in text
    assert "QUESTION_MIN_SCORE=0.7" in text
    assert "# keep comment" in text
    assert "OTHER=keep" in text
    assert text.count("HARD_FILTER_ENABLED=") == 1  # updated, not duplicated


def test_get_retrieval_config_reads_env_with_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HARD_FILTER_ENABLED", "false")
    monkeypatch.delenv("METADATA_BOOSTING_ENABLED", raising=False)  # default True
    monkeypatch.setenv("QUESTION_MIN_SCORE", "0.7")

    cfg = api.get_retrieval_config()
    assert cfg.hard_filter_enabled is False
    assert cfg.metadata_boosting_enabled is True
    assert cfg.question_min_score == pytest.approx(0.7)
