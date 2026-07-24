from __future__ import annotations

import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import threading
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import epiagentbench.launchd_agent as launchd_agent
import epiagentbench.persistent_supervisor as persistent_supervisor
from epiagentbench.persistent_supervisor import ProcessDiagnostic, run_supervised_panel
from epiagentbench.launchd_agent import (
    LaunchAgentError,
    LiveAttestationError,
    LiveAttestationFailureCode,
    attest_completed_launch_agent,
    attest_live_launch_agent,
    finalize_launch_agent,
    generate_launch_agent,
    inspect_launch_agent,
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
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.runtime = self.root / "runtime"
        self.repository = Path(__file__).resolve().parents[1]
        self.authentication_key = self.root / "authentication.key"
        self.authentication_key.write_bytes(b"a" * 32)
        os.chmod(self.authentication_key, 0o600)
        self.claude_storage = self.root / "claude-storage"
        self.codex_storage = self.root / "codex-storage"
        self.claude_storage.mkdir(mode=0o700)
        self.codex_storage.mkdir(mode=0o700)
        self.private_state = self.root / "private.json"
        self.public_manifest = self.root / "manifest.json"
        self.public_results = self.root / "results.json"
        self.private_state.write_text("{}", encoding="utf-8")
        self.public_manifest.write_text(
            json.dumps(
                {
                    "panel_id": "development-matched-50x6-v9-test",
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
        os.chmod(self.private_state, 0o600)
        os.chmod(self.public_manifest, 0o600)

    def tearDown(self) -> None:
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
            "cursor_keychain_service": "epiagentbench-cursor-v9-test",
            "cursor_keychain_account": "offline-test-account",
            "operation": "production",
            "path_environment": "/usr/bin:/bin",
            "instance_token": "1" * 24,
        }
        arguments.update(changes)
        return generate_launch_agent(**arguments)

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
        self.assertEqual(arguments[0:2], ["/usr/bin/caffeinate", "-dimsu"])
        self.assertEqual(arguments[-3:-1], ["worker", "--config"])
        self.assertEqual(Path(arguments[-1]), config_path)
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
        self.assertNotIn("epiagentbench-cursor-v9-test", joined_arguments)
        self.assertNotIn("offline-test-account", joined_arguments)
        self.assertNotIn("CURSOR_API_KEY", joined_arguments)
        self.assertNotIn("security", joined_arguments)
        self.assertNotIn("claude", joined_arguments)
        self.assertNotIn("codex", joined_arguments)
        self.assertNotIn("cursor-agent", joined_arguments)

        all_generated = raw_plist + config_path.read_bytes()
        for canary in _SECRET_CANARIES:
            self.assertNotIn(canary.encode(), all_generated)

        # The private config contains references, never credential contents.
        config = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertNotIn("cursor_api_key", config)
        self.assertNotIn("environment", config)

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
            public_preflight_path=self.root / "preflight.json",
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
            "epiagentbench-cursor-v9-test",
            "offline-test-account",
            *_SECRET_CANARIES,
        ):
            self.assertNotIn(value, encoded)

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

    def test_worker_child_exit_is_finite_and_never_persists_keychain_value(self) -> None:
        generated = self._generate()
        self._commit_start()
        config_path = Path(generated["config_path"])
        observed: dict[str, str] = {}

        def fake_keychain(arguments, **kwargs):
            return subprocess.CompletedProcess(
                arguments,
                0,
                stdout=(_SECRET_CANARIES[0] + "\n").encode(),
                stderr=b"ignored provider diagnostic",
            )

        def fake_child(config, *, child_environment, authentication_key):
            observed["cursor"] = child_environment["CURSOR_API_KEY"]
            observed["authentication_key"] = authentication_key.decode("ascii")
            return 19

        with patch(
            "epiagentbench.launchd_agent._run_core_supervisor",
            side_effect=fake_child,
        ):
            return_code = run_launch_agent_worker(
                config_path,
                keychain_runner=fake_keychain,
            )

        self.assertEqual(return_code, 19)
        self.assertEqual(observed["cursor"], _SECRET_CANARIES[0])
        self.assertEqual(observed["authentication_key"], "a" * 32)
        status_path = self.runtime / "launchd-worker-status.json"
        self.assertEqual(status_path.stat().st_mode & 0o777, 0o600)
        status = json.loads(status_path.read_text(encoding="utf-8"))
        self.assertEqual(status["state"], "supervisor_exited")
        self.assertEqual(status["reason"], "failure")
        persisted = b"".join(path.read_bytes() for path in self.runtime.iterdir())
        for canary in _SECRET_CANARIES:
            self.assertNotIn(canary.encode(), persisted)

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
        target = self.root / "python-target"
        shutil.copy2(Path(sys.executable).resolve(), target)
        os.chmod(target, target.stat().st_mode | 0o100)
        second_hop = self.root / "python3"
        second_hop.symlink_to(target.name)
        entrypoint = self.root / "python"
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
        second_hop.symlink_to(alternate.name)
        with self.assertRaises(LaunchAgentError):
            inspect_launch_agent(
                self.runtime,
                authentication_key_file=self.authentication_key,
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
                target = self.root / f"python-{suffix}"
                shutil.copy2(Path(sys.executable).resolve(), target)
                os.chmod(target, target.stat().st_mode | 0o100)
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
        target = self.root / "python-worker"
        shutil.copy2(Path(sys.executable).resolve(), target)
        os.chmod(target, target.stat().st_mode | 0o100)
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
                keychain_runner=forbidden_keychain,
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
                runtime = self.root / f"source-tamper-runtime-{index}"
                with (
                    patch.object(launchd_agent, "__file__", str(copied_launchd)),
                    patch.object(
                        persistent_supervisor,
                        "__file__",
                        str(copied_supervisor),
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
                            keychain_runner=forbidden_keychain,
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
            "epiagentbench.launchd_agent.finalize_launch_agent",
            return_value={"state": "released"},
        ):
            self.assertEqual(
                run_launch_agent_worker(
                    Path(generated["config_path"]),
                    keychain_runner=fake_keychain,
                ),
                0,
            )

        command = list(observed["command"])
        self.assertEqual(command[2], "run")
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

    def test_keychain_timeout_fails_closed_with_authenticated_status(self) -> None:
        generated = self._generate()
        self._commit_start()

        def timed_out(arguments, **kwargs):
            self.assertEqual(kwargs["timeout"], 15)
            raise subprocess.TimeoutExpired(arguments, kwargs["timeout"])

        self.assertEqual(
            run_launch_agent_worker(
                Path(generated["config_path"]),
                keychain_runner=timed_out,
            ),
            70,
        )
        status = launch_agent_status(
            self.runtime,
            authentication_key_file=self.authentication_key,
            command_runner=self._not_loaded_launchctl,
        )
        self.assertEqual(status["worker_state"], "terminal_incident")
        self.assertEqual(status["worker_reason"], "cursor_keychain_unavailable")
        self.assertIs(status["worker_authenticated"], True)

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
        self.assertNotIn("private provider output", json.dumps(status))
        with self.assertRaises(LaunchAgentError):
            finalize_launch_agent(
                self.runtime,
                authentication_key_file=self.authentication_key,
            )
        self.assertEqual(release.call_count, 1)

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
            "epiagentbench.launchd_agent.finalize_launch_agent",
            return_value={"state": "released"},
        ):
            self.assertEqual(
                run_launch_agent_worker(
                    Path(generated["config_path"]),
                    keychain_runner=fake_keychain,
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
        }
        invalid = (
            b"",
            b"state = not-running\n",
            b"state = not  running\n",
            b"state = RUNNING\n",
            b"state = running\xff\n",
            b"state = waiting\nstate = running\n",
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

    def test_start_and_uninstall_share_nonblocking_control_lock(self) -> None:
        self._generate()
        calls: list[list[str]] = []

        def should_not_run(arguments, **kwargs):
            calls.append(list(arguments))
            return subprocess.CompletedProcess(arguments, 0, stdout=b"", stderr=b"")

        with launchd_agent._LaunchControlLock(self.runtime):
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
                {"health": "stale"},
                LiveAttestationFailureCode.CORE_UNHEALTHY,
            ),
            (
                {"process_diagnostic": "absent"},
                LiveAttestationFailureCode.PROCESS_IDENTITY_MISMATCH,
            ),
            (
                {"heartbeat_age_bucket": "under_2m"},
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

    def test_worker_script_self_bootstraps_without_pythonpath(self) -> None:
        script = self.repository / "examples" / "run_persistent_panel_supervisor.py"
        completed = subprocess.run(
            [str(Path(sys.executable).resolve()), str(script), "--help"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={},
            check=False,
            timeout=10,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
