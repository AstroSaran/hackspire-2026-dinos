import csv

import pytest

from app import train_mango_yield_model as mango

requires_local_source=pytest.mark.skipif(not mango.DATA_FILE.exists(),
    reason='Integration assertion requires the local official mango snapshot; it is not redistributed')


@pytest.fixture(autouse=True)
def _isolated_artifact(tmp_path, monkeypatch):
    # Unit tests must never retrain or replace the running server's active release.
    monkeypatch.setattr(mango, "ARTIFACT_FILE", tmp_path / "mango.json")


def _district_rows(path):
    fields = ["state", "district", "crop", "year", "estimate_round",
              "area_thousand_ha", "production_thousand_mt", "source_url"]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for index in range(22):
            writer.writerow({
                "state": "West Bengal", "district": f"District {index}",
                "crop": "Mango", "year": "2021-22", "estimate_round": "Final Estimate",
                "area_thousand_ha": "0.001", "production_thousand_mt": "0.002",
                "source_url": "https://wbfpih.wb.gov.in/source.pdf",
            })


def test_source_totals_allow_only_accumulated_published_rounding(tmp_path, monkeypatch):
    path = tmp_path / "mango.csv"
    _district_rows(path)
    monkeypatch.setattr(mango, "DATA_FILE", path)
    # District values sum to 0.022; the 0.004 difference is possible when
    # 22 district figures and the source total are independently rounded.
    monkeypatch.setattr(mango, "EXPECTED_TOTALS", {"2021-22": (0.026, 0.044)})

    assert len(mango.load_and_validate()["2021-22"]) == 22


def test_source_totals_still_reject_mismatches_beyond_rounding(tmp_path, monkeypatch):
    path = tmp_path / "mango.csv"
    _district_rows(path)
    monkeypatch.setattr(mango, "DATA_FILE", path)
    monkeypatch.setattr(mango, "EXPECTED_TOTALS", {"2021-22": (0.04, 0.044)})

    with pytest.raises(ValueError, match="do not reconcile"):
        mango.load_and_validate()


@requires_local_source
def test_trained_artifact_is_selected_by_backtest_and_never_worse_than_retired_regression():
    artifact = mango.train()
    summary = artifact["validation"]["candidate_summary"]
    selected = artifact["selected_method"]
    assert artifact["version"].startswith("0.2")
    assert summary[selected]["mean_mae_t_per_ha"] <= summary["persistence"]["mean_mae_t_per_ha"]
    assert summary[selected]["mean_mae_t_per_ha"] < summary["pooled_lag_regression"]["mean_mae_t_per_ha"]
    assert artifact["validation"]["significance"].startswith("NOT_ESTABLISHED")
    assert artifact["release"]["production_decisions"] is False


@requires_local_source
def test_forecasts_have_ordered_intervals_and_cover_all_districts():
    artifact = mango.train()
    forecasts = artifact["experimental_forecasts"]
    assert len(forecasts) == 22
    for item in forecasts:
        assert item["interval_80_low"] <= item["yield_t_per_ha"] <= item["interval_80_high"]


@requires_local_source
def test_data_quality_flags_surface_known_source_anomalies():
    artifact = mango.train()
    found = {(f["district"], f["type"]) for f in artifact["data_quality_flags"]}
    assert ("Murshidabad", "YIELD_JUMP") in found
    assert ("Jalpaiguri", "AREA_BREAK") in found


def test_robust_persistence_needs_three_years_before_overriding_last_value():
    assert mango._robust_persistence([4.0, 9.0]) == 9.0          # level shift, not an outlier
    assert mango._robust_persistence([6.6, 6.6, 6.6, 3.0]) == 6.6  # one-off collapse is reverted
    assert mango._robust_persistence([6.6, 6.6, 6.6, 6.9]) == 6.9  # normal change is kept


@requires_local_source
def test_pooled_out_of_sample_metrics_are_reported_and_in_range():
    artifact = mango.train()
    pooled = artifact["validation"]["candidate_summary"][artifact["selected_method"]]["pooled_out_of_sample"]
    assert 0.0 <= pooled["share_within_10pct"] <= pooled["share_within_20pct"] <= 1.0
    assert pooled["r2"] is not None and pooled["r2"] > 0.7


def test_mango_endpoint_serves_forecasts_and_rejects_unknown_district(mango_source,monkeypatch):
    from fastapi import HTTPException
    from app import main
    from app.model_service import ModelService
    monkeypatch.setattr(mango,'DATA_FILE',mango_source)
    mango.train()
    monkeypatch.setattr(main,'mango_service',ModelService(mango.ARTIFACT_FILE,mango_source))
    payload = main.mango_yield_model(None)
    assert payload["release"]["production_decisions"] is False
    assert len(payload["forecasts"]) == 22
    assert "risk_score" not in payload
    one = main.mango_yield_model("malda")
    assert [f["district"] for f in one["forecasts"]] == ["Malda"]
    with pytest.raises(HTTPException) as exc:
        main.mango_yield_model("Atlantis")
    assert exc.value.status_code == 404
