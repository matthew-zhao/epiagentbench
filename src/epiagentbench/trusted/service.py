"""Two-capability process boundary for an EpiAgentBench episode."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import multiprocessing
import os
from pathlib import Path
import secrets
import socket
from threading import Thread
from typing import Any

from epiagentbench_client import InvestigationClient

from .backend import build_backend
from .controller import TrustedEpisodeController
from .wire import (
    JsonSocket,
    MAX_MESSAGE_BYTES,
    PROTOCOL_VERSION,
    WireError,
    canonical_json,
)


_PUBLIC_ENVELOPE_KEYS = {"version", "id", "method", "params"}
_GENERIC_ERROR = {"code": "rejected", "message": "Request rejected."}
_MAX_AGENT_ARTIFACT_BYTES = 2_097_152


class SecureEpisodeSession:
    """Evaluator-only owner of the private scoring capability and process.

    Never pass this object to the agent.  Pass only the separately returned
    :class:`epiagentbench_client.InvestigationClient`.
    """

    def __init__(
        self,
        process: multiprocessing.process.BaseProcess,
        admin_socket: socket.socket,
    ):
        self._process = process
        self._admin = JsonSocket(admin_socket)
        self._closed = False
        self._scored = False
        self._next_request_id = 1

    @classmethod
    def _from_channel(
        cls,
        process: multiprocessing.process.BaseProcess,
        channel: JsonSocket,
    ) -> SecureEpisodeSession:
        instance = cls.__new__(cls)
        instance._process = process
        instance._admin = channel
        instance._closed = False
        instance._scored = False
        instance._next_request_id = 1
        return instance

    def score(
        self,
        submission: Mapping[str, Any],
        audit_events: Sequence[str] = (),
        agent_artifacts: Sequence[str | bytes] = (),
    ) -> dict[str, Any]:
        """Terminate and score without returning oracle or simulator state."""

        if self._closed or self._scored:
            raise RuntimeError("Secure episode is no longer scoreable")
        if not self._valid_score_inputs(
            submission, audit_events, agent_artifacts
        ):
            raise ValueError("Invalid score request")
        for index, artifact in enumerate(agent_artifacts):
            artifact_id = f"artifact_{index}"
            chunks = self._artifact_chunks(artifact)
            for chunk_index, chunk in enumerate(chunks):
                self._admin_call(
                    "audit_artifact",
                    {
                        "artifact_id": artifact_id,
                        "chunk": chunk,
                        "final": chunk_index == len(chunks) - 1,
                    },
                )
        result = self._admin_call(
            "score",
            {
                "submission": dict(submission),
                "audit_events": list(audit_events),
            },
        )
        if not isinstance(result, dict):
            raise RuntimeError("Trusted evaluator returned an invalid score")
        self._scored = True
        return result

    def score_with_replay(
        self,
        submission: Mapping[str, Any],
        audit_events: Sequence[str] = (),
        agent_artifacts: Sequence[str | bytes] = (),
    ) -> dict[str, Any]:
        """Terminate and return score plus aggregate replay via the admin channel."""

        if self._closed or self._scored:
            raise RuntimeError("Secure episode is no longer scoreable")
        if not self._valid_score_inputs(
            submission, audit_events, agent_artifacts
        ):
            raise ValueError("Invalid score request")
        for index, artifact in enumerate(agent_artifacts):
            artifact_id = f"artifact_{index}"
            chunks = self._artifact_chunks(artifact)
            for chunk_index, chunk in enumerate(chunks):
                self._admin_call(
                    "audit_artifact",
                    {
                        "artifact_id": artifact_id,
                        "chunk": chunk,
                        "final": chunk_index == len(chunks) - 1,
                    },
                )
        result = self._admin_call(
            "score_with_replay",
            {
                "submission": dict(submission),
                "audit_events": list(audit_events),
            },
        )
        if (
            not isinstance(result, dict)
            or set(result) != {"scorecard", "replay_trace"}
            or not isinstance(result["scorecard"], dict)
            or not isinstance(result["replay_trace"], dict)
        ):
            raise RuntimeError("Trusted evaluator returned an invalid replay result")
        self._scored = True
        return result

    def score_request_fits(
        self,
        submission: Mapping[str, Any],
        audit_events: Sequence[str] = (),
        agent_artifacts: Sequence[str | bytes] = (),
    ) -> bool:
        """Preflight the exact future admin score frame without sending it.

        Artifact audit calls consume request identifiers before the score call,
        so their exact chunk count is included in the prospective identifier.
        This is used at the sandbox boundary, where compact UTF-8 agent output
        can expand substantially under the admin wire's ASCII JSON encoding.
        """

        if self._closed or self._scored or not self._valid_score_inputs(
            submission, audit_events, agent_artifacts
        ):
            return False
        try:
            artifact_calls = sum(
                len(self._artifact_chunks(artifact))
                for artifact in agent_artifacts
            )
            request = self._admin_request(
                self._next_request_id + artifact_calls,
                "score",
                {
                    "submission": dict(submission),
                    "audit_events": list(audit_events),
                },
            )
            payload = canonical_json(request)
        except (TypeError, ValueError, OverflowError, RecursionError, WireError):
            return False
        return 0 < len(payload) <= MAX_MESSAGE_BYTES

    def score_with_replay_request_fits(
        self,
        submission: Mapping[str, Any],
        audit_events: Sequence[str] = (),
        agent_artifacts: Sequence[str | bytes] = (),
    ) -> bool:
        """Preflight the exact terminal replay score request frame."""

        if self._closed or self._scored or not self._valid_score_inputs(
            submission, audit_events, agent_artifacts
        ):
            return False
        try:
            artifact_calls = sum(
                len(self._artifact_chunks(artifact))
                for artifact in agent_artifacts
            )
            request = self._admin_request(
                self._next_request_id + artifact_calls,
                "score_with_replay",
                {
                    "submission": dict(submission),
                    "audit_events": list(audit_events),
                },
            )
            payload = canonical_json(request)
        except (TypeError, ValueError, OverflowError, RecursionError, WireError):
            return False
        return 0 < len(payload) <= MAX_MESSAGE_BYTES

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._admin_call("shutdown", {})
        except (RuntimeError, WireError):
            pass
        self._admin.close()
        self._process.join(timeout=2.0)
        if self._process.is_alive():
            self._process.terminate()
            self._process.join(timeout=2.0)

    def __enter__(self) -> SecureEpisodeSession:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _admin_call(self, method: str, params: dict[str, Any]) -> Any:
        request_id = self._next_request_id
        self._next_request_id += 1
        self._admin.send(self._admin_request(request_id, method, params))
        response = self._admin.receive()
        if (
            not isinstance(response, dict)
            or response.get("version") != PROTOCOL_VERSION
            or response.get("id") != request_id
            or response.get("ok") is not True
            or "result" not in response
        ):
            raise RuntimeError("Trusted evaluator unavailable")
        return response["result"]

    @staticmethod
    def _admin_request(
        request_id: int, method: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "version": PROTOCOL_VERSION,
            "id": request_id,
            "method": method,
            "params": params,
        }

    @staticmethod
    def _artifact_chunks(artifact: str | bytes) -> tuple[str, ...]:
        text = (
            artifact.decode("utf-8", errors="replace")
            if isinstance(artifact, bytes)
            else artifact
        )
        if not text:
            return ("",)
        return tuple(
            text[offset : offset + 32_768]
            for offset in range(0, len(text), 32_768)
        )

    @staticmethod
    def _valid_score_inputs(
        submission: Mapping[str, Any],
        audit_events: Sequence[str],
        agent_artifacts: Sequence[str | bytes],
    ) -> bool:
        return not (
            not isinstance(submission, Mapping)
            or isinstance(audit_events, (str, bytes))
            or any(not isinstance(event, str) for event in audit_events)
            or isinstance(agent_artifacts, (str, bytes))
            or len(agent_artifacts) > 8
            or any(
                not isinstance(artifact, (str, bytes))
                for artifact in agent_artifacts
            )
            or sum(len(artifact) for artifact in agent_artifacts)
            > _MAX_AGENT_ARTIFACT_BYTES
        )


def _validated_episode_secret(value: bytes | None) -> bytes:
    """Return a high-entropy secret, or validate a private replay secret."""

    if value is None:
        return secrets.token_bytes(32)
    if type(value) is not bytes or len(value) < 32:
        raise ValueError("Invalid private episode configuration")
    return value


def launch_secure_episode(
    *,
    seed: int,
    family: str | None = None,
    backend: str = "reference",
    episode_secret: bytes | None = None,
) -> tuple[SecureEpisodeSession, InvestigationClient]:
    """Launch a fresh hidden evaluator and return separate trust capabilities."""

    if type(seed) is not int or family is not None and not isinstance(family, str):
        raise ValueError("Invalid private episode configuration")
    if not isinstance(backend, str):
        raise ValueError("Invalid private episode configuration")
    episode_secret = _validated_episode_secret(episode_secret)

    public_parent, public_child = socket.socketpair(
        socket.AF_UNIX, socket.SOCK_STREAM
    )
    admin_parent, admin_child = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    context = multiprocessing.get_context("spawn")
    process = context.Process(
        target=_serve_episode,
        args=(
            public_child,
            admin_child,
            seed,
            family,
            backend,
            episode_secret,
        ),
        name="epiagentbench-trusted-evaluator",
        daemon=True,
    )
    try:
        process.start()
    except Exception:
        public_parent.close()
        public_child.close()
        admin_parent.close()
        admin_child.close()
        raise
    public_child.close()
    admin_child.close()
    try:
        admin_channel = _await_ready(
            process,
            admin_parent,
            timeout_seconds=(
                60.0 if backend in {"starsim", "starsim-ltc-v3"} else 10.0
            ),
        )
    except RuntimeError:
        public_parent.close()
        raise
    return (
        SecureEpisodeSession._from_channel(process, admin_channel),
        InvestigationClient(public_parent),
    )


def launch_socket_episode(
    *,
    public_socket_path: str,
    seed: int,
    family: str | None = None,
    backend: str = "reference",
    episode_secret: bytes | None = None,
) -> SecureEpisodeSession:
    """Launch a broker on a Unix socket suitable for a read-only bind mount.

    The evaluator caller retains the returned admin capability.  An agent
    sandbox receives only the socket pathname and the public client package.
    The socket accepts a single public connection for one episode.
    """

    if type(seed) is not int or family is not None and not isinstance(family, str):
        raise ValueError("Invalid private episode configuration")
    if not isinstance(backend, str) or not isinstance(public_socket_path, str):
        raise ValueError("Invalid private episode configuration")
    episode_secret = _validated_episode_secret(episode_secret)
    path = Path(public_socket_path)
    if (
        not path.is_absolute()
        or not path.parent.is_dir()
        or path.exists()
        or len(str(path).encode("utf-8")) > 100
    ):
        raise ValueError("Invalid public broker path")

    admin_parent, admin_child = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    context = multiprocessing.get_context("spawn")
    process = context.Process(
        target=_serve_socket_episode,
        args=(
            admin_child,
            str(path),
            seed,
            family,
            backend,
            episode_secret,
        ),
        name="epiagentbench-trusted-evaluator",
        daemon=True,
    )
    try:
        process.start()
    except Exception:
        admin_parent.close()
        admin_child.close()
        raise
    admin_child.close()

    admin_channel = _await_ready(
        process,
        admin_parent,
        timeout_seconds=(
            60.0 if backend in {"starsim", "starsim-ltc-v3"} else 10.0
        ),
    )
    return SecureEpisodeSession._from_channel(process, admin_channel)


def _await_ready(
    process: multiprocessing.process.BaseProcess,
    admin_socket: socket.socket,
    *,
    timeout_seconds: float = 10.0,
) -> JsonSocket:
    channel = JsonSocket(admin_socket)
    admin_socket.settimeout(timeout_seconds)
    try:
        ready = channel.receive()
    except WireError:
        try:
            admin_socket.settimeout(None)
        except OSError:
            pass
        channel.close()
        process.join(timeout=0.5)
        if process.is_alive():
            process.terminate()
            process.join(timeout=1.0)
        raise RuntimeError("Trusted evaluator failed to start") from None
    admin_socket.settimeout(None)
    if ready != {"version": PROTOCOL_VERSION, "event": "ready"}:
        channel.close()
        process.terminate()
        process.join(timeout=1.0)
        raise RuntimeError("Trusted evaluator failed to start")
    return channel


def _serve_episode(
    public_socket: socket.socket,
    admin_socket: socket.socket,
    seed: int,
    family: str | None,
    backend_name: str,
    episode_secret: bytes,
) -> None:
    """Child process entry point; configuration never enters public objects."""

    public_channel = JsonSocket(public_socket)
    admin_channel = JsonSocket(admin_socket)
    runtime = None
    controller = None
    try:
        backend = build_backend(backend_name)
        runtime = backend.create_runtime(
            seed=seed,
            family=family,
            presentation_key=episode_secret,
        )
        controller = TrustedEpisodeController(runtime)
    except Exception:
        if runtime is not None:
            runtime.close()
        public_channel.close()
        admin_channel.close()
        return

    try:
        admin_channel.send({"version": PROTOCOL_VERSION, "event": "ready"})
    except WireError:
        public_channel.close()
        admin_channel.close()
        return

    public_thread = Thread(
        target=_serve_public,
        args=(public_channel, controller),
        name="public-investigation-broker",
        daemon=True,
    )
    public_thread.start()
    try:
        _serve_admin(admin_channel, controller)
    finally:
        controller.close()
        public_channel.close()
        admin_channel.close()
        public_thread.join(timeout=0.5)


def _serve_socket_episode(
    admin_socket: socket.socket,
    public_socket_path: str,
    seed: int,
    family: str | None,
    backend_name: str,
    episode_secret: bytes,
) -> None:
    """Child entry point for a single-connection filesystem broker socket."""

    admin_channel = JsonSocket(admin_socket)
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    public_channel: JsonSocket | None = None
    runtime = None
    controller = None
    try:
        backend = build_backend(backend_name)
        runtime = backend.create_runtime(
            seed=seed,
            family=family,
            presentation_key=episode_secret,
        )
        controller = TrustedEpisodeController(runtime)
        listener.bind(public_socket_path)
        os.chmod(public_socket_path, 0o600)
        listener.listen(1)
        admin_channel.send({"version": PROTOCOL_VERSION, "event": "ready"})

        def accept_and_serve() -> None:
            nonlocal public_channel
            try:
                connected, _ = listener.accept()
            except OSError:
                return
            public_channel = JsonSocket(connected)
            _serve_public(public_channel, controller)

        public_thread = Thread(
            target=accept_and_serve,
            name="public-investigation-broker",
            daemon=True,
        )
        public_thread.start()
        _serve_admin(admin_channel, controller)
    except Exception:
        return
    finally:
        if controller is not None:
            controller.close()
        elif runtime is not None:
            runtime.close()
        listener.close()
        if public_channel is not None:
            public_channel.close()
        admin_channel.close()
        try:
            os.unlink(public_socket_path)
        except FileNotFoundError:
            pass


def _serve_public(
    channel: JsonSocket, controller: TrustedEpisodeController
) -> None:
    cache: dict[int, tuple[bytes, dict[str, Any]]] = {}
    for _ in range(4096):
        try:
            request = channel.receive()
        except WireError:
            return
        request_id = _public_request_id(request)
        response: dict[str, Any]
        try:
            _validate_request_envelope(request)
            assert isinstance(request, dict)
            canonical = canonical_json(request)
            previous = cache.get(request_id)
            if previous is not None:
                if previous[0] != canonical:
                    raise ValueError("nonce reuse")
                channel.send(previous[1])
                continue
            result = controller.public_call(request["method"], request["params"])
            response = {
                "version": PROTOCOL_VERSION,
                "id": request_id,
                "ok": True,
                "result": result,
            }
            cache[request_id] = (canonical, response)
        except Exception:
            response = {
                "version": PROTOCOL_VERSION,
                "id": request_id,
                "ok": False,
                "error": dict(_GENERIC_ERROR),
            }
        try:
            channel.send(response)
        except WireError:
            return
    channel.close()


def _serve_admin(
    channel: JsonSocket, controller: TrustedEpisodeController
) -> None:
    while True:
        try:
            request = channel.receive()
            _validate_request_envelope(request)
            assert isinstance(request, dict)
            method = request["method"]
            params = request["params"]
            if method in {"score", "score_with_replay"}:
                if set(params) != {"submission", "audit_events"}:
                    raise ValueError("invalid")
                submission = params["submission"]
                audit_events = params["audit_events"]
                if not isinstance(submission, dict) or not isinstance(
                    audit_events, list
                ) or any(not isinstance(value, str) for value in audit_events):
                    raise ValueError("invalid")
                scorer = (
                    controller.score
                    if method == "score"
                    else controller.score_with_replay
                )
                result: Any = scorer(submission, tuple(audit_events))
            elif method == "audit_artifact":
                if set(params) != {"artifact_id", "chunk", "final"}:
                    raise ValueError("invalid")
                result = controller.audit_artifact(
                    params["artifact_id"],
                    params["chunk"],
                    final=params["final"],
                )
            elif method == "shutdown":
                if params:
                    raise ValueError("invalid")
                channel.send(
                    {
                        "version": PROTOCOL_VERSION,
                        "id": request["id"],
                        "ok": True,
                        "result": {"status": "closed"},
                    }
                )
                return
            else:
                raise ValueError("invalid")
            channel.send(
                {
                    "version": PROTOCOL_VERSION,
                    "id": request["id"],
                    "ok": True,
                    "result": result,
                }
            )
        except Exception:
            # The private channel is evaluator-owned.  Close on any malformed
            # request instead of reflecting exception details.
            return


def _validate_request_envelope(request: Any) -> None:
    if (
        not isinstance(request, dict)
        or set(request) != _PUBLIC_ENVELOPE_KEYS
        or request.get("version") != PROTOCOL_VERSION
        or type(request.get("id")) is not int
        or request["id"] <= 0
        or request["id"] > 2**53 - 1
        or not isinstance(request.get("method"), str)
        or not isinstance(request.get("params"), dict)
    ):
        raise ValueError("invalid request")


def _public_request_id(request: Any) -> int:
    if isinstance(request, dict) and type(request.get("id")) is int:
        value = request["id"]
        if 0 < value <= 2**53 - 1:
            return value
    return 0
