from __future__ import annotations

import importlib.util
import json
import unittest

from epiagentbench.baseline import run_scripted_baseline
from epiagentbench.environment import InvestigationEnvironment
from epiagentbench.trusted.engine import EngineControl, TransmissionEvent
from epiagentbench.trusted.starsim_engine import (
    GLOBAL_TRANSMISSION_MULTIPLIER,
    StarsimDiseaseEngine,
    StarsimSIRConfig,
)
from epiagentbench.trusted.starsim_episode import StarsimSurveillanceBackend
from epiagentbench.trusted.service import launch_secure_episode
from epiagentbench.trusted.surveillance import (
    build_institution_surveillance_episode,
    load_gi_surveillance_profile,
)


HAS_STARSIM = importlib.util.find_spec("starsim") is not None
DAY = 1440
DECISION = 8 * DAY
HORIZON = 21 * DAY


def synthetic_trace() -> tuple[TransmissionEvent, ...]:
    events = [
        TransmissionEvent(index, None, 0)
        for index in range(4)
    ]
    for index in range(4, 64):
        generation = 1 + (index - 4) // 6
        source = (index - 4) % 4
        events.append(
            TransmissionEvent(index, source, generation * 720)
        )
    return tuple(events)


def build_fixture(*, seed: int = 11, key: bytes = b"a" * 32):
    return build_institution_surveillance_episode(
        seed=seed,
        transmission_events=synthetic_trace(),
        population_size=1000,
        episode_decision_minute=DECISION,
        terminal_minute=HORIZON,
        counterfactual_infections={0: 24, 720: 31, 2160: 45},
        presentation_key=key,
    )


class SurveillancePipelineTests(unittest.TestCase):
    def test_frozen_profile_has_parameter_provenance(self):
        profile = load_gi_surveillance_profile()
        self.assertEqual(
            profile["profile_status"], "literature_anchored_experimental"
        )
        self.assertEqual(profile["pathogen"], "norovirus")
        for value in profile["parameters"].values():
            self.assertTrue(value["status"])
            self.assertTrue(value["source"].startswith("https://"))

    def test_fixed_trace_and_presentation_are_deterministic(self):
        first = build_fixture()
        second = build_fixture()
        self.assertEqual(first, second)

    def test_presentation_key_changes_ids_not_latent_science(self):
        first = build_fixture(key=b"a" * 32)
        second = build_fixture(key=b"b" * 32)
        first_ids = {
            item.observation_id for item in first.bundle.public.observations
        }
        second_ids = {
            item.observation_id for item in second.bundle.public.observations
        }
        self.assertTrue(first_ids.isdisjoint(second_ids))
        self.assertEqual(first.diagnostics, second.diagnostics)
        self.assertEqual(
            first.bundle.oracle.counterfactual_metrics,
            second.bundle.oracle.counterfactual_metrics,
        )
        self.assertEqual(
            sorted(item.kind for item in first.bundle.public.observations),
            sorted(item.kind for item in second.bundle.public.observations),
        )
        first_lineage = [
            (
                item.latent_agent_id,
                item.fact_minute,
                item.intrinsic_available_minute,
                item.mechanism,
                item.truth,
            )
            for item in first.lineage
        ]
        second_lineage = [
            (
                item.latent_agent_id,
                item.fact_minute,
                item.intrinsic_available_minute,
                item.mechanism,
                item.truth,
            )
            for item in second.lineage
        ]
        self.assertEqual(first_lineage, second_lineage)

    def test_observation_lineage_and_alert_are_chronologically_coherent(self):
        episode = build_fixture()
        lineage = {item.observation_id: item for item in episode.lineage}
        alerts = [
            item for item in episode.bundle.public.observations if item.kind == "alert"
        ]
        self.assertEqual(len(alerts), 1)
        initial_encounters = [
            item
            for item in episode.bundle.public.observations
            if item.kind == "encounter" and item.release_key == "initial"
        ]
        self.assertEqual(
            alerts[0].payload["observed_count"], len(initial_encounters)
        )
        for observation in episode.bundle.public.observations:
            private = lineage[observation.observation_id]
            self.assertLessEqual(
                private.fact_minute,
                DECISION + max(0, private.intrinsic_available_minute),
            )
            if observation.release_key == "initial":
                self.assertEqual(observation.available_minute, 0)
            if observation.release_key.startswith(("interview:", "test:")):
                self.assertEqual(observation.available_minute, 0)

    def test_no_requested_fact_can_precede_subject_reveal_plus_tool_latency(self):
        episode = build_fixture(seed=0)
        lineage = {item.observation_id: item for item in episode.lineage}
        first_reveal: dict[str, int] = {}
        for item in episode.bundle.public.observations:
            if item.subject_id is None or item.release_key.startswith(
                ("interview:", "test:")
            ):
                continue
            first_reveal[item.subject_id] = min(
                first_reveal.get(item.subject_id, 10**9), item.available_minute
            )
        for item in episode.bundle.public.observations:
            if item.subject_id is None:
                continue
            if item.release_key.startswith("interview:"):
                latency = 120
            elif item.release_key.startswith("test:"):
                latency = 360
            else:
                continue
            self.assertIn(item.subject_id, first_reveal)
            effective_release = first_reveal[item.subject_id] + latency
            self.assertLessEqual(
                lineage[item.observation_id].fact_minute,
                DECISION + effective_release,
            )

    def test_every_decisive_record_is_reachable_before_deadline(self):
        episode = build_fixture()
        observations = {
            item.observation_id: item for item in episode.bundle.public.observations
        }
        first_reveal: dict[str, int] = {}
        for item in observations.values():
            if item.subject_id is not None and not item.release_key.startswith(
                ("interview:", "test:")
            ):
                first_reveal[item.subject_id] = min(
                    first_reveal.get(item.subject_id, 10**9), item.available_minute
                )
        for observation_id in episode.bundle.oracle.decisive_evidence_ids:
            item = observations[observation_id]
            if item.release_key.startswith("interview:"):
                reachable = first_reveal[item.subject_id] + 120
            elif item.release_key.startswith("test:"):
                reachable = first_reveal[item.subject_id] + 360
            else:
                reachable = item.available_minute
            self.assertLessEqual(reachable, 36 * 60)

    def test_trace_order_does_not_change_observation_draws(self):
        normal = build_fixture()
        reversed_episode = build_institution_surveillance_episode(
            seed=11,
            transmission_events=tuple(reversed(synthetic_trace())),
            population_size=1000,
            episode_decision_minute=DECISION,
            terminal_minute=HORIZON,
            counterfactual_infections={0: 24, 720: 31, 2160: 45},
            presentation_key=b"a" * 32,
        )
        self.assertEqual(normal, reversed_episode)

    def test_hidden_counterfactual_outcomes_do_not_change_public_episode(self):
        first = build_fixture()
        second = build_institution_surveillance_episode(
            seed=11,
            transmission_events=synthetic_trace(),
            population_size=1000,
            episode_decision_minute=DECISION,
            terminal_minute=HORIZON,
            counterfactual_infections={0: 10, 720: 20, 2160: 30},
            presentation_key=b"a" * 32,
        )
        self.assertEqual(first.bundle.public, second.bundle.public)
        self.assertEqual(first.lineage, second.lineage)
        self.assertEqual(first.diagnostics, second.diagnostics)
        self.assertNotEqual(
            first.bundle.oracle.action_utility_curves,
            second.bundle.oracle.action_utility_curves,
        )

    def test_stream_records_are_time_gated(self):
        episode = build_fixture()
        stream = sorted(
            (
                item
                for item in episode.bundle.public.observations
                if item.release_key == "stream"
            ),
            key=lambda item: item.available_minute,
        )
        self.assertTrue(stream)
        environment = InvestigationEnvironment(episode.bundle.public)
        environment.search_observations()
        first_minute = stream[0].available_minute
        if first_minute > 1:
            self.assertEqual(environment.advance_time(first_minute - 1), [])
            released = environment.advance_time(1)
        else:
            released = environment.advance_time(first_minute)
        self.assertTrue(released)
        self.assertTrue(
            all(item["available_minute"] <= first_minute for item in released)
        )

    def test_public_episode_contains_no_simulator_parameters(self):
        episode = build_fixture()
        serialized = json.dumps(
            {
                "manifest": episode.bundle.public.manifest,
                "observations": [
                    item.public_dict()
                    for item in episode.bundle.public.observations
                ],
            },
            sort_keys=True,
        )
        for forbidden in (
            "random_seed",
            "daily_transmission_hazard",
            "initial_prevalence",
            "transmission_multiplier",
            "configuration_sha256",
            "latent_agent_id",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_starsim_backend_fails_closed_for_unsupported_family(self):
        with self.assertRaisesRegex(ValueError, "supports only"):
            StarsimSurveillanceBackend().create_scored_episode(
                seed=1,
                family="restaurant_point_source",
                presentation_key=b"x" * 32,
            )


@unittest.skipUnless(HAS_STARSIM, "install the starsim extra")
class StarsimSurveillanceIntegrationTests(unittest.TestCase):
    def test_scored_backend_has_causal_observations_and_outcomes(self):
        episode = StarsimSurveillanceBackend().create_scored_episode(
            seed=7, presentation_key=b"x" * 32
        )
        self.assertTrue(episode.bundle.oracle.is_outbreak)
        self.assertGreaterEqual(episode.diagnostics.initial_positive_labs, 3)
        metrics = episode.bundle.oracle.counterfactual_metrics
        self.assertGreater(
            metrics["counterfactual_no_action_infections"],
            metrics["counterfactual_early_control_infections"],
        )
        self.assertTrue(episode.bundle.oracle.action_utility_curves)

    def test_spawned_broker_scores_starsim_episode_without_private_fields(self):
        session, client = launch_secure_episode(
            seed=7,
            family="institution_person_to_person",
            backend="starsim",
        )
        try:
            submission = run_scripted_baseline(client)
            scorecard = session.score(submission)
            self.assertTrue(scorecard["valid"])
            self.assertEqual(
                scorecard["metrics"]["response_utility_profile_id"],
                "gi_surveillance_v2",
            )
            serialized = json.dumps(
                {"manifest": client.manifest, "submission": submission}
            )
            self.assertNotIn("daily_transmission_hazard", serialized)
            self.assertNotIn("random_seed", serialized)
        finally:
            client.close()
            session.close()

    def test_crn_noop_control_preserves_infection_history(self):
        config = StarsimSIRConfig(
            random_seed=29,
            n_agents=250,
            horizon_days=6,
            timestep_minutes=360,
            n_contacts=10,
            beta=0.04,
            initial_prevalence=0.02,
            infectious_days=3,
        )
        factual = StarsimDiseaseEngine(config)
        noop = StarsimDiseaseEngine(config)
        try:
            noop.apply_control(
                EngineControl(
                    control_id="noop",
                    kind=GLOBAL_TRANSMISSION_MULTIPLIER,
                    effective_minute=2 * DAY,
                    magnitude=1.0,
                )
            )
            factual.advance_to(6 * DAY)
            noop.advance_to(6 * DAY)
            self.assertEqual(
                factual.oracle_snapshot().transmission_events,
                noop.oracle_snapshot().transmission_events,
            )
        finally:
            factual.close()
            noop.close()


if __name__ == "__main__":
    unittest.main()
