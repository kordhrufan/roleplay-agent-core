import json
import subprocess
import sys
import unittest
from unittest import mock

from core.character.models import draft_summary, draft_view_record, staff_response_record
from core.runtime import cli
from core.runtime.character import list_drafts
from tests.instance_support import ROOT
from tests.test_assimilation_decisions import FakeTerminal
from tests.test_character_cli import run
from tests.test_character_draft import LOCATOR, DraftCase

STAFF_JSON_MESSAGE = ("las respuestas de staff transcritas no admiten --json: ejecuta el comando "
                      "en tu terminal y responde a la confirmación")


class StaffCliCase(DraftCase):
    def setUp(self):
        super().setUp()
        self.path = str(self.instance)

    def cli_create(self, *flags, version="1", composition=None, text="# Ficha\nNombre: Aria\n",
                   name="ficha.md"):
        return run(*flags, "character", "draft", "create", "--instance", self.path,
                   "--character-id", "aria", "--version", version, "--composition-sha256",
                   composition or self.effective().composition_sha256,
                   "--input", str(self.write_sheet(text, name)))

    def cli_record(self, *flags, status="APPROVED", version="1", input_path=None, **kwargs):
        with mock.patch.object(cli, "_SystemTerminal", FakeTerminal):
            return run(*flags, "character", "staff", "record", "--instance", self.path,
                       "--character-id", "aria", "--version", version, "--status", status,
                       "--input", str(input_path or self.write_response(version=int(version),
                                                                        **kwargs)))

    def line(self, view):
        record, effective = view.record, view.effective
        return (f"character-sheet v{view.version} | {effective.lifecycle.value} | "
                f"{'CURRENT' if view.current else 'SUPERSEDED'} | "
                f"{effective.review_status.value} | NOT_CONFIRMED | "
                f"composición={record.composition_sha256} | sha256={record.draft_sha256} | "
                f"bytes={record.utf8_size} | corpus={len(record.corpus_refs)}")


class ParserTest(StaffCliCase):
    def test_every_argument_is_required_and_there_is_no_publication(self):
        full = {
            ("draft", "create"): ["--instance", "x", "--character-id", "a", "--version", "1",
                                  "--composition-sha256", "h", "--input", "x"],
            ("draft", "list"): ["--instance", "x", "--character-id", "a"],
            ("draft", "show"): ["--instance", "x", "--character-id", "a", "--version", "1"],
            ("staff", "record"): ["--instance", "x", "--character-id", "a", "--version", "1",
                                  "--status", "APPROVED", "--input", "x"],
        }
        for (group, action), args in full.items():
            for index in range(0, len(args), 2):
                argv = ["character", group, action, *args[:index], *args[index + 2:]]
                with self.subTest(argv=argv):
                    self.assertEqual(run(*argv)[0], 2)
        record = ["character", "staff", "record", *full[("staff", "record")]]
        for argv in ([*record[:-4], "--status", "PENDING_HUMAN_REVIEW", "--input", "x"],
                     [*record[:-4], "--status", "approved", "--input", "x"],
                     ["character", "draft", "show", "--instance", "x", "--character-id", "a",
                      "--version", "0"],
                     [*record, "--yes"],
                     ["character", "draft", "publish"], ["character", "draft", "export"],
                     ["character", "staff", "confirm-publication"], ["character", "publish"]):
            with self.subTest(argv=argv):
                self.assertEqual(run(*argv)[0], 2)


class DraftCliTest(StaffCliCase):
    def test_create_text_and_json_with_copy_block(self):
        code, out, _ = self.cli_create(text="# Ficha\nNombre: «Aria»\r\nsin final")
        view = self.draft()
        self.assertEqual((code, out), (0, (
            f"Ficha creada: {self.line(view)}\n"
            "Revisión del personaje: 2.\n"
            "Ficha para copia manual (no acredita publicación, hasta «Fin de la ficha.»):\n"
            "# Ficha\nNombre: «Aria»\r\nsin final\n"
            "Fin de la ficha.\n")))
        code, out, _ = self.cli_create("--json", composition=view.record.composition_sha256,
                                       text="# Ficha\nNombre: «Aria»\r\nsin final")
        payload = json.loads(out)
        self.assertEqual(payload, {
            "ok": True, "action": "character.draft.create", "character_id": "aria",
            "created": False, "draft": draft_view_record(view), "instance": str(self.instance),
            "state_revision": 2})
        self.assertEqual(set(payload["draft"]), {
            "composition_sha256", "concept", "content", "context_refs", "corpus_ref_count",
            "corpus_refs", "current", "draft_id", "draft_sha256", "lifecycle",
            "publication_status", "review_evidence", "review_status", "source_refs",
            "stale_reason", "utf8_size", "version"})
        self.assertTrue(out.isascii())

    def test_list_and_show_text_and_json(self):
        code, out, _ = run("character", "draft", "list", "--instance", self.path,
                           "--character-id", "aria")
        self.assertEqual((code, out), (0, "No hay fichas para «aria».\n"))
        self.add(text="A\n", citations=(("normas", 3), ("duda", 1)))
        self.decide()
        self.cli_create()
        self.cli_create(version="2", text="# Ficha v2\n", name="v2.md")
        views = list_drafts(self.loaded(), character_id="aria")
        code, out, _ = run("character", "draft", "list", "--instance", self.path,
                           "--character-id", "aria")
        self.assertEqual(out, "".join(self.line(v) + "\n" for v in views))
        self.assertIn("| STALE | SUPERSEDED |", out)
        code, out, _ = run("--json", "character", "draft", "list", "--instance", self.path,
                           "--character-id", "aria")
        self.assertEqual(json.loads(out), {
            "ok": True, "action": "character.draft.list", "character_id": "aria",
            "drafts": [draft_summary(v) for v in views], "instance": str(self.instance),
            "state_revision": 5})
        corpus = {c.key: c.candidate_sha256 for c in self.loaded().candidates}
        view = views[1]
        argv = ("character", "draft", "show", "--instance", self.path, "--character-id", "aria",
                "--version", "2")
        references = (
            f"Concepto citado: v1 | sha256={view.record.concept.concept_sha256} | "
            f"evidencia={view.record.draft.source_refs[0].sha256}\n"
            "Corpus citado (2):\n"
            f"Cita 1: normas v3 | sha256={corpus[('normas', 3)]} | APPROVED\n"
            f"Cita 2: duda v1 | sha256={corpus[('duda', 1)]} | APPROVED\n")
        sheet = ("Ficha para copia manual (no acredita publicación, hasta «Fin de la ficha.»):\n"
                 "# Ficha v2\nFin de la ficha.\n")
        code, out, _ = run(*argv)
        self.assertEqual((code, out), (0, f"{self.line(view)}\nRespuesta del staff: ninguna.\n"
                                          + references + sheet))
        code, out, _ = run("--json", *argv)
        self.assertEqual(json.loads(out), {
            "ok": True, "action": "character.draft.show", "character_id": "aria",
            "draft": draft_view_record(view), "instance": str(self.instance),
            "staff_response": None, "state_revision": 5})
        self.cli_record(version="2", status="REJECTED", response="Cambios: edad\r\nfin")
        view = self.draft(2)
        response = view.staff_response
        code, out, _ = run(*argv)
        self.assertEqual(out, (
            f"{self.line(view)}\n"
            f"Respuesta del staff: REJECTED | respuesta={response.response_sha256} | "
            f"registro={response.staff_review_sha256} | locator={json.dumps(LOCATOR)} | "
            "observada=2026-10-12T18:30:00+02:00.\n" + references + sheet
            + "RESPUESTA TRANSCRITA — texto exacto (hasta «Fin de la respuesta.»):\n"
              "Cambios: edad\r\nfin\nFin de la respuesta.\n"))
        code, out, _ = run("--json", *argv)
        payload = json.loads(out)
        self.assertEqual((payload["staff_response"], payload["draft"]["review_status"]),
                         (staff_response_record(response), "REJECTED"))
        self.assertEqual(payload["draft"]["review_evidence"]["source_id"],
                         "staff-response:aria:v2")

    def test_error_codes_without_mutation(self):
        self.cli_create()
        before = self.loaded().characters[0].state_revision
        current = self.effective().composition_sha256
        cases = [
            (3, ("character", "draft", "show", "--instance", self.path, "--character-id", "aria",
                 "--version", "9")),
            (3, ("character", "draft", "list", "--instance", self.path, "--character-id",
                 "nadie")),
            (3, ("character", "draft", "create", "--instance", self.path, "--character-id",
                 "aria", "--version", "2", "--composition-sha256", "ABC", "--input",
                 str(self.write_sheet("Otra\n", "e1.md")))),
            (4, ("character", "draft", "create", "--instance", self.path, "--character-id",
                 "aria", "--version", "2", "--composition-sha256", "0" * 64, "--input",
                 str(self.write_sheet("Otra\n", "e2.md")))),
            (4, ("character", "draft", "create", "--instance", self.path, "--character-id",
                 "aria", "--version", "3", "--composition-sha256", current, "--input",
                 str(self.write_sheet("Otra\n", "e3.md")))),
            (3, ("character", "draft", "create", "--instance", self.path, "--character-id",
                 "aria", "--version", "2", "--composition-sha256", current, "--input",
                 str(self.root / "no-existe.md"))),
        ]
        for expected, argv in cases:
            with self.subTest(argv=argv[2:5]):
                code, out, err = run(*argv)
                self.assertEqual((code, out), (expected, ""))
                self.assertTrue(err.startswith("Error ("))
                code, out, _ = run("--json", *argv)
                self.assertEqual((code, set(json.loads(out))),
                                 (expected, {"ok", "code", "message"}))
        self.assertEqual(self.loaded().characters[0].state_revision, before)


class StaffRecordCliTest(StaffCliCase):
    def test_json_and_non_interactive_paths_cannot_record(self):
        self.cli_create()
        before = self.loaded().characters[0].state_revision
        code, out, _ = self.cli_record("--json")
        self.assertEqual((code, json.loads(out)), (3, {
            "ok": False, "code": "INVALID_STATE", "message": STAFF_JSON_MESSAGE}))
        argv = ["character", "staff", "record", "--instance", self.path, "--character-id",
                "aria", "--version", "1", "--status", "APPROVED", "--input",
                str(self.write_response())]
        code, out, err = run(*argv, stdin="REGISTRAR-RESPUESTA-STAFF APPROVED character-sheet "
                                          "v1 ABCDEFGH\n")
        self.assertEqual((code, out), (3, ""))
        self.assertIn("terminal interactiva", err)
        result = subprocess.run([sys.executable, "-B", "-m", "core.runtime.cli", *argv],
                                cwd=ROOT, capture_output=True, stdin=subprocess.DEVNULL)
        self.assertEqual(result.returncode, 3)
        self.assertNotIn(b"REGISTRAR-RESPUESTA-STAFF", result.stdout)
        self.assertEqual(self.loaded().characters[0].state_revision, before)

    def test_record_and_retry_outputs(self):
        self.cli_create()
        code, out, _ = self.cli_record()
        view = self.draft()
        response = view.staff_response
        expected_tail = (f"character-sheet v1 | APPROVED | respuesta={response.response_sha256} | "
                         f"registro={response.staff_review_sha256}\n"
                         f"{self.line(view)}\nRevisión del personaje: 3.\n")
        self.assertEqual((code, out), (0, "Respuesta del staff registrada: " + expected_tail))
        self.assertIn("| APPROVED | NOT_CONFIRMED |", out)
        code, out, _ = self.cli_record()
        self.assertEqual((code, out), (0, "Respuesta del staff ya registrada: " + expected_tail))
        self.assertEqual(self.cli_record(status="REJECTED")[0], 4)
        self.assertEqual(self.cli_record(draft_sha256="0" * 64)[0], 4)
        self.assertEqual(self.cli_record(version="2", input_path=self.write_response())[0], 3)
        self.assertEqual(self.cli_record(input_path=self.root / "no-existe.json")[0], 3)


if __name__ == "__main__":
    unittest.main()
