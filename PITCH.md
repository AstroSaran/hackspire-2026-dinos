# Kavach — Pitch Prep

## 10-second pitch
Kavach spots when a village's weather, crop, market and employment risks are
converging into a livelihood distress cascade, and tells an officer what to
do about it — weeks before the crisis peaks.

## 30-second pitch
India already tracks weather (Meghdoot), crop insurance (PMFBY), mandi
prices (e-NAM) and employment demand (MGNREGA) — but a farmer household
experiences all four as one connected crisis, and none of these systems talk
to each other. Kavach fuses those signals into a single risk score, explains
which driver is responsible, predicts how the cascade will unfold, and ranks
the best available intervention from programs that already exist — so
prevention happens instead of just monitoring.

## 2-minute demo script
1. Open the district view — 30 villages, colour-coded 🟢🟡🟠🔴 (10s)
2. Click the top-risk village → driver breakdown appears: "why is risk
   rising" (20s)
3. Point at the cascade chain, explain the conditional probabilities decay
   stage by stage (20s)
4. Show the ranked interventions, tied to a real program (PMFBY/MGNREGA/
   mKisan/e-NAM) with urgency/benefit/cost (20s)
5. Click "Simulate 8-week trajectory" — narrate the village moving from
   stable to critical while the model recomputes live; call out the real
   computed lead time (30s)
6. Close: "None of this replaces Meghdoot or MGNREGA — it makes them work
   together around the household's risk trajectory." (20s)

## 3-minute technical explanation
- **Why not an LLM for the score**: tabular model (RandomForest) trained on
  engineered features is auditable and reproducible; an LLM is only used
  (optionally) downstream to phrase the explanation in natural language.
- **Explainability**: feature importance × local severity, a lightweight
  deterministic stand-in for SHAP — chosen for auditability in a public-sector
  tool over marginal precision gains.
- **Cascade engine**: a multiplicative transition chain (each stage's
  probability = previous stage × a driver-specific transition factor),
  guaranteeing a cascade can't be "more likely" than the shock that started
  it, while still differentiating which stage breaks first per village.
- **Intervention engine**: rule-based and transparent by design — every
  recommendation cites the real program it routes to and the specific driver
  that triggered it, not a black-box suggestion.

## Judge Q&A
**Why did you build this?**
Existing rural data systems in India are individually strong but
fragmented; a household's crisis is multi-domain and current infrastructure
can't see the interaction.

**Who needs it?**
Block/district-level rural development officers who currently have to check
weather, insurance, market and employment systems separately to decide where
to intervene.

**Why existing solutions aren't enough?**
Meghdoot, e-NAM, PMFBY and MGNREGA each monitor one domain well. None fuse
signals into a single household/village risk trajectory or rank
interventions across programs.

**What's innovative?**
Not the individual data sources — the decision layer: convergence detection,
cascade prediction, and cross-program intervention ranking in one auditable
pipeline.

**Why AI, specifically?**
Because "is this village's risk rising, and why" isn't a single-threshold
rule — it depends on how several moderate signals combine, which is exactly
what a trained classifier over engineered features is for. We deliberately
avoided an LLM as the predictor.

**Why this architecture?**
Simplicity and defensibility over sophistication: a tabular model beats a
black-box one for a decision tool that has to be explained to a
non-technical rural officer and audited later.

**How does it work technically?**
Six engineered features → RandomForest → risk probability → feature
importance × local severity for driver attribution → causal-graph-weighted
cascade chain → rule-based intervention ranking.

**What data does it use?**
Rainfall anomaly, crop-stress index, mandi price deviation, MGNREGA demand
spike, water-stress index, historical vulnerability. Currently a
representative/simulated dataset calibrated to published statistic ranges —
**not live feeds** (see README "Data & Limitations").

**How accurate is it?**
AUC 0.73, precision 0.43, recall 0.63 on held-out data — but that measures
how well the model recovers the synthetic causal structure we built into
the training data, not real-world accuracy, because no public ground-truth
outcome dataset exists yet for this problem. We say this upfront rather than
letting anyone assume otherwise.

**What happens when the model is wrong?**
False positives cost a low-cost advisory/monitoring action; false negatives
are the real risk, which is why the intervention engine biases toward
low-cost, high-benefit actions (advisories, eligibility checks) at the
lower-urgency risk bands rather than reserving action only for "critical."

**How do you handle privacy?**
The pilot design is deliberately village/block-level, not household-level,
specifically to avoid handling individual debt/distress data, which the
research review flagged as both the most sensitive and the least available
signal.

**How would you scale it?**
Same pipeline, more districts, once live data connectors (Open-Meteo/IMD,
Earth Engine NDVI, AGMARKNET, NREGA MIS) replace the representative dataset
— the API and model layers don't change.

**What does it cost?**
Not yet estimated — no real infrastructure or API costs have been measured
at pilot or scale; this is not yet quantified.

**What is the biggest limitation?**
No public ground-truth outcome data. Every accuracy number in this project
is a statement about internal consistency with a literature-grounded
simulation, not validated field performance. A real pilot needs a rural
development department partner willing to track actual outcomes.

**What would you build next?**
Live data connectors, a real outcome-tracking partnership for one district,
and full SHAP-based explainability once the model is retrained on any real
labeled outcomes that emerge from that pilot.

*No metrics, users, partnerships, or accuracy figures beyond what's in
`backend/model_artifacts/metrics.json` are claimed anywhere in this project.*
