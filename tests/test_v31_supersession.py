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


class V31SupersessionTests(unittest.TestCase):
    CONTROL_COMMIT = "6efe0fa93e9c72946b48c22ab27a7fe6b41c199c"
    CLOSEOUT_COMMIT = "9c354164347f2b09a7656171ef5cbc7480111c6e"
    CLOSEOUT_TREE = "669e055fd92bff0c29c2f3a1949748bf58172ecb"
    LOCAL_RUNTIME_COMMIT = "4bb1cc37bceb8b8c723db4307eea595b28cc5bb4"
    SUPERSESSION_PATH = (
        "results/development-matched-50x6-v31.superseded.json"
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
            raise TypeError("V31 supersession must be a JSON object")
        cls.superseded = payload

    @staticmethod
    def _keys(payload: object) -> set[str]:
        observed: set[str] = set()
        if isinstance(payload, Mapping):
            for key, value in payload.items():
                observed.add(str(key))
                observed.update(V31SupersessionTests._keys(value))
        elif isinstance(payload, Sequence) and not isinstance(
            payload, (str, bytes, bytearray)
        ):
            for value in payload:
                observed.update(V31SupersessionTests._keys(value))
        return observed

    @staticmethod
    def _strings(payload: object) -> list[str]:
        observed: list[str] = []
        if isinstance(payload, str):
            observed.append(payload)
        elif isinstance(payload, Mapping):
            for value in payload.values():
                observed.extend(V31SupersessionTests._strings(value))
        elif isinstance(payload, Sequence) and not isinstance(
            payload, (str, bytes, bytearray)
        ):
            for value in payload:
                observed.extend(V31SupersessionTests._strings(value))
        return observed

    def test_canonical_duplicate_free_closed_record(self) -> None:
        self.assertEqual(
            self.superseded["schema_version"],
            "epiagentbench.panel_supersession.v24",
        )
        expected = (
            json.dumps(self.superseded, sort_keys=True, indent=2) + "\n"
        ).encode("utf-8")
        self.assertEqual(self.raw, expected)

    def test_published_control_commit_is_the_only_authoritative_base(self) -> None:
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
                    "36f12893ee016cb83be1d90222a5fdba875b4de0",
                    "f9e2d40cee711d902818add7717335b55c18a9ba",
                )
            ),
        )
        self.assertEqual(self.superseded["control_commit"], self.CONTROL_COMMIT)
        self.assertEqual(
            self.superseded["control_parent_commit"],
            "36f12893ee016cb83be1d90222a5fdba875b4de0",
        )
        self.assertEqual(
            self.superseded["control_tree"],
            "f9e2d40cee711d902818add7717335b55c18a9ba",
        )
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
            "305210bd0cf1b7c2089b1bad6b13e701e704dd8c",
        )
        self.assertEqual(
            self.superseded["unpublished_local_runtime_receipt_commit_scope"],
            ["results/development-matched-50x6-v31.runtime.json"],
        )
        self.assertIs(
            self.superseded["unpublished_local_runtime_receipt_authoritative"],
            False,
        )
        self.assertIs(
            self.superseded["unpublished_local_runtime_receipt_published"],
            False,
        )
        self.assertIs(
            self.superseded["unpublished_local_runtime_receipt_reuse_permitted"],
            False,
        )
        self.assertIs(
            self.superseded[
                "terminal_closeout_unpublished_runtime_receipt_in_ancestry_permitted"
            ],
            False,
        )
        self.assertIs(
            self.superseded[
                "terminal_closeout_runtime_receipt_file_in_tree_permitted"
            ],
            False,
        )

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
            "gitbutler_credentials_unavailable_before_remote_update",
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
            "refs/heads/codex/v31-runtime-preflight",
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
            "v31_conservative_claude_ceiling_added_usd",
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

    def test_v31_is_nonresumable_and_v32_is_unset(self) -> None:
        self.assertIs(self.superseded["resumption_permitted"], False)
        self.assertIs(self.superseded["v31_cohort_reuse_permitted"], False)
        self.assertIs(
            self.superseded["v31_key_or_namespace_reuse_permitted"], False
        )
        self.assertEqual(
            self.superseded["replacement_panel_id"],
            "development-matched-50x6-v32",
        )
        self.assertEqual(
            self.superseded["replacement_values_status"],
            "not_yet_created_or_published",
        )
        self.assertIs(
            self.superseded["v32_acknowledgement_receipt_recorded"], False
        )
        self.assertIs(
            self.superseded["v32_commit_or_hash_values_recorded"], False
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
        closeout_metadata = subprocess.run(
            [
                "git",
                "show",
                "-s",
                "--format=%H%n%P%n%T",
                self.CLOSEOUT_COMMIT,
            ],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.splitlines()
        self.assertEqual(
            closeout_metadata,
            [self.CLOSEOUT_COMMIT, self.CONTROL_COMMIT, self.CLOSEOUT_TREE],
        )

        latest_supersession_commit = subprocess.run(
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
        self.assertEqual(latest_supersession_commit, self.CLOSEOUT_COMMIT)

        changed_paths = subprocess.run(
            [
                "git",
                "diff-tree",
                "--no-commit-id",
                "--name-only",
                "-r",
                self.CLOSEOUT_COMMIT,
            ],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.splitlines()
        self.assertEqual(
            sorted(changed_paths),
            sorted((self.SUPERSESSION_PATH, "tests/test_v31_supersession.py")),
        )

        runtime_path = "results/development-matched-50x6-v31.runtime.json"
        tree_paths = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", self.CLOSEOUT_COMMIT],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.splitlines()
        self.assertNotIn(runtime_path, tree_paths)

        closeout_ancestry = subprocess.run(
            ["git", "rev-list", self.CLOSEOUT_COMMIT],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.splitlines()
        self.assertNotIn(self.LOCAL_RUNTIME_COMMIT, closeout_ancestry)


if __name__ == "__main__":
    unittest.main()
