"""Validate and version a locally supplied West Bengal mango snapshot.

The source CSV is not distributed until its reuse terms are confirmed. This
module does not fetch data or modify the input file; its tests use fixtures.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlsplit


BACKEND_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_DIR = BACKEND_DIR.parent
DATA_FILE = BACKEND_DIR / "data" / "wb_mango_district_annual.csv"
METADATA_DIR = BACKEND_DIR / "data" / "metadata"
DATASET_ID = "west-bengal-district-mango-annual"
MANIFEST_SCHEMA_VERSION = 2
PREPROCESSING_VERSION = "1.0.0"
EXPECTED_COLUMNS = [
    "state", "district", "crop", "year", "estimate_round",
    "area_thousand_ha", "production_thousand_mt", "source_url",
]
EXPECTED_YEARS = ["2021-22", "2022-23", "2023-24", "2024-25"]
EXPECTED_TOTALS = {
    "2021-22": (113.896, 942.985),
    "2022-23": (116.005, 1027.584),
    "2023-24": (116.162, 882.271),
    "2024-25": (122.067, 1080.264),
}
EXPECTED_DISTRICT_COUNT = 22
APPROVED_SOURCE_HOSTS = {"wbfpih.wb.gov.in"}


def _relative_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPOSITORY_DIR.resolve()).as_posix()
    except ValueError:
        return path.name


def _check(check_id: str, passed: bool, details: dict) -> dict:
    return {"id": check_id, "status": "PASS" if passed else "FAIL", **details}


def _quantile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _base_report(path: Path, digest: str | None, size: int | None) -> dict:
    return {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "dataset_id": DATASET_ID,
        "dataset_version": f"sha256:{digest}" if digest else None,
        "source_file": _relative_path(path),
        "source_file_sha256": digest,
        "source_file_bytes": size,
        "status": "FAIL",
        "provenance": {
            "description": "Annual final mango area and production estimates for West Bengal districts.",
            "publisher": "West Bengal Directorate of Horticulture / Food Processing Industries and Horticulture",
            "row_level_source_urls": [],
            "collection_date": None,
            "collection_date_note": "Not recorded in the checked-in snapshot; do not infer it from estimate years.",
            "original_source_artifacts_archived": False,
            "usage_conditions": "The repository does not record a reuse license for these source tables. Check each publisher's terms before redistribution.",
        },
        "schema": [],
        "records": {"count": 0, "year_counts": {}, "district_count": 0},
        "quality_checks": [],
        "derived_target": {
            "name": "annual_mango_yield",
            "formula": "production_thousand_mt / area_thousand_ha",
            "unit": "tonnes per hectare",
        },
        "preprocessing": {
            "version": PREPROCESSING_VERSION,
            "filtering_rules": [
                "Accept only West Bengal Mango final-estimate rows with positive area, nonnegative production, and HTTPS source URLs on wbfpih.wb.gov.in.",
                "Require one row for each district and year across all 22 districts and the four observed estimate years.",
                "Do not impute missing values or synthesize records.",
            ],
        },
        "split": {
            "method": "forward temporal holdout on the latest adjacent annual transition",
            "random_seed": None,
            "validation_set": None,
            "note": "Four annual vintages are insufficient for a separate stable validation period. The same districts appear in earlier years and the future-year holdout; this evaluates future years for known districts, not unseen-district generalization.",
            "train_transitions": [],
            "test_transition": None,
        },
    }


def inspect_mango_dataset(path: Path = DATA_FILE) -> dict:
    """Return a deterministic data-quality and provenance report for a CSV."""
    path = Path(path)
    try:
        content = path.read_bytes()
    except OSError as exc:
        report = _base_report(path, None, None)
        report["quality_checks"] = [_check("source_file_readable", False, {"error": type(exc).__name__})]
        return report

    digest = hashlib.sha256(content).hexdigest()
    report = _base_report(path, digest, len(content))
    try:
        text = content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text, newline=""))
        headers = reader.fieldnames or []
        rows = list(reader)
    except (UnicodeDecodeError, csv.Error) as exc:
        report["quality_checks"] = [
            _check("csv_parseable", False, {"error": type(exc).__name__})
        ]
        return report

    schema_ok = headers == EXPECTED_COLUMNS and len(headers) == len(set(headers))
    report["schema"] = [
        {"name": name, "type": "string" if name not in {"area_thousand_ha", "production_thousand_mt"} else "decimal"}
        for name in headers
    ]

    missing_fields = Counter()
    malformed_numeric = []
    invalid_scope = []
    invalid_sources = []
    invalid_labels = []
    malformed_rows = []
    duplicate_keys = Counter()
    by_year: dict[str, list[dict]] = defaultdict(list)
    valid_yields: list[tuple[float, str, str]] = []
    all_sources = set()

    for row_number, row in enumerate(rows, start=2):
        if not schema_ok:
            break
        if row.get(None) is not None:
            malformed_rows.append(row_number)
        for field in EXPECTED_COLUMNS:
            value = row.get(field)
            if value is None or not value.strip():
                missing_fields[field] += 1

        state = (row.get("state") or "").strip()
        district = (row.get("district") or "").strip()
        crop = (row.get("crop") or "").strip()
        year = (row.get("year") or "").strip()
        estimate_round = (row.get("estimate_round") or "").strip()
        source_url = (row.get("source_url") or "").strip()
        if source_url:
            all_sources.add(source_url)
        if state != "West Bengal" or crop.casefold() != "mango" or not district or estimate_round.casefold() != "final estimate":
            invalid_scope.append(row_number)
        key = (state, district.casefold(), crop.casefold(), year, estimate_round.casefold())
        duplicate_keys[key] += 1
        if source_url:
            parsed = urlsplit(source_url)
            if parsed.scheme != "https" or parsed.hostname not in APPROVED_SOURCE_HOSTS:
                invalid_sources.append(row_number)
        else:
            invalid_sources.append(row_number)

        numeric: dict[str, float] = {}
        for field in ("area_thousand_ha", "production_thousand_mt"):
            try:
                number = float(row[field])
                if not math.isfinite(number):
                    raise ValueError("non-finite")
                numeric[field] = number
            except (KeyError, TypeError, ValueError):
                malformed_numeric.append({"row": row_number, "field": field})
        if len(numeric) == 2:
            area = numeric["area_thousand_ha"]
            production = numeric["production_thousand_mt"]
            if area <= 0 or production < 0:
                invalid_labels.append(row_number)
            else:
                valid_yields.append((production / area, district, year))
            by_year[year].append({"area": area, "production": production, "district": district})

    duplicate_row_count = sum(count - 1 for count in duplicate_keys.values() if count > 1)
    year_counts = {year: len(values) for year, values in sorted(by_year.items())}
    districts_by_year = {year: {row["district"] for row in values} for year, values in by_year.items()}
    coverage_ok = (
        sorted(by_year) == EXPECTED_YEARS
        and all(len(by_year[year]) == EXPECTED_DISTRICT_COUNT for year in EXPECTED_YEARS)
        and all(len(districts_by_year[year]) == EXPECTED_DISTRICT_COUNT for year in EXPECTED_YEARS)
        and len({frozenset(names) for names in districts_by_year.values()}) == 1
    )

    total_differences = {}
    if schema_ok:
        for year, expected in EXPECTED_TOTALS.items():
            if year not in by_year:
                total_differences[year] = {"status": "missing_year"}
                continue
            area_sum = sum(row["area"] for row in by_year[year])
            production_sum = sum(row["production"] for row in by_year[year])
            area_delta = round(area_sum - expected[0], 6)
            production_delta = round(production_sum - expected[1], 6)
        total_differences[year] = {
            "area_delta_thousand_ha": area_delta,
            "production_delta_thousand_mt": production_delta,
            "matches_rounded_publisher_total": abs(area_delta) <= 0.012 and abs(production_delta) <= 0.012,
            "publisher_source_urls": sorted({row["source_url"] for row in rows if row["year"] == year and row["source_url"]}),
        }
    totals_ok = bool(total_differences) and all(
        item.get("matches_rounded_publisher_total", False) for item in total_differences.values()
    )

    yields = [item[0] for item in valid_yields]
    distribution_outliers = []
    if len(yields) >= 4:
        q1, q3 = _quantile(yields, 0.25), _quantile(yields, 0.75)
        iqr = q3 - q1
        lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        distribution_outliers = [
            {"district": district, "year": year, "yield_t_per_ha": round(value, 6)}
            for value, district, year in valid_yields if value < lower or value > upper
        ]
        distribution_details = {
            "method": "Tukey 1.5×IQR review flag; this is not an exclusion rule",
            "q1_t_per_ha": round(q1, 6), "q3_t_per_ha": round(q3, 6),
            "min_t_per_ha": round(min(yields), 6), "max_t_per_ha": round(max(yields), 6),
            "flagged_rows": distribution_outliers,
        }
        distribution_status = "PASS" if not distribution_outliers else "WARNING"
    else:
        distribution_details = {"note": "Not enough valid numeric rows for an outlier review."}
        distribution_status = "WARNING"

    checks = [
        _check("schema", schema_ok, {"expected_columns": EXPECTED_COLUMNS, "observed_columns": headers}),
        _check("non_empty_dataset", len(rows) > 0, {"row_count": len(rows)}),
        _check("missing_values", not missing_fields, {"missing_cells_by_field": dict(sorted(missing_fields.items()))}),
        _check("numeric_types_and_finiteness", not malformed_numeric, {"invalid_cells": malformed_numeric}),
        _check("consistent_csv_record_width", not malformed_rows, {"rows_with_extra_fields": malformed_rows}),
        _check("valid_target_inputs", not invalid_labels, {"invalid_area_or_production_rows": invalid_labels}),
        _check("geography_crop_and_estimate_scope", not invalid_scope, {"invalid_rows": invalid_scope}),
        _check("source_provenance", not invalid_sources, {
            "invalid_rows": invalid_sources, "approved_hosts": sorted(APPROVED_SOURCE_HOSTS),
        }),
        _check("unique_district_year_examples", duplicate_row_count == 0, {
            "duplicate_rows": duplicate_row_count,
        }),
        _check("complete_district_year_coverage", coverage_ok, {
            "expected_years": EXPECTED_YEARS, "year_counts": year_counts,
            "districts_per_year": {year: len(names) for year, names in sorted(districts_by_year.items())},
            "district_sets_match_across_years": len({frozenset(names) for names in districts_by_year.values()}) == 1,
        }),
        _check("publisher_total_reconciliation", totals_ok, {"year_deltas": total_differences}),
    ]
    checks.append({"id": "target_distribution_review", "status": distribution_status, **distribution_details})

    ordered_years = sorted(by_year, key=lambda value: (value[:4], value))
    transitions = list(zip(ordered_years, ordered_years[1:]))
    report["provenance"]["row_level_source_urls"] = sorted(all_sources)
    report["records"] = {
        "count": len(rows),
        "year_counts": year_counts,
        "district_count": len(set().union(*districts_by_year.values())) if districts_by_year else 0,
        "yield_summary_t_per_ha": {
            "min": round(min(yields), 6), "max": round(max(yields), 6),
            "mean": round(sum(yields) / len(yields), 6),
        } if yields else None,
    }
    if transitions:
        test_transition = transitions[-1]
        train_transitions = transitions[:-1]
        report["split"]["train_transitions"] = [
            {"from_year": prior, "to_year": following,
             "rows": min(len(districts_by_year.get(prior, set())), len(districts_by_year.get(following, set())))}
            for prior, following in train_transitions
        ]
        report["split"]["test_transition"] = {
            "from_year": test_transition[0], "to_year": test_transition[1],
            "rows": min(len(districts_by_year.get(test_transition[0], set())), len(districts_by_year.get(test_transition[1], set()))),
        }
        train_target_years = {following for _, following in train_transitions}
        test_districts = districts_by_year.get(test_transition[0], set()) & districts_by_year.get(test_transition[1], set())
        report["split"]["estimand"] = "future annual yield for districts with prior-year yield history"
        report["split"]["test_train_district_overlap"] = len(
            set().union(*districts_by_year.values()) & test_districts
        ) if districts_by_year else 0
        report["quality_checks"].append(_check(
            "forward_split_temporal_integrity",
            bool(train_transitions) and test_transition[1] not in train_target_years
            and all(following < test_transition[1] for _, following in train_transitions),
            {
                "training_target_years": sorted(train_target_years),
                "test_target_year": test_transition[1],
                "district_groups_overlap_by_design": True,
                "test_train_district_overlap": report["split"]["test_train_district_overlap"],
            },
        ))
    report["quality_checks"] = checks
    if any(check["status"] == "FAIL" for check in checks):
        report["status"] = "FAIL"
    elif any(check["status"] == "WARNING" for check in checks):
        report["status"] = "PASS_WITH_WARNINGS"
    else:
        report["status"] = "PASS"
    return report


def write_versioned_report(report: dict, metadata_dir: Path = METADATA_DIR) -> Path:
    """Write an immutable, content-addressed report; never overwrite a version."""
    digest = report.get("source_file_sha256")
    if not digest:
        raise ValueError("Cannot version a quality report without a source file checksum.")
    metadata_dir = Path(metadata_dir)
    metadata_dir.mkdir(parents=True, exist_ok=True)
    destination = metadata_dir / (
        f"{DATASET_ID}-manifest-v{MANIFEST_SCHEMA_VERSION}-{digest[:16]}.json"
    )
    serialized = (json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    try:
        with destination.open("xb") as stream:
            stream.write(serialized)
    except FileExistsError:
        if destination.read_bytes() != serialized:
            raise FileExistsError(
                f"Versioned report already exists with different contents: {destination}; "
                "bump MANIFEST_SCHEMA_VERSION before changing its format."
            )
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DATA_FILE, help="CSV source snapshot to inspect")
    parser.add_argument("--metadata-dir", type=Path, default=METADATA_DIR)
    args = parser.parse_args(argv)
    report = inspect_mango_dataset(args.source)
    try:
        report_path = write_versioned_report(report, args.metadata_dir)
    except ValueError as exc:
        print(json.dumps({"status": "FAIL", "error": str(exc)}, indent=2))
        return 2
    failed = [check["id"] for check in report["quality_checks"] if check["status"] != "PASS"]
    print(json.dumps({
        "status": report["status"],
        "dataset_version": report["dataset_version"],
        "records": report["records"]["count"],
        "failed_or_warning_checks": failed,
        "quality_report": str(report_path),
    }, indent=2))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
