# API reference

The OpenAPI schema is generated from the running FastAPI application. Start
Kavach and open:

- Interactive docs: `http://127.0.0.1:8001/docs`
- OpenAPI JSON: `http://127.0.0.1:8001/openapi.json`

## Live-data endpoints

- `GET /health`, `GET /data-health`, `GET /provenance`
- `GET /locations`
- `GET /weather/{village}`
- `GET /weather/{village}/forecast`
- `GET /weather/{village}/warnings`
- `GET /weather/{village}/watch`
- `GET /district-rainfall-anomaly?district={district}`
- `GET /signals/field-crop-survey` — coverage summary only; omits point geometry and editor metadata
- `GET /signals/crop-production`, `GET /signals/market`, `GET /signals/employment`
- `GET /signals/mango-production?district={district}` — available only when the local, rights-cleared snapshot is installed
- `GET /model/readiness`, `GET /model/validation-status`

Optional feeds report `NEEDS_CONFIGURATION` or `UNAVAILABLE` when a source is
not configured or cannot be reached. They never fill gaps with simulated
values. Withheld livelihood-risk routes do not emit a score. The dashboard and
the current source/readiness contracts are described in [`../README.md`](../README.md).
