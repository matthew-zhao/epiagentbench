from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
from pathlib import Path
import unittest


class V18SupersessionTests(unittest.TestCase):
    PUBLIC_FILE_HASHES = {
        "results/development-matched-50x6-v18.runtime.json": (
            "sha256:f9268a75d61f03dca3e2a1c807bfc714b2e65beed9551d16"
            "c48e73e3a0c83d65"
        ),
        "results/development-matched-50x6-v18.manifest.json": (
            "sha256:7efbd6314964146eef9d2a960b307d851fa22d191355976b20"
            "a46843f00d728a"
        ),
        "results/development-matched-50x6-v18.authentication.json": (
            "sha256:5954c933500b8006098fa9388e9e44b904fbf34221ec59d922"
            "b3afc0d71145de"
        ),
        "results/development-matched-50x6-v18.preflight.json": (
            "sha256:4e4211007e96705e8c745f021d5485713f48d8093e4e1163e9"
            "401f06e815faff"
        ),
    }
    PUBLIC_COMMITS = {
        "runtime_receipt_commit": (
            "7d4f337e7f02dc6366d5daf16bc0a5a333943fb0"
        ),
        "manifest_commit": (
            "a8949892137086929170ec0f4ec99015a351834c"
        ),
        "authentication_receipt_commit": (
            "cc674363b87f037458447996c88cc2cc8ad09945"
        ),
        "preflight_receipt_commit": (
            "d9d59cf637684fc45dad3fb6a2097fa455b831a6"
        ),
    }
    ACKNOWLEDGEMENT = (
        "I acknowledge the replacement six-call v19 preflight and "
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
        "runtime-cache-environment refusal, the failed v18 preflight, and "
        "the v19 preflight and production run."
    )

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.runtime = json.loads(
            (
                cls.root
                / "results/development-matched-50x6-v18.runtime.json"
            ).read_bytes()
        )
        cls.manifest = json.loads(
            (
                cls.root
                / "results/development-matched-50x6-v18.manifest.json"
            ).read_bytes()
        )
        cls.authentication = json.loads(
            (
                cls.root
                / "results/development-matched-50x6-v18.authentication.json"
            ).read_bytes()
        )
        cls.preflight = json.loads(
            (
                cls.root
                / "results/development-matched-50x6-v18.preflight.json"
            ).read_bytes()
        )
        cls.superseded = json.loads(
            (
                cls.root
                / "results/development-matched-50x6-v18.superseded.json"
            ).read_bytes()
        )

    @staticmethod
    def _keys(payload: object) -> set[str]:
        observed: set[str] = set()
        if isinstance(payload, Mapping):
            for key, value in payload.items():
                observed.add(str(key))
                observed.update(V18SupersessionTests._keys(value))
        elif isinstance(payload, Sequence) and not isinstance(
            payload, (str, bytes, bytearray)
        ):
            for value in payload:
                observed.update(V18SupersessionTests._keys(value))
        return observed

    def test_supersession_binds_exact_public_v18_artifacts(self) -> None:
        for relative, expected in self.PUBLIC_FILE_HASHES.items():
            observed = "sha256:" + hashlib.sha256(
                (self.root / relative).read_bytes()
            ).hexdigest()
            self.assertEqual(observed, expected)
        self.assertEqual(
            self.superseded["runtime_receipt_file_sha256"],
            self.PUBLIC_FILE_HASHES[
                "results/development-matched-50x6-v18.runtime.json"
            ],
        )
        self.assertEqual(
            self.superseded["manifest_file_sha256"],
            self.PUBLIC_FILE_HASHES[
                "results/development-matched-50x6-v18.manifest.json"
            ],
        )
        self.assertEqual(
            self.superseded["authentication_receipt_file_sha256"],
            self.PUBLIC_FILE_HASHES[
                "results/development-matched-50x6-v18.authentication.json"
            ],
        )
        self.assertEqual(
            self.superseded["preflight_receipt_file_sha256"],
            self.PUBLIC_FILE_HASHES[
                "results/development-matched-50x6-v18.preflight.json"
            ],
        )
        for field, expected in self.PUBLIC_COMMITS.items():
            self.assertEqual(self.superseded[field], expected)
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

    def test_supersession_preserves_legacy_public_projection(self) -> None:
        projection = self.superseded["legacy_public_preflight_projection"]
        for field in (
            "status",
            "failure_reason",
            "failure_stage",
            "incident_code",
            "failed_provider_invocation_state",
            "timed_out",
        ):
            self.assertEqual(projection[field], self.preflight[field])
        self.assertEqual(
            self.superseded[
                "model_bearing_provider_calls_conservatively_chargeable"
            ],
            self.preflight["provider_calls_conservatively_chargeable"],
        )
        states: dict[str, int] = {}
        for profile in self.preflight["profiles"]:
            state = profile["invocation_state"]
            states[state] = states.get(state, 0) + 1
        self.assertEqual(
            self.superseded["preflight_profile_states"], states
        )
        self.assertEqual(self.superseded["preflight_profiles_attempted"], 1)
        self.assertEqual(self.superseded["preflight_profiles_passed"], 0)

    def test_inferred_root_cause_does_not_rewrite_v18_accounting(self) -> None:
        self.assertEqual(
            self.superseded["status"],
            "failed_preflight_provider_cli_readiness",
        )
        self.assertEqual(
            self.superseded["audited_root_cause_code"],
            "non_model_provider_cli_readiness_timeout_before_model_bearing_spawn",
        )
        self.assertEqual(
            self.superseded["root_cause_evidence_level"],
            "strong_control_path_inference_without_raw_provider_output",
        )
        self.assertIs(
            self.superseded[
                "historical_accounting_retroactively_reclassified"
            ],
            False,
        )
        self.assertIs(
            self.superseded["model_bearing_provider_call_exposure_proven"],
            False,
        )
        self.assertEqual(
            self.superseded["model_bearing_provider_spawn_evidence"],
            "not_proven_by_v18_legacy_early_marker_boundary",
        )
        self.assertEqual(
            self.superseded["v18_conservative_claude_ceiling_added_usd"],
            5,
        )

    def test_v18_is_terminal_and_v19_documents_the_new_boundary(self) -> None:
        self.assertEqual(
            self.superseded["schema_version"],
            "epiagentbench.panel_supersession.v10",
        )
        self.assertEqual(
            self.superseded["replacement_panel_id"],
            "development-matched-50x6-v19",
        )
        self.assertIs(self.superseded["resumption_permitted"], False)
        self.assertIs(
            self.superseded["v18_cohort_reuse_permitted"], False
        )
        self.assertIs(
            self.superseded["v18_key_or_namespace_reuse_permitted"], False
        )
        requirements = set(self.superseded["replacement_requirements"])
        self.assertTrue(
            {
                "typed_provider_cli_readiness_timeout",
                "non_model_cli_readiness_before_model_invocation_marker",
                (
                    "durable_model_invocation_marker_immediately_before_"
                    "model_bearing_spawn"
                ),
                "chargeability_derived_from_model_invocation_state",
                "identical_preflight_and_production_accounting_boundary",
                "persistent_supervisor_contract_schema_v8",
                "launchd_config_schema_v11",
                "persistent_supervisor_execution_protocol_v5",
            }.issubset(requirements)
        )
        v18_runbook = (self.root / "docs/V18_RUNBOOK.md").read_text(
            encoding="utf-8"
        )
        self.assertTrue(v18_runbook.startswith("> [!CAUTION]\n"))
        self.assertIn(
            "**TERMINAL AND SUPERSEDED — DO NOT EXECUTE THIS RUNBOOK.**",
            v18_runbook,
        )
        self.assertIn(
            "../results/development-matched-50x6-v18.superseded.json",
            v18_runbook,
        )
        self.assertIn("[V19 runbook](V19_RUNBOOK.md)", v18_runbook)
        v19_runbook = (self.root / "docs/V19_RUNBOOK.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("V19 model-invocation accounting boundary", v19_runbook)
        self.assertIn(self.ACKNOWLEDGEMENT, v19_runbook)
        self.assertEqual(
            "sha256:"
            + hashlib.sha256(self.ACKNOWLEDGEMENT.encode("utf-8")).hexdigest(),
            "sha256:1d60c684287f542b212e02004ac6f434058d5a49dd6c46f035bb450bc279e344",
        )

    def test_v18_released_no_production_result_score_or_trace(self) -> None:
        self.assertEqual(
            self.preflight["production_episodes_consumed"], 0
        )
        self.assertIs(self.preflight["scores_reported"], False)
        self.assertFalse(
            (
                self.root / "results/development-matched-50x6-v18.json"
            ).exists()
        )
        for field in (
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
        self.assertTrue(forbidden_keys.isdisjoint(self._keys(self.superseded)))
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
