from __future__ import annotations

import importlib.util
import json
import unittest

from epiagentbench.baseline import run_scripted_baseline
from epiagentbench.models import Budget, Observation, Oracle, PublicEpisode
from epiagentbench.trusted.controller import TrustedEpisodeController
from epiagentbench.trusted.live_starsim_runtime import trace_prefix
from epiagentbench.trusted.runtime import RuntimeInterventionReceipt
from epiagentbench.trusted.service import launch_secure_episode
from epiagentbench.trusted.starsim_episode import (
    LIVE_ALERT_COUNT_BANDS,
    LIVE_ALERT_COUNT_STRATA,
    StarsimSurveillanceBackend,
    _keyed_private_seed,
    _live_alert_count_stratum,
    _public_alert_admissible,
)


HAS_STARSIM = importlib.util.find_spec("starsim") is not None
DAY_MINUTES = 24 * 60
CONTROL_CYCLE_MINUTES = 6 * 60
INTERACTION_MINUTES = 5 * DAY_MINUTES
PRESENTATION_KEY = b"closed-loop-test-presentation-key"


class SpyClosedLoopRuntime:
    """Dependency-free runtime double for controller state-machine tests."""

    target_id = "site_closedloop001"
    evidence_id = "obs_alert001"
    response_targets = {
        "infection_control": target_id,
        "source_control": "source_closedloop001",
        "entry_control": "entry_closedloop001",
        "audit_reporting": "reporting_closedloop001",
    }

    def __init__(self) -> None:
        policy = Observation(
            observation_id="obs_policy001",
            kind="policy",
            subject_id=None,
            available_minute=0,
            release_key="initial",
            payload={
                "role": "local_epidemiologist",
                "permitted": [
                    "monitor",
                    "audit_reporting",
                    "request_inspection",
                    "infection_control",
                    "source_control",
                    "entry_control",
                    "notify_health_officer",
                ],
                "requires_approval": ["public_alert"],
                "prohibited": [
                    "close_business",
                    "publish_pii",
                    "quarantine_person",
                ],
                "intervention_levels": ["off", "standard", "intensive"],
                "intervention_review_minutes": CONTROL_CYCLE_MINUTES,
                "intervention_target_id": self.target_id,
                "response_control_catalog": {
                    action_type: {
                        "target_id": target_id,
                        "levels": ["off", "standard", "intensive"],
                        "review_minutes": CONTROL_CYCLE_MINUTES,
                        "burden_per_day": {
                            "off": 0.0,
                            "standard": 1.0,
                            "intensive": 2.0,
                        },
                        "setup_credits": {
                            "off": 2,
                            "standard": 10,
                            "intensive": 20,
                        },
                        "description": f"Public {action_type} control.",
                    }
                    for action_type, target_id in self.response_targets.items()
                },
                "forecast_target": "new_encounters",
                "forecast_horizon_minutes": DAY_MINUTES,
                "forecast_minimum_submissions": 2,
                "forecast_review_minutes": DAY_MINUTES,
                "forecast_scoring_rule": "symmetric_log_gaussian_base_2",
            },
        )
        alert = Observation(
            observation_id=self.evidence_id,
            kind="alert",
            subject_id=self.target_id,
            available_minute=0,
            release_key="initial",
            payload={
                "syndrome": "acute_gastrointestinal",
                "observed_count": 8,
                "historical_expected": 2,
                "window_days": 7,
                "message": "A statistical alert requires verification.",
            },
        )
        self._public_episode = PublicEpisode(
            manifest={
                "episode_id": "episode_closedloop001",
                "schema_version": "1.0",
                "role": "local_epidemiologist",
                "start_time": "2032-04-09T09:00:00+00:00",
                "deadline": "2032-04-14T09:00:00+00:00",
                "initial_alert_ids": [alert.observation_id],
                "objectives": ["investigate", "respond", "handoff"],
                "budgets": Budget(
                    tool_calls=100,
                    analyst_minutes=2_000,
                    operational_credits=200,
                    privacy_units=100,
                ).as_dict(),
                "policy_pack": policy.observation_id,
                "enabled_tools": [
                    "search_observations",
                    "advance_time",
                    "set_institution_control",
                    "set_response_control",
                    "submit_forecast",
                    "recommend_action",
                    "get_clock_and_budget",
                ],
            },
            observations=(alert, policy),
        )
        self.current_public_minute = 0
        self.requested_level = "off"
        self.sequence = 0
        self.advance_calls: list[int] = []
        self.control_calls: list[tuple[str, str | None, int]] = []
        self.response_control_calls: list[
            tuple[str, str, str, int]
        ] = []
        self.response_levels = {
            action_type: "off" for action_type in self.response_targets
        }
        self.state_changes: list[tuple[int, str]] = []
        self.closed = False

        # Deliberately private-looking state. Controller responses must be
        # assembled from the public episode and receipts, never this object.
        self.random_seed = 918273
        self.private_config = {"beta": 0.9, "transmission_multiplier": 0.2}
        self.shadow_data = {"infections": 999}

    @property
    def public_episode(self) -> PublicEpisode:
        return self._public_episode

    @property
    def canary_tokens(self) -> tuple[str, ...]:
        return ("EAB-CANARY-SPY-PRIVATE",)

    def advance_to(self, public_minute: int) -> tuple[Observation, ...]:
        if not self.current_public_minute <= public_minute <= INTERACTION_MINUTES:
            raise ValueError("invalid fake runtime time")
        self.current_public_minute = public_minute
        self.advance_calls.append(public_minute)
        return ()

    def apply_institution_control(
        self,
        level: str,
        target_id: str | None,
        public_minute: int,
    ) -> RuntimeInterventionReceipt:
        self.control_calls.append((level, target_id, public_minute))
        if target_id != self.target_id or public_minute != self.current_public_minute:
            raise ValueError("invalid fake runtime control")
        if level == self.requested_level:
            return RuntimeInterventionReceipt(
                status="no_change",
                intervention_id=None,
                effective_at_minute=None,
                level=level,
            )

        self.sequence += 1
        effective_at = (
            public_minute // CONTROL_CYCLE_MINUTES + 1
        ) * CONTROL_CYCLE_MINUTES
        self.requested_level = level
        self.state_changes.append((effective_at, level))
        observation = Observation(
            observation_id=f"obs_intervention{self.sequence:03d}",
            kind="intervention_status",
            subject_id=self.target_id,
            available_minute=effective_at,
            release_key="stream",
            payload={
                "institution_id": self.target_id,
                "sequence": self.sequence,
                "level": level,
                "status": "effective",
                "effective_at_minute": effective_at,
            },
        )
        return RuntimeInterventionReceipt(
            status="scheduled",
            intervention_id=f"intv_spy{self.sequence:03d}",
            effective_at_minute=effective_at,
            level=level,
            observations=(observation,),
        )

    def apply_response_control(
        self,
        action_type: str,
        level: str,
        target_id: str,
        public_minute: int,
    ) -> RuntimeInterventionReceipt:
        self.response_control_calls.append(
            (action_type, level, target_id, public_minute)
        )
        if (
            self.response_targets.get(action_type) != target_id
            or public_minute != self.current_public_minute
        ):
            raise ValueError("invalid fake runtime response control")
        if self.response_levels[action_type] == level:
            return RuntimeInterventionReceipt(
                status="no_change",
                intervention_id=None,
                effective_at_minute=None,
                level=level,
            )
        self.sequence += 1
        effective_at = (
            public_minute // CONTROL_CYCLE_MINUTES + 1
        ) * CONTROL_CYCLE_MINUTES
        self.response_levels[action_type] = level
        return RuntimeInterventionReceipt(
            status="scheduled",
            intervention_id=f"intv_response{self.sequence:03d}",
            effective_at_minute=effective_at,
            level=level,
        )

    def finalize(self) -> Oracle:
        return Oracle(
            family="institution_person_to_person_closed_loop",
            is_outbreak=False,
            true_case_ids=frozenset(),
            explanation_type="propagated",
            source_id=self.target_id,
            decisive_evidence_ids=frozenset({self.evidence_id}),
            action_utilities={
                ("monitor", None): 0.0,
                ("infection_control", self.target_id): 0.0,
            },
            canary_tokens=self.canary_tokens,
        )

    def close(self) -> None:
        self.closed = True


class ClosedLoopControllerTests(unittest.TestCase):
    def make_controller(
        self,
    ) -> tuple[SpyClosedLoopRuntime, TrustedEpisodeController, dict]:
        runtime = SpyClosedLoopRuntime()
        controller = TrustedEpisodeController(runtime)
        self.addCleanup(controller.close)
        started = controller.public_call("start", {})
        return runtime, controller, started

    @staticmethod
    def set_control(
        controller: TrustedEpisodeController,
        level: str,
        target_id: str,
        evidence_ids: list[str],
    ) -> dict:
        return controller.public_call(
            "set_institution_control",
            {
                "level": level,
                "target_id": target_id,
                "evidence_ids": evidence_ids,
            },
        )

    def test_control_receipt_is_time_gated_until_effective(self):
        runtime, controller, _ = self.make_controller()

        receipt = self.set_control(
            controller,
            "standard",
            runtime.target_id,
            [runtime.evidence_id],
        )
        self.assertEqual(receipt["status"], "scheduled")
        self.assertEqual(receipt["effective_at_minute"], CONTROL_CYCLE_MINUTES)
        self.assertEqual(
            controller.public_call(
                "search_observations",
                {"kind": "intervention_status", "filters": {}},
            ),
            [],
        )
        self.assertEqual(
            controller.public_call(
                "advance_time", {"minutes": CONTROL_CYCLE_MINUTES - 1}
            ),
            [],
        )
        self.assertEqual(
            controller.public_call(
                "search_observations",
                {"kind": "intervention_status", "filters": {}},
            ),
            [],
        )

        released = controller.public_call("advance_time", {"minutes": 1})
        self.assertEqual(len(released), 1)
        self.assertEqual(released[0]["kind"], "intervention_status")
        self.assertEqual(released[0]["payload"]["level"], "standard")
        self.assertEqual(
            released[0]["available_minute"], CONTROL_CYCLE_MINUTES
        )

    def test_generic_response_control_uses_catalog_target_and_canonical_ledger(self):
        runtime, controller, started = self.make_controller()
        catalog = started["observations"][1]["payload"][
            "response_control_catalog"
        ]
        target_id = catalog["source_control"]["target_id"]

        receipt = controller.public_call(
            "set_response_control",
            {
                "action_type": "source_control",
                "level": "standard",
                "target_id": target_id,
                "evidence_ids": [runtime.evidence_id],
            },
        )

        self.assertEqual(
            receipt,
            {
                "status": "scheduled",
                "intervention_id": "intv_response001",
                "effective_at_minute": CONTROL_CYCLE_MINUTES,
                "action_type": "source_control",
                "target_id": target_id,
                "level": "standard",
                "violation": None,
                "unseen": [],
            },
        )
        self.assertEqual(
            runtime.response_control_calls,
            [("source_control", "standard", target_id, 0)],
        )
        entry = controller._environment.ledger[-1]
        self.assertEqual(entry.tool, "set_response_control")
        self.assertEqual(entry.arguments["action_type"], "source_control")

    def test_generic_response_control_rejects_wrong_target_before_runtime(self):
        runtime, controller, _ = self.make_controller()
        receipt = controller.public_call(
            "set_response_control",
            {
                "action_type": "entry_control",
                "level": "intensive",
                "target_id": runtime.response_targets["source_control"],
                "evidence_ids": [runtime.evidence_id],
            },
        )

        self.assertEqual(receipt["status"], "unsupported")
        self.assertEqual(receipt["violation"], "unseen_target")
        self.assertEqual(runtime.response_control_calls, [])

    def test_standard_intensive_off_transitions_and_duplicates_are_idempotent(self):
        runtime, controller, _ = self.make_controller()
        evidence = [runtime.evidence_id]

        standard = self.set_control(
            controller, "standard", runtime.target_id, evidence
        )
        duplicate_standard = self.set_control(
            controller, "standard", runtime.target_id, evidence
        )
        controller.public_call(
            "advance_time", {"minutes": CONTROL_CYCLE_MINUTES}
        )
        intensive = self.set_control(
            controller, "intensive", runtime.target_id, evidence
        )
        duplicate_intensive = self.set_control(
            controller, "intensive", runtime.target_id, evidence
        )
        controller.public_call(
            "advance_time", {"minutes": CONTROL_CYCLE_MINUTES}
        )
        off = self.set_control(controller, "off", runtime.target_id, evidence)
        duplicate_off = self.set_control(
            controller, "off", runtime.target_id, evidence
        )

        self.assertEqual(
            [standard["status"], intensive["status"], off["status"]],
            ["scheduled", "scheduled", "scheduled"],
        )
        self.assertEqual(
            [
                duplicate_standard["status"],
                duplicate_intensive["status"],
                duplicate_off["status"],
            ],
            ["no_change", "no_change", "no_change"],
        )
        self.assertEqual(
            runtime.state_changes,
            [
                (360, "standard"),
                (720, "intensive"),
                (1080, "off"),
            ],
        )
        self.assertEqual(runtime.sequence, 3)
        self.assertEqual(runtime.requested_level, "off")
        self.assertEqual(
            len(
                {
                    standard["intervention_id"],
                    intensive["intervention_id"],
                    off["intervention_id"],
                }
            ),
            3,
        )
        self.assertIsNone(duplicate_standard["intervention_id"])
        self.assertIsNone(duplicate_intensive["intervention_id"])
        self.assertIsNone(duplicate_off["intervention_id"])

    def test_wrong_target_and_missing_evidence_never_call_or_mutate_runtime(self):
        runtime, controller, _ = self.make_controller()

        missing_evidence = self.set_control(
            controller, "standard", runtime.target_id, []
        )
        wrong_target = self.set_control(
            controller,
            "intensive",
            "site_notobserved001",
            [runtime.evidence_id],
        )

        self.assertEqual(missing_evidence["status"], "unsupported")
        self.assertEqual(
            missing_evidence["violation"], "missing_action_evidence"
        )
        self.assertEqual(wrong_target["status"], "unsupported")
        self.assertEqual(wrong_target["violation"], "unseen_target")
        self.assertEqual(runtime.control_calls, [])
        self.assertEqual(runtime.advance_calls, [])
        self.assertEqual(runtime.state_changes, [])
        self.assertEqual(runtime.requested_level, "off")
        self.assertEqual(runtime.current_public_minute, 0)

    def test_public_responses_do_not_serialize_private_runtime_state(self):
        runtime, controller, started = self.make_controller()
        receipt = self.set_control(
            controller,
            "standard",
            runtime.target_id,
            [runtime.evidence_id],
        )
        released = controller.public_call(
            "advance_time", {"minutes": CONTROL_CYCLE_MINUTES}
        )
        clock = controller.public_call("get_clock_and_budget", {})

        serialized = json.dumps(
            {
                "started": started,
                "receipt": receipt,
                "released": released,
                "clock": clock,
            },
            sort_keys=True,
        )
        for forbidden in (
            "918273",
            "random_seed",
            "private_config",
            "beta",
            "transmission_multiplier",
            "shadow_data",
            "infections\": 999",
            "EAB-CANARY-SPY-PRIVATE",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, serialized)

    def test_live_admission_rule_reads_only_the_public_time_zero_alert(self):
        runtime = SpyClosedLoopRuntime()
        self.assertTrue(_public_alert_admissible(runtime.public_episode))
        self.assertTrue(
            _public_alert_admissible(runtime.public_episode, "low")
        )
        self.assertTrue(
            _public_alert_admissible(runtime.public_episode, "middle")
        )
        self.assertFalse(
            _public_alert_admissible(runtime.public_episode, "high")
        )

        alert, policy = runtime.public_episode.observations
        low_alert = Observation(
            observation_id=alert.observation_id,
            kind=alert.kind,
            subject_id=alert.subject_id,
            available_minute=alert.available_minute,
            release_key=alert.release_key,
            payload={**alert.payload, "observed_count": 3},
        )
        public = PublicEpisode(
            manifest=runtime.public_episode.manifest,
            observations=(low_alert, policy),
        )
        self.assertFalse(_public_alert_admissible(public))

    def test_alert_count_stratum_is_keyed_separately_from_growth(self):
        key = b"independent-public-covariate-key-001"
        assignments = {
            (
                _keyed_private_seed(
                    key, seed, "closed-loop-growth-regime"
                )
                % 3,
                LIVE_ALERT_COUNT_STRATA.index(
                    _live_alert_count_stratum(key, seed)
                ),
            )
            for seed in range(256)
        }

        # All cross-stratum combinations occur under this fixed replay key;
        # admission-band choice is not a relabeling of the growth stratum.
        self.assertEqual(len(assignments), 9)
        sequence = tuple(
            _live_alert_count_stratum(key, seed) for seed in range(32)
        )
        self.assertEqual(
            sequence,
            tuple(_live_alert_count_stratum(key, seed) for seed in range(32)),
        )
        self.assertNotEqual(
            sequence,
            tuple(
                _live_alert_count_stratum(
                    b"independent-public-covariate-key-002", seed
                )
                for seed in range(32)
            ),
        )

    def test_forecasts_are_committed_prospectively_and_rate_limited(self):
        runtime, controller, _ = self.make_controller()
        del runtime

        first = controller.public_call(
            "submit_forecast", {"expected_new_encounters": 7}
        )
        too_soon = controller.public_call(
            "submit_forecast", {"expected_new_encounters": 4}
        )
        controller.public_call(
            "advance_time", {"minutes": DAY_MINUTES}
        )
        second = controller.public_call(
            "submit_forecast", {"expected_new_encounters": 4}
        )

        self.assertEqual(first["status"], "submitted")
        self.assertEqual(first["forecast_minute"], 0)
        self.assertEqual(first["horizon_minutes"], DAY_MINUTES)
        self.assertEqual(too_soon["status"], "too_soon")
        self.assertEqual(second["status"], "submitted")
        self.assertEqual(second["forecast_minute"], DAY_MINUTES)
        for result in (first, too_soon, second):
            self.assertNotIn("actual", result)


@unittest.skipUnless(HAS_STARSIM, "install the starsim extra")
class ClosedLoopStarsimTests(unittest.TestCase):
    def make_runtime(self, *, seed: int = 7, key: bytes = PRESENTATION_KEY):
        runtime = StarsimSurveillanceBackend().create_runtime(
            seed=seed,
            family="institution_person_to_person",
            presentation_key=key,
        )
        self.addCleanup(runtime.close)
        return runtime

    @staticmethod
    def target_id(runtime) -> str:
        policy = next(
            observation
            for observation in runtime.public_episode.observations
            if observation.kind == "policy"
        )
        return policy.payload["intervention_target_id"]

    def test_same_seed_is_deterministic(self):
        first = self.make_runtime()
        second = self.make_runtime()

        self.assertEqual(first.public_episode, second.public_episode)
        self.assertEqual(first.growth_regime, second.growth_regime)
        self.assertEqual(first.advance_to(720), second.advance_to(720))
        self.assertEqual(
            first._active.oracle_snapshot().transmission_events,
            second._active.oracle_snapshot().transmission_events,
        )
        self.assertEqual(
            first._stream.all_observations, second._stream.all_observations
        )

    def test_secret_presentation_key_also_keys_private_trajectories(self):
        first = self.make_runtime(key=b"private-trajectory-key-number-0001")
        second = self.make_runtime(key=b"private-trajectory-key-number-0002")

        self.assertNotEqual(
            first._config.random_seed,
            second._config.random_seed,
        )

    def test_public_only_admission_includes_coherent_false_alerts(self):
        seed = 4
        key = b"eab-live-policy-panel-key-0001"
        runtime = self.make_runtime(
            seed=seed,
            key=key,
        )
        alert = next(
            observation
            for observation in runtime.public_episode.observations
            if observation.kind == "alert"
        )
        lower, upper = LIVE_ALERT_COUNT_BANDS[
            _live_alert_count_stratum(key, seed)
        ]
        oracle = runtime.finalize()

        self.assertLessEqual(lower, alert.payload["observed_count"])
        self.assertLessEqual(alert.payload["observed_count"], upper)
        self.assertFalse(oracle.is_outbreak)
        self.assertEqual(oracle.explanation_type, "sporadic_background")
        self.assertIsNone(oracle.source_id)

    def test_no_control_keeps_active_and_shadow_equal_and_has_zero_effect(self):
        runtime = self.make_runtime()
        runtime.advance_to(INTERACTION_MINUTES)
        self.assertEqual(
            runtime._active.oracle_snapshot().transmission_events,
            runtime._shadow.oracle_snapshot().transmission_events,
        )

        metrics = runtime.finalize().counterfactual_metrics
        self.assertEqual(
            metrics["counterfactual_no_action_infections"],
            metrics["realized_active_infections"],
        )
        self.assertEqual(metrics["counterfactual_infections_averted"], 0)
        self.assertEqual(metrics["intervention_burden"], 0.0)
        self.assertEqual(metrics["realized_intervention_utility"], 0.0)
        self.assertEqual(metrics["intervention_state_changes"], 0)

    def test_runtime_control_state_transitions_and_duplicates_are_idempotent(self):
        runtime = self.make_runtime()
        target_id = self.target_id(runtime)

        initial_off = runtime.apply_institution_control("off", target_id, 0)
        standard = runtime.apply_institution_control("standard", target_id, 0)
        duplicate_standard = runtime.apply_institution_control(
            "standard", target_id, 0
        )
        runtime.advance_to(360)
        intensive = runtime.apply_institution_control(
            "intensive", target_id, 360
        )
        duplicate_intensive = runtime.apply_institution_control(
            "intensive", target_id, 360
        )
        runtime.advance_to(720)
        off = runtime.apply_institution_control("off", target_id, 720)
        duplicate_off = runtime.apply_institution_control(
            "off", target_id, 720
        )

        self.assertEqual(initial_off.status, "no_change")
        self.assertEqual(
            [standard.status, intensive.status, off.status],
            ["scheduled", "scheduled", "scheduled"],
        )
        self.assertEqual(
            [
                duplicate_standard.status,
                duplicate_intensive.status,
                duplicate_off.status,
            ],
            ["no_change", "no_change", "no_change"],
        )
        self.assertEqual(
            [
                standard.effective_at_minute,
                intensive.effective_at_minute,
                off.effective_at_minute,
            ],
            [360, 720, 1080],
        )
        self.assertEqual(
            runtime._level_changes,
            [
                (runtime._decision_minute + 360, "standard"),
                (runtime._decision_minute + 720, "intensive"),
                (runtime._decision_minute + 1080, "off"),
            ],
        )
        self.assertEqual(runtime._intervention_sequence, 3)

    def test_same_boundary_changes_use_the_engine_sequence_for_burden(self):
        runtime = self.make_runtime(
            key=b"same-boundary-burden-test-key-001"
        )
        target_id = self.target_id(runtime)

        runtime.apply_institution_control("standard", target_id, 0)
        runtime.apply_institution_control("intensive", target_id, 0)
        metrics = runtime.finalize().counterfactual_metrics

        effective = runtime._decision_minute + CONTROL_CYCLE_MINUTES
        expected = (
            runtime._config.horizon_days * DAY_MINUTES - effective
        ) / DAY_MINUTES * 2.0
        self.assertAlmostEqual(metrics["intervention_burden"], expected)

    def test_control_changes_latent_and_public_outcomes_only_after_effective_time(self):
        controlled = self.make_runtime(key=b"causal-closed-loop-test-key-0001")
        no_control = self.make_runtime(key=b"causal-closed-loop-test-key-0001")
        self.assertEqual(controlled.public_episode, no_control.public_episode)

        receipt = controlled.apply_institution_control(
            "intensive", self.target_id(controlled), 0
        )
        self.assertEqual(receipt.effective_at_minute, 360)

        controlled_through_effective = controlled.advance_to(360)
        no_control_through_effective = no_control.advance_to(360)
        self.assertEqual(controlled_through_effective, no_control_through_effective)
        self.assertEqual(
            controlled._active.oracle_snapshot().transmission_events,
            no_control._active.oracle_snapshot().transmission_events,
        )

        controlled_created = list(controlled.advance_to(720))
        no_control_created = list(no_control.advance_to(720))
        controlled_events = controlled._active.oracle_snapshot().transmission_events
        no_control_events = no_control._active.oracle_snapshot().transmission_events
        absolute_effective = controlled._decision_minute + 360
        self.assertEqual(
            trace_prefix(controlled_events, absolute_effective),
            trace_prefix(no_control_events, absolute_effective),
        )
        self.assertNotEqual(controlled_events, no_control_events)

        for minute in range(1080, INTERACTION_MINUTES + 1, 360):
            controlled_created.extend(controlled.advance_to(minute))
            no_control_created.extend(no_control.advance_to(minute))
        self.assertNotEqual(controlled_created, no_control_created)
        self.assertNotEqual(
            controlled._stream.all_observations,
            no_control._stream.all_observations,
        )

    def test_one_twelve_hour_advance_matches_two_six_hour_advances(self):
        single = self.make_runtime(key=b"chunking-closed-loop-test-key-001")
        split = self.make_runtime(key=b"chunking-closed-loop-test-key-001")

        single_created = single.advance_to(720)
        split_created = split.advance_to(360) + split.advance_to(720)

        self.assertEqual(single_created, split_created)
        self.assertEqual(
            single._stream.all_observations, split._stream.all_observations
        )
        self.assertEqual(
            single._active.oracle_snapshot().transmission_events,
            split._active.oracle_snapshot().transmission_events,
        )

    def test_finalize_uses_fixed_horizon_even_when_called_early(self):
        early = self.make_runtime(key=b"early-finalize-closed-loop-key-01")
        advanced = self.make_runtime(key=b"early-finalize-closed-loop-key-01")

        early_oracle = early.finalize()
        advanced.advance_to(INTERACTION_MINUTES)
        advanced_oracle = advanced.finalize()

        self.assertEqual(early_oracle, advanced_oracle)
        self.assertEqual(
            early_oracle.counterfactual_metrics[
                "counterfactual_no_action_infections"
            ],
            early_oracle.counterfactual_metrics["realized_active_infections"],
        )

    def test_investigation_gold_is_frozen_before_actions_change_the_world(self):
        runtime = self.make_runtime(key=b"frozen-investigation-gold-key-001")
        expected_cases = runtime._stream.investigation_true_case_ids
        expected_evidence = (
            runtime._stream.investigation_decisive_evidence_ids
        )
        target_id = self.target_id(runtime)

        runtime.apply_institution_control("intensive", target_id, 0)
        runtime.advance_to(INTERACTION_MINUTES)
        oracle = runtime.finalize()

        self.assertEqual(oracle.true_case_ids, expected_cases)
        self.assertEqual(oracle.decisive_evidence_ids, expected_evidence)
        self.assertEqual(
            oracle.counterfactual_metrics["investigation_gold_cutoff_minute"],
            0,
        )

    def test_real_public_controller_omits_private_simulator_and_shadow_fields(self):
        runtime = self.make_runtime(key=b"public-boundary-closed-loop-key-1")
        controller = TrustedEpisodeController(runtime)
        self.addCleanup(controller.close)
        started = controller.public_call("start", {})
        target_id = next(
            record["payload"]["intervention_target_id"]
            for record in started["observations"]
            if record["kind"] == "policy"
        )
        evidence_id = started["manifest"]["initial_alert_ids"][0]
        receipt = controller.public_call(
            "set_institution_control",
            {
                "level": "standard",
                "target_id": target_id,
                "evidence_ids": [evidence_id],
            },
        )
        before = controller.public_call(
            "search_observations",
            {"kind": "intervention_status", "filters": {}},
        )
        released = controller.public_call("advance_time", {"minutes": 360})
        self.assertEqual(before, [])
        intervention_records = [
            record
            for record in released
            if record["kind"] == "intervention_status"
        ]
        self.assertEqual(len(intervention_records), 1)

        serialized = json.dumps(
            {"start": started, "receipt": receipt, "released": released},
            sort_keys=True,
        )
        for forbidden in (
            "random_seed",
            "configuration_sha256",
            "daily_transmission_hazard",
            "transmission_level",
            "growth_regime",
            "multiplier",
            "shadow",
            "counterfactual",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, serialized)

    def test_spawned_secure_action_advance_and_score_path(self):
        session, client = launch_secure_episode(
            seed=7,
            family="institution_person_to_person",
            backend="starsim",
        )
        try:
            initial = client.initial_observations()
            target_id = next(
                record["payload"]["intervention_target_id"]
                for record in initial
                if record["kind"] == "policy"
            )
            evidence_id = client.manifest["initial_alert_ids"][0]
            receipt = client.set_institution_control(
                "standard", target_id, [evidence_id]
            )
            self.assertEqual(receipt["status"], "scheduled")
            released = client.advance_time(CONTROL_CYCLE_MINUTES)
            self.assertTrue(
                any(record["kind"] == "intervention_status" for record in released)
            )

            submission = run_scripted_baseline(client)
            scorecard = session.score(submission)
            self.assertTrue(scorecard["valid"])
            self.assertEqual(
                scorecard["metrics"]["response_utility_timing_model"],
                "closed_loop_realized_trajectory",
            )
            self.assertGreaterEqual(
                scorecard["metrics"]["intervention_state_changes"], 1
            )
        finally:
            client.close()
            session.close()


if __name__ == "__main__":
    unittest.main()
