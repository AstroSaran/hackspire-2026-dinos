# Kavach — Livelihood Resilience Grid

## One-line description
An early-warning and intervention-orchestration layer that detects when
climate, crop, market and employment risks are converging on a village, and
recommends the earliest feasible action using **existing** government
mechanisms (Meghdoot advisories, PMFBY, MGNREGA, e-NAM) instead of building
another standalone farmer app.

## Problem
Weather, crop, market and employment data already exist in separate
government systems. A household experiences these as one connected crisis;
the current information architecture only detects individual events, not the
interaction between them — so intervention comes late, after distress has
already compounded.

## Solution
A **risk-convergence + cascade-prediction + intervention-ranking** pipeline:
six signals feed a trained classifier that outputs a 0–100 risk score, a
transparent driver breakdown ("why is risk rising"), a 5-stage causal cascade
(shock → crop stress → income loss → debt → employment pressure → migration
risk), and a ranked list of interventions tied to real, existing programs.

## Key features
- Real trained model (RandomForest, scikit-learn) — not a hand-tuned demo score
- Transparent, auditable driver attribution (feature importance × local severity)
- Causal cascade chain with monotonically-decaying conditional probabilities
- Rule-based intervention engine mapped to PMFBY / MGNREGA / mKisan / e-NAM
- A live 8-week "what-if" simulation computed by calling the real model at
  each stage (not scripted numbers) — used for the demo's wow moment
- FastAPI backend with a documented path to swap simulated inputs for live feeds

## Why it is different
Existing systems (Meghdoot, e-NAM, PMFBY, MGNREGA, FEWS NET, WFP HungerMap)
already do climate, crop, market or food-security monitoring individually.
The differentiator here is **not another data source** — it's the decision
graph connecting signals → risk → explanation → cascade → intervention →
outcome, built specifically around India's existing scheme infrastructure.

## Architecture
```
Data sources (weather / crop / market / employment / water / vulnerability)
        -> Feature engineering (backend/app/engine.py: FEATURES)
        -> RandomForest risk model (backend/train_model.py)
        -> Explainability layer (feature importance x local severity)
        -> Cascade engine (causal-graph-weighted transition chain)
        -> Intervention engine (rule-based, tied to real programs)
        -> FastAPI (backend/app/main.py)
        -> Dashboard (frontend/kavach_dashboard.html)
```

## Tech stack
- **Model**: Python, scikit-learn (RandomForestClassifier)
- **Backend**: FastAPI, pandas, numpy
- **Frontend**: Self-contained HTML/CSS/JS dashboard (no build step; embeds
  precomputed model output for the published demo, calls the live API when
  deployed with a backend running)

## AI/ML component
A tabular RandomForestClassifier is the risk engine, trained on 1,200
representative observation-samples (40 per village × 30 villages). It is
**not** an LLM — per design, an LLM is only appropriate downstream, to turn
the model's numeric output into plain-language explanation, never to compute
the score itself. Held-out evaluation: **AUC 0.73, precision 0.43, recall
0.63** (see `backend/model_artifacts/metrics.json`).

##  Data & Limitations — read before presenting this
1. **No public, household-level, ground-truth "did this household suffer a
   livelihood distress cascade" dataset exists.** Meghdoot, e-NAM, MGNREGA MIS
   and PMFBY expose real signals, not a labeled outcome variable. This is a
   real constraint on the whole problem space, not a shortcut we took.
2. The **feature value ranges** (rainfall anomaly, crop stress, price
   deviation, MGNREGA demand spike, water stress, historical vulnerability)
   are calibrated to match published statistic ranges cited in the project's
   research review (IMD/Meghdoot bulletins, e-NAM price data, MGNREGA MIS
   dashboards, and West Bengal rice-farmer livelihood-vulnerability
   literature) — see `backend/data/generate_dataset.py` docstring for exact
   sourcing per feature.
3. The **outcome label** used to train the model is synthetically generated
   from the causal cascade structure (FEWS NET's livelihoods-based
   methodology), plus noise. It is a credible, literature-grounded simulation
   — it is not a real observed outcome.
4. Therefore: **the AUC/precision/recall numbers describe how well the model
   recovers the synthetic structure we built in, not real-world predictive
   accuracy.** Do not present them as validated field accuracy. Say so
   explicitly if a judge asks (see PITCH.md Q&A).
5. **No live API calls are wired up.** This sandbox's network is restricted;
   the backend is architected so `load_snapshot()` in `app/main.py` and the
   feature columns in `generate_dataset.py` are the only places that need to
   change to plug in Open-Meteo/IMD, Sentinel NDVI (Earth Engine), AGMARKNET/
   e-NAM, and NREGA MIS's public endpoints for a real deployment.
6. Migration is presented as a **distress-pressure indicator**, never a
   deterministic prediction, by design.

## Setup
```bash
cd backend
pip install -r requirements.txt
python data/generate_dataset.py   # builds representative dataset
python train_model.py             # trains the real model, writes metrics.json
python export_snapshot.py         # scores all villages + builds the demo simulation
uvicorn app.main:app --reload --port 8000
```

## Environment variables
None required for the representative pilot. For a live deployment, add:
`OPENMETEO_API_KEY` (optional, free tier works without one), `DATA_GOV_IN_API_KEY`
(AGMARKNET/e-NAM), `NREGA_MIS_ENDPOINT`, `GEE_SERVICE_ACCOUNT_JSON` (Sentinel NDVI).

## Running locally
See Setup above. API docs auto-served at `http://localhost:8000/docs`.
Frontend: open `frontend/kavach_dashboard.html` directly, or serve it and
point its fetch calls at the running API (currently it embeds a precomputed
snapshot so the published demo works without a live backend).

## Demo flow
1. Open the dashboard — 30 villages, colour-coded by status.
2. Click the highest-risk village → show driver breakdown, cascade, and
   ranked interventions (all real model output).
3. Click **"Simulate 8-week trajectory"** — watch Bagula move
   🟢 stable → 🟡 watch → 🟠 at-risk → 🔴 critical, with the model recomputing
   score/drivers/cascade/interventions at each stage. The dashboard states the
   real computed lead time (weeks of warning before critical status).

## Future scope
- Wire live feeds (Open-Meteo/IMD, Sentinel NDVI, AGMARKNET, NREGA MIS)
- Replace feature-importance-based attribution with full SHAP decomposition
- Partner with a state rural development department for a real pilot with an
  actual outcome-tracking process (the only way to get real ground truth)
- Household/cluster-level prioritization once ethically and operationally reviewed
