"""Normalized errors raised by model runtime adapters and factories."""

from __future__ import annotations


class ModelRuntimeError(RuntimeError):
    """Base class for model runtime failures."""


class ModelRuntimeConfigurationError(ModelRuntimeError, ValueError):
    """Raised when model runtime configuration is invalid."""


class ModelInvocationError(ModelRuntimeError):
    """Raised when a configured model provider fails during invocation."""
