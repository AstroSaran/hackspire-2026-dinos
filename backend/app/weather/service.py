"""
Kavach — Weather Service
============================
Orchestrates provider selection, short-TTL caching (Part 31: don't hammer
external APIs), and the fallback chain (Part 6): IMD -> optional Open-Meteo
-> LIVE_UNAVAILABLE. Never fabricates a reading at any stage.
"""
import os
import time
from .providers import IMDWeatherProvider, OpenMeteoWeatherProvider, DemoWeatherProvider, ProviderUnavailable, Location
from .models import unavailable_observation, LIVE, STALE, UNAVAILABLE

CACHE_TTL_CURRENT_S = int(os.environ.get("WEATHER_CACHE_TTL_CURRENT_S", 600))     # 10 min
CACHE_TTL_FORECAST_S = int(os.environ.get("WEATHER_CACHE_TTL_FORECAST_S", 3600))  # 1 hour
CACHE_TTL_WARNINGS_S = int(os.environ.get("WEATHER_CACHE_TTL_WARNINGS_S", 300))   # 5 min
STALE_AFTER_S = int(os.environ.get("WEATHER_STALE_AFTER_S", 1800))                # 30 min

WEATHER_PROVIDER = os.environ.get("WEATHER_PROVIDER", "imd")  # imd | open_meteo | demo
ENABLE_FALLBACK = os.environ.get("WEATHER_ENABLE_FALLBACK", "true").lower() == "true"
# Part 35: explicit, opt-in only. Never enabled by default in a "live" deployment.
DEMO_FALLBACK = os.environ.get("WEATHER_DEMO_FALLBACK", "false").lower() == "true"


def _unknown():
    return {"status": "unknown", "last_error": None, "last_checked": None}


class _Cache:
    def __init__(self):
        self.store = {}

    def get(self, key, ttl_s):
        entry = self.store.get(key)
        if not entry:
            return None
        value, fetched_at = entry
        age = time.time() - fetched_at
        if age > ttl_s:
            return None
        return value, age

    def set(self, key, value):
        self.store[key] = (value, time.time())


_cache = _Cache()
_health = {
    "imd": {"current": _unknown(), "forecast": _unknown(), "warnings": _unknown()},
    "open_meteo": {"current": _unknown(), "forecast": _unknown(), "warnings": _unknown()},
}


def _record_health(provider_name, capability, ok, error=None):
    _health.setdefault(provider_name, {"current": _unknown(), "forecast": _unknown(), "warnings": _unknown()})
    _health[provider_name][capability] = {
        "status": "healthy" if ok else "unavailable",
        "last_error": error,
        "last_checked": time.strftime("%Y-%m-%dT%H:%M:%S+05:30", time.localtime()),
    }


def get_data_health():
    return dict(_health)


def _providers_in_order():
    chain = []
    if WEATHER_PROVIDER == "open_meteo":
        chain = [OpenMeteoWeatherProvider()]
    elif WEATHER_PROVIDER == "demo":
        chain = [DemoWeatherProvider()]
    else:
        chain = [IMDWeatherProvider()]
        if ENABLE_FALLBACK:
            chain.append(OpenMeteoWeatherProvider())
    if DEMO_FALLBACK and WEATHER_PROVIDER != "demo":
        chain.append(DemoWeatherProvider())  # last resort only, always opt-in, always SIMULATED_DEMO status
    return chain


def _apply_staleness(obs):
    if obs.status != LIVE or not obs.retrieved_at:
        return obs
    # simple staleness check based on retrieval time vs now
    obs.staleness_minutes = 0.0  # freshly retrieved this call
    return obs


def get_current_weather(loc: Location):
    cache_key = f"current:{loc.village}"
    cached = _cache.get(cache_key, CACHE_TTL_CURRENT_S)
    if cached:
        value, age = cached
        if value.status == LIVE:
            value.status = STALE if age > STALE_AFTER_S else LIVE
        value.staleness_minutes = round(age / 60, 1)
        return value

    last_error = None
    for provider in _providers_in_order():
        try:
            obs = provider.get_current(loc)
            _record_health(provider.name, "current", True)
            _cache.set(cache_key, obs)
            obs.staleness_minutes = 0.0
            return obs
        except ProviderUnavailable as e:
            _record_health(provider.name, "current", False, e.reason)
            last_error = e
            continue
    return unavailable_observation(
        loc.country, loc.state, loc.district, loc.block, loc.village,
        loc.latitude, loc.longitude, loc.resolution,
        note=f"LIVE WEATHER UNAVAILABLE — all configured providers failed. Last error: {last_error}",
    )


def get_forecast_weather(loc: Location):
    cache_key = f"forecast:{loc.village}"
    cached = _cache.get(cache_key, CACHE_TTL_FORECAST_S)
    if cached:
        return cached[0]
    for provider in _providers_in_order():
        try:
            fc = provider.get_forecast(loc)
            _record_health(provider.name, "forecast", True)
            _cache.set(cache_key, fc)
            return fc
        except ProviderUnavailable as e:
            _record_health(provider.name, "forecast", False, e.reason)
            continue
    from .models import WeatherForecast
    return WeatherForecast(
        source="none", provider_name="none", country=loc.country, state=loc.state,
        district=loc.district, block=loc.block, village=loc.village,
        latitude=loc.latitude, longitude=loc.longitude, status=UNAVAILABLE,
        note="FORECAST UNAVAILABLE — all configured providers failed.",
    )


def get_warnings(loc: Location):
    cache_key = f"warnings:{loc.village}"
    cached = _cache.get(cache_key, CACHE_TTL_WARNINGS_S)
    if cached:
        return cached[0]
    for provider in _providers_in_order():
        if not getattr(provider, "supports_warnings", True):
            _health[provider.name]["warnings"] = {
                "status": "not_applicable", "last_error": "provider has no warnings product",
                "last_checked": time.strftime("%Y-%m-%dT%H:%M:%S+05:30", time.localtime()),
            }
            continue
        try:
            warnings = provider.get_warnings(loc)
            _record_health(provider.name, "warnings", True)
            _cache.set(cache_key, warnings)
            return warnings
        except ProviderUnavailable as e:
            _record_health(provider.name, "warnings", False, e.reason)
            continue
    return []  # no provider could genuinely check — see health for why (unavailable vs not_applicable)
