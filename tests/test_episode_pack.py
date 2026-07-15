from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from epiagentbench.trusted.episode_pack import (
    EpisodePackError,
    PrivateEpisodeCohortManifest,
    PrivateEpisodePack,
)
from epiagentbench.trusted.service import launch_secure_episode


FINGERPRINT = "sha256:" + "a" * 64
AUTH_KEY = b"pack authentication key".ljust(32, b"!")


def make_pack(**changes):
    values = {
        "cohort_id": "pilot-2026-07",
        "episode_index": 3,
        "backend": "reference",
        "family": "restaurant_point_source",
        "seed": 19,
        "generator_fingerprint": FINGERPRINT,
        "episode_secret": b"episode secret".ljust(32, b"!"),
        "commitment_nonce": b"commitment nonce".ljust(32, b"!"),
    }
    values.update(changes)
    return PrivateEpisodePack.create(**values)


class PrivateEpisodePackTests(unittest.TestCase):
    def test_pack_replays_a_fresh_evaluator_exactly(self):
        pack = make_pack()
        manifest = PrivateEpisodeCohortManifest.create(
            (pack,), manifest_nonce=b"manifest nonce".ljust(32, b"!")
        )
        launch = pack.launch_kwargs(
            expected_generator_fingerprint=FINGERPRINT,
            cohort_manifest=manifest,
            expected_pack_set_commitment=manifest.pack_set_commitment,
        )
        first_session, first_client = launch_secure_episode(**launch)
        second_session, second_client = launch_secure_episode(**launch)
        try:
            self.assertEqual(first_client.manifest, second_client.manifest)
            self.assertEqual(
                first_client.initial_observations(),
                second_client.initial_observations(),
            )
        finally:
            first_client.close()
            second_client.close()
            first_session.close()
            second_session.close()

    def test_commitment_hides_generation_inputs_from_public_descriptor(self):
        pack = make_pack()
        descriptor = json.dumps(pack.public_descriptor, sort_keys=True)
        self.assertIn(pack.commitment, descriptor)
        self.assertNotIn(str(pack.seed), descriptor)
        self.assertNotIn(str(pack.family), descriptor)
        self.assertNotIn("episode_secret", descriptor)
        self.assertNotIn("episode_index", descriptor)
        changed = make_pack(seed=20)
        self.assertNotEqual(pack.commitment, changed.commitment)

    def test_authenticated_round_trip_and_tamper_rejection(self):
        pack = make_pack()
        sealed = pack.seal(AUTH_KEY)
        self.assertEqual(PrivateEpisodePack.unseal(sealed, AUTH_KEY), pack)
        value = json.loads(sealed)
        value["payload"]["seed"] += 1
        tampered = json.dumps(value, separators=(",", ":")).encode()
        with self.assertRaisesRegex(EpisodePackError, "authentication failed"):
            PrivateEpisodePack.unseal(tampered, AUTH_KEY)

    def test_private_file_is_owner_only_and_rejects_broad_permissions(self):
        pack = make_pack()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "episode.pack"
            pack.write(path, AUTH_KEY)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(PrivateEpisodePack.read(path, AUTH_KEY), pack)
            os.chmod(path, 0o644)
            with self.assertRaisesRegex(EpisodePackError, "Unsafe"):
                PrivateEpisodePack.read(path, AUTH_KEY)

    def test_write_never_removes_an_existing_destination(self):
        pack = make_pack()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "already-there.pack"
            path.write_bytes(b"do not replace")
            with self.assertRaises(FileExistsError):
                pack.write(path, AUTH_KEY)
            self.assertEqual(path.read_bytes(), b"do not replace")

    def test_generator_fingerprint_is_a_replay_gate(self):
        pack = make_pack()
        pack.assert_generator(FINGERPRINT)
        with self.assertRaisesRegex(EpisodePackError, "fingerprint mismatch"):
            pack.assert_generator("sha256:" + "b" * 64)

    def test_authenticated_manifest_freezes_exact_pack_set(self):
        first = make_pack()
        second = make_pack(episode_index=4, seed=20)
        manifest = PrivateEpisodeCohortManifest.create(
            (second, first), manifest_nonce=b"manifest nonce".ljust(32, b"!")
        )
        self.assertEqual(
            tuple(index for index, _ in manifest.episodes), (3, 4)
        )
        sealed = manifest.seal(AUTH_KEY)
        opened = PrivateEpisodeCohortManifest.unseal(sealed, AUTH_KEY)
        self.assertEqual(opened, manifest)
        self.assertEqual(
            opened.public_descriptor["pack_set_commitment"],
            manifest.pack_set_commitment,
        )

        tampered = json.loads(sealed)
        tampered["payload"]["episodes"].pop()
        with self.assertRaisesRegex(EpisodePackError, "authentication failed"):
            PrivateEpisodeCohortManifest.unseal(
                json.dumps(tampered, separators=(",", ":")).encode(), AUTH_KEY
            )

    def test_manifest_file_is_owner_only_authenticated_and_no_overwrite(self):
        manifest = PrivateEpisodeCohortManifest.create((make_pack(),))
        with TemporaryDirectory() as directory:
            path = Path(directory) / "cohort.manifest"
            manifest.write(path, AUTH_KEY)
            original = path.read_bytes()
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(
                PrivateEpisodeCohortManifest.read(path, AUTH_KEY), manifest
            )
            with self.assertRaises(FileExistsError):
                manifest.write(path, AUTH_KEY)
            self.assertEqual(path.read_bytes(), original)
            os.chmod(path, 0o644)
            with self.assertRaisesRegex(EpisodePackError, "Unsafe"):
                PrivateEpisodeCohortManifest.read(path, AUTH_KEY)

    def test_launch_requires_pinned_generator_set_and_exact_membership(self):
        pack = make_pack()
        manifest = PrivateEpisodeCohortManifest.create((pack,))
        with self.assertRaisesRegex(EpisodePackError, "fingerprint mismatch"):
            pack.launch_kwargs(
                expected_generator_fingerprint="sha256:" + "b" * 64,
                cohort_manifest=manifest,
                expected_pack_set_commitment=manifest.pack_set_commitment,
            )
        with self.assertRaisesRegex(EpisodePackError, "pack-set commitment"):
            pack.launch_kwargs(
                expected_generator_fingerprint=FINGERPRINT,
                cohort_manifest=manifest,
                expected_pack_set_commitment="sha256:" + "c" * 64,
            )

        substituted = make_pack(seed=21)
        with self.assertRaisesRegex(EpisodePackError, "outside the frozen cohort"):
            substituted.launch_kwargs(
                expected_generator_fingerprint=FINGERPRINT,
                cohort_manifest=manifest,
                expected_pack_set_commitment=manifest.pack_set_commitment,
            )


if __name__ == "__main__":
    unittest.main()
