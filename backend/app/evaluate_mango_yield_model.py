"""Recompute the experimental mango-yield forward holdout independently.

Run after training with:
    python -m app.evaluate_mango_yield_model --artifact ../data/mango_yield_baseline_model.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .mango_dataset_pipeline import METADATA_DIR, inspect_mango_dataset
from .train_mango_yield_model import (
    ARTIFACT_FILE,
    REPOSITORY_DIR,
    fit_simple_regression,
    load_and_validate,
    metrics,
)


def _repository_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    from_current_directory = (Path.cwd() / path).resolve()
    return from_current_directory if from_current_directory.exists() else (REPOSITORY_DIR / path).resolve()


def evaluate(artifact_path: str | Path = ARTIFACT_FILE, output_dir: str | Path = METADATA_DIR) -> dict:
    artifact_path = _repository_path(artifact_path)
    try:
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Model artifact could not be read: {type(exc).__name__}") from exc
    if artifact.get("status") != "TRAINED_EXPERIMENTAL" or artifact.get("version") != "0.1.0-experimental":
        raise ValueError("Unsupported model artifact; experimental mango artifact required.")
    dataset = artifact.get("dataset", {})
    data_file = _repository_path(dataset.get("file", ""))
    expected_hash = dataset.get("sha256")
    by_year, quality_report = load_and_validate(data_file, expected_hash)
    if quality_report["dataset_version"] != dataset.get("dataset_version"):
        raise ValueError("Dataset version does not match the trained model artifact.")

    years = sorted(by_year, key=lambda year: int(year[:4]))
    districts = sorted(row["district"] for row in by_year[years[0]])
    indexed = {year: {row["district"]: row for row in by_year[year]} for year in years}
    transitions = []
    for prior, following in zip(years, years[1:]):
        for district in districts:
            old, new = indexed[prior][district], indexed[following][district]
            transitions.append({
                "district": district, "from_year": prior, "to_year": following,
                "x_yield": old["yield_t_ha"], "y_yield": new["yield_t_ha"],
            })
    test_from, test_to = years[-2:]
    train_rows = [row for row in transitions if row["to_year"] < test_to]
    test_rows = [row for row in transitions if (row["from_year"], row["to_year"]) == (test_from, test_to)]
    if len(train_rows) != 44 or len(test_rows) != 22:
        raise ValueError("Expected temporal holdout split is incomplete; evaluation stopped.")

    intercept, slope = fit_simple_regression([(row["x_yield"], row["y_yield"]) for row in train_rows])
    actual = [row["y_yield"] for row in test_rows]
    predicted = [intercept + slope * row["x_yield"] for row in test_rows]
    persistence = [row["x_yield"] for row in test_rows]
    model_metrics = metrics(actual, predicted)
    baseline_metrics = metrics(actual, persistence)
    stored_metrics = artifact.get("validation", {}).get("model")
    if model_metrics != stored_metrics:
        raise ValueError("Recomputed holdout metrics do not match the saved artifact.")

    per_district = sorted((
        {"district": row["district"], "actual_t_per_ha": round(row["y_yield"], 6),
         "predicted_t_per_ha": round(prediction, 6), "persistence_t_per_ha": round(row["x_yield"], 6),
         "absolute_error_t_per_ha": round(abs(prediction - row["y_yield"]), 6)}
        for row, prediction in zip(test_rows, predicted)
    ), key=lambda item: item["absolute_error_t_per_ha"], reverse=True)
    report = {
        "evaluation_version": 1,
        "run_id": artifact["run_id"],
        "dataset_version": quality_report["dataset_version"],
        "status": "EVALUATED_EXPERIMENTAL",
        "split": {
            "method": "forward temporal holdout",
            "training_transition_count": len(train_rows),
            "test_transition_count": len(test_rows),
            "test_transition": f"{test_from} -> {test_to}",
            "independent_test_years": 1,
            "district_overlap": "Known district groups repeat across history by design; this does not estimate unseen-district generalization.",
        },
        "model": model_metrics,
        "persistence_baseline": baseline_metrics,
        "model_beats_persistence_on_mae": model_metrics["mae_t_per_ha"] < baseline_metrics["mae_t_per_ha"],
        "per_district_errors": per_district,
        "limitations": [
            "One test year with 22 district rows is too little independent evidence for production decisions.",
            "Annual mango yield is not a crop-stress, livelihood-risk, or MGNREGA outcome.",
        ],
    }
    output_dir = _repository_path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / f"mango-yield-evaluation-v1-{artifact['run_id']}.json"
    serialized = (json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    try:
        with destination.open("xb") as stream:
            stream.write(serialized)
    except FileExistsError:
        if destination.read_bytes() != serialized:
            raise FileExistsError(f"Evaluation report already exists with different contents: {destination}")
    report["report_path"] = str(destination)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, default=ARTIFACT_FILE)
    parser.add_argument("--output-dir", type=Path, default=METADATA_DIR)
    args = parser.parse_args(argv)
    result = evaluate(args.artifact, args.output_dir)
    print(json.dumps({
        "status": result["status"], "run_id": result["run_id"],
        "model": result["model"], "persistence_baseline": result["persistence_baseline"],
        "model_beats_persistence_on_mae": result["model_beats_persistence_on_mae"],
        "report": result["report_path"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
