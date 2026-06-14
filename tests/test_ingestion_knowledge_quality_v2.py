from __future__ import annotations

from collections.abc import Iterator

import pytest

from agentic_rag.core.contracts import (
    Chunk,
    LLMCompletionInput,
    LLMCompletionOutput,
    LLMStreamDelta,
)
from agentic_rag.ingestion.knowledge_quality import (
    AVAILABLE_KNOWLEDGE_QUALITY_METHODS,
    KnowledgeQualityConfigurationError,
    KnowledgeQualityInvocationError,
    UnknownKnowledgeQualityMethodError,
    analyze_chunks,
    parse_knowledge_quality_methods,
)


class _FakeLLMClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = iter(responses)
        self.requests: list[LLMCompletionInput] = []

    def complete(self, request: LLMCompletionInput) -> LLMCompletionOutput:
        self.requests.append(request)
        return LLMCompletionOutput(
            text=next(self.responses),
            provider="test-provider",
            model="small-test-model",
        )

    def stream(self, request: LLMCompletionInput) -> Iterator[LLMStreamDelta]:
        raise AssertionError("Knowledge-quality methods must use non-streaming completion.")


def test_registry_lists_every_v2_method() -> None:
    assert AVAILABLE_KNOWLEDGE_QUALITY_METHODS == (
        "deterministic_v1",
        "metadata_rules",
        "semantic_rules",
        "semantic_verifier",
        "agentic_review",
    )


@pytest.mark.parametrize("raw", [None, "", "   ", []])
def test_empty_method_selection_defaults_to_deterministic_v1(
    raw: str | list[str] | None,
) -> None:
    assert parse_knowledge_quality_methods(raw) == ["deterministic_v1"]


def test_method_parser_preserves_order_and_removes_duplicates() -> None:
    assert parse_knowledge_quality_methods("semantic_rules, deterministic_v1,semantic_rules") == [
        "semantic_rules",
        "deterministic_v1",
    ]


def test_unknown_method_raises_typed_validation_error() -> None:
    with pytest.raises(UnknownKnowledgeQualityMethodError, match="unknown"):
        parse_knowledge_quality_methods("deterministic_v1,unknown")


def test_default_analysis_remains_deterministic_v1() -> None:
    chunks = [
        Chunk(
            chunk_id="left",
            text="VF 8 duoc bao hanh 8 nam.",
            metadata={"source": "left.txt"},
        ),
        Chunk(
            chunk_id="right",
            text="VF 8 duoc bao hanh 6 nam.",
            metadata={"source": "right.txt"},
        ),
    ]

    report = analyze_chunks(chunks)

    assert report.metadata["methods"] == ["deterministic_v1"]
    assert report.findings
    assert all(finding.metadata["method"] == "deterministic_v1" for finding in report.findings)


def test_metadata_rules_detect_same_period_entity_relation_conflict() -> None:
    chunks = [
        Chunk(
            chunk_id="left",
            text="VF 8 market status.",
            metadata={
                "source": "left.txt",
                "entity": "VF 8",
                "attribute": "market_status",
                "value": "available",
                "effective_date": "2026-01-01",
            },
        ),
        Chunk(
            chunk_id="right",
            text="VF 8 market status.",
            metadata={
                "source": "right.txt",
                "entity": "VF 8",
                "attribute": "market_status",
                "value": "discontinued",
                "effective_date": "2026-01-01",
            },
        ),
    ]

    report = analyze_chunks(chunks, methods=["metadata_rules"])

    assert len(report.findings) == 1
    finding = report.findings[0]
    assert finding.kind == "conflict"
    assert finding.metadata["method"] == "metadata_rules"
    assert finding.metadata["conflict_type"] == "entity_relation"


def test_metadata_rules_treat_explicit_supersession_as_non_conflict() -> None:
    chunks = [
        Chunk(
            chunk_id="old",
            text="VF 8 policy version 1.",
            metadata={
                "document_id": "policy-v1",
                "entity": "VF 8",
                "attribute": "charging_policy",
                "value": "station_only",
                "version": "1",
                "effective_date": "2025-01-01",
            },
        ),
        Chunk(
            chunk_id="new",
            text="VF 8 policy version 2.",
            metadata={
                "document_id": "policy-v2",
                "entity": "VF 8",
                "attribute": "charging_policy",
                "value": "home_or_station",
                "version": "2",
                "effective_date": "2026-01-01",
                "supersedes": "policy-v1",
            },
        ),
    ]

    report = analyze_chunks(chunks, methods=["metadata_rules"])

    assert report.findings == []


def test_metadata_rules_ignore_chunks_without_comparable_metadata() -> None:
    chunks = [
        Chunk(chunk_id="left", text="VF 8 is available.", metadata={"source": "a"}),
        Chunk(chunk_id="right", text="VF 8 is unavailable.", metadata={"source": "b"}),
    ]

    report = analyze_chunks(chunks, methods=["metadata_rules"])

    assert report.findings == []


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("VF 8 can use home charging.", "VF 8 cannot use home charging."),
        ("VF 8 duoc phep sac tai nha.", "VF 8 khong duoc phep sac tai nha."),
        ("VF 9 charging is required.", "VF 9 charging is optional."),
        ("VF 9 bat buoc kiem tra pin.", "VF 9 khong bat buoc kiem tra pin."),
    ],
)
def test_semantic_rules_detect_opposite_policy_modalities(
    left: str,
    right: str,
) -> None:
    report = analyze_chunks(
        [
            Chunk(chunk_id="left", text=left, metadata={"source": "a"}),
            Chunk(chunk_id="right", text=right, metadata={"source": "b"}),
        ],
        methods=["semantic_rules"],
    )

    assert len(report.findings) == 1
    assert report.findings[0].metadata["method"] == "semantic_rules"
    assert report.findings[0].metadata["conflict_type"] == "policy"


def test_semantic_rules_detect_recommendation_conflict() -> None:
    report = analyze_chunks(
        [
            Chunk(
                chunk_id="left",
                text="VF 8 owners should use fast charging daily.",
                metadata={},
            ),
            Chunk(
                chunk_id="right",
                text="VF 8 owners should not use fast charging daily.",
                metadata={},
            ),
        ],
        methods=["semantic_rules"],
    )

    assert len(report.findings) == 1
    assert report.findings[0].metadata["conflict_type"] == "recommendation"


def test_semantic_rules_do_not_flag_equivalent_positive_paraphrases() -> None:
    report = analyze_chunks(
        [
            Chunk(
                chunk_id="left",
                text="VF 8 can use home charging.",
                metadata={},
            ),
            Chunk(
                chunk_id="right",
                text="VF 8 is allowed to use home charging.",
                metadata={},
            ),
        ],
        methods=["semantic_rules"],
    )

    assert report.findings == []


def _semantic_candidate_chunks() -> list[Chunk]:
    return [
        Chunk(
            chunk_id="left",
            text="VF 8 battery failures are caused by frequent fast charging.",
            metadata={"source": "left.txt"},
        ),
        Chunk(
            chunk_id="right",
            text="VF 8 battery failures are not caused by frequent fast charging.",
            metadata={"source": "right.txt"},
        ),
    ]


@pytest.mark.parametrize("method", ["semantic_verifier", "agentic_review"])
def test_model_backed_methods_require_an_explicit_client(method: str) -> None:
    with pytest.raises(KnowledgeQualityConfigurationError, match="INGESTION_LLM"):
        analyze_chunks(_semantic_candidate_chunks(), methods=[method])


def test_semantic_verifier_creates_stable_contradiction_finding() -> None:
    client = _FakeLLMClient(
        [
            """
            {
              "verdict": "contradiction",
              "conflict_type": "causal",
              "confidence": 0.91,
              "evidence_spans": ["caused by", "not caused by"],
              "reason": "The causal claims have opposite polarity."
            }
            """
        ]
    )

    first = analyze_chunks(
        _semantic_candidate_chunks(),
        methods=["semantic_verifier"],
        llm_client=client,
    )
    second = analyze_chunks(
        _semantic_candidate_chunks(),
        methods=["semantic_verifier"],
        llm_client=_FakeLLMClient(
            [
                """
                {
                  "verdict": "contradiction",
                  "conflict_type": "causal",
                  "confidence": 0.91,
                  "evidence_spans": ["caused by", "not caused by"],
                  "reason": "The causal claims have opposite polarity."
                }
                """
            ]
        ),
    )

    assert len(first.findings) == 1
    finding = first.findings[0]
    assert finding.finding_id == second.findings[0].finding_id
    assert finding.metadata["method"] == "semantic_verifier"
    assert finding.metadata["conflict_type"] == "causal"
    assert finding.metadata["verifier_model"] == "small-test-model"
    assert finding.metadata["verdict"] == "contradiction"


@pytest.mark.parametrize("verdict", ["support", "unrelated", "uncertain"])
def test_semantic_verifier_ignores_non_conflict_verdicts(verdict: str) -> None:
    client = _FakeLLMClient(
        [
            f"""
            {{
              "verdict": "{verdict}",
              "conflict_type": "causal",
              "confidence": 0.75,
              "evidence_spans": [],
              "reason": "No confirmed contradiction."
            }}
            """
        ]
    )

    report = analyze_chunks(
        _semantic_candidate_chunks(),
        methods=["semantic_verifier"],
        llm_client=client,
    )

    assert report.findings == []


def test_semantic_verifier_rejects_malformed_model_output() -> None:
    with pytest.raises(KnowledgeQualityInvocationError, match="valid JSON"):
        analyze_chunks(
            _semantic_candidate_chunks(),
            methods=["semantic_verifier"],
            llm_client=_FakeLLMClient(["not-json"]),
        )


def test_agentic_review_uses_sequential_roles_and_arbiter_verdict() -> None:
    client = _FakeLLMClient(
        [
            (
                '{"claims": ["fast charging causes failures", '
                '"fast charging does not cause failures"]}'
            ),
            """
            {
              "verdict": "contradiction",
              "conflict_type": "causal",
              "confidence": 0.86,
              "evidence_spans": ["caused by", "not caused by"],
              "reason": "Verifier found opposite causal claims."
            }
            """,
            """
            {
              "verdict": "contradiction",
              "conflict_type": "causal",
              "confidence": 0.94,
              "evidence_spans": ["caused by", "not caused by"],
              "reason": "Arbiter confirms the contradiction."
            }
            """,
        ]
    )

    report = analyze_chunks(
        _semantic_candidate_chunks(),
        methods=["agentic_review"],
        llm_client=client,
    )

    assert len(client.requests) == 3
    assert [
        request.system_message.split("You are the ")[1].split(".")[0] for request in client.requests
    ] == ["claim extractor", "verifier", "arbiter"]
    finding = report.findings[0]
    assert finding.metadata["method"] == "agentic_review"
    assert finding.metadata["agent_notes"]
    assert finding.metadata["max_rounds"] == 1


def test_agentic_review_does_not_create_finding_for_uncertain_arbiter() -> None:
    client = _FakeLLMClient(
        [
            '{"claims": ["claim one", "claim two"]}',
            """
            {
              "verdict": "contradiction",
              "conflict_type": "causal",
              "confidence": 0.7,
              "evidence_spans": [],
              "reason": "Possible conflict."
            }
            """,
            """
            {
              "verdict": "uncertain",
              "conflict_type": "causal",
              "confidence": 0.5,
              "evidence_spans": [],
              "reason": "Context is insufficient."
            }
            """,
        ]
    )

    report = analyze_chunks(
        _semantic_candidate_chunks(),
        methods=["agentic_review"],
        llm_client=client,
    )

    assert report.findings == []
