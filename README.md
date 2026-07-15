# EpiAgentBench

[![CI](https://github.com/matthew-zhao/epiagentbench/actions/workflows/ci.yml/badge.svg)](https://github.com/matthew-zhao/epiagentbench/actions/workflows/ci.yml)

EpiAgentBench is a benchmark concept and runnable reference implementation for
testing AI agents on **alert verification and initial outbreak investigation**.

An episode begins with a noisy surveillance alert. The agent must use a limited
budget and simulated time to determine whether the alert represents a true
outbreak, build a defensible line list, investigate competing explanations, and
recommend a proportionate action supported by evidence.

This stage was selected because it combines:

- high public-health impact;
- genuine multi-step investigation and tool use;
- deterministic synthetic ground truth; and
- meaningful opportunities to test reward hacking, privacy, and unsafe action.

The initial scenario pack focuses on foodborne and gastrointestinal events. The
same interface can later support respiratory, healthcare-associated, zoonotic,
and unknown-disease events.

## Implementation status

The repository now contains a working **reference process boundary**. A fresh
evaluator process owns the private seed, scenario family, oracle, unreleased
observations and schedule, action ledger, and scorer. An evaluated agent receives
only a small client that exchanges JSON messages over a connected Unix-domain
socket.

Secure launches also generate a fresh evaluator-private presentation key. Opaque
episode, person, site, report, and observation identifiers are HMAC-derived from
that key rather than from the latent simulator seed, so replaying the same
hidden seed does not reproduce public identifiers. In live Starsim episodes the
same secret also keys independent growth, simulator, and observation streams,
so enumerable development seed numbers cannot be matched to a public trajectory.
The transparent legacy demo uses a deterministic development key only for
reproducibility. A trusted harness may supply and privately retain an
`episode_secret` for exact evaluator replay; it must never place that secret in
the agent container or public trace.

Two capabilities are deliberately separate:

- `SecureEpisodeSession` is evaluator/admin-only. It owns the spawned process
  and the private channel used to score or shut down an episode. Never pass it
  to an agent.
- `epiagentbench_client.InvestigationClient` is the public agent capability. It
  can call the allow-listed investigation operations, but it cannot score an
  episode or retrieve simulator, oracle, seed, family, future-record, or scorer
  state.

The broker accepts JSON only, validates exact request shapes, serializes public
results through explicit field allow-lists, and returns generic rejection
errors. In the container runner, bounded stdout and stderr are streamed back to
the oracle-owning process for canary scanning before scoring; raw stderr is not
returned in the evaluation result. Python object privacy is not treated as the
security boundary.

The repository also includes a Linux/Docker reference runner. It exposes the
public broker as a permission-restricted Unix socket, mounts only that socket
and the agent entry script, and runs the agent non-root with no network, a
read-only root, dropped capabilities, `no-new-privileges`, an ephemeral scratch
tmpfs, and CPU/memory/PID/time/output limits. Each run starts fresh; no container
or VM snapshot is restored. The two Dockerfiles deliberately
separate the client-only agent image from the evaluator/Starsim image.

This is **not yet a production-hermetic benchmark claim**. The `secure-demo`
runs both processes on the same host and from the same source installation. The
Docker runner is Linux-only and was not exercised on this macOS development
host. Digest-pinned execution plans (the artifact format retains the legacy
`snapshot` name) and authenticated run receipts are now implemented, but the
inference proxy, independently attested runtime state, and
full hostile-container red-team suite are not.

## What is here

- [`docs/BENCHMARK_SPEC.md`](docs/BENCHMARK_SPEC.md): benchmark design,
  scenario families, scoring, sandbox boundary, and threat model.
- [`docs/SCIENTIFIC_VALIDATION.md`](docs/SCIENTIFIC_VALIDATION.md): frozen
  seed-panel results, parameter interpretation, and scientific stop-claims.
- [`docs/CALIBRATION_PROTOCOL.md`](docs/CALIBRATION_PROTOCOL.md): exact CDC
  snapshot, leakage-safe temporal splits, gate-free Starsim fitting, private
  cohort commitments, adversarial audits, and hardening gates.
- [`docs/SCIENTIFIC_V3_PROTOCOL.md`](docs/SCIENTIFIC_V3_PROTOCOL.md): the
  LTC-specific intended use, observation/transmission/action evidence contract,
  uncertainty workflow, and non-authoritative local readiness checklist now
  under development.
- [`docs/OPERATIONAL_DATA_REQUEST.md`](docs/OPERATIONAL_DATA_REQUEST.md): the
  privacy-preserving facility and health-department data needed to validate
  alerts, reporting, investigations, and actions that NORS cannot identify.
- [`docs/HUMAN_EVALUATION_PROTOCOL.md`](docs/HUMAN_EVALUATION_PROTOCOL.md): the
  expert solveability, independent adjudication, and construct-validity study
  scaffold; no participant study has yet been run.
- [`src/epiagentbench/nors_ltc_observation.py`](src/epiagentbench/nors_ltc_observation.py):
  a hash-reporting LTC-only adapter for caller-supplied NORS-shaped data. It
  describes reported outbreaks, not hidden infections, and explicitly refuses
  scientific admissibility until a custodian verifies source provenance.
- [`src/epiagentbench/cms_nh_morphology.py`](src/epiagentbench/cms_nh_morphology.py):
  a trusted/offline, development-only CMS facility-margin adapter for beds,
  census, staffing, and turnover. It emits no facility identities, rejects
  public data relabeled as a holdout, and is not yet admissible for simulation
  conditioning or episode generation; ward/contact structure remains
  unidentifiable from this source.
- [`src/epiagentbench/trusted/starsim_ltc_v3.py`](src/epiagentbench/trusted/starsim_ltc_v3.py):
  a trusted-only role/ward/static-contact-topology Starsim foundation with
  explicit placeholder evidence labels and intervention hooks. The engine is
  now available through the secure `starsim-ltc-v3` backend; temporal trace
  contacts are still aggregated to a static graph rather than applied as
  time-varying transmission doses.
- [`src/epiagentbench/trusted/ltc_closed_loop.py`](src/epiagentbench/trusted/ltc_closed_loop.py):
  the evaluator-only active/no-action adapter that turns LTC engine infections
  and simulator-derived symptoms into the existing surveillance interface,
  exposes pseudonymous roles/wards, and routes the three biological controls
  to their matching engine mechanisms. Staff exclusion and environmental
  cleaning hooks remain intentionally unexposed. Its numeric development
  defaults are public placeholders, not secret calibrated production values.
- [`src/epiagentbench/trusted/institution_traces.py`](src/epiagentbench/trusted/institution_traces.py):
  deterministic private development records for rooms, wards, shifts, meals,
  outside entries, contacts, and trace-derived interviews/inspections. It has
  no causal-mode input and is not yet calibrated to operational facility data.
- [`src/epiagentbench/trusted/intervention_evaluation.py`](src/epiagentbench/trusted/intervention_evaluation.py):
  vector outcomes, paired uncertainty draws, stakeholder-weight sensitivity,
  tail harms, regret, negative controls, and dose-response checks.
- [`src/epiagentbench/trusted/branching_manifest.py`](src/epiagentbench/trusted/branching_manifest.py):
  a legacy development-only caller-attested digest contract. It cannot prove
  simulator execution or shared opening states and must not award benchmark
  credit.
- [`src/epiagentbench/trusted/ltc_branching.py`](src/epiagentbench/trusted/ltc_branching.py):
  the trusted counterfactual path. It freezes private inputs, derives opening
  hashes by replaying Starsim, permits only frozen policies, derives outcomes
  internally, authenticates branch receipts with HMAC, and rejects raw or
  incomplete outcome panels.
- [`schemas/`](schemas): public episode and structured-submission schemas.
- [`src/epiagentbench/`](src/epiagentbench): trusted episode generation,
  controller, evaluator service, deterministic scorer, and development baseline.
- [`src/epiagentbench_client/`](src/epiagentbench_client): the small public
  investigator client intended for the untrusted agent side.
- [`docker/`](docker): separate client-only agent and trusted evaluator image
  definitions.
- [`tests/`](tests): unit tests for scoring, provenance, and safety gates.

The original in-process environment remains available as a transparent
development fixture. It is not safe for an untrusted agent because it contains
all episode observations in Python memory.

The scientific-v3 components above are development foundations, not a fitted
or externally validated episode pack. They are intentionally not the production
default. Small files under [`tests/fixtures/`](tests/fixtures/) test parsers;
their [provenance note](tests/fixtures/README.md) says which values are synthetic
and which are a public three-row CMS projection.

## Run the secure reference demo

```bash
PYTHONPATH=src python3 -m epiagentbench.cli secure-demo --seed 7
PYTHONPATH=src python3 -m epiagentbench.cli secure-demo --seed 7 --backend starsim-ltc-v3 --family institution_person_to_person
```

This launches a separate evaluator process, runs the scripted investigator
through the public JSON broker, and sends the final submission through the
separate admin/scoring capability. Its output intentionally contains no
development truth. The second command selects the role-aware long-term-care
development backend and therefore requires the pinned Starsim dependency.

The legacy, inspectable development path and the test suite are:

```bash
PYTHONPATH=src python3 -m epiagentbench.cli demo --seed 7
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Core scores are programmatic; an LLM judge is not used for leaderboard results.

## Run the development-only agent pilot

The repository includes a public stdio MCP bridge and a deliberately
non-hermetic pilot for locally authenticated cloud-agent CLIs. It currently
pins these full-system pairings:

- Codex CLI with `gpt-5.6-sol`;
- Claude Code with `claude-fable-5`; and
- Cursor Agent with its native `glm-5.2-high` alias.

Run one system or replay one private episode across all three:

```bash
PYTHONPATH=src python3 examples/run_cli_pilot.py codex --seed 1000
PYTHONPATH=src python3 examples/run_cli_pilot.py all --seed 1001
```

Each invocation creates a fresh workspace containing only the public client,
task prompt, schema, and MCP configuration. The private Starsim process and
scorer remain behind the episode socket. Paired runs reuse an evaluator-private
episode secret but never expose it to the agent. The runner records requested
and provider-reported model names, rejects a detected model fallback, rejects
Cursor attempts to use anything outside the exact public MCP allowlist, and
submits output to the strict benchmark validator after the CLI exits.

Single local invocations remain integration smokes, not publishable
comparisons. The CLIs still run on the development host and need provider
network access; the current Linux container runner has no network and cannot
host them unchanged. In particular, Claude Code may route life-science requests
from Fable to another Claude model; the pilot treats that as a failed Fable
attribution rather than silently scoring it. See
[`docs/SCIENTIFIC_VALIDATION.md`](docs/SCIENTIFIC_VALIDATION.md) for the dated
smoke results and remaining gates.

### Development-only paired pilot (2026-07-15)

**This is a descriptive full-system integration result, not a leaderboard or
model ranking.** Before execution, we
[precommitted the panel](results/development-pilot-2026-07-15-v3.manifest.json):
five synthetic `starsim-ltc-v3` episodes (one per causal family), all 15
assignments, rotated system order, no retries, and a fixed denominator in which
evaluator-returned invalid submissions, timeouts, and detected fallbacks score
zero. The
[sanitized per-run artifact](results/development-pilot-2026-07-15-v3.results.json)
contains the complete public results (canonical results digest
`sha256:8d3a076d186e678c7a6034017fd7caa57fb69572ebd882c4bc5f92886470d464`).

| Full-system configuration | Model-attribution result | Valid / attempted | Integrity pass | Fixed-denominator mean (/100) | Median (/100) |
|---|---|---:|---:|---:|---:|
| Codex CLI 0.144.3 + requested `gpt-5.6-sol` | Requested only; CLI emitted no model receipt (5/5) | 4/5 | 4/5 | 40.037 | 50.377 |
| Claude Code 2.1.195 + requested `claude-fable-5` | Failed; provider reported Fable plus `claude-opus-4-8` fallback (5/5) | 0/5 | 0/5 | 0.000 | 0.000 |
| Cursor Agent `2026.07.09-a3815c0` + `glm-5.2-high` | Provider reported `GLM 5.2 High` (5/5; not independently signed) | 0/5 | 0/5 | 0.000 | 0.000 |

These are outcomes of the complete CLI/model/tool configurations, not
attributable model scores. In particular, Claude's zero is **not a Fable
score**: the fallback guard rejected all five attempts, which made no episode
calls. Cursor made 29–38 public episode-tool calls per attempt, but all five
final submissions were invalid and two attempts triggered the unauthorized-tool
guard. Codex produced four valid submissions, but its aggregate cannot be
independently attributed to `gpt-5.6-sol`; its fixed-denominator mean
response-utility component was 0.000/25.

The run used execution commit `9d8f2e9`, Python 3.13.7, Starsim 3.5.1, and
locally authenticated provider CLIs on macOS arm64. It was host-networked and
non-hermetic. The episodes are synthetic and not externally calibrated, there
is only one episode per family, and provider-native reasoning and billing
controls are unequal. These data support no uncertainty estimate, winner,
model-quality claim, epidemiological-realism claim, or scientific-readiness
claim. Publication retires this panel from future private evaluation.

Two earlier same-day panels are excluded from this comparison because our
Cursor runner integration did not permit comparable episode execution; their
decisions remain in the
[v1](results/development-pilot-2026-07-15.adjudication.json) and
[v2](results/development-pilot-2026-07-15-v2.adjudication.json) adjudications.

With the evaluator-only Starsim extra installed, the experimental scored slice
and its seed-panel diagnostic are:

```bash
python3 -m pip install -e '.[starsim]'
PYTHONPATH=src python3 -m epiagentbench.cli secure-demo \
  --backend starsim --family institution_person_to_person --seed 7
PYTHONPATH=src python3 -m epiagentbench.cli validate-starsim --seeds 10
PYTHONPATH=src python3 -m epiagentbench.cli validate-closed-loop --seeds 10
PYTHONPATH=src python3 -m epiagentbench.cli validate-live-modes \
  --seeds-per-mode 4
```

The empirical calibration and adversarial-audit entry points are:

```bash
PYTHONPATH=src python3 -m epiagentbench.cli prepare-nors-calibration \
  --csv run_artifacts/nors/nors_20241220T195740Z.csv \
  --metadata run_artifacts/nors/nors_20241220T195740Z.metadata.json \
  --output run_artifacts/nors/calibration_plan.json

PYTHONPATH=src python3 -m epiagentbench.cli calibrate-starsim-nors \
  --plan run_artifacts/nors/calibration_plan.json \
  --output-report run_artifacts/nors/starsim_composite_fit.json \
  --output-profile run_artifacts/nors/gi_surveillance_nors_candidate.json

PYTHONPATH=src python3 -m epiagentbench.cli refine-starsim-nors-clustered \
  --plan run_artifacts/nors/calibration_plan.json \
  --base-profile run_artifacts/nors/gi_surveillance_nors_candidate.json \
  --output-report run_artifacts/nors/starsim_clustered_refinement.json \
  --output-profile run_artifacts/nors/gi_surveillance_clustered_candidate.json

PYTHONPATH=src python3 -m epiagentbench.cli audit-adversarial \
  --output run_artifacts/adversarial_audit.json
```

These commands do not open the sealed 2020–2023 temporal partitions. See the
calibration protocol before freezing or releasing any candidate.

The private-cohort freezer defaults to 100 balanced five-mode identities and
never simulates or filters outcomes. It intentionally requires a pre-existing
owner-only key outside the new cohort directory:

```bash
PYTHONPATH=src python3 -m epiagentbench.cli freeze-private-cohort \
  --cohort-id private-pilot-v1 \
  --output-directory /secure/eab/private-pilot-v1 \
  --authentication-key-file /secure/eab-keys/private-pilot-v1.key
```

Do not run this against a rejected scientific generator merely to obtain a
nominally private split. The current person-to-person candidate has not passed
its visible calibration gate. The optional clustered ward candidate removed
the previous runaway tail and fit 2009–2018 closely, but it also failed the
disjoint 2019 check and is not a packaged default.

On a Linux evaluator with Docker, build the deliberately minimal agent base:

```bash
docker build --file docker/agent.Dockerfile --tag epiagentbench-agent .
```

An agent entry script connects with
`InvestigationClient.from_environment()` and prints exactly one structured JSON
submission. The trusted harness can run it with
`epiagentbench.trusted.sandbox.evaluate_container_agent(...)`. The runner uses
`--pull=never`; build and pin the approved image before evaluation.

The client-only example and Linux runner can then be exercised with:

```bash
PYTHONPATH=src python3 examples/run_container_eval.py --image epiagentbench-agent
```

For frozen cohorts, `epiagentbench.trusted.hardened_runner` provides the stricter
offline entry point. It authenticates exact cohort membership before Docker,
accepts only a digest-pinned committed plan, uses `--network none`, mounts only
the verified public broker socket, and writes an authenticated receipt over the
trace and execution artifacts. Online model access is deliberately disabled
until a real inference proxy can enforce and attest the committed
model/path/tool/storage and token policies. Unit tests exercise hostile boundary
shapes, but no real Linux hostile-image run has yet set
`linux_execution_verified=true`.

## Simulation realism

The four compact reference families remain deterministic development templates.
They are useful for testing the protocol and scorer, but they are **not realistic
or calibrated infectious-disease simulations**.

There is now also an evaluator-only live environment pinned to
`starsim==3.5.1`. The `starsim` backend supports five experimental causal
modes: person-to-person spread in an institution, a shared contaminated source,
repeated introductions from outside settings, background cases that happen to
trigger an alert, and duplicated records that create a reporting-system
pseudo-outbreak.

Starsim supplies the population, disease state, contact-network process, and
extension points. Person-to-person spread uses its contact route. The shared
source and repeated introductions are evaluator-owned Starsim route modules
that schedule exposure opportunities through those extension points; they are
not built-in named Starsim outbreak models. The reporting artifact is correctly
implemented in the observation layer rather than as a biological infection.
The environment:

- runs a generic SIR process at six-hour timesteps over a CRN-safe contact
  network and detaches infection timing and ancestry before observation
  generation;
- derives time-gated encounters, preliminary and ordered tests, structured
  interviews, background GI records, and the alert numerator from that one
  hidden history;
- derives v2 target inspections from latent contact ancestry, shared-source,
  arrival, and report lineage rather than consulting the private causal-mode
  label. This is an engineering remediation, not an independently simulated
  operational-record process, and inspect-all remains an unrun shortcut audit;
- derives final causal gold and relevant intervention routes from frozen
  ancestry, report lineage, and simulator configuration; the mode label is only
  a private generation/debug stratum;
- keeps simulator UIDs, parameters, attempt count, configuration hash, and all
  observation lineage inside the evaluator;
- keeps an agent-controlled world and an untouched, identically seeded
  comparison world alive inside the trusted evaluator;
- exposes `off`, `standard`, and `intensive` levels for infection control,
  shared-source control, entry control, and reporting audit, while keeping
  experimental biological effect sizes private;
- generates later infections and surveillance records from the controlled
  world as the agent advances time, so the agent can strengthen, relax, or stop
  control and then reassess;
- records at least two prospective 24-hour encounter forecasts before their
  outcomes are available, making growth assessment an explicitly scored task;
- anchors line-list and decisive-evidence gold at the public decision point,
  then adds only true follow-up cases and decisive records that were actually
  returned to the agent, so preventing infections cannot shrink the original
  target and legitimate follow-up does not become a false error; and
- scores the realized trajectory using latent infections averted, reporting
  artifacts prevented, and duration-dependent response burden relative to an
  untouched world and predeclared fixed response bundles.

This is an **experimental norovirus-like observation layer over generic SIR**,
not a pathogen-complete norovirus transmission model. Incubation and symptoms currently affect
observations, not infectiousness. Several testing, routine-reporting, recall,
and utility values in
[`gi_surveillance_v2.json`](src/epiagentbench/data/gi_surveillance_v2.json) are
explicit unvalidated design assumptions. A separate gate-free calibration path
now fits a composite candidate to CDC NORS reported-outbreak-size distributions
without using the benchmark's alert admission filter. That can validate one
observable marginal; it does not separately identify biological transmission
and reporting, and the current attack-rate denominator is not comparable to the
source study.

An evaluator-private deterministic ward topology is available for explicit
calibration candidates while the historical random network remains the default.
The first 80-seed clustered refinement preserved three initial infections and
fit the released 2009–2018 size quantiles, but failed the public 2019 gate. A
separate pinned Adams line-list pipeline now checks duration, peak shape,
resident/staff mix, and symptom margins without reducing them to a leaderboard
reward; see [`docs/EXTERNAL_CURVE_VALIDATION.md`](docs/EXTERNAL_CURVE_VALIDATION.md).

Secure Starsim episodes are closed loop: `set_response_control` schedules a
mode-specific operational state change for the next declared six-hour cycle,
`advance_time` advances both private worlds, and only the controlled world
produces later public records. The legacy `set_institution_control` call remains
as an infection-control compatibility path. The agent can request a target
inspection, act, observe later surveillance, and then strengthen, relax, stop,
or switch controls. Public interaction starts on simulator day 8 and lasts five
days; the finalizer follows both worlds to simulator day 21, an accurately
published 13-day post-decision outcome horizon with eight unobserved days after
interaction closes. A separate static branch generator remains for the original
observation-layer diagnostic.

Response credit is tied to the append-only execution trace. Merely recommending
a response earns no intervention reward: every reported action/target pair must
have a matching scheduled control call, and the final handoff must report its
last executed level. Irrelevant controls have no direct effect on another
mechanism: for example, an audit does not prevent infections and source control
does not directly suppress outside introductions.

The five modes expose the same target catalog, tool surface, and public policy
shape. A secret-keyed admission stream balances the minute-zero alert and
distinct public-patient counts inside narrow public bands; hidden infections,
future records, requested evidence, and intervention outcomes are never
admission inputs. `validate-live-modes` reports mode
coverage, common public-surface checks, candidate same-seed count calipers, and
the reward earned by constant or preregistered alert-count-only policies.

The live LTC-oriented pack also exposes a public six-option
`hypothesis_catalog`. Final submissions must allocate probability across every
published option exactly once; unknown, duplicate, missing, mistargeted, or
non-normalized answers fail closed. This catalog is supplied by the scenario
pack rather than hard-coded into the observation or scoring kernel, and its
multiclass score uses the final trace-derived explanation rather than the
private generation stratum.

This new five-mode panel has not yet been frozen or run as a held-out scientific
result. Same-seed groups that happen to meet public count calipers are candidate
comparison groups, **not matched causal twins**. The earlier 30-episode result
documented in `docs/SCIENTIFIC_VALIDATION.md` remains a historical
person-to-person-slice diagnostic; it cannot validate the expanded distribution.
Transmission strata, exposure schedules, effects, costs, artifact weights, and
labels are benchmark design assumptions—not fitted epidemiology.

Install Starsim only in the trusted evaluator environment. Installing it or the
trusted generator in an agent image would defeat the intended capability split.

## What the current tests establish

The automated tests establish reference-code properties such as delayed release
of requested information, defensive copies of the action ledger, safety gates
for canary/audit events and unauthorized actions, and behavior of the scripted
baseline across the four development families. Secure-boundary tests exercise
the public/admin capability split and check that private values do not appear in
public JSON responses.

The dependency-light suite also checks causal-lineage chronology, spontaneous
stream gating, presentation-ID randomization, decisive-evidence reachability,
tool scheduling noninterference, strict nested public payload schemas, stable
per-person observation randomness, prospective forecast commitments, Unicode
wire-size handling, executed-action/report consistency, and simple-policy
shortcut diagnostics. With the optional extra installed, it runs the real
Starsim backend, reversible and idempotent control invariants, live
action-dependent advancement, decision-time investigation anchors plus observed
follow-up scoring, and a full spawned-broker scoring test.

Passing these tests does not prove OS-level containment, absence of every covert
channel, epidemiologic validity, or reward validity. The Docker runner itself is
not executed by the default test suite. Those claims still require Linux runtime
tests, an actual matched-twin construction rather than count calipers, held-out
calibration, expert review, human solveability studies, utility calibration, and
adversarial red-team evaluation.

## Benchmark principle

> Score whether the agent improves the public-health decision using evidence
> available at the time—not whether it reproduces a preferred chain of thought
> or a prescribed sequence of tool calls.
