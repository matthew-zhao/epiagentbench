"""Private latent-world backend contracts."""

from __future__ import annotations

from typing import Protocol

from ..models import EpisodeBundle
from ..scenario import generate_episode
from .runtime import EpisodeRuntime, StaticEpisodeRuntime


class EpisodeBackend(Protocol):
    """Build one complete private episode inside the trusted process."""

    def create_runtime(
        self,
        *,
        seed: int,
        family: str | None,
        presentation_key: bytes | None = None,
    ) -> EpisodeRuntime:
        """Return a trusted runtime for a static or interactive episode."""

    def create_episode(
        self,
        *,
        seed: int,
        family: str | None,
        presentation_key: bytes | None = None,
    ) -> EpisodeBundle:
        """Return public artifacts plus an oracle that never crosses the wire."""


class ReferenceEpisodeBackend:
    """Adapter for the compact deterministic development generator."""

    def create_runtime(
        self,
        *,
        seed: int,
        family: str | None,
        presentation_key: bytes | None = None,
    ) -> EpisodeRuntime:
        return StaticEpisodeRuntime(
            self.create_episode(
                seed=seed,
                family=family,
                presentation_key=presentation_key,
            )
        )

    def create_episode(
        self,
        *,
        seed: int,
        family: str | None,
        presentation_key: bytes | None = None,
    ) -> EpisodeBundle:
        return generate_episode(
            seed=seed,
            family=family,
            presentation_key=presentation_key,
        )


def build_backend(name: str) -> EpisodeBackend:
    """Resolve an evaluator-side backend without importing it in the client."""

    if name == "reference":
        return ReferenceEpisodeBackend()
    if name == "starsim":
        # Keep the optional dependency and scientific generator evaluator-only.
        from .starsim_episode import StarsimSurveillanceBackend

        return StarsimSurveillanceBackend()
    if name == "starsim-ltc-v3":
        # The role-aware LTC engine and raw facility trace remain evaluator-only.
        from .ltc_closed_loop import LtcStarsimV3Backend

        return LtcStarsimV3Backend()
    raise ValueError("Unknown evaluator backend")
