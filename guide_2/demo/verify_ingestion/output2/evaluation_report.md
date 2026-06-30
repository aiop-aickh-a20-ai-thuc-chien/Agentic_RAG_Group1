# Local Ground-Truth Verification Report

This report was generated locally without sending content to an LLM.

## Summary

- Text similarity ratio: `0.0112`
- Ground truth: 1715 words, 235 lines
- Actual output: 7863 words, 174 lines
- Evidence artifacts searched: 15

## Primary URL routing signal

- Source URL path: `/vn_vi/thong-tin-bao-hanh`
- Primary routing parameter: `modelId`
- Primary model ID: `None`
- Model ID present in actual markdown: `False`
- Model ID present in evidence corpus: `False`
- Model ID present in ground truth: `False`

`modelId` is treated as the page-routing variable for VinFast model-selector URLs, so changing it to VF3/VF5/VF6/VF7/etc. should change the target page being verified.
- Structured key-fact coverage: 6/243 (`0.0247`)
- Structured coverage verdict: `fail`

## Missing structured ground-truth facts

- `page.title`: Xe điện VinFast VF 9 - Giá bán và chương trình ưu đãi | VinFast
- `page.url_model_selector`: https://shop.vinfastauto.com/vn_vi/dat-coc-o-to-dien-vinfast.html?modelId=Products-Car-VF9
- `page.model_id`: Products-Car-VF9
- `vehicle.name`: VinFast VF 9
- `vehicle.type`: eSUV – SUV điện 7 chỗ hạng sang
- `vehicle.tagline`: Sự Lựa Chọn Của Người Thành Đạt, Tiên Phong
- `vehicle.key_specs.range_note`: Tiêu chuẩn WLTP, phiên bản Eco pin CATL
- `vehicle.key_specs.torque_nm`: 620
- `vehicle.key_specs.warranty`: 200.000 km hoặc 10 năm
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
- `deposit.amount_vnd`: 50000000
- `deposit.amount_formatted`: 50.000.000 VNĐ
- `deposit.cta_label`: Đặt cọc 50.000.000 VNĐ
- `deposit.cta_url`: https://shop.vinfastauto.com/vn_vi/dat-coc-o-to-dien-vinfast.html?modelId=Products-Car-VF9
- `rolling_cost_popup.trigger_element`: <a href="javascript:void(0);" data-bs-toggle="modal" data-bs-target="#rollingUpCostPopUp" class="tab-right-cost-more js-rollingUpCostPopUp">Chi tiết</a>
- `rolling_cost_popup.modal_id`: rollingUpCostPopUp
- `rolling_cost_popup.purpose`: Hiển thị chi phí lăn bánh (on-road cost breakdown)
- `configured_prices.note`: Giá xe = Giá niêm yết phiên bản + Phụ thu màu (nếu có). Đã bao gồm VAT.
- `configured_prices.pricing_rule.premium_color_surcharge_vnd`: 12000000
- `configured_prices.pricing_rule.premium_colors[0]`: CE22
- `configured_prices.pricing_rule.premium_colors[1]`: CE17
- `configured_prices.VF9_Eco.edition_id`: NE3NV
- `configured_prices.VF9_Eco.base_price_vnd`: 1499000000
- `configured_prices.VF9_Eco.combinations[0].color_code`: CE18
- `configured_prices.VF9_Eco.combinations[0].color_name`: Infinity Blanc
- `configured_prices.VF9_Eco.combinations[0].color_tier`: standard
- `configured_prices.VF9_Eco.combinations[0].total_price_vnd`: 1499000000
- `configured_prices.VF9_Eco.combinations[0].total_price_formatted`: 1.499.000.000 VNĐ
- ... and 197 more

## Covered structured ground-truth facts

- `page.url_deposit_page`: https://shop.vinfastauto.com/vn_vi/dat-coc-xe-vf9.html
- `vehicle.key_specs.range_wltp_km`: 626
- `vehicle.key_specs.power_hp`: 402
- `rolling_cost_popup.label`: Chi tiết
- `navigation_sections[1]`: Ngoại thất
- `sources.pdp_page`: https://shop.vinfastauto.com/vn_vi/dat-coc-xe-vf9.html

## Generated artifacts

- JSON summary: `guide_2/demo/verify_ingestion/output2/comparison_summary.json`
- Unified diff: `guide_2/demo/verify_ingestion/output2/ground_truth_diff.patch`

Use the diff for line-level review, and use the structured-fact section as a fast smoke test for whether important ground-truth values appeared in the ingestion output.


## Ingested Chunks Verification (Colors & Fallbacks)

- **Total Chunks Loaded**: `30`
- **Chunks Containing Color/Asset Data**: `19`

| Chunk ID | Section | Detected Codes | Images Fallback? | Preview |
| --- | --- | --- | --- | --- |
| `url_7f921895430c_vf-8_c001` | VF 8 | `MPV` | No | ### VF 8  - structure_block_type: product_card - structure_block_id: dom_122aa112ed62 - structure_dedupe_hash: b057918f4... |
| `url_7f921895430c_vf-8_c002` | VF 8 | `MPV`, `VAN` | No | ### VF 8  - structure_block_type: product_card - structure_block_id: dom_320b6a748db1 - structure_dedupe_hash: 2797a4f3e... |
| `url_7f921895430c_vf-8_c003` | VF 8 | `MPV`, `VAN` | No | ### VF 8  - structure_block_type: product_card - structure_block_id: dom_6eec604a905c - structure_dedupe_hash: 69c8f80d6... |
| `url_7f921895430c_vf-8_c005` | VF 8 | `LFP`, `MPV`, `VAN` | No | ### VF 8  structure_block_type: product_card - structure_block_id: dom_e53b8fcc66c5 - structure_dedupe_hash: 531f13d12b0... |
| `url_7f921895430c_vf-8_c006` | VF 8 | `LFP`, `MPV`, `PIN`, `VAN` | No | ### VF 8  content: Thời hạn bảo hành ô tô Thời hạn bảo hành ô tô VinFast đã chuyển đổi Sổ Bảo Hành sang hình thức điện t... |
| `url_7f921895430c_vf-8_c008` | VF 8 | `MPV` | No | ### VF 8  structure_block_type: product_card - structure_block_id: dom_12f51df74304 - structure_dedupe_hash: 8a1e3132a90... |
| `url_7f921895430c_vf-8_c009` | VF 8 | `MPV` | No | ### VF 8  content: Pin cao áp Pin cao áp mua theo xe mới, sử dụng tiêu chuẩn: Áp dụng cho VF 8, VF 9, Lạc Hồng LX 900, L... |
| `url_7f921895430c_vf-8_c010` | VF 8 | `MPV` | No | ### VF 8  ngoại thất Điều kiện sử dụng tiêu chuẩn: Áp dụng cho VF 8, VF 9, Lạc Hồng LX 900, Lạc Hồng 900S, Lạc Hồng 800S... |
| `url_7f921895430c_vf-8_c012` | VF 8 | `MPV` | No | ### VF 8  structure_block_type: product_card - structure_block_id: dom_c15be9997ba8 - structure_dedupe_hash: 51140220e7f... |
| `url_7f921895430c_vf-8_c013` | VF 8 | `MPV` | No | ### VF 8  content: Phụ tùng xe mới Bảo hành giới hạn Pin cao áp Pin cao áp mua theo xe mới, sử dụng tiêu chuẩn: Áp dụng ... |
| `url_7f921895430c_vf-8_c014` | VF 8 | `MPV` | No | ### VF 8  ngoại thất Điều kiện sử dụng tiêu chuẩn: Áp dụng cho VF 8, VF 9, Lạc Hồng LX 900, Lạc Hồng 900S, Lạc Hồng 800S... |
| `url_7f921895430c_vf-8_c016` | VF 8 | `MPV` | No | ### VF 8  structure_block_type: product_card - structure_block_id: dom_9b4c832d4376 - structure_dedupe_hash: 4051ea06447... |
| `url_7f921895430c_vf-8_c017` | VF 8 | `MPV` | No | ### VF 8  content: Phụ tùng xe mới Bảo hành giới hạn Pin cao áp Pin cao áp mua theo xe mới, sử dụng tiêu chuẩn: Áp dụng ... |
| `url_7f921895430c_vf-8_c018` | VF 8 | `MPV` | No | ### VF 8  ngoại thất Điều kiện sử dụng tiêu chuẩn: Áp dụng cho VF 8, VF 9, Lạc Hồng LX 900, Lạc Hồng 900S, Lạc Hồng 800S... |
| `url_7f921895430c_th-ng-tin-b-o-h-nh-vinfast-product-card_c003` | Thông tin bảo hành | VinFast product card | `XDV` | No | ### Thông tin bảo hành | VinFast product card  - structure_block_type: product_card - structure_block_id: dom_732fdb574b... |
| `url_7f921895430c_th-ng-tin-b-o-h-nh-vinfast-product-card_c004` | Thông tin bảo hành | VinFast product card | `NPP`, `XDV` | No | ### Thông tin bảo hành | VinFast product card  - structure_block_type: product_card - structure_block_id: dom_a3882252ce... |
| `url_7f921895430c_th-ng-tin-b-o-h-nh-vinfast-product-card_c005` | Thông tin bảo hành | VinFast product card | `NPP`, `XDV` | No | ### Thông tin bảo hành | VinFast product card  - structure_block_type: product_card - structure_block_id: dom_7001df2078... |
| `url_7f921895430c_th-ng-tin-b-o-h-nh-vinfast-product-card_c006` | Thông tin bảo hành | VinFast product card | `NPP`, `XDV` | No | ### Thông tin bảo hành | VinFast product card  - structure_block_type: product_card - structure_block_id: dom_ae3badfdfc... |
| `url_7f921895430c_th-ng-tin-b-o-h-nh-vinfast-product-card_c007` | Thông tin bảo hành | VinFast product card | `XDV` | No | ### Thông tin bảo hành | VinFast product card  - structure_block_type: product_card - structure_block_id: dom_5c10d22255... |

### Detailed Ingested Color Chunks

#### Chunk `url_7f921895430c_vf-8_c001`
- **Section**: VF 8
- **Codes**: MPV
- **Content Preview**:
  ```
  ### VF 8

- structure_block_type: product_card
- structure_block_id: dom_122aa112ed62
- structure_dedupe_hash: b057918f45c0
- structure_attributes: class='field__item'
- content: VinFast đã chuyển đổi Sổ Bảo Hành sang hình thức điện tử. Tại thời điểm bàn giao xe, Đại lý phân phối sẽ tư vấn, hướng dẫn Khách hàng xác nhận Sổ Bảo Hành điện tử và cách thức tra cứu, sử dụng. Đối với xe được sử dụng ở điều kiện sử dụng tiêu chuẩn: Thời hạn bảo hành 10 năm hoặc 200.000 km tùy điều kiện nào đến trước: Fadil, Lux A 2.0, Lux SA 2.0, President, VF 8, VF 9, Lạc Hồng LX 900, Lạc Hồng 900S, Lạc Hồng 800S. Thời hạn bảo hành 7 năm hoặc 160.000 km tùy điều kiện nào đến trước: VF 3, VF 5, VF 6, VF 7, VF 8 The All New, VF e34, VF Minio Green, VF Nerio Green, VF Herio Green, VF MPV 7, VF Limo Green. Thời hạn bảo hành 5 năm hoặc 130.000 km tùy điều kiện nào đến trước: VF EC Van. Đối với xe đang hoặc đã từng được sử dụng cho hoạt động dịch vụ thương mại: Thời hạn bảo hành 3 năm hoặc 100.000 km tùy điều kiện nào đến trước: VF 3, VF 7, VF 8, VF 9, VF 8 The All New. Phụ tùng được thay thế theo chính sách bảo hành xe có thời hạn bảo hành bằng thời hạn bảo hành còn lại của xe; hoặc thời hạn bảo hành còn lại của phụ tùng được thay thế đó (trong trường hợp phụ tùng có thời hạn bảo hành riêng). ** Dịch vụ thương mại là đối tượng khách hàng kinh doanh, bao gồm nhưng không giới hạn, đang hoặc đã từng sử dụng xe làm taxi, xe sử dụng cho dịch vụ chở khách, kể cả các dịch vụ như Grab, Be hay tương tự, xe cho thuê, xe đưa đón, xe giao hàng. Đối với xe đã từng được sử dụng cho mục đích dịch vụ thương mại, chính sách bảo hành áp dụng cho xe sử dụng cho mục đích dịch vụ thương mại sẽ tiếp tục được duy trì và áp dụng kể cả trong trường hợp chuyển nhượng xe.
  ```

#### Chunk `url_7f921895430c_vf-8_c002`
- **Section**: VF 8
- **Codes**: MPV, VAN
- **Content Preview**:
  ```
  ### VF 8

- structure_block_type: product_card
- structure_block_id: dom_320b6a748db1
- structure_dedupe_hash: 2797a4f3ed8e
- structure_attributes: class='warranty-time-info'
- content: Thời hạn bảo hành ô tô VinFast đã chuyển đổi Sổ Bảo Hành sang hình thức điện tử. Tại thời điểm bàn giao xe, Đại lý phân phối sẽ tư vấn, hướng dẫn Khách hàng xác nhận Sổ Bảo Hành điện tử và cách thức tra cứu, sử dụng. Đối với xe được sử dụng ở điều kiện sử dụng tiêu chuẩn: Thời hạn bảo hành 10 năm hoặc 200.000 km tùy điều kiện nào đến trước: Fadil, Lux A 2.0, Lux SA 2.0, President, VF 8, VF 9, Lạc Hồng LX 900, Lạc Hồng 900S, Lạc Hồng 800S. Thời hạn bảo hành 7 năm hoặc 160.000 km tùy điều kiện nào đến trước: VF 3, VF 5, VF 6, VF 7, VF 8 The All New, VF e34, VF Minio Green, VF Nerio Green, VF Herio Green, VF MPV 7, VF Limo Green. Thời hạn bảo hành 5 năm hoặc 130.000 km tùy điều kiện nào đến trước: VF EC Van. Đối với xe đang hoặc đã từng được sử dụng cho hoạt động dịch vụ thương mại: Thời hạn bảo hành 3 năm hoặc 100.000 km tùy điều kiện nào đến trước: VF 3, VF 7, VF 8, VF 9, VF 8 The All New. Phụ tùng được thay thế theo chính sách bảo hành xe có thời hạn bảo hành bằng thời hạn bảo hành còn lại của xe; hoặc thời hạn bảo hành còn lại của phụ tùng được thay thế đó (trong trường hợp phụ tùng có thời hạn bảo hành riêng). ** Dịch vụ thương mại là đối tượng khách hàng kinh doanh, bao gồm nhưng không giới hạn, đang hoặc đã từng sử dụng xe làm taxi, xe sử dụng cho dịch vụ chở khách, kể cả các dịch vụ như Grab, Be hay tương tự, xe cho thuê, xe đưa đón, xe giao hàng. Đối với xe đã từng được sử dụng cho mục đích dịch vụ thương mại, chính sách bảo hành áp dụng cho xe sử dụng cho mục đích dịch vụ thương mại sẽ tiếp tục được duy trì và áp dụng kể cả trong trường hợp chuyển nhượng xe. SỔ BẢO HÀNH Ô TÔ VF 3 VF 5 VF 6 VF 8 VF 9 Lac Hong 900 LX Minio Green Nerio Green Herio Green Limo Green VF EC VAN Ebus 6B Ebus 8B Ebus 10B MPV 7 HƯỚNG DẪN SỬ DỤNG
  ```

#### Chunk `url_7f921895430c_vf-8_c003`
- **Section**: VF 8
- **Codes**: MPV, VAN
- **Content Preview**:
  ```
  ### VF 8

- structure_block_type: product_card
- structure_block_id: dom_6eec604a905c
- structure_dedupe_hash: 69c8f80d6a14
- structure_attributes: class='paragraph paragraph--type--warranty-time paragraph--view-mode--default'
- content: Thời hạn bảo hành ô tô Thời hạn bảo hành ô tô VinFast đã chuyển đổi Sổ Bảo Hành sang hình thức điện tử. Tại thời điểm bàn giao xe, Đại lý phân phối sẽ tư vấn, hướng dẫn Khách hàng xác nhận Sổ Bảo Hành điện tử và cách thức tra cứu, sử dụng. Đối với xe được sử dụng ở điều kiện sử dụng tiêu chuẩn: Thời hạn bảo hành 10 năm hoặc 200.000 km tùy điều kiện nào đến trước: Fadil, Lux A 2.0, Lux SA 2.0, President, VF 8, VF 9, Lạc Hồng LX 900, Lạc Hồng 900S, Lạc Hồng 800S. Thời hạn bảo hành 7 năm hoặc 160.000 km tùy điều kiện nào đến trước: VF 3, VF 5, VF 6, VF 7, VF 8 The All New, VF e34, VF Minio Green, VF Nerio Green, VF Herio Green, VF MPV 7, VF Limo Green. Thời hạn bảo hành 5 năm hoặc 130.000 km tùy điều kiện nào đến trước: VF EC Van. Đối với xe đang hoặc đã từng được sử dụng cho hoạt động dịch vụ thương mại: Thời hạn bảo hành 3 năm hoặc 100.000 km tùy điều kiện nào đến trước: VF 3, VF 7, VF 8, VF 9, VF 8 The All New. Phụ tùng được thay thế theo chính sách bảo hành xe có thời hạn bảo hành bằng thời hạn bảo hành còn lại của xe; hoặc thời hạn bảo hành còn lại của phụ tùng được thay thế đó (trong trường hợp phụ tùng có thời hạn bảo hành riêng). ** Dịch vụ thương mại là đối tượng khách hàng kinh doanh, bao gồm nhưng không giới hạn, đang hoặc đã từng sử dụng xe làm taxi, xe sử dụng cho dịch vụ chở khách, kể cả các dịch vụ như Grab, Be hay tương tự, xe cho thuê, xe đưa đón, xe giao hàng. Đối với xe đã từng được sử dụng cho mục đích dịch vụ thương mại, chính sách bảo hành áp dụng cho xe sử dụng cho mục đích dịch vụ thương mại sẽ tiếp tục được duy trì và áp dụng kể cả trong trường hợp chuyển nhượng xe. SỔ BẢO HÀNH Ô TÔ VF 3 VF 5 VF 6 VF 8 VF 9 Lac Hong 900 LX Minio Green Nerio Green Herio Green Limo Green VF EC VAN Ebus 6B Ebus 8B Ebus 10B MPV 7 HƯỚNG DẪN SỬ DỤNG
  ```

#### Chunk `url_7f921895430c_vf-8_c005`
- **Section**: VF 8
- **Codes**: LFP, MPV, VAN
- **Content Preview**:
  ```
  ### VF 8

structure_block_type: product_card
- structure_block_id: dom_e53b8fcc66c5
- structure_dedupe_hash: 531f13d12b00
- structure_attributes: class='field__items'
- content: Thời hạn bảo hành ô tô Thời hạn bảo hành ô tô VinFast đã chuyển đổi Sổ Bảo Hành sang hình thức điện tử. Tại thời điểm bàn giao xe, Đại lý phân phối sẽ tư vấn, hướng dẫn Khách hàng xác nhận Sổ Bảo Hành điện tử và cách thức tra cứu, sử dụng. Đối với xe được sử dụng ở điều kiện sử dụng tiêu chuẩn: Thời hạn bảo hành 10 năm hoặc 200.000 km tùy điều kiện nào đến trước: Fadil, Lux A 2.0, Lux SA 2.0, President, VF 8, VF 9, Lạc Hồng LX 900, Lạc Hồng 900S, Lạc Hồng 800S. Thời hạn bảo hành 7 năm hoặc 160.000 km tùy điều kiện nào đến trước: VF 3, VF 5, VF 6, VF 7, VF 8 The All New, VF e34, VF Minio Green, VF Nerio Green, VF Herio Green, VF MPV 7, VF Limo Green. Thời hạn bảo hành 5 năm hoặc 130.000 km tùy điều kiện nào đến trước: VF EC Van. Đối với xe đang hoặc đã từng được sử dụng cho hoạt động dịch vụ thương mại: Thời hạn bảo hành 3 năm hoặc 100.000 km tùy điều kiện nào đến trước: VF 3, VF 7, VF 8, VF 9, VF 8 The All New. Phụ tùng được thay thế theo chính sách bảo hành xe có thời hạn bảo hành bằng thời hạn bảo hành còn lại của xe; hoặc thời hạn bảo hành còn lại của phụ tùng được thay thế đó (trong trường hợp phụ tùng có thời hạn bảo hành riêng). ** Dịch vụ thương mại là đối tượng khách hàng kinh doanh, bao gồm nhưng không giới hạn, đang hoặc đã từng sử dụng xe làm taxi, xe sử dụng cho dịch vụ chở khách, kể cả các dịch vụ như Grab, Be hay tương tự, xe cho thuê, xe đưa đón, xe giao hàng. Đối với xe đã từng được sử dụng cho mục đích dịch vụ thương mại, chính sách bảo hành áp dụng cho xe sử dụng cho mục đích dịch vụ thương mại sẽ tiếp tục được duy trì và áp dụng kể cả trong trường hợp chuyển nhượng xe. SỔ BẢO HÀNH Ô TÔ VF 3 VF 5 VF 6 VF 8 VF 9 Lac Hong 900 LX Minio Green Nerio Green Herio Green Limo Green VF EC VAN Ebus 6B Ebus 8B Ebus 10B MPV 7 HƯỚNG DẪN SỬ DỤNG Thời hạn bảo hành xe máy điện Thời hạn bảo hành xe máy điện Đối với các dòng xe máy điện VinFast sử dụng pin LFP, thời hạn bảo hành xe là 6 năm/không giới hạn số km và thời hạn bảo hành pin lên tới 8 năm/không giới hạn số km .
  ```

#### Chunk `url_7f921895430c_vf-8_c006`
- **Section**: VF 8
- **Codes**: LFP, MPV, PIN, VAN
- **Content Preview**:
  ```
  ### VF 8

content: Thời hạn bảo hành ô tô Thời hạn bảo hành ô tô VinFast đã chuyển đổi Sổ Bảo Hành sang hình thức điện tử. Tại thời điểm bàn giao xe, Đại lý phân phối sẽ tư vấn, hướng dẫn Khách hàng xác nhận Sổ Bảo Hành điện tử và cách thức tra cứu, sử dụng. Đối với xe được sử dụng ở điều kiện sử dụng tiêu chuẩn: Thời hạn bảo hành 10 năm hoặc 200.000 km tùy điều kiện nào đến trước: Fadil, Lux A 2.0, Lux SA 2.0, President, VF 8, VF 9, Lạc Hồng LX 900, Lạc Hồng 900S, Lạc Hồng 800S. Thời hạn bảo hành 7 năm hoặc 160.000 km tùy điều kiện nào đến trước: VF 3, VF 5, VF 6, VF 7, VF 8 The All New, VF e34, VF Minio Green, VF Nerio Green, VF Herio Green, VF MPV 7, VF Limo Green. Thời hạn bảo hành 5 năm hoặc 130.000 km tùy điều kiện nào đến trước: VF EC Van. Đối với xe đang hoặc đã từng được sử dụng cho hoạt động dịch vụ thương mại: Thời hạn bảo hành 3 năm hoặc 100.000 km tùy điều kiện nào đến trước: VF 3, VF 7, VF 8, VF 9, VF 8 The All New. Phụ tùng được thay thế theo chính sách bảo hành xe có thời hạn bảo hành bằng thời hạn bảo hành còn lại của xe; hoặc thời hạn bảo hành còn lại của phụ tùng được thay thế đó (trong trường hợp phụ tùng có thời hạn bảo hành riêng). ** Dịch vụ thương mại là đối tượng khách hàng kinh doanh, bao gồm nhưng không giới hạn, đang hoặc đã từng sử dụng xe làm taxi, xe sử dụng cho dịch vụ chở khách, kể cả các dịch vụ như Grab, Be hay tương tự, xe cho thuê, xe đưa đón, xe giao hàng. Đối với xe đã từng được sử dụng cho mục đích dịch vụ thương mại, chính sách bảo hành áp dụng cho xe sử dụng cho mục đích dịch vụ thương mại sẽ tiếp tục được duy trì và áp dụng kể cả trong trường hợp chuyển nhượng xe. SỔ BẢO HÀNH Ô TÔ VF 3 VF 5 VF 6 VF 8 VF 9 Lac Hong 900 LX Minio Green Nerio Green Herio Green Limo Green VF EC VAN Ebus 6B Ebus 8B Ebus 10B MPV 7 HƯỚNG DẪN SỬ DỤNG Thời hạn bảo hành xe máy điện Thời hạn bảo hành xe máy điện Đối với các dòng xe máy điện VinFast sử dụng pin LFP, thời hạn bảo hành xe là 6 năm/không giới hạn số km và thời hạn bảo hành pin lên tới 8 năm/không giới hạn số km .
Các dòng xe còn lại thời hạn bảo hành 3 năm/không giới hạn km. Đối với pin LFP theo mô hình đổi pin, thời hạn bảo hành là 8 năm/ không giới hạn số km. Quý khách hàng vui lòng tham khảo tại Sổ bảo hành để biết thêm các thông tin bảo hành chi tiết. SỔ BẢO HÀNH XE MÁY ĐIỆN PIN LFP SỔ BẢO HÀNH XE MÁY ĐIỆN PIN KHÁC HƯỚNG DẪN SỬ DỤNG XE MÁY ĐIỆN Klara A1 Klara A2 Klara S Ludo Impes Feliz Theon Klara A2 2020 Vento Tempest Feliz S Shiper Feliz S Klara S2 Theon S Vento S Evo200 Evo200 Lite Motio Evo Neo Evo Lite Neo Vento Neo Feliz Neo Klara Neo Evo Grand Evo Grand Lite Feliz II Feliz 2025 Feliz Lite Vero X ZGoo Flazz VinFast Evo VinFast Amio VinFast Feliz II VinFast Viper VinFast Evo Lite VinFast Flazz VinFast Amio S VF DrgnFly eBike
  ```

#### Chunk `url_7f921895430c_vf-8_c008`
- **Section**: VF 8
- **Codes**: MPV
- **Content Preview**:
  ```
  ### VF 8

structure_block_type: product_card
- structure_block_id: dom_12f51df74304
- structure_dedupe_hash: 8a1e3132a90f
- structure_attributes: class='field__items'
- content: Pin cao áp Pin cao áp mua theo xe mới, sử dụng tiêu chuẩn: Áp dụng cho VF 8, VF 9, Lạc Hồng LX 900, Lạc Hồng 900S, Lạc Hồng 800S: được bảo hành 10 năm hoặc 200.000 km tùy theo điều kiện nào đến trước. Áp dụng cho VF 3, VF 5, VF 6, VF 7, VF 8 The All New, VF Minio Green, VF Herio Green, VF MPV 7, VF e34, VF Nerio Green, VF Limo Green: được bảo hành 8 năm hoặc 160.000 km tùy điều kiện nào đến trước. Áp dụng cho VF EC Van: được bảo hành 7 năm hoặc 160.000 km tùy điều kiện nào đến trước. Pin cao áp mua theo xe mới, xe đang hoặc đã từng sử dụng cho mục đích dịch vụ thương mại: Áp dụng cho VF 3, VF 7, VF 8, VF 9: được bảo hành 3 năm hoặc 100.000 km tùy điều kiện nào đến trước. Đối với xe đã từng được sử dụng cho mục đích dịch vụ thương mại, chính sách bảo hành pin áp dụng cho xe sử dụng cho mục đích dịch vụ thương mại sẽ tiếp tục được duy trì và áp dụng kể cả trong trường hợp chuyển nhượng xe cho chủ sở hữu mới hoặc xe không còn được sử dụng cho mục đích dịch vụ thương mại. Ắc - quy Ô tô xăng: 1 năm hoặc 20.000 km tùy thuộc điều kiện nào đến trước. Ô tô điện: 1 năm (không giới hạn quãng đường sử dụng). Gỉ sét Điều kiện sử dụng tiêu chuẩn: Bảo hành gỉ sét có thời hạn bảo hành là 10 năm từ ngày kích hoạt bảo hành xe (không giới hạn quãng đường sử dụng) với xe VF 8, VF 9, Lạc Hồng LX 900, Lạc Hồng 900S, Lạc Hồng 800S. sử dụng trong điều kiện tiêu chuẩn, áp dụng với tấm kim loại bị xuyên thủng trong điều kiện hoạt động bình thường mà nguyên nhân do lỗi nguyên vật liệu hoặc lỗi lắp ráp của nhà sản xuất, và 7 năm không giới hạn số km với xe VF 3, VF 5, VF 6, VF 7, VF 8 The All New, VF Minio Green, VF Herio Green, VF MPV 7, VF e34, VF Nerio Green, VF Limo Green và 5 năm không giới hạn số km với xe VF EC Van. Sử dụng cho dịch vụ thương mại: Bảo hành là 3 năm hoặc 100.000 km với xe đang hoặc đã từng sử dụng cho mục đích dịch vụ thương mại đối với VF 3, VF 7, VF 8, VF 9.
  ```

#### Chunk `url_7f921895430c_vf-8_c009`
- **Section**: VF 8
- **Codes**: MPV
- **Content Preview**:
  ```
  ### VF 8

content: Pin cao áp Pin cao áp mua theo xe mới, sử dụng tiêu chuẩn: Áp dụng cho VF 8, VF 9, Lạc Hồng LX 900, Lạc Hồng 900S, Lạc Hồng 800S: được bảo hành 10 năm hoặc 200.000 km tùy theo điều kiện nào đến trước. Áp dụng cho VF 3, VF 5, VF 6, VF 7, VF 8 The All New, VF Minio Green, VF Herio Green, VF MPV 7, VF e34, VF Nerio Green, VF Limo Green: được bảo hành 8 năm hoặc 160.000 km tùy điều kiện nào đến trước. Áp dụng cho VF EC Van: được bảo hành 7 năm hoặc 160.000 km tùy điều kiện nào đến trước. Pin cao áp mua theo xe mới, xe đang hoặc đã từng sử dụng cho mục đích dịch vụ thương mại: Áp dụng cho VF 3, VF 7, VF 8, VF 9: được bảo hành 3 năm hoặc 100.000 km tùy điều kiện nào đến trước. Đối với xe đã từng được sử dụng cho mục đích dịch vụ thương mại, chính sách bảo hành pin áp dụng cho xe sử dụng cho mục đích dịch vụ thương mại sẽ tiếp tục được duy trì và áp dụng kể cả trong trường hợp chuyển nhượng xe cho chủ sở hữu mới hoặc xe không còn được sử dụng cho mục đích dịch vụ thương mại. Ắc - quy Ô tô xăng: 1 năm hoặc 20.000 km tùy thuộc điều kiện nào đến trước. Ô tô điện: 1 năm (không giới hạn quãng đường sử dụng). Gỉ sét Điều kiện sử dụng tiêu chuẩn: Bảo hành gỉ sét có thời hạn bảo hành là 10 năm từ ngày kích hoạt bảo hành xe (không giới hạn quãng đường sử dụng) với xe VF 8, VF 9, Lạc Hồng LX 900, Lạc Hồng 900S, Lạc Hồng 800S. sử dụng trong điều kiện tiêu chuẩn, áp dụng với tấm kim loại bị xuyên thủng trong điều kiện hoạt động bình thường mà nguyên nhân do lỗi nguyên vật liệu hoặc lỗi lắp ráp của nhà sản xuất, và 7 năm không giới hạn số km với xe VF 3, VF 5, VF 6, VF 7, VF 8 The All New, VF Minio Green, VF Herio Green, VF MPV 7, VF e34, VF Nerio Green, VF Limo Green và 5 năm không giới hạn số km với xe VF EC Van. Sử dụng cho dịch vụ thương mại: Bảo hành là 3 năm hoặc 100.000 km với xe đang hoặc đã từng sử dụng cho mục đích dịch vụ thương mại đối với VF 3, VF 7, VF 8, VF 9.
Sơn ngoại thất Điều kiện sử dụng tiêu chuẩn: Áp dụng cho VF 8, VF 9, Lạc Hồng LX 900, Lạc Hồng 900S, Lạc Hồng 800S: được bảo hành 10 năm không giới hạn số km. Áp dụng cho VF 3, VF 5, VF 6, VF 7, VF 8 The All New, VF Minio Green, VF Herio Green, VF MPV 7, VF e34, VF Nerio Green, VF Limo Green: được bảo hành 7 năm không giới hạn số km. Áp dụng cho VF EC Van: được bảo hành 5 năm không giới hạn số km. Sử dụng cho dịch vụ thương mại: 3 năm hoặc 100.000 km tùy điều kiện nào đến trước áp dụng cho VF 3, VF 7, VF 8, VF 9. Các bộ phận treo Sử dụng trong điều kiện tiêu chuẩn: Các bộ phận treo (Bộ giảm xóc, Thanh ổn định, Cụm liên kết trên, Cánh tay điều khiển dưới, Khớp bi, Lắp thanh chống trên) được bảo hành 5 năm hoặc 130.000 km tùy điều kiện nào đến trước. Sử dụng cho mục đích dịch vụ thương mại: Áp dụng cho VF 3, VF 7, VF 8, VF 9, thời hạn bảo hành là 3 năm hoặc 100.000 km. Lốp xe Lốp được trang bị theo xe (bao gồm cả lốp dự phòng nếu có) được bảo hành đối với các khuyết tật, hư hỏng do lỗi nguyên vật liệu hoặc lỗi trong quá trình sản xuất, lưu kho của nhà sản xuất lốp được tính kể từ ngày kích hoạt bảo hành xe. Chi tiết bảo hành đối với từng loại sản phẩm như sau: Ô tô xăng: 5 năm (không giới hạn quãng đường sử dụng). Ô tô điện: Bảo hành bởi nhà sản xuất lốp xe. Nếu nhà sản xuất lốp cung cấp dịch vụ bảo hành tại thị trường Việt Nam, lốp xe sẽ được bảo hành hành theo chính sách riêng của nhà sản xuất lốp xe. Những hạng mục, hư hỏng không thuộc bảo hành lốp: Hư hỏng do lốp xe bị phá hoại, tai nạn hoặc va chạm. Hư hỏng do lốp bị lạm dụng trong quá trình sử dụng. Hư hỏng do lốp không được bảo dưỡng hoặc vận hành với áp suất lốp không tiêu chuẩn. Lốp là chi tiết hao mòn theo thời gian và quãng đường sử dụng, các hao mòn này không thuộc phạm vi bảo hành. Các hư hỏng được đánh giá không ảnh hưởng đến chất lượng, hiệu suất hoặc chức năng của lốp. Sử dụng lốp sai so với mục đích khuyến nghị của nhà sản xuất. Lốp đã được sửa chữa, thay đổi, đắp hoặc dán lại.
  ```

#### Chunk `url_7f921895430c_vf-8_c010`
- **Section**: VF 8
- **Codes**: MPV
- **Content Preview**:
  ```
  ### VF 8

ngoại thất Điều kiện sử dụng tiêu chuẩn: Áp dụng cho VF 8, VF 9, Lạc Hồng LX 900, Lạc Hồng 900S, Lạc Hồng 800S: được bảo hành 10 năm không giới hạn số km. Áp dụng cho VF 3, VF 5, VF 6, VF 7, VF 8 The All New, VF Minio Green, VF Herio Green, VF MPV 7, VF e34, VF Nerio Green, VF Limo Green: được bảo hành 7 năm không giới hạn số km. Áp dụng cho VF EC Van: được bảo hành 5 năm không giới hạn số km. Sử dụng cho dịch vụ thương mại: 3 năm hoặc 100.000 km tùy điều kiện nào đến trước áp dụng cho VF 3, VF 7, VF 8, VF 9. Các bộ phận treo Sử dụng trong điều kiện tiêu chuẩn: Các bộ phận treo (Bộ giảm xóc, Thanh ổn định, Cụm liên kết trên, Cánh tay điều khiển dưới, Khớp bi, Lắp thanh chống trên) được bảo hành 5 năm hoặc 130.000 km tùy điều kiện nào đến trước. Sử dụng cho mục đích dịch vụ thương mại: Áp dụng cho VF 3, VF 7, VF 8, VF 9, thời hạn bảo hành là 3 năm hoặc 100.000 km. Lốp xe Lốp được trang bị theo xe (bao gồm cả lốp dự phòng nếu có) được bảo hành đối với các khuyết tật, hư hỏng do lỗi nguyên vật liệu hoặc lỗi trong quá trình sản xuất, lưu kho của nhà sản xuất lốp được tính kể từ ngày kích hoạt bảo hành xe. Chi tiết bảo hành đối với từng loại sản phẩm như sau: Ô tô xăng: 5 năm (không giới hạn quãng đường sử dụng). Ô tô điện: Bảo hành bởi nhà sản xuất lốp xe. Nếu nhà sản xuất lốp cung cấp dịch vụ bảo hành tại thị trường Việt Nam, lốp xe sẽ được bảo hành hành theo chính sách riêng của nhà sản xuất lốp xe. Những hạng mục, hư hỏng không thuộc bảo hành lốp: Hư hỏng do lốp xe bị phá hoại, tai nạn hoặc va chạm. Hư hỏng do lốp bị lạm dụng trong quá trình sử dụng. Hư hỏng do lốp không được bảo dưỡng hoặc vận hành với áp suất lốp không tiêu chuẩn. Lốp là chi tiết hao mòn theo thời gian và quãng đường sử dụng, các hao mòn này không thuộc phạm vi bảo hành. Các hư hỏng được đánh giá không ảnh hưởng đến chất lượng, hiệu suất hoặc chức năng của lốp. Sử dụng lốp sai so với mục đích khuyến nghị của nhà sản xuất. Lốp đã được sửa chữa, thay đổi, đắp hoặc dán lại.
Hư hỏng do ảnh hưởng từ các yếu tố bên ngoài như tình trạng của đường hoặc các bề mặt tiếp xúc khác, những yếu tố khác như hóa chất, ô nhiễm, mưa axit, mưa đá, cát, không khí, muối, đá, hỏa hoạn, thiên tai, v.v... Các vấn đề phát sinh khác mà không thể chứng minh được là có trực tiếp hay gián tiếp liên quan đến vấn đề chất lượng lốp như chi phí cho việc không sử dụng xe, tiêu tốn thời gian, nhiên liệu, điện thoại, chỗ ở hoặc các phát sinh khác.
  ```

#### Chunk `url_7f921895430c_vf-8_c012`
- **Section**: VF 8
- **Codes**: MPV
- **Content Preview**:
  ```
  ### VF 8

structure_block_type: product_card
- structure_block_id: dom_c15be9997ba8
- structure_dedupe_hash: 51140220e7f5
- structure_attributes: class='field__item--content'
- content: Phụ tùng xe mới Bảo hành giới hạn Pin cao áp Pin cao áp mua theo xe mới, sử dụng tiêu chuẩn: Áp dụng cho VF 8, VF 9, Lạc Hồng LX 900, Lạc Hồng 900S, Lạc Hồng 800S: được bảo hành 10 năm hoặc 200.000 km tùy theo điều kiện nào đến trước. Áp dụng cho VF 3, VF 5, VF 6, VF 7, VF 8 The All New, VF Minio Green, VF Herio Green, VF MPV 7, VF e34, VF Nerio Green, VF Limo Green: được bảo hành 8 năm hoặc 160.000 km tùy điều kiện nào đến trước. Áp dụng cho VF EC Van: được bảo hành 7 năm hoặc 160.000 km tùy điều kiện nào đến trước. Pin cao áp mua theo xe mới, xe đang hoặc đã từng sử dụng cho mục đích dịch vụ thương mại: Áp dụng cho VF 3, VF 7, VF 8, VF 9: được bảo hành 3 năm hoặc 100.000 km tùy điều kiện nào đến trước. Đối với xe đã từng được sử dụng cho mục đích dịch vụ thương mại, chính sách bảo hành pin áp dụng cho xe sử dụng cho mục đích dịch vụ thương mại sẽ tiếp tục được duy trì và áp dụng kể cả trong trường hợp chuyển nhượng xe cho chủ sở hữu mới hoặc xe không còn được sử dụng cho mục đích dịch vụ thương mại. Ắc - quy Ô tô xăng: 1 năm hoặc 20.000 km tùy thuộc điều kiện nào đến trước. Ô tô điện: 1 năm (không giới hạn quãng đường sử dụng). Gỉ sét Điều kiện sử dụng tiêu chuẩn: Bảo hành gỉ sét có thời hạn bảo hành là 10 năm từ ngày kích hoạt bảo hành xe (không giới hạn quãng đường sử dụng) với xe VF 8, VF 9, Lạc Hồng LX 900, Lạc Hồng 900S, Lạc Hồng 800S. sử dụng trong điều kiện tiêu chuẩn, áp dụng với tấm kim loại bị xuyên thủng trong điều kiện hoạt động bình thường mà nguyên nhân do lỗi nguyên vật liệu hoặc lỗi lắp ráp của nhà sản xuất, và 7 năm không giới hạn số km với xe VF 3, VF 5, VF 6, VF 7, VF 8 The All New, VF Minio Green, VF Herio Green, VF MPV 7, VF e34, VF Nerio Green, VF Limo Green và 5 năm không giới hạn số km với xe VF EC Van. Sử dụng cho dịch vụ thương mại: Bảo hành là 3 năm hoặc 100.000 km với xe đang hoặc đã từng sử dụng cho mục đích dịch vụ thương mại đối với VF 3, VF 7, VF 8, VF 9.
  ```

#### Chunk `url_7f921895430c_vf-8_c013`
- **Section**: VF 8
- **Codes**: MPV
- **Content Preview**:
  ```
  ### VF 8

content: Phụ tùng xe mới Bảo hành giới hạn Pin cao áp Pin cao áp mua theo xe mới, sử dụng tiêu chuẩn: Áp dụng cho VF 8, VF 9, Lạc Hồng LX 900, Lạc Hồng 900S, Lạc Hồng 800S: được bảo hành 10 năm hoặc 200.000 km tùy theo điều kiện nào đến trước. Áp dụng cho VF 3, VF 5, VF 6, VF 7, VF 8 The All New, VF Minio Green, VF Herio Green, VF MPV 7, VF e34, VF Nerio Green, VF Limo Green: được bảo hành 8 năm hoặc 160.000 km tùy điều kiện nào đến trước. Áp dụng cho VF EC Van: được bảo hành 7 năm hoặc 160.000 km tùy điều kiện nào đến trước. Pin cao áp mua theo xe mới, xe đang hoặc đã từng sử dụng cho mục đích dịch vụ thương mại: Áp dụng cho VF 3, VF 7, VF 8, VF 9: được bảo hành 3 năm hoặc 100.000 km tùy điều kiện nào đến trước. Đối với xe đã từng được sử dụng cho mục đích dịch vụ thương mại, chính sách bảo hành pin áp dụng cho xe sử dụng cho mục đích dịch vụ thương mại sẽ tiếp tục được duy trì và áp dụng kể cả trong trường hợp chuyển nhượng xe cho chủ sở hữu mới hoặc xe không còn được sử dụng cho mục đích dịch vụ thương mại. Ắc - quy Ô tô xăng: 1 năm hoặc 20.000 km tùy thuộc điều kiện nào đến trước. Ô tô điện: 1 năm (không giới hạn quãng đường sử dụng). Gỉ sét Điều kiện sử dụng tiêu chuẩn: Bảo hành gỉ sét có thời hạn bảo hành là 10 năm từ ngày kích hoạt bảo hành xe (không giới hạn quãng đường sử dụng) với xe VF 8, VF 9, Lạc Hồng LX 900, Lạc Hồng 900S, Lạc Hồng 800S. sử dụng trong điều kiện tiêu chuẩn, áp dụng với tấm kim loại bị xuyên thủng trong điều kiện hoạt động bình thường mà nguyên nhân do lỗi nguyên vật liệu hoặc lỗi lắp ráp của nhà sản xuất, và 7 năm không giới hạn số km với xe VF 3, VF 5, VF 6, VF 7, VF 8 The All New, VF Minio Green, VF Herio Green, VF MPV 7, VF e34, VF Nerio Green, VF Limo Green và 5 năm không giới hạn số km với xe VF EC Van. Sử dụng cho dịch vụ thương mại: Bảo hành là 3 năm hoặc 100.000 km với xe đang hoặc đã từng sử dụng cho mục đích dịch vụ thương mại đối với VF 3, VF 7, VF 8, VF 9.
Sơn ngoại thất Điều kiện sử dụng tiêu chuẩn: Áp dụng cho VF 8, VF 9, Lạc Hồng LX 900, Lạc Hồng 900S, Lạc Hồng 800S: được bảo hành 10 năm không giới hạn số km. Áp dụng cho VF 3, VF 5, VF 6, VF 7, VF 8 The All New, VF Minio Green, VF Herio Green, VF MPV 7, VF e34, VF Nerio Green, VF Limo Green: được bảo hành 7 năm không giới hạn số km. Áp dụng cho VF EC Van: được bảo hành 5 năm không giới hạn số km. Sử dụng cho dịch vụ thương mại: 3 năm hoặc 100.000 km tùy điều kiện nào đến trước áp dụng cho VF 3, VF 7, VF 8, VF 9. Các bộ phận treo Sử dụng trong điều kiện tiêu chuẩn: Các bộ phận treo (Bộ giảm xóc, Thanh ổn định, Cụm liên kết trên, Cánh tay điều khiển dưới, Khớp bi, Lắp thanh chống trên) được bảo hành 5 năm hoặc 130.000 km tùy điều kiện nào đến trước. Sử dụng cho mục đích dịch vụ thương mại: Áp dụng cho VF 3, VF 7, VF 8, VF 9, thời hạn bảo hành là 3 năm hoặc 100.000 km. Lốp xe Lốp được trang bị theo xe (bao gồm cả lốp dự phòng nếu có) được bảo hành đối với các khuyết tật, hư hỏng do lỗi nguyên vật liệu hoặc lỗi trong quá trình sản xuất, lưu kho của nhà sản xuất lốp được tính kể từ ngày kích hoạt bảo hành xe. Chi tiết bảo hành đối với từng loại sản phẩm như sau: Ô tô xăng: 5 năm (không giới hạn quãng đường sử dụng). Ô tô điện: Bảo hành bởi nhà sản xuất lốp xe. Nếu nhà sản xuất lốp cung cấp dịch vụ bảo hành tại thị trường Việt Nam, lốp xe sẽ được bảo hành hành theo chính sách riêng của nhà sản xuất lốp xe. Những hạng mục, hư hỏng không thuộc bảo hành lốp: Hư hỏng do lốp xe bị phá hoại, tai nạn hoặc va chạm. Hư hỏng do lốp bị lạm dụng trong quá trình sử dụng. Hư hỏng do lốp không được bảo dưỡng hoặc vận hành với áp suất lốp không tiêu chuẩn. Lốp là chi tiết hao mòn theo thời gian và quãng đường sử dụng, các hao mòn này không thuộc phạm vi bảo hành. Các hư hỏng được đánh giá không ảnh hưởng đến chất lượng, hiệu suất hoặc chức năng của lốp. Sử dụng lốp sai so với mục đích khuyến nghị của nhà sản xuất. Lốp đã được sửa chữa, thay đổi, đắp hoặc dán lại.
  ```

#### Chunk `url_7f921895430c_vf-8_c014`
- **Section**: VF 8
- **Codes**: MPV
- **Content Preview**:
  ```
  ### VF 8

ngoại thất Điều kiện sử dụng tiêu chuẩn: Áp dụng cho VF 8, VF 9, Lạc Hồng LX 900, Lạc Hồng 900S, Lạc Hồng 800S: được bảo hành 10 năm không giới hạn số km. Áp dụng cho VF 3, VF 5, VF 6, VF 7, VF 8 The All New, VF Minio Green, VF Herio Green, VF MPV 7, VF e34, VF Nerio Green, VF Limo Green: được bảo hành 7 năm không giới hạn số km. Áp dụng cho VF EC Van: được bảo hành 5 năm không giới hạn số km. Sử dụng cho dịch vụ thương mại: 3 năm hoặc 100.000 km tùy điều kiện nào đến trước áp dụng cho VF 3, VF 7, VF 8, VF 9. Các bộ phận treo Sử dụng trong điều kiện tiêu chuẩn: Các bộ phận treo (Bộ giảm xóc, Thanh ổn định, Cụm liên kết trên, Cánh tay điều khiển dưới, Khớp bi, Lắp thanh chống trên) được bảo hành 5 năm hoặc 130.000 km tùy điều kiện nào đến trước. Sử dụng cho mục đích dịch vụ thương mại: Áp dụng cho VF 3, VF 7, VF 8, VF 9, thời hạn bảo hành là 3 năm hoặc 100.000 km. Lốp xe Lốp được trang bị theo xe (bao gồm cả lốp dự phòng nếu có) được bảo hành đối với các khuyết tật, hư hỏng do lỗi nguyên vật liệu hoặc lỗi trong quá trình sản xuất, lưu kho của nhà sản xuất lốp được tính kể từ ngày kích hoạt bảo hành xe. Chi tiết bảo hành đối với từng loại sản phẩm như sau: Ô tô xăng: 5 năm (không giới hạn quãng đường sử dụng). Ô tô điện: Bảo hành bởi nhà sản xuất lốp xe. Nếu nhà sản xuất lốp cung cấp dịch vụ bảo hành tại thị trường Việt Nam, lốp xe sẽ được bảo hành hành theo chính sách riêng của nhà sản xuất lốp xe. Những hạng mục, hư hỏng không thuộc bảo hành lốp: Hư hỏng do lốp xe bị phá hoại, tai nạn hoặc va chạm. Hư hỏng do lốp bị lạm dụng trong quá trình sử dụng. Hư hỏng do lốp không được bảo dưỡng hoặc vận hành với áp suất lốp không tiêu chuẩn. Lốp là chi tiết hao mòn theo thời gian và quãng đường sử dụng, các hao mòn này không thuộc phạm vi bảo hành. Các hư hỏng được đánh giá không ảnh hưởng đến chất lượng, hiệu suất hoặc chức năng của lốp. Sử dụng lốp sai so với mục đích khuyến nghị của nhà sản xuất. Lốp đã được sửa chữa, thay đổi, đắp hoặc dán lại.
Hư hỏng do ảnh hưởng từ các yếu tố bên ngoài như tình trạng của đường hoặc các bề mặt tiếp xúc khác, những yếu tố khác như hóa chất, ô nhiễm, mưa axit, mưa đá, cát, không khí, muối, đá, hỏa hoạn, thiên tai, v.v... Các vấn đề phát sinh khác mà không thể chứng minh được là có trực tiếp hay gián tiếp liên quan đến vấn đề chất lượng lốp như chi phí cho việc không sử dụng xe, tiêu tốn thời gian, nhiên liệu, điện thoại, chỗ ở hoặc các phát sinh khác.
  ```

#### Chunk `url_7f921895430c_vf-8_c016`
- **Section**: VF 8
- **Codes**: MPV
- **Content Preview**:
  ```
  ### VF 8

structure_block_type: product_card
- structure_block_id: dom_9b4c832d4376
- structure_dedupe_hash: 4051ea06447d
- structure_attributes: class='paragraph paragraph--type--dvhm-warranty-coverrage-sub paragraph--view-mode--default'
- content: Phụ tùng xe mới Bảo hành giới hạn Pin cao áp Pin cao áp mua theo xe mới, sử dụng tiêu chuẩn: Áp dụng cho VF 8, VF 9, Lạc Hồng LX 900, Lạc Hồng 900S, Lạc Hồng 800S: được bảo hành 10 năm hoặc 200.000 km tùy theo điều kiện nào đến trước. Áp dụng cho VF 3, VF 5, VF 6, VF 7, VF 8 The All New, VF Minio Green, VF Herio Green, VF MPV 7, VF e34, VF Nerio Green, VF Limo Green: được bảo hành 8 năm hoặc 160.000 km tùy điều kiện nào đến trước. Áp dụng cho VF EC Van: được bảo hành 7 năm hoặc 160.000 km tùy điều kiện nào đến trước. Pin cao áp mua theo xe mới, xe đang hoặc đã từng sử dụng cho mục đích dịch vụ thương mại: Áp dụng cho VF 3, VF 7, VF 8, VF 9: được bảo hành 3 năm hoặc 100.000 km tùy điều kiện nào đến trước. Đối với xe đã từng được sử dụng cho mục đích dịch vụ thương mại, chính sách bảo hành pin áp dụng cho xe sử dụng cho mục đích dịch vụ thương mại sẽ tiếp tục được duy trì và áp dụng kể cả trong trường hợp chuyển nhượng xe cho chủ sở hữu mới hoặc xe không còn được sử dụng cho mục đích dịch vụ thương mại. Ắc - quy Ô tô xăng: 1 năm hoặc 20.000 km tùy thuộc điều kiện nào đến trước. Ô tô điện: 1 năm (không giới hạn quãng đường sử dụng). Gỉ sét Điều kiện sử dụng tiêu chuẩn: Bảo hành gỉ sét có thời hạn bảo hành là 10 năm từ ngày kích hoạt bảo hành xe (không giới hạn quãng đường sử dụng) với xe VF 8, VF 9, Lạc Hồng LX 900, Lạc Hồng 900S, Lạc Hồng 800S. sử dụng trong điều kiện tiêu chuẩn, áp dụng với tấm kim loại bị xuyên thủng trong điều kiện hoạt động bình thường mà nguyên nhân do lỗi nguyên vật liệu hoặc lỗi lắp ráp của nhà sản xuất, và 7 năm không giới hạn số km với xe VF 3, VF 5, VF 6, VF 7, VF 8 The All New, VF Minio Green, VF Herio Green, VF MPV 7, VF e34, VF Nerio Green, VF Limo Green và 5 năm không giới hạn số km với xe VF EC Van. Sử dụng cho dịch vụ thương mại: Bảo hành là 3 năm hoặc 100.000 km với xe đang hoặc đã từng sử dụng cho mục đích dịch vụ thương mại đối với VF 3, VF 7, VF 8, VF 9.
  ```

#### Chunk `url_7f921895430c_vf-8_c017`
- **Section**: VF 8
- **Codes**: MPV
- **Content Preview**:
  ```
  ### VF 8

content: Phụ tùng xe mới Bảo hành giới hạn Pin cao áp Pin cao áp mua theo xe mới, sử dụng tiêu chuẩn: Áp dụng cho VF 8, VF 9, Lạc Hồng LX 900, Lạc Hồng 900S, Lạc Hồng 800S: được bảo hành 10 năm hoặc 200.000 km tùy theo điều kiện nào đến trước. Áp dụng cho VF 3, VF 5, VF 6, VF 7, VF 8 The All New, VF Minio Green, VF Herio Green, VF MPV 7, VF e34, VF Nerio Green, VF Limo Green: được bảo hành 8 năm hoặc 160.000 km tùy điều kiện nào đến trước. Áp dụng cho VF EC Van: được bảo hành 7 năm hoặc 160.000 km tùy điều kiện nào đến trước. Pin cao áp mua theo xe mới, xe đang hoặc đã từng sử dụng cho mục đích dịch vụ thương mại: Áp dụng cho VF 3, VF 7, VF 8, VF 9: được bảo hành 3 năm hoặc 100.000 km tùy điều kiện nào đến trước. Đối với xe đã từng được sử dụng cho mục đích dịch vụ thương mại, chính sách bảo hành pin áp dụng cho xe sử dụng cho mục đích dịch vụ thương mại sẽ tiếp tục được duy trì và áp dụng kể cả trong trường hợp chuyển nhượng xe cho chủ sở hữu mới hoặc xe không còn được sử dụng cho mục đích dịch vụ thương mại. Ắc - quy Ô tô xăng: 1 năm hoặc 20.000 km tùy thuộc điều kiện nào đến trước. Ô tô điện: 1 năm (không giới hạn quãng đường sử dụng). Gỉ sét Điều kiện sử dụng tiêu chuẩn: Bảo hành gỉ sét có thời hạn bảo hành là 10 năm từ ngày kích hoạt bảo hành xe (không giới hạn quãng đường sử dụng) với xe VF 8, VF 9, Lạc Hồng LX 900, Lạc Hồng 900S, Lạc Hồng 800S. sử dụng trong điều kiện tiêu chuẩn, áp dụng với tấm kim loại bị xuyên thủng trong điều kiện hoạt động bình thường mà nguyên nhân do lỗi nguyên vật liệu hoặc lỗi lắp ráp của nhà sản xuất, và 7 năm không giới hạn số km với xe VF 3, VF 5, VF 6, VF 7, VF 8 The All New, VF Minio Green, VF Herio Green, VF MPV 7, VF e34, VF Nerio Green, VF Limo Green và 5 năm không giới hạn số km với xe VF EC Van. Sử dụng cho dịch vụ thương mại: Bảo hành là 3 năm hoặc 100.000 km với xe đang hoặc đã từng sử dụng cho mục đích dịch vụ thương mại đối với VF 3, VF 7, VF 8, VF 9.
Sơn ngoại thất Điều kiện sử dụng tiêu chuẩn: Áp dụng cho VF 8, VF 9, Lạc Hồng LX 900, Lạc Hồng 900S, Lạc Hồng 800S: được bảo hành 10 năm không giới hạn số km. Áp dụng cho VF 3, VF 5, VF 6, VF 7, VF 8 The All New, VF Minio Green, VF Herio Green, VF MPV 7, VF e34, VF Nerio Green, VF Limo Green: được bảo hành 7 năm không giới hạn số km. Áp dụng cho VF EC Van: được bảo hành 5 năm không giới hạn số km. Sử dụng cho dịch vụ thương mại: 3 năm hoặc 100.000 km tùy điều kiện nào đến trước áp dụng cho VF 3, VF 7, VF 8, VF 9. Các bộ phận treo Sử dụng trong điều kiện tiêu chuẩn: Các bộ phận treo (Bộ giảm xóc, Thanh ổn định, Cụm liên kết trên, Cánh tay điều khiển dưới, Khớp bi, Lắp thanh chống trên) được bảo hành 5 năm hoặc 130.000 km tùy điều kiện nào đến trước. Sử dụng cho mục đích dịch vụ thương mại: Áp dụng cho VF 3, VF 7, VF 8, VF 9, thời hạn bảo hành là 3 năm hoặc 100.000 km. Lốp xe Lốp được trang bị theo xe (bao gồm cả lốp dự phòng nếu có) được bảo hành đối với các khuyết tật, hư hỏng do lỗi nguyên vật liệu hoặc lỗi trong quá trình sản xuất, lưu kho của nhà sản xuất lốp được tính kể từ ngày kích hoạt bảo hành xe. Chi tiết bảo hành đối với từng loại sản phẩm như sau: Ô tô xăng: 5 năm (không giới hạn quãng đường sử dụng). Ô tô điện: Bảo hành bởi nhà sản xuất lốp xe. Nếu nhà sản xuất lốp cung cấp dịch vụ bảo hành tại thị trường Việt Nam, lốp xe sẽ được bảo hành hành theo chính sách riêng của nhà sản xuất lốp xe. Những hạng mục, hư hỏng không thuộc bảo hành lốp: Hư hỏng do lốp xe bị phá hoại, tai nạn hoặc va chạm. Hư hỏng do lốp bị lạm dụng trong quá trình sử dụng. Hư hỏng do lốp không được bảo dưỡng hoặc vận hành với áp suất lốp không tiêu chuẩn. Lốp là chi tiết hao mòn theo thời gian và quãng đường sử dụng, các hao mòn này không thuộc phạm vi bảo hành. Các hư hỏng được đánh giá không ảnh hưởng đến chất lượng, hiệu suất hoặc chức năng của lốp. Sử dụng lốp sai so với mục đích khuyến nghị của nhà sản xuất. Lốp đã được sửa chữa, thay đổi, đắp hoặc dán lại.
  ```

#### Chunk `url_7f921895430c_vf-8_c018`
- **Section**: VF 8
- **Codes**: MPV
- **Content Preview**:
  ```
  ### VF 8

ngoại thất Điều kiện sử dụng tiêu chuẩn: Áp dụng cho VF 8, VF 9, Lạc Hồng LX 900, Lạc Hồng 900S, Lạc Hồng 800S: được bảo hành 10 năm không giới hạn số km. Áp dụng cho VF 3, VF 5, VF 6, VF 7, VF 8 The All New, VF Minio Green, VF Herio Green, VF MPV 7, VF e34, VF Nerio Green, VF Limo Green: được bảo hành 7 năm không giới hạn số km. Áp dụng cho VF EC Van: được bảo hành 5 năm không giới hạn số km. Sử dụng cho dịch vụ thương mại: 3 năm hoặc 100.000 km tùy điều kiện nào đến trước áp dụng cho VF 3, VF 7, VF 8, VF 9. Các bộ phận treo Sử dụng trong điều kiện tiêu chuẩn: Các bộ phận treo (Bộ giảm xóc, Thanh ổn định, Cụm liên kết trên, Cánh tay điều khiển dưới, Khớp bi, Lắp thanh chống trên) được bảo hành 5 năm hoặc 130.000 km tùy điều kiện nào đến trước. Sử dụng cho mục đích dịch vụ thương mại: Áp dụng cho VF 3, VF 7, VF 8, VF 9, thời hạn bảo hành là 3 năm hoặc 100.000 km. Lốp xe Lốp được trang bị theo xe (bao gồm cả lốp dự phòng nếu có) được bảo hành đối với các khuyết tật, hư hỏng do lỗi nguyên vật liệu hoặc lỗi trong quá trình sản xuất, lưu kho của nhà sản xuất lốp được tính kể từ ngày kích hoạt bảo hành xe. Chi tiết bảo hành đối với từng loại sản phẩm như sau: Ô tô xăng: 5 năm (không giới hạn quãng đường sử dụng). Ô tô điện: Bảo hành bởi nhà sản xuất lốp xe. Nếu nhà sản xuất lốp cung cấp dịch vụ bảo hành tại thị trường Việt Nam, lốp xe sẽ được bảo hành hành theo chính sách riêng của nhà sản xuất lốp xe. Những hạng mục, hư hỏng không thuộc bảo hành lốp: Hư hỏng do lốp xe bị phá hoại, tai nạn hoặc va chạm. Hư hỏng do lốp bị lạm dụng trong quá trình sử dụng. Hư hỏng do lốp không được bảo dưỡng hoặc vận hành với áp suất lốp không tiêu chuẩn. Lốp là chi tiết hao mòn theo thời gian và quãng đường sử dụng, các hao mòn này không thuộc phạm vi bảo hành. Các hư hỏng được đánh giá không ảnh hưởng đến chất lượng, hiệu suất hoặc chức năng của lốp. Sử dụng lốp sai so với mục đích khuyến nghị của nhà sản xuất. Lốp đã được sửa chữa, thay đổi, đắp hoặc dán lại.
Hư hỏng do ảnh hưởng từ các yếu tố bên ngoài như tình trạng của đường hoặc các bề mặt tiếp xúc khác, những yếu tố khác như hóa chất, ô nhiễm, mưa axit, mưa đá, cát, không khí, muối, đá, hỏa hoạn, thiên tai, v.v... Các vấn đề phát sinh khác mà không thể chứng minh được là có trực tiếp hay gián tiếp liên quan đến vấn đề chất lượng lốp như chi phí cho việc không sử dụng xe, tiêu tốn thời gian, nhiên liệu, điện thoại, chỗ ở hoặc các phát sinh khác. Phụ tùng xe mới Bảo hành giới hạn
  ```

#### Chunk `url_7f921895430c_th-ng-tin-b-o-h-nh-vinfast-product-card_c003`
- **Section**: Thông tin bảo hành | VinFast product card
- **Codes**: XDV
- **Content Preview**:
  ```
  ### Thông tin bảo hành | VinFast product card

- structure_block_type: product_card
- structure_block_id: dom_732fdb574b33
- structure_dedupe_hash: cc3744017470
- structure_attributes: class='field__item'
- content: Pin do khách hàng mua và được lắp đặt lên xe tại XDV/ĐLPP của VinFast sau thời điểm giao xe có thời hạn bảo hành là 4 năm hoặc 80.000 km tùy theo điều kiện nào đến trước kể từ ngày mua.

### Thông tin bảo hành | VinFast product card

- structure_block_type: product_card
- structure_block_id: dom_f04271fec611
- structure_dedupe_hash: 265fed41a448
- structure_attributes: class='paragraph paragraph--type--dvhm-warranty-coverrage-scontent paragraph--view-mode--default'
- content: Pin cao áp: Pin do khách hàng mua và được lắp đặt lên xe tại XDV/ĐLPP của VinFast sau thời điểm giao xe có thời hạn bảo hành là 4 năm hoặc 80.000 km tùy theo điều kiện nào đến trước kể từ ngày mua.
  ```

#### Chunk `url_7f921895430c_th-ng-tin-b-o-h-nh-vinfast-product-card_c004`
- **Section**: Thông tin bảo hành | VinFast product card
- **Codes**: NPP, XDV
- **Content Preview**:
  ```
  ### Thông tin bảo hành | VinFast product card

- structure_block_type: product_card
- structure_block_id: dom_a3882252ce77
- structure_dedupe_hash: bdbd3cd294ac
- structure_attributes: class='field__items'
- content: Phụ tùng thay thế cho xe của khách hàng trong quá trình sửa chữa tại XDV/NPP của VinFast do khách hàng chịu chi phí, sẽ có thời hạn bảo hành như sau: Phụ tùng (không bao gồm Ắc Quy 12V và Pin cao áp): Ô tô xăng: bao gồm Fadil, Lux A, Lux SA, President: 12 tháng hoặc 20.000 km tùy thuộc điều kiện nào đến trước từ ngày hoàn thành sửa chữa. Ô tô điện: 2 năm hoặc 40.000 km tùy theo điều kiện nào đến trước tính từ ngày mua. Phụ tùng mua nhưng không được thay thế tại XDV/ NPP của VinFast sẽ không được bảo hành theo chính sách. Để nhận được chế độ bảo hành phụ tùng, khách hàng có trách nhiệm lưu trữ hồ sơ (lệnh sửa chữa, hóa đơn, v.v.) cho những lần thay thế phụ tùng. Quý khách hàng vui lòng tham khảo tại Sổ bảo hành để biết thêm các thông tin bảo hành chi tiết. Pin cao áp: Pin do khách hàng mua và được lắp đặt lên xe tại XDV/ĐLPP của VinFast sau thời điểm giao xe có thời hạn bảo hành là 4 năm hoặc 80.000 km tùy theo điều kiện nào đến trước kể từ ngày mua. Ắc quy 12V: Ô tô xăng: 1 năm hoặc 20.000 km tùy thuộc điều kiện nào đến trước. Ô tô điện: 1 năm (không giới hạn quãng đường sử dụng).
  ```

#### Chunk `url_7f921895430c_th-ng-tin-b-o-h-nh-vinfast-product-card_c005`
- **Section**: Thông tin bảo hành | VinFast product card
- **Codes**: NPP, XDV
- **Content Preview**:
  ```
  ### Thông tin bảo hành | VinFast product card

- structure_block_type: product_card
- structure_block_id: dom_7001df207892
- structure_dedupe_hash: f5dff5b744c7
- structure_attributes: class='field__item--content'
- content: Bảo hành phụ tùng Thay thế chính hãng Phụ tùng thay thế cho xe của khách hàng trong quá trình sửa chữa tại XDV/NPP của VinFast do khách hàng chịu chi phí, sẽ có thời hạn bảo hành như sau: Phụ tùng (không bao gồm Ắc Quy 12V và Pin cao áp): Ô tô xăng: bao gồm Fadil, Lux A, Lux SA, President: 12 tháng hoặc 20.000 km tùy thuộc điều kiện nào đến trước từ ngày hoàn thành sửa chữa. Ô tô điện: 2 năm hoặc 40.000 km tùy theo điều kiện nào đến trước tính từ ngày mua. Phụ tùng mua nhưng không được thay thế tại XDV/ NPP của VinFast sẽ không được bảo hành theo chính sách. Để nhận được chế độ bảo hành phụ tùng, khách hàng có trách nhiệm lưu trữ hồ sơ (lệnh sửa chữa, hóa đơn, v.v.) cho những lần thay thế phụ tùng. Quý khách hàng vui lòng tham khảo tại Sổ bảo hành để biết thêm các thông tin bảo hành chi tiết. Pin cao áp: Pin do khách hàng mua và được lắp đặt lên xe tại XDV/ĐLPP của VinFast sau thời điểm giao xe có thời hạn bảo hành là 4 năm hoặc 80.000 km tùy theo điều kiện nào đến trước kể từ ngày mua. Ắc quy 12V: Ô tô xăng: 1 năm hoặc 20.000 km tùy thuộc điều kiện nào đến trước. Ô tô điện: 1 năm (không giới hạn quãng đường sử dụng).
  ```

#### Chunk `url_7f921895430c_th-ng-tin-b-o-h-nh-vinfast-product-card_c006`
- **Section**: Thông tin bảo hành | VinFast product card
- **Codes**: NPP, XDV
- **Content Preview**:
  ```
  ### Thông tin bảo hành | VinFast product card

- structure_block_type: product_card
- structure_block_id: dom_ae3badfdfc29
- structure_dedupe_hash: 19e447839a5a
- structure_attributes: class='paragraph paragraph--type--dvhm-warranty-coverrage-sub paragraph--view-mode--default'
- content: Bảo hành phụ tùng Thay thế chính hãng Phụ tùng thay thế cho xe của khách hàng trong quá trình sửa chữa tại XDV/NPP của VinFast do khách hàng chịu chi phí, sẽ có thời hạn bảo hành như sau: Phụ tùng (không bao gồm Ắc Quy 12V và Pin cao áp): Ô tô xăng: bao gồm Fadil, Lux A, Lux SA, President: 12 tháng hoặc 20.000 km tùy thuộc điều kiện nào đến trước từ ngày hoàn thành sửa chữa. Ô tô điện: 2 năm hoặc 40.000 km tùy theo điều kiện nào đến trước tính từ ngày mua. Phụ tùng mua nhưng không được thay thế tại XDV/ NPP của VinFast sẽ không được bảo hành theo chính sách. Để nhận được chế độ bảo hành phụ tùng, khách hàng có trách nhiệm lưu trữ hồ sơ (lệnh sửa chữa, hóa đơn, v.v.) cho những lần thay thế phụ tùng. Quý khách hàng vui lòng tham khảo tại Sổ bảo hành để biết thêm các thông tin bảo hành chi tiết. Pin cao áp: Pin do khách hàng mua và được lắp đặt lên xe tại XDV/ĐLPP của VinFast sau thời điểm giao xe có thời hạn bảo hành là 4 năm hoặc 80.000 km tùy theo điều kiện nào đến trước kể từ ngày mua. Ắc quy 12V: Ô tô xăng: 1 năm hoặc 20.000 km tùy thuộc điều kiện nào đến trước. Ô tô điện: 1 năm (không giới hạn quãng đường sử dụng). Bảo hành phụ tùng Thay thế chính hãng
  ```

#### Chunk `url_7f921895430c_th-ng-tin-b-o-h-nh-vinfast-product-card_c007`
- **Section**: Thông tin bảo hành | VinFast product card
- **Codes**: XDV
- **Content Preview**:
  ```
  ### Thông tin bảo hành | VinFast product card

- structure_block_type: product_card
- structure_block_id: dom_5c10d2225530
- structure_dedupe_hash: ab0080f3946a
- content: Pin cao áp: Pin do khách hàng mua và được lắp đặt lên xe tại XDV/ĐLPP của VinFast sau thời điểm giao xe có thời hạn bảo hành là 4 năm (không giới hạn quãng đường sử dụng) tính từ ngày mua.

### Thông tin bảo hành | VinFast product card

- structure_block_type: product_card
- structure_block_id: dom_11be0a3dc6e4
- structure_dedupe_hash: 47759c4ed929
- structure_attributes: class='field__item'
- content: Phụ tùng thay thế cho xe của khách hàng trong quá trình sửa chữa tại XDV/ĐLPP của VinFast do khách hàng chịu chi phí (không bao gồm pin cao áp) sẽ có thời hạn bảo hành 1 năm (không giới hạn quãng đường sử dụng) tính từ ngày mua. Pin cao áp: Pin do khách hàng mua và được lắp đặt lên xe tại XDV/ĐLPP của VinFast sau thời điểm giao xe có thời hạn bảo hành là 4 năm (không giới hạn quãng đường sử dụng) tính từ ngày mua.
  ```
