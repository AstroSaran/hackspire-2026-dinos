"""
Kavach API — Explainable Livelihood-Risk Early-Warning & Decision Support
============================================================================
Run locally:
    uvicorn app.main:app --reload --port 8000

Endpoints:
    GET  /villages                    -> list of all villages with score/status (+ pilot_mode banner)
    GET  /villages/{village}          -> full assessment: score, uncertainty, drivers, data quality,
                                          scenario trajectory, suggested actions, validation status
    GET  /district/summary            -> counts by status band
    POST /villages/{village}/what-if  -> re-score with overridden feature values (for demo/scenario exploration)
    GET  /model/metrics               -> model evaluation metrics + explicit non-field-validation notice
    GET  /model/validation-status     -> the validation-framework status block (section 7 of the design)
    GET  /provenance                  -> per-feature data provenance metadata
    POST /villages/{village}/review   -> log an officer review (human-in-the-loop step)
    GET  /villages/{village}/review-log -> list logged reviews for a village

IMPORTANT: everything under "data" in this API is SIMULATED_REPRESENTATIVE
(see backend/data/generate_dataset.py). This is a pilot/representative mode,
not a live government data feed, and no output here is a field-validated
prediction. See GET /model/validation-status.
"""
import os
import json
import pandas as pd
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from . import engine
from . import review as review_module
from . import geography
from . import weather_features
from .weather import service as weather_service
from .weather.providers import Location as WeatherLocation

HERE = os.path.dirname(os.path.dirname(__file__))

PILOT_BANNER = (
    "Pilot / representative mode: livelihood-signal scores are generated from representative "
    "data and are not field-validated predictions. Weather is a genuine live-data integration "
    "attempt (IMD primary, Open-Meteo documented fallback) — see /data-health for its real status."
)

app = FastAPI(title="Kavach — Explainable Livelihood-Risk Decision Support API", version="0.3.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DATA_COVERAGE_STATIC = {
    "crop": "SIMULATED", "market": "SIMULATED", "employment": "SIMULATED",
    "water": "SIMULATED", "vulnerability": "SIMULATED",
}


def _weather_location(village: str) -> WeatherLocation:
    rec = geography.resolve_location(village)
    if rec is None:
        raise HTTPException(404, f"No West Bengal location record for '{village}'")
    return WeatherLocation(**rec)


def _weather_bundle(village: str):
    loc = _weather_location(village)
    obs = weather_service.get_current_weather(loc)
    fc = weather_service.get_forecast_weather(loc)
    warnings = weather_service.get_warnings(loc)
    return obs, fc, warnings


def load_snapshot() -> pd.DataFrame:
    return pd.read_csv(os.path.join(HERE, "data", "current_snapshot.csv"))


def _raw_signals_with_provenance(row: pd.Series) -> list:
    out = []
    for f in engine.FEATURES:
        prov = engine.PROVENANCE.get(f, {})
        out.append({
            "feature": f,
            "label": engine.FRIENDLY[f],
            "value": row[f],
            "signal_type": prov.get("signal_type"),
            "data_status": prov.get("data_status"),
            "source": prov.get("source"),
            "geographic_level": prov.get("geographic_level"),
            "freshness": prov.get("freshness"),
            "confidence": prov.get("confidence"),
            "live_equivalent": prov.get("live_equivalent"),
        })
    return out


def build_village_result(row: pd.Series, include_live_weather: bool = True):
    feat = row[engine.FEATURES].to_dict()
    result = engine.assess_risk(feat)
    actions = engine.suggest_actions(feat, result)

    weather_block = None
    weather_data_status = "UNAVAILABLE"
    if include_live_weather:
        try:
            obs, fc, warnings = _weather_bundle(row["village"])
            weather_data_status = obs.status  # LIVE | STALE | UNAVAILABLE
            weather_block = {
                "observation": obs.to_dict(),
                "forecast": fc.to_dict(),
                "warnings": [w.to_dict() for w in warnings],
                "derived_rainfall_anomaly": weather_features.rainfall_anomaly_from_observation(obs),
            }
        except Exception as e:  # never let a weather failure break the risk assessment
            weather_block = {"error": str(e)}

    data_coverage = {"weather": weather_data_status, **DATA_COVERAGE_STATIC}

    return {
        "village": row["village"],
        "zone": row["zone"],
        "pilot_mode_banner": PILOT_BANNER,
        "data_coverage": data_coverage,
        "weather": weather_block,
        "observed_signals": _raw_signals_with_provenance(row),
        "model_assessment": {
            "estimated_risk_score": result["risk_score"],
            "status": result["status"],
            "model_uncertainty": result["model_uncertainty"],
            "note": "Model risk score, not a calibrated probability of poverty, migration, debt, or distress.",
        },
        "driver_contribution_indicative": {
            "method": "SHAP (TreeExplainer) over the trained RandomForest",
            "note": "Explains the MODEL's output, not proven real-world causation.",
            "drivers": result["drivers"],
        },
        "data_quality": result["data_quality"],
        "scenario_trajectory": {
            "note": "Illustrative scenario trajectory generated by hand-designed transition weights over "
                    "representative inputs. Not a forecast validated against field outcomes.",
            "stages": result["scenario_trajectory"],
        },
        "suggested_actions_for_officer_review": actions,
        "validation_status": result["validation_status"],
    }


@app.get("/villages")
def list_villages():
    df = load_snapshot()
    out = []
    for _, row in df.iterrows():
        feat = row[engine.FEATURES].to_dict()
        result = engine.assess_risk(feat)
        out.append({"village": row["village"], "zone": row["zone"],
                     "estimated_risk_score": result["risk_score"], "status": result["status"]})
    out.sort(key=lambda v: -v["estimated_risk_score"])
    return {"pilot_mode_banner": PILOT_BANNER, "villages": out}


@app.get("/district/summary")
def district_summary():
    listing = list_villages()
    villages = listing["villages"]
    counts = {"stable": 0, "watch": 0, "risk": 0, "critical": 0}
    for v in villages:
        counts[v["status"]] += 1
    return {"district": "Nadia (representative pilot)", "total_villages": len(villages), "counts": counts,
            "pilot_mode_banner": PILOT_BANNER}


@app.get("/villages/{village}")
def village_detail(village: str):
    df = load_snapshot()
    match = df[df["village"].str.lower() == village.lower()]
    if match.empty:
        raise HTTPException(404, f"Village '{village}' not found")
    return build_village_result(match.iloc[0])


@app.post("/villages/{village}/what-if")
def village_what_if(village: str, overrides: dict = Body(default={})):
    """Explore a scenario: overrides = {'rainfall_anomaly_pct': -40, ...}.
    This is scenario exploration, not a historical prediction."""
    df = load_snapshot()
    match = df[df["village"].str.lower() == village.lower()]
    if match.empty:
        raise HTTPException(404, f"Village '{village}' not found")
    row = match.iloc[0].copy()
    for k, v in overrides.items():
        if k in engine.FEATURES:
            row[k] = v
    return build_village_result(row)


@app.get("/model/metrics")
def model_metrics():
    with open(os.path.join(HERE, "model_artifacts", "metrics.json")) as f:
        metrics = json.load(f)
    with open(os.path.join(HERE, "model_artifacts", "feature_importance.json")) as f:
        importance = json.load(f)
    return {
        "metrics": metrics,
        "feature_importance_global": importance,
        "important_note": "These metrics describe how well the model recovers a synthetic, "
                           "literature-grounded causal structure in REPRESENTATIVE data. They are "
                           "NOT a validated real-world accuracy figure. See /model/validation-status.",
    }


@app.get("/model/validation-status")
def validation_status():
    return engine.VALIDATION_STATUS


@app.get("/provenance")
def provenance():
    return engine.PROVENANCE


@app.post("/villages/{village}/review")
def submit_review(village: str, officer_decision: str = Body(...), action_taken: str = Body(default=None)):
    """Human-in-the-loop step: SYSTEM ASSESSMENT -> OFFICER REVIEW -> ACTION.
    Does not allocate benefits or make eligibility decisions — logs a review only."""
    df = load_snapshot()
    match = df[df["village"].str.lower() == village.lower()]
    if match.empty:
        raise HTTPException(404, f"Village '{village}' not found")
    feat = match.iloc[0][engine.FEATURES].to_dict()
    predicted = engine.assess_risk(feat)
    return review_module.log_officer_review(village, predicted, officer_decision, action_taken)


@app.get("/villages/{village}/review-log")
def review_log(village: str):
    return review_module.list_review_log(village)


@app.get("/")
def root():
    return {"service": "Kavach — Explainable Livelihood-Risk Decision Support API",
            "pilot_mode_banner": PILOT_BANNER, "docs": "/docs"}


# --- Weather (Part 30) -------------------------------------------------------

@app.get("/locations")
def locations():
    return {"country": geography.COUNTRY, "state": geography.STATE,
            "districts": {d: {"blocks": list(b["blocks"].keys())} for d, b in geography.DISTRICTS.items()},
            "villages": geography.all_villages()}


@app.get("/weather/{village}")
def weather_current(village: str):
    loc = _weather_location(village)
    obs = weather_service.get_current_weather(loc)
    return obs.to_dict()


@app.get("/weather/{village}/forecast")
def weather_forecast(village: str):
    loc = _weather_location(village)
    fc = weather_service.get_forecast_weather(loc)
    return fc.to_dict()


@app.get("/weather/{village}/warnings")
def weather_warnings(village: str):
    loc = _weather_location(village)
    warnings = weather_service.get_warnings(loc)
    return [w.to_dict() for w in warnings]


@app.get("/data-health")
def data_health():
    return {
        "providers": weather_service.get_data_health(),
        "signals": {"weather": "see providers above", **DATA_COVERAGE_STATIC},
    }
