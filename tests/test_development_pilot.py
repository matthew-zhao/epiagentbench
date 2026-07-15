from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from epiagentbench.development_pilot import (
    DIMENSION_MAXIMA,
    PANEL,
    _derive_secret,
    _load_json,
    _reconstruct_public_results,
    _raise_on_harness_startup_failure,
    _sanitize_result,
    _validate_commitments,
    aggregate_results,
    prepare_panel,
)
from epiagentbench.pilot import PilotRunResult


class DevelopmentPilotTests(unittest.TestCase):
    def result(self, system: str = "codex") -> PilotRunResult:
        return PilotRunResult(
            system=system,
            requested_model="gpt-5.6-sol",
            observed_models=(),
            cli_version="test-cli",
            development_only=True,
            hermetic=False,
            returncode=0,
            elapsed_seconds=12.5,
            submission={"private": "not published"},
            scorecard={
                "valid": True,
                "total": 80.0,
                "dimensions": {name: maximum * 0.8 for name, maximum in DIMENSION_MAXIMA.items()},
                "metrics": {
                    "integrity_pass": True,
                    "case_f1": 0.8,
                    "raw_action_utility": 99,
                },
                "violations": [],
            },
            audit_events=(),
            stdout_bytes=100,
            stderr_bytes=0,
            diagnostic="private diagnostic",
        )

    def test_prepare_commits_secrets_without_publishing_them(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "schemas").mkdir()
            (root / "schemas" / "submission.schema.json").write_text("{}")
            (root / "src" / "epiagentbench").mkdir(parents=True)
            (root / "src" / "epiagentbench" / "pilot.py").write_text("pilot")
            (root / "src" / "epiagentbench" / "development_pilot.py").write_text(
                "development pilot"
            )
            private_path = root / "run_artifacts" / "private.json"
            public_path = root / "results" / "public.json"
            def git_output(_: Path, *arguments: str) -> str:
                return (
                    ""
                    if arguments
                    == ("status", "--porcelain", "--untracked-files=all")
                    else "a" * 40
                )

            with patch(
                "epiagentbench.development_pilot._git_output",
                side_effect=git_output,
            ), patch(
                "epiagentbench.development_pilot.secrets.token_bytes",
                return_value=b"k" * 32,
            ):
                public = prepare_panel(
                    root=root,
                    private_manifest_path=private_path,
                    public_manifest_path=public_path,
                )
            private_text = private_path.read_text()
            public_text = public_path.read_text()
            self.assertIn((b"k" * 32).hex(), private_text)
            self.assertNotIn((b"k" * 32).hex(), public_text)
            self.assertEqual(os.stat(private_path).st_mode & 0o777, 0o600)
            self.assertEqual(public["planned_assignments"], 15)
            self.assertEqual(len(public["episodes"]), 5)

    def test_sanitized_result_omits_submission_diagnostic_and_oracle_metrics(self) -> None:
        sanitized = _sanitize_result(
            episode=PANEL[0],
            result=self.result(),
            started_at="start",
            finished_at="finish",
        )
        encoded = json.dumps(sanitized)
        self.assertNotIn("submission", encoded)
        self.assertNotIn("diagnostic", encoded)
        self.assertNotIn("raw_action_utility", encoded)
        self.assertEqual(sanitized["model_attribution"], "requested_only_unverified")

    def test_aggregation_keeps_invalid_zero_in_fixed_denominator(self) -> None:
        first = _sanitize_result(
            episode=PANEL[0],
            result=self.result(),
            started_at="start",
            finished_at="finish",
        )
        failed = dict(first)
        failed.update({"episode_ref": "episode_02", "valid": False, "total": 0.0})
        failed["dimensions"] = {name: 0.0 for name in DIMENSION_MAXIMA}
        summary = aggregate_results([first, failed])
        self.assertEqual(summary["codex"]["completed"], 2)
        self.assertEqual(summary["codex"]["valid"], 1)
        self.assertEqual(summary["codex"]["mean_total"], 16.0)

    def test_episode_secret_derivation_is_deterministic_and_separated(self) -> None:
        first = _derive_secret(b"m" * 32, "family-a", 1)
        second = _derive_secret(b"m" * 32, "family-b", 1)
        self.assertEqual(first, _derive_secret(b"m" * 32, "family-a", 1))
        self.assertNotEqual(first, second)

    def test_tampered_public_precommit_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "schemas").mkdir()
            (root / "schemas" / "submission.schema.json").write_text("{}")
            (root / "src" / "epiagentbench").mkdir(parents=True)
            (root / "src" / "epiagentbench" / "pilot.py").write_text("pilot")
            (root / "src" / "epiagentbench" / "development_pilot.py").write_text(
                "development pilot"
            )
            private_path = root / "run_artifacts" / "private.json"
            public_path = root / "results" / "public.json"

            def git_output(_: Path, *arguments: str) -> str:
                return (
                    ""
                    if arguments
                    == ("status", "--porcelain", "--untracked-files=all")
                    else "a" * 40
                )

            with patch(
                "epiagentbench.development_pilot._git_output",
                side_effect=git_output,
            ), patch(
                "epiagentbench.development_pilot.secrets.token_bytes",
                return_value=b"m" * 32,
            ):
                prepare_panel(
                    root=root,
                    private_manifest_path=private_path,
                    public_manifest_path=public_path,
                )
            private = _load_json(private_path)
            public = _load_json(public_path)
            public["episodes"][0]["family"] = "tampered"
            with self.assertRaisesRegex(ValueError, "precommitment"):
                _validate_commitments(private, public, root=root)

    def test_private_checkpoint_reconstructs_missing_public_write(self) -> None:
        result = _sanitize_result(
            episode=PANEL[0],
            result=self.result(),
            started_at="start",
            finished_at="finish",
        )
        assignments = [
            {
                "episode_ref": "episode_01",
                "system": "codex",
                "status": "complete",
                "public_result": result,
            }
        ]
        self.assertEqual(_reconstruct_public_results(assignments), [result])

    def test_interrupted_assignment_fails_closed(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "no-retry"):
            _reconstruct_public_results(
                [
                    {
                        "episode_ref": "episode_01",
                        "system": "codex",
                        "status": "in_progress",
                    }
                ]
            )

    def test_cli_usage_error_is_infrastructure_not_model_zero(self) -> None:
        failed = replace(
            self.result("cursor"),
            returncode=1,
            stdout_bytes=0,
            stderr_bytes=100,
            diagnostic="stderr: Invalid --allowed-tools value",
            audit_events=("agent_failure:nonzero_exit",),
        )
        with self.assertRaisesRegex(RuntimeError, "harness startup"):
            _raise_on_harness_startup_failure(failed)

    def test_missing_episode_mcp_is_infrastructure_not_model_zero(self) -> None:
        failed = replace(
            self.result("claude"),
            audit_events=("agent_failure:mcp_unavailable",),
        )
        with self.assertRaisesRegex(RuntimeError, "MCP was unavailable"):
            _raise_on_harness_startup_failure(failed)


if __name__ == "__main__":
    unittest.main()
