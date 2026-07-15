from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
import unittest

from epiagentbench.trusted.engine import TransmissionEvent
from epiagentbench.trusted.live_surveillance import (
    DAY_MINUTES,
    IncrementalSurveillanceStream,
)
from epiagentbench.trusted.surveillance import load_gi_surveillance_profile


DECISION = 8 * DAY_MINUTES
DEADLINE = 5 * DAY_MINUTES
KEY = b"live-surveillance-test-key-0001"


def observable_profile(*, background_rate: float = 0.0):
    profile = deepcopy(load_gi_surveillance_profile())
    values = {
        "symptomatic_probability": 1.0,
        "care_seeking_probability": 1.0,
        "stool_given_care_probability": 1.0,
        "routine_institution_reporting_probability": 0.0,
        "routine_reporting_specimen_probability": 1.0,
        "preliminary_test_sensitivity": 1.0,
        "confirmatory_test_sensitivity": 1.0,
        "test_specificity": 1.0,
        "interview_recall_probability": 1.0,
        "background_gi_episodes_per_person_year": background_rate,
    }
    for name, value in values.items():
        profile["parameters"][name]["value"] = value
    profile["parameters"]["incubation_days"]["median"] = 0.2
    profile["parameters"]["incubation_days"]["geometric_sd"] = 1.0001
    return profile


def make_stream(
    *,
    seed: int = 17,
    profile=None,
    key: bytes = KEY,
    population_size: int = 1000,
    causal_mode: str = "person_to_person",
    artifact_duplicate_count: int = 0,
) -> IncrementalSurveillanceStream:
    return IncrementalSurveillanceStream(
        seed=seed,
        presentation_key=key,
        profile=profile or observable_profile(),
        population_size=population_size,
        decision_minute=DECISION,
        deadline_minutes=DEADLINE,
        causal_mode=causal_mode,
        artifact_duplicate_count=artifact_duplicate_count,
    )


def observations_by_id(stream: IncrementalSurveillanceStream):
    return {item.observation_id: item for item in stream.all_observations}


class IncrementalSurveillanceTests(unittest.TestCase):
    def test_cumulative_or_delta_ingest_creates_each_record_once(self):
        first = TransmissionEvent(7, None, DECISION - 2 * DAY_MINUTES)
        second = TransmissionEvent(11, 7, DECISION - DAY_MINUTES)
        stream = make_stream()

        first_records = stream.ingest((first, first))
        self.assertTrue(first_records)
        self.assertEqual(stream.ingest((first,)), ())
        second_records = stream.ingest((second, first))
        self.assertTrue(second_records)
        self.assertEqual(stream.ingest((second,)), ())
        self.assertTrue(
            set(item.observation_id for item in first_records).isdisjoint(
                item.observation_id for item in second_records
            )
        )

    def test_trace_order_and_batching_do_not_change_public_catalog(self):
        events = (
            TransmissionEvent(2, None, DECISION - 3 * DAY_MINUTES),
            TransmissionEvent(8, 2, DECISION - 2 * DAY_MINUTES),
            TransmissionEvent(4, 8, DECISION - DAY_MINUTES),
        )
        together = make_stream()
        together.ingest(tuple(reversed(events)))
        together_episode = together.bootstrap()

        incremental = make_stream()
        for event in events:
            incremental.ingest((event,))
        incremental_episode = incremental.bootstrap()
        self.assertEqual(together_episode, incremental_episode)
        self.assertEqual(together.true_case_ids, incremental.true_case_ids)
        self.assertEqual(
            together.decisive_evidence_ids,
            incremental.decisive_evidence_ids,
        )

    def test_latent_transmission_edge_never_changes_interview_claims(self):
        parent_a = TransmissionEvent(0, None, DECISION - 3 * DAY_MINUTES)
        parent_b = TransmissionEvent(1, None, DECISION - 3 * DAY_MINUTES)
        from_a = make_stream()
        from_a.ingest(
            (parent_a, parent_b, TransmissionEvent(2, 0, DECISION - DAY_MINUTES))
        )
        from_b = make_stream()
        from_b.ingest(
            (parent_a, parent_b, TransmissionEvent(2, 1, DECISION - DAY_MINUTES))
        )

        self.assertEqual(from_a.bootstrap(), from_b.bootstrap())
        serialized = json.dumps(
            [item.public_dict() for item in from_a.all_observations],
            sort_keys=True,
        )
        self.assertNotIn("source_agent", serialized)
        self.assertNotIn("mechanism", serialized)

    def test_preventing_one_infection_does_not_shift_unrelated_person(self):
        retained = TransmissionEvent(20, None, DECISION - 2 * DAY_MINUTES)
        preventable = TransmissionEvent(21, None, DECISION - 2 * DAY_MINUTES)
        both = make_stream()
        both.ingest((retained, preventable))
        both.bootstrap()
        controlled = make_stream()
        controlled.ingest((retained,))
        controlled.bootstrap()

        common_ids = set(observations_by_id(both)) & set(observations_by_id(controlled))
        common_non_alerts = {
            item
            for item in common_ids
            if observations_by_id(both)[item].kind != "alert"
        }
        self.assertTrue(common_non_alerts)
        for observation_id in common_non_alerts:
            self.assertEqual(
                observations_by_id(both)[observation_id],
                observations_by_id(controlled)[observation_id],
            )

    def test_background_records_use_action_independent_randomness(self):
        profile = load_gi_surveillance_profile()
        without_infections = make_stream(seed=1, profile=profile)
        without_infections.bootstrap()
        background_ids = {
            item.observation_id
            for item in without_infections.all_observations
            if item.subject_id is not None
        }
        self.assertTrue(background_ids)

        with_infections = make_stream(seed=1, profile=profile)
        with_infections.ingest(
            tuple(
                TransmissionEvent(index, None, DECISION - DAY_MINUTES)
                for index in range(20)
            )
        )
        with_infections.bootstrap()
        second = observations_by_id(with_infections)
        first = observations_by_id(without_infections)
        for observation_id in background_ids:
            self.assertEqual(first[observation_id], second[observation_id])

    def test_bootstrap_contains_future_and_request_only_records(self):
        stream = make_stream()
        # Infection precedes the decision, but incubation and reporting place
        # this person's encounter in the live post-decision stream.
        stream.ingest((TransmissionEvent(4, None, DECISION - 60),))
        episode = stream.bootstrap()
        patient_id = next(iter(stream.true_case_ids))
        patient_records = [
            item for item in episode.observations if item.subject_id == patient_id
        ]
        self.assertTrue(
            any(
                item.release_key == "stream" and item.available_minute > 0
                for item in patient_records
            )
        )
        self.assertEqual(
            {
                item.available_minute
                for item in patient_records
                if item.release_key.startswith(("interview:", "test:"))
            },
            {0},
        )

    def test_dynamic_ingest_returns_registerable_records_and_drain_is_once_only(self):
        initial = TransmissionEvent(1, None, DECISION - 2 * DAY_MINUTES)
        later = TransmissionEvent(3, 1, DECISION + 60)
        stream = make_stream()
        stream.ingest((initial,))
        bootstrapped_ids = {
            item.observation_id for item in stream.bootstrap().observations
        }

        created = stream.ingest((initial, later))
        self.assertTrue(created)
        self.assertTrue(
            bootstrapped_ids.isdisjoint(item.observation_id for item in created)
        )
        self.assertEqual(stream.drain(), created)
        self.assertEqual(stream.drain(), ())
        self.assertEqual(stream.ingest((later,)), ())
        self.assertTrue(
            all(
                item.release_key == "stream"
                or item.release_key.startswith(("interview:", "test:"))
                for item in created
            )
        )

    def test_intervention_receipt_is_a_stream_record(self):
        stream = make_stream()
        stream.bootstrap()
        record = stream.add_intervention_status(1, "intensive", 360)
        self.assertEqual(record.release_key, "stream")
        self.assertEqual(record.kind, "intervention_status")
        self.assertEqual(record.subject_id, stream.institution_id)
        self.assertEqual(record.payload["action_type"], "infection_control")
        self.assertEqual(record.payload["target_id"], stream.institution_id)
        self.assertEqual(record.payload["level"], "intensive")
        self.assertEqual(record.payload["effective_at_minute"], 360)
        self.assertIn(record, stream.all_observations)
        with self.assertRaisesRegex(ValueError, "sequence"):
            stream.add_intervention_status(1, "off", 720)
        with self.assertRaisesRegex(ValueError, "unknown"):
            stream.add_intervention_status(2, "maximum", 720)

        generic = stream.add_response_control_status(
            "source_control", stream.food_service_id, 2, "standard", 720
        )
        self.assertEqual(generic.subject_id, stream.food_service_id)
        self.assertEqual(generic.payload["action_type"], "source_control")
        with self.assertRaisesRegex(ValueError, "target"):
            stream.add_response_control_status(
                "entry_control", stream.food_service_id, 3, "standard", 1080
            )

    def test_manifest_policy_alert_and_initial_diagnostics_are_coherent(self):
        stream = make_stream()
        stream.ingest(
            (
                TransmissionEvent(0, None, DECISION - 3 * DAY_MINUTES),
                TransmissionEvent(1, 0, DECISION - 2 * DAY_MINUTES),
                TransmissionEvent(2, 1, DECISION - DAY_MINUTES),
            )
        )
        episode = stream.bootstrap()
        manifest = episode.manifest
        start = datetime.fromisoformat(manifest["start_time"])
        deadline = datetime.fromisoformat(manifest["deadline"])
        self.assertEqual(int((deadline - start).total_seconds() / 60), DEADLINE)
        self.assertIn("request_inspection", manifest["enabled_tools"])
        self.assertIn("set_institution_control", manifest["enabled_tools"])
        self.assertIn("set_response_control", manifest["enabled_tools"])
        self.assertIn("submit_forecast", manifest["enabled_tools"])

        policy = next(item for item in episode.observations if item.kind == "policy")
        self.assertEqual(
            policy.payload["intervention_levels"],
            ["off", "standard", "intensive"],
        )
        self.assertEqual(policy.payload["intervention_review_minutes"], 360)
        self.assertEqual(
            policy.payload["intervention_outcome_horizon_days"], 21
        )
        self.assertIs(
            policy.payload["intervention_persists_until_changed"], True
        )
        self.assertEqual(
            policy.payload["intervention_burden_units"],
            "utility_points_per_day",
        )
        self.assertEqual(policy.payload["forecast_target"], "new_encounters")
        self.assertEqual(policy.payload["forecast_horizon_minutes"], DAY_MINUTES)
        self.assertEqual(policy.payload["forecast_minimum_submissions"], 2)
        self.assertEqual(policy.payload["forecast_review_minutes"], DAY_MINUTES)
        self.assertEqual(
            policy.payload["forecast_scoring_rule"],
            "symmetric_log_gaussian_base_2",
        )
        catalog = policy.payload["response_control_catalog"]
        self.assertEqual(
            list(catalog),
            [
                "infection_control",
                "source_control",
                "entry_control",
                "audit_reporting",
            ],
        )
        self.assertEqual(
            catalog["source_control"]["target_id"], stream.food_service_id
        )
        self.assertEqual(
            catalog["source_control"]["setup_credits"]["standard"], 8
        )
        self.assertEqual(
            set(catalog["source_control"]),
            {
                "target_id",
                "levels",
                "review_minutes",
                "burden_per_day",
                "setup_credits",
                "description",
            },
        )
        alert = next(item for item in episode.observations if item.kind == "alert")
        initial_encounters = [
            item
            for item in episode.observations
            if item.kind == "encounter" and item.release_key == "initial"
        ]
        self.assertEqual(alert.payload["observed_count"], len(initial_encounters))
        self.assertEqual(stream.initial_alert_count, len(initial_encounters))
        self.assertEqual(stream.initial_diagnostics.secondary_infections, 2)
        self.assertEqual(
            stream.initial_diagnostics.true_cases,
            len(stream.true_case_ids),
        )
        self.assertTrue(stream.decisive_evidence_ids)

    def test_response_catalog_uses_configured_public_costs_when_present(self):
        profile = observable_profile()
        profile["closed_loop_configuration"]["response_controls"] = {
            "source_control": {
                "description": "Configured food-service response.",
                "levels": {
                    "standard": {
                        "burden_per_day": 0.9,
                        "setup_credits": 13,
                    }
                },
            }
        }
        stream = make_stream(profile=profile)
        policy = next(
            item for item in stream.bootstrap().observations if item.kind == "policy"
        )
        control = policy.payload["response_control_catalog"]["source_control"]
        self.assertEqual(control["burden_per_day"]["standard"], 0.9)
        self.assertEqual(control["setup_credits"]["standard"], 13)
        self.assertEqual(control["description"], "Configured food-service response.")

    def test_investigation_gold_is_frozen_at_bootstrap(self):
        stream = make_stream()
        initial = (
            TransmissionEvent(0, None, DECISION - 3 * DAY_MINUTES),
            TransmissionEvent(1, 0, DECISION - 2 * DAY_MINUTES),
            TransmissionEvent(2, 1, DECISION - DAY_MINUTES),
        )
        stream.ingest(initial)
        stream.bootstrap()
        frozen_cases = stream.investigation_true_case_ids
        frozen_evidence = stream.investigation_decisive_evidence_ids

        stream.ingest(
            initial + (TransmissionEvent(3, 2, DECISION + 10),)
        )

        self.assertEqual(stream.investigation_true_case_ids, frozen_cases)
        self.assertEqual(
            stream.investigation_decisive_evidence_ids,
            frozen_evidence,
        )
        followup = stream.followup_true_case_observation_ids
        self.assertEqual(len(followup), 1)
        self.assertEqual(
            stream.followup_relevant_evidence_ids,
            frozenset(next(iter(followup.values())))
            & stream.decisive_evidence_ids,
        )

    def test_alert_expectation_uses_the_same_care_or_reporting_process(self):
        profile = observable_profile(background_rate=0.6)
        profile["parameters"]["care_seeking_probability"]["value"] = 0.2
        profile["parameters"]["routine_institution_reporting_probability"][
            "value"
        ] = 0.5
        stream = make_stream(profile=profile)
        alert = next(
            item
            for item in stream.bootstrap().observations
            if item.kind == "alert"
        )
        detected_probability = 1 - (1 - 0.2) * (1 - 0.5)
        expected = round(1000 * 0.6 * 7 / 365 * detected_probability)
        self.assertEqual(alert.payload["historical_expected"], expected)

    def test_public_surface_has_relative_nonnegative_times_and_no_private_fields(self):
        stream = make_stream(seed=42)
        stream.ingest(
            (
                TransmissionEvent(97, None, DECISION - 2 * DAY_MINUTES),
                TransmissionEvent(103, 97, DECISION - DAY_MINUTES),
            )
        )
        episode = stream.bootstrap()
        serialized = json.dumps(
            {
                "manifest": episode.manifest,
                "observations": [item.public_dict() for item in episode.observations],
            },
            sort_keys=True,
        )
        self.assertTrue(
            all(item.available_minute >= 0 for item in episode.observations)
        )
        for forbidden in (
            "target_agent_id",
            "source_agent_id",
            "infection_minute",
            "random_seed",
            "daily_transmission_hazard",
            "transmission_multiplier",
            "configuration_sha256",
            "latent_agent_id",
            "causal_mode",
            "mechanism",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_universal_targets_and_policy_catalog_do_not_reveal_mode(self):
        catalogs = []
        for causal_mode in (
            "person_to_person",
            "common_source",
            "repeated_introduction",
            "background",
            "reporting_artifact",
        ):
            stream = make_stream(causal_mode=causal_mode)
            episode = stream.bootstrap()
            self.assertEqual(
                stream.response_control_targets,
                {
                    "infection_control": stream.institution_id,
                    "source_control": stream.food_service_id,
                    "entry_control": stream.entry_program_id,
                    "audit_reporting": stream.reporting_system_id,
                },
            )
            policy = next(
                item for item in episode.observations if item.kind == "policy"
            )
            catalog = policy.payload["response_control_catalog"]
            catalogs.append(
                {
                    action_type: {
                        key: value
                        for key, value in entry.items()
                        if key != "target_id"
                    }
                    for action_type, entry in catalog.items()
                }
            )
            serialized = json.dumps(
                [item.public_dict() for item in episode.observations],
                sort_keys=True,
            )
            self.assertNotIn("causal_mode", serialized)
            self.assertNotIn('"mechanism"', serialized)
        self.assertTrue(all(item == catalogs[0] for item in catalogs[1:]))

    def test_mode_aware_interviews_are_noisy_but_investigable(self):
        events = tuple(
            TransmissionEvent(index, None, DECISION - 2 * DAY_MINUTES)
            for index in range(12)
        )

        common = make_stream(seed=29, causal_mode="common_source")
        common.ingest(events)
        common.bootstrap()
        common_interviews = [
            item.payload
            for item in common.all_observations
            if item.kind == "interview"
            and item.subject_id in common.true_case_ids
        ]
        food_recall = [
            item
            for item in common_interviews
            if item["exposure_id"] == common.food_service_id
        ]
        self.assertGreaterEqual(len(food_recall), 8)
        meal_days = {item["meal_day"] for item in food_recall}
        self.assertEqual(len(meal_days), 1)
        self.assertTrue(-4 <= next(iter(meal_days)) <= -1)

        imported = make_stream(seed=29, causal_mode="repeated_introduction")
        imported.ingest(events)
        imported.bootstrap()
        imported_interviews = [
            item.payload
            for item in imported.all_observations
            if item.kind == "interview"
            and item.subject_id in imported.true_case_ids
            and item.payload["exposure_type"] == "different_each_case"
        ]
        self.assertGreaterEqual(len(imported_interviews), 8)
        self.assertEqual(
            len({item["exposure_id"] for item in imported_interviews}),
            len(imported_interviews),
        )

        propagated = make_stream(seed=29, causal_mode="person_to_person")
        propagated.ingest(events)
        propagated.bootstrap()
        propagated_interviews = [
            item.payload
            for item in propagated.all_observations
            if item.kind == "interview"
            and item.subject_id in propagated.true_case_ids
            and item.payload["exposure_id"] == propagated.institution_id
        ]
        self.assertGreaterEqual(len(propagated_interviews), 8)
        self.assertGreaterEqual(
            sum(
                item.get("contact_with_symptomatic_person") is True
                for item in propagated_interviews
            ),
            6,
        )

    def test_reporting_artifact_adds_duplicate_reports_not_true_cases(self):
        stream = make_stream(causal_mode="reporting_artifact")
        episode = stream.bootstrap()
        reports = [
            item for item in episode.observations if item.kind == "case_report"
        ]
        self.assertEqual(len(reports), 6)
        self.assertLess(
            len({item.payload["patient_id"] for item in reports}), len(reports)
        )
        self.assertTrue(
            all(item.payload["source_system"] == "legacy_import" for item in reports)
        )
        self.assertEqual(stream.true_case_ids, frozenset())
        self.assertTrue(
            {item.observation_id for item in reports}.issubset(
                stream.investigation_decisive_evidence_ids
            )
        )
        alert = next(item for item in episode.observations if item.kind == "alert")
        initial_signal_records = [
            item
            for item in episode.observations
            if item.kind in {"encounter", "case_report"}
            and item.release_key == "initial"
        ]
        self.assertEqual(alert.payload["observed_count"], len(initial_signal_records))

    def test_audit_suppresses_only_due_future_reporting_artifacts(self):
        candidates = (
            (360, 100_000),
            (360, 900_000),
            (720, 200_000),
        )
        stream = make_stream(causal_mode="reporting_artifact")
        stream.bootstrap()
        initial_reports = len(
            [item for item in stream.all_observations if item.kind == "case_report"]
        )
        emitted = stream.materialize_reporting_artifact_candidates(
            candidates, through_public_minute=360, audit_level=0.5
        )
        self.assertEqual(len(emitted), 1)
        self.assertEqual(emitted[0].available_minute, 360)
        self.assertEqual(emitted[0].release_key, "stream")
        self.assertEqual(stream.total_emitted_reporting_artifacts, 1)

        # The suppressed 360-minute candidate cannot reappear after its due
        # time, and a fully effective audit suppresses the newly due candidate.
        self.assertEqual(
            stream.materialize_reporting_artifact_candidates(
                candidates, through_public_minute=720, audit_level=0.0
            ),
            (),
        )
        self.assertEqual(stream.total_emitted_reporting_artifacts, 1)
        self.assertEqual(
            len(
                [
                    item
                    for item in stream.all_observations
                    if item.kind == "case_report"
                ]
            ),
            initial_reports + 1,
        )
        self.assertEqual(stream.true_case_ids, frozenset())

        uncontrolled = make_stream(causal_mode="reporting_artifact")
        uncontrolled.bootstrap()
        uncontrolled_emitted = uncontrolled.materialize_reporting_artifact_candidates(
            candidates, through_public_minute=720, audit_level=1.0
        )
        self.assertEqual(len(uncontrolled_emitted), 3)
        self.assertEqual(uncontrolled.total_emitted_reporting_artifacts, 3)
        self.assertIn(emitted[0], uncontrolled_emitted)

    def test_inspections_are_fixed_request_only_records_for_every_target(self):
        stream = make_stream(causal_mode="common_source")
        episode = stream.bootstrap()
        inspections = [
            item for item in episode.observations if item.kind == "inspection"
        ]
        self.assertEqual(len(inspections), 4)
        self.assertEqual(
            {item.subject_id for item in inspections},
            set(stream.response_control_targets.values()),
        )
        for item in inspections:
            self.assertEqual(item.release_key, f"inspection:{item.subject_id}")
            self.assertEqual(
                set(item.payload),
                {"target_id", "target_type", "finding", "summary"},
            )
            self.assertEqual(item.payload["target_id"], item.subject_id)
            self.assertIn(
                item.payload["finding"],
                {
                    "material_concern",
                    "minor_irregularity",
                    "no_material_concern",
                },
            )
            self.assertEqual(
                stream.add_inspection_observation(item.subject_id), item
            )

    def test_rejects_conflicts_invalid_ancestry_and_late_predecision_events(self):
        stream = make_stream()
        with self.assertRaisesRegex(ValueError, "source"):
            stream.ingest((TransmissionEvent(4, 3, DECISION),))
        stream.ingest((TransmissionEvent(4, None, DECISION - DAY_MINUTES),))
        with self.assertRaisesRegex(ValueError, "cannot change"):
            stream.ingest((TransmissionEvent(4, None, DECISION),))
        stream.bootstrap()
        with self.assertRaisesRegex(ValueError, "pre-decision"):
            stream.ingest((TransmissionEvent(5, None, DECISION - 1),))


if __name__ == "__main__":
    unittest.main()
