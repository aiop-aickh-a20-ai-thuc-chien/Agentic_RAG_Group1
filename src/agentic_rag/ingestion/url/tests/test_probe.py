from types import SimpleNamespace

from agentic_rag.ingestion.url.crawler import (
    _best_html_attr,
    _crawl4ai_wait_for_selector,
    _merged_js_execution_result,
    _react_spa_js_code,
)
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


def test_crawl4ai_wait_selector_only_targets_configurator_urls() -> None:
    assert "window.carDeposit" in (
        _crawl4ai_wait_for_selector(
            "https://shop.vinfastauto.com/vn_vi/dat-coc-o-to-dien-vinfast.html?modelId=Products-Car-VF9"
        )
        or ""
    )
    assert "document.querySelector" in (
        _crawl4ai_wait_for_selector("https://shop.vinfastauto.com/vn_vi/dat-coc-xe-vf9.html") or ""
    )


def test_react_spa_js_code_scrolls_and_expands_interactive_content() -> None:
    script = "\n".join(_react_spa_js_code())

    assert "scrollTo" in script
    assert "aria-expanded=false" in script
    assert "[role=tab]" in script
    assert "resource_errors" in script
    assert "carDeposit" in script


def test_merged_js_execution_result_combines_crawl4ai_list_results() -> None:
    merged = _merged_js_execution_result(
        [
            None,
            {"resource_errors": [{"url": "https://example.edu/app.js"}]},
            {"initialization": {"react": True, "car_deposit": False}},
        ]
    )

    assert isinstance(merged, dict)
    assert merged["resource_errors"] == [{"url": "https://example.edu/app.js"}]
    assert merged["initialization"] == {"react": True, "car_deposit": False}


def test_best_html_attr_prefers_raw_html_when_cleaned_html_is_title_only() -> None:
    result = SimpleNamespace(
        cleaned_html="<html><head><title>VF9</title></head></html>",
        fit_html="",
        html=(
            "<html><body><main><h1>VF 9</h1>"
            "<p>Gia ban tu 1.499.000.000 VND.</p></main></body></html>"
        ),
    )

    assert _best_html_attr(result).startswith("<html><body>")


def test_vinfast_configurator_state_to_markdown_preserves_variant_and_color_prices() -> None:
    markdown = vinfast_configurator_state_to_markdown(
        {
            "modelId": "Products-Car-VF9",
            "pageUrl": "https://shop.vinfastauto.com/vn_vi/dat-coc-o-to-dien-vinfast.html?modelId=Products-Car-VF9",
            "notes": [
                "Quang duong di chuyen duoc tinh toan dua tren ket qua kiem dinh NEDC.",
                "Quang duong di chuyen duoc tinh toan dua tren ket qua kiem dinh NEDC.",
            ],
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
    assert "### VF 9 Plus tuy chon 7 cho" in markdown
    assert "window.carDeposit.products.Products-Car-VF9.NE3MV" in markdown
    assert "VF 9 Plus tuy chon 7 cho" in markdown
    assert "1.699.000.000" in markdown
    assert "1.711.000.000" in markdown
    assert "1.699.000.000 VND + 12.000.000 VND = 1.711.000.000 VND" in markdown
    assert "do not reuse a price from another variant" in markdown
    assert "12.000.000" in markdown
    assert markdown.count("Quang duong di chuyen") == 1
    assert "VinFast configurator notes" in markdown
    assert "VF 9 Eco" in markdown
    assert "1.499.000.000" in markdown


def test_vinfast_configurator_state_to_markdown_prefixes_model_when_label_is_short() -> None:
    markdown = vinfast_configurator_state_to_markdown(
        {
            "modelId": "Products-Car-VF9",
            "editions": [
                {
                    "editionCode": "NE3NV",
                    "label": "Plus tuy chon ghe co truong",
                    "basePriceFormatted": "1.731.000.000 VND",
                    "basePriceValue": 1731000000,
                    "colors": [
                        {
                            "colorLabel": "Ivy Green",
                            "priceFormatted": "1.743.000.000 VND",
                            "priceValue": 1743000000,
                            "priceDelta": 12000000,
                        }
                    ],
                }
            ],
        }
    )

    assert markdown is not None
    assert "### VF 9 Plus tuy chon ghe co truong" in markdown
    assert ("VF 9 Plus tuy chon ghe co truong + Ivy Green: final price / gia cuoi cung") in markdown
