"""Declarative artifacts for the hardened Linux fresh-container runner.

This module builds and authenticates plans; it does not itself invoke Docker.
``snapshot`` remains in the artifact format's legacy name, but no VM/container
snapshot is restored.  Each run starts a fresh container with a fresh tmpfs
``/state`` and deletes that state after the episode.
Offline plans use Docker's ``none`` network.  Online plans require a separately
audited inference proxy on an episode-scoped *internal* network.  A policy
object is a fail-closed contract for that proxy, not proof that a proxy enforced
it; the runner must obtain such proof before online execution is enabled.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit


_IMAGE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._/:@-]{0,220}@sha256:[0-9a-f]{64}$"
)
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_HOST = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)
_LIMIT = re.compile(r"^[1-9][0-9]*(?:[kmgt]b?)?$", re.IGNORECASE)
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_ZERO_ROOT = "0" * 64
_TRACE_DOMAIN = b"EpiAgentBench run trace v1\x00"
_RECEIPT_DOMAIN = b"EpiAgentBench run receipt v1\x00"
_PLAN_DOMAIN = b"EpiAgentBench hardened snapshot plan v1\x00"


class SnapshotPlanError(ValueError):
    """Raised when a run plan cannot support the declared isolation model."""


@dataclass(frozen=True, slots=True)
class SnapshotLimits:
    timeout_seconds: int = 900
    memory: str = "2g"
    cpus: float = 2.0
    pids: int = 256
    state_size: str = "512m"

    def __post_init__(self) -> None:
        if (
            type(self.timeout_seconds) is not int
            or not 1 <= self.timeout_seconds <= 3600
            or type(self.pids) is not int
            or not 16 <= self.pids <= 4096
            or type(self.cpus) not in (int, float)
            or not 0.1 <= float(self.cpus) <= 64
            or not isinstance(self.memory, str)
            or not _LIMIT.fullmatch(self.memory)
            or not isinstance(self.state_size, str)
            or not _LIMIT.fullmatch(self.state_size)
        ):
            raise SnapshotPlanError("Invalid snapshot resource limits")

    def as_dict(self) -> dict[str, Any]:
        """Return the normalized limits included in the signed run plan."""

        return {
            "timeout_seconds": self.timeout_seconds,
            "memory": self.memory,
            "cpus": float(self.cpus),
            "pids": self.pids,
            "state_size": self.state_size,
        }


@dataclass(frozen=True, slots=True)
class InferenceProxyPolicy:
    """Committed allow-list policy expected from an external proxy sidecar."""

    policy_id: str
    network_name: str
    proxy_url: str
    allowed_provider_hosts: tuple[str, ...]
    allowed_decoded_paths: tuple[str, ...]
    allowed_models: tuple[str, ...]
    allowed_methods: tuple[str, ...] = ("POST",)
    require_store_false: bool = True
    require_background_false: bool = True
    tools_policy: str = "absent-or-empty"
    tool_choice_policy: str = "absent-or-none"
    max_calls: int = 128
    max_total_tokens: int = 262_144
    max_output_tokens_per_call: int = 16_384
    max_request_bytes: int = 4_194_304
    max_response_bytes: int = 16_777_216

    def __post_init__(self) -> None:
        if not isinstance(self.policy_id, str) or not _IDENTIFIER.fullmatch(
            self.policy_id
        ):
            raise SnapshotPlanError("Invalid inference policy identifier")
        if not isinstance(self.network_name, str) or not _IDENTIFIER.fullmatch(
            self.network_name
        ):
            raise SnapshotPlanError("Invalid internal network name")
        try:
            parsed = urlsplit(self.proxy_url)
            parsed_port = parsed.port
        except ValueError:
            raise SnapshotPlanError("Invalid inference proxy URL") from None
        if (
            parsed.scheme != "http"
            or parsed.hostname != "inference-proxy"
            or parsed_port is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise SnapshotPlanError(
                "Inference proxy must be an uncredentialed internal sidecar URL"
            )
        if (
            not isinstance(self.allowed_provider_hosts, tuple)
            or not self.allowed_provider_hosts
            or len(set(self.allowed_provider_hosts))
            != len(self.allowed_provider_hosts)
            or any(
                not isinstance(host, str)
                or host != host.lower()
                or not _HOST.fullmatch(host)
                for host in self.allowed_provider_hosts
            )
        ):
            raise SnapshotPlanError("Provider hosts must be exact DNS names")
        if self.allowed_methods != ("POST",):
            raise SnapshotPlanError("Inference proxy must allow only POST")
        if (
            not isinstance(self.allowed_decoded_paths, tuple)
            or not self.allowed_decoded_paths
            or len(set(self.allowed_decoded_paths))
            != len(self.allowed_decoded_paths)
            or any(
                not isinstance(path, str)
                or not path.startswith("/")
                or path == "/"
                or "*" in path
                or "?" in path
                or "#" in path
                or "%" in path
                or "//" in path
                or path.endswith("/")
                or ".." in path.split("/")
                for path in self.allowed_decoded_paths
            )
        ):
            raise SnapshotPlanError("Provider paths must be exact decoded paths")
        if (
            not isinstance(self.allowed_models, tuple)
            or not self.allowed_models
            or len(set(self.allowed_models)) != len(self.allowed_models)
            or any(
                not isinstance(model, str)
                or not _MODEL.fullmatch(model)
                or "*" in model
                for model in self.allowed_models
            )
        ):
            raise SnapshotPlanError("Models must be an exact non-wildcard allowlist")
        if (
            self.require_store_false is not True
            or self.require_background_false is not True
            or self.tools_policy != "absent-or-empty"
            or self.tool_choice_policy != "absent-or-none"
        ):
            raise SnapshotPlanError(
                "Inference policy must disable storage, background jobs, and tools"
            )
        if (
            type(self.max_calls) is not int
            or not 1 <= self.max_calls <= 10_000
            or type(self.max_total_tokens) is not int
            or not 1 <= self.max_total_tokens <= 10_000_000
            or type(self.max_output_tokens_per_call) is not int
            or not 1 <= self.max_output_tokens_per_call <= self.max_total_tokens
        ):
            raise SnapshotPlanError("Invalid inference proxy call or token caps")
        if (
            type(self.max_request_bytes) is not int
            or not 1 <= self.max_request_bytes <= 64 * 1024 * 1024
            or type(self.max_response_bytes) is not int
            or not 1 <= self.max_response_bytes <= 256 * 1024 * 1024
        ):
            raise SnapshotPlanError("Invalid inference proxy byte limits")

    @property
    def commitment(self) -> str:
        digest = hashlib.sha256(
            b"EpiAgentBench inference proxy policy v1\x00"
            + _canonical_json(self.as_dict())
        ).hexdigest()
        return f"sha256:{digest}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "network_name": self.network_name,
            "proxy_url": self.proxy_url,
            "allowed_provider_hosts": list(self.allowed_provider_hosts),
            "allowed_decoded_paths": list(self.allowed_decoded_paths),
            "path_match_mode": "exact-after-one-strict-percent-decode",
            "reject_invalid_percent_encoding": True,
            "reject_encoded_path_separators": True,
            "reject_noncanonical_paths": True,
            "allowed_models": list(self.allowed_models),
            "model_match_mode": "exact-json-string",
            "reject_missing_model": True,
            "reject_model_aliases": True,
            "allowed_methods": list(self.allowed_methods),
            "required_request_fields": {
                "store": False,
                "background": False,
            },
            "tools_policy": self.tools_policy,
            "tool_choice_policy": self.tool_choice_policy,
            "max_calls": self.max_calls,
            "max_total_tokens": self.max_total_tokens,
            "max_output_tokens_per_call": self.max_output_tokens_per_call,
            "max_request_bytes": self.max_request_bytes,
            "max_response_bytes": self.max_response_bytes,
            "direct_egress": "deny",
            "credential_mode": "proxy-injected-upstream-credentials",
        }


@dataclass(frozen=True, slots=True)
class HardenedSnapshotPlan:
    """A digest-pinned, read-only container plan for one isolated episode."""

    run_id: str
    image: str
    broker_directory: str
    agent_argv: tuple[str, ...]
    proxy_policy: InferenceProxyPolicy
    limits: SnapshotLimits = SnapshotLimits()
    uid: int = 65_532
    gid: int = 65_532
    network_mode: str = "inference_proxy"

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, str) or not _IDENTIFIER.fullmatch(self.run_id):
            raise SnapshotPlanError("Invalid run identifier")
        if not isinstance(self.image, str) or not _IMAGE.fullmatch(self.image):
            raise SnapshotPlanError("Container image must be pinned by sha256 digest")
        broker = Path(self.broker_directory)
        if (
            not broker.is_absolute()
            or ".." in broker.parts
            or "," in self.broker_directory
            or any(ord(character) < 32 for character in self.broker_directory)
            or len(str(broker / "episode.sock").encode("utf-8")) > 100
        ):
            raise SnapshotPlanError("Invalid public broker directory")
        if (
            not isinstance(self.agent_argv, tuple)
            or not self.agent_argv
            or len(self.agent_argv) > 128
            or any(
                not isinstance(argument, str)
                or not argument
                or "\x00" in argument
                for argument in self.agent_argv
            )
        ):
            raise SnapshotPlanError("Invalid snapshot entry command")
        if (
            type(self.uid) is not int
            or type(self.gid) is not int
            or not 1 <= self.uid <= 2**31 - 1
            or not 1 <= self.gid <= 2**31 - 1
        ):
            raise SnapshotPlanError("Snapshot user must be an unprivileged numeric ID")
        if self.proxy_policy.network_name != f"eab-{self.run_id}":
            raise SnapshotPlanError("Run must use its own episode-scoped network")
        if self.network_mode not in {"none", "inference_proxy"}:
            raise SnapshotPlanError("Invalid snapshot network mode")

    @property
    def image_digest(self) -> str:
        return self.image.rsplit("@", 1)[1]

    def as_dict(self) -> dict[str, Any]:
        """Return every execution-relevant field in canonicalizable form."""

        return {
            "format": "epiagentbench.hardened-snapshot-plan.v1",
            "run_id": self.run_id,
            "image": self.image,
            "broker_directory": self.broker_directory,
            "agent_argv": list(self.agent_argv),
            "proxy_policy": self.proxy_policy.as_dict(),
            "limits": self.limits.as_dict(),
            "uid": self.uid,
            "gid": self.gid,
            "network_mode": self.network_mode,
            "isolation_claims": self.isolation_claims,
        }

    @property
    def commitment(self) -> str:
        """Commit to the complete requested plan, not merely its image."""

        digest = hashlib.sha256(
            _PLAN_DOMAIN + _canonical_json(self.as_dict())
        ).hexdigest()
        return f"sha256:{digest}"

    @property
    def isolation_claims(self) -> dict[str, bool]:
        """Machine-readable requested controls, not proof they were enforced."""

        return {
            "image_digest_pinned": True,
            "root_filesystem_read_only": True,
            "episode_state_ephemeral": True,
            "network_disabled": self.network_mode == "none",
            "episode_network_internal": self.network_mode == "inference_proxy",
            "inference_only_egress_requires_external_proxy": (
                self.network_mode == "inference_proxy"
            ),
            "trusted_source_mounted": False,
            "private_episode_pack_mounted": False,
            "linux_execution_verified": False,
        }

    def network_create_argv(self, docker: str = "docker") -> tuple[str, ...]:
        """Build the required internal network creation command."""

        _plain_executable(docker)
        if self.network_mode != "inference_proxy":
            raise SnapshotPlanError("Offline plans do not create a network")
        return (
            docker,
            "network",
            "create",
            "--internal",
            "--driver",
            "bridge",
            "--label",
            f"org.epiagentbench.run={self.run_id}",
            self.proxy_policy.network_name,
        )

    def docker_argv(self, docker: str = "docker") -> tuple[str, ...]:
        """Build but do not execute the hardened agent-container command."""

        _plain_executable(docker)
        state_options = (
            "rw,noexec,nosuid,nodev,"
            f"size={self.limits.state_size},uid={self.uid},gid={self.gid},mode=0700"
        )
        environment = {
            "HOME": "/state/home",
            "TMPDIR": "/state/tmp",
            "XDG_CACHE_HOME": "/state/cache",
            "PYTHONDONTWRITEBYTECODE": "1",
            "EPIAGENT_SOCKET": "/broker/episode.sock",
        }
        if self.network_mode == "inference_proxy":
            environment.update(
                {
                    "HTTP_PROXY": self.proxy_policy.proxy_url,
                    "HTTPS_PROXY": self.proxy_policy.proxy_url,
                    "ALL_PROXY": self.proxy_policy.proxy_url,
                    "NO_PROXY": "",
                }
            )
        command: list[str] = [
            docker,
            "run",
            "--rm",
            "--pull",
            "never",
            "--name",
            f"eab-{self.run_id}",
            "--network",
            (
                "none"
                if self.network_mode == "none"
                else self.proxy_policy.network_name
            ),
            "--ipc",
            "none",
            "--read-only",
            "--user",
            f"{self.uid}:{self.gid}",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges=true",
            "--pids-limit",
            str(self.limits.pids),
            "--memory",
            self.limits.memory,
            "--cpus",
            str(self.limits.cpus),
            "--ulimit",
            "nofile=256:256",
            "--ulimit",
            "nproc=128:128",
            "--tmpfs",
            f"/state:{state_options}",
            "--mount",
            f"type=bind,src={self.broker_directory},dst=/broker,readonly",
            "--workdir",
            "/state",
        ]
        for name, value in environment.items():
            command.extend(("--env", f"{name}={value}"))
        command.append(self.image)
        command.extend(self.agent_argv)
        return tuple(command)


class AuthenticatedTrace:
    """In-memory hash chain suitable for streaming to an append-only sink."""

    def __init__(self, run_id: str):
        if not isinstance(run_id, str) or not _IDENTIFIER.fullmatch(run_id):
            raise SnapshotPlanError("Invalid trace run identifier")
        self._run_id = run_id
        self._events: list[dict[str, Any]] = []
        self._root = _ZERO_ROOT

    @property
    def root(self) -> str:
        return self._root

    @property
    def event_count(self) -> int:
        return len(self._events)

    @property
    def events(self) -> tuple[dict[str, Any], ...]:
        # Canonical JSON roundtrip prevents callers from mutating nested state.
        return tuple(json.loads(_canonical_json(event)) for event in self._events)

    def append(self, event_type: str, payload: Mapping[str, Any]) -> str:
        if not isinstance(event_type, str) or not _IDENTIFIER.fullmatch(event_type):
            raise SnapshotPlanError("Invalid trace event type")
        if not isinstance(payload, Mapping):
            raise SnapshotPlanError("Trace payload must be a mapping")
        event = {
            "sequence": len(self._events) + 1,
            "event_type": event_type,
            "payload": dict(payload),
        }
        encoded = _canonical_json(event)
        # Detach nested mutable values before retaining the hashed event.
        event = json.loads(encoded)
        self._root = hashlib.sha256(
            _TRACE_DOMAIN + bytes.fromhex(self._root) + encoded
        ).hexdigest()
        self._events.append(event)
        return self._root

    def receipt(
        self,
        *,
        authentication_key: bytes,
        episode_commitment: str,
        plan: HardenedSnapshotPlan,
        requested_model: str,
        observed_model: str,
        runner_version: str,
        artifact_hashes: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """Authenticate the final chain root and all comparison-critical IDs."""

        key = _receipt_key(authentication_key)
        if plan.run_id != self._run_id:
            raise SnapshotPlanError("Trace and snapshot plan run identifiers differ")
        if not isinstance(episode_commitment, str) or not _SHA256.fullmatch(
            episode_commitment
        ):
            raise SnapshotPlanError("Invalid episode commitment")
        for label, value in (
            ("requested model", requested_model),
            ("observed model", observed_model),
            ("runner version", runner_version),
        ):
            if not isinstance(value, str) or not value or "\x00" in value:
                raise SnapshotPlanError(f"Invalid {label}")
        normalized_hashes: dict[str, str] = {}
        if artifact_hashes is not None:
            if (
                not isinstance(artifact_hashes, Mapping)
                or not artifact_hashes
                or any(
                    not isinstance(name, str)
                    or not _IDENTIFIER.fullmatch(name)
                    or not isinstance(digest, str)
                    or not _SHA256.fullmatch(digest)
                    for name, digest in artifact_hashes.items()
                )
            ):
                raise SnapshotPlanError("Invalid receipt artifact hashes")
            normalized_hashes = dict(sorted(artifact_hashes.items()))
        body = {
            "format": "epiagentbench.run-receipt.v1",
            "run_id": self._run_id,
            "event_count": self.event_count,
            "trace_root": self.root,
            "trace_events": list(self.events),
            "episode_commitment": episode_commitment,
            "snapshot_plan_commitment": plan.commitment,
            "image": plan.image,
            "proxy_policy_commitment": plan.proxy_policy.commitment,
            "requested_model": requested_model,
            "observed_model": observed_model,
            "model_fallback_detected": requested_model != observed_model,
            "runner_version": runner_version,
            "artifact_hashes": normalized_hashes,
            "isolation_claims": plan.isolation_claims,
        }
        tag = hmac.new(
            key, _RECEIPT_DOMAIN + _canonical_json(body), hashlib.sha256
        ).hexdigest()
        return {
            **body,
            "authentication": {"algorithm": "hmac-sha256", "tag": tag},
        }

    @staticmethod
    def verify_chain(events: Sequence[Mapping[str, Any]], expected_root: str) -> bool:
        root = _ZERO_ROOT
        try:
            for index, event in enumerate(events, start=1):
                if not isinstance(event, Mapping) or event.get("sequence") != index:
                    return False
                root = hashlib.sha256(
                    _TRACE_DOMAIN
                    + bytes.fromhex(root)
                    + _canonical_json(dict(event))
                ).hexdigest()
        except (ValueError, SnapshotPlanError):
            return False
        return isinstance(expected_root, str) and hmac.compare_digest(
            root, expected_root
        )

    @staticmethod
    def verify_receipt(receipt: Mapping[str, Any], authentication_key: bytes) -> bool:
        try:
            key = _receipt_key(authentication_key)
            if not isinstance(receipt, Mapping):
                return False
            value = dict(receipt)
            authentication = value.pop("authentication")
            if not isinstance(authentication, Mapping) or set(authentication) != {
                "algorithm",
                "tag",
            } or authentication.get("algorithm") != "hmac-sha256":
                return False
            tag = authentication.get("tag")
            if not isinstance(tag, str):
                return False
            expected = hmac.new(
                key,
                _RECEIPT_DOMAIN + _canonical_json(value),
                hashlib.sha256,
            ).hexdigest()
            events = value.get("trace_events")
            event_count = value.get("event_count")
            trace_root = value.get("trace_root")
            return (
                hmac.compare_digest(tag, expected)
                and isinstance(events, list)
                and type(event_count) is int
                and event_count == len(events)
                and AuthenticatedTrace.verify_chain(events, trace_root)
            )
        except (KeyError, TypeError, ValueError, SnapshotPlanError):
            return False


def _receipt_key(value: bytes) -> bytes:
    if type(value) is not bytes or len(value) < 32:
        raise SnapshotPlanError("Receipt key must contain at least 32 bytes")
    return value


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError, RecursionError):
        raise SnapshotPlanError("Value is not canonical JSON") from None


def _plain_executable(value: str) -> None:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise SnapshotPlanError("Invalid Docker executable")
