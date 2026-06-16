from __future__ import annotations

from agentic_rag.ingestion.url.dom import detect_semantic_blocks
from agentic_rag.ingestion.url.entities import extract_entities, extract_product_specs


def test_detect_semantic_blocks_finds_vehicle_cards_and_tables() -> None:
    blocks = detect_semantic_blocks(
        """
        <html>
          <body>
            <nav>Menu</nav>
            <main>
              <article class="vehicle-card">
                <h2>VF 8</h2>
                <p>Gia 849.000.000 VND</p>
                <p>Range 480 km</p>
              </article>
              <table>
                <tr><th>Model</th><th>Price</th></tr>
                <tr><td>VF 7</td><td>799.000.000 VND</td></tr>
              </table>
            </main>
          </body>
        </html>
        """
    )

    block_types = [block.block_type for block in blocks]

    assert "vehicle_card" in block_types
    assert "comparison_table" in block_types
    assert all("Menu" not in block.text for block in blocks)


def test_extract_entities_returns_structured_vehicle_data() -> None:
    blocks = detect_semantic_blocks(
        """
        <article class="vehicle-card">
          <h2>VF 8</h2>
          <p>Gia 849.000.000 VND</p>
          <p>Range 480 km</p>
          <p>5 seats</p>
          <p>Battery capacity 87.7 kWh</p>
          <p>Fast charging 31 minutes</p>
        </article>
        """
    )

    entities = extract_entities(blocks)

    assert len(entities) == 1
    entity = entities[0]
    assert entity.entity_type == "vehicle"
    assert entity.entity_name == "VF 8"
    assert entity.structured_data["price"] == "849.000.000 VND"
    assert entity.structured_data["driving_range"] == "480 km"
    assert entity.structured_data["seats"] == "5 seats"
    assert entity.structured_data["battery_capacity"] == "87.7 kWh"
    assert entity.structured_data["charging_time"] == "31 minutes"
    assert "VF 8" in entity.retrieval_text


def test_extract_product_specs_finds_vehicle_specs_from_text_and_url() -> None:
    specs = extract_product_specs(
        """
        Gia niem yet 1.019.000.000 VND.
        Quang duong di chuyen 471 km.
        Dung luong pin 87,7 kWh.
        Thoi gian sac nhanh 31 phut.
        Cong suat toi da 300 kW.
        Mo men xoan cuc dai 500 Nm.
        Toc do toi da 200 km/h.
        Bao hanh 10 nam.
        """,
        title="VF 8 | VinFast",
        url="https://vinfastauto.com/vn_vi/vf-8",
    )

    assert specs["model_name"] == "VF 8"
    assert specs["price"] == "1.019.000.000 VND"
    assert specs["driving_range"] == "471 km"
    assert specs["battery_capacity"] == "87,7 kWh"
    assert specs["charging_time"] == "31 phut"
    assert specs["power"] == "300 kW"
    assert specs["torque"] == "500 Nm"
    assert specs["max_speed"] == "200 km/h"
    assert specs["warranty"] == "10 nam"
