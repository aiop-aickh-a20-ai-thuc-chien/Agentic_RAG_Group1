"""Configurable LLM clients for grounded generation."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol
from urllib import request

from agentic_rag.runtime_env import load_local_env

DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "qwen3.5:9b-q4_K_M"
DEFAULT_LLM_TIMEOUT_SECONDS = 60.0
GROUNDING_SYSTEM_MESSAGE = (
    "You answer only from the provided evidence. "
    "If evidence is insufficient, say the information is not in the documents."
)


class LLMClient(Protocol):
    """Minimal completion boundary used by the generation module."""

    def complete(self, prompt: str) -> str:
        """Return a text completion for a grounded prompt."""

    def stream_complete(self, prompt: str) -> Iterator[str]:
        """Yield text deltas for a grounded prompt."""


class MissingLLMConfigurationError(RuntimeError):
    """Raised when no LLM credential is configured."""


class UnsupportedLLMProviderError(ValueError):
    """Raised when LLM_PROVIDER is set to an unsupported value."""


@dataclass(frozen=True)
class OpenAIChatClient:
    """Small wrapper around the OpenAI chat completions API."""

    api_key: str | None = None
    model: str = DEFAULT_OPENAI_MODEL

    def complete(self, prompt: str) -> str:
        """Call OpenAI and return the assistant message content."""

        api_key = self.api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise MissingLLMConfigurationError("OPENAI_API_KEY is not configured.")

        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": GROUNDING_SYSTEM_MESSAGE,
                },
                {"role": "user", "content": prompt},
            ],
        )

        return response.choices[0].message.content or ""

    def stream_complete(self, prompt: str) -> Iterator[str]:
        """Call OpenAI streaming chat completions and yield text deltas."""

        api_key = self.api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise MissingLLMConfigurationError("OPENAI_API_KEY is not configured.")

        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        stream = client.chat.completions.create(
            model=self.model,
            temperature=0,
            stream=True,
            messages=[
                {
                    "role": "system",
                    "content": GROUNDING_SYSTEM_MESSAGE,
                },
                {"role": "user", "content": prompt},
            ],
        )

        for chunk in stream:
            if not chunk.choices:
                continue
            content = chunk.choices[0].delta.content
            if content:
                yield content


@dataclass(frozen=True)
class OllamaChatClient:
    """Small wrapper around Ollama's local chat API."""

    base_url: str = DEFAULT_OLLAMA_BASE_URL
    model: str = DEFAULT_OLLAMA_MODEL
    timeout_seconds: float = DEFAULT_LLM_TIMEOUT_SECONDS

    def complete(self, prompt: str) -> str:
        """Call a local Ollama model and return the assistant message content."""

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": GROUNDING_SYSTEM_MESSAGE},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
        }
        body = json.dumps(payload).encode("utf-8")
        url = f"{self.base_url.rstrip('/')}/api/chat"
        chat_request = request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with request.urlopen(chat_request, timeout=self.timeout_seconds) as response:
            raw_response = response.read().decode("utf-8")

        response_payload = json.loads(raw_response)
        if not isinstance(response_payload, dict):
            return ""

        message = response_payload.get("message")
        if not isinstance(message, dict):
            return ""

        content = message.get("content")
        return content if isinstance(content, str) else ""

    def stream_complete(self, prompt: str) -> Iterator[str]:
        """Call Ollama's streaming chat API and yield text deltas."""

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": GROUNDING_SYSTEM_MESSAGE},
                {"role": "user", "content": prompt},
            ],
            "stream": True,
        }
        body = json.dumps(payload).encode("utf-8")
        url = f"{self.base_url.rstrip('/')}/api/chat"
        chat_request = request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with request.urlopen(chat_request, timeout=self.timeout_seconds) as response:
            for raw_line in response:
                line = raw_line.decode("utf-8").strip()
                if not line:
                    continue
                response_payload = json.loads(line)
                if not isinstance(response_payload, dict):
                    continue
                message = response_payload.get("message")
                if not isinstance(message, dict):
                    continue
                content = message.get("content")
                if isinstance(content, str) and content:
                    yield content


def configured_llm_client() -> LLMClient | None:
    """Return the configured LLM client, otherwise `None` for evidence fallback."""

    load_local_env()
    provider = os.getenv("LLM_PROVIDER", "").strip().lower()
    if provider == "ollama":
        return OllamaChatClient(
            base_url=os.getenv("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL),
            model=os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL),
            timeout_seconds=_configured_timeout_seconds(),
        )

    if provider not in {"", "openai"}:
        raise UnsupportedLLMProviderError(f"Unsupported LLM_PROVIDER: {provider}")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    model = os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
    return OpenAIChatClient(api_key=api_key, model=model)


def _configured_timeout_seconds() -> float:
    raw_timeout = os.getenv("LLM_TIMEOUT_SECONDS")
    if not raw_timeout:
        return DEFAULT_LLM_TIMEOUT_SECONDS

    try:
        timeout = float(raw_timeout)
    except ValueError:
        return DEFAULT_LLM_TIMEOUT_SECONDS

    return timeout if timeout > 0 else DEFAULT_LLM_TIMEOUT_SECONDS
