"""Readiness gates and verified public support links for West Bengal.

The service intentionally emits no livelihood risk scores. Each target needs
local, authorized outcome labels and independent temporal/spatial validation.
"""


TRACKS = [
    {
        "id": "crop_weather_stress",
        "name": "Crop and weather stress",
        "horizon": "7 days",
        "status": "WITHHELD",
        "prediction": None,
        "required_evidence": [
            "Verified crop, sowing-stage, and field-condition observations for each district/season",
            "Dated crop-stress or crop-loss outcomes matched to those observations",
            "Live forecast inputs available at each prediction time",
        ],
        "blockers": [
            "The annual West Bengal crop-production dataset is district/crop/season history; it does not label current field stress.",
            "No authorized, district-matched historical crop-stress outcomes are connected for training or validation.",
        ],
    },
    {
        "id": "mgnrega_access_shortfall",
        "name": "MGNREGA work-access shortfall",
        "horizon": "30 days",
        "status": "WITHHELD",
        "prediction": None,
        "required_evidence": [
            "Dated work demand and work provided at the same district and reporting period",
            "Historical shortfall outcomes defined before model fitting",
            "Clear rural coverage and reporting definitions for each district",
        ],
        "blockers": [
            "The current MGNREGA resource UUID is not configured, so the statewide API feed is not connected.",
            "District aggregates cannot establish an individual household's demand or access to work.",
            "Historical outcome labels have not been collected for the proposed forecast horizon.",
        ],
    },
    {
        "id": "livelihood_disruption",
        "name": "Broader livelihood disruption",
        "horizon": "To be preregistered",
        "status": "WITHHELD",
        "prediction": None,
        "required_evidence": [
            "A measurable disruption outcome and forecast horizon agreed with intended users",
            "Privacy-safe, authorized outcomes across relevant livelihood groups",
            "District-matched market, employment, climate, and locally observed impact records across West Bengal",
        ],
        "blockers": [
            "‘Livelihood disruption’ does not yet have a defined observable target or prediction horizon.",
            "Public feeds are contextual aggregates and are not validated district or household outcome labels.",
            "No real historical outcomes are available for training or independent evaluation.",
        ],
    },
]


def readiness(market_status: str, employment_status: str) -> dict:
    """Describe the three requested tracks without fabricating predictions."""
    tracks = [dict(track) for track in TRACKS]
    tracks[1]["blockers"] = [
        (f"MGNREGA source status: {employment_status}; a configured feed is still only district context."),
        *TRACKS[1]["blockers"][1:],
    ]
    tracks[2]["blockers"] = [
        (f"Market source status: {market_status}; market records alone cannot label livelihood disruption."),
        *TRACKS[2]["blockers"][1:],
    ]
    return {
        "status": "WITHHELD",
        "model": {
            "name": "Kavach Multi-Track Livelihood Prediction",
            "version": "0.1.0-readiness",
            "training_status": "NOT_TRAINED",
            "field_validation_status": "NOT_VALIDATED",
        },
        "readiness": "BLOCKED_ON_REAL_LOCAL_OUTCOMES_AND_VALIDATION",
        "release_status": "NOT_FOR_PRODUCTION_DECISIONS",
        "summary": "Scope: all districts returned by the West Bengal public datasets. No track emits a score until real matched outcomes are collected and independently validated.",
        "prediction_tracks": tracks,
        "production_gates": [
            {"gate": "Target and horizon preregistered per track", "status": "INCOMPLETE",
             "detail": "Crop stress and MGNREGA shortfall have proposed 7-day and 30-day horizons; broader disruption still needs an agreed measurable target."},
            {"gate": "Real, authorized local outcome data", "status": "NOT_AVAILABLE",
             "detail": "West Bengal source records are not currently reachable from the Kavach backend. Every label needs provenance, date, district, collection method, and permission. Generated or representative training rows are prohibited."},
            {"gate": "Leakage-safe spatial and temporal evaluation", "status": "NOT_RUN",
             "detail": "Hold out whole locations and later periods; do not split repeated or nearby observations across training and evaluation."},
            {"gate": "Calibration and subgroup evaluation", "status": "NOT_RUN",
             "detail": "Measure calibration, errors, missingness, and false negatives across relevant locations and livelihood groups."},
            {"gate": "Monitoring, abstention, and rollback", "status": "NOT_IMPLEMENTED",
             "detail": "Each deployed track needs input-freshness checks, out-of-domain abstention, drift monitoring, versioning, and rollback."},
        ],
        "next_steps": [
            "Restore outbound HTTPS access from the Kavach backend to api.data.gov.in, then collect every West Bengal page and keep the raw source response with fetch time and resource ID.",
            "Use annual crop records only for a separately named district/crop/season production or yield analysis; they cannot train a seven-day crop-stress model.",
            "Configure a current MGNREGA resource UUID and confirm its fields and reporting period before analyzing district work provision.",
            "Collect consented district-season crop-stress outcomes and dated district employment outcomes before fitting those risk models.",
        ],
        "advisory_resources": [
            {"title": "West Bengal Matir Katha", "action": "Use the area-, season-, and crop-specific state advisory and check with the local agriculture office before changing crops. Statewide averages alone are not a crop-switch recommendation.", "url": "https://matirkatha.wb.gov.in/"},
            {"title": "Soil Health Card", "action": "Base soil amendments and fertilizer decisions on the farmer's own soil test and card.", "url": "https://soilhealth.dac.gov.in/"},
            {"title": "Bangla Shasya Bima", "action": "Check current notified crop, season, enrollment window, and claim rules in the West Bengal scheme portal.", "url": "https://matirkatha.wb.gov.in/"},
            {"title": "PMFBY crop insurance and loss helpline", "action": "Check eligibility and report a covered crop-loss event through the official portal; helpline 14447.", "url": "https://pmfby.gov.in/farmerApplicationForm"},
            {"title": "MGNREGA official portal", "action": "Check current district/block/panchayat records with the local Gram Panchayat; district totals are not proof of an individual's work demand or entitlement.", "url": "https://nrega.nic.in/"},
        ],
        "training_data_policy": "REAL, provenance-documented, use-authorized observations only; no generated, imputed, or representative training rows.",
    }
