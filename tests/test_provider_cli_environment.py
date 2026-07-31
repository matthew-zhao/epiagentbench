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

import epiagentbench.provider_cli_environment as provider_environment


class ProviderCLIEnvironmentTests(unittest.TestCase):
    def _executable(self, directory: Path, name: str, payload: bytes) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        executable = directory / name
        if name == "cursor-agent":
            payload = b"#!/usr/bin/env bash\n" + payload
        elif name.startswith("codex"):
            payload = b"\xcf\xfa\xed\xfe" + payload
        executable.write_bytes(payload)
        executable.chmod(0o755)
        return executable

    def test_cursor_uses_account_local_role_not_ambient_path_or_home(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            account_home = root / "account"
            expected = self._executable(
                account_home / ".local" / "bin",
                "cursor-agent",
                b"cursor",
            )
            malicious = self._executable(
                root / "ambient",
                "cursor-agent",
                b"malicious",
            )
            with (
                patch.object(
                    provider_environment,
                    "current_account",
                    return_value=("tester", account_home, "/bin/zsh"),
                ),
                patch.dict(
                    os.environ,
                    {
                        "HOME": str(root / "wrong-home"),
                        "PATH": str(malicious.parent),
                    },
                    clear=True,
                ),
            ):
                resolution = provider_environment.resolve_provider_cli(
                    "cursor-agent"
                )
            self.assertEqual(resolution.launch_path, expected.resolve())
            self.assertEqual(
                resolution.discovery_role, "current_account_local_bin"
            )

    def test_distinct_duplicate_candidates_fail_closed(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first"
            second = root / "second"
            self._executable(first, "codex", b"first")
            self._executable(second, "codex", b"second")
            with (
                patch.object(
                    provider_environment,
                    "_search_directories",
                    return_value=(
                        ("first_role", first, root),
                        ("second_role", second, root),
                    ),
                ),
                self.assertRaisesRegex(RuntimeError, "ambiguous"),
            ):
                provider_environment.resolve_provider_cli("codex")

    def test_identical_byte_symlink_retarget_changes_frozen_identity(
        self,
    ) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            launch_directory = root / "bin"
            launch_directory.mkdir()
            first = self._executable(
                root / "first", "codex-target", b"same-bytes"
            )
            second = self._executable(
                root / "second", "codex-target", b"same-bytes"
            )
            launch = launch_directory / "codex"
            launch.symlink_to(first)
            with patch.object(
                provider_environment,
                "_search_directories",
                return_value=(("test_role", launch_directory, root),),
            ):
                frozen = provider_environment.resolve_provider_cli("codex")
                launch.unlink()
                launch.symlink_to(second)
                current = provider_environment.resolve_provider_cli("codex")
                self.assertEqual(frozen.target_sha256, current.target_sha256)
                self.assertNotEqual(
                    provider_environment.provider_cli_public_identity(frozen),
                    provider_environment.provider_cli_public_identity(current),
                )
                with self.assertRaisesRegex(RuntimeError, "changed"):
                    provider_environment.attest_provider_cli_resolution(
                        frozen
                    )

    def test_adjacent_installation_dependency_is_content_bound(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            launch_directory = root / "bin"
            target_directory = root / "install"
            launch_directory.mkdir()
            target = self._executable(
                target_directory, "codex-target", b"executable"
            )
            dependency = target_directory / "adjacent.data"
            dependency.write_bytes(b"dependency-v1")
            dependency.chmod(0o644)
            (launch_directory / "codex").symlink_to(target)
            with patch.object(
                provider_environment,
                "_search_directories",
                return_value=(("test_role", launch_directory, root),),
            ):
                frozen = provider_environment.resolve_provider_cli("codex")
                self.assertEqual(frozen.installation_file_count, 2)
                dependency.write_bytes(b"dependency-v2")
                with self.assertRaisesRegex(RuntimeError, "changed"):
                    provider_environment.attest_provider_cli_resolution(
                        frozen
                    )

    def test_unapproved_executable_name_is_rejected_before_search(self) -> None:
        with (
            patch.object(
                provider_environment,
                "_search_directories",
                side_effect=AssertionError("search must not run"),
            ),
            self.assertRaisesRegex(RuntimeError, "not allowlisted"),
        ):
            provider_environment.resolve_provider_cli("git")

    def test_broken_configured_search_role_fails_closed(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            loop = root / "loop"
            loop.symlink_to(loop.name)
            with (
                patch.object(
                    provider_environment,
                    "_search_directories",
                    return_value=(("broken_role", loop, root),),
                ),
                self.assertRaisesRegex(RuntimeError, "search role"),
            ):
                provider_environment.resolve_provider_cli("codex")

    def test_unapproved_writable_ancestry_fails_closed(self) -> None:
        for role, mode in (
            ("test_role", 0o775),
            ("root_managed_homebrew_bin", 0o777),
        ):
            with self.subTest(role=role, mode=oct(mode)):
                with TemporaryDirectory() as directory:
                    root = Path(directory).resolve()
                    launch_directory = root / "bin"
                    target = self._executable(
                        root / "install",
                        "codex-target",
                        b"executable",
                    )
                    launch_directory.mkdir()
                    (launch_directory / "codex").symlink_to(target)
                    root.chmod(mode)
                    with (
                        patch.object(
                            provider_environment,
                            "_search_directories",
                            return_value=(
                                (role, launch_directory, root),
                            ),
                        ),
                        self.assertRaisesRegex(
                            RuntimeError, "ancestry is unsafe"
                        ),
                    ):
                        provider_environment.resolve_provider_cli("codex")

    @unittest.skipUnless(
        sys.platform == "darwin",
        "the frozen provider CLI installation roles are macOS-specific",
    )
    def test_real_env_i_static_cli_discovery_on_bound_host(self) -> None:
        account = pwd.getpwuid(os.getuid())
        launch_paths = (
            Path("/opt/homebrew/bin/claude"),
            Path("/opt/homebrew/bin/codex"),
            Path(account.pw_dir) / ".local" / "bin" / "cursor-agent",
        )
        present = tuple(
            path.exists() or path.is_symlink() for path in launch_paths
        )
        if not any(present):
            self.skipTest("this host has no benchmark provider installations")
        self.assertTrue(
            all(present),
            "a partially installed benchmark provider panel must fail closed",
        )
        source_root = Path(__file__).resolve().parents[1] / "src"
        program = (
            "import json,sys;"
            f"sys.path.insert(0,{str(source_root)!r});"
            "from epiagentbench.provider_cli_environment import "
            "resolve_provider_cli,provider_cli_public_identity;"
            "print(json.dumps([provider_cli_public_identity("
            "resolve_provider_cli(name)) for name in "
            "('claude','codex','cursor-agent')],sort_keys=True))"
        )
        with TemporaryDirectory(
            prefix="eab26-real-env-i-", dir=Path(account.pw_dir)
        ) as directory:
            root = Path(directory)
            clean_home = root / "home"
            clean_tmp = root / "tmp"
            clean_home.mkdir(mode=0o700)
            clean_tmp.mkdir(mode=0o700)
            completed = subprocess.run(
                [sys.executable, "-I", "-S", "-B", "-c", program],
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
                timeout=30,
            )
        self.assertEqual(
            completed.returncode,
            0,
            completed.stderr.decode("utf-8", errors="replace"),
        )
        identities = json.loads(completed.stdout)
        self.assertEqual(
            [identity["name"] for identity in identities],
            ["claude", "codex", "cursor-agent"],
        )
        self.assertTrue(
            all(
                set(identity)
                == {
                    "ancestry_binding_sha256",
                    "discovery_role",
                    "entrypoint_binding_sha256",
                    "entrypoint_kind",
                    "executable_sha256",
                    "execution_format",
                    "external_runtime_policy",
                    "installation_file_count",
                    "installation_kind",
                    "installation_root_binding_sha256",
                    "installation_sha256",
                    "installation_total_bytes",
                    "name",
                }
                for identity in identities
            )
        )
        serialized = json.dumps(identities, sort_keys=True)
        self.assertNotIn(str(Path(account.pw_dir)), serialized)
        self.assertNotIn("/", serialized)


if __name__ == "__main__":
    unittest.main()
