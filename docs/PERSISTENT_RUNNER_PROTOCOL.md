# Persistent matched-panel runner protocol

Status: V29 is terminal after its passing six-call preflight and fail-closed
production incident. V30 is also terminal. It published a provider-free runtime
receipt, manifest, and sanitized authentication receipt, then its sole
preflight-supervisor `generate` invocation failed closed during owner-scoped
temporary-directory validation before the first runtime write. It created no
runtime directory, config, or plist; invoked no install or start operation;
started no provider or model process; and attempted no preflight profile or
production assignment. Its exact public
[supersession record](../results/development-matched-50x6-v30.superseded.json)
releases no protected schedule, trace, provider data, or score. V31 is terminal
too. Its provider-free bootstrap produced two byte-identical candidates and
zero authentication/provider/model starts, but its only authorized GitButler
runtime-receipt publication attempt failed for unavailable credentials before
remote mutation. No V31 runtime receipt became public and no later V31 phase
began. Its exact two-file closeout must be a direct child of published control
commit `6efe0fa93e9c72946b48c22ab27a7fe6b41c199c` and must exclude all runtime
receipt bytes and local/provisional objects from its tree and ancestry. Safe
incident metadata may identify the unpublished commit only as
non-authoritative. The terminal
[V31 runbook](V31_RUNBOOK.md) is historical evidence only.

V32 also is terminal. It completed its provider-free runtime-receipt ceremony
with zero authentication, provider, or model starts, but its one authorized
receipt-publication attempt failed before remote mutation. Its exact two-file
closeout at `f26d8f7e50748883142f3452ee11daf43595e421` excludes the unpublished
runtime object and bytes. V33 then attempted only a fresh source/docs/tests
control-plane publication. That one attempt failed before remote mutation with
zero runtime, authentication, provider, or model starts. Its unpublished local
control commit `dac82434f2e2a73d511df418755b28003222ab3b` is non-authoritative
and excluded from tree, ancestry, parentage, and successor source. V33's exact
two-file closeout is `47ebbfc799310fc73e60e7cbf90cd37c5f9d6d8d`.

V34 published and independently pinned control commit
`72ca992eed6c0faa5961d4063732a8a1da918301`, then failed provider-free
host-contract validation before runtime-receipt generation after the
root-managed Glean route and Claude managed-settings schema evolved. It made
zero helper, authentication, provider, and model starts and no later V34
artifact or private state was created. Its exact two-file closeout is
`038794aa1bf82440259c62afdabab44c01415978` on
`refs/heads/codex/v34-runtime-publication-terminal-closeout`, under
`epiagentbench.panel_supersession.v27`. The
[V34 runbook](V34_RUNBOOK.md) is terminal historical evidence only.

V35 published its control plane and later stopped during provider-free
runtime-receipt publisher setup. V40 stopped during control-plane authoring;
V46 stopped during provider-free scientific-runtime cache-isolation
validation; and V47 stopped at its control-publication precreation scope gate
after sealing but never committing or publishing two non-reusable local
candidates. Their supersession records use schemas v28 through v31. The exact
two-file V47 closeout is
`31928645baff6182852c9c88a393b6fcaa6be557`, with sole parent
`e8946a10997863412d4a2ec0113b72e066a73550`, tree
`e21dacbbfc859206a15c7dbbbb9feaf214ca78d5`, and ref
`refs/heads/codex/v48-v47-control-plane-publication-terminal-closeout`.
That closeout is the sole public predecessor for V48. The
[V35 runbook](V35_RUNBOOK.md) is terminal historical evidence only.

V48 is the forward control-plane design. Its schemas and exact acknowledgement
are source-owned, while its commit and runtime/manifest/authentication values
remain unbound until their separately authorized create-once ceremonies
publish and independently verify them. The [V48 runbook](V48_RUNBOOK.md) is
authoritative; neither it nor this document authorizes execution or spend.
Published V35 reconciled the reviewed root-managed Glean contract and advanced
the public provider CLI contract to `epiagentbench.provider_cli_contract.v3`.
V48 retains that contract unchanged: HTTPS route `/rest/api/v1`, an exact
17-key Claude managed environment, pinned helpers, and one exact managed
`sonnet` default represented publicly by a redacted policy tag. Explicit
per-invocation model selection and provider-reported model validation remain
authoritative; no raw host, OAuth client identifier, credential, or managed
configuration value is published.

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
8. No V48 key, cohort, credential namespace, schedule, private state, or
   supervisor may exist until a provider-free scientific-runtime receipt has
   been produced twice identically, committed and pushed through GitButler,
   and re-attested from a fresh clean checkout at the receipt commit.
9. The runtime-cache root contains only its three dedicated caches; receipt
   bytes and operator summaries are staged separately. Its complete raw
   topology stays authenticated-private behind an opaque public hash.
10. The canonical key-namespace freeze claim is created once before cohort
    randomness. A pending claim without its authenticated completion is
    terminal and cannot be retried or prepared.
11. Authentication and passed-preflight receipts are bound by repository-
    relative path, exact bytes, semantic hash, and a create-once publishing
    commit. A later clean descendant checkout may move paths without weakening
    the binding; unrelated history, dirty bytes, or rebinding fail closed.
12. Exit code 64 has one meaning: the evaluator CLI reloaded an exact public
    terminal receipt that matches authenticated private state. Every other
    nonzero or ambiguous child exit remains a supervisor terminal ambiguity.
13. Foreground authentication requires a manually opened, operator-owned
    Terminal.app TTY. A Codex PTY, automation, background job, pipe,
    redirection, transcript, or terminal multiplexer cannot own or capture the
    ceremony. The evaluator persists its claim before live execution,
    dependency, repository, credential, or provider checks. A post-claim
    integrity failure is terminal with a finite code and truthful
    never-started provider states; a second ceremony is rejected.
14. Authentication-helper attempts use a closed durable marker grammar.
    Passing requires launch-pending, started, returned, and integer return code
    zero. A launch-pending marker without either started or start-failed is
    terminal ambiguity, never a retry. Terminal helper-start and ambiguous-
    start totals are recomputed from the sealed history, and post-return
    execution, dependency, and credential drift keep distinct finite causes.
15. The provider-free `reconcile-authentication` command may act only on a
    stale `running` ceremony after it acquires the nonblocking host-global
    lock, or return an already-terminal state idempotently. It starts no
    helper or model, never infers success from credential files, and converts
    ambiguity only to the existing non-retryable terminal incident.
16. The pre-private runtime receipt must exercise the actual `-I -S -B`
    runner file through multiprocessing `spawn`, start the trusted broker for
    every public family and fixed public boundary seed twice serially, and
    bind only content-free aggregate evidence. A direct engine-only smoke or
    `-c` import probe is insufficient.
17. Provider-free preflight contract attestation durably records one finite
    attempted operation before each contract group and the last completed
    operation only after return. A validation failure, attestation-checkpoint
    persistence failure, and following-phase checkpoint persistence failure
    remain distinct through the private incident, public terminal candidate,
    terminal-incident attestation, and provider-free outer audit.
18. Before the first V48 preclaim mutation, the same supervised child
    exact-checks the sealed spend receipt, canonical committed authentication
    receipt bytes and repository binding, and authenticated supervisor
    execution binding. The first trace stores that closed prerequisite bundle;
    the claim re-attests it and never creates a replacement binding.
19. A V48 passed preclaim is separately durable before the exactly-once paid
    claim. Claim-write reconciliation accepts only the complete authenticated
    before-state or after-state and never repairs or retries an ambiguous
    transition.
20. Before LaunchAgent generation reads an authentication key, private state,
    or manifest-bound private input, and before it creates the runtime
    directory, it validates the inputs used to construct its closed base
    environment. `PATH` is fixed; `TMPDIR` must resolve to a current-user-owned,
    nonsymlink directory with exact mode `0700` and satisfy the 72-byte UTF-8
    path limit. Rejection exposes only `generation_environment_invalid` and
    performs no private read, runtime write, authentication, provider, or model
    start.
21. V48 publishes its control plane exactly once from a fresh standalone
    GitButler primary clone after safely routing the personal `matthew-zhao`
    credential and proving managed hooks unchanged. A failed or ambiguous
    control publication closes only on
    `refs/heads/codex/v48-control-plane-publication-terminal-closeout` as a
    two-file direct child of `31928645baff6182852c9c88a393b6fcaa6be557` and
    is never retried. After a uniquely pinned control commit, V48 publishes
    runtime, manifest, sanitized authentication, and passing preflight receipts
    as four ordered one-file commits on
    `refs/heads/codex/v48-runtime-preflight`. Every ref/path is absent before
    first use, every write/publication is attempted at most once, and every
    public parent is independently pinned from the fixed origin. An early
    ambiguity closes on
    `refs/heads/codex/v48-runtime-publication-terminal-closeout` from the last
    independently pinned commit—never local or provisional state. That path,
    `refs/heads/codex/v48-preflight-terminal-closeout`,
    `refs/heads/codex/v48-production-results`, and
    `refs/heads/codex/v48-terminal-closeout` are mutually exclusive with each
    other and with the control-publication closeout.

## Durable assignment phases and the current adapter

The evaluator's authenticated private checkpoint distinguishes these provider
assignment phases:

- `clean_boundary`: the preceding assignment is terminal and the next paid
  invocation has not been reserved.
- `reserved_not_launched`: the next assignment is durably reserved, but no
  model-invocation marker exists; non-model readiness may run here.
- `launch_committed`: the evaluator has durably persisted
  `model_invocation.started` in the callback immediately before model-bearing
  provider process creation.
- `provider_returned`: the original model-bearing provider process returned,
  and its process group and output pipes were proven quiescent.
- `result_committed`: the sanitized result and terminal assignment state are
  durable.

A provably unlaunched reservation can be adjudicated as nonchargeable, but its
durable assignment is still consumed and never replayed. A crash at or after
`launch_committed` is conservatively chargeable and also cannot replay that
assignment. Without a provider idempotency key or durable remote job handle,
transparent recovery from an in-flight host failure and strict at-most-once
execution are mutually incompatible. The benchmark chooses at-most-once
execution and fails closed.

V21 introduced the separation of attempt accounting from model-invocation
accounting and its durable, ordered, content-free pre-model phase field. V22
added a finite trusted-evaluator startup substage. V48 retains both boundaries.
The only permitted transitions are `provider_environment_setup`,
`provider_cli_readiness`, `episode_startup`, and `model_spawn_boundary`.
Unknown, duplicate, skipped, out-of-order, or provider-supplied phase values
fail closed. The phase contains no provider output, exception text, command
arguments, environment values, paths, credentials, prompts, observations,
episode identifiers, scores, or traces.

Typed environment setup, CLI-unavailable, disposable-workspace, readiness
setup, CLI readiness timeout, CLI-version nonzero, CLI-version empty identity,
provider MCP readiness, and trusted episode-start failures all occur before
`model_invocation.started`. With
`model_invocation_state = "not_started"` they contribute zero conservatively
chargeable model invocations and are never retried. A failure to durably
persist the next phase or the model-invocation marker prevents spawn. Once the
model marker is durable, an interrupted or ambiguous launch remains
conservatively chargeable. A Codex authentication incident requires either
that durable marker or an explicit Codex credential-state incident; a generic
pre-marker control failure records only its execution incident. Preflight and
production share this boundary.

The V21 receipt localized its terminal failure to `episode_startup`, before
model invocation, but did not expose an internal broker substage. A
provider-free exact-file reproduction showed that multiprocessing `spawn`
inherited the parent’s manually extended isolated `sys.path`, replayed the
runner as `__mp_main__`, and the runner appended the same two paths again. The
strict validator correctly rejected the duplicates. V22 first accepted only
the pristine parent or an exact one-copy inherited ordered tail; V48 retains
that rule. Partial, duplicate, reversed, displaced, or trailing states still
fail closed.

The V20 public receipt keeps its historical generic
`provider_execution` / `provider_adapter_execution_failed` projection. Its
durable model state was `not_started`, proving zero conservatively chargeable
calls, but its exact pre-model subphase is not recoverable and is not
retroactively rewritten. The V18 receipt likewise retains its legacy early
marker and one-call conservative accounting.

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
semantics are preserved. The worker revalidates this binding at load and
immediately before the core can launch the credential-free evaluator child.
Byte changes, same-byte inode replacement, or symlink recreation/retargeting
fail closed. This is drift attestation within the owner-scoped boundary, not a
root-anchored pre-exec verifier: launchd necessarily starts Python before
Python can perform its own validation.

## Pre-private scientific-runtime receipt

V48 retains the provider-free boundary before the private panel exists. One
operator-supplied, absolute, attested isolated interpreter runs every V48 CLI
and supervisor entrypoint with `-I -S -B`. The isolated bootstrap
starts with only the standard library, manually appends the attested
repository `src` and V5 virtual-environment `site-packages` in that order in
the parent, and re-attests the already-present exact ordered tail during
`spawn` replay. It does not execute `site`, `.pth`, `sitecustomize`, or
`usercustomize`. Every
scientific-runtime-loading operator command receives one explicit absolute
runtime-cache directory and installs the six-variable environment internally
before scientific imports; missing or poisoned caller values are not
authoritative, and the exact prior presence and bytes are restored in
`finally`. Scientific runtime and cache work likewise runs under an internally
installed `umask 077`, with the caller's prior mask restored in `finally`.

Preparation begins under `/usr/bin/env -i` and admits exactly eight base
variables: fresh empty current-owner `0700` nonsymlink HOME and TMPDIR
directories outside the repository and cache, `LC_ALL=C.UTF-8`, the
current-account USER/LOGNAME/SHELL values, the UID-derived macOS
`__CF_USER_TEXT_ENCODING`, and a fixed process
`PATH=/usr/bin:/bin:/usr/sbin:/sbin`. The entrypoint checks that closed set
before importing benchmark or scientific code; after it installs the six cache
variables, the library checks the resulting exact 14-key environment before
and after each runtime preflight. Any extra key fails even when its value is
empty.

V48 bounds the UTF-8 `TMPDIR` pathname to 72 bytes so its fixed
28-byte episode-directory/socket suffix remains within the broker's 100-byte
Unix-socket limit. LaunchAgent generation canonicalizes that directory and
requires current ownership and exact mode `0700` before any private read or
runtime write, then seals it into the base environment. It never falls back to
global `/tmp`. Non-inheritable
directory descriptors bind clean `HOME` and `TMPDIR`; descriptor and pathname
identity, owner, exact mode, and emptiness are re-attested between preparation
substages. Only a finite `EINTR` is retried. Missing paths, replacements,
links, permission drift, or nonempty directories fail closed.

Provider executable discovery is independent of that process PATH and never
consults environment `PATH` or `HOME`. A stdlib-only resolver accepts only
`claude`, `codex`, and `cursor-agent`; searches fixed system/Homebrew roles plus
the current account's `.local/bin` role from `pwd`; rejects distinct duplicate
candidates; and returns an absolute entrypoint for later invocation. Public
artifacts expose only executable names, generic discovery roles, entrypoint
kinds, and target content hashes. They never expose the account name, expanded
home directory, or resolved provider path. The LaunchAgent likewise ignores
caller PATH and seals only the fixed system process PATH.
The preparation preflight runs twice at a clean pinned control-plane
commit. Each
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
- launches the real controller and pathname-socket broker for all five public
  causal families at public seeds `0`, `7`, and `2**31 - 2`, twice serially
  (30 trusted evaluator starts), requiring identical public-transcript
  digests and complete socket cleanup;
- binds the clean source and CLI contracts; and
- binds the complete runtime-cache v3 tree: an absolute normalized,
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
`results/development-matched-50x6-v48.runtime.json`; they are never regenerated
for publication. A fresh clean checkout at that second commit re-runs the same
attestation and compares its runtime identity to the tracked receipt before
the matched V48 freezer or `prepare` command can create or read a key, cohort,
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

At every V48 preparation boundary, parsing these values only resolves and
validates the normalized cache root. It does not walk the tree. The complete
cache contract is inventoried exactly once, then the resulting authenticated
object and opaque hash are passed to the bound-public and private-binding
comparisons. A discarded inventory inside environment parsing followed by a
second inventory inside contract validation is forbidden.

The public runtime receipt carries the original control-plane commit, runtime
identity and contract hashes, Starsim smoke contract, a separately hashed
closed broker-startup smoke contract, path-free scientific
module-origin identities, the Python target content hash and entrypoint kind,
the closed path-free provider-free environment contract and its component
hash, and opaque hashes of the complete Python and cache bindings. The later
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
data. The same provider-free recovery can publish a privately sealed terminal
preflight candidate after a public-write failure, but it can never resume an
evaluator. V48 persistent-supervisor contract schema v24 intentionally rejects
public V32 schema v17, burned unpublished V33 schema v18, terminal V34 schema
v19, predecessor V35 schema v20, and non-reusable V40, V46, and V47 schemas
v21, v22, and v23, together with every predecessor-specific panel, cohort,
freeze, and lifecycle namespace. A run must be freshly versioned, prepared,
and authorized under the new contract.

## Typed provider-free preflight control diagnostics

V27 failed closed after its one-shot preflight claim at the provider-free
`contract_attestation` phase. Its immutable public
[preflight receipt](../results/development-matched-50x6-v27.preflight.json) and
[supersession record](../results/development-matched-50x6-v27.superseded.json)
prove zero conservatively chargeable model invocations, zero completed
profiles, and zero production episodes, but its v1 envelope cannot distinguish
which inner contract group failed from a failure to persist the immediately
following control checkpoint. V27 is terminal and non-resumable.

V28 added that distinction but grouped all preparation-runtime validation under
one `preparation_runtime` operation. It later failed at that operation after
`authentication_binding` completed. The terminal projection proves zero
completed profiles, zero conservatively chargeable model invocations, zero
production episodes, and no scores, but it cannot safely identify the failed
inner predicate. V28 is terminal and non-resumable.

V48 retains these exact ordered operations and matching
`_failed` codes:

1. `preparation_runtime_bound_contract`;
2. `preparation_runtime_starsim_smoke`;
3. `preparation_runtime_episode_startup_smoke`;
4. `preparation_runtime_cache_identity`; and
5. `preparation_runtime_private_cache_binding`.

Cache identity is deliberately last among the public checks: the single exact
inventory therefore observes any cache mutation caused by either smoke before
the irreversible paid-run claim.

The authenticated incident envelope persists a finite `attempted_operation`
before each contract group and advances `completed_operation` only after the
previous group returned. An attestation-state write failure uses
`contract_attestation_checkpoint_persist_failed`, while failure to persist the
following phase uses `control_phase_checkpoint_persist_failed`. Remaining
finite groups cover schedule design, the public manifest, authentication
binding, public contract surface, component commitments, cohort
identity/freeze/manifest/preparation/retirement, episode-pack integrity,
cohort balance, schedule commitment, and assignment state, plus one closed
internal fallback.

The same attempted/completed operation and optional contract failure code are
exact-compared across the authenticated private incident envelope
`epiagentbench.preflight_incident_envelope.v3`, sanitized public candidate,
`epiagentbench.terminal_incident_attestation.v2`, and
`epiagentbench.terminal_audit.v3`. No exception text, provider output, prompt,
observation, hidden episode identity or family, credential, private path,
schedule, score, or trace is admitted. These diagnostics classify a terminal
failure; they never authorize a retry or continuation. The no-site outer
worker maintains an independent finite catalog and rejects unknown safe names,
typed control fields on non-control incidents, and failure codes that do not
match their attempted contract operation.

The child reserves exit 64 only after a second read proves the public terminal
receipt is byte-for-byte and semantically identical to its HMAC-authenticated
private candidate. The supervisor records only the weaker fact
`runner_reserved_terminal_exit` with a terminal (not ambiguous) phase. The
outer launch worker then independently re-reads the authenticated private
state and exact canonical public bytes before it records
`benchmark_terminal_receipt`. A bare exit 64, missing or torn receipt, failed
outer re-attestation, pause, or ordinary nonzero remains fail-closed and
nonretryable.

Exit 65 has a deliberately narrower meaning. The child may emit it only when
authenticated private state contains a closed, minimal preflight incident
candidate but the exact public terminal receipt has not been attested. The
supervisor authenticates that finite state; after the Cursor credential is
removed from memory, the outer worker performs provider-free reconciliation,
validates the exact-key `epiagentbench.terminal_audit.v3` projection with zero
authentication, provider, and model starts, and independently repeats the exit
64 receipt attestation. Only that complete chain is normalized to exit 64 and
`benchmark_terminal_receipt`. A bare 65, a spoofed core record, a conflicting
public file, or any failed audit becomes terminal ambiguity and can never
restart the evaluator.

## V48 provider-free preclaim validation

The V48 LaunchAgent starts the one supervised panel child with a sealed
non-secret environment. The outer worker does not read Keychain and does not
inject `CURSOR_API_KEY`. Before the child can persist the irreversible six-call
preflight claim, it executes a provider-free phase using the exact executable,
isolated bootstrap, checkout, working directory, cache environment,
process-spawn method, temporary-directory policy, and authenticated execution
context that will continue into paid work. It starts no authentication helper,
provider, or model process and cannot consume an episode or emit a score.

Before the first preclaim-state mutation, the child exact-checks three
already-sealed prerequisites: the full manifest-bound spend authorization; the
canonical published authentication receipt's exact bytes, semantic hash,
repository-relative path, committed blob, and descendant publishing commit;
and the live preflight supervisor's authenticated label, execution-context
hash, config-file hash, panel ID, and public precommitment. The first durable
`epiagentbench.provider_free_preclaim.v3` trace atomically stores their closed
`epiagentbench.provider_free_preclaim_prerequisites.v1` projection. No later
helper may create or substitute a different supervisor binding.

The provider-free phase executes all five preparation-runtime operations. Its
episode-startup operation performs the complete five-family × three-public-seed
× two-repetition smoke: 30 trusted-evaluator starts, deterministic aggregate
transcript equality, and complete pathname-socket cleanup. That full smoke runs
before the irreversible claim and is not repeated afterward.

Provider secrets are not added merely to make child environments appear equal.
After the five operations pass, the child separately persists and validates the
exact passed trace. It then re-attests the prerequisite bundle and attempts one
exactly-once claim in the same private-state critical section. If the claim
write reports failure, full-state reconciliation accepts only the exact
authenticated pre-claim state or exact authenticated claimed state. It never
patches a partial trace, creates a missing binding, repeats validation, or
repairs an unknown state. A read failure, torn/mixed state, or any other
ambiguity is terminal and non-resumable.

Only after a durably reconciled claim may the credential session operate. It
remains unopened until the first Cursor evaluator call, then invokes the fixed
Keychain reader exactly once with the HMAC-bound locator. The value is cached
only in child memory and placed in `CURSOR_API_KEY` only around Cursor
subprocesses; Starsim/broker, Claude, and Codex execution never receive it. The
outer session `finally` wipes the cached value and environment on every exit.

Preclaim success is authenticated and bound to the exact prerequisite bundle,
manifest, execution context, checkout, source, runtime, environment, and cache
identity. Stale, missing, mismatched, failed, or ambiguous validation prevents
the claim and terminates V48. Because validation and claim are phases of the
same child and critical section, there is no public validate-only receipt,
second child, or claim-time liveness sentinel. Production and successful
post-supervisor finalization both independently require the same exact passed
trace and prerequisite binding.

If a prerequisite fails before the first durable trace, the child preserves
that original failure and performs no speculative seal, publication, or
follow-on state read. The one-shot supervisor remains terminal, and a missing
trace can never be reconstructed or treated as resumable.

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

V48's intentionally no-site outer worker does not re-import Starsim or
re-inventory installed scientific distributions. Those live checks remain
mandatory before and after provider calls. Release instead revalidates the
sealed public component hashes, authenticated preparation/runtime-cache
binding, cohort manifest, and every private pack. Owner-only cache contents may
evolve after execution, but the sealed root and three top-level directory
identities, ownership, modes, nonsymlink policy, filesystem boundary, file
count, and byte limits remain enforced.

Authenticated status schema `epiagentbench.launchd_worker_status.v6` exposes
only one of these coarse release codes; it never includes exception text:

| Code | Coarse gate |
|---|---|
| `release_completion_attestation_invalid` | Supervisor completion |
| `release_runtime_binding_invalid` | Frozen worker/config binding |
| `release_private_state_invalid` | Authenticated private state |
| `release_contract_binding_invalid` | Sealed benchmark contracts |
| `release_candidate_invalid` | Staged success candidate |
| `release_public_watermark_invalid` | Existing public watermark/bytes |
| `release_cohort_retirement_failed` | Terminal cohort retirement |
| `release_private_commit_failed` | Private release commit |
| `release_public_commit_failed` | Final public atomic commit |
| `release_postcommit_attestation_failed` | Postcommit worker/config binding |
| `release_internal` | Unclassified local release gate |

Any such code is terminal and non-retryable. The authenticated worker status is
authoritative; the operator preserves the runtime for an offline audit and
creates a freshly versioned panel rather than retrying the worker or provider.

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
arguments. For V48, the worker starts the one supervised panel child without
reading Keychain or injecting a secret. The child completes its provider-free
preclaim phase, durably seals its passed trace, re-attests its exact
prerequisites, and reconciles the paid-run claim before its credential session
may operate. The session reads the Cursor key exactly once, lazily at the first
Cursor evaluator, and caches it only in child memory. `CURSOR_API_KEY` exists
only around Cursor subprocesses and is absent during Starsim/broker, Claude,
and Codex work. The outer `finally` wipes both cache and environment. The key
is absent from the property list, command line, repository, status, and logs.
LaunchAgent stdout and stderr are `/dev/null`; a bounded private event log
contains only allowlisted event codes and finite scalar fields.

For V48, generation also requires the exact manifest-bound runtime-cache root.
The scientific environment is an exact projection of the six variables in the
recomputed private cache contract whose opaque hash appears in the tracked
runtime receipt. Generation derives and installs those values before
matched-panel imports. Every config-backed control, the launchd worker,
handled-terminal path, and finalizer then derives them from the same
HMAC-authenticated closed config, overwrites missing or conflicting caller
values, and restores the caller's exact prior presence and values in
`finally`. The six values never enter plist or argv. A control keeps one
authenticated config/key snapshot for its entire action; finalization
exact-compares a fresh authenticated read against that snapshot before state
mutation and never validates a replacement config under the first config's
environment. Generation recomputes both full raw bindings, compares their
opaque public hashes, and seals the raw Python/bootstrap and cache records only
in the authenticated owner-only config. At config load and immediately before
the credential-free child launch, the worker revalidates the full
Python entrypoint/bootstrap binding and the closed cache inventory, including
paths, environment, owner, mode, device, inode, UID, and content identities.
No ambient cache, PATH-selected interpreter, startup hook, legacy launchd
config, or nonisolated Python process is accepted.

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

No V48 model call may start until all of the following pass through the
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
- foreground-authentication claim tests proving that pre-provider integrity
  failures are durably terminal, launch no helper, publish no authentication
  receipt, expose only finite status, and reject a second ceremony;
- closed authentication-history tests rejecting synthetic passes, terminal
  reentry, retryable launch ambiguity, contradictory provider markers, and
  tampered helper-start totals, while retaining exact post-return root causes;
- Python-entrypoint byte, inode, and venv-symlink drift tests proving failure
  before credential-free child launch;
- two real provider-free Starsim smoke passes proving the identical
  resident-to-staff transmission and matched contact-stop counterfactual, plus
  receipt-byte, installed-distribution-byte, cache environment/inventory,
  cache inode/mode, and tracked-commit drift tests proving failure before any
  private artifact or provider/authentication helper;
- one injected failure for each V48 preparation-runtime operation, proving the
  exact attempted operation, preceding completed operation, matching finite
  failure code, and zero authentication/provider/model starts;
- an exact call-count assertion proving one cache-identity boundary performs
  one and only one complete cache inventory;
- a real provider-free phase in the generated supervised LaunchAgent child,
  with one non-secret entry environment and bootstrap binding, all five
  preparation substages, and the full 30-start broker smoke before the
  irreversible preflight claim;
- prerequisite-bundle tests proving that exact spend authorization, canonical
  authentication-receipt bytes and committed repository binding, and exact
  supervisor label/context/config/panel/precommitment all pass before the first
  preclaim mutation; every missing, stale, changed, unpublished, or substituted
  value must fail before a credential or provider boundary;
- first-trace tests proving the exact prerequisite bundle is stored atomically,
  then exact-re-attested immediately before claim without creating or repairing
  a supervisor binding;
- negative preclaim tests proving it cannot read Keychain, launch an
  authentication helper or provider, claim preflight, consume an episode,
  project a score, or fall through after a failed or ambiguous substage;
- crash injection around each preclaim checkpoint, the separately durable
  passed trace, and the atomic preflight claim, including failure-before-write,
  exception-after-replace, exact before/after state, torn/mixed state, and read
  failure; no ambiguity may be repaired, authorize execution, or repeat the
  full smoke;
- credential-ordering tests proving the outer worker never reads Keychain, the
  child loader is called zero times before claim and exactly once at the first
  Cursor evaluator, no non-Cursor or broker subprocess receives the key, and
  both the in-memory cache and environment are cleared on every exit;
- production and success-release tests proving that a missing, failed, stale,
  or tampered passed trace or prerequisite bundle blocks both provider work and
  final public artifact mutation;
- public-leakage tests proving the receipt and manifest contain only opaque
  Python/cache binding hashes while the raw cache contract remains in
  authenticated private state and the raw Python binding is sealed only in the
  authenticated LaunchAgent config;
- create-once freeze tests proving the canonical pending claim precedes cohort
  randomness, both CLI phases require it, and pending-without-completion is
  terminal and nonretryable;
- LaunchAgent generation/load tests proving the exact receipt-bound cache
  environment is sealed and that an alternate cache or interpreter is rejected
  before credential-free child launch;
- exact and adversarial `launchctl` state-parser tests proving that
  `not_running` still requires authenticated terminal state, deeper nested
  `state =` fields cannot shadow the job state, and unknown or duplicate
  top-level state lines never reach `bootout`;
- terminal-receipt boundary tests proving that exit 64 requires an exact
  authenticated private/public pair, unexpected nonzero exits remain terminal
  ambiguities, completion-checkpoint write failures use the last durable
  `started` marker, and provider-controlled text cannot select incident codes;
- checkout-handoff tests proving repository-relative authentication and
  preflight receipt bindings survive a clean descendant checkout while
  rejecting unrelated history, dirty or tampered bytes, rebinding, and private
  state moved into the checkout;
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

V16 passed foreground authentication, then stopped during the first Claude
preflight call. Its public receipt conservatively records one chargeable call,
no completed preflight, zero production episodes, and no scores. The original
artifact collapsed a handled evaluator failure into `supervisor_exception`;
the offline audit showed that this label did not prove the supervisor itself
crashed. V16 is non-resumable and no production assignment started.

V17 completed preparation and foreground authentication. Its sole preflight
`start` command omitted the six frozen runtime-cache environment values and
was refused before the durable start marker. No worker, provider process,
preflight profile, or model call started. V17 is terminal and its cohort,
keys, credential/cache namespaces, supervisor, runtime, and Keychain service
cannot be reused.

V18 completed provider-free preparation and foreground authentication, then
stopped during its first Claude preflight profile. Its immutable public receipt
uses the legacy `provider_execution` /
`provider_adapter_execution_failed` projection and records one
`started_not_finished` invocation. An offline control-path audit strongly
indicates that the non-model Claude CLI readiness probe timed out before
the model-bearing process was spawned, but the legacy early marker cannot
prove zero billing. V18 therefore retains one conservatively chargeable call.
No production assignment, result, score, or trace was released. V18 is
terminal, non-resumable, and forbidden for namespace or cohort reuse.

V19 completed provider-free preparation and exact spend authorization, then
failed before foreground authentication crossed its intended integrity
boundary because the cache environment still depended on caller exports. The
corrected device ceremony was cancelled after the at-most-once audit. V19
started no model-bearing call, created no credential or public authentication
receipt, and started no preflight or production work. It is terminal and
forbidden for namespace or cohort reuse.

V21 completed provider-free preparation, cohort freeze, manifest publication,
exact spend authorization, and foreground authentication. Its first Claude
preflight profile then failed during trusted episode startup before the model
boundary. The authenticated receipt records zero conservatively chargeable
model calls, zero production episodes, and no scores. The exact provider-free
reproduction above makes V21 terminal and non-resumable; none of its cohort,
key, credentials, cache, supervisor, or execution namespaces may be reused.

V22 completed provider-free runtime publication, cohort freeze, manifest
publication, and exact spend authorization, then its foreground Codex
device-auth coordinator disappeared with durable `running` state but no
provider return or public authentication receipt. The pinned V22 control
terminalized the ambiguity as `interrupted_authentication_ceremony`. It
recorded zero model calls, zero preflight profiles, zero production
assignments, and no scores or traces; its owner-only orphan staging directory
was removed without reading credential contents. V22 is terminal,
non-resumable, and forbidden for cohort or namespace reuse.

V23 completed all six disposable preflight profiles: two Claude, two Codex,
and two Cursor calls. The evaluator child staged a passing candidate and
exited successfully, but the dependency-free outer worker attempted live
scientific-runtime probes under `-I -S` and failed release validation. It
published no official passing preflight receipt, started no production
assignment, and released no score or trace. V23 is terminal, non-resumable,
and contributes a conservative $10 Claude ceiling.

V24 remained an unused control-plane milestone. V25 then attempted one
provider-free preparation-runtime command under a credential-stripped
environment, but its sanitized PATH omitted the required Cursor CLI search
directory. Static CLI identity discovery failed before the scientific runtime,
both Starsim smokes, receipt construction, any private artifact, any provider
or authentication helper, or any model call. V25 is terminal and adds zero to
the conservative Claude ceiling.

V27 binds explicit runtime-cache input, internal environment installation and
exact restoration, an operator-owned Terminal authentication boundary, a
durable foreground-authentication ceremony claim, provider-free interrupted
ceremony reconciliation,
atomic create-once staging/publication, the finite provider-incident taxonomy,
authenticated terminal-receipt exit, completion-checkpoint recovery,
repository-relative receipt handoff, provider-free prelaunch attestation,
nested launchd-state parser, the finite release-failure taxonomy, sealed
post-completion scientific validation without live re-import, provider-free
tracked-source re-attestation, safe owner-only cache-content evolution, an
owner-control-lock-serialized release transition with read-only premature and
contention refusals, and the existing heartbeat/retry/source contracts under
panel/cohort
`development-matched-50x6-v27`, top-level schema
`development_matched_panel_v27`, the exact $610 acknowledgement, and fresh
V27 paths. Its three-commit provider-free release protocol must prove the exact V5
Python under `-I -S -B`, exact Starsim 3.5.1, actual installed
scientific-distribution bytes, the deterministic resident-to-staff/contact-stop
capability smoke, the static provider/configuration identities, the clean
pinned source tree, the real 30-start broker matrix, and the closed bounded
owner-only runtime-cache v3
inventory. The first commit publishes code; the two identical receipts are
then generated through separate no-clobber destinations and compared at that
commit; the second commit publishes those exact bytes through the same atomic
create-once link boundary. Only after a fresh checkout re-attests the second
commit may preparation create the fresh key and empty credentials, burn and
complete the canonical freeze claim, freeze the cohort, create private state,
and prepare the manifest through another no-clobber boundary. The third commit
publishes only that manifest and becomes the frozen execution control. The same
interpreter and cache contract are
mandatory for matched cohort freeze, prepare, LaunchAgent generation,
preflight, and production. The preparation phase makes no authentication,
provider, or model call and stops before the operator separately supplies the
exact manifest-bound acknowledgement.
The V27 panel's Claude ceiling was $510 (102 calls × $5); the exact
acknowledgement's $610 cumulative ceiling adds the conservative $100 allowance
for prior failed panels, including V18's retained $5 legacy-marker call,
V23's two returned Claude preflight calls ($10), and V26's conservative $10
allowance for an indeterminate preflight call count; V19, V20, V21, V22, and
V25 add zero because none started a Claude model-bearing call. V24 also adds zero:
it remained a control-plane-only milestone and created no runtime,
authentication, provider, or model process.
Neither value is a claim about measured billing.
Codex and Cursor remain unbounded.
Historical completed records and transport voids remain audit evidence only
and are never mixed into the new estimand.

V27 later failed closed during provider-free contract attestation before any
model invocation became conservatively chargeable. Its public preflight
receipt remains immutable audit evidence; its cohort, key, credentials,
runtime, supervisor, and execution namespaces are terminal and forbidden for
reuse. V27 adds zero dollars to the conservative prior-panel allowance.

V20 completed its runtime receipt, private freeze, manifest, spend
authorization, and foreground authentication, then stopped on the first Claude
preflight profile. The sanitized receipt records
`model_invocation_state = "not_started"`, zero conservatively chargeable calls,
zero production episodes, and no scores. V20's generic provider-adapter
projection cannot distinguish CLI-identity readiness from trusted episode
startup, so its supersession preserves that uncertainty. V20 is terminal,
non-resumable, and forbidden for namespace or cohort reuse.

V28 later failed closed at `preparation_runtime` after authentication binding
and before any profile or model invocation. Its terminal record proves zero
completed profiles, zero conservatively chargeable model invocations, zero
production episodes, and no scores. Its acknowledgement, cohort, key, cache,
credentials, state, checkouts, supervisor runtimes, Keychain service, and
outputs are terminal and forbidden for reuse. The
[V28 runbook](V28_RUNBOOK.md) is immutable historical evidence only.

V29 later passed all six preflight profiles and entered production exactly
once. Production failed closed after the 26th chargeable invocation boundary
when live attestation classified a boot-identity mismatch even though the host
had not rebooted. The terminal record is non-resumable, releases no score, and
does not justify inspecting the private schedule or traces. V29's public
runtime, manifest, authentication, preflight, production terminal, and
supersession receipts remain immutable evidence. The exact production terminal
receipt passed pinned provider-free attestation with status
`stopped_supervisor_incident`, 26 terminal assignments, and no scientific
results or scores. The production terminal receipt and supersession record are
published together in one closeout commit, independently verified, and pinned
before the V30 control-plane commit. Every V29 private and execution namespace
is permanently retired.

V30 versioned the panel/cohort as `development-matched-50x6-v30`, the top-level
schema as `development_matched_panel_v30`, and every private/execution
namespace. It used `epiagentbench.preparation_runtime_preflight.v4`,
`epiagentbench.bound_preparation_runtime.v3`,
`epiagentbench.persistent_supervisor_contract.v15`,
`epiagentbench.persistent_supervisor.v4`,
identity authentication domain
`epiagentbench:persistent-supervisor:identity:v3`, protocol token
`persistent-supervisor-v9`,
`epiagentbench.launchd_agent.v16`,
`epiagentbench.provider_free_preclaim.v3`,
`epiagentbench.provider_free_preclaim_prerequisites.v1`,
`epiagentbench.preflight_incident_envelope.v3`, and
`epiagentbench.terminal_audit.v3`. Its exact acknowledgement was supplied and
sealed against its published manifest. The provider-free runtime receipt,
manifest, and sanitized authentication receipt were published, but the sole
preflight-supervisor `generate` invocation rejected its temporary-directory
environment before the first runtime write. It created no runtime directory,
config, or plist, invoked no install or start operation, started no provider or
model process, attempted no preflight profile or production assignment, and
released no result or score. The
[V30 supersession record](../results/development-matched-50x6-v30.superseded.json)
and [V30 runbook](V30_RUNBOOK.md) are terminal historical evidence only.

V31 advanced the panel/cohort to `development-matched-50x6-v31`, the top-level
schema to `development_matched_panel_v31`, and the panel persistent-supervisor
contract to v16. Its provider-free candidates passed and matched, but its one
GitButler runtime-receipt publication attempt failed before remote mutation.
Authentication, provider, and model starts remained zero; no public runtime
receipt, manifest, private cohort, authentication, preflight, supervisor, or
production artifact followed. The only valid closeout ref is
`refs/heads/codex/v31-runtime-publication-terminal-closeout`, with sole parent
`6efe0fa93e9c72946b48c22ab27a7fe6b41c199c` and exact two-file scope
`results/development-matched-50x6-v31.superseded.json` plus
`tests/test_v31_supersession.py`. It must not carry a runtime receipt or any
unpublished V31 object into V32 ancestry.

V32 uses `development-matched-50x6-v32`,
`development_matched_panel_v32`, and fresh panel/cohort-specific namespaces.
Its panel persistent-supervisor contract advances to
`epiagentbench.persistent_supervisor_contract.v17`; supervisor state v4,
identity domain v3, protocol v9, and LaunchAgent config v16 are retained. The
generation entry boundary validates its fixed process path and exact
current-owner `0700` `TMPDIR` before private reads or runtime writes and reports
only `generation_environment_invalid` if it is unsafe. The `$160` conservative
prior-through-V31 allowance plus the unchanged `$510` current-run ceiling gives
the source-owned `$670` cumulative ceiling; this is not authorization. The
[V32 runbook](V32_RUNBOOK.md) is now terminal historical evidence. V32's
provider-free receipt candidates passed and matched, but its one receipt
publication attempt failed before remote mutation. Its public closeout commit
`f26d8f7e50748883142f3452ee11daf43595e421` contains only the V32
supersession record and test and excludes the unpublished receipt object from
its tree and ancestry.

V33 prepared but did not publish a fresh control plane. Its sole GitButler
publication attempt failed before remote mutation, with zero runtime,
authentication, provider, and model starts. Its unpublished local commit
`dac82434f2e2a73d511df418755b28003222ab3b` is non-authoritative and cannot
enter successor source or ancestry. V33 closes on
`refs/heads/codex/v33-control-plane-publication-terminal-closeout` at exact
commit `47ebbfc799310fc73e60e7cbf90cd37c5f9d6d8d`, whose only delta is the V33
supersession record and test.

V35, V40, V46, and V47 all stopped without adding to provider spend. Their
four published supersession JSON/test pairs remain byte-identical. The V47
closeout `31928645baff6182852c9c88a393b6fcaa6be557` contains only the V47
supersession record and test, uses `epiagentbench.panel_supersession.v31`, and
is V48's exact public parent.

V48 uses `development-matched-50x6-v48`,
`development_matched_panel_v48`, fresh panel/cohort-specific namespaces, and
`epiagentbench.persistent_supervisor_contract.v24`. Predecessor-specific
contracts v20, v21, v22, and v23 are rejected and v21–v23 are non-reusable.
The root-managed route, redacted default-model semantics, and public provider
CLI contract `epiagentbench.provider_cli_contract.v3` were reconciled in V35;
V48 retains them unchanged. The exact 17-key managed environment, pinned
helpers, explicit per-invocation model argument, and observed-model checks
remain authoritative. All retained supervisor, identity, LaunchAgent,
preparation, provider-free, authentication, and terminal wire schemas remain
unchanged.

V48 fixes fresh `epiagentbench-cursor-v48` and `eab48-` namespaces and reserves
`epiagentbench.panel_supersession.v32`. Its Starsim smoke projection identity is
`sha256:e91a8e76e32048c3bbc63c02ee2a1279fc53a6af078130a7d3baaa91ac8a3d5f`,
frozen after four independent cache-isolated discoveries and two ordinary
final smokes reproduced the same exact value and safe aggregates. The exact
source-owned acknowledgement SHA-256
is `2521ee29ff8baaef2bdab86477e13ed7a384784aba62a76e27b9edac30bdea0f`.

V35, V40, V46, and V47 add `$0`, so the `$160` conservative prior allowance,
`$510` current-run ceiling, and `$670` cumulative source-owned ceiling remain
unchanged and authorize nothing. The [V48 runbook](V48_RUNBOOK.md) is the
authoritative fresh control-plane procedure.
