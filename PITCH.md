# Kavach — West Bengal district resilience workspace

## 10-second pitch

Kavach brings live district weather, official crop history and public-program
data into one place. It shows where each reading comes from and withholds a
livelihood-risk score until real outcomes can validate one.

## 30-second pitch

Public signals arrive at different scales and on different schedules. A model
grid is not a farm observation, a district employment count is not a household
outcome, and annual crop production does not prove livelihood distress. Kavach
lets people choose a West Bengal district, inspect live weather and official
historical crop estimates, and see which government data feeds are connected.
When evidence is missing, the app says so instead of filling the gap with a
simulated risk score.

## What the beta demonstrates

- A selector for the 22 districts represented in the horticulture source
  vintage.
- Server-side district geocoding and live Open-Meteo current conditions and
  seven-day forecast, with the resolved grid point shown as a model location.
- A live environmental screen that applies transparent weather thresholds;
  it is not an official warning or a livelihood-risk model.
- A rainfall comparison for the latest complete ERA5 archive month and its
  1991–2020 monthly normal, with reanalysis provenance.
- An Open-Meteo 0–7 cm topsoil-moisture model field, identified as a grid
  estimate rather than a field reading.
- Official district mango area and production history for 2021-22 to 2024-25.
- A trained annual mango-yield experiment with a time-ordered holdout and a
  simple persistence comparison. It is withheld because its MAE is worse than
  the baseline and there is only one independent test year.
- Optional server-side AGMARKNET, OGD crop and MGNREGA connectors. Failed or
  unconfigured feeds stay explicitly unavailable.
- A livelihood model-readiness panel with release gates and source-linked
  public-support information. It emits no unvalidated risk score.
- Bengali and English support, microphone consent and reviewed speech
  transcription, plus optional private notes.

## Demo flow

1. Select Malda or another district in the source catalogue.
2. Inspect the geocoded weather grid and provider timestamps.
3. Compare the recent complete rainfall month with its 1991–2020 ERA5 normal.
4. Open the official annual mango history and the experimental model metrics.
5. Show the Data fit and connector cards, distinguishing connected feeds from
   missing credentials or provider network failures.
6. Explain why the app withholds a livelihood prediction: no real, dated
   district-matched livelihood outcome labels are available for training and
   validation.

## Product boundary

Kavach is a source-attributed evidence workspace, not a validated 2–8-week
livelihood early-warning model. Weather values are model output near the
selected district headquarters. Annual production is a historical crop-output
measure. MGNREGA district aggregates do not establish household access.
The beta makes no crop-switch, benefit-eligibility, employment, insurance or
migration decision.

## Current limitations and roadmap

The data.gov.in API host is unreachable from the current server environment.
The configured MGNREGA OGD resource is an archived 1 April–31 August 2023
snapshot; the linked state MIS remains the route to current administrative
records. The local published mango history remains usable while OGD feeds are
unavailable. Next, restore server-side OGD access, verify a current MGNREGA
resource and its schema, ingest dated records with provenance, and collect
authorized outcome labels. Only then train a separate livelihood model with
later-time and held-out-district validation, compare it with baselines, and
complete field review.
