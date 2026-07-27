# EpiAgentBench V16 execution runbook

> [!CAUTION]
> This runbook does not authorize authentication, a provider process, spend, a
> supervisor start, or a model call. The current preparation milestone ends
> after the public V16 manifest is validated, committed, pushed through
> GitButler, and pinned. Do not run the authorization or execution sections
> until the operator later supplies the exact manifest-bound acknowledgement.

V16 replaces the terminal, zero-model-call V15 preparation. V15 froze a
cohort, but its selected bare `python3` could not import Starsim. V15 and every
V15 private namespace are non-resumable and forbidden for reuse.

V16 uses a two-commit, provider-free preparation protocol:

1. publish and pin the V16 control-plane code;
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
by the byte-identical runtime-receipt commit. No V16 key, freeze claim, cohort,
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

## Frozen V16 identifiers

| Surface | V16 value |
|---|---|
| Panel and cohort | `development-matched-50x6-v16` |
| Top-level schema | `development_matched_panel_v16` |
| Runtime receipt | `results/development-matched-50x6-v16.runtime.json` |
| Required Python launch path | `/Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python` |
| Required Python flags | `-I -S -B` |
| Required Starsim | `3.5.1` |
| Persistent-supervisor contract | `epiagentbench.persistent_supervisor_contract.v5` |
| Assignments | 50 episodes × 6 profiles = 300 |
| Per-call timeout | 1,800 seconds |
| Claude per-call ceiling | $5 |
| V16 current-run Claude ceiling | $510 (102 Claude calls × $5) |
| Prior conservative Claude ceiling | $70 |
| Cumulative acknowledgement ceiling | $580 ($510 + $70) |
| Codex/Cursor ceiling | unbounded |
| Cursor Keychain service | `epiagentbench-cursor-v16` |

V15 adds zero dollars to the prior ceiling because it launched no provider or
authentication helper and made no model call.

## Fresh V16 paths

```text
$HOME/.codex/epiagentbench-50x6-v16-runtime-worktree
$HOME/.codex/epiagentbench-50x6-v16-prepare-worktree
$HOME/.codex/epiagentbench-v16-runtime-cache
$HOME/.codex/epiagentbench-v16-runtime-receipt-staging
$HOME/.codex/epiagentbench-v16-cohort
$HOME/.codex/epiagentbench-v16-secrets/panel-auth.key
$HOME/.codex/epiagentbench-v16-secrets/.development-matched-50x6-v16.cohort-freeze-claim.v1.json
$HOME/.codex/epiagentbench-v16-secrets/.development-matched-50x6-v16.cohort-freeze-completion.v1.json
$HOME/.codex/epiagentbench-v16-state/development-matched-50x6-v16.private.json
$HOME/.codex/epiagentbench-v16-credentials/claude
$HOME/.codex/epiagentbench-v16-credentials/codex
$HOME/.codex/epiagentbench-v16-supervisors/preflight
$HOME/.codex/epiagentbench-v16-supervisors/production
```

The five public destinations are:

```text
results/development-matched-50x6-v16.runtime.json
results/development-matched-50x6-v16.manifest.json
results/development-matched-50x6-v16.authentication.json
results/development-matched-50x6-v16.preflight.json
results/development-matched-50x6-v16.json
```

Every shell block below is intentionally self-contained: it declares every
path or prior published commit it consumes. Every Python CLI/supervisor
invocation uses the approved V5 virtual-environment interpreter with
`-I -S -B`, and every block that can load the scientific runtime restates the
exact cache environment. Never replace `V16_PYTHON` with `python`, `python3`,
a PATH lookup, or another virtual environment. Never use `PYTHONPATH`; the
isolated scripts build and re-attest their only permitted import paths without
executing `site`, `.pth`, `sitecustomize`, or `usercustomize`.

## 1. Publish and pin the V16 control plane

Use the GitButler-managed primary workspace to commit and push the V16
control-plane changes on `codex/v16-runtime-preflight`. Never use `git push`
and never publish a private artifact. Record the exact 40-hex remote commit as
`V16_CONTROL_COMMIT`.

This first commit must not contain any V16 runtime receipt, manifest,
authentication receipt, preflight receipt, final result, key, cohort, private
state, credential directory, or supervisor runtime.

## 2. Validate the clean control-plane checkout

After the GitButler push, use an operator-approved GitButler-compatible
workflow to materialize a fresh clean checkout at the exact control-plane
commit. Set `V16_RUNTIME_CHECKOUT` to its absolute canonical path, then run
this validation block from the repository's primary checkout. The block is
read-only; it does not create or mutate a Git checkout.

```bash
set -euo pipefail
V16_PYTHON='/Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python'
V16_RUNTIME_CACHE="$HOME/.codex/epiagentbench-v16-runtime-cache"
V16_EXPECTED_COMMIT="${V16_CONTROL_COMMIT:?set the exact published control-plane commit}"
V16_REMOTE_REF='refs/heads/codex/v16-runtime-preflight'
V16_RUNTIME_CHECKOUT="${V16_RUNTIME_CHECKOUT:?set the absolute canonical path to the fresh control-plane checkout}"
[[ "$V16_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
test -x "$V16_PYTHON"
test "$(git ls-remote origin "$V16_REMOTE_REF" | cut -f1)" = \
  "$V16_EXPECTED_COMMIT"
test -d "$V16_RUNTIME_CHECKOUT" && test ! -L "$V16_RUNTIME_CHECKOUT"
test "$(cd "$V16_RUNTIME_CHECKOUT" && pwd -P)" = "$V16_RUNTIME_CHECKOUT"
cd "$V16_RUNTIME_CHECKOUT"
test "$(git rev-parse HEAD)" = "$V16_EXPECTED_COMMIT"
test -z "$(git status --porcelain --untracked-files=all)"
```

## 3. Prove freshness and create separate cache and staging roots

All five public outputs and all private V16 namespaces must be absent before
the cache is created. The cache is runtime state, not a cohort or credential
namespace. Its v3 contract permits exactly three children at the root:
`matplotlib`, `numba`, and `xdg`. Receipt bytes, command summaries, and all
other operator output therefore go into a distinct owner-only staging
directory that never overlaps the cache.

```bash
set -euo pipefail
umask 077
V16_PYTHON='/Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python'
V16_RUNTIME_CACHE="$HOME/.codex/epiagentbench-v16-runtime-cache"
V16_RUNTIME_STAGING="$HOME/.codex/epiagentbench-v16-runtime-receipt-staging"
V16_EXPECTED_COMMIT="${V16_CONTROL_COMMIT:?set the exact published control-plane commit}"
V16_RUNTIME_CHECKOUT="${V16_RUNTIME_CHECKOUT:?set the absolute canonical path to the fresh control-plane checkout}"
[[ "$V16_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
test -x "$V16_PYTHON"
cd "$V16_RUNTIME_CHECKOUT"
test "$(git rev-parse HEAD)" = "$V16_EXPECTED_COMMIT"
test -z "$(git status --porcelain --untracked-files=all)"
for candidate_path in \
  "$HOME/.codex/epiagentbench-v16-runtime-cache" \
  "$HOME/.codex/epiagentbench-v16-runtime-receipt-staging" \
  "$HOME/.codex/epiagentbench-v16-secrets" \
  "$HOME/.codex/epiagentbench-v16-state" \
  "$HOME/.codex/epiagentbench-v16-credentials" \
  "$HOME/.codex/epiagentbench-v16-supervisors" \
  "$HOME/.codex/epiagentbench-v16-cohort" \
  "results/development-matched-50x6-v16.runtime.json" \
  "results/development-matched-50x6-v16.manifest.json" \
  "results/development-matched-50x6-v16.authentication.json" \
  "results/development-matched-50x6-v16.preflight.json" \
  "results/development-matched-50x6-v16.json"; do
  if [ -e "$candidate_path" ] || [ -L "$candidate_path" ]; then
    echo "Refusing occupied V16 path: $candidate_path" >&2
    exit 1
  fi
done
mkdir "$V16_RUNTIME_CACHE"
mkdir "$V16_RUNTIME_STAGING"
mkdir \
  "$V16_RUNTIME_CACHE/matplotlib" \
  "$V16_RUNTIME_CACHE/numba" \
  "$V16_RUNTIME_CACHE/xdg"
chmod 700 \
  "$V16_RUNTIME_CACHE" \
  "$V16_RUNTIME_STAGING" \
  "$V16_RUNTIME_CACHE/matplotlib" \
  "$V16_RUNTIME_CACHE/numba" \
  "$V16_RUNTIME_CACHE/xdg"
export MPLBACKEND='Agg'
export MPLCONFIGDIR="$V16_RUNTIME_CACHE/matplotlib"
export NUMBA_CACHE_DIR="$V16_RUNTIME_CACHE/numba"
export PYTHONDONTWRITEBYTECODE='1'
export STARSIM_INSTALL_FONTS='0'
export XDG_CACHE_HOME="$V16_RUNTIME_CACHE/xdg"
```

## 4. Produce the provider-free runtime receipt twice

Both commands run at the exact control-plane commit and write outside the
repository. A byte difference is terminal for this preparation attempt.

```bash
set -euo pipefail
umask 077
V16_PYTHON='/Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python'
V16_RUNTIME_CACHE="$HOME/.codex/epiagentbench-v16-runtime-cache"
V16_RUNTIME_STAGING="$HOME/.codex/epiagentbench-v16-runtime-receipt-staging"
V16_EXPECTED_COMMIT="${V16_CONTROL_COMMIT:?set the exact published control-plane commit}"
V16_RUNTIME_CHECKOUT="${V16_RUNTIME_CHECKOUT:?set the absolute canonical path to the fresh control-plane checkout}"
V16_RUNTIME_ONE="$V16_RUNTIME_STAGING/preflight-1.json"
V16_RUNTIME_TWO="$V16_RUNTIME_STAGING/preflight-2.json"
[[ "$V16_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
cd "$V16_RUNTIME_CHECKOUT"
test "$(git rev-parse HEAD)" = "$V16_EXPECTED_COMMIT"
test -z "$(git status --porcelain --untracked-files=all)"
test -x "$V16_PYTHON"
export MPLBACKEND='Agg'
export MPLCONFIGDIR="$V16_RUNTIME_CACHE/matplotlib"
export NUMBA_CACHE_DIR="$V16_RUNTIME_CACHE/numba"
export PYTHONDONTWRITEBYTECODE='1'
export STARSIM_INSTALL_FONTS='0'
export XDG_CACHE_HOME="$V16_RUNTIME_CACHE/xdg"
test -d "$V16_RUNTIME_STAGING" && test ! -L "$V16_RUNTIME_STAGING"
test "$(stat -f '%Lp' "$V16_RUNTIME_STAGING")" = 700
test ! -e "$V16_RUNTIME_ONE" && test ! -L "$V16_RUNTIME_ONE"
test ! -e "$V16_RUNTIME_TWO" && test ! -L "$V16_RUNTIME_TWO"
"$V16_PYTHON" -I -S -B \
  examples/run_development_matched_panel.py \
  preflight-preparation-runtime \
  --expected-benchmark-base-commit "$V16_EXPECTED_COMMIT" \
  --runtime-cache-dir "$V16_RUNTIME_CACHE" > "$V16_RUNTIME_ONE"
"$V16_PYTHON" -I -S -B \
  examples/run_development_matched_panel.py \
  preflight-preparation-runtime \
  --expected-benchmark-base-commit "$V16_EXPECTED_COMMIT" \
  --runtime-cache-dir "$V16_RUNTIME_CACHE" > "$V16_RUNTIME_TWO"
test -f "$V16_RUNTIME_ONE" && test ! -L "$V16_RUNTIME_ONE"
test -f "$V16_RUNTIME_TWO" && test ! -L "$V16_RUNTIME_TWO"
test "$(stat -f '%Lp' "$V16_RUNTIME_ONE")" = 600
test "$(stat -f '%Lp' "$V16_RUNTIME_TWO")" = 600
cmp -s "$V16_RUNTIME_ONE" "$V16_RUNTIME_TWO"
test "$(git rev-parse HEAD)" = "$V16_EXPECTED_COMMIT"
test -z "$(git status --porcelain --untracked-files=all)"
for candidate_path in \
  "$HOME/.codex/epiagentbench-v16-secrets" \
  "$HOME/.codex/epiagentbench-v16-state" \
  "$HOME/.codex/epiagentbench-v16-credentials" \
  "$HOME/.codex/epiagentbench-v16-supervisors" \
  "$HOME/.codex/epiagentbench-v16-cohort" \
  "results/development-matched-50x6-v16.runtime.json" \
  "results/development-matched-50x6-v16.manifest.json" \
  "results/development-matched-50x6-v16.authentication.json" \
  "results/development-matched-50x6-v16.preflight.json" \
  "results/development-matched-50x6-v16.json"; do
  if [ -e "$candidate_path" ] || [ -L "$candidate_path" ]; then
    echo "A V16 artifact appeared during provider-free preflight" >&2
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
V16_PYTHON='/Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python'
V16_RUNTIME_CACHE="$HOME/.codex/epiagentbench-v16-runtime-cache"
V16_RUNTIME_STAGING="$HOME/.codex/epiagentbench-v16-runtime-receipt-staging"
V16_EXPECTED_COMMIT="${V16_CONTROL_COMMIT:?set the exact published control-plane commit}"
V16_GITBUTLER_WORKSPACE="${V16_GITBUTLER_WORKSPACE:?set the primary GitButler workspace}"
V16_PUBLIC_RUNTIME='results/development-matched-50x6-v16.runtime.json'
V16_RUNTIME_ONE="$V16_RUNTIME_STAGING/preflight-1.json"
V16_RUNTIME_TWO="$V16_RUNTIME_STAGING/preflight-2.json"
[[ "$V16_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
test -x "$V16_PYTHON"
export MPLBACKEND='Agg'
export MPLCONFIGDIR="$V16_RUNTIME_CACHE/matplotlib"
export NUMBA_CACHE_DIR="$V16_RUNTIME_CACHE/numba"
export PYTHONDONTWRITEBYTECODE='1'
export STARSIM_INSTALL_FONTS='0'
export XDG_CACHE_HOME="$V16_RUNTIME_CACHE/xdg"
cmp -s \
  "$V16_RUNTIME_ONE" \
  "$V16_RUNTIME_TWO"
cd "$V16_GITBUTLER_WORKSPACE"
for candidate_path in \
  "$V16_PUBLIC_RUNTIME" \
  "results/development-matched-50x6-v16.manifest.json" \
  "results/development-matched-50x6-v16.authentication.json" \
  "results/development-matched-50x6-v16.preflight.json" \
  "results/development-matched-50x6-v16.json"; do
  test ! -e "$candidate_path" && test ! -L "$candidate_path"
done
cp "$V16_RUNTIME_ONE" "$V16_PUBLIC_RUNTIME"
cmp -s "$V16_RUNTIME_ONE" "$V16_PUBLIC_RUNTIME"
```

Run `but diff`, copy the exact file change ID for only the runtime receipt,
then commit it to the existing branch and push that named branch:

```text
but commit codex/v16-runtime-preflight \
  -m "Publish V16 scientific runtime receipt" \
  --changes <exact-runtime-receipt-file-id>
but push codex/v16-runtime-preflight
```

No direct `git push` is permitted. Verify the remote branch contains the exact
receipt bytes, and record its exact 40-hex tip as `V16_RECEIPT_COMMIT`. This is
the second provider-free commit.

## 6. Validate the receipt-bound checkout and verify before writing

Use an operator-approved GitButler-compatible workflow to materialize a second
fresh clean checkout rather than mutating or reusing the runtime checkout. Set
`V16_PREPARE_CHECKOUT` to its absolute canonical path. The expected commit for
every remaining preparation command is now the published runtime-receipt
commit, not the earlier control-plane commit. The block below only validates
the supplied checkout before beginning provider-free preparation.

```bash
set -euo pipefail
umask 077
V16_PYTHON='/Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python'
V16_RUNTIME_CACHE="$HOME/.codex/epiagentbench-v16-runtime-cache"
V16_RUNTIME_STAGING="$HOME/.codex/epiagentbench-v16-runtime-receipt-staging"
V16_EXPECTED_COMMIT="${V16_RECEIPT_COMMIT:?set the exact published runtime-receipt commit}"
V16_REMOTE_REF='refs/heads/codex/v16-runtime-preflight'
V16_PREPARE_CHECKOUT="${V16_PREPARE_CHECKOUT:?set the absolute canonical path to the fresh receipt-bound checkout}"
V16_PUBLIC_RUNTIME='results/development-matched-50x6-v16.runtime.json'
V16_VERIFICATION_OUTPUT="$V16_RUNTIME_STAGING/verification.json"
[[ "$V16_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
test -x "$V16_PYTHON"
test "$(git ls-remote origin "$V16_REMOTE_REF" | cut -f1)" = \
  "$V16_EXPECTED_COMMIT"
test -d "$V16_PREPARE_CHECKOUT" && test ! -L "$V16_PREPARE_CHECKOUT"
test "$(cd "$V16_PREPARE_CHECKOUT" && pwd -P)" = \
  "$V16_PREPARE_CHECKOUT"
cd "$V16_PREPARE_CHECKOUT"
test "$(git rev-parse HEAD)" = "$V16_EXPECTED_COMMIT"
test -z "$(git status --porcelain --untracked-files=all)"
test "$(git ls-files --error-unmatch "$V16_PUBLIC_RUNTIME")" = \
  "$V16_PUBLIC_RUNTIME"
test -f "$V16_PUBLIC_RUNTIME" && test ! -L "$V16_PUBLIC_RUNTIME"
for candidate_path in \
  "$HOME/.codex/epiagentbench-v16-secrets" \
  "$HOME/.codex/epiagentbench-v16-state" \
  "$HOME/.codex/epiagentbench-v16-credentials" \
  "$HOME/.codex/epiagentbench-v16-supervisors" \
  "$HOME/.codex/epiagentbench-v16-cohort" \
  "results/development-matched-50x6-v16.manifest.json" \
  "results/development-matched-50x6-v16.authentication.json" \
  "results/development-matched-50x6-v16.preflight.json" \
  "results/development-matched-50x6-v16.json"; do
  if [ -e "$candidate_path" ] || [ -L "$candidate_path" ]; then
    echo "Refusing occupied V16 path: $candidate_path" >&2
    exit 1
  fi
done
export MPLBACKEND='Agg'
export MPLCONFIGDIR="$V16_RUNTIME_CACHE/matplotlib"
export NUMBA_CACHE_DIR="$V16_RUNTIME_CACHE/numba"
export PYTHONDONTWRITEBYTECODE='1'
export STARSIM_INSTALL_FONTS='0'
export XDG_CACHE_HOME="$V16_RUNTIME_CACHE/xdg"
test ! -e "$V16_VERIFICATION_OUTPUT" && test ! -L "$V16_VERIFICATION_OUTPUT"
"$V16_PYTHON" -I -S -B \
  examples/run_development_matched_panel.py \
  verify-preparation-runtime \
  --preparation-runtime-receipt "$V16_PUBLIC_RUNTIME" \
  --expected-benchmark-base-commit "$V16_EXPECTED_COMMIT" \
  --runtime-cache-dir "$V16_RUNTIME_CACHE" \
  > "$V16_VERIFICATION_OUTPUT"
test "$(git rev-parse HEAD)" = "$V16_EXPECTED_COMMIT"
test -z "$(git status --porcelain --untracked-files=all)"
```

A receipt, source, Python/bootstrap, installed-distribution, Starsim-smoke, or
closed cache-inventory mismatch stops before a key or cohort exists. Do not
repair or override a mismatch. The verification summary is staged outside the
cache and remains operator-local.

## 7. Create fresh private prerequisites and freeze exactly once

This is the irreversible V16 preparation boundary. Use the matched V16
`freeze` command; do not call the generic `freeze-private-cohort` command.

```bash
set -euo pipefail
umask 077
set -o noclobber
V16_PYTHON='/Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python'
V16_RUNTIME_CACHE="$HOME/.codex/epiagentbench-v16-runtime-cache"
V16_RUNTIME_STAGING="$HOME/.codex/epiagentbench-v16-runtime-receipt-staging"
V16_EXPECTED_COMMIT="${V16_RECEIPT_COMMIT:?set the exact published runtime-receipt commit}"
V16_PREPARE_CHECKOUT="${V16_PREPARE_CHECKOUT:?set the absolute canonical path to the fresh receipt-bound checkout}"
V16_PUBLIC_RUNTIME='results/development-matched-50x6-v16.runtime.json'
V16_KEY="$HOME/.codex/epiagentbench-v16-secrets/panel-auth.key"
V16_FREEZE_CLAIM="$HOME/.codex/epiagentbench-v16-secrets/.development-matched-50x6-v16.cohort-freeze-claim.v1.json"
V16_COHORT="$HOME/.codex/epiagentbench-v16-cohort"
V16_FREEZE_OUTPUT="$V16_RUNTIME_STAGING/freeze-public.json"
[[ "$V16_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
test -x "$V16_PYTHON"
cd "$V16_PREPARE_CHECKOUT"
test "$(git rev-parse HEAD)" = "$V16_EXPECTED_COMMIT"
test -z "$(git status --porcelain --untracked-files=all)"
export MPLBACKEND='Agg'
export MPLCONFIGDIR="$V16_RUNTIME_CACHE/matplotlib"
export NUMBA_CACHE_DIR="$V16_RUNTIME_CACHE/numba"
export PYTHONDONTWRITEBYTECODE='1'
export STARSIM_INSTALL_FONTS='0'
export XDG_CACHE_HOME="$V16_RUNTIME_CACHE/xdg"
for candidate_path in \
  "$HOME/.codex/epiagentbench-v16-secrets" \
  "$HOME/.codex/epiagentbench-v16-state" \
  "$HOME/.codex/epiagentbench-v16-credentials" \
  "$HOME/.codex/epiagentbench-v16-supervisors" \
  "$V16_COHORT" \
  "results/development-matched-50x6-v16.manifest.json" \
  "results/development-matched-50x6-v16.authentication.json" \
  "results/development-matched-50x6-v16.preflight.json" \
  "results/development-matched-50x6-v16.json"; do
  if [ -e "$candidate_path" ] || [ -L "$candidate_path" ]; then
    echo "Refusing to reuse V16 path: $candidate_path" >&2
    exit 1
  fi
done
mkdir \
  "$HOME/.codex/epiagentbench-v16-secrets" \
  "$HOME/.codex/epiagentbench-v16-state" \
  "$HOME/.codex/epiagentbench-v16-credentials"
mkdir \
  "$HOME/.codex/epiagentbench-v16-credentials/claude" \
  "$HOME/.codex/epiagentbench-v16-credentials/codex"
chmod 700 \
  "$HOME/.codex/epiagentbench-v16-secrets" \
  "$HOME/.codex/epiagentbench-v16-state" \
  "$HOME/.codex/epiagentbench-v16-credentials" \
  "$HOME/.codex/epiagentbench-v16-credentials/claude" \
  "$HOME/.codex/epiagentbench-v16-credentials/codex"
openssl rand 32 > "$V16_KEY"
chmod 600 "$V16_KEY"
test ! -e "$V16_FREEZE_CLAIM" && test ! -L "$V16_FREEZE_CLAIM"
test ! -e "$V16_FREEZE_OUTPUT" && test ! -L "$V16_FREEZE_OUTPUT"
"$V16_PYTHON" -I -S -B \
  examples/run_development_matched_panel.py freeze \
  --preparation-runtime-receipt "$V16_PUBLIC_RUNTIME" \
  --expected-benchmark-base-commit "$V16_EXPECTED_COMMIT" \
  --runtime-cache-dir "$V16_RUNTIME_CACHE" \
  --authentication-key "$V16_KEY" \
  --output-directory "$V16_COHORT" \
  --freeze-claim "$V16_FREEZE_CLAIM" \
  > "$V16_FREEZE_OUTPUT"
```

`freeze` authenticates the canonical claim location against the key namespace,
creates the pending claim without replacement before any cohort randomness,
and writes a separate authenticated completion only after the canonical
cohort is durable. A pending claim without its matching completion is a
terminal interrupted freeze: neither `freeze` nor `prepare` may be retried,
and V16 must be superseded. Do not inspect or publish the claim, completion,
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
V16_PYTHON='/Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python'
V16_RUNTIME_CACHE="$HOME/.codex/epiagentbench-v16-runtime-cache"
V16_RUNTIME_STAGING="$HOME/.codex/epiagentbench-v16-runtime-receipt-staging"
V16_EXPECTED_COMMIT="${V16_RECEIPT_COMMIT:?set the exact published runtime-receipt commit}"
V16_PREPARE_CHECKOUT="${V16_PREPARE_CHECKOUT:?set the absolute canonical path to the fresh receipt-bound checkout}"
V16_PUBLIC_RUNTIME='results/development-matched-50x6-v16.runtime.json'
V16_KEY="$HOME/.codex/epiagentbench-v16-secrets/panel-auth.key"
V16_FREEZE_CLAIM="$HOME/.codex/epiagentbench-v16-secrets/.development-matched-50x6-v16.cohort-freeze-claim.v1.json"
V16_COHORT="$HOME/.codex/epiagentbench-v16-cohort"
V16_PRIVATE_STATE="$HOME/.codex/epiagentbench-v16-state/development-matched-50x6-v16.private.json"
V16_PUBLIC_MANIFEST='results/development-matched-50x6-v16.manifest.json'
V16_PREPARE_OUTPUT="$V16_RUNTIME_STAGING/prepare-public.json"
[[ "$V16_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
test -x "$V16_PYTHON"
cd "$V16_PREPARE_CHECKOUT"
test "$(git rev-parse HEAD)" = "$V16_EXPECTED_COMMIT"
test -z "$(git status --porcelain --untracked-files=all)"
test ! -e "$V16_PRIVATE_STATE" && test ! -L "$V16_PRIVATE_STATE"
test ! -e "$V16_PUBLIC_MANIFEST" && test ! -L "$V16_PUBLIC_MANIFEST"
for candidate_path in \
  "results/development-matched-50x6-v16.authentication.json" \
  "results/development-matched-50x6-v16.preflight.json" \
  "results/development-matched-50x6-v16.json" \
  "$HOME/.codex/epiagentbench-v16-supervisors"; do
  if [ -e "$candidate_path" ] || [ -L "$candidate_path" ]; then
    echo "A later-phase V16 artifact already exists" >&2
    exit 1
  fi
done
export MPLBACKEND='Agg'
export MPLCONFIGDIR="$V16_RUNTIME_CACHE/matplotlib"
export NUMBA_CACHE_DIR="$V16_RUNTIME_CACHE/numba"
export PYTHONDONTWRITEBYTECODE='1'
export STARSIM_INSTALL_FONTS='0'
export XDG_CACHE_HOME="$V16_RUNTIME_CACHE/xdg"
test -f "$V16_FREEZE_CLAIM" && test ! -L "$V16_FREEZE_CLAIM"
test ! -e "$V16_PREPARE_OUTPUT" && test ! -L "$V16_PREPARE_OUTPUT"
"$V16_PYTHON" -I -S -B \
  examples/run_development_matched_panel.py prepare \
  --cohort-manifest "$V16_COHORT/cohort.manifest" \
  --preparation-runtime-receipt "$V16_PUBLIC_RUNTIME" \
  --expected-benchmark-base-commit "$V16_EXPECTED_COMMIT" \
  --runtime-cache-dir "$V16_RUNTIME_CACHE" \
  --authentication-key "$V16_KEY" \
  --freeze-claim "$V16_FREEZE_CLAIM" \
  --claude-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v16-credentials/claude" \
  --codex-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v16-credentials/codex" \
  --private-state "$V16_PRIVATE_STATE" \
  --public-manifest "$V16_PUBLIC_MANIFEST" \
  --timeout 1800 \
  --claude-max-budget-usd 5 \
  > "$V16_PREPARE_OUTPUT"
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
V16_PYTHON='/Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python'
V16_RUNTIME_CACHE="$HOME/.codex/epiagentbench-v16-runtime-cache"
V16_EXPECTED_COMMIT="${V16_RECEIPT_COMMIT:?set the exact published runtime-receipt commit}"
V16_PREPARE_CHECKOUT="${V16_PREPARE_CHECKOUT:?set the absolute canonical path to the fresh receipt-bound checkout}"
V16_GITBUTLER_WORKSPACE="${V16_GITBUTLER_WORKSPACE:?set the primary GitButler workspace}"
V16_PUBLIC_RUNTIME='results/development-matched-50x6-v16.runtime.json'
V16_PUBLIC_MANIFEST='results/development-matched-50x6-v16.manifest.json'
[[ "$V16_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
test -x "$V16_PYTHON"
export MPLBACKEND='Agg'
export MPLCONFIGDIR="$V16_RUNTIME_CACHE/matplotlib"
export NUMBA_CACHE_DIR="$V16_RUNTIME_CACHE/numba"
export PYTHONDONTWRITEBYTECODE='1'
export STARSIM_INSTALL_FONTS='0'
export XDG_CACHE_HOME="$V16_RUNTIME_CACHE/xdg"
cd "$V16_PREPARE_CHECKOUT"
test "$(git rev-parse HEAD)" = "$V16_EXPECTED_COMMIT"
test -f "$V16_PUBLIC_MANIFEST" && test ! -L "$V16_PUBLIC_MANIFEST"
cd "$V16_GITBUTLER_WORKSPACE"
test "$(git ls-files --error-unmatch "$V16_PUBLIC_RUNTIME")" = \
  "$V16_PUBLIC_RUNTIME"
test ! -e "$V16_PUBLIC_MANIFEST" && test ! -L "$V16_PUBLIC_MANIFEST"
for candidate_path in \
  "results/development-matched-50x6-v16.authentication.json" \
  "results/development-matched-50x6-v16.preflight.json" \
  "results/development-matched-50x6-v16.json"; do
  test ! -e "$candidate_path" && test ! -L "$candidate_path"
done
cp "$V16_PREPARE_CHECKOUT/$V16_PUBLIC_MANIFEST" "$V16_PUBLIC_MANIFEST"
cmp -s \
  "$V16_PREPARE_CHECKOUT/$V16_PUBLIC_MANIFEST" \
  "$V16_PUBLIC_MANIFEST"
```

Commit only the manifest with its exact `but diff` file ID and push only the
named branch:

```text
but commit codex/v16-runtime-preflight \
  -m "Publish V16 frozen panel manifest" \
  --changes <exact-public-manifest-file-id>
but push codex/v16-runtime-preflight
```

Verify the remote tip and record it as the pinned V16 manifest commit.

> [!IMPORTANT]
> Stop here for the current milestone. At this point authentication remains
> untouched, model calls remain zero, provider processes remain zero, no
> supervisor exists, and no spend has been authorized.

## 10. Later only: exact spend authorization and authentication

Do not execute this section until the operator separately provides this exact
sentence after inspecting the pinned public manifest:

> I acknowledge the replacement six-call v16 preflight and 300-assignment
> production run, including unbounded Codex/Cursor provider spend and up to
> $580 total Claude spend across the failed v2 preflight, failed v5 preflight,
> failed v6 authentication bootstrap, failed v7 preflight, failed v8
> production run, v9 preflight and failed production run, the abandoned
> zero-model-call v10 precommitment, the failed zero-model-call v11
> authentication bootstrap, the abandoned zero-model-call v12 precommitment,
> the abandoned zero-model-call v13 precommitment, the failed v14 preflight,
> the failed zero-model-call v15 pre-claim preparation, and the v16 preflight
> and production run.

The later authorization command must use the same frozen paths and exact text.
It creates no provider process. The foreground `authenticate` ceremony may
start only after authorization; its sanitized public receipt must be committed
through GitButler before a supervisor is generated.

```bash
set -euo pipefail
V16_PYTHON='/Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python'
V16_RUNTIME_CACHE="$HOME/.codex/epiagentbench-v16-runtime-cache"
V16_EXPECTED_COMMIT="${V16_MANIFEST_COMMIT:?set the exact published V16 manifest commit}"
V16_REPOSITORY_ROOT="${V16_AUTHORIZATION_CHECKOUT:?set the clean manifest-bound checkout}"
V16_KEY="$HOME/.codex/epiagentbench-v16-secrets/panel-auth.key"
V16_PRIVATE_STATE="$HOME/.codex/epiagentbench-v16-state/development-matched-50x6-v16.private.json"
[[ "$V16_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
test -x "$V16_PYTHON"
cd "$V16_REPOSITORY_ROOT"
test "$(git rev-parse HEAD)" = "$V16_EXPECTED_COMMIT"
test -z "$(git status --porcelain --untracked-files=all)"
export MPLBACKEND='Agg'
export MPLCONFIGDIR="$V16_RUNTIME_CACHE/matplotlib"
export NUMBA_CACHE_DIR="$V16_RUNTIME_CACHE/numba"
export PYTHONDONTWRITEBYTECODE='1'
export STARSIM_INSTALL_FONTS='0'
export XDG_CACHE_HOME="$V16_RUNTIME_CACHE/xdg"
"$V16_PYTHON" -I -S -B \
  examples/run_development_matched_panel.py authorize \
  --authentication-key "$V16_KEY" \
  --claude-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v16-credentials/claude" \
  --codex-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v16-credentials/codex" \
  --private-state "$V16_PRIVATE_STATE" \
  --public-manifest \
    results/development-matched-50x6-v16.manifest.json \
  --acknowledgement-text \
    'I acknowledge the replacement six-call v16 preflight and 300-assignment production run, including unbounded Codex/Cursor provider spend and up to $580 total Claude spend across the failed v2 preflight, failed v5 preflight, failed v6 authentication bootstrap, failed v7 preflight, failed v8 production run, v9 preflight and failed production run, the abandoned zero-model-call v10 precommitment, the failed zero-model-call v11 authentication bootstrap, the abandoned zero-model-call v12 precommitment, the abandoned zero-model-call v13 precommitment, the failed v14 preflight, the failed zero-model-call v15 pre-claim preparation, and the v16 preflight and production run.'
```

Only after that exact authorization exists may the foreground authentication
ceremony run:

```bash
set -euo pipefail
V16_PYTHON='/Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python'
V16_RUNTIME_CACHE="$HOME/.codex/epiagentbench-v16-runtime-cache"
V16_EXPECTED_COMMIT="${V16_MANIFEST_COMMIT:?set the exact published V16 manifest commit}"
V16_REPOSITORY_ROOT="${V16_AUTHORIZATION_CHECKOUT:?set the clean manifest-bound checkout}"
V16_KEY="$HOME/.codex/epiagentbench-v16-secrets/panel-auth.key"
V16_PRIVATE_STATE="$HOME/.codex/epiagentbench-v16-state/development-matched-50x6-v16.private.json"
[[ "$V16_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
test -x "$V16_PYTHON"
cd "$V16_REPOSITORY_ROOT"
test "$(git rev-parse HEAD)" = "$V16_EXPECTED_COMMIT"
test -z "$(git status --porcelain --untracked-files=all)"
export MPLBACKEND='Agg'
export MPLCONFIGDIR="$V16_RUNTIME_CACHE/matplotlib"
export NUMBA_CACHE_DIR="$V16_RUNTIME_CACHE/numba"
export PYTHONDONTWRITEBYTECODE='1'
export STARSIM_INSTALL_FONTS='0'
export XDG_CACHE_HOME="$V16_RUNTIME_CACHE/xdg"
"$V16_PYTHON" -I -S -B \
  examples/run_development_matched_panel.py authenticate \
  --authentication-key "$V16_KEY" \
  --claude-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v16-credentials/claude" \
  --codex-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v16-credentials/codex" \
  --private-state "$V16_PRIVATE_STATE" \
  --public-manifest \
    results/development-matched-50x6-v16.manifest.json \
  --acknowledge-interactive-authentication
```

Publish only the sanitized authentication receipt through GitButler. Then,
before supervisor generation, create a fresh supervisor root and fresh Cursor
Keychain service in an operator-visible terminal:

```bash
set -euo pipefail
umask 077
V16_PYTHON='/Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python'
V16_RUNTIME_CACHE="$HOME/.codex/epiagentbench-v16-runtime-cache"
V16_EXPECTED_COMMIT="${V16_AUTHENTICATION_RECEIPT_COMMIT:?set the exact published authentication-receipt commit}"
V16_REPOSITORY_ROOT="${V16_AUTHENTICATION_RECEIPT_CHECKOUT:?set the clean authentication-receipt-bound checkout}"
[[ "$V16_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
test -x "$V16_PYTHON"
cd "$V16_REPOSITORY_ROOT"
test "$(git rev-parse HEAD)" = "$V16_EXPECTED_COMMIT"
test -z "$(git status --porcelain --untracked-files=all)"
export MPLBACKEND='Agg'
export MPLCONFIGDIR="$V16_RUNTIME_CACHE/matplotlib"
export NUMBA_CACHE_DIR="$V16_RUNTIME_CACHE/numba"
export PYTHONDONTWRITEBYTECODE='1'
export STARSIM_INSTALL_FONTS='0'
export XDG_CACHE_HOME="$V16_RUNTIME_CACHE/xdg"
test ! -e "$HOME/.codex/epiagentbench-v16-supervisors"
test ! -L "$HOME/.codex/epiagentbench-v16-supervisors"
if security find-generic-password \
  -a "$USER" \
  -s epiagentbench-cursor-v16 >/dev/null 2>&1; then
  echo "Refusing to reuse the V16 Cursor Keychain service" >&2
  exit 1
fi
mkdir "$HOME/.codex/epiagentbench-v16-supervisors"
chmod 700 "$HOME/.codex/epiagentbench-v16-supervisors"
security add-generic-password \
  -a "$USER" \
  -s epiagentbench-cursor-v16 \
  -w
```

## 11. Later only: complete six-call preflight supervisor commands

After the exact acknowledgement, successful foreground authentication, and
publication of its sanitized receipt, materialize a clean checkout at that
published receipt commit. Then generate, install, inspect, and start the
preflight exactly once:

```bash
set -euo pipefail
V16_PYTHON='/Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python'
V16_RUNTIME_CACHE="$HOME/.codex/epiagentbench-v16-runtime-cache"
V16_EXPECTED_COMMIT="${V16_AUTHENTICATION_RECEIPT_COMMIT:?set the exact published authentication-receipt commit}"
V16_REPOSITORY_ROOT="${V16_EXECUTION_CHECKOUT:?set the clean receipt-bound execution checkout}"
V16_KEY="$HOME/.codex/epiagentbench-v16-secrets/panel-auth.key"
V16_PRIVATE_STATE="$HOME/.codex/epiagentbench-v16-state/development-matched-50x6-v16.private.json"
V16_RUNTIME="$HOME/.codex/epiagentbench-v16-supervisors/preflight"
[[ "$V16_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
test -x "$V16_PYTHON"
cd "$V16_REPOSITORY_ROOT"
test "$(git rev-parse HEAD)" = "$V16_EXPECTED_COMMIT"
test -z "$(git status --porcelain --untracked-files=all)"
export MPLBACKEND='Agg'
export MPLCONFIGDIR="$V16_RUNTIME_CACHE/matplotlib"
export NUMBA_CACHE_DIR="$V16_RUNTIME_CACHE/numba"
export PYTHONDONTWRITEBYTECODE='1'
export STARSIM_INSTALL_FONTS='0'
export XDG_CACHE_HOME="$V16_RUNTIME_CACHE/xdg"
"$V16_PYTHON" -I -S -B \
  examples/run_persistent_panel_supervisor.py generate \
  --operation preflight \
  --runtime-dir "$V16_RUNTIME" \
  --repository-root "$V16_REPOSITORY_ROOT" \
  --python-executable "$V16_PYTHON" \
  --runtime-cache-dir "$V16_RUNTIME_CACHE" \
  --authentication-key "$V16_KEY" \
  --claude-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v16-credentials/claude" \
  --codex-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v16-credentials/codex" \
  --private-state "$V16_PRIVATE_STATE" \
  --public-manifest \
    "$V16_REPOSITORY_ROOT/results/development-matched-50x6-v16.manifest.json" \
  --public-preflight \
    "$V16_REPOSITORY_ROOT/results/development-matched-50x6-v16.preflight.json" \
  --cursor-keychain-service epiagentbench-cursor-v16 \
  --cursor-keychain-account "$USER"
"$V16_PYTHON" -I -S -B \
  examples/run_persistent_panel_supervisor.py install \
  --runtime-dir "$V16_RUNTIME" \
  --authentication-key "$V16_KEY"
"$V16_PYTHON" -I -S -B \
  examples/run_persistent_panel_supervisor.py status \
  --runtime-dir "$V16_RUNTIME" \
  --authentication-key "$V16_KEY"
# Start only if authenticated status is exactly inactive and not-started.
"$V16_PYTHON" -I -S -B \
  examples/run_persistent_panel_supervisor.py start \
  --runtime-dir "$V16_RUNTIME" \
  --authentication-key "$V16_KEY"
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
V16_PYTHON='/Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python'
V16_RUNTIME_CACHE="$HOME/.codex/epiagentbench-v16-runtime-cache"
V16_EXPECTED_COMMIT="${V16_PREFLIGHT_RECEIPT_COMMIT:?set the exact published preflight-receipt commit}"
V16_REPOSITORY_ROOT="${V16_PRODUCTION_CHECKOUT:?set the clean preflight-receipt-bound checkout}"
V16_KEY="$HOME/.codex/epiagentbench-v16-secrets/panel-auth.key"
V16_PRIVATE_STATE="$HOME/.codex/epiagentbench-v16-state/development-matched-50x6-v16.private.json"
V16_RUNTIME="$HOME/.codex/epiagentbench-v16-supervisors/production"
[[ "$V16_EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]
test -x "$V16_PYTHON"
cd "$V16_REPOSITORY_ROOT"
test "$(git rev-parse HEAD)" = "$V16_EXPECTED_COMMIT"
test -z "$(git status --porcelain --untracked-files=all)"
export MPLBACKEND='Agg'
export MPLCONFIGDIR="$V16_RUNTIME_CACHE/matplotlib"
export NUMBA_CACHE_DIR="$V16_RUNTIME_CACHE/numba"
export PYTHONDONTWRITEBYTECODE='1'
export STARSIM_INSTALL_FONTS='0'
export XDG_CACHE_HOME="$V16_RUNTIME_CACHE/xdg"
"$V16_PYTHON" -I -S -B \
  examples/run_persistent_panel_supervisor.py generate \
  --operation production \
  --runtime-dir "$V16_RUNTIME" \
  --repository-root "$V16_REPOSITORY_ROOT" \
  --python-executable "$V16_PYTHON" \
  --runtime-cache-dir "$V16_RUNTIME_CACHE" \
  --authentication-key "$V16_KEY" \
  --claude-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v16-credentials/claude" \
  --codex-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v16-credentials/codex" \
  --private-state "$V16_PRIVATE_STATE" \
  --public-manifest \
    "$V16_REPOSITORY_ROOT/results/development-matched-50x6-v16.manifest.json" \
  --public-results \
    "$V16_REPOSITORY_ROOT/results/development-matched-50x6-v16.json" \
  --cursor-keychain-service epiagentbench-cursor-v16 \
  --cursor-keychain-account "$USER"
"$V16_PYTHON" -I -S -B \
  examples/run_persistent_panel_supervisor.py install \
  --runtime-dir "$V16_RUNTIME" \
  --authentication-key "$V16_KEY"
"$V16_PYTHON" -I -S -B \
  examples/run_persistent_panel_supervisor.py status \
  --runtime-dir "$V16_RUNTIME" \
  --authentication-key "$V16_KEY"
# Start only if authenticated status is exactly inactive and not-started.
"$V16_PYTHON" -I -S -B \
  examples/run_persistent_panel_supervisor.py start \
  --runtime-dir "$V16_RUNTIME" \
  --authentication-key "$V16_KEY"
```

## Terminal rules

- Never reuse any V15 cohort, key, credential, state, runtime, or claim.
- Never create a V16 private artifact before the runtime receipt is committed,
  pushed through GitButler, pinned, and successfully re-attested.
- Never substitute a PATH-selected Python for the exact V5 interpreter, omit
  `-I -S -B`, or inject `PYTHONPATH`/startup hooks.
- Never place a receipt, verification summary, or any other staging file
  inside the runtime-cache root; it may contain only `matplotlib`, `numba`, and
  `xdg`.
- Never change, recreate, relink, chmod, or relocate the bound cache tree.
- Never retry a freeze or prepare after the canonical pending freeze claim
  exists without its authenticated completion.
- Never retry after a V16 private/random artifact or durable start exists.
- Never infer spend authorization from this runbook, receipt, or manifest.
- Never publish the raw Python entrypoint/bootstrap binding, cache paths,
  environment, inventory, or device/inode/UID metadata; only their opaque
  hashes belong in public receipts and manifests.
- Never expose provider output, credentials, prompts, observations, hidden
  episode identifiers/families, schedules, seeds, traces, or scores before the
  final release gate.
