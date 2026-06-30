# Bộ câu hỏi DEMO — Graph BẬT tốt hơn TẮT

Các câu dưới đây: khi **TẮT graph** retrieval bỏ sót đoạn cần; **BẬT graph** kéo đúng đoạn đó vào top-5.

Cách demo: hỏi cùng câu 2 lần (graph OFF → ON), so câu trả lời / trích dẫn.


## Bộ `multihop`

### 1. ✅ ĐỦ bằng chứng nhờ graph
**Câu hỏi:** Trong ba mẫu xe điện Minio Green, Herio Green và Limo Green, mẫu nào có quãng đường di chuyển 1 lần sạc đầy xa nhất theo tiêu chuẩn NEDC, và quãng đường đó là bao nhiêu km?

**Đáp án đúng:** Limo Green xa nhất với 450 km (NEDC). So sánh: Minio Green 210 km, Herio Green 326 km, Limo Green 450 km.

**Graph đóng góp đoạn:** `url_979c49b59ecf_minio-green_c001`

- 🔴 **OFF trả lời:** Trong ba mẫu xe điện Minio Green, Herio Green và Limo Green, quãng đường di chuyển 1 lần sạc đầy theo tiêu chuẩn NEDC của từng mẫu xe như sau:  - **Nerio Green**: 318,6 km [1][2]. - **Herio Green**: 326 km [3][4]. - **Limo Green**: 450 km [5][6].  Vậy mẫu xe có quãng đường di chuyển 1 lần sạc đầy xa
- 🟢 **ON trả lời:** Trong ba mẫu xe điện Minio Green, Herio Green và Limo Green, mẫu xe có quãng đường di chuyển 1 lần sạc đầy xa nhất theo tiêu chuẩn NEDC là Limo Green với quãng đường đạt 450 km [1][2].   Cụ thể: - **Minio Green**: Quãng đường di chuyển 210 km [3][4]. - **Herio Green**: Quãng đường di chuyển 326 km [

### 2. ✅ ĐỦ bằng chứng nhờ graph
**Câu hỏi:** Loại sạc treo tường (gắn tường) mà VinFast chính thức bán cho ô tô điện có giá bao nhiêu, và với loại sạc đó thì sạc từ 10% tới 70% mất khoảng bao lâu?

**Đáp án đúng:** Loại sạc treo tường VinFast chính thức bán là bộ sạc 7,4kW, có giá 10,8 triệu đồng (đã bao gồm VAT). Với loại sạc tại nhà 7,4kW này, thời gian sạc từ 10% tới 70% là khoảng 220 phút.

**Graph đóng góp đoạn:** `url_8eb05fc580e3_th-i-gian-s-c-c-a-c-c-lo-i-s-c-t-i-n-vinfast-vf-nerio-green-nh-th-n-o_c001`

- 🔴 **OFF trả lời:** - Loại sạc treo tường mà VinFast chính thức bán cho ô tô điện có giá 9,4 triệu đồng (đã bao gồm VAT) [1][2]. - Thời gian sạc từ 10% tới 70% với bộ sạc treo tường 7,4kW là khoảng 220 phút [3].
- 🟢 **ON trả lời:** - Loại sạc treo tường mà VinFast chính thức bán cho ô tô điện có giá 9,4 triệu đồng (đã bao gồm VAT) [1][2]. - Thời gian sạc từ 10% tới 70% với bộ sạc treo tường 7,4 kW là khoảng 220 phút [3].

### 3. ✅ ĐỦ bằng chứng nhờ graph
**Câu hỏi:** Trong quá trình bảo dưỡng định kỳ của VinFast, có một hạng mục mà cả ô tô điện VF e34 và xe máy điện VinFast đều cần kiểm tra. Hãy cho biết đó là hạng mục nào, và nêu mốc thay thế/kiểm tra cụ thể của hạng mục đó trên TỪNG loại xe (ô tô điện VF e34 và xe máy điện VinFast).

**Đáp án đúng:** Hạng mục chung là hệ thống phanh (dầu phanh / hệ thống phanh). Trên ô tô điện VF e34: thay mới dầu phanh sau 24.000 km hoặc 24 tháng vận hành (tùy điều kiện nào đến trước), và kiểm tra hệ thống phanh tái sinh thường xuyên. Trên xe máy điện VinFast: hệ thống phanh (phanh trước, phanh sau, tay phanh) cần được kiểm tra sau mỗi 1.000 km; tay phanh cần được bôi trơn sau mỗi 6 tháng hoặc 5.000 km.

**Graph đóng góp đoạn:** `url_ce7fadbe4cec_2-c-c-b-ph-n-c-n-b-o-d-ng-nh-k-tr-n-xe-m-y-i-n-vinfast_c001`

- 🔴 **OFF trả lời:** Trong quá trình bảo dưỡng định kỳ của VinFast, cả ô tô điện VF e34 và xe máy điện VinFast đều cần kiểm tra hạng mục "hệ thống phanh". Cụ thể về mốc thay thế/kiểm tra cho từng loại xe như sau:  ### Ô tô điện VF e34 - **Hệ thống phanh**: Cần thường xuyên kiểm tra hệ thống phanh tái sinh để đảm bảo tạo
- 🟢 **ON trả lời:** Trong quá trình bảo dưỡng định kỳ của VinFast, cả ô tô điện VF e34 và xe máy điện VinFast đều cần kiểm tra hạng mục "hệ thống phanh". Dưới đây là mốc thay thế/kiểm tra cụ thể của hạng mục này trên từng loại xe:  ### Ô tô điện VF e34 - **Hệ thống phanh**: Cần thường xuyên kiểm tra hệ thống phanh tái 

### 4. ✅ ĐỦ bằng chứng nhờ graph
**Câu hỏi:** Tài liệu nêu hai công trình kỷ lục của Vingroup gắn với thời gian thi công cực ngắn: khu nghỉ dưỡng Vinpearl Nha Trang và khu đô thị Vinhomes Riverside. Cộng tổng thời gian thi công được nêu của hai công trình này là bao nhiêu tháng?

**Đáp án đúng:** Vinpearl Nha Trang được xây dựng chỉ trong 18 tháng. Vinhomes Riverside khởi công năm 2011 và chỉ sau 8 tháng đã hình thành. Tổng thời gian thi công nêu trong tài liệu là 18 + 8 = 26 tháng.

**Graph đóng góp đoạn:** `url_3daea9e810b4_01_c003`

- 🔴 **OFF trả lời:** Tổng thời gian thi công của hai công trình Vinpearl Nha Trang và Vinhomes Riverside được nêu như sau:  - **Vinpearl Nha Trang**: Thời gian thi công là 18 tháng [1]. - **Vinhomes Riverside**: Thời gian thi công là 8 tháng [1].  Tổng cộng thời gian thi công của hai công trình là: - 18 tháng + 8 tháng 
- 🟢 **ON trả lời:** Tổng thời gian thi công của hai công trình Vinpearl Nha Trang và Vinhomes Riverside được nêu như sau:  - **Vinpearl Nha Trang**: Thời gian thi công là 18 tháng [1]. - **Vinhomes Riverside**: Thời gian thi công là 8 tháng [2].  Tổng thời gian thi công của cả hai công trình là: 18 tháng + 8 tháng = 26

### 5. ✅ ĐỦ bằng chứng nhờ graph
**Câu hỏi:** Khi gập hết các hàng ghế để mở rộng khoang chứa đồ, dung tích khoang hành lý tối đa của Minio Green so với Limo Green chênh nhau bao nhiêu lít?

**Đáp án đúng:** Minio Green khi gập hết ghế đạt 542 L; Limo Green khi gập hàng ghế thứ ba đạt 606 L. Chênh lệch 606 - 542 = 64 L (Limo Green lớn hơn).

**Graph đóng góp đoạn:** `url_979c49b59ecf_minio-green_c002`

- 🔴 **OFF trả lời:** Mình chưa tìm thấy thông tin này trong tài liệu được cung cấp.
- 🟢 **ON trả lời:** Dung tích khoang hành lý tối đa của hai mẫu xe Minio Green và Limo Green như sau:  - **Minio Green**:   - Khi gập hết ghế: 542 L [1].  - **Limo Green**:   - Khi gập hàng ghế thứ hai: 1.240 L [2][3].  Chênh lệch dung tích khoang hành lý tối đa giữa Limo Green và Minio Green là: - 1.240 L (Limo Green)

### 6. ➕ graph thêm 1 đoạn
**Câu hỏi:** Cộng tổng quãng đường đi được sau một lần sạc đầy của ba mẫu có phạm vi di chuyển cao nhất (Evo200, Feliz S, Klara S 2022) là bao nhiêu km?

**Đáp án đúng:** Evo200 đi 203km, Feliz S đi 198km, Klara S 2022 đi 194km. Tổng cộng 203 + 198 + 194 = 595km.

**Graph đóng góp đoạn:** `url_b0d0a73c8c59_1-3-xe-m-y-i-n-vinfast-klara-s-2022-i-c-194km-sau-m-t-l-n-s-c-y_c001`

- 🔴 **OFF trả lời:** Cộng tổng quãng đường đi được sau một lần sạc đầy của ba mẫu xe máy điện có phạm vi di chuyển cao nhất (Evo200, Feliz S, Klara S 2022) như sau:  - **Evo200**: có khả năng di chuyển khoảng 200 km sau một lần sạc đầy [1][2]. - **Feliz S**: có khả năng di chuyển tới 198 km sau một lần sạc đầy [3][4]. -
- 🟢 **ON trả lời:** Cộng tổng quãng đường đi được sau một lần sạc đầy của ba mẫu xe máy điện có phạm vi di chuyển cao nhất (Evo200, Feliz S, Klara S 2022) như sau:  - **Evo200**: 200 km sau một lần sạc đầy [1]. - **Feliz S**: 198 km sau một lần sạc đầy [2]. - **Klara S 2022**: 194 km sau một lần sạc đầy [3].  Tổng quãn

### 7. ➕ graph thêm 1 đoạn
**Câu hỏi:** Mẫu ô tô điện VinFast nào có thể dùng bộ sạc di động 2.2kW và 3.5kW lại đồng thời là mẫu được mô tả có hệ thống 8 loa ở bản Eco và 10 loa ở bản Plus?

**Đáp án đúng:** Đó là VinFast VF 8. Bộ sạc di động 2.2kW và 3.5kW dùng cho các dòng đang mở bán gồm VF e34, VF 8 và VF 9; trong đó VF 8 là mẫu được mô tả có hệ thống 8 loa (bản Eco) và 10 loa (bản Plus).

**Graph đóng góp đoạn:** `url_55a1dfb5ff8e_2-l-u-trong-l-n-u-s-d-ng-b-s-c-di-ng-t-i-n-vinfast-t-i-nh_c001`

- 🔴 **OFF trả lời:** Mẫu ô tô điện VinFast có thể sử dụng bộ sạc di động 2.2kW và 3.5kW, đồng thời có hệ thống 8 loa ở bản Eco và 10 loa ở bản Plus là VinFast VF 8. Cụ thể:  - **Mẫu xe**: VinFast VF 8 - **Bản Eco**: 8 loa - **Bản Plus**: 10 loa - **Bộ sạc di động**: Hỗ trợ 2.2kW và 3.5kW [1][2].
- 🟢 **ON trả lời:** Mẫu ô tô điện VinFast có thể sử dụng bộ sạc di động 2.2kW và 3.5kW, đồng thời có hệ thống 8 loa ở bản Eco và 10 loa ở bản Plus là mẫu xe VinFast VF e34. Cụ thể:  - **Bộ sạc di động**:    - Có hai loại: 2.2kW và 3.5kW, được sử dụng để sạc tại nhà hoặc các địa điểm khác [1][2].    - **Hệ thống loa**: 

### 8. ➕ graph thêm 1 đoạn
**Câu hỏi:** Một chiếc xe ô tô tải VinFast có tổng khối lượng hàng chuyên chở 25 tấn, sản xuất được 10 năm: lệ phí kiểm định một lần là bao nhiêu và chu kỳ kiểm định là bao nhiêu tháng?

**Đáp án đúng:** Lệ phí kiểm định: 570.000 VNĐ (xe tải trên 20 tấn). Chu kỳ kiểm định: 12 tháng (xe sản xuất từ 7 đến 20 năm).

**Graph đóng góp đoạn:** `url_0b0f450f89e4_3-chu-k-ng-ki-m-xe-t-c-c-lo-i_c001`

- 🔴 **OFF trả lời:** Mình chưa tìm thấy thông tin này trong tài liệu được cung cấp.
- 🟢 **ON trả lời:** Mình chưa tìm thấy thông tin này trong tài liệu được cung cấp.


## Bộ `multihop-graph`

### 9. ✅ ĐỦ bằng chứng nhờ graph
**Câu hỏi:** Hệ thống trạm sạc xe điện VinFast hiện có quy mô khoảng bao nhiêu cổng sạc, và đối với chủ cửa hàng/khu dịch vụ thì hệ thống này mang lại lợi ích gì về mặt khách hàng?

**Đáp án đúng:** Hiện nay có khoảng hơn 150.000 cổng sạc cho xe máy điện và ô tô điện VinFast (phủ sóng khắp 63 tỉnh thành); và hệ thống trạm sạc sẽ giúp thu hút hơn lượng lớn khách hàng sử dụng xe máy điện, ô tô điện đến với cửa hàng, khu dịch vụ của bạn.

**Graph đóng góp đoạn:** `url_7954a1cb52ba_1-s-c-xe-i-n-vinfast-u_c001`

- 🔴 **OFF trả lời:** Hệ thống trạm sạc xe điện VinFast hiện có quy mô khoảng 150.000 cổng sạc cho xe máy điện và ô tô điện, trải dài khắp 63 tỉnh thành tại Việt Nam [1].   Đối với chủ cửa hàng hoặc khu dịch vụ, hệ thống trạm sạc này mang lại một số lợi ích về mặt khách hàng như sau: - **Thu hút khách hàng**: Hệ thống tr
- 🟢 **ON trả lời:** Hệ thống trạm sạc xe điện VinFast hiện có quy mô khoảng hơn 150.000 cổng sạc cho xe máy điện và ô tô điện, trải dài khắp 63 tỉnh thành tại Việt Nam [1][2].   Đối với chủ cửa hàng hoặc khu dịch vụ, hệ thống trạm sạc này mang lại một số lợi ích về mặt khách hàng như sau:  - **Thu hút khách hàng**: Hệ 

### 10. ✅ ĐỦ bằng chứng nhờ graph
**Câu hỏi:** Chương trình "Kiến tạo dịch vụ 5 sao" của VinFast áp dụng cho nhóm khách hàng nào, và đến giai đoạn nào thì chương trình này được VinFast tiếp tục triển khai?

**Đáp án đúng:** Chương trình "Kiến tạo dịch vụ 5 sao" áp dụng cho khách hàng là chủ sở hữu Xe máy điện VinFast (có trải nghiệm dịch vụ tại xưởng dịch vụ chính hãng); và VinFast tiếp tục triển khai chương trình này sang giai đoạn 2 với định hướng đồng nhất chuẩn dịch vụ, nâng tầm trải nghiệm khách hàng.

**Graph đóng góp đoạn:** `url_f2b01d702eaa_tin-t-c_c001`

- 🔴 **OFF trả lời:** Chương trình "Kiến tạo dịch vụ 5 sao" của VinFast áp dụng cho các nhóm khách hàng sau:  - **Đối tượng tham gia**:    - Là chủ sở hữu xe ô tô VinFast (công dân Việt Nam) và có trải nghiệm dịch vụ tại Xưởng dịch vụ chính hãng VinFast trên toàn quốc trong thời gian triển khai chương trình [1].   - Chươ
- 🟢 **ON trả lời:** Chương trình "Kiến tạo dịch vụ 5 sao" của VinFast áp dụng cho nhóm khách hàng là:  - **Chủ sở hữu xe ô tô VinFast** (công dân Việt Nam) và có trải nghiệm dịch vụ tại Xưởng dịch vụ chính hãng VinFast trên toàn quốc trong thời gian triển khai chương trình. Chương trình không áp dụng cho khách hàng kin

### 11. ✅ ĐỦ bằng chứng nhờ graph
**Câu hỏi:** Dịch vụ cứu hộ xe VinFast kết hợp dịch vụ cứu hộ pin song song với những mô hình dịch vụ nào khác, và chính sự kết hợp cùng đội ngũ kỹ thuật đó giúp dịch vụ được người dùng đánh giá cao nhờ đáp ứng các tiêu chí cụ thể nào?

**Đáp án đúng:** Dịch vụ cứu hộ pin được triển khai song song với chính sách cứu hộ 24/7 và dịch vụ sửa chữa lưu động Mobile Service, tạo thành sự kết hợp của 3 mô hình dịch vụ. Nhờ đó, dịch vụ cứu hộ VinFast được người dùng đánh giá cao khi đáp ứng được các tiêu chí về thời gian - hệ thống trang thiết bị và giá cả tối ưu.

**Graph đóng góp đoạn:** `url_3d6edfcbc12a_1-th-i-gian-ho-t-ng-c-a-d-ch-v-c-u-h-pin-vinfast_c001`

- 🔴 **OFF trả lời:** Dịch vụ cứu hộ xe VinFast kết hợp dịch vụ cứu hộ pin với các mô hình dịch vụ khác như dịch vụ sửa chữa lưu động (Mobile Service) và chính sách cứu hộ 24/7. Sự kết hợp này cùng với đội ngũ kỹ thuật viên chuyên nghiệp đã giúp dịch vụ được người dùng đánh giá cao nhờ đáp ứng các tiêu chí cụ thể như:  -
- 🟢 **ON trả lời:** Dịch vụ cứu hộ xe VinFast kết hợp dịch vụ cứu hộ pin với các mô hình dịch vụ khác như dịch vụ sửa chữa lưu động (Mobile Service) và chính sách cứu hộ 24/7. Sự kết hợp này giúp mang lại sự an tâm cho khách hàng khi vận hành xe điện trên mọi hành trình, đặc biệt trong các tình huống xe hết pin giữa đư

### 12. ➕ graph thêm 1 đoạn
**Câu hỏi:** Xe Minio Green có quãng đường di chuyển trong 1 lần sạc đầy là bao nhiêu km theo tiêu chuẩn NEDC, và thời hạn bảo hành áp dụng cho dòng VF Minio Green là bao lâu?

**Đáp án đúng:** Minio Green có quãng đường di chuyển trong 1 lần sạc đầy đạt 210 km theo tiêu chuẩn NEDC, và thời hạn bảo hành áp dụng cho VF Minio Green là 7 năm hoặc 160.000 km (tùy điều kiện nào đến trước).

**Graph đóng góp đoạn:** `url_0261825887bc_minio-green_c001`

- 🔴 **OFF trả lời:** - Quãng đường di chuyển trong 1 lần sạc đầy của xe Minio Green đạt 210 km theo tiêu chuẩn NEDC [1]. - Thời hạn bảo hành áp dụng cho dòng xe Minio Green là 7 năm/160.000 km cho xe mới (bao gồm hệ truyền động) và 8 năm/160.000 km cho pin cao áp (mua lần đầu theo xe mới) [2].
- 🟢 **ON trả lời:** - Quãng đường di chuyển trong 1 lần sạc đầy của xe Minio Green đạt 210 km theo tiêu chuẩn NEDC [1][2]. - Thời hạn bảo hành áp dụng cho dòng VF Minio Green là:   - Bảo hành xe mới (bao gồm hệ truyền động): 7 năm hoặc 160.000 km, tùy điều kiện nào đến trước.   - Bảo hành pin cao áp (mua lần đầu theo x

### 13. ➕ graph thêm 1 đoạn
**Câu hỏi:** Đối với gói thuê pin xe máy điện VinFast, nếu khách hàng thuê 2 pin thì tổng chi phí mỗi tháng (đã bao gồm VAT) là bao nhiêu, và gói thuê pin này được gắn theo tiêu chí nào của xe?

**Đáp án đúng:** Khi thuê 2 pin, tổng chi phí là 300.000 VNĐ/tháng (tương đương mỗi pin 150.000 VNĐ/tháng, đã bao gồm VAT); và gói thuê pin được gắn theo số VIN xe, không gắn với chủ sở hữu xe.

**Graph đóng góp đoạn:** `url_2f24a1b20627_2-l-i-ch-c-a-thu-pin-xe-m-y-i-n-vinfast_c001`

- 🔴 **OFF trả lời:** - Tổng chi phí mỗi tháng cho gói thuê 2 pin xe máy điện VinFast (đã bao gồm VAT) là 300.000 VNĐ [1]. - Gói thuê pin này được gắn theo tiêu chí phù hợp với khách hàng di chuyển nhiều, chạy dịch vụ hoặc cần nguồn năng lượng dự phòng để chủ động hành trình [1].
- 🟢 **ON trả lời:** - Tổng chi phí mỗi tháng cho gói thuê 2 pin xe máy điện VinFast là 350.000 VNĐ (đã bao gồm VAT) [1]. - Gói thuê pin này được gắn theo tiêu chí của xe Vento và các dòng xe chạy pin LFP [1][2].
