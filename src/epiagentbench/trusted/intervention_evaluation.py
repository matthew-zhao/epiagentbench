"""Uncertainty-aware decision analysis for future intervention rollouts.

This evaluator-only module is deliberately detached from the live episode
runtime. It scores counterfactual rollout outcomes only when every policy was
branched from the same committed public opening history and evaluated on the
same future-randomness, posterior, and intervention-effect draws.

These calculations are not epidemiologic calibration or external validation.
Negative-control and dose-response checks below test simulator contracts; they
cannot establish that a simulator represents real outbreaks.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
from dataclasses import dataclass
from itertools import pairwise
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence


EVIDENCE_STATUS = "simulation_decision_analysis_not_epidemiologic_calibration"

OUTCOME_FIELDS = (
    "resident_symptomatic_cases",
    "staff_symptomatic_cases",
    "staff_absence_days",
    "hospitalizations",
    "deaths",
    "incident_duration_days",
    "restriction_days",
    "closure_days",
    "tests_performed",
    "cleaning_hours",
    "investigator_hours",
    "false_escalations",
    "unresolved_reporting_errors",
)

DEFAULT_NEGATIVE_CONTROL_FIELDS = (
    "resident_symptomatic_cases",
    "staff_symptomatic_cases",
    "hospitalizations",
    "deaths",
    "incident_duration_days",
)


def _require_identifier(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise ValueError(
            f"{name} must be a non-empty string of at most 200 characters"
        )


def _require_sha256(value: str, name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be a lowercase hexadecimal SHA-256 digest")


def _finite_nonnegative(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    converted = float(value)
    if not math.isfinite(converted) or converted < 0.0:
        raise ValueError(f"{name} must be finite and non-negative")
    return converted


def _validate_json_value(value: Any, path: str = "opening_history") -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} contains a non-finite number")
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path} contains a non-string object key")
            _validate_json_value(child, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _validate_json_value(child, f"{path}[{index}]")
        return
    raise ValueError(f"{path} is not canonical JSON data")


def _canonical_json_bytes(value: Any) -> bytes:
    _validate_json_value(value)
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


@dataclass(frozen=True, slots=True)
class OpeningHistoryCommitment:
    """Digest of public information available before future branching.

    The history is not retained. Only this domain-separated commitment and its
    public cutoff metadata are carried into trusted rollout records.
    """

    sha256: str
    cutoff_minute: int
    schema_version: str = "opening_history_v1"

    def __post_init__(self) -> None:
        _require_sha256(self.sha256, "opening-history sha256")
        if type(self.cutoff_minute) is not int or self.cutoff_minute < 0:
            raise ValueError("cutoff_minute must be a non-negative integer")
        _require_identifier(self.schema_version, "schema_version")

    def as_dict(self) -> dict[str, str | int]:
        return {
            "sha256": self.sha256,
            "cutoff_minute": self.cutoff_minute,
            "schema_version": self.schema_version,
        }


def commit_opening_history(
    public_opening_history: Any,
    *,
    cutoff_minute: int,
    schema_version: str = "opening_history_v1",
) -> OpeningHistoryCommitment:
    """Commit canonical public history without retaining or returning it."""

    if type(cutoff_minute) is not int or cutoff_minute < 0:
        raise ValueError("cutoff_minute must be a non-negative integer")
    _require_identifier(schema_version, "schema_version")
    payload = {
        "commitment_domain": "epiagentbench.opening_history",
        "cutoff_minute": cutoff_minute,
        "history": public_opening_history,
        "schema_version": schema_version,
    }
    digest = hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()
    return OpeningHistoryCommitment(
        sha256=digest,
        cutoff_minute=cutoff_minute,
        schema_version=schema_version,
    )


@dataclass(frozen=True, slots=True)
class InterventionOutcomes:
    """Health, continuity, and response-burden outcomes; smaller is better."""

    resident_symptomatic_cases: float = 0.0
    staff_symptomatic_cases: float = 0.0
    staff_absence_days: float = 0.0
    hospitalizations: float = 0.0
    deaths: float = 0.0
    incident_duration_days: float = 0.0
    restriction_days: float = 0.0
    closure_days: float = 0.0
    tests_performed: float = 0.0
    cleaning_hours: float = 0.0
    investigator_hours: float = 0.0
    false_escalations: float = 0.0
    unresolved_reporting_errors: float = 0.0

    def __post_init__(self) -> None:
        for field_name in OUTCOME_FIELDS:
            _finite_nonnegative(getattr(self, field_name), field_name)

    def as_dict(self) -> dict[str, float]:
        return {
            field_name: float(getattr(self, field_name))
            for field_name in OUTCOME_FIELDS
        }


def _validated_weights(weights: Mapping[str, float]) -> dict[str, float]:
    if not isinstance(weights, Mapping):
        raise ValueError("outcome_loss_weights must be a mapping")
    supplied = set(weights)
    expected = set(OUTCOME_FIELDS)
    if supplied != expected:
        missing = sorted(expected - supplied)
        extra = sorted(supplied - expected)
        raise ValueError(
            "outcome_loss_weights must explicitly cover the outcome vector; "
            f"missing={missing}, extra={extra}"
        )
    return {
        field_name: _finite_nonnegative(weights[field_name], field_name)
        for field_name in OUTCOME_FIELDS
    }


def stakeholder_weight_profile_sha256(
    *,
    profile_id: str,
    profile_version: str,
    stakeholder_group: str,
    registration_reference: str,
    outcome_loss_weights: Mapping[str, float],
) -> str:
    """Return the content digest to freeze before outcomes are inspected.

    Digest verification prevents content substitution, but does not prove when
    or by whom it was registered. The caller must preserve that evidence at
    ``registration_reference``.
    """

    for value, name in (
        (profile_id, "profile_id"),
        (profile_version, "profile_version"),
        (stakeholder_group, "stakeholder_group"),
        (registration_reference, "registration_reference"),
    ):
        _require_identifier(value, name)
    weights = _validated_weights(outcome_loss_weights)
    payload = {
        "commitment_domain": "epiagentbench.stakeholder_weights",
        "outcome_loss_weights": weights,
        "profile_id": profile_id,
        "profile_version": profile_version,
        "registration_reference": registration_reference,
        "stakeholder_group": stakeholder_group,
    }
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


@dataclass(frozen=True, slots=True)
class StakeholderWeightProfile:
    """A stakeholder loss-weight profile matching a preregistered digest."""

    profile_id: str
    profile_version: str
    stakeholder_group: str
    registration_reference: str
    registration_sha256: str
    outcome_loss_weights: Mapping[str, float]

    def __post_init__(self) -> None:
        _require_sha256(self.registration_sha256, "registration_sha256")
        weights = _validated_weights(self.outcome_loss_weights)
        expected = stakeholder_weight_profile_sha256(
            profile_id=self.profile_id,
            profile_version=self.profile_version,
            stakeholder_group=self.stakeholder_group,
            registration_reference=self.registration_reference,
            outcome_loss_weights=weights,
        )
        if not hmac.compare_digest(expected, self.registration_sha256):
            raise ValueError(
                "stakeholder weight profile does not match its registration digest"
            )
        object.__setattr__(
            self,
            "outcome_loss_weights",
            MappingProxyType(weights),
        )

    def loss(self, outcomes: InterventionOutcomes) -> float:
        loss = math.fsum(
            self.outcome_loss_weights[field_name]
            * float(getattr(outcomes, field_name))
            for field_name in OUTCOME_FIELDS
        )
        if not math.isfinite(loss):
            raise ValueError("weighted outcome loss is not finite")
        return loss

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "stakeholder_group": self.stakeholder_group,
            "registration_reference": self.registration_reference,
            "registration_sha256": self.registration_sha256,
            "outcome_loss_weights": dict(self.outcome_loss_weights),
        }


@dataclass(frozen=True, slots=True, order=True)
class UncertaintyDrawKey:
    """Common-random-number key shared by every compared policy."""

    future_seed: int
    posterior_draw_id: str
    intervention_effect_draw_id: str

    def __post_init__(self) -> None:
        if type(self.future_seed) is not int or self.future_seed < 0:
            raise ValueError("future_seed must be a non-negative integer")
        _require_identifier(self.posterior_draw_id, "posterior_draw_id")
        _require_identifier(
            self.intervention_effect_draw_id,
            "intervention_effect_draw_id",
        )


@dataclass(frozen=True, slots=True)
class PolicyOutcomeDraw:
    """One policy outcome on one committed future uncertainty draw."""

    opening_history: OpeningHistoryCommitment
    policy_id: str
    future_seed: int
    posterior_draw_id: str
    intervention_effect_draw_id: str
    outcomes: InterventionOutcomes

    def __post_init__(self) -> None:
        if not isinstance(self.opening_history, OpeningHistoryCommitment):
            raise ValueError("opening_history must be an OpeningHistoryCommitment")
        _require_identifier(self.policy_id, "policy_id")
        if not isinstance(self.outcomes, InterventionOutcomes):
            raise ValueError("outcomes must be an InterventionOutcomes vector")
        self.draw_key()

    def draw_key(self) -> UncertaintyDrawKey:
        return UncertaintyDrawKey(
            future_seed=self.future_seed,
            posterior_draw_id=self.posterior_draw_id,
            intervention_effect_draw_id=self.intervention_effect_draw_id,
        )


@dataclass(frozen=True, slots=True)
class UncertaintyInterval:
    probability: float
    lower: float
    upper: float

    def as_dict(self) -> dict[str, float]:
        return {
            "probability": self.probability,
            "lower": self.lower,
            "upper": self.upper,
        }


@dataclass(frozen=True, slots=True)
class NumericOutcomeSummary:
    mean: float
    minimum: float
    maximum: float
    uncertainty_interval: UncertaintyInterval

    def as_dict(self) -> dict[str, Any]:
        return {
            "mean": self.mean,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "uncertainty_interval": self.uncertainty_interval.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class PolicyVectorSummary:
    policy_id: str
    draw_count: int
    outcomes: Mapping[str, NumericOutcomeSummary]

    def as_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "draw_count": self.draw_count,
            "outcomes": {
                key: value.as_dict() for key, value in self.outcomes.items()
            },
        }


@dataclass(frozen=True, slots=True)
class PolicyUtilitySummary:
    policy_id: str
    draw_count: int
    mean_utility: float
    mean_harm: float
    mean_drawwise_regret: float
    regret_vs_best_mean_policy: float
    utility_uncertainty_interval: UncertaintyInterval
    severe_tail_probability: float
    severe_tail_mean_harm: float
    severe_tail_harm_threshold: float
    worst_harm: float
    draw_optimal_rate: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "draw_count": self.draw_count,
            "mean_utility": self.mean_utility,
            "mean_harm": self.mean_harm,
            "mean_drawwise_regret": self.mean_drawwise_regret,
            "regret_vs_best_mean_policy": self.regret_vs_best_mean_policy,
            "utility_uncertainty_interval": (
                self.utility_uncertainty_interval.as_dict()
            ),
            "severe_tail_probability": self.severe_tail_probability,
            "severe_tail_mean_harm": self.severe_tail_mean_harm,
            "severe_tail_harm_threshold": self.severe_tail_harm_threshold,
            "worst_harm": self.worst_harm,
            "draw_optimal_rate": self.draw_optimal_rate,
        }


@dataclass(frozen=True, slots=True)
class WeightProfileEvaluation:
    profile_id: str
    registration_sha256: str
    ranking: tuple[str, ...]
    ranks: Mapping[str, int]
    policy_summaries: Mapping[str, PolicyUtilitySummary]

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "registration_sha256": self.registration_sha256,
            "ranking": list(self.ranking),
            "ranks": dict(self.ranks),
            "policy_summaries": {
                key: value.as_dict()
                for key, value in self.policy_summaries.items()
            },
        }


@dataclass(frozen=True, slots=True)
class PolicyRankSensitivity:
    policy_id: str
    best_rank: int
    worst_rank: int
    rank_span: int
    first_place_profile_count: int

    def as_dict(self) -> dict[str, int | str]:
        return {
            "policy_id": self.policy_id,
            "best_rank": self.best_rank,
            "worst_rank": self.worst_rank,
            "rank_span": self.rank_span,
            "first_place_profile_count": self.first_place_profile_count,
        }


@dataclass(frozen=True, slots=True)
class InterventionEvaluationReport:
    opening_history: OpeningHistoryCommitment
    draw_count: int
    future_seed_count: int
    posterior_draw_count: int
    intervention_effect_draw_count: int
    interval_probability: float
    severe_tail_probability: float
    vector_summaries: Mapping[str, PolicyVectorSummary]
    weight_profile_evaluations: Mapping[str, WeightProfileEvaluation]
    rank_sensitivity: Mapping[str, PolicyRankSensitivity]
    evidence_status: str = EVIDENCE_STATUS

    def as_dict(self) -> dict[str, Any]:
        return {
            "opening_history": self.opening_history.as_dict(),
            "draw_count": self.draw_count,
            "future_seed_count": self.future_seed_count,
            "posterior_draw_count": self.posterior_draw_count,
            "intervention_effect_draw_count": self.intervention_effect_draw_count,
            "interval_probability": self.interval_probability,
            "severe_tail_probability": self.severe_tail_probability,
            "vector_summaries": {
                key: value.as_dict() for key, value in self.vector_summaries.items()
            },
            "weight_profile_evaluations": {
                key: value.as_dict()
                for key, value in self.weight_profile_evaluations.items()
            },
            "rank_sensitivity": {
                key: value.as_dict() for key, value in self.rank_sensitivity.items()
            },
            "evidence_status": self.evidence_status,
        }


def _validate_probability(value: float, name: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0.0 < float(value) < 1.0
    ):
        raise ValueError(f"{name} must be finite and strictly between zero and one")


def _mean(values: Sequence[float]) -> float:
    if not values:
        raise ValueError("cannot summarize an empty sequence")
    return math.fsum(values) / len(values)


def _quantile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise ValueError("cannot take a quantile of an empty sequence")
    position = (len(ordered) - 1) * probability
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return ordered[lower_index]
    fraction = position - lower_index
    return (
        ordered[lower_index] * (1.0 - fraction)
        + ordered[upper_index] * fraction
    )


def _interval(
    values: Sequence[float],
    probability: float,
) -> UncertaintyInterval:
    tail = (1.0 - probability) / 2.0
    return UncertaintyInterval(
        probability=probability,
        lower=_quantile(values, tail),
        upper=_quantile(values, 1.0 - tail),
    )


def _numeric_summary(
    values: Sequence[float],
    probability: float,
) -> NumericOutcomeSummary:
    return NumericOutcomeSummary(
        mean=_mean(values),
        minimum=min(values),
        maximum=max(values),
        uncertainty_interval=_interval(values, probability),
    )


def _validated_policy_ids(policy_ids: Sequence[str]) -> tuple[str, ...]:
    if isinstance(policy_ids, (str, bytes)):
        raise ValueError("policy_ids must be a sequence of identifiers")
    policies = tuple(policy_ids)
    if not policies:
        raise ValueError("at least one policy_id is required")
    for policy_id in policies:
        _require_identifier(policy_id, "policy_id")
    if len(set(policies)) != len(policies):
        raise ValueError("policy_ids must be unique")
    return policies


def _validated_profiles(
    profiles: Sequence[StakeholderWeightProfile],
) -> tuple[StakeholderWeightProfile, ...]:
    if isinstance(profiles, (str, bytes)):
        raise ValueError("weight_profiles must be a sequence")
    materialized = tuple(profiles)
    if not materialized:
        raise ValueError("at least one stakeholder weight profile is required")
    if not all(
        isinstance(profile, StakeholderWeightProfile)
        for profile in materialized
    ):
        raise ValueError("weight_profiles contains an invalid profile")
    profile_ids = [profile.profile_id for profile in materialized]
    if len(set(profile_ids)) != len(profile_ids):
        raise ValueError("stakeholder profile IDs must be unique")
    return materialized


def _balanced_panel(
    rows: Iterable[PolicyOutcomeDraw],
    policies: Sequence[str],
    opening_history: OpeningHistoryCommitment,
    *,
    allow_unrequested_policies: bool = False,
) -> dict[str, dict[UncertaintyDrawKey, PolicyOutcomeDraw]]:
    if not isinstance(opening_history, OpeningHistoryCommitment):
        raise ValueError("opening_history must be an OpeningHistoryCommitment")
    expected_policies = set(policies)
    indexed: dict[str, dict[UncertaintyDrawKey, PolicyOutcomeDraw]] = {
        policy_id: {} for policy_id in policies
    }
    for row in rows:
        if not isinstance(row, PolicyOutcomeDraw):
            raise ValueError("panel rows must be PolicyOutcomeDraw values")
        if row.opening_history != opening_history:
            raise ValueError("panel mixes or mismatches opening-history commitments")
        if row.policy_id not in expected_policies:
            if allow_unrequested_policies:
                continue
            raise ValueError(f"unexpected policy_id in panel: {row.policy_id}")
        key = row.draw_key()
        if key in indexed[row.policy_id]:
            raise ValueError(f"duplicate draw for policy {row.policy_id}: {key}")
        indexed[row.policy_id][key] = row

    if not any(indexed.values()):
        raise ValueError("policy panel is empty")
    reference_keys = set(indexed[policies[0]])
    if not reference_keys:
        raise ValueError(f"policy {policies[0]} has no outcome draws")
    for policy_id in policies[1:]:
        keys = set(indexed[policy_id])
        if keys != reference_keys:
            missing = len(reference_keys - keys)
            extra = len(keys - reference_keys)
            raise ValueError(
                "policy panel must be balanced on identical uncertainty draws; "
                f"policy={policy_id}, missing={missing}, extra={extra}"
            )
    return indexed


def _rank_sensitivity(
    policy_id: str,
    profile_ranks: Mapping[str, Mapping[str, int]],
) -> PolicyRankSensitivity:
    ranks = [values[policy_id] for values in profile_ranks.values()]
    return PolicyRankSensitivity(
        policy_id=policy_id,
        best_rank=min(ranks),
        worst_rank=max(ranks),
        rank_span=max(ranks) - min(ranks),
        first_place_profile_count=sum(rank == 1 for rank in ranks),
    )


def evaluate_policy_panel(
    rows: Iterable[PolicyOutcomeDraw],
    *,
    policy_ids: Sequence[str],
    weight_profiles: Sequence[StakeholderWeightProfile],
    opening_history: OpeningHistoryCommitment,
    interval_probability: float = 0.90,
    severe_tail_probability: float = 0.10,
    minimum_axis_draws: int = 2,
) -> InterventionEvaluationReport:
    """Score a balanced policy panel under uncertainty and frozen weights.

    Utility is negative weighted burden, so larger is better. Drawwise regret
    compares with the best policy for each identical draw; expected regret
    compares with the best policy by mean utility and is not clairvoyant.
    """

    _validate_probability(interval_probability, "interval_probability")
    _validate_probability(severe_tail_probability, "severe_tail_probability")
    if type(minimum_axis_draws) is not int or minimum_axis_draws < 1:
        raise ValueError("minimum_axis_draws must be a positive integer")
    policies = _validated_policy_ids(policy_ids)
    profiles = _validated_profiles(weight_profiles)
    indexed = _balanced_panel(rows, policies, opening_history)
    draw_keys = tuple(sorted(next(iter(indexed.values()))))

    future_seeds = {key.future_seed for key in draw_keys}
    posterior_draws = {key.posterior_draw_id for key in draw_keys}
    effect_draws = {key.intervention_effect_draw_id for key in draw_keys}
    for values, name in (
        (future_seeds, "future seeds"),
        (posterior_draws, "posterior draws"),
        (effect_draws, "intervention-effect draws"),
    ):
        if len(values) < minimum_axis_draws:
            raise ValueError(
                f"panel has {len(values)} distinct {name}; "
                f"at least {minimum_axis_draws} required"
            )

    vector_summaries: dict[str, PolicyVectorSummary] = {}
    for policy_id in policies:
        policy_rows = indexed[policy_id]
        summaries = {
            field_name: _numeric_summary(
                [
                    float(getattr(policy_rows[key].outcomes, field_name))
                    for key in draw_keys
                ],
                interval_probability,
            )
            for field_name in OUTCOME_FIELDS
        }
        vector_summaries[policy_id] = PolicyVectorSummary(
            policy_id=policy_id,
            draw_count=len(draw_keys),
            outcomes=MappingProxyType(summaries),
        )

    profile_evaluations: dict[str, WeightProfileEvaluation] = {}
    profile_ranks: dict[str, dict[str, int]] = {}
    for profile in profiles:
        losses = {
            policy_id: [
                profile.loss(indexed[policy_id][key].outcomes)
                for key in draw_keys
            ]
            for policy_id in policies
        }
        utilities = {
            policy_id: [-loss for loss in policy_losses]
            for policy_id, policy_losses in losses.items()
        }
        mean_utilities = {
            policy_id: _mean(values)
            for policy_id, values in utilities.items()
        }
        best_mean_utility = max(mean_utilities.values())
        per_draw_best = [
            max(utilities[policy_id][index] for policy_id in policies)
            for index in range(len(draw_keys))
        ]

        utility_summaries: dict[str, PolicyUtilitySummary] = {}
        for policy_id in policies:
            policy_losses = losses[policy_id]
            policy_utilities = utilities[policy_id]
            ordered_harms = sorted(policy_losses, reverse=True)
            tail_count = max(
                1,
                math.ceil(len(ordered_harms) * severe_tail_probability),
            )
            severe_tail = ordered_harms[:tail_count]
            drawwise_regrets = [
                best - utility
                for best, utility in zip(
                    per_draw_best,
                    policy_utilities,
                    strict=True,
                )
            ]
            optimal_draws = sum(
                math.isclose(utility, best, rel_tol=0.0, abs_tol=1e-12)
                for best, utility in zip(
                    per_draw_best,
                    policy_utilities,
                    strict=True,
                )
            )
            utility_summaries[policy_id] = PolicyUtilitySummary(
                policy_id=policy_id,
                draw_count=len(draw_keys),
                mean_utility=mean_utilities[policy_id],
                mean_harm=_mean(policy_losses),
                mean_drawwise_regret=_mean(drawwise_regrets),
                regret_vs_best_mean_policy=(
                    best_mean_utility - mean_utilities[policy_id]
                ),
                utility_uncertainty_interval=_interval(
                    policy_utilities,
                    interval_probability,
                ),
                severe_tail_probability=severe_tail_probability,
                severe_tail_mean_harm=_mean(severe_tail),
                severe_tail_harm_threshold=severe_tail[-1],
                worst_harm=ordered_harms[0],
                draw_optimal_rate=optimal_draws / len(draw_keys),
            )

        ranking = tuple(
            sorted(
                policies,
                key=lambda policy_id: (-mean_utilities[policy_id], policy_id),
            )
        )
        ranks = {
            policy_id: 1
            + sum(
                other_utility > mean_utilities[policy_id] + 1e-12
                for other_id, other_utility in mean_utilities.items()
                if other_id != policy_id
            )
            for policy_id in policies
        }
        profile_ranks[profile.profile_id] = ranks
        profile_evaluations[profile.profile_id] = WeightProfileEvaluation(
            profile_id=profile.profile_id,
            registration_sha256=profile.registration_sha256,
            ranking=ranking,
            ranks=MappingProxyType(ranks),
            policy_summaries=MappingProxyType(utility_summaries),
        )

    rank_sensitivity = {
        policy_id: _rank_sensitivity(policy_id, profile_ranks)
        for policy_id in policies
    }
    return InterventionEvaluationReport(
        opening_history=opening_history,
        draw_count=len(draw_keys),
        future_seed_count=len(future_seeds),
        posterior_draw_count=len(posterior_draws),
        intervention_effect_draw_count=len(effect_draws),
        interval_probability=interval_probability,
        severe_tail_probability=severe_tail_probability,
        vector_summaries=MappingProxyType(vector_summaries),
        weight_profile_evaluations=MappingProxyType(profile_evaluations),
        rank_sensitivity=MappingProxyType(rank_sensitivity),
    )


@dataclass(frozen=True, slots=True)
class NegativeControlFieldResult:
    outcome_name: str
    reference_mean: float
    negative_control_mean: float
    mean_paired_delta: float
    mean_absolute_paired_delta: float
    paired_delta_interval: UncertaintyInterval
    absolute_tolerance: float
    contract_passed: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "outcome_name": self.outcome_name,
            "reference_mean": self.reference_mean,
            "negative_control_mean": self.negative_control_mean,
            "mean_paired_delta": self.mean_paired_delta,
            "mean_absolute_paired_delta": self.mean_absolute_paired_delta,
            "paired_delta_interval": self.paired_delta_interval.as_dict(),
            "absolute_tolerance": self.absolute_tolerance,
            "contract_passed": self.contract_passed,
        }


@dataclass(frozen=True, slots=True)
class NegativeControlValidation:
    reference_policy_id: str
    negative_control_policy_id: str
    draw_count: int
    fields: Mapping[str, NegativeControlFieldResult]
    contract_passed: bool
    evidence_status: str = EVIDENCE_STATUS

    def as_dict(self) -> dict[str, Any]:
        return {
            "reference_policy_id": self.reference_policy_id,
            "negative_control_policy_id": self.negative_control_policy_id,
            "draw_count": self.draw_count,
            "fields": {
                key: value.as_dict() for key, value in self.fields.items()
            },
            "contract_passed": self.contract_passed,
            "evidence_status": self.evidence_status,
        }


def _validated_outcome_fields(fields: Sequence[str]) -> tuple[str, ...]:
    if isinstance(fields, (str, bytes)):
        raise ValueError("outcome_fields must be a sequence")
    materialized = tuple(fields)
    if not materialized:
        raise ValueError("at least one outcome field is required")
    unknown = sorted(set(materialized) - set(OUTCOME_FIELDS))
    if unknown:
        raise ValueError(f"unknown outcome fields: {unknown}")
    if len(set(materialized)) != len(materialized):
        raise ValueError("outcome fields must be unique")
    return materialized


def _field_tolerances(
    value: float | Mapping[str, float],
    fields: Sequence[str],
) -> dict[str, float]:
    if isinstance(value, Mapping):
        if set(value) != set(fields):
            raise ValueError("absolute_tolerances must exactly cover outcome_fields")
        return {
            field_name: _finite_nonnegative(value[field_name], field_name)
            for field_name in fields
        }
    tolerance = _finite_nonnegative(value, "absolute_tolerances")
    return {field_name: tolerance for field_name in fields}


def validate_negative_control(
    rows: Iterable[PolicyOutcomeDraw],
    *,
    reference_policy_id: str,
    negative_control_policy_id: str,
    opening_history: OpeningHistoryCommitment,
    outcome_fields: Sequence[str] = DEFAULT_NEGATIVE_CONTROL_FIELDS,
    absolute_tolerances: float | Mapping[str, float] = 0.0,
    interval_probability: float = 0.90,
) -> NegativeControlValidation:
    """Check paired no-effect invariance without making a realism claim.

    A field passes only when mean absolute paired difference is within its
    tolerance. Positive and negative implementation errors therefore cannot
    cancel one another in the panel mean.
    """

    _validate_probability(interval_probability, "interval_probability")
    selected_fields = _validated_outcome_fields(outcome_fields)
    tolerances = _field_tolerances(absolute_tolerances, selected_fields)
    policies = _validated_policy_ids(
        (reference_policy_id, negative_control_policy_id)
    )
    indexed = _balanced_panel(
        rows,
        policies,
        opening_history,
        allow_unrequested_policies=True,
    )
    keys = tuple(sorted(indexed[reference_policy_id]))

    results: dict[str, NegativeControlFieldResult] = {}
    for field_name in selected_fields:
        reference_values = [
            float(getattr(indexed[reference_policy_id][key].outcomes, field_name))
            for key in keys
        ]
        control_values = [
            float(
                getattr(
                    indexed[negative_control_policy_id][key].outcomes,
                    field_name,
                )
            )
            for key in keys
        ]
        deltas = [
            control - reference
            for control, reference in zip(
                control_values,
                reference_values,
                strict=True,
            )
        ]
        mean_absolute_delta = _mean([abs(value) for value in deltas])
        tolerance = tolerances[field_name]
        results[field_name] = NegativeControlFieldResult(
            outcome_name=field_name,
            reference_mean=_mean(reference_values),
            negative_control_mean=_mean(control_values),
            mean_paired_delta=_mean(deltas),
            mean_absolute_paired_delta=mean_absolute_delta,
            paired_delta_interval=_interval(deltas, interval_probability),
            absolute_tolerance=tolerance,
            contract_passed=mean_absolute_delta <= tolerance + 1e-12,
        )
    return NegativeControlValidation(
        reference_policy_id=reference_policy_id,
        negative_control_policy_id=negative_control_policy_id,
        draw_count=len(keys),
        fields=MappingProxyType(results),
        contract_passed=all(result.contract_passed for result in results.values()),
    )


@dataclass(frozen=True, slots=True)
class DoseResponseExpectation:
    """A preregistrable monotonic expectation for one outcome component."""

    outcome_name: str
    direction: str
    tolerance: float = 0.0
    minimum_paired_consistency: float = 1.0

    def __post_init__(self) -> None:
        if self.outcome_name not in OUTCOME_FIELDS:
            raise ValueError(f"unknown outcome field: {self.outcome_name}")
        if self.direction not in {"nonincreasing", "nondecreasing"}:
            raise ValueError(
                "direction must be 'nonincreasing' or 'nondecreasing'"
            )
        _finite_nonnegative(self.tolerance, "tolerance")
        if (
            isinstance(self.minimum_paired_consistency, bool)
            or not isinstance(self.minimum_paired_consistency, (int, float))
            or not math.isfinite(float(self.minimum_paired_consistency))
            or not 0.0 <= float(self.minimum_paired_consistency) <= 1.0
        ):
            raise ValueError("minimum_paired_consistency must be in [0, 1]")


@dataclass(frozen=True, slots=True)
class AdjacentDoseResult:
    lower_dose_policy_id: str
    higher_dose_policy_id: str
    mean_delta_higher_minus_lower: float
    paired_consistency: float
    mean_direction_passed: bool
    consistency_passed: bool
    contract_passed: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "lower_dose_policy_id": self.lower_dose_policy_id,
            "higher_dose_policy_id": self.higher_dose_policy_id,
            "mean_delta_higher_minus_lower": self.mean_delta_higher_minus_lower,
            "paired_consistency": self.paired_consistency,
            "mean_direction_passed": self.mean_direction_passed,
            "consistency_passed": self.consistency_passed,
            "contract_passed": self.contract_passed,
        }


@dataclass(frozen=True, slots=True)
class DoseResponseFieldResult:
    expectation: DoseResponseExpectation
    policy_means: Mapping[str, float]
    adjacent_comparisons: tuple[AdjacentDoseResult, ...]
    contract_passed: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "expectation": {
                "outcome_name": self.expectation.outcome_name,
                "direction": self.expectation.direction,
                "tolerance": self.expectation.tolerance,
                "minimum_paired_consistency": (
                    self.expectation.minimum_paired_consistency
                ),
            },
            "policy_means": dict(self.policy_means),
            "adjacent_comparisons": [
                result.as_dict() for result in self.adjacent_comparisons
            ],
            "contract_passed": self.contract_passed,
        }


@dataclass(frozen=True, slots=True)
class DoseResponseValidation:
    ordered_policy_ids: tuple[str, ...]
    draw_count: int
    fields: Mapping[str, DoseResponseFieldResult]
    contract_passed: bool
    evidence_status: str = EVIDENCE_STATUS

    def as_dict(self) -> dict[str, Any]:
        return {
            "ordered_policy_ids": list(self.ordered_policy_ids),
            "draw_count": self.draw_count,
            "fields": {
                key: value.as_dict() for key, value in self.fields.items()
            },
            "contract_passed": self.contract_passed,
            "evidence_status": self.evidence_status,
        }


def validate_dose_response(
    rows: Iterable[PolicyOutcomeDraw],
    *,
    ordered_policy_ids: Sequence[str],
    expectations: Sequence[DoseResponseExpectation],
    opening_history: OpeningHistoryCommitment,
) -> DoseResponseValidation:
    """Check preregistered monotonic outcomes across paired policy doses."""

    policies = _validated_policy_ids(ordered_policy_ids)
    if len(policies) < 2:
        raise ValueError("dose-response validation requires at least two doses")
    materialized_expectations = tuple(expectations)
    if not materialized_expectations or not all(
        isinstance(expectation, DoseResponseExpectation)
        for expectation in materialized_expectations
    ):
        raise ValueError("at least one valid dose-response expectation is required")
    field_names = [
        expectation.outcome_name
        for expectation in materialized_expectations
    ]
    if len(set(field_names)) != len(field_names):
        raise ValueError("dose-response outcome expectations must be unique")

    indexed = _balanced_panel(
        rows,
        policies,
        opening_history,
        allow_unrequested_policies=True,
    )
    keys = tuple(sorted(indexed[policies[0]]))
    field_results: dict[str, DoseResponseFieldResult] = {}
    for expectation in materialized_expectations:
        values = {
            policy_id: [
                float(
                    getattr(
                        indexed[policy_id][key].outcomes,
                        expectation.outcome_name,
                    )
                )
                for key in keys
            ]
            for policy_id in policies
        }
        means = {
            policy_id: _mean(policy_values)
            for policy_id, policy_values in values.items()
        }
        adjacent: list[AdjacentDoseResult] = []
        for lower_policy, higher_policy in pairwise(policies):
            deltas = [
                higher - lower
                for higher, lower in zip(
                    values[higher_policy],
                    values[lower_policy],
                    strict=True,
                )
            ]
            if expectation.direction == "nonincreasing":
                checks = [delta <= expectation.tolerance for delta in deltas]
                mean_passed = _mean(deltas) <= expectation.tolerance
            else:
                checks = [delta >= -expectation.tolerance for delta in deltas]
                mean_passed = _mean(deltas) >= -expectation.tolerance
            consistency = sum(checks) / len(checks)
            consistency_passed = (
                consistency + 1e-12 >= expectation.minimum_paired_consistency
            )
            adjacent.append(
                AdjacentDoseResult(
                    lower_dose_policy_id=lower_policy,
                    higher_dose_policy_id=higher_policy,
                    mean_delta_higher_minus_lower=_mean(deltas),
                    paired_consistency=consistency,
                    mean_direction_passed=mean_passed,
                    consistency_passed=consistency_passed,
                    contract_passed=mean_passed and consistency_passed,
                )
            )
        result = DoseResponseFieldResult(
            expectation=expectation,
            policy_means=MappingProxyType(means),
            adjacent_comparisons=tuple(adjacent),
            contract_passed=all(item.contract_passed for item in adjacent),
        )
        field_results[expectation.outcome_name] = result

    return DoseResponseValidation(
        ordered_policy_ids=policies,
        draw_count=len(keys),
        fields=MappingProxyType(field_results),
        contract_passed=all(
            result.contract_passed for result in field_results.values()
        ),
    )
