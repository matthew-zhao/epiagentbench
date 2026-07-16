from __future__ import annotations

import importlib.util
import json
import unittest

from epiagentbench.cli import build_parser
from epiagentbench.environment import BudgetExceededError, DeadlineExceededError
from epiagentbench.replay_trace import validate_replay_trace
from epiagentbench.trusted.backend import build_backend
from epiagentbench.trusted.controller import (
    PublicRequestRejected,
    TrustedEpisodeController,
)
from epiagentbench.trusted.ltc_closed_loop import LtcStarsimV3Backend
from epiagentbench.trusted.service import launch_secure_episode


HAS_STARSIM = importlib.util.find_spec("starsim") is not None
TEST_EPISODE_KEY = b"\x5a" * 32


@unittest.skipUnless(HAS_STARSIM, "install the starsim extra")
class LtcClosedLoopTests(unittest.TestCase):
    def runtime(self, family: str = "institution_person_to_person"):
        runtime = LtcStarsimV3Backend().create_runtime(
            seed=7,
            family=family,
            presentation_key=b"x" * 32,
        )
        self.addCleanup(runtime.close)
        return runtime

    def test_backend_and_cli_expose_only_the_secure_backend_name(self):
        self.assertIsInstance(build_backend("starsim-ltc-v3"), LtcStarsimV3Backend)
        parsed = build_parser().parse_args(
            ["secure-demo", "--backend", "starsim-ltc-v3"]
        )
        self.assertEqual(parsed.backend, "starsim-ltc-v3")

    def test_backend_runs_through_the_separate_secure_broker(self):
        session, client = launch_secure_episode(
            seed=7,
            family="institution_person_to_person",
            backend="starsim-ltc-v3",
            episode_secret=TEST_EPISODE_KEY,
        )
        try:
            started = {
                "manifest": client.manifest,
                "observations": client.initial_observations(),
            }
            self.assertEqual(len(started["manifest"]["hypothesis_catalog"]), 6)
            serialized = json.dumps(started, sort_keys=True)
            self.assertNotIn("private_metadata", serialized)
            self.assertNotIn("opening_snapshot", serialized)
        finally:
            session.close()

    def test_secure_admin_can_return_score_with_terminal_replay(self):
        session, client = launch_secure_episode(
            seed=7,
            family="restaurant_point_source",
            backend="starsim-ltc-v3",
            episode_secret=TEST_EPISODE_KEY,
        )
        try:
            self.assertTrue(client.initial_observations())
            terminal = session.score_with_replay({})
            self.assertEqual(set(terminal), {"scorecard", "replay_trace"})
            self.assertFalse(terminal["scorecard"]["valid"])
            trace = terminal["replay_trace"]
            self.assertEqual(
                validate_replay_trace(
                    trace, require_complete_control_timeline=True
                ),
                trace,
            )
            self.assertEqual(
                set(trace["frames"][0]["effective_controls"].values()),
                {"off"},
            )
        finally:
            client.close()
            session.close()

    def test_start_is_role_aware_but_contains_no_private_facility_state(self):
        runtime = self.runtime()
        controller = TrustedEpisodeController(runtime)
        started = controller.public_call("start", {})
        self.assertEqual(len(started["manifest"]["hypothesis_catalog"]), 6)
        searchable = controller.public_call(
            "search_observations", {"kind": None, "filters": {}}
        )
        contextual = [
            observation
            for observation in searchable
            if observation["kind"] == "encounter"
            and "facility_role" in observation["payload"]
        ]
        self.assertTrue(contextual)
        self.assertTrue(
            all(
                observation["payload"]["facility_role"]
                in {"resident", "staff", "visitor"}
                and observation["payload"]["ward_id"].startswith("ward_")
                for observation in contextual
            )
        )
        serialized = json.dumps(
            {"start": started, "searchable": searchable}, sort_keys=True
        )
        for private_fragment in (
            "resident-",
            "staff-",
            "visitor-",
            "ward-",
            "room-",
            "contact-",
            "shift-",
            "meal-",
            "entry-",
            "private_metadata",
            "scheduled_exposures",
            "scenario_commitment",
            "manifest_sha256",
            "opening_snapshot",
            "authentication_tag",
        ):
            self.assertNotIn(private_fragment, serialized)

    def test_active_and_shadow_have_identical_full_opening_snapshots(self):
        runtime = self.runtime("restaurant_point_source")
        self.assertEqual(
            runtime._active.private_snapshot(),  # evaluator-only assertion
            runtime._shadow.private_snapshot(),
        )

    def test_source_control_is_routed_to_the_source_hook(self):
        runtime = self.runtime("restaurant_point_source")
        target = runtime._stream.food_service_id
        receipt = runtime.apply_response_control(
            "source_control", "standard", target, 0
        )
        self.assertEqual(receipt.status, "scheduled")
        self.assertEqual(receipt.effective_at_minute, 360)
        runtime.advance_to(360)
        oracle = runtime.finalize()
        self.assertEqual(
            oracle.counterfactual_metrics["source_control_state_changes"], 1
        )
        self.assertLessEqual(
            oracle.counterfactual_metrics["realized_active_infections"],
            oracle.counterfactual_metrics["counterfactual_no_action_infections"],
        )

    def test_terminal_replay_is_model_specific_and_aggregate_only(self):
        runtime = self.runtime("restaurant_point_source")
        controller = TrustedEpisodeController(runtime)
        started = controller.public_call("start", {})
        policy = next(
            item for item in started["observations"] if item["kind"] == "policy"
        )
        target_id = policy["payload"]["response_control_catalog"][
            "source_control"
        ]["target_id"]
        evidence_id = started["observations"][0]["observation_id"]

        receipt = controller.public_call(
            "set_response_control",
            {
                "action_type": "source_control",
                "level": "standard",
                "target_id": target_id,
                "evidence_ids": [evidence_id],
            },
        )
        self.assertEqual(receipt["effective_at_minute"], 360)
        controller.public_call("advance_time", {"minutes": 360})
        terminal = controller.score_with_replay({})

        self.assertEqual(set(terminal), {"scorecard", "replay_trace"})
        trace = terminal["replay_trace"]
        self.assertEqual(
            [frame["minute"] for frame in trace["frames"]],
            list(range(0, trace["frames"][-1]["minute"] + 1, 360)),
        )
        self.assertEqual(
            trace["frames"][0]["effective_controls"]["source_control"],
            "off",
        )
        self.assertEqual(
            trace["frames"][1]["effective_controls"]["source_control"],
            "standard",
        )
        self.assertLess(
            trace["frames"][-1]["active_cumulative_infections"],
            trace["frames"][-1]["no_action_cumulative_infections"],
        )
        self.assertEqual(
            trace["agent_events"][0],
            {
                "sequence": 1,
                "minute": 0,
                "event_type": "set_response_control",
                "status": "scheduled",
                "records_returned": 0,
                "action_type": "source_control",
                "level": "standard",
                "effective_at_minute": 360,
            },
        )
        serialized = json.dumps(trace, sort_keys=True)
        for prohibited in (
            "target_id",
            "evidence_ids",
            "transmission_events",
            "causal_mode",
            "random_seed",
        ):
            self.assertNotIn(prohibited, serialized)

    def test_same_episode_no_action_projection_is_fixed_but_policy_trace_changes(self):
        presentation_key = b"same-private-episode-secret-0001"
        baseline_runtime = LtcStarsimV3Backend().create_runtime(
            seed=7,
            family="restaurant_point_source",
            presentation_key=presentation_key,
        )
        controlled_runtime = LtcStarsimV3Backend().create_runtime(
            seed=7,
            family="restaurant_point_source",
            presentation_key=presentation_key,
        )
        self.addCleanup(baseline_runtime.close)
        self.addCleanup(controlled_runtime.close)
        baseline = TrustedEpisodeController(baseline_runtime)
        controlled = TrustedEpisodeController(controlled_runtime)
        baseline.public_call("start", {})
        started = controlled.public_call("start", {})
        policy = next(
            item for item in started["observations"] if item["kind"] == "policy"
        )
        target_id = policy["payload"]["response_control_catalog"][
            "source_control"
        ]["target_id"]
        evidence_id = started["observations"][0]["observation_id"]
        controlled.public_call(
            "set_response_control",
            {
                "action_type": "source_control",
                "level": "standard",
                "target_id": target_id,
                "evidence_ids": [evidence_id],
            },
        )

        baseline_trace = baseline.score_with_replay({})["replay_trace"]
        controlled_trace = controlled.score_with_replay({})["replay_trace"]

        def projection(trace, branch):
            return [
                (
                    frame["minute"],
                    frame[f"{branch}_currently_infected"],
                    frame[f"{branch}_cumulative_infections"],
                    frame[f"{branch}_reporting_artifacts"],
                )
                for frame in trace["frames"]
            ]

        self.assertEqual(
            projection(baseline_trace, "no_action"),
            projection(controlled_trace, "no_action"),
        )
        self.assertEqual(
            projection(baseline_trace, "active"),
            projection(baseline_trace, "no_action"),
        )
        self.assertNotEqual(
            projection(controlled_trace, "active"),
            projection(baseline_trace, "active"),
        )
        self.assertEqual(baseline_trace["agent_events"], [])
        self.assertNotEqual(
            controlled_trace["agent_events"], baseline_trace["agent_events"]
        )

    def test_rejected_calls_are_sanitized_in_chronological_replay_order(self):
        runtime = self.runtime("restaurant_point_source")
        controller = TrustedEpisodeController(runtime)
        controller.public_call("start", {})

        rejected_calls = (
            (
                "set_response_control",
                {
                    "action_type": "secret_model_action",
                    "level": "secret_model_level",
                    "target_id": "secret_target_id",
                    "evidence_ids": ["secret_evidence_id"],
                },
            ),
            (
                "set_response_control",
                {
                    "action_type": "source_control",
                    "level": "intensive",
                    "target_id": "secret invalid target!",
                    "evidence_ids": ["secret_finite_evidence"],
                },
            ),
            (
                "set_institution_control",
                {
                    "level": "secret_second_level",
                    "target_id": "secret_second_target",
                    "evidence_ids": ["secret_second_evidence"],
                },
            ),
            (
                "recommend_action",
                {
                    "action_type": "secret recommendation!",
                    "target_id": "secret_third_target",
                    "evidence_ids": ["secret_third_evidence"],
                },
            ),
        )
        for method, params in rejected_calls:
            with self.assertRaisesRegex(PublicRequestRejected, "request rejected"):
                controller.public_call(method, params)
        controller.public_call("get_clock_and_budget", {})

        trace = controller.score_with_replay({})["replay_trace"]
        self.assertEqual(
            [event["event_type"] for event in trace["agent_events"]],
            [
                "set_response_control",
                "set_response_control",
                "set_institution_control",
                "recommend_action",
                "get_clock_and_budget",
            ],
        )
        self.assertEqual(
            [event["sequence"] for event in trace["agent_events"]],
            [1, 2, 3, 4, 5],
        )
        self.assertEqual(
            (
                trace["agent_events"][0]["status"],
                trace["agent_events"][0]["action_type"],
                trace["agent_events"][0]["level"],
            ),
            ("denied", "other", "other"),
        )
        self.assertEqual(
            (
                trace["agent_events"][1]["action_type"],
                trace["agent_events"][1]["level"],
            ),
            ("source_control", "intensive"),
        )
        self.assertEqual(trace["agent_events"][1]["status"], "denied")
        self.assertEqual(
            (
                trace["agent_events"][2]["action_type"],
                trace["agent_events"][2]["level"],
            ),
            ("infection_control", "other"),
        )
        self.assertEqual(trace["agent_events"][3]["action_type"], "other")
        for frame in trace["frames"]:
            self.assertEqual(set(frame["effective_controls"].values()), {"off"})
        serialized = json.dumps(trace, sort_keys=True)
        for secret in (
            "secret_model_action",
            "secret_model_level",
            "secret_target_id",
            "secret_evidence_id",
            "secret invalid target!",
            "secret_finite_evidence",
            "secret_second_level",
            "secret_second_target",
            "secret_second_evidence",
            "secret recommendation!",
            "secret_third_target",
            "secret_third_evidence",
        ):
            self.assertNotIn(secret, serialized)

    def test_expected_environment_rejections_are_sanitized_replay_events(self):
        runtime = self.runtime("restaurant_point_source")
        controller = TrustedEpisodeController(runtime)
        controller.public_call("start", {})
        clock = controller.public_call("get_clock_and_budget", {})

        with self.assertRaises(DeadlineExceededError):
            controller.public_call(
                "advance_time", {"minutes": clock["deadline_minute"] + 360}
            )
        for _ in range(clock["remaining"]["tool_calls"]):
            controller.public_call("get_clock_and_budget", {})
        with self.assertRaises(BudgetExceededError):
            controller.public_call("get_clock_and_budget", {})

        trace = controller.score_with_replay({})["replay_trace"]
        denied = [
            event for event in trace["agent_events"] if event["status"] == "denied"
        ]
        self.assertEqual(
            [event["event_type"] for event in denied],
            ["advance_time", "get_clock_and_budget"],
        )
        self.assertTrue(
            all(
                event["action_type"] is None
                and event["level"] is None
                and event["effective_at_minute"] is None
                for event in denied
            )
        )
        for frame in trace["frames"]:
            self.assertEqual(set(frame["effective_controls"].values()), {"off"})

    def test_ordinary_score_does_not_return_replay(self):
        runtime = self.runtime("restaurant_point_source")
        controller = TrustedEpisodeController(runtime)
        controller.public_call("start", {})
        scorecard = controller.score({})
        self.assertEqual(
            set(scorecard),
            {"valid", "total", "dimensions", "metrics", "violations"},
        )
        self.assertNotIn("replay_trace", json.dumps(scorecard, sort_keys=True))

    def test_each_supported_family_is_scored_from_realized_trace_facts(self):
        expected = {
            "institution_person_to_person": "propagated",
            "restaurant_point_source": "common_source",
            "repeated_introduction": "repeated_introduction",
            "coincidental_venue": "sporadic_background",
            "reporting_artifact": "reporting_artifact",
        }
        for family, explanation in expected.items():
            with self.subTest(family=family):
                runtime = LtcStarsimV3Backend().create_runtime(
                    seed=7,
                    family=family,
                    presentation_key=b"ltc-v3-family-test-key-00000001",
                )
                try:
                    self.assertEqual(runtime.finalize().explanation_type, explanation)
                finally:
                    runtime.close()

    def test_background_nuisance_count_is_independent_of_family(self):
        counts = set()
        for family in (
            "institution_person_to_person",
            "restaurant_point_source",
            "repeated_introduction",
            "coincidental_venue",
            "reporting_artifact",
        ):
            runtime = LtcStarsimV3Backend().create_runtime(
                seed=11,
                family=family,
                presentation_key=b"ltc-v3-nuisance-test-key-0000001",
            )
            try:
                counts.add(runtime._stream._background_episode_count)
            finally:
                runtime.close()
        self.assertEqual(len(counts), 1)


if __name__ == "__main__":
    unittest.main()
