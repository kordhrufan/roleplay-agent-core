import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from core.runtime.packages import (
    MAX_MANIFEST_BYTES,
    PackageManifestError,
    PackageType,
    load_manifest,
    load_package_set,
)

ROOT = Path(__file__).resolve().parent.parent
VALID_FIXTURE = ROOT / "tests" / "fixtures" / "packages" / "valid"
REAL_PACKAGES = ROOT / "packages"
CATEGORY = {"character": "characters", "world": "worlds", "system": "systems"}


def manifest(package_type: str, package_id: str, version: str = "1.0.0", requires=()) -> dict:
    return {
        "schema_version": 1,
        "package_type": package_type,
        "package_id": package_id,
        "display_name": package_id.replace("-", " ").title(),
        "version": version,
        "requires": [
            {"package_type": t, "package_id": i, "version": v} for t, i, v in requires
        ],
    }


class TempPackages:
    """Builds package trees inside a temporary directory."""

    def __init__(self, test: unittest.TestCase):
        tmp = tempfile.TemporaryDirectory()
        test.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / "packages"
        self.root.mkdir()

    def write_raw(self, category: str, package_id: str, raw: bytes) -> Path:
        package_dir = self.root / category / package_id
        package_dir.mkdir(parents=True, exist_ok=True)
        (package_dir / "manifest.json").write_bytes(raw)
        return package_dir

    def add(self, data: dict, *, category: str | None = None, directory: str | None = None) -> Path:
        raw = json.dumps(data, indent=2).encode("utf-8")
        return self.write_raw(
            category or CATEGORY[data["package_type"]], directory or data["package_id"], raw
        )


def keys(packages) -> list[tuple[str, str]]:
    return [(p.manifest.package_type.value, p.manifest.package_id) for p in packages]


class LoadManifestTest(unittest.TestCase):
    def test_source_ref_has_exact_hash_and_no_invented_dates(self):
        package_dir = VALID_FIXTURE / "worlds" / "example-world"
        loaded = load_manifest(package_dir)
        raw = (package_dir / "manifest.json").read_bytes()
        ref = loaded.source_ref
        self.assertEqual(ref.source_id, "package-manifest:world:example-world:1.0.0")
        self.assertEqual(ref.locator, (package_dir / "manifest.json").as_posix())
        self.assertEqual(ref.sha256, hashlib.sha256(raw).hexdigest())
        self.assertIsNone(ref.section_or_passage)
        self.assertIsNone(ref.observed_at)
        self.assertIsNone(ref.ic_date)
        self.assertEqual(loaded.package_dir, package_dir)
        self.assertIs(loaded.manifest.package_type, PackageType.WORLD)

    def test_hash_is_reproducible_and_tracks_bytes(self):
        packages = TempPackages(self)
        data = manifest("world", "w")
        first = load_manifest(packages.add(data)).source_ref.sha256
        self.assertEqual(load_manifest(packages.root / "worlds" / "w").source_ref.sha256, first)
        packages.write_raw("worlds", "w", json.dumps(data).encode("utf-8"))
        self.assertNotEqual(load_manifest(packages.root / "worlds" / "w").source_ref.sha256, first)

    def test_expected_type(self):
        package_dir = VALID_FIXTURE / "systems" / "example-system"
        load_manifest(package_dir, expected_type=PackageType.SYSTEM)
        with self.assertRaises(PackageManifestError):
            load_manifest(package_dir, expected_type=PackageType.WORLD)

    def test_package_id_must_match_directory(self):
        packages = TempPackages(self)
        package_dir = packages.add(manifest("world", "w"), directory="other")
        with self.assertRaises(PackageManifestError):
            load_manifest(package_dir)

    def test_missing_manifest_or_directory(self):
        packages = TempPackages(self)
        with self.assertRaises(PackageManifestError):
            load_manifest(packages.root / "worlds" / "absent")
        (packages.root / "worlds" / "empty").mkdir(parents=True)
        with self.assertRaises(PackageManifestError):
            load_manifest(packages.root / "worlds" / "empty")

    def test_rejects_invalid_utf8(self):
        packages = TempPackages(self)
        package_dir = packages.write_raw("worlds", "w", b'{"display_name": "\xff"}')
        with self.assertRaises(PackageManifestError) as ctx:
            load_manifest(package_dir)
        self.assertIsInstance(ctx.exception.__cause__, UnicodeDecodeError)

    def test_rejects_utf8_bom(self):
        packages = TempPackages(self)
        raw = b"\xef\xbb\xbf" + json.dumps(manifest("world", "w")).encode("utf-8")
        with self.assertRaises(PackageManifestError):
            load_manifest(packages.write_raw("worlds", "w", raw))

    def test_rejects_malformed_json(self):
        packages = TempPackages(self)
        for raw in (b"", b"{", b'{"schema_version": 1,}', b"[1, NaN]"):
            with self.subTest(raw=raw):
                with self.assertRaises(PackageManifestError):
                    load_manifest(packages.write_raw("worlds", "w", raw))

    def test_rejects_duplicate_json_keys(self):
        packages = TempPackages(self)
        text = json.dumps(manifest("world", "w"))
        raw = text.replace('"version": "1.0.0"', '"version": "1.0.0", "version": "2.0.0"', 1)
        self.assertNotEqual(raw, text)
        with self.assertRaises(PackageManifestError):
            load_manifest(packages.write_raw("worlds", "w", raw.encode("utf-8")))

    def test_size_limit(self):
        packages = TempPackages(self)
        base = json.dumps(manifest("world", "w"))
        at_limit = base + " " * (MAX_MANIFEST_BYTES - len(base))
        self.assertEqual(len(at_limit.encode("utf-8")), MAX_MANIFEST_BYTES)
        load_manifest(packages.write_raw("worlds", "w", at_limit.encode("utf-8")))
        over = (at_limit + " ").encode("utf-8")
        with self.assertRaises(PackageManifestError):
            load_manifest(packages.write_raw("worlds", "w", over))

    def test_rejects_symlinked_manifest(self):
        packages = TempPackages(self)
        target = packages.add(manifest("world", "w")) / "manifest.json"
        link_dir = packages.root / "worlds" / "linked"
        link_dir.mkdir()
        try:
            os.symlink(target, link_dir / "manifest.json")
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are not available for this user")
        with self.assertRaises(PackageManifestError):
            load_manifest(link_dir)
        with self.assertRaises(PackageManifestError):
            load_package_set(packages.root)


class LoadPackageSetTest(unittest.TestCase):
    def test_valid_fixture_in_topological_order(self):
        loaded = load_package_set(VALID_FIXTURE)
        self.assertEqual(
            keys(loaded),
            [("system", "example-system"), ("world", "example-world"),
             ("character", "example-character")],
        )

    def test_real_packages_load(self):
        loaded = load_package_set(REAL_PACKAGES)
        self.assertEqual(
            keys(loaded),
            [("system", "naruto-rol"), ("world", "naruto-rol"), ("character", "nozomu")],
        )

    def test_real_packages_contain_only_manifests(self):
        files = sorted(p.relative_to(REAL_PACKAGES).as_posix()
                       for p in REAL_PACKAGES.rglob("*") if p.is_file())
        self.assertEqual(
            files,
            ["characters/nozomu/manifest.json", "systems/naruto-rol/manifest.json",
             "worlds/naruto-rol/manifest.json"],
        )

    def test_order_is_deterministic_with_ties(self):
        packages = TempPackages(self)
        packages.add(manifest("character", "b", requires=[("world", "w", "1.0.0")]))
        packages.add(manifest("character", "a", requires=[("world", "w", "1.0.0")]))
        packages.add(manifest("world", "w", requires=[("system", "s", "1.0.0")]))
        packages.add(manifest("system", "s"))
        packages.add(manifest("system", "z"))
        self.assertEqual(
            keys(load_package_set(packages.root)),
            [("system", "s"), ("system", "z"), ("world", "w"), ("character", "a"),
             ("character", "b")],
        )

    def test_empty_or_missing_categories(self):
        packages = TempPackages(self)
        self.assertEqual(load_package_set(packages.root), ())
        (packages.root / "worlds").mkdir()
        packages.add(manifest("system", "s"))
        self.assertEqual(keys(load_package_set(packages.root)), [("system", "s")])

    def test_root_must_exist(self):
        packages = TempPackages(self)
        with self.assertRaises(PackageManifestError):
            load_package_set(packages.root / "absent")

    def test_missing_dependency(self):
        packages = TempPackages(self)
        packages.add(manifest("character", "c", requires=[("world", "w", "1.0.0")]))
        with self.assertRaises(PackageManifestError):
            load_package_set(packages.root)

    def test_dependency_type_must_match(self):
        packages = TempPackages(self)
        packages.add(manifest("system", "w"))
        packages.add(manifest("character", "c", requires=[("world", "w", "1.0.0")]))
        with self.assertRaises(PackageManifestError):
            load_package_set(packages.root)

    def test_dependency_version_must_match_literally(self):
        packages = TempPackages(self)
        packages.add(manifest("world", "w", version="1.0"))
        packages.add(manifest("character", "c", requires=[("world", "w", "1.0.0")]))
        with self.assertRaises(PackageManifestError):
            load_package_set(packages.root)

    def test_type_must_match_category(self):
        packages = TempPackages(self)
        packages.add(manifest("world", "w"), category="systems")
        with self.assertRaises(PackageManifestError):
            load_package_set(packages.root)

    def test_package_id_must_match_directory(self):
        packages = TempPackages(self)
        packages.add(manifest("world", "w"), directory="renamed")
        with self.assertRaises(PackageManifestError):
            load_package_set(packages.root)

    def test_unknown_category_with_manifest(self):
        packages = TempPackages(self)
        packages.add(manifest("system", "s"))
        packages.add(manifest("system", "r"), category="rules")
        with self.assertRaises(PackageManifestError):
            load_package_set(packages.root)

    def test_unknown_category_with_manifest_at_any_depth(self):
        for relative in ("rules/manifest.json", "rules/nested/pkg/manifest.json"):
            with self.subTest(relative=relative):
                packages = TempPackages(self)
                packages.add(manifest("system", "s"))
                path = packages.root / relative
                path.parent.mkdir(parents=True)
                path.write_bytes(json.dumps(manifest("system", "r")).encode("utf-8"))
                with self.assertRaises(PackageManifestError):
                    load_package_set(packages.root)

    def test_unknown_directory_without_manifest_is_ignored(self):
        packages = TempPackages(self)
        packages.add(manifest("system", "s"))
        (packages.root / "docs" / "notes").mkdir(parents=True)
        (packages.root / "docs" / "notes" / "readme.md").write_text("x", encoding="utf-8")
        self.assertEqual(keys(load_package_set(packages.root)), [("system", "s")])

    def test_package_directory_without_manifest_fails(self):
        packages = TempPackages(self)
        packages.add(manifest("system", "s"))
        (packages.root / "worlds" / "incomplete").mkdir(parents=True)
        (packages.root / "worlds" / "incomplete" / "manifest.jsn").write_text("{}", encoding="utf-8")
        with self.assertRaises(PackageManifestError):
            load_package_set(packages.root)

    def test_ignores_loose_files_without_loading_payload(self):
        packages = TempPackages(self)
        package_dir = packages.add(manifest("system", "s"))
        (package_dir / "notes.md").write_text("not loaded", encoding="utf-8")
        (packages.root / "README.md").write_text("not a package", encoding="utf-8")
        (packages.root / "systems" / "index.txt").write_text("not a package", encoding="utf-8")
        self.assertEqual(keys(load_package_set(packages.root)), [("system", "s")])

    def test_deeply_nested_json_is_a_manifest_error(self):
        packages = TempPackages(self)
        raw = ("[" * 20_000 + "]" * 20_000).encode("ascii")
        self.assertLess(len(raw), MAX_MANIFEST_BYTES)
        with self.assertRaises(PackageManifestError):
            load_manifest(packages.write_raw("worlds", "w", raw))

    def test_relative_path_keeps_relative_posix_locator(self):
        packages = TempPackages(self)
        packages.add(manifest("world", "w"))
        previous = os.getcwd()
        os.chdir(packages.root.parent)
        self.addCleanup(os.chdir, previous)
        loaded = load_manifest(Path("packages") / "worlds" / "w")
        self.assertEqual(loaded.source_ref.locator, "packages/worlds/w/manifest.json")
        from_set = load_package_set(Path("packages"))
        self.assertEqual(from_set[0].source_ref.locator, "packages/worlds/w/manifest.json")

    def test_real_manifests_use_lf(self):
        for path in sorted(REAL_PACKAGES.rglob("manifest.json")) + sorted(
            VALID_FIXTURE.rglob("manifest.json")
        ):
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                self.assertNotIn(b"\r", path.read_bytes())

    def test_cycle_fails_closed(self):
        packages = TempPackages(self)
        packages.add(manifest("world", "w", requires=[("system", "s", "1.0.0")]))
        packages.add(manifest("system", "s", requires=[("world", "w", "1.0.0")]))
        packages.add(manifest("character", "c"))
        with self.assertRaises(PackageManifestError) as ctx:
            load_package_set(packages.root)
        self.assertIn("cycle", str(ctx.exception))

    def test_invalid_manifest_fails_whole_set(self):
        packages = TempPackages(self)
        packages.add(manifest("system", "s"))
        packages.write_raw("worlds", "w", b"{")
        with self.assertRaises(PackageManifestError):
            load_package_set(packages.root)


class SymlinkTest(unittest.TestCase):
    """Symlinks are never followed. Skipped only where the OS forbids creating them."""

    def link(self, target: Path, link: Path, *, directory: bool) -> None:
        try:
            os.symlink(target, link, target_is_directory=directory)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are not available for this user")

    def test_symlinked_package_directory(self):
        packages = TempPackages(self)
        real = packages.add(manifest("world", "w"))
        outside = packages.root.parent / "outside"
        outside.mkdir()
        (outside / "linked").mkdir()
        (outside / "linked" / "manifest.json").write_bytes(
            json.dumps(manifest("world", "linked")).encode("utf-8"))
        self.link(outside / "linked", packages.root / "worlds" / "linked", directory=True)
        with self.assertRaises(PackageManifestError):
            load_manifest(packages.root / "worlds" / "linked")
        with self.assertRaises(PackageManifestError):
            load_package_set(packages.root)
        load_manifest(real)

    def test_symlinked_category(self):
        packages = TempPackages(self)
        outside = packages.root.parent / "outside-systems"
        (outside / "s").mkdir(parents=True)
        (outside / "s" / "manifest.json").write_bytes(
            json.dumps(manifest("system", "s")).encode("utf-8"))
        self.link(outside, packages.root / "systems", directory=True)
        with self.assertRaises(PackageManifestError):
            load_package_set(packages.root)

    def test_broken_symlinked_category(self):
        packages = TempPackages(self)
        packages.add(manifest("system", "s"))
        self.link(packages.root.parent / "missing", packages.root / "worlds", directory=True)
        with self.assertRaises(PackageManifestError):
            load_package_set(packages.root)

    def test_broken_symlinked_package_directory(self):
        packages = TempPackages(self)
        packages.add(manifest("system", "s"))
        (packages.root / "worlds").mkdir()
        self.link(packages.root.parent / "missing", packages.root / "worlds" / "w", directory=True)
        with self.assertRaises(PackageManifestError):
            load_package_set(packages.root)


if __name__ == "__main__":
    unittest.main()
