# EpiAgentBench V48 execution runbook

> [!CAUTION]
> **CONTROL-PLANE DESIGN ONLY — NO V48 AUTHENTICATION, PROVIDER, SPEND,
> PREFLIGHT, PRODUCTION, OR MODEL CALL IS AUTHORIZED.**
>
> This runbook freezes the V48 names and gates. It does not authorize creation
> of a runtime receipt, private cohort, manifest, credentials, supervisor, or
> result. Commit values remain explicit placeholders until each public artifact
> is created under a later, separately authorized ceremony and independently
> verified.

## Closed predecessors

V35, V40, V46, and V47 are terminal and non-resumable. V35 published its
control plane but stopped during provider-free runtime-receipt publisher setup.
V40 stopped during control-plane authoring. V46 stopped during provider-free
scientific-runtime cache-isolation validation. V47 sealed two local control
candidates but stopped during publication precreation scope validation; those
candidates were never committed or published and are non-reusable.

Their exact public closeout files and SHA-256 values are immutable historical
inputs:

| Version | Supersession record | Contract test |
|---|---|---|
| V35 | `results/development-matched-50x6-v35.superseded.json` — `843654f16c0bf7a2c461d229ff71a1f3bdf5e36a90ebc8da019d34f8dcf88cf0` | `tests/test_v35_supersession.py` — `68c45bc342152249e48a2e529b0908e2b8ea287779e7709025a80d5334477042` |
| V40 | `results/development-matched-50x6-v40.superseded.json` — `76f533598108bda5996fbabcf7e220d36ffc3675648db744a4dc4cad44dae611` | `tests/test_v40_supersession.py` — `4ce9b0fdebfcc3e78aefd7cb3146ab44e0d3079eac04d343b9d71c756b840419` |
| V46 | `results/development-matched-50x6-v46.superseded.json` — `b751588e905d133ea99c08d42668b50f9d658a1e622c5a6560611c19e052d7bc` | `tests/test_v46_supersession.py` — `2622fdc4fca24ead7e1dfd510055991117c1872bea9757889262b6b001ce6406` |
| V47 | `results/development-matched-50x6-v47.superseded.json` — `69950caf5327cee3523154ea8194f2f8b9b79321cc9f0bf529c876f04bd1c75a` | `tests/test_v47_supersession.py` — `70a0f447ff7b4affbbfc2001c58c7492ff0249c97cb8023a46ba65ecbc793ab1` |

The exact public source for V48 is the V47 two-file closeout commit
`31928645baff6182852c9c88a393b6fcaa6be557`, whose sole parent is
`e8946a10997863412d4a2ec0113b72e066a73550`, tree is
`e21dacbbfc859206a15c7dbbbb9feaf214ca78d5`, and fixed-origin ref is
`refs/heads/codex/v48-v47-control-plane-publication-terminal-closeout`. Its
exact delta is only the V47 pair above under
`epiagentbench.panel_supersession.v31`. The source parent has tree
`3e162b89b8288ceb63776bfd14f2d3f1a3738dd1` and sole parent
`ab2043215d034c06528100033b18de563d754d9c`. V48 begins only as the direct
child of the independently pinned V47 closeout.

No predecessor panel, cohort, cache, state, credential, checkout, supervisor,
Keychain, freeze-claim, socket, temporary, or output namespace is reusable.

## V48 safety invariants

1. V48 uses fresh panel, cohort, cache, state, credential, checkout,
   supervisor, Keychain, freeze-claim, and public-output namespaces. No V47 or
   earlier private or unpublished artifact is copied, moved, relinked,
   imported, or consumed.
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
   production boundary is terminal for V48. No monitor may restart it.
7. Provider output, prompts, observations, hidden episode identifiers or
   families, credentials, OAuth state, private seeds or schedule, traces, and
   scores remain absent from public and monitoring surfaces until final release.
8. Publication uses GitButler only from fresh standalone primary clones.
   Direct `git push` is forbidden. Each named push is attempted once; failure or
   ambiguity is terminal and never retried from the same or another workspace.

## Frozen schemas and identifiers

| Surface | V48 value |
|---|---|
| Panel and cohort | `development-matched-50x6-v48` |
| Top-level schema | `development_matched_panel_v48` |
| Assignments | 50 episodes × 6 profiles = 300 |
| Persistent-supervisor contract | `epiagentbench.persistent_supervisor_contract.v24` |
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
| Starsim smoke control ID | `v48-stop-direct-care` |
| Starsim smoke scenario | `v48_contact_transmission_with_matched_contact_stop` |
| Starsim smoke golden digest | `sha256:e91a8e76e32048c3bbc63c02ee2a1279fc53a6af078130a7d3baaa91ac8a3d5f` |
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
| Provider CLI contract | `epiagentbench.provider_cli_contract.v3` |
| Provider CLI discovery (retained) | `epiagentbench.provider_cli_discovery.v2` |
| Claude authentication (retained) | `epiagentbench.claude_auth.v3` |
| Codex authentication (retained) | `epiagentbench.codex_auth.v1` |
| Provider progress (retained) | `epiagentbench.provider_progress.v1` |
| Cohort preparation (retained) | `epiagentbench.cohort_preparation.v1` |
| Cohort retirement (retained) | `epiagentbench.cohort_retirement.v1` |
| Terminal receipt reconciliation (retained) | `epiagentbench.terminal_receipt_reconciliation.v1` |
| V35 supersession (inherited) | `epiagentbench.panel_supersession.v28` |
| V40 supersession (inherited) | `epiagentbench.panel_supersession.v29` |
| V46 supersession (inherited) | `epiagentbench.panel_supersession.v30` |
| V47 supersession (inherited) | `epiagentbench.panel_supersession.v31` |
| V48 supersession (reserved terminal schema) | `epiagentbench.panel_supersession.v32` |
| V48 cohort freeze claim | `epiagentbench.v48_cohort_freeze_claim.v1` |
| V48 cohort freeze completion | `epiagentbench.v48_cohort_freeze_completion.v1` |
| V48 cohort freeze | `epiagentbench.v48_cohort_freeze.v2` |
| Runtime receipt | `results/development-matched-50x6-v48.runtime.json` |
| Manifest | `results/development-matched-50x6-v48.manifest.json` |
| Authentication receipt | `results/development-matched-50x6-v48.authentication.json` |
| Preflight receipt | `results/development-matched-50x6-v48.preflight.json` |
| Production result | `results/development-matched-50x6-v48.json` |
| Supersession record | `results/development-matched-50x6-v48.superseded.json` |
| Cursor Keychain service | `epiagentbench-cursor-v48` |
| Cursor Keychain account | `matthew.zhao` |
| Socket and temporary prefix | `eab48-` |
| Scientific Python | `/Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python` |
| Python flags | `-I -S -B` |
| Python version | `3.13.7` |
| Starsim version | `3.5.1` |
| Control ref | `refs/heads/codex/v48-control-plane` |
| Control-publication terminal ref | `refs/heads/codex/v48-control-plane-publication-terminal-closeout` |
| Runtime-receipt ref | `refs/heads/codex/v48-runtime-preflight` |
| Manifest publication ref | `refs/heads/codex/v48-runtime-preflight` |
| Authentication publication ref | `refs/heads/codex/v48-runtime-preflight` |
| Preflight publication ref | `refs/heads/codex/v48-runtime-preflight` |
| Terminal runtime-publication ref | `refs/heads/codex/v48-runtime-publication-terminal-closeout` |
| Terminal preflight-closeout ref | `refs/heads/codex/v48-preflight-terminal-closeout` |
| Successful production-result ref | `refs/heads/codex/v48-production-results` |
| Terminal production-closeout ref | `refs/heads/codex/v48-terminal-closeout` |
| Fixed read-only origin | `https://github.com/matthew-zhao/epiagentbench.git` |
| V47 terminal-closeout parent | `e8946a10997863412d4a2ec0113b72e066a73550` |
| V47 terminal-closeout ref | `refs/heads/codex/v48-v47-control-plane-publication-terminal-closeout` |
| V47 terminal-closeout commit / V48 source | `31928645baff6182852c9c88a393b6fcaa6be557` |
| V48 source tree | `e21dacbbfc859206a15c7dbbbb9feaf214ca78d5` |
| Control commit | `<V48_CONTROL_COMMIT_40_HEX>` |
| Control-publication terminal commit | `<V48_CONTROL_PUBLICATION_TERMINAL_CLOSEOUT_COMMIT_40_HEX>` |
| Runtime-receipt commit | `<V48_RUNTIME_RECEIPT_COMMIT_40_HEX>` |
| Manifest commit | `<V48_MANIFEST_COMMIT_40_HEX>` |
| Authentication-receipt commit | `<V48_AUTHENTICATION_RECEIPT_COMMIT_40_HEX>` |
| Passing-preflight commit | `<V48_PREFLIGHT_RECEIPT_COMMIT_40_HEX>` |
| Terminal runtime-publication commit | `<V48_RUNTIME_PUBLICATION_TERMINAL_CLOSEOUT_COMMIT_40_HEX>` |
| Terminal preflight-closeout commit | `<V48_PREFLIGHT_TERMINAL_CLOSEOUT_COMMIT_40_HEX>` |
| Successful production-result commit | `<V48_PRODUCTION_RESULT_COMMIT_40_HEX>` |
| Terminal production-closeout commit | `<V48_TERMINAL_CLOSEOUT_COMMIT_40_HEX>` |

The Starsim digest row is an unsealable Phase B1 slot. It becomes sealable only
when its value is an exact lowercase SHA-256 reproduced by all four independent
cache-isolated discoveries and confirmed by both final smokes. The literal
pending marker must be absent from every sealed candidate.

### Retained root-managed Glean contract

V48 accepts only the reviewed root-managed contract that superseded V34. The
gateway must still be HTTPS, have no user information, explicit port, query, or
fragment, and match both the source-owned approved digest and the exact route
`/rest/api/v1`. The approved redacted endpoint digest is
`sha256:b27f5a0a001afd9310d20c04af550e13c440f2d88ee0891b95c2f73f7186d305`,
and the allowlist identity is
`approved_managed_gateway_v2`. Neither this runbook nor any public receipt
discloses the host or either OAuth client identifier.

Claude managed settings must have exactly four top-level keys: the pinned API
key helper, the exact 17-key managed environment, one reviewed default-model
field, and the pinned telemetry-header helper. The model field must be a string
equal to the approved `sonnet` alias. Its public semantic identity uses only
`approved_managed_claude_default_model_v1` and a redacted placeholder; the raw
setting is never copied into a public receipt. This root-managed default is not
benchmark model authority: every Claude invocation still supplies the frozen
profile's explicit `--model`, and the existing provider-reported observed-model
and fallback validation remains mandatory.

Published V35 advanced the provider CLI contract for that safe public semantic
projection. V48 retains `epiagentbench.provider_cli_contract.v3` unchanged.
The existing environment allowlist, helper pins, telemetry checks, derived
Anthropic route, credential-isolation rules, and no-secret field scan remain
exact and fail closed. This retained source contract performs no helper,
authentication, provider, or model call.

Every V48 validator rejects predecessor panel/schema pairs
`development-matched-50x6-v35` / `development_matched_panel_v35`,
`development-matched-50x6-v40` / `development_matched_panel_v40`,
`development-matched-50x6-v46` / `development_matched_panel_v46`, and
`development-matched-50x6-v47` / `development_matched_panel_v47`; every
predecessor panel/cohort lifecycle namespace; and persistent-supervisor
contracts `epiagentbench.persistent_supervisor_contract.v20`,
`epiagentbench.persistent_supervisor_contract.v21`,
`epiagentbench.persistent_supervisor_contract.v22`, and
`epiagentbench.persistent_supervisor_contract.v23` before control action.
Contracts v21, v22, and v23 are non-reusable. Persistent-supervisor state v4,
identity v3, protocol v9, LaunchAgent v16, worker status v6, provider CLI v3,
and every other generic wire schema are deliberately retained and re-attested.

The V48 control commit cannot contain its own hash. At execution time
`V48_CONTROL_COMMIT` must be an independently supplied lowercase 40-hex value
that exactly matches `refs/heads/codex/v48-control-plane`, exactly matches the
clean runtime checkout's `HEAD`, and is the direct child of the independently
pinned V47 control-publication terminal-closeout commit. The later
runtime-receipt commit must
exactly match
`refs/heads/codex/v48-runtime-preflight`, descend from that pinned control
commit, and add only the existing canonical V48 runtime receipt.

The control-plane publisher is the fresh standalone primary clone
`/Users/matthew.zhao/Documents/Disease Surveillance/epiagentbench-v48-control-plane-workspace`,
rooted at `31928645baff6182852c9c88a393b6fcaa6be557`. Its sole V48 commit may modify
or add only these 17 paths:

- `README.md`;
- `docs/PERSISTENT_RUNNER_PROTOCOL.md`;
- `docs/V35_RUNBOOK.md`;
- `docs/V48_DESIGN.md`;
- `docs/V48_RUNBOOK.md`;
- `src/epiagentbench/development_matched_panel.py`;
- `src/epiagentbench/launchd_agent.py`;
- `tests/test_development_matched_panel.py`;
- `tests/test_persistent_launchd.py`;
- `tests/test_persistent_runner_cli.py`;
- `tests/test_terminal_receipt_attestation.py`;
- `tests/test_v28_typed_contract_attestation.py`;
- `tests/test_v48_deferred_cursor_credential.py`;
- `tests/test_v48_preclaim_reconciliation.py`;
- `tests/test_v48_preparation_substages.py`;
- `tests/test_v48_publication_topology.py`; and
- `tests/test_v48_smoke_tmpdir.py`.

The personal GitHub route must safely resolve to `matthew-zhao` with boolean
push permission for the fixed origin, without printing credential material.
GitButler's managed `pre-commit` and `post-checkout` hooks must remain present
with SHA-256 values
`4d4892f5df8d68688d564b08a9b7ab990ee1af49f85250e94bb9e088f23c5728`
and `9bc3e13271e9bbbebdcb4543cc051e869f10c7a8219e1bff807595e52b345afc`;
`core.hooksPath` remains unset. After all tests and scope checks pass, the only
publication command for the control-plane phase is one named
`but push codex/v48-control-plane`. The
operator-approved GitButler transport may internally use `git push
--no-verify`; no operator command may pass a bypass flag, disable a hook, or
alter hook routing.

Every later publication requires its own explicit authorization. Its exact
fresh standalone GitButler publisher and named push are frozen below; no other
publisher path or branch name is valid. Each named push is attempted once for
the commit it publishes. The staged receipt branch therefore permits at most
one separately authorized invocation for each of its four ordered one-file
commits, never a retry of the same commit.

| Publication | Destination ref | Exact standalone publisher | Required sole parent | Exact named push |
|---|---|---|---|---|
| Control-publication terminal closeout | `refs/heads/codex/v48-control-plane-publication-terminal-closeout` | `/Users/matthew.zhao/Documents/Disease Surveillance/epiagentbench-v48-control-plane-publication-terminal-closeout-workspace` | `31928645baff6182852c9c88a393b6fcaa6be557` | `but push codex/v48-control-plane-publication-terminal-closeout` |
| Staged runtime, manifest, authentication, or passing-preflight receipt | `refs/heads/codex/v48-runtime-preflight` | `/Users/matthew.zhao/Documents/Disease Surveillance/epiagentbench-v48-runtime-preflight-workspace` | Latest independently pinned predecessor required by the four-commit order | `but push codex/v48-runtime-preflight` |
| Runtime-publication terminal closeout | `refs/heads/codex/v48-runtime-publication-terminal-closeout` | `/Users/matthew.zhao/Documents/Disease Surveillance/epiagentbench-v48-runtime-publication-terminal-closeout-workspace` | Last V48 commit independently pinned from the fixed origin | `but push codex/v48-runtime-publication-terminal-closeout` |
| Preflight terminal closeout | `refs/heads/codex/v48-preflight-terminal-closeout` | `/Users/matthew.zhao/Documents/Disease Surveillance/epiagentbench-v48-preflight-terminal-closeout-workspace` | Independently pinned authentication-receipt commit | `but push codex/v48-preflight-terminal-closeout` |
| Successful production result | `refs/heads/codex/v48-production-results` | `/Users/matthew.zhao/Documents/Disease Surveillance/epiagentbench-v48-production-results-workspace` | Independently pinned passing-preflight commit | `but push codex/v48-production-results` |
| Terminal production closeout | `refs/heads/codex/v48-terminal-closeout` | `/Users/matthew.zhao/Documents/Disease Surveillance/epiagentbench-v48-terminal-closeout-workspace` | Independently pinned passing-preflight commit | `but push codex/v48-terminal-closeout` |

A table row becomes active only when that mutually exclusive path is selected
and separately authorized. Creating a publisher or invoking its push before
that selection is forbidden. A failed or ambiguous named push is terminal and
must not be retried from the listed publisher or from any replacement path.

Immediately before every separately authorized named push, run the same
provider-free gate below from the selected publisher. On a ref's first use,
`V48_EXPECTED_REMOTE_TIP` must be the literal `absent`; the query must return
zero bytes. For the second through fourth ordered publications on the staged
receipt ref, it must instead be the lowercase 40-hex commit independently
pinned after the preceding publication, and the query must return exactly that
one hash/ref record. No local or push-returned value may supply it. The block
below freezes the current control-plane phase. A later authorization must
replace all three `V48_*` selection values only with the exact publisher,
destination ref, and expected predecessor fixed by the selected table row.

```sh
# V48_PREPUBLICATION_GATE_BEGIN
set -euo pipefail
V48_PUBLISHER='/Users/matthew.zhao/Documents/Disease Surveillance/epiagentbench-v48-control-plane-workspace'
V48_DESTINATION_REF='refs/heads/codex/v48-control-plane'
V48_EXPECTED_REMOTE_TIP=absent
V48_FIXED_ORIGIN='https://github.com/matthew-zhao/epiagentbench.git'
V48_GH='/Users/matthew.zhao/.local/share/mise/shims/gh'

[[ "$(/usr/bin/git -C "$V48_PUBLISHER" remote get-url origin)" == \
  "$V48_FIXED_ORIGIN" ]] || exit 71
[[ -z "$(/usr/bin/git -C "$V48_PUBLISHER" status --porcelain=v1 \
  --untracked-files=all --ignore-submodules=all)" ]] || exit 71

"$V48_GH" auth switch --hostname github.com --user matthew-zhao
[[ "$("$V48_GH" api user --jq .login)" == matthew-zhao ]] || exit 71
[[ "$("$V48_GH" api repos/matthew-zhao/epiagentbench \
  --jq .permissions.push)" == true ]] || exit 71

if V48_HOOKS_PATH=$(/usr/bin/git -C "$V48_PUBLISHER" config \
  --get core.hooksPath 2>/dev/null); then
  exit 71
else
  [[ $? -eq 1 ]] || exit 71
fi
[[ -z "$V48_HOOKS_PATH" ]] || exit 71
[[ "$(/usr/bin/shasum -a 256 "$V48_PUBLISHER/.git/hooks/pre-commit" | \
  /usr/bin/awk '{print $1}')" == \
  4d4892f5df8d68688d564b08a9b7ab990ee1af49f85250e94bb9e088f23c5728 ]] || exit 71
[[ "$(/usr/bin/shasum -a 256 "$V48_PUBLISHER/.git/hooks/post-checkout" | \
  /usr/bin/awk '{print $1}')" == \
  9bc3e13271e9bbbebdcb4543cc051e869f10c7a8219e1bff807595e52b345afc ]] || exit 71

V48_REMOTE_RECORDS=$(/usr/bin/env -i HOME=/var/empty LC_ALL=C \
  PATH=/usr/bin:/bin:/usr/sbin:/sbin \
  GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null \
  GIT_TERMINAL_PROMPT=0 \
  /usr/bin/git ls-remote --refs "$V48_FIXED_ORIGIN" \
  "$V48_DESTINATION_REF")
if [[ "$V48_EXPECTED_REMOTE_TIP" == absent ]]; then
  [[ -z "$V48_REMOTE_RECORDS" ]] || exit 71
else
  [[ ${#V48_EXPECTED_REMOTE_TIP} -eq 40 ]] || exit 71
  [[ "$V48_EXPECTED_REMOTE_TIP" != *[!0-9a-f]* ]] || exit 71
  [[ "$V48_REMOTE_RECORDS" == \
    "${V48_EXPECTED_REMOTE_TIP}"$'\t'"${V48_DESTINATION_REF}" ]] || exit 71
fi
printf '%s\n' 'v48_prepublication_gate=passed'
# V48_PREPUBLICATION_GATE_END
```

The gate may expose only the selected account name, boolean permission, fixed
origin, hook digests, destination-ref presence, and its finite pass/fail state.
It must never print a token, credential-helper response, OAuth state, or other
secret. Any command failure, unexpected output, nonempty first-use ref, moving
staged predecessor, dirty publisher, hook mismatch, origin mismatch, or
ambiguous credential route fails closed before `but push` and forbids that
publication attempt until a separate terminal-path decision is authorized.

If that one control-plane push fails, returns ambiguously, or cannot be
independently pinned as a unique exact fixed-origin record, V48 is terminal and
the push is never retried. A separately authorized closeout may then use only
`refs/heads/codex/v48-control-plane-publication-terminal-closeout`, created in
a fresh standalone publisher rooted directly at
`31928645baff6182852c9c88a393b6fcaa6be557`. Its sole commit
may add only `results/development-matched-50x6-v48.superseded.json` and
`tests/test_v48_supersession.py`; it cannot contain this unpublished V48
control candidate or any source/doc/runtime/private artifact. Selecting that
control-publication closeout forbids every downstream V48 ref and ceremony.

That same staged public-receipt ref then advances through exactly three more
one-file commits: the canonical manifest, the sanitized authentication
receipt, and the closed passing-preflight receipt, in that order. Each commit
must be independently pinned from the fixed origin before the next phase, and
each fresh checkout must bind its exact commit: `prepare-worktree` at the
runtime receipt, `manifest-worktree` at the manifest, `execution-worktree` at
the authentication receipt, and `production-worktree` at the passing
preflight receipt. No commit may co-publish code, documentation, another
receipt, or a private artifact.

Any failed or ambiguous bootstrap, candidate generation or comparison,
provider-free verification, private preparation, spend authorization,
authentication ceremony/reconciliation, runtime/manifest/authentication-
receipt publication, remote pin, or fresh-checkout binding before the
authentication receipt is independently pinned is terminal. It must
not retry, repair, regenerate, republish, or advance the staged ref. Instead it
uses `refs/heads/codex/v48-runtime-publication-terminal-closeout`, whose sole
parent is the last commit already independently pinned from the fixed origin:
the V48 control commit when no staged receipt was published, otherwise the
latest successfully published one-file runtime, manifest, or authentication
receipt commit. A local branch, candidate, provisional object ID, publication
output, or failed-to-pin remote value is never a parent or pin. Safe incident
metadata may identify such a value only to prove that it is non-authoritative
and excluded from the selected closeout's tree and ancestry.

The early closeout adds only
`results/development-matched-50x6-v48.superseded.json` and
`tests/test_v48_supersession.py`. It never republishes an unpublished candidate
or receipt. The
record binds only the public predecessors that were independently pinned,
states which later artifacts are absent, and reports safe aggregate call/start
counts. It contains no code, documentation, private data, provider output,
prompt, observation, hidden identifier/family, credential/OAuth state, seed,
schedule, trace, or score.

Any terminal or ambiguous preflight outcome after the authentication receipt
is published and before a passing-preflight commit exists must not advance the
staged public-receipt ref. It uses
`refs/heads/codex/v48-preflight-terminal-closeout`, whose sole parent is the
independently pinned authentication-receipt commit. That closeout adds only
`results/development-matched-50x6-v48.superseded.json`,
`tests/test_v48_supersession.py`, and—only when the supervisor durably produced
it—the canonical trace-free closed preflight receipt at
`results/development-matched-50x6-v48.preflight.json`. The supersession record
must explicitly state whether that receipt exists and bind every earlier V48
public receipt.
Thus a failure before any preflight receipt has a two-file closeout; a failure
with an existing closed preflight receipt has a three-file closeout. Neither
scope may contain code, documentation, a production result, or private data.

Successful production publishes only the closed canonical result
`results/development-matched-50x6-v48.json` on
`refs/heads/codex/v48-production-results`, whose sole parent is the passing
preflight commit. A terminal production incident instead uses
`refs/heads/codex/v48-terminal-closeout` and may add only the trace-free
terminal result `results/development-matched-50x6-v48.json`,
`results/development-matched-50x6-v48.superseded.json`, and
`tests/test_v48_supersession.py`. The runtime-publication-terminal,
preflight-terminal, successful-production, and terminal-production paths are
mutually exclusive.
The exact selected remote commit is independently
pinned and checked out cleanly in `release-worktree` before final public release
validation.

Each commit pin is obtained independently from the fixed HTTPS origin, never
from a local branch name or a value copied from the publication command. The
already published V47 predecessor remains exactly
`refs/heads/codex/v48-v47-control-plane-publication-terminal-closeout` at
`31928645baff6182852c9c88a393b6fcaa6be557`. Every selected V48 publication
uses the exact post-publication binding below:

| Phase selection | Exact remote ref | Exact fresh checkout |
|---|---|---|
| `control` | `refs/heads/codex/v48-control-plane` | `/Users/matthew.zhao/.codex/epiagentbench-50x6-v48-runtime-worktree` |
| `runtime_receipt` | `refs/heads/codex/v48-runtime-preflight` | `/Users/matthew.zhao/.codex/epiagentbench-50x6-v48-prepare-worktree` |
| `manifest` | `refs/heads/codex/v48-runtime-preflight` | `/Users/matthew.zhao/.codex/epiagentbench-50x6-v48-manifest-worktree` |
| `authentication_receipt` | `refs/heads/codex/v48-runtime-preflight` | `/Users/matthew.zhao/.codex/epiagentbench-50x6-v48-execution-worktree` |
| `passing_preflight` | `refs/heads/codex/v48-runtime-preflight` | `/Users/matthew.zhao/.codex/epiagentbench-50x6-v48-production-worktree` |
| `control_publication_terminal_closeout` | `refs/heads/codex/v48-control-plane-publication-terminal-closeout` | `/Users/matthew.zhao/.codex/epiagentbench-50x6-v48-release-worktree` |
| `runtime_publication_terminal_closeout` | `refs/heads/codex/v48-runtime-publication-terminal-closeout` | `/Users/matthew.zhao/.codex/epiagentbench-50x6-v48-release-worktree` |
| `preflight_terminal_closeout` | `refs/heads/codex/v48-preflight-terminal-closeout` | `/Users/matthew.zhao/.codex/epiagentbench-50x6-v48-release-worktree` |
| `production_results` | `refs/heads/codex/v48-production-results` | `/Users/matthew.zhao/.codex/epiagentbench-50x6-v48-release-worktree` |
| `terminal_closeout` | `refs/heads/codex/v48-terminal-closeout` | `/Users/matthew.zhao/.codex/epiagentbench-50x6-v48-release-worktree` |

These five terminal or outcome paths are mutually exclusive:
`control_publication_terminal_closeout`,
`runtime_publication_terminal_closeout`, `preflight_terminal_closeout`,
`production_results`, and `terminal_closeout`. Once the control commit is
independently pinned, only the latter four remain selectable.

After the selected push returns and the separately authorized create-once
fresh checkout exists at the selected exact path, set only `V48_PIN_PHASE` to
that table row and run the gate. For the current control-plane phase it is
frozen to `control`; the case statement, rather than operator-supplied ref or
path values, selects its exact binding.

```sh
# V48_POSTPUBLICATION_PIN_GATE_BEGIN
set -euo pipefail
V48_PIN_PHASE=control
V48_FIXED_ORIGIN='https://github.com/matthew-zhao/epiagentbench.git'

case "$V48_PIN_PHASE" in
  control)
    V48_PIN_REF='refs/heads/codex/v48-control-plane'
    V48_PIN_CHECKOUT='/Users/matthew.zhao/.codex/epiagentbench-50x6-v48-runtime-worktree'
    ;;
  runtime_receipt)
    V48_PIN_REF='refs/heads/codex/v48-runtime-preflight'
    V48_PIN_CHECKOUT='/Users/matthew.zhao/.codex/epiagentbench-50x6-v48-prepare-worktree'
    ;;
  manifest)
    V48_PIN_REF='refs/heads/codex/v48-runtime-preflight'
    V48_PIN_CHECKOUT='/Users/matthew.zhao/.codex/epiagentbench-50x6-v48-manifest-worktree'
    ;;
  authentication_receipt)
    V48_PIN_REF='refs/heads/codex/v48-runtime-preflight'
    V48_PIN_CHECKOUT='/Users/matthew.zhao/.codex/epiagentbench-50x6-v48-execution-worktree'
    ;;
  passing_preflight)
    V48_PIN_REF='refs/heads/codex/v48-runtime-preflight'
    V48_PIN_CHECKOUT='/Users/matthew.zhao/.codex/epiagentbench-50x6-v48-production-worktree'
    ;;
  control_publication_terminal_closeout)
    V48_PIN_REF='refs/heads/codex/v48-control-plane-publication-terminal-closeout'
    V48_PIN_CHECKOUT='/Users/matthew.zhao/.codex/epiagentbench-50x6-v48-release-worktree'
    ;;
  runtime_publication_terminal_closeout)
    V48_PIN_REF='refs/heads/codex/v48-runtime-publication-terminal-closeout'
    V48_PIN_CHECKOUT='/Users/matthew.zhao/.codex/epiagentbench-50x6-v48-release-worktree'
    ;;
  preflight_terminal_closeout)
    V48_PIN_REF='refs/heads/codex/v48-preflight-terminal-closeout'
    V48_PIN_CHECKOUT='/Users/matthew.zhao/.codex/epiagentbench-50x6-v48-release-worktree'
    ;;
  production_results)
    V48_PIN_REF='refs/heads/codex/v48-production-results'
    V48_PIN_CHECKOUT='/Users/matthew.zhao/.codex/epiagentbench-50x6-v48-release-worktree'
    ;;
  terminal_closeout)
    V48_PIN_REF='refs/heads/codex/v48-terminal-closeout'
    V48_PIN_CHECKOUT='/Users/matthew.zhao/.codex/epiagentbench-50x6-v48-release-worktree'
    ;;
  *)
    exit 72
    ;;
esac

v48_read_pin() {
  /usr/bin/env -i HOME=/var/empty LC_ALL=C \
    PATH=/usr/bin:/bin:/usr/sbin:/sbin \
    GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null \
    GIT_TERMINAL_PROMPT=0 \
    /usr/bin/git ls-remote --refs --exit-code \
    "$V48_FIXED_ORIGIN" "$V48_PIN_REF"
}

V48_PIN_RECORD_BEFORE=$(v48_read_pin) || exit 72
V48_PIN_SHA=${V48_PIN_RECORD_BEFORE%%$'\t'*}
[[ ${#V48_PIN_SHA} -eq 40 ]] || exit 72
[[ "$V48_PIN_SHA" != *[!0-9a-f]* ]] || exit 72
[[ "$V48_PIN_RECORD_BEFORE" == \
  "${V48_PIN_SHA}"$'\t'"${V48_PIN_REF}" ]] || exit 72

[[ "$(/usr/bin/git -C "$V48_PIN_CHECKOUT" rev-parse --show-toplevel)" == \
  "$V48_PIN_CHECKOUT" ]] || exit 72
[[ "$(/usr/bin/git -C "$V48_PIN_CHECKOUT" remote get-url --all origin)" == \
  "$V48_FIXED_ORIGIN" ]] || exit 72
[[ -z "$(/usr/bin/git -C "$V48_PIN_CHECKOUT" status --porcelain=v1 \
  --untracked-files=all --ignore-submodules=all)" ]] || exit 72
[[ "$(/usr/bin/git -C "$V48_PIN_CHECKOUT" \
  rev-parse --verify 'HEAD^{commit}')" == "$V48_PIN_SHA" ]] || exit 72

V48_PIN_RECORD_AFTER=$(v48_read_pin) || exit 72
[[ "$V48_PIN_RECORD_AFTER" == "$V48_PIN_RECORD_BEFORE" ]] || exit 72

printf '%s\n' 'v48_postpublication_pin_gate=passed'
printf 'v48_pinned_commit=%s\n' "$V48_PIN_SHA"
# V48_POSTPUBLICATION_PIN_GATE_END
```

The exact record comparison retains and rejects duplicate lines and admits
only one lowercase 40-hex object ID followed by one tab and the exact selected
ref. The checkout root, sole origin URL, tracked and untracked cleanliness,
and commit-valued `HEAD` must all match. The second independent query must be
byte-for-byte identical to the first, so a ref that moves during checkout
validation fails closed. An absent, duplicate, malformed, differently named,
or moving remote record, origin mismatch, dirty checkout, or `HEAD` mismatch
forbids continuation. Never infer, repair, or substitute a pin from a local
ref or publication output.

## Fresh namespaces

```text
/Users/matthew.zhao/Documents/Disease Surveillance/epiagentbench-v48-runtime-preflight-workspace
$HOME/.codex/epiagentbench-50x6-v48-runtime-worktree
$HOME/.codex/epiagentbench-50x6-v48-prepare-worktree
$HOME/.codex/epiagentbench-50x6-v48-manifest-worktree
$HOME/.codex/epiagentbench-50x6-v48-execution-worktree
$HOME/.codex/epiagentbench-50x6-v48-production-worktree
$HOME/.codex/epiagentbench-50x6-v48-release-worktree
$HOME/.codex/epiagentbench-v48-runtime-cache
$HOME/.codex/epiagentbench-v48-runtime-receipt-staging
$HOME/.codex/epiagentbench-v48-provider-free-home
$HOME/.codex/epiagentbench-v48-provider-free-tmp
$HOME/.codex/epiagentbench-v48-cohort
$HOME/.codex/epiagentbench-v48-secrets/panel-auth.key
$HOME/.codex/epiagentbench-v48-secrets/.development-matched-50x6-v48.cohort-freeze-claim.v1.json
$HOME/.codex/epiagentbench-v48-secrets/.development-matched-50x6-v48.cohort-freeze-completion.v1.json
$HOME/.codex/epiagentbench-v48-state/development-matched-50x6-v48.private.json
$HOME/.codex/epiagentbench-v48-credentials/claude
$HOME/.codex/epiagentbench-v48-credentials/codex
$HOME/.codex/epiagentbench-v48-supervisors/preflight
$HOME/.codex/epiagentbench-v48-supervisors/production
results/development-matched-50x6-v48.runtime.json
results/development-matched-50x6-v48.manifest.json
results/development-matched-50x6-v48.authentication.json
results/development-matched-50x6-v48.preflight.json
results/development-matched-50x6-v48.json
results/development-matched-50x6-v48.superseded.json
```

Every path must be absent before its create-once phase, while all V47 and
earlier paths remain untouched. Additional owner-only staging paths must
also carry `v48` and may not alias an earlier version.

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
  /Users/matthew.zhao/.codex/epiagentbench-v48-runtime-cache \
  /Users/matthew.zhao/.codex/epiagentbench-v48-runtime-cache/matplotlib \
  /Users/matthew.zhao/.codex/epiagentbench-v48-runtime-cache/numba \
  /Users/matthew.zhao/.codex/epiagentbench-v48-runtime-cache/xdg \
  /Users/matthew.zhao/.codex/epiagentbench-v48-runtime-receipt-staging \
  /Users/matthew.zhao/.codex/epiagentbench-v48-provider-free-home \
  /Users/matthew.zhao/.codex/epiagentbench-v48-provider-free-tmp
do
  if /bin/test -e "$path" || /bin/test -L "$path"; then
    exit 73
  fi
done
/bin/mkdir -m 0700 \
  /Users/matthew.zhao/.codex/epiagentbench-v48-runtime-cache
/bin/mkdir -m 0700 \
  /Users/matthew.zhao/.codex/epiagentbench-v48-runtime-cache/matplotlib \
  /Users/matthew.zhao/.codex/epiagentbench-v48-runtime-cache/numba \
  /Users/matthew.zhao/.codex/epiagentbench-v48-runtime-cache/xdg \
  /Users/matthew.zhao/.codex/epiagentbench-v48-runtime-receipt-staging \
  /Users/matthew.zhao/.codex/epiagentbench-v48-provider-free-home \
  /Users/matthew.zhao/.codex/epiagentbench-v48-provider-free-tmp
for path in \
  /Users/matthew.zhao/.codex/epiagentbench-v48-runtime-cache \
  /Users/matthew.zhao/.codex/epiagentbench-v48-runtime-cache/matplotlib \
  /Users/matthew.zhao/.codex/epiagentbench-v48-runtime-cache/numba \
  /Users/matthew.zhao/.codex/epiagentbench-v48-runtime-cache/xdg \
  /Users/matthew.zhao/.codex/epiagentbench-v48-runtime-receipt-staging \
  /Users/matthew.zhao/.codex/epiagentbench-v48-provider-free-home \
  /Users/matthew.zhao/.codex/epiagentbench-v48-provider-free-tmp
do
  /bin/test ! -L "$path"
  /bin/test "$(/usr/bin/stat -f %Lp "$path")" = 700
done
'
```

Any nonzero exit, interruption, ambiguity, partial creation, unexpected path,
or mode mismatch is a terminal V48 preparation incident. Preserve what was
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
HOME=/Users/matthew.zhao/.codex/epiagentbench-v48-provider-free-home
LC_ALL=C.UTF-8
LOGNAME=matthew.zhao
PATH=/usr/bin:/bin:/usr/sbin:/sbin
SHELL=/bin/zsh
TMPDIR=/Users/matthew.zhao/.codex/epiagentbench-v48-provider-free-tmp
USER=matthew.zhao
__CF_USER_TEXT_ENCODING=0x1F5:0x0:0x0
```

With `V48_CONTROL_COMMIT` independently pinned as described above, run these
two commands from
`/Users/matthew.zhao/.codex/epiagentbench-50x6-v48-runtime-worktree`.
They must each execute the fixed Starsim smoke, the 30-process startup smoke,
and one cache inventory, and must produce byte-identical candidates:

```sh
/usr/bin/env -i \
  HOME=/Users/matthew.zhao/.codex/epiagentbench-v48-provider-free-home \
  LC_ALL=C.UTF-8 LOGNAME=matthew.zhao \
  PATH=/usr/bin:/bin:/usr/sbin:/sbin SHELL=/bin/zsh \
  TMPDIR=/Users/matthew.zhao/.codex/epiagentbench-v48-provider-free-tmp \
  USER=matthew.zhao __CF_USER_TEXT_ENCODING=0x1F5:0x0:0x0 \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python \
  -I -S -B examples/run_development_matched_panel.py \
  preflight-preparation-runtime \
  --expected-benchmark-base-commit "$V48_CONTROL_COMMIT" \
  --runtime-cache-dir /Users/matthew.zhao/.codex/epiagentbench-v48-runtime-cache \
  --public-runtime-receipt /Users/matthew.zhao/.codex/epiagentbench-v48-runtime-receipt-staging/preflight-1.json

/usr/bin/env -i \
  HOME=/Users/matthew.zhao/.codex/epiagentbench-v48-provider-free-home \
  LC_ALL=C.UTF-8 LOGNAME=matthew.zhao \
  PATH=/usr/bin:/bin:/usr/sbin:/sbin SHELL=/bin/zsh \
  TMPDIR=/Users/matthew.zhao/.codex/epiagentbench-v48-provider-free-tmp \
  USER=matthew.zhao __CF_USER_TEXT_ENCODING=0x1F5:0x0:0x0 \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python \
  -I -S -B examples/run_development_matched_panel.py \
  preflight-preparation-runtime \
  --expected-benchmark-base-commit "$V48_CONTROL_COMMIT" \
  --runtime-cache-dir /Users/matthew.zhao/.codex/epiagentbench-v48-runtime-cache \
  --public-runtime-receipt /Users/matthew.zhao/.codex/epiagentbench-v48-runtime-receipt-staging/preflight-2.json

/usr/bin/cmp -s \
  /Users/matthew.zhao/.codex/epiagentbench-v48-runtime-receipt-staging/preflight-1.json \
  /Users/matthew.zhao/.codex/epiagentbench-v48-runtime-receipt-staging/preflight-2.json
```

The two generation commands are two precommitted independent attestations,
not retry slots. If candidate 1 fails or is ambiguous, do not run candidate 2.
If candidate 2 or the byte comparison fails or is ambiguous, do not generate
another candidate. Any interruption or nonzero exit is terminal for this V48
namespace; preserve the cache, staging, `HOME`, `TMPDIR`, and candidates
exactly as observed.

After both candidates independently prove zero authentication, provider, and
model starts, a later explicit authorization must create the fresh standalone
GitButler primary clone
`/Users/matthew.zhao/Documents/Disease Surveillance/epiagentbench-v48-runtime-preflight-workspace`
rooted exactly at the independently pinned V48 control commit. The path and
receipt destination must be absent before creation. Publish candidate 1 exactly
once into that bound primary checkout. This is an exact provider-free copy,
not a third generation:

```sh
/usr/bin/env -i \
  HOME=/Users/matthew.zhao/.codex/epiagentbench-v48-provider-free-home \
  LC_ALL=C.UTF-8 LOGNAME=matthew.zhao \
  PATH=/usr/bin:/bin:/usr/sbin:/sbin SHELL=/bin/zsh \
  TMPDIR=/Users/matthew.zhao/.codex/epiagentbench-v48-provider-free-tmp \
  USER=matthew.zhao __CF_USER_TEXT_ENCODING=0x1F5:0x0:0x0 \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python \
  -I -S -B examples/run_development_matched_panel.py \
  publish-provider-free-json \
  --source /Users/matthew.zhao/.codex/epiagentbench-v48-runtime-receipt-staging/preflight-1.json \
  --destination '/Users/matthew.zhao/Documents/Disease Surveillance/epiagentbench-v48-runtime-preflight-workspace/results/development-matched-50x6-v48.runtime.json'
```

Commit and publish only that receipt through GitButler, independently resolve
exactly one fixed-origin record for the runtime-receipt ref, and materialize
the fresh prepare checkout whose clean `HEAD` equals that remote object ID.
With `V48_RUNTIME_RECEIPT_COMMIT` set only from that independent pin, run this
exact single verification from
`/Users/matthew.zhao/.codex/epiagentbench-50x6-v48-prepare-worktree`:

```sh
/usr/bin/env -i \
  HOME=/Users/matthew.zhao/.codex/epiagentbench-v48-provider-free-home \
  LC_ALL=C.UTF-8 LOGNAME=matthew.zhao \
  PATH=/usr/bin:/bin:/usr/sbin:/sbin SHELL=/bin/zsh \
  TMPDIR=/Users/matthew.zhao/.codex/epiagentbench-v48-provider-free-tmp \
  USER=matthew.zhao __CF_USER_TEXT_ENCODING=0x1F5:0x0:0x0 \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python \
  -I -S -B examples/run_development_matched_panel.py \
  verify-preparation-runtime \
  --preparation-runtime-receipt /Users/matthew.zhao/.codex/epiagentbench-50x6-v48-prepare-worktree/results/development-matched-50x6-v48.runtime.json \
  --expected-benchmark-base-commit "$V48_RUNTIME_RECEIPT_COMMIT" \
  --runtime-cache-dir /Users/matthew.zhao/.codex/epiagentbench-v48-runtime-cache \
  --public-verification-receipt /Users/matthew.zhao/.codex/epiagentbench-v48-runtime-receipt-staging/verification.json
```

`verification.json` must be absent, including as a dangling symlink, before
this one invocation. Any mismatch, nonzero exit, interruption, ambiguity, or
partial verification receipt is terminal; do not rerun verification, repair
the cache, regenerate a candidate, replace the receipt, or reuse either the
retired or active checkout.

## Conservative budget ceiling

The source-owned V48 ceiling is not authorization. It is derived without
reading any private schedule:

- prior panels through V28: `$100`;
- V29 passing preflight: at most two Claude calls, `$10`;
- V29's first 26 production invocations: four complete six-profile blocks plus
  two positions, therefore at most ten Claude calls, `$50`;
- V30 supervisor-generation environment refusal: zero model calls, `$0`;
- V31 runtime-receipt publication failure before remote mutation: zero model
  calls, `$0`;
- V32 runtime-receipt publication failure before remote mutation: zero model
  calls, `$0`;
- V33 control-plane publication failure before remote mutation: zero model
  calls, `$0`;
- V34 provider-free pre-runtime host-contract validation failure: zero model
  calls, `$0`;
- V35 provider-free runtime-receipt publisher setup failure: zero model calls,
  `$0`;
- V40 control-plane authoring failure: zero model calls, `$0`;
- V46 control-plane precreation scientific-runtime cache-isolation failure:
  zero model calls, `$0`;
- V47 control-plane publication precreation scope-inventory failure: zero
  model calls, `$0`;
- conservative prior allowance: `$160`;
- unchanged V48 current-run ceiling: `$510`; and
- cumulative V48 Claude ceiling: `$670`.

Codex and Cursor spend remain explicitly unbounded. None of these values
authorize a provider call. A later operator must supply the exact text below
and seal it against the exact published V48 manifest and public
precommitment:

> I acknowledge the replacement six-call v48 preflight and 300-assignment production run, including unbounded Codex/Cursor provider spend and up to $670 total Claude spend across the failed v2 preflight, failed v5 preflight, failed v6 authentication bootstrap, failed v7 preflight, failed v8 production run, v9 preflight and failed production run, the abandoned zero-model-call v10 precommitment, the failed zero-model-call v11 authentication bootstrap, the abandoned zero-model-call v12 precommitment, the abandoned zero-model-call v13 precommitment, the failed v14 preflight, the failed zero-model-call v15 pre-claim preparation, the failed v16 preflight, the failed zero-model-call v17 pre-start runtime-cache-environment refusal, the failed v18 preflight, the failed zero-model-call v19 authentication setup, the failed zero-model-call v20 preflight, the failed zero-model-call v21 preflight, the failed zero-model-call v22 interrupted authentication ceremony, the failed v23 six-call preflight release validation, the abandoned zero-model-call v24 control-plane precommitment, the failed zero-model-call v25 provider-free preparation-runtime CLI discovery, the failed v26 preflight with indeterminate provider-call count and a conservative $10 Claude allowance, the failed zero-model-call v27 preflight, the failed zero-model-call v28 preflight, the v29 passing preflight and terminal production run with a conservative $60 Claude allowance, the failed zero-model-call v30 preflight supervisor-generation environment validation, the failed zero-model-call v31 provider-free runtime-receipt publication before remote mutation, the failed zero-model-call v32 provider-free runtime-receipt publication before remote mutation, the failed zero-model-call v33 control-plane publication before remote mutation, the failed zero-model-call v34 provider-free pre-runtime host-contract validation, the failed zero-model-call v35 provider-free runtime-receipt publisher setup, the failed zero-model-call v40 control-plane authoring, the failed zero-model-call v46 control-plane precreation scientific-runtime cache-isolation validation, the failed zero-model-call v47 control-plane publication precreation scope-inventory validation, and the v48 preflight and production run.

Its SHA-256 is
`2521ee29ff8baaef2bdab86477e13ed7a384784aba62a76e27b9edac30bdea0f`.

## Create-once sequence

1. Independently pin the exact two-file V47 control-publication terminal
   closeout at `31928645baff6182852c9c88a393b6fcaa6be557`. Preserve all eight
   inherited V35/V40/V46/V47 closeout files byte-identically and prove all
   unpublished predecessor objects remain absent from V48 ancestry.
2. Publish and independently pin a source/tests/docs-only V48 control-plane
   commit on `refs/heads/codex/v48-control-plane` as the direct child of the
   V47 closeout. It contains exactly the frozen 17-file delta and no V48
   result, runtime, credential, or private artifact.
3. In a clean checkout at that commit, produce the provider-free runtime
   receipt twice. Both canonical receipts must be byte-identical and prove
   zero authentication, provider, and model starts.
4. Publish only that existing receipt through GitButler on
   `refs/heads/codex/v48-runtime-preflight` and pin its exact commit.
5. From a fresh clean checkout at the receipt commit, re-attest the receipt and
   all five preparation operations. Only then may a later authorization create
   the V48 key, create-once freeze claim, cohort, private state, and manifest.
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
   commit on `refs/heads/codex/v48-preflight-terminal-closeout` with exactly the
   two- or three-file scope frozen above, then stops. Only a passing six-call
   preflight may be authenticated, committed alone as the next one-file commit
   on the staged ref, and independently matched to its closed public receipt.
   Create a fresh clean production checkout at that exact passing-preflight
   commit. Production uses a fresh supervisor namespace and one separately
   authorized start.
9. On successful completion, publish only the closed result on
   `refs/heads/codex/v48-production-results`. On a terminal incident, publish
   only the frozen trace-free terminal closeout scope on
   `refs/heads/codex/v48-terminal-closeout`. Independently pin the one selected
   ref and validate final release from a fresh clean release checkout.

## Exact supervisor environment and one-shot commands

Before either `generate`, the frozen V48 `TMPDIR` must still resolve to itself,
be a nonsymlink directory owned by the effective user with exact mode `0700`,
and occupy at most 72 UTF-8 bytes. Generation validates that condition before
reading the repository, authentication key, private state, manifest, or other
execution bindings. It exposes only the finite public failure code
`generation_environment_invalid`; any such refusal is terminal for that V48
namespace.

Every `generate`, `install`, `audit`, `status`, and `start` invocation below
uses the same exact clean environment. Do not substitute ambient shell state,
`/private/tmp`, a wrapper, or a different interpreter.

After the authentication-receipt commit is independently pinned and every
preflight gate is satisfied, execute each preflight command once and in this
order. `audit` and `status` are observations; their inclusion here does not
make a failed create-once boundary retryable.

```sh
/usr/bin/env -i HOME=/Users/matthew.zhao/.codex/epiagentbench-v48-provider-free-home LC_ALL=C.UTF-8 LOGNAME=matthew.zhao PATH=/usr/bin:/bin:/usr/sbin:/sbin SHELL=/bin/zsh TMPDIR=/Users/matthew.zhao/.codex/epiagentbench-v48-provider-free-tmp USER=matthew.zhao __CF_USER_TEXT_ENCODING=0x1F5:0x0:0x0 \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python -I -S -B \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v48-execution-worktree/examples/run_persistent_panel_supervisor.py generate \
  --operation preflight \
  --runtime-dir /Users/matthew.zhao/.codex/epiagentbench-v48-supervisors/preflight \
  --repository-root /Users/matthew.zhao/.codex/epiagentbench-50x6-v48-execution-worktree \
  --python-executable /Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python \
  --runtime-cache-dir /Users/matthew.zhao/.codex/epiagentbench-v48-runtime-cache \
  --authentication-key /Users/matthew.zhao/.codex/epiagentbench-v48-secrets/panel-auth.key \
  --claude-secure-storage-dir /Users/matthew.zhao/.codex/epiagentbench-v48-credentials/claude \
  --codex-secure-storage-dir /Users/matthew.zhao/.codex/epiagentbench-v48-credentials/codex \
  --private-state /Users/matthew.zhao/.codex/epiagentbench-v48-state/development-matched-50x6-v48.private.json \
  --public-manifest /Users/matthew.zhao/.codex/epiagentbench-50x6-v48-execution-worktree/results/development-matched-50x6-v48.manifest.json \
  --public-preflight /Users/matthew.zhao/.codex/epiagentbench-50x6-v48-execution-worktree/results/development-matched-50x6-v48.preflight.json \
  --cursor-keychain-service epiagentbench-cursor-v48 \
  --cursor-keychain-account matthew.zhao

/usr/bin/env -i HOME=/Users/matthew.zhao/.codex/epiagentbench-v48-provider-free-home LC_ALL=C.UTF-8 LOGNAME=matthew.zhao PATH=/usr/bin:/bin:/usr/sbin:/sbin SHELL=/bin/zsh TMPDIR=/Users/matthew.zhao/.codex/epiagentbench-v48-provider-free-tmp USER=matthew.zhao __CF_USER_TEXT_ENCODING=0x1F5:0x0:0x0 \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python -I -S -B \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v48-execution-worktree/examples/run_persistent_panel_supervisor.py install \
  --runtime-dir /Users/matthew.zhao/.codex/epiagentbench-v48-supervisors/preflight \
  --authentication-key /Users/matthew.zhao/.codex/epiagentbench-v48-secrets/panel-auth.key

/usr/bin/env -i HOME=/Users/matthew.zhao/.codex/epiagentbench-v48-provider-free-home LC_ALL=C.UTF-8 LOGNAME=matthew.zhao PATH=/usr/bin:/bin:/usr/sbin:/sbin SHELL=/bin/zsh TMPDIR=/Users/matthew.zhao/.codex/epiagentbench-v48-provider-free-tmp USER=matthew.zhao __CF_USER_TEXT_ENCODING=0x1F5:0x0:0x0 \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python -I -S -B \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v48-execution-worktree/examples/run_persistent_panel_supervisor.py audit \
  --runtime-dir /Users/matthew.zhao/.codex/epiagentbench-v48-supervisors/preflight \
  --authentication-key /Users/matthew.zhao/.codex/epiagentbench-v48-secrets/panel-auth.key

/usr/bin/env -i HOME=/Users/matthew.zhao/.codex/epiagentbench-v48-provider-free-home LC_ALL=C.UTF-8 LOGNAME=matthew.zhao PATH=/usr/bin:/bin:/usr/sbin:/sbin SHELL=/bin/zsh TMPDIR=/Users/matthew.zhao/.codex/epiagentbench-v48-provider-free-tmp USER=matthew.zhao __CF_USER_TEXT_ENCODING=0x1F5:0x0:0x0 \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python -I -S -B \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v48-execution-worktree/examples/run_persistent_panel_supervisor.py status \
  --runtime-dir /Users/matthew.zhao/.codex/epiagentbench-v48-supervisors/preflight \
  --authentication-key /Users/matthew.zhao/.codex/epiagentbench-v48-secrets/panel-auth.key

/usr/bin/env -i HOME=/Users/matthew.zhao/.codex/epiagentbench-v48-provider-free-home LC_ALL=C.UTF-8 LOGNAME=matthew.zhao PATH=/usr/bin:/bin:/usr/sbin:/sbin SHELL=/bin/zsh TMPDIR=/Users/matthew.zhao/.codex/epiagentbench-v48-provider-free-tmp USER=matthew.zhao __CF_USER_TEXT_ENCODING=0x1F5:0x0:0x0 \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python -I -S -B \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v48-execution-worktree/examples/run_persistent_panel_supervisor.py start \
  --runtime-dir /Users/matthew.zhao/.codex/epiagentbench-v48-supervisors/preflight \
  --authentication-key /Users/matthew.zhao/.codex/epiagentbench-v48-secrets/panel-auth.key
```

Only after all six profiles pass and both authenticated status and the closed
public preflight receipt independently validate that pass may production be
prepared. The production runtime must still be absent. Execute each production
command once and in this order:

```sh
/usr/bin/env -i HOME=/Users/matthew.zhao/.codex/epiagentbench-v48-provider-free-home LC_ALL=C.UTF-8 LOGNAME=matthew.zhao PATH=/usr/bin:/bin:/usr/sbin:/sbin SHELL=/bin/zsh TMPDIR=/Users/matthew.zhao/.codex/epiagentbench-v48-provider-free-tmp USER=matthew.zhao __CF_USER_TEXT_ENCODING=0x1F5:0x0:0x0 \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python -I -S -B \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v48-production-worktree/examples/run_persistent_panel_supervisor.py generate \
  --operation production \
  --runtime-dir /Users/matthew.zhao/.codex/epiagentbench-v48-supervisors/production \
  --repository-root /Users/matthew.zhao/.codex/epiagentbench-50x6-v48-production-worktree \
  --python-executable /Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python \
  --runtime-cache-dir /Users/matthew.zhao/.codex/epiagentbench-v48-runtime-cache \
  --authentication-key /Users/matthew.zhao/.codex/epiagentbench-v48-secrets/panel-auth.key \
  --claude-secure-storage-dir /Users/matthew.zhao/.codex/epiagentbench-v48-credentials/claude \
  --codex-secure-storage-dir /Users/matthew.zhao/.codex/epiagentbench-v48-credentials/codex \
  --private-state /Users/matthew.zhao/.codex/epiagentbench-v48-state/development-matched-50x6-v48.private.json \
  --public-manifest /Users/matthew.zhao/.codex/epiagentbench-50x6-v48-production-worktree/results/development-matched-50x6-v48.manifest.json \
  --public-results /Users/matthew.zhao/.codex/epiagentbench-50x6-v48-production-worktree/results/development-matched-50x6-v48.json \
  --cursor-keychain-service epiagentbench-cursor-v48 \
  --cursor-keychain-account matthew.zhao

/usr/bin/env -i HOME=/Users/matthew.zhao/.codex/epiagentbench-v48-provider-free-home LC_ALL=C.UTF-8 LOGNAME=matthew.zhao PATH=/usr/bin:/bin:/usr/sbin:/sbin SHELL=/bin/zsh TMPDIR=/Users/matthew.zhao/.codex/epiagentbench-v48-provider-free-tmp USER=matthew.zhao __CF_USER_TEXT_ENCODING=0x1F5:0x0:0x0 \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python -I -S -B \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v48-production-worktree/examples/run_persistent_panel_supervisor.py install \
  --runtime-dir /Users/matthew.zhao/.codex/epiagentbench-v48-supervisors/production \
  --authentication-key /Users/matthew.zhao/.codex/epiagentbench-v48-secrets/panel-auth.key

/usr/bin/env -i HOME=/Users/matthew.zhao/.codex/epiagentbench-v48-provider-free-home LC_ALL=C.UTF-8 LOGNAME=matthew.zhao PATH=/usr/bin:/bin:/usr/sbin:/sbin SHELL=/bin/zsh TMPDIR=/Users/matthew.zhao/.codex/epiagentbench-v48-provider-free-tmp USER=matthew.zhao __CF_USER_TEXT_ENCODING=0x1F5:0x0:0x0 \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python -I -S -B \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v48-production-worktree/examples/run_persistent_panel_supervisor.py audit \
  --runtime-dir /Users/matthew.zhao/.codex/epiagentbench-v48-supervisors/production \
  --authentication-key /Users/matthew.zhao/.codex/epiagentbench-v48-secrets/panel-auth.key

/usr/bin/env -i HOME=/Users/matthew.zhao/.codex/epiagentbench-v48-provider-free-home LC_ALL=C.UTF-8 LOGNAME=matthew.zhao PATH=/usr/bin:/bin:/usr/sbin:/sbin SHELL=/bin/zsh TMPDIR=/Users/matthew.zhao/.codex/epiagentbench-v48-provider-free-tmp USER=matthew.zhao __CF_USER_TEXT_ENCODING=0x1F5:0x0:0x0 \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python -I -S -B \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v48-production-worktree/examples/run_persistent_panel_supervisor.py status \
  --runtime-dir /Users/matthew.zhao/.codex/epiagentbench-v48-supervisors/production \
  --authentication-key /Users/matthew.zhao/.codex/epiagentbench-v48-secrets/panel-auth.key

/usr/bin/env -i HOME=/Users/matthew.zhao/.codex/epiagentbench-v48-provider-free-home LC_ALL=C.UTF-8 LOGNAME=matthew.zhao PATH=/usr/bin:/bin:/usr/sbin:/sbin SHELL=/bin/zsh TMPDIR=/Users/matthew.zhao/.codex/epiagentbench-v48-provider-free-tmp USER=matthew.zhao __CF_USER_TEXT_ENCODING=0x1F5:0x0:0x0 \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v5-venv/bin/python -I -S -B \
  /Users/matthew.zhao/.codex/epiagentbench-50x6-v48-production-worktree/examples/run_persistent_panel_supervisor.py start \
  --runtime-dir /Users/matthew.zhao/.codex/epiagentbench-v48-supervisors/production \
  --authentication-key /Users/matthew.zhao/.codex/epiagentbench-v48-secrets/panel-auth.key
```

At every step above, the destination ref/path must be absent before first use,
the operation is attempted at most once, and the new commit is independently
pinned before a descendant phase begins. Any failed or ambiguous boundary
selects exactly one terminal ref under the parent rules above; it never permits
retry. No step may be inferred from a placeholder. No runtime generation, provider
call, or private write is authorized by this document.

## Terminal rules

- Never restart, resume, or mutate V47 or any earlier version.
- Never reuse a V47 or earlier key, cohort, cache, credential, state, checkout,
  supervisor, Keychain service, claim, or output destination.
- Never fill a commit placeholder from local or provisional state.
- Never launch from an ambient interpreter or PATH-selected provider binary.
- Never start either V48 supervisor twice.
- Never retry or repair the provider-free bootstrap, either receipt candidate,
  publication, or verification after any failed, interrupted, or ambiguous
  boundary.
- Never publish or inspect protected provider or benchmark data before the
  frozen final-release gates permit it.
