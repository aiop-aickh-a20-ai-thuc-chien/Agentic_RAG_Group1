from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from agentic_rag.ingestion.url.interactions import (
    InteractionCaptureResult,
    InteractionControl,
    InteractionOptions,
    InteractionPanelDiff,
    InteractionPanelSnapshot,
    InteractionProfile,
    InteractionStateRecord,
    build_interaction_chunks,
    build_promoted_interaction_chunks,
    detect_interaction_profile,
    extract_interaction_states_from_html,
    extract_specifications_from_text,
    load_url_interactions_with_artifacts,
    persist_interaction_artifacts,
)
from agentic_rag.ingestion.url.interactions.playwright import (
    _CAPTURE_PANELS_JS,
    _DISCOVER_CONTROLS_JS,
    _build_panel_diff,
    _prioritize_states_by_gain,
    _state_from_panel_diff,
)

VINFAST_BOOKING_URL = (
    "https://shop.vinfastauto.com/vn_vi/dat-coc-o-to-dien-vinfast.html?modelId=Products-Car-VF9"
)


def test_detect_interaction_profile_for_booking_url_preserves_model_id() -> None:
    profile = detect_interaction_profile(VINFAST_BOOKING_URL)

    assert profile.interaction_required is True
    assert profile.page_type == "booking_flow"
    assert profile.model_id == "Products-Car-VF9"
    assert profile.url_query_params["modelId"] == "Products-Car-VF9"


def test_extract_interaction_states_from_html_captures_color_price_and_image() -> None:
    result = extract_interaction_states_from_html(
        """
        <html>
          <body>
            <main>
              <h1>VinFast VF 9</h1>
              <p>Gia tam tinh 1.499.000.000 VND</p>
              <img src="/default-vf9.png" alt="VF 9 default" />
              <button
                class="color-swatch"
                data-option-group="color"
                data-option-label="Crimson Red"
                data-price="1.510.000.000 VND"
                data-image="/vf9-red.png"
                data-model-name="VF 9"
              >
                Crimson Red
              </button>
              <button
                class="color-swatch"
                data-option-group="color"
                data-option-label="Ocean Blue"
                data-image="/vf9-blue.png"
              >
                Ocean Blue
              </button>
              <button>Dat coc ngay</button>
            </main>
          </body>
        </html>
        """,
        requested_url=VINFAST_BOOKING_URL,
        final_url="https://shop.vinfastauto.com/vn_vi/dat-coc-o-to-dien-vinfast.html",
        captured_at="2026-06-15T00:00:00+00:00",
    )

    labels = {state.option_label for state in result.states}
    assert labels == {"Crimson Red", "Ocean Blue"}
    assert len(result.skipped_controls) == 1
    red_state = next(state for state in result.states if state.option_label == "Crimson Red")
    blue_state = next(state for state in result.states if state.option_label == "Ocean Blue")

    assert red_state.option_group == "color"
    assert red_state.model_id == "Products-Car-VF9"
    assert red_state.model_name == "VF 9"
    assert red_state.price == "1.510.000.000 VND"
    assert red_state.currency == "VND"
    assert red_state.image_url == "https://shop.vinfastauto.com/vf9-red.png"
    assert red_state.evidence_source == "dom"
    assert blue_state.price == "1.499.000.000 VND"
    assert blue_state.image_url == "https://shop.vinfastauto.com/vf9-blue.png"


def test_extract_interaction_states_marks_disabled_options() -> None:
    result = extract_interaction_states_from_html(
        """
        <html>
          <body>
            <h1>VF 9</h1>
            <button
              class="variant-card"
              data-option-group="trim"
              data-option-label="Plus"
              data-price="1.699.000.000 VND"
              disabled
            >Plus</button>
          </body>
        </html>
        """,
        requested_url=VINFAST_BOOKING_URL,
    )

    assert len(result.states) == 1
    assert result.states[0].availability == "disabled"
    assert result.states[0].variant_options == {"trim": "Plus"}


def test_extract_interaction_states_uses_json_state_payloads() -> None:
    result = extract_interaction_states_from_html(
        """
        <html>
          <body>
            <h1>VF 9</h1>
            <script type="application/json">
              {
                "variants": [
                  {
                    "modelId": "Products-Car-VF9",
                    "modelName": "VF 9",
                    "colorName": "Jet Black",
                    "optionGroup": "color",
                    "displayPrice": "1.520.000.000 VND",
                    "imageUrl": "/vf9-black.png",
                    "availability": "available"
                  }
                ]
              }
            </script>
          </body>
        </html>
        """,
        requested_url=VINFAST_BOOKING_URL,
        final_url="https://shop.vinfastauto.com/vn_vi/dat-coc-o-to-dien-vinfast.html",
    )

    assert len(result.states) == 1
    state = result.states[0]
    assert state.evidence_source == "network"
    assert state.price_source == "json_state"
    assert state.option_group == "color"
    assert state.option_label == "Jet Black"
    assert state.price == "1.520.000.000 VND"
    assert state.image_url == "https://shop.vinfastauto.com/vf9-black.png"


def test_extract_interaction_states_promotes_network_model_specs() -> None:
    result = extract_interaction_states_from_html(
        "<html><body><h1>VF 9</h1></body></html>",
        requested_url=VINFAST_BOOKING_URL,
        final_url="https://shop.vinfastauto.com/vn_vi/dat-coc-o-to-dien-vinfast.html",
        network_payloads=[
            {
                "product": {
                    "modelId": "Products-Car-VF9",
                    "modelName": "VF 9",
                    "specifications": [
                        {"name": "Quang duong di chuyen", "value": "626 km"},
                        {"name": "Dung luong pin", "value": "123 kWh"},
                        {"name": "So cho ngoi", "value": "7"},
                    ],
                }
            }
        ],
        captured_at="2026-06-15T00:00:00+00:00",
    )

    assert len(result.states) == 1
    state = result.states[0]
    assert state.evidence_source == "network"
    assert state.option_group == "specifications"
    assert state.model_id == "Products-Car-VF9"
    assert state.specifications == {
        "battery_capacity": "123 kWh",
        "driving_range": "626 km",
        "seats": "7",
    }
    assert state.changed_fields == ["specifications"]

    debug_chunks = build_interaction_chunks(
        result,
        fetched_at="2026-06-15T00:00:00+00:00",
    )
    promoted_chunks = build_promoted_interaction_chunks(
        result,
        fetched_at="2026-06-15T00:00:00+00:00",
    )

    assert debug_chunks[0].metadata["product_specs"]["driving_range"] == "626 km"
    assert debug_chunks[0].metadata["attribute_group"] == "pricing_specs"
    assert len(promoted_chunks) == 1
    promoted = promoted_chunks[0]
    assert promoted.metadata["retrieval_visibility"] == "normal"
    assert promoted.metadata["section_origin"] == "dynamic_state_payload"
    assert promoted.metadata["product_specs"]["battery_capacity"] == "123 kWh"
    assert "API-backed specifications" in promoted.text
    assert "driving range 626 km" in promoted.text


def test_extract_interaction_states_promotes_model_scoped_deposit_payload() -> None:
    result = extract_interaction_states_from_html(
        "<html><body><h1>VF 9</h1></body></html>",
        requested_url=VINFAST_BOOKING_URL,
        final_url=VINFAST_BOOKING_URL,
        network_payloads=[
            {
                "action": "CarsDeposit-BankInfo",
                "querystring": {"modelID": "Products-Car-VF9"},
                "depositAmount": {
                    "depositAmount": "50.000.000",
                    "depositAmountValue": 50000000,
                },
            }
        ],
        captured_at="2026-06-15T00:00:00+00:00",
    )

    assert len(result.states) == 1
    state = result.states[0]
    assert state.evidence_source == "network"
    assert state.model_id == "Products-Car-VF9"
    assert state.model_name == "VF 9"
    assert state.option_group == "deposit"
    assert state.price == "50.000.000 VND"
    assert state.specifications["deposit_amount"] == "50.000.000 VND"

    promoted_chunks = build_promoted_interaction_chunks(
        result,
        fetched_at="2026-06-15T00:00:00+00:00",
    )

    assert len(promoted_chunks) == 1
    promoted = promoted_chunks[0]
    assert promoted.metadata["selected_model_id"] == "Products-Car-VF9"
    assert promoted.metadata["selected_product_model"] == "VF 9"
    assert promoted.metadata["product_model"] == "VF 9"
    assert promoted.metadata["deposit_amount"] == "50.000.000 VND"
    assert promoted.metadata["retrieval_visibility"] == "normal"
    assert promoted.text == "VF 9 deposit amount is 50.000.000 VND from network payload."


def test_extract_specifications_from_right_panel_text() -> None:
    specs = extract_specifications_from_text(
        """
        Thong so ky thuat
        Quang duong di chuyen: 626 km
        Dung luong pin: 123 kWh
        So cho ngoi
        7
        """
    )

    assert specs == {
        "battery_capacity": "123 kWh",
        "driving_range": "626 km",
        "seats": "7",
    }


def test_build_interaction_chunks_adds_variant_metadata() -> None:
    result = extract_interaction_states_from_html(
        """
        <html>
          <body>
            <h1>VF 9</h1>
            <button
              class="variant-card"
              data-option-group="trim"
              data-option-label="Eco"
              data-price="1.499.000.000 VND"
            >Eco</button>
          </body>
        </html>
        """,
        requested_url=VINFAST_BOOKING_URL,
        captured_at="2026-06-15T00:00:00+00:00",
        options=InteractionOptions(max_states=5),
    )

    chunks = build_interaction_chunks(result, fetched_at="2026-06-15T00:00:00+00:00")

    assert len(chunks) == 1
    assert chunks[0].text == "VF 9 - trim: Eco - price: 1.499.000.000 VND - availability: available"
    metadata = chunks[0].metadata
    assert metadata["requested_url"] == VINFAST_BOOKING_URL
    assert metadata["source"] == VINFAST_BOOKING_URL
    assert metadata["source_type"] == "official"
    assert metadata["url_query_params"]["modelId"] == "Products-Car-VF9"
    assert metadata["interaction_required"] is True
    assert metadata["interaction_state"]["option_label"] == "Eco"
    assert metadata["variant_options"] == {"trim": "Eco"}
    assert metadata["heading"] == "interaction_states"
    assert metadata["breadcrumb"] == ["interaction_states"]
    assert metadata["chunk_type"] == "interaction_debug"
    assert metadata["section_kind"] == "dynamic"
    assert metadata["section_origin"] == "dynamic_interaction"
    assert metadata["retrieval_visibility"] == "debug_only"
    assert metadata["metadata_prefilter_exclude"] is True
    assert metadata["trusted_for_retrieval"] is False
    assert metadata["semantic_application_status"] == "unmapped"
    assert metadata["document_type"] == "booking_flow"
    assert metadata["entities"] == ["VF 9"]
    assert metadata["token_count"] > 0
    assert metadata["chunk_index"] == 1
    assert metadata["product_model"] == "VF 9"
    assert metadata["product_price"] == "1.499.000.000 VND"
    assert metadata["attribute_group"] == "pricing_specs"


def test_build_interaction_chunks_marks_network_payload_as_debug_only() -> None:
    result = extract_interaction_states_from_html(
        """
        <html>
          <body>
            <h1>VF 9</h1>
            <script type="application/json">
              {
                "variants": [
                  {
                    "modelName": "VF 9",
                    "optionGroup": "color",
                    "colorName": "Jet Black",
                    "displayPrice": "1.520.000.000 VND"
                  }
                ]
              }
            </script>
          </body>
        </html>
        """,
        requested_url=VINFAST_BOOKING_URL,
    )

    chunks = build_interaction_chunks(result, fetched_at="2026-06-15T00:00:00+00:00")

    assert chunks[0].metadata["evidence_source"] == "network"
    assert chunks[0].metadata["section_origin"] == "dynamic_state_payload"
    assert chunks[0].metadata["retrieval_visibility"] == "debug_only"
    assert chunks[0].metadata["metadata_prefilter_exclude"] is True
    assert chunks[0].metadata["trusted_for_retrieval"] is False


def test_panel_trim_state_creates_debug_and_promoted_chunks() -> None:
    state = _dynamic_state(
        option_group="trim",
        option_label="Plus",
        price="1.699.000.000 VND",
        image_url="https://shop.vinfastauto.com/vf9-plus.png",
        changed_panels=["center_visual", "right_panel"],
        changed_fields=["price", "image", "visible_text"],
    )
    result = _capture_result(states=[state])

    debug_chunks = build_interaction_chunks(
        result,
        fetched_at="2026-06-15T00:00:00+00:00",
    )
    promoted_chunks = build_promoted_interaction_chunks(
        result,
        fetched_at="2026-06-15T00:00:00+00:00",
    )

    assert len(debug_chunks) == 1
    assert debug_chunks[0].metadata["chunk_type"] == "interaction_debug"
    assert debug_chunks[0].metadata["retrieval_visibility"] == "debug_only"
    assert debug_chunks[0].metadata["metadata_prefilter_exclude"] is True
    assert debug_chunks[0].metadata["trusted_for_retrieval"] is False
    assert debug_chunks[0].metadata["panel_role"] == "left_panel"
    assert debug_chunks[0].metadata["changed_panels"] == ["center_visual", "right_panel"]

    assert len(promoted_chunks) == 1
    promoted = promoted_chunks[0]
    assert promoted.metadata["chunk_type"] == "dynamic_state"
    assert promoted.metadata["retrieval_visibility"] == "normal"
    assert promoted.metadata["metadata_prefilter_exclude"] is False
    assert promoted.metadata["trusted_for_retrieval"] is True
    assert promoted.metadata["semantic_application_status"] == "applied_to_semantic_chunk"
    assert "selected trim Plus" in promoted.text
    assert "right-panel visible price to 1.699.000.000 VND" in promoted.text
    assert "center product image to https://shop.vinfastauto.com/vf9-plus.png" in promoted.text


def test_right_panel_financing_selector_promotes_payment_summary() -> None:
    state = _dynamic_state(
        option_group="financing",
        option_label="Tra gop",
        price="300.000.000 VND",
        image_url=None,
        changed_panels=["right_panel"],
        changed_fields=["price", "visible_text"],
        source_control_id="finance-tra-gop",
    )
    result = _capture_result(states=[state])

    promoted_chunks = build_promoted_interaction_chunks(result)

    assert len(promoted_chunks) == 1
    assert promoted_chunks[0].metadata["changed_panels"] == ["right_panel"]
    assert promoted_chunks[0].metadata["product_price"] == "300.000.000 VND"
    assert "selected financing Tra gop" in promoted_chunks[0].text


def test_carousel_control_remains_debug_only_without_promoted_fact() -> None:
    state = _dynamic_state(
        option_group="carousel",
        option_label="Next",
        price=None,
        image_url="https://shop.vinfastauto.com/vf9-gallery-2.png",
        changed_panels=["center_visual"],
        changed_fields=["image"],
        source_control_id="carousel-next",
    )
    result = _capture_result(states=[state])

    assert len(build_interaction_chunks(result)) == 1
    assert build_promoted_interaction_chunks(result) == []


def test_hidden_network_price_stays_debug_without_visible_panel_evidence() -> None:
    state = _dynamic_state(
        option_group="color",
        option_label="Hidden payload color",
        price="1.900.000.000 VND",
        image_url=None,
        changed_panels=[],
        changed_fields=[],
        evidence_source="network",
    )
    result = _capture_result(states=[state])

    debug_chunks = build_interaction_chunks(result)
    promoted_chunks = build_promoted_interaction_chunks(result)

    assert debug_chunks[0].metadata["retrieval_visibility"] == "debug_only"
    assert promoted_chunks == []


def test_visible_text_model_change_promotes_dynamic_state() -> None:
    state = _dynamic_state(
        option_group="model",
        option_label="VF 3",
        price=None,
        image_url=None,
        changed_panels=["right_panel"],
        changed_fields=["visible_text"],
        source_control_id="model-vf3",
        gain_score=4,
    ).model_copy(
        update={
            "dom_evidence": {
                "control_id": "model-vf3",
                "after_snapshot_text": (
                    "VF 3 modelId Products-Car-VF3 Cong suat toi da 30 kW "
                    "Dung luong pin kha dung 18,64 kWh Quang duong 215 km"
                ),
            }
        }
    )
    result = _capture_result(states=[state])

    promoted_chunks = build_promoted_interaction_chunks(result)

    assert len(promoted_chunks) == 1
    assert promoted_chunks[0].metadata["chunk_type"] == "dynamic_state"
    assert promoted_chunks[0].metadata["retrieval_visibility"] == "normal"
    assert "selected model VF 3" in promoted_chunks[0].text
    assert "Products-Car-VF3" in promoted_chunks[0].text


def test_panel_diff_stores_dom_api_entity_information_gain() -> None:
    control = InteractionControl(
        control_id="spec-button",
        label="Thong so ky thuat",
        group="specifications",
        selector="[data-test='spec']",
        panel_role="right_panel",
        panel_id="right_panel",
    )
    before = [
        InteractionPanelSnapshot(
            snapshot_id="before-specs",
            panel_role="right_panel",
            panel_id="right_panel",
            interaction_step="before:spec-button",
            captured_at="2026-06-15T00:00:00+00:00",
            source_control_id="spec-button",
            text="VF 9",
            text_hash="before",
            node_signatures=["h1#.title:VF 9"],
        )
    ]
    after = [
        InteractionPanelSnapshot(
            snapshot_id="after-specs",
            panel_role="right_panel",
            panel_id="right_panel",
            interaction_step="after:spec-button",
            captured_at="2026-06-15T00:00:01+00:00",
            source_control_id="spec-button",
            text=(
                "VF 9\n"
                "Thong so ky thuat\n"
                "Quang duong di chuyen: 626 km\n"
                "So cho ngoi: 7\n"
                "Gia: 1.499.000.000 VND"
            ),
            text_hash="after",
            price_values=["1.499.000.000 VND"],
            specifications={"driving_range": "626 km", "seats": "7"},
            table_count=1,
            node_signatures=[
                "h1#.title:VF 9",
                "table#.specs:Thong so ky thuat Quang duong",
                "td#.range:626 km",
            ],
        )
    ]

    diff = _build_panel_diff(
        control=control,
        before_snapshots=before,
        after_snapshots=after,
        before_network_payloads=[
            {
                "__endpoint": "https://shop.vinfastauto.com/api/bootstrap",
                "modelId": "Products-Car-VF9",
            }
        ],
        new_network_payloads=[
            {
                "__endpoint": "https://shop.vinfastauto.com/api/specifications",
                "modelId": "Products-Car-VF9",
                "variantName": "VF 9 Plus",
                "specifications": {"range": "626 km", "seats": 7},
            }
        ],
    )

    assert diff.gain_score > 0
    assert diff.dom_gain > 0
    assert diff.api_gain > 0
    assert diff.entity_gain > 0
    dom_gain = cast(dict[str, object], diff.information_gain["dom"])
    api_gain = cast(dict[str, object], diff.information_gain["api"])
    assert dom_gain["new_tables"] == 1
    assert dom_gain["new_prices"] == ["1.499.000.000 VND"]
    assert dom_gain["new_specs"] == {
        "driving_range": "626 km",
        "seats": "7",
    }
    assert api_gain["new_endpoints"] == ["https://shop.vinfastauto.com/api/specifications"]
    assert "specifications.range" in cast(list[str], api_gain["new_json_fields"])
    assert "VF 9 Plus" in cast(list[str], api_gain["new_entities"])
    assert "specifications" in diff.changed_fields
    assert "tables" in diff.changed_fields
    assert "nodes" in diff.changed_fields


def test_bootstrap_modal_trigger_and_body_are_information_gain_sources() -> None:
    assert 'a[data-bs-toggle="modal"]' in _DISCOVER_CONTROLS_JS
    assert "data-bs-target" in _DISCOVER_CONTROLS_JS
    assert "data-target" in _DISCOVER_CONTROLS_JS
    assert "aria-expanded" in _DISCOVER_CONTROLS_JS
    assert ".modal-body" in _CAPTURE_PANELS_JS

    control = InteractionControl(
        control_id="rolling-cost-details",
        label="Chi tiet",
        group="details",
        selector='[data-url-ingestion-interaction-id="rolling-cost-details"]',
        panel_role="right_panel",
        panel_id="rollingUpCostPopUp",
        attributes={
            "href": "javascript:void(0);",
            "data-bs-toggle": "modal",
            "data-bs-target": "#rollingUpCostPopUp",
            "class": "tab-right-cost-more js-rollingUpCostPopUp",
        },
    )
    before = [
        InteractionPanelSnapshot(
            snapshot_id="before-modal",
            panel_role="right_panel",
            panel_id="right_panel",
            interaction_step="before:rolling-cost-details",
            captured_at="2026-06-15T00:00:00+00:00",
            source_control_id=control.control_id,
            text="Chi tiet",
            text_hash="before",
            node_signatures=["a#.tab-right-cost-more:Chi tiet"],
        )
    ]
    after = [
        InteractionPanelSnapshot(
            snapshot_id="after-modal",
            panel_role="right_panel",
            panel_id="rollingUpCostPopUp",
            interaction_step="after:rolling-cost-details",
            captured_at="2026-06-15T00:00:01+00:00",
            source_control_id=control.control_id,
            text=(
                "modal-body\n"
                "Chi phi lan banh\n"
                "Gia xe: 1.499.000.000 VND\n"
                "Quang duong di chuyen: 626 km"
            ),
            text_hash="after",
            price_values=["1.499.000.000 VND"],
            specifications={"driving_range": "626 km"},
            node_signatures=[
                "a#.tab-right-cost-more:Chi tiet",
                "div#rollingUpCostPopUp.modal-body:Chi phi lan banh",
            ],
        )
    ]
    diff = _build_panel_diff(
        control=control,
        before_snapshots=before,
        after_snapshots=after,
    )
    state = _state_from_panel_diff(
        control=control,
        profile=InteractionProfile(
            requested_url=VINFAST_BOOKING_URL,
            final_url="https://shop.vinfastauto.com/vn_vi/dat-coc-o-to-dien-vinfast.html",
            page_type="booking_flow",
            interaction_required=True,
            reasons=["booking_url"],
            url_query_params={"modelId": "Products-Car-VF9"},
            model_id="Products-Car-VF9",
        ),
        diff=diff,
        after_snapshots=after,
        requested_url=VINFAST_BOOKING_URL,
        final_url="https://shop.vinfastauto.com/vn_vi/dat-coc-o-to-dien-vinfast.html",
        captured_at="2026-06-15T00:00:02+00:00",
    )

    assert diff.gain_score > 0
    assert "price" in diff.changed_fields
    assert "specifications" in diff.changed_fields
    assert state is not None
    assert state.option_group == "details"
    assert state.panel_id == "rollingUpCostPopUp"
    assert state.price == "1.499.000.000 VND"
    assert state.specifications == {"driving_range": "626 km"}
    assert state.information_gain["gain_score"] == diff.gain_score


def test_information_gain_prioritizes_revealing_states() -> None:
    low_gain = _dynamic_state(
        option_group="color",
        option_label="White",
        price=None,
        image_url=None,
        changed_panels=["left_panel"],
        changed_fields=["visible_text"],
        source_control_id="color-white",
    )
    high_gain = _dynamic_state(
        option_group="specifications",
        option_label="Thong so",
        price=None,
        image_url=None,
        changed_panels=["right_panel"],
        changed_fields=["specifications"],
        source_control_id="specs",
        gain_score=42,
    )

    assert _prioritize_states_by_gain([low_gain, high_gain])[0].source_control_id == "specs"


def test_persist_interaction_artifacts_writes_panel_snapshots_and_diffs(
    tmp_path: Path,
) -> None:
    state = _dynamic_state(
        option_group="trim",
        option_label="Plus",
        price="1.699.000.000 VND",
        image_url="https://shop.vinfastauto.com/vf9-plus.png",
        changed_panels=["center_visual", "right_panel"],
        changed_fields=["price", "image"],
    )
    result = _capture_result(
        states=[state],
        panel_snapshots=[
            InteractionPanelSnapshot(
                snapshot_id="before-right",
                panel_role="right_panel",
                panel_id="right_panel",
                interaction_step="before:trim-plus",
                captured_at="2026-06-15T00:00:00+00:00",
                source_control_id="trim-plus",
                text="Gia 1.499.000.000 VND",
                text_hash="before",
                price_values=["1.499.000.000 VND"],
            ),
            InteractionPanelSnapshot(
                snapshot_id="after-right",
                panel_role="right_panel",
                panel_id="right_panel",
                interaction_step="after:trim-plus",
                captured_at="2026-06-15T00:00:01+00:00",
                source_control_id="trim-plus",
                text="Gia 1.699.000.000 VND",
                text_hash="after",
                price_values=["1.699.000.000 VND"],
            ),
        ],
        panel_diffs=[
            InteractionPanelDiff(
                diff_id="panel-diff-trim-plus",
                source_control_id="trim-plus",
                control_label="Plus",
                control_group="trim",
                changed_panels=["right_panel"],
                changed_fields=["price"],
                before_snapshot_refs=["before-right"],
                after_snapshot_refs=["after-right"],
                panel_changes={
                    "right_panel": {
                        "price_values_added": ["1.699.000.000 VND"],
                    }
                },
            )
        ],
    )
    chunks = [
        *build_interaction_chunks(result),
        *build_promoted_interaction_chunks(result),
    ]

    artifacts = persist_interaction_artifacts(
        data_dir=tmp_path,
        source=VINFAST_BOOKING_URL,
        run_id="panel-artifacts",
        result=result,
        chunks=chunks,
    )

    assert artifacts is not None
    assert artifacts.panel_snapshots_path is not None
    assert artifacts.panel_snapshots_path.exists()
    assert artifacts.panel_diffs_path is not None
    assert artifacts.panel_diffs_path.exists()
    manifest = json.loads(artifacts.manifest_path.read_text(encoding="utf-8"))
    assert manifest["panel_snapshot_count"] == 2
    assert manifest["panel_diff_count"] == 1


def test_persist_interaction_artifacts_writes_states_and_manifest(tmp_path: Path) -> None:
    result = extract_interaction_states_from_html(
        """
        <html>
          <body>
            <h1>VF 9</h1>
            <button
              data-option-group="color"
              data-option-label="White"
              data-price="1.500.000.000 VND"
            >White</button>
          </body>
        </html>
        """,
        requested_url=VINFAST_BOOKING_URL,
    )
    chunks = build_interaction_chunks(result)

    artifacts = persist_interaction_artifacts(
        data_dir=tmp_path,
        source=VINFAST_BOOKING_URL,
        run_id="vf9-interaction",
        result=result,
        chunks=chunks,
    )

    assert artifacts is not None
    assert artifacts.states_path.exists()
    assert artifacts.chunks_path.exists()
    assert artifacts.manifest_path.exists()
    states_payload = json.loads(artifacts.states_path.read_text(encoding="utf-8"))
    manifest = json.loads(artifacts.manifest_path.read_text(encoding="utf-8"))
    assert states_payload["states"][0]["option_label"] == "White"
    assert manifest["artifact_type"] == "url_interaction_capture"
    assert manifest["state_count"] == 1
    assert manifest["chunk_count"] == 1


def test_load_url_interactions_with_artifacts_uses_injected_capture(tmp_path: Path) -> None:
    def fake_capture(url: str, options: InteractionOptions) -> InteractionCaptureResult:
        assert url == VINFAST_BOOKING_URL
        assert options.max_states == 3
        return extract_interaction_states_from_html(
            """
            <html>
              <body>
                <h1>VF 9</h1>
                <button
                  data-option-group="color"
                  data-option-label="Silver"
                  data-price="1.501.000.000 VND"
                  data-image="/vf9-silver.png"
                >Silver</button>
              </body>
            </html>
            """,
            requested_url=url,
            options=options,
        )

    loaded = load_url_interactions_with_artifacts(
        VINFAST_BOOKING_URL,
        data_artifact_dir=tmp_path,
        run_id="high-level",
        options=InteractionOptions(max_states=3),
        capture=fake_capture,
    )

    assert len(loaded.chunks) == 1
    assert loaded.chunks[0].metadata["interaction_state"]["option_label"] == "Silver"
    assert loaded.artifacts is not None
    assert loaded.artifacts.states_path.exists()
    assert loaded.artifacts.image_snapshots_path is not None
    assert loaded.artifacts.image_snapshots_path.exists()
    snapshot_payload = json.loads(loaded.artifacts.image_snapshots_path.read_text(encoding="utf-8"))
    assert snapshot_payload["snapshots"][0]["option_label"] == "Silver"
    assert snapshot_payload["snapshots"][0]["image_url"].endswith("/vf9-silver.png")
    assert loaded.chunks[0].metadata["image_snapshot_ref"].startswith("image_snapshot_")


def _capture_result(
    *,
    states: list[InteractionStateRecord],
    panel_snapshots: list[InteractionPanelSnapshot] | None = None,
    panel_diffs: list[InteractionPanelDiff] | None = None,
) -> InteractionCaptureResult:
    return InteractionCaptureResult(
        profile=InteractionProfile(
            requested_url=VINFAST_BOOKING_URL,
            final_url="https://shop.vinfastauto.com/vn_vi/dat-coc-o-to-dien-vinfast.html",
            page_type="booking_flow",
            interaction_required=True,
            reasons=["booking_url"],
            url_query_params={"modelId": "Products-Car-VF9"},
            model_id="Products-Car-VF9",
        ),
        states=states,
        panel_snapshots=panel_snapshots or [],
        panel_diffs=panel_diffs or [],
    )


def _dynamic_state(
    *,
    option_group: str,
    option_label: str,
    price: str | None,
    image_url: str | None,
    changed_panels: list[str],
    changed_fields: list[str],
    source_control_id: str = "trim-plus",
    evidence_source: str = "dom",
    gain_score: int = 0,
) -> InteractionStateRecord:
    return InteractionStateRecord(
        state_id=f"state-{source_control_id}",
        requested_url=VINFAST_BOOKING_URL,
        final_url="https://shop.vinfastauto.com/vn_vi/dat-coc-o-to-dien-vinfast.html",
        model_id="Products-Car-VF9",
        model_name="VF 9",
        option_group=option_group,
        option_label=option_label,
        source_control_id=source_control_id,
        panel_role="left_panel",
        panel_id="left_panel",
        variant_options={option_group: option_label},
        price=price,
        currency="VND" if price else None,
        price_source="dom" if price else "not_visible",
        image_url=image_url,
        availability="available",
        evidence_source=evidence_source,
        captured_at="2026-06-15T00:00:00+00:00",
        changed_panels=changed_panels,
        changed_fields=changed_fields,
        before_snapshot_ref="before-right",
        after_snapshot_ref="after-right",
        state_diff_ref="panel-diff-trim-plus",
        gain_score=gain_score,
        information_gain={"gain_score": gain_score} if gain_score else {},
        dom_evidence={
            "control_id": source_control_id,
            "changed_panels": ",".join(changed_panels),
            "changed_fields": ",".join(changed_fields),
        }
        if evidence_source == "dom"
        else {},
        network_evidence={"price": price or ""} if evidence_source == "network" else {},
    )
