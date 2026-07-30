from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import unittest


class V23SupersessionTests(unittest.TestCase):
    RUNTIME_PATH = "results/development-matched-50x6-v23.runtime.json"
    MANIFEST_PATH = "results/development-matched-50x6-v23.manifest.json"
    AUTHENTICATION_PATH = (
        "results/development-matched-50x6-v23.authentication.json"
    )
    SUPERSESSION_PATH = (
        "results/development-matched-50x6-v23.superseded.json"
    )
    RUNTIME_SHA256 = (
        "sha256:78e3eb1a87bf3f950a9c798c1a78f6af2f16577f664b6080f156de7e4739376b"
    )
    MANIFEST_SHA256 = (
        "sha256:bca5015bcf45dc1a1213260922ddca48f4f3d9f4b6aedcad31191d8c555a2e4e"
    )
    AUTHENTICATION_SHA256 = (
        "sha256:9eae8348cc42480e4e0acf2fb064763eaf0120f84218d4cdd244aa841fca8c8f"
    )
    PUBLIC_COMMITS = {
        "control_commit": "cd321a5edbe188eea0fa01338426143a246877d3",
        "runtime_receipt_commit": (
            "cc77f517f1522d3e3637e7822cd44aadbca9e079"
        ),
        "manifest_commit": "6e1f4fb7c9bc47b41dde6022d431c8a2a99f9d37",
        "authentication_receipt_commit": (
            "2fb662695e5fed2f859494d785b3c619e5a52cd9"
        ),
    }
    PRECOMMITMENT_SHA256 = (
        "sha256:3a8fcb8e2de13cfe6d129553345a53dfdb26d29467ebb170c6389bbc277cfcc1"
    )
    ACKNOWLEDGEMENT_SHA256 = (
        "sha256:538b597829cfba4152ced9377c6b05ebe895a6591cee9b3b807fee5e03af298e"
    )

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.manifest = cls._read(cls.MANIFEST_PATH)
        cls.authentication = cls._read(cls.AUTHENTICATION_PATH)
        cls.superseded = cls._read(cls.SUPERSESSION_PATH)

    @classmethod
    def _read(cls, relative: str) -> dict:
        return json.loads((cls.root / relative).read_bytes())

    @staticmethod
    def _keys(payload: object) -> set[str]:
        observed: set[str] = set()
        if isinstance(payload, Mapping):
            for key, value in payload.items():
                observed.add(str(key))
                observed.update(V23SupersessionTests._keys(value))
        elif isinstance(payload, Sequence) and not isinstance(
            payload, (str, bytes, bytearray)
        ):
            for value in payload:
                observed.update(V23SupersessionTests._keys(value))
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
                "exact_root_cause_reproduced_provider_free",
                "exception_text_released",
                "manifest_commit",
                "manifest_file_sha256",
                "model_bearing_provider_call_exposure",
                "model_bearing_provider_calls_conservatively_chargeable",
                "model_calls_started",
                "official_passing_preflight_receipt_created",
                "original_panel_id",
                "original_precommitment_sha256",
                "pending_preflight_watermark_canonical_sha256",
                "pending_preflight_watermark_created",
                "pending_preflight_watermark_file_sha256",
                "pending_preflight_watermark_status",
                "preflight_profiles_attempted",
                "preflight_profiles_evaluator_passed",
                "preflight_profiles_terminal",
                "production_assignments_started",
                "production_episodes_consumed",
                "public_results_artifact_created",
                "raw_provider_outputs_inspected",
                "release_failure_code",
                "release_failure_code_specificity",
                "release_failure_stage",
                "replacement_panel_id",
                "replacement_requirements",
                "required_spend_acknowledgement_text_sha256",
                "results_released",
                "resumption_permitted",
                "root_cause_evidence_level",
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
                "v23_cohort_reuse_permitted",
                "v23_conservative_claude_ceiling_added_usd",
                "v23_key_or_namespace_reuse_permitted",
            },
        )
        self.assertEqual(
            self.superseded["schema_version"],
            "epiagentbench.panel_supersession.v15",
        )

    def test_supersession_binds_exact_public_v23_artifacts(self) -> None:
        for relative, expected in (
            (self.RUNTIME_PATH, self.RUNTIME_SHA256),
            (self.MANIFEST_PATH, self.MANIFEST_SHA256),
            (self.AUTHENTICATION_PATH, self.AUTHENTICATION_SHA256),
        ):
            observed = "sha256:" + hashlib.sha256(
                (self.root / relative).read_bytes()
            ).hexdigest()
            self.assertEqual(observed, expected)
        for field, expected in self.PUBLIC_COMMITS.items():
            self.assertEqual(self.superseded[field], expected)
        self.assertEqual(
            self.superseded["runtime_receipt_file_sha256"],
            self.RUNTIME_SHA256,
        )
        self.assertEqual(
            self.superseded["manifest_file_sha256"],
            self.MANIFEST_SHA256,
        )
        self.assertEqual(
            self.superseded["authentication_receipt_file_sha256"],
            self.AUTHENTICATION_SHA256,
        )
        self.assertEqual(
            self.manifest["precommitment_sha256"],
            self.PRECOMMITMENT_SHA256,
        )
        self.assertEqual(
            self.superseded["original_precommitment_sha256"],
            self.PRECOMMITMENT_SHA256,
        )
        self.assertEqual(
            self.authentication["receipt_sha256"],
            self.superseded["authentication_receipt_sha256"],
        )
        manifest_acknowledgement = self.manifest["run_contract"][
            "spend_authorization"
        ]["required_acknowledgement_text_sha256"]
        self.assertEqual(
            manifest_acknowledgement, self.ACKNOWLEDGEMENT_SHA256
        )
        self.assertEqual(
            self.superseded[
                "required_spend_acknowledgement_text_sha256"
            ],
            self.ACKNOWLEDGEMENT_SHA256,
        )

    def test_v23_is_terminal_six_call_and_not_resumable(self) -> None:
        self.assertEqual(
            self.superseded["status"],
            "failed_preflight_release_validation",
        )
        self.assertEqual(
            self.superseded["release_failure_code"],
            "release_validation_failed",
        )
        self.assertEqual(
            self.superseded["release_failure_code_specificity"],
            "legacy_generic",
        )
        self.assertEqual(self.superseded["model_calls_started"], 6)
        self.assertEqual(
            self.superseded["model_bearing_provider_call_exposure"],
            {"claude": 2, "codex": 2, "cursor": 2, "total": 6},
        )
        self.assertEqual(
            self.superseded[
                "model_bearing_provider_calls_conservatively_chargeable"
            ],
            6,
        )
        for field in (
            "preflight_profiles_attempted",
            "preflight_profiles_evaluator_passed",
            "preflight_profiles_terminal",
        ):
            self.assertEqual(self.superseded[field], 6)
        for field in (
            "production_assignments_started",
            "production_episodes_consumed",
        ):
            self.assertEqual(self.superseded[field], 0)
        self.assertEqual(
            self.superseded[
                "v23_conservative_claude_ceiling_added_usd"
            ],
            10.0,
        )
        for field in (
            "cohort_retired",
            "exception_text_released",
            "official_passing_preflight_receipt_created",
            "public_results_artifact_created",
            "raw_provider_outputs_inspected",
            "resumption_permitted",
            "results_released",
            "scores_released",
            "traces_released",
            "v23_cohort_reuse_permitted",
            "v23_key_or_namespace_reuse_permitted",
        ):
            self.assertIs(self.superseded[field], False)

    def test_pending_watermark_is_not_reclassified_as_passing_receipt(
        self,
    ) -> None:
        self.assertIs(
            self.superseded["pending_preflight_watermark_created"],
            True,
        )
        self.assertEqual(
            self.superseded["pending_preflight_watermark_status"],
            "passed_pending_supervisor_completion",
        )
        for field in (
            "pending_preflight_watermark_file_sha256",
            "pending_preflight_watermark_canonical_sha256",
        ):
            self.assertRegex(
                self.superseded[field],
                r"\Asha256:[0-9a-f]{64}\Z",
            )
        self.assertFalse(
            (
                self.root
                / "results/development-matched-50x6-v23.preflight.json"
            ).exists()
        )

    def test_v24_requires_fresh_namespaces_and_release_boundary(self) -> None:
        self.assertEqual(
            self.superseded["replacement_panel_id"],
            "development-matched-50x6-v24",
        )
        requirements = set(self.superseded["replacement_requirements"])
        self.assertTrue(
            {
                "fresh_panel_precommitment",
                "fresh_authentication_key",
                "fresh_private_schedule_and_cohort",
                "fresh_managed_glean_credential_namespace",
                "fresh_codex_credential_namespace",
                "fresh_cursor_keychain_service_after_authorization",
                "fresh_runtime_cache_and_supervisor_namespaces",
                "post_completion_sealed_scientific_identity_validation_without_live_reimport",
                "post_completion_provider_free_tracked_source_revalidation",
                "post_completion_safe_owner_only_cache_content_evolution_inside_sealed_topology",
                "control_lock_serialized_release_state_machine",
                "premature_and_lock_contention_finalize_read_only",
                "finite_authenticated_release_failure_code_taxonomy",
                "exception_text_forbidden_from_public_release_status",
                "real_launchd_to_matched_panel_no_site_release_regression",
                "exact_v24_manifest_bound_spend_authorization",
                "fresh_foreground_authentication_and_committed_receipt",
            }.issubset(requirements)
        )

    def test_supersession_timestamp_follows_manifest_preparation(self) -> None:
        superseded_at = datetime.fromisoformat(
            self.superseded["superseded_at_utc"].replace("Z", "+00:00")
        )
        prepared_at = datetime.fromisoformat(
            self.manifest["prepared_at_utc"].replace("Z", "+00:00")
        )
        self.assertEqual(superseded_at.tzinfo, timezone.utc)
        self.assertGreater(superseded_at, prepared_at)

    def test_supersession_contains_no_sensitive_or_scored_payload(
        self,
    ) -> None:
        forbidden = {
            "access_token",
            "api_key",
            "argv",
            "cache_directories",
            "credential_contents",
            "episode_id",
            "episode_ref",
            "exception",
            "family",
            "hidden",
            "observation",
            "oauth_state",
            "pack_path",
            "private_seed",
            "prompt",
            "provider_output",
            "raw_output",
            "replay_trace",
            "schedule",
            "score",
            "stderr",
            "stdout",
            "trace",
        }
        self.assertTrue(forbidden.isdisjoint(self._keys(self.superseded)))


if __name__ == "__main__":
    unittest.main()
