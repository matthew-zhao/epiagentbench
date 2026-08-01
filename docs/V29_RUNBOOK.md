# EpiAgentBench V29 execution runbook

> [!CAUTION]
> **CONTROL-PLANE DESIGN ONLY — NO V29 AUTHENTICATION, PROVIDER, SPEND,
> PREFLIGHT, PRODUCTION, OR MODEL CALL IS AUTHORIZED.**
>
> This document defines the V29 preparation and execution gates. The control
> plane is being finalized, but no V29 runtime receipt, manifest,
> authentication receipt, supervisor run, provider call, model call, result,
> trace, or score exists yet. Unpublished commits and artifacts remain explicit
> placeholders. Do not substitute guessed values. A later operator decision
> must bind the exact published manifest, exact acknowledgement text, and exact
> acknowledgement hash before authentication.

## Why V29 exists

V28 is terminal and non-resumable. Its preflight started exactly once and
failed closed during provider-free contract attestation at the coarse
`preparation_runtime` operation. The authenticated terminal projection records:

- zero completed or terminal profiles;
- zero conservatively chargeable model invocations;
- zero production episodes consumed; and
- no scores.

V28 must never be restarted, resumed, retried, reconciled into success, or used
as the basis for a new provider call. Its cohort, key, runtime cache, credential
directories, private state, checkouts, supervisor runtimes, Keychain service,
and output paths are permanently retired. The
[V28 runbook](V28_RUNBOOK.md) is immutable historical evidence.

The offline audit found no public receipt, schema, or commit-order mismatch.
It revalidated every publicly checkable preparation binding and found that the
surviving cache still matched its opaque public commitment. V28 nevertheless
combined five materially different checks under one content-free failure code,
so the public record cannot distinguish a live cache-identity failure, either
scientific smoke, or the authenticated private cache binding. V29 fixes that
diagnostic and execution-boundary design; it does not reinterpret V28 as a
passing run.

## V29 safety invariants

1. V29 uses fresh panel, cohort, cache, state, credential, checkout,
   supervisor, Keychain, and output namespaces. No V28 artifact is copied,
   renamed, relinked, or consumed.
2. Preparation remains provider-free. It starts no authentication helper,
   provider process, or model-bearing process.
3. The full scientific and 30-process broker-startup validation runs in the
   exact LaunchAgent child environment before the irreversible preflight claim.
4. The supervised child enters through a provider-free preclaim phase. That
   phase cannot claim the six-call preflight, consume an episode, read a
   provider credential, update provider authentication, or emit a score.
5. Each preparation substage has one finite content-free operation and failure
   code. Exception text and arbitrary strings are never persisted or
   published.
6. A boundary computes the complete cache inventory exactly once. Root and
   environment parsing must not perform a hidden first inventory before the
   bound comparison performs another.
7. The full 30-process startup smoke is not repeated after the irreversible
   claim. The same child durably seals a passed preclaim, re-attests the exact
   prerequisite bundle, and then performs one exactly-once claim transition.
   Claim reconciliation compares the complete authenticated before/after
   states and never repairs an ambiguous write.
8. A failed or ambiguous V29 preclaim phase or preflight is terminal for
   V29. It never authorizes a retry, a second supervisor start, or reuse of the
   frozen cohort.
9. Publication uses GitButler only. Direct `git push` is forbidden.
10. No artifact placeholder in this runbook is evidence that the corresponding
    artifact or authorization exists.

## Frozen names and intentionally unresolved values

The namespace names below are part of the V29 design. Values that depend on
later source publication or preparation remain explicit placeholders.

| Surface | V29 value |
|---|---|
| Panel and cohort | `development-matched-50x6-v29` |
| Top-level schema | `development_matched_panel_v29` |
| Assignments | 50 episodes × 6 profiles = 300 |
| Public runtime receipt | `results/development-matched-50x6-v29.runtime.json` |
| Public manifest | `results/development-matched-50x6-v29.manifest.json` |
| Public authentication receipt | `results/development-matched-50x6-v29.authentication.json` |
| Public preflight receipt | `results/development-matched-50x6-v29.preflight.json` |
| Public production result | `results/development-matched-50x6-v29.json` |
| Control-plane commit | `<V29_CONTROL_COMMIT_40_HEX>` |
| Runtime-receipt commit | `<V29_RUNTIME_RECEIPT_COMMIT_40_HEX>` |
| Manifest commit | `<V29_MANIFEST_COMMIT_40_HEX>` |
| Authentication-receipt commit | `<V29_AUTHENTICATION_RECEIPT_COMMIT_40_HEX>` |
| Runtime receipt schema | `epiagentbench.preparation_runtime_preflight.v4` |
| Bound preparation schema | `epiagentbench.bound_preparation_runtime.v3` |
| Provider-free environment schema | `epiagentbench.provider_free_preparation_environment.v2` |
| Persistent-supervisor contract schema | `epiagentbench.persistent_supervisor_contract.v14` |
| LaunchAgent config schema | `epiagentbench.launchd_agent.v15` |
| Preclaim validation schema | `epiagentbench.provider_free_preclaim.v3` |
| Preclaim prerequisite schema | `epiagentbench.provider_free_preclaim_prerequisites.v1` |
| Preflight incident envelope | `epiagentbench.preflight_incident_envelope.v3` |
| Provider-free terminal audit | `epiagentbench.terminal_audit.v3` |
| Exact acknowledgement text | Source-owned block in section 4 below |
| Exact acknowledgement SHA-256 | `46b3b9477b44a3c6312746bd2632b40a825c30a774f66d1ca3eb4d6f684338cc` |
| Current-run Claude ceiling | `$510` |
| Prior-panel Claude allowance | `$100` |
| Cumulative Claude ceiling | `$610` |
| Cursor Keychain service | `epiagentbench-cursor-v29` |

Do not fill a commit placeholder until its source artifact is finalized,
published, and independently verified. The exact acknowledgement and hash were
derived from the landed source constant, but they are not a manifest-bound
receipt and do not authorize spend. The schema and ceiling values above are
likewise source-owned control-plane constants, not evidence of execution.

## Fresh V29 namespaces

At minimum, V29 uses these distinct roots and destinations:

```text
$HOME/.codex/epiagentbench-50x6-v29-runtime-worktree
$HOME/.codex/epiagentbench-50x6-v29-prepare-worktree
$HOME/.codex/epiagentbench-50x6-v29-execution-worktree
$HOME/.codex/epiagentbench-v29-runtime-cache
$HOME/.codex/epiagentbench-v29-runtime-receipt-staging
$HOME/.codex/epiagentbench-v29-cohort
$HOME/.codex/epiagentbench-v29-secrets/panel-auth.key
$HOME/.codex/epiagentbench-v29-state/development-matched-50x6-v29.private.json
$HOME/.codex/epiagentbench-v29-credentials/claude
$HOME/.codex/epiagentbench-v29-credentials/codex
$HOME/.codex/epiagentbench-v29-supervisors/preflight
$HOME/.codex/epiagentbench-v29-supervisors/production
results/development-matched-50x6-v29.runtime.json
results/development-matched-50x6-v29.manifest.json
results/development-matched-50x6-v29.authentication.json
results/development-matched-50x6-v29.preflight.json
results/development-matched-50x6-v29.json
```

The final implementation may add owner-only staging or claim paths, but none
may alias a V28 or earlier-version path. Before the first V29 private write, the
operator must prove that every V29 private namespace and public destination is
absent and that every V28 namespace remains untouched.

## Finite preparation-runtime substages

V29 replaces the coarse V28 `preparation_runtime` operation with these exact
ordered operations:

| Operation | Content-free failure code | Required check |
|---|---|---|
| `preparation_runtime_bound_contract` | `preparation_runtime_bound_contract_failed` | Closed public preparation contract, receipt-file binding, schemas, component hashes, runtime identity, source/CLI/runtime commitments, and provider-free environment contract |
| `preparation_runtime_starsim_smoke` | `preparation_runtime_starsim_smoke_failed` | Deterministic fixed Starsim transmission and matched intervention result |
| `preparation_runtime_episode_startup_smoke` | `preparation_runtime_episode_startup_smoke_failed` | Real file-entrypoint/controller/broker startup over five public families, three public seeds, and two serial repetitions: 30 starts with identical aggregate transcript digest and complete socket cleanup |
| `preparation_runtime_cache_identity` | `preparation_runtime_cache_identity_failed` | Exact six-variable cache environment and one complete safety/content inventory, performed after both smokes, compared with the bound opaque hash |
| `preparation_runtime_private_cache_binding` | `preparation_runtime_private_cache_binding_failed` | Authenticated private raw cache contract hashes exactly to the public opaque cache commitment |

Before each operation begins, authenticated control state persists it as
`attempted_operation`. `completed_operation` advances only after the preceding
operation returned successfully. A validation exception maps only to the
matching finite failure code. A failure to persist the attempted-operation
checkpoint remains a distinct checkpoint-persistence incident and cannot be
reported as failed validation.

The private incident, sanitized public terminal candidate, terminal audit, and
outer attestation must exact-compare these values against independent finite
catalogs. None may contain exception text, raw paths, cache inventory, provider
output, prompts, observations, credentials, OAuth state, hidden episode data,
schedule data, traces, or scores.

## One cache inventory per boundary

`preparation_runtime_cache_identity` runs after both scientific smokes so its
single inventory seals the cache state that will cross the paid-run claim. It
follows one explicit data flow:

1. Parse and validate the six cache environment values without walking the
   cache tree.
2. Resolve the one normalized V29 cache root from those values.
3. Inventory the complete cache tree once.
4. Validate ownership, mode, symlink, filesystem, link-count, file-count,
   byte-count, and content constraints while constructing that inventory.
5. Compute its opaque commitment once and compare it with the public bound
   commitment.
6. Pass the already validated contract to the private-binding comparison.

No helper called by steps 1 or 2 may perform a discarded inventory. No later
substage may silently recompute the full inventory during the same boundary.
If a second observation is scientifically necessary, it must be a separately
named and separately typed boundary, not an implementation detail hidden under
the first operation.

This is a per-boundary invariant. Earlier outer LaunchAgent configuration and
safety re-attestations are separate authenticated boundaries; they do not
replace, suppress, or count as the one authoritative post-smoke inventory in
the provider-free preclaim.

## Provider-free preclaim phase in the supervised child

After the exact authentication receipt is published, the generated V29
LaunchAgent starts the one supervised panel child with its sealed non-secret
environment. The outer worker neither retrieves the Cursor Keychain value nor
injects `CURSOR_API_KEY`. Before the same child can claim the one-shot six-call
preflight, it performs the provider-free preclaim phase.

Before the first preclaim-state mutation, that child must read and exact-check
all three prerequisites without invoking an authentication helper, Keychain,
provider, or model:

- the manifest-bound, HMAC-authenticated spend receipt, including the exact
  acknowledgement text, acknowledgement hash, `$510` current-run ceiling,
  `$100` prior-panel allowance, and `$610` cumulative ceiling;
- the canonical published authentication receipt: its exact canonical bytes,
  semantic receipt hash, repository-relative path, committed blob, and
  descendant publishing-commit relationship; and
- the already-running preflight supervisor's exact authenticated label,
  execution-context hash, config-file hash, panel ID, and public
  precommitment.

The first durable preclaim trace stores the closed
`epiagentbench.provider_free_preclaim_prerequisites.v1` bundle. Every later
prerequisite check must exact-compare against that first bundle; no post-claim
helper may create or substitute a different supervisor binding.

Because validation and paid work are phases of one child, they necessarily use
the same values for:

- executable and isolated bootstrap flags;
- repository root and working directory;
- source and installed-runtime bindings;
- non-secret environment, including the six cache variables;
- process spawning method and inherited import tail;
- temporary-directory and socket policies; and
- authenticated manifest, private-state, and execution-context bindings.

No provider credential is present merely to make environments appear equal.
After the claim is durably reconciled, the child still does not read Keychain
until its first Cursor evaluator call. At that boundary it invokes the fixed
reader exactly once using the HMAC-bound non-secret account and service
locator. The value is cached only in that child process's memory. It is placed
in `CURSOR_API_KEY` only around each Cursor subprocess, remains absent during
Starsim/broker work and Claude or Codex calls, and is wiped from the session
and environment in the outer `finally` path on success, failure, or interrupt.

The provider-free phase executes all five ordered preparation substages. In
particular, it performs the full 30-start episode-startup smoke here, before the
irreversible preflight claim. It then durably writes a separately validated
`passed` trace bound to the exact prerequisite bundle, execution context,
manifest, checkout, source, runtime, environment, and cache commitment. A
different checkout, environment, config, cache identity, private-state
commitment, spend receipt, authentication receipt, or supervisor invalidates
that success.

The provider-free phase must prove all of the following:

- provider, authentication-helper, Keychain, and model process counts are zero;
- no provider credential was retrieved or introduced into the child;
- the preflight claim remains unclaimed;
- no profile or production episode was consumed;
- no score, trace, hidden identifier, family, or schedule was released; and
- failure is terminal for V29 and cannot fall through to the paid preflight.

A prerequisite failure before the first durable trace is propagated without a
speculative private seal or public receipt. The already-started one-shot
supervisor still makes V29 terminal; the absence of a trace is not permission
to retry or reconstruct one.

There is no public validate-only receipt, separate validation child, or
claim-time liveness sentinel. The same child and private-state critical section
first persist the finite passed trace, then exact-re-attest the prerequisite
bundle, then attempt the one-shot claim. If a claim checkpoint reports failure,
the child reloads the complete authenticated state and accepts only one of the
predeclared exact before/after states. It never patches a partial trace,
reconstructs a missing claim, or reruns validation. Any missing, mismatched,
stale, torn, or otherwise unrecognized state is a terminal no-repair ambiguity
and can never authorize a retry.

Production and post-supervisor success finalization independently require the
same exact passed preclaim trace and prerequisite binding. A missing, failed,
stale, or tampered trace cannot start production and cannot publish a passed
preflight receipt or completed result.

## Provider-free preparation sequence

Every phase below is conditional on the corresponding source support and tests
already being present. Placeholder values are not shell variables and must not
be pasted into commands.

### 1. Publish and pin the V29 control plane

The control-plane commit contains source, tests, and documentation only. It
must contain no V29 runtime receipt, manifest, authentication receipt, private
state, cohort, credentials, supervisor state, or benchmark result.

Publish through GitButler and record the exact remote commit as
`<V29_CONTROL_COMMIT_40_HEX>`. Independently verify a clean checkout at that
commit before continuing.

### 2. Produce the runtime receipt twice

Using the exact pinned scientific Python under isolated flags and a closed
provider-free environment, run the V29 runtime-preparation command twice from
the control-plane commit. Each pass must execute the fixed Starsim smoke, the
full 30-start episode-startup smoke, and one cache inventory. The two canonical
receipts must be byte-identical.

Both passes must prove zero authentication, provider, and model processes and
must leave the source checkout unchanged. Store staging receipts outside the
cache root. Do not create a key, cohort, credential namespace, private state,
or manifest yet.

The clean `TMPDIR` pathname is part of the scientific contract: its UTF-8
encoding is at most 72 bytes, leaving the fixed 28-byte episode-directory and
socket suffix inside the broker's 100-byte Unix-socket limit. The runner never
falls back to global `/tmp` or truncates a validated path. LaunchAgent
generation first resolves the directory to its canonical path and requires
current ownership and exact mode `0700` before sealing it. The child holds
non-inheritable directory descriptors for clean `HOME` and `TMPDIR` and
re-attests descriptor/path identity, ownership, mode, and emptiness between
every preparation substage. Filesystem attestation retries only a finite
`EINTR`; missing, replaced, linked, nonempty, or otherwise unsafe directories
fail closed.

Publish only the exact byte-identical receipt through GitButler, then record
the remote commit as `<V29_RUNTIME_RECEIPT_COMMIT_40_HEX>`.

### 3. Re-attest and prepare once

Materialize a second clean checkout at the exact runtime-receipt commit.
Re-attest the tracked receipt and all five preparation substages before any
private write. A mismatch ends V29 preparation; do not repair the cache and
rerun.

Only after the re-attestation passes may the matched V29 command create the
fresh authentication key, burn the create-once cohort-freeze claim, freeze the
fresh V29 cohort, and prepare the private state and public manifest exactly
once.

Validate and publish only the resulting public manifest through GitButler.
Record the exact remote commit as `<V29_MANIFEST_COMMIT_40_HEX>`. Stop here.

### 4. Separate spend authorization and authentication

No authorization is implied by sections 1–3. A later operator decision must
bind one exact manifest-bound receipt containing this source-owned V29
acknowledgement:

> I acknowledge the replacement six-call v29 preflight and 300-assignment production run, including unbounded Codex/Cursor provider spend and up to $610 total Claude spend across the failed v2 preflight, failed v5 preflight, failed v6 authentication bootstrap, failed v7 preflight, failed v8 production run, v9 preflight and failed production run, the abandoned zero-model-call v10 precommitment, the failed zero-model-call v11 authentication bootstrap, the abandoned zero-model-call v12 precommitment, the abandoned zero-model-call v13 precommitment, the failed v14 preflight, the failed zero-model-call v15 pre-claim preparation, the failed v16 preflight, the failed zero-model-call v17 pre-start runtime-cache-environment refusal, the failed v18 preflight, the failed zero-model-call v19 authentication setup, the failed zero-model-call v20 preflight, the failed zero-model-call v21 preflight, the failed zero-model-call v22 interrupted authentication ceremony, the failed v23 six-call preflight release validation, the abandoned zero-model-call v24 control-plane precommitment, the failed zero-model-call v25 provider-free preparation-runtime CLI discovery, the failed v26 preflight with indeterminate provider-call count and a conservative $10 Claude allowance, the failed zero-model-call v27 preflight, the failed zero-model-call v28 preflight, and the v29 preflight and production run.

Its SHA-256 is
`46b3b9477b44a3c6312746bd2632b40a825c30a774f66d1ca3eb4d6f684338cc`.
The budget decomposition is fixed at `$510` for V29, `$100` for the
conservatively accounted prior panels, and `$610` cumulative. The text and hash
alone do not authorize spend: they must later be sealed against the exact
published V29 manifest and public precommitment by an explicit operator
acknowledgement.

Only after exact acknowledgement validation may the foreground, zero-model
authentication ceremony run. Publish its sanitized receipt through GitButler
and record `<V29_AUTHENTICATION_RECEIPT_COMMIT_40_HEX>`. Authentication success
does not itself authorize a supervisor start.

### 5. Generate and start preflight once

A fresh clean execution checkout must be at the exact authentication-receipt
commit. Runtime generation binds the V29 cache, manifest, private state,
credentials, source, Python, and execution context.

On the one authorized start, the LaunchAgent sequence is:

1. authenticate its config and frozen source bindings;
2. start the supervised panel child in the exact non-secret environment;
3. before the first preclaim mutation, exact-check the sealed spend receipt,
   canonical published authentication receipt bytes/repository binding, and
   authenticated preflight-supervisor execution binding;
4. atomically persist the first trace together with that exact prerequisite
   bundle;
5. execute and checkpoint, in order, the bound contract, Starsim smoke,
   30-process startup smoke, one post-smoke cache inventory, and private cache
   binding;
6. persist and independently validate the exact passed trace;
7. exact-re-attest the prerequisite bundle and perform the exactly-once claim,
   reconciling only complete authenticated before/after states and never
   repairing ambiguity;
8. execute the six serial unscored profile calls; on the first Cursor call
   only, read Keychain exactly once, cache the value only in child memory, and
   expose it in the environment only around Cursor subprocesses; and
9. wipe the cached value and `CURSOR_API_KEY` in the outer `finally` path.

Never call `start` twice. A failure through step 7 occurs before a provider
call; it still terminates V29 and requires a fresh later version. A failure
afterward is classified from the durable invocation ledger and never permits
another supervisor start or provider retry.

## Required fault-injection and integration evidence

Before V29 preparation, the published control-plane test suite must include:

- one injected failure for each of the five preparation operations, asserting
  the exact attempted operation, prior completed operation, matching failure
  code, and zero provider/authentication/model starts;
- checkpoint-write injection before and after each substage, proving a write
  failure never masquerades as validation failure;
- cache-environment, cache-root, cache-content, inode, mode, symlink,
  ownership, file-count, byte-count, and private-binding faults;
- an assertion that one cache-identity boundary invokes the complete inventory
  builder exactly once;
- Starsim result and reviewed-digest drift faults;
- broker spawn, controller startup, transcript mismatch, socket-collision, and
  socket-cleanup faults across the 30-start smoke;
- a real provider-free phase through the generated supervised LaunchAgent
  child environment, with the initiating process allowed to exit;
- proof that provider-free and paid phases share one child, non-secret entry
  environment, and bootstrap binding;
- prerequisite faults for missing, stale, byte-drifted, noncanonical, or
  unpublished authentication receipts; mismatched spend receipts; and changed
  supervisor label, context, config, panel, or precommitment, all before the
  first preclaim mutation;
- proof that the first trace atomically stores the exact prerequisite bundle
  and that the pre-claim re-attestation rejects any changed bundle;
- hard failures if the provider-free phase reaches Keychain, any
  authentication helper, any provider CLI/model entrypoint, the preflight
  claim, or score projection;
- exact 72-byte/73-byte temporary-path boundary tests, finite single-`EINTR`
  recovery, repeated-`EINTR` failure, immediate missing-path failure, and
  same-path directory-replacement detection;
- proof that injected offline evaluators are rejected from a Git worktree,
  from any descendant of one, and from mutable or credential namespaces
  outside their single owner-only ephemeral test root;
- crash injection immediately before and after each preclaim checkpoint and
  immediately before and after the separately durable passed trace and atomic
  preflight claim;
- full-state claim-reconciliation tests covering exact before-state, exact
  after-state, failure-before-replace, exception-after-replace, torn/mixed
  state, and read failure, proving that ambiguity is never repaired;
- proof that a failed, ambiguous, stale, missing, or tampered preclaim cannot start
  or resume preflight;
- proof that the full 30-start smoke runs before claim and is not repeated
  after claim;
- proof that the Keychain loader is called zero times before claim and exactly
  once at the first Cursor evaluator, the key is absent for Starsim/broker,
  Claude, and Codex execution, only Cursor subprocesses receive it, and both
  the cache and environment are wiped on every exit;
- production and success-finalization tests proving that a missing, failed,
  stale, or tampered passed trace blocks provider execution and public release;
  and
- leakage scans over public receipts, authenticated coarse status, monitor
  output, and terminal audit for paths, inventory, exception text, prompts,
  observations, hidden episode data, credentials, OAuth state, schedule data,
  traces, and scores.

The full suite, exact test count, and test command must be recorded only after
the V29 implementation exists. This runbook does not invent them.

## Terminal rules

- As of this control-plane revision, V29 has no runtime receipt, manifest,
  authentication receipt, live supervisor, preflight, production run,
  provider/model call, result, trace, or score.
- V28 is terminal with zero model calls, zero completed profiles, zero
  production episodes, and no scores. Never retry it.
- Never reuse any V28 or earlier key, cohort, cache, credential, state,
  checkout, supervisor, Keychain service, claim, or result path.
- Never fill a placeholder with a local or provisional value.
- Never publish with direct `git push`.
- Never run validation from an ambient Python, PATH-selected provider, or
  unbound environment.
- Never treat preclaim success as spend authorization, authentication proof,
  supervisor proof, or a passing six-call preflight; all prerequisite bindings
  are independently exact-checked before mutation and again before claim.
- Never start V29 twice or repair-and-resume after a terminal incident.
- Never publish or inspect raw provider output, prompts, observations, hidden
  episode identifiers or families, credentials, OAuth state, private seeds or
  schedules, scores, or traces before the final release gates permit them.
