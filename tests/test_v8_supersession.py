from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest

from epiagentbench.development_matched_panel import _component_hash


class V8SupersessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.preflight_path = (
            cls.root / "results" / "development-matched-50x6-v8.preflight.json"
        )
        cls.stopped_path = (
            cls.root / "results" / "development-matched-50x6-v8.json"
        )
        cls.superseded_path = (
            cls.root / "results" / "development-matched-50x6-v8.superseded.json"
        )
        cls.preflight = json.loads(cls.preflight_path.read_text(encoding="utf-8"))
        cls.stopped = json.loads(cls.stopped_path.read_text(encoding="utf-8"))
        cls.superseded = json.loads(
            cls.superseded_path.read_text(encoding="utf-8")
        )

    @staticmethod
    def _file_hash(path: Path) -> str:
        return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()

    def test_stopped_watermark_releases_no_partial_result(self) -> None:
        self.assertEqual(self.stopped["status"], "stopped_transport_void")
        self.assertEqual(self.stopped["planned_assignments"], 300)
        self.assertEqual(self.stopped["terminal_assignments"], 3)
        self.assertEqual(self.stopped["completed_assignments"], 2)
        self.assertEqual(self.stopped["transport_voids"], 1)
        self.assertEqual(self.stopped["results"], [])
        self.assertEqual(self.stopped["summary"], {"primary_estimand": "pending"})

    def test_supersession_binds_public_receipts_and_exact_exposure(self) -> None:
        self.assertEqual(
            self.superseded["passed_preflight_file_sha256"],
            self._file_hash(self.preflight_path),
        )
        self.assertEqual(
            self.superseded["passed_preflight_canonical_sha256"],
            _component_hash(self.preflight),
        )
        self.assertEqual(
            self.superseded["stopped_results_file_sha256"],
            self._file_hash(self.stopped_path),
        )
        self.assertEqual(
            self.superseded["stopped_results_canonical_sha256"],
            _component_hash(self.stopped),
        )
        self.assertEqual(self.superseded["production_assignments_started"], 3)
        self.assertEqual(self.superseded["completed_production_assignments"], 2)
        self.assertEqual(self.superseded["transport_voids"], 1)
        self.assertEqual(
            self.superseded["provider_call_exposure"],
            {"claude": 3, "codex": 3, "cursor": 3, "total": 9},
        )

    def test_supersession_forbids_reuse_and_release(self) -> None:
        self.assertEqual(
            self.superseded["status"],
            "abandoned_after_terminal_production_incident",
        )
        self.assertIs(self.superseded["terminal_execution_incident"], True)
        self.assertIs(
            self.superseded["terminal_codex_authentication_incident"], True
        )
        self.assertIs(self.superseded["cohort_retired"], False)
        self.assertIs(self.superseded["results_released"], False)
        self.assertIs(self.superseded["traces_released"], False)
        requirements = set(self.superseded["replacement_requirements"])
        self.assertTrue(
            {
                "fresh_cohort",
                "fresh_private_schedule",
                "fresh_codex_credential_namespace",
                "os_owned_persistent_supervisor",
                "crash_boundary_at_most_once_tests",
                "full_fake_300_assignment_soak",
                "fresh_spend_authorization",
            }.issubset(requirements)
        )

    def test_public_incident_artifacts_contain_no_sensitive_surfaces(self) -> None:
        encoded = json.dumps(
            {"stopped": self.stopped, "superseded": self.superseded},
            sort_keys=True,
        ).lower()
        for forbidden in (
            "/users/",
            "episode_ref",
            "pack_commitment",
            "family_label",
            "raw_result",
            "public_result",
            "trace_steps",
            "cursor_api_key",
            "access_token",
            "refresh_token",
            "oauth_state",
        ):
            self.assertNotIn(forbidden, encoded)


if __name__ == "__main__":
    unittest.main()
