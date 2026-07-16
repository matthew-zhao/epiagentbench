"""Strict, aggregate-only contract for terminal replay traces.

Replay traces are evaluator artifacts.  They intentionally contain no agent
text, public or private identifiers, contact edges, event subjects, mechanism
labels, or simulator parameters.  A trace may be released only after an
episode has terminated and its digest has been bound to the episode, harness
profile, and frozen episode-pack commitment.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import hmac
import json
import re
from typing import Any, Mapping


REPLAY_TRACE_SCHEMA_VERSION = "epiagentbench.aggregate-replay-trace.v1"
FRAME_INTERVAL_MINUTES = 360

_MAX_FRAMES = 512
_MAX_AGENT_EVENTS = 1_024
_MAX_AGGREGATE_COUNT = 1_000_000

_TRACE_KEYS = frozenset(
    {
        "schema_version",
        "frame_interval_minutes",
        "frames",
        "agent_events",
    }
)
_FRAME_KEYS = frozenset(
    {
        "minute",
        "active_currently_infected",
        "active_cumulative_infections",
        "active_reporting_artifacts",
        "no_action_currently_infected",
        "no_action_cumulative_infections",
        "no_action_reporting_artifacts",
        "effective_controls",
    }
)
_EVENT_KEYS = frozenset(
    {
        "sequence",
        "minute",
        "event_type",
        "status",
        "records_returned",
        "action_type",
        "level",
        "effective_at_minute",
    }
)

_CONTROL_TYPES = (
    "infection_control",
    "source_control",
    "entry_control",
    "audit_reporting",
)
_CONTROL_LEVELS = ("off", "standard", "intensive")
# Rejected control attempts may contain an arbitrary model-supplied level.  The
# replay records only this sentinel; frame state remains restricted to the
# three real control levels above.
_EVENT_LEVELS = (*_CONTROL_LEVELS, "other")
_EVENT_TYPES = (
    "search_observations",
    "request_interview",
    "order_confirmatory_test",
    "request_inspection",
    "advance_time",
    "recommend_action",
    "set_institution_control",
    "set_response_control",
    "submit_forecast",
    "get_clock_and_budget",
)
_EVENT_STATUSES = (
    "ok",
    "scheduled",
    "no_change",
    "not_found",
    "duplicate_request",
    "unavailable_before_deadline",
    "unsupported",
    "unavailable",
    "too_soon",
    "submitted",
    "recommended",
    "denied",
    "pending_approval",
)
_ACTION_TYPES = (
    *_CONTROL_TYPES,
    # Evaluator-side normalization target for arbitrary denied recommendations.
    # The model-supplied value itself must never enter the replay artifact.
    "other",
    "monitor",
    "request_inspection",
    "notify_health_officer",
    "public_alert",
    "close_business",
    "publish_pii",
    "quarantine_person",
)

_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
_SHA256 = re.compile(r"sha256:[0-9a-f]{64}")
_HASH_DOMAIN = b"EpiAgentBench aggregate replay trace v1\x00"


class ReplayTraceValidationError(ValueError):
    """Raised when an aggregate replay trace violates its closed schema."""


def replay_trace_contract() -> dict[str, Any]:
    """Return a detached, machine-readable description of the trace contract."""

    return {
        "schema_version": REPLAY_TRACE_SCHEMA_VERSION,
        "frame_interval_minutes": FRAME_INTERVAL_MINUTES,
        "max_frames": _MAX_FRAMES,
        "max_agent_events": _MAX_AGENT_EVENTS,
        "max_aggregate_count": _MAX_AGGREGATE_COUNT,
        "trace_keys": sorted(_TRACE_KEYS),
        "frame_keys": sorted(_FRAME_KEYS),
        "event_keys": sorted(_EVENT_KEYS),
        "control_types": list(_CONTROL_TYPES),
        "control_levels": list(_CONTROL_LEVELS),
        "event_levels": list(_EVENT_LEVELS),
        "event_types": list(_EVENT_TYPES),
        "event_statuses": list(_EVENT_STATUSES),
        "action_types": list(_ACTION_TYPES),
    }


def validate_replay_trace(
    value: Any, *, require_complete_control_timeline: bool = False
) -> dict[str, Any]:
    """Validate and return a deep-safe canonical copy of one replay trace.

    The schema is deliberately closed at every level.  The only permitted
    strings are finite enum values and the fixed schema version, which keeps
    arbitrary model text, subject identifiers, and simulator metadata out of
    an artifact intended for visualization.
    """

    trace = _require_mapping(value, "trace")
    _require_exact_keys(trace, _TRACE_KEYS, "trace")
    if trace["schema_version"] != REPLAY_TRACE_SCHEMA_VERSION:
        raise ReplayTraceValidationError("trace.schema_version is unsupported")
    if (
        type(trace["frame_interval_minutes"]) is not int
        or trace["frame_interval_minutes"] != FRAME_INTERVAL_MINUTES
    ):
        raise ReplayTraceValidationError(
            "trace.frame_interval_minutes must equal the fixed interval"
        )

    frames_value = trace["frames"]
    if type(frames_value) is not list:
        raise ReplayTraceValidationError("trace.frames must be a list")
    if not frames_value or len(frames_value) > _MAX_FRAMES:
        raise ReplayTraceValidationError("trace.frames has an invalid length")

    frames: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    for index, frame_value in enumerate(frames_value):
        frame = _validate_frame(frame_value, index)
        if frame["minute"] != index * FRAME_INTERVAL_MINUTES:
            raise ReplayTraceValidationError(
                "trace.frames must start at zero and be contiguous fixed intervals"
            )
        if previous is not None:
            for key in (
                "active_cumulative_infections",
                "active_reporting_artifacts",
                "no_action_cumulative_infections",
                "no_action_reporting_artifacts",
            ):
                if frame[key] < previous[key]:
                    raise ReplayTraceValidationError(
                        "trace cumulative aggregate counts must not decrease"
                    )
        frames.append(frame)
        previous = frame

    opening = frames[0]
    for suffix in (
        "currently_infected",
        "cumulative_infections",
        "reporting_artifacts",
    ):
        if opening[f"active_{suffix}"] != opening[f"no_action_{suffix}"]:
            raise ReplayTraceValidationError(
                "trace active and no-action branches must share an opening state"
            )

    events_value = trace["agent_events"]
    if type(events_value) is not list:
        raise ReplayTraceValidationError("trace.agent_events must be a list")
    if len(events_value) > _MAX_AGENT_EVENTS:
        raise ReplayTraceValidationError("trace.agent_events is too long")
    terminal_minute = frames[-1]["minute"]
    events: list[dict[str, Any]] = []
    previous_minute = 0
    for index, event_value in enumerate(events_value):
        event = _validate_event(event_value, index, terminal_minute)
        if index and event["minute"] < previous_minute:
            raise ReplayTraceValidationError(
                "trace.agent_events must be ordered by simulated minute"
            )
        events.append(event)
        previous_minute = event["minute"]

    _validate_scheduled_control_events(
        frames,
        events,
        require_complete=(require_complete_control_timeline or bool(events)),
    )

    # Constructing the return value field-by-field, followed by deepcopy,
    # prevents custom Mapping/List subclasses and mutable aliases from crossing
    # the validation boundary.
    return deepcopy(
        {
            "schema_version": REPLAY_TRACE_SCHEMA_VERSION,
            "frame_interval_minutes": FRAME_INTERVAL_MINUTES,
            "frames": frames,
            "agent_events": events,
        }
    )


def replay_trace_sha256(
    trace: Any,
    *,
    episode_ref: str,
    profile_id: str,
    pack_commitment: str,
) -> str:
    """Return a domain-separated digest bound to terminal release context."""

    normalized = validate_replay_trace(
        trace, require_complete_control_timeline=True
    )
    _require_identifier(episode_ref, "episode_ref")
    _require_identifier(profile_id, "profile_id")
    if type(pack_commitment) is not str or not _SHA256.fullmatch(pack_commitment):
        raise ReplayTraceValidationError(
            "pack_commitment must be a lowercase sha256 commitment"
        )
    payload = {
        "episode_ref": episode_ref,
        "profile_id": profile_id,
        "pack_commitment": pack_commitment,
        "schema_version": REPLAY_TRACE_SCHEMA_VERSION,
        "trace": normalized,
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
    return "sha256:" + hashlib.sha256(_HASH_DOMAIN + encoded).hexdigest()


def verify_replay_trace_sha256(
    trace: Any,
    *,
    episode_ref: str,
    profile_id: str,
    pack_commitment: str,
    expected_sha256: str,
) -> bool:
    """Verify a context-bound trace digest using constant-time comparison."""

    if type(expected_sha256) is not str or not _SHA256.fullmatch(expected_sha256):
        return False
    actual = replay_trace_sha256(
        trace,
        episode_ref=episode_ref,
        profile_id=profile_id,
        pack_commitment=pack_commitment,
    )
    return hmac.compare_digest(actual, expected_sha256)


def _validate_frame(value: Any, index: int) -> dict[str, Any]:
    frame = _require_mapping(value, f"trace.frames[{index}]")
    _require_exact_keys(frame, _FRAME_KEYS, f"trace.frames[{index}]")
    minute = _require_count(frame["minute"], "frame.minute")
    counts = {
        key: _require_count(frame[key], f"frame.{key}")
        for key in (
            "active_currently_infected",
            "active_cumulative_infections",
            "active_reporting_artifacts",
            "no_action_currently_infected",
            "no_action_cumulative_infections",
            "no_action_reporting_artifacts",
        )
    }
    if counts["active_currently_infected"] > counts[
        "active_cumulative_infections"
    ] or counts["no_action_currently_infected"] > counts[
        "no_action_cumulative_infections"
    ]:
        raise ReplayTraceValidationError(
            "trace current infection counts cannot exceed cumulative infections"
        )

    controls = _require_mapping(frame["effective_controls"], "frame.controls")
    _require_exact_keys(controls, frozenset(_CONTROL_TYPES), "frame.controls")
    normalized_controls: dict[str, str] = {}
    for action in _CONTROL_TYPES:
        level = controls[action]
        if type(level) is not str or level not in _CONTROL_LEVELS:
            raise ReplayTraceValidationError(
                "trace control levels must use the finite level enum"
            )
        normalized_controls[action] = level

    return {
        "minute": minute,
        **counts,
        "effective_controls": normalized_controls,
    }


def _validate_event(
    value: Any, index: int, terminal_minute: int
) -> dict[str, Any]:
    event = _require_mapping(value, f"trace.agent_events[{index}]")
    _require_exact_keys(event, _EVENT_KEYS, f"trace.agent_events[{index}]")
    sequence = _require_count(event["sequence"], "event.sequence")
    if sequence != index + 1:
        raise ReplayTraceValidationError(
            "trace agent event sequences must be contiguous and one-based"
        )
    minute = _require_count(event["minute"], "event.minute")
    if minute > terminal_minute:
        raise ReplayTraceValidationError(
            "trace agent events cannot occur after the terminal frame"
        )
    records_returned = _require_count(
        event["records_returned"], "event.records_returned"
    )

    event_type = event["event_type"]
    if type(event_type) is not str or event_type not in _EVENT_TYPES:
        raise ReplayTraceValidationError(
            "trace event_type must use the finite event enum"
        )
    status = event["status"]
    if type(status) is not str or status not in _EVENT_STATUSES:
        raise ReplayTraceValidationError(
            "trace event status must use the finite status enum"
        )

    action_type = event["action_type"]
    if action_type is not None and (
        type(action_type) is not str or action_type not in _ACTION_TYPES
    ):
        raise ReplayTraceValidationError(
            "trace action_type must be null or use the finite action enum"
        )
    level = event["level"]
    if level is not None and (type(level) is not str or level not in _EVENT_LEVELS):
        raise ReplayTraceValidationError(
            "trace event level must be null or use the finite event-level enum"
        )
    effective_at_minute = event["effective_at_minute"]
    if effective_at_minute is not None:
        effective_at_minute = _require_count(
            effective_at_minute, "event.effective_at_minute"
        )
        if not minute <= effective_at_minute <= terminal_minute:
            raise ReplayTraceValidationError(
                "trace control effect minute is outside the episode"
            )

    rejected_control = status == "denied" and event_type in {
        "set_institution_control",
        "set_response_control",
    }
    if event_type == "set_institution_control":
        if action_type != "infection_control" or level is None or (
            not rejected_control and level not in _CONTROL_LEVELS
        ):
            raise ReplayTraceValidationError(
                "institution-control events require their finite action and level"
            )
    elif event_type == "set_response_control":
        permitted_actions = (
            (*_CONTROL_TYPES, "other") if rejected_control else _CONTROL_TYPES
        )
        if action_type not in permitted_actions or level is None or (
            not rejected_control and level not in _CONTROL_LEVELS
        ):
            raise ReplayTraceValidationError(
                "response-control events require a finite control and level"
            )
    elif event_type == "recommend_action":
        if action_type not in _ACTION_TYPES or level is not None:
            raise ReplayTraceValidationError(
                "recommendation events require only a finite action"
            )
    elif action_type is not None or level is not None:
        raise ReplayTraceValidationError(
            "non-action events cannot carry action or level fields"
        )

    is_control_event = event_type in {
        "set_institution_control",
        "set_response_control",
    }
    if not is_control_event and effective_at_minute is not None:
        raise ReplayTraceValidationError(
            "only control events can carry an effect minute"
        )
    if is_control_event:
        if status == "scheduled" and effective_at_minute is None:
            raise ReplayTraceValidationError(
                "scheduled control events require an effect minute"
            )
        if status != "scheduled" and effective_at_minute is not None:
            raise ReplayTraceValidationError(
                "unscheduled control events cannot carry an effect minute"
            )

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


def _validate_scheduled_control_events(
    frames: list[dict[str, Any]],
    events: list[dict[str, Any]],
    *,
    require_complete: bool,
) -> None:
    """Derive and verify the complete control state from scheduled events.

    Several requests can become effective at the same frame boundary.  The
    simulator applies them in request order, so the final scheduled level for
    each action at that boundary wins and persists until a later change.

    A simulator-owned trace is schema-validated once before the controller has
    attached events, so an empty internal event list may defer this check.  All
    terminal traces and all traces already carrying events are checked fully.
    """

    scheduled_by_minute: dict[int, list[dict[str, Any]]] = {}
    frame_by_minute = {frame["minute"]: frame for frame in frames}
    for event in events:
        if event["status"] != "scheduled" or event["event_type"] not in {
            "set_institution_control",
            "set_response_control",
        }:
            continue
        effective_at_minute = event["effective_at_minute"]
        action_type = event["action_type"]
        level = event["level"]
        # _validate_event has already proved these are concrete values.
        assert isinstance(effective_at_minute, int)
        assert isinstance(action_type, str)
        assert isinstance(level, str)
        if effective_at_minute not in frame_by_minute:
            raise ReplayTraceValidationError(
                "trace scheduled control effects must align to a replay frame"
            )
        if effective_at_minute == 0:
            raise ReplayTraceValidationError(
                "trace opening controls must be all off"
            )
        scheduled_by_minute.setdefault(effective_at_minute, []).append(event)

    if not require_complete:
        return

    expected = {action_type: "off" for action_type in _CONTROL_TYPES}
    for frame in frames:
        for event in scheduled_by_minute.get(frame["minute"], []):
            # Events were validated and retained in replay sequence order.
            expected[event["action_type"]] = event["level"]
        if frame["effective_controls"] != expected:
            raise ReplayTraceValidationError(
                "trace control timeline contradicts scheduled agent events"
            )


def _require_mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ReplayTraceValidationError(f"{path} must be an object")
    if any(type(key) is not str for key in value):
        raise ReplayTraceValidationError(f"{path} keys must be strings")
    return value


def _require_exact_keys(
    value: Mapping[str, Any], expected: frozenset[str], path: str
) -> None:
    if set(value) != expected:
        raise ReplayTraceValidationError(f"{path} must have the exact schema keys")


def _require_count(value: Any, path: str) -> int:
    if type(value) is not int or not 0 <= value <= _MAX_AGGREGATE_COUNT:
        raise ReplayTraceValidationError(
            f"{path} must be a bounded non-negative integer"
        )
    return value


def _require_identifier(value: Any, path: str) -> None:
    if type(value) is not str or not _IDENTIFIER.fullmatch(value):
        raise ReplayTraceValidationError(f"{path} must be a bounded identifier")
