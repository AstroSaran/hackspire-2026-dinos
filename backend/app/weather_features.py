"""
Kavach — Weather -> Feature Pipeline
=======================================
REAL WEATHER -> weather normalization -> historical baseline -> rainfall
anomaly -> Kavach feature layer -> risk engine (Part 8).

HONESTY NOTE: computing a genuine rainfall anomaly requires a real
multi-year historical rainfall baseline for each location (e.g. IMD's
30-year normals). That baseline dataset is not wired into this build — it
would need to come from IMD's climatological normals product, which is a
separate, larger data-acquisition effort from the current-weather API this
build integrates. Rather than fabricate a plausible-looking "normal
rainfall" figure and quietly compute an anomaly against it, this module:
  - uses a single, clearly-labeled PROTOTYPE_BASELINE_MM constant,
  - marks every anomaly it produces with baseline_status="PROTOTYPE_BASELINE",
  - and never lets that computed value overwrite the model's existing
    representative rainfall_anomaly_pct feature unless the caller explicitly
    opts in (see main.py: weather-informed anomaly is additive/optional,
    the representative dataset remains the default so the model's
    already-validated-internally-consistent behavior isn't disturbed by a
    partial, differently-sourced signal).
"""
from .weather.models import LIVE

# A rough Gangetic West Bengal monsoon-season daily rainfall reference,
# used ONLY as a stand-in until a real IMD climatological normal is wired
# in. This is explicitly a prototype value, surfaced as such everywhere it
# is used — never presented as an IMD normal.
PROTOTYPE_BASELINE_MM = 6.5
BASELINE_STATUS = "PROTOTYPE_BASELINE"


def rainfall_anomaly_from_observation(observation) -> dict:
    """observation: a WeatherObservation. Returns a dict with the computed
    anomaly and full status/provenance — or an explicit unavailable marker
    if the observation itself isn't LIVE."""
    if observation.status != LIVE or observation.rainfall_mm is None:
        return {
            "rainfall_anomaly_pct": None,
            "baseline_mm": PROTOTYPE_BASELINE_MM,
            "baseline_status": BASELINE_STATUS,
            "computed": False,
            "reason": observation.note or "no live rainfall observation available",
        }
    actual = observation.rainfall_mm
    anomaly_pct = round(((actual - PROTOTYPE_BASELINE_MM) / PROTOTYPE_BASELINE_MM) * 100, 1)
    return {
        "rainfall_anomaly_pct": anomaly_pct,
        "actual_rainfall_mm": actual,
        "baseline_mm": PROTOTYPE_BASELINE_MM,
        "baseline_status": BASELINE_STATUS,
        "computed": True,
        "reason": None,
    }
