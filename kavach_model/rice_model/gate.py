"""Fail-closed, machine-readable release requirements."""
import numpy as np


def release_gate(metrics,auc_lower,positives,coverage,years,evidence_blockers=()):
    def finite(v):return v is not None and np.isfinite(v)
    checks={
        'positive_brier_skill':finite(metrics.get('brier_skill')) and metrics['brier_skill']>0,
        'auc_lower_bound_above_055':finite(auc_lower) and auc_lower>.55,
        'beats_base_rate':finite(metrics.get('brier')) and finite(metrics.get('base_brier')) and metrics['brier']<metrics['base_brier'],
        'beats_persistence':finite(metrics.get('brier')) and finite(metrics.get('persistence_brier')) and metrics['brier']<metrics['persistence_brier'],
        'at_least_25_heldout_positives':positives>=25,
        'interval_coverage_within_5pp_of_80':finite(coverage) and abs(coverage-.8)<=.05+1e-12,
        'at_least_four_test_years':years>=4,
        'data_evidence_verified':not evidence_blockers,
    }
    reasons=[name for name,passed in checks.items() if not passed]
    return {'status':'released' if all(checks.values()) else 'withheld',
            'checks':checks,'failed_checks':reasons,'evidence_blockers':list(evidence_blockers)}
