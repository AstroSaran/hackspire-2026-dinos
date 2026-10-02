# Kavach dataset inventory and readiness

Last checked: 2026-10-03. This inventory separates predictor feeds from target
labels. A large predictor table does not make a supervised livelihood model
trainable without matched, dated outcomes.

The latest source checks, including failed connections, are recorded without
credentials or downloaded person-level records in
`backend/data/metadata/source-access-2026-10-03.json`.

## Real records in the local development workspace

Only the weather snapshot and its provenance files are included in the public
GitHub repository. The mango snapshot below remains local while redistribution
terms are checked; its source CSV and model artifact are ignored by Git.

| Dataset | Records and coverage | Intended role | Provenance and use status |
|---|---:|---|---|
| `backend/data/wb_mango_district_annual.csv` (local-only) | 88 rows; 22 districts; final mango area/production for 2021-22 through 2024-25 | Actual annual mango-yield target, calculated as production ÷ area; only for a separate experimental annual-yield study | Source URLs are recorded per row. Reuse terms are not confirmed, so the CSV, manifest and model artifact are excluded from GitHub. The experiment loses to persistence on holdout MAE and is not released for forecasts. |
| `backend/data/processed/era5-west-bengal-2018-01-01-to-2025-12-31-d3d80529c0c1df4e.csv` | 64,284 rows; daily, 22 district-headquarters search points; 2018-01-01 to 2025-12-31 | Environmental predictor features: temperature, precipitation, wind, and reference evapotranspiration | Real ERA5 reanalysis through Open-Meteo; raw response and content hashes are under `backend/data/raw/` and `backend/data/metadata/`. CC BY 4.0 attribution is recorded. Open-Meteo's free API is for non-commercial use. Values are model estimates at selected points, not station observations or district means. No outcome labels are included. |
| `backend/data/metadata/wb_district_geocoding_fallbacks.json` | Three cached search points for Alipurduar, Murshidabad and Hooghly | Point resolution only | One-time OpenStreetMap Nominatim fallback, queried 2026-10-02 UTC and cached to avoid repeat requests. ODbL attribution is `© OpenStreetMap contributors`. These are headquarters search points, not administrative boundary geometry. |

The ERA5 dataset is deliberately not joined to the mango table: matching an
annual weather aggregate to an annual yield value is not sufficient evidence
for field-level crop stress, and it cannot create MGNREGA or household
livelihood labels.

## Official sources not collected in this run

| Source | What it can provide | Current status and model limitation |
|---|---|---|
| OGD district-wise, season-wise crop-production statistics | Annual district/crop/season area and production records from 1997 onward | OGD lists the resource as annual and under National Data Sharing and Accessibility Policy; its resource page states Government Open Data License–India. Kavach's configured backend connector returned `UNAVAILABLE` because it could not connect to `api.data.gov.in:443`; no API response was stored. These records can extend historical yield targets, but are not field stress or household distress labels. |
| MGNREGA District-wise Data at a Glance / official Public Data Portal | Dated demand, work allocation, employment and person-day indicators by administrative level and year/period, depending on the selected report | The OGD connector returned `UNAVAILABLE` for backend HTTPS failures on 2026-10-03. The official MPR page loads and describes monthly households/persons demanding work and households working, but its geography selector was disabled and visible year options stopped at 2010-11; no report was exported. The configured OGD resource is a 2023 archive, not a current time series. District aggregates cannot label household access or eligibility. |
| AGMARKNET daily mandi prices through OGD | Commodity/market/date wholesale prices | Connector returned `UNAVAILABLE` because of the same egress block. Price observations are predictors/context; they do not label farm-gate income or distress. |
| West Bengal WUA crop-survey GIS layer | 19 point records; 1 crop-health label and 1 soil-moisture reading; sowing dates span 2018–2026 and harvest dates 2025–2027 | Coverage was reachable on 2026-10-03. The source has no district field and is far too sparse for training. The app fetches only agronomic fields for a coverage summary; it omits coordinates, remarks, global IDs and editor metadata. No clear reuse license is recorded, so point rows are not archived or used for training. Retrieval time is not observation time. |
| IMD historical station/district observations | Official weather observations, depending on access and requested product | IMD's public page displays recent rainfall products and routes historical data queries through its Data Service Portal/contact. No bulk historical IMD dataset or API authorization is configured in Kavach. ERA5 remains separately labeled as reanalysis. |
| West Bengal WUA point crop survey (model-label candidate) | Published schema includes crop, season, sowing/harvest dates, crop-health status and a soil-moisture reading | A count-only request returned 19 records. The app's privacy-limited summary found one non-empty crop-health label and one soil-moisture value. The layer schema also exposes precise coordinates, global IDs and editor metadata; point rows were not downloaded to disk. No reuse terms are recorded. Do not treat this sparse point layer as a statewide label source. |
| MGNREGA Public Data Portal MPR page | Monthly aggregate indicators and selectors for indicator, geography and financial year | The public page returned successfully, but no West Bengal district report was retrievable in the current session: its geography selector was disabled and the rendered year list ended at 2010-11. No report data are included in the training snapshots. |
| Directorate of Economics and Statistics (DES) APY query report | State/district/crop/season/year area, production and yield report | The official query page was identified, but HTTPS timed out from this environment on 2026-10-03. No new records were downloaded. |

OGD source pages: [crop-production catalog](https://www.data.gov.in/catalog/district-wise-season-wise-crop-production-statistics-0), [crop-production resource and license notice](https://data.gov.in/resource/district-wise-season-wise-crop-production-statistics-1997), and [MGNREGA resource](https://www.data.gov.in/resource/district-wise-mgnrega-data-glance). The official MIS [Public Data Portal](https://mnregaweb4.nic.in/netnrega/dynamic2/dynamicreport_new4.aspx) provides report selectors for job cards, work demand, allocation, employment and month-wise indicators. IMD identifies its current rainfall products and historical-data query route on its [Rainfall Information page](https://mausam.imd.gov.in/responsive/rainfallinformation_state.php).

## Labels required before the promised risk models can be trained

1. **Crop/weather stress:** dated, district/block or field-matched observed crop damage/stress or yield-loss outcomes, crop and season, plus verified spatial/time joins to predictors. Annual production is a separate outcome; it is not an individual field-stress label. The WUA layer has only one non-empty crop-health label, so it fails the minimum dataset-coverage gate.
2. **MGNREGA shortfall:** a preregistered target such as period-specific households demanding work versus households receiving work, with stable geography, dates, revisions and definitions. Household-level prediction needs authorized privacy-safe household outcomes; state/district aggregates cannot stand in for them.
3. **Broader livelihood disruption:** a defined outcome and warning horizon with representative, authorized, privacy-safe dated outcome data. No such dataset is currently present.

Until these outcome data are sourced and independently validated, the three
livelihood risk tracks remain withheld. The annual mango experiment is
reproducible but experimental and underperforms persistence on holdout MAE.

## Access actions needed for the uncollected official feeds

- Restore outbound HTTPS from the FastAPI server to `api.data.gov.in:443` and verify DNS, TLS trust, proxy and firewall rules. Keep API keys in `backend/.env`; never paste them into a browser URL or commit them.
- Confirm the active OGD resource UUIDs and field schema for crop production, AGMARKNET and a current MGNREGA resource. Page through all results, preserve the exact raw response, request time, offset, source total, resource UUID and license notice; stop on any page error rather than calling partial data complete.
- For MGNREGA, export a dated state/district/block-level report from the official MIS portal only after recording each selected indicator, administrative level, year and period. Do not collect worker names, job-card numbers, bank details or other person-level identifiers for this project.
- Confirm permitted reuse for the West Bengal horticulture source PDFs before redistribution. For Open-Meteo, retain the attribution in its manifest and use a commercial API plan if the product is operated commercially.
- Obtain written reuse/privacy terms for the WUA survey layer before any point-row collection; do not persist exact coordinates, global IDs, remarks or editor metadata for model training.
