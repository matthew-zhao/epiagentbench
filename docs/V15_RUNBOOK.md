# EpiAgentBench V15 execution runbook

V15 is the fresh replacement for the non-resumable V14 preflight. This
runbook versions the control plane only. Creating or publishing this file does
not prepare a cohort, authorize spend, authenticate a provider, create a
supervisor, or make a model call.

The required order is:

1. publish and pin the V15 code-and-runbook commit;
2. materialize and prove the fresh checkout at that exact published commit;
3. create only the fresh V15 private namespaces needed for preparation and
   freeze the cohort from the proven checkout;
4. prepare and publish the fresh V15 manifest;
5. obtain the exact manifest-bound spend acknowledgement;
6. authorize, authenticate in the foreground, and publish the sanitized
   authentication receipt;
7. create the fresh Cursor credential and supervisor namespaces, then create
   and start the six-call preflight supervisor exactly once;
8. only after all six profiles pass and the receipt is published, create and
   start the 300-assignment production supervisor exactly once.

No step may be retried after an ambiguous or durable start. A failed or
ambiguous panel is superseded with a fresh version.

## Frozen V15 identifiers

| Surface | V15 value |
|---|---|
| Panel and cohort | `development-matched-50x6-v15` |
| Top-level schema | `development_matched_panel_v15` |
| Persistent-supervisor contract | `epiagentbench.persistent_supervisor_contract.v5` |
| Assignments | 50 episodes × 6 profiles = 300 |
| Per-call timeout | 1,800 seconds |
| Claude per-call ceiling | $5 |
| V15 Claude ceiling | $510 |
| Prior conservative Claude ceiling | $70 |
| Cumulative Claude ceiling | $580 |
| Codex/Cursor ceiling | unbounded |
| Cursor Keychain service | `epiagentbench-cursor-v15` |

The $70 prior ceiling includes $10 for V14's two returned Claude preflight
calls. V14 then stopped after the returned Codex Sol call; it started no
production assignment.

## Fresh path namespace

Resolve `$HOME` before use. These names are part of the V15 operator contract;
none may point at, alias, or reuse a V14 path.

```text
$HOME/.codex/epiagentbench-50x6-v15-prepare-worktree
$HOME/.codex/epiagentbench-v15-cohort
$HOME/.codex/epiagentbench-v15-secrets/panel-auth.key
$HOME/.codex/epiagentbench-v15-state/development-matched-50x6-v15.private.json
$HOME/.codex/epiagentbench-v15-credentials/claude
$HOME/.codex/epiagentbench-v15-credentials/codex
$HOME/.codex/epiagentbench-v15-supervisors/preflight
$HOME/.codex/epiagentbench-v15-supervisors/production
```

The public files live in the frozen checkout:

```text
results/development-matched-50x6-v15.manifest.json
results/development-matched-50x6-v15.authentication.json
results/development-matched-50x6-v15.preflight.json
results/development-matched-50x6-v15.json
```

The checkout must be pinned to the published V15 prerequisite commit and clean
before any V15 private artifact is created. The authentication key, private
state, cohort, credentials, and supervisor directories must remain outside the
repository and outside OS temporary storage.

## 1. Materialize and prove the frozen checkout

Set `V15_PREREQUISITE_COMMIT` to the published full commit hash. From the
GitButler-managed primary checkout, prove the remote branch points at that
exact commit, prove the destination has never existed, and create the detached
worktree exactly once:

```bash
set -e
: "${V15_PREREQUISITE_COMMIT:?set the published V15 prerequisite commit}"
V15_REMOTE_REF=refs/heads/codex/v15-supervisor-snapshot-hardening
test "$(git ls-remote origin "$V15_REMOTE_REF" | cut -f1)" = \
  "$V15_PREREQUISITE_COMMIT"
if [ -e "$HOME/.codex/epiagentbench-50x6-v15-prepare-worktree" ] || \
   [ -L "$HOME/.codex/epiagentbench-50x6-v15-prepare-worktree" ]; then
  echo "Refusing to reuse V15 prepare checkout" >&2
  exit 1
fi
git worktree add --detach \
  "$HOME/.codex/epiagentbench-50x6-v15-prepare-worktree" \
  "$V15_PREREQUISITE_COMMIT"
cd "$HOME/.codex/epiagentbench-50x6-v15-prepare-worktree"
test "$(pwd -P)" = \
  "$HOME/.codex/epiagentbench-50x6-v15-prepare-worktree"
test "$(git rev-parse HEAD)" = "$V15_PREREQUISITE_COMMIT"
test -z "$(git status --porcelain --untracked-files=all)"
```

Do not create the authentication key, cohort, private state, credential
directories, or any supervisor runtime until all of these checks pass.

## 2. Create fresh manifest-only private prerequisites

Use a `077` umask. Create a new 32-byte authentication key and empty,
current-user-only Claude and Codex credential directories. Cursor credentials
and supervisor directories are not consumed by `freeze-private-cohort` or
`prepare`; defer them until after manifest-bound authorization and foreground
authentication.

```bash
set -e
umask 077
set -o noclobber
for candidate_path in \
  "$HOME/.codex/epiagentbench-v15-secrets" \
  "$HOME/.codex/epiagentbench-v15-state" \
  "$HOME/.codex/epiagentbench-v15-credentials" \
  "$HOME/.codex/epiagentbench-v15-cohort"; do
  if [ -e "$candidate_path" ] || [ -L "$candidate_path" ]; then
    echo "Refusing to reuse V15 path: $candidate_path" >&2
    exit 1
  fi
done
mkdir \
  "$HOME/.codex/epiagentbench-v15-secrets" \
  "$HOME/.codex/epiagentbench-v15-state" \
  "$HOME/.codex/epiagentbench-v15-credentials"
mkdir \
  "$HOME/.codex/epiagentbench-v15-credentials/claude" \
  "$HOME/.codex/epiagentbench-v15-credentials/codex"
chmod 700 \
  "$HOME/.codex/epiagentbench-v15-secrets" \
  "$HOME/.codex/epiagentbench-v15-state" \
  "$HOME/.codex/epiagentbench-v15-credentials" \
  "$HOME/.codex/epiagentbench-v15-credentials/claude" \
  "$HOME/.codex/epiagentbench-v15-credentials/codex"
openssl rand 32 > \
  "$HOME/.codex/epiagentbench-v15-secrets/panel-auth.key"
chmod 600 "$HOME/.codex/epiagentbench-v15-secrets/panel-auth.key"
```

Freeze a new hidden cohort from the already proven checkout. The destination
must not already exist:

```bash
PYTHONPATH=src python3 -m epiagentbench.cli freeze-private-cohort \
  --cohort-id development-matched-50x6-v15 \
  --output-directory "$HOME/.codex/epiagentbench-v15-cohort" \
  --authentication-key-file \
    "$HOME/.codex/epiagentbench-v15-secrets/panel-auth.key" \
  --episodes 50 \
  --backend starsim-ltc-v3
```

Do not inspect or publish its packs, family map, seeds, or schedule.

## 3. Prepare and publish the V15 manifest

Immediately prove the exact checkout again before preparation:

```bash
: "${V15_PREREQUISITE_COMMIT:?set the published V15 prerequisite commit}"
test "$(pwd -P)" = \
  "$HOME/.codex/epiagentbench-50x6-v15-prepare-worktree"
test "$(git rev-parse HEAD)" = "$V15_PREREQUISITE_COMMIT"
test -z "$(git status --porcelain --untracked-files=all)"
```

Then prepare:

```bash
PYTHONPATH=src python3 examples/run_development_matched_panel.py prepare \
  --cohort-manifest \
    "$HOME/.codex/epiagentbench-v15-cohort/cohort.manifest" \
  --authentication-key \
    "$HOME/.codex/epiagentbench-v15-secrets/panel-auth.key" \
  --claude-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v15-credentials/claude" \
  --codex-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v15-credentials/codex" \
  --private-state \
    "$HOME/.codex/epiagentbench-v15-state/development-matched-50x6-v15.private.json" \
  --public-manifest \
    results/development-matched-50x6-v15.manifest.json \
  --timeout 1800 \
  --claude-max-budget-usd 5
```

Preparation must be provider-process-free. Validate and publish only the public
manifest through GitButler. Keep the authenticated private state untracked.
Stop if the manifest cannot be committed from an otherwise clean checkout.

## 4. Obtain exact spend authorization

The preparation request and this runbook are not spend authorization. After the
exact public manifest is committed, the operator must supply this sentence
verbatim in a new instruction:

> I acknowledge the replacement six-call v15 preflight and 300-assignment
> production run, including unbounded Codex/Cursor provider spend and up to
> $580 total Claude spend across the failed v2 preflight, failed v5 preflight,
> failed v6 authentication bootstrap, failed v7 preflight, failed v8
> production run, v9 preflight and failed production run, the abandoned
> zero-model-call v10 precommitment, the failed zero-model-call v11
> authentication bootstrap, the abandoned zero-model-call v12 precommitment,
> the abandoned zero-model-call v13 precommitment, the failed v14 preflight,
> and the v15 preflight and production run.

Only after receiving that exact sentence, pass it unchanged to `authorize`:

```bash
PYTHONPATH=src python3 examples/run_development_matched_panel.py authorize \
  --authentication-key \
    "$HOME/.codex/epiagentbench-v15-secrets/panel-auth.key" \
  --claude-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v15-credentials/claude" \
  --codex-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v15-credentials/codex" \
  --private-state \
    "$HOME/.codex/epiagentbench-v15-state/development-matched-50x6-v15.private.json" \
  --public-manifest \
    results/development-matched-50x6-v15.manifest.json \
  --acknowledgement-text \
    'I acknowledge the replacement six-call v15 preflight and 300-assignment production run, including unbounded Codex/Cursor provider spend and up to $580 total Claude spend across the failed v2 preflight, failed v5 preflight, failed v6 authentication bootstrap, failed v7 preflight, failed v8 production run, v9 preflight and failed production run, the abandoned zero-model-call v10 precommitment, the failed zero-model-call v11 authentication bootstrap, the abandoned zero-model-call v12 precommitment, the abandoned zero-model-call v13 precommitment, the failed v14 preflight, and the v15 preflight and production run.'
```

Authorization writes only the authenticated private receipt. It does not log in
or call a model.

## 5. Authenticate in the foreground

Run from an operator-visible terminal:

```bash
PYTHONPATH=src python3 examples/run_development_matched_panel.py authenticate \
  --authentication-key \
    "$HOME/.codex/epiagentbench-v15-secrets/panel-auth.key" \
  --claude-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v15-credentials/claude" \
  --codex-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v15-credentials/codex" \
  --private-state \
    "$HOME/.codex/epiagentbench-v15-state/development-matched-50x6-v15.private.json" \
  --public-manifest \
    results/development-matched-50x6-v15.manifest.json \
  --acknowledge-interactive-authentication
```

Validate and publish only the sanitized authentication receipt. Never capture
or publish tokens, OAuth state, provider output, or credential contents. The
receipt must be committed before supervisor generation.

## 6. Create fresh runtime-only prerequisites

Only after the manifest-bound acknowledgement, authorization, foreground
authentication, and published authentication receipt may the operator create
the V15 supervisor root and Cursor Keychain service. Both must still be fresh.
Store the Cursor API key through the interactive Keychain prompt; never place
it in a command line, environment file, plist, or repository.

```bash
set -e
umask 077
set -o noclobber
if [ -e "$HOME/.codex/epiagentbench-v15-supervisors" ] || \
   [ -L "$HOME/.codex/epiagentbench-v15-supervisors" ]; then
  echo "Refusing to reuse V15 supervisor root" >&2
  exit 1
fi
if security find-generic-password \
  -a "$USER" \
  -s epiagentbench-cursor-v15 >/dev/null 2>&1; then
  echo "Refusing to reuse V15 Cursor Keychain service" >&2
  exit 1
fi
mkdir "$HOME/.codex/epiagentbench-v15-supervisors"
chmod 700 "$HOME/.codex/epiagentbench-v15-supervisors"
security add-generic-password \
  -a "$USER" \
  -s epiagentbench-cursor-v15 \
  -w
```

## 7. Create and start preflight exactly once

Generate a new runtime directory exactly once, then install it. Before starting,
authenticated status must show the expected panel and operation, an
authenticated configuration, and no start request.

```bash
PYTHONPATH=src python3 examples/run_persistent_panel_supervisor.py generate \
  --operation preflight \
  --runtime-dir "$HOME/.codex/epiagentbench-v15-supervisors/preflight" \
  --repository-root "$PWD" \
  --python-executable "$(command -v python3)" \
  --authentication-key \
    "$HOME/.codex/epiagentbench-v15-secrets/panel-auth.key" \
  --claude-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v15-credentials/claude" \
  --codex-secure-storage-dir \
    "$HOME/.codex/epiagentbench-v15-credentials/codex" \
  --private-state \
    "$HOME/.codex/epiagentbench-v15-state/development-matched-50x6-v15.private.json" \
  --public-manifest \
    results/development-matched-50x6-v15.manifest.json \
  --public-preflight \
    results/development-matched-50x6-v15.preflight.json \
  --cursor-keychain-service epiagentbench-cursor-v15 \
  --cursor-keychain-account "$USER"

PYTHONPATH=src python3 examples/run_persistent_panel_supervisor.py install \
  --runtime-dir "$HOME/.codex/epiagentbench-v15-supervisors/preflight" \
  --authentication-key \
    "$HOME/.codex/epiagentbench-v15-secrets/panel-auth.key"

PYTHONPATH=src python3 examples/run_persistent_panel_supervisor.py status \
  --runtime-dir "$HOME/.codex/epiagentbench-v15-supervisors/preflight" \
  --authentication-key \
    "$HOME/.codex/epiagentbench-v15-secrets/panel-auth.key"

PYTHONPATH=src python3 examples/run_persistent_panel_supervisor.py start \
  --runtime-dir "$HOME/.codex/epiagentbench-v15-supervisors/preflight" \
  --authentication-key \
    "$HOME/.codex/epiagentbench-v15-secrets/panel-auth.key"
```

Never call `start` again. Monitor only authenticated safe status. On the normal
success path, the one-shot worker verifies supervisor completion, finalizes the
staged trace-free candidate, and reports `released` without an operator
command. If the supervisor is unhealthy, disappears, becomes ambiguous, or
records an incident, do not restart or finalize it; audit and supersede V15.

The explicit `finalize` command is recovery-only. Use it only after an audit
proves the authenticated core completed successfully but the worker crashed
before publication, with no terminal or release-validation incident:

```bash
PYTHONPATH=src python3 examples/run_persistent_panel_supervisor.py finalize \
  --runtime-dir "$HOME/.codex/epiagentbench-v15-supervisors/preflight" \
  --authentication-key \
    "$HOME/.codex/epiagentbench-v15-secrets/panel-auth.key"
```

Do not run recovery finalization on an ordinary released run. Validate that all
six profiles passed and publish the receipt before production.

## 8. Create and start production exactly once

Production uses the same command sequence and safeguards, with these
substitutions:

```text
--operation production
--runtime-dir $HOME/.codex/epiagentbench-v15-supervisors/production
--public-results results/development-matched-50x6-v15.json
```

Generate, install, inspect inactive status, and start exactly once. Do not
create the production runtime unless the committed preflight receipt passes all
six profiles. Expect automatic release only after authenticated completion of
all 300 assignments; reserve explicit finalization for the same audited
post-completion crash-recovery state described above. Before publishing
results, validate the frozen manifest, private state, cohort retirement,
leakage gates, trace consistency, fixed denominators, and release schema.

## Terminal rules

- Never reuse V14's cohort, keys, credentials, runtime, private state, or
  authorization.
- Never retry a durable provider assignment or a started supervisor.
- Never infer permission to spend from preparation, documentation, a prior
  panel's acknowledgement, or a generic flag.
- Never inspect or expose provider output, prompts, observations, hidden
  episode identifiers or families, schedules, seeds, credentials, traces, or
  scores before the final release gate.
- Never publish private state or authentication material.
