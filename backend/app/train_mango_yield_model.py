"""Train an explicitly experimental, annual West Bengal mango-yield model (v0.2).

The only labels are published district/year area and production estimates. This
cannot train or substitute for any short-horizon livelihood-distress model.
Run: python -m app.train_mango_yield_model
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from . import model_registry


BACKEND_DIR = Path(__file__).resolve().parents[1]
DATA_FILE = BACKEND_DIR / "data" / "wb_mango_district_annual.csv"
ARTIFACT_FILE = BACKEND_DIR / "data" / "mango_yield_baseline_model.json"
EXPECTED_TOTALS = {
    "2021-22": (113.896, 942.985),
    "2022-23": (116.005, 1027.584),
    "2023-24": (116.162, 882.271),
    "2024-25": (122.067, 1080.264),
}


def load_and_validate():
    with DATA_FILE.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError("No real source records are available; training stopped.")

    by_year: dict[str, list[dict]] = defaultdict(list)
    required = {"state", "district", "crop", "year", "estimate_round",
                "area_thousand_ha", "production_thousand_mt", "source_url"}
    if not required.issubset(rows[0]):
        raise ValueError("Training CSV is missing required columns.")
    for row in rows:
        if row["state"] != "West Bengal" or row["crop"].casefold() != "mango":
            raise ValueError("Unexpected geography or crop found in the training file.")
        area = float(row["area_thousand_ha"])
        production = float(row["production_thousand_mt"])
        if (not math.isfinite(area) or not math.isfinite(production) or area <= 0 or production < 0
                or not row["source_url"].startswith("https://wbfpih.wb.gov.in/")):
            raise ValueError("Invalid area, production, or source provenance; training stopped.")
        if not row["district"].strip() or row["estimate_round"] != "Final Estimate":
            raise ValueError("District and final estimate provenance are required.")
        if not re.fullmatch(r"20\d{2}-\d{2}", row["year"]) or (int(row["year"][:4]) + 1) % 100 != int(row["year"][-2:]):
            raise ValueError("Invalid agricultural year range.")
        row["area"] = area
        row["production"] = production
        row["yield_t_ha"] = production / area
        by_year[row["year"]].append(row)

    expected_districts = None
    for year, values in by_year.items():
        names = {r["district"] for r in values}
        if len(values) != 22 or len(names) != 22:
            raise ValueError(f"{year} must contain exactly 22 unique published districts; training stopped.")
        if expected_districts is None:
            expected_districts = names
        elif names != expected_districts:
            raise ValueError("District coverage changes across years; align districts before training.")
        if year not in EXPECTED_TOTALS:
            raise ValueError(f"No published state-total cross-check is registered for {year}.")
        area_sum = sum(r["area"] for r in values)
        production_sum = sum(r["production"] for r in values)
        expected_area, expected_production = EXPECTED_TOTALS[year]
        # Each published district figure and state total is rounded to three
        # decimals (thousand units). Permit the accumulated rounding error
        # across the district rows instead of rejecting otherwise reconciling
        # source data. This tolerance is derived from the stated precision.
        rounding_tolerance = (len(values) + 1) * 0.0005 + 1e-9
        if (abs(area_sum - expected_area) > rounding_tolerance
                or abs(production_sum - expected_production) > rounding_tolerance):
            raise ValueError(
                f"District rows for {year} do not reconcile with the official state total; training stopped."
            )
    if set(by_year) != set(EXPECTED_TOTALS):
        raise ValueError("The observed year set is incomplete; training stopped.")
    years = sorted(int(y[:4]) for y in by_year)
    if any(b != a + 1 for a, b in zip(years, years[1:])):
        raise ValueError("Consecutive annual records are required for lag training.")
    return by_year


def fit_simple_regression(pairs):
    if len(pairs) < 2:
        raise ValueError("At least two real transitions are required.")
    xs = [x for x, _ in pairs]
    ys = [y for _, y in pairs]
    xbar = sum(xs) / len(xs)
    ybar = sum(ys) / len(ys)
    variance = sum((x - xbar) ** 2 for x in xs)
    if variance == 0:
        raise ValueError("The training feature has no variance.")
    slope = sum((x - xbar) * (y - ybar) for x, y in pairs) / variance
    intercept = ybar - slope * xbar
    return intercept, slope


def metrics(actual, predicted, weights=None):
    if (not actual or len(actual) != len(predicted)
            or not all(math.isfinite(v) for v in [*actual, *predicted])):
        raise ValueError("Metrics require aligned, nonempty finite observations and predictions.")
    errors = [p - a for a, p in zip(actual, predicted)]
    mae = sum(abs(e) for e in errors) / len(errors)
    rmse = math.sqrt(sum(e * e for e in errors) / len(errors))
    mean = sum(actual) / len(actual)
    total = sum((a - mean) ** 2 for a in actual)
    r2 = None if total == 0 else 1 - sum(e * e for e in errors) / total
    out = {"mae_t_per_ha": round(mae, 4), "rmse_t_per_ha": round(rmse, 4),
           "r2": None if r2 is None else round(r2, 4)}
    rel = [abs(e) / a for e, a in zip(errors, actual) if a > 0]
    out["share_within_10pct"] = round(sum(r <= 0.10 for r in rel) / len(rel), 4) if rel else None
    out["share_within_20pct"] = round(sum(r <= 0.20 for r in rel) / len(rel), 4) if rel else None
    out["zero_target_rows_excluded_from_relative_metrics"] = len(actual) - len(rel)
    if weights:  # production-weighted error: big mango districts matter most
        if len(weights) != len(actual) or not all(math.isfinite(w) and w > 0 for w in weights):
            raise ValueError("Area weights must be finite, positive and aligned.")
        denom = sum(a * w for a, w in zip(actual, weights))
        out["wape_area_weighted"] = round(
            sum(abs(e) * w for e, w in zip(errors, weights)) / denom, 4) if denom else None
    return out


# ---------------------------------------------------------------- candidates
# Every candidate sees only the years strictly before the target year.
JUMP_TOLERANCE = 0.30
# A median of two values is just their mean, so it cannot tell an outlier from a
# real level shift (e.g. a revised estimate that then persists). Only apply the
# outlier fallback when at least three prior observations exist.
MIN_HISTORY_FOR_OUTLIER_RULE = 3


def _persistence(history, **_):
    return history[-1]


def _median_level(history, **_):
    return statistics.median(history)


def _blend(history, **_):
    return 0.5 * history[-1] + 0.5 * statistics.median(history)


def _robust_persistence(history, **_):
    """Carry last year's yield forward unless it is a >30% outlier vs the
    district's own history, in which case fall back to the historical median.
    Guards against one-off placeholder / reporting-break values. With fewer
    than three prior years it is plain persistence."""
    if len(history) < MIN_HISTORY_FOR_OUTLIER_RULE:
        return history[-1]
    median = statistics.median(history)
    return median if abs(history[-1] - median) > JUMP_TOLERANCE * median else history[-1]


def _lag_regression(history, coefficients=None, **_):
    intercept, slope = coefficients
    return intercept + slope * history[-1]


CANDIDATES = {
    "persistence": _persistence,
    "expanding_median": _median_level,
    "blend_last_median": _blend,
    "robust_persistence": _robust_persistence,
    "pooled_lag_regression": _lag_regression,
}


def rolling_origin_backtest(indexed, years, districts):
    """Forecast every year that has >=2 prior years, using only past data."""
    folds = []
    for t in range(2, len(years)):
        target, past = years[t], years[:t]
        coefficients = fit_simple_regression(
            [(indexed[past[i]][d]["yield_t_ha"], indexed[past[i + 1]][d]["yield_t_ha"])
             for d in districts for i in range(len(past) - 1)])
        actual = [indexed[target][d]["yield_t_ha"] for d in districts]
        weights = [indexed[target][d]["area"] for d in districts]
        fold = {"target_year": target, "history_years": past, "candidates": {}}
        for name, fn in CANDIDATES.items():
            predicted = [fn([indexed[y][d]["yield_t_ha"] for y in past],
                            coefficients=coefficients) for d in districts]
            fold["candidates"][name] = {"metrics": metrics(actual, predicted, weights),
                                        "actual": actual, "predicted": predicted,
                                        "districts": list(districts), "weights": weights,
                                        "abs_errors": [abs(p - a) for a, p in zip(actual, predicted)],
                                        "rel_errors": [abs(p - a) / a for a, p in zip(actual, predicted) if a > 0]}
        folds.append(fold)
    return folds


def data_quality_flags(indexed, years, districts):
    """Surface suspicious source records instead of silently training on them."""
    flags = []
    for d in districts:
        series = [indexed[y][d] for y in years]
        for prev, cur in zip(series, series[1:]):
            area_ratio = cur["area"] / prev["area"]
            if area_ratio < 0.5 or area_ratio > 2.0:
                flags.append({"district": d, "year": cur["year"], "type": "AREA_BREAK",
                              "detail": f"area changed x{area_ratio:.2f} ({prev['area']} -> {cur['area']} thousand ha)"})
            if prev["yield_t_ha"] == 0:
                flags.append({"district": d, "year": prev["year"], "type": "ZERO_YIELD",
                              "detail": "Zero production reported; relative yield change is undefined."})
                continue
            yield_ratio = cur["yield_t_ha"] / prev["yield_t_ha"]
            if yield_ratio < 0.6 or yield_ratio > 1.6:
                flags.append({"district": d, "year": cur["year"], "type": "YIELD_JUMP",
                              "detail": f"yield changed x{yield_ratio:.2f} ({prev['yield_t_ha']:.2f} -> {cur['yield_t_ha']:.2f} t/ha)"})
        for r in series:
            if abs(r["yield_t_ha"] * 10 - round(r["yield_t_ha"] * 10)) < 1e-6 and r["yield_t_ha"] >= 4:
                # an exactly round yield on 3-decimal source data suggests a norm, not a measurement
                flags.append({"district": d, "year": r["year"], "type": "SUSPICIOUSLY_ROUND_YIELD",
                              "detail": f"yield is exactly {r['yield_t_ha']:.1f} t/ha"})
        flat = sum(1 for a, b in zip(series, series[1:]) if abs(a["yield_t_ha"] - b["yield_t_ha"]) < 0.02)
        if flat == len(series) - 1:
            flags.append({"district": d, "year": "all", "type": "STATIC_ESTIMATE",
                          "detail": "yield essentially identical in every year; likely carried-forward administrative estimate"})
    return flags


def _quantile(values, q):
    if not values:
        raise ValueError("No positive observed yields for relative-error bands; training stopped.")
    ordered = sorted(values)
    index = min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1)
    return ordered[max(index, 0)]


def train():
    source_digest = hashlib.sha256(DATA_FILE.read_bytes()).hexdigest()
    by_year = load_and_validate()
    years = sorted(by_year, key=lambda y: int(y[:4]))
    districts = sorted(r["district"] for r in by_year[years[0]])
    indexed = {year: {r["district"]: r for r in by_year[year]} for year in years}

    folds = rolling_origin_backtest(indexed, years, districts)
    if not folds:
        raise ValueError("At least three consecutive years are required for a backtest.")
    FLAGS_FOR_SCORING = [fl for fl in data_quality_flags(indexed, years, districts)
                         if fl["type"] in ("YIELD_JUMP", "AREA_BREAK", "SUSPICIOUSLY_ROUND_YIELD") and fl["year"] != "all"]
    summary = {}
    for name in CANDIDATES:
        maes = [f["candidates"][name]["metrics"]["mae_t_per_ha"] for f in folds]
        wapes = [f["candidates"][name]["metrics"]["wape_area_weighted"] for f in folds]
        pooled_actual = [a for f in folds for a in f["candidates"][name]["actual"]]
        pooled_pred = [p for f in folds for p in f["candidates"][name]["predicted"]]
        pooled_w = [w for f in folds for w in f["candidates"][name]["weights"]]
        # "Clean-target" scoring drops records the data-quality checks flag as
        # likely source artefacts in the *target* year. Reported beside, never
        # instead of, the raw numbers.
        flagged = {(fl["district"], fl["year"]) for fl in FLAGS_FOR_SCORING}
        keep = [(a, p, w) for f in folds
                for a, p, w, d in zip(f["candidates"][name]["actual"], f["candidates"][name]["predicted"],
                                      f["candidates"][name]["weights"], f["candidates"][name]["districts"])
                if (d, f["target_year"]) not in flagged]
        summary[name] = {"pooled_out_of_sample": metrics(pooled_actual, pooled_pred, pooled_w),
                          "pooled_clean_target": metrics([k[0] for k in keep], [k[1] for k in keep], [k[2] for k in keep]) if keep else None,
                         "clean_target_records_excluded": len(pooled_actual) - len(keep),
                         "mean_mae_t_per_ha": round(sum(maes) / len(maes), 4),
                         "mean_wape_area_weighted": round(sum(wapes) / len(wapes), 4),
                         "per_fold_mae": {f["target_year"]: m for f, m in zip(folds, maes)}}
    # Select by rolling-origin MAE; ties fall to the simplest (persistence first).
    selected = min(CANDIDATES, key=lambda n: (summary[n]["mean_mae_t_per_ha"], list(CANDIDATES).index(n)))
    baseline_mae = summary["persistence"]["mean_mae_t_per_ha"]

    # Empirical 80% relative-error band from out-of-sample errors of the selected method.
    rel_errors = [e for f in folds for e in f["candidates"][selected]["rel_errors"]]
    band = _quantile(rel_errors, 0.80)

    final_coefficients = fit_simple_regression(
        [(indexed[years[i]][d]["yield_t_ha"], indexed[years[i + 1]][d]["yield_t_ha"])
         for d in districts for i in range(len(years) - 1)])
    next_year = f"{int(years[-1][:4]) + 1}-{(int(years[-1][:4]) + 2) % 100:02d}"
    forecasts = []
    for d in districts:
        history = [indexed[y][d]["yield_t_ha"] for y in years]
        point = CANDIDATES[selected](history, coefficients=final_coefficients)
        forecasts.append({"district": d, "target_year": next_year,
                          "yield_t_per_ha": round(point, 3),
                           "interval_80_low": round(max(0, point * (1 - band)), 3),
                          "interval_80_high": round(point * (1 + band), 3)})

    digest = hashlib.sha256(DATA_FILE.read_bytes()).hexdigest()
    if digest != source_digest:
        raise ValueError("Training source changed during the run; retry with a fixed snapshot.")
    flags = data_quality_flags(indexed, years, districts)
    gap = round(baseline_mae - summary[selected]["mean_mae_t_per_ha"], 4)
    artifact = {
        "schema_version": 1,
        "training_code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "model_name": "West Bengal Mango Yield Baseline",
        "version": "0.2.1-experimental",
        "status": "TRAINED_EXPERIMENTAL",
        "training_completed_at": datetime.now(timezone.utc).isoformat(),
        "target": "annual district mango yield calculated from official production / area estimates",
        "target_unit": "tonnes per hectare",
        "input": "district's own prior-year yield history only",
        "algorithm": f"{selected} (chosen by rolling-origin backtest over {len(CANDIDATES)} candidates)",
        "selected_method": selected,
        "geography": {"state": "West Bengal", "district_count": len(districts)},
        "dataset": {"file": "backend/data/wb_mango_district_annual.csv",
                    "rows": len(by_year) * len(districts), "years": years,
                    "sha256": digest,
                    "source": "West Bengal Directorate of Horticulture, final district mango estimates"},
        "validation": {
            "evaluation_role": "MODEL_SELECTION",
            "untouched_test_years": 0,
            "interval_calibration": "SELECTION_RESIDUALS_NOT_INDEPENDENT",
            "method": "rolling-origin: each target year is forecast using only earlier years; coefficients (where any) are refit on earlier transitions only",
            "folds": [{"target_year": f["target_year"], "history_years": f["history_years"],
                       "candidates": {n: c["metrics"] for n, c in f["candidates"].items()}} for f in folds],
            "candidate_summary": summary,
            "selected_vs_persistence_mae_gain_t_per_ha": gap,
            "rolling_origin_years": len(folds),
            "interval_80_relative_half_width": round(band, 4),
            "significance": "NOT_ESTABLISHED: two forecast origins and 22 districts; differences between the top candidates are within noise",
        },
        "data_quality_flags": flags,
        "evaluation_predictions": [
            {"district": d, "target_year": fold["target_year"],
             "actual_t_per_ha": actual, "predicted_t_per_ha": predicted, "area_thousand_ha": area}
            for fold in folds for d, actual, predicted, area in zip(
                fold["candidates"][selected]["districts"], fold["candidates"][selected]["actual"],
                fold["candidates"][selected]["predicted"], fold["candidates"][selected]["weights"])
        ],
        "experimental_forecasts": forecasts,
        "fitted_parameters_after_holdout": {"intercept": final_coefficients[0],
                                             "yield_lag_coefficient": final_coefficients[1],
                                             "note": "used only by the pooled_lag_regression candidate, which was not selected"},
        "release": {"production_decisions": False,
                    "livelihood_distress_prediction": False,
                    "field_validation": "not performed",
                    "forecast_emission": "experimental forecasts with 80% empirical bands are included for transparency; they are unverified against the not-yet-published next-year estimate and must not drive decisions"},
        "limitations": [
            "Reported validation folds also selected the method; there is no untouched test set. The nominal 80% bands reuse those residuals and do not establish independent 80% coverage.",
            "One-crop, annual output baseline; not a crop-stress, livelihood-risk, or 2-8-week warning model.",
            "Only four official years exist, so only two honest forecast origins; performance claims are weak.",
            "Many districts report an identical yield every year (carried-forward estimates), which makes persistence very hard to beat; see data_quality_flags.",
            "No weather, price, water or household features are used; year-wide shocks (e.g. alternate bearing, 2023-24 dip) are not predictable from this input.",
            "The earlier v0.1 pooled lag regression scored worse than persistence on every fold and was retired as the default.",
        ],
    }
    model_registry.publish(artifact, ARTIFACT_FILE, DATA_FILE, ARTIFACT_FILE.parent / "model_releases")
    return artifact


if __name__ == "__main__":
    result = train()
    print(json.dumps({"status": result["status"], "selected": result["selected_method"],
                      "rows": result["dataset"]["rows"], "years": result["dataset"]["years"],
                      "candidate_summary": result["validation"]["candidate_summary"],
                      "flags": len(result["data_quality_flags"]),
                      "artifact": str(ARTIFACT_FILE)}, indent=2))
