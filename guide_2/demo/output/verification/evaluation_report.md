# Local Ground-Truth Verification Report

This report was generated locally without sending content to an LLM.

## Summary

- Text similarity ratio: `0.019`
- Ground truth: 1715 words, 235 lines
- Actual output: 656 words, 125 lines
- Evidence artifacts searched: 9

## Primary URL routing signal

- Source URL path: `/vn_vi/dat-coc-o-to-dien-vinfast.html`
- Primary routing parameter: `modelId`
- Primary model ID: `Products-Car-VF9`
- Model ID present in actual markdown: `False`
- Model ID present in evidence corpus: `True`
- Model ID present in ground truth: `True`

`modelId` is treated as the page-routing variable for VinFast model-selector URLs, so changing it to VF3/VF5/VF6/VF7/etc. should change the target page being verified.
- Structured key-fact coverage: 204/243 (`0.8395`)
- Structured coverage verdict: `pass`

## Missing structured ground-truth facts

- `page.title`: Xe điện VinFast VF 9 - Giá bán và chương trình ưu đãi | VinFast
- `vehicle.type`: eSUV – SUV điện 7 chỗ hạng sang
- `vehicle.tagline`: Sự Lựa Chọn Của Người Thành Đạt, Tiên Phong
- `vehicle.key_specs.range_note`: Tiêu chuẩn WLTP, phiên bản Eco pin CATL
- `vehicle.key_specs.warranty`: 200.000 km hoặc 10 năm
- `rolling_cost_popup.purpose`: Hiển thị chi phí lăn bánh (on-road cost breakdown)
- `configured_prices.note`: Giá xe = Giá niêm yết phiên bản + Phụ thu màu (nếu có). Đã bao gồm VAT.
- `configured_prices.VF9_Eco.combinations[0].color_tier`: standard
- `configured_prices.VF9_Eco.combinations[1].color_tier`: standard
- `configured_prices.VF9_Eco.combinations[2].color_tier`: standard
- `configured_prices.VF9_Eco.combinations[3].color_tier`: standard
- `configured_prices.VF9_Eco.combinations[4].color_tier`: standard
- `configured_prices.VF9_Eco.combinations[5].color_tier`: premium
- `configured_prices.VF9_Eco.combinations[5].total_price_formatted`: 1.511.000.000 VNĐ
- `configured_prices.VF9_Eco.combinations[6].color_tier`: premium
- `configured_prices.VF9_Eco.combinations[6].total_price_formatted`: 1.511.000.000 VNĐ
- `configured_prices.VF9_Plus_7_cho.combinations[0].color_tier`: standard
- `configured_prices.VF9_Plus_7_cho.combinations[1].color_tier`: standard
- `configured_prices.VF9_Plus_7_cho.combinations[2].color_tier`: standard
- `configured_prices.VF9_Plus_7_cho.combinations[3].color_tier`: standard
- `configured_prices.VF9_Plus_7_cho.combinations[4].color_tier`: standard
- `configured_prices.VF9_Plus_7_cho.combinations[5].color_tier`: premium
- `configured_prices.VF9_Plus_7_cho.combinations[5].total_price_formatted`: 1.711.000.000 VNĐ
- `configured_prices.VF9_Plus_7_cho.combinations[6].color_tier`: premium
- `configured_prices.VF9_Plus_7_cho.combinations[6].total_price_formatted`: 1.711.000.000 VNĐ
- `configured_prices.VF9_Plus_ghe_co_truong.combinations[0].color_tier`: standard
- `configured_prices.VF9_Plus_ghe_co_truong.combinations[1].color_tier`: standard
- `configured_prices.VF9_Plus_ghe_co_truong.combinations[2].color_tier`: standard
- `configured_prices.VF9_Plus_ghe_co_truong.combinations[3].color_tier`: standard
- `configured_prices.VF9_Plus_ghe_co_truong.combinations[4].color_tier`: standard
- `configured_prices.VF9_Plus_ghe_co_truong.combinations[5].color_tier`: premium
- `configured_prices.VF9_Plus_ghe_co_truong.combinations[5].total_price_formatted`: 1.743.000.000 VNĐ
- `configured_prices.VF9_Plus_ghe_co_truong.combinations[6].color_tier`: premium
- `configured_prices.VF9_Plus_ghe_co_truong.combinations[6].total_price_formatted`: 1.743.000.000 VNĐ
- `exterior_colors.note`: Per-color prices removed – the data-price-value attributes in the HTML reflect internal cart totals for a specific edition+color combination, not meaningful standalone color prices. Use variant base prices and surcharge only.
- `exterior_colors.color_categories[0].surcharge_label`: Không phụ thu
- `interior_colors.note`: Available interior colors depend on chosen exterior color
- `navigation_sections[5]`: Pin sạc
- `sources.html_snippet`: Provided document (shop.vinfastauto.com VF9 color selector)

## Covered structured ground-truth facts

- `page.url_deposit_page`: https://shop.vinfastauto.com/vn_vi/dat-coc-xe-vf9.html
- `page.url_model_selector`: https://shop.vinfastauto.com/vn_vi/dat-coc-o-to-dien-vinfast.html?modelId=Products-Car-VF9
- `page.model_id`: Products-Car-VF9
- `vehicle.name`: VinFast VF 9
- `vehicle.key_specs.range_wltp_km`: 626
- `vehicle.key_specs.power_hp`: 402
- `vehicle.key_specs.torque_nm`: 620
- `variants[0].edition_id`: NE3NV
- `variants[0].name`: VF 9 Eco
- `variants[0].base_price_vnd`: 1499000000
- `variants[0].base_price_formatted`: 1.499.000.000 VNĐ
- `variants[1].edition_id`: NE3MV
- `variants[1].name`: VF 9 Plus tùy chọn 7 chỗ
- `variants[1].base_price_vnd`: 1699000000
- `variants[1].base_price_formatted`: 1.699.000.000 VNĐ
- `variants[2].edition_id`: NE3MV
- `variants[2].name`: VF 9 Plus tùy chọn ghế cơ trưởng
- `variants[2].base_price_vnd`: 1731000000
- `variants[2].base_price_formatted`: 1.731.000.000 VNĐ
- `pricing_notes[0]`: Giá xe đã bao gồm VAT.
- ... and 184 more

## Generated artifacts

- JSON summary: `guide_2/demo/output/verification/comparison_summary.json`
- Unified diff: `guide_2/demo/output/verification/ground_truth_diff.patch`

Use the diff for line-level review, and use the structured-fact section as a fast smoke test for whether important ground-truth values appeared in the ingestion output.


## Ingested Chunks Verification (Colors & Fallbacks)

- **Total Chunks Loaded**: `4`
- **Chunks Containing Color/Asset Data**: `3`

| Chunk ID | Section | Detected Codes | Images Fallback? | Preview |
| --- | --- | --- | --- | --- |
| `url_2a7cf685fe11_mpv-7_c001` | MPV 7 | `ADAS`, `AWD`, `FWD`, `MPV`, `NEDC`, `PIN`, `SMART`, `WLTP` | No | # MPV 7  MPV 7 VF 7 VF 8 VF 8 The All New VF 9 - Dòng xe cá nhân - Dòng xe dịch vụ Công suất tối đa 30 kW Dung lượng pin... |
| `url_2a7cf685fe11_hud_c001` | HUD | `HUD`, `MPV`, `PIN` | No | # HUD  HUD Màu nâng cao + 12.000.000 VNĐ VF 8 Plus Chỉ từ 1.199.000.000 VNĐ VF 8 Eco Chỉ từ 1.019.000.000 VNĐ Bao gồm PI... |
| `url_2a7cf685fe11_t-y-ch-n-m-u-c-nh-n-h-a_c001` | Tùy chọn màu - Cá nhân hóa | None | No | ### Tùy chọn màu - Cá nhân hóa  Quý khách tùy chọn màu xe theo sở thích, màu xe có thể thay đổi khi đi làm hợp đồng xe.... |

### Detailed Ingested Color Chunks

#### Chunk `url_2a7cf685fe11_mpv-7_c001`
- **Section**: MPV 7
- **Codes**: ADAS, AWD, FWD, MPV, NEDC, PIN, SMART, WLTP
- **Content Preview**:
  ```
  # MPV 7

MPV 7
VF 7
VF 8
VF 8 The All New
VF 9
- Dòng xe cá nhân
- Dòng xe dịch vụ
Công suất tối đa
30 kW
Dung lượng pin khả dụng
18,64 kWh
Quãng đường di chuyển
215 km
Quãng đường di chuyển được tính toán dựa trên kết quả kiểm định theo quy chuẩn toàn cầu (NEDC). Quãng đường di chuyển thực tế có thể giảm so với kết quả kiểm định, phụ thuộc vào tốc độ lái xe, nhiệt độ, địa hình, thói quen sử dụng của người lái, chế độ lái được cài đặt, số lượng hành khách và các điều kiện giao thông khác.
134 hp/100 kW
Quãng đường di chuyển 1 lần sạc đầy lên tới
326,4 km (NEDC)
Chiều dài cơ sở
2.514 mm
148 hp/110 kW
318,6 km (NEDC)
2.610,8 mm
201 hp/150 kW
460 km (NEDC)
2.730 mm
174 hp/130 kW
485 km (NEDC)
480 km (NEDC)
Quãng đường di chuyển 1 lần sạc đầy
Cập nhật sau
2.840 mm
349 hp/260 kW
Đang cập nhật
440 km (NEDC)
349 hp/150 kW
496 km (NEDC)
562 km (NEDC)
2.950 mm
402 hp/300 kW
457 km (WLTP)
602 km
3.149 mm
626 km
150 kW
450 km (NEDC)
110 kW
2.611 mm
326 km (NEDC)
210 km (NEDC)
2.065 mm
175 km (NEDC)
2.520 mm
Quãng đường di chuyển 1 lần sạc đầy (NEDC)
170 kW
Quãng đường di chuyển/lần sạc đầy
480-500 km (NEDC) (Tùy điều kiện vận hành)
2.840mm
- Ngoại thất
- Nội thất
Các thông tin sản phẩm có thể thay đổi mà không cần báo trước
Lựa chọn xe
Nhập thông tin
Xin mời Quý khách vui lòng chọn phiên bản, nội thất và ngoại thất xe.
Phiên bản xe
VF 3 Plus Chỉ từ 323.000.000 VNĐ
VF 3 Eco Chỉ từ 310.000.000 VNĐ
Dịch vụ pin đi kèm
Bao gồm PIN
Màu cơ bản - Theo xe
Màu nâng cao + 8.000.000 VNĐ
Dự toán trả góp
Chi tiết
Dự toán chi phí lăn bánh
Giá xe đã bao gồm VAT. Tặng gói ADAS và Smart Service.
VF 5 Plus Chỉ từ 537.000.000 VNĐ
Tùy chọn
Lõi thép 16 inch Hợp kim 17 inch
Lõi thép 16 inch
Hợp kim 17 inch
Bao gồm PIN 80.000.000 VNĐ
VF e34 SMART Chỉ từ 710.000.000 VNĐ
VF 6 Plus Chỉ từ 745.000.000 VNĐ
VF 6 Eco Chỉ từ 689.000.000 VNĐ
VF 7 Plus Chỉ từ 889.000.000 VNĐ
VF 7 Eco Chỉ từ 801.000.000 VNĐ
Cầu trước (FWD) Hai cầu (AWD, 2 động cơ)
Cầu trước (FWD)
Hai cầu (AWD, 2 động cơ)
Trần thép Trần kính toàn cảnh
Trần thép
Trần kính toàn cảnh
  ```

#### Chunk `url_2a7cf685fe11_hud_c001`
- **Section**: HUD
- **Codes**: HUD, MPV, PIN
- **Content Preview**:
  ```
  # HUD

HUD
Màu nâng cao + 12.000.000 VNĐ
VF 8 Plus Chỉ từ 1.199.000.000 VNĐ
VF 8 Eco Chỉ từ 1.019.000.000 VNĐ
Bao gồm PIN ~420 km/1 lần sạc
Bao gồm PIN ~400 km/1 lần sạc
VF 9 Plus tùy chọn ghế cơ trưởng
VF 9 Plus tùy chọn 7 chỗ
VF 9 Eco
null
Bao gồm PIN ~438 km/1 lần sạc
Bao gồm PIN ~423 km/1 lần sạc
Infinity Blanc
Limo Green Tiêu chuẩn Chỉ từ 749.000.000 VNĐ
Herio Green Tiêu chuẩn - 2 Chỉ từ 479.000.000 VNĐ
Herio Green Tiêu chuẩn - 1 Chỉ từ 499.000.000 VNĐ
Minio Green Tiêu chuẩn Chỉ từ 272.000.000 VNĐ
Màu nâng cao
EC Van Tiêu chuẩn Chỉ từ 285.000.000 VNĐ
EC Van Nâng cao - Có cửa trượt Chỉ từ 325.000.000 VNĐ
EC Van Nâng cao - Không cửa trượt Chỉ từ 305.000.000 VNĐ
VF MPV 7 Tiêu chuẩn Chỉ từ 819.000.000 VNĐ
Màu nâng cao + 10.000.000 VNĐ
VF 8 The All New Comfort Chỉ từ 999.000.000 VNĐ
  ```

#### Chunk `url_2a7cf685fe11_t-y-ch-n-m-u-c-nh-n-h-a_c001`
- **Section**: Tùy chọn màu - Cá nhân hóa
- **Codes**: None
- **Content Preview**:
  ```
  ### Tùy chọn màu - Cá nhân hóa

Quý khách tùy chọn màu xe theo sở thích, màu xe có thể thay đổi khi đi làm hợp đồng xe.
  ```
