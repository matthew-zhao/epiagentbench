# EpiAgentBench V30 execution runbook

> [!CAUTION]
> **TERMINAL HISTORICAL EVIDENCE — V30 MUST NOT BE RETRIED, RESUMED,
> REPAIRED, OR REUSED.**
>
> V30 published its provider-free runtime receipt, manifest, and sanitized
> authentication receipt. Its sole preflight-supervisor `generate` invocation
> then failed closed while validating the owner-scoped temporary-directory
> contract, before the first runtime write. That refused generation created no
> runtime directory, config, or plist; invoked no install or start operation;
> started no authentication, provider, or model process; attempted no preflight
> profile or production assignment; and released no result or score. The public
> [V30 supersession record](../results/development-matched-50x6-v30.superseded.json)
> is authoritative. V30 is terminal and non-resumable. The remaining text is
> preserved only as historical design evidence and none of its commands may be
> executed. Any replacement must use the fresh namespaces and gates in the
> [V31 runbook](V31_RUNBOOK.md).

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

The exact published V29 closeout commit is
`cf58956cc161507b89afc40f2857934161f6791b` on
`refs/heads/codex/v29-terminal-closeout`.

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
| Preparation receipt | `epiagentbench.preparation_runtime_preflight.v4` |
| Preparation verification | `epiagentbench.preparation_runtime_verification.v3` |
| Bound preparation | `epiagentbench.bound_preparation_runtime.v3` |
| Provider-free environment | `epiagentbench.provider_free_preparation_environment.v2` |
| Runtime-cache contract | `epiagentbench.runtime_cache_contract.v3` |
| Starsim smoke | `epiagentbench.preparation_runtime_smoke.v2` |
| Episode-startup smoke | `epiagentbench.preparation_episode_startup_smoke.v1` |
| Provider-free publication (retained) | `epiagentbench.provider_free_publication.v1` |
| Python isolated bootstrap (retained) | `epiagentbench.python_isolated_bootstrap.v2` |
| Python entrypoint binding (retained) | `epiagentbench.python_entrypoint_binding.v2` |
| LaunchAgent start request (retained) | `epiagentbench.launchd_start_request.v1` |
| Provider-free preclaim (retained) | `epiagentbench.provider_free_preclaim.v3` |
| Preclaim prerequisites (retained) | `epiagentbench.provider_free_preclaim_prerequisites.v1` |
| Preflight incident envelope (retained) | `epiagentbench.preflight_incident_envelope.v3` |
| Provider-free prelaunch (retained) | `epiagentbench.provider_free_prelaunch.v1` |
| Terminal receipt attestation (retained) | `epiagentbench.terminal_receipt_attestation.v1` |
| Provider-free terminal audit (retained) | `epiagentbench.terminal_audit.v3` |
| Terminal incident attestation (retained) | `epiagentbench.terminal_incident_attestation.v2` |
| Spend authorization (retained) | `epiagentbench.spend_authorization.v2` |
| Authentication setup (retained) | `epiagentbench.authentication_setup.v4` |
| Authentication terminal incident (retained) | `epiagentbench.authentication_terminal_incident.v1` |
| Authentication dependency freeze (retained) | `epiagentbench.authentication_dependency_freeze.v1` |
| Authentication receipt (retained) | `epiagentbench.authentication_receipt.v2` |
| Public authentication-receipt attestation (retained) | `epiagentbench.public_authentication_receipt_attestation.v1` |
| Repository receipt binding (retained) | `epiagentbench.repository_receipt_binding.v1` |
| Receipt commit binding (retained) | `epiagentbench.receipt_commit_binding.v1` |
| Private-state storage (retained) | `epiagentbench.private_state_storage.v2` |
| Provider CLI contract (retained) | `epiagentbench.provider_cli_contract.v2` |
| Provider CLI discovery (retained) | `epiagentbench.provider_cli_discovery.v2` |
| Claude authentication (retained) | `epiagentbench.claude_auth.v3` |
| Codex authentication (retained) | `epiagentbench.codex_auth.v1` |
| Provider progress (retained) | `epiagentbench.provider_progress.v1` |
| Cohort preparation (retained) | `epiagentbench.cohort_preparation.v1` |
| Cohort retirement (retained) | `epiagentbench.cohort_retirement.v1` |
| Terminal receipt reconciliation (retained) | `epiagentbench.terminal_receipt_reconciliation.v1` |
| V30 cohort freeze claim | `epiagentbench.v30_cohort_freeze_claim.v1` |
| V30 cohort freeze completion | `epiagentbench.v30_cohort_freeze_completion.v1` |
| V30 cohort freeze | `epiagentbench.v30_cohort_freeze.v2` |
| Runtime receipt | `results/development-matched-50x6-v30.runtime.json` |
| Manifest | `results/development-matched-50x6-v30.manifest.json` |
| Authentication receipt | `results/development-matched-50x6-v30.authentication.json` |
| Preflight receipt | `results/development-matched-50x6-v30.preflight.json` |
| Production result | `results/development-matched-50x6-v30.json` |
| Cursor Keychain service | `epiagentbench-cursor-v30` |
| Cursor Keychain account | `matthew.zhao` |
| Scientific Python | `/Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python` |
| Python flags | `-I -S -B` |
| Python version | `3.13.7` |
| Starsim version | `3.5.1` |
| Control ref | `refs/heads/codex/v30-control-plane` |
| Runtime-receipt ref | `refs/heads/codex/v30-runtime-preflight` |
| Fixed read-only origin | `https://github.com/matthew-zhao/epiagentbench.git` |
| Control commit | `<V30_CONTROL_COMMIT_40_HEX>` |
| Runtime-receipt commit | `<V30_RUNTIME_RECEIPT_COMMIT_40_HEX>` |
| Manifest commit | `<V30_MANIFEST_COMMIT_40_HEX>` |
| Authentication-receipt commit | `<V30_AUTHENTICATION_RECEIPT_COMMIT_40_HEX>` |

Every V30 validator rejects the corresponding V29 panel, top-level, supervisor,
process-identity, protocol, and LaunchAgent schemas before control action.

The first published V30 control commit,
`ddfede1cd6d15821fe5c1918035b5645c5f229ea`, is retired before any runtime
receipt, private artifact, authentication helper, provider, or model start. It
must never be executed or used as a receipt base. The corrected control commit
cannot contain its own hash. At execution time `V30_CONTROL_COMMIT` must be an
independently supplied lowercase 40-hex value that differs from that retired
commit, exactly matches `refs/heads/codex/v30-control-plane`, exactly matches
the clean runtime checkout's `HEAD`, and descends from the pinned V29 closeout.
The later runtime-receipt commit must exactly match
`refs/heads/codex/v30-runtime-preflight`, descend from that corrected control
commit, and add only the existing canonical V30 runtime receipt.

Each commit pin is obtained independently from the fixed HTTPS origin, never
from a local branch name or a value copied from the publication command. For
each exact ref, `git ls-remote --refs --exit-code` must return exactly one
two-field record: a lowercase 40-hex object ID and that exact full ref. The
corresponding fresh checkout must have that fixed URL as `origin`, have a clean
tracked and untracked status, and have `HEAD` equal to the independently
resolved object ID. Apply those requirements separately to:

- `refs/heads/codex/v30-control-plane` and
  `/Users/matthew.zhao/.codex/epiagentbench-50x6-v30-runtime-worktree-r2`;
  and
- `refs/heads/codex/v30-runtime-preflight` and
  `/Users/matthew.zhao/.codex/epiagentbench-50x6-v30-prepare-worktree`.

The two exact independent remote queries are:

```sh
/usr/bin/env -i HOME=/var/empty LC_ALL=C \
  PATH=/usr/bin:/bin:/usr/sbin:/sbin TMPDIR=/private/tmp \
  GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null \
  GIT_TERMINAL_PROMPT=0 \
  /usr/bin/git ls-remote --refs --exit-code \
  https://github.com/matthew-zhao/epiagentbench.git \
  refs/heads/codex/v30-control-plane

/usr/bin/env -i HOME=/var/empty LC_ALL=C \
  PATH=/usr/bin:/bin:/usr/sbin:/sbin TMPDIR=/private/tmp \
  GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null \
  GIT_TERMINAL_PROMPT=0 \
  /usr/bin/git ls-remote --refs --exit-code \
  https://github.com/matthew-zhao/epiagentbench.git \
  refs/heads/codex/v30-runtime-preflight
```

Count and parse each query's stdout without discarding duplicate lines. Then
use `/usr/bin/git -C <checkout> remote get-url origin`, `rev-parse HEAD`, and
`status --porcelain=v1 --untracked-files=all --ignore-submodules=all` to prove
the exact fixed origin, pinned object ID, and empty status in that checkout.

An absent, duplicate, malformed, differently named, or moving remote record,
an origin mismatch, a dirty checkout, or a `HEAD` mismatch fails closed. Do
not infer or repair a pin from any local ref.

## Fresh namespaces

```text
$HOME/.codex/epiagentbench-50x6-v30-runtime-worktree-r2
$HOME/.codex/epiagentbench-50x6-v30-prepare-worktree
$HOME/.codex/epiagentbench-50x6-v30-execution-worktree
$HOME/.codex/epiagentbench-v30-runtime-cache
$HOME/.codex/epiagentbench-v30-runtime-receipt-staging
$HOME/.codex/epiagentbench-v30-provider-free-home
$HOME/.codex/epiagentbench-v30-provider-free-tmp
$HOME/.codex/epiagentbench-v30-cohort
$HOME/.codex/epiagentbench-v30-secrets/panel-auth.key
$HOME/.codex/epiagentbench-v30-secrets/.development-matched-50x6-v30.cohort-freeze-claim.v1.json
$HOME/.codex/epiagentbench-v30-secrets/.development-matched-50x6-v30.cohort-freeze-completion.v1.json
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

`$HOME/.codex/epiagentbench-50x6-v30-runtime-worktree` is immutable retired
evidence at `ddfede1cd6d15821fe5c1918035b5645c5f229ea`; do not mutate, remove, or
execute it. The `-r2` checkout is the sole runtime-receipt checkout for the
corrected control commit.

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

## Provider-free runtime-receipt ceremony

The runtime receipt uses this exact scientific interpreter and no ambient
Python selection:

```text
/Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python -I -S -B
```

Before the first invocation, all seven bootstrap paths below must be absent,
including dangling symlinks. Execute this exact create-only bootstrap once.
Plain `mkdir` is deliberate: `-p`, deletion, truncation, ownership repair, and
reuse are forbidden.

```sh
/usr/bin/env -i LC_ALL=C PATH=/usr/bin:/bin:/usr/sbin:/sbin \
  /bin/sh -eu -c '
umask 077
for path in \
  /Users/matthew.zhao/.codex/epiagentbench-v30-runtime-cache \
  /Users/matthew.zhao/.codex/epiagentbench-v30-runtime-cache/matplotlib \
  /Users/matthew.zhao/.codex/epiagentbench-v30-runtime-cache/numba \
  /Users/matthew.zhao/.codex/epiagentbench-v30-runtime-cache/xdg \
  /Users/matthew.zhao/.codex/epiagentbench-v30-runtime-receipt-staging \
  /Users/matthew.zhao/.codex/epiagentbench-v30-provider-free-home \
  /Users/matthew.zhao/.codex/epiagentbench-v30-provider-free-tmp
do
  if /bin/test -e "$path" || /bin/test -L "$path"; then
    exit 73
  fi
done
/bin/mkdir -m 0700 \
  /Users/matthew.zhao/.codex/epiagentbench-v30-runtime-cache
/bin/mkdir -m 0700 \
  /Users/matthew.zhao/.codex/epiagentbench-v30-runtime-cache/matplotlib \
  /Users/matthew.zhao/.codex/epiagentbench-v30-runtime-cache/numba \
  /Users/matthew.zhao/.codex/epiagentbench-v30-runtime-cache/xdg \
  /Users/matthew.zhao/.codex/epiagentbench-v30-runtime-receipt-staging \
  /Users/matthew.zhao/.codex/epiagentbench-v30-provider-free-home \
  /Users/matthew.zhao/.codex/epiagentbench-v30-provider-free-tmp
for path in \
  /Users/matthew.zhao/.codex/epiagentbench-v30-runtime-cache \
  /Users/matthew.zhao/.codex/epiagentbench-v30-runtime-cache/matplotlib \
  /Users/matthew.zhao/.codex/epiagentbench-v30-runtime-cache/numba \
  /Users/matthew.zhao/.codex/epiagentbench-v30-runtime-cache/xdg \
  /Users/matthew.zhao/.codex/epiagentbench-v30-runtime-receipt-staging \
  /Users/matthew.zhao/.codex/epiagentbench-v30-provider-free-home \
  /Users/matthew.zhao/.codex/epiagentbench-v30-provider-free-tmp
do
  /bin/test ! -L "$path"
  /bin/test "$(/usr/bin/stat -f %Lp "$path")" = 700
done
'
```

Any nonzero exit, interruption, ambiguity, partial creation, unexpected path,
or mode mismatch is a terminal V30 preparation incident. Preserve what was
created for audit; never remove, rename, repair, or rerun the bootstrap. The
cache root may contain exactly its `matplotlib`, `numba`, and `xdg` children,
all seven paths must have mode `0700`, and the staging directory is separate
from the cache. The clean `HOME` is 63 UTF-8 bytes and the clean `TMPDIR` is 62
UTF-8 bytes, below the source-owned 72-byte socket-safety limit. Both must
remain empty before and after every provider-free command. The CLI installs
the six runtime-cache variables itself; the outer process must not supply
them.

The exact outer environment is:

```text
HOME=/Users/matthew.zhao/.codex/epiagentbench-v30-provider-free-home
LC_ALL=C.UTF-8
LOGNAME=matthew.zhao
PATH=/usr/bin:/bin:/usr/sbin:/sbin
SHELL=/bin/zsh
TMPDIR=/Users/matthew.zhao/.codex/epiagentbench-v30-provider-free-tmp
USER=matthew.zhao
__CF_USER_TEXT_ENCODING=0x1F5:0x0:0x0
```

With `V30_CONTROL_COMMIT` independently pinned as described above, run these
two commands from
`/Users/matthew.zhao/.codex/epiagentbench-50x6-v30-runtime-worktree-r2`.
They must each execute the fixed Starsim smoke, the 30-process startup smoke,
and one cache inventory, and must produce byte-identical candidates:

```sh
/usr/bin/env -i \
  HOME=/Users/matthew.zhao/.codex/epiagentbench-v30-provider-free-home \
  LC_ALL=C.UTF-8 LOGNAME=matthew.zhao \
  PATH=/usr/bin:/bin:/usr/sbin:/sbin SHELL=/bin/zsh \
  TMPDIR=/Users/matthew.zhao/.codex/epiagentbench-v30-provider-free-tmp \
  USER=matthew.zhao __CF_USER_TEXT_ENCODING=0x1F5:0x0:0x0 \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python \
  -I -S -B examples/run_development_matched_panel.py \
  preflight-preparation-runtime \
  --expected-benchmark-base-commit "$V30_CONTROL_COMMIT" \
  --runtime-cache-dir /Users/matthew.zhao/.codex/epiagentbench-v30-runtime-cache \
  --public-runtime-receipt /Users/matthew.zhao/.codex/epiagentbench-v30-runtime-receipt-staging/preflight-1.json

/usr/bin/env -i \
  HOME=/Users/matthew.zhao/.codex/epiagentbench-v30-provider-free-home \
  LC_ALL=C.UTF-8 LOGNAME=matthew.zhao \
  PATH=/usr/bin:/bin:/usr/sbin:/sbin SHELL=/bin/zsh \
  TMPDIR=/Users/matthew.zhao/.codex/epiagentbench-v30-provider-free-tmp \
  USER=matthew.zhao __CF_USER_TEXT_ENCODING=0x1F5:0x0:0x0 \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python \
  -I -S -B examples/run_development_matched_panel.py \
  preflight-preparation-runtime \
  --expected-benchmark-base-commit "$V30_CONTROL_COMMIT" \
  --runtime-cache-dir /Users/matthew.zhao/.codex/epiagentbench-v30-runtime-cache \
  --public-runtime-receipt /Users/matthew.zhao/.codex/epiagentbench-v30-runtime-receipt-staging/preflight-2.json

/usr/bin/cmp -s \
  /Users/matthew.zhao/.codex/epiagentbench-v30-runtime-receipt-staging/preflight-1.json \
  /Users/matthew.zhao/.codex/epiagentbench-v30-runtime-receipt-staging/preflight-2.json
```

The two generation commands are two precommitted independent attestations,
not retry slots. If candidate 1 fails or is ambiguous, do not run candidate 2.
If candidate 2 or the byte comparison fails or is ambiguous, do not generate
another candidate. Any interruption or nonzero exit is terminal for this V30
namespace; preserve the cache, staging, `HOME`, `TMPDIR`, and candidates
exactly as observed.

After both candidates independently prove zero authentication, provider, and
model starts, publish candidate 1 exactly once into the GitButler primary
checkout. This is an exact provider-free copy, not a third generation:

```sh
/usr/bin/env -i \
  HOME=/Users/matthew.zhao/.codex/epiagentbench-v30-provider-free-home \
  LC_ALL=C.UTF-8 LOGNAME=matthew.zhao \
  PATH=/usr/bin:/bin:/usr/sbin:/sbin SHELL=/bin/zsh \
  TMPDIR=/Users/matthew.zhao/.codex/epiagentbench-v30-provider-free-tmp \
  USER=matthew.zhao __CF_USER_TEXT_ENCODING=0x1F5:0x0:0x0 \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python \
  -I -S -B examples/run_development_matched_panel.py \
  publish-provider-free-json \
  --source /Users/matthew.zhao/.codex/epiagentbench-v30-runtime-receipt-staging/preflight-1.json \
  --destination '/Users/matthew.zhao/Documents/Disease Surveillance/epiagentbench-v22-edit/results/development-matched-50x6-v30.runtime.json'
```

Commit and publish only that receipt through GitButler, independently resolve
exactly one fixed-origin record for the runtime-receipt ref, and materialize
the fresh prepare checkout whose clean `HEAD` equals that remote object ID.
With `V30_RUNTIME_RECEIPT_COMMIT` set only from that independent pin, run this
exact single verification from
`/Users/matthew.zhao/.codex/epiagentbench-50x6-v30-prepare-worktree`:

```sh
/usr/bin/env -i \
  HOME=/Users/matthew.zhao/.codex/epiagentbench-v30-provider-free-home \
  LC_ALL=C.UTF-8 LOGNAME=matthew.zhao \
  PATH=/usr/bin:/bin:/usr/sbin:/sbin SHELL=/bin/zsh \
  TMPDIR=/Users/matthew.zhao/.codex/epiagentbench-v30-provider-free-tmp \
  USER=matthew.zhao __CF_USER_TEXT_ENCODING=0x1F5:0x0:0x0 \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python \
  -I -S -B examples/run_development_matched_panel.py \
  verify-preparation-runtime \
  --preparation-runtime-receipt /Users/matthew.zhao/.codex/epiagentbench-50x6-v30-prepare-worktree/results/development-matched-50x6-v30.runtime.json \
  --expected-benchmark-base-commit "$V30_RUNTIME_RECEIPT_COMMIT" \
  --runtime-cache-dir /Users/matthew.zhao/.codex/epiagentbench-v30-runtime-cache \
  --public-verification-receipt /Users/matthew.zhao/.codex/epiagentbench-v30-runtime-receipt-staging/verification.json
```

`verification.json` must be absent, including as a dangling symlink, before
this one invocation. Any mismatch, nonzero exit, interruption, ambiguity, or
partial verification receipt is terminal; do not rerun verification, repair
the cache, regenerate a candidate, replace the receipt, or reuse either the
retired or active checkout.

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
   checkout at that commit, generate and install the preflight supervisor
   exactly once, then start it exactly once only after every gate independently
   passes. `audit` and `status` are repeatable, provider-free, authenticated,
   read-only observations while the installed job remains dormant; they are
   not create-once ceremony steps and cannot repair or reauthorize a failed
   gate. `audit` validates the sealed config, plist, source,
   Python/runtime-cache, and prelaunch identity; permits the reusable
   owner-only control-lock leaf created by the install ceremony, requires the
   irreversible start-attempt leaf, start marker, worker status, and core
   supervisor state all to be absent; and accepts only a loaded dormant
   LaunchAgent. Its only launchd
   operation is `print`. It does not query Keychain, invoke a provider, write
   a marker or lock, or mutate launchd, and it returns only coarse allowlisted
   state. A failed or ambiguous observation is terminal even though a healthy
   read-only observation may be repeated.
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
- Never retry or repair the provider-free bootstrap, either receipt candidate,
  publication, or verification after any failed, interrupted, or ambiguous
  boundary.
- Never publish or inspect protected provider or benchmark data before the
  frozen final-release gates permit it.
