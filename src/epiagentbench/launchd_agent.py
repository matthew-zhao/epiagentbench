"""Owner-scoped, one-shot macOS LaunchAgent support for long panel runs.

The launchd property list intentionally contains only the path to an owner-only
configuration file.  In particular, it never contains credentials, provider
environment variables, panel arguments, or log paths.  The worker resolves the
Cursor credential from Keychain after launch and passes it to the supervised
child in memory.

This module does not automatically install or start anything.  The explicit
``install_launch_agent`` and ``start_launch_agent`` functions are the only
entry points which call ``launchctl``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import plistlib
import pwd
import re
import fcntl
import stat
import subprocess
import sys
import tempfile
import time
from enum import StrEnum
from pathlib import Path
from secrets import token_hex
from typing import Any, Callable, Mapping, Sequence
from functools import wraps


_SCHEMA = "epiagentbench.launchd_agent.v4"
_WORKER_STATUS_SCHEMA = "epiagentbench.launchd_worker_status.v3"
_LABEL_PREFIX = "org.epiagentbench.panel"
_OPERATIONS = frozenset({"preflight", "production"})
_CAFFEINATE = Path("/usr/bin/caffeinate")
_SECURITY = Path("/usr/bin/security")
_LAUNCHCTL = Path("/bin/launchctl")
_CONFIG_NAME = "config.json"
_STATUS_NAME = "launchd-worker-status.json"
_START_MARKER_NAME = "launchd-start-request.json"
_CONTROL_LOCK_NAME = "launchd-control.lock"
_CONFIG_AUTH_DOMAIN = b"epiagentbench:launchd-config:v4\x00"
_WORKER_STATUS_AUTH_DOMAIN = b"epiagentbench:launchd-worker-status:v3\x00"
_START_MARKER_AUTH_DOMAIN = b"epiagentbench:launchd-start-request:v1\x00"
_START_MARKER_SCHEMA = "epiagentbench.launchd_start_request.v1"
_MAX_CONFIG_BYTES = 64 * 1024
_MAX_STATUS_BYTES = 16 * 1024
_MAX_AUTHENTICATION_KEY_BYTES = 4096
_KEYCHAIN_TIMEOUT_SECONDS = 15
_LAUNCHCTL_TIMEOUT_SECONDS = 15
_ATTESTATION_STARTUP_TIMEOUT_SECONDS = 5.0
_PROTOCOL_VERSION = "persistent-supervisor-v1"
_SAFE_NAME = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9_.@+-]{0,127}\Z")
_TOKEN = re.compile(r"\A[0-9a-f]{24}\Z")
_SHA256 = re.compile(r"\Asha256:[0-9a-f]{64}\Z")
_SAFE_ENVIRONMENT_KEYS = (
    "HOME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "LOGNAME",
    "PATH",
    "PYTHONPATH",
    "SHELL",
    "TMPDIR",
    "USER",
)
_LAUNCHD_AGENT_SOURCE = Path("src/epiagentbench/launchd_agent.py")
_PERSISTENT_SUPERVISOR_SOURCE = Path(
    "src/epiagentbench/persistent_supervisor.py"
)
_DEVELOPMENT_MATCHED_PANEL_SOURCE = Path(
    "src/epiagentbench/development_matched_panel.py"
)


CommandRunner = Callable[..., subprocess.CompletedProcess[bytes]]


class LaunchAgentError(ValueError):
    """A deliberately non-sensitive launch-agent validation/control error."""


class _TransientCoreStatusError(RuntimeError):
    """An authenticated status/lease pair is between atomic replacements."""


class _LaunchctlOutcome(StrEnum):
    SUCCESS = "success"
    NOT_FOUND = "not_found"
    FAILED = "failed"


def _public_errors(function: Callable[..., Any]) -> Callable[..., Any]:
    """Normalize public failures without ever forwarding subprocess detail."""

    @wraps(function)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        try:
            return function(*args, **kwargs)
        except LaunchAgentError:
            raise LaunchAgentError("LaunchAgent operation was safely refused") from None
        except Exception:
            raise LaunchAgentError("LaunchAgent operation failed safely") from None

    return wrapped


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")


def _authentication_tag(
    domain: bytes,
    payload: Mapping[str, Any],
    authentication_key: bytes,
) -> str:
    return hmac.new(
        authentication_key,
        domain + _canonical_bytes(payload),
        hashlib.sha256,
    ).hexdigest()


def _seal_payload(
    domain: bytes,
    payload: Mapping[str, Any],
    authentication_key: bytes,
) -> dict[str, Any]:
    return {
        **payload,
        "authentication": {
            "algorithm": "hmac-sha256",
            "tag": _authentication_tag(domain, payload, authentication_key),
        },
    }


def _open_payload(
    domain: bytes,
    record: object,
    authentication_key: bytes,
) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise ValueError("Authenticated launch-agent record is invalid")
    unsigned = dict(record)
    authentication = unsigned.pop("authentication", None)
    if (
        not isinstance(authentication, dict)
        or set(authentication) != {"algorithm", "tag"}
        or authentication.get("algorithm") != "hmac-sha256"
        or not isinstance(authentication.get("tag"), str)
        or len(authentication["tag"]) != 64
        or not hmac.compare_digest(
            authentication["tag"],
            _authentication_tag(domain, unsigned, authentication_key),
        )
    ):
        raise ValueError("Authenticated launch-agent record failed verification")
    return unsigned


def _absolute(path: Path | str, *, label: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        raise ValueError(f"{label} must be absolute")
    return candidate


def _lstat_path_without_links(path: Path, *, allow_missing_leaf: bool = False) -> os.stat_result | None:
    """lstat every component and reject symlink traversal."""

    current = Path(path.anchor)
    parts = path.parts[1:]
    for index, part in enumerate(parts):
        current = current / part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            if allow_missing_leaf and index == len(parts) - 1:
                return None
            raise ValueError(f"Required path does not exist: {path}") from None
        except OSError:
            raise ValueError(f"Unable to inspect required path: {path}") from None
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError(f"Path must not contain symlinks: {path}")
    return path.lstat()


def _require_directory(
    path: Path,
    *,
    label: str,
    exact_mode: int | None = None,
    require_current_owner: bool = True,
) -> None:
    metadata = _lstat_path_without_links(path)
    assert metadata is not None
    if not stat.S_ISDIR(metadata.st_mode):
        raise ValueError(f"{label} must be a real directory")
    if require_current_owner and metadata.st_uid != os.getuid():
        raise ValueError(f"{label} must be owned by the current user")
    mode = stat.S_IMODE(metadata.st_mode)
    if exact_mode is not None and mode != exact_mode:
        raise ValueError(f"{label} must have exact {exact_mode:04o} permissions")
    if exact_mode is None and mode & 0o002:
        raise ValueError(f"{label} must not be world-writable")


def _require_regular(
    path: Path,
    *,
    label: str,
    exact_mode: int | None = None,
    allowed_owners: frozenset[int] | None = None,
    executable: bool = False,
) -> None:
    metadata = _lstat_path_without_links(path)
    assert metadata is not None
    owners = allowed_owners if allowed_owners is not None else frozenset({os.getuid()})
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise ValueError(f"{label} must be a single-link regular file")
    if metadata.st_uid not in owners:
        raise ValueError(f"{label} has unsafe ownership")
    mode = stat.S_IMODE(metadata.st_mode)
    if exact_mode is not None and mode != exact_mode:
        raise ValueError(f"{label} must have exact {exact_mode:04o} permissions")
    if exact_mode is None and mode & 0o002:
        raise ValueError(f"{label} must not be world-writable")
    if executable and not mode & 0o100:
        raise ValueError(f"{label} must be executable")


def _read_authentication_key(path: Path) -> bytes:
    """Read an owner-only benchmark key without following or racing links."""

    _require_regular(path, label="authentication key", exact_mode=0o600)
    before = path.lstat()
    if not 32 <= before.st_size <= _MAX_AUTHENTICATION_KEY_BYTES:
        raise ValueError("Authentication key has an invalid size")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            opened = os.fstat(stream.fileno())
            if (
                (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
                or opened.st_nlink != 1
                or opened.st_uid != os.getuid()
                or stat.S_IMODE(opened.st_mode) != 0o600
            ):
                raise ValueError("Authentication key changed while opening")
            key = stream.read(_MAX_AUTHENTICATION_KEY_BYTES + 1)
    except OSError:
        raise ValueError("Authentication key is unavailable") from None
    if len(key) != before.st_size:
        raise ValueError("Authentication key changed while reading")
    return key


def _read_bounded_json(path: Path, *, maximum_bytes: int, label: str) -> object:
    _require_regular(path, label=label)
    metadata = path.lstat()
    if not 0 < metadata.st_size <= maximum_bytes:
        raise ValueError(f"{label} has an invalid size")
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
                raise ValueError(f"{label} changed while opening")
            raw = stream.read(maximum_bytes + 1)
    except OSError:
        raise ValueError(f"{label} is unavailable") from None
    if len(raw) != metadata.st_size:
        raise ValueError(f"{label} changed while reading")
    try:
        return json.loads(raw)
    except (UnicodeError, json.JSONDecodeError):
        raise ValueError(f"{label} is invalid") from None


def _file_sha256(path: Path, *, maximum_bytes: int, label: str) -> str:
    _require_regular(path, label=label)
    metadata = path.lstat()
    if not 0 < metadata.st_size <= maximum_bytes:
        raise ValueError(f"{label} has an invalid size")
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
                raise ValueError(f"{label} changed while opening")
            digest = hashlib.sha256()
            total = 0
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > maximum_bytes:
                    raise ValueError(f"{label} exceeds its size limit")
                digest.update(chunk)
    except OSError:
        raise ValueError(f"{label} is unavailable") from None
    if total != metadata.st_size:
        raise ValueError(f"{label} changed while reading")
    return "sha256:" + digest.hexdigest()


def _runtime_module_sources(repository_root: Path) -> tuple[Path, Path, Path]:
    """Return the only module paths trusted by the persistent worker."""

    launchd_source = repository_root / _LAUNCHD_AGENT_SOURCE
    supervisor_source = repository_root / _PERSISTENT_SUPERVISOR_SOURCE
    benchmark_source = repository_root / _DEVELOPMENT_MATCHED_PANEL_SOURCE
    _require_regular(launchd_source, label="LaunchAgent module source")
    _require_regular(supervisor_source, label="persistent-supervisor module source")
    _require_regular(benchmark_source, label="matched-panel module source")
    return launchd_source, supervisor_source, benchmark_source


def _require_loaded_module_source(module_file: object, expected_path: Path) -> None:
    """Reject a same-name module imported from outside the frozen repository."""

    if not isinstance(module_file, str):
        raise ValueError("Runtime module lacks a source binding")
    observed_path = Path(module_file)
    if not observed_path.is_absolute() or observed_path != expected_path:
        raise ValueError("Runtime module source binding mismatch")


def _verify_frozen_runtime_sources(
    config: Mapping[str, Any],
) -> tuple[Path, Path, Path]:
    """Verify all execution modules without importing either child module.

    The worker calls this immediately before Keychain access and again at the
    core boundary.  It deliberately derives paths from ``repository_root``;
    authenticated configuration contains only their content digests, so it
    cannot redirect either import to an arbitrary file.
    """

    repository_root = Path(str(config["repository_root"]))
    launchd_source, supervisor_source, benchmark_source = (
        _runtime_module_sources(repository_root)
    )
    _require_loaded_module_source(__file__, launchd_source)
    if (
        _file_sha256(
            launchd_source,
            maximum_bytes=2 * 1024 * 1024,
            label="LaunchAgent module source",
        )
        != config["launchd_agent_source_sha256"]
        or _file_sha256(
            supervisor_source,
            maximum_bytes=2 * 1024 * 1024,
            label="persistent-supervisor module source",
        )
        != config["persistent_supervisor_source_sha256"]
        or _file_sha256(
            benchmark_source,
            maximum_bytes=4 * 1024 * 1024,
            label="matched-panel module source",
        )
        != config["development_matched_panel_source_sha256"]
    ):
        raise ValueError("LaunchAgent runtime-source binding mismatch")
    return launchd_source, supervisor_source, benchmark_source


def _manifest_binding(path: Path) -> tuple[str, str]:
    manifest = _read_bounded_json(
        path,
        maximum_bytes=64 * 1024 * 1024,
        label="public manifest",
    )
    if not isinstance(manifest, dict):
        raise ValueError("Public manifest has an invalid schema")
    panel_id = manifest.get("panel_id")
    precommitment = manifest.get("precommitment_sha256")
    if (
        not isinstance(panel_id, str)
        or not _SAFE_NAME.fullmatch(panel_id)
        or not isinstance(precommitment, str)
        or not _SHA256.fullmatch(precommitment)
    ):
        raise ValueError("Public manifest lacks a valid panel binding")
    return panel_id, precommitment


def _require_output_path(path: Path, *, label: str) -> None:
    metadata = _lstat_path_without_links(path, allow_missing_leaf=True)
    if metadata is None:
        _require_directory(path.parent, label=f"{label} parent")
        return
    _require_regular(path, label=label)


def _safe_environment(repository_root: Path, path_environment: str | None) -> dict[str, str]:
    identity = pwd.getpwuid(os.getuid())
    path_value = path_environment if path_environment is not None else os.environ.get("PATH", "")
    if not path_value or "\x00" in path_value or any(
        not component or not Path(component).is_absolute()
        for component in path_value.split(os.pathsep)
    ):
        raise ValueError("PATH must be a non-empty list of absolute directories")
    environment = {
        "HOME": identity.pw_dir,
        "LOGNAME": identity.pw_name,
        "PATH": path_value,
        "PYTHONPATH": str(repository_root / "src"),
        "SHELL": identity.pw_shell or "/bin/zsh",
        "TMPDIR": tempfile.gettempdir(),
        "USER": identity.pw_name,
    }
    for key in ("LANG", "LC_ALL", "LC_CTYPE"):
        value = os.environ.get(key)
        if value and "\x00" not in value:
            environment[key] = value
    return environment


def _write_exclusive(path: Path, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError:
        raise RuntimeError(f"Refusing to replace launch-agent file: {path.name}") from None
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(descriptor)
    _require_regular(path, label=path.name, exact_mode=0o600)


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _worker_program_arguments(config: Mapping[str, Any]) -> list[str]:
    return [
        str(_CAFFEINATE),
        "-dimsu",
        str(config["python_executable"]),
        str(config["worker_script"]),
        "worker",
        "--config",
        str(config["config_path"]),
    ]


def _plist_payload(config: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "Label": config["label"],
        "ProgramArguments": _worker_program_arguments(config),
        "RunAtLoad": False,
        "KeepAlive": False,
        "ProcessType": "Background",
        "StandardOutPath": "/dev/null",
        "StandardErrorPath": "/dev/null",
        "Umask": 0o077,
    }


@_public_errors
def generate_launch_agent(
    *,
    operation: str,
    runtime_dir: Path,
    repository_root: Path,
    python_executable: Path,
    authentication_key_file: Path,
    claude_secure_storage_dir: Path,
    codex_secure_storage_dir: Path,
    private_state_path: Path,
    public_manifest_path: Path,
    cursor_keychain_service: str,
    cursor_keychain_account: str,
    public_preflight_path: Path | None = None,
    public_results_path: Path | None = None,
    path_environment: str | None = None,
    instance_token: str | None = None,
) -> dict[str, Any]:
    """Generate, but do not install, one finite one-shot LaunchAgent."""

    if operation not in _OPERATIONS:
        raise ValueError("operation must be exactly 'preflight' or 'production'")
    if not _SAFE_NAME.fullmatch(cursor_keychain_service):
        raise ValueError("Invalid Cursor Keychain service name")
    if not _SAFE_NAME.fullmatch(cursor_keychain_account):
        raise ValueError("Invalid Cursor Keychain account name")
    if instance_token is None:
        token = token_hex(12)
    else:
        if not isinstance(instance_token, str) or not _SAFE_NAME.fullmatch(instance_token):
            raise ValueError("instance_token must be a safe non-empty instance name")
        token = hashlib.sha256(instance_token.encode("ascii")).hexdigest()[:24]

    runtime = _absolute(runtime_dir, label="runtime directory")
    root = _absolute(repository_root, label="repository root")
    python = _absolute(python_executable, label="Python executable")
    auth_key = _absolute(authentication_key_file, label="authentication key")
    claude_storage = _absolute(
        claude_secure_storage_dir, label="Claude secure-storage directory"
    )
    codex_storage = _absolute(
        codex_secure_storage_dir, label="Codex secure-storage directory"
    )
    private_state = _absolute(private_state_path, label="private state")
    public_manifest = _absolute(public_manifest_path, label="public manifest")
    public_preflight = (
        None
        if public_preflight_path is None
        else _absolute(public_preflight_path, label="public preflight receipt")
    )
    public_results = (
        None
        if public_results_path is None
        else _absolute(public_results_path, label="public results")
    )
    if operation == "preflight" and (public_preflight is None or public_results is not None):
        raise ValueError("preflight requires only public_preflight_path")
    if operation == "production" and (public_results is None or public_preflight is not None):
        raise ValueError("production requires only public_results_path")

    _require_directory(root, label="repository root")
    _require_regular(
        python,
        label="Python executable",
        allowed_owners=frozenset({0, os.getuid()}),
        executable=True,
    )
    worker_script = root / "examples" / "run_persistent_panel_supervisor.py"
    runner_script = root / "examples" / "run_development_matched_panel.py"
    _require_regular(worker_script, label="persistent worker script")
    _require_regular(runner_script, label="frozen panel runner")
    _require_regular(auth_key, label="authentication key", exact_mode=0o600)
    _require_directory(claude_storage, label="Claude secure-storage directory", exact_mode=0o700)
    _require_directory(codex_storage, label="Codex secure-storage directory", exact_mode=0o700)
    _require_regular(private_state, label="private state", exact_mode=0o600)
    _require_regular(public_manifest, label="public manifest")
    authentication_key = _read_authentication_key(auth_key)
    panel_id, precommitment_sha256 = _manifest_binding(public_manifest)
    public_manifest_file_sha256 = _file_sha256(
        public_manifest,
        maximum_bytes=64 * 1024 * 1024,
        label="public manifest",
    )
    runner_source_sha256 = _file_sha256(
        runner_script,
        maximum_bytes=1024 * 1024,
        label="frozen panel runner",
    )
    worker_source_sha256 = _file_sha256(
        worker_script,
        maximum_bytes=1024 * 1024,
        label="persistent worker script",
    )
    (
        launchd_agent_source,
        persistent_supervisor_source,
        development_matched_panel_source,
    ) = _runtime_module_sources(root)
    _require_loaded_module_source(__file__, launchd_agent_source)
    launchd_agent_source_sha256 = _file_sha256(
        launchd_agent_source,
        maximum_bytes=2 * 1024 * 1024,
        label="LaunchAgent module source",
    )
    persistent_supervisor_source_sha256 = _file_sha256(
        persistent_supervisor_source,
        maximum_bytes=2 * 1024 * 1024,
        label="persistent-supervisor module source",
    )
    development_matched_panel_source_sha256 = _file_sha256(
        development_matched_panel_source,
        maximum_bytes=4 * 1024 * 1024,
        label="matched-panel module source",
    )
    import epiagentbench.persistent_supervisor as persistent_supervisor

    _require_loaded_module_source(
        persistent_supervisor.__file__,
        persistent_supervisor_source,
    )

    label = f"{_LABEL_PREFIX}.{os.getuid()}.{token}"
    execution_context_sha256 = persistent_supervisor.compute_execution_context_sha256(
        launchd_label=label,
        operation=operation,
        panel_id=panel_id,
        protocol_version=_PROTOCOL_VERSION,
        public_manifest_sha256=public_manifest_file_sha256,
        runner_source_sha256=runner_source_sha256,
        launchd_agent_source_sha256=launchd_agent_source_sha256,
        persistent_supervisor_source_sha256=(
            persistent_supervisor_source_sha256
        ),
        development_matched_panel_source_sha256=(
            development_matched_panel_source_sha256
        ),
    )
    output_path = public_preflight if public_preflight is not None else public_results
    assert output_path is not None
    _require_output_path(output_path, label="public output")
    _require_regular(
        _CAFFEINATE,
        label="caffeinate executable",
        allowed_owners=frozenset({0}),
        executable=True,
    )
    _require_regular(
        _SECURITY,
        label="security executable",
        allowed_owners=frozenset({0}),
        executable=True,
    )
    _require_directory(runtime.parent, label="runtime parent", exact_mode=0o700)
    if runtime.exists() or runtime.is_symlink():
        raise ValueError("runtime directory must not already exist")

    config_path = runtime / _CONFIG_NAME
    plist_path = runtime / f"{label}.plist"
    unsigned_config: dict[str, Any] = {
        "schema_version": _SCHEMA,
        "label": label,
        "uid": os.getuid(),
        "operation": operation,
        "panel_id": panel_id,
        "precommitment_sha256": precommitment_sha256,
        "protocol_version": _PROTOCOL_VERSION,
        "public_manifest_file_sha256": public_manifest_file_sha256,
        "runner_source_sha256": runner_source_sha256,
        "worker_source_sha256": worker_source_sha256,
        "launchd_agent_source_sha256": launchd_agent_source_sha256,
        "persistent_supervisor_source_sha256": (
            persistent_supervisor_source_sha256
        ),
        "development_matched_panel_source_sha256": (
            development_matched_panel_source_sha256
        ),
        "execution_context_sha256": execution_context_sha256,
        "runtime_dir": str(runtime),
        "config_path": str(config_path),
        "repository_root": str(root),
        "python_executable": str(python),
        "worker_script": str(worker_script),
        "runner_script": str(runner_script),
        "authentication_key_file": str(auth_key),
        "claude_secure_storage_dir": str(claude_storage),
        "codex_secure_storage_dir": str(codex_storage),
        "private_state_path": str(private_state),
        "public_manifest_path": str(public_manifest),
        "public_output_path": str(output_path),
        "cursor_keychain": {
            "service": cursor_keychain_service,
            "account": cursor_keychain_account,
        },
        "base_environment": _safe_environment(root, path_environment),
    }
    config = _seal_payload(_CONFIG_AUTH_DOMAIN, unsigned_config, authentication_key)
    old_umask = os.umask(0o077)
    try:
        os.mkdir(runtime, 0o700)
        os.chmod(runtime, 0o700)
        _write_exclusive(
            config_path,
            (json.dumps(config, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )
        _write_exclusive(
            plist_path,
            plistlib.dumps(_plist_payload(config), fmt=plistlib.FMT_XML, sort_keys=True),
        )
    except BaseException:
        # Files are intentionally left in place for forensic inspection.  A
        # subsequent generate must use a new private runtime directory.
        raise
    finally:
        os.umask(old_umask)
    summary = inspect_launch_agent(
        runtime,
        authentication_key_file=auth_key,
    )
    return {
        **summary,
        "operation": operation,
        "runtime_dir": str(runtime),
        "config_path": str(config_path),
        "plist_path": str(plist_path),
    }


def _load_and_validate(
    runtime_dir: Path,
    *,
    authentication_key_file: Path | None = None,
) -> tuple[dict[str, Any], Path, bytes]:
    runtime = _absolute(runtime_dir, label="runtime directory")
    _require_directory(runtime, label="runtime directory", exact_mode=0o700)
    config_path = runtime / _CONFIG_NAME
    _require_regular(config_path, label="launch-agent config", exact_mode=0o600)
    raw_config = _read_bounded_json(
        config_path,
        maximum_bytes=_MAX_CONFIG_BYTES,
        label="launch-agent config",
    )
    if not isinstance(raw_config, dict):
        raise ValueError("Invalid launch-agent config")
    expected_keys = {
        "schema_version",
        "label",
        "uid",
        "operation",
        "panel_id",
        "precommitment_sha256",
        "protocol_version",
        "public_manifest_file_sha256",
        "runner_source_sha256",
        "worker_source_sha256",
        "launchd_agent_source_sha256",
        "persistent_supervisor_source_sha256",
        "development_matched_panel_source_sha256",
        "execution_context_sha256",
        "runtime_dir",
        "config_path",
        "repository_root",
        "python_executable",
        "worker_script",
        "runner_script",
        "authentication_key_file",
        "claude_secure_storage_dir",
        "codex_secure_storage_dir",
        "private_state_path",
        "public_manifest_path",
        "public_output_path",
        "cursor_keychain",
        "base_environment",
        "authentication",
    }
    if set(raw_config) != expected_keys:
        raise ValueError("Invalid launch-agent config fields")
    configured_key_value = raw_config.get("authentication_key_file")
    if not isinstance(configured_key_value, str) or not Path(configured_key_value).is_absolute():
        raise ValueError("Invalid launch-agent authentication-key path")
    configured_key_path = Path(configured_key_value)
    if authentication_key_file is not None:
        supplied_key_path = _absolute(
            authentication_key_file,
            label="authentication key",
        )
        if supplied_key_path != configured_key_path:
            raise ValueError("Launch-agent authentication-key binding mismatch")
    authentication_key = _read_authentication_key(configured_key_path)
    config = _open_payload(_CONFIG_AUTH_DOMAIN, raw_config, authentication_key)
    if config["schema_version"] != _SCHEMA or config["uid"] != os.getuid():
        raise ValueError("Launch-agent config identity mismatch")
    if config["operation"] not in _OPERATIONS:
        raise ValueError("Invalid launch-agent operation")
    if (
        not isinstance(config["panel_id"], str)
        or not _SAFE_NAME.fullmatch(config["panel_id"])
        or not isinstance(config["precommitment_sha256"], str)
        or not _SHA256.fullmatch(config["precommitment_sha256"])
        or config["protocol_version"] != _PROTOCOL_VERSION
        or any(
            not isinstance(config[name], str) or not _SHA256.fullmatch(config[name])
            for name in (
                "public_manifest_file_sha256",
                "runner_source_sha256",
                "worker_source_sha256",
                "launchd_agent_source_sha256",
                "persistent_supervisor_source_sha256",
                "development_matched_panel_source_sha256",
                "execution_context_sha256",
            )
        )
    ):
        raise ValueError("Invalid launch-agent panel binding")
    if config["runtime_dir"] != str(runtime) or config["config_path"] != str(config_path):
        raise ValueError("Launch-agent config path mismatch")
    expected_label_prefix = f"{_LABEL_PREFIX}.{os.getuid()}."
    if not isinstance(config["label"], str) or not config["label"].startswith(expected_label_prefix):
        raise ValueError("Invalid launch-agent label")
    if not _TOKEN.fullmatch(config["label"][len(expected_label_prefix) :]):
        raise ValueError("Invalid launch-agent label token")
    keychain = config["cursor_keychain"]
    if (
        not isinstance(keychain, dict)
        or set(keychain) != {"service", "account"}
        or not all(isinstance(keychain[key], str) and _SAFE_NAME.fullmatch(keychain[key]) for key in keychain)
    ):
        raise ValueError("Invalid Cursor Keychain locator")
    environment = config["base_environment"]
    if (
        not isinstance(environment, dict)
        or not set(environment).issubset(_SAFE_ENVIRONMENT_KEYS)
        or not {"HOME", "LOGNAME", "PATH", "PYTHONPATH", "SHELL", "TMPDIR", "USER"}.issubset(environment)
        or any(not isinstance(value, str) or not value or "\x00" in value for value in environment.values())
    ):
        raise ValueError("Invalid worker environment")

    path_fields = (
        "repository_root",
        "python_executable",
        "worker_script",
        "runner_script",
        "authentication_key_file",
        "claude_secure_storage_dir",
        "codex_secure_storage_dir",
        "private_state_path",
        "public_manifest_path",
        "public_output_path",
    )
    if any(not isinstance(config[name], str) or not Path(config[name]).is_absolute() for name in path_fields):
        raise ValueError("Launch-agent config contains a non-absolute path")
    _require_directory(Path(config["repository_root"]), label="repository root")
    _require_regular(
        Path(config["python_executable"]),
        label="Python executable",
        allowed_owners=frozenset({0, os.getuid()}),
        executable=True,
    )
    _require_regular(Path(config["worker_script"]), label="persistent worker script")
    _require_regular(Path(config["runner_script"]), label="frozen panel runner")
    repository_root = Path(config["repository_root"])
    if (
        Path(config["worker_script"])
        != repository_root / "examples" / "run_persistent_panel_supervisor.py"
        or Path(config["runner_script"])
        != repository_root / "examples" / "run_development_matched_panel.py"
    ):
        raise ValueError("Launch-agent source binding mismatch")
    _require_regular(Path(config["authentication_key_file"]), label="authentication key", exact_mode=0o600)
    _require_directory(Path(config["claude_secure_storage_dir"]), label="Claude secure-storage directory", exact_mode=0o700)
    _require_directory(Path(config["codex_secure_storage_dir"]), label="Codex secure-storage directory", exact_mode=0o700)
    _require_regular(Path(config["private_state_path"]), label="private state", exact_mode=0o600)
    _require_regular(Path(config["public_manifest_path"]), label="public manifest")
    observed_panel_id, observed_precommitment = _manifest_binding(
        Path(config["public_manifest_path"])
    )
    if (
        observed_panel_id != config["panel_id"]
        or observed_precommitment != config["precommitment_sha256"]
    ):
        raise ValueError("Launch-agent manifest binding mismatch")
    if (
        _file_sha256(
            Path(config["public_manifest_path"]),
            maximum_bytes=64 * 1024 * 1024,
            label="public manifest",
        )
        != config["public_manifest_file_sha256"]
        or _file_sha256(
            Path(config["runner_script"]),
            maximum_bytes=1024 * 1024,
            label="frozen panel runner",
        )
        != config["runner_source_sha256"]
        or _file_sha256(
            Path(config["worker_script"]),
            maximum_bytes=1024 * 1024,
            label="persistent worker script",
        )
        != config["worker_source_sha256"]
    ):
        raise ValueError("Launch-agent source/content binding mismatch")
    _, persistent_supervisor_source, _ = _verify_frozen_runtime_sources(config)
    import epiagentbench.persistent_supervisor as persistent_supervisor

    _require_loaded_module_source(
        persistent_supervisor.__file__,
        persistent_supervisor_source,
    )

    expected_execution_context = persistent_supervisor.compute_execution_context_sha256(
        launchd_label=config["label"],
        operation=config["operation"],
        panel_id=config["panel_id"],
        protocol_version=config["protocol_version"],
        public_manifest_sha256=config["public_manifest_file_sha256"],
        runner_source_sha256=config["runner_source_sha256"],
        launchd_agent_source_sha256=config["launchd_agent_source_sha256"],
        persistent_supervisor_source_sha256=(
            config["persistent_supervisor_source_sha256"]
        ),
        development_matched_panel_source_sha256=(
            config["development_matched_panel_source_sha256"]
        ),
    )
    if config["execution_context_sha256"] != expected_execution_context:
        raise ValueError("Launch-agent execution-context binding mismatch")
    _require_output_path(Path(config["public_output_path"]), label="public output")

    plist_path = runtime / f"{config['label']}.plist"
    _require_regular(plist_path, label="launch-agent plist", exact_mode=0o600)
    try:
        plist = plistlib.loads(plist_path.read_bytes())
    except (OSError, plistlib.InvalidFileException):
        raise ValueError("Invalid launch-agent plist") from None
    if plist != _plist_payload(config):
        raise ValueError("Launch-agent plist does not match the frozen config")
    return config, plist_path, authentication_key


@_public_errors
def inspect_launch_agent(
    runtime_dir: Path,
    *,
    authentication_key_file: Path,
) -> dict[str, Any]:
    """Validate generated artifacts and return a non-sensitive summary."""

    config, plist_path, _ = _load_and_validate(
        runtime_dir,
        authentication_key_file=authentication_key_file,
    )
    return {
        "configured": True,
        "label": config["label"],
        "runtime_mode": "0700",
        "config_mode": "0600",
        "plist_mode": "0600",
    }


def _runner_command(config: Mapping[str, Any]) -> list[str]:
    runner_operation = "preflight" if config["operation"] == "preflight" else "run"
    command = [
        str(config["python_executable"]),
        str(config["runner_script"]),
        runner_operation,
        "--authentication-key",
        str(config["authentication_key_file"]),
        "--claude-secure-storage-dir",
        str(config["claude_secure_storage_dir"]),
        "--codex-secure-storage-dir",
        str(config["codex_secure_storage_dir"]),
        "--private-state",
        str(config["private_state_path"]),
        "--public-manifest",
        str(config["public_manifest_path"]),
        "--supervisor-runtime",
        str(config["runtime_dir"]),
    ]
    if config["operation"] == "preflight":
        command.extend(["--public-preflight", str(config["public_output_path"])])
    else:
        command.extend(["--public-results", str(config["public_output_path"])])
    command.append("--acknowledge-unbounded-provider-spend")
    return command


def _start_marker_payload(config: Mapping[str, Any]) -> dict[str, str]:
    return {
        "schema_version": _START_MARKER_SCHEMA,
        "label": str(config["label"]),
        "operation": str(config["operation"]),
        "panel_id": str(config["panel_id"]),
        "precommitment_sha256": str(config["precommitment_sha256"]),
        "execution_context_sha256": str(config["execution_context_sha256"]),
        "state": "start_requested",
    }


def _write_start_marker(
    runtime: Path,
    *,
    config: Mapping[str, Any],
    authentication_key: bytes,
) -> None:
    destination = runtime / _START_MARKER_NAME
    # Any prior leaf, including a symlink or malformed file, closes the
    # one-shot boundary.  It is never replaced or cleared after ambiguity.
    if destination.exists() or destination.is_symlink():
        raise RuntimeError("One-shot LaunchAgent start was already requested")
    record = _seal_payload(
        _START_MARKER_AUTH_DOMAIN,
        _start_marker_payload(config),
        authentication_key,
    )
    _write_exclusive(destination, _canonical_bytes(record) + b"\n")
    _fsync_directory(runtime)


def _read_start_marker(
    runtime: Path,
    *,
    config: Mapping[str, Any],
    authentication_key: bytes,
) -> dict[str, str] | None:
    path = runtime / _START_MARKER_NAME
    if not path.exists() and not path.is_symlink():
        return None
    _require_regular(path, label="launch-agent start marker", exact_mode=0o600)
    record = _read_bounded_json(
        path,
        maximum_bytes=_MAX_STATUS_BYTES,
        label="launch-agent start marker",
    )
    payload = _open_payload(
        _START_MARKER_AUTH_DOMAIN,
        record,
        authentication_key,
    )
    if payload != _start_marker_payload(config):
        raise ValueError("Invalid launch-agent start marker")
    return {key: str(value) for key, value in payload.items()}


def _atomic_worker_status(
    runtime: Path,
    *,
    config: Mapping[str, Any],
    authentication_key: bytes,
    state: str,
    reason: str | None = None,
) -> None:
    payload: dict[str, Any] = {
        "schema_version": _WORKER_STATUS_SCHEMA,
        "label": config["label"],
        "operation": config["operation"],
        "panel_id": config["panel_id"],
        "precommitment_sha256": config["precommitment_sha256"],
        "execution_context_sha256": config["execution_context_sha256"],
        "state": state,
    }
    if reason is not None:
        payload["reason"] = reason
    record = _seal_payload(
        _WORKER_STATUS_AUTH_DOMAIN,
        payload,
        authentication_key,
    )
    destination = runtime / _STATUS_NAME
    if destination.exists() or destination.is_symlink():
        _require_regular(destination, label="worker status", exact_mode=0o600)
    temporary = runtime / f".{_STATUS_NAME}.{token_hex(12)}"
    _write_exclusive(
        temporary,
        _canonical_bytes(record) + b"\n",
    )
    os.replace(temporary, destination)
    _require_regular(destination, label="worker status", exact_mode=0o600)


def _read_cursor_key(config: Mapping[str, Any], *, command_runner: CommandRunner = subprocess.run) -> str:
    locator = config["cursor_keychain"]
    try:
        completed = command_runner(
            [
                str(_SECURITY),
                "find-generic-password",
                "-a",
                locator["account"],
                "-s",
                locator["service"],
                "-w",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            env=dict(config["base_environment"]),
            timeout=_KEYCHAIN_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError("Cursor Keychain lookup failed") from None
    raw = completed.stdout.rstrip(b"\r\n") if completed.returncode == 0 else b""
    if not raw or len(raw) > 8192 or b"\x00" in raw:
        raise RuntimeError("Cursor Keychain lookup failed")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        raise RuntimeError("Cursor Keychain lookup failed") from None


def _run_core_supervisor(
    config: Mapping[str, Any],
    *,
    child_environment: Mapping[str, str],
    authentication_key: bytes,
) -> int:
    """Narrow adapter to the durable supervisor implementation."""

    _, persistent_supervisor_source, _ = _verify_frozen_runtime_sources(config)
    import epiagentbench.persistent_supervisor as persistent_supervisor

    _require_loaded_module_source(
        persistent_supervisor.__file__,
        persistent_supervisor_source,
    )

    return int(
        persistent_supervisor.run_supervised_command(
            runtime_dir=Path(config["runtime_dir"]),
            operation=str(config["operation"]),
            command=_runner_command(config),
            child_environment=dict(child_environment),
            authentication_key=authentication_key,
            execution_context_sha256=str(config["execution_context_sha256"]),
        )
    )


@_public_errors
def run_launch_agent_worker(
    config_path: Path,
    *,
    keychain_runner: CommandRunner = subprocess.run,
) -> int:
    """Run the one-shot worker.  This is called only by the LaunchAgent."""

    config_file = _absolute(config_path, label="config path")
    config, _, authentication_key = _load_and_validate(config_file.parent)
    if config_file != Path(config["config_path"]):
        raise ValueError("Worker config path mismatch")
    runtime = Path(config["runtime_dir"])
    if (
        _read_start_marker(
            runtime,
            config=config,
            authentication_key=authentication_key,
        )
        is None
    ):
        raise ValueError("Launch-agent worker lacks an authenticated start request")
    if (
        _worker_status(
            runtime,
            config=config,
            authentication_key=authentication_key,
        )
        is not None
    ):
        raise ValueError("Launch-agent worker is one-shot and already entered")
    old_umask = os.umask(0o077)
    try:
        _atomic_worker_status(
            runtime,
            config=config,
            authentication_key=authentication_key,
            state="starting",
        )
        # Re-hash the enforcement modules immediately before any provider
        # credential is retrieved.  This closes the validation-to-Keychain
        # window and fails without invoking ``security`` on mismatch.
        _verify_frozen_runtime_sources(config)
        try:
            cursor_key = _read_cursor_key(config, command_runner=keychain_runner)
        except RuntimeError:
            _atomic_worker_status(
                runtime,
                config=config,
                authentication_key=authentication_key,
                state="terminal_incident",
                reason="cursor_keychain_unavailable",
            )
            return 70
        environment = dict(config["base_environment"])
        environment["CURSOR_API_KEY"] = cursor_key
        _atomic_worker_status(
            runtime,
            config=config,
            authentication_key=authentication_key,
            state="supervisor_running",
        )
        try:
            return_code = _run_core_supervisor(
                config,
                child_environment=environment,
                authentication_key=authentication_key,
            )
        except Exception:
            _atomic_worker_status(
                runtime,
                config=config,
                authentication_key=authentication_key,
                state="terminal_incident",
                reason="supervisor_exception",
            )
            return 70
        finally:
            environment.pop("CURSOR_API_KEY", None)
            cursor_key = ""
        if return_code == 0:
            try:
                finalize_launch_agent(
                    runtime,
                    authentication_key_file=Path(
                        config["authentication_key_file"]
                    ),
                )
            except Exception:
                _atomic_worker_status(
                    runtime,
                    config=config,
                    authentication_key=authentication_key,
                    state="terminal_incident",
                    reason="release_validation_failed",
                )
                return 70
            return 0
        _atomic_worker_status(
            runtime,
            config=config,
            authentication_key=authentication_key,
            state="supervisor_exited",
            reason="failure",
        )
        return return_code
    finally:
        os.umask(old_umask)


def _launchctl(
    arguments: Sequence[str],
    *,
    command_runner: CommandRunner = subprocess.run,
) -> subprocess.CompletedProcess[bytes]:
    try:
        return command_runner(
            [str(_LAUNCHCTL), *arguments],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"},
            timeout=_LAUNCHCTL_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError("launchctl is unavailable") from None


def _launchctl_outcome(
    result: subprocess.CompletedProcess[bytes],
    *,
    allow_not_found: bool,
) -> _LaunchctlOutcome:
    if result.returncode == 0:
        return _LaunchctlOutcome.SUCCESS
    # launchctl uses ESRCH (3) or ENOENT-style service lookup status (113),
    # depending on the macOS release and subcommand.  No stderr text is parsed
    # or exposed: every other nonzero status is an operational failure.
    if allow_not_found and result.returncode in {3, 113}:
        return _LaunchctlOutcome.NOT_FOUND
    return _LaunchctlOutcome.FAILED


class _LaunchControlLock:
    """Serialize start/uninstall without sharing the core supervisor lock."""

    def __init__(self, runtime: Path):
        self._path = runtime / _CONTROL_LOCK_NAME
        self._descriptor: int | None = None

    def __enter__(self) -> "_LaunchControlLock":
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor: int | None = None
        try:
            descriptor = os.open(self._path, flags, 0o600)
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.getuid()
                or metadata.st_nlink != 1
                or stat.S_IMODE(metadata.st_mode) != 0o600
            ):
                raise RuntimeError("Unsafe launch-agent control lock")
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            if descriptor is not None:
                os.close(descriptor)
            raise RuntimeError("Launch-agent control operation is already active") from None
        except OSError:
            if descriptor is not None:
                os.close(descriptor)
            raise RuntimeError("Launch-agent control lock is unavailable") from None
        self._descriptor = descriptor
        return self

    def __exit__(self, *_: object) -> None:
        if self._descriptor is not None:
            os.close(self._descriptor)
            self._descriptor = None


def _launchd_state(
    config: Mapping[str, Any],
    *,
    command_runner: CommandRunner,
) -> str:
    target = f"gui/{os.getuid()}/{config['label']}"
    result = _launchctl(["print", target], command_runner=command_runner)
    outcome = _launchctl_outcome(result, allow_not_found=True)
    if outcome is _LaunchctlOutcome.NOT_FOUND:
        return "not_loaded"
    if outcome is _LaunchctlOutcome.FAILED:
        raise RuntimeError("Unable to query the owner-scoped LaunchAgent")
    match = re.search(rb"(?m)^\s*state\s*=\s*([A-Za-z_-]+)\s*$", result.stdout)
    observed = match.group(1).decode("ascii", "ignore") if match else "unknown"
    return observed if observed in {"running", "waiting", "exited"} else "unknown"


@_public_errors
def install_launch_agent(
    runtime_dir: Path,
    *,
    authentication_key_file: Path,
    command_runner: CommandRunner = subprocess.run,
) -> dict[str, Any]:
    config, plist_path, _ = _load_and_validate(
        runtime_dir,
        authentication_key_file=authentication_key_file,
    )
    result = _launchctl(
        ["bootstrap", f"gui/{os.getuid()}", str(plist_path)],
        command_runner=command_runner,
    )
    if _launchctl_outcome(result, allow_not_found=False) is not _LaunchctlOutcome.SUCCESS:
        raise RuntimeError("Unable to install the owner-scoped LaunchAgent")
    return {"label": config["label"], "state": "installed"}


@_public_errors
def start_launch_agent(
    runtime_dir: Path,
    *,
    authentication_key_file: Path,
    command_runner: CommandRunner = subprocess.run,
) -> dict[str, Any]:
    config, _, authentication_key = _load_and_validate(
        runtime_dir,
        authentication_key_file=authentication_key_file,
    )
    runtime = Path(config["runtime_dir"])
    target = f"gui/{os.getuid()}/{config['label']}"
    with _LaunchControlLock(runtime):
        if (
            _read_start_marker(
                runtime,
                config=config,
                authentication_key=authentication_key,
            )
            is not None
        ):
            raise RuntimeError("Refusing to repeat a one-shot start request")
        # Any authenticated worker record means this one-shot boundary was
        # already crossed.  Refuse even if launchd would permit a second run.
        if _worker_status(runtime, config=config, authentication_key=authentication_key) is not None:
            raise RuntimeError("Refusing to restart a one-shot LaunchAgent")
        core = _core_status(
            runtime,
            authentication_key=authentication_key,
            expected_execution_context_sha256=config["execution_context_sha256"],
        )
        if core["state"] != "not_started":
            raise RuntimeError("Refusing to restart a supervised command")
        # This durable HMAC marker is the launch commitment for launchctl.  It
        # is written and directory-fsynced before kickstart, and intentionally
        # survives every nonzero or ambiguous kickstart outcome.
        _write_start_marker(
            runtime,
            config=config,
            authentication_key=authentication_key,
        )
        # Deliberately omit kickstart -k: an already-running worker must never
        # be killed and relaunched across an ambiguous provider boundary.
        result = _launchctl(["kickstart", target], command_runner=command_runner)
        if _launchctl_outcome(result, allow_not_found=False) is not _LaunchctlOutcome.SUCCESS:
            raise RuntimeError("Unable to start the one-shot LaunchAgent")
    return {"label": config["label"], "state": "start_requested"}


def _worker_status(
    runtime: Path,
    *,
    config: Mapping[str, Any],
    authentication_key: bytes,
) -> dict[str, str] | None:
    path = runtime / _STATUS_NAME
    if not path.exists() and not path.is_symlink():
        return None
    _require_regular(path, label="worker status", exact_mode=0o600)
    record = _read_bounded_json(
        path,
        maximum_bytes=_MAX_STATUS_BYTES,
        label="worker status",
    )
    payload = _open_payload(
        _WORKER_STATUS_AUTH_DOMAIN,
        record,
        authentication_key,
    )
    base_keys = {
        "schema_version",
        "label",
        "operation",
        "panel_id",
        "precommitment_sha256",
        "execution_context_sha256",
        "state",
    }
    state = payload.get("state")
    reason = payload.get("reason")
    if (
        payload.get("schema_version") != _WORKER_STATUS_SCHEMA
        or state
        not in {
            "starting",
            "supervisor_running",
            "release_pending",
            "released",
            "supervisor_exited",
            "terminal_incident",
        }
        or frozenset(payload)
        not in {frozenset(base_keys), frozenset(base_keys | {"reason"})}
        or ("reason" in payload and reason not in {
            "cursor_keychain_unavailable",
            "supervisor_exception",
            "release_validation_failed",
            "success",
            "failure",
            "preflight_passed",
            "production_complete",
        })
        or (
            state in {"starting", "supervisor_running", "release_pending"}
            and "reason" in payload
        )
        or (
            state == "released"
            and reason not in {"preflight_passed", "production_complete"}
        )
        or (state == "supervisor_exited" and reason not in {"success", "failure"})
        or (
            state == "terminal_incident"
            and reason
            not in {
                "cursor_keychain_unavailable",
                "supervisor_exception",
                "release_validation_failed",
            }
        )
        or payload.get("label") != config["label"]
        or payload.get("operation") != config["operation"]
        or payload.get("panel_id") != config["panel_id"]
        or payload.get("precommitment_sha256") != config["precommitment_sha256"]
        or payload.get("execution_context_sha256")
        != config["execution_context_sha256"]
    ):
        raise ValueError("Invalid worker status")
    return {key: str(value) for key, value in payload.items() if key != "schema_version"}


def _heartbeat_age_bucket(heartbeat: object) -> str:
    if not isinstance(heartbeat, int) or isinstance(heartbeat, bool):
        return "invalid"
    age = max(0.0, time.time() - heartbeat)
    if age <= 45:
        return "fresh"
    if age <= 120:
        return "under_2m"
    if age <= 600:
        return "under_10m"
    return "over_10m"


def _core_status(
    runtime: Path,
    *,
    authentication_key: bytes,
    expected_execution_context_sha256: str,
) -> dict[str, Any]:
    """Authenticate both core records and return only coarse safe telemetry."""

    from epiagentbench.persistent_supervisor import (
        LEASE_FILE,
        STATUS_FILE,
        classify_supervisor_health,
        diagnose_supervisor_process,
        read_supervisor_lease,
        read_supervisor_status,
    )

    status_path = runtime / STATUS_FILE
    lease_path = runtime / LEASE_FILE
    status_present = status_path.exists() or status_path.is_symlink()
    lease_present = lease_path.exists() or lease_path.is_symlink()
    if not status_present and not lease_present:
        return {
            "state": "not_started",
            "status_authenticated": False,
            "lease_authenticated": False,
            "health": "not_started",
        }
    if status_present != lease_present:
        raise _TransientCoreStatusError("Supervisor status/lease pair is incomplete")

    status: Mapping[str, object] | None = None
    lease: Mapping[str, object] | None = None
    matching_fields = (
        "lease_epoch",
        "execution_context_sha256",
        "pid",
        "boot_identity_sha256",
        "process_birth_identity_sha256",
        "lifecycle",
        "assignment_phase",
        "heartbeat_sequence",
        "heartbeat_wall_unix_seconds",
    )
    # A heartbeat replaces status before lease.  Retry only that narrow,
    # authenticated torn-read window; never downgrade it to an unknown state.
    for attempt in range(3):
        status = read_supervisor_status(
            runtime,
            authentication_key=authentication_key,
        )
        lease = read_supervisor_lease(
            runtime,
            authentication_key=authentication_key,
        )
        if all(status.get(field) == lease.get(field) for field in matching_fields):
            break
        if attempt < 2:
            time.sleep(0.01)
    else:
        raise _TransientCoreStatusError("Supervisor status/lease pair is inconsistent")
    assert status is not None and lease is not None
    if status.get("execution_context_sha256") != expected_execution_context_sha256:
        raise ValueError("Supervisor execution context is not the configured context")
    process_diagnostic = diagnose_supervisor_process(status)
    health = classify_supervisor_health(
        status,
        now_wall_seconds=time.time(),
        process_diagnostic=process_diagnostic,
    )
    return {
        "state": "authenticated",
        "status_authenticated": True,
        "lease_authenticated": True,
        "lifecycle": status["lifecycle"],
        "assignment_phase": status["assignment_phase"],
        "health": health.value,
        "process_diagnostic": process_diagnostic.value,
        "heartbeat_age_bucket": _heartbeat_age_bucket(
            status["heartbeat_wall_unix_seconds"]
        ),
        "completed_assignments": status["completed_assignments"],
        "total_assignments": status["total_assignments"],
        "active_assignment_ordinal": status["active_assignment_ordinal"],
        "pause_after_current": status["pause_after_current"],
        "failure_code": status["failure_code"],
        "execution_context_sha256": status["execution_context_sha256"],
    }


def _status_snapshot(
    config: Mapping[str, Any],
    *,
    authentication_key: bytes,
    command_runner: CommandRunner,
) -> dict[str, Any]:
    runtime = Path(config["runtime_dir"])
    status: dict[str, Any] = {
        "label": config["label"],
        "operation": config["operation"],
        "panel_id": config["panel_id"],
        "precommitment_sha256": config["precommitment_sha256"],
        "launchd_state": _launchd_state(config, command_runner=command_runner),
        "supervisor": _core_status(
            runtime,
            authentication_key=authentication_key,
            expected_execution_context_sha256=config["execution_context_sha256"],
        ),
    }
    marker = _read_start_marker(
        runtime,
        config=config,
        authentication_key=authentication_key,
    )
    status["start_request_state"] = (
        "authenticated" if marker is not None else "not_requested"
    )
    worker = _worker_status(
        runtime,
        config=config,
        authentication_key=authentication_key,
    )
    if worker is None:
        status["worker_state"] = "not_started"
    else:
        status["worker_state"] = worker["state"]
        status["worker_authenticated"] = True
        if "reason" in worker:
            status["worker_reason"] = worker["reason"]
    return status


@_public_errors
def launch_agent_status(
    runtime_dir: Path,
    *,
    authentication_key_file: Path,
    command_runner: CommandRunner = subprocess.run,
) -> dict[str, Any]:
    config, _, authentication_key = _load_and_validate(
        runtime_dir,
        authentication_key_file=authentication_key_file,
    )
    return _status_snapshot(
        config,
        authentication_key=authentication_key,
        command_runner=command_runner,
    )


@_public_errors
def attest_live_launch_agent(
    runtime_dir: Path,
    *,
    authentication_key_file: Path,
    expected_operation: str,
    expected_panel_id: str,
    expected_precommitment_sha256: str,
) -> dict[str, Any]:
    """Attest the exact live supervisor context before provider execution.

    This function performs only authenticated file reads, process-identity
    diagnostics, and clock checks.  It never invokes or mutates launchctl.
    """

    if (
        expected_operation not in _OPERATIONS
        or not isinstance(expected_panel_id, str)
        or not _SAFE_NAME.fullmatch(expected_panel_id)
        or not isinstance(expected_precommitment_sha256, str)
        or not _SHA256.fullmatch(expected_precommitment_sha256)
    ):
        raise ValueError("Invalid expected launch-agent attestation binding")
    config, _, authentication_key = _load_and_validate(
        runtime_dir,
        authentication_key_file=authentication_key_file,
    )
    if (
        config["operation"] != expected_operation
        or config["panel_id"] != expected_panel_id
        or config["precommitment_sha256"] != expected_precommitment_sha256
    ):
        raise ValueError("Launch-agent attestation binding mismatch")
    runtime = Path(config["runtime_dir"])
    if (
        _read_start_marker(
            runtime,
            config=config,
            authentication_key=authentication_key,
        )
        is None
    ):
        raise ValueError("Launch-agent attestation lacks a start commitment")
    worker = _worker_status(
        runtime,
        config=config,
        authentication_key=authentication_key,
    )
    deadline = time.monotonic() + _ATTESTATION_STARTUP_TIMEOUT_SECONDS
    while True:
        try:
            core = _core_status(
                runtime,
                authentication_key=authentication_key,
                expected_execution_context_sha256=config["execution_context_sha256"],
            )
        except _TransientCoreStatusError:
            if time.monotonic() >= deadline:
                raise ValueError("Supervisor startup attestation timed out") from None
            time.sleep(0.05)
            continue
        if core.get("state") != "not_started" or time.monotonic() >= deadline:
            break
        time.sleep(0.05)
    if (
        worker is None
        or worker.get("state") != "supervisor_running"
        or core.get("state") != "authenticated"
        or core.get("lifecycle") != "running"
        or core.get("assignment_phase") not in {"launch_committed", "running"}
        or core.get("health") != "healthy"
        or core.get("process_diagnostic") != "match"
        or core.get("heartbeat_age_bucket") != "fresh"
    ):
        raise ValueError("Launch-agent supervisor is not live and attested")
    return {
        "attested": True,
        "label": config["label"],
        "operation": config["operation"],
        "panel_id": config["panel_id"],
        "precommitment_sha256": config["precommitment_sha256"],
        "execution_context_sha256": config["execution_context_sha256"],
        "config_file_sha256": _file_sha256(
            Path(config["config_path"]),
            maximum_bytes=_MAX_CONFIG_BYTES,
            label="launch-agent config",
        ),
        "supervisor_health": core["health"],
        "supervisor_process": core["process_diagnostic"],
        "assignment_phase": core["assignment_phase"],
    }


@_public_errors
def attest_completed_launch_agent(
    runtime_dir: Path,
    *,
    authentication_key_file: Path,
    expected_operation: str,
    expected_panel_id: str,
    expected_precommitment_sha256: str,
) -> dict[str, Any]:
    """Authenticate one terminal supervisor before releasing any success.

    Unlike live attestation, a later manual finalizer may legitimately observe
    an absent worker PID.  The authenticated terminal status, matching lease,
    and completed event-chain record are therefore authoritative.
    """

    if (
        expected_operation not in _OPERATIONS
        or not isinstance(expected_panel_id, str)
        or not _SAFE_NAME.fullmatch(expected_panel_id)
        or not isinstance(expected_precommitment_sha256, str)
        or not _SHA256.fullmatch(expected_precommitment_sha256)
    ):
        raise ValueError("Invalid completed launch-agent attestation binding")
    config, _, authentication_key = _load_and_validate(
        runtime_dir,
        authentication_key_file=authentication_key_file,
    )
    if (
        config["operation"] != expected_operation
        or config["panel_id"] != expected_panel_id
        or config["precommitment_sha256"] != expected_precommitment_sha256
    ):
        raise ValueError("Completed launch-agent attestation binding mismatch")
    runtime = Path(config["runtime_dir"])
    if (
        _read_start_marker(
            runtime,
            config=config,
            authentication_key=authentication_key,
        )
        is None
    ):
        raise ValueError("Completed launch-agent attestation lacks a start request")
    worker = _worker_status(
        runtime,
        config=config,
        authentication_key=authentication_key,
    )
    if worker is None or worker.get("state") not in {
        "supervisor_running",
        "release_pending",
        "released",
        "supervisor_exited",
    }:
        raise ValueError("Completed launch-agent worker state is invalid")
    if (
        worker.get("state") == "supervisor_exited"
        and worker.get("reason") != "success"
    ):
        raise ValueError("Completed launch-agent worker did not exit successfully")
    core = _core_status(
        runtime,
        authentication_key=authentication_key,
        expected_execution_context_sha256=config["execution_context_sha256"],
    )
    if (
        core.get("state") != "authenticated"
        or core.get("lifecycle") != "completed"
        or core.get("assignment_phase") != "terminal"
        or core.get("health") != "terminal"
        or core.get("completed_assignments") != 1
        or core.get("total_assignments") != 1
        or core.get("failure_code") != "none"
    ):
        raise ValueError("Launch-agent supervisor did not complete cleanly")

    _, persistent_supervisor_source, _ = _verify_frozen_runtime_sources(config)
    import epiagentbench.persistent_supervisor as persistent_supervisor

    _require_loaded_module_source(
        persistent_supervisor.__file__,
        persistent_supervisor_source,
    )
    events = persistent_supervisor.verify_event_log(
        runtime,
        authentication_key=authentication_key,
    )
    if (
        not events
        or not isinstance(events[-1], Mapping)
        or not isinstance(events[-1].get("body"), Mapping)
        or events[-1]["body"].get("event_type") != "completed"
        or events[-1]["body"].get("execution_context_sha256")
        != config["execution_context_sha256"]
        or events[-1]["body"].get("lifecycle") != "completed"
        or events[-1]["body"].get("assignment_phase") != "terminal"
    ):
        raise ValueError("Completed supervisor event chain is invalid")
    return {
        "attested": True,
        "lifecycle": "completed",
        "label": config["label"],
        "operation": config["operation"],
        "panel_id": config["panel_id"],
        "precommitment_sha256": config["precommitment_sha256"],
        "execution_context_sha256": config["execution_context_sha256"],
        "config_file_sha256": _file_sha256(
            Path(config["config_path"]),
            maximum_bytes=_MAX_CONFIG_BYTES,
            label="launch-agent config",
        ),
        "assignment_phase": core["assignment_phase"],
    }


def _finalize_supervised_release(config: Mapping[str, Any]) -> Mapping[str, Any]:
    """Invoke the frozen local-only evaluator finalizer after core completion."""

    _, _, benchmark_source = _verify_frozen_runtime_sources(config)
    import epiagentbench.development_matched_panel as matched_panel

    _require_loaded_module_source(matched_panel.__file__, benchmark_source)
    payload = matched_panel.finalize_supervised_release(
        root=Path(config["repository_root"]),
        authentication_key_file=Path(config["authentication_key_file"]),
        claude_secure_storage_dir=Path(config["claude_secure_storage_dir"]),
        codex_secure_storage_dir=Path(config["codex_secure_storage_dir"]),
        private_state_path=Path(config["private_state_path"]),
        public_manifest_path=Path(config["public_manifest_path"]),
        public_output_path=Path(config["public_output_path"]),
        supervisor_runtime_dir=Path(config["runtime_dir"]),
        operation=str(config["operation"]),
    )
    if not isinstance(payload, Mapping):
        raise ValueError("Supervised release returned an invalid result")
    return payload


@_public_errors
def finalize_launch_agent(
    runtime_dir: Path,
    *,
    authentication_key_file: Path,
) -> dict[str, Any]:
    """Finalize one staged success without invoking a provider or Keychain.

    The launchd worker calls this automatically.  The same operation may be
    invoked manually only to reconcile a crash after the authenticated core
    already reached ``completed``; it never restarts the worker or child.
    """

    config, _, authentication_key = _load_and_validate(
        runtime_dir,
        authentication_key_file=authentication_key_file,
    )
    runtime = Path(config["runtime_dir"])
    # Refuse an active, failed, or ambiguous core before changing worker state.
    attest_completed_launch_agent(
        runtime,
        authentication_key_file=authentication_key_file,
        expected_operation=str(config["operation"]),
        expected_panel_id=str(config["panel_id"]),
        expected_precommitment_sha256=str(config["precommitment_sha256"]),
    )
    with _LaunchControlLock(runtime):
        config, _, authentication_key = _load_and_validate(
            runtime,
            authentication_key_file=authentication_key_file,
        )
        worker = _worker_status(
            runtime,
            config=config,
            authentication_key=authentication_key,
        )
        if worker is None or worker.get("state") not in {
            "supervisor_running",
            "release_pending",
            "released",
            "supervisor_exited",
        }:
            raise ValueError("Launch-agent release state is not recoverable")
        if worker.get("state") == "supervisor_exited" and worker.get(
            "reason"
        ) != "success":
            raise ValueError("Failed supervisor execution cannot be released")
        attest_completed_launch_agent(
            runtime,
            authentication_key_file=authentication_key_file,
            expected_operation=str(config["operation"]),
            expected_panel_id=str(config["panel_id"]),
            expected_precommitment_sha256=str(config["precommitment_sha256"]),
        )
        if worker.get("state") != "released":
            _atomic_worker_status(
                runtime,
                config=config,
                authentication_key=authentication_key,
                state="release_pending",
            )
        try:
            _finalize_supervised_release(config)
        except Exception:
            _atomic_worker_status(
                runtime,
                config=config,
                authentication_key=authentication_key,
                state="terminal_incident",
                reason="release_validation_failed",
            )
            raise
        reason = (
            "preflight_passed"
            if config["operation"] == "preflight"
            else "production_complete"
        )
        _atomic_worker_status(
            runtime,
            config=config,
            authentication_key=authentication_key,
            state="released",
            reason=reason,
        )
    return {
        "label": config["label"],
        "operation": config["operation"],
        "state": "released",
    }


def _authenticated_terminal(status: Mapping[str, Any]) -> bool:
    worker_state = status.get("worker_state")
    worker_reason = status.get("worker_reason")
    supervisor = status.get("supervisor")
    if (
        status.get("start_request_state") != "authenticated"
        or not isinstance(supervisor, Mapping)
    ):
        return False
    if (
        worker_state == "terminal_incident"
        and worker_reason == "cursor_keychain_unavailable"
    ):
        return supervisor.get("state") == "not_started"
    if worker_state not in {"released", "supervisor_exited", "terminal_incident"}:
        return False
    return (
        supervisor.get("state") == "authenticated"
        and supervisor.get("health") == "terminal"
        and supervisor.get("lifecycle") in {"completed", "failed_closed", "paused"}
    )


@_public_errors
def uninstall_launch_agent(
    runtime_dir: Path,
    *,
    authentication_key_file: Path,
    command_runner: CommandRunner = subprocess.run,
) -> dict[str, Any]:
    config, _, authentication_key = _load_and_validate(
        runtime_dir,
        authentication_key_file=authentication_key_file,
    )
    runtime = Path(config["runtime_dir"])
    target = f"gui/{os.getuid()}/{config['label']}"
    with _LaunchControlLock(runtime):
        status = _status_snapshot(
            config,
            authentication_key=authentication_key,
            command_runner=command_runner,
        )
        if status["launchd_state"] == "not_loaded":
            return {"label": config["label"], "state": "already_uninstalled"}
        if status["launchd_state"] not in {"waiting", "exited"}:
            raise RuntimeError("Refusing to uninstall an active or unknown LaunchAgent")
        if not _authenticated_terminal(status):
            raise RuntimeError("Refusing to uninstall without authenticated terminal state")
        result = _launchctl(["bootout", target], command_runner=command_runner)
        outcome = _launchctl_outcome(result, allow_not_found=True)
        if outcome is _LaunchctlOutcome.FAILED:
            raise RuntimeError("Unable to uninstall the owner-scoped LaunchAgent")
    return {"label": config["label"], "state": "uninstalled"}


__all__ = [
    "LaunchAgentError",
    "attest_completed_launch_agent",
    "attest_live_launch_agent",
    "finalize_launch_agent",
    "generate_launch_agent",
    "inspect_launch_agent",
    "install_launch_agent",
    "launch_agent_status",
    "run_launch_agent_worker",
    "start_launch_agent",
    "uninstall_launch_agent",
]
