"""Precommitted, development-only full-system pilot orchestration.

This module deliberately does not turn the local CLI runner into a leaderboard
harness.  It adds a small, auditable batch contract around that runner: five
outcome-independent paired episodes, a private replay secret, public
commitments, fixed execution order, no retries, and fixed-denominator summary
statistics.  Provider CLIs still execute on the host with network access.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import platform
import secrets
import shutil
import statistics
import subprocess
import sys
from typing import Any, Mapping, Sequence

from .pilot import (
    DEFAULT_EXECUTABLES,
    DEFAULT_MODELS,
    PilotRunResult,
    _task_prompt,
    evaluate_local_cli_agent,
)


PANEL_ID = "development-paired-pilot-v1-2026-07-15"
BACKEND = "starsim-ltc-v3"
SCHEMA_VERSION = "development_pilot_v1"
SYSTEMS = ("codex", "claude", "cursor")
DIMENSION_MAXIMA: Mapping[str, float] = {
    "classification": 15.0,
    "line_list": 15.0,
    "hypothesis": 10.0,
    "response_utility": 25.0,
    "evidence": 10.0,
    "efficiency": 10.0,
    "handoff": 5.0,
    "prospective_forecast": 10.0,
}

# The seeds are derived without consulting simulator outcomes:
# int(SHA256("epiagentbench:development-panel:v1:" + family)[:13], 16).
PANEL: tuple[Mapping[str, Any], ...] = (
    {
        "episode_ref": "episode_01",
        "family": "institution_person_to_person",
        "seed": 869_997_555_248_999,
        "system_order": ("codex", "claude", "cursor"),
    },
    {
        "episode_ref": "episode_02",
        "family": "restaurant_point_source",
        "seed": 3_587_291_329_036_030,
        "system_order": ("claude", "cursor", "codex"),
    },
    {
        "episode_ref": "episode_03",
        "family": "repeated_introduction",
        "seed": 63_387_777_727_111,
        "system_order": ("cursor", "codex", "claude"),
    },
    {
        "episode_ref": "episode_04",
        "family": "coincidental_venue",
        "seed": 4_399_268_858_818_360,
        "system_order": ("codex", "cursor", "claude"),
    },
    {
        "episode_ref": "episode_05",
        "family": "reporting_artifact",
        "seed": 1_325_512_106_057_381,
        "system_order": ("cursor", "claude", "codex"),
    },
)

_PUBLIC_METRICS = (
    "integrity_pass",
    "brier",
    "case_f1",
    "correct_hypothesis_probability",
    "hypothesis_multiclass_brier",
    "provenance_precision",
    "decisive_evidence_recall",
    "forecast_submissions",
    "forecast_mean_absolute_error",
    "tool_calls",
    "analyst_minutes",
    "operational_credits",
    "privacy_units",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")


def _sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _file_sha256(path: Path) -> str:
    return _sha256(path.read_bytes())


def _atomic_json(path: Path, value: Any, *, private: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        0o600 if private else 0o644,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise
    os.chmod(temporary, 0o600 if private else 0o644)
    os.replace(temporary, path)


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def _derive_secret(master: bytes, family: str, seed: int) -> bytes:
    message = f"{family}|{seed}".encode("ascii")
    return hmac.new(master, message, hashlib.sha256).digest()


def _derived_seed(family: str) -> int:
    digest = hashlib.sha256(
        f"epiagentbench:development-panel:v1:{family}".encode("ascii")
    ).hexdigest()
    return int(digest[:13], 16)


def _git_output(root: Path, *args: str) -> str:
    process = subprocess.run(
        ["git", *args],
        cwd=root,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=20,
    )
    if process.returncode != 0:
        raise RuntimeError(
            process.stderr.decode("utf-8", errors="replace").strip()
            or "git command failed"
        )
    return process.stdout.decode("utf-8", errors="strict").strip()


def _source_hashes(root: Path) -> dict[str, str]:
    schema = root / "schemas" / "submission.schema.json"
    pilot = root / "src" / "epiagentbench" / "pilot.py"
    development_pilot = root / "src" / "epiagentbench" / "development_pilot.py"
    return {
        "development_pilot_module": _file_sha256(development_pilot),
        "pilot_module": _file_sha256(pilot),
        "submission_schema": _file_sha256(schema),
        "task_prompt": _sha256(_task_prompt().encode("utf-8")),
    }


def _validate_panel() -> None:
    if sum(DIMENSION_MAXIMA.values()) != 100.0:
        raise RuntimeError("Score dimensions no longer sum to 100")
    if len(PANEL) != 5:
        raise RuntimeError("Development panel must have exactly five episodes")
    for episode in PANEL:
        family = str(episode["family"])
        if int(episode["seed"]) != _derived_seed(family):
            raise RuntimeError(f"Outcome-independent seed mismatch: {family}")
        if set(episode["system_order"]) != set(SYSTEMS):
            raise RuntimeError(f"Invalid execution order: {family}")


def prepare_panel(
    *,
    root: Path,
    private_manifest_path: Path,
    public_manifest_path: Path,
    timeout_seconds: int = 900,
    claude_max_budget_usd: float = 2.0,
) -> dict[str, Any]:
    """Create a private replay manifest and its public precommitment."""

    _validate_panel()
    if _git_output(root, "status", "--porcelain", "--untracked-files=all"):
        raise RuntimeError(
            "Commit and clean the pilot harness before preparing episode commitments"
        )
    if private_manifest_path.exists() or public_manifest_path.exists():
        raise FileExistsError("Refusing to replace an existing pilot manifest")
    if not 1 <= timeout_seconds <= 3600:
        raise ValueError("timeout_seconds must be between 1 and 3600")
    if not 0 < claude_max_budget_usd <= 100:
        raise ValueError("Invalid Claude budget")

    master = secrets.token_bytes(32)
    episodes: list[dict[str, Any]] = []
    private_episodes: list[dict[str, Any]] = []
    for episode in PANEL:
        secret = _derive_secret(
            master, str(episode["family"]), int(episode["seed"])
        )
        public_episode = {
            "episode_ref": episode["episode_ref"],
            "family": episode["family"],
            "seed_derivation": (
                "int(sha256('epiagentbench:development-panel:v1:' + family)"
                ".hexdigest()[:13], 16)"
            ),
            "episode_secret_commitment": _sha256(secret),
            "system_order": list(episode["system_order"]),
        }
        episodes.append(public_episode)
        private_episodes.append(
            {
                **public_episode,
                "seed": episode["seed"],
            }
        )

    base_commit = _git_output(root, "rev-parse", "HEAD")
    run_contract = {
        "backend": BACKEND,
        "timeout_seconds_per_assignment": timeout_seconds,
        "claude_max_budget_usd_per_assignment": claude_max_budget_usd,
        "requested_models": dict(DEFAULT_MODELS),
        "executables": dict(DEFAULT_EXECUTABLES),
        "reasoning_configuration": {
            "codex": "medium",
            "claude": "provider default under explicit USD cap",
            "cursor": "native high model alias",
        },
        "retry_policy": "no retries after an assignment starts",
        "failure_policy": (
            "evaluator-returned timeouts, invalid submissions, and detected model "
            "fallbacks remain in the fixed denominator with score zero; missing "
            "independent model receipts are reported separately; infrastructure or "
            "harness exceptions abort the panel and are not model scores"
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
        "scientific_claim": (
            "five-episode paired integration pilot; descriptive only, not a model ranking"
        ),
        "benchmark_base_commit": base_commit,
        "source_hashes": _source_hashes(root),
        "panel_master_secret_commitment": _sha256(master),
        "episodes": episodes,
        "score_dimension_maxima": dict(DIMENSION_MAXIMA),
        "run_contract": run_contract,
        "planned_assignments": len(PANEL) * len(SYSTEMS),
        "results": [],
        "limitations": [
            "host-networked provider CLIs; execution is not hermetic",
            "requested model identity is not independently signed",
            "unequal provider-native reasoning and billing controls",
            "synthetic LTC-v3 development episodes are not externally calibrated",
            "one episode per causal family is too small for uncertainty estimates",
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


def _attribution(result: PilotRunResult) -> str:
    if any(
        event in {
            "agent_failure:model_fallback",
            "agent_failure:model_unverified",
        }
        for event in result.audit_events
    ):
        return "failed"
    if not result.observed_models:
        return "requested_only_unverified"
    requested = "".join(
        character
        for character in result.requested_model.lower()
        if character.isalnum()
    )
    observed = {
        "".join(character for character in model.lower() if character.isalnum())
        for model in result.observed_models
    }
    if observed == {requested}:
        return "provider_reported_match"
    return "provider_reported_nonexact"


def _sanitize_result(
    *,
    episode: Mapping[str, Any],
    result: PilotRunResult,
    started_at: str,
    finished_at: str,
) -> dict[str, Any]:
    scorecard = result.scorecard
    metrics = scorecard.get("metrics", {})
    dimensions = scorecard.get("dimensions", {})
    valid = bool(scorecard.get("valid", False))
    total = float(scorecard.get("total", 0.0)) if valid else 0.0
    return {
        "episode_ref": episode["episode_ref"],
        "family": episode["family"],
        "system": result.system,
        "started_at_utc": started_at,
        "finished_at_utc": finished_at,
        "requested_model": result.requested_model,
        "observed_models": list(result.observed_models),
        "model_attribution": _attribution(result),
        "cli_version": result.cli_version,
        "development_only": result.development_only,
        "hermetic": result.hermetic,
        "returncode": result.returncode,
        "elapsed_seconds": result.elapsed_seconds,
        "valid": valid,
        "total": total,
        "dimensions": {
            name: float(dimensions.get(name, 0.0)) if valid else 0.0
            for name in DIMENSION_MAXIMA
        },
        "metrics": {
            name: metrics[name]
            for name in _PUBLIC_METRICS
            if name in metrics
        },
        "violations": list(scorecard.get("violations", [])),
        "audit_events": list(result.audit_events),
        "stdout_bytes": result.stdout_bytes,
        "stderr_bytes": result.stderr_bytes,
    }


def aggregate_results(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate every planned assignment; invalid runs retain zero points."""

    keyed: dict[tuple[str, str], Mapping[str, Any]] = {}
    expected_refs = {str(episode["episode_ref"]) for episode in PANEL}
    for result in results:
        key = (str(result.get("episode_ref")), str(result.get("system")))
        if key[0] not in expected_refs or key[1] not in SYSTEMS:
            raise ValueError(f"Unexpected pilot result key: {key}")
        if key in keyed:
            raise ValueError(f"Duplicate pilot result key: {key}")
        keyed[key] = result

    summary: dict[str, Any] = {}
    for system in SYSTEMS:
        selected = [
            keyed[(str(episode["episode_ref"]), system)]
            for episode in PANEL
            if (str(episode["episode_ref"]), system) in keyed
        ]
        planned = [
            keyed.get((str(episode["episode_ref"]), system)) for episode in PANEL
        ]
        totals = [
            float(result.get("total", 0.0)) if result is not None else 0.0
            for result in planned
        ]
        attribution_counts = Counter(
            str(result.get("model_attribution", "failed")) for result in selected
        )
        audit_counts = Counter(
            str(event)
            for result in selected
            for event in result.get("audit_events", [])
        )
        summary[system] = {
            "planned": len(PANEL),
            "completed": len(selected),
            "valid": sum(bool(result.get("valid")) for result in selected),
            "integrity_pass": sum(
                result.get("metrics", {}).get("integrity_pass") is True
                for result in selected
            ),
            "attribution": dict(sorted(attribution_counts.items())),
            "mean_total": round(statistics.fmean(totals), 3),
            "median_total": round(statistics.median(totals), 3),
            "mean_dimensions": {
                name: round(
                    statistics.fmean(
                        float(result.get("dimensions", {}).get(name, 0.0))
                        if result is not None
                        else 0.0
                        for result in planned
                    ),
                    3,
                )
                for name in DIMENSION_MAXIMA
            },
            "median_elapsed_seconds": round(
                statistics.median(
                    float(result.get("elapsed_seconds", 0.0)) for result in selected
                ),
                3,
            )
            if selected
            else None,
            "audit_event_counts": dict(sorted(audit_counts.items())),
        }
    return summary


def _validate_commitments(
    private: Mapping[str, Any], public: Mapping[str, Any], *, root: Path
) -> bytes:
    _validate_panel()
    if private.get("panel_id") != PANEL_ID or public.get("panel_id") != PANEL_ID:
        raise ValueError("Pilot manifest belongs to another panel")
    if private.get("public_precommitment_sha256") != public.get(
        "precommitment_sha256"
    ):
        raise ValueError("Public precommitment does not match the private manifest")
    if public.get("status") != "precommitted" or public.get("results") != []:
        raise ValueError("Public pilot precommitment must remain immutable")
    unsigned = dict(public)
    supplied = unsigned.pop("precommitment_sha256", None)
    if supplied != _sha256(_canonical_bytes(unsigned)):
        raise ValueError("Public pilot precommitment is invalid")
    if public.get("source_hashes") != _source_hashes(root):
        raise ValueError("Executed pilot source does not match the precommitment")
    run_contract = public.get("run_contract")
    if not isinstance(run_contract, dict):
        raise ValueError("Public precommitment has no run contract")
    if (
        run_contract.get("backend") != BACKEND
        or run_contract.get("requested_models") != dict(DEFAULT_MODELS)
        or run_contract.get("executables") != dict(DEFAULT_EXECUTABLES)
    ):
        raise ValueError("Pilot run contract does not match the fixed harness")
    master_hex = private.get("master_secret_hex")
    if not isinstance(master_hex, str):
        raise ValueError("Private manifest has no master secret")
    master = bytes.fromhex(master_hex)
    if _sha256(master) != public.get("panel_master_secret_commitment"):
        raise ValueError("Panel master-secret commitment mismatch")
    public_episodes = public.get("episodes")
    private_episodes = private.get("episodes")
    if not isinstance(public_episodes, list) or not isinstance(private_episodes, list):
        raise ValueError("Pilot episode manifests must be arrays")
    if len(public_episodes) != len(PANEL) or len(private_episodes) != len(PANEL):
        raise ValueError("Pilot episode manifest has the wrong cardinality")
    for expected, public_episode, private_episode in zip(
        PANEL, public_episodes, private_episodes, strict=True
    ):
        ref = str(expected["episode_ref"])
        if (
            public_episode.get("episode_ref") != ref
            or private_episode.get("episode_ref") != ref
            or public_episode.get("family") != expected["family"]
            or private_episode.get("family") != expected["family"]
            or public_episode.get("system_order") != list(expected["system_order"])
            or private_episode.get("system_order") != list(expected["system_order"])
            or private_episode.get("seed") != expected["seed"]
        ):
            raise ValueError(f"Pilot episode contract mismatch: {ref}")
        secret = _derive_secret(
            master,
            str(private_episode["family"]),
            int(private_episode["seed"]),
        )
        if (
            _sha256(secret) != public_episode.get("episode_secret_commitment")
            or private_episode.get("episode_secret_commitment")
            != public_episode.get("episode_secret_commitment")
        ):
            raise ValueError(f"Episode-secret commitment mismatch: {ref}")
    return master


def _execution_environment(root: Path) -> dict[str, Any]:
    try:
        import starsim  # type: ignore

        starsim_version = str(getattr(starsim, "__version__", "unknown"))
    except ImportError:
        starsim_version = "unavailable"
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
        "sandbox": "provider CLI-specific local restrictions; not hermetic",
        "executables_available": {
            system: bool(shutil.which(executable))
            for system, executable in DEFAULT_EXECUTABLES.items()
        },
    }


def _relative_to_root(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError as error:
        raise ValueError("Pilot artifacts must be inside the repository") from error


def _reconstruct_public_results(
    assignments: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    expected = [
        (str(episode["episode_ref"]), str(system))
        for episode in PANEL
        for system in episode["system_order"]
    ]
    if len(assignments) > len(expected):
        raise ValueError("Private pilot state contains too many assignments")
    reconstructed: list[dict[str, Any]] = []
    for index, assignment in enumerate(assignments):
        key = (str(assignment.get("episode_ref")), str(assignment.get("system")))
        if key != expected[index]:
            raise ValueError("Private pilot assignments do not follow the fixed order")
        status = assignment.get("status")
        if status == "in_progress":
            raise RuntimeError(
                "A prior assignment was interrupted after starting; no-retry policy blocks resume"
            )
        if status != "complete" or not isinstance(
            assignment.get("public_result"), dict
        ):
            raise ValueError("Completed assignment has no reconstructable public result")
        public_result = dict(assignment["public_result"])
        if (
            str(public_result.get("episode_ref")),
            str(public_result.get("system")),
        ) != key:
            raise ValueError("Private and public result keys disagree")
        reconstructed.append(public_result)
    aggregate_results(reconstructed)
    return reconstructed


def _preflight_execution(
    *,
    root: Path,
    private_manifest_path: Path,
    public_manifest_path: Path,
    public_results_path: Path,
    public_results_exists: bool,
) -> dict[str, Any]:
    public_relative = _relative_to_root(public_manifest_path, root)
    private_relative = _relative_to_root(private_manifest_path, root)
    results_relative = _relative_to_root(public_results_path, root)
    tracked = _git_output(root, "ls-files", "--error-unmatch", public_relative)
    if tracked != public_relative:
        raise RuntimeError("Public precommitment has not been committed")
    if _git_output(root, "ls-files", private_relative):
        raise RuntimeError("Private replay manifest must never be tracked")
    if os.stat(private_manifest_path).st_mode & 0o077:
        raise RuntimeError("Private replay manifest permissions are too broad")
    environment = _execution_environment(root)
    expected_dirty = f"?? {results_relative}" if public_results_exists else ""
    if str(environment["git_status_at_start"]) != expected_dirty:
        raise RuntimeError("Execution worktree is not clean")
    if environment["starsim"] != "3.5.1":
        raise RuntimeError("The predeclared Starsim 3.5.1 runtime is unavailable")
    unavailable = [
        system
        for system, available in environment["executables_available"].items()
        if not available
    ]
    if unavailable:
        raise RuntimeError("Required provider CLIs are unavailable: " + ", ".join(unavailable))
    return environment


def run_panel(
    *,
    root: Path,
    private_manifest_path: Path,
    public_manifest_path: Path,
    public_results_path: Path,
) -> dict[str, Any]:
    """Run or resume the fixed panel without retrying a started assignment."""

    private = _load_json(private_manifest_path)
    precommit = _load_json(public_manifest_path)
    master = _validate_commitments(private, precommit, root=root)
    reconstructed = _reconstruct_public_results(private["assignments"])
    results_exists = public_results_path.exists()
    environment = _preflight_execution(
        root=root,
        private_manifest_path=private_manifest_path,
        public_manifest_path=public_manifest_path,
        public_results_path=public_results_path,
        public_results_exists=results_exists,
    )
    base_commit = str(precommit["benchmark_base_commit"])
    _git_output(root, "merge-base", "--is-ancestor", base_commit, "HEAD")

    if results_exists:
        public = _load_json(public_results_path)
        if (
            public.get("panel_id") != PANEL_ID
            or public.get("precommitment_sha256")
            != precommit.get("precommitment_sha256")
            or public.get("execution_environment", {}).get("execution_commit")
            != environment["execution_commit"]
        ):
            raise ValueError("Public results do not match this execution contract")
        if public.get("status") == "complete":
            if len(reconstructed) != len(PANEL) * len(SYSTEMS):
                raise ValueError("Completed results do not contain every assignment")
            return public
    else:
        public = {
            "schema_version": SCHEMA_VERSION,
            "panel_id": PANEL_ID,
            "precommitment_sha256": precommit["precommitment_sha256"],
            "development_only": True,
            "leaderboard_eligible": False,
            "hermetic": False,
            "status": "running",
            "started_at_utc": _utc_now(),
            "execution_environment": environment,
            "run_contract": precommit["run_contract"],
            "score_dimension_maxima": precommit["score_dimension_maxima"],
            "planned_assignments": precommit["planned_assignments"],
            "limitations": precommit["limitations"],
        }
    public.pop("running_assignment", None)
    public.pop("infrastructure_error_type", None)
    public["status"] = "running"
    public["results"] = reconstructed
    public["summary"] = aggregate_results(reconstructed)
    private["status"] = "running"
    _atomic_json(private_manifest_path, private, private=True)
    _atomic_json(public_results_path, public)

    completed = {
        (str(item["episode_ref"]), str(item["system"]))
        for item in private["assignments"]
        if item.get("status") == "complete"
    }
    timeout_seconds = int(
        precommit["run_contract"]["timeout_seconds_per_assignment"]
    )
    claude_budget = float(
        precommit["run_contract"]["claude_max_budget_usd_per_assignment"]
    )

    private_by_ref = {
        str(episode["episode_ref"]): episode for episode in private["episodes"]
    }
    for episode in precommit["episodes"]:
        ref = str(episode["episode_ref"])
        private_episode = private_by_ref[ref]
        secret = _derive_secret(
            master,
            str(private_episode["family"]),
            int(private_episode["seed"]),
        )
        for system in episode["system_order"]:
            key = (ref, str(system))
            if key in completed:
                continue
            started_at = _utc_now()
            marker = {
                "episode_ref": ref,
                "system": system,
                "status": "in_progress",
                "started_at_utc": started_at,
            }
            private["assignments"].append(marker)
            public["running_assignment"] = {
                "episode_ref": ref,
                "system": system,
                "started_at_utc": started_at,
            }
            _atomic_json(private_manifest_path, private, private=True)
            _atomic_json(public_results_path, public)
            print(f"START {ref} {system} {started_at}", flush=True)
            try:
                result = evaluate_local_cli_agent(
                    str(system),
                    seed=int(private_episode["seed"]),
                    family=str(private_episode["family"]),
                    backend=BACKEND,
                    episode_secret=secret,
                    timeout_seconds=timeout_seconds,
                    claude_max_budget_usd=claude_budget,
                )
                finished_at = _utc_now()
                marker["raw_result"] = asdict(result)
                sanitized = _sanitize_result(
                    episode=episode,
                    result=result,
                    started_at=started_at,
                    finished_at=finished_at,
                )
            except Exception as error:
                marker["status"] = "in_progress"
                marker["error_type"] = type(error).__name__
                marker["error"] = str(error)
                public["status"] = "blocked_infrastructure"
                public["infrastructure_error_type"] = type(error).__name__
                _atomic_json(private_manifest_path, private, private=True)
                _atomic_json(public_results_path, public)
                raise RuntimeError(
                    "Pilot stopped on an infrastructure error; the started assignment "
                    "cannot be retried under this panel contract"
                ) from error
            marker["status"] = "complete"
            marker["finished_at_utc"] = finished_at
            marker["public_result"] = sanitized
            public.pop("running_assignment", None)
            _atomic_json(private_manifest_path, private, private=True)
            completed.add(key)
            public["results"] = _reconstruct_public_results(private["assignments"])
            public["summary"] = aggregate_results(public["results"])
            _atomic_json(public_results_path, public)
            print(
                f"DONE {ref} {system} total={sanitized['total']} "
                f"valid={sanitized['valid']} attribution={sanitized['model_attribution']}",
                flush=True,
            )

    expected_count = len(PANEL) * len(SYSTEMS)
    public["results"] = _reconstruct_public_results(private["assignments"])
    if len(public["results"]) != expected_count:
        raise RuntimeError("Pilot did not complete every predeclared assignment")
    public["status"] = "complete"
    public["completed_at_utc"] = _utc_now()
    public["panel_retired_after_publication"] = True
    public["summary"] = aggregate_results(public["results"])
    unsigned = dict(public)
    unsigned.pop("results_sha256", None)
    public["results_sha256"] = _sha256(_canonical_bytes(unsigned))
    private["status"] = "complete"
    _atomic_json(private_manifest_path, private, private=True)
    _atomic_json(public_results_path, public)
    return public
