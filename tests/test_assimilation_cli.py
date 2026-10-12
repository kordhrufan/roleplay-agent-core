import contextlib
import importlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from adapters.manual import load_manual_dossier
from core.runtime import cli
from core.runtime.workspace import CORPUS_STATE, create_workspace

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "dossiers" / "minimal-neutral"
RESPECT = "Trata con respeto al resto de participantes"
MANUAL = {"dossier_section": "forum_rules", "source_id": "manual-foro", "source_version": "1",
          "declared_passage": "Convivencia"}
WORLD = {"dossier_section": "setting", "source_id": "mundo-base", "source_version": "2",
         "declared_passage": None}
CANDIDATES = {
    "LITERAL": {"candidate_id": "convivencia-respeto", "version": 1, "domain": "RULES",
                "class": "LITERAL", "text": RESPECT, "scope": "foro",
                "citations": [dict(MANUAL, quote=RESPECT)]},
    "INTERPRETATION": {"candidate_id": "turnos", "version": 1, "domain": "RULES",
                       "class": "INTERPRETATION", "text": "Un post por turno.", "scope": "foro",
                       "citations": [dict(MANUAL, quote="respeta el turno de cada post")]},
    "PROPOSAL": {"candidate_id": "region-inicial", "version": 1, "domain": "WORLD",
                 "class": "PROPOSAL", "text": "Empezar en la Llanura central.", "scope": "foro",
                 "citations": [dict(WORLD, quote="- Llanura central\n")]},
    "UNCERTAINTY": {"candidate_id": "clima-costa", "version": 1, "domain": "WORLD",
                    "class": "UNCERTAINTY", "text": "No consta el clima de la Costa norte.",
                    "scope": "foro", "citations": [dict(WORLD, quote="- Costa norte")]},
}


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class CliCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        shutil.copytree(FIXTURE, self.root / "exp")
        self.workspace = self.root / "ws"
        create_workspace(load_manual_dossier(self.root / "exp"), dossier_dir=self.root / "exp",
                         workspace=self.workspace, core_root=ROOT)
        self.ws = str(self.workspace)

    def input_file(self, value: object, name: str = "candidato.json") -> str:
        path = self.root / name
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return str(path)

    def add(self, value: object, *extra: str) -> tuple[int, str, str]:
        return run(*extra, "assimilation", "candidate", "add", "--workspace", self.ws,
                   "--input", self.input_file(value))

    def assert_error(self, out: str, code: str) -> None:
        payload = json.loads(out)
        self.assertEqual(set(payload), {"ok", "code", "message"})
        self.assertEqual((payload["ok"], payload["code"]), (False, code))


class ParserTest(CliCase):
    def test_import_has_no_side_effects(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            importlib.reload(cli)
        self.assertEqual(out.getvalue(), "")

    def test_workspace_is_required_everywhere(self):
        for argv in (["source", "list"], ["candidate", "list"], ["candidate", "add", "--input", "x"],
                     ["candidate", "show", "--candidate-id", "x"],
                     ["source", "show", "--section", "setting", "--source-id", "x",
                      "--source-version", "1"]):
            with self.subTest(argv=argv):
                self.assertEqual(run("assimilation", *argv)[0], 2)

    def test_passage_selectors_are_exclusive(self):
        code, _, _ = run("assimilation", "source", "show", "--workspace", self.ws, "--section",
                         "forum_rules", "--source-id", "manual-foro", "--source-version", "1",
                         "--declared-passage", "Convivencia", "--without-declared-passage")
        self.assertEqual(code, 2)

    def test_no_decision_closure_instance_or_publication_commands(self):
        for argv in (["assimilation", "candidate", "approve"], ["assimilation", "candidate", "reject"],
                     ["assimilation", "close"], ["assimilation", "decide"], ["instance"],
                     ["publish"], ["send"], ["post"], ["model"], ["turns"]):
            with self.subTest(argv=argv):
                self.assertEqual(run(*argv)[0], 2)


class SourceTest(CliCase):
    def test_list_json(self):
        code, out, _ = run("--json", "assimilation", "source", "list", "--workspace", self.ws)
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(set(payload), {"ok", "action", "sources", "workspace"})
        self.assertEqual(payload["action"], "assimilation.source.list")
        sources = payload["sources"]
        for source in sources:
            self.assertEqual(set(source), {"candidate_eligible", "declared_passage",
                                           "dossier_section", "domain", "source_id",
                                           "source_sha256", "source_version"})
        sections = [s["dossier_section"] for s in sources]
        self.assertEqual(sections, ["forum_rules", "setting", "character_creation", "staff_review",
                                    "platform_format", "loose_material", "loose_material"])
        loose = [s for s in sources if s["dossier_section"] == "loose_material"]
        self.assertTrue(all(not s["candidate_eligible"] and s["domain"] is None for s in loose))
        self.assertNotIn("materials/", out)
        self.assertNotIn("expediente.md", out)

    def test_list_text(self):
        code, out, _ = run("assimilation", "source", "list", "--workspace", self.ws)
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertEqual(len(lines), 7)
        self.assertTrue(lines[0].startswith("forum_rules | manual-foro | v1 | pasaje=Convivencia | sha256="))
        self.assertTrue(lines[0].endswith("| dominio=RULES | candidato=SI"))
        self.assertTrue(lines[1].startswith("setting | mundo-base | v2 | pasaje=null"))
        self.assertTrue(lines[-1].endswith("| dominio=null | candidato=NO"))

    def test_show_text_and_json(self):
        argv = ["assimilation", "source", "show", "--workspace", self.ws, "--section", "setting",
                "--source-id", "mundo-base", "--source-version", "2"]
        code, out, _ = run(*argv)
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith("setting | mundo-base | v2"))
        self.assertEqual(lines[1], " 1 | # Mundo base")
        code, out, _ = run("--json", *argv)
        payload = json.loads(out)
        self.assertEqual(set(payload), {"ok", "action", "source", "workspace"})
        literal = load_manual_dossier(self.root / "exp").sections[1].sources[0].literal_text
        self.assertEqual(payload["source"]["literal_text"], literal)

    def test_show_ambiguity_and_selectors(self):
        argv = ["assimilation", "source", "show", "--workspace", self.ws, "--section",
                "forum_rules", "--source-id", "manual-foro", "--source-version", "1"]
        self.assertEqual(run(*argv)[0], 0)
        code, out, _ = run("--json", *argv, "--without-declared-passage")
        self.assertEqual(code, 3)
        self.assert_error(out, "INVALID_STATE")
        self.assertEqual(run(*argv, "--declared-passage", "Convivencia")[0], 0)
        self.assertEqual(run(*argv, "--declared-passage", "Otro")[0], 3)

    def test_show_loose_material(self):
        code, out, _ = run("--json", "assimilation", "source", "show", "--workspace", self.ws,
                           "--section", "loose_material", "--source-id", "aviso-staff",
                           "--source-version", "1")
        self.assertEqual(code, 0)
        self.assertFalse(json.loads(out)["source"]["candidate_eligible"])

    def test_read_only(self):
        before = (self.workspace / CORPUS_STATE).stat().st_mtime_ns
        run("assimilation", "source", "list", "--workspace", self.ws)
        run("assimilation", "source", "show", "--workspace", self.ws, "--section", "setting",
            "--source-id", "mundo-base", "--source-version", "2")
        self.assertEqual(before, (self.workspace / CORPUS_STATE).stat().st_mtime_ns)


class CandidateTest(CliCase):
    def test_add_list_show_all_classes(self):
        for revision, (cls, value) in enumerate(CANDIDATES.items(), start=1):
            with self.subTest(cls=cls):
                code, out, _ = self.add(value, "--json")
                self.assertEqual(code, 0, out)
                payload = json.loads(out)
                self.assertEqual(set(payload), {"ok", "action", "candidate_id", "candidate_sha256",
                                                "corpus_revision", "created", "version",
                                                "workspace"})
                self.assertEqual((payload["created"], payload["corpus_revision"]), (True, revision))
        code, out, _ = run("--json", "assimilation", "candidate", "list", "--workspace", self.ws)
        payload = json.loads(out)
        self.assertEqual(set(payload), {"ok", "action", "candidates", "corpus_revision", "workspace"})
        self.assertEqual([c["class"] for c in payload["candidates"]], list(CANDIDATES))
        self.assertTrue(all(set(c) == {"candidate_id", "candidate_sha256", "class", "domain",
                                       "review_status", "version"} for c in payload["candidates"]))
        code, out, _ = run("assimilation", "candidate", "list", "--workspace", self.ws)
        lines = out.splitlines()
        self.assertEqual(len(lines), 4)
        self.assertTrue(lines[0].startswith("convivencia-respeto v1 | LITERAL | RULES | "
                                            "PENDING_HUMAN_REVIEW | sha256="))
        self.assertTrue(lines[3].endswith(" | REQUIERE CONFIRMACIÓN"))
        self.assertFalse(lines[0].endswith("CONFIRMACIÓN"))

    def test_add_text_and_retry(self):
        code, out, _ = self.add(CANDIDATES["LITERAL"])
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("Candidato añadido: convivencia-respeto v1"))
        self.assertTrue(out.rstrip().endswith("Revisión del corpus: 1."))
        code, out, _ = self.add(CANDIDATES["LITERAL"])
        self.assertTrue(out.startswith("Candidato ya existente:"))
        self.assertIn("Revisión del corpus: 1.", out)

    def test_show_latest_and_version(self):
        self.add(CANDIDATES["INTERPRETATION"])
        self.add(dict(CANDIDATES["INTERPRETATION"], version=2, text="Otro texto."))
        code, out, _ = run("--json", "assimilation", "candidate", "show", "--workspace", self.ws,
                           "--candidate-id", "turnos")
        payload = json.loads(out)
        self.assertEqual(set(payload), {"ok", "action", "candidate", "corpus_revision", "workspace"})
        self.assertEqual(payload["candidate"]["version"], 2)
        self.assertIn("candidate_sha256", payload["candidate"])
        code, out, _ = run("assimilation", "candidate", "show", "--workspace", self.ws,
                           "--candidate-id", "turnos", "--version", "1")
        self.assertEqual(code, 0)
        self.assertIn("turnos v1 | INTERPRETATION", out)
        self.assertIn("Cita: forum_rules | manual-foro | v1 | pasaje=Convivencia", out)
        self.assertTrue(out.endswith("Texto (exacto, hasta «Fin del texto.»):\nUn post por turno."
                                     "\n(el texto no termina en salto de línea)\nFin del texto.\n"))
        for argv in (["--candidate-id", "turnos", "--version", "3"], ["--candidate-id", "nada"]):
            with self.subTest(argv=argv):
                code, out, _ = run("--json", "assimilation", "candidate", "show", "--workspace",
                                   self.ws, *argv)
                self.assertEqual(code, 3)
                self.assert_error(out, "INVALID_STATE")

    def test_errors_and_codes(self):
        code, out, err = self.add(dict(CANDIDATES["LITERAL"], text="otro"))
        self.assertEqual((code, out), (3, ""))
        self.assertIn("Error (INVALID_STATE)", err)
        self.add(CANDIDATES["LITERAL"])
        code, out, _ = self.add(dict(CANDIDATES["LITERAL"], scope="otro"), "--json")
        self.assertEqual(code, 4)
        self.assert_error(out, "CONFLICT")
        code, out, _ = run("--json", "assimilation", "candidate", "add", "--workspace", self.ws,
                           "--input", str(self.root / "no-existe.json"))
        self.assertEqual(code, 5)
        self.assert_error(out, "IO")
        bad = self.root / "malo.json"
        bad.write_bytes(b'{"candidate_id": 1, "candidate_id": 2}')
        code, out, _ = run("--json", "assimilation", "candidate", "add", "--workspace", self.ws,
                           "--input", str(bad))
        self.assertEqual(code, 3)
        self.assert_error(out, "INVALID_STATE")

    def test_manipulated_workspace(self):
        self.add(CANDIDATES["LITERAL"])
        state = self.workspace / CORPUS_STATE
        state.write_bytes(state.read_bytes().replace(b"PENDING_HUMAN_REVIEW", b"APPROVED"))
        for argv in (["candidate", "list"], ["source", "list"]):
            with self.subTest(argv=argv):
                code, out, _ = run("--json", "assimilation", *argv, "--workspace", self.ws)
                self.assertEqual(code, 3)
                self.assert_error(out, "INVALID_STATE")


def inline(source_id: str, text: str, passage: str | None = None) -> str:
    extra = f' | pasaje="{passage}"' if passage else ""
    return (f'### Fuente\nMetadatos: id="{source_id}" | versión="1" | autoridad="Staff" | '
            f'alcance="foro"{extra}\n~~~~ texto\n{text}~~~~\n')


def file_source(source_id: str, path: str, passage: str) -> str:
    return (f'### Fuente\nMetadatos: id="{source_id}" | versión="1" | autoridad="Staff" | '
            f'alcance="foro" | archivo="{path}" | pasaje="{passage}"\n')


RULE_SECTIONS = {
    "forum_rules": "Normas generales",
    "character_creation": "Creación de fichas",
    "staff_review": "Revisión del staff",
    "platform_format": "Plataforma y formato",
    "combat_system": "Sistema de combate",
    "ability_technique_creation": "Creación de técnicas o habilidades",
}


class CustomDossierTest(unittest.TestCase):
    """A dossier with repeated declarations and every RULES section provided."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.root = root
        dossier = root / "exp"
        (dossier / "m").mkdir(parents=True)
        (dossier / "m" / "manual.md").write_bytes("Norma única del foro.\nOtra norma.\n".encode())
        bodies = {
            "Normas generales": (file_source("manual", "m/manual.md", "Normas")
                                 + file_source("manual", "m/manual.md", "Normas")
                                 + file_source("manual", "m/manual.md", "Otras")),
            "Ambientación": inline("mundo", "Un valle tranquilo.\n"),
        }
        for section, heading in RULE_SECTIONS.items():
            if section != "forum_rules":
                bodies[heading] = inline(f"fuente-{section.replace('_', '-')}",
                                         f"Regla de {heading}.\n")
        text = ("# Expediente del foro\nforum_id: foro-custom\nnombre: Foro custom\n"
                "versión_expediente: 1\n")
        for heading in ("Normas generales", "Ambientación", "Creación de fichas",
                        "Revisión del staff", "Plataforma y formato", "Sistema de combate",
                        "Creación de técnicas o habilidades"):
            text += f"\n## {heading}\n{bodies[heading]}"
        text += "\n## Material suelto\n"
        (dossier / "expediente.md").write_bytes(text.encode("utf-8"))
        self.ws = str(root / "ws")
        create_workspace(load_manual_dossier(dossier), dossier_dir=dossier, workspace=root / "ws",
                         core_root=ROOT)

    def add(self, value: dict) -> tuple[int, str, str]:
        path = self.root / f"{value['candidate_id']}-{value['version']}.json"
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return run("--json", "assimilation", "candidate", "add", "--workspace", self.ws,
                   "--input", str(path))

    def test_identical_declarations_collapse(self):
        code, out, _ = run("--json", "assimilation", "source", "list", "--workspace", self.ws)
        manual = [s for s in json.loads(out)["sources"] if s["source_id"] == "manual"]
        self.assertEqual([s["declared_passage"] for s in manual], ["Normas", "Otras"])
        citation = {"dossier_section": "forum_rules", "source_id": "manual", "source_version": "1",
                    "declared_passage": "Normas", "quote": "Norma única del foro."}
        code, out, _ = self.add({"candidate_id": "norma", "version": 1, "domain": "RULES",
                                 "class": "LITERAL", "text": "Norma única del foro.",
                                 "scope": "foro", "citations": [citation]})
        self.assertEqual(code, 0, out)

    def test_source_show_needs_a_passage_selector_when_ambiguous(self):
        argv = ["--json", "assimilation", "source", "show", "--workspace", self.ws, "--section",
                "forum_rules", "--source-id", "manual", "--source-version", "1"]
        code, out, _ = run(*argv)
        self.assertEqual(code, 3)
        message = json.loads(out)["message"]
        self.assertIn("2 pasajes", message)
        self.assertIn('--declared-passage "Normas"', message)
        self.assertIn('--declared-passage "Otras"', message)
        for passage in ("Normas", "Otras"):
            code, out, _ = run(*argv, "--declared-passage", passage)
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)["source"]["declared_passage"], passage)
        self.assertEqual(run(*argv, "--without-declared-passage")[0], 3)

    def test_every_rules_section_accepts_rules_and_rejects_world(self):
        for section, heading in RULE_SECTIONS.items():
            if section == "forum_rules":
                source = {"source_id": "manual", "declared_passage": "Normas"}
                quote = "Norma única del foro."
            else:
                source = {"source_id": f"fuente-{section.replace('_', '-')}",
                          "declared_passage": None}
                quote = f"Regla de {heading}."
            citation = dict(source, dossier_section=section, source_version="1", quote=quote)
            with self.subTest(section=section):
                rules = {"candidate_id": f"c-{section.replace('_', '-')}", "version": 1,
                         "domain": "RULES", "class": "LITERAL", "text": quote, "scope": "foro",
                         "citations": [citation]}
                code, out, _ = self.add(rules)
                self.assertEqual(code, 0, out)
                world = dict(rules, candidate_id=f"w-{section.replace('_', '-')}", domain="WORLD")
                code, out, _ = self.add(world)
                self.assertEqual(code, 3, out)

    def test_candidate_list_keeps_the_full_history(self):
        citation = {"dossier_section": "setting", "source_id": "mundo", "source_version": "1",
                    "declared_passage": None, "quote": "Un valle tranquilo."}
        base = {"candidate_id": "valle", "version": 1, "domain": "WORLD", "class": "PROPOSAL",
                "text": "Primera idea.", "scope": "foro", "citations": [citation]}
        self.assertEqual(self.add(base)[0], 0)
        self.assertEqual(self.add(dict(base, version=2, text="Segunda idea."))[0], 0)
        code, out, _ = run("--json", "assimilation", "candidate", "list", "--workspace", self.ws)
        self.assertEqual([(c["candidate_id"], c["version"]) for c in json.loads(out)["candidates"]],
                         [("valle", 1), ("valle", 2)])
        code, out, _ = run("assimilation", "candidate", "list", "--workspace", self.ws)
        self.assertEqual([line.split(" | ")[0] for line in out.splitlines()],
                         ["valle v1", "valle v2"])


class ExactTextTest(CliCase):
    """`candidate show` must show the persisted text exactly (REV4B-01)."""

    TEXTS = {
        "crlf": "uno\r\ndos",
        "trailing-newline": "termina en salto\n",
        "unicode": "Conclusión 🧭 — ñandú",
    }

    def add_texts(self) -> None:
        for name, text in self.TEXTS.items():
            value = dict(CANDIDATES["INTERPRETATION"], candidate_id=name, text=text)
            self.assertEqual(self.add(value)[0], 0)

    def shown_text(self, output: bytes) -> bytes:
        header = "Texto (exacto, hasta «Fin del texto.»):\n".encode("utf-8")
        body = output.split(header, 1)[1]
        return body[: body.rindex(b"Fin del texto.\n")]

    def test_main_shows_exact_text(self):
        self.add_texts()
        for name, text in self.TEXTS.items():
            with self.subTest(name=name):
                code, out, _ = run("assimilation", "candidate", "show", "--workspace", self.ws,
                                   "--candidate-id", name)
                self.assertEqual(code, 0)
                expected = text if text.endswith("\n") else (
                    text + "\n(el texto no termina en salto de línea)\n")
                self.assertEqual(self.shown_text(out.encode("utf-8")), expected.encode("utf-8"))

    def test_subprocess_with_narrow_encoding_shows_exact_bytes(self):
        self.add_texts()
        env = dict(os.environ, PYTHONIOENCODING="ascii:strict")
        for name, text in self.TEXTS.items():
            with self.subTest(name=name):
                result = subprocess.run(
                    [sys.executable, "-B", "-m", "core.runtime.cli", "assimilation", "candidate",
                     "show", "--workspace", self.ws, "--candidate-id", name],
                    cwd=ROOT, capture_output=True, env=env)
                self.assertEqual(result.returncode, 0, result.stderr)
                shown = self.shown_text(result.stdout)
                self.assertTrue(shown.startswith(text.encode("utf-8")))
                self.assertNotIn(b"\r\r\n", result.stdout)
                self.assertNotIn(b"?", shown)


class SubprocessTest(CliCase):
    def test_happy_path_as_module(self):
        def call(*args):
            return subprocess.run([sys.executable, "-B", "-m", "core.runtime.cli", "--json",
                                   "assimilation", *args], cwd=ROOT, capture_output=True,
                                  text=True, encoding="utf-8")
        added = call("candidate", "add", "--workspace", self.ws, "--input",
                     self.input_file(CANDIDATES["UNCERTAINTY"]))
        self.assertEqual(added.returncode, 0, added.stderr)
        self.assertTrue(json.loads(added.stdout)["created"])
        listed = call("candidate", "list", "--workspace", self.ws)
        self.assertEqual(json.loads(listed.stdout)["candidates"][0]["class"], "UNCERTAINTY")


if __name__ == "__main__":
    unittest.main()
