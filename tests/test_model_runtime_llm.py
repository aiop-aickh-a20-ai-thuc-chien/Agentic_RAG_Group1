from __future__ import annotations

import sys
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest
from pytest import MonkeyPatch

from agentic_rag.core.contracts import LLMCompletionInput
from agentic_rag.model_runtime.config import LLMProfileConfig
from agentic_rag.model_runtime.errors import ModelInvocationError
from agentic_rag.model_runtime.llm import LiteLLMClient


def _profile(
    *,
    provider: str = "openai",
    model: str = "gpt-4o-mini",
    api_base: str | None = None,
    api_key: str | None = None,
) -> LLMProfileConfig:
    return LLMProfileConfig(
        role="generation",
        provider=provider,
        model=model,
        api_base=api_base,
        api_key=api_key,
        timeout_seconds=12.0,
    )


def test_litellm_complete_passes_normalized_messages(monkeypatch: MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_completion(**kwargs: Any) -> object:
        captured.update(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Grounded answer"))]
        )

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(completion=fake_completion))
    client = LiteLLMClient(config=_profile(api_base="https://example.test/v1", api_key="secret"))

    output = client.complete(
        LLMCompletionInput(
            prompt="Question",
            system_message="System",
            temperature=0.2,
        )
    )

    assert output.text == "Grounded answer"
    assert output.provider == "openai"
    assert output.model == "openai/gpt-4o-mini"
    assert captured["model"] == "openai/gpt-4o-mini"
    assert captured["temperature"] == 0.2
    assert captured["timeout"] == 12.0
    assert captured["api_base"] == "https://example.test/v1"
    assert captured["api_key"] == "secret"
    assert captured["messages"] == [
        {"role": "system", "content": "System"},
        {"role": "user", "content": "Question"},
    ]


def test_litellm_complete_does_not_double_prefix_model(monkeypatch: MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_completion(**kwargs: Any) -> object:
        captured.update(kwargs)
        return {"choices": [{"message": {"content": "Answer"}}]}

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(completion=fake_completion))
    client = LiteLLMClient(config=_profile(model="openai/gpt-4o-mini"))

    output = client.complete(LLMCompletionInput(prompt="Question", system_message="System"))

    assert output.model == "openai/gpt-4o-mini"
    assert captured["model"] == "openai/gpt-4o-mini"


def test_litellm_omits_unset_generic_credentials(monkeypatch: MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_completion(**kwargs: Any) -> object:
        captured.update(kwargs)
        return {"choices": [{"message": {"content": "Answer"}}]}

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(completion=fake_completion))
    client = LiteLLMClient(config=_profile())

    client.complete(LLMCompletionInput(prompt="Question", system_message="System"))

    assert "api_base" not in captured
    assert "api_key" not in captured


def test_litellm_stream_yields_normalized_deltas(monkeypatch: MonkeyPatch) -> None:
    def fake_completion(**kwargs: Any) -> Iterator[object]:
        assert kwargs["stream"] is True
        yield {"choices": [{"delta": {"content": "A"}}]}
        yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="B"))])
        yield {"choices": [{"delta": {"content": ""}}]}

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(completion=fake_completion))
    client = LiteLLMClient(config=_profile())

    deltas = list(client.stream(LLMCompletionInput(prompt="Question", system_message="System")))

    assert [delta.text for delta in deltas] == ["A", "B"]


def test_litellm_errors_are_normalized(monkeypatch: MonkeyPatch) -> None:
    def fake_completion(**kwargs: Any) -> object:
        raise RuntimeError("provider unavailable")

    monkeypatch.setitem(sys.modules, "litellm", SimpleNamespace(completion=fake_completion))
    client = LiteLLMClient(config=_profile())

    with pytest.raises(ModelInvocationError, match="provider unavailable"):
        client.complete(LLMCompletionInput(prompt="Question", system_message="System"))
