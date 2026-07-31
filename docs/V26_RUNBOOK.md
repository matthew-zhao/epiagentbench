# EpiAgentBench V26 execution runbook

> [!CAUTION]
> **PROVIDER-FREE PREPARATION ONLY — NO V26 EXECUTION IS AUTHORIZED.**
>
> The current operator decision covers only sections 1–9: source publication,
> the provider-free runtime receipt, fresh private preparation, and the public
> manifest. It does not authorize authentication, a provider process, spend, a
> supervisor, a preflight, production, or a model call. Stop after publishing
> the manifest. Every later phase requires a separate operator decision and
> the exact manifest-bound acknowledgement below.

V26 supersedes the terminal V25 provider-free preparation attempt. V25 used a
credential-stripped `env -i` process, but its sanitized PATH also omitted the
installed Cursor CLI directory, so static CLI identity discovery failed before
the scientific runtime contract or either Starsim smoke began. No runtime
receipt, private artifact, authentication helper, provider process, supervisor,
or model call was created. Those facts are preserved in the
[V25 supersession record](../results/development-matched-50x6-v25.superseded.json)
and [historical runbook](V25_RUNBOOK.md).

V26 closes that gap with a source-owned provider CLI resolver. The process
PATH is fixed to system tools only; provider discovery separately considers
fixed system/Homebrew roles and the current account's `.local/bin` role without
consulting environment `PATH` or `HOME`. The public receipt discloses only
the CLI name, generic discovery role, entrypoint kind, execution format,
declared external-runtime policy, exact installation file count and byte
count, and path-free executable, installation, entrypoint, ancestry, and root
hashes—not account names, home directories, or resolved paths. Preparation
also runs with an exact closed environment and fresh empty owner-only HOME and
TMPDIR, and binds the path-free environment contract into the runtime identity.

V26 supersedes the unused V24 control-plane milestone at the operator's
direction. V24 produced no runtime receipt, manifest, key, cohort, credential
namespace, private state, authentication ceremony, supervisor, provider
process, or model call; its public facts are preserved in the
[V24 supersession record](../results/development-matched-50x6-v24.superseded.json)
and [historical runbook](V24_RUNBOOK.md).

V26 retains V24's fix for the terminal V23 preflight. All six V23 preflight profiles
completed, but the intentionally dependency-free outer release worker then
tried to import Starsim and re-inventory installed scientific distributions.
Those are live pre-provider checks and cannot run under the worker's deliberate
`-I -S` no-site boundary. The worker safely emitted only
`release_validation_failed`; no score, trace, hidden episode identifier, raw
provider output, or exception text was released. V23 made six model calls,
released no passing preflight receipt, started no production assignment, and
is non-resumable. Its public runtime, manifest, authentication receipt, and
terminal record remain preserved in the
[V23 supersession record](../results/development-matched-50x6-v23.superseded.json)
and [historical runbook](V23_RUNBOOK.md).

V26 keeps V24's scientific cohort construction, exact live checks before and
after provider calls, at-most-once execution, authenticated LaunchAgent
boundary, environment restoration, create-once publication controls, ordered
pre-model ledger, and exact isolated `spawn` bootstrap. It changes only the
post-completion release boundary: the no-site worker validates the already
sealed runtime hashes, freshly re-hashes the provider-free tracked source
surface, and validates the private preparation binding, cohort manifest, and
every private pack without re-importing scientific packages. Safe owner-only
cache content evolution is permitted only inside the sealed cache topology.
Release is serialized by the owner control lock: premature and lock-contention
requests are read-only, while a failure after `release_pending` is classified
before that lock is released. Any recorded refusal is one finite authenticated
code; arbitrary exception text is forbidden.

V26 uses a three-commit, provider-free preparation protocol:

1. publish and pin the V26 control-plane code;
2. at that exact clean commit, run the scientific-runtime preflight twice
   with the pinned V5 Python under `-I -S -B`;
3. compare the two receipts byte-for-byte;
4. commit and push the exact public runtime receipt through GitButler;
5. materialize a fresh clean checkout at the runtime-receipt commit;
6. re-attest the tracked receipt before any private write;
7. create the fresh key and empty credential directories, burn the canonical
   create-once freeze claim, freeze one fresh cohort, and prepare exactly once;
8. validate, commit, push, and pin only the public manifest;
9. stop before authorization.

The first two published commits are therefore exactly the code commit followed
by the byte-identical runtime-receipt commit. No V26 key, freeze claim, cohort,
credential namespace, private state, or manifest may exist before the second
commit is published and re-attested. The manifest is published afterward as a
third commit, and this phase stops before authorization. It makes no
authentication, provider, or model call.

The runtime preflight is substantive. It runs a hardcoded three-person,
four-day long-term-care (LTC) scenario through the real Starsim-backed LTC
engine twice per branch. In the no-action branch, one seeded resident
deterministically transmits to one staff member across the sole direct-care
edge. The counterfactual has the same opening and is matched through day one,
then a day-one contact stop prevents that transmission. This proves the
runtime can execute and distinguish the fixed causal branches; it is a
capability smoke, not calibration evidence, a biological effect estimate, or
a benchmark score. The preflight also binds:

- exact Starsim 3.5.1 and the actual installed bytes of every declared
  scientific distribution, in addition to its package metadata;
- the exact pinned V5 interpreter launched with `-I -S -B`, plus an
  isolated, hook-free bootstrap that appends only the attested repository
  `src` and V5 virtual-environment `site-packages` after the standard library
  in the parent and re-attests the exact inherited tail during `spawn` replay;
- a real file-entrypoint broker smoke covering all five public causal
  families at public seeds `0`, `7`, and `2**31 - 2`, twice serially
  (30 trusted evaluator starts total), with identical aggregate public
  transcript digests and complete pathname-socket cleanup;
- the clean source and CLI contracts at the pinned commit;
- a fresh runtime-cache v3 contract whose normalized, current-user `0700`
  root contains only exact current-user `0700` children `matplotlib`, `numba`,
  and `xdg`; below them the closed inventory contains at most 10,000
  descendants total (directories plus regular files), with owner-only,
  nonsymlinked, same-filesystem entries, single-link regular files of at most
  512 MiB each, and at most 4 GiB of regular-file content in total;
- an internally installed `umask 077` around scientific runtime and cache
  work, followed by exact restoration of the caller's prior mask; and
- the exact six cache environment variables later sealed into the
  LaunchAgent.

The public receipt is deliberately path-free. It exposes the Python target
content hash, entrypoint kind, and an opaque hash of the full Python
entrypoint/bootstrap binding. It exposes only an opaque hash of the full cache
contract. The raw Python binding is transient during preflight and is later
recomputed and sealed in the authenticated owner-only LaunchAgent config; it
is never stored in a public artifact. The full cache paths, environment,
device/inode/UID metadata, modes, top-level-directory and regular-file mtimes,
and inventory are retained in the authenticated private panel state and later
in that config. Path-free
scientific module-origin identities are the narrower public exception: they
contain only a distribution-relative file name and content hash, never an
absolute path or filesystem topology.

These controls constrain ordinary mutation but do not claim to defeat a
privileged same-user or administrator process that can perform a perfectly
timed swap-and-restore (an ABA change) between two filesystem attestations.
The trusted boundary therefore includes the local kernel, filesystem, process
isolation, OS loader and fixed system tools, and an otherwise quiescent
operator account for the duration of each command. The attested executable
ancestry rejects every world-writable component; group-writable ancestry is
permitted only for the declared Homebrew administrator role and is therefore
part of the trusted administrator boundary. Run preparation only on that
trusted, quiescent host. Any evidence of an unexpected same-UID process,
administrator intervention, filesystem remount, loader/tool substitution, or
suspend/resume ambiguity is terminal for the version; do not treat a later
matching hash as proof that no intervening substitution occurred.

The preflight launches no provider or authentication helper and requires no
key, cohort, credential directory, private state, or schedule.

## Frozen V26 identifiers

| Surface | V26 value |
|---|---|
| Panel and cohort | `development-matched-50x6-v26` |
| Top-level schema | `development_matched_panel_v26` |
| Runtime receipt | `results/development-matched-50x6-v26.runtime.json` |
| Required Python launch path | `${EPIAGENTBENCH_PYTHON:?set the absolute isolated EpiAgentBench Python path}` |
| Required Python flags | `-I -S -B` |
| Required Starsim | `3.5.1` |
| Preparation runtime receipt | `epiagentbench.preparation_runtime_preflight.v4` |
| Bound preparation runtime | `epiagentbench.bound_preparation_runtime.v3` |
| Scientific smoke | `epiagentbench.preparation_runtime_smoke.v2` |
| Broker-startup smoke | `epiagentbench.preparation_episode_startup_smoke.v1` |
| Persistent-supervisor contract | `epiagentbench.persistent_supervisor_contract.v11` |
| Authenticated worker status | `epiagentbench.launchd_worker_status.v5` |
| Execution-context protocol | `persistent-supervisor-v7` |
| LaunchAgent config | `epiagentbench.launchd_agent.v13` |
| Authentication setup | `epiagentbench.authentication_setup.v4` |
| Assignments | 50 episodes × 6 profiles = 300 |
| Per-call timeout | 1,800 seconds |
| Claude per-call ceiling | $5 |
| V26 current-run Claude ceiling | $510 (102 Claude calls × $5) |
| Prior conservative Claude ceiling | $90 |
| Cumulative acknowledgement ceiling | $600 ($510 + $90) |
| Required acknowledgement SHA-256 | `sha256:bf3569ffd92b1c06a9566dd673f896d453bd03cb44cd62fa21c2becf90baea2c` |
| Codex/Cursor ceiling | unbounded |
| Cursor Keychain service | `epiagentbench-cursor-v26` |

V15 adds zero dollars to the prior ceiling because it launched no provider or
authentication helper and made no model call. V16 adds a conservative $5 for
its one started-not-finished Claude preflight call. V17 adds zero dollars
because its single control request was refused before any provider or model
process. V18 adds a conservative $5 because its legacy early marker cannot
prove that the first Claude model-bearing process never started, even though
the offline audit strongly indicates a non-model CLI readiness timeout. V19
adds zero dollars because authentication setup ended before any model-bearing
call and no Claude authentication helper started. V20 and V21 each add zero
dollars because their durable markers prove that their first preflight
failures happened before model invocation. V22 adds zero dollars because its
interrupted foreground authentication ceremony started no model call and
never reached preflight or production. V23 adds a conservative $10 for its
two Claude preflight calls; it started no production assignment. V24 adds zero
dollars because it remained a control-plane-only milestone and created no
runtime, private preparation, authentication, provider, or model process. V25
adds zero dollars because its provider-free preparation stopped during static
CLI discovery before any provider or model process.

## Fresh V26 paths

```text
$HOME/.codex/epiagentbench-50x6-v26-runtime-worktree
$HOME/.codex/epiagentbench-50x6-v26-prepare-worktree
$HOME/.codex/epiagentbench-v26-runtime-cache
$HOME/.codex/epiagentbench-v26-runtime-receipt-staging
$HOME/.codex/epiagentbench-v26-cohort
$HOME/.codex/epiagentbench-v26-secrets/panel-auth.key
$HOME/.codex/epiagentbench-v26-secrets/.development-matched-50x6-v26.cohort-freeze-claim.v1.json
$HOME/.codex/epiagentbench-v26-secrets/.development-matched-50x6-v26.cohort-freeze-completion.v1.json
$HOME/.codex/epiagentbench-v26-state/development-matched-50x6-v26.private.json
$HOME/.codex/epiagentbench-v26-credentials/claude
$HOME/.codex/epiagentbench-v26-credentials/codex
$HOME/.codex/epiagentbench-v26-supervisors/preflight
$HOME/.codex/epiagentbench-v26-supervisors/production
```

The five public destinations are:

```text
results/development-matched-50x6-v26.runtime.json
results/development-matched-50x6-v26.manifest.json
results/development-matched-50x6-v26.authentication.json
results/development-matched-50x6-v26.preflight.json
results/development-matched-50x6-v26.json
```

Every shell block below is intentionally self-contained: it declares every
path or prior published commit it consumes. Every Python CLI/supervisor
invocation uses the approved V5 virtual-environment interpreter with
`-I -S -B`, and every block that can load the scientific runtime supplies the
exact bound cache root from which the CLI installs its cache environment.
Never replace `V26_PYTHON` with `python`, `python3`, a PATH lookup, or another
virtual environment. Never use `PYTHONPATH`; the isolated scripts build and
re-attest their only permitted import paths without executing `site`, `.pth`,
`sitecustomize`, or `usercustomize`.

## 1. Publish and pin the V26 control plane

Use the GitButler-managed primary workspace to commit and push the V26
control-plane changes on `codex/v26-runtime-preflight`. Never use `git push`
and never publish a private artifact. Record the exact 40-hex remote commit as
`V26_CONTROL_COMMIT`.

This first commit must not contain any V26 runtime receipt, manifest,
authentication receipt, preflight receipt, final result, key, cohort, private
state, credential directory, or supervisor runtime.

## 2. Validate the clean control-plane checkout

After the GitButler push, use an operator-approved GitButler-compatible
workflow to materialize a fresh clean checkout at the exact control-plane
commit. Set `V26_RUNTIME_CHECKOUT` to its absolute canonical path, then run
this validation block from the repository's primary checkout. The block is
read-only; it does not create or mutate a Git checkout.

Every provider-free block runs in a subshell so its fixed outer `PATH` cannot
hide GitButler from a later operator command. Its `v26_git` wrapper invokes the
fixed system Git with an empty process environment and disables system/global
configuration, hooks, filesystem monitors, untracked-cache helpers, submodule
recursion, credential helpers and prompts, optional locks, and every transport
except the fixed HTTPS origin used for read-only remote attestation. Do not
replace `v26_git` with ambient `git`; Git publication remains GitButler-only.

```bash
(
set -euo pipefail
PATH='/usr/bin:/bin:/usr/sbin:/sbin'
export PATH
v26_git() {
  /usr/bin/env -i \
    HOME=/var/empty \
    LC_ALL=C \
    PATH=/usr/bin:/bin:/usr/sbin:/sbin \
    TMPDIR=/private/tmp \
    GIT_CONFIG_NOSYSTEM=1 \
    GIT_CONFIG_SYSTEM=/dev/null \
    GIT_CONFIG_GLOBAL=/dev/null \
    GIT_OPTIONAL_LOCKS=0 \
    GIT_TERMINAL_PROMPT=0 \
    GIT_ASKPASS=/usr/bin/false \
    SSH_ASKPASS=/usr/bin/false \
    /usr/bin/git --no-pager \
      -c core.hooksPath=/dev/null \
      -c core.fsmonitor=false \
      -c core.untrackedCache=false \
      -c diff.ignoreSubmodules=all \
      -c status.submoduleSummary=false \
      -c submodule.recurse=false \
      -c fetch.recurseSubmodules=false \
      -c credential.helper= \
      -c credential.interactive=never \
      -c protocol.allow=never \
      -c protocol.https.allow=always \
      "$@"
}
V26_PYTHON="${EPIAGENTBENCH_PYTHON:?set the absolute isolated EpiAgentBench Python path}"
V26_RUNTIME_CACHE="$HOME/.codex/epiagentbench-v26-runtime-cache"
V26_EXPECTED_COMMIT="${V26_CONTROL_COMMIT:?set the exact published control-plane commit}"
V26_REMOTE_REF='refs/heads/codex/v26-runtime-preflight'
V26_ORIGIN_URL='https://github.com/matthew-zhao/epiagentbench.git'
V26_RUNTIME_CHECKOUT="${V26_RUNTIME_CHECKOUT:?set the absolute canonical path to the fresh control-plane checkout}"
[[ "$V26_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
test -x "$V26_PYTHON"
test "$(v26_git ls-remote "$V26_ORIGIN_URL" "$V26_REMOTE_REF" | /usr/bin/cut -f1)" = \
  "$V26_EXPECTED_COMMIT"
test -d "$V26_RUNTIME_CHECKOUT"
test ! -L "$V26_RUNTIME_CHECKOUT"
test "$(cd "$V26_RUNTIME_CHECKOUT" && pwd -P)" = "$V26_RUNTIME_CHECKOUT"
cd "$V26_RUNTIME_CHECKOUT"
test "$(v26_git rev-parse HEAD)" = "$V26_EXPECTED_COMMIT"
test -z "$(v26_git status --porcelain=v1 --untracked-files=all --ignore-submodules=all)"
)
```

## 3. Prove freshness and create separate cache and staging roots

All five public outputs and all private V26 namespaces must be absent before
the cache is created. The cache is runtime state, not a cohort or credential
namespace. Its v3 contract permits exactly three children at the root:
`matplotlib`, `numba`, and `xdg`. Receipt bytes, command summaries, and all
other operator output therefore go into a distinct owner-only staging
directory that never overlaps the cache. Two empty owner-only children serve
as the provider-free process HOME and TMPDIR. They are never used for receipt
or operator output and must remain empty after every command.

```bash
(
set -euo pipefail
PATH='/usr/bin:/bin:/usr/sbin:/sbin'
export PATH
umask 077
v26_git() {
  /usr/bin/env -i \
    HOME=/var/empty LC_ALL=C \
    PATH=/usr/bin:/bin:/usr/sbin:/sbin TMPDIR=/private/tmp \
    GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_SYSTEM=/dev/null \
    GIT_CONFIG_GLOBAL=/dev/null GIT_OPTIONAL_LOCKS=0 \
    GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/usr/bin/false \
    SSH_ASKPASS=/usr/bin/false \
    /usr/bin/git --no-pager \
      -c core.hooksPath=/dev/null -c core.fsmonitor=false \
      -c core.untrackedCache=false -c diff.ignoreSubmodules=all \
      -c status.submoduleSummary=false -c submodule.recurse=false \
      -c fetch.recurseSubmodules=false -c credential.helper= \
      -c credential.interactive=never -c protocol.allow=never \
      -c protocol.https.allow=always "$@"
}
V26_PYTHON="${EPIAGENTBENCH_PYTHON:?set the absolute isolated EpiAgentBench Python path}"
V26_RUNTIME_CACHE="$HOME/.codex/epiagentbench-v26-runtime-cache"
V26_RUNTIME_STAGING="$HOME/.codex/epiagentbench-v26-runtime-receipt-staging"
V26_CLEAN_HOME="$V26_RUNTIME_STAGING/clean-home"
V26_CLEAN_TMP="$V26_RUNTIME_STAGING/clean-tmp"
V26_EXPECTED_COMMIT="${V26_CONTROL_COMMIT:?set the exact published control-plane commit}"
V26_RUNTIME_CHECKOUT="${V26_RUNTIME_CHECKOUT:?set the absolute canonical path to the fresh control-plane checkout}"
[[ "$V26_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
test -x "$V26_PYTHON"
cd "$V26_RUNTIME_CHECKOUT"
test "$(v26_git rev-parse HEAD)" = "$V26_EXPECTED_COMMIT"
test -z "$(v26_git status --porcelain=v1 --untracked-files=all --ignore-submodules=all)"
for candidate_path in \
  "$HOME/.codex/epiagentbench-v26-runtime-cache" \
  "$HOME/.codex/epiagentbench-v26-runtime-receipt-staging" \
  "$HOME/.codex/epiagentbench-v26-secrets" \
  "$HOME/.codex/epiagentbench-v26-state" \
  "$HOME/.codex/epiagentbench-v26-credentials" \
  "$HOME/.codex/epiagentbench-v26-supervisors" \
  "$HOME/.codex/epiagentbench-v26-cohort" \
  "results/development-matched-50x6-v26.runtime.json" \
  "results/development-matched-50x6-v26.manifest.json" \
  "results/development-matched-50x6-v26.authentication.json" \
  "results/development-matched-50x6-v26.preflight.json" \
  "results/development-matched-50x6-v26.json"; do
  if [ -e "$candidate_path" ] || [ -L "$candidate_path" ]; then
    echo "Refusing occupied V26 path: $candidate_path" >&2
    exit 1
  fi
done
mkdir "$V26_RUNTIME_CACHE"
mkdir "$V26_RUNTIME_STAGING"
mkdir \
  "$V26_CLEAN_HOME" \
  "$V26_CLEAN_TMP" \
  "$V26_RUNTIME_CACHE/matplotlib" \
  "$V26_RUNTIME_CACHE/numba" \
  "$V26_RUNTIME_CACHE/xdg"
chmod 700 \
  "$V26_RUNTIME_CACHE" \
  "$V26_RUNTIME_STAGING" \
  "$V26_CLEAN_HOME" \
  "$V26_CLEAN_TMP" \
  "$V26_RUNTIME_CACHE/matplotlib" \
  "$V26_RUNTIME_CACHE/numba" \
  "$V26_RUNTIME_CACHE/xdg"
V26_SCRATCH_CONTENT="$(/usr/bin/find \
  "$V26_CLEAN_HOME" -mindepth 1 -print -quit)"
test -z "$V26_SCRATCH_CONTENT"
V26_SCRATCH_CONTENT="$(/usr/bin/find \
  "$V26_CLEAN_TMP" -mindepth 1 -print -quit)"
test -z "$V26_SCRATCH_CONTENT"
)
```

## 4. Produce the provider-free runtime receipt twice

Both commands run at the exact control-plane commit and write outside the
repository. A byte difference is terminal for this preparation attempt. The
entrypoint exact-compares the eight-variable provider-free environment on
entry and again in its finalization path; the shell independently replays that
closed environment and proves the dedicated HOME and TMPDIR are still empty
after every provider-free command.

```bash
(
set -euo pipefail
PATH='/usr/bin:/bin:/usr/sbin:/sbin'
export PATH
umask 077
v26_git() {
  /usr/bin/env -i \
    HOME=/var/empty LC_ALL=C \
    PATH=/usr/bin:/bin:/usr/sbin:/sbin TMPDIR=/private/tmp \
    GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_SYSTEM=/dev/null \
    GIT_CONFIG_GLOBAL=/dev/null GIT_OPTIONAL_LOCKS=0 \
    GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/usr/bin/false \
    SSH_ASKPASS=/usr/bin/false \
    /usr/bin/git --no-pager \
      -c core.hooksPath=/dev/null -c core.fsmonitor=false \
      -c core.untrackedCache=false -c diff.ignoreSubmodules=all \
      -c status.submoduleSummary=false -c submodule.recurse=false \
      -c fetch.recurseSubmodules=false -c credential.helper= \
      -c credential.interactive=never -c protocol.allow=never \
      -c protocol.https.allow=always "$@"
}
V26_PYTHON="${EPIAGENTBENCH_PYTHON:?set the absolute isolated EpiAgentBench Python path}"
V26_RUNTIME_CACHE="$HOME/.codex/epiagentbench-v26-runtime-cache"
V26_RUNTIME_STAGING="$HOME/.codex/epiagentbench-v26-runtime-receipt-staging"
V26_CLEAN_HOME="$V26_RUNTIME_STAGING/clean-home"
V26_CLEAN_TMP="$V26_RUNTIME_STAGING/clean-tmp"
V26_ACCOUNT_NAME="$(/usr/bin/id -un)"
V26_ACCOUNT_SHELL="$(/usr/bin/dscl . -read \
  "/Users/$V26_ACCOUNT_NAME" UserShell | /usr/bin/awk '{print $2}')"
V26_CF_USER_TEXT_ENCODING="$(/usr/bin/printf \
  '0x%X:0x0:0x0' "$(/usr/bin/id -u)")"
V26_PROVIDER_FREE_ENV=(
  /usr/bin/env -i
  "HOME=$V26_CLEAN_HOME"
  "LC_ALL=C.UTF-8"
  "LOGNAME=$V26_ACCOUNT_NAME"
  "PATH=/usr/bin:/bin:/usr/sbin:/sbin"
  "SHELL=$V26_ACCOUNT_SHELL"
  "TMPDIR=$V26_CLEAN_TMP"
  "USER=$V26_ACCOUNT_NAME"
  "__CF_USER_TEXT_ENCODING=$V26_CF_USER_TEXT_ENCODING"
)
v26_provider_free_python() {
  "${V26_PROVIDER_FREE_ENV[@]}" "$V26_PYTHON" -I -S -B "$@"
}
v26_assert_provider_free_environment() {
  local actual expected
  actual="$("${V26_PROVIDER_FREE_ENV[@]}" /usr/bin/env | /usr/bin/sort)"
  expected="$(/usr/bin/printf '%s\n' \
    "HOME=$V26_CLEAN_HOME" \
    "LC_ALL=C.UTF-8" \
    "LOGNAME=$V26_ACCOUNT_NAME" \
    "PATH=/usr/bin:/bin:/usr/sbin:/sbin" \
    "SHELL=$V26_ACCOUNT_SHELL" \
    "TMPDIR=$V26_CLEAN_TMP" \
    "USER=$V26_ACCOUNT_NAME" \
    "__CF_USER_TEXT_ENCODING=$V26_CF_USER_TEXT_ENCODING" |
    /usr/bin/sort)"
  test "$actual" = "$expected"
}
v26_assert_clean_scratch() {
  test -d "$V26_CLEAN_HOME"
  test ! -L "$V26_CLEAN_HOME"
  test -d "$V26_CLEAN_TMP"
  test ! -L "$V26_CLEAN_TMP"
  test "$(/usr/bin/stat -f '%Lp' "$V26_CLEAN_HOME")" = 700
  test "$(/usr/bin/stat -f '%Lp' "$V26_CLEAN_TMP")" = 700
  local observed
  observed="$(/usr/bin/find "$V26_CLEAN_HOME" -mindepth 1 -print -quit)" ||
    return 1
  test -z "$observed"
  observed="$(/usr/bin/find "$V26_CLEAN_TMP" -mindepth 1 -print -quit)" ||
    return 1
  test -z "$observed"
}
V26_EXPECTED_COMMIT="${V26_CONTROL_COMMIT:?set the exact published control-plane commit}"
V26_RUNTIME_CHECKOUT="${V26_RUNTIME_CHECKOUT:?set the absolute canonical path to the fresh control-plane checkout}"
V26_RUNTIME_ONE="$V26_RUNTIME_STAGING/preflight-1.json"
V26_RUNTIME_TWO="$V26_RUNTIME_STAGING/preflight-2.json"
[[ "$V26_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
cd "$V26_RUNTIME_CHECKOUT"
test "$(v26_git rev-parse HEAD)" = "$V26_EXPECTED_COMMIT"
test -z "$(v26_git status --porcelain=v1 --untracked-files=all --ignore-submodules=all)"
test -x "$V26_PYTHON"
test -d "$V26_RUNTIME_STAGING"
test ! -L "$V26_RUNTIME_STAGING"
test "$(/usr/bin/stat -f '%Lp' "$V26_RUNTIME_STAGING")" = 700
test ! -e "$V26_RUNTIME_ONE"
test ! -L "$V26_RUNTIME_ONE"
test ! -e "$V26_RUNTIME_TWO"
test ! -L "$V26_RUNTIME_TWO"
v26_assert_provider_free_environment
v26_assert_clean_scratch
v26_provider_free_python \
  examples/run_development_matched_panel.py \
  preflight-preparation-runtime \
  --expected-benchmark-base-commit "$V26_EXPECTED_COMMIT" \
  --runtime-cache-dir "$V26_RUNTIME_CACHE" \
  --public-runtime-receipt "$V26_RUNTIME_ONE"
v26_assert_provider_free_environment
v26_assert_clean_scratch
v26_provider_free_python \
  examples/run_development_matched_panel.py \
  preflight-preparation-runtime \
  --expected-benchmark-base-commit "$V26_EXPECTED_COMMIT" \
  --runtime-cache-dir "$V26_RUNTIME_CACHE" \
  --public-runtime-receipt "$V26_RUNTIME_TWO"
v26_assert_provider_free_environment
v26_assert_clean_scratch
test -f "$V26_RUNTIME_ONE"
test ! -L "$V26_RUNTIME_ONE"
test -f "$V26_RUNTIME_TWO"
test ! -L "$V26_RUNTIME_TWO"
test "$(/usr/bin/stat -f '%Lp' "$V26_RUNTIME_ONE")" = 644
test "$(/usr/bin/stat -f '%Lp' "$V26_RUNTIME_TWO")" = 644
cmp -s "$V26_RUNTIME_ONE" "$V26_RUNTIME_TWO"
test "$(v26_git rev-parse HEAD)" = "$V26_EXPECTED_COMMIT"
test -z "$(v26_git status --porcelain=v1 --untracked-files=all --ignore-submodules=all)"
for candidate_path in \
  "$HOME/.codex/epiagentbench-v26-secrets" \
  "$HOME/.codex/epiagentbench-v26-state" \
  "$HOME/.codex/epiagentbench-v26-credentials" \
  "$HOME/.codex/epiagentbench-v26-supervisors" \
  "$HOME/.codex/epiagentbench-v26-cohort" \
  "results/development-matched-50x6-v26.runtime.json" \
  "results/development-matched-50x6-v26.manifest.json" \
  "results/development-matched-50x6-v26.authentication.json" \
  "results/development-matched-50x6-v26.preflight.json" \
  "results/development-matched-50x6-v26.json"; do
  if [ -e "$candidate_path" ] || [ -L "$candidate_path" ]; then
    echo "A V26 artifact appeared during provider-free preflight" >&2
    exit 1
  fi
done
v26_assert_provider_free_environment
v26_assert_clean_scratch
)
```

The receipt is closed-schema public data. It contains aggregate smoke output,
path-free scientific identities, the path-free CLI installation fingerprints
described above (including exact file and byte counts), opaque Python/cache
binding hashes, and explicit zero provider/authentication process counters. It contains no raw
Python entrypoint/bootstrap binding, cache contract, absolute path,
device/inode/UID metadata, private random seed, episode identifier, schedule,
credential, prompt, observation, provider output, trace, or score.

The private cache binding seals every relative path and every entry's owner,
mode, device, and inode. It additionally seals every regular file's byte hash,
size, link count, and modification time. Nested-directory modification times
are intentionally excluded: Numba refreshes those timestamps while reading an
otherwise byte-identical cache. Directory topology and identity remain
sealed, and any cache-file byte or permission change still fails verification.

## 5. Commit and push the exact runtime receipt through GitButler

Copy the already-compared bytes to the GitButler primary workspace. Do not
regenerate the receipt there.

```bash
(
set -euo pipefail
PATH='/usr/bin:/bin:/usr/sbin:/sbin'
export PATH
umask 077
v26_git() {
  /usr/bin/env -i \
    HOME=/var/empty LC_ALL=C \
    PATH=/usr/bin:/bin:/usr/sbin:/sbin TMPDIR=/private/tmp \
    GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_SYSTEM=/dev/null \
    GIT_CONFIG_GLOBAL=/dev/null GIT_OPTIONAL_LOCKS=0 \
    GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/usr/bin/false \
    SSH_ASKPASS=/usr/bin/false \
    /usr/bin/git --no-pager \
      -c core.hooksPath=/dev/null -c core.fsmonitor=false \
      -c core.untrackedCache=false -c diff.ignoreSubmodules=all \
      -c status.submoduleSummary=false -c submodule.recurse=false \
      -c fetch.recurseSubmodules=false -c credential.helper= \
      -c credential.interactive=never -c protocol.allow=never \
      -c protocol.https.allow=always "$@"
}
V26_PYTHON="${EPIAGENTBENCH_PYTHON:?set the absolute isolated EpiAgentBench Python path}"
V26_RUNTIME_CACHE="$HOME/.codex/epiagentbench-v26-runtime-cache"
V26_RUNTIME_STAGING="$HOME/.codex/epiagentbench-v26-runtime-receipt-staging"
V26_CLEAN_HOME="$V26_RUNTIME_STAGING/clean-home"
V26_CLEAN_TMP="$V26_RUNTIME_STAGING/clean-tmp"
V26_ACCOUNT_NAME="$(/usr/bin/id -un)"
V26_ACCOUNT_SHELL="$(/usr/bin/dscl . -read \
  "/Users/$V26_ACCOUNT_NAME" UserShell | /usr/bin/awk '{print $2}')"
V26_CF_USER_TEXT_ENCODING="$(/usr/bin/printf \
  '0x%X:0x0:0x0' "$(/usr/bin/id -u)")"
V26_PROVIDER_FREE_ENV=(
  /usr/bin/env -i
  "HOME=$V26_CLEAN_HOME"
  "LC_ALL=C.UTF-8"
  "LOGNAME=$V26_ACCOUNT_NAME"
  "PATH=/usr/bin:/bin:/usr/sbin:/sbin"
  "SHELL=$V26_ACCOUNT_SHELL"
  "TMPDIR=$V26_CLEAN_TMP"
  "USER=$V26_ACCOUNT_NAME"
  "__CF_USER_TEXT_ENCODING=$V26_CF_USER_TEXT_ENCODING"
)
v26_provider_free_python() {
  "${V26_PROVIDER_FREE_ENV[@]}" "$V26_PYTHON" -I -S -B "$@"
}
v26_assert_provider_free_environment() {
  local actual expected
  actual="$("${V26_PROVIDER_FREE_ENV[@]}" /usr/bin/env | /usr/bin/sort)"
  expected="$(/usr/bin/printf '%s\n' \
    "HOME=$V26_CLEAN_HOME" "LC_ALL=C.UTF-8" \
    "LOGNAME=$V26_ACCOUNT_NAME" \
    "PATH=/usr/bin:/bin:/usr/sbin:/sbin" \
    "SHELL=$V26_ACCOUNT_SHELL" "TMPDIR=$V26_CLEAN_TMP" \
    "USER=$V26_ACCOUNT_NAME" \
    "__CF_USER_TEXT_ENCODING=$V26_CF_USER_TEXT_ENCODING" |
    /usr/bin/sort)"
  test "$actual" = "$expected"
}
v26_assert_clean_scratch() {
  local observed
  observed="$(/usr/bin/find "$V26_CLEAN_HOME" -mindepth 1 -print -quit)" ||
    return 1
  test -z "$observed"
  observed="$(/usr/bin/find "$V26_CLEAN_TMP" -mindepth 1 -print -quit)" ||
    return 1
  test -z "$observed"
}
V26_EXPECTED_COMMIT="${V26_CONTROL_COMMIT:?set the exact published control-plane commit}"
V26_GITBUTLER_WORKSPACE="${V26_GITBUTLER_WORKSPACE:?set the primary GitButler workspace}"
V26_REMOTE_REF='refs/heads/codex/v26-runtime-preflight'
V26_ORIGIN_URL='https://github.com/matthew-zhao/epiagentbench.git'
V26_PUBLIC_RUNTIME='results/development-matched-50x6-v26.runtime.json'
V26_RUNTIME_ONE="$V26_RUNTIME_STAGING/preflight-1.json"
V26_RUNTIME_TWO="$V26_RUNTIME_STAGING/preflight-2.json"
[[ "$V26_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
test -x "$V26_PYTHON"
test -d "$V26_GITBUTLER_WORKSPACE"
test ! -L "$V26_GITBUTLER_WORKSPACE"
test "$(cd "$V26_GITBUTLER_WORKSPACE" && pwd -P)" = \
  "$V26_GITBUTLER_WORKSPACE"
cd "$V26_GITBUTLER_WORKSPACE"
test "$(v26_git ls-remote "$V26_ORIGIN_URL" "$V26_REMOTE_REF" | /usr/bin/cut -f1)" = \
  "$V26_EXPECTED_COMMIT"
test -z "$(v26_git status --porcelain=v1 --untracked-files=all --ignore-submodules=all)"
cmp -s \
  "$V26_RUNTIME_ONE" \
  "$V26_RUNTIME_TWO"
for candidate_path in \
  "$V26_PUBLIC_RUNTIME" \
  "results/development-matched-50x6-v26.manifest.json" \
  "results/development-matched-50x6-v26.authentication.json" \
  "results/development-matched-50x6-v26.preflight.json" \
  "results/development-matched-50x6-v26.json"; do
  test ! -e "$candidate_path"
  test ! -L "$candidate_path"
done
v26_assert_provider_free_environment
v26_assert_clean_scratch
v26_provider_free_python \
  examples/run_development_matched_panel.py \
  publish-provider-free-json \
  --source "$V26_RUNTIME_ONE" \
  --destination "$V26_PUBLIC_RUNTIME"
v26_assert_provider_free_environment
v26_assert_clean_scratch
cmp -s "$V26_RUNTIME_ONE" "$V26_PUBLIC_RUNTIME"
test "$(v26_git status --porcelain=v1 --untracked-files=all --ignore-submodules=all)" = \
  "?? $V26_PUBLIC_RUNTIME"
)
```

Run `but diff`, copy the exact file change ID for only the runtime receipt,
then commit it to the existing branch and push that named branch:

```text
but commit codex/v26-runtime-preflight \
  -m "Publish V26 scientific runtime receipt" \
  --changes <exact-runtime-receipt-file-id>
but push codex/v26-runtime-preflight
```

No direct `git push` is permitted. Verify the remote branch contains the exact
receipt bytes, and record its exact 40-hex tip as `V26_RECEIPT_COMMIT`. This is
the second provider-free commit.

## 6. Validate the receipt-bound checkout and verify before writing

Use an operator-approved GitButler-compatible workflow to materialize a second
fresh clean checkout rather than mutating or reusing the runtime checkout. Set
`V26_PREPARE_CHECKOUT` to its absolute canonical path. The expected commit for
every remaining preparation command is now the published runtime-receipt
commit, not the earlier control-plane commit. The block below only validates
the supplied checkout before beginning provider-free preparation.

```bash
(
set -euo pipefail
PATH='/usr/bin:/bin:/usr/sbin:/sbin'
export PATH
umask 077
v26_git() {
  /usr/bin/env -i \
    HOME=/var/empty LC_ALL=C \
    PATH=/usr/bin:/bin:/usr/sbin:/sbin TMPDIR=/private/tmp \
    GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_SYSTEM=/dev/null \
    GIT_CONFIG_GLOBAL=/dev/null GIT_OPTIONAL_LOCKS=0 \
    GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/usr/bin/false \
    SSH_ASKPASS=/usr/bin/false \
    /usr/bin/git --no-pager \
      -c core.hooksPath=/dev/null -c core.fsmonitor=false \
      -c core.untrackedCache=false -c diff.ignoreSubmodules=all \
      -c status.submoduleSummary=false -c submodule.recurse=false \
      -c fetch.recurseSubmodules=false -c credential.helper= \
      -c credential.interactive=never -c protocol.allow=never \
      -c protocol.https.allow=always "$@"
}
V26_PYTHON="${EPIAGENTBENCH_PYTHON:?set the absolute isolated EpiAgentBench Python path}"
V26_RUNTIME_CACHE="$HOME/.codex/epiagentbench-v26-runtime-cache"
V26_RUNTIME_STAGING="$HOME/.codex/epiagentbench-v26-runtime-receipt-staging"
V26_CLEAN_HOME="$V26_RUNTIME_STAGING/clean-home"
V26_CLEAN_TMP="$V26_RUNTIME_STAGING/clean-tmp"
V26_ACCOUNT_NAME="$(/usr/bin/id -un)"
V26_ACCOUNT_SHELL="$(/usr/bin/dscl . -read \
  "/Users/$V26_ACCOUNT_NAME" UserShell | /usr/bin/awk '{print $2}')"
V26_CF_USER_TEXT_ENCODING="$(/usr/bin/printf \
  '0x%X:0x0:0x0' "$(/usr/bin/id -u)")"
V26_PROVIDER_FREE_ENV=(
  /usr/bin/env -i
  "HOME=$V26_CLEAN_HOME"
  "LC_ALL=C.UTF-8"
  "LOGNAME=$V26_ACCOUNT_NAME"
  "PATH=/usr/bin:/bin:/usr/sbin:/sbin"
  "SHELL=$V26_ACCOUNT_SHELL"
  "TMPDIR=$V26_CLEAN_TMP"
  "USER=$V26_ACCOUNT_NAME"
  "__CF_USER_TEXT_ENCODING=$V26_CF_USER_TEXT_ENCODING"
)
v26_provider_free_python() {
  "${V26_PROVIDER_FREE_ENV[@]}" "$V26_PYTHON" -I -S -B "$@"
}
v26_assert_provider_free_environment() {
  local actual expected
  actual="$("${V26_PROVIDER_FREE_ENV[@]}" /usr/bin/env | /usr/bin/sort)"
  expected="$(/usr/bin/printf '%s\n' \
    "HOME=$V26_CLEAN_HOME" "LC_ALL=C.UTF-8" \
    "LOGNAME=$V26_ACCOUNT_NAME" \
    "PATH=/usr/bin:/bin:/usr/sbin:/sbin" \
    "SHELL=$V26_ACCOUNT_SHELL" "TMPDIR=$V26_CLEAN_TMP" \
    "USER=$V26_ACCOUNT_NAME" \
    "__CF_USER_TEXT_ENCODING=$V26_CF_USER_TEXT_ENCODING" |
    /usr/bin/sort)"
  test "$actual" = "$expected"
}
v26_assert_clean_scratch() {
  local observed
  observed="$(/usr/bin/find "$V26_CLEAN_HOME" -mindepth 1 -print -quit)" ||
    return 1
  test -z "$observed"
  observed="$(/usr/bin/find "$V26_CLEAN_TMP" -mindepth 1 -print -quit)" ||
    return 1
  test -z "$observed"
}
V26_CONTROL_COMMIT="${V26_CONTROL_COMMIT:?set the exact published control-plane commit}"
V26_EXPECTED_COMMIT="${V26_RECEIPT_COMMIT:?set the exact published runtime-receipt commit}"
V26_REMOTE_REF='refs/heads/codex/v26-runtime-preflight'
V26_ORIGIN_URL='https://github.com/matthew-zhao/epiagentbench.git'
V26_PREPARE_CHECKOUT="${V26_PREPARE_CHECKOUT:?set the absolute canonical path to the fresh receipt-bound checkout}"
V26_PUBLIC_RUNTIME='results/development-matched-50x6-v26.runtime.json'
V26_RUNTIME_ONE="$V26_RUNTIME_STAGING/preflight-1.json"
V26_RUNTIME_TWO="$V26_RUNTIME_STAGING/preflight-2.json"
V26_VERIFICATION_OUTPUT="$V26_RUNTIME_STAGING/verification.json"
[[ "$V26_CONTROL_COMMIT" =~ ^[0-9a-f]{40}$ ]]
[[ "$V26_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
test -x "$V26_PYTHON"
test -d "$V26_PREPARE_CHECKOUT"
test ! -L "$V26_PREPARE_CHECKOUT"
test "$(cd "$V26_PREPARE_CHECKOUT" && pwd -P)" = \
  "$V26_PREPARE_CHECKOUT"
cd "$V26_PREPARE_CHECKOUT"
test "$(v26_git ls-remote "$V26_ORIGIN_URL" "$V26_REMOTE_REF" | /usr/bin/cut -f1)" = \
  "$V26_EXPECTED_COMMIT"
test "$(v26_git rev-parse HEAD)" = "$V26_EXPECTED_COMMIT"
test -z "$(v26_git status --porcelain=v1 --untracked-files=all --ignore-submodules=all)"
test "$(v26_git rev-list --parents -n 1 HEAD | /usr/bin/awk '{print NF}')" = 2
test "$(v26_git rev-parse HEAD^)" = "$V26_CONTROL_COMMIT"
test "$(v26_git diff --no-ext-diff --ignore-submodules=all --name-status \
  "$V26_CONTROL_COMMIT" "$V26_EXPECTED_COMMIT")" = \
  $'A\t'"$V26_PUBLIC_RUNTIME"
test "$(v26_git ls-files --error-unmatch "$V26_PUBLIC_RUNTIME")" = \
  "$V26_PUBLIC_RUNTIME"
test -f "$V26_PUBLIC_RUNTIME"
test ! -L "$V26_PUBLIC_RUNTIME"
cmp -s "$V26_RUNTIME_ONE" "$V26_RUNTIME_TWO"
cmp -s "$V26_RUNTIME_ONE" "$V26_PUBLIC_RUNTIME"
for candidate_path in \
  "$HOME/.codex/epiagentbench-v26-secrets" \
  "$HOME/.codex/epiagentbench-v26-state" \
  "$HOME/.codex/epiagentbench-v26-credentials" \
  "$HOME/.codex/epiagentbench-v26-supervisors" \
  "$HOME/.codex/epiagentbench-v26-cohort" \
  "results/development-matched-50x6-v26.manifest.json" \
  "results/development-matched-50x6-v26.authentication.json" \
  "results/development-matched-50x6-v26.preflight.json" \
  "results/development-matched-50x6-v26.json"; do
  if [ -e "$candidate_path" ] || [ -L "$candidate_path" ]; then
    echo "Refusing occupied V26 path: $candidate_path" >&2
    exit 1
  fi
done
test ! -e "$V26_VERIFICATION_OUTPUT"
test ! -L "$V26_VERIFICATION_OUTPUT"
v26_assert_provider_free_environment
v26_assert_clean_scratch
v26_provider_free_python \
  examples/run_development_matched_panel.py \
  verify-preparation-runtime \
  --preparation-runtime-receipt "$V26_PUBLIC_RUNTIME" \
  --expected-benchmark-base-commit "$V26_EXPECTED_COMMIT" \
  --runtime-cache-dir "$V26_RUNTIME_CACHE" \
  --public-verification-receipt "$V26_VERIFICATION_OUTPUT"
v26_assert_provider_free_environment
v26_assert_clean_scratch
test -f "$V26_VERIFICATION_OUTPUT"
test ! -L "$V26_VERIFICATION_OUTPUT"
test "$(/usr/bin/stat -f '%Lp' "$V26_VERIFICATION_OUTPUT")" = 644
test "$(v26_git rev-parse HEAD)" = "$V26_EXPECTED_COMMIT"
test -z "$(v26_git status --porcelain=v1 --untracked-files=all --ignore-submodules=all)"
)
```

A receipt, source, Python/bootstrap, installed-distribution, Starsim-smoke, or
closed cache-inventory mismatch stops before a key or cohort exists. Do not
repair or override a mismatch. The verification summary is staged outside the
cache, is written through the same atomic create-once boundary, and remains
operator-local.

## 7. Create fresh private prerequisites and freeze exactly once

This is the irreversible V26 preparation boundary. Use the matched V26
`freeze` command; do not call the generic `freeze-private-cohort` command.

```bash
(
set -euo pipefail
PATH='/usr/bin:/bin:/usr/sbin:/sbin'
export PATH
umask 077
set -o noclobber
v26_git() {
  /usr/bin/env -i \
    HOME=/var/empty LC_ALL=C \
    PATH=/usr/bin:/bin:/usr/sbin:/sbin TMPDIR=/private/tmp \
    GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_SYSTEM=/dev/null \
    GIT_CONFIG_GLOBAL=/dev/null GIT_OPTIONAL_LOCKS=0 \
    GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/usr/bin/false \
    SSH_ASKPASS=/usr/bin/false \
    /usr/bin/git --no-pager \
      -c core.hooksPath=/dev/null -c core.fsmonitor=false \
      -c core.untrackedCache=false -c diff.ignoreSubmodules=all \
      -c status.submoduleSummary=false -c submodule.recurse=false \
      -c fetch.recurseSubmodules=false -c credential.helper= \
      -c credential.interactive=never -c protocol.allow=never \
      -c protocol.https.allow=always "$@"
}
V26_PYTHON="${EPIAGENTBENCH_PYTHON:?set the absolute isolated EpiAgentBench Python path}"
V26_RUNTIME_CACHE="$HOME/.codex/epiagentbench-v26-runtime-cache"
V26_RUNTIME_STAGING="$HOME/.codex/epiagentbench-v26-runtime-receipt-staging"
V26_CLEAN_HOME="$V26_RUNTIME_STAGING/clean-home"
V26_CLEAN_TMP="$V26_RUNTIME_STAGING/clean-tmp"
V26_ACCOUNT_NAME="$(/usr/bin/id -un)"
V26_ACCOUNT_SHELL="$(/usr/bin/dscl . -read \
  "/Users/$V26_ACCOUNT_NAME" UserShell | /usr/bin/awk '{print $2}')"
V26_CF_USER_TEXT_ENCODING="$(/usr/bin/printf \
  '0x%X:0x0:0x0' "$(/usr/bin/id -u)")"
V26_PROVIDER_FREE_ENV=(
  /usr/bin/env -i
  "HOME=$V26_CLEAN_HOME"
  "LC_ALL=C.UTF-8"
  "LOGNAME=$V26_ACCOUNT_NAME"
  "PATH=/usr/bin:/bin:/usr/sbin:/sbin"
  "SHELL=$V26_ACCOUNT_SHELL"
  "TMPDIR=$V26_CLEAN_TMP"
  "USER=$V26_ACCOUNT_NAME"
  "__CF_USER_TEXT_ENCODING=$V26_CF_USER_TEXT_ENCODING"
)
v26_provider_free_python() {
  "${V26_PROVIDER_FREE_ENV[@]}" "$V26_PYTHON" -I -S -B "$@"
}
v26_assert_provider_free_environment() {
  local actual expected
  actual="$("${V26_PROVIDER_FREE_ENV[@]}" /usr/bin/env | /usr/bin/sort)"
  expected="$(/usr/bin/printf '%s\n' \
    "HOME=$V26_CLEAN_HOME" "LC_ALL=C.UTF-8" \
    "LOGNAME=$V26_ACCOUNT_NAME" \
    "PATH=/usr/bin:/bin:/usr/sbin:/sbin" \
    "SHELL=$V26_ACCOUNT_SHELL" "TMPDIR=$V26_CLEAN_TMP" \
    "USER=$V26_ACCOUNT_NAME" \
    "__CF_USER_TEXT_ENCODING=$V26_CF_USER_TEXT_ENCODING" |
    /usr/bin/sort)"
  test "$actual" = "$expected"
}
v26_assert_clean_scratch() {
  local observed
  observed="$(/usr/bin/find "$V26_CLEAN_HOME" -mindepth 1 -print -quit)" ||
    return 1
  test -z "$observed"
  observed="$(/usr/bin/find "$V26_CLEAN_TMP" -mindepth 1 -print -quit)" ||
    return 1
  test -z "$observed"
}
V26_EXPECTED_COMMIT="${V26_RECEIPT_COMMIT:?set the exact published runtime-receipt commit}"
V26_PREPARE_CHECKOUT="${V26_PREPARE_CHECKOUT:?set the absolute canonical path to the fresh receipt-bound checkout}"
V26_PUBLIC_RUNTIME='results/development-matched-50x6-v26.runtime.json'
V26_KEY="$HOME/.codex/epiagentbench-v26-secrets/panel-auth.key"
V26_FREEZE_CLAIM="$HOME/.codex/epiagentbench-v26-secrets/.development-matched-50x6-v26.cohort-freeze-claim.v1.json"
V26_COHORT="$HOME/.codex/epiagentbench-v26-cohort"
V26_FREEZE_OUTPUT="$V26_RUNTIME_STAGING/freeze-public.json"
V26_PRE_FREEZE_VERIFICATION="$V26_RUNTIME_STAGING/pre-freeze-verification.json"
[[ "$V26_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
test -x "$V26_PYTHON"
cd "$V26_PREPARE_CHECKOUT"
test "$(v26_git rev-parse HEAD)" = "$V26_EXPECTED_COMMIT"
test -z "$(v26_git status --porcelain=v1 --untracked-files=all --ignore-submodules=all)"
for candidate_path in \
  "$HOME/.codex/epiagentbench-v26-secrets" \
  "$HOME/.codex/epiagentbench-v26-state" \
  "$HOME/.codex/epiagentbench-v26-credentials" \
  "$HOME/.codex/epiagentbench-v26-supervisors" \
  "$V26_COHORT" \
  "results/development-matched-50x6-v26.manifest.json" \
  "results/development-matched-50x6-v26.authentication.json" \
  "results/development-matched-50x6-v26.preflight.json" \
  "results/development-matched-50x6-v26.json"; do
  if [ -e "$candidate_path" ] || [ -L "$candidate_path" ]; then
    echo "Refusing to reuse V26 path: $candidate_path" >&2
    exit 1
  fi
done
test ! -e "$V26_PRE_FREEZE_VERIFICATION"
test ! -L "$V26_PRE_FREEZE_VERIFICATION"
v26_assert_provider_free_environment
v26_assert_clean_scratch
v26_provider_free_python \
  examples/run_development_matched_panel.py \
  verify-preparation-runtime \
  --preparation-runtime-receipt "$V26_PUBLIC_RUNTIME" \
  --expected-benchmark-base-commit "$V26_EXPECTED_COMMIT" \
  --runtime-cache-dir "$V26_RUNTIME_CACHE" \
  --public-verification-receipt "$V26_PRE_FREEZE_VERIFICATION"
v26_assert_provider_free_environment
v26_assert_clean_scratch
test -f "$V26_PRE_FREEZE_VERIFICATION"
test ! -L "$V26_PRE_FREEZE_VERIFICATION"
test "$(stat -f '%Lp' "$V26_PRE_FREEZE_VERIFICATION")" = 644
test "$(v26_git rev-parse HEAD)" = "$V26_EXPECTED_COMMIT"
test -z "$(v26_git status --porcelain=v1 --untracked-files=all --ignore-submodules=all)"
for candidate_path in \
  "$HOME/.codex/epiagentbench-v26-secrets" \
  "$HOME/.codex/epiagentbench-v26-state" \
  "$HOME/.codex/epiagentbench-v26-credentials" \
  "$HOME/.codex/epiagentbench-v26-supervisors" \
  "$V26_COHORT" \
  "results/development-matched-50x6-v26.manifest.json" \
  "results/development-matched-50x6-v26.authentication.json" \
  "results/development-matched-50x6-v26.preflight.json" \
  "results/development-matched-50x6-v26.json"; do
  if [ -e "$candidate_path" ] || [ -L "$candidate_path" ]; then
    echo "A V26 path appeared during final runtime verification" >&2
    exit 1
  fi
done
mkdir \
  "$HOME/.codex/epiagentbench-v26-secrets" \
  "$HOME/.codex/epiagentbench-v26-state" \
  "$HOME/.codex/epiagentbench-v26-credentials"
mkdir \
  "$HOME/.codex/epiagentbench-v26-credentials/claude" \
  "$HOME/.codex/epiagentbench-v26-credentials/codex"
chmod 700 \
  "$HOME/.codex/epiagentbench-v26-secrets" \
  "$HOME/.codex/epiagentbench-v26-state" \
  "$HOME/.codex/epiagentbench-v26-credentials" \
  "$HOME/.codex/epiagentbench-v26-credentials/claude" \
  "$HOME/.codex/epiagentbench-v26-credentials/codex"
/usr/bin/openssl rand 32 > "$V26_KEY"
chmod 600 "$V26_KEY"
test ! -e "$V26_FREEZE_CLAIM"
test ! -L "$V26_FREEZE_CLAIM"
test ! -e "$V26_FREEZE_OUTPUT"
test ! -L "$V26_FREEZE_OUTPUT"
v26_assert_provider_free_environment
v26_assert_clean_scratch
v26_provider_free_python \
  examples/run_development_matched_panel.py freeze \
  --preparation-runtime-receipt "$V26_PUBLIC_RUNTIME" \
  --expected-benchmark-base-commit "$V26_EXPECTED_COMMIT" \
  --runtime-cache-dir "$V26_RUNTIME_CACHE" \
  --authentication-key "$V26_KEY" \
  --output-directory "$V26_COHORT" \
  --freeze-claim "$V26_FREEZE_CLAIM" \
  > "$V26_FREEZE_OUTPUT"
v26_assert_provider_free_environment
v26_assert_clean_scratch
)
```

`freeze` authenticates the canonical claim location against the key namespace,
creates the pending claim without replacement before any cohort randomness,
and writes a separate authenticated completion only after the canonical
cohort is durable. A pending claim without its matching completion is a
terminal interrupted freeze: neither `freeze` nor `prepare` may be retried,
and V26 must be superseded. Do not inspect or publish the claim, completion,
cohort packs, family map, seed material, schedule, authentication key, or
cohort manifest. This command starts zero authentication helpers, provider
processes, and model calls. Any failure after a private path is created is
terminal.

## 8. Prepare the public manifest exactly once

The prepare command independently re-verifies the tracked receipt before it
reads the key or cohort. It binds the runtime receipt, the real smoke result,
installed scientific bytes, and opaque Python/cache contract hashes into the
public manifest. The corresponding full Python entrypoint/bootstrap and cache
bindings remain private: the cache contract is retained in authenticated
private state, while the Python binding is recomputed and sealed only when the
authenticated owner-only LaunchAgent config is created.

```bash
(
set -euo pipefail
PATH='/usr/bin:/bin:/usr/sbin:/sbin'
export PATH
umask 077
set -o noclobber
v26_git() {
  /usr/bin/env -i \
    HOME=/var/empty LC_ALL=C \
    PATH=/usr/bin:/bin:/usr/sbin:/sbin TMPDIR=/private/tmp \
    GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_SYSTEM=/dev/null \
    GIT_CONFIG_GLOBAL=/dev/null GIT_OPTIONAL_LOCKS=0 \
    GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/usr/bin/false \
    SSH_ASKPASS=/usr/bin/false \
    /usr/bin/git --no-pager \
      -c core.hooksPath=/dev/null -c core.fsmonitor=false \
      -c core.untrackedCache=false -c diff.ignoreSubmodules=all \
      -c status.submoduleSummary=false -c submodule.recurse=false \
      -c fetch.recurseSubmodules=false -c credential.helper= \
      -c credential.interactive=never -c protocol.allow=never \
      -c protocol.https.allow=always "$@"
}
V26_PYTHON="${EPIAGENTBENCH_PYTHON:?set the absolute isolated EpiAgentBench Python path}"
V26_RUNTIME_CACHE="$HOME/.codex/epiagentbench-v26-runtime-cache"
V26_RUNTIME_STAGING="$HOME/.codex/epiagentbench-v26-runtime-receipt-staging"
V26_CLEAN_HOME="$V26_RUNTIME_STAGING/clean-home"
V26_CLEAN_TMP="$V26_RUNTIME_STAGING/clean-tmp"
V26_ACCOUNT_NAME="$(/usr/bin/id -un)"
V26_ACCOUNT_SHELL="$(/usr/bin/dscl . -read \
  "/Users/$V26_ACCOUNT_NAME" UserShell | /usr/bin/awk '{print $2}')"
V26_CF_USER_TEXT_ENCODING="$(/usr/bin/printf \
  '0x%X:0x0:0x0' "$(/usr/bin/id -u)")"
V26_PROVIDER_FREE_ENV=(
  /usr/bin/env -i
  "HOME=$V26_CLEAN_HOME"
  "LC_ALL=C.UTF-8"
  "LOGNAME=$V26_ACCOUNT_NAME"
  "PATH=/usr/bin:/bin:/usr/sbin:/sbin"
  "SHELL=$V26_ACCOUNT_SHELL"
  "TMPDIR=$V26_CLEAN_TMP"
  "USER=$V26_ACCOUNT_NAME"
  "__CF_USER_TEXT_ENCODING=$V26_CF_USER_TEXT_ENCODING"
)
v26_provider_free_python() {
  "${V26_PROVIDER_FREE_ENV[@]}" "$V26_PYTHON" -I -S -B "$@"
}
v26_assert_provider_free_environment() {
  local actual expected
  actual="$("${V26_PROVIDER_FREE_ENV[@]}" /usr/bin/env | /usr/bin/sort)"
  expected="$(/usr/bin/printf '%s\n' \
    "HOME=$V26_CLEAN_HOME" "LC_ALL=C.UTF-8" \
    "LOGNAME=$V26_ACCOUNT_NAME" \
    "PATH=/usr/bin:/bin:/usr/sbin:/sbin" \
    "SHELL=$V26_ACCOUNT_SHELL" "TMPDIR=$V26_CLEAN_TMP" \
    "USER=$V26_ACCOUNT_NAME" \
    "__CF_USER_TEXT_ENCODING=$V26_CF_USER_TEXT_ENCODING" |
    /usr/bin/sort)"
  test "$actual" = "$expected"
}
v26_assert_clean_scratch() {
  local observed
  observed="$(/usr/bin/find "$V26_CLEAN_HOME" -mindepth 1 -print -quit)" ||
    return 1
  test -z "$observed"
  observed="$(/usr/bin/find "$V26_CLEAN_TMP" -mindepth 1 -print -quit)" ||
    return 1
  test -z "$observed"
}
V26_EXPECTED_COMMIT="${V26_RECEIPT_COMMIT:?set the exact published runtime-receipt commit}"
V26_PREPARE_CHECKOUT="${V26_PREPARE_CHECKOUT:?set the absolute canonical path to the fresh receipt-bound checkout}"
V26_PUBLIC_RUNTIME='results/development-matched-50x6-v26.runtime.json'
V26_KEY="$HOME/.codex/epiagentbench-v26-secrets/panel-auth.key"
V26_FREEZE_CLAIM="$HOME/.codex/epiagentbench-v26-secrets/.development-matched-50x6-v26.cohort-freeze-claim.v1.json"
V26_COHORT="$HOME/.codex/epiagentbench-v26-cohort"
V26_PRIVATE_STATE="$HOME/.codex/epiagentbench-v26-state/development-matched-50x6-v26.private.json"
V26_PUBLIC_MANIFEST='results/development-matched-50x6-v26.manifest.json'
V26_PREPARE_OUTPUT="$V26_RUNTIME_STAGING/prepare-public.json"
[[ "$V26_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
test -x "$V26_PYTHON"
cd "$V26_PREPARE_CHECKOUT"
test "$(v26_git rev-parse HEAD)" = "$V26_EXPECTED_COMMIT"
test -z "$(v26_git status --porcelain=v1 --untracked-files=all --ignore-submodules=all)"
test ! -e "$V26_PRIVATE_STATE"
test ! -L "$V26_PRIVATE_STATE"
test ! -e "$V26_PUBLIC_MANIFEST"
test ! -L "$V26_PUBLIC_MANIFEST"
for candidate_path in \
  "results/development-matched-50x6-v26.authentication.json" \
  "results/development-matched-50x6-v26.preflight.json" \
  "results/development-matched-50x6-v26.json" \
  "$HOME/.codex/epiagentbench-v26-supervisors"; do
  if [ -e "$candidate_path" ] || [ -L "$candidate_path" ]; then
    echo "A later-phase V26 artifact already exists" >&2
    exit 1
  fi
done
test -f "$V26_FREEZE_CLAIM"
test ! -L "$V26_FREEZE_CLAIM"
test ! -e "$V26_PREPARE_OUTPUT"
test ! -L "$V26_PREPARE_OUTPUT"
v26_assert_provider_free_environment
v26_assert_clean_scratch
v26_provider_free_python \
  examples/run_development_matched_panel.py prepare \
  --cohort-manifest "$V26_COHORT/cohort.manifest" \
  --preparation-runtime-receipt "$V26_PUBLIC_RUNTIME" \
  --expected-benchmark-base-commit "$V26_EXPECTED_COMMIT" \
  --runtime-cache-dir "$V26_RUNTIME_CACHE" \
  --authentication-key "$V26_KEY" \
  --freeze-claim "$V26_FREEZE_CLAIM" \
  --claude-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v26-credentials/claude" \
  --codex-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v26-credentials/codex" \
  --private-state "$V26_PRIVATE_STATE" \
  --public-manifest "$V26_PUBLIC_MANIFEST" \
  --timeout 1800 \
  --claude-max-budget-usd 5 \
  > "$V26_PREPARE_OUTPUT"
v26_assert_provider_free_environment
v26_assert_clean_scratch
test -f "$V26_PUBLIC_MANIFEST"
test ! -L "$V26_PUBLIC_MANIFEST"
test -f "$V26_PRIVATE_STATE"
test ! -L "$V26_PRIVATE_STATE"
)
```

Preparation starts no authentication bootstrap, provider process, or model
call. It invokes only the pinned macOS Keychain metadata tool to prove the
obsolete Claude item is absent; it never retrieves a password or credential.
Preserve the authenticated private state, full cache contract, freeze claim,
and completion untracked and owner-only. The raw
Python/bootstrap binding stays out of public artifacts and will be recomputed
and sealed in the later authenticated LaunchAgent config. For the complete
Python/cache bindings, the public manifest retains only opaque hashes,
alongside the Python target content hash, entrypoint kind, and path-free
scientific identities. Do not regenerate anything if publication fails;
publish the same already-created public bytes.

## 9. Publish the manifest, pin it, and stop

Copy only the public manifest into the GitButler primary workspace. Confirm
the runtime receipt is already tracked there, and confirm the authentication,
preflight, and final-result destinations remain absent.

```bash
(
set -euo pipefail
PATH='/usr/bin:/bin:/usr/sbin:/sbin'
export PATH
umask 077
v26_git() {
  /usr/bin/env -i \
    HOME=/var/empty LC_ALL=C \
    PATH=/usr/bin:/bin:/usr/sbin:/sbin TMPDIR=/private/tmp \
    GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_SYSTEM=/dev/null \
    GIT_CONFIG_GLOBAL=/dev/null GIT_OPTIONAL_LOCKS=0 \
    GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/usr/bin/false \
    SSH_ASKPASS=/usr/bin/false \
    /usr/bin/git --no-pager \
      -c core.hooksPath=/dev/null -c core.fsmonitor=false \
      -c core.untrackedCache=false -c diff.ignoreSubmodules=all \
      -c status.submoduleSummary=false -c submodule.recurse=false \
      -c fetch.recurseSubmodules=false -c credential.helper= \
      -c credential.interactive=never -c protocol.allow=never \
      -c protocol.https.allow=always "$@"
}
V26_PYTHON="${EPIAGENTBENCH_PYTHON:?set the absolute isolated EpiAgentBench Python path}"
V26_RUNTIME_CACHE="$HOME/.codex/epiagentbench-v26-runtime-cache"
V26_RUNTIME_STAGING="$HOME/.codex/epiagentbench-v26-runtime-receipt-staging"
V26_CLEAN_HOME="$V26_RUNTIME_STAGING/clean-home"
V26_CLEAN_TMP="$V26_RUNTIME_STAGING/clean-tmp"
V26_ACCOUNT_NAME="$(/usr/bin/id -un)"
V26_ACCOUNT_SHELL="$(/usr/bin/dscl . -read \
  "/Users/$V26_ACCOUNT_NAME" UserShell | /usr/bin/awk '{print $2}')"
V26_CF_USER_TEXT_ENCODING="$(/usr/bin/printf \
  '0x%X:0x0:0x0' "$(/usr/bin/id -u)")"
V26_PROVIDER_FREE_ENV=(
  /usr/bin/env -i
  "HOME=$V26_CLEAN_HOME"
  "LC_ALL=C.UTF-8"
  "LOGNAME=$V26_ACCOUNT_NAME"
  "PATH=/usr/bin:/bin:/usr/sbin:/sbin"
  "SHELL=$V26_ACCOUNT_SHELL"
  "TMPDIR=$V26_CLEAN_TMP"
  "USER=$V26_ACCOUNT_NAME"
  "__CF_USER_TEXT_ENCODING=$V26_CF_USER_TEXT_ENCODING"
)
v26_provider_free_python() {
  "${V26_PROVIDER_FREE_ENV[@]}" "$V26_PYTHON" -I -S -B "$@"
}
v26_assert_provider_free_environment() {
  local actual expected
  actual="$("${V26_PROVIDER_FREE_ENV[@]}" /usr/bin/env | /usr/bin/sort)"
  expected="$(/usr/bin/printf '%s\n' \
    "HOME=$V26_CLEAN_HOME" "LC_ALL=C.UTF-8" \
    "LOGNAME=$V26_ACCOUNT_NAME" \
    "PATH=/usr/bin:/bin:/usr/sbin:/sbin" \
    "SHELL=$V26_ACCOUNT_SHELL" "TMPDIR=$V26_CLEAN_TMP" \
    "USER=$V26_ACCOUNT_NAME" \
    "__CF_USER_TEXT_ENCODING=$V26_CF_USER_TEXT_ENCODING" |
    /usr/bin/sort)"
  test "$actual" = "$expected"
}
v26_assert_clean_scratch() {
  local observed
  observed="$(/usr/bin/find "$V26_CLEAN_HOME" -mindepth 1 -print -quit)" ||
    return 1
  test -z "$observed"
  observed="$(/usr/bin/find "$V26_CLEAN_TMP" -mindepth 1 -print -quit)" ||
    return 1
  test -z "$observed"
}
V26_EXPECTED_COMMIT="${V26_RECEIPT_COMMIT:?set the exact published runtime-receipt commit}"
V26_PREPARE_CHECKOUT="${V26_PREPARE_CHECKOUT:?set the absolute canonical path to the fresh receipt-bound checkout}"
V26_GITBUTLER_WORKSPACE="${V26_GITBUTLER_WORKSPACE:?set the primary GitButler workspace}"
V26_PUBLIC_RUNTIME='results/development-matched-50x6-v26.runtime.json'
V26_PUBLIC_MANIFEST='results/development-matched-50x6-v26.manifest.json'
[[ "$V26_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
test -x "$V26_PYTHON"
cd "$V26_PREPARE_CHECKOUT"
test "$(v26_git rev-parse HEAD)" = "$V26_EXPECTED_COMMIT"
test -f "$V26_PUBLIC_MANIFEST"
test ! -L "$V26_PUBLIC_MANIFEST"
test "$(v26_git status --porcelain=v1 --untracked-files=all --ignore-submodules=all)" = \
  "?? $V26_PUBLIC_MANIFEST"
test -d "$V26_GITBUTLER_WORKSPACE"
test ! -L "$V26_GITBUTLER_WORKSPACE"
test "$(cd "$V26_GITBUTLER_WORKSPACE" && pwd -P)" = \
  "$V26_GITBUTLER_WORKSPACE"
cmp -s "$V26_PUBLIC_RUNTIME" \
  "$V26_GITBUTLER_WORKSPACE/$V26_PUBLIC_RUNTIME"
cd "$V26_GITBUTLER_WORKSPACE"
test -z "$(v26_git status --porcelain=v1 --untracked-files=all --ignore-submodules=all)"
test "$(v26_git ls-files --error-unmatch "$V26_PUBLIC_RUNTIME")" = \
  "$V26_PUBLIC_RUNTIME"
test ! -e "$V26_PUBLIC_MANIFEST"
test ! -L "$V26_PUBLIC_MANIFEST"
for candidate_path in \
  "results/development-matched-50x6-v26.authentication.json" \
  "results/development-matched-50x6-v26.preflight.json" \
  "results/development-matched-50x6-v26.json"; do
  test ! -e "$candidate_path"
  test ! -L "$candidate_path"
done
v26_assert_provider_free_environment
v26_assert_clean_scratch
v26_provider_free_python \
  examples/run_development_matched_panel.py \
  publish-provider-free-json \
  --source "$V26_PREPARE_CHECKOUT/$V26_PUBLIC_MANIFEST" \
  --destination "$V26_PUBLIC_MANIFEST"
v26_assert_provider_free_environment
v26_assert_clean_scratch
cmp -s \
  "$V26_PREPARE_CHECKOUT/$V26_PUBLIC_MANIFEST" \
  "$V26_PUBLIC_MANIFEST"
test "$(v26_git status --porcelain=v1 --untracked-files=all --ignore-submodules=all)" = \
  "?? $V26_PUBLIC_MANIFEST"
)
```

Commit only the manifest with its exact `but diff` file ID and push only the
named branch:

```text
but commit codex/v26-runtime-preflight \
  -m "Publish V26 frozen panel manifest" \
  --changes <exact-public-manifest-file-id>
but push codex/v26-runtime-preflight
```

After the push, record the 40-hex remote tip as `V26_MANIFEST_COMMIT`. Use an
operator-approved GitButler-compatible workflow to materialize one final fresh
checkout at that exact remote tip, set `V26_MANIFEST_CHECKOUT` to its absolute
canonical path, and validate the complete three-commit provider-free chain:

```bash
(
set -euo pipefail
PATH='/usr/bin:/bin:/usr/sbin:/sbin'
export PATH
v26_git() {
  /usr/bin/env -i \
    HOME=/var/empty LC_ALL=C \
    PATH=/usr/bin:/bin:/usr/sbin:/sbin TMPDIR=/private/tmp \
    GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_SYSTEM=/dev/null \
    GIT_CONFIG_GLOBAL=/dev/null GIT_OPTIONAL_LOCKS=0 \
    GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/usr/bin/false \
    SSH_ASKPASS=/usr/bin/false \
    /usr/bin/git --no-pager \
      -c core.hooksPath=/dev/null -c core.fsmonitor=false \
      -c core.untrackedCache=false -c diff.ignoreSubmodules=all \
      -c status.submoduleSummary=false -c submodule.recurse=false \
      -c fetch.recurseSubmodules=false -c credential.helper= \
      -c credential.interactive=never -c protocol.allow=never \
      -c protocol.https.allow=always "$@"
}
V26_RECEIPT_COMMIT="${V26_RECEIPT_COMMIT:?set the exact published runtime-receipt commit}"
V26_MANIFEST_COMMIT="${V26_MANIFEST_COMMIT:?set the exact published manifest commit}"
V26_MANIFEST_CHECKOUT="${V26_MANIFEST_CHECKOUT:?set the fresh clean manifest-bound checkout}"
V26_RUNTIME_STAGING="$HOME/.codex/epiagentbench-v26-runtime-receipt-staging"
V26_PREPARE_CHECKOUT="${V26_PREPARE_CHECKOUT:?set the receipt-bound preparation checkout}"
V26_REMOTE_REF='refs/heads/codex/v26-runtime-preflight'
V26_ORIGIN_URL='https://github.com/matthew-zhao/epiagentbench.git'
V26_PUBLIC_RUNTIME='results/development-matched-50x6-v26.runtime.json'
V26_PUBLIC_MANIFEST='results/development-matched-50x6-v26.manifest.json'
[[ "$V26_RECEIPT_COMMIT" =~ ^[0-9a-f]{40}$ ]]
[[ "$V26_MANIFEST_COMMIT" =~ ^[0-9a-f]{40}$ ]]
test -d "$V26_MANIFEST_CHECKOUT"
test ! -L "$V26_MANIFEST_CHECKOUT"
test "$(cd "$V26_MANIFEST_CHECKOUT" && pwd -P)" = \
  "$V26_MANIFEST_CHECKOUT"
cd "$V26_MANIFEST_CHECKOUT"
test "$(v26_git ls-remote "$V26_ORIGIN_URL" "$V26_REMOTE_REF" | /usr/bin/cut -f1)" = \
  "$V26_MANIFEST_COMMIT"
test "$(v26_git rev-parse HEAD)" = "$V26_MANIFEST_COMMIT"
test -z "$(v26_git status --porcelain=v1 --untracked-files=all --ignore-submodules=all)"
test "$(v26_git rev-list --parents -n 1 HEAD | /usr/bin/awk '{print NF}')" = 2
test "$(v26_git rev-parse HEAD^)" = "$V26_RECEIPT_COMMIT"
test "$(v26_git diff --no-ext-diff --ignore-submodules=all --name-status \
  "$V26_RECEIPT_COMMIT" "$V26_MANIFEST_COMMIT")" = \
  $'A\t'"$V26_PUBLIC_MANIFEST"
cmp -s \
  "$V26_RUNTIME_STAGING/preflight-1.json" \
  "$V26_PUBLIC_RUNTIME"
cmp -s \
  "$V26_PREPARE_CHECKOUT/$V26_PUBLIC_MANIFEST" \
  "$V26_PUBLIC_MANIFEST"
)
```

Only after every check passes is `V26_MANIFEST_COMMIT` the pinned V26
provider-free manifest commit.

> [!IMPORTANT]
> Stop here for the current milestone. At this point authentication remains
> untouched, model calls remain zero, provider processes remain zero, no
> supervisor exists, and no spend has been authorized.

## 10. Later only: exact spend authorization and authentication

Do not execute this section until the operator separately provides this exact
sentence after inspecting the pinned public manifest:

> I acknowledge the replacement six-call v26 preflight and 300-assignment
> production run, including unbounded Codex/Cursor provider spend and up to
> $600 total Claude spend across the failed v2 preflight, failed v5 preflight,
> failed v6 authentication bootstrap, failed v7 preflight, failed v8
> production run, v9 preflight and failed production run, the abandoned
> zero-model-call v10 precommitment, the failed zero-model-call v11
> authentication bootstrap, the abandoned zero-model-call v12 precommitment,
> the abandoned zero-model-call v13 precommitment, the failed v14 preflight,
> the failed zero-model-call v15 pre-claim preparation, the failed v16
> preflight, the failed zero-model-call v17 pre-start
> runtime-cache-environment refusal, the failed v18 preflight, the failed
> zero-model-call v19 authentication setup, the failed zero-model-call v20
> preflight, the failed zero-model-call v21 preflight, the failed
> zero-model-call v22 interrupted authentication ceremony, the failed v23
> six-call preflight release validation, the abandoned zero-model-call v24
> control-plane precommitment, the failed zero-model-call v25 provider-free
> preparation-runtime CLI discovery, and the v26 preflight and production run.

The later authorization command must use the same frozen paths and exact text.
It creates no provider process. The foreground `authenticate` ceremony may
start only after authorization; its sanitized public receipt must be committed
through GitButler before a supervisor is generated.

```bash
(
set -euo pipefail
PATH='/usr/bin:/bin:/usr/sbin:/sbin'
export PATH
v26_git() {
  /usr/bin/env -i HOME=/var/empty LC_ALL=C \
    PATH=/usr/bin:/bin:/usr/sbin:/sbin TMPDIR=/private/tmp \
    GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_SYSTEM=/dev/null \
    GIT_CONFIG_GLOBAL=/dev/null GIT_OPTIONAL_LOCKS=0 \
    GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/usr/bin/false \
    SSH_ASKPASS=/usr/bin/false \
    /usr/bin/git --no-pager \
      -c core.hooksPath=/dev/null -c core.fsmonitor=false \
      -c core.untrackedCache=false -c diff.ignoreSubmodules=all \
      -c status.submoduleSummary=false -c submodule.recurse=false \
      -c fetch.recurseSubmodules=false -c credential.helper= \
      -c credential.interactive=never -c protocol.allow=never \
      -c protocol.https.allow=always "$@"
}
V26_PYTHON="${EPIAGENTBENCH_PYTHON:?set the absolute isolated EpiAgentBench Python path}"
V26_RUNTIME_CACHE="$HOME/.codex/epiagentbench-v26-runtime-cache"
V26_EXPECTED_COMMIT="${V26_MANIFEST_COMMIT:?set the exact published V26 manifest commit}"
V26_REPOSITORY_ROOT="${V26_AUTHORIZATION_CHECKOUT:?set the clean manifest-bound checkout}"
V26_KEY="$HOME/.codex/epiagentbench-v26-secrets/panel-auth.key"
V26_PRIVATE_STATE="$HOME/.codex/epiagentbench-v26-state/development-matched-50x6-v26.private.json"
[[ "$V26_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
test -x "$V26_PYTHON"
test -d "$V26_REPOSITORY_ROOT"
test ! -L "$V26_REPOSITORY_ROOT"
test "$(cd "$V26_REPOSITORY_ROOT" && pwd -P)" = "$V26_REPOSITORY_ROOT"
cd "$V26_REPOSITORY_ROOT"
test "$(v26_git rev-parse HEAD)" = "$V26_EXPECTED_COMMIT"
test -z "$(v26_git status --porcelain=v1 --untracked-files=all --ignore-submodules=all)"
"$V26_PYTHON" -I -S -B \
  examples/run_development_matched_panel.py authorize \
  --runtime-cache-dir "$V26_RUNTIME_CACHE" \
  --authentication-key "$V26_KEY" \
  --claude-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v26-credentials/claude" \
  --codex-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v26-credentials/codex" \
  --private-state "$V26_PRIVATE_STATE" \
  --public-manifest \
    results/development-matched-50x6-v26.manifest.json \
  --acknowledgement-text \
    'I acknowledge the replacement six-call v26 preflight and 300-assignment production run, including unbounded Codex/Cursor provider spend and up to $600 total Claude spend across the failed v2 preflight, failed v5 preflight, failed v6 authentication bootstrap, failed v7 preflight, failed v8 production run, v9 preflight and failed production run, the abandoned zero-model-call v10 precommitment, the failed zero-model-call v11 authentication bootstrap, the abandoned zero-model-call v12 precommitment, the abandoned zero-model-call v13 precommitment, the failed v14 preflight, the failed zero-model-call v15 pre-claim preparation, the failed v16 preflight, the failed zero-model-call v17 pre-start runtime-cache-environment refusal, the failed v18 preflight, the failed zero-model-call v19 authentication setup, the failed zero-model-call v20 preflight, the failed zero-model-call v21 preflight, the failed zero-model-call v22 interrupted authentication ceremony, the failed v23 six-call preflight release validation, the abandoned zero-model-call v24 control-plane precommitment, the failed zero-model-call v25 provider-free preparation-runtime CLI discovery, and the v26 preflight and production run.'
)
```

Only after that exact authorization exists may the foreground authentication
ceremony run. The operator must manually open a new Terminal.app window from
the Dock or Spotlight and paste the following block into that window. The
Terminal process, shell, and foreground Python command must be independent of
the Codex app and its PTY. Keep the window open, the Mac awake, and the network
connected until the command returns. Before pasting, set only the three
non-secret operator inputs `EPIAGENTBENCH_PYTHON`, `V26_MANIFEST_COMMIT`, and
`V26_AUTHORIZATION_CHECKOUT` in that Terminal. Never put a credential, device
code, OAuth value, or provider output in an environment variable.

Do not launch this block through Codex execution, `osascript`, a `.command`
double-click, LaunchAgent, scheduled task, `tmux`, or `screen`. Do not use
`exec`, `nohup`, `disown`, `&`, a pipe, redirection, `tee`, `script`, or any
other output capture around `authenticate`. Its stdin, stdout, and stderr must
remain attached directly to the manually owned Terminal TTY. The operator
must personally choose the intended account and complete both browser
ceremonies. Never paste a device code, URL, OAuth state, screenshot, provider
output, or terminal transcript into an agent conversation; report only the
sanitized `auth-status` fields printed after the command returns.

```zsh
(
  set -euo pipefail
  umask 077

  v26_git() {
    /usr/bin/env -i HOME=/var/empty LC_ALL=C \
      PATH=/usr/bin:/bin:/usr/sbin:/sbin TMPDIR=/private/tmp \
      GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_SYSTEM=/dev/null \
      GIT_CONFIG_GLOBAL=/dev/null GIT_OPTIONAL_LOCKS=0 \
      GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/usr/bin/false \
      SSH_ASKPASS=/usr/bin/false \
      /usr/bin/git --no-pager \
        -c core.hooksPath=/dev/null -c core.fsmonitor=false \
        -c core.untrackedCache=false -c diff.ignoreSubmodules=all \
        -c status.submoduleSummary=false -c submodule.recurse=false \
        -c fetch.recurseSubmodules=false -c credential.helper= \
        -c credential.interactive=never -c protocol.allow=never \
        -c protocol.https.allow=always "$@"
  }

  V26_PYTHON="${EPIAGENTBENCH_PYTHON:?set the exact pinned isolated Python}"
  V26_EXPECTED_COMMIT="${V26_MANIFEST_COMMIT:?set the exact published V26 manifest commit}"
  V26_REPOSITORY_ROOT="${V26_AUTHORIZATION_CHECKOUT:?set the clean manifest-bound checkout}"
  V26_RUNTIME_CACHE="$HOME/.codex/epiagentbench-v26-runtime-cache"
  V26_KEY="$HOME/.codex/epiagentbench-v26-secrets/panel-auth.key"
  V26_PRIVATE_STATE="$HOME/.codex/epiagentbench-v26-state/development-matched-50x6-v26.private.json"
  V26_CLAUDE_STORAGE="$HOME/.codex/epiagentbench-v26-credentials/claude"
  V26_CODEX_STORAGE="$HOME/.codex/epiagentbench-v26-credentials/codex"
  V26_MANIFEST="results/development-matched-50x6-v26.manifest.json"

  [[ "$V26_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
  test -t 0
  test -t 1
  test -t 2
  test -x "$V26_PYTHON"
  test -d "$V26_REPOSITORY_ROOT"
  test ! -L "$V26_REPOSITORY_ROOT"
  test "$(cd "$V26_REPOSITORY_ROOT" && pwd -P)" = \
    "$V26_REPOSITORY_ROOT"

  cd "$V26_REPOSITORY_ROOT"
  test "$(v26_git rev-parse HEAD)" = "$V26_EXPECTED_COMMIT"
  test -z "$(v26_git status --porcelain=v1 --untracked-files=all --ignore-submodules=all)"

  V26_AUTH_ARGS=(
    --runtime-cache-dir "$V26_RUNTIME_CACHE"
    --authentication-key "$V26_KEY"
    --claude-secure-storage-dir "$V26_CLAUDE_STORAGE"
    --codex-secure-storage-dir "$V26_CODEX_STORAGE"
    --private-state "$V26_PRIVATE_STATE"
    --public-manifest "$V26_MANIFEST"
  )

  echo "Sanitized status before authentication:"
  "$V26_PYTHON" -I -S -B \
    examples/run_development_matched_panel.py \
    auth-status "${V26_AUTH_ARGS[@]}"

  echo
  echo "Proceed only from required or explicit retryable_failed."
  echo "Never proceed from running, terminal_failed, pending_publication, or passed."
  printf 'Type RUN to begin the foreground ceremony: '
  IFS= read -r V26_CONFIRM
  test "$V26_CONFIRM" = "RUN"

  V26_AUTH_RC=0
  "$V26_PYTHON" -I -S -B \
    examples/run_development_matched_panel.py \
    authenticate "${V26_AUTH_ARGS[@]}" \
    --acknowledge-interactive-authentication \
    || V26_AUTH_RC=$?

  echo
  printf 'Authentication command exit status: %s\n' "$V26_AUTH_RC"
  echo "Sanitized status after authentication:"
  "$V26_PYTHON" -I -S -B \
    examples/run_development_matched_panel.py \
    auth-status "${V26_AUTH_ARGS[@]}"

  if (( V26_AUTH_RC != 0 )); then
    echo "Do not rerun automatically. Act only on the sanitized status above."
  fi
)
```

The pre-ceremony status must be exactly `required` or the explicit durable
`retryable_failed` state. A retry from `retryable_failed` is a new manual
operator decision and is allowed only after the prior process group was
quiesced and the unchanged credential target was proven empty. A status of
`pending_publication` or `passed` means validate and publish the existing
sanitized receipt; it never authorizes another ceremony. A status of
`running` or `terminal_failed` must never be passed to `authenticate`.

Automating only the act of opening an empty Terminal window would not itself
disclose credentials, but `osascript ... do script` makes ownership of the
ceremony ambiguous and weakens the evidence that the operator selected the
intended account. Automating browser account selection or device-code entry
directly violates that boundary. V26 therefore requires manual Terminal
opening, manual paste, and manual account selection.

If the Terminal command disappears and the sanitized state remains `running`,
do not retry and do not infer success from credential or temporary files.
First conduct a provider-content-free process audit and establish that the
foreground owner and every authentication helper are absent. Then run the
following provider-free reconciliation once from the same clean,
manifest-bound checkout:

```bash
(
set -euo pipefail
PATH='/usr/bin:/bin:/usr/sbin:/sbin'
export PATH
v26_git() {
  /usr/bin/env -i HOME=/var/empty LC_ALL=C \
    PATH=/usr/bin:/bin:/usr/sbin:/sbin TMPDIR=/private/tmp \
    GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_SYSTEM=/dev/null \
    GIT_CONFIG_GLOBAL=/dev/null GIT_OPTIONAL_LOCKS=0 \
    GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/usr/bin/false \
    SSH_ASKPASS=/usr/bin/false \
    /usr/bin/git --no-pager \
      -c core.hooksPath=/dev/null -c core.fsmonitor=false \
      -c core.untrackedCache=false -c diff.ignoreSubmodules=all \
      -c status.submoduleSummary=false -c submodule.recurse=false \
      -c fetch.recurseSubmodules=false -c credential.helper= \
      -c credential.interactive=never -c protocol.allow=never \
      -c protocol.https.allow=always "$@"
}
V26_PYTHON="${EPIAGENTBENCH_PYTHON:?set the absolute isolated EpiAgentBench Python path}"
V26_RUNTIME_CACHE="$HOME/.codex/epiagentbench-v26-runtime-cache"
V26_EXPECTED_COMMIT="${V26_MANIFEST_COMMIT:?set the exact published V26 manifest commit}"
V26_REPOSITORY_ROOT="${V26_AUTHORIZATION_CHECKOUT:?set the clean manifest-bound checkout}"
V26_KEY="$HOME/.codex/epiagentbench-v26-secrets/panel-auth.key"
V26_PRIVATE_STATE="$HOME/.codex/epiagentbench-v26-state/development-matched-50x6-v26.private.json"
[[ "$V26_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
test -x "$V26_PYTHON"
test -d "$V26_REPOSITORY_ROOT"
test ! -L "$V26_REPOSITORY_ROOT"
test "$(cd "$V26_REPOSITORY_ROOT" && pwd -P)" = "$V26_REPOSITORY_ROOT"
cd "$V26_REPOSITORY_ROOT"
test "$(v26_git rev-parse HEAD)" = "$V26_EXPECTED_COMMIT"
test -z "$(v26_git status --porcelain=v1 --untracked-files=all --ignore-submodules=all)"
"$V26_PYTHON" -I -S -B \
  examples/run_development_matched_panel.py reconcile-authentication \
  --runtime-cache-dir "$V26_RUNTIME_CACHE" \
  --authentication-key "$V26_KEY" \
  --claude-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v26-credentials/claude" \
  --codex-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v26-credentials/codex" \
  --private-state "$V26_PRIVATE_STATE" \
  --public-manifest \
    results/development-matched-50x6-v26.manifest.json
"$V26_PYTHON" -I -S -B \
  examples/run_development_matched_panel.py auth-status \
  --runtime-cache-dir "$V26_RUNTIME_CACHE" \
  --authentication-key "$V26_KEY" \
  --claude-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v26-credentials/claude" \
  --codex-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v26-credentials/codex" \
  --private-state "$V26_PRIVATE_STATE" \
  --public-manifest \
    results/development-matched-50x6-v26.manifest.json
)
```

`reconcile-authentication` acquires the nonblocking panel lock, starts no
authentication helper, provider, or model, and exposes only the same finite
sanitized status as `auth-status`. It accepts only an abandoned durable
`running` ceremony or an existing terminal incident. A `running` ceremony is
sealed as `terminal_failed` with
`interrupted_authentication_ceremony`, zero model calls, and
`retry_permitted = false`. Reconciliation never promotes credential bytes,
creates a public authentication receipt, or makes the V26 namespaces reusable.
After reconciliation, securely remove any orphaned temporary authentication
directory only after process quiescence, publish a sanitized supersession
record, and prepare a newly versioned panel rather than retrying V26.

### Success path only: publish a completed authentication receipt

If `reconcile-authentication` ran, **stop**. The remainder of this V26 runbook
must not be used; supersede V26 and prepare a newly versioned panel. Continue
below only when `auth-status` reports a durable `pending_publication` or
`passed` ceremony produced by the uninterrupted foreground authentication
command.

The uninterrupted authentication command creates the public receipt once in
the manifest-bound authorization checkout. Do not regenerate it. Require
`auth-status = passed`, then copy those exact bytes once into the clean
GitButler workspace:

```bash
(
set -euo pipefail
PATH='/usr/bin:/bin:/usr/sbin:/sbin'
export PATH
umask 077
v26_git() {
  /usr/bin/env -i \
    HOME=/var/empty LC_ALL=C \
    PATH=/usr/bin:/bin:/usr/sbin:/sbin TMPDIR=/private/tmp \
    GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_SYSTEM=/dev/null \
    GIT_CONFIG_GLOBAL=/dev/null GIT_OPTIONAL_LOCKS=0 \
    GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/usr/bin/false \
    SSH_ASKPASS=/usr/bin/false \
    /usr/bin/git --no-pager \
      -c core.hooksPath=/dev/null -c core.fsmonitor=false \
      -c core.untrackedCache=false -c diff.ignoreSubmodules=all \
      -c status.submoduleSummary=false -c submodule.recurse=false \
      -c fetch.recurseSubmodules=false -c credential.helper= \
      -c credential.interactive=never -c protocol.allow=never \
      -c protocol.https.allow=always "$@"
}
V26_PYTHON="${EPIAGENTBENCH_PYTHON:?set the pinned isolated Python}"
V26_RUNTIME_STAGING="$HOME/.codex/epiagentbench-v26-runtime-receipt-staging"
V26_CLEAN_HOME="$V26_RUNTIME_STAGING/clean-home"
V26_CLEAN_TMP="$V26_RUNTIME_STAGING/clean-tmp"
V26_ACCOUNT_NAME="$(/usr/bin/id -un)"
V26_ACCOUNT_SHELL="$(/usr/bin/dscl . -read \
  "/Users/$V26_ACCOUNT_NAME" UserShell | /usr/bin/awk '{print $2}')"
V26_CF_USER_TEXT_ENCODING="$(/usr/bin/printf \
  '0x%X:0x0:0x0' "$(/usr/bin/id -u)")"
V26_PROVIDER_FREE_ENV=(
  /usr/bin/env -i
  "HOME=$V26_CLEAN_HOME"
  "LC_ALL=C.UTF-8"
  "LOGNAME=$V26_ACCOUNT_NAME"
  "PATH=/usr/bin:/bin:/usr/sbin:/sbin"
  "SHELL=$V26_ACCOUNT_SHELL"
  "TMPDIR=$V26_CLEAN_TMP"
  "USER=$V26_ACCOUNT_NAME"
  "__CF_USER_TEXT_ENCODING=$V26_CF_USER_TEXT_ENCODING"
)
v26_provider_free_python() {
  "${V26_PROVIDER_FREE_ENV[@]}" "$V26_PYTHON" -I -S -B "$@"
}
v26_assert_provider_free_environment() {
  local actual expected
  actual="$("${V26_PROVIDER_FREE_ENV[@]}" /usr/bin/env | /usr/bin/sort)"
  expected="$(/usr/bin/printf '%s\n' \
    "HOME=$V26_CLEAN_HOME" "LC_ALL=C.UTF-8" \
    "LOGNAME=$V26_ACCOUNT_NAME" \
    "PATH=/usr/bin:/bin:/usr/sbin:/sbin" \
    "SHELL=$V26_ACCOUNT_SHELL" "TMPDIR=$V26_CLEAN_TMP" \
    "USER=$V26_ACCOUNT_NAME" \
    "__CF_USER_TEXT_ENCODING=$V26_CF_USER_TEXT_ENCODING" |
    /usr/bin/sort)"
  test "$actual" = "$expected"
}
v26_assert_clean_scratch() {
  local observed
  observed="$(/usr/bin/find "$V26_CLEAN_HOME" -mindepth 1 -print -quit)" ||
    return 1
  test -z "$observed"
  observed="$(/usr/bin/find "$V26_CLEAN_TMP" -mindepth 1 -print -quit)" ||
    return 1
  test -z "$observed"
}
V26_EXPECTED_COMMIT="${V26_MANIFEST_COMMIT:?set the pinned manifest commit}"
V26_SOURCE_CHECKOUT="${V26_AUTHORIZATION_CHECKOUT:?set the manifest-bound authorization checkout}"
V26_GITBUTLER_WORKSPACE="${V26_GITBUTLER_WORKSPACE:?set the primary GitButler workspace}"
V26_REMOTE_REF='refs/heads/codex/v26-runtime-preflight'
V26_ORIGIN_URL='https://github.com/matthew-zhao/epiagentbench.git'
V26_PUBLIC_AUTHENTICATION='results/development-matched-50x6-v26.authentication.json'
[[ "$V26_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
cd "$V26_SOURCE_CHECKOUT"
test "$(v26_git rev-parse HEAD)" = "$V26_EXPECTED_COMMIT"
test -f "$V26_PUBLIC_AUTHENTICATION"
test ! -L "$V26_PUBLIC_AUTHENTICATION"
test "$(v26_git status --porcelain=v1 --untracked-files=all --ignore-submodules=all)" = \
  "?? $V26_PUBLIC_AUTHENTICATION"
cd "$V26_GITBUTLER_WORKSPACE"
test "$(v26_git ls-remote "$V26_ORIGIN_URL" "$V26_REMOTE_REF" | /usr/bin/cut -f1)" = \
  "$V26_EXPECTED_COMMIT"
test -z "$(v26_git status --porcelain=v1 --untracked-files=all --ignore-submodules=all)"
test ! -e "$V26_PUBLIC_AUTHENTICATION"
test ! -L "$V26_PUBLIC_AUTHENTICATION"
v26_assert_provider_free_environment
v26_assert_clean_scratch
v26_provider_free_python \
  examples/run_development_matched_panel.py \
  publish-provider-free-json \
  --source "$V26_SOURCE_CHECKOUT/$V26_PUBLIC_AUTHENTICATION" \
  --destination "$V26_PUBLIC_AUTHENTICATION"
v26_assert_provider_free_environment
v26_assert_clean_scratch
cmp -s \
  "$V26_SOURCE_CHECKOUT/$V26_PUBLIC_AUTHENTICATION" \
  "$V26_PUBLIC_AUTHENTICATION"
test "$(v26_git status --porcelain=v1 --untracked-files=all --ignore-submodules=all)" = \
  "?? $V26_PUBLIC_AUTHENTICATION"
)
```

Commit exactly that file and publish only the named branch through GitButler:

```text
but commit codex/v26-runtime-preflight \
  -m "Publish V26 authentication receipt" \
  --changes <exact-authentication-receipt-file-id>
but push codex/v26-runtime-preflight
```

Record the exact remote tip as `V26_AUTHENTICATION_RECEIPT_COMMIT`. Materialize
a fresh clean checkout at that tip, require its parent to be
`V26_MANIFEST_COMMIT`, require the one-commit diff to add only the
authentication receipt, and byte-compare it with the uninterrupted ceremony's
receipt:

```bash
(
set -euo pipefail
PATH='/usr/bin:/bin:/usr/sbin:/sbin'
export PATH
v26_git() {
  /usr/bin/env -i \
    HOME=/var/empty LC_ALL=C \
    PATH=/usr/bin:/bin:/usr/sbin:/sbin TMPDIR=/private/tmp \
    GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_SYSTEM=/dev/null \
    GIT_CONFIG_GLOBAL=/dev/null GIT_OPTIONAL_LOCKS=0 \
    GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/usr/bin/false \
    SSH_ASKPASS=/usr/bin/false \
    /usr/bin/git --no-pager \
      -c core.hooksPath=/dev/null -c core.fsmonitor=false \
      -c core.untrackedCache=false -c diff.ignoreSubmodules=all \
      -c status.submoduleSummary=false -c submodule.recurse=false \
      -c fetch.recurseSubmodules=false -c credential.helper= \
      -c credential.interactive=never -c protocol.allow=never \
      -c protocol.https.allow=always "$@"
}
V26_MANIFEST_COMMIT="${V26_MANIFEST_COMMIT:?set the pinned manifest commit}"
V26_EXPECTED_COMMIT="${V26_AUTHENTICATION_RECEIPT_COMMIT:?set the authentication-receipt commit}"
V26_CHECKOUT="${V26_AUTHENTICATION_RECEIPT_CHECKOUT:?set the fresh receipt-bound checkout}"
V26_SOURCE_CHECKOUT="${V26_AUTHORIZATION_CHECKOUT:?set the original authorization checkout}"
V26_REMOTE_REF='refs/heads/codex/v26-runtime-preflight'
V26_ORIGIN_URL='https://github.com/matthew-zhao/epiagentbench.git'
V26_PUBLIC_AUTHENTICATION='results/development-matched-50x6-v26.authentication.json'
[[ "$V26_MANIFEST_COMMIT" =~ ^[0-9a-f]{40}$ ]]
[[ "$V26_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
cd "$V26_CHECKOUT"
test "$(v26_git ls-remote "$V26_ORIGIN_URL" "$V26_REMOTE_REF" | /usr/bin/cut -f1)" = \
  "$V26_EXPECTED_COMMIT"
test "$(v26_git rev-parse HEAD)" = "$V26_EXPECTED_COMMIT"
test "$(v26_git rev-parse HEAD^)" = "$V26_MANIFEST_COMMIT"
test -z "$(v26_git status --porcelain=v1 --untracked-files=all --ignore-submodules=all)"
test "$(v26_git diff --no-ext-diff --ignore-submodules=all --name-status \
  "$V26_MANIFEST_COMMIT" "$V26_EXPECTED_COMMIT")" = \
  $'A\t'"$V26_PUBLIC_AUTHENTICATION"
cmp -s \
  "$V26_SOURCE_CHECKOUT/$V26_PUBLIC_AUTHENTICATION" \
  "$V26_PUBLIC_AUTHENTICATION"
)
```

Only after those checks pass is the authentication receipt pinned. Then,
before supervisor generation, create a fresh supervisor root and fresh Cursor
Keychain service in an operator-visible terminal:

```bash
(
set -euo pipefail
PATH='/usr/bin:/bin:/usr/sbin:/sbin'
export PATH
umask 077
v26_git() {
  /usr/bin/env -i \
    HOME=/var/empty LC_ALL=C \
    PATH=/usr/bin:/bin:/usr/sbin:/sbin TMPDIR=/private/tmp \
    GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_SYSTEM=/dev/null \
    GIT_CONFIG_GLOBAL=/dev/null GIT_OPTIONAL_LOCKS=0 \
    GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/usr/bin/false \
    SSH_ASKPASS=/usr/bin/false \
    /usr/bin/git --no-pager \
      -c core.hooksPath=/dev/null -c core.fsmonitor=false \
      -c core.untrackedCache=false -c diff.ignoreSubmodules=all \
      -c status.submoduleSummary=false -c submodule.recurse=false \
      -c fetch.recurseSubmodules=false -c credential.helper= \
      -c credential.interactive=never -c protocol.allow=never \
      -c protocol.https.allow=always "$@"
}
V26_PYTHON="${EPIAGENTBENCH_PYTHON:?set the absolute isolated EpiAgentBench Python path}"
V26_RUNTIME_CACHE="$HOME/.codex/epiagentbench-v26-runtime-cache"
V26_EXPECTED_COMMIT="${V26_AUTHENTICATION_RECEIPT_COMMIT:?set the exact published authentication-receipt commit}"
V26_REPOSITORY_ROOT="${V26_AUTHENTICATION_RECEIPT_CHECKOUT:?set the clean authentication-receipt-bound checkout}"
V26_KEY="$HOME/.codex/epiagentbench-v26-secrets/panel-auth.key"
V26_PRIVATE_STATE="$HOME/.codex/epiagentbench-v26-state/development-matched-50x6-v26.private.json"
[[ "$V26_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
test -x "$V26_PYTHON"
cd "$V26_REPOSITORY_ROOT"
test "$(v26_git rev-parse HEAD)" = "$V26_EXPECTED_COMMIT"
test -z "$(v26_git status --porcelain=v1 --untracked-files=all --ignore-submodules=all)"
"$V26_PYTHON" -I -S -B \
  examples/run_development_matched_panel.py bind-receipt \
  --runtime-cache-dir "$V26_RUNTIME_CACHE" \
  --operation authentication \
  --authentication-key "$V26_KEY" \
  --claude-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v26-credentials/claude" \
  --codex-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v26-credentials/codex" \
  --private-state "$V26_PRIVATE_STATE" \
  --public-manifest \
    results/development-matched-50x6-v26.manifest.json
test ! -e "$HOME/.codex/epiagentbench-v26-supervisors"
test ! -L "$HOME/.codex/epiagentbench-v26-supervisors"
if security find-generic-password \
  -a "$USER" \
  -s epiagentbench-cursor-v26 >/dev/null 2>&1; then
  echo "Refusing to reuse the V26 Cursor Keychain service" >&2
  exit 1
fi
mkdir "$HOME/.codex/epiagentbench-v26-supervisors"
chmod 700 "$HOME/.codex/epiagentbench-v26-supervisors"
/usr/bin/security add-generic-password \
  -a "$USER" \
  -s epiagentbench-cursor-v26 \
  -w
)
```

`bind-receipt` launches no authentication helper or provider. It verifies that
the sanitized authentication receipt is tracked with the exact bytes at the
clean checkout's `HEAD`, then seals that publishing commit into authenticated
private state exactly once. A clean descendant checkout may later move without
rebinding; unrelated history, dirty bytes, or a second commit binding fail
closed. For each supervisor action, finalization exact-compares a fresh authenticated read
against the action's original authenticated snapshot before it mutates durable
state.

### V26 post-completion release boundary

The outer worker runs with `-I -S` and intentionally has no scientific
site-packages. It therefore never re-imports Starsim or recomputes installed
distribution identities after the supervised child completes. Those live
checks remain mandatory before and after every provider call. Release instead
re-hashes the tracked source contract and revalidates the sealed public hashes,
authenticated preparation/runtime-cache binding, cohort manifest, and every
private pack. Owner-only cache contents may evolve only inside the sealed root
and three fixed top-level cache directories; symlinks, public permissions,
filesystem escape, top-level topology replacement, and resource-limit
violations still fail closed.

One nonblocking owner control lock covers the full local release state machine.
A request made before authenticated core completion, or while another owner
holds that lock, changes no worker state and invokes no finalizer. Once the
worker durably enters `release_pending`, any finite release failure is committed
while the same lock remains held; a second invocation cannot race the
classification or repeat the local publication attempt.

Authenticated status schema `epiagentbench.launchd_worker_status.v5` exposes
only these release codes:

- `release_completion_attestation_invalid`
- `release_runtime_binding_invalid`
- `release_private_state_invalid`
- `release_contract_binding_invalid`
- `release_candidate_invalid`
- `release_public_watermark_invalid`
- `release_cohort_retirement_failed`
- `release_private_commit_failed`
- `release_public_commit_failed`
- `release_postcommit_attestation_failed`
- `release_internal`

The code identifies only a coarse gate; exception text is never persisted or
published. Every code is terminal and non-retryable. Preserve the runtime,
perform a provider-free offline audit, supersede the panel, and create a fresh
version. Never restart the worker, child, authentication ceremony, or provider.

### V26 model-invocation accounting boundary

The preflight and production supervisors use the same durable boundary:

- a profile or assignment attempt may begin before any model-bearing process;
- non-model CLI readiness checks run before the model-invocation marker;
- a readiness timeout is typed as `provider_cli_readiness_timeout`, with
  failure stage and timeout stage `provider_cli_readiness`;
- the evaluator persists `model_invocation.started` only in the callback
  immediately before the actual model-bearing process spawn;
- if that marker cannot be persisted, the process is not spawned;
- `model_invocation.finished` is persisted only after the model-bearing
  process returns and reaches its corresponding completion boundary; and
- conservative chargeability is derived from the durable model-invocation
  state, not from the earlier attempt state.

Accordingly, a readiness timeout with
`model_invocation_state = "not_started"` contributes zero conservatively
chargeable model invocations. In production it is released only as the finite
transport-void reason `provider_cli_readiness_timeout`, with both
`failure_stage` and `timeout_stage` set to `provider_cli_readiness`; the same
one-shot worker then advances to the next frozen assignment. A failure after
`model_invocation_state = "started_not_finished"` remains conservatively
chargeable, including an ambiguity between marker persistence and process
creation. This is intentionally asymmetric: non-model readiness probes are not
counted as model calls, while an interrupted or ambiguous model-bearing launch
cannot disappear from spend accounting. A Codex-authentication incident is
created only after that durable model-invocation marker or for an explicit
Codex credential-state incident; a generic pre-marker control failure does not
independently poison Codex authentication. A final-result checkpoint failure
after provider-process quiescence, the post-call supervisor boundary, and
credential attestations have all succeeded records an execution incident but
does not mark Codex authentication ambiguous.

These fields and semantics were introduced in V19 and are retained unchanged
by V26. The V18 receipt retains its legacy `invocation_state`,
`failed_provider_invocation_state`, failure stage, incident, and one-call
conservative accounting exactly as published.

## 11. Later only: complete six-call preflight supervisor commands

After the exact acknowledgement, successful foreground authentication, and
publication of its sanitized receipt, materialize a clean checkout at that
published receipt commit. Then generate, install, inspect, and start the
preflight exactly once:

```bash
(
set -euo pipefail
v26_git() {
  /usr/bin/env -i HOME=/var/empty LC_ALL=C \
    PATH=/usr/bin:/bin:/usr/sbin:/sbin TMPDIR=/private/tmp \
    GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_SYSTEM=/dev/null \
    GIT_CONFIG_GLOBAL=/dev/null GIT_OPTIONAL_LOCKS=0 \
    GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/usr/bin/false \
    SSH_ASKPASS=/usr/bin/false \
    /usr/bin/git --no-pager \
      -c core.hooksPath=/dev/null -c core.fsmonitor=false \
      -c core.untrackedCache=false -c diff.ignoreSubmodules=all \
      -c status.submoduleSummary=false -c submodule.recurse=false \
      -c fetch.recurseSubmodules=false -c credential.helper= \
      -c credential.interactive=never -c protocol.allow=never \
      -c protocol.https.allow=always "$@"
}
V26_PYTHON="${EPIAGENTBENCH_PYTHON:?set the absolute isolated EpiAgentBench Python path}"
V26_RUNTIME_CACHE="$HOME/.codex/epiagentbench-v26-runtime-cache"
V26_EXPECTED_COMMIT="${V26_AUTHENTICATION_RECEIPT_COMMIT:?set the exact published authentication-receipt commit}"
V26_REPOSITORY_ROOT="${V26_EXECUTION_CHECKOUT:?set the clean receipt-bound execution checkout}"
V26_KEY="$HOME/.codex/epiagentbench-v26-secrets/panel-auth.key"
V26_PRIVATE_STATE="$HOME/.codex/epiagentbench-v26-state/development-matched-50x6-v26.private.json"
V26_RUNTIME="$HOME/.codex/epiagentbench-v26-supervisors/preflight"
[[ "$V26_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
test -x "$V26_PYTHON"
cd "$V26_REPOSITORY_ROOT"
test "$(v26_git rev-parse HEAD)" = "$V26_EXPECTED_COMMIT"
test -z "$(v26_git status --porcelain=v1 --untracked-files=all --ignore-submodules=all)"
"$V26_PYTHON" -I -S -B \
  examples/run_persistent_panel_supervisor.py generate \
  --operation preflight \
  --runtime-dir "$V26_RUNTIME" \
  --repository-root "$V26_REPOSITORY_ROOT" \
  --python-executable "$V26_PYTHON" \
  --runtime-cache-dir "$V26_RUNTIME_CACHE" \
  --authentication-key "$V26_KEY" \
  --claude-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v26-credentials/claude" \
  --codex-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v26-credentials/codex" \
  --private-state "$V26_PRIVATE_STATE" \
  --public-manifest \
    "$V26_REPOSITORY_ROOT/results/development-matched-50x6-v26.manifest.json" \
  --public-preflight \
    "$V26_REPOSITORY_ROOT/results/development-matched-50x6-v26.preflight.json" \
  --cursor-keychain-service epiagentbench-cursor-v26 \
  --cursor-keychain-account "$USER"
"$V26_PYTHON" -I -S -B \
  examples/run_persistent_panel_supervisor.py install \
  --runtime-dir "$V26_RUNTIME" \
  --authentication-key "$V26_KEY"
"$V26_PYTHON" -I -S -B \
  examples/run_persistent_panel_supervisor.py status \
  --runtime-dir "$V26_RUNTIME" \
  --authentication-key "$V26_KEY"
# Start only if authenticated status is exactly inactive and not-started.
"$V26_PYTHON" -I -S -B \
  examples/run_persistent_panel_supervisor.py start \
  --runtime-dir "$V26_RUNTIME" \
  --authentication-key "$V26_KEY"
)
```

Never call `start` a second time. Never restart, retry, reorder, parallelize,
stop, boot out, uninstall, or modify an active/frozen run. The generated
LaunchAgent recomputes the exact cache and Python/bootstrap bindings, compares
their opaque public hashes, then seals the complete raw environment,
symlink/module-origin topology, device/inode/UID metadata, and inventory in its
authenticated owner-only config. The selected Python launch path also
necessarily appears in the local owner-only plist/command; no other raw
binding topology belongs there.

## 12. Later only: complete production supervisor commands

Only after authenticated supervisor status and the closed-schema public
receipt both show all six profiles passed may the existing receipt bytes be
published. Do not rerun the preflight or regenerate the receipt. Copy the
untracked receipt from the authentication-receipt-bound execution checkout
into the clean GitButler workspace through the create-once provider-free
publisher:

```bash
(
set -euo pipefail
PATH='/usr/bin:/bin:/usr/sbin:/sbin'
export PATH
umask 077
v26_git() {
  /usr/bin/env -i \
    HOME=/var/empty LC_ALL=C \
    PATH=/usr/bin:/bin:/usr/sbin:/sbin TMPDIR=/private/tmp \
    GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_SYSTEM=/dev/null \
    GIT_CONFIG_GLOBAL=/dev/null GIT_OPTIONAL_LOCKS=0 \
    GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/usr/bin/false \
    SSH_ASKPASS=/usr/bin/false \
    /usr/bin/git --no-pager \
      -c core.hooksPath=/dev/null -c core.fsmonitor=false \
      -c core.untrackedCache=false -c diff.ignoreSubmodules=all \
      -c status.submoduleSummary=false -c submodule.recurse=false \
      -c fetch.recurseSubmodules=false -c credential.helper= \
      -c credential.interactive=never -c protocol.allow=never \
      -c protocol.https.allow=always "$@"
}
V26_PYTHON="${EPIAGENTBENCH_PYTHON:?set the pinned isolated Python}"
V26_RUNTIME_STAGING="$HOME/.codex/epiagentbench-v26-runtime-receipt-staging"
V26_CLEAN_HOME="$V26_RUNTIME_STAGING/clean-home"
V26_CLEAN_TMP="$V26_RUNTIME_STAGING/clean-tmp"
V26_ACCOUNT_NAME="$(/usr/bin/id -un)"
V26_ACCOUNT_SHELL="$(/usr/bin/dscl . -read \
  "/Users/$V26_ACCOUNT_NAME" UserShell | /usr/bin/awk '{print $2}')"
V26_CF_USER_TEXT_ENCODING="$(/usr/bin/printf \
  '0x%X:0x0:0x0' "$(/usr/bin/id -u)")"
V26_PROVIDER_FREE_ENV=(
  /usr/bin/env -i
  "HOME=$V26_CLEAN_HOME"
  "LC_ALL=C.UTF-8"
  "LOGNAME=$V26_ACCOUNT_NAME"
  "PATH=/usr/bin:/bin:/usr/sbin:/sbin"
  "SHELL=$V26_ACCOUNT_SHELL"
  "TMPDIR=$V26_CLEAN_TMP"
  "USER=$V26_ACCOUNT_NAME"
  "__CF_USER_TEXT_ENCODING=$V26_CF_USER_TEXT_ENCODING"
)
v26_provider_free_python() {
  "${V26_PROVIDER_FREE_ENV[@]}" "$V26_PYTHON" -I -S -B "$@"
}
v26_assert_provider_free_environment() {
  local actual expected
  actual="$("${V26_PROVIDER_FREE_ENV[@]}" /usr/bin/env | /usr/bin/sort)"
  expected="$(/usr/bin/printf '%s\n' \
    "HOME=$V26_CLEAN_HOME" "LC_ALL=C.UTF-8" \
    "LOGNAME=$V26_ACCOUNT_NAME" \
    "PATH=/usr/bin:/bin:/usr/sbin:/sbin" \
    "SHELL=$V26_ACCOUNT_SHELL" "TMPDIR=$V26_CLEAN_TMP" \
    "USER=$V26_ACCOUNT_NAME" \
    "__CF_USER_TEXT_ENCODING=$V26_CF_USER_TEXT_ENCODING" |
    /usr/bin/sort)"
  test "$actual" = "$expected"
}
v26_assert_clean_scratch() {
  local observed
  observed="$(/usr/bin/find "$V26_CLEAN_HOME" -mindepth 1 -print -quit)" ||
    return 1
  test -z "$observed"
  observed="$(/usr/bin/find "$V26_CLEAN_TMP" -mindepth 1 -print -quit)" ||
    return 1
  test -z "$observed"
}
V26_EXPECTED_COMMIT="${V26_AUTHENTICATION_RECEIPT_COMMIT:?set the pinned authentication-receipt commit}"
V26_SOURCE_CHECKOUT="${V26_EXECUTION_CHECKOUT:?set the completed preflight checkout}"
V26_GITBUTLER_WORKSPACE="${V26_GITBUTLER_WORKSPACE:?set the primary GitButler workspace}"
V26_REMOTE_REF='refs/heads/codex/v26-runtime-preflight'
V26_ORIGIN_URL='https://github.com/matthew-zhao/epiagentbench.git'
V26_PUBLIC_PREFLIGHT='results/development-matched-50x6-v26.preflight.json'
[[ "$V26_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
cd "$V26_SOURCE_CHECKOUT"
test "$(v26_git rev-parse HEAD)" = "$V26_EXPECTED_COMMIT"
test -f "$V26_PUBLIC_PREFLIGHT"
test ! -L "$V26_PUBLIC_PREFLIGHT"
test "$(v26_git status --porcelain=v1 --untracked-files=all --ignore-submodules=all)" = \
  "?? $V26_PUBLIC_PREFLIGHT"
cd "$V26_GITBUTLER_WORKSPACE"
test "$(v26_git ls-remote "$V26_ORIGIN_URL" "$V26_REMOTE_REF" | /usr/bin/cut -f1)" = \
  "$V26_EXPECTED_COMMIT"
test -z "$(v26_git status --porcelain=v1 --untracked-files=all --ignore-submodules=all)"
test ! -e "$V26_PUBLIC_PREFLIGHT"
test ! -L "$V26_PUBLIC_PREFLIGHT"
v26_assert_provider_free_environment
v26_assert_clean_scratch
v26_provider_free_python \
  examples/run_development_matched_panel.py \
  publish-provider-free-json \
  --source "$V26_SOURCE_CHECKOUT/$V26_PUBLIC_PREFLIGHT" \
  --destination "$V26_PUBLIC_PREFLIGHT"
v26_assert_provider_free_environment
v26_assert_clean_scratch
cmp -s \
  "$V26_SOURCE_CHECKOUT/$V26_PUBLIC_PREFLIGHT" \
  "$V26_PUBLIC_PREFLIGHT"
test "$(v26_git status --porcelain=v1 --untracked-files=all --ignore-submodules=all)" = \
  "?? $V26_PUBLIC_PREFLIGHT"
)
```

Commit exactly that file, push only the named branch through GitButler, and
record the resulting remote tip:

```text
but commit codex/v26-runtime-preflight \
  -m "Publish V26 passing preflight receipt" \
  --changes <exact-preflight-receipt-file-id>
but push codex/v26-runtime-preflight
```

Set `V26_PREFLIGHT_RECEIPT_COMMIT` to the exact 40-hex remote tip. Materialize
a fresh clean checkout at that tip and pin both history and bytes before any
production supervisor is generated:

```bash
(
set -euo pipefail
PATH='/usr/bin:/bin:/usr/sbin:/sbin'
export PATH
v26_git() {
  /usr/bin/env -i \
    HOME=/var/empty LC_ALL=C \
    PATH=/usr/bin:/bin:/usr/sbin:/sbin TMPDIR=/private/tmp \
    GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_SYSTEM=/dev/null \
    GIT_CONFIG_GLOBAL=/dev/null GIT_OPTIONAL_LOCKS=0 \
    GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/usr/bin/false \
    SSH_ASKPASS=/usr/bin/false \
    /usr/bin/git --no-pager \
      -c core.hooksPath=/dev/null -c core.fsmonitor=false \
      -c core.untrackedCache=false -c diff.ignoreSubmodules=all \
      -c status.submoduleSummary=false -c submodule.recurse=false \
      -c fetch.recurseSubmodules=false -c credential.helper= \
      -c credential.interactive=never -c protocol.allow=never \
      -c protocol.https.allow=always "$@"
}
V26_AUTHENTICATION_RECEIPT_COMMIT="${V26_AUTHENTICATION_RECEIPT_COMMIT:?set the authentication-receipt commit}"
V26_EXPECTED_COMMIT="${V26_PREFLIGHT_RECEIPT_COMMIT:?set the preflight-receipt commit}"
V26_CHECKOUT="${V26_PRODUCTION_CHECKOUT:?set the fresh preflight-receipt-bound checkout}"
V26_SOURCE_CHECKOUT="${V26_EXECUTION_CHECKOUT:?set the completed preflight checkout}"
V26_REMOTE_REF='refs/heads/codex/v26-runtime-preflight'
V26_ORIGIN_URL='https://github.com/matthew-zhao/epiagentbench.git'
V26_PUBLIC_PREFLIGHT='results/development-matched-50x6-v26.preflight.json'
[[ "$V26_AUTHENTICATION_RECEIPT_COMMIT" =~ ^[0-9a-f]{40}$ ]]
[[ "$V26_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
cd "$V26_CHECKOUT"
test "$(v26_git ls-remote "$V26_ORIGIN_URL" "$V26_REMOTE_REF" | /usr/bin/cut -f1)" = \
  "$V26_EXPECTED_COMMIT"
test "$(v26_git rev-parse HEAD)" = "$V26_EXPECTED_COMMIT"
test "$(v26_git rev-parse HEAD^)" = \
  "$V26_AUTHENTICATION_RECEIPT_COMMIT"
test -z "$(v26_git status --porcelain=v1 --untracked-files=all --ignore-submodules=all)"
test "$(v26_git diff --no-ext-diff --ignore-submodules=all --name-status \
  "$V26_AUTHENTICATION_RECEIPT_COMMIT" "$V26_EXPECTED_COMMIT")" = \
  $'A\t'"$V26_PUBLIC_PREFLIGHT"
cmp -s \
  "$V26_SOURCE_CHECKOUT/$V26_PUBLIC_PREFLIGHT" \
  "$V26_PUBLIC_PREFLIGHT"
)
```

Only after those checks pass may the provider-free `bind-receipt` call bind
the exact preflight publication commit, and only after that succeeds may
production be generated and started exactly once:

```bash
(
set -euo pipefail
v26_git() {
  /usr/bin/env -i HOME=/var/empty LC_ALL=C \
    PATH=/usr/bin:/bin:/usr/sbin:/sbin TMPDIR=/private/tmp \
    GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_SYSTEM=/dev/null \
    GIT_CONFIG_GLOBAL=/dev/null GIT_OPTIONAL_LOCKS=0 \
    GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/usr/bin/false \
    SSH_ASKPASS=/usr/bin/false \
    /usr/bin/git --no-pager \
      -c core.hooksPath=/dev/null -c core.fsmonitor=false \
      -c core.untrackedCache=false -c diff.ignoreSubmodules=all \
      -c status.submoduleSummary=false -c submodule.recurse=false \
      -c fetch.recurseSubmodules=false -c credential.helper= \
      -c credential.interactive=never -c protocol.allow=never \
      -c protocol.https.allow=always "$@"
}
V26_PYTHON="${EPIAGENTBENCH_PYTHON:?set the absolute isolated EpiAgentBench Python path}"
V26_RUNTIME_CACHE="$HOME/.codex/epiagentbench-v26-runtime-cache"
V26_EXPECTED_COMMIT="${V26_PREFLIGHT_RECEIPT_COMMIT:?set the exact published preflight-receipt commit}"
V26_REPOSITORY_ROOT="${V26_PRODUCTION_CHECKOUT:?set the clean preflight-receipt-bound checkout}"
V26_KEY="$HOME/.codex/epiagentbench-v26-secrets/panel-auth.key"
V26_PRIVATE_STATE="$HOME/.codex/epiagentbench-v26-state/development-matched-50x6-v26.private.json"
V26_RUNTIME="$HOME/.codex/epiagentbench-v26-supervisors/production"
[[ "$V26_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
test -x "$V26_PYTHON"
cd "$V26_REPOSITORY_ROOT"
test "$(v26_git rev-parse HEAD)" = "$V26_EXPECTED_COMMIT"
test -z "$(v26_git status --porcelain=v1 --untracked-files=all --ignore-submodules=all)"
"$V26_PYTHON" -I -S -B \
  examples/run_development_matched_panel.py bind-receipt \
  --runtime-cache-dir "$V26_RUNTIME_CACHE" \
  --operation preflight \
  --authentication-key "$V26_KEY" \
  --claude-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v26-credentials/claude" \
  --codex-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v26-credentials/codex" \
  --private-state "$V26_PRIVATE_STATE" \
  --public-manifest \
    "$V26_REPOSITORY_ROOT/results/development-matched-50x6-v26.manifest.json"
"$V26_PYTHON" -I -S -B \
  examples/run_persistent_panel_supervisor.py generate \
  --operation production \
  --runtime-dir "$V26_RUNTIME" \
  --repository-root "$V26_REPOSITORY_ROOT" \
  --python-executable "$V26_PYTHON" \
  --runtime-cache-dir "$V26_RUNTIME_CACHE" \
  --authentication-key "$V26_KEY" \
  --claude-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v26-credentials/claude" \
  --codex-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v26-credentials/codex" \
  --private-state "$V26_PRIVATE_STATE" \
  --public-manifest \
    "$V26_REPOSITORY_ROOT/results/development-matched-50x6-v26.manifest.json" \
  --public-results \
    "$V26_REPOSITORY_ROOT/results/development-matched-50x6-v26.json" \
  --cursor-keychain-service epiagentbench-cursor-v26 \
  --cursor-keychain-account "$USER"
"$V26_PYTHON" -I -S -B \
  examples/run_persistent_panel_supervisor.py install \
  --runtime-dir "$V26_RUNTIME" \
  --authentication-key "$V26_KEY"
"$V26_PYTHON" -I -S -B \
  examples/run_persistent_panel_supervisor.py status \
  --runtime-dir "$V26_RUNTIME" \
  --authentication-key "$V26_KEY"
# Start only if authenticated status is exactly inactive and not-started.
"$V26_PYTHON" -I -S -B \
  examples/run_persistent_panel_supervisor.py start \
  --runtime-dir "$V26_RUNTIME" \
  --authentication-key "$V26_KEY"
)
```

The preflight `bind-receipt` step is also provider-free and create-once. It
must succeed at the exact clean commit containing the passed public preflight
receipt before production supervisor generation.

## Provider-free terminal-receipt recovery

If a supervisor is already terminal and an offline audit proves that
authenticated private state contains a terminal incident or sealed terminal
preflight candidate but the corresponding public write is missing, do not
restart any supervisor or evaluator. For a terminal preflight, the only
permitted recovery is this self-contained, provider-free command:

```bash
(
set -euo pipefail
v26_git() {
  /usr/bin/env -i HOME=/var/empty LC_ALL=C \
    PATH=/usr/bin:/bin:/usr/sbin:/sbin TMPDIR=/private/tmp \
    GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_SYSTEM=/dev/null \
    GIT_CONFIG_GLOBAL=/dev/null GIT_OPTIONAL_LOCKS=0 \
    GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/usr/bin/false \
    SSH_ASKPASS=/usr/bin/false \
    /usr/bin/git --no-pager \
      -c core.hooksPath=/dev/null -c core.fsmonitor=false \
      -c core.untrackedCache=false -c diff.ignoreSubmodules=all \
      -c status.submoduleSummary=false -c submodule.recurse=false \
      -c fetch.recurseSubmodules=false -c credential.helper= \
      -c credential.interactive=never -c protocol.allow=never \
      -c protocol.https.allow=always "$@"
}
V26_PYTHON="${EPIAGENTBENCH_PYTHON:?set the absolute isolated EpiAgentBench Python path}"
V26_RUNTIME_CACHE="$HOME/.codex/epiagentbench-v26-runtime-cache"
V26_EXPECTED_COMMIT="${V26_AUTHENTICATION_RECEIPT_COMMIT:?set the exact published authentication-receipt commit}"
V26_REPOSITORY_ROOT="${V26_PREFLIGHT_TERMINAL_CHECKOUT:?set the clean terminal preflight checkout}"
V26_KEY="$HOME/.codex/epiagentbench-v26-secrets/panel-auth.key"
V26_PRIVATE_STATE="$HOME/.codex/epiagentbench-v26-state/development-matched-50x6-v26.private.json"
[[ "$V26_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
test -x "$V26_PYTHON"
cd "$V26_REPOSITORY_ROOT"
test "$(v26_git rev-parse HEAD)" = "$V26_EXPECTED_COMMIT"
test -z "$(v26_git status --porcelain=v1 --untracked-files=all --ignore-submodules=all)"
"$V26_PYTHON" -I -S -B \
  examples/run_development_matched_panel.py reconcile-terminal-receipt \
  --runtime-cache-dir "$V26_RUNTIME_CACHE" \
  --operation preflight \
  --authentication-key "$V26_KEY" \
  --private-state "$V26_PRIVATE_STATE" \
  --public-manifest \
    "$V26_REPOSITORY_ROOT/results/development-matched-50x6-v26.manifest.json" \
  --public-output \
    "$V26_REPOSITORY_ROOT/results/development-matched-50x6-v26.preflight.json"
)
```

For a durable production incident, use the separate preflight-receipt-bound
checkout and the canonical production output:

```bash
(
set -euo pipefail
v26_git() {
  /usr/bin/env -i HOME=/var/empty LC_ALL=C \
    PATH=/usr/bin:/bin:/usr/sbin:/sbin TMPDIR=/private/tmp \
    GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_SYSTEM=/dev/null \
    GIT_CONFIG_GLOBAL=/dev/null GIT_OPTIONAL_LOCKS=0 \
    GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/usr/bin/false \
    SSH_ASKPASS=/usr/bin/false \
    /usr/bin/git --no-pager \
      -c core.hooksPath=/dev/null -c core.fsmonitor=false \
      -c core.untrackedCache=false -c diff.ignoreSubmodules=all \
      -c status.submoduleSummary=false -c submodule.recurse=false \
      -c fetch.recurseSubmodules=false -c credential.helper= \
      -c credential.interactive=never -c protocol.allow=never \
      -c protocol.https.allow=always "$@"
}
V26_PYTHON="${EPIAGENTBENCH_PYTHON:?set the absolute isolated EpiAgentBench Python path}"
V26_RUNTIME_CACHE="$HOME/.codex/epiagentbench-v26-runtime-cache"
V26_EXPECTED_COMMIT="${V26_PREFLIGHT_RECEIPT_COMMIT:?set the exact published preflight-receipt commit}"
V26_REPOSITORY_ROOT="${V26_PRODUCTION_TERMINAL_CHECKOUT:?set the clean terminal production checkout}"
V26_KEY="$HOME/.codex/epiagentbench-v26-secrets/panel-auth.key"
V26_PRIVATE_STATE="$HOME/.codex/epiagentbench-v26-state/development-matched-50x6-v26.private.json"
[[ "$V26_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
test -x "$V26_PYTHON"
cd "$V26_REPOSITORY_ROOT"
test "$(v26_git rev-parse HEAD)" = "$V26_EXPECTED_COMMIT"
test -z "$(v26_git status --porcelain=v1 --untracked-files=all --ignore-submodules=all)"
"$V26_PYTHON" -I -S -B \
  examples/run_development_matched_panel.py reconcile-terminal-receipt \
  --runtime-cache-dir "$V26_RUNTIME_CACHE" \
  --operation production \
  --authentication-key "$V26_KEY" \
  --private-state "$V26_PRIVATE_STATE" \
  --public-manifest \
    "$V26_REPOSITORY_ROOT/results/development-matched-50x6-v26.manifest.json" \
  --public-output \
    "$V26_REPOSITORY_ROOT/results/development-matched-50x6-v26.json"
)
```

Reconciliation launches zero authentication helpers, providers, or models. It
publishes only the exact authenticated trace-free candidate, refuses
conflicting or noncanonical bytes, and never changes the supervisor's terminal
classification.

## Terminal rules

- Never reuse any V15, V16, V17, V18, V19, V20, V21, V22, V23, V24, or V25
  cohort, key, credential, state, cache, checkout, supervisor, runtime,
  Keychain service, or claim.
- Never create a V26 private artifact before the runtime receipt is committed,
  pushed through GitButler, pinned, and successfully re-attested.
- Never substitute a PATH-selected Python for the exact V5 interpreter, omit
  `-I -S -B`, or inject `PYTHONPATH`/startup hooks.
- Never place a receipt, verification summary, or any other staging file
  inside the runtime-cache root; it may contain only `matplotlib`, `numba`, and
  `xdg`.
- Never change, recreate, relink, chmod, or relocate the bound cache tree.
- Never retry a freeze or prepare after the canonical pending freeze claim
  exists without its authenticated completion.
- Never retry a V26 freeze, preparation, preflight, production assignment, or
  durable supervisor start. Foreground authentication may retry only from the
  explicit `retryable_failed` ceremony state after process-group quiescence
  and an unchanged empty target have been proven; every terminal or running
  ceremony state rejects reuse.
- Never start foreground authentication from a Codex-owned PTY or an automated,
  backgrounded, detached, redirected, piped, or recorded shell. Use only the
  manually opened Terminal.app procedure in section 10.
- Never treat a provider credential, device-code page, browser callback, or
  temporary file as evidence that authentication passed. Only the
  authenticated private transition plus its sanitized public receipt can pass
  the gate.
- Never infer spend authorization from this runbook, receipt, or manifest.
- Never publish the raw Python entrypoint/bootstrap binding, cache paths,
  environment, inventory, or device/inode/UID metadata; only their opaque
  hashes belong in public receipts and manifests.
- Never expose provider output, credentials, prompts, observations, hidden
  episode identifiers/families, schedules, seeds, traces, or scores before the
  final release gate.
