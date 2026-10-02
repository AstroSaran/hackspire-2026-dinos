# Contributing to Kavach

Thank you for considering contributing to Kavach! This document provides guidelines and instructions for contributing.

## Quick Start

1. Fork the repository
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/hackspire-2026-dinos.git`
3. Run setup: `./setup.sh` (Linux/macOS) or `.\setup.ps1` (Windows)
4. Create a branch: `git checkout -b feature/your-feature-name`
5. Make your changes
6. Run tests: `cd backend && pytest tests/`
7. Commit: `git commit -m "feat: your feature description"`
8. Push: `git push origin feature/your-feature-name`
9. Create a Pull Request

## Development Setup

### Prerequisites
- Python 3.11+
- Git

### Setup Instructions
```bash
# Run the setup script
./setup.sh          # Linux/macOS
.\setup.ps1         # Windows

# Or manual setup
cd backend
python -m venv venv
source venv/bin/activate  # Linux/macOS
# OR
.\venv\Scripts\Activate.ps1  # Windows

pip install -r requirements.txt
python data/generate_dataset.py
python train_model.py
python export_snapshot.py
```

### Running Tests
```bash
cd backend
pytest tests/ -v
```

### Running the API
```bash
cd backend
uvicorn app.main:app --reload --port 8000
```
Visit http://localhost:8000/docs for API documentation.

## Commit Message Convention

We follow [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation changes
- `refactor:` Code refactoring
- `test:` Adding or updating tests
- `chore:` Maintenance tasks

Examples:
```
feat: add rainfall trend visualization
fix: correct SHAP value calculation for edge cases
docs: update README with deployment instructions
refactor: extract weather provider logic into separate module
test: add tests for scenario trajectory confidence decay
chore: update dependencies to latest versions
```

## Code Style

- Follow PEP 8 for Python code
- Use meaningful variable and function names
- Add docstrings to functions and classes
- Keep functions focused and small
- Add comments for complex logic

## Project Structure

```
kavach/
├── backend/
│   ├── app/              # FastAPI application
│   │   ├── main.py       # API endpoints
│   │   ├── engine.py     # Risk assessment & ML logic
│   │   ├── geography.py  # Location resolution
│   │   ├── review.py     # Human-in-the-loop review logging
│   │   └── weather/      # Weather integration
│   ├── data/             # Dataset generation & storage
│   ├── model_artifacts/  # Trained model & metrics
│   └── tests/            # Test suite
├── frontend/             # Static HTML dashboard
└── frontend_data/        # Precomputed village data
```

## What to Contribute

### High Priority
- Live data connector implementations (IMD API, Open-Meteo, AGMARKNET, MGNREGA MIS)
- Additional test coverage
- Performance optimizations
- Documentation improvements
- Bug fixes

### Feature Ideas
- District-level aggregation views
- Historical trend analysis
- SMS/email alert system
- Multi-district support
- API rate limiting and authentication
- Caching layer improvements

### Not Accepted
- Changes that make validation claims without real field data
- Features that bypass officer review requirements
- Code that mislabels simulated data as live
- Household-level tracking without privacy review

## Testing Guidelines

All contributions should include tests:

1. **Unit tests** for new functions in `engine.py`, `geography.py`, etc.
2. **API tests** for new endpoints
3. **Integration tests** for data pipeline changes
4. **Methodological honesty tests** if changing risk scoring or labeling

Run the full test suite before submitting:
```bash
cd backend
pytest tests/ -v --cov=app
```

## Methodological Honesty

Kavach explicitly **does not** claim to predict real-world poverty, migration, or distress with validated accuracy. Any contribution must:

- Label model output as "estimated risk score," not "probability of distress"
- Tag scenario trajectories by evidence status (OBSERVED_SIGNAL / SCENARIO_ESTIMATE / SCENARIO_INDICATOR)
- Mark simulated data as `SIMULATED_REPRESENTATIVE`
- Maintain the `is_field_validated: False` flag
- Never bypass the officer review requirement

Tests in `test_methodological_honesty.py` enforce these constraints and will fail if violated.

## Documentation

Update documentation when:
- Adding new API endpoints → update docstrings and README
- Changing data sources → update PROVENANCE metadata
- Adding features → update README features list
- Fixing bugs → add comments explaining the fix

## Questions?

Open an issue for:
- Feature requests
- Bug reports
- Documentation clarifications
- General questions

## License

By contributing, you agree that your contributions will be licensed under the same license as the project.
