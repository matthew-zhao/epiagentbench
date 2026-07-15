"""Public, untrusted-side client for an EpiAgentBench episode.

This package intentionally has no dependency on the trusted evaluator package.
The only data crossing the boundary are newline-delimited JSON values.
"""

from .client import (
    ClientClosedError,
    InvestigationClient,
    InvestigationClientError,
    ProtocolError,
    RemoteRequestError,
    RequestError,
)

__all__ = [
    "ClientClosedError",
    "InvestigationClient",
    "InvestigationClientError",
    "ProtocolError",
    "RemoteRequestError",
    "RequestError",
]
