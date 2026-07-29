from __future__ import annotations

from contextlib import ExitStack
from pathlib import Path
import socket
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from epiagentbench.trusted.service import (
    TRUSTED_EVALUATOR_STARTUP_STAGES,
    TrustedEvaluatorStartupError,
    _await_ready,
    _send_startup_failure,
    _serve_socket_episode,
    launch_socket_episode,
)
from epiagentbench.trusted.wire import JsonSocket, PROTOCOL_VERSION


class _FakeProcess:
    def __init__(self, *, alive: bool, exitcode: int | None):
        self._alive = alive
        self.exitcode = exitcode
        self.terminated = False

    def is_alive(self) -> bool:
        return self._alive

    def join(self, timeout: float | None = None) -> None:
        del timeout

    def terminate(self) -> None:
        self.terminated = True
        self._alive = False
        if self.exitcode is None:
            self.exitcode = -15


class TrustedStartupDiagnosticTests(unittest.TestCase):
    def test_startup_stage_taxonomy_is_exact(self):
        self.assertEqual(
            TRUSTED_EVALUATOR_STARTUP_STAGES,
            {
                "process_spawn",
                "process_bootstrap_nonzero",
                "backend_resolution",
                "runtime_creation",
                "socket_bind",
                "public_service_start",
                "ready_timeout",
                "startup_channel",
                "startup_protocol",
                "unclassified",
            },
        )

    def test_exact_child_failure_frame_preserves_only_allowlisted_stage(self):
        parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        child_channel = JsonSocket(child)
        child_channel.send(
            {
                "version": PROTOCOL_VERSION,
                "event": "startup_failed",
                "stage": "runtime_creation",
            }
        )
        child_channel.close()
        process = _FakeProcess(alive=False, exitcode=0)
        with self.assertRaises(TrustedEvaluatorStartupError) as caught:
            _await_ready(process, parent, timeout_seconds=0.1)
        self.assertEqual(caught.exception.startup_stage, "runtime_creation")
        self.assertIsNone(caught.exception.__cause__)

    def test_malformed_or_untrusted_child_failure_frame_is_protocol_failure(
        self,
    ):
        frames = (
            {
                "version": PROTOCOL_VERSION,
                "event": "startup_failed",
                "stage": "unclassified",
            },
            {
                "version": PROTOCOL_VERSION,
                "event": "startup_failed",
                "stage": "runtime_creation",
                "detail": "must-not-be-accepted",
            },
            {
                "version": PROTOCOL_VERSION,
                "event": "startup_failed",
                "stage": "not-allowlisted",
            },
            {
                "version": PROTOCOL_VERSION,
                "event": "startup_failed",
                "stage": [],
            },
            {
                "version": PROTOCOL_VERSION,
                "event": "startup_failed",
                "stage": {},
            },
            {
                "version": PROTOCOL_VERSION,
                "event": "startup_failed",
                "stage": None,
            },
            {
                "version": PROTOCOL_VERSION,
                "event": "startup_failed",
                "stage": 1,
            },
        )
        for frame in frames:
            with self.subTest(frame=frame):
                parent, child = socket.socketpair(
                    socket.AF_UNIX, socket.SOCK_STREAM
                )
                channel = JsonSocket(child)
                channel.send(frame)
                channel.close()
                with self.assertRaises(
                    TrustedEvaluatorStartupError
                ) as caught:
                    _await_ready(
                        _FakeProcess(alive=False, exitcode=0),
                        parent,
                        timeout_seconds=0.1,
                    )
                self.assertEqual(
                    caught.exception.startup_stage,
                    "startup_protocol",
                )

    def test_channel_close_distinguishes_bootstrap_exit_and_timeout(self):
        parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        child.close()
        with self.assertRaises(TrustedEvaluatorStartupError) as caught:
            _await_ready(
                _FakeProcess(alive=False, exitcode=1),
                parent,
                timeout_seconds=0.1,
            )
        self.assertEqual(
            caught.exception.startup_stage,
            "process_bootstrap_nonzero",
        )

        parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(child.close)
        process = _FakeProcess(alive=True, exitcode=None)
        with self.assertRaises(TrustedEvaluatorStartupError) as caught:
            _await_ready(process, parent, timeout_seconds=0.01)
        self.assertEqual(caught.exception.startup_stage, "ready_timeout")
        self.assertTrue(process.terminated)

    def test_child_failure_sender_cannot_transmit_detail(self):
        parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        parent_channel = JsonSocket(parent)
        child_channel = JsonSocket(child)
        _send_startup_failure(child_channel, "runtime_creation")
        self.assertEqual(
            parent_channel.receive(),
            {
                "version": PROTOCOL_VERSION,
                "event": "startup_failed",
                "stage": "runtime_creation",
            },
        )
        child_channel.close()
        parent_channel.close()

    def test_process_start_failure_is_typed_and_content_free(self):
        secret = "spawn-secret-must-not-leak"

        class Process:
            def start(self) -> None:
                raise RuntimeError(secret)

        class Context:
            def Process(self, **_kwargs):
                return Process()

        with TemporaryDirectory(prefix="eab-", dir="/tmp") as directory:
            with (
                patch(
                    "epiagentbench.trusted.service.multiprocessing.get_context",
                    return_value=Context(),
                ),
                self.assertRaises(TrustedEvaluatorStartupError) as caught,
            ):
                launch_socket_episode(
                    public_socket_path=str(
                        Path(directory) / "episode.sock"
                    ),
                    seed=7,
                )
        self.assertEqual(caught.exception.startup_stage, "process_spawn")
        self.assertNotIn(secret, str(caught.exception))
        self.assertIsNone(caught.exception.__cause__)

    def test_socket_child_reports_each_operational_startup_stage(self):
        class Runtime:
            @staticmethod
            def close():
                return None

        class Backend:
            @staticmethod
            def create_runtime(**_kwargs):
                return Runtime()

        class Controller:
            @staticmethod
            def close():
                return None

        class BindFailureListener:
            @staticmethod
            def bind(_path):
                raise RuntimeError("socket detail must not leak")

            @staticmethod
            def close():
                return None

        def receive_frame(*contexts):
            parent, child = socket.socketpair(
                socket.AF_UNIX, socket.SOCK_STREAM
            )
            channel = JsonSocket(parent)
            with (
                TemporaryDirectory(
                    prefix="eab-", dir="/tmp"
                ) as directory,
                ExitStack() as stack,
            ):
                for context in contexts:
                    stack.enter_context(context)
                _serve_socket_episode(
                    child,
                    str(Path(directory) / "episode.sock"),
                    7,
                    None,
                    "reference",
                    b"x" * 32,
                )
            frame = channel.receive()
            channel.close()
            return frame

        cases = (
            (
                "backend_resolution",
                (
                    patch(
                        "epiagentbench.trusted.service.build_backend",
                        side_effect=RuntimeError(
                            "backend detail must not leak"
                        ),
                    ),
                ),
            ),
            (
                "runtime_creation",
                (
                    patch(
                        "epiagentbench.trusted.service.build_backend",
                        return_value=type(
                            "FailingBackend",
                            (),
                            {
                                "create_runtime": staticmethod(
                                    lambda **_kwargs: (_ for _ in ()).throw(
                                        RuntimeError(
                                            "runtime detail must not leak"
                                        )
                                    )
                                )
                            },
                        )(),
                    ),
                ),
            ),
            (
                "socket_bind",
                (
                    patch(
                        "epiagentbench.trusted.service.build_backend",
                        return_value=Backend(),
                    ),
                    patch(
                        "epiagentbench.trusted.service."
                        "TrustedEpisodeController",
                        return_value=Controller(),
                    ),
                    patch(
                        "epiagentbench.trusted.service.socket.socket",
                        return_value=BindFailureListener(),
                    ),
                ),
            ),
            (
                "public_service_start",
                (
                    patch(
                        "epiagentbench.trusted.service.build_backend",
                        return_value=Backend(),
                    ),
                    patch(
                        "epiagentbench.trusted.service."
                        "TrustedEpisodeController",
                        return_value=Controller(),
                    ),
                    patch(
                        "epiagentbench.trusted.service.Thread.start",
                        side_effect=RuntimeError(
                            "thread detail must not leak"
                        ),
                    ),
                ),
            ),
        )
        for stage, contexts in cases:
            with self.subTest(stage=stage):
                self.assertEqual(
                    receive_frame(*contexts),
                    {
                        "version": PROTOCOL_VERSION,
                        "event": "startup_failed",
                        "stage": stage,
                    },
                )


if __name__ == "__main__":
    unittest.main()
