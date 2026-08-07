from __future__ import annotations

import json
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import plistlib
import pwd
import shutil
import stat
import subprocess
import sys
import threading
from tempfile import TemporaryDirectory
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import epiagentbench.development_matched_panel as development_matched_panel
import epiagentbench.launchd_agent as launchd_agent
import epiagentbench.persistent_supervisor as persistent_supervisor
from epiagentbench.development_matched_panel import (
    attest_provider_free_prelaunch as _real_attest_provider_free_prelaunch,
)
from epiagentbench.persistent_supervisor import ProcessDiagnostic, run_supervised_panel
from epiagentbench.launchd_agent import (
    GenerationFailureCode,
    GenerationValidationError,
    LaunchAgentError,
    LiveAttestationError,
    LiveAttestationFailureCode,
    attest_completed_launch_agent,
    attest_live_launch_agent,
    audit_launch_agent,
    finalize_launch_agent,
    generate_launch_agent,
    inspect_launch_agent,
    install_launch_agent,
    launch_agent_status,
    run_launch_agent_worker,
    start_launch_agent,
    uninstall_launch_agent,
)


_SECRET_CANARIES = (
    "crsr_DO_NOT_LEAK_76d2f3",
    "oauth-state-DO-NOT-LEAK",
    "provider-output-DO-NOT-LEAK",
)


class _ImmediateCommand:
    def poll(self) -> int:
        return 0

    def terminate(self) -> None:
        return None

    def kill(self) -> None:
        return None


class _ImmediateRunner:
    def start(self) -> _ImmediateCommand:
        return _ImmediateCommand()


class _BlockingCommand:
    def __init__(self, started: threading.Event, release: threading.Event):
        self._started = started
        self._release = release

    def poll(self) -> int | None:
        self._started.set()
        return 0 if self._release.is_set() else None

    def terminate(self) -> None:
        self._release.set()

    def kill(self) -> None:
        self._release.set()


class _BlockingRunner:
    def __init__(self, started: threading.Event, release: threading.Event):
        self._command = _BlockingCommand(started, release)

    def start(self) -> _BlockingCommand:
        return self._command


class PersistentLaunchAgentTests(unittest.TestCase):
    def test_v32_schema_identity_cuts_launchd_v16_protocol_v9(self) -> None:
        self.assertEqual(
            launchd_agent._SCHEMA,
            "epiagentbench.launchd_agent.v16",
        )
        self.assertEqual(
            launchd_agent._PROTOCOL_VERSION,
            "persistent-supervisor-v9",
        )
        self.assertEqual(
            launchd_agent._CONFIG_AUTH_DOMAIN,
            b"epiagentbench:launchd-config:v16\x00",
        )

    def test_cursor_keychain_service_is_derived_from_panel_identity(
        self,
    ) -> None:
        self.assertEqual(
            launchd_agent._required_cursor_keychain_service(
                "development-matched-50x6-v32"
            ),
            "epiagentbench-cursor-v32",
        )
        self.assertEqual(
            launchd_agent._required_cursor_keychain_service(
                "development-matched-50x6-v9-test"
            ),
            "epiagentbench-cursor-v9-test",
        )
        self.assertEqual(
            launchd_agent._required_cursor_keychain_account(),
            pwd.getpwuid(os.getuid()).pw_name,
        )

    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.runtime = self.root / "runtime"
        self.repository = Path(__file__).resolve().parents[1]
        self.cursor_keychain_account = pwd.getpwuid(os.getuid()).pw_name
        self.authentication_key = self.root / "authentication.key"
        self.authentication_key.write_bytes(b"a" * 32)
        os.chmod(self.authentication_key, 0o600)
        self.claude_storage = self.root / "claude-storage"
        self.codex_storage = self.root / "codex-storage"
        self.claude_storage.mkdir(mode=0o700)
        self.codex_storage.mkdir(mode=0o700)
        self.private_state = self.root / "private.json"
        self.public_manifest = (
            self.root
            / "development-matched-50x6-v32.manifest.json"
        )
        self.public_authentication = (
            self.root
            / "development-matched-50x6-v32.authentication.json"
        )
        self.public_preflight = (
            self.root
            / "development-matched-50x6-v32.preflight.json"
        )
        self.public_results = (
            self.root / "development-matched-50x6-v32.json"
        )
        self.private_state.write_text("{}", encoding="utf-8")
        self.public_manifest.write_text(
            json.dumps(
                {
                    "schema_version": development_matched_panel.SCHEMA_VERSION,
                    "panel_id": development_matched_panel.PANEL_ID,
                    "precommitment_sha256": "sha256:" + "b" * 64,
                    "runtime_contract": {
                        "python_entrypoint_kind": "regular_file",
                        "python_executable_sha256": (
                            launchd_agent._python_entrypoint_binding(
                                Path(sys.executable).resolve()
                            )["target"]["sha256"]
                        )
                    },
                }
            ),
            encoding="utf-8",
        )
        self.public_authentication.write_text(
            json.dumps(
                {
                    "schema_version": (
                        development_matched_panel._AUTHENTICATION_RECEIPT_SCHEMA
                    ),
                    "panel_id": development_matched_panel.PANEL_ID,
                    "status": "passed",
                    "model_calls_started": 0,
                }
            ),
            encoding="utf-8",
        )
        os.chmod(self.private_state, 0o600)
        os.chmod(self.public_manifest, 0o600)
        os.chmod(self.public_authentication, 0o600)
        self.authentication_readiness = patch.object(
            development_matched_panel,
            "assert_panel_authentication_ready",
            create=True,
            side_effect=AssertionError(
                "outer LaunchAgent control plane entered credential readiness"
            ),
        )
        self.mock_authentication_readiness = (
            self.authentication_readiness.start()
        )
        self.durable_readiness = patch.object(
            development_matched_panel,
            "assert_durable_live_execution_paths",
        )
        self.mock_durable_readiness = self.durable_readiness.start()
        self.environment_preflight_readiness = patch.object(
            development_matched_panel,
            "assert_environment_preflight_ready",
            return_value={
                "panel_id": development_matched_panel.PANEL_ID,
                "status": "passed",
                "artifact_kind": "preflight",
            },
        )
        self.mock_environment_preflight_readiness = (
            self.environment_preflight_readiness.start()
        )
        self.provider_free_prelaunch = patch.object(
            development_matched_panel,
            "attest_provider_free_prelaunch",
            return_value={
                "panel_id": development_matched_panel.PANEL_ID,
                "operation": "production",
                "status": "passed",
                "provider_processes_started": 0,
                "model_calls_started": 0,
            },
        )
        self.mock_provider_free_prelaunch = (
            self.provider_free_prelaunch.start()
        )
        self.public_authentication_receipt_readiness = patch.object(
            development_matched_panel,
            "assert_public_authentication_receipt_ready",
            return_value={
                "panel_id": development_matched_panel.PANEL_ID,
                "status": "passed",
                "model_calls_started": 0,
            },
        )
        self.mock_public_authentication_receipt_readiness = (
            self.public_authentication_receipt_readiness.start()
        )
        self.isolated_process = patch.object(
            launchd_agent,
            "_validate_isolated_python_process",
            return_value={},
        )
        self.mock_isolated_process = self.isolated_process.start()
        self.boot_identity = patch.object(
            persistent_supervisor,
            "_boot_token",
            return_value=b"offline-stable-boot-session",
        )
        self.mock_boot_identity = self.boot_identity.start()
        self.process_birth_identity = patch.object(
            persistent_supervisor,
            "_process_birth_token",
            return_value=b"offline-stable-process-birth",
        )
        self.mock_process_birth_identity = (
            self.process_birth_identity.start()
        )

    def tearDown(self) -> None:
        self.process_birth_identity.stop()
        self.boot_identity.stop()
        self.isolated_process.stop()
        self.public_authentication_receipt_readiness.stop()
        self.provider_free_prelaunch.stop()
        self.environment_preflight_readiness.stop()
        self.durable_readiness.stop()
        self.authentication_readiness.stop()
        self.temporary.cleanup()

    def _generate(self, **changes: object) -> dict:
        arguments: dict[str, object] = {
            "runtime_dir": self.runtime,
            "repository_root": self.repository,
            "python_executable": Path(sys.executable).resolve(),
            "authentication_key_file": self.authentication_key,
            "claude_secure_storage_dir": self.claude_storage,
            "codex_secure_storage_dir": self.codex_storage,
            "private_state_path": self.private_state,
            "public_manifest_path": self.public_manifest,
            "public_preflight_path": None,
            "public_results_path": self.public_results,
            "cursor_keychain_service": "epiagentbench-cursor-v32",
            "cursor_keychain_account": self.cursor_keychain_account,
            "operation": "production",
            "path_environment": "/usr/bin:/bin:/usr/sbin:/sbin",
            "instance_token": "1" * 24,
        }
        arguments.update(changes)
        return generate_launch_agent(**arguments)

    def _enable_v18_runtime_binding(
        self,
        *,
        name: str = "v18-runtime-cache",
    ) -> tuple[Path, dict[str, str]]:
        cache_root = self.root / name
        cache_root.mkdir(mode=0o700)
        for child in ("matplotlib", "numba", "xdg"):
            (cache_root / child).mkdir(mode=0o700)
        environment = {
            "MPLBACKEND": "Agg",
            "MPLCONFIGDIR": str(cache_root / "matplotlib"),
            "NUMBA_CACHE_DIR": str(cache_root / "numba"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "STARSIM_INSTALL_FONTS": "0",
            "XDG_CACHE_HOME": str(cache_root / "xdg"),
        }

        manifest = json.loads(
            self.public_manifest.read_text(encoding="utf-8")
        )
        python_binding = launchd_agent._python_entrypoint_binding(
            Path(sys.executable).resolve()
        )
        manifest["runtime_contract"][
            "python_executable_binding_sha256"
        ] = launchd_agent._component_sha256(python_binding)
        cache_contract = launchd_agent._runtime_cache_contract(cache_root)
        manifest["preparation_runtime_contract"] = {
            "schema_version": "epiagentbench.bound_preparation_runtime.v3",
            "runtime_cache_contract_sha256": (
                launchd_agent._component_sha256(cache_contract)
            ),
        }
        self.assertEqual(
            cache_contract["environment"],
            environment,
        )
        self.public_manifest.write_text(
            json.dumps(manifest),
            encoding="utf-8",
        )
        return cache_root, environment

    def _copied_isolated_python(self, name: str) -> Path:
        """Create a movable regular-file interpreter with a valid venv root."""

        venv = self.root / name
        binary_dir = venv / "bin"
        site_packages = (
            venv
            / "lib"
            / f"python{sys.version_info.major}.{sys.version_info.minor}"
            / "site-packages"
        )
        binary_dir.mkdir(parents=True, mode=0o700)
        site_packages.mkdir(parents=True, mode=0o700)
        target = binary_dir / "python"
        shutil.copy2(Path(sys.executable).resolve(), target)
        os.chmod(target, 0o700)
        dylib_source = (
            Path(sys.base_prefix)
            / "lib"
            / f"libpython{sys.version_info.major}.{sys.version_info.minor}.dylib"
        )
        if dylib_source.is_file():
            dylib_target = venv / "lib" / dylib_source.name
            shutil.copy2(dylib_source, dylib_target)
            os.chmod(dylib_target, 0o700)
        pyvenv = venv / "pyvenv.cfg"
        pyvenv.write_text(
            "\n".join(
                (
                    f"home = {Path(sys.base_prefix) / 'bin'}",
                    "include-system-site-packages = false",
                    (
                        "version = "
                        f"{sys.version_info.major}.{sys.version_info.minor}."
                        f"{sys.version_info.micro}"
                    ),
                    f"executable = {Path(sys.executable).resolve()}",
                )
            )
            + "\n",
            encoding="utf-8",
        )
        os.chmod(pyvenv, 0o600)
        return target

    @staticmethod
    def _not_loaded_launchctl(arguments, **kwargs):
        return subprocess.CompletedProcess(arguments, 113, stdout=b"", stderr=b"")

    def _config_and_key(self) -> tuple[dict, bytes]:
        config, _, key = launchd_agent._load_and_validate(
            self.runtime,
            authentication_key_file=self.authentication_key,
        )
        return config, key

    def _commit_start(self) -> tuple[dict, bytes]:
        config, key = self._config_and_key()
        launchd_agent._write_start_marker(
            self.runtime,
            config=config,
            authentication_key=key,
        )
        return config, key

    def _complete_core(self) -> tuple[dict, bytes]:
        config, key = self._config_and_key()
        status = run_supervised_panel(
            runner_argv=("unused-offline-runner",),
            environment={},
            runtime_dir=self.runtime,
            authentication_key=key,
            execution_context_sha256=config["execution_context_sha256"],
            command_runner=_ImmediateRunner(),
        )
        self.assertEqual(status["lifecycle"], "completed")
        return config, key

    def _copy_runtime_sources(self, name: str) -> Path:
        copied_repository = self.root / name
        for relative_path in (
            Path("examples/run_development_matched_panel.py"),
            Path("examples/run_persistent_panel_supervisor.py"),
            Path("src/epiagentbench/launchd_agent.py"),
            Path("src/epiagentbench/persistent_supervisor.py"),
            Path("src/epiagentbench/development_matched_panel.py"),
        ):
            destination = copied_repository / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.repository / relative_path, destination)
        return copied_repository

    def test_generated_agent_is_one_shot_owner_only_and_secret_free(self) -> None:
        original = os.environ.get("CURSOR_API_KEY")
        os.environ["CURSOR_API_KEY"] = _SECRET_CANARIES[0]
        try:
            generated = self._generate()
        finally:
            if original is None:
                os.environ.pop("CURSOR_API_KEY", None)
            else:
                os.environ["CURSOR_API_KEY"] = original

        config_path = Path(generated["config_path"])
        plist_path = Path(generated["plist_path"])
        self.assertEqual(self.runtime.stat().st_mode & 0o777, 0o700)
        self.assertEqual(config_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(plist_path.stat().st_mode & 0o777, 0o600)
        self.assertFalse(self.runtime.is_symlink())
        self.assertFalse(config_path.is_symlink())
        self.assertFalse(plist_path.is_symlink())

        raw_plist = plist_path.read_bytes()
        plist = plistlib.loads(raw_plist)
        arguments = plist["ProgramArguments"]
        self.assertEqual(
            arguments,
            [
                "/usr/bin/caffeinate",
                "-dimsu",
                str(Path(sys.executable).resolve()),
                "-I",
                "-S",
                "-B",
                str(
                    self.repository
                    / "examples"
                    / "run_persistent_panel_supervisor.py"
                ),
                "worker",
                "--config",
                str(config_path),
            ],
        )
        self.assertEqual(plist["StandardOutPath"], "/dev/null")
        self.assertEqual(plist["StandardErrorPath"], "/dev/null")
        self.assertIs(plist["RunAtLoad"], False)
        self.assertIs(plist["KeepAlive"], False)
        self.assertNotIn("EnvironmentVariables", plist)

        # The public process boundary points only at the owner-only config.  It
        # must not expose credential paths, private-state paths, provider
        # commands, Keychain metadata, or ambient environment values.
        joined_arguments = "\0".join(arguments)
        for private_value in (
            self.authentication_key,
            self.claude_storage,
            self.codex_storage,
            self.private_state,
            self.public_manifest,
            self.public_results,
        ):
            self.assertNotIn(str(private_value), joined_arguments)
        self.assertNotIn("epiagentbench-cursor-v32", joined_arguments)
        self.assertNotIn(self.cursor_keychain_account, arguments)
        self.assertNotIn("CURSOR_API_KEY", joined_arguments)

        all_generated = raw_plist + config_path.read_bytes()
        for canary in _SECRET_CANARIES:
            self.assertNotIn(canary.encode(), all_generated)

        # The private config contains references, never credential contents.
        config = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertNotIn("cursor_api_key", config)
        self.assertNotIn("environment", config)

    def test_generated_agent_uses_canonical_owner_only_socket_tmpdir(self) -> None:
        with TemporaryDirectory(prefix="e32t-", dir="/tmp") as temporary_raw:
            temporary_root = Path(temporary_raw).resolve(strict=True)
            with patch.object(
                launchd_agent.tempfile,
                "gettempdir",
                return_value=str(temporary_root),
            ):
                self._generate()
            config, _ = self._config_and_key()

            sealed_temporary_root = Path(
                config["base_environment"]["TMPDIR"]
            )
            metadata = sealed_temporary_root.lstat()
            self.assertEqual(
                sealed_temporary_root,
                sealed_temporary_root.resolve(strict=True),
            )
            self.assertFalse(sealed_temporary_root.is_symlink())
            self.assertTrue(sealed_temporary_root.is_dir())
            self.assertEqual(metadata.st_uid, os.getuid())
            self.assertEqual(metadata.st_mode & 0o777, 0o700)
            self.assertLessEqual(
                len(os.fsencode(str(sealed_temporary_root))),
                launchd_agent._MAX_EPISODE_TMPDIR_BYTES,
            )

    def test_generation_environment_refusal_precedes_private_reads_and_writes(
        self,
    ) -> None:
        unsafe_temporary_root = self.root / "shared-temp"
        unsafe_temporary_root.mkdir(mode=0o755)

        with (
            patch.object(
                launchd_agent.tempfile,
                "gettempdir",
                return_value=str(unsafe_temporary_root),
            ),
            patch.object(
                launchd_agent,
                "_require_directory",
                side_effect=AssertionError("filesystem readiness was entered"),
            ) as require_directory,
            patch.object(
                launchd_agent,
                "_require_regular",
                side_effect=AssertionError("private input was inspected"),
            ) as require_regular,
            patch.object(
                launchd_agent,
                "_read_authentication_key",
                side_effect=AssertionError("authentication key was read"),
            ) as read_authentication_key,
            self.assertRaises(GenerationValidationError) as raised,
        ):
            self._generate()

        self.assertIs(
            raised.exception.failure_code,
            GenerationFailureCode.ENVIRONMENT_INVALID,
        )
        require_directory.assert_not_called()
        require_regular.assert_not_called()
        read_authentication_key.assert_not_called()
        self.assertFalse(self.runtime.exists())

    def test_generation_rejects_noncanonical_public_output_before_runtime(
        self,
    ) -> None:
        cases = (
            {
                "operation": "preflight",
                "public_preflight_path": self.root / "typo-preflight.json",
                "public_results_path": None,
            },
            {
                "operation": "production",
                "public_preflight_path": None,
                "public_results_path": self.root / "typo-results.json",
            },
        )
        for changes in cases:
            with self.subTest(operation=changes["operation"]):
                with self.assertRaisesRegex(
                    LaunchAgentError,
                    "failed safely",
                ):
                    self._generate(**changes)
                self.assertFalse(self.runtime.exists())

    def test_generation_rejects_foreign_cursor_keychain_namespace_before_key_read(
        self,
    ) -> None:
        for case, service in (
            ("v31", "epiagentbench-cursor-v31"),
            ("foreign", "epiagentbench-cursor-foreign"),
        ):
            runtime = self.root / f"{case}-cursor-service-runtime"
            with self.subTest(case=case, service=service):
                with patch.object(
                    launchd_agent,
                    "_read_authentication_key",
                    side_effect=AssertionError(
                        "namespace rejection must precede key access"
                    ),
                ) as authentication_read:
                    with self.assertRaises(LaunchAgentError):
                        self._generate(
                            runtime_dir=runtime,
                            instance_token=f"{case}-cursor-service",
                            cursor_keychain_service=service,
                        )
                authentication_read.assert_not_called()
                self.assertFalse(runtime.exists())

    def test_generation_rejects_foreign_cursor_keychain_account_before_key_read(
        self,
    ) -> None:
        for case, account in (
            ("typo", f"{self.cursor_keychain_account}-typo"),
            ("foreign", "foreign-keychain-account"),
        ):
            runtime = self.root / f"{case}-cursor-account-runtime"
            with self.subTest(case=case, account=account):
                with patch.object(
                    launchd_agent,
                    "_read_authentication_key",
                    side_effect=AssertionError(
                        "account rejection must precede key access"
                    ),
                ) as authentication_read:
                    with self.assertRaises(LaunchAgentError):
                        self._generate(
                            runtime_dir=runtime,
                            instance_token=f"{case}-cursor-account",
                            cursor_keychain_account=account,
                        )
                authentication_read.assert_not_called()
                self.assertFalse(runtime.exists())

    def test_v18_cli_bootstraps_work_with_site_hooks_disabled(self) -> None:
        for relative_script in (
            "examples/run_development_matched_panel.py",
            "examples/run_persistent_panel_supervisor.py",
        ):
            completed = subprocess.run(
                [
                    str(Path(sys.executable)),
                    "-I",
                    "-S",
                    "-B",
                    str(self.repository / relative_script),
                    "--help",
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                cwd="/",
                env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"},
                timeout=30,
            )
            self.assertEqual(
                completed.returncode,
                0,
                completed.stderr.decode("utf-8", errors="replace"),
            )
            direct = subprocess.run(
                [
                    str(Path(sys.executable)),
                    str(self.repository / relative_script),
                    "--help",
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                cwd="/",
                env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"},
                timeout=30,
            )
            self.assertEqual(direct.returncode, 2)

    def test_v18_generation_seals_exact_runtime_cache_environment(self) -> None:
        cache_root, expected_environment = (
            self._enable_v18_runtime_binding()
        )

        generated = self._generate(runtime_cache_dir=cache_root)
        config, _ = self._config_and_key()
        sealed_environment = {
            name: config["base_environment"][name]
            for name in launchd_agent._RUNTIME_CACHE_ENVIRONMENT_KEYS
        }

        self.assertEqual(sealed_environment, expected_environment)
        self.assertEqual(
            set(config["base_environment"])
            & launchd_agent._RUNTIME_CACHE_ENVIRONMENT_KEYS,
            set(expected_environment),
        )
        plist = plistlib.loads(Path(generated["plist_path"]).read_bytes())
        self.assertNotIn("EnvironmentVariables", plist)

    def test_v18_generation_overrides_and_restores_poisoned_ambient_cache_environment(
        self,
    ) -> None:
        cache_root, expected_environment = (
            self._enable_v18_runtime_binding()
        )
        poisoned = {
            name: f"poisoned-{index}"
            for index, name in enumerate(
                launchd_agent._RUNTIME_CACHE_ENVIRONMENT_KEYS
            )
        }

        original_compute_execution_context = (
            persistent_supervisor.compute_execution_context_sha256
        )

        def assert_sealed_environment(**kwargs):
            self.assertEqual(
                {
                    name: os.environ.get(name)
                    for name in expected_environment
                },
                expected_environment,
            )
            return original_compute_execution_context(**kwargs)

        with (
            patch.object(
                persistent_supervisor,
                "compute_execution_context_sha256",
                side_effect=assert_sealed_environment,
            ),
            patch.dict(os.environ, poisoned, clear=False),
        ):
            before = {
                name: os.environ.get(name) for name in expected_environment
            }
            self._generate(runtime_cache_dir=cache_root)
            self.assertEqual(
                {
                    name: os.environ.get(name)
                    for name in expected_environment
                },
                before,
            )

    def test_v18_start_self_bootstraps_and_restores_cache_environment(
        self,
    ) -> None:
        cache_root, expected_environment = (
            self._enable_v18_runtime_binding()
        )
        self._generate(runtime_cache_dir=cache_root)
        self.mock_provider_free_prelaunch.reset_mock()

        def assert_sealed_environment(**_kwargs):
            self.assertEqual(
                {
                    name: os.environ.get(name)
                    for name in expected_environment
                },
                expected_environment,
            )
            return {
                "panel_id": development_matched_panel.PANEL_ID,
                "operation": "production",
                "status": "passed",
                "provider_processes_started": 0,
                "model_calls_started": 0,
            }

        self.mock_provider_free_prelaunch.side_effect = (
            assert_sealed_environment
        )
        poisoned = {
            name: f"wrong-{index}"
            for index, name in enumerate(expected_environment)
        }

        def fake_launchctl(arguments, **_kwargs):
            return subprocess.CompletedProcess(
                arguments, 0, stdout=b"", stderr=b""
            )

        with patch.dict(os.environ, poisoned, clear=False):
            before = {
                name: os.environ.get(name) for name in expected_environment
            }
            response = start_launch_agent(
                self.runtime,
                authentication_key_file=self.authentication_key,
                command_runner=fake_launchctl,
            )
            self.assertEqual(response["state"], "start_requested")
            self.assertEqual(
                {
                    name: os.environ.get(name)
                    for name in expected_environment
                },
                before,
            )
        self.assertTrue(
            (self.runtime / "launchd-start-request.json").is_file()
        )

    def test_v18_prelaunch_refusal_restores_cache_environment_before_marker(
        self,
    ) -> None:
        cache_root, expected_environment = (
            self._enable_v18_runtime_binding()
        )
        self._generate(runtime_cache_dir=cache_root)
        calls: list[list[str]] = []

        def refuse_after_environment_check(**_kwargs):
            self.assertEqual(
                {
                    name: os.environ.get(name)
                    for name in expected_environment
                },
                expected_environment,
            )
            raise RuntimeError("offline refusal")

        self.mock_provider_free_prelaunch.side_effect = (
            refuse_after_environment_check
        )

        def forbidden_launchctl(arguments, **_kwargs):
            calls.append(list(arguments))
            return subprocess.CompletedProcess(
                arguments, 0, stdout=b"", stderr=b""
            )

        missing = object()
        before = {
            name: os.environ.get(name, missing)
            for name in expected_environment
        }
        try:
            for name in expected_environment:
                os.environ.pop(name, None)
            with self.assertRaises(LaunchAgentError):
                start_launch_agent(
                    self.runtime,
                    authentication_key_file=self.authentication_key,
                    command_runner=forbidden_launchctl,
                )
            self.assertTrue(
                all(name not in os.environ for name in expected_environment)
            )
        finally:
            for name, value in before.items():
                if value is missing:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = str(value)
        self.assertFalse(
            (self.runtime / "launchd-start-request.json").exists()
        )
        self.assertTrue(
            (self.runtime / "launchd-control.lock").is_file()
        )
        self.assertEqual(calls, [])

    def test_v18_all_config_controls_self_bootstrap_and_restore_environment(
        self,
    ) -> None:
        cache_root, expected_environment = (
            self._enable_v18_runtime_binding()
        )
        self._generate(runtime_cache_dir=cache_root)
        config, key = self._commit_start()
        self._complete_core()
        launchd_agent._atomic_worker_status(
            self.runtime,
            config=config,
            authentication_key=key,
            state="supervisor_exited",
            reason="success",
        )

        def exercise(
            operation: str,
            *,
            ambient: str,
        ) -> None:
            calls: list[list[str]] = []
            control_runtime = self.runtime
            if operation == "install":
                token = "2" * 24 if ambient == "absent" else "3" * 24
                control_runtime = self.root / f"install-{ambient}-runtime"
                self._generate(
                    runtime_dir=control_runtime,
                    runtime_cache_dir=cache_root,
                    instance_token=token,
                )

            def sealed_launchctl(arguments, **_kwargs):
                self.assertEqual(
                    {
                        name: os.environ.get(name)
                        for name in expected_environment
                    },
                    expected_environment,
                )
                calls.append(list(arguments))
                if arguments[1] == "print":
                    return subprocess.CompletedProcess(
                        arguments,
                        0,
                        stdout=b"state = not running\n",
                        stderr=b"",
                    )
                return subprocess.CompletedProcess(
                    arguments,
                    0,
                    stdout=b"",
                    stderr=b"",
                )

            original = {
                name: os.environ.get(name)
                for name in expected_environment
            }
            missing = {
                name for name in expected_environment
                if name not in os.environ
            }
            try:
                if ambient == "absent":
                    for name in expected_environment:
                        os.environ.pop(name, None)
                    expected_after = {
                        name: None for name in expected_environment
                    }
                else:
                    poisoned = {
                        name: f"{operation}-poison-{index}"
                        for index, name in enumerate(expected_environment)
                    }
                    os.environ.update(poisoned)
                    expected_after = dict(poisoned)

                if operation == "inspect":
                    response = inspect_launch_agent(
                        control_runtime,
                        authentication_key_file=self.authentication_key,
                    )
                    self.assertIs(response["configured"], True)
                    self.assertEqual(calls, [])
                elif operation == "install":
                    response = install_launch_agent(
                        control_runtime,
                        authentication_key_file=self.authentication_key,
                        command_runner=sealed_launchctl,
                    )
                    self.assertEqual(response["state"], "installed")
                    self.assertEqual([call[1] for call in calls], ["bootstrap"])
                elif operation == "status":
                    response = launch_agent_status(
                        control_runtime,
                        authentication_key_file=self.authentication_key,
                        command_runner=sealed_launchctl,
                    )
                    self.assertEqual(response["launchd_state"], "not_running")
                    self.assertEqual([call[1] for call in calls], ["print"])
                else:
                    response = uninstall_launch_agent(
                        control_runtime,
                        authentication_key_file=self.authentication_key,
                        command_runner=sealed_launchctl,
                    )
                    self.assertEqual(response["state"], "uninstalled")
                    self.assertEqual(
                        [call[1] for call in calls],
                        ["print", "bootout"],
                    )

                self.assertEqual(
                    {
                        name: os.environ.get(name)
                        for name in expected_environment
                    },
                    expected_after,
                )
            finally:
                for name in expected_environment:
                    if name in missing:
                        os.environ.pop(name, None)
                    else:
                        value = original[name]
                        if value is not None:
                            os.environ[name] = value

        for operation in ("inspect", "install", "status", "uninstall"):
            for ambient in ("absent", "poisoned"):
                with self.subTest(operation=operation, ambient=ambient):
                    exercise(operation, ambient=ambient)

    def test_v18_generation_requires_exact_bound_runtime_cache_root(
        self,
    ) -> None:
        cache_root, _ = self._enable_v18_runtime_binding()

        with self.assertRaises(LaunchAgentError):
            self._generate()
        self.assertFalse(self.runtime.exists())

        wrong_cache = self.root / "wrong-v18-runtime-cache"
        wrong_cache.mkdir(mode=0o700)
        wrong_runtime = self.root / "wrong-cache-runtime"
        with self.assertRaises(LaunchAgentError):
            self._generate(
                runtime_dir=wrong_runtime,
                runtime_cache_dir=wrong_cache,
                instance_token="wrong-cache-root",
            )
        self.assertFalse(wrong_runtime.exists())
        self.assertTrue(cache_root.is_dir())

    def test_v18_runtime_environment_projection_is_exactly_six_keys(
        self,
    ) -> None:
        cache_root, expected_environment = (
            self._enable_v18_runtime_binding()
        )
        contract = launchd_agent._runtime_cache_contract(cache_root)
        cases: list[tuple[str, dict, dict]] = []
        missing = json.loads(json.dumps(contract))
        missing["environment"].pop("MPLBACKEND")
        cases.append(("missing", missing, dict(expected_environment)))
        extra = json.loads(json.dumps(contract))
        extra["environment"]["EXTRA_CACHE_KEY"] = "forbidden"
        cases.append(("extra", extra, dict(expected_environment)))
        wrong = json.loads(json.dumps(contract))
        wrong["environment"]["MPLBACKEND"] = "TkAgg"
        cases.append(("wrong", wrong, dict(expected_environment)))
        base_mismatch = dict(expected_environment)
        base_mismatch["XDG_CACHE_HOME"] = "wrong"
        cases.append(("base_mismatch", contract, base_mismatch))

        for name, candidate, base_environment in cases:
            with self.subTest(name=name), self.assertRaises(ValueError):
                launchd_agent._runtime_cache_environment_values(
                    candidate,
                    base_environment=base_environment,
                )

    def test_v18_live_load_rejects_runtime_cache_inode_drift(self) -> None:
        cache_root, _ = self._enable_v18_runtime_binding()
        self._generate(runtime_cache_dir=cache_root)

        original = cache_root / "numba"
        original.rename(cache_root / "numba-original")
        original.mkdir(mode=0o700)

        with self.assertRaises(ValueError):
            launchd_agent._load_and_validate(
                self.runtime,
                authentication_key_file=self.authentication_key,
            )
        calls: list[list[str]] = []

        def forbidden_control(arguments, **_kwargs):
            calls.append(list(arguments))
            return subprocess.CompletedProcess(
                arguments, 0, stdout=b"", stderr=b""
            )

        with self.assertRaises(LaunchAgentError):
            start_launch_agent(
                self.runtime,
                authentication_key_file=self.authentication_key,
                command_runner=forbidden_control,
            )
        self.assertEqual(calls, [])
        self.assertFalse(
            (self.runtime / "launchd-start-request.json").exists()
        )

    def test_v18_live_load_rejects_runtime_cache_content_drift(self) -> None:
        cache_root, _ = self._enable_v18_runtime_binding()
        cached_file = cache_root / "numba" / "compiled.cache"
        cached_file.write_bytes(b"reviewed-cache-bytes")
        os.chmod(cached_file, 0o600)
        manifest = json.loads(
            self.public_manifest.read_text(encoding="utf-8")
        )
        cache_contract = launchd_agent._runtime_cache_contract(cache_root)
        manifest["preparation_runtime_contract"][
            "runtime_cache_contract_sha256"
        ] = launchd_agent._component_sha256(cache_contract)
        self.public_manifest.write_text(
            json.dumps(manifest),
            encoding="utf-8",
        )
        self._generate(runtime_cache_dir=cache_root)

        cached_file.write_bytes(b"changed-cache-bytes")
        os.chmod(cached_file, 0o600)

        with self.assertRaises(ValueError):
            launchd_agent._load_and_validate(
                self.runtime,
                authentication_key_file=self.authentication_key,
            )

    def test_v18_runtime_cache_ignores_nested_directory_mtime_drift(
        self,
    ) -> None:
        cache_root, _ = self._enable_v18_runtime_binding()
        compiled_directory = cache_root / "numba" / "compiled"
        compiled_directory.mkdir(mode=0o700)
        cached_file = compiled_directory / "artifact.cache"
        cached_file.write_bytes(b"stable-cache-bytes")
        os.chmod(cached_file, 0o600)
        before = launchd_agent._runtime_cache_contract(cache_root)
        metadata = compiled_directory.stat()

        os.utime(
            compiled_directory,
            ns=(metadata.st_atime_ns, metadata.st_mtime_ns + 1_000_000),
        )

        after = launchd_agent._runtime_cache_contract(cache_root)
        self.assertEqual(after, before)
        nested_directory = next(
            item
            for item in after["inventory"]
            if item["relative_path"] == "numba/compiled"
        )
        self.assertEqual(nested_directory["kind"], "directory")
        self.assertNotIn("mtime_ns", nested_directory)

    def test_v26_post_completion_cache_safety_rejects_unsafe_evolution(
        self,
    ) -> None:
        cache_root, _ = self._enable_v18_runtime_binding()
        contract = launchd_agent._runtime_cache_contract(cache_root)
        safe_file = cache_root / "numba" / "generated.cache"
        safe_file.write_bytes(b"owner-only-cache")
        os.chmod(safe_file, 0o600)
        launchd_agent._validate_runtime_cache_contract_safety(contract)

        unsafe_link = cache_root / "xdg" / "escape"
        unsafe_link.symlink_to(self.private_state)
        with self.assertRaises(ValueError):
            launchd_agent._validate_runtime_cache_contract_safety(
                contract
            )
        unsafe_link.unlink()

        os.chmod(safe_file, 0o644)
        with self.assertRaises(ValueError):
            launchd_agent._validate_runtime_cache_contract_safety(
                contract
            )
        os.chmod(safe_file, 0o600)

        original = cache_root / "matplotlib"
        original.rename(cache_root / "matplotlib-original")
        original.mkdir(mode=0o700)
        with self.assertRaises(ValueError):
            launchd_agent._validate_runtime_cache_contract_safety(
                contract
            )

    def test_v18_runtime_cache_must_be_dedicated_and_non_overlapping(
        self,
    ) -> None:
        cache_root, _ = self._enable_v18_runtime_binding(
            name="claude-storage/runtime-cache",
        )

        with self.assertRaises(LaunchAgentError):
            self._generate(runtime_cache_dir=cache_root)
        self.assertFalse(self.runtime.exists())

    def test_v18_runtime_cache_root_rejects_uncommitted_entries(self) -> None:
        cache_root, _ = self._enable_v18_runtime_binding()
        unexpected = cache_root / "ambient.txt"
        unexpected.write_text("ambient", encoding="utf-8")
        os.chmod(unexpected, 0o600)

        with self.assertRaises(LaunchAgentError):
            self._generate(runtime_cache_dir=cache_root)
        self.assertFalse(self.runtime.exists())

    def test_v18_live_load_rejects_sealed_cache_environment_drift(
        self,
    ) -> None:
        cache_root, _ = self._enable_v18_runtime_binding()
        generated = self._generate(runtime_cache_dir=cache_root)
        config_path = Path(generated["config_path"])
        raw_config = json.loads(config_path.read_text(encoding="utf-8"))
        unsigned = launchd_agent._open_payload(
            launchd_agent._CONFIG_AUTH_DOMAIN,
            raw_config,
            b"a" * 32,
        )
        unsigned["base_environment"]["MPLBACKEND"] = "TkAgg"
        resealed = launchd_agent._seal_payload(
            launchd_agent._CONFIG_AUTH_DOMAIN,
            unsigned,
            b"a" * 32,
        )
        config_path.write_text(
            json.dumps(resealed),
            encoding="utf-8",
        )
        os.chmod(config_path, 0o600)

        with self.assertRaises(ValueError):
            launchd_agent._load_and_validate(
                self.runtime,
                authentication_key_file=self.authentication_key,
            )

    def test_v32_rejects_predecessor_launchd_schemas_before_control_action(
        self,
    ) -> None:
        for version in (11, 12, 13, 14, 15):
            with self.subTest(schema_version=version):
                runtime = self.root / f"legacy-v{version}-runtime"
                generated = self._generate(
                    runtime_dir=runtime,
                    instance_token=f"legacy-v{version}",
                )
                config_path = Path(generated["config_path"])
                raw_config = json.loads(
                    config_path.read_text(encoding="utf-8")
                )
                unsigned = launchd_agent._open_payload(
                    launchd_agent._CONFIG_AUTH_DOMAIN,
                    raw_config,
                    b"a" * 32,
                )
                unsigned["schema_version"] = (
                    f"epiagentbench.launchd_agent.v{version}"
                )
                resealed = launchd_agent._seal_payload(
                    launchd_agent._CONFIG_AUTH_DOMAIN,
                    unsigned,
                    b"a" * 32,
                )
                config_path.write_text(
                    json.dumps(resealed), encoding="utf-8"
                )
                os.chmod(config_path, 0o600)
                calls: list[list[str]] = []

                def forbidden_control(arguments, **_kwargs):
                    calls.append(list(arguments))
                    return subprocess.CompletedProcess(
                        arguments, 0, stdout=b"", stderr=b""
                    )

                with self.assertRaises(LaunchAgentError):
                    start_launch_agent(
                        runtime,
                        authentication_key_file=self.authentication_key,
                        command_runner=forbidden_control,
                    )
                self.assertEqual(calls, [])
                self.assertFalse(
                    (runtime / "launchd-start-request.json").exists()
                )

    def test_authenticated_config_rejects_foreign_cursor_keychain_namespace_before_control(
        self,
    ) -> None:
        for case, service in (
            ("v31", "epiagentbench-cursor-v31"),
            ("foreign", "epiagentbench-cursor-foreign"),
        ):
            runtime = self.root / f"authenticated-{case}-cursor-runtime"
            with self.subTest(case=case, service=service):
                generated = self._generate(
                    runtime_dir=runtime,
                    instance_token=f"authenticated-{case}-cursor",
                )
                config_path = Path(generated["config_path"])
                raw_config = json.loads(
                    config_path.read_text(encoding="utf-8")
                )
                unsigned = launchd_agent._open_payload(
                    launchd_agent._CONFIG_AUTH_DOMAIN,
                    raw_config,
                    b"a" * 32,
                )
                unsigned["cursor_keychain"]["service"] = service
                resealed = launchd_agent._seal_payload(
                    launchd_agent._CONFIG_AUTH_DOMAIN,
                    unsigned,
                    b"a" * 32,
                )
                config_path.write_text(
                    json.dumps(resealed, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                os.chmod(config_path, 0o600)
                calls: list[list[str]] = []

                def forbidden_control(arguments, **_kwargs):
                    calls.append(list(arguments))
                    return subprocess.CompletedProcess(
                        arguments, 0, stdout=b"", stderr=b""
                    )

                self.mock_provider_free_prelaunch.reset_mock()
                with self.assertRaises(LaunchAgentError):
                    start_launch_agent(
                        runtime,
                        authentication_key_file=self.authentication_key,
                        command_runner=forbidden_control,
                    )
                self.assertEqual(calls, [])
                self.assertFalse(
                    (runtime / "launchd-start-request.json").exists()
                )
                self.mock_provider_free_prelaunch.assert_not_called()

    def test_authenticated_config_rejects_foreign_cursor_keychain_account_before_control(
        self,
    ) -> None:
        for case, account in (
            ("typo", f"{self.cursor_keychain_account}-typo"),
            ("foreign", "foreign-keychain-account"),
        ):
            runtime = self.root / f"authenticated-{case}-account-runtime"
            with self.subTest(case=case, account=account):
                generated = self._generate(
                    runtime_dir=runtime,
                    instance_token=f"authenticated-{case}-account",
                )
                config_path = Path(generated["config_path"])
                raw_config = json.loads(
                    config_path.read_text(encoding="utf-8")
                )
                unsigned = launchd_agent._open_payload(
                    launchd_agent._CONFIG_AUTH_DOMAIN,
                    raw_config,
                    b"a" * 32,
                )
                unsigned["cursor_keychain"]["account"] = account
                resealed = launchd_agent._seal_payload(
                    launchd_agent._CONFIG_AUTH_DOMAIN,
                    unsigned,
                    b"a" * 32,
                )
                config_path.write_text(
                    json.dumps(resealed, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                os.chmod(config_path, 0o600)
                calls: list[list[str]] = []

                def forbidden_control(arguments, **_kwargs):
                    calls.append(list(arguments))
                    return subprocess.CompletedProcess(
                        arguments, 0, stdout=b"", stderr=b""
                    )

                self.mock_provider_free_prelaunch.reset_mock()
                with self.assertRaises(LaunchAgentError):
                    start_launch_agent(
                        runtime,
                        authentication_key_file=self.authentication_key,
                        command_runner=forbidden_control,
                    )
                self.assertEqual(calls, [])
                self.assertFalse(
                    (runtime / "launchd-start-request.json").exists()
                )
                self.mock_provider_free_prelaunch.assert_not_called()

    def test_v32_rejects_predecessor_protocol_before_control_action(
        self,
    ) -> None:
        generated = self._generate()
        config_path = Path(generated["config_path"])
        raw_config = json.loads(config_path.read_text(encoding="utf-8"))
        unsigned = launchd_agent._open_payload(
            launchd_agent._CONFIG_AUTH_DOMAIN,
            raw_config,
            b"a" * 32,
        )
        unsigned["protocol_version"] = "persistent-supervisor-v8"
        resealed = launchd_agent._seal_payload(
            launchd_agent._CONFIG_AUTH_DOMAIN,
            unsigned,
            b"a" * 32,
        )
        config_path.write_text(json.dumps(resealed), encoding="utf-8")
        os.chmod(config_path, 0o600)
        calls: list[list[str]] = []

        def forbidden_control(arguments, **_kwargs):
            calls.append(list(arguments))
            return subprocess.CompletedProcess(
                arguments, 0, stdout=b"", stderr=b""
            )

        with self.assertRaises(LaunchAgentError):
            start_launch_agent(
                self.runtime,
                authentication_key_file=self.authentication_key,
                command_runner=forbidden_control,
            )
        self.assertEqual(calls, [])
        self.assertFalse(
            (self.runtime / "launchd-start-request.json").exists()
        )

    def test_v32_rejects_predecessor_auth_domain_before_control_action(
        self,
    ) -> None:
        generated = self._generate()
        config_path = Path(generated["config_path"])
        raw_config = json.loads(config_path.read_text(encoding="utf-8"))
        unsigned = launchd_agent._open_payload(
            launchd_agent._CONFIG_AUTH_DOMAIN,
            raw_config,
            b"a" * 32,
        )
        resealed = launchd_agent._seal_payload(
            b"epiagentbench:launchd-config:v15\x00",
            unsigned,
            b"a" * 32,
        )
        config_path.write_text(json.dumps(resealed), encoding="utf-8")
        os.chmod(config_path, 0o600)
        calls: list[list[str]] = []

        def forbidden_control(arguments, **_kwargs):
            calls.append(list(arguments))
            return subprocess.CompletedProcess(
                arguments, 0, stdout=b"", stderr=b""
            )

        with self.assertRaises(LaunchAgentError):
            start_launch_agent(
                self.runtime,
                authentication_key_file=self.authentication_key,
                command_runner=forbidden_control,
            )
        self.assertEqual(calls, [])
        self.assertFalse(
            (self.runtime / "launchd-start-request.json").exists()
        )

    def test_v32_rejects_authenticated_open_config_before_control_action(
        self,
    ) -> None:
        generated = self._generate()
        config_path = Path(generated["config_path"])
        raw_config = json.loads(config_path.read_text(encoding="utf-8"))
        unsigned = launchd_agent._open_payload(
            launchd_agent._CONFIG_AUTH_DOMAIN,
            raw_config,
            b"a" * 32,
        )
        unsigned["unexpected_field"] = "not-allowed"
        resealed = launchd_agent._seal_payload(
            launchd_agent._CONFIG_AUTH_DOMAIN,
            unsigned,
            b"a" * 32,
        )
        config_path.write_text(json.dumps(resealed), encoding="utf-8")
        os.chmod(config_path, 0o600)
        calls: list[list[str]] = []

        def forbidden_control(arguments, **_kwargs):
            calls.append(list(arguments))
            return subprocess.CompletedProcess(
                arguments, 0, stdout=b"", stderr=b""
            )

        with self.assertRaises(LaunchAgentError):
            start_launch_agent(
                self.runtime,
                authentication_key_file=self.authentication_key,
                command_runner=forbidden_control,
            )
        self.assertEqual(calls, [])
        self.assertFalse(
            (self.runtime / "launchd-start-request.json").exists()
        )

    def test_v26_rejects_predecessor_bound_runtime_schema(self) -> None:
        cache_root, _ = self._enable_v18_runtime_binding()
        manifest = json.loads(
            self.public_manifest.read_text(encoding="utf-8")
        )
        manifest["preparation_runtime_contract"]["schema_version"] = (
            "epiagentbench.bound_preparation_runtime.v2"
        )
        self.public_manifest.write_text(
            json.dumps(manifest),
            encoding="utf-8",
        )
        with self.assertRaises(LaunchAgentError):
            self._generate(runtime_cache_dir=cache_root)
        self.assertFalse(self.runtime.exists())

    def test_v18_generation_rejects_manifest_python_binding_hash_drift(
        self,
    ) -> None:
        cache_root, _ = self._enable_v18_runtime_binding()
        manifest = json.loads(
            self.public_manifest.read_text(encoding="utf-8")
        )
        self.assertNotIn(
            "python_executable_binding", manifest["runtime_contract"]
        )
        self.assertNotIn(
            "runtime_cache_contract",
            manifest["preparation_runtime_contract"],
        )
        manifest["runtime_contract"][
            "python_executable_binding_sha256"
        ] = "sha256:" + "f" * 64
        self.public_manifest.write_text(
            json.dumps(manifest),
            encoding="utf-8",
        )

        with self.assertRaises(LaunchAgentError):
            self._generate(
                runtime_cache_dir=cache_root,
            )
        self.assertFalse(self.runtime.exists())

    def test_preflight_and_production_share_one_fixed_worker_boundary(self) -> None:
        production = self._generate(operation="production")
        production_plist = plistlib.loads(
            Path(production["plist_path"]).read_bytes()
        )
        production_argv = production_plist["ProgramArguments"]
        production_config = json.loads(
            Path(production["config_path"]).read_text(encoding="utf-8")
        )

        second_runtime = self.root / "preflight-runtime"
        preflight = self._generate(
            runtime_dir=second_runtime,
            operation="preflight",
            public_preflight_path=self.public_preflight,
            public_results_path=None,
            instance_token="2" * 24,
        )
        preflight_plist = plistlib.loads(Path(preflight["plist_path"]).read_bytes())
        preflight_argv = preflight_plist["ProgramArguments"]
        preflight_config = json.loads(
            Path(preflight["config_path"]).read_text(encoding="utf-8")
        )

        # The operation is private config, not a second entry point or a
        # caller-controlled provider argv.  Normalizing only the config path
        # leaves the exact same supervisor command.
        self.assertEqual(production_argv[:-1], preflight_argv[:-1])
        self.assertEqual(production_config["operation"], "production")
        self.assertEqual(preflight_config["operation"], "preflight")
        for invalid in ("run", "provider", "production --extra", ""):
            with self.subTest(operation=invalid):
                with self.assertRaises(LaunchAgentError):
                    self._generate(
                        runtime_dir=self.root / f"invalid-{len(invalid)}",
                        operation=invalid,
                        instance_token=f"{len(invalid):024x}",
                    )
        with self.assertRaises(LaunchAgentError):
            self._generate(
                runtime_dir=self.root / "arbitrary-argv",
                instance_token="3" * 24,
                runner_argv=("cursor-agent", "--prompt", "attacker-controlled"),
            )

    def test_inspection_is_an_allowlisted_secret_free_summary(self) -> None:
        generated = self._generate()
        summary = inspect_launch_agent(
            self.runtime,
            authentication_key_file=self.authentication_key,
        )
        self.assertEqual(
            set(summary),
            {
                "configured",
                "label",
                "config_mode",
                "plist_mode",
                "runtime_mode",
            },
        )
        self.assertIs(summary["configured"], True)
        self.assertEqual(summary["label"], generated["label"])
        encoded = json.dumps(summary, sort_keys=True)
        for value in (
            str(self.root),
            "authentication.key",
            "claude-storage",
            "codex-storage",
            "epiagentbench-cursor-v32",
            self.cursor_keychain_account,
            *_SECRET_CANARIES,
        ):
            self.assertNotIn(value, encoded)

    def test_v32_audit_authenticates_provider_free_unstarted_boundary(
        self,
    ) -> None:
        generated = self._generate()
        calls: list[list[str]] = []

        def dormant_launchctl(arguments, **_kwargs):
            calls.append(list(arguments))
            return subprocess.CompletedProcess(
                arguments,
                0,
                stdout=b"state = waiting\n",
                stderr=b"",
            )

        audited = audit_launch_agent(
            self.runtime,
            authentication_key_file=self.authentication_key,
            command_runner=dormant_launchctl,
        )

        self.assertEqual(
            audited,
            {
                "state": "audited",
                "label": generated["label"],
                "operation": "production",
                "panel_id": development_matched_panel.PANEL_ID,
                "artifact_integrity": "authenticated",
                "prelaunch_identity": "attested",
                "launchd_state": "waiting",
                "one_shot_state": "unstarted",
            },
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0:2], ["/bin/launchctl", "print"])
        self.assertIn(generated["label"], calls[0][2])
        self.assertFalse(
            (self.runtime / "launchd-start-request.json").exists()
        )
        self.assertFalse(
            (self.runtime / "launchd-control.lock").exists()
        )
        self.mock_durable_readiness.assert_called()
        self.mock_environment_preflight_readiness.assert_called()
        self.mock_provider_free_prelaunch.assert_called()
        self.assertEqual(
            self.mock_public_authentication_receipt_readiness.call_count,
            2,
        )
        for observed in (
            self.mock_public_authentication_receipt_readiness.call_args_list
        ):
            self.assertEqual(
                observed.kwargs,
                {
                    "public_manifest_path": self.public_manifest,
                    "public_authentication_path": (
                        self.public_authentication
                    ),
                },
            )
        self.mock_authentication_readiness.assert_not_called()

    def test_v32_audit_rechecks_authentication_receipt_after_launchd_print(
        self,
    ) -> None:
        self._generate()
        self.mock_public_authentication_receipt_readiness.side_effect = (
            {
                "panel_id": development_matched_panel.PANEL_ID,
                "status": "passed",
                "model_calls_started": 0,
            },
            RuntimeError("authentication receipt replaced after print"),
        )
        calls: list[list[str]] = []

        def dormant_launchctl(arguments, **_kwargs):
            calls.append(list(arguments))
            return subprocess.CompletedProcess(
                arguments,
                0,
                stdout=b"state = waiting\n",
                stderr=b"",
            )

        with self.assertRaises(LaunchAgentError):
            audit_launch_agent(
                self.runtime,
                authentication_key_file=self.authentication_key,
                command_runner=dormant_launchctl,
            )

        self.assertEqual(len(calls), 1)
        self.assertEqual(
            self.mock_public_authentication_receipt_readiness.call_count,
            2,
        )
        self.assertFalse(
            (self.runtime / "launchd-start-request.json").exists()
        )
        self.assertFalse(
            (self.runtime / launchd_agent._START_ATTEMPT_NAME).exists()
        )
        self.mock_authentication_readiness.assert_not_called()

    def test_v32_audit_failure_precedes_launch_control_and_marker(
        self,
    ) -> None:
        self._generate()
        self.mock_provider_free_prelaunch.side_effect = RuntimeError(
            "offline prelaunch identity refusal"
        )
        calls: list[list[str]] = []

        def forbidden_launchctl(arguments, **_kwargs):
            calls.append(list(arguments))
            return subprocess.CompletedProcess(
                arguments,
                0,
                stdout=b"state = waiting\n",
                stderr=b"",
            )

        with self.assertRaises(LaunchAgentError):
            audit_launch_agent(
                self.runtime,
                authentication_key_file=self.authentication_key,
                command_runner=forbidden_launchctl,
            )

        self.assertEqual(calls, [])
        self.assertFalse(
            (self.runtime / "launchd-start-request.json").exists()
        )
        self.assertFalse(
            (self.runtime / "launchd-control.lock").exists()
        )
        self.mock_authentication_readiness.assert_not_called()

    def test_v32_audit_cli_dispatches_safe_coarse_payload(self) -> None:
        script = (
            self.repository
            / "examples"
            / "run_persistent_panel_supervisor.py"
        )
        spec = importlib.util.spec_from_file_location(
            "_test_persistent_panel_supervisor_cli",
            script,
        )
        self.assertIsNotNone(spec)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        expected = {
            "state": "audited",
            "artifact_integrity": "authenticated",
            "prelaunch_identity": "attested",
            "launchd_state": "not_running",
            "one_shot_state": "unstarted",
        }
        output = io.StringIO()
        with (
            patch.object(
                module,
                "audit_launch_agent",
                return_value=expected,
            ) as audit,
            redirect_stdout(output),
        ):
            return_code = module.main(
                [
                    "audit",
                    "--runtime-dir",
                    str(self.runtime),
                    "--authentication-key",
                    str(self.authentication_key),
                ]
            )

        self.assertEqual(return_code, 0)
        audit.assert_called_once_with(
            self.runtime,
            authentication_key_file=self.authentication_key,
        )
        self.assertEqual(json.loads(output.getvalue()), expected)

    def test_v32_generate_cli_emits_typed_environment_refusal(self) -> None:
        script = (
            self.repository
            / "examples"
            / "run_persistent_panel_supervisor.py"
        )
        spec = importlib.util.spec_from_file_location(
            "_test_persistent_panel_supervisor_generate_cli",
            script,
        )
        self.assertIsNotNone(spec)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        output = io.StringIO()
        with (
            patch.object(
                module,
                "generate_launch_agent",
                side_effect=GenerationValidationError(
                    GenerationFailureCode.ENVIRONMENT_INVALID
                ),
            ) as generate,
            redirect_stdout(output),
        ):
            return_code = module.main(
                [
                    "generate",
                    "--operation",
                    "production",
                    "--runtime-dir",
                    str(self.runtime),
                    "--repository-root",
                    str(self.repository),
                    "--runtime-cache-dir",
                    str(self.root / "runtime-cache"),
                    "--authentication-key",
                    str(self.authentication_key),
                    "--claude-secure-storage-dir",
                    str(self.claude_storage),
                    "--codex-secure-storage-dir",
                    str(self.codex_storage),
                    "--private-state",
                    str(self.private_state),
                    "--public-manifest",
                    str(self.public_manifest),
                    "--public-results",
                    str(self.public_results),
                    "--cursor-keychain-service",
                    "epiagentbench-cursor-v32",
                ]
            )

        self.assertEqual(return_code, 2)
        generate.assert_called_once()
        self.assertEqual(
            json.loads(output.getvalue()),
            {
                "status": "refused",
                "reason": "launch_agent_error",
                "failure_code": "generation_environment_invalid",
            },
        )

    def test_generator_rejects_relative_and_symlinked_security_paths(self) -> None:
        with self.assertRaises(LaunchAgentError):
            self._generate(runtime_dir=Path("relative-runtime"))

        target = self.root / "runtime-target"
        target.mkdir(mode=0o700)
        symlink = self.root / "runtime-link"
        symlink.symlink_to(target, target_is_directory=True)
        with self.assertRaises(LaunchAgentError):
            self._generate(runtime_dir=symlink)

        key_target = self.root / "other.key"
        key_target.write_bytes(b"b" * 32)
        os.chmod(key_target, 0o600)
        key_link = self.root / "key-link"
        key_link.symlink_to(key_target)
        with self.assertRaises(LaunchAgentError):
            self._generate(authentication_key_file=key_link)

    def test_generator_rejects_group_readable_key_and_non_directory_storage(self) -> None:
        os.chmod(self.authentication_key, 0o640)
        with self.assertRaises(LaunchAgentError):
            self._generate()
        os.chmod(self.authentication_key, 0o600)

        not_a_directory = self.root / "not-a-directory"
        not_a_directory.write_text("x", encoding="utf-8")
        os.chmod(not_a_directory, 0o600)
        with self.assertRaises(LaunchAgentError):
            self._generate(claude_secure_storage_dir=not_a_directory)

    def test_generator_defers_authentication_readiness_to_claimed_child(
        self,
    ) -> None:
        generated = self._generate()

        self.assertTrue(Path(generated["config_path"]).is_file())
        self.mock_authentication_readiness.assert_not_called()

    def test_authentication_receipt_is_derived_sealed_and_revalidated(
        self,
    ) -> None:
        generated = self._generate()
        config, _ = self._config_and_key()

        self.assertEqual(
            config["public_authentication_path"],
            str(self.public_authentication),
        )
        self.assertEqual(
            config["public_authentication_file_sha256"],
            launchd_agent._file_sha256(
                self.public_authentication,
                maximum_bytes=(
                    launchd_agent._MAX_PUBLIC_AUTHENTICATION_BYTES
                ),
                label="public authentication receipt",
            ),
        )

        self.public_authentication.write_text(
            '{"status":"tampered"}',
            encoding="utf-8",
        )
        os.chmod(self.public_authentication, 0o600)
        with self.assertRaises(LaunchAgentError):
            inspect_launch_agent(
                self.runtime,
                authentication_key_file=self.authentication_key,
            )
        self.assertTrue(Path(generated["config_path"]).exists())

    def test_generator_rejects_missing_derived_authentication_receipt(
        self,
    ) -> None:
        self.public_authentication.unlink()

        with self.assertRaises(LaunchAgentError):
            self._generate()

        self.assertFalse(self.runtime.exists())
        self.mock_authentication_readiness.assert_not_called()

    def test_start_delegates_ownership_without_restart_or_provider_argv(self) -> None:
        generated = self._generate()
        calls: list[list[str]] = []
        launchd_owned = {"worker_active": False}

        def fake_launchctl(arguments, **kwargs):
            calls.append(list(arguments))
            launchd_owned["worker_active"] = True
            return subprocess.CompletedProcess(arguments, 0, stdout=b"", stderr=b"")

        response = start_launch_agent(
            self.runtime,
            authentication_key_file=self.authentication_key,
            command_runner=fake_launchctl,
        )

        # The initiating client has returned, while the fake launch-service
        # abstraction still owns the worker.  There is no child process or
        # provider command tied to the caller's lifetime.
        self.assertEqual(response["state"], "start_requested")
        self.assertIs(launchd_owned["worker_active"], True)
        self.assertEqual(len(calls), 1)
        self.mock_public_authentication_receipt_readiness.assert_called_once_with(
            public_manifest_path=self.public_manifest,
            public_authentication_path=self.public_authentication,
        )
        self.assertEqual(calls[0][0:2], ["/bin/launchctl", "kickstart"])
        self.assertNotIn("-k", calls[0])
        encoded = "\0".join(calls[0])
        self.assertIn(generated["label"], encoded)
        for forbidden in (
            "CURSOR_API_KEY",
            "security",
            str(self.authentication_key),
            str(self.private_state),
            "claude",
            "codex",
            "cursor-agent",
            *_SECRET_CANARIES,
        ):
            self.assertNotIn(forbidden, encoded)
        with self.assertRaises(LaunchAgentError):
            start_launch_agent(
                self.runtime,
                authentication_key_file=self.authentication_key,
                command_runner=fake_launchctl,
            )
        self.assertEqual(len(calls), 1)

    def test_start_rejects_authentication_receipt_semantics_before_commit(
        self,
    ) -> None:
        self._generate()
        self.mock_public_authentication_receipt_readiness.side_effect = (
            RuntimeError("authentication receipt semantics changed")
        )
        calls: list[list[str]] = []

        def forbidden_launchctl(arguments, **_kwargs):
            calls.append(list(arguments))
            return subprocess.CompletedProcess(
                arguments,
                0,
                stdout=b"",
                stderr=b"",
            )

        with self.assertRaises(LaunchAgentError):
            start_launch_agent(
                self.runtime,
                authentication_key_file=self.authentication_key,
                command_runner=forbidden_launchctl,
            )

        self.assertEqual(calls, [])
        self.assertFalse(
            (self.runtime / "launchd-start-request.json").exists()
        )
        self.assertTrue(
            (self.runtime / launchd_agent._START_ATTEMPT_NAME).is_file()
        )
        self.mock_public_authentication_receipt_readiness.assert_called_once_with(
            public_manifest_path=self.public_manifest,
            public_authentication_path=self.public_authentication,
        )
        self.mock_authentication_readiness.assert_not_called()

    def test_start_attempt_is_durable_before_authenticated_runtime_loading(
        self,
    ) -> None:
        self._generate()
        attempt = self.runtime / launchd_agent._START_ATTEMPT_NAME
        fsync_kinds: list[str] = []
        real_fsync = os.fsync

        def recording_fsync(descriptor: int) -> None:
            mode = os.fstat(descriptor).st_mode
            if stat.S_ISREG(mode):
                fsync_kinds.append("file")
            elif stat.S_ISDIR(mode):
                fsync_kinds.append("directory")
            else:
                fsync_kinds.append("other")
            real_fsync(descriptor)

        def refuse_authenticated_load(*_args, **_kwargs):
            self.assertTrue(attempt.is_file())
            self.assertEqual(
                attempt.read_bytes(),
                launchd_agent._CONTROL_ATTEMPT_PAYLOAD,
            )
            self.assertEqual(attempt.stat().st_mode & 0o777, 0o600)
            self.assertEqual(fsync_kinds, ["file", "directory"])
            raise RuntimeError("synthetic authenticated-load refusal")

        with patch.object(
            os,
            "fsync",
            side_effect=recording_fsync,
        ), patch.object(
            launchd_agent,
            "_read_authenticated_config",
            side_effect=refuse_authenticated_load,
        ) as authenticated_load:
            with self.assertRaises(LaunchAgentError):
                start_launch_agent(
                    self.runtime,
                    authentication_key_file=self.authentication_key,
                    command_runner=lambda *_args, **_kwargs: self.fail(
                        "start validation refusal must precede launchctl"
                    ),
                )

        authenticated_load.assert_called_once()
        self.assertTrue(attempt.is_file())
        with patch.object(
            launchd_agent,
            "_read_authenticated_config",
            side_effect=AssertionError(
                "a repeated start must fail before authenticated loading"
            ),
        ) as repeated_load:
            with self.assertRaises(LaunchAgentError):
                start_launch_agent(
                    self.runtime,
                    authentication_key_file=self.authentication_key,
                )
        repeated_load.assert_not_called()

    def test_delayed_concurrent_start_cannot_cross_exclusive_attempt(self) -> None:
        self._generate()
        entered_launchctl = threading.Event()
        release_launchctl = threading.Event()
        outcomes: list[object] = []

        def delayed_launchctl(arguments, **_kwargs):
            entered_launchctl.set()
            if not release_launchctl.wait(timeout=10):
                raise AssertionError("timed out waiting to release launchctl")
            return subprocess.CompletedProcess(
                arguments, 0, stdout=b"", stderr=b""
            )

        def first_start() -> None:
            try:
                outcomes.append(
                    start_launch_agent(
                        self.runtime,
                        authentication_key_file=self.authentication_key,
                        command_runner=delayed_launchctl,
                    )
                )
            except BaseException as error:  # captured for the parent thread
                outcomes.append(error)

        thread = threading.Thread(target=first_start, daemon=True)
        thread.start()
        self.assertTrue(entered_launchctl.wait(timeout=10))
        try:
            with self.assertRaises(LaunchAgentError):
                start_launch_agent(
                    self.runtime,
                    authentication_key_file=self.authentication_key,
                    command_runner=lambda *_args, **_kwargs: self.fail(
                        "a delayed second start reached launchctl"
                    ),
                )
        finally:
            release_launchctl.set()
            thread.join(timeout=10)

        self.assertFalse(thread.is_alive())
        self.assertEqual(len(outcomes), 1)
        self.assertIsInstance(outcomes[0], dict)
        self.assertEqual(outcomes[0]["state"], "start_requested")

    def test_install_attempt_follows_validation_and_is_durable_before_bootstrap(
        self,
    ) -> None:
        self._generate()
        attempt = self.runtime / launchd_agent._INSTALL_ATTEMPT_NAME
        fsync_kinds: list[str] = []
        calls: list[list[str]] = []
        real_fsync = os.fsync

        def recording_fsync(descriptor: int) -> None:
            mode = os.fstat(descriptor).st_mode
            if stat.S_ISREG(mode):
                fsync_kinds.append("file")
            elif stat.S_ISDIR(mode):
                fsync_kinds.append("directory")
            else:
                fsync_kinds.append("other")
            real_fsync(descriptor)

        def failed_bootstrap(arguments, **_kwargs):
            calls.append(list(arguments))
            self.assertTrue(attempt.is_file())
            self.assertEqual(
                attempt.read_bytes(),
                launchd_agent._CONTROL_ATTEMPT_PAYLOAD,
            )
            self.assertEqual(attempt.stat().st_mode & 0o777, 0o600)
            self.assertEqual(fsync_kinds, ["file", "directory"])
            return subprocess.CompletedProcess(
                arguments, 64, stdout=b"", stderr=b""
            )

        with patch.object(
            os,
            "fsync",
            side_effect=recording_fsync,
        ):
            with self.assertRaises(LaunchAgentError):
                install_launch_agent(
                    self.runtime,
                    authentication_key_file=self.authentication_key,
                    command_runner=failed_bootstrap,
                )

        self.assertTrue(attempt.is_file())
        with self.assertRaises(LaunchAgentError):
            install_launch_agent(
                self.runtime,
                authentication_key_file=self.authentication_key,
                command_runner=lambda arguments, **_kwargs: calls.append(
                    list(arguments)
                ),
            )
        self.assertEqual(len(calls), 1)

    def test_install_validation_failure_does_not_publish_attempt(self) -> None:
        self._generate()
        wrong_key = self.root / "wrong-authentication.key"
        wrong_key.write_bytes(b"b" * 32)
        os.chmod(wrong_key, 0o600)
        calls: list[list[str]] = []

        with self.assertRaises(LaunchAgentError):
            install_launch_agent(
                self.runtime,
                authentication_key_file=wrong_key,
                command_runner=lambda arguments, **_kwargs: calls.append(
                    list(arguments)
                ),
            )

        self.assertFalse(
            (self.runtime / launchd_agent._INSTALL_ATTEMPT_NAME).exists()
        )
        self.assertFalse(
            (self.runtime / launchd_agent._CONTROL_LOCK_NAME).exists()
        )
        self.assertEqual(calls, [])

    def test_ambiguous_install_attempt_cannot_be_retried(self) -> None:
        self._generate()
        calls: list[list[str]] = []

        def ambiguous_bootstrap(arguments, **_kwargs):
            calls.append(list(arguments))
            raise subprocess.TimeoutExpired(arguments, 15)

        with self.assertRaises(LaunchAgentError):
            install_launch_agent(
                self.runtime,
                authentication_key_file=self.authentication_key,
                command_runner=ambiguous_bootstrap,
            )
        self.assertTrue(
            (self.runtime / launchd_agent._INSTALL_ATTEMPT_NAME).is_file()
        )

        with self.assertRaises(LaunchAgentError):
            install_launch_agent(
                self.runtime,
                authentication_key_file=self.authentication_key,
                command_runner=lambda arguments, **_kwargs: calls.append(
                    list(arguments)
                ),
            )
        self.assertEqual(len(calls), 1)

    def test_start_defers_authentication_readiness_to_claimed_child(
        self,
    ) -> None:
        self._generate()
        calls: list[list[str]] = []

        def launchctl_only(arguments, **kwargs):
            calls.append(list(arguments))
            return subprocess.CompletedProcess(
                arguments, 0, stdout=b"", stderr=b""
            )

        response = start_launch_agent(
            self.runtime,
            authentication_key_file=self.authentication_key,
            command_runner=launchctl_only,
        )

        self.assertEqual(response["state"], "start_requested")
        self.assertTrue(
            (self.runtime / "launchd-start-request.json").exists()
        )
        self.assertEqual(len(calls), 1)
        self.mock_durable_readiness.assert_called_once_with(
            root=self.repository,
            private_state_path=self.private_state,
        )
        self.mock_authentication_readiness.assert_not_called()

    def test_start_rechecks_preflight_before_keychain_and_start_marker(
        self,
    ) -> None:
        self._generate()
        self.mock_environment_preflight_readiness.side_effect = RuntimeError(
            "preflight receipt binding changed"
        )
        calls: list[list[str]] = []

        def should_not_run(arguments, **kwargs):
            calls.append(list(arguments))
            return subprocess.CompletedProcess(
                arguments, 0, stdout=b"", stderr=b""
            )

        with self.assertRaises(LaunchAgentError):
            start_launch_agent(
                self.runtime,
                authentication_key_file=self.authentication_key,
                command_runner=should_not_run,
            )

        self.assertFalse(
            (self.runtime / "launchd-start-request.json").exists()
        )
        self.assertTrue(
            (self.runtime / "launchd-control.lock").is_file()
        )
        self.assertEqual(calls, [])
        self.mock_environment_preflight_readiness.assert_called_once_with(
            root=self.repository,
            authentication_key_file=self.authentication_key,
            private_state_path=self.private_state,
            public_manifest_path=self.public_manifest,
        )
        self.mock_provider_free_prelaunch.assert_not_called()

    def test_start_rechecks_prelaunch_before_keychain_and_start_marker(
        self,
    ) -> None:
        self._generate()
        self.mock_provider_free_prelaunch.side_effect = RuntimeError(
            "runtime source binding changed"
        )
        calls: list[list[str]] = []

        def should_not_run(arguments, **kwargs):
            calls.append(list(arguments))
            return subprocess.CompletedProcess(
                arguments, 0, stdout=b"", stderr=b""
            )

        with self.assertRaises(LaunchAgentError):
            start_launch_agent(
                self.runtime,
                authentication_key_file=self.authentication_key,
                command_runner=should_not_run,
            )

        self.assertFalse(
            (self.runtime / "launchd-start-request.json").exists()
        )
        self.assertTrue(
            (self.runtime / "launchd-control.lock").is_file()
        )
        self.assertEqual(calls, [])
        self.mock_environment_preflight_readiness.assert_called_once_with(
            root=self.repository,
            authentication_key_file=self.authentication_key,
            private_state_path=self.private_state,
            public_manifest_path=self.public_manifest,
        )
        self.mock_provider_free_prelaunch.assert_called_once_with(
            root=self.repository,
            operation="production",
            public_manifest_path=self.public_manifest,
        )
        self.mock_provider_free_prelaunch.reset_mock()
        self.mock_provider_free_prelaunch.side_effect = None
        with self.assertRaises(LaunchAgentError):
            start_launch_agent(
                self.runtime,
                authentication_key_file=self.authentication_key,
                command_runner=should_not_run,
            )
        self.mock_provider_free_prelaunch.assert_not_called()
        self.assertEqual(calls, [])

    def test_v32_rejects_predecessor_and_foreign_identity_before_generation(
        self,
    ) -> None:
        baseline = json.loads(
            self.public_manifest.read_text(encoding="utf-8")
        )
        cases = (
            (
                "v31-schema",
                development_matched_panel.PANEL_ID,
                "development_matched_panel_v31",
            ),
            (
                "v31-panel",
                "development-matched-50x6-v31",
                development_matched_panel.SCHEMA_VERSION,
            ),
            (
                "foreign-identity",
                "development-matched-50x6-foreign",
                "development_matched_panel_foreign",
            ),
        )
        for case, panel_id, schema_version in cases:
            with self.subTest(case=case):
                manifest = dict(baseline)
                manifest["panel_id"] = panel_id
                manifest["schema_version"] = schema_version
                self.public_manifest.write_text(
                    json.dumps(manifest), encoding="utf-8"
                )
                runtime = self.root / f"{case}-runtime"
                with patch.object(
                    launchd_agent,
                    "_read_authentication_key",
                    side_effect=AssertionError(
                        "identity rejection must precede key access"
                    ),
                ) as authentication_read:
                    with self.assertRaises(LaunchAgentError):
                        self._generate(
                            runtime_dir=runtime,
                            instance_token=case,
                        )

                authentication_read.assert_not_called()
                self.assertFalse(runtime.exists())

    def test_install_rejects_resealed_predecessor_manifest_before_bootstrap(
        self,
    ) -> None:
        generated = self._generate()
        manifest = json.loads(
            self.public_manifest.read_text(encoding="utf-8")
        )
        manifest["panel_id"] = "development-matched-50x6-v31"
        manifest["schema_version"] = "development_matched_panel_v31"
        self.public_manifest.write_text(
            json.dumps(manifest), encoding="utf-8"
        )

        config_path = Path(generated["config_path"])
        record = json.loads(config_path.read_text(encoding="utf-8"))
        unsigned = launchd_agent._open_payload(
            launchd_agent._CONFIG_AUTH_DOMAIN,
            record,
            b"a" * 32,
        )
        unsigned["public_manifest_file_sha256"] = (
            "sha256:"
            + hashlib.sha256(self.public_manifest.read_bytes()).hexdigest()
        )
        resealed = launchd_agent._seal_payload(
            launchd_agent._CONFIG_AUTH_DOMAIN,
            unsigned,
            b"a" * 32,
        )
        config_path.write_text(json.dumps(resealed), encoding="utf-8")
        os.chmod(config_path, 0o600)
        calls: list[list[str]] = []

        with self.assertRaises(LaunchAgentError):
            install_launch_agent(
                self.runtime,
                authentication_key_file=self.authentication_key,
                command_runner=lambda arguments, **_kwargs: calls.append(
                    list(arguments)
                ),
            )

        self.assertEqual(calls, [])
        self.assertFalse(
            (self.runtime / launchd_agent._INSTALL_ATTEMPT_NAME).exists()
        )

    def test_start_never_accesses_cursor_keychain_before_marker(
        self,
    ) -> None:
        self._generate()
        calls: list[list[str]] = []

        def launchctl_only(arguments, **kwargs):
            calls.append(list(arguments))
            return subprocess.CompletedProcess(
                arguments, 0, stdout=b"", stderr=b""
            )

        start_launch_agent(
            self.runtime,
            authentication_key_file=self.authentication_key,
            command_runner=launchctl_only,
        )

        self.assertTrue(
            (self.runtime / "launchd-start-request.json").exists()
        )
        self.assertTrue(calls)
        self.assertFalse(
            any("security" in argument for call in calls for argument in call)
        )

    def test_runner_receives_only_cursor_keychain_locator(self) -> None:
        self._generate()
        config, _ = self._config_and_key()
        command = launchd_agent._runner_command(config)
        self.assertIn("--cursor-keychain-service", command)
        self.assertIn("epiagentbench-cursor-v32", command)
        self.assertIn("--cursor-keychain-account", command)
        self.assertIn(self.cursor_keychain_account, command)
        self.assertNotIn("CURSOR_API_KEY", " ".join(command))

    def test_worker_child_exit_is_finite_and_never_persists_keychain_value(self) -> None:
        generated = self._generate()
        self._commit_start()
        config_path = Path(generated["config_path"])
        observed: dict[str, str] = {}

        def fake_child(config, *, child_environment, authentication_key):
            observed["cursor_absent"] = str(
                "CURSOR_API_KEY" not in child_environment
            )
            observed["authentication_key"] = authentication_key.decode("ascii")
            return 19

        with patch(
            "epiagentbench.launchd_agent._run_core_supervisor",
            side_effect=fake_child,
        ):
            return_code = run_launch_agent_worker(config_path)

        self.assertEqual(return_code, 19)
        self.assertEqual(observed["cursor_absent"], "True")
        self.assertEqual(observed["authentication_key"], "a" * 32)
        status_path = self.runtime / "launchd-worker-status.json"
        self.assertEqual(status_path.stat().st_mode & 0o777, 0o600)
        status = json.loads(status_path.read_text(encoding="utf-8"))
        self.assertEqual(status["state"], "supervisor_exited")
        self.assertEqual(status["reason"], "failure")
        persisted = b"".join(path.read_bytes() for path in self.runtime.iterdir())
        for canary in _SECRET_CANARIES:
            self.assertNotIn(canary.encode(), persisted)

    def test_worker_preserves_typed_core_failure_without_exception_text(
        self,
    ) -> None:
        generated = self._generate()
        self._commit_start()
        config_path = Path(generated["config_path"])

        failure = persistent_supervisor.RunnerFailedError(
            persistent_supervisor.FailureCode.RUNNER_EXIT
        )
        failure.args = (_SECRET_CANARIES[2],)
        with patch(
            "epiagentbench.launchd_agent._run_core_supervisor",
            side_effect=failure,
        ):
            return_code = run_launch_agent_worker(config_path)

        self.assertEqual(return_code, 70)
        config, key = self._config_and_key()
        status = launchd_agent._worker_status(
            self.runtime,
            config=config,
            authentication_key=key,
        )
        self.assertIsNotNone(status)
        self.assertEqual(status["state"], "terminal_incident")
        self.assertEqual(status["reason"], "supervisor_failed")
        self.assertEqual(
            status["supervisor_failure_code"],
            "runner_nonzero_exit",
        )
        public = launch_agent_status(
            self.runtime,
            authentication_key_file=self.authentication_key,
            command_runner=self._not_loaded_launchctl,
        )
        self.assertEqual(
            public["supervisor_failure_code"],
            "runner_nonzero_exit",
        )
        persisted = b"".join(
            path.read_bytes() for path in self.runtime.iterdir()
        )
        self.assertNotIn(_SECRET_CANARIES[2].encode(), persisted)

    def test_supervisor_failure_status_requires_exact_finite_code_pairing(
        self,
    ) -> None:
        self._generate()
        config, key = self._config_and_key()
        with self.assertRaises(ValueError):
            launchd_agent._atomic_worker_status(
                self.runtime,
                config=config,
                authentication_key=key,
                state="terminal_incident",
                reason="supervisor_failed",
            )
        with self.assertRaises(ValueError):
            launchd_agent._atomic_worker_status(
                self.runtime,
                config=config,
                authentication_key=key,
                state="starting",
                supervisor_failure_code=(
                    launchd_agent.SupervisorFailureCode.RUNNER_EXIT
                ),
            )

        payload = {
            "schema_version": launchd_agent._WORKER_STATUS_SCHEMA,
            "label": config["label"],
            "operation": config["operation"],
            "panel_id": config["panel_id"],
            "precommitment_sha256": config["precommitment_sha256"],
            "execution_context_sha256": config[
                "execution_context_sha256"
            ],
            "state": "terminal_incident",
            "reason": "supervisor_failed",
            "supervisor_failure_code": "provider-output-and-secret",
        }
        record = launchd_agent._seal_payload(
            launchd_agent._WORKER_STATUS_AUTH_DOMAIN,
            payload,
            key,
        )
        status_path = self.runtime / "launchd-worker-status.json"
        status_path.write_bytes(
            launchd_agent._canonical_bytes(record) + b"\n"
        )
        os.chmod(status_path, 0o600)
        with self.assertRaises(ValueError):
            launchd_agent._worker_status(
                self.runtime,
                config=config,
                authentication_key=key,
            )

    def test_core_supervisor_exception_classes_map_to_finite_codes(
        self,
    ) -> None:
        audit_runner_code = (
            persistent_supervisor.FailureCode
            .RUNNER_RESERVED_TERMINAL_AUDIT_EXIT
        )
        audit_worker_code = (
            launchd_agent.SupervisorFailureCode
            .RUNNER_RESERVED_TERMINAL_AUDIT_EXIT
        )
        cases = (
            (
                persistent_supervisor.RunnerFailedError(
                    persistent_supervisor.FailureCode.RUNNER_PROTOCOL
                ),
                launchd_agent.SupervisorFailureCode.RUNNER_PROTOCOL,
            ),
            (
                persistent_supervisor.RunnerFailedError(
                    audit_runner_code
                ),
                audit_worker_code,
            ),
            (
                persistent_supervisor.IntegrityError(
                    _SECRET_CANARIES[2]
                ),
                launchd_agent.SupervisorFailureCode.INTEGRITY,
            ),
            (
                persistent_supervisor.UnsafeRecoveryError(
                    _SECRET_CANARIES[2]
                ),
                launchd_agent.SupervisorFailureCode.UNSAFE_RECOVERY,
            ),
            (
                persistent_supervisor.SupervisorBusyError(
                    _SECRET_CANARIES[2]
                ),
                launchd_agent.SupervisorFailureCode.SUPERVISOR_BUSY,
            ),
            (
                persistent_supervisor.ProcessIdentityUnavailableError(
                    _SECRET_CANARIES[2]
                ),
                launchd_agent.SupervisorFailureCode.SUPERVISOR_INTERNAL,
            ),
        )
        for error, expected in cases:
            with self.subTest(expected=expected):
                self.assertIs(
                    launchd_agent._classify_supervisor_failure(error),
                    expected,
                )
        self.assertIs(
            launchd_agent._classify_supervisor_failure(
                RuntimeError(_SECRET_CANARIES[2])
            ),
            launchd_agent.SupervisorFailureCode.SUPERVISOR_INTERNAL,
        )

    def test_worker_fails_closed_before_child_when_identity_is_unavailable(
        self,
    ) -> None:
        generated = self._generate()
        self._commit_start()
        config_path = Path(generated["config_path"])
        unavailable = persistent_supervisor.ProcessIdentityUnavailableError(
            "Persistent supervisor process identity is unavailable"
        )
        with (
            patch.object(
                persistent_supervisor,
                "current_process_identity",
                side_effect=unavailable,
            ),
            patch.object(
                persistent_supervisor.SubprocessCommandRunner,
                "start",
                side_effect=AssertionError(
                    "identity-unavailable startup reached evaluator child"
                ),
            ) as child_start,
        ):
            return_code = run_launch_agent_worker(config_path)

        self.assertEqual(return_code, 70)
        child_start.assert_not_called()
        for core_name in (
            persistent_supervisor.STATUS_FILE,
            persistent_supervisor.LEASE_FILE,
            persistent_supervisor.EVENT_FILE,
        ):
            self.assertFalse((self.runtime / core_name).exists())
        config, key = self._config_and_key()
        status = launchd_agent._worker_status(
            self.runtime,
            config=config,
            authentication_key=key,
        )
        self.assertEqual(
            status,
            {
                "label": config["label"],
                "operation": config["operation"],
                "panel_id": config["panel_id"],
                "precommitment_sha256": config["precommitment_sha256"],
                "execution_context_sha256": config[
                    "execution_context_sha256"
                ],
                "state": "terminal_incident",
                "reason": "supervisor_failed",
                "supervisor_failure_code": "supervisor_internal",
            },
        )
        with self.assertRaises(LaunchAgentError):
            run_launch_agent_worker(config_path)

    def test_worker_preserves_controlled_terminal_receipt_classification(
        self,
    ) -> None:
        generated = self._generate()
        self._commit_start()
        config_path = Path(generated["config_path"])

        with patch(
            "epiagentbench.launchd_agent._run_core_supervisor",
            return_value=(
                persistent_supervisor.HANDLED_TERMINAL_RECEIPT_EXIT_CODE
            ),
        ), patch(
            "epiagentbench.launchd_agent._attest_handled_terminal_receipt",
            return_value={
                "schema_version": (
                    "epiagentbench.terminal_receipt_attestation.v1"
                ),
                "panel_id": development_matched_panel.PANEL_ID,
                "operation": "production",
                "status": "attested",
                "terminal_status": "stopped_supervisor_incident",
                "terminal_assignments": 1,
                "provider_processes_started": 0,
                "model_calls_started": 0,
            },
        ), patch(
            "epiagentbench.launchd_agent._finalize_launch_agent_validated",
        ) as finalize:
            return_code = run_launch_agent_worker(config_path)

        self.assertEqual(
            return_code,
            persistent_supervisor.HANDLED_TERMINAL_RECEIPT_EXIT_CODE,
        )
        finalize.assert_not_called()
        config, key = self._config_and_key()
        status = launchd_agent._worker_status(
            self.runtime,
            config=config,
            authentication_key=key,
        )
        self.assertIsNotNone(status)
        self.assertEqual(status["state"], "supervisor_exited")
        self.assertEqual(status["reason"], "benchmark_terminal_receipt")

    def test_worker_preserves_authenticated_terminal_audit_required_exit(
        self,
    ) -> None:
        generated = self._generate(
            operation="preflight",
            public_preflight_path=self.public_preflight,
            public_results_path=None,
        )
        config, key = self._commit_start()
        config_path = Path(generated["config_path"])

        class AuditRequiredCommand:
            def poll(self) -> int:
                return persistent_supervisor.TERMINAL_AUDIT_REQUIRED_EXIT_CODE

            def terminate(self) -> None:
                return None

            def kill(self) -> None:
                return None

        class AuditRequiredRunner:
            def start(self) -> AuditRequiredCommand:
                return AuditRequiredCommand()

        with self.assertRaises(
            persistent_supervisor.RunnerFailedError
        ):
            run_supervised_panel(
                runner_argv=("offline-audit-required",),
                environment={},
                runtime_dir=self.runtime,
                authentication_key=key,
                execution_context_sha256=config[
                    "execution_context_sha256"
                ],
                command_runner=AuditRequiredRunner(),
            )

        observed_environment: dict[str, str] = {}

        def fake_core(
            config,
            *,
            child_environment,
            authentication_key,
        ):
            nonlocal observed_environment
            observed_environment = child_environment
            return persistent_supervisor.TERMINAL_AUDIT_REQUIRED_EXIT_CODE

        file_sha256 = "sha256:" + "e" * 64
        audit_result = {
            "schema_version": "epiagentbench.terminal_audit.v3",
            "panel_id": config["panel_id"],
            "operation": "preflight",
            "status": "reconciled_and_attested",
            "terminal_status": "stopped_supervisor_incident",
            "incident_code": "supervisor_boundary_attestation_failed",
            "incident_phase": "provider_returned",
            "attempted_operation": None,
            "completed_operation": None,
            "contract_failure_code": None,
            "model_invocations_conservatively_chargeable": 1,
            "file_sha256": file_sha256,
            "provider_processes_started": 0,
            "authentication_processes_started": 0,
            "model_calls_started": 0,
        }
        terminal_attestation = {
            "schema_version": (
                "epiagentbench.terminal_receipt_attestation.v1"
            ),
            "panel_id": config["panel_id"],
            "operation": "preflight",
            "status": "attested",
            "terminal_status": "stopped_supervisor_incident",
            "file_sha256": file_sha256,
            "provider_processes_started": 0,
            "model_calls_started": 0,
        }

        def audit_after_credential_scrub(**kwargs):
            self.assertNotIn("CURSOR_API_KEY", observed_environment)
            return audit_result

        with patch(
            "epiagentbench.launchd_agent._run_core_supervisor",
            side_effect=fake_core,
        ), patch.object(
            development_matched_panel,
            "audit_terminal_incident",
            side_effect=audit_after_credential_scrub,
        ), patch(
            "epiagentbench.launchd_agent._attest_handled_terminal_receipt",
            return_value=terminal_attestation,
        ) as public_receipt_attestation:
            return_code = run_launch_agent_worker(config_path)

        self.assertEqual(
            return_code,
            persistent_supervisor.HANDLED_TERMINAL_RECEIPT_EXIT_CODE,
        )
        public_receipt_attestation.assert_called_once_with(config)
        status = launchd_agent._worker_status(
            self.runtime,
            config=config,
            authentication_key=key,
        )
        self.assertIsNotNone(status)
        self.assertEqual(status["state"], "supervisor_exited")
        self.assertEqual(status["reason"], "benchmark_terminal_receipt")
        self.assertNotIn("supervisor_failure_code", status)

    def test_terminal_audit_requires_closed_provider_free_attestation(
        self,
    ) -> None:
        self._generate(
            operation="preflight",
            public_preflight_path=self.public_preflight,
            public_results_path=None,
        )
        config, _ = self._config_and_key()
        valid = {
            "schema_version": "epiagentbench.terminal_audit.v3",
            "panel_id": config["panel_id"],
            "operation": "preflight",
            "status": "reconciled_and_attested",
            "terminal_status": "failed",
            "incident_code": "supervisor_boundary_attestation_failed",
            "incident_phase": "provider_returned",
            "attempted_operation": None,
            "completed_operation": None,
            "contract_failure_code": None,
            "model_invocations_conservatively_chargeable": 1,
            "file_sha256": "sha256:" + "e" * 64,
            "provider_processes_started": 0,
            "authentication_processes_started": 0,
            "model_calls_started": 0,
        }
        malformed_cases = {
            "extra_key": {
                **valid,
                "provider_output": _SECRET_CANARIES[2],
            },
            "unknown_incident": {
                **valid,
                "incident_code": "arbitrary_safe_name",
            },
            "provider_incident_with_control_fields": {
                **valid,
                "attempted_operation": "provider_returned",
                "completed_operation": "model_spawn_committed",
            },
            "mismatched_contract_failure": {
                **valid,
                "incident_code": "contract_attestation_failed",
                "incident_phase": "contract_attestation",
                "attempted_operation": "episode_pack_integrity",
                "completed_operation": "cohort_manifest",
                "contract_failure_code": "cohort_balance_failed",
            },
        }
        for label, malformed in malformed_cases.items():
            with self.subTest(label=label), patch.object(
                development_matched_panel,
                "audit_terminal_incident",
                return_value=malformed,
            ) as audit, patch.object(
                launchd_agent,
                "_attest_handled_terminal_receipt",
            ) as terminal_attestation:
                with self.assertRaisesRegex(
                    RuntimeError,
                    "Terminal incident audit is invalid",
                ):
                    launchd_agent._attest_terminal_audit_required_exit(
                        config
                    )
                audit.assert_called_once_with(
                    root=Path(config["repository_root"]),
                    operation="preflight",
                    authentication_key_file=Path(
                        config["authentication_key_file"]
                    ),
                    private_state_path=Path(config["private_state_path"]),
                    public_manifest_path=Path(
                        config["public_manifest_path"]
                    ),
                    public_output_path=Path(config["public_output_path"]),
                )
                terminal_attestation.assert_not_called()

    def test_terminal_audit_finite_catalogs_match_inner_projection(
        self,
    ) -> None:
        self.assertEqual(
            launchd_agent._TERMINAL_AUDIT_INCIDENT_PHASES,
            development_matched_panel._PREFLIGHT_INCIDENT_PHASE_SET,
        )
        self.assertEqual(
            launchd_agent._TERMINAL_AUDIT_CONTRACT_OPERATIONS,
            development_matched_panel._CONTRACT_ATTESTATION_OPERATION_SET,
        )
        self.assertEqual(
            launchd_agent._TERMINAL_AUDIT_CONTROL_OPERATIONS,
            development_matched_panel._PREFLIGHT_CONTROL_OPERATIONS,
        )
        self.assertEqual(
            launchd_agent._TERMINAL_AUDIT_INCIDENT_CODES,
            development_matched_panel._PROVIDER_INCIDENT_CODES,
        )

    def test_worker_rejects_bare_terminal_audit_required_exit(
        self,
    ) -> None:
        generated = self._generate()
        self._commit_start()
        config_path = Path(generated["config_path"])

        with patch(
            "epiagentbench.launchd_agent._run_core_supervisor",
            return_value=persistent_supervisor.TERMINAL_AUDIT_REQUIRED_EXIT_CODE,
        ):
            return_code = run_launch_agent_worker(config_path)

        self.assertEqual(return_code, 70)
        config, key = self._config_and_key()
        status = launchd_agent._worker_status(
            self.runtime,
            config=config,
            authentication_key=key,
        )
        self.assertIsNotNone(status)
        self.assertEqual(status["state"], "terminal_incident")
        self.assertEqual(status["reason"], "supervisor_failed")
        self.assertEqual(
            status["supervisor_failure_code"],
            "supervisor_internal",
        )

    def test_worker_records_finite_code_when_terminal_audit_fails(
        self,
    ) -> None:
        generated = self._generate()
        self._commit_start()
        config_path = Path(generated["config_path"])

        with patch(
            "epiagentbench.launchd_agent._run_core_supervisor",
            return_value=persistent_supervisor.TERMINAL_AUDIT_REQUIRED_EXIT_CODE,
        ), patch(
            "epiagentbench.launchd_agent._attest_terminal_audit_required_core",
        ), patch(
            "epiagentbench.launchd_agent._attest_terminal_audit_required_exit",
            side_effect=RuntimeError(_SECRET_CANARIES[2]),
        ):
            return_code = run_launch_agent_worker(config_path)

        self.assertEqual(return_code, 70)
        config, key = self._config_and_key()
        status = launchd_agent._worker_status(
            self.runtime,
            config=config,
            authentication_key=key,
        )
        self.assertIsNotNone(status)
        self.assertEqual(status["state"], "terminal_incident")
        self.assertEqual(status["reason"], "supervisor_failed")
        self.assertEqual(
            status["supervisor_failure_code"],
            "runner_reserved_terminal_audit_exit",
        )
        persisted = b"".join(
            path.read_bytes() for path in self.runtime.iterdir()
        )
        self.assertNotIn(_SECRET_CANARIES[2].encode(), persisted)

    def test_outer_terminal_attestation_binds_the_generated_config(
        self,
    ) -> None:
        self._generate()
        config, _ = self._config_and_key()
        expected = {
            "schema_version": (
                "epiagentbench.terminal_receipt_attestation.v1"
            ),
            "panel_id": config["panel_id"],
            "operation": config["operation"],
            "status": "attested",
            "terminal_status": "stopped_supervisor_incident",
            "terminal_assignments": 1,
            "provider_processes_started": 0,
            "model_calls_started": 0,
        }
        with patch.object(
            development_matched_panel,
            "assert_terminal_receipt_ready_for_exit",
            return_value=expected,
        ) as attest:
            self.assertEqual(
                launchd_agent._attest_handled_terminal_receipt(config),
                expected,
            )
        attest.assert_called_once_with(
            root=Path(config["repository_root"]),
            operation=config["operation"],
            authentication_key_file=Path(
                config["authentication_key_file"]
            ),
            private_state_path=Path(config["private_state_path"]),
            public_manifest_path=Path(config["public_manifest_path"]),
            public_output_path=Path(config["public_output_path"]),
        )

        with (
            patch.object(
                development_matched_panel,
                "assert_terminal_receipt_ready_for_exit",
                return_value={**expected, "model_calls_started": False},
            ),
            self.assertRaisesRegex(
                RuntimeError, "Outer terminal receipt attestation is invalid"
            ),
        ):
            launchd_agent._attest_handled_terminal_receipt(config)

        for field, value in (
            ("panel_id", "development-matched-50x6-wrong"),
            ("operation", "preflight"),
        ):
            with (
                self.subTest(field=field),
                patch.object(
                    development_matched_panel,
                    "assert_terminal_receipt_ready_for_exit",
                    return_value={**expected, field: value},
                ),
                self.assertRaisesRegex(
                    RuntimeError,
                    "Outer terminal receipt attestation is invalid",
                ),
            ):
                launchd_agent._attest_handled_terminal_receipt(config)

    def test_worker_rejects_bare_reserved_exit_without_outer_receipt(
        self,
    ) -> None:
        generated = self._generate()
        self._commit_start()
        config_path = Path(generated["config_path"])

        with patch(
            "epiagentbench.launchd_agent._run_core_supervisor",
            return_value=(
                persistent_supervisor.HANDLED_TERMINAL_RECEIPT_EXIT_CODE
            ),
        ), patch(
            "epiagentbench.launchd_agent._attest_handled_terminal_receipt",
            side_effect=RuntimeError("offline missing receipt"),
        ):
            return_code = run_launch_agent_worker(config_path)

        self.assertEqual(return_code, 70)
        config, key = self._config_and_key()
        status = launchd_agent._worker_status(
            self.runtime,
            config=config,
            authentication_key=key,
        )
        self.assertIsNotNone(status)
        self.assertEqual(status["state"], "terminal_incident")
        self.assertEqual(
            status["reason"],
            "terminal_receipt_attestation_failed",
        )

    def test_worker_rejects_nonisolated_python_before_keychain_access(
        self,
    ) -> None:
        generated = self._generate()
        self._commit_start()
        keychain_calls = 0

        def forbidden_keychain(arguments, **kwargs):
            nonlocal keychain_calls
            keychain_calls += 1
            return subprocess.CompletedProcess(
                arguments,
                0,
                stdout=b"must-not-be-read\n",
                stderr=b"",
            )

        self.isolated_process.stop()
        try:
            with self.assertRaises(LaunchAgentError):
                run_launch_agent_worker(
                    Path(generated["config_path"]),
                )
        finally:
            self.mock_isolated_process = self.isolated_process.start()
        self.assertEqual(keychain_calls, 0)

    def test_config_hmac_and_manifest_binding_reject_tampering(self) -> None:
        generated = self._generate()
        config_path = Path(generated["config_path"])
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["operation"] = "preflight"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        os.chmod(config_path, 0o600)
        with self.assertRaises(LaunchAgentError):
            inspect_launch_agent(
                self.runtime,
                authentication_key_file=self.authentication_key,
            )

        second_runtime = self.root / "manifest-binding-runtime"
        self._generate(runtime_dir=second_runtime, instance_token="4" * 24)
        self.public_manifest.write_text(
            json.dumps(
                {
                    "panel_id": "different-panel-v9",
                    "precommitment_sha256": "sha256:" + "c" * 64,
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaises(LaunchAgentError):
            inspect_launch_agent(
                second_runtime,
                authentication_key_file=self.authentication_key,
            )

    def test_python_entrypoint_binding_preserves_symlink_launch_path(self) -> None:
        target = Path(sys.executable).resolve()
        second_hop = self.root / "python3"
        second_hop.symlink_to(target)
        entrypoint = self.root / "python-entrypoint"
        entrypoint.symlink_to(second_hop.name)
        manifest = json.loads(self.public_manifest.read_text(encoding="utf-8"))
        manifest["runtime_contract"]["python_entrypoint_kind"] = "symlink_chain"
        self.public_manifest.write_text(
            json.dumps(manifest),
            encoding="utf-8",
        )

        generated = self._generate(python_executable=entrypoint)
        config, _ = self._config_and_key()
        binding = config["python_executable_binding"]
        self.assertEqual(config["python_executable"], str(entrypoint))
        self.assertEqual(binding["launch_path"], str(entrypoint))
        self.assertEqual(len(binding["symlink_hops"]), 2)
        self.assertEqual(
            binding["target"]["sha256"],
            config["python_executable_sha256"],
        )
        plist = plistlib.loads(Path(generated["plist_path"]).read_bytes())
        self.assertEqual(plist["ProgramArguments"][2], str(entrypoint))
        self.assertEqual(launchd_agent._runner_command(config)[0], str(entrypoint))

        second_hop.unlink()
        alternate = self.root / "python-alternate"
        shutil.copy2(target, alternate)
        os.chmod(alternate, alternate.stat().st_mode | 0o100)
        second_hop.symlink_to(alternate)
        with self.assertRaises(LaunchAgentError):
            inspect_launch_agent(
                self.runtime,
                authentication_key_file=self.authentication_key,
            )

    def test_python_isolated_bootstrap_binds_but_never_executes_pth(
        self,
    ) -> None:
        venv = self.root / "isolated-venv"
        binary_dir = venv / "bin"
        site_packages = (
            venv
            / "lib"
            / f"python{sys.version_info.major}.{sys.version_info.minor}"
            / "site-packages"
        )
        binary_dir.mkdir(parents=True, mode=0o700)
        site_packages.mkdir(parents=True, mode=0o700)
        entrypoint = binary_dir / "python"
        entrypoint.symlink_to(Path(sys.executable).resolve())
        pyvenv = venv / "pyvenv.cfg"
        pyvenv.write_text(
            "\n".join(
                (
                    f"home = {Path(sys.base_prefix) / 'bin'}",
                    "include-system-site-packages = false",
                    (
                        "version = "
                        f"{sys.version_info.major}.{sys.version_info.minor}."
                        f"{sys.version_info.micro}"
                    ),
                    f"executable = {Path(sys.executable).resolve()}",
                )
            )
            + "\n",
            encoding="utf-8",
        )
        os.chmod(pyvenv, 0o600)
        marker = self.root / "pth-executed"
        pth = site_packages / "malicious.pth"
        pth.write_text(
            "import pathlib; "
            f"pathlib.Path({str(marker)!r}).write_text('executed')\n",
            encoding="utf-8",
        )
        os.chmod(pth, 0o600)

        before = launchd_agent._python_entrypoint_binding(entrypoint)

        self.assertFalse(marker.exists())
        self.assertEqual(
            before["bootstrap"]["venv"]["startup_hook_inventory"][0][
                "relative_path"
            ],
            "malicious.pth",
        )
        self.assertEqual(
            before["bootstrap"]["interpreter_flags"],
            ["-I", "-S", "-B"],
        )
        pth.write_text("# changed without execution\n", encoding="utf-8")
        os.chmod(pth, 0o600)
        after = launchd_agent._python_entrypoint_binding(entrypoint)
        self.assertFalse(marker.exists())
        self.assertNotEqual(
            launchd_agent._component_sha256(before),
            launchd_agent._component_sha256(after),
        )

    def test_python_entrypoint_must_match_public_runtime_digest(self) -> None:
        manifest = json.loads(self.public_manifest.read_text(encoding="utf-8"))
        manifest["runtime_contract"]["python_executable_sha256"] = (
            "sha256:" + "f" * 64
        )
        self.public_manifest.write_text(
            json.dumps(manifest),
            encoding="utf-8",
        )
        with self.assertRaises(LaunchAgentError):
            self._generate()
        self.assertFalse(self.runtime.exists())

    def test_python_entrypoint_binding_rejects_byte_and_inode_drift(self) -> None:
        for suffix, mutate in (
            (
                "bytes",
                lambda path: path.write_bytes(path.read_bytes() + b"drift"),
            ),
            (
                "inode",
                lambda path: os.replace(
                    shutil.copy2(path, path.with_suffix(".replacement")),
                    path,
                ),
            ),
        ):
            with self.subTest(drift=suffix):
                target = self._copied_isolated_python(
                    f"python-{suffix}-venv"
                )
                runtime = self.root / f"python-{suffix}-runtime"
                self._generate(
                    python_executable=target,
                    runtime_dir=runtime,
                    instance_token=f"python-{suffix}",
                )
                mutate(target)
                with self.assertRaises(LaunchAgentError):
                    inspect_launch_agent(
                        runtime,
                        authentication_key_file=self.authentication_key,
                    )

    def test_worker_rechecks_python_binding_before_keychain_access(self) -> None:
        target = self._copied_isolated_python("python-worker-venv")
        generated = self._generate(python_executable=target)
        self._commit_start()
        target.write_bytes(target.read_bytes() + b"drift")
        keychain_calls = 0

        def forbidden_keychain(arguments, **kwargs):
            nonlocal keychain_calls
            keychain_calls += 1
            return subprocess.CompletedProcess(
                arguments, 0, stdout=b"must-not-be-read\n", stderr=b""
            )

        with self.assertRaises(LaunchAgentError):
            run_launch_agent_worker(
                Path(generated["config_path"]),
            )
        self.assertEqual(keychain_calls, 0)

    def test_runtime_module_tampering_is_rejected_before_keychain_access(self) -> None:
        for index, relative_source in enumerate(
            (
                Path("src/epiagentbench/launchd_agent.py"),
                Path("src/epiagentbench/persistent_supervisor.py"),
                Path("src/epiagentbench/development_matched_panel.py"),
            ),
            start=1,
        ):
            with self.subTest(source=relative_source.name):
                copied_repository = self._copy_runtime_sources(f"source-copy-{index}")
                copied_launchd = copied_repository / (
                    "src/epiagentbench/launchd_agent.py"
                )
                copied_supervisor = copied_repository / (
                    "src/epiagentbench/persistent_supervisor.py"
                )
                copied_matched_panel = copied_repository / (
                    "src/epiagentbench/development_matched_panel.py"
                )
                runtime = self.root / f"source-tamper-runtime-{index}"
                with (
                    patch.object(launchd_agent, "__file__", str(copied_launchd)),
                    patch.object(
                        persistent_supervisor,
                        "__file__",
                        str(copied_supervisor),
                    ),
                    patch.object(
                        development_matched_panel,
                        "__file__",
                        str(copied_matched_panel),
                    ),
                ):
                    generated = self._generate(
                        runtime_dir=runtime,
                        repository_root=copied_repository,
                        instance_token=f"source-tamper-{index}",
                    )
                    config, _, key = launchd_agent._load_and_validate(
                        runtime,
                        authentication_key_file=self.authentication_key,
                    )
                    self.assertRegex(
                        config["launchd_agent_source_sha256"],
                        r"\Asha256:[0-9a-f]{64}\Z",
                    )
                    self.assertRegex(
                        config["persistent_supervisor_source_sha256"],
                        r"\Asha256:[0-9a-f]{64}\Z",
                    )
                    self.assertRegex(
                        config["development_matched_panel_source_sha256"],
                        r"\Asha256:[0-9a-f]{64}\Z",
                    )
                    launchd_agent._write_start_marker(
                        runtime,
                        config=config,
                        authentication_key=key,
                    )
                    tampered_source = copied_repository / relative_source
                    with tampered_source.open("a", encoding="utf-8") as stream:
                        stream.write("\n# offline source-tamper canary\n")

                    keychain_calls = 0

                    def forbidden_keychain(arguments, **kwargs):
                        nonlocal keychain_calls
                        keychain_calls += 1
                        return subprocess.CompletedProcess(
                            arguments,
                            0,
                            stdout=b"must-not-be-read\n",
                            stderr=b"",
                        )

                    with self.assertRaises(LaunchAgentError):
                        run_launch_agent_worker(
                            Path(generated["config_path"]),
                        )
                    self.assertEqual(keychain_calls, 0)

    def test_wrong_explicit_authentication_key_is_rejected(self) -> None:
        self._generate()
        wrong_key = self.root / "wrong.key"
        wrong_key.write_bytes(b"z" * 32)
        os.chmod(wrong_key, 0o600)
        with self.assertRaises(LaunchAgentError):
            inspect_launch_agent(
                self.runtime,
                authentication_key_file=wrong_key,
            )

    def test_worker_uses_fixed_run_command_context_and_supervisor_runtime(self) -> None:
        generated = self._generate()
        self._commit_start()
        observed: dict[str, object] = {}

        def fake_keychain(arguments, **kwargs):
            self.assertEqual(kwargs["timeout"], 15)
            return subprocess.CompletedProcess(
                arguments,
                0,
                stdout=b"offline-cursor-key\n",
                stderr=b"",
            )

        def fake_supervised_command(**kwargs):
            observed.update(kwargs)
            return 0

        with patch(
            "epiagentbench.persistent_supervisor.run_supervised_command",
            side_effect=fake_supervised_command,
        ), patch(
            "epiagentbench.launchd_agent._finalize_launch_agent_validated",
            return_value={"state": "released"},
        ):
            self.assertEqual(
                run_launch_agent_worker(
                    Path(generated["config_path"]),
                ),
                0,
            )

        command = list(observed["command"])
        self.assertEqual(
            command[:5],
            [
                str(Path(sys.executable).resolve()),
                "-I",
                "-S",
                "-B",
                str(
                    self.repository
                    / "examples"
                    / "run_development_matched_panel.py"
                ),
            ],
        )
        self.assertEqual(command[5], "run")
        self.assertEqual(
            command[command.index("--supervisor-runtime") + 1],
            str(self.runtime),
        )
        self.assertEqual(observed["operation"], "production")
        self.assertEqual(observed["authentication_key"], b"a" * 32)
        config, _ = self._config_and_key()
        self.assertEqual(
            observed["execution_context_sha256"],
            config["execution_context_sha256"],
        )

    def test_v18_worker_self_bootstraps_child_and_restores_ambient_environment(
        self,
    ) -> None:
        cache_root, expected_environment = (
            self._enable_v18_runtime_binding()
        )
        generated = self._generate(runtime_cache_dir=cache_root)
        self._commit_start()

        def fake_keychain(arguments, **_kwargs):
            return subprocess.CompletedProcess(
                arguments,
                0,
                stdout=b"offline-cursor-key\n",
                stderr=b"",
            )

        def fake_supervised_command(**kwargs):
            self.assertEqual(
                {
                    name: os.environ.get(name)
                    for name in expected_environment
                },
                expected_environment,
            )
            self.assertEqual(
                {
                    name: kwargs["child_environment"].get(name)
                    for name in expected_environment
                },
                expected_environment,
            )
            return 9

        poisoned = {
            name: f"worker-poison-{index}"
            for index, name in enumerate(expected_environment)
        }
        with patch(
            "epiagentbench.persistent_supervisor.run_supervised_command",
            side_effect=fake_supervised_command,
        ), patch.dict(os.environ, poisoned, clear=False):
            before = {
                name: os.environ.get(name) for name in expected_environment
            }
            self.assertEqual(
                run_launch_agent_worker(
                    Path(generated["config_path"]),
                ),
                9,
            )
            self.assertEqual(
                {
                    name: os.environ.get(name)
                    for name in expected_environment
                },
                before,
            )

    def test_launchctl_not_found_is_distinct_from_query_failure(self) -> None:
        self._generate()
        status = launch_agent_status(
            self.runtime,
            authentication_key_file=self.authentication_key,
            command_runner=self._not_loaded_launchctl,
        )
        self.assertEqual(status["launchd_state"], "not_loaded")
        self.assertEqual(status["worker_state"], "not_started")
        self.assertEqual(status["supervisor"]["state"], "not_started")

        def failed(arguments, **kwargs):
            return subprocess.CompletedProcess(arguments, 64, stdout=b"", stderr=b"")

        with self.assertRaises(LaunchAgentError):
            launch_agent_status(
                self.runtime,
                authentication_key_file=self.authentication_key,
                command_runner=failed,
            )

    def test_status_authenticates_core_status_lease_and_context(self) -> None:
        self._generate()
        config, _ = self._complete_core()
        status = launch_agent_status(
            self.runtime,
            authentication_key_file=self.authentication_key,
            command_runner=self._not_loaded_launchctl,
        )
        supervisor = status["supervisor"]
        self.assertIs(supervisor["status_authenticated"], True)
        self.assertIs(supervisor["lease_authenticated"], True)
        self.assertEqual(supervisor["health"], "terminal")
        self.assertEqual(supervisor["lifecycle"], "completed")
        self.assertEqual(
            supervisor["execution_context_sha256"],
            config["execution_context_sha256"],
        )

    def test_completed_attestation_and_release_are_terminal_and_idempotent(self) -> None:
        self._generate()
        config, key = self._commit_start()
        launchd_agent._atomic_worker_status(
            self.runtime,
            config=config,
            authentication_key=key,
            state="supervisor_running",
        )
        self._complete_core()

        attestation = attest_completed_launch_agent(
            self.runtime,
            authentication_key_file=self.authentication_key,
            expected_operation="production",
            expected_panel_id=config["panel_id"],
            expected_precommitment_sha256=config["precommitment_sha256"],
        )
        self.assertIs(attestation["attested"], True)
        self.assertEqual(attestation["lifecycle"], "completed")
        self.assertEqual(attestation["config_file_sha256"][:7], "sha256:")

        with patch(
            "epiagentbench.launchd_agent._finalize_supervised_release",
            return_value={"status": "complete"},
        ) as release:
            first = finalize_launch_agent(
                self.runtime,
                authentication_key_file=self.authentication_key,
            )
            second = finalize_launch_agent(
                self.runtime,
                authentication_key_file=self.authentication_key,
            )
        self.assertEqual(first["state"], "released")
        self.assertEqual(second, first)
        self.assertEqual(release.call_count, 2)
        status = launch_agent_status(
            self.runtime,
            authentication_key_file=self.authentication_key,
            command_runner=self._not_loaded_launchctl,
        )
        self.assertEqual(status["worker_state"], "released")
        self.assertEqual(status["worker_reason"], "production_complete")

    def test_v18_finalize_self_bootstraps_and_restores_cache_environment(
        self,
    ) -> None:
        cache_root, expected_environment = (
            self._enable_v18_runtime_binding()
        )
        self._generate(runtime_cache_dir=cache_root)
        config, key = self._commit_start()
        launchd_agent._atomic_worker_status(
            self.runtime,
            config=config,
            authentication_key=key,
            state="supervisor_running",
        )
        self._complete_core()
        # Scientific libraries are expected to populate their dedicated cache
        # while the supervised child runs.  Post-completion release must
        # preserve the sealed cache boundary without requiring byte-identical
        # cache contents.
        generated_cache = cache_root / "numba" / "generated.cache"
        generated_cache.write_bytes(b"safe-post-start-cache-growth")
        os.chmod(generated_cache, 0o600)

        def assert_sealed_environment(_config):
            self.assertEqual(
                {
                    name: os.environ.get(name)
                    for name in expected_environment
                },
                expected_environment,
            )
            return {"status": "complete"}

        poisoned = {
            name: f"finalize-poison-{index}"
            for index, name in enumerate(expected_environment)
        }
        with patch(
            "epiagentbench.launchd_agent._finalize_supervised_release",
            side_effect=assert_sealed_environment,
        ), patch.dict(os.environ, poisoned, clear=False):
            before = {
                name: os.environ.get(name) for name in expected_environment
            }
            finalized = finalize_launch_agent(
                self.runtime,
                authentication_key_file=self.authentication_key,
            )
            self.assertEqual(finalized["state"], "released")
            self.assertEqual(
                {
                    name: os.environ.get(name)
                    for name in expected_environment
                },
                before,
            )

        status = launch_agent_status(
            self.runtime,
            authentication_key_file=self.authentication_key,
            command_runner=self._not_loaded_launchctl,
        )
        self.assertEqual(status["worker_state"], "released")

        control_calls: list[list[str]] = []

        def terminal_then_bootout(arguments, **_kwargs):
            control_calls.append(list(arguments))
            if arguments[1] == "print":
                return subprocess.CompletedProcess(
                    arguments,
                    0,
                    stdout=b"state = not running\n",
                    stderr=b"",
                )
            return subprocess.CompletedProcess(
                arguments, 0, stdout=b"", stderr=b""
            )

        uninstalled = uninstall_launch_agent(
            self.runtime,
            authentication_key_file=self.authentication_key,
            command_runner=terminal_then_bootout,
        )
        self.assertEqual(uninstalled["state"], "uninstalled")
        self.assertEqual(
            [call[1] for call in control_calls],
            ["print", "bootout"],
        )

    def test_v18_finalize_refuses_alternating_authenticated_config_snapshot(
        self,
    ) -> None:
        cache_root, _ = self._enable_v18_runtime_binding()
        self._generate(runtime_cache_dir=cache_root)
        config, key = self._commit_start()
        launchd_agent._atomic_worker_status(
            self.runtime,
            config=config,
            authentication_key=key,
            state="supervisor_running",
        )
        self._complete_core()
        authenticated = launchd_agent._read_authenticated_config(
            self.runtime,
            authentication_key_file=self.authentication_key,
        )
        alternate = dict(authenticated[2])
        alternate["label"] = alternate["label"] + ".alternate"
        replacement = (
            authenticated[0],
            authenticated[1],
            alternate,
            authenticated[3],
        )
        before = launchd_agent._worker_status(
            self.runtime,
            config=config,
            authentication_key=key,
        )

        with (
            patch(
                "epiagentbench.launchd_agent._read_authenticated_config",
                side_effect=(authenticated, replacement),
            ),
            patch(
                "epiagentbench.launchd_agent._finalize_supervised_release",
            ) as release,
            self.assertRaises(LaunchAgentError),
        ):
            finalize_launch_agent(
                self.runtime,
                authentication_key_file=self.authentication_key,
            )

        release.assert_not_called()
        observed = launchd_agent._worker_status(
            self.runtime,
            config=config,
            authentication_key=key,
        )
        self.assertEqual(observed, before)

    @unittest.skipUnless(hasattr(os, "fork"), "hard-crash recovery requires fork")
    def test_hard_crash_during_release_leaves_manual_finalize_recoverable(self) -> None:
        self._generate()
        config, key = self._commit_start()
        launchd_agent._atomic_worker_status(
            self.runtime,
            config=config,
            authentication_key=key,
            state="supervisor_running",
        )
        self._complete_core()

        child = os.fork()
        if child == 0:
            def hard_exit(_config):
                os._exit(97)

            with patch(
                "epiagentbench.launchd_agent._finalize_supervised_release",
                side_effect=hard_exit,
            ):
                finalize_launch_agent(
                    self.runtime,
                    authentication_key_file=self.authentication_key,
                )
            os._exit(98)

        _, wait_status = os.waitpid(child, 0)
        self.assertTrue(os.WIFEXITED(wait_status))
        self.assertEqual(os.WEXITSTATUS(wait_status), 97)
        pending = launch_agent_status(
            self.runtime,
            authentication_key_file=self.authentication_key,
            command_runner=self._not_loaded_launchctl,
        )
        self.assertEqual(pending["worker_state"], "release_pending")

        with patch(
            "epiagentbench.launchd_agent._finalize_supervised_release",
            return_value={"status": "complete"},
        ) as release:
            finalized = finalize_launch_agent(
                self.runtime,
                authentication_key_file=self.authentication_key,
            )
        self.assertEqual(finalized["state"], "released")
        self.assertEqual(release.call_count, 1)

    def test_release_validation_failure_is_terminal_and_never_retried(self) -> None:
        self._generate()
        config, key = self._commit_start()
        launchd_agent._atomic_worker_status(
            self.runtime,
            config=config,
            authentication_key=key,
            state="supervisor_running",
        )
        self._complete_core()

        with patch(
            "epiagentbench.launchd_agent._finalize_supervised_release",
            side_effect=ValueError("private provider output must never surface"),
        ) as release, self.assertRaises(LaunchAgentError):
            finalize_launch_agent(
                self.runtime,
                authentication_key_file=self.authentication_key,
            )
        self.assertEqual(release.call_count, 1)
        status = launch_agent_status(
            self.runtime,
            authentication_key_file=self.authentication_key,
            command_runner=self._not_loaded_launchctl,
        )
        self.assertEqual(status["worker_state"], "terminal_incident")
        self.assertEqual(status["worker_reason"], "release_validation_failed")
        self.assertEqual(
            status["release_failure_code"],
            "release_internal",
        )
        self.assertNotIn("private provider output", json.dumps(status))
        with self.assertRaises(LaunchAgentError):
            finalize_launch_agent(
                self.runtime,
                authentication_key_file=self.authentication_key,
            )
        self.assertEqual(release.call_count, 1)

    def test_release_validation_code_is_finite_authenticated_and_content_free(
        self,
    ) -> None:
        self._generate()
        config, key = self._commit_start()
        launchd_agent._atomic_worker_status(
            self.runtime,
            config=config,
            authentication_key=key,
            state="supervisor_running",
        )
        self._complete_core()
        secret_detail = "provider-output-DO-NOT-LEAK-database-row-42"

        with (
            patch(
                "epiagentbench.launchd_agent._finalize_supervised_release",
                side_effect=launchd_agent.ReleaseValidationError(
                    launchd_agent.ReleaseValidationFailureCode
                    .PUBLIC_COMMIT_FAILED
                ),
            ),
            self.assertRaises(LaunchAgentError),
        ):
            finalize_launch_agent(
                self.runtime,
                authentication_key_file=self.authentication_key,
            )

        status = launch_agent_status(
            self.runtime,
            authentication_key_file=self.authentication_key,
            command_runner=self._not_loaded_launchctl,
        )
        self.assertEqual(
            status["release_failure_code"],
            "release_public_commit_failed",
        )
        serialized = json.dumps(status, sort_keys=True)
        self.assertNotIn(secret_detail, serialized)
        self.assertNotIn("exception", serialized)

    def test_release_validation_status_requires_exact_finite_code_pairing(
        self,
    ) -> None:
        self._generate()
        config, key = self._config_and_key()
        with self.assertRaises(ValueError):
            launchd_agent._atomic_worker_status(
                self.runtime,
                config=config,
                authentication_key=key,
                state="terminal_incident",
                reason="release_validation_failed",
            )
        with self.assertRaises(ValueError):
            launchd_agent._atomic_worker_status(
                self.runtime,
                config=config,
                authentication_key=key,
                state="starting",
                release_failure_code=(
                    launchd_agent.ReleaseValidationFailureCode.INTERNAL
                ),
            )

        payload = {
            "schema_version": launchd_agent._WORKER_STATUS_SCHEMA,
            "label": config["label"],
            "operation": config["operation"],
            "panel_id": config["panel_id"],
            "precommitment_sha256": config["precommitment_sha256"],
            "execution_context_sha256": config[
                "execution_context_sha256"
            ],
            "state": "terminal_incident",
            "reason": "release_validation_failed",
            "release_failure_code": "release_unbounded_exception_text",
        }
        record = launchd_agent._seal_payload(
            launchd_agent._WORKER_STATUS_AUTH_DOMAIN,
            payload,
            key,
        )
        status_path = self.runtime / "launchd-worker-status.json"
        status_path.write_bytes(
            launchd_agent._canonical_bytes(record) + b"\n"
        )
        os.chmod(status_path, 0o600)
        with self.assertRaises(ValueError):
            launchd_agent._worker_status(
                self.runtime,
                config=config,
                authentication_key=key,
            )

    def test_tampered_worker_status_is_rejected(self) -> None:
        generated = self._generate()
        self._commit_start()

        def fake_keychain(arguments, **kwargs):
            return subprocess.CompletedProcess(
                arguments, 0, stdout=b"offline-cursor-key\n", stderr=b""
            )

        with patch(
            "epiagentbench.launchd_agent._run_core_supervisor",
            return_value=0,
        ), patch(
            "epiagentbench.launchd_agent._finalize_launch_agent_validated",
            return_value={"state": "released"},
        ):
            self.assertEqual(
                run_launch_agent_worker(
                    Path(generated["config_path"]),
                ),
                0,
            )
        status_path = self.runtime / "launchd-worker-status.json"
        record = json.loads(status_path.read_text(encoding="utf-8"))
        record["state"] = "starting"
        status_path.write_text(json.dumps(record), encoding="utf-8")
        os.chmod(status_path, 0o600)
        with self.assertRaises(LaunchAgentError):
            launch_agent_status(
                self.runtime,
                authentication_key_file=self.authentication_key,
                command_runner=self._not_loaded_launchctl,
            )

    def test_uninstall_requires_authenticated_terminal_worker_and_core(self) -> None:
        self._generate()
        self._commit_start()
        calls: list[list[str]] = []

        def inactive(arguments, **kwargs):
            calls.append(list(arguments))
            return subprocess.CompletedProcess(
                arguments,
                0,
                stdout=b"state = not running\n",
                stderr=b"",
            )

        with self.assertRaises(LaunchAgentError):
            uninstall_launch_agent(
                self.runtime,
                authentication_key_file=self.authentication_key,
                command_runner=inactive,
            )
        self.assertTrue(all("bootout" not in call for call in calls))

        config, key = self._complete_core()
        launchd_agent._atomic_worker_status(
            self.runtime,
            config=config,
            authentication_key=key,
            state="supervisor_exited",
            reason="success",
        )
        calls.clear()

        def terminal_then_bootout(arguments, **kwargs):
            calls.append(list(arguments))
            if arguments[1] == "print":
                return subprocess.CompletedProcess(
                    arguments, 0, stdout=b"state = not running\n", stderr=b""
                )
            return subprocess.CompletedProcess(arguments, 0, stdout=b"", stderr=b"")

        response = uninstall_launch_agent(
            self.runtime,
            authentication_key_file=self.authentication_key,
            command_runner=terminal_then_bootout,
        )
        self.assertEqual(response["state"], "uninstalled")
        self.assertEqual([call[1] for call in calls], ["print", "bootout"])

    def test_launchd_state_parser_is_exact_and_fail_closed(self) -> None:
        config = {"label": "org.epiagentbench.panel.offline"}
        valid = {
            b"state = running\n": "running",
            b"\tstate\t=\twaiting\r\n": "waiting",
            b"state = exited\n": "exited",
            b"  state = not running  \n": "not_running",
            (
                b"state = waiting\n"
                b"\tproperties = {\n"
                b"\t\tstate = running\n"
                b"\t}\n"
            ): "waiting",
            (
                b"\tstate = exited\n"
                b"\t\tstate = running\n"
                b"\t\t\tstate = waiting\n"
            ): "exited",
        }
        invalid = (
            b"",
            b"state = not-running\n",
            b"state = not  running\n",
            b"state = RUNNING\n",
            b"state = running\xff\n",
            b"state = waiting\nstate = running\n",
            b"\tstate = waiting\n\tstate = running\n\t\tstate = exited\n",
        )

        for stdout, expected in valid.items():
            with self.subTest(stdout=stdout):
                observed = launchd_agent._launchd_state(
                    config,
                    command_runner=lambda arguments, **kwargs: (
                        subprocess.CompletedProcess(
                            arguments, 0, stdout=stdout, stderr=b""
                        )
                    ),
                )
                self.assertEqual(observed, expected)
        for stdout in invalid:
            with self.subTest(stdout=stdout):
                observed = launchd_agent._launchd_state(
                    config,
                    command_runner=lambda arguments, **kwargs: (
                        subprocess.CompletedProcess(
                            arguments, 0, stdout=stdout, stderr=b""
                        )
                    ),
                )
                self.assertEqual(observed, "unknown")

    def test_failed_kickstart_leaves_durable_no_retry_marker(self) -> None:
        self._generate()
        calls: list[list[str]] = []

        def failed(arguments, **kwargs):
            calls.append(list(arguments))
            return subprocess.CompletedProcess(arguments, 64, stdout=b"", stderr=b"")

        with self.assertRaises(LaunchAgentError):
            start_launch_agent(
                self.runtime,
                authentication_key_file=self.authentication_key,
                command_runner=failed,
            )
        marker = self.runtime / "launchd-start-request.json"
        self.assertTrue(marker.is_file())
        self.assertEqual(marker.stat().st_mode & 0o777, 0o600)

        def would_succeed(arguments, **kwargs):
            calls.append(list(arguments))
            return subprocess.CompletedProcess(arguments, 0, stdout=b"", stderr=b"")

        with self.assertRaises(LaunchAgentError):
            start_launch_agent(
                self.runtime,
                authentication_key_file=self.authentication_key,
                command_runner=would_succeed,
            )
        self.assertEqual(len(calls), 1)

    def test_install_start_and_uninstall_share_nonblocking_control_lock(
        self,
    ) -> None:
        self._generate()
        calls: list[list[str]] = []

        def should_not_run(arguments, **kwargs):
            calls.append(list(arguments))
            return subprocess.CompletedProcess(arguments, 0, stdout=b"", stderr=b"")

        with launchd_agent._LaunchControlLock(self.runtime):
            with self.assertRaises(LaunchAgentError):
                install_launch_agent(
                    self.runtime,
                    authentication_key_file=self.authentication_key,
                    command_runner=should_not_run,
                )
            with self.assertRaises(LaunchAgentError):
                start_launch_agent(
                    self.runtime,
                    authentication_key_file=self.authentication_key,
                    command_runner=should_not_run,
                )
            with self.assertRaises(LaunchAgentError):
                uninstall_launch_agent(
                    self.runtime,
                    authentication_key_file=self.authentication_key,
                    command_runner=should_not_run,
                )
        self.assertEqual(calls, [])
        self.assertFalse(
            (self.runtime / launchd_agent._INSTALL_ATTEMPT_NAME).exists()
        )
        self.assertTrue(
            (self.runtime / launchd_agent._START_ATTEMPT_NAME).is_file()
        )

    def test_finalize_lock_contention_is_read_only(self) -> None:
        self._generate()
        config, key = self._commit_start()
        launchd_agent._atomic_worker_status(
            self.runtime,
            config=config,
            authentication_key=key,
            state="supervisor_running",
        )
        self._complete_core()
        before = launchd_agent._worker_status(
            self.runtime,
            config=config,
            authentication_key=key,
        )

        with (
            patch(
                "epiagentbench.launchd_agent._finalize_supervised_release",
            ) as release,
            launchd_agent._LaunchControlLock(self.runtime),
            self.assertRaises(LaunchAgentError),
        ):
            finalize_launch_agent(
                self.runtime,
                authentication_key_file=self.authentication_key,
            )

        release.assert_not_called()
        after = launchd_agent._worker_status(
            self.runtime,
            config=config,
            authentication_key=key,
        )
        self.assertEqual(after, before)

    def test_premature_finalize_is_read_only(self) -> None:
        self._generate()
        config, key = self._commit_start()
        launchd_agent._atomic_worker_status(
            self.runtime,
            config=config,
            authentication_key=key,
            state="supervisor_running",
        )
        before = launchd_agent._worker_status(
            self.runtime,
            config=config,
            authentication_key=key,
        )

        with (
            patch(
                "epiagentbench.launchd_agent._finalize_supervised_release",
            ) as release,
            self.assertRaises(LaunchAgentError),
        ):
            finalize_launch_agent(
                self.runtime,
                authentication_key_file=self.authentication_key,
            )

        release.assert_not_called()
        after = launchd_agent._worker_status(
            self.runtime,
            config=config,
            authentication_key=key,
        )
        self.assertEqual(after, before)

    def test_live_attestation_checks_worker_core_heartbeat_and_bindings(self) -> None:
        self._generate()
        config, key = self._commit_start()
        launchd_agent._atomic_worker_status(
            self.runtime,
            config=config,
            authentication_key=key,
            state="supervisor_running",
        )
        started = threading.Event()
        release = threading.Event()
        failure: list[BaseException] = []

        def supervise() -> None:
            try:
                run_supervised_panel(
                    runner_argv=("unused-offline-runner",),
                    environment={},
                    runtime_dir=self.runtime,
                    authentication_key=key,
                    execution_context_sha256=config["execution_context_sha256"],
                    command_runner=_BlockingRunner(started, release),
                )
            except BaseException as error:
                failure.append(error)

        thread = threading.Thread(target=supervise, daemon=True)
        thread.start()
        self.assertTrue(started.wait(timeout=3))
        with patch(
            "epiagentbench.launchd_agent._launchctl",
            side_effect=AssertionError("attestation must not call launchctl"),
        ), patch(
            "epiagentbench.persistent_supervisor.diagnose_supervisor_process",
            return_value=ProcessDiagnostic.MATCH,
        ):
            attestation = attest_live_launch_agent(
                self.runtime,
                authentication_key_file=self.authentication_key,
                expected_operation="production",
                expected_panel_id=config["panel_id"],
                expected_precommitment_sha256=config["precommitment_sha256"],
            )
        self.assertIs(attestation["attested"], True)
        self.assertEqual(attestation["supervisor_health"], "healthy")
        self.assertEqual(attestation["supervisor_process"], "match")
        with self.assertRaises(LiveAttestationError) as raised:
            attest_live_launch_agent(
                self.runtime,
                authentication_key_file=self.authentication_key,
                expected_operation="production",
                expected_panel_id="wrong-panel-v9",
                expected_precommitment_sha256=config["precommitment_sha256"],
            )
        self.assertIs(
            raised.exception.failure_code,
            LiveAttestationFailureCode.BINDING_MISMATCH,
        )
        release.set()
        thread.join(timeout=3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(failure, [])

    def test_live_attestation_reports_transient_core_reads_without_retry(self) -> None:
        self._generate()
        config, key = self._commit_start()
        launchd_agent._atomic_worker_status(
            self.runtime,
            config=config,
            authentication_key=key,
            state="supervisor_running",
        )
        with (
            patch(
                "epiagentbench.launchd_agent._core_status",
                side_effect=launchd_agent._TransientCoreStatusError(
                    "offline torn-read injection"
                ),
            ) as core_status,
            patch("epiagentbench.launchd_agent.time.sleep") as sleep,
            self.assertRaises(LiveAttestationError) as transient,
        ):
            attest_live_launch_agent(
                self.runtime,
                authentication_key_file=self.authentication_key,
                expected_operation="production",
                expected_panel_id=config["panel_id"],
                expected_precommitment_sha256=config["precommitment_sha256"],
            )
        self.assertIs(
            transient.exception.failure_code,
            LiveAttestationFailureCode.STATUS_SNAPSHOT_UNSTABLE,
        )
        self.assertEqual(core_status.call_count, 1)
        sleep.assert_not_called()

    def test_core_status_uses_one_wall_clock_sample(self) -> None:
        self._generate()
        config, key = self._config_and_key()
        (self.runtime / persistent_supervisor.STATUS_FILE).write_bytes(b"")
        (self.runtime / persistent_supervisor.LEASE_FILE).write_bytes(b"")
        core_status = {
            "schema_version": persistent_supervisor.SCHEMA_VERSION,
            "lease_epoch": "1" * 64,
            "execution_context_sha256": config[
                "execution_context_sha256"
            ],
            "lifecycle": "running",
            "assignment_phase": "running",
            "pid": 4123,
            "boot_identity_sha256": "sha256:" + "2" * 64,
            "process_birth_identity_sha256": "sha256:" + "3" * 64,
            "heartbeat_sequence": 1,
            "heartbeat_wall_unix_seconds": 1_000,
            "completed_assignments": 0,
            "total_assignments": 1,
            "active_assignment_ordinal": 1,
            "pause_after_current": False,
            "suspend_gap_detected": False,
            "failure_code": "none",
        }
        with (
            patch.object(
                persistent_supervisor,
                "read_supervisor_status",
                return_value=core_status,
            ),
            patch.object(
                persistent_supervisor,
                "read_supervisor_lease",
                return_value=core_status,
            ),
            patch.object(
                persistent_supervisor,
                "diagnose_supervisor_process",
                return_value=ProcessDiagnostic.MATCH,
            ),
            patch.object(
                launchd_agent.time,
                "time",
                side_effect=(1_100.0, 1_000.0),
            ) as wall_clock,
        ):
            sampled = launchd_agent._core_status(
                self.runtime,
                authentication_key=key,
                expected_execution_context_sha256=config[
                    "execution_context_sha256"
                ],
            )
        self.assertEqual(wall_clock.call_count, 1)
        self.assertEqual(sampled["health"], "stale_heartbeat")
        self.assertEqual(sampled["heartbeat_age_bucket"], "under_2m")

    def test_live_attestation_semantic_failures_have_finite_codes(self) -> None:
        self._generate()
        config, key = self._commit_start()
        launchd_agent._atomic_worker_status(
            self.runtime,
            config=config,
            authentication_key=key,
            state="supervisor_running",
        )
        healthy = {
            "state": "authenticated",
            "lifecycle": "running",
            "assignment_phase": "running",
            "health": "healthy",
            "process_diagnostic": "match",
            "heartbeat_age_bucket": "fresh",
        }
        cases = (
            (
                {"lifecycle": "failed_closed"},
                LiveAttestationFailureCode.CORE_NOT_RUNNING,
            ),
            (
                {"assignment_phase": "prepared"},
                LiveAttestationFailureCode.CORE_PHASE_INVALID,
            ),
            (
                {"health": "invalid"},
                LiveAttestationFailureCode.CORE_UNHEALTHY,
            ),
            (
                {
                    "health": "process_mismatch",
                    "process_diagnostic": "boot_mismatch",
                },
                LiveAttestationFailureCode.PROCESS_IDENTITY_MISMATCH,
            ),
            (
                {
                    "health": "stale_heartbeat",
                    "heartbeat_age_bucket": "under_2m",
                },
                LiveAttestationFailureCode.HEARTBEAT_STALE,
            ),
        )
        for changes, expected in cases:
            with self.subTest(failure_code=expected):
                core = {**healthy, **changes}
                with (
                    patch(
                        "epiagentbench.launchd_agent._core_status",
                        return_value=core,
                    ),
                    self.assertRaises(LiveAttestationError) as raised,
                ):
                    attest_live_launch_agent(
                        self.runtime,
                        authentication_key_file=self.authentication_key,
                        expected_operation="production",
                        expected_panel_id=config["panel_id"],
                        expected_precommitment_sha256=(
                            config["precommitment_sha256"]
                        ),
                    )
                self.assertIs(raised.exception.failure_code, expected)

        self.assertEqual(
            launchd_agent._heartbeat_age_bucket(
                1_006,
                now_wall_seconds=1_000.0,
            ),
            "future",
        )
        self.assertEqual(
            launchd_agent._heartbeat_age_bucket(
                1_005,
                now_wall_seconds=1_000.0,
            ),
            "fresh",
        )

        with (
            patch(
                "epiagentbench.launchd_agent._core_status",
                return_value={
                    "state": "not_started",
                    "status_authenticated": False,
                    "lease_authenticated": False,
                    "health": "not_started",
                },
            ) as core_status,
            patch("epiagentbench.launchd_agent.time.sleep") as sleep,
            self.assertRaises(LiveAttestationError) as semantic,
        ):
            attest_live_launch_agent(
                self.runtime,
                authentication_key_file=self.authentication_key,
                expected_operation="production",
                expected_panel_id=config["panel_id"],
                expected_precommitment_sha256=config["precommitment_sha256"],
            )
        self.assertIs(
            semantic.exception.failure_code,
            LiveAttestationFailureCode.CORE_NOT_STARTED,
        )
        self.assertEqual(core_status.call_count, 1)
        sleep.assert_not_called()

    def test_worker_script_self_bootstraps_only_in_isolated_python(self) -> None:
        script = self.repository / "examples" / "run_persistent_panel_supervisor.py"
        completed = subprocess.run(
            [
                str(Path(sys.executable)),
                "-I",
                "-S",
                "-B",
                str(script),
                "--help",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={},
            check=False,
            timeout=10,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr.decode("utf-8"))
        direct = subprocess.run(
            [str(Path(sys.executable)), str(script), "--help"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={},
            check=False,
            timeout=10,
        )
        self.assertEqual(direct.returncode, 2)


if __name__ == "__main__":
    unittest.main()
