import copy
import dataclasses
import unittest

from core.runtime.packages import (
    PackageDependency,
    PackageManifest,
    PackageManifestError,
    PackageType,
    parse_manifest,
)


def manifest_data(**overrides) -> dict:
    data = {
        "schema_version": 1,
        "package_type": "character",
        "package_id": "example-character",
        "display_name": "Example Character",
        "version": "1.0.0",
        "requires": [
            {"package_type": "world", "package_id": "example-world", "version": "1.0.0"},
            {"package_type": "system", "package_id": "example-system", "version": "1.0.0"},
        ],
    }
    data.update(overrides)
    return data


class ParseManifestTest(unittest.TestCase):
    def test_valid_manifest(self):
        manifest = parse_manifest(manifest_data())
        self.assertIsInstance(manifest, PackageManifest)
        self.assertIs(manifest.package_type, PackageType.CHARACTER)
        self.assertEqual(manifest.package_id, "example-character")
        self.assertEqual(manifest.key, (PackageType.CHARACTER, "example-character"))
        self.assertEqual(
            manifest.requires,
            (
                PackageDependency(PackageType.WORLD, "example-world", "1.0.0"),
                PackageDependency(PackageType.SYSTEM, "example-system", "1.0.0"),
            ),
        )

    def test_requires_becomes_tuple_and_input_is_not_mutated(self):
        data = manifest_data()
        snapshot = copy.deepcopy(data)
        manifest = parse_manifest(data)
        self.assertIsInstance(manifest.requires, tuple)
        self.assertEqual(data, snapshot)
        self.assertEqual(parse_manifest(manifest_data(requires=[])).requires, ())

    def test_is_immutable(self):
        manifest = parse_manifest(manifest_data())
        with self.assertRaises(dataclasses.FrozenInstanceError):
            manifest.version = "2.0.0"
        with self.assertRaises(dataclasses.FrozenInstanceError):
            manifest.requires[0].version = "2.0.0"

    def test_version_is_opaque(self):
        for version in ("1.0.0", "2026-10-11", "v3", "beta"):
            with self.subTest(version=version):
                self.assertEqual(parse_manifest(manifest_data(version=version)).version, version)

    def test_root_must_be_object(self):
        for bad in ([], "manifest", None, 1):
            with self.subTest(root=bad):
                with self.assertRaises(PackageManifestError):
                    parse_manifest(bad)

    def test_keys_must_match_exactly(self):
        missing = manifest_data()
        del missing["display_name"]
        with self.assertRaises(PackageManifestError):
            parse_manifest(missing)
        with self.assertRaises(PackageManifestError):
            parse_manifest(manifest_data(payload={"rules": []}))

    def test_schema_version_must_be_integer_one(self):
        for bad in (True, 1.0, "1", 2, 0, None):
            with self.subTest(schema_version=bad):
                with self.assertRaises(PackageManifestError):
                    parse_manifest(manifest_data(schema_version=bad))

    def test_package_type_must_be_known(self):
        for bad in ("Character", "rules", "", None, ["world"]):
            with self.subTest(package_type=bad):
                with self.assertRaises(PackageManifestError):
                    parse_manifest(manifest_data(package_type=bad))

    def test_package_id_format(self):
        for good in ("a", "example-world", "world2", "a-1-b"):
            with self.subTest(package_id=good):
                parse_manifest(manifest_data(package_id=good))
        for bad in ("", "Example", "example_world", "-world", "world-", "a--b", "wörld", " a", 3):
            with self.subTest(package_id=bad):
                with self.assertRaises(PackageManifestError):
                    parse_manifest(manifest_data(package_id=bad))

    def test_text_fields_reject_empty_or_outer_whitespace(self):
        for field in ("display_name", "version"):
            for bad in ("", " ", " x", "x ", "\tx", None, 1):
                with self.subTest(field=field, value=bad):
                    with self.assertRaises(PackageManifestError):
                        parse_manifest(manifest_data(**{field: bad}))

    def test_requires_must_be_list(self):
        for bad in ({}, "example-world", None, ()):
            with self.subTest(requires=bad):
                with self.assertRaises(PackageManifestError):
                    parse_manifest(manifest_data(requires=bad))

    def test_dependency_keys_and_values_are_validated(self):
        base = {"package_type": "world", "package_id": "example-world", "version": "1.0.0"}
        bad_dependencies = (
            "example-world",
            {**base, "optional": True},
            {k: v for k, v in base.items() if k != "version"},
            {**base, "package_type": "rules"},
            {**base, "package_id": "Example"},
            {**base, "version": " 1.0.0"},
        )
        for dep in bad_dependencies:
            with self.subTest(dependency=dep):
                with self.assertRaises(PackageManifestError):
                    parse_manifest(manifest_data(requires=[dep]))

    def test_rejects_self_dependency(self):
        self_dep = {"package_type": "character", "package_id": "example-character", "version": "1.0.0"}
        with self.assertRaises(PackageManifestError):
            parse_manifest(manifest_data(requires=[self_dep]))

    def test_same_id_with_other_type_is_not_self_dependency(self):
        dep = {"package_type": "world", "package_id": "shared-name", "version": "1.0.0"}
        parse_manifest(manifest_data(package_id="shared-name", requires=[dep]))

    def test_rejects_duplicate_dependency_even_with_other_version(self):
        a = {"package_type": "world", "package_id": "example-world", "version": "1.0.0"}
        b = {"package_type": "world", "package_id": "example-world", "version": "2.0.0"}
        with self.assertRaises(PackageManifestError):
            parse_manifest(manifest_data(requires=[a, b]))

    def test_error_is_value_error(self):
        self.assertTrue(issubclass(PackageManifestError, ValueError))


if __name__ == "__main__":
    unittest.main()
