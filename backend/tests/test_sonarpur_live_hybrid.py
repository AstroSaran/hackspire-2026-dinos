"""Live pilot contracts and regression checks."""
import pytest
from fastapi import HTTPException
from app import geography, live_pilots, main


def test_registered_pilot_resolves_real_coordinate():
    pilot = live_pilots.get_by_key("sonarpur")
    record = geography.resolve_location(pilot.village)
    assert record["latitude"] == 22.442948
    assert record["longitude"] == 88.428633
    assert record["district"] == "South 24 Parganas"
    assert record["block"] == "Rajpur Sonarpur"


def test_live_pilot_registry_is_addressable():
    assert live_pilots.all_pilots()
    for pilot in live_pilots.all_pilots():
        assert live_pilots.get_by_key(pilot.url_key) == pilot


def test_live_area_keeps_missing_features_explicit(monkeypatch):
    class Empty:
        def to_dict(self): return {"status": "UNAVAILABLE", "source": None}
    monkeypatch.setattr(main.weather_service, "get_current_weather", lambda loc: Empty())
    monkeypatch.setattr(main.weather_service, "get_forecast_weather", lambda loc: Empty())
    monkeypatch.setattr(main.weather_service, "get_warnings", lambda loc: {"status": "UNAVAILABLE"})
    monkeypatch.setattr(main.weather_historical, "get_pilot_latest_complete_month", lambda: None)
    response = main.live_area("sonarpur")
    assert response["model_assessment"]["status"] == "WITHHELD"
    assert "risk_score" not in response["model_assessment"]
    assert "missing_live_features" in response["model_assessment"]


def test_unknown_pilot_is_404():
    with pytest.raises(HTTPException) as exc:
        main.live_area("not-a-real-pilot")
    assert exc.value.status_code == 404
