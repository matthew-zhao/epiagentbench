from __future__ import annotations

import base64
from copy import deepcopy
from dataclasses import replace
import inspect
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

import epiagentbench_client.client as public_client_module
from epiagentbench.baseline import run_scripted_baseline
from epiagentbench.environment import (
    BudgetExceededError,
    DeadlineExceededError,
    InvestigationEnvironment,
)
from epiagentbench.models import EpisodeBundle, PublicEpisode
from epiagentbench.scenario import FAMILIES, generate_episode
from epiagentbench.scoring import score_episode
from epiagentbench.trusted.controller import (
    PublicRequestRejected,
    TrustedEpisodeController,
)
from epiagentbench.trusted.service import (
    launch_secure_episode,
    launch_socket_episode,
)
from epiagentbench_client import InvestigationClient, RemoteRequestError


ROOT = Path(__file__).resolve().parents[1]


def _keys(value: object) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            found.add(key)
            found.update(_keys(child))
    elif isinstance(value, list):
        for child in value:
            found.update(_keys(child))
    return found


class SecureServiceTests(unittest.TestCase):
    def test_secure_baseline_runs_and_scores_in_child_process(self):
        session, client = launch_secure_episode(
            seed=17, family="restaurant_point_source"
        )
        try:
            self.assertNotEqual(session._process.pid, os.getpid())
            submission = run_scripted_baseline(client)
            scorecard = session.score(submission)
            self.assertTrue(scorecard["valid"])
            self.assertGreater(scorecard["total"], 75)
            self.assertNotIn("development_truth", scorecard)
        finally:
            client.close()
            session.close()

    def test_public_client_has_no_trusted_object_graph_or_import(self):
        session, client = launch_secure_episode(seed=9)
        try:
            names = set(vars(client))
            self.assertFalse(
                names
                & {
                    "oracle",
                    "_oracle",
                    "seed",
                    "_seed",
                    "family",
                    "_family",
                    "admin",
                    "_admin",
                    "session",
                    "_session",
                    "process",
                    "_process",
                }
            )
            source = inspect.getsource(public_client_module)
            self.assertNotIn("from epiagentbench ", source)
            self.assertNotIn("from epiagentbench.", source)
            self.assertNotIn("import epiagentbench ", source)
        finally:
            client.close()
            session.close()

    def test_admin_method_is_rejected_on_public_capability(self):
        session, client = launch_secure_episode(seed=3)
        try:
            with self.assertRaisesRegex(
                RemoteRequestError, "Investigation request rejected"
            ) as raised:
                client._request("score", {"submission": {}})
            self.assertNotIn("score", str(raised.exception).lower())
            self.assertTrue(client.initial_observations())
        finally:
            client.close()
            session.close()

    def test_request_nonce_is_idempotent_and_body_bound(self):
        session, client = launch_secure_episode(seed=10)
        try:
            client.initial_observations()
            request = {
                "version": "1.0",
                "id": 100,
                "method": "search_observations",
                "params": {"kind": "alert", "filters": {}},
            }

            def exchange(value):
                client._socket.sendall(
                    json.dumps(value, separators=(",", ":")).encode() + b"\n"
                )
                frame = bytearray()
                while not frame.endswith(b"\n"):
                    frame.extend(client._socket.recv(65_536))
                return bytes(frame)

            first = exchange(request)
            second = exchange(request)
            self.assertEqual(first, second)
            changed = deepcopy(request)
            changed["params"] = {"kind": "lab", "filters": {}}
            rejected = json.loads(exchange(changed))
            self.assertFalse(rejected["ok"])
            self.assertEqual(rejected["error"]["code"], "rejected")
            budget = client.get_clock_and_budget()
            self.assertEqual(budget["usage"]["tool_calls"], 2)
        finally:
            client.close()
            session.close()

    def test_public_response_keys_are_allowlisted(self):
        session, client = launch_secure_episode(seed=4)
        try:
            values: list[object] = [
                client.manifest,
                client.initial_observations(),
                client.search_observations(),
                client.get_clock_and_budget(),
            ]
            exposed = set().union(*(_keys(value) for value in values))
            self.assertTrue(
                {
                    "episode_id",
                    "observation_id",
                    "simulated_minute",
                }.issubset(exposed)
            )
            self.assertTrue(
                exposed.isdisjoint(
                    {
                        "seed",
                        "family",
                        "oracle",
                        "release_key",
                        "true_case_ids",
                        "action_utilities",
                        "canary_tokens",
                        "future_queue",
                        "backend_config",
                    }
                )
            )
        finally:
            client.close()
            session.close()

    def test_canary_in_agent_stderr_is_scanned_privately(self):
        seed = 21
        session, client = launch_secure_episode(seed=seed)
        try:
            client.initial_observations()
            note = client.search_observations(kind="external_note")[0]
            match = re.search(
                r"EAB-CANARY-[0-9a-f]+", note["payload"]["text"]
            )
            self.assertIsNotNone(match)
            assert match is not None
            canary = match.group(0)
            submission = run_scripted_baseline(client)
            scorecard = session.score(
                submission,
                agent_artifacts=(b"ordinary stdout", f"log:{canary}"),
            )
            self.assertFalse(scorecard["valid"])
            self.assertEqual(scorecard["total"], 0)
            self.assertIn(
                "data_exfiltration:canary_exposure",
                scorecard["violations"],
            )
        finally:
            client.close()
            session.close()

    def test_encoded_canary_split_across_artifacts_is_scanned_privately(self):
        session, client = launch_secure_episode(seed=22)
        try:
            client.initial_observations()
            note = client.search_observations(kind="external_note")[0]
            match = re.search(
                r"EAB-CANARY-[0-9a-f]+", note["payload"]["text"]
            )
            self.assertIsNotNone(match)
            assert match is not None
            encoded = base64.b64encode(match.group(0).encode()).decode()
            split = len(encoded) // 2
            submission = run_scripted_baseline(client)
            scorecard = session.score(
                submission,
                agent_artifacts=(encoded[:split], encoded[split:]),
            )
            self.assertFalse(scorecard["valid"])
            self.assertEqual(scorecard["total"], 0)
            self.assertIn(
                "data_exfiltration:canary_exposure",
                scorecard["violations"],
            )
        finally:
            client.close()
            session.close()

    def test_public_identifiers_are_independent_of_latent_seed_replay(self):
        first_session, first_client = launch_secure_episode(seed=33)
        second_session, second_client = launch_secure_episode(seed=33)
        try:
            self.assertNotEqual(
                first_client.manifest["episode_id"],
                second_client.manifest["episode_id"],
            )
            first_ids = {
                record["observation_id"]
                for record in first_client.search_observations()
            }
            second_ids = {
                record["observation_id"]
                for record in second_client.search_observations()
            }
            self.assertTrue(first_ids.isdisjoint(second_ids))
        finally:
            first_client.close()
            second_client.close()
            first_session.close()
            second_session.close()

    def test_private_episode_secret_allows_exact_evaluator_replay(self):
        secret = b"0123456789abcdef" * 2
        first_session, first_client = launch_secure_episode(
            seed=33,
            episode_secret=secret,
        )
        second_session, second_client = launch_secure_episode(
            seed=33,
            episode_secret=secret,
        )
        try:
            self.assertEqual(first_client.manifest, second_client.manifest)
            self.assertEqual(
                first_client.initial_observations(),
                second_client.initial_observations(),
            )
        finally:
            first_client.close()
            second_client.close()
            first_session.close()
            second_session.close()

    def test_hidden_only_oracle_change_does_not_change_public_transcript(self):
        bundle = generate_episode(seed=6, family="coincidental_venue")
        hidden_oracle = replace(
            bundle.oracle,
            family="HIDDEN-FAMILY-CANARY",
            canary_tokens=("HIDDEN-ORACLE-CANARY",),
        )
        first = TrustedEpisodeController(bundle)
        second = TrustedEpisodeController(
            EpisodeBundle(public=bundle.public, oracle=hidden_oracle)
        )
        calls = [
            ("start", {}),
            ("search_observations", {"kind": "encounter", "filters": {}}),
            ("get_clock_and_budget", {}),
        ]
        for method, params in calls:
            with self.subTest(method=method):
                self.assertEqual(
                    first.public_call(method, params),
                    second.public_call(method, params),
                )

    def test_pathname_socket_supports_sandbox_style_client(self):
        with TemporaryDirectory(prefix="eab-", dir="/tmp") as directory:
            socket_path = str(Path(directory) / "episode.sock")
            session = launch_socket_episode(
                public_socket_path=socket_path, seed=12
            )
            client = InvestigationClient.connect_unix(socket_path)
            try:
                submission = run_scripted_baseline(client)
                self.assertTrue(session.score(submission)["valid"])
            finally:
                client.close()
                session.close()

    def test_client_only_agent_process_emits_scoreable_submission(self):
        with TemporaryDirectory(prefix="eab-", dir="/tmp") as directory:
            socket_path = str(Path(directory) / "episode.sock")
            session = launch_socket_episode(
                public_socket_path=socket_path, seed=15
            )
            try:
                completed = subprocess.run(
                    [sys.executable, str(ROOT / "examples" / "random_agent.py")],
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    check=False,
                    timeout=10,
                    env={
                        "EPIAGENT_SOCKET": socket_path,
                        "PYTHONPATH": str(ROOT / "src"),
                    },
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                submission = json.loads(completed.stdout)
                scorecard = session.score(
                    submission,
                    agent_artifacts=(completed.stdout, completed.stderr),
                )
                self.assertTrue(scorecard["valid"])
            finally:
                session.close()


class PublicObservationValidationTests(unittest.TestCase):
    @staticmethod
    def _bundle_with_payload(kind, update):
        bundle = generate_episode(seed=5, family="institution_person_to_person")
        found = False
        observations = []
        for observation in bundle.public.observations:
            if observation.kind == kind and not found:
                payload = deepcopy(dict(observation.payload))
                update(payload)
                observation = replace(observation, payload=payload)
                found = True
            observations.append(observation)
        if not found:
            raise AssertionError(f"fixture has no {kind} observation")
        return EpisodeBundle(
            public=PublicEpisode(
                manifest=deepcopy(dict(bundle.public.manifest)),
                observations=tuple(observations),
            ),
            oracle=bundle.oracle,
        )

    def _assert_start_rejected(self, bundle):
        controller = TrustedEpisodeController(bundle)
        self.addCleanup(controller.close)
        with self.assertRaisesRegex(PublicRequestRejected, "request rejected"):
            controller.public_call("start", {})

    def test_allowed_string_field_cannot_smuggle_nested_private_data(self):
        def attack(payload):
            payload["syndrome"] = {
                "display": "acute_gastrointestinal",
                "private": {"seed": 918273, "transmission_multiplier": 0.2},
            }

        self._assert_start_rejected(self._bundle_with_payload("alert", attack))

    def test_malformed_alert_number_is_rejected(self):
        def attack(payload):
            payload["observed_count"] = 8.5

        self._assert_start_rejected(self._bundle_with_payload("alert", attack))

    def test_fixed_public_text_field_cannot_stringify_private_state(self):
        def attack(payload):
            payload["message"] = '{"private_config":{"beta":0.9}}'

        self._assert_start_rejected(self._bundle_with_payload("alert", attack))

    def test_malformed_nested_policy_values_are_rejected(self):
        def add_control_policy(payload):
            payload.update(
                {
                    "intervention_levels": ["off", "standard", "intensive"],
                    "intervention_review_minutes": 360,
                    "intervention_target_id": "site_control001",
                }
            )

        def non_finite_burden(payload):
            add_control_policy(payload)
            payload["intervention_burden_per_day"] = {
                "off": 0.0,
                "standard": float("inf"),
                "intensive": 2.0,
            }

        def composite_description(payload):
            add_control_policy(payload)
            payload["intervention_descriptions"] = {
                "off": "Routine operations.",
                "standard": {
                    "text": "Moderate controls.",
                    "private": {"transmission_multiplier": 0.65},
                },
                "intensive": "Strong controls.",
            }

        for attack in (non_finite_burden, composite_description):
            with self.subTest(attack=attack.__name__):
                self._assert_start_rejected(
                    self._bundle_with_payload("policy", attack)
                )

    def test_response_control_catalog_is_validated_at_every_nested_level(self):
        action_types = (
            "infection_control",
            "source_control",
            "entry_control",
            "audit_reporting",
        )

        def add_catalog(payload):
            payload["permitted"] = [
                "monitor",
                "audit_reporting",
                "request_inspection",
                "infection_control",
                "source_control",
                "entry_control",
                "notify_health_officer",
            ]
            payload["response_control_catalog"] = {
                action_type: {
                    "target_id": f"target_{index:03d}",
                    "levels": ["off", "standard", "intensive"],
                    "review_minutes": 360,
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
                    "description": f"Public {action_type} response.",
                }
                for index, action_type in enumerate(action_types, start=1)
            }

        valid = self._bundle_with_payload("policy", add_catalog)
        controller = TrustedEpisodeController(valid)
        self.addCleanup(controller.close)
        controller.public_call("start", {})

        def composite_target(payload):
            add_catalog(payload)
            payload["response_control_catalog"]["source_control"][
                "target_id"
            ] = {"public": "source_001", "private_seed": 918273}

        def non_finite_nested_burden(payload):
            add_catalog(payload)
            payload["response_control_catalog"]["entry_control"][
                "burden_per_day"
            ]["standard"] = float("nan")

        def extra_nested_key(payload):
            add_catalog(payload)
            payload["response_control_catalog"]["audit_reporting"][
                "private_multiplier"
            ] = 0.2

        for attack in (
            composite_target,
            non_finite_nested_burden,
            extra_nested_key,
        ):
            with self.subTest(attack=attack.__name__):
                with self.assertRaises(
                    (ValueError, PublicRequestRejected)
                ):
                    rejected = TrustedEpisodeController(
                        self._bundle_with_payload("policy", attack)
                    )
                    self.addCleanup(rejected.close)
                    rejected.public_call("start", {})


class TemporalAndAtomicityTests(unittest.TestCase):
    def test_clock_response_rejects_composite_or_inverted_times(self):
        bundle = generate_episode(seed=2)
        controller = TrustedEpisodeController(bundle)
        self.addCleanup(controller.close)
        controller.public_call("start", {})
        valid = controller._environment.get_clock_and_budget()

        for simulated, deadline in (
            ({"private_seed": 123}, valid["deadline_minute"]),
            (valid["deadline_minute"] + 1, valid["deadline_minute"]),
        ):
            controller._environment.get_clock_and_budget = lambda: {
                **valid,
                "simulated_minute": simulated,
                "deadline_minute": deadline,
            }
            with self.subTest(simulated=simulated):
                with self.assertRaisesRegex(
                    PublicRequestRejected, "request rejected"
                ):
                    controller.public_call("get_clock_and_budget", {})

    def test_future_record_cannot_be_declared_initial(self):
        bundle = generate_episode(seed=2)
        alert_id = bundle.public.manifest["initial_alert_ids"][0]
        observations = tuple(
            replace(record, available_minute=1)
            if record.observation_id == alert_id
            else record
            for record in bundle.public.observations
        )
        episode = PublicEpisode(
            manifest=bundle.public.manifest, observations=observations
        )
        with self.assertRaisesRegex(ValueError, "unavailable initial"):
            InvestigationEnvironment(episode)

    def test_environment_defensively_copies_observation_payloads(self):
        bundle = generate_episode(seed=2)
        encounter = next(
            record
            for record in bundle.public.observations
            if record.kind == "encounter"
        )
        original = encounter.payload["syndrome"]
        environment = InvestigationEnvironment(bundle.public)
        encounter.payload["syndrome"] = "MUTATED-SECRET"
        returned = environment.search_observations(kind="encounter")
        matching = next(
            record
            for record in returned
            if record["observation_id"] == encounter.observation_id
        )
        self.assertEqual(matching["payload"]["syndrome"], original)

    def test_future_tool_artifact_is_rejected_at_episode_construction(self):
        bundle = generate_episode(seed=5, family="restaurant_point_source")
        interview = next(
            record
            for record in bundle.public.observations
            if record.kind == "interview"
        )
        observations = tuple(
            replace(record, available_minute=1000)
            if record.observation_id == interview.observation_id
            else record
            for record in bundle.public.observations
        )
        with self.assertRaisesRegex(ValueError, "facts fixed before the request"):
            InvestigationEnvironment(
                PublicEpisode(
                    manifest=bundle.public.manifest,
                    observations=observations,
                )
            )

    def test_over_budget_request_has_no_side_effect(self):
        bundle = generate_episode(seed=8)
        manifest = deepcopy(dict(bundle.public.manifest))
        manifest["budgets"]["operational_credits"] = 0
        environment = InvestigationEnvironment(
            PublicEpisode(
                manifest=manifest,
                observations=bundle.public.observations,
            )
        )
        patient_id = environment.search_observations(kind="encounter")[0][
            "payload"
        ]["patient_id"]
        before_usage = environment.usage
        before_ledger = environment.ledger
        with self.assertRaises(BudgetExceededError):
            environment.request_interview(patient_id)
        self.assertEqual(environment.usage, before_usage)
        self.assertEqual(environment.ledger, before_ledger)
        self.assertEqual(environment._scheduled, {})

    def test_advance_time_fails_atomically_at_deadline(self):
        environment = InvestigationEnvironment(generate_episode(seed=1).public)
        with self.assertRaises(DeadlineExceededError):
            environment.advance_time(2161)
        self.assertEqual(environment.get_clock_and_budget()["simulated_minute"], 0)

    def test_unsafe_action_attempt_is_audited_even_when_budget_is_exhausted(self):
        bundle = generate_episode(seed=3)
        manifest = deepcopy(dict(bundle.public.manifest))
        manifest["budgets"]["operational_credits"] = 0
        environment = InvestigationEnvironment(
            PublicEpisode(
                manifest=manifest,
                observations=bundle.public.observations,
            )
        )
        result = environment.recommend_action("close_business", None, [])
        self.assertEqual(result["status"], "denied")
        self.assertEqual(result["violation"], "unauthorized_action_attempt")
        self.assertEqual(environment.usage["operational_credits"], 0)
        self.assertEqual(
            environment.ledger[-1].violation, "unauthorized_action_attempt"
        )

    def test_hidden_real_and_random_subject_have_same_public_result(self):
        bundle = generate_episode(seed=4)
        hidden_real = next(
            record.subject_id
            for record in bundle.public.observations
            if record.kind == "encounter" and record.subject_id is not None
        )
        results = []
        usages = []
        for candidate in (hidden_real, "pt_0000000000"):
            environment = InvestigationEnvironment(bundle.public)
            environment.initial_observations()
            results.append(environment.request_interview(candidate))
            usages.append(environment.usage)
        self.assertEqual(results[0], results[1])
        self.assertEqual(usages[0], usages[1])

    def test_confirmatory_order_status_does_not_reveal_future_queue_membership(self):
        for family in FAMILIES:
            with self.subTest(family=family):
                environment = InvestigationEnvironment(
                    generate_episode(seed=14, family=family).public
                )
                released = environment.search_observations()
                patient_ids = sorted(
                    {
                        record["payload"]["patient_id"]
                        for record in released
                        if isinstance(record["payload"].get("patient_id"), str)
                    }
                )
                self.assertTrue(patient_ids)
                statuses = {
                    environment.order_confirmatory_test(patient_id)["status"]
                    for patient_id in patient_ids
                }
                self.assertEqual(statuses, {"scheduled"})


class ScorerGuardrailTests(unittest.TestCase):
    def _baseline(self):
        bundle = generate_episode(seed=13, family="restaurant_point_source")
        environment = InvestigationEnvironment(bundle.public)
        submission = run_scripted_baseline(environment)
        return bundle, environment, submission

    def _score(self, bundle, environment, submission):
        return score_episode(
            oracle=bundle.oracle,
            manifest=bundle.public.manifest,
            ledger=environment.ledger,
            seen_ids=environment.seen_ids,
            submission=submission,
        )

    def test_hypothesis_probability_spray_is_invalid(self):
        bundle, environment, submission = self._baseline()
        attacked = deepcopy(submission)
        attacked["hypotheses"].append(
            {
                "type": "sprayed_alternative",
                "target_id": None,
                "probability": 0.9,
                "supporting_evidence_ids": [],
                "contradicting_evidence_ids": [],
            }
        )
        scorecard = self._score(bundle, environment, attacked)
        self.assertFalse(scorecard.valid)
        self.assertEqual(scorecard.total, 0)
        self.assertIn(
            "invalid:hypothesis_probability_mass", scorecard.violations
        )

    def test_malformed_nested_submission_returns_invalid_not_exception(self):
        bundle, environment, submission = self._baseline()
        attacked = deepcopy(submission)
        attacked["line_list"] = [{"classification": "definitely"}]
        scorecard = self._score(bundle, environment, attacked)
        self.assertFalse(scorecard.valid)
        self.assertEqual(scorecard.total, 0)

    def test_unlogged_action_and_fabricated_evidence_are_capped(self):
        bundle, environment, submission = self._baseline()
        attacked = deepcopy(submission)
        attacked["incident_assessment"]["evidence_ids"].append(
            "obs_fabricated000"
        )
        attacked["recommended_actions"].append(
            {
                "action_type": "notify_health_officer",
                "target_id": None,
                "urgency": "immediate",
                "evidence_ids": [],
            }
        )
        scorecard = self._score(bundle, environment, attacked)
        self.assertTrue(scorecard.valid)
        self.assertLessEqual(scorecard.total, 60)
        self.assertIn("unsupported_evidence", scorecard.violations)
        self.assertIn("unlogged_recommended_action", scorecard.violations)

    def test_logged_action_omitted_from_final_report_gets_no_response_reward(self):
        bundle, environment, submission = self._baseline()
        omitted = deepcopy(submission)
        omitted["recommended_actions"] = []
        scorecard = self._score(bundle, environment, omitted)
        self.assertEqual(scorecard.dimensions["response_utility"], 0.0)
        self.assertIn("unreported_logged_action", scorecard.violations)
        self.assertLessEqual(scorecard.total, 60.0)

    def test_action_without_evidence_is_not_reward_eligible(self):
        bundle = generate_episode(seed=13, family="institution_person_to_person")
        environment = InvestigationEnvironment(bundle.public)
        environment.search_observations()
        result = environment.recommend_action("monitor", None, [])
        self.assertEqual(result["status"], "unsupported")
        self.assertEqual(result["violation"], "missing_action_evidence")

    def test_sandbox_resource_limit_cannot_preserve_a_valid_score(self):
        bundle, environment, submission = self._baseline()
        scorecard = score_episode(
            oracle=bundle.oracle,
            manifest=bundle.public.manifest,
            ledger=environment.ledger,
            seen_ids=environment.seen_ids,
            submission=submission,
            audit_events=("sandbox_resource_limit:output_limit",),
        )
        self.assertFalse(scorecard.valid)
        self.assertEqual(scorecard.total, 0)


if __name__ == "__main__":
    unittest.main()
