"""
Kavach — Historical Rainfall Baseline
========================================
Part 8/9/10: a defensible rainfall anomaly requires a real historical
baseline. Two real, official candidate sources were investigated for this
build:

  1. India Open Government Data platform (data.gov.in / ap.data.gov.in),
     "Rainfall" catalogue — confirmed to actually host "daily Normal
     rainfall as per the IMD up to the district level" (official OGD
     description, NDSAP-licensed). This is the preferred source when
     available: it is IMD's own published normal, not a model reanalysis.
     Accessing it programmatically requires registering for a free
     data.gov.in API key (DATA_GOV_IN_API_KEY) and is NOT wired up in this
     build — the key was not available in this development environment,
     and Part 10 requires "do not scrape random websites" / use the
     official access path only. See `fetch_ogd_district_normal()` below:
     it is a real, correctly-addressed stub that raises rather than
     fabricates until a key is configured.

  2. Open-Meteo's historical archive API (archive-api.open-meteo.com/v1/archive),
     ERA5 reanalysis, hourly, spatially complete, from January 1940 —
     confirmed via Open-Meteo's own official documentation. This is a
     legitimate, official, keyless alternative when OGD access isn't
     configured, but it is REANALYSIS/MODEL data, not a direct ground
     station observation, and is labeled as such everywhere it appears
     (Part 8: "do not confuse reanalysis/historical model data with direct
     ground-station observations").

Computing a genuine climatological normal (e.g. 1991-2020) requires calling
the archive API across ~30 years of data and averaging — a real, one-time
batch job. No baseline file is assumed to ship with the code. A real
`--populate` operation is available below. The live API uses Windows' native
certificate store through truststore so managed system roots work with normal
TLS verification; certificate checks are never disabled.
"""
import os
import json
import datetime
import time
import truststore
truststore.inject_into_ssl()
import requests

HERE = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))  # backend/
BASELINE_FILE = os.path.join(HERE, "data", "rainfall_baseline.json")

OGD_RAINFALL_CATALOG_URL = "https://www.data.gov.in/catalog/rainfall"
ERA5_ARCHIVE_BASE = "https://archive-api.open-meteo.com/v1/archive"
CLIMATOLOGICAL_PERIOD = "1991-2020"  # only ever used as a LABEL once a real baseline is computed for it


class BaselineUnavailable(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def fetch_ogd_district_normal(district: str, api_key: str = None):
    """Real, correctly-addressed access path for India OGD's official
    district-level IMD normal-rainfall dataset. Requires a free data.gov.in
    API key (DATA_GOV_IN_API_KEY) which is not configured in this build.
    Raises rather than fabricating a normal."""
    if not api_key:
        raise BaselineUnavailable(
            "India OGD rainfall-normal dataset requires a data.gov.in API key "
            "(DATA_GOV_IN_API_KEY, not set) — see " + OGD_RAINFALL_CATALOG_URL
        )
    # Real integration point: data.gov.in's resource API
    # (api.data.gov.in/resource/{resource_id}?api-key=...&format=json&filters[district]=...)
    # is not called here because no key is available in this environment;
    # this function exists so the moment a key is supplied, an engineer
    # wires the actual request rather than this raising indefinitely.
    raise BaselineUnavailable("OGD API key present but request not yet implemented against a confirmed resource_id")




def fetch_era5_daily_baseline(latitude: float, longitude: float, period_start="1991-01-01", period_end="2020-12-31"):
    """Fetch a real ERA5 daily precipitation baseline for a selected grid point."""
    key = f"grid:{latitude:.6f},{longitude:.6f}"
    data = {}
    if os.path.exists(BASELINE_FILE):
        try:
            with open(BASELINE_FILE) as f: data = json.load(f)
        except Exception: data = {}
    if key in data:
        return data[key]
    params = {
        "latitude": latitude, "longitude": longitude,
        "start_date": period_start, "end_date": period_end,
        "daily": "precipitation_sum", "timezone": "Asia/Kolkata",
    }
    r = requests.get(ERA5_ARCHIVE_BASE, params=params, timeout=30)
    r.raise_for_status()
    payload = r.json()
    vals = [v for v in (payload.get("daily", {}).get("precipitation_sum") or []) if v is not None]
    if not vals:
        raise BaselineUnavailable("ERA5 returned no daily precipitation values")
    baseline = {
        "mean_mm": round(sum(vals) / len(vals), 3),
        "period": f"{period_start[:4]}-{period_end[:4]}",
        "source": "Open-Meteo ERA5 reanalysis daily precipitation",
        "computed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "sample_days": len(vals),
        "latitude": latitude, "longitude": longitude,
    }
    data[key] = baseline
    os.makedirs(os.path.dirname(BASELINE_FILE), exist_ok=True)
    with open(BASELINE_FILE, "w") as f: json.dump(data, f, indent=2)
    return baseline


def fetch_era5_monthly_daily_baseline(latitude: float, longitude: float, month: int, period_start="1991-01-01", period_end="2020-12-31"):
    """Real ERA5 daily precipitation mean for one calendar month at a selected grid point."""
    key = f"grid-month:{latitude:.6f},{longitude:.6f}:{int(month):02d}"
    data = {}
    if os.path.exists(BASELINE_FILE):
        try:
            with open(BASELINE_FILE) as f: data = json.load(f)
        except Exception: data = {}
    if key in data:
        return data[key]
    params = {"latitude": latitude, "longitude": longitude, "start_date": period_start, "end_date": period_end,
              "daily": "precipitation_sum", "timezone": "Asia/Kolkata"}
    r = requests.get(ERA5_ARCHIVE_BASE, params=params, timeout=30); r.raise_for_status()
    payload = r.json(); dates = payload.get("daily", {}).get("time") or []; vals = payload.get("daily", {}).get("precipitation_sum") or []
    selected = [float(v) for d,v in zip(dates, vals) if v is not None and int(d[5:7]) == int(month)]
    if not selected: raise BaselineUnavailable(f"ERA5 returned no daily precipitation values for month {month}")
    baseline = {"mean_mm": round(sum(selected)/len(selected), 3), "period": f"{period_start[:4]}-{period_end[:4]}",
                "month": int(month), "source": "Open-Meteo ERA5 reanalysis daily precipitation",
                "computed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "sample_days": len(selected),
                "latitude": latitude, "longitude": longitude}
    data[key]=baseline; os.makedirs(os.path.dirname(BASELINE_FILE), exist_ok=True)
    with open(BASELINE_FILE,"w") as f: json.dump(data,f,indent=2)
    return baseline


def get_baseline(district: str, block: str):
    """Returns the cached, real baseline for this location if one has been
    computed and stored, else None. NEVER computes a plausible-looking
    number on the fly."""
    if not os.path.exists(BASELINE_FILE):
        return None
    try:
        with open(BASELINE_FILE) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    return data.get(f"{district}:{block}")


def get_grid_monthly_normals(latitude: float, longitude: float):
    """Return all twelve cached real month normals for a selected grid point."""
    if not os.path.exists(BASELINE_FILE):
        return None
    try:
        with open(BASELINE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        keys = {str(month): data[f"grid-month:{latitude:.6f},{longitude:.6f}:{month:02d}"]
                for month in range(1, 13)}
    except (json.JSONDecodeError, OSError, KeyError):
        return None
    return keys


def baseline_status():
    """For /data-health — reports honestly whether any real baseline exists."""
    try:
        with open(BASELINE_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        data = {}
    return {
        "baseline_file_present": bool(data),
        "cached_grid_count": len({key.split(":", 1)[1] for key in data if key.startswith("grid:")}),
        "climatological_period_if_populated": CLIMATOLOGICAL_PERIOD,
        "selected_grid_monthly_normals": None,
        "candidate_sources": {
            "india_ogd_imd_normals": {
                "url": OGD_RAINFALL_CATALOG_URL,
                "status": "documented, not integrated — requires DATA_GOV_IN_API_KEY",
            },
            "open_meteo_era5_archive": {
                "url": ERA5_ARCHIVE_BASE,
            "status": "real ERA5 archive integration available; retrieve with `python -m app.weather.historical --populate`; no baseline is bundled",
            },
        },
    }


if __name__ == "__main__":
    import sys
    if "--populate" in sys.argv:
        if len(sys.argv) < 4:
            print("Usage: python -m app.weather.historical --populate LATITUDE LONGITUDE")
            sys.exit(2)
        latitude, longitude = float(sys.argv[2]), float(sys.argv[3])
        failures = 0
        for month in range(1, 13):
            try:
                result = fetch_era5_monthly_daily_baseline(latitude, longitude, month)
                print(f"OK month={month:02d} mean_daily_rainfall_mm={result['mean_mm']} "
                      f"period={result['period']} source={result['source']}")
            except (BaselineUnavailable, requests.RequestException, ValueError) as exc:
                print(f"FAILED month={month:02d}: {exc}")
                failures += 1
                break
        sys.exit(1 if failures else 0)
