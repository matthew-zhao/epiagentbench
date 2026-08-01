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


class V28SupersessionTests(unittest.TestCase):
    CONTROL_COMMIT = "142803ff442fed8d9ef20405bbfc6f61b54c71bf"
    RUNTIME_COMMIT = "309968bfea4da1996f7f330eb67a79c106376cb1"
    MANIFEST_COMMIT = "fc405c50780bf8aee501655e343d72d2eda1981f"
    AUTHENTICATION_COMMIT = (
        "7f9b61db6ede31a25b07595050c19a05b5032023"
    )
    TERMINAL_RECEIPT_PATH = (
        "results/development-matched-50x6-v28.preflight.json"
    )
    SUPERSESSION_PATH = (
        "results/development-matched-50x6-v28.superseded.json"
    )
    COMMIT_BINDINGS = {
        "control": (
            CONTROL_COMMIT,
            "56e30b50c89804a90b628a5ac9cb7d465a2749ff",
            "5525cf1bde1ad7e73d84e0d2d8dde91ae31f21f3",
        ),
        "runtime_receipt": (
            RUNTIME_COMMIT,
            CONTROL_COMMIT,
            "b040b455d555a73705d2530932274fa175e52e4c",
        ),
        "manifest": (
            MANIFEST_COMMIT,
            RUNTIME_COMMIT,
            "a2e86ec26ba5d736bd6238712f5a4c4828c57716",
        ),
        "authentication_receipt": (
            AUTHENTICATION_COMMIT,
            MANIFEST_COMMIT,
            "dfd41174168a8c52b516e7deb7036bbd145c556a",
        ),
    }
    COMMITTED_PUBLIC_ARTIFACTS = {
        "results/development-matched-50x6-v28.runtime.json": (
            RUNTIME_COMMIT,
            "runtime_receipt_file_sha256",
            "sha256:9ed3d3f8b4ddb2fd01986c64cdd68c1087c4337e2ae64d9e19ebade7b5e6de30",
        ),
        "results/development-matched-50x6-v28.manifest.json": (
            MANIFEST_COMMIT,
            "manifest_file_sha256",
            "sha256:9dafb7051dc0b882352d47241cc29d74cf181ac5c952483d55ba5e6a55afe274",
        ),
        "results/development-matched-50x6-v28.authentication.json": (
            AUTHENTICATION_COMMIT,
            "authentication_receipt_file_sha256",
            "sha256:edea4807b03496155506bb3cd56992e1064099436c5963e34276f435ca262873",
        ),
    }
    TERMINAL_RECEIPT_SHA256 = (
        "sha256:595e385fa9e1c60befb0633443bfc5862d10d9d56a804d8ec009c138f349014e"
    )
    EXPECTED_TERMINAL_RECEIPT_BYTES = b"""{
  \"attempted_operation\": \"preparation_runtime\",
  \"completed_operation\": \"authentication_binding\",
  \"contract_failure_code\": \"preparation_runtime_failed\",
  \"development_only\": true,
  \"failure_reason\": \"terminal_abort\",
  \"failure_stage\": \"preflight_control_boundary\",
  \"incident_code\": \"contract_attestation_failed\",
  \"incident_phase\": \"contract_attestation\",
  \"model_invocations_conservatively_chargeable\": 0,
  \"panel_id\": \"development-matched-50x6-v28\",
  \"precommitment_sha256\": \"sha256:ccf288ad44097217707134fdc22be73bf7cb4a0c865d5171d1b5238a267f83ac\",
  \"production_episodes_consumed\": 0,
  \"profiles_recorded\": 0,
  \"profiles_terminal\": 0,
  \"schema_version\": \"development_matched_panel_v28\",
  \"scores_reported\": false,
  \"status\": \"failed\",
  \"terminal_envelope_schema\": \"epiagentbench.preflight_incident_envelope.v2\",
  \"timed_out\": false,
  \"timeout_stages\": []
}
"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.supersession = cls._read(cls.SUPERSESSION_PATH)
        cls.runtime = cls._read(
            "results/development-matched-50x6-v28.runtime.json"
        )
        cls.manifest = cls._read(
            "results/development-matched-50x6-v28.manifest.json"
        )
        cls.authentication = cls._read(
            "results/development-matched-50x6-v28.authentication.json"
        )
        terminal = _load_json_without_duplicate_keys(
            cls.EXPECTED_TERMINAL_RECEIPT_BYTES
        )
        if not isinstance(terminal, dict):
            raise TypeError("V28 terminal receipt fixture must be an object")
        cls.terminal_receipt = terminal

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
                observed.update(V28SupersessionTests._keys(value))
        elif isinstance(payload, Sequence) and not isinstance(
            payload, (str, bytes, bytearray)
        ):
            for value in payload:
                observed.update(V28SupersessionTests._keys(value))
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

    def test_exact_v28_commit_chain_and_public_bytes_are_bound(self) -> None:
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

    def test_public_receipts_are_internally_bound(self) -> None:
        self.assertEqual(self.runtime["status"], "passed")
        self.assertEqual(
            self.runtime["runtime_identity_sha256"],
            self.supersession["runtime_receipt_identity_sha256"],
        )
        self.assertEqual(self.manifest["status"], "precommitted")
        self.assertEqual(
            self.manifest["precommitment_sha256"],
            self.supersession["manifest_precommitment_sha256"],
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

    def test_terminal_receipt_fixture_binds_the_uncommitted_evidence(
        self,
    ) -> None:
        observed = "sha256:" + hashlib.sha256(
            self.EXPECTED_TERMINAL_RECEIPT_BYTES
        ).hexdigest()
        self.assertEqual(observed, self.TERMINAL_RECEIPT_SHA256)
        self.assertEqual(
            self.supersession["preflight_terminal_receipt_file_sha256"],
            self.TERMINAL_RECEIPT_SHA256,
        )
        receipt_bindings = {
            "attempted_operation": "attempted_operation",
            "completed_operation": "completed_operation",
            "contract_failure_code": "contract_failure_code",
            "failure_reason": "failure_reason",
            "failure_stage": "failure_stage",
            "incident_code": "incident_code",
            "incident_phase": "incident_phase",
            "model_invocations_conservatively_chargeable": (
                "model_invocations_conservatively_chargeable"
            ),
            "production_episodes_consumed": "production_episodes_consumed",
            "profiles_recorded": "preflight_profiles_recorded",
            "profiles_terminal": "preflight_profiles_terminal",
            "scores_reported": "scores_reported",
            "terminal_envelope_schema": "terminal_envelope_schema",
            "timed_out": "timed_out",
            "timeout_stages": "timeout_stages",
        }
        for receipt_field, supersession_field in receipt_bindings.items():
            self.assertEqual(
                self.terminal_receipt[receipt_field],
                self.supersession[supersession_field],
            )
        self.assertEqual(
            self.terminal_receipt["precommitment_sha256"],
            self.supersession["manifest_precommitment_sha256"],
        )
        self.assertEqual(
            self.terminal_receipt["schema_version"],
            self.supersession["preflight_terminal_receipt_schema"],
        )
        self.assertEqual(
            self.terminal_receipt["status"],
            self.supersession["preflight_terminal_receipt_status"],
        )

        committed = subprocess.run(
            [
                "git",
                "cat-file",
                "-e",
                f"{self.AUTHENTICATION_COMMIT}:{self.TERMINAL_RECEIPT_PATH}",
            ],
            cwd=self.root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertNotEqual(committed.returncode, 0)
        self.assertFalse((self.root / self.TERMINAL_RECEIPT_PATH).exists())
        self.assertIs(
            self.supersession[
                "preflight_terminal_receipt_originally_committed"
            ],
            False,
        )

    def test_terminal_accounting_is_exactly_zero_and_trace_free(self) -> None:
        self.assertEqual(
            self.supersession["schema_version"],
            "epiagentbench.panel_supersession.v20",
        )
        self.assertEqual(
            self.supersession["status"],
            "failed_zero_model_preflight_preparation_runtime_"
            "contract_attestation",
        )
        self.assertEqual(
            self.supersession["model_bearing_provider_call_exposure"],
            {"claude": 0, "codex": 0, "cursor": 0, "total": 0},
        )
        for field in (
            "model_bearing_provider_calls_started",
            "model_invocations_conservatively_chargeable",
            "preflight_profiles_recorded",
            "preflight_profiles_terminal",
            "production_assignments_started",
            "production_episodes_consumed",
        ):
            self.assertEqual(self.supersession[field], 0, field)
        for field in (
            "public_results_artifact_created",
            "results_released",
            "scores_released",
            "scores_reported",
            "timed_out",
            "traces_released",
        ):
            self.assertIs(self.supersession[field], False, field)
        self.assertEqual(self.supersession["timeout_stages"], [])

        forbidden = {
            "credential",
            "exception_text",
            "hidden_episode_identifier",
            "oauth_state",
            "private_path",
            "prompt",
            "provider_output",
            "raw_provider_output",
            "trace",
        }
        self.assertTrue(
            forbidden.isdisjoint(self._keys(self.supersession))
        )
        self.assertIs(
            self.supersession["raw_provider_outputs_inspected"], False
        )
        self.assertIs(self.supersession["exception_text_released"], False)

    def test_audit_preserves_uncertainty_and_nonresumability(self) -> None:
        self.assertEqual(
            self.supersession["audited_root_cause_scope"],
            "preparation_runtime_contract_group",
        )
        self.assertIs(
            self.supersession["exact_failed_predicate_recoverable"], False
        )
        self.assertEqual(
            self.supersession["provider_free_audit_leading_hypothesis"],
            "transient_thirty_process_episode_startup_smoke_failure",
        )
        self.assertIs(
            self.supersession[
                "provider_free_audit_leading_hypothesis_proven"
            ],
            False,
        )
        self.assertIs(
            self.supersession[
                "provider_free_audit_public_artifact_byte_mismatch_found"
            ],
            False,
        )
        self.assertIs(
            self.supersession[
                "provider_free_audit_public_contract_mismatch_found"
            ],
            False,
        )
        self.assertIs(
            self.supersession[
                "provider_free_audit_private_artifacts_inspected"
            ],
            False,
        )
        self.assertIs(self.supersession["resumption_permitted"], False)
        self.assertIs(
            self.supersession["v28_cohort_reuse_permitted"], False
        )
        self.assertIs(
            self.supersession[
                "v28_identifier_or_namespace_reuse_permitted"
            ],
            False,
        )

    def test_v29_requirements_are_finite_but_values_remain_unset(self) -> None:
        self.assertEqual(
            self.supersession["replacement_panel_id"],
            "development-matched-50x6-v29",
        )
        requirements = set(self.supersession["replacement_requirements"])
        self.assertTrue(
            {
                "finite_preparation_runtime_static_contract_failure_code",
                "finite_preparation_runtime_cache_identity_failure_code",
                "finite_preparation_runtime_starsim_smoke_failure_code",
                "finite_preparation_runtime_episode_startup_smoke_failure_code",
                "finite_preparation_runtime_private_cache_binding_failure_code",
                "fresh_panel_and_cohort_identity",
                "fresh_runtime_cache_and_runtime_receipt",
                (
                    "cursor_keychain_value_retrieved_only_after_atomic_"
                    "preflight_claim"
                ),
                "passed_preclaim_required_for_production",
            }.issubset(requirements)
        )
        self.assertEqual(
            self.supersession["replacement_values_status"],
            "not_yet_created_or_authorized",
        )
        self.assertIs(
            self.supersession["v29_acknowledgement_receipt_recorded"],
            False,
        )
        self.assertIs(
            self.supersession["v29_commit_or_hash_values_recorded"], False
        )
        self.assertTrue(
            {
                "replacement_manifest_commit",
                "replacement_runtime_commit",
                "required_v29_acknowledgement_text_sha256",
                "v29_manifest_precommitment_sha256",
            }.isdisjoint(self.supersession)
        )

    def test_supersession_timestamp_is_utc_and_not_future(self) -> None:
        value = self.supersession["superseded_at_utc"]
        self.assertIsInstance(value, str)
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        self.assertEqual(parsed.tzinfo, timezone.utc)
        self.assertLessEqual(parsed, datetime.now(timezone.utc))


if __name__ == "__main__":
    unittest.main()
