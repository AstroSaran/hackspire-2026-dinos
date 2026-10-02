"""Auditable environmental screening rules over real forecast-provider data.

This is not a learned or livelihood-risk model. It abstains when the input
forecast is unavailable or materially incomplete and never emits probabilities.
"""
from __future__ import annotations

from datetime import date
import hashlib
import json
import math
from typing import Iterable


MODEL_NAME = "Kavach Environmental Watch"
MODEL_VERSION = "1.1.0"
METHOD = "fixed screening thresholds over provider forecast; no learned weights"
THRESHOLDS = {
    "rainfall_mm_day": 50,
    "rain_probability_pct": 70,
    "rainfall_with_probability_mm": 20,
    "wind_max_kmh": 50,
    "temperature_max_c": 40,
}
_FIELD_BOUNDS = {
    "precipitation_sum_mm": (0.0, 1000.0),
    "precipitation_probability_max_pct": (0.0, 100.0),
    "wind_speed_max_kmh": (0.0, 400.0),
    "temperature_max_c": (-80.0, 70.0),
}
_CONFIG_DIGEST = hashlib.sha256(json.dumps(
    {"version": MODEL_VERSION, "thresholds": THRESHOLDS}, sort_keys=True,
    separators=(",", ":")).encode("utf-8")).hexdigest()


def _finite_range(value, low: float, high: float) -> bool:
    if value is None or isinstance(value, bool):
        return False
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return False
    return math.isfinite(parsed) and low <= parsed <= high


def _valid_date(value) -> bool:
    if not isinstance(value, str):
        return False
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def _screening_rows(days: Iterable) -> tuple[list[dict], dict]:
    rows, field_counts = [], {name: 0 for name in _FIELD_BOUNDS}
    total = 0
    invalid_dates = 0
    invalid_values = 0
    for day in days:
        total += 1
        day_date = getattr(day, "date", None)
        if not _valid_date(day_date):
            invalid_dates += 1
            continue
        row = {"date": day_date}
        valid_fields = 0
        for field, (low, high) in _FIELD_BOUNDS.items():
            value = getattr(day, field, None)
            if _finite_range(value, low, high):
                row[field] = float(value)
                field_counts[field] += 1
                valid_fields += 1
            else:
                row[field] = None
                if value is not None:
                    invalid_values += 1
        if valid_fields:
            rows.append(row)
    complete_days = sum(all(row[field] is not None for field in _FIELD_BOUNDS) for row in rows)
    quality = {
        "received_days": total,
        "usable_days": len(rows),
        "complete_days": complete_days,
        "invalid_dates": invalid_dates,
        "invalid_values": invalid_values,
        "field_coverage": {name: {"available_days": count, "received_days": total}
                           for name, count in field_counts.items()},
    }
    return rows, quality


def _watches_from_rows(rows: Iterable[dict]) -> list[dict]:
    watches = []
    for row in rows:
        rainfall = row.get("precipitation_sum_mm")
        rain_probability = row.get("precipitation_probability_max_pct")
        wind = row.get("wind_speed_max_kmh")
        temperature = row.get("temperature_max_c")
        triggers = []
        if rainfall is not None and rainfall >= THRESHOLDS["rainfall_mm_day"]:
            triggers.append("forecast rainfall >= 50 mm/day")
        if (rain_probability is not None and rain_probability >= THRESHOLDS["rain_probability_pct"] and
                rainfall is not None and rainfall >= THRESHOLDS["rainfall_with_probability_mm"]):
            triggers.append("rain probability >= 70% with >= 20 mm forecast")
        if wind is not None and wind >= THRESHOLDS["wind_max_kmh"]:
            triggers.append("forecast maximum wind >= 50 km/h")
        if temperature is not None and temperature >= THRESHOLDS["temperature_max_c"]:
            triggers.append("forecast maximum temperature >= 40 °C")
        if triggers:
            watches.append({
                "date": row["date"], "triggers": triggers, "rainfall_mm": rainfall,
                "rain_probability_pct": rain_probability, "wind_max_kmh": wind,
                "temperature_max_c": temperature,
            })
    return watches


def forecast_watches(days: Iterable) -> list[dict]:
    """Apply documented rules only to finite, plausible, dated provider values."""
    if days is None:
        return []
    rows, _ = _screening_rows(days)
    return _watches_from_rows(rows)


def _rainfall_context(rainfall: dict | None) -> dict:
    unavailable = {"status": "UNAVAILABLE", "note": "No complete-month ERA5 comparison is available."}
    if not isinstance(rainfall, dict):
        return unavailable
    anomaly = rainfall.get("anomaly_pct")
    if not _finite_range(anomaly, -1000.0, 1000.0):
        return unavailable
    observed, normal = rainfall.get("observed_mm"), rainfall.get("expected_mm")
    if not (_finite_range(observed, 0, 100000) and _finite_range(normal, 0.001, 100000)):
        return unavailable
    anomaly = float(anomaly)
    return {
        "status": "CACHED_REAL", "month": rainfall.get("month"),
        "observed_mm": float(observed), "normal_mm": float(normal),
        "anomaly_pct": anomaly,
        "relation_to_normal": "ABOVE_NORMAL" if anomaly > 0 else "BELOW_NORMAL" if anomaly < 0 else "AT_NORMAL",
        "source": rainfall.get("source"), "baseline_period": rainfall.get("baseline_period"),
        "retrieved_at": rainfall.get("retrieved_at"),
    }


def _soil_context(soil: dict | None) -> dict:
    unavailable = {"status": "UNAVAILABLE", "note": "Provider-grid soil-moisture data not available."}
    if not isinstance(soil, dict) or soil.get("status") != "LIVE":
        return unavailable
    value = soil.get("value")
    if not _finite_range(value, 0.0, 1.0):
        return {"status": "UNAVAILABLE", "note": "Provider returned an invalid soil-moisture value; it was excluded."}
    return {
        "status": "LIVE", "value": float(value), "unit": soil.get("unit"),
        "observed_at": soil.get("observed_at"), "fetched_at": soil.get("fetched_at"),
        "source": soil.get("source"), "note": soil.get("note"),
        "provider_latitude": soil.get("provider_latitude"),
        "provider_longitude": soil.get("provider_longitude"),
    }


def assess(forecast, rainfall: dict | None, soil: dict | None, generated_at: str) -> dict:
    """Return an explainable watch plus input-quality gates, never a risk score."""
    forecast_status = getattr(forecast, "status", "UNAVAILABLE")
    days = getattr(forecast, "days", None) or []
    provider = getattr(forecast, "provider_name", None)
    fetched_at = getattr(forecast, "fetched_at", None)
    usable_provider = forecast_status in ("LIVE", "STALE")
    rows, quality = _screening_rows(days) if usable_provider else ([], {
        "received_days": len(days), "usable_days": 0, "complete_days": 0,
        "invalid_dates": 0, "invalid_values": 0,
        "field_coverage": {name: {"available_days": 0, "received_days": len(days)} for name in _FIELD_BOUNDS},
    })
    watches = _watches_from_rows(rows)
    complete = (usable_provider and bool(rows) and quality["usable_days"] == 7 and
                quality["complete_days"] == 7 and quality["invalid_dates"] == 0 and
                quality["invalid_values"] == 0 and bool(fetched_at) and bool(provider) and
                forecast_status == "LIVE")

    if not usable_provider or not rows:
        state = "INCOMPLETE_EVIDENCE"
        summary = "A usable live forecast is unavailable; no environmental screening result can be returned."
    elif watches:
        state = "FORECAST_WATCH"
        date_count = len({watch["date"] for watch in watches})
        summary = f"Forecast screening thresholds were crossed on {date_count} day(s). Check official alerts and local conditions."
        if not complete:
            summary += " Some forecast inputs are missing, invalid, or stale."
    elif not complete:
        state = "INCOMPLETE_EVIDENCE"
        summary = "Some forecast inputs are missing, invalid, or stale; the model will not report a no-trigger result."
    else:
        state = "NO_CONFIGURED_FORECAST_TRIGGER"
        summary = "No configured screening threshold was crossed in the complete live forecast. This is not an all-clear."

    soil_result = _soil_context(soil)
    rainfall_result = _rainfall_context(rainfall)
    quality_state = "COMPLETE" if complete else "PARTIAL" if rows else "UNAVAILABLE"
    return {
        "status": state,
        "model": {"name": MODEL_NAME, "version": MODEL_VERSION, "method": METHOD,
                  "configuration_sha256": _CONFIG_DIGEST},
        "generated_at": generated_at,
        "summary": summary,
        "assessment_quality": {"status": quality_state, **quality,
                               "decision": "SCREENING_ONLY" if watches else "ABSTAIN" if not complete else "NO_RULE_TRIGGER",
                               "stale_input": forecast_status == "STALE"},
        "forecast": {"status": forecast_status if usable_provider else "UNAVAILABLE",
                     "provider": provider, "fetched_at": fetched_at,
                     "watch_count": len(watches), "watches": watches,
                     "thresholds": THRESHOLDS},
        "rainfall_context": rainfall_result,
        "topsoil_context": soil_result,
        "limitations": [
            "Threshold rules are screening rules, not official warnings or locally validated impact thresholds.",
            "Missing or implausible forecast values cause an abstention; a no-trigger result is not an all-clear.",
            "Rainfall anomaly and model-grid soil moisture are context only; neither establishes household or crop stress.",
            "No livelihood prediction, probability, or household risk is trained or emitted.",
        ],
    }
