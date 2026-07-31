from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
from pathlib import Path
import unittest


class V19SupersessionTests(unittest.TestCase):
    RUNTIME_SHA256 = (
        "sha256:2a9a157433db2892b89c7e76292d076fbf09699e4a93a1babf01267963f449aa"
    )
    MANIFEST_SHA256 = (
        "sha256:87f1437cf25d4a607591de32a09f0394d62c0b0eae8b8a09ef1bf10d66e4230a"
    )
    V20_ACKNOWLEDGEMENT = (
        "I acknowledge the replacement six-call v20 preflight and "
        "300-assignment production run, including unbounded Codex/Cursor "
        "provider spend and up to $590 total Claude spend across the failed "
        "v2 preflight, failed v5 preflight, failed v6 authentication "
        "bootstrap, failed v7 preflight, failed v8 production run, v9 "
        "preflight and failed production run, the abandoned zero-model-call "
        "v10 precommitment, the failed zero-model-call v11 authentication "
        "bootstrap, the abandoned zero-model-call v12 precommitment, the "
        "abandoned zero-model-call v13 precommitment, the failed v14 "
        "preflight, the failed zero-model-call v15 pre-claim preparation, "
        "the failed v16 preflight, the failed zero-model-call v17 pre-start "
        "runtime-cache-environment refusal, the failed v18 preflight, the "
        "failed zero-model-call v19 authentication setup, and the v20 "
        "preflight and production run."
    )
    V20_ACKNOWLEDGEMENT_SHA256 = (
        "sha256:c192557a25bb6050be27b3ce2af60837c8a966a47368c67d2d6972a0dc9e73e7"
    )

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.superseded = json.loads(
            (
                cls.root
                / "results/development-matched-50x6-v19.superseded.json"
            ).read_bytes()
        )
        cls.manifest = json.loads(
            (
                cls.root
                / "results/development-matched-50x6-v19.manifest.json"
            ).read_bytes()
        )

    @staticmethod
    def _keys(payload: object) -> set[str]:
        observed: set[str] = set()
        if isinstance(payload, Mapping):
            for key, value in payload.items():
                observed.add(str(key))
                observed.update(V19SupersessionTests._keys(value))
        elif isinstance(payload, Sequence) and not isinstance(
            payload, (str, bytes, bytearray)
        ):
            for value in payload:
                observed.update(V19SupersessionTests._keys(value))
        return observed

    def test_supersession_binds_exact_public_v19_artifacts(self) -> None:
        runtime = (
            self.root / "results/development-matched-50x6-v19.runtime.json"
        )
        manifest = (
            self.root / "results/development-matched-50x6-v19.manifest.json"
        )
        self.assertEqual(
            "sha256:" + hashlib.sha256(runtime.read_bytes()).hexdigest(),
            self.RUNTIME_SHA256,
        )
        self.assertEqual(
            "sha256:" + hashlib.sha256(manifest.read_bytes()).hexdigest(),
            self.MANIFEST_SHA256,
        )
        self.assertEqual(
            self.superseded["runtime_receipt_file_sha256"],
            self.RUNTIME_SHA256,
        )
        self.assertEqual(
            self.superseded["manifest_file_sha256"],
            self.MANIFEST_SHA256,
        )
        self.assertEqual(
            self.superseded["original_precommitment_sha256"],
            self.manifest["precommitment_sha256"],
        )
        self.assertEqual(
            self.superseded[
                "required_spend_acknowledgement_text_sha256"
            ],
            self.manifest["run_contract"]["spend_authorization"][
                "required_acknowledgement_text_sha256"
            ],
        )

    def test_v19_is_terminal_zero_model_and_not_resumable(self) -> None:
        self.assertEqual(
            self.superseded["schema_version"],
            "epiagentbench.panel_supersession.v11",
        )
        self.assertEqual(
            self.superseded["status"],
            "failed_zero_model_authentication_setup",
        )
        self.assertEqual(
            self.superseded["authentication_terminal_state"],
            "terminal_failed",
        )
        self.assertEqual(
            self.superseded["audited_root_cause_code"],
            "foreground_authentication_runtime_cache_not_self_supplied",
        )
        self.assertEqual(
            self.superseded["corrected_attempt_disposition"],
            "cancelled_after_at_most_once_audit",
        )
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
        self.assertEqual(
            self.superseded["v19_conservative_claude_ceiling_added_usd"],
            0,
        )
        for field in (
            "resumption_permitted",
            "v19_cohort_reuse_permitted",
            "v19_key_or_namespace_reuse_permitted",
            "provider_credentials_created",
            "public_authentication_receipt_created",
            "public_preflight_receipt_created",
            "public_results_artifact_created",
            "results_released",
            "scores_released",
            "traces_released",
        ):
            self.assertIs(self.superseded[field], False)

    def test_v20_contains_the_required_repair(self) -> None:
        self.assertEqual(
            self.superseded["replacement_panel_id"],
            "development-matched-50x6-v20",
        )
        requirements = set(self.superseded["replacement_requirements"])
        self.assertTrue(
            {
                (
                    "explicit_runtime_cache_directory_with_internal_"
                    "environment_installation"
                ),
                "exact_runtime_cache_environment_restoration",
                (
                    "durable_authentication_ceremony_claim_before_live_"
                    "attestation"
                ),
                "terminal_allowlisted_pre_provider_integrity_incident",
                "second_authentication_rejected_after_terminal_incident",
                "authentication_setup_schema_v3",
                "persistent_supervisor_contract_schema_v9",
                "launchd_config_schema_v12",
                "persistent_supervisor_execution_protocol_v6",
            }.issubset(requirements)
        )
        v20_manifest = json.loads(
            (
                self.root
                / "results/development-matched-50x6-v20.manifest.json"
            ).read_bytes()
        )
        launcher = (
            self.root / "src/epiagentbench/launchd_agent.py"
        ).read_text(encoding="utf-8")
        self.assertEqual(
            v20_manifest["panel_id"], "development-matched-50x6-v20"
        )
        self.assertEqual(
            v20_manifest["run_contract"]["authentication_setup"][
                "schema_version"
            ],
            "epiagentbench.authentication_setup.v3",
        )
        self.assertIn(
            '_SCHEMA = "epiagentbench.launchd_agent.v13"', launcher
        )
        self.assertIn(
            '_PROTOCOL_VERSION = "persistent-supervisor-v7"', launcher
        )

    def test_v20_acknowledgement_and_budget_are_consistent(self) -> None:
        self.assertEqual(
            "sha256:"
            + hashlib.sha256(
                self.V20_ACKNOWLEDGEMENT.encode("utf-8")
            ).hexdigest(),
            self.V20_ACKNOWLEDGEMENT_SHA256,
        )
        v20_manifest = json.loads(
            (
                self.root
                / "results/development-matched-50x6-v20.manifest.json"
            ).read_bytes()
        )
        self.assertEqual(
            v20_manifest["run_contract"]["spend_authorization"][
                "required_acknowledgement_text_sha256"
            ],
            self.V20_ACKNOWLEDGEMENT_SHA256,
        )

        readme = (self.root / "README.md").read_text(encoding="utf-8")
        runbook = (self.root / "docs/V20_RUNBOOK.md").read_text(
            encoding="utf-8"
        )
        self.assertNotIn(self.V20_ACKNOWLEDGEMENT, readme)
        self.assertIn(self.V20_ACKNOWLEDGEMENT, runbook)
        self.assertIn(self.V20_ACKNOWLEDGEMENT_SHA256, runbook)
        for document in (runbook,):
            self.assertIn("$510", document)
            self.assertIn("$80", document)
            self.assertIn("$590", document)
        self.assertIn("$600", readme)

    def test_v19_runbook_is_terminal_and_points_to_v20(self) -> None:
        runbook = (self.root / "docs/V19_RUNBOOK.md").read_text(
            encoding="utf-8"
        )
        self.assertTrue(runbook.startswith("> [!CAUTION]\n"))
        self.assertIn(
            "**TERMINAL AND SUPERSEDED — DO NOT EXECUTE THIS RUNBOOK.**",
            runbook,
        )
        self.assertIn(
            "../results/development-matched-50x6-v19.superseded.json",
            runbook,
        )
        self.assertIn("[V20 runbook](V20_RUNBOOK.md)", runbook)

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
        ):
            self.assertNotIn(canary, encoded)


if __name__ == "__main__":
    unittest.main()
