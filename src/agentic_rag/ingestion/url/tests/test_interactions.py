from __future__ import annotations

import json
from pathlib import Path

from agentic_rag.ingestion.url.interactions import (
    InteractionCaptureResult,
    InteractionOptions,
    build_interaction_chunks,
    detect_interaction_profile,
    extract_interaction_states_from_html,
    load_url_interactions_with_artifacts,
    persist_interaction_artifacts,
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
    assert metadata["url_query_params"]["modelId"] == "Products-Car-VF9"
    assert metadata["interaction_required"] is True
    assert metadata["interaction_state"]["option_label"] == "Eco"
    assert metadata["variant_options"] == {"trim": "Eco"}
    assert metadata["heading"] == "interaction_states"
    assert metadata["breadcrumb"] == ["interaction_states"]
    assert metadata["document_type"] == "booking_flow"
    assert metadata["entities"] == ["VF 9"]
    assert metadata["token_count"] > 0
    assert metadata["chunk_index"] == 1
    assert metadata["product_model"] == "VF 9"
    assert metadata["product_price"] == "1.499.000.000 VND"
    assert metadata["attribute_group"] == "pricing_specs"


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
