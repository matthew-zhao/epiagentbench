"""Dependency-free MCP bridge for the public investigation client.

The server deliberately imports only the untrusted-side client package.  It
speaks one JSON-RPC 2.0 value per line on stdio and obtains its sole episode
capability from ``EPIAGENT_SOCKET``.
"""

from __future__ import annotations

import json
import sys
from typing import Any, BinaryIO, Iterator

from .client import InvestigationClient, InvestigationClientError


_MAX_MESSAGE_BYTES = 1_048_576
_READ_CHUNK_BYTES = 65_536
_TOO_LARGE = object()
_SERVER_NAME = "epiagentbench-investigation"
_SERVER_VERSION = "0.1.0"
_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")

_PARSE_ERROR = (-32700, "Parse error")
_INVALID_REQUEST = (-32600, "Invalid Request")
_METHOD_NOT_FOUND = (-32601, "Method not found")
_INVALID_PARAMS = (-32602, "Invalid params")
_INTERNAL_ERROR = (-32603, "Internal error")
_TOOL_ERROR_TEXT = "Tool execution failed."


def _object_schema(
    properties: dict[str, Any] | None = None,
    required: tuple[str, ...] = (),
) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties or {},
        "additionalProperties": False,
    }
    if required:
        schema["required"] = list(required)
    return schema


_STRING = {"type": "string", "minLength": 1}
_EVIDENCE_IDS = {"type": "array", "items": _STRING}
_LEVEL = {"type": "string", "enum": ["off", "standard", "intensive"]}
_ACTION_TYPE = {
    "type": "string",
    "enum": [
        "infection_control",
        "source_control",
        "entry_control",
        "audit_reporting",
    ],
}


TOOLS: tuple[dict[str, Any], ...] = (
    {
        "name": "get_manifest",
        "description": "Return the public episode manifest.",
        "inputSchema": _object_schema(),
    },
    {
        "name": "initial_observations",
        "description": "Start the episode and return initially released records.",
        "inputSchema": _object_schema(),
    },
    {
        "name": "search_observations",
        "description": "Search records released by the current public time.",
        "inputSchema": _object_schema(
            {
                "kind": {"type": ["string", "null"]},
                "filters": {"type": "object"},
            }
        ),
    },
    {
        "name": "request_interview",
        "description": "Request an interview for a public patient identifier.",
        "inputSchema": _object_schema({"patient_id": _STRING}, ("patient_id",)),
    },
    {
        "name": "order_confirmatory_test",
        "description": "Order a confirmatory test for a public patient identifier.",
        "inputSchema": _object_schema({"patient_id": _STRING}, ("patient_id",)),
    },
    {
        "name": "request_inspection",
        "description": "Request an inspection for a public control target.",
        "inputSchema": _object_schema({"target_id": _STRING}, ("target_id",)),
    },
    {
        "name": "advance_time",
        "description": "Advance the public investigation clock by positive minutes.",
        "inputSchema": _object_schema(
            {"minutes": {"type": "integer", "minimum": 1}}, ("minutes",)
        ),
    },
    {
        "name": "recommend_action",
        "description": (
            "Record an action recommendation supported by released evidence."
        ),
        "inputSchema": _object_schema(
            {
                "action_type": _STRING,
                "target_id": {"type": ["string", "null"]},
                "evidence_ids": _EVIDENCE_IDS,
            },
            ("action_type", "target_id", "evidence_ids"),
        ),
    },
    {
        "name": "set_institution_control",
        "description": "Set the legacy institution-wide control level.",
        "inputSchema": _object_schema(
            {"level": _LEVEL, "target_id": _STRING, "evidence_ids": _EVIDENCE_IDS},
            ("level", "target_id", "evidence_ids"),
        ),
    },
    {
        "name": "set_response_control",
        "description": "Set a catalog-declared response control level.",
        "inputSchema": _object_schema(
            {
                "action_type": _ACTION_TYPE,
                "level": _LEVEL,
                "target_id": _STRING,
                "evidence_ids": _EVIDENCE_IDS,
            },
            ("action_type", "level", "target_id", "evidence_ids"),
        ),
    },
    {
        "name": "submit_forecast",
        "description": "Commit a forecast for new encounters in the declared horizon.",
        "inputSchema": _object_schema(
            {
                "expected_new_encounters": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 10_000,
                }
            },
            ("expected_new_encounters",),
        ),
    },
    {
        "name": "get_clock_and_budget",
        "description": "Return the public clock, deadline, and remaining budget.",
        "inputSchema": _object_schema(),
    },
)

_READ_ONLY_TOOLS = {
    "get_manifest",
    "initial_observations",
    "search_observations",
    "get_clock_and_budget",
}
TOOLS = tuple(
    {
        **tool,
        "annotations": {
            "readOnlyHint": tool["name"] in _READ_ONLY_TOOLS,
            "destructiveHint": False,
            "openWorldHint": False,
        },
    }
    for tool in TOOLS
)

_TOOL_NAMES = frozenset(tool["name"] for tool in TOOLS)


class _InvalidToolArguments(ValueError):
    pass


def _require_exact(
    arguments: object, required: set[str], optional: set[str] | None = None
) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        raise _InvalidToolArguments
    allowed = required | (optional or set())
    if set(arguments) - allowed or not required.issubset(arguments):
        raise _InvalidToolArguments
    return arguments


def _string(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise _InvalidToolArguments
    return value


def _evidence_ids(value: object) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) for item in value
    ):
        raise _InvalidToolArguments
    return value


def _call_public_tool(
    client: InvestigationClient, name: str, arguments: object
) -> Any:
    if name == "get_manifest":
        _require_exact(arguments, set())
        return client.manifest
    if name == "initial_observations":
        _require_exact(arguments, set())
        return client.initial_observations()
    if name == "search_observations":
        args = _require_exact(arguments, set(), {"kind", "filters"})
        kind = args.get("kind")
        filters = args.get("filters", {})
        if kind is not None and not isinstance(kind, str):
            raise _InvalidToolArguments
        if not isinstance(filters, dict) or "kind" in filters:
            raise _InvalidToolArguments
        return client.search_observations(kind, **filters)
    if name in {"request_interview", "order_confirmatory_test"}:
        args = _require_exact(arguments, {"patient_id"})
        patient_id = _string(args["patient_id"])
        if name == "request_interview":
            return client.request_interview(patient_id)
        return client.order_confirmatory_test(patient_id)
    if name == "request_inspection":
        args = _require_exact(arguments, {"target_id"})
        return client.request_inspection(_string(args["target_id"]))
    if name == "advance_time":
        args = _require_exact(arguments, {"minutes"})
        minutes = args["minutes"]
        if type(minutes) is not int or minutes <= 0:
            raise _InvalidToolArguments
        return client.advance_time(minutes)
    if name == "recommend_action":
        args = _require_exact(
            arguments, {"action_type", "target_id", "evidence_ids"}
        )
        target_id = args["target_id"]
        if target_id is not None:
            target_id = _string(target_id)
        return client.recommend_action(
            _string(args["action_type"]),
            target_id,
            _evidence_ids(args["evidence_ids"]),
        )
    if name == "set_institution_control":
        args = _require_exact(arguments, {"level", "target_id", "evidence_ids"})
        level = args["level"]
        if level not in {"off", "standard", "intensive"}:
            raise _InvalidToolArguments
        return client.set_institution_control(
            level,
            _string(args["target_id"]),
            _evidence_ids(args["evidence_ids"]),
        )
    if name == "set_response_control":
        args = _require_exact(
            arguments, {"action_type", "level", "target_id", "evidence_ids"}
        )
        action_type = args["action_type"]
        level = args["level"]
        if action_type not in {
            "infection_control",
            "source_control",
            "entry_control",
            "audit_reporting",
        } or level not in {"off", "standard", "intensive"}:
            raise _InvalidToolArguments
        return client.set_response_control(
            action_type,
            level,
            _string(args["target_id"]),
            _evidence_ids(args["evidence_ids"]),
        )
    if name == "submit_forecast":
        args = _require_exact(arguments, {"expected_new_encounters"})
        expected = args["expected_new_encounters"]
        if type(expected) is not int or not 0 <= expected <= 10_000:
            raise _InvalidToolArguments
        return client.submit_forecast(expected)
    if name == "get_clock_and_budget":
        _require_exact(arguments, set())
        return client.get_clock_and_budget()
    raise _InvalidToolArguments


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _reject_constant(_: str) -> None:
    raise ValueError("invalid constant")


def _error(request_id: object, error: tuple[int, str]) -> dict[str, Any]:
    code, message = error
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def _result(request_id: object, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _tool_result(value: Any) -> dict[str, Any]:
    encoded = json.dumps(
        value, allow_nan=False, ensure_ascii=True, separators=(",", ":")
    )
    return {"content": [{"type": "text", "text": encoded}], "isError": False}


def _tool_failure() -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": _TOOL_ERROR_TEXT}],
        "isError": True,
    }


def _dispatch(client: InvestigationClient, method: str, params: dict[str, Any]) -> Any:
    if method == "ping":
        return {}
    if method == "initialize":
        requested = params.get("protocolVersion")
        if not isinstance(requested, str):
            raise _InvalidToolArguments
        protocol_version = (
            requested if requested in _PROTOCOL_VERSIONS else _PROTOCOL_VERSIONS[0]
        )
        return {
            "protocolVersion": protocol_version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": _SERVER_NAME, "version": _SERVER_VERSION},
        }
    if method == "tools/list":
        cursor = params.get("cursor")
        if cursor is not None and not isinstance(cursor, str):
            raise _InvalidToolArguments
        return {"tools": list(TOOLS)}
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments", {})
        if not isinstance(name, str) or name not in _TOOL_NAMES:
            raise _InvalidToolArguments
        try:
            return _tool_result(_call_public_tool(client, name, arguments))
        except _InvalidToolArguments:
            raise
        except Exception:
            return _tool_failure()
    raise LookupError


def _valid_id(value: object) -> bool:
    return value is None or isinstance(value, str) or type(value) is int


def _handle_frame(
    client: InvestigationClient, frame: bytes | object
) -> dict[str, Any] | None:
    if frame is _TOO_LARGE:
        return _error(None, _INVALID_REQUEST)
    try:
        message = json.loads(
            frame.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (AttributeError, UnicodeDecodeError, ValueError, RecursionError):
        return _error(None, _PARSE_ERROR)
    if (
        not isinstance(message, dict)
        or message.get("jsonrpc") != "2.0"
        or not isinstance(message.get("method"), str)
    ):
        return _error(None, _INVALID_REQUEST)

    if "id" not in message:
        # MCP defines notifications as one-way messages.  In particular, never
        # execute a state-changing tool call that cannot receive its result.
        return None
    request_id = message["id"]
    if not _valid_id(request_id):
        return _error(None, _INVALID_REQUEST)
    params = message.get("params", {})
    if not isinstance(params, dict):
        return _error(request_id, _INVALID_PARAMS)
    try:
        return _result(request_id, _dispatch(client, message["method"], params))
    except _InvalidToolArguments:
        return _error(request_id, _INVALID_PARAMS)
    except LookupError:
        return _error(request_id, _METHOD_NOT_FOUND)
    except Exception:
        return _error(request_id, _INTERNAL_ERROR)


def _frames(stream: BinaryIO) -> Iterator[bytes | object]:
    buffer = bytearray()
    discarding = False
    # BufferedReader.read(n) may wait for all n bytes on a live stdio pipe.
    # read1(n) returns the bytes currently available, which is required for an
    # interactive MCP handshake. BytesIO also implements read1 for tests.
    read_chunk = getattr(stream, "read1", stream.read)
    while True:
        chunk = read_chunk(_READ_CHUNK_BYTES)
        if not chunk:
            if discarding:
                yield _TOO_LARGE
            elif buffer:
                yield bytes(buffer)
            return
        if not isinstance(chunk, bytes):
            raise TypeError("binary input required")
        offset = 0
        while offset < len(chunk):
            newline = chunk.find(b"\n", offset)
            end = len(chunk) if newline < 0 else newline
            if discarding:
                if newline < 0:
                    break
                discarding = False
                yield _TOO_LARGE
                offset = newline + 1
                continue

            segment = chunk[offset:end]
            if len(buffer) + len(segment) > _MAX_MESSAGE_BYTES:
                buffer.clear()
                if newline < 0:
                    discarding = True
                    break
                yield _TOO_LARGE
                offset = newline + 1
                continue
            buffer.extend(segment)
            if newline < 0:
                break
            yield bytes(buffer)
            buffer.clear()
            offset = newline + 1


def _encode_response(response: dict[str, Any]) -> bytes:
    try:
        encoded = json.dumps(
            response,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError):
        encoded = b""
    if not encoded or len(encoded) > _MAX_MESSAGE_BYTES:
        encoded = json.dumps(
            _error(None, _INTERNAL_ERROR), separators=(",", ":")
        ).encode("ascii")
    return encoded + b"\n"


def serve(
    client: InvestigationClient,
    input_stream: BinaryIO,
    output_stream: BinaryIO,
) -> int:
    """Serve MCP until input EOF, always closing the investigation client."""

    try:
        for frame in _frames(input_stream):
            response = _handle_frame(client, frame)
            if response is None:
                continue
            output_stream.write(_encode_response(response))
            output_stream.flush()
        return 0
    except (OSError, TypeError):
        return 1
    finally:
        client.close()


def main() -> int:
    try:
        client = InvestigationClient.from_environment()
    except InvestigationClientError:
        return 1
    return serve(client, sys.stdin.buffer, sys.stdout.buffer)


if __name__ == "__main__":
    raise SystemExit(main())
