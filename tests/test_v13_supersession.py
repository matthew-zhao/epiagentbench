from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest


class V13SupersessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.manifest_path = (
            cls.root / "results" / "development-matched-50x6-v13.manifest.json"
        )
        cls.superseded_path = (
            cls.root / "results" / "development-matched-50x6-v13.superseded.json"
        )
        cls.superseded = json.loads(
            cls.superseded_path.read_text(encoding="utf-8")
        )

    def test_supersession_has_a_closed_public_schema(self) -> None:
        self.assertEqual(
            set(self.superseded),
            {
                "authentication_bootstraps_started",
                "authorization_dependency_identity_processes_started",
                "authorization_validation_attempts",
                "development_only",
                "failure_reason_codes",
                "failure_stage",
                "model_bearing_provider_call_exposure",
                "model_bearing_provider_calls_conservatively_chargeable",
                "original_manifest_file_sha256",
                "original_manifest_git_commit",
                "original_panel_id",
                "original_precommitment_sha256",
                "original_source_commit",
                "preflight_profiles_attempted",
                "preflight_profiles_passed",
                "production_assignments_started",
                "public_authentication_receipt_created",
                "public_preflight_receipt_created",
                "public_results_artifact_created",
                "replacement_panel_id",
                "replacement_requirements",
                "results_released",
                "resumption_permitted",
                "schema_version",
                "scores_released",
                "spend_acknowledgement_supplied",
                "spend_authorization_recorded",
                "status",
                "superseded_at_utc",
                "traces_released",
                "v13_cohort_reuse_permitted",
                "zero_call_claim_scope",
            },
        )

    def test_supersession_binds_the_published_v13_precommitment(self) -> None:
        manifest_bytes = self.manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes)
        self.assertEqual(
            self.superseded["schema_version"],
            "epiagentbench.panel_supersession.v5",
        )
        self.assertEqual(
            self.superseded["status"],
            "abandoned_zero_model_precommitment",
        )
        self.assertIs(self.superseded["development_only"], True)
        self.assertEqual(
            self.superseded["original_manifest_file_sha256"],
            "sha256:" + hashlib.sha256(manifest_bytes).hexdigest(),
        )
        self.assertEqual(
            self.superseded["original_precommitment_sha256"],
            manifest["precommitment_sha256"],
        )
        self.assertEqual(
            self.superseded["original_panel_id"],
            "development-matched-50x6-v13",
        )
        self.assertEqual(
            self.superseded["replacement_panel_id"],
            "development-matched-50x6-v14",
        )
        self.assertEqual(
            self.superseded["original_manifest_git_commit"],
            "465be822519a20a8ccacbc45b2b454a20e67d53b",
        )
        self.assertEqual(
            self.superseded["original_source_commit"],
            "1a357e88a0e59105a2e193bdd4d3bf9388e4d493",
        )
        self.assertRegex(
            self.superseded["superseded_at_utc"],
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$",
        )

    def test_authorization_failed_before_any_external_call_or_write(self) -> None:
        self.assertEqual(
            self.superseded["failure_stage"],
            "spend_authorization_prewrite_contract_validation",
        )
        self.assertEqual(
            self.superseded["failure_reason_codes"],
            [
                "glean_helper_content_identity_drift",
                "glean_gateway_wrapper_content_identity_drift",
                "authorization_failed_before_private_receipt_write",
            ],
        )
        self.assertEqual(self.superseded["authorization_validation_attempts"], 1)
        self.assertEqual(
            self.superseded[
                "authorization_dependency_identity_processes_started"
            ],
            0,
        )
        self.assertEqual(self.superseded["authentication_bootstraps_started"], 0)
        self.assertEqual(
            self.superseded["model_bearing_provider_call_exposure"], "none"
        )
        self.assertEqual(
            self.superseded[
                "model_bearing_provider_calls_conservatively_chargeable"
            ],
            0,
        )
        self.assertEqual(self.superseded["preflight_profiles_attempted"], 0)
        self.assertEqual(self.superseded["preflight_profiles_passed"], 0)
        self.assertEqual(self.superseded["production_assignments_started"], 0)
        self.assertIs(self.superseded["spend_acknowledgement_supplied"], True)
        self.assertIs(self.superseded["spend_authorization_recorded"], False)
        self.assertEqual(
            self.superseded["zero_call_claim_scope"],
            (
                "authorization performed local read-only contract validation, "
                "including file hashing; no provider or helper process, "
                "authentication bootstrap, model-bearing preflight call, or "
                "production assignment started"
            ),
        )
        self.assertEqual(
            self.superseded["replacement_requirements"],
            [
                "fresh cohort and private schedule",
                "fresh owner-only authentication and credential namespaces",
                "prepare-time static routing and executable contract",
                (
                    "exact Glean helper bundle sampled consistently and bound "
                    "with spend authorization"
                ),
                (
                    "committed sanitized authentication dependency receipt "
                    "before preflight"
                ),
            ],
        )

    def test_v13_cannot_resume_reuse_release_or_leak(self) -> None:
        self.assertIs(self.superseded["resumption_permitted"], False)
        self.assertIs(self.superseded["v13_cohort_reuse_permitted"], False)
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
            "\"claude\"",
            "\"codex\"",
            "\"cursor\"",
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
        ):
            self.assertNotIn(forbidden, encoded)


if __name__ == "__main__":
    unittest.main()
