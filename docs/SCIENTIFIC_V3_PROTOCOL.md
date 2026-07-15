# Scientific v3 protocol: long-term-care norovirus

Status: **implementation in progress; no scientific candidate has passed these
gates and no production cohort should be frozen yet.**

The current development branch implements the data-contract, private trace,
static-topology Starsim, pre-branch manifest, attested vector-evaluation, and
local-readiness building blocks. It does **not** yet wire the trace projector or
manifest into one public closed-loop v3 runtime. Temporal contact records are
still collapsed to a static transmission graph, source acquisition is not
independently authenticated, and no posterior fit, external validation, or
human study has been completed. This is publishable engineering progress, not
completion of the scientific milestone below.

## Intended use

The first scientific profile is deliberately narrow:

> Evaluate whether an agent can investigate a suspected norovirus outbreak in
> a U.S. long-term-care facility, update a calibrated belief about its cause and
> trajectory from delayed and incomplete records, and choose a defensible
> response under uncertainty.

It is not a universal disease-surveillance benchmark. Schools, hospitals,
restaurants, and community surveillance require different populations,
observation processes, and intervention evidence. They may later become
separately validated profiles.

V3 is therefore a **scenario-pack architecture**, not a one-scenario system.
The reusable benchmark kernel owns the public broker, clocks and budgets,
observation release, action ledger, sandbox boundary, rollout commitments,
scoring interfaces, and adversarial audits. A validated scenario pack supplies
its population and places, disease process, operational records, investigation
requests, executable actions, outcome vector, calibration sources, and claim
limits. Long-term-care norovirus is the first pack because a narrow intended use
can be tested scientifically; it must not hard-code LTC-specific entities or
answer choices into the shared kernel.

## Finite hypothesis catalog

The LTC norovirus pack currently publishes six stable public choices:

- `propagated`: person-to-person transmission within the facility;
- `common_source`: a shared contaminated source or environmental exposure;
- `repeated_introduction`: multiple independent entries into the facility;
- `reporting_artifact`: duplicated, mislinked, or delayed records;
- `sporadic_background`: unrelated background illnesses; and
- `other_or_insufficient`: another mechanism or insufficient evidence.

This is not a one-shot multiple-choice question. The agent must assign one
probability distribution across all six choices, investigate, forecast, act,
observe what happens, and update its final distribution. The scorer uses a
multiclass Brier rule and the trace-derived oracle explanation. The catalog
contains no correct-answer marker, and the private scenario stratum is not a
scoring input. Future scenario packs may publish different choices without a
kernel change.

Starsim remains the execution engine because it supports custom diseases,
networks, interventions, and analyzers. Using Starsim is not itself evidence of
realism; the disease-, facility-, observation-, and action-specific modules must
each be calibrated and checked.

## Why v2 cannot simply be retuned

The existing NORS cohort pools eight institutional settings over 2009–2018 and
fits one generic 1,000-person institution. Re-stratifying the locally retained
CDC-shaped snapshot shows a large time pattern even within long-term care. Its
hashes were recorded after acquisition, but acquisition has not been
independently authenticated, so these values remain development evidence:

| Era | Reported LTC person-to-person norovirus outbreaks | q25 / median / q75 reported illnesses |
|---|---:|---:|
| 2009–2012 | 2,723 | 19 / 34 / 55 |
| 2013–2016 | 4,679 | 15 / 27 / 44 |
| 2017–2019 | 4,257 | 12 / 22 / 36 |
| 2019 only | 1,588 | 12 / 21 / 35 |

These values are observations of **reported outbreaks**, not latent infections.
The confirmed-only share also falls from 64.2% in 2009–2012 to 33.7% in
2017–2019. The confirmed-versus-suspected mix, participating jurisdictions, reporting
practice, facility mix, circulating strains, and control practice also change
over time. A calendar-year coefficient may describe this drift, but it must not
be presented as a biological mechanism. The first task is to separate and
model the reporting process rather than force transmission to explain every
change in NORS.

## Three linked models

### 1. Facility and infection process

The v3 institutional world must represent at least:

- residents, staff, and outside visitors as different roles;
- facility size, rooms, wards, shared dining, and staff assignments;
- within-room, within-ward, staff-mediated, shared-meal, and outside-entry
  opportunities;
- one-to-three plausible introductions rather than outcome-selected seeding;
- incubation, symptomatic and asymptomatic infection, symptom-dependent
  infectiousness, recovery, and an optional environmental contamination route;
- resident/staff and symptom heterogeneity supported by the visible Adams line
  lists, with uncertainty rather than exact hard-coded ratios.

The initial release should target long-term care only. CMS Provider Information
and Payroll-Based Journal data can inform the distribution of certified beds,
resident census, staffing, and turnover. Contact and movement assumptions that
cannot be directly identified must remain explicit sensitivity dimensions.

### 2. Surveillance and investigation process

Latent infections must not become agent observations directly. V3 models the
following stages separately:

```text
symptoms
  -> recognition by resident, staff, or facility
  -> facility record or care encounter
  -> alert threshold
  -> health-department notification
  -> investigation and active case finding
  -> specimen collection and assay
  -> preliminary report, amendment, and final outbreak record
```

Delays, missingness, testing, nonresponse, duplicates, and amendments depend on
role, severity, facility, channel, and time. Interviews and inspections must be
derived from simulated shifts, contacts, meals, entries, symptoms, and records.
They may be noisy, but they may never sample a convenient answer directly from
the hidden causal-mode label.

NORS can constrain final reported-outbreak margins. It cannot identify the
false-alert denominator, quiet facility-days, active-case-finding yield,
duplicate prevalence, or latent infections. Those require deidentified facility
symptom/EHR logs and local or state alert-and-investigation logs. NEARS and
linked NORS/CaliciNet/NoroSTAT records are complementary sources for food-service
and reporting-delay components.

### 3. Intervention and utility process

The v2 controls are research placeholders. V3 decomposes them into observable
actions such as:

- active case finding and targeted testing;
- resident cohorting or isolation;
- symptomatic staff exclusion and replacement staffing;
- soap-and-water hand hygiene, PPE, and environmental/vomit cleanup;
- admission, transfer, and visitor restrictions;
- removal of an implicated meal, batch, handler, or source;
- correction of duplicate or malformed surveillance records.

Each action has uncertain uptake, delay, adherence, effectiveness, interaction,
and burden. Published evidence is often low quality, so effect sizes must be
represented as broad evidence-anchored distributions and stress scenarios, not
three secret constants.

Policy value is estimated over multiple future random draws and parameter draws
conditioned on the same opening history. The benchmark reports a vector of
outcomes—resident and staff illness, staff absence, hospitalization/death,
outbreak duration, restriction days, tests, cleaning and investigation burden,
false escalation, and unresolved reporting errors—before applying any
stakeholder weights. A correction is therefore not mechanically penalized;
its staff time remains an operational burden while errors left unfixed remain
a harm. Rankings must be tested across preregistered utility profiles.

## Calibration and validation workflow

1. **Freeze the claim and estimands.** Pin source bytes, parsers, cohort rules,
   target era, metrics, priors, candidate ledger, and failure rules.
2. **Run prior-predictive and recovery checks.** Simulate from known parameter
   draws and verify that the inference procedure can recover identifiable
   quantities. Report non-identifiability instead of converting it into a point
   estimate.
3. **Fit a posterior, not one winning grid cell.** Jointly fit facility,
   transmission, and observation parameters while preserving correlations.
4. **Check joint opening transcripts and full trajectories.** Required targets
   include size and tails, duration, daily curve, peak timing, first-day cases,
   resident/staff and ward distribution, symptoms, specimens, notification and
   laboratory delays, missingness, duplicates, background counts, and their
   correlations.
5. **Use grouped validation.** Use rolling-origin development checks and hold
   out whole states, facilities, and data sources. Random rows from the same
   outbreak or facility are not an independent test.
6. **Use an independent blind test once.** The Adams six-outbreak line list and
   all viewed NORS years are development evidence. A future NORS vintage can
   blindly test only reported-outbreak observables. At least one independent
   line-list/operational source is required for the full task.
7. **Validate actions separately.** Check expected dose response, wrong-route
   negative controls, no pre-action divergence, empirical effect intervals,
   seed/parameter uncertainty, and severe-tail harms.
8. **Run construct-validity studies.** Epidemiologists and infection
   preventionists receive the same information available to agents. Measure
   solveability, probability calibration, action agreement, time, and
   inter-rater reliability. Ambiguous episodes receive multiple acceptable
   answers or are excluded by a predeclared rule based only on opening evidence.

Simulation-based calibration validates the inference implementation; posterior
predictive checks ask whether fitted worlds reproduce relevant observations.
Neither proves that the model is universally true.

## Reward and shortcut guardrails

- Score probabilistic beliefs with proper scoring rules and decisions with
  expected regret over an ensemble; do not collapse both into one opaque score.
- Construct matched alternatives using opening information and pre-action
  nuisance variables only. Never accept or reject an episode using its future
  outcome or the action that eventually wins.
- Include real outbreaks with reporting errors and non-norovirus illness, not
  only pure “no infection” negative modes.
- Test inspect-all, request-everything, always-escalate, always-do-nothing,
  metadata-only, adaptive action-timing, evaluator-tampering, and prompt-
  injection policies.
- Report component scores, average performance, confidence intervals, and
  severe-event/tail failures. A single scalar leaderboard is secondary.

## Local readiness checklist

`epiagentbench.scientific_readiness` requires a complete, committed local
checklist for:

1. the LTC estimand contract;
2. temporal/reporting-drift characterization;
3. joint posterior-predictive checks;
4. observation-process validation;
5. independent blind external validation;
6. intervention-uncertainty validation;
7. stakeholder-utility validation;
8. independently adjudicated expert solveability;
9. an interactive shortcut audit.

Separate leaderboard gates require provider-neutral repeated runs and hostile
Linux execution. A complete manifest includes failed and not-run gates;
omission is not allowed. The local manifest commits its association with the
profile and generator fingerprint, but it does not authenticate evidence or
authorize a production freeze. A trusted custodian still has to retrieve and
verify the committed artifacts, sign the result, and have that signature
checked by the freezer.

## Freeze policy

Freeze now:

- the public baseline and current falsification results;
- source snapshots and parser commitments;
- the v3 intended-use statement, estimands, split rules, metrics, and gate IDs;
- small development cohorts used only for engineering and security tests.

Do **not** freeze yet:

- a production scientific episode cohort;
- point intervention effects or utility weights from v2;
- the visible Adams data or viewed NORS years as a supposedly blind holdout.

After all scientific gates pass, freeze the exact candidate profile, source and
runtime fingerprint, posterior draw bank, metric implementation, and private
episode identities without outcome retries. An independent custodian then runs
the one blind empirical evaluation. A failed holdout becomes development data;
it cannot be tuned and reused as the final test.

## Immediate implementation milestone

The current `codex/scientific-v3` milestone is complete only when it provides:

- a reproducible LTC-only NORS observation diagnostic with era and annual
  stratification, plus a custodian-verified source manifest before that
  diagnostic can satisfy a scientific gate;
- a private facility-trace model whose interviews and inspections are derived
  from roles, wards, shifts, meals, entries, and contacts;
- a trusted branching manifest that commits the hidden opening snapshot,
  simulator/image fingerprint, policy definitions, parameter draws, and
  counterfactual random-event protocol before an uncertainty-aware policy
  evaluator is admitted;
- vector-outcome policy analysis with stakeholder sensitivity built only on
  those trusted rollouts;
- fail-closed local scientific-readiness manifests that never claim to
  authorize a production freeze;
- focused and full regression-test results;
- documentation that marks every unrun empirical or human gate as unrun.

This milestone creates the testable scientific foundation. It does not claim
that external validation, private operational-data calibration, or the human
study has already occurred.

## Primary sources and data systems

- [Starsim model structure](https://docs.starsim.org/user_guide/basics_model.html)
- [CDC NORS data and limitations](https://www.cdc.gov/beam/faq/index.html)
- [CDC NORS reporting guidance](https://www.cdc.gov/nors/downloads/guidance.pdf)
- [CDC NoroSTAT surveillance network](https://www.cdc.gov/norovirus/php/reporting/norostat.html)
- [CDC CaliciNet surveillance network](https://www.cdc.gov/norovirus/php/reporting/calicinet.html)
- [CDC National Environmental Assessment Reporting System](https://www.cdc.gov/restaurant-food-safety/php/investigations/nears.html)
- [CMS nursing-home provider and staffing data](https://data.cms.gov/provider-data/topics/nursing-homes)
- [Adams et al. nursing-home outbreak line lists and transmission analysis](https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1007271)
- [CDC norovirus intervention evidence review](https://www.cdc.gov/infection-control/hcp/norovirus-guidelines/evidence-review.html)
- [Talts et al. simulation-based calibration](https://arxiv.org/abs/1804.06788)
