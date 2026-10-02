"""
Kavach — Weather Subsystem Tests (Part 19)
==============================================
All tests here mock `requests.get` so they pass deterministically with NO
internet access, regardless of the environment they run in — this is a
correction from the previous suite, which happened to pass only because
this sandbox's network is restricted (an accident of environment, not a
real guarantee). Real-network verification is a separate, explicitly
marked integration test (see bottom), skipped by default.
"""
import os
import sys
import json
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.weather.providers import (
    IMDWeatherProvider, OpenMeteoWeatherProvider, DemoWeatherProvider,
    ProviderUnavailable, Location,
)
from app.weather import service as weather_service
from app.weather.models import LIVE, STALE, SIMULATED_DEMO, UNAVAILABLE, OBSERVATION, FORECAST


def _loc(village="Bagula"):
    return Location(country="India", state="West Bengal", district="Nadia",
                    block="Krishnanagar Sadar", village=village,
                    latitude=23.4058, longitude=88.5017, resolution="block_centroid")


def _mock_response(json_body, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body
    return resp


# --- Open-Meteo response parsing (mocked, no network) ------------------------

def test_open_meteo_current_parses_real_shaped_response():
    body = {"current": {"time": "2026-09-26T14:00", "temperature_2m": 31.2,
                         "relative_humidity_2m": 78, "precipitation": 12.4, "rain": 12.4,
                         "weather_code": 61, "wind_speed_10m": 14.0, "wind_direction_10m": 210}}
    with patch("requests.get", return_value=_mock_response(body)):
        obs = OpenMeteoWeatherProvider().get_current(_loc())
    assert obs.status == LIVE
    assert obs.temperature_c == 31.2
    assert obs.precipitation_mm == 12.4
    assert obs.wind_direction_deg == 210
    assert obs.weather_code == 61
    assert obs.data_type == OBSERVATION
    assert "not IMD" in obs.provider_name.lower() or "not imd" in obs.provider_name.lower()


def test_open_meteo_forecast_parses_daily_arrays():
    body = {"daily": {"time": ["2026-09-27", "2026-09-28"],
                       "precipitation_sum": [5.0, 12.0],
                       "temperature_2m_max": [33.0, 32.0], "temperature_2m_min": [26.0, 25.5]}}
    with patch("requests.get", return_value=_mock_response(body)):
        fc = OpenMeteoWeatherProvider().get_forecast(_loc())
    assert fc.status == LIVE
    assert fc.data_type == FORECAST
    assert len(fc.days) == 2
    assert fc.days[0].precipitation_sum_mm == 5.0
    # forecast and observation must never be the same shape
    assert not hasattr(fc, "temperature_c")


def test_open_meteo_error_flag_raises_not_fabricates():
    body = {"error": True, "reason": "Latitude must be in range of -90 to 90°"}
    with patch("requests.get", return_value=_mock_response(body)):
        with pytest.raises(ProviderUnavailable):
            OpenMeteoWeatherProvider().get_current(_loc())


def test_open_meteo_http_failure_raises_not_fabricates():
    with patch("requests.get", return_value=_mock_response({}, status_code=500)):
        with pytest.raises(ProviderUnavailable):
            OpenMeteoWeatherProvider().get_current(_loc())


def test_open_meteo_network_exception_raises_not_fabricates():
    import requests
    with patch("requests.get", side_effect=requests.exceptions.ConnectionError("no route")):
        with pytest.raises(ProviderUnavailable):
            OpenMeteoWeatherProvider().get_current(_loc())


def test_open_meteo_has_no_warnings_product():
    p = OpenMeteoWeatherProvider()
    assert p.supports_warnings is False
    assert p.get_warnings(_loc()) == []


# --- IMD: 401 without whitelisting, no station id -> never fabricates -------

def test_imd_401_raises_provider_unavailable():
    with patch("requests.get", return_value=_mock_response({}, status_code=401)):
        loc = _loc()
        loc.imd_station_id = "42809"
        with pytest.raises(ProviderUnavailable, match="whitelist"):
            IMDWeatherProvider().get_current(loc)


def test_imd_without_station_id_raises_without_network_call():
    with patch("requests.get") as mock_get:
        with pytest.raises(ProviderUnavailable):
            IMDWeatherProvider().get_current(_loc())  # no imd_station_id set
        mock_get.assert_not_called()  # must not even attempt the call


def test_imd_success_shape():
    body = {"Date_Time": "2026-09-26T14:00", "Temperature": "31.2", "Humidity": "78",
            "Rainfall": "12.4", "Wind_Speed": "14"}
    with patch("requests.get", return_value=_mock_response(body)):
        loc = _loc()
        loc.imd_station_id = "42809"
        obs = IMDWeatherProvider().get_current(loc)
    assert obs.status == LIVE
    assert obs.provider == "imd"
    assert obs.temperature_c == 31.2


# --- Demo provider: always SIMULATED_DEMO, deterministic, never network ----

def test_demo_provider_never_touches_network():
    with patch("requests.get") as mock_get:
        obs = DemoWeatherProvider().get_current(_loc())
        mock_get.assert_not_called()
    assert obs.status == SIMULATED_DEMO
    assert obs.status != LIVE


def test_demo_provider_deterministic_not_random():
    obs1 = DemoWeatherProvider().get_current(_loc("Bagula"))
    obs2 = DemoWeatherProvider().get_current(_loc("Bagula"))
    assert obs1.temperature_c == obs2.temperature_c  # same village -> same values every time


# --- Provider fallback chain (mocked) ---------------------------------------

def test_imd_fallback_to_open_meteo(monkeypatch):
    monkeypatch.setattr(weather_service, "IMD_ENABLED", True)
    monkeypatch.setattr(weather_service, "ENABLE_FALLBACK", True)
    monkeypatch.setattr(weather_service, "DEMO_FALLBACK", False)
    weather_service._cache.store.clear()

    body = {"current": {"time": "2026-09-26T14:00", "temperature_2m": 30.0,
                         "relative_humidity_2m": 80, "precipitation": 2.0, "rain": 2.0,
                         "wind_speed_10m": 10.0, "wind_direction_10m": 180}}

    def fake_get(url, params=None, timeout=None):
        if "mausam.imd.gov.in" in url:
            return _mock_response({}, status_code=401)  # IMD not whitelisted
        return _mock_response(body)  # Open-Meteo succeeds

    with patch("requests.get", side_effect=fake_get):
        obs = weather_service.get_current_weather(_loc("FallbackTestVillage"))
    assert obs.status == LIVE
    assert obs.provider == "open_meteo"


def test_no_fake_fallback_when_all_providers_fail(monkeypatch):
    monkeypatch.setattr(weather_service, "IMD_ENABLED", True)
    monkeypatch.setattr(weather_service, "ENABLE_FALLBACK", True)
    monkeypatch.setattr(weather_service, "DEMO_FALLBACK", False)
    weather_service._cache.store.clear()
    with patch("requests.get", return_value=_mock_response({}, status_code=500)):
        obs = weather_service.get_current_weather(_loc("AllFailVillage"))
    assert obs.status == UNAVAILABLE
    assert obs.temperature_c is None
    assert "UNAVAILABLE" in obs.note


def test_demo_fallback_is_never_used_in_live_only_beta(monkeypatch):
    monkeypatch.setattr(weather_service, "IMD_ENABLED", True)
    monkeypatch.setattr(weather_service, "ENABLE_FALLBACK", True)
    monkeypatch.setattr(weather_service, "DEMO_FALLBACK", True)
    weather_service._cache.store.clear()
    with patch("requests.get", return_value=_mock_response({}, status_code=500)):
        obs = weather_service.get_current_weather(_loc("DemoFallbackVillage"))
    assert obs.status == UNAVAILABLE
    assert obs.temperature_c is None


# --- Caching ------------------------------------------------------------

def test_cache_hit_does_not_call_network_again(monkeypatch):
    monkeypatch.setattr(weather_service, "IMD_ENABLED", False)
    monkeypatch.setattr(weather_service, "DEMO_FALLBACK", False)
    weather_service._cache.store.clear()
    body = {"current": {"time": "2026-09-26T14:00", "temperature_2m": 29.0,
                         "relative_humidity_2m": 75, "precipitation": 0.0, "rain": 0.0,
                         "wind_speed_10m": 8.0, "wind_direction_10m": 90}}
    with patch("requests.get", return_value=_mock_response(body)) as mock_get:
        weather_service.get_current_weather(_loc("CacheTestVillage"))
        weather_service.get_current_weather(_loc("CacheTestVillage"))
    assert mock_get.call_count == 1  # second call served from cache, not the network


def test_cache_response_carries_cache_status(monkeypatch):
    monkeypatch.setattr(weather_service, "IMD_ENABLED", False)
    monkeypatch.setattr(weather_service, "DEMO_FALLBACK", False)
    weather_service._cache.store.clear()
    body = {"current": {"time": "2026-09-26T14:00", "temperature_2m": 29.0,
                         "relative_humidity_2m": 75, "precipitation": 0.0, "rain": 0.0,
                         "wind_speed_10m": 8.0, "wind_direction_10m": 90}}
    with patch("requests.get", return_value=_mock_response(body)):
        first = weather_service.get_current_weather(_loc("CacheStatusVillage"))
        second = weather_service.get_current_weather(_loc("CacheStatusVillage"))
    assert first.cache_status == "miss"
    assert second.cache_status == "hit"
    assert second.fresh_until is not None


# --- IST timestamps ----------------------------------------------------

def test_timestamps_are_ist_offset():
    from app.weather.models import now_ist
    ts = now_ist()
    assert ts.endswith("+05:30")


def test_observation_timezone_field_is_kolkata():
    obs = DemoWeatherProvider().get_current(_loc())
    assert obs.timezone == "Asia/Kolkata"


# --- Warnings: never fabricated ------------------------------------------

def test_warnings_unavailable_when_no_source_checkable(monkeypatch):
    monkeypatch.setattr(weather_service, "IMD_ENABLED", False)  # only open_meteo/demo in chain
    monkeypatch.setattr(weather_service, "DEMO_FALLBACK", False)
    weather_service._cache.store.clear()
    result = weather_service.get_warnings(_loc("WarningsTestVillage"))
    assert result["status"] == UNAVAILABLE
    assert result["warnings"] == []
    assert "note" in result  # must explain why, never silently empty


def test_warnings_never_say_no_active_when_unchecked():
    # The service-level contract: UNAVAILABLE status must accompany an empty
    # list; callers must render "WARNING STATUS UNAVAILABLE", not "no active
    # warning", whenever status != LIVE.
    from app.weather.models import unavailable_warning
    w = unavailable_warning("Nadia", "no source reachable")
    assert w.status == UNAVAILABLE
    assert w.headline is None  # never an invented "no warnings" headline


# --- Rainfall anomaly pipeline + historical baseline (Part 9) ---------------

def test_rainfall_anomaly_unavailable_without_baseline(tmp_path, monkeypatch):
    from app import weather_features
    from app.weather import historical
    monkeypatch.setattr(historical, "BASELINE_FILE", str(tmp_path / "nonexistent.json"))
    obs = DemoWeatherProvider().get_current(_loc())  # status=SIMULATED_DEMO, not LIVE
    result = weather_features.compute_rainfall_anomaly(obs, "Nadia", "Krishnanagar Sadar")
    assert result["rainfall_anomaly_pct"] is None
    assert result["model_input_used"] is False


def test_rainfall_anomaly_computed_when_baseline_and_live_obs_exist(tmp_path, monkeypatch):
    from app import weather_features
    from app.weather import historical
    baseline_file = tmp_path / "baseline.json"
    baseline_file.write_text(json.dumps({
        "Nadia:Krishnanagar Sadar": {"mean_mm": 6.5, "period": "1991-2020",
                                      "source": "Open-Meteo ERA5 archive (test fixture)"}
    }))
    monkeypatch.setattr(historical, "BASELINE_FILE", str(baseline_file))
    body = {"current": {"time": "2026-09-26T14:00", "temperature_2m": 30.0,
                         "relative_humidity_2m": 80, "precipitation": 13.0, "rain": 13.0,
                         "wind_speed_10m": 10.0, "wind_direction_10m": 180}}
    with patch("requests.get", return_value=_mock_response(body)):
        obs = OpenMeteoWeatherProvider().get_current(_loc())
    result = weather_features.compute_rainfall_anomaly(obs, "Nadia", "Krishnanagar Sadar")
    assert result["model_input_used"] is True
    assert result["rainfall_anomaly_pct"] == round(((13.0 - 6.5) / 6.5) * 100, 1)
    assert result["baseline_period"] == "1991-2020"


def test_historical_baseline_never_fabricated_without_key():
    from app.weather import historical
    with pytest.raises(historical.BaselineUnavailable):
        historical.fetch_ogd_district_normal("Nadia", api_key=None)


def test_data_health_providers_not_double_nested():
    from app import main
    health = main.data_health()
    assert "imd" in health["providers"]
    assert "current" in health["providers"]["imd"]
    assert "historical_baseline" in health
    assert "candidate_sources" in health["historical_baseline"]


# --- Village coordinate mapping (Part 5) ------------------------------------

def test_known_village_has_real_coordinates():
    from app import geography
    rec = geography.resolve_location("Bagula")
    assert rec["latitude"] is not None and rec["longitude"] is not None
    assert rec["resolution"] == "block_centroid"  # honestly not village-level GPS


def test_unmapped_village_returns_none_not_fabricated_coords():
    from app import geography
    assert geography.resolve_location("NotARealPlace") is None


def test_weather_location_unavailable_for_unmapped_village():
    from app import main
    result = main._weather_location("NotARealPlace")
    assert result is None


# --- Model-input provenance (Part 13) ---------------------------------------

def test_no_representative_model_input_is_exposed_in_live_only_beta():
    from app import main
    assert main.validation_status()["status"] == "WITHHELD"
    assert not hasattr(main, "_raw_signals_with_provenance")


# --- Integration test (real network) — skipped by default, opt-in only -----

@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("KAVACH_RUN_LIVE_INTEGRATION_TESTS") != "true",
    reason="Real-network integration test — opt in with KAVACH_RUN_LIVE_INTEGRATION_TESTS=true "
           "in an environment with internet egress to api.open-meteo.com",
)
def test_integration_real_open_meteo_call_succeeds():
    obs = OpenMeteoWeatherProvider().get_current(_loc())
    assert obs.status == LIVE
    assert obs.temperature_c is not None


def test_district_catalog_uses_verified_west_bengal_scope_without_address_pilot():
    from app import geography
    catalog = geography.district_catalog()
    assert len(catalog) == 22
    assert "Malda" in catalog
    assert geography.resolve_location("Unregistered locality") is None
