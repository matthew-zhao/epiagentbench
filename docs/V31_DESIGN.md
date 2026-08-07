# V31 control-plane design

This document describes pre-freeze V31 engineering work. It is not a spend
authorization, runtime receipt, panel manifest, authentication receipt, or
permission to create private state or invoke a provider.

## Incident carried forward from V30

V30 published its provider-free runtime receipt, manifest, and sanitized
authentication receipt. Its sole preflight-supervisor `generate` invocation
then failed closed while validating the owner-scoped temporary-directory
contract, before the first runtime write. The supplied directory had mode
`0777` and was not owned by the effective user; its absolute path remains
unreleased. The refused generation created no runtime directory, config, or
plist, ran no install or start operation, and started no authentication,
provider, or model process. No preflight profile or production assignment was
attempted, and no result or score was released.

The public
[`development-matched-50x6-v30.superseded.json`](../results/development-matched-50x6-v30.superseded.json)
record closes V30 as terminal and non-resumable. V31 must preserve that record,
the V30 public receipts, and all earlier terminal evidence unchanged. It must
use fresh panel, cohort, credential, private-state, cache, checkout, supervisor,
socket, temporary-directory, and output namespaces.

## Retained process-identity guarantees

V31 retains the three authoritative supervisor-identity components introduced
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
path, or other private input—and before creating the runtime directory—V31
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

The V31 source-level cut explicitly rejects the V30 panel contract. It
advances:

- panel persistent-supervisor contract `v15` to `v16`;
- panel ID from `development-matched-50x6-v30` to
  `development-matched-50x6-v31`;
- top-level schema from `development_matched_panel_v30` to
  `development_matched_panel_v31`; and
- every panel/cohort-specific freeze and private/execution namespace from V30
  to V31.

Persistent-supervisor state remains `v4`, record/event/execution-context
domains remain `v4`, the identity domain remains `v3`, the protocol remains
`v9`, and LaunchAgent config/auth remains `v16`. Those retained wire schemas are
not falsely advanced merely to create a new panel namespace.

The panel, LaunchAgent, tests, and V31 runbook carry the V31-specific values
together. Historical V30 artifacts and its supersession record remain
unchanged. Earlier runbooks remain historical records; the V30 runbook gains
only an explicit terminal banner and forward pointer to V31. This source cut is
still not a runtime receipt, manifest, or execution authorization.

## Gates before any V31 provider call

- Publish only the existing V30 supersession record and its public contract test
  in a V30 terminal-closeout commit whose sole parent is the authenticated V30
  receipt commit `ba25bab441f7cc28f56e4668006f12821949a0e4`. Independently
  resolve and pin the resulting closeout commit before any V31 publication; no
  closeout commit value is assumed in advance.
- Publish and pin the reviewed, post-version-cut V31 control-plane commit.
- Generate and publish the deterministic provider-free runtime receipt.
- Freeze a new manifest and private state in fresh namespaces.
- Explicitly supply the exact `$670` cumulative spend acknowledgement from the
  V31 runbook, including V30's zero-model-call terminal generation refusal; its
  reviewed source text and ceiling are not authorization.
- Complete zero-model-call authentication and the six-call preflight.
- Independently validate and pin the passing preflight receipt before creating
  a production checkout.
- Require separate authorization before the 300-assignment production start.

No V31 runtime, private state, authentication, preflight, or production action
is part of this control-plane patch.
