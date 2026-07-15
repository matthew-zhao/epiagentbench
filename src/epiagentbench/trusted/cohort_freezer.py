"""Freeze private Starsim episode identities without observing any outcomes.

This module samples only episode-generation inputs and writes authenticated
private artifacts.  It never constructs a Starsim backend, simulates an
infection, applies an admission rule, scores an episode, or executes Docker.
Consequently, freezing a cohort is not blind scientific validation and must
not be reported as evidence that the simulator is realistic.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
from importlib import metadata as importlib_metadata
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys
from typing import Any, Mapping

from .episode_pack import (
    PrivateEpisodeCohortManifest,
    PrivateEpisodePack,
)
from .starsim_episode import LIVE_FAMILY_TO_MODE


_FINGERPRINT_DOMAIN = b"EpiAgentBench generator implementation fingerprint v2\x00"
_FREEZE_FORMAT = "epiagentbench.private-cohort-freeze-result.v1"
_COHORT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_PACKAGE_NAMES = ("epiagentbench", "epiagentbench_client")
_SOURCE_SUFFIXES = frozenset({".py", ".json"})
# This is the scientific execution stack declared by the Starsim extra and by
# Starsim 3.5.1 itself.  Versions and wheel RECORD commitments are included;
# absolute installation paths are deliberately excluded.
_RUNTIME_DISTRIBUTIONS = (
    "epiagentbench",
    "matplotlib",
    "networkx",
    "numba",
    "numpy",
    "pandas",
    "scipy",
    "sciris",
    "seaborn",
    "starsim",
)
_MAX_KEY_BYTES = 4_096
_MAX_FINGERPRINT_INPUT_BYTES = 64 * 1024 * 1024
_MAX_EPISODES = 20_000
_INCOMPLETE_MARKER = ".freeze-incomplete"
_MANIFEST_NAME = "cohort.manifest"


class CohortFreezeError(ValueError):
    """Raised when a private cohort cannot be frozen safely."""


@dataclass(frozen=True, slots=True)
class FrozenPrivateCohort:
    """Public-only result of writing one private cohort."""

    public_descriptor: Mapping[str, Any]
    cohort_directory: Path
    manifest_path: Path
    pack_paths: tuple[Path, ...]

    def as_public_dict(self) -> dict[str, Any]:
        """Return only publishable metadata and artifact paths."""

        return {
            "public_descriptor": dict(self.public_descriptor),
            "paths": {
                "cohort_directory": str(self.cohort_directory),
                "manifest": str(self.manifest_path),
                "packs": [str(path) for path in self.pack_paths],
            },
        }


def compute_generator_fingerprint(
    *,
    source_root: str | Path | None = None,
    candidate_profile_bytes: bytes | None = None,
) -> str:
    """Hash package, project, dependency, runtime, and optional profile inputs.

    Absolute checkout paths and file metadata are excluded.  Canonical package
    relative paths, byte lengths, exact contents, ``pyproject.toml``, Python
    runtime identity, and relevant installed distribution identities are
    included.  Distribution identities contain version and wheel ``RECORD``
    commitment, never an installation path.  The same source and runtime stack
    therefore hashes identically after being copied elsewhere.
    """

    if (
        candidate_profile_bytes is not None
        and (
            type(candidate_profile_bytes) is not bytes
            or len(candidate_profile_bytes) > _MAX_FINGERPRINT_INPUT_BYTES
        )
    ):
        raise CohortFreezeError(
            "Candidate profile must be bounded bytes when provided"
        )
    root = (
        Path(__file__).resolve().parents[2]
        if source_root is None
        else Path(source_root).expanduser().resolve(strict=True)
    )
    if not root.is_dir():
        raise CohortFreezeError("Generator source root must be a directory")

    files: list[tuple[str, Path]] = []
    for package_name in _PACKAGE_NAMES:
        package = root / package_name
        if not package.is_dir() or package.is_symlink():
            raise CohortFreezeError(
                f"Generator source root is missing package {package_name!r}"
            )
        for current, directories, filenames in os.walk(package, followlinks=False):
            current_path = Path(current)
            for directory in tuple(directories):
                child = current_path / directory
                if child.is_symlink():
                    raise CohortFreezeError(
                        "Generator source tree cannot contain symlink directories"
                    )
            for filename in filenames:
                path = current_path / filename
                if path.suffix.lower() not in _SOURCE_SUFFIXES:
                    continue
                if path.is_symlink():
                    raise CohortFreezeError(
                        "Generator source tree cannot contain symlink files"
                    )
                relative = path.relative_to(root).as_posix()
                files.append((relative, path))
    files.sort(key=lambda item: item[0])
    if not files:
        raise CohortFreezeError("Generator source inventory is empty")

    project_file = _project_manifest_for_source_root(root)
    runtime_identity = {
        "python": {
            "implementation": sys.implementation.name,
            "cache_tag": sys.implementation.cache_tag,
            "version": list(sys.version_info[:3]),
            "byteorder": sys.byteorder,
        },
        "distributions": {
            name: _distribution_identity(name)
            for name in _RUNTIME_DISTRIBUTIONS
        },
    }

    digest = hashlib.sha256()
    digest.update(_FINGERPRINT_DOMAIN)
    for relative, path in files:
        _hash_field(digest, b"path", relative.encode("utf-8"))
        _hash_field(
            digest,
            b"contents",
            _read_stable_regular_file(
                path, maximum_bytes=_MAX_FINGERPRINT_INPUT_BYTES
            ),
        )
    if project_file is None:
        _hash_field(digest, b"project-manifest-state", b"absent")
    else:
        _hash_field(digest, b"project-manifest-state", b"present")
        _hash_field(digest, b"project-manifest-path", b"pyproject.toml")
        _hash_field(
            digest,
            b"project-manifest-contents",
            _read_stable_regular_file(
                project_file, maximum_bytes=_MAX_FINGERPRINT_INPUT_BYTES
            ),
        )
    _hash_field(
        digest,
        b"runtime-identity",
        json.dumps(
            runtime_identity,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("ascii"),
    )
    if candidate_profile_bytes is None:
        _hash_field(digest, b"candidate-profile-state", b"absent")
    else:
        _hash_field(digest, b"candidate-profile-state", b"present")
        _hash_field(digest, b"candidate-profile", candidate_profile_bytes)
    return f"sha256:{digest.hexdigest()}"


def _project_manifest_for_source_root(root: Path) -> Path | None:
    """Locate only the project manifest paired with this canonical source root."""

    candidates = [root / "pyproject.toml"]
    if root.name == "src":
        candidates.append(root.parent / "pyproject.toml")
    present = [path for path in candidates if path.exists() or path.is_symlink()]
    if len(present) > 1:
        raise CohortFreezeError("Generator source has ambiguous project manifests")
    if not present:
        return None
    manifest = present[0]
    if manifest.is_symlink() or not manifest.is_file():
        raise CohortFreezeError("Project manifest must be a regular non-symlink file")
    return manifest


def _distribution_identity(name: str) -> Mapping[str, str | None]:
    """Return a path-independent identity for one relevant distribution."""

    try:
        distribution = importlib_metadata.distribution(name)
    except importlib_metadata.PackageNotFoundError:
        return {"version": None, "record_sha256": None}
    version = distribution.version
    record = distribution.read_text("RECORD")
    record_sha256 = (
        hashlib.sha256(record.encode("utf-8")).hexdigest()
        if record is not None
        else None
    )
    return {"version": version, "record_sha256": record_sha256}


def freeze_private_starsim_cohort(
    *,
    cohort_id: str,
    output_directory: str | Path,
    authentication_key_file: str | Path,
    episodes: int = 100,
) -> FrozenPrivateCohort:
    """Write exactly ``episodes`` balanced, outcome-unobserved private packs.

    ``output_directory`` must not exist.  A marker remains if a write fails;
    only a directory containing the authenticated manifest and no marker is a
    completed freeze.  The authentication key is read from a separate,
    owner-only file and is never copied into the cohort or returned.
    """

    if not isinstance(cohort_id, str) or not _COHORT_ID.fullmatch(cohort_id):
        raise CohortFreezeError("Invalid cohort identifier")
    if type(episodes) is not int or not 5 <= episodes <= _MAX_EPISODES:
        raise CohortFreezeError(
            "Episode count must be an integer from five through 20000"
        )
    if len(LIVE_FAMILY_TO_MODE) != 5 or len(set(LIVE_FAMILY_TO_MODE.values())) != 5:
        raise CohortFreezeError("Expected exactly five configured live Starsim modes")

    destination = _new_cohort_destination(output_directory)
    key_path = _existing_path_without_final_symlink(authentication_key_file)
    if key_path == destination or destination in key_path.parents:
        raise CohortFreezeError(
            "Authentication key file must be outside the cohort directory"
        )
    authentication_key = _read_authentication_key(key_path)
    if destination.exists() or destination.is_symlink():
        raise CohortFreezeError("Cohort output directory must not already exist")

    # External candidate profiles are intentionally unsupported until the
    # evaluator can authenticate and load those exact bytes at replay.  The
    # bundled profile JSON is already included in this package fingerprint.
    generator_fingerprint = compute_generator_fingerprint()

    families = _balanced_private_family_order(episodes)
    seeds_seen: set[int] = set()
    random_bytes_seen: set[bytes] = set()
    packs: list[PrivateEpisodePack] = []
    for episode_index, family in enumerate(families):
        seed = _unique_private_seed(seeds_seen)
        episode_secret = _unique_private_bytes(random_bytes_seen)
        commitment_nonce = _unique_private_bytes(random_bytes_seen)
        packs.append(
            PrivateEpisodePack.create(
                cohort_id=cohort_id,
                episode_index=episode_index,
                backend="starsim",
                family=family,
                seed=seed,
                generator_fingerprint=generator_fingerprint,
                episode_secret=episode_secret,
                commitment_nonce=commitment_nonce,
            )
        )
    manifest_nonce = _unique_private_bytes(random_bytes_seen)
    manifest = PrivateEpisodeCohortManifest.create(
        packs, manifest_nonce=manifest_nonce
    )

    try:
        os.mkdir(destination, 0o700)
        os.chmod(destination, 0o700)
    except FileExistsError:
        raise CohortFreezeError(
            "Cohort output directory must not already exist"
        ) from None
    _assert_private_directory(destination)
    marker_path = destination / _INCOMPLETE_MARKER
    _write_exclusive_private_file(marker_path, b"incomplete\n")

    pack_paths = tuple(
        destination / f"episode-{index:06d}.pack"
        for index in range(episodes)
    )
    manifest_path = destination / _MANIFEST_NAME
    try:
        for pack, pack_path in zip(packs, pack_paths):
            pack.write(pack_path, authentication_key)
        manifest.write(manifest_path, authentication_key)

        # Authenticate the completed disk artifacts before removing the marker.
        opened_manifest = PrivateEpisodeCohortManifest.read(
            manifest_path, authentication_key
        )
        if opened_manifest != manifest:
            raise CohortFreezeError("Frozen cohort manifest replay mismatch")
        for expected, pack_path in zip(packs, pack_paths):
            opened = PrivateEpisodePack.read(pack_path, authentication_key)
            if opened != expected:
                raise CohortFreezeError("Frozen episode pack replay mismatch")
            opened_manifest.assert_contains(opened)

        if compute_generator_fingerprint() != generator_fingerprint:
            raise CohortFreezeError(
                "Generator source changed during freeze"
            )

        marker_path.unlink()
        _fsync_directory(destination)
    except Exception:
        # Deliberately leave the owner-only directory and marker in place.  A
        # partial freeze is never silently reused or mistaken for a cohort.
        raise

    mode_counts = Counter(LIVE_FAMILY_TO_MODE[pack.family] for pack in packs)
    descriptor = {
        **manifest.public_descriptor,
        "freeze_format": _FREEZE_FORMAT,
        "backend": "starsim",
        "design": "balanced_five_mode",
        "mode_counts": {
            mode: mode_counts[mode]
            for mode in sorted(LIVE_FAMILY_TO_MODE.values())
        },
        "profile_source": "bundled_package_profile_only",
        "generation_policy": "random_private_inputs_without_outcome_filtering",
        "blind_scientific_validation_run": False,
        "docker_execution_run": False,
        "scientific_status": (
            "cohort identities frozen; no simulation, outcome filtering, or "
            "blind scientific validation was run"
        ),
        "execution_status": "no Docker or agent execution was run",
    }
    return FrozenPrivateCohort(
        public_descriptor=descriptor,
        cohort_directory=destination,
        manifest_path=manifest_path,
        pack_paths=pack_paths,
    )


def _balanced_private_family_order(episodes: int) -> tuple[str, ...]:
    families = tuple(LIVE_FAMILY_TO_MODE)
    base, remainder = divmod(episodes, len(families))
    assignments: list[str] = []
    for index, family in enumerate(families):
        assignments.extend([family] * (base + (index < remainder)))
    secrets.SystemRandom().shuffle(assignments)
    return tuple(assignments)


def _unique_private_seed(seen: set[int]) -> int:
    while True:
        seed = secrets.randbelow(2**53)
        if seed not in seen:
            seen.add(seed)
            return seed


def _unique_private_bytes(seen: set[bytes]) -> bytes:
    while True:
        value = secrets.token_bytes(32)
        if value not in seen:
            seen.add(value)
            return value


def _hash_field(digest: Any, label: bytes, value: bytes) -> None:
    digest.update(len(label).to_bytes(4, "big"))
    digest.update(label)
    digest.update(len(value).to_bytes(8, "big"))
    digest.update(value)


def _new_cohort_destination(value: str | Path) -> Path:
    raw = Path(value).expanduser()
    if not raw.is_absolute():
        raw = Path.cwd() / raw
    try:
        parent = raw.parent.resolve(strict=True)
    except OSError:
        raise CohortFreezeError(
            "Cohort output parent must be an existing directory"
        ) from None
    if not parent.is_dir() or raw.name in {"", ".", ".."}:
        raise CohortFreezeError(
            "Cohort output parent must be an existing directory"
        )
    return parent / raw.name


def _existing_path_without_final_symlink(value: str | Path) -> Path:
    raw = Path(value).expanduser()
    if not raw.is_absolute():
        raw = Path.cwd() / raw
    try:
        parent = raw.parent.resolve(strict=True)
    except OSError:
        raise CohortFreezeError("Required private file is unavailable") from None
    path = parent / raw.name
    try:
        metadata = path.lstat()
    except OSError:
        raise CohortFreezeError("Required private file is unavailable") from None
    if not stat.S_ISREG(metadata.st_mode):
        raise CohortFreezeError("Required private file must be a regular file")
    return path


def _read_authentication_key(path: Path) -> bytes:
    metadata = path.lstat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_mode & 0o077
        or metadata.st_uid != os.geteuid()
        or not 32 <= metadata.st_size <= _MAX_KEY_BYTES
    ):
        raise CohortFreezeError(
            "Authentication key must be an owner-only regular file of 32-4096 bytes"
        )
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            opened = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_mode & 0o077
                or opened.st_uid != os.geteuid()
                or not 32 <= opened.st_size <= _MAX_KEY_BYTES
                or (opened.st_dev, opened.st_ino)
                != (metadata.st_dev, metadata.st_ino)
            ):
                raise CohortFreezeError("Authentication key changed while opening")
            key = stream.read(_MAX_KEY_BYTES + 1)
    except OSError:
        raise CohortFreezeError("Authentication key is unavailable") from None
    if len(key) != opened.st_size:
        raise CohortFreezeError("Authentication key changed while reading")
    return key


def _read_stable_regular_file(path: Path, *, maximum_bytes: int) -> bytes:
    try:
        before = path.lstat()
    except OSError:
        raise CohortFreezeError("Fingerprint input is unavailable") from None
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_size < 0
        or before.st_size > maximum_bytes
    ):
        raise CohortFreezeError("Fingerprint input must be a bounded regular file")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            opened = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_size > maximum_bytes
                or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
            ):
                raise CohortFreezeError("Fingerprint input changed while opening")
            data = stream.read(maximum_bytes + 1)
            after = os.fstat(stream.fileno())
    except OSError:
        raise CohortFreezeError("Fingerprint input is unavailable") from None
    if (
        len(data) != opened.st_size
        or after.st_size != opened.st_size
        or after.st_mtime_ns != opened.st_mtime_ns
    ):
        raise CohortFreezeError("Fingerprint input changed while reading")
    return data


def _write_exclusive_private_file(path: Path, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "wb", closefd=True) as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _assert_private_directory(path: Path) -> None:
    metadata = path.lstat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_mode & 0o077
        or metadata.st_uid != os.geteuid()
    ):
        raise CohortFreezeError("Cohort directory is not owner-only")


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
