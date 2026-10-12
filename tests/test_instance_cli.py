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

from core.runtime import cli
from core.runtime.instance import InstanceError
from tests.instance_support import ROOT, add, close, decide, open_workspace

LIST_KEYS = {"candidate_id", "candidate_sha256", "class", "decision", "domain",
             "requires_confirmation", "scope", "version"}


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class InstanceCliCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._base = Path(tempfile.mkdtemp())
        workspace = open_workspace(cls._base)
        for candidate_id in ("normas", "mundo", "fichas", "staff", "formato"):
            decide(workspace, candidate_id)
        add(workspace, {"candidate_id": "sin-salto", "version": 1, "domain": "RULES",
                        "class": "INTERPRETATION", "text": "Texto sin salto final",
                        "scope": "fichas", "citations": [
                            {"dossier_section": "forum_rules", "source_id": "manual-foro",
                             "source_version": "1", "declared_passage": "Convivencia",
                             "quote": "respeta el turno"},
                            {"dossier_section": "character_creation", "source_id": "manual-foro",
                             "source_version": "1", "declared_passage": "Fichas",
                             "quote": "historia.\n"}]})
        decide(workspace, "sin-salto")
        add(workspace, {"candidate_id": "duda", "version": 1, "domain": "WORLD",
                        "class": "UNCERTAINTY", "text": "¿Clima?\n", "scope": "foro",
                        "citations": [{"dossier_section": "setting", "source_id": "mundo-base",
                                       "source_version": "2", "declared_passage": None,
                                       "quote": "- Costa norte"}]})
        decide(workspace, "duda")
        close(workspace)
        cls._workspace = workspace

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._base)

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, True)
        self.workspace = self.root / "ws"
        shutil.copytree(self._workspace, self.workspace)
        self.output = self.root / "instancia"

    def init(self, *extra: str):
        return run(*extra, "instance", "init", "--workspace", str(self.workspace), "--output",
                   str(self.output))

    def created(self) -> str:
        self.assertEqual(self.init()[0], 0)
        return str(self.output)


class ParserTest(InstanceCliCase):
    def test_required_arguments(self):
        for argv in (["instance", "init", "--workspace", "x"], ["instance", "init", "--output", "x"],
                     ["instance", "status"], ["instance", "corpus", "list"],
                     ["instance", "corpus", "show", "--instance", "x", "--candidate-id", "a"],
                     ["instance", "corpus", "show", "--instance", "x", "--version", "1"],
                     ["instance", "corpus", "show", "--instance", "x", "--candidate-id", "a",
                      "--version", "0"],
                     ["instance", "corpus", "show", "--instance", "x", "--candidate-id", "a",
                      "--version", "uno"],
                     ["instance", "corpus", "add"], ["instance", "publish"]):
            with self.subTest(argv=argv):
                self.assertEqual(run(*argv)[0], 2)


class InitStatusTest(InstanceCliCase):
    def test_init_text_and_retry(self):
        code, out, _ = self.init()
        self.assertEqual(code, 0)
        self.assertRegex(out, r"^Instancia creada para el foro «foro-neutral» en .+ "
                              r"\(snapshot sha256=[0-9a-f]{64}\)\.\n$")
        code, out, _ = self.init()
        self.assertRegex(out, r"^La instancia del foro «foro-neutral» ya existía con el mismo "
                              r"contenido: .+ \(snapshot sha256=[0-9a-f]{64}\)\.\n$")

    def test_init_json(self):
        code, out, _ = self.init("--json")
        payload = json.loads(out)
        self.assertEqual(set(payload), {"ok", "action", "created", "forum_id", "instance",
                                        "snapshot_sha256"})
        self.assertEqual((payload["action"], payload["created"]), ("instance.init", True))
        self.assertEqual(payload["instance"], str(self.output))

    def test_status_without_workspace(self):
        instance = self.created()
        shutil.rmtree(self.workspace)
        code, out, _ = run("--json", "instance", "status", "--instance", instance)
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(set(payload), {"ok", "action", "corpus_revision", "forum_id", "instance",
                                        "integrity", "snapshot_sha256"})
        self.assertEqual(payload["integrity"], "OK")
        code, out, _ = run("instance", "status", "--instance", instance)
        self.assertRegex(out, r"^Instancia íntegra del foro «foro-neutral» en .+ \(revisión del "
                              r"corpus \d+; snapshot sha256=[0-9a-f]{64}\)\.\n$")

    def test_error_codes(self):
        code, out, _ = run("--json", "instance", "status", "--instance", str(self.root / "no"))
        self.assertEqual(code, 3)
        self.assertEqual(set(json.loads(out)), {"ok", "code", "message"})
        (self.root / "ocupada").mkdir()
        (self.root / "ocupada" / "x").write_bytes(b"x")
        code, out, _ = run("--json", "instance", "init", "--workspace", str(self.workspace),
                           "--output", str(self.root / "ocupada"))
        self.assertEqual((code, json.loads(out)["code"]), (4, "CONFLICT"))
        code, out, _ = run("--json", "instance", "init", "--workspace", str(self.workspace),
                           "--output", str(ROOT / "tests" / "no-crear-aqui"))
        self.assertEqual((code, json.loads(out)["code"]), (4, "UNSAFE_DESTINATION"))
        with mock.patch.object(cli, "create_instance", side_effect=InstanceError("IO", "disco")):
            code, out, _ = self.init("--json")
        self.assertEqual(json.loads(out), {"ok": False, "code": "IO", "message": "disco"})
        self.assertEqual(code, 5)


class ExactOutputTest(InstanceCliCase):
    """REV4C2-04: complete outputs, byte for byte, for every instance command."""

    def setUp(self):
        super().setUp()
        from core.runtime.instance import approved_corpus, load_instance
        self.assertEqual(self.init()[0], 0)
        self.loaded = load_instance(self.output)
        self.entries = {e.candidate.candidate_id: e for e in approved_corpus(self.loaded)}
        self.snapshot = self.loaded.config.corpus.snapshot_sha256
        self.path = str(self.output)

    def emitted(self, payload: dict) -> str:
        return json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n"

    def test_init_and_status(self):
        self.assertEqual(self.init(), (0, "La instancia del foro «foro-neutral» ya existía con el "
                                          f"mismo contenido: {self.path} (snapshot sha256="
                                          f"{self.snapshot}).\n", ""))
        self.assertEqual(self.init("--json")[1], self.emitted(
            {"ok": True, "action": "instance.init", "created": False, "forum_id": "foro-neutral",
             "instance": self.path, "snapshot_sha256": self.snapshot}))
        revision = self.loaded.corpus_revision
        self.assertEqual(run("instance", "status", "--instance", self.path)[1],
                         f"Instancia íntegra del foro «foro-neutral» en {self.path} (revisión del "
                         f"corpus {revision}; snapshot sha256={self.snapshot}).\n")
        self.assertEqual(run("--json", "instance", "status", "--instance", self.path)[1],
                         self.emitted({"ok": True, "action": "instance.status",
                                       "corpus_revision": revision, "forum_id": "foro-neutral",
                                       "instance": self.path, "integrity": "OK",
                                       "snapshot_sha256": self.snapshot}))

    def test_list(self):
        def line(entry):
            c = entry.candidate
            text = (f"{c.candidate_id} v{c.version} | {c.candidate_class.value} | "
                    f"{c.domain.value} | APPROVED | scope={json.dumps(c.scope, ensure_ascii=False)}"
                    f" | sha256={c.candidate_sha256}")
            return text + (" | REQUIERE CONFIRMACIÓN" if c.requires_confirmation else "")

        expected = "".join(line(e) + "\n" for e in self.entries.values())
        self.assertEqual(run("instance", "corpus", "list", "--instance", self.path)[1], expected)
        summaries = [{"candidate_id": e.candidate.candidate_id,
                      "candidate_sha256": e.candidate.candidate_sha256,
                      "class": e.candidate.candidate_class.value, "decision": "APPROVED",
                      "domain": e.candidate.domain.value,
                      "requires_confirmation": e.candidate.requires_confirmation,
                      "scope": e.candidate.scope, "version": e.candidate.version}
                     for e in self.entries.values()]
        self.assertEqual(run("--json", "instance", "corpus", "list", "--instance", self.path)[1],
                         self.emitted({"ok": True, "action": "instance.corpus.list",
                                       "candidates": summaries,
                                       "corpus_revision": self.loaded.corpus_revision,
                                       "instance": self.path, "snapshot_sha256": self.snapshot}))

    def test_show_text(self):
        entry = self.entries["sin-salto"]
        c, d = entry.candidate, entry.decision
        cites = c.citations
        expected = (
            f"sin-salto v1 | INTERPRETATION | RULES | APPROVED | scope=\"fichas\" | "
            f"sha256={c.candidate_sha256}\n"
            f"Decisión: APPROVED (evidencia={d.evidence.sha256}).\n"
            f"Cita 1: forum_rules | manual-foro | v1 | pasaje=Convivencia | "
            f"sha256={cites[0].source_sha256} | caracteres {cites[0].start}-{cites[0].end}\n"
            "Cita 1 (exacta, hasta «Fin de la cita 1.»):\nrespeta el turno\nFin de la cita 1.\n"
            f"Cita 2: character_creation | manual-foro | v1 | pasaje=Fichas | "
            f"sha256={cites[1].source_sha256} | caracteres {cites[1].start}-{cites[1].end}\n"
            "Cita 2 (exacta, hasta «Fin de la cita 2.»):\nhistoria.\nFin de la cita 2.\n"
            "Texto (exacto, hasta «Fin del texto.»):\nTexto sin salto final\nFin del texto.\n")
        self.assertEqual(run("instance", "corpus", "show", "--instance", self.path,
                             "--candidate-id", "sin-salto", "--version", "1"), (0, expected, ""))

    def test_show_json(self):
        from core.runtime.cli import _candidate_record, _decision_summary
        entry = self.entries["duda"]
        self.assertEqual(
            run("--json", "instance", "corpus", "show", "--instance", self.path, "--candidate-id",
                "duda", "--version", "1")[1],
            self.emitted({"ok": True, "action": "instance.corpus.show",
                          "candidate": _candidate_record(entry.candidate, include_hash=True),
                          "corpus_revision": self.loaded.corpus_revision,
                          "decision": _decision_summary(entry.decision),
                          "effective_review_status": "APPROVED", "instance": self.path,
                          "snapshot_sha256": self.snapshot}))


class CorpusTest(InstanceCliCase):
    def setUp(self):
        super().setUp()
        self.instance = self.created()

    def test_list_text_and_json(self):
        code, out, _ = run("instance", "corpus", "list", "--instance", self.instance)
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertEqual([line.split(" ")[0] for line in lines],
                         ["normas", "mundo", "fichas", "staff", "formato", "sin-salto", "duda"])
        self.assertRegex(lines[0], r'^normas v1 \| LITERAL \| RULES \| APPROVED \| scope="foro" '
                                   r'\| sha256=[0-9a-f]{64}$')
        self.assertTrue(lines[-1].endswith(" | REQUIERE CONFIRMACIÓN"))
        code, out, _ = run("--json", "instance", "corpus", "list", "--instance", self.instance)
        payload = json.loads(out)
        self.assertEqual(set(payload), {"ok", "action", "candidates", "corpus_revision",
                                        "instance", "snapshot_sha256"})
        self.assertTrue(all(set(c) == LIST_KEYS and c["decision"] == "APPROVED"
                            for c in payload["candidates"]))
        self.assertTrue(payload["candidates"][-1]["requires_confirmation"])

    def test_show_text_exact_blocks(self):
        code, out, _ = run("instance", "corpus", "show", "--instance", self.instance,
                           "--candidate-id", "sin-salto", "--version", "1")
        self.assertEqual(code, 0)
        lines = out.split("\n")
        self.assertTrue(lines[0].startswith("sin-salto v1 | INTERPRETATION | RULES | APPROVED | "
                                            'scope="fichas"'))
        self.assertRegex(lines[1], r"^Decisión: APPROVED \(evidencia=[0-9a-f]{64}\)\.$")
        self.assertIn("Cita 1 (exacta, hasta «Fin de la cita 1.»):\nrespeta el turno\n"
                      "Fin de la cita 1.\n", out)
        self.assertIn("Cita 2 (exacta, hasta «Fin de la cita 2.»):\nhistoria.\n"
                      "Fin de la cita 2.\n", out)
        self.assertTrue(out.endswith("Texto (exacto, hasta «Fin del texto.»):\n"
                                     "Texto sin salto final\nFin del texto.\n"))
        self.assertRegex(out, r"Cita 2: character_creation \| manual-foro \| v1 \| pasaje=Fichas "
                              r"\| sha256=[0-9a-f]{64} \| caracteres \d+-\d+\n")

    def test_show_json(self):
        code, out, _ = run("--json", "instance", "corpus", "show", "--instance", self.instance,
                           "--candidate-id", "duda", "--version", "1")
        payload = json.loads(out)
        self.assertEqual(set(payload), {"ok", "action", "candidate", "corpus_revision", "decision",
                                        "effective_review_status", "instance", "snapshot_sha256"})
        self.assertEqual(payload["effective_review_status"], "APPROVED")
        self.assertEqual(payload["candidate"]["text"], "¿Clima?\n")
        self.assertEqual(payload["decision"]["decision_id"], "candidate:duda:v1")

    def test_show_rejects_unknown_or_other_versions(self):
        for candidate_id, version in (("normas", "2"), ("nada", "1")):
            with self.subTest(candidate=candidate_id):
                code, out, _ = run("--json", "instance", "corpus", "show", "--instance",
                                   self.instance, "--candidate-id", candidate_id, "--version",
                                   version)
                self.assertEqual((code, json.loads(out)["code"]), (3, "INVALID_STATE"))

    def test_redirected_stdout_works_without_tty(self):
        result = subprocess.run([sys.executable, "-B", "-m", "core.runtime.cli", "instance",
                                 "corpus", "list", "--instance", self.instance], cwd=ROOT,
                                capture_output=True, stdin=subprocess.DEVNULL)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("REQUIERE CONFIRMACIÓN".encode(), result.stdout)
        self.assertNotIn(b"\r\n", result.stdout)


if __name__ == "__main__":
    unittest.main()
