# West Bengal preharvest rice shortfall model

## Status: WITHHELD

**Public checkout:** the code and aggregate results are published here. Datasets, fitted weights,
and row-level outputs referenced below are local-only under the repository's redistribution
rules. See [README.md](README.md#public-checkout-and-local-inputs) for setup requirements.

This is a reproducible **retrospective research hindcast**, not a released prospective warning service.
The machine-readable decision is `reports/model_release_report.json`. Inference returns the withheld
status; `--require-released` fails closed. No label threshold was loosened to obtain more events.

## Task and population

- Eighteen Census-2011 West Bengal district units, Kolkata excluded. Split districts are aggregated
  by area and production, then yield recomputed. Missing split components are not assigned zero.
- Rice seasons: Autumn/aus, Winter/aman, Summer/boro. Cutoffs: 30 June, 31 July, 15 March.
- Assumed crop-year convention: APY YYYY–YYYY+1; boro cutoff occurs in the ending year.
  **Source-specific verification is outstanding**, so these are conditional hindcasts.
- Primary label: observed yield **strictly below 85%** of the previous five consecutive years' mean.
  A missing prior year means a missing label, never an imputed baseline.
- Auxiliary targets: anomalies in t/ha and percent against both trailing-five mean and an earlier-years
  district-season linear trend. Separate real-data 10% and 20% shortfall sensitivity fits are reported.

## Actual dataset

Processed panel: 1387 district-season-years; labeled rows: 1105;
observed 15% shortfalls: 63. Labeled crop-years: 2002–2022.
The APY snapshot ends at agricultural year 2022–2023; no 2023-start APY records were obtained.
`reports/apy_drop_audit.csv` lists every excluded Rice source row and reason.
`data/processed/panel.csv` SHA-256: `7e32215202ba76acbd3bdb15351a810381af79918219e852eef2660489c73151`.

There is no generated or imputed training data. Aggregations, fitted indices and derived labels use
observed inputs. Incomplete daily windows stay missing; no temporal interpolation, forward fill,
median fill, SMOTE, class balancing, or artificial adverse labels is performed.
Boosted trees use native missing-value handling; linear/mixed models exclude incomplete cases.
Numerical scaling and one-hot district/season encoding are transformations, not missing-value filling.

### Source and feature limitations

- APY and archive best-match weather were imported from existing checksum-verified raw snapshots.
  This verifies local consistency, not source authenticity, boundary history, or redistribution rights.
- Newly downloaded explicit ERA5 has partial district coverage; NASA POWER provides real daily
  temperatures where explicit ERA5 is absent. Sources are not spliced to fill individual missing days.
  POWER's local-solar-day and ERA5's Asia/Kolkata civil-day aggregation are not subdaily aligned.
- Point weather at recorded centroids is not a district-area-weighted average. Original centroids'
  geometry provenance has not been independently verified. ERA5-Land requests were rate-limited.
- NOAA ONI/DMI and IBTrACS were downloaded. Final reanalysis/index/track revisions can differ from
  what was available in real time. Assumed lags: weather seven days; ONI/DMI 45 days; APY 12 months
  after assumed harvest. No historical release-vintage archive was established.
- Census-2011 features are only eligible from a conservative 2014 availability date; never backfilled.
  Their temporal coverage fails the threshold. Markets, groundwater, NDVI/EVI, irrigation and MGNREGA
  lack verified district-period exports at sufficient coverage. Catalogue/portal pages are not datasets.
- Official boundary download failed TLS verification; spatial-neighbour lag remains missing.
  Split-district source naming before actual reorganisations requires independent historical checking.
- CHIRPS cross-check is limited to one centroid and month: {"district": "South 24 Parganas", "month": "2020-06", "chirps_mm": 374.5353088378906, "archive_snapshot_mm": 301.49999999999994, "days": 30, "method": "One centroid, one month; not bias correction or statewide validation."}.
  It does not validate statewide rainfall or provide a bias correction.
- Licences are recorded verbatim/provisionally in the manifest. Unknown redistribution terms remain
  unresolved; no blanket claim is made that all downloaded snapshots are freely redistributable.

Full-panel descriptive coverage (model selection recomputes this using **training folds only**):

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


Columns are added in decreasing observed coverage while preserving at least 60% joint group coverage.
This can retain only part of a group: e.g. SPI is not evidence that low-coverage SPEI/soil were used.
Parsed source counts, date ranges and units are in `data_inventory.json/csv`; per-district observed
daily counts are in `weather_coverage_by_district.csv`. HTTP success alone is not coverage evidence.

## Evaluation protocol

- Outer expanding annual origins; training labels must be released before 30 June of that crop-year,
  the earliest issue date. Summer predictions conservatively use the same frozen crop-year model.
- Development selection: 2012–2015. Locked untouched family evaluation: 2018–2022. Auxiliary
  2009-onward out-of-time predictions support calibration and stacking. No shuffled split.
- Inner tuning: outer-year minus four and minus three, only their then-released training labels.
  Two small fixed settings per family; risk Brier objective. Regression shares risk-selected settings
  within each family; an independently regression-tuned hyperparameter search was **not** performed.
- Families: logistic/ridge, elastic-net logistic/regression, LightGBM, XGBoost, CatBoost,
  Bayesian logistic and linear district-random-intercept mixed effects, per-season LightGBM.
- Baselines: released-history base rate, last available district-season outcome persistence,
  district-season climatology, and zero anomaly / zero shortfall under trailing-mean yield.
  Exact previous-year persistence is unavailable under the conservative publication lag.
- Linear/elastic development coverage is reduced by complete-case exclusion. Family selection
  requires at least 95% development risk coverage; such candidates cannot win on easier subsets.
  Every comparison records its evaluated row count; paired baseline skill uses the same rows.
- Stacking: logistic risk/ridge anomalies from strictly earlier released OOF base predictions.
  Isotonic fits use strictly earlier released OOF probabilities. Insufficient calibration history
  produces a logged identity transform, not a fitted calibration claim.
- Quantiles 10/50/90: separate LightGBM models frozen before calibration crop-year outer-minus-two.
  Sorted quantiles remove crossing; nonnegative CQR score and finite-sample order statistic widen
  the interval. Calibration labels are never refitted into that interval predictor.
  Distribution-free exchangeability is not assumed to hold for a changing climate/time series.
- Confidence intervals: 500 district–crop-year block bootstrap resamples, retaining seasons within
  each block. These may understate uncertainty from common year shocks across districts.
  Metrics weight observed district-seasons equally, not by cultivated area.
- Conditional ablations remove each eligible group from LightGBM with fresh inner tuning on identical
  origin folds. Low-coverage groups are explicitly skipped, not assigned fabricated zero impact.
- Graph/LSTM are logged as not attempted; no verified adjacency and sparse annual outcomes justify
  the simpler model comparison first. Test results do not retroactively change the selected family.

## Locked selection and measured held-out results

Risk model: **mixed_isotonic**. Anomaly model: **catboost**.
Evaluated observations: 260; positive shortfalls: 12.
Positive counts by crop-year: `{"2018": 2, "2019": 3, "2020": 0, "2021": 3, "2022": 4}`.

- AUC: **0.58787**, 95% CI **[0.33073, 0.79381]**.
- Average precision: **0.19718**; Brier: **0.043656**;
  Brier skill versus released-history base rate: **0.012696**.
- Percent-anomaly MAE: **9.3972 percentage points**;
  RMSE: **13.469**; R²: **0.011389**.
- t/ha-anomaly MAE: **0.25547**; RMSE: **0.3571**.
- Nominal 80% percent-anomaly interval observed coverage: **0.80769**;
  mean width: **30.134 percentage points**.

All target units, detrended metrics and CIs are in the release report and `confidence_intervals.json`.

### Release gate

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


Outstanding evidence:
- APY crop-calendar/year convention for boro not source-verified
- Historical APY/reanalysis/index release vintages not available; assumed publication lags
- APY/Census/boundary redistribution terms not independently verified
- Raw APY historical split-district geography before 2016 not independently validated

### Full held-out comparison (not used to choose a new winner)

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


The `lightgbm_label10` and `lightgbm_label20` rows have different binary labels and are sensitivity
analyses, not directly interchangeable AP/AUC comparisons. All other risk rows use 15% shortfall.
The quantile-only row has zero **risk** observations because it does not produce probabilities;
its interval coverage/width are evaluated separately on the same held-out observations.

## Explanations and error analysis

`shap_local.csv`, `shap_top_five.csv`, `shap_global.csv` and `shap_global.png` describe the selected
calibrated probability. Permutation SHAP uses actual training-background rows and one permutation;
it is an approximation, checked for additivity, not causal attribution. No explanation perturbation
is saved as training data. PDP uses observed training quantiles and can break weather correlations.
`explanation_status.json` records any failures. `partial_dependence.csv/png` retain per-fold curves.
`district_year_season_diagnostics.csv`, `worst_cases.csv`, and `stress_years.json` expose failures,
including empty/zero-positive stress subsets; no metric is invented when a subset is undefined.

Highest district percent-anomaly MAEs (descriptive small subsets, not district release approvals):

| value | rows | positives | brier | anomaly_pct_mae | anomaly_pct_rmse | anomaly_pct_coverage |
| --- | --- | --- | --- | --- | --- | --- |
| Purba Medinipur | 15 | 4 | 0.218 | 18.304 | 24.384 | 0.6 |
| Howrah | 15 | 1 | 0.062709 | 16.351 | 19.341 | 0.73333 |
| Bankura | 15 | 1 | 0.065761 | 12.013 | 12.972 | 0.6 |
| Bardhaman | 15 | 1 | 0.065989 | 11.375 | 19.792 | 0.73333 |
| Malda | 15 | 2 | 0.1247 | 10.994 | 15.007 | 0.73333 |


Held-out crop-year diagnostics:

| value | rows | positives | brier | anomaly_pct_mae | anomaly_pct_rmse | anomaly_pct_coverage |
| --- | --- | --- | --- | --- | --- | --- |
| 2018 | 52 | 2 | 0.037108 | 9.74 | 13.078 | 0.80769 |
| 2019 | 52 | 3 | 0.055147 | 10.297 | 14.634 | 0.73077 |
| 2020 | 52 | 0 | 0.0035363 | 7.7004 | 9.2311 | 0.88462 |
| 2021 | 52 | 3 | 0.048167 | 9.8632 | 15.739 | 0.84615 |
| 2022 | 52 | 4 | 0.074323 | 9.3852 | 13.746 | 0.76923 |


Stress subsets (pre-cutoff exposure only; a named cyclone calendar-year is not causal attribution):

| subset | rows | positives | auc | brier | anomaly_pct_mae | anomaly_pct_coverage |
| --- | --- | --- | --- | --- | --- | --- |
| observed_pre_cutoff_cyclone | 43 | 3 | 0.425 | 0.066358 | 11.808 | 0.81395 |
| pre_cutoff_spi3_below_minus1 | 44 | 0 | — | 0.0034506 | 7.3963 | 0.88636 |
| Aila_calendar_year_2009 | 0 | 0 | — | — | — | — |
| Amphan_calendar_year_2020 | 52 | 0 | — | 0.0035363 | 7.7004 | 0.88462 |
| Yaas_calendar_year_2021 | 52 | 3 | 0.96939 | 0.048167 | 9.8632 | 0.84615 |


## Intended use and limits

Use for retrospective evaluation and collecting the missing evidence. Do not treat these scores as
released operational warnings, district crop-loss measurements, or causal climate-impact estimates.
API supports audited out-of-time **2018–2022 crop-year replays** only; it rejects unsupported dates,
missing district components and checksum mismatches. Live future-year inference is not enabled
without a newly audited feature panel and prospective evidence.

See `README.md` for execution commands and `reports/results.csv` for every tuning, calibration,
ablation, sensitivity, evaluation and skipped optional experiment. Fit failures/convergence warnings
are preserved in diagnostics; extracted failures are in `failed_fits.csv`. Archived interrupted runs
are retained as `results_previous_*.csv` and are not mixed into the final comparison.
