#!/bin/bash
# Kavach Setup Script - Quick start for local development

echo "🛡️  Kavach Setup - Livelihood Risk Early Warning System"
echo "=========================================================="
echo ""

# Check Python version
echo "Checking Python version..."
python --version || { echo "❌ Python not found. Please install Python 3.11+"; exit 1; }
echo ""

# Setup backend
echo "Setting up backend..."
cd backend || exit 1

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate || { echo "❌ Failed to activate venv"; exit 1; }

# Install dependencies
echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Copy env file if it doesn't exist
if [ ! -f ".env" ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  Please edit backend/.env with your configuration"
fi

# Generate dataset
echo "Generating representative dataset..."
python data/generate_dataset.py

# Train model
echo "Training risk assessment model..."
python train_model.py

# Export snapshot for frontend
echo "Exporting village snapshot data..."
python export_snapshot.py

cd ..

echo ""
echo "✅ Setup complete!"
echo ""
echo "To start the API server:"
echo "  cd backend"
echo "  source venv/bin/activate"
echo "  uvicorn app.main:app --reload --port 8000"
echo ""
echo "Then open frontend/kavach_dashboard.html in your browser"
