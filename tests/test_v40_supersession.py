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


class V40SupersessionTests(unittest.TestCase):
    BASE_COMMIT = "6471dcd74393852740e64a6c7181d5c44d3d9a30"
    BASE_PARENT = "818b0313eb14e3b31431b267626d8d4a61fa5559"
    BASE_TREE = "1ebc154a6e2da6b03e9b4b526b7eac269fd46ebe"
    SOURCE_REF = "refs/heads/codex/v40-v35-runtime-publication-terminal-closeout"
    CLOSEOUT_REF = (
        "refs/heads/codex/v46-v40-control-plane-publication-terminal-closeout"
    )
    SUPERSESSION_PATH = "results/development-matched-50x6-v40.superseded.json"
    TEST_PATH = "tests/test_v40_supersession.py"
    INCIDENT_IDENTITIES = (
        (
            "v40_control_plane_authoring",
            "control_plane_authoring_patch_context_mismatch",
            "control_plane_authoring_combined_documentation_patch_context_validation",
        ),
        (
            "v40_control_plane_authoring_post_terminal",
            "prohibited_post_terminal_control_plane_authoring_continuation",
            "post_terminal_control_plane_authoring_before_validation",
        ),
        (
            "v41_v40_control_plane_publication_terminal_closeout",
            "redundant_sandboxed_source_pin_dns_failure",
            "successor_precreation_redundant_source_pin_before_mutation",
        ),
        (
            "v42_successor_terminal_closeout_precreation",
            "successor_precreation_local_source_object_unavailable",
            "successor_terminal_closeout_local_source_object_validation_after_remote_and_path_gates_before_candidate_clone_and_mutation",
        ),
        (
            "v43_successor_terminal_closeout_candidate_pre_authoring",
            "successor_candidate_source_pattern_inspection_executable_unavailable",
            "successor_terminal_closeout_source_pattern_inspection_after_candidate_clones_before_candidate_authoring",
        ),
        (
            "v44_successor_terminal_closeout_precreation",
            "successor_precreation_fresh_path_check_executable_unavailable",
            "successor_terminal_closeout_fresh_path_absence_validation_after_remote_ref_gates_before_tool_validation_and_mutation",
        ),
        (
            "v45_successor_terminal_closeout_publication",
            "successor_publication_credential_routing_cli_executable_unavailable",
            "successor_terminal_closeout_credential_routing_after_valid_unpublished_local_commit_validation_before_process_launch_account_selection_and_push",
        ),
    )

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.raw = (cls.root / cls.SUPERSESSION_PATH).read_bytes()
        payload = json.loads(cls.raw, object_pairs_hook=_object_without_duplicate_keys)
        if not isinstance(payload, dict):
            raise TypeError("V40 supersession must be a JSON object")
        cls.superseded = payload

    @staticmethod
    def _keys(payload: object) -> set[str]:
        observed: set[str] = set()
        if isinstance(payload, Mapping):
            for key, value in payload.items():
                observed.add(str(key))
                observed.update(V40SupersessionTests._keys(value))
        elif isinstance(payload, Sequence) and not isinstance(
            payload, (str, bytes, bytearray)
        ):
            for value in payload:
                observed.update(V40SupersessionTests._keys(value))
        return observed

    @staticmethod
    def _strings(payload: object) -> list[str]:
        observed: list[str] = []
        if isinstance(payload, str):
            observed.append(payload)
        elif isinstance(payload, Mapping):
            for value in payload.values():
                observed.extend(V40SupersessionTests._strings(value))
        elif isinstance(payload, Sequence) and not isinstance(
            payload, (str, bytes, bytearray)
        ):
            for value in payload:
                observed.extend(V40SupersessionTests._strings(value))
        return observed

    def test_canonical_duplicate_free_record(self) -> None:
        expected = (
            json.dumps(self.superseded, sort_keys=True, indent=2) + "\n"
        ).encode()
        self.assertEqual(self.raw, expected)

    def test_root_contract_and_public_predecessor_are_exact(self) -> None:
        self.assertEqual(
            self.superseded["schema_version"], "epiagentbench.panel_supersession.v29"
        )
        self.assertEqual(
            self.superseded["status"], "failed_zero_model_control_plane_authoring"
        )
        self.assertEqual(
            self.superseded["terminal_record_kind"],
            "control_plane_authoring_incident_supersession",
        )
        self.assertEqual(
            self.superseded["audited_root_cause_code"],
            "control_plane_authoring_patch_context_mismatch",
        )
        self.assertEqual(
            self.superseded["failure_stage"],
            "control_plane_authoring_combined_documentation_patch_context_validation",
        )
        self.assertEqual(
            self.superseded["original_panel_id"], "development-matched-50x6-v40"
        )
        self.assertEqual(
            self.superseded["replacement_panel_id"], "development-matched-50x6-v46"
        )
        self.assertEqual(
            self.superseded["replacement_values_status"],
            "not_yet_created_or_published",
        )
        self.assertEqual(self.superseded["public_predecessor_commit"], self.BASE_COMMIT)
        self.assertEqual(
            self.superseded["public_predecessor_parent_commit"], self.BASE_PARENT
        )
        self.assertEqual(self.superseded["public_predecessor_tree"], self.BASE_TREE)
        self.assertEqual(self.superseded["public_predecessor_ref"], self.SOURCE_REF)
        self.assertEqual(
            self.superseded["terminal_closeout_required_parent_commit"],
            self.BASE_COMMIT,
        )

    def test_incident_chain_is_exact_ordered_and_terminal(self) -> None:
        incidents = self.superseded["publication_incidents"]
        observed = tuple(
            (incident["namespace"], incident["cause_code"], incident["stage"])
            for incident in incidents
        )
        self.assertEqual(observed, self.INCIDENT_IDENTITIES)
        for incident in incidents:
            self.assertIs(incident["remote_mutation_observed"], False)
        self.assertIs(self.superseded["publication_retry_permitted"], False)
        self.assertIs(self.superseded["resumption_permitted"], False)

    def test_v40_original_failure_and_continuation_are_exact(self) -> None:
        original, continuation = self.superseded["publication_incidents"][:2]
        self.assertEqual(original["dirty_paths_observed"], 17)
        self.assertEqual(original["tracked_modified_paths_observed"], 10)
        self.assertEqual(original["untracked_paths_observed"], 7)
        self.assertEqual(original["combined_documentation_patch_writes"], 0)
        self.assertIs(original["terminal_stop_applied"], False)
        self.assertIs(continuation["continuation_observed"], True)
        self.assertEqual(continuation["continuation_mutating_invocations_minimum"], 1)
        self.assertEqual(continuation["continuation_mutating_completions_minimum"], 1)
        self.assertIs(
            continuation["continuation_invocation_count_exactly_known"], False
        )
        self.assertIs(
            continuation["continuation_completion_count_exactly_known"], False
        )
        self.assertIs(continuation["post_terminal_workspace_mutation_observed"], True)

    def test_v41_and_v42_precreation_failures_are_exact(self) -> None:
        v41 = self.superseded["publication_incidents"][2]
        self.assertEqual(v41["source_ref_pin_queries_attempted_total"], 3)
        self.assertEqual(v41["source_ref_pin_queries_passed_total"], 2)
        self.assertEqual(v41["redundant_source_ref_pin_dns_failures"], 1)
        self.assertEqual(v41["source_pin_retry_invocations"], 0)
        self.assertEqual(
            v41["destination_and_lifecycle_ref_absence_queries_attempted"], 1
        )
        self.assertIs(
            v41["second_destination_and_lifecycle_ref_absence_query_attempted"],
            False,
        )
        v42 = self.superseded["publication_incidents"][3]
        self.assertEqual(v42["mutually_exclusive_ref_bundle_queries_passed"], 2)
        self.assertEqual(v42["source_object_validation_attempts"], 1)
        self.assertIs(v42["source_object_validation_passed"], False)
        self.assertEqual(v42["source_object_validation_retry_invocations"], 0)

    def test_v43_and_v44_tool_failures_are_exact(self) -> None:
        v43 = self.superseded["publication_incidents"][4]
        self.assertEqual(v43["source_inspection_clone_completions"], 1)
        self.assertEqual(v43["candidate_clone_completions"], 2)
        self.assertEqual(v43["source_pattern_inspection_invocations"], 1)
        self.assertIs(v43["source_pattern_inspection_passed"], False)
        self.assertEqual(v43["source_pattern_inspection_retry_invocations"], 0)
        self.assertEqual(v43["candidate_files_authored"], 0)
        v44 = self.superseded["publication_incidents"][5]
        self.assertEqual(v44["mutually_exclusive_ref_bundle_queries_passed"], 2)
        self.assertEqual(v44["fresh_path_check_invocations"], 1)
        self.assertEqual(v44["fresh_path_absence_observations"], 0)
        self.assertEqual(v44["fresh_path_absence_rounds_passed"], 0)
        self.assertEqual(v44["fresh_path_check_retry_invocations"], 0)
        self.assertIs(v44["local_filesystem_mutation_observed"], False)

    def test_v45_valid_local_commit_and_routing_failure_are_exact(self) -> None:
        incident = self.superseded["publication_incidents"][6]
        for key in (
            "all_precreation_gates_passed",
            "all_candidate_gates_passed",
            "all_publisher_gates_passed",
            "candidate_pre_format_byte_identity_passed",
            "candidate_post_format_byte_identity_passed",
            "sole_parent_validation_passed",
            "exact_two_file_delta_validation_passed",
            "postcommit_zero_skip_unittest_passed",
        ):
            self.assertIs(incident[key], True, key)
        self.assertEqual(incident["source_inspection_clone_completions"], 1)
        self.assertEqual(incident["candidate_clone_completions"], 2)
        self.assertEqual(incident["publisher_clone_completions"], 1)
        self.assertEqual(incident["but_diff_invocations"], 1)
        self.assertEqual(incident["gitbutler_commit_invocations"], 1)
        self.assertEqual(incident["gitbutler_commits_created"], 1)
        self.assertEqual(incident["valid_unpublished_local_commits"], 1)
        self.assertEqual(incident["credential_routing_invocations"], 1)
        self.assertEqual(incident["credential_routing_process_launches"], 0)
        self.assertEqual(incident["credential_routing_passes"], 0)
        self.assertEqual(incident["account_selection_changes"], 0)
        self.assertEqual(incident["credential_validation_invocations"], 0)
        self.assertEqual(incident["gitbutler_push_invocations"], 0)
        self.assertEqual(incident["release_clone_attempts"], 0)
        self.assertIs(incident["unpublished_local_commit_identifier_released"], False)
        self.assertIs(incident["unpublished_local_commit_reuse_permitted"], False)

    def test_no_authenticated_model_private_or_downstream_work_started(self) -> None:
        for key in (
            "authentication_cli_invocations",
            "authentication_processes_started",
            "model_bearing_provider_calls_conservatively_chargeable",
            "model_calls_started",
            "preflight_profiles_attempted",
            "preflight_profiles_passed",
            "production_assignments_started",
            "provider_processes_started",
            "start_cli_invocations",
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
            "public_runtime_receipt_created",
            "spend_acknowledgement_supplied",
            "spend_authorization_recorded",
            "supervisor_runtime_generated",
            "verification_receipt_created",
        ):
            self.assertIs(self.superseded[key], False, key)

    def test_publication_namespaces_and_v46_values_are_exact(self) -> None:
        for version in ("v41", "v42", "v43", "v44", "v45"):
            self.assertIs(
                self.superseded[f"{version}_panel_or_control_plane_created"], False
            )
            self.assertIs(
                self.superseded[f"{version}_control_or_runtime_values_created"],
                False,
            )
            self.assertIs(self.superseded[f"{version}_values_reuse_permitted"], False)
        panel_ids = {
            value
            for value in self._strings(self.superseded)
            if value.startswith("development-matched-50x6-")
        }
        self.assertEqual(
            panel_ids,
            {"development-matched-50x6-v40", "development-matched-50x6-v46"},
        )
        self.assertIs(
            self.superseded["v40_persistent_supervisor_contract_v21_reuse_permitted"],
            False,
        )
        self.assertIs(
            self.superseded["v46_persistent_supervisor_contract_v22_required"], True
        )
        self.assertIs(self.superseded["v46_panel_supersession_v30_reserved"], True)
        for key in (
            "v46_acknowledgement_receipt_recorded",
            "v46_commit_or_hash_values_recorded",
            "v46_control_plane_created",
            "v46_control_plane_published",
        ):
            self.assertIs(self.superseded[key], False, key)

    def test_record_releases_no_protected_local_or_unpublished_values(self) -> None:
        forbidden_keys = {
            "access_token",
            "account",
            "account_id",
            "api_key",
            "argv",
            "candidate_path",
            "candidate_sha256",
            "client_id",
            "command",
            "credential_path",
            "email",
            "episode_id",
            "exception",
            "executable_name",
            "executable_path",
            "failed_workspace_path",
            "family",
            "local_commit_id",
            "oauth_state",
            "password",
            "private_path",
            "private_seed",
            "prompt",
            "provider_output",
            "raw_output",
            "runtime_receipt",
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
                "command not found",
                "github.com",
                "github_pat_",
                "ghp_",
                "oauth_state",
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
            "v40_unpublished_authoring_values_released",
            "v45_unpublished_local_commit_value_released",
        ):
            self.assertIs(self.superseded[key], False, key)
        object_ids = set(re.findall(r"\b[0-9a-f]{40}\b", self.raw.decode()))
        self.assertEqual(
            object_ids, {self.BASE_COMMIT, self.BASE_PARENT, self.BASE_TREE}
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
        parents = subprocess.run(
            ["/usr/bin/git", "show", "-s", "--format=%P", closeout_commit],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.strip()
        self.assertEqual(parents, self.BASE_COMMIT)
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
        ancestry = subprocess.run(
            ["/usr/bin/git", "rev-list", "--parents", "-n", "2", closeout_commit],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.splitlines()
        self.assertTrue(ancestry[0].endswith(f" {self.BASE_COMMIT}"))
        tree_paths = subprocess.run(
            ["/usr/bin/git", "ls-tree", "-r", "--name-only", closeout_commit],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.splitlines()
        for forbidden_path in (
            "results/development-matched-50x6-v40.runtime.json",
            "results/development-matched-50x6-v40.manifest.json",
            "results/development-matched-50x6-v40.authentication.json",
            "results/development-matched-50x6-v40.verification.json",
            "results/development-matched-50x6-v40.preflight.json",
            "results/development-matched-50x6-v40.json",
        ):
            self.assertNotIn(forbidden_path, tree_paths)
        self.assertFalse(any("candidate" in path.lower() for path in tree_paths))


if __name__ == "__main__":
    unittest.main()
