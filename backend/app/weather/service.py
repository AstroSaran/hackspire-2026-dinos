"""
Kavach — Weather Service
============================
Provider priority (Part 3 / Part 12):
  1. IMD       — only attempted if IMD_ENABLED=true (default false: not yet
                 whitelisted, see README). Kept in the architecture so
                 flipping this one variable is all that's needed later.
  2. Open-Meteo — real, public, keyless. The immediate real-data source.
  3. No synthetic fallback — unavailable is returned when real providers fail.

Caching (Part 4 / Part 21): fetch once per location per TTL window, not once
per frontend component. Every response carries real cache_status/fetched_at/
fresh_until so the UI never has to guess how fresh a reading is.

LIVE requires BOTH a successful fetch AND passing the freshness policy
(Part 3) — a successful-but-old cached reading is STALE, not LIVE.
"""
import os
import copy
import time
import threading
from functools import wraps
from .providers import IMDWeatherProvider, OpenMeteoWeatherProvider, DemoWeatherProvider, ProviderUnavailable, Location
from .models import unavailable_observation, unavailable_warning, LIVE, STALE, UNAVAILABLE, now_ist

CACHE_TTL_CURRENT_S = int(os.environ.get("WEATHER_CACHE_TTL_CURRENT_S", 600))     # 10 min
CACHE_TTL_FORECAST_S = int(os.environ.get("WEATHER_CACHE_TTL_FORECAST_S", 3600))  # 1 hour
CACHE_TTL_WARNINGS_S = int(os.environ.get("WEATHER_CACHE_TTL_WARNINGS_S", 300))   # 5 min
STALE_AFTER_S = int(os.environ.get("WEATHER_STALE_AFTER_S", 1800))                # 30 min — freshness policy

IMD_ENABLED = os.environ.get("IMD_ENABLED", "false").lower() == "true"
ENABLE_FALLBACK = os.environ.get("WEATHER_ENABLE_FALLBACK", "true").lower() == "true"
# Demo mode is a separate, explicit showcase mode. It is never used as a
# fallback after a live provider fails, and every value remains SIMULATED_DEMO.
DEMO_MODE = os.environ.get("KAVACH_DEMO_MODE", "false").lower() == "true"
DEMO_FALLBACK = False


def _unknown():
    return {"status": "unknown", "last_error": None, "last_checked": None}


class _Cache:
    def __init__(self):
        self.store = {}
        self.lock = threading.RLock()

    def get(self, key):
        with self.lock:
            entry = self.store.get(key)
            if not entry:
                return None
            value, fetched_at_s, ttl_s = entry
            age_s = time.monotonic() - fetched_at_s
            if age_s >= ttl_s:
                self.store.pop(key, None)
                return None  # Expiration must cause revalidation, not an eternal stale hit.
            return copy.deepcopy(value), age_s, ttl_s

    def set(self, key, value, ttl_s):
        with self.lock:
            if len(self.store) >= 512 and key not in self.store:
                self.store.pop(next(iter(self.store)))
            self.store[key] = (copy.deepcopy(value), time.monotonic(), ttl_s)


_cache = _Cache()
_request_locks = [threading.RLock() for _ in range(32)]


def _single_flight(fn):
    """Coalesce concurrent cold-cache reads without an unbounded lock registry."""
    @wraps(fn)
    def wrapped(loc):
        with _request_locks[hash((fn.__name__, loc.village)) % len(_request_locks)]:
            return fn(loc)
    return wrapped
_health = {
    "imd": {"current": _unknown(), "forecast": _unknown(), "warnings": _unknown()},
    "open_meteo": {"current": _unknown(), "forecast": _unknown(), "warnings": _unknown()},
}


def _record_health(provider_name, capability, ok, error=None):
    _health.setdefault(provider_name, {"current": _unknown(), "forecast": _unknown(), "warnings": _unknown()})
    _health[provider_name][capability] = {
        "status": "healthy" if ok else "unavailable",
        "last_error": error,
        "last_checked": now_ist(),
    }


def get_data_health():
    return {
        "providers": dict(_health),
        "imd_enabled_config": IMD_ENABLED,
        "demo_fallback_config": DEMO_FALLBACK,
        "demo_mode": DEMO_MODE,
        "mode": "DEMO_SHOWCASE" if DEMO_MODE else "LIVE_ONLY_BETA",
    }


def _providers_in_order():
    if DEMO_MODE:
        return [DemoWeatherProvider()]
    chain = []
    if IMD_ENABLED:
        chain.append(IMDWeatherProvider())
    if ENABLE_FALLBACK or not IMD_ENABLED:
        chain.append(OpenMeteoWeatherProvider())
    # The user-facing beta is live-data-only. Never fall back to a generated
    # demo observation: if all configured real providers fail, return UNAVAILABLE.
    return chain


def _freshness_label(age_s):
    if age_s < 60:
        return f"fresh ({int(age_s)}s old)"
    if age_s < STALE_AFTER_S:
        return f"fresh ({round(age_s/60,1)} min old)"
    return f"stale ({round(age_s/60,1)} min old)"


@_single_flight
def get_current_weather(loc: Location):
    cache_key = f"current:{DEMO_MODE}:{loc.village}:{loc.latitude}:{loc.longitude}"
    cached = _cache.get(cache_key)
    if cached:
        value, age_s, ttl_s = cached
        value = copy.copy(value)  # never mutate the shared cached object (would corrupt earlier callers' results)
        if value.status == LIVE:
            # LIVE requires passing freshness policy even on cache hit (Part 3)
            value.status = STALE if age_s > STALE_AFTER_S else LIVE
            value.data_status = value.status
        value.cache_status = "hit_stale" if age_s > ttl_s else "hit"
        value.freshness = _freshness_label(age_s)
        value.fresh_until = now_ist(ttl_s - age_s)
        return value

    last_error = None
    for provider in _providers_in_order():
        try:
            obs = provider.get_current(loc)
            _record_health(provider.name, "current", True)
            obs.cache_status = "miss"
            obs.freshness = "fresh (just fetched)"
            obs.fresh_until = now_ist(CACHE_TTL_CURRENT_S)
            _cache.set(cache_key, obs, CACHE_TTL_CURRENT_S)
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


@_single_flight
def get_forecast_weather(loc: Location):
    cache_key = f"forecast:{DEMO_MODE}:{loc.village}:{loc.latitude}:{loc.longitude}"
    cached = _cache.get(cache_key)
    if cached:
        value, age_s, ttl_s = cached
        value = copy.copy(value)
        value.cache_status = "hit_stale" if age_s > ttl_s else "hit"
        if age_s > ttl_s:
            value.status = STALE
            value.data_status = STALE
        return value
    for provider in _providers_in_order():
        try:
            fc = provider.get_forecast(loc)
            _record_health(provider.name, "forecast", True)
            fc.cache_status = "miss"
            fc.fresh_until = now_ist(CACHE_TTL_FORECAST_S)
            _cache.set(cache_key, fc, CACHE_TTL_FORECAST_S)
            return fc
        except ProviderUnavailable as e:
            _record_health(provider.name, "forecast", False, e.reason)
            continue
    from .models import WeatherForecast
    return WeatherForecast(
        provider="none", provider_name="none", source="none", status=UNAVAILABLE, data_status=UNAVAILABLE,
        country=loc.country, state=loc.state, district=loc.district, block=loc.block, village=loc.village,
        latitude=loc.latitude, longitude=loc.longitude, fetched_at=now_ist(),
        note="FORECAST UNAVAILABLE — all configured providers failed.",
    )


@_single_flight
def get_warnings(loc: Location):
    """Part 11: returns (warnings_list, status). status='LIVE' only if a real
    source was genuinely queried successfully (even if the list is empty —
    'checked, none active' is a real result). status='UNAVAILABLE' means no
    source could be checked at all — the caller must show 'WARNING STATUS
    UNAVAILABLE', never 'no active warning'."""
    cache_key = f"warnings:{DEMO_MODE}:{loc.village}:{loc.latitude}:{loc.longitude}"
    cached = _cache.get(cache_key)
    if cached:
        return cached[0]
    for provider in _providers_in_order():
        if not getattr(provider, "supports_warnings", False):
            _health.setdefault(provider.name, {"current": _unknown(), "forecast": _unknown(), "warnings": _unknown()})
            _health[provider.name]["warnings"] = {
                "status": "not_applicable", "last_error": "provider has no warnings product",
                "last_checked": now_ist(),
            }
            continue
        try:
            warnings = provider.get_warnings(loc)
            _record_health(provider.name, "warnings", True)
            result = {"status": LIVE, "warnings": [w.to_dict() for w in warnings], "provider": provider.name}
            _cache.set(cache_key, result, CACHE_TTL_WARNINGS_S)
            return result
        except ProviderUnavailable as e:
            _record_health(provider.name, "warnings", False, e.reason)
            continue
    unavail = unavailable_warning(loc.district, "No warnings source could be genuinely queried — "
                                                 "IMD requires whitelisting, Open-Meteo has no warnings product.")
    return {"status": UNAVAILABLE, "warnings": [], "provider": "none", "note": unavail.note}
