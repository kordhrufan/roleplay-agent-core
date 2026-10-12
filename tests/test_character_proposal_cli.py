import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core.character.models import composition_record, decision_record, proposal_record
from core.runtime import cli
from core.runtime.character import get_proposal, import_concept, list_proposals
from core.runtime.instance import create_instance, load_instance
from tests.instance_support import ROOT, closed_workspace
from tests.test_assimilation_decisions import FakeTerminal
from tests.test_character_cli import run

DECISION_JSON_MESSAGE = ("las decisiones humanas sobre propuestas no admiten --json: ejecuta el "
                         "comando en tu terminal y responde a la confirmación")


class ProposalCliCase(unittest.TestCase):
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
        self.path = str(self.instance)
        self.import_concept(1, "# Aria\nExploradora curiosa.\n")

    def import_concept(self, version, text):
        source = self.root / f"concepto-{version}.md"
        source.write_bytes(text.encode("utf-8"))
        import_concept(self.instance, expected_core_root=ROOT, character_id="aria",
                       version=version, input_path=source, terminal=FakeTerminal())

    def loaded(self):
        return load_instance(self.instance, expected_core_root=ROOT)

    def character(self):
        return self.loaded().characters[0]

    def effective(self):
        return self.character().state.replay.effective

    def write_input(self, proposal_id="ajuste", version=1, base=None, text="Texto propuesto\n",
                    citations=(("normas", 3),), name="propuesta.json", raw=None) -> str:
        path = self.root / name
        if raw is None:
            raw = json.dumps({
                "proposal_id": proposal_id, "version": version,
                "base_composition_sha256": base or self.effective().composition_sha256,
                "text": text, "rationale": "Motivo con «citas».",
                "citations": [{"candidate_id": c, "version": v} for c, v in citations],
            }, ensure_ascii=False).encode("utf-8")
        path.write_bytes(raw)
        return str(path)

    def add(self, *flags, **kwargs):
        return run(*flags, "character", "proposal", "add", "--instance", self.path,
                   "--character-id", "aria", "--input", self.write_input(**kwargs))

    def decide(self, action, proposal_id="ajuste", version="1", *flags):
        with mock.patch.object(cli, "_SystemTerminal", FakeTerminal):
            return run(*flags, "character", "proposal", action, "--instance", self.path,
                       "--character-id", "aria", "--proposal-id", proposal_id,
                       "--version", version)

    def view(self, proposal_id="ajuste", version=1):
        return get_proposal(self.loaded(), character_id="aria", proposal_id=proposal_id,
                            version=version)

    def line(self, view):
        p = view.proposal
        return (f"{p.proposal_id} v{p.version} | {view.status.value} | "
                f"concepto=v{p.concept.version}:{p.concept.concept_sha256} | "
                f"base={p.base_composition_sha256} | resultado={p.result_composition_sha256} | "
                f"sha256={p.proposal_sha256} | citas={len(p.citations)} | "
                f"aplicada={'SÍ' if view.applied_to_effective else 'NO'}")

    def summary(self, view):
        p = view.proposal
        return {"applied_to_effective": view.applied_to_effective,
                "base_composition_sha256": p.base_composition_sha256,
                "citation_count": len(p.citations), "concept": p.concept.as_json(),
                "decision": None if view.decision is None else view.decision.review_status.value,
                "proposal_id": p.proposal_id, "proposal_sha256": p.proposal_sha256,
                "result_composition_sha256": p.result_composition_sha256,
                "status": view.status.value, "version": p.version}


class ParserTest(ProposalCliCase):
    def test_every_argument_is_required(self):
        full = {
            ("effective", "show"): ["--instance", "x", "--character-id", "a"],
            ("proposal", "add"): ["--instance", "x", "--character-id", "a", "--input", "x"],
            ("proposal", "list"): ["--instance", "x", "--character-id", "a"],
        }
        for action in ("show", "approve", "reject"):
            full[("proposal", action)] = ["--instance", "x", "--character-id", "a",
                                          "--proposal-id", "p", "--version", "1"]
        for (group, action), args in full.items():
            for index in range(0, len(args), 2):
                argv = ["character", group, action, *args[:index], *args[index + 2:]]
                with self.subTest(argv=argv):
                    self.assertEqual(run(*argv)[0], 2)
        for extra in (["--version", "0"], ["--version", "x"], ["--yes"], ["--force"],
                      ["--nonce", "ABCDEFGH"]):
            argv = ["character", "proposal", "approve", "--instance", "x", "--character-id", "a",
                    "--proposal-id", "p", "--version", "1", *extra]
            with self.subTest(argv=argv):
                self.assertEqual(run(*argv)[0], 2)


class QueryCliTest(ProposalCliCase):
    def test_effective_show_root_text_and_json(self):
        effective = self.effective()
        code, out, _ = run("character", "effective", "show", "--instance", self.path,
                           "--character-id", "aria")
        self.assertEqual((code, out), (0, (
            f"Composición efectiva: aria | concepto=v1:{effective.concept.concept_sha256} | "
            f"sha256={effective.composition_sha256} | pasos=0 | bytes={effective.utf8_size}\n"
            "Texto efectivo (exacto, hasta «Fin de la composición efectiva.»):\n"
            "# Aria\nExploradora curiosa.\n"
            "Fin de la composición efectiva.\n")))
        code, out, _ = run("--json", "character", "effective", "show", "--instance", self.path,
                           "--character-id", "aria")
        self.assertEqual(json.loads(out), {
            "ok": True, "action": "character.effective.show", "character_id": "aria",
            "composition": {"applied_proposals": [],
                            "composition_sha256": effective.composition_sha256,
                            "concept": effective.concept.as_json(),
                            "text": "# Aria\nExploradora curiosa.\n",
                            "utf8_size": effective.utf8_size},
            "instance": str(self.instance), "state_revision": 1})
        self.assertTrue(out.isascii())

    def test_add_text_and_json_with_retry(self):
        code, out, _ = self.add()
        view = self.view()
        self.assertEqual((code, out), (0, f"Propuesta añadida: {self.line(view)}\n"
                                          "Revisión del personaje: 2.\n"))
        base = view.proposal.base_composition_sha256
        code, out, _ = self.add("--json", base=base)
        self.assertEqual(json.loads(out), {
            "ok": True, "action": "character.proposal.add", "character_id": "aria",
            "created": False, "instance": str(self.instance), "proposal": self.summary(view),
            "state_revision": 2})
        code, out, _ = self.add(base=base)
        self.assertEqual(out, f"Propuesta ya existente: {self.line(view)}\n"
                              "Revisión del personaje: 2.\n")

    def test_list_four_states_text_and_json(self):
        code, out, _ = run("character", "proposal", "list", "--instance", self.path,
                           "--character-id", "aria")
        self.assertEqual((code, out), (0, "No hay propuestas para «aria».\n"))
        code, out, _ = run("--json", "character", "proposal", "list", "--instance", self.path,
                           "--character-id", "aria")
        self.assertEqual(json.loads(out)["proposals"], [])
        self.add(proposal_id="aprobada", name="a.json")
        self.add(proposal_id="rechazada", text="Otra\n", name="b.json")
        self.add(proposal_id="obsoleta", text="Tercera\n", name="c.json")
        self.assertEqual(self.decide("reject", "rechazada")[0], 0)
        self.assertEqual(self.decide("approve", "aprobada")[0], 0)
        self.add(proposal_id="pendiente", text="Cuarta\n", name="d.json")
        views = list_proposals(self.loaded(), character_id="aria")
        self.assertEqual([v.status.value for v in views],
                         ["APPROVED", "REJECTED", "OBSOLETE", "PENDING"])
        code, out, _ = run("character", "proposal", "list", "--instance", self.path,
                           "--character-id", "aria")
        self.assertEqual(out, "".join(self.line(v) + "\n" for v in views))
        self.assertIn("aplicada=SÍ", out.splitlines()[0])
        code, out, _ = run("--json", "character", "proposal", "list", "--instance", self.path,
                           "--character-id", "aria")
        self.assertEqual(json.loads(out), {
            "ok": True, "action": "character.proposal.list", "character_id": "aria",
            "instance": str(self.instance), "proposals": [self.summary(v) for v in views],
            "state_revision": 7})

    def test_show_text_and_json(self):
        self.add(text="Línea «ñ» sin salto final", citations=(("normas", 3), ("duda", 1)))
        normas, duda = (next(c for c in self.loaded().candidates if c.key == key)
                        for key in (("normas", 3), ("duda", 1)))
        view = self.view()
        expected_body = (
            "Citas aprobadas (2):\n"
            f"Cita 1: normas v3 | LITERAL | RULES | APPROVED | sha256={normas.candidate_sha256}\n"
            f"Cita 2: duda v1 | UNCERTAINTY | WORLD | APPROVED | sha256={duda.candidate_sha256}"
            " | REQUIERE CONFIRMACIÓN\n"
            "Motivo exacto (hasta «Fin del motivo.»):\n"
            "Motivo con «citas».\n"
            "Fin del motivo.\n"
            "BASE CITADA — texto exacto (hasta «Fin de la base.»):\n"
            "# Aria\nExploradora curiosa.\n"
            "Fin de la base.\n"
            "PROPUESTA — texto completo que se aprueba/rechaza (hasta «Fin de la propuesta.»):\n"
            "Línea «ñ» sin salto final\n"
            "Fin de la propuesta.\n")
        argv = ("character", "proposal", "show", "--instance", self.path, "--character-id",
                "aria", "--proposal-id", "ajuste", "--version", "1")
        code, out, _ = run(*argv)
        self.assertEqual((code, out), (0, f"{self.line(view)}\n"
                                          "Decisión: ninguna (estado PENDING).\n"
                                          + expected_body))
        code, out, _ = run("--json", *argv)
        self.assertEqual(json.loads(out), {
            "ok": True, "action": "character.proposal.show", "applied_to_effective": False,
            "base": composition_record(view.base), "character_id": "aria", "decision": None,
            "instance": str(self.instance), "proposal": proposal_record(view.proposal),
            "status": "PENDING", "state_revision": 2})
        self.decide("approve")
        approved = self.view()
        code, out, _ = run(*argv)
        self.assertEqual(out, f"{self.line(approved)}\n"
                              f"Decisión: APPROVED (evidencia={approved.decision.evidence.sha256})."
                              "\n" + expected_body)
        code, out, _ = run("--json", *argv)
        payload = json.loads(out)
        self.assertEqual((payload["decision"], payload["status"], payload["applied_to_effective"]),
                         (decision_record(approved.decision), "APPROVED", True))

    def test_unknown_targets_and_input_errors(self):
        self.add()
        cases = [
            (3, ("character", "proposal", "list", "--instance", self.path, "--character-id",
                 "nadie")),
            (3, ("character", "effective", "show", "--instance", self.path, "--character-id",
                 "nadie")),
            (3, ("character", "proposal", "show", "--instance", self.path, "--character-id",
                 "aria", "--proposal-id", "nada", "--version", "1")),
            (3, ("character", "proposal", "show", "--instance", self.path, "--character-id",
                 "aria", "--proposal-id", "ajuste", "--version", "2")),
            (3, ("character", "proposal", "add", "--instance", self.path, "--character-id",
                 "aria", "--input", self.write_input(raw=b'{"proposal_id": "a", "proposal_id": '
                                                         b'"b"}', name="dup.json"))),
            (3, ("character", "proposal", "add", "--instance", self.path, "--character-id",
                 "aria", "--input", self.write_input(raw=b"\xef\xbb\xbf{}", name="bom.json"))),
            (3, ("character", "proposal", "add", "--instance", self.path, "--character-id",
                 "aria", "--input", self.write_input(citations=(("idea", 1),), name="r.json",
                                                     proposal_id="otra"))),
            (4, ("character", "proposal", "add", "--instance", self.path, "--character-id",
                 "aria", "--input", self.write_input(base="0" * 64, name="s.json",
                                                     proposal_id="otra"))),
            (4, ("character", "proposal", "add", "--instance", self.path, "--character-id",
                 "aria", "--input", self.write_input(version=3, name="v.json"))),
            (5, ("character", "proposal", "add", "--instance", self.path, "--character-id",
                 "aria", "--input", str(self.root / "no-existe.json"))),
        ]
        before = self.character().state_revision
        for expected, argv in cases:
            with self.subTest(argv=argv[2:]):
                code, out, err = run(*argv)
                self.assertEqual((code, out), (expected, ""))
                self.assertTrue(err.startswith("Error ("))
                code, out, _ = run("--json", *argv)
                payload = json.loads(out)
                self.assertEqual((code, payload["ok"], set(payload)),
                                 (expected, False, {"ok", "code", "message"}))
        self.assertEqual(self.character().state_revision, before)


class DecisionCliTest(ProposalCliCase):
    def test_json_is_rejected_before_any_prompt(self):
        self.add()
        before = self.character().state_revision
        for action in ("approve", "reject"):
            with self.subTest(action=action):
                code, out, _ = self.decide(action, "ajuste", "1", "--json")
                self.assertEqual((code, json.loads(out)), (3, {
                    "ok": False, "code": "INVALID_STATE", "message": DECISION_JSON_MESSAGE}))
        self.assertEqual(self.character().state_revision, before)

    def test_non_interactive_stdin_or_subprocess_cannot_decide(self):
        self.add()
        before = self.character().state_revision
        argv = ["character", "proposal", "approve", "--instance", self.path, "--character-id",
                "aria", "--proposal-id", "ajuste", "--version", "1"]
        code, out, err = run(*argv, stdin="APROBAR-PROPUESTA ajuste v1 ABCDEFGH\n")
        self.assertEqual((code, out), (3, ""))
        self.assertIn("terminal interactiva", err)
        result = subprocess.run([sys.executable, "-B", "-m", "core.runtime.cli", *argv],
                                cwd=ROOT, capture_output=True, stdin=subprocess.DEVNULL)
        self.assertEqual(result.returncode, 3)
        self.assertNotIn(b"APROBAR-PROPUESTA", result.stdout)
        self.assertEqual(self.character().state_revision, before)

    def test_approve_reject_and_retry_outputs(self):
        self.add(proposal_id="a", name="a.json")
        self.add(proposal_id="b", text="Otra\n", name="b.json")
        code, out, _ = self.decide("approve", "a")
        view = self.view("a")
        effective = self.effective()
        self.assertEqual((code, out), (0, f"Propuesta aprobada: a v1 | "
                                          f"sha256={view.proposal.proposal_sha256}\n"
                                          f"Composición efectiva: {effective.composition_sha256}.\n"
                                          "Revisión del personaje: 4.\n"))
        code, out, _ = self.decide("approve", "a")
        self.assertEqual(out.splitlines()[0], f"Propuesta ya aprobada: a v1 | "
                                              f"sha256={view.proposal.proposal_sha256}")
        self.assertEqual(self.view("b").status.value, "OBSOLETE")
        self.assertEqual(self.decide("approve", "b")[0], 4)
        code, out, _ = self.decide("reject", "b")
        self.assertEqual(out.splitlines()[0], f"Propuesta rechazada: b v1 | "
                                              f"sha256={self.view('b').proposal.proposal_sha256}")
        self.assertEqual(out.splitlines()[1], f"Composición efectiva: "
                                              f"{effective.composition_sha256}.")
        self.assertEqual(self.decide("approve", "a")[0], 0)
        self.assertEqual(self.decide("reject", "a")[0], 4)
        code, out, _ = run("character", "effective", "show", "--instance", self.path,
                           "--character-id", "aria")
        self.assertIn("Paso 1: a v1 | propuesta=", out)
        self.assertIn(f"evidencia={view.decision.evidence.sha256}\n", out)
        self.assertIn("pasos=1 |", out)

    def test_new_concept_resets_effective_and_keeps_history(self):
        self.add()
        self.decide("approve")
        self.import_concept(2, "# Aria\nOtra base.\n")
        code, out, _ = run("--json", "character", "effective", "show", "--instance", self.path,
                           "--character-id", "aria")
        composition = json.loads(out)["composition"]
        self.assertEqual((composition["text"], composition["applied_proposals"],
                          composition["concept"]["version"]), ("# Aria\nOtra base.\n", [], 2))
        code, out, _ = run("character", "proposal", "list", "--instance", self.path,
                           "--character-id", "aria")
        self.assertIn("| APPROVED |", out)
        self.assertIn("aplicada=NO", out)


if __name__ == "__main__":
    unittest.main()
