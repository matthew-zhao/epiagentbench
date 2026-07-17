from __future__ import annotations

from collections import Counter
from contextlib import contextmanager, ExitStack
from dataclasses import asdict, replace
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import epiagentbench.development_matched_panel as matched
from epiagentbench.development_matched_panel import (
    ASSIGNMENT_COUNT,
    COHORT_ID,
    EPISODE_COUNT,
    FAMILIES,
    PROFILES,
    aggregate_complete_results,
    prepare_panel,
    run_environment_preflight,
    run_panel,
)
from epiagentbench.pilot import PilotRunResult
from epiagentbench.replay_trace import replay_trace_sha256
from epiagentbench.trusted.episode_pack import (
    PrivateEpisodeCohortManifest,
    PrivateEpisodePack,
)


GENERATOR = "sha256:" + "a" * 64
AUTHENTICATION_KEY = b"matched panel authentication key".ljust(32, b"!")
SOURCE_CONTRACT = {
    "tracked_runtime_file_count": 40,
    "tracked_runtime_surface_sha256": "sha256:" + "b" * 64,
    "task_prompt_sha256": "sha256:" + "c" * 64,
}
CLI_CONTRACT = {
    "executables": [
        {"name": "claude", "version": "claude-test"},
        {"name": "codex", "version": "codex-test"},
        {"name": "cursor-agent", "version": "cursor-test"},
    ]
}
RUNTIME_CONTRACT = {
    "python": "test-python",
    "starsim": "3.5.1",
    "platform": "test-platform",
    "machine": "test-machine",
}
CLI_VERSIONS = {
    item["name"]: item["version"] for item in CLI_CONTRACT["executables"]
}


class MatchedPanelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.key_path = self.root / "authentication.key"
        self.key_path.write_bytes(AUTHENTICATION_KEY)
        os.chmod(self.key_path, 0o600)
        self.private_path = self.root / "run_artifacts" / "private.json"
        self.public_path = self.root / "results" / "manifest.json"
        self.results_path = self.root / "results" / "results.json"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _cohort(
        self, count: int = EPISODE_COUNT, *, cohort_id: str = COHORT_ID
    ) -> Path:
        cohort = self.root / f"cohort-{count}-{cohort_id}"
        cohort.mkdir(mode=0o700)
        packs: list[PrivateEpisodePack] = []
        for index in range(count):
            family = FAMILIES[index % len(FAMILIES)]
            packs.append(
                PrivateEpisodePack.create(
                    cohort_id=cohort_id,
                    episode_index=index,
                    backend="starsim-ltc-v3",
                    family=family,
                    seed=index + 100,
                    generator_fingerprint=GENERATOR,
                    episode_secret=hashlib.sha256(f"secret-{index}".encode()).digest(),
                    commitment_nonce=hashlib.sha256(
                        f"nonce-{index}".encode()
                    ).digest(),
                )
            )
        manifest = PrivateEpisodeCohortManifest.create(
            packs, manifest_nonce=hashlib.sha256(b"manifest").digest()
        )
        for pack in packs:
            pack.write(cohort / f"episode-{pack.episode_index:06d}.pack", AUTHENTICATION_KEY)
        manifest_path = cohort / "cohort.manifest"
        manifest.write(manifest_path, AUTHENTICATION_KEY)
        return manifest_path

    @staticmethod
    def _git_output(_: Path, *arguments: str) -> str:
        if arguments == ("rev-parse", "HEAD"):
            return "d" * 40
        return ""

    @contextmanager
    def _contracts(self):
        with ExitStack() as stack:
            stack.enter_context(
                patch(
                    "epiagentbench.development_matched_panel._git_output",
                    side_effect=self._git_output,
                )
            )
            stack.enter_context(
                patch(
                    "epiagentbench.development_matched_panel._source_contract",
                    return_value=SOURCE_CONTRACT,
                )
            )
            stack.enter_context(
                patch(
                    "epiagentbench.development_matched_panel._cli_contract",
                    return_value=CLI_CONTRACT,
                )
            )
            stack.enter_context(
                patch(
                    "epiagentbench.development_matched_panel._runtime_contract",
                    return_value=RUNTIME_CONTRACT,
                )
            )
            stack.enter_context(
                patch(
                    "epiagentbench.development_matched_panel.compute_generator_fingerprint",
                    return_value=GENERATOR,
                )
            )
            yield

    def _prepare(self, manifest_path: Path | None = None) -> dict:
        manifest_path = manifest_path or self._cohort()
        with self._contracts(), patch(
            "epiagentbench.development_matched_panel.secrets.token_bytes",
            return_value=b"s" * 32,
        ):
            return prepare_panel(
                root=self.root,
                cohort_manifest_path=manifest_path,
                authentication_key_file=self.key_path,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                timeout_seconds=30,
                claude_max_budget_usd=1.0,
            )

    @staticmethod
    def _result(system: str, model: str, executable: str, total: float) -> PilotRunResult:
        replay_trace = {
            "schema_version": "epiagentbench.aggregate-replay-trace.v1",
            "frame_interval_minutes": 360,
            "frames": [
                {
                    "minute": minute,
                    "active_currently_infected": 2,
                    "active_cumulative_infections": 2,
                    "active_reporting_artifacts": 0,
                    "no_action_currently_infected": 2,
                    "no_action_cumulative_infections": 2,
                    "no_action_reporting_artifacts": 0,
                    "effective_controls": {
                        "infection_control": "off",
                        "source_control": "off",
                        "entry_control": "off",
                        "audit_reporting": "off",
                    },
                }
                for minute in (0, 360)
            ],
            "agent_events": [],
        }
        return PilotRunResult(
            system=system,
            requested_model=model,
            observed_models=() if system == "codex" else (model,),
            cli_version=CLI_VERSIONS[executable],
            development_only=True,
            hermetic=False,
            returncode=0,
            elapsed_seconds=1.0,
            submission={"private": "retained only in private checkpoint"},
            scorecard={
                "valid": True,
                "total": total,
                "dimensions": {name: 0.0 for name in matched.DIMENSION_MAXIMA},
                "metrics": {
                    "integrity_pass": True,
                    "tool_calls": 2,
                    "realized_active_infections": 2,
                    "counterfactual_no_action_infections": 2,
                    "realized_active_artifact_emissions": 0,
                    "counterfactual_no_action_artifact_emissions": 0,
                },
                "violations": [],
            },
            audit_events=(),
            stdout_bytes=10,
            stderr_bytes=0,
            diagnostic="",
            replay_trace=replay_trace,
        )

    def _run_with(self, side_effect):
        with self._contracts(), patch(
            "epiagentbench.development_matched_panel._preflight_execution"
        ), patch(
            "epiagentbench.development_matched_panel._assert_environment_preflight"
        ), patch(
            "epiagentbench.development_matched_panel.evaluate_local_cli_agent",
            side_effect=side_effect,
        ) as evaluate:
            payload = run_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_results_path=self.results_path,
                acknowledge_unbounded_provider_spend=True,
            )
        return payload, evaluate

    def test_prepare_hides_private_fields_and_commits_balanced_schedule(self):
        public = self._prepare()
        private = json.loads(self.private_path.read_text())
        self.assertEqual(public["planned_assignments"], ASSIGNMENT_COUNT)
        self.assertEqual(len(public["episodes"]), EPISODE_COUNT)
        self.assertEqual(len(public["profiles"]), 6)
        self.assertEqual(public["panel_id"], "development-matched-50x6-v3")
        self.assertEqual(public["cohort"]["cohort_id"], COHORT_ID)
        self.assertEqual(
            public["run_contract"]["replay_trace_release"]["release"],
            "terminal_retired_panel_only",
        )
        self.assertIn("replay_sha256", public["contract_hashes"])
        self.assertEqual(
            public["schedule_design"],
            {
                "name": "private_family_stratified_near_balanced_williams",
                "profile_position_count_min": 8,
                "profile_position_count_max": 9,
                "within_family_profile_position_count_min": 1,
                "within_family_profile_position_count_max": 2,
                "ordered_carryover_count_min": 8,
                "ordered_carryover_count_max": 9,
                "within_family_ordered_carryover_count_min": 1,
                "within_family_ordered_carryover_count_max": 2,
                "order_released_only_after_terminal_panel": True,
            },
        )
        self.assertEqual(
            public["run_contract"]["bootstrap"]["pairwise_multiplicity"],
            "bonferroni_fifteen_pairs",
        )
        self.assertEqual(os.stat(self.private_path).st_mode & 0o777, 0o600)
        cohort_manifest_path = Path(private["cohort_manifest_path"])
        self.assertFalse(
            matched._cohort_retirement_path(cohort_manifest_path).exists()
        )
        encoded = json.dumps(public)
        hidden_assignment_surface = json.dumps(
            {
                "episodes": public["episodes"],
                "schedule_design": public["schedule_design"],
                "results": public["results"],
            }
        )
        self.assertNotIn(str(self.root), encoded)
        for family in FAMILIES:
            self.assertNotIn(family, hidden_assignment_surface)
        for forbidden in ("pack_path", "seed", "episode_secret", "profile_order"):
            self.assertNotIn(forbidden, encoded)

        keys = matched._assignment_keys(private["schedule"])
        self.assertEqual(len(keys), ASSIGNMENT_COUNT)
        self.assertEqual(len(set(keys)), ASSIGNMENT_COUNT)
        self.assertEqual(
            Counter(item["family"] for item in private["episodes"]),
            Counter({family: 10 for family in FAMILIES}),
        )
        profile_ids = {profile["profile_id"] for profile in PROFILES}
        self.assertTrue(
            all(
                len(item["profile_order"]) == len(PROFILES)
                and set(item["profile_order"]) == profile_ids
                for item in private["schedule"]
            )
        )
        for position in range(len(PROFILES)):
            counts = Counter(
                item["profile_order"][position] for item in private["schedule"]
            )
            self.assertEqual(set(counts), profile_ids)
            self.assertTrue(set(counts.values()).issubset({8, 9}))

        family_by_ref = {
            item["episode_ref"]: item["family"] for item in private["episodes"]
        }
        expected_carryovers = {
            (first, second)
            for first in profile_ids
            for second in profile_ids
            if first != second
        }
        overall_carryovers: Counter[tuple[str, str]] = Counter()
        for family in FAMILIES:
            family_schedule = [
                item
                for item in private["schedule"]
                if family_by_ref[item["episode_ref"]] == family
            ]
            self.assertEqual(len(family_schedule), 10)
            for position in range(len(PROFILES)):
                counts = Counter(
                    item["profile_order"][position] for item in family_schedule
                )
                self.assertEqual(set(counts), profile_ids)
                self.assertTrue(set(counts.values()).issubset({1, 2}))
            family_carryovers = Counter(
                pair
                for item in family_schedule
                for pair in zip(
                    item["profile_order"], item["profile_order"][1:]
                )
            )
            self.assertEqual(set(family_carryovers), expected_carryovers)
            self.assertTrue(
                set(family_carryovers.values()).issubset({1, 2})
            )
            overall_carryovers.update(family_carryovers)
        self.assertEqual(set(overall_carryovers), expected_carryovers)
        self.assertTrue(set(overall_carryovers.values()).issubset({8, 9}))

    def test_prepare_rejects_wrong_cardinality_and_public_tamper(self):
        with self.assertRaisesRegex(ValueError, "exactly 50"):
            self._prepare(self._cohort(49))

        self.private_path.unlink(missing_ok=True)
        self.public_path.unlink(missing_ok=True)
        self._prepare()
        public = json.loads(self.public_path.read_text())
        public["episodes"][0]["pack_commitment"] = "sha256:" + "f" * 64
        with self._contracts(), self.assertRaisesRegex(ValueError, "precommitment"):
            matched._validate_contracts(
                root=self.root,
                private=matched._load_private_state(
                    self.private_path, AUTHENTICATION_KEY
                ),
                public=public,
                authentication_key=AUTHENTICATION_KEY,
            )

    def test_six_treatment_williams_rows_and_family_extras_are_exact(self):
        rows = matched._WILLIAMS
        self.assertEqual(len(rows), 6)
        self.assertEqual(rows[0], (0, 1, 5, 2, 4, 3))
        self.assertTrue(all(set(row) == set(range(6)) for row in rows))
        predecessor_counts = Counter(
            (first, second)
            for row in rows
            for first, second in zip(row, row[1:])
        )
        self.assertEqual(
            predecessor_counts,
            Counter(
                {
                    (first, second): 1
                    for first in range(6)
                    for second in range(6)
                    if first != second
                }
            ),
        )

        self._prepare()
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        nonce = bytes.fromhex(private["schedule_nonce_hex"])
        profile_permutation = tuple(
            sorted(
                (profile["profile_id"] for profile in PROFILES),
                key=lambda value: matched._keyed(nonce, "profile", value),
            )
        )
        treatment_by_profile = {
            profile_id: index
            for index, profile_id in enumerate(profile_permutation)
        }
        row_id_by_order = {row: row_id for row_id, row in enumerate(rows)}
        family_by_ref = {
            item["episode_ref"]: item["family"] for item in private["episodes"]
        }
        rows_by_family = {family: Counter() for family in FAMILIES}
        for item in private["schedule"]:
            treatment_order = tuple(
                treatment_by_profile[profile_id]
                for profile_id in item["profile_order"]
            )
            rows_by_family[family_by_ref[item["episode_ref"]]][
                row_id_by_order[treatment_order]
            ] += 1

        for family_index, family in enumerate(FAMILIES):
            expected = Counter(range(6))
            expected.update(matched._EXTRA_SEQUENCES[family_index])
            self.assertEqual(rows_by_family[family], expected)
        overall = sum(rows_by_family.values(), Counter())
        self.assertEqual(overall, Counter({0: 9, 1: 9, 2: 8, 3: 8, 4: 8, 5: 8}))

    def test_prepare_rejects_incomplete_or_wrong_cohort_identity(self):
        incomplete = self._cohort()
        (incomplete.parent / ".freeze-incomplete").write_text("incomplete\n")
        with self.assertRaisesRegex(ValueError, "incomplete marker"):
            self._prepare(incomplete)
        self.assertFalse(self.private_path.exists())
        self.assertFalse(self.public_path.exists())

        wrong = self._cohort(cohort_id="development-matched-50x4-v1")
        with self.assertRaisesRegex(ValueError, "identifier"):
            self._prepare(wrong)
        self.assertFalse(self.private_path.exists())
        self.assertFalse(self.public_path.exists())

    def test_spend_gate_prevents_every_provider_call(self):
        self._prepare()
        with patch(
            "epiagentbench.development_matched_panel.evaluate_local_cli_agent"
        ) as evaluate, self.assertRaisesRegex(RuntimeError, "unbounded provider spend"):
            run_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_results_path=self.results_path,
            )
        evaluate.assert_not_called()

    def test_clean_worktree_gate_allows_only_the_private_retirement_marker(self):
        self._prepare()
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        retirement_path = matched._cohort_retirement_path(
            Path(private["cohort_manifest_path"])
        )
        matched._atomic_json(retirement_path, {"test": True}, private=True)
        matched._atomic_json(self.results_path, {"status": "complete"})
        public_relative = matched._relative_to_root(self.public_path, self.root)
        private_relative = matched._relative_to_root(self.private_path, self.root)
        results_relative = matched._relative_to_root(self.results_path, self.root)
        retirement_relative = matched._relative_to_root(retirement_path, self.root)

        def git_output(_: Path, *arguments: str) -> str:
            if arguments == (
                "ls-files",
                "--error-unmatch",
                public_relative,
            ):
                return public_relative
            if arguments in {
                ("ls-files", private_relative),
                ("ls-files", retirement_relative),
            }:
                return ""
            if arguments == (
                "status",
                "--porcelain",
                "--untracked-files=all",
            ):
                return "\n".join(
                    (
                        f"?? {retirement_relative}",
                        f"?? {results_relative}",
                    )
                )
            self.fail(f"unexpected git probe: {arguments!r}")

        with patch(
            "epiagentbench.development_matched_panel._git_output",
            side_effect=git_output,
        ):
            matched._preflight_execution(
                root=self.root,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_results_path=self.results_path,
                allowed_private_artifact_paths=(retirement_path,),
            )

        def dirty_git_output(root: Path, *arguments: str) -> str:
            observed = git_output(root, *arguments)
            if arguments == (
                "status",
                "--porcelain",
                "--untracked-files=all",
            ):
                return observed + "\n?? unexpected-private-file"
            return observed

        with patch(
            "epiagentbench.development_matched_panel._git_output",
            side_effect=dirty_git_output,
        ), self.assertRaisesRegex(RuntimeError, "worktree is not clean"):
            matched._preflight_execution(
                root=self.root,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_results_path=self.results_path,
                allowed_private_artifact_paths=(retirement_path,),
            )

    def test_six_profiles_complete_300_without_partial_public_scores(self):
        self._prepare()
        private_before_run = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        cohort_manifest_path = Path(private_before_run["cohort_manifest_path"])
        retirement_path = matched._cohort_retirement_path(cohort_manifest_path)
        calls: list[tuple[str, str, str | None]] = []
        terminal_write_saw_retirement = False
        captured_progress_artifacts = 0

        def evaluate(system: str, **kwargs):
            running = json.loads(self.results_path.read_text())
            self.assertEqual(running["results"], [])
            self.assertEqual(running["summary"], {"primary_estimand": "pending"})
            self.assertNotIn("replay_trace", json.dumps(running))
            self.assertNotIn("family", json.dumps(running))
            self.assertNotIn("profile_order", json.dumps(running))
            calls.append((system, kwargs["model"], kwargs["claude_effort"]))
            totals = {"claude": 10.0, "codex": 20.0}
            total = totals.get(system, 30.0 if "grok" in kwargs["model"] else 40.0)
            return self._result(system, kwargs["model"], kwargs["executable"], total)

        original_atomic_json = matched._atomic_json

        def guarded_atomic_json(path, value, **kwargs):
            nonlocal terminal_write_saw_retirement, captured_progress_artifacts
            if (
                Path(path) == self.results_path
                and isinstance(value, dict)
                and value.get("status")
                in {"running", "stopped_transport_void"}
            ):
                captured_progress_artifacts += 1
                self.assertEqual(value.get("results"), [])
                self.assertNotIn("replay_trace", json.dumps(value))
            if (
                Path(path) == self.results_path
                and isinstance(value, dict)
                and str(value.get("status", "")).startswith("complete")
            ):
                terminal_write_saw_retirement = True
                self.assertTrue(retirement_path.exists())
                matched._load_cohort_retirement_marker(
                    retirement_path, AUTHENTICATION_KEY
                )
            return original_atomic_json(path, value, **kwargs)

        with patch(
            "epiagentbench.development_matched_panel._atomic_json",
            side_effect=guarded_atomic_json,
        ):
            payload, invoked = self._run_with(evaluate)
        self.assertEqual(payload["status"], "complete")
        self.assertEqual(invoked.call_count, ASSIGNMENT_COUNT)
        self.assertTrue(terminal_write_saw_retirement)
        self.assertGreater(captured_progress_artifacts, ASSIGNMENT_COUNT)
        self.assertTrue(payload["cohort_retired_before_trace_publication"])
        self.assertTrue(
            all(result["trace_status"] == "recorded" for result in payload["results"])
        )
        self.assertTrue(
            all(
                result["replay_trace_sha256"].startswith("sha256:")
                for result in payload["results"]
            )
        )
        for result in payload["results"]:
            with self.subTest(
                episode_ref=result["episode_ref"],
                profile_id=result["profile_id"],
            ):
                self.assertEqual(
                    result["replay_trace_sha256"],
                    replay_trace_sha256(
                        result["replay_trace"],
                        episode_ref=result["episode_ref"],
                        profile_id=result["profile_id"],
                        pack_commitment=result["pack_commitment"],
                    ),
                )
        self.assertEqual(os.stat(retirement_path).st_mode & 0o777, 0o600)
        retirement = matched._load_cohort_retirement_marker(
            retirement_path, AUTHENTICATION_KEY
        )
        self.assertEqual(retirement["cohort_id"], COHORT_ID)
        self.assertEqual(retirement["panel_id"], matched.PANEL_ID)
        self.assertEqual(
            retirement["public_precommitment_sha256"],
            payload["precommitment_sha256"],
        )
        self.assertEqual(
            retirement["terminal_results_sha256"], payload["results_sha256"]
        )
        self.assertEqual(
            retirement["terminal_trace_results_sha256"],
            matched._terminal_trace_results_hash(payload),
        )
        self.assertEqual(retirement["terminal_assignments"], ASSIGNMENT_COUNT)

        resumed, resumed_invoked = self._run_with(
            lambda *_args, **_kwargs: self.fail(
                "a terminal retry must not invoke a provider"
            )
        )
        self.assertEqual(resumed, payload)
        resumed_invoked.assert_not_called()

        with self._contracts(), self.assertRaisesRegex(ValueError, "retired"):
            prepare_panel(
                root=self.root,
                cohort_manifest_path=cohort_manifest_path,
                authentication_key_file=self.key_path,
                private_state_path=self.root
                / "run_artifacts"
                / "reused-private.json",
                public_manifest_path=self.root
                / "results"
                / "reused-manifest.json",
            )

        tampered = json.loads(retirement_path.read_text())
        tampered["terminal_results_sha256"] = "sha256:" + "f" * 64
        matched._atomic_json(retirement_path, tampered, private=True)
        with self.assertRaisesRegex(ValueError, "authentication"):
            self._run_with(
                lambda *_args, **_kwargs: self.fail(
                    "tampered retirement must fail before a provider call"
                )
            )
        cursor_models = {
            model for system, model, _ in calls if system == "cursor"
        }
        self.assertEqual(cursor_models, {"cursor-grok-4.5-high", "kimi-k2.7-code"})
        self.assertEqual(sum(system == "cursor" for system, _, _ in calls), 100)
        self.assertTrue(
            all(
                effort == "high"
                for system, _, effort in calls
                if system == "claude"
            )
        )
        means = {
            key: value["mean_total"]
            for key, value in payload["summary"]["profiles"].items()
        }
        self.assertEqual(
            means,
            {
                "claude-opus-high": 10.0,
                "claude-sonnet-high": 10.0,
                "codex-sol": 20.0,
                "codex-luna-medium": 20.0,
                "cursor-grok-high": 30.0,
                "cursor-kimi-k27-code": 40.0,
            },
        )

    def test_terminalization_rejects_cross_profile_no_action_mismatch(self):
        first = asdict(
            self._result("codex", "gpt-5.6-sol", "codex", 50.0)
        )
        second = asdict(
            self._result("codex", "gpt-5.6-luna", "codex", 50.0)
        )
        second["replay_trace"]["frames"][1][
            "no_action_currently_infected"
        ] = 1
        # Both traces remain individually valid; only their shared no-action
        # counterfactual has been made inconsistent.
        matched.validate_replay_trace(first["replay_trace"])
        matched.validate_replay_trace(second["replay_trace"])

        private = {
            "episodes": [
                {
                    "episode_ref": "episode_0001",
                    "family": FAMILIES[0],
                    "pack_commitment": "sha256:" + "1" * 64,
                }
            ],
            "assignments": [
                {
                    "episode_ref": "episode_0001",
                    "profile_id": "codex-sol",
                    "status": "complete",
                    "public_result": {
                        "episode_ref": "episode_0001",
                        "profile_id": "codex-sol",
                    },
                    "raw_result": first,
                },
                {
                    "episode_ref": "episode_0001",
                    "profile_id": "codex-luna-medium",
                    "status": "complete",
                    "public_result": {
                        "episode_ref": "episode_0001",
                        "profile_id": "codex-luna-medium",
                    },
                    "raw_result": second,
                },
            ],
        }
        with self.assertRaisesRegex(
            ValueError, "profiles disagree on the no-action replay twin"
        ):
            matched._complete_artifact({}, private)

    def test_orphan_is_sealed_never_retried_and_void_suppresses_means(self):
        self._prepare()
        private = json.loads(self.private_path.read_text())
        private.pop("state_authentication")
        first_ref = private["schedule"][0]["episode_ref"]
        first_profile = private["schedule"][0]["profile_order"][0]
        private["assignments"].append(
            {
                "episode_ref": first_ref,
                "profile_id": first_profile,
                "status": "started",
                "started_at_utc": "before-crash",
            }
        )
        matched._write_private_state(
            self.private_path, private, AUTHENTICATION_KEY
        )

        stopped, first_run = self._run_with(
            lambda *_args, **_kwargs: self.fail("orphan must not be retried")
        )
        self.assertEqual(stopped["status"], "stopped_transport_void")
        first_run.assert_not_called()

        calls: list[tuple[str, str]] = []

        def evaluate(system: str, **kwargs):
            calls.append((system, kwargs["model"]))
            return self._result(system, kwargs["model"], kwargs["executable"], 50.0)

        complete, second_run = self._run_with(evaluate)
        self.assertEqual(second_run.call_count, ASSIGNMENT_COUNT - 1)
        self.assertEqual(complete["status"], "complete_with_transport_voids")
        self.assertEqual(
            complete["summary"]["primary_estimand"],
            "unavailable_due_to_transport_voids",
        )
        self.assertFalse(complete["summary"]["fixed_denominator_means_reported"])
        self.assertNotIn("profiles", complete["summary"])

    def test_aggregate_arithmetic_and_bootstrap_are_deterministic(self):
        totals = {
            "claude-opus-high": 10.0,
            "claude-sonnet-high": 15.0,
            "codex-sol": 20.0,
            "codex-luna-medium": 25.0,
            "cursor-grok-high": 30.0,
            "cursor-kimi-k27-code": 40.0,
        }
        results = []
        for index in range(EPISODE_COUNT):
            family = FAMILIES[index % len(FAMILIES)]
            for profile_id, total in totals.items():
                results.append(
                    {
                        "episode_ref": f"episode_{index + 1:04d}",
                        "profile_id": profile_id,
                        "family": family,
                        "valid": True,
                        "total": total,
                    }
                )
        first = aggregate_complete_results(results)
        second = aggregate_complete_results(results)
        self.assertEqual(first, second)
        for profile_id, total in totals.items():
            profile = first["profiles"][profile_id]
            self.assertEqual(profile["mean_total"], total)
            self.assertEqual(profile["valid_rate"], 1.0)
            self.assertEqual(profile["family_stratified_bootstrap_95_ci"], [total, total])
            self.assertEqual(set(profile["by_family"]), set(FAMILIES))
            self.assertTrue(
                all(
                    family["fixed_denominator"] == 10
                    and family["valid"] == 10
                    and family["mean_total"] == total
                    for family in profile["by_family"].values()
                )
            )
        self.assertEqual(len(first["exploratory_pairwise_deltas"]), 15)
        self.assertEqual(
            first["exploratory_pairwise_deltas"][
                "claude-opus-high_minus_codex-sol"
            ]["mean_delta"],
            -10.0,
        )
        pair = first["exploratory_pairwise_deltas"][
            "claude-opus-high_minus_codex-sol"
        ]
        self.assertEqual(pair["simultaneous_familywise_confidence_target"], 0.95)
        self.assertEqual(set(pair["by_family_mean_delta"].values()), {-10.0})

    def test_aggregate_rejects_family_disagreement_and_invalid_totals(self):
        results = []
        for index in range(EPISODE_COUNT):
            family = FAMILIES[index % len(FAMILIES)]
            for profile in PROFILES:
                results.append(
                    {
                        "episode_ref": f"episode_{index + 1:04d}",
                        "profile_id": profile["profile_id"],
                        "family": family,
                        "valid": True,
                        "total": 50.0,
                    }
                )
        results[0]["family"] = FAMILIES[1]
        with self.assertRaisesRegex(ValueError, "disagree"):
            aggregate_complete_results(results)
        results[0]["family"] = FAMILIES[0]
        results[0]["total"] = float("nan")
        with self.assertRaisesRegex(ValueError, "Invalid complete"):
            aggregate_complete_results(results)

    def test_private_checkpoint_tamper_is_rejected(self):
        self._prepare()
        payload = json.loads(self.private_path.read_text())
        payload["status"] = "complete"
        matched._atomic_json(self.private_path, payload, private=True)
        with self.assertRaisesRegex(ValueError, "authentication failed"):
            matched._load_private_state(self.private_path, AUTHENTICATION_KEY)

    def test_exact_kimi_code_receipt_rejects_model_alias_downgrade(self):
        profile = next(
            profile
            for profile in PROFILES
            if profile["profile_id"] == "cursor-kimi-k27-code"
        )
        result = self._result("cursor", "kimi-k2.7-code", "cursor-agent", 50.0)
        downgraded = replace(result, observed_models=("Kimi K2.7",))
        sanitized = matched._sanitize_result(
            episode={
                "episode_ref": "episode_0001",
                "family": FAMILIES[0],
                "pack_commitment": "sha256:" + "1" * 64,
            },
            profile=profile,
            result=downgraded,
            started_at="start",
            finished_at="finish",
        )
        self.assertFalse(sanitized["valid"])
        self.assertEqual(sanitized["total"], 0.0)
        self.assertIn("agent_failure:model_receipt_missing", sanitized["audit_events"])

    def test_terminal_trace_survives_an_invalid_model_scorecard(self):
        result = self._result("codex", "gpt-5.6-sol", "codex", 0.0)
        invalid = replace(
            result,
            scorecard={
                "valid": False,
                "total": 0.0,
                "dimensions": {},
                "metrics": {"integrity_pass": False, "tool_calls": 1},
                "violations": ["invalid_submission"],
            },
        )
        payload = matched._terminal_replay_payload(
            {
                "episode_ref": "episode_0001",
                "profile_id": "codex-sol",
                "raw_result": asdict(invalid),
            },
            {"pack_commitment": "sha256:" + "1" * 64},
        )
        self.assertEqual(payload["trace_status"], "recorded")
        self.assertTrue(payload["replay_trace_sha256"].startswith("sha256:"))

    def test_sonnet_five_receipt_identity_is_exact(self):
        profile = next(
            profile
            for profile in PROFILES
            if profile["profile_id"] == "claude-sonnet-high"
        )
        self.assertTrue(
            matched._exact_model_receipt_satisfied(
                profile, ("Claude Sonnet 5",)
            )
        )
        self.assertFalse(
            matched._exact_model_receipt_satisfied(
                profile, ("Claude Sonnet 5 High",)
            )
        )

    def test_environment_preflight_gate_prevents_production_call(self):
        self._prepare()
        with self._contracts(), patch(
            "epiagentbench.development_matched_panel._preflight_execution"
        ), patch(
            "epiagentbench.development_matched_panel.evaluate_local_cli_agent"
        ) as evaluate, self.assertRaisesRegex(RuntimeError, "environment preflight"):
            run_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_results_path=self.results_path,
                acknowledge_unbounded_provider_spend=True,
            )
        evaluate.assert_not_called()

    def test_disposable_preflight_checks_all_profiles_without_scores(self):
        self._prepare()
        preflight_path = self.root / "results" / "preflight.json"
        claude_efforts: list[str | None] = []

        def evaluate(system: str, **kwargs):
            if system == "claude":
                claude_efforts.append(kwargs["claude_effort"])
            return self._result(system, kwargs["model"], kwargs["executable"], 50.0)

        with patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}), self._contracts(), patch(
            "epiagentbench.development_matched_panel._preflight_execution"
        ), patch(
            "epiagentbench.development_matched_panel.evaluate_local_cli_agent",
            side_effect=evaluate,
        ) as invoked:
            receipt = run_environment_preflight(
                root=self.root,
                authentication_key_file=self.key_path,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_preflight_path=preflight_path,
                acknowledge_unbounded_provider_spend=True,
            )
        self.assertEqual(receipt["status"], "passed")
        self.assertEqual(invoked.call_count, len(PROFILES))
        self.assertEqual(claude_efforts, ["high", "high"])
        self.assertEqual(receipt["production_episodes_consumed"], 0)
        self.assertTrue(all(not item["scored"] for item in receipt["profiles"]))
        self.assertTrue(
            all(item["replay_trace_validated"] for item in receipt["profiles"])
        )
        self.assertNotIn("agent_events", json.dumps(receipt))
        self.assertNotIn("total", json.dumps(receipt))
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        self.assertEqual(private["environment_preflight"]["status"], "passed")
        self.assertEqual(private["assignments"], [])

    def test_disposable_preflight_requires_cursor_key_before_any_call(self):
        self._prepare()
        with patch.dict(os.environ, {}, clear=True), patch(
            "epiagentbench.development_matched_panel.evaluate_local_cli_agent"
        ) as evaluate, self.assertRaisesRegex(RuntimeError, "requires CURSOR_API_KEY"):
            run_environment_preflight(
                root=self.root,
                authentication_key_file=self.key_path,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_preflight_path=self.root / "results" / "preflight.json",
                acknowledge_unbounded_provider_spend=True,
            )
        evaluate.assert_not_called()

    def test_failed_disposable_preflight_is_one_shot(self):
        self._prepare()
        preflight_path = self.root / "results" / "preflight.json"
        with (
            patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}),
            self._contracts(),
            patch("epiagentbench.development_matched_panel._preflight_execution"),
            patch(
                "epiagentbench.development_matched_panel.evaluate_local_cli_agent",
                side_effect=RuntimeError("credential exchange failed"),
            ),
        ):
            receipt = run_environment_preflight(
                root=self.root,
                authentication_key_file=self.key_path,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_preflight_path=preflight_path,
                acknowledge_unbounded_provider_spend=True,
            )
        self.assertEqual(receipt["status"], "failed")
        self.assertEqual(receipt["failure_stage"], "provider_launch")

        with (
            patch.dict(os.environ, {"CURSOR_API_KEY": "test-only"}),
            self._contracts(),
            patch("epiagentbench.development_matched_panel._preflight_execution"),
            patch(
                "epiagentbench.development_matched_panel.evaluate_local_cli_agent"
            ) as evaluate,
            self.assertRaisesRegex(RuntimeError, "one-shot required state"),
        ):
            run_environment_preflight(
                root=self.root,
                authentication_key_file=self.key_path,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_preflight_path=preflight_path,
                acknowledge_unbounded_provider_spend=True,
            )
        evaluate.assert_not_called()

    def test_exclusive_runner_lock_rejects_concurrent_invocation(self):
        copied_state_path = self.root / "run_artifacts" / "copied-private.json"
        with matched._exclusive_run_lock(self.private_path), self.assertRaisesRegex(
            RuntimeError, "already holds the lock"
        ):
            run_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                private_state_path=copied_state_path,
                public_manifest_path=self.public_path,
                public_results_path=self.results_path,
                acknowledge_unbounded_provider_spend=True,
            )

    def test_prepare_rejects_aliased_private_and_public_paths(self):
        manifest = self._cohort()
        with self._contracts(), self.assertRaisesRegex(ValueError, "must be distinct"):
            prepare_panel(
                root=self.root,
                cohort_manifest_path=manifest,
                authentication_key_file=self.key_path,
                private_state_path=self.private_path,
                public_manifest_path=self.private_path,
            )

    def test_partial_state_cannot_claim_completion(self):
        self._prepare()
        private = matched._load_private_state(
            self.private_path, AUTHENTICATION_KEY
        )
        private["status"] = "complete"
        private["assignments"] = [
            {
                "episode_ref": private["schedule"][0]["episode_ref"],
                "profile_id": private["schedule"][0]["profile_order"][0],
                "status": "transport_void",
                "started_at_utc": "start",
                "finished_at_utc": "finish",
            }
        ]
        matched._write_private_state(
            self.private_path, private, AUTHENTICATION_KEY
        )
        with self._contracts(), patch(
            "epiagentbench.development_matched_panel.evaluate_local_cli_agent"
        ) as evaluate, self.assertRaisesRegex(ValueError, "not fully terminal"):
            run_panel(
                root=self.root,
                authentication_key_file=self.key_path,
                private_state_path=self.private_path,
                public_manifest_path=self.public_path,
                public_results_path=self.results_path,
                acknowledge_unbounded_provider_spend=True,
            )
        evaluate.assert_not_called()

    def test_terminal_artifact_reveals_verifiable_schedule_and_family_map(self):
        self._prepare()

        def evaluate(system: str, **kwargs):
            return self._result(system, kwargs["model"], kwargs["executable"], 50.0)

        payload, _ = self._run_with(evaluate)
        public = matched._load_json(self.public_path)
        matched.verify_revealed_commitments(public, payload)
        payload["schedule"][0]["profile_order"] = list(
            reversed(payload["schedule"][0]["profile_order"])
        )
        with self.assertRaisesRegex(ValueError, "schedule"):
            matched.verify_revealed_commitments(public, payload)


if __name__ == "__main__":
    unittest.main()
