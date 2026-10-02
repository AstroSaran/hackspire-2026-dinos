# Kavach — Pitch Prep (corrected framing)

## 10-second pitch
Kavach turns India's fragmented weather, crop, market and employment signals
into one auditable early-warning workflow — it estimates risk, explains why,
explores plausible scenarios, and hands an officer a ranked set of actions
to review, using programs that already exist.

## 30-second pitch
India already tracks weather (Meghdoot), crop insurance (PMFBY), mandi
prices (e-NAM) and employment demand (MGNREGA) — but a household experiences
all four as one connected crisis, and none of these systems talk to each
other. Kavach fuses those signals into an estimated risk score, shows which
signal is driving it, walks through an illustrative scenario trajectory, and
surfaces rule-based suggested actions tied to real programs — for a human
officer to review, not for the system to decide alone.

## What changed, and why we're leading with it
An earlier version of this project presented model output as if it were a
validated prediction of real-world distress, and a hand-built cascade as if
it were an empirically observed probability. Neither claim was true, and we
corrected it rather than paper over it: every score is now labeled
"estimated," every cascade is now labeled "illustrative scenario," and the
dashboard carries a permanent validation-status panel stating plainly that
this is not field-validated. We think this makes the project *more*
credible, not less — a judge asking "how do you know this works?" gets an
honest, specific answer instead of a deflection.

## 2-minute demo script
1. Open the dashboard — pilot-mode banner is visible at the top; 30
   villages, colour-coded 🟢🟡🟠🔴 (10s)
2. Click the top-risk village → **observed signals** panel appears first,
   each with a provenance badge (10s)
3. Point at the **model assessment**: estimated risk score plus a genuine
   model-uncertainty measure (tree disagreement in the forest) (20s)
4. Point at **driver contribution — indicative**: real SHAP output, labeled
   as model explanation, not causal proof (20s)
5. Point at the **illustrative scenario trajectory**: each stage tagged
   observed-signal or scenario-estimate, with a confidence that decays down
   the chain (20s)
6. Show **suggested actions for officer review** — rule-based, deterministic,
   each tied to a real program, each requiring review (20s)
7. Click Approve/Defer/Escalate — narrate the human-in-the-loop step and the
   outcome-tracking field that stays null until a real pilot exists (20s)
8. Close: "Kavach doesn't replace Meghdoot or MGNREGA — it makes them work
   together, and it tells you exactly how confident to be at every step." (20s)

## 3-minute technical explanation
- **Why not an LLM for the score**: a tabular RandomForest trained on
  engineered features is auditable and reproducible; an LLM is only used
  (optionally) downstream to phrase the explanation, never to compute it.
- **Why "estimated risk score," not "probability of distress"**: the
  training label is a literature-grounded synthetic construction, not an
  observed outcome, so we don't dress it up as a calibrated probability of a
  real-world event.
- **Genuine uncertainty**: we report the standard deviation of per-tree
  probability estimates across the forest — an actual measure of model
  disagreement, not a cosmetic confidence number.
- **Real SHAP, honestly scoped**: TreeExplainer output is genuine model
  explanation; we label it "indicative" because explaining the model's
  reasoning is not the same as proving what caused a real household's
  situation.
- **Scenario trajectory, not cascade prediction**: the multiplicative
  transition chain guarantees a stage can't be "more likely" than the shock
  that started it, but every stage carries an evidence-status tag
  (`OBSERVED_SIGNAL` / `SCENARIO_ESTIMATE` / `SCENARIO_INDICATOR`) so nobody
  reads a hand-designed weight as an empirical probability.
- **Intervention engine, deliberately not ML**: rule-based and
  deterministic — same inputs always produce the same suggested actions
  (this is tested), which is what makes it auditable by a human reviewer.

## Judge Q&A
**Why did you build this?**
Existing rural data systems in India are individually strong but
fragmented; a household's crisis is multi-domain and current infrastructure
can't see the interaction.

**Who needs it?**
Block/district-level rural development officers who currently check
weather, insurance, market and employment systems separately to decide
where to intervene — Kavach is a decision-support aid for them, not a
replacement for their judgment.

**Why existing solutions aren't enough?**
Meghdoot, e-NAM, PMFBY and MGNREGA each monitor one domain well. None fuse
signals into a single household/village risk trajectory or rank
interventions across programs.

**What's innovative?**
Not the individual data sources — the decision layer: convergence
detection, scenario exploration, and cross-program action suggestion, with
every claim labeled by evidence type (observed / model / scenario).

**Why AI, specifically?**
Because "is this village's risk rising, and why" depends on how several
moderate signals combine — exactly what a trained classifier over
engineered features is for. We deliberately avoided an LLM as the
predictor, and we deliberately avoided presenting the classifier's output
as more certain than it is.

**Why this architecture?**
Simplicity and honesty over sophistication: a tabular model with real SHAP
and a rule-based action layer beats a black-box pipeline for a tool that
has to be explained to, and audited by, a non-technical rural officer.

**How does it work technically?**
Six engineered features → RandomForest → estimated risk score + tree-based
uncertainty → SHAP driver attribution → causal-graph-weighted scenario
trajectory → rule-based action suggestions → officer review → (future)
outcome logging.

**What data does it use?**
Rainfall anomaly, crop-stress index, mandi price deviation, MGNREGA demand
spike, water-stress index, historical vulnerability. Currently
representative/simulated, calibrated to published statistic ranges — not
live feeds (full provenance at `GET /provenance`).

**How accurate is it?**
AUC 0.73, precision 0.43, recall 0.63 on held-out data — but this measures
how well the model recovers the synthetic causal structure we built into
the training data, not real-world accuracy, because no public ground-truth
outcome dataset exists yet for this problem. `is_field_validated` is
hard-coded `False` in the API. We lead with this limitation rather than
waiting to be asked.

**What happens when the model is wrong?**
False positives cost a low-cost advisory/monitoring action; false negatives
are the real risk, which is why suggested actions bias toward low-cost,
high-benefit steps (advisories, eligibility checks) even at moderate risk
levels rather than reserving action only for "critical" — and every action
still requires officer review before anything happens.

**How do you handle privacy?**
The pilot design is deliberately village/block-level, not household-level,
specifically to avoid handling individual debt/distress data, which the
research review flagged as both the most sensitive and the least available
signal.

**How would you scale it?**
Same pipeline, more districts, once live data connectors (Open-Meteo/IMD,
Earth Engine NDVI, AGMARKNET, NREGA MIS) replace the representative
dataset — the API, model, and action-engine layers don't change.

**What does it cost?**
Not yet estimated — no real infrastructure or API costs have been measured
at pilot or scale; this is not yet quantified.

**What is the biggest limitation?**
No public ground-truth outcome data. Every accuracy figure in this project
describes internal consistency with a literature-grounded simulation, not
validated field performance. A real pilot needs a rural development
department partner willing to record the `subsequent_outcome` field this
build already reserves for that purpose.

**What would you build next?**
Live data connectors, a real outcome-tracking partnership for one district,
and a retrained, re-validated model once any real labeled outcomes exist
from that pilot — at which point, and only then, "estimated risk score"
could be revisited as a calibrated probability.

*No metrics, users, partnerships, or accuracy figures beyond what's in
`backend/model_artifacts/metrics.json` are claimed anywhere in this
project. `is_field_validated` is `False` everywhere it appears.*
