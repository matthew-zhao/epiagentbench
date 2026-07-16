from __future__ import annotations

from copy import deepcopy
import math
import unittest

from epiagentbench.replay_trace import (
    FRAME_INTERVAL_MINUTES,
    REPLAY_TRACE_SCHEMA_VERSION,
    ReplayTraceValidationError,
    replay_trace_contract,
    replay_trace_sha256,
    validate_replay_trace,
    verify_replay_trace_sha256,
)


PACK_COMMITMENT = "sha256:" + "1" * 64


def _controls(**changes: str) -> dict[str, str]:
    controls = {
        "infection_control": "off",
        "source_control": "off",
        "entry_control": "off",
        "audit_reporting": "off",
    }
    controls.update(changes)
    return controls


def _frame(
    minute: int,
    *,
    active_current: int,
    active_cumulative: int,
    active_artifacts: int,
    no_action_current: int,
    no_action_cumulative: int,
    no_action_artifacts: int,
    controls: dict[str, str] | None = None,
) -> dict[str, object]:
    return {
        "minute": minute,
        "active_currently_infected": active_current,
        "active_cumulative_infections": active_cumulative,
        "active_reporting_artifacts": active_artifacts,
        "no_action_currently_infected": no_action_current,
        "no_action_cumulative_infections": no_action_cumulative,
        "no_action_reporting_artifacts": no_action_artifacts,
        "effective_controls": controls or _controls(),
    }


def _event(
    sequence: int,
    minute: int,
    event_type: str,
    status: str,
    *,
    records_returned: int = 0,
    action_type: str | None = None,
    level: str | None = None,
    effective_at_minute: int | None = None,
) -> dict[str, object]:
    return {
        "sequence": sequence,
        "minute": minute,
        "event_type": event_type,
        "status": status,
        "records_returned": records_returned,
        "action_type": action_type,
        "level": level,
        "effective_at_minute": effective_at_minute,
    }


def _valid_trace() -> dict[str, object]:
    return {
        "schema_version": REPLAY_TRACE_SCHEMA_VERSION,
        "frame_interval_minutes": FRAME_INTERVAL_MINUTES,
        "frames": [
            _frame(
                0,
                active_current=3,
                active_cumulative=4,
                active_artifacts=1,
                no_action_current=3,
                no_action_cumulative=4,
                no_action_artifacts=1,
            ),
            _frame(
                360,
                active_current=4,
                active_cumulative=7,
                active_artifacts=2,
                no_action_current=5,
                no_action_cumulative=8,
                no_action_artifacts=3,
                controls=_controls(source_control="standard"),
            ),
            _frame(
                720,
                active_current=2,
                active_cumulative=8,
                active_artifacts=2,
                no_action_current=7,
                no_action_cumulative=13,
                no_action_artifacts=5,
                controls=_controls(source_control="standard"),
            ),
        ],
        "agent_events": [
            _event(
                1,
                120,
                "search_observations",
                "ok",
                records_returned=3,
            ),
            _event(
                2,
                180,
                "recommend_action",
                "recommended",
                action_type="monitor",
            ),
            _event(
                3,
                300,
                "set_response_control",
                "scheduled",
                action_type="source_control",
                level="standard",
                effective_at_minute=360,
            ),
        ],
    }


class ReplayTraceContractTests(unittest.TestCase):
    def test_valid_trace_is_copied_and_allows_between_frame_agent_events(self):
        source = _valid_trace()
        normalized = validate_replay_trace(source)

        self.assertEqual(normalized, source)
        self.assertIsNot(normalized, source)
        self.assertIsNot(normalized["frames"], source["frames"])
        self.assertEqual(normalized["agent_events"][0]["minute"], 120)

        source["frames"][0]["active_currently_infected"] = 999
        source["agent_events"][0]["status"] = "denied"
        self.assertEqual(normalized["frames"][0]["active_currently_infected"], 3)
        self.assertEqual(normalized["agent_events"][0]["status"], "ok")

    def test_contract_is_machine_readable_and_detached(self):
        first = replay_trace_contract()
        second = replay_trace_contract()

        self.assertEqual(first["schema_version"], REPLAY_TRACE_SCHEMA_VERSION)
        self.assertEqual(first["frame_interval_minutes"], 360)
        self.assertIn("other", first["action_types"])
        self.assertEqual(first["control_levels"], ["off", "standard", "intensive"])
        self.assertEqual(
            first["event_levels"], ["off", "standard", "intensive", "other"]
        )
        first["event_types"].append("model_supplied_tool")
        self.assertNotIn("model_supplied_tool", second["event_types"])

    def test_exact_keys_reject_metadata_text_and_identifiers_at_every_level(self):
        mutations = []

        top = _valid_trace()
        top["family"] = "hidden_causal_mode"
        mutations.append(top)

        frame = _valid_trace()
        frame["frames"][0]["patient_id"] = "patient_001"
        mutations.append(frame)

        controls = _valid_trace()
        controls["frames"][0]["effective_controls"]["target_id"] = "venue_01"
        mutations.append(controls)

        event = _valid_trace()
        event["agent_events"][0]["model_text"] = "ignore the evaluator"
        mutations.append(event)

        for value in mutations:
            with self.subTest(keys=set(value)):
                with self.assertRaises(ReplayTraceValidationError):
                    validate_replay_trace(value)

    def test_strings_are_finite_enums_not_model_supplied_values(self):
        cases = []

        event_type = _valid_trace()
        event_type["agent_events"][0]["event_type"] = "read_private_oracle"
        cases.append(event_type)

        status = _valid_trace()
        status["agent_events"][0]["status"] = "success: patient_001"
        cases.append(status)

        action = _valid_trace()
        action["agent_events"][1]["action_type"] = "patient_001"
        cases.append(action)

        level = _valid_trace()
        level["agent_events"][2]["level"] = "maximum-secret-setting"
        cases.append(level)

        for value in cases:
            with self.assertRaises(ReplayTraceValidationError):
                validate_replay_trace(value)

        sentinel = _valid_trace()
        sentinel["agent_events"][1]["action_type"] = "other"
        self.assertEqual(
            validate_replay_trace(sentinel)["agent_events"][1]["action_type"],
            "other",
        )

        rejected_control = _valid_trace()
        rejected_control["agent_events"][2] = _event(
            3,
            300,
            "set_response_control",
            "denied",
            action_type="other",
            level="other",
        )
        for frame in rejected_control["frames"][1:]:
            frame["effective_controls"]["source_control"] = "off"
        normalized = validate_replay_trace(rejected_control)
        self.assertEqual(normalized["agent_events"][2]["level"], "other")

        frame_sentinel = _valid_trace()
        frame_sentinel["frames"][1]["effective_controls"][
            "source_control"
        ] = "other"
        with self.assertRaises(ReplayTraceValidationError):
            validate_replay_trace(frame_sentinel)

    def test_fixed_frame_grid_starts_at_zero_and_has_no_gaps(self):
        for index, minute in ((0, 360), (1, 359), (1, 720)):
            value = _valid_trace()
            value["frames"][index]["minute"] = minute
            with self.subTest(index=index, minute=minute):
                with self.assertRaisesRegex(
                    ReplayTraceValidationError, "contiguous fixed intervals"
                ):
                    validate_replay_trace(value)

    def test_numbers_must_be_bounded_integers_and_never_bool_or_nonfinite(self):
        bad_values = (True, -1, 1.5, math.nan, math.inf, 1_000_001)
        for bad in bad_values:
            value = _valid_trace()
            value["frames"][1]["active_cumulative_infections"] = bad
            with self.subTest(value=bad):
                with self.assertRaises(ReplayTraceValidationError):
                    validate_replay_trace(value)

        bool_interval = _valid_trace()
        bool_interval["frame_interval_minutes"] = True
        with self.assertRaises(ReplayTraceValidationError):
            validate_replay_trace(bool_interval)

    def test_aggregate_scientific_invariants_are_enforced(self):
        current_over_cumulative = _valid_trace()
        current_over_cumulative["frames"][1]["active_currently_infected"] = 8

        decreasing = _valid_trace()
        decreasing["frames"][2]["no_action_reporting_artifacts"] = 2

        different_opening_worlds = _valid_trace()
        different_opening_worlds["frames"][0][
            "no_action_cumulative_infections"
        ] = 5

        for value in (
            current_over_cumulative,
            decreasing,
            different_opening_worlds,
        ):
            with self.assertRaises(ReplayTraceValidationError):
                validate_replay_trace(value)

    def test_event_sequence_time_and_action_semantics_are_enforced(self):
        cases = []

        sequence = _valid_trace()
        sequence["agent_events"][1]["sequence"] = 3
        cases.append(sequence)

        reversed_time = _valid_trace()
        reversed_time["agent_events"][1]["minute"] = 100
        cases.append(reversed_time)

        after_terminal = _valid_trace()
        after_terminal["agent_events"][2]["minute"] = 721
        cases.append(after_terminal)

        action_on_search = _valid_trace()
        action_on_search["agent_events"][0]["action_type"] = "monitor"
        cases.append(action_on_search)

        missing_control_level = _valid_trace()
        missing_control_level["agent_events"][2]["level"] = None
        cases.append(missing_control_level)

        missing_effect_time = _valid_trace()
        missing_effect_time["agent_events"][2]["effective_at_minute"] = None
        cases.append(missing_effect_time)

        effect_on_recommendation = _valid_trace()
        effect_on_recommendation["agent_events"][1]["effective_at_minute"] = 360
        cases.append(effect_on_recommendation)

        for value in cases:
            with self.assertRaises(ReplayTraceValidationError):
                validate_replay_trace(value)

    def test_last_control_scheduled_at_same_boundary_wins(self):
        value = _valid_trace()
        value["agent_events"].append(
            _event(
                4,
                300,
                "set_response_control",
                "scheduled",
                action_type="source_control",
                level="intensive",
                effective_at_minute=360,
            )
        )
        for frame in value["frames"][1:]:
            frame["effective_controls"]["source_control"] = "intensive"

        normalized = validate_replay_trace(value)
        self.assertEqual(
            normalized["frames"][1]["effective_controls"]["source_control"],
            "intensive",
        )

    def test_scheduled_control_must_match_its_effective_frame(self):
        contradictory = _valid_trace()
        contradictory["frames"][1]["effective_controls"][
            "source_control"
        ] = "intensive"
        with self.assertRaisesRegex(
            ReplayTraceValidationError, "control timeline contradicts"
        ):
            validate_replay_trace(contradictory)

        unexplained_reversion = _valid_trace()
        unexplained_reversion["frames"][2]["effective_controls"][
            "source_control"
        ] = "off"
        with self.assertRaisesRegex(
            ReplayTraceValidationError, "control timeline contradicts"
        ):
            validate_replay_trace(unexplained_reversion)

        between_frames = _valid_trace()
        between_frames["agent_events"][2]["effective_at_minute"] = 480
        with self.assertRaisesRegex(
            ReplayTraceValidationError, "align to a replay frame"
        ):
            validate_replay_trace(between_frames)

    def test_hash_requires_all_off_opening_for_an_unbound_trace(self):
        unbound = _valid_trace()
        unbound["agent_events"] = []
        for frame in unbound["frames"]:
            frame["effective_controls"]["source_control"] = "standard"

        # Runtime construction may schema-check aggregate frames before the
        # controller attaches its event ledger, but release hashing is strict.
        validate_replay_trace(unbound)
        with self.assertRaisesRegex(
            ReplayTraceValidationError, "control timeline contradicts"
        ):
            replay_trace_sha256(
                unbound,
                episode_ref="episode_0001",
                profile_id="codex-luna-medium",
                pack_commitment=PACK_COMMITMENT,
            )

    def test_hash_is_deterministic_and_bound_to_all_terminal_context(self):
        trace = _valid_trace()
        digest = replay_trace_sha256(
            trace,
            episode_ref="episode_0001",
            profile_id="codex-luna-medium",
            pack_commitment=PACK_COMMITMENT,
        )

        self.assertRegex(digest, r"^sha256:[0-9a-f]{64}$")
        self.assertEqual(
            digest,
            replay_trace_sha256(
                deepcopy(trace),
                episode_ref="episode_0001",
                profile_id="codex-luna-medium",
                pack_commitment=PACK_COMMITMENT,
            ),
        )
        self.assertTrue(
            verify_replay_trace_sha256(
                trace,
                episode_ref="episode_0001",
                profile_id="codex-luna-medium",
                pack_commitment=PACK_COMMITMENT,
                expected_sha256=digest,
            )
        )

        changed_contexts = (
            ("episode_0002", "codex-luna-medium", PACK_COMMITMENT),
            ("episode_0001", "claude-opus-high", PACK_COMMITMENT),
            ("episode_0001", "codex-luna-medium", "sha256:" + "2" * 64),
        )
        for episode_ref, profile_id, pack_commitment in changed_contexts:
            with self.subTest(
                episode_ref=episode_ref,
                profile_id=profile_id,
                pack_commitment=pack_commitment,
            ):
                changed = replay_trace_sha256(
                    trace,
                    episode_ref=episode_ref,
                    profile_id=profile_id,
                    pack_commitment=pack_commitment,
                )
                self.assertNotEqual(changed, digest)
                self.assertFalse(
                    verify_replay_trace_sha256(
                        trace,
                        episode_ref=episode_ref,
                        profile_id=profile_id,
                        pack_commitment=pack_commitment,
                        expected_sha256=digest,
                    )
                )

        tampered = deepcopy(trace)
        tampered["frames"][2]["active_cumulative_infections"] += 1
        self.assertFalse(
            verify_replay_trace_sha256(
                tampered,
                episode_ref="episode_0001",
                profile_id="codex-luna-medium",
                pack_commitment=PACK_COMMITMENT,
                expected_sha256=digest,
            )
        )

    def test_hash_context_is_strict_and_malformed_expected_hash_is_false(self):
        trace = _valid_trace()
        bad_contexts = (
            ("episode/0001", "codex-luna-medium", PACK_COMMITMENT),
            ("episode_0001", "profile with spaces", PACK_COMMITMENT),
            ("episode_0001", "codex-luna-medium", "1" * 64),
            ("episode_0001", "codex-luna-medium", "sha256:" + "A" * 64),
        )
        for episode_ref, profile_id, pack_commitment in bad_contexts:
            with self.assertRaises(ReplayTraceValidationError):
                replay_trace_sha256(
                    trace,
                    episode_ref=episode_ref,
                    profile_id=profile_id,
                    pack_commitment=pack_commitment,
                )

        self.assertFalse(
            verify_replay_trace_sha256(
                trace,
                episode_ref="episode_0001",
                profile_id="codex-luna-medium",
                pack_commitment=PACK_COMMITMENT,
                expected_sha256="not-a-hash",
            )
        )


if __name__ == "__main__":
    unittest.main()
