# V35 control-plane design

This document describes pre-freeze V35 engineering work. It is not a spend
authorization, runtime receipt, panel manifest, authentication receipt, or
permission to create private state or invoke a provider.

## V34 terminal predecessor

V32 and V33 remain terminal at their independently pinned closeouts
`f26d8f7e50748883142f3452ee11daf43595e421` and
`47ebbfc799310fc73e60e7cbf90cd37c5f9d6d8d`. Their unpublished candidate
objects remain non-authoritative and excluded from successor ancestry.

V34 published and independently pinned its source/docs/tests-only control
commit `72ca992eed6c0faa5961d4063732a8a1da918301`, with sole parent the V33
closeout and tree `8bf73a9753b1b0ea8d5dc2f7e230494a13fd0f47`. Before runtime-receipt
generation, provider-free host-contract validation found a coherent
root-managed Glean route and managed-settings schema evolution. It invoked no
helper and made zero authentication, provider, or model starts. It created no
runtime receipt, key, cohort, private state, manifest, authentication receipt,
supervisor, preflight, production assignment, result, trace, or score, and no
V34 spend acknowledgement was supplied.

V34 closes on
`refs/heads/codex/v34-runtime-publication-terminal-closeout` at
`038794aa1bf82440259c62afdabab44c01415978`, with sole parent the V34 control
commit and tree `fc562ee84d81d51e7186f9186d67bea0d329f39c`. It adds only
[`development-matched-50x6-v34.superseded.json`](../results/development-matched-50x6-v34.superseded.json)
and `tests/test_v34_supersession.py`, under supersession schema
`epiagentbench.panel_supersession.v27`. V35 begins only as its direct child,
preserves both closeout files byte-identically, and uses fresh panel, cohort,
credential, private-state, cache, checkout, supervisor, socket,
temporary-directory, and output namespaces.

## Retained process-identity guarantees

V35 retains the three authoritative supervisor-identity components introduced
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
path, or other private input—and before creating the runtime directory—V35
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

The V35 source-level cut explicitly rejects public V32, burned unpublished
V33, and terminal V34 identities. It advances:

- panel persistent-supervisor contract from
  `epiagentbench.persistent_supervisor_contract.v19` to
  `epiagentbench.persistent_supervisor_contract.v20`;
- panel ID from `development-matched-50x6-v34` to
  `development-matched-50x6-v35`;
- top-level schema from `development_matched_panel_v34` to
  `development_matched_panel_v35`;
- provider CLI contract from `epiagentbench.provider_cli_contract.v2` to
  `epiagentbench.provider_cli_contract.v3`; and
- every panel/cohort-specific freeze and private/execution namespace from V34
  to fresh V35 values.

Persistent-supervisor state remains `v4`, record/event/execution-context
domains remain `v4`, the identity domain remains `v3`, the protocol remains
`v9`, and LaunchAgent config/auth remains `v16`. Those retained wire schemas are
not falsely advanced merely to create a new panel namespace.

The panel, LaunchAgent, tests, and V35 runbook carry the V35-specific values
together. Historical V34 closeout artifacts remain byte-identical. Earlier
runbooks remain historical records; the V34 runbook gains only an explicit
terminal banner and forward pointer to V35. This source cut is still not a
runtime receipt, manifest, or execution authorization.

V34 adds zero to the conservative accounting. V35 therefore
retains the `$510` current-run Claude ceiling, the `$160` prior-through-V34 allowance, and
the `$670` cumulative Claude ceiling. Codex and Cursor remain explicitly
unbounded. These values describe a source-owned ceiling and authorize nothing.

The fresh V35 smoke names are `v35-stop-direct-care` and
`v35_contact_transmission_with_matched_contact_stop`. Because that identity is
part of the hashed projection, the reviewed golden digest must advance to the
independently reproduced duplicate-safe value
`sha256:864f1d51cc4da6a0545445537cca5badc5bb624ed4d8e386786a274e85b78086`.

## Root-managed Glean reconciliation

The installed root-managed bundle retains the same reviewed HTTPS host but
moves the exact gateway route from `/api/v1` to `/rest/api/v1`. V35 pins the
new full-URL digest
`sha256:b27f5a0a001afd9310d20c04af550e13c440f2d88ee0891b95c2f73f7186d305`
in source, requires the exact new path, retains the ban on userinfo, explicit
ports, query, fragment, and secret-bearing fields, and advances the public
allowlist identity to `approved_managed_gateway_v2`. The digest is a redacted
endpoint identity; the raw host and OAuth client identifiers are never placed
in source, docs, or a public receipt.

Claude managed settings retain the exact 17-key environment, pinned API-key
and telemetry helpers, derived Anthropic route, telemetry endpoint policy, and
personal-identifier redaction. Their top level now contains one additional
reviewed default-model field. V35 requires that field to be an exact string
equal to the approved `sonnet` alias, but publishes only
`approved_managed_claude_default_model_v1` and a redacted placeholder. The
managed default cannot select a benchmark profile: every Claude invocation
continues to pass its explicit source-owned `--model`, and the observed-model
and fallback receipt checks remain authoritative. This public semantic shape
change is why the provider CLI contract advances to v3.

## Gates before any V35 provider call

- Independently resolve and pin the exact V34 closeout above; preserve its two
  files byte-identically and prove unpublished predecessor objects are absent
  from V35 ancestry.
- Publish and pin the reviewed, source/docs/tests-only V35 control-plane commit
  as the direct child of `038794aa1bf82440259c62afdabab44c01415978`, using a fresh standalone GitButler primary
  clone, the safely validated personal `matthew-zhao` credential route, intact
  managed hooks, and exactly one named push.
- Generate the deterministic provider-free runtime receipt twice identically,
  publish it alone, and independently pin it.
- Freeze a new manifest and private state in fresh namespaces.
- Explicitly supply the exact `$670` cumulative spend acknowledgement from the
  V35 runbook, including V30's zero-model-call terminal generation refusal and
  V31's and V32's zero-model-call runtime-receipt publication failures, V33's
  zero-model-call control-plane publication failure before remote mutation,
  and V34's zero-model-call provider-free pre-runtime host-contract failure;
  its exact
  SHA-256 is
  `d4afd8238eeb000c25a124936400102d97e327d0624b1b5059c26b0de1fd8bc0`.
  The reviewed source text and ceiling are not authorization.
- Complete zero-model-call authentication and the six-call preflight.
- Independently validate and pin the passing preflight receipt before creating
  a production checkout.
- Require separate authorization before the 300-assignment production start.

No V35 runtime, private state, authentication, preflight, or production action
is part of this control-plane patch.

## Closed publication topology

V35 first attempts exactly one named publication of
`refs/heads/codex/v35-control-plane`. Failure, ambiguity, or a non-unique
fixed-origin pin is terminal and cannot be retried. That outcome closes only
on `refs/heads/codex/v35-control-plane-publication-terminal-closeout`, whose
sole parent is `038794aa1bf82440259c62afdabab44c01415978` and whose exact delta
is the V35 supersession record plus `tests/test_v35_supersession.py`. It cannot
carry the unpublished V35 candidate into tree or ancestry and is mutually
exclusive with every later V35 ref.

V35 uses `refs/heads/codex/v35-runtime-preflight` for exactly four one-file
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
`refs/heads/codex/v35-runtime-publication-terminal-closeout`. Its sole parent is
the last independently pinned public commit: control when no receipt was
published, otherwise the latest pinned staged receipt. It adds only the V35
supersession record and `tests/test_v35_supersession.py`; an unpublished
candidate is never republished through a closeout.

After a published authentication receipt, a terminal preflight uses
`refs/heads/codex/v35-preflight-terminal-closeout`. A passing preflight permits
exactly one later outcome: success on `refs/heads/codex/v35-production-results`
or terminal production on `refs/heads/codex/v35-terminal-closeout`. The early
terminal, preflight terminal, production success, and production terminal refs
are mutually exclusive. Every selected ref is absent before use, published at
most once, independently pinned, and never resumed or repaired.
