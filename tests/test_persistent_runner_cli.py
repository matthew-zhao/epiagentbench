from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from examples import run_development_matched_panel as matched_cli


class PersistentRunnerCliTests(unittest.TestCase):
    def _arguments(self, operation: str) -> list[str]:
        output_flag = (
            "--public-preflight" if operation == "preflight" else "--public-results"
        )
        return [
            "run_development_matched_panel.py",
            operation,
            "--authentication-key",
            "/private/authentication.key",
            "--claude-secure-storage-dir",
            "/private/claude",
            "--codex-secure-storage-dir",
            "/private/codex",
            "--private-state",
            "/private/state.json",
            "--public-manifest",
            "/public/manifest.json",
            output_flag,
            "/public/output.json",
            "--supervisor-runtime",
            "/private/supervisor",
            "--acknowledge-unbounded-provider-spend",
        ]

    def test_supervised_child_exits_zero_only_for_staged_success(self) -> None:
        cases = (
            (
                "preflight",
                "passed_pending_supervisor_completion",
                0,
                "run_environment_preflight",
            ),
            ("preflight", "failed", 1, "run_environment_preflight"),
            (
                "run",
                "complete_pending_supervisor_completion",
                0,
                "run_panel",
            ),
            ("run", "stopped_transport_void", 1, "run_panel"),
            ("run", "stopped_supervisor_incident", 1, "run_panel"),
        )
        for operation, status, expected, target in cases:
            with (
                self.subTest(operation=operation, status=status),
                patch.object(sys, "argv", self._arguments(operation)),
                patch.object(
                    matched_cli,
                    target,
                    return_value={
                        "panel_id": "development-matched-50x6-v11",
                        "status": status,
                    },
                ) as invoked,
                patch.object(
                    matched_cli, "assert_durable_live_execution_paths"
                ) as durable_paths,
                patch("builtins.print"),
            ):
                self.assertEqual(matched_cli.main(), expected)
            self.assertEqual(invoked.call_count, 1)
            self.assertEqual(durable_paths.call_count, 1)
            self.assertNotIn(
                "require_persistent_supervisor", invoked.call_args.kwargs
            )
            self.assertNotIn("offline_test_evaluator", invoked.call_args.kwargs)
            self.assertEqual(
                invoked.call_args.kwargs["supervisor_runtime_dir"],
                Path("/private/supervisor"),
            )

    def test_disposable_execution_root_fails_before_runner_invocation(self) -> None:
        with (
            patch.object(sys, "argv", self._arguments("run")),
            patch.object(
                matched_cli,
                "assert_durable_live_execution_paths",
                side_effect=RuntimeError("durable execution required"),
            ),
            patch.object(matched_cli, "run_panel") as run_panel,
            self.assertRaisesRegex(RuntimeError, "durable execution required"),
        ):
            matched_cli.main()
        run_panel.assert_not_called()


if __name__ == "__main__":
    unittest.main()
