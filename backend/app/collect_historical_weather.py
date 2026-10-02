"""Collect a bounded, real ERA5 daily climate feature snapshot for West Bengal.

Run from ``backend`` with:
    python -m app.collect_historical_weather

The free Open-Meteo API is limited to non-commercial use. This collector caps a
run at eight calendar years for 22 locations, captures raw JSON immutably, and
does not present district-headquarters grid points as district-wide values.
The output is predictor data only; it contains no crop-stress or livelihood
outcome labels and must not be used to claim a trained risk model.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import truststore

truststore.inject_into_ssl()

import requests

from . import geography


BACKEND_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_DIR = BACKEND_DIR.parent
RAW_DIR = BACKEND_DIR / "data" / "raw"
PROCESSED_DIR = BACKEND_DIR / "data" / "processed"
METADATA_DIR = BACKEND_DIR / "data" / "metadata"
GEOCODING_FALLBACK_CACHE = METADATA_DIR / "wb_district_geocoding_fallbacks.json"
GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
DAILY_VARIABLES = (
    "temperature_2m_mean", "temperature_2m_max", "temperature_2m_min",
    "precipitation_sum", "wind_speed_10m_max", "et0_fao_evapotranspiration",
)
DAILY_UNITS = {
    "temperature_2m_mean": "°C", "temperature_2m_max": "°C", "temperature_2m_min": "°C",
    "precipitation_sum": "mm", "wind_speed_10m_max": "km/h",
    "et0_fao_evapotranspiration": "mm",
}
MAX_CALENDAR_YEARS = 8
COLLECTION_MANIFEST_VERSION = 2


class CollectionError(RuntimeError):
    """Raised when a complete valid source response cannot be collected."""


def _repo_path(path: Path) -> str:
    try:
        return Path(path).resolve().relative_to(REPOSITORY_DIR.resolve()).as_posix()
    except ValueError:
        return str(Path(path).resolve())


def _validate_dates(start_date: str, end_date: str) -> tuple[date, date]:
    try:
        start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    except ValueError as exc:
        raise CollectionError("Dates must use ISO format YYYY-MM-DD.") from exc
    if start > end:
        raise CollectionError("Start date must be on or before end date.")
    if end > date.today():
        raise CollectionError("Historical collection end date cannot be in the future.")
    if end.year - start.year + 1 > MAX_CALENDAR_YEARS:
        raise CollectionError("One collection run is capped at eight calendar years to respect free API usage limits.")
    return start, end


def resolve_district_points(session=requests) -> list[dict]:
    try:
        fallback_cache = json.loads(GEOCODING_FALLBACK_CACHE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        fallback_cache = {"results": {}}
    points = []
    for district, search_label in geography.DISTRICT_HQ_QUERIES.items():
        try:
            response = session.get(GEOCODING_URL, params={
                "name": f"{search_label}, West Bengal, India", "count": 10,
                "language": "en", "format": "json",
            }, timeout=15)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise CollectionError(f"Geocoding failed for {district} ({type(exc).__name__}); no dataset was written.") from exc
        results = payload.get("results", []) if isinstance(payload, dict) else []
        match = next((item for item in results
                      if str(item.get("country_code", "")).upper() == "IN"
                      and str(item.get("admin1", "")).strip().casefold() == "west bengal"), None)
        if match:
            point_latitude, point_longitude = match.get("latitude"), match.get("longitude")
            place_name = str(match.get("name", ""))
            geocoding_source = GEOCODING_URL
            geocoding_attribution = "Open-Meteo Geocoding API"
            geocoding_resolution = "Open-Meteo geocoder-confirmed district-headquarters search point; not a district polygon or average"
        else:
            cached = fallback_cache.get("results", {}).get(district)
            address = cached.get("address", {}) if isinstance(cached, dict) else {}
            if (not cached or str(address.get("state", "")).casefold() != "west bengal"
                    or str(address.get("country", "")).casefold() != "india"
                    or str(address.get("state_district", "")).casefold() != district.casefold()):
                raise CollectionError(f"No cached, district-matched West Bengal fallback for {district}; no dataset was written.")
            point_latitude, point_longitude = cached.get("latitude"), cached.get("longitude")
            place_name = str(cached.get("place_name", ""))
            geocoding_source = "OpenStreetMap Nominatim (cached one-time fallback)"
            geocoding_attribution = fallback_cache.get("attribution", "© OpenStreetMap contributors")
            geocoding_resolution = "Cached OSM place search point confirmed within the named West Bengal district; not a district polygon or average"
        try:
            latitude, longitude = float(point_latitude), float(point_longitude)
        except (KeyError, TypeError, ValueError) as exc:
            raise CollectionError(f"Geocoder returned invalid coordinates for {district}; no dataset was written.") from exc
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            raise CollectionError(f"Geocoder returned out-of-range coordinates for {district}; no dataset was written.")
        points.append({
            "district": district,
            "search_label": search_label,
            "place_name": place_name,
            "latitude": latitude,
            "longitude": longitude,
            "resolution": geocoding_resolution,
            "geocoding_source": geocoding_source,
            "geocoding_attribution": geocoding_attribution,
        })
    if len(points) != len(geography.DISTRICT_HQ_QUERIES):
        raise CollectionError("Incomplete district geocoding; no dataset was written.")
    return points


def fetch_era5_daily(points: list[dict], start_date: str, end_date: str, session=requests) -> tuple[bytes, list[dict]]:
    _validate_dates(start_date, end_date)
    if len(points) != len(geography.DISTRICT_HQ_QUERIES):
        raise CollectionError("Expected geocoder-confirmed points for all 22 published districts.")
    params = {
        "latitude": ",".join(str(point["latitude"]) for point in points),
        "longitude": ",".join(str(point["longitude"]) for point in points),
        "start_date": start_date,
        "end_date": end_date,
        "daily": ",".join(DAILY_VARIABLES),
        "timezone": "Asia/Kolkata",
        "models": "era5",
        "format": "json",
    }
    try:
        response = session.get(ARCHIVE_URL, params=params, timeout=180)
        response.raise_for_status()
        raw_content = response.content
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise CollectionError(f"ERA5 archive request failed ({type(exc).__name__}); no dataset was written.") from exc
    if isinstance(payload, dict):
        payloads = [payload]
    elif isinstance(payload, list):
        payloads = payload
    else:
        raise CollectionError("ERA5 returned an unexpected response type; no dataset was written.")
    if len(payloads) != len(points):
        raise CollectionError("ERA5 returned a different number of locations; no dataset was written.")

    processed = []
    for point, location in zip(points, payloads):
        if not isinstance(location, dict) or location.get("error"):
            raise CollectionError(f"ERA5 returned an invalid location response for {point['district']}.")
        daily = location.get("daily", {})
        days = daily.get("time", [])
        if not isinstance(days, list) or not days:
            raise CollectionError(f"ERA5 returned no daily observations for {point['district']}.")
        expected_days = (date.fromisoformat(end_date) - date.fromisoformat(start_date)).days + 1
        expected_date_set = {
            (date.fromisoformat(start_date) + timedelta(days=index)).isoformat()
            for index in range(expected_days)
        }
        if len(days) != expected_days or len(set(days)) != expected_days or set(days) != expected_date_set:
            raise CollectionError(f"ERA5 dates are missing, duplicated, or out of requested coverage for {point['district']}.")
        arrays = {name: daily.get(name) for name in DAILY_VARIABLES}
        if any(not isinstance(values, list) or len(values) != len(days) for values in arrays.values()):
            raise CollectionError(f"ERA5 response schema is incomplete for {point['district']}.")
        for index, day in enumerate(days):
            try:
                parsed_day = date.fromisoformat(day)
            except (TypeError, ValueError) as exc:
                raise CollectionError(f"ERA5 returned an invalid date for {point['district']}.") from exc
            if not date.fromisoformat(start_date) <= parsed_day <= date.fromisoformat(end_date):
                raise CollectionError(f"ERA5 returned a date outside the requested range for {point['district']}.")
            record = {
                "state": "West Bengal", "district": point["district"], "date": day,
                "latitude": point["latitude"], "longitude": point["longitude"],
                "provider_grid_latitude": location.get("latitude"),
                "provider_grid_longitude": location.get("longitude"),
                "source_model": "ERA5 reanalysis",
            }
            for name, values in arrays.items():
                value = values[index]
                if value is not None:
                    try:
                        numeric = float(value)
                    except (TypeError, ValueError) as exc:
                        raise CollectionError(f"ERA5 returned a non-numeric {name} value for {point['district']}.") from exc
                    if not math.isfinite(numeric):
                        raise CollectionError(f"ERA5 returned a non-finite {name} value for {point['district']}.")
                    bounds = {
                        "temperature_2m_mean": (-70, 60), "temperature_2m_max": (-70, 60),
                        "temperature_2m_min": (-70, 60), "precipitation_sum": (0, 1500),
                        "wind_speed_10m_max": (0, 500), "et0_fao_evapotranspiration": (0, 100),
                    }[name]
                    if not bounds[0] <= numeric <= bounds[1]:
                        raise CollectionError(f"ERA5 returned an implausible {name} value for {point['district']}.")
                    record[name] = numeric
                else:
                    record[name] = None
            processed.append(record)
    expected_rows = len(points) * ((date.fromisoformat(end_date) - date.fromisoformat(start_date)).days + 1)
    if len(processed) != expected_rows:
        raise CollectionError("ERA5 daily coverage is incomplete; no dataset was written.")
    for record in processed:
        values = [record[name] for name in ("temperature_2m_min", "temperature_2m_mean", "temperature_2m_max")]
        if all(value is not None for value in values) and not values[0] <= values[1] <= values[2]:
            raise CollectionError(f"ERA5 temperature ordering is invalid for {record['district']} on {record['date']}.")
    return raw_content, processed


def write_collection(raw_content: bytes, rows: list[dict], points: list[dict], start_date: str,
                     end_date: str, raw_dir: Path = RAW_DIR, processed_dir: Path = PROCESSED_DIR,
                     metadata_dir: Path = METADATA_DIR, collected_at: str | None = None) -> dict:
    raw_sha256 = hashlib.sha256(raw_content).hexdigest()
    csv_buffer = io.StringIO(newline="")
    fieldnames = [
        "state", "district", "date", "latitude", "longitude", "provider_grid_latitude",
        "provider_grid_longitude", "source_model", *DAILY_VARIABLES,
    ]
    writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    processed_bytes = csv_buffer.getvalue().encode("utf-8")
    processed_sha256 = hashlib.sha256(processed_bytes).hexdigest()
    collected_at = collected_at or datetime.now(timezone.utc).isoformat()
    collection_id = f"era5-west-bengal-{start_date}-to-{end_date}-{raw_sha256[:16]}"

    raw_dir, processed_dir, metadata_dir = Path(raw_dir), Path(processed_dir), Path(metadata_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"{collection_id}.json"
    processed_path = processed_dir / f"{collection_id}.csv"
    manifest_path = metadata_dir / f"{collection_id}-manifest-v{COLLECTION_MANIFEST_VERSION}.json"
    manifest = {
        "manifest_schema_version": COLLECTION_MANIFEST_VERSION,
        "dataset_id": "west-bengal-district-daily-environmental-features",
        "dataset_version": f"sha256:{processed_sha256}",
        "collection_id": collection_id,
        "collected_at_utc": collected_at,
        "source": {
            "provider": "Open-Meteo Historical Weather API",
            "api_url": ARCHIVE_URL,
            "model": "ERA5 reanalysis",
            "underlying_source": "ECMWF ERA5 historical reanalysis",
            "attribution": "Data: Open-Meteo Historical Weather API and ECMWF ERA5. Licensed under CC BY 4.0; indicate modifications and cite Open-Meteo/ECMWF.",
            "license": "CC-BY-4.0; Free API service terms limit free use to non-commercial purposes.",
            "usage_scope_warning": "For a commercial deployment, use an API plan appropriate to the intended use and confirm source/model terms before redistribution.",
            "observation_type": "Reanalysis model estimates informed by observations; not a station measurement or district-mean field.",
            "geocoding_provider": "Open-Meteo Geocoding API",
            "geocoding_fallback": {
                "provider": "OpenStreetMap Nominatim",
                "license": "ODbL 1.0",
                "attribution": "© OpenStreetMap contributors",
                "cache_file": _repo_path(GEOCODING_FALLBACK_CACHE),
                "use": "Three cached point results for districts absent from the primary geocoder; no repeated Nominatim calls.",
            },
        },
        "request_parameters": {
            "start_date": start_date, "end_date": end_date,
            "model": "era5", "daily_variables": list(DAILY_VARIABLES),
            "timezone": "Asia/Kolkata", "format": "json",
            "location_order": "Matches the district order in coverage.locations; Open-Meteo multi-location API returns corresponding ordered results.",
        },
        "coverage": {
            "state": "West Bengal", "district_count": len(points),
            "districts": [point["district"] for point in points],
            "start_date": start_date, "end_date": end_date,
            "temporal_resolution": "daily", "timezone": "Asia/Kolkata",
            "location_method": "One live-geocoded district-headquarters search point per district.",
            "locations": points,
        },
        "schema": [{"name": name, "type": "string" if name in {"state", "district", "date", "source_model"} else "float", "unit": DAILY_UNITS.get(name)} for name in fieldnames],
        "records": {"count": len(rows), "expected_rows": len(points) * ((date.fromisoformat(end_date) - date.fromisoformat(start_date)).days + 1),
                    "missing_values_by_feature": {name: sum(row[name] is None for row in rows) for name in DAILY_VARIABLES}},
        "provenance": {
            "raw_file": _repo_path(raw_path), "raw_sha256": raw_sha256,
            "processed_file": _repo_path(processed_path), "processed_sha256": processed_sha256,
            "transform": "Flattened provider daily arrays into one location-date row. No interpolation, imputation, aggregation across districts, or synthetic examples.",
        },
        "quality": {},
        "model_readiness": {
            "role": "predictor features only",
            "outcome_labels_included": False,
            "livelihood_model_training_allowed": False,
            "reason": "Environmental covariates do not label crop loss, MGNREGA access shortfall, household income loss, or livelihood disruption.",
        },
    }
    raw_path = _write_immutable(raw_path, raw_content)
    processed_path = _write_immutable(processed_path, processed_bytes)
    manifest["provenance"]["raw_file"] = _repo_path(raw_path)
    manifest["provenance"]["processed_file"] = _repo_path(processed_path)
    duplicates = len(rows) - len({(row["district"], row["date"]) for row in rows})
    all_districts = len({row["district"] for row in rows}) == len(points)
    expected_rows = len(points) * ((date.fromisoformat(end_date) - date.fromisoformat(start_date)).days + 1)
    row_count_ok = len(rows) == expected_rows
    missing_counts = manifest["records"]["missing_values_by_feature"]
    quality_checks = [
        {"id": "no_duplicate_district_dates", "status": "PASS" if duplicates == 0 else "FAIL", "count": duplicates},
        {"id": "all_requested_districts_present", "status": "PASS" if all_districts else "FAIL", "district_count": len({row['district'] for row in rows}), "expected_district_count": len(points)},
        {"id": "expected_location_date_row_count", "status": "PASS" if row_count_ok else "FAIL", "observed": len(rows), "expected": expected_rows},
        {"id": "daily_features_complete", "status": "PASS" if not any(missing_counts.values()) else "WARNING", "missing_values_by_feature": missing_counts},
    ]
    manifest["quality"] = {
        "status": "FAIL" if any(check["status"] == "FAIL" for check in quality_checks)
        else "PASS_WITH_WARNINGS" if any(check["status"] == "WARNING" for check in quality_checks)
        else "PASS",
        "checks": quality_checks,
        "duplicate_district_dates": duplicates,
        "all_requested_locations_returned": all_districts,
        "row_count_matches_location_date_coverage": row_count_ok,
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    manifest_path = _write_immutable(manifest_path, manifest_bytes)
    manifest["manifest_file"] = _repo_path(manifest_path)
    return manifest


def _write_immutable(path: Path, content: bytes) -> Path:
    try:
        with path.open("xb") as stream:
            stream.write(content)
    except FileExistsError:
        if path.read_bytes() != content:
            raise FileExistsError(f"Refusing to overwrite different data at {path}.")
    return path


def _existing_collection(start_date: str, end_date: str, metadata_dir: Path) -> dict | None:
    prefix = f"era5-west-bengal-{start_date}-to-{end_date}-"
    manifests = sorted(Path(metadata_dir).glob(f"{prefix}*-manifest-v*.json"),
                       key=lambda path: path.stat().st_mtime, reverse=True)
    for manifest_path in manifests:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if manifest.get("coverage", {}).get("start_date") == start_date and manifest.get("coverage", {}).get("end_date") == end_date:
            manifest["manifest_file"] = _repo_path(manifest_path)
            manifest["collection_action"] = "REUSED_VERSIONED_SNAPSHOT"
            return manifest
    return None


def collect(start_date: str = "2018-01-01", end_date: str = "2025-12-31", session=requests,
            output_dirs: tuple[Path, Path, Path] = (RAW_DIR, PROCESSED_DIR, METADATA_DIR),
            refresh: bool = False) -> dict:
    _validate_dates(start_date, end_date)
    if not refresh:
        cached = _existing_collection(start_date, end_date, output_dirs[2])
        if cached:
            return cached
    points = resolve_district_points(session)
    raw_content, rows = fetch_era5_daily(points, start_date, end_date, session)
    manifest = write_collection(raw_content, rows, points, start_date, end_date, *output_dirs)
    manifest["collection_action"] = "FETCHED_NEW_SNAPSHOT"
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", default="2018-01-01")
    parser.add_argument("--end-date", default="2025-12-31")
    parser.add_argument("--refresh", action="store_true", help="Fetch a new source snapshot despite an existing complete collection")
    args = parser.parse_args(argv)
    manifest = collect(args.start_date, args.end_date, refresh=args.refresh)
    print(json.dumps({
        "status": manifest["collection_action"],
        "dataset_version": manifest["dataset_version"],
        "records": manifest["records"]["count"],
        "coverage": manifest["coverage"]["start_date"] + " to " + manifest["coverage"]["end_date"],
        "raw_file": manifest["provenance"]["raw_file"],
        "processed_file": manifest["provenance"]["processed_file"],
        "manifest_file": manifest["manifest_file"],
        "livelihood_model_training_allowed": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
