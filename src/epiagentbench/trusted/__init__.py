"""Trusted evaluator components.

Nothing in this package belongs in the untrusted agent image.  The public
client lives in the separate :mod:`epiagentbench_client` package.
"""

from .backend import EpisodeBackend, ReferenceEpisodeBackend
from .service import (
    SecureEpisodeSession,
    launch_secure_episode,
    launch_socket_episode,
)

__all__ = [
    "EpisodeBackend",
    "ReferenceEpisodeBackend",
    "SecureEpisodeSession",
    "launch_secure_episode",
    "launch_socket_episode",
]
