"""Dependency-light contracts for trusted disease-simulation backends.

These types are intentionally separate from the public observation models.
They may contain latent state and raw simulator identifiers and must never be
returned directly to an evaluated agent.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class EngineError(RuntimeError):
    """Base error raised by a trusted disease engine."""


class EngineClosedError(EngineError):
    """Raised when a caller tries to use an engine after closing it."""


class UnsupportedControlError(EngineError):
    """Raised when a backend cannot apply a requested control."""


@dataclass(frozen=True, slots=True)
class EngineControl:
    """A trusted, scheduled control that can alter future transmission.

    Backends must explicitly allow-list ``kind`` values.  ``magnitude`` has
    backend-specific semantics; the reference Starsim adapter supports only a
    cumulative global transmission multiplier in the closed interval [0, 1].
    """

    control_id: str
    kind: str
    effective_minute: int
    magnitude: float
    target_id: str | None = None


@dataclass(frozen=True, slots=True)
class LatentState:
    """A compact trusted state summary at a simulation boundary."""

    minute: int
    population_size: int
    alive_count: int
    susceptible_count: int
    infected_count: int
    recovered_count: int
    dead_count: int


@dataclass(frozen=True, slots=True)
class EngineDelta:
    """Trusted state changes produced by a monotonic advance."""

    start_minute: int
    end_minute: int
    states: tuple[LatentState, ...]
    applied_control_ids: tuple[str, ...]
    terminal: bool


@dataclass(frozen=True, slots=True)
class TransmissionEvent:
    """One detached infection event from a trusted simulator.

    ``source_agent_id`` is ``None`` for an exogenous/seed infection.  Simulator
    UIDs remain trusted-only and must be replaced with presentation IDs before
    anything derived from an event is returned to an evaluated agent.

    ``mechanism`` is evaluator-only provenance.  The dependency-light default
    is deliberately ``"unspecified"`` so existing/custom backends do not
    accidentally claim a route they did not establish.  Concrete adapters may
    use a stricter vocabulary, such as ``"seed"``, ``"person_to_person"``,
    ``"common_source"``, and ``"importation"``.
    """

    target_agent_id: int
    source_agent_id: int | None
    infection_minute: int
    mechanism: str = "unspecified"


@dataclass(frozen=True, slots=True)
class OracleSnapshot:
    """Trusted-only oracle state, detached from simulator-owned objects."""

    minute: int
    terminal: bool
    population_size: int
    alive_agent_ids: tuple[int, ...]
    ever_infected_agent_ids: tuple[int, ...]
    currently_infected_agent_ids: tuple[int, ...]
    recovered_agent_ids: tuple[int, ...]
    dead_agent_ids: tuple[int, ...]
    applied_control_ids: tuple[str, ...]
    transmission_events: tuple[TransmissionEvent, ...]


@dataclass(frozen=True, slots=True)
class PrivateEngineMetadata:
    """Reproducibility metadata that must stay in the evaluator process."""

    backend_name: str
    backend_version: str
    timestep_minutes: int
    configuration_sha256: str


@runtime_checkable
class DiseaseEngine(Protocol):
    """Minimal contract implemented by trusted disease engines."""

    @property
    def current_minute(self) -> int:
        """Current logical time relative to the start of the episode."""

    @property
    def terminal(self) -> bool:
        """Whether the configured simulation horizon has been processed."""

    @property
    def private_metadata(self) -> PrivateEngineMetadata:
        """Return evaluator-only backend and reproducibility metadata."""

    def apply_control(self, control: EngineControl) -> None:
        """Schedule a validated control without exposing simulator state."""

    def advance_to(self, target_minute: int) -> EngineDelta:
        """Advance monotonically to a supported simulation boundary."""

    def oracle_snapshot(self) -> OracleSnapshot:
        """Return a trusted snapshot made only from detached Python values."""

    def close(self) -> None:
        """Release simulator-owned state and make mutation methods unusable."""
