# V32 control-plane design

This document describes pre-freeze V32 engineering work. It is not a spend
authorization, runtime receipt, panel manifest, authentication receipt, or
permission to create private state or invoke a provider.

## Incident carried forward from V31

V31 completed its provider-free bootstrap and generated two byte-identical
runtime-receipt candidates. Authentication, provider, and model starts all
remained zero. Its single authorized GitButler publication attempt then failed
because publication credentials were unavailable, before any remote mutation.
The fixed origin retained `refs/heads/codex/v31-control-plane` at
`6efe0fa93e9c72946b48c22ab27a7fe6b41c199c` and never acquired
`refs/heads/codex/v31-runtime-preflight`. No runtime receipt became public; no
manifest, private cohort, authentication, preflight, supervisor, production
assignment, result, trace, or score followed.

V31 closes on
`refs/heads/codex/v31-runtime-publication-terminal-closeout`, whose sole parent
is the independently pinned control commit above and whose exact delta is only
[`development-matched-50x6-v31.superseded.json`](../results/development-matched-50x6-v31.superseded.json)
and `tests/test_v31_supersession.py`. The closeout must not contain or carry
the local candidate bytes or V31 runtime-receipt bytes. It may identify the
unpublished local commit only as non-authoritative incident metadata, while the
object and receipt remain excluded from its tree and ancestry.
V32 must begin as a direct child of the independently pinned closeout, preserve
all terminal evidence unchanged, and use fresh panel, cohort, credential,
private-state, cache, checkout, supervisor, socket, temporary-directory, and
output namespaces.

## Retained process-identity guarantees

V32 retains the three authoritative supervisor-identity components introduced
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
path, or other private input—and before creating the runtime directory—V32
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

The V32 source-level cut explicitly rejects the V31 panel contract. It
advances:

- panel persistent-supervisor contract `v16` to `v17`;
- panel ID from `development-matched-50x6-v31` to
  `development-matched-50x6-v32`;
- top-level schema from `development_matched_panel_v31` to
  `development_matched_panel_v32`; and
- every panel/cohort-specific freeze and private/execution namespace from V31
  to V32.

Persistent-supervisor state remains `v4`, record/event/execution-context
domains remain `v4`, the identity domain remains `v3`, the protocol remains
`v9`, and LaunchAgent config/auth remains `v16`. Those retained wire schemas are
not falsely advanced merely to create a new panel namespace.

The panel, LaunchAgent, tests, and V32 runbook carry the V32-specific values
together. Historical V31 artifacts and its supersession record remain
unchanged. Earlier runbooks remain historical records; the V31 runbook gains
only an explicit terminal banner and forward pointer to V32. This source cut is
still not a runtime receipt, manifest, or execution authorization.

V31 adds zero to the conservative accounting. V32 therefore retains the
`$510` current-run Claude ceiling, the `$160` prior-through-V31 allowance, and
the `$670` cumulative Claude ceiling. Codex and Cursor remain explicitly
unbounded. These values describe a source-owned ceiling and authorize nothing.

The fresh V32 smoke names are `v32-stop-direct-care` and
`v32_contact_transmission_with_matched_contact_stop`. Because that identity is
part of the hashed projection, the reviewed golden digest advances to
`sha256:3f7c7e4975e9da2e75535672fdf8c4639405cb930d1b160845012694eb6cce8a`.

## Gates before any V32 provider call

- Publish only the existing V31 supersession record and its public contract
  test in `refs/heads/codex/v31-runtime-publication-terminal-closeout`, whose
  sole parent is V31 control commit
  `6efe0fa93e9c72946b48c22ab27a7fe6b41c199c`. Its exact two-file scope excludes
  the V31 runtime receipt and excludes all local/provisional objects from the
  closeout tree and ancestry. Independently
  resolve and pin the closeout before any V32 publication.
- Publish and pin the reviewed, source/docs/tests-only V32 control-plane commit
  as the direct child of that closeout.
- Generate the deterministic provider-free runtime receipt twice identically,
  publish it alone, and independently pin it.
- Freeze a new manifest and private state in fresh namespaces.
- Explicitly supply the exact `$670` cumulative spend acknowledgement from the
  V32 runbook, including V30's zero-model-call terminal generation refusal and
  V31's zero-model-call publication failure before remote mutation; its exact
  SHA-256 is
  `05f6b8f83d7101c8d05b4348256dfffd10946d2909fa3e919c6e6134030d03cb`.
  The reviewed source text and ceiling are not authorization.
- Complete zero-model-call authentication and the six-call preflight.
- Independently validate and pin the passing preflight receipt before creating
  a production checkout.
- Require separate authorization before the 300-assignment production start.

No V32 runtime, private state, authentication, preflight, or production action
is part of this control-plane patch.

## Closed publication topology

V32 uses `refs/heads/codex/v32-runtime-preflight` for exactly four one-file
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
`refs/heads/codex/v32-runtime-publication-terminal-closeout`. Its sole parent is
the last independently pinned public commit: control when no receipt was
published, otherwise the latest pinned staged receipt. It adds only the V32
supersession record and `tests/test_v32_supersession.py`; an unpublished
candidate is never republished through a closeout.

After a published authentication receipt, a terminal preflight uses
`refs/heads/codex/v32-preflight-terminal-closeout`. A passing preflight permits
exactly one later outcome: success on `refs/heads/codex/v32-production-results`
or terminal production on `refs/heads/codex/v32-terminal-closeout`. The early
terminal, preflight terminal, production success, and production terminal refs
are mutually exclusive. Every selected ref is absent before use, published at
most once, independently pinned, and never resumed or repaired.
