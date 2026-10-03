# Kavach model card and release policy

## Current release

Kavach has an **Environmental Watch** fixed-rule forecast screener and three registered livelihood prediction tracks. Environmental Watch is not a trained model. The three livelihood tracks are **not trained and not released**; they return readiness gates only. The public-data scope is all West Bengal districts returned by each configured source. The current weather card remains a single Sonarpur forecast grid and must not be read as statewide weather.

## Environmental Watch 1.1.0

- **Purpose:** surface dates when a live seven-day weather forecast crosses configured weather thresholds.
- **Inputs:** Open-Meteo provider forecast values. ERA5 monthly rainfall comparisons and provider-grid soil moisture are displayed as context only; they do not drive household or crop risk estimates.
- **Rules:** daily precipitation at least 50 mm; rain probability at least 70% with at least 20 mm forecast; max wind at least 50 km/h; or max temperature at least 40 °C.
- **Interpretation:** these are Kavach screening thresholds, not locally validated impact thresholds, official IMD warnings, or an all-clear. A triggered result asks the viewer to check official alerts and local conditions.
- **Input controls:** dates and values are checked for validity and plausible ranges. A no-trigger result requires a live, dated, complete seven-day input. Stale, missing, invalid, or partial inputs abstain from that result. The API returns field coverage, rule/config digest, source and freshness state.
- **Known gap:** threshold performance against local observed impacts has not been evaluated. Do not use this component to automate evacuation, benefit eligibility, allocation, or household classification.

## Livelihood prediction tracks 0.1.0-readiness

There are no trained livelihood predictors. All three tracks report `WITHHELD` and do not emit prediction values, bands, or probabilities:

1. **Crop and weather stress:** proposed 7-day horizon. Requires district/season crop and field observations plus dated, location-matched stress outcomes. Annual production totals are not stress labels.
2. **MGNREGA work-provision shortfall:** proposed 30-day horizon. Requires dated demand and work provided for the same district/reporting period, historical outcomes, and confirmed source definitions. District data cannot predict a household's access.
3. **Broader livelihood disruption:** horizon and measurable outcome still need to be agreed with intended users. Requires privacy-safe district-level outcomes and matched impact evidence across livelihood groups.

The AGMARKNET, crop-production and MGNREGA connectors request West Bengal records across districts. During the 2026-10-02 run, `api.data.gov.in` refused connections from both the Kavach backend and the in-app browser, so no fresh source records were collected and no model was trained. The MGNREGA resource UUID is also not configured; the previously inspected portal-linked UUID covers only April–August 2023 and is not treated as current data. These tracks are registered plans, not active predictions.

The retired DINOS prototype now includes a reproducible Kaggle ingestion path
for Indian rainfall, crop-production, mandi-price, MGNREGA, and census snapshots.
It retains the original six inputs and target contract. The feature panel can
be built from compatible observed fields, but several signals remain explicitly
unavailable and the source set has no validated `distress_cascade_label`.
Accordingly the training entry point refuses to fit until complete real inputs
and a genuine matched binary outcome are supplied. Yield changes, MGNREGA
person-days, synthetic risk categories, and rainfall proxies are never used as
distress labels. That prototype and its ingestion notes are local-only and
excluded from the public repository. The separately published rice experiment
is documented in [kavach_model/MODEL_CARD.md](kavach_model/MODEL_CARD.md).

## Advisory behavior

The dashboard offers general prevention and government-program links, not an AI-generated crop switch. Crop choice must be checked against the farmer's district, season, soil test, water access, sowing stage and current West Bengal agriculture advice. Check [Matir Katha](https://matirkatha.wb.gov.in/) for area/season/crop information and the [Soil Health Card](https://soilhealth.dac.gov.in/) for field-specific soil recommendations. Verify current enrollment windows and notified crops for [Bangla Shasya Bima](https://matirkatha.wb.gov.in/) or [PMFBY](https://pmfby.gov.in/farmerApplicationForm); PMFBY lists helpline 14447 for eligible crop-loss reporting. Confirm MGNREGA information at the relevant local office/Gram Panchayat; district aggregates do not establish individual eligibility or work demand.

## Required evidence before training

Training data must consist of real observations with documented collection method, source, date, geography, rights/consent, target definition, missingness and revision history. Generated, representative, synthetic, or unverifiable rows are prohibited. Feature values must be available at the proposed prediction time to prevent leakage. Household-level data need a privacy review and minimization plan before ingestion.

## Required release gates

1. Pre-register a measurable outcome, prediction horizon, intended users and supported geography.
2. Confirm administrative coverage and legally authorized source access.
3. Establish sufficient, representative real outcomes; determine sample needs from the target and evaluation design rather than an arbitrary row count.
4. Freeze a leakage-safe validation design that holds out later periods and whole locations.
5. Compare with simple non-model baselines; report calibration, precision/recall, false-negative behavior, uncertainty and confidence intervals.
6. Review missingness and errors across locations and relevant livelihood groups; document limitations and human review.
7. Add monitored abstention for out-of-domain/stale inputs, drift alerts, rollback, versioned artifacts, audit logs and a response owner.
8. Complete independent field validation before any real-world decision use.

Until these gates are satisfied, the production behavior is to withhold livelihood predictions.


## West Bengal Mango Yield Baseline 0.2.0-experimental

- **Why v0.1 was replaced:** its pooled one-lag regression was worse than "same as last year" (MAE 0.95 vs 0.57 t/ha; R² 0.64 vs 0.67).
- **Method now:** five candidates are scored by rolling-origin backtest (each year forecast only from earlier years). The winner is `robust_persistence`: carry last year's yield forward, unless it is a >30% outlier against the district's own history (applied only with 3+ prior years; with two, a median cannot tell an outlier from a real level shift).
- **Pooled out-of-sample results (44 district-year forecasts, 2023-24 and 2024-25):**

| Metric | v0.1 regression | Persistence | v0.2 selected |
|---|---|---|---|
| MAE (t/ha) | 0.948 | 0.574 | **0.439** |
| R² | 0.635 | 0.671 | **0.791** |
| Within 10% of actual | 50% | 80% | **82%** |
| Within 20% of actual | 80% | 89% | **91%** |
| Area-weighted error | 20.8% | 17.5% | **10.7%** |

- **Clean-target view (reported beside the raw numbers, never instead):** excluding 4 target records the data-quality checks flag as likely source artefacts, pooled R² is 0.898 and area-weighted error 4.9%.
- **Honest limits:** raw pooled R² is 0.79, just under 0.80. The 2023-24 fold is dominated by a statewide dip (Murshidabad, Nadia) that no history-only model can foresee. With only two forecast origins the gain over persistence is **not statistically established**. The 2023-24 fold is plain persistence by construction.
- **Uncertainty:** every forecast carries an 80% band from out-of-sample relative errors.
- **API:** `GET /models/mango-yield[?district=Malda]` serves forecasts, backtest, flags and limitations. It never returns a risk score.
- **Do not use** for production, insurance, benefit or allocation decisions.
- **Next steps:** earlier years of district yields; rainfall/temperature features once an approved weather archive is reachable from training.

### Dashboard (frontend) changes in this release
- New "Mango yield baseline" panel: backtest R², average error, hit-rates, a sortable-by-size district table with 80% ranges, and source-data warnings.
- Accessibility: skip-to-content link, Escape closes the voice and support panels (focus returns to the launcher), keyboard-scrollable forecast and table regions, darker muted text for contrast, larger small labels.
- Layout: header, hero, cards and location banner stack on phones; floating voice/support buttons no longer cover card content; no horizontal scrolling at 390 px or 1280 px.
