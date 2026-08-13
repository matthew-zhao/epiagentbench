# V48 control-plane design

This document describes pre-freeze V48 engineering work. It is not a spend
authorization, runtime receipt, panel manifest, authentication receipt, or
permission to create private state or invoke a provider.

## Closed V35–V47 predecessor chain

V35 published its control plane at
`818b0313eb14e3b31431b267626d8d4a61fa5559`, then stopped during its
provider-free runtime-receipt publisher setup. Its successor-owned closeout is
the two-file commit `6471dcd74393852740e64a6c7181d5c44d3d9a30` on
`refs/heads/codex/v40-v35-runtime-publication-terminal-closeout`, under
`epiagentbench.panel_supersession.v28`. V40 control-plane authoring then
stopped before publication and closes through the two-file commit
`ab2043215d034c06528100033b18de563d754d9c` on
`refs/heads/codex/v46-v40-control-plane-publication-terminal-closeout`, under
`epiagentbench.panel_supersession.v29`.

V46 stopped during provider-free control-plane-precreation scientific-runtime
cache-isolation validation. Its two-file closeout is
`e8946a10997863412d4a2ec0113b72e066a73550` on
`refs/heads/codex/v47-v46-control-plane-publication-terminal-closeout`, under
`epiagentbench.panel_supersession.v30`. V47 completed and sealed two local
control candidates but stopped at its publication precreation scope gate;
neither candidate was committed, published, or made reusable. Its two-file
closeout is `31928645baff6182852c9c88a393b6fcaa6be557`, with sole parent
`e8946a10997863412d4a2ec0113b72e066a73550`, tree
`e21dacbbfc859206a15c7dbbbb9feaf214ca78d5`, and ref
`refs/heads/codex/v48-v47-control-plane-publication-terminal-closeout`, under
`epiagentbench.panel_supersession.v31`.

The V35, V40, V46, and V47 supersession JSON/test pairs remain byte-identical
at their published hashes. V48 begins only as the direct child of
`31928645baff6182852c9c88a393b6fcaa6be557` and uses fresh panel, cohort,
credential, private-state, cache, checkout, supervisor, socket,
temporary-directory, and output namespaces. All unpublished predecessor
candidate bodies, values, and lifecycle namespaces are non-authoritative and
non-reusable.

The inherited supersession schemas are
`epiagentbench.panel_supersession.v28`,
`epiagentbench.panel_supersession.v29`,
`epiagentbench.panel_supersession.v30`, and
`epiagentbench.panel_supersession.v31`; V48 reserves
`epiagentbench.panel_supersession.v32`. The rejected predecessor panel schemas
are `development_matched_panel_v35`, `development_matched_panel_v40`,
`development_matched_panel_v46`, and `development_matched_panel_v47`, paired
with panel IDs `development-matched-50x6-v35`,
`development-matched-50x6-v40`, `development-matched-50x6-v46`, and
`development-matched-50x6-v47`. Persistent-supervisor contracts
`epiagentbench.persistent_supervisor_contract.v20`,
`epiagentbench.persistent_supervisor_contract.v21`,
`epiagentbench.persistent_supervisor_contract.v22`, and
`epiagentbench.persistent_supervisor_contract.v23` are rejected; v21, v22, and
v23 are non-reusable.

## Retained process-identity guarantees

V48 retains the three authoritative supervisor-identity components introduced
for V30:

1. Linux boot identity remains `/proc/sys/kernel/random/boot_id`.
2. Darwin boot identity is the validated, lowercase value of
   `kern.bootsessionuuid`, domain-separated as
   `darwin-bootsessionuuid-v1` before hashing.
3. Darwin process birth is read from numeric `proc_pidinfo` /
   `PROC_PIDTBSDINFO` fields and domain-separated as
   `darwin-proc-pidtbsdinfo-v1` before hashing.

Formatted `kern.boottime` and `ps lstart` output are forbidden identity
sources. Synthetic wall-minus-monotonic and monotonic-nanosecond fallbacks are
also forbidden. If an authoritative identity is unavailable at construction,
the supervisor fails before writing status, lease, or event state and before
starting the evaluator. Live unavailability remains a fail-closed process
diagnostic.

Live attestation reports a specific process-identity or heartbeat failure
before the generic `core_unhealthy` classification.

## Generation-environment correction

Before reading an authentication key, private state, manifest-bound credential
path, or other private input—and before creating the runtime directory—V48
LaunchAgent generation validates the inputs used to construct its closed base
environment. `PATH` is fixed to the source-owned system path. `TMPDIR` must
resolve to a current-user-owned, nonsymlink directory with exact mode `0700` and
must remain within the source-owned 72-byte UTF-8 socket-path limit. No shared
global temporary directory is accepted or used as a fallback.

An invalid generation environment produces only the finite public failure code
`generation_environment_invalid`. It cannot expose the offending path,
arbitrary exception text, credentials, private state, or provider data, and it
must leave the runtime parent unchanged. After the manifest-bound cache
environment is derived, generation revalidates the complete sealed environment
before constructing the config.

## Frozen source-level version cut

The V48 source-level cut explicitly rejects every V35, V40, V46, and V47
panel-specific identity and the non-reusable persistent-supervisor contract
values v21, v22, and v23. It advances:

- panel persistent-supervisor contract to
  `epiagentbench.persistent_supervisor_contract.v24`, while rejecting
  predecessor V35 v20 and non-reusable v21, v22, and v23;
- panel ID from `development-matched-50x6-v47` to
  `development-matched-50x6-v48`;
- top-level schema from `development_matched_panel_v47` to
  `development_matched_panel_v48`;
- provider CLI contract remains `epiagentbench.provider_cli_contract.v3`; and
- every panel/cohort-specific freeze and private/execution namespace from V47
  to fresh V48 values.

Persistent-supervisor state remains `v4`, record/event/execution-context
domains remain `v4`, the identity domain remains `v3`, the protocol remains
`v9`, and LaunchAgent config/auth remains `v16`. Those retained wire schemas are
not falsely advanced merely to create a new panel namespace.

The panel, LaunchAgent, tests, and V48 runbook carry the V48-specific values
together. Historical V35, V40, V46, and V47 closeout artifacts remain
byte-identical. Earlier runbooks remain historical records; the V35 runbook
gains an explicit terminal banner and forward pointer to V48. This source cut
is still not a runtime receipt, manifest, or execution authorization.

V35, V40, V46, and V47 each add zero to the conservative accounting. V48
therefore retains the `$510` current-run Claude ceiling, the `$160` prior
allowance, and the `$670` cumulative Claude ceiling. Codex and Cursor remain
explicitly unbounded. These values describe a source-owned ceiling and
authorize nothing.

The fresh V48 smoke names are `v48-stop-direct-care` and
`v48_contact_transmission_with_matched_contact_stop`. Because that identity is
part of the hashed projection, the reviewed golden digest must advance to the
independently reproduced duplicate-safe value
`sha256:e91a8e76e32048c3bbc63c02ee2a1279fc53a6af078130a7d3baaa91ac8a3d5f`,
frozen after four independent cache-isolated discoveries and two ordinary
final smokes reproduced the same exact value and safe aggregates.

## Retained root-managed Glean contract

Published V35 reconciled the installed root-managed bundle. V48 retains its
reviewed HTTPS host, exact gateway route `/rest/api/v1`, and full-URL digest
`sha256:b27f5a0a001afd9310d20c04af550e13c440f2d88ee0891b95c2f73f7186d305`
unchanged. It requires that exact path, retains the ban on userinfo, explicit
ports, query, fragment, and secret-bearing fields, and retains the public
allowlist identity `approved_managed_gateway_v2`. The digest is a redacted
endpoint identity; the raw host and OAuth client identifiers are never placed
in source, docs, or a public receipt.

Claude managed settings retain the exact 17-key environment, pinned API-key
and telemetry helpers, derived Anthropic route, telemetry endpoint policy, and
personal-identifier redaction. Their top level now contains one additional
reviewed default-model field. V48 requires that field to be an exact string
equal to the approved `sonnet` alias, but publishes only
`approved_managed_claude_default_model_v1` and a redacted placeholder. The
managed default cannot select a benchmark profile: every Claude invocation
continues to pass its explicit source-owned `--model`, and the observed-model
and fallback receipt checks remain authoritative. V35 advanced the provider
CLI contract for this semantic shape; V48 retains
`epiagentbench.provider_cli_contract.v3` unchanged.

## Gates before any V48 provider call

- Independently resolve and pin the exact V47 closeout above; preserve all four
  inherited closeout pairs byte-identically and prove unpublished predecessor
  objects are absent from V48 ancestry.
- Publish and pin the reviewed, source/docs/tests-only V48 control-plane commit
  as the direct child of `31928645baff6182852c9c88a393b6fcaa6be557`, using a fresh standalone GitButler primary
  clone, the safely validated personal `matthew-zhao` credential route, intact
  managed hooks, and exactly one named push.
- Generate the deterministic provider-free runtime receipt twice identically,
  publish it alone, and independently pin it.
- Freeze a new manifest and private state in fresh namespaces.
- Explicitly supply the exact `$670` cumulative spend acknowledgement from the
  V48 runbook, including V30's zero-model-call terminal generation refusal and
  V31's and V32's zero-model-call runtime-receipt publication failures, V33's
  zero-model-call control-plane publication failure before remote mutation,
  V34's zero-model-call provider-free pre-runtime host-contract failure, V35's
  zero-model-call provider-free runtime-receipt publisher setup failure, V40's
  zero-model-call control-plane authoring failure, V46's zero-model-call
  control-plane precreation scientific-runtime cache-isolation validation
  failure, and V47's zero-model-call control-plane publication precreation
  scope-inventory validation failure;
  its exact
  SHA-256 is
  `2521ee29ff8baaef2bdab86477e13ed7a384784aba62a76e27b9edac30bdea0f`.
  The reviewed source text and ceiling are not authorization.
- Complete zero-model-call authentication and the six-call preflight.
- Independently validate and pin the passing preflight receipt before creating
  a production checkout.
- Require separate authorization before the 300-assignment production start.

No V48 runtime, private state, authentication, preflight, or production action
is part of this control-plane patch.

## Closed publication topology

V48 first attempts exactly one named publication of
`refs/heads/codex/v48-control-plane`. Failure, ambiguity, or a non-unique
fixed-origin pin is terminal and cannot be retried. That outcome closes only
on `refs/heads/codex/v48-control-plane-publication-terminal-closeout`, whose
sole parent is `31928645baff6182852c9c88a393b6fcaa6be557` and whose exact delta
is the V48 supersession record plus `tests/test_v48_supersession.py`. It cannot
carry the unpublished V48 candidate into tree or ancestry and is mutually
exclusive with every later V48 ref.

V48 uses `refs/heads/codex/v48-runtime-preflight` for exactly four one-file
commits in order: runtime receipt, manifest, sanitized authentication receipt,
and passing preflight receipt. Each destination is absent before first use,
each operation is attempted at most once, and each commit is independently
pinned from the fixed origin before the next phase. No local branch,
provisional object ID, publication output, or failed-to-pin remote value can
satisfy a pin.

Any failure or ambiguity through provider-free verification, private
preparation, spend authorization, authentication, runtime/manifest/
authentication-receipt publication, pinning, or checkout binding before the
authentication receipt is independently pinned closes only on
`refs/heads/codex/v48-runtime-publication-terminal-closeout`. Its sole parent is
the last independently pinned public commit: control when no receipt was
published, otherwise the latest pinned staged receipt. It adds only the V48
supersession record and `tests/test_v48_supersession.py`; an unpublished
candidate is never republished through a closeout.

After a published authentication receipt, a terminal preflight uses
`refs/heads/codex/v48-preflight-terminal-closeout`. A passing preflight permits
exactly one later outcome: success on `refs/heads/codex/v48-production-results`
or terminal production on `refs/heads/codex/v48-terminal-closeout`. The early
terminal, preflight terminal, production success, and production terminal refs
are mutually exclusive. Every selected ref is absent before use, published at
most once, independently pinned, and never resumed or repaired.
