from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import json
from pathlib import Path
import re
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


class V35SupersessionTests(unittest.TestCase):
    CONTROL_COMMIT = "818b0313eb14e3b31431b267626d8d4a61fa5559"
    CONTROL_PARENT_COMMIT = "038794aa1bf82440259c62afdabab44c01415978"
    CONTROL_TREE = "f704a9ffd21f7e2ca547b8f502492f477312b5d2"
    SUPERSESSION_PATH = "results/development-matched-50x6-v35.superseded.json"
    TEST_PATH = "tests/test_v35_supersession.py"
    CLOSEOUT_REF = "refs/heads/codex/v40-v35-runtime-publication-terminal-closeout"
    REPLACEMENT_REQUIREMENTS = (
        "fresh_panel_and_cohort_identity",
        "fresh_runtime_cache_and_runtime_receipt",
        "fresh_authentication_key_and_provider_namespaces",
        "fresh_private_schedule_and_cohort",
        "fresh_checkout_supervisor_socket_temporary_and_output_namespaces",
        "closed_public_v35_runtime_publication_supersession_path",
        "fresh_v40_control_plane",
        "independently_pinned_v40_control_plane",
        "independently_pinned_v40_runtime_receipt_before_manifest",
        "create_once_provider_free_runtime_publication_terminal_closeout",
        "fresh_v40_manifest_bound_spend_authorization",
        "fresh_six_call_preflight_and_independent_publication_validation",
        "separate_explicit_three_hundred_assignment_production_authorization",
    )
    EXPECTED_INCIDENTS: tuple[dict[str, object], ...] = (
        {
            "cause_code": "gitbutler_runtime_receipt_publisher_target_mismatch",
            "gitbutler_commit_invocations": 0,
            "gitbutler_push_invocations": 0,
            "namespace": "v35_runtime_receipt_publisher",
            "publisher_setup_invocations": 1,
            "publisher_setup_succeeded": True,
            "publisher_target_validation_attempts": 1,
            "publisher_target_validation_passed": False,
            "remote_mutation_observed": False,
            "required_target_ref": "origin/codex/v35-control-plane",
            "runtime_receipt_copy_invocations": 0,
            "stage": "gitbutler_runtime_receipt_publisher_target_validation_before_runtime_receipt_copy",
            "validated_target_ref": "origin/main",
        },
        {
            "cause_code": "gitbutler_setup_missing_remote_head",
            "credential_routing_invocations": 0,
            "files_authored": 0,
            "gitbutler_commit_invocations": 0,
            "gitbutler_push_invocations": 0,
            "namespace": "v35_terminal_closeout_publisher",
            "publisher_clone_attempts": 1,
            "publisher_clone_succeeded": True,
            "publisher_setup_invocations": 1,
            "publisher_setup_succeeded": False,
            "remote_head_binding_invocations": 0,
            "remote_mutation_observed": False,
            "stage": "gitbutler_terminal_closeout_publisher_setup_before_file_authoring",
        },
        {
            "cause_code": "successor_precreation_shell_unset_parameter_before_mutation",
            "credential_routing_invocations": 0,
            "files_authored": 0,
            "gitbutler_commit_invocations": 0,
            "gitbutler_push_invocations": 0,
            "namespace": "v36_successor_terminal_bridge",
            "precreation_gate_attempts": 1,
            "precreation_gate_passed": False,
            "publisher_clone_attempts": 0,
            "publisher_setup_invocations": 0,
            "remote_head_binding_invocations": 0,
            "remote_mutation_observed": False,
            "stage": "successor_terminal_bridge_precreation_gate_before_mutation",
        },
        {
            "cause_code": "contradictory_fresh_path_observations_before_mutation",
            "credential_routing_invocations": 0,
            "destination_ref_queries_passed": 2,
            "files_authored": 0,
            "fixed_origin_control_ref_queries_passed": 2,
            "followup_fresh_path_observation": "absent",
            "fresh_path_gate_attempts": 1,
            "fresh_path_gate_result": "ambiguous",
            "gitbutler_commit_invocations": 0,
            "gitbutler_push_invocations": 0,
            "initial_fresh_path_observation": "present",
            "namespace": "v37_successor_terminal_bridge",
            "precreation_gate_passed": False,
            "publisher_clone_attempts": 0,
            "publisher_setup_invocations": 0,
            "remote_head_binding_invocations": 0,
            "remote_mutation_observed": False,
            "stage": "successor_terminal_bridge_fresh_path_gate_before_mutation",
        },
        {
            "but_diff_invocations": 1,
            "cause_code": "successor_bridge_formatter_executable_unavailable_on_invoked_path",
            "credential_routing_invocations": 0,
            "exact_contract_unittest_invocations_after_wording_edit": 1,
            "exact_contract_unittest_passed_after_wording_edit": 1,
            "files_authored": 2,
            "format_validation_passed": False,
            "formatter_command_invocations": 1,
            "formatter_executable_resolved": False,
            "formatter_processes_started": 0,
            "formatter_writes": 0,
            "gitbutler_commit_invocations": 0,
            "gitbutler_push_invocations": 0,
            "namespace": "v38_successor_terminal_bridge",
            "optional_pytest_invocations": 1,
            "optional_pytest_module_available": False,
            "optional_pytest_tests_run": 0,
            "post_optional_pytest_failure_local_read_audit_performed": True,
            "post_optional_pytest_failure_wording_edits": 1,
            "precreation_gate_attempts": 1,
            "precreation_gate_passed": True,
            "precreation_read_checks": 8,
            "precreation_read_checks_passed": 8,
            "publisher_clone_attempts": 1,
            "publisher_clone_succeeded": True,
            "publisher_setup_invocations": 1,
            "publisher_setup_succeeded": True,
            "release_clone_attempts": 0,
            "remote_head_binding_invocations": 1,
            "remote_head_binding_succeeded": True,
            "remote_mutation_observed": False,
            "stage": "successor_terminal_bridge_format_validation_after_file_authoring_before_commit",
            "targeted_unittest_active_tests_passed": 18,
            "targeted_unittest_invocations": 2,
            "targeted_unittest_topology_tests_skipped": 2,
            "terminal_stop_applied_after_optional_pytest_failure": False,
        },
        {
            "application_storage_write_denials_observed": 1,
            "authoritative_base_shape_validation_invocations": 1,
            "authoritative_base_shape_validation_passed": True,
            "but_diff_invocations": 0,
            "cause_code": "gitbutler_application_storage_write_sandbox_denied_during_setup",
            "credential_routing_invocations": 0,
            "destination_ref_queries_passed": 2,
            "files_authored": 0,
            "fixed_origin_control_ref_queries_passed": 2,
            "formatter_command_invocations": 0,
            "gitbutler_binary_validation_passed": True,
            "gitbutler_commit_invocations": 0,
            "gitbutler_push_invocations": 0,
            "identity_configuration_invocations": 0,
            "mutually_exclusive_ref_bundle_queries_passed": 2,
            "namespace": "v39_successor_terminal_bridge",
            "optional_pytest_invocations": 0,
            "precreation_remote_and_fresh_path_gate_passed": True,
            "publisher_clone_attempts": 1,
            "publisher_clone_succeeded": True,
            "publisher_setup_invocations": 1,
            "publisher_setup_retry_invocations": 0,
            "publisher_setup_succeeded": False,
            "publisher_workspace_fresh_path_queries_passed": 2,
            "python_validation_passed": True,
            "release_clone_attempts": 0,
            "release_workspace_fresh_path_queries_passed": 2,
            "remote_head_binding_invocations": 1,
            "remote_head_binding_succeeded": True,
            "remote_mutation_observed": False,
            "ruff_validation_passed": True,
            "stage": "successor_terminal_bridge_gitbutler_setup_after_remote_head_binding_before_identity_and_file_authoring",
            "targeted_unittest_invocations": 0,
        },
    )

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.raw = (cls.root / cls.SUPERSESSION_PATH).read_bytes()
        payload = json.loads(cls.raw, object_pairs_hook=_object_without_duplicate_keys)
        if not isinstance(payload, dict):
            raise TypeError("V35 supersession must be a JSON object")
        cls.superseded = payload

    @staticmethod
    def _keys(payload: object) -> set[str]:
        observed: set[str] = set()
        if isinstance(payload, Mapping):
            for key, value in payload.items():
                observed.add(str(key))
                observed.update(V35SupersessionTests._keys(value))
        elif isinstance(payload, Sequence) and not isinstance(
            payload, (str, bytes, bytearray)
        ):
            for value in payload:
                observed.update(V35SupersessionTests._keys(value))
        return observed

    @staticmethod
    def _strings(payload: object) -> list[str]:
        observed: list[str] = []
        if isinstance(payload, str):
            observed.append(payload)
        elif isinstance(payload, Mapping):
            for value in payload.values():
                observed.extend(V35SupersessionTests._strings(value))
        elif isinstance(payload, Sequence) and not isinstance(
            payload, (str, bytes, bytearray)
        ):
            for value in payload:
                observed.extend(V35SupersessionTests._strings(value))
        return observed

    def test_canonical_duplicate_free_record(self) -> None:
        expected = (
            json.dumps(self.superseded, sort_keys=True, indent=2) + "\n"
        ).encode()
        self.assertEqual(self.raw, expected)

    def test_exact_public_contract(self) -> None:
        expected: dict[str, object] = {
            "audited_root_cause_code": "gitbutler_runtime_receipt_publisher_target_mismatch",
            "authentication_cli_invocations": 0,
            "authentication_processes_started": 0,
            "authentication_receipt_created": False,
            "candidate_bodies_released": False,
            "candidate_hashes_released": False,
            "candidate_paths_released": False,
            "control_commit": self.CONTROL_COMMIT,
            "control_parent_commit": self.CONTROL_PARENT_COMMIT,
            "control_plane_independently_pinned": True,
            "control_plane_publication_attempts": 1,
            "control_plane_publication_succeeded": True,
            "control_plane_remote_ref_present": True,
            "control_ref": "refs/heads/codex/v35-control-plane",
            "control_tree": self.CONTROL_TREE,
            "credential_routing_invocations_during_terminal_events": 0,
            "credential_secret_material_inspected": False,
            "development_only": True,
            "exception_text_released": False,
            "failed_workspace_state_released": False,
            "failure_stage": "gitbutler_runtime_receipt_publisher_target_validation_before_runtime_receipt_copy",
            "hidden_episode_identifiers_or_families_inspected": False,
            "install_cli_invocations": 0,
            "manifest_created": False,
            "model_bearing_provider_call_exposure": {
                "claude": 0,
                "codex": 0,
                "cursor": 0,
                "total": 0,
            },
            "model_bearing_provider_calls_conservatively_chargeable": 0,
            "model_calls_started": 0,
            "oauth_state_inspected": False,
            "original_panel_id": "development-matched-50x6-v35",
            "preflight_profiles_attempted": 0,
            "preflight_profiles_passed": 0,
            "private_authentication_key_created": False,
            "private_cohort_created": False,
            "private_or_provider_artifacts_released": False,
            "private_state_created": False,
            "production_assignments_started": 0,
            "protected_payloads_inspected": False,
            "provider_free_runtime_receipt_candidate_comparison_performed": True,
            "provider_free_runtime_receipt_candidates_byte_identical": True,
            "provider_free_runtime_receipt_candidates_generated": 2,
            "provider_free_runtime_receipt_candidates_passed": 2,
            "provider_free_runtime_receipt_generation_cli_invocations": 2,
            "provider_free_runtime_receipt_installations": 0,
            "provider_free_runtime_receipt_installed_locally": False,
            "provider_processes_started": 0,
            "public_preflight_artifact_created": False,
            "public_results_artifact_created": False,
            "public_runtime_receipt_created": False,
            "publication_incidents": list(self.EXPECTED_INCIDENTS),
            "publication_retry_permitted": False,
            "raw_provider_outputs_inspected": False,
            "replacement_panel_id": "development-matched-50x6-v40",
            "replacement_requirements": list(self.REPLACEMENT_REQUIREMENTS),
            "replacement_values_status": "not_yet_created_or_published",
            "results_released": False,
            "resumption_permitted": False,
            "runtime_publication_terminal_closeout_ref": self.CLOSEOUT_REF,
            "runtime_receipt_file_copy_invocations": 0,
            "runtime_receipt_gitbutler_commit_invocations": 0,
            "runtime_receipt_gitbutler_push_invocations": 0,
            "runtime_receipt_publication_attempts": 0,
            "runtime_receipt_publication_succeeded": False,
            "runtime_receipt_remote_mutation_observed": False,
            "runtime_receipt_remote_records_observed": 0,
            "runtime_receipt_remote_ref": "refs/heads/codex/v35-runtime-preflight",
            "runtime_receipt_remote_ref_present": False,
            "runtime_receipt_value_released": False,
            "schema_version": "epiagentbench.panel_supersession.v28",
            "scores_inspected": False,
            "scores_released": False,
            "spend_acknowledgement_supplied": False,
            "spend_authorization_recorded": False,
            "start_cli_invocations": 0,
            "status": "failed_zero_model_runtime_receipt_publisher_setup",
            "supervisor_runtime_generated": False,
            "terminal_closeout_candidate_artifacts_in_tree_or_ancestry_permitted": False,
            "terminal_closeout_failed_workspace_state_in_tree_or_ancestry_permitted": False,
            "terminal_closeout_required_parent_commit": self.CONTROL_COMMIT,
            "terminal_closeout_runtime_receipt_file_in_tree_permitted": False,
            "terminal_record_kind": "provider_free_runtime_receipt_publisher_setup_incident_supersession",
            "traces_inspected": False,
            "traces_released": False,
            "v35_cohort_reuse_permitted": False,
            "v35_conservative_claude_ceiling_added_usd": 0,
            "v35_control_commit_reuse_as_runtime_base_permitted": False,
            "v35_key_or_namespace_reuse_permitted": False,
            "v35_runtime_publication_terminal_closeout_publication_attempts": 0,
            "v35_runtime_publication_terminal_closeout_ref_present": False,
            "v35_runtime_publication_terminal_closeout_retry_permitted": False,
            "v36_panel_or_control_plane_created": False,
            "v36_successor_bridge_ref_present": False,
            "v36_values_reuse_permitted": False,
            "v37_panel_or_control_plane_created": False,
            "v37_successor_bridge_ref_present": False,
            "v37_values_reuse_permitted": False,
            "v38_failed_workspace_values_reuse_permitted": False,
            "v38_panel_or_control_plane_created": False,
            "v38_successor_bridge_ref_present": False,
            "v39_failed_workspace_values_reuse_permitted": False,
            "v39_panel_or_control_plane_created": False,
            "v39_successor_bridge_ref_present": False,
            "v40_acknowledgement_receipt_recorded": False,
            "v40_commit_or_hash_values_recorded": False,
            "v40_control_plane_created": False,
            "v40_control_plane_published": False,
            "verification_cli_invocations": 0,
            "verification_receipt_created": False,
        }
        observed = dict(self.superseded)
        observed.pop("superseded_at_utc")
        self.assertEqual(observed, expected)

    def test_published_control_commit_is_the_authoritative_base(self) -> None:
        observed = subprocess.run(
            ["/usr/bin/git", "show", "-s", "--format=%H %P %T", self.CONTROL_COMMIT],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.strip()
        self.assertEqual(
            observed,
            " ".join(
                (self.CONTROL_COMMIT, self.CONTROL_PARENT_COMMIT, self.CONTROL_TREE)
            ),
        )
        self.assertIs(self.superseded["control_plane_independently_pinned"], True)
        self.assertEqual(
            self.superseded["terminal_closeout_required_parent_commit"],
            self.CONTROL_COMMIT,
        )

    def test_incident_chain_is_exact_ordered_and_terminal(self) -> None:
        self.assertEqual(
            self.superseded["publication_incidents"], list(self.EXPECTED_INCIDENTS)
        )
        self.assertEqual(
            [
                incident["namespace"]
                for incident in self.superseded["publication_incidents"]
            ],
            [
                "v35_runtime_receipt_publisher",
                "v35_terminal_closeout_publisher",
                "v36_successor_terminal_bridge",
                "v37_successor_terminal_bridge",
                "v38_successor_terminal_bridge",
                "v39_successor_terminal_bridge",
            ],
        )
        for incident in self.superseded["publication_incidents"]:
            self.assertIs(incident["remote_mutation_observed"], False)
        self.assertIs(self.superseded["publication_retry_permitted"], False)
        self.assertIs(self.superseded["resumption_permitted"], False)

    def test_v38_validation_failures_are_safe_and_exact(self) -> None:
        incident = self.superseded["publication_incidents"][4]
        self.assertEqual(incident, self.EXPECTED_INCIDENTS[4])
        self.assertEqual(incident["optional_pytest_invocations"], 1)
        self.assertIs(incident["optional_pytest_module_available"], False)
        self.assertIs(
            incident["terminal_stop_applied_after_optional_pytest_failure"], False
        )
        self.assertEqual(incident["post_optional_pytest_failure_wording_edits"], 1)
        self.assertEqual(incident["formatter_command_invocations"], 1)
        self.assertIs(incident["formatter_executable_resolved"], False)
        self.assertEqual(incident["formatter_writes"], 0)
        for key in (
            "gitbutler_commit_invocations",
            "credential_routing_invocations",
            "gitbutler_push_invocations",
            "release_clone_attempts",
        ):
            self.assertEqual(incident[key], 0, key)

    def test_v39_setup_failure_is_safe_and_exact(self) -> None:
        incident = self.superseded["publication_incidents"][5]
        self.assertEqual(incident, self.EXPECTED_INCIDENTS[5])
        for key in (
            "fixed_origin_control_ref_queries_passed",
            "destination_ref_queries_passed",
            "mutually_exclusive_ref_bundle_queries_passed",
            "publisher_workspace_fresh_path_queries_passed",
            "release_workspace_fresh_path_queries_passed",
        ):
            self.assertEqual(incident[key], 2, key)
        self.assertEqual(incident["publisher_clone_attempts"], 1)
        self.assertIs(incident["publisher_clone_succeeded"], True)
        self.assertEqual(incident["remote_head_binding_invocations"], 1)
        self.assertIs(incident["remote_head_binding_succeeded"], True)
        self.assertEqual(incident["publisher_setup_invocations"], 1)
        self.assertIs(incident["publisher_setup_succeeded"], False)
        self.assertEqual(incident["application_storage_write_denials_observed"], 1)
        self.assertEqual(incident["publisher_setup_retry_invocations"], 0)
        for key in (
            "identity_configuration_invocations",
            "files_authored",
            "formatter_command_invocations",
            "targeted_unittest_invocations",
            "optional_pytest_invocations",
            "but_diff_invocations",
            "gitbutler_commit_invocations",
            "credential_routing_invocations",
            "gitbutler_push_invocations",
            "release_clone_attempts",
        ):
            self.assertEqual(incident[key], 0, key)

    def test_candidates_passed_but_no_receipt_was_copied_or_published(self) -> None:
        self.assertEqual(
            self.superseded["provider_free_runtime_receipt_candidates_generated"], 2
        )
        self.assertEqual(
            self.superseded["provider_free_runtime_receipt_candidates_passed"], 2
        )
        self.assertIs(
            self.superseded[
                "provider_free_runtime_receipt_candidate_comparison_performed"
            ],
            True,
        )
        self.assertIs(
            self.superseded["provider_free_runtime_receipt_candidates_byte_identical"],
            True,
        )
        for key in (
            "provider_free_runtime_receipt_installations",
            "runtime_receipt_file_copy_invocations",
            "runtime_receipt_gitbutler_commit_invocations",
            "runtime_receipt_gitbutler_push_invocations",
            "runtime_receipt_publication_attempts",
        ):
            self.assertEqual(self.superseded[key], 0, key)
        for key in (
            "provider_free_runtime_receipt_installed_locally",
            "public_runtime_receipt_created",
            "runtime_receipt_publication_succeeded",
            "runtime_receipt_remote_mutation_observed",
            "runtime_receipt_remote_ref_present",
            "runtime_receipt_value_released",
        ):
            self.assertIs(self.superseded[key], False, key)

    def test_no_authenticated_model_private_or_downstream_work_started(self) -> None:
        for key in (
            "authentication_cli_invocations",
            "authentication_processes_started",
            "install_cli_invocations",
            "model_bearing_provider_calls_conservatively_chargeable",
            "model_calls_started",
            "preflight_profiles_attempted",
            "preflight_profiles_passed",
            "production_assignments_started",
            "provider_processes_started",
            "start_cli_invocations",
            "v35_conservative_claude_ceiling_added_usd",
            "verification_cli_invocations",
        ):
            self.assertEqual(self.superseded[key], 0, key)
        self.assertEqual(
            self.superseded["model_bearing_provider_call_exposure"],
            {"claude": 0, "codex": 0, "cursor": 0, "total": 0},
        )
        for key in (
            "authentication_receipt_created",
            "manifest_created",
            "private_authentication_key_created",
            "private_cohort_created",
            "private_state_created",
            "public_preflight_artifact_created",
            "public_results_artifact_created",
            "spend_acknowledgement_supplied",
            "spend_authorization_recorded",
            "supervisor_runtime_generated",
            "verification_receipt_created",
        ):
            self.assertIs(self.superseded[key], False, key)

    def test_predecessor_namespaces_are_not_panels_and_v40_is_unset(self) -> None:
        for version in ("v36", "v37", "v38", "v39"):
            self.assertIs(
                self.superseded[f"{version}_panel_or_control_plane_created"], False
            )
            self.assertIs(
                self.superseded[f"{version}_successor_bridge_ref_present"], False
            )
        panel_ids = {
            value
            for value in self._strings(self.superseded)
            if value.startswith("development-matched-50x6-")
        }
        self.assertEqual(
            panel_ids,
            {"development-matched-50x6-v35", "development-matched-50x6-v40"},
        )
        self.assertEqual(
            self.superseded["replacement_values_status"], "not_yet_created_or_published"
        )
        for key in (
            "v40_acknowledgement_receipt_recorded",
            "v40_commit_or_hash_values_recorded",
            "v40_control_plane_created",
            "v40_control_plane_published",
        ):
            self.assertIs(self.superseded[key], False, key)

    def test_record_releases_no_protected_or_local_values(self) -> None:
        forbidden_keys = {
            "access_token",
            "account",
            "account_id",
            "api_key",
            "application_storage_path",
            "argv",
            "candidate_1_path",
            "candidate_1_sha256",
            "candidate_2_path",
            "candidate_2_sha256",
            "candidate_path",
            "candidate_sha256",
            "client_id",
            "command",
            "email",
            "episode_id",
            "episode_ref",
            "exception",
            "family",
            "failed_workspace_path",
            "hidden_episode_identifier",
            "invoked_path",
            "observation",
            "oauth_state",
            "password",
            "private_path",
            "private_seed",
            "prompt",
            "provider_output",
            "raw_output",
            "remote_error",
            "runtime_receipt",
            "sandbox_profile",
            "schedule",
            "score",
            "stderr",
            "stdout",
            "token",
            "trace",
            "username",
            "workspace_path",
        }
        self.assertTrue(forbidden_keys.isdisjoint(self._keys(self.superseded)))
        for value in self._strings(self.superseded):
            lowered = value.lower()
            self.assertFalse(lowered.startswith(("/", "~", "file://")))
            self.assertNotIn("\n", value)
            self.assertNotIn("@", value)
            for fragment in (
                "/private/",
                "/users/",
                "access_token",
                "api_key",
                "application support",
                "app-cache.sqlite",
                "client_id",
                "command not found",
                "github.com",
                "github_pat_",
                "ghp_",
                "no module named",
                "oauth_state",
                "operation not permitted",
                "osxkeychain",
                "projects.json",
                "provider_output",
                "https://",
                "trace_steps",
            ):
                self.assertNotIn(fragment, lowered)
        for key in (
            "candidate_bodies_released",
            "candidate_hashes_released",
            "candidate_paths_released",
            "credential_secret_material_inspected",
            "exception_text_released",
            "failed_workspace_state_released",
            "hidden_episode_identifiers_or_families_inspected",
            "oauth_state_inspected",
            "private_or_provider_artifacts_released",
            "protected_payloads_inspected",
            "raw_provider_outputs_inspected",
            "results_released",
            "scores_inspected",
            "scores_released",
            "traces_inspected",
            "traces_released",
        ):
            self.assertIs(self.superseded[key], False, key)
        object_ids = set(re.findall(r"\b[0-9a-f]{40}\b", self.raw.decode()))
        self.assertEqual(
            object_ids,
            {self.CONTROL_COMMIT, self.CONTROL_PARENT_COMMIT, self.CONTROL_TREE},
        )

    def test_supersession_timestamp_is_canonical_current_utc(self) -> None:
        raw = str(self.superseded["superseded_at_utc"])
        parsed = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
        self.assertEqual(raw, parsed.strftime("%Y-%m-%dT%H:%M:%SZ"))
        self.assertLessEqual(parsed, datetime.now(timezone.utc))

    def test_committed_closeout_has_the_authorized_topology(self) -> None:
        tracked = subprocess.run(
            ["/usr/bin/git", "ls-files", "--error-unmatch", self.SUPERSESSION_PATH],
            cwd=self.root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if tracked.returncode != 0:
            self.skipTest("closeout is not committed yet")
        refs = subprocess.run(
            [
                "/usr/bin/git",
                "for-each-ref",
                "--format=%(objectname)",
                self.CLOSEOUT_REF,
            ],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.splitlines()
        if not refs:
            self.skipTest("closeout branch is not finalized yet")
        self.assertEqual(len(refs), 1)
        closeout_commit = refs[0]
        for path in (self.SUPERSESSION_PATH, self.TEST_PATH):
            introducing_commit = subprocess.run(
                ["/usr/bin/git", "log", "-1", "--format=%H", "--", path],
                cwd=self.root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            ).stdout.strip()
            self.assertEqual(introducing_commit, closeout_commit)
        parents = subprocess.run(
            ["/usr/bin/git", "show", "-s", "--format=%P", closeout_commit],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.strip()
        self.assertEqual(parents, self.CONTROL_COMMIT)
        changed_paths = subprocess.run(
            [
                "/usr/bin/git",
                "diff-tree",
                "--no-commit-id",
                "--name-only",
                "-r",
                closeout_commit,
            ],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.splitlines()
        self.assertEqual(
            sorted(changed_paths), sorted((self.SUPERSESSION_PATH, self.TEST_PATH))
        )
        tree_paths = subprocess.run(
            ["/usr/bin/git", "ls-tree", "-r", "--name-only", closeout_commit],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.splitlines()
        for forbidden_path in (
            "results/development-matched-50x6-v35.runtime.json",
            "results/development-matched-50x6-v35.manifest.json",
            "results/development-matched-50x6-v35.authentication.json",
            "results/development-matched-50x6-v35.verification.json",
            "results/development-matched-50x6-v35.preflight.json",
            "results/development-matched-50x6-v35.json",
        ):
            self.assertNotIn(forbidden_path, tree_paths)
        self.assertFalse(any("candidate" in path.lower() for path in tree_paths))
        for local_ref in (
            "refs/heads/codex/v35-runtime-publication-terminal-closeout",
            "refs/heads/codex/v36-v35-runtime-publication-terminal-closeout",
            "refs/heads/codex/v37-v35-runtime-publication-terminal-closeout",
            "refs/heads/codex/v38-v35-runtime-publication-terminal-closeout",
            "refs/heads/codex/v39-v35-runtime-publication-terminal-closeout",
            "refs/heads/codex/v35-runtime-preflight",
            "refs/heads/codex/v35-preflight-terminal-closeout",
            "refs/heads/codex/v35-production-results",
            "refs/heads/codex/v35-terminal-closeout",
        ):
            observed = subprocess.run(
                ["/usr/bin/git", "for-each-ref", "--format=%(objectname)", local_ref],
                cwd=self.root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            ).stdout
            self.assertEqual(observed, "", local_ref)


if __name__ == "__main__":
    unittest.main()
