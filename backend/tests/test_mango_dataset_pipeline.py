import csv
import json
from pathlib import Path

import pytest

from app import mango_dataset_pipeline as pipeline
from app import evaluate_mango_yield_model
from app import train_mango_holdout as train_mango_yield_model


@pytest.fixture
def mango_csv(tmp_path):
    """Small test-only fixture; the licensed source snapshot is not needed by CI."""
    source = tmp_path / "mango-fixture.csv"
    rows = []
    for year_index, year in enumerate(pipeline.EXPECTED_YEARS):
        area_total, production_total = pipeline.EXPECTED_TOTALS[year]
        for district_index in range(pipeline.EXPECTED_DISTRICT_COUNT):
            centered = (district_index - (pipeline.EXPECTED_DISTRICT_COUNT - 1) / 2) / 11
            area = area_total / pipeline.EXPECTED_DISTRICT_COUNT * (1 + centered * 0.04)
            production = production_total / pipeline.EXPECTED_DISTRICT_COUNT * (
                1 + centered * 0.12 + (year_index % 2) * centered * 0.02
            )
            rows.append({
                "state": "West Bengal",
                "district": f"Test District {district_index + 1:02d}",
                "crop": "Mango",
                "year": year,
                "estimate_round": "Final Estimate",
                "area_thousand_ha": f"{area:.6f}",
                "production_thousand_mt": f"{production:.6f}",
                "source_url": "https://wbfpih.wb.gov.in/download?id=test-fixture",
            })
    with source.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=pipeline.EXPECTED_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return source


def _check(report, check_id):
    return next(check for check in report["quality_checks"] if check["id"] == check_id)


def test_quality_report_versions_a_fixture_without_source_data(mango_csv, tmp_path):
    report = pipeline.inspect_mango_dataset(mango_csv)

    assert report["status"] == "PASS"
    assert report["dataset_version"] == f"sha256:{report['source_file_sha256']}"
    assert report["records"]["count"] == 88
    assert report["records"]["year_counts"] == {year: 22 for year in pipeline.EXPECTED_YEARS}
    assert all(check["status"] == "PASS" for check in report["quality_checks"])
    assert report["split"]["test_transition"] == {
        "from_year": "2023-24", "to_year": "2024-25", "rows": 22,
    }

    original = mango_csv.read_bytes()
    manifest = pipeline.write_versioned_report(report, tmp_path / "metadata")
    assert json.loads(manifest.read_text(encoding="utf-8"))["source_file_sha256"] == report["source_file_sha256"]
    assert pipeline.write_versioned_report(report, tmp_path / "metadata") == manifest
    assert mango_csv.read_bytes() == original


def test_duplicate_rows_fail_quality_gate(mango_csv, tmp_path):
    lines = mango_csv.read_text(encoding="utf-8-sig").splitlines()
    duplicate_file = tmp_path / "duplicate.csv"
    duplicate_file.write_text("\n".join(lines + [lines[1]]) + "\n", encoding="utf-8")

    report = pipeline.inspect_mango_dataset(duplicate_file)

    assert report["status"] == "FAIL"
    assert _check(report, "unique_district_year_examples")["status"] == "FAIL"
    assert _check(report, "unique_district_year_examples")["duplicate_rows"] == 1


def test_malformed_numeric_record_fails_quality_gate(mango_csv, tmp_path):
    with mango_csv.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    rows[0]["area_thousand_ha"] = "NaN"
    source = tmp_path / "malformed.csv"
    with source.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=pipeline.EXPECTED_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    report = pipeline.inspect_mango_dataset(source)

    assert report["status"] == "FAIL"
    assert _check(report, "numeric_types_and_finiteness")["status"] == "FAIL"
    assert _check(report, "numeric_types_and_finiteness")["invalid_cells"] == [
        {"row": 2, "field": "area_thousand_ha"},
    ]


def test_unapproved_source_host_fails_quality_gate(mango_csv, tmp_path):
    with mango_csv.open(newline="", encoding="utf-8-sig") as stream:
        rows = list(csv.DictReader(stream))
    rows[0]["source_url"] = "https://example.org/not-the-publisher.pdf"
    source = tmp_path / "wrong-source.csv"
    with source.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=pipeline.EXPECTED_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    report = pipeline.inspect_mango_dataset(source)

    assert report["status"] == "FAIL"
    assert _check(report, "source_provenance")["invalid_rows"] == [2]


def test_extra_csv_fields_are_detected(mango_csv, tmp_path):
    lines = mango_csv.read_text(encoding="utf-8-sig").splitlines()
    malformed = tmp_path / "extra-field.csv"
    malformed.write_text("\n".join([lines[0], lines[1] + ",surplus", *lines[2:]]) + "\n", encoding="utf-8")

    report = pipeline.inspect_mango_dataset(malformed)

    assert report["status"] == "FAIL"
    assert _check(report, "consistent_csv_record_width")["rows_with_extra_fields"] == [2]


def test_versioned_report_refuses_to_overwrite_different_contents(mango_csv, tmp_path):
    report = pipeline.inspect_mango_dataset(mango_csv)
    manifest = pipeline.write_versioned_report(report, tmp_path)
    altered = dict(report)
    altered["status"] = "FAIL"

    with pytest.raises(FileExistsError, match="bump MANIFEST_SCHEMA_VERSION"):
        pipeline.write_versioned_report(altered, tmp_path)
    assert json.loads(manifest.read_text(encoding="utf-8"))["status"] == "PASS"


def test_training_loader_uses_the_shared_quality_gate(tmp_path):
    with pytest.raises(ValueError, match="Dataset quality gate did not pass"):
        train_mango_yield_model.load_and_validate(tmp_path / "missing.csv")


def test_training_configuration_is_version_pinned():
    config, _ = train_mango_yield_model.load_config()
    assert config["dataset"]["expected_sha256"]
    assert len(config["dataset"]["expected_sha256"]) == 64
    assert config["split"]["strategy"] == "forward_temporal_holdout"
    assert config["split"]["validation_transitions"] == 0
    assert config["fit"]["epochs"] is None


def test_training_stops_when_configured_dataset_hash_differs(mango_csv, tmp_path):
    config, _ = train_mango_yield_model.load_config()
    config["dataset"]["path"] = str(mango_csv)
    config["dataset"]["expected_sha256"] = "0" * 64
    custom_config = tmp_path / "config.json"
    custom_config.write_text(json.dumps(config), encoding="utf-8")

    with pytest.raises(ValueError, match="checksum differs"):
        train_mango_yield_model.train(custom_config)


def test_training_artifact_and_separate_evaluator_are_reproducible(mango_csv, tmp_path):
    config, _ = train_mango_yield_model.load_config()
    config["dataset"]["path"] = str(mango_csv)
    config["dataset"]["expected_sha256"] = pipeline.inspect_mango_dataset(mango_csv)["source_file_sha256"]
    config["output"]["model_artifact"] = str(tmp_path / "model.json")
    config["output"]["metadata_dir"] = str(tmp_path / "metadata")
    custom_config = tmp_path / "config.json"
    custom_config.write_text(json.dumps(config), encoding="utf-8")

    artifact = train_mango_yield_model.train(custom_config)
    evaluation = evaluate_mango_yield_model.evaluate(
        tmp_path / "model.json", tmp_path / "evaluation"
    )
    repeated = evaluate_mango_yield_model.evaluate(
        tmp_path / "model.json", tmp_path / "evaluation"
    )

    assert artifact["run_id"] == evaluation["run_id"] == repeated["run_id"]
    assert artifact["dataset"]["dataset_version"].startswith("sha256:")
    assert evaluation["model"] == artifact["validation"]["model"]
    assert evaluation["persistence_baseline"] == artifact["validation"]["persistence_baseline"]
    assert evaluation["report_path"] == repeated["report_path"]
