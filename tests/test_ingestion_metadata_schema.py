from __future__ import annotations

import pytest

from agentic_rag.ingestion.metadata import (
    DOCUMENT_TYPE_VALUES,
    REQUIRED_METADATA_FIELDS,
    SOURCE_CATEGORY_VALUES,
    SOURCE_TYPE_VALUES,
    has_required_metadata,
    missing_required_metadata,
    normalize_metadata,
    require_metadata,
)


def test_source_type_and_updated_date_are_required() -> None:
    assert REQUIRED_METADATA_FIELDS == ("source_type", "updated_date")
    assert {"official", "internal", "partner", "news", "community", "unknown"} <= (
        SOURCE_TYPE_VALUES
    )
    assert SOURCE_CATEGORY_VALUES == SOURCE_TYPE_VALUES
    assert {"policy", "faq", "product_detail"} <= DOCUMENT_TYPE_VALUES

    assert missing_required_metadata({}) == ("source_type", "updated_date")
    assert missing_required_metadata({"source_type": "", "updated_date": ""}) == (
        "source_type",
        "updated_date",
    )
    assert missing_required_metadata({"source_type": "official"}) == ("updated_date",)
    assert (
        missing_required_metadata({"source_type": "official", "updated_date": "2026-06-16"}) == ()
    )
    assert has_required_metadata({"source_type": "internal", "updated_date": "2026-06-16"})
    assert has_required_metadata(
        {"source_type": "internal", "updated_date": "2026-06-16", "document_type": None}
    )

    with pytest.raises(ValueError, match="source_type, updated_date"):
        require_metadata({"document_type": "policy"})


def test_normalize_metadata_coerces_shared_fields_and_entities() -> None:
    normalized = normalize_metadata(
        {
            "source": "https://shop.vinfastauto.com/vn_vi/vf8",
            "source_type": "Official",
            "document_type": "not-a-real-type",
            "language": "VI",
            "product_model": "VF 8",
            "keywords": "pin; bao hanh",
            "entities": ["VF 8", "VinFast", "VF 8"],
            "updated_date": "",
            "captured_at": "2026-06-18T10:00:00+07:00",
        }
    )

    assert normalized["source_type"] == "official"
    assert normalized["document_type"] == "unknown"
    assert normalized["language"] == "vi"
    assert normalized["product_model"] == ["VF 8"]
    assert normalized["keywords"] == ["pin", "bao hanh"]
    assert normalized["entities"] == ["VF 8", "VinFast"]
    assert "VF 8" in normalized["entities_canonical"]
    assert normalized["updated_date"] == "2026-06-18T10:00:00+07:00"


def test_normalize_metadata_is_idempotent_for_lists() -> None:
    metadata = {
        "source_type": "internal",
        "updated_date": "2026-06-18",
        "entities": ["VF 8"],
        "entities_canonical": ["VF 8"],
    }

    assert normalize_metadata(normalize_metadata(metadata)) == normalize_metadata(metadata)
