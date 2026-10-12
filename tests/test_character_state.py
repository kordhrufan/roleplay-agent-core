import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.character.models import CharacterError
from core.runtime import assimilation, character as character_module
from core.runtime.character import get_concept, import_concept, list_concepts
from core.runtime.instance import InstanceError, create_instance, load_instance
from core.runtime.persistence import encode_state, load_state
from tests.instance_support import ROOT, closed_workspace
from tests.test_assimilation_decisions import FakeTerminal


class CharacterCase(unittest.TestCase):
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
        self.workspace = self.root / "ws"
        shutil.copytree(self._workspace, self.workspace)
        self.instance = self.root / "instancia"
        create_instance(self.workspace, output=self.instance, core_root=ROOT)
        self.input = self.root / "concepto.md"
        self.write_input("# Aria\nExploradora curiosa.\n")

    def write_input(self, text: str) -> None:
        self.input.write_bytes(text.encode("utf-8"))

    def import_(self, character_id="aria", version=1, terminal=None, input_path=None):
        return import_concept(self.instance, expected_core_root=ROOT, character_id=character_id,
                              version=version, input_path=input_path or self.input,
                              terminal=terminal or FakeTerminal())

    def state_path(self, character_id="aria") -> Path:
        return self.instance / "characters" / character_id / "state.json"

    def loaded(self):
        return load_instance(self.instance, expected_core_root=ROOT)


class LoadTest(CharacterCase):
    def test_without_and_with_empty_characters_folder(self):
        self.assertEqual(self.loaded().characters, ())
        (self.instance / "characters").mkdir()
        self.assertEqual(self.loaded().characters, ())

    def test_several_characters_sorted_and_statics_untouched(self):
        statics = {p: p.read_bytes() for p in self.instance.rglob("*") if p.is_file()}
        for character_id in ("zeta", "aria", "mid"):
            self.import_(character_id)
        self.assertEqual([c.state.character_id for c in self.loaded().characters],
                         ["aria", "mid", "zeta"])
        for path, data in statics.items():
            self.assertEqual(path.read_bytes(), data)

    def test_works_after_workspace_is_deleted(self):
        self.import_()
        shutil.rmtree(self.workspace)
        self.assertEqual(self.loaded().characters[0].state.current_concept().version, 1)

    def test_extras_and_bad_states_are_rejected(self):
        self.import_()
        folder = self.instance / "characters"
        cases = {
            "file in characters": lambda: (folder / "nota.txt").write_bytes(b"x"),
            "invalid id folder": lambda: (folder / "a_b").mkdir(),
            "abandoned staging": lambda: (folder / ".aria.staging-1234").mkdir(),
            "extra file in character": lambda: (folder / "aria" / "otro.json").write_bytes(b"x"),
            "folder without state": lambda: (folder / "vacio").mkdir(),
        }
        for name, make in cases.items():
            with self.subTest(name):
                snapshot = {p for p in folder.rglob("*")}
                make()
                with self.assertRaises(InstanceError):
                    self.loaded()
                for path in sorted(set(folder.rglob("*")) - snapshot, reverse=True):
                    path.rmdir() if path.is_dir() else path.unlink()
        state = self.state_path()
        original = state.read_bytes()
        state.write_bytes(original.replace(b"Exploradora", b"Exploradoro"))
        with self.assertRaises(InstanceError):
            self.loaded()
        state.write_bytes(original)
        revision, content = load_state(state)
        content["character_id"] = "otro"
        state.write_bytes(encode_state(content, revision=revision))
        with self.assertRaises(InstanceError):
            self.loaded()
        state.write_bytes(original)
        self.loaded()

    def test_a_lock_does_not_block_reading(self):
        self.import_()
        (self.state_path().parent / "state.json.lock").write_bytes(b"")
        self.assertEqual(len(self.loaded().characters), 1)

    @unittest.skipUnless(os.name == "nt", "las junctions son de Windows")
    def test_junction_in_characters_is_rejected(self):
        import _winapi
        outside = self.root / "fuera"
        outside.mkdir()
        (self.instance / "characters").mkdir()
        _winapi.CreateJunction(str(outside), str(self.instance / "characters" / "aria"))
        with self.assertRaises(InstanceError):
            self.loaded()


class ImportTest(CharacterCase):
    def test_v1_prompt_state_and_receipt(self):
        terminal = FakeTerminal()
        with mock.patch.object(assimilation.secrets, "choice", side_effect=list("ABCDEFGH")):
            result = self.import_(terminal=terminal)
        concept = result.concept
        self.assertTrue(result.created)
        self.assertEqual(result.character.state_revision, 1)
        self.assertEqual(terminal.output,
                         "DECLARACIÓN HUMANA DE AUTORÍA\nPersonaje: aria\nVersión: 1\n"
                         f"SHA-256: {concept.concept_sha256}\nBytes UTF-8: {concept.utf8_size}\n"
                         "Termina en LF: SÍ\nConcepto exacto (hasta «Fin del concepto.»):\n"
                         "# Aria\nExploradora curiosa.\nFin del concepto.\n"
                         "Declara que este texto es el concepto que tú aportas; no una propuesta "
                         "del agente.\nEscribe exactamente: DECLARAR-CONCEPTO aria v1 ABCDEFGH\n> ")
        raw = self.state_path().read_text(encoding="utf-8")
        self.assertNotIn("ABCDEFGH", raw)
        self.assertNotIn(str(self.input), raw)
        self.assertNotIn(self.input.name, raw)
        self.assertEqual(sorted(p.name for p in self.state_path().parent.iterdir()), ["state.json"])

    def test_prompt_marks_text_without_final_lf(self):
        self.write_input("sin salto final")
        terminal = FakeTerminal()
        self.import_(terminal=terminal)
        self.assertIn("Termina en LF: NO\nConcepto exacto (hasta «Fin del concepto.»):\n"
                      "sin salto final\nFin del concepto.\n", terminal.output)

    def test_versions_retry_and_conflicts(self):
        self.import_()
        before = (self.state_path().read_bytes(), self.state_path().stat().st_mtime_ns)
        terminal = FakeTerminal()
        retry = self.import_(terminal=terminal)
        self.assertEqual((retry.created, terminal.output), (False, ""))
        self.assertEqual(before, (self.state_path().read_bytes(), self.state_path().stat().st_mtime_ns))
        cases = {
            "same version, other text": (1, "otro texto"),
            "version gap": (3, "otro texto"),
            "no-op new version": (2, "# Aria\nExploradora curiosa.\n"),
        }
        for name, (version, text) in cases.items():
            with self.subTest(name):
                self.write_input(text)
                with self.assertRaises(CharacterError) as ctx:
                    self.import_(version=version)
                self.assertEqual(ctx.exception.code, "CONFLICT")
        self.write_input("# Aria\nExploradora prudente.\n")
        second = self.import_(version=2)
        self.assertEqual((second.created, second.character.state_revision), (True, 2))
        loaded = self.loaded()
        self.assertEqual([c.version for c in list_concepts(loaded, character_id="aria")], [1, 2])
        self.assertEqual(get_concept(loaded, character_id="aria", version=1).text,
                         "# Aria\nExploradora curiosa.\n")

    def test_first_version_must_be_one(self):
        with self.assertRaises(CharacterError) as ctx:
            self.import_(version=2)
        self.assertEqual(ctx.exception.code, "CONFLICT")
        self.assertFalse((self.instance / "characters" / "aria").exists())

    def test_answer_rules(self):
        for name, transform in {"wrong": lambda p: p.lower() + "\n", "eof": lambda p: None}.items():
            with self.subTest(name):
                with self.assertRaises(CharacterError) as ctx:
                    self.import_(terminal=FakeTerminal(transform=transform))
                self.assertEqual(ctx.exception.code, "INVALID_STATE")
                self.assertFalse((self.instance / "characters" / "aria").exists())
        terminal = FakeTerminal(interactive=False)
        with self.assertRaises(CharacterError):
            self.import_(terminal=terminal)
        self.assertEqual(terminal.output, "")

    def test_keyboard_interrupt_writes_nothing(self):
        def interrupt():
            raise KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            self.import_(terminal=FakeTerminal(on_read=interrupt))
        self.assertFalse((self.instance / "characters" / "aria").exists())

    def test_input_rules(self):
        cases = {
            "bom": b"\xef\xbb\xbfhola",
            "invalid utf-8": b"\xff",
            "empty": b"",
            "control": b"hola\x07",
        }
        for name, raw in cases.items():
            with self.subTest(name):
                self.input.write_bytes(raw)
                with self.assertRaises(CharacterError) as ctx:
                    self.import_()
                self.assertEqual(ctx.exception.code, "INVALID_STATE")
        inside_instance = self.instance / "concepto.md"
        for path in (inside_instance, ROOT / "tests" / "fixtures" / "dossiers" / "minimal-neutral"
                     / "materials" / "manual-foro.md", self.root / "no-existe.md"):
            with self.subTest(path=path.name):
                with self.assertRaises(CharacterError):
                    self.import_(input_path=path)

    @unittest.skipUnless(os.name == "nt", "las junctions son de Windows")
    def test_input_through_junction_is_rejected(self):
        import _winapi
        real = self.root / "real"
        real.mkdir()
        (real / "c.md").write_bytes(b"concepto\n")
        _winapi.CreateJunction(str(real), str(self.root / "enlace"))
        with self.assertRaises(CharacterError):
            self.import_(input_path=self.root / "enlace" / "c.md")

    def test_change_between_prompt_and_write(self):
        def change_input():
            self.write_input("otro texto distinto\n")

        with self.assertRaises(CharacterError) as ctx:
            self.import_(terminal=FakeTerminal(on_read=change_input))
        self.assertEqual(ctx.exception.code, "CONFLICT")
        self.assertFalse((self.instance / "characters" / "aria").exists())
        self.write_input("# Aria\nExploradora curiosa.\n")
        self.import_()
        self.write_input("versión dos\n")
        other = self.root / "otro.md"
        other.write_bytes("versión dos concurrente\n".encode("utf-8"))

        def concurrent_v2():
            self.import_(version=2, input_path=other)

        with self.assertRaises(CharacterError) as ctx:
            self.import_(version=2, terminal=FakeTerminal(on_read=concurrent_v2))
        self.assertEqual(ctx.exception.code, "CONFLICT")
        self.assertEqual(get_concept(self.loaded(), character_id="aria", version=2).text,
                         "versión dos concurrente\n")

    def test_locks(self):
        self.import_()
        lock = self.state_path().parent / "state.json.lock"
        lock.write_bytes(b"")
        self.write_input("versión dos\n")
        terminal = FakeTerminal()
        with self.assertRaises(CharacterError) as ctx:
            self.import_(version=2, terminal=terminal)
        self.assertEqual(ctx.exception.code, "CONFLICT")
        self.assertIn(str(lock), ctx.exception.reason)
        self.assertEqual(terminal.output, "")
        lock.unlink()
        real_unlink = assimilation.os.unlink

        def stubborn(path, *args, **kwargs):
            if str(path).endswith(".lock"):
                raise PermissionError("bloqueado")
            return real_unlink(path, *args, **kwargs)

        with mock.patch.object(assimilation.os, "unlink", stubborn):
            with self.assertRaises(CharacterError) as ctx:
                self.import_(version=2)
        self.assertEqual(ctx.exception.code, "IO")
        self.assertIn("el cambio se guardó", ctx.exception.reason)
        lock.unlink()
        self.assertEqual(self.loaded().characters[0].state_revision, 2)

    def swap_for_junction(self):
        """Move the character folder aside and put a junction to it in its place."""
        import _winapi
        folder = self.instance / "characters" / "aria"
        aside = self.root / "fuera-aria"
        folder.rename(aside)
        _winapi.CreateJunction(str(aside), str(folder))
        return aside

    @unittest.skipUnless(os.name == "nt", "las junctions son de Windows")
    def test_junction_swap_when_taking_the_lock_writes_nothing_outside(self):
        self.import_()
        self.write_input("versión dos\n")
        real_lock = character_module._corpus_lock
        swapped = {}

        def racing_lock(state_path, subject, guard=None):
            swapped["aside"] = self.swap_for_junction()
            return real_lock(state_path, subject, guard=guard)

        with mock.patch.object(character_module, "_corpus_lock", racing_lock):
            with self.assertRaises(CharacterError) as ctx:
                self.import_(version=2)
        self.assertEqual(ctx.exception.code, "UNSAFE_DESTINATION")
        aside = swapped["aside"]
        self.assertEqual(sorted(p.name for p in aside.iterdir()), ["state.json"])
        self.assertEqual(load_state(aside / "state.json")[0], 1)

    @unittest.skipUnless(os.name == "nt", "las junctions son de Windows")
    def test_junction_swap_right_before_writing_writes_nothing_outside(self):
        self.import_()
        self.write_input("versión dos\n")
        real_load_state = character_module.load_state
        swapped = {}

        def racing_load_state(path):
            result = real_load_state(path)
            if "aside" not in swapped:
                swapped["aside"] = self.swap_for_junction()
            return result

        with mock.patch.object(character_module, "load_state", racing_load_state):
            with self.assertRaises(CharacterError) as ctx:
                self.import_(version=2)
        self.assertIn(ctx.exception.code, ("UNSAFE_DESTINATION", "CONFLICT"))
        aside = swapped["aside"]
        self.assertEqual(sorted(p.name for p in aside.iterdir()), ["state.json"])
        self.assertEqual(load_state(aside / "state.json")[0], 1)

    def test_failed_lock_release_is_reported_for_any_error_type(self):
        from core.runtime.persistence import PersistenceError
        state = self.root / "estado.json"
        lock = self.root / "estado.json.lock"
        real_unlink = assimilation.os.unlink

        def stubborn(path, *args, **kwargs):
            if str(path).endswith(".lock"):
                raise PermissionError("bloqueado")
            return real_unlink(path, *args, **kwargs)

        for error in (CharacterError("CONFLICT", "estado concurrente"),
                      PersistenceError("IO", "disco lleno")):
            with self.subTest(error=type(error).__name__):
                with mock.patch.object(assimilation.os, "unlink", stubborn):
                    with self.assertRaises(type(error)) as ctx:
                        with assimilation._corpus_lock(state, "este personaje"):
                            raise error
                self.assertEqual(ctx.exception.code, error.code)
                self.assertIn(error.reason, ctx.exception.reason)
                self.assertIn("no se guardó ningún cambio", ctx.exception.reason)
                self.assertIn(str(lock), ctx.exception.reason)
                self.assertIs(ctx.exception.__cause__, error)
                lock.unlink()
        for error in (RuntimeError("fallo inesperado"), KeyboardInterrupt()):
            with self.subTest(error=type(error).__name__):
                with mock.patch.object(assimilation.os, "unlink", stubborn):
                    with self.assertRaises(type(error)) as ctx:
                        with assimilation._corpus_lock(state, "este personaje"):
                            raise error
                self.assertIs(ctx.exception, error)
                notes = " ".join(getattr(ctx.exception, "__notes__", []))
                self.assertIn("no se guardó ningún cambio", notes)
                self.assertIn(str(lock), notes)
                lock.unlink()

    def test_failed_publish_leaves_no_character(self):
        from core.runtime import workspace as workspace_module
        with mock.patch.object(workspace_module.os, "replace", side_effect=OSError("simulado")):
            with self.assertRaises(CharacterError) as ctx:
                self.import_()
        self.assertEqual(ctx.exception.code, "IO")
        folder = self.instance / "characters"
        self.assertEqual(list(folder.iterdir()), [])
        self.loaded()

    def test_failed_append_keeps_previous_state(self):
        from core.runtime import persistence
        self.import_()
        before = self.state_path().read_bytes()
        self.write_input("versión dos\n")
        with mock.patch.object(persistence.os, "replace", side_effect=OSError("simulado")):
            with self.assertRaises(CharacterError) as ctx:
                self.import_(version=2)
        self.assertEqual(ctx.exception.code, "IO")
        self.assertEqual(self.state_path().read_bytes(), before)
        self.assertFalse((self.state_path().parent / "state.json.lock").exists())

    def test_race_on_first_version(self):
        def competitor():
            target = self.instance / "characters" / "aria"
            target.mkdir(parents=True)
            (target / "state.json").write_bytes(b"de otro proceso")

        real_publish = character_module._publish

        def racing_publish(staging, target, initial):
            competitor()
            return real_publish(staging, target, initial)

        with mock.patch.object(character_module, "_publish", racing_publish):
            with self.assertRaises(CharacterError) as ctx:
                self.import_()
        self.assertEqual(ctx.exception.code, "CONFLICT")
        self.assertEqual((self.state_path()).read_bytes(), b"de otro proceso")
        self.assertFalse([p for p in (self.instance / "characters").iterdir()
                          if ".staging-" in p.name])


if __name__ == "__main__":
    unittest.main()
