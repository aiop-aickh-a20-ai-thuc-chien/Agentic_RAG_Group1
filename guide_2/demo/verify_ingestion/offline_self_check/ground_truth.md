# Ground Truth: VinFast VF 9 – Trang Đặt Cọc

> **Sources:**  
> - HTML snippet: `shop.vinfastauto.com` – VF9 color selector (provided)  
> - PDP: https://shop.vinfastauto.com/vn_vi/dat-coc-xe-vf9.html  
> - Model selector: https://shop.vinfastauto.com/vn_vi/dat-coc-o-to-dien-vinfast.html?modelId=Products-Car-VF9  
> - `model_id`: `Products-Car-VF9`

---

## 1. Thông tin xe

| Trường | Giá trị |
|---|---|
| Tên xe | VinFast VF 9 |
| Phân khúc | eSUV – SUV điện 7 chỗ hạng sang |
| Tagline | Sự Lựa Chọn Của Người Thành Đạt, Tiên Phong |
| Quãng đường (WLTP) | **626 km** *(phiên bản Eco, pin CATL)* |
| Công suất | **402 hp / 620 Nm** |
| Bảo hành xe | **200.000 km hoặc 10 năm** |

---

## 2. Phiên bản & Giá niêm yết

| Edition ID | Tên phiên bản | Giá (VNĐ, có VAT) |
|---|---|---|
| `NE3NV` | VF 9 Eco | **1.499.000.000** |
| `NE3MV` | VF 9 Plus | **1.699.000.000** |

**Lưu ý giá:**
- Giá xe **đã bao gồm VAT**.
- Giá xe **chưa bao gồm** tùy chọn ghế cơ trưởng.

---

## 3. Đặt cọc

| Trường | Giá trị |
|---|---|
| Số tiền đặt cọc | **50.000.000 VNĐ** |
| CTA Label | "Đặt cọc 50.000.000 VNĐ" |
| CTA URL | https://shop.vinfastauto.com/vn_vi/dat-coc-o-to-dien-vinfast.html?modelId=Products-Car-VF9 |

---

## 4. Chi phí lăn bánh – Popup "Chi tiết"

Trên trang model selector (`?modelId=Products-Car-VF9`), có link mở modal chi tiết chi phí lăn bánh:

```html
<a href="javascript:void(0);"
   data-bs-toggle="modal"
   data-bs-target="#rollingUpCostPopUp"
   class="tab-right-cost-more js-rollingUpCostPopUp">Chi tiết</a>
```

| Thuộc tính | Giá trị |
|---|---|
| Modal ID | `#rollingUpCostPopUp` |
| CSS classes | `tab-right-cost-more js-rollingUpCostPopUp` |
| Label | Chi tiết |
| Chức năng | Hiển thị bảng chi phí lăn bánh (on-road cost breakdown) |

---

## 5. Màu ngoại thất (Exterior Colors)

> Hiển thị cho edition `NE3NV` (VF 9 Eco). Màu đang chọn mặc định: **Crimson Red**.
>
> ⚠️ **Lưu ý:** Các giá trị `data-price-value` trên từng swatch màu trong HTML (1.731.000.000 / 1.743.000.000) là **cart total nội bộ** cho tổ hợp edition+màu cụ thể, **không phải giá của màu sắc**. Không dùng các con số này để đánh giá. Chỉ dùng giá niêm yết của phiên bản và mức phụ thu màu nâng cao.

### 5.1 Màu cơ bản – Theo xe (không phụ thu)

| Mã màu | Tên màu |
|---|---|
| `CE18` | Infinity Blanc |
| `CE11` | Jet Black |
| `CE1V` | Zenith Grey |
| `CE1M` | Crimson Red ✅ *(mặc định đang chọn)* |
| `CE1W` | Urban Mint |

### 5.2 Màu nâng cao (+12.000.000 VNĐ so với giá niêm yết phiên bản)

| Mã màu | Tên màu |
|---|---|
| `CE22` | Ivy Green |
| `CE17` | Desat Silver |

### 5.3 Bảng giá đầy đủ theo Phiên bản × Màu ngoại thất

> **Công thức:** Giá = Giá niêm yết phiên bản + Phụ thu màu (0 đ hoặc +12.000.000 đ). Đã bao gồm VAT. Chưa bao gồm tùy chọn ghế cơ trưởng.

| Phiên bản | Màu | Loại màu | Giá (VNĐ) |
|---|---|---|---|
| VF 9 Eco | Infinity Blanc | Cơ bản | **1.499.000.000** |
| VF 9 Eco | Jet Black | Cơ bản | **1.499.000.000** |
| VF 9 Eco | Zenith Grey | Cơ bản | **1.499.000.000** |
| VF 9 Eco | Crimson Red ✅ | Cơ bản | **1.499.000.000** |
| VF 9 Eco | Urban Mint | Cơ bản | **1.499.000.000** |
| VF 9 Eco | Ivy Green | Nâng cao | **1.511.000.000** |
| VF 9 Eco | Desat Silver | Nâng cao | **1.511.000.000** |
| VF 9 Plus | Infinity Blanc | Cơ bản | **1.699.000.000** |
| VF 9 Plus | Jet Black | Cơ bản | **1.699.000.000** |
| VF 9 Plus | Zenith Grey | Cơ bản | **1.699.000.000** |
| VF 9 Plus | Crimson Red | Cơ bản | **1.699.000.000** |
| VF 9 Plus | Urban Mint | Cơ bản | **1.699.000.000** |
| VF 9 Plus | Ivy Green | Nâng cao | **1.711.000.000** |
| VF 9 Plus | Desat Silver | Nâng cao | **1.711.000.000** |

**Tóm tắt 4 mức giá có thể xảy ra:**

| Mức giá | Khi nào |
|---|---|
| 1.499.000.000 VNĐ | VF 9 Eco + màu cơ bản |
| 1.511.000.000 VNĐ | VF 9 Eco + màu nâng cao (Ivy Green / Desat Silver) |
| 1.699.000.000 VNĐ | VF 9 Plus + màu cơ bản |
| 1.711.000.000 VNĐ | VF 9 Plus + màu nâng cao (Ivy Green / Desat Silver) |

---

## 6. Màu nội thất (Interior Colors)

> Màu nội thất khả dụng phụ thuộc vào màu ngoại thất đã chọn.

| Màu ngoại thất | Mã ngoại | Nội thất khả dụng |
|---|---|---|
| Infinity Blanc | `CE18` | Granite Black (`CI11`), Saddle Brown (`CI12`) |
| Crimson Red | `CE1M` | Granite Black (`CI11`), Cotton Beige (`CI13`) |
| Urban Mint | `CE1W` | Granite Black (`CI11`), Saddle Brown (`CI12`) |
| Jet Black | `CE11` | Granite Black (`CI11`), Cotton Beige (`CI13`), Saddle Brown (`CI12`) |
| Ivy Green | `CE22` | Granite Black (`CI11`), Cotton Beige (`CI13`), Saddle Brown (`CI12`) |
| Zenith Grey | `CE1V` | Granite Black (`CI11`), Saddle Brown (`CI12`) |
| Desat Silver | `CE17` | Granite Black (`CI11`), Saddle Brown (`CI12`) |

### Tổng hợp mã nội thất

| Mã | Tên |
|---|---|
| `CI11` | Granite Black |
| `CI12` | Saddle Brown |
| `CI13` | Cotton Beige |

---

## 7. Cấu trúc Product ID

Format: `VF-ZVEH-{modelCode}-{editionId}-{exteriorCode}-{interiorCode}`

- Model code: `PE1U_2023`
- Ví dụ: `VF-ZVEH-PE1U_2023-NE3NV-CE18-CI11`

### Danh sách Product IDs (edition NE3NV)

```
VF-ZVEH-PE1U_2023-NE3NV-CE18-CI11
VF-ZVEH-PE1U_2023-NE3NV-CE18-CI12
VF-ZVEH-PE1U_2023-NE3NV-CE1M-CI11
VF-ZVEH-PE1U_2023-NE3NV-CE1M-CI13
VF-ZVEH-PE1U_2023-NE3NV-CE1W-CI11
VF-ZVEH-PE1U_2023-NE3NV-CE1W-CI12
VF-ZVEH-PE1U_2023-NE3NV-CE11-CI11
VF-ZVEH-PE1U_2023-NE3NV-CE11-CI13
VF-ZVEH-PE1U_2023-NE3NV-CE11-CI12
VF-ZVEH-PE1U_2023-NE3NV-CE22-CI11
VF-ZVEH-PE1U_2023-NE3NV-CE22-CI13
VF-ZVEH-PE1U_2023-NE3NV-CE22-CI12
VF-ZVEH-PE1U_2023-NE3NV-CE1V-CI11
VF-ZVEH-PE1U_2023-NE3NV-CE1V-CI12
VF-ZVEH-PE1U_2023-NE3NV-CE17-CI11
VF-ZVEH-PE1U_2023-NE3NV-CE17-CI12
```

---

## 8. Điều hướng trang PDP

Thanh menu dọc trang (section anchors):

1. Phiên bản (`#section-version`)
2. Ngoại thất (`#section-product-exterior`)
3. Nội thất (`#section-product-interior`)
4. Công nghệ (`#section-technology`)
5. Đặc quyền (`#section-exclusive-rights`)
6. Pin sạc (`#section-charging-solution`)

---

## 9. Ghi chú cho Scoring

| Hạng mục kiểm tra | Expected value |
|---|---|
| Số phiên bản | 2 (Eco, Plus) |
| Giá Eco (base) | 1.499.000.000 VNĐ |
| Giá Plus (base) | 1.699.000.000 VNĐ |
| Tiền đặt cọc | 50.000.000 VNĐ |
| Số màu ngoại thất | 7 tổng (5 cơ bản, 2 nâng cao) |
| Phụ thu màu nâng cao | +12.000.000 VNĐ so với giá niêm yết phiên bản |
| Màu nội thất có | 3 (Granite Black, Saddle Brown, Cotton Beige) |
| Màu mặc định hiển thị | Crimson Red (`CE1M`) |
| Modal chi tiết lăn bánh | `#rollingUpCostPopUp` |
| VAT included | Có |
| Bảo hành | 10 năm / 200.000 km |
| **Giá cấu hình: Eco + Infinity Blanc** | **1.499.000.000 VNĐ** |
| **Giá cấu hình: Eco + Jet Black** | **1.499.000.000 VNĐ** |
| **Giá cấu hình: Eco + Zenith Grey** | **1.499.000.000 VNĐ** |
| **Giá cấu hình: Eco + Crimson Red** | **1.499.000.000 VNĐ** |
| **Giá cấu hình: Eco + Urban Mint** | **1.499.000.000 VNĐ** |
| **Giá cấu hình: Eco + Ivy Green** | **1.511.000.000 VNĐ** |
| **Giá cấu hình: Eco + Desat Silver** | **1.511.000.000 VNĐ** |
| **Giá cấu hình: Plus + Infinity Blanc** | **1.699.000.000 VNĐ** |
| **Giá cấu hình: Plus + Jet Black** | **1.699.000.000 VNĐ** |
| **Giá cấu hình: Plus + Zenith Grey** | **1.699.000.000 VNĐ** |
| **Giá cấu hình: Plus + Crimson Red** | **1.699.000.000 VNĐ** |
| **Giá cấu hình: Plus + Urban Mint** | **1.699.000.000 VNĐ** |
| **Giá cấu hình: Plus + Ivy Green** | **1.711.000.000 VNĐ** |
| **Giá cấu hình: Plus + Desat Silver** | **1.711.000.000 VNĐ** |
| Số mức giá có thể xảy ra | 4 (1.499M / 1.511M / 1.699M / 1.711M) |
