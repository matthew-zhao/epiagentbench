# Scientific validation status

Status: **experimental vertical slice; not calibrated, epidemiologically
validated, or leaderboard-ready**.

This document freezes the first end-to-end diagnostic for
`gi_surveillance_v1` and preregisters the first diagnostics for the expanded
`gi_surveillance_v2` environment. It is intentionally a falsifiable status
report, not a realism claim.

## 2026-07-14 calibration and hardening milestone

An exact CDC NORS snapshot and a leakage-aware calibration contract are now
implemented. The 66,713-row public extract is frozen by SHA-256, with 2009–2018
used for fitting, 2019 exposed for model selection, 2020–2021 committed as a
disruption stress period, and 2022–2023 committed as temporal generalization.
The latter is not called a blind holdout because aggregate values were viewed
during source characterization. A true blind empirical test requires a future
NORS vintage containing 2024+ outbreaks after the code and candidate are frozen.

Calibration no longer uses the agent-facing episode admission rule. A separate
evaluator-only panel runs one full Starsim world per predeclared seed, performs
no outcome retries, follows delayed reports beyond the simulator horizon, and
compares simulations with at least two reported illnesses to the same observable
NORS estimand. The unconditional rate at which simulated introductions become
NORS-eligible outbreaks is reported but is not treated as an identified target.

The NORS snapshot supplies the following released development margins:

| Cohort | Fit target, 2009–2018 | Visible check, 2019 |
|---|---:|---:|
| Institutional person-to-person norovirus | median 27, IQR 15–46 (n=12,855) | median 20, IQR 11–35 (n=1,987) |
| Restaurant foodborne norovirus | median 8, IQR 4–16 (n=1,816) | median 7, IQR 4–14 (n=212) |

The fitted contact-hazard and common-source exposure multipliers are explicitly
composite distribution-matching parameters conditional on the fixed reporting
model. They are not uniquely identified biological effects. Daily epidemic
shape, resident/staff heterogeneity, investigation latency, intervention
effects, and no-outbreak alert prevalence require separate evidence.

The repository also now contains adaptive shortcut and metadata-only policies,
forbidden-field and presentation-twin audits, trusted recording of caught
admin/oracle probes, encoded and cross-artifact canary detection, authenticated
exact-set private cohort commitments, digest-pinned fresh-container execution
plans (the format retains the legacy `snapshot` name), and
full-plan-bound run receipts. These are implementation primitives, not a claim
that hostile Linux execution has passed: `linux_execution_verified` remains
false until a real daemon and hostile-container suite attest enforcement.

The first gate-free fit was run with 60 fit seeds and 80 disjoint visible-check
seeds. The restaurant common-source candidate passed its 2019 quantile gate
(simulated q25/median/q75 4.75/7/9 versus 4/7/14). The institutional
person-to-person candidate failed decisively (5/74.5/225 versus 11/20/35;
mean absolute log-quantile error 1.321 against a maximum of 0.35). It produces a
bimodal mixture of small fizzles and enormous outbreaks. No later temporal
partition was opened, and the rejected profile is not frozen as scientifically
validated. The next fit must change the seeding/contact/growth structure rather
than retune the same hazard scalar.

A five-candidate follow-up screen showed that increasing time-zero seeds to
10–34 can superficially improve the fit margin, but every candidate still failed
the 2019 gate and violated the independent one-to-three-index-case constraint
from the Adams nursing-home line lists. This is treated as calibration reward
hacking, not progress. A clustered institutional contact model or another
finite-susceptible-unit structure is required while preserving plausible
introductions.

That clustered structure is now implemented as an optional deterministic
private ward network without changing the packaged default. An eight-cell,
80-seed refinement preserved exactly three initial infections and selected
40-person wards, degree six, rare cross-ward bridges, and daily hazard 0.18.
It fit 2009–2018 closely (16/28/47.25 versus 15/27/46; error 0.043) and removed
the runaway tail, but failed the one-call 2019 check (17.75/38/49.5 versus
11/20/35; error 0.489 against a 0.35 maximum). Its descriptive common-source
2019 error was 0.405. The candidate is rejected, no packaged profile was
promoted, no private cohort was frozen, and no later NORS partition was opened.

The visible Adams external reference is also implemented and pinned: 209 cases
across six outbreaks, source SHA-256
`498efcf4ab49aaf8eb77d1c2c61ff7cfff0a8ca9c859029b25adf041041d4e8a`.
It freezes duration, peak-shape, resident/staff, and symptom metrics but emits
no composite score or gate. It remains a narrow visible falsification source,
not a blind holdout. See `EXTERNAL_CURVE_VALIDATION.md`.

The regenerated adaptive shortcut audit used 40 development and 40 disjoint
development-check live episodes with no generation failures; it was not an
authenticated private holdout. An always-off fitted constant scored
0.475 normalized response reward; a depth-three opening-observation policy
scored 0.475; and a schema/random-ID metadata-only policy scored 0.475 with no
uplift. None crossed the predeclared 0.800 shortcut threshold. Its
encoded-canary/scorer-tripwire matrix passed, but that matrix synthesized
audit-event strings. The same run separately performed real public-capability
`score`, `shutdown`, and `get_oracle` probes and verifies trusted-side score
invalidation. This is evidence against those narrow attacks, not against
arbitrary interactive reward-hacking strategies. Fresh unpublished presentation
secrets make current panels non-replayable unless those secrets are privately
persisted; repeated-split uncertainty is not yet measured.

The first interactive shortcut remediation is now implemented. Inspection
payloads no longer map the private causal-mode label to one favored target or
publish a generic `material_concern` answer. They report noisy counts derived
from the frozen contact, shared-source, arrival, and report-lineage records.
Interviews no longer use the causal-mode label as a fallback when a transmission
event lacks explicit provenance. A matched-trace regression requires inspection
and interview evidence, including its decisive-evidence membership, to remain
identical when only the private mode label changes. The scripted baseline now
forms a patient-level hypothesis before requesting one targeted inspection
instead of inspecting all four catalog targets and selecting the positive one.
The best-fixed intervention comparator likewise derives which biological
control routes exist from the frozen simulator configuration rather than from a
mode-to-action answer table. Final outbreak status, causal explanation, source,
and decisive-evidence gold are now derived from frozen transmission ancestry
and duplicate-report lineage. The private mode label remains a generation and
debug stratum, not scoring truth. An active inspect-all/request-everything agent
has not yet been run on a disjoint panel and remains a required shortcut audit.

This removes a direct lookup of the private causal-mode label; it does not yet
remove the shortcut as a scientific concern. V2 inspection signals are still
constructed from latent transmission ancestry and report lineage rather than
from independently simulated shift, meal, arrival, symptom, and facility-record
processes. An inspect-all policy may therefore still recover the largest
route-aligned signal. V2 also publishes four named controls, one target per control, and
three intensity levels. The first V3 scientific deliverable is therefore an
LTC-specific norovirus scenario pack inside the reusable benchmark system, not
a redefinition of the entire system as one scenario. Later packs can supply
different populations, records, mechanisms, and executable action catalogs
while reusing the broker, scoring, security, and evaluation protocol.

The exact data hashes, commands, stop-claims, and deployment gates are in
[`CALIBRATION_PROTOCOL.md`](CALIBRATION_PROTOCOL.md).

## Implemented causal chain

The original v1 chain covered `institution_person_to_person`. V2 retains that
path and adds common-source exposures, repeated outside introductions,
background alerts, and reporting artifacts:

```text
Starsim contact route plus custom source/introduction routes
    → incubation and symptomatic draws
    → routine institutional reporting or care seeking
    → specimen and assay draws plus background GI
    → initial encounters, labs, interviews, and alert
    → agent requests interviews/inspections and selects named response controls
    → active world advances and creates action-dependent later records
    → agent commits a forward report forecast, reviews the response,
      and may strengthen, relax, stop, or switch control
    → active versus untouched same-seed terminal outcomes
```

All public identifiers and live private RNG streams are separately HMAC-keyed
from a fresh secure-evaluation secret. Simulator parameters,
raw UIDs, lineage, generator attempt count, and counterfactual branches stay on
the evaluator side. Request-only facts are checked against the subject's first
public reveal and tool latency, and decisive records must be obtainable before
the deadline. Incremental observation randomness and public IDs are addressed
per person and mechanism, so a prevented infection cannot reshuffle unrelated
records.

## Frozen 10-seed diagnostic

Run on 2026-07-13 with `starsim==3.5.1`:

```bash
PYTHONPATH=src python3 -m epiagentbench.cli validate-starsim --seeds 10
```

| Metric | Result |
|---|---:|
| Generation success | 10/10 |
| Attempts, median (IQR; range) | 4 (4–7; 2–15) |
| Generation seconds, median (IQR; range) | 1.39 (1.36–2.61; 0.97–3.58) |
| Latent infections, median (IQR; range) | 44 (32.25–56; 16–78) |
| Latent attack rate over the full cohort | 4.4% (3.23%–5.6%; 1.6%–7.8%) |
| Observable true cases, median (IQR; range) | 9.5 (8–11; 7–22) |
| Observable-case panels inside cited NORS outbreak-size IQR | 10% |

The cited person-to-person NORS analysis reports a median outbreak size of 28
and IQR 16–47. The current model underproduces observable cases relative to that
comparison. This is a diagnostic failure to address, not a reason to rejection
sample more aggressively. The source's attack-rate denominator and final-size
reproduction-number estimator are not reproduced by the current cohort model,
so those targets are explicitly marked non-comparable in programmatic output.

## Historical v1 closed-loop shortcut diagnostic

The v1 person-to-person admission bands and simple policies were frozen before
running the untouched holdout on 2026-07-13 with `starsim==3.5.1`:

```bash
PYTHONPATH=src python3 -m epiagentbench.cli validate-closed-loop \
  --start-seed 60 --seeds 30
```

| Metric | Result |
|---|---:|
| Generation and finalization success | 30/30 |
| Hidden growth strata | 11 high, 10 medium, 9 low |
| Independently selected admission bands | 8 high, 14 middle, 8 low |
| Outbreak truth | 19 outbreak, 11 background false alert |
| Best fixed policy: off | 17/30 |
| Best fixed policy: standard | 3/30 |
| Best fixed policy: intensive | 10/30 |
| Best constant-policy mean normalized response | 56.7% |
| Best preregistered alert-count-only response | 62.5% |
| Preregistered simple-policy shortcut threshold | 80% |

For each episode, an evaluator-private stream independently chooses one of three
overlapping public alert-count bands. Candidate retention then reads only the
minute-zero public alert count. It does not inspect hidden infections, future
reports, request-only facts, or whether an intervention succeeds. This admits
background-driven false alerts, makes the optimal fixed response vary, and
breaks the specific opening-count shortcut found during development. Under
response reward normalized from no action to the best fixed policy, neither a
constant policy nor any of four frozen alert-count-only rules crosses the
preregistered 80% shortcut threshold on the untouched holdout.

This does **not** establish epidemiologic realism or eliminate richer public
shortcuts. It is public-covariate balancing, not a matched causal-twin design.
The comparison uses one realized common-random-number outcome per policy and
experimental burden weights; it is not an intervention-effect estimate.

The live task also scores at least two timestamped 24-hour new-encounter
forecasts. Individual future counts stay hidden until the corresponding records
arrive; scoring uses the realized active trajectory and a symmetric log-scale
error. That score is an experimental task-design device, not a validated public-
health forecast metric.

Initial investigation gold is anchored at minute zero so an intervention cannot
improve line-list recall merely by preventing later cases. True follow-up cases
and decisive evidence are added only if their public records were actually
returned to the agent. Intervention reward separately requires executed control
calls and a final report that matches the last executed level for each target.

## Five-mode v2 diagnostic: implemented, not yet a held-out result

The expanded panel can be generated with:

```bash
PYTHONPATH=src python3 -m epiagentbench.cli validate-live-modes \
  --start-seed 0 --seeds-per-mode 4
```

For every seed it attempts all five live modes and reports:

- generation and mode coverage;
- outbreak/non-outbreak truth by mode;
- whether the enabled tools and response catalog have one common public shape;
- which fixed response action or bundle has highest private utility;
- reward earned by each constant single-action policy;
- reward earned by three response policies that read only the opening alert
  count; and
- the fraction of same-seed five-mode candidate groups within predeclared
  alert-count and public-patient-count calipers.

No numerical result is frozen here yet. Running the command on development
seeds is an exploratory diagnostic, not a held-out evaluation. In particular,
same-seed candidates within two public count calipers are **not matched causal
twins**: the construction has not shown exchangeability on the full opening
transcript or on latent nuisance variables. The programmatic report therefore
hard-codes `matched_causal_twins: false`, even if every candidate group happens
to pass the count calipers.

One implementation smoke run on 2026-07-14 used development seeds 0–3 (four
episodes per mode, 20 total). Generation succeeded for 20/20 episodes, all four
same-seed groups met the predeclared alert-count and public-patient-count
calipers, and the public policy/tool surface had one signature. The best fixed
response labels were off (11), infection control (1), source control (3), entry
control (3), and reporting audit (2); neither the constant-response nor the
frozen alert-count-only probes crossed the 80% shortcut threshold. These seeds
were observed during implementation and are therefore **not a holdout**. The
result is recorded only as a reproducible engineering smoke check, not as
scientific validation.

V2 route intensity, exposure timing, control effects, response burdens, and the
utility weight for prevented duplicate records are unvalidated design
assumptions. Reporting artifacts are generated in the surveillance layer and
cannot create biological infections; audits can suppress those records but have
no direct infection effect. Likewise, source and entry controls affect only
their corresponding custom Starsim routes. These invariants are necessary
reward-hacking guardrails, not evidence of epidemiological calibration.

## Development-only external-agent smoke

On 2026-07-14, three locally authenticated agent CLIs were started against the
public MCP boundary. These runs were engineering diagnostics on development
episodes, not a frozen evaluation. No comparative score is reported.

| Full system | Episode | Observed result |
|---|---:|---|
| Codex CLI 0.144.3 + requested `gpt-5.6-sol` | 1001 | Made 49 public tool calls and correctly treated the alert as a reporting artifact, but its final line-list labels did not match the strict enum, so the submission was invalid. The prompt was clarified afterward. Codex JSONL did not provide an observed model receipt. |
| Claude Code 2.1.195 + requested `claude-fable-5` | 1001 | Reported both `claude-fable-5` and `claude-opus-4-8`, made no episode calls, and was rejected by the runner's model-fallback guard. It is not a Fable result. |
| Cursor Agent `2026.07.09-a3815c0` + native `glm-5.2-high` | 1006 | After exact MCP-tool approval was configured, reported `GLM 5.2 High` and made 34 public tool calls. It reached the final drafting step but hit the 420-second development timeout before emitting JSON, so the submission was invalid. |

The pilot now creates a fresh public-only workspace, uses exact per-tool Cursor
permissions without `--force`, localizes Cursor project state, rejects detected
model substitution and non-public Cursor tools, and keeps the simulator and
scorer in the evaluator process. This validates that real agents can reach the
closed-loop interface and that attribution failures are caught. It does not
validate model quality, fairness, hermeticity, or the benchmark distribution.
Provider-backed leaderboard runs still need pinned Linux agent images, an
inference-only egress proxy, independently signed model/tool transcripts,
private cases, repeated runs, and the scientific gates below.

## Parameter interpretation

Direct or derived observation anchors include:

- norovirus incubation median 1.2 days and geometric SD 1.56 from a
  [pooled analysis](https://pmc.ncbi.nlm.nih.gov/articles/PMC3849296/);
- care seeking of 22.0% and stool submission of 4.7% among acute diarrheal
  illness from the modern FoodNet survey described by
  [CDC](https://www.cdc.gov/foodnet/surveys/population.html); and
- background acute diarrheal incidence centered on 0.6 episodes per
  person-year from the [FoodNet population survey analysis](https://pubmed.ncbi.nlm.nih.gov/17291364/).

Several values are only design assumptions: routine institutional reporting,
specimen uptake, interview recall, per-person assay sensitivity/specificity,
low/medium/high transmission strata, intervention strength, implementation
delay, and utility weights. In particular, the cited
[outbreak confirmation study](https://wwwnc.cdc.gov/eid/article/17/8/10-1815_article)
reports multi-specimen outbreak yield; it does **not** estimate the per-person
0.91/0.97 assay sensitivities currently used for tractability.

## What remains before scientific use

1. Replace same-seed count-caliper candidate groups with a defined matched-twin
   estimand covering the full opening transcript and relevant latent nuisance
   variables, then test balance without selecting on future outcomes.
2. Define matching estimands and fit transmission plus observation parameters on
   a calibration split, then run posterior-predictive checks on held-out years or
   settings.
3. Replace design-assumption assay, routine-reporting, recall, and utility values
   with validated sources or predeclared sensitivity analyses.
4. Obtain epidemiologist plausibility review, human solveability results,
   inter-rater agreement, and stakeholder utility calibration.
5. Add active-surveillance and case-targeted controls, calibrate the short-
   horizon forecast metric, and compare policies across more than one stochastic
   realization.
6. Replace the fixed four-target menu with a world-derived facility/entity
   inventory and parameterized operational controls before treating response
   selection as more than a bounded V2 research task.
