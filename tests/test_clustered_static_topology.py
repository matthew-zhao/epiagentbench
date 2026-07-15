from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
import unittest

from epiagentbench.trusted.engine import EngineControl
from epiagentbench.trusted.live_surveillance import IncrementalSurveillanceStream
from epiagentbench.trusted.starsim_engine import (
    CLUSTERED_STATIC_TOPOLOGY_VERSION,
    CONTACT_TRANSMISSION_LEVEL,
    DAY_MINUTES,
    ClusteredStaticTopology,
    StarsimDiseaseEngine,
    StarsimSIRConfig,
)
from epiagentbench.trusted.starsim_episode import StarsimSurveillanceBackend
from epiagentbench.trusted.surveillance import (
    LIVE_PROFILE_RESOURCE,
    load_gi_surveillance_profile,
)


HAS_STARSIM = importlib.util.find_spec("starsim") is not None


def candidate_profile() -> dict:
    profile = deepcopy(load_gi_surveillance_profile(LIVE_PROFILE_RESOURCE))
    profile["transmission_configuration"]["private_contact_topology"] = {
        "construction_version": CLUSTERED_STATIC_TOPOLOGY_VERSION,
        "cluster_size": 40,
        "within_cluster_degree": 6,
        "cross_cluster_edges_per_cluster": 0.2,
    }
    profile["transmission_configuration"][
        "private_fixed_initial_infections"
    ] = {"person_to_person": 3}
    return profile


class ClusteredStaticValidationTests(unittest.TestCase):
    def test_topology_validation_is_strict_without_starsim(self):
        invalid = (
            {"cluster_size": 3, "within_cluster_degree": 2},
            {"cluster_size": 40, "within_cluster_degree": 3},
            {"cluster_size": 40, "within_cluster_degree": 40},
            {
                "cluster_size": 40,
                "within_cluster_degree": 6,
                "cross_cluster_edges_per_cluster": -0.1,
            },
            {
                "cluster_size": 40,
                "within_cluster_degree": 6,
                "cross_cluster_edges_per_cluster": 1.1,
            },
            {
                "cluster_size": 40,
                "within_cluster_degree": 6,
                "construction_version": "future-version",
            },
        )
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(ValueError):
                ClusteredStaticTopology(**values)

        topology = ClusteredStaticTopology(40, 6, 0.2)
        with self.assertRaisesRegex(ValueError, "divide n_agents"):
            StarsimSIRConfig(
                random_seed=1,
                n_agents=101,
                contact_topology=topology,
            )
        with self.assertRaisesRegex(ValueError, "at least two clusters"):
            StarsimSIRConfig(
                random_seed=1,
                n_agents=40,
                contact_topology=topology,
            )
        with self.assertRaisesRegex(ValueError, "must equal initial_prevalence"):
            StarsimSIRConfig(
                random_seed=1,
                n_agents=1_000,
                initial_prevalence=0.003,
                fixed_initial_infections=2,
            )
        with self.assertRaisesRegex(ValueError, "within the population"):
            StarsimSIRConfig(
                random_seed=1,
                n_agents=100,
                initial_prevalence=0.0,
                fixed_initial_infections=0,
            )

    def test_candidate_profile_is_explicit_and_default_remains_dynamic(self):
        default = StarsimSurveillanceBackend()._config(
            11, causal_mode="person_to_person"
        )
        self.assertIsNone(default.contact_topology)
        self.assertIsNone(default.fixed_initial_infections)

        candidate = StarsimSurveillanceBackend(candidate_profile())._config(
            11, causal_mode="person_to_person"
        )
        self.assertEqual(
            candidate.contact_topology,
            ClusteredStaticTopology(40, 6, 0.2),
        )
        self.assertEqual(candidate.fixed_initial_infections, 3)
        self.assertEqual(candidate.initial_prevalence, 0.003)

    def test_candidate_profile_rejects_unknown_private_fields(self):
        profile = candidate_profile()
        profile["transmission_configuration"]["private_contact_topology"][
            "surprise"
        ] = True
        with self.assertRaisesRegex(ValueError, "exactly"):
            StarsimSurveillanceBackend(profile)._config(
                11, causal_mode="person_to_person"
            )

        profile = candidate_profile()
        profile["transmission_configuration"][
            "private_fixed_initial_infections"
        ] = {"unknown-mode": 3}
        with self.assertRaisesRegex(ValueError, "supported modes"):
            StarsimSurveillanceBackend(profile)._config(
                11, causal_mode="person_to_person"
            )

    def test_private_topology_fields_do_not_enter_public_episode(self):
        stream = IncrementalSurveillanceStream(
            seed=17,
            presentation_key=b"p" * 32,
            profile=candidate_profile(),
            population_size=1_000,
            decision_minute=8 * DAY_MINUTES,
            deadline_minutes=5 * DAY_MINUTES,
            causal_mode="person_to_person",
        )
        public = stream.bootstrap()
        serialized = json.dumps(
            {
                "manifest": public.manifest,
                "observations": [
                    observation.public_dict()
                    for observation in public.observations
                ],
            },
            sort_keys=True,
        )
        for forbidden in (
            "private_contact_topology",
            "private_fixed_initial_infections",
            "cluster_size",
            "within_cluster_degree",
            "cross_cluster_edges_per_cluster",
            CLUSTERED_STATIC_TOPOLOGY_VERSION,
        ):
            self.assertNotIn(forbidden, serialized)


@unittest.skipUnless(HAS_STARSIM, "install the starsim extra")
class ClusteredStaticIntegrationTests(unittest.TestCase):
    @staticmethod
    def config(random_seed: int = 31) -> StarsimSIRConfig:
        return StarsimSIRConfig(
            random_seed=random_seed,
            n_agents=120,
            horizon_days=4,
            timestep_minutes=DAY_MINUTES,
            n_contacts=6,
            beta=0.14,
            initial_prevalence=0.025,
            infectious_days=3.0,
            contact_topology=ClusteredStaticTopology(40, 6, 0.2),
            fixed_initial_infections=3,
        )

    @staticmethod
    def graph_edges(engine: StarsimDiseaseEngine) -> frozenset[tuple[int, int]]:
        network = engine._sim.networks[0]
        return frozenset(
            (min(int(left), int(right)), max(int(left), int(right)))
            for left, right in zip(network.p1, network.p2, strict=True)
        )

    def test_default_randomsafe_trajectory_is_unchanged(self):
        engine = StarsimDiseaseEngine(
            StarsimSIRConfig(random_seed=7, n_agents=100, horizon_days=2)
        )
        try:
            self.assertEqual(type(engine._sim.networks[0]).__name__, "RandomSafeNet")
            engine.advance_to(2 * DAY_MINUTES)
            self.assertEqual(
                engine.oracle_snapshot().ever_infected_agent_ids,
                (1, 7, 8, 11, 18, 24, 31, 32, 62, 65, 66, 98),
            )
        finally:
            engine.close()

    def test_static_graph_and_oracle_are_seed_deterministic(self):
        first = StarsimDiseaseEngine(self.config())
        second = StarsimDiseaseEngine(self.config())
        other_seed = StarsimDiseaseEngine(self.config(32))
        try:
            first_edges = self.graph_edges(first)
            self.assertEqual(type(first._sim.networks[0]).__name__, "StaticNet")
            self.assertEqual(len(first_edges), 361)
            self.assertEqual(first_edges, self.graph_edges(second))
            self.assertNotEqual(first_edges, self.graph_edges(other_seed))

            for engine in (first, second):
                engine.advance_to(4 * DAY_MINUTES)
            self.assertEqual(first.oracle_snapshot(), second.oracle_snapshot())
            seed_events = [
                event
                for event in first.oracle_snapshot().transmission_events
                if event.mechanism == "seed"
            ]
            self.assertEqual(len(seed_events), 3)
        finally:
            first.close()
            second.close()
            other_seed.close()

    def test_static_control_preserves_prefix_and_replays_exactly(self):
        def controlled_run():
            active = StarsimDiseaseEngine(self.config(41))
            active.apply_control(
                EngineControl(
                    control_id="ward-control",
                    kind=CONTACT_TRANSMISSION_LEVEL,
                    effective_minute=DAY_MINUTES,
                    magnitude=0.2,
                )
            )
            active.advance_to(DAY_MINUTES)
            prefix = active.oracle_snapshot()
            active.advance_to(4 * DAY_MINUTES)
            final = active.oracle_snapshot()
            active.close()
            return prefix, final

        shadow = StarsimDiseaseEngine(self.config(41))
        try:
            shadow.advance_to(DAY_MINUTES)
            uncontrolled_prefix = shadow.oracle_snapshot()
            shadow.advance_to(4 * DAY_MINUTES)
            uncontrolled_final = shadow.oracle_snapshot()
        finally:
            shadow.close()

        first_prefix, first_final = controlled_run()
        second_prefix, second_final = controlled_run()
        self.assertEqual(first_prefix, uncontrolled_prefix)
        self.assertEqual(first_prefix, second_prefix)
        self.assertEqual(first_final, second_final)
        self.assertEqual(first_final.applied_control_ids, ("ward-control",))
        self.assertGreaterEqual(
            len(uncontrolled_final.ever_infected_agent_ids),
            len(first_final.ever_infected_agent_ids),
        )


if __name__ == "__main__":
    unittest.main()
