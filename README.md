# Kavach — Explainable Livelihood-Risk Early-Warning & Decision Support

![Tests](https://github.com/AstroSaran/hackspire-2026-dinos/actions/workflows/test.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

> 🛡️ **Kavach** (Sanskrit: "shield") - Protecting rural livelihoods through early warning

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

**Architecture**: `WeatherProvider` abstraction (`backend/app/weather/providers.py`) with
`IMDWeatherProvider` (primary) and `OpenMeteoWeatherProvider` (documented fallback), an
orchestration layer with caching and health tracking (`backend/app/weather/service.py`),
and a normalized, provider-independent data model (`backend/app/weather/models.py`) that
never mixes observation and forecast fields.

**IMD investigation — what is actually true, verified during this build:** IMD publishes
real, documented API endpoints (`mausam.imd.gov.in/api/current_wx_api.php`,
`districtwise_rainfall_api.php`, `warnings_district_api.php`, `nowcast_district_api.php`,
and the newer `api.imd.gov.in/api/v1/*` family). **They require IP whitelisting by an IMD
nodal officer.** This was independently confirmed two ways: a live test against a real
endpoint from this build returned HTTP 401, and multiple third-party developer projects
report the identical 401-without-whitelisting behavior. `IMDWeatherProvider` is coded
against the real, correct endpoint contracts and will work once a deployment is
whitelisted and real IMD station/district IDs are supplied — it does not scrape, guess,
or work around the restriction.

**Open-Meteo** (`api.open-meteo.com/v1/forecast`) is a genuinely public, keyless, live
weather API (global NWP model blend — not IMD-sourced), used only as the documented
fallback. It is explicitly labeled "not IMD" everywhere it appears (tested).

**Sandbox limitation, stated plainly:** this development container's network egress is
restricted to package registries and does not include either `mausam.imd.gov.in` or
`api.open-meteo.com` — confirmed via a direct request that returned this container's own
egress-proxy `403 host_not_allowed`, not a rejection from either weather service. Neither
provider could be executed live from inside this container. Both are written against
each API's real, independently-verified contract; run them in an environment with normal
internet egress to get genuinely live data.

**Demo mode** (Part 35): with `WEATHER_DEMO_FALLBACK=true`, a third provider
(`DemoWeatherProvider`) supplies clearly-labeled `SIMULATED_DEMO` weather (deterministic
per-village values, never random, never labeled `LIVE`) so the dashboard's weather card
is demonstrable even where no live provider is reachable. The published dashboard was
exported with this flag on — its weather card says `SIMULATED_DEMO`, not `LIVE`, and
`/data-health` shows the real IMD/Open-Meteo provider failures underneath.

**Per-signal data coverage** (Part 9) — never one blanket LIVE/SIMULATED label; every
response carries a `data_coverage` object:
```
weather:        LIVE | STALE | SIMULATED_DEMO | UNAVAILABLE  (see /data-health for why)
crop:           SIMULATED
market:         SIMULATED
employment:     SIMULATED
water:          SIMULATED
vulnerability:  SIMULATED
```
The live-weather-derived rainfall anomaly (`backend/app/weather_features.py`) is computed
against an explicitly labeled `PROTOTYPE_BASELINE_MM` constant — a real 30-year IMD
climatological normal is not wired in — and is exposed as an **additive, transparent
signal** (`weather.derived_rainfall_anomaly` in the API response), not silently merged
into the trained model's `rainfall_anomaly_pct` feature, so the model's
already-internally-consistent behavior is not disturbed by a partially-sourced
replacement input.

**West Bengal geography** (`backend/app/geography.py`): real Nadia district/block
hierarchy (Krishnanagar Sadar, Tehatta, Ranaghat, Kalyani) with block-headquarters
centroid coordinates (general public geography; resolution marked `block_centroid`, not
village-level GPS). IMD's own numeric district ID for Nadia is not published as an open,
verifiable lookup table, so `imd_district_id` is left `None` rather than guessed —
filling it in is a one-line config change once obtained directly from IMD.

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
- 18 automated tests (`backend/tests/test_methodological_honesty.py`) that fail if any
  future change re-introduces overclaiming language, mislabels simulated data as live,
  or conflates the scenario trajectory with an observed outcome

## Tech stack
- **Model**: Python, scikit-learn (RandomForestClassifier), SHAP (TreeExplainer)
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

## Quick Start

### Automated Setup (Recommended)
```bash
# Linux/macOS
./setup.sh

# Windows PowerShell
.\setup.ps1
```

### Manual Setup
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # then set WEATHER_PROVIDER, WEATHER_DEMO_FALLBACK etc.
python data/generate_dataset.py   # builds representative dataset + provenance metadata
python train_model.py             # trains the real model, writes metrics.json
python export_snapshot.py         # scores all villages, fetches weather, writes frontend data
python -m pytest tests/ -q        # 31 tests: methodological honesty + geography + weather + failure modes
uvicorn app.main:app --reload --port 8000
```

## Running locally
API docs auto-served at `http://localhost:8000/docs`. Key endpoints:
`GET /villages`, `GET /villages/{village}`, `GET /model/validation-status`,
`GET /provenance`, `GET /locations`, `GET /weather/{village}`,
`GET /weather/{village}/forecast`, `GET /weather/{village}/warnings`,
`GET /data-health`, `POST /villages/{village}/review`.
Frontend: open `frontend/kavach_dashboard.html` (embeds a precomputed snapshot,
including the real weather-provider attempt's result, so the published demo works
without a live backend running).

## Demo flow
1. Village selected → 2. Observed signals (with provenance badges) → 3. Model
assessment (estimated risk score + uncertainty) → 4. Driver contribution (indicative
SHAP) → 5. Illustrative scenario trajectory → 6. Suggested actions for officer review
→ 7. Officer review (Approve / Defer / Escalate, logged) → 8. Outcome tracking (null
until a real pilot exists).

Story: *"Many systems already generate signals. Kavach turns those fragmented signals
into an auditable early-warning workflow."* Not: *"Kavach predicts exactly what will
happen."*

## Future scope
- Wire live feeds (Open-Meteo/IMD, Sentinel NDVI, AGMARKNET, NREGA MIS)
- Partner with a state rural-development department for a real pilot that observes and
  records the `subsequent_outcome` field this build already reserves for it — the only
  way any real accuracy claim becomes possible
- Household/cluster-level prioritization once ethically and operationally reviewed

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Project Structure

```
kavach/
├── backend/
│   ├── app/              # FastAPI application
│   │   ├── main.py       # API endpoints
│   │   ├── engine.py     # Risk assessment & ML logic
│   │   ├── geography.py  # Location resolution (West Bengal)
│   │   ├── review.py     # Human-in-the-loop review logging
│   │   └── weather/      # Weather integration (IMD/Open-Meteo)
│   ├── data/             # Dataset generation & storage
│   ├── model_artifacts/  # Trained model & evaluation metrics
│   ├── tests/            # Comprehensive test suite
│   └── requirements.txt  # Python dependencies
├── frontend/             # Static HTML dashboard
├── frontend_data/        # Precomputed village snapshots
├── setup.sh              # Quick setup (Linux/macOS)
├── setup.ps1             # Quick setup (Windows)
└── CONTRIBUTING.md       # Contribution guidelines
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Citation

If you use Kavach in your research or project, please cite:

```bibtex
@software{kavach2026,
  title = {Kavach: Explainable Livelihood-Risk Early-Warning System},
  author = {AstroSaran},
  year = {2026},
  url = {https://github.com/AstroSaran/hackspire-2026-dinos}
}
```

## Acknowledgments

- IMD (India Meteorological Department) for weather data infrastructure
- Open-Meteo for providing open weather API
- FEWS NET for livelihood-vulnerability framework
- West Bengal government data sources
