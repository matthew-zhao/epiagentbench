"""Evaluator-owned counterfactual branching for the private LTC engine.

Unlike :mod:`branching_manifest`, this module does not accept outcome rows or
pre-action hashes from a rollout caller.  The trusted evaluator freezes the
exact engine inputs, replays every opening state itself, executes only a
precommitted policy, and authenticates the resulting receipt with HMAC.

Objects in this module other than :class:`LtcBranchingCommitment` are private
evaluator material.  They must never cross the evaluator/agent boundary.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
import hashlib
import hmac
import json
import math
import re
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from .engine import EngineControl
from .starsim_ltc_v3 import (
    BACKEND_NAME,
    STAFF,
    STAFF_EXCLUSION_LEVEL,
    SUPPORTED_CONTROL_KINDS,
    SUPPORTED_STARSIM_VERSION,
    LtcLatentFrame,
    LtcNorovirusStarsimEngine,
    LtcStarsimV3Config,
    ScheduledLtcExposure,
)


PLAN_VERSION = "epiagentbench.ltc-branch-plan.v1"
RECEIPT_VERSION = "epiagentbench.ltc-branch-receipt.v1"
FUTURE_PROTOCOL = "precommitted_seed_and_external_events_v1"
PLAN_DOMAIN = b"EpiAgentBench trusted LTC branch plan v1\x00"
RECEIPT_DOMAIN = b"EpiAgentBench trusted LTC branch receipt v1\x00"
SNAPSHOT_DOMAIN = b"EpiAgentBench LTC private snapshot v1\x00"
BRANCH_INPUT_DOMAIN = b"EpiAgentBench LTC branch input v1\x00"
CLAIM_LIMITS = (
    "Authentication proves only that the configured trusted evaluator issued the receipt.",
    "A verified rollout is not evidence that the disease model is calibrated or externally valid.",
)

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$")
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")


class LtcBranchingError(ValueError):
    """Raised when a private branch plan or authenticated receipt is invalid."""


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise LtcBranchingError(f"invalid {label}")
    return value


def _digest(value: object, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise LtcBranchingError(f"invalid {label}")
    return value


def _json_value(value: Any, path: str = "value") -> Any:
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise LtcBranchingError(f"{path} contains a non-finite number")
        return value
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, child in value.items():
            if not isinstance(key, str) or key in result:
                raise LtcBranchingError(f"{path} contains an invalid key")
            result[key] = _json_value(child, f"{path}.{key}")
        return result
    if isinstance(value, (tuple, list)):
        return [_json_value(child, f"{path}[]") for child in value]
    raise LtcBranchingError(f"{path} is not canonical JSON data")


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        _json_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _sha256(domain: bytes, value: Any) -> str:
    return "sha256:" + hashlib.sha256(domain + _canonical_json(value)).hexdigest()


def _hmac_sha256(key: bytes, domain: bytes, value: Any) -> str:
    return (
        "sha256:"
        + hmac.new(key, domain + _canonical_json(value), hashlib.sha256).hexdigest()
    )


@dataclass(frozen=True, slots=True)
class LtcRuntimeFingerprint:
    """Exact evaluator runtime/image identity frozen before any action."""

    simulator_name: str
    simulator_version: str
    evaluator_runtime_sha256: str
    evaluator_image_digest: str

    def __post_init__(self) -> None:
        if self.simulator_name != BACKEND_NAME:
            raise LtcBranchingError("runtime fingerprint names the wrong simulator")
        if self.simulator_version != SUPPORTED_STARSIM_VERSION:
            raise LtcBranchingError(
                "runtime fingerprint has the wrong simulator version"
            )
        _digest(self.evaluator_runtime_sha256, "runtime digest")
        _digest(self.evaluator_image_digest, "image digest")


@dataclass(frozen=True, slots=True)
class LtcPolicyDefinition:
    policy_id: str
    policy_version: str
    controls: tuple[EngineControl, ...]

    def __post_init__(self) -> None:
        _identifier(self.policy_id, "policy id")
        _identifier(self.policy_version, "policy version")
        if not isinstance(self.controls, tuple) or any(
            not isinstance(control, EngineControl) for control in self.controls
        ):
            raise LtcBranchingError("policy controls must be an immutable tuple")
        ids: set[str] = set()
        for control in self.controls:
            _identifier(control.control_id, "control id")
            if control.control_id in ids:
                raise LtcBranchingError("control ids must be unique within a policy")
            ids.add(control.control_id)
            if control.kind not in SUPPORTED_CONTROL_KINDS:
                raise LtcBranchingError("policy contains an unsupported LTC control")
            if type(control.effective_minute) is not int:
                raise LtcBranchingError("control effective minute must be an integer")
            if type(control.magnitude) not in (int, float) or isinstance(
                control.magnitude, bool
            ):
                raise LtcBranchingError("control magnitude must be numeric")
            magnitude = float(control.magnitude)
            if not math.isfinite(magnitude) or not 0.0 <= magnitude <= 1.0:
                raise LtcBranchingError(
                    "control magnitude must be finite and in [0, 1]"
                )


@dataclass(frozen=True, slots=True)
class LtcParameterDraw:
    """One private disease/scenario parameter draw.

    ``config`` supplies all configuration except its seed and scheduled future
    events, which are replaced by the selected :class:`LtcFutureDraw`.
    """

    parameter_draw_id: str
    config: LtcStarsimV3Config

    def __post_init__(self) -> None:
        _identifier(self.parameter_draw_id, "parameter draw id")
        if not isinstance(self.config, LtcStarsimV3Config):
            raise LtcBranchingError("parameter draw config has the wrong type")


@dataclass(frozen=True, slots=True)
class LtcFutureDraw:
    future_draw_id: str
    random_seed: int
    scheduled_exposures: tuple[ScheduledLtcExposure, ...]
    protocol_version: str = FUTURE_PROTOCOL

    def __post_init__(self) -> None:
        _identifier(self.future_draw_id, "future draw id")
        if type(self.random_seed) is not int or self.random_seed < 0:
            raise LtcBranchingError("future random seed must be non-negative")
        if not isinstance(self.scheduled_exposures, tuple) or any(
            not isinstance(exposure, ScheduledLtcExposure)
            for exposure in self.scheduled_exposures
        ):
            raise LtcBranchingError("future events must be an immutable exposure tuple")
        if self.protocol_version != FUTURE_PROTOCOL:
            raise LtcBranchingError("unsupported future-event protocol")


@dataclass(frozen=True, slots=True)
class LtcInterventionEffectDraw:
    intervention_effect_draw_id: str
    control_magnitudes: Mapping[str, float]

    def __post_init__(self) -> None:
        _identifier(self.intervention_effect_draw_id, "intervention-effect draw id")
        if not isinstance(self.control_magnitudes, Mapping):
            raise LtcBranchingError("control magnitudes must be a mapping")
        detached: dict[str, float] = {}
        for control_id, value in self.control_magnitudes.items():
            control_id = _identifier(control_id, "effect control id")
            if (
                control_id in detached
                or type(value) not in (int, float)
                or isinstance(value, bool)
            ):
                raise LtcBranchingError("invalid intervention-effect draw")
            magnitude = float(value)
            if not math.isfinite(magnitude) or not 0.0 <= magnitude <= 1.0:
                raise LtcBranchingError("effect magnitude must be finite and in [0, 1]")
            detached[control_id] = magnitude
        object.__setattr__(
            self, "control_magnitudes", MappingProxyType(dict(sorted(detached.items())))
        )


@dataclass(frozen=True, slots=True)
class _FrozenPerson:
    person_id: str
    role: str
    ward_id: str | None
    room_id: str | None


@dataclass(frozen=True, slots=True)
class _FrozenContact:
    contact_id: str
    person_a_id: str
    person_b_id: str
    start_minute: int
    duration_minutes: int
    setting: str
    location_id: str | None


@dataclass(frozen=True, slots=True)
class _FrozenTrace:
    people: tuple[_FrozenPerson, ...]
    contacts: tuple[_FrozenContact, ...]


def _freeze_trace(trace: Any) -> _FrozenTrace:
    """Detach the exact trace; the engine performs the authoritative validation."""

    try:
        people = tuple(
            _FrozenPerson(raw.person_id, raw.role, raw.ward_id, raw.room_id)
            for raw in trace.people
        )
        contacts = tuple(
            _FrozenContact(
                raw.contact_id,
                raw.person_a_id,
                raw.person_b_id,
                raw.start_minute,
                raw.duration_minutes,
                raw.setting,
                raw.location_id,
            )
            for raw in trace.contacts
        )
    except (AttributeError, TypeError) as exc:
        raise LtcBranchingError(
            "trace does not implement the strict LTC trace schema"
        ) from exc
    # Sorting makes the private commitment insensitive to container iteration order.
    return _FrozenTrace(
        people=tuple(sorted(people, key=lambda value: value.person_id)),
        contacts=tuple(sorted(contacts, key=lambda value: value.contact_id)),
    )


@dataclass(frozen=True, slots=True)
class LtcBranchingCommitment:
    """The only branch-plan representation safe to publish."""

    plan_version: str
    manifest_sha256: str
    frozen_at_utc: str
    cutoff_minute: int
    claim_limits: tuple[str, ...] = CLAIM_LIMITS


@dataclass(frozen=True, slots=True)
class FrozenLtcBranchPlan:
    """Private evaluator handle.  Never serialize or expose this object."""

    manifest_id: str
    frozen_at_utc: str
    cutoff_minute: int
    scenario_version: str
    profile_version: str
    generator_version: str
    runtime_fingerprint: LtcRuntimeFingerprint
    trace: _FrozenTrace
    policies: tuple[LtcPolicyDefinition, ...]
    parameter_draws: tuple[LtcParameterDraw, ...]
    intervention_effect_draws: tuple[LtcInterventionEffectDraw, ...]
    future_draws: tuple[LtcFutureDraw, ...]
    opening_snapshot_sha256: tuple[tuple[str, str, str], ...]
    manifest_sha256: str
    authentication_tag: str
    _authentication_key: bytes = field(repr=False, compare=False)
    plan_version: str = PLAN_VERSION

    def public_commitment(self) -> LtcBranchingCommitment:
        return LtcBranchingCommitment(
            plan_version=self.plan_version,
            manifest_sha256=self.manifest_sha256,
            frozen_at_utc=self.frozen_at_utc,
            cutoff_minute=self.cutoff_minute,
        )


def _config_for(
    parameter: LtcParameterDraw, future: LtcFutureDraw
) -> LtcStarsimV3Config:
    return replace(
        parameter.config,
        random_seed=future.random_seed,
        scheduled_exposures=future.scheduled_exposures,
    )


def _policy_payload(policy: LtcPolicyDefinition) -> dict[str, Any]:
    return {
        "policy_id": policy.policy_id,
        "policy_version": policy.policy_version,
        "controls": [asdict(control) for control in policy.controls],
    }


def _private_plan_payload(plan: FrozenLtcBranchPlan) -> dict[str, Any]:
    return {
        "plan_version": plan.plan_version,
        "manifest_id": plan.manifest_id,
        "frozen_at_utc": plan.frozen_at_utc,
        "cutoff_minute": plan.cutoff_minute,
        "scenario_version": plan.scenario_version,
        "profile_version": plan.profile_version,
        "generator_version": plan.generator_version,
        "runtime_fingerprint": asdict(plan.runtime_fingerprint),
        "trace": asdict(plan.trace),
        "policies": [_policy_payload(value) for value in plan.policies],
        "parameter_draws": [
            {
                "parameter_draw_id": value.parameter_draw_id,
                "config": asdict(value.config),
            }
            for value in plan.parameter_draws
        ],
        "intervention_effect_draws": [
            {
                "intervention_effect_draw_id": value.intervention_effect_draw_id,
                "control_magnitudes": dict(value.control_magnitudes),
            }
            for value in plan.intervention_effect_draws
        ],
        "future_draws": [
            {
                "future_draw_id": value.future_draw_id,
                "random_seed": value.random_seed,
                "scheduled_exposures": [
                    asdict(item) for item in value.scheduled_exposures
                ],
                "protocol_version": value.protocol_version,
            }
            for value in plan.future_draws
        ],
        "opening_snapshot_sha256": [
            list(value) for value in plan.opening_snapshot_sha256
        ],
    }


def _verify_plan(plan: FrozenLtcBranchPlan) -> None:
    if not isinstance(plan, FrozenLtcBranchPlan):
        raise LtcBranchingError("verified branching requires a frozen trusted plan")
    payload = _private_plan_payload(plan)
    expected_digest = _sha256(PLAN_DOMAIN, payload)
    expected_tag = _hmac_sha256(plan._authentication_key, PLAN_DOMAIN, payload)
    if not hmac.compare_digest(
        expected_digest, plan.manifest_sha256
    ) or not hmac.compare_digest(expected_tag, plan.authentication_tag):
        raise LtcBranchingError("private branch plan authentication failed")


def _snapshot_sha256(snapshot: LtcLatentFrame) -> str:
    if not isinstance(snapshot, LtcLatentFrame):
        raise LtcBranchingError("LTC engine returned an invalid private snapshot")
    return _sha256(SNAPSHOT_DOMAIN, asdict(snapshot))


def freeze_ltc_branch_plan(
    *,
    manifest_id: str,
    trace: Any,
    cutoff_minute: int,
    scenario_version: str,
    profile_version: str,
    generator_version: str,
    runtime_fingerprint: LtcRuntimeFingerprint,
    policies: Iterable[LtcPolicyDefinition],
    parameter_draws: Iterable[LtcParameterDraw],
    intervention_effect_draws: Iterable[LtcInterventionEffectDraw],
    future_draws: Iterable[LtcFutureDraw],
    authentication_key: bytes,
) -> FrozenLtcBranchPlan:
    """Freeze inputs and derive every opening commitment by executing Starsim."""

    _identifier(manifest_id, "manifest id")
    for value, label in (
        (scenario_version, "scenario version"),
        (profile_version, "profile version"),
        (generator_version, "generator version"),
    ):
        _identifier(value, label)
    if not isinstance(runtime_fingerprint, LtcRuntimeFingerprint):
        raise LtcBranchingError("runtime fingerprint has the wrong type")
    if type(cutoff_minute) is not int or cutoff_minute < 0:
        raise LtcBranchingError("cutoff minute must be a non-negative integer")
    if not isinstance(authentication_key, bytes) or len(authentication_key) < 32:
        raise LtcBranchingError("authentication key must contain at least 32 bytes")

    frozen_trace = _freeze_trace(trace)
    policy_bank = tuple(sorted(tuple(policies), key=lambda value: value.policy_id))
    parameter_bank = tuple(
        sorted(tuple(parameter_draws), key=lambda value: value.parameter_draw_id)
    )
    effect_bank = tuple(
        sorted(
            tuple(intervention_effect_draws),
            key=lambda value: value.intervention_effect_draw_id,
        )
    )
    future_bank = tuple(
        sorted(tuple(future_draws), key=lambda value: value.future_draw_id)
    )
    if len(policy_bank) < 2 or any(
        not isinstance(value, LtcPolicyDefinition) for value in policy_bank
    ):
        raise LtcBranchingError("at least two typed policy definitions are required")
    for bank, value_type, label in (
        (parameter_bank, LtcParameterDraw, "parameter"),
        (effect_bank, LtcInterventionEffectDraw, "intervention-effect"),
        (future_bank, LtcFutureDraw, "future"),
    ):
        if not bank or any(not isinstance(value, value_type) for value in bank):
            raise LtcBranchingError(f"at least one typed {label} draw is required")
    for values, label in (
        (tuple(value.policy_id for value in policy_bank), "policy"),
        (tuple(value.parameter_draw_id for value in parameter_bank), "parameter draw"),
        (
            tuple(value.intervention_effect_draw_id for value in effect_bank),
            "intervention-effect draw",
        ),
        (tuple(value.future_draw_id for value in future_bank), "future draw"),
    ):
        if len(values) != len(set(values)):
            raise LtcBranchingError(f"duplicate {label} id")

    control_ids = {
        control.control_id for policy in policy_bank for control in policy.controls
    }
    if any(set(draw.control_magnitudes) != control_ids for draw in effect_bank):
        raise LtcBranchingError(
            "every intervention-effect draw must cover exactly the frozen controls"
        )
    time_bases = {
        (draw.config.horizon_days, draw.config.timestep_minutes)
        for draw in parameter_bank
    }
    if len(time_bases) != 1:
        raise LtcBranchingError(
            "all parameter draws must use the same horizon and timestep"
        )
    if any(
        exposure.exposure_minute <= cutoff_minute
        for future in future_bank
        for exposure in future.scheduled_exposures
    ):
        raise LtcBranchingError(
            "future-draw exposures must occur strictly after the opening cutoff"
        )
    for parameter in parameter_bank:
        config = parameter.config
        if config.random_seed != 0 or config.scheduled_exposures:
            raise LtcBranchingError(
                "parameter configs must leave seed and scheduled events to the frozen future-draw bank"
            )
        if (
            cutoff_minute % config.timestep_minutes
            or cutoff_minute >= config.horizon_days * 1440
        ):
            raise LtcBranchingError("cutoff must be a pre-terminal simulator boundary")
        for policy in policy_bank:
            for control in policy.controls:
                if (
                    control.effective_minute < cutoff_minute
                    or control.effective_minute % config.timestep_minutes
                    or control.effective_minute >= config.horizon_days * 1440
                ):
                    raise LtcBranchingError(
                        "every policy control must be on or after the frozen cutoff and before the horizon"
                    )

    all_control_ids = [
        control.control_id for policy in policy_bank for control in policy.controls
    ]
    if len(all_control_ids) != len(set(all_control_ids)):
        raise LtcBranchingError("control ids must be unique across the policy bank")
    person_roles = {person.person_id: person.role for person in frozen_trace.people}
    for policy in policy_bank:
        for control in policy.controls:
            if float(control.magnitude) != 1.0:
                raise LtcBranchingError(
                    "frozen policy controls must use magnitude 1; effect draws supply executed magnitudes"
                )
            if control.kind == STAFF_EXCLUSION_LEVEL:
                if person_roles.get(control.target_id or "") != STAFF:
                    raise LtcBranchingError(
                        "staff-exclusion control must target a frozen staff member"
                    )
            elif control.target_id is not None:
                raise LtcBranchingError(
                    "only staff-exclusion controls may have a target"
                )

    openings: list[tuple[str, str, str]] = []
    for parameter in parameter_bank:
        for future in future_bank:
            config = _config_for(parameter, future)
            engine = LtcNorovirusStarsimEngine(frozen_trace, config)
            try:
                engine.advance_to(cutoff_minute)
                snapshot = engine.private_snapshot()
                if snapshot.applied_control_ids:
                    raise LtcBranchingError(
                        "opening replay contains a pre-action control"
                    )
                openings.append(
                    (
                        parameter.parameter_draw_id,
                        future.future_draw_id,
                        _snapshot_sha256(snapshot),
                    )
                )
            finally:
                engine.close()

    frozen_at = (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )
    provisional = FrozenLtcBranchPlan(
        manifest_id=manifest_id,
        frozen_at_utc=frozen_at,
        cutoff_minute=cutoff_minute,
        scenario_version=scenario_version,
        profile_version=profile_version,
        generator_version=generator_version,
        runtime_fingerprint=runtime_fingerprint,
        trace=frozen_trace,
        policies=policy_bank,
        parameter_draws=parameter_bank,
        intervention_effect_draws=effect_bank,
        future_draws=future_bank,
        opening_snapshot_sha256=tuple(openings),
        manifest_sha256="sha256:" + "0" * 64,
        authentication_tag="sha256:" + "0" * 64,
        _authentication_key=authentication_key,
    )
    payload = _private_plan_payload(provisional)
    return replace(
        provisional,
        manifest_sha256=_sha256(PLAN_DOMAIN, payload),
        authentication_tag=_hmac_sha256(authentication_key, PLAN_DOMAIN, payload),
    )


@dataclass(frozen=True, slots=True)
class LtcBranchOutcomes:
    resident_symptomatic_cases: int
    staff_symptomatic_cases: int
    total_infections: int
    transmission_events: int
    terminal_minute: int


@dataclass(frozen=True, slots=True)
class AuthenticatedLtcBranchReceipt:
    receipt_version: str
    manifest_sha256: str
    policy_id: str
    parameter_draw_id: str
    intervention_effect_draw_id: str
    future_draw_id: str
    branch_input_sha256: str
    opening_snapshot_sha256: str
    terminal_snapshot_sha256: str
    outcomes: LtcBranchOutcomes
    receipt_sha256: str
    authentication_tag: str


def _receipt_payload(receipt: AuthenticatedLtcBranchReceipt) -> dict[str, Any]:
    return {
        "receipt_version": receipt.receipt_version,
        "manifest_sha256": receipt.manifest_sha256,
        "policy_id": receipt.policy_id,
        "parameter_draw_id": receipt.parameter_draw_id,
        "intervention_effect_draw_id": receipt.intervention_effect_draw_id,
        "future_draw_id": receipt.future_draw_id,
        "branch_input_sha256": receipt.branch_input_sha256,
        "opening_snapshot_sha256": receipt.opening_snapshot_sha256,
        "terminal_snapshot_sha256": receipt.terminal_snapshot_sha256,
        "outcomes": asdict(receipt.outcomes),
    }


def _find_unique(values: Iterable[Any], field: str, expected: str) -> Any:
    matches = [value for value in values if getattr(value, field) == expected]
    if len(matches) != 1:
        raise LtcBranchingError(f"unknown or ambiguous frozen {field}")
    return matches[0]


def _opening_digest(
    plan: FrozenLtcBranchPlan, parameter_id: str, future_id: str
) -> str:
    matches = [
        digest
        for stored_parameter, stored_future, digest in plan.opening_snapshot_sha256
        if stored_parameter == parameter_id and stored_future == future_id
    ]
    if len(matches) != 1:
        raise LtcBranchingError("opening snapshot bank is incomplete or ambiguous")
    return matches[0]


def _derive_outcomes(snapshot: LtcLatentFrame) -> LtcBranchOutcomes:
    residents = sum(
        person.role == "resident"
        and person.symptom_onset_minute is not None
        and person.symptom_onset_minute <= snapshot.minute
        for person in snapshot.people
    )
    staff = sum(
        person.role == "staff"
        and person.symptom_onset_minute is not None
        and person.symptom_onset_minute <= snapshot.minute
        for person in snapshot.people
    )
    return LtcBranchOutcomes(
        resident_symptomatic_cases=residents,
        staff_symptomatic_cases=staff,
        total_infections=sum(
            person.infection_minute is not None for person in snapshot.people
        ),
        transmission_events=len(snapshot.transmission_events),
        terminal_minute=snapshot.minute,
    )


def execute_ltc_branch(
    plan: FrozenLtcBranchPlan,
    *,
    policy_id: str,
    parameter_draw_id: str,
    intervention_effect_draw_id: str,
    future_draw_id: str,
) -> AuthenticatedLtcBranchReceipt:
    """Replay one opening and execute only the policy frozen in ``plan``."""

    _verify_plan(plan)
    policy = _find_unique(plan.policies, "policy_id", policy_id)
    parameter = _find_unique(
        plan.parameter_draws, "parameter_draw_id", parameter_draw_id
    )
    effect = _find_unique(
        plan.intervention_effect_draws,
        "intervention_effect_draw_id",
        intervention_effect_draw_id,
    )
    future = _find_unique(plan.future_draws, "future_draw_id", future_draw_id)
    config = _config_for(parameter, future)
    expected_opening = _opening_digest(plan, parameter_draw_id, future_draw_id)
    materialized_controls = tuple(
        replace(control, magnitude=effect.control_magnitudes[control.control_id])
        for control in policy.controls
    )
    branch_input = {
        "manifest_sha256": plan.manifest_sha256,
        "policy": _policy_payload(replace(policy, controls=materialized_controls)),
        "parameter_draw_id": parameter_draw_id,
        "intervention_effect_draw_id": intervention_effect_draw_id,
        "future_draw_id": future_draw_id,
        "config": asdict(config),
        "expected_opening_snapshot_sha256": expected_opening,
    }
    branch_input_sha256 = _sha256(BRANCH_INPUT_DOMAIN, branch_input)

    engine = LtcNorovirusStarsimEngine(plan.trace, config)
    try:
        engine.advance_to(plan.cutoff_minute)
        opening = engine.private_snapshot()
        actual_opening = _snapshot_sha256(opening)
        if not hmac.compare_digest(actual_opening, expected_opening):
            raise LtcBranchingError(
                "LTC opening replay does not match the frozen manifest"
            )
        if opening.applied_control_ids:
            raise LtcBranchingError("branch diverged before the action boundary")
        for control in materialized_controls:
            engine.apply_control(control)
        engine.advance_to(config.horizon_days * 1440)
        terminal = engine.private_snapshot()
        outcomes = _derive_outcomes(terminal)
        terminal_digest = _snapshot_sha256(terminal)
    finally:
        engine.close()

    provisional = AuthenticatedLtcBranchReceipt(
        receipt_version=RECEIPT_VERSION,
        manifest_sha256=plan.manifest_sha256,
        policy_id=policy_id,
        parameter_draw_id=parameter_draw_id,
        intervention_effect_draw_id=intervention_effect_draw_id,
        future_draw_id=future_draw_id,
        branch_input_sha256=branch_input_sha256,
        opening_snapshot_sha256=actual_opening,
        terminal_snapshot_sha256=terminal_digest,
        outcomes=outcomes,
        receipt_sha256="sha256:" + "0" * 64,
        authentication_tag="sha256:" + "0" * 64,
    )
    payload = _receipt_payload(provisional)
    return replace(
        provisional,
        receipt_sha256=_sha256(RECEIPT_DOMAIN, payload),
        authentication_tag=_hmac_sha256(
            plan._authentication_key, RECEIPT_DOMAIN, payload
        ),
    )


def verify_ltc_branch_receipt(
    plan: FrozenLtcBranchPlan,
    receipt: AuthenticatedLtcBranchReceipt,
    *,
    replay: bool = True,
) -> AuthenticatedLtcBranchReceipt:
    """Authenticate a receipt and, by default, independently replay its branch."""

    _verify_plan(plan)
    if not isinstance(receipt, AuthenticatedLtcBranchReceipt):
        raise LtcBranchingError(
            "verified evaluation accepts only evaluator-issued LTC branch receipts"
        )
    if receipt.receipt_version != RECEIPT_VERSION or not hmac.compare_digest(
        receipt.manifest_sha256, plan.manifest_sha256
    ):
        raise LtcBranchingError("receipt belongs to a different branch plan")
    payload = _receipt_payload(receipt)
    if not hmac.compare_digest(
        _sha256(RECEIPT_DOMAIN, payload), receipt.receipt_sha256
    ) or not hmac.compare_digest(
        _hmac_sha256(plan._authentication_key, RECEIPT_DOMAIN, payload),
        receipt.authentication_tag,
    ):
        raise LtcBranchingError("branch receipt authentication failed")
    # Membership checks happen even when replay is disabled.
    _find_unique(plan.policies, "policy_id", receipt.policy_id)
    _find_unique(plan.parameter_draws, "parameter_draw_id", receipt.parameter_draw_id)
    _find_unique(
        plan.intervention_effect_draws,
        "intervention_effect_draw_id",
        receipt.intervention_effect_draw_id,
    )
    _find_unique(plan.future_draws, "future_draw_id", receipt.future_draw_id)
    expected_opening = _opening_digest(
        plan, receipt.parameter_draw_id, receipt.future_draw_id
    )
    if not hmac.compare_digest(expected_opening, receipt.opening_snapshot_sha256):
        raise LtcBranchingError("receipt opening does not match the frozen draw")
    if replay:
        replayed = execute_ltc_branch(
            plan,
            policy_id=receipt.policy_id,
            parameter_draw_id=receipt.parameter_draw_id,
            intervention_effect_draw_id=receipt.intervention_effect_draw_id,
            future_draw_id=receipt.future_draw_id,
        )
        if replayed != receipt:
            raise LtcBranchingError("branch receipt does not match independent replay")
    return receipt


@dataclass(frozen=True, slots=True)
class VerifiedLtcPolicySummary:
    policy_id: str
    draw_count: int
    mean_resident_symptomatic_cases: float
    mean_staff_symptomatic_cases: float
    mean_total_infections: float


@dataclass(frozen=True, slots=True)
class VerifiedLtcPolicyPanel:
    manifest_sha256: str
    branch_count: int
    draws_per_policy: int
    policy_summaries: tuple[VerifiedLtcPolicySummary, ...]
    receipt_panel_sha256: str


def evaluate_verified_ltc_policy_panel(
    plan: FrozenLtcBranchPlan,
    receipts: Iterable[AuthenticatedLtcBranchReceipt],
    *,
    replay_receipts: bool = True,
) -> VerifiedLtcPolicyPanel:
    """Evaluate only a complete, balanced panel of authenticated branches."""

    _verify_plan(plan)
    materialized = tuple(receipts)
    if not materialized:
        raise LtcBranchingError("verified policy panel cannot be empty")
    verified = tuple(
        verify_ltc_branch_receipt(plan, receipt, replay=replay_receipts)
        for receipt in materialized
    )
    expected_keys = {
        (
            policy.policy_id,
            parameter.parameter_draw_id,
            effect.intervention_effect_draw_id,
            future.future_draw_id,
        )
        for policy in plan.policies
        for parameter in plan.parameter_draws
        for effect in plan.intervention_effect_draws
        for future in plan.future_draws
    }
    actual_keys = {
        (
            receipt.policy_id,
            receipt.parameter_draw_id,
            receipt.intervention_effect_draw_id,
            receipt.future_draw_id,
        )
        for receipt in verified
    }
    if len(actual_keys) != len(verified) or actual_keys != expected_keys:
        raise LtcBranchingError(
            "verified policy panel must contain exactly one receipt for every frozen branch"
        )
    summaries: list[VerifiedLtcPolicySummary] = []
    for policy in plan.policies:
        rows = [
            receipt for receipt in verified if receipt.policy_id == policy.policy_id
        ]
        count = len(rows)
        summaries.append(
            VerifiedLtcPolicySummary(
                policy_id=policy.policy_id,
                draw_count=count,
                mean_resident_symptomatic_cases=sum(
                    row.outcomes.resident_symptomatic_cases for row in rows
                )
                / count,
                mean_staff_symptomatic_cases=sum(
                    row.outcomes.staff_symptomatic_cases for row in rows
                )
                / count,
                mean_total_infections=sum(row.outcomes.total_infections for row in rows)
                / count,
            )
        )
    panel_digest = _sha256(
        RECEIPT_DOMAIN,
        sorted(receipt.receipt_sha256 for receipt in verified),
    )
    return VerifiedLtcPolicyPanel(
        manifest_sha256=plan.manifest_sha256,
        branch_count=len(verified),
        draws_per_policy=len(verified) // len(plan.policies),
        policy_summaries=tuple(summaries),
        receipt_panel_sha256=panel_digest,
    )
