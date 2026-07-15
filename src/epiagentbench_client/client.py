"""Synchronous JSON-RPC client for the investigator-facing socket.

The client contains no simulator, oracle, scorer, or episode-generation code.
It is therefore safe to place this module in the untrusted agent image.  The
trusted service remains responsible for authorization and response sanitation;
Python object privacy is not treated as a security boundary.
"""

from __future__ import annotations

from copy import deepcopy
import json
import os
import socket
from threading import Lock
from typing import Any, NoReturn


_PROTOCOL_VERSION = "1.0"
_MAX_MESSAGE_BYTES = 1_048_576
_RECV_CHUNK_BYTES = 65_536


class InvestigationClientError(RuntimeError):
    """Base class for fixed, non-sensitive client errors."""


class ClientClosedError(InvestigationClientError):
    """Raised when an operation is attempted on a closed client."""


class RequestError(InvestigationClientError):
    """Raised when a request cannot be represented by the public protocol."""


class RemoteRequestError(InvestigationClientError):
    """Raised when the trusted service rejects a request."""


class ProtocolError(InvestigationClientError):
    """Raised when the peer violates the public wire protocol."""


class InvestigationClient:
    """Blocking investigator API over an already-connected Unix socket.

    Calls are serialized, so a client can be shared by cooperating threads.
    The first access to :attr:`manifest` or :meth:`initial_observations` sends a
    single ``start`` request and caches its public result.
    """

    def __init__(self, connected_socket: socket.socket):
        _validate_socket(connected_socket)
        self._socket = connected_socket
        self._receive_buffer = bytearray()
        self._next_request_id = 1
        self._lock = Lock()
        self._closed = False
        self._manifest: dict[str, Any] | None = None
        self._initial: list[dict[str, Any]] | None = None

    @classmethod
    def from_fd(cls, fd: int) -> InvestigationClient:
        """Construct from a duplicate of a connected Unix-socket descriptor.

        Duplicating the descriptor makes ownership explicit: closing this
        client never closes the caller's original descriptor.  The duplicate
        is also marked non-inheritable before it is wrapped as a socket.
        """

        if type(fd) is not int or fd < 0:
            raise RequestError("Invalid investigation request.")
        try:
            duplicate = os.dup(fd)
            os.set_inheritable(duplicate, False)
        except OSError:
            raise RequestError("Invalid investigation request.") from None

        connected_socket: socket.socket | None = None
        try:
            connected_socket = socket.socket(fileno=duplicate)
            duplicate = -1  # Ownership moved to connected_socket.
            return cls(connected_socket)
        except Exception:
            if connected_socket is not None:
                connected_socket.close()
            elif duplicate >= 0:
                try:
                    os.close(duplicate)
                except OSError:
                    pass
            raise RequestError("Invalid investigation request.") from None

    @classmethod
    def connect_unix(cls, path: str) -> InvestigationClient:
        """Connect to a mounted public broker socket by pathname."""

        if (
            not isinstance(path, str)
            or not path
            or len(path.encode("utf-8")) > 100
        ):
            raise RequestError("Invalid investigation request.")
        connected_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            connected_socket.connect(path)
            return cls(connected_socket)
        except Exception:
            connected_socket.close()
            raise InvestigationClientError(
                "Investigation service unavailable."
            ) from None

    @classmethod
    def from_environment(cls) -> InvestigationClient:
        """Connect using the non-secret ``EPIAGENT_SOCKET`` contract variable."""

        path = os.environ.get("EPIAGENT_SOCKET")
        if path is None:
            raise RequestError("Invalid investigation request.")
        return cls.connect_unix(path)

    @property
    def manifest(self) -> dict[str, Any]:
        """Return a copy of the public episode manifest."""

        with self._lock:
            self._ensure_started_locked()
            assert self._manifest is not None
            return deepcopy(self._manifest)

    def initial_observations(self) -> list[dict[str, Any]]:
        """Start the episode if necessary and return its initial records."""

        with self._lock:
            self._ensure_started_locked()
            assert self._initial is not None
            return deepcopy(self._initial)

    def search_observations(
        self, kind: str | None = None, **filters: Any
    ) -> list[dict[str, Any]]:
        if kind is not None and not isinstance(kind, str):
            raise RequestError("Invalid investigation request.")
        result = self._request(
            "search_observations", {"kind": kind, "filters": filters}
        )
        return _require_record_list(result)

    def request_interview(self, patient_id: str) -> dict[str, Any]:
        _require_string(patient_id)
        result = self._request("request_interview", {"patient_id": patient_id})
        return _require_record(result)

    def order_confirmatory_test(self, patient_id: str) -> dict[str, Any]:
        _require_string(patient_id)
        result = self._request(
            "order_confirmatory_test", {"patient_id": patient_id}
        )
        return _require_record(result)

    def request_inspection(self, target_id: str) -> dict[str, Any]:
        """Request a fixed inspection report for a public control target."""

        _require_string(target_id)
        result = self._request(
            "request_inspection", {"target_id": target_id}
        )
        return _require_record(result)

    def advance_time(self, minutes: int) -> list[dict[str, Any]]:
        if type(minutes) is not int or minutes <= 0:
            raise RequestError("Invalid investigation request.")
        result = self._request("advance_time", {"minutes": minutes})
        return _require_record_list(result)

    def recommend_action(
        self,
        action_type: str,
        target_id: str | None,
        evidence_ids: list[str] | tuple[str, ...],
    ) -> dict[str, Any]:
        _require_string(action_type)
        if target_id is not None:
            _require_string(target_id)
        if not isinstance(evidence_ids, (list, tuple)) or any(
            not isinstance(evidence_id, str) for evidence_id in evidence_ids
        ):
            raise RequestError("Invalid investigation request.")
        result = self._request(
            "recommend_action",
            {
                "action_type": action_type,
                "target_id": target_id,
                "evidence_ids": list(evidence_ids),
            },
        )
        return _require_record(result)

    def set_institution_control(
        self,
        level: str,
        target_id: str,
        evidence_ids: list[str] | tuple[str, ...],
    ) -> dict[str, Any]:
        """Schedule a declared institution-wide control level.

        The public API accepts only named operational levels. Biological
        effect sizes and simulator parameters remain evaluator-private.
        """

        if level not in {"off", "standard", "intensive"}:
            raise RequestError("Invalid investigation request.")
        _require_string(target_id)
        if not isinstance(evidence_ids, (list, tuple)) or any(
            not isinstance(evidence_id, str) for evidence_id in evidence_ids
        ):
            raise RequestError("Invalid investigation request.")
        result = self._request(
            "set_institution_control",
            {
                "level": level,
                "target_id": target_id,
                "evidence_ids": list(evidence_ids),
            },
        )
        return _require_record(result)

    def set_response_control(
        self,
        action_type: str,
        level: str,
        target_id: str,
        evidence_ids: list[str] | tuple[str, ...],
    ) -> dict[str, Any]:
        """Schedule a public, catalog-declared response control."""

        if action_type not in {
            "infection_control",
            "source_control",
            "entry_control",
            "audit_reporting",
        } or level not in {"off", "standard", "intensive"}:
            raise RequestError("Invalid investigation request.")
        _require_string(target_id)
        if not isinstance(evidence_ids, (list, tuple)) or any(
            not isinstance(evidence_id, str) for evidence_id in evidence_ids
        ):
            raise RequestError("Invalid investigation request.")
        result = self._request(
            "set_response_control",
            {
                "action_type": action_type,
                "level": level,
                "target_id": target_id,
                "evidence_ids": list(evidence_ids),
            },
        )
        return _require_record(result)

    def submit_forecast(self, expected_new_encounters: int) -> dict[str, Any]:
        """Commit a forecast for new encounters in the declared horizon."""

        if type(expected_new_encounters) is not int or not (
            0 <= expected_new_encounters <= 10_000
        ):
            raise RequestError("Invalid investigation request.")
        result = self._request(
            "submit_forecast",
            {"expected_new_encounters": expected_new_encounters},
        )
        return _require_record(result)

    def get_clock_and_budget(self) -> dict[str, Any]:
        return _require_record(self._request("get_clock_and_budget", {}))

    def close(self) -> None:
        """Close the public channel without sending a privileged operation."""

        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._receive_buffer.clear()
            self._socket.close()

    def __enter__(self) -> InvestigationClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _ensure_started_locked(self) -> None:
        if self._manifest is not None:
            return
        result = self._request_locked("start", {})
        record = _require_record(result)
        manifest = record.get("manifest")
        observations = record.get("observations")
        if not isinstance(manifest, dict):
            self._protocol_failure()
        initial = _require_record_list(observations)
        self._manifest = deepcopy(manifest)
        self._initial = deepcopy(initial)

    def _request(self, method: str, params: dict[str, Any]) -> Any:
        with self._lock:
            return self._request_locked(method, params)

    def _request_locked(self, method: str, params: dict[str, Any]) -> Any:
        if self._closed:
            raise ClientClosedError("Investigation client is closed.")

        request_id = self._next_request_id
        self._next_request_id += 1
        request = {
            "version": _PROTOCOL_VERSION,
            "id": request_id,
            "method": method,
            "params": params,
        }
        try:
            encoded = json.dumps(
                request,
                allow_nan=False,
                ensure_ascii=True,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError, OverflowError, RecursionError):
            raise RequestError("Invalid investigation request.") from None
        if len(encoded) > _MAX_MESSAGE_BYTES:
            raise RequestError("Invalid investigation request.")

        try:
            self._socket.sendall(encoded + b"\n")
            response_bytes = self._read_frame_locked()
        except OSError:
            self._close_after_failure_locked()
            raise InvestigationClientError(
                "Investigation service unavailable."
            ) from None

        try:
            response = json.loads(
                response_bytes.decode("utf-8"),
                object_pairs_hook=_unique_object,
                parse_constant=_reject_json_constant,
            )
        except (UnicodeDecodeError, ValueError, RecursionError):
            self._close_after_failure_locked()
            raise ProtocolError(
                "Invalid response from investigation service."
            ) from None

        if (
            not isinstance(response, dict)
            or response.get("version") != _PROTOCOL_VERSION
            or type(response.get("id")) is not int
            or response["id"] != request_id
            or type(response.get("ok")) is not bool
        ):
            self._protocol_failure()
        if response["ok"] is False:
            raise RemoteRequestError("Investigation request rejected.")
        if "result" not in response:
            self._protocol_failure()
        return response["result"]

    def _read_frame_locked(self) -> bytes:
        while True:
            delimiter = self._receive_buffer.find(b"\n")
            if delimiter >= 0:
                if delimiter > _MAX_MESSAGE_BYTES:
                    self._protocol_failure()
                frame = bytes(self._receive_buffer[:delimiter])
                del self._receive_buffer[: delimiter + 1]
                if not frame:
                    self._protocol_failure()
                return frame

            if len(self._receive_buffer) > _MAX_MESSAGE_BYTES:
                self._protocol_failure()
            chunk = self._socket.recv(_RECV_CHUNK_BYTES)
            if not chunk:
                self._close_after_failure_locked()
                raise InvestigationClientError(
                    "Investigation service unavailable."
                )
            self._receive_buffer.extend(chunk)

    def _protocol_failure(self) -> NoReturn:
        self._close_after_failure_locked()
        raise ProtocolError("Invalid response from investigation service.")

    def _close_after_failure_locked(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._receive_buffer.clear()
        self._socket.close()


def _validate_socket(connected_socket: socket.socket) -> None:
    if not isinstance(connected_socket, socket.socket):
        raise RequestError("Invalid investigation request.")
    if connected_socket.family != socket.AF_UNIX:
        raise RequestError("Invalid investigation request.")
    if (connected_socket.type & 0xF) != socket.SOCK_STREAM:
        raise RequestError("Invalid investigation request.")
    try:
        connected_socket.getpeername()
    except OSError:
        raise RequestError("Invalid investigation request.") from None


def _require_string(value: object) -> None:
    if not isinstance(value, str):
        raise RequestError("Invalid investigation request.")


def _require_record(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProtocolError("Invalid response from investigation service.")
    return deepcopy(value)


def _require_record_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(
        not isinstance(item, dict) for item in value
    ):
        raise ProtocolError("Invalid response from investigation service.")
    return deepcopy(value)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_json_constant(_: str) -> NoReturn:
    raise ValueError("invalid JSON numeric constant")
