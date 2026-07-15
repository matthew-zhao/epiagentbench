from __future__ import annotations

from dataclasses import replace
from itertools import product
import unittest

from epiagentbench.trusted.intervention_evaluation import (
    EVIDENCE_STATUS,
    OUTCOME_FIELDS,
    DoseResponseExpectation,
    InterventionOutcomes,
    PolicyOutcomeDraw,
    StakeholderWeightProfile,
    commit_opening_history,
    evaluate_policy_panel,
    stakeholder_weight_profile_sha256,
    validate_dose_response,
    validate_negative_control,
)


def _profile(
    profile_id: str,
    stakeholder_group: str,
    selected_weights: dict[str, float],
) -> StakeholderWeightProfile:
    weights = {field_name: 0.0 for field_name in OUTCOME_FIELDS}
    weights.update(selected_weights)
    arguments = {
        "profile_id": profile_id,
        "profile_version": "v1",
        "stakeholder_group": stakeholder_group,
        "registration_reference": f"frozen-test-manifest:{profile_id}",
        "outcome_loss_weights": weights,
    }
    digest = stakeholder_weight_profile_sha256(**arguments)
    return StakeholderWeightProfile(
        **arguments,
        registration_sha256=digest,
    )


class InterventionEvaluationFoundationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.opening = commit_opening_history(
            {
                "alerts": [
                    {"available_minute": 0, "kind": "syndromic", "count": 4}
                ],
                "facility": "public-presentation-id",
            },
            cutoff_minute=720,
        )
        self.keys = tuple(
            product(
                (101, 102),
                ("posterior-a", "posterior-b"),
                ("effect-low", "effect-high"),
            )
        )

    def _outcomes(self, policy_id: str, key_index: int) -> InterventionOutcomes:
        baseline_cases = 20.0 + key_index
        case_reduction = {
            "off": 0.0,
            "standard": 4.0,
            "intensive": 8.0,
        }[policy_id]
        restriction_days = {
            "off": 0.0,
            "standard": 2.0,
            "intensive": 6.0,
        }[policy_id]
        return InterventionOutcomes(
            resident_symptomatic_cases=baseline_cases - case_reduction,
            staff_symptomatic_cases=5.0 - case_reduction / 4.0,
            staff_absence_days=10.0 - case_reduction / 2.0,
            hospitalizations=1.0,
            deaths=0.25,
            incident_duration_days=12.0 - case_reduction / 2.0,
            restriction_days=restriction_days,
            closure_days=restriction_days / 2.0,
            tests_performed=2.0 + restriction_days,
            cleaning_hours=restriction_days * 3.0,
            investigator_hours=4.0 + restriction_days,
            false_escalations=1.0 if policy_id == "intensive" else 0.0,
            unresolved_reporting_errors=0.0,
        )

    def _panel(self, policies=("off", "standard", "intensive")):
        return [
            PolicyOutcomeDraw(
                opening_history=self.opening,
                policy_id=policy_id,
                future_seed=future_seed,
                posterior_draw_id=posterior_draw_id,
                intervention_effect_draw_id=effect_draw_id,
                outcomes=self._outcomes(policy_id, key_index),
            )
            for key_index, (
                future_seed,
                posterior_draw_id,
                effect_draw_id,
            ) in enumerate(self.keys)
            for policy_id in policies
        ]

    def test_commitment_is_canonical_and_retains_no_opening_history(self):
        first = commit_opening_history(
            {"b": [2, 3], "a": 1},
            cutoff_minute=60,
        )
        second = commit_opening_history(
            {"a": 1, "b": [2, 3]},
            cutoff_minute=60,
        )

        self.assertEqual(first, second)
        self.assertEqual(
            set(first.as_dict()),
            {"sha256", "cutoff_minute", "schema_version"},
        )
        with self.assertRaisesRegex(ValueError, "non-finite"):
            commit_opening_history({"bad": float("nan")}, cutoff_minute=0)
        with self.assertRaisesRegex(ValueError, "non-string"):
            commit_opening_history({1: "ambiguous key"}, cutoff_minute=0)

    def test_weight_profiles_must_match_their_frozen_content_digest(self):
        profile = _profile("health", "residents", {"deaths": 100.0})
        changed = dict(profile.outcome_loss_weights)
        changed["deaths"] = 99.0

        with self.assertRaisesRegex(ValueError, "registration digest"):
            StakeholderWeightProfile(
                profile_id=profile.profile_id,
                profile_version=profile.profile_version,
                stakeholder_group=profile.stakeholder_group,
                registration_reference=profile.registration_reference,
                registration_sha256=profile.registration_sha256,
                outcome_loss_weights=changed,
            )
        with self.assertRaisesRegex(ValueError, "explicitly cover"):
            stakeholder_weight_profile_sha256(
                profile_id="incomplete",
                profile_version="v1",
                stakeholder_group="test",
                registration_reference="frozen-test-manifest:incomplete",
                outcome_loss_weights={"deaths": 1.0},
            )

    def test_reporting_repairs_are_not_mis_scored_as_harm(self):
        profile = _profile(
            "report-quality",
            "surveillance-operations",
            {"unresolved_reporting_errors": 1.0},
        )
        corrected = InterventionOutcomes(unresolved_reporting_errors=0.0)
        uncorrected = InterventionOutcomes(unresolved_reporting_errors=3.0)

        self.assertNotIn("reporting_corrections", OUTCOME_FIELDS)
        self.assertLess(profile.loss(corrected), profile.loss(uncorrected))

    def test_balanced_panel_reports_vector_uncertainty_regret_tail_and_ranks(self):
        health = _profile(
            "health",
            "resident-and-staff-health",
            {
                "resident_symptomatic_cases": 1.0,
                "staff_symptomatic_cases": 1.0,
                "hospitalizations": 10.0,
                "deaths": 100.0,
            },
        )
        continuity = _profile(
            "continuity",
            "facility-continuity",
            {
                "resident_symptomatic_cases": 0.1,
                "restriction_days": 2.0,
                "closure_days": 5.0,
            },
        )

        report = evaluate_policy_panel(
            self._panel(),
            policy_ids=("off", "standard", "intensive"),
            weight_profiles=(health, continuity),
            opening_history=self.opening,
        )

        self.assertEqual(report.draw_count, 8)
        self.assertEqual(report.future_seed_count, 2)
        self.assertEqual(report.posterior_draw_count, 2)
        self.assertEqual(report.intervention_effect_draw_count, 2)
        self.assertEqual(report.evidence_status, EVIDENCE_STATUS)
        self.assertEqual(
            set(report.vector_summaries["off"].outcomes),
            set(OUTCOME_FIELDS),
        )
        self.assertEqual(
            report.vector_summaries["off"].outcomes[
                "resident_symptomatic_cases"
            ].mean,
            23.5,
        )

        health_result = report.weight_profile_evaluations["health"]
        continuity_result = report.weight_profile_evaluations["continuity"]
        self.assertEqual(health_result.ranking[0], "intensive")
        self.assertEqual(continuity_result.ranking[0], "off")
        off_health = health_result.policy_summaries["off"]
        intensive_health = health_result.policy_summaries["intensive"]
        self.assertGreater(off_health.mean_drawwise_regret, 0.0)
        self.assertGreater(off_health.regret_vs_best_mean_policy, 0.0)
        self.assertEqual(intensive_health.regret_vs_best_mean_policy, 0.0)
        self.assertLessEqual(
            off_health.utility_uncertainty_interval.lower,
            off_health.mean_utility,
        )
        self.assertGreaterEqual(
            off_health.severe_tail_mean_harm,
            off_health.mean_harm,
        )
        self.assertEqual(report.rank_sensitivity["intensive"].best_rank, 1)
        self.assertEqual(report.rank_sensitivity["intensive"].worst_rank, 3)
        self.assertEqual(report.rank_sensitivity["intensive"].rank_span, 2)

    def test_panel_rejects_mixed_history_missing_draws_and_thin_axes(self):
        profile = _profile("health", "health", {"deaths": 1.0})
        rows = self._panel(("off", "standard"))
        other_opening = commit_opening_history(
            {"alerts": []},
            cutoff_minute=720,
        )
        mixed = [replace(rows[0], opening_history=other_opening), *rows[1:]]
        with self.assertRaisesRegex(ValueError, "opening-history"):
            evaluate_policy_panel(
                mixed,
                policy_ids=("off", "standard"),
                weight_profiles=(profile,),
                opening_history=self.opening,
            )

        with self.assertRaisesRegex(ValueError, "balanced"):
            evaluate_policy_panel(
                rows[:-1],
                policy_ids=("off", "standard"),
                weight_profiles=(profile,),
                opening_history=self.opening,
            )

        one_key = [row for row in rows if row.future_seed == 101]
        with self.assertRaisesRegex(ValueError, "future seeds"):
            evaluate_policy_panel(
                one_key,
                policy_ids=("off", "standard"),
                weight_profiles=(profile,),
                opening_history=self.opening,
            )

    def test_negative_control_uses_paired_absolute_differences(self):
        reference_rows = self._panel(("off",))
        sham_rows = [
            replace(
                row,
                policy_id="sham",
                outcomes=replace(
                    row.outcomes,
                    tests_performed=row.outcomes.tests_performed + 2.0,
                ),
            )
            for row in reference_rows
        ]
        rows = reference_rows + sham_rows

        result = validate_negative_control(
            rows,
            reference_policy_id="off",
            negative_control_policy_id="sham",
            opening_history=self.opening,
        )
        self.assertTrue(result.contract_passed)
        self.assertEqual(result.evidence_status, EVIDENCE_STATUS)

        changed_sham = list(sham_rows)
        changed_sham[0] = replace(
            changed_sham[0],
            outcomes=replace(
                changed_sham[0].outcomes,
                resident_symptomatic_cases=(
                    changed_sham[0].outcomes.resident_symptomatic_cases + 1.0
                ),
            ),
        )
        failed = validate_negative_control(
            reference_rows + changed_sham,
            reference_policy_id="off",
            negative_control_policy_id="sham",
            opening_history=self.opening,
        )
        self.assertFalse(failed.contract_passed)
        self.assertEqual(
            failed.fields["resident_symptomatic_cases"].mean_paired_delta,
            0.125,
        )
        self.assertEqual(
            failed.fields[
                "resident_symptomatic_cases"
            ].mean_absolute_paired_delta,
            0.125,
        )

    def test_dose_response_checks_health_benefit_and_operational_burden(self):
        expectations = (
            DoseResponseExpectation(
                "resident_symptomatic_cases",
                "nonincreasing",
            ),
            DoseResponseExpectation("restriction_days", "nondecreasing"),
        )
        rows = self._panel()

        result = validate_dose_response(
            rows,
            ordered_policy_ids=("off", "standard", "intensive"),
            expectations=expectations,
            opening_history=self.opening,
        )
        self.assertTrue(result.contract_passed)
        self.assertEqual(result.evidence_status, EVIDENCE_STATUS)

        broken = list(rows)
        intensive_index = next(
            index for index, row in enumerate(broken) if row.policy_id == "intensive"
        )
        broken[intensive_index] = replace(
            broken[intensive_index],
            outcomes=replace(
                broken[intensive_index].outcomes,
                resident_symptomatic_cases=100.0,
            ),
        )
        failed = validate_dose_response(
            broken,
            ordered_policy_ids=("off", "standard", "intensive"),
            expectations=expectations,
            opening_history=self.opening,
        )
        self.assertFalse(failed.contract_passed)
        health_result = failed.fields["resident_symptomatic_cases"]
        self.assertFalse(health_result.adjacent_comparisons[-1].contract_passed)


if __name__ == "__main__":
    unittest.main()
