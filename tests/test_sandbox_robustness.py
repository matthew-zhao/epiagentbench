from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import epiagentbench.trusted.sandbox as sandbox_module
from epiagentbench.trusted.sandbox import (
    _parse_submission,
    _score_agent_output,
    evaluate_container_agent,
)
from epiagentbench.trusted.service import (
    SecureEpisodeSession,
    launch_secure_episode,
)
from epiagentbench.trusted.wire import MAX_MESSAGE_BYTES


ROOT = Path(__file__).resolve().parents[1]


class SandboxTransportRobustnessTests(unittest.TestCase):
    def test_unicode_expansion_becomes_scored_invalid_submission(self):
        stdout = json.dumps(
            {"payload": "\U0001f600" * 90_000},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        self.assertLess(len(stdout), MAX_MESSAGE_BYTES)
        parsed = _parse_submission(stdout)
        self.assertIsInstance(parsed, dict)
        assert parsed is not None

        session, client = launch_secure_episode(seed=41)
        audit_events: list[str] = []
        try:
            self.assertFalse(
                session.score_request_fits(
                    parsed,
                    audit_events=audit_events,
                    agent_artifacts=(stdout, b""),
                )
            )
            submission, scorecard = _score_agent_output(
                session=session,
                stdout=stdout,
                stderr=b"",
                audit_events=audit_events,
            )
            self.assertEqual(submission, {})
            self.assertEqual(
                audit_events, ["sandbox_failure:invalid_submission"]
            )
            self.assertFalse(scorecard["valid"])
            self.assertEqual(scorecard["total"], 0)
            self.assertIn(
                "sandbox_failure:invalid_submission",
                scorecard["violations"],
            )
        finally:
            client.close()
            session.close()

    def test_broker_directory_is_removed_when_session_launch_fails(self):
        with TemporaryDirectory(prefix="eab-test-", dir="/tmp") as parent:
            broker = Path(parent) / "broker"
            broker.mkdir()
            with (
                patch.object(
                    sandbox_module,
                    "_validate_runner_inputs",
                    return_value="/usr/bin/docker",
                ),
                patch.object(
                    sandbox_module.tempfile,
                    "mkdtemp",
                    return_value=str(broker),
                ),
                patch.object(
                    sandbox_module,
                    "launch_socket_episode",
                    side_effect=RuntimeError("startup failed"),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "startup failed"):
                    evaluate_container_agent(
                        image="agent:test",
                        agent_script=str(ROOT / "examples" / "random_agent.py"),
                        seed=1,
                    )
            self.assertFalse(broker.exists())

    def test_existing_session_is_closed_when_container_launch_fails(self):
        session = Mock(spec=SecureEpisodeSession)
        with TemporaryDirectory(prefix="eab-test-", dir="/tmp") as parent:
            broker = Path(parent) / "broker"
            broker.mkdir()
            with (
                patch.object(
                    sandbox_module,
                    "_validate_runner_inputs",
                    return_value="/usr/bin/docker",
                ),
                patch.object(
                    sandbox_module.tempfile,
                    "mkdtemp",
                    return_value=str(broker),
                ),
                patch.object(
                    sandbox_module,
                    "launch_socket_episode",
                    return_value=session,
                ),
                patch.object(sandbox_module.os, "getuid", return_value=1000),
                patch.object(sandbox_module.os, "getgid", return_value=1000),
                patch.object(
                    sandbox_module.subprocess,
                    "Popen",
                    side_effect=OSError("container launch failed"),
                ),
            ):
                with self.assertRaisesRegex(OSError, "container launch failed"):
                    evaluate_container_agent(
                        image="agent:test",
                        agent_script=str(ROOT / "examples" / "random_agent.py"),
                        seed=1,
                    )
            session.close.assert_called_once_with()
            self.assertFalse(broker.exists())

    def test_started_container_is_removed_when_output_collection_fails(self):
        session = Mock(spec=SecureEpisodeSession)
        process = Mock()
        with TemporaryDirectory(prefix="eab-test-", dir="/tmp") as parent:
            broker = Path(parent) / "broker"
            broker.mkdir()
            with (
                patch.object(
                    sandbox_module,
                    "_validate_runner_inputs",
                    return_value="/usr/bin/docker",
                ),
                patch.object(
                    sandbox_module.tempfile,
                    "mkdtemp",
                    return_value=str(broker),
                ),
                patch.object(
                    sandbox_module,
                    "launch_socket_episode",
                    return_value=session,
                ),
                patch.object(sandbox_module.os, "getuid", return_value=1000),
                patch.object(sandbox_module.os, "getgid", return_value=1000),
                patch.object(
                    sandbox_module.uuid,
                    "uuid4",
                    return_value=Mock(hex="cleanup123"),
                ),
                patch.object(
                    sandbox_module.subprocess,
                    "Popen",
                    return_value=process,
                ),
                patch.object(
                    sandbox_module,
                    "_collect_bounded",
                    side_effect=RuntimeError("collector failed"),
                ),
                patch.object(
                    sandbox_module, "_force_remove_container"
                ) as remove_container,
            ):
                with self.assertRaisesRegex(RuntimeError, "collector failed"):
                    evaluate_container_agent(
                        image="agent:test",
                        agent_script=str(ROOT / "examples" / "random_agent.py"),
                        seed=1,
                    )

            remove_container.assert_called_once()
            docker, container_name, environment = remove_container.call_args.args
            self.assertEqual(docker, "/usr/bin/docker")
            self.assertEqual(container_name, "epiagent-cleanup123")
            self.assertEqual(
                environment,
                {
                    "PATH": sandbox_module.os.environ.get(
                        "PATH", sandbox_module.os.defpath
                    )
                },
            )
            session.close.assert_called_once_with()
            self.assertFalse(broker.exists())


if __name__ == "__main__":
    unittest.main()
