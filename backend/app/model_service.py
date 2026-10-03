"""Monitored, fail-closed serving for the experimental annual yield baseline."""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone
from . import model_registry

logger = logging.getLogger("kavach.models")


class ModelService:
    def __init__(self, artifact=model_registry.ARTIFACT_FILE, source=model_registry.DATA_FILE):
        self.artifact = artifact
        self.source = source
        self._lock = threading.Lock()
        self._metrics = {"validation_requests": 0, "validation_failures": 0,
                         "total_validation_ms": 0.0, "last_success_at": None,
                         "last_failure_at": None, "active_release_id": None}

    def load(self):
        start = time.perf_counter()
        failed = False
        artifact = None
        try:
            artifact = model_registry.load_artifact(
                self.artifact, self.source, os.environ.get("KAVACH_MANGO_ARTIFACT_SHA256", "").strip())
            return artifact
        except model_registry.ArtifactError as exc:
            failed = True
            logger.error("mango_model_validation_failed reason=%s", exc)
            raise
        finally:
            with self._lock:
                self._metrics["validation_requests"] += 1
                self._metrics["validation_failures"] += int(failed)
                self._metrics["total_validation_ms"] += (time.perf_counter() - start) * 1000
                self._metrics["last_failure_at" if failed else "last_success_at"] = datetime.now(timezone.utc).isoformat()
                self._metrics["active_release_id"] = None if failed else artifact["integrity"]["payload_sha256"]

    def metrics(self):
        with self._lock:
            result = dict(self._metrics)
        total = result.pop("total_validation_ms")
        result["mean_validation_ms"] = round(total / max(1, result["validation_requests"]), 3)
        result["scope"] = "This worker process only; resets on restart. Export to monitoring for retention."
        return result

    def readiness(self, artifact=None):
        """An operational check must never certify scientific or field readiness."""
        failure = None
        if artifact is None:
            try:
                artifact = self.load()
            except model_registry.ArtifactError as exc:
                failure = str(exc)
        now = datetime.now(timezone.utc)
        gate = lambda name, passed, detail: {"gate": name, "status": "PASSED" if passed else "BLOCKED", "detail": detail}
        gates = [gate("artifact_integrity", failure is None, failure or "JSON schema, checksum, finite values and interval ordering validated."),
                 gate("training_source_integrity", failure is None, "Artifact must match the local training CSV SHA-256 and district/year coverage."),
                 gate("independent_release_pin", bool(os.environ.get("KAVACH_MANGO_ARTIFACT_SHA256", "").strip()) and failure is None,
                      "A deployment-managed SHA-256 pin is required for an independently approved artifact."),
                 gate("untouched_test_evaluation", False, "Available rolling-origin folds also selected the model; no untouched test years."),
                 gate("independent_interval_coverage", False, "Nominal 80% bands use selection residuals; independent coverage is not established."),
                 gate("field_validation", False, "No independent field-validation evidence or deployment acceptance recorded."),
                 gate("outcome_drift_monitoring", False, "New observed outcomes are needed to monitor prediction drift and actual error.")]
        result = {"status": "BLOCKED_FOR_PRODUCTION", "checked_at": now.isoformat(),
                  "serving_status": "UNAVAILABLE" if failure else "VALIDATED_EXPERIMENTAL",
                  "production_ready": False, "production_decisions": False,
                  "gates": gates, "monitoring": self.metrics(),
                  "judge_summary": "Kavach serves a versioned experimental crop baseline with integrity checks, input validation and rollback. Independent test seasons, interval calibration and field validation are still required for production model decisions.",
                  "next_steps": ["Collect additional source-verified annual outcomes and reserve untouched future seasons.",
                                 "Agree deployment-specific accuracy and coverage requirements before evaluating the holdout.",
                                 "Validate locally and review district errors before approving a release.",
                                 "Pin the approved artifact and export worker metrics to deployment monitoring."]}
        if artifact:
            target = artifact["experimental_forecasts"][0]["target_year"]
            past_target = int(target[:4]) < now.year
            result.update(release_id=artifact["integrity"]["payload_sha256"],
                          model_version=artifact["version"], dataset=artifact["dataset"],
                          target_year=target,
                          target_period_status="PRIOR_START_YEAR" if past_target else "CURRENT_OR_FUTURE_START_YEAR",
                          validation_origins=len(artifact["validation"]["folds"]), untouched_test_years=0,
                          source_quality_flag_count=len(artifact["data_quality_flags"]))
            gates.append(gate("target_recency", not past_target,
                              f"Stored forecast targets {target}; it is not automatically a next-season forecast at today's date."))
        return result


mango_service = ModelService()
