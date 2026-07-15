"""Authenticated, evaluator-private episode replay artifacts.

The public commitment is safe to place in a run manifest.  The serialized pack
is not public: it contains the seed, family, and presentation secret needed to
create an exact fresh evaluator for each compared system.  Confidentiality at
rest is supplied by owner-only filesystem permissions; the HMAC supplies
integrity and evaluator authentication, not encryption.
"""

from __future__ import annotations

from dataclasses import dataclass
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import stat
from typing import Any, NoReturn, Sequence


_FORMAT = "epiagentbench.private-episode-pack.v1"
_COHORT_FORMAT = "epiagentbench.private-episode-cohort.v1"
_COMMIT_DOMAIN = b"EpiAgentBench private episode commitment v1\x00"
_AUTH_DOMAIN = b"EpiAgentBench private episode pack authentication v1\x00"
_COHORT_COMMIT_DOMAIN = b"EpiAgentBench private cohort commitment v1\x00"
_COHORT_AUTH_DOMAIN = b"EpiAgentBench private cohort authentication v1\x00"
_MAX_PACK_BYTES = 65_536
_MAX_COHORT_BYTES = 4_194_304
_MAX_COHORT_EPISODES = 20_000
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")


class EpisodePackError(ValueError):
    """Raised when a private episode pack is malformed or unauthenticated."""


@dataclass(frozen=True, slots=True)
class PrivateEpisodePack:
    """The complete private identity of one reproducible evaluator episode."""

    cohort_id: str
    episode_index: int
    backend: str
    family: str | None
    seed: int
    episode_secret: bytes
    generator_fingerprint: str
    commitment_nonce: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.cohort_id, str) or not _IDENTIFIER.fullmatch(
            self.cohort_id
        ):
            raise EpisodePackError("Invalid cohort identifier")
        if type(self.episode_index) is not int or not (
            0 <= self.episode_index <= 2**53 - 1
        ):
            raise EpisodePackError("Invalid episode index")
        if not isinstance(self.backend, str) or not _IDENTIFIER.fullmatch(
            self.backend
        ):
            raise EpisodePackError("Invalid backend identifier")
        if self.family is not None and (
            not isinstance(self.family, str)
            or not _IDENTIFIER.fullmatch(self.family)
        ):
            raise EpisodePackError("Invalid family identifier")
        if type(self.seed) is not int or not 0 <= self.seed <= 2**53 - 1:
            raise EpisodePackError("Invalid private seed")
        if type(self.episode_secret) is not bytes or len(self.episode_secret) != 32:
            raise EpisodePackError("Episode secret must contain exactly 32 bytes")
        if not isinstance(
            self.generator_fingerprint, str
        ) or not _FINGERPRINT.fullmatch(self.generator_fingerprint):
            raise EpisodePackError("Invalid generator fingerprint")
        if (
            type(self.commitment_nonce) is not bytes
            or len(self.commitment_nonce) != 32
        ):
            raise EpisodePackError("Commitment nonce must contain exactly 32 bytes")

    @classmethod
    def create(
        cls,
        *,
        cohort_id: str,
        episode_index: int,
        backend: str,
        family: str | None,
        seed: int,
        generator_fingerprint: str,
        episode_secret: bytes | None = None,
        commitment_nonce: bytes | None = None,
    ) -> PrivateEpisodePack:
        """Create a pack without deriving secrets from low-entropy metadata."""

        return cls(
            cohort_id=cohort_id,
            episode_index=episode_index,
            backend=backend,
            family=family,
            seed=seed,
            episode_secret=(
                secrets.token_bytes(32)
                if episode_secret is None
                else episode_secret
            ),
            generator_fingerprint=generator_fingerprint,
            commitment_nonce=(
                secrets.token_bytes(32)
                if commitment_nonce is None
                else commitment_nonce
            ),
        )

    @property
    def commitment(self) -> str:
        """Return a hiding commitment to every private generation input."""

        digest = hashlib.sha256(
            _COMMIT_DOMAIN + _canonical_json(self._private_payload())
        ).hexdigest()
        return f"sha256:{digest}"

    @property
    def public_descriptor(self) -> dict[str, str]:
        """Return the only pack metadata intended for an agent-facing record."""

        return {
            "format": _FORMAT,
            "cohort_id": self.cohort_id,
            "commitment": self.commitment,
        }

    def launch_kwargs(
        self,
        *,
        expected_generator_fingerprint: str,
        cohort_manifest: PrivateEpisodeCohortManifest,
        expected_pack_set_commitment: str,
    ) -> dict[str, str | int | bytes | None]:
        """Return replay arguments only after every frozen-set gate passes.

        Requiring these values at the launch boundary prevents a caller from
        accidentally skipping the generator check or substituting a different,
        individually authentic pack from the same storage area.
        """

        self.assert_generator(expected_generator_fingerprint)
        if not isinstance(cohort_manifest, PrivateEpisodeCohortManifest):
            raise EpisodePackError("Authenticated cohort manifest is required")
        cohort_manifest.assert_commitment(expected_pack_set_commitment)
        cohort_manifest.assert_contains(self)

        return {
            "seed": self.seed,
            "family": self.family,
            "backend": self.backend,
            "episode_secret": self.episode_secret,
        }

    def assert_generator(self, fingerprint: str) -> None:
        """Fail closed rather than replaying against a different generator."""

        if not hmac.compare_digest(self.generator_fingerprint, fingerprint):
            raise EpisodePackError("Episode generator fingerprint mismatch")

    def seal(self, authentication_key: bytes) -> bytes:
        """Serialize and authenticate this evaluator-private pack."""

        key = _authentication_key(authentication_key)
        body = {
            "format": _FORMAT,
            "payload": self._private_payload(),
            "commitment": self.commitment,
        }
        tag = hmac.new(
            key, _AUTH_DOMAIN + _canonical_json(body), hashlib.sha256
        ).hexdigest()
        return _canonical_json(
            {
                **body,
                "authentication": {
                    "algorithm": "hmac-sha256",
                    "tag": tag,
                },
            }
        )

    @classmethod
    def unseal(
        cls, payload: bytes, authentication_key: bytes
    ) -> PrivateEpisodePack:
        """Authenticate and parse a private pack with strict JSON handling."""

        key = _authentication_key(authentication_key)
        if type(payload) is not bytes or not 0 < len(payload) <= _MAX_PACK_BYTES:
            raise EpisodePackError("Invalid private episode pack")
        try:
            value = json.loads(
                payload.decode("utf-8"),
                object_pairs_hook=_unique_object,
                parse_constant=_reject_constant,
            )
        except (UnicodeDecodeError, ValueError, RecursionError):
            raise EpisodePackError("Invalid private episode pack") from None
        if not isinstance(value, dict) or set(value) != {
            "format",
            "payload",
            "commitment",
            "authentication",
        }:
            raise EpisodePackError("Invalid private episode pack")
        authentication = value["authentication"]
        if not isinstance(authentication, dict) or set(authentication) != {
            "algorithm",
            "tag",
        } or authentication.get("algorithm") != "hmac-sha256":
            raise EpisodePackError("Invalid private episode pack")
        body = {
            "format": value["format"],
            "payload": value["payload"],
            "commitment": value["commitment"],
        }
        expected_tag = hmac.new(
            key, _AUTH_DOMAIN + _canonical_json(body), hashlib.sha256
        ).hexdigest()
        tag = authentication.get("tag")
        if not isinstance(tag, str) or not hmac.compare_digest(tag, expected_tag):
            raise EpisodePackError("Private episode pack authentication failed")
        if body["format"] != _FORMAT or not isinstance(body["payload"], dict):
            raise EpisodePackError("Invalid private episode pack")
        pack = cls._from_private_payload(body["payload"])
        commitment = body["commitment"]
        if not isinstance(commitment, str) or not hmac.compare_digest(
            commitment, pack.commitment
        ):
            raise EpisodePackError("Private episode pack commitment mismatch")
        return pack

    def write(self, path: str | Path, authentication_key: bytes) -> None:
        """Create an owner-only pack file without following a final symlink."""

        destination = Path(path)
        if not destination.is_absolute() or not destination.parent.is_dir():
            raise EpisodePackError("Private pack path must have an existing parent")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        data = self.seal(authentication_key)
        descriptor: int | None = None
        created = False
        try:
            descriptor = os.open(destination, flags, 0o600)
            created = True
            with os.fdopen(descriptor, "wb", closefd=True) as stream:
                descriptor = None
                os.fchmod(stream.fileno(), 0o600)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            if descriptor is not None:
                os.close(descriptor)
            if created:
                try:
                    destination.unlink()
                except OSError:
                    pass
            raise

    @classmethod
    def read(
        cls, path: str | Path, authentication_key: bytes
    ) -> PrivateEpisodePack:
        """Read only a small, regular, owner-private pack file."""

        source = Path(path)
        try:
            metadata = source.lstat()
        except OSError:
            raise EpisodePackError("Private episode pack unavailable") from None
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_mode & 0o077
            or not 0 < metadata.st_size <= _MAX_PACK_BYTES
        ):
            raise EpisodePackError("Unsafe private episode pack permissions")
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(source, flags)
            with os.fdopen(descriptor, "rb", closefd=True) as stream:
                opened = os.fstat(stream.fileno())
                if (
                    not stat.S_ISREG(opened.st_mode)
                    or opened.st_mode & 0o077
                    or not 0 < opened.st_size <= _MAX_PACK_BYTES
                ):
                    raise EpisodePackError(
                        "Unsafe private episode pack permissions"
                    )
                data = stream.read(_MAX_PACK_BYTES + 1)
        except OSError:
            raise EpisodePackError("Private episode pack unavailable") from None
        return cls.unseal(data, authentication_key)

    def _private_payload(self) -> dict[str, Any]:
        return {
            "cohort_id": self.cohort_id,
            "episode_index": self.episode_index,
            "backend": self.backend,
            "family": self.family,
            "seed": self.seed,
            "episode_secret": base64.b64encode(self.episode_secret).decode("ascii"),
            "generator_fingerprint": self.generator_fingerprint,
            "commitment_nonce": base64.b64encode(self.commitment_nonce).decode(
                "ascii"
            ),
        }

    @classmethod
    def _from_private_payload(cls, value: dict[str, Any]) -> PrivateEpisodePack:
        if set(value) != {
            "cohort_id",
            "episode_index",
            "backend",
            "family",
            "seed",
            "episode_secret",
            "generator_fingerprint",
            "commitment_nonce",
        }:
            raise EpisodePackError("Invalid private episode pack")
        try:
            secret = base64.b64decode(value["episode_secret"], validate=True)
            nonce = base64.b64decode(value["commitment_nonce"], validate=True)
        except (TypeError, ValueError):
            raise EpisodePackError("Invalid private episode pack") from None
        return cls(
            cohort_id=value["cohort_id"],
            episode_index=value["episode_index"],
            backend=value["backend"],
            family=value["family"],
            seed=value["seed"],
            episode_secret=secret,
            generator_fingerprint=value["generator_fingerprint"],
            commitment_nonce=nonce,
        )


@dataclass(frozen=True, slots=True)
class PrivateEpisodeCohortManifest:
    """Authenticated exact membership list for one frozen private cohort.

    The manifest contains only hiding pack commitments, never episode seeds,
    families, or presentation secrets.  Its public commitment can be pinned or
    timestamped before systems are evaluated, while its HMAC prevents an
    unauthenticated party from editing the membership list in storage.
    """

    cohort_id: str
    generator_fingerprint: str
    episodes: tuple[tuple[int, str], ...]
    manifest_nonce: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.cohort_id, str) or not _IDENTIFIER.fullmatch(
            self.cohort_id
        ):
            raise EpisodePackError("Invalid cohort identifier")
        if not isinstance(
            self.generator_fingerprint, str
        ) or not _FINGERPRINT.fullmatch(self.generator_fingerprint):
            raise EpisodePackError("Invalid generator fingerprint")
        if type(self.episodes) is not tuple or not (
            1 <= len(self.episodes) <= _MAX_COHORT_EPISODES
        ):
            raise EpisodePackError("Invalid frozen cohort membership")
        normalized: list[tuple[int, str]] = []
        for entry in self.episodes:
            if type(entry) is not tuple or len(entry) != 2:
                raise EpisodePackError("Invalid frozen cohort membership")
            index, commitment = entry
            if (
                type(index) is not int
                or not 0 <= index <= 2**53 - 1
                or not isinstance(commitment, str)
                or not _FINGERPRINT.fullmatch(commitment)
            ):
                raise EpisodePackError("Invalid frozen cohort membership")
            normalized.append((index, commitment))
        if (
            normalized != sorted(normalized)
            or len({index for index, _ in normalized}) != len(normalized)
            or len({commitment for _, commitment in normalized}) != len(normalized)
        ):
            raise EpisodePackError("Frozen cohort entries must be unique and sorted")
        if type(self.manifest_nonce) is not bytes or len(self.manifest_nonce) != 32:
            raise EpisodePackError("Manifest nonce must contain exactly 32 bytes")

    @classmethod
    def create(
        cls,
        packs: Sequence[PrivateEpisodePack],
        *,
        manifest_nonce: bytes | None = None,
    ) -> PrivateEpisodeCohortManifest:
        """Freeze the complete, index-addressed set of private pack commitments."""

        if isinstance(packs, (str, bytes)) or not isinstance(packs, Sequence):
            raise EpisodePackError("Private cohort must be a non-empty sequence")
        materialized = tuple(packs)
        if not materialized or any(
            not isinstance(pack, PrivateEpisodePack) for pack in materialized
        ):
            raise EpisodePackError("Private cohort must contain episode packs")
        first = materialized[0]
        if any(
            pack.cohort_id != first.cohort_id
            or pack.generator_fingerprint != first.generator_fingerprint
            for pack in materialized
        ):
            raise EpisodePackError(
                "Private cohort packs must share a cohort and generator"
            )
        episodes = tuple(
            sorted((pack.episode_index, pack.commitment) for pack in materialized)
        )
        return cls(
            cohort_id=first.cohort_id,
            generator_fingerprint=first.generator_fingerprint,
            episodes=episodes,
            manifest_nonce=(
                secrets.token_bytes(32)
                if manifest_nonce is None
                else manifest_nonce
            ),
        )

    @property
    def pack_set_commitment(self) -> str:
        """Commit to the exact index-to-pack mapping of the frozen cohort."""

        digest = hashlib.sha256(
            _COHORT_COMMIT_DOMAIN + _canonical_json(self._payload())
        ).hexdigest()
        return f"sha256:{digest}"

    @property
    def public_descriptor(self) -> dict[str, str | int]:
        """Return publishable proof metadata without per-episode identifiers."""

        return {
            "format": _COHORT_FORMAT,
            "cohort_id": self.cohort_id,
            "episode_count": len(self.episodes),
            "generator_fingerprint": self.generator_fingerprint,
            "pack_set_commitment": self.pack_set_commitment,
        }

    def assert_commitment(self, expected: str) -> None:
        """Require the externally pinned exact-set commitment."""

        if not isinstance(expected, str) or not _FINGERPRINT.fullmatch(expected):
            raise EpisodePackError("Invalid expected pack-set commitment")
        if not hmac.compare_digest(self.pack_set_commitment, expected):
            raise EpisodePackError("Frozen pack-set commitment mismatch")

    def assert_contains(self, pack: PrivateEpisodePack) -> None:
        """Require an exact pack commitment at its frozen episode index."""

        if not isinstance(pack, PrivateEpisodePack):
            raise EpisodePackError("Invalid private episode pack")
        if (
            pack.cohort_id != self.cohort_id
            or pack.generator_fingerprint != self.generator_fingerprint
        ):
            raise EpisodePackError("Private pack is outside the frozen cohort")
        expected = dict(self.episodes).get(pack.episode_index)
        if expected is None or not hmac.compare_digest(expected, pack.commitment):
            raise EpisodePackError("Private pack is outside the frozen cohort")

    def seal(self, authentication_key: bytes) -> bytes:
        """Serialize and authenticate the exact frozen membership list."""

        key = _authentication_key(authentication_key)
        body = {
            "format": _COHORT_FORMAT,
            "payload": self._payload(),
            "pack_set_commitment": self.pack_set_commitment,
        }
        tag = hmac.new(
            key, _COHORT_AUTH_DOMAIN + _canonical_json(body), hashlib.sha256
        ).hexdigest()
        sealed = _canonical_json(
            {
                **body,
                "authentication": {
                    "algorithm": "hmac-sha256",
                    "tag": tag,
                },
            }
        )
        if len(sealed) > _MAX_COHORT_BYTES:
            raise EpisodePackError("Private cohort manifest is too large")
        return sealed

    def write(self, path: str | Path, authentication_key: bytes) -> None:
        """Create an owner-only manifest without replacing an existing path."""

        destination = Path(path)
        if not destination.is_absolute() or not destination.parent.is_dir():
            raise EpisodePackError(
                "Private cohort path must have an existing parent"
            )
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        data = self.seal(authentication_key)
        descriptor: int | None = None
        created = False
        try:
            descriptor = os.open(destination, flags, 0o600)
            created = True
            with os.fdopen(descriptor, "wb", closefd=True) as stream:
                descriptor = None
                os.fchmod(stream.fileno(), 0o600)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            if descriptor is not None:
                os.close(descriptor)
            if created:
                try:
                    destination.unlink()
                except OSError:
                    pass
            raise

    @classmethod
    def read(
        cls, path: str | Path, authentication_key: bytes
    ) -> PrivateEpisodeCohortManifest:
        """Read only a small, regular, owner-private cohort manifest."""

        source = Path(path)
        try:
            metadata = source.lstat()
        except OSError:
            raise EpisodePackError("Private cohort manifest unavailable") from None
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_mode & 0o077
            or not 0 < metadata.st_size <= _MAX_COHORT_BYTES
        ):
            raise EpisodePackError("Unsafe private cohort manifest permissions")
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(source, flags)
            with os.fdopen(descriptor, "rb", closefd=True) as stream:
                opened = os.fstat(stream.fileno())
                if (
                    not stat.S_ISREG(opened.st_mode)
                    or opened.st_mode & 0o077
                    or not 0 < opened.st_size <= _MAX_COHORT_BYTES
                    or (opened.st_dev, opened.st_ino)
                    != (metadata.st_dev, metadata.st_ino)
                ):
                    raise EpisodePackError(
                        "Unsafe private cohort manifest permissions"
                    )
                data = stream.read(_MAX_COHORT_BYTES + 1)
        except OSError:
            raise EpisodePackError("Private cohort manifest unavailable") from None
        return cls.unseal(data, authentication_key)

    @classmethod
    def unseal(
        cls, payload: bytes, authentication_key: bytes
    ) -> PrivateEpisodeCohortManifest:
        """Authenticate and strictly parse a frozen cohort manifest."""

        key = _authentication_key(authentication_key)
        if type(payload) is not bytes or not 0 < len(payload) <= _MAX_COHORT_BYTES:
            raise EpisodePackError("Invalid private cohort manifest")
        try:
            value = json.loads(
                payload.decode("utf-8"),
                object_pairs_hook=_unique_object,
                parse_constant=_reject_constant,
            )
        except (UnicodeDecodeError, ValueError, RecursionError):
            raise EpisodePackError("Invalid private cohort manifest") from None
        if not isinstance(value, dict) or set(value) != {
            "format",
            "payload",
            "pack_set_commitment",
            "authentication",
        }:
            raise EpisodePackError("Invalid private cohort manifest")
        authentication = value["authentication"]
        if (
            not isinstance(authentication, dict)
            or set(authentication) != {"algorithm", "tag"}
            or authentication.get("algorithm") != "hmac-sha256"
        ):
            raise EpisodePackError("Invalid private cohort manifest")
        body = {
            "format": value["format"],
            "payload": value["payload"],
            "pack_set_commitment": value["pack_set_commitment"],
        }
        expected_tag = hmac.new(
            key, _COHORT_AUTH_DOMAIN + _canonical_json(body), hashlib.sha256
        ).hexdigest()
        tag = authentication.get("tag")
        if not isinstance(tag, str) or not hmac.compare_digest(tag, expected_tag):
            raise EpisodePackError("Private cohort authentication failed")
        if body["format"] != _COHORT_FORMAT or not isinstance(
            body["payload"], dict
        ):
            raise EpisodePackError("Invalid private cohort manifest")
        manifest = cls._from_payload(body["payload"])
        commitment = body["pack_set_commitment"]
        if not isinstance(commitment, str) or not hmac.compare_digest(
            commitment, manifest.pack_set_commitment
        ):
            raise EpisodePackError("Private cohort commitment mismatch")
        return manifest

    def _payload(self) -> dict[str, Any]:
        return {
            "cohort_id": self.cohort_id,
            "generator_fingerprint": self.generator_fingerprint,
            "episodes": [
                {"episode_index": index, "commitment": commitment}
                for index, commitment in self.episodes
            ],
            "manifest_nonce": base64.b64encode(self.manifest_nonce).decode("ascii"),
        }

    @classmethod
    def _from_payload(
        cls, value: dict[str, Any]
    ) -> PrivateEpisodeCohortManifest:
        if set(value) != {
            "cohort_id",
            "generator_fingerprint",
            "episodes",
            "manifest_nonce",
        } or not isinstance(value["episodes"], list):
            raise EpisodePackError("Invalid private cohort manifest")
        episodes: list[tuple[int, str]] = []
        for entry in value["episodes"]:
            if not isinstance(entry, dict) or set(entry) != {
                "episode_index",
                "commitment",
            }:
                raise EpisodePackError("Invalid private cohort manifest")
            episodes.append((entry["episode_index"], entry["commitment"]))
        try:
            nonce = base64.b64decode(value["manifest_nonce"], validate=True)
        except (TypeError, ValueError):
            raise EpisodePackError("Invalid private cohort manifest") from None
        return cls(
            cohort_id=value["cohort_id"],
            generator_fingerprint=value["generator_fingerprint"],
            episodes=tuple(episodes),
            manifest_nonce=nonce,
        )


def _authentication_key(value: bytes) -> bytes:
    if type(value) is not bytes or len(value) < 32:
        raise EpisodePackError("Authentication key must contain at least 32 bytes")
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
        raise EpisodePackError("Value is not canonical JSON") from None


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, child in pairs:
        if key in value:
            raise EpisodePackError("Duplicate JSON key")
        value[key] = child
    return value


def _reject_constant(_: str) -> NoReturn:
    raise EpisodePackError("Non-finite JSON number")
