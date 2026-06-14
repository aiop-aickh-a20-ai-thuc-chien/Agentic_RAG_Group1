from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from agentic_rag.ingestion.knowledge_quality import analyze_chunks
from agentic_rag.testing.knowledge_quality_cases import (
    REQUIRED_METHODS,
    KnowledgeQualityCase,
    build_knowledge_quality_case_studies,
    render_knowledge_quality_case_studies_markdown,
)


def test_case_schema_is_strict_and_frozen() -> None:
    case = KnowledgeQualityCase.model_validate(
        {
            "case_id": "case_exact_duplicate_v1",
            "conflict_type": "exact_duplicate",
            "chunks": [],
            "expected_methods": ["deterministic_v1"],
            "expected_conflict": True,
            "notes": "Exact duplicate chunks.",
        }
    )

    assert case.case_id == "case_exact_duplicate_v1"

    with pytest.raises(ValidationError):
        KnowledgeQualityCase.model_validate(
            {
                "case_id": "case_exact_duplicate_v1",
                "conflict_type": "exact_duplicate",
                "chunks": [],
                "expected_methods": ["deterministic_v1"],
                "expected_conflict": True,
                "notes": "Exact duplicate chunks.",
                "unexpected": True,
            }
        )

    with pytest.raises(ValidationError):
        case.expected_conflict = False  # type: ignore[misc]


def test_case_studies_include_required_scenarios_with_stable_ids() -> None:
    cases = build_knowledge_quality_case_studies()
    expected_case_ids = [
        "case_exact_duplicate_v1",
        "case_near_duplicate_v1",
        "case_numeric_conflict_v1",
        "case_temporal_conflict_v1",
        "case_policy_conflict_v1",
        "case_entity_relation_conflict_v1",
        "case_causal_conflict_v1",
        "case_exception_conflict_v1",
        "case_recommendation_conflict_v1",
        "case_equivalent_paraphrase_non_conflict_v1",
        "case_metadata_supersession_non_conflict_v1",
    ]

    assert len(cases) >= 11
    assert len({case.case_id for case in cases}) == len(cases)
    assert [case.case_id for case in cases] == expected_case_ids
    assert {case.conflict_type for case in cases} >= {
        "exact_duplicate",
        "near_duplicate",
        "numeric",
        "temporal",
        "policy",
        "entity_relation",
        "causal",
        "exception",
        "recommendation",
        "equivalent_paraphrase",
        "metadata_supersession",
    }


def test_every_required_method_has_positive_and_negative_case() -> None:
    cases = build_knowledge_quality_case_studies()

    for method in REQUIRED_METHODS:
        positive = [
            case for case in cases if method in case.expected_methods and case.expected_conflict
        ]
        negative = [
            case for case in cases if method in case.expected_methods and not case.expected_conflict
        ]

        assert positive, method
        assert negative, method


def test_renderer_is_deterministic_and_table_like() -> None:
    cases = build_knowledge_quality_case_studies()

    rendered_once = render_knowledge_quality_case_studies_markdown(cases)
    rendered_twice = render_knowledge_quality_case_studies_markdown(tuple(cases))

    assert rendered_once == rendered_twice
    assert rendered_once.startswith("| case_id |")
    assert "| expected_methods |" in rendered_once
    assert rendered_once.count("\n") >= len(cases)
    assert not re.search(r"\s+$", rendered_once, flags=re.MULTILINE)


def test_renderer_includes_case_notes_and_chunk_ids() -> None:
    cases = build_knowledge_quality_case_studies()
    rendered = render_knowledge_quality_case_studies_markdown(cases)

    assert "case_exact_duplicate_v1" in rendered
    assert "expected_conflict" in rendered
    assert "notes" in rendered
    assert any(chunk.chunk_id in rendered for case in cases for chunk in case.chunks)


@pytest.mark.parametrize(
    ("case_id", "method", "expected_finding"),
    [
        ("case_exact_duplicate_v1", "deterministic_v1", True),
        ("case_near_duplicate_v1", "deterministic_v1", True),
        ("case_numeric_conflict_v1", "deterministic_v1", True),
        ("case_temporal_conflict_v1", "metadata_rules", True),
        ("case_entity_relation_conflict_v1", "metadata_rules", True),
        ("case_policy_conflict_v1", "semantic_rules", True),
        ("case_recommendation_conflict_v1", "semantic_rules", True),
        ("case_equivalent_paraphrase_non_conflict_v1", "semantic_rules", False),
        ("case_metadata_supersession_non_conflict_v1", "metadata_rules", False),
    ],
)
def test_offline_case_expectations_match_detector_behavior(
    case_id: str,
    method: str,
    expected_finding: bool,
) -> None:
    case = next(item for item in build_knowledge_quality_case_studies() if item.case_id == case_id)

    report = analyze_chunks(list(case.chunks), methods=[method])

    assert bool(report.findings) is expected_finding
