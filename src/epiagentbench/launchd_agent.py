"""Owner-scoped, one-shot macOS LaunchAgent support for long panel runs.

The launchd property list intentionally contains only the path to an owner-only
configuration file.  In particular, it never contains credentials, provider
environment variables, panel arguments, or log paths.  The worker resolves the
Cursor credential from Keychain after launch and passes it to the supervised
child in memory.

This module never changes launchd state automatically. Explicit install,
start, and uninstall controls are the only mutating ``launchctl`` entry points;
status performs only a read-only ``launchctl print``.
"""

from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterator
from functools import wraps
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


_SCHEMA = "epiagentbench.launchd_agent.v12"
_WORKER_STATUS_SCHEMA = "epiagentbench.launchd_worker_status.v4"
_LABEL_PREFIX = "org.epiagentbench.panel"
_OPERATIONS = frozenset({"preflight", "production"})
_CAFFEINATE = Path("/usr/bin/caffeinate")
_SECURITY = Path("/usr/bin/security")
_LAUNCHCTL = Path("/bin/launchctl")
_CONFIG_NAME = "config.json"
_STATUS_NAME = "launchd-worker-status.json"
_START_MARKER_NAME = "launchd-start-request.json"
_CONTROL_LOCK_NAME = "launchd-control.lock"
_CONFIG_AUTH_DOMAIN = b"epiagentbench:launchd-config:v12\x00"
_WORKER_STATUS_AUTH_DOMAIN = b"epiagentbench:launchd-worker-status:v4\x00"
_START_MARKER_AUTH_DOMAIN = b"epiagentbench:launchd-start-request:v1\x00"
_START_MARKER_SCHEMA = "epiagentbench.launchd_start_request.v1"
_MAX_CONFIG_BYTES = 8 * 1024 * 1024
_MAX_STATUS_BYTES = 16 * 1024
_MAX_PUBLIC_AUTHENTICATION_BYTES = 1024 * 1024
_MAX_PYTHON_EXECUTABLE_BYTES = 256 * 1024 * 1024
_MAX_PYTHON_BOOTSTRAP_FILE_BYTES = 32 * 1024 * 1024
_MAX_RUNTIME_CACHE_FILES = 10_000
_MAX_RUNTIME_CACHE_FILE_BYTES = 512 * 1024 * 1024
_MAX_RUNTIME_CACHE_BYTES = 4 * 1024 * 1024 * 1024
_MAX_AUTHENTICATION_KEY_BYTES = 4096
_MAX_PYTHON_SYMLINK_HOPS = 8
_PYTHON_BOOTSTRAP_TIMEOUT_SECONDS = 15
_KEYCHAIN_TIMEOUT_SECONDS = 15
_LAUNCHCTL_TIMEOUT_SECONDS = 15
_PROTOCOL_VERSION = "persistent-supervisor-v6"
_SAFE_NAME = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9_.@+-]{0,127}\Z")
_TOKEN = re.compile(r"\A[0-9a-f]{24}\Z")
_SHA256 = re.compile(r"\Asha256:[0-9a-f]{64}\Z")
_SAFE_ENVIRONMENT_KEYS = (
    "HOME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "LOGNAME",
    "MPLBACKEND",
    "MPLCONFIGDIR",
    "NUMBA_CACHE_DIR",
    "PATH",
    "PYTHONDONTWRITEBYTECODE",
    "SHELL",
    "STARSIM_INSTALL_FONTS",
    "TMPDIR",
    "USER",
    "XDG_CACHE_HOME",
)
_RUNTIME_CACHE_ENVIRONMENT_KEYS = frozenset(
    {
        "MPLBACKEND",
        "MPLCONFIGDIR",
        "NUMBA_CACHE_DIR",
        "PYTHONDONTWRITEBYTECODE",
        "STARSIM_INSTALL_FONTS",
        "XDG_CACHE_HOME",
    }
)
_PYTHON_ENTRYPOINT_BINDING_SCHEMA = (
    "epiagentbench.python_entrypoint_binding.v2"
)
_RUNTIME_CACHE_CONTRACT_SCHEMA = "epiagentbench.runtime_cache_contract.v3"
_ISOLATED_PYTHON_FLAGS = ("-I", "-S", "-B")
_LAUNCHD_AGENT_SOURCE = Path("src/epiagentbench/launchd_agent.py")
_PERSISTENT_SUPERVISOR_SOURCE = Path(
    "src/epiagentbench/persistent_supervisor.py"
)
_DEVELOPMENT_MATCHED_PANEL_SOURCE = Path(
    "src/epiagentbench/development_matched_panel.py"
)
_HANDLED_TERMINAL_RECEIPT_EXIT_CODE = 64


CommandRunner = Callable[..., subprocess.CompletedProcess[bytes]]


class LaunchAgentError(ValueError):
    """A deliberately non-sensitive launch-agent validation/control error."""


class LiveAttestationFailureCode(StrEnum):
    """Finite, non-sensitive reasons a live supervisor was refused."""

    INVALID_EXPECTATION = "invalid_expectation"
    CONFIG_INTEGRITY = "config_integrity"
    BINDING_MISMATCH = "binding_mismatch"
    START_COMMITMENT_MISSING = "start_commitment_missing"
    START_COMMITMENT_INVALID = "start_commitment_invalid"
    STATUS_SNAPSHOT_UNSTABLE = "status_snapshot_unstable"
    WORKER_STATUS_INVALID = "worker_status_invalid"
    WORKER_NOT_RUNNING = "worker_not_running"
    CORE_INTEGRITY = "core_integrity"
    CORE_NOT_STARTED = "core_not_started"
    CORE_NOT_RUNNING = "core_not_running"
    CORE_PHASE_INVALID = "core_phase_invalid"
    CORE_UNHEALTHY = "core_unhealthy"
    PROCESS_IDENTITY_MISMATCH = "process_identity_mismatch"
    HEARTBEAT_STALE = "heartbeat_stale"


class LiveAttestationError(LaunchAgentError):
    """A live-attestation refusal carrying only a finite safe code."""

    def __init__(self, failure_code: LiveAttestationFailureCode):
        if not isinstance(failure_code, LiveAttestationFailureCode):
            raise TypeError("failure_code must be a LiveAttestationFailureCode")
        self.failure_code = failure_code
        super().__init__("LaunchAgent live attestation was safely refused")


class _TransientAtomicReadError(ValueError):
    """A file changed between lstat and opening its stable descriptor."""


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
        except LiveAttestationError as error:
            raise LiveAttestationError(error.failure_code) from None
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
                raise _TransientAtomicReadError(
                    f"{label} changed while opening"
                )
            raw = stream.read(maximum_bytes + 1)
    except OSError:
        raise ValueError(f"{label} is unavailable") from None
    if len(raw) != metadata.st_size:
        raise _TransientAtomicReadError(f"{label} changed while reading")
    try:
        return json.loads(raw)
    except (UnicodeError, json.JSONDecodeError):
        raise ValueError(f"{label} is invalid") from None


def _file_sha256(
    path: Path,
    *,
    maximum_bytes: int,
    label: str,
    allowed_owners: frozenset[int] | None = None,
) -> str:
    _require_regular(path, label=label, allowed_owners=allowed_owners)
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


def _component_sha256(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _bounded_file_binding(
    path: Path,
    *,
    label: str,
    maximum_bytes: int,
    allowed_owners: frozenset[int],
) -> dict[str, Any]:
    """Bind an immutable-looking regular file, including empty cache files."""

    _require_regular(path, label=label, allowed_owners=allowed_owners)
    before = path.lstat()
    if not 0 <= before.st_size <= maximum_bytes:
        raise ValueError(f"{label} has an invalid size")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            opened = os.fstat(stream.fileno())
            if (
                (opened.st_dev, opened.st_ino)
                != (before.st_dev, before.st_ino)
                or opened.st_size != before.st_size
                or opened.st_nlink != 1
            ):
                raise ValueError(f"{label} changed while opening")
            digest = hashlib.sha256()
            observed_bytes = 0
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                observed_bytes += len(chunk)
                if observed_bytes > maximum_bytes:
                    raise ValueError(f"{label} exceeds its size limit")
                digest.update(chunk)
    except OSError:
        raise ValueError(f"{label} is unavailable") from None
    after = path.lstat()
    stable_fields = (
        "st_dev",
        "st_ino",
        "st_size",
        "st_mtime_ns",
        "st_mode",
        "st_nlink",
        "st_uid",
    )
    if (
        observed_bytes != before.st_size
        or any(
            getattr(before, field) != getattr(after, field)
            for field in stable_fields
        )
    ):
        raise ValueError(f"{label} changed while binding")
    return {
        "path": str(path),
        "device": before.st_dev,
        "inode": before.st_ino,
        "owner_uid": before.st_uid,
        "mode": f"{stat.S_IMODE(before.st_mode):04o}",
        "size_bytes": before.st_size,
        "mtime_ns": before.st_mtime_ns,
        "sha256": "sha256:" + digest.hexdigest(),
    }


def _directory_binding(
    path: Path,
    *,
    label: str,
    exact_mode: int | None = None,
    require_current_owner: bool = True,
) -> dict[str, Any]:
    _require_directory(
        path,
        label=label,
        exact_mode=exact_mode,
        require_current_owner=require_current_owner,
    )
    metadata = path.lstat()
    return {
        "path": str(path),
        "device": metadata.st_dev,
        "inode": metadata.st_ino,
        "owner_uid": metadata.st_uid,
        "mode": f"{stat.S_IMODE(metadata.st_mode):04o}",
        "mtime_ns": metadata.st_mtime_ns,
    }


def _isolated_python_probe(path: Path) -> dict[str, Any]:
    """Inspect one interpreter with startup hooks and ambient paths disabled."""

    probe = (
        "import importlib.util,json,sys;"
        "names=('encodings','hashlib','hmac','json','pathlib','runpy');"
        "origins={n:(getattr(importlib.util.find_spec(n),'origin',None)) "
        "for n in names};"
        "print(json.dumps({"
        "'executable':sys.executable,"
        "'implementation':sys.implementation.name,"
        "'cache_tag':sys.implementation.cache_tag,"
        "'version':[sys.version_info.major,sys.version_info.minor,"
        "sys.version_info.micro],"
        "'prefix':sys.prefix,"
        "'base_prefix':sys.base_prefix,"
        "'sys_path':sys.path,"
        "'flags':{"
        "'dont_write_bytecode':sys.flags.dont_write_bytecode,"
        "'isolated':sys.flags.isolated,"
        "'no_site':sys.flags.no_site,"
        "'ignore_environment':sys.flags.ignore_environment,"
        "'safe_path':sys.flags.safe_path},"
        "'module_origins':origins},sort_keys=True))"
    )
    try:
        completed = subprocess.run(
            [str(path), *_ISOLATED_PYTHON_FLAGS, "-c", probe],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            cwd="/",
            env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"},
            timeout=_PYTHON_BOOTSTRAP_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError("Python isolated-bootstrap probe failed") from None
    if (
        completed.returncode != 0
        or not 0 < len(completed.stdout) <= 64 * 1024
    ):
        raise ValueError("Python isolated-bootstrap probe failed")
    try:
        result = json.loads(completed.stdout)
    except (UnicodeError, json.JSONDecodeError):
        raise ValueError("Python isolated-bootstrap probe was invalid") from None
    if not isinstance(result, dict):
        raise ValueError("Python isolated-bootstrap probe was invalid")
    return result


def _path_identity_allow_absent(
    path: Path,
    *,
    label: str,
    allowed_owners: frozenset[int],
) -> dict[str, Any]:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return {"path": str(path), "kind": "absent"}
    if stat.S_ISDIR(metadata.st_mode):
        _require_directory(
            path,
            label=label,
            require_current_owner=False,
        )
        if metadata.st_uid not in allowed_owners:
            raise ValueError(f"{label} has unsafe ownership")
        return {
            **_directory_binding(
                path,
                label=label,
                require_current_owner=False,
            ),
            "kind": "directory",
        }
    if stat.S_ISREG(metadata.st_mode):
        return {
            **_bounded_file_binding(
                path,
                label=label,
                maximum_bytes=_MAX_PYTHON_BOOTSTRAP_FILE_BYTES,
                allowed_owners=allowed_owners,
            ),
            "kind": "regular_file",
        }
    raise ValueError(f"{label} has an unsafe type")


def _python_startup_hook_inventory(
    site_packages_path: Path,
    *,
    allowed_owners: frozenset[int],
) -> list[dict[str, Any]]:
    """Bind every .pth/sitecustomize/usercustomize candidate without loading it."""

    try:
        candidates = sorted(
            (
                candidate
                for candidate in site_packages_path.iterdir()
                if candidate.suffix == ".pth"
                or candidate.name
                in {
                    "sitecustomize",
                    "sitecustomize.py",
                    "sitecustomize.pyc",
                    "usercustomize",
                    "usercustomize.py",
                    "usercustomize.pyc",
                }
            ),
            key=lambda candidate: candidate.name,
        )
    except OSError:
        raise ValueError(
            "Python startup-hook inventory is unavailable"
        ) from None
    inventory: list[dict[str, Any]] = []
    total_bytes = 0
    for candidate in candidates:
        try:
            metadata = candidate.lstat()
        except OSError:
            raise ValueError(
                "Python startup-hook inventory changed"
            ) from None
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError("Python startup hooks must not be symlinks")
        descendants = (
            [candidate]
            if stat.S_ISREG(metadata.st_mode)
            else (
                sorted(
                    candidate.rglob("*"),
                    key=lambda item: item.relative_to(
                        site_packages_path
                    ).as_posix(),
                )
                if stat.S_ISDIR(metadata.st_mode)
                else []
            )
        )
        if not descendants and not stat.S_ISDIR(metadata.st_mode):
            raise ValueError("Python startup hook has an unsafe type")
        if stat.S_ISDIR(metadata.st_mode):
            descendants.insert(0, candidate)
        for descendant in descendants:
            if len(inventory) >= 1024:
                raise ValueError("Python startup-hook inventory is too large")
            relative = descendant.relative_to(site_packages_path).as_posix()
            observed = descendant.lstat()
            if (
                not relative
                or len(relative.encode("utf-8")) > 4096
                or stat.S_ISLNK(observed.st_mode)
                or observed.st_uid not in allowed_owners
                or stat.S_IMODE(observed.st_mode) & 0o022
            ):
                raise ValueError("Python startup-hook inventory is unsafe")
            if stat.S_ISDIR(observed.st_mode):
                inventory.append(
                    {
                        "relative_path": relative,
                        "kind": "directory",
                        "device": observed.st_dev,
                        "inode": observed.st_ino,
                        "owner_uid": observed.st_uid,
                        "mode": f"{stat.S_IMODE(observed.st_mode):04o}",
                        "mtime_ns": observed.st_mtime_ns,
                    }
                )
                continue
            if not stat.S_ISREG(observed.st_mode):
                raise ValueError("Python startup hook has an unsafe type")
            binding = _bounded_file_binding(
                descendant,
                label="Python startup-hook file",
                maximum_bytes=_MAX_PYTHON_BOOTSTRAP_FILE_BYTES,
                allowed_owners=allowed_owners,
            )
            total_bytes += int(binding["size_bytes"])
            if total_bytes > 64 * 1024 * 1024:
                raise ValueError("Python startup-hook inventory is too large")
            binding["relative_path"] = relative
            binding["kind"] = "regular_file"
            binding.pop("path")
            inventory.append(binding)
    return inventory


def _python_bootstrap_binding(
    launch_path: Path,
    *,
    allowed_owners: frozenset[int],
) -> dict[str, Any]:
    probe = _isolated_python_probe(launch_path)
    expected_probe_keys = {
        "base_prefix",
        "cache_tag",
        "executable",
        "flags",
        "implementation",
        "module_origins",
        "prefix",
        "sys_path",
        "version",
    }
    flags = probe.get("flags")
    version = probe.get("version")
    sys_path = probe.get("sys_path")
    origins = probe.get("module_origins")
    if (
        set(probe) != expected_probe_keys
        or probe.get("executable") != str(launch_path)
        or not isinstance(probe.get("implementation"), str)
        or not isinstance(probe.get("cache_tag"), str)
        or not isinstance(probe.get("prefix"), str)
        or not isinstance(probe.get("base_prefix"), str)
        or not isinstance(version, list)
        or len(version) != 3
        or any(type(part) is not int or part < 0 for part in version)
        or flags
        != {
            "dont_write_bytecode": 1,
            "ignore_environment": 1,
            "isolated": 1,
            "no_site": 1,
            "safe_path": True,
        }
        or not isinstance(sys_path, list)
        or not sys_path
        or any(
            not isinstance(item, str)
            or not item
            or "\x00" in item
            or not Path(item).is_absolute()
            or Path(os.path.normpath(item)) != Path(item)
            for item in sys_path
        )
        or len(set(sys_path)) != len(sys_path)
        or not isinstance(origins, dict)
        or set(origins)
        != {"encodings", "hashlib", "hmac", "json", "pathlib", "runpy"}
    ):
        raise ValueError("Python isolated-bootstrap contract is invalid")

    isolated_path_bindings = [
        _path_identity_allow_absent(
            Path(item),
            label="isolated Python path",
            allowed_owners=allowed_owners,
        )
        for item in sys_path
    ]
    module_origins: dict[str, dict[str, Any] | str] = {}
    for name, raw_origin in sorted(origins.items()):
        if raw_origin in {"built-in", "frozen"}:
            module_origins[name] = str(raw_origin)
            continue
        if (
            not isinstance(raw_origin, str)
            or not Path(raw_origin).is_absolute()
        ):
            raise ValueError("Python bootstrap module origin is invalid")
        module_origins[name] = _bounded_file_binding(
            Path(raw_origin),
            label=f"Python bootstrap module {name}",
            maximum_bytes=_MAX_PYTHON_BOOTSTRAP_FILE_BYTES,
            allowed_owners=allowed_owners,
        )

    venv_root = launch_path.parent.parent
    pyvenv_cfg = venv_root / "pyvenv.cfg"
    venv: dict[str, Any] | None = None
    if pyvenv_cfg.exists() or pyvenv_cfg.is_symlink():
        if launch_path.parent.name != "bin":
            raise ValueError("Python virtual-environment layout is invalid")
        pyvenv_binding = _bounded_file_binding(
            pyvenv_cfg,
            label="Python pyvenv.cfg",
            maximum_bytes=64 * 1024,
            allowed_owners=allowed_owners,
        )
        site_packages_path = (
            venv_root
            / "lib"
            / f"python{version[0]}.{version[1]}"
            / "site-packages"
        )
        site_packages_binding = _directory_binding(
            site_packages_path,
            label="Python virtual-environment site-packages",
        )
        startup_inventory = _python_startup_hook_inventory(
            site_packages_path,
            allowed_owners=allowed_owners,
        )
        venv = {
            "root": _directory_binding(
                venv_root,
                label="Python virtual-environment root",
            ),
            "pyvenv_cfg": pyvenv_binding,
            "site_packages": site_packages_binding,
            "startup_hook_inventory": startup_inventory,
        }
    return {
        "schema_version": "epiagentbench.python_isolated_bootstrap.v2",
        "interpreter_flags": list(_ISOLATED_PYTHON_FLAGS),
        "implementation": probe["implementation"],
        "cache_tag": probe["cache_tag"],
        "version": version,
        "prefix": probe["prefix"],
        "base_prefix": probe["base_prefix"],
        "isolated_sys_path": isolated_path_bindings,
        "module_origins": module_origins,
        "venv": venv,
    }


def _python_entrypoint_binding(path: Path) -> dict[str, Any]:
    """Bind a Python entrypoint and its hook-free isolated bootstrap."""

    launch_path = _absolute(path, label="Python executable")
    if os.path.normpath(str(launch_path)) != str(launch_path):
        raise ValueError("Python executable path must be normalized")
    allowed_owners = frozenset({0, os.getuid()})
    candidate = launch_path
    seen: set[str] = set()
    hops: list[dict[str, Any]] = []
    for _ in range(_MAX_PYTHON_SYMLINK_HOPS + 1):
        candidate_text = str(candidate)
        if candidate_text in seen:
            raise ValueError("Python executable symlink chain is cyclic")
        seen.add(candidate_text)
        _require_directory(
            candidate.parent,
            label="Python executable parent",
            require_current_owner=False,
        )
        metadata = candidate.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            if len(hops) >= _MAX_PYTHON_SYMLINK_HOPS:
                raise ValueError("Python executable symlink chain is too deep")
            if metadata.st_uid not in allowed_owners:
                raise ValueError("Python executable symlink has unsafe ownership")
            link_text = os.readlink(candidate)
            if not link_text or len(link_text) > 4096 or "\x00" in link_text:
                raise ValueError("Python executable symlink target is invalid")
            hops.append(
                {
                    "path": candidate_text,
                    "link_text": link_text,
                    "device": metadata.st_dev,
                    "inode": metadata.st_ino,
                    "owner_uid": metadata.st_uid,
                    "mode": f"{stat.S_IMODE(metadata.st_mode):04o}",
                    "mtime_ns": metadata.st_mtime_ns,
                }
            )
            target = Path(link_text)
            if not target.is_absolute():
                target = candidate.parent / target
            candidate = Path(os.path.normpath(str(target)))
            if not candidate.is_absolute():
                raise ValueError("Python executable symlink target is invalid")
            continue
        _require_regular(
            candidate,
            label="Python executable",
            allowed_owners=allowed_owners,
            executable=True,
        )
        before = candidate.lstat()
        digest = _file_sha256(
            candidate,
            maximum_bytes=_MAX_PYTHON_EXECUTABLE_BYTES,
            label="Python executable",
            allowed_owners=allowed_owners,
        )
        after = candidate.lstat()
        stable_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_mode", "st_nlink")
        if any(getattr(before, name) != getattr(after, name) for name in stable_fields):
            raise ValueError("Python executable changed while binding")
        for hop in hops:
            hop_path = Path(hop["path"])
            observed = hop_path.lstat()
            if (
                not stat.S_ISLNK(observed.st_mode)
                or observed.st_uid not in allowed_owners
                or observed.st_dev != hop["device"]
                or observed.st_ino != hop["inode"]
                or observed.st_uid != hop["owner_uid"]
                or f"{stat.S_IMODE(observed.st_mode):04o}" != hop["mode"]
                or observed.st_mtime_ns != hop["mtime_ns"]
                or os.readlink(hop_path) != hop["link_text"]
            ):
                raise ValueError("Python executable symlink changed while binding")
        bootstrap = _python_bootstrap_binding(
            launch_path,
            allowed_owners=allowed_owners,
        )
        final_target = candidate.lstat()
        if any(
            getattr(before, name) != getattr(final_target, name)
            for name in stable_fields
        ):
            raise ValueError("Python executable changed during bootstrap binding")
        for hop in hops:
            hop_path = Path(hop["path"])
            observed = hop_path.lstat()
            if (
                not stat.S_ISLNK(observed.st_mode)
                or observed.st_uid not in allowed_owners
                or observed.st_dev != hop["device"]
                or observed.st_ino != hop["inode"]
                or observed.st_uid != hop["owner_uid"]
                or f"{stat.S_IMODE(observed.st_mode):04o}" != hop["mode"]
                or observed.st_mtime_ns != hop["mtime_ns"]
                or os.readlink(hop_path) != hop["link_text"]
            ):
                raise ValueError(
                    "Python executable symlink changed during bootstrap binding"
                )
        return {
            "schema_version": _PYTHON_ENTRYPOINT_BINDING_SCHEMA,
            "launch_path": str(launch_path),
            "symlink_hops": hops,
            "target": {
                "path": str(candidate),
                "device": before.st_dev,
                "inode": before.st_ino,
                "owner_uid": before.st_uid,
                "mode": f"{stat.S_IMODE(before.st_mode):04o}",
                "size_bytes": before.st_size,
                "mtime_ns": before.st_mtime_ns,
                "sha256": digest,
            },
            "bootstrap": bootstrap,
        }
    raise ValueError("Python executable symlink chain is too deep")


def _validate_python_entrypoint_binding(config: Mapping[str, Any]) -> None:
    binding = config.get("python_executable_binding")
    if (
        not isinstance(binding, dict)
        or set(binding)
        != {
            "schema_version",
            "launch_path",
            "symlink_hops",
            "target",
            "bootstrap",
        }
        or binding.get("schema_version")
        != _PYTHON_ENTRYPOINT_BINDING_SCHEMA
        or binding.get("launch_path") != config.get("python_executable")
        or not isinstance(binding.get("symlink_hops"), list)
        or not isinstance(binding.get("target"), dict)
        or set(binding["target"])
        != {
            "path",
            "device",
            "inode",
            "owner_uid",
            "mode",
            "size_bytes",
            "mtime_ns",
            "sha256",
        }
        or binding["target"].get("sha256")
        != config.get("python_executable_sha256")
        or _component_sha256(binding)
        != config.get("python_executable_binding_sha256")
    ):
        raise ValueError("Invalid Python executable binding")
    observed = _python_entrypoint_binding(Path(str(config["python_executable"])))
    if not hmac.compare_digest(_canonical_bytes(observed), _canonical_bytes(binding)):
        raise ValueError("Python executable binding changed")


def _bound_isolated_sys_path(binding: Mapping[str, Any]) -> list[str]:
    bootstrap = binding.get("bootstrap")
    raw_paths = (
        bootstrap.get("isolated_sys_path")
        if isinstance(bootstrap, dict)
        else None
    )
    if not isinstance(raw_paths, list):
        raise ValueError("Python isolated-bootstrap path is invalid")
    paths: list[str] = []
    for identity in raw_paths:
        path = identity.get("path") if isinstance(identity, dict) else None
        if not isinstance(path, str) or not Path(path).is_absolute():
            raise ValueError("Python isolated-bootstrap path is invalid")
        paths.append(path)
    return paths


def _bound_site_packages(binding: Mapping[str, Any]) -> str | None:
    bootstrap = binding.get("bootstrap")
    venv = bootstrap.get("venv") if isinstance(bootstrap, dict) else None
    if venv is None:
        return None
    site_packages = (
        venv.get("site_packages") if isinstance(venv, dict) else None
    )
    path = (
        site_packages.get("path")
        if isinstance(site_packages, dict)
        else None
    )
    if not isinstance(path, str) or not Path(path).is_absolute():
        raise ValueError("Python site-packages binding is invalid")
    return path


def _python_binding_paths(binding: Mapping[str, Any]) -> tuple[Path, ...]:
    """Return every raw Python/bootstrap path sealed by one private binding."""

    paths: set[Path] = set()

    def collect(value: object) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"path", "launch_path"} and isinstance(child, str):
                    candidate = Path(child)
                    if candidate.is_absolute():
                        paths.add(candidate)
                else:
                    collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    collect(binding)
    return tuple(sorted(paths, key=str))


def _validate_isolated_python_process(
    *,
    python_executable: Path,
    repository_root: Path,
    binding: Mapping[str, Any] | None = None,
    include_site_packages: bool,
) -> dict[str, Any]:
    """Reattest the hook-free process and its exact manually-built sys.path."""

    observed = (
        _python_entrypoint_binding(python_executable)
        if binding is None
        else dict(binding)
    )
    if binding is not None:
        current = _python_entrypoint_binding(python_executable)
        if not hmac.compare_digest(
            _canonical_bytes(current),
            _canonical_bytes(observed),
        ):
            raise ValueError("Python executable binding changed")
    if (
        sys.flags.isolated != 1
        or sys.flags.no_site != 1
        or sys.flags.ignore_environment != 1
        or sys.flags.dont_write_bytecode != 1
        or not sys.flags.safe_path
        or Path(sys.executable) != python_executable
    ):
        raise ValueError("Python process is not isolated")
    expected_sys_path = _bound_isolated_sys_path(observed)
    source_root = repository_root / "src"
    expected_sys_path.append(str(source_root))
    if include_site_packages:
        site_packages = _bound_site_packages(observed)
        if site_packages is None:
            raise ValueError(
                "Isolated benchmark runner requires a bound virtual environment"
            )
        expected_sys_path.append(site_packages)
    if sys.path != expected_sys_path or len(set(sys.path)) != len(sys.path):
        raise ValueError("Python isolated sys.path binding mismatch")
    return observed


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


def _runtime_cache_file_binding(
    path: Path,
    *,
    relative_path: str,
) -> dict[str, Any]:
    binding = _bounded_file_binding(
        path,
        label="runtime cache file",
        maximum_bytes=_MAX_RUNTIME_CACHE_FILE_BYTES,
        allowed_owners=frozenset({os.getuid()}),
    )
    binding.pop("path")
    return {
        "relative_path": relative_path,
        "kind": "regular_file",
        **binding,
    }


def _runtime_cache_contract(runtime_cache_dir: Path) -> dict[str, Any]:
    """Bind the complete owner-only cache tree without exposing it publicly."""

    root = _absolute(runtime_cache_dir, label="runtime cache directory")
    if Path(os.path.normpath(str(root))) != root:
        raise ValueError("Runtime cache directory must be normalized")
    expected_paths = {
        "root": root,
        "matplotlib": root / "matplotlib",
        "numba": root / "numba",
        "xdg": root / "xdg",
    }
    directories = {
        name: _directory_binding(
            path,
            label=f"runtime cache {name}",
            exact_mode=0o700,
        )
        for name, path in expected_paths.items()
    }
    root_device = int(directories["root"]["device"])
    if any(
        identity["device"] != root_device
        for identity in directories.values()
    ):
        raise ValueError("Runtime caches must share one dedicated filesystem")
    try:
        root_entries_before = sorted(entry.name for entry in root.iterdir())
    except OSError:
        raise ValueError("Runtime cache inventory is unavailable") from None
    if root_entries_before != ["matplotlib", "numba", "xdg"]:
        raise ValueError(
            "Runtime cache root must contain only its three dedicated caches"
        )

    inventory: list[dict[str, Any]] = []
    total_files = 0
    total_bytes = 0
    for cache_name in ("matplotlib", "numba", "xdg"):
        cache_root = expected_paths[cache_name]
        try:
            descendants = sorted(
                cache_root.rglob("*"),
                key=lambda candidate: candidate.relative_to(root).as_posix(),
            )
        except OSError:
            raise ValueError("Runtime cache inventory is unavailable") from None
        for candidate in descendants:
            relative = candidate.relative_to(root).as_posix()
            if (
                not relative
                or len(relative.encode("utf-8")) > 4096
                or relative.startswith("/")
                or "\x00" in relative
            ):
                raise ValueError("Runtime cache inventory is invalid")
            try:
                metadata = candidate.lstat()
            except OSError:
                raise ValueError(
                    "Runtime cache changed while inventorying"
                ) from None
            if stat.S_ISLNK(metadata.st_mode):
                raise ValueError("Runtime cache must not contain symlinks")
            if metadata.st_dev != root_device:
                raise ValueError("Runtime cache must not cross filesystems")
            if metadata.st_uid != os.getuid() or stat.S_IMODE(
                metadata.st_mode
            ) & 0o077:
                raise ValueError(
                    "Runtime cache descendants must be owner-only"
                )
            if len(inventory) >= _MAX_RUNTIME_CACHE_FILES:
                raise ValueError("Runtime cache exceeds its attestation limit")
            if stat.S_ISDIR(metadata.st_mode):
                inventory.append(
                    {
                        "relative_path": relative,
                        "kind": "directory",
                        "device": metadata.st_dev,
                        "inode": metadata.st_ino,
                        "owner_uid": metadata.st_uid,
                        "mode": f"{stat.S_IMODE(metadata.st_mode):04o}",
                    }
                )
                continue
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise ValueError(
                    "Runtime cache contains an unsafe descendant"
                )
            total_files += 1
            total_bytes += metadata.st_size
            if (
                total_files > _MAX_RUNTIME_CACHE_FILES
                or total_bytes > _MAX_RUNTIME_CACHE_BYTES
            ):
                raise ValueError("Runtime cache exceeds its attestation limit")
            inventory.append(
                _runtime_cache_file_binding(
                    candidate,
                    relative_path=relative,
                )
            )
    try:
        root_entries_after = sorted(entry.name for entry in root.iterdir())
    except OSError:
        raise ValueError("Runtime cache inventory is unavailable") from None
    if root_entries_after != root_entries_before:
        raise ValueError("Runtime cache changed while inventorying")
    observed_directories = {
        name: _directory_binding(
            path,
            label=f"runtime cache {name}",
            exact_mode=0o700,
        )
        for name, path in expected_paths.items()
    }
    if observed_directories != directories:
        raise ValueError("Runtime cache changed while inventorying")
    second_relative_paths: list[str] = []
    for cache_name in ("matplotlib", "numba", "xdg"):
        cache_root = expected_paths[cache_name]
        try:
            second_relative_paths.extend(
                candidate.relative_to(root).as_posix()
                for candidate in sorted(
                    cache_root.rglob("*"),
                    key=lambda item: item.relative_to(root).as_posix(),
                )
            )
        except OSError:
            raise ValueError(
                "Runtime cache changed while inventorying"
            ) from None
    if second_relative_paths != [
        item["relative_path"] for item in inventory
    ]:
        raise ValueError("Runtime cache changed while inventorying")
    for item in inventory:
        candidate = root / str(item["relative_path"])
        if item["kind"] == "regular_file":
            observed_item = _runtime_cache_file_binding(
                candidate,
                relative_path=str(item["relative_path"]),
            )
        else:
            observed = candidate.lstat()
            observed_item = {
                "relative_path": item["relative_path"],
                "kind": "directory",
                "device": observed.st_dev,
                "inode": observed.st_ino,
                "owner_uid": observed.st_uid,
                "mode": f"{stat.S_IMODE(observed.st_mode):04o}",
            }
        if observed_item != item:
            raise ValueError("Runtime cache changed while inventorying")
    environment = {
        "MPLBACKEND": "Agg",
        "MPLCONFIGDIR": str(root / "matplotlib"),
        "NUMBA_CACHE_DIR": str(root / "numba"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "STARSIM_INSTALL_FONTS": "0",
        "XDG_CACHE_HOME": str(root / "xdg"),
    }
    return {
        "schema_version": _RUNTIME_CACHE_CONTRACT_SCHEMA,
        "environment": environment,
        "directories": directories,
        "inventory": inventory,
        "inventory_file_count": total_files,
        "inventory_file_bytes": total_bytes,
    }


def _paths_overlap(left: Path, right: Path) -> bool:
    left = Path(os.path.normpath(str(left)))
    right = Path(os.path.normpath(str(right)))
    return (
        left == right
        or left in right.parents
        or right in left.parents
    )


def _require_dedicated_runtime_cache(
    cache_root: Path,
    *,
    protected_paths: Sequence[Path],
) -> None:
    for protected in protected_paths:
        if _paths_overlap(cache_root, protected):
            raise ValueError(
                "Runtime cache must not overlap benchmark or credential state"
            )


def _validate_runtime_cache_binding(config: Mapping[str, Any]) -> None:
    cache = config.get("runtime_cache_contract")
    cache_sha256 = config.get("runtime_cache_contract_sha256")
    if cache is None:
        if cache_sha256 is not None:
            raise ValueError("Invalid launch-agent runtime-cache binding")
        return
    root_path = (
        cache.get("directories", {}).get("root", {}).get("path")
        if isinstance(cache, dict)
        else None
    )
    if (
        not isinstance(root_path, str)
        or not isinstance(cache_sha256, str)
        or _component_sha256(cache) != cache_sha256
        or _runtime_cache_contract(Path(root_path)) != cache
    ):
        raise ValueError("Launch-agent runtime cache changed")


def _manifest_binding(
    path: Path,
) -> tuple[
    str,
    str,
    str,
    str,
    str | None,
    str | None,
]:
    manifest = _read_bounded_json(
        path,
        maximum_bytes=64 * 1024 * 1024,
        label="public manifest",
    )
    if not isinstance(manifest, dict):
        raise ValueError("Public manifest has an invalid schema")
    panel_id = manifest.get("panel_id")
    precommitment = manifest.get("precommitment_sha256")
    runtime_contract = manifest.get("runtime_contract")
    python_executable_sha256 = (
        runtime_contract.get("python_executable_sha256")
        if isinstance(runtime_contract, dict)
        else None
    )
    python_entrypoint_kind = (
        runtime_contract.get("python_entrypoint_kind")
        if isinstance(runtime_contract, dict)
        else None
    )
    python_entrypoint_binding_sha256 = (
        runtime_contract.get("python_executable_binding_sha256")
        if isinstance(runtime_contract, dict)
        else None
    )
    preparation_runtime_contract = manifest.get(
        "preparation_runtime_contract"
    )
    runtime_cache_contract_sha256 = (
        preparation_runtime_contract.get("runtime_cache_contract_sha256")
        if isinstance(preparation_runtime_contract, dict)
        else None
    )
    uses_bound_preparation_runtime = preparation_runtime_contract is not None
    if (
        not isinstance(panel_id, str)
        or not _SAFE_NAME.fullmatch(panel_id)
        or not isinstance(precommitment, str)
        or not _SHA256.fullmatch(precommitment)
        or not isinstance(python_executable_sha256, str)
        or not _SHA256.fullmatch(python_executable_sha256)
        or python_entrypoint_kind not in {"regular_file", "symlink_chain"}
        or uses_bound_preparation_runtime
        and (
            not isinstance(python_entrypoint_binding_sha256, str)
            or not _SHA256.fullmatch(python_entrypoint_binding_sha256)
            or not isinstance(runtime_cache_contract_sha256, str)
            or not _SHA256.fullmatch(runtime_cache_contract_sha256)
            or not isinstance(preparation_runtime_contract, dict)
            or preparation_runtime_contract.get("schema_version")
            != "epiagentbench.bound_preparation_runtime.v1"
            or isinstance(runtime_contract, dict)
            and (
                "python_executable" in runtime_contract
                or "python_executable_binding" in runtime_contract
            )
            or "runtime_cache_contract" in preparation_runtime_contract
        )
    ):
        raise ValueError("Public manifest lacks a valid panel binding")
    return (
        panel_id,
        precommitment,
        python_executable_sha256,
        str(python_entrypoint_kind),
        (
            str(python_entrypoint_binding_sha256)
            if uses_bound_preparation_runtime
            else None
        ),
        (
            str(runtime_cache_contract_sha256)
            if uses_bound_preparation_runtime
            else None
        ),
    )


def _public_authentication_path(public_manifest: Path, panel_id: str) -> Path:
    path = public_manifest.with_name(f"{panel_id}.authentication.json")
    if path == public_manifest:
        raise ValueError("Public authentication receipt must be distinct")
    return path


def _require_output_path(path: Path, *, label: str) -> None:
    metadata = _lstat_path_without_links(path, allow_missing_leaf=True)
    if metadata is None:
        _require_directory(path.parent, label=f"{label} parent")
        return
    _require_regular(path, label=label)


def _safe_environment(
    repository_root: Path,
    path_environment: str | None,
    runtime_environment: Mapping[str, str] | None = None,
) -> dict[str, str]:
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
        "SHELL": identity.pw_shell or "/bin/zsh",
        "TMPDIR": tempfile.gettempdir(),
        "USER": identity.pw_name,
    }
    for key in ("LANG", "LC_ALL", "LC_CTYPE"):
        value = os.environ.get(key)
        if value and "\x00" not in value:
            environment[key] = value
    if runtime_environment is not None:
        if (
            set(runtime_environment) != _RUNTIME_CACHE_ENVIRONMENT_KEYS
            or any(
                not isinstance(value, str) or not value or "\x00" in value
                for value in runtime_environment.values()
            )
        ):
            raise ValueError("Invalid sealed runtime-cache environment")
        environment.update(runtime_environment)
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
        *_ISOLATED_PYTHON_FLAGS,
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


def _runtime_cache_environment_values(
    runtime_cache_contract: object,
    *,
    base_environment: object,
) -> dict[str, str]:
    """Derive the exact six-variable environment from a sealed cache contract."""

    if runtime_cache_contract is None:
        if isinstance(base_environment, Mapping) and (
            set(base_environment) & _RUNTIME_CACHE_ENVIRONMENT_KEYS
        ):
            raise ValueError("Unexpected runtime-cache environment")
        return {}
    if not isinstance(runtime_cache_contract, Mapping):
        raise ValueError("Invalid runtime-cache contract")
    configured_environment = runtime_cache_contract.get("environment")
    directories = runtime_cache_contract.get("directories")
    root_binding = (
        directories.get("root")
        if isinstance(directories, Mapping)
        else None
    )
    root_value = (
        root_binding.get("path")
        if isinstance(root_binding, Mapping)
        else None
    )
    if (
        runtime_cache_contract.get("schema_version")
        != _RUNTIME_CACHE_CONTRACT_SCHEMA
        or not isinstance(configured_environment, Mapping)
        or set(configured_environment)
        != _RUNTIME_CACHE_ENVIRONMENT_KEYS
        or not isinstance(base_environment, Mapping)
        or not isinstance(root_value, str)
        or not Path(root_value).is_absolute()
        or Path(os.path.normpath(root_value)) != Path(root_value)
    ):
        raise ValueError("Invalid runtime-cache environment binding")
    root = Path(root_value)
    expected = {
        "MPLBACKEND": "Agg",
        "MPLCONFIGDIR": str(root / "matplotlib"),
        "NUMBA_CACHE_DIR": str(root / "numba"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "STARSIM_INSTALL_FONTS": "0",
        "XDG_CACHE_HOME": str(root / "xdg"),
    }
    if (
        dict(configured_environment) != expected
        or {
            name: base_environment.get(name)
            for name in _RUNTIME_CACHE_ENVIRONMENT_KEYS
        }
        != expected
        or any(
            not isinstance(value, str) or not value or "\x00" in value
            for value in expected.values()
        )
    ):
        raise ValueError("Runtime-cache environment binding changed")
    return expected


@contextmanager
def _temporary_runtime_cache_environment(
    runtime_cache_contract: object,
    *,
    base_environment: object,
) -> Iterator[None]:
    """Install the authenticated cache environment and restore the caller."""

    expected = _runtime_cache_environment_values(
        runtime_cache_contract,
        base_environment=base_environment,
    )
    if not expected:
        yield
        return
    missing = object()
    previous: dict[str, object] = {
        name: os.environ.get(name, missing) for name in expected
    }
    try:
        for name, value in expected.items():
            os.environ[name] = value
        yield
    finally:
        for name, value in previous.items():
            if value is missing:
                os.environ.pop(name, None)
            else:
                os.environ[name] = str(value)


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
    runtime_cache_dir: Path | None = None,
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
    python_executable_binding = _python_entrypoint_binding(python)
    python_executable_sha256 = str(
        python_executable_binding["target"]["sha256"]
    )
    python_executable_binding_sha256 = _component_sha256(
        python_executable_binding
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
    (
        panel_id,
        precommitment_sha256,
        manifest_python_executable_sha256,
        manifest_python_entrypoint_kind,
        manifest_python_executable_binding_sha256,
        manifest_runtime_cache_contract_sha256,
    ) = _manifest_binding(public_manifest)
    expected_output = public_manifest.with_name(
        (
            f"{panel_id}.preflight.json"
            if operation == "preflight"
            else f"{panel_id}.json"
        )
    )
    supplied_output = (
        public_preflight if operation == "preflight" else public_results
    )
    if supplied_output != expected_output:
        raise ValueError("Public output path is not canonical for the panel")
    python_entrypoint_kind = (
        "symlink_chain"
        if python_executable_binding["symlink_hops"]
        else "regular_file"
    )
    if (
        manifest_python_executable_sha256 != python_executable_sha256
        or manifest_python_entrypoint_kind != python_entrypoint_kind
    ):
        raise ValueError("Python executable differs from the public manifest")
    if (
        manifest_python_executable_binding_sha256 is not None
        and not hmac.compare_digest(
            manifest_python_executable_binding_sha256,
            python_executable_binding_sha256,
        )
    ):
        raise ValueError("Python executable binding differs from the public manifest")
    runtime_cache_contract: dict[str, Any] | None = None
    manifest_runtime_environment: dict[str, str] | None = None
    if manifest_runtime_cache_contract_sha256 is not None:
        if runtime_cache_dir is None:
            raise ValueError(
                "This LaunchAgent requires the manifest-bound runtime cache "
                "directory"
            )
        supplied_runtime_cache = _absolute(
            runtime_cache_dir, label="runtime cache directory"
        )
        runtime_cache_contract = _runtime_cache_contract(
            supplied_runtime_cache
        )
        observed_runtime_cache_sha256 = _component_sha256(
            runtime_cache_contract
        )
        if not hmac.compare_digest(
            observed_runtime_cache_sha256,
            manifest_runtime_cache_contract_sha256,
        ):
            raise ValueError("Runtime cache differs from the public manifest")
        manifest_runtime_environment = dict(
            runtime_cache_contract["environment"]
        )
    elif runtime_cache_dir is not None:
        raise ValueError(
            "Runtime cache directory is not bound by the public manifest"
        )
    public_manifest_file_sha256 = _file_sha256(
        public_manifest,
        maximum_bytes=64 * 1024 * 1024,
        label="public manifest",
    )
    public_authentication = _public_authentication_path(public_manifest, panel_id)
    _require_regular(
        public_authentication,
        label="public authentication receipt",
    )
    public_authentication_file_sha256_before = _file_sha256(
        public_authentication,
        maximum_bytes=_MAX_PUBLIC_AUTHENTICATION_BYTES,
        label="public authentication receipt",
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
    with _temporary_runtime_cache_environment(
        runtime_cache_contract,
        base_environment=manifest_runtime_environment,
    ):
        import epiagentbench.development_matched_panel as matched_panel
        import epiagentbench.persistent_supervisor as persistent_supervisor

        _require_loaded_module_source(
            matched_panel.__file__,
            development_matched_panel_source,
        )
        _require_loaded_module_source(
            persistent_supervisor.__file__,
            persistent_supervisor_source,
        )
        matched_panel.assert_panel_authentication_ready(
            root=root,
            authentication_key_file=auth_key,
            claude_secure_storage_dir=claude_storage,
            codex_secure_storage_dir=codex_storage,
            private_state_path=private_state,
            public_manifest_path=public_manifest,
            require_clean_checkout=True,
        )
        public_authentication_file_sha256 = _file_sha256(
            public_authentication,
            maximum_bytes=_MAX_PUBLIC_AUTHENTICATION_BYTES,
            label="public authentication receipt",
        )
        if (
            public_authentication_file_sha256
            != public_authentication_file_sha256_before
        ):
            raise ValueError(
                "Public authentication receipt changed during readiness validation"
            )

        label = f"{_LABEL_PREFIX}.{os.getuid()}.{token}"
        execution_context_sha256 = (
            persistent_supervisor.compute_execution_context_sha256(
                launchd_label=label,
                operation=operation,
                panel_id=panel_id,
                protocol_version=_PROTOCOL_VERSION,
                public_manifest_sha256=public_manifest_file_sha256,
                python_executable_sha256=python_executable_sha256,
                runner_source_sha256=runner_source_sha256,
                launchd_agent_source_sha256=launchd_agent_source_sha256,
                persistent_supervisor_source_sha256=(
                    persistent_supervisor_source_sha256
                ),
                development_matched_panel_source_sha256=(
                    development_matched_panel_source_sha256
                ),
            )
        )
    output_path = public_preflight if public_preflight is not None else public_results
    assert output_path is not None
    if runtime_cache_contract is not None:
        supplied_runtime_cache = Path(
            runtime_cache_contract["directories"]["root"]["path"]
        )
        _require_dedicated_runtime_cache(
            supplied_runtime_cache,
            protected_paths=(
                runtime,
                root,
                *_python_binding_paths(python_executable_binding),
                auth_key,
                claude_storage,
                codex_storage,
                private_state,
                public_manifest,
                public_authentication,
                output_path,
            ),
        )
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
        "public_authentication_file_sha256": (
            public_authentication_file_sha256
        ),
        "python_executable_sha256": python_executable_sha256,
        "python_executable_binding_sha256": (
            python_executable_binding_sha256
        ),
        "runtime_cache_contract_sha256": (
            _component_sha256(runtime_cache_contract)
            if runtime_cache_contract is not None
            else None
        ),
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
        "python_executable_binding": python_executable_binding,
        "runtime_cache_contract": runtime_cache_contract,
        "worker_script": str(worker_script),
        "runner_script": str(runner_script),
        "authentication_key_file": str(auth_key),
        "claude_secure_storage_dir": str(claude_storage),
        "codex_secure_storage_dir": str(codex_storage),
        "private_state_path": str(private_state),
        "public_manifest_path": str(public_manifest),
        "public_authentication_path": str(public_authentication),
        "public_output_path": str(output_path),
        "cursor_keychain": {
            "service": cursor_keychain_service,
            "account": cursor_keychain_account,
        },
        "base_environment": _safe_environment(
            root,
            path_environment,
            runtime_environment=manifest_runtime_environment,
        ),
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


def _read_authenticated_config(
    runtime_dir: Path,
    *,
    authentication_key_file: Path | None = None,
) -> tuple[Path, Path, dict[str, Any], bytes]:
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
        "public_authentication_file_sha256",
        "python_executable_sha256",
        "python_executable_binding_sha256",
        "runtime_cache_contract_sha256",
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
        "python_executable_binding",
        "runtime_cache_contract",
        "worker_script",
        "runner_script",
        "authentication_key_file",
        "claude_secure_storage_dir",
        "codex_secure_storage_dir",
        "private_state_path",
        "public_manifest_path",
        "public_authentication_path",
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
    return runtime, config_path, config, authentication_key


def _assert_authenticated_config_snapshot(
    config: Mapping[str, Any],
    *,
    authentication_key: bytes,
) -> str:
    """Reopen and exact-compare the one config bound to the active environment."""

    runtime = Path(config["runtime_dir"])
    config_path = Path(config["config_path"])
    (
        observed_runtime,
        observed_config_path,
        observed_config,
        observed_authentication_key,
    ) = _read_authenticated_config(
        runtime,
        authentication_key_file=Path(config["authentication_key_file"]),
    )
    if (
        observed_runtime != runtime
        or observed_config_path != config_path
        or not hmac.compare_digest(
            observed_authentication_key,
            authentication_key,
        )
        or not hmac.compare_digest(
            _canonical_bytes(observed_config),
            _canonical_bytes(config),
        )
    ):
        raise ValueError("Launch-agent config changed after authentication")
    expected_bytes = (
        json.dumps(
            _seal_payload(
                _CONFIG_AUTH_DOMAIN,
                observed_config,
                observed_authentication_key,
            ),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    expected_sha256 = "sha256:" + hashlib.sha256(expected_bytes).hexdigest()
    if not hmac.compare_digest(
        _file_sha256(
            observed_config_path,
            maximum_bytes=_MAX_CONFIG_BYTES,
            label="launch-agent config",
        ),
        expected_sha256,
    ):
        raise ValueError("Launch-agent config encoding changed")
    return expected_sha256


def _validate_authenticated_config(
    *,
    runtime: Path,
    config_path: Path,
    config: dict[str, Any],
    authentication_key: bytes,
) -> tuple[dict[str, Any], Path, bytes]:
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
                "public_authentication_file_sha256",
                "python_executable_sha256",
                "python_executable_binding_sha256",
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
        or not {"HOME", "LOGNAME", "PATH", "SHELL", "TMPDIR", "USER"}.issubset(environment)
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
        "public_authentication_path",
        "public_output_path",
    )
    if any(not isinstance(config[name], str) or not Path(config[name]).is_absolute() for name in path_fields):
        raise ValueError("Launch-agent config contains a non-absolute path")
    _require_directory(Path(config["repository_root"]), label="repository root")
    _validate_python_entrypoint_binding(config)
    configured_cache = config.get("runtime_cache_contract")
    configured_cache_sha256 = config.get(
        "runtime_cache_contract_sha256"
    )
    if configured_cache is None:
        if configured_cache_sha256 is not None or bool(
            set(environment) & _RUNTIME_CACHE_ENVIRONMENT_KEYS
        ):
            raise ValueError("Invalid launch-agent runtime-cache binding")
    elif (
        not isinstance(configured_cache, dict)
        or not isinstance(configured_cache_sha256, str)
        or not _SHA256.fullmatch(configured_cache_sha256)
        or _component_sha256(configured_cache)
        != configured_cache_sha256
    ):
        raise ValueError("Invalid launch-agent runtime-cache binding")
    else:
        cache_root = configured_cache.get("directories", {}).get(
            "root", {}
        ).get("path")
        if (
            not isinstance(cache_root, str)
            or _runtime_cache_contract(Path(cache_root))
            != configured_cache
            or any(
                environment.get(name)
                != configured_cache["environment"].get(name)
                for name in _RUNTIME_CACHE_ENVIRONMENT_KEYS
            )
        ):
            raise ValueError("Launch-agent runtime cache changed")
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
    _require_regular(
        Path(config["public_authentication_path"]),
        label="public authentication receipt",
    )
    if configured_cache is not None:
        _require_dedicated_runtime_cache(
            Path(configured_cache["directories"]["root"]["path"]),
            protected_paths=(
                *_python_binding_paths(config["python_executable_binding"]),
                *(
                    Path(config[name])
                    for name in (
                        "runtime_dir",
                        "repository_root",
                        "authentication_key_file",
                        "claude_secure_storage_dir",
                        "codex_secure_storage_dir",
                        "private_state_path",
                        "public_manifest_path",
                        "public_authentication_path",
                        "public_output_path",
                    )
                ),
            ),
        )
    (
        observed_panel_id,
        observed_precommitment,
        observed_python_executable_sha256,
        observed_python_entrypoint_kind,
        observed_python_executable_binding_sha256,
        observed_runtime_cache_contract_sha256,
    ) = _manifest_binding(Path(config["public_manifest_path"]))
    if (
        observed_panel_id != config["panel_id"]
        or observed_precommitment != config["precommitment_sha256"]
        or observed_python_executable_sha256
        != config["python_executable_sha256"]
        or observed_python_entrypoint_kind
        != (
            "symlink_chain"
            if config["python_executable_binding"]["symlink_hops"]
            else "regular_file"
        )
        or observed_python_executable_binding_sha256 is not None
        and not hmac.compare_digest(
            observed_python_executable_binding_sha256,
            config["python_executable_binding_sha256"],
        )
        or observed_runtime_cache_contract_sha256
        != config["runtime_cache_contract_sha256"]
        or observed_runtime_cache_contract_sha256 is None
        and configured_cache is not None
        or observed_runtime_cache_contract_sha256 is not None
        and configured_cache is None
        or configured_cache is not None
        and not hmac.compare_digest(
            _component_sha256(configured_cache),
            observed_runtime_cache_contract_sha256,
        )
    ):
        raise ValueError("Launch-agent manifest binding mismatch")
    if (
        Path(config["public_authentication_path"])
        != _public_authentication_path(
            Path(config["public_manifest_path"]),
            config["panel_id"],
        )
    ):
        raise ValueError("Launch-agent authentication-receipt path mismatch")
    if (
        _file_sha256(
            Path(config["public_manifest_path"]),
            maximum_bytes=64 * 1024 * 1024,
            label="public manifest",
        )
        != config["public_manifest_file_sha256"]
        or _file_sha256(
            Path(config["public_authentication_path"]),
            maximum_bytes=_MAX_PUBLIC_AUTHENTICATION_BYTES,
            label="public authentication receipt",
        )
        != config["public_authentication_file_sha256"]
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
        python_executable_sha256=config["python_executable_sha256"],
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


def _load_and_validate(
    runtime_dir: Path,
    *,
    authentication_key_file: Path | None = None,
) -> tuple[dict[str, Any], Path, bytes]:
    """Validate a config without extending its environment beyond this call."""

    runtime, config_path, config, authentication_key = (
        _read_authenticated_config(
            runtime_dir,
            authentication_key_file=authentication_key_file,
        )
    )
    return _validate_authenticated_config(
        runtime=runtime,
        config_path=config_path,
        config=config,
        authentication_key=authentication_key,
    )


@contextmanager
def _load_in_authenticated_runtime_environment(
    runtime_dir: Path,
    *,
    authentication_key_file: Path | None = None,
) -> Iterator[tuple[dict[str, Any], Path, bytes]]:
    """Open one HMAC config and hold its exact cache environment while used."""

    runtime, config_path, config, authentication_key = (
        _read_authenticated_config(
            runtime_dir,
            authentication_key_file=authentication_key_file,
        )
    )
    if (
        config.get("schema_version") != _SCHEMA
        or config.get("uid") != os.getuid()
    ):
        raise ValueError("Launch-agent config identity mismatch")
    with _temporary_runtime_cache_environment(
        config.get("runtime_cache_contract"),
        base_environment=config.get("base_environment"),
    ):
        yield _validate_authenticated_config(
            runtime=runtime,
            config_path=config_path,
            config=config,
            authentication_key=authentication_key,
        )


@_public_errors
def inspect_launch_agent(
    runtime_dir: Path,
    *,
    authentication_key_file: Path,
) -> dict[str, Any]:
    """Validate generated artifacts and return a non-sensitive summary."""

    with _load_in_authenticated_runtime_environment(
        runtime_dir,
        authentication_key_file=authentication_key_file,
    ) as (config, plist_path, _):
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
        *_ISOLATED_PYTHON_FLAGS,
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


def _attest_cursor_keychain(
    config: Mapping[str, Any],
    *,
    command_runner: CommandRunner = subprocess.run,
) -> None:
    """Confirm the Cursor credential exists without retrieving its value."""

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
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            env=dict(config["base_environment"]),
            timeout=_KEYCHAIN_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError("Cursor Keychain attestation failed") from None
    if completed.returncode != 0:
        raise RuntimeError("Cursor Keychain attestation failed")


def _run_core_supervisor(
    config: Mapping[str, Any],
    *,
    child_environment: Mapping[str, str],
    authentication_key: bytes,
) -> int:
    """Narrow adapter to the durable supervisor implementation."""

    _validate_python_entrypoint_binding(config)
    _validate_runtime_cache_binding(config)
    _validate_isolated_python_process(
        python_executable=Path(str(config["python_executable"])),
        repository_root=Path(str(config["repository_root"])),
        binding=config["python_executable_binding"],
        include_site_packages=False,
    )
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


def _attest_handled_terminal_receipt(
    config: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Re-attest reserved exit 64 outside the child/supervisor boundary."""

    _, _, matched_panel_source = _verify_frozen_runtime_sources(config)
    import epiagentbench.development_matched_panel as matched_panel

    _require_loaded_module_source(
        matched_panel.__file__,
        matched_panel_source,
    )
    attestation = matched_panel.assert_terminal_receipt_ready_for_exit(
        root=Path(str(config["repository_root"])),
        operation=str(config["operation"]),
        authentication_key_file=Path(
            str(config["authentication_key_file"])
        ),
        private_state_path=Path(str(config["private_state_path"])),
        public_manifest_path=Path(str(config["public_manifest_path"])),
        public_output_path=Path(str(config["public_output_path"])),
    )
    if (
        not isinstance(attestation, Mapping)
        or attestation.get("schema_version")
        != "epiagentbench.terminal_receipt_attestation.v1"
        or attestation.get("panel_id") != config["panel_id"]
        or attestation.get("operation") != config["operation"]
        or attestation.get("status") != "attested"
        or attestation.get("provider_processes_started") != 0
        or type(attestation.get("provider_processes_started")) is not int
        or attestation.get("model_calls_started") != 0
        or type(attestation.get("model_calls_started")) is not int
    ):
        raise RuntimeError("Outer terminal receipt attestation is invalid")
    return attestation


def _run_launch_agent_worker_validated(
    config_file: Path,
    *,
    config: Mapping[str, Any],
    authentication_key: bytes,
    keychain_runner: CommandRunner = subprocess.run,
) -> int:
    """Run one already-authenticated worker inside its sealed environment."""

    if config_file != Path(config["config_path"]):
        raise ValueError("Worker config path mismatch")
    _validate_isolated_python_process(
        python_executable=Path(str(config["python_executable"])),
        repository_root=Path(str(config["repository_root"])),
        binding=config["python_executable_binding"],
        include_site_packages=False,
    )
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
        _validate_python_entrypoint_binding(config)
        _validate_runtime_cache_binding(config)
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
        if return_code == _HANDLED_TERMINAL_RECEIPT_EXIT_CODE:
            try:
                _attest_handled_terminal_receipt(config)
            except Exception:
                _atomic_worker_status(
                    runtime,
                    config=config,
                    authentication_key=authentication_key,
                    state="terminal_incident",
                    reason="terminal_receipt_attestation_failed",
                )
                return 70
        _atomic_worker_status(
            runtime,
            config=config,
            authentication_key=authentication_key,
            state="supervisor_exited",
            reason=(
                "benchmark_terminal_receipt"
                if return_code == _HANDLED_TERMINAL_RECEIPT_EXIT_CODE
                else "failure"
            ),
        )
        return return_code
    finally:
        os.umask(old_umask)


@_public_errors
def run_launch_agent_worker(
    config_path: Path,
    *,
    keychain_runner: CommandRunner = subprocess.run,
) -> int:
    """Run the one-shot worker inside its authenticated cache environment."""

    config_file = _absolute(config_path, label="config path")
    with _load_in_authenticated_runtime_environment(
        config_file.parent,
    ) as (config, _, authentication_key):
        return _run_launch_agent_worker_validated(
            config_file,
            config=config,
            authentication_key=authentication_key,
            keychain_runner=keychain_runner,
        )


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
    matches = re.findall(
        rb"(?m)^([ \t]*)state[ \t]*=[ \t]*([^\r\n]*?)[ \t]*\r?$",
        result.stdout,
    )
    if not matches:
        return "unknown"
    # ``launchctl print`` may include nested objects with their own ``state``
    # fields. Only the unique least-indented state belongs to the queried job;
    # duplicate peers remain ambiguous and fail closed.
    def indentation_width(raw: bytes) -> int:
        return sum(8 if character == 0x09 else 1 for character in raw)

    minimum = min(indentation_width(indent) for indent, _ in matches)
    top_level = [
        value
        for indent, value in matches
        if indentation_width(indent) == minimum
    ]
    if len(top_level) != 1:
        return "unknown"
    return {
        b"running": "running",
        b"waiting": "waiting",
        b"exited": "exited",
        b"not running": "not_running",
    }.get(top_level[0], "unknown")


@_public_errors
def install_launch_agent(
    runtime_dir: Path,
    *,
    authentication_key_file: Path,
    command_runner: CommandRunner = subprocess.run,
) -> dict[str, Any]:
    with _load_in_authenticated_runtime_environment(
        runtime_dir,
        authentication_key_file=authentication_key_file,
    ) as (config, plist_path, _):
        result = _launchctl(
            ["bootstrap", f"gui/{os.getuid()}", str(plist_path)],
            command_runner=command_runner,
        )
        if (
            _launchctl_outcome(result, allow_not_found=False)
            is not _LaunchctlOutcome.SUCCESS
        ):
            raise RuntimeError("Unable to install the owner-scoped LaunchAgent")
        return {"label": config["label"], "state": "installed"}


def _start_launch_agent_validated(
    config: Mapping[str, Any],
    *,
    authentication_key: bytes,
    command_runner: CommandRunner = subprocess.run,
) -> dict[str, Any]:
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
        import epiagentbench.development_matched_panel as matched_panel

        _, _, development_matched_panel_source = _verify_frozen_runtime_sources(
            config
        )
        _require_loaded_module_source(
            matched_panel.__file__,
            development_matched_panel_source,
        )
        matched_panel.assert_durable_live_execution_paths(
            root=Path(config["repository_root"]),
            private_state_path=Path(config["private_state_path"]),
        )
        matched_panel.assert_panel_authentication_ready(
            root=Path(config["repository_root"]),
            authentication_key_file=Path(config["authentication_key_file"]),
            claude_secure_storage_dir=Path(
                config["claude_secure_storage_dir"]
            ),
            codex_secure_storage_dir=Path(
                config["codex_secure_storage_dir"]
            ),
            private_state_path=Path(config["private_state_path"]),
            public_manifest_path=Path(config["public_manifest_path"]),
            require_clean_checkout=True,
        )
        if config["operation"] == "production":
            matched_panel.assert_environment_preflight_ready(
                root=Path(config["repository_root"]),
                authentication_key_file=Path(
                    config["authentication_key_file"]
                ),
                private_state_path=Path(config["private_state_path"]),
                public_manifest_path=Path(config["public_manifest_path"]),
            )
        matched_panel.attest_provider_free_prelaunch(
            root=Path(config["repository_root"]),
            operation=str(config["operation"]),
            public_manifest_path=Path(config["public_manifest_path"]),
        )
        _attest_cursor_keychain(config, command_runner=command_runner)
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


@_public_errors
def start_launch_agent(
    runtime_dir: Path,
    *,
    authentication_key_file: Path,
    command_runner: CommandRunner = subprocess.run,
) -> dict[str, Any]:
    """Request one start using only the HMAC-bound runtime environment."""

    with _load_in_authenticated_runtime_environment(
        runtime_dir,
        authentication_key_file=authentication_key_file,
    ) as (config, _, authentication_key):
        return _start_launch_agent_validated(
            config,
            authentication_key=authentication_key,
            command_runner=command_runner,
        )


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
            "benchmark_terminal_receipt",
            "cursor_keychain_unavailable",
            "supervisor_exception",
            "release_validation_failed",
            "terminal_receipt_attestation_failed",
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
        or (
            state == "supervisor_exited"
            and reason
            not in {"success", "failure", "benchmark_terminal_receipt"}
        )
        or (
            state == "terminal_incident"
            and reason
            not in {
                "cursor_keychain_unavailable",
                "supervisor_exception",
                "release_validation_failed",
                "terminal_receipt_attestation_failed",
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
    with _load_in_authenticated_runtime_environment(
        runtime_dir,
        authentication_key_file=authentication_key_file,
    ) as (config, _, authentication_key):
        return _status_snapshot(
            config,
            authentication_key=authentication_key,
            command_runner=command_runner,
        )


def _attest_live_launch_agent_validated(
    config: Mapping[str, Any],
    *,
    authentication_key: bytes,
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
        raise LiveAttestationError(
            LiveAttestationFailureCode.INVALID_EXPECTATION
        )
    if (
        config["operation"] != expected_operation
        or config["panel_id"] != expected_panel_id
        or config["precommitment_sha256"] != expected_precommitment_sha256
    ):
        raise LiveAttestationError(
            LiveAttestationFailureCode.BINDING_MISMATCH
        )
    runtime = Path(config["runtime_dir"])
    try:
        start_marker = _read_start_marker(
            runtime,
            config=config,
            authentication_key=authentication_key,
        )
    except Exception:
        raise LiveAttestationError(
            LiveAttestationFailureCode.START_COMMITMENT_INVALID
        ) from None
    if start_marker is None:
        raise LiveAttestationError(
            LiveAttestationFailureCode.START_COMMITMENT_MISSING
        )
    try:
        worker = _worker_status(
            runtime,
            config=config,
            authentication_key=authentication_key,
        )
    except _TransientAtomicReadError:
        raise LiveAttestationError(
            LiveAttestationFailureCode.STATUS_SNAPSHOT_UNSTABLE
        ) from None
    except Exception:
        raise LiveAttestationError(
            LiveAttestationFailureCode.WORKER_STATUS_INVALID
        ) from None
    if worker is None or worker.get("state") != "supervisor_running":
        raise LiveAttestationError(
            LiveAttestationFailureCode.WORKER_NOT_RUNNING
        )
    try:
        core = _core_status(
            runtime,
            authentication_key=authentication_key,
            expected_execution_context_sha256=config["execution_context_sha256"],
        )
    except _TransientCoreStatusError:
        raise LiveAttestationError(
            LiveAttestationFailureCode.STATUS_SNAPSHOT_UNSTABLE
        ) from None
    except Exception:
        raise LiveAttestationError(
            LiveAttestationFailureCode.CORE_INTEGRITY
        ) from None
    if core.get("state") == "not_started":
        raise LiveAttestationError(
            LiveAttestationFailureCode.CORE_NOT_STARTED
        )
    if (
        core.get("state") != "authenticated"
        or core.get("lifecycle") != "running"
    ):
        raise LiveAttestationError(
            LiveAttestationFailureCode.CORE_NOT_RUNNING
        )
    if core.get("assignment_phase") not in {"launch_committed", "running"}:
        raise LiveAttestationError(
            LiveAttestationFailureCode.CORE_PHASE_INVALID
        )
    if core.get("health") != "healthy":
        raise LiveAttestationError(
            LiveAttestationFailureCode.CORE_UNHEALTHY
        )
    if core.get("process_diagnostic") != "match":
        raise LiveAttestationError(
            LiveAttestationFailureCode.PROCESS_IDENTITY_MISMATCH
        )
    if core.get("heartbeat_age_bucket") != "fresh":
        raise LiveAttestationError(
            LiveAttestationFailureCode.HEARTBEAT_STALE
        )
    try:
        config_file_sha256 = _assert_authenticated_config_snapshot(
            config,
            authentication_key=authentication_key,
        )
    except Exception:
        raise LiveAttestationError(
            LiveAttestationFailureCode.CONFIG_INTEGRITY
        ) from None
    return {
        "attested": True,
        "label": config["label"],
        "operation": config["operation"],
        "panel_id": config["panel_id"],
        "precommitment_sha256": config["precommitment_sha256"],
        "execution_context_sha256": config["execution_context_sha256"],
        "config_file_sha256": config_file_sha256,
        "supervisor_health": core["health"],
        "supervisor_process": core["process_diagnostic"],
        "assignment_phase": core["assignment_phase"],
    }


@_public_errors
def attest_live_launch_agent(
    runtime_dir: Path,
    *,
    authentication_key_file: Path,
    expected_operation: str,
    expected_panel_id: str,
    expected_precommitment_sha256: str,
) -> dict[str, Any]:
    """Attest live state inside the HMAC-bound runtime environment."""

    try:
        with _load_in_authenticated_runtime_environment(
            runtime_dir,
            authentication_key_file=authentication_key_file,
        ) as (config, _, authentication_key):
            return _attest_live_launch_agent_validated(
                config,
                authentication_key=authentication_key,
                expected_operation=expected_operation,
                expected_panel_id=expected_panel_id,
                expected_precommitment_sha256=(
                    expected_precommitment_sha256
                ),
            )
    except LiveAttestationError:
        raise
    except Exception:
        raise LiveAttestationError(
            LiveAttestationFailureCode.CONFIG_INTEGRITY
        ) from None


def _attest_completed_launch_agent_validated(
    config: Mapping[str, Any],
    *,
    authentication_key: bytes,
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
        "config_file_sha256": _assert_authenticated_config_snapshot(
            config,
            authentication_key=authentication_key,
        ),
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
    """Authenticate terminal state inside the sealed runtime environment."""

    with _load_in_authenticated_runtime_environment(
        runtime_dir,
        authentication_key_file=authentication_key_file,
    ) as (config, _, authentication_key):
        return _attest_completed_launch_agent_validated(
            config,
            authentication_key=authentication_key,
            expected_operation=expected_operation,
            expected_panel_id=expected_panel_id,
            expected_precommitment_sha256=(
                expected_precommitment_sha256
            ),
        )


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


def _finalize_launch_agent_validated(
    config: Mapping[str, Any],
    *,
    authentication_key: bytes,
) -> dict[str, Any]:
    """Finalize one staged success without invoking a provider or Keychain.

    The launchd worker calls this automatically.  The same operation may be
    invoked manually only to reconcile a crash after the authenticated core
    already reached ``completed``; it never restarts the worker or child.
    """

    runtime = Path(config["runtime_dir"])
    # Refuse an active, failed, or ambiguous core before changing worker state.
    _attest_completed_launch_agent_validated(
        config,
        authentication_key=authentication_key,
        expected_operation=str(config["operation"]),
        expected_panel_id=str(config["panel_id"]),
        expected_precommitment_sha256=str(config["precommitment_sha256"]),
    )
    with _LaunchControlLock(runtime):
        _assert_authenticated_config_snapshot(
            config,
            authentication_key=authentication_key,
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
        _attest_completed_launch_agent_validated(
            config,
            authentication_key=authentication_key,
            expected_operation=str(config["operation"]),
            expected_panel_id=str(config["panel_id"]),
            expected_precommitment_sha256=str(config["precommitment_sha256"]),
        )
        if worker.get("state") != "released":
            _assert_authenticated_config_snapshot(
                config,
                authentication_key=authentication_key,
            )
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
        _assert_authenticated_config_snapshot(
            config,
            authentication_key=authentication_key,
        )
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


@_public_errors
def finalize_launch_agent(
    runtime_dir: Path,
    *,
    authentication_key_file: Path,
) -> dict[str, Any]:
    """Finalize one release inside the authenticated cache environment."""

    with _load_in_authenticated_runtime_environment(
        runtime_dir,
        authentication_key_file=authentication_key_file,
    ) as (config, _, authentication_key):
        return _finalize_launch_agent_validated(
            config,
            authentication_key=authentication_key,
        )


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


def _uninstall_launch_agent_validated(
    config: Mapping[str, Any],
    *,
    authentication_key: bytes,
    command_runner: CommandRunner = subprocess.run,
) -> dict[str, Any]:
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
        if status["launchd_state"] not in {"waiting", "exited", "not_running"}:
            raise RuntimeError("Refusing to uninstall an active or unknown LaunchAgent")
        if not _authenticated_terminal(status):
            raise RuntimeError("Refusing to uninstall without authenticated terminal state")
        result = _launchctl(["bootout", target], command_runner=command_runner)
        outcome = _launchctl_outcome(result, allow_not_found=True)
        if outcome is _LaunchctlOutcome.FAILED:
            raise RuntimeError("Unable to uninstall the owner-scoped LaunchAgent")
    return {"label": config["label"], "state": "uninstalled"}


@_public_errors
def uninstall_launch_agent(
    runtime_dir: Path,
    *,
    authentication_key_file: Path,
    command_runner: CommandRunner = subprocess.run,
) -> dict[str, Any]:
    """Uninstall terminal state inside the authenticated cache environment."""

    with _load_in_authenticated_runtime_environment(
        runtime_dir,
        authentication_key_file=authentication_key_file,
    ) as (config, _, authentication_key):
        return _uninstall_launch_agent_validated(
            config,
            authentication_key=authentication_key,
            command_runner=command_runner,
        )


__all__ = [
    "LaunchAgentError",
    "LiveAttestationError",
    "LiveAttestationFailureCode",
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
