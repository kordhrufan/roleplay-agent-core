import dataclasses
import hashlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.review.models import ReviewStatus
from core.runtime import instance as instance_module
from core.runtime.instance import (
    INSTANCE_CORPUS,
    ApprovedCorpusEntry,
    InstanceCorpus,
    InstanceError,
    SourceWorkspace,
    approved_corpus,
    create_instance,
    get_approved_candidate,
    load_instance,
)
from core.runtime.workspace import CORPUS_STATE, load_workspace
from tests.instance_support import ROOT, closed_workspace, open_workspace

EXPECTED_LAYOUT = ["AGENTS.md", "CLAUDE.md", "corpus/state.json", "dossier/expediente.md",
                   "dossier/materials/manual-foro.md", "dossier/materials/material-suelto.md",
                   "instance.json", "work/integrity.json"]


def files(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def snapshot(root: Path) -> dict:
    return {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.rglob("*") if p.is_file()}


class InstanceCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._template_dir = Path(tempfile.mkdtemp())
        cls._template_ws = closed_workspace(cls._template_dir)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._template_dir)

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        self.workspace = self.root / "ws"
        shutil.copytree(self._template_ws, self.workspace)
        self.output = self.root / "instancia"

    def create(self, output: Path | None = None):
        return create_instance(self.workspace, output=output or self.output, core_root=ROOT)


class ModelTest(unittest.TestCase):
    def test_instance_corpus(self):
        corpus = InstanceCorpus(INSTANCE_CORPUS, 3, "a" * 64, 10, "b" * 64)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            corpus.revision = 4
        for overrides in (dict(path="corpus/otro.json"), dict(revision=-1), dict(size=True),
                          dict(sha256="A" * 64), dict(snapshot_sha256="x")):
            with self.subTest(overrides=str(overrides)):
                with self.assertRaises(InstanceError):
                    dataclasses.replace(corpus, **overrides)

    def test_source_workspace(self):
        SourceWorkspace("c" * 64)
        with self.assertRaises(InstanceError):
            SourceWorkspace("ruta/del/workspace")


class CreateTest(InstanceCase):
    def test_layout_and_exact_copies(self):
        result = self.create()
        self.assertTrue(result.created)
        self.assertEqual(files(self.output), EXPECTED_LAYOUT)
        for relative in EXPECTED_LAYOUT[2:6]:
            self.assertEqual((self.output / relative).read_bytes(),
                             (self.workspace / relative).read_bytes())
        for absent in ("workspace.json", "characters", "memory", "specialists"):
            self.assertFalse((self.output / absent).exists())

    def test_config_has_fingerprint_not_workspace_path(self):
        result = self.create()
        raw = (self.output / "instance.json").read_text(encoding="utf-8")
        self.assertNotIn(str(self.workspace), raw)
        self.assertNotIn(self.workspace.name + '"', raw)
        config = result.instance.config
        self.assertEqual(config.source_workspace.workspace_json_sha256,
                         hashlib.sha256((self.workspace / "workspace.json").read_bytes()).hexdigest())
        corpus_bytes = (self.workspace / CORPUS_STATE).read_bytes()
        self.assertEqual((config.corpus.sha256, config.corpus.size),
                         (hashlib.sha256(corpus_bytes).hexdigest(), len(corpus_bytes)))
        self.assertEqual(config.corpus.snapshot_sha256,
                         load_workspace(self.workspace).closure.snapshot_sha256)
        self.assertEqual(config.packages, ())
        self.assertEqual(config.instance_root, self.output)
        self.assertEqual(config.core_root, ROOT)

    def test_full_history_is_copied(self):
        result = self.create()
        workspace = load_workspace(self.workspace)
        self.assertEqual(result.instance.candidates, workspace.candidates)
        self.assertEqual(result.instance.decisions, workspace.decisions)
        self.assertEqual(result.instance.closure, workspace.closure)

    def test_open_workspace_is_rejected(self):
        workspace = open_workspace(self.root, "abierto")
        with self.assertRaises(InstanceError) as ctx:
            create_instance(workspace, output=self.output, core_root=ROOT)
        self.assertEqual(ctx.exception.code, "INVALID_STATE")
        self.assertIn("no está cerrada", ctx.exception.reason)
        self.assertFalse(self.output.exists())

    def test_locked_or_manipulated_workspace(self):
        lock = self.workspace / (CORPUS_STATE + ".lock")
        lock.write_bytes(b"")
        with self.assertRaises(InstanceError) as ctx:
            self.create()
        self.assertEqual(ctx.exception.code, "CONFLICT")
        lock.unlink()
        state = self.workspace / CORPUS_STATE
        state.write_bytes(state.read_bytes().replace(b'"APPROVED"', b'"REJECTED"', 1))
        with self.assertRaises(InstanceError) as ctx:
            self.create()
        self.assertEqual(ctx.exception.code, "INVALID_STATE")
        self.assertFalse(self.output.exists())

    def test_retry_is_idempotent(self):
        self.create()
        before = snapshot(self.output)
        result = self.create()
        self.assertFalse(result.created)
        self.assertEqual(before, snapshot(self.output))

    def test_unsafe_destinations(self):
        (self.root / "ocupada").mkdir()
        (self.root / "ocupada" / "x.txt").write_bytes(b"x")
        cases = {
            "inside checkout": (ROOT / "tests" / "no-crear-aqui", "UNSAFE_DESTINATION"),
            "checkout spelled in upper case": (Path(str(ROOT / "tests" / "no-crear-aqui").upper()),
                                               "UNSAFE_DESTINATION"),
            "inside workspace": (self.workspace / "instancia", "UNSAFE_DESTINATION"),
            "workspace itself": (self.workspace, "UNSAFE_DESTINATION"),
            "ancestor of workspace": (self.root, "UNSAFE_DESTINATION"),
            "missing parent": (self.root / "no" / "instancia", "UNSAFE_DESTINATION"),
            "non-empty": (self.root / "ocupada", "CONFLICT"),
        }
        for name, (target, code) in cases.items():
            with self.subTest(name):
                with self.assertRaises(InstanceError) as ctx:
                    self.create(target)
                self.assertEqual(ctx.exception.code, code)
        self.assertFalse((ROOT / "tests" / "no-crear-aqui").exists())
        self.assertFalse((self.workspace / "instancia").exists())
        self.assertEqual(files(self.root / "ocupada"), ["x.txt"])

    @unittest.skipUnless(os.name == "nt", "las junctions son de Windows")
    def test_junction_destination(self):
        import _winapi
        real = self.root / "real"
        real.mkdir()
        _winapi.CreateJunction(str(real), str(self.root / "enlace"))
        with self.assertRaises(InstanceError) as ctx:
            self.create(self.root / "enlace")
        self.assertEqual(ctx.exception.code, "UNSAFE_DESTINATION")
        self.assertEqual(list(real.iterdir()), [])
        with self.assertRaises(InstanceError) as ctx:
            self.create(Path("\\\\?\\" + str(ROOT / "tests" / "no-crear-aqui")))
        self.assertEqual(ctx.exception.code, "UNSAFE_DESTINATION")

    def test_source_change_between_reads_conflicts(self):
        real_read = instance_module._read_source
        calls = []

        def read_source(workspace_root, core_root):
            calls.append(1)
            source = real_read(workspace_root, core_root)
            if len(calls) == 2:
                return dataclasses.replace(source, corpus=source.corpus + b" ")
            return source

        with mock.patch.object(instance_module, "_read_source", read_source):
            with self.assertRaises(InstanceError) as ctx:
                self.create()
        self.assertEqual(ctx.exception.code, "CONFLICT")
        self.assertFalse(self.output.exists())
        self.assertFalse([p for p in self.root.iterdir() if ".staging-" in p.name])

    def test_failed_replace_leaves_nothing(self):
        with mock.patch.object(instance_module.os, "replace", side_effect=OSError("simulado")):
            with self.assertRaises(InstanceError) as ctx:
                self.create()
        self.assertEqual(ctx.exception.code, "IO")
        self.assertFalse(self.output.exists())
        self.assertFalse([p for p in self.root.iterdir() if ".staging-" in p.name])

    def test_races(self):
        reference = self.root / "referencia"
        real_replace = os.replace

        def racing(populate):
            def replace(source, target):
                if ".staging-" in str(source):
                    populate(Path(target))
                return real_replace(source, target)
            return mock.patch.object(instance_module.os, "replace", replace)

        def foreign(target):
            target.mkdir()
            (target / "ajeno.txt").write_bytes(b"x")

        with racing(foreign):
            with self.assertRaises(InstanceError) as ctx:
                self.create()
        self.assertEqual(ctx.exception.code, "CONFLICT")
        self.assertEqual(files(self.output), ["ajeno.txt"])
        shutil.rmtree(self.output)
        if os.name == "nt":  # rename onto an existing folder fails on Windows
            # An identical tree must have been generated for this same destination.
            self.create(self.output)
            shutil.copytree(self.output, reference)
            shutil.rmtree(self.output)
            with racing(lambda target: shutil.copytree(reference, target)):
                result = self.create()
            self.assertFalse(result.created)
        self.assertFalse([p for p in self.root.iterdir() if ".staging-" in p.name])


class Rev4C2Test(InstanceCase):
    """REV4C2-01..03: linked parents, destination races and extra empty folders."""

    def junction(self, target: Path, link: Path) -> None:
        if os.name != "nt":
            self.skipTest("las junctions son de Windows")
        import _winapi
        _winapi.CreateJunction(str(target), str(link))

    def test_parent_junction_is_rejected_on_create_and_load(self):
        real_parent = self.root / "padre-real"
        real_parent.mkdir()
        self.junction(real_parent, self.root / "padre-enlace")
        with self.assertRaises(InstanceError) as ctx:
            self.create(self.root / "padre-enlace" / "instancia")
        self.assertEqual(ctx.exception.code, "UNSAFE_DESTINATION")
        self.assertIn("padre-enlace", ctx.exception.reason)
        self.assertEqual(list(real_parent.iterdir()), [])
        self.create(real_parent / "instancia")
        with self.assertRaises(InstanceError) as ctx:
            load_instance(self.root / "padre-enlace" / "instancia")
        self.assertEqual(ctx.exception.code, "INVALID_STATE")
        load_instance(real_parent / "instancia")

    def race_on_second_read(self, action):
        real_read = instance_module._read_source
        calls = []

        def read_source(workspace_root, core_root):
            calls.append(1)
            source = real_read(workspace_root, core_root)
            if len(calls) == 2:
                action()
            return source

        return mock.patch.object(instance_module, "_read_source", read_source)

    def test_absent_destination_that_appears_empty_is_not_overwritten(self):
        with self.race_on_second_read(lambda: self.output.mkdir()):
            with self.assertRaises(InstanceError) as ctx:
                self.create()
        self.assertEqual(ctx.exception.code, "CONFLICT")
        self.assertTrue(self.output.is_dir())
        self.assertEqual(list(self.output.iterdir()), [])
        self.assertFalse([p for p in self.root.iterdir() if ".staging-" in p.name])

    def test_empty_destination_replaced_by_another_is_not_overwritten(self):
        self.output.mkdir()
        marker = {}

        def swap():
            self.output.rmdir()
            self.output.mkdir()
            marker["ino"] = os.stat(self.output).st_ino

        with self.race_on_second_read(swap):
            with self.assertRaises(InstanceError) as ctx:
                self.create()
        self.assertEqual(ctx.exception.code, "CONFLICT")
        self.assertEqual(os.stat(self.output).st_ino, marker["ino"])
        self.assertEqual(list(self.output.iterdir()), [])

    def test_creation_is_refused_where_rename_could_replace_a_folder(self):
        from core.runtime import workspace as workspace_module
        from tests.instance_support import FIXTURE
        from adapters.manual import load_manual_dossier
        with mock.patch.object(workspace_module, "_publish_supported", return_value=False):
            with self.assertRaises(InstanceError) as ctx:
                self.create()
            self.assertEqual(ctx.exception.code, "UNSAFE_DESTINATION")
            self.assertIn("solo está soportado en Windows", ctx.exception.reason)
            with self.assertRaises(workspace_module.WorkspaceError) as ctx:
                workspace_module.create_workspace(load_manual_dossier(FIXTURE),
                                                  dossier_dir=FIXTURE,
                                                  workspace=self.root / "otro-ws", core_root=ROOT)
            self.assertEqual(ctx.exception.code, "UNSAFE_DESTINATION")
            self.assertIsNotNone(load_workspace(self.workspace).closure)  # reading still works
        self.assertFalse(self.output.exists())
        self.assertFalse((self.root / "otro-ws").exists())

    def test_empty_destination_that_stays_empty_is_used(self):
        self.output.mkdir()
        self.assertTrue(self.create().created)

    def test_extra_empty_folders_are_rejected(self):
        self.create()
        for relative in ("dossier/vacio", "dossier/materials/a/b", "corpus/vacio", "work/vacio"):
            with self.subTest(relative=relative):
                path = self.output / relative
                first_new = next(p for p in reversed([path, *path.parents]) if not p.exists())
                path.mkdir(parents=True)
                with self.assertRaises(InstanceError) as ctx:
                    load_instance(self.output)
                self.assertEqual(ctx.exception.code, "INVALID_STATE")
                shutil.rmtree(first_new)
        load_instance(self.output)


class LoadTest(InstanceCase):
    def setUp(self):
        super().setUp()
        self.create()

    def assert_invalid(self, code="INVALID_STATE"):
        with self.assertRaises(InstanceError) as ctx:
            load_instance(self.output, expected_core_root=ROOT)
        self.assertEqual(ctx.exception.code, code)

    def test_works_after_workspace_is_deleted(self):
        shutil.rmtree(self.workspace)
        loaded = load_instance(self.output, expected_core_root=ROOT)
        self.assertEqual(loaded.config.forum_id, "foro-neutral")

    def test_detects_edit_of_every_managed_file(self):
        for relative in EXPECTED_LAYOUT:
            with self.subTest(relative=relative):
                path = self.output / relative
                original = path.read_bytes()
                path.write_bytes(original + b" ")
                self.assert_invalid()
                path.write_bytes(original)
        load_instance(self.output)

    def test_extra_files_are_rejected(self):
        for relative in ("extra.md", "dossier/extra.md", "corpus/otro.json", "work/nota.txt",
                         "characters/x.json", "corpus/state.json.lock"):
            with self.subTest(relative=relative):
                path = self.output / relative
                created_dir = not path.parent.exists()
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(b"x")
                self.assert_invalid()
                path.unlink()
                if created_dir:
                    path.parent.rmdir()
        load_instance(self.output)

    def test_recomputed_integrity_still_fails(self):
        agents = self.output / "AGENTS.md"
        agents.write_bytes(agents.read_bytes().replace("No ejecutes nunca".encode(),
                                                       "Ejecuta siempre".encode()))
        integrity_path = self.output / "work" / "integrity.json"
        integrity = json.loads(integrity_path.read_bytes())
        for item in integrity["files"]:
            if item["path"] == "AGENTS.md":
                data = agents.read_bytes()
                item["sha256"], item["size"] = hashlib.sha256(data).hexdigest(), len(data)
        integrity_path.write_bytes(instance_module.canonical_json_bytes(integrity, pretty=True))
        self.assert_invalid()

    def test_moved_instance_or_other_checkout(self):
        moved = self.root / "movida"
        shutil.copytree(self.output, moved)
        with self.assertRaises(InstanceError) as ctx:
            load_instance(moved)
        self.assertEqual(ctx.exception.code, "INVALID_STATE")
        self.assertIn("otra ruta", ctx.exception.reason)
        with self.assertRaises(InstanceError) as ctx:
            load_instance(self.output, expected_core_root=self.root)
        self.assertEqual(ctx.exception.code, "CONFLICT")

    def test_not_an_instance(self):
        with self.assertRaises(InstanceError):
            load_instance(self.root / "no-existe")
        with self.assertRaises(InstanceError):
            load_instance(self.workspace)


class ApprovedCorpusTest(InstanceCase):
    def setUp(self):
        super().setUp()
        self.instance = self.create().instance

    def test_only_current_approved_versions(self):
        entries = approved_corpus(self.instance)
        keys = [entry.candidate.key for entry in entries]
        self.assertEqual(keys, [("normas", 3), ("mundo", 1), ("fichas", 3), ("staff", 1),
                                ("formato", 1), ("duda", 1)])
        self.assertTrue(all(e.decision.review_status is ReviewStatus.APPROVED for e in entries))
        uncertainty = next(e for e in entries if e.candidate.candidate_id == "duda")
        self.assertTrue(uncertainty.candidate.requires_confirmation)

    def test_explicit_lookup_never_falls_back(self):
        entry = get_approved_candidate(self.instance, candidate_id="normas", version=3)
        self.assertEqual(entry.candidate.version, 3)
        for candidate_id, version in (("normas", 1), ("normas", 2), ("fichas", 1), ("idea", 1),
                                      ("nada", 1), ("normas", 4)):
            with self.subTest(candidate=f"{candidate_id} v{version}"):
                with self.assertRaises(InstanceError) as ctx:
                    get_approved_candidate(self.instance, candidate_id=candidate_id,
                                           version=version)
                self.assertEqual(ctx.exception.code, "INVALID_STATE")

    def test_entry_requires_matching_approved_decision(self):
        entries = approved_corpus(self.instance)
        normas, mundo = entries[0], entries[1]
        with self.assertRaises(InstanceError):
            ApprovedCorpusEntry(normas.candidate, mundo.decision)
        rejected = next(d for d in self.instance.decisions if d.candidate_id == "idea")
        idea = next(c for c in self.instance.candidates if c.candidate_id == "idea")
        with self.assertRaises(InstanceError):
            ApprovedCorpusEntry(idea, rejected)


class InstructionsV2Test(InstanceCase):
    """7b: instructions are a version axis of their own; v1 stays the default."""

    def create2(self, output=None):
        return create_instance(self.workspace, output=output or self.output, core_root=ROOT,
                               instructions_version=2)

    def tree(self, root):
        return {p.relative_to(root).as_posix(): p.read_bytes()
                for p in sorted(root.rglob("*")) if p.is_file()}

    def rewrite(self, changes):
        """Apply `changes` ({path: bytes | None}) and regenerate a consistent manifest, so a
        failure comes from the instructions checks and not from integrity.json."""
        for relative, data in changes.items():
            path = self.output / relative
            if data is None:
                path.unlink()
            else:
                path.write_bytes(data)
        config = json.loads((self.output / "instance.json").read_bytes())
        paths = ["AGENTS.md", "CLAUDE.md", "instance.json", "corpus/state.json",
                 *(f["path"] for f in config["dossier"]["files"])]
        if (self.output / "work" / "instructions.json").is_file():
            paths.append("work/instructions.json")
        covered = sorted(paths)
        integrity = {"algorithm": "sha256", "files": [
            {"path": path, "sha256": hashlib.sha256((self.output / path).read_bytes()).hexdigest(),
             "size": len((self.output / path).read_bytes())} for path in covered],
            "schema_version": config["schema_version"]}
        (self.output / "work" / "integrity.json").write_bytes(
            instance_module.canonical_json_bytes(integrity, pretty=True))

    def assert_invalid(self, fragment=None):
        with self.assertRaises(InstanceError) as ctx:
            load_instance(self.output, expected_core_root=ROOT)
        self.assertEqual(ctx.exception.code, "INVALID_STATE", ctx.exception.reason)
        if fragment is not None:
            self.assertIn(fragment, ctx.exception.reason)

    def descriptor(self):
        return json.loads((self.output / "work" / "instructions.json").read_bytes())

    def test_default_and_explicit_v1_are_the_historical_tree(self):
        self.create()
        self.assertEqual(files(self.output), EXPECTED_LAYOUT)
        default = self.tree(self.output)
        shutil.rmtree(self.output)
        create_instance(self.workspace, output=self.output, core_root=ROOT, instructions_version=1)
        self.assertEqual(self.tree(self.output), default)
        instructions = load_instance(self.output).instructions
        self.assertEqual((instructions.version, instructions.descriptor_sha256,
                          [f.path for f in instructions.files]),
                         (1, None, ["AGENTS.md", "CLAUDE.md"]))
        self.assertEqual(instructions.instructions_sha256, instance_module._sha256(
            instance_module.canonical_json_bytes({
                "files": [f.as_json() for f in instructions.files],
                "format": "roleplay-agent-core-instance-instructions",
                "instructions_version": 1}, pretty=False)))

    def test_v2_layout_descriptor_manifest_and_retry(self):
        result = self.create2()
        self.assertTrue(result.created)
        self.assertEqual(files(self.output), sorted([*EXPECTED_LAYOUT, "work/instructions.json"]))
        agents = (self.output / "AGENTS.md").read_bytes()
        claude = (self.output / "CLAUDE.md").read_bytes()
        managed = [{"path": name, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
                   for name, data in (("AGENTS.md", agents), ("CLAUDE.md", claude))]
        set_sha = instance_module._sha256(instance_module.canonical_json_bytes(
            {"files": managed, "format": "roleplay-agent-core-instance-instructions",
             "instructions_version": 2}, pretty=False))
        raw = (self.output / "work" / "instructions.json").read_bytes()
        self.assertEqual(raw, instance_module.canonical_json_bytes({
            "files": managed, "format": "roleplay-agent-core-instance-instructions",
            "instructions_sha256": set_sha, "instructions_version": 2}, pretty=True))
        integrity = json.loads((self.output / "work" / "integrity.json").read_bytes())
        self.assertIn({"path": "work/instructions.json", "sha256": hashlib.sha256(raw).hexdigest(),
                       "size": len(raw)}, integrity["files"])
        self.assertEqual(integrity["schema_version"], 1)
        loaded = load_instance(self.output, expected_core_root=ROOT)
        self.assertEqual((loaded.config.schema_version, loaded.instructions.version,
                          loaded.instructions.instructions_sha256,
                          loaded.instructions.descriptor_sha256),
                         (1, 2, set_sha, hashlib.sha256(raw).hexdigest()))
        self.assertNotIn(b"Consultas disponibles", agents)
        before = snapshot(self.output)
        self.assertFalse(self.create2().created)
        self.assertEqual(snapshot(self.output), before)
        with self.assertRaises(InstanceError) as ctx:
            self.create()  # a v1 request on a v2 folder is not a migration
        self.assertEqual(ctx.exception.code, "CONFLICT")
        v1 = self.root / "v1"
        self.create(v1)
        with self.assertRaises(InstanceError) as ctx:
            self.create2(v1)
        self.assertEqual(ctx.exception.code, "CONFLICT")
        self.assertEqual(snapshot(self.output), before)

    def test_version_argument(self):
        for value in (True, 0, 3, "2", 2.0, None):
            with self.subTest(value=value):
                with self.assertRaises(InstanceError) as ctx:
                    create_instance(self.workspace, output=self.output, core_root=ROOT,
                                    instructions_version=value)
                self.assertEqual(ctx.exception.code, "INVALID_STATE")
        self.assertFalse(self.output.exists())

    def test_descriptor_manipulations_fail_closed(self):
        self.create2()
        original = self.tree(self.output)
        good = self.descriptor()
        canonical = instance_module.canonical_json_bytes

        def variant(**changes):
            data = json.loads(json.dumps(good))
            for key, value in changes.items():
                if value is KeyError:
                    del data[key]
                else:
                    data[key] = value
            return canonical(data, pretty=True)

        swapped = list(reversed(good["files"]))
        resized = json.loads(json.dumps(good["files"]))
        resized[0]["size"] += 1
        rehashed = json.loads(json.dumps(good["files"]))
        rehashed[1]["sha256"] = "0" * 64
        cases = {
            "version 1": variant(instructions_version=1),
            "version 3": variant(instructions_version=3),
            "version text": variant(instructions_version="2"),
            "version bool": variant(instructions_version=True),
            "format": variant(format="otro"),
            "extra key": variant(extra=1),
            "missing key": variant(instructions_sha256=KeyError),
            "order": variant(files=swapped),
            "size": variant(files=resized),
            "hash": variant(files=rehashed),
            "set hash": variant(instructions_sha256="0" * 64),
            "not canonical": canonical(good, pretty=False),
            "a list": canonical([good], pretty=True),
        }
        for name, data in cases.items():
            with self.subTest(case=name):
                self.rewrite({"work/instructions.json": data})
                self.assert_invalid()
                self.rewrite({path: original[path] for path in original
                              if path != "work/integrity.json"})
                self.assertEqual(self.tree(self.output), original)
        with self.subTest(case="descriptor removed"):
            self.rewrite({"work/instructions.json": None})
            self.assert_invalid("instrucciones v1")
        self.rewrite({"work/instructions.json": original["work/instructions.json"]})
        self.assertEqual(load_instance(self.output).instructions.version, 2)

    def test_mixed_sets_and_uncovered_descriptor(self):
        self.create2()
        original = self.tree(self.output)
        config = load_instance(self.output).config
        v1_agents = instance_module.render_instructions(instance_module.AGENTS_TEMPLATE, config)
        # AGENTS v1 + CLAUDE v2 with a descriptor that describes them both exactly.
        files = [{"path": "AGENTS.md", "sha256": hashlib.sha256(v1_agents).hexdigest(),
                  "size": len(v1_agents)}, self.descriptor()["files"][1]]
        set_sha = instance_module._sha256(instance_module.canonical_json_bytes(
            {"files": files, "format": "roleplay-agent-core-instance-instructions",
             "instructions_version": 2}, pretty=False))
        mixed = instance_module.canonical_json_bytes(
            {"files": files, "format": "roleplay-agent-core-instance-instructions",
             "instructions_sha256": set_sha, "instructions_version": 2}, pretty=True)
        self.rewrite({"AGENTS.md": v1_agents, "work/instructions.json": mixed})
        self.assert_invalid("AGENTS.md no corresponde a su plantilla (instrucciones v2)")
        self.rewrite({path: original[path] for path in original if path != "work/integrity.json"})
        # Both Markdown v1 but a descriptor present: not a v1 instance either.
        v1_claude = instance_module.render_instructions(instance_module.CLAUDE_TEMPLATE, config)
        self.rewrite({"AGENTS.md": v1_agents, "CLAUDE.md": v1_claude})
        self.assert_invalid()
        self.rewrite({path: original[path] for path in original if path != "work/integrity.json"})
        # A descriptor the manifest does not list.
        integrity = json.loads(original["work/integrity.json"])
        integrity["files"] = [f for f in integrity["files"]
                              if f["path"] != "work/instructions.json"]
        (self.output / "work" / "integrity.json").write_bytes(
            instance_module.canonical_json_bytes(integrity, pretty=True))
        self.assert_invalid()
        (self.output / "work" / "integrity.json").write_bytes(original["work/integrity.json"])
        (self.output / "work" / "otro.json").write_bytes(b"{}")
        self.assert_invalid()
        (self.output / "work" / "otro.json").unlink()
        descriptor = self.output / "work" / "instructions.json"
        descriptor.unlink()
        descriptor.mkdir()
        self.assert_invalid()
        descriptor.rmdir()
        descriptor.write_bytes(original["work/instructions.json"])
        self.assertEqual(self.tree(self.output), original)
        self.assertEqual(load_instance(self.output).instructions.version, 2)


if __name__ == "__main__":
    unittest.main()
