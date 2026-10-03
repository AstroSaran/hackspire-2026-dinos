# DINOS deck delivery tracker

This file compares the six-page DINOS pitch deck with the current Kavach beta. A
pitch promise is marked delivered only when the working application and its data
support it. Missing records are never replaced with simulated values.

## Current position

The project is on the same problem and product direction, but it has not reached
the deck's predictive outcome. The current release is a source-attributed
dashboard with a seven-day weather threshold screener and model-readiness gates.
There is no trained livelihood-risk model, causal model, or personalized
government-intervention router.

The market and crop connectors now request all West Bengal districts and expose
page offsets. The backend makes data.gov.in requests server-side with keys kept
in `backend/.env`. In the current run, `api.data.gov.in` refused HTTPS
connections from the Kavach server and the browser; no statewide records were
collected. The MGNREGA resource ID is not configured. Do not set the previously
inspected April–August 2023 snapshot as a live feed.

## Promise-by-promise status

| Deck promise | Current status | Work required |
|---|---|---|
| Climate, crop, mandi, and employment signals combined | Partial | The app has weather and connectors for crop production and mandi records. The crop feed is annual, MGNREGA is not configured, and none of the OGD records could be fetched in this run. Add verified current source access and coverage metadata. |
| Village/block warnings 2–8 weeks before distress | Not delivered | Define a target and horizon by source/geography; collect dated real outcomes; train and evaluate separate models. The current seven-day weather screen is not a livelihood forecast. |
| Causal explanations and quantitative drivers | Not delivered | Establish a causal question and valid interventions/confounders; use field and administrative outcome data. Correlations or a deck example must not be rendered as measured causal effects. |
| Recommend the best government support by urgency, cost, and impact | Partial, general links only | The dashboard now links to official West Bengal crop advice, soil cards, Bangla Shasya Bima, PMFBY, and MGNREGA. Eligibility, costs, impact ranking, and automatic routing need verified rules, current program data, and human review. |
| Connect Meghdoot/IMD, e-NAM/AGMARKNET, and MGNREGA | Partial | AGMARKNET is configured; Open-Meteo is not IMD/Meghdoot. MGNREGA needs a current resource UUID. Do not describe these as completed integrations. |
| District/geospatial command center and agro-climatic zones | Not delivered | Add verified district boundaries and zone classifications with source/date, then map source coverage and model output. Current weather is one Sonarpur grid, not a West Bengal surface. |
| Household or vulnerable-cluster identification | Not delivered | Needs authorized, privacy-reviewed household/cluster outcomes. Public district aggregates cannot identify a household. |
| Human-in-the-loop policy feedback | Partial | Users can inspect source limitations; a governed administrator review, intervention log, and measured follow-up outcome loop remain to be built. |
| Predictive M&E showing whether support changed outcomes | Not delivered | Record authorized interventions and dated outcomes, define comparison design, and evaluate changes before claiming impact. |
| Synthetic augmentation to bridge reporting delays | Intentionally excluded | The project requirement is real data only. Report missingness/latency and abstain; synthetic rows cannot stand in for observed outcomes. |
| Production architecture named in the deck | Not delivered | The beta currently uses FastAPI and a static HTML dashboard. TimescaleDB/PostGIS/Kafka/PyTorch/CausalML/XGBoost/GEE are not implemented. Adopt components only when the measured workload and available data justify them. |

## Immediate release gates

1. Restore outbound HTTPS from the backend host to `api.data.gov.in`; verify the
   stored keys privately and retrieve every West Bengal page for the configured
   official resources.
2. Identify a current MGNREGA resource UUID and inspect its fields, geography,
   update cadence, and date coverage before using it.
3. Preserve raw source rows, request time, resource UUID, pagination, field
   definitions, and revisions. Do not merge district, block, and household
   records as if they were the same geography.
4. Define real outcome labels for crop stress, employment shortfall, and broad
   livelihood disruption. Crop production totals can support a separate annual
   production/yield analysis, not a short-horizon field-stress label.
5. Train each supported target separately; hold out later periods and whole
   districts, compare against simple baselines, calibrate uncertainty, and
   abstain outside validated coverage.
6. Release support suggestions as source-linked options for human review. Do
   not prescribe crop changes or determine scheme eligibility from statewide
   averages.
