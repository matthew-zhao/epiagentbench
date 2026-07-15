"""Optional evaluator-only Starsim backend.

This adapter is a deterministic integration smoke test around Starsim's SIR
model.  It is not a calibrated enteric-disease model and must not be described
as epidemiologically realistic without separate calibration and validation.

The adapter is not itself a security boundary: it retains the private Starsim
object internally.  It must run in a trusted process/container, and only a
separate allow-listed investigation broker may communicate with the agent.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

from .engine import (
    EngineClosedError,
    EngineControl,
    EngineDelta,
    EngineError,
    LatentState,
    OracleSnapshot,
    PrivateEngineMetadata,
    TransmissionEvent,
    UnsupportedControlError,
)


DAY_MINUTES = 24 * 60
SUPPORTED_STARSIM_VERSION = "3.5.1"
GLOBAL_TRANSMISSION_MULTIPLIER = "global_transmission_multiplier"
GLOBAL_TRANSMISSION_LEVEL = "global_transmission_level"
CONTACT_TRANSMISSION_LEVEL = "contact_transmission_level"
COMMON_SOURCE_EXPOSURE_LEVEL = "common_source_exposure_level"
IMPORTATION_EXPOSURE_LEVEL = "importation_exposure_level"

COMMON_SOURCE = "common_source"
IMPORTATION = "importation"
EXOGENOUS_MECHANISMS = frozenset({COMMON_SOURCE, IMPORTATION})
CLUSTERED_STATIC_TOPOLOGY_VERSION = "clustered_static_v1"


@dataclass(frozen=True, slots=True)
class ScheduledExogenousExposure:
    """One private, precommitted opportunity for an external infection.

    At ``exposure_minute``, a still-susceptible target is infected when its
    fixed ``threshold`` is below the current absolute level for ``mechanism``.
    Keeping the threshold in the frozen episode configuration means factual
    and counterfactual engines never consume different random draws merely
    because a control suppressed an earlier exposure.
    """

    mechanism: str
    target_agent_id: int
    exposure_minute: int
    threshold: float


@dataclass(frozen=True, slots=True)
class ClusteredStaticTopology:
    """Private deterministic contact topology for institutional candidates.

    Each equal-sized cluster is an even-degree ring lattice over a private,
    seed-derived permutation of its members.  A small, fixed number of
    cross-cluster edges is then selected by domain-separated hashes.  The
    topology consumes no process-global RNG state and never enters a public
    episode payload.
    """

    cluster_size: int
    within_cluster_degree: int
    cross_cluster_edges_per_cluster: float = 0.0
    construction_version: str = CLUSTERED_STATIC_TOPOLOGY_VERSION

    def __post_init__(self) -> None:
        if self.construction_version != CLUSTERED_STATIC_TOPOLOGY_VERSION:
            raise ValueError("unsupported clustered-static topology version")
        if type(self.cluster_size) is not int or self.cluster_size < 4:
            raise ValueError("cluster_size must be an integer of at least four")
        if (
            type(self.within_cluster_degree) is not int
            or self.within_cluster_degree < 2
            or self.within_cluster_degree % 2
            or self.within_cluster_degree >= self.cluster_size
        ):
            raise ValueError(
                "within_cluster_degree must be an even integer from two "
                "through cluster_size - 1"
            )
        bridges = self.cross_cluster_edges_per_cluster
        if (
            type(bridges) not in (int, float)
            or not math.isfinite(float(bridges))
            or not 0.0 <= float(bridges) <= 1.0
        ):
            raise ValueError(
                "cross_cluster_edges_per_cluster must be finite and in [0, 1]"
            )


@dataclass(frozen=True, slots=True)
class StarsimSIRConfig:
    """Private configuration for the reference Starsim SIR backend."""

    random_seed: int
    n_agents: int = 1_000
    start_date: str = "2032-04-01"
    horizon_days: int = 30
    timestep_minutes: int = DAY_MINUTES
    n_contacts: int = 8
    beta: float = 0.05
    initial_prevalence: float = 0.02
    infectious_days: float = 7.0
    fatality_probability: float = 0.0
    scheduled_exogenous_exposures: tuple[ScheduledExogenousExposure, ...] = ()
    contact_topology: ClusteredStaticTopology | None = None
    fixed_initial_infections: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.random_seed, int) or self.random_seed < 0:
            raise ValueError("random_seed must be a non-negative integer")
        if not isinstance(self.n_agents, int) or self.n_agents < 2:
            raise ValueError("n_agents must be an integer of at least 2")
        try:
            date.fromisoformat(self.start_date)
        except (TypeError, ValueError) as exc:
            raise ValueError("start_date must be an ISO-8601 calendar date") from exc
        if not isinstance(self.horizon_days, int) or self.horizon_days < 1:
            raise ValueError("horizon_days must be a positive integer")
        if (
            not isinstance(self.timestep_minutes, int)
            or self.timestep_minutes < 1
            or DAY_MINUTES % self.timestep_minutes
        ):
            raise ValueError(
                "timestep_minutes must be a positive divisor of one day"
            )
        if not isinstance(self.n_contacts, int) or self.n_contacts < 1:
            raise ValueError("n_contacts must be a positive integer")
        if not math.isfinite(self.beta) or not 0.0 <= self.beta <= 1.0:
            raise ValueError("beta must be finite and between 0 and 1")
        if (
            not math.isfinite(self.initial_prevalence)
            or not 0.0 <= self.initial_prevalence <= 1.0
        ):
            raise ValueError(
                "initial_prevalence must be finite and between 0 and 1"
            )
        if not math.isfinite(self.infectious_days) or self.infectious_days <= 0:
            raise ValueError("infectious_days must be finite and positive")
        if (
            not math.isfinite(self.fatality_probability)
            or not 0.0 <= self.fatality_probability <= 1.0
        ):
            raise ValueError(
                "fatality_probability must be finite and between 0 and 1"
            )
        if self.fatality_probability != 0.0:
            raise ValueError(
                "the detached Starsim SIR adapter does not yet support deaths"
            )
        if self.contact_topology is not None:
            if not isinstance(self.contact_topology, ClusteredStaticTopology):
                raise ValueError(
                    "contact_topology must be a ClusteredStaticTopology or None"
                )
            cluster_size = self.contact_topology.cluster_size
            if self.n_agents % cluster_size:
                raise ValueError("cluster_size must divide n_agents exactly")
            cluster_count = self.n_agents // cluster_size
            if (
                self.contact_topology.cross_cluster_edges_per_cluster > 0
                and cluster_count < 2
            ):
                raise ValueError(
                    "cross-cluster edges require at least two clusters"
                )
        if self.fixed_initial_infections is not None:
            if (
                type(self.fixed_initial_infections) is not int
                or not 1 <= self.fixed_initial_infections <= self.n_agents
            ):
                raise ValueError(
                    "fixed_initial_infections must be an integer within the population"
                )
            expected_prevalence = self.fixed_initial_infections / self.n_agents
            if not math.isclose(
                self.initial_prevalence,
                expected_prevalence,
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise ValueError(
                    "fixed_initial_infections must equal initial_prevalence times "
                    "n_agents"
                )
        if not isinstance(self.scheduled_exogenous_exposures, tuple):
            raise ValueError(
                "scheduled_exogenous_exposures must be an immutable tuple"
            )

        seen_candidates: set[tuple[str, int, int]] = set()
        for candidate in self.scheduled_exogenous_exposures:
            if not isinstance(candidate, ScheduledExogenousExposure):
                raise ValueError(
                    "scheduled_exogenous_exposures must contain only "
                    "ScheduledExogenousExposure values"
                )
            if (
                not isinstance(candidate.mechanism, str)
                or candidate.mechanism not in EXOGENOUS_MECHANISMS
            ):
                raise ValueError(
                    "scheduled exposure mechanism must be 'common_source' "
                    "or 'importation'"
                )
            if (
                not isinstance(candidate.target_agent_id, int)
                or isinstance(candidate.target_agent_id, bool)
                or not 0 <= candidate.target_agent_id < self.n_agents
            ):
                raise ValueError(
                    "scheduled exposure target_agent_id is outside the population"
                )
            if (
                not isinstance(candidate.exposure_minute, int)
                or isinstance(candidate.exposure_minute, bool)
                or candidate.exposure_minute % self.timestep_minutes
            ):
                raise ValueError(
                    "scheduled exposure minute must fall on a simulator "
                    "timestep boundary"
                )
            if not 0 <= candidate.exposure_minute <= self.horizon_days * DAY_MINUTES:
                raise ValueError(
                    "scheduled exposure minute is outside the configured horizon"
                )
            if (
                isinstance(candidate.threshold, bool)
                or not isinstance(candidate.threshold, (int, float))
                or not math.isfinite(candidate.threshold)
                or not 0.0 <= candidate.threshold < 1.0
            ):
                raise ValueError(
                    "scheduled exposure threshold must be finite and in [0, 1)"
                )

            candidate_key = (
                candidate.mechanism,
                candidate.target_agent_id,
                candidate.exposure_minute,
            )
            if candidate_key in seen_candidates:
                raise ValueError(
                    "scheduled exposure candidates must be unique by mechanism, "
                    "target, and minute"
                )
            seen_candidates.add(candidate_key)

        # A target cannot acquire two different external provenances on one
        # timestep.  Rejecting this ambiguity lets the detached oracle label
        # every external event exactly, without peeking into disease internals.
        target_times = [
            (candidate.target_agent_id, candidate.exposure_minute)
            for candidate in self.scheduled_exogenous_exposures
        ]
        if len(target_times) != len(set(target_times)):
            raise ValueError(
                "a target may have at most one scheduled external mechanism "
                "per timestep"
            )


def _make_scheduled_exogenous_route(
    ss: Any,
    mechanism: str,
    candidates: tuple[ScheduledExogenousExposure, ...],
    timestep_minutes: int,
) -> Any:
    """Create an official Starsim Route without importing Starsim publicly."""

    by_step: dict[int, tuple[ScheduledExogenousExposure, ...]] = {}
    for candidate in candidates:
        step = candidate.exposure_minute // timestep_minutes
        by_step[step] = (*by_step.get(step, ()), candidate)

    class ScheduledExogenousRoute(ss.Route):
        """A CRN-safe external route backed by precommitted candidates."""

        def __init__(self) -> None:
            super().__init__(name=mechanism, label=mechanism.replace("_", " "))
            self.absolute_level = 1.0
            self.candidates_by_step = by_step
            self.emitted_mechanisms: dict[tuple[int, int], str] = {}

        def compute_transmission(
            self,
            rel_sus: Any,
            rel_trans: Any,
            disease_beta: Any,
            disease: Any = None,
        ) -> Any:
            # `disease_beta` and `rel_trans` intentionally do not participate:
            # contact transmissibility must not change external exposure risk.
            del rel_trans, disease_beta
            if disease is None:
                raise EngineError("scheduled exogenous route requires a disease")

            step = int(disease.ti)
            selected: list[int] = []
            for candidate in self.candidates_by_step.get(step, ()):
                uid = candidate.target_agent_id
                susceptibility = float(rel_sus.raw[uid])
                if (
                    susceptibility > 0.0
                    and candidate.threshold
                    < self.absolute_level * susceptibility
                ):
                    selected.append(uid)
                    self.emitted_mechanisms[(step, uid)] = mechanism
            return ss.uids(selected)

        def step(self) -> None:
            # Transmission is invoked by Infection.infect(); Route is also a
            # loop module, so an explicit no-op prevents Starsim from warning
            # that an ordinary network-update step was accidentally omitted.
            return None

    return ScheduledExogenousRoute()


def _load_starsim() -> Any:
    """Import the optional dependency only inside the trusted adapter."""

    os.environ.setdefault("STARSIM_INSTALL_FONTS", "0")
    try:
        import starsim as ss
    except ModuleNotFoundError as exc:
        if exc.name == "starsim":
            raise EngineError(
                "Starsim is optional and evaluator-only; install "
                f"'starsim=={SUPPORTED_STARSIM_VERSION}' in the trusted image"
            ) from exc
        raise

    version = getattr(ss, "__version__", "unknown")
    if version != SUPPORTED_STARSIM_VERSION:
        raise EngineError(
            "Unsupported Starsim version: expected "
            f"{SUPPORTED_STARSIM_VERSION}, found {version}"
        )
    return ss


def _private_topology_digest(
    random_seed: int,
    domain: str,
    *values: int,
) -> bytes:
    """Return a stable, domain-separated private topology draw."""

    hasher = hashlib.sha256()
    hasher.update(b"epiagentbench:clustered-static:v1\x00")
    for value in (random_seed, domain, *values):
        encoded = str(value).encode("ascii")
        hasher.update(len(encoded).to_bytes(4, "big"))
        hasher.update(encoded)
    return hasher.digest()


def _make_clustered_static_network(
    ss: Any,
    config: StarsimSIRConfig,
) -> Any:
    """Build one private deterministic Starsim StaticNet.

    Validation has already established equal clusters and an even within-
    cluster degree.  Hash-ranked membership permutations and bridges make the
    graph a pure function of the private simulator seed and configuration.
    """

    topology = config.contact_topology
    if topology is None:  # Defensive guard; callers select this path explicitly.
        raise EngineError("clustered-static topology was not configured")
    try:
        import networkx as nx
    except ModuleNotFoundError as exc:  # Starsim 3.5.1 normally supplies this.
        if exc.name == "networkx":
            raise EngineError(
                "clustered-static topology requires Starsim's networkx dependency"
            ) from exc
        raise

    cluster_size = topology.cluster_size
    degree = topology.within_cluster_degree
    cluster_count = config.n_agents // cluster_size
    graph = nx.Graph()
    graph.add_nodes_from(range(config.n_agents))

    # A regular ring lattice over a seed-private permutation gives every ward
    # exactly the requested degree without invoking a version-sensitive graph
    # generator or process-global random state.
    for cluster in range(cluster_count):
        first_uid = cluster * cluster_size
        members = list(range(first_uid, first_uid + cluster_size))
        members.sort(
            key=lambda uid: _private_topology_digest(
                config.random_seed,
                "cluster-member-order",
                cluster_size,
                degree,
                cluster,
                uid,
            )
        )
        for index, source in enumerate(members):
            for offset in range(1, degree // 2 + 1):
                target = members[(index + offset) % cluster_size]
                graph.add_edge(min(source, target), max(source, target))

    possible_pairs = [
        (left, right)
        for left in range(cluster_count)
        for right in range(left + 1, cluster_count)
    ]
    possible_pairs.sort(
        key=lambda pair: _private_topology_digest(
            config.random_seed,
            "cross-cluster-pair",
            cluster_size,
            degree,
            pair[0],
            pair[1],
        )
    )
    bridge_count = int(
        math.floor(
            cluster_count * topology.cross_cluster_edges_per_cluster + 0.5
        )
    )
    for left, right in possible_pairs[:bridge_count]:
        left_draw = _private_topology_digest(
            config.random_seed,
            "cross-cluster-left-endpoint",
            cluster_size,
            degree,
            left,
            right,
        )
        right_draw = _private_topology_digest(
            config.random_seed,
            "cross-cluster-right-endpoint",
            cluster_size,
            degree,
            left,
            right,
        )
        source = left * cluster_size + int.from_bytes(left_draw[:8], "big") % cluster_size
        target = (
            right * cluster_size
            + int.from_bytes(right_draw[:8], "big") % cluster_size
        )
        graph.add_edge(source, target)

    return ss.StaticNet(graph=graph)


def _fixed_initial_uids(config: StarsimSIRConfig) -> tuple[int, ...]:
    """Choose an exact initial count without exposing or redrawing it."""

    count = config.fixed_initial_infections
    if count is None:
        return ()
    ranked = sorted(
        range(config.n_agents),
        key=lambda uid: _private_topology_digest(
            config.random_seed,
            "fixed-initial-infection",
            uid,
        ),
    )
    return tuple(sorted(ranked[:count]))


class StarsimDiseaseEngine:
    """Trusted Starsim SIR adapter with fixed-step deterministic execution."""

    def __init__(self, config: StarsimSIRConfig):
        ss = _load_starsim()
        self._config = config
        self._horizon_minutes = config.horizon_days * DAY_MINUTES
        self._timestep_minutes = config.timestep_minutes
        self._current_minute = 0
        self._terminal = False
        self._closed = False
        self._pending_controls: list[EngineControl] = []
        self._known_control_ids: set[str] = set()
        self._applied_control_ids: list[str] = []
        self._exogenous_levels = {
            COMMON_SOURCE: 1.0,
            IMPORTATION: 1.0,
        }

        config_json = json.dumps(
            asdict(config), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        self._private_metadata = PrivateEngineMetadata(
            backend_name="starsim_sir",
            backend_version=ss.__version__,
            timestep_minutes=config.timestep_minutes,
            configuration_sha256=hashlib.sha256(config_json).hexdigest(),
        )

        candidates_by_mechanism = {
            mechanism: tuple(
                candidate
                for candidate in config.scheduled_exogenous_exposures
                if candidate.mechanism == mechanism
            )
            for mechanism in EXOGENOUS_MECHANISMS
        }
        # External routes come before the contact network.  Starsim preserves
        # the first route when two routes propose the same target on one step;
        # the ordering therefore makes an emitted external provenance exact.
        # With the default empty schedule, no custom route is added at all, so
        # the historical adapter configuration and trajectory are unchanged.
        exogenous_routes = [
            _make_scheduled_exogenous_route(
                ss,
                mechanism,
                candidates_by_mechanism[mechanism],
                config.timestep_minutes,
            )
            for mechanism in (COMMON_SOURCE, IMPORTATION)
            if candidates_by_mechanism[mechanism]
        ]
        if config.contact_topology is None:
            # This is deliberately the historical default.  Keeping the same
            # module type, parameters, and position preserves existing
            # RandomSafeNet trajectories byte-for-byte.
            contact_network = ss.RandomSafeNet(
                n_edges=max(1, config.n_contacts // 2)
            )
        else:
            contact_network = _make_clustered_static_network(ss, config)
        networks = [*exogenous_routes, contact_network]

        self._sim = ss.Sim(
            n_agents=config.n_agents,
            # A relative time axis is exact at sub-day timesteps.  Calendar
            # strings in Starsim 3.5.1 can accumulate fractional-day drift.
            # The public observation adapter maps logical minutes to ISO dates.
            start=ss.days(0),
            dur=ss.days(config.horizon_days),
            dt=ss.days(config.timestep_minutes / DAY_MINUTES),
            rand_seed=config.random_seed,
            verbose=0,
            networks=networks,
            diseases=ss.SIR(
                # A bare float inherits SIR's default per-year unit.  The GI
                # profile specifies a daily transmission hazard explicitly.
                beta=ss.perday(config.beta),
                init_prev=(
                    config.initial_prevalence
                    if config.fixed_initial_infections is None
                    else 0.0
                ),
                dur_inf=ss.days(config.infectious_days),
                p_death=config.fatality_probability,
            ),
            analyzers=ss.infection_log(),
        )
        self._sim.init()
        if config.fixed_initial_infections is not None:
            disease = self._sim.get_module("sir")
            initial_uids = ss.uids(_fixed_initial_uids(config))
            disease.set_prognoses(initial_uids, sources=-1)
            disease.pars._n_initial_cases = len(initial_uids)
        self._exogenous_routes = {
            mechanism: self._sim.get_module(mechanism)
            for mechanism in EXOGENOUS_MECHANISMS
            if candidates_by_mechanism[mechanism]
        }

    @property
    def current_minute(self) -> int:
        return self._current_minute

    @property
    def terminal(self) -> bool:
        return self._terminal

    @property
    def private_metadata(self) -> PrivateEngineMetadata:
        return self._private_metadata

    def apply_control(self, control: EngineControl) -> None:
        """Schedule one allow-listed contact or external-route control.

        ``GLOBAL_TRANSMISSION_MULTIPLIER`` preserves the original cumulative
        behavior.  ``GLOBAL_TRANSMISSION_LEVEL`` instead replaces the current
        relative-transmission value, making repeated settings idempotent and
        allowing a later value of 1.0 to restore the uncontrolled baseline.
        Both historical global kinds are aliases for contact transmission.

        ``CONTACT_TRANSMISSION_LEVEL``, ``COMMON_SOURCE_EXPOSURE_LEVEL``, and
        ``IMPORTATION_EXPOSURE_LEVEL`` are absolute, idempotent route levels.
        External levels gate only future precommitted candidates and never
        change contact beta or the other external mechanism.

        This is an integration hook, not a calibrated public-health action
        model.  All controls remain population-wide and evaluator-private.
        """

        self._ensure_open()
        if self._terminal:
            raise EngineError("cannot schedule a control after the horizon")
        if not control.control_id or control.control_id.isspace():
            raise ValueError("control_id must be non-empty")
        if control.control_id in self._known_control_ids:
            raise ValueError("control_id must be unique within an engine run")
        if control.kind not in {
            CONTACT_TRANSMISSION_LEVEL,
            COMMON_SOURCE_EXPOSURE_LEVEL,
            GLOBAL_TRANSMISSION_LEVEL,
            GLOBAL_TRANSMISSION_MULTIPLIER,
            IMPORTATION_EXPOSURE_LEVEL,
        }:
            raise UnsupportedControlError(
                f"unsupported Starsim SIR control kind: {control.kind!r}"
            )
        if control.target_id is not None:
            raise UnsupportedControlError(
                "the reference Starsim SIR controls are global and have no target"
            )
        if (
            not isinstance(control.effective_minute, int)
            or control.effective_minute % self._timestep_minutes
        ):
            raise ValueError(
                "effective_minute must fall on a simulator timestep boundary"
            )
        if not (
            self._current_minute
            <= control.effective_minute
            <= self._horizon_minutes
        ):
            raise ValueError("effective_minute is outside the remaining horizon")
        if (
            not math.isfinite(control.magnitude)
            or not 0.0 <= control.magnitude <= 1.0
        ):
            raise ValueError("control magnitude must be finite and between 0 and 1")

        self._known_control_ids.add(control.control_id)
        self._pending_controls.append(control)
        self._pending_controls.sort(
            key=lambda item: (item.effective_minute, item.control_id)
        )

    def advance_to(self, target_minute: int) -> EngineDelta:
        """Advance to a monotonic simulator-timestep boundary.

        Starsim timelines include both their start and stop endpoints.  Each
        partial ``run(until=sim.now)`` processes the current endpoint.  When the
        logical horizon is reached, one final partial run processes the stop
        endpoint and causes Starsim to finalize without moving logical time
        beyond the configured horizon.
        """

        self._ensure_open()
        if not isinstance(target_minute, int):
            raise TypeError("target_minute must be an integer")
        if target_minute % self._timestep_minutes:
            raise ValueError(
                "target_minute must fall on a simulator timestep boundary"
            )
        if target_minute < self._current_minute:
            raise ValueError("the disease engine cannot move backward in time")
        if target_minute > self._horizon_minutes:
            raise ValueError("target_minute exceeds the configured horizon")

        start_minute = self._current_minute
        states: list[LatentState] = []
        applied: list[str] = []

        while self._current_minute < target_minute:
            applied.extend(self._activate_due_controls(self._current_minute))

            # run_one_step() is explicitly a debugging API in Starsim 3.5.1
            # and does not finalize/mark complete at the horizon.  The main run
            # API supports resumable partial execution and is used instead.
            self._sim.run(until=self._sim.now, verbose=0)
            self._current_minute += self._timestep_minutes

            if self._current_minute == self._horizon_minutes:
                applied.extend(
                    self._activate_due_controls(self._current_minute)
                )
                self._sim.run(until=self._sim.now, verbose=0)
                if not self._sim.complete:
                    raise EngineError(
                        "Starsim did not finalize at the configured horizon"
                    )
                self._terminal = True

            states.append(self._latent_state())

        return EngineDelta(
            start_minute=start_minute,
            end_minute=self._current_minute,
            states=tuple(states),
            applied_control_ids=tuple(applied),
            terminal=self._terminal,
        )

    def oracle_snapshot(self) -> OracleSnapshot:
        self._ensure_open()
        disease = self._sim.get_module("sir")
        alive_ids = self._uids(self._sim.people.alive)
        infected_ids = self._uids(disease.infected)
        recovered_ids = self._uids(disease.recovered)
        dead_ids = self._uids(self._sim.people.dead)
        ever_infected_ids = tuple(
            int(uid)
            for uid, infection_time in zip(
                self._sim.people.uid, disease.ti_infected.values, strict=True
            )
            if math.isfinite(float(infection_time))
        )
        return OracleSnapshot(
            minute=self._current_minute,
            terminal=self._terminal,
            population_size=len(self._sim.people),
            alive_agent_ids=alive_ids,
            ever_infected_agent_ids=ever_infected_ids,
            currently_infected_agent_ids=infected_ids,
            recovered_agent_ids=recovered_ids,
            dead_agent_ids=dead_ids,
            applied_control_ids=tuple(self._applied_control_ids),
            transmission_events=self._transmission_events(disease),
        )

    def close(self) -> None:
        if self._closed:
            return
        self._pending_controls.clear()
        self._exogenous_routes.clear()
        self._sim = None
        self._closed = True

    def _activate_due_controls(self, minute: int) -> tuple[str, ...]:
        due = [
            control
            for control in self._pending_controls
            if control.effective_minute <= minute
        ]
        if not due:
            return ()

        disease = self._sim.get_module("sir")
        for control in due:
            if control.kind == GLOBAL_TRANSMISSION_MULTIPLIER:
                disease.rel_trans[:] *= control.magnitude
            elif control.kind in {
                CONTACT_TRANSMISSION_LEVEL,
                GLOBAL_TRANSMISSION_LEVEL,
            }:
                disease.rel_trans[:] = control.magnitude
            elif control.kind == COMMON_SOURCE_EXPOSURE_LEVEL:
                self._set_exogenous_level(COMMON_SOURCE, control.magnitude)
            elif control.kind == IMPORTATION_EXPOSURE_LEVEL:
                self._set_exogenous_level(IMPORTATION, control.magnitude)
            else:  # Defensive fail-closed guard for corrupted pending state.
                raise UnsupportedControlError(
                    f"unsupported Starsim SIR control kind: {control.kind!r}"
                )
            self._applied_control_ids.append(control.control_id)
            self._pending_controls.remove(control)
        return tuple(control.control_id for control in due)

    def _set_exogenous_level(self, mechanism: str, magnitude: float) -> None:
        self._exogenous_levels[mechanism] = magnitude
        route = self._exogenous_routes.get(mechanism)
        if route is not None:
            route.absolute_level = magnitude

    def _latent_state(self) -> LatentState:
        disease = self._sim.get_module("sir")
        return LatentState(
            minute=self._current_minute,
            population_size=len(self._sim.people),
            alive_count=int(self._sim.people.alive.sum()),
            susceptible_count=int(disease.susceptible.sum()),
            infected_count=int(disease.infected.sum()),
            recovered_count=int(disease.recovered.sum()),
            dead_count=int(self._sim.people.dead.sum()),
        )

    @staticmethod
    def _uids(state: Any) -> tuple[int, ...]:
        return tuple(int(uid) for uid in state.uids)

    def _transmission_events(self, disease: Any) -> tuple[TransmissionEvent, ...]:
        """Detach infection timing and ancestry from Starsim-owned objects."""

        source_by_target: dict[int, int | None] = {}
        infection_log = disease.infection_log
        if infection_log is None:
            for analyzer in self._sim.analyzers.values():
                logs = getattr(analyzer, "logs", None)
                if logs is not None and "sir" in logs:
                    infection_log = logs["sir"]
                    break
        if infection_log is not None:
            for source, target, _ in infection_log.edges(keys=True):
                try:
                    source_value = int(source)
                except (TypeError, ValueError, OverflowError):
                    source_value = -1
                source_by_target[int(target)] = (
                    source_value if source_value >= 0 else None
                )

        external_mechanism_by_event: dict[tuple[int, int], str] = {}
        for route in self._exogenous_routes.values():
            for (step, uid), mechanism in route.emitted_mechanisms.items():
                external_mechanism_by_event[
                    (step * self._timestep_minutes, uid)
                ] = mechanism

        # ``values`` follows active UIDs and can omit people who died.  The raw
        # state is indexed by stable Starsim UID and preserves ever-infected
        # history.  This adapter currently has no births, so population size is
        # the used length.
        raw_times = disease.ti_infected.raw[: len(self._sim.people)]
        events: list[TransmissionEvent] = []
        for uid, infection_time in enumerate(raw_times):
            if not math.isfinite(float(infection_time)):
                continue
            infection_minute = int(
                round(float(infection_time) * self._timestep_minutes)
            )
            source_agent_id = source_by_target.get(uid)
            if source_agent_id is not None:
                mechanism = "person_to_person"
            else:
                mechanism = external_mechanism_by_event.get(
                    (infection_minute, uid),
                    "seed",
                )
            events.append(
                TransmissionEvent(
                    target_agent_id=uid,
                    source_agent_id=source_agent_id,
                    infection_minute=infection_minute,
                    mechanism=mechanism,
                )
            )
        return tuple(
            sorted(
                events,
                key=lambda event: (
                    event.infection_minute,
                    event.target_agent_id,
                ),
            )
        )

    def _ensure_open(self) -> None:
        if self._closed:
            raise EngineClosedError("the disease engine is closed")
