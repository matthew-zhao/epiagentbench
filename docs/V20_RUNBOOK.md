# EpiAgentBench V20 execution runbook

> [!CAUTION]
> This runbook does not authorize authentication, a provider process, spend, a
> supervisor start, or a model call. The current preparation milestone ends
> after the public V20 manifest is validated, committed, pushed through
> GitButler, and pinned. Do not run the authorization or execution sections
> until the operator later supplies the exact manifest-bound acknowledgement.

V20 replaces the terminal V19 authentication setup. V19 completed its
provider-free runtime receipt, private freeze, manifest publication, and exact
spend authorization. Its first foreground authentication command omitted the
six runtime-cache variables that the bound contract expected from the caller,
so execution-contract attestation failed before the operator TTY or any
authentication helper. A corrected Codex device-login ceremony was then
cancelled after the at-most-once policy audit showed that V19 lacked a durable
transition for that early failure. V19 is terminal: zero model-bearing calls
started, no provider credential or public authentication receipt was created,
and no preflight profile, production assignment, score, or trace was released.
The missing device approval was not the root cause. V19 and every V19 private
namespace are non-resumable and forbidden for reuse.

V20 preserves V19's model-invocation accounting, authenticated LaunchAgent
environment, exact restoration, and atomic create-once publication. It removes
the foreground shell-environment dependency: every scientific-runtime-loading
operator command accepts one explicit bound runtime-cache directory, installs
the exact six variables internally before scientific imports, ignores poisoned
ambient values, and restores the caller's prior environment exactly.
Authentication also writes a
durable ceremony claim after the TTY gate but before live execution,
dependency, repository, credential, or provider checks. A post-claim integrity
failure becomes a finite terminal incident while provider statuses remain
truthfully not started, and a second authentication attempt is rejected.
Clean device-flow failures remain retryable only after process-group
quiescence and an unchanged empty credential namespace are proven. Each
authentication-helper attempt has a closed durable sequence:
`launch_pending`, `started` or `start_failed`, and, for a started helper,
`returned`. A provider can pass only after a recorded integer return code of
zero. A persisted launch-pending marker without either a started or
start-failed marker is conservatively ambiguous and can never be retried.
Terminal incidents record both the number of helper processes known to have
started and the separate number of ambiguous starts, recomputed from the
sealed attempt history. Execution, frozen-dependency, or credential drift
after a helper returns retains a distinct finite post-return failure code.

V20 uses a two-commit, provider-free preparation protocol:

1. publish and pin the V20 control-plane code;
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
by the byte-identical runtime-receipt commit. No V20 key, freeze claim, cohort,
credential namespace, private state, or manifest may exist before the second
commit is published and re-attested. The manifest is published afterward as a
separate commit, and this phase stops before authorization. It makes no
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
  `src` and V5 virtual-environment `site-packages` after the standard library;
- the clean source and CLI contracts at the pinned commit;
- a fresh runtime-cache v3 contract whose normalized, current-user `0700`
  root contains only exact current-user `0700` children `matplotlib`, `numba`,
  and `xdg`; below them the closed inventory contains at most 10,000
  descendants total (directories plus regular files), with owner-only,
  nonsymlinked, same-filesystem entries, single-link regular files of at most
  512 MiB each, and at most 4 GiB of regular-file content in total; and
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

The preflight launches no provider or authentication helper and requires no
key, cohort, credential directory, private state, or schedule.

## Frozen V20 identifiers

| Surface | V20 value |
|---|---|
| Panel and cohort | `development-matched-50x6-v20` |
| Top-level schema | `development_matched_panel_v20` |
| Runtime receipt | `results/development-matched-50x6-v20.runtime.json` |
| Required Python launch path | `/Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python` |
| Required Python flags | `-I -S -B` |
| Required Starsim | `3.5.1` |
| Persistent-supervisor contract | `epiagentbench.persistent_supervisor_contract.v9` |
| Execution-context protocol | `persistent-supervisor-v6` |
| LaunchAgent config | `epiagentbench.launchd_agent.v12` |
| Authentication setup | `epiagentbench.authentication_setup.v3` |
| Assignments | 50 episodes × 6 profiles = 300 |
| Per-call timeout | 1,800 seconds |
| Claude per-call ceiling | $5 |
| V20 current-run Claude ceiling | $510 (102 Claude calls × $5) |
| Prior conservative Claude ceiling | $80 |
| Cumulative acknowledgement ceiling | $590 ($510 + $80) |
| Required acknowledgement SHA-256 | `sha256:c192557a25bb6050be27b3ce2af60837c8a966a47368c67d2d6972a0dc9e73e7` |
| Codex/Cursor ceiling | unbounded |
| Cursor Keychain service | `epiagentbench-cursor-v20` |

V15 adds zero dollars to the prior ceiling because it launched no provider or
authentication helper and made no model call. V16 adds a conservative $5 for
its one started-not-finished Claude preflight call. V17 adds zero dollars
because its single control request was refused before any provider or model
process. V18 adds a conservative $5 because its legacy early marker cannot
prove that the first Claude model-bearing process never started, even though
the offline audit strongly indicates a non-model CLI readiness timeout. V19
adds zero dollars because authentication setup ended before any model-bearing
call and no Claude authentication helper started.

## Fresh V20 paths

```text
$HOME/.codex/epiagentbench-50x6-v20-runtime-worktree
$HOME/.codex/epiagentbench-50x6-v20-prepare-worktree
$HOME/.codex/epiagentbench-v20-runtime-cache
$HOME/.codex/epiagentbench-v20-runtime-receipt-staging
$HOME/.codex/epiagentbench-v20-cohort
$HOME/.codex/epiagentbench-v20-secrets/panel-auth.key
$HOME/.codex/epiagentbench-v20-secrets/.development-matched-50x6-v20.cohort-freeze-claim.v1.json
$HOME/.codex/epiagentbench-v20-secrets/.development-matched-50x6-v20.cohort-freeze-completion.v1.json
$HOME/.codex/epiagentbench-v20-state/development-matched-50x6-v20.private.json
$HOME/.codex/epiagentbench-v20-credentials/claude
$HOME/.codex/epiagentbench-v20-credentials/codex
$HOME/.codex/epiagentbench-v20-supervisors/preflight
$HOME/.codex/epiagentbench-v20-supervisors/production
```

The five public destinations are:

```text
results/development-matched-50x6-v20.runtime.json
results/development-matched-50x6-v20.manifest.json
results/development-matched-50x6-v20.authentication.json
results/development-matched-50x6-v20.preflight.json
results/development-matched-50x6-v20.json
```

Every shell block below is intentionally self-contained: it declares every
path or prior published commit it consumes. Every Python CLI/supervisor
invocation uses the approved V5 virtual-environment interpreter with
`-I -S -B`, and every block that can load the scientific runtime supplies the
exact bound cache root from which the CLI installs its cache environment.
Never replace `V20_PYTHON` with `python`, `python3`, a PATH lookup, or another
virtual environment. Never use `PYTHONPATH`; the isolated scripts build and
re-attest their only permitted import paths without executing `site`, `.pth`,
`sitecustomize`, or `usercustomize`.

## 1. Publish and pin the V20 control plane

Use the GitButler-managed primary workspace to commit and push the V20
control-plane changes on `codex/v20-runtime-preflight`. Never use `git push`
and never publish a private artifact. Record the exact 40-hex remote commit as
`V20_CONTROL_COMMIT`.

This first commit must not contain any V20 runtime receipt, manifest,
authentication receipt, preflight receipt, final result, key, cohort, private
state, credential directory, or supervisor runtime.

## 2. Validate the clean control-plane checkout

After the GitButler push, use an operator-approved GitButler-compatible
workflow to materialize a fresh clean checkout at the exact control-plane
commit. Set `V20_RUNTIME_CHECKOUT` to its absolute canonical path, then run
this validation block from the repository's primary checkout. The block is
read-only; it does not create or mutate a Git checkout.

```bash
set -euo pipefail
V20_PYTHON='/Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python'
V20_RUNTIME_CACHE="$HOME/.codex/epiagentbench-v20-runtime-cache"
V20_EXPECTED_COMMIT="${V20_CONTROL_COMMIT:?set the exact published control-plane commit}"
V20_REMOTE_REF='refs/heads/codex/v20-runtime-preflight'
V20_RUNTIME_CHECKOUT="${V20_RUNTIME_CHECKOUT:?set the absolute canonical path to the fresh control-plane checkout}"
[[ "$V20_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
test -x "$V20_PYTHON"
test "$(git ls-remote origin "$V20_REMOTE_REF" | cut -f1)" = \
  "$V20_EXPECTED_COMMIT"
test -d "$V20_RUNTIME_CHECKOUT" && test ! -L "$V20_RUNTIME_CHECKOUT"
test "$(cd "$V20_RUNTIME_CHECKOUT" && pwd -P)" = "$V20_RUNTIME_CHECKOUT"
cd "$V20_RUNTIME_CHECKOUT"
test "$(git rev-parse HEAD)" = "$V20_EXPECTED_COMMIT"
test -z "$(git status --porcelain --untracked-files=all)"
```

## 3. Prove freshness and create separate cache and staging roots

All five public outputs and all private V20 namespaces must be absent before
the cache is created. The cache is runtime state, not a cohort or credential
namespace. Its v3 contract permits exactly three children at the root:
`matplotlib`, `numba`, and `xdg`. Receipt bytes, command summaries, and all
other operator output therefore go into a distinct owner-only staging
directory that never overlaps the cache.

```bash
set -euo pipefail
umask 077
V20_PYTHON='/Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python'
V20_RUNTIME_CACHE="$HOME/.codex/epiagentbench-v20-runtime-cache"
V20_RUNTIME_STAGING="$HOME/.codex/epiagentbench-v20-runtime-receipt-staging"
V20_EXPECTED_COMMIT="${V20_CONTROL_COMMIT:?set the exact published control-plane commit}"
V20_RUNTIME_CHECKOUT="${V20_RUNTIME_CHECKOUT:?set the absolute canonical path to the fresh control-plane checkout}"
[[ "$V20_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
test -x "$V20_PYTHON"
cd "$V20_RUNTIME_CHECKOUT"
test "$(git rev-parse HEAD)" = "$V20_EXPECTED_COMMIT"
test -z "$(git status --porcelain --untracked-files=all)"
for candidate_path in \
  "$HOME/.codex/epiagentbench-v20-runtime-cache" \
  "$HOME/.codex/epiagentbench-v20-runtime-receipt-staging" \
  "$HOME/.codex/epiagentbench-v20-secrets" \
  "$HOME/.codex/epiagentbench-v20-state" \
  "$HOME/.codex/epiagentbench-v20-credentials" \
  "$HOME/.codex/epiagentbench-v20-supervisors" \
  "$HOME/.codex/epiagentbench-v20-cohort" \
  "results/development-matched-50x6-v20.runtime.json" \
  "results/development-matched-50x6-v20.manifest.json" \
  "results/development-matched-50x6-v20.authentication.json" \
  "results/development-matched-50x6-v20.preflight.json" \
  "results/development-matched-50x6-v20.json"; do
  if [ -e "$candidate_path" ] || [ -L "$candidate_path" ]; then
    echo "Refusing occupied V20 path: $candidate_path" >&2
    exit 1
  fi
done
mkdir "$V20_RUNTIME_CACHE"
mkdir "$V20_RUNTIME_STAGING"
mkdir \
  "$V20_RUNTIME_CACHE/matplotlib" \
  "$V20_RUNTIME_CACHE/numba" \
  "$V20_RUNTIME_CACHE/xdg"
chmod 700 \
  "$V20_RUNTIME_CACHE" \
  "$V20_RUNTIME_STAGING" \
  "$V20_RUNTIME_CACHE/matplotlib" \
  "$V20_RUNTIME_CACHE/numba" \
  "$V20_RUNTIME_CACHE/xdg"
```

## 4. Produce the provider-free runtime receipt twice

Both commands run at the exact control-plane commit and write outside the
repository. A byte difference is terminal for this preparation attempt.

```bash
set -euo pipefail
umask 077
V20_PYTHON='/Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python'
V20_RUNTIME_CACHE="$HOME/.codex/epiagentbench-v20-runtime-cache"
V20_RUNTIME_STAGING="$HOME/.codex/epiagentbench-v20-runtime-receipt-staging"
V20_EXPECTED_COMMIT="${V20_CONTROL_COMMIT:?set the exact published control-plane commit}"
V20_RUNTIME_CHECKOUT="${V20_RUNTIME_CHECKOUT:?set the absolute canonical path to the fresh control-plane checkout}"
V20_RUNTIME_ONE="$V20_RUNTIME_STAGING/preflight-1.json"
V20_RUNTIME_TWO="$V20_RUNTIME_STAGING/preflight-2.json"
[[ "$V20_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
cd "$V20_RUNTIME_CHECKOUT"
test "$(git rev-parse HEAD)" = "$V20_EXPECTED_COMMIT"
test -z "$(git status --porcelain --untracked-files=all)"
test -x "$V20_PYTHON"
test -d "$V20_RUNTIME_STAGING" && test ! -L "$V20_RUNTIME_STAGING"
test "$(stat -f '%Lp' "$V20_RUNTIME_STAGING")" = 700
test ! -e "$V20_RUNTIME_ONE" && test ! -L "$V20_RUNTIME_ONE"
test ! -e "$V20_RUNTIME_TWO" && test ! -L "$V20_RUNTIME_TWO"
"$V20_PYTHON" -I -S -B \
  examples/run_development_matched_panel.py \
  preflight-preparation-runtime \
  --expected-benchmark-base-commit "$V20_EXPECTED_COMMIT" \
  --runtime-cache-dir "$V20_RUNTIME_CACHE" \
  --public-runtime-receipt "$V20_RUNTIME_ONE"
"$V20_PYTHON" -I -S -B \
  examples/run_development_matched_panel.py \
  preflight-preparation-runtime \
  --expected-benchmark-base-commit "$V20_EXPECTED_COMMIT" \
  --runtime-cache-dir "$V20_RUNTIME_CACHE" \
  --public-runtime-receipt "$V20_RUNTIME_TWO"
test -f "$V20_RUNTIME_ONE" && test ! -L "$V20_RUNTIME_ONE"
test -f "$V20_RUNTIME_TWO" && test ! -L "$V20_RUNTIME_TWO"
test "$(stat -f '%Lp' "$V20_RUNTIME_ONE")" = 644
test "$(stat -f '%Lp' "$V20_RUNTIME_TWO")" = 644
cmp -s "$V20_RUNTIME_ONE" "$V20_RUNTIME_TWO"
test "$(git rev-parse HEAD)" = "$V20_EXPECTED_COMMIT"
test -z "$(git status --porcelain --untracked-files=all)"
for candidate_path in \
  "$HOME/.codex/epiagentbench-v20-secrets" \
  "$HOME/.codex/epiagentbench-v20-state" \
  "$HOME/.codex/epiagentbench-v20-credentials" \
  "$HOME/.codex/epiagentbench-v20-supervisors" \
  "$HOME/.codex/epiagentbench-v20-cohort" \
  "results/development-matched-50x6-v20.runtime.json" \
  "results/development-matched-50x6-v20.manifest.json" \
  "results/development-matched-50x6-v20.authentication.json" \
  "results/development-matched-50x6-v20.preflight.json" \
  "results/development-matched-50x6-v20.json"; do
  if [ -e "$candidate_path" ] || [ -L "$candidate_path" ]; then
    echo "A V20 artifact appeared during provider-free preflight" >&2
    exit 1
  fi
done
```

The receipt is closed-schema public data. It contains aggregate smoke output,
path-free scientific identities, opaque Python/cache binding hashes, and
explicit zero provider/authentication process counters. It contains no raw
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
set -euo pipefail
umask 077
V20_PYTHON='/Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python'
V20_RUNTIME_CACHE="$HOME/.codex/epiagentbench-v20-runtime-cache"
V20_RUNTIME_STAGING="$HOME/.codex/epiagentbench-v20-runtime-receipt-staging"
V20_EXPECTED_COMMIT="${V20_CONTROL_COMMIT:?set the exact published control-plane commit}"
V20_GITBUTLER_WORKSPACE="${V20_GITBUTLER_WORKSPACE:?set the primary GitButler workspace}"
V20_PUBLIC_RUNTIME='results/development-matched-50x6-v20.runtime.json'
V20_RUNTIME_ONE="$V20_RUNTIME_STAGING/preflight-1.json"
V20_RUNTIME_TWO="$V20_RUNTIME_STAGING/preflight-2.json"
[[ "$V20_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
test -x "$V20_PYTHON"
cmp -s \
  "$V20_RUNTIME_ONE" \
  "$V20_RUNTIME_TWO"
cd "$V20_GITBUTLER_WORKSPACE"
for candidate_path in \
  "$V20_PUBLIC_RUNTIME" \
  "results/development-matched-50x6-v20.manifest.json" \
  "results/development-matched-50x6-v20.authentication.json" \
  "results/development-matched-50x6-v20.preflight.json" \
  "results/development-matched-50x6-v20.json"; do
  test ! -e "$candidate_path" && test ! -L "$candidate_path"
done
"$V20_PYTHON" -I -S -B \
  examples/run_development_matched_panel.py \
  publish-provider-free-json \
  --source "$V20_RUNTIME_ONE" \
  --destination "$V20_PUBLIC_RUNTIME"
cmp -s "$V20_RUNTIME_ONE" "$V20_PUBLIC_RUNTIME"
```

Run `but diff`, copy the exact file change ID for only the runtime receipt,
then commit it to the existing branch and push that named branch:

```text
but commit codex/v20-runtime-preflight \
  -m "Publish V20 scientific runtime receipt" \
  --changes <exact-runtime-receipt-file-id>
but push codex/v20-runtime-preflight
```

No direct `git push` is permitted. Verify the remote branch contains the exact
receipt bytes, and record its exact 40-hex tip as `V20_RECEIPT_COMMIT`. This is
the second provider-free commit.

## 6. Validate the receipt-bound checkout and verify before writing

Use an operator-approved GitButler-compatible workflow to materialize a second
fresh clean checkout rather than mutating or reusing the runtime checkout. Set
`V20_PREPARE_CHECKOUT` to its absolute canonical path. The expected commit for
every remaining preparation command is now the published runtime-receipt
commit, not the earlier control-plane commit. The block below only validates
the supplied checkout before beginning provider-free preparation.

```bash
set -euo pipefail
umask 077
V20_PYTHON='/Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python'
V20_RUNTIME_CACHE="$HOME/.codex/epiagentbench-v20-runtime-cache"
V20_RUNTIME_STAGING="$HOME/.codex/epiagentbench-v20-runtime-receipt-staging"
V20_EXPECTED_COMMIT="${V20_RECEIPT_COMMIT:?set the exact published runtime-receipt commit}"
V20_REMOTE_REF='refs/heads/codex/v20-runtime-preflight'
V20_PREPARE_CHECKOUT="${V20_PREPARE_CHECKOUT:?set the absolute canonical path to the fresh receipt-bound checkout}"
V20_PUBLIC_RUNTIME='results/development-matched-50x6-v20.runtime.json'
V20_VERIFICATION_OUTPUT="$V20_RUNTIME_STAGING/verification.json"
[[ "$V20_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
test -x "$V20_PYTHON"
test "$(git ls-remote origin "$V20_REMOTE_REF" | cut -f1)" = \
  "$V20_EXPECTED_COMMIT"
test -d "$V20_PREPARE_CHECKOUT" && test ! -L "$V20_PREPARE_CHECKOUT"
test "$(cd "$V20_PREPARE_CHECKOUT" && pwd -P)" = \
  "$V20_PREPARE_CHECKOUT"
cd "$V20_PREPARE_CHECKOUT"
test "$(git rev-parse HEAD)" = "$V20_EXPECTED_COMMIT"
test -z "$(git status --porcelain --untracked-files=all)"
test "$(git ls-files --error-unmatch "$V20_PUBLIC_RUNTIME")" = \
  "$V20_PUBLIC_RUNTIME"
test -f "$V20_PUBLIC_RUNTIME" && test ! -L "$V20_PUBLIC_RUNTIME"
for candidate_path in \
  "$HOME/.codex/epiagentbench-v20-secrets" \
  "$HOME/.codex/epiagentbench-v20-state" \
  "$HOME/.codex/epiagentbench-v20-credentials" \
  "$HOME/.codex/epiagentbench-v20-supervisors" \
  "$HOME/.codex/epiagentbench-v20-cohort" \
  "results/development-matched-50x6-v20.manifest.json" \
  "results/development-matched-50x6-v20.authentication.json" \
  "results/development-matched-50x6-v20.preflight.json" \
  "results/development-matched-50x6-v20.json"; do
  if [ -e "$candidate_path" ] || [ -L "$candidate_path" ]; then
    echo "Refusing occupied V20 path: $candidate_path" >&2
    exit 1
  fi
done
test ! -e "$V20_VERIFICATION_OUTPUT" && test ! -L "$V20_VERIFICATION_OUTPUT"
"$V20_PYTHON" -I -S -B \
  examples/run_development_matched_panel.py \
  verify-preparation-runtime \
  --preparation-runtime-receipt "$V20_PUBLIC_RUNTIME" \
  --expected-benchmark-base-commit "$V20_EXPECTED_COMMIT" \
  --runtime-cache-dir "$V20_RUNTIME_CACHE" \
  --public-verification-receipt "$V20_VERIFICATION_OUTPUT"
test -f "$V20_VERIFICATION_OUTPUT" && test ! -L "$V20_VERIFICATION_OUTPUT"
test "$(stat -f '%Lp' "$V20_VERIFICATION_OUTPUT")" = 644
test "$(git rev-parse HEAD)" = "$V20_EXPECTED_COMMIT"
test -z "$(git status --porcelain --untracked-files=all)"
```

A receipt, source, Python/bootstrap, installed-distribution, Starsim-smoke, or
closed cache-inventory mismatch stops before a key or cohort exists. Do not
repair or override a mismatch. The verification summary is staged outside the
cache, is written through the same atomic create-once boundary, and remains
operator-local.

## 7. Create fresh private prerequisites and freeze exactly once

This is the irreversible V20 preparation boundary. Use the matched V20
`freeze` command; do not call the generic `freeze-private-cohort` command.

```bash
set -euo pipefail
umask 077
set -o noclobber
V20_PYTHON='/Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python'
V20_RUNTIME_CACHE="$HOME/.codex/epiagentbench-v20-runtime-cache"
V20_RUNTIME_STAGING="$HOME/.codex/epiagentbench-v20-runtime-receipt-staging"
V20_EXPECTED_COMMIT="${V20_RECEIPT_COMMIT:?set the exact published runtime-receipt commit}"
V20_PREPARE_CHECKOUT="${V20_PREPARE_CHECKOUT:?set the absolute canonical path to the fresh receipt-bound checkout}"
V20_PUBLIC_RUNTIME='results/development-matched-50x6-v20.runtime.json'
V20_KEY="$HOME/.codex/epiagentbench-v20-secrets/panel-auth.key"
V20_FREEZE_CLAIM="$HOME/.codex/epiagentbench-v20-secrets/.development-matched-50x6-v20.cohort-freeze-claim.v1.json"
V20_COHORT="$HOME/.codex/epiagentbench-v20-cohort"
V20_FREEZE_OUTPUT="$V20_RUNTIME_STAGING/freeze-public.json"
[[ "$V20_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
test -x "$V20_PYTHON"
cd "$V20_PREPARE_CHECKOUT"
test "$(git rev-parse HEAD)" = "$V20_EXPECTED_COMMIT"
test -z "$(git status --porcelain --untracked-files=all)"
for candidate_path in \
  "$HOME/.codex/epiagentbench-v20-secrets" \
  "$HOME/.codex/epiagentbench-v20-state" \
  "$HOME/.codex/epiagentbench-v20-credentials" \
  "$HOME/.codex/epiagentbench-v20-supervisors" \
  "$V20_COHORT" \
  "results/development-matched-50x6-v20.manifest.json" \
  "results/development-matched-50x6-v20.authentication.json" \
  "results/development-matched-50x6-v20.preflight.json" \
  "results/development-matched-50x6-v20.json"; do
  if [ -e "$candidate_path" ] || [ -L "$candidate_path" ]; then
    echo "Refusing to reuse V20 path: $candidate_path" >&2
    exit 1
  fi
done
mkdir \
  "$HOME/.codex/epiagentbench-v20-secrets" \
  "$HOME/.codex/epiagentbench-v20-state" \
  "$HOME/.codex/epiagentbench-v20-credentials"
mkdir \
  "$HOME/.codex/epiagentbench-v20-credentials/claude" \
  "$HOME/.codex/epiagentbench-v20-credentials/codex"
chmod 700 \
  "$HOME/.codex/epiagentbench-v20-secrets" \
  "$HOME/.codex/epiagentbench-v20-state" \
  "$HOME/.codex/epiagentbench-v20-credentials" \
  "$HOME/.codex/epiagentbench-v20-credentials/claude" \
  "$HOME/.codex/epiagentbench-v20-credentials/codex"
openssl rand 32 > "$V20_KEY"
chmod 600 "$V20_KEY"
test ! -e "$V20_FREEZE_CLAIM" && test ! -L "$V20_FREEZE_CLAIM"
test ! -e "$V20_FREEZE_OUTPUT" && test ! -L "$V20_FREEZE_OUTPUT"
"$V20_PYTHON" -I -S -B \
  examples/run_development_matched_panel.py freeze \
  --preparation-runtime-receipt "$V20_PUBLIC_RUNTIME" \
  --expected-benchmark-base-commit "$V20_EXPECTED_COMMIT" \
  --runtime-cache-dir "$V20_RUNTIME_CACHE" \
  --authentication-key "$V20_KEY" \
  --output-directory "$V20_COHORT" \
  --freeze-claim "$V20_FREEZE_CLAIM" \
  > "$V20_FREEZE_OUTPUT"
```

`freeze` authenticates the canonical claim location against the key namespace,
creates the pending claim without replacement before any cohort randomness,
and writes a separate authenticated completion only after the canonical
cohort is durable. A pending claim without its matching completion is a
terminal interrupted freeze: neither `freeze` nor `prepare` may be retried,
and V20 must be superseded. Do not inspect or publish the claim, completion,
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
set -euo pipefail
umask 077
V20_PYTHON='/Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python'
V20_RUNTIME_CACHE="$HOME/.codex/epiagentbench-v20-runtime-cache"
V20_RUNTIME_STAGING="$HOME/.codex/epiagentbench-v20-runtime-receipt-staging"
V20_EXPECTED_COMMIT="${V20_RECEIPT_COMMIT:?set the exact published runtime-receipt commit}"
V20_PREPARE_CHECKOUT="${V20_PREPARE_CHECKOUT:?set the absolute canonical path to the fresh receipt-bound checkout}"
V20_PUBLIC_RUNTIME='results/development-matched-50x6-v20.runtime.json'
V20_KEY="$HOME/.codex/epiagentbench-v20-secrets/panel-auth.key"
V20_FREEZE_CLAIM="$HOME/.codex/epiagentbench-v20-secrets/.development-matched-50x6-v20.cohort-freeze-claim.v1.json"
V20_COHORT="$HOME/.codex/epiagentbench-v20-cohort"
V20_PRIVATE_STATE="$HOME/.codex/epiagentbench-v20-state/development-matched-50x6-v20.private.json"
V20_PUBLIC_MANIFEST='results/development-matched-50x6-v20.manifest.json'
V20_PREPARE_OUTPUT="$V20_RUNTIME_STAGING/prepare-public.json"
[[ "$V20_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
test -x "$V20_PYTHON"
cd "$V20_PREPARE_CHECKOUT"
test "$(git rev-parse HEAD)" = "$V20_EXPECTED_COMMIT"
test -z "$(git status --porcelain --untracked-files=all)"
test ! -e "$V20_PRIVATE_STATE" && test ! -L "$V20_PRIVATE_STATE"
test ! -e "$V20_PUBLIC_MANIFEST" && test ! -L "$V20_PUBLIC_MANIFEST"
for candidate_path in \
  "results/development-matched-50x6-v20.authentication.json" \
  "results/development-matched-50x6-v20.preflight.json" \
  "results/development-matched-50x6-v20.json" \
  "$HOME/.codex/epiagentbench-v20-supervisors"; do
  if [ -e "$candidate_path" ] || [ -L "$candidate_path" ]; then
    echo "A later-phase V20 artifact already exists" >&2
    exit 1
  fi
done
test -f "$V20_FREEZE_CLAIM" && test ! -L "$V20_FREEZE_CLAIM"
test ! -e "$V20_PREPARE_OUTPUT" && test ! -L "$V20_PREPARE_OUTPUT"
"$V20_PYTHON" -I -S -B \
  examples/run_development_matched_panel.py prepare \
  --cohort-manifest "$V20_COHORT/cohort.manifest" \
  --preparation-runtime-receipt "$V20_PUBLIC_RUNTIME" \
  --expected-benchmark-base-commit "$V20_EXPECTED_COMMIT" \
  --runtime-cache-dir "$V20_RUNTIME_CACHE" \
  --authentication-key "$V20_KEY" \
  --freeze-claim "$V20_FREEZE_CLAIM" \
  --claude-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v20-credentials/claude" \
  --codex-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v20-credentials/codex" \
  --private-state "$V20_PRIVATE_STATE" \
  --public-manifest "$V20_PUBLIC_MANIFEST" \
  --timeout 1800 \
  --claude-max-budget-usd 5 \
  > "$V20_PREPARE_OUTPUT"
```

Preparation still starts zero authentication helpers, provider processes, and
model calls. Preserve the authenticated private state, full cache contract,
freeze claim, and completion untracked and owner-only. The raw
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
set -euo pipefail
umask 077
V20_PYTHON='/Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python'
V20_RUNTIME_CACHE="$HOME/.codex/epiagentbench-v20-runtime-cache"
V20_EXPECTED_COMMIT="${V20_RECEIPT_COMMIT:?set the exact published runtime-receipt commit}"
V20_PREPARE_CHECKOUT="${V20_PREPARE_CHECKOUT:?set the absolute canonical path to the fresh receipt-bound checkout}"
V20_GITBUTLER_WORKSPACE="${V20_GITBUTLER_WORKSPACE:?set the primary GitButler workspace}"
V20_PUBLIC_RUNTIME='results/development-matched-50x6-v20.runtime.json'
V20_PUBLIC_MANIFEST='results/development-matched-50x6-v20.manifest.json'
[[ "$V20_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
test -x "$V20_PYTHON"
cd "$V20_PREPARE_CHECKOUT"
test "$(git rev-parse HEAD)" = "$V20_EXPECTED_COMMIT"
test -f "$V20_PUBLIC_MANIFEST" && test ! -L "$V20_PUBLIC_MANIFEST"
cd "$V20_GITBUTLER_WORKSPACE"
test "$(git ls-files --error-unmatch "$V20_PUBLIC_RUNTIME")" = \
  "$V20_PUBLIC_RUNTIME"
test ! -e "$V20_PUBLIC_MANIFEST" && test ! -L "$V20_PUBLIC_MANIFEST"
for candidate_path in \
  "results/development-matched-50x6-v20.authentication.json" \
  "results/development-matched-50x6-v20.preflight.json" \
  "results/development-matched-50x6-v20.json"; do
  test ! -e "$candidate_path" && test ! -L "$candidate_path"
done
"$V20_PYTHON" -I -S -B \
  examples/run_development_matched_panel.py \
  publish-provider-free-json \
  --source "$V20_PREPARE_CHECKOUT/$V20_PUBLIC_MANIFEST" \
  --destination "$V20_PUBLIC_MANIFEST"
cmp -s \
  "$V20_PREPARE_CHECKOUT/$V20_PUBLIC_MANIFEST" \
  "$V20_PUBLIC_MANIFEST"
```

Commit only the manifest with its exact `but diff` file ID and push only the
named branch:

```text
but commit codex/v20-runtime-preflight \
  -m "Publish V20 frozen panel manifest" \
  --changes <exact-public-manifest-file-id>
but push codex/v20-runtime-preflight
```

Verify the remote tip and record it as the pinned V20 manifest commit.

> [!IMPORTANT]
> Stop here for the current milestone. At this point authentication remains
> untouched, model calls remain zero, provider processes remain zero, no
> supervisor exists, and no spend has been authorized.

## 10. Later only: exact spend authorization and authentication

Do not execute this section until the operator separately provides this exact
sentence after inspecting the pinned public manifest:

> I acknowledge the replacement six-call v20 preflight and 300-assignment
> production run, including unbounded Codex/Cursor provider spend and up to
> $590 total Claude spend across the failed v2 preflight, failed v5 preflight,
> failed v6 authentication bootstrap, failed v7 preflight, failed v8
> production run, v9 preflight and failed production run, the abandoned
> zero-model-call v10 precommitment, the failed zero-model-call v11
> authentication bootstrap, the abandoned zero-model-call v12 precommitment,
> the abandoned zero-model-call v13 precommitment, the failed v14 preflight,
> the failed zero-model-call v15 pre-claim preparation, the failed v16
> preflight, the failed zero-model-call v17 pre-start
> runtime-cache-environment refusal, the failed v18 preflight, the failed
> zero-model-call v19 authentication setup, and the v20 preflight and
> production run.

The later authorization command must use the same frozen paths and exact text.
It creates no provider process. The foreground `authenticate` ceremony may
start only after authorization; its sanitized public receipt must be committed
through GitButler before a supervisor is generated.

```bash
set -euo pipefail
V20_PYTHON='/Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python'
V20_RUNTIME_CACHE="$HOME/.codex/epiagentbench-v20-runtime-cache"
V20_EXPECTED_COMMIT="${V20_MANIFEST_COMMIT:?set the exact published V20 manifest commit}"
V20_REPOSITORY_ROOT="${V20_AUTHORIZATION_CHECKOUT:?set the clean manifest-bound checkout}"
V20_KEY="$HOME/.codex/epiagentbench-v20-secrets/panel-auth.key"
V20_PRIVATE_STATE="$HOME/.codex/epiagentbench-v20-state/development-matched-50x6-v20.private.json"
[[ "$V20_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
test -x "$V20_PYTHON"
test -d "$V20_REPOSITORY_ROOT" && test ! -L "$V20_REPOSITORY_ROOT"
test "$(cd "$V20_REPOSITORY_ROOT" && pwd -P)" = "$V20_REPOSITORY_ROOT"
cd "$V20_REPOSITORY_ROOT"
test "$(git rev-parse HEAD)" = "$V20_EXPECTED_COMMIT"
test -z "$(git status --porcelain --untracked-files=all)"
"$V20_PYTHON" -I -S -B \
  examples/run_development_matched_panel.py authorize \
  --runtime-cache-dir "$V20_RUNTIME_CACHE" \
  --authentication-key "$V20_KEY" \
  --claude-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v20-credentials/claude" \
  --codex-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v20-credentials/codex" \
  --private-state "$V20_PRIVATE_STATE" \
  --public-manifest \
    results/development-matched-50x6-v20.manifest.json \
  --acknowledgement-text \
    'I acknowledge the replacement six-call v20 preflight and 300-assignment production run, including unbounded Codex/Cursor provider spend and up to $590 total Claude spend across the failed v2 preflight, failed v5 preflight, failed v6 authentication bootstrap, failed v7 preflight, failed v8 production run, v9 preflight and failed production run, the abandoned zero-model-call v10 precommitment, the failed zero-model-call v11 authentication bootstrap, the abandoned zero-model-call v12 precommitment, the abandoned zero-model-call v13 precommitment, the failed v14 preflight, the failed zero-model-call v15 pre-claim preparation, the failed v16 preflight, the failed zero-model-call v17 pre-start runtime-cache-environment refusal, the failed v18 preflight, the failed zero-model-call v19 authentication setup, and the v20 preflight and production run.'
```

Only after that exact authorization exists may the foreground authentication
ceremony run:

```bash
set -euo pipefail
V20_PYTHON='/Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python'
V20_RUNTIME_CACHE="$HOME/.codex/epiagentbench-v20-runtime-cache"
V20_EXPECTED_COMMIT="${V20_MANIFEST_COMMIT:?set the exact published V20 manifest commit}"
V20_REPOSITORY_ROOT="${V20_AUTHORIZATION_CHECKOUT:?set the clean manifest-bound checkout}"
V20_KEY="$HOME/.codex/epiagentbench-v20-secrets/panel-auth.key"
V20_PRIVATE_STATE="$HOME/.codex/epiagentbench-v20-state/development-matched-50x6-v20.private.json"
[[ "$V20_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
test -x "$V20_PYTHON"
test -d "$V20_REPOSITORY_ROOT" && test ! -L "$V20_REPOSITORY_ROOT"
test "$(cd "$V20_REPOSITORY_ROOT" && pwd -P)" = "$V20_REPOSITORY_ROOT"
cd "$V20_REPOSITORY_ROOT"
test "$(git rev-parse HEAD)" = "$V20_EXPECTED_COMMIT"
test -z "$(git status --porcelain --untracked-files=all)"
"$V20_PYTHON" -I -S -B \
  examples/run_development_matched_panel.py authenticate \
  --runtime-cache-dir "$V20_RUNTIME_CACHE" \
  --authentication-key "$V20_KEY" \
  --claude-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v20-credentials/claude" \
  --codex-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v20-credentials/codex" \
  --private-state "$V20_PRIVATE_STATE" \
  --public-manifest \
    results/development-matched-50x6-v20.manifest.json \
  --acknowledge-interactive-authentication
```

Publish only the sanitized authentication receipt through GitButler. Then,
before supervisor generation, create a fresh supervisor root and fresh Cursor
Keychain service in an operator-visible terminal:

```bash
set -euo pipefail
umask 077
V20_PYTHON='/Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python'
V20_RUNTIME_CACHE="$HOME/.codex/epiagentbench-v20-runtime-cache"
V20_EXPECTED_COMMIT="${V20_AUTHENTICATION_RECEIPT_COMMIT:?set the exact published authentication-receipt commit}"
V20_REPOSITORY_ROOT="${V20_AUTHENTICATION_RECEIPT_CHECKOUT:?set the clean authentication-receipt-bound checkout}"
V20_KEY="$HOME/.codex/epiagentbench-v20-secrets/panel-auth.key"
V20_PRIVATE_STATE="$HOME/.codex/epiagentbench-v20-state/development-matched-50x6-v20.private.json"
[[ "$V20_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
test -x "$V20_PYTHON"
cd "$V20_REPOSITORY_ROOT"
test "$(git rev-parse HEAD)" = "$V20_EXPECTED_COMMIT"
test -z "$(git status --porcelain --untracked-files=all)"
"$V20_PYTHON" -I -S -B \
  examples/run_development_matched_panel.py bind-receipt \
  --runtime-cache-dir "$V20_RUNTIME_CACHE" \
  --operation authentication \
  --authentication-key "$V20_KEY" \
  --claude-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v20-credentials/claude" \
  --codex-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v20-credentials/codex" \
  --private-state "$V20_PRIVATE_STATE" \
  --public-manifest \
    results/development-matched-50x6-v20.manifest.json
test ! -e "$HOME/.codex/epiagentbench-v20-supervisors"
test ! -L "$HOME/.codex/epiagentbench-v20-supervisors"
if security find-generic-password \
  -a "$USER" \
  -s epiagentbench-cursor-v20 >/dev/null 2>&1; then
  echo "Refusing to reuse the V20 Cursor Keychain service" >&2
  exit 1
fi
mkdir "$HOME/.codex/epiagentbench-v20-supervisors"
chmod 700 "$HOME/.codex/epiagentbench-v20-supervisors"
security add-generic-password \
  -a "$USER" \
  -s epiagentbench-cursor-v20 \
  -w
```

`bind-receipt` launches no authentication helper or provider. It verifies that
the sanitized authentication receipt is tracked with the exact bytes at the
clean checkout's `HEAD`, then seals that publishing commit into authenticated
private state exactly once. A clean descendant checkout may later move without
rebinding; unrelated history, dirty bytes, or a second commit binding fail
closed. For each supervisor action, finalization exact-compares a fresh authenticated read
against the action's original authenticated snapshot before it mutates durable
state.

### V20 model-invocation accounting boundary

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
by V20. The V18 receipt retains its legacy `invocation_state`,
`failed_provider_invocation_state`, failure stage, incident, and one-call
conservative accounting exactly as published.

## 11. Later only: complete six-call preflight supervisor commands

After the exact acknowledgement, successful foreground authentication, and
publication of its sanitized receipt, materialize a clean checkout at that
published receipt commit. Then generate, install, inspect, and start the
preflight exactly once:

```bash
set -euo pipefail
V20_PYTHON='/Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python'
V20_RUNTIME_CACHE="$HOME/.codex/epiagentbench-v20-runtime-cache"
V20_EXPECTED_COMMIT="${V20_AUTHENTICATION_RECEIPT_COMMIT:?set the exact published authentication-receipt commit}"
V20_REPOSITORY_ROOT="${V20_EXECUTION_CHECKOUT:?set the clean receipt-bound execution checkout}"
V20_KEY="$HOME/.codex/epiagentbench-v20-secrets/panel-auth.key"
V20_PRIVATE_STATE="$HOME/.codex/epiagentbench-v20-state/development-matched-50x6-v20.private.json"
V20_RUNTIME="$HOME/.codex/epiagentbench-v20-supervisors/preflight"
[[ "$V20_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
test -x "$V20_PYTHON"
cd "$V20_REPOSITORY_ROOT"
test "$(git rev-parse HEAD)" = "$V20_EXPECTED_COMMIT"
test -z "$(git status --porcelain --untracked-files=all)"
"$V20_PYTHON" -I -S -B \
  examples/run_persistent_panel_supervisor.py generate \
  --operation preflight \
  --runtime-dir "$V20_RUNTIME" \
  --repository-root "$V20_REPOSITORY_ROOT" \
  --python-executable "$V20_PYTHON" \
  --runtime-cache-dir "$V20_RUNTIME_CACHE" \
  --authentication-key "$V20_KEY" \
  --claude-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v20-credentials/claude" \
  --codex-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v20-credentials/codex" \
  --private-state "$V20_PRIVATE_STATE" \
  --public-manifest \
    "$V20_REPOSITORY_ROOT/results/development-matched-50x6-v20.manifest.json" \
  --public-preflight \
    "$V20_REPOSITORY_ROOT/results/development-matched-50x6-v20.preflight.json" \
  --cursor-keychain-service epiagentbench-cursor-v20 \
  --cursor-keychain-account "$USER"
"$V20_PYTHON" -I -S -B \
  examples/run_persistent_panel_supervisor.py install \
  --runtime-dir "$V20_RUNTIME" \
  --authentication-key "$V20_KEY"
"$V20_PYTHON" -I -S -B \
  examples/run_persistent_panel_supervisor.py status \
  --runtime-dir "$V20_RUNTIME" \
  --authentication-key "$V20_KEY"
# Start only if authenticated status is exactly inactive and not-started.
"$V20_PYTHON" -I -S -B \
  examples/run_persistent_panel_supervisor.py start \
  --runtime-dir "$V20_RUNTIME" \
  --authentication-key "$V20_KEY"
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

Only after all six profiles pass, the sanitized preflight receipt is
validated and committed through GitButler, and a fresh clean checkout is
materialized at that published commit may production be generated and started
exactly once:

```bash
set -euo pipefail
V20_PYTHON='/Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python'
V20_RUNTIME_CACHE="$HOME/.codex/epiagentbench-v20-runtime-cache"
V20_EXPECTED_COMMIT="${V20_PREFLIGHT_RECEIPT_COMMIT:?set the exact published preflight-receipt commit}"
V20_REPOSITORY_ROOT="${V20_PRODUCTION_CHECKOUT:?set the clean preflight-receipt-bound checkout}"
V20_KEY="$HOME/.codex/epiagentbench-v20-secrets/panel-auth.key"
V20_PRIVATE_STATE="$HOME/.codex/epiagentbench-v20-state/development-matched-50x6-v20.private.json"
V20_RUNTIME="$HOME/.codex/epiagentbench-v20-supervisors/production"
[[ "$V20_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
test -x "$V20_PYTHON"
cd "$V20_REPOSITORY_ROOT"
test "$(git rev-parse HEAD)" = "$V20_EXPECTED_COMMIT"
test -z "$(git status --porcelain --untracked-files=all)"
"$V20_PYTHON" -I -S -B \
  examples/run_development_matched_panel.py bind-receipt \
  --runtime-cache-dir "$V20_RUNTIME_CACHE" \
  --operation preflight \
  --authentication-key "$V20_KEY" \
  --claude-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v20-credentials/claude" \
  --codex-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v20-credentials/codex" \
  --private-state "$V20_PRIVATE_STATE" \
  --public-manifest \
    "$V20_REPOSITORY_ROOT/results/development-matched-50x6-v20.manifest.json"
"$V20_PYTHON" -I -S -B \
  examples/run_persistent_panel_supervisor.py generate \
  --operation production \
  --runtime-dir "$V20_RUNTIME" \
  --repository-root "$V20_REPOSITORY_ROOT" \
  --python-executable "$V20_PYTHON" \
  --runtime-cache-dir "$V20_RUNTIME_CACHE" \
  --authentication-key "$V20_KEY" \
  --claude-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v20-credentials/claude" \
  --codex-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v20-credentials/codex" \
  --private-state "$V20_PRIVATE_STATE" \
  --public-manifest \
    "$V20_REPOSITORY_ROOT/results/development-matched-50x6-v20.manifest.json" \
  --public-results \
    "$V20_REPOSITORY_ROOT/results/development-matched-50x6-v20.json" \
  --cursor-keychain-service epiagentbench-cursor-v20 \
  --cursor-keychain-account "$USER"
"$V20_PYTHON" -I -S -B \
  examples/run_persistent_panel_supervisor.py install \
  --runtime-dir "$V20_RUNTIME" \
  --authentication-key "$V20_KEY"
"$V20_PYTHON" -I -S -B \
  examples/run_persistent_panel_supervisor.py status \
  --runtime-dir "$V20_RUNTIME" \
  --authentication-key "$V20_KEY"
# Start only if authenticated status is exactly inactive and not-started.
"$V20_PYTHON" -I -S -B \
  examples/run_persistent_panel_supervisor.py start \
  --runtime-dir "$V20_RUNTIME" \
  --authentication-key "$V20_KEY"
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
set -euo pipefail
V20_PYTHON='/Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python'
V20_RUNTIME_CACHE="$HOME/.codex/epiagentbench-v20-runtime-cache"
V20_EXPECTED_COMMIT="${V20_AUTHENTICATION_RECEIPT_COMMIT:?set the exact published authentication-receipt commit}"
V20_REPOSITORY_ROOT="${V20_PREFLIGHT_TERMINAL_CHECKOUT:?set the clean terminal preflight checkout}"
V20_KEY="$HOME/.codex/epiagentbench-v20-secrets/panel-auth.key"
V20_PRIVATE_STATE="$HOME/.codex/epiagentbench-v20-state/development-matched-50x6-v20.private.json"
[[ "$V20_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
test -x "$V20_PYTHON"
cd "$V20_REPOSITORY_ROOT"
test "$(git rev-parse HEAD)" = "$V20_EXPECTED_COMMIT"
test -z "$(git status --porcelain --untracked-files=all)"
"$V20_PYTHON" -I -S -B \
  examples/run_development_matched_panel.py reconcile-terminal-receipt \
  --runtime-cache-dir "$V20_RUNTIME_CACHE" \
  --operation preflight \
  --authentication-key "$V20_KEY" \
  --private-state "$V20_PRIVATE_STATE" \
  --public-manifest \
    "$V20_REPOSITORY_ROOT/results/development-matched-50x6-v20.manifest.json" \
  --public-output \
    "$V20_REPOSITORY_ROOT/results/development-matched-50x6-v20.preflight.json"
```

For a durable production incident, use the separate preflight-receipt-bound
checkout and the canonical production output:

```bash
set -euo pipefail
V20_PYTHON='/Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python'
V20_RUNTIME_CACHE="$HOME/.codex/epiagentbench-v20-runtime-cache"
V20_EXPECTED_COMMIT="${V20_PREFLIGHT_RECEIPT_COMMIT:?set the exact published preflight-receipt commit}"
V20_REPOSITORY_ROOT="${V20_PRODUCTION_TERMINAL_CHECKOUT:?set the clean terminal production checkout}"
V20_KEY="$HOME/.codex/epiagentbench-v20-secrets/panel-auth.key"
V20_PRIVATE_STATE="$HOME/.codex/epiagentbench-v20-state/development-matched-50x6-v20.private.json"
[[ "$V20_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
test -x "$V20_PYTHON"
cd "$V20_REPOSITORY_ROOT"
test "$(git rev-parse HEAD)" = "$V20_EXPECTED_COMMIT"
test -z "$(git status --porcelain --untracked-files=all)"
"$V20_PYTHON" -I -S -B \
  examples/run_development_matched_panel.py reconcile-terminal-receipt \
  --runtime-cache-dir "$V20_RUNTIME_CACHE" \
  --operation production \
  --authentication-key "$V20_KEY" \
  --private-state "$V20_PRIVATE_STATE" \
  --public-manifest \
    "$V20_REPOSITORY_ROOT/results/development-matched-50x6-v20.manifest.json" \
  --public-output \
    "$V20_REPOSITORY_ROOT/results/development-matched-50x6-v20.json"
```

Reconciliation launches zero authentication helpers, providers, or models. It
publishes only the exact authenticated trace-free candidate, refuses
conflicting or noncanonical bytes, and never changes the supervisor's terminal
classification.

## Terminal rules

- Never reuse any V15, V16, V17, V18, or V19 cohort, key, credential, state, cache,
  supervisor, runtime, Keychain service, or claim.
- Never create a V20 private artifact before the runtime receipt is committed,
  pushed through GitButler, pinned, and successfully re-attested.
- Never substitute a PATH-selected Python for the exact V5 interpreter, omit
  `-I -S -B`, or inject `PYTHONPATH`/startup hooks.
- Never place a receipt, verification summary, or any other staging file
  inside the runtime-cache root; it may contain only `matplotlib`, `numba`, and
  `xdg`.
- Never change, recreate, relink, chmod, or relocate the bound cache tree.
- Never retry a freeze or prepare after the canonical pending freeze claim
  exists without its authenticated completion.
- Never retry a V20 freeze, preparation, preflight, production assignment, or
  durable supervisor start. Foreground authentication may retry only from the
  explicit `retryable_failed` ceremony state after process-group quiescence
  and an unchanged empty target have been proven; every terminal or running
  ceremony state rejects reuse.
- Never infer spend authorization from this runbook, receipt, or manifest.
- Never publish the raw Python entrypoint/bootstrap binding, cache paths,
  environment, inventory, or device/inode/UID metadata; only their opaque
  hashes belong in public receipts and manifests.
- Never expose provider output, credentials, prompts, observations, hidden
  episode identifiers/families, schedules, seeds, traces, or scores before the
  final release gate.
