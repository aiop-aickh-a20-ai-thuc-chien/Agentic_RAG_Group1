from agentic_rag.ingestion.url.acquisition import (
    FetchedPage,
    acquisition_record_from_fetched_page,
)
from agentic_rag.ingestion.url.interactions import (
    InteractionCaptureResult,
    InteractionControl,
    InteractionProfile,
    InteractionStateRecord,
    SectionVisit,
    assess_configurator_readiness,
    finalize_traversal,
    stable_control_identity,
)


def test_acquisition_record_is_bounded_and_keeps_evidence_separate() -> None:
    record = acquisition_record_from_fetched_page(
        FetchedPage(html="abcdef", url="https://example.test/final", original_url="https://example.test/start"),
        framework_state={"modelId": "Products-Car-VF9"},
        network_payload_refs=("network.jsonl#1",),
        max_html_chars=4,
    )

    assert record.requested_url == "https://example.test/start"
    assert record.rendered_html == "abcd"
    assert record.html_truncated is True
    assert record.network_payload_refs == ("network.jsonl#1",)


def test_configurator_state_graph_reports_complete_scoped_capture() -> None:
    edition = InteractionControl(
        control_id="dom-1",
        label="VF 9 Eco",
        group="edition",
        attributes={"data-variant-id": "NE3NV"},
    )
    readiness = assess_configurator_readiness(
        target_model_id="Products-Car-VF9",
        selected_model_id="Products-Car-VF9",
        visible_text="VF 9 hero specifications",
        controls=[edition],
        configuration_panel_present=True,
    )
    state = InteractionStateRecord(
        state_id="state-eco",
        interaction_step="edition:NE3NV",
        edition_id="NE3NV",
        requested_url="https://example.test/vf9",
        model_id="Products-Car-VF9",
        model_name="VF 9",
        option_group="edition",
        option_label="Eco",
        source_control_id="dom-1",
        captured_at="2026-06-20T00:00:00+00:00",
        after_snapshot_ref="snapshot-after-eco",
        settle_outcome="settled",
    )
    result = InteractionCaptureResult(
        profile=InteractionProfile(
            requested_url="https://example.test/vf9",
            page_type="vehicle_configurator",
            interaction_required=True,
            model_id="Products-Car-VF9",
        ),
        controls=[edition],
        states=[state],
        readiness=readiness,
        section_visits=[
            SectionVisit(section_id=section, reached=True)
            for section in (
                "phien-ban",
                "ngoai-that",
                "noi-that",
                "cong-nghe",
                "dac-quyen",
                "pin-sac",
            )
        ],
    )

    finalized = finalize_traversal(result, expected_model="VF 9")

    assert readiness.ready is True
    assert stable_control_identity(edition) == "edition:data-variant-id:NE3NV"
    assert finalized.traversal_complete is True
    assert finalized.transitions[0].edition_id == "NE3NV"
    assert finalized.transitions[0].evidence_refs == ["snapshot-after-eco"]
