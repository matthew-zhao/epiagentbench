from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
from pathlib import Path
import unittest


class V20SupersessionTests(unittest.TestCase):
    PUBLIC_FILE_HASHES = {
        "results/development-matched-50x6-v20.runtime.json": (
            "sha256:be8d3e10d4c719a436a4173464caea9a5a40d008828feb055d8f0ac0aebd199f"
        ),
        "results/development-matched-50x6-v20.manifest.json": (
            "sha256:e70d60c4599fc583190401769f9edeaa7c8264a2466f7d0b92282b220d38fc9a"
        ),
        "results/development-matched-50x6-v20.authentication.json": (
            "sha256:ac3377729c647d7c421649a020c93fabbb9a3324a70542de7aa25e13874606f0"
        ),
        "results/development-matched-50x6-v20.preflight.json": (
            "sha256:168137e071cb61421617498488f55471e01c645e48b4440fc4b63371071a4fbb"
        ),
    }
    PUBLIC_COMMITS = {
        "control_commit": "8f472268187a62697b7c86e79a94fd6a9e5e678a",
        "runtime_receipt_commit": (
            "1177e3ab89a7c0a7ddb1dd7fa1ab8d0cda9c7c1d"
        ),
        "manifest_commit": "7f5f73738ea2021fd4666a8e5db6a1cb409913ce",
        "authentication_receipt_commit": (
            "89a0cb40bfb08aabef0391446b843c0251b7a2a7"
        ),
        "preflight_execution_commit": (
            "89a0cb40bfb08aabef0391446b843c0251b7a2a7"
        ),
    }
    V21_ACKNOWLEDGEMENT = (
        "I acknowledge the replacement six-call v21 preflight and "
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
        "failed zero-model-call v19 authentication setup, the failed "
        "zero-model-call v20 preflight, and the v21 preflight and production "
        "run."
    )
    V21_ACKNOWLEDGEMENT_SHA256 = (
        "sha256:9d149c27986f0e35c9f4a5c40f9d315ac6ab1fcef1ef7eafc079832c2bbab1cc"
    )

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.runtime = json.loads(
            (
                cls.root
                / "results/development-matched-50x6-v20.runtime.json"
            ).read_bytes()
        )
        cls.manifest = json.loads(
            (
                cls.root
                / "results/development-matched-50x6-v20.manifest.json"
            ).read_bytes()
        )
        cls.authentication = json.loads(
            (
                cls.root
                / "results/development-matched-50x6-v20.authentication.json"
            ).read_bytes()
        )
        cls.preflight = json.loads(
            (
                cls.root
                / "results/development-matched-50x6-v20.preflight.json"
            ).read_bytes()
        )
        cls.superseded = json.loads(
            (
                cls.root
                / "results/development-matched-50x6-v20.superseded.json"
            ).read_bytes()
        )

    @staticmethod
    def _keys(payload: object) -> set[str]:
        observed: set[str] = set()
        if isinstance(payload, Mapping):
            for key, value in payload.items():
                observed.add(str(key))
                observed.update(V20SupersessionTests._keys(value))
        elif isinstance(payload, Sequence) and not isinstance(
            payload, (str, bytes, bytearray)
        ):
            for value in payload:
                observed.update(V20SupersessionTests._keys(value))
        return observed

    def test_supersession_has_closed_public_schema(self) -> None:
        self.assertEqual(
            set(self.superseded),
            {
                "audited_root_cause_code",
                "authentication_receipt_commit",
                "authentication_receipt_created",
                "authentication_receipt_file_sha256",
                "authentication_receipt_sha256",
                "cohort_retired",
                "control_commit",
                "development_only",
                "exact_subphase_recoverable_from_v20_public_receipt",
                "failed_model_invocation_state",
                "failed_profile_id",
                "historical_failure_reason",
                "historical_failure_stage",
                "historical_incident_code",
                "manifest_commit",
                "manifest_file_sha256",
                "model_bearing_provider_call_exposure",
                "model_bearing_provider_calls_conservatively_chargeable",
                "original_panel_id",
                "original_precommitment_sha256",
                "preflight_execution_commit",
                "preflight_profiles_attempted",
                "preflight_profiles_passed",
                "preflight_receipt_created",
                "preflight_receipt_file_sha256",
                "preflight_receipt_status",
                "production_assignments_started",
                "production_episodes_consumed",
                "public_results_artifact_created",
                "replacement_panel_id",
                "replacement_requirements",
                "required_spend_acknowledgement_text_sha256",
                "results_released",
                "resumption_permitted",
                "root_cause_evidence_level",
                "root_cause_scope",
                "runtime_receipt_commit",
                "runtime_receipt_file_sha256",
                "schema_version",
                "scores_released",
                "spend_acknowledgement_supplied",
                "spend_authorization_receipt_sha256",
                "spend_authorization_recorded",
                "status",
                "superseded_at_utc",
                "traces_released",
                "v20_cohort_reuse_permitted",
                "v20_conservative_claude_ceiling_added_usd",
                "v20_key_or_namespace_reuse_permitted",
            },
        )
        self.assertEqual(
            self.superseded["schema_version"],
            "epiagentbench.panel_supersession.v12",
        )
        self.assertRegex(
            self.superseded["superseded_at_utc"],
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$",
        )

    def test_supersession_binds_exact_public_v20_artifacts(self) -> None:
        for relative, expected in self.PUBLIC_FILE_HASHES.items():
            observed = "sha256:" + hashlib.sha256(
                (self.root / relative).read_bytes()
            ).hexdigest()
            self.assertEqual(observed, expected)
        self.assertEqual(
            self.superseded["runtime_receipt_file_sha256"],
            self.PUBLIC_FILE_HASHES[
                "results/development-matched-50x6-v20.runtime.json"
            ],
        )
        self.assertEqual(
            self.superseded["manifest_file_sha256"],
            self.PUBLIC_FILE_HASHES[
                "results/development-matched-50x6-v20.manifest.json"
            ],
        )
        self.assertEqual(
            self.superseded["authentication_receipt_file_sha256"],
            self.PUBLIC_FILE_HASHES[
                "results/development-matched-50x6-v20.authentication.json"
            ],
        )
        self.assertEqual(
            self.superseded["preflight_receipt_file_sha256"],
            self.PUBLIC_FILE_HASHES[
                "results/development-matched-50x6-v20.preflight.json"
            ],
        )
        for field, expected in self.PUBLIC_COMMITS.items():
            self.assertEqual(self.superseded[field], expected)
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
        self.assertEqual(
            self.superseded["authentication_receipt_sha256"],
            self.authentication["receipt_sha256"],
        )
        self.assertEqual(
            self.superseded["spend_authorization_receipt_sha256"],
            self.authentication["spend_authorization_receipt_sha256"],
        )

    def test_v20_failed_before_model_start_and_is_not_resumable(self) -> None:
        self.assertEqual(
            self.superseded["status"],
            "failed_zero_model_preflight_terminal_abort",
        )
        self.assertEqual(self.preflight["status"], "failed")
        self.assertEqual(
            self.preflight["failed_profile_id"], "claude-opus-high"
        )
        self.assertEqual(
            self.preflight["failed_model_invocation_state"], "not_started"
        )
        self.assertEqual(
            self.preflight["model_invocations_conservatively_chargeable"], 0
        )
        self.assertEqual(self.preflight["production_episodes_consumed"], 0)
        self.assertIs(self.preflight["scores_reported"], False)
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
            self.superseded["v20_conservative_claude_ceiling_added_usd"],
            0,
        )
        for field in (
            "resumption_permitted",
            "v20_cohort_reuse_permitted",
            "v20_key_or_namespace_reuse_permitted",
            "public_results_artifact_created",
            "results_released",
            "scores_released",
            "traces_released",
        ):
            self.assertIs(self.superseded[field], False)

    def test_v20_receipt_does_not_overclaim_the_exact_subphase(self) -> None:
        self.assertEqual(
            self.superseded["audited_root_cause_code"],
            "pre_model_failure_collapsed_by_v20_generic_provider_adapter_taxonomy",
        )
        self.assertEqual(
            self.superseded["root_cause_evidence_level"],
            "authenticated_public_receipt_plus_provider_free_offline_audit",
        )
        self.assertEqual(
            self.superseded["root_cause_scope"],
            "before_durable_model_invocation_start",
        )
        self.assertIs(
            self.superseded[
                "exact_subphase_recoverable_from_v20_public_receipt"
            ],
            False,
        )
        self.assertEqual(
            self.superseded["historical_failure_reason"],
            self.preflight["failure_reason"],
        )
        self.assertEqual(
            self.superseded["historical_failure_stage"],
            self.preflight["failure_stage"],
        )
        self.assertEqual(
            self.superseded["historical_incident_code"],
            self.preflight["incident_code"],
        )

    def test_v21_documents_the_required_repair_and_exact_budget(self) -> None:
        self.assertEqual(
            self.superseded["replacement_panel_id"],
            "development-matched-50x6-v21",
        )
        requirements = set(self.superseded["replacement_requirements"])
        self.assertTrue(
            {
                "finite_content_free_pre_model_phase_taxonomy",
                "durable_pre_model_phase_checkpoint",
                "typed_provider_environment_setup_failure",
                "typed_provider_cli_unavailable_failure",
                "typed_provider_workspace_setup_failure",
                "typed_provider_cli_readiness_setup_failure",
                "typed_cli_version_nonzero_failure",
                "typed_cli_version_empty_failure",
                "typed_provider_mcp_readiness_failure",
                "typed_episode_startup_failure",
                (
                    "durable_model_invocation_marker_immediately_before_"
                    "model_bearing_spawn"
                ),
                "chargeability_derived_only_from_durable_model_invocation_state",
                "identical_preflight_and_production_phase_accounting",
                (
                    "test_evaluator_must_not_synthesize_model_start_after_"
                    "generic_exception"
                ),
            }.issubset(requirements)
        )
        self.assertEqual(
            "sha256:"
            + hashlib.sha256(
                self.V21_ACKNOWLEDGEMENT.encode("utf-8")
            ).hexdigest(),
            self.V21_ACKNOWLEDGEMENT_SHA256,
        )
        readme = (self.root / "README.md").read_text(encoding="utf-8")
        runbook = (self.root / "docs/V21_RUNBOOK.md").read_text(
            encoding="utf-8"
        )
        self.assertIn(self.V21_ACKNOWLEDGEMENT, runbook)
        for document in (runbook,):
            self.assertIn("$510", document)
            self.assertIn("$80", document)
            self.assertIn("$590", document)
        self.assertIn("$610", readme)
        self.assertIn(self.V21_ACKNOWLEDGEMENT_SHA256, runbook)

    def test_v20_runbook_is_terminal_and_points_to_v21(self) -> None:
        runbook = (self.root / "docs/V20_RUNBOOK.md").read_text(
            encoding="utf-8"
        )
        self.assertTrue(runbook.startswith("> [!CAUTION]\n"))
        self.assertIn(
            "**TERMINAL AND SUPERSEDED — DO NOT EXECUTE THIS RUNBOOK.**",
            runbook,
        )
        self.assertIn(
            "../results/development-matched-50x6-v20.superseded.json",
            runbook,
        )
        self.assertIn("[V21 runbook](V21_RUNBOOK.md)", runbook)

    def test_v20_released_no_production_result_score_or_trace(self) -> None:
        self.assertFalse(
            (
                self.root / "results/development-matched-50x6-v20.json"
            ).exists()
        )
        self.assertEqual(
            self.superseded["production_assignments_started"], 0
        )
        self.assertEqual(
            self.superseded["production_episodes_consumed"], 0
        )

    def test_v21_runbook_preserves_the_two_commit_provider_free_boundary(
        self,
    ) -> None:
        runbook = (self.root / "docs/V21_RUNBOOK.md").read_text(
            encoding="utf-8"
        )
        publish = runbook.index("publish-provider-free-json")
        receipt_commit = runbook.index(
            "Publish V21 scientific runtime receipt"
        )
        tracked_receipt = runbook.index(
            'git ls-files --error-unmatch "$V21_PUBLIC_RUNTIME"'
        )
        private_creation = runbook.index("openssl rand 32")
        self.assertLess(publish, receipt_commit)
        self.assertLess(receipt_commit, tracked_receipt)
        self.assertLess(tracked_receipt, private_creation)
        self.assertIn("--public-runtime-receipt", runbook)
        self.assertIn("--freeze-claim", runbook)
        self.assertIn(
            '"$HOME/.codex/epiagentbench-v21-credentials/claude"',
            runbook,
        )
        self.assertIn(
            '"$HOME/.codex/epiagentbench-v21-credentials/codex"',
            runbook,
        )
        self.assertIn(
            "${EPIAGENTBENCH_PYTHON:?"
            "set the absolute isolated EpiAgentBench Python path}",
            runbook,
        )
        self.assertNotIn("/Users/", runbook)
        self.assertNotIn("/home/", runbook)

    def test_v20_preflight_receipt_contains_no_sensitive_payload(self) -> None:
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
            forbidden_keys.isdisjoint(self._keys(self.preflight))
        )
        encoded = json.dumps(self.preflight, sort_keys=True).lower()
        for canary in (
            "/home/",
            "/private/",
            "/users/",
            "auth.json",
            "credentials.json",
            "panel-auth.key",
            "schedule_nonce_hex",
        ):
            self.assertNotIn(canary, encoded)

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
