from types import SimpleNamespace

from app import environmental_model, livelihood_model


def _forecast(status="LIVE", *, missing=None, invalid=None):
    days = []
    for day_index in range(1, 8):
        values = {
            "precipitation_sum_mm": 0.0,
            "precipitation_probability_max_pct": 0.0,
            "wind_speed_max_kmh": 10.0,
            "temperature_max_c": 25.0,
        }
        if missing:
            values[missing] = None
        if invalid:
            values[invalid[0]] = invalid[1]
        days.append(SimpleNamespace(date=f"2026-10-{day_index:02d}", **values))
    return SimpleNamespace(status=status, provider_name="Unit-test fixture",
                           fetched_at="2026-10-02T12:00:00+05:30", days=days)


def test_complete_live_forecast_may_report_no_configured_trigger():
    result = environmental_model.assess(_forecast(), None, None, "2026-10-02T12:00:00+05:30")
    assert result["status"] == "NO_CONFIGURED_FORECAST_TRIGGER"
    assert result["assessment_quality"]["status"] == "COMPLETE"
    assert result["assessment_quality"]["complete_days"] == 7
    assert "probability" not in result
    assert "score" not in result


def test_missing_forecast_fields_force_abstention_not_a_no_trigger():
    result = environmental_model.assess(
        _forecast(missing="temperature_max_c"), None, None, "2026-10-02T12:00:00+05:30")
    assert result["status"] == "INCOMPLETE_EVIDENCE"
    assert result["assessment_quality"]["decision"] == "ABSTAIN"
    assert result["assessment_quality"]["complete_days"] == 0


def test_implausible_values_are_excluded_and_reported():
    result = environmental_model.assess(
        _forecast(invalid=("wind_speed_max_kmh", float("nan"))), None, None,
        "2026-10-02T12:00:00+05:30")
    assert result["status"] == "INCOMPLETE_EVIDENCE"
    assert result["assessment_quality"]["invalid_values"] == 7
    assert result["forecast"]["watch_count"] == 0


def test_stale_forecast_never_becomes_a_no_trigger():
    result = environmental_model.assess(
        _forecast(status="STALE"), None, None, "2026-10-02T12:00:00+05:30")
    assert result["status"] == "INCOMPLETE_EVIDENCE"
    assert result["assessment_quality"]["stale_input"] is True


def test_unphysical_context_values_are_withheld():
    result = environmental_model.assess(
        _forecast(), {"anomaly_pct": float("inf"), "observed_mm": 20, "expected_mm": 10},
        {"status": "LIVE", "value": 1.8}, "2026-10-02T12:00:00+05:30")
    assert result["rainfall_context"]["status"] == "UNAVAILABLE"
    assert result["topsoil_context"]["status"] == "UNAVAILABLE"


def test_livelihood_model_readiness_includes_production_gates_but_no_prediction():
    result = livelihood_model.readiness("UNAVAILABLE", "NEEDS_CONFIGURATION")
    assert result["status"] == "WITHHELD"
    assert result["release_status"] == "NOT_FOR_PRODUCTION_DECISIONS"
    assert len(result["production_gates"]) >= 5
    assert all(gate["status"] != "PASSED" for gate in result["production_gates"])
    assert "prediction" not in result
    assert "probability" not in result
