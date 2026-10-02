# Kavach — West Bengal live-data beta

Kavach is a source-attributed data workspace for West Bengal. Choose any of the
22 districts represented in the published horticulture dataset. The dashboard
resolves a district-headquarters search point for live Open-Meteo weather and
shows dated official mango area and production estimates for 2021-22 through
2024-25. Optional mandi, crop and MGNREGA connectors request real records from
data.gov.in when configured. Missing sources stay unavailable; the app never
substitutes simulated livelihood signals or risk scores.

## What is live, and what is not connected

| Signal | Current beta behavior | Source / limitation |
|---|---|---|
| Current weather and forecast | Fetched through FastAPI from Open-Meteo for a selected district; the API caches real provider responses | Open-Meteo model output; provider-resolved grid coordinates are displayed; not a station observation |
| Forecast watch | Derived from the seven-day live forecast | Kavach screening thresholds are clearly labeled as model watches, not IMD warnings or official impact thresholds. Official IMD alert access remains separately linked and unavailable unless configured. |
| Rainfall anomaly | API fetches the latest complete archived month and matching calendar-month normal | Real Open-Meteo ERA5 reanalysis at the selected provider grid, not a rain-gauge observation; the API caches the dated comparison for six hours |
| Historical environmental features | Versioned 2018–2025 daily snapshot collected for all 22 district-headquarters search points | 64,284 ERA5 reanalysis rows (temperature, precipitation, wind and reference evapotranspiration); predictors only, not crop-loss or livelihood labels; source and point-resolution limits are in the dataset manifest |
| Topsoil moisture | Live 0–7 cm provider-grid model field | Open-Meteo forecast model estimate in m³/m³; not a field reading, crop-stress score, groundwater level or irrigation recommendation |
| Field crop-survey coverage | Live source-coverage summary from the West Bengal WUA GIS layer | 19 point records were counted on 2026-10-03, with one crop-health label and one soil-moisture reading; no district field. Too sparse for training. The app excludes coordinates and editor metadata |
| Environmental watch model | Runs transparent forecast thresholds in the background over real weather inputs | Reports watch dates and contextual rainfall/soil-moisture evidence; no calibrated livelihood-impact score is inferred |
| Mandi prices | Optional live connector | AGMARKNET daily reports through data.gov.in, filtered to West Bengal. Rows are dated wholesale reports, not real-time local quotes |
| MGNREGA employment | Optional live connector and direct official MIS link | Statewide district aggregates require an official API key and a current resource UUID. District totals are not household demand or entitlement |
| Horticulture history | Local-only snapshot in this development workspace; not bundled in the public GitHub repo | Official annual district mango estimates for 22 districts, 2021-22 to 2024-25; historical values, not a live feed or stress labels. Reuse terms are not confirmed |
| Annual mango-yield experiment | Local experimental artifact; forecast withheld and artifact not bundled | 88 local official-source rows; one held-out year; its MAE is worse than the prior-year baseline. Not a livelihood, stress or production-decision model |
| OGD crop production | Optional live connector | Annual district/crop/season history from data.gov.in when the resource and API access work; not field-stress labels |
| Crop stress, water and vulnerability | Not connected | Dated field stress/loss labels, appropriately scaled soil or groundwater observations, and authorized outcome data are not connected. No proxy values are filled in. |
| Livelihood risk score | Withheld | No validated outcome labels or field-validated model exists |

### Source fit and data setup

The dashboard's **Data fit** panel explains source coverage at the selected
district scale. The weather card uses one live-geocoded headquarters point, not
a district average. Historical mango records cover all 22 districts in the
source tables. The panel reports coverage only; it does not estimate a
livelihood score.

### Reproduce the mango snapshot quality gate and experiment

The public repository does not include the mango CSV or its trained artifact
because reuse terms for the source tables have not been confirmed. Obtain
permission and a verified copy before running these commands. The unit tests
use local test fixtures and do not require that source dataset.

From the repository root in PowerShell:

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m app.mango_dataset_pipeline
..\.venv\Scripts\python.exe -m app.train_mango_yield_model --config configs/train_mango_yield.json
..\.venv\Scripts\python.exe -m app.evaluate_mango_yield_model --artifact data/mango_yield_baseline_model.json
```

When an authorized CSV is supplied at the configured path, the quality command
validates it without fetching or changing it, then writes a content-addressed report under
`backend/data/metadata/`. The trainer runs the same gate and records the data
hash and report path in its model artifact. A changed CSV receives a new report
version; an existing versioned report cannot be silently replaced. The current
CSV is already a normalized transcription, not the publisher's original raw
files. Its original source artifacts and collection date are not archived, and
the repository does not record a reuse license for those tables; confirm
publisher terms before redistributing the data.

This experiment has no separate validation set: four yearly vintages are too
few for one. Its final adjacent-year holdout covers 22 known districts, not
unseen-district generalization. It remains withheld because it loses to the
prior-year baseline on MAE and has only one independent test year.

### Refresh the historical weather feature snapshot

The current immutable snapshot, raw provider response, and provenance manifest
are under `backend/data/{raw,processed,metadata}/`. To request a different
date range (at most eight calendar years per run):

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m app.collect_historical_weather --start-date 2018-01-01 --end-date 2025-12-31
```

An existing matching snapshot is reused without another provider request. Add
`--refresh` only when intentionally collecting a new revision. Open-Meteo's
free API is for non-commercial use; commercial operation requires an
appropriate API plan. Each manifest records required Open-Meteo/ECMWF
attribution and the grid-point/reanalysis limitations. The collector does not
train a risk model because this dataset contains predictor features, not
outcomes. See [DATASET_INVENTORY.md](DATASET_INVENTORY.md) for the source
inventory and the outcome data required for the withheld tracks.

The latest acquisition check found the three `data.gov.in` connectors unable
to establish HTTPS from this backend. The official MGNREGA MPR page loaded, but
its geography selector was disabled and no report could be exported. See
`backend/data/metadata/source-access-2026-10-03.json` for timestamped
source-by-source results; the report contains no credentials.

Weather polling runs every five minutes while the dashboard is visible. Soil
context is revalidated every fifteen minutes; market and employment feeds are
revalidated hourly. A visible tab refreshes on focus or reconnect only when its
cached readings are older than their interval. Hidden tabs pause polling.

The district selector uses the published district catalogue in
`backend/app/geography.py`. FastAPI sends the district-headquarters search label
to Open-Meteo's geocoder and makes weather/archive requests server-side.
Coordinates are not presented as field locations or district centroids. The
retired pilot registry is empty.

The retired synthetic prototype and its model artifacts are not part of the current application.

## Production packaging

The repository includes a hardened API container and a production Compose
profile for deployment behind a trusted HTTPS reverse proxy. Follow
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) to set allowed origins/hosts and the
proxy trust range. Caches and throttles are process-local, so the packaged API
runs one worker and is not horizontally scalable until shared controls are
configured. The application still withholds livelihood predictions pending
real outcome data and independent validation.

## Run locally (PowerShell)

From the repository root:

```powershell
.\run.ps1
```

Open `http://127.0.0.1:8001/dashboard/kavach_dashboard.html` in a browser.
The local URL allows microphone access. Weather refreshes every five minutes
while the page is visible; the dashboard refreshes on focus or reconnect only
when data is older than that interval. Polling pauses in hidden tabs. Daily market/employment feeds are
revalidated hourly and soil moisture every fifteen minutes; the manual refresh
button forces a fresh request. Provider publication schedules determine when
the underlying values change. Change the API endpoint if the backend uses
another host or port.

`backend/requirements-live.txt` is the runtime dependency set.

### Optional official mandi and employment feeds

Generate an API key from the official [data.gov.in platform](https://www.data.gov.in/)
and identify active resource UUIDs for the official [AGMARKNET daily price
dataset](https://www.data.gov.in/catalog/current-daily-price-various-commodities-various-markets-mandi)
and [district-wise MGNREGA dataset](https://www.data.gov.in/resource/district-wise-mgnrega-data-glance).
Set the key and each resource UUID in `backend/.env` before starting Kavach:

```powershell
$env:DATA_GOV_IN_API_KEY = 'your-key'
$env:DATA_GOV_IN_MARKET_RESOURCE_ID = 'official-resource-uuid'
$env:DATA_GOV_IN_MGNREGA_RESOURCE_ID = 'ee03643a-ee4c-48c2-ac30-9f2ff26ab722'
$env:DATA_GOV_IN_CROP_RESOURCE_ID = '35be999b-0208-4354-b557-f6ca9a5355de'
```

The configured MGNREGA resource is the published **1 April–31 August 2023
snapshot**. It is historical context, not today's employment feed. The linked
official state MIS is the place to inspect current district/block/panchayat
records. Replace the snapshot UUID only after confirming a newer resource and
its schema on the official portal. The connector uses the official **Current Daily Price of Various
Commodities from Various Markets (Mandi)** resource. It reports dated wholesale
min/max/modal prices; rows are not live local quotes. MGNREGA feed rows are
administrative aggregates and do not establish individual employment demand.

### Optional AI support assistant

The dashboard includes Kavach Support for explanations of readings, source status, and feed setup. It uses a public-data-only evidence snapshot cached in memory for 90 seconds. Chat stays unsaved unless a signed-in user explicitly saves an answer as a note. Before recording, the voice panel asks for consent and lets the user review text before choosing Continue or Save transcript. ElevenLabs is used for speech-to-text when configured, with Gemini as the fallback; generated speech uses ElevenLabs when a voice is configured, with browser speech as the fallback. Optional voice cloning sends audio samples to ElevenLabs only after separate consent and speaker-authorization confirmation. Kavach does not persist those samples. Provider data-handling terms still apply. User notes are not included in the evidence snapshot or sent to Gemini.

Create a Gemini API key in Google AI Studio. Put it in `backend/.env` (copy `backend/.env.example` as a starting point); the backend loads this private file at startup. Gemini is preferred when configured. An OpenAI key is an optional fallback. Never add either key to HTML, JavaScript, or a public repository:

```powershell
Copy-Item backend/.env.example backend/.env
# Add GEMINI_API_KEY=your-key to backend/.env, then run:
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

Check `GET /support/status` for setup readiness and model name. Optional ElevenLabs voice setup: set `ELEVENLABS_API_KEY` in `backend/.env`; set `ELEVENLABS_VOICE_ID` to an existing voice if you want it selected by default. `ELEVENLABS_STT_MODEL` defaults to `scribe_v2`, and `ELEVENLABS_TTS_MODEL` defaults to `eleven_multilingual_v2`. With an ElevenLabs key, the voice panel uses it for transcription; otherwise it can use Gemini. The “Clone a voice” panel accepts one to three samples only after confirming the speaker's permission and consent to share them with ElevenLabs; the returned voice is selected for that browser session. Configure a default voice ID for repeat use across sessions. Chat and voice endpoints have rate limits and share the configurable daily request cap (`KAVACH_DAILY_AI_LIMIT`, default 300). Provider plans may charge separately. Keep provider keys in the backend environment, never in the dashboard.

### Optional private accounts and notes

MongoDB is optional. Set `MONGODB_URI` and `MONGODB_DB_NAME` to use local MongoDB
or Atlas. The local development compose file binds Mongo only to `127.0.0.1` and
requires `MONGO_ROOT_USER` and `MONGO_ROOT_PASSWORD`. Configure `JWT_SECRET` (at
least 32 characters) and a Fernet `ENCRYPTION_KEY`; leave both unset to keep
accounts disabled. Notes are opt-in, hard-deletable and the body is encrypted
before MongoDB storage. Access tokens last 15 minutes and remain in page memory;
refresh cookies are HTTP-only, Secure and SameSite strict. Chats remain unsaved
by default. Saved notes are marked “Your note: not verified by Kavach” and do
not affect weather, evidence snapshots or live models. See [PRIVACY.md](PRIVACY.md).

For a local setup, run `docker compose up -d` after setting Mongo root variables,
or point `MONGODB_URI` at an already running MongoDB. Production deployments
need MongoDB access control, TLS and protected backups.

### Known limitations

- Weather represents a single provider grid near the selected district
  headquarters, not local station readings or a district-wide surface.
- Mandi rows are daily wholesale reports and may be distant from the selected
  district point. MGNREGA rows are district aggregates, not household outcomes.
- The discoverable MGNREGA OGD resource covers 1 April–31 August 2023; a
  successful API retrieval would not make those observations current.
- Crop-stress, groundwater/water-supply and validated livelihood-outcome feeds
  are not connected. Kavach does not produce a livelihood-risk score.
- The annual mango experiment was withheld because it lost to the simple
  prior-year baseline on MAE and has only one independent test year.
- IMD API access requires the relevant official access approval/whitelisting.
- Gemini availability, model access, API pricing and data handling depend on the
  configured provider account.
- Account storage is optional and needs operational security review before use
  beyond a local demo.

### Sharing checklist

Before creating a project ZIP, exclude `.env`, `backend/.env`, `.venv/`, `tmp/`
and all `*.pkl` files. Never share a real API key. Read [SECURITY.md](SECURITY.md).

Each connector returns `NEEDS_CONFIGURATION` until its resource ID and API key are configured, and `UNAVAILABLE` if the real API request fails. Mandi and crop data use `DATA_GOV_IN_API_KEY`; MGNREGA can use its separate `DATA_GOV_IN_MGNREGA_API_KEY` (or fall back to the shared key). Requests are made server-side by FastAPI; the browser never receives the API key. West Bengal records can be paged with `offset` and `limit` on `/signals/market`, `/signals/crop-production`, and `/signals/employment`. Market data are dated daily reports; MGNREGA data are district aggregates, not household-level demand. For a keyless
browse of the live official MIS, use the [West Bengal portal](https://mnregaweb2.dord.gov.in/netnrega/homestciti.aspx?state_code=32&state_name=WEST%20BENGAL&lflag=eng&labels=labels).
Choose the relevant West Bengal district, block, and panchayat. Do not
assign rural aggregate records to a household or weather grid without an
authoritative geographic match.

## API

- `GET /health` — beta mode and service health.
- `GET /weather/{village}` — provider-backed weather response with provenance.
- `GET /weather/{village}/forecast` — provider-backed forecast.
- `GET /weather/{village}/warnings` — official warning provider result or explicit `UNAVAILABLE`.
- `GET /weather/{village}/watch` — transparent threshold flags derived from a real weather forecast; never an official warning.
- `GET /data-health` — weather provider health and baseline availability.
- `GET /signals/soil-moisture` — real provider-grid 0–7 cm model field, with timestamp and provenance.
- `GET /signals/field-crop-survey` — live coverage from the West Bengal government crop-survey GIS layer; returns summary counts only, not point locations or editor metadata.
- `GET /signals/environmental-model` — background environmental watch plus explicit livelihood-model readiness and blockers.
- `GET /support/status` and `POST /support/chat` — optional server-keyed AI helper grounded in a fresh, source-labeled snapshot of real feeds.
- `GET /signals/market` — official daily market feed, or explicit `UNAVAILABLE`.
- `GET /signals/employment` — official daily district MGNREGA aggregate, or explicit `UNAVAILABLE`.
- `GET /signals/crop-production` — optional official annual district/crop/season production feed, or explicit `UNAVAILABLE`.
- `GET /signals/mango-production?district=Malda` — official historical mango estimates for the selected district.
- `GET /signals/mango-yield-model` — training and holdout results for the withheld annual-yield experiment.
- `GET /model/readiness` — livelihood-model evidence and release gates.
- `GET /districts/geocode?district=Malda` — live West Bengal headquarters geocode.
- `GET /district-weather?district=Malda` — real current, seven-day forecast, threshold watch and 0–7 cm soil field.
- `GET /district-rainfall-anomaly?district=Malda` — latest complete ERA5 month compared with its 1991–2020 monthly normal.
- `GET /live-area/{key}` — retired legacy route; use `/locations` for district selection.
- `GET /locations` — published West Bengal district catalogue; coordinates are resolved server-side when selected.

Synthetic scoring, what-if and expansion endpoints return HTTP 410 in this
beta. The app does not make benefit, insurance, employment or migration
decisions.

Rainfall comparison requests the selected grid's previous complete month and
its 1991–2020 ERA5 calendar-month normals from Open-Meteo. A result appears only
when both real archive requests return complete data. No fixed-place baseline
or stale location cache is bundled.
Windows-native certificate validation is enabled through truststore so the
Python provider requests use the machine's trusted roots without disabling
HTTPS verification.

## Data rules

- Preserve source, retrieval time, valid time, freshness and provider-resolved
  coordinates for every live value.
- Show `NEEDS_CONFIGURATION` when credentials/resource IDs are missing and `UNAVAILABLE` when a configured source fails.
- Weather forecast watches are screening indicators only; official alerts remain authoritative.
- Never call weather-model output a sensor observation.
- Never treat a district-level market row as a village-specific quote.
- Do not calculate a livelihood risk score until real local input coverage and
  real outcome validation exist.
