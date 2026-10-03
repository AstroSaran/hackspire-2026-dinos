# Kavach — Hackspire live-data beta

Kavach is a source-attributed live data workspace for West Bengal. Its weather
card uses one clearly labeled Sonarpur forecast grid; official crop, mandi and
employment records are requested for all West Bengal districts. It shows data
only after a configured real provider responds. It never renders
the earlier prototype's simulated livelihood signals, synthetic risk score, or
illustrative trajectory.

## What is live, and what is not connected

| Signal | Current beta behavior | Source / limitation |
|---|---|---|
| Current weather and forecast | Fetched directly from Open-Meteo when the user refreshes; does not depend on the local API being online | Open-Meteo model output; provider-resolved grid coordinates are displayed; not a station observation |
| Forecast watch | Derived from the seven-day live forecast | Kavach screening thresholds are clearly labeled as model watches, not IMD warnings or official impact thresholds. Official IMD alert access remains separately linked and unavailable unless configured. |
| Rainfall anomaly | Compares the most recent complete month with its same-calendar-month 1991–2020 normal | Real Open-Meteo ERA5 reanalysis at the returned grid cell, not a rain-gauge observation; the dashboard refreshes the archive query and uses a dated same-month cache only if that query fails |
| Topsoil moisture | Live 0–7 cm provider-grid model field | Open-Meteo forecast model estimate in m³/m³; not a field reading, crop-stress score, groundwater level or irrigation recommendation |
| Environmental watch model | Runs transparent forecast thresholds in the background over real weather inputs | Reports watch dates and contextual rainfall/soil-moisture evidence; no calibrated livelihood-impact score is inferred |
| Mandi prices | Optional live connector | AGMARKNET daily reports through data.gov.in, filtered to West Bengal. Rows are dated wholesale reports, not real-time local quotes |
| MGNREGA employment | Optional live connector and direct official MIS link | Statewide district aggregates require an official API key and a current resource UUID. District totals are not household demand or entitlement |
| Crop production | Optional live connector | Annual district/crop/season area and production history across West Bengal; not crop-stress labels or an individual yield forecast |
| Crop stress, water and vulnerability | Not connected | Dated field stress/loss labels, appropriately scaled soil or groundwater observations, and authorized outcome data are not connected. No proxy values are filled in. |
| Livelihood risk score | Withheld | No validated outcome labels or field-validated model exists |

### Source fit and data setup

The dashboard's **Data fit** panel explains source coverage. Mandi, crop and
employment feeds request West Bengal records across districts. The local weather
panel remains Sonarpur-only. The panel reports coverage only; it does not
estimate a livelihood score.

Weather polling runs every five minutes while the dashboard is visible. Soil
context is revalidated every fifteen minutes; market and employment feeds are
revalidated hourly. A visible tab refreshes on focus or reconnect only when its
cached readings are older than their interval. Hidden tabs pause polling.

The registered pilots and coordinates are listed in
`backend/data/live_pilots.json`. Add a location only after checking its source,
administrative area and coordinate resolution. The dashboard obtains the
coordinate from `/locations` rather than embedding it in the page.

Retired prototype code and datasets are local-only under `legacy_prototype/`;
they are excluded from the public repository. Yield and employment measurements
are not substituted for observed distress labels.

## Standalone rice-yield research

[`kavach_model/`](kavach_model/README.md) contains the separate preharvest rice
pipeline, tests, source metadata, plots and aggregate evaluation reports. Its
[model card](kavach_model/MODEL_CARD.md) records a **withheld** release. See its
README for the locally supplied data and artifact requirements.

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

`backend/requirements-live.txt` is the runtime dependency set. The local app is
tested with the patched dependency versions pinned there and in
`backend/requirements-test.txt`.

### Showcase demo mode

For a presentation where provider access is unavailable, run the explicitly
labeled deterministic showcase mode in a separate process:

```powershell
$env:KAVACH_DEMO_MODE = 'true'
cd backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8002
```

Open `http://127.0.0.1:8002/dashboard/kavach_dashboard.html`. The banner,
provider status, timestamps and source copy identify the values as simulated;
demo mode never acts as a fallback after a live provider fails. Unset the
variable and use port 8001 for the live-only beta.

### Model workbench

The supported experimental model is the annual West Bengal district mango-yield
baseline. It trains only on the official, provenance-linked CSV and selects a
candidate by rolling-origin backtest; it is not a livelihood-risk model:

The public repository excludes `backend/data/wb_mango_district_annual.csv`,
trained model JSON and release archives pending source redistribution terms.
Supply an authorized local snapshot before training. Without it, model routes
report unavailable and the weather/data workspace still runs. CI uses isolated
test fixtures for registry and serving contracts; source-specific integration
checks skip when the official snapshot is absent.

```powershell
cd backend
..\.venv\Scripts\python.exe -m app.train_mango_yield_model
```

`GET /models/mango-yield` validates the source and artifact before returning an
experimental result. `GET /models/readiness` exposes the blocked production
gates; `GET /models/metrics` reports worker-local validation counters.
`python -m app.model_registry --list` lists releases; `--activate SHA256`
validates and restores an archived release. An optional digest pin is configured
through `KAVACH_MANGO_ARTIFACT_SHA256`.

The previous v0.1 holdout experiment is retained as `app.train_mango_holdout`
with its separate evaluator and `backend/configs/train_mango_yield.json`.

The legacy six-feature distress interface remains blocked until independently
observed outcome labels and complete location-matched inputs are available.
Kaggle convenience copies and synthetic labels are not used as substitutes.

### Optional official mandi and employment feeds

Generate an API key from the official [data.gov.in platform](https://www.data.gov.in/)
and identify active resource UUIDs for the official [AGMARKNET daily price
dataset](https://www.data.gov.in/catalog/current-daily-price-various-commodities-various-markets-mandi)
and [district-wise MGNREGA dataset](https://www.data.gov.in/resource/district-wise-mgnrega-data-glance).
Set the key and each resource UUID in `backend/.env` before starting Kavach:

```powershell
$env:DATA_GOV_IN_API_KEY = 'your-key'
$env:DATA_GOV_IN_MARKET_RESOURCE_ID = 'official-resource-uuid'
$env:DATA_GOV_IN_MGNREGA_RESOURCE_ID = 'official-resource-uuid'
$env:DATA_GOV_IN_CROP_RESOURCE_ID = '35be999b-0208-4354-b557-f6ca9a5355de'
```

The mandi connector uses the official **Current Daily Price of Various
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

- The Sonarpur pilot is a municipal address; MGNREGA rural aggregates do not
  apply to individual households there.
- Mandi records are daily wholesale reports and may be distant from the pilot.
- Crop, groundwater/water-supply and validated livelihood-outcome feeds are not
  connected. Kavach does not produce a livelihood risk score.
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
assign those rural records to the pilot address until an authoritative boundary
match confirms coverage.

## API

- `GET /health` — beta mode and service health.
- `GET /weather/{village}` — provider-backed weather response with provenance.
- `GET /weather/{village}/forecast` — provider-backed forecast.
- `GET /weather/{village}/warnings` — official warning provider result or explicit `UNAVAILABLE`.
- `GET /weather/{village}/watch` — transparent threshold flags derived from a real weather forecast; never an official warning.
- `GET /data-health` — weather provider health and baseline availability.
- `GET /signals/soil-moisture` — real provider-grid 0–7 cm model field, with timestamp and provenance.
- `GET /signals/environmental-model` — background environmental watch plus explicit livelihood-model readiness and blockers.
- `GET /support/status` and `POST /support/chat` — optional server-keyed AI helper grounded in a fresh, source-labeled snapshot of real feeds.
- `GET /signals/market` — official daily market feed, or explicit `UNAVAILABLE`.
- `GET /signals/employment` — official daily district MGNREGA aggregate, or explicit `UNAVAILABLE`.
- `GET /signals/crop-production` — official annual South 24 Parganas crop/season production history, or explicit `UNAVAILABLE`. This is not field-level crop stress or a short-horizon forecast.
- `GET /live-area/sonarpur` — location, weather and withheld assessment status.
- `GET /locations` — supported geography and coordinate resolution.
- `GET /models/mango-yield` — experimental annual district mango-yield baseline with backtest metrics, 80% bands and data-quality flags (see MODEL_CARD.md). Not a risk score.

Synthetic scoring, what-if and expansion endpoints return HTTP 410 in this
beta. The app does not make benefit, insurance, employment or migration
decisions.

The saved Sonarpur ERA5 baseline contains all twelve 1991–2020 monthly normals
for the provider-resolved grid cell. The latest completed-month cache is dated
and source-attributed; it is not treated as a current-month observation.
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
