from __future__ import annotations

import json
import os
from pathlib import Path
import pwd
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from examples import run_development_matched_panel as matched_cli
from epiagentbench.development_matched_panel import FAMILIES


class PersistentRunnerCliTests(unittest.TestCase):
    def test_provider_free_entrypoint_rejects_extra_environment_before_import(
        self,
    ) -> None:
        runner = Path(matched_cli.__file__).resolve()
        account = pwd.getpwuid(os.getuid())
        provider_free_parent = Path.home()
        with (
            TemporaryDirectory(
                prefix="e35h-", dir=provider_free_parent
            ) as clean_home_raw,
            TemporaryDirectory(
                prefix="e35t-", dir=provider_free_parent
            ) as clean_tmp_raw,
        ):
            clean_home = Path(clean_home_raw)
            clean_tmp = Path(clean_tmp_raw)
            environment = {
                "HOME": str(clean_home),
                "LC_ALL": "C.UTF-8",
                "LOGNAME": account.pw_name,
                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                "SHELL": account.pw_shell,
                "TMPDIR": str(clean_tmp),
                "USER": account.pw_name,
                "__CF_USER_TEXT_ENCODING": (
                    f"0x{os.getuid():X}:0x0:0x0"
                ),
            }
            command = [
                sys.executable,
                "-I",
                "-S",
                "-B",
                str(runner),
                "publish-provider-free-json",
                "--help",
            ]
            passed = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=environment,
                check=False,
                timeout=30,
            )
            self.assertEqual(
                passed.returncode,
                0,
                passed.stderr.decode("utf-8", errors="replace"),
            )
            failed = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={**environment, "CURSOR_API_KEY": ""},
                check=False,
                timeout=30,
            )
            self.assertEqual(failed.returncode, 2)
            self.assertEqual(failed.stdout, b"")
            self.assertEqual(failed.stderr, b"")
            for name in ("HOME", "TMPDIR"):
                with self.subTest(noncanonical_directory=name):
                    noncanonical = dict(environment)
                    noncanonical[name] = environment[name] + "/"
                    rejected = subprocess.run(
                        command,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        env=noncanonical,
                        check=False,
                        timeout=30,
                    )
                    self.assertEqual(rejected.returncode, 2)
                    self.assertEqual(rejected.stdout, b"")
                    self.assertEqual(rejected.stderr, b"")

    def test_isolated_import_path_installs_once_and_spawn_replay_is_idempotent(
        self,
    ) -> None:
        source = Path("/frozen/repository/src")
        site = Path("/frozen/venv/lib/python3.11/site-packages")
        baseline = ["/stdlib", "/stdlib/lib-dynload"]
        with patch.object(sys, "path", list(baseline)):
            matched_cli._install_exact_isolated_import_path(
                source_root=source,
                site_packages=site,
            )
            installed = list(sys.path)
            self.assertEqual(
                installed,
                [*baseline, str(source), str(site)],
            )

            matched_cli._install_exact_isolated_import_path(
                source_root=source,
                site_packages=site,
            )
            self.assertEqual(sys.path, installed)

    def test_isolated_import_path_rejects_every_nonexact_inherited_state(
        self,
    ) -> None:
        source = Path("/frozen/repository/src")
        site = Path("/frozen/venv/lib/python3.11/site-packages")
        malformed = (
            ["/stdlib", str(source)],
            ["/stdlib", str(site)],
            ["/stdlib", str(site), str(source)],
            ["/stdlib", str(source), str(site), str(source)],
            ["/stdlib", str(source), "/unexpected", str(site)],
            ["/stdlib", str(source), str(site), "/unexpected"],
        )
        for candidate in malformed:
            with (
                self.subTest(candidate=candidate),
                patch.object(sys, "path", list(candidate)),
                self.assertRaisesRegex(
                    RuntimeError,
                    "malformed isolated matched-panel import path",
                ),
            ):
                matched_cli._install_exact_isolated_import_path(
                    source_root=source,
                    site_packages=site,
                )

    def test_isolated_prefix_is_rejected_before_project_import(self) -> None:
        runner = Path(matched_cli.__file__).resolve()
        with TemporaryDirectory(
            prefix="eab22-shadow-", dir="/tmp"
        ) as directory:
            shadow_root = Path(directory)
            package = shadow_root / "epiagentbench"
            package.mkdir()
            (package / "__init__.py").write_text("", encoding="utf-8")
            marker = shadow_root / "shadow-imported"
            (package / "launchd_agent.py").write_text(
                "from pathlib import Path\n"
                f"Path({str(marker)!r}).write_text('bad', encoding='utf-8')\n",
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-S",
                    "-B",
                    "-c",
                    (
                        "import runpy,sys;"
                        "sys.path.insert(0,sys.argv[2]);"
                        "runpy.run_path(sys.argv[1],run_name='__mp_main__')"
                    ),
                    str(runner),
                    str(shadow_root),
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={},
                check=False,
                timeout=30,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertFalse(marker.exists())

    def test_isolated_two_entry_tail_is_rejected_before_project_import(
        self,
    ) -> None:
        runner = Path(matched_cli.__file__).resolve()
        with TemporaryDirectory(
            prefix="eab22-shadow-tail-", dir="/tmp"
        ) as directory:
            shadow_root = Path(directory)
            package = shadow_root / "epiagentbench"
            package.mkdir()
            (package / "__init__.py").write_text("", encoding="utf-8")
            marker = shadow_root / "shadow-imported"
            (package / "launchd_agent.py").write_text(
                "from pathlib import Path\n"
                f"Path({str(marker)!r}).write_text('bad', encoding='utf-8')\n",
                encoding="utf-8",
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-S",
                    "-B",
                    "-c",
                    (
                        "import runpy,sys;"
                        "sys.path.extend((sys.argv[2],sys.argv[3]));"
                        "runpy.run_path(sys.argv[1],run_name='__mp_main__')"
                    ),
                    str(runner),
                    str(shadow_root),
                    "/unexpected-second-tail",
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={},
                check=False,
                timeout=30,
            )
            self.assertNotEqual(completed.returncode, 0)
            self.assertFalse(marker.exists())

    def test_real_isolated_file_entrypoint_replays_under_spawn_and_starts_broker(
        self,
    ) -> None:
        with TemporaryDirectory(
            prefix="e29-import-cache-", dir="/private/tmp"
        ) as import_cache_raw:
            import_cache = Path(import_cache_raw)
            import_environment = matched_cli._runtime_cache_environment(
                import_cache
            )
            for name in (
                "MPLCONFIGDIR",
                "NUMBA_CACHE_DIR",
                "XDG_CACHE_HOME",
            ):
                Path(import_environment[name]).mkdir(mode=0o700)
            try:
                with patch.dict(
                    os.environ, import_environment, clear=False
                ):
                    import starsim  # type: ignore
            except ImportError:
                self.skipTest(
                    "exact Starsim scientific runtime is unavailable"
                )
        if str(getattr(starsim, "__version__", "")) != "3.5.1":
            self.skipTest("test requires exact Starsim 3.5.1")

        runner = Path(matched_cli.__file__).resolve()
        provider_free_parent = Path.home()
        with (
            TemporaryDirectory(
                prefix="eab35-runtime-", dir="/private/tmp"
            ) as directory,
            TemporaryDirectory(
                prefix="e35h-", dir=provider_free_parent
            ) as clean_home_raw,
            TemporaryDirectory(
                prefix="e35t-", dir=provider_free_parent
            ) as clean_tmp_raw,
        ):
            clean_home = Path(clean_home_raw)
            clean_tmp = Path(clean_tmp_raw)
            runtime_cache_environment = (
                matched_cli._runtime_cache_environment(Path(directory))
            )
            for name in (
                "MPLCONFIGDIR",
                "NUMBA_CACHE_DIR",
                "XDG_CACHE_HOME",
            ):
                Path(runtime_cache_environment[name]).mkdir(mode=0o700)
            account = pwd.getpwuid(os.getuid())
            completed = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-S",
                    "-B",
                    str(runner),
                    "smoke-episode-startup",
                    "--runtime-cache-dir",
                    directory,
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={
                    "HOME": str(clean_home),
                    "LC_ALL": "C.UTF-8",
                    "LOGNAME": account.pw_name,
                    "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                    "SHELL": account.pw_shell,
                    "TMPDIR": str(clean_tmp),
                    "USER": account.pw_name,
                    "__CF_USER_TEXT_ENCODING": (
                        f"0x{os.getuid():X}:0x0:0x0"
                    ),
                },
                check=False,
                timeout=300,
            )

        self.assertEqual(
            completed.returncode,
            0,
            completed.stderr.decode("utf-8", errors="replace"),
        )
        receipt = json.loads(completed.stdout)
        self.assertEqual(
            receipt["schema_version"],
            "epiagentbench.preparation_episode_startup_smoke.v1",
        )
        self.assertEqual(receipt["public_families"], list(FAMILIES))
        self.assertEqual(receipt["public_seeds"], [0, 7, 2**31 - 2])
        self.assertEqual(receipt["serial_repetitions"], 2)
        self.assertEqual(
            receipt["trusted_evaluator_processes_started"],
            30,
        )
        self.assertTrue(receipt["public_transcript_reproducible"])
        self.assertEqual(receipt["provider_processes_started"], 0)
        self.assertEqual(receipt["authentication_processes_started"], 0)
        self.assertEqual(receipt["model_calls_started"], 0)
        self.assertFalse(receipt["private_artifacts_required"])

    def test_preparation_runtime_preflight_bypasses_private_path_gate(self):
        payload = {
            "schema_version": (
                "epiagentbench.preparation_runtime_preflight.v4"
            ),
            "panel_id": matched_cli.PANEL_ID,
            "status": "passed",
            "provider_processes_started": 0,
            "authentication_processes_started": 0,
            "model_calls_started": 0,
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
                "epiagentbench.preparation_runtime_verification.v3"
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
                    "epiagentbench.preparation_runtime_verification.v3"
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
            "--runtime-cache-dir",
            "/private/runtime-cache",
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
            "--cursor-keychain-service",
            "epiagentbench-cursor-v35",
            "--cursor-keychain-account",
            "test-account",
            "--acknowledge-unbounded-provider-spend",
        ]

    def test_operator_runtime_cache_bootstrap_overrides_all_six_values_and_restores(
        self,
    ) -> None:
        original = {
            name: f"poisoned-{index}"
            for index, name in enumerate(
                matched_cli._RUNTIME_CACHE_ENVIRONMENT_KEYS
            )
        }
        with patch.dict(os.environ, original, clear=False):
            snapshot = matched_cli._install_runtime_cache_environment(
                self._authentication_arguments()
            )
            self.assertEqual(snapshot, original)
            self.assertEqual(
                {
                    name: os.environ.get(name)
                    for name in matched_cli._RUNTIME_CACHE_ENVIRONMENT_KEYS
                },
                matched_cli._runtime_cache_environment(
                    Path("/private/runtime-cache")
                ),
            )

            matched_cli._restore_runtime_cache_environment(snapshot)
            self.assertEqual(
                {
                    name: os.environ.get(name)
                    for name in matched_cli._RUNTIME_CACHE_ENVIRONMENT_KEYS
                },
                original,
            )

    def test_runtime_cache_environment_is_restored_after_all_exit_paths(
        self,
    ) -> None:
        class SyntheticError(RuntimeError):
            pass

        def invoke(outcome: str) -> None:
            snapshot = matched_cli._install_runtime_cache_environment(
                self._authentication_arguments()
            )
            try:
                if outcome == "error":
                    raise SyntheticError("synthetic error")
                if outcome == "interrupt":
                    raise KeyboardInterrupt
            finally:
                matched_cli._restore_runtime_cache_environment(snapshot)

        for outcome, expected_exception in (
            ("success", None),
            ("error", SyntheticError),
            ("interrupt", KeyboardInterrupt),
        ):
            with (
                self.subTest(outcome=outcome),
                patch.dict(os.environ, {}, clear=True),
            ):
                if expected_exception is None:
                    invoke(outcome)
                else:
                    with self.assertRaises(expected_exception):
                        invoke(outcome)
                self.assertEqual(
                    {
                        name: os.environ.get(name)
                        for name in matched_cli._RUNTIME_CACHE_ENVIRONMENT_KEYS
                    },
                    {
                        name: None
                        for name in matched_cli._RUNTIME_CACHE_ENVIRONMENT_KEYS
                    },
                )

    def test_operator_runtime_cache_argument_rejects_ambiguous_or_unsafe_values(
        self,
    ) -> None:
        base = self._authentication_arguments()
        flag_index = base.index("--runtime-cache-dir")
        cases = {
            "missing": base[:flag_index] + base[flag_index + 2 :],
            "duplicate": base
            + ["--runtime-cache-dir=/private/second-runtime-cache"],
            "relative": (
                base[: flag_index + 1]
                + ["relative/runtime-cache"]
                + base[flag_index + 2 :]
            ),
            "non_normalized": (
                base[: flag_index + 1]
                + ["/private/runtime-cache/../runtime-cache"]
                + base[flag_index + 2 :]
            ),
        }
        for name, arguments in cases.items():
            with self.subTest(name=name), self.assertRaises(SystemExit) as raised:
                matched_cli._install_runtime_cache_environment(arguments)
            self.assertEqual(raised.exception.code, 2)

    def test_supervised_argv_stays_cache_path_free_and_uses_sealed_environment(
        self,
    ) -> None:
        cache_root = Path("/private/sealed-runtime-cache")
        sealed_environment = matched_cli._runtime_cache_environment(cache_root)
        for operation in ("preflight", "run"):
            arguments = self._arguments(operation)
            with (
                self.subTest(operation=operation),
                patch.dict(os.environ, sealed_environment, clear=False),
            ):
                self.assertNotIn("--runtime-cache-dir", arguments)
                self.assertFalse(
                    any(str(cache_root) in argument for argument in arguments)
                )
                self.assertEqual(
                    matched_cli._runtime_cache_argument(arguments),
                    str(cache_root),
                )

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
                "preflight",
                "failed_incident_sealed",
                65,
                "run_environment_preflight",
            ),
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
                patch.object(
                    matched_cli,
                    "assert_terminal_incident_ready_for_exit",
                ) as terminal_incident,
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
            if expected == 65:
                terminal_incident.assert_called_once()
            else:
                terminal_incident.assert_not_called()

    def test_terminal_audit_dispatches_only_to_provider_free_audit(self) -> None:
        arguments = [
            "runner",
            "terminal-audit",
            "--operation",
            "preflight",
            "--authentication-key",
            "/private/authentication.key",
            "--private-state",
            "/private/state.json",
            "--public-manifest",
            "/public/manifest.json",
            "--public-output",
            "/public/preflight.json",
        ]
        payload = {
            "schema_version": "epiagentbench.terminal_audit.v3",
            "panel_id": matched_cli.PANEL_ID,
            "operation": "preflight",
            "status": "reconciled_and_attested",
            "terminal_status": "failed",
            "incident_code": "supervisor_boundary_attestation_failed",
            "incident_phase": "repository_preflight",
            "attempted_operation": None,
            "completed_operation": None,
            "contract_failure_code": None,
            "model_invocations_conservatively_chargeable": 0,
            "file_sha256": "sha256:" + "a" * 64,
            "provider_processes_started": 0,
            "authentication_processes_started": 0,
            "model_calls_started": 0,
        }
        with (
            patch.object(sys, "argv", arguments),
            patch.object(
                matched_cli,
                "assert_durable_live_execution_paths",
            ) as durable_paths,
            patch.object(
                matched_cli,
                "audit_terminal_incident",
                return_value=payload,
            ) as audit,
            patch.object(
                matched_cli,
                "reconcile_terminal_receipt",
            ) as legacy_reconcile,
            patch("builtins.print") as safe_print,
        ):
            self.assertEqual(matched_cli.main(), 0)
        durable_paths.assert_called_once()
        legacy_reconcile.assert_not_called()
        audit.assert_called_once_with(
            root=Path(matched_cli.__file__).resolve().parents[1],
            operation="preflight",
            authentication_key_file=Path("/private/authentication.key"),
            private_state_path=Path("/private/state.json"),
            public_manifest_path=Path("/public/manifest.json"),
            public_output_path=Path("/public/preflight.json"),
        )
        self.assertEqual(json.loads(safe_print.call_args.args[0]), payload)

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
        durable_paths.assert_not_called()
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
                "failure_code": None,
                "failure_stage": None,
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
            "failure_code": "token-failure-code-canary",
            "failure_stage": "token-failure-stage-canary",
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
                "failure_code": None,
                "failure_stage": None,
            },
        )

    def test_authentication_summary_retains_exact_postreturn_failures(
        self,
    ) -> None:
        cases = (
            (
                "execution_contract_attestation_failed_after_provider_return",
                "execution_contract_after_provider_return",
            ),
            (
                "frozen_authentication_dependency_attestation_failed_after_"
                "provider_return",
                "authentication_dependency_after_provider_return",
            ),
            (
                "credential_integrity_failed_after_provider_return",
                "credential_integrity_after_provider_return",
            ),
        )
        for failure_code, failure_stage in cases:
            payload = {
                "panel_id": matched_cli.PANEL_ID,
                "status": "terminal_failed",
                "providers": {
                    "codex": {"status": "terminal_failed"},
                    "managed_glean": {"status": "required"},
                },
                "model_calls_started": 0,
                "failure_code": failure_code,
                "failure_stage": failure_stage,
            }
            with self.subTest(failure_code=failure_code):
                summary = matched_cli._safe_authentication_summary(payload)
                self.assertEqual(summary["failure_code"], failure_code)
                self.assertEqual(summary["failure_stage"], failure_stage)


if __name__ == "__main__":
    unittest.main()
