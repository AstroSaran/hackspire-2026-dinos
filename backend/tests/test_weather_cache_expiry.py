from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.weather import models, service
from app.weather.providers import Location, ProviderUnavailable


@pytest.fixture
def context(monkeypatch):
    cache = service._Cache()
    monkeypatch.setattr(service, "_cache", cache)
    clock = [1000.0]
    monkeypatch.setattr(service.time, "monotonic", lambda: clock[0])
    loc = Location("India", "West Bengal", "Nadia", "Block", "CacheExpiry", 23.4, 88.5, "grid")
    provider = SimpleNamespace(name="test", supports_warnings=True,
        get_current=Mock(side_effect=lambda _: models.WeatherObservation("test", "test", "test", status="LIVE")),
        get_forecast=Mock(side_effect=lambda _: models.WeatherForecast("test", "test", "test", status="LIVE")),
        get_warnings=Mock(return_value=[]))
    monkeypatch.setattr(service, "_providers_in_order", lambda: [provider])
    return loc, provider, clock


@pytest.mark.parametrize("function,method,ttl", [
    (service.get_current_weather, "get_current", service.CACHE_TTL_CURRENT_S),
    (service.get_forecast_weather, "get_forecast", service.CACHE_TTL_FORECAST_S),
    (service.get_warnings, "get_warnings", service.CACHE_TTL_WARNINGS_S),
])
def test_cache_refreshes_at_expiry_and_abstains_on_failed_refresh(context, function, method, ttl):
    loc, provider, clock = context
    call = getattr(provider, method)
    function(loc)
    clock[0] += ttl - 1
    function(loc)
    assert call.call_count == 1
    clock[0] += 1
    function(loc)
    assert call.call_count == 2
    call.side_effect = ProviderUnavailable("test", "offline")
    clock[0] += ttl
    result = function(loc)
    assert (result["status"] if isinstance(result, dict) else result.status) == "UNAVAILABLE"


def test_concurrent_cold_requests_share_one_provider_call(context):
    loc, provider, _ = context
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(service.get_current_weather, [loc] * 16))
    assert all(result.status == "LIVE" for result in results)
    assert provider.get_current.call_count == 1
    results[0].temperature_c = 999
    assert service.get_current_weather(loc).temperature_c is None


def test_ist_timestamp_is_correct_even_with_utc_os_clock():
    before = datetime.now(timezone.utc)
    stamp = datetime.fromisoformat(models.now_ist())
    after = datetime.now(timezone.utc)
    assert stamp.utcoffset().total_seconds() == 19800
    assert -1 <= (stamp - before).total_seconds() <= (after - before).total_seconds()
