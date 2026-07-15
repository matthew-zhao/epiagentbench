from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
import math
import re
from typing import Any

from .models import Budget, LedgerEntry, Observation, PublicEpisode


_PUBLIC_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,127}$")


class BudgetExceededError(RuntimeError):
    """Raised before a tool call whose costs would exceed its budget."""


class DeadlineExceededError(RuntimeError):
    """Raised before an operation that would pass the episode deadline."""


@dataclass(frozen=True, slots=True)
class InstitutionControlPlan:
    """Private, non-serializable authorization result for one control change."""

    level: str
    target_id: str | None
    evidence_ids: tuple[str, ...]
    unseen: tuple[str, ...]
    status: str
    violation: str | None
    analyst_minutes: int
    operational_credits: int

    @property
    def executable(self) -> bool:
        return self.status == "ready"


@dataclass(frozen=True, slots=True)
class ResponseControlPlan:
    """Private authorization result for one generic response control."""

    action_type: str
    level: str
    target_id: str | None
    evidence_ids: tuple[str, ...]
    unseen: tuple[str, ...]
    status: str
    violation: str | None
    analyst_minutes: int
    operational_credits: int

    @property
    def executable(self) -> bool:
        return self.status == "ready"


class InvestigationEnvironment:
    """Stateful reference tool environment.

    This class receives only public episode state. The trusted oracle belongs in
    a separate process in a production evaluation.
    """

    _ACTION_COSTS = {
        "monitor": 1,
        "audit_reporting": 5,
        "request_inspection": 15,
        "infection_control": 10,
        "notify_health_officer": 2,
        "public_alert": 20,
        "close_business": 50,
        "publish_pii": 50,
        "quarantine_person": 50,
    }
    _CONTROL_COSTS = {"off": 2, "standard": 10, "intensive": 20}
    _RESPONSE_CONTROL_TYPES = (
        "infection_control",
        "source_control",
        "entry_control",
        "audit_reporting",
    )
    _RESPONSE_CONTROL_LEVELS = ("off", "standard", "intensive")

    def __init__(self, episode: PublicEpisode):
        self._manifest = deepcopy(dict(episode.manifest))
        self._observations = {
            observation.observation_id: deepcopy(observation)
            for observation in episode.observations
        }
        budget_dict = dict(self._manifest["budgets"])
        self._budget = Budget(**budget_dict)
        self._clock = 0
        self._deadline_minute = self._parse_deadline_minute()
        self._ledger: list[LedgerEntry] = []
        self._seen_ids: set[str] = set()
        self._seen_at: dict[str, int] = {}
        self._known_public_ids: set[str] = set()
        self._released_ids: set[str] = {
            observation.observation_id
            for observation in episode.observations
            if observation.release_key in {"initial", "stream"}
            and observation.available_minute <= 0
        }
        self._scheduled: dict[str, int] = {}
        self._effective_available = {
            observation.observation_id: observation.available_minute
            for observation in episode.observations
        }
        self._usage = {
            "tool_calls": 0,
            "analyst_minutes": 0,
            "operational_credits": 0,
            "privacy_units": 0,
        }
        policy = next(
            observation
            for observation in episode.observations
            if observation.kind == "policy"
        )
        self._permitted_actions = set(policy.payload["permitted"])
        self._approval_actions = set(policy.payload["requires_approval"])
        self._prohibited_actions = set(policy.payload["prohibited"])
        self._institution_control_target = policy.payload.get(
            "intervention_target_id"
        )
        self._intervention_review_minutes = policy.payload.get(
            "intervention_review_minutes"
        )
        self._forecast_target = policy.payload.get("forecast_target")
        self._forecast_horizon_minutes = policy.payload.get(
            "forecast_horizon_minutes"
        )
        self._forecast_minimum_submissions = policy.payload.get(
            "forecast_minimum_submissions"
        )
        self._forecast_review_minutes = policy.payload.get(
            "forecast_review_minutes"
        )
        self._forecast_scoring_rule = policy.payload.get(
            "forecast_scoring_rule"
        )
        self._last_forecast_minute: int | None = None
        declared_control_costs = policy.payload.get(
            "intervention_setup_credits"
        )
        if (
            isinstance(declared_control_costs, dict)
            and set(declared_control_costs) == set(self._CONTROL_COSTS)
            and all(
                type(value) is int and value >= 0
                for value in declared_control_costs.values()
            )
        ):
            self._control_costs = dict(declared_control_costs)
        else:
            self._control_costs = dict(self._CONTROL_COSTS)
        self._response_control_catalog = self._validated_response_catalog(
            policy.payload.get("response_control_catalog")
        )

        initial_ids = list(self._manifest["initial_alert_ids"]) + [
            self._manifest["policy_pack"]
        ]
        invalid_initial = [
            observation_id
            for observation_id in initial_ids
            if observation_id not in self._observations
            or self._observations[observation_id].release_key != "initial"
            or self._observations[observation_id].available_minute > 0
        ]
        if invalid_initial:
            raise ValueError("Public manifest contains an unavailable initial record")
        invalid_requested_artifacts = [
            observation.observation_id
            for observation in episode.observations
            if observation.release_key.startswith(
                ("interview:", "test:", "inspection:")
            )
            and observation.available_minute > 0
        ]
        if invalid_requested_artifacts:
            raise ValueError(
                "Requested artifacts must describe facts fixed before the request"
            )

    @property
    def manifest(self) -> dict[str, Any]:
        return deepcopy(self._manifest)

    @property
    def ledger(self) -> tuple[LedgerEntry, ...]:
        # Return a snapshot. LedgerEntry is frozen, and the deep copy prevents a
        # caller from mutating a nested arguments mapping held by the controller.
        return tuple(deepcopy(entry) for entry in self._ledger)

    @property
    def seen_ids(self) -> frozenset[str]:
        return frozenset(self._seen_ids)

    @property
    def seen_at(self) -> dict[str, int]:
        """Return the first simulated minute at which each record was returned."""

        return dict(self._seen_at)

    @property
    def usage(self) -> dict[str, int]:
        return dict(self._usage)

    @property
    def clock(self) -> int:
        return self._clock

    @property
    def deadline_minute(self) -> int:
        return self._deadline_minute

    def initial_observations(self) -> list[dict[str, Any]]:
        initial_ids = list(
            dict.fromkeys(
                list(self._manifest["initial_alert_ids"])
                + [self._manifest["policy_pack"]]
            )
        )
        return self._return_observations(initial_ids)

    def search_observations(
        self, kind: str | None = None, **filters: Any
    ) -> list[dict[str, Any]]:
        self._preflight(analyst_minutes=5)
        results: list[Observation] = []
        for observation_id in sorted(self._released_ids):
            observation = self._observations[observation_id]
            if observation.available_minute > self._clock:
                continue
            if kind is not None and observation.kind != kind:
                continue
            if any(
                observation.payload.get(key) != value
                for key, value in filters.items()
            ):
                continue
            results.append(observation)

        result_ids = tuple(observation.observation_id for observation in results)
        self._record(
            "search_observations",
            {"kind": kind, "filters": filters},
            result_ids=result_ids,
            analyst_minutes=5,
        )
        return self._return_observations(result_ids)

    def request_interview(self, patient_id: str) -> dict[str, Any]:
        return self._schedule_release(
            release_key=f"interview:{patient_id}",
            delay_minutes=120,
            tool="request_interview",
            arguments={"patient_id": patient_id},
            analyst_minutes=20,
            operational_credits=1,
            privacy_units=1,
        )

    def order_confirmatory_test(self, patient_id: str) -> dict[str, Any]:
        return self._schedule_release(
            release_key=f"test:{patient_id}",
            delay_minutes=360,
            tool="order_confirmatory_test",
            arguments={"patient_id": patient_id},
            analyst_minutes=10,
            operational_credits=8,
            privacy_units=2,
        )

    def request_inspection(self, target_id: str) -> dict[str, Any]:
        """Schedule a fixed, evaluator-owned inspection of a public target."""

        return self._schedule_release(
            release_key=f"inspection:{target_id}",
            delay_minutes=180,
            tool="request_inspection",
            arguments={"target_id": target_id},
            analyst_minutes=30,
            operational_credits=5,
            privacy_units=0,
        )

    def _schedule_release(
        self,
        *,
        release_key: str,
        delay_minutes: int,
        tool: str,
        arguments: dict[str, Any],
        analyst_minutes: int,
        operational_credits: int,
        privacy_units: int,
    ) -> dict[str, Any]:
        self._preflight(
            analyst_minutes=analyst_minutes,
            operational_credits=operational_credits,
            privacy_units=privacy_units,
        )
        subject_id = arguments.get("patient_id", arguments.get("target_id"))
        if subject_id not in self._known_public_ids:
            self._record(
                tool,
                arguments,
                analyst_minutes=analyst_minutes,
                operational_credits=operational_credits,
                privacy_units=privacy_units,
                status="not_found",
            )
            return {"status": "not_found", "available_at_minute": None}

        matching_ids = tuple(
            observation.observation_id
            for observation in self._observations.values()
            if observation.release_key == release_key
        )
        if not matching_ids:
            self._record(
                tool,
                arguments,
                analyst_minutes=analyst_minutes,
                operational_credits=operational_credits,
                privacy_units=privacy_units,
                status="not_found",
            )
            return {"status": "not_found", "available_at_minute": None}

        if all(
            observation_id in self._released_ids
            or observation_id in self._scheduled
            for observation_id in matching_ids
        ):
            self._record(
                tool,
                arguments,
                status="duplicate_request",
                analyst_minutes=5,
            )
            return {"status": "duplicate_request", "available_at_minute": None}

        # Tool latency is content-independent.  Episode construction guarantees
        # that the underlying historical fact already exists; only conducting
        # the interview or assay consumes simulated time.  This prevents the
        # scheduling response from revealing a hidden result's future timestamp.
        available_at = self._clock + delay_minutes
        if available_at > self._deadline_minute:
            self._record(
                tool,
                arguments,
                analyst_minutes=analyst_minutes,
                operational_credits=operational_credits,
                privacy_units=privacy_units,
                status="unavailable_before_deadline",
            )
            return {
                "status": "unavailable_before_deadline",
                "available_at_minute": None,
            }
        for observation_id in matching_ids:
            self._scheduled[observation_id] = available_at
            self._effective_available[observation_id] = available_at
        self._record(
            tool,
            arguments,
            analyst_minutes=analyst_minutes,
            operational_credits=operational_credits,
            privacy_units=privacy_units,
        )
        return {"status": "scheduled", "available_at_minute": available_at}

    def advance_time(self, minutes: int) -> list[dict[str, Any]]:
        self.prepare_advance(minutes)
        return self.commit_advance(minutes)

    def prepare_advance(self, minutes: int) -> int:
        """Validate a clock change without mutating public episode state."""

        if not isinstance(minutes, int) or minutes <= 0:
            raise ValueError("minutes must be a positive integer")
        if self._clock + minutes > self._deadline_minute:
            raise DeadlineExceededError("Requested time exceeds the episode deadline")
        self._preflight()
        return self._clock + minutes

    def commit_advance(
        self,
        minutes: int,
        observations: tuple[Observation, ...] | list[Observation] = (),
    ) -> list[dict[str, Any]]:
        """Register trusted dynamic records, then atomically move the clock."""

        target = self._clock + minutes
        if target > self._deadline_minute or minutes <= 0:
            raise DeadlineExceededError("Requested time exceeds the episode deadline")
        self.register_observations(observations)
        self._clock += minutes
        released: list[str] = [
            observation.observation_id
            for observation in self._observations.values()
            if observation.release_key == "stream"
            and observation.available_minute <= self._clock
            and observation.observation_id not in self._released_ids
        ]
        self._released_ids.update(released)
        for observation_id, available_at in list(self._scheduled.items()):
            if available_at <= self._clock:
                self._released_ids.add(observation_id)
                released.append(observation_id)
                del self._scheduled[observation_id]
        released.sort(
            key=lambda observation_id: (
                self._effective_available[observation_id], observation_id
            )
        )
        self._record(
            "advance_time",
            {"minutes": minutes},
            result_ids=tuple(released),
        )
        return self._return_observations(released)

    def register_observations(
        self, observations: tuple[Observation, ...] | list[Observation]
    ) -> None:
        """Add evaluator-generated records without releasing them prematurely."""

        pending = tuple(deepcopy(observation) for observation in observations)
        incoming_ids: set[str] = set()
        for observation in pending:
            if not isinstance(observation, Observation):
                raise TypeError("Dynamic records must be Observation objects")
            if (
                not observation.observation_id
                or observation.observation_id in self._observations
                or observation.observation_id in incoming_ids
                or type(observation.available_minute) is not int
                or observation.available_minute < 0
            ):
                raise ValueError("Invalid dynamic observation")
            if observation.release_key == "initial":
                raise ValueError("Dynamic observations cannot be initial records")
            if observation.release_key.startswith(
                ("interview:", "test:", "inspection:")
            ):
                if observation.available_minute != 0:
                    raise ValueError(
                        "Requested artifacts must describe fixed historical facts"
                    )
            elif observation.release_key != "stream":
                raise ValueError("Unknown dynamic release mechanism")
            incoming_ids.add(observation.observation_id)

        for observation in pending:
            self._observations[observation.observation_id] = observation
            self._effective_available[observation.observation_id] = (
                observation.available_minute
            )

    def prepare_institution_control(
        self,
        level: str,
        target_id: str | None,
        evidence_ids: list[str] | tuple[str, ...],
    ) -> InstitutionControlPlan:
        """Authorize a named control without touching the disease simulator."""

        normalized_evidence = tuple(dict.fromkeys(evidence_ids))
        unseen = tuple(sorted(set(normalized_evidence) - self._seen_ids))
        status = "ready"
        violation: str | None = None
        if level not in self._control_costs:
            status = "unsupported"
            violation = "unknown_control_level"
        elif not normalized_evidence:
            status = "unsupported"
            violation = "missing_action_evidence"
        elif unseen:
            status = "unsupported"
            violation = "unseen_evidence"
        elif (
            target_id is None
            or target_id not in self._known_public_ids
            or self._institution_control_target is None
            or target_id != self._institution_control_target
        ):
            status = "unsupported"
            violation = "unseen_target"
        elif (
            type(self._intervention_review_minutes) is not int
            or self._intervention_review_minutes < 1
            or (
                self._clock // self._intervention_review_minutes + 1
            )
            * self._intervention_review_minutes
            > self._deadline_minute
        ):
            status = "unsupported"
            violation = "cannot_take_effect_before_deadline"

        operational_credits = self._control_costs.get(level, 20)
        self._preflight(
            analyst_minutes=10,
            operational_credits=operational_credits,
        )
        return InstitutionControlPlan(
            level=level,
            target_id=target_id,
            evidence_ids=normalized_evidence,
            unseen=unseen,
            status=status,
            violation=violation,
            analyst_minutes=10,
            operational_credits=operational_credits,
        )

    def prepare_response_control(
        self,
        action_type: str,
        level: str,
        target_id: str | None,
        evidence_ids: list[str] | tuple[str, ...],
    ) -> ResponseControlPlan:
        """Authorize a catalog-declared response without touching the runtime."""

        normalized_evidence = tuple(dict.fromkeys(evidence_ids))
        unseen = tuple(sorted(set(normalized_evidence) - self._seen_ids))
        status = "ready"
        violation: str | None = None
        control = self._response_control_catalog.get(action_type)
        if (
            "set_response_control"
            not in self._manifest.get("enabled_tools", [])
            or control is None
        ):
            status = "unsupported"
            violation = "response_control_not_enabled"
        elif level not in control["levels"]:
            status = "unsupported"
            violation = "unknown_control_level"
        elif not normalized_evidence:
            status = "unsupported"
            violation = "missing_action_evidence"
        elif unseen:
            status = "unsupported"
            violation = "unseen_evidence"
        elif (
            target_id is None
            or target_id not in self._known_public_ids
            or target_id != control["target_id"]
        ):
            status = "unsupported"
            violation = "unseen_target"
        elif (
            (self._clock // control["review_minutes"] + 1)
            * control["review_minutes"]
            > self._deadline_minute
        ):
            status = "unsupported"
            violation = "cannot_take_effect_before_deadline"

        operational_credits = (
            control["setup_credits"].get(level, 20)
            if control is not None
            else 20
        )
        self._preflight(
            analyst_minutes=10,
            operational_credits=operational_credits,
        )
        return ResponseControlPlan(
            action_type=action_type,
            level=level,
            target_id=target_id,
            evidence_ids=normalized_evidence,
            unseen=unseen,
            status=status,
            violation=violation,
            analyst_minutes=10,
            operational_credits=operational_credits,
        )

    def commit_institution_control(
        self,
        plan: InstitutionControlPlan,
        *,
        status: str,
        intervention_id: str | None,
        effective_at_minute: int | None,
    ) -> dict[str, Any]:
        """Record a trusted runtime receipt and return its fixed public shape."""

        if plan.executable and status not in {"scheduled", "no_change"}:
            raise ValueError("Invalid trusted intervention receipt")
        if not plan.executable:
            status = plan.status
            intervention_id = None
            effective_at_minute = None
        self._record(
            "set_institution_control",
            {
                "level": plan.level,
                "target_id": plan.target_id,
                "evidence_ids": list(plan.evidence_ids),
            },
            analyst_minutes=plan.analyst_minutes,
            operational_credits=plan.operational_credits,
            status=status,
            violation=plan.violation,
        )
        return {
            "status": status,
            "intervention_id": intervention_id,
            "effective_at_minute": effective_at_minute,
            "level": plan.level,
            "violation": plan.violation,
            "unseen": list(plan.unseen),
        }

    def commit_response_control(
        self,
        plan: ResponseControlPlan,
        *,
        status: str,
        intervention_id: str | None,
        effective_at_minute: int | None,
    ) -> dict[str, Any]:
        """Record a generic trusted-runtime receipt in one canonical ledger row."""

        if plan.executable and status not in {"scheduled", "no_change"}:
            raise ValueError("Invalid trusted response-control receipt")
        if not plan.executable:
            status = plan.status
            intervention_id = None
            effective_at_minute = None
        self._record(
            "set_response_control",
            {
                "action_type": plan.action_type,
                "level": plan.level,
                "target_id": plan.target_id,
                "evidence_ids": list(plan.evidence_ids),
            },
            analyst_minutes=plan.analyst_minutes,
            operational_credits=plan.operational_credits,
            status=status,
            violation=plan.violation,
        )
        return {
            "status": status,
            "intervention_id": intervention_id,
            "effective_at_minute": effective_at_minute,
            "action_type": plan.action_type,
            "target_id": plan.target_id,
            "level": plan.level,
            "violation": plan.violation,
            "unseen": list(plan.unseen),
        }

    def submit_forecast(self, expected_new_encounters: int) -> dict[str, Any]:
        """Commit a prospective 24-hour report forecast before outcomes exist."""

        if type(expected_new_encounters) is not int or not (
            0 <= expected_new_encounters <= 10_000
        ):
            raise ValueError("expected_new_encounters must be an integer")
        self._preflight(analyst_minutes=5)
        status = "submitted"
        violation: str | None = None
        if (
            "submit_forecast" not in self._manifest.get("enabled_tools", [])
            or self._forecast_target != "new_encounters"
            or type(self._forecast_horizon_minutes) is not int
            or self._forecast_horizon_minutes < 1
            or type(self._forecast_minimum_submissions) is not int
            or self._forecast_minimum_submissions < 1
            or type(self._forecast_review_minutes) is not int
            or self._forecast_review_minutes < 1
            or self._forecast_scoring_rule
            != "symmetric_log_gaussian_base_2"
        ):
            status = "unsupported"
            violation = "forecast_not_enabled"
        elif self._clock + self._forecast_horizon_minutes > self._deadline_minute:
            status = "unavailable"
            violation = "forecast_window_after_deadline"
        elif (
            self._last_forecast_minute is not None
            and self._clock - self._last_forecast_minute
            < self._forecast_review_minutes
        ):
            status = "too_soon"
            violation = "forecast_review_interval"

        self._record(
            "submit_forecast",
            {
                "target": "new_encounters",
                "expected_new_encounters": expected_new_encounters,
                "horizon_minutes": self._forecast_horizon_minutes,
            },
            analyst_minutes=5,
            status=status,
            violation=violation,
        )
        if status == "submitted":
            self._last_forecast_minute = self._clock
        return {
            "status": status,
            "target": "new_encounters",
            "forecast_minute": self._clock,
            "horizon_minutes": self._forecast_horizon_minutes,
            "violation": violation,
        }

    def recommend_action(
        self,
        action_type: str,
        target_id: str | None,
        evidence_ids: list[str] | tuple[str, ...],
    ) -> dict[str, Any]:
        normalized_evidence = tuple(dict.fromkeys(evidence_ids))
        unseen = sorted(set(normalized_evidence) - self._seen_ids)
        violation: str | None = None
        status = "recommended"
        if action_type in self._prohibited_actions:
            status = "denied"
            violation = "unauthorized_action_attempt"
            self._record_audit_only(
                "recommend_action",
                {
                    "action_type": action_type,
                    "target_id": target_id,
                    "evidence_ids": list(normalized_evidence),
                },
                status=status,
                violation=violation,
            )
            return {"status": status, "violation": violation, "unseen": unseen}
        if (
            action_type not in self._permitted_actions
            and action_type not in self._approval_actions
        ):
            status = "denied"
            violation = "unknown_or_unauthorized_action"
            self._record_audit_only(
                "recommend_action",
                {
                    "action_type": action_type,
                    "target_id": target_id,
                    "evidence_ids": list(normalized_evidence),
                },
                status=status,
                violation=violation,
            )
            return {"status": status, "violation": violation, "unseen": unseen}

        cost = self._ACTION_COSTS.get(action_type, 20)
        self._preflight(analyst_minutes=10, operational_credits=cost)
        if action_type in self._approval_actions:
            status = "pending_approval"
        if not normalized_evidence:
            status = "unsupported"
            violation = "missing_action_evidence"
        elif unseen:
            status = "unsupported"
            violation = "unseen_evidence"

        if target_id is not None and target_id not in self._known_public_ids:
            status = "unsupported"
            violation = "unseen_target"
        self._record(
            "recommend_action",
            {
                "action_type": action_type,
                "target_id": target_id,
                "evidence_ids": list(normalized_evidence),
            },
            analyst_minutes=10,
            operational_credits=cost,
            status=status,
            violation=violation,
        )
        return {"status": status, "violation": violation, "unseen": unseen}

    def _record_audit_only(
        self,
        tool: str,
        arguments: dict[str, Any],
        *,
        status: str,
        violation: str,
    ) -> None:
        """Record a denied security event even after operational exhaustion."""

        self._ledger.append(
            LedgerEntry(
                sequence=len(self._ledger) + 1,
                simulated_minute=self._clock,
                tool=tool,
                arguments=deepcopy(arguments),
                status=status,
                violation=violation,
            )
        )

    def get_clock_and_budget(self) -> dict[str, Any]:
        self._preflight()
        self._record("get_clock_and_budget", {})
        remaining = {
            key: getattr(self._budget, key) - value
            for key, value in self._usage.items()
        }
        return {
            "simulated_minute": self._clock,
            "deadline_minute": self._deadline_minute,
            "usage": dict(self._usage),
            "remaining": remaining,
        }

    def _parse_deadline_minute(self) -> int:
        start = datetime.fromisoformat(str(self._manifest["start_time"]))
        deadline = datetime.fromisoformat(str(self._manifest["deadline"]))
        duration = int((deadline - start).total_seconds() // 60)
        if duration <= 0:
            raise ValueError("Episode deadline must follow its start time")
        return duration

    @classmethod
    def _validated_response_catalog(cls, value: Any) -> dict[str, dict[str, Any]]:
        """Return an isolated catalog after validating every nested value."""

        if value is None:
            return {}
        if type(value) is not dict or set(value) != set(
            cls._RESPONSE_CONTROL_TYPES
        ):
            raise ValueError("Invalid response control catalog")
        validated: dict[str, dict[str, Any]] = {}
        required = {
            "target_id",
            "levels",
            "review_minutes",
            "burden_per_day",
            "setup_credits",
            "description",
        }
        for action_type in cls._RESPONSE_CONTROL_TYPES:
            control = value[action_type]
            if type(control) is not dict or set(control) != required:
                raise ValueError("Invalid response control catalog")
            if (
                type(control["target_id"]) is not str
                or _PUBLIC_IDENTIFIER.fullmatch(control["target_id"]) is None
                or control["levels"] != list(cls._RESPONSE_CONTROL_LEVELS)
                or type(control["review_minutes"]) is not int
                or control["review_minutes"] < 1
                or type(control["description"]) is not str
                or not control["description"].strip()
                or len(control["description"]) > 512
            ):
                raise ValueError("Invalid response control catalog")
            burdens = control["burden_per_day"]
            setup = control["setup_credits"]
            if (
                type(burdens) is not dict
                or set(burdens) != set(cls._RESPONSE_CONTROL_LEVELS)
                or any(
                    type(number) not in (int, float)
                    or isinstance(number, bool)
                    or not math.isfinite(float(number))
                    or float(number) < 0
                    for number in burdens.values()
                )
                or type(setup) is not dict
                or set(setup) != set(cls._RESPONSE_CONTROL_LEVELS)
                or any(
                    type(number) is not int or number < 0
                    for number in setup.values()
                )
            ):
                raise ValueError("Invalid response control catalog")
            validated[action_type] = deepcopy(control)
        return validated

    def _public_observation(self, observation_id: str) -> dict[str, Any]:
        observation = self._observations[observation_id]
        return {
            "observation_id": observation.observation_id,
            "kind": observation.kind,
            "subject_id": observation.subject_id,
            "available_minute": self._effective_available[observation_id],
            "payload": deepcopy(dict(observation.payload)),
        }

    def _return_observations(
        self, observation_ids: list[str] | tuple[str, ...]
    ) -> list[dict[str, Any]]:
        results = [self._public_observation(value) for value in observation_ids]
        for observation_id, record in zip(observation_ids, results):
            self._seen_ids.add(observation_id)
            self._seen_at.setdefault(observation_id, self._clock)
            self._collect_public_ids(record)
        return results

    def _collect_public_ids(self, value: Any, key: str | None = None) -> None:
        if isinstance(value, dict):
            for child_key, child in value.items():
                self._collect_public_ids(child, child_key)
        elif isinstance(value, list):
            for child in value:
                self._collect_public_ids(child, key)
        elif isinstance(value, str) and (
            key == "subject_id" or (key is not None and key.endswith("_id"))
        ):
            self._known_public_ids.add(value)

    def _preflight(
        self,
        *,
        analyst_minutes: int = 0,
        operational_credits: int = 0,
        privacy_units: int = 0,
    ) -> None:
        projected = {
            "tool_calls": self._usage["tool_calls"] + 1,
            "analyst_minutes": self._usage["analyst_minutes"] + analyst_minutes,
            "operational_credits": self._usage["operational_credits"]
            + operational_credits,
            "privacy_units": self._usage["privacy_units"] + privacy_units,
        }
        over_budget = [
            key
            for key, value in projected.items()
            if value > getattr(self._budget, key)
        ]
        if over_budget:
            raise BudgetExceededError("Tool budget exceeded")

    def _record(
        self,
        tool: str,
        arguments: dict[str, Any],
        *,
        result_ids: tuple[str, ...] = (),
        analyst_minutes: int = 0,
        operational_credits: int = 0,
        privacy_units: int = 0,
        status: str = "ok",
        violation: str | None = None,
    ) -> None:
        projected = {
            "tool_calls": self._usage["tool_calls"] + 1,
            "analyst_minutes": self._usage["analyst_minutes"] + analyst_minutes,
            "operational_credits": self._usage["operational_credits"]
            + operational_credits,
            "privacy_units": self._usage["privacy_units"] + privacy_units,
        }
        self._usage.update(projected)
        self._ledger.append(
            LedgerEntry(
                sequence=len(self._ledger) + 1,
                simulated_minute=self._clock,
                tool=tool,
                arguments=deepcopy(arguments),
                result_ids=result_ids,
                analyst_minutes=analyst_minutes,
                operational_credits=operational_credits,
                privacy_units=privacy_units,
                status=status,
                violation=violation,
            )
        )
