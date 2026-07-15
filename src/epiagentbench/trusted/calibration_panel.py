"""Evaluator-only, gate-free Starsim calibration panels.

The benchmark episode generator deliberately admits only alerts that are useful
to investigate.  That admission rule must not be used for scientific
calibration because it conditions on the simulated outcome.  This module runs
exactly one Starsim world for each predeclared seed and measures the full
reported-outbreak estimand through the same surveillance observation model.

NORS contains outbreaks rather than all introductions, so comparisons condition
on at least two reported illnesses.  The unconditional inclusion fraction is
reported separately and is never treated as empirically identified by NORS.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
import hashlib
import itertools
import json
import math
from typing import Any, Mapping, Sequence

from ..calibration import CALIBRATION_PLAN_VERSION, compare_reported_outbreak_sizes
from .live_surveillance import DAY_MINUTES, IncrementalSurveillanceStream
from .starsim_episode import StarsimSurveillanceBackend, _keyed_private_seed
from .starsim_engine import (
    CLUSTERED_STATIC_TOPOLOGY_VERSION,
    ClusteredStaticTopology,
)
from .surveillance import LIVE_PROFILE_RESOURCE, load_gi_surveillance_profile


PANEL_VERSION = "starsim_nors_full_horizon_v1"
SUPPORTED_CALIBRATION_MODES = (
    "person_to_person",
    "common_source",
)
DEFAULT_CONTACT_HAZARD_MULTIPLIERS = (0.20, 0.30, 0.40, 0.50, 0.65, 0.80, 1.00)
DEFAULT_COMMON_SOURCE_EXPOSURE_MULTIPLIERS = (
    0.20,
    0.30,
    0.40,
    0.50,
    0.65,
    0.80,
    1.00,
)
DEFAULT_FOLLOWUP_DAYS = 14
MINIMUM_ELIGIBLE_FRACTION = 0.20
CLUSTERED_REFINEMENT_VERSION = "starsim_nors_clustered_refinement_v1"
CLUSTERED_VISIBLE_GATE_MAX_LOG_QUANTILE_ERROR = 0.35
CLUSTERED_FIXED_INITIAL_INFECTIONS = 3
DEFAULT_CLUSTER_SIZES = (40,)
DEFAULT_WITHIN_CLUSTER_DEGREES = (6,)
DEFAULT_CROSS_CLUSTER_EDGE_DENSITIES = (0.0, 0.2)
DEFAULT_DAILY_CONTACT_HAZARDS = (0.12, 0.14, 0.16, 0.18)


@dataclass(frozen=True, slots=True)
class FullHorizonObservation:
    """One trusted calibration row; none of these fields are agent-visible."""

    seed: int
    causal_mode: str
    growth_regime: str
    latent_infections: int
    reported_illnesses: int
    population_size: int
    followup_days: int

    @property
    def nors_eligible(self) -> bool:
        return self.reported_illnesses >= 2

    def as_dict(self) -> dict[str, Any]:
        return {**asdict(self), "nors_eligible": self.nors_eligible}


def generate_full_horizon_observation(
    *,
    seed: int,
    causal_mode: str,
    profile: Mapping[str, Any] | None = None,
    contact_hazard_multiplier: float = 1.0,
    common_source_exposure_multiplier: float = 1.0,
    followup_days: int = DEFAULT_FOLLOWUP_DAYS,
) -> FullHorizonObservation:
    """Run one seed once, with no admission filtering or outcome retry."""

    if type(seed) is not int or seed < 0:
        raise ValueError("seed must be a non-negative integer")
    if causal_mode not in SUPPORTED_CALIBRATION_MODES:
        raise ValueError("unsupported NORS calibration mode")
    _positive_multiplier(contact_hazard_multiplier, "contact hazard")
    _positive_multiplier(
        common_source_exposure_multiplier, "common-source exposure"
    )
    if type(followup_days) is not int or not 1 <= followup_days <= 60:
        raise ValueError("followup_days must be an integer from one through 60")

    selected_profile = _calibration_profile(
        profile,
        common_source_exposure_multiplier=common_source_exposure_multiplier,
    )
    backend = StarsimSurveillanceBackend(profile=selected_profile)
    presentation_key = hashlib.sha256(
        f"{PANEL_VERSION}:presentation:{seed}".encode("ascii")
    ).digest()
    regimes = selected_profile["closed_loop_configuration"][
        "growth_regime_multipliers"
    ]
    regime_names = tuple(sorted(regimes))
    if not regime_names:
        raise ValueError("profile has no growth regimes")
    growth_regime = regime_names[
        _keyed_private_seed(
            presentation_key, seed, "calibration-growth-regime"
        )
        % len(regime_names)
    ]
    growth_multiplier = float(regimes[growth_regime])
    exposures = backend._scheduled_exposures(
        seed=seed,
        attempt=0,
        presentation_key=presentation_key,
        causal_mode=causal_mode,
    )
    config = backend._config(
        _keyed_private_seed(presentation_key, seed, "calibration-starsim"),
        beta_multiplier=growth_multiplier * float(contact_hazard_multiplier),
        profile=selected_profile,
        causal_mode=causal_mode,
        scheduled_exposures=exposures,
    )
    run = backend._run(config)
    stream = IncrementalSurveillanceStream(
        seed=_keyed_private_seed(
            presentation_key, seed, "calibration-observation"
        ),
        presentation_key=presentation_key,
        profile=selected_profile,
        population_size=run.population_size,
        # A zero decision point plus the full engine horizon and follow-up
        # measures all reports. It does not reuse the agent-facing alert window.
        decision_minute=0,
        deadline_minutes=run.terminal_minute + followup_days * DAY_MINUTES,
        causal_mode=causal_mode,
    )
    stream.ingest(run.events)
    return FullHorizonObservation(
        seed=seed,
        causal_mode=causal_mode,
        growth_regime=growth_regime,
        latent_infections=len(run.events),
        reported_illnesses=len(stream.true_case_ids),
        population_size=run.population_size,
        followup_days=followup_days,
    )


def generate_calibration_panel(
    seeds: Sequence[int],
    *,
    causal_mode: str,
    profile: Mapping[str, Any] | None = None,
    contact_hazard_multiplier: float = 1.0,
    common_source_exposure_multiplier: float = 1.0,
    followup_days: int = DEFAULT_FOLLOWUP_DAYS,
) -> tuple[FullHorizonObservation, ...]:
    """Generate a predeclared seed panel without replacement or retries."""

    materialized = tuple(seeds)
    if (
        not materialized
        or len(set(materialized)) != len(materialized)
        or any(type(seed) is not int or seed < 0 for seed in materialized)
    ):
        raise ValueError("calibration seeds must be unique non-negative integers")
    return tuple(
        generate_full_horizon_observation(
            seed=seed,
            causal_mode=causal_mode,
            profile=profile,
            contact_hazard_multiplier=contact_hazard_multiplier,
            common_source_exposure_multiplier=common_source_exposure_multiplier,
            followup_days=followup_days,
        )
        for seed in materialized
    )


def evaluate_calibration_panel(
    observations: Sequence[FullHorizonObservation],
    target: Mapping[str, Any],
) -> dict[str, Any]:
    """Compare the NORS-eligible conditional distribution and show exclusions."""

    rows = tuple(observations)
    if not rows:
        raise ValueError("calibration panel is empty")
    modes = {row.causal_mode for row in rows}
    if len(modes) != 1 or len({row.seed for row in rows}) != len(rows):
        raise ValueError("calibration panel must contain one mode and unique seeds")
    eligible_values = [
        row.reported_illnesses for row in rows if row.nors_eligible
    ]
    minimum_eligible = max(3, math.ceil(len(rows) * MINIMUM_ELIGIBLE_FRACTION))
    comparison = (
        compare_reported_outbreak_sizes(eligible_values, target)
        if len(eligible_values) >= minimum_eligible
        else None
    )
    growth_counts: dict[str, int] = {}
    for row in rows:
        growth_counts[row.growth_regime] = growth_counts.get(row.growth_regime, 0) + 1
    row_commitment = hashlib.sha256(
        b"".join(
            _canonical_json(row.as_dict()) + b"\n"
            for row in sorted(rows, key=lambda item: item.seed)
        )
    ).hexdigest()
    return {
        "panel_version": PANEL_VERSION,
        "causal_mode": next(iter(modes)),
        "predeclared_seeds_sha256": hashlib.sha256(
            _canonical_json(sorted(row.seed for row in rows))
        ).hexdigest(),
        "panel_rows_sha256": row_commitment,
        "episodes_run_once": len(rows),
        "outcome_retries": 0,
        "nors_condition": "reported_illnesses >= 2",
        "nors_eligible_episodes": len(eligible_values),
        "nors_eligible_fraction": round(len(eligible_values) / len(rows), 6),
        "eligibility_is_not_a_nors_calibration_target": True,
        "minimum_eligible_for_comparison": minimum_eligible,
        "growth_regime_counts": dict(sorted(growth_counts.items())),
        "unconditional_reported_illnesses": _numeric_summary(
            [row.reported_illnesses for row in rows]
        ),
        "unconditional_latent_infections": _numeric_summary(
            [row.latent_infections for row in rows]
        ),
        "comparison": comparison,
        "fit_objective": (
            comparison["mean_absolute_log_quantile_error"]
            if comparison is not None
            else None
        ),
    }


def refine_nors_clustered_topology_candidate(
    plan: Mapping[str, Any],
    *,
    fit_seeds: Sequence[int],
    validation_seeds: Sequence[int],
    profile: Mapping[str, Any] | None = None,
    cluster_sizes: Sequence[int] = DEFAULT_CLUSTER_SIZES,
    within_cluster_degrees: Sequence[int] = DEFAULT_WITHIN_CLUSTER_DEGREES,
    cross_cluster_edge_densities: Sequence[float] = (
        DEFAULT_CROSS_CLUSTER_EDGE_DENSITIES
    ),
    daily_contact_hazards: Sequence[float] = DEFAULT_DAILY_CONTACT_HAZARDS,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Refine a private clustered P2P candidate without opening sealed data.

    Every grid cell runs exactly one world for every predeclared fit seed. The
    winner is selected solely against the released 2009--2018 institutional
    person-to-person target. Only after selection, the selected profile runs
    once on a disjoint simulator-seed panel against visible 2019 P2P data. A
    second, descriptive common-source 2019 run checks the preserved source
    candidate but cannot alter selection or the P2P-only frozen gate.
    """

    base_profile = _calibration_profile(profile)
    fit_seed_tuple = _valid_seed_panel(fit_seeds, "fit")
    validation_seed_tuple = _valid_seed_panel(validation_seeds, "validation")
    if set(fit_seed_tuple) & set(validation_seed_tuple):
        raise ValueError("fit and validation seed panels must be disjoint")

    plan_sha256 = _required_sha256(plan.get("plan_sha256"), "plan")
    fit_target = _released_cohort_target(
        plan, "calibration", "institution_person_to_person"
    )
    p2p_validation_target = _released_cohort_target(
        plan, "model_selection", "institution_person_to_person"
    )
    source_validation_target = _released_cohort_target(
        plan, "model_selection", "restaurant_common_source"
    )
    grid_parameters = _clustered_refinement_grid(
        base_profile,
        cluster_sizes=cluster_sizes,
        within_cluster_degrees=within_cluster_degrees,
        cross_cluster_edge_densities=cross_cluster_edge_densities,
        daily_contact_hazards=daily_contact_hazards,
    )
    grid_specification = {
        "cluster_sizes": sorted(
            {item["cluster_size"] for item in grid_parameters}
        ),
        "within_cluster_degrees": sorted(
            {item["within_cluster_degree"] for item in grid_parameters}
        ),
        "cross_cluster_edge_densities": sorted(
            {
                item["cross_cluster_edges_per_cluster"]
                for item in grid_parameters
            }
        ),
        "daily_contact_hazards": sorted(
            {item["daily_contact_hazard"] for item in grid_parameters}
        ),
        "candidate_count": len(grid_parameters),
    }
    grid_sha256 = hashlib.sha256(
        _canonical_json(grid_specification)
    ).hexdigest()
    fit_seed_sha256 = hashlib.sha256(
        _canonical_json(list(fit_seed_tuple))
    ).hexdigest()
    validation_seed_sha256 = hashlib.sha256(
        _canonical_json(list(validation_seed_tuple))
    ).hexdigest()
    contract = {
        "refinement_version": CLUSTERED_REFINEMENT_VERSION,
        "panel_version": PANEL_VERSION,
        "topology_version": CLUSTERED_STATIC_TOPOLOGY_VERSION,
        "plan_sha256": plan_sha256,
        "grid_sha256": grid_sha256,
        "fit_seed_panel_sha256": fit_seed_sha256,
        "validation_seed_panel_sha256": validation_seed_sha256,
        "fit_target_sha256": hashlib.sha256(
            _canonical_json(fit_target)
        ).hexdigest(),
        "p2p_validation_target_sha256": hashlib.sha256(
            _canonical_json(p2p_validation_target)
        ).hexdigest(),
        "common_source_validation_target_sha256": hashlib.sha256(
            _canonical_json(source_validation_target)
        ).hexdigest(),
        "fixed_initial_infections": CLUSTERED_FIXED_INITIAL_INFECTIONS,
        "visible_gate_scope": "institution_person_to_person_only",
        "visible_gate_maximum_mean_absolute_log_quantile_error": (
            CLUSTERED_VISIBLE_GATE_MAX_LOG_QUANTILE_ERROR
        ),
    }
    contract_sha256 = hashlib.sha256(_canonical_json(contract)).hexdigest()

    fit_grid: list[dict[str, Any]] = []
    expected_fit_regimes: dict[str, int] | None = None
    for parameters in grid_parameters:
        cell_profile = _build_clustered_candidate_profile(
            base_profile, parameters
        )
        panel = _exact_generated_panel(
            generate_calibration_panel(
                fit_seed_tuple,
                causal_mode="person_to_person",
                profile=cell_profile,
            ),
            expected_seeds=fit_seed_tuple,
            causal_mode="person_to_person",
        )
        evaluation = evaluate_calibration_panel(panel, fit_target)
        regime_counts = evaluation["growth_regime_counts"]
        if expected_fit_regimes is None:
            expected_fit_regimes = regime_counts
        elif regime_counts != expected_fit_regimes:
            raise RuntimeError(
                "growth-regime allocation changed across refinement cells"
            )
        fit_grid.append(
            {
                "parameters": dict(parameters),
                "configuration_sha256": _candidate_configuration_sha256(
                    cell_profile
                ),
                "panel_rows": _serialized_panel_rows(panel),
                "evaluation": evaluation,
            }
        )

    selectable = [
        row
        for row in fit_grid
        if row["evaluation"]["fit_objective"] is not None
    ]
    if not selectable:
        raise RuntimeError("no clustered grid cell produced enough outbreaks")
    selected = min(
        selectable,
        key=lambda row: (
            float(row["evaluation"]["fit_objective"]),
            float(row["parameters"]["daily_contact_hazard"]),
            float(
                row["parameters"]["cross_cluster_edges_per_cluster"]
            ),
            int(row["parameters"]["cluster_size"]),
            int(row["parameters"]["within_cluster_degree"]),
        ),
    )
    selected_parameters = dict(selected["parameters"])
    candidate_profile = _build_clustered_candidate_profile(
        base_profile, selected_parameters
    )

    # Selection is complete before either visible-2019 panel is constructed.
    p2p_validation_panel = _exact_generated_panel(
        generate_calibration_panel(
            validation_seed_tuple,
            causal_mode="person_to_person",
            profile=candidate_profile,
        ),
        expected_seeds=validation_seed_tuple,
        causal_mode="person_to_person",
    )
    p2p_validation = evaluate_calibration_panel(
        p2p_validation_panel, p2p_validation_target
    )
    p2p_objective = p2p_validation["fit_objective"]
    p2p_gate = {
        "scope": "institution_person_to_person_only",
        "metric": "mean_absolute_log_quantile_error",
        "maximum": CLUSTERED_VISIBLE_GATE_MAX_LOG_QUANTILE_ERROR,
        "frozen_before_fit": True,
        "passed": (
            p2p_objective is not None
            and float(p2p_objective)
            <= CLUSTERED_VISIBLE_GATE_MAX_LOG_QUANTILE_ERROR
        ),
    }

    source_validation_panel = _exact_generated_panel(
        generate_calibration_panel(
            validation_seed_tuple,
            causal_mode="common_source",
            profile=candidate_profile,
        ),
        expected_seeds=validation_seed_tuple,
        causal_mode="common_source",
    )
    source_validation = evaluate_calibration_panel(
        source_validation_panel, source_validation_target
    )
    source_configuration_before = _common_source_configuration(base_profile)
    source_configuration_after = _common_source_configuration(candidate_profile)
    if source_configuration_before != source_configuration_after:
        raise RuntimeError(
            "clustered P2P refinement changed common-source exposure settings"
        )

    report: dict[str, Any] = {
        "report_version": CLUSTERED_REFINEMENT_VERSION,
        "panel_version": PANEL_VERSION,
        "topology_version": CLUSTERED_STATIC_TOPOLOGY_VERSION,
        "plan_sha256": plan_sha256,
        "refinement_contract": contract,
        "refinement_contract_sha256": contract_sha256,
        "fit_partition": "calibration_2009_2018",
        "selection_cohort": "institution_person_to_person",
        "visible_validation_partition": "model_selection_2019",
        "selection_uses_visible_validation": False,
        "sealed_temporal_partitions_used": False,
        "sealed_data_status": "not_opened_not_used",
        "measurement_contract": {
            "estimand": "full-horizon reported illnesses per outbreak",
            "followup_days": DEFAULT_FOLLOWUP_DAYS,
            "one_world_per_seed_per_cell": True,
            "outcome_admission_filter": False,
            "outcome_retries": 0,
            "condition_for_nors_comparison": "reported_illnesses >= 2",
            "fixed_person_to_person_initial_infections": (
                CLUSTERED_FIXED_INITIAL_INFECTIONS
            ),
        },
        "identifiability_warning": (
            "Topology and contact hazard are composite distribution-matching "
            "parameters conditional on the fixed observation model; they are "
            "not uniquely identified biological effects."
        ),
        "grid_specification": grid_specification,
        "grid_sha256": grid_sha256,
        "fit_seed_panel_sha256": fit_seed_sha256,
        "validation_seed_panel_sha256": validation_seed_sha256,
        "fit_growth_regime_counts": expected_fit_regimes,
        "fit_grid": fit_grid,
        "selection_rule": (
            "minimum 2009-2018 P2P mean absolute log quantile error; "
            "deterministic parameter tie-break"
        ),
        "selected_parameters": selected_parameters,
        "selected_configuration_sha256": (
            _candidate_configuration_sha256(candidate_profile)
        ),
        "p2p_visible_validation": {
            "panel_rows": _serialized_panel_rows(p2p_validation_panel),
            "evaluation": p2p_validation,
            "preregistered_gate": p2p_gate,
        },
        "p2p_visible_gate_passed": p2p_gate["passed"],
        "common_source_visible_sensitivity": {
            "role": (
                "descriptive one-call check; not a selection criterion and "
                "not part of the P2P gate"
            ),
            "preserved_exposure_configuration": True,
            "exposure_configuration_sha256": hashlib.sha256(
                _canonical_json(source_configuration_after)
            ).hexdigest(),
            "panel_rows": _serialized_panel_rows(source_validation_panel),
            "evaluation": source_validation,
        },
        "true_blind_holdout_status": "not_opened_not_used",
    }
    report["report_sha256"] = hashlib.sha256(
        _canonical_json(report)
    ).hexdigest()

    # Preserve any parent NORS/common-source calibration record verbatim and
    # attach a separate refinement record. The profile remains an explicit
    # candidate and is never installed as a packaged default here.
    candidate_profile["clustered_refinement_record"] = {
        "report_version": CLUSTERED_REFINEMENT_VERSION,
        "report_sha256": report["report_sha256"],
        "refinement_contract_sha256": contract_sha256,
        "plan_sha256": plan_sha256,
        "fit_years": list(range(2009, 2019)),
        "visible_validation_years": [2019],
        "selected_parameters": selected_parameters,
        "p2p_visible_gate": dict(p2p_gate),
        "common_source_visible_check_is_descriptive": True,
        "sealed_data_used": False,
        "blind_holdout_passed": False,
    }
    return report, candidate_profile


def fit_nors_composite_candidate(
    plan: Mapping[str, Any],
    *,
    fit_seeds: Sequence[int],
    validation_seeds: Sequence[int],
    profile: Mapping[str, Any] | None = None,
    contact_hazard_multipliers: Sequence[float] = (
        DEFAULT_CONTACT_HAZARD_MULTIPLIERS
    ),
    common_source_exposure_multipliers: Sequence[float] = (
        DEFAULT_COMMON_SOURCE_EXPOSURE_MULTIPLIERS
    ),
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Fit on 2009--2018 targets, then evaluate once on visible 2019 targets.

    The two scalar multipliers are composite distribution-matching parameters.
    They are not estimates of a uniquely identified biological transmission
    rate or reporting probability.
    """

    base_profile = _calibration_profile(profile)
    fit_seed_tuple = _valid_seed_panel(fit_seeds, "fit")
    validation_seed_tuple = _valid_seed_panel(validation_seeds, "validation")
    if set(fit_seed_tuple) & set(validation_seed_tuple):
        raise ValueError("fit and validation seed panels must be disjoint")
    contact_grid = _valid_grid(contact_hazard_multipliers, "contact hazard")
    exposure_grid = _valid_grid(
        common_source_exposure_multipliers, "common-source exposure"
    )
    calibration_targets = _released_targets(plan, "calibration")
    validation_targets = _released_targets(plan, "model_selection")

    contact_candidates: list[dict[str, Any]] = []
    for multiplier in contact_grid:
        panel = generate_calibration_panel(
            fit_seed_tuple,
            causal_mode="person_to_person",
            profile=base_profile,
            contact_hazard_multiplier=multiplier,
        )
        evaluation = evaluate_calibration_panel(
            panel, calibration_targets["institution_person_to_person"]
        )
        contact_candidates.append(
            {"contact_hazard_multiplier": multiplier, "evaluation": evaluation}
        )
    selected_contact = _select_candidate(
        contact_candidates, "contact_hazard_multiplier"
    )
    contact_multiplier = float(selected_contact["contact_hazard_multiplier"])

    source_candidates: list[dict[str, Any]] = []
    for multiplier in exposure_grid:
        panel = generate_calibration_panel(
            fit_seed_tuple,
            causal_mode="common_source",
            profile=base_profile,
            contact_hazard_multiplier=contact_multiplier,
            common_source_exposure_multiplier=multiplier,
        )
        evaluation = evaluate_calibration_panel(
            panel, calibration_targets["restaurant_common_source"]
        )
        source_candidates.append(
            {
                "common_source_exposure_multiplier": multiplier,
                "evaluation": evaluation,
            }
        )
    selected_source = _select_candidate(
        source_candidates, "common_source_exposure_multiplier"
    )
    exposure_multiplier = float(
        selected_source["common_source_exposure_multiplier"]
    )

    fitted_profile = build_fitted_profile(
        base_profile,
        plan=plan,
        contact_hazard_multiplier=contact_multiplier,
        common_source_exposure_multiplier=exposure_multiplier,
    )
    validation: dict[str, Any] = {}
    for cohort, mode in (
        ("institution_person_to_person", "person_to_person"),
        ("restaurant_common_source", "common_source"),
    ):
        panel = generate_calibration_panel(
            validation_seed_tuple,
            causal_mode=mode,
            profile=fitted_profile,
        )
        evaluation = evaluate_calibration_panel(panel, validation_targets[cohort])
        objective = evaluation["fit_objective"]
        evaluation["preregistered_quantile_gate"] = {
            "maximum_mean_absolute_log_quantile_error": 0.35,
            "passed": objective is not None and float(objective) <= 0.35,
        }
        validation[cohort] = evaluation

    report: dict[str, Any] = {
        "report_version": "starsim_nors_composite_fit_v1",
        "panel_version": PANEL_VERSION,
        "plan_sha256": plan.get("plan_sha256"),
        "fit_partition": "calibration_2009_2018",
        "visible_validation_partition": "model_selection_2019",
        "sealed_temporal_partitions_used": False,
        "identifiability_warning": (
            "Contact-hazard and common-source exposure multipliers are "
            "composite distribution-matching parameters conditional on the "
            "fixed observation model; they are not uniquely identified "
            "biological effects."
        ),
        "measurement_contract": {
            "estimand": "full-horizon reported illnesses per outbreak",
            "followup_days": DEFAULT_FOLLOWUP_DAYS,
            "one_world_per_seed": True,
            "outcome_admission_filter": False,
            "condition_for_nors_comparison": "reported_illnesses >= 2",
        },
        "fit_seed_count": len(fit_seed_tuple),
        "validation_seed_count": len(validation_seed_tuple),
        "contact_hazard_grid": contact_candidates,
        "selected_contact_hazard_multiplier": contact_multiplier,
        "common_source_exposure_grid": source_candidates,
        "selected_common_source_exposure_multiplier": exposure_multiplier,
        "visible_validation": validation,
        "visible_validation_passed": all(
            item["preregistered_quantile_gate"]["passed"]
            for item in validation.values()
        ),
        "true_blind_holdout_status": "awaiting_independent_future_nors_vintage",
    }
    report["report_sha256"] = hashlib.sha256(_canonical_json(report)).hexdigest()
    return report, fitted_profile


def build_fitted_profile(
    profile: Mapping[str, Any],
    *,
    plan: Mapping[str, Any],
    contact_hazard_multiplier: float,
    common_source_exposure_multiplier: float,
) -> dict[str, Any]:
    """Materialize a candidate profile without mutating the source profile."""

    _positive_multiplier(contact_hazard_multiplier, "contact hazard")
    _positive_multiplier(
        common_source_exposure_multiplier, "common-source exposure"
    )
    fitted = _calibration_profile(
        profile,
        common_source_exposure_multiplier=common_source_exposure_multiplier,
    )
    transmission = fitted["transmission_configuration"]
    transmission["daily_transmission_hazard"] = round(
        float(transmission["daily_transmission_hazard"])
        * float(contact_hazard_multiplier),
        10,
    )
    transmission["status"] = "nors_composite_candidate_not_blindly_validated"
    fitted["profile_id"] = (
        f"{fitted['profile_id']}_nors_composite_candidate"
    )
    fitted["profile_status"] = "nors_composite_candidate"
    fitted["calibration_record"] = {
        "panel_version": PANEL_VERSION,
        "plan_sha256": plan.get("plan_sha256"),
        "fit_years": list(range(2009, 2019)),
        "visible_validation_years": [2019],
        "contact_hazard_multiplier": float(contact_hazard_multiplier),
        "common_source_exposure_multiplier": float(
            common_source_exposure_multiplier
        ),
        "identifiability": "composite_not_biological",
        "blind_holdout_passed": False,
    }
    return fitted


def _calibration_profile(
    profile: Mapping[str, Any] | None,
    *,
    common_source_exposure_multiplier: float = 1.0,
) -> dict[str, Any]:
    selected = deepcopy(
        dict(
            load_gi_surveillance_profile(LIVE_PROFILE_RESOURCE)
            if profile is None
            else profile
        )
    )
    closed_loop = selected.get("closed_loop_configuration")
    if not isinstance(closed_loop, Mapping):
        raise ValueError("calibration requires the live multi-route profile")
    modes = closed_loop.get("causal_modes")
    if not isinstance(modes, Mapping) or "common_source" not in modes:
        raise ValueError("profile has no common-source mode")
    mode = modes["common_source"]
    for field in (
        "predecision_exposure_candidates",
        "future_exposure_candidates",
    ):
        bounds = mode.get(field)
        if (
            not isinstance(bounds, list)
            or len(bounds) != 2
            or any(type(value) is not int or value < 0 for value in bounds)
            or bounds[0] > bounds[1]
        ):
            raise ValueError(f"invalid common-source {field}")
        scaled = [
            max(0, round(value * float(common_source_exposure_multiplier)))
            for value in bounds
        ]
        mode[field] = [min(scaled), max(scaled)]
    return selected


def _clustered_refinement_grid(
    profile: Mapping[str, Any],
    *,
    cluster_sizes: Sequence[int],
    within_cluster_degrees: Sequence[int],
    cross_cluster_edge_densities: Sequence[float],
    daily_contact_hazards: Sequence[float],
) -> tuple[dict[str, int | float], ...]:
    transmission = profile.get("transmission_configuration")
    closed_loop = profile.get("closed_loop_configuration")
    if not isinstance(transmission, Mapping) or not isinstance(
        closed_loop, Mapping
    ):
        raise ValueError("clustered refinement requires transmission settings")
    population = transmission.get("population_size")
    if type(population) is not int or population < 4:
        raise ValueError("clustered refinement requires an integer population")
    modes = closed_loop.get("causal_modes")
    p2p = modes.get("person_to_person") if isinstance(modes, Mapping) else None
    initial_prevalence = (
        p2p.get("initial_prevalence") if isinstance(p2p, Mapping) else None
    )
    if (
        type(initial_prevalence) not in (int, float)
        or not math.isclose(
            float(initial_prevalence),
            CLUSTERED_FIXED_INITIAL_INFECTIONS / population,
            rel_tol=0.0,
            abs_tol=1e-12,
        )
    ):
        raise ValueError(
            "person-to-person initial prevalence must equal exactly three "
            "infections divided by population"
        )

    sizes = _unique_integer_grid(cluster_sizes, "cluster size")
    degrees = _unique_integer_grid(
        within_cluster_degrees, "within-cluster degree"
    )
    densities = _unique_unit_interval_grid(
        cross_cluster_edge_densities, "cross-cluster edge density"
    )
    hazards = _unique_unit_interval_grid(
        daily_contact_hazards,
        "daily contact hazard",
        strictly_positive=True,
    )
    rows: list[dict[str, int | float]] = []
    for size, degree, density, hazard in itertools.product(
        sizes, degrees, densities, hazards
    ):
        topology = ClusteredStaticTopology(
            cluster_size=size,
            within_cluster_degree=degree,
            cross_cluster_edges_per_cluster=density,
        )
        if population % topology.cluster_size:
            raise ValueError("cluster size must divide population exactly")
        if density > 0.0 and population // topology.cluster_size < 2:
            raise ValueError("cross-cluster edges require at least two clusters")
        rows.append(
            {
                "cluster_size": size,
                "within_cluster_degree": degree,
                "cross_cluster_edges_per_cluster": density,
                "daily_contact_hazard": hazard,
            }
        )
    return tuple(rows)


def _build_clustered_candidate_profile(
    profile: Mapping[str, Any],
    parameters: Mapping[str, int | float],
) -> dict[str, Any]:
    candidate = deepcopy(dict(profile))
    transmission = candidate.get("transmission_configuration")
    if not isinstance(transmission, dict):
        raise ValueError("candidate profile has no mutable transmission settings")
    parent_status = transmission.get("status")
    transmission["daily_transmission_hazard"] = float(
        parameters["daily_contact_hazard"]
    )
    transmission["private_contact_topology"] = {
        "construction_version": CLUSTERED_STATIC_TOPOLOGY_VERSION,
        "cluster_size": int(parameters["cluster_size"]),
        "within_cluster_degree": int(
            parameters["within_cluster_degree"]
        ),
        "cross_cluster_edges_per_cluster": float(
            parameters["cross_cluster_edges_per_cluster"]
        ),
    }
    transmission["private_fixed_initial_infections"] = {
        "person_to_person": CLUSTERED_FIXED_INITIAL_INFECTIONS
    }
    transmission["clustered_refinement_parent_status"] = parent_status
    transmission["status"] = (
        "clustered_static_candidate_not_blindly_validated"
    )
    candidate["profile_id"] = (
        f"{candidate.get('profile_id', 'gi_surveillance')}"
        "_clustered_static_candidate"
    )
    candidate["profile_status"] = (
        "clustered_static_candidate_not_blindly_validated"
    )
    return candidate


def _common_source_configuration(profile: Mapping[str, Any]) -> dict[str, Any]:
    closed_loop = profile.get("closed_loop_configuration")
    modes = (
        closed_loop.get("causal_modes")
        if isinstance(closed_loop, Mapping)
        else None
    )
    common_source = (
        modes.get("common_source") if isinstance(modes, Mapping) else None
    )
    if not isinstance(common_source, Mapping):
        raise ValueError("candidate profile has no common-source configuration")
    parent_record = profile.get("calibration_record")
    exposure_multiplier = (
        parent_record.get("common_source_exposure_multiplier")
        if isinstance(parent_record, Mapping)
        else None
    )
    return {
        "causal_mode": deepcopy(dict(common_source)),
        "parent_common_source_exposure_multiplier": exposure_multiplier,
    }


def _candidate_configuration_sha256(profile: Mapping[str, Any]) -> str:
    projection = {
        "parameters": profile.get("parameters"),
        "transmission_configuration": profile.get(
            "transmission_configuration"
        ),
        "closed_loop_configuration": profile.get(
            "closed_loop_configuration"
        ),
    }
    return hashlib.sha256(_canonical_json(projection)).hexdigest()


def _exact_generated_panel(
    observations: Sequence[FullHorizonObservation],
    *,
    expected_seeds: Sequence[int],
    causal_mode: str,
) -> tuple[FullHorizonObservation, ...]:
    rows = tuple(observations)
    expected = tuple(expected_seeds)
    if (
        len(rows) != len(expected)
        or any(not isinstance(row, FullHorizonObservation) for row in rows)
        or tuple(row.seed for row in rows) != expected
        or any(row.causal_mode != causal_mode for row in rows)
    ):
        raise RuntimeError(
            "panel generation must return exactly one ordered row per "
            "predeclared seed without filtering"
        )
    return rows


def _serialized_panel_rows(
    observations: Sequence[FullHorizonObservation],
) -> list[dict[str, Any]]:
    return [
        row.as_dict()
        for row in sorted(observations, key=lambda item: item.seed)
    ]


def _released_cohort_target(
    plan: Mapping[str, Any],
    partition: str,
    cohort_name: str,
) -> dict[str, Any]:
    if partition not in {"calibration", "model_selection"}:
        raise ValueError("clustered refinement may use only released partitions")
    if plan.get("plan_version") != CALIBRATION_PLAN_VERSION:
        raise ValueError("unsupported NORS calibration plan")
    cohorts = plan.get("cohorts")
    cohort = cohorts.get(cohort_name) if isinstance(cohorts, Mapping) else None
    released = (
        cohort.get("released_targets")
        if isinstance(cohort, Mapping)
        else None
    )
    target = released.get(partition) if isinstance(released, Mapping) else None
    if not isinstance(target, Mapping):
        raise ValueError("calibration plan is missing a released cohort target")
    return deepcopy(dict(target))


def _required_sha256(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{label} SHA-256 must be 64 lowercase hex characters")
    return value


def _unique_integer_grid(
    values: Sequence[int], label: str
) -> tuple[int, ...]:
    grid = tuple(values)
    if (
        not grid
        or len(set(grid)) != len(grid)
        or any(type(value) is not int or value < 1 for value in grid)
    ):
        raise ValueError(f"{label} grid must contain unique positive integers")
    return tuple(sorted(grid))


def _unique_unit_interval_grid(
    values: Sequence[float],
    label: str,
    *,
    strictly_positive: bool = False,
) -> tuple[float, ...]:
    materialized = tuple(values)
    if not materialized or len(set(materialized)) != len(materialized):
        raise ValueError(f"{label} grid must contain unique values")
    result: list[float] = []
    for value in materialized:
        if (
            type(value) not in (int, float)
            or not math.isfinite(float(value))
            or not 0.0 <= float(value) <= 1.0
            or (strictly_positive and float(value) == 0.0)
        ):
            interval = "(0, 1]" if strictly_positive else "[0, 1]"
            raise ValueError(f"{label} values must be finite and in {interval}")
        result.append(float(value))
    return tuple(sorted(result))


def _released_targets(
    plan: Mapping[str, Any], partition: str
) -> dict[str, Mapping[str, Any]]:
    if plan.get("plan_version") != CALIBRATION_PLAN_VERSION:
        raise ValueError("unsupported NORS calibration plan")
    cohorts = plan.get("cohorts")
    if not isinstance(cohorts, Mapping):
        raise ValueError("calibration plan has no cohorts")
    result: dict[str, Mapping[str, Any]] = {}
    for name in ("institution_person_to_person", "restaurant_common_source"):
        cohort = cohorts.get(name)
        targets = (
            cohort.get("released_targets")
            if isinstance(cohort, Mapping)
            else None
        )
        target = targets.get(partition) if isinstance(targets, Mapping) else None
        if not isinstance(target, Mapping):
            raise ValueError("calibration plan is missing a released target")
        result[name] = target
    return result


def _select_candidate(
    candidates: Sequence[Mapping[str, Any]], parameter: str
) -> Mapping[str, Any]:
    eligible = [
        candidate
        for candidate in candidates
        if candidate["evaluation"]["fit_objective"] is not None
    ]
    if not eligible:
        raise RuntimeError("no calibration grid point produced enough outbreaks")
    return min(
        eligible,
        key=lambda item: (
            float(item["evaluation"]["fit_objective"]),
            float(item[parameter]),
        ),
    )


def _valid_seed_panel(values: Sequence[int], label: str) -> tuple[int, ...]:
    panel = tuple(values)
    if (
        len(panel) < 5
        or len(set(panel)) != len(panel)
        or any(type(value) is not int or value < 0 for value in panel)
    ):
        raise ValueError(f"{label} seeds must contain at least five unique values")
    return panel


def _valid_grid(values: Sequence[float], label: str) -> tuple[float, ...]:
    grid = tuple(float(value) for value in values)
    if not grid or len(set(grid)) != len(grid):
        raise ValueError(f"{label} grid must contain unique values")
    for value in grid:
        _positive_multiplier(value, label)
    return tuple(sorted(grid))


def _positive_multiplier(value: object, label: str) -> None:
    if (
        type(value) not in (int, float)
        or not math.isfinite(float(value))
        or not 0.01 <= float(value) <= 10.0
    ):
        raise ValueError(f"{label} multiplier must be finite and in [0.01, 10]")


def _numeric_summary(values: Sequence[int]) -> dict[str, int | float]:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("cannot summarize an empty panel")

    def quantile(probability: float) -> float:
        position = (len(ordered) - 1) * probability
        lower = int(position)
        upper = min(lower + 1, len(ordered) - 1)
        fraction = position - lower
        return ordered[lower] + fraction * (ordered[upper] - ordered[lower])

    return {
        "n": len(ordered),
        "min": ordered[0],
        "q25": round(quantile(0.25), 6),
        "median": round(quantile(0.5), 6),
        "q75": round(quantile(0.75), 6),
        "p90": round(quantile(0.9), 6),
        "max": ordered[-1],
        "mean": round(sum(ordered) / len(ordered), 6),
    }


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
