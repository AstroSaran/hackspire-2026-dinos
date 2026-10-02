# DINOS deck delivery tracker

This tracker checks the DINOS deck's promises against the running Kavach beta.
It reports partial work plainly; missing real outcomes are not filled with
synthetic data.

## Current position

The app now supports selecting any district in the 22-district West Bengal
horticulture data vintage, displaying live weather near a geocoded district
headquarters, and inspecting official annual mango history. An experimental
annual yield model was trained and evaluated. It underperforms the persistence
baseline on MAE and is withheld. The short-horizon livelihood-risk goal remains
unfulfilled.

The backend requests configured data.gov.in feeds server-side. In this run,
`api.data.gov.in` refused connections from the Kavach environment, and the
historical MGNREGA resource is configured for the 1 April–31 August 2023
snapshot. It is not a current feed. Historical mango source records were
collected from published West Bengal Directorate of Horticulture estimates;
they are not live measurements.

The WUA crop-survey layer currently has 19 point records but only one
crop-health label and one soil-moisture value, so it cannot train the promised
crop-stress model. The official MGNREGA MPR page loaded during the latest
check, but its geography selector was disabled and no report could be
exported. Source checks are logged in
`backend/data/metadata/source-access-2026-10-03.json`.

## Promise-by-promise status

| Deck promise | Status | Remaining work |
|---|---|---|
| Climate, crop, mandi, employment signals combined | Partial | District-selectable weather and historical horticulture are available. Live OGD mandi/crop feeds require working server egress and active resource configuration; MGNREGA has only a 2023 archive configured, not a current series. |
| Village/block warnings 2–8 weeks before distress | Not delivered | Define outcome and horizon; collect dated location-matched outcomes; train separately, validate prospectively and abstain when evidence is missing. The app's seven-day weather screen is not a distress model. |
| Causal explanations and quantitative drivers | Not delivered | Define a causal question and measure interventions/confounders with suitable data. Current readings are not causal effects. |
| Best government support by urgency, cost and impact | Partial, general links only | Scheme eligibility, cost/impact ranking, program data and human review remain unimplemented. |
| Meghdoot/IMD, e-NAM/AGMARKNET and MGNREGA integrations | Partial | Open-Meteo powers weather, not IMD/Meghdoot. AGMARKNET and MGNREGA depend on configured real server feeds; MGNREGA resource setup is incomplete. |
| District/geospatial command center and agro-climatic zones | Partial | District selector and point weather display exist. Verified boundaries, agro-climatic zones and district-wide spatial surfaces are not implemented. |
| Household or vulnerable-cluster identification | Not delivered | Requires authorized, privacy-reviewed, location-matched outcome data. Public district aggregates cannot identify households. |
| Human-in-the-loop policy feedback | Partial | The app labels evidence limits and offers general official links; case review, intervention logs and governed follow-up remain to be built. |
| Predictive M&E of support outcomes | Not delivered | Needs authorized intervention records, dated outcomes and a valid impact-evaluation design. |
| Synthetic augmentation for reporting delays | Excluded by requirement | Keep missingness and latency visible; never use synthetic data as observed outcomes. |
| Production architecture in the deck | Not delivered | Current beta uses FastAPI and a static HTML dashboard. TimescaleDB/PostGIS/Kafka/PyTorch/CausalML/XGBoost/GEE are not implemented. |

## Completed model experiment

The annual mango experiment uses 88 official rows (22 districts × four crop
years, 2021-22 through 2024-25). Its single forward test transition is
2023-24 → 2024-25. Model MAE is 0.8636 t/ha; prior-year persistence MAE is
0.5865 t/ha. The artifact remains local and is excluded from GitHub while
source reuse terms are checked. It emits no production forecast and cannot
serve as a crop-stress or livelihood-distress model.

## Remaining release gates

1. Restore and verify backend HTTPS access to `api.data.gov.in`; use active
   resource IDs and page through every West Bengal response.
2. Confirm a current MGNREGA resource UUID, schema, geography and update cadence; retain the 2023 archive as historical context only.
3. Store source rows with resource ID, request time, pagination, field
   definitions, publication time and revision history.
4. Define real labels for crop stress, employment shortfall and livelihood
   disruption. Annual crop production supports only a separate annual-output
   study.
5. Train each supported target separately with later-time and held-out-district
   validation, compare against baselines, quantify uncertainty, and abstain
   outside evidence coverage.
6. Keep scheme suggestions source-linked and for human review; do not prescribe
   crop changes or infer eligibility from statewide averages.
