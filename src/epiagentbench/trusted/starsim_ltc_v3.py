"""Trusted-only Starsim foundation for a role-aware LTC norovirus model.

This module is deliberately separate from :mod:`starsim_engine`, which remains
the v2 compatibility backend.  The model here is an engineering foundation,
not a calibrated norovirus model.  Every numeric default is explicitly marked
as a prior/design placeholder and promotion requires separate evidence.

Raw simulator identifiers, facility roles, wards, contacts, schedules, and
latent states are private evaluator data.  ``public_engine_descriptor()`` is
the only public serialization supplied by this module and is intentionally
constant across episodes.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from .engine import (
    EngineClosedError,
    EngineControl,
    EngineError,
    UnsupportedControlError,
)


DAY_MINUTES = 24 * 60
SUPPORTED_STARSIM_VERSION = "3.5.1"
BACKEND_NAME = "starsim_ltc_norovirus_v3"
PUBLIC_MODEL_STATUS = "development_only_not_calibrated"

RESIDENT = "resident"
STAFF = "staff"
VISITOR = "visitor"
SUPPORTED_ROLES = frozenset({RESIDENT, STAFF, VISITOR})

SEED = "seed"
PERSON_TO_PERSON = "person_to_person"
COMMON_SOURCE = "common_source"
IMPORTATION = "importation"
ENVIRONMENTAL = "environmental"
SCHEDULED_MECHANISMS = frozenset(
    {COMMON_SOURCE, IMPORTATION, ENVIRONMENTAL}
)

CONTACT_REDUCTION_LEVEL = "ltc_contact_reduction_level"
STAFF_EXCLUSION_LEVEL = "ltc_staff_exclusion_level"
SOURCE_CONTROL_LEVEL = "ltc_source_control_level"
ENTRY_CONTROL_LEVEL = "ltc_entry_control_level"
ENVIRONMENTAL_CONTROL_LEVEL = "ltc_environmental_control_level"
SUPPORTED_CONTROL_KINDS = frozenset(
    {
        CONTACT_REDUCTION_LEVEL,
        STAFF_EXCLUSION_LEVEL,
        SOURCE_CONTROL_LEVEL,
        ENTRY_CONTROL_LEVEL,
        ENVIRONMENTAL_CONTROL_LEVEL,
    }
)

SUSCEPTIBLE = "susceptible"
EXPOSED_INCUBATING = "exposed_incubating"
INFECTIOUS_SYMPTOMATIC = "infectious_symptomatic"
INFECTIOUS_ASYMPTOMATIC = "infectious_asymptomatic"
RECOVERED = "recovered"

PRIOR_PLACEHOLDER = "prior_placeholder"
DESIGN_PLACEHOLDER = "design_placeholder"
EVIDENCE_ANCHORED_PRIOR = "evidence_anchored_prior"
CALIBRATED_CANDIDATE = "calibrated_candidate"
VALIDATED = "validated"
EVIDENCE_STATUSES = frozenset(
    {
        PRIOR_PLACEHOLDER,
        DESIGN_PLACEHOLDER,
        EVIDENCE_ANCHORED_PRIOR,
        CALIBRATED_CANDIDATE,
        VALIDATED,
    }
)
_EVIDENCE_REQUIRING_REFERENCE = frozenset(
    {EVIDENCE_ANCHORED_PRIOR, CALIBRATED_CANDIDATE, VALIDATED}
)

STATIC_CONTACT_AGGREGATION = "unique_undirected_trace_pair_v1"


def _validate_evidence(
    status: str,
    reference: str | None,
    *,
    field_name: str,
) -> None:
    if status not in EVIDENCE_STATUSES:
        raise ValueError(f"{field_name} has an unsupported evidence status")
    if status in _EVIDENCE_REQUIRING_REFERENCE and (
        not isinstance(reference, str) or not reference.strip()
    ):
        raise ValueError(
            f"{field_name} requires a non-empty evidence reference"
        )
    if reference is not None and (
        not isinstance(reference, str) or not reference.strip()
    ):
        raise ValueError(f"{field_name} evidence reference must be non-empty")


def _finite_probability(value: Any, field_name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0.0 <= float(value) <= 1.0
    ):
        raise ValueError(f"{field_name} must be finite and in [0, 1]")
    return float(value)


def _finite_nonnegative(value: Any, field_name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0.0
    ):
        raise ValueError(f"{field_name} must be finite and non-negative")
    return float(value)


@dataclass(frozen=True, slots=True)
class RoleInfectiousnessProfile:
    """One role-specific, evidence-labelled natural-history prior.

    Values supplied by the defaults are development priors only.  They are not
    estimates from NORS, Adams line lists, or an intervention trial.
    """

    role: str
    symptomatic_probability: float = 0.5
    symptomatic_relative_infectiousness: float = 1.0
    asymptomatic_relative_infectiousness: float = 0.5
    evidence_status: str = PRIOR_PLACEHOLDER
    evidence_reference: str | None = None

    def __post_init__(self) -> None:
        if self.role not in SUPPORTED_ROLES:
            raise ValueError("role profile has an unsupported LTC role")
        _finite_probability(
            self.symptomatic_probability, "symptomatic_probability"
        )
        symptomatic = _finite_nonnegative(
            self.symptomatic_relative_infectiousness,
            "symptomatic_relative_infectiousness",
        )
        asymptomatic = _finite_nonnegative(
            self.asymptomatic_relative_infectiousness,
            "asymptomatic_relative_infectiousness",
        )
        if not symptomatic > asymptomatic:
            raise ValueError(
                "symptomatic relative infectiousness must exceed asymptomatic "
                "relative infectiousness"
            )
        _validate_evidence(
            self.evidence_status,
            self.evidence_reference,
            field_name=f"role profile {self.role}",
        )


def _placeholder_role_profiles() -> tuple[RoleInfectiousnessProfile, ...]:
    return tuple(
        RoleInfectiousnessProfile(role=role)
        for role in (RESIDENT, STAFF, VISITOR)
    )


@dataclass(frozen=True, slots=True)
class LtcNorovirusNaturalHistory:
    """Uncalibrated natural-history inputs for the v3 development model."""

    contact_beta_per_day: float = 0.05
    incubation_days: float = 1.0
    infectious_days: float = 2.0
    role_profiles: tuple[RoleInfectiousnessProfile, ...] = field(
        default_factory=_placeholder_role_profiles
    )
    evidence_status: str = PRIOR_PLACEHOLDER
    evidence_reference: str | None = None

    def __post_init__(self) -> None:
        beta = _finite_probability(
            self.contact_beta_per_day, "contact_beta_per_day"
        )
        if beta <= 0.0:
            raise ValueError("contact_beta_per_day must be positive")
        for name, value in (
            ("incubation_days", self.incubation_days),
            ("infectious_days", self.infectious_days),
        ):
            checked = _finite_nonnegative(value, name)
            if checked <= 0.0:
                raise ValueError(f"{name} must be positive")
        if not isinstance(self.role_profiles, tuple):
            raise ValueError("role_profiles must be an immutable tuple")
        if any(
            not isinstance(profile, RoleInfectiousnessProfile)
            for profile in self.role_profiles
        ):
            raise ValueError(
                "role_profiles must contain RoleInfectiousnessProfile values"
            )
        roles = tuple(profile.role for profile in self.role_profiles)
        if len(roles) != len(set(roles)):
            raise ValueError("role_profiles must contain each role at most once")
        _validate_evidence(
            self.evidence_status,
            self.evidence_reference,
            field_name="natural history",
        )


@dataclass(frozen=True, slots=True)
class LtcInterventionAssumptions:
    """Evidence label for deterministic control hooks.

    A control magnitude is an experimental relative level, not a claimed real-
    world effect size.  Policy evaluation must provide an uncertainty model
    before these hooks can support scientific conclusions.
    """

    evidence_status: str = DESIGN_PLACEHOLDER
    evidence_reference: str | None = None

    def __post_init__(self) -> None:
        _validate_evidence(
            self.evidence_status,
            self.evidence_reference,
            field_name="intervention assumptions",
        )


@dataclass(frozen=True, slots=True)
class ScheduledLtcExposure:
    """One private, precommitted external-exposure opportunity.

    ``threshold`` is fixed before actions.  A route-level control compares the
    same threshold in factual and counterfactual worlds, so suppressing one
    opportunity cannot shift later random draws.
    """

    mechanism: str
    target_person_id: str
    exposure_minute: int
    threshold: float
    evidence_status: str = DESIGN_PLACEHOLDER
    evidence_reference: str | None = None

    def __post_init__(self) -> None:
        if self.mechanism not in SCHEDULED_MECHANISMS:
            raise ValueError("scheduled exposure has an unsupported mechanism")
        if (
            not isinstance(self.target_person_id, str)
            or not self.target_person_id.strip()
        ):
            raise ValueError("scheduled exposure target must be non-empty")
        if (
            type(self.exposure_minute) is not int
            or self.exposure_minute < 0
        ):
            raise ValueError("scheduled exposure minute must be non-negative")
        threshold = _finite_probability(self.threshold, "exposure threshold")
        if threshold == 1.0:
            raise ValueError("exposure threshold must be in [0, 1)")
        _validate_evidence(
            self.evidence_status,
            self.evidence_reference,
            field_name="scheduled exposure",
        )


@dataclass(frozen=True, slots=True)
class LtcStarsimV3Config:
    """Private configuration for one LTC norovirus Starsim world.

    ``evidence_status`` is intentionally required.  Callers cannot construct a
    scenario without saying whether it is a placeholder, prior, calibration
    candidate, or validated profile.
    """

    random_seed: int
    seed_person_ids: tuple[str, ...]
    evidence_status: str
    horizon_days: int = 14
    timestep_minutes: int = DAY_MINUTES
    natural_history: LtcNorovirusNaturalHistory = field(
        default_factory=LtcNorovirusNaturalHistory
    )
    scheduled_exposures: tuple[ScheduledLtcExposure, ...] = ()
    intervention_assumptions: LtcInterventionAssumptions = field(
        default_factory=LtcInterventionAssumptions
    )
    evidence_reference: str | None = None

    def __post_init__(self) -> None:
        if type(self.random_seed) is not int or self.random_seed < 0:
            raise ValueError("random_seed must be a non-negative integer")
        if not isinstance(self.seed_person_ids, tuple) or not (
            1 <= len(self.seed_person_ids) <= 3
        ):
            raise ValueError("seed_person_ids must contain exactly one to three IDs")
        if any(
            not isinstance(person_id, str) or not person_id.strip()
            for person_id in self.seed_person_ids
        ):
            raise ValueError("seed person IDs must be non-empty strings")
        if len(self.seed_person_ids) != len(set(self.seed_person_ids)):
            raise ValueError("seed person IDs must be unique")
        if type(self.horizon_days) is not int or self.horizon_days < 1:
            raise ValueError("horizon_days must be a positive integer")
        if (
            type(self.timestep_minutes) is not int
            or self.timestep_minutes < 1
            or DAY_MINUTES % self.timestep_minutes
        ):
            raise ValueError(
                "timestep_minutes must be a positive divisor of one day"
            )
        if not isinstance(self.natural_history, LtcNorovirusNaturalHistory):
            raise ValueError("natural_history has the wrong type")
        dt_days = self.timestep_minutes / DAY_MINUTES
        for duration_name, duration_days in (
            ("incubation_days", self.natural_history.incubation_days),
            ("infectious_days", self.natural_history.infectious_days),
        ):
            steps = duration_days / dt_days
            if not math.isclose(steps, round(steps), rel_tol=0.0, abs_tol=1e-9):
                raise ValueError(
                    f"{duration_name} must be an exact simulator timestep multiple"
                )
        if not isinstance(self.intervention_assumptions, LtcInterventionAssumptions):
            raise ValueError("intervention_assumptions has the wrong type")
        if not isinstance(self.scheduled_exposures, tuple) or any(
            not isinstance(exposure, ScheduledLtcExposure)
            for exposure in self.scheduled_exposures
        ):
            raise ValueError(
                "scheduled_exposures must be an immutable tuple of exposures"
            )
        horizon_minutes = self.horizon_days * DAY_MINUTES
        target_times: set[tuple[str, int]] = set()
        for exposure in self.scheduled_exposures:
            if exposure.exposure_minute % self.timestep_minutes:
                raise ValueError(
                    "scheduled exposures must fall on a simulator boundary"
                )
            if exposure.exposure_minute > horizon_minutes:
                raise ValueError("scheduled exposure exceeds the horizon")
            target_time = (
                exposure.target_person_id,
                exposure.exposure_minute,
            )
            if target_time in target_times:
                raise ValueError(
                    "a person may have only one scheduled external mechanism "
                    "on a timestep"
                )
            target_times.add(target_time)
        _validate_evidence(
            self.evidence_status,
            self.evidence_reference,
            field_name="scenario configuration",
        )


@dataclass(frozen=True, slots=True)
class PrivateLtcEngineMetadata:
    """Commitments retained only in the trusted evaluator process."""

    backend_name: str
    backend_version: str
    timestep_minutes: int
    scenario_configuration_sha256: str
    role_ward_metadata_sha256: str
    contact_trace_sha256: str
    static_network_sha256: str
    exposure_schedule_sha256: str
    scenario_commitment_sha256: str
    static_contact_aggregation: str
    scenario_evidence_status: str
    natural_history_evidence_status: str
    intervention_evidence_status: str


@dataclass(frozen=True, slots=True)
class LtcTransmissionEvent:
    """Detached, private infection ancestry in facility person IDs."""

    target_person_id: str
    source_person_id: str | None
    infection_minute: int
    mechanism: str


@dataclass(frozen=True, slots=True)
class LtcPersonLatentState:
    """Private person state at one deterministic simulation boundary."""

    person_id: str
    role: str
    ward_id: str | None
    room_id: str | None
    state: str
    symptom_onset_minute: int | None
    infection_minute: int | None
    recovery_minute: int | None
    relative_infectiousness: float


@dataclass(frozen=True, slots=True)
class LtcLatentFrame:
    """Private full-population frame for later observation projection."""

    minute: int
    people: tuple[LtcPersonLatentState, ...]
    transmission_events: tuple[LtcTransmissionEvent, ...]
    applied_control_ids: tuple[str, ...]
    terminal: bool


@dataclass(frozen=True, slots=True)
class LtcAdvanceDelta:
    start_minute: int
    end_minute: int
    frames: tuple[LtcLatentFrame, ...]
    applied_control_ids: tuple[str, ...]
    terminal: bool


@dataclass(frozen=True, slots=True)
class _PersonRecord:
    person_id: str
    role: str
    ward_id: str | None
    room_id: str | None


@dataclass(frozen=True, slots=True)
class _ContactRecord:
    contact_id: str
    person_a_id: str
    person_b_id: str
    start_minute: int
    duration_minutes: int
    setting: str
    location_id: str | None


@dataclass(frozen=True, slots=True)
class _ResolvedExposure:
    mechanism: str
    target_uid: int
    exposure_minute: int
    threshold: float


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _scenario_commitment(parts: Mapping[str, str]) -> str:
    return _canonical_sha256(dict(sorted(parts.items())))


def _deterministic_unit_interval(seed: int, domain: str, person_id: str) -> float:
    hasher = hashlib.sha256()
    hasher.update(b"epiagentbench:ltc-norovirus-v3\x00")
    for value in (str(seed), domain, person_id):
        encoded = value.encode("utf-8")
        hasher.update(len(encoded).to_bytes(4, "big"))
        hasher.update(encoded)
    return int.from_bytes(hasher.digest()[:8], "big") / 2**64


def public_engine_descriptor() -> dict[str, str]:
    """Return the complete public engine description.

    It intentionally excludes version, seed, commitments, trace structure,
    mechanism schedule, model parameters, evidence labels, and latent counts.
    Those values must remain across the evaluator/agent process boundary.
    """

    return {
        "engine_family": "institutional_disease_simulator",
        "model_status": PUBLIC_MODEL_STATUS,
    }


def _load_starsim() -> Any:
    os.environ.setdefault("STARSIM_INSTALL_FONTS", "0")
    try:
        import starsim as ss
    except ModuleNotFoundError as exc:
        if exc.name == "starsim":
            raise EngineError(
                "Starsim is optional and evaluator-only; install the pinned "
                f"starsim=={SUPPORTED_STARSIM_VERSION} dependency"
            ) from exc
        raise

    if getattr(ss, "__version__", None) != SUPPORTED_STARSIM_VERSION:
        raise EngineError("unsupported Starsim version for the LTC v3 engine")
    required = (
        "BoolArr",
        "BoolState",
        "FloatArr",
        "Infection",
        "Network",
        "Route",
        "Sim",
        "StaticNet",
        "days",
        "infection_log",
        "perday",
        "uids",
    )
    if any(not hasattr(ss, name) for name in required):
        raise EngineError("pinned Starsim lacks a required LTC v3 capability")
    return ss


def _read_trace(trace: Any) -> tuple[tuple[_PersonRecord, ...], tuple[_ContactRecord, ...]]:
    """Detach the strict ``institution_traces`` contract without retaining it."""

    try:
        raw_people = trace.people
        raw_contacts = trace.contacts
    except AttributeError as exc:
        raise ValueError("trace does not implement the institution trace contract") from exc

    people: list[_PersonRecord] = []
    for raw in raw_people:
        try:
            person = _PersonRecord(
                person_id=raw.person_id,
                role=raw.role,
                ward_id=raw.ward_id,
                room_id=raw.room_id,
            )
        except AttributeError as exc:
            raise ValueError("trace person is missing a required field") from exc
        if (
            not isinstance(person.person_id, str)
            or not person.person_id.strip()
            or person.role not in SUPPORTED_ROLES
            or (
                person.ward_id is not None
                and (
                    not isinstance(person.ward_id, str)
                    or not person.ward_id.strip()
                )
            )
            or (
                person.room_id is not None
                and (
                    not isinstance(person.room_id, str)
                    or not person.room_id.strip()
                )
            )
        ):
            raise ValueError("trace person contains invalid private metadata")
        if person.role == RESIDENT and person.ward_id is None:
            raise ValueError("every resident must have a ward assignment")
        people.append(person)
    people.sort(key=lambda item: item.person_id)
    if len(people) < 2 or len({person.person_id for person in people}) != len(people):
        raise ValueError("trace must contain at least two uniquely identified people")
    roles = {person.role for person in people}
    if not {RESIDENT, STAFF} <= roles:
        raise ValueError("an LTC trace must contain residents and staff")

    valid_ids = {person.person_id for person in people}
    contacts: list[_ContactRecord] = []
    for raw in raw_contacts:
        try:
            contact = _ContactRecord(
                contact_id=raw.contact_id,
                person_a_id=raw.person_a_id,
                person_b_id=raw.person_b_id,
                start_minute=raw.start_minute,
                duration_minutes=raw.duration_minutes,
                setting=raw.setting,
                location_id=raw.location_id,
            )
        except AttributeError as exc:
            raise ValueError("trace contact is missing a required field") from exc
        if (
            not isinstance(contact.contact_id, str)
            or not contact.contact_id.strip()
            or contact.person_a_id not in valid_ids
            or contact.person_b_id not in valid_ids
            or contact.person_a_id == contact.person_b_id
            or type(contact.start_minute) is not int
            or contact.start_minute < 0
            or type(contact.duration_minutes) is not int
            or contact.duration_minutes < 1
            or not isinstance(contact.setting, str)
            or not contact.setting.strip()
            or (
                contact.location_id is not None
                and (
                    not isinstance(contact.location_id, str)
                    or not contact.location_id.strip()
                )
            )
        ):
            raise ValueError("trace contact contains invalid private metadata")
        contacts.append(contact)
    contacts.sort(key=lambda item: item.contact_id)
    if not contacts:
        raise ValueError("trace must contain at least one explicit contact")
    if len({contact.contact_id for contact in contacts}) != len(contacts):
        raise ValueError("trace contact IDs must be unique")
    return tuple(people), tuple(contacts)


def _make_static_network(
    ss: Any,
    people: tuple[_PersonRecord, ...],
    contacts: tuple[_ContactRecord, ...],
) -> tuple[Any, tuple[tuple[int, int], ...]]:
    """Aggregate explicit trace contacts to a deterministic static graph.

    The conversion intentionally does not infer a dose or calibrated edge
    weight from contact duration.  One undirected edge is present for every
    unique pair that appears in the committed contact trace.
    """

    try:
        import networkx as nx
    except ModuleNotFoundError as exc:
        if exc.name == "networkx":
            raise EngineError("Starsim's static-network dependency is unavailable") from exc
        raise
    uid_by_id = {person.person_id: uid for uid, person in enumerate(people)}
    edge_set = {
        tuple(
            sorted(
                (
                    uid_by_id[contact.person_a_id],
                    uid_by_id[contact.person_b_id],
                )
            )
        )
        for contact in contacts
    }
    edges = tuple(sorted(edge_set))
    if not edges:
        raise EngineError("the explicit trace produced no static contact edges")
    graph = nx.Graph()
    graph.add_nodes_from(range(len(people)))
    graph.add_edges_from(edges)
    return ss.StaticNet(graph=graph), edges


def _make_scheduled_route(
    ss: Any,
    mechanism: str,
    exposures: tuple[_ResolvedExposure, ...],
    timestep_minutes: int,
) -> Any:
    by_step: dict[int, tuple[_ResolvedExposure, ...]] = {}
    for exposure in exposures:
        step = exposure.exposure_minute // timestep_minutes
        by_step[step] = (*by_step.get(step, ()), exposure)

    class PrecommittedLtcRoute(ss.Route):
        def __init__(self) -> None:
            super().__init__(name=mechanism, label=mechanism.replace("_", " "))
            self.absolute_level = 1.0
            self.candidates_by_step = by_step
            self.emitted: dict[tuple[int, int], str] = {}

        def compute_transmission(
            self,
            rel_sus: Any,
            rel_trans: Any,
            disease_beta: Any,
            disease: Any = None,
        ) -> Any:
            del rel_trans, disease_beta
            if disease is None:
                raise EngineError("scheduled LTC route requires a disease")
            step = int(disease.ti)
            selected: list[int] = []
            for exposure in self.candidates_by_step.get(step, ()):
                uid = exposure.target_uid
                susceptibility = float(rel_sus.raw[uid])
                if (
                    susceptibility > 0.0
                    and exposure.threshold
                    < self.absolute_level * susceptibility
                ):
                    selected.append(uid)
                    self.emitted[(step, uid)] = mechanism
            return ss.uids(selected)

        def step(self) -> None:
            return None

    return PrecommittedLtcRoute()


def _make_norovirus_disease(
    ss: Any,
    *,
    config: LtcStarsimV3Config,
    people: tuple[_PersonRecord, ...],
) -> Any:
    """Create a Starsim disease with explicit incubation and symptom states."""

    dt_days = config.timestep_minutes / DAY_MINUTES
    incubation_steps_float = config.natural_history.incubation_days / dt_days
    infectious_steps_float = config.natural_history.infectious_days / dt_days
    incubation_steps = int(round(incubation_steps_float))
    infectious_steps = int(round(infectious_steps_float))
    if not math.isclose(
        incubation_steps_float, incubation_steps, rel_tol=0.0, abs_tol=1e-9
    ) or not math.isclose(
        infectious_steps_float, infectious_steps, rel_tol=0.0, abs_tol=1e-9
    ):
        raise ValueError(
            "natural-history durations must be exact simulator timestep multiples"
        )
    if incubation_steps < 1 or infectious_steps < 1:
        raise ValueError("natural-history durations must span at least one timestep")

    profile_by_role = {
        profile.role: profile for profile in config.natural_history.role_profiles
    }
    missing_roles = {person.role for person in people} - set(profile_by_role)
    if missing_roles:
        raise ValueError("natural history lacks a profile for a trace role")
    role_by_uid = tuple(person.role for person in people)
    person_id_by_uid = tuple(person.person_id for person in people)

    class LtcNorovirusDisease(ss.Infection):
        def __init__(self) -> None:
            super().__init__()
            self.define_pars(
                beta=ss.perday(config.natural_history.contact_beta_per_day),
                init_prev=None,
            )
            self.define_states(
                ss.BoolState("susceptible", default=True, label="Susceptible"),
                ss.BoolState("infected", label="Infected"),
                ss.BoolState("exposed", label="Exposed/incubating"),
                ss.BoolState(
                    "infectious_symptomatic",
                    label="Symptomatic infectious",
                ),
                ss.BoolState(
                    "infectious_asymptomatic",
                    label="Asymptomatic infectious",
                ),
                ss.BoolState("recovered", label="Recovered"),
                ss.BoolArr("will_be_symptomatic", label="Symptom prognosis"),
                ss.FloatArr("ti_infected", label="Time of acquisition"),
                ss.FloatArr("ti_infectious", label="Time infectiousness begins"),
                ss.FloatArr("ti_recovered", label="Time of recovery"),
                ss.FloatArr("rel_sus", default=1.0, label="Relative susceptibility"),
                ss.FloatArr("rel_trans", default=0.0, label="Relative transmission"),
                reset=True,
            )

        @property
        def infectious(self) -> Any:
            return self.infectious_symptomatic | self.infectious_asymptomatic

        def set_outcomes(self, uids: Any, sources: Any = None) -> None:
            # All trace people are LTC residents/staff/visitors, never congenital
            # cases.  Bypassing Infection.set_outcomes avoids coupling this model
            # to Starsim's synthetic age distribution.
            self.set_prognoses(uids, sources)

        def set_prognoses(self, uids: Any, sources: Any = None) -> None:
            super().set_prognoses(uids, sources)
            ti = int(self.ti)
            self.susceptible[uids] = False
            self.infected[uids] = True
            self.exposed[uids] = True
            self.infectious_symptomatic[uids] = False
            self.infectious_asymptomatic[uids] = False
            self.recovered[uids] = False
            self.ti_infected[uids] = ti
            self.ti_infectious[uids] = ti + incubation_steps
            self.ti_recovered[uids] = ti + incubation_steps + infectious_steps
            for uid_value in uids:
                uid = int(uid_value)
                profile = profile_by_role[role_by_uid[uid]]
                draw = _deterministic_unit_interval(
                    config.random_seed,
                    "symptom-prognosis",
                    person_id_by_uid[uid],
                )
                self.will_be_symptomatic[ss.uids([uid])] = (
                    draw < profile.symptomatic_probability
                )
            self.rel_trans[uids] = 0.0

        def step_state(self) -> None:
            ti = int(self.ti)
            newly_infectious = (
                self.exposed & (self.ti_infectious <= ti)
            ).uids
            if len(newly_infectious):
                self.exposed[newly_infectious] = False
                for uid_value in newly_infectious:
                    uid = int(uid_value)
                    one = ss.uids([uid])
                    profile = profile_by_role[role_by_uid[uid]]
                    if bool(self.will_be_symptomatic[one][0]):
                        self.infectious_symptomatic[one] = True
                        self.rel_trans[one] = (
                            profile.symptomatic_relative_infectiousness
                        )
                    else:
                        self.infectious_asymptomatic[one] = True
                        self.rel_trans[one] = (
                            profile.asymptomatic_relative_infectiousness
                        )

            recovered = (
                self.infected & (self.ti_recovered <= ti)
            ).uids
            if len(recovered):
                self.exposed[recovered] = False
                self.infectious_symptomatic[recovered] = False
                self.infectious_asymptomatic[recovered] = False
                self.infected[recovered] = False
                self.recovered[recovered] = True
                self.rel_trans[recovered] = 0.0

    return LtcNorovirusDisease()


class LtcNorovirusStarsimEngine:
    """Trusted, fixed-step LTC simulator with deterministic latent frames."""

    def __init__(self, trace: Any, config: LtcStarsimV3Config):
        if not isinstance(config, LtcStarsimV3Config):
            raise ValueError("config must be an LtcStarsimV3Config")
        people, contacts = _read_trace(trace)
        person_by_id = {person.person_id: person for person in people}
        if any(person_id not in person_by_id for person_id in config.seed_person_ids):
            raise ValueError("seed person is not present in the facility trace")
        if any(
            exposure.target_person_id not in person_by_id
            for exposure in config.scheduled_exposures
        ):
            raise ValueError("scheduled exposure target is not in the facility trace")

        ss = _load_starsim()
        self._config = config
        self._people = people
        self._contacts = contacts
        self._person_by_id = person_by_id
        self._uid_by_person_id = {
            person.person_id: uid for uid, person in enumerate(people)
        }
        self._person_id_by_uid = tuple(person.person_id for person in people)
        self._horizon_minutes = config.horizon_days * DAY_MINUTES
        self._timestep_minutes = config.timestep_minutes
        self._current_minute = 0
        self._terminal = False
        self._closed = False
        self._pending_controls: list[EngineControl] = []
        self._known_control_ids: set[str] = set()
        self._applied_control_ids: list[str] = []
        self._contact_level = 1.0
        self._staff_levels: dict[str, float] = {}
        self._route_levels = {
            COMMON_SOURCE: 1.0,
            IMPORTATION: 1.0,
            ENVIRONMENTAL: 1.0,
        }
        self._frames: list[LtcLatentFrame] = []

        contact_network, static_edges = _make_static_network(ss, people, contacts)
        resolved_exposures = tuple(
            _ResolvedExposure(
                mechanism=exposure.mechanism,
                target_uid=self._uid_by_person_id[exposure.target_person_id],
                exposure_minute=exposure.exposure_minute,
                threshold=exposure.threshold,
            )
            for exposure in config.scheduled_exposures
        )
        by_mechanism = {
            mechanism: tuple(
                exposure
                for exposure in resolved_exposures
                if exposure.mechanism == mechanism
            )
            for mechanism in SCHEDULED_MECHANISMS
        }
        external_routes = [
            _make_scheduled_route(
                ss,
                mechanism,
                by_mechanism[mechanism],
                config.timestep_minutes,
            )
            for mechanism in (COMMON_SOURCE, IMPORTATION, ENVIRONMENTAL)
            if by_mechanism[mechanism]
        ]
        disease = _make_norovirus_disease(
            ss,
            config=config,
            people=people,
        )

        role_ward_records = [
            {
                "person_id": person.person_id,
                "role": person.role,
                "ward_id": person.ward_id,
                "room_id": person.room_id,
            }
            for person in people
        ]
        contact_records = [asdict(contact) for contact in contacts]
        exposure_records = [asdict(exposure) for exposure in config.scheduled_exposures]
        commitments = {
            "scenario_configuration": _canonical_sha256(asdict(config)),
            "role_ward_metadata": _canonical_sha256(role_ward_records),
            "contact_trace": _canonical_sha256(contact_records),
            "static_network": _canonical_sha256(
                {
                    "aggregation": STATIC_CONTACT_AGGREGATION,
                    "edges": static_edges,
                }
            ),
            "exposure_schedule": _canonical_sha256(exposure_records),
        }
        self._private_metadata = PrivateLtcEngineMetadata(
            backend_name=BACKEND_NAME,
            backend_version=ss.__version__,
            timestep_minutes=config.timestep_minutes,
            scenario_configuration_sha256=commitments[
                "scenario_configuration"
            ],
            role_ward_metadata_sha256=commitments["role_ward_metadata"],
            contact_trace_sha256=commitments["contact_trace"],
            static_network_sha256=commitments["static_network"],
            exposure_schedule_sha256=commitments["exposure_schedule"],
            scenario_commitment_sha256=_scenario_commitment(commitments),
            static_contact_aggregation=STATIC_CONTACT_AGGREGATION,
            scenario_evidence_status=config.evidence_status,
            natural_history_evidence_status=(
                config.natural_history.evidence_status
            ),
            intervention_evidence_status=(
                config.intervention_assumptions.evidence_status
            ),
        )

        self._sim = ss.Sim(
            n_agents=len(people),
            start=ss.days(0),
            dur=ss.days(config.horizon_days),
            dt=ss.days(config.timestep_minutes / DAY_MINUTES),
            rand_seed=config.random_seed,
            verbose=0,
            networks=[*external_routes, contact_network],
            diseases=disease,
            analyzers=ss.infection_log(),
        )
        try:
            self._sim.init()
            self._disease = self._sim.get_module("ltcnorovirusdisease")
            # Sim initialization owns/copies module instances; retain the
            # initialized final route rather than the constructor input.
            self._contact_network = self._sim.networks[-1]
            self._assert_disease_capabilities()
            seed_uids = ss.uids(
                [
                    self._uid_by_person_id[person_id]
                    for person_id in config.seed_person_ids
                ]
            )
            self._disease.set_prognoses(seed_uids, sources=-1)
            self._disease.pars._n_initial_cases = len(seed_uids)
            self._baseline_edge_beta = self._contact_network.beta.copy()
            self._routes = {
                mechanism: self._sim.get_module(mechanism)
                for mechanism in SCHEDULED_MECHANISMS
                if by_mechanism[mechanism]
            }
            # Process the opening (ti=0) endpoint once.  Subsequent logical
            # frames then coincide with Starsim's ti=1, ti=2, ... states rather
            # than lagging one boundary behind their recorded transition time.
            self._sim.run(until=self._sim.now, verbose=0)
            seed_events = [
                event
                for event in self._transmission_events()
                if event.mechanism == SEED
            ]
            if len(seed_events) != len(config.seed_person_ids):
                raise EngineError("Starsim did not preserve exact seed introductions")
            self._frames.append(self._latent_frame())
        except Exception:
            self._sim = None
            self._closed = True
            raise

    @property
    def current_minute(self) -> int:
        return self._current_minute

    @property
    def terminal(self) -> bool:
        return self._terminal

    @property
    def private_metadata(self) -> PrivateLtcEngineMetadata:
        self._ensure_open()
        return self._private_metadata

    @property
    def private_trajectory(self) -> tuple[LtcLatentFrame, ...]:
        self._ensure_open()
        return tuple(self._frames)

    @property
    def public_descriptor(self) -> dict[str, str]:
        return public_engine_descriptor()

    def apply_control(self, control: EngineControl) -> None:
        """Schedule an absolute, CRN-safe intervention level.

        Contact controls change weights on a fixed edge array, never its shape
        or order.  Source/environment controls gate fixed thresholds.  Staff
        exclusion affects contact edges incident to one staff member; it does
        not rewrite infection states or suppress outside acquisition.
        """

        self._ensure_open()
        if self._terminal:
            raise EngineError("cannot schedule a control after the horizon")
        if not isinstance(control, EngineControl):
            raise ValueError("control must be an EngineControl")
        if not control.control_id or control.control_id.isspace():
            raise ValueError("control_id must be non-empty")
        if control.control_id in self._known_control_ids:
            raise ValueError("control_id must be unique within an engine run")
        if control.kind not in SUPPORTED_CONTROL_KINDS:
            raise UnsupportedControlError("unsupported LTC v3 control kind")
        if (
            type(control.effective_minute) is not int
            or control.effective_minute % self._timestep_minutes
            or not self._current_minute
            <= control.effective_minute
            < self._horizon_minutes
        ):
            raise ValueError("control time must be a remaining simulator boundary")
        _finite_probability(control.magnitude, "control magnitude")
        if control.kind == STAFF_EXCLUSION_LEVEL:
            target = self._person_by_id.get(control.target_id or "")
            if target is None or target.role != STAFF:
                raise UnsupportedControlError(
                    "staff exclusion requires a configured staff target"
                )
        elif control.target_id is not None:
            raise UnsupportedControlError(
                "this LTC v3 control kind does not accept a target"
            )
        self._known_control_ids.add(control.control_id)
        self._pending_controls.append(control)
        self._pending_controls.sort(
            key=lambda item: (item.effective_minute, item.control_id)
        )

    def advance_to(self, target_minute: int) -> LtcAdvanceDelta:
        self._ensure_open()
        if type(target_minute) is not int:
            raise TypeError("target_minute must be an integer")
        if target_minute % self._timestep_minutes:
            raise ValueError("target_minute must be a simulator boundary")
        if not self._current_minute <= target_minute <= self._horizon_minutes:
            raise ValueError("target_minute is outside the remaining horizon")

        start = self._current_minute
        frames: list[LtcLatentFrame] = []
        applied: list[str] = []
        while self._current_minute < target_minute:
            applied.extend(self._activate_due_controls(self._current_minute))
            self._sim.run(until=self._sim.now, verbose=0)
            self._current_minute += self._timestep_minutes
            if self._current_minute == self._horizon_minutes:
                if not self._sim.complete:
                    raise EngineError("Starsim did not finalize at the v3 horizon")
                self._terminal = True
            frame = self._latent_frame()
            self._frames.append(frame)
            frames.append(frame)
        return LtcAdvanceDelta(
            start_minute=start,
            end_minute=self._current_minute,
            frames=tuple(frames),
            applied_control_ids=tuple(applied),
            terminal=self._terminal,
        )

    def private_snapshot(self) -> LtcLatentFrame:
        self._ensure_open()
        return self._latent_frame()

    def close(self) -> None:
        if self._closed:
            return
        self._pending_controls.clear()
        self._routes.clear()
        self._sim = None
        self._closed = True

    def _assert_disease_capabilities(self) -> None:
        required_states = (
            "susceptible",
            "infected",
            "exposed",
            "infectious_symptomatic",
            "infectious_asymptomatic",
            "recovered",
            "will_be_symptomatic",
            "ti_infected",
            "ti_infectious",
            "ti_recovered",
            "rel_sus",
            "rel_trans",
        )
        if any(not hasattr(self._disease, name) for name in required_states):
            raise EngineError("Starsim dropped a required LTC disease state")
        try:
            original = self._disease.rel_trans.raw.copy()
            self._disease.rel_trans[:] = original
        except Exception as exc:
            raise EngineError(
                "Starsim cannot support role/symptom relative infectiousness"
            ) from exc

    def _activate_due_controls(self, minute: int) -> tuple[str, ...]:
        due = [
            control
            for control in self._pending_controls
            if control.effective_minute <= minute
        ]
        if not due:
            return ()
        refresh_contacts = False
        for control in due:
            if control.kind == CONTACT_REDUCTION_LEVEL:
                self._contact_level = float(control.magnitude)
                refresh_contacts = True
            elif control.kind == STAFF_EXCLUSION_LEVEL:
                assert control.target_id is not None
                self._staff_levels[control.target_id] = float(control.magnitude)
                refresh_contacts = True
            elif control.kind == SOURCE_CONTROL_LEVEL:
                self._set_route_level(COMMON_SOURCE, float(control.magnitude))
            elif control.kind == ENTRY_CONTROL_LEVEL:
                self._set_route_level(IMPORTATION, float(control.magnitude))
            elif control.kind == ENVIRONMENTAL_CONTROL_LEVEL:
                self._set_route_level(ENVIRONMENTAL, float(control.magnitude))
            else:
                raise UnsupportedControlError("corrupt pending LTC v3 control")
            self._pending_controls.remove(control)
            self._applied_control_ids.append(control.control_id)
        if refresh_contacts:
            self._refresh_contact_levels()
        return tuple(control.control_id for control in due)

    def _set_route_level(self, mechanism: str, level: float) -> None:
        self._route_levels[mechanism] = level
        route = self._routes.get(mechanism)
        if route is not None:
            route.absolute_level = level

    def _refresh_contact_levels(self) -> None:
        values = self._baseline_edge_beta.copy()
        for index, (left_value, right_value) in enumerate(
            zip(
                self._contact_network.p1,
                self._contact_network.p2,
                strict=True,
            )
        ):
            left_id = self._person_id_by_uid[int(left_value)]
            right_id = self._person_id_by_uid[int(right_value)]
            staff_level = self._staff_levels.get(left_id, 1.0) * (
                self._staff_levels.get(right_id, 1.0)
            )
            values[index] *= self._contact_level * staff_level
        self._contact_network.beta[:] = values

    def _latent_frame(self) -> LtcLatentFrame:
        disease = self._disease
        states: list[LtcPersonLatentState] = []
        for uid, person in enumerate(self._people):
            one = uid
            flags = {
                SUSCEPTIBLE: bool(disease.susceptible.raw[one]),
                EXPOSED_INCUBATING: bool(disease.exposed.raw[one]),
                INFECTIOUS_SYMPTOMATIC: bool(
                    disease.infectious_symptomatic.raw[one]
                ),
                INFECTIOUS_ASYMPTOMATIC: bool(
                    disease.infectious_asymptomatic.raw[one]
                ),
                RECOVERED: bool(disease.recovered.raw[one]),
            }
            active = [name for name, enabled in flags.items() if enabled]
            if len(active) != 1:
                raise EngineError("LTC disease states do not form a partition")
            state = active[0]
            infection_step = float(disease.ti_infected.raw[one])
            infectious_step = float(disease.ti_infectious.raw[one])
            recovery_step = float(disease.ti_recovered.raw[one])
            will_symptom = bool(disease.will_be_symptomatic.raw[one])
            states.append(
                LtcPersonLatentState(
                    person_id=person.person_id,
                    role=person.role,
                    ward_id=person.ward_id,
                    room_id=person.room_id,
                    state=state,
                    symptom_onset_minute=(
                        int(round(infectious_step * self._timestep_minutes))
                        if will_symptom and math.isfinite(infectious_step)
                        else None
                    ),
                    infection_minute=(
                        int(round(infection_step * self._timestep_minutes))
                        if math.isfinite(infection_step)
                        else None
                    ),
                    recovery_minute=(
                        int(round(recovery_step * self._timestep_minutes))
                        if math.isfinite(recovery_step)
                        else None
                    ),
                    relative_infectiousness=float(disease.rel_trans.raw[one]),
                )
            )
        return LtcLatentFrame(
            minute=self._current_minute,
            people=tuple(states),
            transmission_events=self._transmission_events(),
            applied_control_ids=tuple(self._applied_control_ids),
            terminal=self._terminal,
        )

    def _transmission_events(self) -> tuple[LtcTransmissionEvent, ...]:
        disease = self._disease
        source_by_target: dict[int, int | None] = {}
        infection_log = disease.infection_log
        if infection_log is None:
            for analyzer in self._sim.analyzers.values():
                logs = getattr(analyzer, "logs", None)
                if logs is not None and disease.name in logs:
                    infection_log = logs[disease.name]
                    break
        if infection_log is not None:
            for source, target, _ in infection_log.edges(keys=True):
                try:
                    source_uid = int(source)
                except (TypeError, ValueError, OverflowError):
                    source_uid = -1
                source_by_target[int(target)] = (
                    source_uid if source_uid >= 0 else None
                )

        external_by_event: dict[tuple[int, int], str] = {}
        for route in self._routes.values():
            for (step, uid), mechanism in route.emitted.items():
                external_by_event[(step * self._timestep_minutes, uid)] = mechanism

        events: list[LtcTransmissionEvent] = []
        for uid, infection_step in enumerate(
            disease.ti_infected.raw[: len(self._people)]
        ):
            if not math.isfinite(float(infection_step)):
                continue
            minute = int(round(float(infection_step) * self._timestep_minutes))
            source_uid = source_by_target.get(uid)
            if source_uid is None:
                mechanism = external_by_event.get((minute, uid), SEED)
                source_person_id = None
            else:
                mechanism = PERSON_TO_PERSON
                source_person_id = self._person_id_by_uid[source_uid]
            events.append(
                LtcTransmissionEvent(
                    target_person_id=self._person_id_by_uid[uid],
                    source_person_id=source_person_id,
                    infection_minute=minute,
                    mechanism=mechanism,
                )
            )
        return tuple(
            sorted(
                events,
                key=lambda event: (
                    event.infection_minute,
                    event.target_person_id,
                ),
            )
        )

    def _ensure_open(self) -> None:
        if self._closed:
            raise EngineClosedError("the LTC v3 disease engine is closed")
