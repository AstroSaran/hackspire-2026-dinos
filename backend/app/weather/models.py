"""
Kavach — Normalized Weather Data Model
==========================================
Provider-independent shapes. Every field that could be confused for a live
reading carries its own status so a caller can never accidentally present
stale or unavailable data as live (Part 31 / Part 33 requirement).
"""
from dataclasses import dataclass, field, asdict
from typing import Optional, List
import time

LIVE = "LIVE"
STALE = "STALE"
UNAVAILABLE = "UNAVAILABLE"
SIMULATED_DEMO = "SIMULATED_DEMO"  # Part 35: demo/simulation mode weather — never to be confused with LIVE


@dataclass
class WeatherObservation:
    source: str                      # "IMD" or "Open-Meteo"
    provider_name: str               # e.g. "India Meteorological Department"
    country: str
    state: str
    district: str
    block: Optional[str]
    village: Optional[str]
    latitude: float
    longitude: float
    location_resolution: str         # "block_centroid" | "station" | "village"
    data_type: str = "observation"
    observation_time: Optional[str] = None   # ISO8601, Asia/Kolkata
    retrieved_at: Optional[str] = None        # ISO8601, when Kavach fetched it
    temperature_c: Optional[float] = None
    humidity_pct: Optional[float] = None
    rainfall_mm: Optional[float] = None
    wind_speed_kmh: Optional[float] = None
    status: str = UNAVAILABLE        # LIVE | STALE | UNAVAILABLE
    staleness_minutes: Optional[float] = None
    note: Optional[str] = None

    def to_dict(self):
        return asdict(self)


@dataclass
class WeatherForecastPoint:
    valid_from: str
    valid_until: str
    temperature_c: Optional[float] = None
    rainfall_mm: Optional[float] = None
    condition: Optional[str] = None


@dataclass
class WeatherForecast:
    source: str
    provider_name: str
    country: str
    state: str
    district: str
    block: Optional[str]
    village: Optional[str]
    latitude: float
    longitude: float
    data_type: str = "forecast"
    forecast_issue_time: Optional[str] = None
    retrieved_at: Optional[str] = None
    points: List[WeatherForecastPoint] = field(default_factory=list)
    status: str = UNAVAILABLE
    note: Optional[str] = None

    def to_dict(self):
        d = asdict(self)
        return d


@dataclass
class WeatherWarning:
    source: str
    provider_name: str
    district: str
    headline: str
    severity: Optional[str] = None
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None
    issued_at: Optional[str] = None
    retrieved_at: Optional[str] = None
    status: str = UNAVAILABLE
    note: Optional[str] = None

    def to_dict(self):
        return asdict(self)


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S+05:30", time.localtime())


def unavailable_observation(country, state, district, block, village, lat, lon, resolution, note):
    return WeatherObservation(
        source="none", provider_name="none", country=country, state=state, district=district,
        block=block, village=village, latitude=lat, longitude=lon, location_resolution=resolution,
        retrieved_at=now_iso(), status=UNAVAILABLE, note=note,
    )
