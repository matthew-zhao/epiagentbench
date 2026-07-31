from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
from pathlib import Path
import unittest


class V16SupersessionTests(unittest.TestCase):
    PUBLIC_FILE_HASHES = {
        "results/development-matched-50x6-v16.manifest.json": (
            "sha256:5e8521a8bcbf28f30c3e7aad319472c16b9fa2025770befd2f7126f0aa6112e0"
        ),
        "results/development-matched-50x6-v16.authentication.json": (
            "sha256:b0d9a9bb63d637bd4fc94be0ad88a49bdb7a693831db9dc8725f2fa7ac68aa5f"
        ),
        "results/development-matched-50x6-v16.preflight.json": (
            "sha256:a2a2e9dacefa819653b397f103754d2c42c054f4b03d4e1c7a25ad1e6b2ff2d5"
        ),
    }

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.superseded = json.loads(
            (
                cls.root
                / "results/development-matched-50x6-v16.superseded.json"
            ).read_bytes()
        )

    @staticmethod
    def _keys(payload: object) -> set[str]:
        observed: set[str] = set()
        if isinstance(payload, Mapping):
            for key, value in payload.items():
                observed.add(str(key))
                observed.update(V16SupersessionTests._keys(value))
        elif isinstance(payload, Sequence) and not isinstance(
            payload, (str, bytes, bytearray)
        ):
            for value in payload:
                observed.update(V16SupersessionTests._keys(value))
        return observed

    def test_supersession_has_closed_public_schema(self) -> None:
        self.assertEqual(
            set(self.superseded),
            {
                "audited_root_cause_code",
                "authentication_receipt_created",
                "authentication_receipt_file_sha256",
                "authentication_receipt_sha256",
                "cohort_retired",
                "development_only",
                "failed_profile_id",
                "historical_preflight_failure_reason",
                "historical_preflight_failure_stage",
                "historical_provider_invocation_state",
                "historical_worker_terminal_classification",
                "manifest_file_sha256",
                "model_bearing_provider_call_exposure",
                "model_bearing_provider_calls_conservatively_chargeable",
                "original_panel_id",
                "original_precommitment_sha256",
                "preflight_profiles_attempted",
                "preflight_profiles_passed",
                "preflight_receipt_file_sha256",
                "preflight_receipt_status",
                "production_assignments_started",
                "public_results_artifact_created",
                "replacement_panel_id",
                "replacement_requirements",
                "results_released",
                "resumption_permitted",
                "root_cause_scope",
                "schema_version",
                "scores_released",
                "spend_acknowledgement_supplied",
                "spend_authorization_recorded",
                "status",
                "superseded_at_utc",
                "traces_released",
                "v16_cohort_reuse_permitted",
                "v16_key_or_namespace_reuse_permitted",
            },
        )
        self.assertEqual(
            self.superseded["schema_version"],
            "epiagentbench.panel_supersession.v8",
        )
        self.assertRegex(
            self.superseded["superseded_at_utc"],
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$",
        )

    def test_supersession_binds_exact_trace_free_v16_artifacts(self) -> None:
        for relative, expected in self.PUBLIC_FILE_HASHES.items():
            digest = "sha256:" + hashlib.sha256(
                (self.root / relative).read_bytes()
            ).hexdigest()
            self.assertEqual(digest, expected)
        self.assertEqual(
            self.superseded["manifest_file_sha256"],
            self.PUBLIC_FILE_HASHES[
                "results/development-matched-50x6-v16.manifest.json"
            ],
        )
        self.assertEqual(
            self.superseded["authentication_receipt_file_sha256"],
            self.PUBLIC_FILE_HASHES[
                "results/development-matched-50x6-v16.authentication.json"
            ],
        )
        self.assertEqual(
            self.superseded["preflight_receipt_file_sha256"],
            self.PUBLIC_FILE_HASHES[
                "results/development-matched-50x6-v16.preflight.json"
            ],
        )

    def test_failure_accounting_matches_public_preflight(self) -> None:
        preflight = json.loads(
            (
                self.root
                / "results/development-matched-50x6-v16.preflight.json"
            ).read_bytes()
        )
        authentication = json.loads(
            (
                self.root
                / "results/development-matched-50x6-v16.authentication.json"
            ).read_bytes()
        )
        self.assertEqual(preflight["status"], "failed")
        self.assertEqual(preflight["preflight_purpose"], (
            "unscored_infrastructure_routing_handshake"
        ))
        self.assertEqual(preflight["production_episodes_consumed"], 0)
        self.assertIs(preflight["scores_reported"], False)
        self.assertEqual(preflight["provider_calls_conservatively_chargeable"], 1)
        attempted = [
            profile
            for profile in preflight["profiles"]
            if profile["invocation_state"] != "not_started"
        ]
        self.assertEqual(len(attempted), 1)
        self.assertEqual(
            attempted[0]["profile_id"],
            self.superseded["failed_profile_id"],
        )
        self.assertEqual(
            attempted[0]["invocation_state"],
            self.superseded["historical_provider_invocation_state"],
        )
        self.assertEqual(
            authentication["receipt_sha256"],
            self.superseded["authentication_receipt_sha256"],
        )
        self.assertEqual(
            self.superseded["model_bearing_provider_call_exposure"],
            {"claude": 1, "codex": 0, "cursor": 0, "total": 1},
        )

    def test_v16_is_terminal_and_v17_has_the_required_handoff_controls(self) -> None:
        self.assertEqual(
            self.superseded["status"],
            "failed_preflight_terminal_handoff",
        )
        self.assertEqual(
            self.superseded["audited_root_cause_code"],
            "handled_terminal_receipt_collapsed_to_supervisor_exception",
        )
        self.assertEqual(
            self.superseded["root_cause_scope"],
            "control_plane_terminal_handoff_not_provider_specific",
        )
        self.assertIs(self.superseded["resumption_permitted"], False)
        self.assertIs(self.superseded["v16_cohort_reuse_permitted"], False)
        self.assertIs(
            self.superseded["v16_key_or_namespace_reuse_permitted"], False
        )
        requirements = set(self.superseded["replacement_requirements"])
        self.assertTrue(
            {
                "trusted_closed_incident_taxonomy",
                "durable_terminal_receipt_before_handled_exit",
                "reserved_handled_terminal_exit_code_64",
                "provider_free_terminal_receipt_reconciliation",
                "repository_relative_receipt_bindings",
                "persistent_supervisor_contract_schema_v6",
            }.issubset(requirements)
        )
        source = (
            self.root / "src/epiagentbench/development_matched_panel.py"
        ).read_text(encoding="utf-8")
        supervisor = (
            self.root / "src/epiagentbench/persistent_supervisor.py"
        ).read_text(encoding="utf-8")
        for symbol in (
            "assert_terminal_receipt_ready_for_exit",
            "reconcile_terminal_receipt",
            "attest_provider_free_prelaunch",
            "bind_panel_receipt_commit",
        ):
            self.assertIn(f"def {symbol}", source)
        self.assertIn("HANDLED_TERMINAL_RECEIPT_EXIT_CODE = 64", supervisor)
        self.assertIn(
            "persistent_supervisor_contract_schema_v6",
            requirements,
        )
        self.assertIn(
            '"schema_version": "epiagentbench.persistent_supervisor_contract.v11"',
            source,
        )

    def test_current_v16_runbook_is_terminal_and_points_to_v17(self) -> None:
        runbook = (self.root / "docs/V16_RUNBOOK.md").read_text(
            encoding="utf-8"
        )
        self.assertTrue(runbook.startswith("> [!CAUTION]\n"))
        self.assertIn(
            "**TERMINAL AND SUPERSEDED — DO NOT EXECUTE THIS RUNBOOK.**",
            runbook,
        )
        self.assertIn("Do not resume, repair, or reuse any V16", runbook)
        self.assertIn(
            "../results/development-matched-50x6-v16.superseded.json",
            runbook,
        )
        self.assertIn("[V17 runbook](V17_RUNBOOK.md)", runbook)

    def test_v16_terminal_facts_do_not_depend_on_v17_lifecycle(self) -> None:
        runbook = (self.root / "docs/V17_RUNBOOK.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("two-commit, provider-free preparation protocol", runbook)
        self.assertIn("provider processes remain zero", runbook)
        self.assertIn("model calls remain zero", runbook)
        self.assertIs(self.superseded["results_released"], False)
        self.assertIs(self.superseded["scores_released"], False)
        self.assertIs(self.superseded["traces_released"], False)
        self.assertIs(
            self.superseded["public_results_artifact_created"], False
        )

    def test_supersession_contains_no_sensitive_or_scored_payload(self) -> None:
        forbidden_keys = {
            "access_token",
            "api_key",
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
            "schedule",
            "schedule_nonce",
            "score",
            "stderr",
            "stdout",
            "trace",
            "trace_steps",
        }
        self.assertTrue(forbidden_keys.isdisjoint(self._keys(self.superseded)))
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
