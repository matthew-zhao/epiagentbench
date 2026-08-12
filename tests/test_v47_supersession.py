from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
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


class V47SupersessionTests(unittest.TestCase):
    BASE_COMMIT = "e8946a10997863412d4a2ec0113b72e066a73550"
    BASE_PARENT = "ab2043215d034c06528100033b18de563d754d9c"
    BASE_TREE = "3e162b89b8288ceb63776bfd14f2d3f1a3738dd1"
    SOURCE_REF = "refs/heads/codex/v47-v46-control-plane-publication-terminal-closeout"
    CLOSEOUT_REF = (
        "refs/heads/codex/v48-v47-control-plane-publication-terminal-closeout"
    )
    SUPERSESSION_PATH = "results/development-matched-50x6-v47.superseded.json"
    TEST_PATH = "tests/test_v47_supersession.py"
    INHERITED_HASHES = {
        "results/development-matched-50x6-v35.superseded.json": (
            "843654f16c0bf7a2c461d229ff71a1f3bdf5e36a90ebc8da019d34f8dcf88cf0"
        ),
        "results/development-matched-50x6-v40.superseded.json": (
            "76f533598108bda5996fbabcf7e220d36ffc3675648db744a4dc4cad44dae611"
        ),
        "results/development-matched-50x6-v46.superseded.json": (
            "b751588e905d133ea99c08d42668b50f9d658a1e622c5a6560611c19e052d7bc"
        ),
        "tests/test_v35_supersession.py": (
            "68c45bc342152249e48a2e529b0908e2b8ea287779e7709025a80d5334477042"
        ),
        "tests/test_v40_supersession.py": (
            "4ce9b0fdebfcc3e78aefd7cb3146ab44e0d3079eac04d343b9d71c756b840419"
        ),
        "tests/test_v46_supersession.py": (
            "2622fdc4fca24ead7e1dfd510055991117c1872bea9757889262b6b001ce6406"
        ),
    }
    INCIDENT_IDENTITIES = (
        (
            "v47_control_plane_phase_b2_precreation",
            "control_plane_publication_scope_inventory_not_exact_changed_path_attestation",
            "control_plane_publication_local_scope_inventory_after_source_candidate_and_tool_validation_before_network_credentials_clone_gitbutler_and_mutation",
        ),
        (
            "v47_control_plane_phase_b2_post_terminal_precreation",
            "prohibited_post_terminal_control_plane_publication_scope_inventory_substitution_failure",
            "post_terminal_control_plane_publication_local_scope_inventory_before_network_credentials_clone_gitbutler_and_mutation",
        ),
    )

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.raw = (cls.root / cls.SUPERSESSION_PATH).read_bytes()
        payload = json.loads(cls.raw, object_pairs_hook=_object_without_duplicate_keys)
        if not isinstance(payload, dict):
            raise TypeError("V47 supersession must be a JSON object")
        cls.superseded = payload

    @staticmethod
    def _keys(payload: object) -> set[str]:
        observed: set[str] = set()
        if isinstance(payload, Mapping):
            for key, value in payload.items():
                observed.add(str(key))
                observed.update(V47SupersessionTests._keys(value))
        elif isinstance(payload, Sequence) and not isinstance(
            payload, (str, bytes, bytearray)
        ):
            for value in payload:
                observed.update(V47SupersessionTests._keys(value))
        return observed

    @staticmethod
    def _strings(payload: object) -> list[str]:
        observed: list[str] = []
        if isinstance(payload, str):
            observed.append(payload)
        elif isinstance(payload, Mapping):
            for value in payload.values():
                observed.extend(V47SupersessionTests._strings(value))
        elif isinstance(payload, Sequence) and not isinstance(
            payload, (str, bytes, bytearray)
        ):
            for value in payload:
                observed.extend(V47SupersessionTests._strings(value))
        return observed

    def test_canonical_duplicate_free_record(self) -> None:
        expected = (
            json.dumps(self.superseded, sort_keys=True, indent=2) + "\n"
        ).encode()
        self.assertEqual(self.raw, expected)

    def test_root_contract_and_public_predecessor_are_exact(self) -> None:
        expected = {
            "schema_version": "epiagentbench.panel_supersession.v31",
            "status": "failed_zero_model_control_plane_publication_precreation",
            "terminal_record_kind": (
                "control_plane_publication_precreation_incident_supersession"
            ),
            "audited_root_cause_code": (
                "control_plane_publication_scope_inventory_not_exact_changed_path_"
                "attestation"
            ),
            "failure_stage": (
                "control_plane_publication_local_scope_inventory_after_source_"
                "candidate_and_tool_validation_before_network_credentials_clone_"
                "gitbutler_and_mutation"
            ),
            "original_panel_id": "development-matched-50x6-v47",
            "replacement_panel_id": "development-matched-50x6-v48",
            "replacement_values_status": "not_yet_created_or_published",
            "public_predecessor_commit": self.BASE_COMMIT,
            "public_predecessor_parent_commit": self.BASE_PARENT,
            "public_predecessor_ref": self.SOURCE_REF,
            "public_predecessor_tree": self.BASE_TREE,
            "terminal_closeout_required_parent_commit": self.BASE_COMMIT,
            "terminal_closeout_required_ref": self.CLOSEOUT_REF,
        }
        for key, value in expected.items():
            self.assertEqual(self.superseded[key], value, key)
        self.assertEqual(
            self.superseded["terminal_closeout_required_paths"],
            [self.SUPERSESSION_PATH, self.TEST_PATH],
        )
        self.assertIs(self.superseded["development_only"], True)
        self.assertIs(self.superseded["publication_retry_permitted"], False)
        self.assertIs(self.superseded["resumption_permitted"], False)

    def test_incident_chain_is_exact_ordered_and_terminal(self) -> None:
        incidents = self.superseded["publication_incidents"]
        observed = tuple(
            (incident["namespace"], incident["cause_code"], incident["stage"])
            for incident in incidents
        )
        self.assertEqual(observed, self.INCIDENT_IDENTITIES)
        first, second = incidents
        self.assertEqual(first["read_only_dry_run_inventory_invocations"], 1)
        self.assertEqual(first["successful_process_exits"], 1)
        self.assertEqual(first["aggregate_inventory_lines_observed"], 336)
        self.assertEqual(first["required_changed_path_attestation_paths"], 17)
        self.assertIs(first["changed_path_attestation_created"], False)
        self.assertIs(first["scope_gate_passed"], False)
        self.assertIs(first["terminal_stop_applied"], False)
        self.assertEqual(
            second["prohibited_read_only_substitute_inventory_invocations"], 1
        )
        self.assertEqual(second["substitute_inventory_passes"], 0)
        self.assertEqual(second["scope_json_attestations_created"], 0)
        self.assertEqual(second["temporary_files_created"], 0)
        self.assertEqual(second["output_files_created"], 0)
        self.assertIs(second["terminal_stop_applied"], True)
        self.assertEqual(self.superseded["scope_inventory_retry_invocations"], 0)
        self.assertEqual(self.superseded["scope_inventory_substitution_invocations"], 1)
        self.assertIs(self.superseded["remote_mutation_observed"], False)

    def test_terminal_closeout_two_file_contract_is_exact(self) -> None:
        self.assertEqual(self.superseded["terminal_closeout_required_file_count"], 2)
        self.assertEqual(
            self.superseded["terminal_closeout_required_paths"],
            [self.SUPERSESSION_PATH, self.TEST_PATH],
        )
        self.assertEqual(
            self.superseded["terminal_closeout_required_parent_commit"],
            self.BASE_COMMIT,
        )
        self.assertEqual(
            self.superseded["terminal_closeout_required_ref"], self.CLOSEOUT_REF
        )

    def test_safe_precreation_gate_aggregates_are_exact(self) -> None:
        self.assertEqual(
            self.superseded["passed_precreation_gates"],
            {
                "authorized_manifest_candidate_validations_passed": 2,
                "authorized_manifest_paths": 17,
                "candidate_symlink_checks_passed": 2,
                "candidate_tree_validations_passed": 2,
                "candidate_trees_byte_identical": True,
                "inherited_closeout_path_validations_passed": 18,
                "inherited_closeout_paths": 6,
                "publisher_path_absence_validation_passed": True,
                "release_path_absence_validation_passed": True,
                "source_clean_validation_passed": True,
                "source_delta_paths": 2,
                "source_delta_validation_passed": True,
                "source_head_validation_passed": True,
                "source_parent_validation_passed": True,
                "source_tree_validation_passed": True,
                "tool_identity_and_version_gates_passed": 7,
            },
        )

    def test_no_network_credentials_repository_or_downstream_work_started(self) -> None:
        for key in (
            "api_access_invocations",
            "authentication_cli_invocations",
            "authentication_processes_started",
            "branch_creation_invocations",
            "clone_invocations",
            "cohort_creation_invocations",
            "commits_created",
            "credential_access_invocations",
            "gitbutler_invocations",
            "manifest_creation_invocations",
            "model_bearing_provider_calls_conservatively_chargeable",
            "model_calls_started",
            "network_query_invocations",
            "preflight_profiles_attempted",
            "preflight_profiles_passed",
            "private_state_creation_invocations",
            "production_assignments_started",
            "provider_processes_started",
            "push_invocations",
            "ref_creation_invocations",
            "release_checkout_creation_invocations",
            "repository_write_invocations",
            "result_artifact_creation_invocations",
            "runtime_receipt_creation_invocations",
            "start_cli_invocations",
            "supervisor_generation_invocations",
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

    def test_v47_is_non_reusable_and_v48_is_declarative_only(self) -> None:
        self.assertEqual(self.superseded["v47_control_candidates_existed_locally"], 2)
        self.assertEqual(self.superseded["v47_control_candidates_sealed"], 2)
        self.assertEqual(self.superseded["v47_control_candidates_committed"], 0)
        self.assertEqual(self.superseded["v47_control_candidates_published"], 0)
        for key in (
            "v47_control_candidates_reuse_permitted",
            "v47_control_plane_created",
            "v47_control_plane_published",
            "v47_lifecycle_namespaces_reuse_permitted",
            "v47_panel_namespace_development_matched_panel_v47_reuse_permitted",
            "v47_persistent_supervisor_contract_v23_reuse_permitted",
            "v47_runtime_values_created",
            "v47_unpublished_control_plane_values_released",
        ):
            self.assertIs(self.superseded[key], False, key)
        self.assertIs(self.superseded["v48_declarative_replacement_only"], True)
        self.assertIs(self.superseded["v48_fresh_lifecycle_namespaces_required"], True)
        self.assertEqual(
            self.superseded["v48_panel_namespace_required"],
            "development_matched_panel_v48",
        )
        self.assertIs(self.superseded["v48_panel_supersession_v32_reserved"], True)
        self.assertIs(
            self.superseded["v48_persistent_supervisor_contract_v24_required"],
            True,
        )
        self.assertIs(self.superseded["v48_control_or_runtime_values_created"], False)
        self.assertIs(self.superseded["v48_values_published"], False)
        panel_ids = {
            value
            for value in self._strings(self.superseded)
            if value.startswith("development-matched-50x6-")
        }
        self.assertEqual(
            panel_ids,
            {"development-matched-50x6-v47", "development-matched-50x6-v48"},
        )

    def test_generic_wire_contracts_are_retained(self) -> None:
        self.assertIs(self.superseded["generic_wire_schemas_changed"], False)
        self.assertEqual(
            self.superseded["retained_generic_contract_versions"],
            {
                "launch_agent": "v16",
                "persistent_runner_protocol": "v9",
                "provider_cli": "v3",
                "worker_status": "v6",
            },
        )

    def test_inherited_public_closeout_hashes_are_exact(self) -> None:
        for path, expected in self.INHERITED_HASHES.items():
            actual = hashlib.sha256((self.root / path).read_bytes()).hexdigest()
            self.assertEqual(actual, expected, path)

    def test_record_releases_no_protected_local_or_unpublished_values(self) -> None:
        forbidden_keys = {
            "acknowledgement_sha256",
            "acknowledgement_text",
            "access_token",
            "account",
            "account_id",
            "api_key",
            "argv",
            "cache_path",
            "candidate_body",
            "candidate_path",
            "candidate_sha256",
            "client_id",
            "command",
            "credential_path",
            "diagnostic_body",
            "diagnostic_path",
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
            "smoke_digest",
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
            "diagnostic_artifacts_released",
            "diagnostic_bodies_released",
            "diagnostic_hashes_released",
            "diagnostic_paths_released",
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
            object_ids, {self.BASE_COMMIT, self.BASE_PARENT, self.BASE_TREE}
        )

    def test_record_contains_no_sha256_values(self) -> None:
        self.assertEqual(re.findall(r"\b[0-9a-f]{64}\b", self.raw.decode()), [])

    def test_supersession_timestamp_is_canonical_current_utc(self) -> None:
        raw = str(self.superseded["superseded_at_utc"])
        parsed = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
        self.assertEqual(raw, parsed.strftime("%Y-%m-%dT%H:%M:%SZ"))
        self.assertLessEqual(parsed, datetime.now(timezone.utc))

    def test_committed_closeout_has_the_authorized_topology(self) -> None:
        inside_work_tree = subprocess.run(
            ["/usr/bin/git", "rev-parse", "--is-inside-work-tree"],
            cwd=self.root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if inside_work_tree.returncode != 0:
            self.skipTest("closeout candidate is not a Git checkout")
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
        base_parents = subprocess.run(
            ["/usr/bin/git", "show", "-s", "--format=%P", self.BASE_COMMIT],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.strip()
        self.assertEqual(base_parents, self.BASE_PARENT)
        base_tree = subprocess.run(
            ["/usr/bin/git", "show", "-s", "--format=%T", self.BASE_COMMIT],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.strip()
        self.assertEqual(base_tree, self.BASE_TREE)
        base_changed_paths = subprocess.run(
            [
                "/usr/bin/git",
                "diff-tree",
                "--no-commit-id",
                "--name-only",
                "-r",
                self.BASE_COMMIT,
            ],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.splitlines()
        self.assertEqual(
            sorted(base_changed_paths),
            sorted(
                (
                    "results/development-matched-50x6-v46.superseded.json",
                    "tests/test_v46_supersession.py",
                )
            ),
        )
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
        tree_paths = subprocess.run(
            ["/usr/bin/git", "ls-tree", "-r", "--name-only", closeout_commit],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.splitlines()
        for forbidden_path in (
            "results/development-matched-50x6-v47.runtime.json",
            "results/development-matched-50x6-v47.manifest.json",
            "results/development-matched-50x6-v47.authentication.json",
            "results/development-matched-50x6-v47.verification.json",
            "results/development-matched-50x6-v47.preflight.json",
            "results/development-matched-50x6-v47.json",
        ):
            self.assertNotIn(forbidden_path, tree_paths)
        self.assertFalse(any("candidate" in path.lower() for path in tree_paths))


if __name__ == "__main__":
    unittest.main()
