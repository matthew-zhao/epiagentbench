from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
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


class V34SupersessionTests(unittest.TestCase):
    CONTROL_COMMIT = "72ca992eed6c0faa5961d4063732a8a1da918301"
    CONTROL_PARENT_COMMIT = (
        "47ebbfc799310fc73e60e7cbf90cd37c5f9d6d8d"
    )
    CONTROL_TREE = "8bf73a9753b1b0ea8d5dc2f7e230494a13fd0f47"
    SUPERSESSION_PATH = (
        "results/development-matched-50x6-v34.superseded.json"
    )
    TEST_PATH = "tests/test_v34_supersession.py"
    CLOSEOUT_REF = (
        "refs/heads/codex/"
        "v34-runtime-publication-terminal-closeout"
    )
    REPLACEMENT_REQUIREMENTS = (
        "fresh_panel_and_cohort_identity",
        "fresh_runtime_cache_and_runtime_receipt",
        "fresh_authentication_key_and_provider_namespaces",
        "fresh_private_schedule_and_cohort",
        "fresh_checkout_supervisor_socket_temporary_and_output_namespaces",
        "closed_public_v34_runtime_publication_supersession_path",
        "fresh_v35_control_plane_with_reconciled_root_managed_glean_contract",
        "independently_pinned_v35_control_plane",
        "independently_pinned_v35_runtime_receipt_before_manifest",
        "create_once_provider_free_runtime_publication_terminal_closeout",
        "fresh_v35_manifest_bound_spend_authorization",
        "fresh_six_call_preflight_and_independent_publication_validation",
        "separate_explicit_three_hundred_assignment_production_authorization",
    )

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.raw = (cls.root / cls.SUPERSESSION_PATH).read_bytes()
        payload = json.loads(
            cls.raw,
            object_pairs_hook=_object_without_duplicate_keys,
        )
        if not isinstance(payload, dict):
            raise TypeError("V34 supersession must be a JSON object")
        cls.superseded = payload

    @staticmethod
    def _keys(payload: object) -> set[str]:
        observed: set[str] = set()
        if isinstance(payload, Mapping):
            for key, value in payload.items():
                observed.add(str(key))
                observed.update(V34SupersessionTests._keys(value))
        elif isinstance(payload, Sequence) and not isinstance(
            payload, (str, bytes, bytearray)
        ):
            for value in payload:
                observed.update(V34SupersessionTests._keys(value))
        return observed

    @staticmethod
    def _strings(payload: object) -> list[str]:
        observed: list[str] = []
        if isinstance(payload, str):
            observed.append(payload)
        elif isinstance(payload, Mapping):
            for value in payload.values():
                observed.extend(V34SupersessionTests._strings(value))
        elif isinstance(payload, Sequence) and not isinstance(
            payload, (str, bytes, bytearray)
        ):
            for value in payload:
                observed.extend(V34SupersessionTests._strings(value))
        return observed

    def test_canonical_duplicate_free_record(self) -> None:
        expected = (
            json.dumps(self.superseded, sort_keys=True, indent=2) + "\n"
        ).encode("utf-8")
        self.assertEqual(self.raw, expected)

    def test_exact_public_contract(self) -> None:
        expected: dict[str, object] = {
            "audited_root_cause_code": (
                "root_managed_glean_gateway_route_and_managed_settings_"
                "schema_drift"
            ),
            "authentication_cli_invocations": 0,
            "authentication_processes_started": 0,
            "authentication_receipt_created": False,
            "control_commit": self.CONTROL_COMMIT,
            "control_parent_commit": self.CONTROL_PARENT_COMMIT,
            "control_plane_independently_pinned": True,
            "control_plane_publication_attempts": 1,
            "control_plane_publication_succeeded": True,
            "control_plane_remote_records_observed": 1,
            "control_plane_remote_ref_present": True,
            "control_ref": "refs/heads/codex/v34-control-plane",
            "control_tree": self.CONTROL_TREE,
            "credential_routing_metadata_inspected": True,
            "credential_secret_material_inspected": False,
            "development_only": True,
            "exception_text_released": False,
            "failure_stage": (
                "provider_free_host_contract_validation_before_runtime_"
                "receipt_generation"
            ),
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
            "original_panel_id": "development-matched-50x6-v34",
            "preflight_profiles_attempted": 0,
            "preflight_profiles_passed": 0,
            "private_authentication_key_created": False,
            "private_cohort_created": False,
            "private_state_created": False,
            "production_assignments_started": 0,
            "protected_payloads_inspected": False,
            "provider_free_host_contract_validation_attempted": True,
            "provider_free_host_contract_validation_passed": False,
            "provider_free_runtime_receipt_candidate_comparison_performed": False,
            "provider_free_runtime_receipt_candidates_generated": 0,
            "provider_free_runtime_receipt_candidates_passed": 0,
            "provider_free_runtime_receipt_installations": 0,
            "provider_free_runtime_receipt_installed_locally": False,
            "provider_processes_started": 0,
            "public_preflight_artifact_created": False,
            "public_results_artifact_created": False,
            "public_runtime_receipt_created": False,
            "publication_retry_permitted": False,
            "raw_provider_outputs_inspected": False,
            "replacement_panel_id": "development-matched-50x6-v35",
            "replacement_requirements": list(
                self.REPLACEMENT_REQUIREMENTS
            ),
            "replacement_values_status": "not_yet_created_or_published",
            "results_released": False,
            "resumption_permitted": False,
            "root_managed_configuration_metadata_inspected": True,
            "root_managed_configuration_values_released": False,
            "root_managed_glean_helper_invocations": 0,
            "runtime_publication_terminal_closeout_ref": self.CLOSEOUT_REF,
            "runtime_receipt_generation_cli_invocations": 0,
            "runtime_receipt_publication_attempts": 0,
            "runtime_receipt_publication_succeeded": False,
            "runtime_receipt_remote_mutation_observed": False,
            "runtime_receipt_remote_records_observed": 0,
            "runtime_receipt_remote_ref": (
                "refs/heads/codex/v34-runtime-preflight"
            ),
            "runtime_receipt_remote_ref_present": False,
            "schema_version": "epiagentbench.panel_supersession.v27",
            "scores_inspected": False,
            "scores_released": False,
            "spend_acknowledgement_supplied": False,
            "spend_authorization_recorded": False,
            "start_cli_invocations": 0,
            "status": (
                "failed_zero_model_pre_runtime_host_contract_validation"
            ),
            "supervisor_runtime_generated": False,
            "terminal_closeout_later_v34_artifacts_in_tree_permitted": False,
            "terminal_closeout_required_parent_commit": self.CONTROL_COMMIT,
            "terminal_closeout_runtime_receipt_file_in_tree_permitted": False,
            (
                "terminal_closeout_unpublished_runtime_receipt_in_"
                "ancestry_permitted"
            ): False,
            "terminal_record_kind": (
                "provider_free_pre_runtime_host_contract_incident_"
                "supersession"
            ),
            "traces_inspected": False,
            "traces_released": False,
            "v34_cohort_reuse_permitted": False,
            "v34_conservative_claude_ceiling_added_usd": 0,
            "v34_control_commit_reuse_as_runtime_base_permitted": False,
            "v34_key_or_namespace_reuse_permitted": False,
            "v35_acknowledgement_receipt_recorded": False,
            "v35_commit_or_hash_values_recorded": False,
            "verification_cli_invocations": 0,
            "verification_receipt_created": False,
        }
        observed = dict(self.superseded)
        observed.pop("superseded_at_utc")
        self.assertEqual(observed, expected)

    def test_published_control_commit_is_the_authoritative_base(self) -> None:
        observed = subprocess.run(
            [
                "git",
                "show",
                "-s",
                "--format=%H %P %T",
                self.CONTROL_COMMIT,
            ],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.strip()
        self.assertEqual(
            observed,
            " ".join(
                (
                    self.CONTROL_COMMIT,
                    self.CONTROL_PARENT_COMMIT,
                    self.CONTROL_TREE,
                )
            ),
        )
        self.assertIs(
            self.superseded["control_plane_independently_pinned"], True
        )
        self.assertEqual(
            self.superseded["control_plane_remote_records_observed"], 1
        )
        self.assertIs(
            self.superseded["control_plane_remote_ref_present"], True
        )
        self.assertEqual(
            self.superseded["terminal_closeout_required_parent_commit"],
            self.CONTROL_COMMIT,
        )

    def test_host_contract_failure_is_typed_and_terminal(self) -> None:
        self.assertEqual(
            self.superseded["audited_root_cause_code"],
            "root_managed_glean_gateway_route_and_managed_settings_"
            "schema_drift",
        )
        self.assertEqual(
            self.superseded["failure_stage"],
            "provider_free_host_contract_validation_before_runtime_"
            "receipt_generation",
        )
        self.assertEqual(
            self.superseded["status"],
            "failed_zero_model_pre_runtime_host_contract_validation",
        )
        self.assertEqual(
            self.superseded["terminal_record_kind"],
            "provider_free_pre_runtime_host_contract_incident_"
            "supersession",
        )
        self.assertIs(
            self.superseded[
                "provider_free_host_contract_validation_attempted"
            ],
            True,
        )
        self.assertIs(
            self.superseded[
                "provider_free_host_contract_validation_passed"
            ],
            False,
        )
        for key in (
            "publication_retry_permitted",
            "resumption_permitted",
            "v34_control_commit_reuse_as_runtime_base_permitted",
        ):
            self.assertIs(self.superseded[key], False, key)

    def test_no_runtime_authenticated_or_model_work_started(self) -> None:
        for key in (
            "authentication_cli_invocations",
            "authentication_processes_started",
            "install_cli_invocations",
            "model_bearing_provider_calls_conservatively_chargeable",
            "model_calls_started",
            "preflight_profiles_attempted",
            "preflight_profiles_passed",
            "production_assignments_started",
            "provider_free_runtime_receipt_candidates_generated",
            "provider_free_runtime_receipt_candidates_passed",
            "provider_free_runtime_receipt_installations",
            "provider_processes_started",
            "root_managed_glean_helper_invocations",
            "runtime_receipt_generation_cli_invocations",
            "runtime_receipt_publication_attempts",
            "start_cli_invocations",
            "v34_conservative_claude_ceiling_added_usd",
            "verification_cli_invocations",
        ):
            self.assertEqual(self.superseded[key], 0, key)
        self.assertEqual(
            self.superseded["model_bearing_provider_call_exposure"],
            {"claude": 0, "codex": 0, "cursor": 0, "total": 0},
        )
        for key in (
            "authentication_receipt_created",
            "credential_secret_material_inspected",
            "manifest_created",
            "oauth_state_inspected",
            "private_authentication_key_created",
            "private_cohort_created",
            "private_state_created",
            "provider_free_runtime_receipt_candidate_comparison_performed",
            "provider_free_runtime_receipt_installed_locally",
            "public_preflight_artifact_created",
            "public_results_artifact_created",
            "public_runtime_receipt_created",
            "runtime_receipt_publication_succeeded",
            "runtime_receipt_remote_mutation_observed",
            "runtime_receipt_remote_ref_present",
            "spend_acknowledgement_supplied",
            "spend_authorization_recorded",
            "supervisor_runtime_generated",
            "verification_receipt_created",
        ):
            self.assertIs(self.superseded[key], False, key)
        self.assertEqual(
            self.superseded["runtime_receipt_remote_records_observed"], 0
        )
        self.assertFalse(
            any(
                str(key).startswith("unpublished_local_runtime_receipt_")
                for key in self.superseded
            )
        )

    def test_v34_is_nonreusable_and_v35_is_unset(self) -> None:
        self.assertIs(self.superseded["v34_cohort_reuse_permitted"], False)
        self.assertIs(
            self.superseded["v34_key_or_namespace_reuse_permitted"], False
        )
        self.assertEqual(
            self.superseded["replacement_panel_id"],
            "development-matched-50x6-v35",
        )
        self.assertEqual(
            self.superseded["replacement_requirements"],
            list(self.REPLACEMENT_REQUIREMENTS),
        )
        self.assertEqual(
            self.superseded["replacement_values_status"],
            "not_yet_created_or_published",
        )
        self.assertIs(
            self.superseded["v35_acknowledgement_receipt_recorded"], False
        )
        self.assertIs(
            self.superseded["v35_commit_or_hash_values_recorded"], False
        )

    def test_record_releases_no_protected_or_configuration_values(self) -> None:
        forbidden_keys = {
            "access_token",
            "account",
            "account_id",
            "api_key",
            "argv",
            "client_id",
            "email",
            "episode_id",
            "episode_ref",
            "exception",
            "family",
            "gateway_url",
            "hidden_episode_identifier",
            "observation",
            "oauth_state",
            "password",
            "private_path",
            "private_seed",
            "prompt",
            "provider_output",
            "raw_output",
            "remote_error",
            "schedule",
            "score",
            "stderr",
            "stdout",
            "token",
            "trace",
            "username",
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
                "client_id",
                "github.com",
                "github_pat_",
                "ghp_",
                "oauth_state",
                "osxkeychain",
                "provider_output",
                "https://",
                "trace_steps",
            ):
                self.assertNotIn(fragment, lowered)
        for key in (
            "exception_text_released",
            "hidden_episode_identifiers_or_families_inspected",
            "protected_payloads_inspected",
            "raw_provider_outputs_inspected",
            "results_released",
            "root_managed_configuration_values_released",
            "scores_inspected",
            "scores_released",
            "traces_inspected",
            "traces_released",
        ):
            self.assertIs(self.superseded[key], False, key)
        self.assertIs(
            self.superseded["credential_routing_metadata_inspected"], True
        )
        self.assertIs(
            self.superseded[
                "root_managed_configuration_metadata_inspected"
            ],
            True,
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
            ["git", "ls-files", "--error-unmatch", self.SUPERSESSION_PATH],
            cwd=self.root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if tracked.returncode != 0:
            self.skipTest("closeout is not committed yet")

        closeout_ref = subprocess.run(
            ["git", "rev-parse", "--verify", self.CLOSEOUT_REF],
            cwd=self.root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if closeout_ref.returncode != 0:
            self.skipTest("closeout branch is not finalized yet")
        closeout_commit = closeout_ref.stdout.strip()

        for path in (self.SUPERSESSION_PATH, self.TEST_PATH):
            introducing_commit = subprocess.run(
                ["git", "log", "-1", "--format=%H", "--", path],
                cwd=self.root,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            ).stdout.strip()
            self.assertEqual(introducing_commit, closeout_commit)

        parents = subprocess.run(
            ["git", "show", "-s", "--format=%P", closeout_commit],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.strip()
        self.assertEqual(parents, self.CONTROL_COMMIT)

        changed_paths = subprocess.run(
            [
                "git",
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
            sorted(changed_paths),
            sorted((self.SUPERSESSION_PATH, self.TEST_PATH)),
        )

        tree_paths = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", closeout_commit],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.splitlines()
        for forbidden_path in (
            "results/development-matched-50x6-v34.runtime.json",
            "results/development-matched-50x6-v34.manifest.json",
            "results/development-matched-50x6-v34.authentication.json",
            "results/development-matched-50x6-v34.verification.json",
            "results/development-matched-50x6-v34.preflight.json",
            "results/development-matched-50x6-v34.json",
        ):
            self.assertNotIn(forbidden_path, tree_paths)

        for mutually_exclusive_ref in (
            "refs/heads/codex/v34-control-plane-publication-terminal-closeout",
            "refs/heads/codex/v34-runtime-preflight",
            "refs/heads/codex/v34-preflight-terminal-closeout",
            "refs/heads/codex/v34-production-results",
            "refs/heads/codex/v34-terminal-closeout",
        ):
            observed = subprocess.run(
                ["git", "rev-parse", "--verify", mutually_exclusive_ref],
                cwd=self.root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertNotEqual(observed.returncode, 0, mutually_exclusive_ref)


if __name__ == "__main__":
    unittest.main()
