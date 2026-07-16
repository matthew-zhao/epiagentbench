"""Precommitted, development-only Claude Opus high-effort pilot.

This is an intentionally small, unpaired follow-up panel.  It reuses the
trusted development-pilot machinery for commitments, sanitization, and atomic
checkpoints while fixing one Claude configuration across five fresh episodes.
Provider execution remains host-networked and non-hermetic.

The v2 identifier is deliberate: v1 was permanently voided after a Claude MCP
isolation failure and its assignments are never reused here.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict
import hashlib
import hmac
import os
from pathlib import Path
import platform
import secrets
import shutil
import statistics
import subprocess
import sys
from typing import Any, Mapping, Sequence

from .development_pilot import (
    BACKEND,
    DIMENSION_MAXIMA,
    _atomic_json,
    _canonical_bytes,
    _derive_secret,
    _file_sha256,
    _git_output,
    _load_json,
    _raise_on_harness_startup_failure,
    _relative_to_root,
    _sanitize_result as _sanitize_base_result,
    _sha256,
    _utc_now,
)
from .pilot import (
    PilotRunResult,
    _CLAUDE_EXPECTED_TOOLS as _PILOT_CLAUDE_EXPECTED_TOOLS,
    _PUBLIC_TOOL_NAMES as _PILOT_PUBLIC_TOOL_NAMES,
    _task_prompt,
    evaluate_local_cli_agent,
)
from .trusted.cohort_freezer import compute_generator_fingerprint


PANEL_ID = "development-opus-high-pilot-v2-2026-07-15"
SCHEMA_VERSION = "development_opus_pilot_v2"
SYSTEM = "claude"
REQUESTED_MODEL = "claude-opus-4-8"
CLAUDE_EFFORT = "high"
CLAUDE_EXECUTABLE = "claude"
FAMILIES = (
    "institution_person_to_person",
    "restaurant_point_source",
    "repeated_introduction",
    "coincidental_venue",
    "reporting_artifact",
)
EPISODE_REFS = tuple(f"episode_{index:02d}" for index in range(1, 6))
PUBLIC_MCP_TOOLS = (
    "get_manifest",
    "initial_observations",
    "search_observations",
    "request_interview",
    "order_confirmatory_test",
    "request_inspection",
    "advance_time",
    "recommend_action",
    "set_institution_control",
    "set_response_control",
    "submit_forecast",
    "get_clock_and_budget",
)
EXPECTED_CLAUDE_INIT_TOOLS = (
    *(f"mcp__epiagent__{tool}" for tool in PUBLIC_MCP_TOOLS),
    "StructuredOutput",
)


def _claude_isolation_contract() -> dict[str, Any]:
    """Return the exact validated Claude invocation/isolation contract."""

    return {
        "isolated_assignment_environment": True,
        "temporary_home_and_config": True,
        "environment_roots": [
            "HOME",
            "XDG_CONFIG_HOME",
            "XDG_CACHE_HOME",
            "XDG_DATA_HOME",
            "XDG_STATE_HOME",
            "CLAUDE_CONFIG_DIR",
        ],
        "unset_environment": ["CLAUDE_CODE_SAFE_MODE"],
        "safe_mode": False,
        "setting_sources": ["project"],
        "permission_mode": "dontAsk",
        "declared_builtin_tools": ["Read"],
        "disallowed_tools": ["Read"],
        "slash_commands_disabled": True,
        "strict_explicit_mcp_config": True,
        "allowed_tools": ["mcp__epiagent__*"],
        "expected_mcp_servers": {"epiagent": "connected"},
        "expected_init_tools": list(EXPECTED_CLAUDE_INIT_TOOLS),
        "expected_init_tool_count": len(EXPECTED_CLAUDE_INIT_TOOLS),
        "inventory_failure_event": "agent_failure:mcp_unavailable",
        "unauthorized_tool_event": "agent_failure:unauthorized_tool",
    }


def _permuted_families(master: bytes) -> tuple[str, ...]:
    """Randomly key the balanced family set without consulting outcomes."""

    return tuple(
        sorted(
            FAMILIES,
            key=lambda family: hmac.new(
                master, b"family-order\0" + family.encode("ascii"), hashlib.sha256
            ).digest(),
        )
    )


def _derived_seed(master: bytes, episode_ref: str, family: str) -> int:
    digest = hmac.new(
        master,
        f"episode-seed\0{episode_ref}\0{family}".encode("ascii"),
        hashlib.sha256,
    ).digest()
    return int.from_bytes(digest[:7], "big") & ((1 << 52) - 1)


def _family_opening_salt(master: bytes, episode_ref: str) -> bytes:
    return hmac.new(
        master,
        b"family-opening\0" + episode_ref.encode("ascii"),
        hashlib.sha256,
    ).digest()


def _family_commitment(opening_salt: bytes, family: str) -> str:
    return _sha256(opening_salt + b"\0" + family.encode("ascii"))


def _private_panel(master: bytes) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "episode_ref": episode_ref,
            "family": family,
            "seed": _derived_seed(master, episode_ref, family),
            "family_opening_salt_hex": _family_opening_salt(
                master, episode_ref
            ).hex(),
        }
        for episode_ref, family in zip(
            EPISODE_REFS, _permuted_families(master), strict=True
        )
    )


def _validate_panel() -> None:
    if len(EPISODE_REFS) != 5 or len(set(EPISODE_REFS)) != 5:
        raise RuntimeError("Opus development panel must have five opaque episode refs")
    if len(FAMILIES) != 5 or len(set(FAMILIES)) != 5:
        raise RuntimeError("Opus development panel must have five balanced families")
    if sum(DIMENSION_MAXIMA.values()) != 100.0:
        raise RuntimeError("Score dimensions no longer sum to 100")
    if len(PUBLIC_MCP_TOOLS) != 12 or len(set(PUBLIC_MCP_TOOLS)) != 12:
        raise RuntimeError("Claude isolation contract must expose 12 public MCP tools")
    if set(EXPECTED_CLAUDE_INIT_TOOLS) != {
        "StructuredOutput",
        *(f"mcp__epiagent__{tool}" for tool in PUBLIC_MCP_TOOLS),
    }:
        raise RuntimeError("Claude init inventory contract is inconsistent")
    if PUBLIC_MCP_TOOLS != _PILOT_PUBLIC_TOOL_NAMES or (
        EXPECTED_CLAUDE_INIT_TOOLS != _PILOT_CLAUDE_EXPECTED_TOOLS
    ):
        raise RuntimeError("Opus precommit and Claude runner inventories disagree")


def _source_hashes(root: Path) -> dict[str, Any]:
    """Bind every tracked benchmark/client/schema runtime input by path and bytes."""

    output = _git_output(
        root,
        "ls-files",
        "--",
        "examples/run_development_opus_pilot.py",
        "src/epiagentbench",
        "src/epiagentbench_client",
        "schemas",
        "pyproject.toml",
    )
    relative_paths = sorted({line for line in output.splitlines() if line})
    required = (
        "src/epiagentbench/",
        "src/epiagentbench_client/",
        "schemas/",
    )
    if (
        not relative_paths
        or "pyproject.toml" not in relative_paths
        or "examples/run_development_opus_pilot.py" not in relative_paths
        or any(not any(path.startswith(prefix) for path in relative_paths) for prefix in required)
        or "src/epiagentbench/development_opus_pilot.py" not in relative_paths
    ):
        raise RuntimeError("Tracked runtime source surface is empty or incomplete")
    files: dict[str, str] = {}
    resolved_root = root.resolve()
    for relative in relative_paths:
        path = (root / relative).resolve()
        try:
            path.relative_to(resolved_root)
        except ValueError as error:
            raise RuntimeError("Tracked runtime source escapes the repository") from error
        if not path.is_file():
            raise RuntimeError(f"Tracked runtime source is missing: {relative}")
        files[Path(relative).as_posix()] = _file_sha256(path)
    canonical_files = {path: files[path] for path in sorted(files)}
    return {
        "tracked_runtime_files": canonical_files,
        "tracked_runtime_surface_sha256": _sha256(
            _canonical_bytes(canonical_files)
        ),
        "resolved_generator_runtime_fingerprint": compute_generator_fingerprint(
            source_root=root / "src"
        ),
        "task_prompt": _sha256(_task_prompt().encode("utf-8")),
    }


def _claude_version() -> str:
    resolved = shutil.which(CLAUDE_EXECUTABLE)
    if resolved is None:
        raise RuntimeError("The Claude CLI is unavailable")
    process = subprocess.run(
        [resolved, "--version"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=15,
    )
    version = process.stdout.decode("utf-8", errors="replace").strip()[:200]
    if process.returncode != 0 or not version:
        raise RuntimeError("Unable to read the Claude CLI version")
    return version


def _require_claude_version(expected: str) -> str:
    observed = _claude_version()
    if observed != expected:
        raise RuntimeError(
            f"Claude CLI version drift: expected {expected!r}, observed {observed!r}"
        )
    return observed


def prepare_panel(
    *,
    root: Path,
    private_manifest_path: Path,
    public_manifest_path: Path,
    timeout_seconds: int = 900,
    claude_max_budget_usd: float = 5.0,
) -> dict[str, Any]:
    """Create owner-only replay state and an immutable public precommitment."""

    _validate_panel()
    if _git_output(root, "status", "--porcelain", "--untracked-files=all"):
        raise RuntimeError("Commit and clean the harness before preparing the panel")
    if private_manifest_path.exists() or public_manifest_path.exists():
        raise FileExistsError("Refusing to replace an existing Opus panel manifest")
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 3600:
        raise ValueError("timeout_seconds must be between 1 and 3600")
    if not 0 < claude_max_budget_usd <= 100:
        raise ValueError("Invalid Claude budget")

    claude_cli_version = _claude_version()
    master = secrets.token_bytes(32)
    public_episodes: list[dict[str, Any]] = []
    private_episodes: list[dict[str, Any]] = []
    for episode in _private_panel(master):
        opening_salt = bytes.fromhex(str(episode["family_opening_salt_hex"]))
        secret = _derive_secret(
            master, str(episode["family"]), int(episode["seed"])
        )
        public_episode = {
            "episode_ref": episode["episode_ref"],
            "family_commitment": _family_commitment(
                opening_salt, str(episode["family"])
            ),
            "episode_secret_commitment": _sha256(secret),
        }
        public_episodes.append(public_episode)
        private_episodes.append({**episode, **public_episode})

    run_contract = {
        "backend": BACKEND,
        "system": SYSTEM,
        "executable": CLAUDE_EXECUTABLE,
        "claude_cli_version": claude_cli_version,
        "requested_model": REQUESTED_MODEL,
        "exact_model_receipt_required": True,
        "fallback_model": None,
        "requested_effort": CLAUDE_EFFORT,
        "effort_attribution": "requested_only_unverified",
        "native_output_contract": "Claude --json-schema with submission.schema.json",
        "claude_isolation_contract": _claude_isolation_contract(),
        "timeout_seconds_per_assignment": timeout_seconds,
        "claude_max_budget_usd_per_assignment": claude_max_budget_usd,
        "retry_policy": "no retries after an assignment starts",
        "final_commitment_opening": (
            "publish the panel master secret only after all five assignments finish"
        ),
        "failure_policy": (
            "timeouts, invalid structured submissions, and nonexact or missing model "
            "receipts remain in the fixed five-episode denominator with score zero; "
            "infrastructure or harness exceptions stop and retire the panel"
        ),
    }
    public: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "panel_id": PANEL_ID,
        "status": "precommitted",
        "prepared_at_utc": _utc_now(),
        "development_only": True,
        "leaderboard_eligible": False,
        "hermetic": False,
        "paired": False,
        "calibrated": False,
        "scientific_claim": (
            "five-episode configuration check; descriptive only, not a model ranking"
        ),
        "benchmark_base_commit": _git_output(root, "rev-parse", "HEAD"),
        "source_hashes": _source_hashes(root),
        "panel_master_secret_commitment": _sha256(master),
        "episodes": public_episodes,
        "score_dimension_maxima": dict(DIMENSION_MAXIMA),
        "run_contract": run_contract,
        "planned_assignments": len(EPISODE_REFS),
        "results": [],
        "limitations": [
            "host-networked Claude CLI execution is not hermetic",
            "this unpaired panel cannot support cross-system causal comparisons",
            "synthetic LTC-v3 development episodes are not externally calibrated",
            "one episode per causal family is too small for uncertainty estimates",
            "final publication opens the master secret for exact replay and permanently retires this panel",
        ],
    }
    private = {
        "schema_version": SCHEMA_VERSION,
        "panel_id": PANEL_ID,
        "master_secret_hex": master.hex(),
        "episodes": private_episodes,
        "assignments": [],
        "status": "prepared",
    }
    public["precommitment_sha256"] = _sha256(_canonical_bytes(public))
    private["public_precommitment_sha256"] = public["precommitment_sha256"]
    _atomic_json(private_manifest_path, private, private=True)
    _atomic_json(public_manifest_path, public)
    return public


def _sanitize_result(
    *,
    episode: Mapping[str, Any],
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
    receipt_exact = (
        result.requested_model == REQUESTED_MODEL
        and result.observed_models == (REQUESTED_MODEL,)
    )
    schema_constrained_submission_accepted = bool(result.submission) and not any(
        event == "agent_failure:invalid_submission" for event in result.audit_events
    )
    sanitized["exact_model_receipt"] = receipt_exact
    sanitized["schema_constrained_submission_accepted"] = (
        schema_constrained_submission_accepted
    )
    sanitized["requested_effort"] = CLAUDE_EFFORT
    sanitized["effort_attribution"] = "requested_only_unverified"
    audit_events = set(result.audit_events)
    mcp_inventory_verified = (
        "agent_failure:mcp_unavailable" not in audit_events
    )
    sanitized["mcp_inventory_verified"] = mcp_inventory_verified
    sanitized["mcp_inventory_status"] = (
        "verified" if mcp_inventory_verified else "unavailable"
    )
    unauthorized_tool_detected = (
        "agent_failure:unauthorized_tool" in audit_events
    )
    sanitized["unauthorized_tool_detected"] = unauthorized_tool_detected
    sanitized["unauthorized_tool_status"] = (
        "detected" if unauthorized_tool_detected else "not_detected"
    )
    opening = episode.get("family_opening_salt_hex")
    if not isinstance(opening, str):
        raise ValueError("Private episode has no family commitment opening")
    sanitized["family_commitment_opening_salt_hex"] = opening
    if not receipt_exact:
        sanitized["valid"] = False
        sanitized["total"] = 0.0
        sanitized["dimensions"] = {name: 0.0 for name in DIMENSION_MAXIMA}
        sanitized["metrics"]["integrity_pass"] = False
        sanitized["model_attribution"] = "failed"
        audit = list(sanitized["audit_events"])
        if "agent_failure:model_receipt_nonexact" not in audit:
            audit.append("agent_failure:model_receipt_nonexact")
        sanitized["audit_events"] = audit
    return sanitized


def _raise_on_opus_startup_failure(result: PilotRunResult) -> None:
    """Separate a failed Claude invocation from an attributable model score."""

    if "agent_failure:timeout" in result.audit_events:
        return
    _raise_on_harness_startup_failure(result)
    metrics = result.scorecard.get("metrics", {})
    tool_calls = metrics.get("tool_calls", 0) if isinstance(metrics, dict) else 0
    if result.returncode != 0 and not result.observed_models and not tool_calls:
        raise RuntimeError(
            "Claude exited before model attribution or any episode tool call; "
            "treating schema/model/effort/policy/config failure as infrastructure"
        )


def aggregate_results(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarize against the fixed five-episode denominator."""

    expected_refs = set(EPISODE_REFS)
    keyed: dict[str, Mapping[str, Any]] = {}
    for result in results:
        ref = str(result.get("episode_ref"))
        if ref not in expected_refs or result.get("system") != SYSTEM:
            raise ValueError(f"Unexpected Opus pilot result: {ref}")
        if ref in keyed:
            raise ValueError(f"Duplicate Opus pilot result: {ref}")
        keyed[ref] = result
    planned = [keyed.get(episode_ref) for episode_ref in EPISODE_REFS]
    completed = list(keyed.values())
    totals = [float(item.get("total", 0.0)) if item else 0.0 for item in planned]
    audit_counts = Counter(
        str(event) for item in completed for event in item.get("audit_events", [])
    )
    return {
        "planned": len(EPISODE_REFS),
        "completed": len(completed),
        "valid": sum(bool(item.get("valid")) for item in completed),
        "integrity_pass": sum(
            item.get("metrics", {}).get("integrity_pass") is True
            for item in completed
        ),
        "exact_model_receipts": sum(
            item.get("exact_model_receipt") is True for item in completed
        ),
        "schema_constrained_submissions_accepted": sum(
            item.get("schema_constrained_submission_accepted") is True
            for item in completed
        ),
        "mcp_inventory_verified": sum(
            item.get("mcp_inventory_verified") is True for item in completed
        ),
        "mcp_inventory_unverified": sum(
            item.get("mcp_inventory_verified") is not True for item in completed
        ),
        "unauthorized_tool_detected": sum(
            item.get("unauthorized_tool_detected") is True for item in completed
        ),
        "unauthorized_tool_clear": sum(
            item.get("unauthorized_tool_detected") is False for item in completed
        ),
        "mean_total": round(statistics.fmean(totals), 3),
        "median_total": round(statistics.median(totals), 3),
        "mean_dimensions": {
            name: round(
                statistics.fmean(
                    float(item.get("dimensions", {}).get(name, 0.0))
                    if item
                    else 0.0
                    for item in planned
                ),
                3,
            )
            for name in DIMENSION_MAXIMA
        },
        "median_elapsed_seconds": round(
            statistics.median(
                float(item.get("elapsed_seconds", 0.0)) for item in completed
            ),
            3,
        )
        if completed
        else None,
        "audit_event_counts": dict(sorted(audit_counts.items())),
    }


def _validate_commitments(
    private: Mapping[str, Any], public: Mapping[str, Any], *, root: Path
) -> bytes:
    _validate_panel()
    if private.get("panel_id") != PANEL_ID or public.get("panel_id") != PANEL_ID:
        raise ValueError("Manifest belongs to another panel")
    if private.get("public_precommitment_sha256") != public.get(
        "precommitment_sha256"
    ):
        raise ValueError("Private state does not match the public precommitment")
    unsigned = dict(public)
    supplied = unsigned.pop("precommitment_sha256", None)
    if supplied != _sha256(_canonical_bytes(unsigned)):
        raise ValueError("Public precommitment is invalid")
    if public.get("status") != "precommitted" or public.get("results") != []:
        raise ValueError("Public precommitment must remain immutable")
    if public.get("source_hashes") != _source_hashes(root):
        raise ValueError("Executed source does not match the precommitment")
    expected_contract = {
        "backend": BACKEND,
        "system": SYSTEM,
        "executable": CLAUDE_EXECUTABLE,
        "requested_model": REQUESTED_MODEL,
        "exact_model_receipt_required": True,
        "fallback_model": None,
        "requested_effort": CLAUDE_EFFORT,
        "effort_attribution": "requested_only_unverified",
        "final_commitment_opening": (
            "publish the panel master secret only after all five assignments finish"
        ),
    }
    contract = public.get("run_contract")
    if not isinstance(contract, dict) or any(
        contract.get(key) != value for key, value in expected_contract.items()
    ):
        raise ValueError("Opus run contract does not match the fixed harness")
    if not isinstance(contract.get("claude_cli_version"), str) or not contract.get(
        "claude_cli_version"
    ):
        raise ValueError("Opus run contract has no pinned Claude CLI version")
    if contract.get("native_output_contract") != (
        "Claude --json-schema with submission.schema.json"
    ):
        raise ValueError("Opus structured-output contract is not fixed")
    if contract.get("claude_isolation_contract") != _claude_isolation_contract():
        raise ValueError("Opus Claude isolation contract is not fixed")
    timeout = contract.get("timeout_seconds_per_assignment")
    budget = contract.get("claude_max_budget_usd_per_assignment")
    if type(timeout) is not int or not 1 <= timeout <= 3600:
        raise ValueError("Opus timeout contract is invalid")
    if (
        isinstance(budget, bool)
        or not isinstance(budget, (int, float))
        or not 0 < float(budget) <= 100
    ):
        raise ValueError("Opus budget contract is invalid")
    master_hex = private.get("master_secret_hex")
    if not isinstance(master_hex, str):
        raise ValueError("Private manifest has no master secret")
    master = bytes.fromhex(master_hex)
    if _sha256(master) != public.get("panel_master_secret_commitment"):
        raise ValueError("Panel master-secret commitment mismatch")
    public_episodes = public.get("episodes")
    private_episodes = private.get("episodes")
    if not isinstance(public_episodes, list) or not isinstance(private_episodes, list):
        raise ValueError("Episode manifests must be arrays")
    if len(public_episodes) != len(EPISODE_REFS) or len(private_episodes) != len(
        EPISODE_REFS
    ):
        raise ValueError("Episode manifest has the wrong cardinality")
    if {str(item.get("family")) for item in private_episodes} != set(FAMILIES):
        raise ValueError("Private episode manifest is not family-balanced")
    for expected_ref, public_episode, private_episode in zip(
        EPISODE_REFS, public_episodes, private_episodes, strict=True
    ):
        if any(
            key in public_episode
            for key in ("family", "seed", "seed_derivation", "family_opening_salt_hex")
        ):
            raise ValueError("Public precommitment reveals a private episode field")
        family = private_episode.get("family")
        opening_hex = private_episode.get("family_opening_salt_hex")
        if (
            public_episode.get("episode_ref") != expected_ref
            or private_episode.get("episode_ref") != expected_ref
            or not isinstance(family, str)
            or family not in FAMILIES
            or not isinstance(opening_hex, str)
            or private_episode.get("seed")
            != _derived_seed(master, expected_ref, str(family))
        ):
            raise ValueError("Episode contract mismatch")
        try:
            opening_salt = bytes.fromhex(opening_hex)
        except ValueError as error:
            raise ValueError("Invalid family commitment opening") from error
        if opening_salt != _family_opening_salt(master, expected_ref):
            raise ValueError("Family commitment opening mismatch")
        if public_episode.get("family_commitment") != _family_commitment(
            opening_salt, family
        ):
            raise ValueError("Family commitment mismatch")
        secret = _derive_secret(
            master, family, int(private_episode["seed"])
        )
        if (
            public_episode.get("episode_secret_commitment") != _sha256(secret)
            or private_episode.get("episode_secret_commitment") != _sha256(secret)
        ):
            raise ValueError("Episode-secret commitment mismatch")
    return master


def _reconstruct_public_results(
    assignments: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if len(assignments) > len(EPISODE_REFS):
        raise ValueError("Private state contains too many assignments")
    reconstructed: list[dict[str, Any]] = []
    for ref, assignment in zip(EPISODE_REFS, assignments):
        if assignment.get("episode_ref") != ref or assignment.get("system") != SYSTEM:
            raise ValueError("Assignments do not follow the fixed order")
        if assignment.get("status") == "in_progress":
            raise RuntimeError(
                "A prior assignment started but did not finish; no-retry policy blocks resume"
            )
        public_result = assignment.get("public_result")
        if assignment.get("status") != "complete" or not isinstance(
            public_result, dict
        ):
            raise ValueError("Completed assignment has no public result")
        if (
            public_result.get("episode_ref") != ref
            or public_result.get("system") != SYSTEM
        ):
            raise ValueError("Private checkpoint and public result disagree")
        reconstructed.append(dict(public_result))
    aggregate_results(reconstructed)
    return reconstructed


def _execution_environment(root: Path) -> dict[str, Any]:
    try:
        import starsim  # type: ignore

        starsim_version = str(getattr(starsim, "__version__", "unknown"))
    except ImportError:
        starsim_version = "unavailable"
    claude_cli_version = _claude_version()
    return {
        "execution_commit": _git_output(root, "rev-parse", "HEAD"),
        "git_status_at_start": _git_output(
            root, "status", "--porcelain", "--untracked-files=all"
        ),
        "python": sys.version.split()[0],
        "starsim": starsim_version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "provider_network_access": True,
        "sandbox": "Claude safe mode with public MCP only; not hermetic",
        "claude_available": True,
        "claude_cli_version": claude_cli_version,
    }


def _require_same_execution_environment(
    pinned: Mapping[str, Any], current: Mapping[str, Any]
) -> None:
    """Allow only the expected untracked-results status change on resume."""

    if set(pinned) != set(current):
        raise RuntimeError("Execution environment shape changed during the panel")
    for key, value in pinned.items():
        if key == "git_status_at_start":
            continue
        if current.get(key) != value:
            raise RuntimeError(f"Execution environment drifted during the panel: {key}")


def _public_scaffold(
    *,
    precommit: Mapping[str, Any],
    execution_environment: Mapping[str, Any],
    started_at_utc: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "panel_id": PANEL_ID,
        "precommitment_sha256": precommit["precommitment_sha256"],
        "development_only": True,
        "leaderboard_eligible": False,
        "hermetic": False,
        "paired": False,
        "calibrated": False,
        "status": "running",
        "started_at_utc": started_at_utc,
        "execution_environment": dict(execution_environment),
        "run_contract": precommit["run_contract"],
        "score_dimension_maxima": precommit["score_dimension_maxima"],
        "planned_assignments": len(EPISODE_REFS),
        "limitations": precommit["limitations"],
    }


def _running_public_artifact(
    *,
    precommit: Mapping[str, Any],
    execution_environment: Mapping[str, Any],
    started_at_utc: str,
    completed_assignments: int,
    running_assignment: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    public = _public_scaffold(
        precommit=precommit,
        execution_environment=execution_environment,
        started_at_utc=started_at_utc,
    )
    public["results"] = []
    public["completed_assignments"] = completed_assignments
    public["summary"] = aggregate_results([])
    if running_assignment is not None:
        public["running_assignment"] = dict(running_assignment)
    return public


def _complete_public_artifact(
    *,
    precommit: Mapping[str, Any],
    execution_environment: Mapping[str, Any],
    started_at_utc: str,
    completed_at_utc: str,
    results: Sequence[Mapping[str, Any]],
    master: bytes,
) -> dict[str, Any]:
    public = _public_scaffold(
        precommit=precommit,
        execution_environment=execution_environment,
        started_at_utc=started_at_utc,
    )
    public["status"] = "complete"
    public["results"] = [dict(result) for result in results]
    public["completed_assignments"] = len(results)
    public["completed_at_utc"] = completed_at_utc
    public["panel_retired_after_publication"] = True
    public["panel_master_secret_opening_hex"] = master.hex()
    public["summary"] = aggregate_results(public["results"])
    public["results_sha256"] = _sha256(_canonical_bytes(public))
    return public


def _preflight_execution(
    *,
    root: Path,
    private_manifest_path: Path,
    public_manifest_path: Path,
    public_results_path: Path,
    expected_claude_cli_version: str,
) -> dict[str, Any]:
    public_relative = _relative_to_root(public_manifest_path, root)
    private_relative = _relative_to_root(private_manifest_path, root)
    results_relative = _relative_to_root(public_results_path, root)
    if _git_output(root, "ls-files", "--error-unmatch", public_relative) != public_relative:
        raise RuntimeError("Public precommitment has not been committed")
    if _git_output(root, "ls-files", private_relative):
        raise RuntimeError("Private replay state must never be tracked")
    if os.stat(private_manifest_path).st_mode & 0o077:
        raise RuntimeError("Private replay state permissions are too broad")
    environment = _execution_environment(root)
    expected_dirty = f"?? {results_relative}" if public_results_path.exists() else ""
    if environment["git_status_at_start"] != expected_dirty:
        raise RuntimeError("Execution worktree is not clean")
    if environment["starsim"] != "3.5.1":
        raise RuntimeError("The predeclared Starsim 3.5.1 runtime is unavailable")
    if not environment["claude_available"]:
        raise RuntimeError("The Claude CLI is unavailable")
    if environment["claude_cli_version"] != expected_claude_cli_version:
        raise RuntimeError("Claude CLI version drifted after the public precommitment")
    return environment


def run_panel(
    *,
    root: Path,
    private_manifest_path: Path,
    public_manifest_path: Path,
    public_results_path: Path,
) -> dict[str, Any]:
    """Run or safely resume the fixed panel without retrying started work."""

    private = _load_json(private_manifest_path)
    precommit = _load_json(public_manifest_path)
    master = _validate_commitments(private, precommit, root=root)
    reconstructed = _reconstruct_public_results(private["assignments"])
    current_environment = _preflight_execution(
        root=root,
        private_manifest_path=private_manifest_path,
        public_manifest_path=public_manifest_path,
        public_results_path=public_results_path,
        expected_claude_cli_version=str(
            precommit["run_contract"]["claude_cli_version"]
        ),
    )
    _git_output(
        root, "merge-base", "--is-ancestor", precommit["benchmark_base_commit"], "HEAD"
    )
    existing_public = (
        _load_json(public_results_path) if public_results_path.exists() else None
    )
    if existing_public is not None and (
        existing_public.get("panel_id") != PANEL_ID
        or existing_public.get("precommitment_sha256")
        != precommit.get("precommitment_sha256")
    ):
        raise ValueError("Public results do not match the execution contract")

    pinned_environment = private.get("execution_environment")
    panel_started_at = private.get("panel_started_at_utc")
    if pinned_environment is None and panel_started_at is None:
        if existing_public is not None:
            raise ValueError("Public results have no authoritative private run state")
        pinned_environment = dict(current_environment)
        panel_started_at = _utc_now()
        private["execution_environment"] = pinned_environment
        private["panel_started_at_utc"] = panel_started_at
    elif not isinstance(pinned_environment, dict) or not isinstance(
        panel_started_at, str
    ):
        raise ValueError("Private run state is incomplete")
    _require_same_execution_environment(pinned_environment, current_environment)

    if private.get("status") == "blocked_infrastructure":
        raise RuntimeError("This panel was retired after an infrastructure failure")
    if private.get("status") == "complete":
        completed_at = private.get("panel_completed_at_utc")
        if len(reconstructed) != len(EPISODE_REFS) or not isinstance(
            completed_at, str
        ):
            raise ValueError("Private completed state is incomplete")
        expected = _complete_public_artifact(
            precommit=precommit,
            execution_environment=pinned_environment,
            started_at_utc=panel_started_at,
            completed_at_utc=completed_at,
            results=reconstructed,
            master=master,
        )
        if existing_public is not None and existing_public.get("status") == "complete":
            if existing_public != expected:
                raise ValueError("Completed public results differ from private state")
            return existing_public
        _atomic_json(public_results_path, expected)
        return expected
    if existing_public is not None and existing_public.get("status") == "complete":
        raise ValueError("Public results claim completion before private state")
    if private.get("status") not in {"prepared", "running"}:
        raise ValueError("Private run state has an invalid status")

    # Rebuild the public artifact exclusively from immutable precommitment and
    # owner-only checkpoint state. Stale or injected partial fields never flow
    # into a later artifact or its final digest.
    public = _running_public_artifact(
        precommit=precommit,
        execution_environment=pinned_environment,
        started_at_utc=panel_started_at,
        completed_assignments=len(reconstructed),
    )
    private["status"] = "running"
    _atomic_json(private_manifest_path, private, private=True)
    _atomic_json(public_results_path, public)

    completed = {str(item["episode_ref"]) for item in private["assignments"]}
    timeout = int(precommit["run_contract"]["timeout_seconds_per_assignment"])
    budget = float(
        precommit["run_contract"]["claude_max_budget_usd_per_assignment"]
    )
    pinned_claude_version = str(
        precommit["run_contract"]["claude_cli_version"]
    )
    private_by_ref = {
        str(item["episode_ref"]): item for item in private["episodes"]
    }
    for episode in precommit["episodes"]:
        ref = str(episode["episode_ref"])
        if ref in completed:
            continue
        private_episode = private_by_ref[ref]
        try:
            _require_claude_version(pinned_claude_version)
        except Exception as error:
            private["status"] = "blocked_infrastructure"
            public = _running_public_artifact(
                precommit=precommit,
                execution_environment=pinned_environment,
                started_at_utc=panel_started_at,
                completed_assignments=len(private["assignments"]),
            )
            public["status"] = "blocked_infrastructure"
            public["infrastructure_error_type"] = type(error).__name__
            _atomic_json(private_manifest_path, private, private=True)
            _atomic_json(public_results_path, public)
            raise RuntimeError(
                "Pilot stopped because the pinned Claude CLI was unavailable or drifted"
            ) from error
        assignment_started_at = _utc_now()
        marker: dict[str, Any] = {
            "episode_ref": ref,
            "system": SYSTEM,
            "status": "in_progress",
            "started_at_utc": assignment_started_at,
        }
        private["assignments"].append(marker)
        public = _running_public_artifact(
            precommit=precommit,
            execution_environment=pinned_environment,
            started_at_utc=panel_started_at,
            completed_assignments=len(private["assignments"]) - 1,
            running_assignment=marker,
        )
        _atomic_json(private_manifest_path, private, private=True)
        _atomic_json(public_results_path, public)
        print(f"START {ref} {SYSTEM} {assignment_started_at}", flush=True)
        secret = _derive_secret(
            master, str(private_episode["family"]), int(private_episode["seed"])
        )
        try:
            result = evaluate_local_cli_agent(
                SYSTEM,
                seed=int(private_episode["seed"]),
                family=str(private_episode["family"]),
                backend=BACKEND,
                episode_secret=secret,
                model=REQUESTED_MODEL,
                executable=CLAUDE_EXECUTABLE,
                timeout_seconds=timeout,
                claude_max_budget_usd=budget,
                claude_effort=CLAUDE_EFFORT,
            )
            _raise_on_opus_startup_failure(result)
            if result.cli_version != pinned_claude_version:
                raise RuntimeError("Claude CLI version changed during an assignment")
            finished_at = _utc_now()
            marker["raw_result"] = asdict(result)
            sanitized = _sanitize_result(
                episode=private_episode,
                result=result,
                started_at=assignment_started_at,
                finished_at=finished_at,
            )
        except Exception as error:
            marker["error_type"] = type(error).__name__
            marker["error"] = str(error)
            private["status"] = "blocked_infrastructure"
            public = _running_public_artifact(
                precommit=precommit,
                execution_environment=pinned_environment,
                started_at_utc=panel_started_at,
                completed_assignments=len(private["assignments"]) - 1,
                running_assignment=marker,
            )
            public["status"] = "blocked_infrastructure"
            public["infrastructure_error_type"] = type(error).__name__
            _atomic_json(private_manifest_path, private, private=True)
            _atomic_json(public_results_path, public)
            raise RuntimeError(
                "Pilot stopped on infrastructure failure; the started assignment "
                "cannot be retried and this panel is retired"
            ) from error
        marker["status"] = "complete"
        marker["finished_at_utc"] = finished_at
        marker["public_result"] = sanitized
        private["status"] = "running"
        _atomic_json(private_manifest_path, private, private=True)
        completed_results = _reconstruct_public_results(private["assignments"])
        public = _running_public_artifact(
            precommit=precommit,
            execution_environment=pinned_environment,
            started_at_utc=panel_started_at,
            completed_assignments=len(completed_results),
        )
        _atomic_json(public_results_path, public)
        print(
            f"DONE {ref} {SYSTEM} total={sanitized['total']} "
            f"valid={sanitized['valid']} receipt={sanitized['exact_model_receipt']}",
            flush=True,
        )

    completed_results = _reconstruct_public_results(private["assignments"])
    if len(completed_results) != len(EPISODE_REFS):
        raise RuntimeError("Pilot did not complete all five assignments")
    private["status"] = "complete"
    private["panel_completed_at_utc"] = _utc_now()
    _atomic_json(private_manifest_path, private, private=True)
    public = _complete_public_artifact(
        precommit=precommit,
        execution_environment=pinned_environment,
        started_at_utc=panel_started_at,
        completed_at_utc=private["panel_completed_at_utc"],
        results=completed_results,
        master=master,
    )
    _atomic_json(public_results_path, public)
    return public
