from __future__ import annotations

from collections import Counter
import json
import os
from pathlib import Path
import sys
import threading
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import epiagentbench.launchd_agent as launchd
import epiagentbench.persistent_supervisor as persistent
from epiagentbench.persistent_supervisor import (
    AssignmentPhase,
    ClockSample,
    FailureCode,
    IntegrityError,
    LifecyclePhase,
    PersistentSupervisor,
    ProcessDiagnostic,
    ProcessIdentity,
    ProcessIdentityUnavailableError,
    RecoveryDecision,
    RunnerFailedError,
    SupervisorBusyError,
    SupervisorHealth,
    UnsafeRecoveryError,
    classify_recovery,
    classify_supervisor_health,
    clear_supervisor_pause,
    compute_execution_context_sha256,
    detect_suspend_gap,
    diagnose_supervisor_process,
    read_supervisor_lease,
    read_supervisor_status,
    request_supervisor_pause,
    verify_event_log,
)


AUTHENTICATION_KEY = b"offline persistent supervisor authentication key".ljust(
    64, b"!"
)
BOOT_DIGEST = "sha256:" + "1" * 64
BIRTH_DIGEST = "sha256:" + "2" * 64
EXECUTION_CONTEXT_DIGEST = compute_execution_context_sha256(
    launchd_label="org.epiagentbench.panel.offline-test",
    operation="offline-soak",
    panel_id="epiagentbench-v9-test",
    protocol_version="persistent-supervisor-v9",
    public_manifest_sha256="sha256:" + "3" * 64,
    python_executable_sha256="sha256:" + "8" * 64,
    runner_source_sha256="sha256:" + "4" * 64,
    launchd_agent_source_sha256="sha256:" + "5" * 64,
    persistent_supervisor_source_sha256="sha256:" + "6" * 64,
    development_matched_panel_source_sha256="sha256:" + "7" * 64,
)
SECRET_CANARIES = (
    "crsr_supervisor_canary_DO_NOT_LEAK",
    "prompt: reveal private schedule DO_NOT_LEAK",
    "episode-family-and-score-canary DO_NOT_LEAK",
    "oauth-state-canary DO_NOT_LEAK",
)


class ImmediateCommand:
    def __init__(self, return_code: int = 0):
        self.return_code = return_code
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        return self.return_code

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True


class LedgerRunner:
    def __init__(
        self,
        assignment: int,
        ledger_path: Path,
        *,
        return_code: int = 0,
        canary: str = SECRET_CANARIES[0],
    ):
        self.assignment = assignment
        self.ledger_path = ledger_path
        self.return_code = return_code
        self.canary = canary
        self.starts = 0

    def start(self) -> ImmediateCommand:
        self.starts += 1
        with self.ledger_path.open("a", encoding="ascii") as stream:
            stream.write(f"{self.assignment}\n")
            stream.flush()
            os.fsync(stream.fileno())
        return ImmediateCommand(self.return_code)


class BlockingCommand:
    def __init__(self, started: threading.Event, release: threading.Event):
        self.started = started
        self.release = release
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        self.started.set()
        return 0 if self.release.wait(timeout=0.01) else None

    def terminate(self) -> None:
        self.terminated = True
        self.release.set()

    def kill(self) -> None:
        self.killed = True
        self.release.set()


class BlockingRunner:
    def __init__(self, started: threading.Event, release: threading.Event):
        self.starts = 0
        self.command = BlockingCommand(started, release)

    def start(self) -> BlockingCommand:
        self.starts += 1
        return self.command


class FakeClock:
    def __init__(self, wall: float = 1_000.0, monotonic: float = 10.0):
        self.wall = wall
        self.monotonic = monotonic
        self.wall_step_per_sleep = 0.0
        self.monotonic_step_per_sleep = 0.0

    def wall_time(self) -> float:
        return self.wall

    def monotonic_time(self) -> float:
        return self.monotonic

    def sleep(self, _: float) -> None:
        self.wall += self.wall_step_per_sleep
        self.monotonic += self.monotonic_step_per_sleep


class IncrementingWallClock:
    def __init__(self, wall: float = 1_000.05, step: float = 0.95):
        self.wall = wall
        self.step = step

    def __call__(self) -> float:
        observed = self.wall
        self.wall += self.step
        return observed


class PollSequenceCommand:
    def __init__(self, results: list[int | None]):
        self.results = list(results)
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        if self.results:
            return self.results.pop(0)
        return None

    def terminate(self) -> None:
        self.terminated = True
        self.results[:] = [0]

    def kill(self) -> None:
        self.killed = True
        self.results[:] = [0]


class FixedCommandRunner:
    def __init__(self, command: PollSequenceCommand | ImmediateCommand):
        self.command = command
        self.starts = 0

    def start(self):
        self.starts += 1
        return self.command


class SimulatedHostLoss(BaseException):
    pass


class PersistentSupervisorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        os.chmod(self.root, 0o700)
        self.runtime = self.root / "runtime"
        self.ledger = self.root / "external-invocation-ledger.txt"
        self.identity = ProcessIdentity(
            boot_identity_sha256=BOOT_DIGEST,
            pid=max(1, os.getpid()),
            process_birth_identity_sha256=BIRTH_DIGEST,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _supervisor(self, runtime: Path | None = None, **changes) -> PersistentSupervisor:
        arguments = {
            "execution_context_sha256": EXECUTION_CONTEXT_DIGEST,
            "heartbeat_interval_seconds": 10.0,
            "process_identity": self.identity,
        }
        arguments.update(changes)
        return PersistentSupervisor(
            runtime or self.runtime,
            AUTHENTICATION_KEY,
            **arguments,
        )

    def _ledger_values(self) -> list[int]:
        if not self.ledger.exists():
            return []
        return [int(value) for value in self.ledger.read_text().splitlines()]

    def test_v30_schema_and_authentication_domains_are_cut(self) -> None:
        self.assertEqual(
            persistent.SCHEMA_VERSION,
            "epiagentbench.persistent_supervisor.v4",
        )
        self.assertEqual(
            persistent._RECORD_DOMAIN,
            b"epiagentbench:persistent-supervisor:record:v4\x00",
        )
        self.assertEqual(
            persistent._EVENT_HASH_DOMAIN,
            b"epiagentbench:persistent-supervisor:event-hash:v4\x00",
        )
        self.assertEqual(
            persistent._EVENT_HMAC_DOMAIN,
            b"epiagentbench:persistent-supervisor:event-hmac:v4\x00",
        )
        self.assertEqual(
            persistent._IDENTITY_DOMAIN,
            b"epiagentbench:persistent-supervisor:identity:v3\x00",
        )
        self.assertEqual(
            persistent._EXECUTION_CONTEXT_DOMAIN,
            b"epiagentbench:persistent-supervisor:execution-context:v4\x00",
        )

    def test_recovery_classifier_permits_only_provably_unlaunched_boundaries(self) -> None:
        for phase in (
            AssignmentPhase.CLEAN_BOUNDARY,
            AssignmentPhase.PREPARED,
            AssignmentPhase.RESULT_COMMITTED,
        ):
            with self.subTest(phase=phase):
                self.assertIs(
                    classify_recovery(phase, LifecyclePhase.RUNNING),
                    RecoveryDecision.SAFE_TO_RESUME,
                )
        for phase in (
            AssignmentPhase.LAUNCH_COMMITTED,
            AssignmentPhase.RUNNING,
            AssignmentPhase.TERMINAL_AMBIGUITY,
        ):
            with self.subTest(phase=phase):
                self.assertIs(
                    classify_recovery(phase, LifecyclePhase.RUNNING),
                    RecoveryDecision.FAIL_CLOSED,
                )
        self.assertIs(
            classify_recovery(AssignmentPhase.TERMINAL, LifecyclePhase.COMPLETED),
            RecoveryDecision.ALREADY_TERMINAL,
        )
        self.assertIs(
            classify_recovery("attacker_phase", "running"),
            RecoveryDecision.FAIL_CLOSED,
        )

    def test_execution_context_binds_every_runtime_source_module(self) -> None:
        arguments = {
            "launchd_label": "org.epiagentbench.panel.offline-test",
            "operation": "offline-soak",
            "panel_id": "epiagentbench-v9-test",
            "protocol_version": "persistent-supervisor-v9",
            "public_manifest_sha256": "sha256:" + "3" * 64,
            "python_executable_sha256": "sha256:" + "8" * 64,
            "runner_source_sha256": "sha256:" + "4" * 64,
            "launchd_agent_source_sha256": "sha256:" + "5" * 64,
            "persistent_supervisor_source_sha256": "sha256:" + "6" * 64,
            "development_matched_panel_source_sha256": "sha256:" + "7" * 64,
        }
        baseline = compute_execution_context_sha256(**arguments)
        for field, replacement in (
            ("python_executable_sha256", "sha256:" + "b" * 64),
            ("launchd_agent_source_sha256", "sha256:" + "8" * 64),
            ("persistent_supervisor_source_sha256", "sha256:" + "9" * 64),
            (
                "development_matched_panel_source_sha256",
                "sha256:" + "a" * 64,
            ),
        ):
            with self.subTest(field=field):
                changed = dict(arguments)
                changed[field] = replacement
                self.assertNotEqual(
                    compute_execution_context_sha256(**changed),
                    baseline,
                )

    def test_authenticated_status_and_lease_reject_hmac_tampering(self) -> None:
        status = self._supervisor().run(LedgerRunner(1, self.ledger))
        self.assertEqual(status["lifecycle"], LifecyclePhase.COMPLETED)
        lease = read_supervisor_lease(
            self.runtime, authentication_key=AUTHENTICATION_KEY
        )
        self.assertEqual(lease["lease_epoch"], status["lease_epoch"])
        self.assertEqual(
            lease["execution_context_sha256"],
            status["execution_context_sha256"],
        )
        for name in ("status.json", "lease.json"):
            with self.subTest(name=name):
                path = self.runtime / name
                original = path.read_bytes()
                value = json.loads(original)
                value["heartbeat_sequence"] += 1
                path.write_text(json.dumps(value), encoding="utf-8")
                os.chmod(path, 0o600)
                loader = (
                    read_supervisor_status
                    if name == "status.json"
                    else read_supervisor_lease
                )
                with self.assertRaises(IntegrityError):
                    loader(self.runtime, authentication_key=AUTHENTICATION_KEY)
                path.write_bytes(original)
                os.chmod(path, 0o600)

    def test_v30_rejects_predecessor_and_open_supervisor_records(self) -> None:
        self._supervisor().run(LedgerRunner(1, self.ledger))
        for name, record_type, loader in (
            ("status.json", "status", read_supervisor_status),
            ("lease.json", "lease", read_supervisor_lease),
        ):
            with self.subTest(name=name):
                path = self.runtime / name
                original = path.read_bytes()
                sealed = json.loads(original)
                payload = {
                    key: value
                    for key, value in sealed.items()
                    if key != "authentication"
                }
                for mutation, replacement in (
                    (
                        "predecessor",
                        {
                            "schema_version": (
                                "epiagentbench.persistent_supervisor.v3"
                            )
                        },
                    ),
                    ("open", {"unexpected_field": "not-allowed"}),
                ):
                    with self.subTest(name=name, mutation=mutation):
                        mutated = {**payload, **replacement}
                        path.write_bytes(
                            persistent._canonical_bytes(
                                persistent._seal_record(
                                    record_type,
                                    mutated,
                                    AUTHENTICATION_KEY,
                                )
                            )
                            + b"\n"
                        )
                        os.chmod(path, 0o600)
                        with self.assertRaises(IntegrityError):
                            loader(
                                self.runtime,
                                authentication_key=AUTHENTICATION_KEY,
                            )
                path.write_bytes(original)
                os.chmod(path, 0o600)

    def test_v30_rejects_predecessor_and_open_event_schemas(self) -> None:
        self._supervisor().run(LedgerRunner(1, self.ledger))
        path = self.runtime / persistent.EVENT_FILE
        original = path.read_bytes()
        first = json.loads(original.splitlines()[0])
        original_body = dict(first["body"])

        def sealed_event(body: dict[str, object]) -> dict[str, object]:
            record_sha256 = persistent._event_hash(body)
            signed = {
                "body": body,
                "record_sha256": record_sha256,
            }
            return {
                **signed,
                "authentication": {
                    "algorithm": "hmac-sha256",
                    "tag": persistent._event_tag(
                        signed,
                        AUTHENTICATION_KEY,
                    ),
                },
            }

        mutations: tuple[tuple[str, dict[str, object]], ...] = (
            (
                "predecessor_body",
                sealed_event(
                    {
                        **original_body,
                        "schema_version": (
                            "epiagentbench.persistent_supervisor.v3"
                        ),
                    }
                ),
            ),
            (
                "open_body",
                sealed_event(
                    {**original_body, "unexpected_field": "not-allowed"}
                ),
            ),
            (
                "open_envelope",
                {
                    **sealed_event(original_body),
                    "unexpected_field": "not-allowed",
                },
            ),
        )
        for mutation, event in mutations:
            with self.subTest(mutation=mutation):
                path.write_bytes(persistent._canonical_bytes(event) + b"\n")
                os.chmod(path, 0o600)
                with self.assertRaises(IntegrityError):
                    verify_event_log(
                        self.runtime,
                        authentication_key=AUTHENTICATION_KEY,
                    )
        path.write_bytes(original)
        os.chmod(path, 0o600)

    def test_status_and_lease_share_timestamp_across_second_boundary(self) -> None:
        wall_clock = IncrementingWallClock()
        terminal = self._supervisor(
            wall_clock=wall_clock,
            monotonic_clock=lambda: 10.0,
        ).run(LedgerRunner(1, self.ledger))
        status = read_supervisor_status(
            self.runtime, authentication_key=AUTHENTICATION_KEY
        )
        lease = read_supervisor_lease(
            self.runtime, authentication_key=AUTHENTICATION_KEY
        )
        self.assertEqual(
            status["heartbeat_wall_unix_seconds"],
            lease["heartbeat_wall_unix_seconds"],
        )
        self.assertEqual(
            terminal["heartbeat_wall_unix_seconds"],
            lease["heartbeat_wall_unix_seconds"],
        )
        observed = launchd._core_status(
            self.runtime,
            authentication_key=AUTHENTICATION_KEY,
            expected_execution_context_sha256=EXECUTION_CONTEXT_DIGEST,
        )
        self.assertEqual(observed["state"], "authenticated")
        self.assertEqual(observed["health"], "terminal")
        self.assertEqual(observed["runner_commands_completed"], 1)
        self.assertEqual(observed["runner_commands_total"], 1)
        self.assertNotIn("completed_assignments", observed)
        self.assertNotIn("total_assignments", observed)

    def test_execution_context_mismatch_never_reuses_terminal_runtime(self) -> None:
        first = LedgerRunner(1, self.ledger)
        self._supervisor().run(first)
        different_context = "sha256:" + "9" * 64
        second = LedgerRunner(2, self.ledger)
        with self.assertRaises(UnsafeRecoveryError):
            self._supervisor(
                execution_context_sha256=different_context
            ).run(second)
        self.assertEqual(self._ledger_values(), [1])
        self.assertEqual(second.starts, 0)
        status = read_supervisor_status(
            self.runtime, authentication_key=AUTHENTICATION_KEY
        )
        lease = read_supervisor_lease(
            self.runtime, authentication_key=AUTHENTICATION_KEY
        )
        self.assertEqual(
            status["execution_context_sha256"], EXECUTION_CONTEXT_DIGEST
        )
        self.assertEqual(
            lease["execution_context_sha256"], EXECUTION_CONTEXT_DIGEST
        )

    def test_status_has_exact_allowlisted_schema_and_no_content_fields(self) -> None:
        self._supervisor().run(
            LedgerRunner(1, self.ledger, canary=SECRET_CANARIES[1])
        )
        status = read_supervisor_status(
            self.runtime, authentication_key=AUTHENTICATION_KEY
        )
        self.assertEqual(
            set(status),
            {
                "schema_version",
                "lease_epoch",
                "execution_context_sha256",
                "lifecycle",
                "assignment_phase",
                "pid",
                "boot_identity_sha256",
                "process_birth_identity_sha256",
                "heartbeat_sequence",
                "heartbeat_wall_unix_seconds",
                "completed_assignments",
                "total_assignments",
                "active_assignment_ordinal",
                "pause_after_current",
                "suspend_gap_detected",
                "failure_code",
            },
        )
        encoded = json.dumps(status, sort_keys=True)
        for forbidden in (
            "provider",
            "output",
            "prompt",
            "observation",
            "episode",
            "family",
            "score",
            "trace",
            "credential",
            "oauth",
            "environment",
            *SECRET_CANARIES,
        ):
            self.assertNotIn(forbidden.lower(), encoded.lower())

    def test_live_lock_is_authoritative_over_stale_or_reused_pid_metadata(self) -> None:
        started = threading.Event()
        release = threading.Event()
        first_runner = BlockingRunner(started, release)
        outcome: list[object] = []

        def run_first() -> None:
            try:
                outcome.append(self._supervisor().run(first_runner))
            except BaseException as error:  # surfaced by the assertion below
                outcome.append(error)

        thread = threading.Thread(target=run_first, daemon=True)
        thread.start()
        self.assertTrue(started.wait(timeout=2.0))

        reused_identity = ProcessIdentity(
            boot_identity_sha256=BOOT_DIGEST,
            pid=self.identity.pid,
            process_birth_identity_sha256="sha256:" + "3" * 64,
        )
        contender = PersistentSupervisor(
            self.runtime,
            AUTHENTICATION_KEY,
            execution_context_sha256=EXECUTION_CONTEXT_DIGEST,
            heartbeat_interval_seconds=10.0,
            process_identity=reused_identity,
        )
        with self.assertRaises(SupervisorBusyError):
            contender.run(LedgerRunner(2, self.ledger))

        release.set()
        thread.join(timeout=2.0)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(outcome), 1)
        self.assertIsInstance(outcome[0], dict)
        self.assertEqual(first_runner.starts, 1)

    def test_darwin_boot_session_uuid_is_canonical_and_strict(self) -> None:
        upper = b"19AB956D-0088-46DB-B2AB-FC67966D5433\n"
        lower = b"19ab956d-0088-46db-b2ab-fc67966d5433"
        expected = (
            b"darwin-bootsessionuuid-v1:"
            b"19ab956d-0088-46db-b2ab-fc67966d5433"
        )
        self.assertEqual(
            persistent._canonical_darwin_boot_session_token(upper),
            expected,
        )
        self.assertEqual(
            persistent._canonical_darwin_boot_session_token(lower),
            expected,
        )
        for invalid in (
            b"",
            b"00000000-0000-0000-0000-000000000000",
            b"19ab956d008846dbb2abfc67966d5433",
            b" 19ab956d-0088-46db-b2ab-fc67966d5433",
            b"19ab956d-0088-46db-b2ab-fc67966d5433 ",
            b"19ab956d-0088-46db-b2ab-fc67966d5433\n\n",
            b"not-a-boot-session-uuid-000000000000",
        ):
            with self.subTest(invalid=invalid):
                self.assertIsNone(
                    persistent._canonical_darwin_boot_session_token(invalid)
                )

    def test_darwin_boot_probe_uses_only_boot_session_uuid(self) -> None:
        payload = b"19AB956D-0088-46DB-B2AB-FC67966D5433\x00"

        class FakeSysctlByName:
            argtypes: object = None
            restype: object = None

            def __init__(self) -> None:
                self.calls: list[tuple[bytes, object, int]] = []

            def __call__(
                self,
                name: bytes,
                output: object,
                size_pointer: object,
                replacement: object,
                replacement_size: int,
            ) -> int:
                size = persistent.ctypes.cast(
                    size_pointer,
                    persistent.ctypes.POINTER(persistent.ctypes.c_size_t),
                ).contents
                self.calls.append((name, output, replacement_size))
                self.assert_no_replacement(replacement, replacement_size)
                if output is None:
                    size.value = len(payload)
                    return 0
                persistent.ctypes.memmove(output, payload, len(payload))
                size.value = len(payload)
                return 0

            @staticmethod
            def assert_no_replacement(
                replacement: object,
                replacement_size: int,
            ) -> None:
                if replacement is not None or replacement_size != 0:
                    raise AssertionError("boot-session sysctl attempted a write")

        fake_sysctl = FakeSysctlByName()
        fake_libc = type("FakeLibC", (), {"sysctlbyname": fake_sysctl})()
        with (
            patch.object(persistent.ctypes, "CDLL", return_value=fake_libc),
            patch.object(
                persistent.subprocess,
                "run",
                side_effect=AssertionError("external sysctl is forbidden"),
            ),
        ):
            token = persistent._darwin_boot_session_token()
        self.assertEqual(
            token,
            (
                b"darwin-bootsessionuuid-v1:"
                b"19ab956d-0088-46db-b2ab-fc67966d5433"
            ),
        )
        self.assertEqual(len(fake_sysctl.calls), 2)
        self.assertEqual(
            [call[0] for call in fake_sysctl.calls],
            [b"kern.bootsessionuuid", b"kern.bootsessionuuid"],
        )
        self.assertIsNone(fake_sysctl.calls[0][1])
        self.assertIsNotNone(fake_sysctl.calls[1][1])

    def test_darwin_boot_probe_retries_only_unavailable_reads(self) -> None:
        expected = (
            b"darwin-bootsessionuuid-v1:"
            b"19ab956d-0088-46db-b2ab-fc67966d5433"
        )
        with (
            patch.object(persistent.Path, "read_bytes", side_effect=OSError),
            patch.object(persistent.platform, "system", return_value="Darwin"),
            patch.object(
                persistent,
                "_darwin_boot_session_token",
                side_effect=(None, None, expected),
            ) as boot_session,
            patch.object(persistent.time, "sleep") as sleep,
        ):
            self.assertEqual(persistent._boot_token(), expected)
        self.assertEqual(boot_session.call_count, 3)
        self.assertEqual(sleep.call_count, 2)
        sleep.assert_called_with(0.01)

    def test_darwin_process_birth_fields_are_numeric_and_strict(self) -> None:
        self.assertEqual(
            persistent.ctypes.sizeof(persistent._DarwinProcBSDInfo),
            persistent._DARWIN_PROC_BSDINFO_SIZE,
        )
        self.assertEqual(persistent._DarwinProcBSDInfo.pbi_pid.offset, 12)
        self.assertEqual(
            persistent._DarwinProcBSDInfo.pbi_start_tvsec.offset,
            120,
        )
        self.assertEqual(
            persistent._DarwinProcBSDInfo.pbi_start_tvusec.offset,
            128,
        )
        token = persistent._canonical_darwin_process_birth_token(
            requested_pid=4123,
            reported_pid=4123,
            start_seconds=1_786_000_000,
            start_microseconds=123_456,
        )
        self.assertEqual(
            token,
            b"darwin-proc-pidtbsdinfo-v1:1786000000:123456",
        )
        invalid = (
            {"requested_pid": 0},
            {"reported_pid": 4124},
            {"start_seconds": 0},
            {"start_microseconds": -1},
            {"start_microseconds": 1_000_000},
        )
        base = {
            "requested_pid": 4123,
            "reported_pid": 4123,
            "start_seconds": 1_786_000_000,
            "start_microseconds": 123_456,
        }
        for changes in invalid:
            with self.subTest(changes=changes):
                self.assertIsNone(
                    persistent._canonical_darwin_process_birth_token(
                        **{**base, **changes}
                    )
                )

    def test_darwin_process_birth_uses_exact_proc_pidinfo_abi(self) -> None:
        class FakeProcPidInfo:
            argtypes: object = None
            restype: object = None

            def __init__(self, observed_size_delta: int = 0) -> None:
                self.calls: list[tuple[int, int, int, int]] = []
                self.observed_size_delta = observed_size_delta

            def __call__(
                self,
                pid: int,
                flavor: int,
                argument: int,
                buffer: object,
                size: int,
            ) -> int:
                self.calls.append((pid, flavor, argument, size))
                info = persistent.ctypes.cast(
                    buffer,
                    persistent.ctypes.POINTER(
                        persistent._DarwinProcBSDInfo
                    ),
                ).contents
                info.pbi_pid = pid
                info.pbi_start_tvsec = 1_786_000_000
                info.pbi_start_tvusec = 123_456
                return size + self.observed_size_delta

        fake_proc_pidinfo = FakeProcPidInfo()
        fake_libproc = type(
            "FakeLibProc",
            (),
            {"proc_pidinfo": fake_proc_pidinfo},
        )()
        with patch.object(
            persistent.ctypes,
            "CDLL",
            return_value=fake_libproc,
        ) as load:
            token = persistent._darwin_process_birth_token(4123)
        self.assertEqual(
            token,
            b"darwin-proc-pidtbsdinfo-v1:1786000000:123456",
        )
        load.assert_called_once_with(
            "/usr/lib/libproc.dylib",
            use_errno=True,
        )
        self.assertEqual(
            fake_proc_pidinfo.calls,
            [(4123, 3, 0, persistent._DARWIN_PROC_BSDINFO_SIZE)],
        )

        short_proc_pidinfo = FakeProcPidInfo(observed_size_delta=-1)
        short_libproc = type(
            "ShortLibProc",
            (),
            {"proc_pidinfo": short_proc_pidinfo},
        )()
        with patch.object(
            persistent.ctypes,
            "CDLL",
            return_value=short_libproc,
        ):
            self.assertIsNone(
                persistent._darwin_process_birth_token(4123)
            )

    def test_darwin_process_birth_never_uses_formatted_ps_output(self) -> None:
        expected = b"darwin-proc-pidtbsdinfo-v1:1786000000:123456"
        with (
            patch.object(persistent.Path, "read_bytes", side_effect=OSError),
            patch.object(persistent.platform, "system", return_value="Darwin"),
            patch.object(
                persistent,
                "_darwin_process_birth_token",
                return_value=expected,
            ) as birth,
            patch.object(
                persistent.subprocess,
                "run",
                side_effect=AssertionError("formatted ps output is forbidden"),
            ),
        ):
            self.assertEqual(persistent._process_birth_token(4123), expected)
        birth.assert_called_once_with(4123)

    def test_unavailable_identity_never_reaches_runner_or_durable_state(
        self,
    ) -> None:
        cases = (
            ("boot", None, b"birth"),
            ("birth", b"boot", None),
        )
        for name, boot, birth in cases:
            runtime = self.root / f"unavailable-{name}"
            runner = LedgerRunner(1, self.ledger)
            with (
                self.subTest(identity=name),
                patch.object(persistent, "_boot_token", return_value=boot),
                patch.object(
                    persistent,
                    "_process_birth_token",
                    return_value=birth,
                ),
                self.assertRaises(ProcessIdentityUnavailableError),
            ):
                persistent.run_supervised_panel(
                    runner_argv=("unused-offline-runner",),
                    environment={},
                    runtime_dir=runtime,
                    authentication_key=AUTHENTICATION_KEY,
                    execution_context_sha256=EXECUTION_CONTEXT_DIGEST,
                    command_runner=runner,
                )
            self.assertEqual(runner.starts, 0)
            self.assertTrue(runtime.is_dir())
            self.assertEqual(list(runtime.iterdir()), [])

    def test_process_diagnostic_detects_pid_reuse_and_boot_change(self) -> None:
        status = {
            "pid": 4123,
            "boot_identity_sha256": persistent._identity_hash(b"boot-a"),
            "process_birth_identity_sha256": persistent._identity_hash(b"birth-a"),
        }
        with (
            patch.object(persistent, "_boot_token", return_value=b"boot-b"),
            patch.object(persistent.os, "kill"),
            patch.object(persistent, "_process_birth_token", return_value=b"birth-a"),
        ):
            self.assertIs(
                diagnose_supervisor_process(status), ProcessDiagnostic.BOOT_MISMATCH
            )
        with (
            patch.object(persistent, "_boot_token", return_value=b"boot-a"),
            patch.object(persistent.os, "kill"),
            patch.object(persistent, "_process_birth_token", return_value=b"birth-b"),
        ):
            self.assertIs(
                diagnose_supervisor_process(status), ProcessDiagnostic.BIRTH_MISMATCH
            )

    def test_process_diagnostic_unavailable_short_circuits_liveness(self) -> None:
        status = {
            "pid": 4123,
            "boot_identity_sha256": persistent._identity_hash(b"boot-a"),
            "process_birth_identity_sha256": persistent._identity_hash(b"birth-a"),
        }
        with (
            patch.object(persistent, "_boot_token", return_value=None),
            patch.object(persistent.os, "kill") as kill,
            patch.object(persistent, "_process_birth_token") as birth,
        ):
            self.assertIs(
                diagnose_supervisor_process(status),
                ProcessDiagnostic.UNAVAILABLE,
            )
        kill.assert_not_called()
        birth.assert_not_called()

    def test_stale_supervisor_heartbeat_cannot_be_masked_by_provider_activity(self) -> None:
        status = {
            "lifecycle": LifecyclePhase.RUNNING.value,
            "heartbeat_wall_unix_seconds": 1_000,
        }
        recent_provider_activity_wall_seconds = 1_099
        self.assertGreater(recent_provider_activity_wall_seconds, 1_000)
        self.assertIs(
            classify_supervisor_health(
                status,
                now_wall_seconds=1_100,
                process_diagnostic=ProcessDiagnostic.MATCH,
                max_heartbeat_age_seconds=45,
            ),
            SupervisorHealth.STALE_HEARTBEAT,
        )
        self.assertIs(
            classify_supervisor_health(
                status,
                now_wall_seconds=1_010,
                process_diagnostic=ProcessDiagnostic.MATCH,
                max_heartbeat_age_seconds=45,
            ),
            SupervisorHealth.HEALTHY,
        )
        self.assertIs(
            classify_supervisor_health(
                status,
                now_wall_seconds=1_010,
                process_diagnostic=ProcessDiagnostic.BIRTH_MISMATCH,
                max_heartbeat_age_seconds=45,
            ),
            SupervisorHealth.PROCESS_MISMATCH,
        )

    def test_pause_request_is_honored_only_after_current_assignment(self) -> None:
        class PauseOnPoll(ImmediateCommand):
            def poll(inner_self) -> int | None:
                request_supervisor_pause(
                    self.runtime, authentication_key=AUTHENTICATION_KEY
                )
                return 0

        first = FixedCommandRunner(PauseOnPoll())
        second = LedgerRunner(2, self.ledger)
        status = self._supervisor().run((first, second))
        self.assertEqual(status["lifecycle"], LifecyclePhase.PAUSED)
        self.assertEqual(status["assignment_phase"], AssignmentPhase.CLEAN_BOUNDARY)
        self.assertEqual(status["completed_assignments"], 1)
        self.assertEqual(first.starts, 1)
        self.assertEqual(second.starts, 0)

        clear_supervisor_pause(self.runtime, authentication_key=AUTHENTICATION_KEY)
        resumed = self._supervisor().run((first, second))
        self.assertEqual(resumed["lifecycle"], LifecyclePhase.COMPLETED)
        self.assertEqual(first.starts, 1, "completed prefix must not be replayed")
        self.assertEqual(second.starts, 1)

    def test_crash_before_launch_commit_is_resumable_without_duplicate_call(self) -> None:
        runner = LedgerRunner(1, self.ledger)
        crashing = self._supervisor()
        transition = crashing._transition

        def crash_before_commit(**kwargs):
            if kwargs.get("assignment_phase") is AssignmentPhase.LAUNCH_COMMITTED:
                raise SimulatedHostLoss
            return transition(**kwargs)

        with patch.object(crashing, "_transition", side_effect=crash_before_commit):
            with self.assertRaises(SimulatedHostLoss):
                crashing.run(runner)
        durable = read_supervisor_status(
            self.runtime, authentication_key=AUTHENTICATION_KEY
        )
        self.assertEqual(durable["assignment_phase"], AssignmentPhase.PREPARED)
        self.assertEqual(self._ledger_values(), [])

        completed = self._supervisor().run(runner)
        self.assertEqual(completed["lifecycle"], LifecyclePhase.COMPLETED)
        self.assertEqual(self._ledger_values(), [1])
        self.assertEqual(runner.starts, 1)

    def test_crash_after_launch_commit_never_retries_external_call(self) -> None:
        runner = LedgerRunner(1, self.ledger)
        crashing = self._supervisor()
        fail_closed = crashing._fail_closed

        class StartsThenLosesHost(LedgerRunner):
            def start(inner_self):
                super().start()
                raise SimulatedHostLoss

        launched = StartsThenLosesHost(1, self.ledger)

        def lose_host_before_incident_record(*args, **kwargs):
            raise SimulatedHostLoss

        with patch.object(
            crashing, "_fail_closed", side_effect=lose_host_before_incident_record
        ):
            with self.assertRaises(SimulatedHostLoss):
                crashing.run(launched)
        durable = read_supervisor_status(
            self.runtime, authentication_key=AUTHENTICATION_KEY
        )
        self.assertEqual(
            durable["assignment_phase"], AssignmentPhase.LAUNCH_COMMITTED
        )
        self.assertEqual(self._ledger_values(), [1])

        with self.assertRaises(UnsafeRecoveryError):
            self._supervisor().run(runner)
        self.assertEqual(self._ledger_values(), [1])
        self.assertEqual(runner.starts, 0)
        terminal = read_supervisor_status(
            self.runtime, authentication_key=AUTHENTICATION_KEY
        )
        lease = read_supervisor_lease(
            self.runtime, authentication_key=AUTHENTICATION_KEY
        )
        self.assertEqual(lease["lease_epoch"], terminal["lease_epoch"])
        self.assertEqual(terminal["lifecycle"], LifecyclePhase.FAILED_CLOSED)
        self.assertEqual(terminal["failure_code"], FailureCode.UNSAFE_RECOVERY)

    def test_nonzero_child_exit_is_terminal_and_not_retried(self) -> None:
        failed = LedgerRunner(1, self.ledger, return_code=23)
        with self.assertRaises(RunnerFailedError) as raised:
            self._supervisor().run(failed)
        self.assertIs(
            raised.exception.failure_code,
            FailureCode.RUNNER_EXIT,
        )
        self.assertNotIn(SECRET_CANARIES[0], str(raised.exception))
        self.assertEqual(self._ledger_values(), [1])
        with self.assertRaises(UnsafeRecoveryError):
            self._supervisor().run(LedgerRunner(1, self.ledger))
        self.assertEqual(self._ledger_values(), [1])
        status = read_supervisor_status(
            self.runtime, authentication_key=AUTHENTICATION_KEY
        )
        self.assertEqual(status["failure_code"], FailureCode.RUNNER_EXIT)
        self.assertEqual(
            status["assignment_phase"], AssignmentPhase.TERMINAL_AMBIGUITY
        )

    def test_reserved_terminal_receipt_exit_is_distinct_and_not_retried(
        self,
    ) -> None:
        failed = LedgerRunner(
            1,
            self.ledger,
            return_code=persistent.HANDLED_TERMINAL_RECEIPT_EXIT_CODE,
        )
        with self.assertRaises(RunnerFailedError) as raised:
            self._supervisor().run(failed)
        self.assertIs(
            raised.exception.failure_code,
            FailureCode.RUNNER_RESERVED_TERMINAL_EXIT,
        )
        self.assertEqual(self._ledger_values(), [1])
        status = read_supervisor_status(
            self.runtime,
            authentication_key=AUTHENTICATION_KEY,
        )
        self.assertEqual(status["lifecycle"], LifecyclePhase.FAILED_CLOSED)
        self.assertEqual(status["assignment_phase"], AssignmentPhase.TERMINAL)
        self.assertEqual(
            status["failure_code"],
            FailureCode.RUNNER_RESERVED_TERMINAL_EXIT,
        )

        with self.assertRaises(UnsafeRecoveryError):
            self._supervisor().run(LedgerRunner(1, self.ledger))
        self.assertEqual(self._ledger_values(), [1])

    def test_reserved_terminal_audit_exit_is_terminal_and_not_retried(
        self,
    ) -> None:
        failed = LedgerRunner(
            1,
            self.ledger,
            return_code=persistent.TERMINAL_AUDIT_REQUIRED_EXIT_CODE,
        )
        with self.assertRaises(RunnerFailedError) as raised:
            self._supervisor().run(failed)
        self.assertIs(
            raised.exception.failure_code,
            FailureCode.RUNNER_RESERVED_TERMINAL_AUDIT_EXIT,
        )
        status = read_supervisor_status(
            self.runtime,
            authentication_key=AUTHENTICATION_KEY,
        )
        self.assertEqual(status["lifecycle"], LifecyclePhase.FAILED_CLOSED)
        self.assertEqual(status["assignment_phase"], AssignmentPhase.TERMINAL)
        self.assertEqual(
            status["failure_code"],
            FailureCode.RUNNER_RESERVED_TERMINAL_AUDIT_EXIT,
        )
        with self.assertRaises(UnsafeRecoveryError):
            self._supervisor().run(LedgerRunner(1, self.ledger))
        self.assertEqual(self._ledger_values(), [1])

    def test_supervised_command_forwards_authenticated_reserved_exit_state(
        self,
    ) -> None:
        self.runtime.mkdir(mode=0o700)
        handled = {
            "lifecycle": LifecyclePhase.FAILED_CLOSED.value,
            "assignment_phase": AssignmentPhase.TERMINAL.value,
            "failure_code": FailureCode.RUNNER_RESERVED_TERMINAL_EXIT.value,
        }
        with patch.object(
            persistent,
            "run_supervised_panel",
            side_effect=RunnerFailedError(
                FailureCode.RUNNER_RESERVED_TERMINAL_EXIT
            ),
        ), patch.object(
            persistent,
            "read_supervisor_status",
            return_value=handled,
        ):
            self.assertEqual(
                persistent.run_supervised_command(
                    runtime_dir=self.runtime,
                    operation="preflight",
                    command=("offline-command",),
                    child_environment={},
                    authentication_key=AUTHENTICATION_KEY,
                    execution_context_sha256=EXECUTION_CONTEXT_DIGEST,
                ),
                persistent.HANDLED_TERMINAL_RECEIPT_EXIT_CODE,
            )

        for untrusted_state in (
            {
                **handled,
                "assignment_phase": AssignmentPhase.TERMINAL_AMBIGUITY.value,
            },
            {
                **handled,
                "failure_code": FailureCode.RUNNER_EXIT.value,
            },
        ):
            with self.subTest(untrusted_state=untrusted_state), patch.object(
                persistent,
                "run_supervised_panel",
                side_effect=RunnerFailedError(FailureCode.RUNNER_EXIT),
            ), patch.object(
                persistent,
                "read_supervisor_status",
                return_value=untrusted_state,
            ):
                with self.assertRaises(RunnerFailedError):
                    persistent.run_supervised_command(
                        runtime_dir=self.runtime,
                        operation="preflight",
                        command=("offline-command",),
                        child_environment={},
                        authentication_key=AUTHENTICATION_KEY,
                        execution_context_sha256=EXECUTION_CONTEXT_DIGEST,
                    )

    def test_supervised_command_does_not_relabel_pause_as_terminal_receipt(
        self,
    ) -> None:
        self.runtime.mkdir(mode=0o700)
        with patch.object(
            persistent,
            "run_supervised_panel",
            return_value={"lifecycle": LifecyclePhase.PAUSED.value},
        ):
            with self.assertRaises(RunnerFailedError) as raised:
                persistent.run_supervised_command(
                    runtime_dir=self.runtime,
                    operation="production",
                    command=("offline-command",),
                    child_environment={},
                    authentication_key=AUTHENTICATION_KEY,
                    execution_context_sha256=EXECUTION_CONTEXT_DIGEST,
                )
            self.assertIs(
                raised.exception.failure_code,
                FailureCode.SUPERVISOR_INTERNAL,
            )

    def test_supervised_command_forwards_authenticated_terminal_audit_exit(
        self,
    ) -> None:
        self.runtime.mkdir(mode=0o700)
        handled = {
            "lifecycle": LifecyclePhase.FAILED_CLOSED.value,
            "assignment_phase": AssignmentPhase.TERMINAL.value,
            "failure_code": (
                FailureCode.RUNNER_RESERVED_TERMINAL_AUDIT_EXIT.value
            ),
        }
        with patch.object(
            persistent,
            "run_supervised_panel",
            side_effect=RunnerFailedError(
                FailureCode.RUNNER_RESERVED_TERMINAL_AUDIT_EXIT
            ),
        ), patch.object(
            persistent,
            "read_supervisor_status",
            return_value=handled,
        ):
            self.assertEqual(
                persistent.run_supervised_command(
                    runtime_dir=self.runtime,
                    operation="preflight",
                    command=("offline-command",),
                    child_environment={},
                    authentication_key=AUTHENTICATION_KEY,
                    execution_context_sha256=EXECUTION_CONTEXT_DIGEST,
                ),
                persistent.TERMINAL_AUDIT_REQUIRED_EXIT_CODE,
            )

    def test_suspend_gap_is_distinct_from_provider_activity_and_fails_closed(self) -> None:
        self.assertFalse(
            detect_suspend_gap(
                ClockSample(100.0, 50.0),
                ClockSample(110.0, 60.0),
                heartbeat_interval_seconds=10.0,
            )
        )
        self.assertTrue(
            detect_suspend_gap(
                ClockSample(100.0, 50.0),
                ClockSample(200.0, 60.0),
                heartbeat_interval_seconds=10.0,
            )
        )

        clock = FakeClock()
        clock.wall_step_per_sleep = 100.0
        clock.monotonic_step_per_sleep = 10.0
        command = PollSequenceCommand([None, None])
        supervisor = self._supervisor(
            wall_clock=clock.wall_time,
            monotonic_clock=clock.monotonic_time,
            sleep=clock.sleep,
        )
        with self.assertRaises(RunnerFailedError):
            supervisor.run(FixedCommandRunner(command))
        self.assertTrue(command.terminated)
        status = read_supervisor_status(
            self.runtime, authentication_key=AUTHENTICATION_KEY
        )
        self.assertEqual(status["lifecycle"], LifecyclePhase.FAILED_CLOSED)
        self.assertTrue(status["suspend_gap_detected"])
        self.assertEqual(status["failure_code"], FailureCode.SUSPEND_GAP)

    def test_event_log_is_owner_only_bounded_hash_chained_and_secret_free(self) -> None:
        runners = [
            LedgerRunner(index, self.ledger, canary=SECRET_CANARIES[index % 4])
            for index in range(1, 4)
        ]
        self._supervisor().run(runners)
        path = self.runtime / "events.jsonl"
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertLessEqual(path.stat().st_size, persistent.DEFAULT_MAX_EVENT_LOG_BYTES)
        records = verify_event_log(
            self.runtime, authentication_key=AUTHENTICATION_KEY
        )
        self.assertGreater(len(records), 3)
        for previous, current in zip(records, records[1:]):
            self.assertEqual(
                current["body"]["previous_sha256"], previous["record_sha256"]
            )
        persisted = b"".join(
            item.read_bytes() for item in self.runtime.iterdir() if item.is_file()
        )
        for canary in SECRET_CANARIES:
            self.assertNotIn(canary.encode(), persisted)

        lines = path.read_bytes().splitlines()
        tampered = json.loads(lines[1])
        tampered["body"]["completed_assignments"] += 1
        lines[1] = json.dumps(tampered, sort_keys=True).encode()
        path.write_bytes(b"\n".join(lines) + b"\n")
        os.chmod(path, 0o600)
        with self.assertRaises(IntegrityError):
            verify_event_log(self.runtime, authentication_key=AUTHENTICATION_KEY)

    def test_event_record_limit_fails_closed_without_unbounded_append(self) -> None:
        supervisor = self._supervisor(max_event_records=16)
        runners = [LedgerRunner(index, self.ledger) for index in range(1, 20)]
        with self.assertRaises((IntegrityError, RunnerFailedError)):
            supervisor.run(runners)
        path = self.runtime / "events.jsonl"
        self.assertLessEqual(len(path.read_bytes().splitlines()), 16)
        status = read_supervisor_status(
            self.runtime, authentication_key=AUTHENTICATION_KEY
        )
        self.assertEqual(status["lifecycle"], LifecyclePhase.FAILED_CLOSED)
        self.assertIn(
            status["failure_code"],
            {FailureCode.EVENT_LIMIT, FailureCode.INTEGRITY},
        )

    def test_three_hundred_assignment_soak_uses_external_at_most_once_ledger(self) -> None:
        runners = [LedgerRunner(index, self.ledger) for index in range(1, 301)]
        status = self._supervisor().run(runners)
        self.assertEqual(status["lifecycle"], LifecyclePhase.COMPLETED)
        self.assertEqual(status["completed_assignments"], 300)
        values = self._ledger_values()
        counts = Counter(values)
        self.assertEqual(values, list(range(1, 301)))
        self.assertEqual(set(counts.values()), {1})
        self.assertTrue(all(runner.starts == 1 for runner in runners))

        # A second initiator observes terminal authenticated state and performs
        # no launch.  This is the external proof, not a self-reported count.
        repeated = self._supervisor().run(runners)
        self.assertEqual(repeated["lifecycle"], LifecyclePhase.COMPLETED)
        self.assertEqual(self._ledger_values(), values)
        self.assertTrue(all(runner.starts == 1 for runner in runners))
        records = verify_event_log(
            self.runtime, authentication_key=AUTHENTICATION_KEY
        )
        self.assertLessEqual(len(records), persistent.DEFAULT_MAX_EVENT_RECORDS)

    def test_production_shaped_single_child_checkpoints_three_hundred_items(self) -> None:
        """Exercise the same one-child shape used by the launchd adapter."""

        child_runtime = self.root / "production-shaped-runtime"
        child_ledger = self.root / "production-shaped-ledger.txt"
        child_checkpoint = self.root / "production-shaped-checkpoint.json"
        fake_panel = self.root / "fake_panel.py"
        fake_panel.write_text(
            "import json, os, sys\n"
            "from pathlib import Path\n"
            "ledger = Path(sys.argv[1])\n"
            "checkpoint = Path(sys.argv[2])\n"
            "voids = 0\n"
            "for ordinal in range(1, 301):\n"
            "    with ledger.open('a', encoding='ascii') as stream:\n"
            "        stream.write(f'{ordinal}\\n')\n"
            "        stream.flush()\n"
            "        os.fsync(stream.fileno())\n"
            "    if ordinal == 137:\n"
            "        voids += 1\n"
            "    checkpoint.write_text(\n"
            "        json.dumps({\n"
            "            'terminal': ordinal,\n"
            "            'transport_voids': voids,\n"
            "            'status': (\n"
            "                'complete_pending_supervisor_completion'\n"
            "                if ordinal == 300 else 'running'\n"
            "            ),\n"
            "        }),\n"
            "        encoding='utf-8',\n"
            "    )\n"
            "candidate = json.loads(checkpoint.read_text())\n"
            "assert candidate == {\n"
            "    'terminal': 300,\n"
            "    'transport_voids': 1,\n"
            "    'status': 'complete_pending_supervisor_completion',\n"
            "}\n",
            encoding="utf-8",
        )
        os.chmod(fake_panel, 0o600)
        with patch.object(
            persistent,
            "current_process_identity",
            return_value=self.identity,
        ):
            status = persistent.run_supervised_panel(
                runner_argv=(
                    sys.executable,
                    str(fake_panel),
                    str(child_ledger),
                    str(child_checkpoint),
                ),
                environment={},
                runtime_dir=child_runtime,
                authentication_key=AUTHENTICATION_KEY,
                execution_context_sha256=EXECUTION_CONTEXT_DIGEST,
                heartbeat_interval_seconds=10.0,
            )
        self.assertEqual(status["lifecycle"], LifecyclePhase.COMPLETED)
        self.assertEqual(status["total_assignments"], 1)
        self.assertEqual(status["completed_assignments"], 1)
        values = [int(value) for value in child_ledger.read_text().splitlines()]
        self.assertEqual(values, list(range(1, 301)))
        self.assertEqual(set(Counter(values).values()), {1})
        self.assertEqual(
            json.loads(child_checkpoint.read_text()),
            {
                "terminal": 300,
                "transport_voids": 1,
                "status": "complete_pending_supervisor_completion",
            },
        )


if __name__ == "__main__":
    unittest.main()
