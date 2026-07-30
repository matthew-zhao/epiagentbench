from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import unittest


class V24SupersessionTests(unittest.TestCase):
    SUPERSESSION_PATH = (
        "results/development-matched-50x6-v24.superseded.json"
    )
    CONTROL_COMMIT = "84a7d474dc9528d1e53a8aee0c011478c63dda39"
    CONTROL_PARENT = "2fb662695e5fed2f859494d785b3c619e5a52cd9"
    CONTROL_TREE = "75857121e98f717f378f42580d38a6caf74599fe"
    PINNED_FILES = {
        "docs/V24_RUNBOOK.md": (
            "published_runbook_sha256",
            "sha256:1bba0523eebbdc322ab5173d8c72139d9ce31990c582324e6e486e5881ed17fd",
        ),
        "src/epiagentbench/development_matched_panel.py": (
            "published_matched_panel_source_sha256",
            "sha256:8222879a805c2604f0414417d460c6f532366d081073d1a3a8b2ec2749fbfc0c",
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
    V24_PUBLIC_OUTPUTS = (
        "results/development-matched-50x6-v24.runtime.json",
        "results/development-matched-50x6-v24.manifest.json",
        "results/development-matched-50x6-v24.authentication.json",
        "results/development-matched-50x6-v24.preflight.json",
        "results/development-matched-50x6-v24.json",
    )

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.superseded = json.loads(
            (cls.root / cls.SUPERSESSION_PATH).read_bytes()
        )

    @staticmethod
    def _keys(payload: object) -> set[str]:
        observed: set[str] = set()
        if isinstance(payload, Mapping):
            for key, value in payload.items():
                observed.add(str(key))
                observed.update(V24SupersessionTests._keys(value))
        elif isinstance(payload, Sequence) and not isinstance(
            payload, (str, bytes, bytearray)
        ):
            for value in payload:
                observed.update(V24SupersessionTests._keys(value))
        return observed

    def _git_show_bytes(self, relative: str) -> bytes:
        return subprocess.run(
            ["git", "show", f"{self.CONTROL_COMMIT}:{relative}"],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout

    def test_closed_public_schema(self) -> None:
        self.assertEqual(
            set(self.superseded),
            {
                "authentication_started",
                "cohort_freeze_claim_created",
                "cohort_frozen",
                "control_commit",
                "control_parent_commit",
                "control_tree",
                "development_only",
                "empty_credential_namespaces_created",
                "model_bearing_provider_call_exposure",
                "model_bearing_provider_calls_conservatively_chargeable",
                "model_calls_started",
                "original_panel_id",
                "preflight_profiles_attempted",
                "private_authentication_key_created",
                "private_panel_state_created",
                "production_assignments_started",
                "provider_or_authentication_helper_processes_started",
                "public_authentication_receipt_created",
                "public_manifest_created",
                "public_preflight_receipt_created",
                "public_results_artifact_created",
                "public_runtime_receipt_created",
                "published_entrypoint_sha256",
                "published_launchd_source_sha256",
                "published_matched_panel_source_sha256",
                "published_pyproject_sha256",
                "published_runbook_sha256",
                "replacement_panel_id",
                "replacement_requirements",
                "results_released",
                "resumption_permitted",
                "schema_version",
                "scores_released",
                "spend_acknowledgement_supplied",
                "spend_authorization_recorded",
                "status",
                "superseded_at_utc",
                "supersession_reason_code",
                "supervisor_runtime_created",
                "traces_released",
                "v24_conservative_claude_ceiling_added_usd",
                "v24_identifier_or_namespace_reuse_permitted",
            },
        )
        self.assertEqual(
            self.superseded["schema_version"],
            "epiagentbench.panel_supersession.v16",
        )
        self.assertIs(self.superseded["development_only"], True)
        self.assertEqual(
            self.superseded["replacement_requirements"],
            [
                "fresh_panel_and_cohort_identity",
                "fresh_runtime_cache_and_runtime_receipt",
                "fresh_authentication_key",
                "fresh_private_schedule_and_cohort",
                "fresh_managed_glean_credential_namespace",
                "fresh_codex_credential_namespace",
                "fresh_cursor_keychain_service_after_authorization",
                "exact_v25_manifest_bound_spend_authorization",
            ],
        )
        superseded_at = datetime.fromisoformat(
            self.superseded["superseded_at_utc"].replace("Z", "+00:00")
        )
        self.assertEqual(superseded_at.tzinfo, timezone.utc)
        self.assertEqual(
            superseded_at.isoformat().replace("+00:00", "Z"),
            self.superseded["superseded_at_utc"],
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

    def test_v24_stopped_before_every_runtime_boundary(self) -> None:
        self.assertEqual(
            self.superseded["status"],
            "abandoned_zero_model_control_plane_precommitment",
        )
        self.assertEqual(
            self.superseded["supersession_reason_code"],
            "operator_selected_fresh_v25_before_preparation",
        )
        for field in (
            "authentication_started",
            "cohort_freeze_claim_created",
            "cohort_frozen",
            "empty_credential_namespaces_created",
            "private_authentication_key_created",
            "private_panel_state_created",
            "public_authentication_receipt_created",
            "public_manifest_created",
            "public_preflight_receipt_created",
            "public_results_artifact_created",
            "public_runtime_receipt_created",
            "results_released",
            "scores_released",
            "spend_acknowledgement_supplied",
            "spend_authorization_recorded",
            "supervisor_runtime_created",
            "traces_released",
            "resumption_permitted",
            "v24_identifier_or_namespace_reuse_permitted",
        ):
            self.assertFalse(self.superseded[field], field)
        for field in (
            "model_bearing_provider_calls_conservatively_chargeable",
            "model_calls_started",
            "preflight_profiles_attempted",
            "production_assignments_started",
            "provider_or_authentication_helper_processes_started",
            "v24_conservative_claude_ceiling_added_usd",
        ):
            self.assertEqual(self.superseded[field], 0, field)
        self.assertEqual(
            self.superseded["model_bearing_provider_call_exposure"],
            {"claude": 0, "codex": 0, "cursor": 0, "total": 0},
        )
        self.assertEqual(
            self.superseded["original_panel_id"],
            "development-matched-50x6-v24",
        )
        self.assertEqual(
            self.superseded["replacement_panel_id"],
            "development-matched-50x6-v25",
        )

    def test_no_v24_run_artifact_exists(self) -> None:
        for relative in self.V24_PUBLIC_OUTPUTS:
            self.assertFalse((self.root / relative).exists(), relative)
        self.assertTrue(
            (self.root / self.SUPERSESSION_PATH).is_file()
        )

    def test_public_receipt_has_no_sensitive_names_or_values(self) -> None:
        forbidden = {
            "api_key",
            "credential_value",
            "device_code",
            "episode_id",
            "family_map",
            "oauth_state",
            "observation",
            "private_seed",
            "prompt",
            "provider_output",
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

    def test_archived_runbook_is_terminal_and_points_to_v25(self) -> None:
        runbook = (self.root / "docs" / "V24_RUNBOOK.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("SUPERSEDED BEFORE PREPARATION", runbook)
        self.assertIn("development-matched-50x6-v24.superseded.json", runbook)
        self.assertIn("V25_RUNBOOK.md", runbook)


if __name__ == "__main__":
    unittest.main()
