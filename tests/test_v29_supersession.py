from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import unittest


def _object_without_duplicate_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _load_json_without_duplicate_keys(raw: bytes) -> object:
    return json.loads(raw, object_pairs_hook=_object_without_duplicate_keys)


class V29SupersessionTests(unittest.TestCase):
    CONTROL_COMMIT = "4a4b25b9481c0163bd3bcd9008f7497778e8ef32"
    RUNTIME_COMMIT = "457347a4a40f51fe19d30977a46880e01bfa0d3e"
    MANIFEST_COMMIT = "aba22c11eafd20445365518e8ab3bea3f670b361"
    AUTHENTICATION_COMMIT = (
        "d93a09c475adc1745a7924328a6869b184358cd8"
    )
    PREFLIGHT_COMMIT = "ae14eb1d6eea1dcd5835907324c205673792db3b"
    PRODUCTION_RESULT_PATH = "results/development-matched-50x6-v29.json"
    PRODUCTION_RESULT_SHA256 = (
        "sha256:649677044193bff4ee4ba6142d11340cea6a7163160216d268b"
        "05fa31bad9634"
    )
    SUPERSESSION_PATH = (
        "results/development-matched-50x6-v29.superseded.json"
    )
    COMMIT_BINDINGS = {
        "control": (
            CONTROL_COMMIT,
            "7f9b61db6ede31a25b07595050c19a05b5032023",
            "81627dc0e50e72cae7a68a31ff602eed7eac09e7",
        ),
        "runtime_receipt": (
            RUNTIME_COMMIT,
            CONTROL_COMMIT,
            "2a9a4e8e5adf9ca38cbb5b077672bc792ad4638f",
        ),
        "manifest": (
            MANIFEST_COMMIT,
            RUNTIME_COMMIT,
            "3fd6d26243934008a9f1c08a4f023f186515c90c",
        ),
        "authentication_receipt": (
            AUTHENTICATION_COMMIT,
            MANIFEST_COMMIT,
            "d4d4a99d63f110e9030dfa267c359f951e21a7cd",
        ),
        "preflight_receipt": (
            PREFLIGHT_COMMIT,
            AUTHENTICATION_COMMIT,
            "9ab99cc499c6a9c730665efd794c0bc7a3f545d6",
        ),
    }
    COMMITTED_PUBLIC_ARTIFACTS = {
        "results/development-matched-50x6-v29.runtime.json": (
            RUNTIME_COMMIT,
            "runtime_receipt_file_sha256",
            "sha256:89cf8ce1f85af928614e4fc82074bb6b6469d3fe5c877c8650b0d8552a9ac48c",
        ),
        "results/development-matched-50x6-v29.manifest.json": (
            MANIFEST_COMMIT,
            "manifest_file_sha256",
            "sha256:95fdcf5ab6cbf6f9c55a83a7aa5f842b039e9028ae57ff1a5331500a0ea50ec0",
        ),
        "results/development-matched-50x6-v29.authentication.json": (
            AUTHENTICATION_COMMIT,
            "authentication_receipt_file_sha256",
            "sha256:106fd837a7d81e61b99b188a0b673c3f645f8c9301834c99c4de81519d877276",
        ),
        "results/development-matched-50x6-v29.preflight.json": (
            PREFLIGHT_COMMIT,
            "preflight_receipt_file_sha256",
            "sha256:4a25078ed7606d2cb4c30b709f0248ec5b0569c82c5f97a423354a0b0f044651",
        ),
    }
    EXPECTED_KEYS = {
        "audited_root_cause_scope",
        "authentication_receipt_commit",
        "authentication_receipt_file_sha256",
        "authentication_receipt_parent_commit",
        "authentication_receipt_self_sha256",
        "authentication_receipt_status",
        "authentication_receipt_tree",
        "completed_production_assignments",
        "control_commit",
        "control_parent_commit",
        "control_tree",
        "credentials_or_oauth_state_inspected",
        "development_only",
        "exact_failed_identity_bytes_proven",
        "exact_identity_failure_evidence_public_source_digest_available",
        "exact_root_cause_proven",
        "exception_text_released",
        "failed_assignment_sealed_as_transport_void",
        "hidden_episode_identifiers_or_families_inspected",
        "host_reboot_observed",
        "identity_mismatch_observed",
        "legacy_identity_causal_alternatives",
        "manifest_commit",
        "manifest_file_sha256",
        "manifest_parent_commit",
        "manifest_precommitment_sha256",
        "manifest_status",
        "manifest_tree",
        "model_bearing_provider_calls_started",
        "model_invocations_conservatively_chargeable",
        "original_panel_id",
        "preflight_model_invocations_conservatively_chargeable",
        "preflight_profiles_recorded",
        "preflight_profiles_terminal",
        "preflight_receipt_commit",
        "preflight_receipt_file_sha256",
        "preflight_receipt_parent_commit",
        "preflight_receipt_schema",
        "preflight_receipt_status",
        "preflight_receipt_tree",
        (
            "prior_authorized_audit_authenticated_private_state_safe_"
            "aggregate_inspected"
        ),
        (
            "prior_authorized_audit_authenticated_supervisor_safe_aggregate_"
            "inspected"
        ),
        "prior_authorized_audit_scope",
        "prior_authenticated_supervisor_live_attestation_failure_code",
        "prior_authenticated_supervisor_process_diagnostic",
        "production_assignments_started",
        "production_assignments_terminal",
        "production_episodes_consumed",
        "production_model_invocations_conservatively_chargeable",
        "production_transport_voids",
        "prompts_or_observations_inspected",
        "protected_payloads_inspected",
        "raw_provider_outputs_inspected",
        "replacement_panel_id",
        "replacement_requirements",
        "replacement_values_status",
        "results_released",
        "resumption_permitted",
        "root_cause_evidence_scope",
        "runtime_receipt_commit",
        "runtime_receipt_file_sha256",
        "runtime_receipt_identity_sha256",
        "runtime_receipt_parent_commit",
        "runtime_receipt_status",
        "runtime_receipt_tree",
        "schema_version",
        "scores_inspected",
        "scores_released",
        "scores_reported",
        "spend_acknowledgement_supplied",
        "spend_authorization_receipt_sha256",
        "spend_authorization_recorded",
        "status",
        "superseded_at_utc",
        "supersession_publication_precedes_v30_version_cut",
        "terminal_execution_incident",
        "terminal_publication_artifacts",
        "terminal_publication_path_resolution",
        "terminal_publication_path_resolved",
        "terminal_receipt_absent_at_preflight_commit",
        "terminal_receipt_attestation_failure_code",
        "terminal_receipt_attestation_function",
        "terminal_receipt_attestation_model_calls_started",
        "terminal_receipt_attestation_operation",
        "terminal_receipt_attestation_provider_free",
        "terminal_receipt_attestation_provider_processes_started",
        "terminal_receipt_attestation_repository_commit",
        "terminal_receipt_attestation_schema",
        "terminal_receipt_attestation_status",
        "terminal_receipt_attestation_succeeded",
        "terminal_receipt_attestation_terminal_assignments",
        "terminal_receipt_attestation_terminal_status",
        "terminal_receipt_completed_assignments",
        "terminal_receipt_failure_stage",
        "terminal_receipt_file_sha256",
        "terminal_receipt_incident_code",
        "terminal_receipt_leaderboard_eligible",
        (
            "terminal_receipt_model_invocations_conservatively_"
            "chargeable"
        ),
        "terminal_receipt_planned_assignments",
        "terminal_receipt_primary_estimand",
        "terminal_receipt_reconstructed",
        "terminal_receipt_results_count",
        "terminal_receipt_schema",
        "terminal_receipt_source_checkout_observation",
        "terminal_receipt_status",
        "terminal_receipt_terminal_assignments",
        "terminal_receipt_transport_voids",
        "timed_out",
        "timeout_stages",
        "traces_inspected",
        "traces_released",
        "v29_cohort_reuse_permitted",
        "v29_identifier_or_namespace_reuse_permitted",
        "v30_acknowledgement_receipt_recorded",
        "v30_commit_or_hash_values_recorded",
    }
    EXPECTED_CAUSAL_ALTERNATIVES = [
        "formatted_kern_boottime_representation_drift",
        (
            "synthetic_wall_minus_monotonic_fallback_persisted_after_"
            "transient_probe_failure"
        ),
    ]
    EXPECTED_REPLACEMENT_REQUIREMENTS = [
        "fresh_panel_and_cohort_identity",
        "fresh_runtime_cache_and_runtime_receipt",
        "fresh_authentication_key_and_provider_namespaces",
        "fresh_private_schedule_and_cohort",
        "fresh_checkout_supervisor_socket_temporary_and_output_namespaces",
        "darwin_bootsessionuuid_identity",
        "darwin_numeric_proc_pidinfo_birth_identity",
        "no_synthetic_process_identity_fallback",
        "identity_unavailable_fails_before_supervisor_state_or_evaluator_start",
        "specific_live_identity_attestation_before_generic_health",
        "v30_supervisor_launchd_protocol_and_contract_version_cut",
        "closed_public_terminal_receipt_and_supersession_path",
        "exact_v30_manifest_bound_spend_authorization",
        "fresh_six_call_preflight_and_independent_publication_validation",
        "separate_explicit_three_hundred_assignment_production_authorization",
    ]
    EXPECTED_TERMINAL_RECEIPT_KEYS = {
        "attestation_failure_code",
        "completed_assignments",
        "development_only",
        "failure_stage",
        "hermetic",
        "incident_code",
        "leaderboard_eligible",
        "model_invocations_conservatively_chargeable",
        "panel_id",
        "planned_assignments",
        "precommitment_sha256",
        "results",
        "schema_version",
        "started_at_utc",
        "status",
        "summary",
        "terminal_assignments",
        "transport_voids",
    }

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.terminal_receipt_raw = (
            cls.root / cls.PRODUCTION_RESULT_PATH
        ).read_bytes()
        terminal_receipt = _load_json_without_duplicate_keys(
            cls.terminal_receipt_raw
        )
        if not isinstance(terminal_receipt, dict):
            raise TypeError("V29 terminal receipt must be a JSON object")
        cls.terminal_receipt = terminal_receipt
        cls.supersession_raw = (cls.root / cls.SUPERSESSION_PATH).read_bytes()
        supersession = _load_json_without_duplicate_keys(cls.supersession_raw)
        if not isinstance(supersession, dict):
            raise TypeError("V29 supersession must be a JSON object")
        cls.supersession = supersession
        cls.runtime = cls._read(
            "results/development-matched-50x6-v29.runtime.json"
        )
        cls.manifest = cls._read(
            "results/development-matched-50x6-v29.manifest.json"
        )
        cls.authentication = cls._read(
            "results/development-matched-50x6-v29.authentication.json"
        )
        cls.preflight = cls._read(
            "results/development-matched-50x6-v29.preflight.json"
        )

    @classmethod
    def _read(cls, relative: str) -> dict[str, object]:
        payload = _load_json_without_duplicate_keys(
            (cls.root / relative).read_bytes()
        )
        if not isinstance(payload, dict):
            raise TypeError(f"{relative} must contain a JSON object")
        return payload

    @staticmethod
    def _keys(payload: object) -> set[str]:
        observed: set[str] = set()
        if isinstance(payload, Mapping):
            for key, value in payload.items():
                observed.add(str(key))
                observed.update(V29SupersessionTests._keys(value))
        elif isinstance(payload, Sequence) and not isinstance(
            payload, (str, bytes, bytearray)
        ):
            for value in payload:
                observed.update(V29SupersessionTests._keys(value))
        return observed

    @staticmethod
    def _strings(payload: object) -> list[str]:
        observed: list[str] = []
        if isinstance(payload, str):
            observed.append(payload)
        elif isinstance(payload, Mapping):
            for value in payload.values():
                observed.extend(V29SupersessionTests._strings(value))
        elif isinstance(payload, Sequence) and not isinstance(
            payload, (str, bytes, bytearray)
        ):
            for value in payload:
                observed.extend(V29SupersessionTests._strings(value))
        return observed

    def _git_show_bytes(self, commit: str, relative: str) -> bytes:
        return subprocess.run(
            ["git", "show", f"{commit}:{relative}"],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout

    def test_duplicate_json_object_keys_are_rejected(self) -> None:
        with self.assertRaisesRegex(
            ValueError, r"duplicate JSON object key: status"
        ):
            _load_json_without_duplicate_keys(
                b'{"status":"first","status":"second"}'
            )

    def test_closed_schema_and_deterministic_encoding(self) -> None:
        self.assertEqual(set(self.supersession), self.EXPECTED_KEYS)
        self.assertEqual(
            self.supersession["schema_version"],
            "epiagentbench.panel_supersession.v22",
        )
        expected = (
            json.dumps(self.supersession, sort_keys=True, indent=2) + "\n"
        ).encode("utf-8")
        self.assertEqual(self.supersession_raw, expected)

    def test_exact_v29_commit_chain_and_public_bytes_are_bound(self) -> None:
        for prefix, (commit, parent, tree) in self.COMMIT_BINDINGS.items():
            observed = subprocess.run(
                ["git", "show", "-s", "--format=%H %P %T", commit],
                cwd=self.root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            ).stdout.strip()
            self.assertEqual(observed, f"{commit} {parent} {tree}")
            self.assertEqual(self.supersession[f"{prefix}_commit"], commit)
            self.assertEqual(
                self.supersession[f"{prefix}_parent_commit"], parent
            )
            self.assertEqual(self.supersession[f"{prefix}_tree"], tree)

        for relative, (commit, field, expected) in (
            self.COMMITTED_PUBLIC_ARTIFACTS.items()
        ):
            historical = self._git_show_bytes(commit, relative)
            current = (self.root / relative).read_bytes()
            self.assertEqual(current, historical)
            observed = "sha256:" + hashlib.sha256(historical).hexdigest()
            self.assertEqual(observed, expected)
            self.assertEqual(self.supersession[field], expected)

    def test_committed_receipts_are_internally_bound(self) -> None:
        self.assertEqual(
            self.runtime["status"],
            self.supersession["runtime_receipt_status"],
        )
        self.assertEqual(self.runtime["status"], "passed")
        self.assertEqual(
            self.runtime["runtime_identity_sha256"],
            self.supersession["runtime_receipt_identity_sha256"],
        )
        self.assertEqual(
            self.manifest["status"], self.supersession["manifest_status"]
        )
        self.assertEqual(self.manifest["status"], "precommitted")
        self.assertEqual(
            self.manifest["precommitment_sha256"],
            self.supersession["manifest_precommitment_sha256"],
        )
        self.assertEqual(
            self.authentication["status"],
            self.supersession["authentication_receipt_status"],
        )
        self.assertEqual(self.authentication["status"], "passed")
        self.assertEqual(
            self.authentication["receipt_sha256"],
            self.supersession["authentication_receipt_self_sha256"],
        )
        self.assertEqual(
            self.authentication["spend_authorization_receipt_sha256"],
            self.supersession["spend_authorization_receipt_sha256"],
        )
        self.assertEqual(self.authentication["model_calls_started"], 0)
        self.assertEqual(
            self.authentication["production_episodes_consumed"], 0
        )
        self.assertIs(self.authentication["scores_reported"], False)

        self.assertEqual(
            self.preflight["status"],
            self.supersession["preflight_receipt_status"],
        )
        self.assertEqual(self.preflight["status"], "passed")
        self.assertEqual(
            self.preflight["schema_version"],
            self.supersession["preflight_receipt_schema"],
        )
        self.assertEqual(
            self.preflight["precommitment_sha256"],
            self.supersession["manifest_precommitment_sha256"],
        )
        self.assertEqual(
            self.preflight["model_invocations_conservatively_chargeable"],
            self.supersession[
                "preflight_model_invocations_conservatively_chargeable"
            ],
        )
        self.assertEqual(len(self.preflight["profiles"]), 6)
        self.assertEqual(len(self.preflight["profiles_passed"]), 6)
        self.assertEqual(self.preflight["production_episodes_consumed"], 0)
        self.assertIs(self.preflight["scores_reported"], False)

    def test_exact_terminal_receipt_precedes_supersession_publication(
        self,
    ) -> None:
        committed_at_preflight = subprocess.run(
            [
                "git",
                "cat-file",
                "-e",
                f"{self.PREFLIGHT_COMMIT}:{self.PRODUCTION_RESULT_PATH}",
            ],
            cwd=self.root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertNotEqual(committed_at_preflight.returncode, 0)
        self.assertIs(
            self.supersession["terminal_receipt_absent_at_preflight_commit"],
            True,
        )
        self.assertEqual(
            "sha256:" + hashlib.sha256(self.terminal_receipt_raw).hexdigest(),
            self.PRODUCTION_RESULT_SHA256,
        )
        self.assertEqual(
            self.supersession["terminal_receipt_file_sha256"],
            self.PRODUCTION_RESULT_SHA256,
        )
        self.assertEqual(
            self.supersession["terminal_publication_artifacts"],
            [self.PRODUCTION_RESULT_PATH, self.SUPERSESSION_PATH],
        )
        self.assertEqual(
            len(self.supersession["terminal_publication_artifacts"]),
            len(set(self.supersession["terminal_publication_artifacts"])),
        )
        self.assertEqual(
            self.supersession["terminal_publication_path_resolution"],
            (
                "exact_terminal_receipt_then_supersession_same_v29_closeout_"
                "commit"
            ),
        )
        self.assertIs(
            self.supersession["terminal_publication_path_resolved"], True
        )
        self.assertIs(
            self.supersession["terminal_receipt_reconstructed"], False
        )
        self.assertEqual(
            self.supersession["terminal_receipt_source_checkout_observation"],
            (
                "untracked_in_authorized_v29_production_checkout_before_"
                "closeout_promotion"
            ),
        )

    def test_terminal_receipt_closed_schema_and_safe_aggregate_mirrors(
        self,
    ) -> None:
        receipt = self.terminal_receipt
        self.assertEqual(set(receipt), self.EXPECTED_TERMINAL_RECEIPT_KEYS)
        expected_bytes = (
            json.dumps(receipt, sort_keys=True, indent=2) + "\n"
        ).encode("utf-8")
        self.assertEqual(self.terminal_receipt_raw, expected_bytes)
        direct_mirrors = {
            "attestation_failure_code": (
                "terminal_receipt_attestation_failure_code"
            ),
            "completed_assignments": "terminal_receipt_completed_assignments",
            "failure_stage": "terminal_receipt_failure_stage",
            "incident_code": "terminal_receipt_incident_code",
            "leaderboard_eligible": "terminal_receipt_leaderboard_eligible",
            "model_invocations_conservatively_chargeable": (
                "terminal_receipt_model_invocations_conservatively_chargeable"
            ),
            "planned_assignments": "terminal_receipt_planned_assignments",
            "schema_version": "terminal_receipt_schema",
            "status": "terminal_receipt_status",
            "terminal_assignments": "terminal_receipt_terminal_assignments",
            "transport_voids": "terminal_receipt_transport_voids",
        }
        for receipt_field, supersession_field in direct_mirrors.items():
            self.assertEqual(
                receipt[receipt_field],
                self.supersession[supersession_field],
                receipt_field,
            )
        self.assertEqual(
            receipt["schema_version"], "development_matched_panel_v29"
        )
        self.assertEqual(receipt["status"], "stopped_supervisor_incident")
        self.assertEqual(receipt["planned_assignments"], 300)
        self.assertEqual(receipt["terminal_assignments"], 26)
        self.assertEqual(receipt["completed_assignments"], 25)
        self.assertEqual(receipt["transport_voids"], 1)
        self.assertEqual(
            receipt["model_invocations_conservatively_chargeable"], 26
        )
        self.assertEqual(receipt["results"], [])
        self.assertEqual(
            self.supersession["terminal_receipt_results_count"], 0
        )
        self.assertEqual(receipt["summary"], {"primary_estimand": "pending"})
        self.assertEqual(
            receipt["summary"]["primary_estimand"],
            self.supersession["terminal_receipt_primary_estimand"],
        )
        self.assertIs(receipt["leaderboard_eligible"], False)
        self.assertEqual(
            receipt["incident_code"], "provider_execution_isolation_failed"
        )
        self.assertEqual(
            receipt["failure_stage"], "supervisor_attestation_after_provider"
        )
        self.assertEqual(
            receipt["attestation_failure_code"], "core_unhealthy"
        )
        self.assertEqual(
            receipt["precommitment_sha256"],
            self.supersession["manifest_precommitment_sha256"],
        )
        started_at = datetime.fromisoformat(
            str(receipt["started_at_utc"]).replace("Z", "+00:00")
        )
        self.assertEqual(started_at.tzinfo, timezone.utc)

    def test_provider_free_terminal_receipt_attestation_is_whitelisted(
        self,
    ) -> None:
        expected = {
            "terminal_receipt_attestation_function": (
                "assert_terminal_receipt_ready_for_exit"
            ),
            "terminal_receipt_attestation_schema": (
                "epiagentbench.terminal_receipt_attestation.v1"
            ),
            "terminal_receipt_attestation_status": "attested",
            "terminal_receipt_attestation_operation": "production",
            "terminal_receipt_attestation_terminal_status": (
                "stopped_supervisor_incident"
            ),
            "terminal_receipt_attestation_terminal_assignments": 26,
            "terminal_receipt_attestation_repository_commit": (
                self.PREFLIGHT_COMMIT
            ),
            "terminal_receipt_attestation_provider_processes_started": 0,
            "terminal_receipt_attestation_model_calls_started": 0,
        }
        for field, value in expected.items():
            self.assertEqual(self.supersession[field], value, field)
        self.assertIs(
            self.supersession["terminal_receipt_attestation_succeeded"],
            True,
        )
        self.assertIs(
            self.supersession["terminal_receipt_attestation_provider_free"],
            True,
        )

    def test_terminal_accounting_is_closed_and_non_scientific(self) -> None:
        self.assertEqual(
            self.supersession["status"],
            "terminal_supervisor_incident_superseded",
        )
        self.assertEqual(
            self.supersession["model_bearing_provider_calls_started"], 32
        )
        self.assertEqual(
            self.supersession["model_invocations_conservatively_chargeable"],
            32,
        )
        self.assertEqual(
            self.supersession[
                "preflight_model_invocations_conservatively_chargeable"
            ],
            6,
        )
        self.assertEqual(
            self.supersession[
                "production_model_invocations_conservatively_chargeable"
            ],
            26,
        )
        self.assertEqual(self.supersession["preflight_profiles_recorded"], 6)
        self.assertEqual(self.supersession["preflight_profiles_terminal"], 6)
        self.assertEqual(
            self.supersession["production_assignments_started"], 26
        )
        self.assertEqual(
            self.supersession["production_assignments_terminal"], 26
        )
        self.assertEqual(
            self.supersession["completed_production_assignments"], 25
        )
        self.assertEqual(
            self.supersession["production_episodes_consumed"], 26
        )
        self.assertEqual(self.supersession["production_transport_voids"], 1)
        self.assertIs(
            self.supersession["failed_assignment_sealed_as_transport_void"],
            True,
        )
        for field in (
            "results_released",
            "scores_released",
            "scores_reported",
            "timed_out",
            "traces_released",
        ):
            self.assertIs(self.supersession[field], False, field)
        self.assertEqual(self.supersession["timeout_stages"], [])

    def test_audit_preserves_causal_uncertainty_and_nonresumability(
        self,
    ) -> None:
        self.assertEqual(
            self.supersession["audited_root_cause_scope"],
            "post_provider_supervisor_attestation",
        )
        self.assertEqual(
            self.supersession[
                "prior_authenticated_supervisor_live_attestation_failure_code"
            ],
            "process_identity_mismatch",
        )
        self.assertEqual(
            self.supersession[
                "prior_authenticated_supervisor_process_diagnostic"
            ],
            "boot_mismatch",
        )
        self.assertIs(self.supersession["identity_mismatch_observed"], True)
        self.assertIs(self.supersession["host_reboot_observed"], False)
        self.assertIs(
            self.supersession["exact_failed_identity_bytes_proven"],
            False,
        )
        self.assertIs(self.supersession["exact_root_cause_proven"], False)
        self.assertEqual(
            self.supersession["legacy_identity_causal_alternatives"],
            self.EXPECTED_CAUSAL_ALTERNATIVES,
        )
        self.assertEqual(
            len(self.EXPECTED_CAUSAL_ALTERNATIVES),
            len(set(self.EXPECTED_CAUSAL_ALTERNATIVES)),
        )
        self.assertEqual(
            self.supersession["prior_authorized_audit_scope"],
            (
                "authenticated_private_state_and_supervisor_safe_aggregate_"
                "projections_only"
            ),
        )
        self.assertIs(
            self.supersession[
                "prior_authorized_audit_authenticated_private_state_safe_"
                "aggregate_inspected"
            ],
            True,
        )
        self.assertIs(
            self.supersession[
                "prior_authorized_audit_authenticated_supervisor_safe_"
                "aggregate_inspected"
            ],
            True,
        )
        self.assertEqual(
            self.supersession["root_cause_evidence_scope"],
            (
                "prior_authorized_authenticated_safe_aggregate_projections_"
                "without_public_source_digest"
            ),
        )
        self.assertIs(
            self.supersession[
                "exact_identity_failure_evidence_public_source_digest_"
                "available"
            ],
            False,
        )
        for field in (
            "credentials_or_oauth_state_inspected",
            "hidden_episode_identifiers_or_families_inspected",
            "prompts_or_observations_inspected",
            "protected_payloads_inspected",
            "raw_provider_outputs_inspected",
            "scores_inspected",
            "traces_inspected",
        ):
            self.assertIs(self.supersession[field], False, field)
        self.assertIs(
            self.supersession[
                "supersession_publication_precedes_v30_version_cut"
            ],
            True,
        )
        self.assertIs(self.supersession["terminal_execution_incident"], True)
        self.assertIs(self.supersession["resumption_permitted"], False)
        self.assertIs(
            self.supersession["v29_cohort_reuse_permitted"], False
        )
        self.assertIs(
            self.supersession[
                "v29_identifier_or_namespace_reuse_permitted"
            ],
            False,
        )

    def test_v30_requirements_are_finite_but_values_remain_unset(self) -> None:
        self.assertEqual(
            self.supersession["replacement_panel_id"],
            "development-matched-50x6-v30",
        )
        self.assertEqual(
            self.supersession["replacement_requirements"],
            self.EXPECTED_REPLACEMENT_REQUIREMENTS,
        )
        self.assertEqual(
            len(self.EXPECTED_REPLACEMENT_REQUIREMENTS),
            len(set(self.EXPECTED_REPLACEMENT_REQUIREMENTS)),
        )
        self.assertEqual(
            self.supersession["replacement_values_status"],
            "not_yet_created_or_authorized",
        )
        self.assertIs(
            self.supersession["v30_acknowledgement_receipt_recorded"], False
        )
        self.assertIs(
            self.supersession["v30_commit_or_hash_values_recorded"], False
        )
        self.assertTrue(
            {
                "replacement_manifest_commit",
                "replacement_runtime_commit",
                "required_v30_acknowledgement_text_sha256",
                "v30_manifest_precommitment_sha256",
            }.isdisjoint(self.supersession)
        )

    def test_public_terminal_receipt_and_supersession_are_trace_free(
        self,
    ) -> None:
        forbidden_keys = {
            "access_token",
            "api_key",
            "argv",
            "credential",
            "credential_contents",
            "episode_id",
            "episode_ref",
            "exception",
            "family",
            "hidden_episode_identifier",
            "observation",
            "oauth_state",
            "private_path",
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
        forbidden_string_fragments = (
            "/users/",
            "\\users\\",
            "access_token",
            "api_key",
            "credential",
            "episode_",
            "episode_ref",
            "family",
            "file://",
            "hidden_episode",
            "oauth_state",
            "observation",
            "pack_commitment",
            "private_seed",
            "prompt",
            "provider_output",
            "raw_output",
            "refresh_token",
            "replay_trace",
            "score",
            "trace_steps",
        )
        for label, payload in (
            ("terminal receipt", self.terminal_receipt),
            ("supersession", self.supersession),
        ):
            self.assertTrue(
                forbidden_keys.isdisjoint(self._keys(payload)), label
            )
            for value in self._strings(payload):
                lowered = value.lower()
                self.assertFalse(
                    lowered.startswith(("/", "~", "file://")),
                    (label, value),
                )
                self.assertNotIn("\n", value, (label, value))
                for fragment in forbidden_string_fragments:
                    self.assertNotIn(fragment, lowered, (label, value))
        self.assertIs(self.supersession["exception_text_released"], False)

    def test_supersession_timestamp_is_utc_and_after_preflight(self) -> None:
        superseded_at = datetime.fromisoformat(
            str(self.supersession["superseded_at_utc"]).replace("Z", "+00:00")
        )
        preflight_completed_at = datetime.fromisoformat(
            str(self.preflight["completed_at_utc"]).replace("Z", "+00:00")
        )
        self.assertEqual(superseded_at.tzinfo, timezone.utc)
        self.assertGreater(superseded_at, preflight_completed_at)
        self.assertLessEqual(superseded_at, datetime.now(timezone.utc))


if __name__ == "__main__":
    unittest.main()
