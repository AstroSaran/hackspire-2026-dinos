# Kavach Quick Start Guide

Get Kavach running locally in 5 minutes.

## Prerequisites

- Python 3.11 or higher
- Git

Check your Python version:
```bash
python --version
# Should show Python 3.11.x or higher
```

## Installation

### Step 1: Clone the Repository

```bash
git clone https://github.com/AstroSaran/hackspire-2026-dinos.git
cd hackspire-2026-dinos
```

### Step 2: Run the Setup Script

**Windows (PowerShell):**
```powershell
.\setup.ps1
```

**Linux/macOS:**
```bash
chmod +x setup.sh
./setup.sh
```

The setup script will:
- Create a Python virtual environment
- Install all dependencies
- Generate the representative dataset
- Train the risk assessment model
- Export village snapshot data

This takes about 2-3 minutes.

### Step 3: Start the API Server

```bash
cd backend

# Activate virtual environment
# Windows:
.\venv\Scripts\Activate.ps1
# Linux/macOS:
source venv/bin/activate

# Start the server
uvicorn app.main:app --reload --port 8000
```

You should see:
```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

### Step 4: Explore the API

Open your browser to:
- **Interactive API Docs**: http://localhost:8000/docs
- **API Root**: http://localhost:8000

Try these endpoints:
- http://localhost:8000/villages - List all villages
- http://localhost:8000/villages/Bagula - Get detailed assessment
- http://localhost:8000/data-health - Check data provider status
- http://localhost:8000/model/validation-status - View validation status

### Step 5: View the Dashboard

While the API server is running, open the dashboard:

```bash
# In a new terminal, from the project root
open frontend/kavach_dashboard.html  # macOS
start frontend/kavach_dashboard.html  # Windows
xdg-open frontend/kavach_dashboard.html  # Linux
```

Or simply double-click `frontend/kavach_dashboard.html` in your file explorer.

## What You'll See

The dashboard shows:
- 30 villages from Nadia district, West Bengal
- Risk scores color-coded by severity (🟢🟡🟠🔴)
- Detailed risk assessment with:
  - Observed signals (rainfall, crop stress, market prices, etc.)
  - Model-estimated risk score with uncertainty
  - SHAP-based driver explanation
  - Illustrative scenario trajectory
  - Suggested actions for officer review

## Key Endpoints to Try

### List Villages
```bash
curl http://localhost:8000/villages
```

### Get Village Details
```bash
curl http://localhost:8000/villages/Bagula
```

### What-If Scenario
```bash
curl -X POST http://localhost:8000/villages/Bagula/what-if \
  -H "Content-Type: application/json" \
  -d '{"rainfall_anomaly_pct": -40, "crop_stress_index": 60}'
```

### Submit Officer Review
```bash
curl -X POST http://localhost:8000/villages/Bagula/review \
  -H "Content-Type: application/json" \
  -d '{"officer_decision": "approved", "action_taken": "Sent agromet advisory"}'
```

## Running Tests

```bash
cd backend
pytest tests/ -v
```

You should see 31 tests pass, including:
- Methodological honesty tests (ensuring no overclaiming)
- Geography tests (West Bengal validation)
- Weather provider tests
- Data quality tests

## Understanding the Data

**Important**: All data in this demo is **SIMULATED_REPRESENTATIVE**, not live government data.

- **Weather**: Demo mode by default (set `WEATHER_PROVIDER=open_meteo` in `.env` for live weather)
- **Crop/Market/Employment**: Synthetic data calibrated to published statistics
- **Risk Scores**: Model output over representative data, NOT validated predictions
- **Validation Status**: Explicitly marked as "Not field validated"

Check the validation status:
```bash
curl http://localhost:8000/model/validation-status
```

## Configuring Weather Providers

Edit `backend/.env`:

```bash
# Use demo weather (default)
WEATHER_PROVIDER=demo
WEATHER_DEMO_FALLBACK=true

# OR use Open-Meteo (requires internet)
WEATHER_PROVIDER=open_meteo
WEATHER_ENABLE_FALLBACK=true

# OR use IMD (requires IP whitelisting)
WEATHER_PROVIDER=imd
# (IMD setup requires official approval and IP whitelisting)
```

Restart the server after changing `.env`.

## Common Issues

### Port Already in Use
If port 8000 is busy, use a different port:
```bash
uvicorn app.main:app --reload --port 8001
```

### Dependencies Not Installing
If you have SSL certificate errors with pip:
```bash
pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt
```

### Module Not Found
Make sure you're in the `backend` directory and virtual environment is activated:
```bash
cd backend
source venv/bin/activate  # or .\venv\Scripts\Activate.ps1 on Windows
python -c "import app.main; print('OK')"
```

## Next Steps

- **Read the Docs**: See [docs/API.md](docs/API.md) for full API documentation
- **Deploy**: See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for production deployment
- **Contribute**: See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines
- **Understand the Design**: Read [README.md](README.md) for architecture details

## Demo Workflow

1. **Start API** → `uvicorn app.main:app --reload --port 8000`
2. **Open Dashboard** → `frontend/kavach_dashboard.html`
3. **Select a Village** → Click on any village in the list
4. **Review Assessment**:
   - Observed signals (with data provenance)
   - Risk score + uncertainty
   - Driver explanation (SHAP)
   - Scenario trajectory
   - Suggested actions
5. **Submit Review** → Use "Approve/Defer/Escalate" buttons
6. **Explore Scenarios** → Try "What-if Analysis" with different values

## Getting Help

- **Issues**: https://github.com/AstroSaran/hackspire-2026-dinos/issues
- **API Docs**: http://localhost:8000/docs (when running)
- **Full README**: [README.md](README.md)

---

**You're all set!** 🎉 Kavach is now running locally. Explore the API and dashboard to see how it turns fragmented signals into an auditable early-warning workflow.
