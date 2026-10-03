"""Validated JSON-only model releases with atomic activation and offline rollback.

Checksums detect corruption. An optional deployment-managed digest pin supplies
an independent trust anchor; a self-checksum is not a signature or field validation.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
ARTIFACT_FILE = DATA_DIR / "mango_yield_baseline_model.json"
DATA_FILE = DATA_DIR / "wb_mango_district_annual.csv"
RELEASE_DIR = DATA_DIR / "model_releases"
METHODS = {"persistence", "expanding_median", "blend_last_median",
           "robust_persistence", "pooled_lag_regression"}
MAX_ARTIFACT_BYTES = 2_000_000


class ArtifactError(ValueError):
    """An artifact failed a serving or publication gate."""


def digest(artifact: dict) -> str:
    payload = {k: v for k, v in artifact.items() if k != "integrity"}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _require(condition, message):
    if not condition:
        raise ArtifactError(message)


def _finite(value, minimum=None):
    return (type(value) in (int, float) and math.isfinite(value)
            and (minimum is None or value >= minimum))


def _year(value):
    _require(isinstance(value, str) and re.fullmatch(r"20\d{2}-\d{2}", value), "Invalid crop year.")
    _require((int(value[:4]) + 1) % 100 == int(value[-2:]), "Invalid crop-year range.")
    return int(value[:4])


def validate_artifact(artifact: dict, source_bytes: bytes, expected_digest: str = "") -> dict:
    """Fail closed on malformed output, changed source, or contradictory release metadata."""
    try:
        _require(isinstance(artifact, dict), "Artifact must be an object.")
        calculated = digest(artifact)  # also rejects NaN/Infinity anywhere in the payload
        _require(artifact.get("schema_version") == 1, "Unsupported model artifact schema.")
        _require(artifact["integrity"] == {"algorithm": "sha256", "payload_sha256": calculated},
                 "Artifact checksum mismatch; rebuild or roll back the release.")
        if expected_digest:
            _require(calculated == expected_digest, "Artifact does not match the deployment digest pin.")
        _require(artifact["status"] == "TRAINED_EXPERIMENTAL", "Unsupported release status.")
        _require(artifact["selected_method"] in METHODS, "Unknown model method.")
        _require(artifact["target_unit"] == "tonnes per hectare", "Unexpected target unit.")
        _require(artifact["release"]["production_decisions"] is False
                 and artifact["release"]["livelihood_distress_prediction"] is False
                 and artifact["release"]["field_validation"] == "not performed",
                 "This artifact contract is restricted to experimental crop-yield serving.")
        trained = datetime.fromisoformat(artifact["training_completed_at"])
        _require(trained.tzinfo is not None and trained <= datetime.now(timezone.utc),
                 "Training timestamp must be timezone-aware and not in the future.")
        _require(bool(artifact["model_name"]) and bool(artifact["version"])
                 and bool(artifact["limitations"]), "Missing model documentation.")

        dataset = artifact["dataset"]
        _require(dataset["sha256"] == hashlib.sha256(source_bytes).hexdigest(),
                 "Training data changed; retrain before serving forecasts.")
        source = list(csv.DictReader(io.StringIO(source_bytes.decode("utf-8-sig"))))
        districts = {row["district"] for row in source}
        years = sorted({row["year"] for row in source}, key=_year)
        starts = [_year(y) for y in years]
        _require(len(years) >= 3 and all(b == a + 1 for a, b in zip(starts, starts[1:])),
                 "Training years must be consecutive with at least three years.")
        _require(dataset["years"] == years and dataset["rows"] == len(source),
                 "Dataset metadata does not match the source.")
        _require(artifact["geography"] == {"state": "West Bengal", "district_count": len(districts)},
                 "Geography does not match the source.")
        _require(len(source) == len(districts) * len(years)
                 and len({(r["district"], r["year"]) for r in source}) == len(source),
                 "Source district/year panel is incomplete or duplicated.")
        predictions = artifact["experimental_forecasts"]
        _require(len(predictions) == len(districts)
                 and {p["district"] for p in predictions} == districts, "Forecast district coverage mismatch.")
        target = f"{starts[-1] + 1}-{(starts[-1] + 2) % 100:02d}"
        for prediction in predictions:
            _require(prediction["target_year"] == target, "Forecast target must follow the training years.")
            low, point, high = (prediction[k] for k in ("interval_80_low", "yield_t_per_ha", "interval_80_high"))
            _require(all(_finite(v, 0) for v in (low, point, high)) and low <= point <= high,
                     "Forecast values and intervals must be finite, nonnegative and ordered.")

        validation = artifact["validation"]
        folds = validation["folds"]
        _require([f["target_year"] for f in folds] == years[2:], "Backtest forecast origins are incomplete.")
        for index, fold in enumerate(folds, start=2):
            _require(fold["history_years"] == years[:index], "Backtest uses future or missing history.")
        summaries = validation["candidate_summary"]
        _require(set(summaries) == METHODS, "Candidate comparison is incomplete.")
        for name, summary in summaries.items():
            _require(_finite(summary["mean_mae_t_per_ha"], 0), "Invalid selection error.")
            scores = summary["pooled_out_of_sample"]
            for key in ("mae_t_per_ha", "rmse_t_per_ha", "wape_area_weighted"):
                _require(_finite(scores[key], 0), "Invalid backtest error metric.")
            r2 = scores["r2"]
            _require(r2 is None or (_finite(r2) and r2 <= 1), "Invalid R-squared.")
            shares = [scores[k] for k in ("share_within_10pct", "share_within_20pct")]
            _require(all(_finite(v, 0) and v <= 1 for v in shares) and shares[0] <= shares[1],
                     "Invalid backtest coverage shares.")
        selected = artifact["selected_method"]
        _require(summaries[selected]["mean_mae_t_per_ha"] ==
                 min(s["mean_mae_t_per_ha"] for s in summaries.values()), "Selected model did not win validation.")
        _require(_finite(validation["interval_80_relative_half_width"], 0), "Invalid uncertainty band.")
        _require(validation["evaluation_role"] == "MODEL_SELECTION"
                 and validation["untouched_test_years"] == 0
                 and validation["interval_calibration"] == "SELECTION_RESIDUALS_NOT_INDEPENDENT",
                 "Validation must disclose model-selection reuse and unvalidated bands.")
        _require(len(artifact["evaluation_predictions"]) == len(folds) * len(districts),
                 "Missing selected-model evaluation rows.")
        expected_keys = {(district, year) for district in districts for year in years[2:]}
        observations = {(row["district"], row["year"]): row for row in source}
        evaluations = artifact["evaluation_predictions"]
        _require({(row["district"], row["target_year"]) for row in evaluations} == expected_keys,
                 "Evaluation rows have duplicate or unknown district/year keys.")
        for row in evaluations:
            _require(all(_finite(row[k], 0) for k in ("actual_t_per_ha", "area_thousand_ha"))
                     and _finite(row["predicted_t_per_ha"]), "Invalid evaluation values.")
            observed = observations[(row["district"], row["target_year"])]
            area = float(observed["area_thousand_ha"])
            _require(area > 0 and math.isclose(row["actual_t_per_ha"], float(observed["production_thousand_mt"]) / area)
                     and math.isclose(row["area_thousand_ha"], area), "Evaluation targets differ from the source.")
        calculated_mae = round(sum(abs(row["predicted_t_per_ha"] - row["actual_t_per_ha"])
                                   for row in evaluations) / len(evaluations), 4)
        _require(calculated_mae == summaries[selected]["pooled_out_of_sample"]["mae_t_per_ha"],
                 "Reported error does not match the evaluation rows.")
        _require(isinstance(artifact["data_quality_flags"], list), "Missing source quality report.")
        for flag in artifact["data_quality_flags"]:
            _require(flag["district"] in districts and isinstance(flag["type"], str)
                     and isinstance(flag["detail"], str), "Invalid source quality flag.")
    except ArtifactError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError) as exc:
        raise ArtifactError("Malformed or non-finite model artifact.") from exc
    return artifact


def load_artifact(path: Path = ARTIFACT_FILE, source: Path = DATA_FILE, expected_digest: str = "") -> dict:
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_ARTIFACT_BYTES + 1)
        _require(len(raw) <= MAX_ARTIFACT_BYTES, "Artifact is too large.")
        artifact = json.loads(raw)
        return validate_artifact(artifact, source.read_bytes(), expected_digest)
    except OSError as exc:
        raise ArtifactError("Model artifact or training dataset is missing or unreadable.") from exc
    except (ValueError, TypeError) as exc:
        if isinstance(exc, ArtifactError):
            raise
        raise ArtifactError("Model artifact is not valid JSON.") from exc


def atomic_write(path: Path, payload: bytes):
    """Readers see either the old complete release or the new complete release."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".model-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def publish(artifact: dict, path: Path = ARTIFACT_FILE, source: Path = DATA_FILE,
            releases: Path = RELEASE_DIR):
    artifact["integrity"] = {"algorithm": "sha256", "payload_sha256": digest(artifact)}
    validate_artifact(artifact, source.read_bytes())
    raw = json.dumps(artifact, indent=2, ensure_ascii=False, allow_nan=False).encode() + b"\n"
    # Archive an existing valid release before changing the active file.
    if path.exists():
        try:
            previous = load_artifact(path, source)
        except ArtifactError:
            previous = None  # Legacy/invalid files are never rollback candidates.
        if previous:
            atomic_write(releases / f"{digest(previous)}.json",
                         json.dumps(previous, ensure_ascii=False, allow_nan=False).encode())
    atomic_write(releases / f"{digest(artifact)}.json", raw)
    atomic_write(path, raw)


def activate(release_id: str, path: Path = ARTIFACT_FILE, source: Path = DATA_FILE,
             releases: Path = RELEASE_DIR):
    _require(bool(re.fullmatch(r"[a-f0-9]{64}", release_id)), "Use a full SHA-256 release ID.")
    artifact = load_artifact(releases / f"{release_id}.json", source, release_id)
    atomic_write(path, json.dumps(artifact, ensure_ascii=False, allow_nan=False).encode() + b"\n")
    return artifact


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--activate", metavar="SHA256", help="Validate and atomically activate an archived release")
    parser.add_argument("--list", action="store_true", help="List locally archived release IDs")
    args = parser.parse_args()
    if args.activate:
        result = activate(args.activate)
        print(json.dumps({"activated": digest(result), "production_decisions": False}))
    elif args.list:
        print(json.dumps(sorted(p.stem for p in RELEASE_DIR.glob("*.json"))))
    else:
        result = load_artifact(expected_digest=os.environ.get("KAVACH_MANGO_ARTIFACT_SHA256", ""))
        print(json.dumps({"validated": digest(result), "version": result["version"]}))
