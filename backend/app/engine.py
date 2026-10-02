"""
Kavach — Risk Assessment, Explanation, Scenario & Intervention Engine
=======================================================================
Reframed per methodological correction: this module NEVER claims to predict
real-world poverty, migration, debt or distress with validated probability.
It produces:
  - an "estimated risk score" (0-100) from a trained RandomForest, plus a
    genuine model-uncertainty measure (disagreement across trees) — NOT a
    calibrated real-world probability
  - real SHAP-based driver contribution, explicitly labeled as model
    explanation, not proof of real-world causation
  - a labeled SCENARIO TRAJECTORY (not a "predicted cascade") built from
    hand-designed transition weights, with each stage tagged by evidence
    status (OBSERVED_SIGNAL / SCENARIO_ESTIMATE / SCENARIO_INDICATOR) and a
    qualitative relative-risk level rather than a bare probability number
  - rule-based, auditable intervention suggestions FOR OFFICER REVIEW, never
    described as "the system's decision"

See data/generate_dataset.py for full data-provenance metadata (this is
SIMULATED_REPRESENTATIVE data throughout this build).
"""
import pickle
import json
import os
import numpy as np
import pandas as pd
import shap

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
with open(os.path.join(HERE, "data", "feature_provenance.json")) as f:
    PROVENANCE = json.load(f)

_EXPLAINER = shap.TreeExplainer(MODEL)

DATA_STATUS_SIMULATED = "SIMULATED_REPRESENTATIVE"

VALIDATION_STATUS = {
    "model_validation": "Not field validated",
    "data": "Representative / simulated",
    "real_outcome_labels": "Not currently available",
    "field_validation": "Future pilot",
    "note": (
        "No public, household- or village-level ground-truth 'did this place experience "
        "a livelihood distress cascade' dataset exists in India's open-data ecosystem today. "
        "All scores, explanations and trajectories below are computed by a real, running "
        "pipeline over representative/simulated inputs. This is an intentional research "
        "boundary, disclosed up front — not a hidden limitation."
    ),
}


def status_for(score: int) -> str:
    if score >= 75:
        return "critical"
    if score >= 55:
        return "risk"
    if score >= 35:
        return "watch"
    return "stable"


def _severity(feature: str, value: float) -> float:
    """0-1 'how extreme is this reading' — used for the scenario trajectory only.
    Real driver attribution below uses SHAP, not this function."""
    if feature == "rainfall_anomaly_pct":
        return float(np.clip(max(0, -value) / 60, 0, 1))
    if feature == "crop_stress_index":
        return float(np.clip(value / 100, 0, 1))
    if feature == "mandi_price_deviation_pct":
        return float(np.clip(max(0, -value) / 40, 0, 1))
    if feature == "mgnrega_demand_spike_pct":
        return float(np.clip(max(0, value) / 60, 0, 1))
    if feature == "water_stress_index":
        return float(np.clip(value / 100, 0, 1))
    if feature == "historical_vulnerability":
        return float(np.clip(value / 100, 0, 1))
    return 0.0


def _relative_level(v: float) -> str:
    if v >= 0.70:
        return "HIGH"
    if v >= 0.45:
        return "MODERATE-HIGH"
    if v >= 0.20:
        return "MODERATE"
    return "LOW"


def _data_quality(row: dict) -> dict:
    """Confidence should degrade if inputs are missing/out-of-expected-range.
    In this representative build nothing is missing, so quality is uniformly
    'simulated - not field data' rather than a fabricated high score."""
    missing = [f for f in FEATURES if row.get(f) is None or (isinstance(row.get(f), float) and np.isnan(row[f]))]
    completeness = 1.0 - len(missing) / len(FEATURES)
    return {
        "data_status": DATA_STATUS_SIMULATED,
        "completeness": round(completeness, 2),
        "missing_features": missing,
        "overall_quality_label": "Representative simulation (not live data)" if not missing
        else "Representative simulation, incomplete inputs",
    }


def assess_risk(row: dict) -> dict:
    """row: dict with the 6 raw feature columns.
    Returns estimated risk score, model uncertainty, SHAP-based driver
    explanation, data quality/provenance, and a labeled scenario trajectory.
    NOTHING here is a validated real-world probability — see VALIDATION_STATUS."""
    x = pd.DataFrame([{k: row[k] for k in FEATURES}])
    x_arr = x.to_numpy()  # avoid per-tree "fitted without feature names" warnings

    # --- Model risk score (NOT a calibrated real-world probability) ---
    tree_probas = np.array([t.predict_proba(x_arr)[0, 1] for t in MODEL.estimators_])
    mean_proba = float(tree_probas.mean())
    score = int(round(mean_proba * 100))
    status = status_for(score)

    # --- Genuine model uncertainty: disagreement across the forest's trees ---
    tree_std = float(tree_probas.std())
    if tree_std < 0.08:
        uncertainty_label = "low model disagreement"
    elif tree_std < 0.18:
        uncertainty_label = "moderate model disagreement"
    else:
        uncertainty_label = "high model disagreement"

    # --- Real SHAP explanation (model explanation, not real-world causation) ---
    shap_values = _EXPLAINER.shap_values(x)
    sv = np.asarray(shap_values)
    if sv.ndim == 3:  # (n_samples, n_features, n_classes)
        contrib = sv[0, :, 1]
    else:  # (n_samples, n_features) already class-1
        contrib = sv[0]
    abs_total = np.abs(contrib).sum() or 1e-9
    drivers = sorted(
        [[FRIENDLY[f], round(100 * abs(c) / abs_total, 1), ("increases" if c > 0 else "decreases")]
         for f, c in zip(FEATURES, contrib)],
        key=lambda p: -p[1],
    )

    data_quality = _data_quality(row)

    # --- Scenario trajectory (NOT a predicted/validated cascade) ---
    crop_component = _severity("crop_stress_index", row["crop_stress_index"])
    income_component = 0.5 * crop_component + 0.5 * _severity("mandi_price_deviation_pct", row["mandi_price_deviation_pct"])
    debt_component = income_component * (0.6 + 0.4 * _severity("historical_vulnerability", row["historical_vulnerability"]))
    employment_component = _severity("mgnrega_demand_spike_pct", row["mgnrega_demand_spike_pct"])
    migration_component = 0.7 * (0.5 * debt_component + 0.5 * employment_component) + 0.3 * debt_component

    stage_defs = [
        ("Weather / water shock", _severity("rainfall_anomaly_pct", row["rainfall_anomaly_pct"]), "OBSERVED_SIGNAL"),
        ("Crop stress & yield loss", crop_component, "OBSERVED_SIGNAL"),
        ("Income pressure & distress-sale risk", income_component, "SCENARIO_ESTIMATE"),
        ("Debt / reduced coping capacity", debt_component, "SCENARIO_ESTIMATE"),
        ("Employment pressure (MGNREGA demand)", employment_component, "OBSERVED_SIGNAL"),
        ("Distress-migration pressure", migration_component, "SCENARIO_INDICATOR"),
    ]
    trajectory = []
    for i, (label, magnitude, evidence) in enumerate(stage_defs):
        # confidence deliberately decays down the chain: each derived stage
        # stacks another assumption on top of the last, and evidence should
        # say so rather than implying uniform certainty throughout.
        conf = max(0.15, 0.85 - 0.13 * i)
        trajectory.append({
            "stage": label,
            "relative_level": _relative_level(magnitude),
            "evidence_status": evidence,
            "confidence": round(conf, 2),
            "is_observed_or_simulated": "simulated" if data_quality["data_status"] == DATA_STATUS_SIMULATED else "observed",
        })

    return {
        "risk_score": score,           # "Estimated risk score" — NOT a probability of poverty/migration/debt/distress
        "model_uncertainty": {"tree_std": round(tree_std, 3), "label": uncertainty_label},
        "status": status,
        "drivers": drivers,            # real SHAP output, labeled "indicative" by the caller/UI
        "data_quality": data_quality,
        "scenario_trajectory": trajectory,
        "validation_status": VALIDATION_STATUS,
    }


CASCADE_STAGES = [
    "Weather / water shock", "Crop stress & yield loss",
    "Income pressure & distress-sale risk", "Debt / reduced coping capacity",
    "Employment pressure (MGNREGA demand)", "Distress-migration pressure",
]

# ---------------------------------------------------------------------------
# Intervention engine — rule-based and deliberately NOT ML. Kept rule-based
# because that is what makes it auditable; each suggestion must be reviewed
# by a human officer, never auto-applied.
# ---------------------------------------------------------------------------

def suggest_actions(row: dict, result: dict) -> list:
    """Returns 'suggested actions for officer review' — never described as
    'best intervention' or a system decision."""
    d = {name: pct for name, pct, *_ in result["drivers"]}
    candidates = []

    def add(title, program, driver_key, urgency_days, benefit, feasibility, trigger):
        if trigger:
            candidates.append({
                "title": title,
                "program": program,
                "linked_driver": driver_key,
                "driver_share": d.get(driver_key, 0),
                "urgency_days": urgency_days,
                "expected_benefit_category": benefit,
                "feasibility": feasibility,
                "evidence_status": "rule_based_suggestion",
                "requires_officer_review": True,
            })

    add("Review agromet advisory dispatch (irrigation scheduling / drought-tolerant practice)",
        "mKisan / Kisan Sarathi", "Rainfall deficit", 5, "High", "Low effort",
        trigger=row["rainfall_anomaly_pct"] < -10 or row["crop_stress_index"] > 40)

    add("Review case for early PMFBY crop-loss assessment",
        "PMFBY", "Crop stress", 7, "High", "Low effort",
        trigger=row["crop_stress_index"] > 35)

    add("Verify crop-insurance enrollment & eligibility before window closes",
        "PMFBY", "Crop stress", 10, "Medium", "Low effort",
        trigger=row["crop_stress_index"] > 25)

    add("Alert mandi/market cell — review MSP procurement support or storage linkage",
        "e-NAM / State Marketing Board", "Market decline", 10, "Medium", "Medium effort",
        trigger=row["mandi_price_deviation_pct"] < -8)

    add("Review MGNREGA work-demand preparedness ahead of possible surge",
        "MGNREGA", "Employment pressure", 7, "High", "Low effort",
        trigger=row["mgnrega_demand_spike_pct"] > 15)

    add("Review water-stress relief options (tanker supply / groundwater recharge check)",
        "State PHE / CGWB", "Water stress", 14, "Medium", "Medium effort",
        trigger=row["water_stress_index"] > 45)

    add("Review case for cash-transfer / social-protection outreach given structural vulnerability",
        "State Social Welfare", "Structural vulnerability", 14, "Medium", "Medium effort",
        trigger=row["historical_vulnerability"] > 60 and result["risk_score"] > 45)

    add("Routine monitoring — no action currently indicated",
        "—", None, None, "—", "—",
        trigger=len(candidates) == 0)

    def sort_key(c):
        urgency = c["urgency_days"] if c["urgency_days"] is not None else 999
        return (-c["driver_share"], urgency)

    candidates.sort(key=sort_key)
    for i, c in enumerate(candidates[:4]):
        c["suggested_priority"] = (
            "High priority for review" if i == 0 and result["risk_score"] >= 55 else
            "Medium priority for review" if result["risk_score"] >= 35 else
            "Watch / low priority"
        )
    return candidates[:4]


# Backward-compatible aliases used by earlier scripts/tests during migration.
score_village = assess_risk
rank_interventions = suggest_actions
