"""Tests for the runtime entity normalizer + query pre-filter (Phase 2 + 4).

These run against the committed ``entity_map.json`` / ``entity_filter_allowlist.json``
artifacts, so the asserted canonicals are stable facts of the shipped data.
"""

from __future__ import annotations

import types

import pytest

from agentic_rag.ingestion.metadata import (
    build_entity_menu,
    detect_in_query,
    normalize,
    normalize_all,
    normalize_filterable,
)


# --------------------------------------------------------------------------
# normalize / normalize_all / normalize_filterable
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("VF8", "VF 8"),
        ("VinFast VF 8", "VF 8"),
        ("Thảm Cốp 3D VF 7", "VF 7"),
        ("TP.HCM", "Hồ Chí Minh"),
        ("KlaraS", "Klara S"),
    ],
)
def test_normalize_variant_to_canonical(raw: str, expected: str) -> None:
    assert normalize(raw) == expected


def test_normalize_unknown_returns_input() -> None:
    assert normalize("một thứ chưa từng thấy") == "một thứ chưa từng thấy"


def test_normalize_generic_kept_as_is() -> None:
    # generic terms exist in the map but are not rewritten to anything else
    assert normalize("pin") == "pin"


def test_normalize_all_dedupes_canonicals() -> None:
    result = normalize_all(["VF8", "VinFast VF 8", "Thảm Cốp 3D VF 8", "Hà Nội"])
    assert result == ["VF 8", "Hà Nội"]


def test_normalize_filterable_drops_generic_and_brand() -> None:
    # "VinFast" (brand) and "pin" (generic) must be dropped; "VF 8" kept.
    result = normalize_filterable(["VinFast", "VF 8", "pin"])
    assert result == ["VF 8"]


# --------------------------------------------------------------------------
# detect_in_query (dictionary, allowlist-gated, word-boundary safe)
# --------------------------------------------------------------------------
def test_detect_direct_mention() -> None:
    assert detect_in_query("pin VF8 mấy kWh") == ["VF 8"]


def test_detect_multiple_entities_union() -> None:
    found = detect_in_query("so sánh VF 8 với VF 9")
    assert set(found) == {"VF 8", "VF 9"}


def test_detect_no_entity_returns_empty() -> None:
    assert detect_in_query("chính sách bảo hành thế nào") == []


def test_detect_does_not_false_match_short_location() -> None:
    # "Mỹ" (location) must not match inside "thẩm mỹ".
    assert "Mỹ" not in detect_in_query("thẩm mỹ viện gần đây")


def test_detect_empty_query() -> None:
    assert detect_in_query("") == []


def test_detect_only_returns_allowlisted() -> None:
    # Everything detected must be a high-coverage (allowlisted) canonical.
    from agentic_rag.ingestion.metadata.entity_normalizer import _filter_allowlist

    allowlist = _filter_allowlist()
    if allowlist is None:
        pytest.skip("no allowlist artifact present")
    found = detect_in_query("VF 8 ở Hà Nội và Theon S")
    assert set(found) <= allowlist


# --------------------------------------------------------------------------
# build_entity_menu
# --------------------------------------------------------------------------
def test_build_entity_menu_has_types() -> None:
    menu = build_entity_menu()
    assert "car_model:" in menu
    assert "VF 8" in menu


# --------------------------------------------------------------------------
# Qdrant filter builder — entity_filter adds a union MatchAny on the canonical field
# --------------------------------------------------------------------------
def _fake_models() -> types.SimpleNamespace:
    class MatchAny:
        def __init__(self, any: list[str]) -> None:
            self.any = any

    class MatchValue:
        def __init__(self, value: str) -> None:
            self.value = value

    class FieldCondition:
        def __init__(self, key: str, match: object) -> None:
            self.key = key
            self.match = match

    class Filter:
        def __init__(self, must: list[object], must_not: list[object]) -> None:
            self.must = must
            self.must_not = must_not

    return types.SimpleNamespace(
        MatchAny=MatchAny, MatchValue=MatchValue, FieldCondition=FieldCondition, Filter=Filter
    )


def test_combined_filter_adds_entity_condition() -> None:
    from agentic_rag.retrieval.search import (
        _QDRANT_ENTITIES_CANONICAL_FIELD,
        _qdrant_combined_filter,
    )

    models = _fake_models()
    flt = _qdrant_combined_filter(
        None, exclude_dedup_layers=None, entity_filter=["VF 8", "VF 9"], models=models
    )
    entity_conditions = [c for c in flt.must if c.key == _QDRANT_ENTITIES_CANONICAL_FIELD]
    assert len(entity_conditions) == 1
    assert entity_conditions[0].match.any == ["VF 8", "VF 9"]


def test_combined_filter_without_entity_filter_has_no_entity_condition() -> None:
    from agentic_rag.retrieval.search import (
        _QDRANT_ENTITIES_CANONICAL_FIELD,
        _qdrant_combined_filter,
    )

    models = _fake_models()
    flt = _qdrant_combined_filter(None, exclude_dedup_layers=None, models=models)
    assert all(c.key != _QDRANT_ENTITIES_CANONICAL_FIELD for c in flt.must)


# --------------------------------------------------------------------------
# ENV flag
# --------------------------------------------------------------------------
def test_prefilter_flag_off(monkeypatch: pytest.MonkeyPatch) -> None:
    from agentic_rag.retrieval import search

    monkeypatch.setenv("HARD_FILTER_ENABLED", "false")
    assert search._entity_prefilter_for("VF 8 giá bao nhiêu") is None


def test_prefilter_flag_on(monkeypatch: pytest.MonkeyPatch) -> None:
    from agentic_rag.retrieval import search

    monkeypatch.setenv("HARD_FILTER_ENABLED", "true")
    assert search._entity_prefilter_for("VF 8 giá bao nhiêu") == ["VF 8"]


# --------------------------------------------------------------------------
# C/D — LLM paraphrase fallback (flag-gated, closed-set validated)
# --------------------------------------------------------------------------
def test_llm_paraphrase_fallback_on(monkeypatch: pytest.MonkeyPatch) -> None:
    from agentic_rag.retrieval import search

    search._llm_detect_entities.cache_clear()
    monkeypatch.setenv("HARD_FILTER_ENABLED", "true")
    monkeypatch.setenv("ENTITY_PREFILTER_LLM", "true")

    class FakeClient:
        def complete(self, request: object) -> object:
            # one valid canonical + one hallucinated name that must be dropped
            return types.SimpleNamespace(text='["VF 9", "Xe Bay Vũ Trụ"]')

    monkeypatch.setattr(
        "agentic_rag.model_runtime.factory.get_llm_client", lambda role: FakeClient()
    )
    # Paraphrase with no literal entity -> dictionary misses -> LLM fallback.
    result = search._entity_prefilter_for("mẫu SUV điện cao cấp nhất")
    assert result == ["VF 9"]  # hallucinated entity filtered out by allowlist


def test_llm_paraphrase_fallback_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    from agentic_rag.retrieval import search

    search._llm_detect_entities.cache_clear()
    monkeypatch.setenv("HARD_FILTER_ENABLED", "true")
    monkeypatch.delenv("ENTITY_PREFILTER_LLM", raising=False)  # default off
    # No literal entity + LLM off -> no pre-filter (full search).
    assert search._entity_prefilter_for("mẫu SUV điện cao cấp nhất") is None
