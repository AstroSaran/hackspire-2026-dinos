# Quick start

Kavach is a live-data beta for West Bengal. It shows provider-sourced weather
and data availability; the three livelihood-risk scores remain withheld because
validated real outcome labels are not available.

## Run locally

Requirements: Python 3.11 or later.

Windows PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\run.ps1
```

Linux or macOS:

```sh
chmod +x run.sh
./run.sh
```

The dashboard is served at `http://127.0.0.1:8001/dashboard/kavach_dashboard.html`.
FastAPI's interactive reference is at `http://127.0.0.1:8001/docs`.

The application never generates representative data or substitutes simulated
risk scores. Optional data.gov.in, AI, and MongoDB settings belong in the
ignored `backend/.env`; never commit real credentials.

## Run tests

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m pip install -r requirements-test.txt
..\.venv\Scripts\python.exe -m pytest -q
```

Tests use small fixtures and do not make live network calls by default.

## Data status

The versioned ERA5 weather snapshot is real historical predictor data with
Open-Meteo/ECMWF attribution. It is not a crop-loss or livelihood label dataset.
The mango CSV/model snapshot is not included in GitHub while reuse terms are
checked. The OGD connectors currently need working backend HTTPS egress. See
[`DATASET_INVENTORY.md`](DATASET_INVENTORY.md) and the source-access report for
current coverage and the exact missing outcome datasets.
