from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import socket
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import epiagentbench.trusted.hardened_runner as runner
from epiagentbench.trusted.episode_pack import (
    EpisodePackError,
    PrivateEpisodeCohortManifest,
    PrivateEpisodePack,
)
from epiagentbench.trusted.hardened_runner import (
    HardenedRunnerError,
    HardenedRunnerUnavailableError,
    execute_frozen_episode,
    load_hardened_snapshot_plan,
)
from epiagentbench.trusted.hardened_snapshot import (
    AuthenticatedTrace,
    HardenedSnapshotPlan,
    InferenceProxyPolicy,
    SnapshotLimits,
)
from epiagentbench.trusted.service import SecureEpisodeSession


FINGERPRINT = "sha256:" + "a" * 64
IMAGE = "registry.example/agent@sha256:" + "1" * 64
PACK_KEY = b"pack authentication key".ljust(32, b"!")
RECEIPT_KEY = b"receipt authentication key".ljust(32, b"!")


def make_pack(**changes):
    values = {
        "cohort_id": "private-pilot-1",
        "episode_index": 2,
        "backend": "reference",
        "family": "restaurant_point_source",
        "seed": 173,
        "generator_fingerprint": FINGERPRINT,
        "episode_secret": b"episode secret".ljust(32, b"!"),
        "commitment_nonce": b"commitment nonce".ljust(32, b"!"),
    }
    values.update(changes)
    return PrivateEpisodePack.create(**values)


def make_plan(broker: Path, *, network_mode: str = "none"):
    policy = InferenceProxyPolicy(
        policy_id="disabled-offline-policy",
        network_name="eab-private-run-2",
        proxy_url="http://inference-proxy:8080",
        allowed_provider_hosts=("api.openai.com",),
        allowed_decoded_paths=("/v1/responses",),
        allowed_models=("gpt-5.6-sol",),
        max_calls=32,
        max_total_tokens=65_536,
    )
    return HardenedSnapshotPlan(
        run_id="private-run-2",
        image=IMAGE,
        broker_directory=str(broker),
        agent_argv=("/opt/agent/run", "--one-episode"),
        proxy_policy=policy,
        limits=SnapshotLimits(timeout_seconds=60),
        uid=os.geteuid() or 65_532,
        gid=os.getegid() or 65_532,
        network_mode=network_mode,
    )


def write_private_artifacts(directory: Path, pack: PrivateEpisodePack):
    manifest = PrivateEpisodeCohortManifest.create(
        (pack,), manifest_nonce=b"manifest nonce".ljust(32, b"!")
    )
    pack_path = directory / "episode.pack"
    manifest_path = directory / "cohort.manifest"
    pack.write(pack_path, PACK_KEY)
    manifest_path.write_bytes(manifest.seal(PACK_KEY))
    os.chmod(manifest_path, 0o600)
    return manifest, pack_path, manifest_path


class HardenedFrozenRunnerTests(unittest.TestCase):
    def setUp(self):
        fingerprint = patch.object(
            runner, "compute_generator_fingerprint", return_value=FINGERPRINT
        )
        fingerprint.start()
        self.addCleanup(fingerprint.stop)

    def test_plan_loader_requires_exact_schema_and_published_commitment(self):
        with TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            plan = make_plan(directory / "broker")
            path = directory / "plan.json"
            path.write_text(json.dumps(plan.as_dict(), sort_keys=True))
            self.assertEqual(
                load_hardened_snapshot_plan(
                    path, expected_commitment=plan.commitment
                ),
                plan,
            )

            changed = plan.as_dict()
            changed["isolation_claims"]["linux_execution_verified"] = True
            path.write_text(json.dumps(changed, sort_keys=True))
            with self.assertRaisesRegex(
                HardenedRunnerError, "unsupported policy fields"
            ):
                load_hardened_snapshot_plan(
                    path, expected_commitment=plan.commitment
                )

    def test_integrated_runner_unseals_executes_scores_and_receipts(self):
        with TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            pack = make_pack()
            manifest, pack_path, manifest_path = write_private_artifacts(
                directory, pack
            )
            broker = directory / "broker"
            receipt_path = directory / "run.receipt"
            plan = make_plan(broker)
            session = Mock(spec=SecureEpisodeSession)
            process = Mock()
            process.returncode = 0

            def launch(**kwargs):
                public_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                public_socket.bind(kwargs["public_socket_path"])
                public_socket.close()
                return session

            scorecard = {"valid": True, "total": 0.75, "violations": []}
            submission = {"outbreak_assessment": "confirmed"}
            with (
                patch.object(runner.sys, "platform", "linux"),
                patch.object(runner.shutil, "which", return_value="/usr/bin/docker"),
                patch.object(runner, "launch_socket_episode", side_effect=launch),
                patch.object(
                    runner,
                    "_verify_broker_boundary",
                    wraps=runner._verify_broker_boundary,
                ) as verify_broker,
                patch.object(runner.subprocess, "Popen", return_value=process) as popen,
                patch.object(
                    runner,
                    "_collect_bounded",
                    return_value=(b'{"outbreak_assessment":"confirmed"}', b"log", "ok"),
                ),
                patch.object(
                    runner,
                    "_score_agent_output",
                    return_value=(submission, scorecard),
                ),
            ):
                result = execute_frozen_episode(
                    plan=plan,
                    pack_path=pack_path,
                    manifest_path=manifest_path,
                    pack_authentication_key=PACK_KEY,
                    expected_pack_set_commitment=manifest.pack_set_commitment,
                    expected_generator_fingerprint=FINGERPRINT,
                    receipt_authentication_key=RECEIPT_KEY,
                    receipt_path=receipt_path,
                )

            command = popen.call_args.args[0]
            joined = " ".join(command)
            self.assertIn("--network none", joined)
            self.assertIn("--read-only", command)
            self.assertIn("--cap-drop ALL", joined)
            mounts = [
                command[index + 1]
                for index, value in enumerate(command[:-1])
                if value == "--mount"
            ]
            self.assertEqual(len(mounts), 1)
            self.assertIn("dst=/broker,readonly", mounts[0])
            self.assertNotIn(str(pack_path), joined)
            self.assertNotIn(str(manifest_path), joined)
            self.assertNotIn("docker.sock", joined)
            self.assertNotIn("HTTP_PROXY=", joined)
            self.assertFalse(broker.exists())
            self.assertEqual(verify_broker.call_count, 2)
            self.assertEqual(receipt_path.stat().st_mode & 0o777, 0o600)
            self.assertTrue(
                AuthenticatedTrace.verify_receipt(result.receipt, RECEIPT_KEY)
            )
            self.assertEqual(
                set(result.receipt["artifact_hashes"]),
                {"execution", "scorecard", "stderr", "stdout", "submission"},
            )
            self.assertFalse(
                result.receipt["isolation_claims"]["linux_execution_verified"]
            )
            session.close.assert_called_once_with()

            tampered = deepcopy(result.receipt)
            tampered["artifact_hashes"]["scorecard"] = "sha256:" + "f" * 64
            self.assertFalse(
                AuthenticatedTrace.verify_receipt(tampered, RECEIPT_KEY)
            )

    def test_tampered_pack_fails_before_evaluator_or_docker(self):
        with TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            pack = make_pack()
            manifest, pack_path, manifest_path = write_private_artifacts(
                directory, pack
            )
            value = json.loads(pack_path.read_bytes())
            value["payload"]["seed"] += 1
            pack_path.write_text(json.dumps(value))
            os.chmod(pack_path, 0o600)
            plan = make_plan(directory / "broker")
            with (
                patch.object(runner.sys, "platform", "linux"),
                patch.object(runner.shutil, "which", return_value="/usr/bin/docker"),
                patch.object(runner, "launch_socket_episode") as launch,
                patch.object(runner.subprocess, "Popen") as popen,
            ):
                with self.assertRaisesRegex(EpisodePackError, "authentication failed"):
                    execute_frozen_episode(
                        plan=plan,
                        pack_path=pack_path,
                        manifest_path=manifest_path,
                        pack_authentication_key=PACK_KEY,
                        expected_pack_set_commitment=manifest.pack_set_commitment,
                        expected_generator_fingerprint=FINGERPRINT,
                        receipt_authentication_key=RECEIPT_KEY,
                        receipt_path=directory / "receipt",
                    )
            launch.assert_not_called()
            popen.assert_not_called()

    def test_substituted_authentic_pack_fails_frozen_membership_gate(self):
        with TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            frozen = make_pack()
            manifest, _, manifest_path = write_private_artifacts(directory, frozen)
            substituted = make_pack(seed=999)
            substitute_path = directory / "substitute.pack"
            substituted.write(substitute_path, PACK_KEY)
            plan = make_plan(directory / "broker")
            with (
                patch.object(runner.sys, "platform", "linux"),
                patch.object(runner.shutil, "which", return_value="/usr/bin/docker"),
                patch.object(runner, "launch_socket_episode") as launch,
            ):
                with self.assertRaisesRegex(
                    EpisodePackError, "outside the frozen cohort"
                ):
                    execute_frozen_episode(
                        plan=plan,
                        pack_path=substitute_path,
                        manifest_path=manifest_path,
                        pack_authentication_key=PACK_KEY,
                        expected_pack_set_commitment=manifest.pack_set_commitment,
                        expected_generator_fingerprint=FINGERPRINT,
                        receipt_authentication_key=RECEIPT_KEY,
                        receipt_path=directory / "receipt",
                    )
            launch.assert_not_called()

    def test_installed_generator_is_recomputed_before_evaluator_or_docker(self):
        with TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            pack = make_pack()
            manifest, pack_path, manifest_path = write_private_artifacts(
                directory, pack
            )
            plan = make_plan(directory / "broker")
            with (
                patch.object(runner.sys, "platform", "linux"),
                patch.object(runner.shutil, "which", return_value="/usr/bin/docker"),
                patch.object(
                    runner,
                    "compute_generator_fingerprint",
                    return_value="sha256:" + "b" * 64,
                ),
                patch.object(runner, "launch_socket_episode") as launch,
                patch.object(runner.subprocess, "Popen") as popen,
            ):
                with self.assertRaisesRegex(
                    HardenedRunnerError, "Installed generator fingerprint differs"
                ):
                    execute_frozen_episode(
                        plan=plan,
                        pack_path=pack_path,
                        manifest_path=manifest_path,
                        pack_authentication_key=PACK_KEY,
                        expected_pack_set_commitment=manifest.pack_set_commitment,
                        expected_generator_fingerprint=FINGERPRINT,
                        receipt_authentication_key=RECEIPT_KEY,
                        receipt_path=directory / "receipt",
                    )
            launch.assert_not_called()
            popen.assert_not_called()

    def test_online_plan_and_non_linux_host_fail_closed(self):
        with TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            online = make_plan(directory / "broker", network_mode="inference_proxy")
            with self.assertRaisesRegex(HardenedRunnerError, "policy enforcement"):
                runner._validate_execution_boundary(online, "docker")

            offline = make_plan(directory / "broker")
            with patch.object(runner.sys, "platform", "darwin"):
                with self.assertRaisesRegex(
                    HardenedRunnerUnavailableError, "Linux only"
                ):
                    runner._validate_execution_boundary(offline, "docker")

    def test_private_artifacts_reject_group_readable_permissions(self):
        with TemporaryDirectory() as raw_directory:
            path = Path(raw_directory) / "private.pack"
            path.write_bytes(b"secret")
            os.chmod(path, 0o640)
            with self.assertRaisesRegex(EpisodePackError, "Unsafe"):
                runner._read_private_file(path)

    def test_broker_boundary_requires_exact_socket_type_owner_mode_and_contents(self):
        with TemporaryDirectory() as raw_directory:
            directory = Path(raw_directory)
            broker = directory / "broker"
            broker.mkdir(mode=0o700)
            socket_path = broker / "episode.sock"
            public_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            public_socket.bind(str(socket_path))
            public_socket.close()
            plan = make_plan(broker)
            runner._grant_broker_access(broker, socket_path, plan)
            runner._verify_broker_boundary(broker, socket_path, plan)

            extra = broker / "smuggled-private-file"
            extra.write_text("unexpected")
            with self.assertRaisesRegex(HardenedRunnerError, "tampered"):
                runner._verify_broker_boundary(broker, socket_path, plan)
            extra.unlink()

            os.chmod(socket_path, 0o660)
            with self.assertRaisesRegex(HardenedRunnerError, "tampered"):
                runner._verify_broker_boundary(broker, socket_path, plan)


if __name__ == "__main__":
    unittest.main()
