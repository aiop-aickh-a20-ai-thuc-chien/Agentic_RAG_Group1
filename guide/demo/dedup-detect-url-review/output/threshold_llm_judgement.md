# Dedup Threshold LLM Judgement

## Best Choice

- Layer 2 SimHash threshold: 2
- Layer 3 embedding threshold: 0.86
- Precision: 0.526316
- Recall: 0.909091
- F1: 0.666667
- TP/FP/FN/TN: 20/18/2/52

This choice has the highest F1 score, indicating a good balance between precision and recall.

### FP IDs

- `url_af47f4447d39_g-i-film-c-ch-nhi-t-d-n-tr-n-vinfast-vf-7_c001 <-> url_a6303bd62393_g-i-film-c-ch-nhi-t-d-n-tr-n-vinfast-vf-8_c001`
- `url_41e129546ab4_th-m-c-p-3d-vf-5_c001 <-> url_9ab039da74f7_th-m-c-p-3d-vf-8_c001`
- `url_af47f4447d39_g-i-film-c-ch-nhi-t-d-n-tr-n-vinfast-vf-7_c001 <-> url_4b5932cf32dd_g-i-film-c-ch-nhi-t-d-n-tr-n-vinfast-vf-9_c001`
- `url_14dca2f93906_m-t-s-n-ph-m_c001 <-> url_576c19489788_m-t-s-n-ph-m_c001`
- `url_da089c213ff3_danh-m-c-s-n-ph-m_c001 <-> url_b2072da96c82_danh-m-c-s-n-ph-m_c001`
- `url_a6303bd62393_g-i-film-c-ch-nhi-t-d-n-tr-n-vinfast-vf-8_c001 <-> url_4b5932cf32dd_g-i-film-c-ch-nhi-t-d-n-tr-n-vinfast-vf-9_c001`
- `url_14dca2f93906_th-ng-tin-chi-ti-t_c001 <-> url_576c19489788_th-ng-tin-chi-ti-t_c001`
- `url_41e129546ab4_m-t-s-n-ph-m_c001 <-> url_9fefe496b741_m-t-s-n-ph-m_c001`
- `url_41e129546ab4_m-t-s-n-ph-m_c001 <-> url_9ab039da74f7_m-t-s-n-ph-m_c001`
- `url_da089c213ff3_danh-m-c-s-n-ph-m_c001 <-> url_98e6d571d228_danh-m-c-s-n-ph-m_c001`
- `url_da089c213ff3_danh-m-c-s-n-ph-m_c001 <-> url_bb8316c78e8e_danh-m-c-s-n-ph-m_c001`
- `url_263224b30384_danh-m-c-s-n-ph-m_c001 <-> url_b2072da96c82_danh-m-c-s-n-ph-m_c001`
- `url_263224b30384_danh-m-c-s-n-ph-m_c001 <-> url_98e6d571d228_danh-m-c-s-n-ph-m_c001`
- `url_263224b30384_danh-m-c-s-n-ph-m_c001 <-> url_bb8316c78e8e_danh-m-c-s-n-ph-m_c001`
- `url_b2072da96c82_danh-m-c-s-n-ph-m_c001 <-> url_98e6d571d228_danh-m-c-s-n-ph-m_c001`
- `url_b2072da96c82_danh-m-c-s-n-ph-m_c001 <-> url_e6d6418f6309_danh-m-c-s-n-ph-m_c001`
- `url_98e6d571d228_danh-m-c-s-n-ph-m_c001 <-> url_e6d6418f6309_danh-m-c-s-n-ph-m_c001`
- `url_e6d6418f6309_danh-m-c-s-n-ph-m_c001 <-> url_bb8316c78e8e_danh-m-c-s-n-ph-m_c001`

### FN IDs

- `url_a3bdef93d1e7_ng-k-th-nh-c-ng_c001 <-> url_97c0d5b92fd0_ng-k-th-nh-c-ng_c001`
- `url_a3bdef93d1e7_ng-k-th-nh-c-ng_c001 <-> url_9dd8e94fee25_ng-k-th-nh-c-ng_c001`

## Optimized Choice

- Layer 2 SimHash threshold: 2
- Layer 3 embedding threshold: 0.88
- Precision: 0.545455
- Recall: 0.818182
- F1: 0.654545
- TP/FP/FN/TN: 18/15/4/55

This choice provides a better precision while maintaining a reasonable recall, making it suitable for deployment.

### FP IDs

- `url_af47f4447d39_g-i-film-c-ch-nhi-t-d-n-tr-n-vinfast-vf-7_c001 <-> url_a6303bd62393_g-i-film-c-ch-nhi-t-d-n-tr-n-vinfast-vf-8_c001`
- `url_41e129546ab4_th-m-c-p-3d-vf-5_c001 <-> url_9ab039da74f7_th-m-c-p-3d-vf-8_c001`
- `url_af47f4447d39_g-i-film-c-ch-nhi-t-d-n-tr-n-vinfast-vf-7_c001 <-> url_4b5932cf32dd_g-i-film-c-ch-nhi-t-d-n-tr-n-vinfast-vf-9_c001`
- `url_14dca2f93906_m-t-s-n-ph-m_c001 <-> url_576c19489788_m-t-s-n-ph-m_c001`
- `url_da089c213ff3_danh-m-c-s-n-ph-m_c001 <-> url_b2072da96c82_danh-m-c-s-n-ph-m_c001`
- `url_a6303bd62393_g-i-film-c-ch-nhi-t-d-n-tr-n-vinfast-vf-8_c001 <-> url_4b5932cf32dd_g-i-film-c-ch-nhi-t-d-n-tr-n-vinfast-vf-9_c001`
- `url_14dca2f93906_th-ng-tin-chi-ti-t_c001 <-> url_576c19489788_th-ng-tin-chi-ti-t_c001`
- `url_41e129546ab4_m-t-s-n-ph-m_c001 <-> url_9fefe496b741_m-t-s-n-ph-m_c001`
- `url_41e129546ab4_m-t-s-n-ph-m_c001 <-> url_9ab039da74f7_m-t-s-n-ph-m_c001`
- `url_da089c213ff3_danh-m-c-s-n-ph-m_c001 <-> url_98e6d571d228_danh-m-c-s-n-ph-m_c001`
- `url_da089c213ff3_danh-m-c-s-n-ph-m_c001 <-> url_bb8316c78e8e_danh-m-c-s-n-ph-m_c001`
- `url_263224b30384_danh-m-c-s-n-ph-m_c001 <-> url_b2072da96c82_danh-m-c-s-n-ph-m_c001`
- `url_263224b30384_danh-m-c-s-n-ph-m_c001 <-> url_98e6d571d228_danh-m-c-s-n-ph-m_c001`
- `url_263224b30384_danh-m-c-s-n-ph-m_c001 <-> url_bb8316c78e8e_danh-m-c-s-n-ph-m_c001`
- `url_b2072da96c82_danh-m-c-s-n-ph-m_c001 <-> url_98e6d571d228_danh-m-c-s-n-ph-m_c001`
- `url_b2072da96c82_danh-m-c-s-n-ph-m_c001 <-> url_e6d6418f6309_danh-m-c-s-n-ph-m_c001`
- `url_98e6d571d228_danh-m-c-s-n-ph-m_c001 <-> url_e6d6418f6309_danh-m-c-s-n-ph-m_c001`
- `url_e6d6418f6309_danh-m-c-s-n-ph-m_c001 <-> url_bb8316c78e8e_danh-m-c-s-n-ph-m_c001`

### FN IDs

- `url_a3bdef93d1e7_ng-k-th-nh-c-ng_c001 <-> url_97c0d5b92fd0_ng-k-th-nh-c-ng_c001`
- `url_a3bdef93d1e7_ng-k-th-nh-c-ng_c001 <-> url_9dd8e94fee25_ng-k-th-nh-c-ng_c001`

## Compromised Choice

- Layer 2 SimHash threshold: 2
- Layer 3 embedding threshold: 0.9
- Precision: 0.571429
- Recall: 0.545455
- F1: 0.55814
- TP/FP/FN/TN: 12/9/10/61

This choice offers a compromise with slightly better precision but lower recall, which may be acceptable in certain scenarios.

### FP IDs

- `url_af47f4447d39_g-i-film-c-ch-nhi-t-d-n-tr-n-vinfast-vf-7_c001 <-> url_a6303bd62393_g-i-film-c-ch-nhi-t-d-n-tr-n-vinfast-vf-8_c001`
- `url_41e129546ab4_th-m-c-p-3d-vf-5_c001 <-> url_9ab039da74f7_th-m-c-p-3d-vf-8_c001`
- `url_af47f4447d39_g-i-film-c-ch-nhi-t-d-n-tr-n-vinfast-vf-7_c001 <-> url_4b5932cf32dd_g-i-film-c-ch-nhi-t-d-n-tr-n-vinfast-vf-9_c001`
- `url_14dca2f93906_m-t-s-n-ph-m_c001 <-> url_576c19489788_m-t-s-n-ph-m_c001`
- `url_da089c213ff3_danh-m-c-s-n-ph-m_c001 <-> url_b2072da96c82_danh-m-c-s-n-ph-m_c001`
- `url_a6303bd62393_g-i-film-c-ch-nhi-t-d-n-tr-n-vinfast-vf-8_c001 <-> url_4b5932cf32dd_g-i-film-c-ch-nhi-t-d-n-tr-n-vinfast-vf-9_c001`
- `url_14dca2f93906_th-ng-tin-chi-ti-t_c001 <-> url_576c19489788_th-ng-tin-chi-ti-t_c001`
- `url_41e129546ab4_m-t-s-n-ph-m_c001 <-> url_9fefe496b741_m-t-s-n-ph-m_c001`
- `url_41e129546ab4_m-t-s-n-ph-m_c001 <-> url_9ab039da74f7_m-t-s-n-ph-m_c001`
- `url_da089c213ff3_danh-m-c-s-n-ph-m_c001 <-> url_98e6d571d228_danh-m-c-s-n-ph-m_c001`
- `url_da089c213ff3_danh-m-c-s-n-ph-m_c001 <-> url_bb8316c78e8e_danh-m-c-s-n-ph-m_c001`
- `url_263224b30384_danh-m-c-s-n-ph-m_c001 <-> url_b2072da96c82_danh-m-c-s-n-ph-m_c001`
- `url_263224b30384_danh-m-c-s-n-ph-m_c001 <-> url_98e6d571d228_danh-m-c-s-n-ph-m_c001`
- `url_263224b30384_danh-m-c-s-n-ph-m_c001 <-> url_bb8316c78e8e_danh-m-c-s-n-ph-m_c001`
- `url_b2072da96c82_danh-m-c-s-n-ph-m_c001 <-> url_98e6d571d228_danh-m-c-s-n-ph-m_c001`
- `url_b2072da96c82_danh-m-c-s-n-ph-m_c001 <-> url_e6d6418f6309_danh-m-c-s-n-ph-m_c001`
- `url_98e6d571d228_danh-m-c-s-n-ph-m_c001 <-> url_e6d6418f6309_danh-m-c-s-n-ph-m_c001`
- `url_e6d6418f6309_danh-m-c-s-n-ph-m_c001 <-> url_bb8316c78e8e_danh-m-c-s-n-ph-m_c001`

### FN IDs

- `url_a3bdef93d1e7_ng-k-th-nh-c-ng_c001 <-> url_97c0d5b92fd0_ng-k-th-nh-c-ng_c001`
- `url_a3bdef93d1e7_ng-k-th-nh-c-ng_c001 <-> url_9dd8e94fee25_ng-k-th-nh-c-ng_c001`

## Worst Choice

- Layer 2 SimHash threshold: 40
- Layer 3 embedding threshold: None
- Precision: 0.23913
- Recall: 1.0
- F1: 0.385965
- TP/FP/FN/TN: 22/70/0/0

This choice has a very low precision, leading to a high number of false positives, which is detrimental for duplicate detection.

### FP IDs

None.

### FN IDs

None.

## Decision Notes

The tradeoff between false positives and false negatives is critical in duplicate detection. High false positives can merge unrelated items, while high false negatives can leave duplicates in the corpus. The best choice balances these risks effectively.

## Follow-Up Labeling Advice

Consider reviewing the false positives and false negatives identified in the best choice to improve the model further. Labeling additional data points may help refine the thresholds.
