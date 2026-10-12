import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.character.models import concept_record
from core.runtime import cli
from core.runtime.character import import_concept
from core.runtime.instance import create_instance, load_instance
from tests.instance_support import ROOT, closed_workspace
from tests.test_assimilation_decisions import FakeTerminal


def run(*argv: str, stdin: str = "") -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
            mock.patch.object(sys, "stdin", io.StringIO(stdin)):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class CharacterCliCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(tempfile.mkdtemp())
        workspace = closed_workspace(cls.root)
        cls.instance = cls.root / "instancia"
        create_instance(workspace, output=cls.instance, core_root=ROOT)
        cls.input = cls.root / "concepto.md"
        for version, text in ((1, "# Aria\nExploradora.\n"), (2, "# Aria\nSin salto final")):
            cls.input.write_bytes(text.encode("utf-8"))
            import_concept(cls.instance, expected_core_root=ROOT, character_id="aria",
                           version=version, input_path=cls.input, terminal=FakeTerminal())
        cls.path = str(cls.instance)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.root)

    def loaded_character(self):
        return load_instance(self.instance).characters[0]


class ParserTest(CharacterCliCase):
    def test_required_arguments_and_positive_version(self):
        for argv in (["character", "concept", "import", "--instance", "x", "--character-id", "a",
                      "--version", "1"],
                     ["character", "concept", "import", "--instance", "x", "--character-id", "a",
                      "--input", "x"],
                     ["character", "concept", "list", "--instance", "x"],
                     ["character", "concept", "show", "--instance", "x", "--character-id", "a"],
                     ["character", "concept", "show", "--instance", "x", "--character-id", "a",
                      "--version", "0"],
                     ["character", "concept", "import", "--instance", "x", "--character-id", "a",
                      "--version", "1", "--input", "x", "--yes"],
                     ["character", "proposal", "add"], ["character", "draft"]):
            with self.subTest(argv=argv):
                self.assertEqual(run(*argv)[0], 2)


class ImportCliTest(CharacterCliCase):
    def argv(self, version="3"):
        return ["character", "concept", "import", "--instance", self.path, "--character-id",
                "aria", "--version", version, "--input", str(self.input)]

    def test_json_is_rejected_before_any_prompt(self):
        before = self.loaded_character().state_revision
        code, out, _ = run("--json", *self.argv())
        self.assertEqual(code, 3)
        self.assertEqual(json.loads(out), {
            "ok": False, "code": "INVALID_STATE",
            "message": "las declaraciones humanas de concepto no admiten --json: ejecuta el "
                       "comando en tu terminal y responde a la confirmación"})
        self.assertEqual(self.loaded_character().state_revision, before)

    def test_non_interactive_stdin_cannot_import(self):
        before = self.loaded_character().state_revision
        self.input.write_bytes(b"otra version\n")
        code, out, err = run(*self.argv(), stdin="DECLARAR-CONCEPTO aria v3 ABCDEFGH\n")
        self.assertEqual((code, out), (3, ""))
        self.assertIn("terminal interactiva", err)
        result = subprocess.run([sys.executable, "-B", "-m", "core.runtime.cli", *self.argv()],
                                cwd=ROOT, capture_output=True, stdin=subprocess.DEVNULL)
        self.assertEqual(result.returncode, 3)
        self.assertNotIn("DECLARAR-CONCEPTO".encode(), result.stdout)
        self.assertEqual(self.loaded_character().state_revision, before)

    def test_success_output_through_the_cli_handler(self):
        self.input.write_bytes(b"# Aria\nExploradora.\n")
        with mock.patch.object(cli, "_SystemTerminal", FakeTerminal):
            code, out, _ = run(*self.argv("1"))
        concept = self.loaded_character().state.concepts[0]
        self.assertEqual((code, out), (0, f"Concepto ya existente: aria v1 | HUMAN_DECLARED | "
                                          f"sha256={concept.concept_sha256} | "
                                          f"bytes={concept.utf8_size}\nRevisión del personaje: 2.\n"))


class QueryCliTest(CharacterCliCase):
    def test_list_text_and_json(self):
        character = self.loaded_character()
        c1, c2 = character.state.concepts
        code, out, _ = run("character", "concept", "list", "--instance", self.path,
                           "--character-id", "aria")
        self.assertEqual((code, out), (0, "".join(
            f"aria v{c.version} | HUMAN_DECLARED | sha256={c.concept_sha256} | "
            f"bytes={c.utf8_size}\n" for c in (c1, c2))))
        code, out, _ = run("--json", "character", "concept", "list", "--instance", self.path,
                           "--character-id", "aria")
        expected = {"ok": True, "action": "character.concept.list", "character_id": "aria",
                    "concepts": [{"authorship": "HUMAN_DECLARED",
                                  "concept_sha256": c.concept_sha256,
                                  "evidence_sha256": c.evidence.sha256,
                                  "utf8_size": c.utf8_size, "version": c.version}
                                 for c in (c1, c2)],
                    "instance": self.path, "state_revision": character.state_revision}
        self.assertEqual(out, json.dumps(expected, ensure_ascii=True, sort_keys=True) + "\n")

    def test_show_text_and_json(self):
        character = self.loaded_character()
        c2 = character.state.concepts[1]
        code, out, _ = run("character", "concept", "show", "--instance", self.path,
                           "--character-id", "aria", "--version", "2")
        self.assertEqual((code, out), (0,
            f"aria v2 | HUMAN_DECLARED | sha256={c2.concept_sha256} | bytes={c2.utf8_size}\n"
            f"Evidencia: {c2.evidence.sha256}\n"
            "Texto (exacto, hasta «Fin del concepto.»):\n# Aria\nSin salto final\n"
            "Fin del concepto.\n"))
        code, out, _ = run("--json", "character", "concept", "show", "--instance", self.path,
                           "--character-id", "aria", "--version", "2")
        expected = {"ok": True, "action": "character.concept.show", "character_id": "aria",
                    "concept": concept_record("aria", c2), "instance": self.path,
                    "state_revision": character.state_revision}
        self.assertEqual(out, json.dumps(expected, ensure_ascii=True, sort_keys=True) + "\n")
        self.assertEqual(json.loads(out)["concept"]["text"], "# Aria\nSin salto final")

    def test_unknown_character_or_version(self):
        for argv in (["--character-id", "nadie", "--version", "1"],
                     ["--character-id", "aria", "--version", "9"]):
            with self.subTest(argv=argv):
                code, out, _ = run("--json", "character", "concept", "show", "--instance",
                                   self.path, *argv)
                self.assertEqual((code, json.loads(out)["code"]), (3, "INVALID_STATE"))
        code, _, _ = run("character", "concept", "list", "--instance", self.path,
                         "--character-id", "nadie")
        self.assertEqual(code, 3)

    def test_redirected_stdout_works_for_queries(self):
        result = subprocess.run([sys.executable, "-B", "-m", "core.runtime.cli", "character",
                                 "concept", "show", "--instance", self.path, "--character-id",
                                 "aria", "--version", "1"], cwd=ROOT, capture_output=True,
                                stdin=subprocess.DEVNULL)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b"# Aria\nExploradora.\nFin del concepto.\n", result.stdout)


if __name__ == "__main__":
    unittest.main()
