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


class V32SupersessionTests(unittest.TestCase):
    CONTROL_COMMIT = "c6cd10e795944e08e76a6de249689d1a5538099b"
    CONTROL_PARENT_COMMIT = "9c354164347f2b09a7656171ef5cbc7480111c6e"
    CONTROL_TREE = "e8336b16bdb6384a64eecb583377cc664e2adf4e"
    LOCAL_RUNTIME_COMMIT = "1ffd2f2903cb7a8327ff0ef7a0f10870e1a27e3b"
    LOCAL_RUNTIME_TREE = "33cfdd5e62bd338e55e2deaa72a4a0360ad093df"
    SUPERSESSION_PATH = (
        "results/development-matched-50x6-v32.superseded.json"
    )
    CLOSEOUT_REF = (
        "refs/heads/codex/v32-runtime-publication-terminal-closeout"
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
            raise TypeError("V32 supersession must be a JSON object")
        cls.superseded = payload

    @staticmethod
    def _keys(payload: object) -> set[str]:
        observed: set[str] = set()
        if isinstance(payload, Mapping):
            for key, value in payload.items():
                observed.add(str(key))
                observed.update(V32SupersessionTests._keys(value))
        elif isinstance(payload, Sequence) and not isinstance(
            payload, (str, bytes, bytearray)
        ):
            for value in payload:
                observed.update(V32SupersessionTests._keys(value))
        return observed

    @staticmethod
    def _strings(payload: object) -> list[str]:
        observed: list[str] = []
        if isinstance(payload, str):
            observed.append(payload)
        elif isinstance(payload, Mapping):
            for value in payload.values():
                observed.extend(V32SupersessionTests._strings(value))
        elif isinstance(payload, Sequence) and not isinstance(
            payload, (str, bytes, bytearray)
        ):
            for value in payload:
                observed.extend(V32SupersessionTests._strings(value))
        return observed

    def test_canonical_duplicate_free_closed_record(self) -> None:
        self.assertEqual(
            self.superseded["schema_version"],
            "epiagentbench.panel_supersession.v25",
        )
        expected = (
            json.dumps(self.superseded, sort_keys=True, indent=2) + "\n"
        ).encode("utf-8")
        self.assertEqual(self.raw, expected)

    def test_exact_public_contract_keys(self) -> None:
        expected_keys = {
            "audited_root_cause_code",
            "authentication_cli_invocations",
            "authentication_processes_started",
            "authentication_receipt_created",
            "control_commit",
            "control_parent_commit",
            "control_ref",
            "control_tree",
            "credentials_or_oauth_state_inspected",
            "development_only",
            "exception_text_released",
            "failure_stage",
            "gitbutler_publication_attempt_completed",
            "gitbutler_publication_attempts",
            "gitbutler_publication_exit_code",
            "hidden_episode_identifiers_or_families_inspected",
            "install_cli_invocations",
            "manifest_created",
            "model_bearing_provider_call_exposure",
            "model_bearing_provider_calls_conservatively_chargeable",
            "model_calls_started",
            "original_panel_id",
            "preflight_profiles_attempted",
            "preflight_profiles_passed",
            "private_cohort_created",
            "production_assignments_started",
            "protected_payloads_inspected",
            "provider_free_runtime_receipt_candidates_byte_identical",
            "provider_free_runtime_receipt_candidates_generated",
            "provider_free_runtime_receipt_candidates_passed",
            "provider_free_runtime_receipt_installations",
            "provider_free_runtime_receipt_installed_locally",
            "provider_processes_started",
            "public_preflight_artifact_created",
            "public_results_artifact_created",
            "publication_retry_permitted",
            "raw_provider_outputs_inspected",
            "remote_ref_mutation_observed",
            "replacement_panel_id",
            "replacement_requirements",
            "replacement_values_status",
            "results_released",
            "resumption_permitted",
            "runtime_receipt_remote_records_observed",
            "runtime_receipt_remote_ref",
            "runtime_receipt_remote_ref_present",
            "schema_version",
            "scores_inspected",
            "scores_released",
            "start_cli_invocations",
            "status",
            "superseded_at_utc",
            "supervisor_runtime_generated",
            "terminal_closeout_required_parent_commit",
            "terminal_closeout_runtime_receipt_file_in_tree_permitted",
            "terminal_closeout_unpublished_runtime_receipt_in_ancestry_permitted",
            "terminal_record_kind",
            "traces_inspected",
            "traces_released",
            "unpublished_local_runtime_receipt_authoritative",
            "unpublished_local_runtime_receipt_commit",
            "unpublished_local_runtime_receipt_commit_scope",
            "unpublished_local_runtime_receipt_parent_commit",
            "unpublished_local_runtime_receipt_published",
            "unpublished_local_runtime_receipt_reuse_permitted",
            "unpublished_local_runtime_receipt_tree",
            "v32_cohort_reuse_permitted",
            "v32_conservative_claude_ceiling_added_usd",
            "v32_key_or_namespace_reuse_permitted",
            "v33_acknowledgement_receipt_recorded",
            "v33_commit_or_hash_values_recorded",
            "verification_cli_invocations",
            "verification_receipt_created",
        }
        self.assertEqual(set(self.superseded), expected_keys)
        self.assertEqual(
            self.superseded["original_panel_id"],
            "development-matched-50x6-v32",
        )
        self.assertIs(self.superseded["development_only"], True)

    def test_published_control_commit_is_the_only_authoritative_base(self) -> None:
        observed = subprocess.run(
            ["git", "show", "-s", "--format=%H %P %T", self.CONTROL_COMMIT],
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
        self.assertEqual(self.superseded["control_commit"], self.CONTROL_COMMIT)
        self.assertEqual(
            self.superseded["control_parent_commit"],
            self.CONTROL_PARENT_COMMIT,
        )
        self.assertEqual(self.superseded["control_tree"], self.CONTROL_TREE)
        self.assertEqual(
            self.superseded["terminal_closeout_required_parent_commit"],
            self.CONTROL_COMMIT,
        )

    def test_unpublished_receipt_is_non_authoritative_incident_evidence(self) -> None:
        self.assertEqual(
            self.superseded["unpublished_local_runtime_receipt_commit"],
            self.LOCAL_RUNTIME_COMMIT,
        )
        self.assertEqual(
            self.superseded["unpublished_local_runtime_receipt_parent_commit"],
            self.CONTROL_COMMIT,
        )
        self.assertEqual(
            self.superseded["unpublished_local_runtime_receipt_tree"],
            self.LOCAL_RUNTIME_TREE,
        )
        self.assertEqual(
            self.superseded["unpublished_local_runtime_receipt_commit_scope"],
            ["results/development-matched-50x6-v32.runtime.json"],
        )
        for key in (
            "unpublished_local_runtime_receipt_authoritative",
            "unpublished_local_runtime_receipt_published",
            "unpublished_local_runtime_receipt_reuse_permitted",
            "terminal_closeout_unpublished_runtime_receipt_in_ancestry_permitted",
            "terminal_closeout_runtime_receipt_file_in_tree_permitted",
        ):
            self.assertIs(self.superseded[key], False, key)

    def test_single_failed_gitbutler_publication_changed_no_remote_ref(self) -> None:
        self.assertEqual(
            self.superseded["status"],
            "failed_zero_model_runtime_receipt_publication",
        )
        self.assertEqual(
            self.superseded["terminal_record_kind"],
            "provider_free_runtime_receipt_publication_incident_supersession",
        )
        self.assertEqual(
            self.superseded["audited_root_cause_code"],
            "gitbutler_stale_stack_metadata_and_http_403_before_remote_update",
        )
        self.assertEqual(
            self.superseded["failure_stage"],
            "gitbutler_runtime_receipt_publication_before_remote_update",
        )
        self.assertEqual(self.superseded["gitbutler_publication_attempts"], 1)
        self.assertIs(
            self.superseded["gitbutler_publication_attempt_completed"],
            False,
        )
        self.assertEqual(self.superseded["gitbutler_publication_exit_code"], 1)
        self.assertEqual(
            self.superseded["runtime_receipt_remote_ref"],
            "refs/heads/codex/v32-runtime-preflight",
        )
        self.assertEqual(
            self.superseded["runtime_receipt_remote_records_observed"], 0
        )
        self.assertIs(
            self.superseded["runtime_receipt_remote_ref_present"], False
        )
        self.assertIs(self.superseded["remote_ref_mutation_observed"], False)
        self.assertIs(self.superseded["publication_retry_permitted"], False)

    def test_no_authenticated_or_model_bearing_work_started(self) -> None:
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
            "verification_cli_invocations",
            "v32_conservative_claude_ceiling_added_usd",
        ):
            self.assertEqual(self.superseded[key], 0, key)
        self.assertEqual(
            self.superseded["model_bearing_provider_call_exposure"],
            {"claude": 0, "codex": 0, "cursor": 0, "total": 0},
        )
        self.assertEqual(
            self.superseded["provider_free_runtime_receipt_candidates_generated"],
            2,
        )
        self.assertEqual(
            self.superseded["provider_free_runtime_receipt_candidates_passed"],
            2,
        )
        self.assertIs(
            self.superseded[
                "provider_free_runtime_receipt_candidates_byte_identical"
            ],
            True,
        )
        self.assertEqual(
            self.superseded["provider_free_runtime_receipt_installations"], 1
        )
        self.assertIs(
            self.superseded["provider_free_runtime_receipt_installed_locally"],
            True,
        )

    def test_no_downstream_or_private_artifact_is_claimed(self) -> None:
        for key in (
            "authentication_receipt_created",
            "manifest_created",
            "private_cohort_created",
            "public_preflight_artifact_created",
            "public_results_artifact_created",
            "supervisor_runtime_generated",
            "verification_receipt_created",
        ):
            self.assertIs(self.superseded[key], False, key)

    def test_v32_is_nonresumable_and_v33_is_unset(self) -> None:
        self.assertIs(self.superseded["resumption_permitted"], False)
        self.assertIs(self.superseded["v32_cohort_reuse_permitted"], False)
        self.assertIs(
            self.superseded["v32_key_or_namespace_reuse_permitted"], False
        )
        self.assertEqual(
            self.superseded["replacement_panel_id"],
            "development-matched-50x6-v33",
        )
        self.assertEqual(
            self.superseded["replacement_values_status"],
            "not_yet_created_or_published",
        )
        self.assertIs(
            self.superseded["v33_acknowledgement_receipt_recorded"], False
        )
        self.assertIs(
            self.superseded["v33_commit_or_hash_values_recorded"], False
        )

    def test_record_is_trace_free_and_contains_no_protected_payload(self) -> None:
        forbidden_keys = {
            "access_token",
            "api_key",
            "argv",
            "credential",
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
            "schedule",
            "score",
            "stderr",
            "stdout",
            "trace",
        }
        self.assertTrue(forbidden_keys.isdisjoint(self._keys(self.superseded)))
        for value in self._strings(self.superseded):
            lowered = value.lower()
            self.assertFalse(lowered.startswith(("/", "~", "file://")))
            self.assertNotIn("\n", value)
            for fragment in (
                "/private/",
                "/users/",
                "access_token",
                "api_key",
                "episode_",
                "family",
                "oauth_state",
                "observation",
                "private_seed",
                "prompt",
                "provider_output",
                "score",
                "trace_steps",
            ):
                self.assertNotIn(fragment, lowered)
        for key in (
            "credentials_or_oauth_state_inspected",
            "hidden_episode_identifiers_or_families_inspected",
            "protected_payloads_inspected",
            "raw_provider_outputs_inspected",
            "scores_inspected",
            "scores_released",
            "traces_inspected",
            "traces_released",
            "results_released",
            "exception_text_released",
        ):
            self.assertIs(self.superseded[key], False, key)

    def test_supersession_timestamp_is_current_utc(self) -> None:
        superseded_at = datetime.fromisoformat(
            str(self.superseded["superseded_at_utc"]).replace("Z", "+00:00")
        )
        self.assertEqual(superseded_at.tzinfo, timezone.utc)
        self.assertLessEqual(superseded_at, datetime.now(timezone.utc))

    def test_committed_closeout_has_the_approved_two_file_topology(self) -> None:
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", self.SUPERSESSION_PATH],
            cwd=self.root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if tracked.returncode != 0:
            self.skipTest("closeout is not committed yet")

        closeout_commit = subprocess.run(
            ["git", "log", "-1", "--format=%H", "--", self.SUPERSESSION_PATH],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.strip()
        closeout_ref = subprocess.run(
            ["git", "rev-parse", self.CLOSEOUT_REF],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.strip()
        self.assertEqual(closeout_commit, closeout_ref)

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
            sorted((self.SUPERSESSION_PATH, "tests/test_v32_supersession.py")),
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
            "results/development-matched-50x6-v32.runtime.json",
            "results/development-matched-50x6-v32.manifest.json",
            "results/development-matched-50x6-v32.authentication.json",
            "results/development-matched-50x6-v32.preflight.json",
            "results/development-matched-50x6-v32.json",
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
        self.assertNotIn(self.LOCAL_RUNTIME_COMMIT, ancestry)


if __name__ == "__main__":
    unittest.main()
