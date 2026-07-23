"""Persistent, provider-agnostic supervision for long benchmark commands.

This module deliberately knows nothing about models, credentials, prompts, or
benchmark records.  It keeps a small authenticated control plane around an
injectable command runner.  Command arguments and environments remain only in
memory and are never written to the supervisor directory.

The supervisor lock is distinct from the matched-panel runner's own lock.  It
prevents two wrappers from owning the same runtime directory; the child runner
continues to enforce its authoritative panel-level at-most-once lock.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import platform
import secrets
import signal
import stat
import subprocess
import time
from typing import Callable, Mapping, Protocol, Sequence, runtime_checkable


SCHEMA_VERSION = "epiagentbench.persistent_supervisor.v1"
LEASE_FILE = "lease.json"
STATUS_FILE = "status.json"
EVENT_FILE = "events.jsonl"
CONTROL_FILE = "control.json"
LOCK_FILE = "supervisor.lock"

DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 15.0
MIN_HEARTBEAT_INTERVAL_SECONDS = 10.0
MAX_HEARTBEAT_INTERVAL_SECONDS = 30.0
DEFAULT_MAX_EVENT_RECORDS = 4096
DEFAULT_MAX_EVENT_LOG_BYTES = 2_000_000
MAX_JSON_BYTES = 32_768
MAX_EVENT_LINE_BYTES = 4096
MAX_KEY_BYTES = 4096

_RECORD_DOMAIN = b"epiagentbench:persistent-supervisor:record:v1\x00"
_EVENT_HASH_DOMAIN = b"epiagentbench:persistent-supervisor:event-hash:v1\x00"
_EVENT_HMAC_DOMAIN = b"epiagentbench:persistent-supervisor:event-hmac:v1\x00"
_IDENTITY_DOMAIN = b"epiagentbench:persistent-supervisor:identity:v1\x00"
_EXECUTION_CONTEXT_DOMAIN = (
    b"epiagentbench:persistent-supervisor:execution-context:v1\x00"
)
_ZERO_EVENT_HASH = "sha256:" + "0" * 64


class LifecyclePhase(StrEnum):
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSE_REQUESTED = "pause_requested"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED_CLOSED = "failed_closed"


class AssignmentPhase(StrEnum):
    CLEAN_BOUNDARY = "clean_boundary"
    PREPARED = "prepared"
    LAUNCH_COMMITTED = "launch_committed"
    RUNNING = "running"
    RESULT_COMMITTED = "result_committed"
    TERMINAL_AMBIGUITY = "terminal_ambiguity"
    TERMINAL = "terminal"


class RecoveryDecision(StrEnum):
    SAFE_TO_RESUME = "safe_to_resume"
    ALREADY_TERMINAL = "already_terminal"
    FAIL_CLOSED = "fail_closed"


class FailureCode(StrEnum):
    NONE = "none"
    UNSAFE_RECOVERY = "unsafe_recovery"
    RUNNER_START = "runner_start_failed"
    RUNNER_EXIT = "runner_nonzero_exit"
    RUNNER_PROTOCOL = "runner_protocol_failure"
    SUSPEND_GAP = "suspend_gap"
    INTEGRITY = "integrity_failure"
    EVENT_LIMIT = "event_limit"
    SUPERVISOR_INTERNAL = "supervisor_internal"


class EventType(StrEnum):
    LEASE_ACQUIRED = "lease_acquired"
    RECOVERY_ACCEPTED = "recovery_accepted"
    ASSIGNMENT_PREPARED = "assignment_prepared"
    LAUNCH_COMMITTED = "launch_committed"
    COMMAND_STARTED = "command_started"
    ASSIGNMENT_COMPLETED = "assignment_completed"
    PAUSE_REQUESTED = "pause_requested"
    PAUSED = "paused"
    COMPLETED = "completed"
    SUSPEND_GAP_DETECTED = "suspend_gap_detected"
    FAILED_CLOSED = "failed_closed"


class ProcessDiagnostic(StrEnum):
    MATCH = "match"
    PID_ABSENT = "pid_absent"
    BOOT_MISMATCH = "boot_mismatch"
    BIRTH_MISMATCH = "birth_mismatch"
    UNAVAILABLE = "unavailable"


class SupervisorHealth(StrEnum):
    HEALTHY = "healthy"
    STALE_HEARTBEAT = "stale_heartbeat"
    PROCESS_MISMATCH = "process_mismatch"
    TERMINAL = "terminal"
    INVALID = "invalid"


class SupervisorError(RuntimeError):
    """Base class for fixed-message supervisor failures."""


class SupervisorBusyError(SupervisorError):
    """Another process holds the runtime directory's supervisor lock."""


class IntegrityError(SupervisorError):
    """A private file failed its closed-schema or HMAC checks."""


class UnsafeRecoveryError(SupervisorError):
    """A prior launch commitment makes automatic retry ambiguous."""


class RunnerFailedError(SupervisorError):
    """The injected runner failed after durable launch commitment."""


@dataclass(frozen=True)
class ProcessIdentity:
    """Hashed host/process identity suitable for a sanitized lease."""

    boot_identity_sha256: str
    pid: int
    process_birth_identity_sha256: str


@dataclass(frozen=True)
class ClockSample:
    wall_seconds: float
    monotonic_seconds: float


@runtime_checkable
class RunningCommand(Protocol):
    """One started command; ``poll`` must be non-blocking."""

    def poll(self) -> int | None: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...


@runtime_checkable
class CommandRunner(Protocol):
    """Injectable irreversible command launch.

    ``start`` is called only after the supervisor has durably recorded
    :attr:`AssignmentPhase.LAUNCH_COMMITTED`.  It must not return until the
    child has either been launched or a launch failure is known.
    """

    def start(self) -> RunningCommand: ...


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")


def _identity_hash(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(_IDENTITY_DOMAIN + value).hexdigest()


def compute_execution_context_sha256(
    *,
    launchd_label: str,
    operation: str,
    panel_id: str,
    protocol_version: str,
    public_manifest_sha256: str,
    runner_source_sha256: str,
    launchd_agent_source_sha256: str,
    persistent_supervisor_source_sha256: str,
    development_matched_panel_source_sha256: str,
) -> str:
    """Bind a runtime to finite public execution context, never argv or env.

    All fields are deliberately public identifiers or content digests.  Paths,
    command arguments, environment variables, and credential material are not
    accepted by this API.
    """

    safe_identifier_characters = frozenset(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._@+-"
    )
    identifiers = (launchd_label, operation, panel_id, protocol_version)
    if any(
        not isinstance(value, str)
        or not 1 <= len(value) <= 128
        or any(character not in safe_identifier_characters for character in value)
        for value in identifiers
    ):
        raise ValueError("Execution context contains an invalid public identifier")
    source_digests = (
        public_manifest_sha256,
        runner_source_sha256,
        launchd_agent_source_sha256,
        persistent_supervisor_source_sha256,
        development_matched_panel_source_sha256,
    )
    if any(not _valid_digest(value) for value in source_digests):
        raise ValueError("Execution context requires valid public SHA-256 digests")
    public_context = {
        "launchd_label": launchd_label,
        "operation": operation,
        "panel_id": panel_id,
        "protocol_version": protocol_version,
        "public_manifest_sha256": public_manifest_sha256,
        "runner_source_sha256": runner_source_sha256,
        "launchd_agent_source_sha256": launchd_agent_source_sha256,
        "persistent_supervisor_source_sha256": (
            persistent_supervisor_source_sha256
        ),
        "development_matched_panel_source_sha256": (
            development_matched_panel_source_sha256
        ),
    }
    return "sha256:" + hashlib.sha256(
        _EXECUTION_CONTEXT_DOMAIN + _canonical_bytes(public_context)
    ).hexdigest()


def _valid_digest(value: object) -> bool:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        return False
    suffix = value[7:]
    return len(suffix) == 64 and all(character in "0123456789abcdef" for character in suffix)


def _load_authentication_key(value: bytes | Path) -> bytes:
    if isinstance(value, bytes):
        if not 32 <= len(value) <= MAX_KEY_BYTES:
            raise ValueError("Authentication key must contain 32-4096 bytes")
        return value
    path = Path(value)
    try:
        metadata = path.lstat()
    except OSError:
        raise ValueError("Authentication key is unavailable") from None
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or metadata.st_mode & 0o077
        or metadata.st_nlink != 1
        or not 32 <= metadata.st_size <= MAX_KEY_BYTES
    ):
        raise ValueError("Authentication key must be an owner-only regular file")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            opened = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_uid != os.geteuid()
                or opened.st_mode & 0o077
                or opened.st_nlink != 1
                or (opened.st_dev, opened.st_ino)
                != (metadata.st_dev, metadata.st_ino)
            ):
                raise ValueError("Authentication key changed while opening")
            key = stream.read(MAX_KEY_BYTES + 1)
    except OSError:
        raise ValueError("Authentication key is unavailable") from None
    if len(key) != metadata.st_size:
        raise ValueError("Authentication key changed while reading")
    return key


def _ensure_private_directory(path: Path, *, create: bool) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        raise ValueError("Supervisor runtime directory must be absolute")
    if create:
        candidate.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        metadata = candidate.lstat()
        resolved = candidate.resolve(strict=True)
    except OSError:
        raise ValueError("Supervisor runtime directory is unavailable") from None
    if (
        resolved != candidate
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
    ):
        raise ValueError("Supervisor runtime directory must be a real owner directory")
    if metadata.st_mode & 0o077:
        try:
            os.chmod(candidate, 0o700)
            metadata = candidate.lstat()
        except OSError:
            raise ValueError("Supervisor runtime directory is not owner-only") from None
    if stat.S_IMODE(metadata.st_mode) != 0o700:
        raise ValueError("Supervisor runtime directory is not owner-only")
    return candidate


def _validate_private_file(path: Path, *, maximum_bytes: int) -> os.stat_result:
    try:
        metadata = path.lstat()
    except OSError:
        raise IntegrityError("Private supervisor file is unavailable") from None
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_nlink != 1
        or not 0 <= metadata.st_size <= maximum_bytes
    ):
        raise IntegrityError("Private supervisor file failed safety checks")
    return metadata


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_private_json(path: Path, value: Mapping[str, object]) -> None:
    payload = _canonical_bytes(value) + b"\n"
    if not 0 < len(payload) <= MAX_JSON_BYTES:
        raise IntegrityError("Private supervisor record exceeds its size limit")
    if path.exists() or path.is_symlink():
        _validate_private_file(path, maximum_bytes=MAX_JSON_BYTES)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(16)}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor: int | None = None
    created = False
    try:
        descriptor = os.open(temporary, flags, 0o600)
        created = True
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            descriptor = None
            os.fchmod(stream.fileno(), 0o600)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        created = False
        os.chmod(path, 0o600)
        _fsync_directory(path.parent)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if created:
            try:
                temporary.unlink()
            except OSError:
                pass


def _record_tag(record_type: str, payload: Mapping[str, object], key: bytes) -> str:
    message = _RECORD_DOMAIN + record_type.encode("ascii") + b"\x00" + _canonical_bytes(payload)
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def _seal_record(
    record_type: str, payload: Mapping[str, object], key: bytes
) -> dict[str, object]:
    return {
        **payload,
        "authentication": {
            "algorithm": "hmac-sha256",
            "tag": _record_tag(record_type, payload, key),
        },
    }


def _read_private_json(path: Path) -> dict[str, object]:
    metadata = _validate_private_file(path, maximum_bytes=MAX_JSON_BYTES)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            opened = os.fstat(stream.fileno())
            if (
                (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino)
                or opened.st_size != metadata.st_size
                or opened.st_nlink != 1
            ):
                raise IntegrityError("Private supervisor file changed while opening")
            raw = stream.read(MAX_JSON_BYTES + 1)
    except OSError:
        raise IntegrityError("Private supervisor file is unavailable") from None
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise IntegrityError("Private supervisor record is invalid") from None
    if not isinstance(value, dict):
        raise IntegrityError("Private supervisor record is invalid")
    return value


def _open_record(
    path: Path,
    *,
    record_type: str,
    key: bytes,
    expected_keys: frozenset[str],
) -> dict[str, object]:
    sealed = _read_private_json(path)
    authentication = sealed.pop("authentication", None)
    supplied = authentication.get("tag") if isinstance(authentication, dict) else None
    if (
        frozenset(sealed) != expected_keys
        or not isinstance(authentication, dict)
        or set(authentication) != {"algorithm", "tag"}
        or authentication.get("algorithm") != "hmac-sha256"
        or not isinstance(supplied, str)
        or not hmac.compare_digest(supplied, _record_tag(record_type, sealed, key))
    ):
        raise IntegrityError("Private supervisor record authentication failed")
    return sealed


def _boot_token() -> bytes | None:
    linux_path = Path("/proc/sys/kernel/random/boot_id")
    try:
        raw = linux_path.read_bytes()
        if 0 < len(raw) <= 256:
            return b"linux:" + raw.strip()
    except OSError:
        pass
    if platform.system() == "Darwin":
        try:
            result = subprocess.run(
                ["/usr/sbin/sysctl", "-n", "kern.boottime"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"},
                check=False,
                timeout=2,
            )
            if result.returncode == 0 and 0 < len(result.stdout) <= 512:
                return b"darwin:" + result.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    return None


def _process_birth_token(pid: int) -> bytes | None:
    proc_stat = Path("/proc") / str(pid) / "stat"
    try:
        raw = proc_stat.read_bytes()
        if 0 < len(raw) <= 8192:
            _, separator, tail = raw.rpartition(b")")
            fields = tail.strip().split()
            if separator and len(fields) > 19:
                return b"linux-proc-start:" + fields[19]
    except OSError:
        pass
    if platform.system() == "Darwin":
        try:
            result = subprocess.run(
                ["/bin/ps", "-o", "lstart=", "-p", str(pid)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"},
                check=False,
                timeout=2,
            )
            if result.returncode == 0 and 0 < len(result.stdout) <= 256:
                return b"darwin-ps-start:" + result.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    return None


def current_process_identity() -> ProcessIdentity:
    """Return a hashed boot/PID/birth triple for PID-reuse diagnostics."""

    pid = os.getpid()
    boot = _boot_token()
    birth = _process_birth_token(pid)
    if boot is None:
        # This remains stable for this process and is explicitly only a
        # diagnostic fallback, not the authoritative flock identity.
        boot = f"fallback-boot:{int(time.time() - time.monotonic())}".encode("ascii")
    if birth is None:
        birth = f"fallback-birth:{pid}:{time.monotonic_ns()}".encode("ascii")
    return ProcessIdentity(_identity_hash(boot), pid, _identity_hash(birth))


def diagnose_supervisor_process(status: Mapping[str, object]) -> ProcessDiagnostic:
    """Compare a sanitized status identity with current host process state."""

    pid = status.get("pid")
    expected_boot = status.get("boot_identity_sha256")
    expected_birth = status.get("process_birth_identity_sha256")
    if not isinstance(pid, int) or pid <= 0 or not _valid_digest(expected_boot) or not _valid_digest(expected_birth):
        return ProcessDiagnostic.UNAVAILABLE
    boot = _boot_token()
    if boot is None:
        return ProcessDiagnostic.UNAVAILABLE
    if not hmac.compare_digest(_identity_hash(boot), str(expected_boot)):
        return ProcessDiagnostic.BOOT_MISMATCH
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return ProcessDiagnostic.PID_ABSENT
    except PermissionError:
        return ProcessDiagnostic.UNAVAILABLE
    birth = _process_birth_token(pid)
    if birth is None:
        return ProcessDiagnostic.UNAVAILABLE
    if not hmac.compare_digest(_identity_hash(birth), str(expected_birth)):
        return ProcessDiagnostic.BIRTH_MISMATCH
    return ProcessDiagnostic.MATCH


def classify_supervisor_health(
    status: Mapping[str, object],
    *,
    now_wall_seconds: float,
    process_diagnostic: ProcessDiagnostic | str,
    max_heartbeat_age_seconds: float = 45.0,
) -> SupervisorHealth:
    """Classify liveness without consulting provider output or activity.

    This intentionally makes the supervisor heartbeat and process identity the
    only live signals.  A recently active provider cannot mask a dead wrapper.
    """

    try:
        lifecycle = LifecyclePhase(status.get("lifecycle"))
        diagnostic = ProcessDiagnostic(process_diagnostic)
    except ValueError:
        return SupervisorHealth.INVALID
    heartbeat = status.get("heartbeat_wall_unix_seconds")
    if (
        not isinstance(heartbeat, int)
        or isinstance(heartbeat, bool)
        or not isinstance(now_wall_seconds, (int, float))
        or isinstance(now_wall_seconds, bool)
        or not isinstance(max_heartbeat_age_seconds, (int, float))
        or isinstance(max_heartbeat_age_seconds, bool)
        or max_heartbeat_age_seconds <= 0
    ):
        return SupervisorHealth.INVALID
    if lifecycle in {
        LifecyclePhase.COMPLETED,
        LifecyclePhase.FAILED_CLOSED,
        LifecyclePhase.PAUSED,
    }:
        return SupervisorHealth.TERMINAL
    age = float(now_wall_seconds) - heartbeat
    if age < -5.0 or age > float(max_heartbeat_age_seconds):
        return SupervisorHealth.STALE_HEARTBEAT
    if diagnostic is not ProcessDiagnostic.MATCH:
        return SupervisorHealth.PROCESS_MISMATCH
    return SupervisorHealth.HEALTHY


def classify_recovery(
    assignment_phase: AssignmentPhase | str,
    lifecycle: LifecyclePhase | str | None = None,
) -> RecoveryDecision:
    """Classify whether durable state permits another irreversible launch."""

    try:
        phase = AssignmentPhase(assignment_phase)
        life = LifecyclePhase(lifecycle) if lifecycle is not None else None
    except ValueError:
        return RecoveryDecision.FAIL_CLOSED
    if life in {LifecyclePhase.COMPLETED, LifecyclePhase.FAILED_CLOSED} or phase is AssignmentPhase.TERMINAL:
        return RecoveryDecision.ALREADY_TERMINAL
    if phase in {
        AssignmentPhase.CLEAN_BOUNDARY,
        AssignmentPhase.PREPARED,
        AssignmentPhase.RESULT_COMMITTED,
    }:
        return RecoveryDecision.SAFE_TO_RESUME
    return RecoveryDecision.FAIL_CLOSED


def detect_suspend_gap(
    previous: ClockSample,
    current: ClockSample,
    *,
    heartbeat_interval_seconds: float,
) -> bool:
    """Detect clock regression, suspend, or a materially missed heartbeat."""

    wall_delta = current.wall_seconds - previous.wall_seconds
    monotonic_delta = current.monotonic_seconds - previous.monotonic_seconds
    if wall_delta < 0 or monotonic_delta < 0:
        return True
    missed_limit = max(45.0, heartbeat_interval_seconds * 3.0)
    drift_limit = max(5.0, heartbeat_interval_seconds)
    return (
        wall_delta > missed_limit
        or monotonic_delta > missed_limit
        or abs(wall_delta - monotonic_delta) > drift_limit
    )


_STATUS_KEYS = frozenset(
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
    }
)
_LEASE_KEYS = frozenset(
    {
        "schema_version",
        "lease_epoch",
        "execution_context_sha256",
        "pid",
        "boot_identity_sha256",
        "process_birth_identity_sha256",
        "lifecycle",
        "assignment_phase",
        "heartbeat_sequence",
        "created_wall_unix_seconds",
        "heartbeat_wall_unix_seconds",
    }
)
_CONTROL_KEYS = frozenset(
    {
        "schema_version",
        "pause_after_current",
        "request_epoch",
        "requested_wall_unix_seconds",
    }
)


def _validate_status(status: Mapping[str, object]) -> None:
    try:
        lifecycle = LifecyclePhase(status.get("lifecycle"))
        phase = AssignmentPhase(status.get("assignment_phase"))
        failure = FailureCode(status.get("failure_code"))
    except ValueError:
        raise IntegrityError("Supervisor status contains an invalid enum") from None
    integers = (
        status.get("pid"),
        status.get("heartbeat_sequence"),
        status.get("heartbeat_wall_unix_seconds"),
        status.get("completed_assignments"),
        status.get("total_assignments"),
    )
    if (
        status.get("schema_version") != SCHEMA_VERSION
        or not isinstance(status.get("lease_epoch"), str)
        or len(str(status.get("lease_epoch"))) != 64
        or not _valid_digest(status.get("execution_context_sha256"))
        or not _valid_digest(status.get("boot_identity_sha256"))
        or not _valid_digest(status.get("process_birth_identity_sha256"))
        or any(not isinstance(item, int) or item < 0 for item in integers)
        or status.get("pid") == 0
        or int(status.get("completed_assignments", -1)) > int(status.get("total_assignments", -1))
        or not isinstance(status.get("pause_after_current"), bool)
        or not isinstance(status.get("suspend_gap_detected"), bool)
    ):
        raise IntegrityError("Supervisor status failed closed-schema validation")
    ordinal = status.get("active_assignment_ordinal")
    if ordinal is not None and (not isinstance(ordinal, int) or ordinal <= 0):
        raise IntegrityError("Supervisor status contains an invalid active ordinal")
    if lifecycle is LifecyclePhase.FAILED_CLOSED and failure is FailureCode.NONE:
        raise IntegrityError("Failed-closed supervisor status lacks a failure code")
    if lifecycle is not LifecyclePhase.FAILED_CLOSED and failure is not FailureCode.NONE:
        raise IntegrityError("Nonterminal supervisor status contains a failure code")
    if lifecycle is LifecyclePhase.COMPLETED and phase is not AssignmentPhase.TERMINAL:
        raise IntegrityError("Completed supervisor status is not terminal")


def read_supervisor_status(
    runtime_dir: Path,
    *,
    authentication_key: bytes | Path,
) -> dict[str, object]:
    """Read and authenticate the finite, provider-content-free status record."""

    directory = _ensure_private_directory(Path(runtime_dir), create=False)
    key = _load_authentication_key(authentication_key)
    status = _open_record(
        directory / STATUS_FILE,
        record_type="status",
        key=key,
        expected_keys=_STATUS_KEYS,
    )
    _validate_status(status)
    return status


def read_supervisor_lease(
    runtime_dir: Path,
    *,
    authentication_key: bytes | Path,
) -> dict[str, object]:
    directory = _ensure_private_directory(Path(runtime_dir), create=False)
    key = _load_authentication_key(authentication_key)
    lease = _open_record(
        directory / LEASE_FILE,
        record_type="lease",
        key=key,
        expected_keys=_LEASE_KEYS,
    )
    if (
        lease.get("schema_version") != SCHEMA_VERSION
        or not isinstance(lease.get("lease_epoch"), str)
        or len(str(lease.get("lease_epoch"))) != 64
        or not _valid_digest(lease.get("execution_context_sha256"))
        or not isinstance(lease.get("pid"), int)
        or int(lease.get("pid", 0)) <= 0
        or not _valid_digest(lease.get("boot_identity_sha256"))
        or not _valid_digest(lease.get("process_birth_identity_sha256"))
    ):
        raise IntegrityError("Supervisor lease failed closed-schema validation")
    try:
        LifecyclePhase(lease.get("lifecycle"))
        AssignmentPhase(lease.get("assignment_phase"))
    except ValueError:
        raise IntegrityError("Supervisor lease contains an invalid enum") from None
    return lease


def _write_control(runtime_dir: Path, key: bytes, requested: bool) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "pause_after_current": requested,
        "request_epoch": secrets.token_hex(32),
        "requested_wall_unix_seconds": int(time.time()),
    }
    _atomic_private_json(runtime_dir / CONTROL_FILE, _seal_record("control", payload, key))
    return payload


def request_supervisor_pause(
    runtime_dir: Path,
    *,
    authentication_key: bytes | Path,
) -> dict[str, object]:
    """Request a pause at the next clean assignment boundary."""

    directory = _ensure_private_directory(Path(runtime_dir), create=False)
    return _write_control(directory, _load_authentication_key(authentication_key), True)


def clear_supervisor_pause(
    runtime_dir: Path,
    *,
    authentication_key: bytes | Path,
) -> dict[str, object]:
    """Clear a pause request before deliberately resuming a paused job."""

    directory = _ensure_private_directory(Path(runtime_dir), create=False)
    return _write_control(directory, _load_authentication_key(authentication_key), False)


def _event_hash(payload: Mapping[str, object]) -> str:
    return "sha256:" + hashlib.sha256(_EVENT_HASH_DOMAIN + _canonical_bytes(payload)).hexdigest()


def _event_tag(payload: Mapping[str, object], key: bytes) -> str:
    return hmac.new(key, _EVENT_HMAC_DOMAIN + _canonical_bytes(payload), hashlib.sha256).hexdigest()


_EVENT_BODY_KEYS = frozenset(
    {
        "schema_version",
        "lease_epoch",
        "execution_context_sha256",
        "sequence",
        "event_type",
        "lifecycle",
        "assignment_phase",
        "completed_assignments",
        "total_assignments",
        "heartbeat_sequence",
        "wall_unix_seconds",
        "previous_sha256",
    }
)


def _verify_event_bytes(
    raw: bytes,
    *,
    key: bytes,
    max_event_records: int,
    max_event_log_bytes: int,
) -> tuple[dict[str, object], ...]:
    if len(raw) > max_event_log_bytes or (raw and not raw.endswith(b"\n")):
        raise IntegrityError("Supervisor event journal exceeds its size limit")
    lines = raw.splitlines()
    if len(lines) > max_event_records:
        raise IntegrityError("Supervisor event journal exceeds its record limit")
    records: list[dict[str, object]] = []
    previous = _ZERO_EVENT_HASH
    for sequence, line in enumerate(lines, start=1):
        if not line or len(line) > MAX_EVENT_LINE_BYTES:
            raise IntegrityError("Supervisor event journal contains an invalid line")
        try:
            record = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise IntegrityError("Supervisor event journal is invalid") from None
        if not isinstance(record, dict) or set(record) != {
            "body",
            "record_sha256",
            "authentication",
        }:
            raise IntegrityError("Supervisor event journal has an open schema")
        body = record.get("body")
        authentication = record.get("authentication")
        if (
            not isinstance(body, dict)
            or frozenset(body) != _EVENT_BODY_KEYS
            or body.get("schema_version") != SCHEMA_VERSION
            or not isinstance(body.get("lease_epoch"), str)
            or len(str(body.get("lease_epoch"))) != 64
            or not _valid_digest(body.get("execution_context_sha256"))
            or body.get("sequence") != sequence
            or body.get("previous_sha256") != previous
            or not isinstance(authentication, dict)
            or set(authentication) != {"algorithm", "tag"}
            or authentication.get("algorithm") != "hmac-sha256"
        ):
            raise IntegrityError("Supervisor event journal failed schema validation")
        try:
            EventType(body.get("event_type"))
            LifecyclePhase(body.get("lifecycle"))
            AssignmentPhase(body.get("assignment_phase"))
        except ValueError:
            raise IntegrityError("Supervisor event journal contains an invalid enum") from None
        expected_hash = _event_hash(body)
        signed = {"body": body, "record_sha256": expected_hash}
        supplied_tag = authentication.get("tag")
        if (
            record.get("record_sha256") != expected_hash
            or not isinstance(supplied_tag, str)
            or not hmac.compare_digest(supplied_tag, _event_tag(signed, key))
        ):
            raise IntegrityError("Supervisor event journal authentication failed")
        for name in (
            "completed_assignments",
            "total_assignments",
            "heartbeat_sequence",
            "wall_unix_seconds",
        ):
            if (
                not isinstance(body.get(name), int)
                or isinstance(body.get(name), bool)
                or int(body[name]) < 0
            ):
                raise IntegrityError("Supervisor event journal contains an invalid count")
        previous = expected_hash
        records.append(record)
    return tuple(records)


def verify_event_log(
    runtime_dir: Path,
    *,
    authentication_key: bytes | Path,
    max_event_records: int = DEFAULT_MAX_EVENT_RECORDS,
    max_event_log_bytes: int = DEFAULT_MAX_EVENT_LOG_BYTES,
) -> tuple[dict[str, object], ...]:
    """Verify the bounded closed-schema HMAC/hash-chain event journal."""

    directory = _ensure_private_directory(Path(runtime_dir), create=False)
    key = _load_authentication_key(authentication_key)
    path = directory / EVENT_FILE
    if not path.exists() and not path.is_symlink():
        return ()
    metadata = _validate_private_file(path, maximum_bytes=max_event_log_bytes)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            opened = os.fstat(stream.fileno())
            if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
                raise IntegrityError("Supervisor event journal changed while opening")
            raw = stream.read(max_event_log_bytes + 1)
    except OSError:
        raise IntegrityError("Supervisor event journal is unavailable") from None
    if len(raw) != metadata.st_size:
        raise IntegrityError("Supervisor event journal exceeds its size limit")
    return _verify_event_bytes(
        raw,
        key=key,
        max_event_records=max_event_records,
        max_event_log_bytes=max_event_log_bytes,
    )


class _SupervisorLock:
    def __init__(self, runtime_dir: Path):
        self._path = runtime_dir / LOCK_FILE
        self._descriptor: int | None = None

    def __enter__(self) -> "_SupervisorLock":
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor: int | None = None
        try:
            descriptor = os.open(self._path, flags, 0o600)
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_uid != os.geteuid()
                or opened.st_nlink != 1
                or opened.st_mode & 0o077
            ):
                raise IntegrityError("Unsafe supervisor lock file")
            os.fchmod(descriptor, 0o600)
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            if descriptor is not None:
                os.close(descriptor)
            raise SupervisorBusyError("Another persistent supervisor holds the lease") from None
        except IntegrityError:
            if descriptor is not None:
                os.close(descriptor)
            raise
        except OSError:
            if descriptor is not None:
                os.close(descriptor)
            raise IntegrityError("Unable to acquire the persistent supervisor lock") from None
        assert descriptor is not None
        self._descriptor = descriptor
        return self

    def __exit__(self, *_: object) -> None:
        if self._descriptor is not None:
            os.close(self._descriptor)
            self._descriptor = None


class _SubprocessRunningCommand:
    def __init__(self, process: subprocess.Popen[bytes]):
        self._process = process

    def poll(self) -> int | None:
        return self._process.poll()

    def terminate(self) -> None:
        if self._process.poll() is None:
            try:
                os.killpg(self._process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    def kill(self) -> None:
        if self._process.poll() is None:
            try:
                os.killpg(self._process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


class SubprocessCommandRunner:
    """In-memory argv/environment adapter with output discarded by default."""

    def __init__(self, runner_argv: Sequence[str], environment: Mapping[str, str]):
        argv = tuple(runner_argv)
        if (
            not argv
            or any(not isinstance(item, str) or not item or "\x00" in item for item in argv)
            or any(
                not isinstance(key, str)
                or not isinstance(value, str)
                or "\x00" in key
                or "\x00" in value
                for key, value in environment.items()
            )
        ):
            raise ValueError("Runner command or environment is invalid")
        self._argv = argv
        self._environment = dict(environment)

    def start(self) -> RunningCommand:
        process = subprocess.Popen(
            self._argv,
            env=self._environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            start_new_session=True,
        )
        return _SubprocessRunningCommand(process)


class PersistentSupervisor:
    """Own one private authenticated runtime and execute commands at most once."""

    def __init__(
        self,
        runtime_dir: Path,
        authentication_key: bytes | Path,
        *,
        execution_context_sha256: str,
        heartbeat_interval_seconds: float = DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
        max_event_records: int = DEFAULT_MAX_EVENT_RECORDS,
        max_event_log_bytes: int = DEFAULT_MAX_EVENT_LOG_BYTES,
        wall_clock: Callable[[], float] = time.time,
        monotonic_clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        process_identity: ProcessIdentity | None = None,
    ):
        if not MIN_HEARTBEAT_INTERVAL_SECONDS <= heartbeat_interval_seconds <= MAX_HEARTBEAT_INTERVAL_SECONDS:
            raise ValueError("Heartbeat interval must be between 10 and 30 seconds")
        if max_event_records < 16 or max_event_log_bytes < 16 * MAX_EVENT_LINE_BYTES:
            raise ValueError("Supervisor event journal bounds are too small")
        self.runtime_dir = _ensure_private_directory(Path(runtime_dir), create=True)
        self._key = _load_authentication_key(authentication_key)
        if not _valid_digest(execution_context_sha256):
            raise ValueError("Execution context must be a SHA-256 digest")
        self._execution_context_sha256 = execution_context_sha256
        self.heartbeat_interval_seconds = float(heartbeat_interval_seconds)
        self.max_event_records = int(max_event_records)
        self.max_event_log_bytes = int(max_event_log_bytes)
        self._wall_clock = wall_clock
        self._monotonic_clock = monotonic_clock
        self._sleep = sleep
        self._identity = process_identity or current_process_identity()
        if (
            self._identity.pid <= 0
            or not _valid_digest(self._identity.boot_identity_sha256)
            or not _valid_digest(self._identity.process_birth_identity_sha256)
        ):
            raise ValueError("Injected process identity is invalid")
        self._lease_epoch = secrets.token_hex(32)
        self._heartbeat_sequence = 0
        self._created_wall_seconds = int(self._wall_clock())
        self._last_sample = ClockSample(self._wall_clock(), self._monotonic_clock())
        self._last_heartbeat_monotonic = self._last_sample.monotonic_seconds
        self._event_records: tuple[dict[str, object], ...] = ()
        self._status: dict[str, object] | None = None

    def _write_status(self) -> None:
        assert self._status is not None
        _validate_status(self._status)
        _atomic_private_json(
            self.runtime_dir / STATUS_FILE,
            _seal_record("status", self._status, self._key),
        )

    def _write_lease(self) -> None:
        assert self._status is not None
        lease: dict[str, object] = {
            "schema_version": SCHEMA_VERSION,
            "lease_epoch": self._lease_epoch,
            "execution_context_sha256": self._execution_context_sha256,
            "pid": self._identity.pid,
            "boot_identity_sha256": self._identity.boot_identity_sha256,
            "process_birth_identity_sha256": self._identity.process_birth_identity_sha256,
            "lifecycle": self._status["lifecycle"],
            "assignment_phase": self._status["assignment_phase"],
            "heartbeat_sequence": self._heartbeat_sequence,
            "created_wall_unix_seconds": self._created_wall_seconds,
            "heartbeat_wall_unix_seconds": int(self._wall_clock()),
        }
        _atomic_private_json(
            self.runtime_dir / LEASE_FILE,
            _seal_record("lease", lease, self._key),
        )

    def _append_event(self, event_type: EventType) -> None:
        path = self.runtime_dir / EVENT_FILE
        existed = path.exists() or path.is_symlink()
        flags = os.O_RDWR | os.O_APPEND
        if not existed:
            flags |= os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags, 0o600)
        except OSError:
            raise IntegrityError("Supervisor event journal changed before append") from None
        try:
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_uid != os.geteuid()
                or opened.st_nlink != 1
                or opened.st_mode & 0o077
                or opened.st_size > self.max_event_log_bytes
            ):
                raise IntegrityError("Unsafe supervisor event journal")
            os.fchmod(descriptor, 0o600)
            os.lseek(descriptor, 0, os.SEEK_SET)
            raw = os.read(descriptor, self.max_event_log_bytes + 1)
            if len(raw) != opened.st_size:
                raise IntegrityError("Supervisor event journal changed while reading")
            self._event_records = _verify_event_bytes(
                raw,
                key=self._key,
                max_event_records=self.max_event_records,
                max_event_log_bytes=self.max_event_log_bytes,
            )
            if len(self._event_records) >= self.max_event_records:
                raise IntegrityError("Supervisor event journal record limit reached")
            previous = (
                str(self._event_records[-1]["record_sha256"])
                if self._event_records
                else _ZERO_EVENT_HASH
            )
            assert self._status is not None
            body: dict[str, object] = {
                "schema_version": SCHEMA_VERSION,
                "lease_epoch": self._lease_epoch,
                "execution_context_sha256": self._execution_context_sha256,
                "sequence": len(self._event_records) + 1,
                "event_type": event_type.value,
                "lifecycle": self._status["lifecycle"],
                "assignment_phase": self._status["assignment_phase"],
                "completed_assignments": self._status["completed_assignments"],
                "total_assignments": self._status["total_assignments"],
                "heartbeat_sequence": self._heartbeat_sequence,
                "wall_unix_seconds": int(self._wall_clock()),
                "previous_sha256": previous,
            }
            record_hash = _event_hash(body)
            signed: dict[str, object] = {
                "body": body,
                "record_sha256": record_hash,
            }
            record = {
                **signed,
                "authentication": {
                    "algorithm": "hmac-sha256",
                    "tag": _event_tag(signed, self._key),
                },
            }
            payload = _canonical_bytes(record) + b"\n"
            if len(payload) > MAX_EVENT_LINE_BYTES:
                raise IntegrityError("Supervisor event record exceeds its size limit")
            if opened.st_size + len(payload) > self.max_event_log_bytes:
                raise IntegrityError("Supervisor event journal byte limit reached")
            written = os.write(descriptor, payload)
            if written != len(payload):
                raise IntegrityError("Supervisor event journal append was incomplete")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        self._event_records = (*self._event_records, record)

    def _load_control(self) -> bool:
        path = self.runtime_dir / CONTROL_FILE
        if not path.exists() and not path.is_symlink():
            return False
        control = _open_record(
            path,
            record_type="control",
            key=self._key,
            expected_keys=_CONTROL_KEYS,
        )
        if (
            control.get("schema_version") != SCHEMA_VERSION
            or not isinstance(control.get("pause_after_current"), bool)
            or not isinstance(control.get("request_epoch"), str)
            or len(str(control.get("request_epoch"))) != 64
            or not isinstance(control.get("requested_wall_unix_seconds"), int)
            or int(control.get("requested_wall_unix_seconds", -1)) < 0
        ):
            raise IntegrityError("Supervisor control record failed schema validation")
        return bool(control["pause_after_current"])

    def _transition(
        self,
        *,
        lifecycle: LifecyclePhase | None = None,
        assignment_phase: AssignmentPhase | None = None,
        failure_code: FailureCode | None = None,
        active_assignment_ordinal: int | None | object = ...,
        event: EventType | None = None,
    ) -> None:
        assert self._status is not None
        if lifecycle is not None:
            self._status["lifecycle"] = lifecycle.value
        if assignment_phase is not None:
            self._status["assignment_phase"] = assignment_phase.value
        if failure_code is not None:
            self._status["failure_code"] = failure_code.value
        if active_assignment_ordinal is not ...:
            self._status["active_assignment_ordinal"] = active_assignment_ordinal
        self._status["heartbeat_wall_unix_seconds"] = int(self._wall_clock())
        self._write_status()
        self._write_lease()
        if event is not None:
            self._append_event(event)

    def _heartbeat(self) -> bool:
        assert self._status is not None
        current = ClockSample(self._wall_clock(), self._monotonic_clock())
        suspended = detect_suspend_gap(
            self._last_sample,
            current,
            heartbeat_interval_seconds=self.heartbeat_interval_seconds,
        )
        self._last_sample = current
        self._last_heartbeat_monotonic = current.monotonic_seconds
        self._heartbeat_sequence += 1
        self._status["heartbeat_sequence"] = self._heartbeat_sequence
        self._status["heartbeat_wall_unix_seconds"] = int(current.wall_seconds)
        if suspended:
            self._status["suspend_gap_detected"] = True
        self._write_status()
        self._write_lease()
        return suspended

    def _fail_closed(self, code: FailureCode, *, event: EventType = EventType.FAILED_CLOSED) -> None:
        assert self._status is not None
        self._status["lifecycle"] = LifecyclePhase.FAILED_CLOSED.value
        self._status["assignment_phase"] = AssignmentPhase.TERMINAL_AMBIGUITY.value
        self._status["failure_code"] = code.value
        self._status["active_assignment_ordinal"] = None
        self._status["heartbeat_wall_unix_seconds"] = int(self._wall_clock())
        self._write_status()
        self._write_lease()
        try:
            self._append_event(event)
            if event is not EventType.FAILED_CLOSED:
                self._append_event(EventType.FAILED_CLOSED)
        except IntegrityError:
            # The authenticated terminal status remains authoritative when the
            # bounded journal itself is the incident.
            pass

    def _terminate_ambiguous_command(self, command: RunningCommand) -> None:
        try:
            command.terminate()
        except BaseException:
            return
        # Fixed iterations keep cleanup bounded even when a fault-injection
        # clock is frozen or the host monotonic clock becomes unavailable.
        for _ in range(50):
            try:
                if command.poll() is not None:
                    return
            except BaseException:
                return
            self._sleep(0.1)
        try:
            command.kill()
        except BaseException:
            pass

    def status(self) -> dict[str, object]:
        if self._status is None:
            raise SupervisorError("Persistent supervisor has not started")
        return dict(self._status)

    def request_pause(self) -> dict[str, object]:
        """Request pause using this supervisor's already-loaded key."""

        return _write_control(self.runtime_dir, self._key, True)

    def run(
        self,
        command_runner: CommandRunner | Sequence[CommandRunner],
    ) -> dict[str, object]:
        """Run one or more commands, pausing only between successful commands.

        A sequence is useful for offline soak/fault-injection tests and for a
        future per-assignment adapter.  ``run_supervised_panel`` supplies a
        single command because the current matched-panel executable owns its
        internal assignment loop and checkpoint protocol.
        """

        if isinstance(command_runner, CommandRunner):
            runners = (command_runner,)
        else:
            runners = tuple(command_runner)
        if not runners or any(not isinstance(item, CommandRunner) for item in runners):
            raise ValueError("At least one valid command runner is required")
        with _SupervisorLock(self.runtime_dir):
            prior: dict[str, object] | None = None
            status_path = self.runtime_dir / STATUS_FILE
            lease_path = self.runtime_dir / LEASE_FILE
            status_exists = status_path.exists() or status_path.is_symlink()
            lease_exists = lease_path.exists() or lease_path.is_symlink()
            if status_exists != lease_exists:
                raise IntegrityError("Supervisor status and lease are incomplete")
            if status_exists:
                prior = read_supervisor_status(
                    self.runtime_dir, authentication_key=self._key
                )
                prior_lease = read_supervisor_lease(
                    self.runtime_dir, authentication_key=self._key
                )
                matching_fields = (
                    "lease_epoch",
                    "execution_context_sha256",
                    "pid",
                    "boot_identity_sha256",
                    "process_birth_identity_sha256",
                    "lifecycle",
                    "assignment_phase",
                    "heartbeat_sequence",
                )
                if any(
                    prior.get(field) != prior_lease.get(field)
                    for field in matching_fields
                ):
                    raise IntegrityError("Supervisor status and lease do not match")
                prior_context = prior.get("execution_context_sha256")
                if not isinstance(prior_context, str) or not hmac.compare_digest(
                    prior_context, self._execution_context_sha256
                ):
                    raise UnsafeRecoveryError(
                        "Supervisor execution context does not match"
                    )
                decision = classify_recovery(
                    str(prior["assignment_phase"]), str(prior["lifecycle"])
                )
                if decision is RecoveryDecision.ALREADY_TERMINAL:
                    if prior["lifecycle"] == LifecyclePhase.COMPLETED.value:
                        return prior
                    raise UnsafeRecoveryError("Prior supervisor state is terminal")
                if decision is RecoveryDecision.FAIL_CLOSED:
                    self._status = dict(prior)
                    self._lease_epoch = secrets.token_hex(32)
                    self._status["lease_epoch"] = self._lease_epoch
                    self._status["pid"] = self._identity.pid
                    self._status["boot_identity_sha256"] = (
                        self._identity.boot_identity_sha256
                    )
                    self._status["process_birth_identity_sha256"] = (
                        self._identity.process_birth_identity_sha256
                    )
                    self._heartbeat_sequence = 0
                    self._status["heartbeat_sequence"] = 0
                    self._fail_closed(FailureCode.UNSAFE_RECOVERY)
                    raise UnsafeRecoveryError(
                        "Prior launch commitment makes automatic retry unsafe"
                    )
                if int(prior["total_assignments"]) != len(runners):
                    raise UnsafeRecoveryError("Runner count changed across recovery")
                completed = int(prior["completed_assignments"])
            else:
                completed = 0
            now = int(self._wall_clock())
            self._status = {
                "schema_version": SCHEMA_VERSION,
                "lease_epoch": self._lease_epoch,
                "execution_context_sha256": self._execution_context_sha256,
                "lifecycle": LifecyclePhase.INITIALIZING.value,
                "assignment_phase": AssignmentPhase.CLEAN_BOUNDARY.value,
                "pid": self._identity.pid,
                "boot_identity_sha256": self._identity.boot_identity_sha256,
                "process_birth_identity_sha256": self._identity.process_birth_identity_sha256,
                "heartbeat_sequence": self._heartbeat_sequence,
                "heartbeat_wall_unix_seconds": now,
                "completed_assignments": completed,
                "total_assignments": len(runners),
                "active_assignment_ordinal": None,
                "pause_after_current": False,
                "suspend_gap_detected": False,
                "failure_code": FailureCode.NONE.value,
            }
            self._write_status()
            self._write_lease()
            self._append_event(
                EventType.RECOVERY_ACCEPTED if prior is not None else EventType.LEASE_ACQUIRED
            )
            self._transition(lifecycle=LifecyclePhase.RUNNING)
            for index in range(completed, len(runners)):
                try:
                    pause_requested = self._load_control()
                except IntegrityError:
                    self._fail_closed(FailureCode.INTEGRITY)
                    raise
                self._status["pause_after_current"] = pause_requested
                if pause_requested:
                    self._transition(
                        lifecycle=LifecyclePhase.PAUSED,
                        assignment_phase=AssignmentPhase.CLEAN_BOUNDARY,
                        active_assignment_ordinal=None,
                        event=EventType.PAUSED,
                    )
                    return self.status()
                ordinal = index + 1
                self._transition(
                    assignment_phase=AssignmentPhase.PREPARED,
                    active_assignment_ordinal=ordinal,
                    event=EventType.ASSIGNMENT_PREPARED,
                )
                # This is the at-most-once point: any crash after this durable
                # transition is ambiguous and classify_recovery fails closed.
                self._transition(
                    assignment_phase=AssignmentPhase.LAUNCH_COMMITTED,
                    event=EventType.LAUNCH_COMMITTED,
                )
                try:
                    running = runners[index].start()
                    if not isinstance(running, RunningCommand):
                        raise TypeError
                except BaseException:
                    self._fail_closed(FailureCode.RUNNER_START)
                    raise RunnerFailedError("Runner failed after launch commitment") from None
                try:
                    self._transition(
                        assignment_phase=AssignmentPhase.RUNNING,
                        event=EventType.COMMAND_STARTED,
                    )
                    while True:
                        try:
                            return_code = running.poll()
                        except BaseException:
                            self._terminate_ambiguous_command(running)
                            self._fail_closed(FailureCode.RUNNER_PROTOCOL)
                            raise RunnerFailedError("Running command protocol failed") from None
                        if return_code is not None:
                            break
                        pause_requested = self._load_control()
                        if pause_requested and not self._status["pause_after_current"]:
                            self._status["pause_after_current"] = True
                            self._transition(
                                lifecycle=LifecyclePhase.PAUSE_REQUESTED,
                                event=EventType.PAUSE_REQUESTED,
                            )
                        observed = self._monotonic_clock()
                        if observed - self._last_heartbeat_monotonic >= self.heartbeat_interval_seconds:
                            if self._heartbeat():
                                self._terminate_ambiguous_command(running)
                                self._fail_closed(
                                    FailureCode.SUSPEND_GAP,
                                    event=EventType.SUSPEND_GAP_DETECTED,
                                )
                                raise RunnerFailedError("Suspend gap forced fail-closed stop")
                        self._sleep(min(1.0, self.heartbeat_interval_seconds / 4.0))
                    if not isinstance(return_code, int) or isinstance(return_code, bool):
                        self._fail_closed(FailureCode.RUNNER_PROTOCOL)
                        raise RunnerFailedError("Running command returned an invalid result")
                    if return_code != 0:
                        self._fail_closed(FailureCode.RUNNER_EXIT)
                        raise RunnerFailedError("Runner exited unsuccessfully")
                    self._status["completed_assignments"] = ordinal
                    self._transition(
                        assignment_phase=AssignmentPhase.RESULT_COMMITTED,
                        active_assignment_ordinal=None,
                    )
                    self._transition(
                        assignment_phase=AssignmentPhase.CLEAN_BOUNDARY,
                        event=EventType.ASSIGNMENT_COMPLETED,
                    )
                except BaseException as error:
                    self._terminate_ambiguous_command(running)
                    if self._status["lifecycle"] != LifecyclePhase.FAILED_CLOSED.value:
                        code = (
                            FailureCode.INTEGRITY
                            if isinstance(error, IntegrityError)
                            else FailureCode.SUPERVISOR_INTERNAL
                        )
                        try:
                            self._fail_closed(code)
                        except BaseException:
                            pass
                    raise
                try:
                    pause_requested = self._load_control()
                except IntegrityError:
                    self._fail_closed(FailureCode.INTEGRITY)
                    raise
                self._status["pause_after_current"] = pause_requested
                if pause_requested and ordinal < len(runners):
                    self._transition(
                        lifecycle=LifecyclePhase.PAUSED,
                        assignment_phase=AssignmentPhase.CLEAN_BOUNDARY,
                        event=EventType.PAUSED,
                    )
                    return self.status()
            self._status["pause_after_current"] = False
            self._transition(
                lifecycle=LifecyclePhase.COMPLETED,
                assignment_phase=AssignmentPhase.TERMINAL,
                failure_code=FailureCode.NONE,
                active_assignment_ordinal=None,
                event=EventType.COMPLETED,
            )
            return self.status()


def run_supervised_panel(
    *,
    runner_argv: Sequence[str],
    environment: Mapping[str, str],
    runtime_dir: Path,
    authentication_key: bytes | Path,
    execution_context_sha256: str,
    heartbeat_interval_seconds: float = DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    command_runner: CommandRunner | None = None,
) -> Mapping[str, object]:
    """Run the current panel executable beneath a persistent supervisor.

    Neither ``runner_argv`` nor ``environment`` is serialized, hashed, placed
    in an exception, or included in an event.  An injected runner is intended
    for offline testing; when supplied, argv/environment are only validated by
    the caller's adapter and are otherwise ignored.
    """

    runner = command_runner or SubprocessCommandRunner(runner_argv, environment)
    supervisor = PersistentSupervisor(
        runtime_dir,
        authentication_key,
        execution_context_sha256=execution_context_sha256,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
    )
    return supervisor.run(runner)


def run_supervised_command(
    *,
    runtime_dir: Path,
    operation: str,
    command: Sequence[str],
    child_environment: Mapping[str, str],
    authentication_key: bytes | Path,
    execution_context_sha256: str,
    heartbeat_interval_seconds: float = DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
) -> int:
    """Compatibility adapter for the owner-scoped launchd worker.

    ``operation`` is validated but deliberately not persisted.  The launchd
    adapter must explicitly provide its owner-only benchmark authentication
    key; the supervisor never invents or discovers credentials.
    """

    if operation not in {"preflight", "production"}:
        raise ValueError("Supervisor operation is invalid")
    directory = _ensure_private_directory(Path(runtime_dir), create=False)
    status = run_supervised_panel(
        runner_argv=command,
        environment=child_environment,
        runtime_dir=directory,
        authentication_key=authentication_key,
        execution_context_sha256=execution_context_sha256,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
    )
    return 0 if status.get("lifecycle") == LifecyclePhase.COMPLETED.value else 75


__all__ = [
    "AssignmentPhase",
    "ClockSample",
    "CommandRunner",
    "FailureCode",
    "IntegrityError",
    "LifecyclePhase",
    "PersistentSupervisor",
    "ProcessDiagnostic",
    "ProcessIdentity",
    "RecoveryDecision",
    "RunnerFailedError",
    "RunningCommand",
    "SubprocessCommandRunner",
    "SupervisorBusyError",
    "SupervisorError",
    "SupervisorHealth",
    "UnsafeRecoveryError",
    "classify_recovery",
    "classify_supervisor_health",
    "clear_supervisor_pause",
    "compute_execution_context_sha256",
    "current_process_identity",
    "detect_suspend_gap",
    "diagnose_supervisor_process",
    "read_supervisor_lease",
    "read_supervisor_status",
    "request_supervisor_pause",
    "run_supervised_panel",
    "run_supervised_command",
    "verify_event_log",
]
