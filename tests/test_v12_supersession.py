from __future__ import annotations

import json
from pathlib import Path
import unittest


class V12SupersessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.manifest_path = (
            cls.root / "results" / "development-matched-50x6-v12.manifest.json"
        )
        cls.superseded_path = (
            cls.root / "results" / "development-matched-50x6-v12.superseded.json"
        )
        cls.superseded = json.loads(
            cls.superseded_path.read_text(encoding="utf-8")
        )

    def test_supersession_has_a_closed_public_schema(self) -> None:
        self.assertEqual(
            set(self.superseded),
            {
                "authentication_bootstraps_started",
                "development_only",
                "failure_reason_codes",
                "failure_stage",
                "model_bearing_provider_call_exposure",
                "model_bearing_provider_calls_conservatively_chargeable",
                "original_manifest_file_sha256",
                "original_manifest_published",
                "original_manifest_unpublished_local_commit",
                "original_panel_id",
                "original_precommitment_sha256",
                "original_source_commit",
                "preparation_audit",
                "preflight_profiles_attempted",
                "preflight_profiles_passed",
                "production_assignments_started",
                "public_authentication_receipt_created",
                "public_manifest_withheld",
                "public_preflight_receipt_created",
                "public_results_artifact_created",
                "replacement_panel_id",
                "replacement_requirements",
                "results_released",
                "resumption_permitted",
                "schema_version",
                "scores_released",
                "spend_authorization_recorded",
                "status",
                "superseded_at_utc",
                "traces_released",
                "v12_cohort_reuse_permitted",
                "zero_call_claim_scope",
            },
        )
        self.assertEqual(
            set(self.superseded["authentication_bootstraps_started"]),
            {"codex", "managed_glean", "total"},
        )
        self.assertEqual(
            set(self.superseded["model_bearing_provider_call_exposure"]),
            {"claude", "codex", "cursor", "total"},
        )
        self.assertEqual(
            set(self.superseded["preparation_audit"]),
            {
                "assignments_started",
                "authenticated_private_state_status",
                "model_calls_started",
                "provider_or_helper_version_processes_started",
            },
        )

    def test_supersession_binds_the_exact_withheld_v12_identity(self) -> None:
        self.assertEqual(
            self.superseded["schema_version"],
            "epiagentbench.panel_supersession.v4",
        )
        self.assertEqual(
            self.superseded["status"],
            "abandoned_zero_model_precommitment",
        )
        self.assertIs(self.superseded["development_only"], True)
        self.assertEqual(
            self.superseded["failure_stage"],
            "zero_model_precommitment_audit",
        )
        self.assertEqual(
            self.superseded["zero_call_claim_scope"],
            "model-bearing provider invocations; four zero-model "
            "provider/helper version processes ran during preparation",
        )
        self.assertRegex(
            self.superseded["superseded_at_utc"],
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$",
        )
        self.assertEqual(
            self.superseded["original_panel_id"],
            "development-matched-50x6-v12",
        )
        self.assertEqual(
            self.superseded["replacement_panel_id"],
            "development-matched-50x6-v13",
        )
        self.assertEqual(
            self.superseded["original_manifest_file_sha256"],
            "sha256:fef3ccc4bb05338e60b48b89ca3546bb96a10e72f34f9868cff4c96910ebcec5",
        )
        self.assertEqual(
            self.superseded["original_precommitment_sha256"],
            "sha256:ee7f7f752e8e08d7eee27907cf85f9ddc5a9b9fbc4674d7cafee12af8d8ee674",
        )
        self.assertEqual(
            self.superseded["original_source_commit"],
            "a83dba29f473243a2891d845f701d4a557b55762",
        )
        self.assertEqual(
            self.superseded["original_manifest_unpublished_local_commit"],
            "9e70193ae1e6a3efdb7fe74d8fae69bacb68daae",
        )
        self.assertIs(self.superseded["original_manifest_published"], False)
        self.assertIs(self.superseded["public_manifest_withheld"], True)
        self.assertFalse(self.manifest_path.exists())

    def test_zero_model_scope_and_four_identity_processes_are_exact(self) -> None:
        self.assertEqual(
            self.superseded["authentication_bootstraps_started"],
            {"codex": 0, "managed_glean": 0, "total": 0},
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
            self.superseded["preparation_audit"],
            {
                "assignments_started": 0,
                "authenticated_private_state_status": "prepared",
                "model_calls_started": 0,
                "provider_or_helper_version_processes_started": 4,
            },
        )
        self.assertEqual(self.superseded["preflight_profiles_attempted"], 0)
        self.assertEqual(self.superseded["preflight_profiles_passed"], 0)
        self.assertEqual(self.superseded["production_assignments_started"], 0)
        self.assertIs(self.superseded["spend_authorization_recorded"], False)

    def test_v12_cannot_resume_reuse_or_release(self) -> None:
        self.assertIs(self.superseded["resumption_permitted"], False)
        self.assertIs(self.superseded["v12_cohort_reuse_permitted"], False)
        self.assertIs(self.superseded["results_released"], False)
        self.assertIs(self.superseded["scores_released"], False)
        self.assertIs(self.superseded["traces_released"], False)
        self.assertIs(
            self.superseded["public_authentication_receipt_created"], False
        )
        self.assertIs(
            self.superseded["public_preflight_receipt_created"], False
        )
        self.assertIs(
            self.superseded["public_results_artifact_created"], False
        )
        self.assertEqual(
            self.superseded["failure_reason_codes"],
            [
                "prepare_executed_provider_controlled_version_commands",
                "initial_artifact_publication_was_not_create_once",
            ],
        )
        self.assertEqual(
            self.superseded["replacement_requirements"],
            [
                "fresh_panel_and_cohort_identity",
                "fresh_authentication_key",
                "fresh_private_schedule",
                "fresh_managed_glean_credential_namespace",
                "fresh_codex_credential_namespace",
                "provider_process_free_preparation",
                "host_global_prepare_lease",
                "authenticated_create_once_cohort_claim",
                "create_once_private_then_public_publication",
            ],
        )

    def test_public_supersession_contains_no_sensitive_or_raw_surfaces(self) -> None:
        encoded = json.dumps(self.superseded, sort_keys=True).lower()
        for forbidden in (
            "/users/",
            "/private/",
            "episode_ref",
            "episode_id",
            "pack_commitment",
            "family",
            "schedule_nonce",
            "seed",
            "credentials.json",
            "auth.json",
            "api_key",
            "access_token",
            "refresh_token",
            "oauth_state",
            "provider_output",
            "\"stdout\"",
            "\"stderr\"",
            "raw_stdout",
            "raw_stderr",
            "trace_steps",
            "claude code",
            "codex-cli",
            "cursor-agent ",
        ):
            self.assertNotIn(forbidden, encoded)


if __name__ == "__main__":
    unittest.main()
