# West Bengal preharvest rice model

Standalone real-data research project. Read **[MODEL_CARD.md](MODEL_CARD.md)** and
`reports/model_release_report.json` for the executed results and release decision.
No generated or imputed observations enter training/evaluation.

## Public checkout and local inputs

This directory publishes the research source, tests, dependency pins, provenance metadata,
and aggregate measured reports. Under the repository's [data and model standards](../CONTRIBUTING.md#data-and-model-standards),
raw/processed datasets, fitted `.joblib` weights, and row-level outputs are local-only while
redistribution terms remain unverified. `models/manifest.json` and `models/selection.json`
are checksum/selection metadata, not fitted model weights.

The complete experiment was executed in the standalone local workspace. The included results
describe that run; a fresh GitHub checkout does not contain its training inputs or runnable weights.
`reports/environment.json` records the executed environment; publication-only documentation and
conditional integration-test changes do not alter those measured results.

Python 3.12, CPU only. Install dependencies and run the data-independent tests from this directory:

```sh
make setup
make test
```

Integration tests explicitly skip when their real-data panel or fitted artifacts are absent.
To reproduce the complete experiment, supply the source snapshots identified by
`reports/source_manifest.json` under `data/raw/`, including `apy_wb.csv`,
`weather_existing.csv.gz`, and `centroids.csv`, with appropriate source permissions. Then run:

```sh
make train
make evaluate
make test
make predict
```

`make train` rebuilds features before training. To rerun only training against the audited panel:

```sh
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python -m rice_model.train
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 .venv/bin/python -m rice_model.evaluate
```

Once supplied locally, source snapshots under `data/raw/` make offline reproduction independent
of the application repository. Downloading fresh sources can change the experiment inputs.
Do not run downloads concurrently with feature building/training:

```sh
make fetch
make enrich
make train
make evaluate
```

Fetch requires locally supplied APY/weather/centroid seed snapshots. APY fresh-download attempts failed;
`make fetch` cannot recover a missing APY snapshot from a working upstream endpoint at present.
All attempted URLs, errors, provisional licensing notes, UTC timestamps and checksums are logged
in `reports/source_manifest.json`. A portal/catalogue response is not a usable feature export.
The optional `--import-snapshots PATH` fetch argument is an initial migration helper, not a runtime
dependency. Only use raw snapshots with the expected source checksum report.

## Audited inference

After reproducing the run or restoring the matching local processed panel, fitted weights,
and release report:

```sh
.venv/bin/python -m rice_model.inference \
  --district "South 24 Parganas" --season Winter --cutoff-date 2022-07-31
```

```python
from rice_model.inference import predict
result = predict("South 24 Parganas", "Winter", "2022-07-31")
```

Returns probability, expected anomaly in percent and t/ha, conformal 80% intervals, top-five
plain-language SHAP drivers, assumed lead time, quality flags, and the actual gate status.
Supported seasons: `Autumn`, `Winter`, `Summer`; fixed cutoffs only. Summer crop-year Y uses
15 March Y+1 under the documented, still-unverified source-calendar convention.

Only audited **2018–2022 crop-year historical replays** are available. There is no live-data or
future-date fallback. Darjeeling Autumn/Summer post-split rows are unavailable because the
Kalimpong components were not reported. Aliases are harmonised; Kolkata is excluded.
Adding `--require-released` rejects inference unless every release check passes.

Model selection, panel, source manifest and every loaded model have integrity hashes. After data
changes, retrain and reevaluate; do not bypass a checksum mismatch. Joblib files are trusted local
artifacts, not an interchange format for untrusted downloads.

## Key outputs

The table describes the complete local experiment. Paths containing datasets, `.joblib` weights,
and row-level outputs are intentionally ignored in this public checkout; the aggregate reports,
plots, experiment logs, and provenance/checksum metadata are included.

| Path | Purpose |
| --- | --- |
| `data/processed/panel.csv` | Real labelled observations and features; strict model feature allowlist |
| `reports/apy_drop_audit.csv` | Excluded Rice APY rows and reasons |
| `reports/feature_coverage.json` | Descriptive coverage; fold-local coverage is in experiment logs |
| `reports/results.csv` | Inner/outer fits, calibration, stacking, ablations, sensitivity, metrics and skips |
| `reports/model_comparison.csv` | Executed held-out baseline/family/ablation/sensitivity comparisons |
| `reports/confidence_intervals.json` | District–crop-year block-bootstrap uncertainty |
| `reports/model_release_report.json` | Fail-closed machine-readable release gate |
| `reports/selected_predictions.csv` | Out-of-time predictions from locked selections |
| `reports/calibration_bins.csv`, `calibration.png` | Reliability diagnostics, including empty bins |
| `reports/shap_*.csv/png`, `partial_dependence.csv/png` | Explanations and dependence diagnostics |
| `reports/district_year_season_diagnostics.csv` | Geographic and temporal failure analysis |
| `reports/worst_cases.csv`, `stress_years.json` | Largest errors and observed stress subsets |
| `reports/source_attempts.csv` | Exact download outcomes, URLs and checksums |
| `reports/data_inventory.json/csv` | Parsed content counts, periods, units and district coverage |
| `reports/weather_coverage_by_district.csv` | Actual observed/missing daily weather counts |
| `reports/environment.json` | Actual package versions, platform and code hashes |
| `models/selection.json`, `manifest.json`, `*.joblib` | Locked choices, hashes and per-origin artifacts |
| `MODEL_CARD.md`, `reports/RESULTS.md` | Generated measured results and explicit limitations |

The release gate requires positive Brier skill, AUC CI lower bound above 0.55, better Brier than
base rate and persistence, at least 25 held-out positives, interval coverage within five percentage
points of 80%, at least four test years, and verified temporal/source evidence. Missing evidence
produces `withheld`. Graph/LSTM and low-coverage feature groups are explicitly reported as skipped.

Direct dependencies are pinned in `requirements.txt`; generated `requirements.lock.txt` pins all
resolved packages for Linux/Python 3.12 and is used by `make setup` when present.
`reports/environment.json` records the environment and code hashes. Synthetic training-style fixtures
appear only in unit tests; SHAP/PDP perturbations are explanations, never training observations. Downloaded source redistribution terms
are not uniformly verified; see the manifest and model card before redistributing snapshots.
