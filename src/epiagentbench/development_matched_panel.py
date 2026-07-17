"""Precommitted 50-episode, six-profile development comparison.

This host-networked runner is deliberately ineligible for a leaderboard.  It
binds a fresh authenticated LTC-v3 cohort, hides families and execution order
until completion, checkpoints every provider attempt, and never retries an
assignment once its started marker has reached durable storage.
"""

from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from dataclasses import asdict
import fcntl
import hashlib
import hmac
from itertools import combinations
import json
import math
import os
from pathlib import Path
import platform
import secrets
import shutil
import stat
import statistics
import subprocess
import sys
from typing import Any, Mapping, Sequence

from .development_pilot import (
    DIMENSION_MAXIMA,
    _canonical_bytes,
    _git_output,
    _raise_on_harness_startup_failure,
    _relative_to_root,
    _sanitize_result as _sanitize_base_result,
    _sha256,
    _utc_now,
)
from .pilot import PilotRunResult, _task_prompt, evaluate_local_cli_agent
from .replay_trace import (
    replay_trace_contract,
    replay_trace_sha256,
    validate_replay_trace,
)
from .trusted.cohort_freezer import (
    _RUNTIME_DISTRIBUTIONS,
    _distribution_identity,
    _existing_path_without_final_symlink,
    _read_authentication_key,
    compute_generator_fingerprint,
)
from .trusted.episode_pack import PrivateEpisodeCohortManifest, PrivateEpisodePack


PANEL_ID = "development-matched-50x6-v3"
COHORT_ID = PANEL_ID
SCHEMA_VERSION = "development_matched_panel_v3"
BACKEND = "starsim-ltc-v3"
EPISODE_COUNT = 50
EPISODES_PER_FAMILY = 10
ASSIGNMENT_COUNT = 300
BOOTSTRAP_REPLICATES = 20_000
FAMILIES = (
    "institution_person_to_person",
    "restaurant_point_source",
    "repeated_introduction",
    "coincidental_venue",
    "reporting_artifact",
)
PROFILES: tuple[Mapping[str, Any], ...] = (
    {
        "profile_id": "claude-opus-high",
        "system": "claude",
        "requested_model": "claude-opus-4-8",
        "requested_reasoning": "high",
        "executable": "claude",
        "model_receipt_policy": "provider_match_required",
    },
    {
        "profile_id": "claude-sonnet-high",
        "system": "claude",
        "requested_model": "claude-sonnet-5",
        "requested_reasoning": "high",
        "executable": "claude",
        "model_receipt_policy": "provider_match_required",
    },
    {
        "profile_id": "codex-sol",
        "system": "codex",
        "requested_model": "gpt-5.6-sol",
        "requested_reasoning": "medium",
        "executable": "codex",
        "model_receipt_policy": "command_attested",
    },
    {
        "profile_id": "codex-luna-medium",
        "system": "codex",
        "requested_model": "gpt-5.6-luna",
        "requested_reasoning": "medium",
        "executable": "codex",
        "model_receipt_policy": "command_attested",
    },
    {
        "profile_id": "cursor-grok-high",
        "system": "cursor",
        "requested_model": "cursor-grok-4.5-high",
        "requested_reasoning": "high_model_alias",
        "executable": "cursor-agent",
        "model_receipt_policy": "provider_match_required",
    },
    {
        "profile_id": "cursor-kimi-k27-code",
        "system": "cursor",
        "requested_model": "kimi-k2.7-code",
        "requested_reasoning": "model default; Cursor exposes no reasoning tier",
        "executable": "cursor-agent",
        "model_receipt_policy": "provider_match_required",
    },
)

_PROFILE_BY_ID = {str(profile["profile_id"]): profile for profile in PROFILES}
_PROFILE_IDS = tuple(_PROFILE_BY_ID)
_WILLIAMS_BASE = (0, 1, 5, 2, 4, 3)
_WILLIAMS = tuple(
    tuple((treatment + shift) % len(_WILLIAMS_BASE) for treatment in _WILLIAMS_BASE)
    for shift in range(len(_WILLIAMS_BASE))
)
_EXTRA_SEQUENCES = (
    (0, 1, 2, 3),
    (4, 5, 0, 1),
    (2, 3, 4, 5),
    (0, 1, 2, 3),
    (0, 1, 4, 5),
)
_SCHEDULE_DOMAIN = b"EpiAgentBench private matched schedule v2\x00"
_FAMILY_MAP_DOMAIN = b"EpiAgentBench private matched family map v2\x00"
_PRIVATE_STATE_DOMAIN = b"EpiAgentBench authenticated matched private state v2\x00"
_COHORT_RETIREMENT_DOMAIN = (
    b"EpiAgentBench authenticated terminal cohort retirement v1\x00"
)
_COHORT_RETIREMENT_SCHEMA = "epiagentbench.cohort_retirement.v1"
_COHORT_RETIREMENT_FILE = ".epiagentbench-cohort-retired.json"
_COHORT_RETIREMENT_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "cohort_id",
        "panel_id",
        "pack_set_commitment",
        "public_precommitment_sha256",
        "terminal_results_sha256",
        "terminal_trace_results_sha256",
        "terminal_status",
        "terminal_assignments",
        "retired_at_utc",
    }
)
_MAX_PANEL_JSON_BYTES = 64 * 1024 * 1024
_EXPECTED_RECEIPT_IDENTITIES = {
    "claude-opus-high": "claudeopus48",
    "claude-sonnet-high": "claudesonnet5",
    "cursor-grok-high": "cursorgrok45high",
    "cursor-kimi-k27-code": "kimik27code",
}
_MATCHED_PANEL_NETWORK_OVERRIDES = (
    "ALL_PROXY",
    "CURL_CA_BUNDLE",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NODE_EXTRA_CA_CERTS",
    "REQUESTS_CA_BUNDLE",
    "SSL_CERT_DIR",
    "SSL_CERT_FILE",
    "all_proxy",
    "http_proxy",
    "https_proxy",
)


def _validate_schedule_design() -> None:
    treatments = set(range(len(PROFILES)))
    expected_pairs = {
        (first, second)
        for first in treatments
        for second in treatments
        if first != second
    }
    if (
        len(PROFILES) != 6
        or len(_PROFILE_BY_ID) != len(PROFILES)
        or EPISODE_COUNT != len(FAMILIES) * EPISODES_PER_FAMILY
        or ASSIGNMENT_COUNT != EPISODE_COUNT * len(PROFILES)
        or len(_WILLIAMS) != len(PROFILES)
        or any(set(row) != treatments for row in _WILLIAMS)
        or len(_EXTRA_SEQUENCES) != len(FAMILIES)
        or any(len(extra) != 4 for extra in _EXTRA_SEQUENCES)
    ):
        raise RuntimeError("Invalid six-treatment matched-panel design")
    base_carryovers = Counter(
        pair for row in _WILLIAMS for pair in zip(row, row[1:])
    )
    if set(base_carryovers) != expected_pairs or set(base_carryovers.values()) != {1}:
        raise RuntimeError("Williams rows are not first-order carryover balanced")

    overall_rows: list[tuple[int, ...]] = []
    for extra in _EXTRA_SEQUENCES:
        if any(row_id not in treatments for row_id in extra):
            raise RuntimeError("Williams extra sequence identifier is invalid")
        family_rows = list(_WILLIAMS) + [_WILLIAMS[row_id] for row_id in extra]
        overall_rows.extend(family_rows)
        for position in treatments:
            counts = Counter(row[position] for row in family_rows)
            if set(counts) != treatments or not set(counts.values()).issubset({1, 2}):
                raise RuntimeError("Within-family profile positions are unbalanced")
        carryovers = Counter(
            pair for row in family_rows for pair in zip(row, row[1:])
        )
        if set(carryovers) != expected_pairs or not set(
            carryovers.values()
        ).issubset({1, 2}):
            raise RuntimeError("Within-family carryovers are unbalanced")
    for position in treatments:
        counts = Counter(row[position] for row in overall_rows)
        if set(counts) != treatments or not set(counts.values()).issubset({8, 9}):
            raise RuntimeError("Overall profile positions are unbalanced")
    carryovers = Counter(
        pair for row in overall_rows for pair in zip(row, row[1:])
    )
    if set(carryovers) != expected_pairs or not set(carryovers.values()).issubset(
        {8, 9}
    ):
        raise RuntimeError("Overall carryovers are unbalanced")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, child in pairs:
        if key in value:
            raise ValueError("Duplicate JSON key in matched-panel artifact")
        value[key] = child
    return value


def _reject_constant(_: str) -> None:
    raise ValueError("Non-finite JSON number in matched-panel artifact")


def _load_json(path: Path, *, private: bool = False) -> dict[str, Any]:
    """Read one bounded regular JSON file without following a final symlink."""

    try:
        metadata = path.lstat()
    except OSError:
        raise ValueError(f"Matched-panel artifact is unavailable: {path.name}") from None
    if (
        not stat.S_ISREG(metadata.st_mode)
        or (private and metadata.st_mode & 0o077)
        or not 0 < metadata.st_size <= _MAX_PANEL_JSON_BYTES
    ):
        raise ValueError(f"Unsafe matched-panel artifact: {path.name}")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            opened = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_dev != metadata.st_dev
                or opened.st_ino != metadata.st_ino
                or opened.st_size != metadata.st_size
                or (private and opened.st_mode & 0o077)
            ):
                raise ValueError(f"Matched-panel artifact changed while opening: {path.name}")
            payload = stream.read(_MAX_PANEL_JSON_BYTES + 1)
    except OSError:
        raise ValueError(f"Matched-panel artifact is unavailable: {path.name}") from None
    if len(payload) != metadata.st_size:
        raise ValueError(f"Matched-panel artifact changed while reading: {path.name}")
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, ValueError, RecursionError):
        raise ValueError(f"Invalid matched-panel JSON: {path.name}") from None
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path.name}")
    return value


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_json(path: Path, value: Any, *, private: bool = False) -> None:
    """Atomically replace JSON through a random, exclusive, non-symlink temp."""

    path.parent.mkdir(parents=True, exist_ok=True)
    parent_metadata = path.parent.lstat()
    if not stat.S_ISDIR(parent_metadata.st_mode) or path.parent.is_symlink():
        raise ValueError("Matched-panel artifact parent must be a real directory")
    if path.exists() or path.is_symlink():
        target_metadata = path.lstat()
        if not stat.S_ISREG(target_metadata.st_mode):
            raise ValueError("Matched-panel artifact target must be a regular file")
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if len(payload) > _MAX_PANEL_JSON_BYTES:
        raise ValueError("Matched-panel artifact exceeds the size limit")
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(16)}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor: int | None = None
    created = False
    try:
        descriptor = os.open(temporary, flags, 0o600 if private else 0o644)
        created = True
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            descriptor = None
            os.fchmod(stream.fileno(), 0o600 if private else 0o644)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        created = False
        os.chmod(path, 0o600 if private else 0o644)
        _fsync_directory(path.parent)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if created:
            try:
                temporary.unlink()
            except OSError:
                pass


def _private_state_tag(value: Mapping[str, Any], key: bytes) -> str:
    return hmac.new(
        key,
        _PRIVATE_STATE_DOMAIN + _canonical_bytes(value),
        hashlib.sha256,
    ).hexdigest()


def _write_private_state(path: Path, value: Mapping[str, Any], key: bytes) -> None:
    unsigned = dict(value)
    unsigned.pop("state_authentication", None)
    sealed = {
        **unsigned,
        "state_authentication": {
            "algorithm": "hmac-sha256",
            "tag": _private_state_tag(unsigned, key),
        },
    }
    _atomic_json(path, sealed, private=True)


def _load_private_state(path: Path, key: bytes) -> dict[str, Any]:
    sealed = _load_json(path, private=True)
    authentication = sealed.pop("state_authentication", None)
    supplied = authentication.get("tag") if isinstance(authentication, dict) else None
    expected = _private_state_tag(sealed, key)
    if (
        not isinstance(authentication, dict)
        or authentication.get("algorithm") != "hmac-sha256"
        or not isinstance(supplied, str)
        or not hmac.compare_digest(supplied, expected)
    ):
        raise ValueError("Private matched-panel state authentication failed")
    return sealed


def _cohort_retirement_path(cohort_manifest_path: Path) -> Path:
    return cohort_manifest_path.parent / _COHORT_RETIREMENT_FILE


def _cohort_retirement_tag(value: Mapping[str, Any], key: bytes) -> str:
    return hmac.new(
        key,
        _COHORT_RETIREMENT_DOMAIN + _canonical_bytes(value),
        hashlib.sha256,
    ).hexdigest()


def _load_cohort_retirement_marker(path: Path, key: bytes) -> dict[str, Any]:
    """Load one owner-only retirement record and verify its closed HMAC schema."""

    sealed = _load_json(path, private=True)
    authentication = sealed.pop("authentication", None)
    supplied = (
        authentication.get("tag") if isinstance(authentication, dict) else None
    )
    expected = _cohort_retirement_tag(sealed, key)
    if (
        set(sealed) != _COHORT_RETIREMENT_KEYS
        or not isinstance(authentication, dict)
        or set(authentication) != {"algorithm", "tag"}
        or authentication.get("algorithm") != "hmac-sha256"
        or not isinstance(supplied, str)
        or not hmac.compare_digest(supplied, expected)
        or sealed.get("schema_version") != _COHORT_RETIREMENT_SCHEMA
        or sealed.get("status") != "retired_terminal_trace_release"
    ):
        raise ValueError("Cohort retirement marker authentication failed")
    return sealed


def _cohort_retirement_if_present(
    cohort_manifest_path: Path, key: bytes
) -> dict[str, Any] | None:
    path = _cohort_retirement_path(cohort_manifest_path)
    if not path.exists() and not path.is_symlink():
        return None
    return _load_cohort_retirement_marker(path, key)


def _create_private_json_once(path: Path, value: Any) -> bool:
    """Atomically create, but never replace, one owner-only JSON record."""

    path.parent.mkdir(parents=True, exist_ok=True)
    parent_metadata = path.parent.lstat()
    if not stat.S_ISDIR(parent_metadata.st_mode) or path.parent.is_symlink():
        raise ValueError("Retirement marker parent must be a real directory")
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if not 0 < len(payload) <= _MAX_PANEL_JSON_BYTES:
        raise ValueError("Retirement marker exceeds the size limit")
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(16)}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor: int | None = None
    created_temporary = False
    try:
        descriptor = os.open(temporary, flags, 0o600)
        created_temporary = True
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            descriptor = None
            os.fchmod(stream.fileno(), 0o600)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            # A same-directory hard link is an atomic no-replace publication.
            # If any marker already exists, including a symlink or malformed
            # file, retain it for authentication checks rather than clobber it.
            os.link(temporary, path, follow_symlinks=False)
        except FileExistsError:
            return False
        os.chmod(path, 0o600)
        _fsync_directory(path.parent)
        return True
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if created_temporary:
            try:
                temporary.unlink()
            except OSError:
                pass


def _assert_retirement_matches_panel(
    marker: Mapping[str, Any],
    *,
    manifest: PrivateEpisodeCohortManifest,
    public_manifest: Mapping[str, Any],
) -> None:
    if (
        marker.get("cohort_id") != manifest.cohort_id
        or marker.get("panel_id") != PANEL_ID
        or marker.get("pack_set_commitment") != manifest.pack_set_commitment
        or marker.get("public_precommitment_sha256")
        != public_manifest.get("precommitment_sha256")
    ):
        raise ValueError("Cohort retirement marker belongs to another panel")


def _terminal_trace_results_hash(artifact: Mapping[str, Any]) -> str:
    results = artifact.get("results")
    if not isinstance(results, list):
        raise ValueError("Terminal artifact has no replay result matrix")
    projection = []
    for result in results:
        if not isinstance(result, Mapping):
            raise ValueError("Terminal artifact has an invalid replay result")
        projection.append(
            {
                "episode_ref": result.get("episode_ref"),
                "profile_id": result.get("profile_id"),
                "trace_status": result.get("trace_status"),
                "replay_trace_sha256": result.get("replay_trace_sha256"),
            }
        )
    return _component_hash(projection)


def _terminal_cohort_retirement(
    *,
    manifest: PrivateEpisodeCohortManifest,
    public_manifest: Mapping[str, Any],
    artifact: Mapping[str, Any],
) -> dict[str, Any]:
    results_sha256 = artifact.get("results_sha256")
    terminal_assignments = artifact.get("terminal_assignments")
    terminal_status = artifact.get("status")
    retired_at_utc = artifact.get("completed_at_utc")
    if (
        not isinstance(results_sha256, str)
        or not results_sha256.startswith("sha256:")
        or type(terminal_assignments) is not int
        or terminal_assignments != ASSIGNMENT_COUNT
        or terminal_status not in {"complete", "complete_with_transport_voids"}
        or not isinstance(retired_at_utc, str)
        or not retired_at_utc
    ):
        raise ValueError("Terminal artifact cannot retire its frozen cohort")
    return {
        "schema_version": _COHORT_RETIREMENT_SCHEMA,
        "status": "retired_terminal_trace_release",
        "cohort_id": manifest.cohort_id,
        "panel_id": PANEL_ID,
        "pack_set_commitment": manifest.pack_set_commitment,
        "public_precommitment_sha256": public_manifest["precommitment_sha256"],
        "terminal_results_sha256": results_sha256,
        "terminal_trace_results_sha256": _terminal_trace_results_hash(artifact),
        "terminal_status": terminal_status,
        "terminal_assignments": terminal_assignments,
        "retired_at_utc": retired_at_utc,
    }


def _ensure_terminal_cohort_retirement(
    *,
    cohort_manifest_path: Path,
    manifest: PrivateEpisodeCohortManifest,
    public_manifest: Mapping[str, Any],
    artifact: Mapping[str, Any],
    authentication_key: bytes,
) -> dict[str, Any]:
    """Create or verify the retirement barrier before public trace release."""

    expected = _terminal_cohort_retirement(
        manifest=manifest,
        public_manifest=public_manifest,
        artifact=artifact,
    )
    path = _cohort_retirement_path(cohort_manifest_path)
    existing = _cohort_retirement_if_present(
        cohort_manifest_path, authentication_key
    )
    if existing is None:
        sealed = {
            **expected,
            "authentication": {
                "algorithm": "hmac-sha256",
                "tag": _cohort_retirement_tag(expected, authentication_key),
            },
        }
        _create_private_json_once(path, sealed)
        existing = _load_cohort_retirement_marker(path, authentication_key)
    if existing != expected:
        raise ValueError("Cohort retirement marker differs from terminal results")
    return existing


def _assert_distinct_paths(*paths: Path) -> None:
    resolved = [path.expanduser().resolve() for path in paths]
    if len(resolved) != len(set(resolved)):
        raise ValueError("Matched-panel artifact paths must be distinct")


@contextmanager
def _exclusive_run_lock(_: Path):
    """Hold one host-global lease for this panel, independent of state path."""

    lock_root = Path("/tmp") / f"epiagentbench-panel-locks-{os.getuid()}"
    lock_root.mkdir(mode=0o700, exist_ok=True)
    if lock_root.is_symlink() or not stat.S_ISDIR(lock_root.lstat().st_mode):
        raise RuntimeError("Unsafe matched-panel lock directory")
    os.chmod(lock_root, 0o700)
    lock_path = lock_root / f"{PANEL_ID}.lock"
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError:
        raise RuntimeError("Unable to open the matched-panel run lock") from None
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_mode & 0o077:
            raise RuntimeError("Unsafe matched-panel run lock")
        os.fchmod(descriptor, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Another matched-panel runner already holds the lock") from None
        yield
    finally:
        os.close(descriptor)


def _component_hash(value: Any) -> str:
    return _sha256(_canonical_bytes(value))


def _profile_contract() -> list[dict[str, Any]]:
    return [dict(profile) for profile in PROFILES]


def _source_contract(root: Path) -> dict[str, Any]:
    output = _git_output(
        root,
        "ls-files",
        "--",
        "examples/run_development_matched_panel.py",
        "src/epiagentbench",
        "src/epiagentbench_client",
        "schemas",
        "pyproject.toml",
    )
    paths = sorted({line for line in output.splitlines() if line})
    required = {
        "examples/run_development_matched_panel.py",
        "src/epiagentbench/development_matched_panel.py",
        "pyproject.toml",
    }
    if not required.issubset(paths) or not any(
        path.startswith("src/epiagentbench_client/") for path in paths
    ):
        raise RuntimeError("Tracked matched-panel source surface is incomplete")
    inventory: dict[str, str] = {}
    resolved_root = root.resolve()
    for relative in paths:
        tracked_path = root / relative
        if tracked_path.is_symlink():
            raise RuntimeError("Tracked matched-panel source cannot be a symlink")
        source = tracked_path.resolve()
        try:
            source.relative_to(resolved_root)
        except ValueError as error:
            raise RuntimeError("Tracked source escapes the repository") from error
        if not source.is_file():
            raise RuntimeError("Tracked matched-panel source is unavailable")
        inventory[relative] = _sha256(source.read_bytes())
    return {
        "tracked_runtime_file_count": len(inventory),
        "tracked_runtime_surface_sha256": _component_hash(inventory),
        "task_prompt_sha256": _sha256(_task_prompt().encode("utf-8")),
    }


def _read_cli_identity(executable: str) -> dict[str, str]:
    resolved = shutil.which(executable)
    if resolved is None:
        raise RuntimeError(f"Required provider CLI is unavailable: {executable}")
    resolved_path = Path(resolved).resolve(strict=True)
    if not resolved_path.is_file() or resolved_path.is_symlink():
        raise RuntimeError(f"Provider CLI is not a regular executable: {executable}")
    process = subprocess.run(
        [str(resolved_path), "--version"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=15,
    )
    version = process.stdout.decode("utf-8", errors="replace").strip()[:200]
    if process.returncode != 0 or not version:
        raise RuntimeError(f"Unable to pin provider CLI version: {executable}")
    digest = hashlib.sha256()
    with resolved_path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "name": executable,
        "version": version,
        "executable_sha256": "sha256:" + digest.hexdigest(),
    }


def _cli_contract() -> dict[str, Any]:
    network_overrides = [
        name for name in _MATCHED_PANEL_NETWORK_OVERRIDES if os.environ.get(name)
    ]
    if network_overrides:
        raise RuntimeError(
            "Matched-panel preparation forbids ambient proxy or custom-CA overrides"
        )
    identities: dict[str, dict[str, str]] = {}
    for profile in PROFILES:
        executable = str(profile["executable"])
        if executable not in identities:
            identities[executable] = _read_cli_identity(executable)
    return {
        "executables": [
            identities[executable] for executable in sorted(identities)
        ],
        "ambient_proxy_or_custom_ca_overrides": [],
    }


def _runtime_contract() -> dict[str, Any]:
    try:
        import starsim  # type: ignore

        starsim_version = str(getattr(starsim, "__version__", "unknown"))
    except ImportError:
        raise RuntimeError(
            "Starsim is required before the 50-episode panel can be prepared"
        ) from None
    if starsim_version in {"", "unknown", "unavailable"}:
        raise RuntimeError("Unable to pin the required Starsim runtime")
    return {
        "python": sys.version.split()[0],
        "python_implementation": sys.implementation.name,
        "python_cache_tag": sys.implementation.cache_tag,
        "starsim": starsim_version,
        "platform": platform.system(),
        "machine": platform.machine(),
        "scientific_distributions": {
            name: dict(_distribution_identity(name))
            for name in _RUNTIME_DISTRIBUTIONS
        },
    }


def _keyed(nonce: bytes, *parts: str) -> bytes:
    message = b"\x00".join(part.encode("ascii") for part in parts)
    return hmac.new(nonce, message, hashlib.sha256).digest()


def _private_schedule(
    episodes: Sequence[Mapping[str, Any]], nonce: bytes
) -> list[dict[str, Any]]:
    profile_permutation = tuple(
        sorted(_PROFILE_IDS, key=lambda value: _keyed(nonce, "profile", value))
    )
    order_by_ref: dict[str, list[str]] = {}
    for family_index, family in enumerate(FAMILIES):
        family_episodes = sorted(
            (episode for episode in episodes if episode["family"] == family),
            key=lambda episode: _keyed(
                nonce, "family-episode", family, str(episode["pack_commitment"])
            ),
        )
        if len(family_episodes) != EPISODES_PER_FAMILY:
            raise ValueError("Frozen cohort is not exactly balanced by family")
        sequence_ids = list(range(len(_WILLIAMS))) + list(
            _EXTRA_SEQUENCES[family_index]
        )
        sequence_ids = [
            sequence_id
            for _, sequence_id in sorted(
                enumerate(sequence_ids),
                key=lambda item: _keyed(
                    nonce, "sequence", family, str(item[0]), str(item[1])
                ),
            )
        ]
        for episode, sequence_id in zip(family_episodes, sequence_ids, strict=True):
            order_by_ref[str(episode["episode_ref"])] = [
                profile_permutation[index] for index in _WILLIAMS[sequence_id]
            ]
    run_order = sorted(
        episodes,
        key=lambda episode: _keyed(
            nonce, "run-order", str(episode["pack_commitment"])
        ),
    )
    return [
        {
            "episode_ref": episode["episode_ref"],
            "profile_order": order_by_ref[str(episode["episode_ref"])],
        }
        for episode in run_order
    ]


def _schedule_commitment(schedule: Sequence[Mapping[str, Any]], nonce: bytes) -> str:
    return _sha256(_SCHEDULE_DOMAIN + nonce + _canonical_bytes(schedule))


def _family_map(episodes: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "episode_ref": str(episode["episode_ref"]),
            "family": str(episode["family"]),
        }
        for episode in sorted(episodes, key=lambda item: str(item["episode_ref"]))
    ]


def _family_map_commitment(
    episodes: Sequence[Mapping[str, Any]], nonce: bytes
) -> str:
    return _sha256(_FAMILY_MAP_DOMAIN + nonce + _canonical_bytes(_family_map(episodes)))


def _assignment_keys(
    schedule: Sequence[Mapping[str, Any]],
) -> list[tuple[str, str]]:
    return [
        (str(item["episode_ref"]), str(profile_id))
        for item in schedule
        for profile_id in item["profile_order"]
    ]


def _load_frozen_cohort(
    manifest_path: Path, authentication_key: bytes
) -> tuple[PrivateEpisodeCohortManifest, list[dict[str, Any]]]:
    incomplete_marker = manifest_path.parent / ".freeze-incomplete"
    if incomplete_marker.exists() or incomplete_marker.is_symlink():
        raise ValueError("Frozen cohort retains its incomplete marker")
    manifest = PrivateEpisodeCohortManifest.read(manifest_path, authentication_key)
    if _cohort_retirement_if_present(manifest_path, authentication_key) is not None:
        raise ValueError("Frozen cohort is retired and cannot be prepared again")
    if manifest.cohort_id != COHORT_ID:
        raise ValueError("Frozen cohort identifier does not match the panel")
    if len(manifest.episodes) != EPISODE_COUNT or [
        index for index, _ in manifest.episodes
    ] != list(range(EPISODE_COUNT)):
        raise ValueError("Matched panel requires exactly 50 contiguous frozen packs")
    installed = compute_generator_fingerprint()
    if manifest.generator_fingerprint != installed:
        raise ValueError("Frozen cohort generator differs from the installed runtime")
    episodes: list[dict[str, Any]] = []
    for index, expected_commitment in manifest.episodes:
        pack_path = manifest_path.parent / f"episode-{index:06d}.pack"
        pack = PrivateEpisodePack.read(pack_path, authentication_key)
        manifest.assert_contains(pack)
        if (
            pack.commitment != expected_commitment
            or pack.backend != BACKEND
            or pack.generator_fingerprint != installed
            or pack.family not in FAMILIES
        ):
            raise ValueError("Frozen pack violates the matched-panel contract")
        episodes.append(
            {
                "episode_ref": f"episode_{index + 1:04d}",
                "episode_index": index,
                "pack_path": str(pack_path.resolve()),
                "pack_commitment": pack.commitment,
                "family": pack.family,
            }
        )
    if Counter(str(item["family"]) for item in episodes) != Counter(
        {family: EPISODES_PER_FAMILY for family in FAMILIES}
    ):
        raise ValueError("Frozen cohort must contain exactly ten packs per family")
    return manifest, episodes


def prepare_panel(
    *,
    root: Path,
    cohort_manifest_path: Path,
    authentication_key_file: Path,
    private_state_path: Path,
    public_manifest_path: Path,
    timeout_seconds: int = 900,
    claude_max_budget_usd: float = 5.0,
) -> dict[str, Any]:
    """Bind a fresh authenticated cohort and write its public precommitment."""

    _validate_schedule_design()
    if _git_output(root, "status", "--porcelain", "--untracked-files=all"):
        raise RuntimeError("Commit and clean the matched-panel harness before prepare")
    _assert_distinct_paths(
        cohort_manifest_path,
        authentication_key_file,
        private_state_path,
        public_manifest_path,
    )
    _relative_to_root(private_state_path, root)
    _relative_to_root(public_manifest_path, root)
    if private_state_path.exists() or public_manifest_path.exists():
        raise FileExistsError("Refusing to replace a matched-panel artifact")
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 3600:
        raise ValueError("Invalid assignment timeout")
    if (
        isinstance(claude_max_budget_usd, bool)
        or not isinstance(claude_max_budget_usd, (int, float))
        or not math.isfinite(float(claude_max_budget_usd))
        or not 0 < float(claude_max_budget_usd) <= 100
    ):
        raise ValueError("Invalid Claude assignment budget")

    key_path = _existing_path_without_final_symlink(authentication_key_file)
    key = _read_authentication_key(key_path)
    manifest_path = _existing_path_without_final_symlink(cohort_manifest_path)
    manifest, episodes = _load_frozen_cohort(manifest_path, key)
    nonce = secrets.token_bytes(32)
    schedule = _private_schedule(episodes, nonce)
    keys = _assignment_keys(schedule)
    if len(keys) != ASSIGNMENT_COUNT or len(set(keys)) != ASSIGNMENT_COUNT:
        raise RuntimeError(
            f"Matched schedule does not contain {ASSIGNMENT_COUNT} unique assignments"
        )

    profiles = _profile_contract()
    source = _source_contract(root)
    cli = _cli_contract()
    budgets = {
        "claude_max_budget_usd_per_assignment": float(claude_max_budget_usd),
        "other_provider_spend_cap": None,
        "explicit_unbounded_provider_spend_acknowledgement_required": True,
    }
    timeouts = {"seconds_per_assignment": timeout_seconds}
    runtime = _runtime_contract()
    replay = replay_trace_contract()
    public: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "panel_id": PANEL_ID,
        "status": "precommitted",
        "prepared_at_utc": _utc_now(),
        "development_only": True,
        "hermetic": False,
        "leaderboard_eligible": False,
        "paired": True,
        "calibrated": False,
        "benchmark_base_commit": _git_output(root, "rev-parse", "HEAD"),
        "backend": BACKEND,
        "cohort": {
            "cohort_id": COHORT_ID,
            "episode_count": EPISODE_COUNT,
            "balanced_mode_count": len(FAMILIES),
            "episodes_per_mode": EPISODES_PER_FAMILY,
            "pack_set_commitment": manifest.pack_set_commitment,
            "generator_fingerprint": manifest.generator_fingerprint,
        },
        "episodes": [
            {
                "episode_ref": episode["episode_ref"],
                "pack_commitment": episode["pack_commitment"],
            }
            for episode in sorted(episodes, key=lambda item: str(item["episode_ref"]))
        ],
        "profiles": profiles,
        "cli_contract": cli,
        "source_contract": source,
        "runtime_contract": runtime,
        "replay_trace_contract": replay,
        "budget_contract": budgets,
        "timeout_contract": timeouts,
        "contract_hashes": {
            "source_sha256": _component_hash(source),
            "cli_sha256": _component_hash(cli),
            "profiles_sha256": _component_hash(profiles),
            "budgets_sha256": _component_hash(budgets),
            "timeouts_sha256": _component_hash(timeouts),
            "runtime_sha256": _component_hash(runtime),
            "replay_sha256": _component_hash(replay),
        },
        "private_schedule_commitment": _schedule_commitment(schedule, nonce),
        "private_family_map_commitment": _family_map_commitment(episodes, nonce),
        "schedule_design": {
            "name": "private_family_stratified_near_balanced_williams",
            "profile_position_count_min": 8,
            "profile_position_count_max": 9,
            "within_family_profile_position_count_min": 1,
            "within_family_profile_position_count_max": 2,
            "ordered_carryover_count_min": 8,
            "ordered_carryover_count_max": 9,
            "within_family_ordered_carryover_count_min": 1,
            "within_family_ordered_carryover_count_max": 2,
            "order_released_only_after_terminal_panel": True,
        },
        "run_contract": {
            "planned_assignments": ASSIGNMENT_COUNT,
            "retry_policy": "at most one provider invocation per assignment",
            "orphan_policy": "seal started assignment as transport_void; never retry",
            "transport_void_policy": (
                "stop current command; later command may continue remaining "
                "assignments"
            ),
            "partial_public_results": False,
            "environment_preflight_required_before_production_launch": True,
            "replay_trace_release": {
                "capture": "evaluator_generated_aggregate_only",
                "partial_publication": False,
                "release": "terminal_retired_panel_only",
                "frame_interval_minutes": replay["frame_interval_minutes"],
                "matched_no_action_twin_equality_required": True,
                "scored_endpoint_equality_required": True,
            },
            "primary_estimand": "fixed 50-episode mean per profile only with zero transport voids",
            "bootstrap": {
                "method": "deterministic family-stratified percentile",
                "replicates": BOOTSTRAP_REPLICATES,
                "profile_confidence": 0.95,
                "pairwise_multiplicity": "bonferroni_fifteen_pairs",
                "resampling_unit": "episode",
                "strata": "five scenario families",
                "pairwise_resampling": "paired within episode",
            },
        },
        "planned_assignments": ASSIGNMENT_COUNT,
        "results": [],
        "limitations": [
            "host-networked provider CLIs; execution is not hermetic",
            "synthetic development episodes are not held-out external validation",
            (
                "intervals condition on this generator and equal family weights; "
                "they do not include model rerun variability or simulator "
                "misspecification"
            ),
            "provider spend outside Claude's assignment cap is unbounded",
            "complete agent-system outcomes are not isolated base-model scores",
            (
                "provider usage, cost, and signed request receipts are not yet "
                "captured by this development runner"
            ),
            (
                "local HMAC checkpoints, a public progress watermark, and a "
                "host-global lock are not an external rollback-resistant ledger"
            ),
        ],
    }
    public["precommitment_sha256"] = _component_hash(public)
    private = {
        "schema_version": SCHEMA_VERSION,
        "panel_id": PANEL_ID,
        "status": "prepared",
        "public_precommitment_sha256": public["precommitment_sha256"],
        "cohort_manifest_path": str(manifest_path.resolve()),
        "episodes": episodes,
        "schedule_nonce_hex": nonce.hex(),
        "schedule": schedule,
        "environment_preflight": {
            "status": "required",
            "required_contract_hashes": {
                "source_sha256": public["contract_hashes"]["source_sha256"],
                "cli_sha256": public["contract_hashes"]["cli_sha256"],
                "profiles_sha256": public["contract_hashes"]["profiles_sha256"],
                "runtime_sha256": public["contract_hashes"]["runtime_sha256"],
                "replay_sha256": public["contract_hashes"]["replay_sha256"],
            },
        },
        "assignments": [],
    }
    _write_private_state(private_state_path, private, key)
    _atomic_json(public_manifest_path, public)
    return public


def _validate_public_hash(public: Mapping[str, Any]) -> None:
    unsigned = dict(public)
    supplied = unsigned.pop("precommitment_sha256", None)
    if supplied != _component_hash(unsigned):
        raise ValueError("Public matched-panel precommitment is invalid")


def _validate_contracts(
    *,
    root: Path,
    private: Mapping[str, Any],
    public: Mapping[str, Any],
    authentication_key: bytes,
) -> tuple[
    PrivateEpisodeCohortManifest,
    dict[str, PrivateEpisodePack],
    list[dict[str, Any]],
]:
    _validate_schedule_design()
    _validate_public_hash(public)
    if (
        public.get("panel_id") != PANEL_ID
        or public.get("status") != "precommitted"
        or public.get("results") != []
        or private.get("panel_id") != PANEL_ID
        or private.get("public_precommitment_sha256")
        != public.get("precommitment_sha256")
    ):
        raise ValueError("Matched-panel manifest contract mismatch")
    expected_contracts = {
        "source_contract": _source_contract(root),
        "cli_contract": _cli_contract(),
        "runtime_contract": _runtime_contract(),
        "replay_trace_contract": replay_trace_contract(),
        "profiles": _profile_contract(),
    }
    for name, expected in expected_contracts.items():
        if public.get(name) != expected:
            raise ValueError(f"Pinned matched-panel contract drifted: {name}")
    hashes = public.get("contract_hashes")
    if not isinstance(hashes, dict) or any(
        hashes.get(field) != _component_hash(value)
        for field, value in (
            ("source_sha256", public["source_contract"]),
            ("cli_sha256", public["cli_contract"]),
            ("profiles_sha256", public["profiles"]),
            ("budgets_sha256", public["budget_contract"]),
            ("timeouts_sha256", public["timeout_contract"]),
            ("runtime_sha256", public["runtime_contract"]),
            ("replay_sha256", public["replay_trace_contract"]),
        )
    ):
        raise ValueError("Matched-panel component commitment mismatch")
    cohort_contract = public.get("cohort", {})
    if (
        not isinstance(cohort_contract, dict)
        or cohort_contract.get("cohort_id") != COHORT_ID
    ):
        raise ValueError("Frozen cohort identity contract mismatch")
    expected_generator = cohort_contract.get("generator_fingerprint")
    if not isinstance(expected_generator, str):
        raise ValueError("Frozen cohort generator commitment is invalid")
    installed = compute_generator_fingerprint()
    if not hmac.compare_digest(installed, expected_generator):
        raise ValueError("Installed generator differs from the frozen panel")

    manifest_path = _existing_path_without_final_symlink(
        str(private.get("cohort_manifest_path"))
    )
    manifest = PrivateEpisodeCohortManifest.read(manifest_path, authentication_key)
    retirement = _cohort_retirement_if_present(
        manifest_path, authentication_key
    )
    if retirement is not None:
        if private.get("status") != "complete":
            raise ValueError("Frozen cohort was retired before this panel completed")
        _assert_retirement_matches_panel(
            retirement,
            manifest=manifest,
            public_manifest=public,
        )
    if (
        manifest.cohort_id != COHORT_ID
        or manifest.generator_fingerprint != installed
        or manifest.pack_set_commitment
        != cohort_contract.get("pack_set_commitment")
    ):
        raise ValueError("Frozen set no longer matches the public commitment")
    private_episodes = private.get("episodes")
    if not isinstance(private_episodes, list) or len(private_episodes) != EPISODE_COUNT:
        raise ValueError("Private matched-panel episode state is invalid")
    public_commitments = {
        str(item.get("episode_ref")): str(item.get("pack_commitment"))
        for item in public.get("episodes", [])
        if isinstance(item, dict)
    }
    packs: dict[str, PrivateEpisodePack] = {}
    for episode in private_episodes:
        ref = str(episode.get("episode_ref"))
        pack = PrivateEpisodePack.read(
            Path(str(episode.get("pack_path"))), authentication_key
        )
        manifest.assert_contains(pack)
        if (
            pack.backend != BACKEND
            or pack.generator_fingerprint != installed
            or pack.family != episode.get("family")
            or pack.commitment != episode.get("pack_commitment")
            or public_commitments.get(ref) != pack.commitment
        ):
            raise ValueError("Private pack replay mismatch")
        packs[ref] = pack
    if len(packs) != EPISODE_COUNT or Counter(
        str(pack.family) for pack in packs.values()
    ) != Counter({family: EPISODES_PER_FAMILY for family in FAMILIES}):
        raise ValueError("Private matched-panel cohort is not balanced")
    try:
        nonce = bytes.fromhex(str(private.get("schedule_nonce_hex")))
    except ValueError as error:
        raise ValueError("Private schedule nonce is invalid") from error
    schedule = _private_schedule(private_episodes, nonce)
    if (
        len(nonce) != 32
        or private.get("schedule") != schedule
        or public.get("private_schedule_commitment")
        != _schedule_commitment(schedule, nonce)
        or public.get("private_family_map_commitment")
        != _family_map_commitment(private_episodes, nonce)
    ):
        raise ValueError("Private matched schedule or family map does not match its commitment")
    expected_keys = _assignment_keys(schedule)
    assignments = private.get("assignments")
    if not isinstance(assignments, list) or len(assignments) > ASSIGNMENT_COUNT:
        raise ValueError("Private assignment state is invalid")
    for index, assignment in enumerate(assignments):
        key_value = (
            str(assignment.get("episode_ref")),
            str(assignment.get("profile_id")),
        )
        if key_value != expected_keys[index] or assignment.get("status") not in {
            "started",
            "complete",
            "transport_void",
        }:
            raise ValueError("Private assignments do not follow the committed order")
        if assignment.get("status") == "started" and index != len(assignments) - 1:
            raise ValueError("Only the final checkpoint may remain started")
    if private.get("status") == "complete" and (
        len(assignments) != ASSIGNMENT_COUNT
        or any(item.get("status") not in {"complete", "transport_void"} for item in assignments)
    ):
        raise ValueError("Completed private state is not fully terminal")
    return manifest, packs, schedule


def _assert_environment_preflight(
    root: Path, private: Mapping[str, Any], public: Mapping[str, Any]
) -> None:
    preflight = private.get("environment_preflight")
    expected = {
        name: public["contract_hashes"][name]
        for name in (
            "source_sha256",
            "cli_sha256",
            "profiles_sha256",
            "runtime_sha256",
            "replay_sha256",
        )
    }
    if (
        not isinstance(preflight, dict)
        or preflight.get("status") != "passed"
        or preflight.get("passed_contract_hashes") != expected
    ):
        raise RuntimeError(
            "A disposable six-profile environment preflight bound to the current "
            "contracts must pass before any production episode is launched"
        )
    receipt_path = Path(str(preflight.get("public_receipt_path", "")))
    receipt_relative = _relative_to_root(receipt_path, root)
    if (
        _git_output(root, "ls-files", "--error-unmatch", receipt_relative)
        != receipt_relative
    ):
        raise RuntimeError("The passed environment preflight receipt is not committed")
    receipt = _load_json(receipt_path)
    if (
        receipt.get("status") != "passed"
        or receipt.get("contract_hashes") != expected
        or preflight.get("public_receipt_sha256") != _component_hash(receipt)
    ):
        raise RuntimeError("The committed environment preflight receipt is invalid")


def run_environment_preflight(
    *,
    root: Path,
    authentication_key_file: Path,
    private_state_path: Path,
    public_manifest_path: Path,
    public_preflight_path: Path,
    acknowledge_unbounded_provider_spend: bool = False,
) -> dict[str, Any]:
    """Exercise every provider profile on one disposable, unscored episode."""

    if acknowledge_unbounded_provider_spend is not True:
        raise RuntimeError(
            "Explicit acknowledgement of unbounded preflight provider spend is required"
        )
    if not os.environ.get("CURSOR_API_KEY", "").strip():
        raise RuntimeError(
            "Disposable six-profile preflight requires CURSOR_API_KEY before "
            "any provider call"
        )
    _assert_distinct_paths(
        authentication_key_file,
        private_state_path,
        public_manifest_path,
        public_preflight_path,
    )
    with _exclusive_run_lock(private_state_path):
        authentication_key = _read_authentication_key(
            _existing_path_without_final_symlink(authentication_key_file)
        )
        private = _load_private_state(private_state_path, authentication_key)
        public = _load_json(public_manifest_path)
        _validate_contracts(
            root=root,
            private=private,
            public=public,
            authentication_key=authentication_key,
        )
        if private.get("assignments") or private.get("status") != "prepared":
            raise RuntimeError("Environment preflight must precede production execution")
        preflight = private.get("environment_preflight")
        if not isinstance(preflight, dict) or preflight.get("status") != "required":
            raise RuntimeError("Environment preflight is not in its one-shot required state")
        if public_preflight_path.exists() or public_preflight_path.is_symlink():
            raise FileExistsError("Refusing to replace an environment preflight receipt")
        _preflight_execution(
            root=root,
            private_state_path=private_state_path,
            public_manifest_path=public_manifest_path,
            public_results_path=public_preflight_path,
        )

        contract_hashes = {
            name: public["contract_hashes"][name]
            for name in (
                "source_sha256",
                "cli_sha256",
                "profiles_sha256",
                "runtime_sha256",
                "replay_sha256",
            )
        }
        cli_versions = {
            str(item["name"]): str(item["version"])
            for item in public["cli_contract"]["executables"]
        }
        timeout = int(public["timeout_contract"]["seconds_per_assignment"])
        budget = float(
            public["budget_contract"]["claude_max_budget_usd_per_assignment"]
        )
        attempts: list[dict[str, Any]] = []
        private["environment_preflight"] = {
            "status": "running",
            "started_at_utc": _utc_now(),
            "attempts": attempts,
            "required_contract_hashes": contract_hashes,
        }
        _write_private_state(private_state_path, private, authentication_key)

        public_attempts: list[dict[str, Any]] = []
        for profile in PROFILES:
            profile_id = str(profile["profile_id"])
            marker: dict[str, Any] = {
                "profile_id": profile_id,
                "status": "started",
                "started_at_utc": _utc_now(),
            }
            attempts.append(marker)
            _write_private_state(private_state_path, private, authentication_key)
            digest = hashlib.sha256(
                f"{PANEL_ID}|disposable-preflight|{profile_id}".encode("ascii")
            ).digest()
            failure_stage = "provider_launch"
            try:
                result = evaluate_local_cli_agent(
                    str(profile["system"]),
                    seed=int.from_bytes(digest[:6], "big"),
                    family="reporting_artifact",
                    backend=BACKEND,
                    episode_secret=digest,
                    model=str(profile["requested_model"]),
                    executable=str(profile["executable"]),
                    timeout_seconds=timeout,
                    claude_max_budget_usd=budget,
                    claude_effort=(
                        "high" if profile["system"] == "claude" else None
                    ),
                )
                _raise_on_harness_startup_failure(result)
                receipt_required = profile["model_receipt_policy"] == "provider_match_required"
                receipt_ok = _exact_model_receipt_satisfied(
                    profile, result.observed_models
                )
                metrics = result.scorecard.get("metrics", {})
                failure_stage = "trace_validation"
                try:
                    validate_replay_trace(result.replay_trace)
                except (TypeError, ValueError) as error:
                    raise RuntimeError(
                        "Disposable provider preflight replay contract failed"
                    ) from error
                failure_stage = (
                    "model_receipt"
                    if receipt_required and not receipt_ok
                    else "provider_contract"
                )
                if (
                    result.system != profile["system"]
                    or result.requested_model != profile["requested_model"]
                    or result.cli_version != cli_versions[str(profile["executable"])]
                    or result.returncode != 0
                    or not result.submission
                    or not isinstance(metrics, dict)
                    or metrics.get("integrity_pass") is not True
                    or type(metrics.get("tool_calls")) is not int
                    or metrics.get("tool_calls", 0) < 1
                    or any(
                        str(event).startswith("infrastructure_failure:")
                        for event in result.audit_events
                    )
                    or (receipt_required and not receipt_ok)
                ):
                    raise RuntimeError("Disposable provider preflight contract failed")
                raw_hash = _component_hash(asdict(result))
                marker.update(
                    {
                        "status": "passed",
                        "finished_at_utc": _utc_now(),
                        "raw_result_sha256": raw_hash,
                    }
                )
                public_attempts.append(
                    {
                        "profile_id": profile_id,
                        "system": profile["system"],
                        "requested_model": profile["requested_model"],
                        "observed_models": list(result.observed_models),
                        "cli_version": result.cli_version,
                        "model_receipt_satisfied": (
                            receipt_ok if receipt_required else None
                        ),
                        "raw_result_sha256": raw_hash,
                        "replay_trace_validated": True,
                        "scored": False,
                    }
                )
                _write_private_state(private_state_path, private, authentication_key)
            except Exception as error:
                marker.update(
                    {
                        "status": "failed",
                        "finished_at_utc": _utc_now(),
                        "failure_class": type(error).__name__,
                        "failure_stage": failure_stage,
                    }
                )
                failed = {
                    "schema_version": SCHEMA_VERSION,
                    "panel_id": PANEL_ID,
                    "status": "failed",
                    "development_only": True,
                    "production_episodes_consumed": 0,
                    "contract_hashes": contract_hashes,
                    "profiles_passed": public_attempts,
                    "failed_profile_id": profile_id,
                    "failure_class": type(error).__name__,
                    "failure_stage": failure_stage,
                    "scores_reported": False,
                }
                private["environment_preflight"] = {
                    **private["environment_preflight"],
                    "status": "failed",
                    "finished_at_utc": _utc_now(),
                }
                _atomic_json(public_preflight_path, failed)
                private["environment_preflight"]["public_receipt_path"] = str(
                    public_preflight_path.resolve()
                )
                private["environment_preflight"]["public_receipt_sha256"] = (
                    _component_hash(failed)
                )
                _write_private_state(private_state_path, private, authentication_key)
                return failed

        receipt = {
            "schema_version": SCHEMA_VERSION,
            "panel_id": PANEL_ID,
            "status": "passed",
            "development_only": True,
            "production_episodes_consumed": 0,
            "contract_hashes": contract_hashes,
            "profiles": public_attempts,
            "scores_reported": False,
            "completed_at_utc": _utc_now(),
        }
        _atomic_json(public_preflight_path, receipt)
        private["environment_preflight"] = {
            **private["environment_preflight"],
            "status": "passed",
            "finished_at_utc": receipt["completed_at_utc"],
            "passed_contract_hashes": contract_hashes,
            "public_receipt_path": str(public_preflight_path.resolve()),
            "public_receipt_sha256": _component_hash(receipt),
        }
        _write_private_state(private_state_path, private, authentication_key)
        return receipt


def _preflight_execution(
    *,
    root: Path,
    private_state_path: Path,
    public_manifest_path: Path,
    public_results_path: Path,
    allowed_private_artifact_paths: Sequence[Path] = (),
) -> None:
    public_relative = _relative_to_root(public_manifest_path, root)
    private_relative = _relative_to_root(private_state_path, root)
    results_relative = _relative_to_root(public_results_path, root)
    if _git_output(root, "ls-files", "--error-unmatch", public_relative) != public_relative:
        raise RuntimeError("Public matched-panel precommitment has not been committed")
    if _git_output(root, "ls-files", private_relative):
        raise RuntimeError("Private matched-panel state must never be tracked")
    if os.stat(private_state_path).st_mode & 0o077:
        raise RuntimeError("Private matched-panel state permissions are too broad")
    expected_dirty = (
        {f"?? {results_relative}"} if public_results_path.exists() else set()
    )
    for artifact_path in allowed_private_artifact_paths:
        if not artifact_path.exists() and not artifact_path.is_symlink():
            continue
        metadata = artifact_path.lstat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_mode & 0o077
        ):
            raise RuntimeError("Authenticated private run artifact is unsafe")
        try:
            artifact_relative = _relative_to_root(artifact_path, root)
        except ValueError:
            # An external private cohort cannot appear in this repository's
            # status output, but its marker still must be a safe owner-only file.
            continue
        if _git_output(root, "ls-files", artifact_relative):
            raise RuntimeError("Authenticated private run artifact is unsafe")
        expected_dirty.add(f"?? {artifact_relative}")
    observed_dirty = _git_output(
        root, "status", "--porcelain", "--untracked-files=all"
    )
    observed_lines = {line for line in observed_dirty.splitlines() if line}
    if observed_lines != expected_dirty:
        raise RuntimeError("Matched-panel execution worktree is not clean")


def _public_running(
    public_manifest: Mapping[str, Any],
    private: Mapping[str, Any],
    *,
    status: str = "running",
) -> dict[str, Any]:
    assignments = private.get("assignments", [])
    completed = sum(item.get("status") == "complete" for item in assignments)
    voids = sum(item.get("status") == "transport_void" for item in assignments)
    return {
        "schema_version": SCHEMA_VERSION,
        "panel_id": PANEL_ID,
        "precommitment_sha256": public_manifest["precommitment_sha256"],
        "development_only": True,
        "hermetic": False,
        "leaderboard_eligible": False,
        "status": status,
        "started_at_utc": private["panel_started_at_utc"],
        "planned_assignments": ASSIGNMENT_COUNT,
        "terminal_assignments": completed + voids,
        "completed_assignments": completed,
        "transport_voids": voids,
        "results": [],
        "summary": {"primary_estimand": "pending"},
    }


def _normalized_model_identity(value: str) -> str:
    return "".join(character for character in value.lower() if character.isalnum())


def _exact_model_receipt_satisfied(
    profile: Mapping[str, Any], observed_models: Sequence[str]
) -> bool:
    expected = _EXPECTED_RECEIPT_IDENTITIES.get(str(profile["profile_id"]))
    if expected is None:
        return False
    identities = tuple(_normalized_model_identity(value) for value in observed_models)
    return identities == (expected,)


def _sanitize_result(
    *,
    episode: Mapping[str, Any],
    profile: Mapping[str, Any],
    result: PilotRunResult,
    started_at: str,
    finished_at: str,
) -> dict[str, Any]:
    sanitized = _sanitize_base_result(
        episode=episode,
        result=result,
        started_at=started_at,
        finished_at=finished_at,
    )
    sanitized["profile_id"] = profile["profile_id"]
    sanitized["pack_commitment"] = episode["pack_commitment"]
    sanitized["requested_reasoning"] = profile["requested_reasoning"]
    sanitized["evidence_hashes"] = {
        "captured_stdout_sha256": result.captured_stdout_sha256,
        "captured_stderr_sha256": result.captured_stderr_sha256,
        "command_sha256": result.command_sha256,
        "raw_result_sha256": _component_hash(asdict(result)),
    }
    policy = str(profile["model_receipt_policy"])
    receipt_ok = _exact_model_receipt_satisfied(profile, result.observed_models)
    sanitized["model_receipt_policy"] = policy
    sanitized["model_receipt_satisfied"] = (
        receipt_ok if policy == "provider_match_required" else None
    )
    if policy == "provider_match_required" and not receipt_ok:
        sanitized["valid"] = False
        sanitized["total"] = 0.0
        sanitized["dimensions"] = {name: 0.0 for name in DIMENSION_MAXIMA}
        events = list(sanitized["audit_events"])
        if "agent_failure:model_receipt_missing" not in events:
            events.append("agent_failure:model_receipt_missing")
        sanitized["audit_events"] = events
        sanitized["model_attribution"] = "failed"
    return sanitized


def _percentile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def _stratified_ci(
    values: Mapping[str, Sequence[float]], *, tag: str, lower: float, upper: float
) -> list[float]:
    samples: list[float] = []
    for replicate in range(BOOTSTRAP_REPLICATES):
        selected: list[float] = []
        for family in FAMILIES:
            population = list(values[family])
            for draw in range(len(population)):
                digest = hashlib.sha256(
                    f"{PANEL_ID}|{tag}|{replicate}|{family}|{draw}".encode("ascii")
                ).digest()
                selected.append(population[int.from_bytes(digest[:8], "big") % len(population)])
        samples.append(statistics.fmean(selected))
    return [round(_percentile(samples, lower), 3), round(_percentile(samples, upper), 3)]


def aggregate_complete_results(
    results: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Compute predeclared statistics for a zero-transport-void complete panel."""

    if len(results) != ASSIGNMENT_COUNT:
        raise ValueError(
            f"Complete matched-panel aggregation requires {ASSIGNMENT_COUNT} results"
        )
    keyed: dict[tuple[str, str], Mapping[str, Any]] = {}
    for result in results:
        key = (str(result.get("episode_ref")), str(result.get("profile_id")))
        total = result.get("total")
        valid = result.get("valid")
        if (
            key in keyed
            or key[1] not in _PROFILE_BY_ID
            or result.get("family") not in FAMILIES
            or type(valid) is not bool
            or isinstance(total, bool)
            or not isinstance(total, (int, float))
            or not math.isfinite(float(total))
            or not 0 <= float(total) <= 100
            or (not valid and float(total) != 0.0)
        ):
            raise ValueError("Invalid complete matched-panel result")
        keyed[key] = result
    refs = sorted({ref for ref, _ in keyed})
    if len(refs) != EPISODE_COUNT or any(
        (ref, profile_id) not in keyed for ref in refs for profile_id in _PROFILE_IDS
    ):
        raise ValueError("Complete matched-panel result matrix is incomplete")
    if any(
        len({keyed[(ref, profile_id)].get("family") for profile_id in _PROFILE_IDS})
        != 1
        for ref in refs
    ):
        raise ValueError("Profiles disagree about an episode's family")
    profiles: dict[str, Any] = {}
    for profile_id in _PROFILE_IDS:
        selected = [keyed[(ref, profile_id)] for ref in refs]
        by_family = {
            family: [
                float(item.get("total", 0.0))
                for item in selected
                if item.get("family") == family
            ]
            for family in FAMILIES
        }
        if any(len(values) != EPISODES_PER_FAMILY for values in by_family.values()):
            raise ValueError("Complete results are not family balanced")
        totals = [float(item.get("total", 0.0)) for item in selected]
        family_summaries = {
            family: {
                "fixed_denominator": EPISODES_PER_FAMILY,
                "valid": sum(
                    bool(item.get("valid"))
                    for item in selected
                    if item.get("family") == family
                ),
                "valid_rate": round(
                    sum(
                        bool(item.get("valid"))
                        for item in selected
                        if item.get("family") == family
                    )
                    / EPISODES_PER_FAMILY,
                    3,
                ),
                "invalid_zero_count": sum(
                    not bool(item.get("valid"))
                    for item in selected
                    if item.get("family") == family
                ),
                "mean_total": round(statistics.fmean(by_family[family]), 3),
            }
            for family in FAMILIES
        }
        valid_count = sum(bool(item.get("valid")) for item in selected)
        profiles[profile_id] = {
            "fixed_denominator": EPISODE_COUNT,
            "valid": valid_count,
            "valid_rate": round(valid_count / EPISODE_COUNT, 3),
            "mean_total": round(statistics.fmean(totals), 3),
            "family_stratified_bootstrap_95_ci": _stratified_ci(
                by_family, tag=f"profile:{profile_id}", lower=0.025, upper=0.975
            ),
            "by_family": family_summaries,
        }
    pairwise: dict[str, Any] = {}
    pair_count = math.comb(len(_PROFILE_IDS), 2)
    alpha_tail = 0.05 / (2 * pair_count)
    for first, second in combinations(_PROFILE_IDS, 2):
        deltas = {
            family: [
                float(keyed[(ref, first)].get("total", 0.0))
                - float(keyed[(ref, second)].get("total", 0.0))
                for ref in refs
                if keyed[(ref, first)].get("family") == family
                and keyed[(ref, second)].get("family") == family
            ]
            for family in FAMILIES
        }
        flat = [value for family in FAMILIES for value in deltas[family]]
        pairwise[f"{first}_minus_{second}"] = {
            "exploratory": True,
            "mean_delta": round(statistics.fmean(flat), 3),
            "simultaneous_familywise_confidence_target": 0.95,
            "per_interval_confidence": round(1 - 0.05 / pair_count, 6),
            "family_stratified_bootstrap_ci": _stratified_ci(
                deltas,
                tag=f"pair:{first}:{second}",
                lower=alpha_tail,
                upper=1 - alpha_tail,
            ),
            "by_family_mean_delta": {
                family: round(statistics.fmean(deltas[family]), 3)
                for family in FAMILIES
            },
        }
    return {
        "primary_estimand": "available",
        "profiles": profiles,
        "exploratory_pairwise_deltas": pairwise,
    }


def verify_revealed_commitments(
    public_manifest: Mapping[str, Any], completed_artifact: Mapping[str, Any]
) -> None:
    """Verify the terminal schedule and family-map reveal against precommitment."""

    reveal = completed_artifact.get("commitment_reveal")
    try:
        nonce = bytes.fromhex(str(reveal.get("schedule_nonce_hex")))
    except (AttributeError, ValueError):
        raise ValueError("Completed matched panel has no valid commitment reveal") from None
    if len(nonce) != 32:
        raise ValueError("Completed matched panel has no valid commitment reveal")
    schedule = completed_artifact.get("schedule")
    episodes = completed_artifact.get("episodes")
    if not isinstance(schedule, list) or not isinstance(episodes, list):
        raise ValueError("Completed matched-panel reveal is malformed")
    committed_schedule = [
        {
            "episode_ref": item.get("episode_ref"),
            "profile_order": item.get("profile_order"),
        }
        for item in schedule
        if isinstance(item, dict)
    ]
    if len(committed_schedule) != EPISODE_COUNT:
        raise ValueError("Completed matched-panel schedule is incomplete")
    if public_manifest.get("private_schedule_commitment") != _schedule_commitment(
        committed_schedule, nonce
    ):
        raise ValueError("Revealed schedule does not match its precommitment")
    family_episodes = [
        {"episode_ref": item.get("episode_ref"), "family": item.get("family")}
        for item in episodes
        if isinstance(item, dict)
    ]
    if len(family_episodes) != EPISODE_COUNT or public_manifest.get(
        "private_family_map_commitment"
    ) != _family_map_commitment(family_episodes, nonce):
        raise ValueError("Revealed family map does not match its precommitment")


def _terminal_replay_payload(
    assignment: Mapping[str, Any], episode: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate and bind a private trace for a terminal, not-yet-public artifact."""

    raw_result = assignment.get("raw_result")
    if not isinstance(raw_result, Mapping):
        raise ValueError("Completed assignment has no authenticated raw result")
    trace = validate_replay_trace(raw_result.get("replay_trace"))
    episode_ref = str(assignment["episode_ref"])
    profile_id = str(assignment["profile_id"])
    pack_commitment = str(episode["pack_commitment"])
    return {
        "trace_status": "recorded",
        "replay_trace": trace,
        "replay_trace_sha256": replay_trace_sha256(
            trace,
            episode_ref=episode_ref,
            profile_id=profile_id,
            pack_commitment=pack_commitment,
        ),
    }


def _no_action_projection(
    trace: Mapping[str, Any],
) -> tuple[tuple[int, int, int, int], ...]:
    return tuple(
        (
            int(frame["minute"]),
            int(frame["no_action_currently_infected"]),
            int(frame["no_action_cumulative_infections"]),
            int(frame["no_action_reporting_artifacts"]),
        )
        for frame in trace["frames"]
    )


def _complete_artifact(
    public_manifest: Mapping[str, Any], private: Mapping[str, Any]
) -> dict[str, Any]:
    episodes = {str(item["episode_ref"]): item for item in private["episodes"]}
    results: list[dict[str, Any]] = []
    no_action_by_episode: dict[
        str, tuple[tuple[int, int, int, int], ...]
    ] = {}
    recorded_by_episode: Counter[str] = Counter()
    voids = 0
    for assignment in private["assignments"]:
        episode = episodes[str(assignment["episode_ref"])]
        if assignment["status"] == "complete":
            result = dict(assignment["public_result"])
            result["family"] = episode["family"]
            replay = _terminal_replay_payload(assignment, episode)
            result.update(replay)
            episode_ref = str(assignment["episode_ref"])
            projection = _no_action_projection(replay["replay_trace"])
            prior = no_action_by_episode.setdefault(episode_ref, projection)
            if not hmac.compare_digest(
                _component_hash(prior), _component_hash(projection)
            ):
                raise ValueError(
                    "Matched profiles disagree on the no-action replay twin"
                )
            recorded_by_episode[episode_ref] += 1
        else:
            voids += 1
            result = {
                "episode_ref": assignment["episode_ref"],
                "profile_id": assignment["profile_id"],
                "family": episode["family"],
                "status": "transport_void",
                "reason": assignment.get("void_reason", "transport_unavailable"),
                "trace_status": "unavailable_transport_void",
            }
        results.append(result)
    if voids == 0 and (
        set(recorded_by_episode) != set(episodes)
        or set(recorded_by_episode.values()) != {len(PROFILES)}
    ):
        raise ValueError("Complete panel is missing matched replay traces")
    summary = (
        aggregate_complete_results(results)
        if voids == 0
        else {
            "primary_estimand": "unavailable_due_to_transport_voids",
            "transport_voids": voids,
            "fixed_denominator_means_reported": False,
        }
    )
    artifact: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "panel_id": PANEL_ID,
        "precommitment_sha256": public_manifest["precommitment_sha256"],
        "development_only": True,
        "hermetic": False,
        "leaderboard_eligible": False,
        "status": "complete" if voids == 0 else "complete_with_transport_voids",
        "started_at_utc": private["panel_started_at_utc"],
        "completed_at_utc": private["panel_completed_at_utc"],
        "planned_assignments": ASSIGNMENT_COUNT,
        "terminal_assignments": len(private["assignments"]),
        "transport_voids": voids,
        "episodes": [
            {
                "episode_ref": item["episode_ref"],
                "pack_commitment": item["pack_commitment"],
                "family": item["family"],
            }
            for item in sorted(private["episodes"], key=lambda value: str(value["episode_ref"]))
        ],
        "schedule": [
            {
                "episode_ref": item["episode_ref"],
                "family": episodes[str(item["episode_ref"])]["family"],
                "profile_order": list(item["profile_order"]),
            }
            for item in private["schedule"]
        ],
        "results": results,
        "summary": summary,
        "commitment_reveal": {
            "schedule_nonce_hex": private["schedule_nonce_hex"],
        },
        "cohort_retired_before_trace_publication": True,
    }
    verify_revealed_commitments(public_manifest, artifact)
    artifact["results_sha256"] = _component_hash(artifact)
    return artifact


def _run_panel_locked(
    *,
    root: Path,
    authentication_key_file: Path,
    private_state_path: Path,
    public_manifest_path: Path,
    public_results_path: Path,
    acknowledge_unbounded_provider_spend: bool = False,
) -> dict[str, Any]:
    """Run or resume the 300 assignments, never retrying a durable start."""

    if acknowledge_unbounded_provider_spend is not True:
        raise RuntimeError("Explicit acknowledgement of unbounded provider spend is required")
    _assert_distinct_paths(
        authentication_key_file,
        private_state_path,
        public_manifest_path,
        public_results_path,
    )
    authentication_key = _read_authentication_key(
        _existing_path_without_final_symlink(authentication_key_file)
    )
    private = _load_private_state(private_state_path, authentication_key)
    public_manifest = _load_json(public_manifest_path)
    manifest, packs, schedule = _validate_contracts(
        root=root,
        private=private,
        public=public_manifest,
        authentication_key=authentication_key,
    )
    cohort_manifest_path = _existing_path_without_final_symlink(
        str(private["cohort_manifest_path"])
    )
    _assert_environment_preflight(root, private, public_manifest)
    _preflight_execution(
        root=root,
        private_state_path=private_state_path,
        public_manifest_path=public_manifest_path,
        public_results_path=public_results_path,
        allowed_private_artifact_paths=(
            _cohort_retirement_path(cohort_manifest_path),
        ),
    )
    _git_output(
        root,
        "merge-base",
        "--is-ancestor",
        str(public_manifest["benchmark_base_commit"]),
        "HEAD",
    )
    if "panel_started_at_utc" not in private:
        private["panel_started_at_utc"] = _utc_now()
    existing = _load_json(public_results_path) if public_results_path.exists() else None
    if existing is not None and (
        existing.get("panel_id") != PANEL_ID
        or existing.get("precommitment_sha256") != public_manifest["precommitment_sha256"]
    ):
        raise ValueError("Public results belong to another matched panel")
    private_terminal = sum(
        item.get("status") in {"complete", "transport_void"}
        for item in private.get("assignments", [])
    )
    if existing is not None:
        public_terminal = existing.get("terminal_assignments")
        if type(public_terminal) is not int or public_terminal < 0:
            raise ValueError("Public matched-panel progress watermark is invalid")
        if public_terminal > private_terminal:
            raise RuntimeError(
                "Private state is behind the public progress watermark; "
                "refusing to replay paid assignments"
            )
    if private.get("status") == "complete":
        expected = _complete_artifact(public_manifest, private)
        _ensure_terminal_cohort_retirement(
            cohort_manifest_path=cohort_manifest_path,
            manifest=manifest,
            public_manifest=public_manifest,
            artifact=expected,
            authentication_key=authentication_key,
        )
        if existing is not None and existing.get("status", "").startswith("complete"):
            if existing != expected:
                raise ValueError("Completed public artifact differs from private state")
            return existing
        _atomic_json(public_results_path, expected)
        return expected

    assignments = private["assignments"]
    if assignments and assignments[-1]["status"] == "started":
        assignments[-1]["status"] = "transport_void"
        assignments[-1]["finished_at_utc"] = _utc_now()
        assignments[-1]["void_reason"] = "interrupted_after_durable_start"
        private["status"] = "running"
        _write_private_state(private_state_path, private, authentication_key)
        stopped = _public_running(public_manifest, private, status="stopped_transport_void")
        _atomic_json(public_results_path, stopped)
        return stopped

    private["status"] = "running"
    _write_private_state(private_state_path, private, authentication_key)
    _atomic_json(public_results_path, _public_running(public_manifest, private))
    episode_by_ref = {str(item["episode_ref"]): item for item in private["episodes"]}
    keys = _assignment_keys(schedule)
    cli_versions = {
        str(item["name"]): str(item["version"])
        for item in public_manifest["cli_contract"]["executables"]
    }
    timeout = int(public_manifest["timeout_contract"]["seconds_per_assignment"])
    budget = float(
        public_manifest["budget_contract"]["claude_max_budget_usd_per_assignment"]
    )
    for ref, profile_id in keys[len(assignments) :]:
        profile = _PROFILE_BY_ID[profile_id]
        episode = episode_by_ref[ref]
        pack = packs[ref]
        launch_kwargs = pack.launch_kwargs(
            expected_generator_fingerprint=str(
                public_manifest["cohort"]["generator_fingerprint"]
            ),
            cohort_manifest=manifest,
            expected_pack_set_commitment=str(
                public_manifest["cohort"]["pack_set_commitment"]
            ),
        )
        started = _utc_now()
        marker: dict[str, Any] = {
            "episode_ref": ref,
            "profile_id": profile_id,
            "status": "started",
            "started_at_utc": started,
        }
        assignments.append(marker)
        _write_private_state(private_state_path, private, authentication_key)
        _atomic_json(public_results_path, _public_running(public_manifest, private))
        try:
            result = evaluate_local_cli_agent(
                str(profile["system"]),
                **launch_kwargs,
                model=str(profile["requested_model"]),
                executable=str(profile["executable"]),
                timeout_seconds=timeout,
                claude_max_budget_usd=budget,
                claude_effort=(
                    "high" if profile["system"] == "claude" else None
                ),
            )
            marker["raw_result"] = asdict(result)
            _raise_on_harness_startup_failure(result)
            if (
                result.system != profile["system"]
                or result.requested_model != profile["requested_model"]
                or result.cli_version != cli_versions[str(profile["executable"])]
            ):
                raise RuntimeError("Provider result differs from its pinned profile")
            finished = _utc_now()
            sanitized = _sanitize_result(
                episode=episode,
                profile=profile,
                result=result,
                started_at=started,
                finished_at=finished,
            )
        except Exception as error:
            marker["status"] = "transport_void"
            marker["finished_at_utc"] = _utc_now()
            marker["void_reason"] = type(error).__name__
            private["status"] = "running"
            _write_private_state(private_state_path, private, authentication_key)
            stopped = _public_running(
                public_manifest, private, status="stopped_transport_void"
            )
            _atomic_json(public_results_path, stopped)
            return stopped
        marker["status"] = "complete"
        marker["finished_at_utc"] = finished
        marker["public_result"] = sanitized
        _write_private_state(private_state_path, private, authentication_key)
        _atomic_json(public_results_path, _public_running(public_manifest, private))

    if len(assignments) != ASSIGNMENT_COUNT or any(
        assignment["status"] not in {"complete", "transport_void"}
        for assignment in assignments
    ):
        raise RuntimeError(
            f"Matched panel did not reach {ASSIGNMENT_COUNT} terminal assignments"
        )
    private["status"] = "complete"
    private["panel_completed_at_utc"] = _utc_now()
    _write_private_state(private_state_path, private, authentication_key)
    artifact = _complete_artifact(public_manifest, private)
    _ensure_terminal_cohort_retirement(
        cohort_manifest_path=cohort_manifest_path,
        manifest=manifest,
        public_manifest=public_manifest,
        artifact=artifact,
        authentication_key=authentication_key,
    )
    _atomic_json(public_results_path, artifact)
    return artifact


def run_panel(
    *,
    root: Path,
    authentication_key_file: Path,
    private_state_path: Path,
    public_manifest_path: Path,
    public_results_path: Path,
    acknowledge_unbounded_provider_spend: bool = False,
) -> dict[str, Any]:
    """Run or resume the panel under one exclusive at-most-once lease."""

    if acknowledge_unbounded_provider_spend is not True:
        raise RuntimeError(
            "Explicit acknowledgement of unbounded provider spend is required"
        )
    with _exclusive_run_lock(private_state_path):
        return _run_panel_locked(
            root=root,
            authentication_key_file=authentication_key_file,
            private_state_path=private_state_path,
            public_manifest_path=public_manifest_path,
            public_results_path=public_results_path,
            acknowledge_unbounded_provider_spend=True,
        )
