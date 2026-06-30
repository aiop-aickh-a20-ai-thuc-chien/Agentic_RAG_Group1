# Local Ground-Truth Verification Report

This report was generated locally without sending content to an LLM.

## Summary

- Text similarity ratio: `1.0`
- Ground truth: 1337 words, 218 lines
- Actual output: 1337 words, 218 lines
- Structured key-fact coverage: 178/203 (`0.8768`)

## Missing structured ground-truth facts

- `page.title`: Xe điện VinFast VF 9 - Giá bán và chương trình ưu đãi | VinFast
- `vehicle.key_specs.range_note`: Tiêu chuẩn WLTP, phiên bản Eco pin CATL
- `pricing_notes[0]`: Giá xe đã bao gồm VAT.
- `pricing_notes[1]`: Giá xe chưa bao gồm tùy chọn ghế cơ trưởng.
- `rolling_cost_popup.purpose`: Hiển thị chi phí lăn bánh (on-road cost breakdown)
- `configured_prices.note`: Giá xe = Giá niêm yết phiên bản + Phụ thu màu (nếu có). Đã bao gồm VAT. Chưa bao gồm tùy chọn ghế cơ trưởng.
- `configured_prices.VF9_Eco.combinations[0].color_tier`: standard
- `configured_prices.VF9_Eco.combinations[1].color_tier`: standard
- `configured_prices.VF9_Eco.combinations[2].color_tier`: standard
- `configured_prices.VF9_Eco.combinations[3].color_tier`: standard
- `configured_prices.VF9_Eco.combinations[4].color_tier`: standard
- `configured_prices.VF9_Eco.combinations[5].color_tier`: premium
- `configured_prices.VF9_Eco.combinations[6].color_tier`: premium
- `configured_prices.VF9_Plus.combinations[0].color_tier`: standard
- `configured_prices.VF9_Plus.combinations[1].color_tier`: standard
- `configured_prices.VF9_Plus.combinations[2].color_tier`: standard
- `configured_prices.VF9_Plus.combinations[3].color_tier`: standard
- `configured_prices.VF9_Plus.combinations[4].color_tier`: standard
- `configured_prices.VF9_Plus.combinations[5].color_tier`: premium
- `configured_prices.VF9_Plus.combinations[6].color_tier`: premium
- `exterior_colors.note`: Per-color prices removed – the data-price-value attributes in the HTML reflect internal cart totals for a specific edition+color combination, not meaningful standalone color prices. Use variant base prices and surcharge only.
- `exterior_colors.color_categories[0].category`: Màu cơ bản - Theo xe
- `exterior_colors.color_categories[1].surcharge_label`: + 12.000.000 VNĐ
- `interior_colors.note`: Available interior colors depend on chosen exterior color
- `sources.html_snippet`: Provided document (shop.vinfastauto.com VF9 color selector)

## Covered structured ground-truth facts

- `page.url_deposit_page`: https://shop.vinfastauto.com/vn_vi/dat-coc-xe-vf9.html
- `page.url_model_selector`: https://shop.vinfastauto.com/vn_vi/dat-coc-o-to-dien-vinfast.html?modelId=Products-Car-VF9
- `page.model_id`: Products-Car-VF9
- `vehicle.name`: VinFast VF 9
- `vehicle.type`: eSUV – SUV điện 7 chỗ hạng sang
- `vehicle.tagline`: Sự Lựa Chọn Của Người Thành Đạt, Tiên Phong
- `vehicle.key_specs.range_wltp_km`: 626
- `vehicle.key_specs.power_hp`: 402
- `vehicle.key_specs.torque_nm`: 620
- `vehicle.key_specs.warranty`: 200.000 km hoặc 10 năm
- `variants[0].edition_id`: NE3NV
- `variants[0].name`: VF 9 Eco
- `variants[0].base_price_vnd`: 1499000000
- `variants[0].base_price_formatted`: 1.499.000.000 VNĐ
- `variants[1].edition_id`: NE3MV
- `variants[1].name`: VF 9 Plus
- `variants[1].base_price_vnd`: 1699000000
- `variants[1].base_price_formatted`: 1.699.000.000 VNĐ
- `deposit.amount_vnd`: 50000000
- `deposit.amount_formatted`: 50.000.000 VNĐ
- ... and 158 more

## Generated artifacts

- JSON summary: `guide_2/demo/verify_ingestion/offline_self_check/comparison_summary.json`
- Unified diff: `guide_2/demo/verify_ingestion/offline_self_check/ground_truth_diff.patch`

Use the diff for line-level review, and use the structured-fact section as a fast smoke test for whether important ground-truth values appeared in the ingestion output.
