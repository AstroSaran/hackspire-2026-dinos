# Kavach API Documentation

Base URL: `http://localhost:8000` (development)

## Core Endpoints

### List All Villages

```http
GET /villages
```

Returns a list of all villages with their risk scores and status.

**Response:**
```json
{
  "pilot_mode_banner": "...",
  "villages": [
    {
      "village": "Bagula",
      "zone": "North",
      "estimated_risk_score": 71,
      "status": "risk"
    }
  ]
}
```

**Status Values:**
- `stable` (0-34): Low risk
- `watch` (35-54): Moderate risk
- `risk` (55-74): High risk
- `critical` (75-100): Critical risk

---

### Get Village Details

```http
GET /villages/{village}
```

Returns comprehensive assessment for a specific village.

**Parameters:**
- `village` (path): Village name (case-insensitive)

**Response Structure:**
```json
{
  "village": "Bagula",
  "zone": "North",
  "pilot_mode_banner": "...",
  "data_coverage": {
    "weather": "LIVE|STALE|UNAVAILABLE|SIMULATED_DEMO",
    "crop": "SIMULATED",
    "market": "SIMULATED",
    "employment": "SIMULATED",
    "water": "SIMULATED",
    "vulnerability": "SIMULATED"
  },
  "weather": {
    "observation": {...},
    "forecast": {...},
    "warnings": [...],
    "derived_rainfall_anomaly": -15.2
  },
  "observed_signals": [
    {
      "feature": "rainfall_anomaly_pct",
      "label": "Rainfall deficit",
      "value": -15.0,
      "signal_type": "weather_derived",
      "data_status": "SIMULATED_REPRESENTATIVE",
      "source": "IMD/Meghdoot (simulated)",
      "geographic_level": "district",
      "freshness": "current_season",
      "confidence": "high",
      "live_equivalent": "IMD district rainfall API / Meghdoot bulletins"
    }
  ],
  "model_assessment": {
    "estimated_risk_score": 71,
    "status": "risk",
    "model_uncertainty": {
      "tree_std": 0.145,
      "label": "moderate model disagreement"
    },
    "note": "Model risk score, not a calibrated probability of poverty, migration, debt, or distress."
  },
  "driver_contribution_indicative": {
    "method": "SHAP (TreeExplainer) over the trained RandomForest",
    "note": "Explains the MODEL's output, not proven real-world causation.",
    "drivers": [
      ["Rainfall deficit", 28.5, "increases"],
      ["Crop stress", 22.1, "increases"]
    ]
  },
  "scenario_trajectory": {
    "note": "Illustrative scenario trajectory...",
    "stages": [
      {
        "stage": "Weather / water shock",
        "relative_level": "MODERATE",
        "evidence_status": "OBSERVED_SIGNAL",
        "confidence": 0.85,
        "is_observed_or_simulated": "simulated"
      }
    ]
  },
  "suggested_actions_for_officer_review": [...],
  "validation_status": {...}
}
```

---

### What-If Scenario Analysis

```http
POST /villages/{village}/what-if
```

Explore hypothetical scenarios by overriding feature values.

**Request Body:**
```json
{
  "rainfall_anomaly_pct": -40,
  "crop_stress_index": 60
}
```

**Features You Can Override:**
- `rainfall_anomaly_pct` (-60 to +40)
- `crop_stress_index` (0 to 100)
- `mandi_price_deviation_pct` (-40 to +40)
- `mgnrega_demand_spike_pct` (-20 to +60)
- `water_stress_index` (0 to 100)
- `historical_vulnerability` (0 to 100)

---

### District Summary

```http
GET /district/summary
```

Get aggregated risk statistics for the district.

**Response:**
```json
{
  "district": "Nadia (representative pilot)",
  "total_villages": 30,
  "counts": {
    "stable": 8,
    "watch": 10,
    "risk": 8,
    "critical": 4
  },
  "pilot_mode_banner": "..."
}
```

---

## Model & Validation

### Model Metrics

```http
GET /model/metrics
```

Returns model evaluation metrics and feature importance.

**Response:**
```json
{
  "metrics": {
    "accuracy": 0.68,
    "precision": 0.43,
    "recall": 0.63,
    "f1": 0.51,
    "auc": 0.73,
    "is_field_validated": false
  },
  "feature_importance_global": {...},
  "important_note": "..."
}
```

---

### Validation Status

```http
GET /model/validation-status
```

Returns explicit validation status and limitations.

---

### Data Provenance

```http
GET /provenance
```

Returns detailed metadata for each feature including source, data status, and live equivalent.

---

## Weather Integration

### Current Weather

```http
GET /weather/{village}
```

Get current weather observation for a village.

---

### Weather Forecast

```http
GET /weather/{village}/forecast
```

Get 7-day weather forecast.

---

### Weather Warnings

```http
GET /weather/{village}/warnings
```

Get active weather warnings and advisories.

---

### Data Health Status

```http
GET /data-health
```

Check the health status of all data providers (weather, crop, market, etc.).

**Response:**
```json
{
  "providers": {
    "imd": {
      "current": {
        "status": "unavailable",
        "last_error": "IP not whitelisted",
        "last_checked": "2026-10-02T14:30:00+05:30"
      }
    },
    "open_meteo": {...}
  },
  "signals": {
    "weather": "see providers above",
    "crop": "SIMULATED",
    "market": "SIMULATED",
    "employment": "SIMULATED",
    "water": "SIMULATED",
    "vulnerability": "SIMULATED"
  }
}
```

---

## Geography

### List Locations

```http
GET /locations
```

Returns the geographic hierarchy (districts, blocks, villages) supported by the system.

---

## Human-in-the-Loop

### Submit Officer Review

```http
POST /villages/{village}/review
```

Log an officer's review decision.

**Request Body:**
```json
{
  "officer_decision": "approved|deferred|escalated",
  "action_taken": "Sent agromet advisory via mKisan"
}
```

**Response:**
```json
{
  "timestamp": "2026-10-02T14:35:22+05:30",
  "village": "Bagula",
  "predicted_risk_score": 71,
  "predicted_status": "risk",
  "officer_decision": "approved",
  "action_taken": "Sent agromet advisory via mKisan",
  "subsequent_outcome": null
}
```

Note: `subsequent_outcome` is intentionally null until a real pilot observes outcomes.

---

### Get Review Log

```http
GET /villages/{village}/review-log
```

Retrieve all logged reviews for a village.

---

## Interactive API Documentation

Visit `http://localhost:8000/docs` for interactive Swagger UI documentation where you can test all endpoints.

## Authentication

Currently, no authentication is required (development mode). For production deployment, implement:
- API key authentication
- Rate limiting
- IP whitelisting for sensitive endpoints

## Error Responses

All errors follow this format:

```json
{
  "detail": "Village 'UnknownPlace' not found"
}
```

**Common HTTP Status Codes:**
- `200`: Success
- `404`: Resource not found
- `422`: Validation error (invalid parameters)
- `500`: Internal server error

## Rate Limits

No rate limits in development. Recommended production limits:
- General endpoints: 100 requests/minute
- What-if scenarios: 20 requests/minute
- Review submissions: 10 requests/minute

## CORS

CORS is enabled for all origins in development (`allow_origins=["*"]`). Restrict this in production.
