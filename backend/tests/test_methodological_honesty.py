"""Methodological guardrails for Kavach's live-only API."""
import pytest
from fastapi import HTTPException
from app import main


def test_validation_status_withholds_scoring():
    payload = main.validation_status()
    assert payload["status"] == "WITHHELD"
    assert payload["is_field_validated"] is False
    assert "risk_score" not in payload


def test_live_area_never_emits_a_score(monkeypatch):
    class EmptyObservation:
        def to_dict(self): return {"status": "UNAVAILABLE", "source": None}
    monkeypatch.setattr(main.weather_service, "get_current_weather", lambda loc: EmptyObservation())
    monkeypatch.setattr(main.weather_service, "get_forecast_weather", lambda loc: EmptyObservation())
    monkeypatch.setattr(main.weather_service, "get_warnings", lambda loc: {"status": "UNAVAILABLE"})
    monkeypatch.setattr(main.weather_historical, "get_pilot_latest_complete_month", lambda: None)
    result = main.live_area("sonarpur")
    assert "risk_score" not in result
    assert result["model_assessment"]["status"] == "WITHHELD"


def test_risk_assessment_route_is_disabled():
    with pytest.raises(HTTPException) as exc:
        main.village_detail("Sonarpur")
    assert exc.value.status_code == 410
    assert "withheld" in exc.value.detail.lower()


def test_health_discloses_live_only_policy():
    payload = main.health()
    assert payload["synthetic_risk_scoring"] is False
    assert "real providers only" in payload["provider_policy"]
