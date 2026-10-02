# Contributing to Kavach

Thank you for contributing. Kavach is a live-data beta for West Bengal. Keep source attribution, freshness, spatial coverage and uncertainty visible in any changes. Do not add generated or simulated observations to live feeds or claim a livelihood prediction is validated when no verified outcome labels support it.

## Development setup

Requirements: Python 3.11 or later and Git.

Run the application from the repository root:

```powershell
.\run.ps1
```

```sh
./run.sh
```

The dashboard is served at `http://127.0.0.1:8001/dashboard/kavach_dashboard.html`; FastAPI documents endpoints at `/docs`. Runtime settings and API credentials belong in the ignored `backend/.env`, never in source files or commits. See `QUICKSTART.md` for optional official data feeds and provider setup.

Install development dependencies and run the backend suite:

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m pip install -r requirements-live.txt -r requirements-test.txt
..\.venv\Scripts\python.exe -m pytest -q
```

Tests use fixtures and should not require live service credentials or network access.

## Data and model standards

- Preserve source URL, publisher, retrieval date, licensing/terms, transformation, geographic resolution and temporal coverage for each dataset.
- Keep raw source data immutable when licensing permits; use content hashes and versioned provenance manifests for collected snapshots.
- Never redistribute data or artifacts until the source terms permit it.
- Distinguish measured observations, provider model estimates, administrative aggregates, scenario indicators and unavailable values.
- Do not impute missing live feeds with demo or synthetic values.
- Treat environmental signals as evidence for human review; do not present them as household-level livelihood outcomes or calibrated distress probabilities.
- Do not store precise household locations or personal records without a documented privacy basis and safeguards.

## Code and pull requests

Use focused changes, descriptive names and comments where logic is not self-evident. Include regression tests for changed behavior, update source/model documentation when relevant, and run the backend suite before opening a pull request. Use Conventional Commit prefixes such as `feat:`, `fix:`, `docs:`, `test:` and `chore:`.

## Security

Never commit `.env` files, provider keys, personal data, database exports, unreviewed raw datasets or model artifacts. Report suspected credential exposure by rotating the affected credential and following `SECURITY.md`.
