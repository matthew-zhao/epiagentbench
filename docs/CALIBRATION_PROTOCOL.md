# Calibration, private splits, and hardening protocol

Status: **implemented research pipeline; not yet a claim of scientific realism
or leaderboard-grade isolation**.

This protocol separates four questions that are easy to conflate:

1. Does the simulator reproduce observable properties of real reported
   outbreaks?
2. Can a candidate pass data it was not tuned on?
3. Can shallow or malicious agents exploit the benchmark instead of solving the
   investigation?
4. Can private episodes and evaluator state survive a hostile execution
   boundary?

A pass on one question is not evidence for the others.

## 1. Empirical snapshot and released targets

The primary snapshot is the CDC National Outbreak Reporting System (NORS)
streamlined public extract:

- dataset: <https://data.cdc.gov/Foodborne-Waterborne-and-Related-Diseases/NORS/5xkq-dg7x>
- CDC use and limitation guidance: <https://www.cdc.gov/nors/data/index.html>
- data vintage: 2024-12-20, containing reports through 2023
- rows: 66,713
- CSV SHA-256:
  `b6eb4e70af99371c0f11c97560a99732fa07b95896a81c01828ee954552f7b97`
- metadata SHA-256:
  `fe8b1e6e058134367c38544b0465493be61c26420e70b505b31650afed50ad9b`
- calibration-plan SHA-256:
  `edd95a05e139f470b09dbc7a31225d7a7b6dfa0bd3663217af1269f83b2ac742`

New retrievals fetch Socrata metadata before and after the CSV and reject the
download if the dataset revision or schema changes between requests. This
provides revision consistency; it does not claim the independent HTTP requests
are atomic.

The plan exposes only the development targets needed to fit and select a
candidate:

| Cohort | Partition | Outbreaks | Median illnesses | Middle 50% | Mean |
|---|---|---:|---:|---:|---:|
| Institutional, person-to-person norovirus | 2009–2018 fit | 12,855 | 27 | 15–46 | 36.62 |
| Institutional, person-to-person norovirus | 2019 visible validation | 1,987 | 20 | 11–35 | 27.38 |
| Restaurant, foodborne norovirus | 2009–2018 fit | 1,816 | 8 | 4–16 | 14.94 |
| Restaurant, foodborne norovirus | 2019 visible validation | 212 | 7 | 4–14 | 11.77 |

NORS is a voluntary, dynamic reporting system, not a census of infections.
The public extract contains one row per reported outbreak and does not expose
complete line lists, non-outbreak alerts, transmission trees, or timed
intervention counterfactuals. These targets can constrain the distribution of
reported outbreak sizes; they cannot separately identify transmissibility and
ascertainment.

## 2. Split discipline

The exact snapshot is partitioned before fitting:

- **Fit:** 2009–2018.
- **Visible model selection:** 2019.
- **Pandemic disruption stress:** 2020–2021, committed but not released.
- **Temporal generalization:** 2022–2023, committed but not released to the fit.
- **True blind empirical holdout:** a future NORS vintage containing 2024+
  outbreaks, ingested by an independent evaluator only after the profile, code,
  metrics, thresholds, and private-episode manifest are frozen.

The 2022–2023 partition is deliberately called temporal generalization rather
than a blind holdout. Aggregate values from those years were viewed during
source characterization, even though the automated fit does not consume them.
Calling it blind would overstate the evidence.

If a candidate fails a post-freeze partition, that partition becomes
development data. It cannot be used to tune and then be reused as the final
test.

## 3. Like-for-like simulator measurement

The agent-facing benchmark generator admits alerts only when their opening
public counts are usable. That is appropriate for task construction but invalid
for scientific calibration: filtering on the final outbreak size would make the
simulator appear realistic by construction.

`trusted/calibration_panel.py` therefore uses a separate measurement path:

- predeclare unique seeds;
- run exactly one Starsim world per seed;
- never retry or reject based on latent or reported outcomes;
- follow the whole 21-day simulation plus 14 days for delayed symptom reports;
- pass infections through the same symptom and reporting model used by the
  benchmark;
- compare only simulations with at least two reported illnesses, matching the
  NORS outbreak definition; and
- report the unconditional inclusion fraction separately, without treating it
  as a NORS-identified target.

The fit changes two scalar, evaluator-private composite parameters: a contact
hazard multiplier and a common-source exposure-candidate multiplier. Reporting
probabilities and other observation assumptions remain fixed. The resulting
numbers are distribution-matching parameters conditional on those assumptions,
not estimates of a unique biological reproduction number.

Run the reproducible workflow with:

```bash
PYTHONPATH=src python3 -m epiagentbench.cli fetch-nors-snapshot \
  --output-directory run_artifacts/nors

PYTHONPATH=src python3 -m epiagentbench.cli prepare-nors-calibration \
  --csv run_artifacts/nors/nors_20241220T195740Z.csv \
  --metadata run_artifacts/nors/nors_20241220T195740Z.metadata.json \
  --output run_artifacts/nors/calibration_plan.json

PYTHONPATH=src python3 -m epiagentbench.cli calibrate-starsim-nors \
  --plan run_artifacts/nors/calibration_plan.json \
  --fit-seeds 60 --validation-seeds 80 \
  --output-report run_artifacts/nors/starsim_composite_fit.json \
  --output-profile run_artifacts/nors/gi_surveillance_nors_candidate.json
```

The command fits only on 2009–2018, then performs one disjoint simulator-seed
check against the already-visible 2019 target. It never opens the committed
2020–2023 partitions.

### First composite fit result (2026-07-14)

The first preregistered run used 60 fit seeds and 80 disjoint simulator seeds
for the visible 2019 check. It rejected the candidate:

| Cohort | Selected multiplier | Fit quantiles (q25 / median / q75) | 2019 simulated | 2019 target | Gate |
|---|---:|---:|---:|---:|---:|
| Institutional person-to-person | contact hazard 1.0 | 6 / 25 / 155.75 | 5 / 74.5 / 225 | 11 / 20 / 35 | **fail** |
| Restaurant common-source | exposure count 0.3 | 5 / 7 / 8 | 4.75 / 7 / 9 | 4 / 7 / 14 | pass |

The person-to-person model is over-dispersed: too many small fizzles and too
many very large outbreaks. Its mean absolute log-quantile error was 0.738 on the
fit target and 1.321 on the visible 2019 target, above the frozen 0.35 gate. The
common-source error was 0.350 on fit and 0.205 on 2019.

This failure is not repaired by opening later data or by repeatedly adjusting
the same scalar. The next candidate must address structural heterogeneity—seed
count, facility/contact structure, and the mixture of subcritical and
supercritical growth—using only released development targets. The rejected
profile remains a diagnostic artifact and must not be frozen as scientifically
validated.

A follow-up five-candidate structural screen confirmed an important
reward-hacking failure mode in the calibration itself. Raising time-zero
prevalence to 10–34 seed infections can make the development quantiles look much
better, but all such candidates failed the public 2019 gate and conflict with
the independent Adams nursing-home data, where outbreaks began with only one to
three index cases. Those candidates were rejected rather than promoted. The
next simulator change must preserve plausible seeding and replace the
homogeneous mixing structure with clustered institutional contacts or another
mechanistic finite-susceptible-unit model.

### Clustered-facility refinement result (2026-07-14)

The next preregistered refinement preserved exactly three initial infections
and replaced homogeneous random mixing with a deterministic private ward
network. Eight cells crossed bridge density 0/0.2 and daily contact hazard
0.12/0.14/0.16/0.18; every cell ran once on each of 80 fit seeds. Selection
used only the released 2009–2018 person-to-person target. The selected cell had
40-person wards, degree six, 0.2 cross-ward edges per ward, and hazard 0.18:

| Check | Simulated q25 / median / q75 | Target | Mean log-quantile error | Gate |
|---|---:|---:|---:|---:|
| 2009–2018 fit | 16 / 28 / 47.25 | 15 / 27 / 46 | 0.043 | selection only |
| 2019 P2P, 80 disjoint simulator seeds | 17.75 / 38 / 49.5 | 11 / 20 / 35 | 0.489 | **fail** (maximum 0.35) |
| 2019 common-source sensitivity | 8 / 11 / 15 | 4 / 7 / 14 | 0.405 | descriptive |

Clustering removed the previous 200–300-case runaway tail, but the fitted
distribution did not generalize to the lower 2019 outbreak-size distribution.
The candidate is therefore rejected. The result is in
`run_artifacts/nors/starsim_clustered_refinement.json` (file SHA-256
`275cd41cde9d2550e794e81a8267b0d131b76b18b99ed2198cee9b900b12d22f`;
internal report SHA-256
`1f00ea1a6ac372c52381b3a27781909f6b2989a3c4113f84708566d70b84d6f0`).
No 2020–2023 or future blind target was opened.

The exact run is available as a command rather than an ad hoc notebook:

```bash
PYTHONPATH=src python3 -m epiagentbench.cli refine-starsim-nors-clustered \
  --plan run_artifacts/nors/calibration_plan.json \
  --base-profile run_artifacts/nors/gi_surveillance_nors_candidate.json \
  --fit-start-seed 2000 --fit-seeds 80 \
  --validation-start-seed 12000 --validation-seeds 80 \
  --output-report run_artifacts/nors/starsim_clustered_refinement.json \
  --output-profile run_artifacts/nors/gi_surveillance_clustered_candidate.json
```

Before any sealed temporal release, freeze a candidate that passes the declared
development/model-selection gates. The freeze automatically commits the fitted
profile plus all relevant package source/data, `pyproject.toml`, Python runtime,
and installed scientific dependency identities; it does not accept a
caller-selected calibration file:

```bash
PYTHONPATH=src python3 -m epiagentbench.cli freeze-calibration-candidate \
  --plan run_artifacts/nors/calibration_plan.json \
  --profile run_artifacts/nors/gi_surveillance_nors_candidate.json \
  --output run_artifacts/nors/candidate_freeze.json
```

Either sealed partition requires
`--acknowledge-sealed-partition-release`. Do not release either during parameter
selection.

## 4. External curve-shape reference implemented; candidate check still required

Matching outbreak-size quantiles is necessary but not sufficient. A simulator
can match total cases while producing implausible growth, duration, peaks, or
joint symptom patterns.

The independent visible shape reference is the CC0 line list for 209 cases across six
confirmed South Carolina nursing-home outbreaks published by Adams et al.:
<https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1007271>.
It contains onset day, resident/staff status, symptoms, and outbreak number.
It is useful for duration, peak timing, curve shape, and resident/staff
heterogeneity, but six confirmed outbreaks are too narrow to establish broad
external validity.

The strict downloader/parser and metric contract are implemented in
`external_validation.py`. The pinned 35,374-byte CSV has SHA-256
`498efcf4ab49aaf8eb77d1c2c61ff7cfff0a8ca9c859029b25adf041041d4e8a`;
the generated visible reference report has SHA-256
`9b7e2a56d8a88f6a1d2bd03457fd03e328bcb13a6fcb9dff02b225809517e790`.
It freezes duration, peak timing/concentration, resident/staff mix, and symptom
margins without creating a composite reward or pass gate. See
[`EXTERNAL_CURVE_VALIDATION.md`](EXTERNAL_CURVE_VALIDATION.md). The rejected
clustered candidate was not promoted merely to compare it against this source.

Investigation latency and common-source evidence should be checked separately
against CDC NEARS data. Intervention effects cannot be recovered causally from
the streamlined NORS export and must remain uncertain scenario assumptions
until stronger evidence or expert elicitation is available.

## 5. Adversarial benchmark audits

`adversarial.py` and the trusted controller now include:

- a shallow decision-tree policy trained to maximize evaluator reward from
  development-only opening observations;
- a metadata-only policy over schema and randomized-ID buckets;
- recursive forbidden-key scans and presentation-secret metamorphic tests;
- trusted-side recording of public score/oracle/admin probes, even when the
  agent catches the rejection;
- invalidation for canary leakage in raw, Base64, URL-safe Base64, hexadecimal,
  percent, HTML, Unicode-escape, case-obfuscated, separator-obfuscated, or
  cross-artifact fragmented form; and
- a synthesized scorer-tripwire/canary matrix; and
- live secure-controller probes that attempt public `score`, `shutdown`, and
  `get_oracle` calls, catch the generic denial, continue, and verify that the
  trusted evaluator still invalidates the final score.

Run the full development-to-disjoint-check shortcut audit with (the CLI retains
`heldout` in its option names for compatibility):

```bash
PYTHONPATH=src python3 -m epiagentbench.cli audit-adversarial \
  --training-seeds-per-mode 8 \
  --heldout-seeds-per-mode 8 \
  --output run_artifacts/adversarial_audit.json
```

The regenerated fixed-size run completed on 2026-07-14 with 40 development and 40
disjoint development-check live episodes and no generation failures. It was not
an authenticated private holdout. The fitted constant
policy scored 0.475 normalized response reward, the opening-observation tree
0.475, and the metadata-only tree 0.475 with zero uplift. All remained below the
predeclared 0.800 shortcut threshold, and the encoded-canary/integrity matrix
passed. Real public `score`, `shutdown`, and `get_oracle` probes were rejected,
recorded on the trusted side, and still zeroed the final score after the caller
caught the denial. The report is stored at
`run_artifacts/adversarial_audit.json`.

Current code gives every panel episode a distinct key derived from a fresh,
unpublished panel secret and publishes only that secret's SHA-256 commitment.
Because the secret also keys private trajectories and is deliberately not
persisted, a panel declares its seed range and secret commitment but is not
exactly replayable. The
single development/check pair does not quantify presentation-secret or
repeated-split variance.

This audit is an initial shortcut detector, not a complete red team. The
adaptive policy selects one fixed response from precomputed utility rows; it
does not yet learn arbitrary interactive tool-call or timing exploits. The
metadata scanner must also be extended across dynamic responses, timing, error,
length, and encoded-value channels.

## 6. Frozen private episodes

Private episode packs contain private seeds, presentation secrets, family, and
generator fingerprint. They are owner-only evaluator artifacts. Each pack has a
nonce-hiding commitment and HMAC authentication. A cohort manifest commits to
the exact episode-index-to-pack mapping, and replay fails unless all of the
following match:

- expected generator fingerprint;
- authenticated cohort manifest;
- externally pinned pack-set commitment; and
- exact membership at that episode index.

The public cohort descriptor exposes only the cohort identifier, count,
generator fingerprint, and hiding pack-set commitment. It never exposes a seed,
family, episode secret, or individual episode index.

Once a bundled generator has passed the declared development gates, an operator
can freeze the default balanced 100-episode cohort with an existing owner-only
authentication key stored outside the new cohort directory:

```bash
PYTHONPATH=src python3 -m epiagentbench.cli freeze-private-cohort \
  --cohort-id private-pilot-v1 \
  --output-directory /secure/eab/private-pilot-v1 \
  --authentication-key-file /secure/eab-keys/private-pilot-v1.key \
  --episodes 100
```

The output directory must not already exist. The freezer samples cryptographic
inputs, balances the five modes, and writes `0700`/`0600` artifacts without
constructing Starsim or inspecting outcomes. It currently supports only the
profile bundled into the fingerprinted package; arbitrary external profiles are
rejected until replay can load and authenticate their exact bytes.

The command was **not** run for the current scientific pilot because the
person-to-person candidate failed calibration. Freezing it now would preserve a
known-invalid episode distribution.

For production, the pack-set commitment must be timestamped or signed outside
the evaluation host, and pack contents should use envelope encryption/KMS rather
than relying only on `0600` permissions.

## 7. Hardened execution status

The implemented execution plan (whose artifact format retains the legacy word
`snapshot`) requires a digest-pinned image, read-only root,
non-root UID, dropped capabilities, `no-new-privileges`, private IPC, bounded
resources, and no private pack or trusted source mount. Every run starts a fresh
container with a fresh tmpfs `/state`; there is no snapshot restore or
copy-on-write checkpoint. Offline runs have no network. Authenticated receipts bind
the full canonical plan, episode commitment, trace root, requested and observed
model names, and model-fallback status.

`trusted/hardened_runner.py` now integrates the offline path end to end on a
Linux host: it authenticates a pack and its exact cohort membership before
Docker, recomputes the installed package/project/runtime fingerprint before and
after evaluator startup, creates and verifies an otherwise-empty Unix-socket broker directory,
mounts only that public socket, runs the digest-pinned image with `--network
none`, scores through the retained admin capability, rechecks the socket
boundary, removes the broker, and writes a no-overwrite `0600` HMAC receipt.
The receipt binds the trace plus execution, stdout, stderr, submission, and
scorecard hashes. Online execution fails closed until an independently attested
proxy exists.

The proxy policy contract now requires exact decoded paths and model IDs,
POST-only requests, `store=false`, `background=false`, no hosted tools, and
call/token/byte caps. No proxy implementation is claimed; a contract without an
enforcing, attested process is not a security boundary.

These are machine-checkable plans and cryptographic commitments, not proof that
a Linux kernel enforced them. On this macOS host:

- `linux_execution_verified` remains `false`;
- the inference proxy has not been deployed or attested;
- no hostile-container suite has run against a real Linux Docker daemon; and
- observed model identity is not yet an independently signed provider/proxy
  attestation.

A leaderboard must stay closed until Linux CI verifies mounts, namespace and
egress denial, broker ownership, cleanup, resource attacks, malicious protocol
frames, evaluator-process discovery, proxy request normalization, exact model
allow-lists, hosted-tool denial, `store=false`, token/call caps, and signed
observed-state receipts.
