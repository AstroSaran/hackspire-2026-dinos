"""
Kavach — Scoring, Explainability, Cascade & Intervention Engine
=================================================================
This is the real decision layer described in the product's "moat": not
another data source, but signals -> risk -> explanation -> cascade ->
intervention, in one auditable pipeline.
"""
import pickle
import json
import os
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.dirname(__file__))  # backend/
FEATURES = [
    "rainfall_anomaly_pct", "crop_stress_index", "mandi_price_deviation_pct",
    "mgnrega_demand_spike_pct", "water_stress_index", "historical_vulnerability",
]
FRIENDLY = {
    "rainfall_anomaly_pct": "Rainfall deficit",
    "crop_stress_index": "Crop stress",
    "mandi_price_deviation_pct": "Market decline",
    "mgnrega_demand_spike_pct": "Employment pressure",
    "water_stress_index": "Water stress",
    "historical_vulnerability": "Structural vulnerability",
}

with open(os.path.join(HERE, "model_artifacts", "risk_model.pkl"), "rb") as f:
    MODEL = pickle.load(f)
with open(os.path.join(HERE, "model_artifacts", "feature_importance.json")) as f:
    IMPORTANCE = json.load(f)


def status_for(score: int) -> str:
    if score >= 75:
        return "critical"
    if score >= 55:
        return "risk"
    if score >= 35:
        return "watch"
    return "stable"


def _severity(feature: str, value: float) -> float:
    """Map a raw feature value to a 0-1 'how bad is this' severity, so that
    driver contribution reflects both model importance AND how extreme the
    reading is for this village (a research-literature-consistent choice:
    exposure/sensitivity should scale with shock magnitude, not just weight)."""
    if feature == "rainfall_anomaly_pct":
        return np.clip(max(0, -value) / 60, 0, 1)  # deficits matter most
    if feature == "crop_stress_index":
        return np.clip(value / 100, 0, 1)
    if feature == "mandi_price_deviation_pct":
        return np.clip(max(0, -value) / 40, 0, 1)
    if feature == "mgnrega_demand_spike_pct":
        return np.clip(max(0, value) / 60, 0, 1)
    if feature == "water_stress_index":
        return np.clip(value / 100, 0, 1)
    if feature == "historical_vulnerability":
        return np.clip(value / 100, 0, 1)
    return 0.0


def score_village(row: dict) -> dict:
    """row: dict with the 6 raw feature columns. Returns score, status,
    driver attribution (%), and a 5-stage cascade probability chain."""
    x = pd.DataFrame([{k: row[k] for k in FEATURES}])
    proba = float(MODEL.predict_proba(x)[0, 1])
    score = int(round(proba * 100))
    status = status_for(score)

    # Driver attribution: model feature_importance (global, "how much this
    # signal matters in general") x local severity (how bad it is HERE),
    # renormalized to sum to 100. This is a lightweight, transparent stand-in
    # for a full SHAP decomposition -- deterministic and auditable, which
    # matters more than marginal precision for a public-sector decision tool.
    raw = {f: IMPORTANCE[f] * _severity(f, row[f]) for f in FEATURES}
    total = sum(raw.values()) or 1e-9
    drivers = sorted(
        [[FRIENDLY[f], round(100 * v / total, 1)] for f, v in raw.items()],
        key=lambda p: -p[1],
    )

    # Cascade chain: conditional probability of each downstream stage, driven
    # by the FEWS-NET-style causal graph (shock -> crop/income loss -> distress
    # borrowing -> employment pressure -> migration risk). Each stage's
    # probability = overall risk probability tempered by the stage-specific
    # driver strength, monotonically non-increasing down the chain (a cascade
    # can't be "more likely" than the shock that started it).
    crop_component = _severity("crop_stress_index", row["crop_stress_index"])
    income_component = 0.5 * crop_component + 0.5 * _severity("mandi_price_deviation_pct", row["mandi_price_deviation_pct"])
    debt_component = income_component * (0.6 + 0.4 * _severity("historical_vulnerability", row["historical_vulnerability"]))
    employment_component = 0.5 * debt_component + 0.5 * _severity("mgnrega_demand_spike_pct", row["mgnrega_demand_spike_pct"])
    migration_component = 0.7 * employment_component + 0.3 * debt_component

    stage_components = [crop_component, income_component, debt_component, employment_component, migration_component]
    # Each stage's conditional probability = previous stage's probability x a
    # transition factor that reflects how strong THIS stage's specific driver
    # is (0.40-1.00 range). This guarantees a monotonically non-increasing
    # chain (you can't be more likely to reach stage N than stage N-1) while
    # still differentiating villages by which stage breaks the cascade.
    cascade = []
    prev = proba
    for comp in stage_components:
        transition = 0.40 + 0.60 * comp
        prev = prev * transition
        cascade.append(int(round(prev * 100)))

    return {
        "risk_score": score,
        "risk_probability": round(proba, 3),
        "status": status,
        "drivers": drivers,
        "cascade": cascade,
    }


CASCADE_STAGES = [
    "Weather / water shock",
    "Crop stress & yield loss",
    "Income loss & distress sale",
    "Debt / reduced coping capacity",
    "Employment pressure (MGNREGA demand)",
    "Distress-migration risk",
]

# ---------------------------------------------------------------------------
# Intervention engine — rule-based, transparent, tied to REAL existing
# government mechanisms (Rule: "not a new scheme, a coordination layer").
# ---------------------------------------------------------------------------

def rank_interventions(row: dict, result: dict) -> list:
    d = {name: pct for name, pct in result["drivers"]}
    candidates = []

    def add(title, program, driver_key, urgency_days, benefit, cost, trigger):
        if trigger:
            candidates.append({
                "title": title,
                "program": program,
                "urgency_days": urgency_days,
                "benefit": benefit,
                "cost": cost,
                "linked_driver": driver_key,
                "driver_share": d.get(driver_key, 0),
            })

    add("Push targeted agromet advisory (irrigation scheduling / drought-tolerant practice)",
        "mKisan / Kisan Sarathi", "Rainfall deficit", 5, "High", "Low",
        trigger=row["rainfall_anomaly_pct"] < -10 or row["crop_stress_index"] > 40)

    add("Flag for early PMFBY crop-loss assessment",
        "PMFBY", "Crop stress", 7, "High", "Low",
        trigger=row["crop_stress_index"] > 35)

    add("Verify crop-insurance enrollment & eligibility before window closes",
        "PMFBY", "Crop stress", 10, "Medium", "Low",
        trigger=row["crop_stress_index"] > 25)

    add("Alert mandi/market cell — consider MSP procurement support or storage linkage",
        "e-NAM / State Marketing Board", "Market decline", 10, "Medium", "Medium",
        trigger=row["mandi_price_deviation_pct"] < -8)

    add("Pre-position MGNREGA worksite allocation ahead of demand surge",
        "MGNREGA", "Employment pressure", 7, "High", "Low",
        trigger=row["mgnrega_demand_spike_pct"] > 15)

    add("Coordinate water-stress relief (tanker supply / groundwater recharge check)",
        "State PHE / CGWB", "Water stress", 14, "Medium", "Medium",
        trigger=row["water_stress_index"] > 45)

    add("Prioritise for cash-transfer / social-protection outreach given structural vulnerability",
        "State Social Welfare", "Structural vulnerability", 14, "Medium", "Medium",
        trigger=row["historical_vulnerability"] > 60 and result["risk_score"] > 45)

    add("Routine monitoring — no active intervention required",
        "—", None, None, "—", "—",
        trigger=len(candidates) == 0)

    # Rank by (driver_share desc, urgency asc)
    def sort_key(c):
        urgency = c["urgency_days"] if c["urgency_days"] is not None else 999
        return (-c["driver_share"], urgency)

    candidates.sort(key=sort_key)
    for i, c in enumerate(candidates[:4]):
        c["priority"] = "High priority" if i == 0 and result["risk_score"] >= 55 else (
            "Medium" if result["risk_score"] >= 35 else "Watch")
    return candidates[:4]
