# EpiAgentBench V31 execution runbook

> [!CAUTION]
> **V31 IS TERMINAL AND NON-RESUMABLE. DO NOT EXECUTE ANY CEREMONY BELOW.**
>
> The commands and placeholders below are preserved only as historical design
> evidence. They do not authorize publication, authentication, provider use,
> spend, preflight, production, retry, repair, or reuse. The forward procedure
> is the [V32 runbook](V32_RUNBOOK.md).

## Terminal runtime-publication incident

V31 completed its provider-free bootstrap and produced two byte-identical
runtime-receipt candidates with zero authentication, provider, and model
starts. Its single authorized GitButler publication attempt then failed before
any remote mutation because publication credentials were unavailable. The
fixed origin retained `refs/heads/codex/v31-control-plane` at
`6efe0fa93e9c72946b48c22ab27a7fe6b41c199c` and had no
`refs/heads/codex/v31-runtime-preflight` record. No runtime receipt became
public; no manifest, private cohort, authentication, preflight, supervisor, or
production action followed. The local candidates and unpublished local commit
are quarantined evidence, not public pins, and may not enter later ancestry or
be reused.

V31 closes only through
`refs/heads/codex/v31-runtime-publication-terminal-closeout`. That ref must be
the sole child of the independently pinned control commit
`6efe0fa93e9c72946b48c22ab27a7fe6b41c199c` and must add exactly:

- `results/development-matched-50x6-v31.superseded.json`; and
- `tests/test_v31_supersession.py`.

It must not contain V31 runtime-receipt bytes, candidate bytes, a manifest,
private artifact, authentication receipt, preflight receipt, result, provider
data, or trace. The record may identify the unpublished local receipt commit
only as safe, non-authoritative incident metadata; that object and its receipt
must remain outside the closeout tree and ancestry. The closeout records the
one failed publication attempt and zero authentication/provider/model calls
under `epiagentbench.panel_supersession.v24`.
After its exact remote commit is independently pinned, V32 may begin from that
closeout; V31 itself remains permanently closed.

## Closed predecessor

V30 is terminal and non-resumable. Its sole preflight-supervisor `generate`
invocation failed the owner-scoped temporary-directory contract before the
first runtime write. No runtime directory, config, plist, install, start,
provider process, model call, preflight profile, or production assignment was
created or started. There is no V30 preflight or result artifact, and the V30
supervisor generation must never be retried or repaired.

The closed public predecessor record is
`results/development-matched-50x6-v30.superseded.json`. Its historical
closeout ref is `refs/heads/codex/v30-terminal-closeout`; its exact commit is
`36f12893ee016cb83be1d90222a5fdba875b4de0`, independently resolved from the
fixed origin. That closeout is the sole child of the exact
published V30 authentication-receipt commit
`ba25bab441f7cc28f56e4668006f12821949a0e4` and may add only the supersession
record and its focused test. It cannot authorize V31 or alter another V30
artifact.

## V31 safety invariants

1. V31 uses fresh panel, cohort, cache, state, credential, checkout,
   supervisor, Keychain, freeze-claim, and public-output namespaces. No V30 or
   earlier private artifact is copied, moved, relinked, or consumed.
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
   production boundary is terminal for V31. No monitor may restart it.
7. Provider output, prompts, observations, hidden episode identifiers or
   families, credentials, OAuth state, private seeds or schedule, traces, and
   scores remain absent from public and monitoring surfaces until final release.
8. Publication uses GitButler only. Direct `git push` is forbidden.

## Frozen schemas and identifiers

| Surface | V31 value |
|---|---|
| Panel and cohort | `development-matched-50x6-v31` |
| Top-level schema | `development_matched_panel_v31` |
| Assignments | 50 episodes × 6 profiles = 300 |
| Persistent-supervisor contract | `epiagentbench.persistent_supervisor_contract.v16` |
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
| V31 cohort freeze claim | `epiagentbench.v31_cohort_freeze_claim.v1` |
| V31 cohort freeze completion | `epiagentbench.v31_cohort_freeze_completion.v1` |
| V31 cohort freeze | `epiagentbench.v31_cohort_freeze.v2` |
| Runtime receipt | `results/development-matched-50x6-v31.runtime.json` |
| Manifest | `results/development-matched-50x6-v31.manifest.json` |
| Authentication receipt | `results/development-matched-50x6-v31.authentication.json` |
| Preflight receipt | `results/development-matched-50x6-v31.preflight.json` |
| Production result | `results/development-matched-50x6-v31.json` |
| Cursor Keychain service | `epiagentbench-cursor-v31` |
| Cursor Keychain account | `matthew.zhao` |
| Scientific Python | `/Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python` |
| Python flags | `-I -S -B` |
| Python version | `3.13.7` |
| Starsim version | `3.5.1` |
| Control ref | `refs/heads/codex/v31-control-plane` |
| Runtime-receipt ref | `refs/heads/codex/v31-runtime-preflight` |
| Manifest publication ref | `refs/heads/codex/v31-runtime-preflight` |
| Authentication publication ref | `refs/heads/codex/v31-runtime-preflight` |
| Preflight publication ref | `refs/heads/codex/v31-runtime-preflight` |
| Terminal preflight-closeout ref | `refs/heads/codex/v31-preflight-terminal-closeout` |
| Successful production-result ref | `refs/heads/codex/v31-production-results` |
| Terminal production-closeout ref | `refs/heads/codex/v31-terminal-closeout` |
| Fixed read-only origin | `https://github.com/matthew-zhao/epiagentbench.git` |
| V30 terminal-closeout ref | `refs/heads/codex/v30-terminal-closeout` |
| V30 terminal-closeout commit | `36f12893ee016cb83be1d90222a5fdba875b4de0` |
| Control commit | `<V31_CONTROL_COMMIT_40_HEX>` |
| Runtime-receipt commit | `<V31_RUNTIME_RECEIPT_COMMIT_40_HEX>` |
| Manifest commit | `<V31_MANIFEST_COMMIT_40_HEX>` |
| Authentication-receipt commit | `<V31_AUTHENTICATION_RECEIPT_COMMIT_40_HEX>` |
| Passing-preflight commit | `<V31_PREFLIGHT_RECEIPT_COMMIT_40_HEX>` |
| Terminal preflight-closeout commit | `<V31_PREFLIGHT_TERMINAL_CLOSEOUT_COMMIT_40_HEX>` |
| Successful production-result commit | `<V31_PRODUCTION_RESULT_COMMIT_40_HEX>` |

Every V31 validator rejects the V30 panel and top-level schemas, every V30
cohort-freeze namespace, and persistent-supervisor contract v15 before control
action. Persistent-supervisor state v4, identity v3, protocol v9, LaunchAgent
v16, and worker status v6 are deliberately retained and re-attested.

The V31 control commit cannot contain its own hash. At execution time
`V31_CONTROL_COMMIT` must be an independently supplied lowercase 40-hex value
that exactly matches `refs/heads/codex/v31-control-plane`, exactly matches the
clean runtime checkout's `HEAD`, and is the direct child of the independently
pinned V30 terminal-closeout commit. The later runtime-receipt commit must
exactly match
`refs/heads/codex/v31-runtime-preflight`, descend from that corrected control
commit, and add only the existing canonical V31 runtime receipt.

That same staged public-receipt ref then advances through exactly three more
one-file commits: the canonical manifest, the sanitized authentication
receipt, and the closed passing-preflight receipt, in that order. Each commit
must be independently pinned from the fixed origin before the next phase, and
each fresh checkout must bind its exact commit: `prepare-worktree` at the
runtime receipt, `manifest-worktree` at the manifest, `execution-worktree` at
the authentication receipt, and `production-worktree` at the passing
preflight receipt. No commit may co-publish code, documentation, another
receipt, or a private artifact.

Any terminal or ambiguous preflight outcome after the authentication receipt
is published and before a passing-preflight commit exists must not advance the
staged public-receipt ref. It uses
`refs/heads/codex/v31-preflight-terminal-closeout`, whose sole parent is the
independently pinned authentication-receipt commit. That closeout adds only
`results/development-matched-50x6-v31.superseded.json`, its focused public
contract test, and—only when the supervisor durably produced it—the canonical
trace-free closed preflight receipt. The supersession record must explicitly
state whether that receipt exists and bind every earlier V31 public receipt.
Thus a failure before any preflight receipt has a two-file closeout; a failure
with an existing closed preflight receipt has a three-file closeout. Neither
scope may contain code, documentation, a production result, or private data.

Successful production publishes only the closed canonical result on
`refs/heads/codex/v31-production-results`, whose sole parent is the passing
preflight commit. A terminal production incident instead uses
`refs/heads/codex/v31-terminal-closeout` and may add only the trace-free
terminal result, its supersession record, and their focused public contract
test. The preflight-terminal, successful-production, and terminal-production
paths are mutually exclusive. The exact selected remote commit is independently
pinned and checked out cleanly in `release-worktree` before final public release
validation.

Each commit pin is obtained independently from the fixed HTTPS origin, never
from a local branch name or a value copied from the publication command. For
each exact ref, `git ls-remote --refs --exit-code` must return exactly one
two-field record: a lowercase 40-hex object ID and that exact full ref. The
corresponding fresh checkout must have that fixed URL as `origin`, have a clean
tracked and untracked status, and have `HEAD` equal to the independently
resolved object ID. Apply those requirements separately to:

- `refs/heads/codex/v31-control-plane` and
  `/Users/matthew.zhao/.codex/epiagentbench-50x6-v31-runtime-worktree`;
  and
- `refs/heads/codex/v31-runtime-preflight` and each phase-specific prepare,
  manifest, execution, or production checkout; and
- on a terminal preflight,
  `refs/heads/codex/v31-preflight-terminal-closeout`; otherwise, after a
  passing preflight, exactly one of `refs/heads/codex/v31-production-results`
  or `refs/heads/codex/v31-terminal-closeout`; plus
  `/Users/matthew.zhao/.codex/epiagentbench-50x6-v31-release-worktree`.

The predecessor closeout, control, and staged-receipt queries are below.
Repeat the staged-receipt query after each of its four one-file publications
and bind the newly observed tip to the phase-specific commit placeholder before
continuing:

```sh
/usr/bin/env -i HOME=/var/empty LC_ALL=C \
  PATH=/usr/bin:/bin:/usr/sbin:/sbin \
  GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null \
  GIT_TERMINAL_PROMPT=0 \
  /usr/bin/git ls-remote --refs --exit-code \
  https://github.com/matthew-zhao/epiagentbench.git \
  refs/heads/codex/v30-terminal-closeout

/usr/bin/env -i HOME=/var/empty LC_ALL=C \
  PATH=/usr/bin:/bin:/usr/sbin:/sbin \
  GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null \
  GIT_TERMINAL_PROMPT=0 \
  /usr/bin/git ls-remote --refs --exit-code \
  https://github.com/matthew-zhao/epiagentbench.git \
  refs/heads/codex/v31-control-plane

/usr/bin/env -i HOME=/var/empty LC_ALL=C \
  PATH=/usr/bin:/bin:/usr/sbin:/sbin \
  GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null \
  GIT_TERMINAL_PROMPT=0 \
  /usr/bin/git ls-remote --refs --exit-code \
  https://github.com/matthew-zhao/epiagentbench.git \
  refs/heads/codex/v31-runtime-preflight
```

After a terminal preflight, run only the first final query below. After a
passing preflight and production, run exactly one of the remaining two. These
three terminal paths are mutually exclusive:

```sh
/usr/bin/env -i HOME=/var/empty LC_ALL=C \
  PATH=/usr/bin:/bin:/usr/sbin:/sbin \
  GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null \
  GIT_TERMINAL_PROMPT=0 \
  /usr/bin/git ls-remote --refs --exit-code \
  https://github.com/matthew-zhao/epiagentbench.git \
  refs/heads/codex/v31-preflight-terminal-closeout

/usr/bin/env -i HOME=/var/empty LC_ALL=C \
  PATH=/usr/bin:/bin:/usr/sbin:/sbin \
  GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null \
  GIT_TERMINAL_PROMPT=0 \
  /usr/bin/git ls-remote --refs --exit-code \
  https://github.com/matthew-zhao/epiagentbench.git \
  refs/heads/codex/v31-production-results

/usr/bin/env -i HOME=/var/empty LC_ALL=C \
  PATH=/usr/bin:/bin:/usr/sbin:/sbin \
  GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null \
  GIT_TERMINAL_PROMPT=0 \
  /usr/bin/git ls-remote --refs --exit-code \
  https://github.com/matthew-zhao/epiagentbench.git \
  refs/heads/codex/v31-terminal-closeout
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
$HOME/.codex/epiagentbench-50x6-v31-runtime-worktree
$HOME/.codex/epiagentbench-50x6-v31-prepare-worktree
$HOME/.codex/epiagentbench-50x6-v31-manifest-worktree
$HOME/.codex/epiagentbench-50x6-v31-execution-worktree
$HOME/.codex/epiagentbench-50x6-v31-production-worktree
$HOME/.codex/epiagentbench-50x6-v31-release-worktree
$HOME/.codex/epiagentbench-v31-runtime-cache
$HOME/.codex/epiagentbench-v31-runtime-receipt-staging
$HOME/.codex/epiagentbench-v31-provider-free-home
$HOME/.codex/epiagentbench-v31-provider-free-tmp
$HOME/.codex/epiagentbench-v31-cohort
$HOME/.codex/epiagentbench-v31-secrets/panel-auth.key
$HOME/.codex/epiagentbench-v31-secrets/.development-matched-50x6-v31.cohort-freeze-claim.v1.json
$HOME/.codex/epiagentbench-v31-secrets/.development-matched-50x6-v31.cohort-freeze-completion.v1.json
$HOME/.codex/epiagentbench-v31-state/development-matched-50x6-v31.private.json
$HOME/.codex/epiagentbench-v31-credentials/claude
$HOME/.codex/epiagentbench-v31-credentials/codex
$HOME/.codex/epiagentbench-v31-supervisors/preflight
$HOME/.codex/epiagentbench-v31-supervisors/production
results/development-matched-50x6-v31.runtime.json
results/development-matched-50x6-v31.manifest.json
results/development-matched-50x6-v31.authentication.json
results/development-matched-50x6-v31.preflight.json
results/development-matched-50x6-v31.json
```

Every path must be absent before its create-once phase, while all V30 and
earlier paths remain untouched. Additional owner-only staging paths must also
carry `v31` and may not alias an earlier version.

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
  /Users/matthew.zhao/.codex/epiagentbench-v31-runtime-cache \
  /Users/matthew.zhao/.codex/epiagentbench-v31-runtime-cache/matplotlib \
  /Users/matthew.zhao/.codex/epiagentbench-v31-runtime-cache/numba \
  /Users/matthew.zhao/.codex/epiagentbench-v31-runtime-cache/xdg \
  /Users/matthew.zhao/.codex/epiagentbench-v31-runtime-receipt-staging \
  /Users/matthew.zhao/.codex/epiagentbench-v31-provider-free-home \
  /Users/matthew.zhao/.codex/epiagentbench-v31-provider-free-tmp
do
  if /bin/test -e "$path" || /bin/test -L "$path"; then
    exit 73
  fi
done
/bin/mkdir -m 0700 \
  /Users/matthew.zhao/.codex/epiagentbench-v31-runtime-cache
/bin/mkdir -m 0700 \
  /Users/matthew.zhao/.codex/epiagentbench-v31-runtime-cache/matplotlib \
  /Users/matthew.zhao/.codex/epiagentbench-v31-runtime-cache/numba \
  /Users/matthew.zhao/.codex/epiagentbench-v31-runtime-cache/xdg \
  /Users/matthew.zhao/.codex/epiagentbench-v31-runtime-receipt-staging \
  /Users/matthew.zhao/.codex/epiagentbench-v31-provider-free-home \
  /Users/matthew.zhao/.codex/epiagentbench-v31-provider-free-tmp
for path in \
  /Users/matthew.zhao/.codex/epiagentbench-v31-runtime-cache \
  /Users/matthew.zhao/.codex/epiagentbench-v31-runtime-cache/matplotlib \
  /Users/matthew.zhao/.codex/epiagentbench-v31-runtime-cache/numba \
  /Users/matthew.zhao/.codex/epiagentbench-v31-runtime-cache/xdg \
  /Users/matthew.zhao/.codex/epiagentbench-v31-runtime-receipt-staging \
  /Users/matthew.zhao/.codex/epiagentbench-v31-provider-free-home \
  /Users/matthew.zhao/.codex/epiagentbench-v31-provider-free-tmp
do
  /bin/test ! -L "$path"
  /bin/test "$(/usr/bin/stat -f %Lp "$path")" = 700
done
'
```

Any nonzero exit, interruption, ambiguity, partial creation, unexpected path,
or mode mismatch is a terminal V31 preparation incident. Preserve what was
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
HOME=/Users/matthew.zhao/.codex/epiagentbench-v31-provider-free-home
LC_ALL=C.UTF-8
LOGNAME=matthew.zhao
PATH=/usr/bin:/bin:/usr/sbin:/sbin
SHELL=/bin/zsh
TMPDIR=/Users/matthew.zhao/.codex/epiagentbench-v31-provider-free-tmp
USER=matthew.zhao
__CF_USER_TEXT_ENCODING=0x1F5:0x0:0x0
```

With `V31_CONTROL_COMMIT` independently pinned as described above, run these
two commands from
`/Users/matthew.zhao/.codex/epiagentbench-50x6-v31-runtime-worktree`.
They must each execute the fixed Starsim smoke, the 30-process startup smoke,
and one cache inventory, and must produce byte-identical candidates:

```sh
/usr/bin/env -i \
  HOME=/Users/matthew.zhao/.codex/epiagentbench-v31-provider-free-home \
  LC_ALL=C.UTF-8 LOGNAME=matthew.zhao \
  PATH=/usr/bin:/bin:/usr/sbin:/sbin SHELL=/bin/zsh \
  TMPDIR=/Users/matthew.zhao/.codex/epiagentbench-v31-provider-free-tmp \
  USER=matthew.zhao __CF_USER_TEXT_ENCODING=0x1F5:0x0:0x0 \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python \
  -I -S -B examples/run_development_matched_panel.py \
  preflight-preparation-runtime \
  --expected-benchmark-base-commit "$V31_CONTROL_COMMIT" \
  --runtime-cache-dir /Users/matthew.zhao/.codex/epiagentbench-v31-runtime-cache \
  --public-runtime-receipt /Users/matthew.zhao/.codex/epiagentbench-v31-runtime-receipt-staging/preflight-1.json

/usr/bin/env -i \
  HOME=/Users/matthew.zhao/.codex/epiagentbench-v31-provider-free-home \
  LC_ALL=C.UTF-8 LOGNAME=matthew.zhao \
  PATH=/usr/bin:/bin:/usr/sbin:/sbin SHELL=/bin/zsh \
  TMPDIR=/Users/matthew.zhao/.codex/epiagentbench-v31-provider-free-tmp \
  USER=matthew.zhao __CF_USER_TEXT_ENCODING=0x1F5:0x0:0x0 \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python \
  -I -S -B examples/run_development_matched_panel.py \
  preflight-preparation-runtime \
  --expected-benchmark-base-commit "$V31_CONTROL_COMMIT" \
  --runtime-cache-dir /Users/matthew.zhao/.codex/epiagentbench-v31-runtime-cache \
  --public-runtime-receipt /Users/matthew.zhao/.codex/epiagentbench-v31-runtime-receipt-staging/preflight-2.json

/usr/bin/cmp -s \
  /Users/matthew.zhao/.codex/epiagentbench-v31-runtime-receipt-staging/preflight-1.json \
  /Users/matthew.zhao/.codex/epiagentbench-v31-runtime-receipt-staging/preflight-2.json
```

The two generation commands are two precommitted independent attestations,
not retry slots. If candidate 1 fails or is ambiguous, do not run candidate 2.
If candidate 2 or the byte comparison fails or is ambiguous, do not generate
another candidate. Any interruption or nonzero exit is terminal for this V31
namespace; preserve the cache, staging, `HOME`, `TMPDIR`, and candidates
exactly as observed.

After both candidates independently prove zero authentication, provider, and
model starts, publish candidate 1 exactly once into the GitButler primary
checkout. This is an exact provider-free copy, not a third generation:

```sh
/usr/bin/env -i \
  HOME=/Users/matthew.zhao/.codex/epiagentbench-v31-provider-free-home \
  LC_ALL=C.UTF-8 LOGNAME=matthew.zhao \
  PATH=/usr/bin:/bin:/usr/sbin:/sbin SHELL=/bin/zsh \
  TMPDIR=/Users/matthew.zhao/.codex/epiagentbench-v31-provider-free-tmp \
  USER=matthew.zhao __CF_USER_TEXT_ENCODING=0x1F5:0x0:0x0 \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python \
  -I -S -B examples/run_development_matched_panel.py \
  publish-provider-free-json \
  --source /Users/matthew.zhao/.codex/epiagentbench-v31-runtime-receipt-staging/preflight-1.json \
  --destination '/Users/matthew.zhao/Documents/Disease Surveillance/epiagentbench-v22-edit/results/development-matched-50x6-v31.runtime.json'
```

Commit and publish only that receipt through GitButler, independently resolve
exactly one fixed-origin record for the runtime-receipt ref, and materialize
the fresh prepare checkout whose clean `HEAD` equals that remote object ID.
With `V31_RUNTIME_RECEIPT_COMMIT` set only from that independent pin, run this
exact single verification from
`/Users/matthew.zhao/.codex/epiagentbench-50x6-v31-prepare-worktree`:

```sh
/usr/bin/env -i \
  HOME=/Users/matthew.zhao/.codex/epiagentbench-v31-provider-free-home \
  LC_ALL=C.UTF-8 LOGNAME=matthew.zhao \
  PATH=/usr/bin:/bin:/usr/sbin:/sbin SHELL=/bin/zsh \
  TMPDIR=/Users/matthew.zhao/.codex/epiagentbench-v31-provider-free-tmp \
  USER=matthew.zhao __CF_USER_TEXT_ENCODING=0x1F5:0x0:0x0 \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python \
  -I -S -B examples/run_development_matched_panel.py \
  verify-preparation-runtime \
  --preparation-runtime-receipt /Users/matthew.zhao/.codex/epiagentbench-50x6-v31-prepare-worktree/results/development-matched-50x6-v31.runtime.json \
  --expected-benchmark-base-commit "$V31_RUNTIME_RECEIPT_COMMIT" \
  --runtime-cache-dir /Users/matthew.zhao/.codex/epiagentbench-v31-runtime-cache \
  --public-verification-receipt /Users/matthew.zhao/.codex/epiagentbench-v31-runtime-receipt-staging/verification.json
```

`verification.json` must be absent, including as a dangling symlink, before
this one invocation. Any mismatch, nonzero exit, interruption, ambiguity, or
partial verification receipt is terminal; do not rerun verification, repair
the cache, regenerate a candidate, replace the receipt, or reuse either the
retired or active checkout.

## Conservative budget ceiling

The source-owned V31 ceiling is not authorization. It is derived without
reading any private schedule:

- prior panels through V28: `$100`;
- V29 passing preflight: at most two Claude calls, `$10`;
- V29's first 26 production invocations: four complete six-profile blocks plus
  two positions, therefore at most ten Claude calls, `$50`;
- V30 supervisor-generation environment refusal: zero model calls, `$0`;
- conservative prior-through-V30 allowance: `$160`;
- unchanged V31 current-run ceiling: `$510`; and
- cumulative V31 Claude ceiling: `$670`.

Codex and Cursor spend remain explicitly unbounded. None of these values
authorize a provider call. A later operator must supply the exact text below
and seal it against the exact published V31 manifest and public
precommitment:

> I acknowledge the replacement six-call v31 preflight and 300-assignment production run, including unbounded Codex/Cursor provider spend and up to $670 total Claude spend across the failed v2 preflight, failed v5 preflight, failed v6 authentication bootstrap, failed v7 preflight, failed v8 production run, v9 preflight and failed production run, the abandoned zero-model-call v10 precommitment, the failed zero-model-call v11 authentication bootstrap, the abandoned zero-model-call v12 precommitment, the abandoned zero-model-call v13 precommitment, the failed v14 preflight, the failed zero-model-call v15 pre-claim preparation, the failed v16 preflight, the failed zero-model-call v17 pre-start runtime-cache-environment refusal, the failed v18 preflight, the failed zero-model-call v19 authentication setup, the failed zero-model-call v20 preflight, the failed zero-model-call v21 preflight, the failed zero-model-call v22 interrupted authentication ceremony, the failed v23 six-call preflight release validation, the abandoned zero-model-call v24 control-plane precommitment, the failed zero-model-call v25 provider-free preparation-runtime CLI discovery, the failed v26 preflight with indeterminate provider-call count and a conservative $10 Claude allowance, the failed zero-model-call v27 preflight, the failed zero-model-call v28 preflight, the v29 passing preflight and terminal production run with a conservative $60 Claude allowance, the failed zero-model-call v30 preflight supervisor-generation environment validation, and the v31 preflight and production run.

Its SHA-256 is
`83adb3d80750858ec0a6c5ee678d6af870e2a495272c8ed161c2ac175888673c`.

## Create-once sequence

1. Publish and independently pin the two-file V30 terminal closeout on
   `refs/heads/codex/v30-terminal-closeout` as the sole child of
   `ba25bab441f7cc28f56e4668006f12821949a0e4`.
2. Publish and independently pin a source/tests/docs-only V31 control-plane
   commit on `refs/heads/codex/v31-control-plane` as the direct child of that
   closeout. It contains no V31 runtime or private artifact.
3. In a clean checkout at that commit, produce the provider-free runtime
   receipt twice. Both canonical receipts must be byte-identical and prove
   zero authentication, provider, and model starts.
4. Publish only that existing receipt through GitButler on
   `refs/heads/codex/v31-runtime-preflight` and pin its exact commit.
5. From a fresh clean checkout at the receipt commit, re-attest the receipt and
   all five preparation operations. Only then may a later authorization create
   the V31 key, create-once freeze claim, cohort, private state, and manifest.
6. Publish and pin only the public manifest as the next one-file commit on the
   same staged public-receipt ref. From a fresh clean manifest checkout, a
   later explicit operator decision may create the exact manifest-bound spend
   receipt and run the foreground authentication ceremony.
7. Publish and pin only the sanitized authentication receipt as the next
   one-file commit on that ref. From a fresh clean execution checkout at that
   commit, generate and install the preflight supervisor
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
8. A terminal or ambiguous preflight instead closes from the authentication
   commit on `refs/heads/codex/v31-preflight-terminal-closeout` with exactly the
   two- or three-file scope frozen above, then stops. Only a passing six-call
   preflight may be authenticated, committed alone as the next one-file commit
   on the staged ref, and independently matched to its closed public receipt.
   Create a fresh clean production checkout at that exact passing-preflight
   commit. Production uses a fresh supervisor namespace and one separately
   authorized start.
9. On successful completion, publish only the closed result on
   `refs/heads/codex/v31-production-results`. On a terminal incident, publish
   only the frozen trace-free terminal closeout scope on
   `refs/heads/codex/v31-terminal-closeout`. Independently pin the one selected
   ref and validate final release from a fresh clean release checkout.

## Exact supervisor environment and one-shot commands

Before either `generate`, the frozen V31 `TMPDIR` must still resolve to itself,
be a nonsymlink directory owned by the effective user with exact mode `0700`,
and occupy at most 72 UTF-8 bytes. Generation validates that condition before
reading the repository, authentication key, private state, manifest, or other
execution bindings. It exposes only the finite public failure code
`generation_environment_invalid`; any such refusal is terminal for that V31
namespace.

Every `generate`, `install`, `audit`, `status`, and `start` invocation below
uses the same exact clean environment. Do not substitute ambient shell state,
`/private/tmp`, a wrapper, or a different interpreter.

After the authentication-receipt commit is independently pinned and every
preflight gate is satisfied, execute each preflight command once and in this
order. `audit` and `status` are observations; their inclusion here does not
make a failed create-once boundary retryable.

```sh
/usr/bin/env -i HOME=/Users/matthew.zhao/.codex/epiagentbench-v31-provider-free-home LC_ALL=C.UTF-8 LOGNAME=matthew.zhao PATH=/usr/bin:/bin:/usr/sbin:/sbin SHELL=/bin/zsh TMPDIR=/Users/matthew.zhao/.codex/epiagentbench-v31-provider-free-tmp USER=matthew.zhao __CF_USER_TEXT_ENCODING=0x1F5:0x0:0x0 \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python -I -S -B \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v31-execution-worktree/examples/run_persistent_panel_supervisor.py generate \
  --operation preflight \
  --runtime-dir /Users/matthew.zhao/.codex/epiagentbench-v31-supervisors/preflight \
  --repository-root /Users/matthew.zhao/.codex/epiagentbench-50x6-v31-execution-worktree \
  --python-executable /Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python \
  --runtime-cache-dir /Users/matthew.zhao/.codex/epiagentbench-v31-runtime-cache \
  --authentication-key /Users/matthew.zhao/.codex/epiagentbench-v31-secrets/panel-auth.key \
  --claude-secure-storage-dir /Users/matthew.zhao/.codex/epiagentbench-v31-credentials/claude \
  --codex-secure-storage-dir /Users/matthew.zhao/.codex/epiagentbench-v31-credentials/codex \
  --private-state /Users/matthew.zhao/.codex/epiagentbench-v31-state/development-matched-50x6-v31.private.json \
  --public-manifest /Users/matthew.zhao/.codex/epiagentbench-50x6-v31-execution-worktree/results/development-matched-50x6-v31.manifest.json \
  --public-preflight /Users/matthew.zhao/.codex/epiagentbench-50x6-v31-execution-worktree/results/development-matched-50x6-v31.preflight.json \
  --cursor-keychain-service epiagentbench-cursor-v31 \
  --cursor-keychain-account matthew.zhao

/usr/bin/env -i HOME=/Users/matthew.zhao/.codex/epiagentbench-v31-provider-free-home LC_ALL=C.UTF-8 LOGNAME=matthew.zhao PATH=/usr/bin:/bin:/usr/sbin:/sbin SHELL=/bin/zsh TMPDIR=/Users/matthew.zhao/.codex/epiagentbench-v31-provider-free-tmp USER=matthew.zhao __CF_USER_TEXT_ENCODING=0x1F5:0x0:0x0 \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python -I -S -B \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v31-execution-worktree/examples/run_persistent_panel_supervisor.py install \
  --runtime-dir /Users/matthew.zhao/.codex/epiagentbench-v31-supervisors/preflight \
  --authentication-key /Users/matthew.zhao/.codex/epiagentbench-v31-secrets/panel-auth.key

/usr/bin/env -i HOME=/Users/matthew.zhao/.codex/epiagentbench-v31-provider-free-home LC_ALL=C.UTF-8 LOGNAME=matthew.zhao PATH=/usr/bin:/bin:/usr/sbin:/sbin SHELL=/bin/zsh TMPDIR=/Users/matthew.zhao/.codex/epiagentbench-v31-provider-free-tmp USER=matthew.zhao __CF_USER_TEXT_ENCODING=0x1F5:0x0:0x0 \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python -I -S -B \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v31-execution-worktree/examples/run_persistent_panel_supervisor.py audit \
  --runtime-dir /Users/matthew.zhao/.codex/epiagentbench-v31-supervisors/preflight \
  --authentication-key /Users/matthew.zhao/.codex/epiagentbench-v31-secrets/panel-auth.key

/usr/bin/env -i HOME=/Users/matthew.zhao/.codex/epiagentbench-v31-provider-free-home LC_ALL=C.UTF-8 LOGNAME=matthew.zhao PATH=/usr/bin:/bin:/usr/sbin:/sbin SHELL=/bin/zsh TMPDIR=/Users/matthew.zhao/.codex/epiagentbench-v31-provider-free-tmp USER=matthew.zhao __CF_USER_TEXT_ENCODING=0x1F5:0x0:0x0 \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python -I -S -B \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v31-execution-worktree/examples/run_persistent_panel_supervisor.py status \
  --runtime-dir /Users/matthew.zhao/.codex/epiagentbench-v31-supervisors/preflight \
  --authentication-key /Users/matthew.zhao/.codex/epiagentbench-v31-secrets/panel-auth.key

/usr/bin/env -i HOME=/Users/matthew.zhao/.codex/epiagentbench-v31-provider-free-home LC_ALL=C.UTF-8 LOGNAME=matthew.zhao PATH=/usr/bin:/bin:/usr/sbin:/sbin SHELL=/bin/zsh TMPDIR=/Users/matthew.zhao/.codex/epiagentbench-v31-provider-free-tmp USER=matthew.zhao __CF_USER_TEXT_ENCODING=0x1F5:0x0:0x0 \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python -I -S -B \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v31-execution-worktree/examples/run_persistent_panel_supervisor.py start \
  --runtime-dir /Users/matthew.zhao/.codex/epiagentbench-v31-supervisors/preflight \
  --authentication-key /Users/matthew.zhao/.codex/epiagentbench-v31-secrets/panel-auth.key
```

Only after all six profiles pass and both authenticated status and the closed
public preflight receipt independently validate that pass may production be
prepared. The production runtime must still be absent. Execute each production
command once and in this order:

```sh
/usr/bin/env -i HOME=/Users/matthew.zhao/.codex/epiagentbench-v31-provider-free-home LC_ALL=C.UTF-8 LOGNAME=matthew.zhao PATH=/usr/bin:/bin:/usr/sbin:/sbin SHELL=/bin/zsh TMPDIR=/Users/matthew.zhao/.codex/epiagentbench-v31-provider-free-tmp USER=matthew.zhao __CF_USER_TEXT_ENCODING=0x1F5:0x0:0x0 \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python -I -S -B \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v31-production-worktree/examples/run_persistent_panel_supervisor.py generate \
  --operation production \
  --runtime-dir /Users/matthew.zhao/.codex/epiagentbench-v31-supervisors/production \
  --repository-root /Users/matthew.zhao/.codex/epiagentbench-50x6-v31-production-worktree \
  --python-executable /Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python \
  --runtime-cache-dir /Users/matthew.zhao/.codex/epiagentbench-v31-runtime-cache \
  --authentication-key /Users/matthew.zhao/.codex/epiagentbench-v31-secrets/panel-auth.key \
  --claude-secure-storage-dir /Users/matthew.zhao/.codex/epiagentbench-v31-credentials/claude \
  --codex-secure-storage-dir /Users/matthew.zhao/.codex/epiagentbench-v31-credentials/codex \
  --private-state /Users/matthew.zhao/.codex/epiagentbench-v31-state/development-matched-50x6-v31.private.json \
  --public-manifest /Users/matthew.zhao/.codex/epiagentbench-50x6-v31-production-worktree/results/development-matched-50x6-v31.manifest.json \
  --public-results /Users/matthew.zhao/.codex/epiagentbench-50x6-v31-production-worktree/results/development-matched-50x6-v31.json \
  --cursor-keychain-service epiagentbench-cursor-v31 \
  --cursor-keychain-account matthew.zhao

/usr/bin/env -i HOME=/Users/matthew.zhao/.codex/epiagentbench-v31-provider-free-home LC_ALL=C.UTF-8 LOGNAME=matthew.zhao PATH=/usr/bin:/bin:/usr/sbin:/sbin SHELL=/bin/zsh TMPDIR=/Users/matthew.zhao/.codex/epiagentbench-v31-provider-free-tmp USER=matthew.zhao __CF_USER_TEXT_ENCODING=0x1F5:0x0:0x0 \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python -I -S -B \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v31-production-worktree/examples/run_persistent_panel_supervisor.py install \
  --runtime-dir /Users/matthew.zhao/.codex/epiagentbench-v31-supervisors/production \
  --authentication-key /Users/matthew.zhao/.codex/epiagentbench-v31-secrets/panel-auth.key

/usr/bin/env -i HOME=/Users/matthew.zhao/.codex/epiagentbench-v31-provider-free-home LC_ALL=C.UTF-8 LOGNAME=matthew.zhao PATH=/usr/bin:/bin:/usr/sbin:/sbin SHELL=/bin/zsh TMPDIR=/Users/matthew.zhao/.codex/epiagentbench-v31-provider-free-tmp USER=matthew.zhao __CF_USER_TEXT_ENCODING=0x1F5:0x0:0x0 \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python -I -S -B \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v31-production-worktree/examples/run_persistent_panel_supervisor.py audit \
  --runtime-dir /Users/matthew.zhao/.codex/epiagentbench-v31-supervisors/production \
  --authentication-key /Users/matthew.zhao/.codex/epiagentbench-v31-secrets/panel-auth.key

/usr/bin/env -i HOME=/Users/matthew.zhao/.codex/epiagentbench-v31-provider-free-home LC_ALL=C.UTF-8 LOGNAME=matthew.zhao PATH=/usr/bin:/bin:/usr/sbin:/sbin SHELL=/bin/zsh TMPDIR=/Users/matthew.zhao/.codex/epiagentbench-v31-provider-free-tmp USER=matthew.zhao __CF_USER_TEXT_ENCODING=0x1F5:0x0:0x0 \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python -I -S -B \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v31-production-worktree/examples/run_persistent_panel_supervisor.py status \
  --runtime-dir /Users/matthew.zhao/.codex/epiagentbench-v31-supervisors/production \
  --authentication-key /Users/matthew.zhao/.codex/epiagentbench-v31-secrets/panel-auth.key

/usr/bin/env -i HOME=/Users/matthew.zhao/.codex/epiagentbench-v31-provider-free-home LC_ALL=C.UTF-8 LOGNAME=matthew.zhao PATH=/usr/bin:/bin:/usr/sbin:/sbin SHELL=/bin/zsh TMPDIR=/Users/matthew.zhao/.codex/epiagentbench-v31-provider-free-tmp USER=matthew.zhao __CF_USER_TEXT_ENCODING=0x1F5:0x0:0x0 \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python -I -S -B \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v31-production-worktree/examples/run_persistent_panel_supervisor.py start \
  --runtime-dir /Users/matthew.zhao/.codex/epiagentbench-v31-supervisors/production \
  --authentication-key /Users/matthew.zhao/.codex/epiagentbench-v31-secrets/panel-auth.key
```

No step may be inferred from a placeholder. No runtime generation, provider
call, or private write is authorized by this document.

## Terminal rules

- Never restart, resume, or mutate V30 or any earlier version.
- Never reuse a V30 or earlier key, cohort, cache, credential, state, checkout,
  supervisor, Keychain service, claim, or output destination.
- Never fill a commit placeholder from local or provisional state.
- Never launch from an ambient interpreter or PATH-selected provider binary.
- Never start either V31 supervisor twice.
- Never retry or repair the provider-free bootstrap, either receipt candidate,
  publication, or verification after any failed, interrupted, or ambiguous
  boundary.
- Never publish or inspect protected provider or benchmark data before the
  frozen final-release gates permit it.
