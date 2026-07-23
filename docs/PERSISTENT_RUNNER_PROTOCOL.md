# Persistent matched-panel runner protocol

Status: proposed v9 execution contract. This document does not authorize a
provider call.

## Purpose

The development matched panel takes roughly one day when its 300 assignments
run serially. The process that owns those assignments must not depend on the
lifetime of a Codex task, terminal, PTY, editor, or desktop-app turn. A chat
heartbeat may observe the run, but it must never own, relaunch, reorder, or
repair it.

The local macOS pilot therefore runs as a user `launchd` job. `launchd` owns a
small supervisor under `caffeinate`; the supervisor owns the panel runner and
an authenticated execution lease. Closing the initiating task or app must not
terminate that job.

## Safety invariants

1. The hidden schedule remains serial and frozen before any model-bearing
   call.
2. Exactly one panel runner may own a panel, and exactly one supervisor may
   own a supervisor runtime. The runner's existing host-global panel lock and
   the supervisor's distinct runtime lock are authoritative within their
   scopes; PID metadata is diagnostic only.
3. A paid provider launch is preceded by a durable launch commitment. Once
   that commitment exists, the assignment is never retried unless the
   provider offers a frozen, verified idempotency mechanism.
4. The still-running evaluator may continue with the next assignment only
   when the preceding assignment has a durable terminal record and there is
   no execution or credential incident. The current one-child adapter does
   not translate that rule into permission to relaunch a vanished evaluator.
5. An interrupted Codex call is terminal because its persistent credential
   file may have been refreshed in place.
6. No monitor can mutate panel state or invoke a provider.
7. Provider text, prompts, observations, episode references, family labels,
   schedule data, scores, traces, credentials, OAuth state, environment
   variables, and arbitrary exception text never enter supervisor status or
   logs.

## Durable assignment phases and the current adapter

The evaluator's authenticated private checkpoint distinguishes these provider
assignment phases:

- `clean_boundary`: the preceding assignment is terminal and the next paid
  invocation has not been reserved.
- `reserved_not_launched`: the next assignment is durably reserved and the
  evaluator can prove that no provider process was started.
- `launch_committed`: the evaluator has durably crossed the at-most-once
  boundary immediately before provider process creation.
- `provider_returned`: the original provider process returned and its process
  group and output pipes were proven quiescent.
- `result_committed`: the sanitized result and terminal assignment state are
  durable.

A crash at `clean_boundary` or a provably unlaunched reservation is eligible
for evaluator-adjudicated recovery. A crash at or after `launch_committed`
cannot replay that assignment. Without a provider idempotency key or durable
remote job handle, transparent recovery from an in-flight host failure and
strict at-most-once execution are mutually incompatible. The benchmark
chooses at-most-once execution and fails closed.

The initial macOS adapter supervises one complete evaluator command, not 300
individual provider commands. Its own `prepared`, `launch_committed`,
`running`, and terminal phases describe that one child command. The evaluator
remains authoritative for every provider assignment and retains its separate
panel lock and authenticated checkpoints. This release fixes task, terminal,
and app detachment; it does not promise automatic restart of a crashed outer
supervisor at the next provider-assignment boundary. Such a crash is terminal
until an explicit audit proves otherwise. A 300-command supervisor soak tests
the generic phase machine, while a separate production-shaped fake panel and
real launchd detachment test exercise the one-command adapter.

The first authenticated live attestation permanently binds the private panel
state to the exact LaunchAgent label, execution-context digest, and sealed
configuration-file digest for that operation. A newly generated runtime cannot
replace it, even at a clean assignment boundary. Any loss of that bound
supervisor after execution begins is a terminal panel incident.

## Two-phase success and public release

The evaluator child cannot publish a successful preflight receipt or completed
benchmark result. On success it first writes an HMAC-private candidate and then
a trace-free public `pending_supervisor_completion` watermark. Scores, traces,
schedule order, and family labels remain private. The child exits successfully
only after that pending state is durable.

The outer supervisor then records its own authenticated `completed` status,
matching lease, and terminal event-chain record. Still inside the one-shot
LaunchAgent worker, a local-only finalizer verifies those records and the exact
create-once runtime binding. Only then may it mark the private release as
complete and atomically replace the public watermark with the final receipt or
result. The public artifact is the final evaluator-side durable write.

If the worker crashes after supervisor completion but before publication, an
explicit `finalize` control may repeat only this local verification and atomic
publication step. It cannot relaunch the worker, evaluator, authentication
bootstrap, or provider. A terminal release-validation incident is never
retryable.

## Supervisor lease and liveness

The private supervisor directory and every file in it are current-user owned,
non-symlinked, non-hardlinked, and mode `0700` or `0600` as appropriate. An
authenticated lease binds:

- panel identifier and public precommitment;
- a random lease epoch;
- boot-session identity;
- supervisor PID and process-birth identity;
- lifecycle state and last heartbeat time;
- a monotonic heartbeat counter.

The supervisor holds its distinct runtime lock for its full lifetime while the
child evaluator holds the panel lock. It updates an authenticated heartbeat
every 10--30 seconds. A sanitized supervisor status reports only its finite
child-command state, heartbeat age, pause state, and incident enum. Existing
evaluator telemetry remains the separate source for aggregate completion,
void, remaining, active-profile, coarse-activity, and credential-quarantine
state. A monitor must authenticate both sources.

Provider-output activity is not a liveness signal. A monitor reports healthy
only when the authenticated heartbeat is fresh, the launchd label and lease
epoch agree, the expected process birth identity is live, and no incident is
present.

## LaunchAgent boundary

The public LaunchAgent property list contains no secret or provider command.
It invokes only:

```text
/usr/bin/caffeinate -dimsu <python> <supervisor-cli> worker --config <private-config>
```

The owner-only private config contains allowlisted paths and frozen command
arguments. The worker reads the Cursor API key from the named macOS Keychain
service into its child environment in memory. The key is absent from the
property list, command line, repository, status, and logs. LaunchAgent stdout
and stderr are `/dev/null`; a bounded private event log contains only
allowlisted event codes and finite scalar fields.

The job is a one-shot supervised run, not an unconditional `KeepAlive` loop.
After an in-flight crash, an automatic restart must not create another paid
call. Recovery requires the same authenticated state audit as a manual launch.

## Pause, sleep, network, and shutdown

`pause_after_current` is available to the generic multi-command supervisor and
is honored only between its child commands. The current production-shaped
adapter has one child command for the entire panel, so it does **not** claim a
safe between-provider pause. No live v9 operator may use a stop signal as a
pause; stopping an active child is an interruption and requires incident
audit.

`caffeinate` prevents idle sleep while the job is active. The supervisor also
compares wall and monotonic clocks. An unexpected suspension gap is recorded
as a finite lifecycle event and evaluated at the next safe boundary.

The current adapter delegates network behavior inside a provider call to the
existing evaluator timeout and transport-void rules; it does not add a
pre-launch connectivity oracle. A network failure after the evaluator's
provider launch commitment never permits a retry. A reboot or power loss
during an active call remains terminal. A final artifact is releasable only if
the authenticated supervisor finishes without a suspension or integrity
incident, even if the child happened to write a candidate artifact first.

## Required offline release gate

No v9 model call may start until all of the following pass through the same
supervisor path intended for production:

- a real macOS launchd test where the initiating process exits while the
  production `PersistentSupervisor` core and a fake long-running child remain
  alive and then complete; the production LaunchAgent/Keychain wrapper is
  covered separately with fake Keychain and launchctl boundaries;
- crash injection before and after every durable phase transition, with an
  external fake-call ledger proving at most one invocation per assignment;
- concurrent launch, stale PID, PID reuse, boot change, lock, and lease-tamper
  tests;
- stale provider telemetry with a dead supervisor producing an alert;
- generic pause and suspension-gap tests, plus production-shaped mid-call
  interruption and release-gate tests;
- secret, prompt, episode, schedule, trace, and score canary scans across the
  property list, private event log, public progress, and monitor output;
- a 300-command generic-supervisor soak and a production-shaped fake panel
  that internally checkpoints 300 assignments, durably records one ordinary
  transport void, continues exactly once through every later assignment, and
  exits successfully only with a pending 300-terminal candidate;
- candidate-publication crash tests proving that no passed receipt, score,
  trace, schedule, or family label is released before authenticated supervisor
  completion, plus idempotent post-completion finalization;
- the existing cohort-retirement, no-partial-release, evaluator-tampering,
  metadata-leakage, and prompt-injection suites.

## Versioning consequence

The persistent supervisor changes the source, runtime, timeout, and operational
contracts. V8 therefore cannot be resumed or relabeled. A live v9 requires a
fresh hidden cohort and schedule, authentication key, credential namespaces,
public precommitment, supervised six-profile preflight, and exact spend
authorization. The v8 completed records and transport void are audit evidence
only and are never mixed into the v9 estimand.
