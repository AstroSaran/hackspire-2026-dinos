"""Render human-readable reports only from executed experiment outputs."""
import json
import math

import pandas as pd

from .common import ROOT, RAW, PROCESSED, REPORTS,save_json,sha,utc


def table(frame,columns=None):
    frame=frame[columns] if columns else frame
    def value(x):
        if isinstance(x,float):return f'{x:.5g}' if math.isfinite(x) else '—'
        return str(x).replace('|','/').replace('\n',' ')
    header='| '+' | '.join(frame.columns)+' |\n| '+' | '.join(['---']*len(frame.columns))+' |\n'
    return header+'\n'.join('| '+' | '.join(value(x) for x in row)+' |' for row in frame.itertuples(index=False,name=None))+'\n'


def write_reports(gate,comparison):
    panel=json.loads((REPORTS/'panel_summary.json').read_text())
    coverage=json.loads((REPORTS/'feature_coverage.json').read_text())
    manifest=json.loads((REPORTS/'source_manifest.json').read_text())
    source=pd.DataFrame(manifest)
    cross=json.loads((REPORTS/'rainfall_crosscheck.json').read_text()) if (REPORTS/'rainfall_crosscheck.json').exists() else {}
    m=gate['metrics'];ci=gate['confidence_intervals_95'];n=lambda x:f'{x:.5g}'
    group_rows=[]
    for name,details in coverage.items():
        group_rows.append({'group':name,'joint_coverage':details['coverage'],'eligible':details['eligible'],
                           'selected_features':', '.join(details['eligible_features']) or 'none'})
    failed=[];runs=pd.read_csv(REPORTS/'results.csv')
    for row in runs.itertuples():
        if not isinstance(row.details,str):continue
        info=json.loads(row.details)
        for fit in info.get('fits',[]):
            if fit['status']!='OK':failed.append({'stage':row.stage,'model':row.model,'year':row.year,**fit})
    pd.DataFrame(failed,columns=['stage','model','year','season','target','status','error']).to_csv(REPORTS/'failed_fits.csv',index=False)
    checks=pd.DataFrame([{'check':k,'passed':v} for k,v in gate['checks'].items()])
    columns=['model','rows','positives','auc','ap','brier','brier_skill','anomaly_pct_mae','anomaly_pct_rmse','anomaly_pct_r2']
    diagnostic=pd.read_csv(REPORTS/'district_year_season_diagnostics.csv')
    worst_districts=diagnostic[diagnostic.group.eq('district')].sort_values('anomaly_pct_mae',ascending=False).head(5)
    year_errors=diagnostic[diagnostic.group.eq('crop_year')]
    error_columns=['value','rows','positives','brier','anomaly_pct_mae','anomaly_pct_rmse','anomaly_pct_coverage']
    stress=json.loads((REPORTS/'stress_years.json').read_text())
    stress_rows=pd.DataFrame([{'subset':name,**item['metrics']} for name,item in stress.items()])
    card=f'''# West Bengal preharvest rice shortfall model

## Status: {gate['status'].upper()}

This is a reproducible **retrospective research hindcast**, not a released prospective warning service.
The machine-readable decision is `reports/model_release_report.json`. Inference returns the withheld
status; `--require-released` fails closed. No label threshold was loosened to obtain more events.

## Task and population

- Eighteen Census-2011 West Bengal district units, Kolkata excluded. Split districts are aggregated
  by area and production, then yield recomputed. Missing split components are not assigned zero.
- Rice seasons: Autumn/aus, Winter/aman, Summer/boro. Cutoffs: 30 June, 31 July, 15 March.
- Assumed crop-year convention: APY YYYY–YYYY+1; boro cutoff occurs in the ending year.
  **Source-specific verification is outstanding**, so these are conditional hindcasts.
- Primary label: observed yield **strictly below 85%** of the previous five consecutive years' mean.
  A missing prior year means a missing label, never an imputed baseline.
- Auxiliary targets: anomalies in t/ha and percent against both trailing-five mean and an earlier-years
  district-season linear trend. Separate real-data 10% and 20% shortfall sensitivity fits are reported.

## Actual dataset

Processed panel: {panel['rows']} district-season-years; labeled rows: {panel['labeled_rows']};
observed 15% shortfalls: {panel['positives']}. Labeled crop-years: {min(panel['years'])}–{max(panel['years'])}.
The APY snapshot ends at agricultural year 2022–2023; no 2023-start APY records were obtained.
`reports/apy_drop_audit.csv` lists every excluded Rice source row and reason.
`data/processed/panel.csv` SHA-256: `{panel['panel_sha256']}`.

There is no generated or imputed training data. Aggregations, fitted indices and derived labels use
observed inputs. Incomplete daily windows stay missing; no temporal interpolation, forward fill,
median fill, SMOTE, class balancing, or artificial adverse labels is performed.
Boosted trees use native missing-value handling; linear/mixed models exclude incomplete cases.
Numerical scaling and one-hot district/season encoding are transformations, not missing-value filling.

### Source and feature limitations

- APY and archive best-match weather were imported from existing checksum-verified raw snapshots.
  This verifies local consistency, not source authenticity, boundary history, or redistribution rights.
- Newly downloaded explicit ERA5 has partial district coverage; NASA POWER provides real daily
  temperatures where explicit ERA5 is absent. Sources are not spliced to fill individual missing days.
  POWER's local-solar-day and ERA5's Asia/Kolkata civil-day aggregation are not subdaily aligned.
- Point weather at recorded centroids is not a district-area-weighted average. Original centroids'
  geometry provenance has not been independently verified. ERA5-Land requests were rate-limited.
- NOAA ONI/DMI and IBTrACS were downloaded. Final reanalysis/index/track revisions can differ from
  what was available in real time. Assumed lags: weather seven days; ONI/DMI 45 days; APY 12 months
  after assumed harvest. No historical release-vintage archive was established.
- Census-2011 features are only eligible from a conservative 2014 availability date; never backfilled.
  Their temporal coverage fails the threshold. Markets, groundwater, NDVI/EVI, irrigation and MGNREGA
  lack verified district-period exports at sufficient coverage. Catalogue/portal pages are not datasets.
- Official boundary download failed TLS verification; spatial-neighbour lag remains missing.
  Split-district source naming before actual reorganisations requires independent historical checking.
- CHIRPS cross-check is limited to one centroid and month: {json.dumps(cross,ensure_ascii=False)}.
  It does not validate statewide rainfall or provide a bias correction.
- Licences are recorded verbatim/provisionally in the manifest. Unknown redistribution terms remain
  unresolved; no blanket claim is made that all downloaded snapshots are freely redistributable.

Full-panel descriptive coverage (model selection recomputes this using **training folds only**):

{table(pd.DataFrame(group_rows))}

Columns are added in decreasing observed coverage while preserving at least 60% joint group coverage.
This can retain only part of a group: e.g. SPI is not evidence that low-coverage SPEI/soil were used.
Parsed source counts, date ranges and units are in `data_inventory.json/csv`; per-district observed
daily counts are in `weather_coverage_by_district.csv`. HTTP success alone is not coverage evidence.

## Evaluation protocol

- Outer expanding annual origins; training labels must be released before 30 June of that crop-year,
  the earliest issue date. Summer predictions conservatively use the same frozen crop-year model.
- Development selection: 2012–2015. Locked untouched family evaluation: 2018–2022. Auxiliary
  2009-onward out-of-time predictions support calibration and stacking. No shuffled split.
- Inner tuning: outer-year minus four and minus three, only their then-released training labels.
  Two small fixed settings per family; risk Brier objective. Regression shares risk-selected settings
  within each family; an independently regression-tuned hyperparameter search was **not** performed.
- Families: logistic/ridge, elastic-net logistic/regression, LightGBM, XGBoost, CatBoost,
  Bayesian logistic and linear district-random-intercept mixed effects, per-season LightGBM.
- Baselines: released-history base rate, last available district-season outcome persistence,
  district-season climatology, and zero anomaly / zero shortfall under trailing-mean yield.
  Exact previous-year persistence is unavailable under the conservative publication lag.
- Linear/elastic development coverage is reduced by complete-case exclusion. Family selection
  requires at least 95% development risk coverage; such candidates cannot win on easier subsets.
  Every comparison records its evaluated row count; paired baseline skill uses the same rows.
- Stacking: logistic risk/ridge anomalies from strictly earlier released OOF base predictions.
  Isotonic fits use strictly earlier released OOF probabilities. Insufficient calibration history
  produces a logged identity transform, not a fitted calibration claim.
- Quantiles 10/50/90: separate LightGBM models frozen before calibration crop-year outer-minus-two.
  Sorted quantiles remove crossing; nonnegative CQR score and finite-sample order statistic widen
  the interval. Calibration labels are never refitted into that interval predictor.
  Distribution-free exchangeability is not assumed to hold for a changing climate/time series.
- Confidence intervals: 500 district–crop-year block bootstrap resamples, retaining seasons within
  each block. These may understate uncertainty from common year shocks across districts.
  Metrics weight observed district-seasons equally, not by cultivated area.
- Conditional ablations remove each eligible group from LightGBM with fresh inner tuning on identical
  origin folds. Low-coverage groups are explicitly skipped, not assigned fabricated zero impact.
- Graph/LSTM are logged as not attempted; no verified adjacency and sparse annual outcomes justify
  the simpler model comparison first. Test results do not retroactively change the selected family.

## Locked selection and measured held-out results

Risk model: **{gate['classifier']}**. Anomaly model: **{gate['regressor']}**.
Evaluated observations: {m['rows']}; positive shortfalls: {m['positives']}.
Positive counts by crop-year: `{json.dumps(gate['positives_by_year'])}`.

- AUC: **{n(m['auc'])}**, 95% CI **[{n(ci['auc']['lower'])}, {n(ci['auc']['upper'])}]**.
- Average precision: **{n(m['ap'])}**; Brier: **{n(m['brier'])}**;
  Brier skill versus released-history base rate: **{n(m['brier_skill'])}**.
- Percent-anomaly MAE: **{n(m['anomaly_pct_mae'])} percentage points**;
  RMSE: **{n(m['anomaly_pct_rmse'])}**; R²: **{n(m['anomaly_pct_r2'])}**.
- t/ha-anomaly MAE: **{n(m['anomaly_mae'])}**; RMSE: **{n(m['anomaly_rmse'])}**.
- Nominal 80% percent-anomaly interval observed coverage: **{n(m['anomaly_pct_coverage'])}**;
  mean width: **{n(m['anomaly_pct_width'])} percentage points**.

All target units, detrended metrics and CIs are in the release report and `confidence_intervals.json`.

### Release gate

{table(checks)}

Outstanding evidence:
{chr(10).join('- '+x for x in gate['evidence_blockers'])}

### Full held-out comparison (not used to choose a new winner)

{table(comparison,columns)}

The `lightgbm_label10` and `lightgbm_label20` rows have different binary labels and are sensitivity
analyses, not directly interchangeable AP/AUC comparisons. All other risk rows use 15% shortfall.
The quantile-only row has zero **risk** observations because it does not produce probabilities;
its interval coverage/width are evaluated separately on the same held-out observations.

## Explanations and error analysis

`shap_local.csv`, `shap_top_five.csv`, `shap_global.csv` and `shap_global.png` describe the selected
calibrated probability. Permutation SHAP uses actual training-background rows and one permutation;
it is an approximation, checked for additivity, not causal attribution. No explanation perturbation
is saved as training data. PDP uses observed training quantiles and can break weather correlations.
`explanation_status.json` records any failures. `partial_dependence.csv/png` retain per-fold curves.
`district_year_season_diagnostics.csv`, `worst_cases.csv`, and `stress_years.json` expose failures,
including empty/zero-positive stress subsets; no metric is invented when a subset is undefined.

Highest district percent-anomaly MAEs (descriptive small subsets, not district release approvals):

{table(worst_districts,error_columns)}

Held-out crop-year diagnostics:

{table(year_errors,error_columns)}

Stress subsets (pre-cutoff exposure only; a named cyclone calendar-year is not causal attribution):

{table(stress_rows,['subset','rows','positives','auc','brier','anomaly_pct_mae','anomaly_pct_coverage'])}

## Intended use and limits

Use for retrospective evaluation and collecting the missing evidence. Do not treat these scores as
released operational warnings, district crop-loss measurements, or causal climate-impact estimates.
API supports audited out-of-time **2018–2022 crop-year replays** only; it rejects unsupported dates,
missing district components and checksum mismatches. Live future-year inference is not enabled
without a newly audited feature panel and prospective evidence.

See `README.md` for execution commands and `reports/results.csv` for every tuning, calibration,
ablation, sensitivity, evaluation and skipped optional experiment. Fit failures/convergence warnings
are preserved in diagnostics; extracted failures are in `failed_fits.csv`. Archived interrupted runs
are retained as `results_previous_*.csv` and are not mixed into the final comparison.
'''
    (ROOT/'MODEL_CARD.md').write_text(card)
    (REPORTS/'RESULTS.md').write_text('# Executed results\n\n'+
        f"Release status: **{gate['status']}**. Locked classifier: **{gate['classifier']}**.\n\n"+
        table(comparison,columns)+'\n## Feature coverage\n\n'+table(pd.DataFrame(group_rows))+
        '\n## Source attempt outcomes\n\n'+table(source.groupby('status').size().rename('attempts').reset_index())+
        '\nFull URLs, checksums, licences and exact errors: `source_attempts.csv` / `source_manifest.json`.\n'+
        '\n## Release checks\n\n'+table(checks)+'\nSee `../MODEL_CARD.md` for protocol and limitations.\n')


def main():
    """Refresh presentation from saved measured outputs without rerunning experiments."""
    write_reports(json.loads((REPORTS/'model_release_report.json').read_text()),
                  pd.read_csv(REPORTS/'model_comparison.csv'))
    path=REPORTS/'environment.json'
    environment=json.loads(path.read_text())
    environment['documentation_refreshed_at']=utc()
    environment['final_code_sha256']={str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'rice_model').glob('*.py')}
    save_json(path,environment)
    print('Regenerated MODEL_CARD.md and reports/RESULTS.md from saved measured outputs.')


if __name__=='__main__':main()
