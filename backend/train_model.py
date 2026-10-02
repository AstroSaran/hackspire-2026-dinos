"""
Kavach — Risk Model Training
=============================
Trains a RandomForestClassifier on the representative dataset (see
data/generate_dataset.py for the honesty note on data provenance).

Why RandomForest and not an LLM: per the project's own design rule
("Don't make an LLM the prediction engine"), the risk score comes from a
tabular model trained on engineered features. An LLM is used ONLY downstream,
to turn the model's numeric output + driver attribution into a plain-language
explanation (see app/narrate.py) — never to compute the score itself.
"""
import pandas as pd
import numpy as np
import pickle
import json
import os
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, precision_score, recall_score

HERE = os.path.dirname(__file__)
FEATURES = [
    "rainfall_anomaly_pct", "crop_stress_index", "mandi_price_deviation_pct",
    "mgnrega_demand_spike_pct", "water_stress_index", "historical_vulnerability",
]

df = pd.read_csv(os.path.join(HERE, "data", "training_data.csv"))
X = df[FEATURES]
y = df["distress_cascade_label"]

X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, random_state=42, stratify=y)

model = RandomForestClassifier(
    n_estimators=300, max_depth=6, min_samples_leaf=8, random_state=42, class_weight="balanced"
)
model.fit(X_train, y_train)

pred_proba = model.predict_proba(X_test)[:, 1]
pred = model.predict(X_test)
metrics = {
    "auc": round(float(roc_auc_score(y_test, pred_proba)), 3),
    "precision": round(float(precision_score(y_test, pred)), 3),
    "recall": round(float(recall_score(y_test, pred)), 3),
    "n_train": len(X_train),
    "n_test": len(X_test),
    "note": "Evaluated on held-out REPRESENTATIVE/SIMULATED data, not a real "
            "historical outcome dataset. These numbers describe how well the "
            "model recovers the synthetic causal structure we built in, not "
            "real-world predictive accuracy. Do not present as a validated "
            "field accuracy figure.",
}

os.makedirs(os.path.join(HERE, "model_artifacts"), exist_ok=True)
with open(os.path.join(HERE, "model_artifacts", "risk_model.pkl"), "wb") as f:
    pickle.dump(model, f)
with open(os.path.join(HERE, "model_artifacts", "metrics.json"), "w") as f:
    json.dump(metrics, f, indent=2)
with open(os.path.join(HERE, "model_artifacts", "feature_importance.json"), "w") as f:
    json.dump(dict(zip(FEATURES, [round(float(v), 4) for v in model.feature_importances_])), f, indent=2)

print(json.dumps(metrics, indent=2))
print("Feature importances:", dict(zip(FEATURES, model.feature_importances_.round(3))))
