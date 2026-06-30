"""Backfill duplicate metadata for already-ingested local source documents."""

from __future__ import annotations

import argparse
import json

from dotenv import load_dotenv

from agentic_rag.generation.evidence import (
    configured_evidence_provider_name,
    source_provider_from_env,
)
from agentic_rag.integrations.local_pdf.providers import LocalPdfEvidenceProvider
from agentic_rag.runtime_env import load_local_env


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill ingestion dedup metadata across existing source chunks.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run detection and print the summary without writing chunks or vector payloads.",
    )
    parser.add_argument(
        "--strict-embedding",
        action="store_true",
        help="Fail when Layer 3 embedding dedup fails instead of falling back to exact/simhash.",
    )
    args = parser.parse_args()

    load_dotenv()
    load_local_env()
    provider_name = configured_evidence_provider_name()
    provider = source_provider_from_env()
    if provider_name != "local_pdf" or not isinstance(provider, LocalPdfEvidenceProvider):
        raise SystemExit("Dedup backfill is only supported when EVIDENCE_PROVIDER=local_pdf.")

    result = provider.backfill_dedup(
        strict_embedding=args.strict_embedding,
        dry_run=args.dry_run,
    )
    print(json.dumps(_jsonable(result), ensure_ascii=False, indent=2, sort_keys=True))


def _jsonable(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


if __name__ == "__main__":
    main()
