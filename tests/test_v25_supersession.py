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


class V25SupersessionTests(unittest.TestCase):
    SUPERSESSION_PATH = (
        "results/development-matched-50x6-v25.superseded.json"
    )
    CONTROL_COMMIT = "5ba7585cbc6568eeaaa5a2c9126b6879428e0478"
    CONTROL_PARENT = "84a7d474dc9528d1e53a8aee0c011478c63dda39"
    CONTROL_TREE = "c647813101b3923578e77f6308b73448cb089890"
    PINNED_FILES = {
        "docs/V25_RUNBOOK.md": (
            "published_runbook_sha256",
            "sha256:bd30e603488200a7aff7ecd103f248a434450169cf1168697feeb7def79f1d1e",
        ),
        "docs/PERSISTENT_RUNNER_PROTOCOL.md": (
            "published_protocol_sha256",
            "sha256:e204cdda1df52cdb0919a5450fff46fd6eca94c912ce8c0cfa78011d83f8c9c4",
        ),
        "src/epiagentbench/development_matched_panel.py": (
            "published_matched_panel_source_sha256",
            "sha256:a752ef8bbd1396ed7ca7a3e418099df77a40619ff75a5134aeaff9a9ce868b51",
        ),
        "src/epiagentbench/launchd_agent.py": (
            "published_launchd_source_sha256",
            "sha256:2cab9774556fd9aca31d877aa9897112d9a45ecf69384902b97bff9ecbc70ab8",
        ),
        "examples/run_development_matched_panel.py": (
            "published_entrypoint_sha256",
            "sha256:da4ac391330f72185544c00f7829e92c86167eb821f68f3fa1d85a72694c7a8a",
        ),
        "pyproject.toml": (
            "published_pyproject_sha256",
            "sha256:a5f691b5e92e285dff9429773133c619425cdfa73f741414a05d3b96fb227014",
        ),
    }
    V25_PUBLIC_OUTPUTS = (
        "results/development-matched-50x6-v25.runtime.json",
        "results/development-matched-50x6-v25.manifest.json",
        "results/development-matched-50x6-v25.authentication.json",
        "results/development-matched-50x6-v25.preflight.json",
        "results/development-matched-50x6-v25.json",
    )
    REPLACEMENT_REQUIREMENTS = [
        "fresh_panel_and_cohort_identity",
        "fresh_runtime_cache_and_runtime_receipt",
        "fresh_runtime_receipt_staging_namespace",
        "fresh_authentication_key",
        "fresh_private_schedule_and_cohort",
        "fresh_managed_glean_credential_namespace",
        "fresh_codex_credential_namespace",
        "fresh_cursor_keychain_service_after_authorization",
        "fresh_supervisor_namespaces",
        "checked_in_credential_free_preparation_environment",
        "explicit_required_provider_cli_search_directories",
        "pinned_cursor_cli_directory_in_source_owned_discovery",
        "sanitized_environment_contract_bound_into_runtime_receipt",
        "real_env_i_static_cli_discovery_regression",
        "fresh_v26_provider_free_runtime_preflight_twice",
        "exact_v26_manifest_bound_spend_authorization",
    ]
    EXPECTED_SUPERSESSION = {
        "ambient_provider_credential_environment_forwarded": False,
        "authentication_started": False,
        "cli_contract_completed": False,
        "cohort_freeze_claim_created": False,
        "cohort_frozen": False,
        "control_commit": CONTROL_COMMIT,
        "control_parent_commit": CONTROL_PARENT,
        "control_tree": CONTROL_TREE,
        "development_only": True,
        "empty_credential_namespaces_created": False,
        "episode_startup_smoke_started": False,
        "evidence_level": (
            "operator_observed_failure_plus_pinned_source_control_flow"
        ),
        "failed_provider_cli": "cursor-agent",
        "failed_public_command": "preflight-preparation-runtime",
        "failure_scope": (
            "static_cli_discovery_before_runtime_contract_smoke_or_receipt_"
            "publication"
        ),
        "failure_stage": "preparation_runtime_static_cli_discovery",
        "model_bearing_provider_call_exposure": {
            "claude": 0,
            "codex": 0,
            "cursor": 0,
            "total": 0,
        },
        "model_bearing_provider_calls_conservatively_chargeable": 0,
        "model_calls_started": 0,
        "original_panel_id": "development-matched-50x6-v25",
        "preflight_profiles_attempted": 0,
        "preparation_runtime_payload_created": False,
        "private_authentication_key_created": False,
        "private_panel_state_created": False,
        "production_assignments_started": 0,
        "provider_free_preflight_invocations": 1,
        "provider_free_publication_attempted": False,
        "provider_or_authentication_helper_processes_started": 0,
        "public_authentication_receipt_created": False,
        "public_manifest_created": False,
        "public_preflight_receipt_created": False,
        "public_results_artifact_created": False,
        "public_runtime_receipt_created": False,
        "published_entrypoint_sha256": (
            "sha256:da4ac391330f72185544c00f7829e92c86167eb821f68f3fa1d85a"
            "72694c7a8a"
        ),
        "published_launchd_source_sha256": (
            "sha256:2cab9774556fd9aca31d877aa9897112d9a45ecf69384902b97bff9"
            "ecbc70ab8"
        ),
        "published_matched_panel_source_sha256": (
            "sha256:a752ef8bbd1396ed7ca7a3e418099df77a40619ff75a5134aeaff9a"
            "9ce868b51"
        ),
        "published_protocol_sha256": (
            "sha256:e204cdda1df52cdb0919a5450fff46fd6eca94c912ce8c0cfa78011"
            "d83f8c9c4"
        ),
        "published_pyproject_sha256": (
            "sha256:a5f691b5e92e285dff9429773133c619425cdfa73f741414a05d3b9"
            "6fb227014"
        ),
        "published_runbook_sha256": (
            "sha256:bd30e603488200a7aff7ecd103f248a434450169cf1168697feeb7de"
            "f79f1d1e"
        ),
        "replacement_panel_id": "development-matched-50x6-v26",
        "replacement_requirements": REPLACEMENT_REQUIREMENTS,
        "required_cursor_cli_search_directory_present": False,
        "required_spend_acknowledgement_text_sha256": (
            "sha256:4b9093c6a0b1f9743d48c60cc4f02050bcbc56e37e9d7e292d06263"
            "4dac6fa83"
        ),
        "results_released": False,
        "resumption_permitted": False,
        "runtime_contract_started": False,
        "runtime_receipt_staging_file_created": False,
        "sanitized_environment_mode": "env_i",
        "schema_version": "epiagentbench.panel_supersession.v17",
        "scores_released": False,
        "source_contract_completed": True,
        "spend_acknowledgement_supplied": False,
        "spend_authorization_recorded": False,
        "starsim_smoke_started": False,
        "status": "failed_zero_model_provider_free_runtime_preflight",
        "superseded_at_utc": "2026-07-30T23:51:54Z",
        "supersession_reason_code": (
            "sanitized_path_omitted_required_cursor_cli_search_directory"
        ),
        "supervisor_runtime_created": False,
        "traces_released": False,
        "v25_conservative_claude_ceiling_added_usd": 0.0,
        "v25_identifier_or_namespace_reuse_permitted": False,
    }

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.superseded = _load_json_without_duplicate_keys(
            (cls.root / cls.SUPERSESSION_PATH).read_bytes()
        )
        if not isinstance(cls.superseded, dict):
            raise TypeError("V25 supersession artifact must be a JSON object")

    @staticmethod
    def _keys(payload: object) -> set[str]:
        observed: set[str] = set()
        if isinstance(payload, Mapping):
            for key, value in payload.items():
                observed.add(str(key))
                observed.update(V25SupersessionTests._keys(value))
        elif isinstance(payload, Sequence) and not isinstance(
            payload, (str, bytes, bytearray)
        ):
            for value in payload:
                observed.update(V25SupersessionTests._keys(value))
        return observed

    def _git_show_bytes(self, relative: str) -> bytes:
        return subprocess.run(
            ["git", "show", f"{self.CONTROL_COMMIT}:{relative}"],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout

    def test_exact_closed_public_schema_and_values(self) -> None:
        self.assertEqual(self.superseded, self.EXPECTED_SUPERSESSION)
        self.assertEqual(
            set(self.superseded["model_bearing_provider_call_exposure"]),
            {"claude", "codex", "cursor", "total"},
        )
        superseded_at = datetime.fromisoformat(
            self.superseded["superseded_at_utc"].replace("Z", "+00:00")
        )
        self.assertEqual(superseded_at.tzinfo, timezone.utc)
        self.assertEqual(
            superseded_at.isoformat().replace("+00:00", "Z"),
            self.superseded["superseded_at_utc"],
        )

    def test_duplicate_json_object_keys_are_rejected(self) -> None:
        with self.assertRaisesRegex(
            ValueError, r"duplicate JSON object key: status"
        ):
            _load_json_without_duplicate_keys(
                b'{"status":"first","nested":{"ok":true},'
                b'"status":"second"}'
            )

    def test_binds_exact_published_control_plane(self) -> None:
        self.assertEqual(self.superseded["control_commit"], self.CONTROL_COMMIT)
        self.assertEqual(
            self.superseded["control_parent_commit"], self.CONTROL_PARENT
        )
        self.assertEqual(self.superseded["control_tree"], self.CONTROL_TREE)
        for relative, (field, expected) in self.PINNED_FILES.items():
            observed = "sha256:" + hashlib.sha256(
                self._git_show_bytes(relative)
            ).hexdigest()
            self.assertEqual(observed, expected)
            self.assertEqual(self.superseded[field], expected)

    def test_failure_preceded_runtime_smoke_and_provider_boundaries(self) -> None:
        self.assertEqual(
            self.superseded["status"],
            "failed_zero_model_provider_free_runtime_preflight",
        )
        self.assertEqual(
            self.superseded["failure_stage"],
            "preparation_runtime_static_cli_discovery",
        )
        self.assertEqual(self.superseded["failed_provider_cli"], "cursor-agent")
        self.assertIs(self.superseded["source_contract_completed"], True)
        for field in (
            "cli_contract_completed",
            "runtime_contract_started",
            "starsim_smoke_started",
            "episode_startup_smoke_started",
            "preparation_runtime_payload_created",
            "public_runtime_receipt_created",
            "public_manifest_created",
            "private_authentication_key_created",
            "cohort_freeze_claim_created",
            "cohort_frozen",
            "private_panel_state_created",
            "authentication_started",
            "results_released",
            "scores_released",
            "traces_released",
            "resumption_permitted",
            "v25_identifier_or_namespace_reuse_permitted",
        ):
            self.assertFalse(self.superseded[field], field)
        for field in (
            "provider_or_authentication_helper_processes_started",
            "preflight_profiles_attempted",
            "production_assignments_started",
            "model_calls_started",
            "model_bearing_provider_calls_conservatively_chargeable",
            "v25_conservative_claude_ceiling_added_usd",
        ):
            self.assertEqual(self.superseded[field], 0, field)
        source = self._git_show_bytes(
            "src/epiagentbench/development_matched_panel.py"
        ).decode("utf-8")
        preflight = source[source.index("def preflight_preparation_runtime") :]
        self.assertLess(
            preflight.index("source = _source_contract(root)"),
            preflight.index("cli = _cli_contract()"),
        )
        self.assertLess(
            preflight.index("cli = _cli_contract()"),
            preflight.index("runtime = _runtime_contract()"),
        )

    def test_no_v25_run_artifact_exists(self) -> None:
        for relative in self.V25_PUBLIC_OUTPUTS:
            self.assertFalse((self.root / relative).exists(), relative)

    def test_public_receipt_has_no_sensitive_names_or_values(self) -> None:
        forbidden = {
            "api_key",
            "authentication_key_value",
            "credential_value",
            "device_code",
            "episode_id",
            "family_map",
            "oauth_state",
            "observation",
            "private_seed",
            "prompt",
            "provider_output",
            "raw_argv",
            "raw_environment",
            "raw_output",
            "schedule_nonce",
            "score_data",
            "trace_data",
        }
        observed = self._keys(self.superseded)
        for fragment in forbidden:
            self.assertFalse(
                any(fragment in key.lower() for key in observed),
                fragment,
            )
        serialized = json.dumps(
            self.superseded, sort_keys=True, separators=(",", ":")
        ).lower()
        for fragment in forbidden | {
            "/users/",
            "/home/",
            "file://",
            "matthew.zhao",
        }:
            self.assertNotIn(fragment, serialized)

    def test_archived_runbook_is_terminal_and_points_to_v26(self) -> None:
        runbook = (self.root / "docs" / "V25_RUNBOOK.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("TERMINAL ZERO-CALL FAILURE", runbook)
        self.assertIn("development-matched-50x6-v25.superseded.json", runbook)
        self.assertIn("V26_RUNBOOK.md", runbook)


if __name__ == "__main__":
    unittest.main()
