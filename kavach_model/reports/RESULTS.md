# Executed results

Release status: **withheld**. Locked classifier: **mixed_isotonic**.

| model | rows | positives | auc | ap | brier | brier_skill | anomaly_pct_mae | anomaly_pct_rmse | anomaly_pct_r2 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| lightgbm_label20 | 260 | 8 | 0.6622 | 0.084792 | 0.029924 | 0.0023863 | 9.8325 | 14.09 | -0.081935 |
| linear_isotonic | 260 | 12 | 0.65675 | 0.083122 | 0.043645 | 0.012953 | 9.9185 | 13.825 | -0.041565 |
| mixed_isotonic | 260 | 12 | 0.58787 | 0.19718 | 0.043656 | 0.012696 | 9.6659 | 13.626 | -0.011774 |
| lightgbm_isotonic | 260 | 12 | 0.58182 | 0.064462 | 0.044036 | 0.004108 | 9.8325 | 14.09 | -0.081935 |
| stack | 260 | 12 | 0.50638 | 0.065709 | 0.044061 | 0.0035424 | 9.7825 | 13.702 | -0.023126 |
| lightgbm_season_isotonic | 260 | 12 | 0.53646 | 0.053016 | 0.044183 | 0.00078959 | 9.8794 | 14.212 | -0.10072 |
| mixed | 260 | 12 | 0.68548 | 0.11212 | 0.0442 | 0.00040156 | 9.6659 | 13.626 | -0.011774 |
| base_rate | 260 | 12 | 0.44758 | 0.047436 | 0.044218 | 0 | 9.5793 | 13.622 | -0.011275 |
| stack_isotonic | 260 | 12 | 0.43011 | 0.045833 | 0.04438 | -0.0036666 | 9.7825 | 13.702 | -0.023126 |
| xgboost_isotonic | 260 | 12 | 0.47883 | 0.04472 | 0.044421 | -0.0045898 | 9.5122 | 13.807 | -0.038871 |
| lightgbm_without_climate | 260 | 12 | 0.56754 | 0.079015 | 0.044659 | -0.0099873 | 9.9778 | 14.072 | -0.079105 |
| lightgbm_without_memory_spatial | 260 | 12 | 0.59173 | 0.06719 | 0.044669 | -0.010195 | 10.213 | 14.497 | -0.14529 |
| lightgbm | 260 | 12 | 0.62769 | 0.075639 | 0.044675 | -0.010343 | 9.8325 | 14.09 | -0.081935 |
| catboost | 260 | 12 | 0.44355 | 0.061258 | 0.044692 | -0.01072 | 9.3972 | 13.469 | 0.011389 |
| lightgbm_without_cyclone | 260 | 12 | 0.62332 | 0.074718 | 0.044741 | -0.01184 | 9.8325 | 14.09 | -0.081935 |
| elastic | 260 | 12 | 0.70497 | 0.098044 | 0.044835 | -0.013956 | 9.9126 | 13.756 | -0.031213 |
| lightgbm_season | 260 | 12 | 0.57611 | 0.074395 | 0.04511 | -0.020176 | 9.8794 | 14.212 | -0.10072 |
| xgboost | 260 | 12 | 0.54032 | 0.056453 | 0.045211 | -0.022469 | 9.5122 | 13.807 | -0.038871 |
| elastic_isotonic | 260 | 12 | 0.64231 | 0.099085 | 0.045307 | -0.024636 | 9.9126 | 13.756 | -0.031213 |
| catboost_isotonic | 260 | 12 | 0.39365 | 0.039108 | 0.045735 | -0.03431 | 9.3972 | 13.469 | 0.011389 |
| linear | 260 | 12 | 0.68918 | 0.094527 | 0.046149 | -0.043667 | 9.9185 | 13.825 | -0.041565 |
| trailing_mean | 260 | 12 | 0.5 | 0.046154 | 0.046154 | -0.043784 | 9.8762 | 14.015 | -0.070432 |
| lightgbm_without_weather | 260 | 12 | 0.59644 | 0.081694 | 0.04619 | -0.044606 | 9.5061 | 13.548 | -0.00025191 |
| climatology | 260 | 12 | 0.58905 | 0.1028 | 0.046255 | -0.04608 | 10.139 | 14.293 | -0.11333 |
| persistence | 260 | 12 | 0.52151 | 0.049883 | 0.080769 | -0.82662 | 11.75 | 17.128 | -0.5988 |
| lightgbm_label10 | 260 | 24 | 0.51342 | 0.12198 | 0.087989 | -0.047615 | 10.051 | 14.269 | -0.10961 |
| quantile_CQR | 0 | 0 | — | — | — | — | — | — | — |

## Feature coverage

| group | joint_coverage | eligible | selected_features |
| --- | --- | --- | --- |
| weather | 0.75294 | True | diurnal_range, dry_spell, extreme_days, gdd10, heavy_days, hot35, hot38, rain_total, rain_z, spi1, spi3, spi6 |
| soil | 0 | False | none |
| vegetation | 0 | False | none |
| climate | 1 | True | dmi_lag, oni_lag |
| cyclone | 1 | True | cyclone_150km, cyclone_days |
| market | 0 | False | none |
| water | 0 | False | none |
| vulnerability | 0 | False | none |
| employment | 0 | False | none |
| memory_spatial | 0.90769 | True | area_change, yield_trend, previous_residual |

## Source attempt outcomes

| status | attempts |
| --- | --- |
| BLOCKED | 3 |
| FAILED | 38 |
| FETCHED | 31 |
| PORTAL_ONLY | 5 |
| REUSED_SNAPSHOT | 2 |
| SKIPPED | 1 |

Full URLs, checksums, licences and exact errors: `source_attempts.csv` / `source_manifest.json`.

## Release checks

| check | passed |
| --- | --- |
| positive_brier_skill | True |
| auc_lower_bound_above_055 | False |
| beats_base_rate | True |
| beats_persistence | True |
| at_least_25_heldout_positives | False |
| interval_coverage_within_5pp_of_80 | True |
| at_least_four_test_years | True |
| data_evidence_verified | False |

See `../MODEL_CARD.md` for protocol and limitations.
