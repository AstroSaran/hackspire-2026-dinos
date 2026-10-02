"""
Kavach — Methodological-Honesty Test Suite
=============================================
These tests exist to guard the correction made to this project: a system
that previously risked presenting simulated numbers as validated,
real-world predictions. Every test here asserts an absence (a forbidden
claim, word, or mislabeling) or a required presence (a provenance field,
a rule-based marker). If a future change reintroduces overclaiming
language, these tests should fail.
"""
import os
import sys
import json
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import main, engine, review as review_module

FORBIDDEN_VALIDATED_TERMS = [
    "is a validated probability", "is a validated prediction", "proven intervention",
    "this is a confirmed accuracy", "guaranteed outcome", "certain to occur",
]
# Legitimate honest disclaimers contain negated forms of similar words
# (e.g. "not field-validated predictions") -- those are required, not forbidden.


@pytest.fixture
def sample_village():
    df = main.load_snapshot()
    return df.iloc[0]


@pytest.fixture
def sample_result(sample_village):
    return main.build_village_result(sample_village)


# 1. Simulated data is never presented as live data --------------------------

def test_all_observed_signals_marked_simulated(sample_result):
    for sig in sample_result["observed_signals"]:
        assert sig["data_status"] == "SIMULATED_REPRESENTATIVE"
        assert sig["data_status"] != "LIVE"


def test_pilot_banner_present_everywhere_data_is_shown():
    listing = main.list_villages()
    assert "representative" in listing["pilot_mode_banner"].lower()
    assert "not field-validated" in listing["pilot_mode_banner"].lower()


def test_data_quality_never_claims_live_data(sample_result):
    label = sample_result["data_quality"]["overall_quality_label"].lower()
    assert "representative" in label or "simulat" in label
    # "live" may appear only inside the honest negation "not live data"
    if "live" in label:
        assert "not live data" in label


# 2. Model output is never labeled as validated probability ------------------

def test_risk_score_not_called_a_probability(sample_result):
    ma = sample_result["model_assessment"]
    assert "estimated_risk_score" in ma
    assert "risk_probability" not in ma
    note = ma["note"].lower()
    assert "not a calibrated probability" in note


def test_metrics_endpoint_flags_non_validation():
    metrics = main.model_metrics()
    assert metrics["metrics"]["is_field_validated"] is False
    assert "not" in metrics["important_note"].lower()


def test_validation_status_declares_not_field_validated():
    vs = engine.VALIDATION_STATUS
    assert vs["model_validation"] == "Not field validated"
    assert vs["real_outcome_labels"] == "Not currently available"


def test_no_forbidden_overclaiming_terms_anywhere(sample_result):
    blob = json.dumps(sample_result).lower()
    for term in FORBIDDEN_VALIDATED_TERMS:
        assert term not in blob


# 3. Scenario cascade values are never labeled as observed outcomes ----------

def test_scenario_trajectory_not_labeled_predicted_cascade(sample_result):
    traj = sample_result["scenario_trajectory"]
    assert "note" in traj
    assert "not a forecast validated against field outcomes" in traj["note"].lower()
    for stage in traj["stages"]:
        assert stage["evidence_status"] in (
            "OBSERVED_SIGNAL", "SCENARIO_ESTIMATE", "SCENARIO_INDICATOR",
        )
        # none of the scenario-derived stages may claim to be an observed outcome
        if stage["evidence_status"] != "OBSERVED_SIGNAL":
            assert stage["is_observed_or_simulated"] == "simulated"


def test_scenario_stages_carry_confidence_not_bare_probability(sample_result):
    for stage in sample_result["scenario_trajectory"]["stages"]:
        assert "confidence" in stage
        assert "relative_level" in stage
        assert stage["relative_level"] in ("LOW", "MODERATE", "MODERATE-HIGH", "HIGH")


# 4. Interventions remain rule-based -----------------------------------------

def test_suggested_actions_are_rule_based_and_require_review(sample_result):
    actions = sample_result["suggested_actions_for_officer_review"]
    assert len(actions) > 0
    for a in actions:
        assert a["evidence_status"] == "rule_based_suggestion"
        assert a["requires_officer_review"] is True
        assert "suggested_priority" in a
        # never phrased as a certainty
        assert "best intervention" not in a["title"].lower()


def test_intervention_engine_is_deterministic_not_ml(sample_village):
    feat = sample_village[engine.FEATURES].to_dict()
    result = engine.assess_risk(feat)
    a1 = engine.suggest_actions(feat, result)
    a2 = engine.suggest_actions(feat, result)
    assert a1 == a2  # same inputs -> same rule-based output, no stochasticity


# 5. Unknown/missing data reduces confidence ---------------------------------

def test_missing_feature_lowers_completeness_and_is_flagged():
    row = {
        "rainfall_anomaly_pct": -10.0, "crop_stress_index": 20.0,
        "mandi_price_deviation_pct": -5.0, "mgnrega_demand_spike_pct": 5.0,
        "water_stress_index": 15.0, "historical_vulnerability": None,
    }
    dq = engine._data_quality(row)
    assert dq["completeness"] < 1.0
    assert "historical_vulnerability" in dq["missing_features"]
    assert "incomplete inputs" in dq["overall_quality_label"]


def test_complete_row_has_full_completeness(sample_village):
    feat = sample_village[engine.FEATURES].to_dict()
    dq = engine._data_quality(feat)
    assert dq["completeness"] == 1.0
    assert dq["missing_features"] == []


# 6. Data provenance appears in API responses --------------------------------

def test_provenance_endpoint_covers_every_feature():
    prov = main.provenance()
    for f in engine.FEATURES:
        assert f in prov
        entry = prov[f]
        for key in ("source", "data_status", "geographic_level", "signal_type",
                    "freshness", "confidence", "live_equivalent"):
            assert key in entry


def test_village_detail_carries_provenance_per_signal(sample_result):
    for sig in sample_result["observed_signals"]:
        for key in ("source", "data_status", "geographic_level", "confidence", "live_equivalent"):
            assert key in sig
            assert sig[key] is not None


# 7. Dashboard/API correctly distinguishes observed/model/scenario information

def test_response_sections_are_kept_separate(sample_result):
    # OBSERVED SIGNAL
    assert "observed_signals" in sample_result
    # MODEL ASSESSMENT
    assert "model_assessment" in sample_result
    assert "model_uncertainty" in sample_result["model_assessment"]
    # SCENARIO
    assert "scenario_trajectory" in sample_result
    # these three must not collapse into one blob: distinct top-level keys
    assert sample_result["observed_signals"] is not sample_result["model_assessment"]
    assert sample_result["scenario_trajectory"] is not sample_result["model_assessment"]


def test_driver_explanation_labeled_indicative_not_causal(sample_result):
    dci = sample_result["driver_contribution_indicative"]
    assert "shap" in dci["method"].lower()
    assert "not proven real-world causation" in dci["note"].lower()


# Human review / outcome tracking --------------------------------------------

def test_officer_review_logs_and_leaves_outcome_null(tmp_path, monkeypatch):
    monkeypatch.setattr(review_module, "LOG_PATH", str(tmp_path / "log.jsonl"))
    predicted = {"risk_score": 71, "status": "risk"}
    rec = review_module.log_officer_review("Bagula", predicted, "approved", "sent advisory")
    assert rec["subsequent_outcome"] is None  # not available until a real pilot observes it
    assert rec["predicted_risk_score"] == 71
    logged = review_module.list_review_log("Bagula")
    assert len(logged) == 1
