from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from epiagentbench.cli import build_parser, main
from epiagentbench.trusted.cohort_freezer import (
    CohortFreezeError,
    compute_generator_fingerprint,
    freeze_private_starsim_cohort,
)
from epiagentbench.trusted.episode_pack import (
    PrivateEpisodeCohortManifest,
    PrivateEpisodePack,
)
from epiagentbench.trusted.ltc_closed_loop import LtcStarsimV3Backend
from epiagentbench.trusted.starsim_episode import (
    LIVE_FAMILY_TO_MODE,
    StarsimSurveillanceBackend,
)


AUTHENTICATION_KEY = b"private cohort authentication key".ljust(32, b"!")


def _write_key(path: Path, value: bytes = AUTHENTICATION_KEY) -> None:
    path.write_bytes(value)
    os.chmod(path, 0o600)


def _make_source_tree(root: Path, *, changed: bool = False) -> None:
    evaluator = root / "epiagentbench"
    client = root / "epiagentbench_client"
    (evaluator / "data").mkdir(parents=True)
    client.mkdir()
    (evaluator / "generator.py").write_text(
        "VALUE = 2\n" if changed else "VALUE = 1\n", encoding="utf-8"
    )
    (evaluator / "data" / "profile.json").write_text(
        '{"profile":1}', encoding="utf-8"
    )
    (client / "client.py").write_text("PUBLIC = True\n", encoding="utf-8")
    (client / "ignored.txt").write_text("not fingerprinted", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        "[project]\nname='test-generator'\nversion='0.1'\n",
        encoding="utf-8",
    )


class GeneratorFingerprintTests(unittest.TestCase):
    def test_fingerprint_is_path_independent_and_content_bound(self):
        with TemporaryDirectory() as directory:
            first = Path(directory) / "first"
            second = Path(directory) / "second"
            changed = Path(directory) / "changed"
            _make_source_tree(first)
            shutil.copytree(first, second)
            _make_source_tree(changed, changed=True)

            baseline = compute_generator_fingerprint(source_root=first)
            copied = compute_generator_fingerprint(source_root=second)
            modified = compute_generator_fingerprint(source_root=changed)
            self.assertEqual(baseline, copied)
            self.assertNotEqual(baseline, modified)
            self.assertRegex(baseline, r"^sha256:[0-9a-f]{64}$")

            (second / "pyproject.toml").write_text(
                "[project]\nname='test-generator'\nversion='0.2'\n",
                encoding="utf-8",
            )
            self.assertNotEqual(
                baseline, compute_generator_fingerprint(source_root=second)
            )

    def test_optional_candidate_profile_is_domain_bound(self):
        with TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            _make_source_tree(root)
            absent = compute_generator_fingerprint(source_root=root)
            empty = compute_generator_fingerprint(
                source_root=root, candidate_profile_bytes=b""
            )
            first = compute_generator_fingerprint(
                source_root=root, candidate_profile_bytes=b'{"candidate":1}'
            )
            second = compute_generator_fingerprint(
                source_root=root, candidate_profile_bytes=b'{"candidate":2}'
            )
            self.assertEqual(
                first,
                compute_generator_fingerprint(
                    source_root=root,
                    candidate_profile_bytes=b'{"candidate":1}',
                ),
            )
            self.assertEqual(len({absent, empty, first, second}), 4)

    def test_runtime_dependency_identity_is_content_bound(self):
        with TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            _make_source_tree(root)
            with patch(
                "epiagentbench.trusted.cohort_freezer._distribution_identity",
                return_value={"version": "1", "record_sha256": "a"},
            ):
                first = compute_generator_fingerprint(source_root=root)
            with patch(
                "epiagentbench.trusted.cohort_freezer._distribution_identity",
                return_value={"version": "2", "record_sha256": "b"},
            ):
                second = compute_generator_fingerprint(source_root=root)
            self.assertNotEqual(first, second)

    def test_symlinked_source_input_is_rejected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            _make_source_tree(root)
            target = root / "outside.py"
            target.write_text("SECRET = 1\n", encoding="utf-8")
            (root / "epiagentbench" / "linked.py").symlink_to(target)
            with self.assertRaisesRegex(CohortFreezeError, "symlink"):
                compute_generator_fingerprint(source_root=root)


class PrivateCohortFreezeTests(unittest.TestCase):
    def test_freeze_writes_exact_balanced_private_set_without_simulation(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            key_path = root / "authentication.key"
            cohort_path = root / "private-cohort"
            _write_key(key_path)

            with patch.object(
                StarsimSurveillanceBackend,
                "create_runtime",
                side_effect=AssertionError("freezer must not simulate"),
            ), patch.object(
                StarsimSurveillanceBackend,
                "create_episode",
                side_effect=AssertionError("freezer must not simulate"),
            ):
                frozen = freeze_private_starsim_cohort(
                    cohort_id="private-pilot-test",
                    output_directory=cohort_path,
                    authentication_key_file=key_path,
                    episodes=7,
                )

            public = frozen.as_public_dict()
            self.assertEqual(set(public), {"public_descriptor", "paths"})
            descriptor = public["public_descriptor"]
            self.assertEqual(descriptor["episode_count"], 7)
            self.assertEqual(descriptor["backend"], "starsim")
            self.assertEqual(descriptor["design"], "balanced_five_mode")
            self.assertFalse(descriptor["blind_scientific_validation_run"])
            self.assertFalse(descriptor["docker_execution_run"])
            self.assertEqual(
                descriptor["profile_source"],
                "bundled_package_profile_only",
            )
            self.assertEqual(sum(descriptor["mode_counts"].values()), 7)
            self.assertEqual(
                set(descriptor["mode_counts"]),
                set(LIVE_FAMILY_TO_MODE.values()),
            )
            self.assertLessEqual(
                max(descriptor["mode_counts"].values())
                - min(descriptor["mode_counts"].values()),
                1,
            )
            self.assertEqual(len(public["paths"]["packs"]), 7)
            self.assertNotIn("authentication.key", json.dumps(public))
            self.assertNotIn("seed", json.dumps(public).lower())
            self.assertNotIn("episode_secret", json.dumps(public))
            self.assertNotIn("commitment_nonce", json.dumps(public))

            self.assertEqual(cohort_path.stat().st_mode & 0o777, 0o700)
            self.assertFalse((cohort_path / ".freeze-incomplete").exists())
            self.assertEqual(frozen.manifest_path.stat().st_mode & 0o777, 0o600)
            self.assertTrue(
                all(path.stat().st_mode & 0o777 == 0o600 for path in frozen.pack_paths)
            )

            manifest = PrivateEpisodeCohortManifest.read(
                frozen.manifest_path, AUTHENTICATION_KEY
            )
            packs = tuple(
                PrivateEpisodePack.read(path, AUTHENTICATION_KEY)
                for path in frozen.pack_paths
            )
            self.assertEqual(len(packs), 7)
            self.assertEqual(len({pack.seed for pack in packs}), 7)
            self.assertEqual(len({pack.episode_secret for pack in packs}), 7)
            self.assertEqual(len({pack.commitment_nonce for pack in packs}), 7)
            all_private_bytes = (
                {pack.episode_secret for pack in packs}
                | {pack.commitment_nonce for pack in packs}
                | {manifest.manifest_nonce}
            )
            self.assertEqual(len(all_private_bytes), 15)
            self.assertEqual({pack.backend for pack in packs}, {"starsim"})
            family_counts = {
                family: sum(pack.family == family for pack in packs)
                for family in LIVE_FAMILY_TO_MODE
            }
            self.assertEqual(sum(family_counts.values()), 7)
            self.assertLessEqual(
                max(family_counts.values()) - min(family_counts.values()), 1
            )
            for pack in packs:
                manifest.assert_contains(pack)
                launch = pack.launch_kwargs(
                    expected_generator_fingerprint=descriptor[
                        "generator_fingerprint"
                    ],
                    cohort_manifest=manifest,
                    expected_pack_set_commitment=descriptor[
                        "pack_set_commitment"
                    ],
                )
                self.assertEqual(launch["backend"], "starsim")

    def test_freeze_fifty_ltc_episodes_is_exactly_balanced_without_simulation(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            key_path = root / "authentication.key"
            cohort_path = root / "private-ltc-cohort"
            _write_key(key_path)

            with patch.object(
                LtcStarsimV3Backend,
                "create_runtime",
                side_effect=AssertionError("freezer must not simulate"),
            ), patch.object(
                LtcStarsimV3Backend,
                "create_episode",
                side_effect=AssertionError("freezer must not simulate"),
            ):
                frozen = freeze_private_starsim_cohort(
                    cohort_id="private-ltc-fifty",
                    output_directory=cohort_path,
                    authentication_key_file=key_path,
                    episodes=50,
                    backend="starsim-ltc-v3",
                )

            descriptor = frozen.public_descriptor
            self.assertEqual(descriptor["episode_count"], 50)
            self.assertEqual(descriptor["backend"], "starsim-ltc-v3")
            self.assertEqual(set(descriptor["mode_counts"].values()), {10})

            packs = tuple(
                PrivateEpisodePack.read(path, AUTHENTICATION_KEY)
                for path in frozen.pack_paths
            )
            self.assertEqual(len(packs), 50)
            self.assertEqual({pack.backend for pack in packs}, {"starsim-ltc-v3"})
            self.assertEqual(
                {
                    family: sum(pack.family == family for pack in packs)
                    for family in LIVE_FAMILY_TO_MODE
                },
                {family: 10 for family in LIVE_FAMILY_TO_MODE},
            )

    def test_freeze_rejects_backend_outside_strict_allowlist(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            key_path = root / "authentication.key"
            cohort_path = root / "unsupported-cohort"
            _write_key(key_path)

            with self.assertRaisesRegex(
                CohortFreezeError, "Unsupported cohort backend"
            ):
                freeze_private_starsim_cohort(
                    cohort_id="unsupported-backend",
                    output_directory=cohort_path,
                    authentication_key_file=key_path,
                    episodes=5,
                    backend="reference",
                )
            self.assertFalse(cohort_path.exists())

    def test_owner_only_external_key_and_no_overwrite_are_required(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            key_path = root / "authentication.key"
            _write_key(key_path)
            os.chmod(key_path, 0o644)
            with self.assertRaisesRegex(CohortFreezeError, "owner-only"):
                freeze_private_starsim_cohort(
                    cohort_id="bad-key-mode",
                    output_directory=root / "bad-mode-cohort",
                    authentication_key_file=key_path,
                    episodes=5,
                )

            _write_key(key_path, b"too short")
            with self.assertRaisesRegex(CohortFreezeError, "32-4096"):
                freeze_private_starsim_cohort(
                    cohort_id="short-key",
                    output_directory=root / "short-key-cohort",
                    authentication_key_file=key_path,
                    episodes=5,
                )

            _write_key(key_path)
            destination = root / "existing-cohort"
            destination.mkdir()
            sentinel = destination / "sentinel"
            sentinel.write_text("do not replace", encoding="utf-8")
            with self.assertRaisesRegex(CohortFreezeError, "must not already exist"):
                freeze_private_starsim_cohort(
                    cohort_id="no-overwrite",
                    output_directory=destination,
                    authentication_key_file=key_path,
                    episodes=5,
                )
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "do not replace")

            inside_key = destination / "inside.key"
            _write_key(inside_key)
            with self.assertRaisesRegex(CohortFreezeError, "outside"):
                freeze_private_starsim_cohort(
                    cohort_id="inside-key",
                    output_directory=destination,
                    authentication_key_file=inside_key,
                    episodes=5,
                )

class PrivateCohortCliTests(unittest.TestCase):
    def test_cli_defaults_to_one_hundred_episodes(self):
        args = build_parser().parse_args(
            [
                "freeze-private-cohort",
                "--cohort-id",
                "pilot",
                "--output-directory",
                "/tmp/not-created-by-parser",
                "--authentication-key-file",
                "/tmp/key-not-read-by-parser",
            ]
        )
        self.assertEqual(args.episodes, 100)
        self.assertEqual(args.backend, "starsim")

    def test_cli_rejects_backend_outside_strict_allowlist(self):
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            build_parser().parse_args(
                [
                    "freeze-private-cohort",
                    "--cohort-id",
                    "pilot",
                    "--output-directory",
                    "/tmp/not-created-by-parser",
                    "--authentication-key-file",
                    "/tmp/key-not-read-by-parser",
                    "--backend",
                    "reference",
                ]
            )

    def test_cli_forbids_external_candidate_profile_until_replay_supports_it(self):
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            build_parser().parse_args(
                [
                    "freeze-private-cohort",
                    "--cohort-id",
                    "pilot",
                    "--output-directory",
                    "/tmp/not-created-by-parser",
                    "--authentication-key-file",
                    "/tmp/key-not-read-by-parser",
                    "--candidate-profile",
                    "/tmp/not-loadable.json",
                ]
            )

    def test_cli_prints_only_public_descriptor_and_paths(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            key_path = root / "authentication.key"
            output_path = root / "cli-cohort"
            _write_key(key_path)
            stream = io.StringIO()
            with redirect_stdout(stream), patch.object(
                StarsimSurveillanceBackend,
                "create_runtime",
                side_effect=AssertionError("CLI freezer must not simulate"),
            ):
                status = main(
                    [
                        "freeze-private-cohort",
                        "--cohort-id",
                        "cli-private-pilot",
                        "--output-directory",
                        str(output_path),
                        "--authentication-key-file",
                        str(key_path),
                        "--episodes",
                        "5",
                        "--backend",
                        "starsim-ltc-v3",
                    ]
                )
            self.assertEqual(status, 0)
            output = json.loads(stream.getvalue())
            self.assertEqual(set(output), {"public_descriptor", "paths"})
            self.assertFalse(
                output["public_descriptor"]["blind_scientific_validation_run"]
            )
            self.assertFalse(output["public_descriptor"]["docker_execution_run"])
            self.assertEqual(
                output["public_descriptor"]["backend"], "starsim-ltc-v3"
            )
            self.assertNotIn(str(key_path), stream.getvalue())
            self.assertNotIn(AUTHENTICATION_KEY.decode(), stream.getvalue())


if __name__ == "__main__":
    unittest.main()
