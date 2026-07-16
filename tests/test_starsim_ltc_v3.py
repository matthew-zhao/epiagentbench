from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import importlib.util
import json
import unittest

from epiagentbench.trusted.engine import EngineControl
from epiagentbench.trusted.starsim_ltc_v3 import (
    COMMON_SOURCE,
    CONTACT_REDUCTION_LEVEL,
    DAY_MINUTES,
    DESIGN_PLACEHOLDER,
    ENTRY_CONTROL_LEVEL,
    ENVIRONMENTAL,
    ENVIRONMENTAL_CONTROL_LEVEL,
    EVIDENCE_ANCHORED_PRIOR,
    EXPOSED_INCUBATING,
    IMPORTATION,
    INFECTIOUS_ASYMPTOMATIC,
    INFECTIOUS_SYMPTOMATIC,
    LtcInterventionAssumptions,
    LtcNorovirusNaturalHistory,
    LtcNorovirusStarsimEngine,
    LtcStarsimV3Config,
    PRIOR_PLACEHOLDER,
    RECOVERED,
    RESIDENT,
    RoleInfectiousnessProfile,
    SEED,
    SOURCE_CONTROL_LEVEL,
    STAFF,
    STAFF_EXCLUSION_LEVEL,
    ScheduledLtcExposure,
    public_engine_descriptor,
)


HAS_STARSIM = importlib.util.find_spec("starsim") is not None


@dataclass(frozen=True)
class _Person:
    person_id: str
    role: str
    ward_id: str | None
    room_id: str | None


@dataclass(frozen=True)
class _Contact:
    contact_id: str
    person_a_id: str
    person_b_id: str
    start_minute: int
    duration_minutes: int
    setting: str
    location_id: str | None


@dataclass(frozen=True)
class _Trace:
    people: tuple[_Person, ...]
    contacts: tuple[_Contact, ...]


def small_trace() -> _Trace:
    return _Trace(
        people=(
            _Person("resident-alpha", RESIDENT, "ward-red", "room-1"),
            _Person("resident-beta", RESIDENT, "ward-blue", "room-2"),
            _Person("staff-alpha", STAFF, "ward-red", None),
            _Person("staff-beta", STAFF, "ward-blue", None),
        ),
        contacts=(
            _Contact(
                "contact-1",
                "resident-alpha",
                "staff-alpha",
                0,
                60,
                "direct_care",
                "ward-red",
            ),
            # A second time-stamped trace record for the same pair must not
            # silently become a calibrated double-weight static edge.
            _Contact(
                "contact-2",
                "staff-alpha",
                "resident-alpha",
                120,
                30,
                "direct_care",
                "ward-red",
            ),
            _Contact(
                "contact-3",
                "resident-beta",
                "staff-beta",
                0,
                45,
                "direct_care",
                "ward-blue",
            ),
            _Contact(
                "contact-4",
                "staff-alpha",
                "staff-beta",
                240,
                20,
                "staff_handoff",
                "staff-room",
            ),
        ),
    )


def role_aware_history(beta: float = 0.2) -> LtcNorovirusNaturalHistory:
    return LtcNorovirusNaturalHistory(
        contact_beta_per_day=beta,
        incubation_days=1.0,
        infectious_days=2.0,
        role_profiles=(
            RoleInfectiousnessProfile(
                role=RESIDENT,
                symptomatic_probability=1.0,
                symptomatic_relative_infectiousness=1.6,
                asymptomatic_relative_infectiousness=0.3,
            ),
            RoleInfectiousnessProfile(
                role=STAFF,
                symptomatic_probability=0.0,
                symptomatic_relative_infectiousness=1.1,
                asymptomatic_relative_infectiousness=0.2,
            ),
        ),
    )


class LtcV3DependencyLightTests(unittest.TestCase):
    def test_scenario_evidence_status_is_required_and_defaults_are_labelled(self):
        with self.assertRaises(TypeError):
            LtcStarsimV3Config(  # type: ignore[call-arg]
                random_seed=1,
                seed_person_ids=("resident-alpha",),
            )

        config = LtcStarsimV3Config(
            random_seed=1,
            seed_person_ids=("resident-alpha",),
            evidence_status=DESIGN_PLACEHOLDER,
        )
        self.assertEqual(config.natural_history.evidence_status, PRIOR_PLACEHOLDER)
        self.assertEqual(
            config.intervention_assumptions.evidence_status,
            DESIGN_PLACEHOLDER,
        )
        self.assertTrue(
            all(
                profile.evidence_status == PRIOR_PLACEHOLDER
                for profile in config.natural_history.role_profiles
            )
        )

        with self.assertRaisesRegex(ValueError, "evidence reference"):
            LtcNorovirusNaturalHistory(
                evidence_status=EVIDENCE_ANCHORED_PRIOR
            )
        anchored = LtcInterventionAssumptions(
            evidence_status=EVIDENCE_ANCHORED_PRIOR,
            evidence_reference="registry-record-sha256:abc",
        )
        self.assertEqual(anchored.evidence_status, EVIDENCE_ANCHORED_PRIOR)

    def test_seed_and_schedule_validation_is_strict_without_starsim(self):
        for seed_ids in ((), ("a", "b", "c", "d"), ("a", "a")):
            with self.subTest(seed_ids=seed_ids), self.assertRaises(ValueError):
                LtcStarsimV3Config(
                    random_seed=1,
                    seed_person_ids=seed_ids,
                    evidence_status=DESIGN_PLACEHOLDER,
                )

        with self.assertRaisesRegex(ValueError, "only one"):
            LtcStarsimV3Config(
                random_seed=1,
                seed_person_ids=("a",),
                evidence_status=DESIGN_PLACEHOLDER,
                scheduled_exposures=(
                    ScheduledLtcExposure(COMMON_SOURCE, "b", DAY_MINUTES, 0.1),
                    ScheduledLtcExposure(IMPORTATION, "b", DAY_MINUTES, 0.2),
                ),
            )
        with self.assertRaisesRegex(ValueError, "timestep multiple"):
            history = LtcNorovirusNaturalHistory(incubation_days=0.75)
            LtcStarsimV3Config(
                random_seed=1,
                seed_person_ids=("resident-alpha",),
                evidence_status=DESIGN_PLACEHOLDER,
                timestep_minutes=DAY_MINUTES,
                natural_history=history,
            )

    def test_public_descriptor_has_no_episode_or_parameter_channel(self):
        config = LtcStarsimV3Config(
            random_seed=987654321,
            seed_person_ids=("resident-private-canary",),
            evidence_status=DESIGN_PLACEHOLDER,
            timestep_minutes=6 * 60,
            natural_history=LtcNorovirusNaturalHistory(
                contact_beta_per_day=0.731,
                incubation_days=1.25,
                infectious_days=3.75,
            ),
            scheduled_exposures=(
                ScheduledLtcExposure(
                    COMMON_SOURCE,
                    "source-private-canary",
                    DAY_MINUTES,
                    0.619,
                ),
            ),
        )
        descriptor = public_engine_descriptor()
        self.assertEqual(
            descriptor,
            {
                "engine_family": "institutional_disease_simulator",
                "model_status": "development_only_not_calibrated",
            },
        )
        serialized = json.dumps(descriptor, sort_keys=True)
        private = json.dumps(asdict(config), sort_keys=True)
        self.assertNotEqual(serialized, private)
        for forbidden in (
            "987654321",
            "resident-private-canary",
            "source-private-canary",
            "0.731",
            "0.619",
            "seed_person_ids",
            "scheduled_exposures",
            "role_profiles",
            "common_source",
            "ward",
        ):
            self.assertNotIn(forbidden, serialized)


@unittest.skipUnless(HAS_STARSIM, "install the starsim extra")
class LtcV3StarsimIntegrationTests(unittest.TestCase):
    def config(self, *, seed: int = 41) -> LtcStarsimV3Config:
        return LtcStarsimV3Config(
            random_seed=seed,
            seed_person_ids=("resident-alpha",),
            evidence_status=DESIGN_PLACEHOLDER,
            horizon_days=4,
            natural_history=role_aware_history(),
            scheduled_exposures=(
                ScheduledLtcExposure(
                    IMPORTATION,
                    "staff-beta",
                    0,
                    0.1,
                ),
            ),
        )

    def test_static_trace_network_exact_seeds_and_private_commitments(self):
        engine = LtcNorovirusStarsimEngine(small_trace(), self.config())
        try:
            self.assertEqual(type(engine._contact_network).__name__, "StaticNet")
            edges = {
                tuple(sorted((int(left), int(right))))
                for left, right in zip(
                    engine._contact_network.p1,
                    engine._contact_network.p2,
                    strict=True,
                )
            }
            self.assertEqual(len(edges), 3)
            events = engine.private_snapshot().transmission_events
            self.assertEqual(
                [event.target_person_id for event in events if event.mechanism == SEED],
                ["resident-alpha"],
            )
            self.assertEqual(
                [
                    event.target_person_id
                    for event in events
                    if event.mechanism == IMPORTATION
                ],
                ["staff-beta"],
            )
            metadata_json = json.dumps(
                asdict(engine.private_metadata), sort_keys=True
            )
            for raw_private in (
                "resident-alpha",
                "staff-beta",
                "ward-red",
                "room-1",
                "contact-1",
            ):
                self.assertNotIn(raw_private, metadata_json)
            self.assertEqual(engine.public_descriptor, public_engine_descriptor())
        finally:
            engine.close()

        moved = small_trace()
        moved_people = tuple(
            replace(person, ward_id="ward-blue")
            if person.person_id == "staff-alpha"
            else person
            for person in moved.people
        )
        other = LtcNorovirusStarsimEngine(
            replace(moved, people=moved_people), self.config()
        )
        baseline = LtcNorovirusStarsimEngine(small_trace(), self.config())
        try:
            self.assertNotEqual(
                baseline.private_metadata.role_ward_metadata_sha256,
                other.private_metadata.role_ward_metadata_sha256,
            )
            self.assertNotEqual(
                baseline.private_metadata.scenario_commitment_sha256,
                other.private_metadata.scenario_commitment_sha256,
            )
        finally:
            other.close()
            baseline.close()

    def test_states_are_deterministic_and_role_symptom_infectiousness_is_used(self):
        first = LtcNorovirusStarsimEngine(small_trace(), self.config())
        second = LtcNorovirusStarsimEngine(small_trace(), self.config())
        try:
            opening = {person.person_id: person for person in first.private_snapshot().people}
            self.assertEqual(opening["resident-alpha"].state, EXPOSED_INCUBATING)
            self.assertEqual(opening["staff-beta"].state, EXPOSED_INCUBATING)
            self.assertEqual(opening["resident-alpha"].relative_infectiousness, 0.0)

            for engine in (first, second):
                engine.advance_to(DAY_MINUTES)
            day_one = {
                person.person_id: person
                for person in first.private_snapshot().people
            }
            self.assertEqual(
                day_one["resident-alpha"].state,
                INFECTIOUS_SYMPTOMATIC,
            )
            self.assertAlmostEqual(
                day_one["resident-alpha"].relative_infectiousness,
                1.6,
                places=6,
            )
            self.assertEqual(
                day_one["staff-beta"].state,
                INFECTIOUS_ASYMPTOMATIC,
            )
            self.assertAlmostEqual(
                day_one["staff-beta"].relative_infectiousness,
                0.2,
                places=6,
            )
            self.assertEqual(first.private_trajectory, second.private_trajectory)

            for engine in (first, second):
                engine.advance_to(3 * DAY_MINUTES)
            day_three = {
                person.person_id: person
                for person in first.private_snapshot().people
            }
            self.assertEqual(day_three["resident-alpha"].state, RECOVERED)
            self.assertEqual(day_three["staff-beta"].state, RECOVERED)
            self.assertEqual(first.private_trajectory, second.private_trajectory)
            self.assertEqual(first.private_metadata, second.private_metadata)
        finally:
            first.close()
            second.close()

    def test_source_environment_and_importation_routes_are_separate_and_crn_safe(self):
        config = LtcStarsimV3Config(
            random_seed=17,
            seed_person_ids=("resident-alpha",),
            evidence_status=DESIGN_PLACEHOLDER,
            horizon_days=3,
            natural_history=role_aware_history(beta=0.000001),
            scheduled_exposures=(
                ScheduledLtcExposure(
                    COMMON_SOURCE,
                    "resident-beta",
                    DAY_MINUTES,
                    0.2,
                ),
                ScheduledLtcExposure(
                    IMPORTATION,
                    "staff-alpha",
                    DAY_MINUTES,
                    0.2,
                ),
                ScheduledLtcExposure(
                    ENVIRONMENTAL,
                    "staff-beta",
                    DAY_MINUTES,
                    0.2,
                ),
            ),
        )

        def controlled_run():
            engine = LtcNorovirusStarsimEngine(small_trace(), config)
            engine.apply_control(
                EngineControl(
                    control_id="close-source",
                    kind=SOURCE_CONTROL_LEVEL,
                    effective_minute=0,
                    magnitude=0.0,
                )
            )
            engine.apply_control(
                EngineControl(
                    control_id="clean-environment",
                    kind=ENVIRONMENTAL_CONTROL_LEVEL,
                    effective_minute=0,
                    magnitude=0.0,
                )
            )
            delta = engine.advance_to(2 * DAY_MINUTES)
            snapshot = engine.private_snapshot()
            engine.close()
            return delta, snapshot

        first_delta, first = controlled_run()
        second_delta, second = controlled_run()
        self.assertEqual(first_delta, second_delta)
        self.assertEqual(first, second)
        mechanisms = {event.mechanism for event in first.transmission_events}
        self.assertIn(SEED, mechanisms)
        self.assertIn(IMPORTATION, mechanisms)
        self.assertNotIn(COMMON_SOURCE, mechanisms)
        self.assertNotIn(ENVIRONMENTAL, mechanisms)

        shadow = LtcNorovirusStarsimEngine(small_trace(), config)
        try:
            self.assertEqual(
                first.transmission_events[:1],
                shadow.private_snapshot().transmission_events,
            )
            shadow.advance_to(2 * DAY_MINUTES)
            shadow_mechanisms = {
                event.mechanism
                for event in shadow.private_snapshot().transmission_events
            }
            self.assertTrue(
                {COMMON_SOURCE, IMPORTATION, ENVIRONMENTAL} <= shadow_mechanisms
            )
        finally:
            shadow.close()

        entry_controlled = LtcNorovirusStarsimEngine(small_trace(), config)
        try:
            entry_controlled.apply_control(
                EngineControl(
                    control_id="screen-entries",
                    kind=ENTRY_CONTROL_LEVEL,
                    effective_minute=0,
                    magnitude=0.0,
                )
            )
            entry_controlled.advance_to(2 * DAY_MINUTES)
            entry_mechanisms = {
                event.mechanism
                for event in entry_controlled.private_snapshot().transmission_events
            }
            self.assertNotIn(IMPORTATION, entry_mechanisms)
            self.assertTrue(
                {COMMON_SOURCE, ENVIRONMENTAL} <= entry_mechanisms
            )
        finally:
            entry_controlled.close()

    def test_contact_and_staff_controls_preserve_edges_and_prefix(self):
        config = replace(self.config(), scheduled_exposures=())
        active = LtcNorovirusStarsimEngine(small_trace(), config)
        shadow = LtcNorovirusStarsimEngine(small_trace(), config)
        replay = LtcNorovirusStarsimEngine(small_trace(), config)
        try:
            for engine in (active, replay):
                engine.apply_control(
                    EngineControl(
                        control_id="exclude-staff",
                        kind=STAFF_EXCLUSION_LEVEL,
                        effective_minute=DAY_MINUTES,
                        magnitude=0.0,
                        target_id="staff-alpha",
                    )
                )
                engine.apply_control(
                    EngineControl(
                        control_id="reduce-contacts",
                        kind=CONTACT_REDUCTION_LEVEL,
                        effective_minute=DAY_MINUTES,
                        magnitude=0.5,
                    )
                )

            active.advance_to(DAY_MINUTES)
            shadow.advance_to(DAY_MINUTES)
            replay.advance_to(DAY_MINUTES)
            self.assertEqual(active.private_snapshot(), shadow.private_snapshot())
            self.assertEqual(active.private_snapshot(), replay.private_snapshot())

            before_edges = tuple(
                zip(active._contact_network.p1, active._contact_network.p2, strict=True)
            )
            active.advance_to(3 * DAY_MINUTES)
            replay.advance_to(3 * DAY_MINUTES)
            after_edges = tuple(
                zip(active._contact_network.p1, active._contact_network.p2, strict=True)
            )
            self.assertEqual(before_edges, after_edges)
            self.assertEqual(active.private_trajectory, replay.private_trajectory)
            self.assertEqual(
                active.private_snapshot().applied_control_ids,
                ("exclude-staff", "reduce-contacts"),
            )

            staff_uid = active._uid_by_person_id["staff-alpha"]
            for left, right, beta in zip(
                active._contact_network.p1,
                active._contact_network.p2,
                active._contact_network.beta,
                strict=True,
            ):
                if staff_uid in {int(left), int(right)}:
                    self.assertEqual(float(beta), 0.0)
                else:
                    self.assertEqual(float(beta), 0.5)
        finally:
            active.close()
            shadow.close()
            replay.close()

    def test_control_must_have_time_to_affect_a_remaining_step(self):
        engine = LtcNorovirusStarsimEngine(small_trace(), self.config())
        try:
            with self.assertRaisesRegex(ValueError, "remaining simulator boundary"):
                engine.apply_control(
                    EngineControl(
                        control_id="too-late",
                        kind=CONTACT_REDUCTION_LEVEL,
                        effective_minute=self.config().horizon_days * DAY_MINUTES,
                        magnitude=0.0,
                    )
                )
        finally:
            engine.close()


if __name__ == "__main__":
    unittest.main()
