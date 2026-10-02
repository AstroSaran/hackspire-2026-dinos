import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from app import geography
from app import collect_historical_weather as collector


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
        self.content = json.dumps(payload, sort_keys=True).encode("utf-8")

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def _points():
    return [{
        "district": district, "latitude": 20.0 + index / 10,
        "longitude": 85.0 + index / 10,
    } for index, district in enumerate(geography.DISTRICT_HQ_QUERIES)]


def _archive_payload(points, days=("2024-01-01", "2024-01-02"), *, precipitation=1):
    return [{
        "latitude": point["latitude"], "longitude": point["longitude"],
        "daily": {
            "time": list(days),
            "temperature_2m_mean": [25.0] * len(days),
            "temperature_2m_max": [30.0] * len(days),
            "temperature_2m_min": [20.0] * len(days),
            "precipitation_sum": [precipitation] * len(days),
            "wind_speed_10m_max": [10.0] * len(days),
            "et0_fao_evapotranspiration": [2.0] * len(days),
        },
    } for point in points]


class FakeArchiveSession:
    def __init__(self, payload):
        self.payload = payload
        self.urls = []

    def get(self, url, **kwargs):
        self.urls.append(url)
        return FakeResponse(self.payload)


def test_collection_window_respects_date_and_api_quota_caps():
    with pytest.raises(collector.CollectionError, match="capped at eight"):
        collector._validate_dates("2017-01-01", "2025-01-01")
    with pytest.raises(collector.CollectionError, match="on or before"):
        collector._validate_dates("2024-02-01", "2024-01-31")
    with pytest.raises(collector.CollectionError, match="future"):
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        collector._validate_dates(tomorrow, tomorrow)


def test_multi_district_historical_response_normalizes_without_imputation():
    points = _points()
    session = FakeArchiveSession(_archive_payload(points))

    raw, rows = collector.fetch_era5_daily(points, "2024-01-01", "2024-01-02", session)

    assert raw
    assert len(rows) == 44
    assert rows[0]["district"] == points[0]["district"]
    assert rows[0]["precipitation_sum"] == 1.0
    assert rows[0]["source_model"] == "ERA5 reanalysis"
    assert len(session.urls) == 1


def test_incomplete_location_payload_is_rejected():
    points = _points()
    session = FakeArchiveSession(_archive_payload(points[:-1]))

    with pytest.raises(collector.CollectionError, match="different number of locations"):
        collector.fetch_era5_daily(points, "2024-01-01", "2024-01-02", session)


def test_implausible_feature_value_is_rejected():
    points = _points()
    session = FakeArchiveSession(_archive_payload(points, precipitation=-1.0))

    with pytest.raises(collector.CollectionError, match="implausible precipitation_sum"):
        collector.fetch_era5_daily(points, "2024-01-01", "2024-01-02", session)


def test_collection_writes_immutable_raw_processed_and_provenance(tmp_path):
    points = _points()
    raw, rows = collector.fetch_era5_daily(
        points, "2024-01-01", "2024-01-02", FakeArchiveSession(_archive_payload(points))
    )
    dirs = (tmp_path / "raw", tmp_path / "processed", tmp_path / "metadata")
    manifest = collector.write_collection(
        raw, rows, points, "2024-01-01", "2024-01-02", *dirs,
        collected_at="2024-01-03T00:00:00+00:00",
    )

    assert manifest["records"]["count"] == 44
    assert manifest["manifest_schema_version"] == collector.COLLECTION_MANIFEST_VERSION
    assert manifest["quality"]["status"] == "PASS"
    assert manifest["quality"]["duplicate_district_dates"] == 0
    assert manifest["model_readiness"]["outcome_labels_included"] is False
    assert manifest["source"]["license"].startswith("CC-BY-4.0")
    for key in ("raw_file", "processed_file"):
        assert Path(manifest["provenance"][key]).is_file()
    assert list(dirs[0].glob("*.json"))
    assert list(dirs[1].glob("*.csv"))
    manifest_path = next(dirs[2].glob("*.json"))
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["dataset_version"] == manifest["dataset_version"]

    different_raw = raw + b"\n"
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        collector._write_immutable(next(dirs[0].glob("*.json")), different_raw)


def test_district_geocoder_uses_only_cached_state_confirmed_fallbacks(tmp_path, monkeypatch):
    fallback_cache = tmp_path / "osm-cache.json"
    cached_results = {}
    missing_geocoders = {"Alipurduar", "Murshidabad", "Hooghly"}
    search_to_district = {search: district for district, search in geography.DISTRICT_HQ_QUERIES.items()}
    for district in missing_geocoders:
        cached_results[district] = {
            "place_name": district, "latitude": 25.0, "longitude": 88.0,
            "address": {"state": "West Bengal", "country": "India", "state_district": district},
        }
    fallback_cache.write_text(json.dumps({"results": cached_results}), encoding="utf-8")
    monkeypatch.setattr(collector, "GEOCODING_FALLBACK_CACHE", fallback_cache)

    class FakeGeocoderSession:
        def get(self, url, *, params, **kwargs):
            search_label = params["name"].split(",", 1)[0]
            district = search_to_district[search_label]
            results = [] if district in missing_geocoders else [{
                "name": search_label, "latitude": 23.0, "longitude": 88.0,
                "country_code": "IN", "admin1": "West Bengal",
            }]
            return FakeResponse({"results": results})

    points = collector.resolve_district_points(FakeGeocoderSession())

    assert len(points) == 22
    assert sum("OpenStreetMap" in point["geocoding_source"] for point in points) == 3
    assert all(point["geocoding_attribution"] for point in points)


def test_same_date_range_uses_saved_snapshot_without_another_api_call(tmp_path):
    points = _points()
    raw, rows = collector.fetch_era5_daily(
        points, "2024-01-01", "2024-01-02", FakeArchiveSession(_archive_payload(points))
    )
    dirs = (tmp_path / "raw", tmp_path / "processed", tmp_path / "metadata")
    collector.write_collection(raw, rows, points, "2024-01-01", "2024-01-02", *dirs)

    class NetworkMustNotBeUsed:
        def get(self, *args, **kwargs):
            raise AssertionError("A cached collection should avoid provider calls.")

    cached = collector.collect(
        "2024-01-01", "2024-01-02", session=NetworkMustNotBeUsed(), output_dirs=dirs
    )

    assert cached["records"]["count"] == 44
    assert cached["manifest_file"]
    assert cached["collection_action"] == "REUSED_VERSIONED_SNAPSHOT"
