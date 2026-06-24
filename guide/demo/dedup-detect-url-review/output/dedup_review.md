# URL Dedup Detection Review

## Inputs

- URL count: 28
- Total chunks: 83
- Exact enabled: True
- SimHash enabled: True
- Embedding enabled: True
- SimHash threshold: 6
- Embedding threshold: 0.92

## URL Ingestion Summary

| # | Status | Chunks | Markdown chars | Parser | URL |
| ---: | --- | ---: | ---: | --- | --- |
| 1 | ok | 1 | 1076 |  | https://shop.vinfastauto.com/vn_vi/ACS10000002.html |
| 2 | ok | 4 | 1555 |  | https://shop.vinfastauto.com/vn_vi/ACS10000005.html |
| 3 | ok | 4 | 1479 |  | https://shop.vinfastauto.com/vn_vi/ACS10000006.html |
| 4 | ok | 4 | 1902 |  | https://shop.vinfastauto.com/vn_vi/ACS10000007.html |
| 5 | ok | 4 | 1421 |  | https://shop.vinfastauto.com/vn_vi/ACS10000008.html |
| 6 | ok | 4 | 1549 |  | https://shop.vinfastauto.com/vn_vi/ACS10000009.html |
| 7 | ok | 4 | 1617 |  | https://shop.vinfastauto.com/vn_vi/ACS10000010.html |
| 8 | ok | 1 | 1000 |  | https://shop.vinfastauto.com/vn_vi/5001 |
| 9 | ok | 1 | 945 |  | https://shop.vinfastauto.com/vn_vi/5002 |
| 10 | ok | 1 | 1006 |  | https://shop.vinfastauto.com/vn_vi/5003 |
| 11 | ok | 1 | 808 |  | https://shop.vinfastauto.com/vn_vi/5004 |
| 12 | ok | 1 | 957 |  | https://shop.vinfastauto.com/vn_vi/5005 |
| 13 | ok | 1 | 843 |  | https://shop.vinfastauto.com/vn_vi/5006 |
| 14 | ok | 1 | 988 |  | https://shop.vinfastauto.com/vn_vi/5007 |
| 15 | ok | 3 | 1422 |  | https://shop.vinfastauto.com/vn_vi/INSULATIONFILMCEILINGVF7.html |
| 16 | ok | 3 | 1557 |  | https://shop.vinfastauto.com/vn_vi/INSULATIONFILMCEILINGVF8.html |
| 17 | ok | 3 | 1441 |  | https://shop.vinfastauto.com/vn_vi/INSULATIONFILMCEILINGVF9.html |
| 18 | ok | 7 | 4274 |  | https://shop.vinfastauto.com/vn_vi/dat-coc-xe-dien-vf3.html |
| 19 | ok | 5 | 3547 |  | https://shop.vinfastauto.com/vn_vi/dat-coc-xe-dien-vf5.html |
| 20 | ok | 5 | 2664 |  | https://shop.vinfastauto.com/vn_vi/dat-coc-xe-dien-vf6.html |
| 21 | ok | 10 | 7060 |  | https://shop.vinfastauto.com/vn_vi/dat-coc-xe-dien-vf7.html |
| 22 | ok | 3 | 3549 |  | https://shop.vinfastauto.com/vn_vi/dat-coc-xe-dien-vfe34.html |
| 23 | ok | 2 | 3748 |  | https://vinfastauto.com/vn_vi/cau-hoi-thuong-gap/cau-hoi-xe-may-dien/san-pham/evo-grand-lite |
| 24 | ok | 1 | 2050 |  | https://vinfastauto.com/vn_vi/cau-hoi-thuong-gap/cau-hoi-xe-may-dien/san-pham/evo-lite-neo |
| 25 | ok | 2 | 3778 |  | https://vinfastauto.com/vn_vi/cau-hoi-thuong-gap/cau-hoi-xe-may-dien/san-pham/feliz-2025 |
| 26 | ok | 2 | 3633 |  | https://vinfastauto.com/vn_vi/cau-hoi-thuong-gap/cau-hoi-xe-may-dien/san-pham/feliz-lite |
| 27 | ok | 2 | 675 |  | https://vinfastauto.com/vn_vi/cau-hoi-thuong-gap/cau-hoi-xe-may-dien/san-pham/klara-s |
| 28 | ok | 3 | 2720 |  | https://vinfastauto.com/vn_vi/cau-hoi-thuong-gap/cau-hoi-xe-may-dien/san-pham/theon-s |

## Duplicate Counts

- Exact matches: 1
- SimHash matches: 6
- Embedding matches: 10

## Exact Matches

| Layer | Score | Distance | Left chunk | Right chunk | Left preview | Right preview |
| --- | ---: | ---: | --- | --- | --- | --- |
| exact_sha256 | 1.0000 |  | url_af47f4447d39_m-t-s-n-ph-m_c001 | url_4b5932cf32dd_m-t-s-n-ph-m_c001 | ### Mô tả sản phẩm SẢN PHẨM GÓI DÁN FILM CÁCH NHIỆT VF x 3M Với triết lý “Đặt khách hàng làm trọng tâm”, VinFast không ngừng sáng tạo để tạo ra các sản phẩm đẳng cấp và trải ngh... | ### Mô tả sản phẩm SẢN PHẨM GÓI DÁN FILM CÁCH NHIỆT VF x 3M Với triết lý “Đặt khách hàng làm trọng tâm”, VinFast không ngừng sáng tạo để tạo ra các sản phẩm đẳng cấp và trải ngh... |

## SimHash Matches

| Layer | Score | Distance | Left chunk | Right chunk | Left preview | Right preview |
| --- | ---: | ---: | --- | --- | --- | --- |
| simhash | 0.9375 | 4 | url_576c19489788_s-n-ph-m-t-ng-t_c001 | url_9ab039da74f7_s-n-ph-m-t-ng-t_c001 | ### Sản phẩm tương tự - Tấm Che Nắng Cửa VinFast VF 8: 540.000 VNĐ - Cốp Nóc Phi Thuyền ô tô VinFast VF 8: Tạm hết hàng - Gói Dán Film Cách Nhiệt VinFast VF 8: Nhận tại showroom... | ### Sản phẩm tương tự - Tấm Che Nắng Cửa VinFast VF 8: 540.000 VNĐ - Cốp Nóc Phi Thuyền ô tô VinFast VF 8: Tạm hết hàng - Thảm Sàn Nhựa 2D VF 8: 2.210.000 VNĐ - Gói Dán Film Các... |
| simhash | 0.9531 | 3 | url_41e129546ab4_th-ng-tin-chi-ti-t_c001 | url_9fefe496b741_th-ng-tin-chi-ti-t_c001 | ### Thông tin chi tiết Sản phẩm được làm từ nhựa TPE nguyên sinh cao cấp, không gây mùi hôi khó chịu và an toàn cho sức khỏe. Chất liệu nhựa TPE cao cấp giúp bảo vệ sàn cốp trướ... | ### Thông tin chi tiết Sản phẩm được làm từ nhựa TPE nguyên sinh cao cấp, không gây mùi hôi khó chịu và an toàn cho sức khỏe. Chất liệu nhựa TPE cao cấp giúp bảo vệ sàn cốp trướ... |
| simhash | 0.9219 | 5 | url_9fefe496b741_th-ng-tin-chi-ti-t_c001 | url_9ab039da74f7_th-ng-tin-chi-ti-t_c001 | ### Thông tin chi tiết Sản phẩm được làm từ nhựa TPE nguyên sinh cao cấp, không gây mùi hôi khó chịu và an toàn cho sức khỏe. Chất liệu nhựa TPE cao cấp giúp bảo vệ sàn cốp trướ... | ### Thông tin chi tiết Sản phẩm được làm từ nhựa TPE nguyên sinh cao cấp, không gây mùi hôi khó chịu và an toàn cho sức khỏe. Chất liệu nhựa TPE cao cấp giúp bảo vệ sàn cốp trướ... |
| simhash | 0.9375 | 4 | url_af47f4447d39_m-t-s-n-ph-m_c001 | url_a6303bd62393_m-t-s-n-ph-m_c001 | ### Mô tả sản phẩm SẢN PHẨM GÓI DÁN FILM CÁCH NHIỆT VF x 3M Với triết lý “Đặt khách hàng làm trọng tâm”, VinFast không ngừng sáng tạo để tạo ra các sản phẩm đẳng cấp và trải ngh... | ### Mô tả sản phẩm SẢN PHẨM GÓI DÁN FILM CÁCH NHIỆT VF x 3M Với triết lý “Đặt khách hàng làm trọng tâm”, VinFast không ngừng sáng tạo để tạo ra các sản phẩm đẳng cấp và trải ngh... |
| simhash | 0.9375 | 4 | url_a6303bd62393_m-t-s-n-ph-m_c001 | url_4b5932cf32dd_m-t-s-n-ph-m_c001 | ### Mô tả sản phẩm SẢN PHẨM GÓI DÁN FILM CÁCH NHIỆT VF x 3M Với triết lý “Đặt khách hàng làm trọng tâm”, VinFast không ngừng sáng tạo để tạo ra các sản phẩm đẳng cấp và trải ngh... | ### Mô tả sản phẩm SẢN PHẨM GÓI DÁN FILM CÁCH NHIỆT VF x 3M Với triết lý “Đặt khách hàng làm trọng tâm”, VinFast không ngừng sáng tạo để tạo ra các sản phẩm đẳng cấp và trải ngh... |
| simhash | 0.9062 | 6 | url_1bbafe5353e6_c-u-h-i-th-ng-g-p-v-xe-m-y-i-n-vinfast-klara-s_c001 | url_25169e5b4cf2_c-u-h-i-th-ng-g-p-v-xe-m-y-i-n-vinfast-theon-s_c001 | # Câu hỏi thường gặp về xe máy điện VinFast Klara S Câu hỏi thường gặp về xe máy điện & ô tô VinFast \| VinFast | # Câu hỏi thường gặp về xe máy điện VinFast Theon S Câu hỏi thường gặp về xe máy điện & ô tô VinFast \| VinFast |

## Embedding Matches

| Layer | Score | Distance | Left chunk | Right chunk | Left preview | Right preview |
| --- | ---: | ---: | --- | --- | --- | --- |
| embedding_similarity | 0.9594 |  | url_14dca2f93906_s-n-ph-m-t-ng-t_c001 | url_41e129546ab4_s-n-ph-m-t-ng-t_c001 | ### Sản phẩm tương tự - Thảm Cốp 3D VF 5: 990.000 VNĐ - Tấm Che Nắng Cửa VinFast VF 5: 495.000 VNĐ - Gói Dán Film Cách Nhiệt VinFast VF 5: Nhận tại showroom / Tạm hết hàng - VF ... | ### Sản phẩm tương tự - Thảm Sàn Nhựa 2D VF 5: 1.969.000 VNĐ - Tấm Che Nắng Cửa VinFast VF 5: 495.000 VNĐ - Gói Dán Film Cách Nhiệt VinFast VF 5: Nhận tại showroom / Tạm hết hàn... |
| embedding_similarity | 0.9941 |  | url_3a5a8a334b10_s-n-ph-m-t-ng-t_c001 | url_9fefe496b741_s-n-ph-m-t-ng-t_c001 | ### Sản phẩm tương tự - Thảm Sàn Nhựa VinFast Nerio Green: Tạm hết hàng - Gói Dán Film Cách Nhiệt VinFast Nerio Green: Nhận tại showroom Tạm hết hàng - Tấm Che Nắng Cửa VinFast ... | ### Sản phẩm tương tự - Thảm Sàn Nhựa VinFast Nerio Green: Tạm hết hàng - Gói Dán Film Cách Nhiệt VinFast Nerio Green: Nhận tại showroom Tạm hết hàng - Tấm Che Nắng Cửa VinFast ... |
| embedding_similarity | 0.9285 |  | url_41e129546ab4_m-t-s-n-ph-m_c001 | url_9ab039da74f7_m-t-s-n-ph-m_c001 | ### Mô tả sản phẩm Thảm lót cốp 3D VinFast VF 5 được sản xuất với chất liệu nhựa TPE cao cấp. Sản phẩm được thiết kế đặc biệt cho dòng xe VinFast VF 5. Thảm lót cốp thiết kế ngu... | ### Mô tả sản phẩm Thảm lót cốp 3D VinFast VF 8 được sản xuất với chất liệu nhựa TPE cao cấp. Sản phẩm được thiết kế đặc biệt cho dòng xe VinFast VF 8. Thảm lót cốp thiết kế ngu... |
| embedding_similarity | 0.9763 |  | url_41e129546ab4_th-ng-tin-chi-ti-t_c001 | url_9ab039da74f7_th-ng-tin-chi-ti-t_c001 | ### Thông tin chi tiết Sản phẩm được làm từ nhựa TPE nguyên sinh cao cấp, không gây mùi hôi khó chịu và an toàn cho sức khỏe. Chất liệu nhựa TPE cao cấp giúp bảo vệ sàn cốp trướ... | ### Thông tin chi tiết Sản phẩm được làm từ nhựa TPE nguyên sinh cao cấp, không gây mùi hôi khó chịu và an toàn cho sức khỏe. Chất liệu nhựa TPE cao cấp giúp bảo vệ sàn cốp trướ... |
| embedding_similarity | 0.9355 |  | url_da089c213ff3_danh-m-c-s-n-ph-m_c001 | url_263224b30384_danh-m-c-s-n-ph-m_c001 | ### DANH MỤC SẢN PHẨM - Sản phẩm mới - Phong cách sống Phụ kiện ô tô điện - Phụ kiện VF 9 - Phụ kiện VF 8 - Phụ kiện VF 7 - Phụ kiện VF 6 - Phụ kiện Nerio Green - Phụ kiện Limo ... | ### DANH MỤC SẢN PHẨM - Sản phẩm mới - Phong cách sống Phụ kiện ô tô điện - Phụ kiện VF 9 - Phụ kiện VF 8 - Phụ kiện VF 7 - Phụ kiện VF 6 - Phụ kiện Nerio Green - Phụ kiện Limo ... |
| embedding_similarity | 0.9215 |  | url_263224b30384_danh-m-c-s-n-ph-m_c001 | url_bb8316c78e8e_danh-m-c-s-n-ph-m_c001 | ### DANH MỤC SẢN PHẨM - Sản phẩm mới - Phong cách sống Phụ kiện ô tô điện - Phụ kiện VF 9 - Phụ kiện VF 8 - Phụ kiện VF 7 - Phụ kiện VF 6 - Phụ kiện Nerio Green - Phụ kiện Limo ... | ### DANH MỤC SẢN PHẨM - Sản phẩm mới - Phong cách sống Phụ kiện ô tô điện - Phụ kiện VF 9 - Phụ kiện VF 8 - Phụ kiện VF 7 - Phụ kiện VF 6 - Phụ kiện Nerio Green - Phụ kiện Limo ... |
| embedding_similarity | 0.9308 |  | url_b2072da96c82_danh-m-c-s-n-ph-m_c001 | url_bb8316c78e8e_danh-m-c-s-n-ph-m_c001 | ### DANH MỤC SẢN PHẨM - Sản phẩm mới - Phong cách sống Phụ kiện ô tô điện - Phụ kiện VF 9 - Phụ kiện VF 8 - Phụ kiện VF 7 - Phụ kiện VF 6 - Phụ kiện Nerio Green - Phụ kiện Limo ... | ### DANH MỤC SẢN PHẨM - Sản phẩm mới - Phong cách sống Phụ kiện ô tô điện - Phụ kiện VF 9 - Phụ kiện VF 8 - Phụ kiện VF 7 - Phụ kiện VF 6 - Phụ kiện Nerio Green - Phụ kiện Limo ... |
| embedding_similarity | 0.9731 |  | url_af47f4447d39_g-i-film-c-ch-nhi-t-d-n-tr-n-vinfast-vf-7_c001 | url_a6303bd62393_g-i-film-c-ch-nhi-t-d-n-tr-n-vinfast-vf-8_c001 | # Gói Film Cách Nhiệt Dán Trần VinFast VF 7 5.625.000 VNĐ Chọn gói - Premium - First Royal Nhận tại showroom | # Gói Film Cách Nhiệt Dán Trần VinFast VF 8 5.625.000 VNĐ Chọn gói - Premium - First Royal Nhận tại showroom |
| embedding_similarity | 0.9707 |  | url_af47f4447d39_g-i-film-c-ch-nhi-t-d-n-tr-n-vinfast-vf-7_c001 | url_4b5932cf32dd_g-i-film-c-ch-nhi-t-d-n-tr-n-vinfast-vf-9_c001 | # Gói Film Cách Nhiệt Dán Trần VinFast VF 7 5.625.000 VNĐ Chọn gói - Premium - First Royal Nhận tại showroom | # Gói Film Cách Nhiệt Dán Trần VinFast VF 9 7.875.000 VNĐ Chọn gói - Premium - First Royal Nhận tại showroom |
| embedding_similarity | 0.9714 |  | url_a6303bd62393_g-i-film-c-ch-nhi-t-d-n-tr-n-vinfast-vf-8_c001 | url_4b5932cf32dd_g-i-film-c-ch-nhi-t-d-n-tr-n-vinfast-vf-9_c001 | # Gói Film Cách Nhiệt Dán Trần VinFast VF 8 5.625.000 VNĐ Chọn gói - Premium - First Royal Nhận tại showroom | # Gói Film Cách Nhiệt Dán Trần VinFast VF 9 7.875.000 VNĐ Chọn gói - Premium - First Royal Nhận tại showroom |
