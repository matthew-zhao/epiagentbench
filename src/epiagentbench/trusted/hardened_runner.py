"""Linux-only execution of one authenticated frozen episode pack.

The evaluator opens private pack material on the host, validates exact frozen
cohort membership, and launches a broker that exposes only the public Unix
socket.  The untrusted image receives no private file, evaluator source, admin
channel, host network, or Docker socket.  This runner intentionally supports
offline images only.  Online model access remains disabled until a real
inference proxy can produce an independently verified policy attestation.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import hmac
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
from typing import Any, Mapping, NoReturn, Sequence

from .cohort_freezer import CohortFreezeError, compute_generator_fingerprint
from .episode_pack import (
    EpisodePackError,
    PrivateEpisodeCohortManifest,
    PrivateEpisodePack,
)
from .hardened_snapshot import (
    AuthenticatedTrace,
    HardenedSnapshotPlan,
    InferenceProxyPolicy,
    SnapshotLimits,
    SnapshotPlanError,
)
from .sandbox import _collect_bounded, _force_remove_container, _score_agent_output
from .service import SecureEpisodeSession, launch_socket_episode


_MAX_PRIVATE_FILE_BYTES = 4_194_304
_MAX_PLAN_BYTES = 262_144
_RUNNER_VERSION = "frozen-offline-runner-0.1"


class HardenedRunnerUnavailableError(RuntimeError):
    """Raised when the Linux/Docker runner cannot be used."""


class HardenedRunnerError(RuntimeError):
    """Raised when a frozen run cannot preserve its security contract."""


@dataclass(frozen=True, slots=True)
class FrozenEpisodeExecutionResult:
    """Public result plus authenticated evidence; never includes raw stderr."""

    submission: dict[str, Any]
    scorecard: dict[str, Any]
    audit_events: tuple[str, ...]
    trace_events: tuple[dict[str, Any], ...]
    receipt: dict[str, Any]
    receipt_path: str


def load_hardened_snapshot_plan(
    path: str | Path, *, expected_commitment: str
) -> HardenedSnapshotPlan:
    """Strictly load a public plan and require its externally pinned hash."""

    source = Path(path)
    try:
        payload = source.read_bytes()
    except OSError:
        raise HardenedRunnerError("Snapshot plan is unavailable") from None
    if not 0 < len(payload) <= _MAX_PLAN_BYTES:
        raise HardenedRunnerError("Invalid snapshot plan")
    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise HardenedRunnerError("Invalid snapshot plan") from None
    plan = _plan_from_dict(value)
    if not isinstance(expected_commitment, str) or not hmac.compare_digest(
        plan.commitment, expected_commitment
    ):
        raise HardenedRunnerError("Snapshot plan commitment mismatch")
    return plan


def execute_frozen_episode(
    *,
    plan: HardenedSnapshotPlan,
    pack_path: str | Path,
    manifest_path: str | Path,
    pack_authentication_key: bytes,
    expected_pack_set_commitment: str,
    expected_generator_fingerprint: str,
    receipt_authentication_key: bytes,
    receipt_path: str | Path,
    docker: str = "docker",
) -> FrozenEpisodeExecutionResult:
    """Validate, execute, score, and receipt one frozen offline episode.

    No secret is placed in the container command or environment.  A failed or
    malformed container submission is still scored through the normal trusted
    evaluator and receives a receipt.  Failures before an evaluator exists
    fail closed without starting Docker.
    """

    executable = _validate_execution_boundary(plan, docker)
    _validate_authentication_key(
        pack_authentication_key, label="pack authentication"
    )
    _validate_authentication_key(
        receipt_authentication_key, label="receipt authentication"
    )
    pack = PrivateEpisodePack.unseal(
        _read_private_file(pack_path), pack_authentication_key
    )
    manifest = PrivateEpisodeCohortManifest.unseal(
        _read_private_file(manifest_path), pack_authentication_key
    )
    installed_generator_fingerprint = _installed_generator_fingerprint()
    if not isinstance(expected_generator_fingerprint, str) or not hmac.compare_digest(
        installed_generator_fingerprint, expected_generator_fingerprint
    ):
        raise HardenedRunnerError(
            "Installed generator fingerprint differs from the published value"
        )
    launch = pack.launch_kwargs(
        expected_generator_fingerprint=installed_generator_fingerprint,
        cohort_manifest=manifest,
        expected_pack_set_commitment=expected_pack_set_commitment,
    )

    trace = AuthenticatedTrace(plan.run_id)
    trace.append(
        "pack_validated",
        {
            "episode_commitment": pack.commitment,
            "pack_set_commitment": manifest.pack_set_commitment,
            "generator_fingerprint": installed_generator_fingerprint,
            "installed_generator_recomputed": True,
        },
    )

    broker_directory = Path(plan.broker_directory)
    receipt_destination = _validate_new_private_path(receipt_path)
    try:
        receipt_destination.relative_to(broker_directory)
    except ValueError:
        pass
    else:
        raise HardenedRunnerError("Receipt must be outside the ephemeral broker")
    session: SecureEpisodeSession | None = None
    process: subprocess.Popen[bytes] | None = None
    container_launched = False
    container_run_complete = False
    environment = {"PATH": os.environ.get("PATH", os.defpath)}
    stdout = b""
    stderr = b""
    outcome = "launch_error"
    returncode: int | None = None
    audit_events: list[str] = []
    try:
        _create_broker_directory(broker_directory)
        socket_path = broker_directory / "episode.sock"
        session = launch_socket_episode(
            public_socket_path=str(socket_path),
            **launch,
        )
        if not hmac.compare_digest(
            _installed_generator_fingerprint(),
            installed_generator_fingerprint,
        ):
            raise HardenedRunnerError(
                "Installed generator changed while starting the evaluator"
            )
        _grant_broker_access(broker_directory, socket_path, plan)
        _verify_broker_boundary(broker_directory, socket_path, plan)
        trace.append(
            "evaluator_started",
            {"public_socket_only": True, "broker_mount": "/broker:ro"},
        )

        command = plan.docker_argv(executable)
        _assert_no_private_material(command, pack, pack_path, manifest_path)
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=environment,
                close_fds=True,
            )
            container_launched = True
            trace.append(
                "container_started",
                {
                    "image_digest": plan.image_digest,
                    "network_mode": plan.network_mode,
                },
            )
            stdout, stderr, outcome = _collect_bounded(
                process, timeout_seconds=plan.limits.timeout_seconds
            )
            container_run_complete = True
            returncode = process.returncode
        except OSError:
            audit_events.append("sandbox_failure:launch_error")

        if process is not None:
            if outcome != "ok":
                audit_events.append(f"sandbox_resource_limit:{outcome}")
                _force_remove_container(
                    executable, f"eab-{plan.run_id}", environment
                )
            elif returncode != 0:
                audit_events.append("sandbox_failure:nonzero_exit")

        try:
            _verify_broker_boundary(broker_directory, socket_path, plan)
        except HardenedRunnerError:
            audit_events.append("sandbox_escape:broker_boundary_tampered")

        execution_record = {
            "outcome": outcome,
            "returncode": returncode,
            "stdout_bytes": len(stdout),
            "stderr_bytes": len(stderr),
            "stdout_sha256": _sha256(stdout),
            "stderr_sha256": _sha256(stderr),
        }
        trace.append("container_finished", execution_record)

        if session is None:  # Defensive; launch failures above already raise.
            raise HardenedRunnerError("Trusted evaluator was not created")
        submission, scorecard = _score_agent_output(
            session=session,
            stdout=stdout,
            stderr=stderr,
            audit_events=audit_events,
        )
        scorecard_bytes = _canonical_json(scorecard)
        submission_bytes = _canonical_json(submission)
        execution_bytes = _canonical_json(execution_record)
        trace.append(
            "episode_scored",
            {
                "valid": scorecard.get("valid") is True,
                "total": scorecard.get("total"),
                "scorecard_sha256": _sha256(scorecard_bytes),
                "submission_sha256": _sha256(submission_bytes),
            },
        )

        embedded_identity = f"offline-image:{plan.image_digest}"
        receipt = trace.receipt(
            authentication_key=receipt_authentication_key,
            episode_commitment=pack.commitment,
            plan=plan,
            requested_model=embedded_identity,
            observed_model=embedded_identity,
            runner_version=_RUNNER_VERSION,
            artifact_hashes={
                "execution": _sha256(execution_bytes),
                "scorecard": _sha256(scorecard_bytes),
                "stderr": _sha256(stderr),
                "stdout": _sha256(stdout),
                "submission": _sha256(submission_bytes),
            },
        )
        written = _write_private_new_file(
            receipt_destination, _canonical_json(receipt)
        )
        return FrozenEpisodeExecutionResult(
            submission=submission,
            scorecard=scorecard,
            audit_events=tuple(audit_events),
            trace_events=trace.events,
            receipt=receipt,
            receipt_path=str(written),
        )
    finally:
        try:
            if (
                container_launched
                and not container_run_complete
                and process is not None
            ):
                _force_remove_container(
                    executable, f"eab-{plan.run_id}", environment
                )
        finally:
            try:
                if session is not None:
                    session.close()
            finally:
                shutil.rmtree(broker_directory, ignore_errors=True)


def _validate_execution_boundary(
    plan: HardenedSnapshotPlan, docker: str
) -> str:
    if not isinstance(plan, HardenedSnapshotPlan):
        raise SnapshotPlanError("Authenticated snapshot plan is required")
    if plan.network_mode != "none":
        raise HardenedRunnerError(
            "Online execution is disabled until proxy policy enforcement is "
            "independently attested"
        )
    if sys.platform != "linux":
        raise HardenedRunnerUnavailableError(
            "The frozen snapshot runner is supported on Linux only"
        )
    if not isinstance(docker, str) or not docker or "\x00" in docker:
        raise HardenedRunnerError("Invalid Docker executable")
    executable = shutil.which(docker)
    if executable is None:
        raise HardenedRunnerUnavailableError("Docker is not installed")
    return executable


def _installed_generator_fingerprint() -> str:
    """Recompute the locally installed generator, never trust a pack/caller string."""

    try:
        return compute_generator_fingerprint()
    except CohortFreezeError:
        raise HardenedRunnerError(
            "Installed generator fingerprint could not be verified"
        ) from None


def _read_private_file(path: str | Path) -> bytes:
    source = Path(path)
    if not source.is_absolute():
        raise EpisodePackError("Private artifact path must be absolute")
    try:
        before = source.lstat()
    except OSError:
        raise EpisodePackError("Private artifact unavailable") from None
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_mode & 0o077
        or before.st_uid != os.geteuid()
        or not 0 < before.st_size <= _MAX_PRIVATE_FILE_BYTES
    ):
        raise EpisodePackError("Unsafe private artifact")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(source, flags)
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            after = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(after.st_mode)
                or after.st_mode & 0o077
                or after.st_uid != os.geteuid()
                or after.st_dev != before.st_dev
                or after.st_ino != before.st_ino
                or after.st_size != before.st_size
            ):
                raise EpisodePackError("Unsafe private artifact")
            payload = stream.read(_MAX_PRIVATE_FILE_BYTES + 1)
    except OSError:
        raise EpisodePackError("Private artifact unavailable") from None
    if not 0 < len(payload) <= _MAX_PRIVATE_FILE_BYTES:
        raise EpisodePackError("Unsafe private artifact")
    return payload


def _create_broker_directory(path: Path) -> None:
    try:
        parent = path.parent.lstat()
    except OSError:
        raise HardenedRunnerError("Broker parent directory is unavailable") from None
    if not stat.S_ISDIR(parent.st_mode):
        raise HardenedRunnerError("Broker parent must not be a symlink")
    try:
        os.mkdir(path, 0o700)
    except FileExistsError:
        raise HardenedRunnerError("Broker directory already exists") from None
    except OSError:
        raise HardenedRunnerError("Broker directory could not be created") from None
    os.chmod(path, 0o700)


def _grant_broker_access(
    directory: Path, socket_path: Path, plan: HardenedSnapshotPlan
) -> None:
    effective_uid = os.geteuid()
    effective_gid = os.getegid()
    if effective_uid != 0 and (
        plan.uid != effective_uid or plan.gid != effective_gid
    ):
        raise HardenedRunnerError(
            "Non-root runner must use its own uid and gid for the container"
        )
    if effective_uid == 0:
        os.chown(directory, plan.uid, plan.gid)
        os.chown(socket_path, plan.uid, plan.gid)
    os.chmod(directory, 0o700)
    os.chmod(socket_path, 0o600)


def _verify_broker_boundary(
    directory: Path, socket_path: Path, plan: HardenedSnapshotPlan
) -> None:
    """Require an exact one-socket broker directory before and after execution."""

    try:
        directory_metadata = directory.lstat()
        socket_metadata = socket_path.lstat()
        with os.scandir(directory) as iterator:
            entries = tuple(iterator)
        entry_metadata = (
            entries[0].stat(follow_symlinks=False)
            if len(entries) == 1
            else None
        )
    except OSError:
        raise HardenedRunnerError("Public broker boundary is unavailable") from None
    if (
        not stat.S_ISDIR(directory_metadata.st_mode)
        or stat.S_IMODE(directory_metadata.st_mode) != 0o700
        or directory_metadata.st_uid != plan.uid
        or directory_metadata.st_gid != plan.gid
        or len(entries) != 1
        or entries[0].name != "episode.sock"
        or entries[0].is_symlink()
        or entry_metadata is None
        or entry_metadata.st_dev != socket_metadata.st_dev
        or entry_metadata.st_ino != socket_metadata.st_ino
        or not stat.S_ISSOCK(socket_metadata.st_mode)
        or stat.S_IMODE(socket_metadata.st_mode) != 0o600
        or socket_metadata.st_uid != plan.uid
        or socket_metadata.st_gid != plan.gid
        or socket_metadata.st_nlink != 1
    ):
        raise HardenedRunnerError("Public broker boundary was tampered with")


def _assert_no_private_material(
    command: tuple[str, ...],
    pack: PrivateEpisodePack,
    pack_path: str | Path,
    manifest_path: str | Path,
) -> None:
    rendered = "\x00".join(command)
    forbidden = (
        pack.episode_secret.hex(),
        str(Path(pack_path)),
        str(Path(manifest_path)),
        "episode_secret",
        "docker.sock",
    )
    if any(value and value in rendered for value in forbidden):
        raise HardenedRunnerError("Private material entered the container command")


def _write_private_new_file(path: str | Path, payload: bytes) -> Path:
    destination = _validate_new_private_path(path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor: int | None = None
    created = False
    try:
        descriptor = os.open(destination, flags, 0o600)
        created = True
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            descriptor = None
            os.fchmod(stream.fileno(), 0o600)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        if descriptor is not None:
            os.close(descriptor)
        if created:
            try:
                destination.unlink()
            except OSError:
                pass
        raise
    return destination


def _validate_new_private_path(path: str | Path) -> Path:
    destination = Path(path)
    if not destination.is_absolute():
        raise HardenedRunnerError("Receipt path must be absolute")
    try:
        parent = destination.parent.lstat()
    except OSError:
        raise HardenedRunnerError(
            "Receipt path must have an existing parent"
        ) from None
    if not stat.S_ISDIR(parent.st_mode):
        raise HardenedRunnerError("Receipt parent must not be a symlink")
    try:
        destination.lstat()
    except FileNotFoundError:
        return destination
    except OSError:
        raise HardenedRunnerError("Receipt destination is unavailable") from None
    raise FileExistsError(destination)


def _validate_authentication_key(value: bytes, *, label: str) -> None:
    if type(value) is not bytes or not 32 <= len(value) <= 4096:
        raise HardenedRunnerError(
            f"{label.capitalize()} key must contain 32 to 4096 bytes"
        )


def _sha256(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _canonical_json(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, RecursionError):
        raise HardenedRunnerError("Runner artifact is not canonical JSON") from None


def _plan_from_dict(value: Any) -> HardenedSnapshotPlan:
    if not isinstance(value, dict) or set(value) != {
        "format",
        "run_id",
        "image",
        "broker_directory",
        "agent_argv",
        "proxy_policy",
        "limits",
        "uid",
        "gid",
        "network_mode",
        "isolation_claims",
    } or value.get("format") != "epiagentbench.hardened-snapshot-plan.v1":
        raise HardenedRunnerError("Invalid snapshot plan")
    policy_value = value["proxy_policy"]
    limits_value = value["limits"]
    if not isinstance(policy_value, dict) or not isinstance(limits_value, dict):
        raise HardenedRunnerError("Invalid snapshot plan")
    if set(limits_value) != {
        "timeout_seconds",
        "memory",
        "cpus",
        "pids",
        "state_size",
    }:
        raise HardenedRunnerError("Invalid snapshot plan")
    try:
        required = policy_value["required_request_fields"]
        if not isinstance(required, dict) or set(required) != {
            "store",
            "background",
        }:
            raise HardenedRunnerError("Invalid snapshot plan")
        policy = InferenceProxyPolicy(
            policy_id=policy_value["policy_id"],
            network_name=policy_value["network_name"],
            proxy_url=policy_value["proxy_url"],
            allowed_provider_hosts=tuple(policy_value["allowed_provider_hosts"]),
            allowed_decoded_paths=tuple(policy_value["allowed_decoded_paths"]),
            allowed_models=tuple(policy_value["allowed_models"]),
            allowed_methods=tuple(policy_value["allowed_methods"]),
            require_store_false=required["store"] is False,
            require_background_false=required["background"] is False,
            tools_policy=policy_value["tools_policy"],
            tool_choice_policy=policy_value["tool_choice_policy"],
            max_calls=policy_value["max_calls"],
            max_total_tokens=policy_value["max_total_tokens"],
            max_output_tokens_per_call=policy_value[
                "max_output_tokens_per_call"
            ],
            max_request_bytes=policy_value["max_request_bytes"],
            max_response_bytes=policy_value["max_response_bytes"],
        )
        limits = SnapshotLimits(
            timeout_seconds=limits_value["timeout_seconds"],
            memory=limits_value["memory"],
            cpus=limits_value["cpus"],
            pids=limits_value["pids"],
            state_size=limits_value["state_size"],
        )
        plan = HardenedSnapshotPlan(
            run_id=value["run_id"],
            image=value["image"],
            broker_directory=value["broker_directory"],
            agent_argv=tuple(value["agent_argv"]),
            proxy_policy=policy,
            limits=limits,
            uid=value["uid"],
            gid=value["gid"],
            network_mode=value["network_mode"],
        )
    except (KeyError, TypeError, SnapshotPlanError, HardenedRunnerError):
        raise HardenedRunnerError("Invalid snapshot plan") from None
    if plan.as_dict() != value:
        raise HardenedRunnerError("Snapshot plan contains unsupported policy fields")
    return plan


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, child in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = child
    return value


def _reject_constant(_: str) -> NoReturn:
    raise ValueError("non-finite JSON number")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m epiagentbench.trusted.hardened_runner"
    )
    parser.add_argument("--plan", required=True)
    parser.add_argument("--expected-plan-commitment", required=True)
    parser.add_argument("--pack", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--pack-key-file", required=True)
    parser.add_argument("--receipt-key-file", required=True)
    parser.add_argument("--expected-pack-set-commitment", required=True)
    parser.add_argument("--expected-generator-fingerprint", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--docker", default="docker")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    plan = load_hardened_snapshot_plan(
        args.plan, expected_commitment=args.expected_plan_commitment
    )
    result = execute_frozen_episode(
        plan=plan,
        pack_path=Path(args.pack).resolve(),
        manifest_path=Path(args.manifest).resolve(),
        pack_authentication_key=_read_private_file(
            Path(args.pack_key_file).resolve()
        ),
        expected_pack_set_commitment=args.expected_pack_set_commitment,
        expected_generator_fingerprint=args.expected_generator_fingerprint,
        receipt_authentication_key=_read_private_file(
            Path(args.receipt_key_file).resolve()
        ),
        receipt_path=Path(args.receipt).resolve(),
        docker=args.docker,
    )
    print(
        json.dumps(
            {
                "scorecard": result.scorecard,
                "audit_events": list(result.audit_events),
                "receipt_path": result.receipt_path,
                "receipt_authenticated": True,
                "linux_execution_verified": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
