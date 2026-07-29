from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
from pathlib import Path
import unittest


class V21SupersessionTests(unittest.TestCase):
    PUBLIC_FILE_HASHES = {
        "results/development-matched-50x6-v21.runtime.json": (
            "sha256:d129a150e3f7d91d2159331a48f751649109809354b9da4ab1fc559a1727e5c0"
        ),
        "results/development-matched-50x6-v21.manifest.json": (
            "sha256:11ceccec1fdda82cef5bde855017ae63cd813072107cd5c0ae85e5643e579fec"
        ),
        "results/development-matched-50x6-v21.authentication.json": (
            "sha256:750997a56d64b9e31a069aae06ad902dc29051dd872a335bda6ed06b753d6a1d"
        ),
        "results/development-matched-50x6-v21.preflight.json": (
            "sha256:6e7addd4be8a7650d3e3ff112a09205731a83c0ee6785575cbcc775f44335933"
        ),
    }
    PUBLIC_COMMITS = {
        "control_commit": "595df41eae489efcfff2789fcdc52e02cd3a0cb5",
        "runtime_receipt_commit": (
            "3f96521417ff0aa625dd4e28823f7dd45ccef948"
        ),
        "manifest_commit": "f9fde5b850e7c6c5dd9559b8c606f804b22119e6",
        "authentication_receipt_commit": (
            "53d3748da3136152d69109a24ee802983fc1bd06"
        ),
        "preflight_execution_commit": (
            "83c3e28640ca747707e31662270b9880ac1b4387"
        ),
    }
    V22_ACKNOWLEDGEMENT = (
        "I acknowledge the replacement six-call v22 preflight and "
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
        "zero-model-call v20 preflight, the failed zero-model-call v21 "
        "preflight, and the v22 preflight and production run."
    )

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.runtime = cls._read(
            "results/development-matched-50x6-v21.runtime.json"
        )
        cls.manifest = cls._read(
            "results/development-matched-50x6-v21.manifest.json"
        )
        cls.authentication = cls._read(
            "results/development-matched-50x6-v21.authentication.json"
        )
        cls.preflight = cls._read(
            "results/development-matched-50x6-v21.preflight.json"
        )
        cls.superseded = cls._read(
            "results/development-matched-50x6-v21.superseded.json"
        )

    @classmethod
    def _read(cls, relative: str) -> dict:
        return json.loads((cls.root / relative).read_bytes())

    @staticmethod
    def _keys(payload: object) -> set[str]:
        observed: set[str] = set()
        if isinstance(payload, Mapping):
            for key, value in payload.items():
                observed.add(str(key))
                observed.update(V21SupersessionTests._keys(value))
        elif isinstance(payload, Sequence) and not isinstance(
            payload, (str, bytes, bytearray)
        ):
            for value in payload:
                observed.update(V21SupersessionTests._keys(value))
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
                "exact_subphase_recoverable_from_v21_public_receipt",
                "failed_model_invocation_state",
                "failed_pre_model_phase",
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
                "v21_cohort_reuse_permitted",
                "v21_conservative_claude_ceiling_added_usd",
                "v21_key_or_namespace_reuse_permitted",
            },
        )
        self.assertEqual(
            self.superseded["schema_version"],
            "epiagentbench.panel_supersession.v13",
        )

    def test_supersession_binds_exact_v21_public_artifacts(self) -> None:
        for relative, expected in self.PUBLIC_FILE_HASHES.items():
            observed = "sha256:" + hashlib.sha256(
                (self.root / relative).read_bytes()
            ).hexdigest()
            self.assertEqual(observed, expected)
        for field, expected in self.PUBLIC_COMMITS.items():
            self.assertEqual(self.superseded[field], expected)
        self.assertEqual(
            self.superseded["runtime_receipt_file_sha256"],
            self.PUBLIC_FILE_HASHES[
                "results/development-matched-50x6-v21.runtime.json"
            ],
        )
        self.assertEqual(
            self.superseded["manifest_file_sha256"],
            self.PUBLIC_FILE_HASHES[
                "results/development-matched-50x6-v21.manifest.json"
            ],
        )
        self.assertEqual(
            self.superseded["authentication_receipt_file_sha256"],
            self.PUBLIC_FILE_HASHES[
                "results/development-matched-50x6-v21.authentication.json"
            ],
        )
        self.assertEqual(
            self.superseded["preflight_receipt_file_sha256"],
            self.PUBLIC_FILE_HASHES[
                "results/development-matched-50x6-v21.preflight.json"
            ],
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
        self.assertEqual(
            self.superseded["authentication_receipt_sha256"],
            self.authentication["receipt_sha256"],
        )
        self.assertEqual(
            self.superseded["spend_authorization_receipt_sha256"],
            self.authentication["spend_authorization_receipt_sha256"],
        )

    def test_v21_failed_before_model_start_and_is_never_resumable(self) -> None:
        self.assertEqual(
            self.superseded["status"],
            "failed_zero_model_preflight_episode_startup",
        )
        self.assertEqual(self.preflight["status"], "failed")
        self.assertEqual(
            self.preflight["failed_profile_id"],
            "claude-opus-high",
        )
        self.assertEqual(
            self.preflight["failed_model_invocation_state"],
            "not_started",
        )
        self.assertEqual(
            self.preflight["failed_pre_model_phase"],
            "episode_startup",
        )
        self.assertEqual(
            self.superseded["failed_profile_id"],
            self.preflight["failed_profile_id"],
        )
        self.assertEqual(
            self.superseded["failed_model_invocation_state"],
            self.preflight["failed_model_invocation_state"],
        )
        self.assertEqual(
            self.superseded["failed_pre_model_phase"],
            self.preflight["failed_pre_model_phase"],
        )
        self.assertEqual(
            self.superseded["historical_failure_reason"],
            self.preflight["failure_reason"],
        )
        self.assertEqual(
            self.superseded["preflight_receipt_status"],
            self.preflight["status"],
        )
        self.assertEqual(
            self.superseded["preflight_profiles_attempted"],
            sum(
                profile["outcome"]
                not in {
                    "not_started_terminal_abort",
                    "skipped_dependency",
                }
                for profile in self.preflight["profiles"]
            ),
        )
        self.assertEqual(
            self.superseded["preflight_profiles_passed"],
            sum(
                profile["outcome"] == "passed"
                for profile in self.preflight["profiles"]
            ),
        )
        self.assertEqual(
            self.preflight["model_invocations_conservatively_chargeable"],
            0,
        )
        self.assertEqual(self.preflight["production_episodes_consumed"], 0)
        self.assertIs(self.preflight["scores_reported"], False)
        self.assertEqual(
            self.superseded["model_bearing_provider_call_exposure"],
            {"claude": 0, "codex": 0, "cursor": 0, "total": 0},
        )
        self.assertEqual(
            self.superseded["v21_conservative_claude_ceiling_added_usd"],
            0,
        )
        for field in (
            "resumption_permitted",
            "v21_cohort_reuse_permitted",
            "v21_key_or_namespace_reuse_permitted",
            "public_results_artifact_created",
            "results_released",
            "scores_released",
            "traces_released",
        ):
            self.assertIs(self.superseded[field], False)

    def test_root_cause_claim_is_precise_about_receipt_and_reproduction(
        self,
    ) -> None:
        self.assertEqual(
            self.superseded["audited_root_cause_code"],
            "multiprocessing_spawn_file_replay_duplicated_isolated_sys_path",
        )
        self.assertEqual(
            self.superseded["root_cause_scope"],
            "trusted_episode_broker_bootstrap_before_model_invocation",
        )
        self.assertEqual(
            self.superseded["root_cause_evidence_level"],
            "authenticated_public_receipt_plus_exact_provider_free_file_entrypoint_reproduction",
        )
        self.assertIs(
            self.superseded["exact_root_cause_reproduced_provider_free"],
            True,
        )
        self.assertIs(
            self.superseded[
                "exact_subphase_recoverable_from_v21_public_receipt"
            ],
            False,
        )
        self.assertEqual(
            self.superseded["historical_failure_stage"],
            self.preflight["failure_stage"],
        )
        self.assertEqual(
            self.superseded["historical_incident_code"],
            self.preflight["incident_code"],
        )

    def test_v22_requires_the_real_spawn_smoke_and_fresh_namespaces(self):
        self.assertEqual(
            self.superseded["replacement_panel_id"],
            "development-matched-50x6-v22",
        )
        self.assertEqual(
            self.superseded["replacement_requirements"],
            [
                "fresh_panel_precommitment",
                "fresh_authentication_key",
                "fresh_private_schedule_and_cohort",
                "fresh_managed_glean_credential_namespace",
                "fresh_codex_credential_namespace",
                "fresh_cursor_keychain_service_after_authorization",
                "fresh_runtime_cache_and_supervisor_namespaces",
                "exact_idempotent_isolated_sys_path_parent_or_spawn_replay_only",
                "partial_duplicate_reordered_or_displaced_import_paths_fail_closed",
                "unchanged_exact_isolated_python_process_validator",
                "real_python_I_S_B_file_entrypoint_multiprocessing_spawn_smoke",
                "all_public_families_and_boundary_public_seeds_twice_serially",
                "provider_free_broker_ready_handshake_before_private_cohort_creation",
                "finite_content_free_episode_startup_substage",
                "episode_startup_smoke_bound_into_preparation_runtime_receipt",
                "fresh_v22_manifest_bound_spend_authorization",
                "fresh_foreground_authentication_and_committed_receipt",
            ],
        )
        self.assertEqual(
            "sha256:"
            + hashlib.sha256(self.V22_ACKNOWLEDGEMENT.encode()).hexdigest(),
            "sha256:fea481a235c9edf64348c0e98e4b8b913869a929ee66ae3a9bf49052cdd1a94a",
        )

    def test_v21_public_receipt_and_supersession_are_content_free(self) -> None:
        forbidden = {
            "access_token",
            "api_key",
            "credential_contents",
            "oauth_state",
            "observation",
            "private_seed",
            "prompt",
            "provider_output",
            "raw_stderr",
            "raw_stdout",
            "refresh_token",
            "schedule",
            "score",
            "stderr",
            "stdout",
            "trace",
        }
        self.assertTrue(forbidden.isdisjoint(self._keys(self.preflight)))
        self.assertTrue(forbidden.isdisjoint(self._keys(self.superseded)))

    def test_v21_runbook_is_terminal_and_points_to_v22(self) -> None:
        runbook = (self.root / "docs/V21_RUNBOOK.md").read_text(
            encoding="utf-8"
        )
        self.assertTrue(runbook.startswith("> [!CAUTION]\n"))
        self.assertIn(
            "**TERMINAL AND SUPERSEDED — DO NOT EXECUTE THIS RUNBOOK.**",
            runbook,
        )
        self.assertIn(
            "../results/development-matched-50x6-v21.superseded.json",
            runbook,
        )
        self.assertIn("[V22 runbook](V22_RUNBOOK.md)", runbook)


if __name__ == "__main__":
    unittest.main()
