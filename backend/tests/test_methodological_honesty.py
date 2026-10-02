"""Methodological guardrails for Kavach's live-only API."""
import pytest
from fastapi import HTTPException
from app import main


def test_validation_status_withholds_scoring():
    payload = main.validation_status()
    assert payload["status"] == "WITHHELD"
    assert payload["is_field_validated"] is False
    assert "risk_score" not in payload


def test_legacy_area_route_is_retired():
    with pytest.raises(HTTPException) as exc:
        main.live_area("legacy")
    assert exc.value.status_code == 410


def test_risk_assessment_route_is_disabled():
    with pytest.raises(HTTPException) as exc:
        main.village_detail("Unknown locality")
    assert exc.value.status_code == 410
    assert "withheld" in exc.value.detail.lower()


def test_health_discloses_live_only_policy():
    payload = main.health()
    assert payload["synthetic_risk_scoring"] is False
    assert "real providers only" in payload["provider_policy"]
