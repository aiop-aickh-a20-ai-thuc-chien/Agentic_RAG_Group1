from __future__ import annotations

import pytest

from agentic_rag.ingestion.metadata import (
    DOCUMENT_TYPE_VALUES,
    REQUIRED_METADATA_FIELDS,
    SOURCE_CATEGORY_VALUES,
    SOURCE_TYPE_VALUES,
    has_required_metadata,
    missing_required_metadata,
    require_metadata,
)


def test_source_type_and_updated_date_are_required() -> None:
    assert REQUIRED_METADATA_FIELDS == ("source_type", "updated_date")
    assert {"pdf", "url", "html", "text"} <= SOURCE_TYPE_VALUES
    assert {"official", "internal", "news"} <= SOURCE_CATEGORY_VALUES
    assert {"policy", "faq", "product_detail"} <= DOCUMENT_TYPE_VALUES

    assert missing_required_metadata({}) == ("source_type", "updated_date")
    assert missing_required_metadata({"source_type": "", "updated_date": ""}) == (
        "source_type",
        "updated_date",
    )
    assert missing_required_metadata({"source_type": "url"}) == ("updated_date",)
    assert missing_required_metadata({"source_type": "url", "updated_date": "2026-06-16"}) == ()
    assert has_required_metadata({"source_type": "pdf", "updated_date": "2026-06-16"})
    assert has_required_metadata(
        {"source_type": "pdf", "updated_date": "2026-06-16", "document_type": None}
    )

    with pytest.raises(ValueError, match="source_type, updated_date"):
        require_metadata({"document_type": "policy"})
