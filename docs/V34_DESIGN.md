# V34 control-plane design

This document describes pre-freeze V34 engineering work. It is not a spend
authorization, runtime receipt, panel manifest, authentication receipt, or
permission to create private state or invoke a provider.

## Incidents carried forward from V32 and V33

V32 completed its provider-free runtime-receipt ceremony with zero
authentication, provider, or model starts. Its single authorized receipt
publication attempt failed before any remote mutation. Its terminal public
closeout is `f26d8f7e50748883142f3452ee11daf43595e421`, the sole child of
published V32 control commit `c6cd10e795944e08e76a6de249689d1a5538099b`.
The closeout adds only
[`development-matched-50x6-v32.superseded.json`](../results/development-matched-50x6-v32.superseded.json)
and `tests/test_v32_supersession.py`. It excludes the unpublished V32 runtime
receipt and local commit from its tree and ancestry.

V33 then performed only a source/docs/tests control-plane preparation. Its one
authorized GitButler publication attempt failed before any remote mutation
because the personal credential route was not selected. It created no runtime
receipt, key, cohort, private state, manifest, authentication receipt,
supervisor, preflight, production assignment, result, provider start, or model
call. The unpublished control commit
`dac82434f2e2a73d511df418755b28003222ab3b` is non-authoritative incident
metadata and must never be imported, cherry-picked, copied, patched, or used as
a parent or pin.

V33 closes on
`refs/heads/codex/v33-control-plane-publication-terminal-closeout` at
`47ebbfc799310fc73e60e7cbf90cd37c5f9d6d8d`, whose sole parent is the V32
closeout and whose exact delta is only
[`development-matched-50x6-v33.superseded.json`](../results/development-matched-50x6-v33.superseded.json)
and `tests/test_v33_supersession.py`. V34 begins only as its direct child,
preserves both two-file closeouts unchanged, and uses fresh panel, cohort,
credential, private-state, cache, checkout, supervisor, socket,
temporary-directory, and output namespaces.

## Retained process-identity guarantees

V34 retains the three authoritative supervisor-identity components introduced
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
path, or other private input—and before creating the runtime directory—V34
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

The V34 source-level cut explicitly rejects both the public V32 contract and
the burned unpublished V33 contract. It
advances:

- panel persistent-supervisor contract
  `epiagentbench.persistent_supervisor_contract.v17` directly to
  `epiagentbench.persistent_supervisor_contract.v19`, skipping burned V33
  value `epiagentbench.persistent_supervisor_contract.v18`;
- panel ID from `development-matched-50x6-v32` to
  `development-matched-50x6-v34`;
- top-level schema from `development_matched_panel_v32` to
  `development_matched_panel_v34`; and
- the burned unpublished V33 panel/schema pair
  `development-matched-50x6-v33` / `development_matched_panel_v33`, plus every
  panel/cohort-specific freeze and private/execution namespace from V32 and
  V33, to fresh V34 values.

Persistent-supervisor state remains `v4`, record/event/execution-context
domains remain `v4`, the identity domain remains `v3`, the protocol remains
`v9`, and LaunchAgent config/auth remains `v16`. Those retained wire schemas are
not falsely advanced merely to create a new panel namespace.

The panel, LaunchAgent, tests, and V34 runbook carry the V34-specific values
together. Historical V32 and V33 closeout artifacts remain byte-identical.
Earlier runbooks remain historical records; the V32 runbook gains only an
explicit terminal banner and forward pointer to V34. This source cut is still
not a runtime receipt, manifest, or execution authorization.

V32 and V33 each add zero to the conservative accounting. V34 therefore
retains the `$510` current-run Claude ceiling, the `$160` prior-through-V33 allowance, and
the `$670` cumulative Claude ceiling. Codex and Cursor remain explicitly
unbounded. These values describe a source-owned ceiling and authorize nothing.

The fresh V34 smoke names are `v34-stop-direct-care` and
`v34_contact_transmission_with_matched_contact_stop`. Because that identity is
part of the hashed projection, the reviewed golden digest advances to
`sha256:a89e9c69a08c87beee6e2e953453335ed8ddda83d407bf2dc050766f8ce73a68`.

## Gates before any V34 provider call

- Independently resolve and pin the exact V32 and V33 closeouts above; preserve
  their four files byte-identically and prove the unpublished V32 runtime
  object and V33 control object are absent from V34 ancestry.
- Publish and pin the reviewed, source/docs/tests-only V34 control-plane commit
  as the direct child of `47ebbfc799310fc73e60e7cbf90cd37c5f9d6d8d`, using a fresh standalone GitButler primary
  clone, the safely validated personal `matthew-zhao` credential route, intact
  managed hooks, and exactly one named push.
- Generate the deterministic provider-free runtime receipt twice identically,
  publish it alone, and independently pin it.
- Freeze a new manifest and private state in fresh namespaces.
- Explicitly supply the exact `$670` cumulative spend acknowledgement from the
  V34 runbook, including V30's zero-model-call terminal generation refusal and
  V31's zero-model-call publication failure, V32's zero-model-call
  runtime-receipt publication failure, and V33's zero-model-call control-plane
  publication failure before remote mutation; its exact
  SHA-256 is
  `b5026b6c3cdd3a2f6ca7f408f93bcb9a72236b305b57254811315067e4d6b97a`.
  The reviewed source text and ceiling are not authorization.
- Complete zero-model-call authentication and the six-call preflight.
- Independently validate and pin the passing preflight receipt before creating
  a production checkout.
- Require separate authorization before the 300-assignment production start.

No V34 runtime, private state, authentication, preflight, or production action
is part of this control-plane patch.

## Closed publication topology

V34 first attempts exactly one named publication of
`refs/heads/codex/v34-control-plane`. Failure, ambiguity, or a non-unique
fixed-origin pin is terminal and cannot be retried. That outcome closes only
on `refs/heads/codex/v34-control-plane-publication-terminal-closeout`, whose
sole parent is `47ebbfc799310fc73e60e7cbf90cd37c5f9d6d8d` and whose exact delta
is the V34 supersession record plus `tests/test_v34_supersession.py`. It cannot
carry the unpublished V34 candidate into tree or ancestry and is mutually
exclusive with every later V34 ref.

V34 uses `refs/heads/codex/v34-runtime-preflight` for exactly four one-file
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
`refs/heads/codex/v34-runtime-publication-terminal-closeout`. Its sole parent is
the last independently pinned public commit: control when no receipt was
published, otherwise the latest pinned staged receipt. It adds only the V34
supersession record and `tests/test_v34_supersession.py`; an unpublished
candidate is never republished through a closeout.

After a published authentication receipt, a terminal preflight uses
`refs/heads/codex/v34-preflight-terminal-closeout`. A passing preflight permits
exactly one later outcome: success on `refs/heads/codex/v34-production-results`
or terminal production on `refs/heads/codex/v34-terminal-closeout`. The early
terminal, preflight terminal, production success, and production terminal refs
are mutually exclusive. Every selected ref is absent before use, published at
most once, independently pinned, and never resumed or repaired.
