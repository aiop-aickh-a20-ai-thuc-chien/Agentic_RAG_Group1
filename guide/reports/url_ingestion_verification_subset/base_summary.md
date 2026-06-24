# URL Ingestion Base Evaluation

- Started: `2026-06-13T04:23:40.499281+00:00`
- Completed: `2026-06-13T04:26:20.063006+00:00`
- URLs selected: `12`
- Processed: `12`
- Passed: `1`
- Failed: `9`
- Errors: `2`
- Skipped: `0`
- Browser extractor: `True`

## Failing Or Error Samples

| # | Status | Score | URL | Main Errors |
| ---: | --- | ---: | --- | --- |
| 1 | failed | 0.952 | https://shop.vinfastauto.com/vn_vi/EEP73111000AA.html | required_text_snippet: EEP73111000AA |
| 2 | error | 0.000 | https://vinfastauto.com/vn_vi/thong-tin-bao-hanh | RuntimeError: Failed to fetch URL https://vinfastauto.com/vn_vi/thong-tin-bao-hanh: HTTP 403 |
| 3 | failed | 0.857 | https://shop.vinfastauto.com/vn_vi/car-vf8.html | required_text_snippet: car vf8; forbidden_text_snippet: Hotline; strip_footer |
| 4 | failed | 0.944 | https://shop.vinfastauto.com/vn_vi/5010 | strip_navigation |
| 5 | failed | 0.952 | https://shop.vinfastauto.com/vn_vi/UltraLightSafetyHelmet.html | required_text_snippet: UltraLightSafetyHelmet |
| 6 | error | 0.000 | https://vinfastauto.com/vn_vi/gia-cuu-ho-o-to-dien-vinfast | RuntimeError: Failed to fetch URL https://vinfastauto.com/vn_vi/gia-cuu-ho-o-to-dien-vinfast: HTTP 403 |
| 7 | failed | 0.842 | https://vinfastauto.com/vn_vi/tong-quan-tram-sac-vinfast | required_text_snippet: tong quan tram sac vinfast; forbidden_text_snippet: Support; strip_navigation |
| 8 | failed | 0.842 | https://vinfastauto.com/vn_vi/o-to-dien-vinfast-mo-ban | required_text_snippet: dien vinfast ban; forbidden_text_snippet: Support; strip_navigation |
| 9 | failed | 0.762 | https://vinfastauto.com/vn_vi/cau-hoi-thuong-gap-ve-he-thong-tram-sac-vinfast | required_text_snippet: cau hoi thuong gap thong; forbidden_text_snippet: Đăng nhập; forbidden_text_snippet: Support; strip_navigation; entity_boundary |
| 10 | failed | 0.900 | https://vinfastauto.com/vn_vi/hop-dong-va-chinh-sach/chinh-sach/cho-xe-may-dien | required_text_snippet: cho may dien; entity_boundary |
| 11 | failed | 0.789 | https://vinfastauto.com/vn_vi/limo-green | chunk_count; required_metadata_keys; preserve_canonical_url; language_expected |

## Output Files

- Results JSONL: `guide\reports\url_ingestion_verification_subset\base_results.jsonl`
- Summary JSON: `guide\reports\url_ingestion_verification_subset\base_summary.json`
- Summary Markdown: `guide\reports\url_ingestion_verification_subset\base_summary.md`
