# URL Ingestion Base Evaluation

- Started: `2026-06-13T04:37:36.461225+00:00`
- Completed: `2026-06-13T04:40:39.705548+00:00`
- URLs selected: `12`
- Processed: `12`
- Passed: `4`
- Failed: `8`
- Errors: `0`
- Skipped: `0`
- Browser extractor: `True`

## Failing Or Error Samples

| # | Status | Score | URL | Main Errors |
| ---: | --- | ---: | --- | --- |
| 2 | failed | 0.947 | https://vinfastauto.com/vn_vi/thong-tin-bao-hanh | strip_navigation |
| 3 | failed | 0.905 | https://shop.vinfastauto.com/vn_vi/car-vf8.html | forbidden_text_snippet: Hotline; strip_footer |
| 4 | failed | 0.944 | https://shop.vinfastauto.com/vn_vi/5010 | strip_navigation |
| 6 | failed | 0.737 | https://vinfastauto.com/vn_vi/gia-cuu-ho-o-to-dien-vinfast | required_text_snippet: gia cuu dien vinfast; forbidden_text_snippet: Hotline; forbidden_text_snippet: Support; strip_navigation; strip_footer |
| 7 | failed | 0.895 | https://vinfastauto.com/vn_vi/tong-quan-tram-sac-vinfast | forbidden_text_snippet: Support; strip_navigation |
| 8 | failed | 0.842 | https://vinfastauto.com/vn_vi/o-to-dien-vinfast-mo-ban | required_text_snippet: dien vinfast ban; forbidden_text_snippet: Support; strip_navigation |
| 9 | failed | 0.762 | https://vinfastauto.com/vn_vi/cau-hoi-thuong-gap-ve-he-thong-tram-sac-vinfast | required_text_snippet: cau hoi thuong gap thong; forbidden_text_snippet: Đăng nhập; forbidden_text_snippet: Support; strip_navigation; entity_boundary |
| 10 | failed | 0.900 | https://vinfastauto.com/vn_vi/hop-dong-va-chinh-sach/chinh-sach/cho-xe-may-dien | required_text_snippet: cho may dien; entity_boundary |

## Output Files

- Results JSONL: `guide\reports\url_ingestion_verification_subset_final\base_results.jsonl`
- Summary JSON: `guide\reports\url_ingestion_verification_subset_final\base_summary.json`
- Summary Markdown: `guide\reports\url_ingestion_verification_subset_final\base_summary.md`
