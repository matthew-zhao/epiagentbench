# V30 control-plane design

This document describes pre-freeze V30 engineering work. It is not a spend
authorization, runtime receipt, panel manifest, authentication receipt, or
permission to create private state or invoke a provider.

## Incident carried forward from V29

V29 reached 25 completed assignments and then failed closed after the 26th
provider invocation. The post-provider supervisor attestation observed a boot
identity mismatch, while the available host evidence showed no reboot. The
sanitized evidence does not retain the exact physical bytes that produced the
stored identity, so it cannot distinguish formatted `kern.boottime` drift from
an old synthetic fallback persisted after a transient startup-probe failure.
Both V29 identity paths were noncanonical. The chargeable invocation was sealed
as a transport void and V29 is terminal and non-resumable.

The exact trace-free V29 production terminal receipt passed pinned
provider-free attestation with status `stopped_supervisor_incident`, 26
terminal assignments, and no scientific results or scores. It and the V29
supersession record close the public predecessor path without inspecting or
releasing protected schedule, trace, or provider data.

V30 must preserve the V29 receipts and pinned checkouts as immutable evidence.
It must use fresh panel, cohort, credential, private-state, cache, checkout,
supervisor, socket, and output namespaces.

## Process identity correction

The V30 supervisor identity has three authoritative components:

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

## Frozen source-level version cut

The V30 source-level cut explicitly rejects earlier runtime schemas. It
advances:

- persistent supervisor state `v3` to `v4`;
- supervisor record/event/execution-context domains `v3` to `v4`;
- supervisor identity domain `v2` to `v3`;
- persistent-supervisor protocol `v8` to `v9`;
- LaunchAgent config/auth schema `v15` to `v16`;
- panel persistent-supervisor contract `v14` to `v15`;
- panel ID and top-level schema to `development-matched-50x6-v30` and
  `development_matched_panel_v30`.

The panel, supervisor, LaunchAgent, tests, and V30 runbook carry these values
together. Historical V29 artifacts and its runbook remain unchanged. This
source cut is still not a runtime receipt, manifest, or execution
authorization.

## Gates before any V30 provider call

- Publish only the existing exact V29 production terminal receipt at
  `results/development-matched-50x6-v29.json` together with
  `results/development-matched-50x6-v29.superseded.json` in one closeout
  commit, independently verify it, and pin its exact commit before any V30
  publication.
- Publish and pin the reviewed, post-version-cut V30 control-plane commit.
- Generate and publish the deterministic provider-free runtime receipt.
- Freeze a new manifest and private state in fresh namespaces.
- Explicitly supply the exact `$670` cumulative spend acknowledgement from the
  V30 runbook; its reviewed source text and ceiling are not authorization.
- Complete zero-model-call authentication and the six-call preflight.
- Independently validate and pin the passing preflight receipt before creating
  a production checkout.
- Require separate authorization before the 300-assignment production start.

No V30 runtime, private state, authentication, preflight, or production action
is part of this control-plane patch.
