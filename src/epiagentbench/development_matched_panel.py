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
import importlib
from importlib import metadata as importlib_metadata
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
import time
from tempfile import TemporaryDirectory, gettempdir
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
    ProviderAttemptPersistenceError,
    ProviderCLIReadinessTimeoutError,
    ProviderCompletionPersistenceError,
    ProviderExecutionIsolationError,
    ProviderInvocationPersistenceError,
    ProviderOutputIsolationError,
    ProviderProcessIsolationError,
    ProviderProgressPersistenceError,
    ProviderQuarantinePersistenceError,
    ProviderResultCheckpointPersistenceError,
    ProviderSpawnIsolationError,
    ProviderStateIsolationError,
    _ProviderTemporaryDirectory,
    _attest_codex_auth_storage,
    _attest_claude_secure_storage_keychain,
    _attest_managed_glean_home_link,
    _canonical_codex_auth_storage_path,
    _install_disposable_storage_roots,
    _isolate_claude_environment,
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
    _read_authentication_key as _read_authentication_key_unbound,
    compute_generator_fingerprint,
    freeze_private_starsim_cohort,
)
from .trusted.episode_pack import PrivateEpisodeCohortManifest, PrivateEpisodePack


PANEL_ID = "development-matched-50x6-v19"
COHORT_ID = PANEL_ID
SCHEMA_VERSION = "development_matched_panel_v19"
BACKEND = "starsim-ltc-v3"
REQUIRED_STARSIM_VERSION = "3.5.1"
EPISODE_COUNT = 50
EPISODES_PER_FAMILY = 10
ASSIGNMENT_COUNT = 300
BOOTSTRAP_REPLICATES = 20_000
REQUIRED_SPEND_ACKNOWLEDGEMENT = (
    "I acknowledge the replacement six-call v19 preflight and 300-assignment "
    "production run, including unbounded Codex/Cursor provider spend and up "
    "to $590 total Claude spend across the failed v2 preflight, failed v5 "
    "preflight, failed v6 authentication bootstrap, failed v7 preflight, "
    "failed v8 production run, v9 preflight and failed production run, the "
    "abandoned zero-model-call v10 precommitment, the failed zero-model-call "
    "v11 authentication bootstrap, the abandoned zero-model-call v12 "
    "precommitment, the abandoned zero-model-call v13 precommitment, the "
    "failed v14 preflight, the failed zero-model-call v15 pre-claim "
    "preparation, the failed v16 preflight, the failed zero-model-call v17 "
    "pre-start runtime-cache-environment refusal, the failed v18 preflight, "
    "and the v19 preflight and production run."
)
_PREPARATION_RUNTIME_PREFLIGHT_SCHEMA = (
    "epiagentbench.preparation_runtime_preflight.v2"
)
_BOUND_PREPARATION_RUNTIME_SCHEMA = (
    "epiagentbench.bound_preparation_runtime.v1"
)
_PREPARATION_RUNTIME_SMOKE_SCHEMA = (
    "epiagentbench.preparation_runtime_smoke.v1"
)
_PREPARATION_RUNTIME_SMOKE_GOLDEN_SHA256 = (
    "sha256:"
    "fad38877b79d2be90fbb136702878fb1c10f5547f0d0170a5ebcab6c9e776d12"
)
_RUNTIME_CACHE_CONTRACT_SCHEMA = "epiagentbench.runtime_cache_contract.v3"
_RUNTIME_CACHE_ENVIRONMENT_KEYS = (
    "MPLBACKEND",
    "MPLCONFIGDIR",
    "NUMBA_CACHE_DIR",
    "PYTHONDONTWRITEBYTECODE",
    "STARSIM_INSTALL_FONTS",
    "XDG_CACHE_HOME",
)
_SPEND_AUTHORIZATION_SCHEMA = "epiagentbench.spend_authorization.v2"
_AUTHENTICATION_SETUP_SCHEMA = "epiagentbench.authentication_setup.v2"
_AUTHENTICATION_RECEIPT_SCHEMA = "epiagentbench.authentication_receipt.v2"
_PUBLIC_RECEIPT_BINDING_SCHEMA = (
    "epiagentbench.repository_receipt_binding.v1"
)
_PUBLIC_RECEIPT_BINDING_KEYS = frozenset(
    {
        "schema_version",
        "artifact_kind",
        "repository_relative_path",
        "file_sha256",
        "content_sha256",
        "published_commit",
    }
)
_AUTHENTICATION_DEPENDENCY_FREEZE_SCHEMA = (
    "epiagentbench.authentication_dependency_freeze.v1"
)
_ROOT_MANAGED_EXECUTABLE_POLICY = (
    "root_owned_root_group_single_link_regular_nonwritable_executable"
)
_PRIVATE_STATE_STORAGE_SCHEMA = "epiagentbench.private_state_storage.v2"
_CLAUDE_CUMULATIVE_AUTHORIZATION_CEILING_USD = 590.0
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
_COHORT_FREEZE_CLAIM_DOMAIN = (
    b"EpiAgentBench authenticated create-once V19 cohort freeze claim v1\x00"
)
_COHORT_FREEZE_COMPLETION_DOMAIN = (
    b"EpiAgentBench authenticated create-once V19 cohort freeze completion v1\x00"
)
_COHORT_FREEZE_KEY_IDENTITY_DOMAIN = (
    b"EpiAgentBench V19 cohort freeze authentication key identity v1\x00"
)
_COHORT_FREEZE_CLAIM_SCHEMA = "epiagentbench.v19_cohort_freeze_claim.v1"
_COHORT_FREEZE_COMPLETION_SCHEMA = (
    "epiagentbench.v19_cohort_freeze_completion.v1"
)
_COHORT_FREEZE_CLAIM_FILE = (
    f".{PANEL_ID}.cohort-freeze-claim.v1.json"
)
_COHORT_FREEZE_COMPLETION_FILE = (
    f".{PANEL_ID}.cohort-freeze-completion.v1.json"
)
_COHORT_FREEZE_CLAIM_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "panel_id",
        "cohort_id",
        "backend",
        "episode_count",
        "runtime_receipt_file_sha256",
        "runtime_identity_sha256",
        "expected_benchmark_base_commit",
        "authentication_key_identity_commitment",
        "canonical_cohort_destination",
        "claimed_at_utc",
    }
)
_COHORT_FREEZE_COMPLETION_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "panel_id",
        "cohort_id",
        "freeze_claim_sha256",
        "canonical_cohort_destination",
        "manifest_file_sha256",
        "pack_set_commitment",
        "generator_fingerprint",
        "completed_at_utc",
    }
)
_COHORT_PREPARATION_DOMAIN = (
    b"EpiAgentBench authenticated create-once cohort preparation v1\x00"
)
_COHORT_PREPARATION_SCHEMA = "epiagentbench.cohort_preparation.v1"
_COHORT_PREPARATION_FILE = ".epiagentbench-cohort-prepared.json"
_COHORT_PREPARATION_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "cohort_id",
        "panel_id",
        "pack_set_commitment",
        "public_precommitment_sha256",
        "private_state_target_sha256",
        "public_manifest_target_sha256",
        "claimed_at_utc",
    }
)
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
_PENDING_PREFLIGHT_STATUS = "passed_pending_supervisor_completion"
_PENDING_PRODUCTION_STATUS = "complete_pending_supervisor_completion"
_PERSISTENT_EXECUTION_BINDINGS_KEY = "persistent_execution_bindings"
_PUBLIC_RELEASE_KEY = "public_release"
_SUPERVISOR_BINDING_FIELDS = frozenset(
    {
        "operation",
        "label",
        "execution_context_sha256",
        "config_file_sha256",
        "panel_id",
        "precommitment_sha256",
    }
)
_PERSISTENT_ATTESTATION_FAILURE_CODES = frozenset(
    {
        "supervisor_required",
        "public_contract_mismatch",
        "public_binding_invalid",
        "invalid_expectation",
        "config_integrity",
        "binding_mismatch",
        "start_commitment_missing",
        "start_commitment_invalid",
        "status_snapshot_unstable",
        "worker_status_invalid",
        "worker_not_running",
        "core_integrity",
        "core_not_started",
        "core_not_running",
        "core_phase_invalid",
        "core_unhealthy",
        "process_identity_mismatch",
        "heartbeat_stale",
        "binding_projection_invalid",
        "private_binding_invalid",
        "runtime_replacement",
        "attestation_internal",
    }
)
_PROVIDER_ISOLATION_FAILURE_CLASSES = frozenset(
    {
        "ProviderExecutionIsolationError",
        "ProviderAttemptPersistenceError",
        "ProviderCompletionPersistenceError",
        "ProviderInvocationPersistenceError",
        "ProviderOutputIsolationError",
        "ProviderProcessIsolationError",
        "ProviderProgressPersistenceError",
        "ProviderQuarantinePersistenceError",
        "ProviderResultCheckpointPersistenceError",
        "ProviderSpawnIsolationError",
        "ProviderStateIsolationError",
    }
)
_PROVIDER_INCIDENT_CODES = frozenset(
    {
        "credential_attestation_failed",
        "evaluator_return_contract_failed",
        "provider_adapter_execution_failed",
        "provider_attempt_marker_persist_failed",
        "provider_cli_readiness_timeout",
        "provider_completion_marker_persist_failed",
        "provider_execution_isolation_failed",
        "model_invocation_marker_persist_failed",
        "provider_output_isolation_failed",
        "provider_process_isolation_failed",
        "provider_progress_checkpoint_persist_failed",
        "provider_quarantine_checkpoint_persist_failed",
        "provider_result_checkpoint_persist_failed",
        "provider_interrupted_after_durable_attempt",
        "provider_result_processing_failed",
        "provider_spawn_failed",
        "provider_state_isolation_failed",
        "supervisor_boundary_attestation_failed",
        "unexpected_control_path_failure",
    }
)
_PREFLIGHT_FAILURE_STAGES = frozenset(
    {
        "codex_quarantine_checkpoint",
        "credential_attestation",
        "durable_attempt_marker",
        "execution_contract_after_harness",
        "execution_contract_before_harness",
        "glean_dependency_after_harness",
        "glean_dependency_before_harness",
        "harness_startup_contract",
        "progress_validation",
        "provider_completion_marker",
        "provider_contract",
        "provider_cli_readiness",
        "provider_execution",
        "model_invocation_marker",
        "provider_progress_checkpoint",
        "provider_result_checkpoint",
        "result_contract",
        "supervisor_attestation_after_harness",
        "supervisor_attestation_before_harness",
        "supervisor_attestation_final_completion",
        "trace_validation",
    }
)
_PRODUCTION_PUBLIC_FAILURE_STAGES = frozenset(
    {
        "provider_isolation_after_model_invocation_start",
        "provider_isolation_before_model_invocation",
        "provider_isolation_before_provider",
        "provider_isolation_final_completion",
        "supervisor_attestation_after_provider",
        "supervisor_attestation_before_provider",
        "supervisor_attestation_final_completion",
    }
)
_SNAPSHOT_ATTESTATION_DEADLINE_SECONDS = 0.25
_SNAPSHOT_ATTESTATION_RETRY_DELAYS_SECONDS = (0.05, 0.10)
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
        or (private and metadata.st_uid != os.getuid())
        or (private and metadata.st_nlink != 1)
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
                or (private and opened.st_uid != os.getuid())
                or (private and opened.st_nlink != 1)
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


def _create_public_json_once(path: Path, value: Any) -> None:
    """Publish one complete public JSON file without replacing an existing path."""

    path.parent.mkdir(parents=True, exist_ok=True)
    parent_metadata = path.parent.lstat()
    if not stat.S_ISDIR(parent_metadata.st_mode) or path.parent.is_symlink():
        raise ValueError("Matched-panel artifact parent must be a real directory")
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    if len(payload) > _MAX_PANEL_JSON_BYTES:
        raise ValueError("Matched-panel artifact exceeds the size limit")
    temporary = path.with_name(
        f".{path.name}.{secrets.token_hex(16)}.create-once"
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor: int | None = None
    temporary_exists = False
    try:
        descriptor = os.open(temporary, flags, 0o644)
        temporary_exists = True
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            descriptor = None
            os.fchmod(stream.fileno(), 0o644)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path, follow_symlinks=False)
        _fsync_directory(path.parent)
        temporary.unlink()
        temporary_exists = False
        _fsync_directory(path.parent)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary_exists:
            try:
                temporary.unlink()
            except OSError:
                pass


def create_provider_free_public_json_once(path: Path, value: Any) -> None:
    """Create and verify one canonical public JSON artifact without clobbering."""

    _create_public_json_once(path, value)
    if _load_json(path) != value:
        raise RuntimeError("Create-once public artifact verification failed")


def _read_canonical_public_json_bytes(path: Path) -> tuple[bytes, dict[str, Any]]:
    """Read one stable, canonical public JSON object without following links."""

    try:
        metadata = path.lstat()
    except OSError:
        raise ValueError("Provider-free publication source is unavailable") from None
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or metadata.st_nlink != 1
        or not 0 < metadata.st_size <= _MAX_PANEL_JSON_BYTES
    ):
        raise ValueError("Provider-free publication source is unsafe")
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
                or opened.st_uid != os.getuid()
                or opened.st_nlink != 1
                or opened.st_size != metadata.st_size
            ):
                raise ValueError(
                    "Provider-free publication source changed while opening"
                )
            payload = stream.read(_MAX_PANEL_JSON_BYTES + 1)
            after = os.fstat(stream.fileno())
    except OSError:
        raise ValueError("Provider-free publication source is unavailable") from None
    if (
        len(payload) != metadata.st_size
        or after.st_dev != opened.st_dev
        or after.st_ino != opened.st_ino
        or after.st_size != opened.st_size
        or after.st_mtime_ns != opened.st_mtime_ns
    ):
        raise ValueError("Provider-free publication source changed while reading")
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, ValueError, RecursionError):
        raise ValueError("Provider-free publication source is invalid") from None
    if not isinstance(value, dict):
        raise ValueError("Provider-free publication source must be an object")
    canonical = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    if not hmac.compare_digest(payload, canonical):
        raise ValueError("Provider-free publication source is not canonical")
    return payload, value


def publish_provider_free_public_json_once(
    *,
    source_path: Path,
    destination_path: Path,
) -> dict[str, Any]:
    """Publish exact canonical JSON bytes through the create-once link boundary."""

    if source_path.absolute() == destination_path.absolute():
        raise ValueError("Provider-free source and destination must differ")
    payload, value = _read_canonical_public_json_bytes(source_path)
    create_provider_free_public_json_once(destination_path, value)
    published, observed = _read_canonical_public_json_bytes(destination_path)
    if observed != value or not hmac.compare_digest(payload, published):
        raise RuntimeError("Provider-free publication bytes changed")
    return {
        "schema_version": "epiagentbench.provider_free_publication.v1",
        "status": "published",
        "provider_processes_started": 0,
        "authentication_processes_started": 0,
        "model_calls_started": 0,
    }


def _private_state_tag(value: Mapping[str, Any], key: bytes) -> str:
    return hmac.new(
        key,
        _PRIVATE_STATE_DOMAIN + _canonical_bytes(value),
        hashlib.sha256,
    ).hexdigest()


def _write_private_state(path: Path, value: Mapping[str, Any], key: bytes) -> None:
    _validate_bound_private_state_storage(path, value)
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
    _validate_bound_private_state_storage(path, value)


def _create_private_state_once(
    path: Path, value: Mapping[str, Any], key: bytes
) -> None:
    """Create the first authenticated checkpoint without replacing any path."""

    _validate_bound_private_state_storage(path, value)
    unsigned = dict(value)
    unsigned.pop("state_authentication", None)
    sealed = {
        **unsigned,
        "state_authentication": {
            "algorithm": "hmac-sha256",
            "tag": _private_state_tag(unsigned, key),
        },
    }
    if not _create_private_json_once(path, sealed):
        raise FileExistsError(
            "Refusing to replace an existing matched-panel private state"
        )
    _validate_bound_private_state_storage(path, value)


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
    _validate_bound_private_state_storage(path, sealed)
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
        raise ValueError("Create-once private record parent must be a real directory")
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if not 0 < len(payload) <= _MAX_PANEL_JSON_BYTES:
        raise ValueError("Create-once private record exceeds the size limit")
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
            else:
                _fsync_directory(path.parent)


def _cohort_freeze_key_identity(authentication_key: bytes) -> str:
    return "hmac-sha256:" + hmac.new(
        authentication_key,
        _COHORT_FREEZE_KEY_IDENTITY_DOMAIN + PANEL_ID.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()


def _cohort_freeze_claim_tag(
    value: Mapping[str, Any], authentication_key: bytes
) -> str:
    return hmac.new(
        authentication_key,
        _COHORT_FREEZE_CLAIM_DOMAIN + _canonical_bytes(value),
        hashlib.sha256,
    ).hexdigest()


def _cohort_freeze_completion_tag(
    value: Mapping[str, Any], authentication_key: bytes
) -> str:
    return hmac.new(
        authentication_key,
        _COHORT_FREEZE_COMPLETION_DOMAIN + _canonical_bytes(value),
        hashlib.sha256,
    ).hexdigest()


def _canonical_new_private_path(value: Path, *, label: str) -> Path:
    raw = value.expanduser()
    if not raw.is_absolute():
        raw = Path.cwd() / raw
    try:
        parent = raw.parent.resolve(strict=True)
    except OSError:
        raise ValueError(f"{label} parent must already exist") from None
    if not parent.is_dir() or parent.is_symlink() or raw.name in {"", ".", ".."}:
        raise ValueError(f"{label} parent must be a real directory")
    return parent / raw.name


def _canonical_cohort_destination(value: Path) -> Path:
    return _canonical_new_private_path(value, label="V19 cohort destination")


def _cohort_freeze_claim_path(
    authentication_key_path: Path,
    requested_path: Path | None = None,
) -> Path:
    """Return the one V19 claim location paired with this owner-only key."""

    expected = authentication_key_path.parent / _COHORT_FREEZE_CLAIM_FILE
    try:
        parent_metadata = expected.parent.lstat()
    except OSError:
        raise ValueError(
            "V19 authentication-key namespace is unavailable"
        ) from None
    if (
        not stat.S_ISDIR(parent_metadata.st_mode)
        or expected.parent.is_symlink()
        or parent_metadata.st_uid != os.getuid()
        or parent_metadata.st_mode & 0o077
    ):
        raise ValueError(
            "V19 authentication-key namespace must be owner-only"
        )
    if requested_path is None:
        return expected
    supplied = _canonical_new_private_path(
        requested_path, label="V19 cohort freeze claim"
    )
    if supplied != expected:
        raise ValueError(
            "V19 cohort freeze claim must use the canonical key-namespace path"
        )
    return expected


def _cohort_freeze_completion_path(claim_path: Path) -> Path:
    return claim_path.with_name(_COHORT_FREEZE_COMPLETION_FILE)


def _load_cohort_freeze_claim(
    path: Path, authentication_key: bytes
) -> dict[str, Any]:
    sealed = _load_json(path, private=True)
    authentication = sealed.pop("authentication", None)
    supplied = (
        authentication.get("tag") if isinstance(authentication, dict) else None
    )
    expected = _cohort_freeze_claim_tag(sealed, authentication_key)
    if (
        set(sealed) != _COHORT_FREEZE_CLAIM_KEYS
        or not isinstance(authentication, dict)
        or set(authentication) != {"algorithm", "tag"}
        or authentication.get("algorithm") != "hmac-sha256"
        or not isinstance(supplied, str)
        or not hmac.compare_digest(supplied, expected)
        or sealed.get("schema_version") != _COHORT_FREEZE_CLAIM_SCHEMA
        or sealed.get("status") != "pending_create_once_freeze"
    ):
        raise ValueError("V19 cohort freeze claim authentication failed")
    return sealed


def _load_cohort_freeze_completion(
    path: Path, authentication_key: bytes
) -> dict[str, Any]:
    sealed = _load_json(path, private=True)
    authentication = sealed.pop("authentication", None)
    supplied = (
        authentication.get("tag") if isinstance(authentication, dict) else None
    )
    expected = _cohort_freeze_completion_tag(sealed, authentication_key)
    if (
        set(sealed) != _COHORT_FREEZE_COMPLETION_KEYS
        or not isinstance(authentication, dict)
        or set(authentication) != {"algorithm", "tag"}
        or authentication.get("algorithm") != "hmac-sha256"
        or not isinstance(supplied, str)
        or not hmac.compare_digest(supplied, expected)
        or sealed.get("schema_version") != _COHORT_FREEZE_COMPLETION_SCHEMA
        or sealed.get("status") != "completed_create_once_freeze"
    ):
        raise ValueError("V19 cohort freeze completion authentication failed")
    return sealed


def _pending_cohort_freeze_claim(
    *,
    runtime_verification: Mapping[str, Any],
    expected_benchmark_base_commit: str,
    canonical_cohort_destination: Path,
    authentication_key: bytes,
) -> dict[str, Any]:
    receipt_hash = runtime_verification.get(
        "published_receipt_file_sha256"
    )
    runtime_identity = runtime_verification.get("runtime_identity_sha256")
    verified_commit = runtime_verification.get(
        "verified_benchmark_base_commit"
    )
    if (
        not _is_sha256(receipt_hash)
        or not _is_sha256(runtime_identity)
        or verified_commit != expected_benchmark_base_commit
    ):
        raise RuntimeError(
            "Verified V19 runtime receipt cannot bind a cohort freeze claim"
        )
    return {
        "schema_version": _COHORT_FREEZE_CLAIM_SCHEMA,
        "status": "pending_create_once_freeze",
        "panel_id": PANEL_ID,
        "cohort_id": COHORT_ID,
        "backend": BACKEND,
        "episode_count": EPISODE_COUNT,
        "runtime_receipt_file_sha256": receipt_hash,
        "runtime_identity_sha256": runtime_identity,
        "expected_benchmark_base_commit": expected_benchmark_base_commit,
        "authentication_key_identity_commitment": (
            _cohort_freeze_key_identity(authentication_key)
        ),
        "canonical_cohort_destination": str(
            canonical_cohort_destination
        ),
        "claimed_at_utc": _utc_now(),
    }


def _create_pending_cohort_freeze_claim(
    *,
    claim_path: Path,
    runtime_verification: Mapping[str, Any],
    expected_benchmark_base_commit: str,
    canonical_cohort_destination: Path,
    authentication_key: bytes,
) -> dict[str, Any]:
    """Burn the only V19 freeze attempt before any cohort randomness."""

    completion_path = _cohort_freeze_completion_path(claim_path)
    if completion_path.exists() or completion_path.is_symlink():
        raise FileExistsError(
            "V19 cohort freeze completion already exists; never rerun freeze"
        )
    claim = _pending_cohort_freeze_claim(
        runtime_verification=runtime_verification,
        expected_benchmark_base_commit=expected_benchmark_base_commit,
        canonical_cohort_destination=canonical_cohort_destination,
        authentication_key=authentication_key,
    )
    sealed = {
        **claim,
        "authentication": {
            "algorithm": "hmac-sha256",
            "tag": _cohort_freeze_claim_tag(claim, authentication_key),
        },
    }
    if not _create_private_json_once(claim_path, sealed):
        raise FileExistsError(
            "V19 cohort freeze already has a pending claim; interrupted "
            "freezes are terminal and must never be retried"
        )
    if _load_cohort_freeze_claim(claim_path, authentication_key) != claim:
        raise RuntimeError("V19 cohort freeze claim failed its durable reload")
    return claim


def _complete_cohort_freeze_claim(
    *,
    claim_path: Path,
    claim: Mapping[str, Any],
    manifest_path: Path,
    manifest: PrivateEpisodeCohortManifest,
    authentication_key: bytes,
) -> dict[str, Any]:
    """Append one authenticated completion without replacing the claim."""

    canonical_manifest_path = _existing_path_without_final_symlink(
        manifest_path
    )
    if canonical_manifest_path.name != "cohort.manifest":
        raise ValueError("V19 cohort manifest must use its canonical filename")
    completion = {
        "schema_version": _COHORT_FREEZE_COMPLETION_SCHEMA,
        "status": "completed_create_once_freeze",
        "panel_id": PANEL_ID,
        "cohort_id": COHORT_ID,
        "freeze_claim_sha256": _component_hash(claim),
        "canonical_cohort_destination": str(
            canonical_manifest_path.parent
        ),
        "manifest_file_sha256": _fixed_file_sha256(
            canonical_manifest_path, label="V19 frozen cohort manifest"
        ),
        "pack_set_commitment": manifest.pack_set_commitment,
        "generator_fingerprint": manifest.generator_fingerprint,
        "completed_at_utc": _utc_now(),
    }
    path = _cohort_freeze_completion_path(claim_path)
    sealed = {
        **completion,
        "authentication": {
            "algorithm": "hmac-sha256",
            "tag": _cohort_freeze_completion_tag(
                completion, authentication_key
            ),
        },
    }
    if not _create_private_json_once(path, sealed):
        raise FileExistsError(
            "V19 cohort freeze completion already exists; never replace it"
        )
    if _load_cohort_freeze_completion(path, authentication_key) != completion:
        raise RuntimeError(
            "V19 cohort freeze completion failed its durable reload"
        )
    return completion


def _require_completed_cohort_freeze_claim(
    *,
    claim_path: Path,
    manifest_path: Path,
    runtime_receipt_file_sha256: str,
    runtime_identity_sha256: str,
    expected_benchmark_base_commit: str,
    authentication_key: bytes,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Authenticate the immutable pending/completion pair for one cohort."""

    if not claim_path.exists() and not claim_path.is_symlink():
        raise ValueError(
            "Frozen V19 cohort has no authenticated create-once freeze claim"
        )
    claim = _load_cohort_freeze_claim(claim_path, authentication_key)
    completion_path = _cohort_freeze_completion_path(claim_path)
    if not completion_path.exists() and not completion_path.is_symlink():
        raise RuntimeError(
            "V19 cohort freeze remains pending; interrupted freezes are "
            "terminal and cannot be prepared or retried"
        )
    completion = _load_cohort_freeze_completion(
        completion_path, authentication_key
    )
    canonical_destination = manifest_path.parent.resolve(strict=True)
    if manifest_path.name != "cohort.manifest":
        raise ValueError("V19 cohort manifest must use its canonical filename")
    expected_claim = {
        "panel_id": PANEL_ID,
        "cohort_id": COHORT_ID,
        "backend": BACKEND,
        "episode_count": EPISODE_COUNT,
        "runtime_receipt_file_sha256": runtime_receipt_file_sha256,
        "runtime_identity_sha256": runtime_identity_sha256,
        "expected_benchmark_base_commit": expected_benchmark_base_commit,
        "authentication_key_identity_commitment": (
            _cohort_freeze_key_identity(authentication_key)
        ),
        "canonical_cohort_destination": str(canonical_destination),
    }
    if any(claim.get(name) != value for name, value in expected_claim.items()):
        raise ValueError("V19 cohort freeze claim belongs to another freeze")
    if not isinstance(claim.get("claimed_at_utc"), str) or not claim[
        "claimed_at_utc"
    ]:
        raise ValueError("V19 cohort freeze claim has no claim time")

    manifest = PrivateEpisodeCohortManifest.read(
        manifest_path, authentication_key
    )
    expected_completion = {
        "panel_id": PANEL_ID,
        "cohort_id": COHORT_ID,
        "freeze_claim_sha256": _component_hash(claim),
        "canonical_cohort_destination": str(canonical_destination),
        "manifest_file_sha256": _fixed_file_sha256(
            manifest_path, label="V19 frozen cohort manifest"
        ),
        "pack_set_commitment": manifest.pack_set_commitment,
        "generator_fingerprint": manifest.generator_fingerprint,
    }
    if any(
        completion.get(name) != value
        for name, value in expected_completion.items()
    ):
        raise ValueError(
            "V19 cohort freeze completion differs from its manifest or claim"
        )
    if not isinstance(completion.get("completed_at_utc"), str) or not completion[
        "completed_at_utc"
    ]:
        raise ValueError("V19 cohort freeze completion has no completion time")
    return claim, completion


def _cohort_preparation_path(cohort_manifest_path: Path) -> Path:
    return cohort_manifest_path.parent / _COHORT_PREPARATION_FILE


def _cohort_preparation_tag(value: Mapping[str, Any], key: bytes) -> str:
    return hmac.new(
        key,
        _COHORT_PREPARATION_DOMAIN + _canonical_bytes(value),
        hashlib.sha256,
    ).hexdigest()


def _load_cohort_preparation_marker(
    path: Path, key: bytes
) -> dict[str, Any]:
    sealed = _load_json(path, private=True)
    authentication = sealed.pop("authentication", None)
    supplied = (
        authentication.get("tag") if isinstance(authentication, dict) else None
    )
    expected = _cohort_preparation_tag(sealed, key)
    if (
        set(sealed) != _COHORT_PREPARATION_KEYS
        or not isinstance(authentication, dict)
        or set(authentication) != {"algorithm", "tag"}
        or authentication.get("algorithm") != "hmac-sha256"
        or not isinstance(supplied, str)
        or not hmac.compare_digest(supplied, expected)
        or sealed.get("schema_version") != _COHORT_PREPARATION_SCHEMA
        or sealed.get("status") != "claimed_create_once_preparation"
    ):
        raise ValueError("Cohort preparation marker authentication failed")
    return sealed


def _cohort_preparation_claim(
    *,
    manifest: PrivateEpisodeCohortManifest,
    public_manifest: Mapping[str, Any],
    private_state_path: Path,
    public_manifest_path: Path,
) -> dict[str, Any]:
    return {
        "schema_version": _COHORT_PREPARATION_SCHEMA,
        "status": "claimed_create_once_preparation",
        "cohort_id": manifest.cohort_id,
        "panel_id": PANEL_ID,
        "pack_set_commitment": manifest.pack_set_commitment,
        "public_precommitment_sha256": public_manifest[
            "precommitment_sha256"
        ],
        "private_state_target_sha256": _sha256(
            str(private_state_path.expanduser().resolve()).encode("utf-8")
        ),
        "public_manifest_target_sha256": _sha256(
            str(public_manifest_path.expanduser().resolve()).encode("utf-8")
        ),
        "claimed_at_utc": _utc_now(),
    }


def _claim_cohort_preparation(
    *,
    cohort_manifest_path: Path,
    manifest: PrivateEpisodeCohortManifest,
    public_manifest: Mapping[str, Any],
    private_state_path: Path,
    public_manifest_path: Path,
    authentication_key: bytes,
) -> dict[str, Any]:
    """Burn one frozen cohort into exactly one create-once preparation."""

    expected = _cohort_preparation_claim(
        manifest=manifest,
        public_manifest=public_manifest,
        private_state_path=private_state_path,
        public_manifest_path=public_manifest_path,
    )
    path = _cohort_preparation_path(cohort_manifest_path)
    sealed = {
        **expected,
        "authentication": {
            "algorithm": "hmac-sha256",
            "tag": _cohort_preparation_tag(expected, authentication_key),
        },
    }
    if not _create_private_json_once(path, sealed):
        raise FileExistsError(
            "Frozen cohort already has a preparation claim; never retry it"
        )
    if _load_cohort_preparation_marker(path, authentication_key) != expected:
        raise RuntimeError("Cohort preparation claim failed its post-write reload")
    return expected


def _assert_cohort_preparation_matches_panel(
    marker: Mapping[str, Any],
    *,
    manifest: PrivateEpisodeCohortManifest,
    public_manifest: Mapping[str, Any],
    private_state_path: Path,
    public_manifest_path: Path,
) -> None:
    expected = {
        "schema_version": _COHORT_PREPARATION_SCHEMA,
        "status": "claimed_create_once_preparation",
        "cohort_id": manifest.cohort_id,
        "panel_id": PANEL_ID,
        "pack_set_commitment": manifest.pack_set_commitment,
        "public_precommitment_sha256": public_manifest.get(
            "precommitment_sha256"
        ),
        "private_state_target_sha256": _sha256(
            str(private_state_path.expanduser().resolve()).encode("utf-8")
        ),
        "public_manifest_target_sha256": _sha256(
            str(public_manifest_path.expanduser().resolve()).encode("utf-8")
        ),
    }
    if any(marker.get(name) != value for name, value in expected.items()):
        raise ValueError("Cohort preparation marker belongs to another panel")
    if not isinstance(marker.get("claimed_at_utc"), str) or not marker[
        "claimed_at_utc"
    ]:
        raise ValueError("Cohort preparation marker has no claim time")


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
    try:
        private_relative = _relative_to_root(private_state_path, root)
    except ValueError:
        private_relative = None
    if (
        _git_output(root, "ls-files", "--error-unmatch", public_relative)
        != public_relative
    ):
        raise RuntimeError(
            "Public matched-panel precommitment must be committed before spend "
            "authorization"
        )
    if private_relative is not None and _git_output(
        root, "ls-files", private_relative
    ):
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


def _authentication_receipt_path(public_manifest_path: Path) -> Path:
    return public_manifest_path.with_name(f"{PANEL_ID}.authentication.json")


def _preflight_receipt_path(public_manifest_path: Path) -> Path:
    return public_manifest_path.with_name(f"{PANEL_ID}.preflight.json")


def _canonical_public_output_path(
    public_manifest_path: Path,
    *,
    operation: str,
) -> Path:
    if operation == "preflight":
        return _preflight_receipt_path(public_manifest_path)
    if operation == "production":
        return public_manifest_path.with_name(f"{PANEL_ID}.json")
    raise ValueError("Public output operation is invalid")


def _assert_canonical_public_output_path(
    public_manifest_path: Path,
    public_output_path: Path,
    *,
    operation: str,
) -> Path:
    expected = _canonical_public_output_path(
        public_manifest_path,
        operation=operation,
    )
    if Path(os.path.abspath(public_output_path)) != Path(
        os.path.abspath(expected)
    ):
        raise RuntimeError(
            f"Live {operation} public output path is not canonical"
        )
    return expected


def _public_json_file_sha256(value: Mapping[str, Any]) -> str:
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    return _sha256(payload)


def _assert_exact_public_json_bytes(
    path: Path,
    payload: Mapping[str, Any],
    *,
    label: str,
) -> str:
    expected = _public_json_file_sha256(payload)
    observed = _fixed_file_sha256(
        path,
        label=label,
        maximum_bytes=_MAX_PANEL_JSON_BYTES,
    )
    if not hmac.compare_digest(observed, expected):
        raise RuntimeError(f"Required {label} bytes are not canonical")
    return observed


def _repository_receipt_binding(
    *,
    root: Path,
    path: Path,
    artifact_kind: str,
    content_sha256: str,
    payload: Mapping[str, Any],
    published_commit: str | None = None,
) -> dict[str, Any]:
    if artifact_kind not in {"authentication", "preflight"}:
        raise ValueError("Public receipt binding kind is invalid")
    relative = _relative_to_root(path, root)
    if (
        not isinstance(content_sha256, str)
        or not content_sha256.startswith("sha256:")
        or len(content_sha256) != 71
    ):
        raise ValueError("Public receipt content digest is invalid")
    if published_commit is not None and (
        len(published_commit) != 40
        or any(character not in "0123456789abcdef" for character in published_commit)
    ):
        raise ValueError("Public receipt publishing commit is invalid")
    return {
        "schema_version": _PUBLIC_RECEIPT_BINDING_SCHEMA,
        "artifact_kind": artifact_kind,
        "repository_relative_path": relative,
        "file_sha256": _public_json_file_sha256(payload),
        "content_sha256": content_sha256,
        "published_commit": published_commit,
    }


def _git_blob_sha256(root: Path, commit: str, relative: str) -> str:
    try:
        size = int(_git_output(root, "cat-file", "-s", f"{commit}:{relative}"))
    except (RuntimeError, ValueError):
        raise RuntimeError("Committed public receipt blob is unavailable") from None
    if not 0 < size <= _MAX_PANEL_JSON_BYTES:
        raise RuntimeError("Committed public receipt blob has an invalid size")
    process = subprocess.run(
        ["git", "cat-file", "blob", f"{commit}:{relative}"],
        cwd=root,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=20,
    )
    if process.returncode != 0 or len(process.stdout) != size:
        raise RuntimeError("Committed public receipt blob is unavailable")
    return _sha256(process.stdout)


def _validate_repository_receipt_binding(
    binding: Any,
    *,
    root: Path,
    path: Path,
    artifact_kind: str,
    content_sha256: str,
    payload: Mapping[str, Any],
    require_published_commit: bool,
) -> dict[str, Any]:
    expected = _repository_receipt_binding(
        root=root,
        path=path,
        artifact_kind=artifact_kind,
        content_sha256=content_sha256,
        payload=payload,
        published_commit=None,
    )
    if (
        not isinstance(binding, dict)
        or set(binding) != _PUBLIC_RECEIPT_BINDING_KEYS
        or any(
            binding.get(name) != value
            for name, value in expected.items()
            if name != "published_commit"
        )
    ):
        raise RuntimeError("Public receipt repository binding changed")
    commit = binding.get("published_commit")
    if commit is None:
        if require_published_commit:
            raise RuntimeError(
                "Public receipt has not been bound to its publishing commit"
            )
        return binding
    if (
        not isinstance(commit, str)
        or len(commit) != 40
        or any(character not in "0123456789abcdef" for character in commit)
    ):
        raise RuntimeError("Public receipt publishing commit is invalid")
    relative = str(binding["repository_relative_path"])
    _git_output(root, "merge-base", "--is-ancestor", commit, "HEAD")
    if _git_blob_sha256(root, commit, relative) != binding["file_sha256"]:
        raise RuntimeError("Committed public receipt bytes changed")
    return binding


def _receipt_path_from_binding(
    root: Path,
    binding: Any,
    *,
    artifact_kind: str,
) -> Path:
    if not isinstance(binding, Mapping):
        raise RuntimeError("Public receipt repository binding is missing")
    relative = binding.get("repository_relative_path")
    if (
        binding.get("artifact_kind") != artifact_kind
        or not isinstance(relative, str)
        or not relative
    ):
        raise RuntimeError("Public receipt repository binding is invalid")
    path = root / relative
    try:
        resolved_root = root.resolve(strict=True)
        resolved_path = path.resolve(strict=True)
        resolved_path.relative_to(resolved_root)
    except (OSError, RuntimeError, ValueError):
        raise RuntimeError("Public receipt repository binding is invalid") from None
    expected_name = (
        f"{PANEL_ID}.authentication.json"
        if artifact_kind == "authentication"
        else f"{PANEL_ID}.preflight.json"
    )
    if resolved_path.name != expected_name:
        raise RuntimeError("Public receipt repository binding is invalid")
    return resolved_path


def _path_is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _paths_overlap(first: Path, second: Path) -> bool:
    return _path_is_within(first, second) or _path_is_within(second, first)


def _temporary_storage_roots() -> tuple[Path, ...]:
    roots: list[Path] = []
    for candidate in (
        Path("/tmp"),
        Path("/private/tmp"),
        Path("/var/tmp"),
        Path(gettempdir()),
    ):
        try:
            resolved = candidate.resolve(strict=True)
        except OSError:
            resolved = candidate.resolve(strict=False)
        if resolved not in roots:
            roots.append(resolved)
    return tuple(roots)


def _is_temporary_storage_path(path: Path) -> bool:
    resolved = path.expanduser().resolve(strict=False)
    return any(
        _path_is_within(resolved, temporary_root)
        for temporary_root in _temporary_storage_roots()
    )


def _private_state_storage_binding(
    path: Path,
    *,
    root: Path,
    create_temporary_test_parent: bool = False,
) -> dict[str, Any]:
    """Bind one canonical private state path to its durable parent directory."""

    candidate = path.expanduser()
    if not candidate.is_absolute():
        raise ValueError("Private matched-panel state path must be absolute")
    resolved_root = root.resolve(strict=True)
    temporary_test_root = _is_temporary_storage_path(resolved_root)
    if (
        temporary_test_root
        and create_temporary_test_parent
        and not candidate.parent.exists()
    ):
        candidate.parent.mkdir(parents=True, mode=0o700)
        os.chmod(candidate.parent, 0o700)
    try:
        resolved_parent = candidate.parent.resolve(strict=True)
        parent_metadata = candidate.parent.lstat()
    except (OSError, RuntimeError):
        raise ValueError(
            "Private matched-panel state parent must already exist"
        ) from None
    canonical_path = resolved_parent / candidate.name
    if not temporary_test_root and candidate.parent != resolved_parent:
        raise ValueError(
            "Private matched-panel state parent must not contain symlinks"
        )
    if (
        not stat.S_ISDIR(parent_metadata.st_mode)
        or stat.S_ISLNK(parent_metadata.st_mode)
        or parent_metadata.st_uid != os.getuid()
    ):
        raise ValueError(
            "Private matched-panel state parent must be a current-user real directory"
        )
    storage_class = (
        "temporary_offline_test"
        if temporary_test_root
        else "durable_external"
    )
    if storage_class == "durable_external":
        if (
            stat.S_IMODE(parent_metadata.st_mode) != 0o700
            or _path_is_within(resolved_parent, resolved_root)
            or _is_temporary_storage_path(resolved_parent)
        ):
            raise ValueError(
                "Live private matched-panel state must use a pre-existing "
                "current-user 0700 directory outside the repository and OS "
                "temporary storage"
            )
    else:
        try:
            _relative_to_root(canonical_path, resolved_root)
        except ValueError:
            raise ValueError(
                "Offline-test private state must remain inside its temporary root"
            ) from None
    if candidate.exists() or candidate.is_symlink():
        metadata = candidate.lstat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_nlink != 1
        ):
            raise ValueError(
                "Private matched-panel state must be a current-user, "
                "single-link 0600 regular file"
            )
    return {
        "schema_version": _PRIVATE_STATE_STORAGE_SCHEMA,
        "storage_class": storage_class,
        "canonical_path": str(canonical_path),
        "parent_device": int(parent_metadata.st_dev),
        "parent_inode": int(parent_metadata.st_ino),
    }


def _private_state_storage_identity(path: Path) -> dict[str, Any]:
    """Revalidate one private file without binding it to a checkout path."""

    candidate = path.expanduser()
    if not candidate.is_absolute():
        raise ValueError("Private matched-panel state path must be absolute")
    try:
        resolved_parent = candidate.parent.resolve(strict=True)
        parent_metadata = candidate.parent.lstat()
    except (OSError, RuntimeError):
        raise ValueError(
            "Private matched-panel state parent must already exist"
        ) from None
    if (
        not stat.S_ISDIR(parent_metadata.st_mode)
        or stat.S_ISLNK(parent_metadata.st_mode)
        or parent_metadata.st_uid != os.getuid()
    ):
        raise ValueError(
            "Private matched-panel state parent must be a current-user real directory"
        )
    if candidate.exists() or candidate.is_symlink():
        metadata = candidate.lstat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_nlink != 1
        ):
            raise ValueError(
                "Private matched-panel state must be a current-user, "
                "single-link 0600 regular file"
            )
    return {
        "canonical_path": str(resolved_parent / candidate.name),
        "parent_device": int(parent_metadata.st_dev),
        "parent_inode": int(parent_metadata.st_ino),
    }


def _validate_bound_private_state_storage(
    path: Path, private: Mapping[str, Any]
) -> None:
    binding = private.get("private_state_storage")
    expected_keys = {
        "schema_version",
        "storage_class",
        "canonical_path",
        "parent_device",
        "parent_inode",
    }
    if (
        not isinstance(binding, Mapping)
        or set(binding) != expected_keys
        or binding.get("schema_version") != _PRIVATE_STATE_STORAGE_SCHEMA
        or binding.get("storage_class")
        not in {"durable_external", "temporary_offline_test"}
        or not isinstance(binding.get("canonical_path"), str)
        or type(binding.get("parent_device")) is not int
        or type(binding.get("parent_inode")) is not int
    ):
        raise ValueError("Invalid private matched-panel state storage binding")
    identity = _private_state_storage_identity(path)
    observed = {
        "schema_version": _PRIVATE_STATE_STORAGE_SCHEMA,
        "storage_class": binding["storage_class"],
        **identity,
    }
    parent = Path(str(identity["canonical_path"])).parent
    parent_metadata = parent.lstat()
    if (
        binding["storage_class"] == "durable_external"
        and (
            _is_temporary_storage_path(parent)
            or stat.S_IMODE(parent_metadata.st_mode) != 0o700
        )
        or binding["storage_class"] == "temporary_offline_test"
        and not _is_temporary_storage_path(parent)
    ):
        raise ValueError("Private matched-panel state storage class changed")
    if not hmac.compare_digest(
        _canonical_bytes(dict(binding)), _canonical_bytes(observed)
    ):
        raise ValueError("Private matched-panel state storage binding changed")


def assert_durable_live_execution_paths(
    *, root: Path, private_state_path: Path
) -> None:
    """Reject live CLI execution from a disposable checkout or state path."""

    resolved_root = root.resolve(strict=True)
    root_metadata = root.lstat()
    if (
        not stat.S_ISDIR(root_metadata.st_mode)
        or stat.S_ISLNK(root_metadata.st_mode)
        or root_metadata.st_uid != os.getuid()
        or _is_temporary_storage_path(resolved_root)
    ):
        raise RuntimeError(
            "Live matched-panel execution requires a current-user durable "
            "repository checkout outside OS temporary storage"
        )
    binding = _private_state_storage_binding(
        private_state_path,
        root=resolved_root,
    )
    if binding["storage_class"] != "durable_external":
        raise RuntimeError(
            "Live matched-panel execution requires durable external private state"
        )


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
            "authentication_stage": (
                "foreground_interactive_zero_model_before_preflight"
            ),
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
            "authentication_stage": (
                "foreground_device_auth_zero_model_before_preflight"
            ),
            "device_auth_flag": "--device-auth",
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
    *,
    credential_name: str = "auth.json",
) -> bool:
    """Best-effort rollback without ever removing an unrelated target."""

    try:
        target_metadata = os.stat(
            credential_name,
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
        os.unlink(credential_name, dir_fd=target_directory_descriptor)
        os.fsync(target_directory_descriptor)
    except OSError:
        return False
    return True


def _promote_staged_codex_auth(
    source_directory: Path,
    target_directory: Path,
    *,
    expected_target_identity: Mapping[str, int],
    credential_name: str = "auth.json",
    maximum_bytes: int = _CODEX_BOOTSTRAP_AUTH_BYTES_MAX,
    provider_label: str = "Codex",
) -> None:
    """Publish one opaque auth file with a same-filesystem no-clobber move."""

    if (
        not credential_name
        or "/" in credential_name
        or credential_name in {".", ".."}
        or maximum_bytes < 1
    ):
        raise ValueError("Invalid authentication promotion contract")

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
                f"{provider_label} authentication target changed before promotion"
            )
        source_directory_metadata = os.fstat(source_directory_descriptor)
        if source_directory_metadata.st_dev != target_directory_metadata.st_dev:
            raise ProviderStateIsolationError(
                f"{provider_label} authentication staging filesystem changed"
            )

        flags = os.O_RDONLY
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        flags |= getattr(os, "O_NONBLOCK", 0)
        try:
            source_descriptor = os.open(
                credential_name,
                flags,
                dir_fd=source_directory_descriptor,
            )
        except FileNotFoundError:
            raise RuntimeError(
                f"{provider_label} authentication bootstrap failed"
            ) from None
        except OSError:
            raise ProviderStateIsolationError(
                f"{provider_label} authentication staged credential is unsafe"
            ) from None
        source_metadata = os.fstat(source_descriptor)
        if (
            not stat.S_ISREG(source_metadata.st_mode)
            or source_metadata.st_uid != os.getuid()
            or stat.S_IMODE(source_metadata.st_mode) != 0o600
            or source_metadata.st_nlink != 1
            or not 1
            <= source_metadata.st_size
            <= maximum_bytes
            or source_metadata.st_dev != target_directory_metadata.st_dev
        ):
            raise ProviderStateIsolationError(
                f"{provider_label} authentication staged credential is unsafe"
            )
        try:
            path_metadata = os.stat(
                credential_name,
                dir_fd=source_directory_descriptor,
                follow_symlinks=False,
            )
            os.fsync(source_descriptor)
        except OSError:
            raise ProviderStateIsolationError(
                f"{provider_label} authentication staged credential changed"
            ) from None
        if not _same_codex_bootstrap_metadata(
            source_metadata, path_metadata, _CODEX_BOOTSTRAP_FILE_FIELDS
        ):
            raise ProviderStateIsolationError(
                f"{provider_label} authentication staged credential changed"
            )

        try:
            os.link(
                credential_name,
                credential_name,
                src_dir_fd=source_directory_descriptor,
                dst_dir_fd=target_directory_descriptor,
                follow_symlinks=False,
            )
            linked = True
            os.fsync(target_directory_descriptor)
            target_metadata = os.stat(
                credential_name,
                dir_fd=target_directory_descriptor,
                follow_symlinks=False,
            )
            source_after_link = os.fstat(source_descriptor)
        except OSError:
            raise ProviderStateIsolationError(
                f"{provider_label} authentication credential promotion failed"
            ) from None
        if (
            target_metadata.st_dev != source_metadata.st_dev
            or target_metadata.st_ino != source_metadata.st_ino
            or target_metadata.st_nlink != 2
            or source_after_link.st_nlink != 2
        ):
            raise ProviderStateIsolationError(
                f"{provider_label} authentication credential promotion changed"
            )

        try:
            os.unlink(credential_name, dir_fd=source_directory_descriptor)
            os.fsync(source_directory_descriptor)
            os.fsync(target_directory_descriptor)
            final_target_metadata = os.stat(
                credential_name,
                dir_fd=target_directory_descriptor,
                follow_symlinks=False,
            )
        except OSError:
            raise ProviderStateIsolationError(
                f"{provider_label} authentication credential promotion failed"
            ) from None
        try:
            os.stat(
                credential_name,
                dir_fd=source_directory_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            pass
        except OSError:
            raise ProviderStateIsolationError(
                f"{provider_label} authentication staging state is unavailable"
            ) from None
        else:
            raise ProviderStateIsolationError(
                f"{provider_label} authentication staging entry remained after promotion"
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
                f"{provider_label} authentication credential promotion changed"
            )
        linked = False
    except BaseException as error:
        rollback_failed = False
        if linked and source_metadata is not None:
            rollback_failed = not _remove_promoted_codex_auth_if_owned(
                target_directory_descriptor,
                source_metadata,
                credential_name=credential_name,
            )
        if rollback_failed:
            raise ProviderStateIsolationError(
                f"{provider_label} authentication credential promotion rollback failed"
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
    stdin_target: int | None = subprocess.DEVNULL,
    umask: int,
    invocation_launch_pending: Callable[[], None] | None = None,
    invocation_started: Callable[[], None] | None = None,
    invocation_start_failed: Callable[[], None] | None = None,
    invocation_returned: Callable[[int], None] | None = None,
) -> subprocess.CompletedProcess[None]:
    """Run an authentication helper without capturing credential-bearing output."""

    if (
        stdin_target not in {None, subprocess.DEVNULL}
        or stdout_target not in {None, subprocess.DEVNULL}
        or stderr_target not in {None, subprocess.DEVNULL}
    ):
        raise ValueError("Authentication process streams must not be captured")
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
                stdin=stdin_target,
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
                    "--device-auth",
                    "-c",
                    'cli_auth_credentials_store="file"',
                ],
                cwd=root,
                environment=environment,
                timeout_seconds=timeout_seconds,
                stdin_target=None,
                stdout_target=None,
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


def _managed_glean_auth_file_identity(path: Path) -> dict[str, int]:
    if not _attest_managed_glean_credentials(path):
        raise RuntimeError("Managed Glean credential file is unavailable")
    try:
        metadata = (path / "credentials.json").lstat()
    except OSError:
        raise RuntimeError("Managed Glean credential file is unavailable") from None
    return {"device": int(metadata.st_dev), "inode": int(metadata.st_ino)}


def _require_managed_glean_auth_file_identity(
    path: Path, expected_identity: Mapping[str, int]
) -> None:
    if _managed_glean_auth_file_identity(path) != dict(expected_identity):
        raise RuntimeError("Managed Glean credential file identity changed")


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
    """Authenticate into same-filesystem staging, then publish without clobber."""

    target_identity = _claude_secure_storage_identity(path)
    if _attest_managed_glean_credentials(path):
        raise ProviderStateIsolationError(
            "Managed Glean authentication target changed"
        )
    with _ProviderTemporaryDirectory(directory=path.parent) as temporary:
        root = Path(temporary).resolve()
        staging = root / "credentials"
        runtime = root / "runtime"
        try:
            staging.mkdir(mode=0o700)
            runtime.mkdir(mode=0o700)
        except OSError:
            raise ProviderStateIsolationError(
                "Managed Glean authentication staging directory is unsafe"
            ) from None
        environment = os.environ.copy()
        glean_home_link = _isolate_claude_environment(
            environment, runtime, staging, oauth_client_id
        )
        if glean_home_link is None:
            raise RuntimeError("Managed Glean bootstrap isolation failed")
        _attest_managed_glean_home_link(glean_home_link, staging)
        try:
            process = _run_no_capture_process_group(
                [str(_GLEAN_GATEWAY_TOKEN_WRAPPER_PATH)],
                cwd=runtime,
                environment=environment,
                timeout_seconds=timeout_seconds,
                stdin_target=None,
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
                _attest_managed_glean_home_link(glean_home_link, staging)
            except Exception:
                if not isinstance(
                    active_error, ProviderExecutionIsolationError
                ):
                    raise
        if process.returncode != 0:
            raise RuntimeError("Managed Glean authentication bootstrap failed")
        if _claude_secure_storage_identity(path) != target_identity:
            raise ProviderStateIsolationError(
                "Managed Glean authentication target changed"
            )
        if _attest_managed_glean_credentials(path):
            raise ProviderStateIsolationError(
                "Managed Glean authentication target changed"
            )
        if not _attest_managed_glean_credentials(staging):
            raise RuntimeError("Managed Glean authentication bootstrap failed")
        _promote_staged_codex_auth(
            staging,
            path,
            expected_target_identity=target_identity,
            credential_name="credentials.json",
            maximum_bytes=_MAX_MANAGED_GLEAN_CREDENTIAL_BYTES,
            provider_label="Managed Glean",
        )
        if not _attest_managed_glean_credentials(path):
            raise ProviderStateIsolationError(
                "Managed Glean authentication credential promotion failed"
            )


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
        "examples/run_persistent_panel_supervisor.py",
        "src/epiagentbench",
        "src/epiagentbench_client",
        "schemas",
        "pyproject.toml",
    )
    paths = sorted({line for line in output.splitlines() if line})
    required = {
        "examples/run_development_matched_panel.py",
        "examples/run_persistent_panel_supervisor.py",
        "src/epiagentbench/development_matched_panel.py",
        "src/epiagentbench/launchd_agent.py",
        "src/epiagentbench/persistent_supervisor.py",
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
        "executable_sha256": digest,
    }


def _fixed_file_sha256(
    path: Path,
    *,
    label: str,
    maximum_bytes: int | None = None,
) -> str:
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
        or (
            maximum_bytes is not None
            and not 0 < metadata.st_size <= maximum_bytes
        )
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


def _read_authentication_key(path: Path) -> bytes:
    """Read the V19 key only when one stable inode owns its namespace."""

    try:
        before = path.lstat()
    except OSError:
        raise RuntimeError("V19 authentication key is unavailable") from None
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
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_uid != os.getuid()
        or before.st_mode & 0o077
        or before.st_nlink != 1
    ):
        raise RuntimeError(
            "V19 authentication key must be an owner-only single-link file"
        )
    try:
        key = _read_authentication_key_unbound(path)
        after = path.lstat()
    except (OSError, ValueError):
        raise RuntimeError("V19 authentication key is unavailable") from None
    if any(
        getattr(after, field) != getattr(before, field)
        for field in stable_fields
    ):
        raise RuntimeError("V19 authentication key changed while reading")
    return key


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


def _read_owned_json(
    path: Path,
    *,
    label: str,
    owner_uid: int,
    max_bytes: int = 64 * 1024,
) -> tuple[bytes, dict[str, Any]]:
    """Read one bounded owner-controlled JSON file through a stable descriptor."""

    try:
        metadata = path.lstat()
    except OSError:
        raise RuntimeError(f"Required {label} is unavailable") from None
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != owner_uid
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


def _read_root_owned_json(
    path: Path, *, label: str, max_bytes: int = 64 * 1024
) -> tuple[bytes, dict[str, Any]]:
    return _read_owned_json(
        path,
        label=label,
        owner_uid=0,
        max_bytes=max_bytes,
    )


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
        digest = _root_owned_regular_executable_sha256(
            _GLEAN_HELPER_PATH, label="Glean helper"
        )
    except (OSError, RuntimeError):
        raise ProviderStateIsolationError(
            "Unable to pin Glean helper identity"
        ) from None
    try:
        final_digest = _root_owned_regular_executable_sha256(
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
        "sha256": digest,
        "policy": _ROOT_MANAGED_EXECUTABLE_POLICY,
    }


def _glean_gateway_dispatch_contract() -> dict[str, Any]:
    return {
        "argv0_basename": "glean-llm-gateway-token",
        "arguments": [],
        "option_source": "glean.DefaultOptions",
        "oauth_client_id_source": "explicit_GLEAN_HELPER_OAUTH_CLIENT_ID",
        "credential_path": "$HOME/.glean-llm-gateway/credentials.json",
    }


def _require_root_owned_regular_executable_metadata(
    metadata: os.stat_result, *, label: str
) -> None:
    """Enforce the root-managed executable policy on one metadata sample."""

    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != 0
        or metadata.st_gid != 0
        or metadata.st_nlink != 1
        or metadata.st_mode & 0o022
        or not metadata.st_mode & 0o111
    ):
        raise RuntimeError(f"Required {label} ownership policy drifted")


def _require_root_owned_nonwritable_ancestry(
    path: Path, *, label: str
) -> None:
    """Exclude non-root pathname replacement through every ancestor."""

    current = path.parent
    while True:
        try:
            metadata = current.lstat()
        except OSError:
            raise RuntimeError(
                f"Required {label} ancestor is unavailable"
            ) from None
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != 0
            or metadata.st_gid != 0
            or metadata.st_mode & 0o022
        ):
            raise RuntimeError(
                f"Required {label} ancestor ownership policy drifted"
            )
        if current.parent == current:
            break
        current = current.parent


def _root_owned_regular_executable_sha256(path: Path, *, label: str) -> str:
    """Hash a stable root-owned executable and re-attest its path policy."""

    if not path.is_absolute():
        raise RuntimeError(f"Required {label} path must be absolute")
    _require_root_owned_nonwritable_ancestry(path, label=label)
    try:
        before = path.lstat()
    except OSError:
        raise RuntimeError(f"Required {label} is unavailable") from None
    _require_root_owned_regular_executable_metadata(before, label=label)
    digest = _fixed_file_sha256(path, label=label)
    try:
        after = path.lstat()
    except OSError:
        raise RuntimeError(f"Required {label} changed while hashing") from None
    _require_root_owned_regular_executable_metadata(after, label=label)
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
    if any(
        getattr(after, field) != getattr(before, field)
        for field in stable_fields
    ):
        raise RuntimeError(f"Required {label} changed while hashing")
    _require_root_owned_nonwritable_ancestry(path, label=label)
    return digest


def _root_owned_regular_executable_identity(
    path: Path, *, label: str
) -> dict[str, Any]:
    """Pin one fixed, nonsymlink root-managed executable entrypoint."""

    digest = _root_owned_regular_executable_sha256(path, label=label)
    try:
        resolved = path.resolve(strict=True)
        entry_metadata = path.lstat()
        resolved_metadata = resolved.lstat()
    except (OSError, RuntimeError):
        raise RuntimeError(f"Unable to resolve required {label}") from None
    _require_root_owned_regular_executable_metadata(
        entry_metadata, label=label
    )
    _require_root_owned_regular_executable_metadata(
        resolved_metadata, label=label
    )
    if (
        (entry_metadata.st_dev, entry_metadata.st_ino)
        != (resolved_metadata.st_dev, resolved_metadata.st_ino)
        or resolved != path
    ):
        raise RuntimeError(f"Required {label} must be a fixed regular file")
    final_digest = _root_owned_regular_executable_sha256(path, label=label)
    if not hmac.compare_digest(digest, final_digest):
        raise RuntimeError(f"Required {label} changed during identity probe")
    return {
        "path": str(path),
        "entrypoint_kind": "regular_file",
        "link_text": None,
        "resolved_path": str(resolved),
        "target_sha256": digest,
        "policy": _ROOT_MANAGED_EXECUTABLE_POLICY,
    }


def _deferred_root_owned_executable_contract(
    path: Path, *, label: str
) -> dict[str, Any]:
    """Validate a fixed root-managed entrypoint without freezing its bytes yet."""

    if not path.is_absolute():
        raise RuntimeError(f"Required {label} path must be absolute")
    try:
        metadata = path.lstat()
    except OSError:
        raise RuntimeError(f"Required {label} is unavailable") from None
    _require_root_owned_nonwritable_ancestry(path, label=label)
    _require_root_owned_regular_executable_metadata(metadata, label=label)
    return {
        "path": str(path),
        "entrypoint_kind": "root_owned_single_link_regular_executable",
        "group_or_world_writable": False,
        "trusted_root_owned_nonwritable_ancestry": True,
        "exact_content_freeze_stage": (
            "manifest_bound_spend_authorization_before_authentication"
        ),
        "freeze_once": True,
        "required_live_attestation_boundaries": [
            "before_and_after_foreground_authentication",
            "before_and_after_each_preflight_provider_call",
            "before_and_after_each_production_provider_call",
        ],
    }


def _current_glean_auth_dependency_identity() -> dict[str, Any]:
    """Take one internally consistent, process-free snapshot of mutable helpers."""

    def read_once() -> dict[str, Any]:
        try:
            wrapper = _root_owned_regular_executable_identity(
                _GLEAN_GATEWAY_TOKEN_WRAPPER_PATH,
                label="Glean LLM gateway token wrapper",
            )
            wrapper["dispatch_contract"] = _glean_gateway_dispatch_contract()
            return {
                "schema_version": _AUTHENTICATION_DEPENDENCY_FREEZE_SCHEMA,
                "glean_helper": _glean_helper_identity(),
                "glean_llm_gateway_token_wrapper": wrapper,
            }
        except ProviderExecutionIsolationError:
            raise
        except (OSError, RuntimeError, ValueError):
            raise ProviderStateIsolationError(
                "Unable to attest Glean authentication dependencies"
            ) from None

    first = read_once()
    second = read_once()
    if first != second:
        raise ProviderStateIsolationError(
            "Glean authentication dependencies changed during identity freeze"
        )
    return first


def _cli_contract() -> dict[str, Any]:
    network_overrides = [
        name for name in _MATCHED_PANEL_NETWORK_OVERRIDES if os.environ.get(name)
    ]
    if network_overrides:
        raise RuntimeError(
            "Matched-panel preparation forbids ambient proxy or custom-CA overrides"
        )
    identities: dict[str, dict[str, Any]] = {}
    for profile in PROFILES:
        executable = str(profile["executable"])
        if executable not in identities:
            identities[executable] = _read_cli_identity(executable)
    glean_config, glean_config_identity = _safe_glean_config()
    managed_settings, telemetry_enabled = _managed_settings_identity(
        glean_config
    )
    gateway_wrapper = _deferred_root_owned_executable_contract(
        _GLEAN_GATEWAY_TOKEN_WRAPPER_PATH,
        label="Glean LLM gateway token wrapper",
    )
    gateway_wrapper["dispatch_contract"] = _glean_gateway_dispatch_contract()
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
            "glean_helper": _deferred_root_owned_executable_contract(
                _GLEAN_HELPER_PATH,
                label="Glean helper",
            ),
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


def _installed_distribution_content_identity(name: str) -> dict[str, Any]:
    """Hash the installed bytes, not only the wheel RECORD declaration."""

    try:
        distribution = importlib_metadata.distribution(name)
    except importlib_metadata.PackageNotFoundError:
        return {
            "installed_file_count": 0,
            "installed_file_bytes": 0,
            "installed_content_sha256": None,
        }
    files = distribution.files
    if files is None or not 1 <= len(files) <= 100_000:
        raise RuntimeError(
            f"Unable to enumerate installed distribution bytes: {name}"
        )
    inventory: dict[str, dict[str, Any]] = {}
    total_bytes = 0
    for package_path in sorted(files, key=str):
        relative = str(package_path)
        if (
            not relative
            or "\x00" in relative
            or relative in inventory
        ):
            raise RuntimeError(
                f"Installed distribution has an invalid file inventory: {name}"
            )
        candidate = Path(distribution.locate_file(package_path))
        try:
            metadata = candidate.lstat()
        except OSError:
            raise RuntimeError(
                f"Installed distribution file is unavailable: {name}"
            ) from None
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_size < 0
            or metadata.st_size > 512 * 1024 * 1024
        ):
            raise RuntimeError(
                f"Installed distribution file is unsafe: {name}"
            )
        total_bytes += metadata.st_size
        if total_bytes > 4 * 1024 * 1024 * 1024:
            raise RuntimeError(
                f"Installed distribution exceeds the attestation limit: {name}"
            )
        inventory[relative] = {
            "size_bytes": metadata.st_size,
            "sha256": _fixed_file_sha256(
                candidate,
                label=f"{name} installed file",
            ),
        }
    return {
        "installed_file_count": len(inventory),
        "installed_file_bytes": total_bytes,
        "installed_content_sha256": _component_hash(inventory),
    }


def _scientific_module_origin_identity(name: str) -> dict[str, str]:
    """Prove the imported top-level module belongs to the bytes we hashed."""

    module = importlib.import_module(name)
    module_file = getattr(module, "__file__", None)
    if not isinstance(module_file, str) or not module_file:
        raise RuntimeError(
            f"Scientific module has no regular origin: {name}"
        )
    try:
        origin = Path(module_file).resolve(strict=True)
        metadata = origin.lstat()
    except (OSError, RuntimeError):
        raise RuntimeError(
            f"Scientific module origin is unavailable: {name}"
        ) from None
    if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise RuntimeError(
            f"Scientific module origin is unsafe: {name}"
        )
    if name == "epiagentbench":
        expected = Path(__file__).resolve(strict=True).parent / "__init__.py"
        if origin != expected:
            raise RuntimeError(
                "EpiAgentBench imported from outside the tracked source tree"
            )
        return {
            "origin_role": "tracked_repository_source",
            "distribution_file": "src/epiagentbench/__init__.py",
            "sha256": _fixed_file_sha256(
                origin, label="EpiAgentBench package origin"
            ),
        }
    try:
        distribution = importlib_metadata.distribution(name)
    except importlib_metadata.PackageNotFoundError:
        raise RuntimeError(
            f"Scientific distribution is unavailable: {name}"
        ) from None
    files = distribution.files
    if files is None:
        raise RuntimeError(
            f"Scientific distribution inventory is unavailable: {name}"
        )
    matches = [
        str(package_path)
        for package_path in files
        if Path(distribution.locate_file(package_path)).resolve(
            strict=False
        )
        == origin
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"Imported module is not uniquely owned by its distribution: {name}"
        )
    return {
        "origin_role": "installed_distribution_file",
        "distribution_file": matches[0],
        "sha256": _fixed_file_sha256(
            origin, label=f"{name} imported module origin"
        ),
    }


def _runtime_cache_contract(runtime_cache_dir: Path) -> dict[str, Any]:
    root = runtime_cache_dir.expanduser().absolute()
    expected_environment = {
        "MPLBACKEND": "Agg",
        "MPLCONFIGDIR": str(root / "matplotlib"),
        "NUMBA_CACHE_DIR": str(root / "numba"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "STARSIM_INSTALL_FONTS": "0",
        "XDG_CACHE_HOME": str(root / "xdg"),
    }
    if any(
        os.environ.get(name) != expected_environment[name]
        for name in _RUNTIME_CACHE_ENVIRONMENT_KEYS
    ):
        raise RuntimeError(
            "V19 runtime-cache environment does not match the exact contract"
        )
    from .launchd_agent import (
        _runtime_cache_contract as _private_runtime_cache_contract,
    )

    try:
        contract = _private_runtime_cache_contract(root)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from None
    if (
        contract.get("schema_version") != _RUNTIME_CACHE_CONTRACT_SCHEMA
        or contract.get("environment") != expected_environment
    ):
        raise RuntimeError("V19 runtime-cache contract is inconsistent")
    return contract


def _runtime_cache_root_from_environment() -> Path:
    matplotlib_path = os.environ.get("MPLCONFIGDIR")
    if not isinstance(matplotlib_path, str) or not matplotlib_path:
        raise RuntimeError("V19 runtime-cache environment is unavailable")
    candidate = Path(matplotlib_path)
    if candidate.name != "matplotlib":
        raise RuntimeError("V19 runtime-cache environment is invalid")
    root = candidate.parent
    _runtime_cache_contract(root)
    return root


def _preparation_runtime_smoke() -> dict[str, Any]:
    """Verify one fixed causal transmission/control result in real Starsim.

    The no-action and contact-stop worlds share an identical trace, seed,
    natural history, and random seed.  Each policy branch is executed twice.
    The complete projected result must both reproduce exactly and match the
    reviewed digest pinned in source; a merely successful Starsim import is
    insufficient.
    """

    from .trusted.engine import EngineControl
    from .trusted.institution_traces import (
        InstitutionTrace,
        TraceContact,
        TracePerson,
    )
    from .trusted.starsim_ltc_v3 import (
        CONTACT_REDUCTION_LEVEL,
        DAY_MINUTES,
        DESIGN_PLACEHOLDER,
        PERSON_TO_PERSON,
        RESIDENT,
        STAFF,
        LtcNorovirusNaturalHistory,
        LtcNorovirusStarsimEngine,
        LtcStarsimV3Config,
        RoleInfectiousnessProfile,
    )

    trace = InstitutionTrace(
        people=(
            TracePerson(
                "golden-index",
                RESIDENT,
                "golden-ward",
                "golden-room-a",
            ),
            TracePerson(
                "golden-contact",
                STAFF,
                "golden-ward",
                None,
            ),
            TracePerson(
                "golden-isolated",
                RESIDENT,
                "golden-ward",
                "golden-room-b",
            ),
        ),
        shifts=(),
        meals=(),
        entries=(),
        contacts=(
            TraceContact(
                "golden-direct-care",
                "golden-index",
                "golden-contact",
                0,
                60,
                "direct_care",
                "golden-ward",
            ),
        ),
        horizon_minutes=4 * DAY_MINUTES,
    )
    config = LtcStarsimV3Config(
        random_seed=1601,
        seed_person_ids=("golden-index",),
        evidence_status=DESIGN_PLACEHOLDER,
        horizon_days=4,
        timestep_minutes=DAY_MINUTES,
        natural_history=LtcNorovirusNaturalHistory(
            contact_beta_per_day=1.0,
            incubation_days=1.0,
            infectious_days=3.0,
            role_profiles=(
                RoleInfectiousnessProfile(
                    role=RESIDENT,
                    symptomatic_probability=1.0,
                    symptomatic_relative_infectiousness=1.0,
                    asymptomatic_relative_infectiousness=0.1,
                ),
                RoleInfectiousnessProfile(
                    role=STAFF,
                    symptomatic_probability=1.0,
                    symptomatic_relative_infectiousness=1.0,
                    asymptomatic_relative_infectiousness=0.1,
                ),
            ),
        ),
    )

    def summarize(snapshot: Any) -> dict[str, Any]:
        return {
            "minute": snapshot.minute,
            "state_counts": dict(
                sorted(Counter(person.state for person in snapshot.people).items())
            ),
            "transmission_counts_by_mechanism": dict(
                sorted(
                    Counter(
                        event.mechanism
                        for event in snapshot.transmission_events
                    ).items()
                )
            ),
            "applied_control_ids": list(snapshot.applied_control_ids),
            "terminal": snapshot.terminal,
        }

    def run_branch(
        *, apply_contact_stop: bool
    ) -> tuple[dict[str, str], dict[str, Any]]:
        engine = LtcNorovirusStarsimEngine(trace, config)
        try:
            if apply_contact_stop:
                engine.apply_control(
                    EngineControl(
                        control_id="v19-stop-direct-care",
                        kind=CONTACT_REDUCTION_LEVEL,
                        effective_minute=DAY_MINUTES,
                        magnitude=0.0,
                    )
                )
            boundaries = [summarize(engine.private_snapshot())]
            for day in range(1, 5):
                engine.advance_to(day * DAY_MINUTES)
                boundaries.append(summarize(engine.private_snapshot()))
            return (
                engine.public_descriptor,
                {
                    "boundaries": boundaries,
                    "transmission_events": [
                        asdict(event)
                        for event in engine.private_snapshot().transmission_events
                    ],
                },
            )
        finally:
            engine.close()

    reproduced: dict[str, dict[str, Any]] = {}
    engine_descriptor: dict[str, str] | None = None
    for branch_name, apply_contact_stop in (
        ("no_action", False),
        ("contact_stop_action", True),
    ):
        first = run_branch(apply_contact_stop=apply_contact_stop)
        second = run_branch(apply_contact_stop=apply_contact_stop)
        if first != second:
            raise RuntimeError(
                f"V19 Starsim golden smoke is nondeterministic: {branch_name}"
            )
        descriptor, branch = first
        if engine_descriptor is None:
            engine_descriptor = descriptor
        elif descriptor != engine_descriptor:
            raise RuntimeError(
                "V19 Starsim golden smoke changed engine descriptors"
            )
        reproduced[branch_name] = branch

    no_action = reproduced["no_action"]
    contact_stop_action = reproduced["contact_stop_action"]
    no_action_secondary_count = sum(
        event["mechanism"] == PERSON_TO_PERSON
        for event in no_action["transmission_events"]
    )
    action_secondary_count = sum(
        event["mechanism"] == PERSON_TO_PERSON
        for event in contact_stop_action["transmission_events"]
    )
    paired_checks = {
        "matched_opening": (
            no_action["boundaries"][0]
            == contact_stop_action["boundaries"][0]
        ),
        "matched_through_day_one": (
            no_action["boundaries"][1]
            == contact_stop_action["boundaries"][1]
        ),
        "no_action_person_to_person_secondary_count": (
            no_action_secondary_count
        ),
        "action_person_to_person_secondary_count": action_secondary_count,
        "prevented_person_to_person_secondary_count": (
            no_action_secondary_count - action_secondary_count
        ),
        "known_branch_divergence": no_action != contact_stop_action,
    }
    expected_paired_checks = {
        "matched_opening": True,
        "matched_through_day_one": True,
        "no_action_person_to_person_secondary_count": 1,
        "action_person_to_person_secondary_count": 0,
        "prevented_person_to_person_secondary_count": 1,
        "known_branch_divergence": True,
    }
    if paired_checks != expected_paired_checks:
        raise RuntimeError(
            "V19 Starsim golden smoke lost its causal transmission/control "
            "divergence"
        )

    projection = {
        "engine_descriptor": engine_descriptor,
        "scientific_scope": (
            "deterministic_capability_smoke_not_calibration_evidence"
        ),
        "branch_runs_per_policy": 2,
        "fixed_scenario": {
            "population_by_role": {"resident": 2, "staff": 1},
            "explicit_contact_edges": 1,
            "index_seed_count": 1,
            "horizon_days": 4,
            "intervention": {
                "kind": CONTACT_REDUCTION_LEVEL,
                "effective_minute": DAY_MINUTES,
                "magnitude": 0.0,
            },
        },
        "no_action": no_action,
        "contact_stop_action": contact_stop_action,
        "paired_checks": paired_checks,
    }
    result_sha256 = _component_hash(projection)
    if result_sha256 != _PREPARATION_RUNTIME_SMOKE_GOLDEN_SHA256:
        raise RuntimeError(
            "V19 Starsim golden smoke result drifted from its reviewed digest"
        )
    return {
        "schema_version": _PREPARATION_RUNTIME_SMOKE_SCHEMA,
        "fixed_public_scenario": (
            "v19_contact_transmission_with_matched_contact_stop"
        ),
        "result_sha256": result_sha256,
        "result": projection,
    }


def _runtime_contract() -> dict[str, Any]:
    try:
        import starsim  # type: ignore

        starsim_version = str(getattr(starsim, "__version__", "unknown"))
    except ImportError:
        raise RuntimeError(
            "Starsim is required before the 50-episode panel can be prepared"
        ) from None
    if starsim_version != REQUIRED_STARSIM_VERSION:
        raise RuntimeError(
            "V19 requires exact Starsim "
            f"{REQUIRED_STARSIM_VERSION}; observed {starsim_version!r}"
        )
    from .launchd_agent import _python_entrypoint_binding

    python_binding = _python_entrypoint_binding(Path(sys.executable))
    launch_path = Path(str(python_binding["launch_path"]))
    temporary_roots = {
        Path("/tmp"),
        Path("/private/tmp"),
        Path("/var/folders"),
        Path(gettempdir()).expanduser().resolve(),
    }
    if any(
        launch_path == temporary
        or temporary in launch_path.parents
        for temporary in temporary_roots
    ):
        raise RuntimeError("V19 Python executable must not be temporary")
    return {
        "python": sys.version.split()[0],
        "python_implementation": sys.implementation.name,
        "python_cache_tag": sys.implementation.cache_tag,
        "python_entrypoint_kind": (
            "symlink_chain"
            if python_binding["symlink_hops"]
            else "regular_file"
        ),
        "python_executable_sha256": python_binding["target"]["sha256"],
        "python_executable_binding_sha256": _component_hash(
            python_binding
        ),
        "python_executable_binding_policy": (
            "full_path_symlink_inode_and_content_binding_private_only"
        ),
        "starsim": starsim_version,
        "platform": platform.system(),
        "machine": platform.machine(),
        "scientific_distributions": {
            name: {
                **dict(_distribution_identity(name)),
                **_installed_distribution_content_identity(name),
            }
            for name in _RUNTIME_DISTRIBUTIONS
        },
        "scientific_module_origins": {
            name: _scientific_module_origin_identity(name)
            for name in _RUNTIME_DISTRIBUTIONS
        },
    }


def _preparation_runtime_identity(receipt: Mapping[str, Any]) -> str:
    return _component_hash(
        {
            "panel_id": receipt.get("panel_id"),
            "required_starsim_version": receipt.get(
                "required_starsim_version"
            ),
            "source_contract_sha256": receipt.get(
                "source_contract_sha256"
            ),
            "cli_contract_sha256": receipt.get("cli_contract_sha256"),
            "runtime_contract_sha256": receipt.get(
                "runtime_contract_sha256"
            ),
            "runtime_cache_contract_sha256": receipt.get(
                "runtime_cache_contract_sha256"
            ),
            "starsim_smoke_contract_sha256": receipt.get(
                "starsim_smoke_contract_sha256"
            ),
        }
    )


def preflight_preparation_runtime(
    *,
    root: Path,
    expected_benchmark_base_commit: str,
    runtime_cache_dir: Path,
) -> dict[str, Any]:
    """Attest every public preparation dependency before private V19 creation."""

    head_before = _git_output(root, "rev-parse", "HEAD")
    if (
        not isinstance(expected_benchmark_base_commit, str)
        or len(expected_benchmark_base_commit) != 40
        or any(
            character not in "0123456789abcdef"
            for character in expected_benchmark_base_commit
        )
        or not isinstance(head_before, str)
        or len(head_before) != 40
        or any(
            character not in "0123456789abcdef"
            for character in head_before
        )
        or not hmac.compare_digest(
            head_before, expected_benchmark_base_commit
        )
    ):
        raise RuntimeError(
            "V19 runtime preflight is not at the expected pinned commit"
        )
    if _git_output(root, "status", "--porcelain", "--untracked-files=all"):
        raise RuntimeError(
            "Commit and clean the matched-panel harness before runtime preflight"
        )
    source = _source_contract(root)
    cli = _cli_contract()
    cache_root = runtime_cache_dir.expanduser().absolute()
    if _paths_overlap(cache_root, root.resolve(strict=True)):
        raise RuntimeError(
            "V19 runtime cache must be outside the repository"
        )
    runtime = _runtime_contract()
    smoke = _preparation_runtime_smoke()
    runtime_cache = _runtime_cache_contract(runtime_cache_dir)
    head_after = _git_output(root, "rev-parse", "HEAD")
    if (
        not hmac.compare_digest(head_before, head_after)
        or _git_output(
            root, "status", "--porcelain", "--untracked-files=all"
        )
    ):
        raise RuntimeError(
            "V19 source changed during preparation runtime preflight"
        )
    receipt = {
        "schema_version": _PREPARATION_RUNTIME_PREFLIGHT_SCHEMA,
        "panel_id": PANEL_ID,
        "status": "passed",
        "benchmark_base_commit": head_before,
        "required_starsim_version": REQUIRED_STARSIM_VERSION,
        "source_contract_sha256": _component_hash(source),
        "cli_contract_sha256": _component_hash(cli),
        "runtime_contract_sha256": _component_hash(runtime),
        "runtime_cache_contract_sha256": _component_hash(runtime_cache),
        "starsim_smoke_contract_sha256": _component_hash(smoke),
        "runtime_contract": runtime,
        "starsim_smoke_contract": smoke,
        "provider_processes_started": 0,
        "authentication_processes_started": 0,
        "private_artifacts_required": False,
    }
    receipt["runtime_identity_sha256"] = _preparation_runtime_identity(
        receipt
    )
    return receipt


def _load_preparation_runtime_receipt(
    *, root: Path, receipt_path: Path
) -> tuple[dict[str, Any], str, str]:
    relative = _relative_to_root(receipt_path, root)
    if (
        _git_output(root, "ls-files", "--error-unmatch", relative)
        != relative
    ):
        raise RuntimeError(
            "V19 preparation runtime receipt must already be committed"
        )
    try:
        encoded, receipt = _read_owned_json(
            receipt_path,
            label="V19 preparation runtime receipt",
            owner_uid=os.getuid(),
            max_bytes=16 * 1024 * 1024,
        )
    except RuntimeError:
        raise RuntimeError(
            "V19 preparation runtime receipt is unavailable"
        ) from None
    expected_keys = {
        "authentication_processes_started",
        "benchmark_base_commit",
        "cli_contract_sha256",
        "panel_id",
        "private_artifacts_required",
        "provider_processes_started",
        "required_starsim_version",
        "runtime_cache_contract_sha256",
        "runtime_contract",
        "runtime_contract_sha256",
        "runtime_identity_sha256",
        "schema_version",
        "source_contract_sha256",
        "starsim_smoke_contract",
        "starsim_smoke_contract_sha256",
        "status",
    }
    if (
        set(receipt) != expected_keys
        or receipt.get("schema_version")
        != _PREPARATION_RUNTIME_PREFLIGHT_SCHEMA
        or receipt.get("panel_id") != PANEL_ID
        or receipt.get("status") != "passed"
        or receipt.get("required_starsim_version")
        != REQUIRED_STARSIM_VERSION
        or receipt.get("provider_processes_started") != 0
        or receipt.get("authentication_processes_started") != 0
        or receipt.get("private_artifacts_required") is not False
        or not isinstance(receipt.get("benchmark_base_commit"), str)
        or len(str(receipt["benchmark_base_commit"])) != 40
        or any(
            character not in "0123456789abcdef"
            for character in str(receipt["benchmark_base_commit"])
        )
        or any(
            not _is_sha256(receipt.get(name))
            for name in (
                "source_contract_sha256",
                "cli_contract_sha256",
                "runtime_contract_sha256",
                "runtime_cache_contract_sha256",
                "starsim_smoke_contract_sha256",
                "runtime_identity_sha256",
            )
        )
        or type(receipt.get("provider_processes_started")) is not int
        or type(receipt.get("authentication_processes_started")) is not int
        or receipt.get("runtime_contract_sha256")
        != _component_hash(receipt.get("runtime_contract"))
        or receipt.get("starsim_smoke_contract_sha256")
        != _component_hash(receipt.get("starsim_smoke_contract"))
        or receipt.get("runtime_identity_sha256")
        != _preparation_runtime_identity(receipt)
    ):
        raise RuntimeError(
            "V19 preparation runtime receipt failed closed-schema validation"
        )
    return receipt, _sha256(encoded), relative


def verify_preparation_runtime(
    *,
    root: Path,
    receipt_path: Path,
    expected_benchmark_base_commit: str,
    runtime_cache_dir: Path,
) -> dict[str, Any]:
    """Re-attest and compare the tracked pre-private V19 runtime receipt."""

    published, receipt_file_sha256, relative = (
        _load_preparation_runtime_receipt(
            root=root, receipt_path=receipt_path
        )
    )
    current = preflight_preparation_runtime(
        root=root,
        expected_benchmark_base_commit=expected_benchmark_base_commit,
        runtime_cache_dir=runtime_cache_dir,
    )
    current_runtime_cache = _runtime_cache_contract(runtime_cache_dir)
    if current.get("runtime_cache_contract_sha256") != _component_hash(
        current_runtime_cache
    ):
        raise RuntimeError(
            "V19 runtime cache changed during receipt verification"
        )
    if not hmac.compare_digest(
        str(published["runtime_identity_sha256"]),
        str(current["runtime_identity_sha256"]),
    ):
        raise RuntimeError(
            "V19 preparation runtime differs from the published receipt"
        )
    return {
        "schema_version": "epiagentbench.preparation_runtime_verification.v1",
        "panel_id": PANEL_ID,
        "status": "passed",
        "required_starsim_version": REQUIRED_STARSIM_VERSION,
        "published_receipt_path": relative,
        "published_receipt_file_sha256": receipt_file_sha256,
        "published_benchmark_base_commit": published[
            "benchmark_base_commit"
        ],
        "verified_benchmark_base_commit": current[
            "benchmark_base_commit"
        ],
        "runtime_identity_sha256": current["runtime_identity_sha256"],
        "source_contract_sha256": current["source_contract_sha256"],
        "cli_contract_sha256": current["cli_contract_sha256"],
        "runtime_contract_sha256": current["runtime_contract_sha256"],
        "runtime_cache_contract_sha256": current[
            "runtime_cache_contract_sha256"
        ],
        "starsim_smoke_contract_sha256": current[
            "starsim_smoke_contract_sha256"
        ],
        "runtime_contract": current["runtime_contract"],
        "runtime_cache_contract": current_runtime_cache,
        "starsim_smoke_contract": current["starsim_smoke_contract"],
        "provider_processes_started": 0,
        "authentication_processes_started": 0,
        "private_artifacts_required": False,
    }


def _validate_bound_preparation_runtime(
    public: Mapping[str, Any], *, rerun_smoke: bool
) -> dict[str, Any]:
    bound = public.get("preparation_runtime_contract")
    if (
        not isinstance(bound, dict)
        or set(bound)
        != {
            "cli_contract_sha256",
            "panel_id",
            "published_receipt_path",
            "published_receipt_file_sha256",
            "published_benchmark_base_commit",
            "required_starsim_version",
            "runtime_cache_contract_sha256",
            "runtime_contract_sha256",
            "runtime_identity_sha256",
            "schema_version",
            "source_contract_sha256",
            "starsim_smoke_contract",
            "starsim_smoke_contract_sha256",
            "verified_benchmark_base_commit",
        }
        or bound.get("schema_version")
        != _BOUND_PREPARATION_RUNTIME_SCHEMA
        or bound.get("panel_id") != PANEL_ID
        or bound.get("required_starsim_version")
        != REQUIRED_STARSIM_VERSION
        or any(
            not _is_sha256(bound.get(name))
            for name in (
                "published_receipt_file_sha256",
                "source_contract_sha256",
                "cli_contract_sha256",
                "runtime_contract_sha256",
                "runtime_cache_contract_sha256",
                "starsim_smoke_contract_sha256",
                "runtime_identity_sha256",
            )
        )
        or bound.get("published_receipt_path")
        != f"results/{PANEL_ID}.runtime.json"
        or any(
            not isinstance(bound.get(name), str)
            or len(str(bound[name])) != 40
            or any(
                character not in "0123456789abcdef"
                for character in str(bound[name])
            )
            for name in (
                "published_benchmark_base_commit",
                "verified_benchmark_base_commit",
            )
        )
        or bound.get("verified_benchmark_base_commit")
        != public.get("benchmark_base_commit")
        or bound.get("source_contract_sha256")
        != _component_hash(public.get("source_contract"))
        or bound.get("cli_contract_sha256")
        != _component_hash(public.get("cli_contract"))
        or bound.get("runtime_contract_sha256")
        != _component_hash(public.get("runtime_contract"))
        or bound.get("starsim_smoke_contract_sha256")
        != _component_hash(bound.get("starsim_smoke_contract"))
        or bound.get("runtime_identity_sha256")
        != _preparation_runtime_identity(bound)
    ):
        raise ValueError("Bound V19 preparation runtime is invalid")
    runtime_cache = _runtime_cache_contract(
        _runtime_cache_root_from_environment()
    )
    if bound.get("runtime_cache_contract_sha256") != _component_hash(
        runtime_cache
    ):
        raise ValueError("Bound V19 runtime cache changed")
    if rerun_smoke and _preparation_runtime_smoke() != bound.get(
        "starsim_smoke_contract"
    ):
        raise ValueError("Bound V19 Starsim smoke result changed")
    return bound


def _persistent_supervisor_contract() -> dict[str, Any]:
    """Return the public, path-free next-run process-ownership contract."""

    return {
        "schema_version": "epiagentbench.persistent_supervisor_contract.v8",
        "platform": "macos_user_launchagent",
        "sleep_inhibitor": "caffeinate_-dimsu",
        "job_policy": "finite_one_shot_no_unconditional_keepalive",
        "adapter_scope": "one_complete_evaluator_command",
        "provider_assignment_authority": (
            "authenticated_inner_evaluator_checkpoint_and_panel_lock"
        ),
        "automatic_outer_crash_recovery": False,
        "handled_terminal_receipt_exit": {
            "exit_code": 64,
            "child_gate": (
                "exact_authenticated_private_candidate_and_public_receipt"
            ),
            "supervisor_failure_code": (
                "runner_reserved_terminal_exit"
            ),
            "outer_worker_gate": (
                "independent_provider_free_terminal_receipt_reattestation"
            ),
            "unexpected_nonzero_policy": "terminal_ambiguity",
        },
        "provider_free_prelaunch_attestation": True,
        "provider_free_terminal_receipt_reconciliation": True,
        "model_invocation_accounting": {
            "readiness_phase": (
                "non_model_cli_readiness_before_chargeable_boundary"
            ),
            "chargeable_boundary": (
                "authenticated_model_invocation_marker_immediately_before_popen"
            ),
            "marker_failure_policy": "popen_not_attempted",
            "readiness_timeout_incident": (
                "provider_cli_readiness_timeout"
            ),
            "readiness_timeout_chargeable": False,
            "readiness_timeout_preflight_policy": "terminal_failure",
            "readiness_timeout_production_policy": (
                "fixed_denominator_transport_void_continue_same_worker"
            ),
            "spawn_after_marker_policy": (
                "conservatively_chargeable_even_if_spawn_outcome_ambiguous"
            ),
        },
        "stdout_stderr": "discarded",
        "cursor_key_source": "macos_keychain_in_memory_only",
        "private_config": "owner_only_hmac_authenticated_closed_schema",
        "status": "owner_only_hmac_authenticated_closed_schema",
        "frozen_privileged_sources": [
            "launchd_agent",
            "persistent_supervisor",
            "development_matched_panel",
        ],
        "python_entrypoint": (
            "content_digest_plus_private_symlink_inode_topology"
        ),
        "scientific_runtime_environment": (
            "manifest_bound_python_entrypoint_and_owner_only_cache_directories"
        ),
        "runtime_cache_environment_bootstrap": {
            "source": "hmac_authenticated_closed_launch_agent_config",
            "keys": sorted(_RUNTIME_CACHE_ENVIRONMENT_KEYS),
            "application": (
                "exact_overwrite_before_generate_control_worker_and_finalize_"
                "matched_panel_boundaries"
            ),
            "caller_ambient_values": "ignored",
            "restoration": "exact_prior_presence_and_value_in_finally",
            "plist_or_argv_disclosure": False,
        },
        "liveness": {
            "heartbeat_interval_seconds": 15,
            "provider_activity_is_liveness": False,
            "requires_boot_pid_and_process_birth_match": True,
        },
        "live_attestation": {
            "failure_codes": sorted(_PERSISTENT_ATTESTATION_FAILURE_CODES),
            "snapshot_attempts": (
                len(_SNAPSHOT_ATTESTATION_RETRY_DELAYS_SECONDS) + 1
            ),
            "snapshot_deadline_milliseconds": int(
                _SNAPSHOT_ATTESTATION_DEADLINE_SECONDS * 1000
            ),
            "snapshot_retry_delays_milliseconds": [
                int(delay * 1000)
                for delay in _SNAPSHOT_ATTESTATION_RETRY_DELAYS_SECONDS
            ],
            "retryable_reads": [
                "authenticated_worker_atomic_replacement",
                "authenticated_core_status_lease_torn_pair",
            ],
            "retry_boundaries": [
                "initial_binding",
                "before_model_invocation",
                "after_model_invocation",
                "final_completion",
            ],
            "provider_call_retry": "forbidden",
            "public_incident_projection": {
                "incident_codes": sorted(_PROVIDER_INCIDENT_CODES),
                "failure_stages": sorted(
                    _PREFLIGHT_FAILURE_STAGES
                    | _PRODUCTION_PUBLIC_FAILURE_STAGES
                ),
                "attestation_failure_code": "allowlisted_when_present",
                "provider_output": "forbidden",
                "benchmark_data": "forbidden",
            },
        },
        "execution_binding": [
            "launchd_label",
            "operation",
            "panel_id",
            "public_precommitment_sha256",
            "public_authentication_receipt_sha256",
            "python_executable_sha256",
            "sealed_config_file_sha256",
        ],
        "execution_binding_policy": "create_once_per_operation_never_replace",
        "operator_stop_policy": "never_stop_or_bootout_an_active_job",
        "release_gate": (
            "two_phase_private_candidate_then_authenticated_supervisor_"
            "completed_status_lease_and_event_chain_before_public_success"
        ),
        "manual_finalize_scope": "local_idempotent_publication_only_no_provider",
    }


def _attest_execution_contracts(
    *, root: Path, public: Mapping[str, Any]
) -> None:
    """Revalidate only the public execution surfaces around a provider call."""

    try:
        _validate_bound_preparation_runtime(public, rerun_smoke=False)
        fresh = {
            "source_contract": _source_contract(root),
            "cli_contract": _cli_contract(),
            "runtime_contract": _runtime_contract(),
            "replay_trace_contract": replay_trace_contract(),
            "persistent_supervisor_contract": _persistent_supervisor_contract(),
            "profiles": _profile_contract(),
        }
    except ProviderExecutionIsolationError:
        raise
    except Exception:
        raise ProviderStateIsolationError(
            "Unable to attest per-call execution contracts"
        ) from None
    hashes = public.get("contract_hashes")
    hash_names = {
        "source_contract": "source_sha256",
        "cli_contract": "cli_sha256",
        "runtime_contract": "runtime_sha256",
        "replay_trace_contract": "replay_sha256",
        "persistent_supervisor_contract": "supervisor_sha256",
        "profiles": "profiles_sha256",
    }
    for surface, current in fresh.items():
        if (
            not isinstance(hashes, dict)
            or public.get(surface) != current
            or hashes.get(hash_names[surface]) != _component_hash(current)
        ):
            raise ProviderStateIsolationError(
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
            "frozen_glean_auth_dependency_identity_sha256",
            "claude_cumulative_authorization_ceiling_usd",
            "unbounded_codex_cursor_provider_spend",
            "exact_acknowledgement_text",
        ],
    }


def _authentication_setup_contract(
    public_manifest_path: Path,
) -> dict[str, Any]:
    return {
        "schema_version": _AUTHENTICATION_SETUP_SCHEMA,
        "stage": "foreground_interactive_before_one_shot_preflight",
        "public_receipt_file": _authentication_receipt_path(
            public_manifest_path
        ).name,
        "providers": {
            "codex": {
                "method": "pinned_cli_device_auth",
                "interactive_streams": "operator_tty_never_captured",
            },
            "managed_glean": {
                "method": "pinned_managed_oauth_helper",
                "stdout": "discarded_never_captured",
                "stderr": "operator_tty_never_captured",
            },
        },
        "model_calls": 0,
        "authentication_dependency_identity": {
            "prepare_time_contract": (
                "fixed_root_owned_paths_and_dispatch_semantics"
            ),
            "exact_byte_identity_freeze": (
                "consistently_sampled_and_bound_with_manifest_bound_"
                "spend_authorization"
            ),
            "public_commitment": (
                "opaque_bundle_hash_in_authentication_receipt_before_preflight"
            ),
        },
        "retry_policy": (
            "only_after_verified_process_group_quiescence_and_"
            "unchanged_empty_target"
        ),
        "preflight_behavior": "attest_only_never_authenticate",
    }


def _private_state_storage_contract() -> dict[str, Any]:
    return {
        "schema_version": _PRIVATE_STATE_STORAGE_SCHEMA,
        "authoritative_copy_count": 1,
        "location": "outside_repository_and_os_temporary_storage",
        "parent": "pre_existing_current_user_0700_real_directory",
        "state_file": "current_user_single_link_0600_regular_file",
        "private_binding": (
            "canonical_private_path_and_parent_device_inode_hmac_"
            "authenticated_without_checkout_path"
        ),
        "checkout_separation": (
            "revalidated_against_current_repository_root_at_every_live_boundary"
        ),
        "write_validation": "before_and_after_every_authenticated_atomic_write",
        "read_validation": "metadata_during_open_then_binding_after_authentication",
        "public_paths_or_filesystem_identifiers": False,
        "rollback_fallback_copy": False,
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
    prior_ceiling = 80.0
    return {
        "claude_max_budget_usd_per_assignment": per_call_ceiling,
        "claude_max_budget_usd_per_call": per_call_ceiling,
        "claude_current_v19_authorization_ceiling_usd": current_ceiling,
        "claude_current_v19_authorization_breakdown": {
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
            "v8_usd": 15.0,
            "v9_usd": 20.0,
            "v10_usd": 0.0,
            "v11_usd": 0.0,
            "v12_usd": 0.0,
            "v13_usd": 0.0,
            "v14_usd": 10.0,
            "v15_usd": 0.0,
            "v16_usd": 5.0,
            "v17_usd": 0.0,
            "v18_usd": 5.0,
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
            "v8_preflight_receipt": (
                "results/development-matched-50x6-v8.preflight.json"
            ),
            "v8_stopped_watermark": (
                "results/development-matched-50x6-v8.json"
            ),
            "v8_supersession": (
                "results/development-matched-50x6-v8.superseded.json"
            ),
            "v9_preflight_receipt": (
                "results/development-matched-50x6-v9.preflight.json"
            ),
            "v9_stopped_watermark": (
                "results/development-matched-50x6-v9.json"
            ),
            "v10_manifest": (
                "results/development-matched-50x6-v10.manifest.json"
            ),
            "v10_supersession": (
                "results/development-matched-50x6-v10.superseded.json"
            ),
            "v11_manifest": (
                "results/development-matched-50x6-v11.manifest.json"
            ),
            "v11_supersession": (
                "results/development-matched-50x6-v11.superseded.json"
            ),
            "v12_supersession": (
                "results/development-matched-50x6-v12.superseded.json"
            ),
            "v13_manifest": (
                "results/development-matched-50x6-v13.manifest.json"
            ),
            "v13_supersession": (
                "results/development-matched-50x6-v13.superseded.json"
            ),
            "v14_manifest": (
                "results/development-matched-50x6-v14.manifest.json"
            ),
            "v14_authentication_receipt": (
                "results/development-matched-50x6-v14.authentication.json"
            ),
            "v14_preflight_artifact": (
                "results/development-matched-50x6-v14.preflight.json"
            ),
            "v14_supersession": (
                "results/development-matched-50x6-v14.superseded.json"
            ),
            "v15_supersession": (
                "results/development-matched-50x6-v15.superseded.json"
            ),
            "v16_manifest": (
                "results/development-matched-50x6-v16.manifest.json"
            ),
            "v16_authentication_receipt": (
                "results/development-matched-50x6-v16.authentication.json"
            ),
            "v16_preflight_artifact": (
                "results/development-matched-50x6-v16.preflight.json"
            ),
            "v16_supersession": (
                "results/development-matched-50x6-v16.superseded.json"
            ),
            "v17_runtime_receipt": (
                "results/development-matched-50x6-v17.runtime.json"
            ),
            "v17_manifest": (
                "results/development-matched-50x6-v17.manifest.json"
            ),
            "v17_authentication_receipt": (
                "results/development-matched-50x6-v17.authentication.json"
            ),
            "v17_supersession": (
                "results/development-matched-50x6-v17.superseded.json"
            ),
            "v18_runtime_receipt": (
                "results/development-matched-50x6-v18.runtime.json"
            ),
            "v18_manifest": (
                "results/development-matched-50x6-v18.manifest.json"
            ),
            "v18_authentication_receipt": (
                "results/development-matched-50x6-v18.authentication.json"
            ),
            "v18_preflight_artifact": (
                "results/development-matched-50x6-v18.preflight.json"
            ),
            "v18_supersession": (
                "results/development-matched-50x6-v18.superseded.json"
            ),
        },
        "ceiling_interpretation": (
            "authorization ceilings, not measured provider billing"
        ),
        "other_provider_spend_cap": None,
        "other_provider_spend": "unbounded",
        "explicit_unbounded_provider_spend_acknowledgement_required": True,
    }


def freeze_panel_cohort(
    *,
    root: Path,
    preparation_runtime_receipt_path: Path,
    expected_benchmark_base_commit: str,
    runtime_cache_dir: Path,
    authentication_key_file: Path,
    output_directory: Path,
    freeze_claim_path: Path | None = None,
) -> dict[str, Any]:
    """Claim and freeze V19 exactly once after runtime re-attestation."""

    verification = verify_preparation_runtime(
        root=root,
        receipt_path=preparation_runtime_receipt_path,
        expected_benchmark_base_commit=expected_benchmark_base_commit,
        runtime_cache_dir=runtime_cache_dir,
    )
    key_path = _existing_path_without_final_symlink(
        authentication_key_file
    )
    authentication_key = _read_authentication_key(key_path)
    claim_path = _cohort_freeze_claim_path(key_path, freeze_claim_path)
    completion_path = _cohort_freeze_completion_path(claim_path)
    destination = _canonical_cohort_destination(output_directory)
    _assert_distinct_paths(
        preparation_runtime_receipt_path,
        runtime_cache_dir,
        key_path,
        claim_path,
        completion_path,
        destination,
    )
    cache_root = runtime_cache_dir.expanduser().resolve(strict=False)
    for label, candidate in (
        ("authentication key", key_path),
        ("cohort freeze claim", claim_path),
        ("cohort freeze completion", completion_path),
        ("cohort output", destination),
    ):
        if _paths_overlap(
            cache_root, candidate.expanduser().resolve(strict=False)
        ):
            raise ValueError(
                f"V19 runtime cache must not overlap the {label}"
            )
    claim = _create_pending_cohort_freeze_claim(
        claim_path=claim_path,
        runtime_verification=verification,
        expected_benchmark_base_commit=expected_benchmark_base_commit,
        canonical_cohort_destination=destination,
        authentication_key=authentication_key,
    )
    frozen = freeze_private_starsim_cohort(
        cohort_id=COHORT_ID,
        output_directory=destination,
        authentication_key_file=key_path,
        episodes=EPISODE_COUNT,
        backend=BACKEND,
    )
    if (
        frozen.public_descriptor.get("cohort_id") != COHORT_ID
        or frozen.public_descriptor.get("episode_count") != EPISODE_COUNT
        or frozen.public_descriptor.get("backend") != BACKEND
    ):
        raise RuntimeError("Frozen V19 cohort returned an invalid public receipt")
    if (
        frozen.cohort_directory != destination
        or frozen.manifest_path != destination / "cohort.manifest"
    ):
        raise RuntimeError(
            "Frozen V19 cohort returned a noncanonical artifact location"
        )
    manifest = PrivateEpisodeCohortManifest.read(
        frozen.manifest_path, authentication_key
    )
    completion = _complete_cohort_freeze_claim(
        claim_path=claim_path,
        claim=claim,
        manifest_path=frozen.manifest_path,
        manifest=manifest,
        authentication_key=authentication_key,
    )
    if completion["pack_set_commitment"] != manifest.pack_set_commitment:
        raise RuntimeError("V19 cohort freeze completion commitment mismatch")
    return {
        "schema_version": "epiagentbench.v19_cohort_freeze.v2",
        "panel_id": PANEL_ID,
        "status": "frozen_claim_completed",
        "backend": BACKEND,
        "episode_count": EPISODE_COUNT,
        "runtime_identity_sha256": verification[
            "runtime_identity_sha256"
        ],
        "create_once_claim_status": "completed",
        "provider_processes_started": 0,
        "authentication_processes_started": 0,
        "model_calls_started": 0,
    }


def _prepare_panel_locked(
    *,
    root: Path,
    cohort_manifest_path: Path,
    preparation_runtime_receipt_path: Path,
    expected_benchmark_base_commit: str,
    runtime_cache_dir: Path,
    authentication_key_file: Path,
    claude_secure_storage_dir: Path,
    codex_secure_storage_dir: Path,
    private_state_path: Path,
    public_manifest_path: Path,
    timeout_seconds: int = 1800,
    claude_max_budget_usd: float = 5.0,
    freeze_claim_path: Path | None = None,
) -> dict[str, Any]:
    """Prepare while the host-global panel lease is held."""

    _validate_schedule_design()
    authentication_receipt_path = _authentication_receipt_path(
        public_manifest_path
    )
    if _git_output(root, "status", "--porcelain", "--untracked-files=all"):
        raise RuntimeError("Commit and clean the matched-panel harness before prepare")
    _assert_distinct_paths(
        cohort_manifest_path,
        preparation_runtime_receipt_path,
        runtime_cache_dir,
        authentication_key_file,
        private_state_path,
        public_manifest_path,
        authentication_receipt_path,
    )
    _relative_to_root(public_manifest_path, root)
    if (
        private_state_path.exists()
        or private_state_path.is_symlink()
        or public_manifest_path.exists()
        or public_manifest_path.is_symlink()
        or authentication_receipt_path.exists()
        or authentication_receipt_path.is_symlink()
    ):
        raise FileExistsError("Refusing to replace a matched-panel artifact")
    if type(timeout_seconds) is not int or timeout_seconds != 1800:
        raise ValueError("V19 requires an exact 1800-second assignment timeout")
    if (
        isinstance(claude_max_budget_usd, bool)
        or not isinstance(claude_max_budget_usd, (int, float))
        or float(claude_max_budget_usd) != 5.0
    ):
        raise ValueError("V19 requires an exact $5 Claude per-call ceiling")

    # Re-run the same public, provider-free preparation preflight before
    # touching the cohort, authentication key, or any private artifact.  This
    # makes a missing/drifted scientific runtime fail before the create-once
    # preparation boundary, even if an operator skipped the runbook command.
    runtime_verification = verify_preparation_runtime(
        root=root,
        receipt_path=preparation_runtime_receipt_path,
        expected_benchmark_base_commit=expected_benchmark_base_commit,
        runtime_cache_dir=runtime_cache_dir,
    )
    cache_root = runtime_cache_dir.expanduser().resolve(strict=False)
    for label, candidate in (
        ("frozen cohort", cohort_manifest_path.parent),
        ("authentication key", authentication_key_file),
        ("Claude credential namespace", claude_secure_storage_dir),
        ("Codex credential namespace", codex_secure_storage_dir),
        ("private state", private_state_path),
        ("public manifest", public_manifest_path),
    ):
        if _paths_overlap(
            cache_root, candidate.expanduser().resolve(strict=False)
        ):
            raise ValueError(
                f"V19 runtime cache must not overlap the {label}"
            )
    profiles = _profile_contract()
    source = _source_contract(root)
    cli = _cli_contract()
    if (
        _component_hash(source)
        != runtime_verification["source_contract_sha256"]
        or _component_hash(cli)
        != runtime_verification["cli_contract_sha256"]
    ):
        raise RuntimeError(
            "V19 source or CLI identity drifted after runtime verification"
        )

    private_state_storage = _private_state_storage_binding(
        private_state_path,
        root=root,
        create_temporary_test_parent=True,
    )

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
    resolved_freeze_claim_path = _cohort_freeze_claim_path(
        key_path, freeze_claim_path
    )
    _assert_distinct_paths(
        cohort_manifest_path,
        preparation_runtime_receipt_path,
        runtime_cache_dir,
        key_path,
        resolved_freeze_claim_path,
        _cohort_freeze_completion_path(resolved_freeze_claim_path),
        private_state_path,
        public_manifest_path,
        authentication_receipt_path,
    )
    for label, candidate in (
        ("cohort freeze claim", resolved_freeze_claim_path),
        (
            "cohort freeze completion",
            _cohort_freeze_completion_path(resolved_freeze_claim_path),
        ),
    ):
        if _paths_overlap(
            cache_root, candidate.expanduser().resolve(strict=False)
        ):
            raise ValueError(
                f"V19 runtime cache must not overlap the {label}"
            )
    manifest_path = _existing_path_without_final_symlink(cohort_manifest_path)
    freeze_claim, freeze_completion = (
        _require_completed_cohort_freeze_claim(
            claim_path=resolved_freeze_claim_path,
            manifest_path=manifest_path,
            runtime_receipt_file_sha256=runtime_verification[
                "published_receipt_file_sha256"
            ],
            runtime_identity_sha256=runtime_verification[
                "runtime_identity_sha256"
            ],
            expected_benchmark_base_commit=(
                expected_benchmark_base_commit
            ),
            authentication_key=key,
        )
    )
    if _cohort_retirement_if_present(manifest_path, key) is not None:
        raise ValueError("Frozen cohort is retired and cannot be prepared again")
    preparation_claim_path = _cohort_preparation_path(manifest_path)
    if preparation_claim_path.exists() or preparation_claim_path.is_symlink():
        raise FileExistsError(
            "Frozen cohort already has a preparation claim; never retry it"
        )
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
    runtime = dict(runtime_verification["runtime_contract"])
    preparation_runtime = {
        "schema_version": _BOUND_PREPARATION_RUNTIME_SCHEMA,
        "panel_id": PANEL_ID,
        "required_starsim_version": runtime_verification[
            "required_starsim_version"
        ],
        "published_receipt_path": runtime_verification[
            "published_receipt_path"
        ],
        "published_receipt_file_sha256": runtime_verification[
            "published_receipt_file_sha256"
        ],
        "published_benchmark_base_commit": runtime_verification[
            "published_benchmark_base_commit"
        ],
        "verified_benchmark_base_commit": runtime_verification[
            "verified_benchmark_base_commit"
        ],
        "runtime_identity_sha256": runtime_verification[
            "runtime_identity_sha256"
        ],
        "source_contract_sha256": runtime_verification[
            "source_contract_sha256"
        ],
        "cli_contract_sha256": runtime_verification[
            "cli_contract_sha256"
        ],
        "runtime_contract_sha256": runtime_verification[
            "runtime_contract_sha256"
        ],
        "runtime_cache_contract_sha256": runtime_verification[
            "runtime_cache_contract_sha256"
        ],
        "starsim_smoke_contract_sha256": runtime_verification[
            "starsim_smoke_contract_sha256"
        ],
        "starsim_smoke_contract": runtime_verification[
            "starsim_smoke_contract"
        ],
    }
    replay = replay_trace_contract()
    supervisor = _persistent_supervisor_contract()
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
        "preparation_runtime_contract": preparation_runtime,
        "replay_trace_contract": replay,
        "persistent_supervisor_contract": supervisor,
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
            "preparation_runtime_sha256": _component_hash(
                preparation_runtime
            ),
            "replay_sha256": _component_hash(replay),
            "supervisor_sha256": _component_hash(supervisor),
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
            "persistent_execution": {
                "required_for_preflight_and_production": True,
                "contract": "persistent_supervisor_contract",
                "outer_command_scope": "one_complete_evaluator_command",
                "provider_assignment_checkpoint_owner": "inner_evaluator",
                "monitor_may_relaunch": False,
                "active_job_may_be_booted_out": False,
            },
            "spend_authorization": _spend_authorization_contract(),
            "authentication_setup": _authentication_setup_contract(
                public_manifest_path
            ),
            "private_state_storage": _private_state_storage_contract(),
            "retry_policy": "at most one provider invocation per assignment",
            "orphan_policy": (
                "seal started assignment as transport_void; never retry; "
                "block cohort completion and every later provider call"
            ),
            "transport_void_policy": (
                "ordinary cleanly quiesced void ends only that provider "
                "assignment and the same still-running supervised evaluator "
                "continues with the next assignment without a second outer "
                "launch; crash-orphan, provider process or state isolation, "
                "episode-service cleanup, and Codex authentication incidents "
                "are terminal and non-resumable"
            ),
            "terminal_incident_policy": {
                "crash_after_durable_attempt_before_model_invocation": {
                    "all_profiles": ["execution_incident"],
                },
                "crash_after_model_invocation_start": {
                    "non_codex": ["execution_incident"],
                    "codex": ["execution_incident", "codex_auth_incident"],
                },
                "provider_process_or_output_pipe_isolation_failure": {
                    "non_codex": ["execution_incident"],
                    "codex_before_model_invocation": [
                        "execution_incident",
                    ],
                    "codex_after_model_invocation_start": [
                        "execution_incident",
                        "codex_auth_incident",
                    ],
                },
                "provider_state_persistence_guard_failure": {
                    "non_codex": ["execution_incident"],
                    "codex_before_model_invocation": [
                        "execution_incident",
                    ],
                    "codex_after_model_invocation_start": [
                        "execution_incident",
                        "codex_auth_incident",
                    ],
                    "post_quiescence_result_checkpoint": [
                        "execution_incident",
                    ],
                    "post_quiescence_codex_authentication_state": (
                        "not ambiguous after successful provider-process, "
                        "supervisor-boundary, and credential attestations"
                    ),
                },
                "episode_service_cleanup_failure": {
                    "non_codex": ["execution_incident"],
                    "codex_before_model_invocation": [
                        "execution_incident",
                    ],
                    "codex_after_model_invocation_start": [
                        "execution_incident",
                        "codex_auth_incident",
                    ],
                },
                "codex_timeout_or_post_launch_credential_link_drift": [
                    "codex_auth_incident"
                ],
                "codex_authentication_boundary": (
                    "record only after durable model_invocation start or an "
                    "explicit Codex credential-state incident"
                ),
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
            "transport_void_public_schema": {
                "reason": "finite_provider_incident_code",
                "allowed_reasons": sorted(_PROVIDER_INCIDENT_CODES),
                "timeout_stage": [
                    None,
                    "provider_cli_readiness",
                    "model_invocation",
                ],
                "failure_stage": [
                    None,
                    "provider_cli_readiness",
                    "model_invocation",
                ],
            },
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
            "authentication_prerequisite": (
                "committed_sanitized_receipt_before_supervisor_creation"
            ),
            "per_provider_call_execution_attestation": {
                "surfaces": [
                    "source_contract",
                    "cli_contract",
                    "runtime_contract",
                    "preparation_runtime_contract",
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
        "private_state_storage": private_state_storage,
        "public_precommitment_sha256": public["precommitment_sha256"],
        "cohort_manifest_path": str(manifest_path.resolve()),
        "cohort_freeze_claim_path": str(
            resolved_freeze_claim_path.resolve(strict=False)
        ),
        "cohort_freeze_claim": freeze_claim,
        "cohort_freeze_completion": freeze_completion,
        "claude_secure_storage_dir": str(resolved_claude_secure_storage_dir),
        "claude_secure_storage_identity": claude_secure_storage_identity,
        "claude_auth_commitment_key_hex": claude_auth_commitment_key.hex(),
        "codex_secure_storage_dir": str(resolved_codex_secure_storage_dir),
        "codex_secure_storage_identity": codex_secure_storage_identity,
        "codex_auth_commitment_key_hex": codex_auth_commitment_key.hex(),
        "episodes": episodes,
        "schedule_nonce_hex": nonce.hex(),
        "schedule": schedule,
        "authentication_dependency_freeze": {
            "schema_version": _AUTHENTICATION_DEPENDENCY_FREEZE_SCHEMA,
            "status": "required",
        },
        "authentication_setup": {
            "schema_version": _AUTHENTICATION_SETUP_SCHEMA,
            "status": "required",
            "required_contract_hashes": {
                name: public["contract_hashes"][name]
                for name in (
                    "source_sha256",
                    "cli_sha256",
                    "claude_auth_sha256",
                    "codex_auth_sha256",
                    "budgets_sha256",
                    "runtime_sha256",
                    "preparation_runtime_sha256",
                    "supervisor_sha256",
                )
            },
            "codex": {"status": "required", "attempts": []},
            "managed_glean": {"status": "required", "attempts": []},
            "model_calls_started": 0,
        },
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
                "preparation_runtime_sha256": public["contract_hashes"][
                    "preparation_runtime_sha256"
                ],
                "replay_sha256": public["contract_hashes"]["replay_sha256"],
                "supervisor_sha256": public["contract_hashes"][
                    "supervisor_sha256"
                ],
            },
        },
        "preparation_runtime_private_contract": {
            "runtime_cache_contract": runtime_verification[
                "runtime_cache_contract"
            ],
        },
        "assignments": [],
    }
    claim = _claim_cohort_preparation(
        cohort_manifest_path=manifest_path,
        manifest=manifest,
        public_manifest=public,
        private_state_path=private_state_path,
        public_manifest_path=public_manifest_path,
        authentication_key=key,
    )
    _assert_cohort_preparation_matches_panel(
        claim,
        manifest=manifest,
        public_manifest=public,
        private_state_path=private_state_path,
        public_manifest_path=public_manifest_path,
    )
    private["cohort_preparation_claim"] = claim
    _create_private_state_once(private_state_path, private, key)
    if _load_private_state(private_state_path, key) != private:
        raise RuntimeError(
            "Authenticated private matched-panel state failed its post-write reload"
        )
    _create_public_json_once(public_manifest_path, public)
    if _load_json(public_manifest_path) != public:
        raise RuntimeError(
            "Public matched-panel precommitment failed its post-write reload"
        )
    return public


def prepare_panel(
    *,
    root: Path,
    cohort_manifest_path: Path,
    preparation_runtime_receipt_path: Path,
    expected_benchmark_base_commit: str,
    runtime_cache_dir: Path,
    authentication_key_file: Path,
    claude_secure_storage_dir: Path,
    codex_secure_storage_dir: Path,
    private_state_path: Path,
    public_manifest_path: Path,
    timeout_seconds: int = 1800,
    claude_max_budget_usd: float = 5.0,
    freeze_claim_path: Path | None = None,
) -> dict[str, Any]:
    """Bind one fresh cohort and publish one create-once precommitment pair."""

    with _exclusive_run_lock(private_state_path):
        return _prepare_panel_locked(
            root=root,
            cohort_manifest_path=cohort_manifest_path,
            preparation_runtime_receipt_path=(
                preparation_runtime_receipt_path
            ),
            expected_benchmark_base_commit=(
                expected_benchmark_base_commit
            ),
            runtime_cache_dir=runtime_cache_dir,
            authentication_key_file=authentication_key_file,
            claude_secure_storage_dir=claude_secure_storage_dir,
            codex_secure_storage_dir=codex_secure_storage_dir,
            private_state_path=private_state_path,
            public_manifest_path=public_manifest_path,
            timeout_seconds=timeout_seconds,
            claude_max_budget_usd=claude_max_budget_usd,
            freeze_claim_path=freeze_claim_path,
        )


def _validate_public_hash(public: Mapping[str, Any]) -> None:
    unsigned = dict(public)
    supplied = unsigned.pop("precommitment_sha256", None)
    if supplied != _component_hash(unsigned):
        raise ValueError("Public matched-panel precommitment is invalid")


def _assert_private_public_panel_binding(
    private: Mapping[str, Any],
    public: Mapping[str, Any],
) -> None:
    """Bind a minimal authenticated private state to one public panel."""

    if (
        private.get("schema_version") != SCHEMA_VERSION
        or private.get("panel_id") != PANEL_ID
        or public.get("schema_version") != SCHEMA_VERSION
        or public.get("panel_id") != PANEL_ID
        or public.get("status") != "precommitted"
        or not isinstance(public.get("precommitment_sha256"), str)
        or private.get("public_precommitment_sha256")
        != public.get("precommitment_sha256")
    ):
        raise RuntimeError(
            "Authenticated private state is not bound to the public panel"
        )


def _validate_contracts(
    *,
    root: Path,
    private: Mapping[str, Any],
    public: Mapping[str, Any],
    authentication_key: bytes,
    claude_secure_storage_dir: Path,
    codex_secure_storage_dir: Path,
    revalidate_live_identity_contracts: bool = True,
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
        or public["run_contract"].get("authentication_setup")
        != _authentication_setup_contract(
            Path(f"{PANEL_ID}.manifest.json")
        )
        or public["run_contract"].get("private_state_storage")
        != _private_state_storage_contract()
        or private.get("panel_id") != PANEL_ID
        or private.get("public_precommitment_sha256")
        != public.get("precommitment_sha256")
    ):
        raise ValueError("Matched-panel manifest contract mismatch")
    _authentication_dependency_freeze(
        private,
        public,
        require_frozen=private.get("spend_authorization") is not None,
    )
    _validate_authentication_setup_state(private, public)
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
    bound_preparation_runtime = _validate_bound_preparation_runtime(
        public, rerun_smoke=revalidate_live_identity_contracts
    )
    private_preparation_runtime = private.get(
        "preparation_runtime_private_contract"
    )
    if (
        not isinstance(private_preparation_runtime, dict)
        or set(private_preparation_runtime)
        != {"runtime_cache_contract"}
        or _component_hash(
            private_preparation_runtime.get("runtime_cache_contract")
        )
        != bound_preparation_runtime.get(
            "runtime_cache_contract_sha256"
        )
    ):
        raise ValueError(
            "Private V19 preparation runtime binding is invalid"
        )
    expected_contracts = {
        "runtime_contract": _runtime_contract(),
        "replay_trace_contract": replay_trace_contract(),
        "persistent_supervisor_contract": _persistent_supervisor_contract(),
        "profiles": _profile_contract(),
    }
    if revalidate_live_identity_contracts:
        # Live prepare/preflight/production boundaries must prove that the
        # checked-out source and installed provider executables still match
        # the frozen manifest.  The post-supervisor release path deliberately
        # skips these executable probes: its authenticated pending candidate
        # was created only after the live child performed these checks, and
        # finalization must not launch anything after outer completion.
        expected_contracts.update(
            {
                "source_contract": _source_contract(root),
                "cli_contract": _cli_contract(),
            }
        )
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
            (
                "preparation_runtime_sha256",
                public["preparation_runtime_contract"],
            ),
            ("replay_sha256", public["replay_trace_contract"]),
            (
                "supervisor_sha256",
                public["persistent_supervisor_contract"],
            ),
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
    preparation_runtime_contract = public.get(
        "preparation_runtime_contract"
    )
    if not isinstance(preparation_runtime_contract, Mapping):
        raise ValueError("V19 preparation runtime contract is missing")
    freeze_claim_path = Path(str(private.get("cohort_freeze_claim_path")))
    freeze_claim, freeze_completion = (
        _require_completed_cohort_freeze_claim(
            claim_path=freeze_claim_path,
            manifest_path=manifest_path,
            runtime_receipt_file_sha256=str(
                preparation_runtime_contract.get(
                    "published_receipt_file_sha256"
                )
            ),
            runtime_identity_sha256=str(
                preparation_runtime_contract.get(
                    "runtime_identity_sha256"
                )
            ),
            expected_benchmark_base_commit=str(
                preparation_runtime_contract.get(
                    "verified_benchmark_base_commit"
                )
            ),
            authentication_key=authentication_key,
        )
    )
    if (
        private.get("cohort_freeze_claim") != freeze_claim
        or private.get("cohort_freeze_completion") != freeze_completion
    ):
        raise ValueError(
            "Authenticated V19 cohort freeze claim differs from private state"
        )
    manifest = PrivateEpisodeCohortManifest.read(manifest_path, authentication_key)
    preparation_claim = _load_cohort_preparation_marker(
        _cohort_preparation_path(manifest_path), authentication_key
    )
    if (
        private.get("cohort_preparation_claim") != preparation_claim
        or preparation_claim.get("cohort_id") != manifest.cohort_id
        or preparation_claim.get("panel_id") != PANEL_ID
        or preparation_claim.get("pack_set_commitment")
        != manifest.pack_set_commitment
        or preparation_claim.get("public_precommitment_sha256")
        != public.get("precommitment_sha256")
    ):
        raise ValueError("Cohort preparation claim differs from this panel")
    retirement = _cohort_retirement_if_present(
        manifest_path, authentication_key
    )
    if retirement is not None:
        if private.get("status") not in {
            "complete",
            _PENDING_PRODUCTION_STATUS,
        }:
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
        try:
            model_invocation_state = _durable_model_invocation_state(
                assignment
            )
        except RuntimeError as error:
            raise ValueError(
                "Private assignment model-invocation marker is invalid"
            ) from error
        if (
            assignment.get("status") == "complete"
            and model_invocation_state != "finished"
        ):
            raise ValueError(
                "Completed assignment lacks a finished model invocation"
            )
        projected_state = assignment.get("model_invocation_state")
        projected_chargeable = assignment.get("conservative_chargeable")
        if (
            projected_state is not None
            and projected_state != model_invocation_state
        ) or (
            projected_chargeable is not None
            and projected_chargeable
            is not (model_invocation_state != "not_started")
        ):
            raise ValueError(
                "Private assignment model-invocation projection is invalid"
            )
        if assignment.get("status") == "transport_void":
            void_reason = assignment.get("void_reason")
            timeout_stage = assignment.get("timeout_stage")
            failure_stage = assignment.get("failure_stage")
            if (
                void_reason not in _PROVIDER_INCIDENT_CODES
                or timeout_stage
                not in {None, "provider_cli_readiness", "model_invocation"}
                or failure_stage
                not in {None, "provider_cli_readiness", "model_invocation"}
            ):
                raise ValueError(
                    "Private transport-void projection is invalid"
                )
            if (
                void_reason == "provider_cli_readiness_timeout"
                or timeout_stage == "provider_cli_readiness"
                or failure_stage == "provider_cli_readiness"
            ) and (
                void_reason != "provider_cli_readiness_timeout"
                or timeout_stage != "provider_cli_readiness"
                or failure_stage != "provider_cli_readiness"
                or model_invocation_state != "not_started"
                or assignment.get("timed_out") is not True
                or projected_chargeable is not False
            ):
                raise ValueError(
                    "Private readiness-timeout projection is invalid"
                )
    if private.get("status") in {"complete", _PENDING_PRODUCTION_STATUS} and (
        len(assignments) != ASSIGNMENT_COUNT
        or any(item.get("status") not in {"complete", "transport_void"} for item in assignments)
    ):
        raise ValueError("Completed private state is not fully terminal")
    bindings = private.get(_PERSISTENT_EXECUTION_BINDINGS_KEY)
    if bindings is not None:
        if not isinstance(bindings, dict) or any(
            operation not in {"preflight", "production"}
            or not isinstance(binding, dict)
            or set(binding) != _SUPERVISOR_BINDING_FIELDS
            or binding.get("operation") != operation
            or binding.get("panel_id") != PANEL_ID
            or binding.get("precommitment_sha256")
            != public.get("precommitment_sha256")
            for operation, binding in bindings.items()
        ):
            raise ValueError("Private persistent-supervisor binding is invalid")
    for incident_name in ("execution_incident", "codex_auth_incident"):
        incident = private.get(incident_name)
        if incident is None:
            continue
        attestation_failure_code = (
            incident.get("attestation_failure_code")
            if isinstance(incident, dict)
            else None
        )
        incident_code = (
            incident.get("incident_code")
            if isinstance(incident, dict)
            else None
        )
        ordinary_void = (
            isinstance(incident, dict)
            and type(incident.get("assignment_index")) is int
            and 0 <= incident["assignment_index"] < len(assignments)
            and assignments[incident["assignment_index"]].get("status")
            == "transport_void"
            and "boundary" not in incident
        )
        supervisor_boundary = (
            incident_name == "execution_incident"
            and isinstance(incident, dict)
            and type(incident.get("assignment_index")) is int
            and incident["assignment_index"] == len(assignments)
            and incident.get("boundary")
            in {"clean_before_assignment", "final_completion"}
            and (
                incident.get("boundary") == "final_completion"
                or isinstance(incident.get("profile_id"), str)
            )
        )
        if (
            not isinstance(incident, dict)
            or incident.get("status") != "terminal"
            or not isinstance(incident.get("failure_class"), str)
            or not incident["failure_class"]
            or (
                incident_name == "execution_incident"
                and incident_code not in _PROVIDER_INCIDENT_CODES
            )
            or (
                attestation_failure_code is not None
                and attestation_failure_code
                not in _PERSISTENT_ATTESTATION_FAILURE_CODES
            )
            or (
                incident_name == "codex_auth_incident"
                and not _codex_auth_incident_is_valid(
                    incident, assignments
                )
            )
            or not (ordinary_void or supervisor_boundary)
        ):
            raise ValueError("Private terminal incident state is invalid")
    if private.get("status") in {"complete", _PENDING_PRODUCTION_STATUS} and any(
        private.get(name) is not None
        for name in ("execution_incident", "codex_auth_incident")
    ):
        raise ValueError("Completed private state contains a terminal incident")
    return manifest, packs, schedule


def _expected_spend_authorization(
    public: Mapping[str, Any],
    *,
    frozen_glean_auth_dependency_identity_sha256: str,
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
        or not _is_sha256(frozen_glean_auth_dependency_identity_sha256)
        or not isinstance(public.get("run_contract"), Mapping)
        or public["run_contract"].get("spend_authorization")
        != _spend_authorization_contract()
    ):
        raise ValueError("V19 spend authorization contract mismatch")
    unsigned = {
        "schema_version": _SPEND_AUTHORIZATION_SCHEMA,
        "status": "authorized",
        "panel_id": PANEL_ID,
        "final_public_precommitment_sha256": precommitment,
        "budget_contract_sha256": str(hashes["budgets_sha256"]),
        "frozen_glean_auth_dependency_identity_sha256": (
            frozen_glean_auth_dependency_identity_sha256
        ),
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
    supplied = private.get("spend_authorization")
    if not isinstance(supplied, Mapping):
        raise RuntimeError(
            "A manifest-bound exact v19 spend authorization receipt is required "
            "before any authentication bootstrap or model-bearing provider call"
        )
    try:
        freeze = _authentication_dependency_freeze(
            private, public, require_frozen=True
        )
        expected = _expected_spend_authorization(
            public,
            frozen_glean_auth_dependency_identity_sha256=str(
                freeze["identity_sha256"]
            ),
        )
    except (RuntimeError, ValueError):
        raise RuntimeError(
            "A manifest-bound exact v19 spend authorization receipt is required "
            "before any authentication bootstrap or model-bearing provider call"
        ) from None
    if not hmac.compare_digest(
        _canonical_bytes(dict(supplied)), _canonical_bytes(expected)
    ):
        raise RuntimeError(
            "A manifest-bound exact v19 spend authorization receipt is required "
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
            "The exact v19 $590 cumulative spend acknowledgement text is required"
        )
    assert_durable_live_execution_paths(
        root=root,
        private_state_path=private_state_path,
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
        authentication_setup = _validate_authentication_setup_state(
            private, public
        )
        if (
            private.get("status") != "prepared"
            or private.get("assignments") != []
            or not isinstance(preflight, Mapping)
            or preflight.get("status") != "required"
            or authentication_setup.get("status") != "required"
            or any(
                authentication_setup[name].get("status") != "required"
                or authentication_setup[name].get("attempts") != []
                for name in ("codex", "managed_glean")
            )
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
        existing = private.get("spend_authorization")
        if existing is not None:
            expected = _assert_spend_authorization(private, public)
            _attest_frozen_glean_auth_dependencies(private, public)
            return expected
        if private.get("authentication_dependency_freeze") != {
            "schema_version": _AUTHENTICATION_DEPENDENCY_FREEZE_SCHEMA,
            "status": "required",
        }:
            raise RuntimeError(
                "Authentication dependency identity was already consumed"
            )
        frozen_identity = _current_glean_auth_dependency_identity()
        frozen_identity_sha256 = _component_hash(frozen_identity)
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
        if _current_glean_auth_dependency_identity() != frozen_identity:
            raise ProviderStateIsolationError(
                "Glean authentication dependencies changed during authorization"
            )
        private["authentication_dependency_freeze"] = {
            "schema_version": _AUTHENTICATION_DEPENDENCY_FREEZE_SCHEMA,
            "status": "frozen",
            "panel_id": PANEL_ID,
            "public_precommitment_sha256": public["precommitment_sha256"],
            "static_cli_contract_sha256": public["contract_hashes"][
                "cli_sha256"
            ],
            "identity": frozen_identity,
            "identity_sha256": frozen_identity_sha256,
            "frozen_at_utc": _utc_now(),
        }
        expected = _expected_spend_authorization(
            public,
            frozen_glean_auth_dependency_identity_sha256=(
                frozen_identity_sha256
            ),
        )
        private["spend_authorization"] = expected
        _write_private_state(private_state_path, private, authentication_key)
        return expected


_AUTHENTICATION_PROVIDER_STATUSES = frozenset(
    {
        "required",
        "running",
        "retryable_failed",
        "terminal_failed",
        "passed",
    }
)
_AUTHENTICATION_SETUP_STATUSES = frozenset(
    {
        "required",
        "running",
        "retryable_failed",
        "terminal_failed",
        "pending_publication",
        "passed",
    }
)


def _authentication_contract_hashes(
    public: Mapping[str, Any],
) -> dict[str, str]:
    hashes = public.get("contract_hashes")
    names = (
        "source_sha256",
        "cli_sha256",
        "claude_auth_sha256",
        "codex_auth_sha256",
        "budgets_sha256",
        "runtime_sha256",
        "preparation_runtime_sha256",
        "supervisor_sha256",
    )
    if not isinstance(hashes, Mapping) or any(
        not isinstance(hashes.get(name), str) for name in names
    ):
        raise ValueError("Authentication contract commitments are invalid")
    return {name: str(hashes[name]) for name in names}


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and len(value) == 71
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _validate_glean_auth_dependency_identity(
    value: Any,
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "glean_helper",
        "glean_llm_gateway_token_wrapper",
    }:
        raise ValueError("Frozen Glean authentication dependency identity is invalid")
    helper = value.get("glean_helper")
    wrapper = value.get("glean_llm_gateway_token_wrapper")
    if (
        value.get("schema_version") != _AUTHENTICATION_DEPENDENCY_FREEZE_SCHEMA
        or not isinstance(helper, dict)
        or set(helper) != {"path", "sha256", "policy"}
        or helper.get("path") != str(_GLEAN_HELPER_PATH)
        or not _is_sha256(helper.get("sha256"))
        or helper.get("policy") != _ROOT_MANAGED_EXECUTABLE_POLICY
        or not isinstance(wrapper, dict)
        or set(wrapper)
        != {
            "path",
            "entrypoint_kind",
            "link_text",
            "resolved_path",
            "target_sha256",
            "policy",
            "dispatch_contract",
        }
        or wrapper.get("path") != str(_GLEAN_GATEWAY_TOKEN_WRAPPER_PATH)
        or wrapper.get("entrypoint_kind") != "regular_file"
        or wrapper.get("link_text") is not None
        or wrapper.get("policy") != _ROOT_MANAGED_EXECUTABLE_POLICY
        or not isinstance(wrapper.get("resolved_path"), str)
        or not Path(str(wrapper["resolved_path"])).is_absolute()
        or not _is_sha256(wrapper.get("target_sha256"))
        or wrapper.get("dispatch_contract") != _glean_gateway_dispatch_contract()
    ):
        raise ValueError("Frozen Glean authentication dependency identity is invalid")
    return value


def _authentication_dependency_freeze(
    private: Mapping[str, Any],
    public: Mapping[str, Any],
    *,
    require_frozen: bool,
) -> dict[str, Any]:
    freeze = private.get("authentication_dependency_freeze")
    if not isinstance(freeze, dict) or freeze.get("schema_version") != (
        _AUTHENTICATION_DEPENDENCY_FREEZE_SCHEMA
    ):
        raise ValueError("Private authentication dependency freeze is invalid")
    if freeze.get("status") == "required":
        if set(freeze) != {"schema_version", "status"} or require_frozen:
            raise RuntimeError(
                "Manifest-bound Glean authentication dependencies are not frozen"
            )
        return freeze
    if set(freeze) != {
        "schema_version",
        "status",
        "panel_id",
        "public_precommitment_sha256",
        "static_cli_contract_sha256",
        "identity",
        "identity_sha256",
        "frozen_at_utc",
    }:
        raise ValueError("Private authentication dependency freeze is invalid")
    identity = _validate_glean_auth_dependency_identity(freeze.get("identity"))
    hashes = public.get("contract_hashes")
    if (
        freeze.get("status") != "frozen"
        or freeze.get("panel_id") != PANEL_ID
        or freeze.get("public_precommitment_sha256")
        != public.get("precommitment_sha256")
        or not isinstance(hashes, Mapping)
        or freeze.get("static_cli_contract_sha256") != hashes.get("cli_sha256")
        or freeze.get("identity_sha256") != _component_hash(identity)
        or not isinstance(freeze.get("frozen_at_utc"), str)
        or not freeze["frozen_at_utc"]
    ):
        raise ValueError("Private authentication dependency freeze is invalid")
    return freeze


def _sanitized_authentication_dependency_projection(
    freeze: Mapping[str, Any],
) -> dict[str, Any]:
    _validate_glean_auth_dependency_identity(freeze.get("identity"))
    return {
        "schema_version": _AUTHENTICATION_DEPENDENCY_FREEZE_SCHEMA,
        "identity_sha256": freeze["identity_sha256"],
        "root_owned_single_link_regular_executable_policy_attested": True,
        "exact_bundle_identity_withheld": True,
        "raw_provider_output_published": False,
        "raw_machine_paths_published": False,
    }


def _attest_frozen_glean_auth_dependencies(
    private: Mapping[str, Any], public: Mapping[str, Any]
) -> dict[str, Any]:
    freeze = _authentication_dependency_freeze(
        private, public, require_frozen=True
    )
    current = _current_glean_auth_dependency_identity()
    if not hmac.compare_digest(
        _canonical_bytes(current),
        _canonical_bytes(dict(freeze["identity"])),
    ):
        raise ProviderStateIsolationError(
            "Frozen Glean authentication dependencies drifted"
        )
    return freeze


def _validate_authentication_setup_state(
    private: Mapping[str, Any],
    public: Mapping[str, Any],
) -> dict[str, Any]:
    setup = private.get("authentication_setup")
    if (
        not isinstance(setup, dict)
        or setup.get("schema_version") != _AUTHENTICATION_SETUP_SCHEMA
        or setup.get("status") not in _AUTHENTICATION_SETUP_STATUSES
        or setup.get("required_contract_hashes")
        != _authentication_contract_hashes(public)
        or setup.get("model_calls_started") != 0
        or type(setup.get("model_calls_started")) is not int
    ):
        raise ValueError("Private authentication setup state is invalid")
    for provider in ("codex", "managed_glean"):
        value = setup.get(provider)
        if (
            not isinstance(value, dict)
            or value.get("status") not in _AUTHENTICATION_PROVIDER_STATUSES
            or not isinstance(value.get("attempts"), list)
            or any(
                not isinstance(attempt, dict)
                or attempt.get("status")
                not in {
                    "launch_pending",
                    "started",
                    "start_failed",
                    "returned",
                    "retryable_failed",
                    "terminal_failed",
                    "passed",
                }
                for attempt in value["attempts"]
            )
        ):
            raise ValueError("Private provider authentication state is invalid")
        attempts = value["attempts"]
        provider_status = value["status"]
        if provider_status == "required":
            if attempts:
                raise ValueError(
                    "Private provider authentication state is invalid"
                )
        elif (
            not attempts
            or attempts[-1].get("status") != provider_status
            and not (
                provider_status == "running"
                and attempts[-1].get("status")
                in {
                    "launch_pending",
                    "started",
                    "start_failed",
                    "returned",
                }
            )
        ):
            raise ValueError(
                "Private provider authentication state is invalid"
            )

    overall = setup["status"]
    provider_pair = (
        setup["codex"]["status"],
        setup["managed_glean"]["status"],
    )
    allowed_pairs = {
        "required": {
            ("required", "required"),
            ("passed", "required"),
        },
        "running": {
            ("running", "required"),
            ("passed", "running"),
        },
        "retryable_failed": {
            ("retryable_failed", "required"),
            ("passed", "retryable_failed"),
        },
        "terminal_failed": {
            ("terminal_failed", "required"),
            ("passed", "terminal_failed"),
            ("terminal_failed", "terminal_failed"),
        },
        "pending_publication": {("passed", "passed")},
        "passed": {("passed", "passed")},
    }
    if provider_pair not in allowed_pairs[overall]:
        raise ValueError(
            "Private authentication setup state transition is invalid"
        )
    return setup


def _require_completed_authentication_state(
    private: Mapping[str, Any],
    public: Mapping[str, Any],
) -> dict[str, Any]:
    setup = _validate_authentication_setup_state(private, public)
    if (
        setup.get("status") not in {"pending_publication", "passed"}
        or setup["codex"].get("status") != "passed"
        or setup["managed_glean"].get("status") != "passed"
    ):
        raise RuntimeError("Authentication providers have not both passed")
    for field in (
        "codex_auth_file_identity",
        "managed_glean_auth_file_identity",
    ):
        identity = private.get(field)
        if (
            not isinstance(identity, Mapping)
            or set(identity) != {"device", "inode"}
            or any(
                type(identity.get(name)) is not int
                or int(identity[name]) < 0
                for name in ("device", "inode")
            )
        ):
            raise ValueError(
                "Completed authentication credential identity is invalid"
            )
    return setup


def _validate_authentication_contracts(
    *,
    root: Path,
    private: Mapping[str, Any],
    public: Mapping[str, Any],
    public_manifest_path: Path,
    claude_secure_storage_dir: Path,
    codex_secure_storage_dir: Path,
    revalidate_live_identity_contracts: bool,
) -> dict[str, Any]:
    """Validate authentication-only surfaces without reading cohort packs."""

    _validate_public_hash(public)
    run_contract = public.get("run_contract")
    if (
        public.get("schema_version") != SCHEMA_VERSION
        or public.get("panel_id") != PANEL_ID
        or public.get("status") != "precommitted"
        or public.get("results") != []
        or public.get("budget_contract") != _budget_contract(5.0)
        or not isinstance(run_contract, Mapping)
        or run_contract.get("spend_authorization")
        != _spend_authorization_contract()
        or run_contract.get("authentication_setup")
        != _authentication_setup_contract(public_manifest_path)
        or private.get("schema_version") != SCHEMA_VERSION
        or private.get("panel_id") != PANEL_ID
        or private.get("public_precommitment_sha256")
        != public.get("precommitment_sha256")
    ):
        raise ValueError("Authentication setup contract mismatch")
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
    hashes = public.get("contract_hashes")
    if not isinstance(hashes, Mapping) or any(
        hashes.get(name) != _component_hash(value)
        for name, value in (
            ("source_sha256", public.get("source_contract")),
            ("cli_sha256", public.get("cli_contract")),
            ("claude_auth_sha256", public.get("claude_auth_contract")),
            ("codex_auth_sha256", public.get("codex_auth_contract")),
            ("profiles_sha256", public.get("profiles")),
            ("budgets_sha256", public.get("budget_contract")),
            ("timeouts_sha256", public.get("timeout_contract")),
            ("runtime_sha256", public.get("runtime_contract")),
            ("replay_sha256", public.get("replay_trace_contract")),
            ("supervisor_sha256", public.get("persistent_supervisor_contract")),
        )
    ):
        raise ValueError("Authentication component commitment mismatch")
    if revalidate_live_identity_contracts:
        _attest_execution_contracts(root=root, public=public)
        _attest_frozen_glean_auth_dependencies(private, public)
    return _validate_authentication_setup_state(private, public)


def _expected_authentication_receipt(
    private: Mapping[str, Any],
    public: Mapping[str, Any],
) -> dict[str, Any]:
    _require_completed_authentication_state(private, public)
    spend = _assert_spend_authorization(private, public)
    dependency_freeze = _authentication_dependency_freeze(
        private, public, require_frozen=True
    )
    unsigned = {
        "schema_version": _AUTHENTICATION_RECEIPT_SCHEMA,
        "panel_id": PANEL_ID,
        "status": "passed",
        "development_only": True,
        "precommitment_sha256": public["precommitment_sha256"],
        "authentication_contract_hashes": _authentication_contract_hashes(
            public
        ),
        "spend_authorization_receipt_sha256": spend["receipt_sha256"],
        "authentication_dependency_identity": (
            _sanitized_authentication_dependency_projection(
                dependency_freeze
            )
        ),
        "authentication_prerequisite": {
            "codex": "passed_before_preflight",
            "managed_glean": "passed_before_preflight",
            "codex_method": "pinned_cli_device_auth",
            "managed_glean_method": "pinned_managed_oauth_helper",
            "model_calls": 0,
        },
        "model_calls_started": 0,
        "production_episodes_consumed": 0,
        "scores_reported": False,
    }
    return {**unsigned, "receipt_sha256": _component_hash(unsigned)}


def _validate_authentication_receipt(
    receipt: Mapping[str, Any],
    *,
    private: Mapping[str, Any],
    public: Mapping[str, Any],
) -> None:
    expected = _expected_authentication_receipt(private, public)
    if not hmac.compare_digest(
        _canonical_bytes(dict(receipt)), _canonical_bytes(expected)
    ):
        raise ValueError("Public authentication receipt is invalid")


def _authentication_status_payload(
    setup: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "panel_id": PANEL_ID,
        "status": str(setup.get("status")),
        "providers": {
            provider: {"status": str(setup[provider].get("status"))}
            for provider in ("codex", "managed_glean")
        },
        "model_calls_started": 0,
    }


def _require_operator_authentication_tty() -> None:
    streams = (sys.stdin, sys.stdout, sys.stderr)
    if any(
        not callable(getattr(stream, "isatty", None))
        or not stream.isatty()
        for stream in streams
    ):
        raise RuntimeError(
            "Interactive authentication requires a foreground operator TTY"
        )


def _authentication_provider_is_retryably_empty(
    provider: str,
    *,
    root: Path,
    private: Mapping[str, Any],
    claude_secure_storage_dir: Path,
    codex_secure_storage_dir: Path,
) -> bool:
    try:
        if provider == "codex":
            _require_codex_credential_state(
                codex_secure_storage_dir,
                root=root,
                expected_identity=_private_codex_storage_identity(private),
                credentials_present=False,
            )
            return True
        elif provider == "managed_glean":
            _require_claude_credential_state(
                claude_secure_storage_dir,
                root=root,
                expected_identity=_private_claude_storage_identity(private),
                managed_glean_credentials_present=False,
            )
            return True
    except Exception:
        return False
    raise ValueError("Unknown authentication provider")


def _terminalize_authentication_incident(
    *,
    private: dict[str, Any],
    private_state_path: Path,
    authentication_key: bytes,
    incident: str,
) -> None:
    setup = private["authentication_setup"]
    now = _utc_now()
    for provider in ("codex", "managed_glean"):
        state = setup[provider]
        attempts = state["attempts"]
        attempts.append(
            {
                "status": "terminal_failed",
                "finished_at_utc": now,
                "invocation": incident,
            }
        )
        state["status"] = "terminal_failed"
    setup["status"] = "terminal_failed"
    _write_private_state(
        private_state_path, private, authentication_key
    )


def _persist_authentication_attempt(
    *,
    private: dict[str, Any],
    provider: str,
    private_state_path: Path,
    authentication_key: bytes,
    action: str,
    returncode: int | None = None,
) -> None:
    setup = private["authentication_setup"]
    state = setup[provider]
    attempts = state["attempts"]
    now = _utc_now()
    if action == "launch_pending":
        if state.get("status") not in {"required", "retryable_failed"}:
            raise ProviderStateIsolationError(
                "Authentication invocation state changed"
            )
        attempts.append(
            {
                "status": "launch_pending",
                "launch_pending_at_utc": now,
            }
        )
        state["status"] = "running"
        setup["status"] = "running"
    else:
        if state.get("status") != "running" or not attempts:
            raise ProviderStateIsolationError(
                "Authentication invocation state changed"
            )
        attempt = attempts[-1]
        if action == "started" and attempt.get("status") == "launch_pending":
            attempt.update({"status": "started", "started_at_utc": now})
        elif (
            action == "start_failed"
            and attempt.get("status") == "launch_pending"
        ):
            attempt.update(
                {"status": "start_failed", "start_failed_at_utc": now}
            )
        elif (
            action == "returned"
            and attempt.get("status") == "started"
            and type(returncode) is int
        ):
            attempt.update(
                {
                    "status": "returned",
                    "returned_at_utc": now,
                    "returncode": returncode,
                }
            )
        else:
            raise ProviderStateIsolationError(
                "Authentication invocation state changed"
            )
    try:
        _write_private_state(private_state_path, private, authentication_key)
    except Exception as error:
        raise ProviderStateIsolationError(
            "Authentication invocation marker could not be persisted"
        ) from error


def _finish_authentication_provider_attempt(
    *,
    private: dict[str, Any],
    provider: str,
    status: str,
    private_state_path: Path,
    authentication_key: bytes,
) -> None:
    setup = private["authentication_setup"]
    state = setup[provider]
    attempts = state["attempts"]
    if status not in {"retryable_failed", "terminal_failed", "passed"}:
        raise ValueError("Invalid authentication attempt outcome")
    if not attempts:
        attempts.append(
            {
                "status": status,
                "finished_at_utc": _utc_now(),
                "invocation": "not_launched",
            }
        )
    else:
        attempts[-1] = {
            **attempts[-1],
            "status": status,
            "finished_at_utc": _utc_now(),
        }
    state["status"] = status
    if status == "terminal_failed":
        setup["status"] = "terminal_failed"
    elif status == "retryable_failed":
        setup["status"] = "retryable_failed"
    elif all(
        setup[name].get("status") == "passed"
        for name in ("codex", "managed_glean")
    ):
        setup["status"] = "pending_publication"
    else:
        setup["status"] = "required"
    _write_private_state(private_state_path, private, authentication_key)


def _publish_authentication_receipt(
    *,
    root: Path,
    private: dict[str, Any],
    public: Mapping[str, Any],
    private_state_path: Path,
    public_manifest_path: Path,
    authentication_key: bytes,
) -> dict[str, Any]:
    setup = _require_completed_authentication_state(private, public)
    receipt_path = _authentication_receipt_path(public_manifest_path)
    expected = _expected_authentication_receipt(private, public)
    if setup.get("status") == "pending_publication":
        candidate = setup.get("pending_public_receipt")
        if candidate is None:
            setup["pending_public_receipt"] = expected
            _write_private_state(
                private_state_path, private, authentication_key
            )
        elif candidate != expected:
            raise ProviderStateIsolationError(
                "Authentication receipt publication state changed"
            )
    elif setup.get("status") != "passed":
        raise RuntimeError("Authentication providers have not both passed")

    if receipt_path.exists() or receipt_path.is_symlink():
        observed = _load_json(receipt_path)
        _validate_authentication_receipt(
            observed, private=private, public=public
        )
    else:
        try:
            _create_public_json_once(receipt_path, expected)
        except FileExistsError:
            pass
        observed = _load_json(receipt_path)
        _validate_authentication_receipt(
            observed, private=private, public=public
        )
    if setup.get("status") != "passed":
        setup.pop("pending_public_receipt", None)
        setup["status"] = "passed"
        setup["public_receipt_binding"] = _repository_receipt_binding(
            root=root,
            path=receipt_path,
            artifact_kind="authentication",
            content_sha256=str(observed["receipt_sha256"]),
            payload=observed,
        )
        setup["public_receipt_sha256"] = observed["receipt_sha256"]
        _write_private_state(private_state_path, private, authentication_key)
    return observed


def _attest_authentication_credentials(
    *,
    root: Path,
    private: Mapping[str, Any],
    setup: Mapping[str, Any],
    claude_secure_storage_dir: Path,
    codex_secure_storage_dir: Path,
) -> None:
    codex_passed = setup["codex"].get("status") == "passed"
    glean_passed = setup["managed_glean"].get("status") == "passed"
    _require_codex_credential_state(
        codex_secure_storage_dir,
        root=root,
        expected_identity=_private_codex_storage_identity(private),
        credentials_present=codex_passed,
    )
    _require_claude_credential_state(
        claude_secure_storage_dir,
        root=root,
        expected_identity=_private_claude_storage_identity(private),
        managed_glean_credentials_present=glean_passed,
    )
    if codex_passed:
        identity = private.get("codex_auth_file_identity")
        if not isinstance(identity, Mapping):
            raise ValueError("Codex credential identity is unavailable")
        _require_codex_auth_file_identity(
            codex_secure_storage_dir, identity
        )
    if glean_passed:
        identity = private.get("managed_glean_auth_file_identity")
        if not isinstance(identity, Mapping):
            raise ValueError("Managed Glean credential identity is unavailable")
        _require_managed_glean_auth_file_identity(
            claude_secure_storage_dir, identity
        )


def authenticate_panel(
    *,
    root: Path,
    authentication_key_file: Path,
    claude_secure_storage_dir: Path,
    codex_secure_storage_dir: Path,
    private_state_path: Path,
    public_manifest_path: Path,
    acknowledge_interactive_authentication: bool = False,
) -> dict[str, Any]:
    """Run foreground, zero-model authentication before one-shot preflight."""

    if acknowledge_interactive_authentication is not True:
        raise RuntimeError(
            "Explicit acknowledgement of foreground interactive "
            "authentication is required"
        )
    assert_durable_live_execution_paths(
        root=root, private_state_path=private_state_path
    )
    resolved_claude = _validate_claude_secure_storage_dir(
        claude_secure_storage_dir, root=root
    )
    resolved_codex = _validate_codex_secure_storage_dir(
        codex_secure_storage_dir, root=root
    )
    if _paths_overlap(resolved_claude, resolved_codex):
        raise ValueError(
            "Claude and Codex secure storage directories must not overlap"
        )
    receipt_path = _authentication_receipt_path(public_manifest_path)
    _assert_distinct_paths(
        authentication_key_file,
        private_state_path,
        public_manifest_path,
        receipt_path,
    )
    with _exclusive_run_lock(private_state_path):
        key = _read_authentication_key(
            _existing_path_without_final_symlink(authentication_key_file)
        )
        private = _load_private_state(private_state_path, key)
        public = _load_json(public_manifest_path)
        setup = _validate_authentication_contracts(
            root=root,
            private=private,
            public=public,
            public_manifest_path=public_manifest_path,
            claude_secure_storage_dir=resolved_claude,
            codex_secure_storage_dir=resolved_codex,
            revalidate_live_identity_contracts=False,
        )
        _assert_spend_authorization(private, public)
        _attest_execution_contracts(root=root, public=public)
        _attest_frozen_glean_auth_dependencies(private, public)
        if setup.get("status") == "terminal_failed":
            raise RuntimeError(
                "This panel has a terminal authentication incident"
            )
        if setup.get("status") in {"pending_publication", "passed"}:
            try:
                _attest_authentication_credentials(
                    root=root,
                    private=private,
                    setup=setup,
                    claude_secure_storage_dir=resolved_claude,
                    codex_secure_storage_dir=resolved_codex,
                )
                _attest_execution_contracts(root=root, public=public)
                _attest_frozen_glean_auth_dependencies(private, public)
            except Exception:
                _terminalize_authentication_incident(
                    private=private,
                    private_state_path=private_state_path,
                    authentication_key=key,
                    incident="credential_integrity_incident",
                )
                raise RuntimeError(
                    "Authentication entered a terminal credential-integrity "
                    "state; this V19 panel cannot retry"
                ) from None
            if (
                setup.get("status") == "pending_publication"
                and not receipt_path.exists()
                and not receipt_path.is_symlink()
            ):
                _assert_authorization_worktree(
                    root=root,
                    private_state_path=private_state_path,
                    public_manifest_path=public_manifest_path,
                )
            _publish_authentication_receipt(
                root=root,
                private=private,
                public=public,
                private_state_path=private_state_path,
                public_manifest_path=public_manifest_path,
                authentication_key=key,
            )
            return _authentication_status_payload(
                private["authentication_setup"]
            )
        if setup.get("status") == "running":
            _terminalize_authentication_incident(
                private=private,
                private_state_path=private_state_path,
                authentication_key=key,
                incident="interrupted_process_state",
            )
            raise RuntimeError(
                "Authentication process state is ambiguous; this V19 panel "
                "cannot retry"
            )
        if (
            private.get("status") != "prepared"
            or private.get("assignments") != []
            or not isinstance(private.get("environment_preflight"), Mapping)
            or private["environment_preflight"].get("status") != "required"
        ):
            raise RuntimeError(
                "Authentication must precede the one-shot environment preflight"
            )
        _assert_authorization_worktree(
            root=root,
            private_state_path=private_state_path,
            public_manifest_path=public_manifest_path,
        )
        try:
            _attest_authentication_credentials(
                root=root,
                private=private,
                setup=setup,
                claude_secure_storage_dir=resolved_claude,
                codex_secure_storage_dir=resolved_codex,
            )
        except Exception:
            _terminalize_authentication_incident(
                private=private,
                private_state_path=private_state_path,
                authentication_key=key,
                incident="credential_integrity_incident",
            )
            raise RuntimeError(
                "Authentication entered a terminal credential-integrity "
                "state; this V19 panel cannot retry"
            ) from None
        _require_operator_authentication_tty()
        timeout = int(public["timeout_contract"]["seconds_per_assignment"])
        providers = (
            (
                "codex",
                lambda: _bootstrap_codex_credentials(
                    resolved_codex,
                    executable=str(
                        _PROFILE_BY_ID["codex-sol"]["executable"]
                    ),
                    timeout_seconds=timeout,
                    invocation_launch_pending=lambda: (
                        _persist_authentication_attempt(
                            private=private,
                            provider="codex",
                            private_state_path=private_state_path,
                            authentication_key=key,
                            action="launch_pending",
                        )
                    ),
                    invocation_started=lambda: (
                        _persist_authentication_attempt(
                            private=private,
                            provider="codex",
                            private_state_path=private_state_path,
                            authentication_key=key,
                            action="started",
                        )
                    ),
                    invocation_start_failed=lambda: (
                        _persist_authentication_attempt(
                            private=private,
                            provider="codex",
                            private_state_path=private_state_path,
                            authentication_key=key,
                            action="start_failed",
                        )
                    ),
                    invocation_returned=lambda returncode: (
                        _persist_authentication_attempt(
                            private=private,
                            provider="codex",
                            private_state_path=private_state_path,
                            authentication_key=key,
                            action="returned",
                            returncode=returncode,
                        )
                    ),
                ),
            ),
            (
                "managed_glean",
                lambda: _bootstrap_managed_glean_credentials(
                    resolved_claude,
                    oauth_client_id=_glean_claude_oauth_client_id(),
                    timeout_seconds=timeout,
                    invocation_launch_pending=lambda: (
                        _persist_authentication_attempt(
                            private=private,
                            provider="managed_glean",
                            private_state_path=private_state_path,
                            authentication_key=key,
                            action="launch_pending",
                        )
                    ),
                    invocation_started=lambda: (
                        _persist_authentication_attempt(
                            private=private,
                            provider="managed_glean",
                            private_state_path=private_state_path,
                            authentication_key=key,
                            action="started",
                        )
                    ),
                    invocation_start_failed=lambda: (
                        _persist_authentication_attempt(
                            private=private,
                            provider="managed_glean",
                            private_state_path=private_state_path,
                            authentication_key=key,
                            action="start_failed",
                        )
                    ),
                    invocation_returned=lambda returncode: (
                        _persist_authentication_attempt(
                            private=private,
                            provider="managed_glean",
                            private_state_path=private_state_path,
                            authentication_key=key,
                            action="returned",
                            returncode=returncode,
                        )
                    ),
                ),
            ),
        )
        for provider, bootstrap in providers:
            state = setup[provider]
            if state.get("status") == "passed":
                continue
            _attest_execution_contracts(root=root, public=public)
            _attest_frozen_glean_auth_dependencies(private, public)
            _assert_authorization_worktree(
                root=root,
                private_state_path=private_state_path,
                public_manifest_path=public_manifest_path,
            )
            try:
                _attest_authentication_credentials(
                    root=root,
                    private=private,
                    setup=setup,
                    claude_secure_storage_dir=resolved_claude,
                    codex_secure_storage_dir=resolved_codex,
                )
            except Exception:
                _terminalize_authentication_incident(
                    private=private,
                    private_state_path=private_state_path,
                    authentication_key=key,
                    incident="credential_integrity_incident",
                )
                raise RuntimeError(
                    "Authentication entered a terminal credential-integrity "
                    "state; this V19 panel cannot retry"
                ) from None
            try:
                bootstrap()
                _attest_execution_contracts(root=root, public=public)
                _attest_frozen_glean_auth_dependencies(private, public)
                if provider == "codex":
                    _require_codex_credential_state(
                        resolved_codex,
                        root=root,
                        expected_identity=_private_codex_storage_identity(
                            private
                        ),
                        credentials_present=True,
                    )
                    private["codex_auth_file_identity"] = (
                        _codex_auth_file_identity(resolved_codex)
                    )
                else:
                    _require_claude_credential_state(
                        resolved_claude,
                        root=root,
                        expected_identity=_private_claude_storage_identity(
                            private
                        ),
                        managed_glean_credentials_present=True,
                    )
                    private["managed_glean_auth_file_identity"] = (
                        _managed_glean_auth_file_identity(resolved_claude)
                    )
                _finish_authentication_provider_attempt(
                    private=private,
                    provider=provider,
                    status="passed",
                    private_state_path=private_state_path,
                    authentication_key=key,
                )
            except KeyboardInterrupt:
                _finish_authentication_provider_attempt(
                    private=private,
                    provider=provider,
                    status="terminal_failed",
                    private_state_path=private_state_path,
                    authentication_key=key,
                )
                raise
            except Exception as error:
                retryable = (
                    not isinstance(error, ProviderExecutionIsolationError)
                    and _authentication_provider_is_retryably_empty(
                        provider,
                        root=root,
                        private=private,
                        claude_secure_storage_dir=resolved_claude,
                        codex_secure_storage_dir=resolved_codex,
                    )
                )
                _finish_authentication_provider_attempt(
                    private=private,
                    provider=provider,
                    status=(
                        "retryable_failed"
                        if retryable
                        else "terminal_failed"
                    ),
                    private_state_path=private_state_path,
                    authentication_key=key,
                )
                if retryable:
                    return _authentication_status_payload(
                        private["authentication_setup"]
                    )
                raise RuntimeError(
                    "Authentication entered a terminal ambiguous state; this "
                    "V19 panel cannot retry"
                ) from None

        _attest_execution_contracts(root=root, public=public)
        _attest_frozen_glean_auth_dependencies(private, public)
        _assert_authorization_worktree(
            root=root,
            private_state_path=private_state_path,
            public_manifest_path=public_manifest_path,
        )
        try:
            _attest_authentication_credentials(
                root=root,
                private=private,
                setup=private["authentication_setup"],
                claude_secure_storage_dir=resolved_claude,
                codex_secure_storage_dir=resolved_codex,
            )
        except Exception:
            _terminalize_authentication_incident(
                private=private,
                private_state_path=private_state_path,
                authentication_key=key,
                incident="credential_integrity_incident",
            )
            raise RuntimeError(
                "Authentication entered a terminal credential-integrity "
                "state; this V19 panel cannot retry"
            ) from None
        _publish_authentication_receipt(
            root=root,
            private=private,
            public=public,
            private_state_path=private_state_path,
            public_manifest_path=public_manifest_path,
            authentication_key=key,
        )
        return _authentication_status_payload(
            private["authentication_setup"]
        )


def panel_authentication_status(
    *,
    root: Path,
    authentication_key_file: Path,
    claude_secure_storage_dir: Path,
    codex_secure_storage_dir: Path,
    private_state_path: Path,
    public_manifest_path: Path,
) -> dict[str, Any]:
    """Return finite authentication state without launching any helper."""

    with _exclusive_run_lock(private_state_path):
        key = _read_authentication_key(
            _existing_path_without_final_symlink(authentication_key_file)
        )
        private = _load_private_state(private_state_path, key)
        public = _load_json(public_manifest_path)
        resolved_claude = _validate_claude_secure_storage_dir(
            claude_secure_storage_dir, root=root
        )
        resolved_codex = _validate_codex_secure_storage_dir(
            codex_secure_storage_dir, root=root
        )
        setup = _validate_authentication_contracts(
            root=root,
            private=private,
            public=public,
            public_manifest_path=public_manifest_path,
            claude_secure_storage_dir=resolved_claude,
            codex_secure_storage_dir=resolved_codex,
            revalidate_live_identity_contracts=False,
        )
        try:
            _attest_authentication_credentials(
                root=root,
                private=private,
                setup=setup,
                claude_secure_storage_dir=resolved_claude,
                codex_secure_storage_dir=resolved_codex,
            )
        except Exception:
            terminal = _authentication_status_payload(setup)
            terminal["status"] = "terminal_failed"
            terminal["providers"] = {
                provider: {"status": "terminal_failed"}
                for provider in ("codex", "managed_glean")
            }
            return terminal
        if setup.get("status") == "passed":
            receipt = _load_json(
                _authentication_receipt_path(public_manifest_path)
            )
            _validate_authentication_receipt(
                receipt, private=private, public=public
            )
        return _authentication_status_payload(setup)


def assert_panel_authentication_ready(
    *,
    root: Path,
    authentication_key_file: Path,
    claude_secure_storage_dir: Path,
    codex_secure_storage_dir: Path,
    private_state_path: Path,
    public_manifest_path: Path,
    require_clean_checkout: bool = True,
    revalidate_live_identity_contracts: bool = True,
) -> dict[str, Any]:
    """Fail closed unless committed foreground authentication is still valid."""

    key = _read_authentication_key(
        _existing_path_without_final_symlink(authentication_key_file)
    )
    private = _load_private_state(private_state_path, key)
    public = _load_json(public_manifest_path)
    resolved_claude = _validate_claude_secure_storage_dir(
        claude_secure_storage_dir, root=root
    )
    resolved_codex = _validate_codex_secure_storage_dir(
        codex_secure_storage_dir, root=root
    )
    setup = _validate_authentication_contracts(
        root=root,
        private=private,
        public=public,
        public_manifest_path=public_manifest_path,
        claude_secure_storage_dir=resolved_claude,
        codex_secure_storage_dir=resolved_codex,
        revalidate_live_identity_contracts=False,
    )
    _assert_spend_authorization(private, public)
    if revalidate_live_identity_contracts:
        _attest_execution_contracts(root=root, public=public)
        _attest_frozen_glean_auth_dependencies(private, public)
    if setup.get("status") != "passed":
        raise RuntimeError(
            "Foreground authentication must pass before supervisor creation"
        )
    _attest_authentication_credentials(
        root=root,
        private=private,
        setup=setup,
        claude_secure_storage_dir=resolved_claude,
        codex_secure_storage_dir=resolved_codex,
    )
    receipt_path = _authentication_receipt_path(public_manifest_path)
    receipt = _load_json(receipt_path)
    _validate_authentication_receipt(
        receipt, private=private, public=public
    )
    if setup.get("public_receipt_sha256") != receipt.get("receipt_sha256"):
        raise RuntimeError("Authentication receipt binding changed")
    _validate_repository_receipt_binding(
        setup.get("public_receipt_binding"),
        root=root,
        path=receipt_path,
        artifact_kind="authentication",
        content_sha256=str(receipt["receipt_sha256"]),
        payload=receipt,
        require_published_commit=True,
    )
    if require_clean_checkout:
        _assert_authorization_worktree(
            root=root,
            private_state_path=private_state_path,
            public_manifest_path=public_manifest_path,
        )
        receipt_relative = _relative_to_root(receipt_path, root)
        if (
            _git_output(
                root, "ls-files", "--error-unmatch", receipt_relative
            )
            != receipt_relative
        ):
            raise RuntimeError(
                "Authentication receipt must be committed before supervisor creation"
            )
    return receipt


def bind_panel_receipt_commit(
    *,
    root: Path,
    operation: str,
    authentication_key_file: Path,
    claude_secure_storage_dir: Path,
    codex_secure_storage_dir: Path,
    private_state_path: Path,
    public_manifest_path: Path,
) -> dict[str, Any]:
    """Bind one already-published receipt to exact tracked bytes and commit.

    This provider-free step is deliberately separate from receipt publication:
    the receipt must first be committed, after which the authenticated private
    state records that immutable commit exactly once. Later clean descendant
    checkouts may move without changing the binding.
    """

    if operation not in {"authentication", "preflight"}:
        raise ValueError("Public receipt binding operation is invalid")
    assert_durable_live_execution_paths(
        root=root, private_state_path=private_state_path
    )
    authentication_key = _read_authentication_key(
        _existing_path_without_final_symlink(authentication_key_file)
    )
    with _exclusive_run_lock(private_state_path):
        private = _load_private_state(private_state_path, authentication_key)
        public = _load_json(public_manifest_path)
        resolved_claude = _validate_claude_secure_storage_dir(
            claude_secure_storage_dir, root=root
        )
        resolved_codex = _validate_codex_secure_storage_dir(
            codex_secure_storage_dir, root=root
        )
        setup = _validate_authentication_contracts(
            root=root,
            private=private,
            public=public,
            public_manifest_path=public_manifest_path,
            claude_secure_storage_dir=resolved_claude,
            codex_secure_storage_dir=resolved_codex,
            revalidate_live_identity_contracts=False,
        )
        _assert_spend_authorization(private, public)
        if setup.get("status") != "passed":
            raise RuntimeError(
                "Authentication receipt must pass before commit binding"
            )
        authentication_receipt_path = _authentication_receipt_path(
            public_manifest_path
        )
        authentication_receipt = _load_json(authentication_receipt_path)
        _validate_authentication_receipt(
            authentication_receipt, private=private, public=public
        )
        _validate_repository_receipt_binding(
            setup.get("public_receipt_binding"),
            root=root,
            path=authentication_receipt_path,
            artifact_kind="authentication",
            content_sha256=str(authentication_receipt["receipt_sha256"]),
            payload=authentication_receipt,
            require_published_commit=operation == "preflight",
        )

        if operation == "authentication":
            state = setup
            path = authentication_receipt_path
            payload = authentication_receipt
            content_sha256 = str(authentication_receipt["receipt_sha256"])
        else:
            _assert_environment_preflight(
                root,
                private,
                public,
                require_published_commit=False,
            )
            preflight = private.get("environment_preflight")
            if not isinstance(preflight, dict):
                raise RuntimeError("Environment preflight state is invalid")
            state = preflight
            path = _receipt_path_from_binding(
                root,
                state.get("public_receipt_binding"),
                artifact_kind="preflight",
            )
            payload = _load_json(path)
            content_sha256 = str(state["public_receipt_sha256"])

        binding = _validate_repository_receipt_binding(
            state.get("public_receipt_binding"),
            root=root,
            path=path,
            artifact_kind=operation,
            content_sha256=content_sha256,
            payload=payload,
            require_published_commit=False,
        )
        head = _assert_authorization_worktree(
            root=root,
            private_state_path=private_state_path,
            public_manifest_path=public_manifest_path,
        )
        relative = str(binding["repository_relative_path"])
        if (
            _git_output(root, "ls-files", "--error-unmatch", relative)
            != relative
            or _git_blob_sha256(root, head, relative)
            != binding["file_sha256"]
        ):
            raise RuntimeError(
                "Public receipt must be committed with its exact bytes"
            )
        existing_commit = binding.get("published_commit")
        if existing_commit is None:
            state["public_receipt_binding"] = {
                **binding,
                "published_commit": head,
            }
            _write_private_state(
                private_state_path, private, authentication_key
            )
            published_commit = head
        else:
            _validate_repository_receipt_binding(
                binding,
                root=root,
                path=path,
                artifact_kind=operation,
                content_sha256=content_sha256,
                payload=payload,
                require_published_commit=True,
            )
            published_commit = str(existing_commit)
        return {
            "schema_version": "epiagentbench.receipt_commit_binding.v1",
            "panel_id": PANEL_ID,
            "artifact_kind": operation,
            "status": "bound",
            "published_commit": published_commit,
            "file_sha256": binding["file_sha256"],
        }


def assert_environment_preflight_ready(
    *,
    root: Path,
    authentication_key_file: Path,
    private_state_path: Path,
    public_manifest_path: Path,
) -> dict[str, Any]:
    """Attest the passed preflight receipt without invoking any provider."""

    authentication_key = _read_authentication_key(
        _existing_path_without_final_symlink(authentication_key_file)
    )
    private = _load_private_state(private_state_path, authentication_key)
    public = _load_json(public_manifest_path)
    _assert_environment_preflight(root, private, public)
    preflight = private["environment_preflight"]
    binding = preflight["public_receipt_binding"]
    return {
        "panel_id": PANEL_ID,
        "status": "passed",
        "artifact_kind": "preflight",
        "published_commit": binding["published_commit"],
        "file_sha256": binding["file_sha256"],
    }


def _terminal_preflight_candidate(
    private: Mapping[str, Any],
    public: Mapping[str, Any],
) -> tuple[Mapping[str, Any], dict[str, Any]]:
    preflight = private.get("environment_preflight")
    candidate = (
        preflight.get("terminal_public_receipt")
        if isinstance(preflight, Mapping)
        else None
    )
    if (
        not isinstance(preflight, Mapping)
        or preflight.get("status") != "failed"
        or not isinstance(candidate, dict)
        or candidate.get("schema_version") != SCHEMA_VERSION
        or candidate.get("panel_id") != PANEL_ID
        or candidate.get("status")
        not in {"failed", "stopped_supervisor_incident"}
        or candidate.get("development_only") is not True
        or type(candidate.get("production_episodes_consumed")) is not int
        or candidate.get("production_episodes_consumed") != 0
        or candidate.get("scores_reported") is not False
        or candidate.get("precommitment_sha256")
        != public.get("precommitment_sha256")
        or preflight.get("public_receipt_sha256")
        != _component_hash(candidate)
    ):
        raise RuntimeError(
            "Authenticated terminal preflight candidate is invalid"
        )
    incident_code = candidate.get("incident_code")
    if (
        (
            incident_code is not None
            and incident_code not in _PROVIDER_INCIDENT_CODES
        )
        or (
            candidate.get("status") == "stopped_supervisor_incident"
            and incident_code != "supervisor_boundary_attestation_failed"
        )
        or (
            candidate.get("failure_reason") == "terminal_abort"
            and incident_code not in _PROVIDER_INCIDENT_CODES
        )
    ):
        raise RuntimeError(
            "Terminal preflight receipt incident code is invalid"
        )
    failure_stage = candidate.get("failure_stage")
    if (
        (
            failure_stage is not None
            and failure_stage not in _PREFLIGHT_FAILURE_STAGES
        )
        or (
            candidate.get("failure_reason") == "terminal_abort"
            and failure_stage not in _PREFLIGHT_FAILURE_STAGES
        )
    ):
        raise RuntimeError(
            "Terminal preflight receipt failure stage is invalid"
        )
    if candidate.get("failure_reason") == "provider_cli_readiness_timeout":
        profiles = candidate.get("profiles")
        failed_profile_id = candidate.get("failed_profile_id")
        readiness_profiles: list[Mapping[str, Any]] = []
        expected_chargeable = 0
        profiles_consistent = isinstance(profiles, list)
        if profiles_consistent:
            for profile in profiles:
                if not isinstance(profile, Mapping):
                    profiles_consistent = False
                    break
                model_invocation_state = profile.get(
                    "model_invocation_state"
                )
                if model_invocation_state not in {
                    "not_started",
                    "started_not_finished",
                    "finished",
                }:
                    profiles_consistent = False
                    break
                chargeable = model_invocation_state != "not_started"
                if profile.get("conservative_chargeable") is not chargeable:
                    profiles_consistent = False
                    break
                expected_chargeable += int(chargeable)
                if profile.get("profile_id") == failed_profile_id:
                    readiness_profiles.append(profile)
        readiness_profile = (
            readiness_profiles[0]
            if len(readiness_profiles) == 1
            else None
        )
        if (
            candidate.get("failure_stage") != "provider_cli_readiness"
            or candidate.get("incident_code")
            != "provider_cli_readiness_timeout"
            or candidate.get("failed_model_invocation_state")
            != "not_started"
            or not profiles_consistent
            or readiness_profile is None
            or readiness_profile.get("model_invocation_state")
            != "not_started"
            or readiness_profile.get("conservative_chargeable") is not False
            or readiness_profile.get("outcome")
            != "failed_provider_cli_readiness_timeout"
            or readiness_profile.get("timed_out") is not True
            or readiness_profile.get("timeout_stage")
            != "provider_cli_readiness"
            or candidate.get("model_invocations_conservatively_chargeable")
            != expected_chargeable
            or candidate.get("timed_out") is not True
            or candidate.get("timeout_stages")
            != ["provider_cli_readiness"]
        ):
            raise RuntimeError(
                "Terminal readiness-timeout receipt is inconsistent"
            )
    return preflight, candidate


def assert_terminal_receipt_ready_for_exit(
    *,
    root: Path,
    operation: str,
    authentication_key_file: Path,
    private_state_path: Path,
    public_manifest_path: Path,
    public_output_path: Path,
) -> dict[str, Any]:
    """Prove that exit 64 refers to one authenticated terminal receipt.

    This is a provider-free child-process boundary.  The reserved exit code is
    emitted only after the public artifact is reloaded and matched exactly to
    authenticated durable state.  A missing, torn, or inconsistent receipt
    therefore becomes an unexpected process failure rather than a falsely
    classified benchmark outcome.
    """

    if operation not in {"preflight", "production"}:
        raise ValueError("Terminal receipt operation is invalid")
    authentication_key = _read_authentication_key(
        _existing_path_without_final_symlink(authentication_key_file)
    )
    with _exclusive_run_lock(private_state_path):
        private = _load_private_state(private_state_path, authentication_key)
        public = _load_json(public_manifest_path)
        _validate_public_hash(public)
        _assert_private_public_panel_binding(private, public)
        _assert_canonical_public_output_path(
            public_manifest_path,
            public_output_path,
            operation=operation,
        )
        observed = _load_json(public_output_path)

        if operation == "preflight":
            preflight, candidate = _terminal_preflight_candidate(
                private,
                public,
            )
            if candidate != observed:
                raise RuntimeError(
                    "Authenticated terminal preflight receipt is inconsistent"
                )
            binding = _validate_repository_receipt_binding(
                preflight.get("public_receipt_binding"),
                root=root,
                path=public_output_path,
                artifact_kind="preflight",
                content_sha256=str(preflight["public_receipt_sha256"]),
                payload=candidate,
                require_published_commit=False,
            )
            observed_file_sha256 = _assert_exact_public_json_bytes(
                public_output_path,
                candidate,
                label="terminal preflight receipt",
            )
            if not hmac.compare_digest(
                observed_file_sha256,
                str(binding["file_sha256"]),
            ):
                raise RuntimeError(
                    "Terminal preflight receipt bytes changed"
                )
            return {
                "schema_version": (
                    "epiagentbench.terminal_receipt_attestation.v1"
                ),
                "panel_id": PANEL_ID,
                "operation": operation,
                "status": "attested",
                "terminal_status": str(candidate["status"]),
                "file_sha256": str(binding["file_sha256"]),
                "provider_processes_started": 0,
                "model_calls_started": 0,
            }

        status = observed.get("status")
        if status not in {
            "stopped_supervisor_incident",
            "stopped_transport_void",
        }:
            raise RuntimeError(
                "Production child did not publish a terminal stop receipt"
            )
        execution_incident = private.get("execution_incident")
        codex_auth_incident = private.get("codex_auth_incident")
        if execution_incident is None and codex_auth_incident is None:
            raise RuntimeError(
                "Production terminal receipt has no durable incident"
            )
        assignments = private.get("assignments")
        if not isinstance(assignments, list):
            raise RuntimeError(
                "Production terminal receipt assignments are invalid"
            )
        if (
            codex_auth_incident is not None
            and not _codex_auth_incident_is_valid(
                codex_auth_incident, assignments
            )
        ):
            raise RuntimeError(
                "Production Codex authentication incident is invalid"
            )
        if execution_incident is not None:
            if (
                not isinstance(execution_incident, Mapping)
                or execution_incident.get("status") != "terminal"
                or execution_incident.get("incident_code")
                not in _PROVIDER_INCIDENT_CODES
                or not isinstance(
                    execution_incident.get("failure_class"), str
                )
                or not execution_incident["failure_class"]
            ):
                raise RuntimeError(
                    "Production execution incident is invalid"
                )
            failure_class = execution_incident["failure_class"]
            failure_code = execution_incident.get(
                "attestation_failure_code"
            )
            supervisor_incident = (
                execution_incident.get("boundary")
                in {"clean_before_assignment", "final_completion"}
                or failure_code in _PERSISTENT_ATTESTATION_FAILURE_CODES
                or (
                    "boundary" not in execution_incident
                    and failure_class
                    in _PROVIDER_ISOLATION_FAILURE_CLASSES
                )
            )
            if supervisor_incident != (
                status == "stopped_supervisor_incident"
            ):
                raise RuntimeError(
                    "Production terminal incident classification changed"
                )
        elif status == "stopped_supervisor_incident":
            raise RuntimeError(
                "Production supervisor receipt has no execution incident"
            )
        if status == "stopped_supervisor_incident":
            # This validates the finite failure class/code and its assignment
            # or clean-boundary relationship without exposing private content.
            _public_supervisor_incident_fields(private)
        else:
            for incident in (execution_incident, codex_auth_incident):
                if incident is None:
                    continue
                assignment_index = (
                    incident.get("assignment_index")
                    if isinstance(incident, Mapping)
                    else None
                )
                if (
                    not isinstance(incident, Mapping)
                    or incident.get("status") != "terminal"
                    or "boundary" in incident
                    or type(assignment_index) is not int
                    or not 0 <= assignment_index < len(assignments)
                    or assignments[assignment_index].get("status")
                    != "transport_void"
                ):
                    raise RuntimeError(
                        "Production transport incident is inconsistent"
                    )
        expected = _public_running(public, private, status=str(status))
        if (
            observed != expected
            or observed.get("scores_reported") is not None
            and observed.get("scores_reported") is not False
        ):
            raise RuntimeError(
                "Authenticated terminal production receipt is inconsistent"
            )
        _assert_exact_public_json_bytes(
            public_output_path,
            expected,
            label="terminal production receipt",
        )
        return {
            "schema_version": "epiagentbench.terminal_receipt_attestation.v1",
            "panel_id": PANEL_ID,
            "operation": operation,
            "status": "attested",
            "terminal_status": str(status),
            "terminal_assignments": int(observed["terminal_assignments"]),
            "provider_processes_started": 0,
            "model_calls_started": 0,
        }


def reconcile_terminal_receipt(
    *,
    root: Path,
    operation: str,
    authentication_key_file: Path,
    private_state_path: Path,
    public_manifest_path: Path,
    public_output_path: Path,
) -> dict[str, Any]:
    """Publish only a durable authenticated terminal candidate, provider-free.

    This is the recovery path for a crash after private terminal state became
    durable but before its trace-free public receipt was written.  It never
    resumes an evaluator and never replaces a conflicting preflight receipt.
    """

    if operation not in {"preflight", "production"}:
        raise ValueError("Terminal receipt operation is invalid")
    assert_durable_live_execution_paths(
        root=root, private_state_path=private_state_path
    )
    authentication_key = _read_authentication_key(
        _existing_path_without_final_symlink(authentication_key_file)
    )
    with _exclusive_run_lock(private_state_path):
        private = _load_private_state(private_state_path, authentication_key)
        public = _load_json(public_manifest_path)
        _validate_public_hash(public)
        _assert_private_public_panel_binding(private, public)
        _assert_canonical_public_output_path(
            public_manifest_path,
            public_output_path,
            operation=operation,
        )

        if operation == "preflight":
            preflight, candidate = _terminal_preflight_candidate(
                private,
                public,
            )
            binding = _validate_repository_receipt_binding(
                preflight.get("public_receipt_binding"),
                root=root,
                path=public_output_path,
                artifact_kind="preflight",
                content_sha256=str(preflight["public_receipt_sha256"]),
                payload=candidate,
                require_published_commit=False,
            )
            if public_output_path.exists() or public_output_path.is_symlink():
                if _load_json(public_output_path) != candidate:
                    raise RuntimeError(
                        "Refusing to replace a conflicting terminal receipt"
                    )
                _assert_exact_public_json_bytes(
                    public_output_path,
                    candidate,
                    label="terminal preflight receipt",
                )
            else:
                _create_public_json_once(public_output_path, candidate)
            if _load_json(public_output_path) != candidate:
                raise RuntimeError(
                    "Terminal preflight receipt failed durable reload"
                )
            observed_file_sha256 = _assert_exact_public_json_bytes(
                public_output_path,
                candidate,
                label="terminal preflight receipt",
            )
            if not hmac.compare_digest(
                observed_file_sha256,
                str(binding["file_sha256"]),
            ):
                raise RuntimeError(
                    "Terminal preflight receipt bytes changed"
                )
            return {
                "schema_version": (
                    "epiagentbench.terminal_receipt_reconciliation.v1"
                ),
                "panel_id": PANEL_ID,
                "operation": operation,
                "status": "reconciled",
                "terminal_status": str(candidate["status"]),
                "file_sha256": str(binding["file_sha256"]),
                "provider_processes_started": 0,
                "model_calls_started": 0,
            }

        candidate = _reconcile_terminal_incident_public_progress(
            root=root,
            public_manifest=public,
            private=private,
            public_results_path=public_output_path,
        )
        _assert_exact_public_json_bytes(
            public_output_path,
            candidate,
            label="terminal production receipt",
        )
        return {
            "schema_version": (
                "epiagentbench.terminal_receipt_reconciliation.v1"
            ),
            "panel_id": PANEL_ID,
            "operation": operation,
            "status": "reconciled",
            "terminal_status": str(candidate["status"]),
            "terminal_assignments": int(candidate["terminal_assignments"]),
            "provider_processes_started": 0,
            "model_calls_started": 0,
        }


def attest_provider_free_prelaunch(
    *,
    root: Path,
    operation: str,
    public_manifest_path: Path,
) -> dict[str, Any]:
    """Recheck executable/runtime plumbing before the durable start marker."""

    if operation not in {"preflight", "production"}:
        raise ValueError("Provider-free prelaunch operation is invalid")
    public = _load_json(public_manifest_path)
    _validate_public_hash(public)
    _attest_execution_contracts(root=root, public=public)
    hashes = public.get("contract_hashes")
    if not isinstance(hashes, Mapping):
        raise ValueError("Provider-free prelaunch contract is invalid")
    return {
        "schema_version": "epiagentbench.provider_free_prelaunch.v1",
        "panel_id": PANEL_ID,
        "operation": operation,
        "status": "passed",
        "source_sha256": hashes["source_sha256"],
        "cli_sha256": hashes["cli_sha256"],
        "runtime_sha256": hashes["runtime_sha256"],
        "supervisor_sha256": hashes["supervisor_sha256"],
        "provider_processes_started": 0,
        "model_calls_started": 0,
    }


def _assert_environment_preflight(
    root: Path,
    private: Mapping[str, Any],
    public: Mapping[str, Any],
    *,
    require_published_commit: bool = True,
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
            "preparation_runtime_sha256",
            "replay_sha256",
            "supervisor_sha256",
        )
    }
    private_attempts = (
        preflight.get("attempts") if isinstance(preflight, dict) else None
    )
    authentication_setup = _validate_authentication_setup_state(
        private, public
    )
    expected_authentication_prerequisite = {
        "receipt_sha256": authentication_setup.get("public_receipt_sha256"),
        "codex": "passed_before_preflight",
        "managed_glean": "passed_before_preflight",
        "model_calls": 0,
    }

    if (
        not isinstance(preflight, dict)
        or authentication_setup.get("status") != "passed"
        or not isinstance(
            authentication_setup.get("public_receipt_sha256"), str
        )
        or preflight.get("status") != "passed"
        or preflight.get("passed_contract_hashes") != expected
        or preflight.get("authentication_prerequisite")
        != expected_authentication_prerequisite
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
            or _durable_model_invocation_state(attempt) != "finished"
            for attempt in private_attempts
        )
    ):
        raise RuntimeError(
            "A disposable six-profile environment preflight bound to the current "
            "contracts must pass before any production episode is launched"
        )
    binding = preflight.get("public_receipt_binding")
    receipt_path = _receipt_path_from_binding(
        root, binding, artifact_kind="preflight"
    )
    receipt = _load_json(receipt_path)
    profile_receipts = receipt.get("profiles")

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
            and item.get("model_invocation_state") == "finished"
            and item.get("outcome") == "passed"
            and item.get("timed_out") is False
            and item.get("timeout_stage") is None
            and item.get("conservative_chargeable") is True
            and item.get("failure_reason") is None
            and "cli_version" not in item
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
        or receipt.get("authentication_prerequisite")
        != expected_authentication_prerequisite
        or receipt.get("codex_auth_quarantine") != "clear"
        or receipt.get("preflight_purpose")
        != "unscored_infrastructure_routing_handshake"
        or receipt.get("failed_model_invocation_state") is not None
        or receipt.get("timeout_stages") != []
        or receipt.get("failed_profile_ids") != []
        or receipt.get("failure_reason") is not None
        or receipt.get("timed_out") is not False
        or receipt.get("model_invocations_conservatively_chargeable")
        != len(PROFILES)
        or not exact_profile_receipts
        or receipt.get("profiles_passed") != profile_receipts
        or receipt.get("contract_hashes") != expected
        or receipt.get("precommitment_sha256")
        != public.get("precommitment_sha256")
        or preflight.get("public_receipt_sha256") != _component_hash(receipt)
    ):
        raise RuntimeError("The committed environment preflight receipt is invalid")
    _validate_repository_receipt_binding(
        binding,
        root=root,
        path=receipt_path,
        artifact_kind="preflight",
        content_sha256=str(preflight["public_receipt_sha256"]),
        payload=receipt,
        require_published_commit=require_published_commit,
    )


def _durable_model_invocation_state(marker: Mapping[str, Any]) -> str:
    """Project the durable model-spawn marker onto a finite public state."""

    invocation = marker.get("model_invocation")
    if invocation is None:
        return "not_started"
    if not isinstance(invocation, dict):
        raise RuntimeError("Model invocation marker is invalid")
    status = invocation.get("status")
    started_at = invocation.get("started_at_utc")
    if not isinstance(started_at, str) or not started_at:
        raise RuntimeError("Model invocation marker is invalid")
    if status == "started" and set(invocation) == {
        "status",
        "started_at_utc",
    }:
        return "started_not_finished"
    if (
        status == "finished"
        and set(invocation)
        == {"status", "started_at_utc", "finished_at_utc"}
        and isinstance(invocation.get("finished_at_utc"), str)
        and bool(invocation["finished_at_utc"])
    ):
        return "finished"
    raise RuntimeError("Model invocation marker is invalid")


def _codex_auth_incident_is_valid(
    incident: Any,
    assignments: Any,
) -> bool:
    """Validate that a terminal Codex incident crossed its declared boundary."""

    if (
        not isinstance(incident, Mapping)
        or incident.get("status") != "terminal"
        or not isinstance(incident.get("failure_class"), str)
        or not incident["failure_class"]
        or "boundary" in incident
        or type(incident.get("assignment_index")) is not int
        or not isinstance(assignments, list)
    ):
        return False
    assignment_index = int(incident["assignment_index"])
    if not 0 <= assignment_index < len(assignments):
        return False
    assignment = assignments[assignment_index]
    if (
        not isinstance(assignment, Mapping)
        or assignment.get("status") != "transport_void"
    ):
        return False
    profile = _PROFILE_BY_ID.get(str(assignment.get("profile_id")))
    if not isinstance(profile, Mapping) or profile.get("system") != "codex":
        return False
    if incident["failure_class"] == "CodexAuthenticationIncidentError":
        return True
    try:
        return (
            _durable_model_invocation_state(assignment) != "not_started"
        )
    except RuntimeError:
        return False


def _conservatively_chargeable_provider_calls(
    attempts: Sequence[Mapping[str, Any]],
) -> int:
    return sum(
        _durable_model_invocation_state(attempt) != "not_started"
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
    model_invocation_state: str,
    outcome: str,
    timed_out: bool,
    timeout_stage: str | None,
) -> dict[str, Any]:
    if model_invocation_state not in {
        "not_started",
        "started_not_finished",
        "finished",
    }:
        raise RuntimeError("Invalid preflight model invocation state")
    if outcome not in {
        "passed",
        "failed_timeout",
        "failed_provider",
        "failed_provider_cli_readiness_timeout",
        "skipped_dependency",
        "terminal_abort",
        "not_started_terminal_abort",
    }:
        raise RuntimeError("Invalid preflight profile outcome")
    if type(timed_out) is not bool:
        raise RuntimeError("Invalid preflight timeout outcome")
    if timeout_stage not in {None, "provider_cli_readiness", "model_invocation"}:
        raise RuntimeError("Invalid preflight timeout stage")
    if timed_out is not (timeout_stage is not None):
        raise RuntimeError("Preflight timeout flag and stage disagree")
    chargeable = model_invocation_state != "not_started"
    return {
        "profile_id": profile["profile_id"],
        "system": profile["system"],
        "requested_model": profile["requested_model"],
        "requested_reasoning": profile["requested_reasoning"],
        "model_invocation_state": model_invocation_state,
        "outcome": outcome,
        "timed_out": timed_out,
        "timeout_stage": timeout_stage,
        "conservative_chargeable": chargeable,
    }


def _persistent_attestation_error(
    failure_code: str,
) -> ProviderExecutionIsolationError:
    if failure_code not in _PERSISTENT_ATTESTATION_FAILURE_CODES:
        failure_code = "attestation_internal"
    message = {
        "supervisor_required": "A live persistent supervisor is required",
        "runtime_replacement": (
            "Persistent-supervisor runtime replacement was refused"
        ),
    }.get(failure_code, "Live persistent-supervisor attestation failed")
    error = ProviderExecutionIsolationError(
        message
    )
    error.attestation_failure_code = failure_code
    return error


def _attestation_incident_fields(error: BaseException) -> dict[str, str]:
    failure_code = getattr(error, "attestation_failure_code", None)
    if (
        not isinstance(error, ProviderExecutionIsolationError)
        or failure_code not in _PERSISTENT_ATTESTATION_FAILURE_CODES
    ):
        return {}
    return {"attestation_failure_code": str(failure_code)}


def _provider_incident_code(
    error: BaseException,
    *,
    fallback: str,
) -> str:
    """Project an exception onto one finite, content-free incident code."""

    if fallback not in _PROVIDER_INCIDENT_CODES:
        fallback = "unexpected_control_path_failure"
    trusted_types = (
        (
            ProviderAttemptPersistenceError,
            "provider_attempt_marker_persist_failed",
        ),
        (
            ProviderCLIReadinessTimeoutError,
            "provider_cli_readiness_timeout",
        ),
        (
            ProviderCompletionPersistenceError,
            "provider_completion_marker_persist_failed",
        ),
        (
            ProviderInvocationPersistenceError,
            "model_invocation_marker_persist_failed",
        ),
        (
            ProviderProgressPersistenceError,
            "provider_progress_checkpoint_persist_failed",
        ),
        (
            ProviderQuarantinePersistenceError,
            "provider_quarantine_checkpoint_persist_failed",
        ),
        (
            ProviderResultCheckpointPersistenceError,
            "provider_result_checkpoint_persist_failed",
        ),
        (ProviderSpawnIsolationError, "provider_spawn_failed"),
        (ProviderOutputIsolationError, "provider_output_isolation_failed"),
        (ProviderProcessIsolationError, "provider_process_isolation_failed"),
        (ProviderStateIsolationError, "provider_state_isolation_failed"),
        (
            ProviderExecutionIsolationError,
            "provider_execution_isolation_failed",
        ),
    )
    for error_type, code in trusted_types:
        if isinstance(error, error_type):
            return code
    return fallback


def _provider_failure_stage(error: BaseException, *, fallback: str) -> str:
    """Project an exception onto a finite, content-free failure stage."""

    if isinstance(error, ProviderCLIReadinessTimeoutError):
        return "provider_cli_readiness"
    if fallback not in _PREFLIGHT_FAILURE_STAGES:
        return "provider_execution"
    return fallback


def _provider_timeout_stage(
    error: BaseException,
    *,
    result: PilotRunResult | None,
) -> str | None:
    """Distinguish model timeouts from non-model CLI readiness timeouts."""

    if isinstance(error, ProviderCLIReadinessTimeoutError):
        return "provider_cli_readiness"
    if result is not None and _result_timed_out(result):
        return "model_invocation"
    return None


def _attest_with_transient_snapshot_retry(
    attestation: Callable[[], Any],
    *,
    invariant: Callable[[], bool] | None = None,
) -> Any:
    """Retry only an authenticated torn snapshot, never a provider call."""

    deadline = time.monotonic() + _SNAPSHOT_ATTESTATION_DEADLINE_SECONDS
    retry_delays = _SNAPSHOT_ATTESTATION_RETRY_DELAYS_SECONDS
    for attempt in range(len(retry_delays) + 1):
        if invariant is not None and invariant() is not True:
            raise _persistent_attestation_error("private_binding_invalid")
        try:
            return attestation()
        except ProviderExecutionIsolationError as error:
            if (
                getattr(error, "attestation_failure_code", None)
                != "status_snapshot_unstable"
                or attempt == len(retry_delays)
            ):
                raise
            delay = retry_delays[attempt]
            if time.monotonic() + delay > deadline:
                raise
            time.sleep(delay)
            if time.monotonic() > deadline:
                raise
    raise AssertionError("Snapshot-attestation retry loop escaped")


def _attest_required_persistent_execution(
    *,
    required: bool,
    supervisor_runtime_dir: Path | None,
    authentication_key_file: Path,
    operation: str,
    public_manifest: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Require a live, manifest-bound supervisor before a live CLI run."""

    if type(required) is not bool:
        raise ValueError("Persistent-supervisor requirement must be boolean")
    if not required:
        if supervisor_runtime_dir is not None:
            raise ValueError(
                "A supervisor runtime may be supplied only when attestation is required"
            )
        return None
    if supervisor_runtime_dir is None or operation not in {"preflight", "production"}:
        raise _persistent_attestation_error("supervisor_required")
    if public_manifest.get("persistent_supervisor_contract") != (
        _persistent_supervisor_contract()
    ):
        raise _persistent_attestation_error("public_contract_mismatch")
    panel_id = public_manifest.get("panel_id")
    precommitment = public_manifest.get("precommitment_sha256")
    if panel_id != PANEL_ID or not isinstance(precommitment, str):
        raise _persistent_attestation_error("public_binding_invalid")
    try:
        from .launchd_agent import (
            LiveAttestationError,
            attest_live_launch_agent,
        )
    except Exception:
        raise _persistent_attestation_error("attestation_internal") from None
    try:
        attestation = attest_live_launch_agent(
            supervisor_runtime_dir,
            authentication_key_file=authentication_key_file,
            expected_operation=operation,
            expected_panel_id=PANEL_ID,
            expected_precommitment_sha256=precommitment,
        )
    except LiveAttestationError as error:
        raise _persistent_attestation_error(
            str(error.failure_code)
        ) from None
    except Exception:
        raise _persistent_attestation_error("attestation_internal") from None
    return _normalized_supervisor_binding(
        attestation,
        operation=operation,
        public_manifest=public_manifest,
    )


def _normalized_supervisor_binding(
    attestation: Mapping[str, Any],
    *,
    operation: str,
    public_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Project one live/terminal attestation onto an immutable private key."""

    panel_id = public_manifest.get("panel_id")
    precommitment = public_manifest.get("precommitment_sha256")
    label = attestation.get("label") if isinstance(attestation, Mapping) else None
    context = (
        attestation.get("execution_context_sha256")
        if isinstance(attestation, Mapping)
        else None
    )
    config_file_sha256 = (
        attestation.get("config_file_sha256")
        if isinstance(attestation, Mapping)
        else None
    )
    if (
        operation not in {"preflight", "production"}
        or panel_id != PANEL_ID
        or not isinstance(precommitment, str)
        or not precommitment.startswith("sha256:")
        or len(precommitment) != 71
        or not isinstance(label, str)
        or not label
        or len(label) > 255
        or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.@+-" for character in label)
        or not isinstance(context, str)
        or not context.startswith("sha256:")
        or len(context) != 71
        or not isinstance(config_file_sha256, str)
        or not config_file_sha256.startswith("sha256:")
        or len(config_file_sha256) != 71
    ):
        raise _persistent_attestation_error("binding_projection_invalid")
    binding = {
        "operation": operation,
        "label": label,
        "execution_context_sha256": context,
        "config_file_sha256": config_file_sha256,
        "panel_id": PANEL_ID,
        "precommitment_sha256": precommitment,
    }
    if set(binding) != _SUPERVISOR_BINDING_FIELDS:
        raise AssertionError("Persistent-supervisor binding schema drifted")
    return binding


def _claim_persistent_execution_binding(
    private: dict[str, Any],
    *,
    operation: str,
    binding: Mapping[str, Any] | None,
) -> bool:
    """Create one immutable operation binding; return whether it was created."""

    if binding is None:
        return False
    normalized = dict(binding)
    if set(normalized) != _SUPERVISOR_BINDING_FIELDS:
        raise _persistent_attestation_error("private_binding_invalid")
    bindings = private.get(_PERSISTENT_EXECUTION_BINDINGS_KEY)
    if bindings is None:
        bindings = {}
        private[_PERSISTENT_EXECUTION_BINDINGS_KEY] = bindings
    if not isinstance(bindings, dict) or any(
        name not in {"preflight", "production"} for name in bindings
    ):
        raise _persistent_attestation_error("private_binding_invalid")
    existing = bindings.get(operation)
    if existing is None:
        bindings[operation] = normalized
        return True
    if not isinstance(existing, Mapping) or not hmac.compare_digest(
        _canonical_bytes(dict(existing)), _canonical_bytes(normalized)
    ):
        raise _persistent_attestation_error("runtime_replacement")
    return False


def _attest_and_match_persistent_execution(
    *,
    required: bool,
    supervisor_runtime_dir: Path | None,
    authentication_key_file: Path,
    operation: str,
    public_manifest: Mapping[str, Any],
    private: dict[str, Any],
) -> tuple[dict[str, Any] | None, bool]:
    binding = _attest_required_persistent_execution(
        required=required,
        supervisor_runtime_dir=supervisor_runtime_dir,
        authentication_key_file=authentication_key_file,
        operation=operation,
        public_manifest=public_manifest,
    )
    created = _claim_persistent_execution_binding(
        private,
        operation=operation,
        binding=binding,
    )
    return binding, created


def _execution_evaluator(
    *,
    require_persistent_supervisor: bool,
    offline_test_evaluator: Callable[..., PilotRunResult] | None,
) -> Callable[..., PilotRunResult]:
    """Select the live evaluator only under supervision.

    Unsupervised execution is intentionally available only to private
    deterministic test seams that explicitly inject an offline fake.
    """

    if type(require_persistent_supervisor) is not bool:
        raise ValueError("Persistent-supervisor requirement must be boolean")
    if require_persistent_supervisor:
        if offline_test_evaluator is not None:
            raise ValueError(
                "An offline test evaluator cannot be used by a live supervised run"
            )
        return evaluate_local_cli_agent
    if offline_test_evaluator is None or not callable(offline_test_evaluator):
        raise ProviderExecutionIsolationError(
            "Unsupervised execution requires an explicitly injected offline test evaluator"
        )
    return offline_test_evaluator


def _run_environment_preflight_core(
    *,
    root: Path,
    authentication_key_file: Path,
    claude_secure_storage_dir: Path,
    codex_secure_storage_dir: Path,
    private_state_path: Path,
    public_manifest_path: Path,
    public_preflight_path: Path,
    supervisor_runtime_dir: Path | None = None,
    require_persistent_supervisor: bool = True,
    offline_test_evaluator: Callable[..., PilotRunResult] | None = None,
    acknowledge_unbounded_provider_spend: bool = False,
) -> dict[str, Any]:
    """Exercise every provider profile on one disposable, unscored episode."""

    if acknowledge_unbounded_provider_spend is not True:
        raise RuntimeError(
            "Explicit acknowledgement of unbounded preflight provider spend is required"
        )
    if require_persistent_supervisor:
        _assert_canonical_public_output_path(
            public_manifest_path,
            public_preflight_path,
            operation="preflight",
        )
    evaluator = _execution_evaluator(
        require_persistent_supervisor=require_persistent_supervisor,
        offline_test_evaluator=offline_test_evaluator,
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
    if not os.environ.get("CURSOR_API_KEY", "").strip():
        raise RuntimeError(
            "Disposable six-profile preflight requires CURSOR_API_KEY before "
            "any provider call"
        )
    with _exclusive_run_lock(private_state_path):
        authentication_key = _read_authentication_key(
            _existing_path_without_final_symlink(authentication_key_file)
        )
        private = _load_private_state(private_state_path, authentication_key)
        public = _load_json(public_manifest_path)
        _validate_public_hash(public)
        authentication_receipt = assert_panel_authentication_ready(
            root=root,
            authentication_key_file=authentication_key_file,
            claude_secure_storage_dir=resolved_claude_secure_storage_dir,
            codex_secure_storage_dir=resolved_codex_secure_storage_dir,
            private_state_path=private_state_path,
            public_manifest_path=public_manifest_path,
            require_clean_checkout=require_persistent_supervisor,
            revalidate_live_identity_contracts=False,
        )
        _, binding_created = _attest_with_transient_snapshot_retry(
            lambda: _attest_and_match_persistent_execution(
                required=require_persistent_supervisor,
                supervisor_runtime_dir=supervisor_runtime_dir,
                authentication_key_file=authentication_key_file,
                operation="preflight",
                public_manifest=public,
                private=private,
            )
        )
        if binding_created:
            # Authentication is already sealed and committed.  The exact
            # label/context is now burned before any model-bearing call.
            _write_private_state(private_state_path, private, authentication_key)

        def attest_current_supervisor() -> None:
            _attest_and_match_persistent_execution(
                required=require_persistent_supervisor,
                supervisor_runtime_dir=supervisor_runtime_dir,
                authentication_key_file=authentication_key_file,
                operation="preflight",
                public_manifest=public,
                private=private,
            )
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
            managed_glean_credentials_present=True,
        )
        _require_codex_credential_state(
            resolved_codex_secure_storage_dir,
            root=root,
            expected_identity=codex_secure_storage_identity,
            credentials_present=True,
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
            managed_glean_credentials_present=True,
        )
        _require_codex_credential_state(
            resolved_codex_secure_storage_dir,
            root=root,
            expected_identity=codex_secure_storage_identity,
            credentials_present=True,
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
                "preparation_runtime_sha256",
                "replay_sha256",
                "supervisor_sha256",
            )
        }
        timeout = int(public["timeout_contract"]["seconds_per_assignment"])
        claude_glean_oauth_client_id = _glean_claude_oauth_client_id()
        codex_auth_file_identity = _private_codex_auth_file_identity(private)
        managed_glean_auth_file_identity = private.get(
            "managed_glean_auth_file_identity"
        )
        if not isinstance(managed_glean_auth_file_identity, Mapping):
            raise RuntimeError(
                "Managed Glean credential identity is unavailable"
            )
        budget = float(
            public["budget_contract"]["claude_max_budget_usd_per_assignment"]
        )
        attempts: list[dict[str, Any]] = []
        private["environment_preflight"] = {
            "status": "running",
            "started_at_utc": _utc_now(),
            "attempts": attempts,
            "required_contract_hashes": contract_hashes,
            "authentication_prerequisite": {
                "receipt_sha256": authentication_receipt["receipt_sha256"],
                "codex": "passed_before_preflight",
                "managed_glean": "passed_before_preflight",
                "model_calls": 0,
            },
            "codex_auth_quarantine": {"status": "clear"},
        }
        _write_private_state(private_state_path, private, authentication_key)
        public_attempts: list[dict[str, Any]] = []

        def attest_preflight_supervisor_boundary() -> None:
            expected_attempt_count = len(attempts)
            _attest_with_transient_snapshot_retry(
                attest_current_supervisor,
                invariant=lambda: len(attempts) == expected_attempt_count,
            )

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
                    model_invocation_state="not_started",
                    outcome="skipped_dependency",
                    timed_out=False,
                    timeout_stage=None,
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
            attempt_index = len(attempts)
            attempts.append(marker)
            failure_stage = "durable_attempt_marker"
            incident_code = "provider_attempt_marker_persist_failed"
            result: PilotRunResult | None = None
            try:
                try:
                    _write_private_state(
                        private_state_path, private, authentication_key
                    )
                except Exception:
                    raise ProviderAttemptPersistenceError(
                        "Provider attempt marker could not be persisted"
                    ) from None
                managed_glean_state_before: str | None = None
                codex_credentials_state_before: str | None = None
                if profile["system"] == "claude":
                    failure_stage = "credential_attestation"
                    incident_code = "credential_attestation_failed"
                    _require_claude_credential_state(
                        resolved_claude_secure_storage_dir,
                        root=root,
                        expected_identity=claude_secure_storage_identity,
                        managed_glean_credentials_present=True,
                    )
                    _require_managed_glean_auth_file_identity(
                        resolved_claude_secure_storage_dir,
                        managed_glean_auth_file_identity,
                    )
                    managed_glean_state_before = "present"
                    failure_stage = "provider_execution"
                    incident_code = "provider_adapter_execution_failed"
                if profile["system"] == "codex":
                    failure_stage = "credential_attestation"
                    incident_code = "credential_attestation_failed"
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
                    failure_stage = "provider_execution"
                    incident_code = "provider_adapter_execution_failed"
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
                failure_stage = "supervisor_attestation_before_harness"
                incident_code = "supervisor_boundary_attestation_failed"
                attest_preflight_supervisor_boundary()
                failure_stage = "execution_contract_before_harness"
                _attest_execution_contracts(root=root, public=public)
                failure_stage = "glean_dependency_before_harness"
                _attest_frozen_glean_auth_dependencies(private, public)

                def persist_model_invocation_start() -> None:
                    nonlocal failure_stage, incident_code
                    failure_stage = "model_invocation_marker"
                    incident_code = (
                        "model_invocation_marker_persist_failed"
                    )
                    if "model_invocation" in marker:
                        raise ProviderStateIsolationError(
                            "Model invocation marker transition is invalid"
                        )
                    marker["model_invocation"] = {
                        "status": "started",
                        "started_at_utc": _utc_now(),
                    }
                    try:
                        _write_private_state(
                            private_state_path,
                            private,
                            authentication_key,
                        )
                    except Exception:
                        raise ProviderInvocationPersistenceError(
                            "Model invocation marker could not be persisted"
                        ) from None
                    failure_stage = "provider_execution"
                    incident_code = "provider_adapter_execution_failed"

                def persist_progress(snapshot: Mapping[str, Any]) -> None:
                    nonlocal failure_stage, incident_code
                    failure_stage = "provider_progress_checkpoint"
                    incident_code = (
                        "provider_progress_checkpoint_persist_failed"
                    )
                    try:
                        marker["progress_telemetry"] = (
                            _safe_live_provider_progress(snapshot)
                        )
                        _write_private_state(
                            private_state_path,
                            private,
                            authentication_key,
                        )
                    except ProviderProgressPersistenceError:
                        raise
                    except Exception:
                        raise ProviderProgressPersistenceError(
                            "Provider progress checkpoint could not be persisted"
                        ) from None
                    failure_stage = "provider_execution"
                    incident_code = "provider_adapter_execution_failed"

                failure_stage = "provider_execution"
                incident_code = "provider_adapter_execution_failed"
                result = evaluator(
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
                    model_invocation_start_callback=(
                        persist_model_invocation_start
                    ),
                    **provider_auth_kwargs,
                )
                failure_stage = "provider_completion_marker"
                incident_code = "provider_completion_marker_persist_failed"
                invocation = marker.get("model_invocation")
                if (
                    not isinstance(invocation, dict)
                    or invocation.get("status") != "started"
                ):
                    raise ProviderStateIsolationError(
                        "Model invocation start marker is unavailable"
                    )
                marker["model_invocation"] = {
                    **invocation,
                    "status": "finished",
                    "finished_at_utc": _utc_now(),
                }
                try:
                    _write_private_state(
                        private_state_path, private, authentication_key
                    )
                except Exception:
                    raise ProviderCompletionPersistenceError(
                        "Provider completion marker could not be persisted"
                    ) from None
                failure_stage = "supervisor_attestation_after_harness"
                incident_code = "supervisor_boundary_attestation_failed"
                attest_preflight_supervisor_boundary()
                failure_stage = "execution_contract_after_harness"
                _attest_execution_contracts(root=root, public=public)
                failure_stage = "glean_dependency_after_harness"
                _attest_frozen_glean_auth_dependencies(private, public)
                if profile["system"] == "claude":
                    failure_stage = "credential_attestation"
                    incident_code = "credential_attestation_failed"
                    _require_claude_credential_state(
                        resolved_claude_secure_storage_dir,
                        root=root,
                        expected_identity=claude_secure_storage_identity,
                        managed_glean_credentials_present=True,
                    )
                    _require_managed_glean_auth_file_identity(
                        resolved_claude_secure_storage_dir,
                        managed_glean_auth_file_identity,
                    )
                if profile["system"] == "codex":
                    failure_stage = "credential_attestation"
                    incident_code = "credential_attestation_failed"
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
                incident_code = "evaluator_return_contract_failed"
                if (
                    result.system != profile["system"]
                    or result.requested_model != profile["requested_model"]
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
                incident_code = "provider_result_processing_failed"
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
                incident_code = "provider_result_processing_failed"
                if timed_out:
                    ordinary_failure_reason = "timeout"
                elif result.returncode != 0 and ordinary_failure_reason is None:
                    ordinary_failure_reason = "nonzero_exit"
                elif receipt_required and not receipt_ok:
                    ordinary_failure_reason = "model_receipt_failure"
                raw_hash = _component_hash(asdict(result))
                if timed_out and profile["system"] == "codex":
                    failure_stage = "codex_quarantine_checkpoint"
                    incident_code = (
                        "provider_quarantine_checkpoint_persist_failed"
                    )
                    private["environment_preflight"][
                        "codex_auth_quarantine"
                    ] = {
                        "status": "quarantined",
                        "reason": "cleanly_quiesced_timeout",
                        "profile_id": profile_id,
                        "quarantined_at_utc": _utc_now(),
                    }
                    try:
                        _write_private_state(
                            private_state_path,
                            private,
                            authentication_key,
                        )
                    except Exception:
                        raise ProviderQuarantinePersistenceError(
                            "Provider quarantine checkpoint could not be persisted"
                        ) from None
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
                    model_invocation_state="finished",
                    outcome=(
                        "passed"
                        if passed
                        else "failed_timeout"
                        if timed_out
                        else "failed_provider"
                    ),
                    timed_out=timed_out,
                    timeout_stage=(
                        "model_invocation" if timed_out else None
                    ),
                )
                public_attempt.update(
                    {
                        "observed_models": list(result.observed_models),
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
                failure_stage = "provider_result_checkpoint"
                incident_code = (
                    "provider_result_checkpoint_persist_failed"
                )
                try:
                    _write_private_state(
                        private_state_path, private, authentication_key
                    )
                except Exception:
                    raise ProviderResultCheckpointPersistenceError(
                        "Provider result checkpoint could not be persisted"
                    ) from None
                public_attempts.append(public_attempt)
            except Exception as error:
                # Durable state, not the mutated in-memory marker, is the sole
                # authority for chargeability and finished-vs-ambiguous state.
                durable_private = _load_private_state(
                    private_state_path, authentication_key
                )
                durable_preflight = durable_private.get(
                    "environment_preflight"
                )
                durable_attempts = (
                    durable_preflight.get("attempts")
                    if isinstance(durable_preflight, dict)
                    else None
                )
                if (
                    not isinstance(durable_attempts, list)
                    or len(durable_attempts) not in {
                        attempt_index,
                        attempt_index + 1,
                    }
                ):
                    raise ProviderStateIsolationError(
                        "Durable preflight attempt state changed"
                    ) from None
                if len(durable_attempts) == attempt_index:
                    durable_marker = {
                        "profile_id": profile_id,
                        "status": "started",
                        "started_at_utc": marker["started_at_utc"],
                    }
                    durable_attempts.append(durable_marker)
                else:
                    observed_marker = durable_attempts[attempt_index]
                    if (
                        not isinstance(observed_marker, dict)
                        or observed_marker.get("profile_id") != profile_id
                    ):
                        raise ProviderStateIsolationError(
                            "Durable preflight attempt state changed"
                        ) from None
                    durable_marker = observed_marker
                private = durable_private
                attempts = durable_attempts
                marker = durable_marker
                if isinstance(
                    error, ProviderQuarantinePersistenceError
                ):
                    private["environment_preflight"][
                        "codex_auth_quarantine"
                    ] = {
                        "status": "quarantined",
                        "reason": (
                            "quarantine_checkpoint_persist_failed"
                        ),
                        "profile_id": profile_id,
                        "quarantined_at_utc": _utc_now(),
                    }
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
                        "failure_stage": _provider_failure_stage(
                            error, fallback=failure_stage
                        ),
                        "incident_code": _provider_incident_code(
                            error, fallback=incident_code
                        ),
                        **_attestation_incident_fields(error),
                    }
                )
                model_invocation_state = (
                    _durable_model_invocation_state(marker)
                )
                timeout_stage = _provider_timeout_stage(
                    error, result=result
                )
                timed_out = timeout_stage is not None
                terminal_failure_stage = _provider_failure_stage(
                    error, fallback=failure_stage
                )
                terminal_incident_code = _provider_incident_code(
                    error, fallback=incident_code
                )
                readiness_timeout = isinstance(
                    error, ProviderCLIReadinessTimeoutError
                )
                failure_reason = (
                    "provider_cli_readiness_timeout"
                    if readiness_timeout
                    else "terminal_abort"
                )
                terminal_outcome = _preflight_profile_outcome(
                    profile,
                    model_invocation_state=model_invocation_state,
                    outcome=(
                        "failed_provider_cli_readiness_timeout"
                        if readiness_timeout
                        else "terminal_abort"
                    ),
                    timed_out=timed_out,
                    timeout_stage=timeout_stage,
                )
                terminal_outcome.update(
                    {
                        "failure_reason": failure_reason,
                        "failure_stage": terminal_failure_stage,
                        "incident_code": terminal_incident_code,
                        **_attestation_incident_fields(error),
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
                        model_invocation_state="not_started",
                        outcome="not_started_terminal_abort",
                        timed_out=False,
                        timeout_stage=None,
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
                    "authentication_prerequisite": private[
                        "environment_preflight"
                    ]["authentication_prerequisite"],
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
                    "failed_model_invocation_state": (
                        model_invocation_state
                    ),
                    "model_invocations_conservatively_chargeable": (
                        _conservatively_chargeable_provider_calls(attempts)
                    ),
                    "failure_reason": failure_reason,
                    "failure_stage": terminal_failure_stage,
                    "incident_code": terminal_incident_code,
                    **_attestation_incident_fields(error),
                    "timed_out": timed_out,
                    "timeout_stages": (
                        [timeout_stage] if timeout_stage is not None else []
                    ),
                    "scores_reported": False,
                }
                private["environment_preflight"] = {
                    **private["environment_preflight"],
                    "status": "failed",
                    "finished_at_utc": _utc_now(),
                    "terminal_public_receipt": failed,
                    "public_receipt_binding": _repository_receipt_binding(
                        root=root,
                        path=public_preflight_path,
                        artifact_kind="preflight",
                        content_sha256=_component_hash(failed),
                        payload=failed,
                    ),
                    "public_receipt_sha256": _component_hash(failed),
                }
                _write_private_state(private_state_path, private, authentication_key)
                _atomic_json(public_preflight_path, failed)
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
            "authentication_prerequisite": private[
                "environment_preflight"
            ]["authentication_prerequisite"],
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
            "failed_model_invocation_state": (
                profile_failures[0]["model_invocation_state"]
                if profile_failures
                else None
            ),
            "model_invocations_conservatively_chargeable": (
                _conservatively_chargeable_provider_calls(attempts)
            ),
            "failure_reason": (
                "one_or_more_profile_failures" if profile_failures else None
            ),
            "timed_out": any(item["timed_out"] for item in profile_failures),
            "timeout_stages": sorted(
                {
                    str(item["timeout_stage"])
                    for item in profile_failures
                    if item["timeout_stage"] is not None
                }
            ),
            "scores_reported": False,
            "completed_at_utc": _utc_now(),
        }
        if profile_failures:
            private["environment_preflight"] = {
                **private["environment_preflight"],
                "status": "failed",
                "finished_at_utc": receipt["completed_at_utc"],
                "terminal_public_receipt": receipt,
                "public_receipt_binding": _repository_receipt_binding(
                    root=root,
                    path=public_preflight_path,
                    artifact_kind="preflight",
                    content_sha256=_component_hash(receipt),
                    payload=receipt,
                ),
                "public_receipt_sha256": _component_hash(receipt),
            }
            # The authenticated terminal candidate is always durable before
            # the public receipt.  A public-write failure can therefore be
            # reconciled without another provider invocation.
            _write_private_state(
                private_state_path, private, authentication_key
            )
            _atomic_json(public_preflight_path, receipt)
            return receipt
        if not profile_failures:
            try:
                attest_preflight_supervisor_boundary()
            except ProviderExecutionIsolationError as error:
                stopped = {
                    "schema_version": SCHEMA_VERSION,
                    "panel_id": PANEL_ID,
                    "status": "stopped_supervisor_incident",
                    "development_only": True,
                    "production_episodes_consumed": 0,
                    "precommitment_sha256": public["precommitment_sha256"],
                    "profiles_terminal": len(public_attempts),
                    "model_invocations_conservatively_chargeable": (
                        _conservatively_chargeable_provider_calls(attempts)
                    ),
                    "failure_stage": (
                        "supervisor_attestation_final_completion"
                    ),
                    "incident_code": (
                        "supervisor_boundary_attestation_failed"
                    ),
                    **_attestation_incident_fields(error),
                    "scores_reported": False,
                }
                private["environment_preflight"] = {
                    **private["environment_preflight"],
                    "status": "failed",
                    "finished_at_utc": receipt["completed_at_utc"],
                    "terminal_public_receipt": stopped,
                    "public_receipt_binding": _repository_receipt_binding(
                        root=root,
                        path=public_preflight_path,
                        artifact_kind="preflight",
                        content_sha256=_component_hash(stopped),
                        payload=stopped,
                    ),
                    "public_receipt_sha256": _component_hash(stopped),
                    "supervisor_incident": {
                        "status": "terminal",
                        "failure_class": type(error).__name__,
                        "boundary": "final_completion",
                        "incident_code": (
                            "supervisor_boundary_attestation_failed"
                        ),
                        **_attestation_incident_fields(error),
                    },
                }
                _write_private_state(
                    private_state_path, private, authentication_key
                )
                _atomic_json(public_preflight_path, stopped)
                return stopped
        if not profile_failures and require_persistent_supervisor:
            pending = _public_preflight_pending(public, receipt)
            private["environment_preflight"] = {
                **private["environment_preflight"],
                "status": _PENDING_PREFLIGHT_STATUS,
                "finished_at_utc": receipt["completed_at_utc"],
                "pending_public_receipt": receipt,
                "pending_public_receipt_sha256": _component_hash(receipt),
                _PUBLIC_RELEASE_KEY: {
                    "status": "pending_supervisor_completion",
                    "operation": "preflight",
                },
            }
            private["environment_preflight"][
                "passed_contract_hashes"
            ] = contract_hashes
            # The sealed candidate must be durable before even the trace-free
            # public watermark appears.
            _write_private_state(private_state_path, private, authentication_key)
            _atomic_json(public_preflight_path, pending)
            return pending
        private["environment_preflight"] = {
            **private["environment_preflight"],
            "status": receipt["status"],
            "finished_at_utc": receipt["completed_at_utc"],
            "public_receipt_binding": _repository_receipt_binding(
                root=root,
                path=public_preflight_path,
                artifact_kind="preflight",
                content_sha256=_component_hash(receipt),
                payload=receipt,
            ),
            "public_receipt_sha256": _component_hash(receipt),
        }
        if not profile_failures:
            private["environment_preflight"][
                "passed_contract_hashes"
            ] = contract_hashes
        _write_private_state(private_state_path, private, authentication_key)
        _atomic_json(public_preflight_path, receipt)
        return receipt


def run_environment_preflight(
    *,
    root: Path,
    authentication_key_file: Path,
    claude_secure_storage_dir: Path,
    codex_secure_storage_dir: Path,
    private_state_path: Path,
    public_manifest_path: Path,
    public_preflight_path: Path,
    supervisor_runtime_dir: Path | None = None,
    acknowledge_unbounded_provider_spend: bool = False,
) -> dict[str, Any]:
    """Exercise every provider profile under authenticated supervision.

    The public entry point deliberately exposes neither a supervision switch
    nor an evaluator callback.  Offline fault-injection belongs in the
    private test-only helper below.
    """

    assert_durable_live_execution_paths(
        root=root,
        private_state_path=private_state_path,
    )
    return _run_environment_preflight_core(
        root=root,
        authentication_key_file=authentication_key_file,
        claude_secure_storage_dir=claude_secure_storage_dir,
        codex_secure_storage_dir=codex_secure_storage_dir,
        private_state_path=private_state_path,
        public_manifest_path=public_manifest_path,
        public_preflight_path=public_preflight_path,
        supervisor_runtime_dir=supervisor_runtime_dir,
        require_persistent_supervisor=True,
        offline_test_evaluator=None,
        acknowledge_unbounded_provider_spend=(
            acknowledge_unbounded_provider_spend
        ),
    )


def _run_environment_preflight_for_offline_test(
    *,
    root: Path,
    authentication_key_file: Path,
    claude_secure_storage_dir: Path,
    codex_secure_storage_dir: Path,
    private_state_path: Path,
    public_manifest_path: Path,
    public_preflight_path: Path,
    offline_test_evaluator: Callable[..., PilotRunResult],
    acknowledge_unbounded_provider_spend: bool = False,
) -> dict[str, Any]:
    """Private deterministic seam for unit tests; never a live run path."""

    return _run_environment_preflight_core(
        root=root,
        authentication_key_file=authentication_key_file,
        claude_secure_storage_dir=claude_secure_storage_dir,
        codex_secure_storage_dir=codex_secure_storage_dir,
        private_state_path=private_state_path,
        public_manifest_path=public_manifest_path,
        public_preflight_path=public_preflight_path,
        supervisor_runtime_dir=None,
        require_persistent_supervisor=False,
        offline_test_evaluator=offline_test_evaluator,
        acknowledge_unbounded_provider_spend=(
            acknowledge_unbounded_provider_spend
        ),
    )


def _preflight_execution(
    *,
    root: Path,
    private_state_path: Path,
    public_manifest_path: Path,
    public_results_path: Path,
    allowed_private_artifact_paths: Sequence[Path] = (),
) -> None:
    public_relative = _relative_to_root(public_manifest_path, root)
    try:
        private_relative = _relative_to_root(private_state_path, root)
    except ValueError:
        private_relative = None
    results_relative = _relative_to_root(public_results_path, root)
    if _git_output(root, "ls-files", "--error-unmatch", public_relative) != public_relative:
        raise RuntimeError("Public matched-panel precommitment has not been committed")
    if private_relative is not None and _git_output(
        root, "ls-files", private_relative
    ):
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
    chargeable = _conservatively_chargeable_provider_calls(assignments)
    artifact = {
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
        "model_invocations_conservatively_chargeable": chargeable,
        "results": [],
        "summary": {"primary_estimand": "pending"},
    }
    if status == "stopped_supervisor_incident":
        artifact.update(_public_supervisor_incident_fields(private))
    return artifact


def _public_supervisor_incident_fields(
    private: Mapping[str, Any],
) -> dict[str, str]:
    """Project one private incident onto a finite, trace-free public code."""

    incident = private.get("execution_incident")
    if not isinstance(incident, Mapping) or incident.get("status") != "terminal":
        raise ValueError("Stopped supervisor artifact has no terminal incident")
    failure_class = incident.get("failure_class")
    if failure_class not in _PROVIDER_ISOLATION_FAILURE_CLASSES:
        raise ValueError("Stopped supervisor incident class is invalid")
    assignments = private.get("assignments")
    if not isinstance(assignments, list):
        raise ValueError("Stopped supervisor incident assignments are invalid")
    assignment_index = incident.get("assignment_index")
    boundary = incident.get("boundary")
    failure_code = incident.get("attestation_failure_code")
    incident_code = incident.get("incident_code")
    if (
        incident_code not in _PROVIDER_INCIDENT_CODES
        or
        failure_code is not None
        and failure_code not in _PERSISTENT_ATTESTATION_FAILURE_CODES
    ):
        raise ValueError("Stopped supervisor artifact has an unsafe incident code")
    if boundary == "clean_before_assignment":
        if (
            type(assignment_index) is not int
            or assignment_index != len(assignments)
            or not isinstance(incident.get("profile_id"), str)
        ):
            raise ValueError("Stopped supervisor incident boundary is invalid")
        failure_stage = (
            "supervisor_attestation_before_provider"
            if failure_code is not None
            else "provider_isolation_before_provider"
        )
    elif boundary == "final_completion":
        if (
            type(assignment_index) is not int
            or assignment_index != len(assignments)
        ):
            raise ValueError("Stopped supervisor incident boundary is invalid")
        failure_stage = (
            "supervisor_attestation_final_completion"
            if failure_code is not None
            else "provider_isolation_final_completion"
        )
    else:
        if (
            "boundary" in incident
            or type(assignment_index) is not int
            or not 0 <= assignment_index < len(assignments)
            or assignments[assignment_index].get("status")
            != "transport_void"
        ):
            raise ValueError("Stopped supervisor incident boundary is invalid")
        if failure_code is not None:
            failure_stage = "supervisor_attestation_after_provider"
        else:
            failure_stage = (
                "provider_isolation_before_model_invocation"
                if _durable_model_invocation_state(
                    assignments[assignment_index]
                )
                == "not_started"
                else "provider_isolation_after_model_invocation_start"
            )
    fields = {
        "failure_stage": failure_stage,
        "incident_code": str(incident_code),
    }
    if failure_code is not None:
        fields["attestation_failure_code"] = str(failure_code)
    return fields


def _public_preflight_pending(
    public_manifest: Mapping[str, Any],
    receipt: Mapping[str, Any],
) -> dict[str, Any]:
    profiles = receipt.get("profiles")
    if not isinstance(profiles, list):
        raise ValueError("Pending preflight candidate has no profile matrix")
    chargeable = receipt.get(
        "model_invocations_conservatively_chargeable"
    )
    if type(chargeable) is not int or chargeable < 0:
        raise ValueError(
            "Pending preflight candidate has invalid model-invocation count"
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "panel_id": PANEL_ID,
        "status": _PENDING_PREFLIGHT_STATUS,
        "development_only": True,
        "production_episodes_consumed": 0,
        "precommitment_sha256": public_manifest["precommitment_sha256"],
        "profiles_terminal": len(profiles),
        "model_invocations_conservatively_chargeable": chargeable,
        "scores_reported": False,
        "release_gate": "authenticated_outer_supervisor_completion_required",
    }


def _reconcile_terminal_incident_public_progress(
    *,
    root: Path,
    public_manifest: Mapping[str, Any],
    private: Mapping[str, Any],
    public_results_path: Path,
) -> dict[str, Any]:
    """Repair only a trace-free public watermark after a durable incident."""

    execution_incident = private.get("execution_incident")
    codex_auth_incident = private.get("codex_auth_incident")
    if execution_incident is None and codex_auth_incident is None:
        raise ValueError("No durable terminal incident is available")
    if execution_incident is not None:
        assignments = private.get("assignments")
        assignment_index = (
            execution_incident.get("assignment_index")
            if isinstance(execution_incident, Mapping)
            else None
        )
        if (
            not isinstance(execution_incident, Mapping)
            or execution_incident.get("status") != "terminal"
            or not isinstance(
                execution_incident.get("failure_class"), str
            )
            or not execution_incident["failure_class"]
            or execution_incident.get("incident_code")
            not in _PROVIDER_INCIDENT_CODES
            or type(assignment_index) is not int
            or not isinstance(assignments, list)
        ):
            raise ValueError("Terminal execution incident state is invalid")
        if "boundary" not in execution_incident and (
            not 0 <= assignment_index < len(assignments)
            or assignments[assignment_index].get("status")
            != "transport_void"
        ):
            raise ValueError("Terminal execution incident state is invalid")
    if codex_auth_incident is not None:
        assignments = private.get("assignments")
        if not _codex_auth_incident_is_valid(
            codex_auth_incident, assignments
        ):
            raise ValueError("Terminal Codex authentication incident is invalid")
    if (
        isinstance(execution_incident, Mapping)
        and "boundary" in execution_incident
        and execution_incident.get("boundary")
        not in {"clean_before_assignment", "final_completion"}
    ):
        raise ValueError("Terminal supervisor incident boundary is invalid")
    attestation_failure_code = (
        execution_incident.get("attestation_failure_code")
        if isinstance(execution_incident, Mapping)
        else None
    )
    if (
        attestation_failure_code is not None
        and attestation_failure_code
        not in _PERSISTENT_ATTESTATION_FAILURE_CODES
    ):
        raise ValueError("Terminal supervisor incident failure code is unsafe")
    failure_class = (
        execution_incident.get("failure_class")
        if isinstance(execution_incident, Mapping)
        else None
    )
    supervisor_boundary = (
        isinstance(execution_incident, Mapping)
        and (
            execution_incident.get("boundary")
            in {"clean_before_assignment", "final_completion"}
            or attestation_failure_code
            in _PERSISTENT_ATTESTATION_FAILURE_CODES
            or (
                "boundary" not in execution_incident
                and failure_class in _PROVIDER_ISOLATION_FAILURE_CLASSES
            )
        )
    )
    expected_status = (
        "stopped_supervisor_incident"
        if supervisor_boundary
        else "stopped_transport_void"
    )
    expected = _public_running(
        public_manifest, private, status=expected_status
    )
    relative = _relative_to_root(public_results_path, root)
    if _git_output(root, "ls-files", relative):
        raise RuntimeError(
            "Terminal-incident public progress path must remain untracked"
        )

    existing: dict[str, Any] | None = None
    if public_results_path.exists() or public_results_path.is_symlink():
        existing = _load_json(public_results_path)
        expected_running = _public_running(public_manifest, private)
        existing_status = existing.get("status")
        expected_schema = (
            set(expected_running)
            if existing_status == "running"
            else set(expected)
            if existing_status == expected_status
            else set()
        )
        if set(existing) != expected_schema:
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
            "model_invocations_conservatively_chargeable",
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
    if _load_json(public_results_path) != expected:
        raise RuntimeError(
            "Terminal-incident public progress failed durable reload"
        )
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
    sanitized.pop("cli_version", None)
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
            model_invocation_state = _durable_model_invocation_state(
                assignment
            )
            void_reason = assignment.get("void_reason")
            timeout_stage = assignment.get("timeout_stage")
            failure_stage = assignment.get("failure_stage")
            if (
                void_reason not in _PROVIDER_INCIDENT_CODES
                or timeout_stage
                not in {None, "provider_cli_readiness", "model_invocation"}
                or failure_stage
                not in {None, "provider_cli_readiness", "model_invocation"}
            ):
                raise ValueError(
                    "Transport-void public projection is invalid"
                )
            result = {
                "episode_ref": assignment["episode_ref"],
                "profile_id": assignment["profile_id"],
                "family": episode["family"],
                "status": "transport_void",
                "reason": void_reason,
                "trace_status": "unavailable_transport_void",
                "model_invocation_state": model_invocation_state,
                "conservative_chargeable": (
                    model_invocation_state != "not_started"
                ),
                "timeout_stage": timeout_stage,
                "failure_stage": failure_stage,
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
        "model_invocations_conservatively_chargeable": (
            _conservatively_chargeable_provider_calls(
                private["assignments"]
            )
        ),
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


def _completed_supervisor_binding(
    *,
    supervisor_runtime_dir: Path,
    authentication_key_file: Path,
    operation: str,
    public_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    # Resolve the trusted implementation here rather than accepting a caller-
    # supplied callback.  Public release must not be reachable through an
    # otherwise-valid fake attestation supplied to this API.
    from .launchd_agent import attest_completed_launch_agent

    try:
        attestation = attest_completed_launch_agent(
            supervisor_runtime_dir,
            authentication_key_file=authentication_key_file,
            expected_operation=operation,
            expected_panel_id=PANEL_ID,
            expected_precommitment_sha256=public_manifest[
                "precommitment_sha256"
            ],
        )
    except Exception:
        raise ProviderExecutionIsolationError(
            "Completed persistent-supervisor attestation failed"
        ) from None
    if (
        not isinstance(attestation, Mapping)
        or attestation.get("attested") is not True
        or attestation.get("lifecycle") != "completed"
    ):
        raise ProviderExecutionIsolationError(
            "Public release requires authenticated supervisor completion"
        )
    return _normalized_supervisor_binding(
        attestation,
        operation=operation,
        public_manifest=public_manifest,
    )


def _require_existing_persistent_execution_binding(
    private: Mapping[str, Any],
    *,
    operation: str,
    completed_binding: Mapping[str, Any],
) -> None:
    bindings = private.get(_PERSISTENT_EXECUTION_BINDINGS_KEY)
    existing = bindings.get(operation) if isinstance(bindings, Mapping) else None
    if (
        not isinstance(existing, Mapping)
        or set(existing) != _SUPERVISOR_BINDING_FIELDS
        or not hmac.compare_digest(
            _canonical_bytes(dict(existing)),
            _canonical_bytes(dict(completed_binding)),
        )
    ):
        raise ProviderExecutionIsolationError(
            "Completed supervisor differs from the create-once runtime binding"
        )


def finalize_supervised_release(
    *,
    root: Path,
    authentication_key_file: Path,
    claude_secure_storage_dir: Path,
    codex_secure_storage_dir: Path,
    private_state_path: Path,
    public_manifest_path: Path,
    public_output_path: Path,
    supervisor_runtime_dir: Path,
    operation: str,
) -> dict[str, Any]:
    """Publish one staged success after authenticated outer completion.

    This function is deliberately local-only: it never invokes an evaluator,
    authentication bootstrap, provider CLI, Keychain lookup, or network probe.
    The launchd worker calls it after the one supervised child command reaches
    its authenticated terminal-completed state.  Re-entry is safe only for
    reconciling an exact artifact written before a crash.
    """

    if operation not in {"preflight", "production"}:
        raise ValueError("Supervised release operation is invalid")
    _assert_canonical_public_output_path(
        public_manifest_path,
        public_output_path,
        operation=operation,
    )
    assert_durable_live_execution_paths(
        root=root,
        private_state_path=private_state_path,
    )
    _assert_distinct_paths(
        authentication_key_file,
        private_state_path,
        public_manifest_path,
        public_output_path,
    )
    with _exclusive_run_lock(private_state_path):
        authentication_key = _read_authentication_key(
            _existing_path_without_final_symlink(authentication_key_file)
        )
        private = _load_private_state(private_state_path, authentication_key)
        public = _load_json(public_manifest_path)
        _validate_public_hash(public)
        completed_binding = _completed_supervisor_binding(
            supervisor_runtime_dir=supervisor_runtime_dir,
            authentication_key_file=authentication_key_file,
            operation=operation,
            public_manifest=public,
        )
        _require_existing_persistent_execution_binding(
            private,
            operation=operation,
            completed_binding=completed_binding,
        )
        if any(
            private.get(name) is not None
            for name in ("execution_incident", "codex_auth_incident")
        ):
            raise ProviderExecutionIsolationError(
                "A terminal execution incident blocks public release"
            )
        resolved_claude_storage = _validate_claude_secure_storage_dir(
            claude_secure_storage_dir, root=root
        )
        resolved_codex_storage = _validate_codex_secure_storage_dir(
            codex_secure_storage_dir, root=root
        )
        manifest, _, _ = _validate_contracts(
            root=root,
            private=private,
            public=public,
            authentication_key=authentication_key,
            claude_secure_storage_dir=resolved_claude_storage,
            codex_secure_storage_dir=resolved_codex_storage,
            revalidate_live_identity_contracts=False,
        )

        if operation == "preflight":
            preflight = private.get("environment_preflight")
            if not isinstance(preflight, dict) or preflight.get("status") not in {
                _PENDING_PREFLIGHT_STATUS,
                "passed",
            }:
                raise ProviderExecutionIsolationError(
                    "No passed preflight candidate is pending release"
                )
            candidate = preflight.get("pending_public_receipt")
            if (
                not isinstance(candidate, dict)
                or candidate.get("status") != "passed"
                or candidate.get("panel_id") != PANEL_ID
                or candidate.get("precommitment_sha256")
                != public.get("precommitment_sha256")
                or preflight.get("pending_public_receipt_sha256")
                != _component_hash(candidate)
            ):
                raise ProviderExecutionIsolationError(
                    "Pending preflight release candidate is invalid"
                )
            candidate_sha256 = _component_hash(candidate)
            release = preflight.get(_PUBLIC_RELEASE_KEY)
            expected_release_status = (
                "released"
                if preflight.get("status") == "passed"
                else "pending_supervisor_completion"
            )
            if (
                not isinstance(release, Mapping)
                or dict(release)
                != {
                    "status": expected_release_status,
                    "operation": "preflight",
                }
            ):
                raise ProviderExecutionIsolationError(
                    "Pending preflight release state is invalid"
                )
            expected_pending = _public_preflight_pending(public, candidate)
            existing = _load_json(public_output_path)
            if existing != expected_pending and existing != candidate:
                raise ProviderExecutionIsolationError(
                    "Public preflight path differs from its staged candidate"
                )
            if preflight.get("status") == "passed":
                binding = preflight.get("public_receipt_binding")
                published_commit = (
                    binding.get("published_commit")
                    if isinstance(binding, Mapping)
                    else None
                )
                if preflight.get("public_receipt_sha256") != candidate_sha256:
                    raise ProviderExecutionIsolationError(
                        "Released preflight receipt digest changed"
                    )
                _validate_repository_receipt_binding(
                    binding,
                    root=root,
                    path=public_output_path,
                    artifact_kind="preflight",
                    content_sha256=candidate_sha256,
                    payload=candidate,
                    require_published_commit=published_commit is not None,
                )
                if existing == expected_pending:
                    if published_commit is not None:
                        raise ProviderExecutionIsolationError(
                            "A committed preflight receipt cannot regress "
                            "to its pending watermark"
                        )
                    _atomic_json(public_output_path, candidate)
                else:
                    _assert_exact_public_json_bytes(
                        public_output_path,
                        candidate,
                        label="preflight receipt",
                    )
                # Once released, finalization is a pure reconciliation step.
                # In particular, never reconstruct the binding: doing so
                # would erase a later create-once publishing commit.
                return candidate
            if existing == candidate:
                _assert_exact_public_json_bytes(
                    public_output_path,
                    candidate,
                    label="preflight receipt",
                )
            preflight.update(
                {
                    "status": "passed",
                    "public_receipt_binding": (
                        _repository_receipt_binding(
                            root=root,
                            path=public_output_path,
                            artifact_kind="preflight",
                            content_sha256=candidate_sha256,
                            payload=candidate,
                        )
                    ),
                    "public_receipt_sha256": candidate_sha256,
                    _PUBLIC_RELEASE_KEY: {
                        "status": "released",
                        "operation": "preflight",
                    },
                }
            )
            _write_private_state(
                private_state_path, private, authentication_key
            )
            # Public success is deliberately the final evaluator-side durable
            # write.  A crash before it leaves only the trace-free pending
            # watermark; a retry can verify the already-committed private
            # release marker and publish the exact same candidate.
            if existing == expected_pending:
                _atomic_json(public_output_path, candidate)
            return candidate

        if private.get("status") not in {
            _PENDING_PRODUCTION_STATUS,
            "complete",
        }:
            raise ProviderExecutionIsolationError(
                "No complete production candidate is pending release"
            )
        artifact = _complete_artifact(public, private)
        release = private.get(_PUBLIC_RELEASE_KEY)
        if (
            not isinstance(release, Mapping)
            or release.get("operation") != "production"
            or release.get("status")
            not in {"pending_supervisor_completion", "released"}
            or release.get("candidate_results_sha256")
            != artifact.get("results_sha256")
        ):
            raise ProviderExecutionIsolationError(
                "Pending production release candidate is invalid"
            )
        expected_pending = _public_running(
            public,
            private,
            status=_PENDING_PRODUCTION_STATUS,
        )
        existing = _load_json(public_output_path)
        if existing != expected_pending and existing != artifact:
            raise ProviderExecutionIsolationError(
                "Public results path differs from its staged candidate"
            )
        cohort_manifest_path = _existing_path_without_final_symlink(
            str(private["cohort_manifest_path"])
        )
        _ensure_terminal_cohort_retirement(
            cohort_manifest_path=cohort_manifest_path,
            manifest=manifest,
            public_manifest=public,
            artifact=artifact,
            authentication_key=authentication_key,
        )
        private["status"] = "complete"
        private[_PUBLIC_RELEASE_KEY] = {
            **dict(release),
            "status": "released",
        }
        _write_private_state(private_state_path, private, authentication_key)
        if existing == expected_pending:
            _atomic_json(public_output_path, artifact)
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
    supervisor_runtime_dir: Path | None = None,
    require_persistent_supervisor: bool = True,
    offline_test_evaluator: Callable[..., PilotRunResult] | None = None,
    acknowledge_unbounded_provider_spend: bool = False,
) -> dict[str, Any]:
    """Run or resume the 300 assignments, never retrying a durable start."""

    if acknowledge_unbounded_provider_spend is not True:
        raise RuntimeError("Explicit acknowledgement of unbounded provider spend is required")
    if require_persistent_supervisor:
        _assert_canonical_public_output_path(
            public_manifest_path,
            public_results_path,
            operation="production",
        )
    evaluator = _execution_evaluator(
        require_persistent_supervisor=require_persistent_supervisor,
        offline_test_evaluator=offline_test_evaluator,
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
        public_results_path,
    )
    authentication_key = _read_authentication_key(
        _existing_path_without_final_symlink(authentication_key_file)
    )
    private = _load_private_state(private_state_path, authentication_key)
    public_manifest = _load_json(public_manifest_path)
    _validate_public_hash(public_manifest)
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
    _, binding_created = _attest_with_transient_snapshot_retry(
        lambda: _attest_and_match_persistent_execution(
            required=require_persistent_supervisor,
            supervisor_runtime_dir=supervisor_runtime_dir,
            authentication_key_file=authentication_key_file,
            operation="production",
            public_manifest=public_manifest,
            private=private,
        )
    )
    if binding_created:
        _write_private_state(private_state_path, private, authentication_key)

    def attest_current_supervisor() -> None:
        _attest_and_match_persistent_execution(
            required=require_persistent_supervisor,
            supervisor_runtime_dir=supervisor_runtime_dir,
            authentication_key_file=authentication_key_file,
            operation="production",
            public_manifest=public_manifest,
            private=private,
        )
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
    managed_glean_auth_file_identity = private.get(
        "managed_glean_auth_file_identity"
    )
    if not isinstance(managed_glean_auth_file_identity, Mapping):
        raise RuntimeError("Managed Glean credential identity is unavailable")
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

    def attest_clean_provider_boundary() -> None:
        expected_assignment_count = len(assignments)
        _attest_with_transient_snapshot_retry(
            attest_current_supervisor,
            invariant=lambda: len(assignments) == expected_assignment_count,
        )

    def attest_full_provider_boundary() -> None:
        """Attest supervisor, execution, and helper state as one boundary."""

        try:
            attest_clean_provider_boundary()
            _attest_execution_contracts(
                root=root, public=public_manifest
            )
            _attest_frozen_glean_auth_dependencies(
                private, public_manifest
            )
        except ProviderExecutionIsolationError:
            raise
        except (OSError, RuntimeError, ValueError):
            raise ProviderStateIsolationError(
                "Provider boundary attestation failed"
            ) from None

    if assignments and assignments[-1]["status"] == "started":
        interrupted_profile_id = str(assignments[-1]["profile_id"])
        interrupted_model_state = _durable_model_invocation_state(
            assignments[-1]
        )
        private["execution_incident"] = {
            "status": "terminal",
            "assignment_index": len(assignments) - 1,
            "failure_class": "interrupted_after_durable_attempt",
            "incident_code": "provider_interrupted_after_durable_attempt",
        }
        if (
            _PROFILE_BY_ID[interrupted_profile_id]["system"] == "codex"
            and interrupted_model_state != "not_started"
        ):
            private["codex_auth_incident"] = {
                "status": "terminal",
                "assignment_index": len(assignments) - 1,
                "failure_class": "interrupted_after_model_invocation_start",
            }
        assignments[-1]["status"] = "transport_void"
        assignments[-1]["finished_at_utc"] = _utc_now()
        assignments[-1]["void_reason"] = (
            "provider_interrupted_after_durable_attempt"
        )
        assignments[-1]["model_invocation_state"] = (
            interrupted_model_state
        )
        assignments[-1]["conservative_chargeable"] = (
            interrupted_model_state != "not_started"
        )
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
    if remaining_systems:
        assert_panel_authentication_ready(
            root=root,
            authentication_key_file=authentication_key_file,
            claude_secure_storage_dir=resolved_claude_secure_storage_dir,
            codex_secure_storage_dir=resolved_codex_secure_storage_dir,
            private_state_path=private_state_path,
            public_manifest_path=public_manifest_path,
            require_clean_checkout=False,
            revalidate_live_identity_contracts=False,
        )
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
        _require_managed_glean_auth_file_identity(
            resolved_claude_secure_storage_dir,
            managed_glean_auth_file_identity,
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
            _require_managed_glean_auth_file_identity(
                resolved_claude_secure_storage_dir,
                managed_glean_auth_file_identity,
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
        try:
            attest_full_provider_boundary()
        except ProviderExecutionIsolationError as error:
            private["execution_incident"] = {
                "status": "terminal",
                "assignment_index": len(assignments),
                "failure_class": type(error).__name__,
                "incident_code": "supervisor_boundary_attestation_failed",
                "boundary": "clean_before_assignment",
                "profile_id": profile_id,
                **_attestation_incident_fields(error),
            }
            private["status"] = "running"
            _write_private_state(
                private_state_path, private, authentication_key
            )
            stopped = _public_running(
                public_manifest,
                private,
                status="stopped_supervisor_incident",
            )
            _atomic_json(public_results_path, stopped)
            return stopped
        started = _utc_now()
        marker: dict[str, Any] = {
            "episode_ref": ref,
            "profile_id": profile_id,
            "status": "started",
            "started_at_utc": started,
        }
        assignments.append(marker)
        codex_auth_ambiguous = False
        incident_code = "provider_attempt_marker_persist_failed"
        result: PilotRunResult | None = None
        try:
            try:
                _write_private_state(
                    private_state_path, private, authentication_key
                )
            except Exception:
                raise ProviderAttemptPersistenceError(
                    "Provider attempt marker could not be persisted"
                ) from None
            try:
                _atomic_json(
                    public_results_path,
                    _public_running(public_manifest, private),
                )
            except Exception:
                raise ProviderStateIsolationError(
                    "Public attempt checkpoint could not be persisted"
                ) from None
            incident_code = "provider_adapter_execution_failed"

            def persist_model_invocation_start() -> None:
                nonlocal incident_code
                incident_code = "model_invocation_marker_persist_failed"
                if "model_invocation" in marker:
                    raise ProviderStateIsolationError(
                        "Model invocation marker transition is invalid"
                    )
                marker["model_invocation"] = {
                    "status": "started",
                    "started_at_utc": _utc_now(),
                }
                try:
                    _write_private_state(
                        private_state_path,
                        private,
                        authentication_key,
                    )
                except Exception:
                    raise ProviderInvocationPersistenceError(
                        "Model invocation marker could not be persisted"
                    ) from None
                incident_code = "provider_adapter_execution_failed"

            def persist_progress(snapshot: Mapping[str, Any]) -> None:
                nonlocal incident_code
                incident_code = "provider_progress_checkpoint_persist_failed"
                try:
                    marker["progress_telemetry"] = (
                        _safe_live_provider_progress(snapshot)
                    )
                    _write_private_state(
                        private_state_path, private, authentication_key
                    )
                except ProviderProgressPersistenceError:
                    raise
                except Exception:
                    raise ProviderProgressPersistenceError(
                        "Provider progress checkpoint could not be persisted"
                    ) from None
                incident_code = "provider_adapter_execution_failed"

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
            incident_code = "provider_adapter_execution_failed"
            result = evaluator(
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
                model_invocation_start_callback=(
                    persist_model_invocation_start
                ),
                **provider_auth_kwargs,
            )
            incident_code = "provider_completion_marker_persist_failed"
            invocation = marker.get("model_invocation")
            if (
                not isinstance(invocation, dict)
                or invocation.get("status") != "started"
            ):
                raise ProviderStateIsolationError(
                    "Model invocation start marker is unavailable"
                )
            marker["model_invocation"] = {
                **invocation,
                "status": "finished",
                "finished_at_utc": _utc_now(),
            }
            try:
                _write_private_state(
                    private_state_path, private, authentication_key
                )
            except Exception:
                raise ProviderCompletionPersistenceError(
                    "Provider completion marker could not be persisted"
                ) from None
            incident_code = "supervisor_boundary_attestation_failed"
            attest_full_provider_boundary()
            if profile["system"] == "claude":
                incident_code = "credential_attestation_failed"
                try:
                    _require_claude_credential_state(
                        resolved_claude_secure_storage_dir,
                        root=root,
                        expected_identity=claude_secure_storage_identity,
                        managed_glean_credentials_present=True,
                    )
                    _require_managed_glean_auth_file_identity(
                        resolved_claude_secure_storage_dir,
                        managed_glean_auth_file_identity,
                    )
                except (OSError, RuntimeError, ValueError):
                    raise ProviderStateIsolationError(
                        "Claude credential persistence isolation failed"
                    ) from None
            if profile["system"] == "codex":
                incident_code = "credential_attestation_failed"
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
            incident_code = "evaluator_return_contract_failed"
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
            ):
                raise RuntimeError("Provider result differs from its pinned profile")
            incident_code = "provider_result_processing_failed"
            finished = _utc_now()
            sanitized = _sanitize_result(
                episode=episode,
                profile=profile,
                result=result,
                started_at=started,
                finished_at=finished,
            )
        except Exception as error:
            # The authenticated checkpoint is the only authority for whether
            # the model-bearing spawn boundary was crossed. In particular, a
            # failed marker write prevents Popen and must remain nonchargeable
            # even though the in-memory marker was tentatively mutated.
            durable_private = _load_private_state(
                private_state_path, authentication_key
            )
            durable_assignments = durable_private.get("assignments")
            assignment_index = len(assignments) - 1
            if (
                not isinstance(durable_assignments, list)
                or len(durable_assignments)
                not in {assignment_index, assignment_index + 1}
            ):
                raise ProviderStateIsolationError(
                    "Durable assignment state changed after provider failure"
                ) from None
            if len(durable_assignments) == assignment_index:
                durable_marker = {
                    "episode_ref": ref,
                    "profile_id": profile_id,
                    "status": "started",
                    "started_at_utc": started,
                }
                durable_assignments.append(durable_marker)
            else:
                durable_marker = durable_assignments[assignment_index]
                if (
                    not isinstance(durable_marker, dict)
                    or durable_marker.get("episode_ref") != ref
                    or durable_marker.get("profile_id") != profile_id
                    or durable_marker.get("status") != "started"
                ):
                    raise ProviderStateIsolationError(
                        "Durable assignment state changed after provider failure"
                    ) from None
            private = durable_private
            assignments = durable_assignments
            marker = durable_marker
            model_invocation_state = _durable_model_invocation_state(
                marker
            )
            projected_incident_code = _provider_incident_code(
                error, fallback=incident_code
            )
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
                    "incident_code": projected_incident_code,
                    **_attestation_incident_fields(error),
                }
                if (
                    profile["system"] == "codex"
                    and model_invocation_state != "not_started"
                ):
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
            marker["void_reason"] = projected_incident_code
            marker["model_invocation_state"] = model_invocation_state
            marker["conservative_chargeable"] = (
                marker["model_invocation_state"] != "not_started"
            )
            timeout_stage = _provider_timeout_stage(
                error,
                result=result,
            )
            marker["failure_stage"] = timeout_stage
            if timeout_stage is not None:
                marker["timed_out"] = True
                marker["timeout_stage"] = timeout_stage
            private["status"] = "running"
            _write_private_state(private_state_path, private, authentication_key)
            terminal_incident = any(
                private.get(name) is not None
                for name in ("execution_incident", "codex_auth_incident")
            )
            if require_persistent_supervisor and not terminal_incident:
                # The persistent supervisor owns one complete 300-assignment
                # evaluator process.  A safely returned, nonterminal provider
                # failure is a fixed-denominator void, not a reason to exit
                # that process and request a forbidden second launch.
                _atomic_json(
                    public_results_path,
                    _public_running(public_manifest, private),
                )
                continue
            stopped_status = (
                "stopped_supervisor_incident"
                if isinstance(error, ProviderExecutionIsolationError)
                else "stopped_transport_void"
            )
            stopped = _public_running(
                public_manifest, private, status=stopped_status
            )
            _atomic_json(public_results_path, stopped)
            return stopped
        marker["status"] = "complete"
        marker["finished_at_utc"] = finished
        marker["public_result"] = sanitized
        try:
            _write_private_state(
                private_state_path, private, authentication_key
            )
        except Exception:
            # The in-memory marker is not evidence that completion reached
            # durable storage. Reload the authenticated checkpoint and
            # terminalize that still-started assignment without another
            # provider invocation.
            durable_private = _load_private_state(
                private_state_path, authentication_key
            )
            durable_assignments = durable_private.get("assignments")
            assignment_index = len(assignments) - 1
            if (
                not isinstance(durable_assignments, list)
                or len(durable_assignments) != len(assignments)
                or not 0 <= assignment_index < len(durable_assignments)
            ):
                raise ProviderStateIsolationError(
                    "Durable assignment state changed after provider return"
                ) from None
            durable_marker = durable_assignments[assignment_index]
            if (
                not isinstance(durable_marker, dict)
                or durable_marker.get("episode_ref") != ref
                or durable_marker.get("profile_id") != profile_id
                or durable_marker.get("status") != "started"
            ):
                raise ProviderStateIsolationError(
                    "Durable assignment state changed after provider return"
                ) from None
            completion_error = ProviderCompletionPersistenceError(
                "Provider completion checkpoint could not be persisted"
            )
            durable_marker.update(
                {
                    "status": "transport_void",
                    "finished_at_utc": _utc_now(),
                    "void_reason": (
                        "provider_completion_marker_persist_failed"
                    ),
                    "model_invocation_state": (
                        _durable_model_invocation_state(durable_marker)
                    ),
                    "conservative_chargeable": True,
                    "failure_stage": None,
                }
            )
            durable_private["execution_incident"] = {
                "status": "terminal",
                "assignment_index": assignment_index,
                "failure_class": type(completion_error).__name__,
                "incident_code": _provider_incident_code(
                    completion_error,
                    fallback="provider_completion_marker_persist_failed",
                ),
            }
            durable_private["status"] = "running"
            _write_private_state(
                private_state_path, durable_private, authentication_key
            )
            stopped = _public_running(
                public_manifest,
                durable_private,
                status="stopped_supervisor_incident",
            )
            _atomic_json(public_results_path, stopped)
            return stopped
        _atomic_json(public_results_path, _public_running(public_manifest, private))

    if len(assignments) != ASSIGNMENT_COUNT or any(
        assignment["status"] not in {"complete", "transport_void"}
        for assignment in assignments
    ):
        raise RuntimeError(
            f"Matched panel did not reach {ASSIGNMENT_COUNT} terminal assignments"
        )
    try:
        attest_full_provider_boundary()
    except ProviderExecutionIsolationError as error:
        private["execution_incident"] = {
            "status": "terminal",
            "assignment_index": len(assignments),
            "failure_class": type(error).__name__,
            "incident_code": "supervisor_boundary_attestation_failed",
            "boundary": "final_completion",
            **_attestation_incident_fields(error),
        }
        private["status"] = "running"
        _write_private_state(private_state_path, private, authentication_key)
        stopped = _public_running(
            public_manifest,
            private,
            status="stopped_supervisor_incident",
        )
        _atomic_json(public_results_path, stopped)
        return stopped
    private["status"] = (
        _PENDING_PRODUCTION_STATUS
        if require_persistent_supervisor
        else "complete"
    )
    private["panel_completed_at_utc"] = _utc_now()
    artifact = _complete_artifact(public_manifest, private)
    if require_persistent_supervisor:
        private[_PUBLIC_RELEASE_KEY] = {
            "status": "pending_supervisor_completion",
            "operation": "production",
            "candidate_results_sha256": artifact["results_sha256"],
        }
        _write_private_state(private_state_path, private, authentication_key)
        pending = _public_running(
            public_manifest,
            private,
            status=_PENDING_PRODUCTION_STATUS,
        )
        _atomic_json(public_results_path, pending)
        return pending
    _write_private_state(private_state_path, private, authentication_key)
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
    supervisor_runtime_dir: Path | None = None,
    acknowledge_unbounded_provider_spend: bool = False,
) -> dict[str, Any]:
    """Run or resume the panel under authenticated persistent supervision."""

    if acknowledge_unbounded_provider_spend is not True:
        raise RuntimeError(
            "Explicit acknowledgement of unbounded provider spend is required"
        )
    assert_durable_live_execution_paths(
        root=root,
        private_state_path=private_state_path,
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
            supervisor_runtime_dir=supervisor_runtime_dir,
            require_persistent_supervisor=True,
            offline_test_evaluator=None,
            acknowledge_unbounded_provider_spend=True,
        )


def _run_panel_for_offline_test(
    *,
    root: Path,
    authentication_key_file: Path,
    claude_secure_storage_dir: Path,
    codex_secure_storage_dir: Path,
    private_state_path: Path,
    public_manifest_path: Path,
    public_results_path: Path,
    offline_test_evaluator: Callable[..., PilotRunResult],
    acknowledge_unbounded_provider_spend: bool = False,
) -> dict[str, Any]:
    """Private deterministic seam for unit tests; never a live run path."""

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
            supervisor_runtime_dir=None,
            require_persistent_supervisor=False,
            offline_test_evaluator=offline_test_evaluator,
            acknowledge_unbounded_provider_spend=True,
        )
