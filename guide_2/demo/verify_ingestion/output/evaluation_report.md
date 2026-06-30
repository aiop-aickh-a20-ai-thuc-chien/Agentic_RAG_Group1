# Local Ground-Truth Verification Report

This report was generated locally without sending content to an LLM.

## Summary

- Text similarity ratio: `0.0138`
- Ground truth: 1715 words, 235 lines
- Actual output: 2002 words, 239 lines
- Evidence artifacts searched: 17

## Primary URL routing signal

- Source URL path: `/vn_vi/dat-coc-o-to-dien-vinfast.html`
- Primary routing parameter: `modelId`
- Primary model ID: `Products-Car-VF9`
- Model ID present in actual markdown: `False`
- Model ID present in evidence corpus: `True`
- Model ID present in ground truth: `True`

`modelId` is treated as the page-routing variable for VinFast model-selector URLs, so changing it to VF3/VF5/VF6/VF7/etc. should change the target page being verified.
- Structured key-fact coverage: 225/243 (`0.9259`)
- Structured coverage verdict: `pass`

## Missing structured ground-truth facts

- `page.title`: Xe điện VinFast VF 9 - Giá bán và chương trình ưu đãi | VinFast
- `vehicle.type`: eSUV – SUV điện 7 chỗ hạng sang
- `vehicle.tagline`: Sự Lựa Chọn Của Người Thành Đạt, Tiên Phong
- `vehicle.key_specs.range_note`: Tiêu chuẩn WLTP, phiên bản Eco pin CATL
- `vehicle.key_specs.warranty`: 200.000 km hoặc 10 năm
- `rolling_cost_popup.purpose`: Hiển thị chi phí lăn bánh (on-road cost breakdown)
- `configured_prices.note`: Giá xe = Giá niêm yết phiên bản + Phụ thu màu (nếu có). Đã bao gồm VAT.
- `configured_prices.VF9_Eco.combinations[5].total_price_formatted`: 1.511.000.000 VNĐ
- `configured_prices.VF9_Eco.combinations[6].total_price_formatted`: 1.511.000.000 VNĐ
- `configured_prices.VF9_Plus_7_cho.combinations[5].total_price_formatted`: 1.711.000.000 VNĐ
- `configured_prices.VF9_Plus_7_cho.combinations[6].total_price_formatted`: 1.711.000.000 VNĐ
- `configured_prices.VF9_Plus_ghe_co_truong.combinations[5].total_price_formatted`: 1.743.000.000 VNĐ
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
- ... and 205 more

## Generated artifacts

- JSON summary: `guide_2/demo/verify_ingestion/output/comparison_summary.json`
- Unified diff: `guide_2/demo/verify_ingestion/output/ground_truth_diff.patch`

Use the diff for line-level review, and use the structured-fact section as a fast smoke test for whether important ground-truth values appeared in the ingestion output.


## Ingested Chunks Verification (Colors & Fallbacks)

- **Total Chunks Loaded**: `12`
- **Chunks Containing Color/Asset Data**: `11`

| Chunk ID | Section | Detected Codes | Images Fallback? | Preview |
| --- | --- | --- | --- | --- |
| `url_2a7cf685fe11_general-info_c001` | General Info | `MPV` | No | ## General Info  - **Vehicle Models**: VF 3, VF 5, VF 6, VF 7, VF 8, VF 9, MPV 7 - **Categories**: Personal vehicles, Se... |
| `url_2a7cf685fe11_specifications_c001` | Specifications | `NEDC` | No | ## Specifications  | Specification                        | Value                                   | |-----------------... |
| `url_2a7cf685fe11_pricing_c001` | Pricing | `MPV`, `SMART`, `TBD` | No | ### Pricing  | Model                | Price (VNĐ)          | |----------------------|----------------------| | VF 3 Plus... |
| `url_2a7cf685fe11_estimated-costs_c001` | Estimated Costs | `TBD` | No | ### Estimated Costs  | Item                                      | Cost (VNĐ)            | |----------------------------... |
| `url_2a7cf685fe11_ti-n-ch_c001` | Tiện ích | `MPV`, `SA2` | No | ### Tiện ích  - structure_block_type: product_card - structure_block_id: dom_06af2e28052e - structure_dedupe_hash: fafe6... |
| `url_2a7cf685fe11_ti-n-ch_c002` | Tiện ích | `MPV`, `SA2` | No | ### Tiện ích  structure_block_type: product_card - structure_block_id: dom_06af2e28052e - structure_dedupe_hash: fafe6e0... |
| `url_2a7cf685fe11_ti-n-ch_c003` | Tiện ích | `MPV`, `SA2` | No | ### Tiện ích  8 tháng 10 , 2021 Tiện ích Đăng ký lái thử So sánh xe Dự toán chi phí lăn bánh Dự toán vay trả góp Thẩm đị... |
| `url_2a7cf685fe11_structured-dom-content_c001` | Structured DOM Content | `DOM`, `MPV`, `NEDC`, `VF3` | No | ### Structured DOM Content  - structure_block_type: vehicle_card - structure_block_id: dom_2d9beffbc0d1 - structure_dedu... |
| `url_2a7cf685fe11_t-c-c-mua-xe-t-i-n-vinfast-online-vehicle-card_c001` | Đặt cọc mua xe ô tô điện VinFast online vehicle card | `NEDC`, `VF5` | No | ### Đặt cọc mua xe ô tô điện VinFast online vehicle card  - structure_block_type: vehicle_card - structure_block_id: dom... |
| `url_2a7cf685fe11_t-c-c-mua-xe-t-i-n-vinfast-online-vehicle-card_c002` | Đặt cọc mua xe ô tô điện VinFast online vehicle card | `NEDC`, `VFE34` | No | ### Đặt cọc mua xe ô tô điện VinFast online vehicle card  - structure_block_type: vehicle_card - structure_block_id: dom... |
| `url_2a7cf685fe11_t-c-c-mua-xe-t-i-n-vinfast-online-vehicle-card_c003` | Đặt cọc mua xe ô tô điện VinFast online vehicle card | `NEDC` | No | ### Đặt cọc mua xe ô tô điện VinFast online vehicle card  - structure_block_type: vehicle_card - structure_block_id: dom... |

### Detailed Ingested Color Chunks

#### Chunk `url_2a7cf685fe11_general-info_c001`
- **Section**: General Info
- **Codes**: MPV
- **Content Preview**:
  ```
  ## General Info

- **Vehicle Models**: VF 3, VF 5, VF 6, VF 7, VF 8, VF 9, MPV 7
- **Categories**: Personal vehicles, Service vehicles
  ```

#### Chunk `url_2a7cf685fe11_specifications_c001`
- **Section**: Specifications
- **Codes**: NEDC
- **Content Preview**:
  ```
  ## Specifications

| Specification                        | Value                                   |
|--------------------------------------|-----------------------------------------|
| Maximum Power                        | 30 kW                                  |
| Usable Battery Capacity               | 18.64 kWh                              |
| Driving Range (NEDC)                | 215 km                                  |
| Driving Range (Full Charge, NEDC)   | Up to 500.5 km                         |
| Wheelbase                            | 2,514 mm - 3,149 mm                   |
| Power Output                         | 134 hp / 100 kW - 402 hp / 300 kW     |
| Driving Range (1 Charge, NEDC)      | 326.4 km - 626 km                      |
  ```

#### Chunk `url_2a7cf685fe11_pricing_c001`
- **Section**: Pricing
- **Codes**: MPV, SMART, TBD
- **Content Preview**:
  ```
  ### Pricing

| Model                | Price (VNĐ)          |
|----------------------|----------------------|
| VF 3 Plus            | 323,000,000          |
| VF 3 Eco             | 310,000,000          |
| VF 5 Plus            | 537,000,000          |
| VF e34 SMART         | 710,000,000          |
| VF 6 Plus            | 745,000,000          |
| VF 6 Eco             | 689,000,000          |
| VF 7 Plus            | 889,000,000          |
| VF 7 Eco             | 801,000,000          |
| VF 8 Plus            | 1,199,000,000        |
| VF 8 Eco             | 1,019,000,000        |
| VF 9 Plus (7 seats) | TBD                  |
| VF 9 Eco             | TBD                  |
| VF MPV 7 Standard    | 819,000,000          |

### Configurable Options

| Option                          | Additional Cost (VNĐ) |
|---------------------------------|------------------------|
| Enhanced Color                  | +8,000,000            |
| Enhanced Color (Premium)        | +12,000,000           |
| Steel Core 16 inch              | Included               |
| Alloy 17 inch                   | Included               |
| Steel Core 16 inch (with battery)| 80,000,000            |
| Sliding Door (EC Van)           | +20,000,000           |
  ```

#### Chunk `url_2a7cf685fe11_estimated-costs_c001`
- **Section**: Estimated Costs
- **Codes**: TBD
- **Content Preview**:
  ```
  ### Estimated Costs

| Item                                      | Cost (VNĐ)            |
|-------------------------------------------|-----------------------|
| Vehicle Price (including VAT)             | 1,499,000,000         |
| State Fees                                | 16,380,700            |
| Registration Fee                          | 14,000,000            |
| Road Maintenance Fee (12 months)         | 1,560,000             |
| Civil Liability Insurance (12 months)    | 480,700               |
| Inspection Fee                            | 340,000               |
| Green Future Initiative Discount          | -149,900,000          |
| Total Estimated Cost                      | 1,365,480,700         |

### Financing Options

- **Down Payment**: 20%
- **Loan Package**: Standard Loan
- **Loan Duration**: 8 years
- **Interest Rate**: TBD

### Monthly Payment Estimate

- **Estimated Monthly Payment**: From 0 VNĐ/month
  ```

#### Chunk `url_2a7cf685fe11_ti-n-ch_c001`
- **Section**: Tiện ích
- **Codes**: MPV, SA2
- **Content Preview**:
  ```
  ### Tiện ích

- structure_block_type: product_card
- structure_block_id: dom_06af2e28052e
- structure_dedupe_hash: fafe6e0674a4
- structure_attributes: class='header'
- content: VinFast - Mãnh liệt tinh thần Việt VinFast - Mãnh liệt tinh thần Việt VinFast - Mãnh liệt tinh thần Việt VinFast - Mãnh liệt tinh thần Việt Giới thiệu Ô tô Động cơ điện Động cơ xăng Dòng xe dịch vụ VF 3 VF 5 VF 6 VF MPV 7 VF 7 VF 8 VF 8 The All New VF 9 Fadil Lux A2.0 Lux SA2.0 President Minio Green Herio Green Nerio Green Limo Green EC Van EBus Xe máy điện Phụ kiện xe Dịch vụ hậu mãi BẢO HÀNH & BẢO DƯỠNG HƯỚNG DẪN SỬ DỤNG Thông tin bảo hành Thông tin bảo dưỡng định kỳ Thông tin dịch vụ Tra cứu tình trạng xe Hướng dẫn sử dụng ô tô Hướng dẫn sử dụng xe máy điện Hướng dẫn sử dụng VinFast App đặt lịch Pin và trạm sạc Pin và trạm sạc Ô tô điện Pin và trạm sạc Xe máy điện Lưu trữ năng lượng 0 Tài khoản Đăng ký lái thử Nhắc nhở bảo dưỡng xe Đã đến lúc bảo dưỡng xe của bạn.
  ```

#### Chunk `url_2a7cf685fe11_ti-n-ch_c002`
- **Section**: Tiện ích
- **Codes**: MPV, SA2
- **Content Preview**:
  ```
  ### Tiện ích

structure_block_type: product_card
- structure_block_id: dom_06af2e28052e
- structure_dedupe_hash: fafe6e0674a4
- structure_attributes: class='header'
- content: VinFast - Mãnh liệt tinh thần Việt VinFast - Mãnh liệt tinh thần Việt VinFast - Mãnh liệt tinh thần Việt VinFast - Mãnh liệt tinh thần Việt Giới thiệu Ô tô Động cơ điện Động cơ xăng Dòng xe dịch vụ VF 3 VF 5 VF 6 VF MPV 7 VF 7 VF 8 VF 8 The All New VF 9 Fadil Lux A2.0 Lux SA2.0 President Minio Green Herio Green Nerio Green Limo Green EC Van EBus Xe máy điện Phụ kiện xe Dịch vụ hậu mãi BẢO HÀNH & BẢO DƯỠNG HƯỚNG DẪN SỬ DỤNG Thông tin bảo hành Thông tin bảo dưỡng định kỳ Thông tin dịch vụ Tra cứu tình trạng xe Hướng dẫn sử dụng ô tô Hướng dẫn sử dụng xe máy điện Hướng dẫn sử dụng VinFast App đặt lịch Pin và trạm sạc Pin và trạm sạc Ô tô điện Pin và trạm sạc Xe máy điện Lưu trữ năng lượng 0 Tài khoản Đăng ký lái thử Nhắc nhở bảo dưỡng xe Đã đến lúc bảo dưỡng xe của bạn.
Ngày: 8 tháng 10 , 2021 Tiện ích Đăng ký lái thử So sánh xe Dự toán chi phí lăn bánh Dự toán vay trả góp Thẩm định vay trả góp Đặt lịch dịch vụ Mua sắm VF DrgnFly eBike Phụ kiện xe Tin tức Công ty Cộng đồng Hỗ trợ Tìm Showroom & Trạm sạc Câu hỏi thường gặp Thảo luận Cộng đồng VinFast Toàn cầu Giới thiệu Ô tô Xem tất cả Động cơ điện dòng xe cá nhân VF 3 VF 5 VF 6 VF e34 MPV 7 VF 7 VF 8 VF 8 The All New VF 9 Động cơ xăng Fadil Lux A2.0 Lux SA2.0 President Dòng xe dịch vụ Minio Green Herio Green Nerio Green Limo Green EC Van EBus Xe máy điện VF DrgnFly eBike Dịch vụ hậu mãi Bảo hành & Bảo dưỡng Thông tin bảo hành Thông tin bảo dưỡng định kỳ Thông tin dịch vụ Tra cứu tình trạng xe Hướng dẫn sử dụng Hướng dẫn sử dụng ô tô Hướng dẫn sử dụng xe máy điện Hướng dẫn sử dụng VinFast App Pin và trạm sạc Pin và trạm sạc Ô tô điện Pin và trạm sạc Xe máy điện Lưu trữ năng lượng Tiện ích So sánh xe Dự toán chi phí lăn bánh Dự toán vay trả góp Đặt lịch dịch vụ Thẩm định vay trả góp Mua sắm Phụ kiện xe Tin tức Công ty Cộng đồng Hỗ trợ Tìm Showroom & Trạm sạc Câu hỏi thường gặp Thảo luận Cộng đồng VinFast Toàn cầu Đăng ký lái thử Lựa chọn quốc gia Việt Nam Bắc Mỹ United States English Canada English Francais Châu Âu France Francais Deutschland Deutsch Nederland Nederlands Others English Châu Á Việt Nam Tiếng Việt English if(typeof window.data === 'undefined') { window.data = {}; } window.data.redirectWhiteList = ["vinfastauto.com","salesforce.com"] if(window.Profile) { var accountSubmenu = document.querySelector('#mobile-login'); if(accountSubmenu) { accountSubmenu.removeAttribute('data-bs-target'); accountSubmenu.setAttribute('href', "/vn_vi/thong-tin-ca-nhan"); if(document.documentElement.getAttribute('lang') === 'en') { accountSubmenu.querySelector('.user-name').innerHTML = window.Profile.firstName + " " + window.Profile.lastName; } else { accountSubmenu.querySelector('.user-name').innerHTML = window.Profile.lastName + " " + window.Profile.firstName; } accountSubmenu.classList.add('logged-in');
  ```

#### Chunk `url_2a7cf685fe11_ti-n-ch_c003`
- **Section**: Tiện ích
- **Codes**: MPV, SA2
- **Content Preview**:
  ```
  ### Tiện ích

8 tháng 10 , 2021 Tiện ích Đăng ký lái thử So sánh xe Dự toán chi phí lăn bánh Dự toán vay trả góp Thẩm định vay trả góp Đặt lịch dịch vụ Mua sắm VF DrgnFly eBike Phụ kiện xe Tin tức Công ty Cộng đồng Hỗ trợ Tìm Showroom & Trạm sạc Câu hỏi thường gặp Thảo luận Cộng đồng VinFast Toàn cầu Giới thiệu Ô tô Xem tất cả Động cơ điện dòng xe cá nhân VF 3 VF 5 VF 6 VF e34 MPV 7 VF 7 VF 8 VF 8 The All New VF 9 Động cơ xăng Fadil Lux A2.0 Lux SA2.0 President Dòng xe dịch vụ Minio Green Herio Green Nerio Green Limo Green EC Van EBus Xe máy điện VF DrgnFly eBike Dịch vụ hậu mãi Bảo hành & Bảo dưỡng Thông tin bảo hành Thông tin bảo dưỡng định kỳ Thông tin dịch vụ Tra cứu tình trạng xe Hướng dẫn sử dụng Hướng dẫn sử dụng ô tô Hướng dẫn sử dụng xe máy điện Hướng dẫn sử dụng VinFast App Pin và trạm sạc Pin và trạm sạc Ô tô điện Pin và trạm sạc Xe máy điện Lưu trữ năng lượng Tiện ích So sánh xe Dự toán chi phí lăn bánh Dự toán vay trả góp Đặt lịch dịch vụ Thẩm định vay trả góp Mua sắm Phụ kiện xe Tin tức Công ty Cộng đồng Hỗ trợ Tìm Showroom & Trạm sạc Câu hỏi thường gặp Thảo luận Cộng đồng VinFast Toàn cầu Đăng ký lái thử Lựa chọn quốc gia Việt Nam Bắc Mỹ United States English Canada English Francais Châu Âu France Francais Deutschland Deutsch Nederland Nederlands Others English Châu Á Việt Nam Tiếng Việt English if(typeof window.data === 'undefined') { window.data = {}; } window.data.redirectWhiteList = ["vinfastauto.com","salesforce.com"] if(window.Profile) { var accountSubmenu = document.querySelector('#mobile-login'); if(accountSubmenu) { accountSubmenu.removeAttribute('data-bs-target'); accountSubmenu.setAttribute('href', "/vn_vi/thong-tin-ca-nhan"); if(document.documentElement.getAttribute('lang') === 'en') { accountSubmenu.querySelector('.user-name').innerHTML = window.Profile.firstName + " " + window.Profile.lastName; } else { accountSubmenu.querySelector('.user-name').innerHTML = window.Profile.lastName + " " + window.Profile.firstName; } accountSubmenu.classList.add('logged-in');
} } document.querySelectorAll('#mega-submenu .submenu-expand').forEach(function(item) { item.addEventListener('click', function(event) { var activeExpand = document.querySelector('#mega-submenu .submenu-expand.active-expand'); if(activeExpand) { activeExpand.classList.remove('active-expand'); } if(activeExpand !== item) { item.classList.add('active-expand'); } }) }); function login_success() { if (typeof dataLayer === 'undefined') return false; dataLayer.push({ 'event': 'login', 'user_id': window.Profile.sfscCustomerNo, 'method': 'Vinfast Account' }); }; if(localStorage.getItem('Logged') !== 'false' && window.Profile) { login_success(); localStorage.setItem('Logged', 'false'); }
  ```

#### Chunk `url_2a7cf685fe11_structured-dom-content_c001`
- **Section**: Structured DOM Content
- **Codes**: DOM, MPV, NEDC, VF3
- **Content Preview**:
  ```
  ### Structured DOM Content

- structure_block_type: vehicle_card
- structure_block_id: dom_2d9beffbc0d1
- structure_dedupe_hash: 252e4d9e17b8
- structure_attributes: class='swiper-container list-car-swiper list-car-swiper-pc swiper-initialized swiper-vertical swiper-backface-hidden'
- content: VF 3 VF 3 VF 5 VF 5 VF 6 VF 6 MPV 7 MPV 7 VF 7 VF 7 VF 8 VF 8 VF 8 The All New VF 8 The All New VF 9 VF 9

### Đặt cọc mua xe ô tô điện VinFast online vehicle card

- structure_block_type: vehicle_card
- structure_block_id: dom_dae279cdfce9
- structure_dedupe_hash: 1be0ace2f214
- structure_attributes: class='car-info-item'
- content: Công suất tối đa 30 kW

### Đặt cọc mua xe ô tô điện VinFast online vehicle card

- structure_block_type: vehicle_card
- structure_block_id: dom_4b3fdb52670a
- structure_dedupe_hash: 9204a7dc6c87
- structure_attributes: class='car-info-item'
- content: Dung lượng pin khả dụng 18,64 kWh

### Đặt cọc mua xe ô tô điện VinFast online vehicle card

- structure_block_type: vehicle_card
- structure_block_id: dom_30a8c307c7c3
- structure_dedupe_hash: ce0ab24bc061
- structure_attributes: class='car-info-item'
- content: Quãng đường di chuyển 215 km

### Đặt cọc mua xe ô tô điện VinFast online vehicle card

- structure_block_type: vehicle_card
- structure_block_id: dom_112f6ad2996a
- structure_dedupe_hash: 2226dff94342
- structure_attributes: class='tab-car-left-info' data-modelid='Products-Car-VF3'
- content: Công suất tối đa 30 kW Dung lượng pin khả dụng 18,64 kWh Quãng đường di chuyển 215 km Quãng đường di chuyển được tính toán dựa trên kết quả kiểm định theo quy chuẩn toàn cầu (NEDC). Quãng đường di chuyển thực tế có thể giảm so với kết quả kiểm định, phụ thuộc vào tốc độ lái xe, nhiệt độ, địa hình, thói quen sử dụng của người lái, chế độ lái được cài đặt, số lượng hành khách và các điều kiện giao thông khác.
  ```

#### Chunk `url_2a7cf685fe11_t-c-c-mua-xe-t-i-n-vinfast-online-vehicle-card_c001`
- **Section**: Đặt cọc mua xe ô tô điện VinFast online vehicle card
- **Codes**: NEDC, VF5
- **Content Preview**:
  ```
  ### Đặt cọc mua xe ô tô điện VinFast online vehicle card

- structure_block_type: vehicle_card
- structure_block_id: dom_ebf43582a8ab
- structure_dedupe_hash: 508ba965c5e2
- structure_attributes: class='car-info-item'
- content: Công suất tối đa 134 hp/100 kW

### Đặt cọc mua xe ô tô điện VinFast online vehicle card

- structure_block_type: vehicle_card
- structure_block_id: dom_25b6e29cd86d
- structure_dedupe_hash: a2f4dc7f72e5
- structure_attributes: class='car-info-item'
- content: Quãng đường di chuyển 1 lần sạc đầy lên tới 326,4 km (NEDC)

### Đặt cọc mua xe ô tô điện VinFast online vehicle card

- structure_block_type: vehicle_card
- structure_block_id: dom_b1bfb4642aab
- structure_dedupe_hash: c0da46e59970
- structure_attributes: class='car-info-item'
- content: Chiều dài cơ sở 2.514 mm

### Đặt cọc mua xe ô tô điện VinFast online vehicle card

- structure_block_type: vehicle_card
- structure_block_id: dom_c728d1ca51b1
- structure_dedupe_hash: 21b4ecf1506d
- structure_attributes: class='tab-car-left-info' data-modelid='Products-Car-VF5'
- content: Công suất tối đa 134 hp/100 kW Quãng đường di chuyển 1 lần sạc đầy lên tới 326,4 km (NEDC) Chiều dài cơ sở 2.514 mm Quãng đường di chuyển được tính toán dựa trên kết quả kiểm định theo quy chuẩn toàn cầu (NEDC). Quãng đường di chuyển thực tế có thể giảm so với kết quả kiểm định, phụ thuộc vào tốc độ lái xe, nhiệt độ, địa hình, thói quen sử dụng của người lái, chế độ lái được cài đặt, số lượng hành khách và các điều kiện giao thông khác. Công suất tối đa 134 hp/100 kW Quãng đường di chuyển 1 lần sạc đầy lên tới 326,4 km (NEDC) Chiều dài cơ sở 2.514 mm Quãng đường di chuyển được tính toán dựa trên kết quả kiểm định theo quy chuẩn toàn cầu (NEDC). Quãng đường di chuyển thực tế có thể giảm so với kết quả kiểm định, phụ thuộc vào tốc độ lái xe, nhiệt độ, địa hình, thói quen sử dụng của người lái, chế độ lái được cài đặt, số lượng hành khách và các điều kiện giao thông khác.
  ```

#### Chunk `url_2a7cf685fe11_t-c-c-mua-xe-t-i-n-vinfast-online-vehicle-card_c002`
- **Section**: Đặt cọc mua xe ô tô điện VinFast online vehicle card
- **Codes**: NEDC, VFE34
- **Content Preview**:
  ```
  ### Đặt cọc mua xe ô tô điện VinFast online vehicle card

- structure_block_type: vehicle_card
- structure_block_id: dom_9de8b77330f1
- structure_dedupe_hash: 3496c1db4b5d
- structure_attributes: class='car-info-item'
- content: Công suất tối đa 148 hp/110 kW

### Đặt cọc mua xe ô tô điện VinFast online vehicle card

- structure_block_type: vehicle_card
- structure_block_id: dom_4091db3071c2
- structure_dedupe_hash: 70a35c64e29e
- structure_attributes: class='car-info-item'
- content: Quãng đường di chuyển 1 lần sạc đầy lên tới 318,6 km (NEDC)

### Đặt cọc mua xe ô tô điện VinFast online vehicle card

- structure_block_type: vehicle_card
- structure_block_id: dom_782a2074c311
- structure_dedupe_hash: 7534dcd6470d
- structure_attributes: class='car-info-item'
- content: Chiều dài cơ sở 2.610,8 mm

### Đặt cọc mua xe ô tô điện VinFast online vehicle card

- structure_block_type: vehicle_card
- structure_block_id: dom_590cbeb6117e
- structure_dedupe_hash: b5a4f7d70269
- structure_attributes: class='tab-car-left-info' data-modelid='Products-Car-VFE34'
- content: Công suất tối đa 148 hp/110 kW Quãng đường di chuyển 1 lần sạc đầy lên tới 318,6 km (NEDC) Chiều dài cơ sở 2.610,8 mm Công suất tối đa 148 hp/110 kW Quãng đường di chuyển 1 lần sạc đầy lên tới 318,6 km (NEDC) Chiều dài cơ sở 2.610,8 mm

### Đặt cọc mua xe ô tô điện VinFast online vehicle card

- structure_block_type: vehicle_card
- structure_block_id: dom_6e549a26ae4c
- structure_dedupe_hash: 25268a64f0a7
- structure_attributes: class='car-info-item'
- content: Công suất tối đa 201 hp/150 kW

### Đặt cọc mua xe ô tô điện VinFast online vehicle card

- structure_block_type: vehicle_card
- structure_block_id: dom_4d65089a6a85
- structure_dedupe_hash: 26e43134ac61
- structure_attributes: class='car-info-item'
- content: Quãng đường di chuyển 1 lần sạc đầy lên tới 460 km (NEDC)
  ```

#### Chunk `url_2a7cf685fe11_t-c-c-mua-xe-t-i-n-vinfast-online-vehicle-card_c003`
- **Section**: Đặt cọc mua xe ô tô điện VinFast online vehicle card
- **Codes**: NEDC
- **Content Preview**:
  ```
  ### Đặt cọc mua xe ô tô điện VinFast online vehicle card

- structure_block_type: vehicle_card
- structure_block_id: dom_385d208d203d
- structure_dedupe_hash: 68ca2fb49d7c
- structure_attributes: class='car-info-item'
- content: Chiều dài cơ sở 2.730 mm

### Đặt cọc mua xe ô tô điện VinFast online vehicle card

- structure_block_type: vehicle_card
- structure_block_id: dom_814cf0e0c59b
- structure_dedupe_hash: 747c270e00d8
- structure_attributes: class='car-info-item'
- content: Công suất tối đa 174 hp/130 kW

### Đặt cọc mua xe ô tô điện VinFast online vehicle card

- structure_block_type: vehicle_card
- structure_block_id: dom_1123cf796e58
- structure_dedupe_hash: 63aadc5524a4
- structure_attributes: class='car-info-item'
- content: Quãng đường di chuyển 1 lần sạc đầy lên tới 485 km (NEDC)

### Đặt cọc mua xe ô tô điện VinFast online vehicle card

- structure_block_type: vehicle_card
- structure_block_id: dom_1dfd9403b0ff
- structure_dedupe_hash: d8d27f09a473
- structure_attributes: class='car-info-item'
- content: Quãng đường di chuyển 1 lần sạc đầy lên tới 480 km (NEDC)
  ```


# LLM Evaluation Report



# Evaluation of Actual Output Against Ground Truth

## 1. Content Completeness
The actual output is missing significant information from the ground truth:
- **Model Specifics**: The actual output does not provide detailed information about the VinFast VF 9 model, including its tagline, warranty, and specific pricing for different editions.
- **Deposit Information**: There is no mention of the deposit amount or the call-to-action (CTA) related to placing a deposit for the VF 9.
- **Color Options**: The actual output lacks the detailed breakdown of exterior and interior color options, which is crucial for potential buyers.
- **Cost Breakdown**: While there is a total cost breakdown, it does not match the detailed structure provided in the ground truth, which includes specific fees and the modal for on-road costs.

## 2. Content Correctness
- **Inaccurate Specifications**: The actual output lists specifications for various models, including the VF 3, VF 5, and others, which are not relevant to the VF 9. This could lead to confusion for users looking specifically for information on the VF 9.
- **Hallucinations**: The actual output includes models and specifications that do not appear in the ground truth, such as the VF 3 and VF e34 SMART, which are irrelevant to the context of the VF 9.

## 3. Structure and Formatting
- **Headings and Sections**: The structure of the actual output is not aligned with the ground truth. The ground truth has a clear, logical flow with numbered sections, while the actual output is more fragmented and lacks a coherent structure.
- **Tables**: The tables in the actual output do not match the format or content of the ground truth. For example, the pricing table does not specify the different editions of the VF 9, which is critical for understanding the pricing structure.

## 4. Noise and Boilerplate
- **Irrelevant Content**: The actual output contains a significant amount of irrelevant content, such as general vehicle information and boilerplate text about VinFast, which detracts from the specific information about the VF 9.
- **Excessive Details**: The inclusion of unrelated models and their specifications adds noise, making it difficult for users to find the specific information they need about the VF 9.

## 5. Overall Score
**Score: 3/10**

### Summary of Findings
The actual output fails to provide a comprehensive and accurate representation of the VinFast VF 9 as outlined in the ground truth. Key information is missing, and the structure is disorganized, leading to confusion. The presence of irrelevant content and inaccuracies further diminishes the quality of the output. Improvements are needed to ensure that the output aligns closely with the ground truth in terms of completeness, correctness, and clarity.