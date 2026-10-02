"""
Exports data for the static dashboard artifact using the REFRAMED pipeline:
estimated risk score + model uncertainty, real SHAP drivers, data quality,
scenario trajectory (not "predicted cascade"), and suggested actions FOR
OFFICER REVIEW (not "best intervention"). Also exports the validation-status
block and per-feature provenance so the UI can visibly distinguish
"representative simulation" from "observed/live data" (there is currently no
live data in this build — see README).
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))
from app import main, engine

OUT = os.path.join(os.path.dirname(__file__), "..", "frontend_data")
os.makedirs(OUT, exist_ok=True)


def slim_actions(actions):
    return [[a["title"], a["suggested_priority"], a["program"], a["urgency_days"],
             a["expected_benefit_category"], a["feasibility"]] for a in actions[:3]]


def slim_trajectory(stages):
    return [[s["stage"], s["relative_level"], s["evidence_status"], s["confidence"]] for s in stages]


def slim_signals(row):
    return [[engine.FRIENDLY[f], round(float(row[f]), 1)] for f in engine.FEATURES]


def slim_weather(weather_block):
    if not weather_block or "observation" not in weather_block:
        return {"status": (weather_block or {}).get("status", "UNAVAILABLE"),
                "note": (weather_block or {}).get("note")}
    obs = weather_block["observation"]
    fc = weather_block.get("forecast", {})
    warn = weather_block.get("warnings", {})
    pipeline = weather_block.get("rainfall_anomaly_pipeline") or {}
    return {
        "status": obs["status"], "provider": obs.get("provider"), "provider_name": obs.get("provider_name"),
        "source": obs.get("source"),
        "temperature_c": obs.get("temperature_c"), "precipitation_mm": obs.get("precipitation_mm"),
        "humidity_pct": obs.get("humidity_pct"), "wind_speed_kmh": obs.get("wind_speed_kmh"),
        "wind_direction_deg": obs.get("wind_direction_deg"),
        "observed_at": obs.get("observed_at"), "fetched_at": obs.get("fetched_at"),
        "cache_status": obs.get("cache_status"), "freshness": obs.get("freshness"), "note": obs.get("note"),
        "forecast_days": [[d["date"], d.get("precipitation_sum_mm"), d.get("temperature_max_c"), d.get("temperature_min_c")]
                          for d in fc.get("days", [])][:7],
        "forecast_status": fc.get("status"),
        "warnings_status": warn.get("status"), "warnings": warn.get("warnings", []), "warnings_note": warn.get("note"),
        "rainfall_anomaly_pct": pipeline.get("rainfall_anomaly_pct"),
        "rainfall_model_input_used": pipeline.get("model_input_used"),
        "rainfall_baseline_period": pipeline.get("baseline_period"),
    }


# 1. All villages, fully assessed by the real (reframed) pipeline, weather included
full = [main.build_village_result(row) for _, row in main.load_snapshot().iterrows()]
with open(os.path.join(OUT, "villages_scored.json"), "w") as f:
    json.dump(full, f, indent=2, default=str)

v_export = []
for v in full:
    v_export.append([
        v["village"], v["model_assessment"]["estimated_risk_score"],
        v["model_assessment"]["model_uncertainty"]["label"],
        [[s["feature"], round(float(s["value"]), 1)] for s in v["observed_signals"]],
        [[d[0], d[1], d[2]] for d in v["driver_contribution_indicative"]["drivers"]],
        slim_trajectory(v["scenario_trajectory"]["stages"]),
        slim_actions(v["suggested_actions_for_officer_review"]),
        v["data_coverage"],
        slim_weather(v["weather"]),
        v["zone"],
    ])

# 2. Provenance, once (same schema applies to every village's signals)
provenance_export = [
    [engine.FRIENDLY[f], engine.PROVENANCE[f]["signal_type"], engine.PROVENANCE[f]["data_status"],
     engine.PROVENANCE[f]["confidence"], engine.PROVENANCE[f]["live_equivalent"]]
    for f in engine.FEATURES
]

# 3. 8-week SCENARIO trajectory simulation (real scoring engine, staged inputs)
#    Renamed per spec: this is a scenario, not a historical prediction.
stages = [
    {"week": 0, "note": "Baseline — normal monsoon pattern (scenario input).",
     "overrides": {"rainfall_anomaly_pct": -3, "crop_stress_index": 5,
                   "mandi_price_deviation_pct": 1, "mgnrega_demand_spike_pct": 2,
                   "water_stress_index": 8}},
    {"week": 2, "note": "Rainfall anomaly first appears in the scenario; crop stress not yet elevated.",
     "overrides": {"rainfall_anomaly_pct": -16, "crop_stress_index": 14,
                   "mandi_price_deviation_pct": -2, "mgnrega_demand_spike_pct": 4,
                   "water_stress_index": 18}},
    {"week": 4, "note": "Scenario shows crop stress rising; mandi arrivals softening.",
     "overrides": {"rainfall_anomaly_pct": -28, "crop_stress_index": 38,
                   "mandi_price_deviation_pct": -11, "mgnrega_demand_spike_pct": 9,
                   "water_stress_index": 32}},
    {"week": 6, "note": "Scenario shows MGNREGA demand rising alongside income-pressure indicators.",
     "overrides": {"rainfall_anomaly_pct": -34, "crop_stress_index": 55,
                   "mandi_price_deviation_pct": -19, "mgnrega_demand_spike_pct": 22,
                   "water_stress_index": 41}},
    {"week": 8, "note": "Scenario shows distress-migration pressure indicators elevated.",
     "overrides": {"rainfall_anomaly_pct": -37, "crop_stress_index": 63,
                   "mandi_price_deviation_pct": -24, "mgnrega_demand_spike_pct": 31,
                   "water_stress_index": 47}},
]

df = main.load_snapshot()
base = df[df["village"] == "Bagula"].iloc[0]

sim_export = []
first_watch_week = None
first_critical_week = None
for s in stages:
    row = base.copy()
    for k, v in s["overrides"].items():
        row[k] = v
    feat = row[engine.FEATURES].to_dict()
    result = engine.assess_risk(feat)
    actions = engine.suggest_actions(feat, result)
    if first_watch_week is None and result["status"] in ("watch", "risk", "critical"):
        first_watch_week = s["week"]
    if first_critical_week is None and result["status"] == "critical":
        first_critical_week = s["week"]
    sim_export.append([
        s["week"], s["note"], result["risk_score"], result["status"],
        result["model_uncertainty"]["label"],
        [[d[0], d[1], d[2]] for d in result["drivers"]],
        slim_trajectory(result["scenario_trajectory"]),
        slim_actions(actions),
    ])

lead_time_weeks = (
    (first_critical_week - first_watch_week)
    if (first_watch_week is not None and first_critical_week is not None)
    else None
)

payload = {
    "v": v_export,
    "provenance": provenance_export,
    "sim": sim_export,
    "lead": lead_time_weeks,
    "validation": engine.VALIDATION_STATUS,
    "locations": main.locations(),
    "data_health": main.data_health(),
    "pilot_banner": main.PILOT_BANNER,
}
with open(os.path.join(os.path.dirname(__file__), "..", "frontend_data.js"), "w") as f:
    f.write("const KD = " + json.dumps(payload, separators=(",", ":")) + ";")

print("Exported", len(v_export), "villages.")
print("Scenario lead time (weeks of warning before 'critical' status, in the illustrative scenario):", lead_time_weeks)
for row in sim_export:
    print(f"  week {row[0]:>2}  score={row[2]:>3}  status={row[3]:<8}  {row[1]}")

import os as _os
print("frontend_data.js size KB:", round(_os.path.getsize(os.path.join(os.path.dirname(__file__), "..", "frontend_data.js")) / 1024, 1))
