"""Closed, credential-free provider CLI discovery.

Provider programs are selected from source-owned directories instead of the
caller's ``PATH`` or ``HOME``.  Callers may publish the path-free role and
entrypoint kind, but must keep the resolved paths private.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import pwd
import stat
from typing import Any


SYSTEM_PROCESS_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"
ALLOWED_PROVIDER_EXECUTABLES = frozenset(
    {"claude", "codex", "cursor-agent"}
)
_MAX_INSTALLATION_ENTRIES = 2_048
_MAX_INSTALLATION_FILE_BYTES = 512 * 1024 * 1024
_MAX_INSTALLATION_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
_STABLE_FILE_FIELDS = (
    "st_dev",
    "st_ino",
    "st_mode",
    "st_uid",
    "st_gid",
    "st_nlink",
    "st_size",
    "st_mtime_ns",
    "st_ctime_ns",
)


@dataclass(frozen=True)
class ProviderCLIResolution:
    executable_name: str
    discovery_role: str
    launch_path: Path
    target_path: Path
    entrypoint_kind: str
    installation_kind: str
    installation_file_count: int
    installation_total_bytes: int
    installation_sha256: str
    target_sha256: str
    execution_format: str
    external_runtime_policy: str
    entrypoint_binding_sha256: str
    ancestry_binding_sha256: str
    installation_root_binding_sha256: str
    _installation_root_path: Path = field(repr=False)
    _launch_identity: tuple[int, ...] = field(repr=False)
    _target_identity: tuple[int, ...] = field(repr=False)
    _installation_root_identity: tuple[int, ...] = field(repr=False)


def current_account() -> tuple[str, Path, str]:
    """Return a validated account name, home, and login shell."""

    try:
        record = pwd.getpwuid(os.getuid())
        name = str(record.pw_name)
        raw_home = str(record.pw_dir)
        shell = str(record.pw_shell)
    except (KeyError, OSError, RuntimeError, ValueError):
        raise RuntimeError("Current account identity is unavailable") from None
    home = Path(raw_home)
    if (
        not name
        or "\x00" in name
        or "/" in name
        or not home.is_absolute()
        or home != Path(os.path.normpath(raw_home))
        or "\x00" in raw_home
        or not shell.startswith("/")
        or shell != os.path.normpath(shell)
        or "\x00" in shell
    ):
        raise RuntimeError("Current account identity is invalid")
    return name, home, shell


def _search_directories() -> tuple[tuple[str, Path, Path], ...]:
    _, account_home, _ = current_account()
    return (
        (
            "root_managed_usr_local_bin",
            Path("/usr/local/bin"),
            Path("/usr/local"),
        ),
        (
            "root_managed_homebrew_bin",
            Path("/opt/homebrew/bin"),
            Path("/opt/homebrew"),
        ),
        (
            "current_account_local_bin",
            account_home / ".local" / "bin",
            account_home / ".local",
        ),
        ("system_usr_bin", Path("/usr/bin"), Path("/usr")),
        ("system_bin", Path("/bin"), Path("/usr")),
        ("system_usr_sbin", Path("/usr/sbin"), Path("/usr")),
        ("system_sbin", Path("/sbin"), Path("/usr")),
    )


def _metadata_identity(metadata: os.stat_result) -> tuple[int, ...]:
    return tuple(int(getattr(metadata, field)) for field in _STABLE_FILE_FIELDS)


def _component_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _relative_path(path: Path, scope: Path) -> str:
    try:
        relative = path.relative_to(scope).as_posix()
    except ValueError:
        raise RuntimeError("Provider CLI path escapes its installation role") from None
    if not relative or relative == "." or relative.startswith("../"):
        raise RuntimeError("Provider CLI role-relative path is invalid")
    return relative


def _directory_ancestry_binding(
    *,
    discovery_role: str,
    launch_path: Path,
    target_path: Path,
    installation_scope: Path,
) -> str:
    entries: list[dict[str, Any]] = []
    directories = {launch_path.parent}
    current = target_path.parent
    while True:
        directories.add(current)
        if current == installation_scope:
            break
        if installation_scope not in current.parents:
            raise RuntimeError("Provider CLI ancestry escapes its installation role")
        current = current.parent
    for directory in sorted(
        directories,
        key=lambda value: (
            len(value.parts),
            value.as_posix(),
        ),
    ):
        try:
            metadata = directory.lstat()
            resolved = directory.resolve(strict=True)
        except (OSError, RuntimeError):
            raise RuntimeError("Provider CLI ancestry is unavailable") from None
        if (
            resolved != directory
            or not stat.S_ISDIR(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid not in {0, os.getuid()}
            or metadata.st_mode & stat.S_IWOTH
            or (
                metadata.st_mode & stat.S_IWGRP
                and discovery_role != "root_managed_homebrew_bin"
            )
        ):
            raise RuntimeError("Provider CLI ancestry is unsafe")
        entries.append(
            {
                "relative_path": (
                    "."
                    if directory == installation_scope
                    else _relative_path(directory, installation_scope)
                ),
                "metadata": list(_metadata_identity(metadata)),
            }
        )
    return _component_sha256(entries)


def _entrypoint_binding_sha256(
    *,
    executable_name: str,
    discovery_role: str,
    launch_path: Path,
    launch_metadata: os.stat_result,
    target_path: Path,
    target_metadata: os.stat_result,
    installation_scope: Path,
    installation_root: Path,
) -> str:
    link_text: str | None = None
    if stat.S_ISLNK(launch_metadata.st_mode):
        try:
            link_text = os.readlink(launch_path)
        except OSError:
            raise RuntimeError("Provider CLI entrypoint changed") from None
    return _component_sha256(
        {
            "executable_name": executable_name,
            "discovery_role": discovery_role,
            "entrypoint_kind": (
                "symlink"
                if stat.S_ISLNK(launch_metadata.st_mode)
                else "regular_file"
            ),
            "launch_basename": launch_path.name,
            "launch_link_text": link_text,
            "launch_metadata": list(_metadata_identity(launch_metadata)),
            "target_role_relative_path": _relative_path(
                target_path, installation_scope
            ),
            "target_metadata": list(_metadata_identity(target_metadata)),
            "installation_root_role_relative_path": _relative_path(
                installation_root, installation_scope
            ),
        }
    )


def _stable_file_sha256(
    path: Path, *, allow_empty: bool = False
) -> tuple[str, os.stat_result]:
    descriptor: int | None = None
    try:
        before = path.lstat()
    except OSError:
        raise RuntimeError("Provider CLI installation file is unavailable") from None
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_nlink != 1
        or not (
            (0 if allow_empty else 1)
            <= before.st_size
            <= _MAX_INSTALLATION_FILE_BYTES
        )
        or before.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
        or before.st_uid not in {0, os.getuid()}
    ):
        raise RuntimeError("Provider CLI installation file is unsafe")
    digest = hashlib.sha256()
    try:
        flags = os.O_RDONLY
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if _metadata_identity(opened) != _metadata_identity(before):
            raise RuntimeError("Provider CLI installation file changed")
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        after = os.fstat(descriptor)
        final = path.lstat()
        if (
            _metadata_identity(after) != _metadata_identity(before)
            or _metadata_identity(final) != _metadata_identity(before)
        ):
            raise RuntimeError("Provider CLI installation file changed")
    except RuntimeError:
        raise
    except OSError:
        raise RuntimeError("Provider CLI installation file is unavailable") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return "sha256:" + digest.hexdigest(), before


def _execution_contract(
    executable_name: str,
    target_path: Path,
    expected_metadata: os.stat_result,
) -> tuple[str, str]:
    descriptor: int | None = None
    try:
        flags = os.O_RDONLY
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(target_path, flags)
        opened = os.fstat(descriptor)
        prefix = os.read(descriptor, 64)
        final = target_path.lstat()
    except OSError:
        raise RuntimeError("Provider CLI execution format is unavailable") from None
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if (
        _metadata_identity(opened) != _metadata_identity(expected_metadata)
        or _metadata_identity(final) != _metadata_identity(expected_metadata)
    ):
        raise RuntimeError("Provider CLI changed during format binding")
    if executable_name in {"claude", "codex"}:
        if not prefix.startswith(b"\xcf\xfa\xed\xfe"):
            raise RuntimeError("Provider CLI Mach-O execution format is invalid")
        return (
            "macho64_little_endian",
            (
                "content_bound_adjacent_tree_with_os_loader_and_"
                "dynamic_dependencies_outside_benchmark_binding"
            ),
        )
    if executable_name == "cursor-agent":
        if not prefix.startswith(b"#!/usr/bin/env bash\n"):
            raise RuntimeError("Cursor CLI execution format is invalid")
        return (
            "system_env_bash_script",
            (
                "fixed_system_path_env_bash_tools_plus_content_bound_"
                "adjacent_node_tree_os_tools_outside_benchmark_binding"
            ),
        )
    raise RuntimeError("Provider CLI execution format is unsupported")


def _installation_contract(
    executable_name: str,
    target_path: Path,
) -> tuple[
    str,
    int,
    int,
    str,
    str,
    os.stat_result,
    Path,
    os.stat_result,
    str,
]:
    target_sha256, target_metadata = _stable_file_sha256(target_path)

    root = target_path.parent
    try:
        root_metadata = root.lstat()
        resolved_root = root.resolve(strict=True)
    except (OSError, RuntimeError):
        raise RuntimeError("Provider CLI installation root is unavailable") from None
    if (
        root != resolved_root
        or not stat.S_ISDIR(root_metadata.st_mode)
        or stat.S_ISLNK(root_metadata.st_mode)
        or root_metadata.st_uid not in {0, os.getuid()}
        or root_metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
    ):
        raise RuntimeError("Provider CLI installation root is unsafe")

    inventory: list[dict[str, Any]] = []
    total_bytes = 0
    descendants: list[Path] = []
    pending = [root]
    while pending:
        parent = pending.pop()
        children: list[Path] = []
        try:
            with os.scandir(parent) as stream:
                for entry in stream:
                    descendants.append(Path(entry.path))
                    children.append(Path(entry.path))
                    if len(descendants) > _MAX_INSTALLATION_ENTRIES:
                        raise RuntimeError(
                            "Provider CLI installation inventory is too large"
                        )
        except RuntimeError:
            raise
        except OSError:
            raise RuntimeError(
                "Provider CLI installation inventory is unavailable"
            ) from None
        for child in sorted(
            children,
            key=lambda path: path.name,
            reverse=True,
        ):
            try:
                if stat.S_ISDIR(child.lstat().st_mode):
                    pending.append(child)
            except OSError:
                raise RuntimeError(
                    "Provider CLI installation inventory is unavailable"
                ) from None
    if not descendants:
        raise RuntimeError("Provider CLI installation inventory is invalid")
    for descendant in sorted(
        descendants,
        key=lambda path: path.relative_to(root).as_posix(),
    ):
        relative = descendant.relative_to(root).as_posix()
        try:
            metadata = descendant.lstat()
            resolved = descendant.resolve(strict=True)
        except (OSError, RuntimeError):
            raise RuntimeError(
                "Provider CLI installation inventory is unavailable"
            ) from None
        if (
            resolved != descendant
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid not in {0, os.getuid()}
            or metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
        ):
            raise RuntimeError("Provider CLI installation inventory is unsafe")
        if stat.S_ISDIR(metadata.st_mode):
            inventory.append(
                {
                    "kind": "directory",
                    "mode": f"{stat.S_IMODE(metadata.st_mode):04o}",
                    "relative_path": relative,
                }
            )
            continue
        if not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError("Provider CLI installation inventory is unsafe")
        digest, stable_metadata = _stable_file_sha256(
            descendant, allow_empty=True
        )
        total_bytes += int(stable_metadata.st_size)
        if total_bytes > _MAX_INSTALLATION_TOTAL_BYTES:
            raise RuntimeError("Provider CLI installation inventory is too large")
        inventory.append(
            {
                "kind": "regular_file",
                "mode": f"{stat.S_IMODE(stable_metadata.st_mode):04o}",
                "relative_path": relative,
                "sha256": digest,
                "size_bytes": int(stable_metadata.st_size),
            }
        )
    if target_path.relative_to(root).as_posix() not in {
        item["relative_path"]
        for item in inventory
        if item["kind"] == "regular_file"
    }:
        raise RuntimeError("Provider CLI target is absent from its installation")
    try:
        final_root_metadata = root.lstat()
        final_target_metadata = target_path.lstat()
    except OSError:
        raise RuntimeError("Provider CLI installation changed") from None
    if (
        _metadata_identity(final_root_metadata)
        != _metadata_identity(root_metadata)
        or _metadata_identity(final_target_metadata)
        != _metadata_identity(target_metadata)
    ):
        raise RuntimeError("Provider CLI installation changed")
    encoded = json.dumps(
        {
            "executable_name": executable_name,
            "inventory": inventory,
            "root_mode": f"{stat.S_IMODE(root_metadata.st_mode):04o}",
            "root_owner_uid": int(root_metadata.st_uid),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return (
        "closed_installation_tree",
        sum(1 for item in inventory if item["kind"] == "regular_file"),
        total_bytes,
        "sha256:" + hashlib.sha256(encoded).hexdigest(),
        target_sha256,
        target_metadata,
        root,
        root_metadata,
        _component_sha256(
            {
                "metadata": list(_metadata_identity(root_metadata)),
                "target_basename": target_path.name,
            }
        ),
    )


def _resolve_provider_cli(executable_name: str) -> ProviderCLIResolution:
    """Resolve one allowlisted CLI without consulting ambient environment."""

    if (
        executable_name not in ALLOWED_PROVIDER_EXECUTABLES
        or "/" in executable_name
        or "\x00" in executable_name
    ):
        raise RuntimeError("Provider CLI name is not allowlisted")
    candidates: list[ProviderCLIResolution] = []
    for role, directory, installation_scope in _search_directories():
        try:
            resolved_directory = directory.resolve(strict=True)
            resolved_scope = installation_scope.resolve(strict=True)
        except FileNotFoundError:
            continue
        except (OSError, RuntimeError):
            raise RuntimeError("Provider CLI search role is unavailable") from None
        launch_path = resolved_directory / executable_name
        try:
            launch_metadata = launch_path.lstat()
        except FileNotFoundError:
            continue
        except OSError:
            raise RuntimeError("Provider CLI search failed") from None
        try:
            target_path = launch_path.resolve(strict=True)
            target_metadata = target_path.stat()
            target_path.relative_to(resolved_scope)
        except (OSError, RuntimeError):
            raise RuntimeError("Provider CLI target is unavailable") from None
        except ValueError:
            raise RuntimeError(
                "Provider CLI target escapes its source-owned installation role"
            ) from None
        executable_bits = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
        if (
            not (
                stat.S_ISREG(launch_metadata.st_mode)
                or stat.S_ISLNK(launch_metadata.st_mode)
            )
            or not stat.S_ISREG(target_metadata.st_mode)
            or not target_metadata.st_mode & executable_bits
            or not os.access(launch_path, os.X_OK)
        ):
            raise RuntimeError("Provider CLI target is not executable")
        (
            installation_kind,
            installation_file_count,
            installation_total_bytes,
            installation_sha256,
            target_sha256,
            stable_target_metadata,
            installation_root,
            installation_root_metadata,
            installation_root_binding_sha256,
        ) = _installation_contract(executable_name, target_path)
        entrypoint_binding_sha256 = _entrypoint_binding_sha256(
            executable_name=executable_name,
            discovery_role=role,
            launch_path=launch_path,
            launch_metadata=launch_metadata,
            target_path=target_path,
            target_metadata=stable_target_metadata,
            installation_scope=resolved_scope,
            installation_root=installation_root,
        )
        ancestry_binding_sha256 = _directory_ancestry_binding(
            discovery_role=role,
            launch_path=launch_path,
            target_path=target_path,
            installation_scope=resolved_scope,
        )
        execution_format, external_runtime_policy = _execution_contract(
            executable_name,
            target_path,
            stable_target_metadata,
        )
        candidates.append(
            ProviderCLIResolution(
                executable_name=executable_name,
                discovery_role=role,
                launch_path=launch_path,
                target_path=target_path,
                entrypoint_kind=(
                    "symlink" if stat.S_ISLNK(launch_metadata.st_mode)
                    else "regular_file"
                ),
                installation_kind=installation_kind,
                installation_file_count=installation_file_count,
                installation_total_bytes=installation_total_bytes,
                installation_sha256=installation_sha256,
                target_sha256=target_sha256,
                execution_format=execution_format,
                external_runtime_policy=external_runtime_policy,
                entrypoint_binding_sha256=entrypoint_binding_sha256,
                ancestry_binding_sha256=ancestry_binding_sha256,
                installation_root_binding_sha256=(
                    installation_root_binding_sha256
                ),
                _installation_root_path=installation_root,
                _launch_identity=_metadata_identity(launch_metadata),
                _target_identity=_metadata_identity(stable_target_metadata),
                _installation_root_identity=_metadata_identity(
                    installation_root_metadata
                ),
            )
        )
    if not candidates:
        raise RuntimeError("Required provider CLI is unavailable")
    distinct_targets = {candidate.target_path for candidate in candidates}
    if len(distinct_targets) != 1:
        raise RuntimeError("Provider CLI discovery is ambiguous")
    return candidates[0]


def resolve_provider_cli(executable_name: str) -> ProviderCLIResolution:
    """Resolve and content-bind one source-allowlisted provider installation."""

    first = _resolve_provider_cli(executable_name)
    second = _resolve_provider_cli(executable_name)
    if first != second:
        raise RuntimeError("Provider CLI changed during discovery")
    return first


def attest_provider_cli_resolution(
    resolution: ProviderCLIResolution,
) -> None:
    """Fail closed unless a previously resolved CLI installation is unchanged."""

    if not isinstance(resolution, ProviderCLIResolution):
        raise RuntimeError("Provider CLI resolution is invalid")
    current = _resolve_provider_cli(resolution.executable_name)
    if current != resolution:
        raise RuntimeError("Provider CLI changed after discovery")


def provider_cli_public_identity(
    resolution: ProviderCLIResolution,
) -> dict[str, Any]:
    """Return the complete path-free identity used by public contracts."""

    if not isinstance(resolution, ProviderCLIResolution):
        raise RuntimeError("Provider CLI resolution is invalid")
    return {
        "name": resolution.executable_name,
        "discovery_role": resolution.discovery_role,
        "entrypoint_kind": resolution.entrypoint_kind,
        "executable_sha256": resolution.target_sha256,
        "execution_format": resolution.execution_format,
        "external_runtime_policy": resolution.external_runtime_policy,
        "installation_kind": resolution.installation_kind,
        "installation_file_count": resolution.installation_file_count,
        "installation_total_bytes": resolution.installation_total_bytes,
        "installation_sha256": resolution.installation_sha256,
        "entrypoint_binding_sha256": resolution.entrypoint_binding_sha256,
        "ancestry_binding_sha256": resolution.ancestry_binding_sha256,
        "installation_root_binding_sha256": (
            resolution.installation_root_binding_sha256
        ),
    }
