"""Optional Linux/Docker runner for a single untrusted agent episode."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, NoReturn
import uuid

from .service import SecureEpisodeSession, launch_socket_episode


_MAX_STREAM_BYTES = 1_048_576
_IMAGE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/@:-]{0,254}$")
_LIMIT_VALUE = re.compile(r"^[1-9][0-9]*(?:[kmgt]b?)?$", re.IGNORECASE)


class SandboxUnavailableError(RuntimeError):
    """Raised when the hardened container runner cannot be used."""


@dataclass(frozen=True, slots=True)
class ContainerLimits:
    timeout_seconds: int = 300
    memory: str = "1g"
    cpus: float = 1.0
    pids: int = 128
    scratch_size: str = "256m"


@dataclass(frozen=True, slots=True)
class ContainerEvaluationResult:
    submission: dict[str, Any]
    scorecard: dict[str, Any]
    audit_events: tuple[str, ...]
    agent_stderr_bytes: int


def evaluate_container_agent(
    *,
    image: str,
    agent_script: str,
    seed: int,
    family: str | None = None,
    backend: str = "reference",
    limits: ContainerLimits = ContainerLimits(),
) -> ContainerEvaluationResult:
    """Run one JSON-producing agent image and score it after termination.

    This runner deliberately supports Linux only.  It passes the public Unix
    socket through a read-only bind mount and never mounts the evaluator source,
    oracle, Docker socket, host temporary directory, or admin capability.
    """

    docker = _validate_runner_inputs(image, agent_script, limits)
    script = Path(agent_script).resolve(strict=True)
    broker_directory = tempfile.mkdtemp(prefix="eab-", dir="/tmp")
    session: SecureEpisodeSession | None = None
    container_name: str | None = None
    container_launched = False
    container_run_complete = False
    environment = {"PATH": os.environ.get("PATH", os.defpath)}
    try:
        os.chmod(broker_directory, 0o700)
        socket_path = str(Path(broker_directory) / "episode.sock")
        session = launch_socket_episode(
            public_socket_path=socket_path,
            seed=seed,
            family=family,
            backend=backend,
        )
        container_uid = os.getuid() if os.getuid() != 0 else 65532
        container_gid = os.getgid() if os.getuid() != 0 else 65532
        if os.getuid() == 0:
            os.chown(broker_directory, container_uid, container_gid)
            os.chown(socket_path, container_uid, container_gid)
        container_name = f"epiagent-{uuid.uuid4().hex}"
        audit_events: list[str] = []
        command = [
            docker,
            "run",
            "--rm",
            "--pull",
            "never",
            "--name",
            container_name,
            "--network",
            "none",
            "--ipc",
            "none",
            "--read-only",
            "--user",
            f"{container_uid}:{container_gid}",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges=true",
            "--pids-limit",
            str(limits.pids),
            "--memory",
            limits.memory,
            "--cpus",
            str(limits.cpus),
            "--ulimit",
            "nofile=128:128",
            "--ulimit",
            "nproc=64:64",
            "--tmpfs",
            f"/scratch:rw,noexec,nosuid,nodev,size={limits.scratch_size}",
            "--env",
            "HOME=/scratch",
            "--env",
            "TMPDIR=/scratch",
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
            "--env",
            "EPIAGENT_SOCKET=/broker/episode.sock",
            "--mount",
            f"type=bind,src={broker_directory},dst=/broker,readonly",
            "--mount",
            f"type=bind,src={script},dst=/work/agent.py,readonly",
            image,
        ]
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
            close_fds=True,
        )
        container_launched = True
        stdout, stderr, outcome = _collect_bounded(
            process, timeout_seconds=limits.timeout_seconds
        )
        # _collect_bounded waits for the docker client to exit. At this point a
        # normal ``--rm`` run has cleaned itself up; exceptional collector paths
        # are handled in the outer finally below.
        container_run_complete = True
        if outcome != "ok":
            audit_events.append(f"sandbox_resource_limit:{outcome}")
            _force_remove_container(docker, container_name, environment)
        elif process.returncode != 0:
            audit_events.append("sandbox_failure:nonzero_exit")

        submission, scorecard = _score_agent_output(
            session=session,
            stdout=stdout,
            stderr=stderr,
            audit_events=audit_events,
        )
        return ContainerEvaluationResult(
            submission=submission,
            scorecard=scorecard,
            audit_events=tuple(audit_events),
            agent_stderr_bytes=len(stderr),
        )
    finally:
        try:
            if (
                container_launched
                and not container_run_complete
                and container_name is not None
            ):
                _force_remove_container(docker, container_name, environment)
        finally:
            try:
                if session is not None:
                    session.close()
            finally:
                shutil.rmtree(broker_directory, ignore_errors=True)


def _validate_runner_inputs(
    image: str, agent_script: str, limits: ContainerLimits
) -> str:
    if sys.platform != "linux":
        raise SandboxUnavailableError(
            "The mounted Unix-socket Docker runner is supported on Linux only."
        )
    docker = shutil.which("docker")
    if docker is None:
        raise SandboxUnavailableError("Docker is not installed.")
    if not isinstance(image, str) or not _IMAGE_NAME.fullmatch(image):
        raise ValueError("Invalid agent image")
    script = Path(agent_script)
    if not script.is_file() or "," in str(script.resolve()):
        raise ValueError("Agent script does not exist")
    if (
        type(limits.timeout_seconds) is not int
        or not 1 <= limits.timeout_seconds <= 3600
        or type(limits.pids) is not int
        or not 16 <= limits.pids <= 4096
        or type(limits.cpus) not in (int, float)
        or not 0.1 <= float(limits.cpus) <= 64
        or not isinstance(limits.memory, str)
        or not isinstance(limits.scratch_size, str)
        or not _LIMIT_VALUE.fullmatch(limits.memory)
        or not _LIMIT_VALUE.fullmatch(limits.scratch_size)
    ):
        raise ValueError("Invalid sandbox limits")
    return docker


def _collect_bounded(
    process: subprocess.Popen[bytes], *, timeout_seconds: int
) -> tuple[bytes, bytes, str]:
    if process.stdout is None or process.stderr is None:
        raise RuntimeError("Container output pipes were not created")
    selector = selectors.DefaultSelector()
    streams = {process.stdout: bytearray(), process.stderr: bytearray()}
    for stream in streams:
        os.set_blocking(stream.fileno(), False)
        selector.register(stream, selectors.EVENT_READ)

    deadline = time.monotonic() + timeout_seconds
    outcome = "ok"
    while selector.get_map():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            outcome = "timeout"
            process.kill()
            break
        for key, _ in selector.select(timeout=min(remaining, 0.25)):
            stream = key.fileobj
            try:
                chunk = os.read(stream.fileno(), 65_536)
            except BlockingIOError:
                continue
            if not chunk:
                selector.unregister(stream)
                continue
            buffer = streams[stream]
            if len(buffer) + len(chunk) > _MAX_STREAM_BYTES:
                keep = max(0, _MAX_STREAM_BYTES - len(buffer))
                buffer.extend(chunk[:keep])
                outcome = "output_limit"
                process.kill()
                break
            buffer.extend(chunk)
        if outcome != "ok":
            break

    selector.close()
    try:
        process.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2.0)
    return bytes(streams[process.stdout]), bytes(streams[process.stderr]), outcome


def _force_remove_container(
    docker: str, container_name: str, environment: dict[str, str]
) -> None:
    try:
        subprocess.run(
            [docker, "rm", "--force", container_name],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=environment,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def _parse_submission(stdout: bytes) -> dict[str, Any] | None:
    if not stdout or len(stdout) > _MAX_STREAM_BYTES:
        return None
    try:
        value = json.loads(
            stdout.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None
    return value if isinstance(value, dict) else None


def _score_agent_output(
    *,
    session: SecureEpisodeSession,
    stdout: bytes,
    stderr: bytes,
    audit_events: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate sandbox output against its exact evaluator transport frame."""

    artifacts = (stdout, stderr)
    submission = _parse_submission(stdout)
    if submission is None or not session.score_request_fits(
        submission,
        audit_events=audit_events,
        agent_artifacts=artifacts,
    ):
        audit_events.append("sandbox_failure:invalid_submission")
        submission = {}
    scorecard = session.score(
        submission,
        audit_events=audit_events,
        agent_artifacts=artifacts,
    )
    return submission, scorecard


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, child in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = child
    return value


def _reject_constant(_: str) -> NoReturn:
    raise ValueError("non-finite JSON number")
