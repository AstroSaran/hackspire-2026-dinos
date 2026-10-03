import copy
import csv
import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from app import main, model_registry as registry, train_mango_yield_model as trainer
from app.model_service import ModelService


@pytest.fixture
def trained(tmp_path, monkeypatch, mango_source):
    path = tmp_path / "active.json"
    monkeypatch.setattr(trainer, "ARTIFACT_FILE", path)
    monkeypatch.setattr(trainer, "DATA_FILE", mango_source)
    artifact = trainer.train()
    return artifact, path, trainer.DATA_FILE, tmp_path / "model_releases"


def resign(artifact):
    artifact["integrity"] = {"algorithm": "sha256", "payload_sha256": registry.digest(artifact)}
    return artifact


def test_corruption_and_source_changes_fail_closed(trained, tmp_path):
    artifact, path, source, _ = trained
    artifact["experimental_forecasts"][0]["yield_t_per_ha"] += 1
    path.write_text(json.dumps(artifact))
    with pytest.raises(registry.ArtifactError, match="checksum"):
        registry.load_artifact(path, source)
    path.write_text(json.dumps(resign(artifact)))
    changed = tmp_path / "changed.csv"
    changed.write_bytes(source.read_bytes() + b"\n")
    with pytest.raises(registry.ArtifactError, match="Training data changed"):
        registry.load_artifact(path, changed)


@pytest.mark.parametrize("mutate", [
    lambda a: a["experimental_forecasts"][0].update(interval_80_low=-1),
    lambda a: a["experimental_forecasts"][0].update(interval_80_high=0),
    lambda a: a["experimental_forecasts"][0].update(target_year="2029-30"),
    lambda a: a["experimental_forecasts"][0].update(district="Atlantis"),
    lambda a: a["validation"]["folds"][0]["history_years"].append("2024-25"),
    lambda a: a["release"].update(production_decisions=True),
    lambda a: a["validation"].update(untouched_test_years=2),
    lambda a: a["evaluation_predictions"][0].update(actual_t_per_ha=999),
])
def test_semantically_invalid_artifacts_are_rejected_even_with_checksum(trained, mutate):
    artifact, _, source, _ = trained
    mutate(artifact)
    with pytest.raises(registry.ArtifactError):
        registry.validate_artifact(resign(artifact), source.read_bytes())


def test_nonfinite_and_malformed_json_are_rejected(trained):
    artifact, path, source, _ = trained
    artifact["experimental_forecasts"][0]["yield_t_per_ha"] = float("nan")
    path.write_text(json.dumps(artifact))
    with pytest.raises(registry.ArtifactError):
        registry.load_artifact(path, source)
    path.write_text('{"partial":')
    with pytest.raises(registry.ArtifactError, match="valid JSON"):
        registry.load_artifact(path, source)


def test_publish_retains_release_and_rollback_validates_it(trained):
    artifact, path, source, releases = trained
    old_id = registry.digest(artifact)
    updated = copy.deepcopy(artifact)
    updated["version"] = "0.2.2-experimental"
    registry.publish(updated, path, source, releases)
    assert registry.load_artifact(path, source)["version"] == "0.2.2-experimental"
    registry.activate(old_id, path, source, releases)
    assert registry.load_artifact(path, source) == artifact
    with pytest.raises(registry.ArtifactError, match="full SHA"):
        registry.activate("../../bad", path, source, releases)


def test_invalid_publish_does_not_replace_active_file(trained):
    artifact, path, source, releases = trained
    before = path.read_bytes()
    artifact["release"]["production_decisions"] = True
    with pytest.raises(registry.ArtifactError):
        registry.publish(artifact, path, source, releases)
    assert path.read_bytes() == before


def test_independent_digest_pin_checked(trained):
    artifact, path, source, _ = trained
    assert registry.load_artifact(path, source, registry.digest(artifact))
    with pytest.raises(registry.ArtifactError, match="deployment digest pin"):
        registry.load_artifact(path, source, "0" * 64)


def test_serving_api_returns_503_and_counts_failures(trained, monkeypatch):
    _, path, source, _ = trained
    service = ModelService(path, source)
    monkeypatch.setattr(main, "mango_service", service)
    monkeypatch.delenv("KAVACH_MANGO_ARTIFACT_SHA256", raising=False)
    client = TestClient(main.app)
    good = client.get("/models/mango-yield?district=Malda")
    assert good.status_code == 200
    assert good.json()["evaluation"]["role"] == "MODEL_SELECTION"
    assert good.json()["forecasts"][0]["district"] == "Malda"
    path.write_text("{}")
    bad = client.get("/models/mango-yield")
    assert bad.status_code == 503
    assert "forecasts" not in bad.json()
    assert bad.headers["cache-control"] == "no-store"
    readiness = client.get("/models/readiness").json()
    assert readiness["production_ready"] is False
    assert readiness["serving_status"] == "UNAVAILABLE"
    assert service.metrics()["validation_failures"] == 2
    assert service.metrics()["active_release_id"] is None


def test_validated_artifact_does_not_claim_production_ready(trained, monkeypatch):
    _, path, source, _ = trained
    monkeypatch.delenv("KAVACH_MANGO_ARTIFACT_SHA256", raising=False)
    result = ModelService(path, source).readiness()
    assert result["serving_status"] == "VALIDATED_EXPERIMENTAL"
    assert result["production_ready"] is False
    assert result["untouched_test_years"] == 0
    assert any(g["gate"] == "field_validation" and g["status"] == "BLOCKED" for g in result["gates"])


@pytest.mark.parametrize("invalid", ["nan", "inf", "-inf"])
def test_training_rejects_nonfinite_source(trained, tmp_path, monkeypatch, invalid):
    _, _, source, _ = trained
    changed = tmp_path / "invalid.csv"
    with source.open(newline='',encoding='utf-8') as stream:
        rows=list(csv.DictReader(stream))
    rows[0]['area_thousand_ha']=invalid
    with changed.open('w',newline='',encoding='utf-8') as stream:
        writer=csv.DictWriter(stream,fieldnames=rows[0]);writer.writeheader();writer.writerows(rows)
    monkeypatch.setattr(trainer, "DATA_FILE", changed)
    with pytest.raises(ValueError, match="Invalid area"):
        trainer.load_and_validate()


def test_evaluation_rows_reproduce_reported_mae(trained):
    artifact, _, source, _ = trained
    rows = artifact["evaluation_predictions"]
    assert len(rows) == 44
    assert artifact["dataset"]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    actual = [r["actual_t_per_ha"] for r in rows]
    predicted = [r["predicted_t_per_ha"] for r in rows]
    measured = trainer.metrics(actual, predicted)
    assert measured["mae_t_per_ha"] == artifact["validation"]["candidate_summary"][artifact["selected_method"]]["pooled_out_of_sample"]["mae_t_per_ha"]
