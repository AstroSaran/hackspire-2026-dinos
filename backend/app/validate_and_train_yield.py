"""Build and evaluate a West Bengal district-season rice yield-shortfall model.

This is a separate experimental crop-outcome model. It does not alter DINOS's
six-feature livelihood interface or train on distress_cascade_label.

The target is an APY-observed Rice yield below 85% of the district/season mean
of the five immediately preceding agricultural years. Weather inputs are
daily Open-Meteo ERA5 reanalysis at 2011 district polygon centroids. For an
early-warning interpretation, rainfall and temperature stop before the usual
harvest month. The ERA5 values are reanalysis, not station observations.

Run from ``backend`` after placing the APY source CSV at
``data/raw/apy/crop-wise-area-production-yield.csv``::

    python -m app.validate_and_train_yield
    python -m app.validate_and_train_yield --skip-weather

1997-2025 spans 29 years, requiring four <=8-year chunks (8+8+8+5).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import time
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import requests
import truststore
import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import accuracy_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import make_pipeline

truststore.inject_into_ssl()

HERE = Path(__file__).resolve().parent
BACKEND_DIR = HERE.parent
REPO = BACKEND_DIR.parent
APY_FILE = BACKEND_DIR / "data" / "raw" / "apy" / "crop-wise-area-production-yield.csv"
OUT_DIR = BACKEND_DIR / "data" / "experimental" / "rice-yield-shortfall"
WEATHER_CACHE = OUT_DIR / "weather_chunks"
WEATHER_API = "https://archive-api.open-meteo.com/v1/archive"
BOUNDARY_QUERY = (
    "https://mapservice.gov.in/gismapservice/rest/services/"
    "BharatMapService/Admin_Boundary_District/MapServer/1/query"
)
WEATHER_COLUMNS = ["rainfall_mm", "wet_days_1mm", "max_7day_rainfall_mm", "mean_tmax_c"]
DISTRICT_ALIASES = {
    "Alipurduar": "Jalpaiguri",
    "Kalimpong": "Darjeeling",
    "Jhargram": "Paschim Medinipur",
    "Paschim Bardhaman": "Bardhaman",
    "Purba Bardhaman": "Bardhaman",
}
# West Bengal Rice seasons are named for harvest season. Use only weather before
# their usual harvest: Aus/Autumn sown Feb-Apr, Aman/Winter sown Jun-Jul, and
# Boro/Summer sown Nov-Jan. A crop-year is the first year in APY's YYYY-YY.
SEASON_WINDOW = {
    "Autumn": (lambda y: f"{y}-02-01", lambda y: f"{y}-06-30"),
    "Winter": (lambda y: f"{y}-06-01", lambda y: f"{y}-10-31"),
    "Summer": (lambda y: f"{y-1}-11-01", lambda y: f"{y}-04-30"),
}
FEATURES = WEATHER_COLUMNS
TARGET = "rice_yield_shortfall"


def canonical_district(value: object) -> str:
    value = " ".join(str(value).strip().split())
    return DISTRICT_ALIASES.get(value, value)


def parse_crop_year(value: object) -> int:
    text = str(value).strip()
    try:
        year = int(text[:4])
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Invalid APY agricultural year: {value!r}") from exc
    if not 1900 <= year <= 2100:
        raise ValueError(f"Invalid APY agricultural year: {value!r}")
    return year


def load_apy(path: Path = APY_FILE) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"APY input not found: {path}")
    raw = pd.read_csv(path, low_memory=False)
    required = {"state_name", "district_name", "crop_name", "year", "season", "area", "production", "yield"}
    missing = required - set(raw.columns)
    if missing:
        raise ValueError(f"APY file missing required columns: {sorted(missing)}")
    raw = raw[
        raw.state_name.astype("string").str.strip().str.casefold().eq("west bengal")
        & raw.crop_name.astype("string").str.strip().str.casefold().eq("rice")
        & ~raw.season.astype("string").str.strip().str.casefold().eq("total")
    ].copy()
    raw["crop_year"] = raw.year.map(parse_crop_year)
    raw["district"] = raw.district_name.map(canonical_district)
    raw["season"] = raw.season.astype("string").str.strip().str.title()
    raw = raw[raw.season.isin(SEASON_WINDOW)].copy()
    for col in ("area", "production", "yield"):
        raw[col] = pd.to_numeric(raw[col].astype("string").str.replace(",", "", regex=False), errors="coerce")
    raw = raw.dropna(subset=["district", "crop_year", "area", "production"])
    raw = raw[(raw.area > 0) & (raw.production >= 0)]
    # Adjacent districts are merged using additive APY area and production;
    # merged yield is never a simple/unweighted average of child yields.
    grouped = raw.groupby(["district", "crop_year", "season"], as_index=False).agg(
        area=("area", "sum"), production=("production", "sum"),
        source_rows=("district_name", "size"),
    )
    grouped["yield_t_ha"] = grouped.production / grouped.area
    if grouped.duplicated(["district", "crop_year", "season"]).any():
        raise ValueError("APY aggregation did not produce unique district/year/season rows")
    grouped = grouped.sort_values(["district", "season", "crop_year"]).reset_index(drop=True)
    # Require each of the five immediately previous agricultural years. A gap
    # must not silently turn this into a five-record mean over a longer period.
    lookup = {(r.district, r.season, int(r.crop_year)): float(r.yield_t_ha)
              for r in grouped.itertuples(index=False)}
    baselines: list[float] = []
    for r in grouped.itertuples(index=False):
        lagged = [lookup.get((r.district, r.season, y)) for y in range(int(r.crop_year) - 5, int(r.crop_year))]
        baselines.append(float(np.mean(lagged)) if all(v is not None and np.isfinite(v) for v in lagged) else np.nan)
    grouped["prior_5y_mean_yield_t_ha"] = baselines
    grouped[TARGET] = np.where(
        grouped.prior_5y_mean_yield_t_ha.notna(),
        grouped.yield_t_ha < 0.85 * grouped.prior_5y_mean_yield_t_ha,
        np.nan,
    )
    grouped[TARGET] = grouped[TARGET].astype("boolean")
    return grouped


def _ring_centroid(ring: list[list[float]]) -> tuple[float, float, float] | None:
    """Signed shoelace centroid in a West-Bengal local equirectangular plane."""
    r_earth, cos_lat0 = 6_371_000.0, math.cos(math.radians(24.5))
    points = [(math.radians(p[0]) * r_earth * cos_lat0, math.radians(p[1]) * r_earth)
              for p in ring if len(p) >= 2]
    if len(points) < 4:
        return None
    cross_sum = cx_sum = cy_sum = 0.0
    for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1]):
        cross = x1 * y2 - x2 * y1
        cross_sum += cross
        cx_sum += (x1 + x2) * cross
        cy_sum += (y1 + y2) * cross
    area = cross_sum / 2.0
    if abs(area) < 1e-5:
        return None
    return area, cx_sum / (6.0 * area), cy_sum / (6.0 * area)


def district_centroids(session: requests.Session | None = None) -> dict[str, tuple[float, float]]:
    """Fetch official district polygons; dissolve post-2011 splits by aliases."""
    session = session or requests.Session()
    response = session.get(BOUNDARY_QUERY, params={
        "where": "stname='West Bengal'", "outFields": "dtname,stname,dtcode11,year_stat",
        "returnGeometry": "true", "outSR": "4326", "f": "json",
    }, timeout=90)
    response.raise_for_status()
    payload = response.json()
    if payload.get("error") or not isinstance(payload.get("features"), list):
        raise ValueError("Official district boundary service returned no feature list")
    moments: dict[str, list[float]] = {}
    for feature in payload["features"]:
        attrs, rings = feature.get("attributes", {}), feature.get("geometry", {}).get("rings", [])
        if attrs.get("stname", "").casefold() != "west bengal" or not rings:
            continue
        district = canonical_district(attrs.get("dtname", ""))
        moment = moments.setdefault(district, [0.0, 0.0, 0.0])
        for ring in rings:
            value = _ring_centroid(ring)
            if value:
                area, cx, cy = value
                moment[0] += area
                moment[1] += area * cx
                moment[2] += area * cy
    result = {}
    for district, (area, cx, cy) in moments.items():
        if abs(area) < 1e-5:
            continue
        longitude = math.degrees((cx / area) / (6_371_000.0 * math.cos(math.radians(24.5))))
        latitude = math.degrees((cy / area) / 6_371_000.0)
        if not (20.5 <= latitude <= 27.5 and 85.0 <= longitude <= 90.0):
            raise ValueError(f"Computed centroid for {district} is outside West Bengal bounds: {latitude:.4f}, {longitude:.4f}")
        result[district] = (latitude, longitude)
    if len(result) < 18:
        raise ValueError(f"Boundary response yielded only {len(result)} usable district centroids")
    return result


def chunks(start_year: int, end_year: int, size: int = 8) -> list[tuple[int, int]]:
    if size < 1 or end_year < start_year:
        raise ValueError("Invalid weather chunk range")
    return [(y, min(y + size - 1, end_year)) for y in range(start_year, end_year + 1, size)]


def _cache_name(district: str, start: int, end: int) -> Path:
    slug = "_".join(district.casefold().split())
    return WEATHER_CACHE / f"{slug}_{start}_{end}.csv"


def fetch_weather_chunks(start_year: int = 1997, end_year: int = 2025,
                         session: requests.Session | None = None) -> tuple[pd.DataFrame, dict]:
    session = session or requests.Session()
    WEATHER_CACHE.mkdir(parents=True, exist_ok=True)
    points = district_centroids(session)
    requested_chunks = chunks(start_year, end_year, 8)
    records: list[pd.DataFrame] = []
    fetched, reused, failures = 0, 0, []
    districts = sorted(points.items())
    for first, last in requested_chunks:
        missing_points = []
        for district, (lat, lon) in districts:
            cache = _cache_name(district, first, last)
            if cache.is_file():
                frame = pd.read_csv(cache, parse_dates=["date"])
                if len(frame) and {"date", "rainfall_mm", "tmax_c"}.issubset(frame.columns):
                    records.append(frame)
                    reused += 1
                    continue
            missing_points.append((district, lat, lon, cache))
        if not missing_points:
            continue
        params = {
            # Open-Meteo supports comma-separated locations in one response;
            # batching keeps the free public archive below request-rate limits.
            "latitude": ",".join(f"{lat:.6f}" for _, lat, _, _ in missing_points),
            "longitude": ",".join(f"{lon:.6f}" for _, _, lon, _ in missing_points),
            "start_date": f"{first}-01-01", "end_date": f"{last}-12-31",
            "daily": "precipitation_sum,temperature_2m_max",
            "timezone": "Asia/Kolkata",
        }
        try:
            response = None
            for attempt in range(5):
                response = session.get(WEATHER_API, params=params, timeout=180)
                if response.status_code != 429 and response.status_code < 500:
                    break
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = min(120, max(10, int(retry_after))) if retry_after else min(120, 15 * (attempt + 1))
                except ValueError:
                    delay = min(120, 15 * (attempt + 1))
                time.sleep(delay)
            assert response is not None
            response.raise_for_status()
            payload = response.json()
            locations = payload if isinstance(payload, list) else [payload]
            if len(locations) != len(missing_points):
                raise ValueError(f"ERA5 returned {len(locations)} locations for {len(missing_points)} requested districts")
            for (district, lat, lon, cache), location in zip(missing_points, locations):
                daily = location.get("daily", {})
                dates = daily.get("time", [])
                rain, tmax = daily.get("precipitation_sum", []), daily.get("temperature_2m_max", [])
                if not dates or len(dates) != len(rain) or len(dates) != len(tmax):
                    failures.append({"district": district, "chunk": [first, last],
                                     "error": "InvalidResponse", "detail": "ERA5 response had missing/inconsistent daily arrays"})
                    continue
                frame = pd.DataFrame({"district": district, "date": pd.to_datetime(dates),
                                      "rainfall_mm": rain, "tmax_c": tmax,
                                      "latitude": lat, "longitude": lon})
                frame.to_csv(cache, index=False)
                records.append(frame)
                fetched += 1
        except (requests.RequestException, ValueError, KeyError) as exc:
            for district, _, _, _ in missing_points:
                failures.append({"district": district, "chunk": [first, last],
                                 "error": type(exc).__name__, "detail": str(exc)[:300]})
    if not records:
        return pd.DataFrame(columns=["district", "date", "rainfall_mm", "tmax_c", "latitude", "longitude"]), {
            "district_count": len(points), "chunks_per_district": len(requested_chunks),
            "fetched_chunks": fetched, "cached_chunks_reused": reused, "failures": failures,
            "coverage_start": None, "coverage_end": None,
        }
    weather = pd.concat(records, ignore_index=True)
    weather["date"] = pd.to_datetime(weather["date"], errors="coerce")
    weather["rainfall_mm"] = pd.to_numeric(weather.rainfall_mm, errors="coerce")
    weather["tmax_c"] = pd.to_numeric(weather.tmax_c, errors="coerce")
    weather = weather.dropna(subset=["district", "date"]).drop_duplicates(["district", "date"])
    report = {
        "district_count": len(points), "districts": sorted(points),
        "district_centroid_source": BOUNDARY_QUERY,
        "district_centroid_method": "area-weighted polygon centroids from Government of India district boundary service; 2011 split districts dissolved per configured aliases; local equirectangular projection",
        "chunks": requested_chunks, "chunks_per_district": len(requested_chunks),
        "maximum_chunk_years": max(b - a + 1 for a, b in requested_chunks),
        "fetched_chunks": fetched, "cached_chunks_reused": reused, "failures": failures,
        "weather_source": WEATHER_API, "weather_product": "ERA5 reanalysis daily precipitation and maximum temperature",
        "weather_is_station_observation": False,
        "daily_rows": int(len(weather)), "coverage_start": str(weather.date.min().date()),
        "coverage_end": str(weather.date.max().date()),
    }
    return weather, report


def build_weather_features(weather: pd.DataFrame, apy: pd.DataFrame) -> pd.DataFrame:
    required = {"district", "date", "rainfall_mm", "tmax_c"}
    if required - set(weather.columns):
        raise ValueError(f"Weather panel is missing columns: {sorted(required - set(weather.columns))}")
    x = weather.copy()
    x["district"] = x.district.map(canonical_district)
    x["date"] = pd.to_datetime(x.date, errors="coerce")
    x["rainfall_mm"] = pd.to_numeric(x.rainfall_mm, errors="coerce")
    x["tmax_c"] = pd.to_numeric(x.tmax_c, errors="coerce")
    x = x.dropna(subset=["district", "date"])
    x = x.drop_duplicates(["district", "date"]).sort_values(["district", "date"])
    x["rain_7d"] = x.groupby("district", sort=False).rainfall_mm.transform(lambda s: s.rolling(7, min_periods=7).sum())
    index = x.set_index(["district", "date"])
    outputs = []
    for row in apy[["district", "crop_year", "season"]].itertuples(index=False):
        start_func, end_func = SEASON_WINDOW[row.season]
        start, end = pd.Timestamp(start_func(int(row.crop_year))), pd.Timestamp(end_func(int(row.crop_year)))
        try:
            subset = index.loc[row.district].loc[start:end]
        except KeyError:
            subset = pd.DataFrame(columns=x.columns)
        if subset.empty:
            vals = {col: np.nan for col in FEATURES}
            day_count = 0
        else:
            rain = pd.to_numeric(subset.rainfall_mm, errors="coerce")
            temps = pd.to_numeric(subset.tmax_c, errors="coerce")
            vals = {
                "rainfall_mm": float(rain.sum(min_count=1)) if rain.notna().any() else np.nan,
                "wet_days_1mm": float((rain >= 1.0).sum()) if rain.notna().any() else np.nan,
                "max_7day_rainfall_mm": float(pd.to_numeric(subset.rain_7d, errors="coerce").max()) if pd.to_numeric(subset.rain_7d, errors="coerce").notna().any() else np.nan,
                "mean_tmax_c": float(temps.mean()) if temps.notna().any() else np.nan,
            }
            day_count = int(rain.notna().sum())
            expected_days = int((end - start).days + 1)
            # Partial windows are unavailable, not silently treated as full
            # season totals. Keep the observed day count for auditing.
            if len(subset) != expected_days or rain.notna().sum() != expected_days or temps.notna().sum() != expected_days:
                vals = {col: np.nan for col in FEATURES}
        outputs.append({"district": row.district, "crop_year": int(row.crop_year), "season": row.season,
                        "weather_period_start": str(start.date()), "weather_period_end": str(end.date()),
                        "weather_days_expected": int((end - start).days + 1),
                        "weather_days_available": day_count, **vals})
    return pd.DataFrame(outputs)


def build_panel(apy: pd.DataFrame, weather_features: pd.DataFrame) -> pd.DataFrame:
    panel = apy.merge(weather_features, on=["district", "crop_year", "season"], how="left", validate="one_to_one")
    panel = panel[panel[TARGET].notna()].copy()
    panel[TARGET] = panel[TARGET].astype(int)
    panel["state"] = "West Bengal"
    panel["year"] = panel.crop_year.astype(int)
    return panel


def evaluate(panel: pd.DataFrame, test_start_year: int = 2018,
             model_output: Path | None = None) -> dict:
    labeled = panel.dropna(subset=[TARGET]).copy()
    eligible = labeled.dropna(subset=FEATURES).copy()
    train = eligible[eligible.year < test_start_year]
    test = eligible[eligible.year >= test_start_year]
    positives = int(labeled[TARGET].sum())
    gates = {
        "at_least_150_labeled_rows": len(labeled) >= 150,
        "at_least_25_positive_shortfalls": positives >= 25,
        "at_least_8_labeled_years": labeled.year.nunique() >= 8,
        "at_least_12_districts": labeled.district.nunique() >= 12,
        "at_least_5_test_shortfalls": int(test[TARGET].sum()) >= 5,
        "complete_weather_inputs": len(eligible) >= 150,
        "both_test_classes": test[TARGET].nunique() == 2,
    }
    missing_by_feature = {c: int(labeled[c].isna().sum()) for c in FEATURES}
    base = {
        "status": "BLOCKED" if not all(gates.values()) else "READY_TO_EVALUATE",
        "target": "APY-observed Rice yield < 85% of previous five consecutive district/season years' mean yield",
        "target_column": TARGET,
        "label_source": str(APY_FILE),
        "rows_after_target_lag": int(len(labeled)), "positive_shortfalls": positives,
        "positive_rate": round(float(labeled[TARGET].mean()), 6) if len(labeled) else None,
        "years": sorted(map(int, labeled.year.unique())), "year_count": int(labeled.year.nunique()),
        "districts": sorted(labeled.district.unique()), "district_count": int(labeled.district.nunique()),
        "weather_complete_rows": int(len(eligible)), "missing_weather_by_feature": missing_by_feature,
        "test_start_year": test_start_year, "train_rows": int(len(train)), "test_rows": int(len(test)),
        "test_positive_shortfalls": int(test[TARGET].sum()), "gates": gates,
        "feature_columns": FEATURES,
    }
    if not all(gates.values()):
        base["blockers"] = [name for name, ok in gates.items() if not ok]
        base["candidate_model_artifact"] = None
        return base

    # The original DINOS estimator family is retained (Random Forest), but it
    # is fitted as a separately named crop-yield experiment with weather-only
    # inputs. Median imputers are learned on training rows only.
    model = make_pipeline(
        SimpleImputer(strategy="median"),
        RandomForestClassifier(n_estimators=500, max_depth=6, min_samples_leaf=8,
                               random_state=42, class_weight="balanced_subsample"),
    )
    model.fit(train[FEATURES], train[TARGET])
    actual = test[TARGET].astype(int).to_numpy()
    model_probability = model.predict_proba(test[FEATURES])[:, 1]
    train_rate = float(train[TARGET].mean())
    base_rate_probability = np.full(len(test), train_rate)
    # Prior-year target must be from the exact same district and crop season.
    labels = labeled.set_index(["district", "season", "year"])[TARGET]
    persistence_probability = []
    for row in test[["district", "season", "year"]].itertuples(index=False):
        prior = labels.get((row.district, row.season, int(row.year) - 1), np.nan)
        persistence_probability.append(float(prior) if pd.notna(prior) else train_rate)
    persistence_probability = np.asarray(persistence_probability)

    def scores(probability: Iterable[float]) -> dict:
        values = np.asarray(list(probability), dtype=float)
        return {"auc": round(float(roc_auc_score(actual, values)), 4),
                "brier_score": round(float(brier_score_loss(actual, values)), 6)}

    model_metrics = scores(model_probability)
    persistence_metrics = scores(persistence_probability)
    base_metrics = scores(base_rate_probability)
    estimator = model.named_steps["randomforestclassifier"]
    base.update({
        "status": "EVALUATED",
        "evaluation": {
            "split": f"train years < {test_start_year}; test years >= {test_start_year}",
            "test_years": sorted(map(int, test.year.unique())),
            "model": model_metrics,
            "persistence_same_district_season_previous_year": persistence_metrics,
            "base_rate_from_training_only": base_metrics,
            "beats_both_baselines_auc": model_metrics["auc"] > persistence_metrics["auc"] and model_metrics["auc"] > base_metrics["auc"],
            "beats_both_baselines_brier": model_metrics["brier_score"] < persistence_metrics["brier_score"] and model_metrics["brier_score"] < base_metrics["brier_score"],
            "model_accuracy_at_0_5": round(float(accuracy_score(actual, model_probability >= 0.5)), 4),
            "train_prevalence": round(train_rate, 6),
        },
        "feature_importance": {name: round(float(importance), 6)
                               for name, importance in zip(FEATURES, estimator.feature_importances_)},
        "candidate_model_artifact": str(model_output) if model_output else None,
        "claim_allowed": bool(
            model_metrics["auc"] > persistence_metrics["auc"]
            and model_metrics["auc"] > base_metrics["auc"]
            and model_metrics["brier_score"] < persistence_metrics["brier_score"]
            and model_metrics["brier_score"] < base_metrics["brier_score"]
        ),
        "limitations": [
            "Weather predictors are grid-cell ERA5 reanalysis at district polygon centroids, not station observations or district spatial means.",
            "Yield shortfall is a retrospective APY-derived crop outcome; it is not livelihood distress.",
            "A successful temporal holdout on one state is exploratory and does not establish operational forecasting skill.",
            "Rainfall and temperature use the pre-harvest seasonal windows documented in this script; crop calendars vary locally.",
        ],
    })
    if model_output:
        model_output.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(model, model_output)
    return base


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apy", type=Path, default=APY_FILE)
    parser.add_argument("--output-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--start-year", type=int, default=1997)
    parser.add_argument("--end-year", type=int, default=2025)
    parser.add_argument("--test-start-year", type=int, default=2018)
    parser.add_argument("--skip-weather", action="store_true", help="Use only already cached ERA5 chunk files")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    global WEATHER_CACHE
    WEATHER_CACHE = args.output_dir / "weather_chunks"
    apy = load_apy(args.apy)
    weather, weather_report = (fetch_weather_chunks(args.start_year, args.end_year)
                               if not args.skip_weather else _load_cached_weather(args.start_year, args.end_year))
    weather_features = build_weather_features(weather, apy)
    panel = build_panel(apy, weather_features)
    model_file = args.output_dir / "candidate_model.joblib"
    report = evaluate(panel, args.test_start_year, model_file)
    report["weather_ingestion"] = weather_report
    report["district_season_weather_rows"] = int(len(weather_features))
    report["panel_rows"] = int(len(panel))
    report["run_timestamp_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    report["panel_schema"] = list(panel.columns)
    report["source_checksums_sha256"] = {
        "apy_csv": hashlib.sha256(args.apy.read_bytes()).hexdigest(),
        "weather_chunks": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(WEATHER_CACHE.glob("*.csv"))
        },
    }
    panel.to_csv(args.output_dir / "rice_district_season_panel.csv", index=False)
    (args.output_dir / "training_report.json").write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({
        "status": report["status"], "rows_after_target_lag": report["rows_after_target_lag"],
        "positive_shortfalls": report["positive_shortfalls"], "year_count": report["year_count"],
        "district_count": report["district_count"], "weather_complete_rows": report["weather_complete_rows"],
        "test_rows": report["test_rows"], "test_positive_shortfalls": report["test_positive_shortfalls"],
        "gates": report["gates"], "evaluation": report.get("evaluation"),
        "claim_allowed": report.get("claim_allowed"), "weather_ingestion": weather_report,
        "report": str(args.output_dir / "training_report.json"),
        "panel": str(args.output_dir / "rice_district_season_panel.csv"),
        "candidate_model": report.get("candidate_model_artifact"),
    }, indent=2, allow_nan=False))
    return 0 if report["status"] == "EVALUATED" else 2


def _load_cached_weather(start_year: int, end_year: int) -> tuple[pd.DataFrame, dict]:
    parts = []
    missing = []
    for first, last in chunks(start_year, end_year, 8):
        for cache in WEATHER_CACHE.glob(f"*_{first}_{last}.csv"):
            parts.append(pd.read_csv(cache, parse_dates=["date"]))
        # Validate full district coverage later; this identifies absent chunks.
        if not list(WEATHER_CACHE.glob(f"*_{first}_{last}.csv")):
            missing.append([first, last])
    frame = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(
        columns=["district", "date", "rainfall_mm", "tmax_c", "latitude", "longitude"])
    frame["date"] = pd.to_datetime(frame.date, errors="coerce")
    return frame, {"cached_only": True, "chunks": chunks(start_year, end_year, 8), "missing_chunks": missing,
                   "cached_chunk_files": len(parts), "daily_rows": len(frame),
                   "coverage_start": str(frame.date.min().date()) if len(frame) else None,
                   "coverage_end": str(frame.date.max().date()) if len(frame) else None,
                   "weather_source": WEATHER_API}


if __name__ == "__main__":
    raise SystemExit(main())
