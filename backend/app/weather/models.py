"""
Kavach — Normalized Weather Data Model
==========================================
Provider-independent shapes carrying full provenance (Part 6): provider,
source, status, data_status, data_type, location, timestamps, timezone,
freshness, cache_status. Every field that could be confused for a live
reading carries its own status so a caller can never present stale or
unavailable data as live (Part 3 / Part 25).

All user-facing timestamps are Asia/Kolkata / IST (Part 7). Internally we
just use IST directly (no UTC storage layer exists yet in this build — see
README "Known limitations").
"""
from dataclasses import dataclass, field, asdict
from typing import Optional, List
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TIMEZONE = "Asia/Kolkata"

# Status values — never blended, never silently swapped (Part 3, Part 25)
LIVE = "LIVE"
STALE = "STALE"
SIMULATED_DEMO = "SIMULATED_DEMO"
UNAVAILABLE = "UNAVAILABLE"

# Data types — never call a forecast "observed" (Part 6)
OBSERVATION = "OBSERVATION"
FORECAST = "FORECAST"
WARNING = "WARNING"
SIMULATED = "SIMULATED"


def now_ist(offset_seconds=0):
    return (datetime.now(ZoneInfo(TIMEZONE)) + timedelta(seconds=offset_seconds)).isoformat(timespec="seconds")


@dataclass
class WeatherObservation:
    provider: str                      # short code: "imd" | "open_meteo" | "demo" | "none"
    provider_name: str                 # display name, e.g. "India Meteorological Department"
    source: str                        # dataset/model detail, e.g. "Open-Meteo Forecast API (GFS/ECMWF/ICON blend)"
    status: str = UNAVAILABLE          # LIVE | STALE | SIMULATED_DEMO | UNAVAILABLE
    data_status: str = UNAVAILABLE     # mirrors `status`; kept as its own field for naming
                                        # consistency with the livelihood-signal provenance objects
    data_type: str = OBSERVATION       # OBSERVATION | FORECAST | WARNING | SIMULATED

    country: str = "India"
    state: str = "West Bengal"
    district: Optional[str] = None
    block: Optional[str] = None
    village: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    provider_latitude: Optional[float] = None  # Weather provider's resolved grid/station coordinate
    provider_longitude: Optional[float] = None
    location_resolution: str = "unknown"   # "block_centroid" | "station" | "village" | "unavailable"

    observed_at: Optional[str] = None  # IST, ISO8601 — when the reading is valid for
    fetched_at: Optional[str] = None   # IST, ISO8601 — when Kavach retrieved it
    timezone: str = TIMEZONE
    freshness: Optional[str] = None    # human string, e.g. "fresh (2 min old)" / "stale (54 min old)"
    cache_status: str = "miss"         # "miss" | "hit" | "hit_stale"
    fresh_until: Optional[str] = None  # IST — when the cache entry expires

    temperature_c: Optional[float] = None
    humidity_pct: Optional[float] = None
    precipitation_mm: Optional[float] = None
    rain_mm: Optional[float] = None
    wind_speed_kmh: Optional[float] = None
    wind_direction_deg: Optional[float] = None
    weather_code: Optional[int] = None
    evapotranspiration_mm: Optional[float] = None

    note: Optional[str] = None

    def to_dict(self):
        return asdict(self)


@dataclass
class WeatherForecastDay:
    date: str                          # IST calendar date, e.g. "2026-09-27"
    precipitation_sum_mm: Optional[float] = None
    temperature_max_c: Optional[float] = None
    temperature_min_c: Optional[float] = None
    precipitation_probability_max_pct: Optional[float] = None
    wind_speed_max_kmh: Optional[float] = None
    weather_code: Optional[int] = None


@dataclass
class WeatherForecast:
    provider: str
    provider_name: str
    source: str
    status: str = UNAVAILABLE
    data_status: str = UNAVAILABLE
    data_type: str = FORECAST

    country: str = "India"
    state: str = "West Bengal"
    district: Optional[str] = None
    block: Optional[str] = None
    village: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    provider_latitude: Optional[float] = None  # Weather provider's resolved grid coordinate
    provider_longitude: Optional[float] = None

    issued_at: Optional[str] = None    # IST — when this forecast run was issued
    fetched_at: Optional[str] = None
    timezone: str = TIMEZONE
    cache_status: str = "miss"
    fresh_until: Optional[str] = None

    days: List[WeatherForecastDay] = field(default_factory=list)
    note: Optional[str] = None

    def to_dict(self):
        return asdict(self)


@dataclass
class WeatherWarning:
    provider: str
    provider_name: str
    source: str
    district: str
    status: str = UNAVAILABLE          # LIVE (a real query succeeded) | UNAVAILABLE (not genuinely checked)
    data_status: str = UNAVAILABLE
    data_type: str = WARNING
    headline: Optional[str] = None     # None when status=UNAVAILABLE — never invent a headline
    severity: Optional[str] = None
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None
    issued_at: Optional[str] = None
    fetched_at: Optional[str] = None
    timezone: str = TIMEZONE
    note: Optional[str] = None

    def to_dict(self):
        return asdict(self)


def unavailable_observation(country, state, district, block, village, lat, lon, resolution, note):
    return WeatherObservation(
        provider="none", provider_name="none", source="none",
        status=UNAVAILABLE, data_status=UNAVAILABLE,
        country=country, state=state, district=district, block=block, village=village,
        latitude=lat, longitude=lon, location_resolution=resolution,
        fetched_at=now_ist(), note=note,
    )


def unavailable_warning(district: str, note: str):
    """Part 11: 'WARNING STATUS UNAVAILABLE', never 'no active warning', unless a
    real source was genuinely queried successfully."""
    return WeatherWarning(
        provider="none", provider_name="none", source="none", district=district,
        status=UNAVAILABLE, data_status=UNAVAILABLE, headline=None,
        fetched_at=now_ist(), note=note,
    )
