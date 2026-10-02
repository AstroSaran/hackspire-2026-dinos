# Kavach model card and release policy

## Current release

Kavach is a West Bengal district data workspace. The weather display and its
transparent seven-day threshold screen are not trained livelihood models. The
app has one annual mango-yield experiment trained from official historical
district estimates; it is explicitly withheld from forecasts and decisions.
The project now has a separately versioned, real ERA5 reanalysis feature
snapshot for all 22 West Bengal district-headquarters search points. It is
predictor data only and does not supply any livelihood outcome labels.
No crop-stress, MGNREGA shortfall, or broad livelihood-distress predictor is
trained or released.

## Weather screening

- **Input:** Open-Meteo current conditions and seven-day model forecast, fetched
  for a geocoded point near the selected district headquarters.
- **Rules:** Daily precipitation >= 50 mm; rain probability >= 70% together with
  >= 20 mm forecast; maximum wind >= 50 km/h; or maximum temperature >= 40 °C.
- **Interpretation:** These are Kavach screening thresholds, not locally
  validated impact thresholds, official IMD warnings, or an all-clear.
- **Context:** The dashboard may compare a completed month against ERA5
  1991–2020 reanalysis normals and show Open-Meteo modelled topsoil moisture.
  Neither is a field reading or a livelihood-risk label.
- **Limits:** A headquarters grid cannot represent every block, farm, or
  household. Check official IMD alerts and local conditions before acting.

## Annual mango-yield experiment 0.1.0-experimental

- **Purpose:** explore a one-year-ahead district mango-yield baseline from
  historical annual area and production estimates.
- **Source:** West Bengal Directorate of Horticulture final annual estimates;
  the checked records cover 22 districts and fiscal crop years 2021-22 through
  2024-25. The dashboard's source file is
  `backend/data/wb_mango_district_annual.csv`.
- **Dataset tracking:** exact CSV SHA-256, source links, schema, quality checks
  and deterministic forward split are recorded in the content-addressed
  local manifest under `backend/data/metadata/`. Collection date and source
  reuse terms were not present in the original snapshot. The CSV, manifest and
  trained artifact are excluded from public GitHub until reuse terms are
  confirmed; unit tests use synthetic test-only fixtures.
- **Target:** production divided by area, in tonnes per hectare. This derived
  annual target is not crop stress, yield loss causality, household income,
  employment, or livelihood distress.
- **Input and method:** previous-year yield only; pooled ordinary least-squares
  regression with one lag feature.
- **Validation:** train on 44 district transitions ending by 2022-23; test on
  22 districts for the single 2023-24 to 2024-25 transition.
- **Forward-test result:** model MAE 0.8636 t/ha, RMSE 1.4325 t/ha, R² 0.7124.
  Prior-year persistence baseline MAE 0.5865 t/ha, RMSE 1.4668 t/ha,
  R² 0.6985. The model loses to the baseline on MAE.
- **Release:** local experimental artifact only and not included in public GitHub. District forecasts are withheld;
  there is only one independent test year, no field validation, and the latest
  ingested annual report year is 2024-25. No 2025-26 prediction is emitted.

## Historical environment predictor dataset

- **Snapshot:** 64,284 daily rows across 22 district-headquarters search points,
  2018-01-01 through 2025-12-31.
- **Variables:** ERA5 mean/minimum/maximum temperature, precipitation,
  maximum wind speed and reference evapotranspiration.
- **Source:** Open-Meteo Historical Weather API, ERA5 reanalysis, informed by
  observation systems but still a model estimate. Three point searches use
  cached OpenStreetMap Nominatim results where the primary geocoder returned
  no district match; the manifest records per-point source and attribution.
- **Files:** raw JSON under `backend/data/raw/`, normalized CSV under
  `backend/data/processed/`, and version/provenance/quality manifest under
  `backend/data/metadata/`.
- **License/use:** the manifest records CC BY 4.0 attribution for the weather
  data and that Open-Meteo's free API is restricted to non-commercial use.
  Commercial deployment needs a suitable API plan and a fresh terms review.
- **Role:** covariates only. These point estimates are not official station
  observations, district means, field crop-loss labels, MGNREGA targets, or
  household livelihood outcomes. They are not currently used to train a
  livelihood-risk model.

## Livelihood prediction tracks

All three are `WITHHELD` and emit no score, band, or probability:

1. **Crop and weather stress:** needs date- and location-matched field stress
   labels. Annual output totals are not those labels. The alternative West
   Bengal WUA crop-survey GIS layer is connected for coverage assessment, but
   its point records have no district field and the current fetch contains only
   one crop-health label and one soil-moisture reading; it is not training or
   validation data for a statewide model.
2. **MGNREGA work-provision shortfall:** needs a verified, current resource,
   historical district-by-period demand and provision targets, and confirmed
   source definitions. District aggregates cannot predict household access.
3. **Broader livelihood disruption:** needs an agreed outcome and horizon plus
   privacy-safe, representative district-level outcome and impact evidence.

The OGD mandi, crop, and employment connectors retain server-side credentials
and return explicit configuration or provider errors. The local model experiment
does not depend on those connectors, but cannot substitute for their missing
features or outcome labels.

## Advisory and public support

The dashboard offers general source-linked support routes, not personalized
crop-switch instructions, causal effects, eligibility decisions, or automated
benefit routing. Farmers should confirm district, season, soil test, water
access, sowing stage, and current local extension guidance before changing
crops. Public district averages are not field recommendations.

## Release gates

1. Pre-register target, horizon, users and supported geography.
2. Confirm source authority, field definitions, dates, geography and update
   cadence; preserve revisions and provenance.
3. Collect adequate real, representative outcomes; do not synthesize labels.
4. Use leakage-safe forward and geographic holdouts, compare with simple
   baselines, and report calibration, uncertainty and error by group.
5. Add monitored abstention for stale and out-of-domain evidence, versioned
   artifacts, drift checks, rollback and accountable human review.
6. Complete independent field validation before decision use.

Until the livelihood release gates pass, the product withholds livelihood
predictions.
