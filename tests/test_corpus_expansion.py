import copy
import hashlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from adapters.manual import load_manual_dossier
from core.review.models import ReviewStatus
from core.runtime import assimilation
from core.runtime.assimilation import (
    ADDITIVE_FORMAT,
    LEGACY_FORMAT,
    AssimilationError,
    AssimilationState,
    add_candidate,
    close_expansion,
    decode_closed_corpus,
    merge_closed_expansion,
    record_candidate_decision,
    snapshot_record,
)
from core.runtime.instance import (
    InstanceError,
    closed_corpus_of,
    create_instance,
    load_instance,
)
from core.runtime.persistence import canonical_json_bytes, load_state
from core.runtime.workspace import (
    BASE_CORPUS,
    CORPUS_STATE,
    EXPANSION_WORKSPACE_KIND,
    WorkspaceError,
    compare_additive_dossier,
    create_expansion_workspace,
    load_workspace,
)
from tests.instance_support import FIXTURE, ROOT, closed_workspace
from tests.test_assimilation_decisions import FakeTerminal

APPROVED, REJECTED = ReviewStatus.APPROVED, ReviewStatus.REJECTED
SETTING_END = "Fin del pasaje de ambientación.\n~~~~~\n"
NEW_SETTING = ('\n### Fuente\nMetadatos: id="razas" | versión="1" | autoridad="Staff" | '
               'alcance="foro"\n~~~~ texto\nLas criaturas del norte nacen del hielo.\n'
               "Las del sur, del fuego.\n~~~~\n")
NEW_QUOTE = "Las criaturas del norte nacen del hielo."


def successor_dossier(root: Path, name="exp2", version="2026-10-14", edit=None,
                      new_setting=True) -> Path:
    """A copy of the neutral fixture with another version and, by default, one new source."""
    target = root / name
    shutil.copytree(FIXTURE, target)
    text = (target / "expediente.md").read_text(encoding="utf-8")
    text = text.replace("versión_expediente: 2026-10-11", f"versión_expediente: {version}")
    if new_setting:
        text = text.replace(SETTING_END, SETTING_END + NEW_SETTING)
    if edit is not None:
        text = edit(text, target)
    (target / "expediente.md").write_bytes(text.encode("utf-8"))
    return target


def new_candidate(candidate_id="hielo", version=1, quote=NEW_QUOTE, cls="LITERAL",
                  extra_citations=(), text=None):
    citations = [{"dossier_section": "setting", "source_id": "razas", "source_version": "1",
                  "declared_passage": None, "quote": quote}, *extra_citations]
    return {"candidate_id": candidate_id, "version": version, "domain": "WORLD", "class": cls,
            "text": quote if text is None else text, "scope": "foro", "citations": citations}


OLD_SETTING_CITATION = {"dossier_section": "setting", "source_id": "mundo-base",
                        "source_version": "2", "declared_passage": None, "quote": "# Mundo base"}


class ExpansionCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._base = Path(tempfile.mkdtemp())
        cls._workspace = closed_workspace(cls._base)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._base)

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        workspace = self.root / "ws"
        shutil.copytree(self._workspace, workspace)
        self.instance = self.root / "instancia"
        create_instance(workspace, output=self.instance, core_root=ROOT)
        shutil.rmtree(workspace)  # an expansion never needs the original workspace
        self.successor = successor_dossier(self.root)
        self.workspace = self.root / "ampliacion"

    def extend(self, dossier_dir=None, workspace=None):
        dossier_dir = dossier_dir or self.successor
        return create_expansion_workspace(self.instance, dossier=load_manual_dossier(dossier_dir),
                                          dossier_dir=dossier_dir,
                                          workspace=workspace or self.workspace, core_root=ROOT)

    def loaded(self):
        return load_workspace(self.workspace, expected_core_root=ROOT)

    def add(self, value):
        loaded = self.loaded()
        return add_candidate(self.workspace / CORPUS_STATE, dossier=loaded.dossier,
                             expected_revision=loaded.corpus_revision, value=value,
                             context=loaded.expansion)

    def decide(self, candidate_id="hielo", version=1, status=APPROVED, terminal=None):
        loaded = self.loaded()
        return record_candidate_decision(
            self.workspace / CORPUS_STATE, dossier=loaded.dossier,
            expected_revision=loaded.corpus_revision, candidate_id=candidate_id, version=version,
            review_status=status, terminal=terminal or FakeTerminal(), context=loaded.expansion)

    def close(self, terminal=None):
        loaded = self.loaded()
        return close_expansion(self.workspace / CORPUS_STATE, dossier=loaded.dossier,
                               context=loaded.expansion,
                               expected_revision=loaded.corpus_revision,
                               terminal=terminal or FakeTerminal())

    def closed_round(self, *values, status=APPROVED):
        self.extend()
        for value in values or (new_candidate(),):
            self.add(value)
            self.decide(value["candidate_id"], value["version"], status)
        return self.close()


class DossierComparisonTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        self.base = load_manual_dossier(FIXTURE)

    def compare(self, path, base=None, previous=("2026-10-11",)):
        return compare_additive_dossier(base or self.base, load_manual_dossier(path),
                                        previous_versions=previous)

    def test_additions_are_accepted(self):
        self.assertEqual(self.compare(successor_dossier(self.root)).new_sources, (("razas", "1"),))

        def new_version(text, target):
            (target / "materials" / "manual-foro-v2.md").write_bytes(
                (target / "materials" / "manual-foro.md").read_bytes() + b"Nueva regla.\n")
            return text.replace(
                '| pasaje="Convivencia"\n',
                '| pasaje="Convivencia"\n\n### Fuente\nMetadatos: id="manual-foro" | versión="2" '
                '| autoridad="Staff" | alcance="foro" | archivo="materials/manual-foro-v2.md"\n')

        delta = self.compare(successor_dossier(self.root, "v2", edit=new_version,
                                               new_setting=False))
        self.assertEqual(delta.new_sources, (("manual-foro", "2"),))

        def loose(text, target):
            return text + ('\n### Fuente\nMetadatos: id="anexo" | versión="1" | '
                           'autoridad="Staff" | alcance="foro"\n~~~~ texto\nAnexo.\n~~~~\n')

        self.assertEqual(self.compare(successor_dossier(self.root, "loose", edit=loose,
                                                        new_setting=False)).new_sources,
                         (("anexo", "1"),))

    def test_missing_section_can_become_provided(self):
        def missing(text, target):
            return text.replace("## Sistema de combate\nEstado: NO APLICA\n"
                                "Nota: El foro no tiene combate mecánico.\n",
                                "## Sistema de combate\nEstado: FALTA\n"
                                "Nota: El foro no tiene combate mecánico.\n")

        base = load_manual_dossier(successor_dossier(self.root, "base", version="2026-10-11",
                                                     edit=missing, new_setting=False))

        def provided(text, target):
            return missing(text, target).replace(
                "Estado: FALTA\nNota: El foro no tiene combate mecánico.\n",
                'Nota: El foro no tiene combate mecánico.\n### Fuente\nMetadatos: id="combate" | '
                'versión="1" | autoridad="Staff" | alcance="foro"\n~~~~ texto\nTurnos.\n~~~~\n')

        delta = self.compare(successor_dossier(self.root, "prov", edit=provided,
                                               new_setting=False), base=base)
        self.assertEqual(delta.new_sources, (("combate", "1"),))
        with self.assertRaises(WorkspaceError) as ctx:
            self.compare(successor_dossier(self.root, "na", edit=provided, new_setting=False))
        self.assertEqual(ctx.exception.code, "CONFLICT")

    def test_non_additive_changes_are_conflicts(self):
        cases = {
            "same version": dict(version="2026-10-11"),
            "used version": dict(version="2025-01-01"),
            "nothing new": dict(new_setting=False),
            "renamed forum": dict(edit=lambda t, d: t.replace("nombre: Foro neutral de prueba",
                                                               "nombre: Otro nombre")),
            "edited inline text": dict(edit=lambda t, d: t.replace(
                "en negrita.", "en cursiva.")),
            "edited metadata": dict(edit=lambda t, d: t.replace(
                'id="revision-staff" | versión="1" | autoridad="Staff"',
                'id="revision-staff" | versión="1" | autoridad="Moderación"')),
            "edited note": dict(edit=lambda t, d: t.replace(
                "Nota: El foro no tiene combate mecánico.", "Nota: Cambiada.")),
            "deleted source": dict(new_setting=False, edit=lambda t, d: t.replace(
                'id="formato-posts"', 'id="formato-nuevo"')),
            "edited file": dict(edit=lambda t, d: (
                (d / "materials" / "manual-foro.md").write_bytes(
                    (d / "materials" / "manual-foro.md").read_bytes() + b"x\n"), t)[1]),
            "status changed": dict(edit=lambda t, d: t.replace(
                "## Creación de técnicas o habilidades\nEstado: NO APLICA\n",
                '## Creación de técnicas o habilidades\n### Fuente\nMetadatos: id="tec" | '
                'versión="1" | autoridad="Staff" | alcance="foro"\n~~~~ texto\nT.\n~~~~\n')),
            "old key reused": dict(new_setting=False, edit=lambda t, d: t.replace(
                '| pasaje="Convivencia"\n',
                '| pasaje="Convivencia"\n\n### Fuente\nMetadatos: id="manual-foro" | versión="1" '
                '| autoridad="Staff" | alcance="foro" | archivo="materials/manual-foro.md" | '
                'pasaje="Otra parte"\n')),
        }
        for name, kwargs in cases.items():
            with self.subTest(name):
                path = successor_dossier(self.root, name.replace(" ", "-"), **kwargs)
                with self.assertRaises(WorkspaceError) as ctx:
                    self.compare(path, previous=("2026-10-11", "2025-01-01"))
                self.assertEqual(ctx.exception.code, "CONFLICT", name)

    def test_removed_loose_material_is_a_conflict(self):
        def drop(text, target):
            index = text.index('### Fuente\nMetadatos: id="aviso-staff"')
            return text[:index].rstrip("\n") + "\n"

        with self.assertRaises(WorkspaceError) as ctx:
            self.compare(successor_dossier(self.root, "drop", edit=drop))
        self.assertEqual(ctx.exception.code, "CONFLICT")


class ExpansionWorkspaceTest(ExpansionCase):
    def test_layout_bytes_and_binding(self):
        result = self.extend()
        self.assertTrue(result.created)
        loaded = result.workspace
        instance = load_instance(self.instance)
        files = sorted(p.relative_to(self.workspace).as_posix()
                       for p in self.workspace.rglob("*") if p.is_file())
        self.assertIn(BASE_CORPUS, files)
        self.assertIn("base/dossier/expediente.md", files)
        self.assertIn("dossier/expediente.md", files)
        self.assertEqual((self.workspace / BASE_CORPUS).read_bytes(),
                         (self.instance / "corpus" / "state.json").read_bytes())
        for managed in instance.config.dossier_files:
            self.assertEqual((self.workspace / "base" / managed.path).read_bytes(),
                             (self.instance / managed.path).read_bytes())
        config = json.loads((self.workspace / "workspace.json").read_text(encoding="utf-8"))
        self.assertEqual((config["kind"], config["schema_version"]),
                         (EXPANSION_WORKSPACE_KIND, 2))
        self.assertEqual(config["base_instance"], {
            "corpus_revision": instance.corpus_revision,
            "corpus_sha256": hashlib.sha256(
                (self.instance / "corpus" / "state.json").read_bytes()).hexdigest(),
            "instance_json_sha256": hashlib.sha256(
                (self.instance / "instance.json").read_bytes()).hexdigest(),
            "integrity_sha256": hashlib.sha256(
                (self.instance / "work" / "integrity.json").read_bytes()).hexdigest(),
            "snapshot_sha256": instance.closure.snapshot_sha256})
        integrity = json.loads((self.workspace / "work" / "integrity.json").read_text("utf-8"))
        self.assertEqual(integrity["schema_version"], 2)
        self.assertNotIn(CORPUS_STATE, [f["path"] for f in integrity["files"]])
        self.assertEqual(load_state(self.workspace / CORPUS_STATE),
                         (instance.corpus_revision,
                          {"candidates": [], "closure": None, "decisions": []}))
        context = loaded.expansion
        self.assertEqual((context.round, context.base.current.format, context.delta.version),
                         (2, LEGACY_FORMAT, "2026-10-14"))
        self.assertEqual((loaded.candidates, loaded.decisions, loaded.closure), ((), (), None))
        self.assertNotIn(str(self.instance), (self.workspace / "workspace.json").read_text("utf-8"))

    def test_retry_conflicts_and_overlaps(self):
        self.extend()
        mtime = os.stat(self.workspace / "workspace.json").st_mtime_ns
        self.assertFalse(self.extend().created)
        self.assertEqual(os.stat(self.workspace / "workspace.json").st_mtime_ns, mtime)
        other = successor_dossier(self.root, "exp3", version="2026-10-15")
        with self.assertRaises(WorkspaceError) as ctx:
            self.extend(dossier_dir=other)
        self.assertEqual(ctx.exception.code, "CONFLICT")
        for target in (self.instance / "dentro", self.successor / "dentro"):
            with self.subTest(target=target.name):
                with self.assertRaises(WorkspaceError) as ctx:
                    self.extend(workspace=target)
                self.assertEqual(ctx.exception.code, "UNSAFE_DESTINATION")
        not_additive = successor_dossier(self.root, "same", version="2026-10-11")
        with self.assertRaises(WorkspaceError) as ctx:
            self.extend(dossier_dir=not_additive, workspace=self.root / "w2")
        self.assertEqual(ctx.exception.code, "CONFLICT")
        self.assertFalse((self.root / "w2").exists())
        self.assertEqual(sorted(p.name for p in self.root.iterdir() if ".staging-" in p.name), [])

    def test_tampering_is_detected(self):
        self.extend()
        cases = {
            "base corpus": self.workspace / BASE_CORPUS,
            "base dossier": self.workspace / "base" / "dossier" / "expediente.md",
            "workspace.json": self.workspace / "workspace.json",
        }
        for name, path in cases.items():
            with self.subTest(name):
                original = path.read_bytes()
                path.write_bytes(original.replace(b"a", b"b", 1))
                with self.assertRaises(WorkspaceError):
                    self.loaded()
                path.write_bytes(original)
        (self.workspace / "base" / "intruso.md").write_bytes(b"x")
        with self.assertRaises(WorkspaceError):
            self.loaded()

    def test_an_expansion_workspace_cannot_create_an_instance(self):
        self.closed_round()
        with self.assertRaises(InstanceError) as ctx:
            create_instance(self.workspace, output=self.root / "otra", core_root=ROOT)
        self.assertIn("instance update", ctx.exception.reason)


class RoundTest(ExpansionCase):
    def test_delta_rules(self):
        self.extend()
        with self.assertRaises(AssimilationError) as ctx:
            self.add(new_candidate("normas"))
        self.assertEqual(ctx.exception.code, "CONFLICT")
        with self.assertRaises(AssimilationError) as ctx:
            self.add({**new_candidate("viejo", text="# Mundo base"),
                      "citations": [OLD_SETTING_CITATION]})
        self.assertEqual(ctx.exception.code, "INVALID_STATE")
        mixed = new_candidate("mixto", cls="INTERPRETATION", text="Mezcla de fuentes.",
                              extra_citations=[OLD_SETTING_CITATION])
        self.assertTrue(self.add(mixed).created)
        self.assertTrue(self.add(new_candidate("hielo")).created)
        self.assertTrue(self.add(new_candidate("hielo", 2, quote="Las del sur, del fuego.")
                                 ).created)
        loaded = self.loaded()
        base_revision = loaded.expansion.base.revision
        self.assertEqual(loaded.corpus_revision, base_revision + 3)
        with self.assertRaises(AssimilationError):
            self.decide("hielo", 1)
        with self.assertRaises(AssimilationError):
            self.decide("normas", 3)
        self.decide("hielo", 2)
        self.decide("mixto", 1, REJECTED)
        self.assertEqual(self.loaded().corpus_revision, base_revision + 5)

    def test_closure_rules_prompt_and_revision(self):
        self.extend()
        with self.assertRaises(AssimilationError) as ctx:
            self.close()
        self.assertIn("ningún candidato nuevo", ctx.exception.reason)
        self.add(new_candidate())
        with self.assertRaises(AssimilationError) as ctx:
            self.close()
        self.assertIn("faltan decisiones", ctx.exception.reason)
        self.decide(status=REJECTED)
        loaded = self.loaded()
        terminal = FakeTerminal()
        result = self.close(terminal)
        snapshot = result.snapshot
        context = loaded.expansion
        prompt, phrase = terminal.output.rsplit("Escribe exactamente: ", 1)
        self.assertEqual(prompt, (
            "CIERRE HUMANO DE AMPLIACIÓN REQUERIDO\n"
            "Foro: foro-neutral\n"
            "Ronda: 2\n"
            "Expediente: 2026-10-11 -> 2026-10-14\n"
            f"Expediente SHA-256: {context.dossier.snapshot_sha256}\n"
            f"Snapshot padre SHA-256: {context.base.current.snapshot_sha256}\n"
            f"Revisión del corpus: {loaded.corpus_revision}\n"
            f"Snapshot nuevo SHA-256: {snapshot.snapshot_sha256}\n"
            "Nuevos vigentes: 1; aprobados: 0; rechazados: 1\n"
            "Rechazados: hielo v1\n"
            "Incertidumbres: ninguna\n"))
        self.assertRegex(phrase, rf"^CERRAR-AMPLIACION foro-neutral r2 c{loaded.corpus_revision} "
                                 r"[A-HJ-NP-Z2-9]{8}\n> $")
        self.assertEqual((snapshot.format, snapshot.ordinal, snapshot.closure_id,
                          snapshot.base_revision, result.corpus_revision),
                         (ADDITIVE_FORMAT, 2, "assimilation-closure:r2", loaded.corpus_revision,
                          loaded.corpus_revision + 1))
        self.assertEqual(snapshot.receipt.confirmation_sha256,
                         hashlib.sha256(phrase[:-3].encode()).hexdigest())
        data = (self.workspace / CORPUS_STATE).read_bytes()
        terminal = FakeTerminal()
        again = self.close(terminal)
        self.assertEqual((again.created, terminal.output), (False, ""))
        self.assertEqual((self.workspace / CORPUS_STATE).read_bytes(), data)
        with self.assertRaises(AssimilationError):
            self.add(new_candidate("otro"))
        with self.assertRaises(AssimilationError):
            self.decide(status=APPROVED)

    def test_answers_and_changes_during_the_prompt(self):
        self.extend()
        self.add(new_candidate())
        self.decide()
        data = (self.workspace / CORPUS_STATE).read_bytes()
        for transform in (lambda p: p.lower() + "\n", lambda p: None, lambda p: p + " \n"):
            with self.assertRaises(AssimilationError):
                self.close(FakeTerminal(transform=transform))
        terminal = FakeTerminal(interactive=False)
        with self.assertRaises(AssimilationError):
            self.close(terminal)
        self.assertEqual(terminal.output, "")

        def interrupt():
            raise KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            self.close(FakeTerminal(on_read=interrupt))
        self.assertEqual((self.workspace / CORPUS_STATE).read_bytes(), data)

        def concurrent():
            self.add(new_candidate("tarde", quote="Las del sur, del fuego."))

        with self.assertRaises(AssimilationError) as ctx:
            self.close(FakeTerminal(on_read=concurrent))
        self.assertEqual(ctx.exception.code, "CONFLICT")
        self.assertIsNone(self.loaded().closure)

    def test_input_changes_during_the_prompt_write_nothing(self):
        self.extend()
        self.add(new_candidate())
        self.decide()
        targets = {
            "base corpus": self.workspace / BASE_CORPUS,
            "base dossier": self.workspace / "base" / "dossier" / "expediente.md",
            "successor dossier": self.workspace / "dossier" / "expediente.md",
            "workspace.json": self.workspace / "workspace.json",
            "integrity": self.workspace / "work" / "integrity.json",
        }
        state = self.workspace / CORPUS_STATE
        for name, path in targets.items():
            with self.subTest(name):
                original, data = path.read_bytes(), state.read_bytes()
                revision = self.loaded().corpus_revision

                def touch():
                    path.write_bytes(original + b"\n")

                with self.assertRaises(AssimilationError) as ctx:
                    self.close(FakeTerminal(on_read=touch))
                self.assertEqual(ctx.exception.code, "CONFLICT")
                self.assertEqual(state.read_bytes(), data)
                path.write_bytes(original)
                self.assertEqual(self.loaded().corpus_revision, revision)
                self.assertIsNone(self.loaded().closure)
                self.assertFalse((self.workspace / "corpus" / "state.json.lock").exists())

    def test_coherent_config_rewrite_during_the_prompt_is_a_conflict(self):
        self.extend()
        self.add(new_candidate())
        self.decide()
        state = self.workspace / CORPUS_STATE
        data = state.read_bytes()
        config_path = self.workspace / "workspace.json"
        integrity_path = self.workspace / "work" / "integrity.json"
        originals = (config_path.read_bytes(), integrity_path.read_bytes())

        def rewrite():
            config = json.loads(originals[0])
            config["base_instance"]["instance_json_sha256"] = "f" * 64
            raw = canonical_json_bytes(config, pretty=True)
            integrity = json.loads(originals[1])
            for item in integrity["files"]:
                if item["path"] == "workspace.json":
                    item.update(sha256=hashlib.sha256(raw).hexdigest(), size=len(raw))
            config_path.write_bytes(raw)
            integrity_path.write_bytes(canonical_json_bytes(integrity, pretty=True))

        with self.assertRaises(AssimilationError) as ctx:
            self.close(FakeTerminal(on_read=rewrite))
        self.assertEqual(ctx.exception.code, "CONFLICT")
        self.assertEqual(state.read_bytes(), data)
        self.assertFalse((self.workspace / "corpus" / "state.json.lock").exists())
        self.assertIsNone(self.loaded().closure)  # the rewrite is coherent: it still loads

    def test_union_coverage_counts_earlier_snapshots(self):
        # All new candidates rejected: base literals still cover every section.
        result = self.closed_round(status=REJECTED)
        self.assertTrue(result.created)

    def test_tampered_round_closure_fails_to_load(self):
        self.closed_round()
        revision, content = load_state(self.workspace / CORPUS_STATE)
        from core.runtime.persistence import encode_state
        changes = {
            "snapshot hash": lambda c: c["closure"].update(snapshot_sha256="0" * 64),
            "parent": lambda c: c["closure"].update(parent_snapshot_sha256="1" * 64),
            "ordinal": lambda c: c["closure"].update(ordinal=3),
            "counts": lambda c: c["closure"].update(candidate_count=1),
            "evidence": lambda c: c["closure"]["evidence"].update(sha256="0" * 64),
            "receipt": lambda c: c["closure"]["receipt"].update(confirmation_sha256="0" * 64),
            "dossier version": lambda c: c["closure"]["dossier"].update(dossier_version="x"),
            "extra key": lambda c: c["closure"].update(nota=1),
        }
        original = (self.workspace / CORPUS_STATE).read_bytes()
        for name, change in changes.items():
            with self.subTest(name):
                tampered = copy.deepcopy(content)
                change(tampered)
                (self.workspace / CORPUS_STATE).write_bytes(encode_state(tampered,
                                                                         revision=revision))
                with self.assertRaises(WorkspaceError):
                    self.loaded()
        (self.workspace / CORPUS_STATE).write_bytes(original)
        self.loaded()

    def test_locks_on_round_closure(self):
        self.extend()
        self.add(new_candidate())
        self.decide()
        lock = self.workspace / "corpus" / "state.json.lock"
        lock.write_bytes(b"")
        terminal = FakeTerminal()
        with self.assertRaises(AssimilationError) as ctx:
            self.close(terminal)
        self.assertEqual((ctx.exception.code, terminal.output), ("CONFLICT", ""))
        lock.unlink()
        real_unlink = assimilation.os.unlink

        def stubborn(path, *args, **kwargs):
            if str(path).endswith(".lock"):
                raise PermissionError("bloqueado")
            return real_unlink(path, *args, **kwargs)

        with mock.patch.object(assimilation.os, "unlink", stubborn):
            with self.assertRaises(AssimilationError) as ctx:
                self.close()
        self.assertIn("el cambio se guardó", ctx.exception.reason)
        lock.unlink()
        self.assertIsNotNone(self.loaded().closure)


class ClosedChainTest(ExpansionCase):
    def chain(self):
        self.closed_round(new_candidate(), new_candidate("dos", quote="Las del sur, del fuego."))
        loaded = self.loaded()
        revision, content = merge_closed_expansion(
            loaded.expansion.base,
            AssimilationState(loaded.candidates, loaded.decisions, None), loaded.closure)
        return loaded, revision, content

    def decode(self, loaded, content, revision):
        return decode_closed_corpus(content, dossier=loaded.dossier, revision=revision,
                                    descriptor=loaded.expansion.dossier)

    def test_merge_decode_and_origin(self):
        loaded, revision, content = self.chain()
        self.assertEqual(set(content), {"candidates", "decisions", "snapshots"})
        chain = self.decode(loaded, content, revision)
        legacy, additive = chain.snapshots
        instance = load_instance(self.instance)
        original = load_state(self.instance / "corpus" / "state.json")[1]["closure"]
        self.assertEqual((legacy.format, legacy.closure_id, legacy.snapshot_sha256,
                          legacy.base_revision, legacy.corpus_revision),
                         (LEGACY_FORMAT, "assimilation-closure", original["snapshot_sha256"],
                          original["base_revision"], instance.corpus_revision))
        self.assertEqual(snapshot_record(legacy)["evidence"], original["evidence"])
        self.assertEqual(snapshot_record(legacy)["receipt"], original["receipt"])
        self.assertEqual(additive.parent_snapshot_sha256, legacy.snapshot_sha256)
        self.assertEqual(chain.snapshot_for("normas", 3), legacy)
        self.assertEqual(chain.snapshot_for("dos", 1), additive)
        self.assertIsNone(chain.snapshot_for("nada", 1))
        self.assertEqual(canonical_json_bytes(content, pretty=False),
                         canonical_json_bytes(merge_closed_expansion(
                             loaded.expansion.base,
                             AssimilationState(loaded.candidates, loaded.decisions, None),
                             loaded.closure)[1], pretty=False))

    def test_v1_content_reads_as_legacy(self):
        instance = load_instance(self.instance)
        chain = closed_corpus_of(instance)
        self.assertEqual([s.format for s in chain.snapshots], [LEGACY_FORMAT])
        self.assertEqual(len(chain.candidates), len(instance.candidates))
        revision, content = load_state(self.instance / "corpus" / "state.json")
        content["closure"] = None
        from core.runtime.workspace import dossier_descriptor
        with self.assertRaises(AssimilationError):
            decode_closed_corpus(content, dossier=instance.dossier, revision=revision,
                                 descriptor=dossier_descriptor(instance.dossier,
                                                               instance.config.dossier_files))

    def test_every_chain_tampering_is_rejected(self):
        loaded, revision, content = self.chain()
        legacy_candidates = loaded.expansion.base.current.candidate_count
        changes = {
            "extra key": lambda c: c.update(closure=None),
            "ordinal": lambda c: c["snapshots"][1].update(ordinal=3),
            "parent": lambda c: c["snapshots"][1].update(parent_snapshot_sha256="2" * 64),
            "counts": lambda c: c["snapshots"][1].update(candidate_count=legacy_candidates),
            "base revision": lambda c: c["snapshots"][1].update(
                base_revision=c["snapshots"][1]["base_revision"] + 1,
                corpus_revision=c["snapshots"][1]["corpus_revision"] + 1),
            "snapshot hash": lambda c: c["snapshots"][1].update(snapshot_sha256="0" * 64),
            "evidence": lambda c: c["snapshots"][1]["evidence"].update(sha256="0" * 64),
            "legacy evidence": lambda c: c["snapshots"][0]["evidence"].update(sha256="0" * 64),
            "legacy hash": lambda c: c["snapshots"][0].update(snapshot_sha256="0" * 64),
            "dossier hash": lambda c: c["snapshots"][1]["dossier"].update(snapshot_sha256="0" * 64),
            "candidate text": lambda c: c["candidates"][-1].update(text="otro"),
            "decision status": lambda c: c["decisions"][-1].update(review_status="REJECTED"),
            "snapshots order": lambda c: c["snapshots"].reverse(),
            "missing snapshot": lambda c: c["snapshots"].pop(),
            "legacy as additive": lambda c: c["snapshots"][0].update(format=ADDITIVE_FORMAT),
            "record outside snapshots": lambda c: c["decisions"].append(c["decisions"][0]),
        }
        for name, change in changes.items():
            with self.subTest(name):
                tampered = copy.deepcopy(content)
                change(tampered)
                with self.assertRaises(AssimilationError):
                    self.decode(loaded, tampered, revision)
        for wrong in (revision - 1, revision + 1):
            with self.assertRaises(AssimilationError):
                self.decode(loaded, content, wrong)

    def test_self_consistent_but_invalid_descriptors_are_rejected(self):
        loaded, revision, content = self.chain()
        current_version = content["snapshots"][-1]["dossier"]["dossier_version"]

        def rehash(dossier):
            core = {k: v for k, v in dossier.items() if k != "snapshot_sha256"}
            dossier["snapshot_sha256"] = hashlib.sha256(
                canonical_json_bytes(core, pretty=False)).hexdigest()

        changes = {
            "repeated version": lambda d: d.update(dossier_version=current_version),
            "other schema": lambda d: d.update(schema_version=2),
            "path outside dossier": lambda d: d["files"][0].update(path="../expediente.md"),
            "path traversal": lambda d: d["files"][0].update(path="dossier/../x.md"),
            "no main file": lambda d: d.update(files=[f for f in d["files"]
                                                      if f["path"] != "dossier/expediente.md"]),
        }
        for name, change in changes.items():
            with self.subTest(name):
                tampered = copy.deepcopy(content)
                change(tampered["snapshots"][0]["dossier"])
                rehash(tampered["snapshots"][0]["dossier"])
                with self.assertRaises(AssimilationError):
                    self.decode(loaded, tampered, revision)
        self.decode(loaded, content, revision)

    def test_suffix_cannot_reuse_a_closed_id(self):
        loaded, revision, content = self.chain()
        forged = copy.deepcopy(content)
        normas = next(c for c in forged["candidates"] if c["candidate_id"] == "normas")
        forged["candidates"][-1]["candidate_id"] = "normas"
        forged["candidates"][-1]["version"] = normas["version"] + 1
        with self.assertRaises(AssimilationError):
            self.decode(loaded, forged, revision)


if __name__ == "__main__":
    unittest.main()
