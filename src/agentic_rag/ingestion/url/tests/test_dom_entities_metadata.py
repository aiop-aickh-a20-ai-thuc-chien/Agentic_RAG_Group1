from __future__ import annotations

from bs4 import BeautifulSoup

from agentic_rag.ingestion.url.dom import append_structure_aware_markdown, detect_semantic_blocks
from agentic_rag.ingestion.url.dom.entities import DomEntityExtractor
from agentic_rag.ingestion.url.entities import (
    extract_entities,
    extract_product_specs,
    filter_blocks_for_primary_entity,
    infer_primary_page_entity,
)
from agentic_rag.ingestion.url.extractor import extract_markdown_from_html


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


def test_detect_semantic_blocks_preserves_configurator_data_attributes() -> None:
    blocks = detect_semantic_blocks(
        """
        <section class="product-card" data-price-value="50000000" data-bs-target="#deposit">
          <h2>VF 9 Eco</h2>
          <p>Gia 1.499.000.000 VND</p>
          <p>Thong tin cau hinh xe dien VinFast VF 9 du dai de tao semantic block.</p>
        </section>
        """
    )

    product_block = next(block for block in blocks if "data-price-value" in block.attributes)

    assert product_block.attributes["data-price-value"] == "50000000"
    assert product_block.attributes["data-bs-target"] == "#deposit"


def test_append_structure_aware_markdown_adds_deduped_dom_sections() -> None:
    blocks = detect_semantic_blocks(
        """
        <article class="vehicle-card">
          <h2>VF 8</h2>
          <p>Gia 849.000.000 VND</p>
          <p>Range 480 km</p>
        </article>
        """
    )

    markdown = append_structure_aware_markdown("# VF 8\n\nOverview.", blocks, title="VF 8")

    assert "## Structured DOM Content" in markdown
    assert "### VF 8" in markdown
    assert "structure_block_type: vehicle_card" in markdown
    assert "structure_dedupe_hash:" in markdown
    assert "Gia 849.000.000 VND" in markdown


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


def test_primary_entity_filter_drops_cross_sell_model_blocks() -> None:
    blocks = detect_semantic_blocks(
        """
        <main>
          <article class="vehicle-card"><h2>VF 9</h2><p>Gia 1.499.000.000 VND</p></article>
          <article class="vehicle-card"><h2>VF 3</h2><p>Gia 299.000.000 VND</p></article>
          <article class="vehicle-card"><h2>VF 5</h2><p>Gia 529.000.000 VND</p></article>
        </main>
        """
    )
    primary = infer_primary_page_entity(
        title="Dat coc VF 9",
        url="https://shop.vinfastauto.com/vn_vi/dat-coc.html?modelId=Products-Car-VF9",
    )

    filtered = filter_blocks_for_primary_entity(blocks, primary_entity=primary)

    assert primary == "VF 9"
    assert any("VF 9" in block.text for block in filtered)
    assert all("VF 3" not in block.text and "VF 5" not in block.text for block in filtered)


def test_extract_product_specs_returns_variant_aware_nested_schema() -> None:
    specs = extract_product_specs(
        """
        VF 9 Eco gia 1.499.000.000 VND
        VF 9 Plus gia 1.699.000.000 VND
        Mau ngoai that do premium + 12.000.000 VND
        Mau ngoai that trang standard
        """,
        title="VF 9",
        url="https://shop.vinfastauto.com/vn_vi/dat-coc.html?modelId=Products-Car-VF9",
    )

    editions = specs["editions"]
    colors = specs["colors"]

    assert isinstance(editions, dict)
    assert editions["VF 9 Eco"]["price"] == "1.499.000.000 VND"
    assert editions["VF 9 Plus"]["price"] == "1.699.000.000 VND"
    assert isinstance(colors, dict)
    assert {"name": "do", "surcharge": "12.000.000 VND"} in colors["premium"]
    assert {"name": "trang"} in colors["standard"]


def test_dom_entity_extractor_finds_grid_label_value_pairs() -> None:
    soup = BeautifulSoup(
        """
        <section class="spec-grid">
          <div>Quang duong</div><div>626 km</div>
          <div>Dung luong pin</div><div>123 kWh</div>
        </section>
        """,
        "html.parser",
    )

    pairs = DomEntityExtractor(soup).extract_label_value_pairs(".spec-grid")

    assert ("Quang duong", "626 km") in [(pair.label, pair.value) for pair in pairs]
    assert ("Dung luong pin", "123 kWh") in [(pair.label, pair.value) for pair in pairs]


def test_extract_markdown_from_html_hydrates_embedded_json_product_state() -> None:
    extracted = extract_markdown_from_html(
        """
        <html>
          <head><title>VF 9</title></head>
          <body>
            <h1>VF 9</h1>
            <script id="__NEXT_DATA__" type="application/json">
            {
              "props": {
                "pageProps": {
                  "variants": [
                    {"name": "VF 9 Eco", "price": 1499000000},
                    {"name": "VF 9 Plus", "price": 1699000000}
                  ],
                  "colors": [
                    {"colorName": "Trang", "price": 0},
                    {"colorName": "Do premium", "price": 12000000}
                  ]
                }
              }
            }
            </script>
          </body>
        </html>
        """,
        title="VF 9",
        source_url="https://shop.vinfastauto.com/vn_vi/dat-coc.html?modelId=Products-Car-VF9",
    )

    assert extracted is not None
    assert "## Phien ban va gia" in extracted.markdown
    assert "| VF 9 Eco | 1.499.000.000 VND |" in extracted.markdown
    assert "| VF 9 Plus | 1.699.000.000 VND |" in extracted.markdown


def test_detect_color_option_blocks_with_attributes_and_fallbacks() -> None:
    html = """
    <html>
      <body>
        <ul class="colorItemList bike slides">
            <li class="slide-item active" data-name="Trắng Ngọc Trai" data-item="WHR1" data-pid="VF-ZFG-ESNE9LHH-WHR1">
                <img src="https://example.com/WHR1.png" alt="Màu xe VinFast Trắng Ngọc Trai">
            </li>
            <li class="slide-item" data-name="Xanh Oliu" data-item="GNV1" data-pid="VF-ZFG-ESNE9LHH-GNV1">
                <img src="https://example.com/GNV1.png" alt="Màu xe VinFast Xanh Oliu">
            </li>
            <li class="slide-item" data-item="REQ1" data-pid="VF-ZFG-ESNE9LHH-REQ1">
                <img src="https://example.com/REQ1.png">
            </li>
        </ul>
      </body>
    </html>
    """
    blocks = detect_semantic_blocks(html)
    block_types = [block.block_type for block in blocks]
    
    assert "color_option" in block_types
    
    # 1. Verify text formats
    assert any("Màu ngoại thất: Trắng Ngọc Trai (WHR1)" in block.text for block in blocks)
    assert any("Màu ngoại thất: Xanh Oliu (GNV1)" in block.text for block in blocks)
    assert any("Màu ngoại thất: REQ1 (https://example.com/REQ1.png)" in block.text for block in blocks)

    # 2. Verify append_structure_aware_markdown
    markdown = append_structure_aware_markdown("# VF 8\n\nOverview.", blocks, title="VF 8")
    assert "## Structured DOM Content" in markdown
    assert "Màu ngoại thất: Trắng Ngọc Trai (WHR1)" in markdown
    assert "Màu ngoại thất: REQ1 (https://example.com/REQ1.png)" in markdown

    # 3. Verify product specs extraction from the augmented markdown text
    specs = extract_product_specs(markdown, title="VF 8")
    colors = specs.get("colors", {})
    assert "standard" in colors
    color_names = [c["name"] for c in colors["standard"]]
    assert "Trắng Ngọc Trai (WHR1)" in color_names
    assert "Xanh Oliu (GNV1)" in color_names
    assert "REQ1 (https://example.com/REQ1.png)" in color_names
