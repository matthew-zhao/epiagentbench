from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from examples import run_development_matched_panel as matched_cli


class PersistentRunnerCliTests(unittest.TestCase):
    def test_preparation_runtime_preflight_bypasses_private_path_gate(self):
        payload = {
            "schema_version": (
                "epiagentbench.preparation_runtime_preflight.v2"
            ),
            "panel_id": matched_cli.PANEL_ID,
            "status": "passed",
            "provider_processes_started": 0,
            "authentication_processes_started": 0,
            "private_artifacts_required": False,
        }
        with (
            patch.object(
                sys,
                "argv",
                [
                    "run_development_matched_panel.py",
                    "preflight-preparation-runtime",
                    "--expected-benchmark-base-commit",
                    "d" * 40,
                    "--runtime-cache-dir",
                    "/private/runtime-cache",
                ],
            ),
            patch.object(
                matched_cli,
                "preflight_preparation_runtime",
                return_value=payload,
            ) as preflight,
            patch.object(
                matched_cli, "assert_durable_live_execution_paths"
            ) as durable_paths,
            patch("builtins.print") as safe_print,
        ):
            self.assertEqual(matched_cli.main(), 0)

        preflight.assert_called_once_with(
            root=Path(matched_cli.__file__).resolve().parents[1],
            expected_benchmark_base_commit="d" * 40,
            runtime_cache_dir=Path("/private/runtime-cache"),
        )
        durable_paths.assert_not_called()
        self.assertEqual(json.loads(safe_print.call_args.args[0]), payload)

    def test_preparation_runtime_verification_can_publish_create_once(self):
        payload = {
            "schema_version": (
                "epiagentbench.preparation_runtime_verification.v2"
            ),
            "panel_id": matched_cli.PANEL_ID,
            "status": "passed",
            "runtime_cache_contract": {"private": "must-not-publish"},
            "provider_processes_started": 0,
            "authentication_processes_started": 0,
            "model_calls_started": 0,
        }
        with (
            patch.object(
                sys,
                "argv",
                [
                    "run_development_matched_panel.py",
                    "verify-preparation-runtime",
                    "--preparation-runtime-receipt",
                    "/public/runtime.json",
                    "--expected-benchmark-base-commit",
                    "d" * 40,
                    "--runtime-cache-dir",
                    "/private/runtime-cache",
                    "--public-verification-receipt",
                    "/private/verification.json",
                ],
            ),
            patch.object(
                matched_cli,
                "verify_preparation_runtime",
                return_value=payload,
            ) as verify,
            patch.object(
                matched_cli,
                "create_provider_free_public_json_once",
            ) as create_once,
            patch.object(
                matched_cli, "assert_durable_live_execution_paths"
            ) as durable_paths,
            patch("builtins.print") as safe_print,
        ):
            self.assertEqual(matched_cli.main(), 0)

        verify.assert_called_once_with(
            root=Path(matched_cli.__file__).resolve().parents[1],
            receipt_path=Path("/public/runtime.json"),
            expected_benchmark_base_commit="d" * 40,
            runtime_cache_dir=Path("/private/runtime-cache"),
        )
        create_once.assert_called_once_with(
            Path("/private/verification.json"),
            {
                "schema_version": (
                    "epiagentbench.preparation_runtime_verification.v2"
                ),
                "panel_id": matched_cli.PANEL_ID,
                "status": "passed",
                "provider_processes_started": 0,
                "authentication_processes_started": 0,
                "model_calls_started": 0,
            },
        )
        durable_paths.assert_not_called()
        self.assertEqual(
            json.loads(safe_print.call_args.args[0]),
            {
                "panel_id": matched_cli.PANEL_ID,
                "status": "verified",
                "provider_processes_started": 0,
                "authentication_processes_started": 0,
                "model_calls_started": 0,
            },
        )

    def _authentication_arguments(
        self, operation: str = "authenticate"
    ) -> list[str]:
        arguments = [
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
        ]
        if operation == "authenticate":
            arguments.append("--acknowledge-interactive-authentication")
        return arguments

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
            ("preflight", "failed", 64, "run_environment_preflight"),
            (
                "run",
                "complete_pending_supervisor_completion",
                0,
                "run_panel",
            ),
            ("run", "stopped_transport_void", 64, "run_panel"),
            ("run", "stopped_supervisor_incident", 64, "run_panel"),
        )
        for operation, status, expected, target in cases:
            with (
                self.subTest(operation=operation, status=status),
                patch.object(sys, "argv", self._arguments(operation)),
                patch.object(
                    matched_cli,
                    target,
                    return_value={
                        "panel_id": "development-matched-50x6-v18",
                        "status": status,
                    },
                ) as invoked,
                patch.object(
                    matched_cli, "assert_durable_live_execution_paths"
                ) as durable_paths,
                patch.object(
                    matched_cli,
                    "assert_terminal_receipt_ready_for_exit",
                ) as terminal_receipt,
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
            if expected == 64:
                terminal_receipt.assert_called_once()
            else:
                terminal_receipt.assert_not_called()

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

    def test_authenticate_dispatches_only_to_foreground_authentication(self) -> None:
        payload = {
            "panel_id": matched_cli.PANEL_ID,
            "status": "passed",
            "providers": {
                "codex": {"status": "passed"},
                "managed_glean": {"status": "passed"},
            },
            "model_calls_started": 0,
            "credential_canary": "must-not-print",
        }
        with (
            patch.object(sys, "argv", self._authentication_arguments()),
            patch.object(
                matched_cli, "authenticate_panel", return_value=payload
            ) as authenticate,
            patch.object(
                matched_cli, "panel_authentication_status"
            ) as authentication_status,
            patch.object(
                matched_cli, "assert_durable_live_execution_paths"
            ) as durable_paths,
            patch("builtins.print") as safe_print,
        ):
            self.assertEqual(matched_cli.main(), 0)

        authentication_status.assert_not_called()
        durable_paths.assert_called_once()
        authenticate.assert_called_once_with(
            root=Path(matched_cli.__file__).resolve().parents[1],
            authentication_key_file=Path("/private/authentication.key"),
            claude_secure_storage_dir=Path("/private/claude"),
            codex_secure_storage_dir=Path("/private/codex"),
            private_state_path=Path("/private/state.json"),
            public_manifest_path=Path("/public/manifest.json"),
            acknowledge_interactive_authentication=True,
        )
        rendered = json.loads(safe_print.call_args.args[0])
        self.assertEqual(
            rendered,
            {
                "panel_id": matched_cli.PANEL_ID,
                "status": "passed",
                "authentication_ready": True,
                "codex_status": "passed",
                "managed_glean_status": "passed",
                "model_calls_started": 0,
            },
        )
        self.assertNotIn("must-not-print", safe_print.call_args.args[0])

    def test_authentication_failure_returns_nonzero_and_sanitizes_status(
        self,
    ) -> None:
        payload = {
            "panel_id": "development-matched-50x6-v18",
            "status": "retryable_failed",
            "providers": {
                "codex": {"status": "retryable_failed"},
                "managed_glean": {"status": "required"},
            },
            "model_calls_started": 0,
        }
        with (
            patch.object(sys, "argv", self._authentication_arguments()),
            patch.object(
                matched_cli, "authenticate_panel", return_value=payload
            ),
            patch.object(
                matched_cli, "assert_durable_live_execution_paths"
            ),
            patch("builtins.print") as safe_print,
        ):
            self.assertEqual(matched_cli.main(), 1)

        rendered = json.loads(safe_print.call_args.args[0])
        self.assertEqual(rendered["status"], "retryable_failed")
        self.assertIs(rendered["authentication_ready"], False)
        self.assertEqual(rendered["model_calls_started"], 0)

    def test_auth_status_is_read_only_and_does_not_require_acknowledgement(
        self,
    ) -> None:
        payload = {
            "panel_id": "development-matched-50x6-v18",
            "status": "required",
            "providers": {
                "codex": {"status": "required"},
                "managed_glean": {"status": "required"},
            },
            "model_calls_started": 0,
        }
        with (
            patch.object(
                sys, "argv", self._authentication_arguments("auth-status")
            ),
            patch.object(
                matched_cli,
                "panel_authentication_status",
                return_value=payload,
            ) as authentication_status,
            patch.object(matched_cli, "authenticate_panel") as authenticate,
            patch.object(
                matched_cli, "assert_durable_live_execution_paths"
            ),
            patch("builtins.print"),
        ):
            self.assertEqual(matched_cli.main(), 0)

        authenticate.assert_not_called()
        authentication_status.assert_called_once_with(
            root=Path(matched_cli.__file__).resolve().parents[1],
            authentication_key_file=Path("/private/authentication.key"),
            claude_secure_storage_dir=Path("/private/claude"),
            codex_secure_storage_dir=Path("/private/codex"),
            private_state_path=Path("/private/state.json"),
            public_manifest_path=Path("/public/manifest.json"),
        )

    def test_authenticate_requires_explicit_interactive_acknowledgement(
        self,
    ) -> None:
        arguments = self._authentication_arguments()
        arguments.remove("--acknowledge-interactive-authentication")
        with (
            patch.object(sys, "argv", arguments),
            patch.object(matched_cli, "authenticate_panel") as authenticate,
            patch("sys.stderr"),
            self.assertRaises(SystemExit) as raised,
        ):
            matched_cli.main()
        self.assertEqual(raised.exception.code, 2)
        authenticate.assert_not_called()

    def test_authentication_summary_rejects_unrecognized_secret_bearing_values(
        self,
    ) -> None:
        payload = {
            "panel_id": "token-panel-id-canary",
            "status": "token-status-canary",
            "providers": {
                "codex": {"status": "token-provider-canary"},
                "managed_glean": "not-a-provider-object",
            },
            "model_calls_started": "token-count-canary",
        }
        summary = matched_cli._safe_authentication_summary(payload)
        self.assertEqual(
            summary,
            {
                "panel_id": "unknown",
                "status": "unknown",
                "authentication_ready": False,
                "codex_status": "unknown",
                "managed_glean_status": "unknown",
                "model_calls_started": 0,
            },
        )


if __name__ == "__main__":
    unittest.main()
