from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import epiagentbench.development_matched_panel as matched


class V48SmokeTmpdirTests(unittest.TestCase):
    def test_socket_path_budget_accepts_72_bytes_and_rejects_73(self) -> None:
        accepted = Path("/" + "a" * 71)
        rejected = Path("/" + "a" * 72)
        self.assertEqual(len(os.fsencode(str(accepted))), 72)
        self.assertEqual(len(os.fsencode(str(rejected))), 73)
        matched._assert_preparation_socket_path_budget(accepted)
        with self.assertRaisesRegex(RuntimeError, "socket path budget"):
            matched._assert_preparation_socket_path_budget(rejected)
        self.assertEqual(
            matched._PREPARATION_EPISODE_TMPDIR_MAX_BYTES,
            72,
        )

    def test_directory_observation_retries_one_interruption(self) -> None:
        with TemporaryDirectory(dir="/private/tmp") as temporary:
            candidate = Path(temporary)
            real_lstat = Path.lstat
            calls = 0

            def flaky_lstat(path: Path):
                nonlocal calls
                if path == candidate and calls == 0:
                    calls += 1
                    raise InterruptedError()
                calls += 1
                return real_lstat(path)

            with patch.object(Path, "lstat", flaky_lstat):
                metadata, resolved, entries = (
                    matched._provider_free_directory_observation(
                        candidate,
                        label="HOME",
                    )
                )
        self.assertEqual(resolved, candidate.resolve())
        self.assertEqual(entries, ())
        self.assertEqual(metadata.st_uid, os.getuid())
        self.assertGreaterEqual(calls, 2)

    def test_directory_observation_finitely_fails_repeated_interruptions(
        self,
    ) -> None:
        with TemporaryDirectory(dir="/private/tmp") as temporary:
            candidate = Path(temporary)
            with (
                patch.object(
                    Path,
                    "lstat",
                    side_effect=InterruptedError(),
                ) as lstat,
                self.assertRaisesRegex(RuntimeError, "was interrupted"),
            ):
                matched._provider_free_directory_observation(
                    candidate,
                    label="HOME",
                )
        self.assertEqual(
            lstat.call_count,
            matched._PROVIDER_FREE_DIRECTORY_ATTESTATION_ATTEMPTS,
        )

    def test_directory_observation_does_not_retry_missing_path(self) -> None:
        candidate = Path("/private/tmp/eab48-definitely-missing")
        with (
            patch.object(
                Path,
                "lstat",
                side_effect=FileNotFoundError(),
            ) as lstat,
            self.assertRaisesRegex(RuntimeError, "is unavailable"),
        ):
            matched._provider_free_directory_observation(
                candidate,
                label="HOME",
            )
        lstat.assert_called_once_with()

    def test_directory_fd_guard_detects_same_path_replacement(self) -> None:
        with TemporaryDirectory(dir="/private/tmp") as temporary:
            namespace = Path(temporary)
            account_home = namespace / "account"
            repository = namespace / "repository"
            cache = namespace / "cache"
            clean_home = account_home / "home"
            clean_tmp = account_home / "tmp"
            for directory in (
                account_home,
                repository,
                cache,
                clean_home,
                clean_tmp,
            ):
                directory.mkdir(mode=0o700)
            environment = {
                "HOME": str(clean_home),
                "TMPDIR": str(clean_tmp),
            }
            with (
                patch.dict(os.environ, environment, clear=False),
                patch.object(
                    matched,
                    "current_account",
                    return_value=("offline", account_home, "/bin/zsh"),
                ),
                matched._provider_free_directory_identity_guard(
                    repository_root=repository,
                    runtime_cache_root=cache,
                ) as reattest,
            ):
                moved = account_home / "tmp-original"
                clean_tmp.rename(moved)
                clean_tmp.mkdir(mode=0o700)
                with self.assertRaisesRegex(RuntimeError, "identity changed"):
                    reattest()


if __name__ == "__main__":
    unittest.main()
