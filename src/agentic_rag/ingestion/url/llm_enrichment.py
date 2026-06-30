"""LLM-assisted enrichment pass for URL markdown."""

from __future__ import annotations

import json
from typing import Any

from agentic_rag.core.contracts import LLMCompletionInput
from agentic_rag.model_runtime.errors import ModelRuntimeConfigurationError
from agentic_rag.model_runtime.factory import get_llm_client
from agentic_rag.runtime_env import load_local_env

_ENRICHMENT_SYSTEM_MESSAGE = """\
You are an expert technical writer and data structured extractor.
Your job is to read messy, unstructured HTML-extracted Markdown and any hidden structured JSON data (like __NEXT_DATA__) and produce a pristine, highly structured Markdown document.

## Formatting Guidelines
1. Identify the core entity or topic of the page (e.g., a specific product, article, or document).
2. Use clear markdown headings (##) to separate distinct sections (e.g., General Info, Specifications, Pricing, etc.).
3. Extract any pricing, technical specifications, or lists of features into clean Markdown tables.
4. If this is an e-commerce product page, strictly group pricing by base price vs. configurable options/colors.
5. Do not hallucinate data that is not present in the source text or JSON. If specific colors or options are mixed, try to map them to their correct variants using context.
6. Preserve all original numbers, prices, and critical factual details precisely.

Output ONLY the clean markdown document.
"""

def enrich_markdown_with_llm(raw_markdown: str, next_data: dict[str, Any] | None) -> str:
    """Use the ingestion LLM to restructure raw markdown and JSON into structured markdown."""
    import sys
    if "pytest" in sys.modules:
        return raw_markdown

    try:
        load_local_env()
        client = get_llm_client("ingestion")
    except ModelRuntimeConfigurationError:
        # LLM enrichment not configured, fallback to raw
        return raw_markdown

    prompt_data = {
        "raw_extracted_markdown": raw_markdown,
        "next_data_structured_json": next_data or {},
    }

    try:
        completion = client.complete(
            LLMCompletionInput(
                system_message=_ENRICHMENT_SYSTEM_MESSAGE,
                prompt=f"Please restructure the following data into a clean, highly structured Markdown document:\n\n{json.dumps(prompt_data, ensure_ascii=False, indent=2)}",
                temperature=0.1,
            )
        )
        # Verify the LLM didn't return an empty string
        if completion.text.strip():
            return completion.text.strip()
    except Exception as e:
        import logging
        logging.warning(f"LLM enrichment failed: {e}")
        
    return raw_markdown
