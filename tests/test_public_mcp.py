from __future__ import annotations

from io import BytesIO
import inspect
import json
import unittest

import epiagentbench_client.mcp_server as mcp_server
from epiagentbench_client import InvestigationClientError


class FakeInvestigationClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []
        self.closed = False
        self.fail_interview = False

    @property
    def manifest(self) -> dict[str, object]:
        self.calls.append(("get_manifest", (), {}))
        return {"episode_id": "public-episode"}

    def initial_observations(self) -> list[dict[str, object]]:
        self.calls.append(("initial_observations", (), {}))
        return [{"record_id": "obs-1"}]

    def search_observations(self, kind=None, **filters):
        self.calls.append(("search_observations", (kind,), filters))
        return [{"kind": kind, "filters": filters}]

    def request_interview(self, patient_id):
        self.calls.append(("request_interview", (patient_id,), {}))
        if self.fail_interview:
            raise InvestigationClientError("private detail must not escape")
        return {"status": "scheduled"}

    def order_confirmatory_test(self, patient_id):
        self.calls.append(("order_confirmatory_test", (patient_id,), {}))
        return {"status": "scheduled"}

    def request_inspection(self, target_id):
        self.calls.append(("request_inspection", (target_id,), {}))
        return {"status": "scheduled"}

    def advance_time(self, minutes):
        self.calls.append(("advance_time", (minutes,), {}))
        return [{"minute": minutes}]

    def recommend_action(self, action_type, target_id, evidence_ids):
        self.calls.append(
            ("recommend_action", (action_type, target_id, evidence_ids), {})
        )
        return {"status": "recorded"}

    def set_institution_control(self, level, target_id, evidence_ids):
        self.calls.append(
            ("set_institution_control", (level, target_id, evidence_ids), {})
        )
        return {"status": "scheduled"}

    def set_response_control(self, action_type, level, target_id, evidence_ids):
        self.calls.append(
            (
                "set_response_control",
                (action_type, level, target_id, evidence_ids),
                {},
            )
        )
        return {"status": "scheduled"}

    def submit_forecast(self, expected_new_encounters):
        self.calls.append(("submit_forecast", (expected_new_encounters,), {}))
        return {"status": "recorded"}

    def get_clock_and_budget(self):
        self.calls.append(("get_clock_and_budget", (), {}))
        return {"current_minute": 0}

    def close(self) -> None:
        self.closed = True


def _request(request_id: int, method: str, params=None) -> bytes:
    message = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        message["params"] = params
    return json.dumps(message, separators=(",", ":")).encode() + b"\n"


def _run(payload: bytes, client: FakeInvestigationClient | None = None):
    fake = client or FakeInvestigationClient()
    output = BytesIO()
    status = mcp_server.serve(fake, BytesIO(payload), output)
    responses = [json.loads(line) for line in output.getvalue().splitlines()]
    return status, responses, fake


class PublicMcpServerTests(unittest.TestCase):
    def test_frame_reader_prefers_nonblocking_buffered_read1(self):
        class ReadOneStream:
            def __init__(self) -> None:
                self.calls = 0

            def read(self, _: int) -> bytes:
                raise AssertionError("blocking read must not be used")

            def read1(self, _: int) -> bytes:
                self.calls += 1
                return b'{}\n' if self.calls == 1 else b""

        self.assertEqual(list(mcp_server._frames(ReadOneStream())), [b"{}"])

    def test_initialize_ping_notifications_and_typed_tool_list(self):
        notification = (
            b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n'
        )
        payload = b"".join(
            [
                _request(
                    1,
                    "initialize",
                    {
                        "protocolVersion": "2024-11-05",
                        "clientInfo": {"name": "test", "version": "1"},
                        "capabilities": {},
                    },
                ),
                notification,
                _request(2, "ping", {}),
                _request(3, "tools/list", {}),
            ]
        )
        status, responses, client = _run(payload)

        self.assertEqual(status, 0)
        self.assertTrue(client.closed)
        self.assertEqual([response["id"] for response in responses], [1, 2, 3])
        initialized = responses[0]["result"]
        self.assertEqual(initialized["protocolVersion"], "2024-11-05")
        self.assertEqual(
            initialized["serverInfo"]["name"], "epiagentbench-investigation"
        )
        tools = responses[2]["result"]["tools"]
        self.assertEqual(
            {tool["name"] for tool in tools},
            {
                "get_manifest",
                "initial_observations",
                "search_observations",
                "request_interview",
                "order_confirmatory_test",
                "request_inspection",
                "advance_time",
                "recommend_action",
                "set_institution_control",
                "set_response_control",
                "submit_forecast",
                "get_clock_and_budget",
            },
        )
        for tool in tools:
            schema = tool["inputSchema"]
            self.assertEqual(schema["type"], "object")
            self.assertFalse(schema["additionalProperties"])
            self.assertFalse(tool["annotations"]["destructiveHint"])
            self.assertFalse(tool["annotations"]["openWorldHint"])
        read_only = {
            tool["name"]
            for tool in tools
            if tool["annotations"]["readOnlyHint"]
        }
        self.assertEqual(
            read_only,
            {
                "get_manifest",
                "initial_observations",
                "search_observations",
                "get_clock_and_budget",
            },
        )

    def test_tool_calls_route_only_to_public_client_methods(self):
        calls = [
            ("get_manifest", {}),
            ("initial_observations", {}),
            ("search_observations", {"kind": "lab", "filters": {"site": "A"}}),
            ("request_interview", {"patient_id": "patient-1"}),
            ("order_confirmatory_test", {"patient_id": "patient-1"}),
            ("request_inspection", {"target_id": "target-1"}),
            ("advance_time", {"minutes": 60}),
            (
                "recommend_action",
                {
                    "action_type": "monitor",
                    "target_id": None,
                    "evidence_ids": ["obs-1"],
                },
            ),
            (
                "set_institution_control",
                {
                    "level": "standard",
                    "target_id": "target-1",
                    "evidence_ids": ["obs-1"],
                },
            ),
            (
                "set_response_control",
                {
                    "action_type": "source_control",
                    "level": "intensive",
                    "target_id": "target-1",
                    "evidence_ids": ["obs-1"],
                },
            ),
            ("submit_forecast", {"expected_new_encounters": 4}),
            ("get_clock_and_budget", {}),
        ]
        payload = b"".join(
            _request(index, "tools/call", {"name": name, "arguments": arguments})
            for index, (name, arguments) in enumerate(calls, start=1)
        )
        status, responses, client = _run(payload)

        self.assertEqual(status, 0)
        self.assertEqual(len(responses), len(calls))
        for response in responses:
            result = response["result"]
            self.assertFalse(result["isError"])
            self.assertIsInstance(
                json.loads(result["content"][0]["text"]), (dict, list)
            )
        self.assertEqual(
            [name for name, _, _ in client.calls], [name for name, _ in calls]
        )

    def test_bad_tool_arguments_and_unknown_methods_use_fixed_errors(self):
        payload = b"".join(
            [
                _request(
                    1,
                    "tools/call",
                    {"name": "advance_time", "arguments": {"minutes": True}},
                ),
                _request(
                    2,
                    "tools/call",
                    {"name": "score", "arguments": {}},
                ),
                _request(3, "private/admin", {}),
            ]
        )
        _, responses, client = _run(payload)

        self.assertEqual(
            responses[0]["error"], {"code": -32602, "message": "Invalid params"}
        )
        self.assertEqual(
            responses[1]["error"], {"code": -32602, "message": "Invalid params"}
        )
        self.assertEqual(
            responses[2]["error"], {"code": -32601, "message": "Method not found"}
        )
        self.assertEqual(client.calls, [])

    def test_client_failure_is_sanitized_as_mcp_tool_failure(self):
        client = FakeInvestigationClient()
        client.fail_interview = True
        payload = _request(
            1,
            "tools/call",
            {
                "name": "request_interview",
                "arguments": {"patient_id": "patient-1"},
            },
        )
        _, responses, _ = _run(payload, client)

        result = responses[0]["result"]
        self.assertTrue(result["isError"])
        self.assertEqual(result["content"][0]["text"], "Tool execution failed.")
        self.assertNotIn("private", json.dumps(responses))

    def test_malformed_duplicate_and_oversize_frames_do_not_stop_server(self):
        oversize = b"x" * (mcp_server._MAX_MESSAGE_BYTES + 1) + b"\n"
        payload = b"".join(
            [
                b"{not-json}\n",
                b'{"jsonrpc":"2.0","id":1,"id":2,"method":"ping"}\n',
                oversize,
                _request(4, "ping", {}),
            ]
        )
        status, responses, _ = _run(payload)

        self.assertEqual(status, 0)
        self.assertEqual(
            [item["error"]["code"] for item in responses[:3]],
            [-32700, -32700, -32600],
        )
        self.assertEqual(responses[3], {"jsonrpc": "2.0", "id": 4, "result": {}})

    def test_tool_call_notification_is_not_executed(self):
        payload = (
            b'{"jsonrpc":"2.0","method":"tools/call","params":'
            b'{"name":"advance_time","arguments":{"minutes":60}}}\n'
        )
        _, responses, client = _run(payload)
        self.assertEqual(responses, [])
        self.assertEqual(client.calls, [])

    def test_module_has_no_trusted_package_import(self):
        source = inspect.getsource(mcp_server)
        self.assertNotIn("from epiagentbench ", source)
        self.assertNotIn("from epiagentbench.", source)
        self.assertNotIn("import epiagentbench ", source)


if __name__ == "__main__":
    unittest.main()
