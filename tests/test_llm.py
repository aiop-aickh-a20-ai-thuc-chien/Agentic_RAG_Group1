from __future__ import annotations

from collections.abc import Iterator

import pytest
from pytest import MonkeyPatch

from agentic_rag.core.contracts import (
    LLMCompletionInput,
    LLMCompletionOutput,
    LLMStreamDelta,
)
from agentic_rag.generation.answering import GROUNDING_SYSTEM_MESSAGE, _traced_complete
from agentic_rag.model_runtime.factory import clear_model_runtime_caches, get_llm_client
from agentic_rag.model_runtime.llm import LiteLLMClient


@pytest.fixture(autouse=True)
def _clean_runtime(monkeypatch: MonkeyPatch) -> Iterator[None]:
    clear_model_runtime_caches()
    monkeypatch.setattr("agentic_rag.model_runtime.config.load_local_env", lambda: None)
    yield
    clear_model_runtime_caches()


class _FakeTypedLLM:
    def __init__(self) -> None:
        self.requests: list[LLMCompletionInput] = []

    def complete(self, request: LLMCompletionInput) -> LLMCompletionOutput:
        self.requests.append(request)
        return LLMCompletionOutput(text=" Answer ", provider="test", model="test")

    def stream(self, request: LLMCompletionInput) -> Iterator[LLMStreamDelta]:
        self.requests.append(request)
        yield LLMStreamDelta(text="A")


def test_traced_complete_uses_typed_request_and_grounding_system_message() -> None:
    client = _FakeTypedLLM()

    result = _traced_complete("Question and evidence", client)

    assert result == "Answer"
    assert client.requests == [
        LLMCompletionInput(
            prompt="Question and evidence",
            system_message=GROUNDING_SYSTEM_MESSAGE,
        )
    ]


def test_get_llm_client_returns_none_for_disabled_provider(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "none")

    assert get_llm_client("generation") is None


def test_get_llm_client_returns_litellm_for_enabled_provider(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o-mini")

    client = get_llm_client("generation")

    assert isinstance(client, LiteLLMClient)
    assert client.config.provider == "openai"
    assert client.config.model == "gpt-4o-mini"
