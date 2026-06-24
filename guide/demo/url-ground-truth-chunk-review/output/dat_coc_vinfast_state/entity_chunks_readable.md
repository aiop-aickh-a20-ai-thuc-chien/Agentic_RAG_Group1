# Chunk review

| # | Role | Section path | Models | Price | modelId | Choices | Chars | Chunk ID |
| ---: | --- | --- | --- | --- | --- | --- | ---: | --- |
| 1 | dataset_state | dat_coc_vinfast_state > Dataset state | VF3, VF9 | no | yes | yes | 514 | `url-ground-truth-entity_11d4f182714b_dataset-state-dataset-state_c001` |
| 2 | current_model | dat_coc_vinfast_state > Thông tin xe hiện tại | VF 9, VF3 | no | yes | no | 211 | `url-ground-truth-entity_11d4f182714b_current-model-th-ng-tin-xe-hi-n-t-i_c002` |
| 3 | model_version | dat_coc_vinfast_state > VF 9 Eco | VF 9 | yes | no | yes | 269 | `url-ground-truth-entity_11d4f182714b_model-version-vf-9-eco_c003` |
| 4 | model_version | dat_coc_vinfast_state > VF 9 Plus tùy chọn 7 chỗ | VF 9, VF 9 Plus | yes | no | yes | 301 | `url-ground-truth-entity_11d4f182714b_model-version-vf-9-plus-t-y-ch-n-7-ch_c004` |
| 5 | model_version | dat_coc_vinfast_state > VF 9 Plus tùy chọn ghế cơ trưởng | VF 9, VF 9 Plus | yes | no | yes | 317 | `url-ground-truth-entity_11d4f182714b_model-version-vf-9-plus-t-y-ch-n-gh-c-tr-ng_c005` |
| 6 | choices | dat_coc_vinfast_state > Ngoại thất VF9 | VF9 | yes | no | yes | 235 | `url-ground-truth-entity_11d4f182714b_choices-ngo-i-th-t-vf9_c006` |
| 7 | choices | dat_coc_vinfast_state > Nội thất VF9 | VF9 | no | no | yes | 164 | `url-ground-truth-entity_11d4f182714b_choices-n-i-th-t-vf9_c007` |
| 8 | customer_choices | dat_coc_vinfast_state > Hạng thành viên và ưu đãi | - | no | no | yes | 309 | `url-ground-truth-entity_11d4f182714b_customer-choices-h-ng-th-nh-vi-n-v-u-i_c008` |
| 9 | customer_choices | dat_coc_vinfast_state > Tỉnh thành | - | no | no | no | 77 | `url-ground-truth-entity_11d4f182714b_customer-choices-t-nh-th-nh_c009` |
| 10 | pricing | dat_coc_vinfast_state > Bảng tính chi phí lăn bánh | - | yes | no | yes | 440 | `url-ground-truth-entity_11d4f182714b_pricing-b-ng-t-nh-chi-ph-l-n-b-nh_c010` |
| 11 | model_navigation | dat_coc_vinfast_state > VF 3 | VF 3, VF3 | no | yes | no | 141 | `url-ground-truth-entity_11d4f182714b_model-navigation-vf-3_c011` |
| 12 | model_navigation | dat_coc_vinfast_state > VF 5 | VF 5, VF5 | no | yes | no | 141 | `url-ground-truth-entity_11d4f182714b_model-navigation-vf-5_c012` |
| 13 | model_navigation | dat_coc_vinfast_state > VF 6 | VF 6, VF6 | no | yes | no | 141 | `url-ground-truth-entity_11d4f182714b_model-navigation-vf-6_c013` |
| 14 | model_navigation | dat_coc_vinfast_state > VF 7 | VF 7, VF7 | no | yes | no | 141 | `url-ground-truth-entity_11d4f182714b_model-navigation-vf-7_c014` |
| 15 | model_navigation | dat_coc_vinfast_state > VF 8 | VF 8, VF8 | no | yes | no | 141 | `url-ground-truth-entity_11d4f182714b_model-navigation-vf-8_c015` |
| 16 | model_navigation | dat_coc_vinfast_state > VF 8 The All New | VF 8, VF8 | no | yes | no | 177 | `url-ground-truth-entity_11d4f182714b_model-navigation-vf-8-the-all-new_c016` |
| 17 | model_navigation | dat_coc_vinfast_state > MPV 7 | MPV 7, MPV7 | no | yes | no | 144 | `url-ground-truth-entity_11d4f182714b_model-navigation-mpv-7_c017` |

## Coverage

- All important scalar values appear in the generated Markdown.

## 1. Dataset state

- Chunk ID: `url-ground-truth-entity_11d4f182714b_dataset-state-dataset-state_c001`
- Section path: dat_coc_vinfast_state > Dataset state

```markdown
# Ground truth đặt cọc VinFast: dat_coc_vinfast_state

- Dataset ID: dat_coc_vinfast_state
- Target URL: https://shop.vinfastauto.com/vn_vi/dat-coc-o-to-dien-vinfast.html?modelId=Products-Car-VF3
- Status: state_only_not_yet_calculated

## Ghi chú ground truth

- Tên file có VF9 nhưng dataset này được dùng làm ground truth trạng thái cho URL đặt cọc có modelId=Products-Car-VF3.
- Ground truth hiện mô tả state/configurator và panel modelId; không coi các chi phí lăn bánh là kết quả tính toán cuối cùng cho VF3.
```

## 2. Thông tin xe hiện tại

- Chunk ID: `url-ground-truth-entity_11d4f182714b_current-model-th-ng-tin-xe-hi-n-t-i_c002`
- Section path: dat_coc_vinfast_state > Thông tin xe hiện tại

```markdown
## Thông tin xe hiện tại

- Mẫu xe đang hiển thị: VF 9
- Trạng thái dataset: state_only_not_yet_calculated
- Target URL: https://shop.vinfastauto.com/vn_vi/dat-coc-o-to-dien-vinfast.html?modelId=Products-Car-VF3
```

## 3. VF 9 Eco

- Chunk ID: `url-ground-truth-entity_11d4f182714b_model-version-vf-9-eco_c003`
- Section path: dat_coc_vinfast_state > VF 9 Eco

```markdown
## VF 9 Eco

- Mẫu xe: VF 9
- Phiên bản: VF 9 Eco
- Giá thực tế hiện tại: 1.499.000.000 VNĐ
- Giá nguyên gốc: 1.589.000.000 VNĐ
- Trạng thái hiển thị giá gốc: line-through
- HTML class của giá gốc: field-spec-item--desc-sub
- Tùy chọn pin: Bao gồm PIN ~423 km/1 lần sạc
```

## 4. VF 9 Plus tùy chọn 7 chỗ

- Chunk ID: `url-ground-truth-entity_11d4f182714b_model-version-vf-9-plus-t-y-ch-n-7-ch_c004`
- Section path: dat_coc_vinfast_state > VF 9 Plus tùy chọn 7 chỗ

```markdown
## VF 9 Plus tùy chọn 7 chỗ

- Mẫu xe: VF 9
- Phiên bản: VF 9 Plus tùy chọn 7 chỗ
- Giá thực tế hiện tại: 1.699.000.000 VNĐ
- Giá nguyên gốc: 1.789.000.000 VNĐ
- Trạng thái hiển thị giá gốc: line-through
- HTML class của giá gốc: field-spec-item--desc-sub
- Tùy chọn pin: Bao gồm PIN ~423 km/1 lần sạc
```

## 5. VF 9 Plus tùy chọn ghế cơ trưởng

- Chunk ID: `url-ground-truth-entity_11d4f182714b_model-version-vf-9-plus-t-y-ch-n-gh-c-tr-ng_c005`
- Section path: dat_coc_vinfast_state > VF 9 Plus tùy chọn ghế cơ trưởng

```markdown
## VF 9 Plus tùy chọn ghế cơ trưởng

- Mẫu xe: VF 9
- Phiên bản: VF 9 Plus tùy chọn ghế cơ trưởng
- Giá thực tế hiện tại: 1.731.000.000 VNĐ
- Giá nguyên gốc: 1.821.000.000 VNĐ
- Trạng thái hiển thị giá gốc: line-through
- HTML class của giá gốc: field-spec-item--desc-sub
- Tùy chọn pin: Bao gồm PIN ~438 km/1 lần sạc
```

## 6. Ngoại thất VF9

- Chunk ID: `url-ground-truth-entity_11d4f182714b_choices-ngo-i-th-t-vf9_c006`
- Section path: dat_coc_vinfast_state > Ngoại thất VF9

```markdown
## Ngoại thất VF9

### Màu cơ bản theo xe
- Infinity Blanc (Trắng)
- Jet Black (Đen)
- Zenith Grey (Xám)
- Crimson Red (Đỏ)
- Urban Mint (Xanh ngọc)

### Màu nâng cao
- Phụ phí: 12.000.000 VNĐ
- Ivy Green (Xanh lá)
- Desat Silver (Bạc)
```

## 7. Nội thất VF9

- Chunk ID: `url-ground-truth-entity_11d4f182714b_choices-n-i-th-t-vf9_c007`
- Section path: dat_coc_vinfast_state > Nội thất VF9

```markdown
## Nội thất VF9

- Granite Black (Đen)
- Saddle Brown (Nâu)
- Cotton Beige (Be)
- Ghi chú: Tùy chọn màu nội thất phụ thuộc vào việc lựa chọn phiên bản Eco hay Plus.
```

## 8. Hạng thành viên và ưu đãi

- Chunk ID: `url-ground-truth-entity_11d4f182714b_customer-choices-h-ng-th-nh-vi-n-v-u-i_c008`
- Section path: dat_coc_vinfast_state > Hạng thành viên và ưu đãi

```markdown
## Hạng thành viên và ưu đãi

### Hạng thành viên VinClub
- Chưa có
- VinClub Vàng
- VinClub Bạch Kim
- VinClub Kim Cương
- Quyền lợi: Áp dụng tích điểm và giảm giá trực tiếp tùy theo hạng thẻ VinClub

### Ưu đãi
- Mã khuyến mãi: null
- Chương trình áp dụng: Miễn phí sạc pin, ưu đãi gửi xe công cộng Vingroup
```

## 9. Tỉnh thành

- Chunk ID: `url-ground-truth-entity_11d4f182714b_customer-choices-t-nh-th-nh_c009`
- Section path: dat_coc_vinfast_state > Tỉnh thành

```markdown
## Tỉnh thành

- Hà Nội
- TP. Hồ Chí Minh
- Hà Tĩnh
- Các tỉnh/thành phố khác
```

## 10. Bảng tính chi phí lăn bánh

- Chunk ID: `url-ground-truth-entity_11d4f182714b_pricing-b-ng-t-nh-chi-ph-l-n-b-nh_c010`
- Section path: dat_coc_vinfast_state > Bảng tính chi phí lăn bánh

```markdown
## Bảng tính chi phí lăn bánh

| Hạng mục | Giá trị |
| --- | --- |
| Giá xe | 1.499.000.000 VNĐ |
| Phí giảm về ưu đãi | - 0 VNĐ |
| Lệ phí trước bạ | 0 VNĐ (Ô tô điện được miễn 100% LPTB) |
| Phí đăng ký biển số | 20.000.000 VNĐ (Tạm tính tại vùng I) |
| Phí đăng kiểm | 340.000 VNĐ |
| Phí bảo trì | 1.560.000 VNĐ / năm (Phí bảo trì đường bộ) |
| Bảo hiểm TNDS bắt buộc | 873.400 VNĐ / năm |
| Tổng chi phí lăn bánh | 1.521.773.400 VNĐ |
```

## 11. VF 3

- Chunk ID: `url-ground-truth-entity_11d4f182714b_model-navigation-vf-3_c011`
- Section path: dat_coc_vinfast_state > VF 3

```markdown
## VF 3

- Tên xe: VF 3
- modelId: Products-Car-VF3
- Mô tả panel: Panel điều hướng bên phải. Khi tương tác sẽ cập nhật tham số URL ?modelId=
```

## 12. VF 5

- Chunk ID: `url-ground-truth-entity_11d4f182714b_model-navigation-vf-5_c012`
- Section path: dat_coc_vinfast_state > VF 5

```markdown
## VF 5

- Tên xe: VF 5
- modelId: Products-Car-VF5
- Mô tả panel: Panel điều hướng bên phải. Khi tương tác sẽ cập nhật tham số URL ?modelId=
```

## 13. VF 6

- Chunk ID: `url-ground-truth-entity_11d4f182714b_model-navigation-vf-6_c013`
- Section path: dat_coc_vinfast_state > VF 6

```markdown
## VF 6

- Tên xe: VF 6
- modelId: Products-Car-VF6
- Mô tả panel: Panel điều hướng bên phải. Khi tương tác sẽ cập nhật tham số URL ?modelId=
```

## 14. VF 7

- Chunk ID: `url-ground-truth-entity_11d4f182714b_model-navigation-vf-7_c014`
- Section path: dat_coc_vinfast_state > VF 7

```markdown
## VF 7

- Tên xe: VF 7
- modelId: Products-Car-VF7
- Mô tả panel: Panel điều hướng bên phải. Khi tương tác sẽ cập nhật tham số URL ?modelId=
```

## 15. VF 8

- Chunk ID: `url-ground-truth-entity_11d4f182714b_model-navigation-vf-8_c015`
- Section path: dat_coc_vinfast_state > VF 8

```markdown
## VF 8

- Tên xe: VF 8
- modelId: Products-Car-VF8
- Mô tả panel: Panel điều hướng bên phải. Khi tương tác sẽ cập nhật tham số URL ?modelId=
```

## 16. VF 8 The All New

- Chunk ID: `url-ground-truth-entity_11d4f182714b_model-navigation-vf-8-the-all-new_c016`
- Section path: dat_coc_vinfast_state > VF 8 The All New

```markdown
## VF 8 The All New

- Tên xe: VF 8 The All New
- modelId: Products-Car-VF8-The-All-New
- Mô tả panel: Panel điều hướng bên phải. Khi tương tác sẽ cập nhật tham số URL ?modelId=
```

## 17. MPV 7

- Chunk ID: `url-ground-truth-entity_11d4f182714b_model-navigation-mpv-7_c017`
- Section path: dat_coc_vinfast_state > MPV 7

```markdown
## MPV 7

- Tên xe: MPV 7
- modelId: Products-Car-MPV7
- Mô tả panel: Panel điều hướng bên phải. Khi tương tác sẽ cập nhật tham số URL ?modelId=
```
