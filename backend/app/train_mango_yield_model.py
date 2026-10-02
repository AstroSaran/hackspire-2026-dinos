"""Train an explicitly experimental, annual West Bengal mango-yield model.

The only labels are published district/year area and production estimates. This
cannot train or substitute for any short-horizon livelihood-distress model.
Run: python -m app.train_mango_yield_model
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .mango_dataset_pipeline import (
    REPOSITORY_DIR,
    inspect_mango_dataset,
    write_versioned_report,
)


BACKEND_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_DIR = BACKEND_DIR.parent
DATA_FILE = BACKEND_DIR / "data" / "wb_mango_district_annual.csv"
ARTIFACT_FILE = BACKEND_DIR / "data" / "mango_yield_baseline_model.json"
CONFIG_FILE = BACKEND_DIR / "configs" / "train_mango_yield.json"


def _display_path(path: Path) -> str:
    try:
        return Path(path).resolve().relative_to(REPOSITORY_DIR.resolve()).as_posix()
    except ValueError:
        return str(Path(path).resolve())


def _repository_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    from_current_directory = (Path.cwd() / path).resolve()
    return from_current_directory if from_current_directory.exists() else (REPOSITORY_DIR / path).resolve()


def load_config(config_path: str | Path = CONFIG_FILE) -> tuple[dict, Path]:
    config_path = Path(config_path)
    resolved_path = config_path if config_path.is_absolute() else (BACKEND_DIR / config_path).resolve()
    try:
        config = json.loads(resolved_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Training configuration could not be read: {type(exc).__name__}") from exc
    if not isinstance(config, dict) or config.get("config_version") != 1:
        raise ValueError("Unsupported or invalid training configuration version.")
    for section in ("dataset", "model", "split", "fit", "output"):
        if not isinstance(config.get(section), dict):
            raise ValueError(f"Training configuration section is missing or invalid: {section}")
    if config["split"].get("strategy") != "forward_temporal_holdout" or config["split"].get("test_transitions") != 1:
        raise ValueError("This dataset currently supports one final forward temporal holdout only.")
    if config["split"].get("validation_transitions") != 0:
        raise ValueError("A separate validation period is not supported by the four available annual vintages.")
    if config["fit"].get("solver") != "closed_form_ordinary_least_squares":
        raise ValueError("Unsupported fit solver for this experimental pipeline.")
    return config, resolved_path
def load_and_validate(data_file: Path = DATA_FILE, expected_sha256: str | None = None):
    quality_report = inspect_mango_dataset(data_file)
    if quality_report["status"] != "PASS":
        failed = [
            check["id"] for check in quality_report["quality_checks"]
            if check["status"] != "PASS"
        ]
        raise ValueError(
            "Dataset quality gate did not pass; training stopped. "
            f"Review checks: {', '.join(failed)}"
        )
    if expected_sha256 and quality_report["source_file_sha256"] != expected_sha256:
        raise ValueError("Dataset checksum differs from the configured version; training stopped.")
    with data_file.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        raise ValueError("No real source records are available; training stopped.")

    by_year: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        area = float(row["area_thousand_ha"])
        production = float(row["production_thousand_mt"])
        row["area"] = area
        row["production"] = production
        row["yield_t_ha"] = production / area
        by_year[row["year"]].append(row)
    return by_year, quality_report


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


def metrics(actual, predicted):
    errors = [p - a for a, p in zip(actual, predicted)]
    mae = sum(abs(e) for e in errors) / len(errors)
    rmse = math.sqrt(sum(e * e for e in errors) / len(errors))
    mean = sum(actual) / len(actual)
    total = sum((a - mean) ** 2 for a in actual)
    r2 = None if total == 0 else 1 - sum(e * e for e in errors) / total
    return {"mae_t_per_ha": round(mae, 4), "rmse_t_per_ha": round(rmse, 4),
            "r2": None if r2 is None else round(r2, 4)}


def train(config_path: str | Path = CONFIG_FILE):
    started_at = time.perf_counter()
    config, resolved_config_path = load_config(config_path)
    data_file = _repository_path(config["dataset"].get("path", ""))
    expected_sha256 = config["dataset"].get("expected_sha256")
    if not isinstance(expected_sha256, str) or len(expected_sha256) != 64:
        raise ValueError("An exact 64-character dataset SHA-256 must be configured.")
    by_year, quality_report = load_and_validate(data_file, expected_sha256)
    metadata_dir = _repository_path(config["output"].get("metadata_dir", ""))
    quality_report_path = write_versioned_report(quality_report, metadata_dir)
    years = sorted(by_year, key=lambda y: int(y[:4]))
    districts = sorted(r["district"] for r in by_year[years[0]])
    indexed = {year: {r["district"]: r for r in by_year[year]} for year in years}

    transitions = []
    for prior, following in zip(years, years[1:]):
        for district in districts:
            old = indexed[prior][district]
            new = indexed[following][district]
            transitions.append({"district": district, "from_year": prior, "to_year": following,
                                "x_yield": old["yield_t_ha"], "y_yield": new["yield_t_ha"]})

    # Keep the newest annual transition completely out of model fitting.
    test_transition = years[-2:]
    train_rows = [r for r in transitions if r["to_year"] < test_transition[1]]
    test_rows = [r for r in transitions if (r["from_year"], r["to_year"]) == tuple(test_transition)]
    if len(train_rows) != 44 or len(test_rows) != 22:
        raise ValueError("The time-ordered train/test split is incomplete; training stopped.")

    intercept, slope = fit_simple_regression([(r["x_yield"], r["y_yield"]) for r in train_rows])
    actual = [r["y_yield"] for r in test_rows]
    predicted = [intercept + slope * r["x_yield"] for r in test_rows]
    persistence = [r["x_yield"] for r in test_rows]

    # Final fitted coefficients use every published transition after the
    # holdout has been scored. Metrics stay attached to the untouched holdout.
    final_intercept, final_slope = fit_simple_regression(
        [(r["x_yield"], r["y_yield"]) for r in transitions]
    )
    train_predicted = [intercept + slope * r["x_yield"] for r in train_rows]
    training_metrics = metrics([r["y_yield"] for r in train_rows], train_predicted)
    absolute_errors = [abs(p - a) for a, p in zip(actual, predicted)]
    failure_cases = sorted(
        ({"district": row["district"], "from_year": row["from_year"], "to_year": row["to_year"],
          "actual_t_per_ha": round(row["y_yield"], 6),
          "predicted_t_per_ha": round(prediction, 6),
          "persistence_t_per_ha": round(row["x_yield"], 6),
          "absolute_error_t_per_ha": round(abs(prediction - row["y_yield"]), 6)}
         for row, prediction in zip(test_rows, predicted)),
        key=lambda item: item["absolute_error_t_per_ha"], reverse=True,
    )
    configuration_sha256 = hashlib.sha256(resolved_config_path.read_bytes()).hexdigest()
    run_id = hashlib.sha256(
        f"{quality_report['source_file_sha256']}:{configuration_sha256}".encode("ascii")
    ).hexdigest()[:20]
    artifact = {
        "run_id": run_id,
        "model_name": config["model"]["name"],
        "version": config["model"]["version"],
        "status": "TRAINED_EXPERIMENTAL",
        "training_completed_at": datetime.now(timezone.utc).isoformat(),
        "training_duration_seconds": round(time.perf_counter() - started_at, 6),
        "training_configuration": {
            "file": _display_path(resolved_config_path),
            "sha256": configuration_sha256,
            "values": config,
        },
        "environment": {
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "device": "CPU; Python standard library closed-form fit",
        },
        "training_loss": {"metric": "mae_t_per_ha", "value": training_metrics["mae_t_per_ha"]},
        "training_metrics": training_metrics,
        "target": config["model"]["target"],
        "target_unit": config["model"]["target_unit"],
        "input": config["model"]["input_feature"],
        "algorithm": config["model"]["algorithm"],
        "geography": {"state": "West Bengal", "district_count": 22},
        "dataset": {"id": config["dataset"]["id"],
                    "file": _display_path(data_file),
                    "rows": len(by_year) * 22, "years": years,
                    "yearly_transition_rows": len(transitions),
                    "sha256": quality_report["source_file_sha256"],
                    "dataset_version": quality_report["dataset_version"],
                    "quality_report": _display_path(quality_report_path),
                    "source": "West Bengal Directorate of Horticulture, final district mango estimates"},
        "validation": {
            "method": "forward temporal holdout: train on 2021-22 to 2022-23 and 2022-23 to 2023-24 transitions; test on 2023-24 to 2024-25",
            "train_transition_count": len(train_rows), "test_transition_count": len(test_rows),
            "test_year_transition": f"{test_transition[0]} -> {test_transition[1]}",
            "model": metrics(actual, predicted),
            "persistence_baseline": metrics(actual, persistence),
            "error_analysis_worst_five": failure_cases[:5],
            "district_group_overlap": "All 22 districts occur in training history and test input history by design; the test estimates future-year performance for known districts, not unseen-district generalization.",
            "validation_set": "Not available: four annual vintages do not provide a separate stable period.",
            "independent_test_years": 1,
        },
        "fitted_parameters_after_holdout": {"intercept": final_intercept, "yield_lag_coefficient": final_slope,
                                             "fit_transition_count": len(transitions)},
        "release": {"production_decisions": False,
                    "livelihood_distress_prediction": False,
                    "field_validation": "not performed",
                    "forecast_emission": "withheld: the district-level 2025-26 final mango observations were not ingested; annual crop estimates are not distress labels"},
        "limitations": [
            "This is a one-crop, annual output baseline, not a crop-stress, livelihood-risk, or 2-8-week warning model.",
            "There are four final-estimate years and only one held-out test year; validation is too small for production use.",
            "The target is derived from area and production estimates and contains no weather, price, employment, water, household, or intervention features.",
            "Some source tables have different publication dates; retain the original year/estimate round and refresh from the live official endpoint when backend egress is available.",
        ],
    }
    artifact_path = _repository_path(config["output"]["model_artifact"])
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact["artifact_path"] = _display_path(artifact_path)
    artifact_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
    return artifact


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG_FILE,
                        help="JSON training configuration")
    args = parser.parse_args()
    result = train(args.config)
    print(json.dumps({"status": result["status"], "rows": result["dataset"]["rows"],
                      "years": result["dataset"]["years"],
                      "validation": result["validation"],
                      "run_id": result["run_id"],
                      "artifact": result["artifact_path"]}, indent=2))
