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


class V27SupersessionTests(unittest.TestCase):
    CONTROL_COMMIT = "7a702a208caa6e2db69497660ad831a8f2e17331"
    RUNTIME_COMMIT = "3516a2a5b50233d208378bc83d59df0aad24cb20"
    MANIFEST_COMMIT = "8cd10bc4a5f117d51c3c917bf101397d0025dd1c"
    AUTHENTICATION_COMMIT = "56e30b50c89804a90b628a5ac9cb7d465a2749ff"
    TERMINAL_RECEIPT_PATH = (
        "results/development-matched-50x6-v27.preflight.json"
    )
    SUPERSESSION_PATH = (
        "results/development-matched-50x6-v27.superseded.json"
    )
    COMMIT_BINDINGS = {
        "control": (
            CONTROL_COMMIT,
            "e8f0b606af9f821e7da090083b3e772ad832dc79",
            "ef2d0d296e9c2e21bfc748e77c0aa6ebe7a567d5",
        ),
        "runtime_receipt": (
            RUNTIME_COMMIT,
            CONTROL_COMMIT,
            "0a5d7c245f09bb212ccbb980107f8bd4979fffd3",
        ),
        "manifest": (
            MANIFEST_COMMIT,
            RUNTIME_COMMIT,
            "76f2992e95e1a8edd9d7e921c31c46e397131399",
        ),
        "authentication_receipt": (
            AUTHENTICATION_COMMIT,
            MANIFEST_COMMIT,
            "eba005c8a0d41b7bb4ccf986a1204469846e916c",
        ),
    }
    COMMITTED_PUBLIC_ARTIFACTS = {
        "results/development-matched-50x6-v27.runtime.json": (
            RUNTIME_COMMIT,
            "runtime_receipt_file_sha256",
            "sha256:9fba5cb10373b17c906e9b2605267bf3388947ca9f3fb060a12c4338008f46b6",
        ),
        "results/development-matched-50x6-v27.manifest.json": (
            MANIFEST_COMMIT,
            "manifest_file_sha256",
            "sha256:ee757920fb6b2be73a309a8a7baa507991f237c723e101c7aec2ad581df626c6",
        ),
        "results/development-matched-50x6-v27.authentication.json": (
            AUTHENTICATION_COMMIT,
            "authentication_receipt_file_sha256",
            "sha256:dffa1daaaa8bec20f1ad58a6763483950d91b4f04bda70698befc9448ab28fef",
        ),
    }
    HISTORICAL_CONTROL_FILES = {
        "docs/V27_RUNBOOK.md": (
            "historical_v27_runbook_sha256",
            "sha256:29bbcf95d4165d37eb779652749d19530be4bbe04ffc38600433f69e0f542ba1",
        ),
        "docs/PERSISTENT_RUNNER_PROTOCOL.md": (
            "historical_persistent_runner_protocol_sha256",
            "sha256:9d1519fcd86c930a191c49a69662c910536dd3f9edcf0e8727ebb0edf52367d6",
        ),
        "src/epiagentbench/development_matched_panel.py": (
            "historical_matched_panel_source_sha256",
            "sha256:aa794c97c466623f6fabef07e68e937f9dcb93e8adc59e6dbe20349ac7a471a3",
        ),
        "src/epiagentbench/launchd_agent.py": (
            "historical_launchd_source_sha256",
            "sha256:88b28138b5665a1d727ce1365ff42b31411ec3ebcffb6a43b55c27094decf704",
        ),
        "src/epiagentbench/persistent_supervisor.py": (
            "historical_persistent_supervisor_source_sha256",
            "sha256:10d4dfedbbcad4aed3a7ec40d438eee708088604fb5f23c444edcbb6e18bac4c",
        ),
        "src/epiagentbench/provider_cli_environment.py": (
            "historical_provider_cli_environment_source_sha256",
            "sha256:e0b8adaa6a44ef6c763ace75fa0e17b2d3b7c9636c63cdac4d67b0058cb8281c",
        ),
        "examples/run_development_matched_panel.py": (
            "historical_entrypoint_sha256",
            "sha256:3a1db7a882d6865d67dc988e34a58e259c7c6f4b436dd1e5ccc526268714757c",
        ),
        "examples/run_persistent_panel_supervisor.py": (
            "historical_launchd_entrypoint_sha256",
            "sha256:4b55a63936bb914cbc692ab7840367a750a2161d5de9c7e9e639c8b9f6979270",
        ),
        "pyproject.toml": (
            "historical_pyproject_sha256",
            "sha256:a5f691b5e92e285dff9429773133c619425cdfa73f741414a05d3b96fb227014",
        ),
    }
    TERMINAL_RECEIPT_SHA256 = (
        "sha256:b21e544eb394cac3fafd39a9c27afdc4cd032e90df7c2f4664f8ea782c10f440"
    )
    EXPECTED_TERMINAL_RECEIPT_BYTES = b"""{
  \"development_only\": true,
  \"failure_reason\": \"terminal_abort\",
  \"failure_stage\": \"preflight_control_boundary\",
  \"incident_code\": \"unexpected_control_path_failure\",
  \"incident_phase\": \"contract_attestation\",
  \"model_invocations_conservatively_chargeable\": 0,
  \"panel_id\": \"development-matched-50x6-v27\",
  \"precommitment_sha256\": \"sha256:bb21ad5e93267da6dbe255d0e91aa18fe20aeb5ff18ab9cc3a5b2051e692fd17\",
  \"production_episodes_consumed\": 0,
  \"profiles_recorded\": 0,
  \"profiles_terminal\": 0,
  \"schema_version\": \"development_matched_panel_v27\",
  \"scores_reported\": false,
  \"status\": \"failed\",
  \"terminal_envelope_schema\": \"epiagentbench.preflight_incident_envelope.v1\",
  \"timed_out\": false,
  \"timeout_stages\": []
}
"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.supersession = cls._read(cls.SUPERSESSION_PATH)
        cls.runtime = cls._read(
            "results/development-matched-50x6-v27.runtime.json"
        )
        cls.manifest = cls._read(
            "results/development-matched-50x6-v27.manifest.json"
        )
        cls.authentication = cls._read(
            "results/development-matched-50x6-v27.authentication.json"
        )
        cls.terminal_receipt_raw = (
            cls.root / cls.TERMINAL_RECEIPT_PATH
        ).read_bytes()
        terminal_receipt = _load_json_without_duplicate_keys(
            cls.terminal_receipt_raw
        )
        if not isinstance(terminal_receipt, dict):
            raise TypeError("V27 terminal receipt must contain a JSON object")
        cls.terminal_receipt = terminal_receipt

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
                observed.update(V27SupersessionTests._keys(value))
        elif isinstance(payload, Sequence) and not isinstance(
            payload, (str, bytes, bytearray)
        ):
            for value in payload:
                observed.update(V27SupersessionTests._keys(value))
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

    def test_exact_v27_commit_chain_and_public_bytes_are_bound(self) -> None:
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

    def test_exact_historical_v27_control_bytes_are_bound(self) -> None:
        for relative, (field, expected) in (
            self.HISTORICAL_CONTROL_FILES.items()
        ):
            historical = self._git_show_bytes(self.CONTROL_COMMIT, relative)
            observed = "sha256:" + hashlib.sha256(historical).hexdigest()
            self.assertEqual(observed, expected)
            self.assertEqual(self.supersession[field], expected)

    def test_terminal_receipt_is_the_exact_immutable_failure_evidence(
        self,
    ) -> None:
        self.assertEqual(
            self.terminal_receipt_raw, self.EXPECTED_TERMINAL_RECEIPT_BYTES
        )
        observed = "sha256:" + hashlib.sha256(
            self.terminal_receipt_raw
        ).hexdigest()
        self.assertEqual(observed, self.TERMINAL_RECEIPT_SHA256)
        self.assertEqual(
            self.supersession["preflight_terminal_receipt_file_sha256"],
            self.TERMINAL_RECEIPT_SHA256,
        )
        receipt_bindings = {
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

    def test_original_receipt_was_uncommitted_and_publication_is_pending(
        self,
    ) -> None:
        originally_committed = subprocess.run(
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
        self.assertNotEqual(originally_committed.returncode, 0)
        self.assertIs(
            self.supersession[
                "preflight_terminal_receipt_originally_committed"
            ],
            False,
        )
        self.assertEqual(
            self.supersession["historical_publication_status"], "pending"
        )
        for field in (
            "historical_publication_commit",
            "historical_publication_parent_commit",
            "historical_publication_tree",
        ):
            self.assertIsNone(self.supersession[field], field)
        self.assertEqual(
            self.supersession["historical_publication_semantics"],
            "future_commit_records_later_historical_evidence_not_original_"
            "receipt_publication",
        )

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

    def test_zero_call_accounting_and_non_resumability_are_explicit(
        self,
    ) -> None:
        self.assertEqual(
            self.supersession["schema_version"],
            "epiagentbench.panel_supersession.v19",
        )
        self.assertEqual(
            self.supersession["status"],
            "failed_zero_model_preflight_contract_attestation_boundary",
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
            "resumption_permitted",
            "scores_released",
            "scores_reported",
            "traces_released",
            "v27_cohort_reuse_permitted",
            "v27_identifier_or_namespace_reuse_permitted",
        ):
            self.assertIs(self.supersession[field], False, field)
        self.assertIs(
            self.supersession["exact_failed_operation_recoverable"], False
        )
        self.assertEqual(
            self.supersession["audited_root_cause_scope"],
            "contract_validation_or_following_checkpoint_persistence",
        )

    def test_v28_requirements_close_the_v27_observability_gap(self) -> None:
        requirements = set(self.supersession["replacement_requirements"])
        for required in (
            "fresh_panel_and_cohort_identity",
            "finite_content_free_contract_attestation_failure_codes",
            "last_completed_phase_and_failed_operation_recorded_separately",
            "contract_validation_and_checkpoint_persistence_failures_distinguished",
            "provider_free_prestart_attestation_in_worker_execution_context",
            "fault_injection_for_each_contract_attestation_group",
            "real_supervisor_worker_contract_boundary_integration_test",
            "no_exception_text_private_paths_or_hidden_identifiers_in_public_receipts",
            "exact_v28_manifest_bound_spend_authorization",
        ):
            self.assertIn(required, requirements)
        self.assertEqual(
            self.supersession["replacement_panel_id"],
            "development-matched-50x6-v28",
        )

    def test_supersession_is_utc_and_contains_no_sensitive_payload(
        self,
    ) -> None:
        superseded_at = datetime.fromisoformat(
            str(self.supersession["superseded_at_utc"]).replace(
                "Z", "+00:00"
            )
        )
        prepared_at = datetime.fromisoformat(
            str(self.manifest["prepared_at_utc"]).replace("Z", "+00:00")
        )
        self.assertEqual(superseded_at.tzinfo, timezone.utc)
        self.assertGreater(superseded_at, prepared_at)
        serialized = json.dumps(
            self.supersession, sort_keys=True, separators=(",", ":")
        ).lower()
        for forbidden in (
            "/users/",
            "access_token",
            "api_key",
            "device_code",
            "episode_id",
            "episode_ref",
            "oauth_state",
            "private_seed",
            '"prompt"',
            '"observation"',
            '"trace"',
        ):
            self.assertNotIn(forbidden, serialized)
        self.assertNotIn("exception_text", self._keys(self.supersession))


if __name__ == "__main__":
    unittest.main()
