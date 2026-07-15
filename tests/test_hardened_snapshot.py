from __future__ import annotations

from copy import deepcopy
import unittest

from epiagentbench.trusted.hardened_snapshot import (
    AuthenticatedTrace,
    HardenedSnapshotPlan,
    InferenceProxyPolicy,
    SnapshotLimits,
    SnapshotPlanError,
)


IMAGE = "registry.example/epiagent@sha256:" + "1" * 64
RECEIPT_KEY = b"receipt authentication key".ljust(32, b"!")


def make_policy(**changes):
    values = {
        "policy_id": "openai-inference-v1",
        "network_name": "eab-run-17",
        "proxy_url": "http://inference-proxy:8080",
        "allowed_provider_hosts": ("api.openai.com",),
        "allowed_decoded_paths": ("/v1/responses",),
        "allowed_models": ("gpt-5.6-sol",),
    }
    values.update(changes)
    return InferenceProxyPolicy(**values)


def make_plan(**changes):
    values = {
        "run_id": "run-17",
        "image": IMAGE,
        "broker_directory": "/tmp/eab-17",
        "agent_argv": ("codex", "exec", "--ephemeral"),
        "proxy_policy": make_policy(),
    }
    values.update(changes)
    return HardenedSnapshotPlan(**values)


class HardenedSnapshotPlanTests(unittest.TestCase):
    def test_plan_requires_digest_pinned_image(self):
        with self.assertRaisesRegex(SnapshotPlanError, "pinned"):
            make_plan(image="registry.example/epiagent:latest")

    def test_plan_builds_read_only_isolated_command_without_private_mounts(self):
        plan = make_plan()
        command = plan.docker_argv()
        joined = " ".join(command)
        self.assertIn("--pull never", joined)
        self.assertIn("--read-only", command)
        self.assertIn("--ipc none", joined)
        self.assertIn("--cap-drop ALL", joined)
        self.assertIn("--network eab-run-17", joined)
        self.assertIn("/state:rw,noexec,nosuid,nodev", joined)
        self.assertIn("src=/tmp/eab-17,dst=/broker,readonly", joined)
        self.assertIn("HTTPS_PROXY=http://inference-proxy:8080", joined)
        self.assertIn(IMAGE, command)
        for private_term in ("episode_secret", "family=", "seed=", "oracle"):
            self.assertNotIn(private_term, joined)
        self.assertFalse(plan.isolation_claims["linux_execution_verified"])
        self.assertFalse(plan.isolation_claims["trusted_source_mounted"])
        self.assertFalse(plan.isolation_claims["private_episode_pack_mounted"])

    def test_network_plan_is_internal_and_episode_scoped(self):
        plan = make_plan()
        network = plan.network_create_argv()
        self.assertIn("--internal", network)
        self.assertEqual(network[-1], "eab-run-17")
        with self.assertRaisesRegex(SnapshotPlanError, "episode-scoped"):
            make_plan(
                proxy_policy=make_policy(network_name="shared-agent-network")
            )

    def test_proxy_requires_exact_hosts_and_internal_alias(self):
        with self.assertRaisesRegex(SnapshotPlanError, "exact DNS"):
            make_policy(allowed_provider_hosts=("*.openai.com",))
        with self.assertRaisesRegex(SnapshotPlanError, "internal sidecar"):
            make_policy(proxy_url="https://proxy.example:443")
        with self.assertRaisesRegex(SnapshotPlanError, "exact decoded paths"):
            make_policy(allowed_decoded_paths=("/v1/*",))

    def test_proxy_policy_is_fail_closed_for_paths_models_tools_and_budgets(self):
        policy = make_policy(max_calls=31, max_total_tokens=70_000)
        payload = policy.as_dict()
        self.assertEqual(
            payload["path_match_mode"],
            "exact-after-one-strict-percent-decode",
        )
        self.assertTrue(payload["reject_encoded_path_separators"])
        self.assertEqual(
            payload["required_request_fields"],
            {"store": False, "background": False},
        )
        self.assertEqual(payload["tools_policy"], "absent-or-empty")
        self.assertEqual(payload["allowed_models"], ["gpt-5.6-sol"])
        self.assertEqual(payload["max_calls"], 31)
        self.assertEqual(payload["max_total_tokens"], 70_000)

        hostile = (
            {"allowed_decoded_paths": ("/v1/%72esponses",)},
            {"allowed_decoded_paths": ("/v1/responses/",)},
            {"allowed_decoded_paths": ("/v1//responses",)},
            {"allowed_models": ("gpt-*",)},
            {"allowed_methods": ("GET", "POST")},
            {"require_store_false": False},
            {"require_background_false": False},
            {"tools_policy": "allow"},
            {"tool_choice_policy": "auto"},
            {"max_calls": 0},
            {"max_total_tokens": 0},
            {"max_output_tokens_per_call": 300_000},
        )
        for changes in hostile:
            with self.subTest(changes=changes):
                with self.assertRaises(SnapshotPlanError):
                    make_policy(**changes)

    def test_offline_plan_has_no_network_or_proxy_environment(self):
        plan = make_plan(network_mode="none")
        command = plan.docker_argv()
        joined = " ".join(command)
        self.assertIn("--network none", joined)
        self.assertNotIn("HTTP_PROXY=", joined)
        self.assertNotIn("HTTPS_PROXY=", joined)
        self.assertTrue(plan.isolation_claims["network_disabled"])
        self.assertFalse(plan.isolation_claims["episode_network_internal"])
        with self.assertRaisesRegex(SnapshotPlanError, "do not create"):
            plan.network_create_argv()

    def test_trace_chain_and_receipt_detect_tampering_and_model_fallback(self):
        plan = make_plan()
        trace = AuthenticatedTrace(plan.run_id)
        trace.append("agent_started", {"cli_version": "1.2.3"})
        trace.append("tool_result", {"tool": "get_manifest", "ok": True})
        events = trace.events
        self.assertTrue(AuthenticatedTrace.verify_chain(events, trace.root))
        tampered_events = [deepcopy(event) for event in events]
        tampered_events[1]["payload"]["ok"] = False
        self.assertFalse(
            AuthenticatedTrace.verify_chain(tampered_events, trace.root)
        )

        receipt = trace.receipt(
            authentication_key=RECEIPT_KEY,
            episode_commitment="sha256:" + "2" * 64,
            plan=plan,
            requested_model="claude-fable-5",
            observed_model="claude-opus-4-1",
            runner_version="snapshot-runner-0.1",
        )
        self.assertTrue(receipt["model_fallback_detected"])
        self.assertEqual(receipt["snapshot_plan_commitment"], plan.commitment)
        self.assertTrue(
            AuthenticatedTrace.verify_receipt(receipt, RECEIPT_KEY)
        )
        tampered_receipt = deepcopy(receipt)
        tampered_receipt["observed_model"] = "claude-fable-5"
        self.assertFalse(
            AuthenticatedTrace.verify_receipt(tampered_receipt, RECEIPT_KEY)
        )

    def test_receipt_authenticates_execution_and_score_hashes(self):
        plan = make_plan(network_mode="none")
        trace = AuthenticatedTrace(plan.run_id)
        hashes = {
            "execution": "sha256:" + "3" * 64,
            "scorecard": "sha256:" + "4" * 64,
        }
        receipt = trace.receipt(
            authentication_key=RECEIPT_KEY,
            episode_commitment="sha256:" + "2" * 64,
            plan=plan,
            requested_model="offline-image:sha256:" + "1" * 64,
            observed_model="offline-image:sha256:" + "1" * 64,
            runner_version="snapshot-runner-0.1",
            artifact_hashes=hashes,
        )
        self.assertEqual(receipt["artifact_hashes"], hashes)
        self.assertTrue(AuthenticatedTrace.verify_receipt(receipt, RECEIPT_KEY))
        changed = deepcopy(receipt)
        changed["artifact_hashes"]["scorecard"] = "sha256:" + "5" * 64
        self.assertFalse(AuthenticatedTrace.verify_receipt(changed, RECEIPT_KEY))

    def test_receipt_binds_complete_canonical_snapshot_plan(self):
        plan = make_plan()
        changed = make_plan(
            agent_argv=("different-agent", "--unsafe-mode"),
            limits=SnapshotLimits(memory="8g", cpus=4.0),
            uid=1234,
            gid=1234,
        )
        self.assertNotEqual(plan.commitment, changed.commitment)

        trace = AuthenticatedTrace(plan.run_id)
        common = {
            "authentication_key": RECEIPT_KEY,
            "episode_commitment": "sha256:" + "2" * 64,
            "requested_model": "gpt-5.6-sol",
            "observed_model": "gpt-5.6-sol",
            "runner_version": "snapshot-runner-0.1",
        }
        first = trace.receipt(plan=plan, **common)
        second = trace.receipt(plan=changed, **common)
        self.assertNotEqual(first, second)
        self.assertEqual(first["snapshot_plan_commitment"], plan.commitment)
        self.assertEqual(second["snapshot_plan_commitment"], changed.commitment)
        self.assertFalse(first["isolation_claims"]["linux_execution_verified"])
        self.assertFalse(second["isolation_claims"]["linux_execution_verified"])

    def test_trace_detaches_nested_payloads_and_receipt_binds_run(self):
        plan = make_plan()
        trace = AuthenticatedTrace(plan.run_id)
        payload = {"nested": {"value": 1}}
        trace.append("tool_result", payload)
        payload["nested"]["value"] = 2
        self.assertEqual(trace.events[0]["payload"]["nested"]["value"], 1)
        self.assertTrue(AuthenticatedTrace.verify_chain(trace.events, trace.root))

        other_plan = make_plan(
            run_id="other-run",
            proxy_policy=make_policy(network_name="eab-other-run"),
        )
        with self.assertRaisesRegex(SnapshotPlanError, "identifiers differ"):
            trace.receipt(
                authentication_key=RECEIPT_KEY,
                episode_commitment="sha256:" + "2" * 64,
                plan=other_plan,
                requested_model="gpt-5.6-sol",
                observed_model="gpt-5.6-sol",
                runner_version="snapshot-runner-0.1",
            )


if __name__ == "__main__":
    unittest.main()
