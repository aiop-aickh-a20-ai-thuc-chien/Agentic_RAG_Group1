# URL Ingestion Base Evaluation

- Started: `2026-06-13T04:44:38.786043+00:00`
- Completed: `2026-06-13T04:47:56.519043+00:00`
- URLs selected: `12`
- Processed: `12`
- Passed: `6`
- Failed: `6`
- Errors: `0`
- Skipped: `0`
- Browser extractor: `True`

## Failing Or Error Samples

| # | Status | Score | URL | Main Errors |
| ---: | --- | ---: | --- | --- |
| 2 | failed | 0.947 | https://vinfastauto.com/vn_vi/thong-tin-bao-hanh | strip_navigation |
| 3 | failed | 0.905 | https://shop.vinfastauto.com/vn_vi/car-vf8.html | forbidden_text_snippet: Đăng ký nhận tin; strip_footer |
| 7 | failed | 0.895 | https://vinfastauto.com/vn_vi/tong-quan-tram-sac-vinfast | forbidden_text_snippet: Đăng ký nhận tin; strip_footer |
| 8 | failed | 0.789 | https://vinfastauto.com/vn_vi/o-to-dien-vinfast-mo-ban | chunk_count; required_metadata_keys; preserve_canonical_url; language_expected |
| 9 | failed | 0.952 | https://vinfastauto.com/vn_vi/cau-hoi-thuong-gap-ve-he-thong-tram-sac-vinfast | entity_boundary |
| 10 | failed | 0.950 | https://vinfastauto.com/vn_vi/hop-dong-va-chinh-sach/chinh-sach/cho-xe-may-dien | entity_boundary |

## Output Files

- Results JSONL: `guide\reports\url_ingestion_verification_subset_complete\base_results.jsonl`
- Summary JSON: `guide\reports\url_ingestion_verification_subset_complete\base_summary.json`
- Summary Markdown: `guide\reports\url_ingestion_verification_subset_complete\base_summary.md`
