# Kavach model lab

## Current reproducible baseline

`app.train_mango_yield_model` was rerun against
`wb_mango_district_annual.csv`, an official West Bengal Directorate of
Horticulture source-linked dataset.

- 88 district-year records
- 22 districts
- 2021–22 through 2024–25
- selected method: `robust_persistence`
- rolling-origin out-of-sample MAE: `0.4394 t/ha`
- production-weighted WAPE: `0.1069`
- two rolling-origin model-selection folds; no untouched test origins

The artifact is written to `mango_yield_baseline_model.json`. These results are
experimental and cannot be interpreted as household livelihood risk, crop
stress, insurance eligibility, or an operational decision signal. Four years is
too little history for strong claims; adding another official reconciled year is
the highest-value next step.

The source CSV and fitted artifact are local-only, pending confirmed source
redistribution terms. The figures above describe the earlier local v0.2 run,
not a new training run performed while publishing this code. The integrity-checked
v0.2.1 trainer must be run explicitly against an authorized local source before serving.

## Source checks

The official OGD mandi catalog was checked, but its current page reports no
resource/API available for direct retrieval. Mandi data therefore remains
`NEEDS_CONFIGURATION` until a current official resource UUID and API key are
configured. The connected crop-history route is also an annual context feed,
not a field-stress label.

The legacy replacement-source pipeline currently reports 16,073 crop rows but
zero complete rows for the six-feature distress interface and no observed
distress labels. It remains blocked by design. Crop yield, market prices,
MGNREGA participation, rainfall, or deterministic demo rows must not be
relabelled as distress outcomes.

## Safe next training gate

Before adding a new model, the source must provide:

1. a documented target definition and observation window;
2. exact West Bengal district/period keys;
3. auditable provenance for every target and feature;
4. time-ordered validation with district holdouts where appropriate; and
5. enough independent years and field review to justify the intended use.

Until those gates pass, Kavach may show source coverage, transparent weather
watches, and experimental annual crop baselines, but it withholds a
livelihood-risk score.
