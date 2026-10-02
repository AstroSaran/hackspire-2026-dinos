"""
Kavach — Representative Village Dataset Generator
====================================================
IMPORTANT / HONESTY NOTE (see README.md "Data & Limitations"):
No public, household-level, ground-truth "did this village suffer a livelihood
distress cascade" dataset exists in India's open-data ecosystem. Meghdoot,
e-NAM, MGNREGA MIS and PMFBY expose real *signals* (weather, prices, work
demand, insurance) but not a labeled outcome variable suitable for supervised
training.

This script therefore generates a REPRESENTATIVE / SIMULATED dataset for
~30 villages in a stand-in "Nadia-like" district of West Bengal. The value
RANGES for each feature (rainfall anomaly, NDVI/crop-stress proxy, mandi
price deviation, MGNREGA demand spike, water stress, historical vulnerability)
are calibrated to match the real, published ranges cited in our research
review (IMD/Meghdoot agromet bulletins, e-NAM price bulletins, MGNREGA MIS
public dashboards, and the West Bengal rice-farmer livelihood-vulnerability
literature). The synthetic OUTCOME LABEL is generated from the causal
cascade structure (rainfall -> crop stress -> income loss -> distress
borrowing -> employment pressure -> migration risk) described in FEWS NET's
livelihoods-based methodology, plus noise — it is NOT a real observed outcome.

When deployed for real, `feature engineering` in app/features.py is designed
so each of these six columns can be replaced by a live pipeline call
(Open-Meteo/IMD, Sentinel NDVI via Earth Engine, AGMARKNET/e-NAM API,
NREGA MIS public API, CGWB groundwater, and a maintained vulnerability
register) without touching the model or API layer.
"""
import numpy as np
import pandas as pd
import json
import os

RNG = np.random.default_rng(42)
N_VILLAGES = 30

VILLAGE_NAMES = [
    "Bagula", "Chapra", "Krishnaganj", "Hanskhali", "Ranaghat", "Santipur",
    "Nabadwip", "Kaliganj", "Nakashipara", "Chakdaha", "Haringhata", "Tehatta",
    "Karimpur", "Palashipara", "Debagram", "Thanarpara", "Betai", "Mayapur",
    "Gangnapur", "Dhubulia", "Fulia", "Birnagar", "Taherpur", "Shantipur Rural",
    "Char Meghna", "Char Brahmanagar", "Bethuadahari", "Ramnagar", "Majhdia", "Duttapulia",
]

ZONE = {
    # Zone label affects the *shape* of shocks (flood vs rainfall-deficit vs market/migration)
    "flood": {"names": ["Char Meghna", "Char Brahmanagar", "Bethuadahari", "Ramnagar"]},
    "rainfall_crop": {"names": ["Bagula", "Chapra", "Krishnaganj", "Hanskhali", "Karimpur",
                                 "Palashipara", "Debagram", "Thanarpara", "Betai", "Tehatta"]},
    "market_migration": {"names": ["Ranaghat", "Santipur", "Nabadwip", "Kaliganj", "Nakashipara",
                                    "Chakdaha", "Haringhata", "Mayapur", "Gangnapur", "Dhubulia",
                                    "Fulia", "Birnagar", "Taherpur", "Shantipur Rural", "Majhdia", "Duttapulia"]},
}


def zone_of(name):
    for z, d in ZONE.items():
        if name in d["names"]:
            return z
    return "rainfall_crop"


def sample_village(name, week_offset=0):
    zone = zone_of(name)

    # --- Base ranges calibrated to published statistics ---
    # Rainfall anomaly (%): Meghdoot agromet bulletins for Gangetic WB typically
    # report block-level deviation from normal in the -60% to +40% range during
    # a stressed monsoon window.
    if zone == "rainfall_crop":
        rainfall_anom = RNG.normal(-22, 14)
    elif zone == "flood":
        rainfall_anom = RNG.normal(+18, 20)  # excess, not deficit
    else:
        rainfall_anom = RNG.normal(-10, 12)

    # Crop stress proxy (0-100, higher = worse), loosely tracks |rainfall anomaly|
    # and adds noise for pest/soil factors documented in the WB rice-vulnerability study.
    crop_stress = np.clip(0.9 * abs(rainfall_anom) + RNG.normal(5, 8), 0, 100)

    # Mandi price deviation (%) from 3-year seasonal average, e-NAM style.
    # Distress-sale conditions (post-harvest glut after a shock) push this negative.
    price_dev = RNG.normal(-6, 12) - 0.15 * crop_stress

    # MGNREGA demand spike (% change in households demanding work vs district median)
    demand_spike = RNG.normal(8, 15) + 0.25 * crop_stress + (10 if zone == "market_migration" else 0)

    # Water stress index (0-100)
    water_stress = np.clip(0.6 * max(0, -rainfall_anom) + RNG.normal(10, 10), 0, 100)
    if zone == "flood":
        water_stress = np.clip(water_stress + 20, 0, 100)  # flooding also degrades usable water

    # Historical vulnerability (0-100): land fragmentation, irrigation coverage,
    # debt exposure, land holding size — proxied as a static per-village trait.
    hist_vuln = np.clip(RNG.normal(45, 18), 5, 95)

    return {
        "village": name,
        "zone": zone,
        "rainfall_anomaly_pct": round(float(rainfall_anom), 1),
        "crop_stress_index": round(float(crop_stress), 1),
        "mandi_price_deviation_pct": round(float(price_dev), 1),
        "mgnrega_demand_spike_pct": round(float(demand_spike), 1),
        "water_stress_index": round(float(water_stress), 1),
        "historical_vulnerability": round(float(hist_vuln), 1),
    }


def build_dataset(n_samples_per_village=40):
    """Build a training set: many simulated observation-weeks per village so the
    model learns the *relationship* between features and outcome, not village identity."""
    rows = []
    for v in VILLAGE_NAMES:
        for _ in range(n_samples_per_village):
            r = sample_village(v)
            # Causal-ish synthetic label using the cascade weights described in
            # the research doc (rainfall 31%, crop 25%, market 18%, employment 15%, water 11%)
            z = (
                0.031 * max(0, -r["rainfall_anomaly_pct"]) * 3.0
                + 0.25 * r["crop_stress_index"]
                + 0.18 * max(0, -r["mandi_price_deviation_pct"]) * 2.0
                + 0.15 * max(0, r["mgnrega_demand_spike_pct"])
                + 0.11 * r["water_stress_index"]
                + 0.20 * r["historical_vulnerability"]
                - 35  # intercept so ~ half are low risk
            )
            prob = 1 / (1 + np.exp(-z / 9))
            label = int(RNG.random() < prob)
            r["distress_cascade_label"] = label
            rows.append(r)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    os.makedirs(os.path.dirname(__file__), exist_ok=True)
    df = build_dataset()
    df.to_csv(os.path.join(os.path.dirname(__file__), "training_data.csv"), index=False)

    # Also emit one "current snapshot" row per village (latest week) for the live dashboard
    snapshot = pd.DataFrame([sample_village(v) for v in VILLAGE_NAMES])
    snapshot.to_csv(os.path.join(os.path.dirname(__file__), "current_snapshot.csv"), index=False)
    print(f"Training rows: {len(df)}  | Positive rate: {df.distress_cascade_label.mean():.2f}")
    print(f"Snapshot villages: {len(snapshot)}")
