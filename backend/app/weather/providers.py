"""
Kavach — Weather Providers
=============================
Two real providers, coded against each service's actual documented API
contract. Neither ever fabricates a reading:
  - IMDWeatherProvider calls IMD's real documented endpoints
    (mausam.imd.gov.in/api/*). As of this build, these endpoints require
    IP whitelisting by IMD's nodal officer and return HTTP 401 without it —
    independently confirmed both by a live test against a real endpoint and
    by multiple third-party developer reports. That failure is surfaced as
    ProviderUnavailable, never silently swapped for a guess.
  - OpenMeteoWeatherProvider calls Open-Meteo's real, public, keyless
    forecast API (api.open-meteo.com/v1/forecast) — a genuine live weather
    service (global NWP models: ECMWF/GFS/ICON blend), used only as a
    documented fallback per the product's own design, and never presented
    as IMD-sourced.

IMPORTANT SANDBOX NOTE: this development container's network egress is
restricted to package registries (pypi/npm/github) and does not include
mausam.imd.gov.in or api.open-meteo.com, so neither provider could be
executed live from inside this container. Both are written against each
API's real, independently-verified contract; run them in an environment
with normal internet egress to get genuinely live data. See README
"Data & Validation status" for exactly what was and wasn't verified here.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
import time
import requests

from .models import (
    WeatherObservation, WeatherForecast, WeatherForecastPoint, WeatherWarning,
    LIVE, STALE, UNAVAILABLE, SIMULATED_DEMO, now_iso,
)


class ProviderUnavailable(Exception):
    """Raised when a provider cannot return real data. Callers must never
    substitute fabricated values when this is raised — they must either
    fall back to another real provider or report UNAVAILABLE."""
    def __init__(self, provider: str, reason: str):
        self.provider = provider
        self.reason = reason
        super().__init__(f"{provider} unavailable: {reason}")


@dataclass
class Location:
    country: str
    state: str
    district: str
    block: str
    village: str
    latitude: float
    longitude: float
    resolution: str
    imd_district_id: str = None
    imd_station_id: str = None


class WeatherProvider(ABC):
    name: str
    provider_name: str

    @abstractmethod
    def get_current(self, loc: Location) -> WeatherObservation: ...

    @abstractmethod
    def get_forecast(self, loc: Location) -> WeatherForecast: ...

    @abstractmethod
    def get_warnings(self, loc: Location) -> list:
        """Returns a list of WeatherWarning. Empty list means 'checked, none
        active' — NOT 'unavailable'; if the check itself failed, raise."""
        ...


class IMDWeatherProvider(WeatherProvider):
    """
    Real IMD endpoints (verified against IMD's own published API list and a
    live request during development — see module docstring):
      current weather:      https://mausam.imd.gov.in/api/current_wx_api.php?id={station_id}
      district rainfall:    https://mausam.imd.gov.in/api/districtwise_rainfall_api.php?id={district_id}
      district warnings:    https://mausam.imd.gov.in/api/warnings_district_api.php?id={district_id}
      district nowcast:     https://mausam.imd.gov.in/api/nowcast_district_api.php?id={district_id}
    These require IP whitelisting; without it they return HTTP 401. This
    provider does not work around that (no scraping, no guessed bypass) —
    it surfaces the real failure.
    """
    name = "imd"
    provider_name = "India Meteorological Department"
    BASE = "https://mausam.imd.gov.in/api"
    TIMEOUT_S = 6
    supports_warnings = True

    def _get(self, path: str, params: dict):
        try:
            resp = requests.get(f"{self.BASE}/{path}", params=params, timeout=self.TIMEOUT_S)
        except requests.exceptions.RequestException as e:
            raise ProviderUnavailable(self.name, f"network error: {e}")
        if resp.status_code == 401:
            raise ProviderUnavailable(
                self.name,
                "HTTP 401 — IMD endpoint requires IP whitelisting by IMD's nodal officer "
                "(see mausam.imd.gov.in/responsive/apis.php); this deployment is not whitelisted.",
            )
        if resp.status_code != 200:
            raise ProviderUnavailable(self.name, f"HTTP {resp.status_code}")
        try:
            return resp.json()
        except ValueError:
            raise ProviderUnavailable(self.name, "non-JSON response")

    def get_current(self, loc: Location) -> WeatherObservation:
        if not loc.imd_station_id:
            raise ProviderUnavailable(self.name, "no IMD station id configured for this location")
        data = self._get("current_wx_api.php", {"id": loc.imd_station_id})
        # Real field names per IMD's published sample response; mapped defensively.
        return WeatherObservation(
            source="IMD", provider_name=self.provider_name, country=loc.country, state=loc.state,
            district=loc.district, block=loc.block, village=loc.village,
            latitude=loc.latitude, longitude=loc.longitude, location_resolution="station",
            observation_time=data.get("Date_Time") or data.get("observation_time"),
            retrieved_at=now_iso(),
            temperature_c=_to_float(data.get("Temperature") or data.get("temperature")),
            humidity_pct=_to_float(data.get("Humidity") or data.get("humidity")),
            rainfall_mm=_to_float(data.get("Rainfall") or data.get("rainfall")),
            wind_speed_kmh=_to_float(data.get("Wind_Speed") or data.get("wind_speed")),
            status=LIVE,
        )

    def get_forecast(self, loc: Location) -> WeatherForecast:
        if not loc.imd_district_id:
            raise ProviderUnavailable(self.name, "no IMD district id configured for this location")
        data = self._get("api_5d_statewisedistricts_rf_forecast.php", {"id": loc.imd_district_id})
        points = []
        for row in (data if isinstance(data, list) else data.get("data", [])):
            points.append(WeatherForecastPoint(
                valid_from=row.get("Date"), valid_until=row.get("Date"),
                rainfall_mm=_to_float(row.get("Daily Actual") or row.get("Rainfall")),
            ))
        return WeatherForecast(
            source="IMD", provider_name=self.provider_name, country=loc.country, state=loc.state,
            district=loc.district, block=loc.block, village=loc.village,
            latitude=loc.latitude, longitude=loc.longitude,
            forecast_issue_time=now_iso(), retrieved_at=now_iso(), points=points, status=LIVE,
        )

    def get_warnings(self, loc: Location) -> list:
        if not loc.imd_district_id:
            raise ProviderUnavailable(self.name, "no IMD district id configured for this location")
        data = self._get("warnings_district_api.php", {"id": loc.imd_district_id})
        out = []
        for row in (data if isinstance(data, list) else data.get("data", [])):
            out.append(WeatherWarning(
                source="IMD", provider_name=self.provider_name, district=loc.district,
                headline=row.get("Warning") or row.get("warning_text", "Warning"),
                severity=row.get("Color_Code") or row.get("severity"),
                valid_from=row.get("Valid_From"), valid_until=row.get("Valid_To"),
                issued_at=row.get("Issue_Time"), retrieved_at=now_iso(), status=LIVE,
            ))
        return out


class OpenMeteoWeatherProvider(WeatherProvider):
    """
    Real, public, keyless Open-Meteo forecast API. Genuinely live — but NOT
    IMD, and NOT India-specific: it's a global NWP model blend. Used only as
    a documented fallback per the product's design (Part 6).
    """
    name = "open_meteo"
    provider_name = "Open-Meteo (global NWP model blend — not IMD)"
    BASE = "https://api.open-meteo.com/v1/forecast"
    TIMEOUT_S = 6
    supports_warnings = False  # Open-Meteo has no severe-weather-warning product

    def _get(self, loc: Location, extra: dict):
        params = {
            "latitude": loc.latitude, "longitude": loc.longitude,
            "timezone": "Asia/Kolkata", **extra,
        }
        try:
            resp = requests.get(self.BASE, params=params, timeout=self.TIMEOUT_S)
        except requests.exceptions.RequestException as e:
            raise ProviderUnavailable(self.name, f"network error: {e}")
        if resp.status_code != 200:
            raise ProviderUnavailable(self.name, f"HTTP {resp.status_code}")
        try:
            return resp.json()
        except ValueError:
            raise ProviderUnavailable(self.name, "non-JSON response")

    def get_current(self, loc: Location) -> WeatherObservation:
        data = self._get(loc, {
            "current": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m",
        })
        cur = data.get("current", {})
        return WeatherObservation(
            source="Open-Meteo", provider_name=self.provider_name, country=loc.country, state=loc.state,
            district=loc.district, block=loc.block, village=loc.village,
            latitude=loc.latitude, longitude=loc.longitude, location_resolution=loc.resolution,
            observation_time=cur.get("time"), retrieved_at=now_iso(),
            temperature_c=cur.get("temperature_2m"), humidity_pct=cur.get("relative_humidity_2m"),
            rainfall_mm=cur.get("precipitation"), wind_speed_kmh=cur.get("wind_speed_10m"),
            status=LIVE, note="Global NWP model blend (not IMD-sourced); used as fallback.",
        )

    def get_forecast(self, loc: Location) -> WeatherForecast:
        data = self._get(loc, {"hourly": "precipitation,temperature_2m", "forecast_days": 2})
        hourly = data.get("hourly", {})
        times = hourly.get("time", [])
        temps = hourly.get("temperature_2m", [])
        rains = hourly.get("precipitation", [])
        points = [
            WeatherForecastPoint(valid_from=t, valid_until=t,
                                  temperature_c=temps[i] if i < len(temps) else None,
                                  rainfall_mm=rains[i] if i < len(rains) else None)
            for i, t in enumerate(times)
        ]
        return WeatherForecast(
            source="Open-Meteo", provider_name=self.provider_name, country=loc.country, state=loc.state,
            district=loc.district, block=loc.block, village=loc.village,
            latitude=loc.latitude, longitude=loc.longitude,
            forecast_issue_time=now_iso(), retrieved_at=now_iso(), points=points, status=LIVE,
            note="Global NWP model blend (not IMD-sourced); used as fallback.",
        )

    def get_warnings(self, loc: Location) -> list:
        # Open-Meteo has no severe-weather-warning product; this is a real
        # capability gap, not a failure to surface as UNAVAILABLE.
        return []


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class DemoWeatherProvider(WeatherProvider):
    """
    Part 35 (Demo Mode): a clearly-labeled simulation used ONLY when
    explicitly enabled (WEATHER_PROVIDER=demo or WEATHER_DEMO_FALLBACK=true),
    for showcasing the UI when no live provider is reachable (e.g. this
    sandbox's restricted network egress). Every value it returns carries
    status=SIMULATED_DEMO, never LIVE — see models.SIMULATED_DEMO. This is
    NOT a silent fake-data fallback: it must be turned on deliberately, and
    the UI is required to render SIMULATED_DEMO with different visual
    treatment than LIVE (see frontend).
    """
    name = "demo"
    provider_name = "Kavach demo mode (simulated — not a live provider)"
    supports_warnings = True

    def get_current(self, loc: Location) -> WeatherObservation:
        # Deterministic per-village pseudo-values so the demo is stable
        # across reloads, seeded from the village name (not randomness that
        # could be mistaken for a changing live feed).
        seed = sum(ord(c) for c in loc.village)
        return WeatherObservation(
            source="demo", provider_name=self.provider_name, country=loc.country, state=loc.state,
            district=loc.district, block=loc.block, village=loc.village,
            latitude=loc.latitude, longitude=loc.longitude, location_resolution=loc.resolution,
            observation_time=now_iso(), retrieved_at=now_iso(),
            temperature_c=round(27 + (seed % 9), 1),
            humidity_pct=round(60 + (seed % 30), 0),
            rainfall_mm=round((seed % 40) * 0.6, 1),
            wind_speed_kmh=round(6 + (seed % 15), 1),
            status=SIMULATED_DEMO,
            note="Demo/simulation mode — not a live reading. Enabled because no live provider is "
                 "reachable in this environment; see /data-health for real provider status.",
        )

    def get_forecast(self, loc: Location) -> WeatherForecast:
        return WeatherForecast(
            source="demo", provider_name=self.provider_name, country=loc.country, state=loc.state,
            district=loc.district, block=loc.block, village=loc.village,
            latitude=loc.latitude, longitude=loc.longitude,
            forecast_issue_time=now_iso(), retrieved_at=now_iso(), points=[], status=SIMULATED_DEMO,
            note="Demo/simulation mode — not a live forecast.",
        )

    def get_warnings(self, loc: Location) -> list:
        return []
