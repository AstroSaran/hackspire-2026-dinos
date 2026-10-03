# West Bengal rice yield-shortfall experiment

Last evaluated: 2026-10-03. This is an offline, experimental crop-outcome model. It does **not** change the deployed Kavach application or DINOS's six-feature livelihood model, and it does not predict `distress_cascade_label`.

## Data and target

- APY source: Ministry of Agriculture district/crop/season area, production, and yield records. The local Kaggle snapshot contains 455,359 India rows; West Bengal contains 16,089 rows. Only West Bengal Rice seasons are used; APY's aggregate `Total` season rows are excluded.
- The four requested geography merges harmonize the panel to the 2011 vintage: Alipurduar→Jalpaiguri, Kalimpong→Darjeeling, Jhargram→Paschim Medinipur, and both Bardhaman subdivisions→Bardhaman. Where APY has split-district values, area and production are added before yield is recomputed as production divided by area.
- Label: `rice_yield_shortfall = 1` when the observed APY district-season Rice yield is strictly below 85% of the mean yield in the five immediately preceding consecutive APY years for that same harmonized district and season. Rows lacking any of those five years stay unlabeled.
- The label is an observed crop-yield-derived outcome, not a livelihood, employment, household, or distress outcome.

## Weather inputs

Daily Open-Meteo ERA5 reanalysis was collected for 1997-01-01 through 2025-12-31. West Bengal's 2011 district polygons were taken from the [Government of India district boundary service](https://mapservice.gov.in/gismapservice/rest/services/BharatMapService/Admin_Boundary_District/MapServer); split polygons were dissolved according to the mappings above, then one area-weighted polygon centroid was used per 2011 district. ERA5 grid-cell values at these points are not station readings or district-area averages.

The four inputs are full-window rainfall total, number of days with at least 1 mm rainfall, maximum rolling 7-day rainfall, and mean daily maximum temperature. Inputs end before the usual harvest period: Autumn/Aus uses February-June, Winter/Aman June-October, and Summer/Boro November of the prior calendar year through April. This is a broad pre-harvest calendar proxy; local planting and harvest dates vary. The broad season references are documented in the [FAO/FASAL crop-calendar paper](https://www.fao.org/fileadmin/templates/rap/files/meetings/2016/160524_AMIS-CM_5.1.3_Early_season_crop_forecasting_with_econometric_modelling_FASAL_in_India.pdf).

The archive is split into four requests: 1997-2004, 2005-2012, 2013-2020, 2021-2025. Three chunks of at most eight years cannot cover a 29-year range. Open-Meteo documents ERA5 historical coverage and multiple-location requests in its [Historical Weather API documentation](https://open-meteo.com/en/docs/historical-weather-api).

## Evaluation

There are 1,119 rows with a valid previous-five-year label, 63 positive shortfalls, 21 label years (2002-2022), and 18 districts. The chronological holdout is 2018-2022; it contains 270 rows and 12 positive shortfalls. All four weather inputs are present for each of these labeled rows. The requested minimum gates (150 rows, 25 positive labels, 8 years, 12 districts, and 5 positive test labels) pass.

| Probability score on 2018-2022 | AUC (higher is better) | Brier (lower is better) |
| --- | ---: | ---: |
| Weather Random Forest | 0.5036 | 0.129242 |
| Same district-season previous year | 0.5203 | 0.081481 |
| Base rate from training years only | 0.5000 | 0.042713 |

**Result: no skill claim.** The weather model does not beat persistence on AUC and has a worse Brier score than both baselines. Its 89.63% accuracy is below the 95.56% accuracy of predicting no event for all 270 test rows, reflecting the low event prevalence. These results do not support an operational warning.

## Reproduction

Download the real APY CSV snapshot used for the experiment and place it at:

```text
backend/data/raw/apy/crop-wise-area-production-yield.csv
```

Install the isolated experiment dependencies (not part of the live backend):

```powershell
cd backend
python -m pip install -r requirements-yield-experiment.txt
```

Fetch weather and run the time-split experiment:

```powershell
python -m app.validate_and_train_yield
```

With weather already cached locally:

```powershell
python -m app.validate_and_train_yield --skip-weather
```

The script writes a raw-chunk cache, feature panel, JSON report, and candidate `.joblib` model below `backend/data/experimental/rice-yield-shortfall/`. Local APY, weather cache, panel, report, and candidate model are intentionally excluded from Git; the script records APY and weather SHA-256 values in its report. Open-Meteo/ERA5 attribution and non-commercial free-service limits are recorded by the collector and must be respected.

The experiment is separate from `backend/app/collect_historical_weather.py`'s live Kavach feature snapshot: it uses historical 2011 district polygon centroids for this crop study and does not feed or modify the live dashboard.
