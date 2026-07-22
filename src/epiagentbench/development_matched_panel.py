"""Precommitted 50-episode, six-profile development comparison.

This host-networked runner is deliberately ineligible for a leaderboard.  It
binds a fresh authenticated LTC-v3 cohort, hides families and execution order
until completion, checkpoints every provider attempt, and never retries an
assignment once its started marker has reached durable storage.
"""

from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from dataclasses import asdict, replace
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
from tempfile import TemporaryDirectory
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlsplit

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
from .pilot import (
    CodexAuthenticationIncidentError,
    PilotRunResult,
    ProviderExecutionIsolationError,
    ProviderOutputOverflowError,
    ProviderProcessIsolationError,
    ProviderStateIsolationError,
    _ProviderTemporaryDirectory,
    _attest_codex_auth_storage,
    _attest_claude_secure_storage_keychain,
    _attest_managed_glean_home_link,
    _canonical_codex_auth_storage_path,
    _install_disposable_storage_roots,
    _isolate_claude_environment,
    _isolate_identity_environment,
    _quiesce_provider_process_group,
    _retain_path_and_locale,
    _reject_claude_plaintext_fallback,
    _run_provider_process_group,
    _task_prompt,
    evaluate_local_cli_agent,
)
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


PANEL_ID = "development-matched-50x6-v8"
COHORT_ID = PANEL_ID
SCHEMA_VERSION = "development_matched_panel_v8"
BACKEND = "starsim-ltc-v3"
EPISODE_COUNT = 50
EPISODES_PER_FAMILY = 10
ASSIGNMENT_COUNT = 300
BOOTSTRAP_REPLICATES = 20_000
REQUIRED_SPEND_ACKNOWLEDGEMENT = (
    "I acknowledge the replacement six-call v8 preflight and 300-assignment "
    "production run, including unbounded Codex/Cursor provider spend and up "
    "to $535 total Claude spend across the failed v2 preflight, failed v5 "
    "preflight, failed v6 authentication bootstrap, failed v7 preflight, "
    "v8 preflight, and production."
)
_SPEND_AUTHORIZATION_SCHEMA = "epiagentbench.spend_authorization.v1"
_CLAUDE_CUMULATIVE_AUTHORIZATION_CEILING_USD = 535.0
_UNBOUNDED_PROVIDER_SPEND_AUTHORIZATION = {
    "codex": "unbounded",
    "cursor": "unbounded",
}
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
        "profile_id": "codex-luna-max",
        "system": "codex",
        "requested_model": "gpt-5.6-luna",
        "requested_reasoning": "max",
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
    "NO_PROXY",
    "REQUESTS_CA_BUNDLE",
    "SSL_CERT_DIR",
    "SSL_CERT_FILE",
    "all_proxy",
    "http_proxy",
    "https_proxy",
    "no_proxy",
)
_CLAUDE_AUTH_NAMESPACE_DOMAIN = b"EpiAgentBench Claude auth namespace v2\x00"
_CODEX_AUTH_NAMESPACE_DOMAIN = b"EpiAgentBench Codex auth namespace v1\x00"
_MAX_MANAGED_GLEAN_CREDENTIAL_BYTES = 1024 * 1024
_GLEAN_HELPER_PATH = Path("/usr/local/bin/glean-helper")
_GLEAN_GATEWAY_TOKEN_WRAPPER_PATH = Path(
    "/usr/local/bin/glean-llm-gateway-token"
)
_GLEAN_CONFIG_PATH = Path("/usr/local/etc/glean/config.json")
_APPROVED_GLEAN_GATEWAY_SHA256 = (
    "sha256:85149e53b43b0d08be95efe77a15b6adbb79eac40e34857de00cbbd86180216f"
)
_APPROVED_GLEAN_GATEWAY_PATH = "/api/v1"
_GLEAN_GATEWAY_ALLOWLIST_TAG = "approved_managed_gateway_v1"
_CLAUDE_MANAGED_SETTINGS_PATH = Path(
    "/Library/Application Support/ClaudeCode/managed-settings.json"
)
_CLAUDE_OTEL_HELPER_PATH = Path("/usr/local/bin/claude-otel-helper")
_APPROVED_CLAUDE_OTEL_ENDPOINT_SHA256 = (
    "sha256:9bfd7befa14d967b990aa907cccd78aa7c93b61a9b1ab77e23cf3bb3b0c50fbe"
)
_MACOS_SECURITY_PATH = Path("/usr/bin/security")
_CLAUDE_MANAGED_ENV_KEYS = frozenset(
    {
        "ANTHROPIC_BASE_URL",
        "CLAUDE_CODE_API_KEY_HELPER_TTL_MS",
        "CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS",
        "CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY",
        "CLAUDE_CODE_ENABLE_TELEMETRY",
        "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS",
        "CLAUDE_CODE_USE_VERTEX",
        "ENABLE_TOOL_SEARCH",
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_PROTOCOL",
        "OTEL_LOGS_EXPORTER",
        "OTEL_LOGS_EXPORT_INTERVAL",
        "OTEL_METRICS_EXPORTER",
        "OTEL_METRICS_INCLUDE_ACCOUNT_UUID",
        "OTEL_METRIC_EXPORT_INTERVAL",
        "OTEL_RESOURCE_ATTRIBUTES",
        "USE_CLAUDE_PROJECT_DIR",
    }
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


def _assert_authorization_worktree(
    *,
    root: Path,
    private_state_path: Path,
    public_manifest_path: Path,
    expected_head: str | None = None,
) -> str:
    """Require authorization to bind an already committed clean manifest."""

    head_before = _git_output(root, "rev-parse", "HEAD")
    if (
        not head_before
        or expected_head is not None
        and not hmac.compare_digest(head_before, expected_head)
    ):
        raise RuntimeError(
            "Matched-panel repository HEAD changed during spend authorization"
        )
    public_relative = _relative_to_root(public_manifest_path, root)
    private_relative = _relative_to_root(private_state_path, root)
    if (
        _git_output(root, "ls-files", "--error-unmatch", public_relative)
        != public_relative
    ):
        raise RuntimeError(
            "Public matched-panel precommitment must be committed before spend "
            "authorization"
        )
    if _git_output(root, "ls-files", private_relative):
        raise RuntimeError("Private matched-panel state must never be tracked")
    metadata = private_state_path.lstat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        raise RuntimeError(
            "Private matched-panel state must be a current-user, single-link "
            "0600 regular file"
        )
    if _git_output(root, "status", "--porcelain", "--untracked-files=all"):
        raise RuntimeError(
            "Matched-panel execution worktree must be clean before spend "
            "authorization"
        )
    head_after = _git_output(root, "rev-parse", "HEAD")
    if not hmac.compare_digest(head_before, head_after):
        raise RuntimeError(
            "Matched-panel repository HEAD changed during spend authorization"
        )
    return head_before


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


def _path_is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _paths_overlap(first: Path, second: Path) -> bool:
    return _path_is_within(first, second) or _path_is_within(second, first)


def _validate_claude_secure_storage_dir(path: Path, *, root: Path) -> Path:
    """Validate the stable Claude credential namespace without following links."""

    candidate = Path(path)
    if not candidate.is_absolute():
        raise ValueError("Claude secure storage directory must be an absolute path")

    current = Path(candidate.anchor)
    for component in candidate.parts[1:]:
        current = current / component
        try:
            metadata = current.lstat()
        except OSError:
            raise ValueError(
                "Claude secure storage directory must be an existing real directory"
            ) from None
        if stat.S_ISLNK(metadata.st_mode):
            raise ValueError(
                "Claude secure storage directory must not contain symlink components"
            )

    try:
        resolved = candidate.resolve(strict=True)
        metadata = resolved.stat()
    except OSError:
        raise ValueError(
            "Claude secure storage directory must be an existing real directory"
        ) from None
    if not stat.S_ISDIR(metadata.st_mode):
        raise ValueError("Claude secure storage path must be a real directory")
    if metadata.st_uid != os.getuid():
        raise ValueError(
            "Claude secure storage directory must be owned by the current user"
        )
    if stat.S_IMODE(metadata.st_mode) != 0o700:
        raise ValueError(
            "Claude secure storage directory must have exact 0700 permissions"
        )

    resolved_root = root.resolve(strict=True)
    if _path_is_within(resolved, resolved_root):
        raise ValueError(
            "Claude secure storage directory must be outside the repository"
        )
    resolved_tmp = Path("/tmp").resolve(strict=True)
    if _path_is_within(resolved, resolved_tmp):
        raise ValueError("Claude secure storage directory must be outside /tmp")
    return resolved


def _claude_secure_storage_identity(path: Path) -> dict[str, int]:
    try:
        metadata = path.lstat()
    except OSError:
        raise RuntimeError(
            "Claude secure-storage filesystem identity is unavailable"
        ) from None
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise RuntimeError("Claude secure-storage filesystem identity changed")
    return {
        "device": int(metadata.st_dev),
        "inode": int(metadata.st_ino),
    }


def _private_claude_storage_identity(
    private: Mapping[str, Any],
) -> dict[str, int]:
    value = private.get("claude_secure_storage_identity")
    if (
        not isinstance(value, dict)
        or set(value) != {"device", "inode"}
        or any(type(value[name]) is not int or value[name] < 0 for name in value)
    ):
        raise ValueError("Invalid private Claude secure-storage identity")
    return {"device": value["device"], "inode": value["inode"]}


def _assert_claude_storage_separate_from_artifacts(
    secure_storage_dir: Path,
    *,
    cohort_manifest_path: Path,
    authentication_key_file: Path,
    private_state_path: Path,
    public_manifest_path: Path,
    additional_artifact_paths: Sequence[Path] = (),
) -> None:
    artifact_parents = [
        (cohort_manifest_path.parent.resolve(strict=True), "frozen cohort directory"),
        (
            authentication_key_file.parent.resolve(strict=True),
            "authentication-key directory",
        ),
        (private_state_path.parent.resolve(strict=False), "private-state directory"),
        (
            public_manifest_path.parent.resolve(strict=False),
            "public-manifest directory",
        ),
    ]
    artifact_parents.extend(
        (
            path.parent.resolve(strict=False),
            "additional public-artifact directory",
        )
        for path in additional_artifact_paths
    )
    for parent, label in artifact_parents:
        if _paths_overlap(secure_storage_dir, parent):
            raise ValueError(
                "Claude secure storage directory and the "
                f"{label} must not overlap"
            )


def _claude_auth_namespace_commitment(
    path: Path,
    identity: Mapping[str, int],
    key: bytes,
) -> str:
    if len(key) != 32:
        raise ValueError("Invalid Claude namespace commitment key")
    digest = hmac.new(key, digestmod=hashlib.sha256)
    digest.update(_CLAUDE_AUTH_NAMESPACE_DOMAIN)
    digest.update(os.fsencode(str(path)))
    digest.update(b"\x00")
    digest.update(_canonical_bytes(dict(identity)))
    return "hmac-sha256:" + digest.hexdigest()


def _claude_auth_contract(
    path: Path,
    identity: Mapping[str, int],
    commitment_key: bytes,
) -> dict[str, Any]:
    return {
        "schema_version": "epiagentbench.claude_auth.v3",
        "secure_storage_namespace_commitment": (
            _claude_auth_namespace_commitment(path, identity, commitment_key)
        ),
        "secure_storage_role": "stable_managed_glean_auth_only",
        "filesystem_identity": "private_device_and_inode_committed",
        "per_invocation_isolation": {
            "home_root": "fresh_with_evaluator_owned_glean_symlink",
            "config_root": "fresh",
            "session_root": "fresh",
        },
        "credential_backend": {
            "managed_glean_api_key_helper": "required",
            "persistent_allowlist": ["credentials.json"],
            "credential_contents": "never_read_or_hashed",
            "credential_file_metadata": {
                "type": "regular_nonsymlink",
                "owner": "current_uid",
                "mode": "0600",
                "hard_links": 1,
                "size_bytes_min": 1,
                "size_bytes_max": _MAX_MANAGED_GLEAN_CREDENTIAL_BYTES,
            },
            "initial_state": "absent_at_prepare",
            "preflight_bootstrap": "separate_no_model_step",
            "claude_calls": "credentials_required_before_and_after",
            "macos_keychain": "required_absent_throughout",
            "claude_plaintext_fallback": "forbidden",
        },
        "inherited_provider_routing": "scrubbed",
    }


def _validate_codex_secure_storage_dir(path: Path, *, root: Path) -> Path:
    """Validate the stable Codex credential namespace without exposing it."""

    try:
        resolved = _canonical_codex_auth_storage_path(path, allow_empty=True)
    except (TypeError, ValueError, RuntimeError):
        raise ValueError(
            "Codex secure storage directory must be an existing real 0700 directory"
        ) from None
    resolved_root = root.resolve(strict=True)
    if _path_is_within(resolved, resolved_root):
        raise ValueError(
            "Codex secure storage directory must be outside the repository"
        )
    resolved_tmp = Path("/tmp").resolve(strict=True)
    if _path_is_within(resolved, resolved_tmp):
        raise ValueError("Codex secure storage directory must be outside /tmp")
    return resolved


def _codex_secure_storage_identity(path: Path) -> dict[str, int]:
    try:
        metadata = path.lstat()
    except OSError:
        raise RuntimeError(
            "Codex secure-storage filesystem identity is unavailable"
        ) from None
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise RuntimeError("Codex secure-storage filesystem identity changed")
    return {
        "device": int(metadata.st_dev),
        "inode": int(metadata.st_ino),
    }


def _private_codex_storage_identity(
    private: Mapping[str, Any],
) -> dict[str, int]:
    value = private.get("codex_secure_storage_identity")
    if (
        not isinstance(value, dict)
        or set(value) != {"device", "inode"}
        or any(type(value[name]) is not int or value[name] < 0 for name in value)
    ):
        raise ValueError("Invalid private Codex secure-storage identity")
    return {"device": value["device"], "inode": value["inode"]}


def _assert_codex_storage_separate_from_artifacts(
    secure_storage_dir: Path,
    *,
    cohort_manifest_path: Path,
    authentication_key_file: Path,
    private_state_path: Path,
    public_manifest_path: Path,
    additional_artifact_paths: Sequence[Path] = (),
) -> None:
    artifact_parents = [
        (cohort_manifest_path.parent.resolve(strict=True), "frozen cohort directory"),
        (
            authentication_key_file.parent.resolve(strict=True),
            "authentication-key directory",
        ),
        (private_state_path.parent.resolve(strict=False), "private-state directory"),
        (
            public_manifest_path.parent.resolve(strict=False),
            "public-manifest directory",
        ),
    ]
    artifact_parents.extend(
        (
            path.parent.resolve(strict=False),
            "additional public-artifact directory",
        )
        for path in additional_artifact_paths
    )
    for parent, label in artifact_parents:
        if _paths_overlap(secure_storage_dir, parent):
            raise ValueError(
                "Codex secure storage directory and the "
                f"{label} must not overlap"
            )


def _codex_auth_namespace_commitment(
    path: Path,
    identity: Mapping[str, int],
    key: bytes,
) -> str:
    if len(key) != 32:
        raise ValueError("Invalid Codex namespace commitment key")
    digest = hmac.new(key, digestmod=hashlib.sha256)
    digest.update(_CODEX_AUTH_NAMESPACE_DOMAIN)
    digest.update(os.fsencode(str(path)))
    digest.update(b"\x00")
    digest.update(_canonical_bytes(dict(identity)))
    return "hmac-sha256:" + digest.hexdigest()


def _codex_auth_contract(
    path: Path,
    identity: Mapping[str, int],
    commitment_key: bytes,
) -> dict[str, Any]:
    return {
        "schema_version": "epiagentbench.codex_auth.v1",
        "secure_storage_namespace_commitment": (
            _codex_auth_namespace_commitment(path, identity, commitment_key)
        ),
        "secure_storage_role": "stable_codex_auth_only",
        "filesystem_identity": "private_device_and_inode_committed",
        "per_invocation_isolation": {
            "home_root": "fresh_with_evaluator_owned_codex_symlink",
            "config_root": "fresh",
            "session_root": "fresh",
        },
        "credential_backend": {
            "persistent_allowlist": ["auth.json"],
            "credential_contents": "opaque_never_parsed_hashed_or_logged",
            "credential_file_metadata": {
                "type": "regular_nonsymlink",
                "owner": "current_uid",
                "mode": "0600",
                "hard_links": 1,
                "size_bytes_min": 1,
                "size_bytes_max": 1024 * 1024,
            },
            "initial_state": "absent_at_prepare",
            "preflight_bootstrap": "dedicated_pinned_cli_oauth_no_model_call",
            "codex_calls": "credentials_required_before_and_after",
            "refresh_rotation": "pinned_cli_in_place_write_with_file_identity_fixed",
            "credential_store": "inline_file_mode_only",
            "host_auth_and_keyring": "forbidden",
            "host_writeback": "forbidden",
        },
        "inherited_provider_routing": "scrubbed",
    }


def _require_codex_credential_state(
    path: Path,
    *,
    root: Path,
    expected_identity: Mapping[str, int],
    credentials_present: bool,
) -> None:
    """Verify only Codex credential metadata and the committed namespace."""

    def assert_identity() -> None:
        resolved = _validate_codex_secure_storage_dir(path, root=root)
        if resolved != path or _codex_secure_storage_identity(path) != dict(
            expected_identity
        ):
            raise RuntimeError("Codex secure-storage filesystem identity changed")

    assert_identity()
    observed = _attest_codex_auth_storage(path, allow_empty=not credentials_present)
    assert_identity()
    if (
        _attest_codex_auth_storage(path, allow_empty=not credentials_present)
        is not observed
    ):
        raise RuntimeError("Codex credential metadata changed")
    if observed is not credentials_present:
        expectation = "present" if credentials_present else "absent"
        raise RuntimeError("Codex credential file must be " + expectation)


def _codex_auth_file_identity(path: Path) -> dict[str, int]:
    try:
        metadata = (path / "auth.json").lstat()
    except OSError:
        raise RuntimeError("Codex credential file identity is unavailable") from None
    if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise RuntimeError("Codex credential file identity changed")
    return {"device": int(metadata.st_dev), "inode": int(metadata.st_ino)}


def _private_codex_auth_file_identity(
    private: Mapping[str, Any],
) -> dict[str, int]:
    value = private.get("codex_auth_file_identity")
    if (
        not isinstance(value, dict)
        or set(value) != {"device", "inode"}
        or any(type(value[name]) is not int or value[name] < 0 for name in value)
    ):
        raise ValueError("Invalid private Codex credential file identity")
    return {"device": value["device"], "inode": value["inode"]}


def _require_codex_auth_file_identity(
    path: Path, expected_identity: Mapping[str, int]
) -> None:
    if _codex_auth_file_identity(path) != dict(expected_identity):
        raise RuntimeError("Codex credential file identity changed")


_CODEX_BOOTSTRAP_AUTH_BYTES_MAX = 1024 * 1024
_CODEX_BOOTSTRAP_DIRECTORY_FIELDS = (
    "st_dev",
    "st_ino",
    "st_mode",
    "st_uid",
)
_CODEX_BOOTSTRAP_FILE_FIELDS = (
    "st_dev",
    "st_ino",
    "st_mode",
    "st_uid",
    "st_nlink",
    "st_size",
    "st_mtime_ns",
    "st_ctime_ns",
)
_CODEX_BOOTSTRAP_PROMOTED_FILE_FIELDS = (
    "st_dev",
    "st_ino",
    "st_mode",
    "st_uid",
    "st_size",
    "st_mtime_ns",
)


def _open_codex_bootstrap_directory(path: Path) -> int:
    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        metadata = os.fstat(descriptor)
    except OSError:
        raise ProviderStateIsolationError(
            "Codex authentication bootstrap directory is unsafe"
        ) from None
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        os.close(descriptor)
        raise ProviderStateIsolationError(
            "Codex authentication bootstrap directory is unsafe"
        )
    return descriptor


def _same_codex_bootstrap_metadata(
    left: os.stat_result,
    right: os.stat_result,
    fields: Sequence[str],
) -> bool:
    return all(getattr(left, name) == getattr(right, name) for name in fields)


def _require_empty_codex_bootstrap_home(path: Path) -> None:
    descriptor = _open_codex_bootstrap_directory(path)
    try:
        before = os.fstat(descriptor)
        names = os.listdir(descriptor)
        after = os.fstat(descriptor)
    except OSError:
        raise ProviderStateIsolationError(
            "Codex authentication bootstrap directory changed"
        ) from None
    finally:
        os.close(descriptor)
    if names or not _same_codex_bootstrap_metadata(
        before, after, _CODEX_BOOTSTRAP_DIRECTORY_FIELDS
    ):
        raise ProviderStateIsolationError(
            "Codex authentication bootstrap directory changed"
        )


def _require_empty_codex_auth_target(
    path: Path, expected_identity: Mapping[str, int]
) -> None:
    try:
        identity = _codex_secure_storage_identity(path)
        populated = _attest_codex_auth_storage(path, allow_empty=True)
    except RuntimeError:
        raise ProviderStateIsolationError(
            "Codex authentication target state is unsafe"
        ) from None
    if identity != dict(expected_identity) or populated:
        raise ProviderStateIsolationError(
            "Codex authentication target changed"
        )


def _remove_promoted_codex_auth_if_owned(
    target_directory_descriptor: int,
    source_metadata: os.stat_result,
) -> bool:
    """Best-effort rollback without ever removing an unrelated target."""

    try:
        target_metadata = os.stat(
            "auth.json",
            dir_fd=target_directory_descriptor,
            follow_symlinks=False,
        )
    except OSError:
        return False
    if (
        target_metadata.st_dev != source_metadata.st_dev
        or target_metadata.st_ino != source_metadata.st_ino
    ):
        return False
    try:
        os.unlink("auth.json", dir_fd=target_directory_descriptor)
        os.fsync(target_directory_descriptor)
    except OSError:
        return False
    return True


def _promote_staged_codex_auth(
    source_directory: Path,
    target_directory: Path,
    *,
    expected_target_identity: Mapping[str, int],
) -> None:
    """Publish opaque Codex auth with a same-filesystem no-clobber move."""

    source_directory_descriptor = _open_codex_bootstrap_directory(
        source_directory
    )
    target_directory_descriptor = _open_codex_bootstrap_directory(
        target_directory
    )
    source_descriptor: int | None = None
    source_metadata: os.stat_result | None = None
    linked = False
    try:
        target_directory_metadata = os.fstat(target_directory_descriptor)
        if (
            target_directory_metadata.st_dev
            != expected_target_identity.get("device")
            or target_directory_metadata.st_ino
            != expected_target_identity.get("inode")
            or os.listdir(target_directory_descriptor)
        ):
            raise ProviderStateIsolationError(
                "Codex authentication target changed before promotion"
            )
        source_directory_metadata = os.fstat(source_directory_descriptor)
        if source_directory_metadata.st_dev != target_directory_metadata.st_dev:
            raise ProviderStateIsolationError(
                "Codex authentication staging filesystem changed"
            )

        flags = os.O_RDONLY
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        flags |= getattr(os, "O_NONBLOCK", 0)
        try:
            source_descriptor = os.open(
                "auth.json",
                flags,
                dir_fd=source_directory_descriptor,
            )
        except FileNotFoundError:
            raise RuntimeError("Codex authentication bootstrap failed") from None
        except OSError:
            raise ProviderStateIsolationError(
                "Codex authentication staged credential is unsafe"
            ) from None
        source_metadata = os.fstat(source_descriptor)
        if (
            not stat.S_ISREG(source_metadata.st_mode)
            or source_metadata.st_uid != os.getuid()
            or stat.S_IMODE(source_metadata.st_mode) != 0o600
            or source_metadata.st_nlink != 1
            or not 1
            <= source_metadata.st_size
            <= _CODEX_BOOTSTRAP_AUTH_BYTES_MAX
            or source_metadata.st_dev != target_directory_metadata.st_dev
        ):
            raise ProviderStateIsolationError(
                "Codex authentication staged credential is unsafe"
            )
        try:
            path_metadata = os.stat(
                "auth.json",
                dir_fd=source_directory_descriptor,
                follow_symlinks=False,
            )
            os.fsync(source_descriptor)
        except OSError:
            raise ProviderStateIsolationError(
                "Codex authentication staged credential changed"
            ) from None
        if not _same_codex_bootstrap_metadata(
            source_metadata, path_metadata, _CODEX_BOOTSTRAP_FILE_FIELDS
        ):
            raise ProviderStateIsolationError(
                "Codex authentication staged credential changed"
            )

        try:
            os.link(
                "auth.json",
                "auth.json",
                src_dir_fd=source_directory_descriptor,
                dst_dir_fd=target_directory_descriptor,
                follow_symlinks=False,
            )
            linked = True
            os.fsync(target_directory_descriptor)
            target_metadata = os.stat(
                "auth.json",
                dir_fd=target_directory_descriptor,
                follow_symlinks=False,
            )
            source_after_link = os.fstat(source_descriptor)
        except OSError:
            raise ProviderStateIsolationError(
                "Codex authentication credential promotion failed"
            ) from None
        if (
            target_metadata.st_dev != source_metadata.st_dev
            or target_metadata.st_ino != source_metadata.st_ino
            or target_metadata.st_nlink != 2
            or source_after_link.st_nlink != 2
        ):
            raise ProviderStateIsolationError(
                "Codex authentication credential promotion changed"
            )

        try:
            os.unlink("auth.json", dir_fd=source_directory_descriptor)
            os.fsync(source_directory_descriptor)
            os.fsync(target_directory_descriptor)
            final_target_metadata = os.stat(
                "auth.json",
                dir_fd=target_directory_descriptor,
                follow_symlinks=False,
            )
        except OSError:
            raise ProviderStateIsolationError(
                "Codex authentication credential promotion failed"
            ) from None
        try:
            os.stat(
                "auth.json",
                dir_fd=source_directory_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            pass
        except OSError:
            raise ProviderStateIsolationError(
                "Codex authentication staging state is unavailable"
            ) from None
        else:
            raise ProviderStateIsolationError(
                "Codex authentication staging entry remained after promotion"
            )
        if (
            final_target_metadata.st_dev != source_metadata.st_dev
            or final_target_metadata.st_ino != source_metadata.st_ino
            or final_target_metadata.st_nlink != 1
            or not _same_codex_bootstrap_metadata(
                source_metadata,
                final_target_metadata,
                _CODEX_BOOTSTRAP_PROMOTED_FILE_FIELDS,
            )
        ):
            raise ProviderStateIsolationError(
                "Codex authentication credential promotion changed"
            )
        linked = False
    except BaseException as error:
        rollback_failed = False
        if linked and source_metadata is not None:
            rollback_failed = not _remove_promoted_codex_auth_if_owned(
                target_directory_descriptor,
                source_metadata,
            )
        if rollback_failed:
            raise ProviderStateIsolationError(
                "Codex authentication credential promotion rollback failed"
            ) from error
        raise
    finally:
        if source_descriptor is not None:
            os.close(source_descriptor)
        os.close(target_directory_descriptor)
        os.close(source_directory_descriptor)


def _run_no_capture_process_group(
    command: Sequence[str],
    *,
    cwd: Path,
    environment: Mapping[str, str],
    timeout_seconds: int,
    stdout_target: int | None,
    stderr_target: int | None,
    umask: int,
    invocation_launch_pending: Callable[[], None] | None = None,
    invocation_started: Callable[[], None] | None = None,
    invocation_start_failed: Callable[[], None] | None = None,
    invocation_returned: Callable[[int], None] | None = None,
) -> subprocess.CompletedProcess[None]:
    """Run an authentication helper without capturing credential-bearing output."""

    if stdout_target not in {None, subprocess.DEVNULL} or stderr_target not in {
        None,
        subprocess.DEVNULL,
    }:
        raise ValueError("Authentication process output must not be captured")
    if os.name != "posix" or not hasattr(os, "killpg"):
        raise ProviderProcessIsolationError(
            "Authentication process-group isolation is unavailable"
        )

    process: subprocess.Popen[bytes] | None = None
    group_quiesced = False
    try:
        if invocation_launch_pending is not None:
            invocation_launch_pending()
        try:
            process = subprocess.Popen(
                list(command),
                cwd=cwd,
                stdin=subprocess.DEVNULL,
                stdout=stdout_target,
                stderr=stderr_target,
                env=dict(environment),
                start_new_session=True,
                umask=umask,
            )
        except (OSError, ValueError) as start_error:
            if invocation_start_failed is not None:
                try:
                    invocation_start_failed()
                except Exception:
                    raise ProviderStateIsolationError(
                        "Authentication process start-failure marker could not be persisted"
                    ) from start_error
            raise ProviderProcessIsolationError(
                "Authentication process could not be started in an isolated group"
            ) from None
        if invocation_started is not None:
            invocation_started()
        try:
            returncode = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            _quiesce_provider_process_group(process, force=True)
            group_quiesced = True
            raise subprocess.TimeoutExpired(
                list(command), timeout_seconds
            ) from None
        except OSError:
            raise ProviderProcessIsolationError(
                "Authentication process state could not be verified"
            ) from None

        _quiesce_provider_process_group(process, force=False)
        group_quiesced = True
        if invocation_returned is not None:
            invocation_returned(returncode)
        return subprocess.CompletedProcess(list(command), returncode)
    finally:
        active_error = sys.exception()
        cleanup_error: ProviderProcessIsolationError | None = None
        try:
            if process is not None:
                if not group_quiesced:
                    _quiesce_provider_process_group(process, force=True)
                try:
                    process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    raise ProviderProcessIsolationError(
                        "Authentication process leader could not be reaped"
                    ) from None
                except OSError:
                    raise ProviderProcessIsolationError(
                        "Authentication process leader state could not be verified"
                    ) from None
        except ProviderProcessIsolationError as error:
            cleanup_error = error
        if cleanup_error is not None:
            if active_error is not None:
                raise cleanup_error from active_error
            raise cleanup_error from None


def _bootstrap_codex_credentials(
    path: Path,
    *,
    executable: str,
    timeout_seconds: int,
    invocation_launch_pending: Callable[[], None] | None = None,
    invocation_started: Callable[[], None] | None = None,
    invocation_start_failed: Callable[[], None] | None = None,
    invocation_returned: Callable[[int], None] | None = None,
) -> None:
    """Obtain independent file-backed Codex OAuth credentials without a model call."""

    resolved_executable = shutil.which(executable)
    if resolved_executable is None:
        raise RuntimeError("Codex authentication bootstrap executable is unavailable")
    try:
        resolved_path = path.resolve(strict=True)
    except (OSError, RuntimeError):
        raise ProviderStateIsolationError(
            "Codex authentication target is unavailable"
        ) from None
    if resolved_path != path:
        raise ProviderStateIsolationError(
            "Codex authentication target is unsafe"
        )
    try:
        target_identity = _codex_secure_storage_identity(path)
    except RuntimeError:
        raise ProviderStateIsolationError(
            "Codex authentication target state is unsafe"
        ) from None
    _require_empty_codex_auth_target(path, target_identity)
    with _ProviderTemporaryDirectory(directory=path.parent) as temporary:
        root = Path(temporary).resolve()
        try:
            root_metadata = root.lstat()
            parent_metadata = path.parent.lstat()
        except OSError:
            raise ProviderStateIsolationError(
                "Codex authentication staging directory is unavailable"
            ) from None
        if (
            root.parent != path.parent
            or root_metadata.st_dev != target_identity["device"]
            or root_metadata.st_dev != parent_metadata.st_dev
            or not stat.S_ISDIR(root_metadata.st_mode)
            or stat.S_ISLNK(root_metadata.st_mode)
            or root_metadata.st_uid != os.getuid()
            or stat.S_IMODE(root_metadata.st_mode) != 0o700
        ):
            raise ProviderStateIsolationError(
                "Codex authentication staging directory is unsafe"
            )
        environment = os.environ.copy()
        _retain_path_and_locale(environment)
        isolated = _install_disposable_storage_roots(
            environment, root, namespace="codex-login"
        )
        codex_home = isolated["HOME"] / ".codex"
        try:
            codex_home.mkdir(mode=0o700)
            codex_home.chmod(0o700)
        except OSError:
            raise ProviderStateIsolationError(
                "Codex authentication bootstrap isolation failed"
            ) from None
        _require_empty_codex_bootstrap_home(codex_home)
        _require_empty_codex_auth_target(path, target_identity)
        environment["CODEX_HOME"] = str(codex_home)
        try:
            process = _run_no_capture_process_group(
                [
                    resolved_executable,
                    "login",
                    "-c",
                    'cli_auth_credentials_store="file"',
                ],
                cwd=root,
                environment=environment,
                timeout_seconds=timeout_seconds,
                stdout_target=subprocess.DEVNULL,
                stderr_target=subprocess.DEVNULL,
                umask=0o077,
                invocation_launch_pending=invocation_launch_pending,
                invocation_started=invocation_started,
                invocation_start_failed=invocation_start_failed,
                invocation_returned=invocation_returned,
            )
        except ProviderExecutionIsolationError:
            raise
        except subprocess.SubprocessError:
            raise RuntimeError("Codex authentication bootstrap failed") from None
        if process.returncode != 0:
            raise RuntimeError("Codex authentication bootstrap failed")
        _require_empty_codex_auth_target(path, target_identity)
        _promote_staged_codex_auth(
            codex_home,
            path,
            expected_target_identity=target_identity,
        )
        _attest_codex_auth_storage(path)


def _validate_codex_auth_binding(
    *,
    root: Path,
    codex_secure_storage_dir: Path,
    private: Mapping[str, Any],
    public: Mapping[str, Any],
) -> Path:
    resolved = _validate_codex_secure_storage_dir(
        codex_secure_storage_dir, root=root
    )
    if private.get("codex_secure_storage_dir") != str(resolved):
        raise ValueError(
            "Codex secure storage directory does not match authenticated private state"
        )
    try:
        commitment_key = bytes.fromhex(
            str(private.get("codex_auth_commitment_key_hex", ""))
        )
    except ValueError:
        raise ValueError("Invalid private Codex namespace commitment key") from None
    if len(commitment_key) != 32:
        raise ValueError("Invalid private Codex namespace commitment key")
    expected_identity = _private_codex_storage_identity(private)
    if _codex_secure_storage_identity(resolved) != expected_identity:
        raise ValueError("Codex secure-storage filesystem identity changed")
    expected = _codex_auth_contract(
        resolved,
        expected_identity,
        commitment_key,
    )
    if public.get("codex_auth_contract") != expected:
        raise ValueError("Codex secure storage namespace commitment mismatch")
    return resolved


def _attest_managed_glean_credentials(path: Path) -> bool:
    """Validate the exact persistent tree using metadata only."""

    try:
        root_metadata = path.lstat()
    except OSError:
        raise RuntimeError("Managed Glean credential metadata is unavailable") from None
    if (
        not stat.S_ISDIR(root_metadata.st_mode)
        or stat.S_ISLNK(root_metadata.st_mode)
        or root_metadata.st_uid != os.getuid()
        or stat.S_IMODE(root_metadata.st_mode) != 0o700
    ):
        raise RuntimeError("Managed Glean credential directory is unsafe")
    try:
        names = {entry.name for entry in os.scandir(path)}
    except OSError:
        raise RuntimeError("Managed Glean credential metadata is unavailable") from None
    if not names:
        try:
            if any(True for _entry in os.scandir(path)):
                raise RuntimeError("Managed Glean credential metadata changed")
        except OSError:
            raise RuntimeError("Managed Glean credential metadata changed") from None
        return False
    if names != {"credentials.json"}:
        raise RuntimeError("Managed Glean credential directory has unexpected entries")

    credential_path = path / "credentials.json"
    try:
        metadata = credential_path.lstat()
    except OSError:
        raise RuntimeError("Managed Glean credential metadata is unavailable") from None
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_nlink != 1
        or not 1 <= metadata.st_size <= _MAX_MANAGED_GLEAN_CREDENTIAL_BYTES
    ):
        raise RuntimeError("Managed Glean credential file metadata is unsafe")

    stable_fields = (
        "st_dev",
        "st_ino",
        "st_mode",
        "st_uid",
        "st_nlink",
        "st_size",
        "st_mtime_ns",
        "st_ctime_ns",
    )
    try:
        final_names = {entry.name for entry in os.scandir(path)}
        final_metadata = credential_path.lstat()
    except OSError:
        raise RuntimeError("Managed Glean credential metadata changed") from None
    if final_names != names or any(
        getattr(final_metadata, field) != getattr(metadata, field)
        for field in stable_fields
    ):
        raise RuntimeError("Managed Glean credential metadata changed")
    return True


def _require_claude_credential_state(
    path: Path,
    *,
    root: Path,
    expected_identity: Mapping[str, int],
    managed_glean_credentials_present: bool,
) -> None:
    """Verify credential metadata without retrieving credential contents."""

    def assert_identity() -> None:
        resolved = _validate_claude_secure_storage_dir(path, root=root)
        if resolved != path or _claude_secure_storage_identity(path) != dict(
            expected_identity
        ):
            raise RuntimeError("Claude secure-storage filesystem identity changed")

    assert_identity()
    _reject_claude_plaintext_fallback(path)
    observed = _attest_managed_glean_credentials(path)
    keychain_present = _attest_claude_secure_storage_keychain(path)
    assert_identity()
    if _attest_managed_glean_credentials(path) is not observed:
        raise RuntimeError("Managed Glean credential metadata changed")
    if keychain_present:
        raise RuntimeError("Claude Keychain record must remain absent")
    if observed is not managed_glean_credentials_present:
        expectation = "present" if managed_glean_credentials_present else "absent"
        raise RuntimeError(
            "Managed Glean credential file must be " + expectation
        )


def _bootstrap_managed_glean_credentials(
    path: Path,
    *,
    oauth_client_id: str,
    timeout_seconds: int,
    invocation_launch_pending: Callable[[], None] | None = None,
    invocation_started: Callable[[], None] | None = None,
    invocation_start_failed: Callable[[], None] | None = None,
    invocation_returned: Callable[[int], None] | None = None,
) -> None:
    """Run the pinned helper without capturing its token-bearing stdout."""

    with _ProviderTemporaryDirectory() as temporary:
        root = Path(temporary).resolve()
        environment = os.environ.copy()
        glean_home_link = _isolate_claude_environment(
            environment, root, path, oauth_client_id
        )
        if glean_home_link is None:
            raise RuntimeError("Managed Glean bootstrap isolation failed")
        _attest_managed_glean_home_link(glean_home_link, path)
        try:
            process = _run_no_capture_process_group(
                [str(_GLEAN_GATEWAY_TOKEN_WRAPPER_PATH)],
                cwd=root,
                environment=environment,
                timeout_seconds=timeout_seconds,
                stdout_target=subprocess.DEVNULL,
                stderr_target=None,
                umask=0o077,
                invocation_launch_pending=invocation_launch_pending,
                invocation_started=invocation_started,
                invocation_start_failed=invocation_start_failed,
                invocation_returned=invocation_returned,
            )
        except ProviderExecutionIsolationError:
            raise
        except subprocess.SubprocessError:
            raise RuntimeError("Managed Glean authentication bootstrap failed") from None
        finally:
            active_error = sys.exception()
            try:
                _attest_managed_glean_home_link(glean_home_link, path)
            except Exception:
                if not isinstance(
                    active_error, ProviderExecutionIsolationError
                ):
                    raise
        if process.returncode != 0:
            raise RuntimeError("Managed Glean authentication bootstrap failed")


def _validate_claude_auth_binding(
    *,
    root: Path,
    claude_secure_storage_dir: Path,
    private: Mapping[str, Any],
    public: Mapping[str, Any],
) -> Path:
    resolved = _validate_claude_secure_storage_dir(
        claude_secure_storage_dir, root=root
    )
    if private.get("claude_secure_storage_dir") != str(resolved):
        raise ValueError(
            "Claude secure storage directory does not match authenticated private state"
        )
    try:
        commitment_key = bytes.fromhex(
            str(private.get("claude_auth_commitment_key_hex", ""))
        )
    except ValueError:
        raise ValueError("Invalid private Claude namespace commitment key") from None
    if len(commitment_key) != 32:
        raise ValueError("Invalid private Claude namespace commitment key")
    expected_identity = _private_claude_storage_identity(private)
    if _claude_secure_storage_identity(resolved) != expected_identity:
        raise ValueError("Claude secure-storage filesystem identity changed")
    expected = _claude_auth_contract(
        resolved,
        expected_identity,
        commitment_key,
    )
    if public.get("claude_auth_contract") != expected:
        raise ValueError("Claude secure storage namespace commitment mismatch")
    return resolved


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


def _identity_version_probe(command: Sequence[str], *, label: str) -> str:
    """Read a bounded version string in a credential-free process group."""

    try:
        with _ProviderTemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            environment = os.environ.copy()
            _isolate_identity_environment(environment, root)
            process = _run_provider_process_group(
                command,
                cwd=root,
                environment=environment,
                timeout_seconds=15,
                umask=0o077,
            )
    except ProviderExecutionIsolationError:
        raise
    except (ProviderOutputOverflowError, subprocess.TimeoutExpired):
        raise ProviderStateIsolationError(
            f"Unable to pin {label} version"
        ) from None
    except (OSError, RuntimeError, ValueError):
        raise ProviderStateIsolationError(
            f"Unable to pin {label} version"
        ) from None
    version = (process.stdout + b"\n" + process.stderr).decode(
        "utf-8", errors="replace"
    ).strip()[:200]
    if process.returncode != 0 or not version:
        raise ProviderStateIsolationError(f"Unable to pin {label} version")
    return version


def _read_cli_identity(executable: str) -> dict[str, str]:
    try:
        resolved = shutil.which(executable)
        if resolved is None:
            raise ProviderStateIsolationError(
                f"Required provider CLI is unavailable: {executable}"
            )
        resolved_path = Path(resolved).resolve(strict=True)
        if not resolved_path.is_file() or resolved_path.is_symlink():
            raise ProviderStateIsolationError(
                f"Provider CLI is not a regular executable: {executable}"
            )
        digest = _fixed_file_sha256(
            resolved_path, label=f"provider CLI {executable}"
        )
    except ProviderExecutionIsolationError:
        raise
    except (OSError, RuntimeError):
        raise ProviderStateIsolationError(
            f"Unable to pin provider CLI identity: {executable}"
        ) from None
    version = _identity_version_probe(
        [str(resolved_path), "--version"], label=f"provider CLI {executable}"
    )
    try:
        final_digest = _fixed_file_sha256(
            resolved_path, label=f"provider CLI {executable}"
        )
    except (OSError, RuntimeError):
        raise ProviderStateIsolationError(
            f"Provider CLI changed during identity probe: {executable}"
        ) from None
    if final_digest != digest:
        raise ProviderStateIsolationError(
            f"Provider CLI changed during identity probe: {executable}"
        )
    return {
        "name": executable,
        "version": version,
        "executable_sha256": digest,
    }


def _fixed_file_sha256(path: Path, *, label: str) -> str:
    """Hash one stable nonsymlink file through an attested descriptor."""

    descriptor: int | None = None
    try:
        metadata = path.lstat()
    except OSError:
        raise RuntimeError(f"Required {label} is unavailable") from None
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_nlink < 1
    ):
        raise RuntimeError(f"Required {label} must be a regular file")
    stable_fields = (
        "st_dev",
        "st_ino",
        "st_mode",
        "st_uid",
        "st_gid",
        "st_nlink",
        "st_size",
        "st_mtime_ns",
        "st_ctime_ns",
    )
    digest = hashlib.sha256()
    try:
        flags = os.O_RDONLY
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if any(
            getattr(opened, field) != getattr(metadata, field)
            for field in stable_fields
        ):
            raise RuntimeError(f"Required {label} changed while opening")
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        after = os.fstat(descriptor)
        final_metadata = path.lstat()
        if any(
            getattr(after, field) != getattr(metadata, field)
            or getattr(final_metadata, field) != getattr(metadata, field)
            for field in stable_fields
        ):
            raise RuntimeError(f"Required {label} changed while hashing")
    except RuntimeError:
        raise
    except OSError:
        raise RuntimeError(f"Unable to hash required {label}") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return "sha256:" + digest.hexdigest()


def _decode_unique_json(encoded: bytes, *, label: str) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError
            value[key] = item
        return value

    try:
        decoded = json.loads(
            encoded.decode("utf-8"), object_pairs_hook=reject_duplicates
        )
    except (UnicodeError, ValueError, TypeError):
        raise RuntimeError(f"Required {label} JSON is invalid") from None
    if not isinstance(decoded, dict):
        raise RuntimeError(f"Required {label} JSON is invalid")
    return decoded


def _read_root_owned_json(
    path: Path, *, label: str, max_bytes: int = 64 * 1024
) -> tuple[bytes, dict[str, Any]]:
    """Read one bounded, root-owned JSON policy file with duplicate rejection."""

    try:
        metadata = path.lstat()
    except OSError:
        raise RuntimeError(f"Required {label} is unavailable") from None
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != 0
        or metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
        or metadata.st_nlink != 1
        or not 1 <= metadata.st_size <= max_bytes
    ):
        raise RuntimeError(f"Required {label} metadata is unsafe")
    stable_fields = (
        "st_dev",
        "st_ino",
        "st_mode",
        "st_uid",
        "st_nlink",
        "st_size",
        "st_mtime_ns",
        "st_ctime_ns",
    )
    descriptor: int | None = None
    try:
        flags = os.O_RDONLY
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if any(
            getattr(opened, field) != getattr(metadata, field)
            for field in stable_fields
        ):
            raise RuntimeError(f"Required {label} changed while opening")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(64 * 1024, max_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes:
                raise RuntimeError(f"Required {label} exceeds its size bound")
        encoded = b"".join(chunks)
        after = os.fstat(descriptor)
        final_metadata = path.lstat()
        if (
            len(encoded) != metadata.st_size
            or any(
                getattr(after, field) != getattr(metadata, field)
                or getattr(final_metadata, field) != getattr(metadata, field)
                for field in stable_fields
            )
        ):
            raise RuntimeError(f"Required {label} changed while reading")
    except RuntimeError:
        raise
    except OSError:
        raise RuntimeError(f"Unable to read required {label}") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return encoded, _decode_unique_json(encoded, label=label)


def _safe_glean_config() -> tuple[dict[str, Any], dict[str, Any]]:
    encoded, config = _read_root_owned_json(
        _GLEAN_CONFIG_PATH, label="Glean configuration"
    )
    forbidden_fragments = ("secret", "token", "password", "api_key", "apikey")

    def assert_safe_keys(value: Any) -> None:
        if not isinstance(value, dict):
            return
        for key, item in value.items():
            normalized = str(key).lower().replace("-", "_")
            if any(fragment in normalized for fragment in forbidden_fragments):
                raise RuntimeError("Glean configuration contains a forbidden field")
            assert_safe_keys(item)

    assert_safe_keys(config)
    oauth = config.get("oauth")
    claude = oauth.get("claude") if isinstance(oauth, dict) else None
    codex = oauth.get("codex") if isinstance(oauth, dict) else None
    if (
        set(config) != {"gateway_url", "oauth"}
        or not isinstance(oauth, dict)
        or set(oauth) != {"claude", "codex"}
        or not isinstance(claude, dict)
        or set(claude) != {"client_id"}
        or not isinstance(codex, dict)
        or set(codex) != {"client_id"}
    ):
        raise RuntimeError("Glean configuration schema is unsafe")
    gateway_url = config.get("gateway_url")
    claude_client_id = claude.get("client_id")
    codex_client_id = codex.get("client_id")
    if any(
        not isinstance(value, str)
        or not value
        or len(value) > 2048
        or any(character.isspace() for character in value)
        for value in (gateway_url, claude_client_id, codex_client_id)
    ):
        raise RuntimeError("Glean configuration values are unsafe")
    try:
        parsed_gateway = urlsplit(gateway_url)
        gateway_port = parsed_gateway.port
    except ValueError:
        raise RuntimeError("Glean gateway URL is unsafe") from None
    if (
        _sha256(gateway_url.encode("utf-8"))
        != _APPROVED_GLEAN_GATEWAY_SHA256
        or parsed_gateway.scheme != "https"
        or not parsed_gateway.hostname
        or gateway_port is not None
        or parsed_gateway.path != _APPROVED_GLEAN_GATEWAY_PATH
        or parsed_gateway.username is not None
        or parsed_gateway.password is not None
        or parsed_gateway.query
        or parsed_gateway.fragment
    ):
        raise RuntimeError("Glean gateway URL is unsafe")
    identity = {
        "path": str(_GLEAN_CONFIG_PATH),
        "sha256": _sha256(encoded),
        "semantic_projection": {
            "schema": "gateway_url_plus_claude_and_codex_oauth_client_ids_only",
            "gateway_scheme": "https",
            "gateway_endpoint_allowlist_tag": _GLEAN_GATEWAY_ALLOWLIST_TAG,
            "gateway_port": "default_https",
            "gateway_url_sha256": _sha256(gateway_url.encode("utf-8")),
            "claude_client_id_sha256": _sha256(
                claude_client_id.encode("utf-8")
            ),
            "codex_client_id_sha256": _sha256(
                codex_client_id.encode("utf-8")
            ),
            "contains_secret_bearing_fields": False,
        },
    }
    return config, identity


def _managed_settings_identity(
    glean_config: Mapping[str, Any],
) -> tuple[dict[str, Any], bool]:
    _encoded, settings = _read_root_owned_json(
        _CLAUDE_MANAGED_SETTINGS_PATH,
        label="Claude managed settings",
    )
    sensitive_fragments = (
        "secret",
        "token",
        "password",
        "api_key",
        "apikey",
        "auth",
        "header",
    )
    sensitive_field_exceptions = {
        ("apiKeyHelper",),
        ("otelHeadersHelper",),
        ("env", "CLAUDE_CODE_API_KEY_HELPER_TTL_MS"),
    }

    def reject_sensitive_fields(value: Any, path: tuple[str, ...] = ()) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                child_path = (*path, str(key))
                normalized = str(key).lower().replace("-", "_")
                if (
                    any(
                        fragment in normalized
                        for fragment in sensitive_fragments
                    )
                    and child_path not in sensitive_field_exceptions
                ):
                    raise RuntimeError(
                        "Claude managed settings contain a forbidden sensitive field"
                    )
                reject_sensitive_fields(item, child_path)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                reject_sensitive_fields(item, (*path, str(index)))

    reject_sensitive_fields(settings)
    if set(settings) != {"apiKeyHelper", "env", "otelHeadersHelper"}:
        raise RuntimeError("Claude managed settings top-level schema drifted")
    environment = settings.get("env")
    if (
        not isinstance(environment, dict)
        or set(environment) != _CLAUDE_MANAGED_ENV_KEYS
    ):
        raise RuntimeError("Claude managed settings environment schema drifted")

    expected_environment: dict[str, Any] = {
        "ANTHROPIC_BASE_URL": (
            str(glean_config["gateway_url"]).rstrip("/") + "/anthropic"
        ),
        "CLAUDE_CODE_API_KEY_HELPER_TTL_MS": "1800000",
        "CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS": "1",
        "CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY": "1",
        "CLAUDE_CODE_ENABLE_TELEMETRY": 1,
        "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1",
        "CLAUDE_CODE_USE_VERTEX": 0,
        "ENABLE_TOOL_SEARCH": 1,
        "OTEL_EXPORTER_OTLP_PROTOCOL": "http/json",
        "OTEL_LOGS_EXPORTER": "otlp",
        "OTEL_LOGS_EXPORT_INTERVAL": "5000",
        "OTEL_METRICS_EXPORTER": "otlp",
        "OTEL_METRICS_INCLUDE_ACCOUNT_UUID": "true",
        "OTEL_METRIC_EXPORT_INTERVAL": "60000",
        "USE_CLAUDE_PROJECT_DIR": "1",
    }
    for key, expected_value in expected_environment.items():
        observed_value = environment[key]
        if (
            type(observed_value) is not type(expected_value)
            or observed_value != expected_value
        ):
            raise RuntimeError("Claude managed settings value policy drifted")

    otel_endpoint = environment["OTEL_EXPORTER_OTLP_ENDPOINT"]
    if not isinstance(otel_endpoint, str):
        raise RuntimeError("Claude managed OTEL endpoint policy drifted")
    try:
        parsed_otel_endpoint = urlsplit(otel_endpoint)
        otel_endpoint_port = parsed_otel_endpoint.port
    except ValueError:
        raise RuntimeError("Claude managed OTEL endpoint policy drifted") from None
    if (
        _sha256(otel_endpoint.encode("utf-8"))
        != _APPROVED_CLAUDE_OTEL_ENDPOINT_SHA256
        or parsed_otel_endpoint.scheme != "https"
        or not parsed_otel_endpoint.hostname
        or otel_endpoint_port is not None
        or parsed_otel_endpoint.username is not None
        or parsed_otel_endpoint.password is not None
        or parsed_otel_endpoint.query
        or parsed_otel_endpoint.fragment
    ):
        raise RuntimeError("Claude managed OTEL endpoint policy drifted")

    resource_attributes = environment["OTEL_RESOURCE_ATTRIBUTES"]
    if (
        not isinstance(resource_attributes, str)
        or not resource_attributes.startswith("user.email=")
        or resource_attributes.count("=") != 1
        or "," in resource_attributes
        or len(resource_attributes) > 320
    ):
        raise RuntimeError("Claude managed OTEL resource policy drifted")
    resource_email = resource_attributes.removeprefix("user.email=")
    if (
        not resource_email
        or not resource_email.isascii()
        or resource_email.count("@") != 1
        or any(
            character.isspace() or ord(character) < 0x20
            for character in resource_email
        )
    ):
        raise RuntimeError("Claude managed OTEL resource policy drifted")

    if settings["apiKeyHelper"] != str(_GLEAN_GATEWAY_TOKEN_WRAPPER_PATH):
        raise RuntimeError("Claude managed authentication helper drifted")
    if settings["otelHeadersHelper"] != str(_CLAUDE_OTEL_HELPER_PATH):
        raise RuntimeError("Claude managed telemetry helper drifted")
    telemetry_enabled = True
    redacted_environment = dict(environment)
    redacted_environment["ANTHROPIC_BASE_URL"] = (
        "<validated-derived-managed-gateway-anthropic-route>"
    )
    redacted_environment["OTEL_EXPORTER_OTLP_ENDPOINT"] = (
        "<validated-approved-managed-otel-endpoint>"
    )
    redacted_environment["OTEL_RESOURCE_ATTRIBUTES"] = (
        "user.email=<validated-redacted>"
    )
    redacted_projection = {
        "apiKeyHelper": settings["apiKeyHelper"],
        "env": redacted_environment,
        "otelHeadersHelper": settings["otelHeadersHelper"],
    }
    return (
        {
            "path": str(_CLAUDE_MANAGED_SETTINGS_PATH),
            "redacted_projection_sha256": _component_hash(
                redacted_projection
            ),
            "semantic_projection": {
                "api_key_helper_matches_pinned_wrapper": True,
                "anthropic_base_url_matches_glean_gateway": True,
                "telemetry_enabled": telemetry_enabled,
                "otel_headers_helper_matches_pinned_helper": True,
                "top_level_key_allowlist_exact": True,
                "managed_environment_key_allowlist_exact": True,
                "managed_environment_key_count": len(
                    _CLAUDE_MANAGED_ENV_KEYS
                ),
                "managed_environment_value_types_and_policies_validated": True,
                "forbidden_sensitive_fields_absent": True,
                "raw_values_disclosed": False,
                "raw_file_sha256_published": False,
                "personal_identifier_commitment_published": False,
            },
        },
        telemetry_enabled,
    )


def _safe_entrypoint_identity(path: Path, *, label: str) -> dict[str, Any]:
    """Pin a regular entrypoint or one direct symlink to a regular file."""

    if not path.is_absolute():
        raise RuntimeError(f"Required {label} path must be absolute")
    try:
        entry_metadata = path.lstat()
    except OSError:
        raise RuntimeError(f"Required {label} is unavailable") from None

    link_text: str | None = None
    if stat.S_ISREG(entry_metadata.st_mode):
        entrypoint_kind = "regular_file"
        direct_target = path
        target_metadata = entry_metadata
    elif stat.S_ISLNK(entry_metadata.st_mode):
        entrypoint_kind = "symlink"
        try:
            link_text = os.readlink(path)
        except OSError:
            raise RuntimeError(f"Unable to read required {label} symlink") from None
        direct_target = Path(link_text)
        if not direct_target.is_absolute():
            direct_target = path.parent / direct_target
        try:
            target_metadata = direct_target.lstat()
        except OSError:
            raise RuntimeError(
                f"Required {label} symlink target is unavailable"
            ) from None
        if not stat.S_ISREG(target_metadata.st_mode):
            raise RuntimeError(
                f"Required {label} symlink must point directly to a regular file"
            )
    else:
        raise RuntimeError(
            f"Required {label} must be a regular file or direct symlink to one"
        )

    try:
        resolved_target = direct_target.resolve(strict=True)
        resolved_metadata = resolved_target.lstat()
    except (OSError, RuntimeError):
        raise RuntimeError(f"Unable to resolve required {label}") from None
    if (
        not stat.S_ISREG(resolved_metadata.st_mode)
        or (resolved_metadata.st_dev, resolved_metadata.st_ino)
        != (target_metadata.st_dev, target_metadata.st_ino)
    ):
        raise RuntimeError(f"Required {label} does not resolve to its pinned file")

    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(resolved_target, flags)
    except OSError:
        raise RuntimeError(f"Unable to open required {label}") from None
    try:
        opened_metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened_metadata.st_mode)
            or (opened_metadata.st_dev, opened_metadata.st_ino)
            != (resolved_metadata.st_dev, resolved_metadata.st_ino)
        ):
            raise RuntimeError(f"Required {label} changed before hashing")
        digest = hashlib.sha256()
        for chunk in iter(lambda: os.read(descriptor, 1024 * 1024), b""):
            digest.update(chunk)
        final_opened_metadata = os.fstat(descriptor)
        stable_fields = (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
        if any(
            getattr(opened_metadata, field) != getattr(final_opened_metadata, field)
            for field in stable_fields
        ):
            raise RuntimeError(f"Required {label} changed while hashing")
    except OSError:
        raise RuntimeError(f"Unable to hash required {label}") from None
    finally:
        os.close(descriptor)

    try:
        final_entry_metadata = path.lstat()
        final_resolved_target = path.resolve(strict=True)
        final_target_metadata = final_resolved_target.lstat()
        final_link_text = os.readlink(path) if link_text is not None else None
    except (OSError, RuntimeError):
        raise RuntimeError(f"Required {label} changed while hashing") from None
    if (
        (final_entry_metadata.st_dev, final_entry_metadata.st_ino)
        != (entry_metadata.st_dev, entry_metadata.st_ino)
        or final_entry_metadata.st_mode != entry_metadata.st_mode
        or final_link_text != link_text
        or final_resolved_target != resolved_target
        or not stat.S_ISREG(final_target_metadata.st_mode)
        or any(
            getattr(final_target_metadata, field)
            != getattr(final_opened_metadata, field)
            for field in stable_fields
        )
    ):
        raise RuntimeError(f"Required {label} changed while hashing")

    return {
        "path": str(path),
        "entrypoint_kind": entrypoint_kind,
        "link_text": link_text,
        "resolved_path": str(resolved_target),
        "target_sha256": "sha256:" + digest.hexdigest(),
    }


def _glean_helper_identity() -> dict[str, str]:
    try:
        digest = _fixed_file_sha256(_GLEAN_HELPER_PATH, label="Glean helper")
    except (OSError, RuntimeError):
        raise ProviderStateIsolationError(
            "Unable to pin Glean helper identity"
        ) from None
    version = _identity_version_probe(
        [str(_GLEAN_HELPER_PATH), "--version"], label="Glean helper"
    )
    try:
        final_digest = _fixed_file_sha256(
            _GLEAN_HELPER_PATH, label="Glean helper"
        )
    except (OSError, RuntimeError):
        raise ProviderStateIsolationError(
            "Glean helper changed during identity probe"
        ) from None
    if final_digest != digest:
        raise ProviderStateIsolationError(
            "Glean helper changed during identity probe"
        )
    return {
        "path": str(_GLEAN_HELPER_PATH),
        "version": version,
        "sha256": digest,
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
    glean_config, glean_config_identity = _safe_glean_config()
    managed_settings, telemetry_enabled = _managed_settings_identity(
        glean_config
    )
    gateway_wrapper = _safe_entrypoint_identity(
        _GLEAN_GATEWAY_TOKEN_WRAPPER_PATH,
        label="Glean LLM gateway token wrapper",
    )
    gateway_wrapper["dispatch_contract"] = {
        "argv0_basename": "glean-llm-gateway-token",
        "arguments": [],
        "option_source": "glean.DefaultOptions",
        "oauth_client_id_source": "explicit_GLEAN_HELPER_OAUTH_CLIENT_ID",
        "credential_path": "$HOME/.glean-llm-gateway/credentials.json",
    }
    otel_helper = (
        {
            "path": str(_CLAUDE_OTEL_HELPER_PATH),
            "sha256": _fixed_file_sha256(
                _CLAUDE_OTEL_HELPER_PATH,
                label="Claude OTEL headers helper",
            ),
        }
        if telemetry_enabled
        else {"status": "disabled_by_managed_settings"}
    )
    return {
        "executables": [
            identities[executable] for executable in sorted(identities)
        ],
        "claude_auth_dependencies": {
            "macos_security_metadata_tool": {
                "path": str(_MACOS_SECURITY_PATH),
                "sha256": _fixed_file_sha256(
                    _MACOS_SECURITY_PATH,
                    label="macOS Keychain metadata tool",
                ),
            },
            "glean_helper": _glean_helper_identity(),
            "glean_llm_gateway_token_wrapper": gateway_wrapper,
            "glean_config": glean_config_identity,
            "managed_settings": managed_settings,
            "claude_otel_headers_helper": otel_helper,
        },
        "ambient_proxy_or_custom_ca_overrides": [],
    }


def _glean_claude_oauth_client_id() -> str:
    config, _identity = _safe_glean_config()
    return str(config["oauth"]["claude"]["client_id"])


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


def _attest_execution_contracts(
    *, root: Path, public: Mapping[str, Any]
) -> None:
    """Revalidate only the public execution surfaces around a provider call."""

    try:
        fresh = {
            "source_contract": _source_contract(root),
            "cli_contract": _cli_contract(),
            "runtime_contract": _runtime_contract(),
            "replay_trace_contract": replay_trace_contract(),
            "profiles": _profile_contract(),
        }
    except Exception as error:
        raise RuntimeError(
            "Unable to attest per-call execution contracts"
        ) from error
    hashes = public.get("contract_hashes")
    hash_names = {
        "source_contract": "source_sha256",
        "cli_contract": "cli_sha256",
        "runtime_contract": "runtime_sha256",
        "replay_trace_contract": "replay_sha256",
        "profiles": "profiles_sha256",
    }
    for surface, current in fresh.items():
        if (
            not isinstance(hashes, dict)
            or public.get(surface) != current
            or hashes.get(hash_names[surface]) != _component_hash(current)
        ):
            raise RuntimeError(
                f"Per-call execution contract drifted: {surface}"
            )


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


def _spend_authorization_contract() -> dict[str, Any]:
    return {
        "schema_version": _SPEND_AUTHORIZATION_SCHEMA,
        "storage": "authenticated_private_state_only",
        "required_before": (
            "any_authentication_bootstrap_or_model_bearing_provider_call"
        ),
        "required_acknowledgement_text_sha256": _sha256(
            REQUIRED_SPEND_ACKNOWLEDGEMENT.encode("utf-8")
        ),
        "receipt_binding": [
            "panel_id",
            "final_public_precommitment_sha256",
            "budget_contract_sha256",
            "claude_cumulative_authorization_ceiling_usd",
            "unbounded_codex_cursor_provider_spend",
            "exact_acknowledgement_text",
        ],
    }


def _budget_contract(claude_max_budget_usd: float) -> dict[str, Any]:
    per_call_ceiling = float(claude_max_budget_usd)
    current_preflight_calls = sum(
        profile["system"] == "claude" for profile in PROFILES
    )
    current_production_calls = EPISODE_COUNT * current_preflight_calls
    current_ceiling = per_call_ceiling * (
        current_preflight_calls + current_production_calls
    )
    prior_ceiling = 25.0
    return {
        "claude_max_budget_usd_per_assignment": per_call_ceiling,
        "claude_max_budget_usd_per_call": per_call_ceiling,
        "claude_current_v8_authorization_ceiling_usd": current_ceiling,
        "claude_current_v8_authorization_breakdown": {
            "preflight_calls": current_preflight_calls,
            "production_calls": current_production_calls,
            "per_call_ceiling_usd": per_call_ceiling,
            "preflight_ceiling_usd": (
                current_preflight_calls * per_call_ceiling
            ),
            "production_ceiling_usd": (
                current_production_calls * per_call_ceiling
            ),
        },
        "claude_prior_failed_panel_conservative_ceiling_usd": prior_ceiling,
        "claude_prior_failed_panel_breakdown": {
            "v2_usd": 10.0,
            "v3_usd": 0.0,
            "v4_usd": 0.0,
            "v5_usd": 5.0,
            "v6_usd": 0.0,
            "v7_usd": 10.0,
        },
        "claude_cumulative_authorization_ceiling_usd": (
            prior_ceiling + current_ceiling
        ),
        "prior_public_audit_references": {
            "v2_preflight_receipt": (
                "results/development-matched-50x6-v2.preflight.json"
            ),
            "v2_supersession": (
                "results/development-matched-50x6-v2.superseded.json"
            ),
            "v5_supersession": (
                "results/development-matched-50x6-v5.superseded.json"
            ),
            "v5_preflight_receipt": (
                "results/development-matched-50x6-v5.preflight.json"
            ),
            "v6_supersession": (
                "results/development-matched-50x6-v6.superseded.json"
            ),
            "v6_preflight_receipt": (
                "results/development-matched-50x6-v6.preflight.json"
            ),
            "v7_preflight_receipt": (
                "results/development-matched-50x6-v7.preflight.json"
            ),
            "v7_supersession": (
                "results/development-matched-50x6-v7.superseded.json"
            ),
        },
        "ceiling_interpretation": (
            "authorization ceilings, not measured provider billing"
        ),
        "other_provider_spend_cap": None,
        "other_provider_spend": "unbounded",
        "explicit_unbounded_provider_spend_acknowledgement_required": True,
    }


def prepare_panel(
    *,
    root: Path,
    cohort_manifest_path: Path,
    authentication_key_file: Path,
    claude_secure_storage_dir: Path,
    codex_secure_storage_dir: Path,
    private_state_path: Path,
    public_manifest_path: Path,
    timeout_seconds: int = 1800,
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
    if type(timeout_seconds) is not int or timeout_seconds != 1800:
        raise ValueError("V8 requires an exact 1800-second assignment timeout")
    if (
        isinstance(claude_max_budget_usd, bool)
        or not isinstance(claude_max_budget_usd, (int, float))
        or float(claude_max_budget_usd) != 5.0
    ):
        raise ValueError("V8 requires an exact $5 Claude per-call ceiling")

    resolved_claude_secure_storage_dir = _validate_claude_secure_storage_dir(
        claude_secure_storage_dir, root=root
    )
    claude_secure_storage_identity = _claude_secure_storage_identity(
        resolved_claude_secure_storage_dir
    )
    resolved_codex_secure_storage_dir = _validate_codex_secure_storage_dir(
        codex_secure_storage_dir, root=root
    )
    codex_secure_storage_identity = _codex_secure_storage_identity(
        resolved_codex_secure_storage_dir
    )
    if _paths_overlap(
        resolved_claude_secure_storage_dir,
        resolved_codex_secure_storage_dir,
    ):
        raise ValueError("Claude and Codex secure storage directories must not overlap")

    key_path = _existing_path_without_final_symlink(authentication_key_file)
    key = _read_authentication_key(key_path)
    manifest_path = _existing_path_without_final_symlink(cohort_manifest_path)
    _assert_claude_storage_separate_from_artifacts(
        resolved_claude_secure_storage_dir,
        cohort_manifest_path=manifest_path,
        authentication_key_file=key_path,
        private_state_path=private_state_path,
        public_manifest_path=public_manifest_path,
    )
    _assert_codex_storage_separate_from_artifacts(
        resolved_codex_secure_storage_dir,
        cohort_manifest_path=manifest_path,
        authentication_key_file=key_path,
        private_state_path=private_state_path,
        public_manifest_path=public_manifest_path,
    )
    _require_claude_credential_state(
        resolved_claude_secure_storage_dir,
        root=root,
        expected_identity=claude_secure_storage_identity,
        managed_glean_credentials_present=False,
    )
    _require_codex_credential_state(
        resolved_codex_secure_storage_dir,
        root=root,
        expected_identity=codex_secure_storage_identity,
        credentials_present=False,
    )
    manifest, episodes = _load_frozen_cohort(manifest_path, key)
    nonce = secrets.token_bytes(32)
    claude_auth_commitment_key = secrets.token_bytes(32)
    codex_auth_commitment_key = secrets.token_bytes(32)
    schedule = _private_schedule(episodes, nonce)
    keys = _assignment_keys(schedule)
    if len(keys) != ASSIGNMENT_COUNT or len(set(keys)) != ASSIGNMENT_COUNT:
        raise RuntimeError(
            f"Matched schedule does not contain {ASSIGNMENT_COUNT} unique assignments"
        )

    profiles = _profile_contract()
    source = _source_contract(root)
    cli = _cli_contract()
    claude_auth = _claude_auth_contract(
        resolved_claude_secure_storage_dir,
        claude_secure_storage_identity,
        claude_auth_commitment_key,
    )
    codex_auth = _codex_auth_contract(
        resolved_codex_secure_storage_dir,
        codex_secure_storage_identity,
        codex_auth_commitment_key,
    )
    budgets = _budget_contract(float(claude_max_budget_usd))
    timeouts = {
        "seconds_per_assignment": timeout_seconds,
        "non_codex_timeout_policy": (
            "fixed_denominator_zero_after_original_process_group_quiescence"
        ),
        "codex_timeout_policy": (
            "terminal_transport_void_due_to_credential_refresh_ambiguity"
        ),
        "preflight_codex_timeout_policy": (
            "after_clean_quiescence_and_auth_attestation_quarantine_codex_"
            "namespace_skip_later_codex_and_continue_independent_profiles"
        ),
    }
    runtime = _runtime_contract()
    replay = replay_trace_contract()
    _require_claude_credential_state(
        resolved_claude_secure_storage_dir,
        root=root,
        expected_identity=claude_secure_storage_identity,
        managed_glean_credentials_present=False,
    )
    _require_codex_credential_state(
        resolved_codex_secure_storage_dir,
        root=root,
        expected_identity=codex_secure_storage_identity,
        credentials_present=False,
    )
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
        "claude_auth_contract": claude_auth,
        "codex_auth_contract": codex_auth,
        "source_contract": source,
        "runtime_contract": runtime,
        "replay_trace_contract": replay,
        "budget_contract": budgets,
        "timeout_contract": timeouts,
        "contract_hashes": {
            "source_sha256": _component_hash(source),
            "cli_sha256": _component_hash(cli),
            "claude_auth_sha256": _component_hash(claude_auth),
            "codex_auth_sha256": _component_hash(codex_auth),
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
            "spend_authorization": _spend_authorization_contract(),
            "retry_policy": "at most one provider invocation per assignment",
            "orphan_policy": (
                "seal started assignment as transport_void; never retry; "
                "block cohort completion and every later provider call"
            ),
            "transport_void_policy": (
                "ordinary cleanly quiesced void stops current command and a "
                "later command may continue; crash-orphan, provider process or "
                "state isolation, episode-service cleanup, and Codex "
                "authentication incidents are terminal and non-resumable"
            ),
            "terminal_incident_policy": {
                "crash_after_durable_start": {
                    "non_codex": ["execution_incident"],
                    "codex": ["execution_incident", "codex_auth_incident"],
                },
                "provider_process_or_output_pipe_isolation_failure": {
                    "non_codex": ["execution_incident"],
                    "codex": ["execution_incident", "codex_auth_incident"],
                },
                "provider_state_persistence_guard_failure": {
                    "non_codex": ["execution_incident"],
                    "codex": ["execution_incident", "codex_auth_incident"],
                },
                "episode_service_cleanup_failure": {
                    "non_codex": ["execution_incident"],
                    "codex": ["execution_incident", "codex_auth_incident"],
                },
                "codex_timeout_or_post_launch_credential_link_drift": [
                    "codex_auth_incident"
                ],
                "effects": (
                    "seal the current assignment as transport_void; never retry; "
                    "call no later provider; block cohort retirement, terminal "
                    "completion, and private trace release"
                ),
            },
            "provider_process_policy": (
                "new POSIX session; bounded output capture; terminate and "
                "verify the original process group before continuing; detached "
                "processes that close inherited pipes remain outside this "
                "development runner's containment guarantee"
            ),
            "partial_public_results": False,
            "environment_preflight_required_before_production_launch": True,
            "environment_preflight_scope": (
                "unscored_infrastructure_routing_handshake_not_capability_screen"
            ),
            "environment_preflight_failure_policy": {
                "ordinary_clean_provider_failure": (
                    "record_finite_outcome_and_continue_in_frozen_sequence"
                ),
                "codex_clean_timeout": (
                    "durably_quarantine_codex_skip_later_codex_continue_"
                    "independent_profiles"
                ),
                "security_isolation_cleanup_or_contract_failure": (
                    "terminal_abort_and_no_later_provider_call"
                ),
                "production_gate": "all_six_profiles_must_pass",
            },
            "managed_glean_auth_bootstrap": {
                "stage": "before_six_profile_calls",
                "model_calls": 0,
                "stdout": "discarded_never_captured",
                "stderr": "inherited_for_oauth_instructions",
                "credentials_required_after": True,
            },
            "codex_auth_bootstrap": {
                "stage": "before_six_profile_calls",
                "model_calls": 0,
                "one_shot": True,
                "method": "pinned_cli_oauth_with_file_credential_store",
                "credentials_required_after": True,
            },
            "per_provider_call_execution_attestation": {
                "surfaces": [
                    "source_contract",
                    "cli_contract",
                    "runtime_contract",
                    "replay_trace_contract",
                    "profiles",
                ],
                "preflight": {
                    "before": "before_top_level_provider_harness_invocation",
                    "after": "after_top_level_provider_harness_return",
                    "drift_policy": "fail_preflight_closed",
                },
                "production": {
                    "before": "before_durable_assignment_start",
                    "after": (
                        "after_top_level_provider_harness_return_inside_transport_guard"
                    ),
                    "preexisting_drift_consumes_assignment": False,
                    "mid_call_drift": "transport_void",
                },
                "private_secrets_or_episode_packs_read_per_check": False,
            },
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
            (
                "provider output capture is bounded, but this macOS development "
                "runner enforces no aggregate provider RSS, filesystem-byte or "
                "file-count, process-count, or OS-job ceiling; original-process-"
                "group containment is not full job containment"
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
        "claude_secure_storage_dir": str(resolved_claude_secure_storage_dir),
        "claude_secure_storage_identity": claude_secure_storage_identity,
        "claude_auth_commitment_key_hex": claude_auth_commitment_key.hex(),
        "codex_secure_storage_dir": str(resolved_codex_secure_storage_dir),
        "codex_secure_storage_identity": codex_secure_storage_identity,
        "codex_auth_commitment_key_hex": codex_auth_commitment_key.hex(),
        "episodes": episodes,
        "schedule_nonce_hex": nonce.hex(),
        "schedule": schedule,
        "environment_preflight": {
            "status": "required",
            "required_contract_hashes": {
                "source_sha256": public["contract_hashes"]["source_sha256"],
                "cli_sha256": public["contract_hashes"]["cli_sha256"],
                "claude_auth_sha256": public["contract_hashes"][
                    "claude_auth_sha256"
                ],
                "codex_auth_sha256": public["contract_hashes"][
                    "codex_auth_sha256"
                ],
                "profiles_sha256": public["contract_hashes"]["profiles_sha256"],
                "budgets_sha256": public["contract_hashes"]["budgets_sha256"],
                "timeouts_sha256": public["contract_hashes"]["timeouts_sha256"],
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
    claude_secure_storage_dir: Path,
    codex_secure_storage_dir: Path,
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
        or public.get("budget_contract") != _budget_contract(5.0)
        or not isinstance(public.get("run_contract"), dict)
        or public["run_contract"].get("spend_authorization")
        != _spend_authorization_contract()
        or private.get("panel_id") != PANEL_ID
        or private.get("public_precommitment_sha256")
        != public.get("precommitment_sha256")
    ):
        raise ValueError("Matched-panel manifest contract mismatch")
    _validate_claude_auth_binding(
        root=root,
        claude_secure_storage_dir=claude_secure_storage_dir,
        private=private,
        public=public,
    )
    _validate_codex_auth_binding(
        root=root,
        codex_secure_storage_dir=codex_secure_storage_dir,
        private=private,
        public=public,
    )
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
            ("claude_auth_sha256", public["claude_auth_contract"]),
            ("codex_auth_sha256", public["codex_auth_contract"]),
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
    for incident_name in ("execution_incident", "codex_auth_incident"):
        incident = private.get(incident_name)
        if incident is None:
            continue
        if (
            not isinstance(incident, dict)
            or incident.get("status") != "terminal"
            or type(incident.get("assignment_index")) is not int
            or not 0 <= incident["assignment_index"] < len(assignments)
            or not isinstance(incident.get("failure_class"), str)
            or not incident["failure_class"]
            or assignments[incident["assignment_index"]].get("status")
            != "transport_void"
        ):
            raise ValueError("Private terminal incident state is invalid")
    if private.get("status") == "complete" and any(
        private.get(name) is not None
        for name in ("execution_incident", "codex_auth_incident")
    ):
        raise ValueError("Completed private state contains a terminal incident")
    return manifest, packs, schedule


def _expected_spend_authorization(
    public: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the one exact private receipt accepted for this precommitment."""

    budget = public.get("budget_contract")
    hashes = public.get("contract_hashes")
    profiles = public.get("profiles")
    precommitment = public.get("precommitment_sha256")
    ceiling = (
        budget.get("claude_cumulative_authorization_ceiling_usd")
        if isinstance(budget, Mapping)
        else None
    )
    non_claude_systems = (
        {
            str(profile.get("system"))
            for profile in profiles
            if isinstance(profile, Mapping) and profile.get("system") != "claude"
        }
        if isinstance(profiles, list)
        else set()
    )
    if (
        not isinstance(budget, Mapping)
        or not isinstance(hashes, Mapping)
        or not isinstance(precommitment, str)
        or not precommitment.startswith("sha256:")
        or isinstance(ceiling, bool)
        or not isinstance(ceiling, (int, float))
        or float(ceiling) != _CLAUDE_CUMULATIVE_AUTHORIZATION_CEILING_USD
        or budget.get("other_provider_spend_cap") is not None
        or budget.get("other_provider_spend") != "unbounded"
        or non_claude_systems != set(_UNBOUNDED_PROVIDER_SPEND_AUTHORIZATION)
        or hashes.get("budgets_sha256") != _component_hash(budget)
        or not isinstance(public.get("run_contract"), Mapping)
        or public["run_contract"].get("spend_authorization")
        != _spend_authorization_contract()
    ):
        raise ValueError("V8 spend authorization contract mismatch")
    unsigned = {
        "schema_version": _SPEND_AUTHORIZATION_SCHEMA,
        "status": "authorized",
        "panel_id": PANEL_ID,
        "final_public_precommitment_sha256": precommitment,
        "budget_contract_sha256": str(hashes["budgets_sha256"]),
        "claude_cumulative_authorization_ceiling_usd": float(ceiling),
        "unbounded_provider_spend": dict(
            _UNBOUNDED_PROVIDER_SPEND_AUTHORIZATION
        ),
        "acknowledgement_text": REQUIRED_SPEND_ACKNOWLEDGEMENT,
        "acknowledgement_text_sha256": _sha256(
            REQUIRED_SPEND_ACKNOWLEDGEMENT.encode("utf-8")
        ),
    }
    return {**unsigned, "receipt_sha256": _component_hash(unsigned)}


def _assert_spend_authorization(
    private: Mapping[str, Any], public: Mapping[str, Any]
) -> dict[str, Any]:
    expected = _expected_spend_authorization(public)
    supplied = private.get("spend_authorization")
    if not isinstance(supplied, Mapping) or not hmac.compare_digest(
        _canonical_bytes(dict(supplied)), _canonical_bytes(expected)
    ):
        raise RuntimeError(
            "A manifest-bound exact v8 spend authorization receipt is required "
            "before any authentication bootstrap or model-bearing provider call"
        )
    return expected


def authorize_panel_spend(
    *,
    root: Path,
    authentication_key_file: Path,
    claude_secure_storage_dir: Path,
    codex_secure_storage_dir: Path,
    private_state_path: Path,
    public_manifest_path: Path,
    acknowledgement_text: str,
) -> dict[str, Any]:
    """Persist exact authorization before any bootstrap or model-bearing call."""

    if not isinstance(acknowledgement_text, str) or not hmac.compare_digest(
        acknowledgement_text, REQUIRED_SPEND_ACKNOWLEDGEMENT
    ):
        raise RuntimeError(
            "The exact v8 $535 cumulative spend acknowledgement text is required"
        )
    resolved_claude_secure_storage_dir = _validate_claude_secure_storage_dir(
        claude_secure_storage_dir, root=root
    )
    resolved_codex_secure_storage_dir = _validate_codex_secure_storage_dir(
        codex_secure_storage_dir, root=root
    )
    if _paths_overlap(
        resolved_claude_secure_storage_dir,
        resolved_codex_secure_storage_dir,
    ):
        raise ValueError("Claude and Codex secure storage directories must not overlap")
    _assert_distinct_paths(
        authentication_key_file,
        private_state_path,
        public_manifest_path,
    )
    with _exclusive_run_lock(private_state_path):
        authorization_head = _assert_authorization_worktree(
            root=root,
            private_state_path=private_state_path,
            public_manifest_path=public_manifest_path,
        )
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
            claude_secure_storage_dir=resolved_claude_secure_storage_dir,
            codex_secure_storage_dir=resolved_codex_secure_storage_dir,
        )
        preflight = private.get("environment_preflight")
        if (
            private.get("status") != "prepared"
            or private.get("assignments") != []
            or not isinstance(preflight, Mapping)
            or preflight.get("status") != "required"
        ):
            raise RuntimeError(
                "Spend authorization must precede every authentication bootstrap "
                "and model-bearing provider call"
            )
        claude_identity = _private_claude_storage_identity(private)
        codex_identity = _private_codex_storage_identity(private)
        _require_claude_credential_state(
            resolved_claude_secure_storage_dir,
            root=root,
            expected_identity=claude_identity,
            managed_glean_credentials_present=False,
        )
        _require_codex_credential_state(
            resolved_codex_secure_storage_dir,
            root=root,
            expected_identity=codex_identity,
            credentials_present=False,
        )
        expected = _expected_spend_authorization(public)
        existing = private.get("spend_authorization")
        if existing is not None:
            _assert_spend_authorization(private, public)
            return expected
        _assert_authorization_worktree(
            root=root,
            private_state_path=private_state_path,
            public_manifest_path=public_manifest_path,
            expected_head=authorization_head,
        )
        if _load_json(public_manifest_path) != public:
            raise RuntimeError(
                "Public matched-panel precommitment changed during spend "
                "authorization"
            )
        private["spend_authorization"] = expected
        _write_private_state(private_state_path, private, authentication_key)
        return expected


def _assert_environment_preflight(
    root: Path, private: Mapping[str, Any], public: Mapping[str, Any]
) -> None:
    preflight = private.get("environment_preflight")
    expected = {
        name: public["contract_hashes"][name]
        for name in (
            "source_sha256",
            "cli_sha256",
            "claude_auth_sha256",
            "codex_auth_sha256",
            "profiles_sha256",
            "budgets_sha256",
            "timeouts_sha256",
            "runtime_sha256",
            "replay_sha256",
        )
    }
    private_attempts = (
        preflight.get("attempts") if isinstance(preflight, dict) else None
    )
    expected_bootstrap_fields = {
        "status",
        "launch_pending_at_utc",
        "started_at_utc",
        "returned_at_utc",
        "returncode",
        "finished_at_utc",
    }

    def passed_bootstrap(value: Any) -> bool:
        return (
            isinstance(value, dict)
            and set(value) == expected_bootstrap_fields
            and value.get("status") == "passed"
            and value.get("returncode") == 0
            and all(
                isinstance(value.get(name), str) and bool(value[name])
                for name in expected_bootstrap_fields
                - {"status", "returncode"}
            )
        )

    if (
        not isinstance(preflight, dict)
        or preflight.get("status") != "passed"
        or preflight.get("passed_contract_hashes") != expected
        or not passed_bootstrap(preflight.get("managed_glean_auth_bootstrap"))
        or not passed_bootstrap(preflight.get("codex_auth_bootstrap"))
        or preflight.get("codex_auth_quarantine") != {"status": "clear"}
        or not isinstance(private_attempts, list)
        or len(private_attempts) != len(PROFILES)
        or tuple(
            attempt.get("profile_id") if isinstance(attempt, dict) else None
            for attempt in private_attempts
        )
        != _PROFILE_IDS
        or any(
            not isinstance(attempt, dict)
            or attempt.get("status") != "passed"
            or _durable_provider_invocation_state(attempt) != "finished"
            for attempt in private_attempts
        )
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
    profile_receipts = receipt.get("profiles")
    expected_cli_versions = {
        str(item["name"]): str(item["version"])
        for item in public["cli_contract"]["executables"]
    }

    def valid_profile_receipt(
        item: Any, expected_profile: Mapping[str, Any]
    ) -> bool:
        if not isinstance(item, dict):
            return False
        observed_models = item.get("observed_models")
        if not isinstance(observed_models, list) or any(
            not isinstance(value, str) for value in observed_models
        ):
            return False
        receipt_required = (
            expected_profile["model_receipt_policy"]
            == "provider_match_required"
        )
        model_receipt_valid = (
            item.get("model_receipt_satisfied") is True
            and _exact_model_receipt_satisfied(
                expected_profile, observed_models
            )
            if receipt_required
            else item.get("model_receipt_satisfied") is None
        )
        return (
            item.get("profile_id") == expected_profile["profile_id"]
            and item.get("system") == expected_profile["system"]
            and item.get("requested_model")
            == expected_profile["requested_model"]
            and item.get("requested_reasoning")
            == expected_profile["requested_reasoning"]
            and item.get("invocation_state") == "finished"
            and item.get("outcome") == "passed"
            and item.get("timed_out") is False
            and item.get("conservative_chargeable") is True
            and item.get("failure_reason") is None
            and item.get("cli_version")
            == expected_cli_versions[str(expected_profile["executable"])]
            and item.get("scored") is False
            and item.get("replay_trace_validated") is True
            and item.get("infrastructure_handshake_passed") is True
            and isinstance(item.get("progress_telemetry"), dict)
            and set(item["progress_telemetry"])
            == {
                "schema_version",
                "observed_elapsed_bucket",
                "output_seen",
                "first_output_elapsed_bucket",
                "last_output_elapsed_bucket",
                "combined_output_bytes_bucket",
                "first_activity_elapsed_bucket",
                "last_activity_elapsed_bucket",
                "permitted_mcp_calls",
                "activity_count_source",
            }
            and _safe_live_provider_progress(item["progress_telemetry"])
            == item["progress_telemetry"]
            and (
                expected_profile["system"] != "codex"
                or (
                    item.get("codex_credentials_state_before") == "present"
                    and item.get("codex_credentials_state_after") == "present"
                    and item.get("codex_auth_link_before") == "bound"
                    and item.get("codex_auth_link_after") == "bound"
                    and item.get("refresh_persistence_attested") is True
                )
            )
            and model_receipt_valid
        )

    exact_profile_receipts = (
        isinstance(profile_receipts, list)
        and len(profile_receipts) == len(PROFILES)
        and tuple(
            item.get("profile_id") if isinstance(item, dict) else None
            for item in profile_receipts
        )
        == _PROFILE_IDS
        and all(
            valid_profile_receipt(item, expected_profile)
            for item, expected_profile in zip(profile_receipts, PROFILES)
        )
    )
    if (
        receipt.get("schema_version") != SCHEMA_VERSION
        or receipt.get("panel_id") != PANEL_ID
        or receipt.get("status") != "passed"
        or receipt.get("development_only") is not True
        or receipt.get("production_episodes_consumed") != 0
        or type(receipt.get("production_episodes_consumed")) is not int
        or receipt.get("scores_reported") is not False
        or receipt.get("managed_glean_auth_bootstrap") != "passed"
        or receipt.get("codex_auth_bootstrap") != "passed"
        or receipt.get("codex_auth_quarantine") != "clear"
        or receipt.get("preflight_purpose")
        != "unscored_infrastructure_routing_handshake"
        or receipt.get("failed_provider_invocation_state") is not None
        or receipt.get("failed_profile_ids") != []
        or receipt.get("failure_reason") is not None
        or receipt.get("timed_out") is not False
        or receipt.get("provider_calls_conservatively_chargeable")
        != len(PROFILES)
        or not exact_profile_receipts
        or receipt.get("profiles_passed") != profile_receipts
        or receipt.get("contract_hashes") != expected
        or receipt.get("precommitment_sha256")
        != public.get("precommitment_sha256")
        or preflight.get("public_receipt_sha256") != _component_hash(receipt)
    ):
        raise RuntimeError("The committed environment preflight receipt is invalid")


def _durable_provider_invocation_state(marker: Mapping[str, Any]) -> str:
    """Project the private durable marker onto a finite public call state."""

    invocation = marker.get("provider_invocation")
    if invocation is None:
        return "not_started"
    if not isinstance(invocation, dict):
        raise RuntimeError("Provider invocation marker is invalid")
    status = invocation.get("status")
    if status == "started":
        return "started_not_finished"
    if status == "finished":
        return "finished"
    raise RuntimeError("Provider invocation marker is invalid")


def _conservatively_chargeable_provider_calls(
    attempts: Sequence[Mapping[str, Any]],
) -> int:
    return sum(
        _durable_provider_invocation_state(attempt) != "not_started"
        for attempt in attempts
    )


_PROGRESS_ELAPSED_BUCKETS = frozenset(
    {
        "none",
        "lt_30s",
        "30_119s",
        "120_299s",
        "300_899s",
        "900_1799s",
        "ge_1800s",
    }
)
_PROGRESS_BYTE_BUCKETS = frozenset(
    {"0", "1_4095", "4096_65535", "65536_1048575", "ge_1048576"}
)


def _elapsed_progress_bucket(seconds: float) -> str:
    if seconds < 30:
        return "lt_30s"
    if seconds < 120:
        return "30_119s"
    if seconds < 300:
        return "120_299s"
    if seconds < 900:
        return "300_899s"
    if seconds < 1800:
        return "900_1799s"
    return "ge_1800s"


def _output_progress_bucket(value: int) -> str:
    if value == 0:
        return "0"
    if value < 4 * 1024:
        return "1_4095"
    if value < 64 * 1024:
        return "4096_65535"
    if value < 1024 * 1024:
        return "65536_1048575"
    return "ge_1048576"


def _safe_provider_progress(result: PilotRunResult) -> dict[str, Any]:
    """Return only finite, content-free provider progress telemetry."""

    metrics = result.scorecard.get("metrics")
    permitted_mcp_calls = (
        metrics.get("tool_calls") if isinstance(metrics, Mapping) else None
    )
    if (
        type(permitted_mcp_calls) is not int
        or not 0 <= permitted_mcp_calls <= 50
    ):
        raise RuntimeError("Trusted provider progress count is invalid")
    raw = result.progress_telemetry
    base_keys = {
        "schema_version",
        "observed_elapsed_bucket",
        "output_seen",
        "first_output_elapsed_bucket",
        "last_output_elapsed_bucket",
        "combined_output_bytes_bucket",
    }
    terminal_keys = base_keys | {
        "first_activity_elapsed_bucket",
        "last_activity_elapsed_bucket",
        "permitted_mcp_calls",
        "activity_count_source",
    }
    if not raw:
        elapsed = _elapsed_progress_bucket(max(0.0, result.elapsed_seconds))
        output_seen = result.stdout_bytes + result.stderr_bytes > 0
        raw = {
            "schema_version": "epiagentbench.provider_progress.v1",
            "observed_elapsed_bucket": elapsed,
            "output_seen": output_seen,
            "first_output_elapsed_bucket": elapsed if output_seen else "none",
            "last_output_elapsed_bucket": elapsed if output_seen else "none",
            "combined_output_bytes_bucket": _output_progress_bucket(
                result.stdout_bytes + result.stderr_bytes
            ),
        }
    if not isinstance(raw, Mapping) or (
        set(raw) != base_keys and set(raw) != terminal_keys
    ):
        raise RuntimeError("Provider progress telemetry has an invalid schema")
    progress = dict(raw)
    if progress.get("schema_version") != "epiagentbench.provider_progress.v1":
        raise RuntimeError("Provider progress telemetry has an invalid schema")
    if type(progress.get("output_seen")) is not bool:
        raise RuntimeError("Provider progress telemetry has an invalid value")
    if any(
        progress.get(name) not in _PROGRESS_ELAPSED_BUCKETS
        for name in (
            "observed_elapsed_bucket",
            "first_output_elapsed_bucket",
            "last_output_elapsed_bucket",
        )
    ) or progress.get("combined_output_bytes_bucket") not in _PROGRESS_BYTE_BUCKETS:
        raise RuntimeError("Provider progress telemetry has an invalid value")
    if progress["output_seen"] is False and (
        progress["first_output_elapsed_bucket"] != "none"
        or progress["last_output_elapsed_bucket"] != "none"
    ):
        raise RuntimeError("Provider progress telemetry is inconsistent")
    if set(progress) == terminal_keys:
        if (
            progress.get("first_activity_elapsed_bucket")
            not in _PROGRESS_ELAPSED_BUCKETS
            or progress.get("last_activity_elapsed_bucket")
            not in _PROGRESS_ELAPSED_BUCKETS
            or progress.get("permitted_mcp_calls") != permitted_mcp_calls
            or progress.get("activity_count_source")
            != "trusted_terminal_scorecard"
        ):
            raise RuntimeError("Provider progress telemetry is inconsistent")
        return progress
    return {
        **progress,
        "first_activity_elapsed_bucket": progress[
            "first_output_elapsed_bucket"
        ],
        "last_activity_elapsed_bucket": progress["last_output_elapsed_bucket"],
        "permitted_mcp_calls": permitted_mcp_calls,
        "activity_count_source": "trusted_terminal_scorecard",
    }


def _safe_live_provider_progress(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one coarse in-flight progress checkpoint."""

    if not isinstance(value, Mapping):
        raise ProviderStateIsolationError("Provider progress checkpoint was invalid")
    snapshot = dict(value)
    if snapshot == {
        "schema_version": "epiagentbench.provider_progress.v1",
        "status": "suppressed_credential_output",
    }:
        return snapshot
    base_keys = {
        "schema_version",
        "observed_elapsed_bucket",
        "output_seen",
        "first_output_elapsed_bucket",
        "last_output_elapsed_bucket",
        "combined_output_bytes_bucket",
    }
    terminal_keys = base_keys | {
        "first_activity_elapsed_bucket",
        "last_activity_elapsed_bucket",
        "permitted_mcp_calls",
        "activity_count_source",
    }
    if set(snapshot) not in (base_keys, terminal_keys):
        raise ProviderStateIsolationError("Provider progress checkpoint was invalid")
    if (
        snapshot.get("schema_version")
        != "epiagentbench.provider_progress.v1"
        or type(snapshot.get("output_seen")) is not bool
        or snapshot.get("observed_elapsed_bucket")
        not in _PROGRESS_ELAPSED_BUCKETS
        or snapshot.get("first_output_elapsed_bucket")
        not in _PROGRESS_ELAPSED_BUCKETS
        or snapshot.get("last_output_elapsed_bucket")
        not in _PROGRESS_ELAPSED_BUCKETS
        or snapshot.get("combined_output_bytes_bucket")
        not in _PROGRESS_BYTE_BUCKETS
    ):
        raise ProviderStateIsolationError("Provider progress checkpoint was invalid")
    if set(snapshot) == terminal_keys and (
        snapshot.get("first_activity_elapsed_bucket")
        not in _PROGRESS_ELAPSED_BUCKETS
        or snapshot.get("last_activity_elapsed_bucket")
        not in _PROGRESS_ELAPSED_BUCKETS
        or type(snapshot.get("permitted_mcp_calls")) is not int
        or not 0 <= snapshot["permitted_mcp_calls"] <= 50
        or snapshot.get("activity_count_source")
        != "trusted_terminal_scorecard"
    ):
        raise ProviderStateIsolationError("Provider progress checkpoint was invalid")
    return snapshot


def _result_timed_out(result: PilotRunResult) -> bool:
    return bool(
        result.timed_out
        or (
            result.returncode == 124
            and "agent_failure:timeout" in result.audit_events
        )
    )


def _preflight_profile_outcome(
    profile: Mapping[str, Any],
    *,
    invocation_state: str,
    outcome: str,
    timed_out: bool,
) -> dict[str, Any]:
    if invocation_state not in {"not_started", "started_not_finished", "finished"}:
        raise RuntimeError("Invalid preflight invocation state")
    if outcome not in {
        "passed",
        "failed_timeout",
        "failed_provider",
        "skipped_dependency",
        "terminal_abort",
        "not_started_terminal_abort",
    }:
        raise RuntimeError("Invalid preflight profile outcome")
    if type(timed_out) is not bool:
        raise RuntimeError("Invalid preflight timeout outcome")
    chargeable = invocation_state != "not_started"
    return {
        "profile_id": profile["profile_id"],
        "system": profile["system"],
        "requested_model": profile["requested_model"],
        "requested_reasoning": profile["requested_reasoning"],
        "invocation_state": invocation_state,
        "outcome": outcome,
        "timed_out": timed_out,
        "conservative_chargeable": chargeable,
    }


def run_environment_preflight(
    *,
    root: Path,
    authentication_key_file: Path,
    claude_secure_storage_dir: Path,
    codex_secure_storage_dir: Path,
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
    resolved_claude_secure_storage_dir = _validate_claude_secure_storage_dir(
        claude_secure_storage_dir, root=root
    )
    resolved_codex_secure_storage_dir = _validate_codex_secure_storage_dir(
        codex_secure_storage_dir, root=root
    )
    if _paths_overlap(
        resolved_claude_secure_storage_dir,
        resolved_codex_secure_storage_dir,
    ):
        raise ValueError("Claude and Codex secure storage directories must not overlap")
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
        _validate_public_hash(public)
        _assert_spend_authorization(private, public)
        _validate_claude_auth_binding(
            root=root,
            claude_secure_storage_dir=resolved_claude_secure_storage_dir,
            private=private,
            public=public,
        )
        _validate_codex_auth_binding(
            root=root,
            codex_secure_storage_dir=resolved_codex_secure_storage_dir,
            private=private,
            public=public,
        )
        claude_secure_storage_identity = _private_claude_storage_identity(
            private
        )
        codex_secure_storage_identity = _private_codex_storage_identity(private)
        cohort_manifest_path = _existing_path_without_final_symlink(
            str(private.get("cohort_manifest_path"))
        )
        _assert_claude_storage_separate_from_artifacts(
            resolved_claude_secure_storage_dir,
            cohort_manifest_path=cohort_manifest_path,
            authentication_key_file=authentication_key_file,
            private_state_path=private_state_path,
            public_manifest_path=public_manifest_path,
            additional_artifact_paths=(public_preflight_path,),
        )
        _assert_codex_storage_separate_from_artifacts(
            resolved_codex_secure_storage_dir,
            cohort_manifest_path=cohort_manifest_path,
            authentication_key_file=authentication_key_file,
            private_state_path=private_state_path,
            public_manifest_path=public_manifest_path,
            additional_artifact_paths=(public_preflight_path,),
        )
        if not os.environ.get("CURSOR_API_KEY", "").strip():
            raise RuntimeError(
                "Disposable six-profile preflight requires CURSOR_API_KEY before "
                "any provider call"
            )
        _validate_contracts(
            root=root,
            private=private,
            public=public,
            authentication_key=authentication_key,
            claude_secure_storage_dir=resolved_claude_secure_storage_dir,
            codex_secure_storage_dir=resolved_codex_secure_storage_dir,
        )
        if private.get("assignments") or private.get("status") != "prepared":
            raise RuntimeError("Environment preflight must precede production execution")
        preflight = private.get("environment_preflight")
        if not isinstance(preflight, dict) or preflight.get("status") != "required":
            raise RuntimeError("Environment preflight is not in its one-shot required state")
        if public_preflight_path.exists() or public_preflight_path.is_symlink():
            raise FileExistsError("Refusing to replace an environment preflight receipt")
        _require_claude_credential_state(
            resolved_claude_secure_storage_dir,
            root=root,
            expected_identity=claude_secure_storage_identity,
            managed_glean_credentials_present=False,
        )
        _require_codex_credential_state(
            resolved_codex_secure_storage_dir,
            root=root,
            expected_identity=codex_secure_storage_identity,
            credentials_present=False,
        )
        _preflight_execution(
            root=root,
            private_state_path=private_state_path,
            public_manifest_path=public_manifest_path,
            public_results_path=public_preflight_path,
        )
        _require_claude_credential_state(
            resolved_claude_secure_storage_dir,
            root=root,
            expected_identity=claude_secure_storage_identity,
            managed_glean_credentials_present=False,
        )
        _require_codex_credential_state(
            resolved_codex_secure_storage_dir,
            root=root,
            expected_identity=codex_secure_storage_identity,
            credentials_present=False,
        )

        contract_hashes = {
            name: public["contract_hashes"][name]
            for name in (
                "source_sha256",
                "cli_sha256",
                "claude_auth_sha256",
                "codex_auth_sha256",
                "profiles_sha256",
                "budgets_sha256",
                "timeouts_sha256",
                "runtime_sha256",
                "replay_sha256",
            )
        }
        cli_versions = {
            str(item["name"]): str(item["version"])
            for item in public["cli_contract"]["executables"]
        }
        timeout = int(public["timeout_contract"]["seconds_per_assignment"])
        claude_glean_oauth_client_id = _glean_claude_oauth_client_id()
        budget = float(
            public["budget_contract"]["claude_max_budget_usd_per_assignment"]
        )
        attempts: list[dict[str, Any]] = []
        private["environment_preflight"] = {
            "status": "running",
            "started_at_utc": _utc_now(),
            "attempts": attempts,
            "required_contract_hashes": contract_hashes,
            "managed_glean_auth_bootstrap": {"status": "not_started"},
            "codex_auth_bootstrap": {"status": "not_started"},
            "codex_auth_quarantine": {"status": "clear"},
        }
        _write_private_state(private_state_path, private, authentication_key)

        def persist_bootstrap_marker(
            name: str,
            *,
            expected_status: str,
            replacement: Mapping[str, Any],
        ) -> None:
            state = private["environment_preflight"][name]
            if state.get("status") != expected_status:
                raise ProviderStateIsolationError(
                    "Authentication bootstrap invocation marker changed"
                )
            private["environment_preflight"][name] = dict(replacement)
            try:
                _write_private_state(
                    private_state_path, private, authentication_key
                )
            except Exception:
                private["environment_preflight"][name] = state
                raise

        def mark_bootstrap_launch_pending(name: str) -> None:
            persist_bootstrap_marker(
                name,
                expected_status="not_started",
                replacement={
                    "status": "launch_pending",
                    "launch_pending_at_utc": _utc_now(),
                },
            )

        def mark_bootstrap_started(name: str) -> None:
            state = private["environment_preflight"][name]
            persist_bootstrap_marker(
                name,
                expected_status="launch_pending",
                replacement={
                    **state,
                    "status": "started",
                    "started_at_utc": _utc_now(),
                },
            )

        def mark_bootstrap_start_failed(name: str) -> None:
            state = private["environment_preflight"][name]
            persist_bootstrap_marker(
                name,
                expected_status="launch_pending",
                replacement={
                    **state,
                    "status": "start_failed",
                    "start_failed_at_utc": _utc_now(),
                },
            )

        def mark_bootstrap_returned(name: str, returncode: int) -> None:
            state = private["environment_preflight"][name]
            if type(returncode) is not int:
                raise ProviderStateIsolationError(
                    "Authentication bootstrap invocation marker changed"
                )
            persist_bootstrap_marker(
                name,
                expected_status="started",
                replacement={
                    **state,
                    "status": "returned",
                    "returned_at_utc": _utc_now(),
                    "returncode": returncode,
                },
            )

        public_attempts: list[dict[str, Any]] = []
        failure_stage = "codex_auth_bootstrap"
        active_bootstrap: str | None = None
        try:
            _attest_execution_contracts(root=root, public=public)
            _require_codex_credential_state(
                resolved_codex_secure_storage_dir,
                root=root,
                expected_identity=codex_secure_storage_identity,
                credentials_present=False,
            )
            active_bootstrap = "codex_auth_bootstrap"
            _bootstrap_codex_credentials(
                resolved_codex_secure_storage_dir,
                executable=str(_PROFILE_BY_ID["codex-sol"]["executable"]),
                timeout_seconds=timeout,
                invocation_launch_pending=lambda: mark_bootstrap_launch_pending(
                    "codex_auth_bootstrap"
                ),
                invocation_started=lambda: mark_bootstrap_started(
                    "codex_auth_bootstrap"
                ),
                invocation_start_failed=lambda: mark_bootstrap_start_failed(
                    "codex_auth_bootstrap"
                ),
                invocation_returned=lambda returncode: mark_bootstrap_returned(
                    "codex_auth_bootstrap", returncode
                ),
            )
            if private["environment_preflight"][active_bootstrap].get(
                "status"
            ) != "returned":
                raise ProviderStateIsolationError(
                    "Codex authentication bootstrap return was not recorded"
                )
            _require_codex_credential_state(
                resolved_codex_secure_storage_dir,
                root=root,
                expected_identity=codex_secure_storage_identity,
                credentials_present=True,
            )
            codex_auth_file_identity = _codex_auth_file_identity(
                resolved_codex_secure_storage_dir
            )
            private["codex_auth_file_identity"] = codex_auth_file_identity
            private["environment_preflight"]["codex_auth_bootstrap"] = {
                **private["environment_preflight"]["codex_auth_bootstrap"],
                "status": "passed",
                "finished_at_utc": _utc_now(),
            }
            _write_private_state(
                private_state_path, private, authentication_key
            )
            active_bootstrap = None
            failure_stage = "post_codex_auth_contract_attestation"
            _attest_execution_contracts(root=root, public=public)

            failure_stage = "managed_glean_auth_bootstrap"
            _attest_execution_contracts(root=root, public=public)
            _require_claude_credential_state(
                resolved_claude_secure_storage_dir,
                root=root,
                expected_identity=claude_secure_storage_identity,
                managed_glean_credentials_present=False,
            )
            active_bootstrap = "managed_glean_auth_bootstrap"
            _bootstrap_managed_glean_credentials(
                resolved_claude_secure_storage_dir,
                oauth_client_id=claude_glean_oauth_client_id,
                timeout_seconds=timeout,
                invocation_launch_pending=lambda: mark_bootstrap_launch_pending(
                    "managed_glean_auth_bootstrap"
                ),
                invocation_started=lambda: mark_bootstrap_started(
                    "managed_glean_auth_bootstrap"
                ),
                invocation_start_failed=lambda: mark_bootstrap_start_failed(
                    "managed_glean_auth_bootstrap"
                ),
                invocation_returned=lambda returncode: mark_bootstrap_returned(
                    "managed_glean_auth_bootstrap", returncode
                ),
            )
            if private["environment_preflight"][active_bootstrap].get(
                "status"
            ) != "returned":
                raise ProviderStateIsolationError(
                    "Managed Glean authentication bootstrap return was not recorded"
                )
            _require_claude_credential_state(
                resolved_claude_secure_storage_dir,
                root=root,
                expected_identity=claude_secure_storage_identity,
                managed_glean_credentials_present=True,
            )
            _require_codex_credential_state(
                resolved_codex_secure_storage_dir,
                root=root,
                expected_identity=codex_secure_storage_identity,
                credentials_present=True,
            )
            _require_codex_auth_file_identity(
                resolved_codex_secure_storage_dir,
                codex_auth_file_identity,
            )
            _attest_execution_contracts(root=root, public=public)
            private["environment_preflight"][
                "managed_glean_auth_bootstrap"
            ] = {
                **private["environment_preflight"][
                    "managed_glean_auth_bootstrap"
                ],
                "status": "passed",
                "finished_at_utc": _utc_now(),
            }
            _write_private_state(
                private_state_path, private, authentication_key
            )
            active_bootstrap = None
        except Exception as error:
            if active_bootstrap is not None:
                bootstrap_state = private["environment_preflight"][
                    active_bootstrap
                ]
                if bootstrap_state.get("status") in {"started", "returned"}:
                    private["environment_preflight"][active_bootstrap] = {
                        **bootstrap_state,
                        "status": "failed",
                        "finished_at_utc": _utc_now(),
                    }
            private["environment_preflight"] = {
                **private["environment_preflight"],
                "status": "failed",
                "finished_at_utc": _utc_now(),
            }
            terminal_profiles: list[dict[str, Any]] = []
            for profile in PROFILES:
                attempts.append(
                    {
                        "profile_id": profile["profile_id"],
                        "status": "not_started_terminal_abort",
                        "finished_at_utc": _utc_now(),
                    }
                )
                outcome = _preflight_profile_outcome(
                    profile,
                    invocation_state="not_started",
                    outcome="not_started_terminal_abort",
                    timed_out=False,
                )
                outcome.update(
                    {
                        "failure_reason": "authentication_bootstrap_failure",
                        "scored": False,
                        "infrastructure_handshake_passed": False,
                    }
                )
                terminal_profiles.append(outcome)
            _write_private_state(
                private_state_path, private, authentication_key
            )
            failed = {
                "schema_version": SCHEMA_VERSION,
                "panel_id": PANEL_ID,
                "status": "failed",
                "development_only": True,
                "production_episodes_consumed": 0,
                "contract_hashes": contract_hashes,
                "precommitment_sha256": public["precommitment_sha256"],
                "managed_glean_auth_bootstrap": private[
                    "environment_preflight"
                ]["managed_glean_auth_bootstrap"]["status"],
                "codex_auth_bootstrap": private[
                    "environment_preflight"
                ]["codex_auth_bootstrap"]["status"],
                "codex_auth_quarantine": "clear",
                "preflight_purpose": (
                    "unscored_infrastructure_routing_handshake"
                ),
                "profiles": terminal_profiles,
                "profiles_passed": [],
                "failed_profile_ids": list(_PROFILE_IDS),
                "failed_provider_invocation_state": None,
                "provider_calls_conservatively_chargeable": 0,
                "failure_reason": "authentication_bootstrap_failure",
                "failure_stage": failure_stage,
                "timed_out": False,
                "scores_reported": False,
            }
            _atomic_json(public_preflight_path, failed)
            private["environment_preflight"]["public_receipt_path"] = str(
                public_preflight_path.resolve()
            )
            private["environment_preflight"]["public_receipt_sha256"] = (
                _component_hash(failed)
            )
            _write_private_state(
                private_state_path, private, authentication_key
            )
            return failed

        shared_digest = hashlib.sha256(
            f"{PANEL_ID}|disposable-preflight|shared".encode("ascii")
        ).digest()
        for profile in PROFILES:
            profile_id = str(profile["profile_id"])
            quarantine = private["environment_preflight"][
                "codex_auth_quarantine"
            ]
            if (
                profile["system"] == "codex"
                and quarantine.get("status") == "quarantined"
            ):
                marker = {
                    "profile_id": profile_id,
                    "status": "skipped_dependency",
                    "finished_at_utc": _utc_now(),
                }
                attempts.append(marker)
                skipped = _preflight_profile_outcome(
                    profile,
                    invocation_state="not_started",
                    outcome="skipped_dependency",
                    timed_out=False,
                )
                skipped.update(
                    {
                        "failure_reason": "codex_auth_quarantined_after_timeout",
                        "scored": False,
                        "infrastructure_handshake_passed": False,
                    }
                )
                public_attempts.append(skipped)
                _write_private_state(
                    private_state_path, private, authentication_key
                )
                continue
            marker: dict[str, Any] = {
                "profile_id": profile_id,
                "status": "started",
                "started_at_utc": _utc_now(),
            }
            attempts.append(marker)
            _write_private_state(private_state_path, private, authentication_key)
            failure_stage = "provider_launch"
            result: PilotRunResult | None = None
            try:
                managed_glean_state_before: str | None = None
                codex_credentials_state_before: str | None = None
                if profile["system"] == "claude":
                    failure_stage = "credential_attestation"
                    _require_claude_credential_state(
                        resolved_claude_secure_storage_dir,
                        root=root,
                        expected_identity=claude_secure_storage_identity,
                        managed_glean_credentials_present=True,
                    )
                    managed_glean_state_before = "present"
                    failure_stage = "provider_launch"
                if profile["system"] == "codex":
                    failure_stage = "credential_attestation"
                    _require_codex_credential_state(
                        resolved_codex_secure_storage_dir,
                        root=root,
                        expected_identity=codex_secure_storage_identity,
                        credentials_present=True,
                    )
                    _require_codex_auth_file_identity(
                        resolved_codex_secure_storage_dir,
                        codex_auth_file_identity,
                    )
                    codex_credentials_state_before = "present"
                    failure_stage = "provider_launch"
                provider_auth_kwargs = (
                    {
                        "claude_secure_storage_dir": (
                            resolved_claude_secure_storage_dir
                        ),
                        "claude_glean_oauth_client_id": (
                            claude_glean_oauth_client_id
                        ),
                    }
                    if profile["system"] == "claude"
                    else (
                        {
                            "codex_auth_storage_dir": (
                                resolved_codex_secure_storage_dir
                            )
                        }
                        if profile["system"] == "codex"
                        else {}
                    )
                )
                failure_stage = "execution_contract_before_harness"
                _attest_execution_contracts(root=root, public=public)
                failure_stage = "provider_launch"
                marker["provider_invocation"] = {
                    "status": "started",
                    "started_at_utc": _utc_now(),
                }
                _write_private_state(
                    private_state_path, private, authentication_key
                )

                def persist_progress(snapshot: Mapping[str, Any]) -> None:
                    marker["progress_telemetry"] = (
                        _safe_live_provider_progress(snapshot)
                    )
                    _write_private_state(
                        private_state_path, private, authentication_key
                    )

                result = evaluate_local_cli_agent(
                    str(profile["system"]),
                    seed=int.from_bytes(shared_digest[:6], "big"),
                    family="reporting_artifact",
                    backend=BACKEND,
                    episode_secret=shared_digest,
                    model=str(profile["requested_model"]),
                    executable=str(profile["executable"]),
                    timeout_seconds=timeout,
                    claude_max_budget_usd=budget,
                    claude_effort=(
                        "high" if profile["system"] == "claude" else None
                    ),
                    codex_reasoning_effort=(
                        str(profile["requested_reasoning"])
                        if profile["system"] == "codex"
                        else None
                    ),
                    progress_callback=persist_progress,
                    **provider_auth_kwargs,
                )
                marker["provider_invocation"] = {
                    **marker["provider_invocation"],
                    "status": "finished",
                    "finished_at_utc": _utc_now(),
                }
                _write_private_state(
                    private_state_path, private, authentication_key
                )
                failure_stage = "execution_contract_after_harness"
                _attest_execution_contracts(root=root, public=public)
                if profile["system"] == "claude":
                    failure_stage = "credential_attestation"
                    _require_claude_credential_state(
                        resolved_claude_secure_storage_dir,
                        root=root,
                        expected_identity=claude_secure_storage_identity,
                        managed_glean_credentials_present=True,
                    )
                if profile["system"] == "codex":
                    failure_stage = "credential_attestation"
                    _require_codex_credential_state(
                        resolved_codex_secure_storage_dir,
                        root=root,
                        expected_identity=codex_secure_storage_identity,
                        credentials_present=True,
                    )
                    _require_codex_auth_file_identity(
                        resolved_codex_secure_storage_dir,
                        codex_auth_file_identity,
                    )
                failure_stage = "result_contract"
                if (
                    result.system != profile["system"]
                    or result.requested_model != profile["requested_model"]
                    or result.cli_version
                    != cli_versions[str(profile["executable"])]
                ):
                    raise RuntimeError(
                        "Disposable provider result contract drifted"
                    )
                receipt_required = (
                    profile["model_receipt_policy"]
                    == "provider_match_required"
                )
                receipt_ok = _exact_model_receipt_satisfied(
                    profile, result.observed_models
                )
                failure_stage = "trace_validation"
                try:
                    validate_replay_trace(result.replay_trace)
                except (TypeError, ValueError) as error:
                    raise RuntimeError(
                        "Disposable provider preflight replay contract failed"
                    ) from error
                failure_stage = "progress_validation"
                progress = _safe_provider_progress(result)
                timed_out = _result_timed_out(result)
                ordinary_failure_reason: str | None = None
                failure_stage = "harness_startup_contract"
                _raise_on_harness_startup_failure(result)
                failure_stage = "provider_contract"
                if timed_out:
                    ordinary_failure_reason = "timeout"
                elif result.returncode != 0 and ordinary_failure_reason is None:
                    ordinary_failure_reason = "nonzero_exit"
                elif receipt_required and not receipt_ok:
                    ordinary_failure_reason = "model_receipt_failure"
                raw_hash = _component_hash(asdict(result))
                if timed_out and profile["system"] == "codex":
                    private["environment_preflight"][
                        "codex_auth_quarantine"
                    ] = {
                        "status": "quarantined",
                        "reason": "cleanly_quiesced_timeout",
                        "profile_id": profile_id,
                        "quarantined_at_utc": _utc_now(),
                    }
                    _write_private_state(
                        private_state_path, private, authentication_key
                    )
                passed = ordinary_failure_reason is None
                marker.update(
                    {
                        "status": "passed" if passed else "failed",
                        "finished_at_utc": _utc_now(),
                        "raw_result_sha256": raw_hash,
                        "timed_out": timed_out,
                        "failure_reason": ordinary_failure_reason,
                        "progress_telemetry": progress,
                    }
                )
                public_attempt = _preflight_profile_outcome(
                    profile,
                    invocation_state="finished",
                    outcome=(
                        "passed"
                        if passed
                        else "failed_timeout"
                        if timed_out
                        else "failed_provider"
                    ),
                    timed_out=timed_out,
                )
                public_attempt.update(
                    {
                        "observed_models": list(result.observed_models),
                        "cli_version": result.cli_version,
                        "model_receipt_satisfied": (
                            receipt_ok if receipt_required else None
                        ),
                        "raw_result_sha256": raw_hash,
                        "replay_trace_validated": True,
                        "progress_telemetry": progress,
                        "failure_reason": ordinary_failure_reason,
                        "scored": False,
                        "infrastructure_handshake_passed": passed,
                    }
                )
                if profile["system"] == "claude":
                    public_attempt["managed_glean_credentials_state_before"] = (
                        managed_glean_state_before
                    )
                    public_attempt["managed_glean_credentials_state_after"] = (
                        "present"
                    )
                if profile["system"] == "codex":
                    public_attempt.update(
                        {
                            "codex_credentials_state_before": (
                                codex_credentials_state_before
                            ),
                            "codex_credentials_state_after": "present",
                            "codex_auth_link_before": "bound",
                            "codex_auth_link_after": "bound",
                            "refresh_persistence_attested": True,
                        }
                    )
                public_attempts.append(public_attempt)
                _write_private_state(private_state_path, private, authentication_key)
            except Exception as error:
                if isinstance(
                    error,
                    (CodexAuthenticationIncidentError, ProviderStateIsolationError),
                ):
                    marker.pop("progress_telemetry", None)
                marker.update(
                    {
                        "status": "terminal_abort",
                        "finished_at_utc": _utc_now(),
                        "failure_class": type(error).__name__,
                        "failure_stage": failure_stage,
                    }
                )
                invocation_state = _durable_provider_invocation_state(marker)
                timed_out = bool(
                    result is not None and _result_timed_out(result)
                )
                terminal_outcome = _preflight_profile_outcome(
                    profile,
                    invocation_state=invocation_state,
                    outcome="terminal_abort",
                    timed_out=timed_out,
                )
                terminal_outcome.update(
                    {
                        "failure_reason": "terminal_abort",
                        "failure_stage": failure_stage,
                        "scored": False,
                        "infrastructure_handshake_passed": False,
                    }
                )
                public_attempts.append(terminal_outcome)
                for remaining in PROFILES[len(public_attempts) :]:
                    remaining_marker = {
                        "profile_id": remaining["profile_id"],
                        "status": "not_started_terminal_abort",
                        "finished_at_utc": _utc_now(),
                    }
                    attempts.append(remaining_marker)
                    unstarted = _preflight_profile_outcome(
                        remaining,
                        invocation_state="not_started",
                        outcome="not_started_terminal_abort",
                        timed_out=False,
                    )
                    unstarted.update(
                        {
                            "failure_reason": "terminal_abort",
                            "scored": False,
                            "infrastructure_handshake_passed": False,
                        }
                    )
                    public_attempts.append(unstarted)
                failed = {
                    "schema_version": SCHEMA_VERSION,
                    "panel_id": PANEL_ID,
                    "status": "failed",
                    "development_only": True,
                    "production_episodes_consumed": 0,
                    "contract_hashes": contract_hashes,
                    "precommitment_sha256": public["precommitment_sha256"],
                    "managed_glean_auth_bootstrap": "passed",
                    "codex_auth_bootstrap": "passed",
                    "codex_auth_quarantine": private[
                        "environment_preflight"
                    ]["codex_auth_quarantine"]["status"],
                    "preflight_purpose": (
                        "unscored_infrastructure_routing_handshake"
                    ),
                    "profiles": public_attempts,
                    "profiles_passed": [
                        item
                        for item in public_attempts
                        if item["outcome"] == "passed"
                    ],
                    "failed_profile_id": profile_id,
                    "failed_provider_invocation_state": (
                        invocation_state
                    ),
                    "provider_calls_conservatively_chargeable": (
                        _conservatively_chargeable_provider_calls(attempts)
                    ),
                    "failure_reason": "terminal_abort",
                    "failure_stage": failure_stage,
                    "timed_out": timed_out,
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

        profile_failures = [
            item for item in public_attempts if item["outcome"] != "passed"
        ]
        receipt = {
            "schema_version": SCHEMA_VERSION,
            "panel_id": PANEL_ID,
            "status": "failed" if profile_failures else "passed",
            "development_only": True,
            "production_episodes_consumed": 0,
            "contract_hashes": contract_hashes,
            "precommitment_sha256": public["precommitment_sha256"],
            "managed_glean_auth_bootstrap": "passed",
            "codex_auth_bootstrap": "passed",
            "codex_auth_quarantine": private["environment_preflight"][
                "codex_auth_quarantine"
            ]["status"],
            "preflight_purpose": "unscored_infrastructure_routing_handshake",
            "profiles": public_attempts,
            "profiles_passed": [
                item for item in public_attempts if item["outcome"] == "passed"
            ],
            "failed_profile_ids": [
                item["profile_id"] for item in profile_failures
            ],
            "failed_provider_invocation_state": (
                profile_failures[0]["invocation_state"]
                if profile_failures
                else None
            ),
            "provider_calls_conservatively_chargeable": (
                _conservatively_chargeable_provider_calls(attempts)
            ),
            "failure_reason": (
                "one_or_more_profile_failures" if profile_failures else None
            ),
            "timed_out": any(item["timed_out"] for item in profile_failures),
            "scores_reported": False,
            "completed_at_utc": _utc_now(),
        }
        _atomic_json(public_preflight_path, receipt)
        private["environment_preflight"] = {
            **private["environment_preflight"],
            "status": receipt["status"],
            "finished_at_utc": receipt["completed_at_utc"],
            "public_receipt_path": str(public_preflight_path.resolve()),
            "public_receipt_sha256": _component_hash(receipt),
        }
        if not profile_failures:
            private["environment_preflight"][
                "passed_contract_hashes"
            ] = contract_hashes
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


def _reconcile_terminal_incident_public_progress(
    *,
    root: Path,
    public_manifest: Mapping[str, Any],
    private: Mapping[str, Any],
    public_results_path: Path,
) -> dict[str, Any]:
    """Repair only a trace-free public watermark after a durable incident."""

    expected = _public_running(
        public_manifest, private, status="stopped_transport_void"
    )
    relative = _relative_to_root(public_results_path, root)
    if _git_output(root, "ls-files", relative):
        raise RuntimeError(
            "Terminal-incident public progress path must remain untracked"
        )

    existing: dict[str, Any] | None = None
    if public_results_path.exists() or public_results_path.is_symlink():
        existing = _load_json(public_results_path)
        if set(existing) != set(expected):
            raise ValueError(
                "Terminal-incident public progress has an unsafe schema"
            )
        fixed_fields = (
            "schema_version",
            "panel_id",
            "precommitment_sha256",
            "development_only",
            "hermetic",
            "leaderboard_eligible",
            "started_at_utc",
            "planned_assignments",
        )
        if any(existing[name] != expected[name] for name in fixed_fields):
            raise ValueError(
                "Terminal-incident public progress differs from its panel"
            )
        if existing["status"] not in {
            "running",
            "stopped_transport_void",
        }:
            raise ValueError(
                "Terminal-incident public progress has an unsafe status"
            )
        if existing["results"] != [] or existing["summary"] != {
            "primary_estimand": "pending"
        }:
            raise ValueError(
                "Terminal-incident public progress must remain trace-free"
            )
        count_fields = (
            "terminal_assignments",
            "completed_assignments",
            "transport_voids",
        )
        for name in count_fields:
            value = existing[name]
            if (
                type(value) is not int
                or value < 0
                or value > expected[name]
            ):
                raise ValueError(
                    "Terminal-incident public progress watermark is unsafe"
                )
        if existing["terminal_assignments"] != (
            existing["completed_assignments"] + existing["transport_voids"]
        ):
            raise ValueError(
                "Terminal-incident public progress counts are inconsistent"
            )
        if existing == expected:
            return expected

    _atomic_json(public_results_path, expected)
    return expected


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
    sanitized["timed_out"] = _result_timed_out(result)
    sanitized["progress_telemetry"] = _safe_provider_progress(result)
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
    if any(
        private.get(name) is not None
        for name in ("execution_incident", "codex_auth_incident")
    ):
        raise RuntimeError(
            "A terminal provider incident blocks cohort completion and trace release"
        )
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
    claude_secure_storage_dir: Path,
    codex_secure_storage_dir: Path,
    private_state_path: Path,
    public_manifest_path: Path,
    public_results_path: Path,
    acknowledge_unbounded_provider_spend: bool = False,
) -> dict[str, Any]:
    """Run or resume the 300 assignments, never retrying a durable start."""

    if acknowledge_unbounded_provider_spend is not True:
        raise RuntimeError("Explicit acknowledgement of unbounded provider spend is required")
    resolved_claude_secure_storage_dir = _validate_claude_secure_storage_dir(
        claude_secure_storage_dir, root=root
    )
    resolved_codex_secure_storage_dir = _validate_codex_secure_storage_dir(
        codex_secure_storage_dir, root=root
    )
    if _paths_overlap(
        resolved_claude_secure_storage_dir,
        resolved_codex_secure_storage_dir,
    ):
        raise ValueError("Claude and Codex secure storage directories must not overlap")
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
    _validate_public_hash(public_manifest)
    _assert_spend_authorization(private, public_manifest)
    manifest, packs, schedule = _validate_contracts(
        root=root,
        private=private,
        public=public_manifest,
        authentication_key=authentication_key,
        claude_secure_storage_dir=resolved_claude_secure_storage_dir,
        codex_secure_storage_dir=resolved_codex_secure_storage_dir,
    )
    claude_secure_storage_identity = _private_claude_storage_identity(private)
    codex_secure_storage_identity = _private_codex_storage_identity(private)
    cohort_manifest_path = _existing_path_without_final_symlink(
        str(private["cohort_manifest_path"])
    )
    _assert_claude_storage_separate_from_artifacts(
        resolved_claude_secure_storage_dir,
        cohort_manifest_path=cohort_manifest_path,
        authentication_key_file=authentication_key_file,
        private_state_path=private_state_path,
        public_manifest_path=public_manifest_path,
        additional_artifact_paths=(public_results_path,),
    )
    _assert_codex_storage_separate_from_artifacts(
        resolved_codex_secure_storage_dir,
        cohort_manifest_path=cohort_manifest_path,
        authentication_key_file=authentication_key_file,
        private_state_path=private_state_path,
        public_manifest_path=public_manifest_path,
        additional_artifact_paths=(public_results_path,),
    )
    if (
        private.get("execution_incident") is not None
        or private.get("codex_auth_incident") is not None
    ):
        _reconcile_terminal_incident_public_progress(
            root=root,
            public_manifest=public_manifest,
            private=private,
            public_results_path=public_results_path,
        )
        if private.get("execution_incident") is not None:
            raise RuntimeError(
                "A terminal provider execution incident makes this panel "
                "non-resumable"
            )
        raise RuntimeError(
            "A terminal Codex authentication incident makes this panel "
            "non-resumable"
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
        interrupted_profile_id = str(assignments[-1]["profile_id"])
        private["execution_incident"] = {
            "status": "terminal",
            "assignment_index": len(assignments) - 1,
            "failure_class": "interrupted_after_durable_start",
        }
        if _PROFILE_BY_ID[interrupted_profile_id]["system"] == "codex":
            private["codex_auth_incident"] = {
                "status": "terminal",
                "assignment_index": len(assignments) - 1,
                "failure_class": "interrupted_after_durable_start",
            }
        assignments[-1]["status"] = "transport_void"
        assignments[-1]["finished_at_utc"] = _utc_now()
        assignments[-1]["void_reason"] = "interrupted_after_durable_start"
        private["status"] = "running"
        _write_private_state(private_state_path, private, authentication_key)
        stopped = _public_running(public_manifest, private, status="stopped_transport_void")
        _atomic_json(public_results_path, stopped)
        return stopped

    keys = _assignment_keys(schedule)
    remaining_profile_ids = {
        profile_id for _, profile_id in keys[len(assignments) :]
    }
    remaining_systems = {
        str(_PROFILE_BY_ID[profile_id]["system"])
        for profile_id in remaining_profile_ids
    }
    if (
        "cursor" in remaining_systems
        and not os.environ.get("CURSOR_API_KEY", "").strip()
    ):
        raise RuntimeError(
            "Production execution requires CURSOR_API_KEY before any new "
            "assignment is durably started"
        )
    if "claude" in remaining_systems:
        _require_claude_credential_state(
            resolved_claude_secure_storage_dir,
            root=root,
            expected_identity=claude_secure_storage_identity,
            managed_glean_credentials_present=True,
        )
    if "codex" in remaining_systems:
        codex_auth_file_identity = _private_codex_auth_file_identity(private)
        _require_codex_credential_state(
            resolved_codex_secure_storage_dir,
            root=root,
            expected_identity=codex_secure_storage_identity,
            credentials_present=True,
        )
        _require_codex_auth_file_identity(
            resolved_codex_secure_storage_dir,
            codex_auth_file_identity,
        )
    else:
        codex_auth_file_identity = None

    private["status"] = "running"
    _write_private_state(private_state_path, private, authentication_key)
    _atomic_json(public_results_path, _public_running(public_manifest, private))
    episode_by_ref = {str(item["episode_ref"]): item for item in private["episodes"]}
    cli_versions = {
        str(item["name"]): str(item["version"])
        for item in public_manifest["cli_contract"]["executables"]
    }
    timeout = int(public_manifest["timeout_contract"]["seconds_per_assignment"])
    claude_glean_oauth_client_id = _glean_claude_oauth_client_id()
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
        if profile["system"] == "claude":
            _require_claude_credential_state(
                resolved_claude_secure_storage_dir,
                root=root,
                expected_identity=claude_secure_storage_identity,
                managed_glean_credentials_present=True,
            )
        if profile["system"] == "codex":
            assert codex_auth_file_identity is not None
            _require_codex_credential_state(
                resolved_codex_secure_storage_dir,
                root=root,
                expected_identity=codex_secure_storage_identity,
                credentials_present=True,
            )
            _require_codex_auth_file_identity(
                resolved_codex_secure_storage_dir,
                codex_auth_file_identity,
            )
        _attest_execution_contracts(root=root, public=public_manifest)
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
        codex_auth_ambiguous = False
        try:
            def persist_progress(snapshot: Mapping[str, Any]) -> None:
                marker["progress_telemetry"] = _safe_live_provider_progress(
                    snapshot
                )
                _write_private_state(
                    private_state_path, private, authentication_key
                )

            provider_auth_kwargs = (
                {
                    "claude_secure_storage_dir": (
                        resolved_claude_secure_storage_dir
                    ),
                    "claude_glean_oauth_client_id": (
                        claude_glean_oauth_client_id
                    ),
                }
                if profile["system"] == "claude"
                else (
                    {
                        "codex_auth_storage_dir": (
                            resolved_codex_secure_storage_dir
                        )
                    }
                    if profile["system"] == "codex"
                    else {}
                )
            )
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
                codex_reasoning_effort=(
                    str(profile["requested_reasoning"])
                    if profile["system"] == "codex"
                    else None
                ),
                progress_callback=persist_progress,
                **provider_auth_kwargs,
            )
            _attest_execution_contracts(root=root, public=public_manifest)
            if profile["system"] == "claude":
                try:
                    _require_claude_credential_state(
                        resolved_claude_secure_storage_dir,
                        root=root,
                        expected_identity=claude_secure_storage_identity,
                        managed_glean_credentials_present=True,
                    )
                except (OSError, RuntimeError, ValueError):
                    raise ProviderStateIsolationError(
                        "Claude credential persistence isolation failed"
                    ) from None
            if profile["system"] == "codex":
                assert codex_auth_file_identity is not None
                try:
                    _require_codex_credential_state(
                        resolved_codex_secure_storage_dir,
                        root=root,
                        expected_identity=codex_secure_storage_identity,
                        credentials_present=True,
                    )
                    _require_codex_auth_file_identity(
                        resolved_codex_secure_storage_dir,
                        codex_auth_file_identity,
                    )
                except (OSError, RuntimeError, ValueError):
                    codex_auth_ambiguous = True
                    raise
            marker["raw_result"] = asdict(result)
            fixed_denominator_timeout = _result_timed_out(result)
            if profile["system"] == "codex" and fixed_denominator_timeout:
                codex_auth_ambiguous = True
                raise RuntimeError(
                    "Codex timeout makes credential refresh state ambiguous"
                )
            _raise_on_harness_startup_failure(
                replace(result, returncode=0)
                if fixed_denominator_timeout
                else result
            )
            if (
                type(result.returncode) is not int
                or result.returncode != 0
            ) and not fixed_denominator_timeout:
                raise RuntimeError("Provider CLI returned a nonzero transport status")
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
            if isinstance(
                error,
                (CodexAuthenticationIncidentError, ProviderStateIsolationError),
            ):
                marker.pop("progress_telemetry", None)
            if isinstance(error, ProviderExecutionIsolationError):
                private["execution_incident"] = {
                    "status": "terminal",
                    "assignment_index": len(assignments) - 1,
                    "failure_class": type(error).__name__,
                }
                if profile["system"] == "codex":
                    codex_auth_ambiguous = True
            if isinstance(error, CodexAuthenticationIncidentError):
                codex_auth_ambiguous = True
            if profile["system"] == "codex" and codex_auth_ambiguous:
                private["codex_auth_incident"] = {
                    "status": "terminal",
                    "assignment_index": len(assignments) - 1,
                    "failure_class": type(error).__name__,
                }
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
    claude_secure_storage_dir: Path,
    codex_secure_storage_dir: Path,
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
            claude_secure_storage_dir=claude_secure_storage_dir,
            codex_secure_storage_dir=codex_secure_storage_dir,
            private_state_path=private_state_path,
            public_manifest_path=public_manifest_path,
            public_results_path=public_results_path,
            acknowledge_unbounded_provider_spend=True,
        )
