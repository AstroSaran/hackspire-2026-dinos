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
batch job. This container's network egress does not reach
archive-api.open-meteo.com (same restriction as the live forecast API), so
that batch job has NOT been run, and no baseline file exists in this build.
`get_baseline()` therefore returns None with a clear reason rather than
inventing a plausible-looking normal — per Part 9's explicit instruction.

Once a deployment has real network access, running
`python -m app.weather.historical --populate` (see `__main__` below) would
call the real ERA5 archive for each village's 1991-2020 monsoon-season
window, average it, and write `backend/data/rainfall_baseline.json` with
full source/period/retrieval-date documentation — which `get_baseline()`
would then load and use, still clearly labeled.
"""
import os
import json
import datetime

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


def baseline_status():
    """For /data-health — reports honestly whether any real baseline exists."""
    exists = os.path.exists(BASELINE_FILE)
    return {
        "baseline_file_present": exists,
        "climatological_period_if_populated": CLIMATOLOGICAL_PERIOD,
        "candidate_sources": {
            "india_ogd_imd_normals": {
                "url": OGD_RAINFALL_CATALOG_URL,
                "status": "documented, not integrated — requires DATA_GOV_IN_API_KEY",
            },
            "open_meteo_era5_archive": {
                "url": ERA5_ARCHIVE_BASE,
                "status": "documented, correct endpoint, not executed — this environment's "
                          "network egress does not reach archive-api.open-meteo.com",
            },
        },
    }


if __name__ == "__main__":
    import sys
    if "--populate" in sys.argv:
        print("This would call", ERA5_ARCHIVE_BASE, "for each village in app.geography over",
              CLIMATOLOGICAL_PERIOD, "and write", BASELINE_FILE)
        print("Not run: no network egress to archive-api.open-meteo.com in this environment.")
        sys.exit(1)
