from __future__ import annotations

import importlib.util
import unittest

from epiagentbench.trusted.engine import EngineControl, EngineError
from epiagentbench.trusted.starsim_engine import (
    COMMON_SOURCE,
    COMMON_SOURCE_EXPOSURE_LEVEL,
    CONTACT_TRANSMISSION_LEVEL,
    DAY_MINUTES,
    GLOBAL_TRANSMISSION_LEVEL,
    GLOBAL_TRANSMISSION_MULTIPLIER,
    IMPORTATION,
    IMPORTATION_EXPOSURE_LEVEL,
    ScheduledExogenousExposure,
    StarsimDiseaseEngine,
    StarsimSIRConfig,
)


HAS_STARSIM = importlib.util.find_spec("starsim") is not None


class StarsimAdapterTests(unittest.TestCase):
    def test_configuration_validation_does_not_require_optional_dependency(self):
        with self.assertRaises(ValueError):
            StarsimSIRConfig(random_seed=-1)
        with self.assertRaisesRegex(ValueError, "does not yet support deaths"):
            StarsimSIRConfig(random_seed=1, fatality_probability=0.1)
        with self.assertRaisesRegex(ValueError, "immutable tuple"):
            StarsimSIRConfig(random_seed=1, scheduled_exogenous_exposures=[])
        with self.assertRaisesRegex(ValueError, "outside the population"):
            StarsimSIRConfig(
                random_seed=1,
                n_agents=10,
                scheduled_exogenous_exposures=(
                    ScheduledExogenousExposure(COMMON_SOURCE, 10, 0, 0.5),
                ),
            )
        with self.assertRaisesRegex(ValueError, "timestep boundary"):
            StarsimSIRConfig(
                random_seed=1,
                scheduled_exogenous_exposures=(
                    ScheduledExogenousExposure(IMPORTATION, 1, 1, 0.5),
                ),
            )
        with self.assertRaisesRegex(ValueError, r"\[0, 1\)"):
            StarsimSIRConfig(
                random_seed=1,
                scheduled_exogenous_exposures=(
                    ScheduledExogenousExposure(IMPORTATION, 1, 0, 1.0),
                ),
            )

    @unittest.skipIf(HAS_STARSIM, "missing-dependency behavior only")
    def test_missing_optional_dependency_fails_closed(self):
        with self.assertRaisesRegex(EngineError, "evaluator-only"):
            StarsimDiseaseEngine(StarsimSIRConfig(random_seed=1))

    @unittest.skipUnless(HAS_STARSIM, "install the starsim extra")
    def test_same_seed_produces_same_detached_oracle(self):
        config = StarsimSIRConfig(
            random_seed=7,
            n_agents=100,
            horizon_days=2,
        )
        first = StarsimDiseaseEngine(config)
        second = StarsimDiseaseEngine(config)
        try:
            first.advance_to(2 * 1440)
            second.advance_to(2 * 1440)
            self.assertEqual(first.oracle_snapshot(), second.oracle_snapshot())
        finally:
            first.close()
            second.close()

    @unittest.skipUnless(HAS_STARSIM, "install the starsim extra")
    def test_absolute_transmission_level_is_idempotent_and_restorable(self):
        engine = StarsimDiseaseEngine(
            StarsimSIRConfig(
                random_seed=11,
                n_agents=100,
                horizon_days=4,
            )
        )
        try:
            for control in (
                EngineControl(
                    control_id="reduce",
                    kind=CONTACT_TRANSMISSION_LEVEL,
                    effective_minute=0,
                    magnitude=0.4,
                ),
                EngineControl(
                    control_id="repeat",
                    kind=GLOBAL_TRANSMISSION_LEVEL,
                    effective_minute=DAY_MINUTES,
                    magnitude=0.4,
                ),
                EngineControl(
                    control_id="restore",
                    kind=CONTACT_TRANSMISSION_LEVEL,
                    effective_minute=2 * DAY_MINUTES,
                    magnitude=1.0,
                ),
            ):
                engine.apply_control(control)

            engine.advance_to(DAY_MINUTES)
            disease = engine._sim.get_module("sir")
            self.assertTrue((disease.rel_trans.values == 0.4).all())

            engine.advance_to(2 * DAY_MINUTES)
            self.assertTrue((disease.rel_trans.values == 0.4).all())

            engine.advance_to(3 * DAY_MINUTES)
            self.assertTrue((disease.rel_trans.values == 1.0).all())
        finally:
            engine.close()

    @unittest.skipUnless(HAS_STARSIM, "install the starsim extra")
    def test_mixed_controls_use_stable_control_id_order(self):
        engine = StarsimDiseaseEngine(
            StarsimSIRConfig(
                random_seed=13,
                n_agents=100,
                horizon_days=2,
            )
        )
        try:
            # Schedule in reverse order.  Activation order is nevertheless
            # stable: cumulative multiplier "a" runs before absolute level
            # "b", so the final level is exactly 0.4 rather than 0.2.
            engine.apply_control(
                EngineControl(
                    control_id="b-level",
                    kind=GLOBAL_TRANSMISSION_LEVEL,
                    effective_minute=0,
                    magnitude=0.4,
                )
            )
            engine.apply_control(
                EngineControl(
                    control_id="a-multiplier",
                    kind=GLOBAL_TRANSMISSION_MULTIPLIER,
                    effective_minute=0,
                    magnitude=0.5,
                )
            )

            delta = engine.advance_to(DAY_MINUTES)
            disease = engine._sim.get_module("sir")
            self.assertEqual(
                delta.applied_control_ids,
                ("a-multiplier", "b-level"),
            )
            self.assertTrue((disease.rel_trans.values == 0.4).all())
        finally:
            engine.close()

    @unittest.skipUnless(HAS_STARSIM, "install the starsim extra")
    def test_exogenous_schedule_is_deterministic_and_provenance_is_detached(self):
        exposures = (
            ScheduledExogenousExposure(COMMON_SOURCE, 5, 0, 0.2),
            ScheduledExogenousExposure(IMPORTATION, 6, DAY_MINUTES, 0.8),
            ScheduledExogenousExposure(COMMON_SOURCE, 7, DAY_MINUTES, 0.4),
        )
        config = StarsimSIRConfig(
            random_seed=23,
            n_agents=30,
            horizon_days=2,
            beta=0.0,
            initial_prevalence=0.0,
            scheduled_exogenous_exposures=exposures,
        )
        first = StarsimDiseaseEngine(config)
        second = StarsimDiseaseEngine(config)
        try:
            first.advance_to(2 * DAY_MINUTES)
            second.advance_to(2 * DAY_MINUTES)
            self.assertEqual(first.oracle_snapshot(), second.oracle_snapshot())
            self.assertEqual(
                {
                    (event.target_agent_id, event.infection_minute, event.mechanism)
                    for event in first.oracle_snapshot().transmission_events
                },
                {
                    (5, 0, COMMON_SOURCE),
                    (6, DAY_MINUTES, IMPORTATION),
                    (7, DAY_MINUTES, COMMON_SOURCE),
                },
            )
            self.assertTrue(
                all(
                    event.source_agent_id is None
                    for event in first.oracle_snapshot().transmission_events
                )
            )
        finally:
            first.close()
            second.close()

    @unittest.skipUnless(HAS_STARSIM, "install the starsim extra")
    def test_fixed_thresholds_make_absolute_external_levels_idempotent(self):
        config = StarsimSIRConfig(
            random_seed=31,
            n_agents=30,
            horizon_days=1,
            beta=0.0,
            initial_prevalence=0.0,
            scheduled_exogenous_exposures=(
                ScheduledExogenousExposure(COMMON_SOURCE, 3, 0, 0.2),
                ScheduledExogenousExposure(COMMON_SOURCE, 4, 0, 0.8),
            ),
        )
        engine = StarsimDiseaseEngine(config)
        try:
            engine.apply_control(
                EngineControl(
                    control_id="common-half",
                    kind=COMMON_SOURCE_EXPOSURE_LEVEL,
                    effective_minute=0,
                    magnitude=0.5,
                )
            )
            engine.advance_to(DAY_MINUTES)
            self.assertEqual(
                tuple(
                    event.target_agent_id
                    for event in engine.oracle_snapshot().transmission_events
                ),
                (3,),
            )
        finally:
            engine.close()

    @unittest.skipUnless(HAS_STARSIM, "install the starsim extra")
    def test_controls_are_mechanism_specific(self):
        exposures = (
            ScheduledExogenousExposure(COMMON_SOURCE, 3, 0, 0.2),
            ScheduledExogenousExposure(IMPORTATION, 4, 0, 0.2),
        )
        config = StarsimSIRConfig(
            random_seed=37,
            n_agents=30,
            horizon_days=1,
            beta=0.0,
            initial_prevalence=0.0,
            scheduled_exogenous_exposures=exposures,
        )

        def run_with(kind: str, magnitude: float) -> set[str]:
            engine = StarsimDiseaseEngine(config)
            try:
                engine.apply_control(
                    EngineControl(
                        control_id=kind,
                        kind=kind,
                        effective_minute=0,
                        magnitude=magnitude,
                    )
                )
                engine.advance_to(DAY_MINUTES)
                return {
                    event.mechanism
                    for event in engine.oracle_snapshot().transmission_events
                }
            finally:
                engine.close()

        self.assertEqual(
            run_with(CONTACT_TRANSMISSION_LEVEL, 0.0),
            {COMMON_SOURCE, IMPORTATION},
        )
        self.assertEqual(
            run_with(COMMON_SOURCE_EXPOSURE_LEVEL, 0.0),
            {IMPORTATION},
        )
        self.assertEqual(
            run_with(IMPORTATION_EXPOSURE_LEVEL, 0.0),
            {COMMON_SOURCE},
        )

    @unittest.skipUnless(HAS_STARSIM, "install the starsim extra")
    def test_relevant_control_preserves_prefix_and_future_only(self):
        config = StarsimSIRConfig(
            random_seed=41,
            n_agents=30,
            horizon_days=3,
            beta=0.0,
            initial_prevalence=0.0,
            scheduled_exogenous_exposures=(
                ScheduledExogenousExposure(COMMON_SOURCE, 3, 0, 0.2),
                ScheduledExogenousExposure(COMMON_SOURCE, 4, DAY_MINUTES, 0.2),
                ScheduledExogenousExposure(
                    COMMON_SOURCE,
                    5,
                    2 * DAY_MINUTES,
                    0.2,
                ),
            ),
        )
        active = StarsimDiseaseEngine(config)
        shadow = StarsimDiseaseEngine(config)
        try:
            active.apply_control(
                EngineControl(
                    control_id="close-source",
                    kind=COMMON_SOURCE_EXPOSURE_LEVEL,
                    effective_minute=DAY_MINUTES,
                    magnitude=0.0,
                )
            )
            active.advance_to(DAY_MINUTES)
            shadow.advance_to(DAY_MINUTES)
            self.assertEqual(active.oracle_snapshot(), shadow.oracle_snapshot())

            active.advance_to(3 * DAY_MINUTES)
            shadow.advance_to(3 * DAY_MINUTES)
            self.assertEqual(
                tuple(
                    event.target_agent_id
                    for event in active.oracle_snapshot().transmission_events
                ),
                (3,),
            )
            self.assertEqual(
                tuple(
                    event.target_agent_id
                    for event in shadow.oracle_snapshot().transmission_events
                ),
                (3, 4, 5),
            )
        finally:
            active.close()
            shadow.close()

    @unittest.skipUnless(HAS_STARSIM, "install the starsim extra")
    def test_seed_and_contact_events_have_distinct_provenance(self):
        engine = StarsimDiseaseEngine(
            StarsimSIRConfig(
                random_seed=29,
                n_agents=100,
                horizon_days=2,
                n_contacts=8,
                beta=1.0,
                initial_prevalence=0.1,
            )
        )
        try:
            engine.advance_to(2 * DAY_MINUTES)
            mechanisms = {
                event.mechanism
                for event in engine.oracle_snapshot().transmission_events
            }
            self.assertIn("seed", mechanisms)
            self.assertIn("person_to_person", mechanisms)
        finally:
            engine.close()


if __name__ == "__main__":
    unittest.main()
