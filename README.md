# Kavach — Explainable Livelihood-Risk Early-Warning & Decision Support

## One-line description
A decision-support layer that turns fragmented climate, crop, market, water
and employment signals into an auditable early-warning workflow: it
estimates risk, explains why risk is rising, explores plausible scenario
trajectories, and surfaces rule-based suggested actions for a human officer
to review — using programs (PMFBY, MGNREGA, mKisan, e-NAM) that already
exist, rather than replacing them.

## What Kavach is not
Kavach does **not** claim to predict poverty, migration, debt or livelihood
distress with a validated real-world probability. It does not auto-allocate
benefits or make eligibility decisions. Every score, driver, and trajectory
in this build is computed by a real, running pipeline over **representative
/ simulated** data — not a live government feed — and is labeled as such
throughout the API and UI. See "Data & Validation status" below before
presenting this anywhere.

## Architecture (the required pipeline)
```
DATA SIGNALS
   -> DATA QUALITY / PROVENANCE     (backend/data/generate_dataset.py: FEATURE_PROVENANCE)
   -> RISK ASSESSMENT               (backend/app/engine.py: assess_risk — RandomForest,
                                      "estimated risk score", real model-uncertainty from
                                      tree disagreement, NOT a calibrated probability)
   -> DRIVER EXPLANATION            (real SHAP TreeExplainer output, labeled
                                      "driver contribution — indicative", not causal proof)
   -> SCENARIO / TRAJECTORY ENGINE  (hand-designed transition weights, labeled
                                      "illustrative scenario trajectory", not a forecast)
   -> INTERVENTION RULE ENGINE      (deterministic, rule-based, tied to real programs;
                                      "suggested actions for officer review")
   -> HUMAN REVIEW                  (backend/app/review.py: officer decision logged)
   -> OUTCOME TRACKING              (subsequent_outcome field, intentionally null —
                                      no real pilot has observed it yet)
   -> FUTURE MODEL VALIDATION       (backend/app/main.py: GET /model/validation-status)
```

## Real weather integration (West Bengal, India)
Country: India · State: West Bengal · Timezone: Asia/Kolkata · Units: °C, mm, km/h.

**Provider priority** (`backend/app/weather/service.py`):
1. **IMD** — only attempted if `IMD_ENABLED=true` (default `false`: not yet whitelisted).
2. **Open-Meteo** — the immediate real-data source. Public, keyless, always attempted as fallback.
3. **Demo** — only if `WEATHER_DEMO_FALLBACK=true`. Always `SIMULATED_DEMO`, never `LIVE`.

**Architecture**: `WeatherProvider` abstraction (`backend/app/weather/providers.py`) with
`IMDWeatherProvider`, `OpenMeteoWeatherProvider`, `DemoWeatherProvider`; an orchestration
layer with real caching/freshness/health tracking (`backend/app/weather/service.py`); a
historical-baseline module (`backend/app/weather/historical.py`); and a normalized data
model (`backend/app/weather/models.py`) carrying full provenance (provider, source,
status, data_status, data_type, location, observed_at/issued_at/fetched_at, timezone,
freshness, cache_status) that never mixes observation and forecast fields.

**IMD** — confirmed via a live 401 test and independent third-party reports: real,
documented endpoints exist but require IP whitelisting by IMD's nodal officer. Kept in
the architecture as the future primary provider (`IMD_ENABLED=false` by default); no
bearer-token flow was invented for it since none exists publicly.

**Open-Meteo** — real, public, keyless. Two APIs used: the forecast API
(`api.open-meteo.com/v1/forecast` — current + 7-day daily, requesting only
temperature/humidity/precipitation/rain/wind speed/wind direction, per Part 4's "don't
request unnecessary variables") and the historical ERA5 archive API
(`archive-api.open-meteo.com/v1/archive`) for baseline computation. Both confirmed via
Open-Meteo's own official documentation and GitHub repo. Labeled "not IMD" everywhere it
appears (tested).

**Sandbox limitation, stated plainly:** this development container's network egress does
not reach `mausam.imd.gov.in`, `api.open-meteo.com`, or `data.gov.in` — confirmed via a
direct request that returned this container's own egress-proxy `403 host_not_allowed`,
and via `web_fetch`'s robots.txt policy on the same hosts. **Neither provider's live call
could be executed from inside this container.** Every provider is written against its
real, independently-verified API contract; deploy with normal internet egress (which
almost any real hosting environment has) to get genuinely live data immediately for
Open-Meteo — no IMD whitelisting wait required.

**Demo mode**: with `WEATHER_DEMO_FALLBACK=true`, `DemoWeatherProvider` supplies
clearly-labeled `SIMULATED_DEMO` weather (deterministic per-village values, never random)
so the dashboard's weather card is demonstrable where no live provider is reachable — the
published dashboard was exported with this flag on; its weather card says
`SIMULATED_DEMO`, not `LIVE`.

**Rainfall anomaly pipeline** (`backend/app/weather_features.py`, Part 9): OBSERVATION →
HISTORICAL BASELINE → ANOMALY → QUALITY CHECK → MODEL INPUT, every stage inspectable via
`weather.rainfall_anomaly_pipeline` in the API response. **A defensible baseline could
not be constructed in this build** — computing one honestly requires either (a) a
data.gov.in API key for India OGD's official IMD district-normal-rainfall dataset
(confirmed to exist at `www.data.gov.in/catalog/rainfall`, not obtained here), or (b) a
real multi-decade batch call to Open-Meteo's ERA5 archive (this sandbox has no network
egress to run it). So `rainfall_anomaly_pct` is honestly `UNAVAILABLE` with
`model_input_used: false` throughout this build, per Part 9's explicit instruction rather
than inventing a plausible-looking normal. See `historical.py`'s `--populate` entry point
for the real (not-yet-run) computation path, and `GET /data-health` →
`historical_baseline` for live status.

**Live weather vs. the trained model** (Part 13) — the RandomForest is trained on the
representative/synthetic dataset (`backend/data/generate_dataset.py`) and remains so:
displaying live Open-Meteo weather does **not** mean the model was retrained on it. Every
village response's `observed_signals[].model_input_used` is `true` for the six
representative features (they ARE the model's real input today) and the weather block's
`rainfall_model_input_used` is `false` (live weather is shown, not yet fed to the model)
— this distinction is asserted by a test (`test_model_input_flag_distinguishes...`).

**Weather warnings** (Part 11) — Open-Meteo has no warnings product and IMD's requires
whitelisting, so `GET /weather/{village}/warnings` returns `{"status": "UNAVAILABLE", ...}`
today. The UI renders this as **"WARNING STATUS UNAVAILABLE"**, never "no active
warning" — that phrase is reserved for when a real source was genuinely queried and
returned an empty result.

**Per-signal data coverage** (Part 14) — every response carries a `data_coverage` object:
```
weather:        LIVE | STALE | SIMULATED_DEMO | UNAVAILABLE  (see /data-health for why)
crop:           SIMULATED
market:         SIMULATED
employment:     SIMULATED
water:          SIMULATED
vulnerability:  SIMULATED
historical_outcomes: NOT_AVAILABLE
```

**West Bengal geography** (`backend/app/geography.py`): real Nadia district/block
hierarchy (Krishnanagar Sadar, Tehatta, Ranaghat, Kalyani) with block-headquarters
centroid coordinates (general public geography; resolution marked `block_centroid`, not
village-level GPS — Part 5). IMD's own numeric district ID for Nadia is not published as
an open, verifiable lookup table, so `imd_district_id` is left `None` rather than
guessed. A village with no geography record resolves to an explicit "weather location
unavailable" response, never a fabricated coordinate (tested).

## Key features

- Real trained RandomForestClassifier (scikit-learn) — kept as the risk model per design;
  an LLM is never used to compute the score, only (optionally) to narrate it downstream
- Real SHAP (TreeExplainer) driver attribution — genuine model explanation, explicitly
  labeled as indicative, not proof of real-world causation
- Genuine model uncertainty: standard deviation of per-tree probability estimates across
  the forest, surfaced as "low / moderate / high model disagreement"
- Full data-provenance metadata on every signal: source, data_status
  (`SIMULATED_REPRESENTATIVE`), geographic level, freshness, confidence, and what the
  live equivalent would be
- Scenario trajectory (not "predicted cascade"): each stage tagged `OBSERVED_SIGNAL`,
  `SCENARIO_ESTIMATE`, or `SCENARIO_INDICATOR`, with a qualitative relative-risk level
  and a confidence figure that deliberately decays down the chain
- Rule-based, deterministic intervention engine — same inputs always produce the same
  suggested actions (tested; see `backend/tests/`), each requiring officer review
- Human-in-the-loop logging: `POST /villages/{village}/review` records an officer's
  decision, with `subsequent_outcome` intentionally left null until a real pilot exists
  to observe it
- A `GET /model/validation-status` endpoint stating, in plain language, that this model
  is not field-validated and that no real outcome-label dataset currently exists
- 59 automated tests across `backend/tests/test_methodological_honesty.py` and
  `test_weather_integration.py` — properly mocked (no real network dependency, Part 19),
  covering geography, provider fallback, caching, IST timestamps, rainfall-anomaly
  pipeline, and every overclaiming-language guard, plus one explicitly opt-in real-network
  integration test (skipped by default)

## Tech stack
- **Model**: Python, scikit-learn (RandomForestClassifier), SHAP (TreeExplainer)
- **Weather**: `requests` against Open-Meteo (immediate, live) and IMD (future, pending
  whitelisting); historical baseline path documented against India OGD + Open-Meteo ERA5
- **Backend**: FastAPI, pandas, numpy
- **Frontend**: self-contained HTML/CSS/JS dashboard, no build step

## Data & Validation status — read before presenting this anywhere
| | |
|---|---|
| Model validation | **Not field validated** |
| Data | **Representative / simulated** |
| Real outcome labels | **Not currently available** |
| Field validation | **Future pilot** |

No public, household- or village-level ground-truth "did this place experience a
livelihood distress cascade" dataset exists in India's open-data ecosystem today.
Meghdoot, e-NAM, MGNREGA MIS and PMFBY expose real *signals*, not a labeled outcome
variable. This is a real constraint on the whole problem space, not a shortcut taken
here — and it's disclosed up front as an intentional research boundary, not a hidden
limitation.

Feature value **ranges** are calibrated to published statistics (see per-feature
`calibration_note` in `backend/data/generate_dataset.py`: IMD/Meghdoot bulletins, e-NAM
price data, MGNREGA MIS dashboards, and the West Bengal rice-farmer
livelihood-vulnerability literature). The **outcome label** used to train the model,
and the scenario trajectory's transition weights, are synthetic constructions
consistent with FEWS NET's livelihoods-based causal structure — not observed events.

Model metrics (`backend/model_artifacts/metrics.json`: AUC 0.73, precision 0.43,
recall 0.63) describe how well the model recovers **the synthetic structure we built
in**, not real-world predictive accuracy. `is_field_validated` is hard-coded `False`.

No live API calls are wired up in this sandbox (network access here is restricted to
package registries). The backend is structured so that `load_snapshot()` in
`app/main.py` and the feature columns in `generate_dataset.py` are the only places that
need to change to plug in Open-Meteo/IMD, Sentinel NDVI (Earth Engine), AGMARKNET/e-NAM,
and NREGA MIS's public endpoints for a real deployment.

Migration is presented only as a **scenario/distress-pressure indicator**, never a
deterministic prediction, by design.

## Setup
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # set IMD_ENABLED, WEATHER_DEMO_FALLBACK, DATA_GOV_IN_API_KEY etc.
python data/generate_dataset.py   # builds representative dataset + provenance metadata
python train_model.py             # trains the real model, writes metrics.json
python export_snapshot.py         # scores all villages, attempts live weather, writes frontend data
python -m pytest tests/ -q        # 59 tests (1 skipped: opt-in real-network integration test)
uvicorn app.main:app --reload --port 8000
```
To see genuinely live Open-Meteo data: deploy anywhere with normal internet egress and
leave `IMD_ENABLED=false` (default) — Open-Meteo needs no key and no whitelisting.
To run the real-network integration test: `KAVACH_RUN_LIVE_INTEGRATION_TESTS=true python -m pytest tests/test_weather_integration.py -k integration`.

## Running locally
API docs auto-served at `http://localhost:8000/docs`. Key endpoints:
`GET /villages`, `GET /villages/{village}`, `GET /model/validation-status`,
`GET /provenance`, `GET /locations`, `GET /weather/{village}`,
`GET /weather/{village}/forecast`, `GET /weather/{village}/warnings`,
`GET /data-health`, `POST /villages/{village}/review`, `GET /villages/{village}/review-log`.
Frontend: open `frontend/kavach_dashboard.html` (embeds a precomputed snapshot so the
published demo works standalone; set `window.KAVACH_API_BASE` before load to point the
officer-review buttons at a real running backend instead of the static fallback).

## Demo flow (Part 24)
Open Kavach → West Bengal location hierarchy → select a village → risk score /100 → why
is risk rising → live Open-Meteo weather (source + timestamp) → forecast → data-health
panel → which inputs are real vs. representative → illustrative scenario trajectory →
suggested actions for officer review → submit Review/Defer/Escalate → backend
confirmation (or honest local-only note if no backend is running) → validation status.

Story: *"See where risk is rising, understand why, know which signals are real, explore
what could happen next, and give the officer clear actions to review."* Not: *"Kavach
predicts exactly what will happen."*

## Future scope
- Wire live feeds (Open-Meteo/IMD, Sentinel NDVI, AGMARKNET, NREGA MIS)
- Partner with a state rural-development department for a real pilot that observes and
  records the `subsequent_outcome` field this build already reserves for it — the only
  way any real accuracy claim becomes possible
- Household/cluster-level prioritization once ethically and operationally reviewed

## Sonarpur live-data pilot

A dedicated live-data pilot location is configured for:

`Sonarpur Station Road, Mission Pally, Narendrapur, Rajpur Sonarpur, Kolkata – 700150, West Bengal, India`

Coordinates: `22.442948, 88.428633` (public geocoded address reference).

The dedicated endpoint is:

`GET /live-area/sonarpur`

It uses the real Open-Meteo provider for current weather and forecast when the deployment has normal internet egress. Demo fallback is disabled in the example configuration for this pilot, so unavailable live data remains `UNAVAILABLE` rather than being fabricated.

**Important:** the livelihood-risk Random Forest score is deliberately withheld for this location until the remaining model inputs (crop stress, market, employment, water stress and vulnerability) are backed by real area-specific data. The live pilot therefore demonstrates genuine weather ingestion without falsely presenting a weather-only reading as a validated livelihood-risk prediction.

A small browser page for this endpoint is included at `frontend/sonarpur_live.html`.


## Sonarpur live pilot + expansion mode
The project now has a dedicated real-data pilot for **Sonarpur Station Road, Mission Pally, Narendrapur, Rajpur Sonarpur, Kolkata – 700150** (22.442948, 88.428633). In `SONARPUR_LIVE_HYBRID` mode, current weather comes from Open-Meteo and rainfall anomaly can be computed against a real Open-Meteo ERA5 historical baseline at runtime. The remaining five livelihood features are deliberately simulated and visibly labeled as such. This lets the demo show a genuine local live signal without pretending the entire livelihood model is field-validated.

`GET /expansion-mode` exposes the wider representative/simulated village layer as an explicit expansion option. This is the intended demonstration pattern: **one real pilot area now, simulated expansion elsewhere until each signal has a defensible real source.**
