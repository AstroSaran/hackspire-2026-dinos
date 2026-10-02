"""
Kavach API — Livelihood Early Warning
=======================================
Run locally:
    uvicorn app.main:app --reload --port 8000

Endpoints:
    GET  /villages                 -> list of all villages with score/status
    GET  /villages/{village}       -> full detail: score, drivers, cascade, interventions
    GET  /district/summary         -> counts by status band
    POST /villages/{village}/what-if  -> re-score with overridden feature values (for demo/simulation)
    GET  /model/metrics            -> honest model evaluation metrics + data-provenance note

Data provenance: see backend/data/generate_dataset.py docstring. Snapshot data
is REPRESENTATIVE/SIMULATED, calibrated to published statistic ranges, not a
live feed. Swap `load_snapshot()` for a real ingestion call to go live.
"""
import os
import json
import pandas as pd
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from . import engine

HERE = os.path.dirname(os.path.dirname(__file__))

app = FastAPI(title="Kavach — Livelihood Early Warning API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def load_snapshot() -> pd.DataFrame:
    return pd.read_csv(os.path.join(HERE, "data", "current_snapshot.csv"))


def build_village_result(row: pd.Series) -> dict:
    feat = row[engine.FEATURES].to_dict()
    result = engine.score_village(feat)
    interventions = engine.rank_interventions(feat, result)
    return {
        "village": row["village"],
        "zone": row["zone"],
        "raw_signals": feat,
        "risk_score": result["risk_score"],
        "status": result["status"],
        "drivers": result["drivers"],
        "cascade": {"stages": engine.CASCADE_STAGES, "probabilities": [None] + result["cascade"]},
        "interventions": interventions,
    }


@app.get("/villages")
def list_villages():
    df = load_snapshot()
    out = []
    for _, row in df.iterrows():
        feat = row[engine.FEATURES].to_dict()
        result = engine.score_village(feat)
        out.append({"village": row["village"], "zone": row["zone"],
                     "risk_score": result["risk_score"], "status": result["status"]})
    out.sort(key=lambda v: -v["risk_score"])
    return out


@app.get("/district/summary")
def district_summary():
    villages = list_villages()
    counts = {"stable": 0, "watch": 0, "risk": 0, "critical": 0}
    for v in villages:
        counts[v["status"]] += 1
    return {"district": "Nadia (representative pilot)", "total_villages": len(villages), "counts": counts}


@app.get("/villages/{village}")
def village_detail(village: str):
    df = load_snapshot()
    match = df[df["village"].str.lower() == village.lower()]
    if match.empty:
        raise HTTPException(404, f"Village '{village}' not found")
    return build_village_result(match.iloc[0])


@app.post("/villages/{village}/what-if")
def village_what_if(village: str, overrides: dict = Body(default={})):
    """Simulate a shock: overrides = {'rainfall_anomaly_pct': -40, ...}"""
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
    return {"metrics": metrics, "feature_importance": importance}


@app.get("/")
def root():
    return {"service": "Kavach Livelihood Early Warning API", "docs": "/docs"}
