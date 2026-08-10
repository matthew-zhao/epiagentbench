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


class V33SupersessionTests(unittest.TestCase):
    PUBLIC_PREDECESSOR_COMMIT = (
        "f26d8f7e50748883142f3452ee11daf43595e421"
    )
    PUBLIC_PREDECESSOR_PARENT_COMMIT = (
        "c6cd10e795944e08e76a6de249689d1a5538099b"
    )
    PUBLIC_PREDECESSOR_TREE = (
        "2daa94031f3d34cf5b4283928c3523af7ee758c4"
    )
    LOCAL_CONTROL_COMMIT = (
        "dac82434f2e2a73d511df418755b28003222ab3b"
    )
    LOCAL_CONTROL_TREE = "0e2fa417ab5ebf3c3b952269425bf7e74b9f4ce9"
    SUPERSESSION_PATH = (
        "results/development-matched-50x6-v33.superseded.json"
    )
    TEST_PATH = "tests/test_v33_supersession.py"
    CLOSEOUT_REF = (
        "refs/heads/codex/"
        "v33-control-plane-publication-terminal-closeout"
    )
    LOCAL_CONTROL_SCOPE = (
        "README.md",
        "docs/PERSISTENT_RUNNER_PROTOCOL.md",
        "docs/V32_RUNBOOK.md",
        "docs/V33_DESIGN.md",
        "docs/V33_RUNBOOK.md",
        "src/epiagentbench/development_matched_panel.py",
        "src/epiagentbench/launchd_agent.py",
        "tests/test_development_matched_panel.py",
        "tests/test_persistent_launchd.py",
        "tests/test_persistent_runner_cli.py",
        "tests/test_terminal_receipt_attestation.py",
        "tests/test_v28_typed_contract_attestation.py",
        "tests/test_v31_supersession.py",
        "tests/test_v32_publication_topology.py",
        "tests/test_v33_deferred_cursor_credential.py",
        "tests/test_v33_preclaim_reconciliation.py",
        "tests/test_v33_preparation_substages.py",
        "tests/test_v33_publication_topology.py",
        "tests/test_v33_smoke_tmpdir.py",
    )
    REPLACEMENT_REQUIREMENTS = (
        "fresh_panel_and_cohort_identity",
        "fresh_runtime_cache_and_runtime_receipt",
        "fresh_authentication_key_and_provider_namespaces",
        "fresh_private_schedule_and_cohort",
        "fresh_checkout_supervisor_socket_temporary_and_output_namespaces",
        "closed_public_v33_control_plane_publication_supersession_path",
        "independently_pinned_v34_control_plane",
        "independently_pinned_v34_runtime_receipt_before_manifest",
        "create_once_provider_free_runtime_publication_terminal_closeout",
        "fresh_v34_manifest_bound_spend_authorization",
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
            raise TypeError("V33 supersession must be a JSON object")
        cls.superseded = payload

    @staticmethod
    def _keys(payload: object) -> set[str]:
        observed: set[str] = set()
        if isinstance(payload, Mapping):
            for key, value in payload.items():
                observed.add(str(key))
                observed.update(V33SupersessionTests._keys(value))
        elif isinstance(payload, Sequence) and not isinstance(
            payload, (str, bytes, bytearray)
        ):
            for value in payload:
                observed.update(V33SupersessionTests._keys(value))
        return observed

    @staticmethod
    def _strings(payload: object) -> list[str]:
        observed: list[str] = []
        if isinstance(payload, str):
            observed.append(payload)
        elif isinstance(payload, Mapping):
            for value in payload.values():
                observed.extend(V33SupersessionTests._strings(value))
        elif isinstance(payload, Sequence) and not isinstance(
            payload, (str, bytes, bytearray)
        ):
            for value in payload:
                observed.extend(V33SupersessionTests._strings(value))
        return observed

    def test_canonical_duplicate_free_record(self) -> None:
        expected = (
            json.dumps(self.superseded, sort_keys=True, indent=2) + "\n"
        ).encode("utf-8")
        self.assertEqual(self.raw, expected)

    def test_exact_public_contract(self) -> None:
        expected: dict[str, object] = {
            "audited_root_cause_code": (
                "gitbutler_credential_routing_http_403_before_remote_update"
            ),
            "authentication_cli_invocations": 0,
            "authentication_processes_started": 0,
            "authentication_receipt_created": False,
            "control_plane_closeout_ref": self.CLOSEOUT_REF,
            "control_plane_remote_records_observed": 0,
            "control_plane_remote_ref": (
                "refs/heads/codex/v33-control-plane"
            ),
            "control_plane_remote_ref_present": False,
            "credential_secret_material_inspected": False,
            "development_only": True,
            "exception_text_released": False,
            "failure_stage": (
                "gitbutler_control_plane_publication_before_remote_update"
            ),
            "gitbutler_publication_attempts": 1,
            "gitbutler_publication_command_returned": True,
            "gitbutler_publication_exit_code": 1,
            "gitbutler_publication_succeeded": False,
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
            "original_panel_id": "development-matched-50x6-v33",
            "preflight_profiles_attempted": 0,
            "preflight_profiles_passed": 0,
            "private_authentication_key_created": False,
            "private_cohort_created": False,
            "private_state_created": False,
            "production_assignments_started": 0,
            "protected_payloads_inspected": False,
            "provider_free_runtime_receipt_candidate_comparison_performed": False,
            "provider_free_runtime_receipt_candidates_generated": 0,
            "provider_free_runtime_receipt_candidates_passed": 0,
            "provider_free_runtime_receipt_installations": 0,
            "provider_free_runtime_receipt_installed_locally": False,
            "provider_processes_started": 0,
            "public_predecessor_commit": self.PUBLIC_PREDECESSOR_COMMIT,
            "public_predecessor_parent_commit": (
                self.PUBLIC_PREDECESSOR_PARENT_COMMIT
            ),
            "public_predecessor_ref": (
                "refs/heads/codex/"
                "v32-runtime-publication-terminal-closeout"
            ),
            "public_predecessor_tree": self.PUBLIC_PREDECESSOR_TREE,
            "public_preflight_artifact_created": False,
            "public_results_artifact_created": False,
            "public_runtime_receipt_created": False,
            "publication_retry_permitted": False,
            "raw_provider_outputs_inspected": False,
            "remote_ref_mutation_observed": False,
            "replacement_panel_id": "development-matched-50x6-v34",
            "replacement_requirements": list(self.REPLACEMENT_REQUIREMENTS),
            "replacement_values_status": "not_yet_created_or_published",
            "results_released": False,
            "resumption_permitted": False,
            "schema_version": "epiagentbench.panel_supersession.v26",
            "scores_inspected": False,
            "scores_released": False,
            "spend_acknowledgement_supplied": False,
            "spend_authorization_recorded": False,
            "start_cli_invocations": 0,
            "status": "failed_zero_model_control_plane_publication",
            "supervisor_runtime_generated": False,
            "terminal_closeout_required_parent_commit": (
                self.PUBLIC_PREDECESSOR_COMMIT
            ),
            "terminal_closeout_unpublished_control_commit_in_ancestry_permitted": False,
            "terminal_closeout_unpublished_control_delta_in_tree_permitted": False,
            "terminal_record_kind": (
                "control_plane_publication_incident_supersession"
            ),
            "traces_inspected": False,
            "traces_released": False,
            "unpublished_local_control_plane_authoritative": False,
            "unpublished_local_control_plane_commit": self.LOCAL_CONTROL_COMMIT,
            "unpublished_local_control_plane_commit_scope": list(
                self.LOCAL_CONTROL_SCOPE
            ),
            "unpublished_local_control_plane_parent_commit": (
                self.PUBLIC_PREDECESSOR_COMMIT
            ),
            "unpublished_local_control_plane_published": False,
            "unpublished_local_control_plane_reuse_permitted": False,
            "unpublished_local_control_plane_tree": self.LOCAL_CONTROL_TREE,
            "v33_cohort_reuse_permitted": False,
            "v33_conservative_claude_ceiling_added_usd": 0,
            "v33_key_or_namespace_reuse_permitted": False,
            "v34_acknowledgement_receipt_recorded": False,
            "v34_commit_or_hash_values_recorded": False,
            "verification_cli_invocations": 0,
            "verification_receipt_created": False,
        }
        observed = dict(self.superseded)
        observed.pop("superseded_at_utc")
        self.assertEqual(observed, expected)

    def test_public_predecessor_is_exactly_pinned(self) -> None:
        observed = subprocess.run(
            [
                "git",
                "show",
                "-s",
                "--format=%H %P %T",
                self.PUBLIC_PREDECESSOR_COMMIT,
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
                    self.PUBLIC_PREDECESSOR_COMMIT,
                    self.PUBLIC_PREDECESSOR_PARENT_COMMIT,
                    self.PUBLIC_PREDECESSOR_TREE,
                )
            ),
        )

    def test_failed_control_publication_is_terminal(self) -> None:
        self.assertEqual(
            self.superseded["status"],
            "failed_zero_model_control_plane_publication",
        )
        self.assertEqual(
            self.superseded["terminal_record_kind"],
            "control_plane_publication_incident_supersession",
        )
        self.assertEqual(self.superseded["gitbutler_publication_attempts"], 1)
        self.assertIs(
            self.superseded["gitbutler_publication_command_returned"], True
        )
        self.assertEqual(self.superseded["gitbutler_publication_exit_code"], 1)
        for key in (
            "gitbutler_publication_succeeded",
            "control_plane_remote_ref_present",
            "remote_ref_mutation_observed",
            "publication_retry_permitted",
            "resumption_permitted",
        ):
            self.assertIs(self.superseded[key], False, key)
        self.assertEqual(
            self.superseded["control_plane_remote_records_observed"], 0
        )

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
            "start_cli_invocations",
            "v33_conservative_claude_ceiling_added_usd",
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
            "private_authentication_key_created",
            "private_cohort_created",
            "private_state_created",
            "provider_free_runtime_receipt_candidate_comparison_performed",
            "provider_free_runtime_receipt_installed_locally",
            "public_preflight_artifact_created",
            "public_results_artifact_created",
            "public_runtime_receipt_created",
            "spend_acknowledgement_supplied",
            "spend_authorization_recorded",
            "supervisor_runtime_generated",
            "verification_receipt_created",
        ):
            self.assertIs(self.superseded[key], False, key)

    def test_unpublished_control_candidate_is_quarantined(self) -> None:
        self.assertEqual(
            self.superseded["unpublished_local_control_plane_commit"],
            self.LOCAL_CONTROL_COMMIT,
        )
        self.assertEqual(
            self.superseded["unpublished_local_control_plane_parent_commit"],
            self.PUBLIC_PREDECESSOR_COMMIT,
        )
        self.assertEqual(
            self.superseded["unpublished_local_control_plane_tree"],
            self.LOCAL_CONTROL_TREE,
        )
        self.assertEqual(
            self.superseded["unpublished_local_control_plane_commit_scope"],
            list(self.LOCAL_CONTROL_SCOPE),
        )
        for key in (
            "unpublished_local_control_plane_authoritative",
            "unpublished_local_control_plane_published",
            "unpublished_local_control_plane_reuse_permitted",
            "terminal_closeout_unpublished_control_commit_in_ancestry_permitted",
            "terminal_closeout_unpublished_control_delta_in_tree_permitted",
        ):
            self.assertIs(self.superseded[key], False, key)

    def test_v33_is_nonreusable_and_v34_is_unset(self) -> None:
        self.assertIs(self.superseded["v33_cohort_reuse_permitted"], False)
        self.assertIs(
            self.superseded["v33_key_or_namespace_reuse_permitted"], False
        )
        self.assertEqual(
            self.superseded["replacement_panel_id"],
            "development-matched-50x6-v34",
        )
        self.assertEqual(
            self.superseded["replacement_values_status"],
            "not_yet_created_or_published",
        )
        self.assertIs(
            self.superseded["v34_acknowledgement_receipt_recorded"], False
        )
        self.assertIs(
            self.superseded["v34_commit_or_hash_values_recorded"], False
        )

    def test_record_releases_no_protected_or_account_data(self) -> None:
        forbidden_keys = {
            "access_token",
            "account",
            "account_id",
            "api_key",
            "argv",
            "credential",
            "credentials",
            "email",
            "episode_id",
            "episode_ref",
            "exception",
            "family",
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
                "github.com",
                "github_pat_",
                "ghp_",
                "keychain",
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
            "scores_inspected",
            "scores_released",
            "traces_inspected",
            "traces_released",
        ):
            self.assertIs(self.superseded[key], False, key)

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

        committed_artifact = subprocess.run(
            [
                "git",
                "ls-tree",
                "-r",
                "--name-only",
                closeout_commit,
                "--",
                self.SUPERSESSION_PATH,
            ],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.splitlines()
        if self.SUPERSESSION_PATH not in committed_artifact:
            self.skipTest("closeout branch does not contain the artifact yet")

        introducing_commit = subprocess.run(
            [
                "git",
                "log",
                "-1",
                "--format=%H",
                "--",
                self.SUPERSESSION_PATH,
            ],
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
        self.assertEqual(parents, self.PUBLIC_PREDECESSOR_COMMIT)

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

        unpublished_scope_changes = subprocess.run(
            [
                "git",
                "diff",
                "--name-only",
                self.PUBLIC_PREDECESSOR_COMMIT,
                closeout_commit,
                "--",
                *self.LOCAL_CONTROL_SCOPE,
            ],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.splitlines()
        self.assertEqual(unpublished_scope_changes, [])

        tree_paths = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", closeout_commit],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.splitlines()
        for forbidden_path in (
            "docs/V33_DESIGN.md",
            "docs/V33_RUNBOOK.md",
            "results/development-matched-50x6-v33.runtime.json",
            "results/development-matched-50x6-v33.manifest.json",
            "results/development-matched-50x6-v33.authentication.json",
            "results/development-matched-50x6-v33.verification.json",
            "results/development-matched-50x6-v33.preflight.json",
            "results/development-matched-50x6-v33.json",
            "tests/test_v33_deferred_cursor_credential.py",
            "tests/test_v33_preclaim_reconciliation.py",
            "tests/test_v33_preparation_substages.py",
            "tests/test_v33_publication_topology.py",
            "tests/test_v33_smoke_tmpdir.py",
        ):
            self.assertNotIn(forbidden_path, tree_paths)

        ancestry = subprocess.run(
            ["git", "rev-list", closeout_commit],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.splitlines()
        self.assertNotIn(self.LOCAL_CONTROL_COMMIT, ancestry)


if __name__ == "__main__":
    unittest.main()
