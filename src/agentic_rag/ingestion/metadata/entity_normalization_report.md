# Entity Normalization — Báo cáo thống kê hoàn chỉnh

## 1. Tổng quan

- Raw entity (cách viết thô): **1036**
- Canonical (sau chuẩn hóa): **762**
- Tỉ lệ gộp: 1036/762 = **1.36** variant/canonical
- Tổng chunk trong corpus: **1488**
- Chunk có ≥1 entity filterable: **890** (59.8%)
- Canonical thực sự lọc ra chunk: **163**

## 2. Theo type

| type | raw | canonical | filterable |
|------|-----|-----------|------------|
| car_model | 130 | 19 | ✅ |
| ebike_model | 74 | 27 | ✅ |
| location | 136 | 117 | ✅ |
| brand | 51 | 35 | — |
| accessory | 66 | 46 | — |
| contact | 36 | 27 | — |
| generic | 305 | 277 | — |
| other | 238 | 214 | — |

## 3. Phân bố số variant / canonical

| #variants | #canonical |
|-----------|------------|
| 1 | 655 |
| 2 | 65 |
| 3 | 16 |
| 4 | 7 |
| 5 | 3 |
| 6 | 4 |
| 7 | 3 |
| 8 | 3 |
| 9 | 1 |
| 13 | 1 |
| 15 | 2 |
| 18 | 1 |
| 21 | 1 |

> 655/762 canonical chỉ có 1 cách viết (không gộp gì).

## 4. Coverage — mỗi canonical lọc ra bao nhiêu chunk

Số canonical lọc ra ≥1 chunk: **163**. (Filter `entities_canonical` chứa giá trị.)

| canonical | type | #chunks | % corpus |
|-----------|------|---------|----------|
| VF 8 | car_model | 203 | 13.6% |
| VF 9 | car_model | 133 | 8.9% |
| VF e34 | car_model | 116 | 7.8% |
| VF 7 | car_model | 86 | 5.8% |
| VF 5 | car_model | 77 | 5.2% |
| VF 3 | car_model | 76 | 5.1% |
| Hà Nội | location | 74 | 5.0% |
| Theon S | ebike_model | 70 | 4.7% |
| VF 6 | car_model | 65 | 4.4% |
| Klara S | ebike_model | 57 | 3.8% |
| Việt Nam | location | 48 | 3.2% |
| Vento S | ebike_model | 43 | 2.9% |
| Indonesia | location | 40 | 2.7% |
| Feliz S | ebike_model | 39 | 2.6% |
| Nerio Green | car_model | 39 | 2.6% |
| Evo 200 | ebike_model | 35 | 2.4% |
| Hồ Chí Minh | location | 34 | 2.3% |
| Limo Green | car_model | 33 | 2.2% |
| VF MPV 7 | car_model | 31 | 2.1% |
| Đà Nẵng | location | 26 | 1.7% |
| Feliz | ebike_model | 24 | 1.6% |
| Evo Grand | ebike_model | 22 | 1.5% |
| E-Scooter | ebike_model | 21 | 1.4% |
| Hải Phòng | location | 19 | 1.3% |
| Fadil | car_model | 17 | 1.1% |
| Ấn Độ | location | 16 | 1.1% |
| EC Van | car_model | 15 | 1.0% |
| Lux A2.0 | car_model | 15 | 1.0% |
| Lux SA2.0 | car_model | 15 | 1.0% |
| Feliz Lite | ebike_model | 13 | 0.9% |
| Philippines | location | 13 | 0.9% |
| Vento | ebike_model | 13 | 0.9% |
| Flazz | ebike_model | 11 | 0.7% |
| Evo | ebike_model | 9 | 0.6% |
| Minio Green | ebike_model | 9 | 0.6% |
| Châu Âu | location | 8 | 0.5% |
| Klara A2 | ebike_model | 7 | 0.5% |
| Viper | ebike_model | 7 | 0.5% |
| Cần Thơ | location | 6 | 0.4% |
| Feliz 2025 | ebike_model | 6 | 0.4% |
| Feliz II | ebike_model | 6 | 0.4% |
| Amio | ebike_model | 5 | 0.3% |
| DrgnFly | ebike_model | 5 | 0.3% |
| Evo Lite Neo | ebike_model | 5 | 0.3% |
| Đình Vũ – Cát Hải | location | 5 | 0.3% |
| Bắc Mỹ | location | 4 | 0.3% |
| Cát Bà | location | 4 | 0.3% |
| Nhật Bản | location | 4 | 0.3% |
| Tempest | car_model | 4 | 0.3% |
| Vinhomes Times City | location | 4 | 0.3% |
| Gia Lâm | location | 3 | 0.2% |
| Nam Từ Liêm | location | 3 | 0.2% |
| Nha Trang | location | 3 | 0.2% |
| Quảng Ninh | location | 3 | 0.2% |
| Quốc Oai | location | 3 | 0.2% |
| Singapore | location | 3 | 0.2% |
| Thăng Long | location | 3 | 0.2% |
| Trung Đông | location | 3 | 0.2% |
| Vincom | location | 3 | 0.2% |
| Vinhomes Ocean Park | location | 3 | 0.2% |
| Đông Anh | location | 3 | 0.2% |
| An Giang | location | 2 | 0.1% |
| An Hải | location | 2 | 0.1% |
| Ba Vì | location | 2 | 0.1% |
| Cần Giờ | location | 2 | 0.1% |
| D’ EL Dorado 1 | location | 2 | 0.1% |
| D’ Le Roi Soleil | location | 2 | 0.1% |
| EB 6 | ebike_model | 2 | 0.1% |
| Evo Lite | ebike_model | 2 | 0.1% |
| Golden West Complex | location | 2 | 0.1% |
| Hai Bà Trưng | location | 2 | 0.1% |
| Hoàng Mai | location | 2 | 0.1% |
| Hà Thành | location | 2 | 0.1% |
| Hà Tĩnh | location | 2 | 0.1% |
| Italy | location | 2 | 0.1% |
| Khánh Hoà | location | 2 | 0.1% |
| King Palace | location | 2 | 0.1% |
| Long Biên | location | 2 | 0.1% |
| Lạc Hồng 800S | ebike_model | 2 | 0.1% |
| Lạc Hồng 900S | ebike_model | 2 | 0.1% |
| Malaysia | location | 2 | 0.1% |
| Minio | ebike_model | 2 | 0.1% |
| Phú Quốc | location | 2 | 0.1% |
| Somerset West Lake Hanoi | location | 2 | 0.1% |
| Somerset West Point | location | 2 | 0.1% |
| Stellar Garden | location | 2 | 0.1% |
| Thanh Xuân | location | 2 | 0.1% |
| Thái Lan | location | 2 | 0.1% |
| Tây Hồ | location | 2 | 0.1% |
| Vinhomes Royal City | location | 2 | 0.1% |
| Vinmec Times City | location | 2 | 0.1% |
| Việt Đức Complex | location | 2 | 0.1% |
| Ba Đình | location | 1 | 0.1% |
| Bãi đỗ xe Mễ Trì | location | 1 | 0.1% |
| Bãi đỗ xe Trạm đăng kiểm 29.15D | location | 1 | 0.1% |
| Bình Vượng Tower | location | 1 | 0.1% |
| Bắc Giang | location | 1 | 0.1% |
| Bắc Từ Liêm | location | 1 | 0.1% |
| Chung cư A15 Bộ Công An | location | 1 | 0.1% |
| Chung cư CT2-3 Dream Town | location | 1 | 0.1% |
| Chung cư Hồ Hà Eco City | location | 1 | 0.1% |
| Chung cư Intracom 1 | location | 1 | 0.1% |
| Chung cư Ruby City 3 | location | 1 | 0.1% |
| Chung cư Splendora | location | 1 | 0.1% |
| Chung cư Tecco Garden | location | 1 | 0.1% |
| Chung cư Tecco Skyville | location | 1 | 0.1% |
| Châu Á | location | 1 | 0.1% |
| Chí Tuyến Bắc | location | 1 | 0.1% |
| Coninco Tower | location | 1 | 0.1% |
| Cát Hải | location | 1 | 0.1% |
| Cầu Giấy | location | 1 | 0.1% |
| Dubai | location | 1 | 0.1% |
| HPC Landmark 105 | location | 1 | 0.1% |
| Hoài Đức | location | 1 | 0.1% |
| Hoàng Hà | location | 1 | 0.1% |
| Hà Đông | location | 1 | 0.1% |
| Hòa Khánh | location | 1 | 0.1% |
| Hòa Vang | location | 1 | 0.1% |
| Hòn Tre | location | 1 | 0.1% |
| Hải Châu | location | 1 | 0.1% |
| Israel | location | 1 | 0.1% |
| Kazakhstan | location | 1 | 0.1% |
| Khu đô thị Thanh Hà | location | 1 | 0.1% |
| Klara | ebike_model | 1 | 0.1% |
| Liên Chiểu | location | 1 | 0.1% |
| Lux | car_model | 1 | 0.1% |
| Lạc Hồng 900 LX | ebike_model | 1 | 0.1% |
| Mê Linh | location | 1 | 0.1% |
| Mũi Cà Mau | location | 1 | 0.1% |
| Mỹ | location | 1 | 0.1% |
| Ngũ Hành Sơn | location | 1 | 0.1% |
| Phú Quốc United Center | location | 1 | 0.1% |
| Phú Sơn | location | 1 | 0.1% |
| Phúc Thọ | location | 1 | 0.1% |
| Quang Minh | location | 1 | 0.1% |
| Rainbow Văn Quán | location | 1 | 0.1% |
| Subang | location | 1 | 0.1% |
| Sóc Sơn | location | 1 | 0.1% |
| TTTM Hiền Lương | location | 1 | 0.1% |
| Thanh Oai | location | 1 | 0.1% |
| Thanh Trì | location | 1 | 0.1% |
| Thường Tín | location | 1 | 0.1% |
| Trung Quốc | location | 1 | 0.1% |
| UAE | location | 1 | 0.1% |
| Ucraina | location | 1 | 0.1% |
| VF 7S | car_model | 1 | 0.1% |
| VF e35 | car_model | 1 | 0.1% |
| VF e36 | car_model | 1 | 0.1% |
| Vincom Center | location | 1 | 0.1% |
| Vincom Center Bà Triệu | location | 1 | 0.1% |
| Vincom Center Nguyễn Chí Thanh | location | 1 | 0.1% |
| Vincom Center Phạm Ngọc Thạch | location | 1 | 0.1% |
| Vincom MegaMall Times City | location | 1 | 0.1% |
| Vinhomes Green Bay | location | 1 | 0.1% |
| Vinhomes Symphony | location | 1 | 0.1% |
| Vinhomes Thăng Long Nam | location | 1 | 0.1% |
| Xuân Mai Complex | location | 1 | 0.1% |
| Đài Bắc | location | 1 | 0.1% |
| Đài Loan | location | 1 | 0.1% |
| Đại học Bách Khoa Hà Nội | location | 1 | 0.1% |
| Đống Đa | location | 1 | 0.1% |
| Đức | location | 1 | 0.1% |
| Ứng Hòa | location | 1 | 0.1% |

## 5. Menu canonical filterable (dùng cho query filter)

### car_model (19)

EC Van, Fadil, Limo Green, Lux, Lux A2.0, Lux SA2.0, Nerio Green, Tempest, VF 3, VF 5, VF 6, VF 7, VF 7S, VF 8, VF 9, VF MPV 7, VF e34, VF e35, VF e36

### ebike_model (27)

Amio, DrgnFly, E-Scooter, EB 6, Evo, Evo 200, Evo Grand, Evo Lite, Evo Lite Neo, Feliz, Feliz 2025, Feliz II, Feliz Lite, Feliz S, Flazz, Klara, Klara A2, Klara S, Lạc Hồng 800S, Lạc Hồng 900 LX, Lạc Hồng 900S, Minio, Minio Green, Theon S, Vento, Vento S, Viper

### location (117)

An Giang, An Hải, Ba Vì, Ba Đình, Bãi đỗ xe Mễ Trì, Bãi đỗ xe Trạm đăng kiểm 29.15D, Bình Vượng Tower, Bắc Giang, Bắc Mỹ, Bắc Từ Liêm, Chung cư A15 Bộ Công An, Chung cư CT2-3 Dream Town, Chung cư Hồ Hà Eco City, Chung cư Intracom 1, Chung cư Ruby City 3, Chung cư Splendora, Chung cư Tecco Garden, Chung cư Tecco Skyville, Châu Á, Châu Âu, Chí Tuyến Bắc, Coninco Tower, Cát Bà, Cát Hải, Cần Giờ, Cần Thơ, Cầu Giấy, Dubai, D’ EL Dorado 1, D’ Le Roi Soleil, Gia Lâm, Golden West Complex, HPC Landmark 105, Hai Bà Trưng, Hoài Đức, Hoàng Hà, Hoàng Mai, Hà Nội, Hà Thành, Hà Tĩnh, Hà Đông, Hòa Khánh, Hòa Vang, Hòn Tre, Hải Châu, Hải Phòng, Hồ Chí Minh, Indonesia, Israel, Italy, Kazakhstan, Khu đô thị Thanh Hà, Khánh Hoà, King Palace, Liên Chiểu, Long Biên, Malaysia, Mê Linh, Mũi Cà Mau, Mỹ, Nam Từ Liêm, Ngũ Hành Sơn, Nha Trang, Nhật Bản, Philippines, Phú Quốc, Phú Quốc United Center, Phú Sơn, Phúc Thọ, Quang Minh, Quảng Ninh, Quốc Oai, Rainbow Văn Quán, Singapore, Somerset West Lake Hanoi, Somerset West Point, Stellar Garden, Subang, Sóc Sơn, TTTM Hiền Lương, Thanh Oai, Thanh Trì, Thanh Xuân, Thái Lan, Thăng Long, Thường Tín, Trung Quốc, Trung Đông, Tây Hồ, UAE, Ucraina, Vincom, Vincom Center, Vincom Center Bà Triệu, Vincom Center Nguyễn Chí Thanh, Vincom Center Phạm Ngọc Thạch, Vincom MegaMall Times City, Vinhomes Green Bay, Vinhomes Ocean Park, Vinhomes Royal City, Vinhomes Symphony, Vinhomes Thăng Long Nam, Vinhomes Times City, Vinmec Times City, Việt Nam, Việt Đức Complex, Xuân Mai Complex, Đà Nẵng, Đài Bắc, Đài Loan, Đình Vũ – Cát Hải, Đông Anh, Đại học Bách Khoa Hà Nội, Đống Đa, Đức, Ấn Độ, Ứng Hòa

## 6. Ghi chú

- **Non-filterable** (brand/generic/contact/other): cố tình loại khỏi filter (vd 'VinFast' 75% chunk, 'pin', 'xe điện') — không phải rác, chỉ không dùng pre-filter.
- **Đuôi dài** (canonical ít chunk): hiếm nhưng hợp lệ; vô hại, chỉ trigger khi query nhắc tới.
- **Lưu ý type:** một canonical có thể hiện sai type ở vài chỗ (vd 'Lux A2.0') do type được LLM gán theo cụm — số coverage vẫn đúng.