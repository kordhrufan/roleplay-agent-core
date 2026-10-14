import json
import subprocess
import sys
import unittest
from unittest import mock

from core.runtime import cli
from tests.instance_support import ROOT
from tests.test_assimilation_decisions import FakeTerminal
from tests.test_character_cli import run
from tests.test_corpus_expansion import ExpansionCase, new_candidate, successor_dossier


class ExpansionCliCase(ExpansionCase):
    def cli_extend(self, *flags, dossier=None, workspace=None):
        return run(*flags, "assimilation", "extend", "--instance", str(self.instance),
                   "--dossier", str(dossier or self.successor),
                   "--workspace", str(workspace or self.workspace))

    def ws(self, *argv):
        return run(*argv, "--workspace", str(self.workspace))


class ParserTest(ExpansionCliCase):
    def test_extend_requires_every_argument(self):
        full = ["--instance", "x", "--dossier", "y", "--workspace", "z"]
        for index in range(0, len(full), 2):
            argv = ["assimilation", "extend", *full[:index], *full[index + 2:]]
            with self.subTest(argv=argv):
                self.assertEqual(run(*argv)[0], 2)
        for name in ("reopen", "supersede", "retire"):
            self.assertEqual(run("assimilation", name, "--workspace", "x")[0], 2)


class ExtendCliTest(ExpansionCliCase):
    def test_extend_text_and_json(self):
        code, out, _ = self.cli_extend()
        context = self.loaded().expansion
        parent = context.base.current.snapshot_sha256
        detail = f"(snapshot base={parent}; expediente 2026-10-11 -> 2026-10-14)"
        self.assertEqual((code, out), (0, f"Workspace de ampliación creado para «foro-neutral» "
                                          f"en {self.workspace} {detail}.\n"))
        code, out, _ = self.cli_extend()
        self.assertEqual(out, f"El workspace de ampliación de «foro-neutral» ya existía con el "
                              f"mismo contenido: {self.workspace} {detail}.\n")
        code, out, _ = self.cli_extend("--json")
        self.assertEqual(json.loads(out), {
            "ok": True, "action": "assimilation.extend", "base_snapshot_sha256": parent,
            "created": False, "dossier_version": "2026-10-14", "forum_id": "foro-neutral",
            "previous_dossier_version": "2026-10-11", "workspace": str(self.workspace)})

    def test_status_and_sources(self):
        self.cli_extend()
        context = self.loaded().expansion
        base = self.loaded().corpus_revision
        code, out, _ = self.ws("assimilation", "status")
        self.assertEqual(out, (
            f"Workspace de ampliación íntegro del foro «foro-neutral» en {self.workspace} "
            f"(ronda 2; snapshot base={context.base.current.snapshot_sha256}; revisión del corpus "
            f"{base}; expediente 2026-10-11 -> 2026-10-14; estado ABIERTO).\n"))
        code, out, _ = self.ws("--json", "assimilation", "status")
        self.assertEqual(json.loads(out), {
            "ok": True, "action": "assimilation.status",
            "base_snapshot_sha256": context.base.current.snapshot_sha256,
            "corpus_revision": base, "dossier_version": "2026-10-14",
            "forum_id": "foro-neutral", "integrity": "OK",
            "previous_dossier_version": "2026-10-11", "round": 2, "round_state": "OPEN",
            "workspace": str(self.workspace)})
        code, out, _ = self.ws("assimilation", "source", "list")
        lines = out.splitlines()
        self.assertEqual([line for line in lines if line.endswith(" | NUEVA")],
                         [line for line in lines if "| razas |" in line])
        self.assertEqual(len([line for line in lines if line.endswith(" | NUEVA")]), 1)
        code, out, _ = self.ws("--json", "assimilation", "source", "list")
        sources = json.loads(out)["sources"]
        self.assertEqual([s["source_id"] for s in sources if s["new_in_expansion"]], ["razas"])

    def test_round_through_the_cli(self):
        self.cli_extend()
        path = self.root / "c.json"
        path.write_text(json.dumps(new_candidate(), ensure_ascii=False), encoding="utf-8")
        code, out, _ = self.ws("--json", "assimilation", "candidate", "add", "--input",
                               str(path))
        self.assertEqual((code, json.loads(out)["created"]), (0, True))
        closed = self.root / "closed.json"
        closed.write_text(json.dumps(new_candidate("normas"), ensure_ascii=False),
                          encoding="utf-8")
        code, out, _ = self.ws("--json", "assimilation", "candidate", "add", "--input",
                               str(closed))
        self.assertEqual((code, json.loads(out)["code"]), (4, "CONFLICT"))
        code, out, _ = self.ws("--json", "assimilation", "candidate", "list")
        self.assertEqual([c["candidate_id"] for c in json.loads(out)["candidates"]], ["hielo"])
        argv = ("assimilation", "candidate", "approve", "--candidate-id", "hielo", "--version",
                "1")
        with mock.patch.object(cli, "_SystemTerminal", FakeTerminal):
            self.assertEqual(self.ws(*argv)[0], 0)
            code, out, _ = self.ws("--json", "assimilation", "close")
            self.assertEqual((code, json.loads(out)["code"]), (3, "INVALID_STATE"))
            code, out, _ = self.ws("assimilation", "close")
        loaded = self.loaded()
        snapshot = loaded.closure
        tail = (f"foro-neutral | ronda 2 | snapshot padre {snapshot.parent_snapshot_sha256} | "
                f"snapshot sha256={snapshot.snapshot_sha256}\n"
                f"Revisión del corpus: {loaded.corpus_revision}.\n")
        self.assertEqual((code, out), (0, "Ampliación cerrada: " + tail))
        with mock.patch.object(cli, "_SystemTerminal", FakeTerminal):
            code, out, _ = self.ws("assimilation", "close")
        self.assertEqual(out, "Ampliación ya cerrada: " + tail)
        code, out, _ = self.ws("--json", "assimilation", "status")
        self.assertEqual(json.loads(out)["round_state"], "CLOSED")

    def test_human_steps_need_a_terminal(self):
        self.cli_extend()
        self.add(new_candidate())
        self.decide()
        argv = ["assimilation", "close", "--workspace", str(self.workspace)]
        code, out, err = run(*argv, stdin="CERRAR-AMPLIACION foro-neutral r2 c1 ABCDEFGH\n")
        self.assertEqual((code, out), (3, ""))
        result = subprocess.run([sys.executable, "-B", "-m", "core.runtime.cli", *argv],
                                cwd=ROOT, capture_output=True, stdin=subprocess.DEVNULL)
        self.assertEqual(result.returncode, 3)
        self.assertNotIn(b"CERRAR-AMPLIACION", result.stdout)
        self.assertIsNone(self.loaded().closure)

    def test_error_codes(self):
        same = successor_dossier(self.root, "same", version="2026-10-11")
        cases = [
            (4, dict(dossier=same, workspace=self.root / "w1")),
            (4, dict(workspace=self.instance / "dentro")),
        ]
        for expected, kwargs in cases:
            with self.subTest(kwargs=sorted(kwargs)):
                code, out, err = self.cli_extend(**kwargs)
                self.assertEqual((code, out), (expected, ""))
                code, out, _ = self.cli_extend("--json", **kwargs)
                self.assertEqual((code, set(json.loads(out))),
                                 (expected, {"ok", "code", "message"}))
        code, out, _ = run("--json", "assimilation", "extend", "--instance",
                           str(self.root / "no-existe"), "--dossier", str(self.successor),
                           "--workspace", str(self.root / "w3"))
        self.assertEqual(code, 3)


if __name__ == "__main__":
    unittest.main()
