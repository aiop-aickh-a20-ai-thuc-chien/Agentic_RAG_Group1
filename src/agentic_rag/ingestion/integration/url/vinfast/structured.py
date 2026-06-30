"""Optional Instructor/OpenAI structured text and screenshot extraction."""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
from typing import Any

from agentic_rag.ingestion.integration.url.vinfast.models import VinFastProduct

_FIELDS_PROMPT = """Extract the VinFast product shown in the supplied evidence.
Return product_type, model_name, variant, base_price_vnd as integer VND,
battery_subscription, scale_ratio, specs, promotions, source_url and scraped_at.
Do not invent values that are not visible in the evidence."""


def parse_text_with_instructor(
    raw_text: str,
    source_url: str,
    *,
    model: str | None = None,
    client: Any | None = None,
) -> VinFastProduct:
    """Convert raw source-backed text into the strict product schema."""

    structured, resolved_model = _structured_client(client, model)
    response = structured.chat.completions.create(
        model=resolved_model,
        response_model=VinFastProduct,
        messages=[
            {
                "role": "user",
                "content": (
                    f"{_FIELDS_PROMPT}\nsource_url: {source_url}\n"
                    f"scraped_at: {datetime.now(UTC).isoformat()}\n\n{raw_text}"
                ),
            }
        ],
    )
    return VinFastProduct.model_validate(response)


def extract_screenshot_with_instructor(
    screenshot_path: str | Path,
    source_url: str,
    *,
    model: str | None = None,
    client: Any | None = None,
) -> VinFastProduct:
    """Use a screenshot only after network and DOM extraction are exhausted."""

    return extract_screenshot_bytes_with_instructor(
        Path(screenshot_path).read_bytes(), source_url, model=model, client=client
    )


def extract_screenshot_bytes_with_instructor(
    screenshot: bytes,
    source_url: str,
    *,
    model: str | None = None,
    client: Any | None = None,
) -> VinFastProduct:
    """Extract a product from in-memory PNG bytes without creating a temp file."""

    image = base64.b64encode(screenshot).decode("ascii")
    structured, resolved_model = _structured_client(client, model)
    response = structured.chat.completions.create(
        model=resolved_model,
        response_model=VinFastProduct,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image}"}},
                    {
                        "type": "text",
                        "text": (
                            f"{_FIELDS_PROMPT}\nsource_url: {source_url}\n"
                            f"scraped_at: {datetime.now(UTC).isoformat()}"
                        ),
                    },
                ],
            }
        ],
    )
    return VinFastProduct.model_validate(response)


def _structured_client(client: Any | None, model: str | None) -> tuple[Any, str]:
    if client is not None:
        return client, model or "gpt-4o"
    structured, configured_model = _instructor_client()
    return structured, model or configured_model


def _instructor_client() -> tuple[Any, str]:
    try:
        instructor = import_module("instructor")
        openai = import_module("openai")
        from agentic_rag.model_runtime.config import resolve_llm_profile

        profile = resolve_llm_profile("ingestion")
        if profile.provider != "openai" or not profile.model:
            raise RuntimeError("VinFast structured extraction requires LLM_PROVIDER=openai")
        client_options: dict[str, object] = {"timeout": profile.timeout_seconds}
        if profile.api_key:
            client_options["api_key"] = profile.api_key
        if profile.api_base:
            client_options["base_url"] = profile.api_base
        return instructor.from_openai(openai.OpenAI(**client_options)), profile.model
    except (ImportError, AttributeError) as exc:
        raise RuntimeError(
            "Instructor and OpenAI are required; install the vinfast-pipeline extra"
        ) from exc
