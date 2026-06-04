from agentic_rag.ingestion.url.probe import (
    should_probe_interactive_state,
    vinfast_configurator_state_to_markdown,
)


def test_should_probe_interactive_state_only_matches_vinfast_configurator() -> None:
    assert should_probe_interactive_state(
        "https://shop.vinfastauto.com/vn_vi/dat-coc-o-to-dien-vinfast.html?modelId=Products-Car-VF9"
    )
    assert not should_probe_interactive_state("https://shop.vinfastauto.com/vn_vi/Parts")
    assert not should_probe_interactive_state(
        "https://vinfastauto.com/vn_vi/dat-coc-o-to-dien-vinfast.html?modelId=Products-Car-VF9"
    )


def test_vinfast_configurator_state_to_markdown_preserves_variant_and_color_prices() -> None:
    markdown = vinfast_configurator_state_to_markdown(
        {
            "modelId": "Products-Car-VF9",
            "pageUrl": "https://shop.vinfastauto.com/vn_vi/dat-coc-o-to-dien-vinfast.html?modelId=Products-Car-VF9",
            "editions": [
                {
                    "editionCode": "NE3MV",
                    "label": "VF 9 Plus tuy chon 7 cho",
                    "basePriceFormatted": "1.699.000.000 VND",
                    "basePriceValue": 1699000000,
                    "colors": [
                        {
                            "colorCode": "advanced",
                            "colorLabel": "Mau nang cao",
                            "priceFormatted": "1.711.000.000 VND",
                            "priceValue": 1711000000,
                            "priceDelta": 12000000,
                        }
                    ],
                },
                {
                    "editionCode": "NE3LV",
                    "label": "VF 9 Eco",
                    "basePriceFormatted": "",
                    "basePriceValue": 1499000000,
                    "colors": [],
                },
            ],
        }
    )

    assert markdown is not None
    assert "Probed Interactive State" in markdown
    assert "VF 9 Plus tuy chon 7 cho" in markdown
    assert "1.699.000.000" in markdown
    assert "1.711.000.000" in markdown
    assert "12.000.000" in markdown
    assert "VF 9 Eco" in markdown
    assert "1.499.000.000" in markdown
