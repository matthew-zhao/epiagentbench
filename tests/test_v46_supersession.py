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


class V46SupersessionTests(unittest.TestCase):
    BASE_COMMIT = "ab2043215d034c06528100033b18de563d754d9c"
    BASE_PARENT = "6471dcd74393852740e64a6c7181d5c44d3d9a30"
    BASE_TREE = "7fcdc0116dc0d74b9779c064655a9fd774ed1390"
    SOURCE_REF = "refs/heads/codex/v46-v40-control-plane-publication-terminal-closeout"
    CLOSEOUT_REF = (
        "refs/heads/codex/v47-v46-control-plane-publication-terminal-closeout"
    )
    SUPERSESSION_PATH = "results/development-matched-50x6-v46.superseded.json"
    TEST_PATH = "tests/test_v46_supersession.py"
    INHERITED_HASHES = {
        "results/development-matched-50x6-v35.superseded.json": (
            "843654f16c0bf7a2c461d229ff71a1f3bdf5e36a90ebc8da019d34f8dcf88cf0"
        ),
        "results/development-matched-50x6-v40.superseded.json": (
            "76f533598108bda5996fbabcf7e220d36ffc3675648db744a4dc4cad44dae611"
        ),
        "tests/test_v35_supersession.py": (
            "68c45bc342152249e48a2e529b0908e2b8ea287779e7709025a80d5334477042"
        ),
        "tests/test_v40_supersession.py": (
            "4ce9b0fdebfcc3e78aefd7cb3146ab44e0d3079eac04d343b9d71c756b840419"
        ),
    }

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.raw = (cls.root / cls.SUPERSESSION_PATH).read_bytes()
        payload = json.loads(cls.raw, object_pairs_hook=_object_without_duplicate_keys)
        if not isinstance(payload, dict):
            raise TypeError("V46 supersession must be a JSON object")
        cls.superseded = payload

    @staticmethod
    def _keys(payload: object) -> set[str]:
        observed: set[str] = set()
        if isinstance(payload, Mapping):
            for key, value in payload.items():
                observed.add(str(key))
                observed.update(V46SupersessionTests._keys(value))
        elif isinstance(payload, Sequence) and not isinstance(
            payload, (str, bytes, bytearray)
        ):
            for value in payload:
                observed.update(V46SupersessionTests._keys(value))
        return observed

    @staticmethod
    def _strings(payload: object) -> list[str]:
        observed: list[str] = []
        if isinstance(payload, str):
            observed.append(payload)
        elif isinstance(payload, Mapping):
            for value in payload.values():
                observed.extend(V46SupersessionTests._strings(value))
        elif isinstance(payload, Sequence) and not isinstance(
            payload, (str, bytes, bytearray)
        ):
            for value in payload:
                observed.extend(V46SupersessionTests._strings(value))
        return observed

    def test_canonical_duplicate_free_record(self) -> None:
        expected = (
            json.dumps(self.superseded, sort_keys=True, indent=2) + "\n"
        ).encode()
        self.assertEqual(self.raw, expected)

    def test_root_contract_and_public_predecessor_are_exact(self) -> None:
        expected = {
            "schema_version": "epiagentbench.panel_supersession.v30",
            "status": "failed_zero_model_control_plane_precreation",
            "terminal_record_kind": "control_plane_precreation_incident_supersession",
            "audited_root_cause_code": (
                "control_plane_precreation_starsim_isolated_cache_environment_unbound"
            ),
            "failure_stage": (
                "control_plane_precreation_scientific_runtime_starsim_import_"
                "validation_before_hook_credential_clone_and_mutation"
            ),
            "original_panel_id": "development-matched-50x6-v46",
            "replacement_panel_id": "development-matched-50x6-v47",
            "replacement_values_status": "not_yet_created_or_published",
            "public_predecessor_commit": self.BASE_COMMIT,
            "public_predecessor_parent_commit": self.BASE_PARENT,
            "public_predecessor_ref": self.SOURCE_REF,
            "public_predecessor_tree": self.BASE_TREE,
            "terminal_closeout_required_parent_commit": self.BASE_COMMIT,
        }
        for key, value in expected.items():
            self.assertEqual(self.superseded[key], value, key)
        self.assertIs(self.superseded["development_only"], True)
        self.assertIs(self.superseded["publication_retry_permitted"], False)
        self.assertIs(self.superseded["resumption_permitted"], False)

    def test_single_v46_precreation_incident_is_exact(self) -> None:
        self.assertEqual(len(self.superseded["publication_incidents"]), 1)
        incident = self.superseded["publication_incidents"][0]
        self.assertEqual(
            incident,
            {
                "authentication_cli_invocations": 0,
                "authentication_processes_started": 0,
                "but_diff_invocations": 0,
                "candidate_clone_attempts": 0,
                "cause_code": (
                    "control_plane_precreation_starsim_isolated_cache_environment_"
                    "unbound"
                ),
                "cohort_creation_invocations": 0,
                "credential_route_checks": 0,
                "file_authoring_invocations": 0,
                "file_writes": 0,
                "fresh_path_absence_observations_passed": 8,
                "fresh_path_absence_observations_required": 8,
                "fresh_path_absence_rounds_passed": 2,
                "fresh_paths_checked": 4,
                "gitbutler_commit_invocations": 0,
                "gitbutler_push_invocations": 0,
                "gitbutler_setup_invocations": 0,
                "gitbutler_version_pin_passed": True,
                "hook_integrity_checks": 0,
                "inherited_public_closeout_hashes_validated": 4,
                "isolated_scientific_cache_environment_bound_before_import": False,
                "lifecycle_absence_reads_attempted": 2,
                "lifecycle_absence_reads_passed": 2,
                "local_filesystem_mutation_observed": False,
                "manifest_creation_invocations": 0,
                "model_calls_started": 0,
                "namespace": "v46_control_plane_phase_b_precreation",
                "precreation_gate_passed": False,
                "preflight_profiles_started": 0,
                "private_state_creation_invocations": 0,
                "production_assignments_started": 0,
                "provider_processes_started": 0,
                "public_source_delta_validation_passed": True,
                "public_source_head_validation_passed": True,
                "public_source_parent_validation_passed": True,
                "public_source_tree_validation_passed": True,
                "publisher_clone_attempts": 0,
                "release_clone_attempts": 0,
                "remote_mutation_observed": False,
                "repository_clone_attempts": 0,
                "repository_python_version_pin_passed": True,
                "result_artifact_creation_invocations": 0,
                "ruff_format_check_invocations": 0,
                "ruff_format_invocations": 0,
                "ruff_lint_invocations": 0,
                "ruff_version_pin_passed": True,
                "scientific_python_version_pin_passed": True,
                "source_ref_pin_queries_attempted": 2,
                "source_ref_pin_queries_passed": 2,
                "stage": (
                    "control_plane_precreation_scientific_runtime_starsim_import_"
                    "validation_before_hook_credential_clone_and_mutation"
                ),
                "starsim_import_validation_attempts": 1,
                "starsim_import_validation_passes": 0,
                "starsim_version_validations_completed": 0,
                "stdlib_unittest_invocations": 0,
                "supervisor_generation_invocations": 0,
                "terminal_stop_applied": True,
            },
        )

    def test_disposable_diagnostics_are_separate_and_exact(self) -> None:
        self.assertEqual(
            self.superseded["post_terminal_disposable_diagnostic_audit"],
            {
                "account_route_correction_authorizations": 1,
                "account_route_correction_completions": 1,
                "artifacts_released": False,
                "ceremony_retry_invocations": 0,
                "ceremony_state_reused": False,
                "commits_created": 0,
                "full_smoke_diagnostic_processes_completed": 4,
                "full_smoke_diagnostic_processes_started": 4,
                "full_smoke_invocations_completed": 6,
                "full_smoke_invocations_started": 6,
                "full_smoke_reviewed_results_matched": True,
                "gitbutler_push_invocations": 0,
                "gitbutler_setup_completions": 1,
                "host_readiness_attempts": 2,
                "host_readiness_attempts_passed": 1,
                "isolated_cache_binding_validated": True,
                "isolated_starsim_import_validated": True,
                "lifecycle_values_created": False,
                "model_calls_started": 0,
                "provider_calls_started": 0,
                "remote_mutation_observed": False,
                "route_mismatch_terminal_stops": 1,
                "second_host_readiness_attempt_passed": True,
                "teardown_completed": True,
                "version_neutral": True,
            },
        )

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

    def test_v46_is_terminal_and_v47_is_declarative_only(self) -> None:
        self.assertIs(
            self.superseded["v46_persistent_supervisor_contract_v22_reuse_permitted"],
            False,
        )
        self.assertIs(
            self.superseded["v47_persistent_supervisor_contract_v23_required"],
            True,
        )
        self.assertIs(self.superseded["v47_panel_supersession_v31_reserved"], True)
        self.assertIs(self.superseded["v47_declarative_replacement_only"], True)
        for key in (
            "v46_acknowledgement_receipt_recorded",
            "v46_commit_or_hash_values_recorded",
            "v46_control_plane_created",
            "v46_control_plane_published",
            "v46_unpublished_control_plane_values_released",
            "v47_acknowledgement_receipt_recorded",
            "v47_commit_or_hash_values_recorded",
            "v47_control_plane_created",
            "v47_control_plane_published",
            "v47_runtime_values_created",
        ):
            self.assertIs(self.superseded[key], False, key)
        panel_ids = {
            value
            for value in self._strings(self.superseded)
            if value.startswith("development-matched-50x6-")
        }
        self.assertEqual(
            panel_ids,
            {"development-matched-50x6-v46", "development-matched-50x6-v47"},
        )

    def test_public_source_shape_and_inherited_hashes_are_exact(self) -> None:
        parents = subprocess.run(
            ["/usr/bin/git", "show", "-s", "--format=%P", self.BASE_COMMIT],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.strip()
        self.assertEqual(parents, self.BASE_PARENT)
        tree = subprocess.run(
            ["/usr/bin/git", "show", "-s", "--format=%T", self.BASE_COMMIT],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.strip()
        self.assertEqual(tree, self.BASE_TREE)
        changed_paths = subprocess.run(
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
            sorted(changed_paths),
            sorted(
                (
                    "results/development-matched-50x6-v40.superseded.json",
                    "tests/test_v40_supersession.py",
                )
            ),
        )
        for path, expected in self.INHERITED_HASHES.items():
            actual = hashlib.sha256((self.root / path).read_bytes()).hexdigest()
            self.assertEqual(actual, expected, path)

    def test_record_releases_no_protected_local_or_unpublished_values(self) -> None:
        forbidden_keys = {
            "access_token",
            "account",
            "account_id",
            "api_key",
            "argv",
            "cache_path",
            "candidate_path",
            "candidate_sha256",
            "client_id",
            "command",
            "credential_path",
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
        tree_paths = subprocess.run(
            ["/usr/bin/git", "ls-tree", "-r", "--name-only", closeout_commit],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.splitlines()
        for forbidden_path in (
            "results/development-matched-50x6-v46.runtime.json",
            "results/development-matched-50x6-v46.manifest.json",
            "results/development-matched-50x6-v46.authentication.json",
            "results/development-matched-50x6-v46.verification.json",
            "results/development-matched-50x6-v46.preflight.json",
            "results/development-matched-50x6-v46.json",
        ):
            self.assertNotIn(forbidden_path, tree_paths)
        self.assertFalse(any("candidate" in path.lower() for path in tree_paths))


if __name__ == "__main__":
    unittest.main()
