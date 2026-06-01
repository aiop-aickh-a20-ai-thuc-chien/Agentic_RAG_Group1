import json
from typing import Any

from pytest import MonkeyPatch

from agentic_rag.generation.llm import (
    DEFAULT_OLLAMA_BASE_URL,
    DEFAULT_OLLAMA_MODEL,
    OllamaChatClient,
    OpenAIChatClient,
    configured_llm_client,
)


def test_configured_llm_client_returns_none_without_provider_or_openai_key(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    assert configured_llm_client() is None


def test_configured_llm_client_uses_openai_when_key_is_present(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o-mini")

    client = configured_llm_client()

    assert isinstance(client, OpenAIChatClient)
    assert client.api_key == "test-key"
    assert client.model == "gpt-4o-mini"


def test_configured_llm_client_uses_ollama_with_default_quantized_qwen_model(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)

    client = configured_llm_client()

    assert isinstance(client, OllamaChatClient)
    assert client.base_url == DEFAULT_OLLAMA_BASE_URL
    assert client.model == DEFAULT_OLLAMA_MODEL


def test_configured_llm_client_uses_ollama_environment_overrides(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3.5:4b")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "12.5")

    client = configured_llm_client()

    assert isinstance(client, OllamaChatClient)
    assert client.base_url == "http://localhost:11434/"
    assert client.model == "qwen3.5:4b"
    assert client.timeout_seconds == 12.5


def test_ollama_chat_client_posts_chat_payload(monkeypatch: MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps({"message": {"content": "Tra loi tu Ollama"}}).encode("utf-8")

    def fake_urlopen(request: Any, timeout: float) -> FakeResponse:
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("agentic_rag.generation.llm.request.urlopen", fake_urlopen)

    client = OllamaChatClient(
        base_url="http://localhost:11434/",
        model="qwen3.5:9b-q4_K_M",
        timeout_seconds=15,
    )

    answer = client.complete("Question and evidence")

    assert answer == "Tra loi tu Ollama"
    assert captured["url"] == "http://localhost:11434/api/chat"
    assert captured["body"]["model"] == "qwen3.5:9b-q4_K_M"
    assert captured["body"]["stream"] is False
    assert captured["body"]["messages"][0]["role"] == "system"
    assert captured["body"]["messages"][1] == {
        "role": "user",
        "content": "Question and evidence",
    }
    assert captured["timeout"] == 15


def test_ollama_chat_client_streams_chat_payload(monkeypatch: MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class FakeStreamResponse:
        def __enter__(self) -> "FakeStreamResponse":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def __iter__(self) -> "FakeStreamResponse":
            return self

        def __next__(self) -> bytes:
            lines = [
                json.dumps({"message": {"content": "Tra "}}).encode("utf-8"),
                json.dumps({"message": {"content": "loi"}}).encode("utf-8"),
            ]
            index = captured.get("index", 0)
            if not isinstance(index, int) or index >= len(lines):
                raise StopIteration
            captured["index"] = index + 1
            return lines[index]

    def fake_urlopen(request: Any, timeout: float) -> FakeStreamResponse:
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeStreamResponse()

    monkeypatch.setattr("agentic_rag.generation.llm.request.urlopen", fake_urlopen)

    client = OllamaChatClient(
        base_url="http://localhost:11434/",
        model="qwen3.5:9b-q4_K_M",
        timeout_seconds=15,
    )

    deltas = list(client.stream_complete("Question and evidence"))

    assert deltas == ["Tra ", "loi"]
    assert captured["url"] == "http://localhost:11434/api/chat"
    assert captured["body"]["model"] == "qwen3.5:9b-q4_K_M"
    assert captured["body"]["stream"] is True
    assert captured["timeout"] == 15
