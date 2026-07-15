from __future__ import annotations

import unittest
from copy import deepcopy
from dataclasses import replace

from epiagentbench.baseline import run_scripted_baseline
from epiagentbench.environment import InvestigationEnvironment
from epiagentbench.models import LedgerEntry
from epiagentbench.scenario import generate_episode
from epiagentbench.scoring import score_episode
from epiagentbench.validation import (
    ALERT_COUNT_ONLY_POLICIES,
    CONSTANT_POLICY_SHORTCUT_THRESHOLD,
    _alert_count_policy_diagnostics,
    _constant_policy_diagnostics,
    _constant_policy_shortcut_present,
    _policy_shortcut_present,
)


class ClosedLoopRewardGuardrailTests(unittest.TestCase):
    def baseline_context(self):
        bundle = generate_episode(
            seed=13, family="institution_person_to_person"
        )
        environment = InvestigationEnvironment(bundle.public)
        submission = run_scripted_baseline(environment)
        return bundle, environment, submission

    def score_with_closed_loop_utilities(
        self,
        *,
        realized: float,
        off: float,
        best: float,
        executed_level: str | None = "standard",
    ):
        bundle, environment, submission = self.baseline_context()
        oracle = replace(
            bundle.oracle,
            counterfactual_metrics={
                "response_utility_timing_model": (
                    "closed_loop_realized_trajectory"
                ),
                "realized_intervention_utility": realized,
                "closed_loop_fixed_off_utility": off,
                "closed_loop_best_fixed_utility": best,
                "closed_loop_policy_floor": min(realized, off, best),
            },
        )
        ledger = tuple(
            entry
            for entry in environment.ledger
            if entry.tool != "recommend_action"
        )
        submission = deepcopy(submission)
        if executed_level is None:
            submission["recommended_actions"] = [
                {
                    "action_type": "monitor",
                    "target_id": None,
                    "urgency": "monitor",
                    "evidence_ids": [],
                }
            ]
            ledger += (
                LedgerEntry(
                    sequence=len(ledger) + 1,
                    simulated_minute=0,
                    tool="recommend_action",
                    arguments={
                        "action_type": "monitor",
                        "target_id": None,
                        "evidence_ids": [],
                    },
                    status="recommended",
                ),
            )
        else:
            target_id = "site_executed001"
            submission["recommended_actions"] = [
                {
                    "action_type": "infection_control",
                    "target_id": target_id,
                    "urgency": "immediate",
                    "evidence_ids": [],
                    "control_level": executed_level,
                }
            ]
            ledger += (
                LedgerEntry(
                    sequence=len(ledger) + 1,
                    simulated_minute=0,
                    tool="set_institution_control",
                    arguments={
                        "level": executed_level,
                        "target_id": target_id,
                        "evidence_ids": [],
                    },
                    status="scheduled",
                ),
            )
        return score_episode(
            oracle=oracle,
            manifest=bundle.public.manifest,
            ledger=ledger,
            seen_ids=environment.seen_ids,
            submission=submission,
        )

    def test_harmful_policy_cannot_earn_reward_from_a_worse_policy_floor(self):
        scorecard = self.score_with_closed_loop_utilities(
            realized=-5.0,
            off=0.0,
            best=10.0,
        )
        self.assertEqual(scorecard.dimensions["response_utility"], 0.0)

    def test_matching_off_gets_full_reward_when_off_is_best(self):
        scorecard = self.score_with_closed_loop_utilities(
            realized=0.0,
            off=0.0,
            best=0.0,
            executed_level=None,
        )
        self.assertEqual(scorecard.dimensions["response_utility"], 25.0)

    def test_positive_improvement_is_normalized_from_no_action(self):
        scorecard = self.score_with_closed_loop_utilities(
            realized=5.0,
            off=0.0,
            best=10.0,
        )
        self.assertEqual(scorecard.dimensions["response_utility"], 12.5)

    def test_executed_control_must_match_the_final_report(self):
        bundle, environment, baseline_submission = self.baseline_context()
        oracle = replace(
            bundle.oracle,
            counterfactual_metrics={
                "response_utility_timing_model": (
                    "closed_loop_realized_trajectory"
                ),
                "realized_intervention_utility": 10.0,
                "closed_loop_fixed_off_utility": 0.0,
                "closed_loop_best_fixed_utility": 10.0,
            },
        )
        ledger = tuple(
            entry
            for entry in environment.ledger
            if entry.tool != "recommend_action"
        ) + (
            LedgerEntry(
                sequence=len(environment.ledger) + 1,
                simulated_minute=360,
                tool="set_institution_control",
                arguments={
                    "level": "standard",
                    "target_id": "site_executed001",
                    "evidence_ids": [],
                },
                status="scheduled",
            ),
        )

        omitted = deepcopy(baseline_submission)
        omitted["recommended_actions"] = []
        omitted_score = score_episode(
            oracle=oracle,
            manifest=bundle.public.manifest,
            ledger=ledger,
            seen_ids=environment.seen_ids,
            submission=omitted,
        )
        self.assertIn("unreported_logged_action", omitted_score.violations)
        self.assertEqual(omitted_score.dimensions["response_utility"], 0.0)

        matching = deepcopy(omitted)
        matching["recommended_actions"] = [
            {
                "action_type": "infection_control",
                "target_id": "site_executed001",
                "urgency": "immediate",
                "evidence_ids": [],
                "control_level": "standard",
            }
        ]
        matching_score = score_episode(
            oracle=oracle,
            manifest=bundle.public.manifest,
            ledger=ledger,
            seen_ids=environment.seen_ids,
            submission=matching,
        )
        self.assertNotIn(
            "unlogged_recommended_action", matching_score.violations
        )
        self.assertNotIn(
            "unreported_logged_action", matching_score.violations
        )
        self.assertEqual(matching_score.dimensions["response_utility"], 25.0)

        wrong_level = deepcopy(matching)
        wrong_level["recommended_actions"][0]["control_level"] = "intensive"
        wrong_score = score_episode(
            oracle=oracle,
            manifest=bundle.public.manifest,
            ledger=ledger,
            seen_ids=environment.seen_ids,
            submission=wrong_level,
        )
        self.assertIn("control_trace_report_mismatch", wrong_score.violations)
        self.assertEqual(wrong_score.dimensions["response_utility"], 0.0)

    def test_recommending_but_not_executing_control_gets_no_response_reward(self):
        bundle, environment, submission = self.baseline_context()
        oracle = replace(
            bundle.oracle,
            counterfactual_metrics={
                "response_utility_timing_model": (
                    "closed_loop_realized_trajectory"
                ),
                "realized_intervention_utility": 0.0,
                "closed_loop_fixed_off_utility": 0.0,
                "closed_loop_best_fixed_utility": 0.0,
            },
        )

        scorecard = score_episode(
            oracle=oracle,
            manifest=bundle.public.manifest,
            ledger=environment.ledger,
            seen_ids=environment.seen_ids,
            submission=submission,
        )

        self.assertIn(
            "unexecuted_control_recommendation", scorecard.violations
        )
        self.assertEqual(scorecard.dimensions["response_utility"], 0.0)

    def test_one_executed_control_cannot_cover_an_unexecuted_second_target(self):
        bundle, environment, baseline_submission = self.baseline_context()
        oracle = replace(
            bundle.oracle,
            counterfactual_metrics={
                "response_utility_timing_model": (
                    "closed_loop_realized_trajectory"
                ),
                "realized_intervention_utility": 10.0,
                "closed_loop_fixed_off_utility": 0.0,
                "closed_loop_best_fixed_utility": 10.0,
            },
        )
        executed_target = "site_executed001"
        claimed_target = "site_claimed002"
        ledger = tuple(
            entry
            for entry in environment.ledger
            if entry.tool != "recommend_action"
        ) + (
            LedgerEntry(
                sequence=len(environment.ledger) + 1,
                simulated_minute=360,
                tool="set_institution_control",
                arguments={
                    "level": "standard",
                    "target_id": executed_target,
                    "evidence_ids": [],
                },
                status="scheduled",
            ),
            LedgerEntry(
                sequence=len(environment.ledger) + 2,
                simulated_minute=360,
                tool="recommend_action",
                arguments={
                    "action_type": "infection_control",
                    "target_id": claimed_target,
                    "evidence_ids": [],
                },
                status="recommended",
            ),
        )
        submission = deepcopy(baseline_submission)
        submission["recommended_actions"] = [
            {
                "action_type": "infection_control",
                "target_id": executed_target,
                "urgency": "immediate",
                "evidence_ids": [],
                "control_level": "standard",
            },
            {
                "action_type": "infection_control",
                "target_id": claimed_target,
                "urgency": "immediate",
                "evidence_ids": [],
                "control_level": "intensive",
            },
        ]

        scorecard = score_episode(
            oracle=oracle,
            manifest=bundle.public.manifest,
            ledger=ledger,
            seen_ids=environment.seen_ids,
            submission=submission,
        )

        self.assertIn(
            "unexecuted_control_recommendation", scorecard.violations
        )
        self.assertEqual(scorecard.dimensions["response_utility"], 0.0)

    def test_generic_execution_requires_matching_action_target_and_level(self):
        bundle, environment, baseline_submission = self.baseline_context()
        oracle = replace(
            bundle.oracle,
            counterfactual_metrics={
                "response_utility_timing_model": (
                    "closed_loop_realized_trajectory"
                ),
                "realized_intervention_utility": 10.0,
                "closed_loop_fixed_off_utility": 0.0,
                "closed_loop_best_fixed_utility": 10.0,
            },
        )
        target_id = "source_executed001"
        ledger = tuple(
            entry
            for entry in environment.ledger
            if entry.tool != "recommend_action"
        ) + (
            LedgerEntry(
                sequence=len(environment.ledger) + 1,
                simulated_minute=360,
                tool="set_response_control",
                arguments={
                    "action_type": "source_control",
                    "level": "standard",
                    "target_id": target_id,
                    "evidence_ids": [],
                },
                status="scheduled",
            ),
        )

        variants = {
            "matching": ("source_control", target_id, "standard", None),
            "wrong_action": (
                "infection_control",
                target_id,
                "standard",
                "control_trace_report_mismatch",
            ),
            "wrong_target": (
                "source_control",
                "source_claimed002",
                "standard",
                "control_trace_report_mismatch",
            ),
            "wrong_level": (
                "source_control",
                target_id,
                "intensive",
                "control_trace_report_mismatch",
            ),
        }
        for name, (action_type, action_target, level, expected_violation) in (
            variants.items()
        ):
            submission = deepcopy(baseline_submission)
            submission["recommended_actions"] = [
                {
                    "action_type": action_type,
                    "target_id": action_target,
                    "urgency": "immediate",
                    "evidence_ids": [],
                    "control_level": level,
                }
            ]
            with self.subTest(name=name):
                scorecard = score_episode(
                    oracle=oracle,
                    manifest=bundle.public.manifest,
                    ledger=ledger,
                    seen_ids=environment.seen_ids,
                    submission=submission,
                )
                if expected_violation is None:
                    self.assertNotIn(
                        "control_trace_report_mismatch",
                        scorecard.violations,
                    )
                    self.assertEqual(
                        scorecard.dimensions["response_utility"], 25.0
                    )
                else:
                    self.assertIn(expected_violation, scorecard.violations)
                    self.assertEqual(
                        scorecard.dimensions["response_utility"], 0.0
                    )

    def test_unexecuted_generic_control_claim_gets_no_response_reward(self):
        bundle, environment, baseline_submission = self.baseline_context()
        oracle = replace(
            bundle.oracle,
            counterfactual_metrics={
                "response_utility_timing_model": (
                    "closed_loop_realized_trajectory"
                ),
                "realized_intervention_utility": 10.0,
                "closed_loop_fixed_off_utility": 0.0,
                "closed_loop_best_fixed_utility": 10.0,
            },
        )
        target_id = "entry_claimed001"
        ledger = tuple(
            entry
            for entry in environment.ledger
            if entry.tool != "recommend_action"
        ) + (
            LedgerEntry(
                sequence=len(environment.ledger) + 1,
                simulated_minute=360,
                tool="recommend_action",
                arguments={
                    "action_type": "entry_control",
                    "target_id": target_id,
                    "evidence_ids": [],
                },
                status="recommended",
            ),
        )
        manifest = deepcopy(dict(bundle.public.manifest))
        manifest["enabled_tools"] = list(manifest["enabled_tools"]) + [
            "set_response_control"
        ]
        submission = deepcopy(baseline_submission)
        submission["recommended_actions"] = [
            {
                "action_type": "entry_control",
                "target_id": target_id,
                "urgency": "immediate",
                "evidence_ids": [],
                "control_level": "standard",
            }
        ]

        scorecard = score_episode(
            oracle=oracle,
            manifest=manifest,
            ledger=ledger,
            seen_ids=environment.seen_ids,
            submission=submission,
        )

        self.assertIn(
            "unexecuted_control_recommendation", scorecard.violations
        )
        self.assertEqual(scorecard.dimensions["response_utility"], 0.0)

    def test_constant_policy_shortcut_uses_expected_reward_not_argmax_count(self):
        rows = [
            {
                "fixed_policy_utilities": {
                    "off": 0.0,
                    "standard": 10.0,
                    "intensive": 8.0,
                }
            },
            {
                "fixed_policy_utilities": {
                    "off": 0.0,
                    "standard": 9.0,
                    "intensive": 10.0,
                }
            },
        ]
        diagnostics = _constant_policy_diagnostics(rows)

        self.assertEqual(
            diagnostics["standard"]["mean_normalized_response_score"],
            0.95,
        )
        self.assertEqual(
            diagnostics["standard"]["mean_regret_vs_best_fixed"], 0.5
        )
        self.assertEqual(
            diagnostics["standard"]["harm_rate_below_no_action"], 0.0
        )
        self.assertEqual(diagnostics["standard"]["worst_utility"], 9.0)
        self.assertGreaterEqual(
            diagnostics["standard"]["mean_normalized_response_score"],
            CONSTANT_POLICY_SHORTCUT_THRESHOLD,
        )
        self.assertTrue(_constant_policy_shortcut_present(diagnostics))

    def test_preregistered_alert_count_policy_is_a_shortcut_guardrail(self):
        rows = [
            {
                "initial_alert_count": 8,
                "fixed_policy_utilities": {
                    "off": 0.0,
                    "standard": -2.0,
                    "intensive": -5.0,
                },
            },
            {
                "initial_alert_count": 11,
                "fixed_policy_utilities": {
                    "off": 0.0,
                    "standard": 4.0,
                    "intensive": 2.0,
                },
            },
            {
                "initial_alert_count": 20,
                "fixed_policy_utilities": {
                    "off": 0.0,
                    "standard": 8.0,
                    "intensive": 10.0,
                },
            },
        ]

        diagnostics = _alert_count_policy_diagnostics(rows)

        self.assertIn("alert_triage_10_12", ALERT_COUNT_ONLY_POLICIES)
        self.assertEqual(
            diagnostics["alert_triage_10_12"][
                "mean_normalized_response_score"
            ],
            1.0,
        )
        self.assertTrue(_policy_shortcut_present(diagnostics))

    def test_forecasts_are_scored_only_from_timestamped_commitments(self):
        bundle, environment, submission = self.baseline_context()
        oracle = replace(
            bundle.oracle,
            counterfactual_metrics={
                "response_utility_timing_model": (
                    "closed_loop_realized_trajectory"
                ),
                "realized_intervention_utility": 0.0,
                "closed_loop_fixed_off_utility": 0.0,
                "closed_loop_best_fixed_utility": 0.0,
            },
            forecast_event_minutes=(720, 1500, 1800),
            forecast_horizon_minutes=1440,
            forecast_minimum_submissions=2,
        )
        ledger = environment.ledger + (
            LedgerEntry(
                sequence=len(environment.ledger) + 1,
                simulated_minute=0,
                tool="submit_forecast",
                arguments={
                    "target": "new_encounters",
                    "expected_new_encounters": 1,
                    "horizon_minutes": 1440,
                },
                status="submitted",
            ),
            LedgerEntry(
                sequence=len(environment.ledger) + 2,
                simulated_minute=1440,
                tool="submit_forecast",
                arguments={
                    "target": "new_encounters",
                    "expected_new_encounters": 2,
                    "horizon_minutes": 1440,
                },
                status="submitted",
            ),
        )

        scorecard = score_episode(
            oracle=oracle,
            manifest=bundle.public.manifest,
            ledger=ledger,
            seen_ids=environment.seen_ids,
            submission=submission,
        )

        self.assertEqual(scorecard.dimensions["prospective_forecast"], 10.0)
        self.assertEqual(scorecard.metrics["forecast_submissions"], 2)
        self.assertEqual(scorecard.metrics["forecast_mean_absolute_error"], 0.0)

    def test_false_alert_without_decisive_gold_uses_provenance_not_zero(self):
        bundle, environment, submission = self.baseline_context()
        oracle = replace(bundle.oracle, decisive_evidence_ids=frozenset())

        scorecard = score_episode(
            oracle=oracle,
            manifest=bundle.public.manifest,
            ledger=environment.ledger,
            seen_ids=environment.seen_ids,
            submission=submission,
        )

        self.assertGreater(scorecard.dimensions["evidence"], 0.0)
        self.assertEqual(scorecard.metrics["decisive_evidence_recall"], 1.0)

    def test_seen_followup_case_and_evidence_belong_in_final_handoff(self):
        bundle, environment, submission = self.baseline_context()
        patient_id = "pt_followup001"
        observation_id = "obs_followup001"
        oracle = replace(
            bundle.oracle,
            followup_true_case_observation_ids={
                patient_id: (observation_id,)
            },
            followup_relevant_evidence_ids=frozenset({observation_id}),
        )
        seen_ids = set(environment.seen_ids) | {observation_id}
        omitted = score_episode(
            oracle=oracle,
            manifest=bundle.public.manifest,
            ledger=environment.ledger,
            seen_ids=seen_ids,
            submission=submission,
        )
        included_submission = deepcopy(submission)
        included_submission["line_list"].append(
            {
                "patient_id": patient_id,
                "classification": "confirmed",
                "evidence_ids": [observation_id],
            }
        )
        included = score_episode(
            oracle=oracle,
            manifest=bundle.public.manifest,
            ledger=environment.ledger,
            seen_ids=seen_ids,
            submission=included_submission,
        )

        self.assertGreater(
            included.dimensions["line_list"],
            omitted.dimensions["line_list"],
        )
        self.assertEqual(included.metrics["followup_true_cases_seen"], 1)


if __name__ == "__main__":
    unittest.main()
