from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
from pathlib import Path
import subprocess
import unittest


class V15SupersessionTests(unittest.TestCase):
    PREREQUISITE_COMMIT = "a6861369026520d926b9357e8f7a5a29d5a00c32"
    PREREQUISITE_TREE = "d44c1d1ffbc92a0d0a24859830bbb730605fe792"
    PUBLIC_FILE_HASHES = {
        "docs/V15_RUNBOOK.md": (
            "sha256:56854960ee0337bc7d1b2b987d5bd5b2c15fad2f5ceea1a04911795fdcdab0cd"
        ),
        "src/epiagentbench/development_matched_panel.py": (
            "sha256:3a58ef2665d6f2a7bf08ac4bdac6a028fbe995f42abb9a626ad7cc325f8741ba"
        ),
        "examples/run_development_matched_panel.py": (
            "sha256:832ee271b4e19e1efa6eeb46fab0271962aff2621c9c18c16c627d2b78aa3411"
        ),
        "pyproject.toml": (
            "sha256:a5f691b5e92e285dff9429773133c619425cdfa73f741414a05d3b96fb227014"
        ),
    }

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.superseded_path = (
            cls.root
            / "results/development-matched-50x6-v15.superseded.json"
        )
        cls.superseded = json.loads(cls.superseded_path.read_bytes())

    @staticmethod
    def _keys(payload: object) -> set[str]:
        observed: set[str] = set()
        if isinstance(payload, Mapping):
            for key, value in payload.items():
                observed.add(str(key))
                observed.update(V15SupersessionTests._keys(value))
        elif isinstance(payload, Sequence) and not isinstance(
            payload, (str, bytes, bytearray)
        ):
            for value in payload:
                observed.update(V15SupersessionTests._keys(value))
        return observed

    def _published_bytes(self, relative: str) -> bytes:
        return subprocess.run(
            ["git", "show", f"{self.PREREQUISITE_COMMIT}:{relative}"],
            cwd=self.root,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout

    def test_supersession_has_a_closed_public_schema(self) -> None:
        self.assertEqual(
            set(self.superseded),
            {
                "authentication_started",
                "cohort_frozen",
                "cohort_preparation_claim_created",
                "cohort_retired",
                "cursor_keychain_created",
                "development_only",
                "empty_credential_namespaces_created",
                "failure_exception_class",
                "failure_reason_code",
                "failure_stage",
                "model_bearing_provider_call_exposure",
                "model_bearing_provider_calls_conservatively_chargeable",
                "original_panel_id",
                "preflight_profiles_attempted",
                "preparation_runtime_preflight_status",
                "private_authentication_key_created",
                "private_panel_state_created",
                "production_assignments_started",
                "provider_or_authentication_helper_processes_started",
                "public_authentication_receipt_created",
                "public_manifest_created",
                "public_preflight_receipt_created",
                "public_results_artifact_created",
                "published_prepare_entrypoint_sha256",
                "published_prerequisite_commit",
                "published_prerequisite_tree",
                "published_pyproject_sha256",
                "published_runbook_sha256",
                "published_source_sha256",
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
                "supervisor_runtime_created",
                "traces_released",
                "v15_cohort_reuse_permitted",
                "v15_key_or_namespace_reuse_permitted",
            },
        )
        self.assertEqual(
            self.superseded["schema_version"],
            "epiagentbench.panel_supersession.v7",
        )
        self.assertRegex(
            self.superseded["superseded_at_utc"],
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$",
        )

    def test_supersession_binds_the_exact_published_v15_source(self) -> None:
        self.assertEqual(
            self.superseded["published_prerequisite_commit"],
            self.PREREQUISITE_COMMIT,
        )
        tree = subprocess.run(
            ["git", "show", "-s", "--format=%T", self.PREREQUISITE_COMMIT],
            cwd=self.root,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout.strip()
        self.assertEqual(tree, self.PREREQUISITE_TREE)
        self.assertEqual(
            self.superseded["published_prerequisite_tree"],
            self.PREREQUISITE_TREE,
        )
        artifact_fields = {
            "docs/V15_RUNBOOK.md": "published_runbook_sha256",
            "src/epiagentbench/development_matched_panel.py": (
                "published_source_sha256"
            ),
            "examples/run_development_matched_panel.py": (
                "published_prepare_entrypoint_sha256"
            ),
            "pyproject.toml": "published_pyproject_sha256",
        }
        for relative, field in artifact_fields.items():
            digest = "sha256:" + hashlib.sha256(
                self._published_bytes(relative)
            ).hexdigest()
            self.assertEqual(digest, self.PUBLIC_FILE_HASHES[relative])
            self.assertEqual(self.superseded[field], digest)

    def test_published_v15_tree_contains_no_public_run_artifact(self) -> None:
        for relative in (
            "results/development-matched-50x6-v15.manifest.json",
            "results/development-matched-50x6-v15.authentication.json",
            "results/development-matched-50x6-v15.preflight.json",
            "results/development-matched-50x6-v15.json",
        ):
            with self.subTest(relative=relative):
                observed = subprocess.run(
                    [
                        "git",
                        "ls-tree",
                        "-r",
                        "--name-only",
                        self.PREREQUISITE_COMMIT,
                        "--",
                        relative,
                    ],
                    cwd=self.root,
                    check=True,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                ).stdout.splitlines()
                self.assertEqual(observed, [])

    def test_current_v15_runbook_is_terminal_and_points_to_v16(self) -> None:
        runbook = (self.root / "docs/V15_RUNBOOK.md").read_text(
            encoding="utf-8"
        )
        self.assertTrue(runbook.startswith("> [!CAUTION]\n"))
        self.assertIn(
            "**TERMINAL AND SUPERSEDED — DO NOT EXECUTE THIS RUNBOOK.**",
            runbook,
        )
        self.assertIn("do not create,", runbook)
        self.assertIn("resume, repair, or reuse any V15 path", runbook)
        self.assertIn(
            "../results/development-matched-50x6-v15.superseded.json",
            runbook,
        )
        self.assertIn("[V16 runbook](V16_RUNBOOK.md)", runbook)

    def test_failure_is_terminal_preclaim_and_zero_model(self) -> None:
        self.assertEqual(
            self.superseded["status"],
            "failed_zero_model_preclaim_preparation",
        )
        self.assertEqual(
            self.superseded["failure_stage"],
            "manifest_preparation_runtime_contract_import",
        )
        self.assertEqual(
            self.superseded["failure_reason_code"],
            "starsim_import_unavailable_in_selected_python",
        )
        self.assertEqual(
            self.superseded["failure_exception_class"],
            "ModuleNotFoundError",
        )
        self.assertIs(self.superseded["cohort_frozen"], True)
        self.assertIs(
            self.superseded["cohort_preparation_claim_created"], False
        )
        self.assertEqual(
            self.superseded["preparation_runtime_preflight_status"],
            "not_available_v15_inline_runtime_import_failed",
        )
        self.assertIs(self.superseded["private_panel_state_created"], False)
        self.assertIs(self.superseded["public_manifest_created"], False)
        self.assertIs(
            self.superseded["public_authentication_receipt_created"], False
        )
        self.assertIs(
            self.superseded["public_preflight_receipt_created"], False
        )
        self.assertIs(self.superseded["spend_acknowledgement_supplied"], False)
        self.assertIs(self.superseded["spend_authorization_recorded"], False)
        self.assertIs(self.superseded["authentication_started"], False)
        self.assertEqual(
            self.superseded["provider_or_authentication_helper_processes_started"],
            0,
        )
        self.assertEqual(
            self.superseded["model_bearing_provider_calls_conservatively_chargeable"],
            0,
        )
        self.assertEqual(
            self.superseded["model_bearing_provider_call_exposure"],
            {"claude": 0, "codex": 0, "cursor": 0, "total": 0},
        )
        self.assertEqual(self.superseded["preflight_profiles_attempted"], 0)
        self.assertEqual(self.superseded["production_assignments_started"], 0)

    def test_v15_cannot_resume_reuse_release_or_leak(self) -> None:
        self.assertIs(self.superseded["resumption_permitted"], False)
        self.assertIs(self.superseded["v15_cohort_reuse_permitted"], False)
        self.assertIs(
            self.superseded["v15_key_or_namespace_reuse_permitted"], False
        )
        self.assertIs(self.superseded["results_released"], False)
        self.assertIs(self.superseded["scores_released"], False)
        self.assertIs(self.superseded["traces_released"], False)
        self.assertIs(
            self.superseded["public_results_artifact_created"], False
        )
        forbidden_keys = {
            "access_token",
            "api_key",
            "credential_contents",
            "episode_id",
            "family",
            "oauth_state",
            "observation",
            "private_seed",
            "prompt",
            "provider_output",
            "raw_stderr",
            "raw_stdout",
            "refresh_token",
            "schedule",
            "schedule_nonce",
            "score",
            "stderr",
            "stdout",
            "trace",
            "trace_steps",
        }
        self.assertTrue(forbidden_keys.isdisjoint(self._keys(self.superseded)))
        encoded = json.dumps(self.superseded, sort_keys=True).lower()
        for canary in (
            "/home/",
            "/private/",
            "/users/",
            "auth.json",
            "credentials.json",
            "episode_0001",
            "institution_person_to_person",
            "panel-auth.key",
            "restaurant_point_source",
            "reporting_artifact",
            "schedule_nonce_hex",
        ):
            self.assertNotIn(canary, encoded)
        self.assertEqual(
            self.superseded["replacement_panel_id"],
            "development-matched-50x6-v16",
        )


if __name__ == "__main__":
    unittest.main()
