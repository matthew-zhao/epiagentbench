"""Small JSON-only framing layer for trusted evaluator sockets."""

from __future__ import annotations

import json
import socket
from typing import Any, NoReturn


PROTOCOL_VERSION = "1.0"
MAX_MESSAGE_BYTES = 1_048_576
_RECV_CHUNK_BYTES = 65_536


class WireError(RuntimeError):
    """A malformed or unavailable JSON channel."""


class JsonSocket:
    """Newline-delimited JSON over a connected Unix stream socket."""

    def __init__(self, connected_socket: socket.socket):
        self._socket = connected_socket
        self._buffer = bytearray()

    def receive(self) -> Any:
        frame = self._read_frame()
        try:
            return json.loads(
                frame.decode("utf-8"),
                object_pairs_hook=_unique_object,
                parse_constant=_reject_constant,
            )
        except (UnicodeDecodeError, ValueError, RecursionError):
            raise WireError("invalid message") from None

    def send(self, value: Any) -> bytes:
        try:
            payload = json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        except (TypeError, ValueError, OverflowError, RecursionError):
            raise WireError("invalid message") from None
        if not payload or len(payload) > MAX_MESSAGE_BYTES:
            raise WireError("invalid message")
        try:
            self._socket.sendall(payload + b"\n")
        except OSError:
            raise WireError("channel unavailable") from None
        return payload

    def close(self) -> None:
        try:
            self._socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self._socket.close()

    def _read_frame(self) -> bytes:
        while True:
            delimiter = self._buffer.find(b"\n")
            if delimiter >= 0:
                if delimiter == 0 or delimiter > MAX_MESSAGE_BYTES:
                    raise WireError("invalid message")
                frame = bytes(self._buffer[:delimiter])
                del self._buffer[: delimiter + 1]
                return frame
            if len(self._buffer) > MAX_MESSAGE_BYTES:
                raise WireError("invalid message")
            try:
                chunk = self._socket.recv(_RECV_CHUNK_BYTES)
            except OSError:
                raise WireError("channel unavailable") from None
            if not chunk:
                raise WireError("channel unavailable")
            self._buffer.extend(chunk)


def canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError):
        raise WireError("invalid message") from None


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _reject_constant(_: str) -> NoReturn:
    raise ValueError("invalid numeric constant")
