"""LiteLLM-backed LLM adapter."""

from __future__ import annotations

import importlib
from collections.abc import Iterator
from typing import Any, cast

from pydantic import BaseModel, ConfigDict

from agentic_rag.core.contracts import (
    LLMCompletionInput,
    LLMCompletionOutput,
    LLMStreamDelta,
)
from agentic_rag.model_runtime.config import LLMProfileConfig
from agentic_rag.model_runtime.errors import (
    ModelInvocationError,
    ModelRuntimeConfigurationError,
)


class LiteLLMClient(BaseModel):
    """Normalize LLM completion and streaming calls through LiteLLM."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    config: LLMProfileConfig

    def complete(self, request: LLMCompletionInput) -> LLMCompletionOutput:
        """Return one normalized text completion."""

        try:
            litellm = importlib.import_module("litellm")
            response = litellm.completion(**self._completion_kwargs(request))
        except Exception as exc:
            raise ModelInvocationError(f"LLM invocation failed: {exc}") from exc

        return LLMCompletionOutput(
            text=_extract_completion_text(response),
            provider=self.config.provider,
            model=self._model_name(),
        )

    def stream(self, request: LLMCompletionInput) -> Iterator[LLMStreamDelta]:
        """Yield normalized text deltas from a LiteLLM streaming completion."""

        try:
            litellm = importlib.import_module("litellm")
            stream = litellm.completion(
                **self._completion_kwargs(request),
                stream=True,
            )
            for chunk in stream:
                text = _extract_stream_delta_text(chunk)
                if text:
                    yield LLMStreamDelta(text=text)
        except Exception as exc:
            raise ModelInvocationError(f"LLM streaming invocation failed: {exc}") from exc

    def _completion_kwargs(self, request: LLMCompletionInput) -> dict[str, object]:
        kwargs: dict[str, object] = {
            "model": self._model_name(),
            "messages": [
                {"role": "system", "content": request.system_message},
                {"role": "user", "content": request.prompt},
            ],
            "temperature": request.temperature,
            "timeout": self.config.timeout_seconds,
        }
        if self.config.api_base is not None:
            kwargs["api_base"] = self.config.api_base
        if self.config.api_key is not None:
            kwargs["api_key"] = self.config.api_key
        return kwargs

    def _model_name(self) -> str:
        if self.config.provider == "none" or not self.config.model:
            raise ModelRuntimeConfigurationError("LiteLLMClient requires an enabled model profile.")
        provider = "openai" if self.config.provider == "local" else self.config.provider
        prefix = f"{provider}/"
        if self.config.model.startswith(prefix):
            return self.config.model
        return f"{prefix}{self.config.model}"


def _extract_completion_text(response: object) -> str:
    choice = _first_choice(response)
    message = _get(choice, "message")
    content = _get(message, "content") if message is not None else None
    return content if isinstance(content, str) else ""


def _extract_stream_delta_text(chunk: object) -> str:
    choice = _first_choice(chunk)
    delta = _get(choice, "delta")
    content = _get(delta, "content") if delta is not None else None
    return content if isinstance(content, str) else ""


def _first_choice(response: object) -> object | None:
    choices = _get(response, "choices")
    if isinstance(choices, list) and choices:
        return cast(object, choices[0])
    return None


def _get(value: object, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)
