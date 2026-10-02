"""
Kavach — Human Review & Outcome Tracking
===========================================
Implements the decision layer required by the product design:

    SYSTEM ASSESSMENT -> OFFICER REVIEW -> ACTION -> OUTCOME

and the future-validation record schema: for each village and time period we
store what the model saw and predicted, what was actually observed, what
action was taken, and (eventually) what happened — because THIS is the
dataset that would need to exist before any real accuracy claim is possible.

This is a minimal, file-backed append-only log (JSON Lines), sufficient for
a hackathon demo. A real deployment would use a proper database with access
control, since officer identity and case outcomes are sensitive.
"""
import os
import json
import time
import uuid

HERE = os.path.dirname(os.path.dirname(__file__))
LOG_PATH = os.path.join(HERE, "data", "review_outcome_log.jsonl")

# Fields required by the future-validation design (see PROJECT spec sec. 7)
VALIDATION_RECORD_SCHEMA = [
    "record_id", "village", "logged_at",
    "model_warning_date", "predicted_risk_score", "predicted_status",
    "observed_weather_shock", "observed_crop_stress", "observed_employment_demand",
    "observed_market_movement",
    "officer_reviewed", "officer_decision", "action_taken",
    "subsequent_outcome",  # left null until a real pilot can observe/record it
]


def log_officer_review(village: str, predicted: dict, officer_decision: str, action_taken: str = None) -> dict:
    """Called when an officer reviews a system assessment. This is the
    SYSTEM ASSESSMENT -> OFFICER REVIEW -> ACTION step. `subsequent_outcome`
    is intentionally left null: it can only be filled in by a real pilot
    that later observes what actually happened."""
    record = {
        "record_id": str(uuid.uuid4()),
        "village": village,
        "logged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model_warning_date": time.strftime("%Y-%m-%d", time.gmtime()),
        "predicted_risk_score": predicted.get("risk_score"),
        "predicted_status": predicted.get("status"),
        "observed_weather_shock": None,     # to be filled by a real pilot's field data
        "observed_crop_stress": None,
        "observed_employment_demand": None,
        "observed_market_movement": None,
        "officer_reviewed": True,
        "officer_decision": officer_decision,   # e.g. "approved", "deferred", "escalated"
        "action_taken": action_taken,
        "subsequent_outcome": None,          # NOT AVAILABLE — see validation_status
    }
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")
    return record


def list_review_log(village: str = None) -> list:
    if not os.path.exists(LOG_PATH):
        return []
    out = []
    with open(LOG_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if village is None or rec["village"].lower() == village.lower():
                out.append(rec)
    return out
