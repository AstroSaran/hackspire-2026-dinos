# Deployment notes

Kavach is a live-data beta, not a validated livelihood-risk decision system.
It currently withholds all three promised livelihood-risk predictions. Do not
use it to decide eligibility, allocate aid, recommend crop changes, or assess
individual households.

## Local development

The local launch scripts create a virtual environment, install pinned runtime
dependencies and start Uvicorn on `127.0.0.1:8001`:

```powershell
.\run.ps1
```

`docker-compose.yml` starts only the optional MongoDB service; it does not build
or deploy the API. The dashboard and API are served together by FastAPI.

## Container deployment

The production image runs as an unprivileged user, has a read-only root
filesystem, uses one Uvicorn worker, and exposes a process health check. Keep
one worker: response caches, AI concurrency limits, and request throttles are
currently process-local. Do not scale replicas until those controls use shared
storage.

1. Copy `backend/.env.example` to `backend/.env`. Store real provider and
   database credentials only in that ignored file or your deployment secret
   manager.
2. Set `KAVACH_ALLOWED_ORIGINS` to the exact HTTPS dashboard origin and
   `KAVACH_ALLOWED_HOSTS` to the public API hostname plus `127.0.0.1` for the
   container health check.
3. Set `FORWARDED_ALLOW_IPS` to the exact IP address or CIDR of the trusted
   reverse proxy. Never use `*`; requests must reach the API through that proxy.
4. Point `MONGODB_URI` at a protected MongoDB deployment if accounts/notes are
   enabled. Leave it empty to disable private accounts while public data works.
5. Start the API container; its host port is bound to loopback for a local TLS
   reverse proxy:

```powershell
$env:KAVACH_ALLOWED_ORIGINS = 'https://dashboard.example.org'
$env:KAVACH_ALLOWED_HOSTS = 'api.example.org,127.0.0.1'
$env:FORWARDED_ALLOW_IPS = '172.20.0.1'
docker compose --env-file backend/.env -f docker-compose.production.yml up --build -d
```

Replace the example names and proxy IP with the deployment's actual values.
The server must terminate TLS, enforce request/body limits, and restrict direct
network access to port 8001. The included health check tests API process
availability; it does not claim external data providers or MongoDB are healthy.
Do not expose the container port directly to the public internet.

## Before exposing an instance

1. Deploy the API behind a maintained HTTPS reverse proxy and restrict direct
   access to the Uvicorn port.
2. Set `KAVACH_ALLOWED_ORIGINS` to the exact dashboard origin. Keep `.env`
   values in the host's secret manager; never put provider keys in HTML or URLs.
3. Keep `WEATHER_DEMO_FALLBACK=false`. The app returns explicit unavailable
   states when providers fail.
4. Configure the MongoDB URI only if private account storage is needed; require
   authentication, use TLS and backups, and set an encryption key before
   storing private notes.
5. Verify outbound DNS/HTTPS to approved live providers. In the last source
   check, the backend could not connect to `api.data.gov.in`, so crop,
   employment and market OGD feeds were unavailable.
6. Review every source's reuse terms before redistribution. The mango snapshot
   and model artifact are intentionally absent from the public repository
   while rights are unresolved. Open-Meteo's free API is non-commercial and
   requires attribution.
7. Re-run the test suite and `/data-health` checks in the actual deployment
   environment. Live-provider integration tests are opt-in and must not be
   treated as synthetic data validation.

## Production release gates

- Obtain adequate dated, location-matched real outcomes for crop stress,
  MGNREGA shortfall and broader livelihood disruption.
- Confirm data rights, field definitions, update cadence, security and privacy
  review for every source.
- Train each target separately; use forward-time and held-out-geography
  evaluation, compare to simple baselines, document uncertainty and failure
  cases, and keep abstention behavior.
- Complete independent field validation, monitoring, incident response,
  backups and accountable human review before any decision-support release.

The Docker image and local compose file are deployment scaffolding, not a hosted
deployment. Domain, TLS certificate, reverse proxy, secret storage, outbound
provider access, database, alerting, and backup configuration still belong to
the operator and must be verified in the target environment.

See [`../DATASET_INVENTORY.md`](../DATASET_INVENTORY.md) and
[`../MODEL_CARD.md`](../MODEL_CARD.md) for current dataset readiness and model
limitations.
