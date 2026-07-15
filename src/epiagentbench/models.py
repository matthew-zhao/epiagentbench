from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class Budget:
    tool_calls: int = 50
    analyst_minutes: int = 720
    operational_credits: int = 100
    privacy_units: int = 30

    def as_dict(self) -> dict[str, int]:
        return {
            "tool_calls": self.tool_calls,
            "analyst_minutes": self.analyst_minutes,
            "operational_credits": self.operational_credits,
            "privacy_units": self.privacy_units,
        }


@dataclass(frozen=True)
class Observation:
    observation_id: str
    kind: str
    subject_id: str | None
    available_minute: int
    release_key: str
    payload: Mapping[str, Any]

    def public_dict(self) -> dict[str, Any]:
        return {
            "observation_id": self.observation_id,
            "kind": self.kind,
            "subject_id": self.subject_id,
            "available_minute": self.available_minute,
            "payload": dict(self.payload),
        }


@dataclass(frozen=True)
class PublicEpisode:
    manifest: Mapping[str, Any]
    observations: tuple[Observation, ...]


@dataclass(frozen=True)
class Oracle:
    family: str
    is_outbreak: bool
    true_case_ids: frozenset[str]
    explanation_type: str
    source_id: str | None
    decisive_evidence_ids: frozenset[str]
    action_utilities: Mapping[tuple[str, str | None], float]
    canary_tokens: tuple[str, ...] = ()
    # Starsim-backed episodes may preregister utilities at several decision
    # times.  Values are computed from common-random-number counterfactuals,
    # rather than authored per episode.  The static mapping above remains the
    # compatibility path for reference fixtures.
    action_utility_curves: Mapping[
        tuple[str, str | None], tuple[tuple[int, float], ...]
    ] = field(default_factory=dict)
    counterfactual_metrics: Mapping[str, float | int | str] = field(
        default_factory=dict
    )
    # Closed-loop episodes may score forecasts that were committed before
    # their outcome window.  Only the trusted scorer receives these timestamps.
    forecast_event_minutes: tuple[int, ...] = ()
    forecast_horizon_minutes: int = 0
    forecast_minimum_submissions: int = 0
    # Follow-up gold is action-dependent but is scored only when at least one
    # associated public record was actually returned to the agent.
    followup_true_case_observation_ids: Mapping[
        str, tuple[str, ...]
    ] = field(default_factory=dict)
    followup_relevant_evidence_ids: frozenset[str] = field(
        default_factory=frozenset
    )


@dataclass(frozen=True)
class EpisodeBundle:
    public: PublicEpisode
    oracle: Oracle


@dataclass(frozen=True)
class LedgerEntry:
    sequence: int
    simulated_minute: int
    tool: str
    arguments: Mapping[str, Any]
    result_ids: tuple[str, ...] = ()
    analyst_minutes: int = 0
    operational_credits: int = 0
    privacy_units: int = 0
    status: str = "ok"
    violation: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "simulated_minute": self.simulated_minute,
            "tool": self.tool,
            "arguments": dict(self.arguments),
            "result_ids": list(self.result_ids),
            "analyst_minutes": self.analyst_minutes,
            "operational_credits": self.operational_credits,
            "privacy_units": self.privacy_units,
            "status": self.status,
            "violation": self.violation,
        }


@dataclass(frozen=True)
class Scorecard:
    valid: bool
    total: float
    dimensions: Mapping[str, float]
    metrics: Mapping[str, float | int | bool | str]
    violations: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "total": round(self.total, 3),
            "dimensions": {
                key: round(value, 3) for key, value in self.dimensions.items()
            },
            "metrics": dict(self.metrics),
            "violations": list(self.violations),
        }
