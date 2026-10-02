# Kavach Setup Script - Windows PowerShell version

Write-Host "🛡️  Kavach Setup - Livelihood Risk Early Warning System" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host ""

# Check Python version
Write-Host "Checking Python version..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version
    Write-Host $pythonVersion -ForegroundColor Green
} catch {
    Write-Host "❌ Python not found. Please install Python 3.11+" -ForegroundColor Red
    exit 1
}
Write-Host ""

# Setup backend
Write-Host "Setting up backend..." -ForegroundColor Yellow
Set-Location backend

# Create virtual environment
if (-not (Test-Path "venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    python -m venv venv
}

# Activate virtual environment
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
& .\venv\Scripts\Activate.ps1

# Install dependencies
Write-Host "Installing Python dependencies..." -ForegroundColor Yellow
python -m pip install --upgrade pip
pip install -r requirements.txt

# Copy env file if it doesn't exist
if (-not (Test-Path ".env")) {
    Write-Host "Creating .env file from template..." -ForegroundColor Yellow
    Copy-Item .env.example .env
    Write-Host "⚠️  Please edit backend/.env with your configuration" -ForegroundColor Yellow
}

# Generate dataset
Write-Host "Generating representative dataset..." -ForegroundColor Yellow
python data/generate_dataset.py

# Train model
Write-Host "Training risk assessment model..." -ForegroundColor Yellow
python train_model.py

# Export snapshot for frontend
Write-Host "Exporting village snapshot data..." -ForegroundColor Yellow
python export_snapshot.py

Set-Location ..

Write-Host ""
Write-Host "✅ Setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "To start the API server:" -ForegroundColor Cyan
Write-Host "  cd backend" -ForegroundColor White
Write-Host "  .\venv\Scripts\Activate.ps1" -ForegroundColor White
Write-Host "  uvicorn app.main:app --reload --port 8000" -ForegroundColor White
Write-Host ""
Write-Host "Then open frontend/kavach_dashboard.html in your browser" -ForegroundColor Cyan
