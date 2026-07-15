from __future__ import annotations

from copy import deepcopy
import importlib.util
import unittest
from unittest.mock import patch

from epiagentbench.trusted.calibration_panel import (
    FullHorizonObservation,
    build_fitted_profile,
    evaluate_calibration_panel,
    generate_full_horizon_observation,
    refine_nors_clustered_topology_candidate,
)
from epiagentbench.trusted.surveillance import (
    LIVE_PROFILE_RESOURCE,
    load_gi_surveillance_profile,
)


HAS_STARSIM = importlib.util.find_spec("starsim") is not None


def refinement_plan() -> dict:
    return {
        "plan_version": "nors_temporal_v2",
        "plan_sha256": "a" * 64,
        "cohorts": {
            "institution_person_to_person": {
                "released_targets": {
                    "calibration": {
                        "reported_outbreak_size": {
                            "q25": 15.0,
                            "median": 27.0,
                            "q75": 46.0,
                        }
                    },
                    "model_selection": {
                        "reported_outbreak_size": {
                            "q25": 12.0,
                            "median": 20.0,
                            "q75": 35.0,
                        }
                    },
                }
            },
            "restaurant_common_source": {
                "released_targets": {
                    "model_selection": {
                        "reported_outbreak_size": {
                            "q25": 4.0,
                            "median": 7.0,
                            "q75": 14.0,
                        }
                    }
                }
            },
        },
    }


def parent_nors_candidate() -> dict:
    return build_fitted_profile(
        load_gi_surveillance_profile(LIVE_PROFILE_RESOURCE),
        plan={"plan_sha256": "a" * 64},
        contact_hazard_multiplier=1.0,
        common_source_exposure_multiplier=0.3,
    )


def mocked_refinement_panel(
    seeds,
    *,
    causal_mode,
    profile,
    **_kwargs,
):
    seed_tuple = tuple(seeds)
    transmission = profile["transmission_configuration"]
    hazard = float(transmission["daily_transmission_hazard"])
    bridge_density = float(
        transmission["private_contact_topology"][
            "cross_cluster_edges_per_cluster"
        ]
    )
    if causal_mode == "common_source":
        values = (2, 4, 7, 14, 25)
    elif seed_tuple == (101, 102, 103, 104, 105):
        values = (2, 12, 20, 35, 70)
    elif hazard == 0.14 and bridge_density == 0.2:
        values = (2, 15, 27, 46, 80)
    elif hazard == 0.14:
        values = (2, 14, 25, 45, 75)
    elif bridge_density == 0.2:
        values = (2, 9, 16, 27, 50)
    else:
        values = (2, 8, 15, 25, 45)
    regimes = ("high", "low", "medium", "low", "medium")
    return tuple(
        FullHorizonObservation(
            seed=seed,
            causal_mode=causal_mode,
            growth_regime=regime,
            latent_infections=value * 2,
            reported_illnesses=value,
            population_size=1000,
            followup_days=14,
        )
        for seed, value, regime in zip(
            seed_tuple, values, regimes, strict=True
        )
    )


class CalibrationPanelContractTests(unittest.TestCase):
    def test_panel_conditions_like_nors_but_reports_all_introductions(self):
        rows = tuple(
            FullHorizonObservation(
                seed=index,
                causal_mode="person_to_person",
                growth_regime="medium",
                latent_infections=value + 1,
                reported_illnesses=value,
                population_size=1000,
                followup_days=14,
            )
            for index, value in enumerate((0, 1, 2, 4, 8))
        )
        result = evaluate_calibration_panel(
            rows,
            {
                "reported_outbreak_size": {
                    "q25": 3.0,
                    "median": 4.0,
                    "q75": 6.0,
                }
            },
        )

        self.assertEqual(result["episodes_run_once"], 5)
        self.assertEqual(result["outcome_retries"], 0)
        self.assertEqual(result["nors_eligible_episodes"], 3)
        self.assertEqual(
            result["comparison"]["simulated"]["median"], 4.0
        )
        self.assertEqual(
            result["unconditional_reported_illnesses"]["min"], 0
        )

    def test_fitted_profile_scales_copy_and_records_nonidentifiability(self):
        source = load_gi_surveillance_profile(LIVE_PROFILE_RESOURCE)
        original_hazard = source["transmission_configuration"][
            "daily_transmission_hazard"
        ]
        original_bounds = source["closed_loop_configuration"]["causal_modes"][
            "common_source"
        ]["predecision_exposure_candidates"]

        fitted = build_fitted_profile(
            source,
            plan={"plan_sha256": "a" * 64},
            contact_hazard_multiplier=0.5,
            common_source_exposure_multiplier=0.5,
        )

        self.assertEqual(
            fitted["transmission_configuration"]["daily_transmission_hazard"],
            0.02,
        )
        self.assertEqual(
            fitted["closed_loop_configuration"]["causal_modes"][
                "common_source"
            ]["predecision_exposure_candidates"],
            [9, 18],
        )
        self.assertEqual(
            fitted["calibration_record"]["identifiability"],
            "composite_not_biological",
        )
        self.assertEqual(
            source["transmission_configuration"]["daily_transmission_hazard"],
            original_hazard,
        )
        self.assertEqual(
            source["closed_loop_configuration"]["causal_modes"][
                "common_source"
            ]["predecision_exposure_candidates"],
            original_bounds,
        )

    @unittest.skipUnless(HAS_STARSIM, "install the starsim extra")
    def test_one_seed_is_deterministic_and_has_no_admission_retry(self):
        first = generate_full_horizon_observation(
            seed=3,
            causal_mode="person_to_person",
            contact_hazard_multiplier=0.4,
        )
        second = generate_full_horizon_observation(
            seed=3,
            causal_mode="person_to_person",
            contact_hazard_multiplier=0.4,
        )

        self.assertEqual(first, second)
        self.assertGreaterEqual(first.latent_infections, 0)
        self.assertGreaterEqual(first.reported_illnesses, 0)


class ClusteredRefinementContractTests(unittest.TestCase):
    def test_fit_only_selection_then_one_call_per_visible_cohort(self):
        parent = parent_nors_candidate()
        original = deepcopy(parent)
        calls = []

        def generator(*args, **kwargs):
            calls.append((args, kwargs))
            return mocked_refinement_panel(*args, **kwargs)

        with patch(
            "epiagentbench.trusted.calibration_panel.generate_calibration_panel",
            side_effect=generator,
        ):
            report, candidate = refine_nors_clustered_topology_candidate(
                refinement_plan(),
                fit_seeds=(1, 2, 3, 4, 5),
                validation_seeds=(101, 102, 103, 104, 105),
                profile=parent,
                cluster_sizes=(40,),
                within_cluster_degrees=(6,),
                cross_cluster_edge_densities=(0.0, 0.2),
                daily_contact_hazards=(0.12, 0.14),
            )

        self.assertEqual(len(calls), 6)
        self.assertTrue(
            all(
                call[1]["causal_mode"] == "person_to_person"
                for call in calls[:5]
            )
        )
        self.assertEqual(calls[-1][1]["causal_mode"], "common_source")
        self.assertEqual(
            tuple(calls[-1][0][0]), (101, 102, 103, 104, 105)
        )
        self.assertEqual(
            report["selected_parameters"],
            {
                "cluster_size": 40,
                "within_cluster_degree": 6,
                "cross_cluster_edges_per_cluster": 0.2,
                "daily_contact_hazard": 0.14,
            },
        )
        self.assertEqual(len(report["fit_grid"]), 4)
        self.assertTrue(
            all(len(row["panel_rows"]) == 5 for row in report["fit_grid"])
        )
        self.assertEqual(
            report["fit_growth_regime_counts"],
            {"high": 1, "low": 2, "medium": 2},
        )
        gate = report["p2p_visible_validation"]["preregistered_gate"]
        self.assertEqual(gate["scope"], "institution_person_to_person_only")
        self.assertEqual(gate["maximum"], 0.35)
        self.assertTrue(gate["frozen_before_fit"])
        self.assertTrue(gate["passed"])
        self.assertFalse(report["selection_uses_visible_validation"])
        self.assertFalse(report["sealed_temporal_partitions_used"])
        self.assertEqual(report["sealed_data_status"], "not_opened_not_used")
        self.assertIn(
            "not a selection criterion",
            report["common_source_visible_sensitivity"]["role"],
        )
        self.assertTrue(
            report["common_source_visible_sensitivity"][
                "preserved_exposure_configuration"
            ]
        )

        transmission = candidate["transmission_configuration"]
        self.assertEqual(transmission["daily_transmission_hazard"], 0.14)
        self.assertEqual(
            transmission["private_fixed_initial_infections"],
            {"person_to_person": 3},
        )
        self.assertEqual(
            transmission["private_contact_topology"]["cluster_size"], 40
        )
        self.assertEqual(
            candidate["calibration_record"][
                "common_source_exposure_multiplier"
            ],
            0.3,
        )
        self.assertEqual(
            candidate["closed_loop_configuration"]["causal_modes"][
                "common_source"
            ],
            original["closed_loop_configuration"]["causal_modes"][
                "common_source"
            ],
        )
        self.assertIn("clustered_refinement_record", candidate)
        self.assertEqual(parent, original)

    def test_report_and_candidate_commitments_are_reproducible(self):
        arguments = dict(
            plan=refinement_plan(),
            fit_seeds=(1, 2, 3, 4, 5),
            validation_seeds=(101, 102, 103, 104, 105),
            profile=parent_nors_candidate(),
            cluster_sizes=(40,),
            within_cluster_degrees=(6,),
            cross_cluster_edge_densities=(0.0, 0.2),
            daily_contact_hazards=(0.12, 0.14),
        )
        with patch(
            "epiagentbench.trusted.calibration_panel.generate_calibration_panel",
            side_effect=mocked_refinement_panel,
        ):
            first_report, first_candidate = (
                refine_nors_clustered_topology_candidate(**arguments)
            )
        with patch(
            "epiagentbench.trusted.calibration_panel.generate_calibration_panel",
            side_effect=mocked_refinement_panel,
        ):
            second_report, second_candidate = (
                refine_nors_clustered_topology_candidate(**arguments)
            )

        self.assertEqual(first_report, second_report)
        self.assertEqual(first_candidate, second_candidate)
        self.assertEqual(len(first_report["report_sha256"]), 64)
        self.assertEqual(len(first_report["grid_sha256"]), 64)
        self.assertEqual(
            len(first_report["refinement_contract_sha256"]), 64
        )
        self.assertEqual(
            first_candidate["clustered_refinement_record"]["report_sha256"],
            first_report["report_sha256"],
        )

    def test_invalid_or_filtered_panels_fail_before_validation(self):
        with patch(
            "epiagentbench.trusted.calibration_panel.generate_calibration_panel"
        ) as generator:
            with self.assertRaisesRegex(ValueError, "disjoint"):
                refine_nors_clustered_topology_candidate(
                    refinement_plan(),
                    fit_seeds=(1, 2, 3, 4, 5),
                    validation_seeds=(5, 6, 7, 8, 9),
                    profile=parent_nors_candidate(),
                )
            generator.assert_not_called()

        with patch(
            "epiagentbench.trusted.calibration_panel.generate_calibration_panel"
        ) as generator:
            with self.assertRaisesRegex(ValueError, "divide population"):
                refine_nors_clustered_topology_candidate(
                    refinement_plan(),
                    fit_seeds=(1, 2, 3, 4, 5),
                    validation_seeds=(101, 102, 103, 104, 105),
                    profile=parent_nors_candidate(),
                    cluster_sizes=(30,),
                )
            generator.assert_not_called()

        def filtered(*args, **kwargs):
            return mocked_refinement_panel(*args, **kwargs)[:-1]

        with patch(
            "epiagentbench.trusted.calibration_panel.generate_calibration_panel",
            side_effect=filtered,
        ) as generator:
            with self.assertRaisesRegex(RuntimeError, "exactly one ordered row"):
                refine_nors_clustered_topology_candidate(
                    refinement_plan(),
                    fit_seeds=(1, 2, 3, 4, 5),
                    validation_seeds=(101, 102, 103, 104, 105),
                    profile=parent_nors_candidate(),
                    cluster_sizes=(40,),
                    within_cluster_degrees=(6,),
                    cross_cluster_edge_densities=(0.0,),
                    daily_contact_hazards=(0.14,),
                )
            self.assertEqual(generator.call_count, 1)


if __name__ == "__main__":
    unittest.main()
