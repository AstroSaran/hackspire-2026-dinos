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

## Setup
```bash
cd backend
pip install -r requirements.txt
python data/generate_dataset.py   # builds representative dataset + provenance metadata
python train_model.py             # trains the real model, writes metrics.json
python export_snapshot.py         # scores all villages + builds the demo scenario, writes frontend data
python -m pytest tests/ -q        # 18 tests: methodological-honesty invariants
uvicorn app.main:app --reload --port 8000
```

## Running locally
API docs auto-served at `http://localhost:8000/docs`. Key endpoints:
`GET /villages`, `GET /villages/{village}`, `GET /model/validation-status`,
`GET /provenance`, `POST /villages/{village}/review`.
Frontend: open `frontend/kavach_dashboard.html` (embeds a precomputed snapshot so the
published demo works without a live backend running).

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
