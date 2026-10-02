"""
Kavach — Rainfall Anomaly Pipeline (Part 9)
===============================================
CURRENT/HISTORICAL OBSERVATION -> HISTORICAL BASELINE -> ANOMALY ->
FEATURE QUALITY CHECK -> MODEL INPUT

Every stage is surfaced explicitly. If a defensible baseline does not
exist for a location, this returns rainfall_anomaly_pct=None with
model_input_used=False and a clear reason — it never fabricates a number.
"""
from .weather.models import LIVE
from .weather import historical


def compute_rainfall_anomaly(observation, district: str, block: str, latitude=None, longitude=None, live_pilot=False, rainfall_mm_override=None, measurement_type="observation") -> dict:
    """observation: a WeatherObservation (real, from the weather service).
    Returns the full pipeline trace, not just the final number, so the API
    and UI can show exactly which stage failed if any did."""
    stage_1_observation = {
        "have_observation": observation.status == LIVE,
        "precipitation_mm": rainfall_mm_override if rainfall_mm_override is not None else observation.precipitation_mm,
        "measurement_type": measurement_type,
        "observed_at": observation.observed_at,
        "provider": observation.provider_name,
    }

    baseline = historical.get_baseline(district, block)
    if baseline is None and live_pilot and latitude is not None and longitude is not None:
        try:
            baseline = historical.fetch_era5_daily_baseline(latitude, longitude)
        except Exception as exc:
            baseline = None
            live_baseline_error = str(exc)
        else:
            live_baseline_error = None
    else:
        live_baseline_error = None
    stage_2_baseline = {
        "have_baseline": baseline is not None,
        "baseline": baseline,  # None, or {"mean_mm": ..., "period": ..., "source": ..., "computed_at": ...}
    }

    if not stage_1_observation["have_observation"]:
        return _unavailable(stage_1_observation, stage_2_baseline,
                             "no live rainfall observation available")
    if baseline is None:
        return _unavailable(stage_1_observation, stage_2_baseline,
                             "no defensible historical baseline exists for this location yet — "
                             "see /data-health baseline status; India OGD/IMD normals require an "
                             "API key not configured in this build, and the Open-Meteo ERA5 batch "
                             "computation has not been run (no network egress in this environment)")

    actual = stage_1_observation["precipitation_mm"]
    mean_mm = baseline["mean_mm"]
    if mean_mm in (None, 0):
        return _unavailable(stage_1_observation, stage_2_baseline, "baseline mean is zero/invalid")

    anomaly_pct = round(((actual - mean_mm) / mean_mm) * 100, 1)
    stage_3_anomaly = {"rainfall_anomaly_pct": anomaly_pct}

    # Feature quality check: reject implausible readings rather than pass them to the model
    quality_ok = -100 <= anomaly_pct <= 500 and actual is not None and actual >= 0
    stage_4_quality = {"quality_ok": quality_ok,
                        "reason": None if quality_ok else "anomaly out of plausible range"}

    if not quality_ok:
        return {
            "stage_1_observation": stage_1_observation, "stage_2_baseline": stage_2_baseline,
            "stage_3_anomaly": stage_3_anomaly, "stage_4_quality": stage_4_quality,
            "rainfall_anomaly_pct": None, "model_input_used": False,
            "baseline_period": baseline.get("period"), "baseline_source": baseline.get("source"),
        }

    return {
        "stage_1_observation": stage_1_observation, "stage_2_baseline": stage_2_baseline,
        "stage_3_anomaly": stage_3_anomaly, "stage_4_quality": stage_4_quality,
        "rainfall_anomaly_pct": anomaly_pct, "model_input_used": True,
        "baseline_period": baseline.get("period"), "baseline_source": baseline.get("source"),
    }


def _unavailable(stage_1, stage_2, reason):
    return {
        "stage_1_observation": stage_1, "stage_2_baseline": stage_2,
        "stage_3_anomaly": None, "stage_4_quality": None,
        "rainfall_anomaly_pct": None, "model_input_used": False,
        "baseline_period": None, "baseline_source": None,
        "reason": reason,
    }
