from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

from epiagentbench.development_matched_panel import _component_hash


class V10SupersessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.manifest_path = (
            cls.root / "results" / "development-matched-50x6-v10.manifest.json"
        )
        cls.superseded_path = (
            cls.root / "results" / "development-matched-50x6-v10.superseded.json"
        )
        cls.manifest = json.loads(
            cls.manifest_path.read_text(encoding="utf-8")
        )
        cls.superseded = json.loads(
            cls.superseded_path.read_text(encoding="utf-8")
        )

    @staticmethod
    def _file_hash(path: Path) -> str:
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()

    def test_supersession_has_a_closed_public_schema(self) -> None:
        self.assertEqual(
            set(self.superseded),
            {
                "authentication_bootstraps_started",
                "cohort_retired",
                "cohort_reuse_permitted",
                "development_only",
                "evidence_strength",
                "failure_reason_code",
                "failure_stage",
                "model_bearing_provider_call_exposure",
                "model_bearing_provider_calls_conservatively_chargeable",
                "original_manifest_canonical_sha256",
                "original_manifest_file_sha256",
                "original_manifest_git_commit",
                "original_panel_id",
                "original_precommitment_sha256",
                "persistent_supervisor_started",
                "preflight_profiles_attempted",
                "preflight_profiles_passed",
                "prepare_identity_probes",
                "private_state_recoverable",
                "production_assignments_started",
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
                "zero_call_claim_scope",
            },
        )
        self.assertEqual(
            self.superseded["schema_version"],
            "epiagentbench.panel_supersession.v2",
        )
        self.assertEqual(
            self.superseded["status"],
            "abandoned_before_spend_authorization_receipt",
        )

    def test_supersession_binds_the_committed_public_manifest(self) -> None:
        self.assertEqual(
            self.superseded["original_manifest_file_sha256"],
            self._file_hash(self.manifest_path),
        )
        self.assertEqual(
            self.superseded["original_manifest_canonical_sha256"],
            _component_hash(self.manifest),
        )
        self.assertEqual(
            self.superseded["original_precommitment_sha256"],
            self.manifest["precommitment_sha256"],
        )

    def test_zero_call_scope_is_precise_and_reuse_is_forbidden(self) -> None:
        self.assertEqual(
            self.superseded["authentication_bootstraps_started"],
            {"codex": 0, "managed_glean": 0, "total": 0},
        )
        self.assertEqual(self.superseded["preflight_profiles_attempted"], 0)
        self.assertEqual(self.superseded["production_assignments_started"], 0)
        self.assertEqual(
            self.superseded[
                "model_bearing_provider_calls_conservatively_chargeable"
            ],
            0,
        )
        self.assertEqual(
            self.superseded["model_bearing_provider_call_exposure"],
            {"claude": 0, "codex": 0, "cursor": 0, "total": 0},
        )
        self.assertEqual(
            self.superseded["prepare_identity_probes"],
            "completed_credential_free_no_model",
        )
        self.assertIs(self.superseded["spend_authorization_recorded"], False)
        self.assertIs(self.superseded["resumption_permitted"], False)
        self.assertIs(self.superseded["cohort_reuse_permitted"], False)
        self.assertIs(self.superseded["results_released"], False)
        self.assertIs(self.superseded["scores_released"], False)
        self.assertIs(self.superseded["traces_released"], False)

    def test_public_supersession_contains_no_sensitive_surfaces(self) -> None:
        encoded = json.dumps(self.superseded, sort_keys=True).lower()
        for forbidden in (
            "/users/",
            "/private/tmp",
            "episode_ref",
            "episode_id",
            "pack_commitment",
            "family",
            "schedule_nonce",
            "seed",
            "credentials.json",
            "api_key",
            "access_token",
            "refresh_token",
            "oauth_state",
            "provider_output",
            "exception",
            "trace_steps",
        ):
            self.assertNotIn(forbidden, encoded)


if __name__ == "__main__":
    unittest.main()
