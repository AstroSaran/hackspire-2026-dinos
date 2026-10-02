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


# --- Geography tests (Part 32) -----------------------------------------------

def test_west_bengal_accepted():
    from app import geography
    assert geography.is_supported_state("West Bengal") is True
    assert geography.is_supported_country("India") is True


def test_usa_rejected():
    from app import geography
    assert geography.is_supported_state("California") is False
    assert geography.is_supported_state("Texas") is False
    assert geography.is_supported_country("United States") is False


def test_villages_resolve_to_real_wb_hierarchy():
    from app import geography
    rec = geography.resolve_location("Bagula")
    assert rec["country"] == "India"
    assert rec["state"] == "West Bengal"
    assert rec["district"] == "Nadia"
    assert rec["block"] == "Krishnanagar Sadar"


def test_unknown_village_resolves_to_none():
    from app import geography
    assert geography.resolve_location("Springfield") is None


# --- Weather model / provider tests (Part 32) --------------------------------
# (fuller, properly-mocked weather coverage lives in test_weather_integration.py;
# these two just check the normalized model's field shape.)

def test_observation_has_timestamp_fields():
    from app.weather.models import WeatherObservation, now_ist
    obs = WeatherObservation(
        provider="imd", provider_name="India Meteorological Department", source="IMD current-weather API",
        country="India", state="West Bengal", district="Nadia", block="Krishnanagar Sadar", village="Bagula",
        latitude=23.4, longitude=88.5, location_resolution="station",
        observed_at="2026-09-26T10:00:00+05:30", fetched_at=now_ist(), status="LIVE",
    )
    assert obs.observed_at is not None
    assert obs.fetched_at is not None
    assert obs.timezone == "Asia/Kolkata"


def test_forecast_has_issue_time_and_differs_from_observation_shape():
    from app.weather.models import WeatherForecast
    fc = WeatherForecast(
        provider="imd", provider_name="India Meteorological Department", source="IMD forecast API",
        country="India", state="West Bengal", district="Nadia", block="Krishnanagar Sadar", village="Bagula",
        latitude=23.4, longitude=88.5, issued_at="2026-09-26T06:00:00+05:30", status="LIVE",
    )
    assert fc.issued_at is not None
    assert fc.data_type == "FORECAST"
    assert not hasattr(fc, "observed_at")  # forecast and observation are never mixed


def test_imd_endpoint_requires_station_id_never_guesses_one():
    from app.weather.providers import IMDWeatherProvider, ProviderUnavailable, Location
    provider = IMDWeatherProvider()
    loc = Location(country="India", state="West Bengal", district="Nadia", block="Krishnanagar Sadar",
                   village="Bagula", latitude=23.4, longitude=88.5, resolution="block_centroid")
    with pytest.raises(ProviderUnavailable):
        provider.get_current(loc)  # no imd_station_id configured -> must raise, never fabricate


def test_provider_failure_never_produces_fake_reading(monkeypatch):
    """Simulates both providers failing and asserts the service reports
    UNAVAILABLE rather than inventing a plausible-looking reading."""
    from app.weather import service as weather_service
    from app.weather.providers import Location, ProviderUnavailable

    class AlwaysFails:
        name = "fake"
        def get_current(self, loc):
            raise ProviderUnavailable("fake", "simulated outage for test")

    monkeypatch.setattr(weather_service, "_providers_in_order", lambda: [AlwaysFails()])
    loc = Location(country="India", state="West Bengal", district="Nadia", block="Krishnanagar Sadar",
                   village="TestVillage", latitude=23.4, longitude=88.5, resolution="block_centroid")
    obs = weather_service.get_current_weather(loc)
    assert obs.status == "UNAVAILABLE"
    assert obs.temperature_c is None and obs.precipitation_mm is None
    assert "UNAVAILABLE" in obs.note


def test_open_meteo_never_labeled_as_imd():
    from app.weather.providers import OpenMeteoWeatherProvider
    p = OpenMeteoWeatherProvider()
    # It may legitimately say "not IMD" as a disclosure; it must never claim
    # to BE India Meteorological Department.
    assert "india meteorological department" not in p.provider_name.lower()
    assert "not imd" in p.provider_name.lower()


# --- UI/data export tests: LIVE vs SIMULATED must be visibly distinguished ---

def test_village_detail_exposes_per_signal_data_coverage(sample_result):
    cov = sample_result["data_coverage"]
    assert cov["weather"] in ("LIVE", "STALE", "UNAVAILABLE")
    for k in ("crop", "market", "employment", "water", "vulnerability"):
        assert cov[k] == "SIMULATED"


def test_weather_block_never_silently_merged_into_model_score(sample_result):
    # the model's own signal list must still show the representative rainfall
    # feature as SIMULATED_REPRESENTATIVE regardless of live weather status —
    # the live weather layer is additive/transparent, not a silent override.
    rainfall_signal = next(s for s in sample_result["observed_signals"] if s["feature"] == "rainfall_anomaly_pct")
    assert rainfall_signal["data_status"] == "SIMULATED_REPRESENTATIVE"


# --- Validation tests: forbidden regressions (Part 32) -----------------------

def test_estimated_risk_score_never_becomes_probability_of_distress(sample_result):
    blob = json.dumps(sample_result).lower()
    # Legitimate honest disclaimers say "not a calibrated probability of X" —
    # only the unqualified, affirmative claim is forbidden.
    assert "is a probability of distress" not in blob
    assert "is a probability of poverty" not in blob
    assert "ai predicts" not in blob
    assert "ai-selected" not in blob
    assert "ai selected" not in blob


def test_no_us_geography_leaks_into_response(sample_result):
    blob = json.dumps(sample_result).lower()
    for term in ("california", "texas", "new york", "united states", "fahrenheit"):
        assert term not in blob
