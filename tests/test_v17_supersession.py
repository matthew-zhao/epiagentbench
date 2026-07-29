from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
from pathlib import Path
import unittest


class V17SupersessionTests(unittest.TestCase):
    PUBLIC_FILE_HASHES = {
        "results/development-matched-50x6-v17.runtime.json": (
            "sha256:e23a819482146111270866a32b7b98390c9e58e54437cf024a8457b006237442"
        ),
        "results/development-matched-50x6-v17.manifest.json": (
            "sha256:c3e9969cb945f907a5955dfb1ae710eff4f33b16e9b93f1ffb5106ddf6893a77"
        ),
        "results/development-matched-50x6-v17.authentication.json": (
            "sha256:57a132d31f8b98d4085f019580706d555144d764631a24cafeb4ed75e1316d20"
        ),
    }
    PUBLIC_COMMITS = {
        "runtime_receipt_commit": (
            "7a53d66d25c038caae2152d880c0f8ea176fdbe4"
        ),
        "manifest_commit": (
            "3f59ce133a29c65116acca692ffe6ac6b2aec387"
        ),
        "authentication_receipt_commit": (
            "9e5455351ef68494181d3e8144384d910c30ebd2"
        ),
    }

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.superseded = json.loads(
            (
                cls.root
                / "results/development-matched-50x6-v17.superseded.json"
            ).read_bytes()
        )

    @staticmethod
    def _keys(payload: object) -> set[str]:
        observed: set[str] = set()
        if isinstance(payload, Mapping):
            for key, value in payload.items():
                observed.add(str(key))
                observed.update(V17SupersessionTests._keys(value))
        elif isinstance(payload, Sequence) and not isinstance(
            payload, (str, bytes, bytearray)
        ):
            for value in payload:
                observed.update(V17SupersessionTests._keys(value))
        return observed

    def test_supersession_binds_exact_public_v17_artifacts(self) -> None:
        for relative, expected in self.PUBLIC_FILE_HASHES.items():
            observed = "sha256:" + hashlib.sha256(
                (self.root / relative).read_bytes()
            ).hexdigest()
            self.assertEqual(observed, expected)
        self.assertEqual(
            self.superseded["runtime_receipt_file_sha256"],
            self.PUBLIC_FILE_HASHES[
                "results/development-matched-50x6-v17.runtime.json"
            ],
        )
        self.assertEqual(
            self.superseded["manifest_file_sha256"],
            self.PUBLIC_FILE_HASHES[
                "results/development-matched-50x6-v17.manifest.json"
            ],
        )
        self.assertEqual(
            self.superseded["authentication_receipt_file_sha256"],
            self.PUBLIC_FILE_HASHES[
                "results/development-matched-50x6-v17.authentication.json"
            ],
        )
        for field, expected in self.PUBLIC_COMMITS.items():
            self.assertEqual(self.superseded[field], expected)

    def test_v17_stopped_before_irreversible_or_model_boundary(self) -> None:
        self.assertEqual(
            self.superseded["schema_version"],
            "epiagentbench.panel_supersession.v9",
        )
        self.assertEqual(
            self.superseded["status"],
            "failed_zero_model_pre_start_refusal",
        )
        self.assertEqual(self.superseded["start_cli_invocations"], 1)
        self.assertEqual(
            self.superseded["durable_start_request_state"],
            "not_requested",
        )
        self.assertIs(self.superseded["start_marker_written"], False)
        self.assertIs(self.superseded["launchctl_kickstart_invoked"], False)
        self.assertEqual(
            self.superseded["worker_state_after_refusal"], "not_started"
        )
        self.assertEqual(
            self.superseded["supervisor_state_after_refusal"],
            "not_started",
        )
        self.assertEqual(self.superseded["preflight_profiles_attempted"], 0)
        self.assertEqual(self.superseded["production_assignments_started"], 0)
        self.assertEqual(
            self.superseded["model_bearing_provider_call_exposure"],
            {"claude": 0, "codex": 0, "cursor": 0, "total": 0},
        )
        self.assertEqual(
            self.superseded[
                "model_bearing_provider_calls_conservatively_chargeable"
            ],
            0,
        )

    def test_v17_authentication_passed_but_refused_start_invoked_nothing(self) -> None:
        authentication = json.loads(
            (
                self.root
                / "results/development-matched-50x6-v17.authentication.json"
            ).read_bytes()
        )
        self.assertEqual(authentication["status"], "passed")
        self.assertEqual(authentication["model_calls_started"], 0)
        self.assertEqual(
            authentication["receipt_sha256"],
            self.superseded["authentication_receipt_sha256"],
        )
        self.assertEqual(
            self.superseded[
                "authentication_processes_started_by_refused_start"
            ],
            0,
        )
        self.assertEqual(
            self.superseded["provider_processes_started_by_refused_start"],
            0,
        )

    def test_v17_is_terminal_and_v18_contains_the_fix(self) -> None:
        self.assertIs(self.superseded["resumption_permitted"], False)
        self.assertIs(
            self.superseded["v17_cohort_reuse_permitted"], False
        )
        self.assertIs(
            self.superseded["v17_key_or_namespace_reuse_permitted"], False
        )
        requirements = set(self.superseded["replacement_requirements"])
        self.assertTrue(
            {
                "authenticated_runtime_cache_environment_self_supply",
                "exact_environment_restore_after_every_launcher_boundary",
                "launchd_config_schema_v10",
                "persistent_supervisor_execution_protocol_v4",
                "persistent_supervisor_contract_schema_v7",
                "atomic_create_once_publication",
            }.issubset(requirements)
        )
        launcher = (
            self.root / "src/epiagentbench/launchd_agent.py"
        ).read_text(encoding="utf-8")
        panel = (
            self.root / "src/epiagentbench/development_matched_panel.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            '_SCHEMA = "epiagentbench.launchd_agent.v11"', launcher
        )
        self.assertIn(
            '_PROTOCOL_VERSION = "persistent-supervisor-v5"', launcher
        )
        self.assertIn(
            "def _load_in_authenticated_runtime_environment", launcher
        )
        self.assertIn(
            "def _assert_authenticated_config_snapshot", launcher
        )
        self.assertIn(
            '"schema_version": "epiagentbench.persistent_supervisor_contract.v8"',
            panel,
        )

    def test_v17_runbook_is_terminal_and_points_to_v18(self) -> None:
        runbook = (self.root / "docs/V17_RUNBOOK.md").read_text(
            encoding="utf-8"
        )
        self.assertTrue(runbook.startswith("> [!CAUTION]\n"))
        self.assertIn(
            "**TERMINAL AND SUPERSEDED — DO NOT EXECUTE THIS RUNBOOK.**",
            runbook,
        )
        self.assertIn("Do not resume, repair, or reuse any V17", runbook)
        self.assertIn(
            "../results/development-matched-50x6-v17.superseded.json",
            runbook,
        )
        self.assertIn("[V18 runbook](V18_RUNBOOK.md)", runbook)

    def test_no_v17_preflight_or_results_and_no_release(self) -> None:
        self.assertFalse(
            (
                self.root
                / "results/development-matched-50x6-v17.preflight.json"
            ).exists()
        )
        self.assertFalse(
            (
                self.root / "results/development-matched-50x6-v17.json"
            ).exists()
        )
        for field in (
            "public_preflight_artifact_created",
            "public_results_artifact_created",
            "results_released",
            "scores_released",
            "traces_released",
        ):
            self.assertIs(self.superseded[field], False)

    def test_supersession_contains_no_sensitive_or_scored_payload(self) -> None:
        forbidden_keys = {
            "access_token",
            "api_key",
            "argv",
            "cache_directories",
            "credential_contents",
            "episode_id",
            "family",
            "oauth_state",
            "observation",
            "private_seed",
            "prompt",
            "provider_output",
            "raw_stderr",
            "raw_stdout",
            "refresh_token",
            "runtime_environment",
            "schedule",
            "schedule_nonce",
            "score",
            "stderr",
            "stdout",
            "trace",
            "trace_steps",
        }
        self.assertTrue(
            forbidden_keys.isdisjoint(self._keys(self.superseded))
        )
        encoded = json.dumps(self.superseded, sort_keys=True).lower()
        for canary in (
            "/home/",
            "/private/",
            "/users/",
            "auth.json",
            "credentials.json",
            "episode_0001",
            "panel-auth.key",
            "schedule_nonce_hex",
        ):
            self.assertNotIn(canary, encoded)


if __name__ == "__main__":
    unittest.main()
