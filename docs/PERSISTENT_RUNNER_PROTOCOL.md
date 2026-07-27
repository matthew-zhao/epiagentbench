# Persistent matched-panel runner protocol

Status at control-plane publication: versioned V16 persistent-supervisor
contract schema v5. The source contract, panel/schema identifiers, spend
accounting, path namespace, and [V16 runbook](V16_RUNBOOK.md) are defined. The
runtime receipt, cohort, and manifest are created only by the later runbook
phases; this document does not itself authorize authentication, a provider
process, spend, a supervisor start, or a model call.

## Purpose

The development matched panel takes roughly one day when its 300 assignments
run serially. The process that owns those assignments must not depend on the
lifetime of a Codex task, terminal, PTY, editor, or desktop-app turn. A chat
heartbeat may observe the run, but it must never own, relaunch, reorder, or
repair it.

The local macOS pilot therefore runs as a user `launchd` job. `launchd` owns a
small supervisor under `caffeinate`; the supervisor owns the panel runner and
an authenticated execution lease. Closing the initiating task or app must not
terminate that job.

## Safety invariants

1. The hidden schedule remains serial and frozen before any model-bearing
   call.
2. Exactly one panel runner may own a panel, and exactly one supervisor may
   own a supervisor runtime. The runner's existing host-global panel lock and
   the supervisor's distinct runtime lock are authoritative within their
   scopes; PID metadata is diagnostic only.
3. A paid provider launch is preceded by a durable launch commitment. Once
   that commitment exists, the assignment is never retried unless the
   provider offers a frozen, verified idempotency mechanism.
4. The still-running evaluator may continue with the next assignment only
   when the preceding assignment has a durable terminal record and there is
   no execution or credential incident. The current one-child adapter does
   not translate that rule into permission to relaunch a vanished evaluator.
5. An interrupted Codex call is terminal because its persistent credential
   file may have been refreshed in place.
6. No monitor can mutate panel state or invoke a provider.
7. Provider text, prompts, observations, episode references, family labels,
   schedule data, scores, traces, credentials, OAuth state, environment
   variables, and arbitrary exception text never enter supervisor status or
   logs.
8. No V16 key, cohort, credential namespace, schedule, private state, or
   supervisor may exist until a provider-free scientific-runtime receipt has
   been produced twice identically, committed and pushed through GitButler,
   and re-attested from a fresh clean checkout at the receipt commit.
9. The runtime-cache root contains only its three dedicated caches; receipt
   bytes and operator summaries are staged separately. Its complete raw
   topology stays authenticated-private behind an opaque public hash.
10. The canonical key-namespace freeze claim is created once before cohort
    randomness. A pending claim without its authenticated completion is
    terminal and cannot be retried or prepared.

## Durable assignment phases and the current adapter

The evaluator's authenticated private checkpoint distinguishes these provider
assignment phases:

- `clean_boundary`: the preceding assignment is terminal and the next paid
  invocation has not been reserved.
- `reserved_not_launched`: the next assignment is durably reserved and the
  evaluator can prove that no provider process was started.
- `launch_committed`: the evaluator has durably crossed the at-most-once
  boundary immediately before provider process creation.
- `provider_returned`: the original provider process returned and its process
  group and output pipes were proven quiescent.
- `result_committed`: the sanitized result and terminal assignment state are
  durable.

A crash at `clean_boundary` or a provably unlaunched reservation is eligible
for evaluator-adjudicated recovery. A crash at or after `launch_committed`
cannot replay that assignment. Without a provider idempotency key or durable
remote job handle, transparent recovery from an in-flight host failure and
strict at-most-once execution are mutually incompatible. The benchmark
chooses at-most-once execution and fails closed.

The initial macOS adapter supervises one complete evaluator command, not 300
individual provider commands. Its own `prepared`, `launch_committed`,
`running`, and terminal phases describe that one child command. The evaluator
remains authoritative for every provider assignment and retains its separate
panel lock and authenticated checkpoints. This release fixes task, terminal,
and app detachment; it does not promise automatic restart of a crashed outer
supervisor at the next provider-assignment boundary. Such a crash is terminal
until an explicit audit proves otherwise. A 300-command supervisor soak tests
the generic phase machine, while a separate production-shaped fake panel and
real launchd detachment test exercise the one-command adapter.

The first authenticated live attestation permanently binds the private panel
state to the exact LaunchAgent label, execution-context digest, and sealed
configuration-file digest for that operation. A newly generated runtime cannot
replace it, even at a clean assignment boundary. Any loss of that bound
supervisor after execution begins is a terminal panel incident.

The execution-context digest also binds the exact Python target bytes. The
private authenticated configuration retains the original launch path and a
closed record of each venv-style symlink hop plus the final target's inode,
size, and digest. The original path, rather than a resolved base-interpreter
path, remains in the plist and child command so ordinary virtual-environment
semantics are preserved. The worker revalidates this binding at load, before
Keychain access, and immediately before the core can launch the evaluator.
Byte changes, same-byte inode replacement, or symlink recreation/retargeting
fail closed. This is drift attestation within the owner-scoped boundary, not a
root-anchored pre-exec verifier: launchd necessarily starts Python before
Python can perform its own validation.

## Pre-private scientific-runtime receipt

V16 adds a provider-free boundary before the private panel exists. One exact
absolute interpreter,
`/Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python`, runs every
V16 CLI and supervisor entrypoint with `-I -S -B`. The isolated bootstrap
starts with only the standard library, manually appends the attested
repository `src` and V5 virtual-environment `site-packages` in that order, and
does not execute `site`, `.pth`, `sitecustomize`, or `usercustomize`. The
preparation preflight runs twice at a clean pinned control-plane commit. Each
pass:

- requires exact Starsim 3.5.1;
- hashes the actual installed regular-file bytes for every declared scientific
  distribution, in addition to package metadata;
- computes the complete Python entrypoint and hook-free bootstrap binding,
  including the launch path, symlink chain, target topology, isolated
  `sys.path`, and standard-library module origins;
- executes a hardcoded three-person, four-day LTC scenario twice per policy
  through the real Starsim-backed engine: the no-action branch has one
  deterministic resident-to-staff transmission across the sole direct-care
  edge, while the matched day-one contact stop prevents it;
- binds the clean source and CLI contracts; and
- binds the complete runtime-cache v2 tree: an absolute normalized,
  current-user `0700` root containing only exact current-user `0700`
  `matplotlib`, `numba`, and `xdg` subdirectories; below those children, the
  closed, bounded, content-hashed inventory contains at most 10,000
  descendants total (directories plus regular files), all owner-only,
  nonsymlinked, and on the root filesystem, with single-link regular files
  limited to 512 MiB each and 4 GiB of regular-file content in total.

The fixed resident-to-staff/contact-stop result is a deterministic engine
capability smoke. It is not calibration evidence, a biological effect
estimate, or a benchmark score.

The two closed-schema receipts must be byte-identical. The exact bytes are then
committed and pushed through GitButler as
`results/development-matched-50x6-v16.runtime.json`; they are never regenerated
for publication. A fresh clean checkout at that second commit re-runs the same
attestation and compares its runtime identity to the tracked receipt before
the matched V16 freezer or `prepare` command can create or read a key, cohort,
schedule, or private state.

The operator stages the two receipts and every local verification/command
summary in a separate owner-only directory. Nothing may be staged in the cache
root because its only permitted root entries are `matplotlib`, `numba`, and
`xdg`.

The cache contract fixes exactly:

```text
MPLBACKEND=Agg
MPLCONFIGDIR=<owner-only-cache>/matplotlib
NUMBA_CACHE_DIR=<owner-only-cache>/numba
PYTHONDONTWRITEBYTECODE=1
STARSIM_INSTALL_FONTS=0
XDG_CACHE_HOME=<owner-only-cache>/xdg
```

The public runtime receipt carries the original control-plane commit, runtime
identity and contract hashes, Starsim smoke contract, path-free scientific
module-origin identities, the Python target content hash and entrypoint kind,
and opaque hashes of the complete Python and cache bindings. The later
manifest additionally carries the tracked receipt path and file digest plus
both the original control-plane commit and the receipt-bound verification
commit. Neither artifact contains a raw absolute Python/cache path, Python
symlink/bootstrap/module-origin topology, cache environment, cache inventory,
or device/inode/UID metadata. The raw Python binding is transient during
preflight and later recomputed into the authenticated owner-only LaunchAgent
config. The full raw cache contract is retained in authenticated private panel
state and later in that config.

Cache relinking, replacement, permission drift, path drift, environment drift,
inventory/content drift, Python/bootstrap drift, installed-byte drift, or
smoke-result drift fails closed. These checks are provider-free runtime
attestation; the receipt, matched freezer, and prepare command launch no
provider process, authentication helper, or model call.

Only after the code commit and then the byte-identical receipt commit have been
published and the receipt re-attested may preparation create the fresh key and
empty credential directories. The matched freezer then creates one canonical,
HMAC-authenticated pending claim in the authentication-key namespace before
any cohort randomness and appends a separate completion after the cohort is
durable. Both `freeze` and `prepare` require that exact claim path. A pending
claim without completion is a terminal, nonretryable interrupted freeze.
Preparation may then create private state and the public manifest, publish only
that manifest, and stop before authorization.

## Live-attestation failures and bounded snapshot retry

Live attestation preserves no arbitrary exception text. It emits one finite
safe failure code covering configuration/binding integrity, the durable start
commitment, worker state, authenticated core state, lifecycle, assignment
phase, health, process identity, heartbeat freshness, or an unstable
authenticated status snapshot.

Only `status_snapshot_unstable` is retryable. It means either the worker status
changed during its atomic replacement or the authenticated core status/lease
pair remained torn after its internal read loop. Initial binding and the
read-only supervisor checks before and after a provider call and at final
completion may each make at most three total attestation attempts, with 50 ms
and 100 ms delays and a 250 ms retry deadline, while proving that the
lock-owned attempt or assignment list remains at its last durable count. The
lease copies the exact heartbeat timestamp already persisted in status; it
never resamples the clock between the two authenticated records. The durable
`started` marker and provider process creation occur only after the before-call
check succeeds. Retrying a read-only attestation never retries a provider call.
Semantic state, stale heartbeat, process mismatch, authentication, source,
Python, manifest, config, and create-once binding failures are never retried.

If production stops at a provider boundary, its public watermark includes only
a finite failure stage and, for live-attestation failures, the allowlisted
failure code. Reconciliation can rebuild that trace-free projection from the
authenticated private incident without releasing provider output or benchmark
data. Persistent-supervisor contract schema v5 intentionally rejects schema-v4
manifests; a run must be freshly versioned, prepared, and authorized under the
new contract.

## Two-phase success and public release

The evaluator child cannot publish a successful preflight receipt or completed
benchmark result. On success it first writes an HMAC-private candidate and then
a trace-free public `pending_supervisor_completion` watermark. Scores, traces,
schedule order, and family labels remain private. The child exits successfully
only after that pending state is durable.

The outer supervisor then records its own authenticated `completed` status,
matching lease, and terminal event-chain record. Still inside the one-shot
LaunchAgent worker, a local-only finalizer verifies those records and the exact
create-once runtime binding. Only then may it mark the private release as
complete and atomically replace the public watermark with the final receipt or
result. The public artifact is the final evaluator-side durable write.

If the worker crashes after supervisor completion but before publication, an
explicit `finalize` control may repeat only this local verification and atomic
publication step. It cannot relaunch the worker, evaluator, authentication
bootstrap, or provider. A terminal release-validation incident is never
retryable.

## Supervisor lease and liveness

The private supervisor directory and every file in it are current-user owned,
non-symlinked, non-hardlinked, and mode `0700` or `0600` as appropriate. An
authenticated lease binds:

- panel identifier and public precommitment;
- a random lease epoch;
- boot-session identity;
- supervisor PID and process-birth identity;
- lifecycle state and last heartbeat time;
- a monotonic heartbeat counter.

The supervisor holds its distinct runtime lock for its full lifetime while the
child evaluator holds the panel lock. It updates an authenticated heartbeat
every 10--30 seconds. A sanitized supervisor status reports only its finite
child-command state, heartbeat age, pause state, and incident enum. Existing
evaluator telemetry remains the separate source for aggregate completion,
void, remaining, active-profile, coarse-activity, and credential-quarantine
state. A monitor must authenticate both sources.

Provider-output activity is not a liveness signal. A monitor reports healthy
only when the authenticated heartbeat is fresh, the launchd label and lease
epoch agree, the expected process birth identity is live, and no incident is
present.

## LaunchAgent boundary

The local owner-only LaunchAgent property list contains no secret or provider
command. It invokes only:

```text
/usr/bin/caffeinate -dimsu <python> -I -S -B <supervisor-cli> worker --config <private-config>
```

The owner-only private config contains allowlisted paths and frozen command
arguments. The worker reads the Cursor API key from the named macOS Keychain
service into its child environment in memory. The key is absent from the
property list, command line, repository, status, and logs. LaunchAgent stdout
and stderr are `/dev/null`; a bounded private event log contains only
allowlisted event codes and finite scalar fields.

For V16, generation also requires the exact manifest-bound runtime-cache root.
The LaunchAgent environment is a closed projection of the six variables in
the recomputed private cache contract whose opaque hash appears in the tracked
runtime receipt. Generation recomputes both full raw bindings, compares their
opaque public hashes, and seals the raw Python/bootstrap and cache records only
in the authenticated owner-only config. At config load, before Keychain
access, and immediately before child launch, the worker revalidates the full
Python entrypoint/bootstrap binding and the closed cache inventory, including
paths, environment, owner, mode, device, inode, UID, and content identities.
No ambient cache, PATH-selected interpreter, startup hook, or nonisolated
Python process is accepted.

The job is a one-shot supervised run, not an unconditional `KeepAlive` loop.
After an in-flight crash, an automatic restart must not create another paid
call. Recovery requires the same authenticated state audit as a manual launch.

Read-only status uses `launchctl print` and exposes only the finite states
`running`, `waiting`, `exited`, `not_running`, `not_loaded`, and `unknown`.
Literal `state = not running` maps to loaded-but-inactive `not_running`; it is
never treated as absent `not_loaded`. Missing, duplicate, malformed, or
unrecognized state lines map to `unknown`. Uninstall requires both an exact
inactive state (`waiting`, `exited`, or `not_running`) and authenticated
terminal worker/core state. Active, unknown, query-failure, or unauthenticated
states never reach `bootout`.

## Pause, sleep, network, and shutdown

The source checkout and authoritative private checkpoint have separate
lifecycles. Any next live CLI must run from a current-user durable checkout
outside OS temporary storage. Its one HMAC-authenticated private state lives in
a different, pre-existing current-user `0700` real directory outside both that
checkout and OS temporary storage. The private state binds its canonical path
and parent device/inode, and every authenticated read and atomic write
revalidates that binding plus exact `0600`, current-user, single-link file
metadata. The public manifest commits only the path-free storage policy.
Repository cleanup therefore cannot silently delete the authoritative
checkpoint, and no rollback-capable peer mirror is used.

`pause_after_current` is available to the generic multi-command supervisor and
is honored only between its child commands. The current production-shaped
adapter has one child command for the entire panel, so it does **not** claim a
safe between-provider pause. No live operator may use a stop signal as a
pause; stopping an active child is an interruption and requires incident
audit.

`caffeinate` prevents idle sleep while the job is active. The supervisor also
compares wall and monotonic clocks. An unexpected suspension gap is recorded
as a finite lifecycle event and evaluated at the next safe boundary.

The current adapter delegates network behavior inside a provider call to the
existing evaluator timeout and transport-void rules; it does not add a
pre-launch connectivity oracle. A network failure after the evaluator's
provider launch commitment never permits a retry. A reboot or power loss
during an active call remains terminal. A final artifact is releasable only if
the authenticated supervisor finishes without a suspension or integrity
incident, even if the child happened to write a candidate artifact first.

## Required offline release gate

No V16 model call may start until all of the following pass through the
same supervisor path intended for production:

- a real macOS launchd test where the initiating process exits while the
  production `PersistentSupervisor` core and a fake long-running child remain
  alive and then complete; the production LaunchAgent/Keychain wrapper is
  covered separately with fake Keychain and launchctl boundaries;
- crash injection before and after every durable phase transition, with an
  external fake-call ledger proving at most one invocation per assignment;
- concurrent launch, stale PID, PID reuse, boot change, lock, and lease-tamper
  tests;
- stale provider telemetry with a dead supervisor producing an alert;
- generic pause and suspension-gap tests, plus production-shaped mid-call
  interruption and release-gate tests;
- secret, prompt, episode, schedule, trace, and score canary scans across the
  property list, private event log, public progress, and monitor output;
- a 300-command generic-supervisor soak and a production-shaped fake panel
  that internally checkpoints 300 assignments, durably records one ordinary
  transport void, continues exactly once through every later assignment, and
  exits successfully only with a pending 300-terminal candidate;
- candidate-publication crash tests proving that no passed receipt, score,
  trace, schedule, or family label is released before authenticated supervisor
  completion, plus idempotent post-completion finalization;
- finite-code live-attestation tests proving that only an unstable authenticated
  snapshot can retry at initial, before-provider, after-provider, and final
  read-only boundaries; that every provider is invoked at most once; that
  before-provider exhaustion invokes none; that after-provider or final
  exhaustion invokes no additional provider; and that semantic failures are
  never retried;
- Python-entrypoint byte, inode, and venv-symlink drift tests proving failure
  before Keychain access or child launch;
- two real provider-free Starsim smoke passes proving the identical
  resident-to-staff transmission and matched contact-stop counterfactual, plus
  receipt-byte, installed-distribution-byte, cache environment/inventory,
  cache inode/mode, and tracked-commit drift tests proving failure before any
  private artifact or provider/authentication helper;
- public-leakage tests proving the receipt and manifest contain only opaque
  Python/cache binding hashes while the raw cache contract remains in
  authenticated private state and the raw Python binding is sealed only in the
  authenticated LaunchAgent config;
- create-once freeze tests proving the canonical pending claim precedes cohort
  randomness, both CLI phases require it, and pending-without-completion is
  terminal and nonretryable;
- LaunchAgent generation/load tests proving the exact receipt-bound cache
  environment is sealed and that an alternate cache or interpreter is rejected
  before Keychain access or child launch;
- exact and adversarial `launchctl` state-parser tests proving that
  `not_running` still requires authenticated terminal state and that unknown or
  duplicate state lines never reach `bootout`;
- the existing cohort-retirement, no-partial-release, evaluator-tampering,
  metadata-leakage, and prompt-injection suites.

## Versioning consequence

This file contains historical post-V9/V11 design context. V14 completed its
foreground authentication ceremony and later stopped fail-closed during
preflight after three returned calls when post-harness live attestation
reported `status_snapshot_unstable`. Its trace-free stopped preflight and
supersession bind that terminal outcome. The create-once run is non-resumable,
its cohort cannot be reused, and no V14 production assignment started.

V15 later stopped during provider-free preparation because its selected
`python3` could not import Starsim. It created no cohort claim, private panel
state, public manifest, authorization, authentication, supervisor, provider
call, score, or trace. Its frozen cohort and private namespaces are
non-resumable and forbidden for reuse.

V16 now binds the new heartbeat-pair, retry, diagnostic, source, and operational
contracts under panel/cohort `development-matched-50x6-v16`, top-level schema
`development_matched_panel_v16`, the exact $580 acknowledgement, and fresh V16
paths. Its two-commit provider-free runtime protocol must prove the exact V5
Python under `-I -S -B`, exact Starsim 3.5.1, actual installed
scientific-distribution bytes, the deterministic resident-to-staff/contact-stop
capability smoke, the static provider/configuration identities, the clean
pinned source tree, and the closed bounded owner-only runtime-cache v2
inventory. The first commit publishes code; the two identical receipts are
then generated and compared at that commit; the second commit publishes those
exact receipt bytes. Only after a fresh checkout re-attests the second commit
may preparation create the fresh key and empty credentials, burn and complete
the canonical freeze claim, freeze the cohort, create private state, and
prepare and publish the manifest. The same interpreter and cache contract are
mandatory for matched cohort freeze, prepare, LaunchAgent generation,
preflight, and production. The preparation phase makes no authentication,
provider, or model call and stops before the operator separately supplies the
exact manifest-bound acknowledgement.
The current V16 panel's Claude ceiling is $510 (102 calls × $5); the exact
acknowledgement's $580 cumulative ceiling adds the conservative $70 allowance
for prior failed panels. Neither value is a claim about measured billing.
Codex and Cursor remain unbounded.
Historical completed records and transport voids remain audit evidence only
and are never mixed into the new estimand.
