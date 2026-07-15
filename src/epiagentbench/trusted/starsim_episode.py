"""Evaluator-only Starsim-to-surveillance episode backend.

The static benchmark remains an experimental person-to-person development
slice.  Its first NORS candidate failed visible validation and is not calibrated.
The live benchmark additionally uses evaluator-owned Starsim routes for shared
sources and outside introductions, plus a surveillance-layer artifact mode.
None of those experimental route parameters are claimed as fitted effects.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import hmac
import random
from typing import Any, Mapping

from ..models import EpisodeBundle, PublicEpisode
from .engine import EngineControl, TransmissionEvent
from .starsim_engine import (
    CLUSTERED_STATIC_TOPOLOGY_VERSION,
    COMMON_SOURCE,
    ClusteredStaticTopology,
    GLOBAL_TRANSMISSION_MULTIPLIER,
    IMPORTATION,
    ScheduledExogenousExposure,
    StarsimDiseaseEngine,
    StarsimSIRConfig,
)
from .live_starsim_runtime import ClosedLoopStarsimRuntime
from .surveillance import (
    DAY_MINUTES,
    LIVE_PROFILE_RESOURCE,
    ScoredSurveillanceEpisode,
    build_institution_surveillance_episode,
    derive_private_seed,
    load_gi_surveillance_profile,
)


SUPPORTED_FAMILY = "institution_person_to_person"
LIVE_FAMILY_TO_MODE: Mapping[str, str] = {
    "institution_person_to_person": "person_to_person",
    "restaurant_point_source": "common_source",
    "repeated_introduction": "repeated_introduction",
    "coincidental_venue": "background",
    "reporting_artifact": "reporting_artifact",
}
_PRIVATE_TOPOLOGY_KEYS = frozenset(
    {
        "construction_version",
        "cluster_size",
        "within_cluster_degree",
        "cross_cluster_edges_per_cluster",
    }
)
_PRIVATE_INITIAL_COUNT_MODES = frozenset(
    {"default", *LIVE_FAMILY_TO_MODE.values()}
)


def _private_contact_topology(
    transmission: Mapping[str, Any],
) -> ClusteredStaticTopology | None:
    """Parse an explicit evaluator-only candidate topology."""

    raw = transmission.get("private_contact_topology")
    if raw is None:
        return None
    if not isinstance(raw, Mapping) or set(raw) != _PRIVATE_TOPOLOGY_KEYS:
        raise ValueError(
            "private_contact_topology must contain exactly the clustered-static fields"
        )
    if raw.get("construction_version") != CLUSTERED_STATIC_TOPOLOGY_VERSION:
        raise ValueError("unsupported private contact topology version")
    return ClusteredStaticTopology(
        construction_version=str(raw["construction_version"]),
        cluster_size=raw["cluster_size"],
        within_cluster_degree=raw["within_cluster_degree"],
        cross_cluster_edges_per_cluster=raw[
            "cross_cluster_edges_per_cluster"
        ],
    )


def _private_fixed_initial_infections(
    transmission: Mapping[str, Any],
    causal_mode: str | None,
) -> int | None:
    """Select an optional exact initial count for one private causal mode."""

    raw = transmission.get("private_fixed_initial_infections")
    if raw is None:
        return None
    if (
        not isinstance(raw, Mapping)
        or any(type(key) is not str for key in raw)
        or not set(raw) <= _PRIVATE_INITIAL_COUNT_MODES
        or any(type(value) is not int or value < 1 for value in raw.values())
    ):
        raise ValueError(
            "private_fixed_initial_infections must map supported modes to "
            "positive integer counts"
        )
    if causal_mode is not None and causal_mode in raw:
        return raw[causal_mode]
    return raw.get("default")
LIVE_FAMILIES = tuple(LIVE_FAMILY_TO_MODE)
MODE_TO_LIVE_FAMILY = {
    mode: family for family, mode in LIVE_FAMILY_TO_MODE.items()
}
CONTROL_DECISION_MINUTES = (0, 12 * 60, 36 * 60)
MAX_GENERATION_ATTEMPTS = 64
LIVE_ALERT_ADMISSION_RULE_ID = "public_opening_count_strata_v2"
# These overlapping, six-count-wide bands are an admission-balance device, not
# latent labels. A band is chosen independently of mode and growth. Candidates
# must place both the alert numerator and the distinct public patient count in
# the same band, so complete same-seed groups satisfy the declared count
# caliper by construction. No future or request-only record is inspected.
LIVE_ALERT_COUNT_BANDS: Mapping[str, tuple[int, int]] = {
    "low": (6, 12),
    "middle": (8, 14),
    "high": (10, 16),
}
LIVE_ALERT_COUNT_STRATA = ("low", "middle", "high")


def _keyed_private_seed(
    key: bytes,
    seed: int,
    domain: str,
    attempt: int = 0,
) -> int:
    """Derive an evaluator-private stream that sequential seeds cannot reveal."""

    if (
        not isinstance(key, bytes)
        or len(key) < 16
        or type(seed) is not int
        or seed < 0
        or not domain
        or type(attempt) is not int
        or attempt < 0
    ):
        raise ValueError("Invalid keyed private seed derivation")
    digest = hmac.new(
        key,
        (
            f"epiagentbench:closed-loop:v1:{seed}:{domain}:{attempt}"
        ).encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return int.from_bytes(digest[:8], "big") % (2**31 - 1)


def _live_alert_count_stratum(
    key: bytes,
    seed: int,
) -> str:
    """Choose a public-covariate admission stratum independently of growth."""

    return LIVE_ALERT_COUNT_STRATA[
        _keyed_private_seed(key, seed, "closed-loop-alert-count-stratum")
        % len(LIVE_ALERT_COUNT_STRATA)
    ]


def _public_alert_admissible(
    public_episode: PublicEpisode,
    alert_count_stratum: str | None = None,
) -> bool:
    """Apply the live admission rule using only the minute-zero transcript."""

    initial_alert_ids = public_episode.manifest.get("initial_alert_ids")
    if not isinstance(initial_alert_ids, list) or len(initial_alert_ids) != 1:
        return False
    alert_id = initial_alert_ids[0]
    if not isinstance(alert_id, str):
        return False
    matches = [
        observation
        for observation in public_episode.observations
        if observation.observation_id == alert_id
        and observation.kind == "alert"
        and observation.release_key == "initial"
        and observation.available_minute <= 0
    ]
    if len(matches) != 1:
        return False
    observed_count = matches[0].payload.get("observed_count")
    if type(observed_count) is not int:
        return False
    if alert_count_stratum is None:
        lower, upper = (4, 30)
    else:
        bounds = LIVE_ALERT_COUNT_BANDS.get(alert_count_stratum)
        if bounds is None:
            raise ValueError("Unknown live alert-count stratum")
        lower, upper = bounds
    return lower <= observed_count <= upper


def _public_opening_admissible(
    public_episode: PublicEpisode,
    alert_count_stratum: str,
) -> bool:
    """Match two opening public counts without reading hidden or future state."""

    if not _public_alert_admissible(public_episode, alert_count_stratum):
        return False
    lower, upper = LIVE_ALERT_COUNT_BANDS[alert_count_stratum]
    public_patient_ids = {
        observation.payload.get("patient_id")
        for observation in public_episode.observations
        if observation.available_minute <= 0
        and observation.release_key in {"initial", "stream"}
        and isinstance(observation.payload.get("patient_id"), str)
    }
    return lower <= len(public_patient_ids) <= upper


@dataclass(frozen=True, slots=True)
class _LatentRun:
    events: tuple[TransmissionEvent, ...]
    population_size: int
    terminal_minute: int


class StarsimSurveillanceBackend:
    """Build a causally linked, outcome-scored Starsim investigation episode."""

    def __init__(self, profile: Mapping[str, Any] | None = None):
        if profile is None:
            self._profile = dict(load_gi_surveillance_profile())
            self._live_profile = dict(
                load_gi_surveillance_profile(LIVE_PROFILE_RESOURCE)
            )
        else:
            # Supplying a profile is an explicit reproducibility override for
            # both creation paths. Legacy v1 profiles retain the original live
            # person-to-person configuration through the compatibility branch.
            self._profile = dict(profile)
            self._live_profile = dict(profile)

    @property
    def live_profile_id(self) -> str:
        """Private reproducibility label used by evaluator diagnostics."""

        return str(self._live_profile["profile_id"])

    def create_runtime(
        self,
        *,
        seed: int,
        family: str | None,
        presentation_key: bytes | None = None,
    ) -> ClosedLoopStarsimRuntime:
        """Create a retained, action-dependent runtime for secure evaluation.

        Selection requires the observable opening alert and public-patient
        counts to fall in an independently keyed public-covariate band. It
        does not condition on future outbreak size or any intervention winning.
        """

        if type(seed) is not int or seed < 0:
            raise ValueError("seed must be a non-negative integer")
        if presentation_key is None:
            presentation_key = hashlib.sha256(
                f"epiagentbench-development-live-presentation:{seed}".encode(
                    "ascii"
                )
            ).digest()

        selected_family, causal_mode = self._select_live_mode(
            seed=seed,
            family=family,
            presentation_key=presentation_key,
        )

        closed_loop = self._live_profile["closed_loop_configuration"]
        regimes = closed_loop[
            "growth_regime_multipliers"
        ]
        regime_names = tuple(sorted(regimes))
        regime = regime_names[
            _keyed_private_seed(
                presentation_key, seed, "closed-loop-growth-regime"
            )
            % len(regime_names)
        ]
        multiplier = float(regimes[regime])
        alert_count_stratum = _live_alert_count_stratum(
            presentation_key, seed
        )
        future_artifacts = self._future_artifact_candidates(
            seed=seed,
            presentation_key=presentation_key,
            causal_mode=causal_mode,
        )
        for attempt in range(MAX_GENERATION_ATTEMPTS):
            # Background ascertainment and other opening observation draws
            # must vary across bounded retries; otherwise no-infection modes
            # would repeat the identical inadmissible alert 64 times. The
            # retry is still admitted solely on its public minute-zero count.
            observation_seed = _keyed_private_seed(
                presentation_key,
                seed,
                "closed-loop-observations",
                attempt,
            )
            initial_artifacts = self._artifact_count(
                seed=seed,
                presentation_key=presentation_key,
                causal_mode=causal_mode,
                field="initial_duplicate_reports",
                attempt=attempt,
            )
            simulator_seed = _keyed_private_seed(
                presentation_key, seed, "starsim-live", attempt
            )
            exposures = self._scheduled_exposures(
                seed=seed,
                attempt=attempt,
                presentation_key=presentation_key,
                causal_mode=causal_mode,
            )
            runtime = ClosedLoopStarsimRuntime(
                seed=observation_seed,
                presentation_key=presentation_key,
                profile=self._live_profile,
                config=self._config(
                    simulator_seed,
                    beta_multiplier=multiplier,
                    profile=self._live_profile,
                    causal_mode=causal_mode,
                    scheduled_exposures=exposures,
                ),
                growth_regime=regime,
                causal_mode=causal_mode,
                family=selected_family,
                initial_artifact_duplicates=initial_artifacts,
                future_artifact_candidates=future_artifacts,
            )
            # Admission may inspect only the exact records available to the
            # agent at minute zero. Hidden infections, later encounters,
            # request-only evidence, and intervention outcomes must not
            # influence which episode is admitted.
            if _public_opening_admissible(
                runtime.public_episode, alert_count_stratum
            ):
                return runtime
            runtime.close()

        raise RuntimeError(
            "No observable experimental closed-loop alert in the selected "
            "public count stratum was generated within the bounded attempt budget"
        )

    def _select_live_mode(
        self,
        *,
        seed: int,
        family: str | None,
        presentation_key: bytes,
    ) -> tuple[str, str]:
        """Select a mode on a private stream independent of admission strata."""

        configured_modes = self._live_profile["closed_loop_configuration"].get(
            "causal_modes"
        )
        if not isinstance(configured_modes, Mapping):
            # Compatibility for explicitly supplied v1 profiles.
            selected = family or SUPPORTED_FAMILY
            if selected != SUPPORTED_FAMILY:
                raise ValueError(
                    "This legacy Starsim profile supports only "
                    f"{SUPPORTED_FAMILY!r}"
                )
            return selected, "person_to_person"

        if family is None:
            causal_modes = tuple(
                mode
                for mode in MODE_TO_LIVE_FAMILY
                if mode in configured_modes
            )
            if not causal_modes:
                raise ValueError("The live profile defines no supported causal modes")
            causal_mode = causal_modes[
                _keyed_private_seed(
                    presentation_key, seed, "closed-loop-causal-mode"
                )
                % len(causal_modes)
            ]
            return MODE_TO_LIVE_FAMILY[causal_mode], causal_mode

        causal_mode = LIVE_FAMILY_TO_MODE.get(family)
        if causal_mode is None or causal_mode not in configured_modes:
            raise ValueError(
                "Unsupported live Starsim family; expected one of "
                f"{LIVE_FAMILIES!r}"
            )
        return family, causal_mode

    def _artifact_count(
        self,
        *,
        seed: int,
        presentation_key: bytes,
        causal_mode: str,
        field: str,
        attempt: int = 0,
    ) -> int:
        modes = self._live_profile["closed_loop_configuration"].get(
            "causal_modes", {}
        )
        values = modes.get(causal_mode, {}).get(field, [0, 0])
        if (
            not isinstance(values, list)
            or len(values) != 2
            or any(type(value) is not int or value < 0 for value in values)
            or values[0] > values[1]
        ):
            raise ValueError(f"Invalid {field} range in live profile")
        rng = random.Random(
            _keyed_private_seed(
                presentation_key,
                seed,
                f"closed-loop-{field}",
                attempt,
            )
        )
        return rng.randint(values[0], values[1])

    def _future_artifact_candidates(
        self,
        *,
        seed: int,
        presentation_key: bytes,
        causal_mode: str,
    ) -> tuple[tuple[int, int], ...]:
        count = self._artifact_count(
            seed=seed,
            presentation_key=presentation_key,
            causal_mode=causal_mode,
            field="future_duplicate_reports",
        )
        if count == 0:
            return ()
        closed_loop = self._live_profile["closed_loop_configuration"]
        tick = int(closed_loop["implementation_cycle_minutes"])
        deadline = int(closed_loop["interaction_days"]) * DAY_MINUTES
        rng = random.Random(
            _keyed_private_seed(
                presentation_key, seed, "closed-loop-future-artifact-candidates"
            )
        )
        release_steps = range(2, max(3, deadline // tick + 1))
        candidates: set[tuple[int, int]] = set()
        while len(candidates) < count:
            candidates.add(
                (
                    rng.choice(release_steps) * tick,
                    rng.randrange(1_000_000),
                )
            )
        return tuple(sorted(candidates))

    def _scheduled_exposures(
        self,
        *,
        seed: int,
        attempt: int,
        presentation_key: bytes,
        causal_mode: str,
    ) -> tuple[ScheduledExogenousExposure, ...]:
        if causal_mode not in {"common_source", "repeated_introduction"}:
            return ()
        closed_loop = self._live_profile["closed_loop_configuration"]
        mode = closed_loop["causal_modes"][causal_mode]
        transmission = self._live_profile["transmission_configuration"]
        population = int(transmission["population_size"])
        tick = int(transmission["timestep_minutes"])
        decision = int(transmission["decision_day"]) * DAY_MINUTES
        horizon = int(transmission["horizon_days"]) * DAY_MINUTES
        interaction = int(closed_loop["interaction_days"]) * DAY_MINUTES
        pre_rng = random.Random(
            _keyed_private_seed(
                presentation_key,
                seed,
                f"closed-loop-{causal_mode}-predecision-exposures",
                attempt,
            )
        )
        # Future exposure pressure is precommitted on a stream that does not
        # include the bounded generation-attempt index. Retrying solely to meet
        # an opening public-count band therefore cannot silently redraw the
        # future source/importation challenge.
        future_rng = random.Random(
            _keyed_private_seed(
                presentation_key,
                seed,
                f"closed-loop-{causal_mode}-future-exposures",
            )
        )

        def draw_count(field: str, rng: random.Random) -> int:
            bounds = mode[field]
            if (
                not isinstance(bounds, list)
                or len(bounds) != 2
                or any(type(value) is not int or value < 0 for value in bounds)
                or bounds[0] > bounds[1]
            ):
                raise ValueError(f"Invalid {field} range in live profile")
            return rng.randint(bounds[0], bounds[1])

        pre_count = draw_count(
            "predecision_exposure_candidates", pre_rng
        )
        future_count = draw_count(
            "future_exposure_candidates", future_rng
        )
        total = pre_count + future_count
        if total > population:
            raise ValueError("Exogenous candidate count exceeds population")
        future_targets = future_rng.sample(range(population), future_count)
        future_target_set = set(future_targets)
        pre_targets = pre_rng.sample(
            [uid for uid in range(population) if uid not in future_target_set],
            pre_count,
        )
        mechanism = (
            COMMON_SOURCE
            if causal_mode == "common_source"
            else IMPORTATION
        )

        if causal_mode == "common_source":
            # One concealed meal/source wave before the alert; optional later
            # contaminated-source waves make source control consequential.
            pre_wave = decision - pre_rng.choice((8, 12, 16)) * tick
            future_waves = tuple(
                decision + offset * tick for offset in (2, 4, 8, 12, 16)
                if decision + offset * tick <= min(horizon, decision + interaction)
            )
            pre_minutes = (pre_wave,) * pre_count
            future_minutes = tuple(
                future_waves[index % len(future_waves)]
                for index in range(future_count)
            )
        else:
            pre_steps = tuple(
                range(
                    max(1, (decision - 7 * DAY_MINUTES) // tick),
                    decision // tick,
                )
            )
            future_steps = tuple(
                range(
                    decision // tick + 2,
                    min(horizon, decision + interaction) // tick + 1,
                )
            )
            pre_minutes = tuple(
                pre_rng.choice(pre_steps) * tick for _ in range(pre_count)
            )
            future_minutes = tuple(
                future_rng.choice(future_steps) * tick
                for _ in range(future_count)
            )

        pre_candidates = [
            ScheduledExogenousExposure(
                mechanism=mechanism,
                target_agent_id=target,
                exposure_minute=minute,
                threshold=pre_rng.random(),
            )
            for target, minute in zip(pre_targets, pre_minutes, strict=True)
        ]
        future_candidates = [
            ScheduledExogenousExposure(
                mechanism=mechanism,
                target_agent_id=target,
                exposure_minute=minute,
                threshold=future_rng.random(),
            )
            for target, minute in zip(
                future_targets, future_minutes, strict=True
            )
        ]
        return tuple(
            sorted(
                (*pre_candidates, *future_candidates),
                key=lambda item: (
                    item.exposure_minute,
                    item.target_agent_id,
                ),
            )
        )

    def create_episode(
        self,
        *,
        seed: int,
        family: str | None,
        presentation_key: bytes | None = None,
    ) -> EpisodeBundle:
        return self.create_scored_episode(
            seed=seed,
            family=family,
            presentation_key=presentation_key,
        ).bundle

    def create_scored_episode(
        self,
        *,
        seed: int,
        family: str | None = None,
        presentation_key: bytes | None = None,
    ) -> ScoredSurveillanceEpisode:
        if type(seed) is not int or seed < 0:
            raise ValueError("seed must be a non-negative integer")
        selected_family = family or SUPPORTED_FAMILY
        if selected_family != SUPPORTED_FAMILY:
            raise ValueError(
                "The experimental Starsim backend supports only "
                f"{SUPPORTED_FAMILY!r}"
            )
        if presentation_key is None:
            presentation_key = hashlib.sha256(
                f"epiagentbench-development-starsim-presentation:{seed}".encode(
                    "ascii"
                )
            ).digest()

        transmission = self._profile["transmission_configuration"]
        decision_minute = int(transmission["decision_day"]) * DAY_MINUTES
        horizon_minute = int(transmission["horizon_days"]) * DAY_MINUTES

        for attempt in range(MAX_GENERATION_ATTEMPTS):
            simulator_seed = derive_private_seed(seed, "starsim", attempt)
            config = self._config(simulator_seed)
            factual = self._run(config)
            if not self._benchmark_trace_gate(factual, decision_minute):
                continue

            # Observation acceptance is checked before paying for each
            # counterfactual branch.  The same observation RNG stream is reused
            # when the final action curves are attached.
            provisional = build_institution_surveillance_episode(
                seed=seed,
                transmission_events=factual.events,
                population_size=factual.population_size,
                episode_decision_minute=decision_minute,
                terminal_minute=factual.terminal_minute,
                counterfactual_infections={0: len(factual.events)},
                presentation_key=presentation_key,
                profile=self._profile,
            )
            if not self._observable_and_solvable(provisional):
                continue

            outcomes: dict[int, int] = {}
            for relative_minute in CONTROL_DECISION_MINUTES:
                effective_minute = decision_minute + relative_minute
                controlled = self._run(
                    config,
                    control=EngineControl(
                        control_id=f"institution_control_{relative_minute}",
                        kind=GLOBAL_TRANSMISSION_MULTIPLIER,
                        effective_minute=effective_minute,
                        magnitude=float(
                            self._profile["utility_profile"][
                                "transmission_multiplier"
                            ]
                        ),
                    ),
                )
                self._assert_counterfactual_prefix(
                    factual.events,
                    controlled.events,
                    effective_minute=effective_minute,
                )
                outcomes[relative_minute] = len(controlled.events)

            final = build_institution_surveillance_episode(
                seed=seed,
                transmission_events=factual.events,
                population_size=factual.population_size,
                episode_decision_minute=decision_minute,
                terminal_minute=factual.terminal_minute,
                counterfactual_infections=outcomes,
                presentation_key=presentation_key,
                profile=self._profile,
            )
            if not self._observable_and_solvable(final):
                raise AssertionError(
                    "Attaching counterfactuals changed observation generation"
                )
            return replace(
                final,
                diagnostics=replace(
                    final.diagnostics, generation_attempts=attempt + 1
                ),
            )

        raise RuntimeError(
            "No benchmark-accepted experimental Starsim episode was generated "
            "within the bounded attempt budget"
        )

    def _config(
        self,
        simulator_seed: int,
        *,
        beta_multiplier: float = 1.0,
        profile: Mapping[str, Any] | None = None,
        causal_mode: str | None = None,
        scheduled_exposures: tuple[ScheduledExogenousExposure, ...] = (),
    ) -> StarsimSIRConfig:
        selected_profile = self._profile if profile is None else profile
        values = selected_profile["transmission_configuration"]
        initial_prevalence = float(values["initial_prevalence"])
        mode_beta_multiplier = 1.0
        if causal_mode is not None:
            mode_values = selected_profile["closed_loop_configuration"].get(
                "causal_modes", {}
            ).get(causal_mode)
            if mode_values is not None:
                initial_prevalence = float(
                    mode_values["initial_prevalence"]
                )
                mode_beta_multiplier = float(
                    mode_values["contact_beta_multiplier"]
                )
        return StarsimSIRConfig(
            random_seed=simulator_seed,
            n_agents=int(values["population_size"]),
            horizon_days=int(values["horizon_days"]),
            timestep_minutes=int(values["timestep_minutes"]),
            n_contacts=int(values["mean_contacts"]),
            beta=float(values["daily_transmission_hazard"])
            * beta_multiplier
            * mode_beta_multiplier,
            initial_prevalence=initial_prevalence,
            infectious_days=float(values["infectious_days"]),
            fatality_probability=0.0,
            scheduled_exogenous_exposures=scheduled_exposures,
            contact_topology=_private_contact_topology(values),
            fixed_initial_infections=_private_fixed_initial_infections(
                values, causal_mode
            ),
        )

    @staticmethod
    def _run(
        config: StarsimSIRConfig,
        control: EngineControl | None = None,
    ) -> _LatentRun:
        engine = StarsimDiseaseEngine(config)
        try:
            if control is not None:
                engine.apply_control(control)
            engine.advance_to(config.horizon_days * DAY_MINUTES)
            snapshot = engine.oracle_snapshot()
            return _LatentRun(
                events=snapshot.transmission_events,
                population_size=snapshot.population_size,
                terminal_minute=snapshot.minute,
            )
        finally:
            engine.close()

    def _benchmark_trace_gate(
        self, run: _LatentRun, decision_minute: int
    ) -> bool:
        lower, upper = self._profile["transmission_configuration"][
            "experimental_latent_infection_bounds"
        ]
        lower = int(lower)
        upper = int(upper)
        before_decision = sum(
            event.infection_minute <= decision_minute for event in run.events
        )
        secondary = sum(event.source_agent_id is not None for event in run.events)
        return (
            lower <= len(run.events) <= upper
            and 8 <= before_decision <= 50
            and secondary >= 8
            and len(run.events) - before_decision >= 3
        )

    @staticmethod
    def _observable_and_solvable(episode: ScoredSurveillanceEpisode) -> bool:
        diagnostics = episode.diagnostics
        return (
            episode.bundle.oracle.is_outbreak
            and 10 <= diagnostics.public_suspects <= 40
            and 6 <= diagnostics.true_cases <= 30
            and diagnostics.initial_true_cases >= 4
            and diagnostics.initial_positive_labs >= 3
            and diagnostics.recalled_institution_exposures >= 3
            and 5 <= diagnostics.alert_count <= 30
        )

    @staticmethod
    def _assert_counterfactual_prefix(
        factual: tuple[TransmissionEvent, ...],
        controlled: tuple[TransmissionEvent, ...],
        *,
        effective_minute: int,
    ) -> None:
        factual_prefix = tuple(
            event for event in factual if event.infection_minute < effective_minute
        )
        controlled_prefix = tuple(
            event for event in controlled if event.infection_minute < effective_minute
        )
        if factual_prefix != controlled_prefix:
            raise RuntimeError(
                "Counterfactual branch diverged before its intervention"
            )
