from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from epiagentbench.development_opus_pilot import (
    BACKEND,
    CLAUDE_EFFORT,
    EPISODE_REFS,
    EXPECTED_CLAUDE_INIT_TOOLS,
    FAMILIES,
    PANEL_ID,
    PUBLIC_MCP_TOOLS,
    REQUESTED_MODEL,
    _canonical_bytes,
    _claude_isolation_contract,
    _claude_structured_output_contract,
    _family_commitment,
    _private_panel,
    _raise_on_opus_startup_failure,
    _reconstruct_public_results,
    _sanitize_result,
    _sha256,
    _source_hashes,
    aggregate_results,
    prepare_panel,
    run_panel,
)
from epiagentbench.development_pilot import DIMENSION_MAXIMA
from epiagentbench.pilot import PilotRunResult, parse_agent_output


class DevelopmentOpusPilotTests(unittest.TestCase):
    CLAUDE_VERSION = "2.1.195 (Claude Code)"

    def result(
        self,
        *,
        observed_models: tuple[str, ...] = (REQUESTED_MODEL,),
        valid: bool = True,
        returncode: int = 0,
        tool_calls: int = 1,
        audit_events: tuple[str, ...] = (),
    ) -> PilotRunResult:
        return PilotRunResult(
            system="claude",
            requested_model=REQUESTED_MODEL,
            observed_models=observed_models,
            cli_version=self.CLAUDE_VERSION,
            development_only=True,
            hermetic=False,
            returncode=returncode,
            elapsed_seconds=10.0,
            submission={"private": "structured native output"} if valid else {},
            scorecard={
                "valid": valid,
                "total": 80.0 if valid else 0.0,
                "dimensions": {
                    name: maximum * 0.8
                    for name, maximum in DIMENSION_MAXIMA.items()
                }
                if valid
                else {},
                "metrics": {
                    "integrity_pass": valid,
                    "case_f1": 0.8 if valid else 0.0,
                    "raw_action_utility": 123,
                    "tool_calls": tool_calls,
                },
                "violations": [],
            },
            audit_events=audit_events,
            stdout_bytes=100,
            stderr_bytes=0,
            diagnostic="private diagnostic",
        )

    def _fake_root(self, root: Path) -> None:
        (root / "schemas").mkdir()
        (root / "schemas" / "submission.schema.json").write_text(
            (
                Path(__file__).resolve().parents[1]
                / "schemas"
                / "submission.schema.json"
            ).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        package = root / "src" / "epiagentbench"
        package.mkdir(parents=True)
        (package / "pilot.py").write_text("pilot", encoding="utf-8")
        (package / "development_pilot.py").write_text(
            "shared development pilot", encoding="utf-8"
        )
        (package / "development_opus_pilot.py").write_text(
            "opus pilot", encoding="utf-8"
        )
        client = root / "src" / "epiagentbench_client"
        client.mkdir()
        (client / "mcp_server.py").write_text("client", encoding="utf-8")
        examples = root / "examples"
        examples.mkdir()
        (examples / "run_development_opus_pilot.py").write_text(
            "runner", encoding="utf-8"
        )
        (root / "pyproject.toml").write_text("[project]\n", encoding="utf-8")

    @staticmethod
    def _fake_git(_: Path, *arguments: str) -> str:
        if arguments == ("status", "--porcelain", "--untracked-files=all"):
            return ""
        if arguments[:2] == ("ls-files", "--"):
            return "\n".join(
                (
                    "examples/run_development_opus_pilot.py",
                    "pyproject.toml",
                    "schemas/submission.schema.json",
                    "src/epiagentbench/development_opus_pilot.py",
                    "src/epiagentbench/development_pilot.py",
                    "src/epiagentbench/pilot.py",
                    "src/epiagentbench_client/mcp_server.py",
                )
            )
        return "a" * 40

    def test_master_randomizes_private_balanced_families_and_seeds(self) -> None:
        first = _private_panel(b"a" * 32)
        second = _private_panel(b"b" * 32)
        self.assertEqual(tuple(item["episode_ref"] for item in first), EPISODE_REFS)
        self.assertEqual({item["family"] for item in first}, set(FAMILIES))
        self.assertEqual({item["family"] for item in second}, set(FAMILIES))
        self.assertNotEqual(
            [item["family"] for item in first],
            [item["family"] for item in second],
        )
        self.assertNotEqual(
            [item["seed"] for item in first], [item["seed"] for item in second]
        )
        self.assertTrue(all(0 <= int(item["seed"]) < 2**52 for item in first))

    def test_prepare_hides_seeds_and_secrets_and_fixes_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._fake_root(root)
            private_path = root / "run_artifacts" / "private.json"
            public_path = root / "results" / "manifest.json"
            with patch(
                "epiagentbench.development_opus_pilot._git_output",
                side_effect=self._fake_git,
            ), patch(
                "epiagentbench.development_opus_pilot.secrets.token_bytes",
                return_value=b"o" * 32,
            ), patch(
                "epiagentbench.development_opus_pilot._claude_version",
                return_value=self.CLAUDE_VERSION,
            ):
                public = prepare_panel(
                    root=root,
                    private_manifest_path=private_path,
                    public_manifest_path=public_path,
                )

            private_text = private_path.read_text(encoding="utf-8")
            public_text = public_path.read_text(encoding="utf-8")
            self.assertIn((b"o" * 32).hex(), private_text)
            self.assertNotIn((b"o" * 32).hex(), public_text)
            self.assertNotIn("panel_master_secret_opening_hex", public_text)
            self.assertNotIn('"seed":', public_text)
            self.assertIn('"seed":', private_text)
            for family in FAMILIES:
                self.assertNotIn(family, public_text)
            self.assertEqual(os.stat(private_path).st_mode & 0o777, 0o600)
            commitments = {
                episode["episode_secret_commitment"]
                for episode in public["episodes"]
            }
            self.assertEqual(len(commitments), 5)
            self.assertTrue(
                all(value.startswith("sha256:") for value in commitments)
            )
            self.assertEqual(public["panel_id"], PANEL_ID)
            self.assertEqual(
                public["panel_id"],
                "development-opus-high-pilot-v3-2026-07-15",
            )
            self.assertEqual(public["schema_version"], "development_opus_pilot_v3")
            private = json.loads(private_text)
            self.assertEqual(
                {item["family"] for item in private["episodes"]}, set(FAMILIES)
            )
            for public_episode, private_episode in zip(
                public["episodes"], private["episodes"], strict=True
            ):
                self.assertEqual(
                    public_episode["family_commitment"],
                    _family_commitment(
                        bytes.fromhex(
                            private_episode["family_opening_salt_hex"]
                        ),
                        private_episode["family"],
                    ),
                )
            self.assertEqual(public["planned_assignments"], 5)
            self.assertEqual(public["run_contract"]["requested_model"], REQUESTED_MODEL)
            self.assertEqual(public["run_contract"]["requested_effort"], "high")
            self.assertEqual(
                public["run_contract"]["effort_attribution"],
                "requested_only_unverified",
            )
            self.assertEqual(
                public["run_contract"]["claude_cli_version"], self.CLAUDE_VERSION
            )
            isolation = public["run_contract"]["claude_isolation_contract"]
            self.assertEqual(isolation, _claude_isolation_contract())
            self.assertEqual(len(PUBLIC_MCP_TOOLS), 12)
            self.assertEqual(
                set(isolation["expected_init_tools"]),
                set(EXPECTED_CLAUDE_INIT_TOOLS),
            )
            self.assertEqual(isolation["expected_init_tool_count"], 13)
            self.assertEqual(isolation["permission_mode"], "dontAsk")
            self.assertFalse(isolation["safe_mode"])
            self.assertEqual(isolation["disallowed_tools"], ["Read"])
            self.assertEqual(isolation["setting_sources"], ["project"])
            self.assertEqual(
                isolation["expected_mcp_servers"], {"epiagent": "connected"}
            )
            self.assertEqual(
                isolation["structured_output_failure_event"],
                "agent_failure:structured_output_unavailable",
            )
            self.assertIsNone(public["run_contract"]["fallback_model"])
            self.assertTrue(
                public["run_contract"]["exact_model_receipt_required"]
            )
            self.assertEqual(
                public["run_contract"]["timeout_seconds_per_assignment"], 900
            )
            self.assertEqual(
                public["run_contract"]["claude_max_budget_usd_per_assignment"],
                5.0,
            )
            output_contract = public["run_contract"]["native_output_contract"]
            self.assertEqual(
                output_contract, _claude_structured_output_contract(root)
            )
            self.assertEqual(output_contract["transport"], "Claude --json-schema")
            self.assertTrue(
                output_contract["full_schema_revalidated_by_trusted_scorer"]
            )
            self.assertTrue(output_contract["provider_schema_sha256"].startswith("sha256:"))
            self.assertFalse(public["paired"])
            self.assertFalse(public["calibrated"])
            self.assertFalse(public["hermetic"])
            runtime_files = public["source_hashes"]["tracked_runtime_files"]
            self.assertEqual(len(runtime_files), 7)
            self.assertIn("examples/run_development_opus_pilot.py", runtime_files)
            self.assertIn("pyproject.toml", runtime_files)
            self.assertIn("src/epiagentbench_client/mcp_server.py", runtime_files)
            self.assertIn(
                "resolved_generator_runtime_fingerprint", public["source_hashes"]
            )

    def test_source_hash_fails_closed_on_empty_or_missing_surface(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._fake_root(root)
            with patch(
                "epiagentbench.development_opus_pilot._git_output",
                return_value="",
            ):
                with self.assertRaisesRegex(RuntimeError, "empty or incomplete"):
                    _source_hashes(root)
            (root / "pyproject.toml").unlink()
            with patch(
                "epiagentbench.development_opus_pilot._git_output",
                side_effect=self._fake_git,
            ):
                with self.assertRaisesRegex(RuntimeError, "missing"):
                    _source_hashes(root)

    def test_sanitization_records_native_output_and_requires_exact_receipt(self) -> None:
        episodes = _private_panel(b"s" * 32)
        exact = _sanitize_result(
            episode=episodes[0],
            result=self.result(),
            started_at="start",
            finished_at="finish",
        )
        self.assertTrue(exact["valid"])
        self.assertTrue(exact["exact_model_receipt"])
        self.assertTrue(exact["schema_constrained_submission_accepted"])
        self.assertEqual(exact["requested_effort"], "high")
        self.assertEqual(
            exact["effort_attribution"], "requested_only_unverified"
        )
        self.assertTrue(exact["mcp_inventory_verified"])
        self.assertEqual(exact["mcp_inventory_status"], "verified")
        self.assertFalse(exact["unauthorized_tool_detected"])
        self.assertEqual(exact["unauthorized_tool_status"], "not_detected")
        encoded = json.dumps(exact)
        self.assertNotIn("structured native output", encoded)
        self.assertNotIn("private diagnostic", encoded)
        self.assertNotIn("raw_action_utility", encoded)

        nonexact = _sanitize_result(
            episode=episodes[0],
            result=self.result(observed_models=("claude-opus-4-8-fallback",)),
            started_at="start",
            finished_at="finish",
        )
        self.assertFalse(nonexact["valid"])
        self.assertEqual(nonexact["total"], 0.0)
        self.assertFalse(nonexact["exact_model_receipt"])
        self.assertFalse(nonexact["metrics"]["integrity_pass"])
        self.assertIn(
            "agent_failure:model_receipt_nonexact", nonexact["audit_events"]
        )

        unauthorized = _sanitize_result(
            episode=episodes[0],
            result=self.result(
                valid=False,
                audit_events=("agent_failure:unauthorized_tool",),
            ),
            started_at="start",
            finished_at="finish",
        )
        self.assertTrue(unauthorized["mcp_inventory_verified"])
        self.assertTrue(unauthorized["unauthorized_tool_detected"])
        self.assertEqual(unauthorized["unauthorized_tool_status"], "detected")

    def test_fixed_denominator_includes_missing_and_invalid_as_zero(self) -> None:
        episodes = _private_panel(b"d" * 32)
        first = _sanitize_result(
            episode=episodes[0],
            result=self.result(),
            started_at="start",
            finished_at="finish",
        )
        invalid = _sanitize_result(
            episode=episodes[1],
            result=self.result(valid=False),
            started_at="start",
            finished_at="finish",
        )
        summary = aggregate_results([first, invalid])
        self.assertEqual(summary["planned"], 5)
        self.assertEqual(summary["completed"], 2)
        self.assertEqual(summary["valid"], 1)
        self.assertEqual(summary["mean_total"], 16.0)
        self.assertEqual(summary["median_total"], 0.0)
        self.assertEqual(summary["mcp_inventory_verified"], 2)
        self.assertEqual(summary["mcp_inventory_unverified"], 0)
        self.assertEqual(summary["unauthorized_tool_clear"], 2)
        self.assertEqual(summary["unauthorized_tool_detected"], 0)

    def test_checkpoint_reconstruction_and_no_retry_policy(self) -> None:
        result = _sanitize_result(
            episode=_private_panel(b"c" * 32)[0],
            result=self.result(),
            started_at="start",
            finished_at="finish",
        )
        assignment = {
            "episode_ref": "episode_01",
            "system": "claude",
            "status": "complete",
            "public_result": result,
        }
        self.assertEqual(_reconstruct_public_results([assignment]), [result])
        with self.assertRaisesRegex(RuntimeError, "no-retry"):
            _reconstruct_public_results(
                [
                    {
                        "episode_ref": "episode_01",
                        "system": "claude",
                        "status": "in_progress",
                    }
                ]
            )

    def test_nonzero_pre_model_zero_tool_exit_is_infrastructure(self) -> None:
        failed = self.result(
            observed_models=(),
            valid=False,
            returncode=2,
            tool_calls=0,
        )
        with self.assertRaisesRegex(RuntimeError, "schema/model/effort/policy/config"):
            _raise_on_opus_startup_failure(failed)

        attributable = self.result(
            observed_models=(REQUESTED_MODEL,),
            valid=False,
            returncode=2,
            tool_calls=0,
        )
        _raise_on_opus_startup_failure(attributable)

        timed_out = self.result(
            observed_models=(),
            valid=False,
            returncode=124,
            tool_calls=0,
            audit_events=("agent_failure:timeout", "agent_failure:nonzero_exit"),
        )
        _raise_on_opus_startup_failure(timed_out)

        _, _, parsed_timeout_audit = parse_agent_output(
            "claude",
            requested_model=REQUESTED_MODEL,
            stdout=b"",
        )
        pre_init_timeout = self.result(
            observed_models=(),
            valid=False,
            returncode=124,
            tool_calls=0,
            audit_events=(
                "agent_failure:timeout",
                "agent_failure:nonzero_exit",
                *parsed_timeout_audit,
            ),
        )
        self.assertIn("agent_failure:mcp_unavailable", pre_init_timeout.audit_events)
        _raise_on_opus_startup_failure(pre_init_timeout)

        mcp_unavailable = self.result(
            observed_models=(REQUESTED_MODEL,),
            valid=False,
            returncode=0,
            tool_calls=0,
            audit_events=("agent_failure:mcp_unavailable",),
        )
        with self.assertRaisesRegex(RuntimeError, "MCP was unavailable"):
            _raise_on_opus_startup_failure(mcp_unavailable)

        structured_output_unavailable = self.result(
            observed_models=(REQUESTED_MODEL,),
            valid=False,
            returncode=0,
            tool_calls=0,
            audit_events=("agent_failure:structured_output_unavailable",),
        )
        with self.assertRaisesRegex(RuntimeError, "structured output was unavailable"):
            _raise_on_opus_startup_failure(structured_output_unavailable)

    def test_run_threads_exact_model_high_effort_and_native_schema_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            private_path = root / "run_artifacts" / "private.json"
            public_path = root / "results" / "manifest.json"
            results_path = root / "results" / "results.json"
            private_path.parent.mkdir()
            public_path.parent.mkdir()
            master = b"r" * 32
            private_episodes = [dict(item) for item in _private_panel(master)]
            private = {
                "panel_id": PANEL_ID,
                "episodes": private_episodes,
                "assignments": [],
                "status": "prepared",
            }
            public = {
                "panel_id": PANEL_ID,
                "precommitment_sha256": "sha256:test",
                "benchmark_base_commit": "a" * 40,
                "episodes": [
                    {
                        "episode_ref": item["episode_ref"],
                        "family_commitment": _family_commitment(
                            bytes.fromhex(item["family_opening_salt_hex"]),
                            item["family"],
                        ),
                    }
                    for item in private_episodes
                ],
                "run_contract": {
                    "timeout_seconds_per_assignment": 900,
                    "claude_max_budget_usd_per_assignment": 5.0,
                    "claude_cli_version": self.CLAUDE_VERSION,
                },
                "score_dimension_maxima": dict(DIMENSION_MAXIMA),
                "limitations": ["development only"],
            }
            environment = {
                "execution_commit": "b" * 40,
                "git_status_at_start": "",
                "starsim": "3.5.1",
                "claude_available": True,
                "claude_cli_version": self.CLAUDE_VERSION,
            }
            private["execution_environment"] = environment
            private["panel_started_at_utc"] = "panel-start"
            private_path.write_text(json.dumps(private), encoding="utf-8")
            os.chmod(private_path, 0o600)
            public_path.write_text(json.dumps(public), encoding="utf-8")
            results_path.write_text(
                json.dumps(
                    {
                        "panel_id": PANEL_ID,
                        "precommitment_sha256": "sha256:test",
                        "status": "running",
                        "attacker_injected": "must not survive",
                    }
                ),
                encoding="utf-8",
            )
            with patch(
                "epiagentbench.development_opus_pilot._validate_commitments",
                return_value=master,
            ), patch(
                "epiagentbench.development_opus_pilot._preflight_execution",
                return_value=environment,
            ), patch(
                "epiagentbench.development_opus_pilot._git_output",
                return_value="",
            ), patch(
                "epiagentbench.development_opus_pilot.evaluate_local_cli_agent",
                return_value=self.result(),
            ) as evaluate, patch(
                "epiagentbench.development_opus_pilot._claude_version",
                return_value=self.CLAUDE_VERSION,
            ) as version:
                completed = run_panel(
                    root=root,
                    private_manifest_path=private_path,
                    public_manifest_path=public_path,
                    public_results_path=results_path,
                )

            self.assertEqual(evaluate.call_count, 5)
            self.assertEqual(version.call_count, 5)
            for call in evaluate.call_args_list:
                self.assertEqual(call.args, ("claude",))
                self.assertEqual(call.kwargs["model"], REQUESTED_MODEL)
                self.assertEqual(call.kwargs["claude_effort"], CLAUDE_EFFORT)
                self.assertEqual(call.kwargs["backend"], BACKEND)
                self.assertEqual(call.kwargs["timeout_seconds"], 900)
                self.assertEqual(call.kwargs["claude_max_budget_usd"], 5.0)
                self.assertNotIn("fallback_model", call.kwargs)
            self.assertEqual(completed["status"], "complete")
            self.assertTrue(completed["panel_retired_after_publication"])
            self.assertEqual(completed["summary"]["exact_model_receipts"], 5)
            self.assertEqual(completed["summary"]["mcp_inventory_verified"], 5)
            self.assertEqual(completed["summary"]["unauthorized_tool_detected"], 0)
            self.assertEqual(completed["completed_assignments"], 5)
            self.assertEqual(
                completed["panel_master_secret_opening_hex"], master.hex()
            )
            self.assertNotIn("attacker_injected", completed)
            self.assertNotIn('"seed"', json.dumps(completed))
            for result in completed["results"]:
                self.assertIn(result["family"], FAMILIES)
                self.assertIn("family_commitment_opening_salt_hex", result)
                self.assertEqual(result["requested_effort"], "high")
                self.assertEqual(
                    result["effort_attribution"], "requested_only_unverified"
                )
                self.assertEqual(result["mcp_inventory_status"], "verified")
                self.assertEqual(
                    result["unauthorized_tool_status"], "not_detected"
                )
            unsigned = dict(completed)
            supplied = unsigned.pop("results_sha256")
            self.assertEqual(supplied, _sha256(_canonical_bytes(unsigned)))

    def test_startup_failure_persists_raw_result_before_panel_retirement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            private_path = root / "run_artifacts" / "private.json"
            public_path = root / "results" / "manifest.json"
            results_path = root / "results" / "results.json"
            private_path.parent.mkdir()
            public_path.parent.mkdir()
            master = b"z" * 32
            private = {
                "panel_id": PANEL_ID,
                "episodes": [dict(item) for item in _private_panel(master)],
                "assignments": [],
                "status": "prepared",
            }
            public = {
                "panel_id": PANEL_ID,
                "precommitment_sha256": "sha256:test",
                "benchmark_base_commit": "a" * 40,
                "episodes": [
                    {"episode_ref": item["episode_ref"]}
                    for item in private["episodes"]
                ],
                "run_contract": {
                    "timeout_seconds_per_assignment": 900,
                    "claude_max_budget_usd_per_assignment": 5.0,
                    "claude_cli_version": self.CLAUDE_VERSION,
                },
                "score_dimension_maxima": dict(DIMENSION_MAXIMA),
                "limitations": ["development only"],
            }
            environment = {
                "execution_commit": "b" * 40,
                "git_status_at_start": "",
                "starsim": "3.5.1",
                "claude_available": True,
                "claude_cli_version": self.CLAUDE_VERSION,
            }
            private_path.write_text(json.dumps(private), encoding="utf-8")
            os.chmod(private_path, 0o600)
            public_path.write_text(json.dumps(public), encoding="utf-8")
            failed = self.result(
                valid=False,
                tool_calls=0,
                audit_events=("agent_failure:structured_output_unavailable",),
            )
            with patch(
                "epiagentbench.development_opus_pilot._validate_commitments",
                return_value=master,
            ), patch(
                "epiagentbench.development_opus_pilot._preflight_execution",
                return_value=environment,
            ), patch(
                "epiagentbench.development_opus_pilot._git_output",
                return_value="",
            ), patch(
                "epiagentbench.development_opus_pilot.evaluate_local_cli_agent",
                return_value=failed,
            ), patch(
                "epiagentbench.development_opus_pilot._claude_version",
                return_value=self.CLAUDE_VERSION,
            ):
                with self.assertRaisesRegex(RuntimeError, "cannot be retried"):
                    run_panel(
                        root=root,
                        private_manifest_path=private_path,
                        public_manifest_path=public_path,
                        public_results_path=results_path,
                    )

            checkpoint = json.loads(private_path.read_text(encoding="utf-8"))
            self.assertEqual(checkpoint["status"], "blocked_infrastructure")
            self.assertEqual(len(checkpoint["assignments"]), 1)
            marker = checkpoint["assignments"][0]
            self.assertEqual(marker["status"], "in_progress")
            self.assertEqual(
                marker["raw_result"]["audit_events"],
                ["agent_failure:structured_output_unavailable"],
            )
            blocked = json.loads(results_path.read_text(encoding="utf-8"))
            self.assertEqual(blocked["status"], "blocked_infrastructure")
            self.assertEqual(blocked["completed_assignments"], 0)
            public_text = results_path.read_text(encoding="utf-8")
            self.assertNotIn("private diagnostic", public_text)
            self.assertNotIn("raw_action_utility", public_text)
            private_text = private_path.read_text(encoding="utf-8")
            self.assertIn("private diagnostic", private_text)
            self.assertIn("raw_action_utility", private_text)


if __name__ == "__main__":
    unittest.main()
