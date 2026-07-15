"""Secure closed-loop adapter for the development LTC norovirus engine.

LTC means long-term care.  This module keeps each episode's facility trace,
raw person identifiers, realized parameter draw, scheduled exposure routes,
and latent states inside the evaluator.  It exposes only the existing
surveillance DTOs through ``ClosedLoopStarsimRuntime``.  The numeric
development defaults in this public source file are not private calibration
parameters and must be replaced by a committed private profile before a
production cohort is frozen.

The model is a development candidate, not a calibrated or validated model.
The operational trace is currently aggregated to a static Starsim network;
contact timing and duration are not yet transmission doses.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any, Mapping

from ..ltc_scenario import ltc_norovirus_hypothesis_catalog
from ..models import EpisodeBundle
from .engine import EngineControl, OracleSnapshot, TransmissionEvent
from .institution_traces import (
    InstitutionTrace,
    InstitutionTraceConfig,
    generate_institution_trace,
)
from .live_starsim_runtime import ClosedLoopStarsimRuntime
from .starsim_ltc_v3 import (
    COMMON_SOURCE,
    CONTACT_REDUCTION_LEVEL,
    ENTRY_CONTROL_LEVEL,
    EXPOSED_INCUBATING,
    IMPORTATION,
    INFECTIOUS_ASYMPTOMATIC,
    INFECTIOUS_SYMPTOMATIC,
    PRIOR_PLACEHOLDER,
    RESIDENT,
    STAFF,
    VISITOR,
    SOURCE_CONTROL_LEVEL,
    LtcNorovirusNaturalHistory,
    LtcNorovirusStarsimEngine,
    RoleInfectiousnessProfile,
    LtcStarsimV3Config,
    ScheduledLtcExposure,
)
from .surveillance import (
    DAY_MINUTES,
    LIVE_PROFILE_RESOURCE,
    load_gi_surveillance_profile,
)


BACKEND_NAME = "starsim-ltc-v3"
SUPPORTED_FAMILIES: Mapping[str, str] = {
    "institution_person_to_person": "person_to_person",
    "restaurant_point_source": "common_source",
    "repeated_introduction": "repeated_introduction",
    "coincidental_venue": "background",
    "reporting_artifact": "reporting_artifact",
}
CONTROL_KINDS: Mapping[str, str | None] = {
    "infection_control": CONTACT_REDUCTION_LEVEL,
    "source_control": SOURCE_CONTROL_LEVEL,
    "entry_control": ENTRY_CONTROL_LEVEL,
    # Reporting correction changes precommitted record artifacts, not biology.
    "audit_reporting": None,
}
_ACTIVE_STATES = frozenset(
    {
        EXPOSED_INCUBATING,
        INFECTIOUS_SYMPTOMATIC,
        INFECTIOUS_ASYMPTOMATIC,
    }
)


def _private_seed(key: bytes, public_seed: int, domain: str) -> int:
    digest = hmac.new(
        key,
        f"epiagentbench:ltc-v3:{public_seed}:{domain}".encode("ascii"),
        hashlib.sha256,
    ).digest()
    return int.from_bytes(digest[:8], "big") % (2**31 - 1)


def _threshold(key: bytes, public_seed: int, label: str) -> float:
    value = _private_seed(key, public_seed, f"threshold:{label}")
    return value / float(2**31 - 1)


class _LtcDiseaseEngineAdapter:
    """Translate the richer LTC engine to the shared trusted engine contract."""

    def __init__(self, trace: InstitutionTrace, config: LtcStarsimV3Config):
        self._engine = LtcNorovirusStarsimEngine(trace, config)
        ordered_people = tuple(sorted(trace.people, key=lambda item: item.person_id))
        self._agent_by_person = {
            person.person_id: index for index, person in enumerate(ordered_people)
        }

    @property
    def current_minute(self) -> int:
        return self._engine.current_minute

    @property
    def terminal(self) -> bool:
        return self._engine.terminal

    @property
    def private_metadata(self) -> Any:
        return self._engine.private_metadata

    def apply_control(self, control: EngineControl) -> None:
        self._engine.apply_control(control)

    def advance_to(self, target_minute: int) -> Any:
        return self._engine.advance_to(target_minute)

    def oracle_snapshot(self) -> OracleSnapshot:
        frame = self._engine.private_snapshot()
        events = tuple(
            TransmissionEvent(
                target_agent_id=self._agent_by_person[event.target_person_id],
                source_agent_id=(
                    None
                    if event.source_person_id is None
                    else self._agent_by_person[event.source_person_id]
                ),
                infection_minute=event.infection_minute,
                mechanism=event.mechanism,
            )
            for event in frame.transmission_events
        )
        infected = frozenset(event.target_agent_id for event in events)
        currently_infected = tuple(
            self._agent_by_person[person.person_id]
            for person in frame.people
            if person.state in _ACTIVE_STATES
        )
        recovered = tuple(
            self._agent_by_person[person.person_id]
            for person in frame.people
            if person.state == "recovered"
        )
        population = len(frame.people)
        return OracleSnapshot(
            minute=frame.minute,
            terminal=frame.terminal,
            population_size=population,
            alive_agent_ids=tuple(range(population)),
            ever_infected_agent_ids=tuple(sorted(infected)),
            currently_infected_agent_ids=tuple(sorted(currently_infected)),
            recovered_agent_ids=tuple(sorted(recovered)),
            dead_agent_ids=(),
            applied_control_ids=frame.applied_control_ids,
            transmission_events=events,
        )

    def symptom_onsets(self) -> dict[int, int | None]:
        """Return simulator-derived symptoms for every realized infection."""

        frame = self._engine.private_snapshot()
        infected = {
            event.target_person_id for event in frame.transmission_events
        }
        return {
            self._agent_by_person[person.person_id]: person.symptom_onset_minute
            for person in frame.people
            if person.person_id in infected
        }

    def private_snapshot(self) -> Any:
        return self._engine.private_snapshot()

    def close(self) -> None:
        self._engine.close()


class LtcStarsimV3Backend:
    """Build a private role-aware LTC world for the secure episode broker."""

    def __init__(self, profile: Mapping[str, Any] | None = None):
        self._profile = dict(
            profile
            if profile is not None
            else load_gi_surveillance_profile(LIVE_PROFILE_RESOURCE)
        )

    def create_runtime(
        self,
        *,
        seed: int,
        family: str | None,
        presentation_key: bytes | None = None,
    ) -> ClosedLoopStarsimRuntime:
        if type(seed) is not int or seed < 0:
            raise ValueError("seed must be a non-negative integer")
        if presentation_key is None:
            presentation_key = hashlib.sha256(
                f"epiagentbench-development-ltc-v3:{seed}".encode("ascii")
            ).digest()
        if not isinstance(presentation_key, bytes) or len(presentation_key) < 16:
            raise ValueError("presentation_key must contain at least 16 bytes")

        selected_family = self._select_family(seed, family, presentation_key)
        causal_mode = SUPPORTED_FAMILIES[selected_family]
        trace = generate_institution_trace(
            InstitutionTraceConfig(
                seed=_private_seed(presentation_key, seed, "facility-trace"),
                ward_count=2,
                residents_per_ward=8,
                staff_per_ward=3,
                visitor_count=4,
                days=14,
            )
        )
        config, world_actions = self._scenario_config(
            seed=seed,
            presentation_key=presentation_key,
            trace=trace,
            causal_mode=causal_mode,
        )
        people = tuple(sorted(trace.people, key=lambda item: item.person_id))
        public_context = {
            index: {
                "facility_role": person.role,
                # IncrementalSurveillanceStream owns public pseudonymization.
                "ward_id": person.ward_id or "facility-wide",
            }
            for index, person in enumerate(people)
        }

        def engine_factory(value: LtcStarsimV3Config) -> _LtcDiseaseEngineAdapter:
            return _LtcDiseaseEngineAdapter(trace, value)

        initial_artifacts = 8 if causal_mode == "reporting_artifact" else 0
        future_artifacts = (
            ((720, 150_000), (1440, 450_000), (2160, 700_000), (2880, 900_000))
            if causal_mode == "reporting_artifact"
            else ()
        )
        return ClosedLoopStarsimRuntime(
            seed=_private_seed(presentation_key, seed, "observations"),
            presentation_key=presentation_key,
            profile=self._profile,
            config=config,
            growth_regime="ltc_development_prior",
            causal_mode=causal_mode,
            family=selected_family,
            initial_artifact_duplicates=initial_artifacts,
            future_artifact_candidates=future_artifacts,
            hypothesis_catalog=ltc_norovirus_hypothesis_catalog(),
            engine_factory=engine_factory,
            control_kinds=CONTROL_KINDS,
            world_present_biological_actions=world_actions,
            person_context_by_agent_id=public_context,
            symptom_onset_provider=lambda engine: engine.symptom_onsets(),
            trusted_state_provider=lambda engine: engine.private_snapshot(),
            # A precommitted, family-independent nuisance count adds shared
            # background variation. It does not make the family transcripts
            # exchangeable; matched-opening admission remains a release gate.
            background_episode_count=(
                8
                + _private_seed(
                    presentation_key, seed, "background-episode-count"
                )
                % 5
            ),
        )

    def create_episode(
        self,
        *,
        seed: int,
        family: str | None,
        presentation_key: bytes | None = None,
    ) -> EpisodeBundle:
        runtime = self.create_runtime(
            seed=seed,
            family=family,
            presentation_key=presentation_key,
        )
        try:
            public = runtime.public_episode
            oracle = runtime.finalize()
            return EpisodeBundle(public=public, oracle=oracle)
        finally:
            runtime.close()

    @staticmethod
    def _select_family(seed: int, family: str | None, key: bytes) -> str:
        if family is not None:
            if family not in SUPPORTED_FAMILIES:
                raise ValueError("Unsupported LTC v3 episode family")
            return family
        families = tuple(SUPPORTED_FAMILIES)
        return families[_private_seed(key, seed, "family") % len(families)]

    def _scenario_config(
        self,
        *,
        seed: int,
        presentation_key: bytes,
        trace: InstitutionTrace,
        causal_mode: str,
    ) -> tuple[LtcStarsimV3Config, tuple[str, ...]]:
        people = tuple(sorted(trace.people, key=lambda item: item.person_id))
        residents = [person.person_id for person in people if person.role == "resident"]
        staff = [person.person_id for person in people if person.role == "staff"]
        visitors = [person.person_id for person in people if person.role == "visitor"]
        if causal_mode == "person_to_person":
            seed_ids = tuple(residents[:3])
            beta = 0.35
            schedule: list[ScheduledLtcExposure] = []
            actions = ("infection_control",)
        elif causal_mode == "common_source":
            seed_ids = (residents[0],)
            beta = 0.025
            candidates = [
                *((person_id, 2 * DAY_MINUTES) for person_id in residents[2:8]),
                *((person_id, 9 * DAY_MINUTES) for person_id in residents[8:14]),
            ]
            schedule = [
                ScheduledLtcExposure(
                    mechanism=COMMON_SOURCE,
                    target_person_id=person_id,
                    exposure_minute=minute,
                    threshold=_threshold(
                        presentation_key, seed, f"common:{person_id}:{minute}"
                    ),
                )
                for person_id, minute in candidates
            ]
            actions = ("infection_control", "source_control")
        elif causal_mode == "repeated_introduction":
            seed_ids = (residents[0],)
            beta = 0.025
            outside_people = [*staff, *visitors]
            minutes = [
                DAY_MINUTES,
                DAY_MINUTES,
                3 * DAY_MINUTES,
                3 * DAY_MINUTES,
                5 * DAY_MINUTES,
                5 * DAY_MINUTES,
                9 * DAY_MINUTES,
                10 * DAY_MINUTES,
                11 * DAY_MINUTES,
            ]
            schedule = [
                ScheduledLtcExposure(
                    mechanism=IMPORTATION,
                    target_person_id=person_id,
                    exposure_minute=minute,
                    threshold=_threshold(
                        presentation_key, seed, f"import:{person_id}:{minute}"
                    ),
                )
                for person_id, minute in zip(
                    outside_people[: len(minutes)], minutes, strict=True
                )
            ]
            actions = ("infection_control", "entry_control")
        else:
            # One low-spread infection supplies a biologically plausible
            # background event without making it an institutional outbreak.
            seed_ids = (residents[0],)
            beta = 0.001
            schedule = []
            actions = ("infection_control",)

        growth = self._profile["closed_loop_configuration"][
            "growth_regime_multipliers"
        ]
        regime_names = tuple(sorted(growth))
        regime = regime_names[
            _private_seed(presentation_key, seed, "growth") % len(regime_names)
        ]
        natural_history = LtcNorovirusNaturalHistory(
            contact_beta_per_day=min(0.95, beta * float(growth[regime])),
            incubation_days=1.0,
            infectious_days=2.0,
            role_profiles=tuple(
                RoleInfectiousnessProfile(
                    role=role,
                    symptomatic_probability=0.85,
                    evidence_status=PRIOR_PLACEHOLDER,
                )
                for role in (RESIDENT, STAFF, VISITOR)
            ),
            evidence_status=PRIOR_PLACEHOLDER,
        )
        return (
            LtcStarsimV3Config(
                random_seed=_private_seed(
                    presentation_key, seed, "disease-simulator"
                ),
                seed_person_ids=seed_ids,
                evidence_status=PRIOR_PLACEHOLDER,
                horizon_days=14,
                timestep_minutes=360,
                natural_history=natural_history,
                scheduled_exposures=tuple(schedule),
            ),
            actions,
        )
