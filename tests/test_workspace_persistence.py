import dataclasses
import hashlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from adapters.manual import load_manual_dossier
from core.runtime import persistence, workspace
from core.runtime.persistence import (
    PersistenceError,
    atomic_write_bytes,
    canonical_json_bytes,
    encode_state,
    load_state,
    load_strict_json,
)
from core.runtime.workspace import (
    LoadedWorkspace,
    ManagedFile,
    WorkspaceConfig,
    WorkspaceError,
    create_workspace,
    load_workspace,
)

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "dossiers" / "minimal-neutral"


def temp_dir(test: unittest.TestCase) -> Path:
    tmp = tempfile.TemporaryDirectory()
    test.addCleanup(tmp.cleanup)
    return Path(tmp.name)


class CanonicalJsonTest(unittest.TestCase):
    def test_pretty_and_compact_forms(self):
        value = {"b": [1, {"d": None}], "a": "ñ"}
        self.assertEqual(
            canonical_json_bytes(value, pretty=True),
            '{\n  "a": "ñ",\n  "b": [\n    1,\n    {\n      "d": null\n    }\n  ]\n}\n'.encode(),
        )
        self.assertEqual(canonical_json_bytes(value, pretty=False),
                         '{"a":"ñ","b":[1,{"d":null}]}'.encode())

    def test_rejects_unstorable_values(self):
        for bad in (float("nan"), {"a": object()}, {"a": "\ud800"}):
            with self.subTest(value=repr(bad)):
                with self.assertRaises(PersistenceError) as ctx:
                    canonical_json_bytes(bad, pretty=True)
                self.assertEqual(ctx.exception.code, "INVALID_STATE")


class StrictJsonTest(unittest.TestCase):
    def test_rejects_invalid_documents(self):
        root = temp_dir(self)
        cases = {
            "bom": b'\xef\xbb\xbf{"a": 1}',
            "utf8": b'{"a": "\xff"}',
            "duplicate": b'{"a": 1, "a": 2}',
            "nan": b'{"a": NaN}',
            "deep": b"[" * 20000 + b"]" * 20000,
            "malformed": b"{",
        }
        for name, raw in cases.items():
            with self.subTest(name):
                path = root / f"{name}.json"
                path.write_bytes(raw)
                with self.assertRaises(PersistenceError) as ctx:
                    load_strict_json(path)
                self.assertEqual(ctx.exception.code, "INVALID_STATE")
                if name != "bom":  # detected directly, there is no underlying error to chain
                    self.assertIsNotNone(ctx.exception.__cause__)

    def test_missing_file_is_io(self):
        with self.assertRaises(PersistenceError) as ctx:
            load_strict_json(temp_dir(self) / "absent.json")
        self.assertEqual(ctx.exception.code, "IO")
        self.assertIsInstance(ctx.exception.__cause__, OSError)


class AtomicWriteTest(unittest.TestCase):
    def test_writes_and_replaces(self):
        path = temp_dir(self) / "state.json"
        atomic_write_bytes(path, b"uno")
        atomic_write_bytes(path, b"dos")
        self.assertEqual(path.read_bytes(), b"dos")
        self.assertEqual(sorted(p.name for p in path.parent.iterdir()), ["state.json"])

    def test_failed_replace_keeps_previous_bytes_and_cleans_temp(self):
        path = temp_dir(self) / "state.json"
        path.write_bytes(b"anterior")
        with mock.patch.object(persistence.os, "replace", side_effect=OSError("simulado")):
            with self.assertRaises(PersistenceError) as ctx:
                atomic_write_bytes(path, b"nuevo")
        self.assertEqual(ctx.exception.code, "IO")
        self.assertEqual(path.read_bytes(), b"anterior")
        self.assertEqual(sorted(p.name for p in path.parent.iterdir()), ["state.json"])

    def test_failed_cleanup_is_reported(self):
        path = temp_dir(self) / "state.json"
        path.write_bytes(b"anterior")
        with mock.patch.object(persistence.os, "replace", side_effect=OSError("simulado")),                 mock.patch.object(persistence.os, "unlink", side_effect=OSError("bloqueado")):
            with self.assertRaises(PersistenceError) as ctx:
                atomic_write_bytes(path, b"nuevo")
        self.assertIn("bórralo a mano", ctx.exception.reason)
        leftovers = [p for p in path.parent.iterdir() if p.name != "state.json"]
        self.assertEqual(len(leftovers), 1)
        self.assertIn(leftovers[0].name, ctx.exception.reason)
        self.assertEqual(path.read_bytes(), b"anterior")

    def test_requires_bytes(self):
        with self.assertRaises(PersistenceError):
            atomic_write_bytes(temp_dir(self) / "x", "texto")


class StateEnvelopeTest(unittest.TestCase):
    def test_exact_envelope(self):
        content = {"candidates": [], "closure": None, "decisions": []}
        raw = encode_state(content, revision=0)
        data = json.loads(raw)
        self.assertEqual(set(data), {"schema_version", "revision", "content", "content_sha256"})
        hashed = canonical_json_bytes({"schema_version": 1, "revision": 0, "content": content},
                                      pretty=False)
        self.assertEqual(data["content_sha256"], hashlib.sha256(hashed).hexdigest())
        path = temp_dir(self) / "state.json"
        path.write_bytes(raw)
        self.assertEqual(load_state(path), (0, content))

    def test_invalid_revision(self):
        for bad in (-1, True, 1.0, "1"):
            with self.subTest(revision=bad):
                with self.assertRaises(PersistenceError):
                    encode_state({}, revision=bad)

    def test_detects_edits(self):
        path = temp_dir(self) / "state.json"
        raw = encode_state({"a": 1}, revision=3)
        edits = {
            "content": raw.replace(b'"a": 1', b'"a": 2'),
            "revision": raw.replace(b'"revision": 3', b'"revision": 4'),
            "whitespace": raw.replace(b"\n", b"\r\n"),
            "extra key": raw.replace(b'"revision"', b'"x": 1,\n  "revision"'),
        }
        for name, edited in edits.items():
            with self.subTest(name):
                self.assertNotEqual(edited, raw)
                path.write_bytes(edited)
                with self.assertRaises(PersistenceError) as ctx:
                    load_state(path)
                self.assertEqual(ctx.exception.code, "INVALID_STATE")


class ModelTest(unittest.TestCase):
    def config(self, **overrides) -> WorkspaceConfig:
        fields = dict(schema_version=1, forum_id="foro", display_name="Foro",
                      dossier_version="1", core_root=ROOT, dossier_path="dossier/expediente.md",
                      dossier_files=(ManagedFile("dossier/expediente.md", "0" * 64, 1),))
        fields.update(overrides)
        return WorkspaceConfig(**fields)

    def test_managed_file_validation(self):
        ManagedFile("dossier/a.md", "a" * 64, 0)
        for path, digest, size in (("/a", "a" * 64, 0), ("a\\b", "a" * 64, 0), ("../a", "a" * 64, 0),
                                   ("a:b", "a" * 64, 0), ("a", "A" * 64, 0), ("a", "a" * 64, -1),
                                   ("a", "a" * 64, True)):
            with self.subTest(path=path, digest=digest[:2], size=size):
                with self.assertRaises(WorkspaceError):
                    ManagedFile(path, digest, size)

    def test_config_validation_and_immutability(self):
        config = self.config()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            config.forum_id = "otro"
        unsorted = (ManagedFile("dossier/z.md", "0" * 64, 1), ManagedFile("dossier/expediente.md", "0" * 64, 1))
        for overrides in (dict(schema_version=2), dict(forum_id="Foro"), dict(display_name=" x"),
                          dict(core_root=Path("relativa")), dict(dossier_path="dossier/otro.md"),
                          dict(dossier_files=()), dict(dossier_files=unsorted),
                          dict(dossier_files=(ManagedFile("otro/expediente.md", "0" * 64, 1),))):
            with self.subTest(overrides=str(overrides)[:60]):
                with self.assertRaises(WorkspaceError):
                    self.config(**overrides)


class CreateWorkspaceTest(unittest.TestCase):
    def setUp(self):
        self.root = temp_dir(self)
        self.dossier_dir = self.root / "expediente"
        shutil.copytree(FIXTURE, self.dossier_dir)
        self.target = self.root / "ws"

    def create(self, target: Path | None = None):
        return create_workspace(load_manual_dossier(self.dossier_dir), dossier_dir=self.dossier_dir,
                                workspace=target or self.target, core_root=ROOT)

    def test_creates_expected_layout(self):
        result = self.create()
        self.assertTrue(result.created)
        self.assertIsInstance(result.workspace, LoadedWorkspace)
        files = sorted(p.relative_to(self.target).as_posix() for p in self.target.rglob("*") if p.is_file())
        self.assertEqual(files, ["corpus/state.json", "dossier/expediente.md",
                                 "dossier/materials/manual-foro.md",
                                 "dossier/materials/material-suelto.md",
                                 "work/integrity.json", "workspace.json"])
        self.assertEqual(result.workspace.corpus_revision, 0)
        self.assertEqual(result.workspace.config.core_root, ROOT)
        for relative in files[1:4]:
            self.assertEqual((self.target / relative).read_bytes(),
                             (self.dossier_dir / relative.split("/", 1)[1]).read_bytes())
        self.assertEqual(load_state(self.target / "corpus" / "state.json"),
                         (0, {"candidates": [], "closure": None, "decisions": []}))

    def test_integrity_covers_config_and_dossier(self):
        self.create()
        integrity = json.loads((self.target / "work" / "integrity.json").read_bytes())
        self.assertEqual(set(integrity), {"algorithm", "files", "schema_version"})
        paths = [f["path"] for f in integrity["files"]]
        self.assertEqual(paths, sorted(paths))
        self.assertIn("workspace.json", paths)
        self.assertNotIn("corpus/state.json", paths)
        self.assertNotIn("work/integrity.json", paths)

    def test_unreferenced_files_are_not_copied(self):
        (self.dossier_dir / "materials" / "privado.md").write_bytes(b"no referenciado\n")
        self.create()
        self.assertFalse((self.target / "dossier" / "materials" / "privado.md").exists())

    def test_retry_is_idempotent_without_writes(self):
        self.create()
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.target.rglob("*") if p.is_file()}
        result = self.create()
        self.assertFalse(result.created)
        after = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.target.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_retry_with_different_input_conflicts(self):
        self.create()
        manual = self.dossier_dir / "materials" / "manual-foro.md"
        manual.write_bytes(manual.read_bytes() + b"Nueva norma.\n")
        with self.assertRaises(WorkspaceError) as ctx:
            self.create()
        self.assertEqual(ctx.exception.code, "CONFLICT")

    def test_empty_existing_directory_is_used(self):
        self.target.mkdir()
        self.assertTrue(self.create().created)

    def test_failed_rename_leaves_no_partial_workspace(self):
        for existed in (False, True):
            with self.subTest(existed=existed):
                target = self.root / f"ws-{existed}"
                if existed:
                    target.mkdir()
                with mock.patch.object(workspace.os, "replace", side_effect=OSError("simulado")):
                    with self.assertRaises(WorkspaceError) as ctx:
                        self.create(target)
                self.assertEqual(ctx.exception.code, "IO")
                self.assertEqual(target.exists(), existed)
                if existed:
                    self.assertEqual(list(target.iterdir()), [])
                self.assertFalse([p for p in self.root.iterdir() if ".staging-" in p.name])

    def competitor(self, populate: bool):
        """Replace os.replace with one that lets another actor create the target first."""
        real_replace = os.replace

        def racing_replace(source, target):
            if ".staging-" in str(source):
                Path(target).mkdir(exist_ok=True)
                if populate:
                    (Path(target) / "ajeno.txt").write_bytes(b"de otro proceso")
            return real_replace(source, target)

        return mock.patch.object(workspace.os, "replace", racing_replace)

    def test_race_with_foreign_content_is_a_conflict(self):
        with self.competitor(populate=True):
            with self.assertRaises(WorkspaceError) as ctx:
                self.create()
        self.assertEqual(ctx.exception.code, "CONFLICT")
        self.assertEqual([p.name for p in self.target.iterdir()], ["ajeno.txt"])
        self.assertFalse([p for p in self.root.iterdir() if ".staging-" in p.name])

    def test_race_with_identical_workspace_is_idempotent(self):
        reference = self.root / "referencia"
        self.create(reference)
        real_replace = os.replace

        def racing_replace(source, target):
            if ".staging-" in str(source):
                shutil.copytree(reference, target)
            return real_replace(source, target)

        with mock.patch.object(workspace.os, "replace", racing_replace):
            if os.name != "nt":
                self.skipTest("en POSIX rename sobre una carpeta no vacía también falla, "
                              "pero el orden de la prueba depende de Windows")
            result = self.create()
        self.assertFalse(result.created)
        self.assertFalse([p for p in self.root.iterdir() if ".staging-" in p.name])

    def test_identical_race_with_failed_cleanup_is_reported(self):
        if os.name != "nt":
            self.skipTest("la carrera depende de que rename falle sobre una carpeta existente")
        reference = self.root / "referencia"
        self.create(reference)
        real_replace, real_rmtree = os.replace, shutil.rmtree

        def racing_replace(source, target):
            if ".staging-" in str(source):
                shutil.copytree(reference, target)
            return real_replace(source, target)

        def stubborn_rmtree(path, *args, **kwargs):
            if ".staging-" in str(path):
                raise OSError("bloqueado")
            return real_rmtree(path, *args, **kwargs)

        with mock.patch.object(workspace.os, "replace", racing_replace), \
                mock.patch.object(workspace.shutil, "rmtree", stubborn_rmtree):
            with self.assertRaises(WorkspaceError) as ctx:
                self.create()
        self.assertEqual(ctx.exception.code, "IO")
        self.assertIsInstance(ctx.exception.__cause__, OSError)
        leftovers = [p for p in self.root.iterdir() if ".staging-" in p.name]
        self.assertEqual(len(leftovers), 1)
        self.assertIn(leftovers[0].name, ctx.exception.reason)
        self.assertEqual(ctx.exception.reason.count("bórrala a mano"), 1)
        load_workspace(self.target, expected_core_root=ROOT)
        real_rmtree(leftovers[0])

    def test_failed_staging_cleanup_is_reported(self):
        real_rmtree = shutil.rmtree

        def stubborn_rmtree(path, *args, **kwargs):
            if ".staging-" in str(path):
                raise OSError("bloqueado")
            return real_rmtree(path, *args, **kwargs)

        with mock.patch.object(workspace.os, "replace", side_effect=OSError("simulado")),                 mock.patch.object(workspace.shutil, "rmtree", stubborn_rmtree):
            with self.assertRaises(WorkspaceError) as ctx:
                self.create()
        self.assertEqual(ctx.exception.code, "IO")
        self.assertIn("bórrala a mano", ctx.exception.reason)
        leftovers = [p for p in self.root.iterdir() if ".staging-" in p.name]
        self.assertEqual(len(leftovers), 1)
        self.assertIn(leftovers[0].name, ctx.exception.reason)
        real_rmtree(leftovers[0])

    def test_dossier_must_match_its_directory(self):
        other = self.root / "otro"
        shutil.copytree(FIXTURE, other)
        with self.assertRaises(WorkspaceError):
            create_workspace(load_manual_dossier(other), dossier_dir=self.dossier_dir,
                             workspace=self.target, core_root=ROOT)

    def test_core_root_must_be_the_checkout(self):
        dossier = load_manual_dossier(self.dossier_dir)
        for core_root in (self.root, Path("relativa")):
            with self.subTest(core_root=core_root):
                with self.assertRaises(WorkspaceError):
                    create_workspace(dossier, dossier_dir=self.dossier_dir, workspace=self.target,
                                     core_root=core_root)


class LoadWorkspaceTest(unittest.TestCase):
    def setUp(self):
        self.root = temp_dir(self)
        dossier_dir = self.root / "expediente"
        shutil.copytree(FIXTURE, dossier_dir)
        self.target = self.root / "ws"
        create_workspace(load_manual_dossier(dossier_dir), dossier_dir=dossier_dir,
                         workspace=self.target, core_root=ROOT)

    def assert_invalid(self, code: str = "INVALID_STATE"):
        with self.assertRaises(WorkspaceError) as ctx:
            load_workspace(self.target, expected_core_root=ROOT)
        self.assertEqual(ctx.exception.code, code)
        return ctx.exception

    def test_loads(self):
        loaded = load_workspace(self.target, expected_core_root=ROOT)
        self.assertEqual(loaded.config.forum_id, "foro-neutral")
        self.assertEqual(loaded.workspace_root, self.target)

    def test_detects_edit_of_each_managed_file(self):
        for relative in ("workspace.json", "work/integrity.json", "corpus/state.json",
                         "dossier/expediente.md", "dossier/materials/manual-foro.md"):
            with self.subTest(relative=relative):
                path = self.target / relative
                original = path.read_bytes()
                path.write_bytes(original.replace(b"\n", b"\n ", 1))
                self.assert_invalid()
                path.write_bytes(original)
                load_workspace(self.target, expected_core_root=ROOT)

    def test_recomputed_config_hash_still_fails_integrity(self):
        path = self.target / "workspace.json"
        data = json.loads(path.read_bytes())
        data["display_name"] = "Otro nombre"
        path.write_bytes(canonical_json_bytes(data, pretty=True))
        self.assert_invalid()

    def test_extra_or_missing_files(self):
        extra = self.target / "dossier" / "materials" / "extra.md"
        extra.write_bytes(b"x\n")
        self.assert_invalid()
        extra.unlink()
        state = self.target / "corpus" / "state.json"
        saved = state.read_bytes()
        state.unlink()
        self.assert_invalid()
        state.write_bytes(saved)
        load_workspace(self.target)

    def test_other_checkout_conflicts(self):
        load_workspace(self.target)
        with self.assertRaises(WorkspaceError) as ctx:
            load_workspace(self.target, expected_core_root=self.root)
        self.assertEqual(ctx.exception.code, "CONFLICT")

    def test_not_a_workspace(self):
        with self.assertRaises(WorkspaceError):
            load_workspace(self.root / "absent")
        with self.assertRaises(WorkspaceError):
            load_workspace(self.root / "expediente")


if __name__ == "__main__":
    unittest.main()
