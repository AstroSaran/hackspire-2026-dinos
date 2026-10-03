# Kavach — Hackspire 2026

## 10-second pitch

Kavach is a place-aware resilience evidence workspace. It connects live weather
with official employment and market information when available, shows where
each source actually applies, and refuses to turn missing data into a risk
score.

## 30-second pitch

When livelihoods are at stake, fragmented public data can be as dangerous as
missing data: a model grid is not a street sensor, and a rural employment
aggregate is not evidence about an urban household. Kavach brings real
provider-backed weather together with official MGNREGA and mandi feeds when
connected. Every value carries source, time and coverage. If this municipal
address cannot be matched to a rural Gram Panchayat or validated outcome data,
the product says so before a decision is made.

## What the beta demonstrates

- A registered Sonarpur address and its location on a map.
- Real on-demand weather-model output with provider-resolved grid coordinates
  shown separately from the registered address point.
- A completed-month rainfall anomaly against a retrieved 1991–2020 ERA5
  reanalysis normal, with the month, source grid and retrieval time shown.
- A live modelled 0–7 cm soil-moisture field, explicitly distinguished from a
  field measurement or crop/water-stress index.
- Forecast screening watches derived from real model output, with thresholds
  and a clear distinction from official IMD warnings.
- A live, explainable environmental evidence model that refreshes in the
  background, plus a separate livelihood-model readiness panel.
- Optional live AGMARKNET daily prices and MGNREGA district aggregates through
  official data.gov.in resources.
- A direct, keyless route into the current West Bengal MGNREGA MIS. Its
  hierarchy reaches South 24 Parganas and the `SONAR PUR` block, with panchayat
  reports below it.
- A coverage caveat: the registered address is in Rajpur Sonarpur municipality;
  no rural GP match is verified, so block reports are context only.
- A rule-based data-fit panel explains the spatial level and applicability of
  each feed for this registered address.
- Optional private accounts can save encrypted user notes. Notes remain
  unverified and are never mixed into live panels or AI evidence.
- Bengali and English voice input requests consent before recording; clips go
  to Gemini for transcription, and users review the text before sending or
  explicitly saving it.
- A withheld livelihood assessment until real local inputs and outcome
  validation exist. The readiness model shows the missing evidence and gates
  scoring instead of inventing a prediction.

## Demo flow

1. Open the dashboard and confirm the registered point and its administrative
   description.
2. Refresh weather. Compare valid time, fetch time and provider grid location.
3. Open the official West Bengal MGNREGA MIS and browse its district and block
   hierarchy. Explain why those rural reports are not automatically assigned
   to the municipal address.
4. Show live market/employment feed records if API credentials and resource IDs
   are configured; otherwise show the exact backend settings still required.
5. Review which crop, water and vulnerability feeds remain unconnected.
6. Explain why Kavach withholds a risk score until spatial coverage and real
   outcome labels have been validated.
7. Show the data-fit panel and explain why daily mandi rows and rural
   employment aggregates do not represent a household at the address.

## Product boundary

Kavach is a source-attributed evidence workspace, not a validated early-warning
model. Weather values come from a forecast model blend, not a local sensor.
Forecast screening watches are not official warnings or impact thresholds.
AGMARKNET rows are dated mandi reports. MGNREGA block/district values are
administrative aggregates, not household demand at the selected address. Crop,
water and vulnerability feeds are not connected. The beta makes no benefit,
employment or migration decisions.

## Live refresh and limitations

The dashboard checks weather every five minutes while visible, pauses polling
in hidden tabs, and refreshes on focus or reconnect only when readings are
stale. Soil context is revalidated every fifteen minutes; market and employment
feeds hourly. These are query intervals, not promises that a source publishes
new records at that cadence.

Mandi prices require a data.gov.in API key and the active resource ID for the
Current Daily Price of Various Commodities from Various Markets (Mandi)
dataset. These are dated wholesale rows, not local real-time quotes. Crop,
water and validated livelihood outcomes remain disconnected. MongoDB accounts
and encrypted notes are optional and do not affect live panels or AI evidence.
IMD access remains unavailable until the required official access is granted.

## Pilot roadmap

1. Configure and validate the official data.gov.in market and employment
   resource IDs.
2. Verify the registered address against authoritative municipal and rural
   administrative boundaries before using panchayat-level records.
3. Add appropriately resolved crop and water observations with source dates.
4. Partner with a local authority to collect privacy-safe outcome observations.
5. Only then define, validate and present a livelihood-risk model.
