"""VLM adapter protocol; implementations must return cited structured evidence."""

from agentic_rag.core.ports import LLMClient
from agentic_rag.ingestion.integration.url.adapters.base import ExtractionAdapter
from agentic_rag.model_runtime.errors import ModelRuntimeConfigurationError

VlmRegionAdapter = ExtractionAdapter


def configured_ingestion_vlm_client() -> LLMClient | None:
    """Resolve INGESTION_LLM_* with the existing LLM_* fallback."""

    # TODO [guide_2/vinfast_pipeline_todo §4 – Validate VLM output with Pydantic]:
    # After calling the VLM, validate the returned JSON against the VinFastProduct
    # Pydantic schema (model_name, variant, base_price_vnd, battery_subscription,
    # specs, promotions). Reject if required fields are missing.
    # Reference: guide_2/vinfast_pipeline_todo (1).md §4
    #
    # TODO [guide_2/vinfast_pipeline_todo §5 – Deterministic chunk_id for VLM output]:
    # Assign `chunk_id = md5(f"{model_name}-{variant}-{battery_subscription}".encode()).hexdigest()`
    # so that repeated VLM calls for the same product state produce the same
    # chunk ID and do not create duplicates in the Vector DB.
    # Reference: guide_2/vinfast_pipeline_todo (1).md §5
    #
    # TODO [guide_2/vinfast_pipeline_todo §4 reconcile – VLM vs API priority]:
    # If VLM output conflicts with API/network data for the same field,
    # always prefer the API/network value. Mark conflicting VLM fields as
    # `origin="visually_inferred"` and `confidence < 1.0` so reconciliation
    # can demote them. See `reconciliation.py` TODO for the enforcement point.
    # Reference: guide_2/vinfast_pipeline_todo (1).md §4 reconcile rule
    try:
        from agentic_rag.model_runtime.factory import get_llm_client

        return get_llm_client("ingestion")
    except ModelRuntimeConfigurationError:
        return None


__all__ = ["VlmRegionAdapter", "configured_ingestion_vlm_client"]
