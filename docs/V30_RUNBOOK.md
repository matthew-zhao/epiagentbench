# EpiAgentBench V30 execution runbook

> [!CAUTION]
> **CONTROL-PLANE DESIGN ONLY — NO V30 AUTHENTICATION, PROVIDER, SPEND,
> PREFLIGHT, PRODUCTION, OR MODEL CALL IS AUTHORIZED.**
>
> This runbook freezes the V30 names and gates. It does not authorize creation
> of a runtime receipt, private cohort, manifest, credentials, supervisor, or
> result. Commit values remain explicit placeholders until each public artifact
> is created under a later, separately authorized ceremony and independently
> verified.

## Closed predecessor

V29 is terminal and non-resumable. Its six-call preflight passed, and its
production supervisor later failed closed after the 26th chargeable invocation
boundary. The authenticated incident classified a boot-identity mismatch even
though the host had not rebooted. The run must not be restarted, resumed,
repaired, or used to infer a score. Its public runtime, manifest,
authentication, preflight, production terminal, and supersession receipts are
immutable evidence. The exact trace-free production terminal receipt passed
pinned provider-free attestation with status `stopped_supervisor_incident`, 26
terminal assignments, and no scientific results or scores. Its private
schedule, provider output, traces, credentials, and scores remain protected.

The two closed public predecessor records are
`results/development-matched-50x6-v29.json` and
`results/development-matched-50x6-v29.superseded.json`. They are published
together in one closeout commit, independently verified, and pinned before the
V30 control-plane commit. Publication is a historical closeout only; it cannot
authorize V30 and must not alter any other V29 artifact.

## V30 safety invariants

1. V30 uses fresh panel, cohort, cache, state, credential, checkout,
   supervisor, Keychain, freeze-claim, and public-output namespaces. No V29
   private artifact is copied, moved, relinked, or consumed.
2. Preparation remains provider-free and starts no authentication helper,
   provider process, or model-bearing process.
3. The same supervised child performs the provider-free preclaim phase
   before the irreversible preflight claim. At its named cache-identity
   boundary it computes the complete cache inventory exactly once.
4. The full 30-process broker-startup smoke completes before the claim and is
   not repeated after it.
5. Darwin process identity is construction-or-failure: a canonical boot-session
   UUID and numeric `proc_pidinfo` birth identity are mandatory. There is no
   formatted-time, wall-clock, or synthetic fallback.
6. A failed or ambiguous preclaim, preflight, identity attestation, or
   production boundary is terminal for V30. No monitor may restart it.
7. Provider output, prompts, observations, hidden episode identifiers or
   families, credentials, OAuth state, private seeds or schedule, traces, and
   scores remain absent from public and monitoring surfaces until final release.
8. Publication uses GitButler only. Direct `git push` is forbidden.

## Frozen schemas and identifiers

| Surface | V30 value |
|---|---|
| Panel and cohort | `development-matched-50x6-v30` |
| Top-level schema | `development_matched_panel_v30` |
| Assignments | 50 episodes × 6 profiles = 300 |
| Persistent-supervisor contract | `epiagentbench.persistent_supervisor_contract.v15` |
| Persistent-supervisor state records | `epiagentbench.persistent_supervisor.v4` |
| Process identity authentication domain | `epiagentbench:persistent-supervisor:identity:v3` |
| Supervisor protocol token | `persistent-supervisor-v9` |
| LaunchAgent config | `epiagentbench.launchd_agent.v16` |
| LaunchAgent worker status | `epiagentbench.launchd_worker_status.v6` |
| Runtime receipt | `results/development-matched-50x6-v30.runtime.json` |
| Manifest | `results/development-matched-50x6-v30.manifest.json` |
| Authentication receipt | `results/development-matched-50x6-v30.authentication.json` |
| Preflight receipt | `results/development-matched-50x6-v30.preflight.json` |
| Production result | `results/development-matched-50x6-v30.json` |
| Cursor Keychain service | `epiagentbench-cursor-v30` |
| Control commit | `<V30_CONTROL_COMMIT_40_HEX>` |
| Runtime-receipt commit | `<V30_RUNTIME_RECEIPT_COMMIT_40_HEX>` |
| Manifest commit | `<V30_MANIFEST_COMMIT_40_HEX>` |
| Authentication-receipt commit | `<V30_AUTHENTICATION_RECEIPT_COMMIT_40_HEX>` |

Every V30 validator rejects the corresponding V29 panel, top-level, supervisor,
process-identity, protocol, and LaunchAgent schemas before control action.

## Fresh namespaces

```text
$HOME/.codex/epiagentbench-50x6-v30-runtime-worktree
$HOME/.codex/epiagentbench-50x6-v30-prepare-worktree
$HOME/.codex/epiagentbench-50x6-v30-execution-worktree
$HOME/.codex/epiagentbench-v30-runtime-cache
$HOME/.codex/epiagentbench-v30-runtime-receipt-staging
$HOME/.codex/epiagentbench-v30-cohort
$HOME/.codex/epiagentbench-v30-secrets/panel-auth.key
$HOME/.codex/epiagentbench-v30-state/development-matched-50x6-v30.private.json
$HOME/.codex/epiagentbench-v30-credentials/claude
$HOME/.codex/epiagentbench-v30-credentials/codex
$HOME/.codex/epiagentbench-v30-supervisors/preflight
$HOME/.codex/epiagentbench-v30-supervisors/production
results/development-matched-50x6-v30.runtime.json
results/development-matched-50x6-v30.manifest.json
results/development-matched-50x6-v30.authentication.json
results/development-matched-50x6-v30.preflight.json
results/development-matched-50x6-v30.json
```

Every path must be absent before its create-once phase, while all V29 paths
remain untouched. Additional owner-only staging paths must also carry `v30`
and may not alias an earlier version.

## Finite provider-free preparation

The provider-free preclaim phase performs these exact ordered operations:

| Operation | Content-free failure code |
|---|---|
| `preparation_runtime_bound_contract` | `preparation_runtime_bound_contract_failed` |
| `preparation_runtime_starsim_smoke` | `preparation_runtime_starsim_smoke_failed` |
| `preparation_runtime_episode_startup_smoke` | `preparation_runtime_episode_startup_smoke_failed` |
| `preparation_runtime_cache_identity` | `preparation_runtime_cache_identity_failed` |
| `preparation_runtime_private_cache_binding` | `preparation_runtime_private_cache_binding_failed` |

The attempted operation is durably recorded before each check. The completed
operation advances only after success. Validation, checkpoint-persistence, and
following-phase checkpoint failures retain distinct finite codes. No arbitrary
exception text or private data may enter a public receipt.

## Conservative budget ceiling

The source-owned V30 ceiling is not authorization. It is derived without
reading the V29 private schedule:

- prior panels through V28: `$100`;
- V29 passing preflight: at most two Claude calls, `$10`;
- V29's first 26 production invocations: four complete six-profile blocks plus
  two positions, therefore at most ten Claude calls, `$50`;
- conservative prior-through-V29 allowance: `$160`;
- unchanged V30 current-run ceiling: `$510`; and
- cumulative V30 Claude ceiling: `$670`.

Codex and Cursor spend remain explicitly unbounded. None of these values
authorize a provider call. A later operator must supply the exact text below
and seal it against the exact published V30 manifest and public
precommitment:

> I acknowledge the replacement six-call v30 preflight and 300-assignment production run, including unbounded Codex/Cursor provider spend and up to $670 total Claude spend across the failed v2 preflight, failed v5 preflight, failed v6 authentication bootstrap, failed v7 preflight, failed v8 production run, v9 preflight and failed production run, the abandoned zero-model-call v10 precommitment, the failed zero-model-call v11 authentication bootstrap, the abandoned zero-model-call v12 precommitment, the abandoned zero-model-call v13 precommitment, the failed v14 preflight, the failed zero-model-call v15 pre-claim preparation, the failed v16 preflight, the failed zero-model-call v17 pre-start runtime-cache-environment refusal, the failed v18 preflight, the failed zero-model-call v19 authentication setup, the failed zero-model-call v20 preflight, the failed zero-model-call v21 preflight, the failed zero-model-call v22 interrupted authentication ceremony, the failed v23 six-call preflight release validation, the abandoned zero-model-call v24 control-plane precommitment, the failed zero-model-call v25 provider-free preparation-runtime CLI discovery, the failed v26 preflight with indeterminate provider-call count and a conservative $10 Claude allowance, the failed zero-model-call v27 preflight, the failed zero-model-call v28 preflight, the v29 passing preflight and terminal production run with a conservative $60 Claude allowance, and the v30 preflight and production run.

Its SHA-256 is
`197ce6f0938bad1f8aa3c20c5e052a9519312d4814ffa088bbba99f4e31a42e5`.

## Create-once sequence

1. Publish and independently pin a source/tests/docs-only V30 control-plane
   commit. It contains no V30 runtime or private artifact.
2. In a clean checkout at that commit, produce the provider-free runtime
   receipt twice. Both canonical receipts must be byte-identical and prove
   zero authentication, provider, and model starts.
3. Publish only that existing receipt through GitButler and pin its exact
   commit.
4. From a fresh clean checkout at the receipt commit, re-attest the receipt and
   all five preparation operations. Only then may a later authorization create
   the V30 key, create-once freeze claim, cohort, private state, and manifest.
5. Publish and pin only the public manifest. A later explicit operator decision
   may then create the exact manifest-bound spend receipt and run the foreground
   authentication ceremony.
6. Publish and pin the sanitized authentication receipt. From a fresh clean
   checkout at that commit, generate, install, audit, and status the preflight
   supervisor exactly once, then start it exactly once only after every gate
   independently passes.
7. A passing six-call preflight must be authenticated and independently match
   its closed public receipt before production preparation. Production uses a
   fresh runtime namespace and one authorized start.

No step may be inferred from a placeholder. No runtime generation, provider
call, or private write is authorized by this document.

## Terminal rules

- Never restart, resume, or mutate V29.
- Never reuse a V29 key, cohort, cache, credential, state, checkout,
  supervisor, Keychain service, claim, or output destination.
- Never fill a commit placeholder from local or provisional state.
- Never launch from an ambient interpreter or PATH-selected provider binary.
- Never start either V30 supervisor twice.
- Never publish or inspect protected provider or benchmark data before the
  frozen final-release gates permit it.
