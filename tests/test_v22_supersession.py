from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import unittest


class V22SupersessionTests(unittest.TestCase):
    RUNTIME_PATH = "results/development-matched-50x6-v22.runtime.json"
    MANIFEST_PATH = "results/development-matched-50x6-v22.manifest.json"
    SUPERSESSION_PATH = (
        "results/development-matched-50x6-v22.superseded.json"
    )
    RUNTIME_SHA256 = (
        "sha256:22df7e6c6b967890c44bc0d8fb3de429b992318dcc41b13fd5fd1b5f8107a95d"
    )
    MANIFEST_SHA256 = (
        "sha256:6df4c47635985cddec327db5a9d283a79523523886be7e68cbf9681e54d7f0b0"
    )
    PUBLIC_COMMITS = {
        "control_commit": "47fcb3b47aa235586d99200b74d5d62f03a4a5fb",
        "runtime_receipt_commit": (
            "544f467bd3b396008512677799b1af225fca6c34"
        ),
        "manifest_commit": "3ab15a071b433fb309c2bf0cc0cebaf39d69ac93",
    }
    PRECOMMITMENT_SHA256 = (
        "sha256:cc46b58450f9325a19fe8ff3c9c2d25d3d196e03f5319a5b0e0491851dee5163"
    )
    ACKNOWLEDGEMENT_SHA256 = (
        "sha256:fea481a235c9edf64348c0e98e4b8b913869a929ee66ae3a9bf49052cdd1a94a"
    )

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.runtime = cls._read(cls.RUNTIME_PATH)
        cls.manifest = cls._read(cls.MANIFEST_PATH)
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
                observed.update(V22SupersessionTests._keys(value))
        elif isinstance(payload, Sequence) and not isinstance(
            payload, (str, bytes, bytearray)
        ):
            for value in payload:
                observed.update(V22SupersessionTests._keys(value))
        return observed

    def test_supersession_has_closed_public_schema(self) -> None:
        self.assertEqual(
            set(self.superseded),
            {
                "authentication_failure_code",
                "authentication_failure_stage",
                "authentication_terminal_state",
                "control_commit",
                "development_only",
                "manifest_commit",
                "manifest_file_sha256",
                "model_bearing_provider_call_exposure",
                "model_bearing_provider_calls_conservatively_chargeable",
                "model_calls_started",
                "original_panel_id",
                "original_precommitment_sha256",
                "orphan_staging_contents_inspected",
                "owner_only_orphan_staging_directories_removed",
                "preflight_profiles_attempted",
                "preflight_profiles_passed",
                "production_assignments_started",
                "production_episodes_consumed",
                "public_authentication_receipt_created",
                "public_final_receipt_created",
                "public_preflight_receipt_created",
                "public_results_artifact_created",
                "replacement_panel_id",
                "replacement_requirements",
                "required_spend_acknowledgement_text_sha256",
                "results_released",
                "resumption_permitted",
                "runtime_receipt_commit",
                "runtime_receipt_file_sha256",
                "schema_version",
                "scores_released",
                "spend_acknowledgement_supplied",
                "spend_authorization_recorded",
                "status",
                "superseded_at_utc",
                "traces_released",
                "v22_authentication_receipt_created",
                "v22_cohort_reuse_permitted",
                "v22_conservative_claude_ceiling_added_usd",
                "v22_key_or_namespace_reuse_permitted",
            },
        )
        self.assertEqual(
            self.superseded["schema_version"],
            "epiagentbench.panel_supersession.v14",
        )

    def test_supersession_binds_exact_public_v22_artifacts(self) -> None:
        for relative, expected in (
            (self.RUNTIME_PATH, self.RUNTIME_SHA256),
            (self.MANIFEST_PATH, self.MANIFEST_SHA256),
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
            self.manifest["precommitment_sha256"],
            self.PRECOMMITMENT_SHA256,
        )
        self.assertEqual(
            self.superseded["original_precommitment_sha256"],
            self.PRECOMMITMENT_SHA256,
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

    def test_v22_is_terminal_zero_model_and_not_resumable(self) -> None:
        self.assertEqual(
            self.superseded["status"],
            "failed_zero_model_authentication_ceremony",
        )
        self.assertEqual(
            self.superseded["authentication_terminal_state"],
            "terminal_failed",
        )
        self.assertEqual(
            self.superseded["authentication_failure_code"],
            "interrupted_authentication_ceremony",
        )
        self.assertEqual(
            self.superseded["authentication_failure_stage"],
            "authentication_ceremony_reentry",
        )
        self.assertEqual(self.superseded["model_calls_started"], 0)
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
        for field in (
            "preflight_profiles_attempted",
            "preflight_profiles_passed",
            "production_assignments_started",
            "production_episodes_consumed",
            "v22_conservative_claude_ceiling_added_usd",
        ):
            self.assertEqual(self.superseded[field], 0)
        for field in (
            "public_authentication_receipt_created",
            "public_final_receipt_created",
            "public_preflight_receipt_created",
            "public_results_artifact_created",
            "resumption_permitted",
            "results_released",
            "scores_released",
            "traces_released",
            "v22_authentication_receipt_created",
            "v22_cohort_reuse_permitted",
            "v22_key_or_namespace_reuse_permitted",
        ):
            self.assertIs(self.superseded[field], False)

    def test_v22_created_no_authentication_preflight_or_final_receipt(
        self,
    ) -> None:
        for relative in (
            "results/development-matched-50x6-v22.authentication.json",
            "results/development-matched-50x6-v22.preflight.json",
            "results/development-matched-50x6-v22.json",
        ):
            self.assertFalse((self.root / relative).exists())

    def test_orphan_staging_cleanup_discloses_no_credential_content(
        self,
    ) -> None:
        self.assertEqual(
            self.superseded[
                "owner_only_orphan_staging_directories_removed"
            ],
            1,
        )
        self.assertIs(
            self.superseded["orphan_staging_contents_inspected"], False
        )

    def test_v23_requires_provider_free_reconciliation_and_terminal_auth(
        self,
    ) -> None:
        self.assertEqual(
            self.superseded["replacement_panel_id"],
            "development-matched-50x6-v23",
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
                "fresh_authorization_checkout",
                "provider_free_reconcile_authentication",
                "manual_persistent_terminal_authentication",
                "exact_v23_manifest_bound_spend_authorization",
                "fresh_committed_authentication_receipt",
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

    def test_supersession_omits_helper_start_counts(self) -> None:
        forbidden = {
            "authentication_bootstraps_started",
            "authentication_processes_started",
            "authentication_processes_started_by_refused_start",
            "provider_or_authentication_helper_processes_started",
            "provider_process_starts_ambiguous",
            "provider_processes_started",
        }
        self.assertTrue(forbidden.isdisjoint(self._keys(self.superseded)))

    def test_supersession_contains_no_sensitive_or_scored_payload(self) -> None:
        forbidden = {
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
        self.assertTrue(forbidden.isdisjoint(self._keys(self.superseded)))
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
