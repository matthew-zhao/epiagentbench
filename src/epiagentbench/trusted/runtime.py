"""Trusted lifecycle contract for static and interactive episodes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..models import EpisodeBundle, Observation, Oracle, PublicEpisode


@dataclass(frozen=True)
class RuntimeInterventionReceipt:
    """Trusted result of attempting to change a running episode."""

    status: str
    intervention_id: str | None
    effective_at_minute: int | None
    level: str
    observations: tuple[Observation, ...] = tuple()


class EpisodeRuntime(Protocol):
    """Private mutable-world seam used by the trusted evaluator."""

    @property
    def public_episode(self) -> PublicEpisode:
        """Return the episode artifacts safe to expose to an agent."""

    @property
    def canary_tokens(self) -> tuple[str, ...]:
        """Return evaluator-only canaries used for leakage detection."""

    def advance_to(self, public_minute: int) -> tuple[Observation, ...]:
        """Advance the latent world and return newly available observations."""

    def apply_institution_control(
        self,
        level: str,
        target_id: str | None,
        public_minute: int,
    ) -> RuntimeInterventionReceipt:
        """Attempt to set institution-wide transmission control."""

    def apply_response_control(
        self,
        action_type: str,
        level: str,
        target_id: str,
        public_minute: int,
    ) -> RuntimeInterventionReceipt:
        """Attempt to set one catalog-declared response control."""

    def finalize(self) -> Oracle:
        """Freeze and return the evaluator-only oracle for scoring."""

    def close(self) -> None:
        """Release resources owned by the runtime."""


class StaticEpisodeRuntime:
    """Compatibility runtime for an already-generated immutable episode."""

    def __init__(self, bundle: EpisodeBundle) -> None:
        self._bundle = bundle

    @property
    def public_episode(self) -> PublicEpisode:
        return self._bundle.public

    @property
    def canary_tokens(self) -> tuple[str, ...]:
        return self._bundle.oracle.canary_tokens

    def advance_to(self, public_minute: int) -> tuple[Observation, ...]:
        del public_minute
        return ()

    def apply_institution_control(
        self,
        level: str,
        target_id: str | None,
        public_minute: int,
    ) -> RuntimeInterventionReceipt:
        del target_id, public_minute
        return RuntimeInterventionReceipt(
            status="unsupported",
            intervention_id=None,
            effective_at_minute=None,
            level=level,
        )

    def apply_response_control(
        self,
        action_type: str,
        level: str,
        target_id: str,
        public_minute: int,
    ) -> RuntimeInterventionReceipt:
        del action_type, target_id, public_minute
        return RuntimeInterventionReceipt(
            status="unsupported",
            intervention_id=None,
            effective_at_minute=None,
            level=level,
        )

    def finalize(self) -> Oracle:
        return self._bundle.oracle

    def close(self) -> None:
        return None
