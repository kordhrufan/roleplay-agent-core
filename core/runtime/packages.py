"""Package manifests: identity, version and dependencies of character, world and system packages.

A manifest carries no domain payload. World and system packages only name a selectable namespace;
rules and lore are assimilated per instance outside the repository.
"""

from __future__ import annotations

import hashlib
import heapq
import json
import os
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from core.memory.provenance import SourceRef

MANIFEST_NAME = "manifest.json"
MAX_MANIFEST_BYTES = 65_536
SCHEMA_VERSION = 1

_PACKAGE_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_MANIFEST_KEYS = frozenset(
    {"schema_version", "package_type", "package_id", "display_name", "version", "requires"}
)
_DEPENDENCY_KEYS = frozenset({"package_type", "package_id", "version"})


class PackageType(str, Enum):
    CHARACTER = "character"
    WORLD = "world"
    SYSTEM = "system"


_CATEGORIES = {
    "characters": PackageType.CHARACTER,
    "worlds": PackageType.WORLD,
    "systems": PackageType.SYSTEM,
}


class PackageManifestError(ValueError):
    """A manifest is malformed or a package set cannot be resolved."""


@dataclass(frozen=True, slots=True)
class PackageDependency:
    package_type: PackageType
    package_id: str
    version: str


@dataclass(frozen=True, slots=True)
class PackageManifest:
    schema_version: int
    package_type: PackageType
    package_id: str
    display_name: str
    version: str
    requires: tuple[PackageDependency, ...]

    @property
    def key(self) -> tuple[PackageType, str]:
        return (self.package_type, self.package_id)


@dataclass(frozen=True, slots=True)
class LoadedPackageManifest:
    manifest: PackageManifest
    package_dir: Path
    source_ref: SourceRef


def parse_manifest(data: object) -> PackageManifest:
    """Validate a decoded manifest object. The input is never mutated."""
    _require_keys("manifest", data, _MANIFEST_KEYS)
    schema_version = data["schema_version"]
    if type(schema_version) is not int or schema_version != SCHEMA_VERSION:
        raise PackageManifestError(f"schema_version must be the integer {SCHEMA_VERSION}")
    package_type = _parse_type("package_type", data["package_type"])
    package_id = _parse_id("package_id", data["package_id"])
    display_name = _parse_text("display_name", data["display_name"])
    version = _parse_text("version", data["version"])
    requires_data = data["requires"]
    if not isinstance(requires_data, list):
        raise PackageManifestError("requires must be a list")
    requires = tuple(_parse_dependency(i, item) for i, item in enumerate(requires_data))
    seen: set[tuple[PackageType, str]] = set()
    for dep in requires:
        key = (dep.package_type, dep.package_id)
        if key == (package_type, package_id):
            raise PackageManifestError(f"package {package_id} cannot require itself")
        if key in seen:
            raise PackageManifestError(
                f"duplicate dependency {dep.package_type.value}:{dep.package_id}"
            )
        seen.add(key)
    return PackageManifest(
        schema_version, package_type, package_id, display_name, version, requires
    )


def load_manifest(
    package_dir: Path, *, expected_type: PackageType | None = None
) -> LoadedPackageManifest:
    """Read `<package_dir>/manifest.json` and bind it to its directory and exact bytes."""
    package_dir = Path(package_dir)
    manifest_path = package_dir / MANIFEST_NAME
    if package_dir.is_symlink() or not package_dir.is_dir():
        raise PackageManifestError(f"{package_dir} is not a regular directory")
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise PackageManifestError(f"{manifest_path} is not a regular file")
    with manifest_path.open("rb") as handle:
        raw = handle.read(MAX_MANIFEST_BYTES + 1)
    if len(raw) > MAX_MANIFEST_BYTES:
        raise PackageManifestError(f"{manifest_path} exceeds {MAX_MANIFEST_BYTES} bytes")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PackageManifestError(f"{manifest_path} is not valid UTF-8") from exc
    try:
        data = json.loads(
            text, object_pairs_hook=_reject_duplicate_keys, parse_constant=_reject_constant
        )
    except (json.JSONDecodeError, PackageManifestError) as exc:
        raise PackageManifestError(f"{manifest_path} is not valid JSON: {exc}") from exc
    except RecursionError as exc:
        raise PackageManifestError(f"{manifest_path} is nested too deeply") from exc
    manifest = parse_manifest(data)
    if manifest.package_id != package_dir.name:
        raise PackageManifestError(
            f"package_id {manifest.package_id} does not match directory {package_dir.name}"
        )
    if expected_type is not None and manifest.package_type is not expected_type:
        raise PackageManifestError(
            f"{manifest.package_id} is a {manifest.package_type.value} package, "
            f"expected {expected_type.value}"
        )
    source_ref = SourceRef(
        source_id=(
            f"package-manifest:{manifest.package_type.value}:"
            f"{manifest.package_id}:{manifest.version}"
        ),
        locator=manifest_path.as_posix(),
        sha256=hashlib.sha256(raw).hexdigest(),
    )
    return LoadedPackageManifest(manifest, package_dir, source_ref)


def load_package_set(packages_root: Path) -> tuple[LoadedPackageManifest, ...]:
    """Load every package under `packages_root` and resolve dependencies.

    Returns dependencies before dependents, ties ordered by (type, id, version). Any missing
    dependency, version mismatch or cycle fails the whole set. Every directory inside a category
    is a package and must have a manifest; loose files are ignored. Symlinks are never followed.
    """
    packages_root = Path(packages_root)
    if packages_root.is_symlink() or not packages_root.is_dir():
        raise PackageManifestError(f"{packages_root} is not a regular directory")
    for entry in sorted(packages_root.iterdir()):
        if entry.is_symlink():
            raise PackageManifestError(f"symlinks are not allowed in a package tree: {entry}")
        if entry.is_dir() and entry.name not in _CATEGORIES and _contains_manifest(entry):
            raise PackageManifestError(f"unknown package category {entry.name!r}")

    loaded: dict[tuple[PackageType, str], LoadedPackageManifest] = {}
    for category, package_type in _CATEGORIES.items():
        category_dir = packages_root / category
        if not category_dir.exists():
            continue
        if not category_dir.is_dir():
            raise PackageManifestError(f"{category_dir} is not a regular directory")
        for package_dir in sorted(category_dir.iterdir()):
            if package_dir.is_symlink():
                raise PackageManifestError(
                    f"symlinks are not allowed in a package tree: {package_dir}"
                )
            if not package_dir.is_dir():
                continue
            package = load_manifest(package_dir, expected_type=package_type)
            key = package.manifest.key
            if key in loaded:
                raise PackageManifestError(f"duplicate package {package_type.value}:{key[1]}")
            loaded[key] = package

    for package in loaded.values():
        for dep in package.manifest.requires:
            target = loaded.get((dep.package_type, dep.package_id))
            if target is None:
                raise PackageManifestError(
                    f"{package.manifest.package_id} requires missing "
                    f"{dep.package_type.value}:{dep.package_id}"
                )
            if target.manifest.version != dep.version:
                raise PackageManifestError(
                    f"{package.manifest.package_id} requires "
                    f"{dep.package_type.value}:{dep.package_id} {dep.version}, "
                    f"found {target.manifest.version}"
                )
    return _topological_order(loaded)


def _topological_order(
    loaded: dict[tuple[PackageType, str], LoadedPackageManifest],
) -> tuple[LoadedPackageManifest, ...]:
    def sort_key(key: tuple[PackageType, str]) -> tuple[str, str, str]:
        return (key[0].value, key[1], loaded[key].manifest.version)

    pending = {key: len(package.manifest.requires) for key, package in loaded.items()}
    dependents: dict[tuple[PackageType, str], list[tuple[PackageType, str]]] = {
        key: [] for key in loaded
    }
    for key, package in loaded.items():
        for dep in package.manifest.requires:
            dependents[(dep.package_type, dep.package_id)].append(key)
    ready = [(sort_key(key), key) for key, count in pending.items() if count == 0]
    heapq.heapify(ready)
    ordered: list[LoadedPackageManifest] = []
    while ready:
        _, key = heapq.heappop(ready)
        ordered.append(loaded[key])
        for dependent in dependents[key]:
            pending[dependent] -= 1
            if pending[dependent] == 0:
                heapq.heappush(ready, (sort_key(dependent), dependent))
    if len(ordered) != len(loaded):
        cyclic = sorted(f"{t.value}:{i}" for (t, i), count in pending.items() if count > 0)
        raise PackageManifestError(f"dependency cycle among {', '.join(cyclic)}")
    return tuple(ordered)


def _contains_manifest(directory: Path) -> bool:
    for _, _, files in os.walk(directory, followlinks=False):
        if MANIFEST_NAME in files:
            return True
    return False


def _parse_dependency(index: int, data: object) -> PackageDependency:
    _require_keys(f"requires[{index}]", data, _DEPENDENCY_KEYS)
    return PackageDependency(
        _parse_type(f"requires[{index}].package_type", data["package_type"]),
        _parse_id(f"requires[{index}].package_id", data["package_id"]),
        _parse_text(f"requires[{index}].version", data["version"]),
    )


def _require_keys(name: str, data: object, keys: frozenset[str]) -> None:
    if not isinstance(data, dict):
        raise PackageManifestError(f"{name} must be a JSON object")
    actual = set(data)
    if actual != keys:
        missing = sorted(keys - actual)
        unknown = sorted(str(k) for k in actual - keys)
        raise PackageManifestError(f"{name} keys mismatch: missing {missing}, unknown {unknown}")


def _parse_type(name: str, value: object) -> PackageType:
    try:
        return PackageType(value)
    except ValueError as exc:
        raise PackageManifestError(f"{name} must be one of {[t.value for t in PackageType]}") from exc


def _parse_id(name: str, value: object) -> str:
    if not isinstance(value, str) or not _PACKAGE_ID.fullmatch(value):
        raise PackageManifestError(f"{name} must match {_PACKAGE_ID.pattern}")
    return value


def _parse_text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise PackageManifestError(f"{name} must be non-empty text without outer whitespace")
    return value


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise PackageManifestError(f"duplicate key {key!r}")
        result[key] = value
    return result


def _reject_constant(name: str) -> object:
    raise PackageManifestError(f"non-standard JSON constant {name}")
