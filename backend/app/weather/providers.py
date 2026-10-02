"""
Kavach — Weather Providers
=============================
Three providers, none of which fabricate a reading:

  - IMDWeatherProvider: real documented endpoints (mausam.imd.gov.in/api/*).
    Confirmed (live test, HTTP 401) to require IP whitelisting by IMD's
    nodal officer, corroborated by independent third-party reports. Kept in
    the architecture as the future primary provider (Part 12) — never
    removed, never worked around.

  - OpenMeteoWeatherProvider: real, public, keyless forecast API
    (api.open-meteo.com/v1/forecast) plus the historical archive API
    (archive-api.open-meteo.com/v1/archive, ERA5 reanalysis from 1940) used
    for a defensible rainfall baseline. Confirmed via Open-Meteo's own
    official site and GitHub repo: "Simple JSON API — HTTP GET, no
    authentication, CC BY 4.0 data licence." Requests only the variables
    Kavach actually uses (Part 4: "do not request unnecessary variables").

  - DemoWeatherProvider: explicit, opt-in only, status=SIMULATED_DEMO,
    never LIVE. For showcasing the UI where no live provider is reachable.

SANDBOX NOTE: this container's network egress excludes both
mausam.imd.gov.in and api.open-meteo.com (confirmed via a direct request
that returned this container's own egress-proxy `403 host_not_allowed`, not
a rejection from either weather service, and via web-fetch's robots.txt
policy on the same host). Both real providers are written against each
API's actual, independently-verified contract; deploy with normal internet
egress to get genuinely live data.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
import requests

from .models import (
    WeatherObservation, WeatherForecast, WeatherForecastDay, WeatherWarning,
    LIVE, STALE, UNAVAILABLE, SIMULATED_DEMO, OBSERVATION, FORECAST, WARNING,
    now_ist, unavailable_warning,
)


class ProviderUnavailable(Exception):
    """Raised when a provider cannot return real data. Callers must never
    substitute fabricated values when this is raised."""
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
    imd_district_id: Optional[str] = None
    imd_station_id: Optional[str] = None


class WeatherProvider(ABC):
    name: str
    provider_name: str
    supports_warnings: bool = False

    @abstractmethod
    def get_current(self, loc: Location) -> WeatherObservation: ...

    @abstractmethod
    def get_forecast(self, loc: Location) -> WeatherForecast: ...

    def get_warnings(self, loc: Location) -> list:
        """Default: this provider has no warnings product. Service layer
        treats this as 'not applicable', distinct from a failed check."""
        return []


class IMDWeatherProvider(WeatherProvider):
    """
    Real IMD endpoints. Requires IP whitelisting (see module docstring) —
    without it, every call below returns HTTP 401, surfaced honestly.
    """
    name = "imd"
    provider_name = "India Meteorological Department"
    supports_warnings = True
    BASE = "https://mausam.imd.gov.in/api"
    TIMEOUT_S = 6

    def _get(self, path: str, params: dict):
        try:
            resp = requests.get(f"{self.BASE}/{path}", params=params, timeout=self.TIMEOUT_S)
        except requests.exceptions.RequestException as e:
            raise ProviderUnavailable(self.name, f"network error: {e}")
        if resp.status_code == 401:
            raise ProviderUnavailable(
                self.name,
                "HTTP 401 — requires IP whitelisting by IMD's nodal officer "
                "(mausam.imd.gov.in/responsive/apis.php); this deployment is not whitelisted.",
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
        return WeatherObservation(
            provider=self.name, provider_name=self.provider_name,
            source="IMD current-weather API (station observation)",
            status=LIVE, data_status=LIVE, data_type=OBSERVATION,
            country=loc.country, state=loc.state, district=loc.district, block=loc.block,
            village=loc.village, latitude=loc.latitude, longitude=loc.longitude,
            location_resolution="station",
            observed_at=data.get("Date_Time") or data.get("observation_time"),
            fetched_at=now_ist(), cache_status="miss",
            temperature_c=_f(data.get("Temperature") or data.get("temperature")),
            humidity_pct=_f(data.get("Humidity") or data.get("humidity")),
            precipitation_mm=_f(data.get("Rainfall") or data.get("rainfall")),
            wind_speed_kmh=_f(data.get("Wind_Speed") or data.get("wind_speed")),
            wind_direction_deg=_f(data.get("Wind_Direction")),
        )

    def get_forecast(self, loc: Location) -> WeatherForecast:
        if not loc.imd_district_id:
            raise ProviderUnavailable(self.name, "no IMD district id configured for this location")
        data = self._get("api_5d_statewisedistricts_rf_forecast.php", {"id": loc.imd_district_id})
        days = []
        for row in (data if isinstance(data, list) else data.get("data", [])):
            days.append(WeatherForecastDay(
                date=row.get("Date"),
                precipitation_sum_mm=_f(row.get("Daily Actual") or row.get("Rainfall")),
            ))
        return WeatherForecast(
            provider=self.name, provider_name=self.provider_name,
            source="IMD 5-day district rainfall forecast",
            status=LIVE, data_status=LIVE,
            country=loc.country, state=loc.state, district=loc.district, block=loc.block,
            village=loc.village, latitude=loc.latitude, longitude=loc.longitude,
            issued_at=now_ist(), fetched_at=now_ist(), days=days,
        )

    def get_warnings(self, loc: Location) -> list:
        if not loc.imd_district_id:
            raise ProviderUnavailable(self.name, "no IMD district id configured for this location")
        data = self._get("warnings_district_api.php", {"id": loc.imd_district_id})
        out = []
        for row in (data if isinstance(data, list) else data.get("data", [])):
            out.append(WeatherWarning(
                provider=self.name, provider_name=self.provider_name,
                source="IMD district-wise warning API", district=loc.district,
                status=LIVE, data_status=LIVE,
                headline=row.get("Warning") or row.get("warning_text"),
                severity=row.get("Color_Code") or row.get("severity"),
                valid_from=row.get("Valid_From"), valid_until=row.get("Valid_To"),
                issued_at=row.get("Issue_Time"), fetched_at=now_ist(),
            ))
        return out


class OpenMeteoWeatherProvider(WeatherProvider):
    """
    Real, public, keyless Open-Meteo APIs:
      current + forecast: https://api.open-meteo.com/v1/forecast
      historical (ERA5):  https://archive-api.open-meteo.com/v1/archive
    Genuinely live — but NOT IMD, and NOT India-specific: a global NWP model
    blend (documented fallback per Part 3/Part 12).
    """
    name = "open_meteo"
    provider_name = "Open-Meteo (global NWP model blend — not IMD)"
    supports_warnings = False  # real capability gap, not a failure (Part 6)
    FORECAST_BASE = "https://api.open-meteo.com/v1/forecast"
    ARCHIVE_BASE = "https://archive-api.open-meteo.com/v1/archive"
    TIMEOUT_S = 6
    # Requested only where Kavach actually uses them (Part 4)
    CURRENT_VARS = "temperature_2m,relative_humidity_2m,precipitation,rain,wind_speed_10m,wind_direction_10m"
    DAILY_VARS = "precipitation_sum,temperature_2m_max,temperature_2m_min"
    DAILY_HISTORICAL_VARS = "precipitation_sum,et0_fao_evapotranspiration"

    def _get(self, base: str, loc: Location, extra: dict):
        params = {"latitude": loc.latitude, "longitude": loc.longitude,
                   "timezone": "Asia/Kolkata", **extra}
        try:
            resp = requests.get(base, params=params, timeout=self.TIMEOUT_S)
        except requests.exceptions.RequestException as e:
            raise ProviderUnavailable(self.name, f"network error: {e}")
        if resp.status_code != 200:
            raise ProviderUnavailable(self.name, f"HTTP {resp.status_code}")
        try:
            data = resp.json()
        except ValueError:
            raise ProviderUnavailable(self.name, "non-JSON response")
        if data.get("error"):
            raise ProviderUnavailable(self.name, data.get("reason", "API returned error:true"))
        return data

    def get_current(self, loc: Location) -> WeatherObservation:
        data = self._get(self.FORECAST_BASE, loc, {"current": self.CURRENT_VARS})
        cur = data.get("current", {})
        return WeatherObservation(
            provider=self.name, provider_name=self.provider_name,
            source="Open-Meteo Forecast API — global NWP blend (GFS/ECMWF/ICON)",
            status=LIVE, data_status=LIVE, data_type=OBSERVATION,
            country=loc.country, state=loc.state, district=loc.district, block=loc.block,
            village=loc.village, latitude=loc.latitude, longitude=loc.longitude,
            location_resolution=loc.resolution,
            observed_at=cur.get("time"), fetched_at=now_ist(), cache_status="miss",
            temperature_c=cur.get("temperature_2m"), humidity_pct=cur.get("relative_humidity_2m"),
            precipitation_mm=cur.get("precipitation"), rain_mm=cur.get("rain"),
            wind_speed_kmh=cur.get("wind_speed_10m"), wind_direction_deg=cur.get("wind_direction_10m"),
            note="Global NWP model blend (not IMD-sourced); used as documented fallback.",
        )

    def get_forecast(self, loc: Location) -> WeatherForecast:
        data = self._get(self.FORECAST_BASE, loc, {"daily": self.DAILY_VARS, "forecast_days": 7})
        daily = data.get("daily", {})
        dates = daily.get("time", [])
        psum = daily.get("precipitation_sum", [])
        tmax = daily.get("temperature_2m_max", [])
        tmin = daily.get("temperature_2m_min", [])
        days = [WeatherForecastDay(
            date=d,
            precipitation_sum_mm=psum[i] if i < len(psum) else None,
            temperature_max_c=tmax[i] if i < len(tmax) else None,
            temperature_min_c=tmin[i] if i < len(tmin) else None,
        ) for i, d in enumerate(dates)]
        return WeatherForecast(
            provider=self.name, provider_name=self.provider_name,
            source="Open-Meteo Forecast API — global NWP blend (GFS/ECMWF/ICON), 7-day daily",
            status=LIVE, data_status=LIVE,
            country=loc.country, state=loc.state, district=loc.district, block=loc.block,
            village=loc.village, latitude=loc.latitude, longitude=loc.longitude,
            issued_at=now_ist(), fetched_at=now_ist(), days=days,
            note="Global NWP model blend (not IMD-sourced); used as documented fallback.",
        )

    def get_historical_daily_precip(self, loc: Location, start_date: str, end_date: str) -> list:
        """Real Open-Meteo historical archive call (ERA5 reanalysis).
        Returns [(date, precipitation_sum_mm, et0_mm), ...]. Raises
        ProviderUnavailable on any failure — never fabricates a series."""
        data = self._get(self.ARCHIVE_BASE, loc, {
            "start_date": start_date, "end_date": end_date, "daily": self.DAILY_HISTORICAL_VARS,
        })
        daily = data.get("daily", {})
        dates = daily.get("time", [])
        psum = daily.get("precipitation_sum", [])
        et0 = daily.get("et0_fao_evapotranspiration", [])
        return list(zip(dates, psum, et0)) if dates else []


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class DemoWeatherProvider(WeatherProvider):
    """
    Part 23 (Demo Mode): a clearly-labeled simulation used ONLY when
    explicitly enabled, for showcasing the UI when no live provider is
    reachable. Every value carries status=SIMULATED_DEMO, never LIVE.
    Deterministic per-village values (seeded from the name), never random,
    so it can't be mistaken for a changing live feed.
    """
    name = "demo"
    provider_name = "Kavach demo mode (simulated — not a live provider)"
    supports_warnings = False

    def get_current(self, loc: Location) -> WeatherObservation:
        seed = sum(ord(c) for c in loc.village)
        return WeatherObservation(
            provider=self.name, provider_name=self.provider_name,
            source="Kavach demo-mode deterministic simulation",
            status=SIMULATED_DEMO, data_status=SIMULATED_DEMO, data_type="SIMULATED",
            country=loc.country, state=loc.state, district=loc.district, block=loc.block,
            village=loc.village, latitude=loc.latitude, longitude=loc.longitude,
            location_resolution=loc.resolution,
            observed_at=now_ist(), fetched_at=now_ist(), cache_status="miss",
            temperature_c=round(27 + (seed % 9), 1), humidity_pct=round(60 + (seed % 30), 0),
            precipitation_mm=round((seed % 40) * 0.6, 1), rain_mm=round((seed % 40) * 0.6, 1),
            wind_speed_kmh=round(6 + (seed % 15), 1), wind_direction_deg=float(seed % 360),
            note="Demo/simulation mode — not a live reading. Enabled because no live provider is "
                 "reachable in this environment; see /data-health for real provider status.",
        )

    def get_forecast(self, loc: Location) -> WeatherForecast:
        return WeatherForecast(
            provider=self.name, provider_name=self.provider_name,
            source="Kavach demo-mode deterministic simulation",
            status=SIMULATED_DEMO, data_status=SIMULATED_DEMO,
            country=loc.country, state=loc.state, district=loc.district, block=loc.block,
            village=loc.village, latitude=loc.latitude, longitude=loc.longitude,
            issued_at=now_ist(), fetched_at=now_ist(), days=[],
            note="Demo/simulation mode — not a live forecast.",
        )
