"""Vertical slice of increments 4 and 7a: dossier → workspace → candidates → decisions and
closure → instance → human concept → proposals → effective composition → sheet → transcribed
staff response → topic → transcribed post → human seed → developed draft → manual publication
confirmed afterwards.

Agent steps run through the CLI in a fresh process each time (a restart between phases). Human
steps (barrier A) go through the API with a fake terminal, because a real TTY cannot be scripted;
every call reloads the state from disk.

No step may reach the network, start a process (where a model provider would live) or open a
database. Python audit hooks watch the execution itself, not the imports: in each CLI child an
attempt leaves a marker and ends the process with `os._exit`, which no `except` can hide; in the
human steps an attempt is recorded and checked afterwards. Optional modules that the slice does
not reach are not a failure.
"""

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from core.review.models import ReviewStatus
from core.runtime.character import (
    import_concept,
    record_proposal_decision,
    record_staff_response,
)
from core.runtime.narrative import (
    confirm_narrative_publication,
    import_human_seed,
    record_external_post,
)
from tests.expected_instance_templates import EXPECTED_AGENTS, EXPECTED_CLAUDE, EXPECTED_POLICY
from tests.instance_support import close, decide
from tests.test_assimilation_decisions import FakeTerminal

ROOT = Path(__file__).resolve().parent.parent
DOSSIER = ROOT / "tests" / "fixtures" / "dossiers" / "minimal-neutral"
INPUTS = ROOT / "tests" / "fixtures" / "vertical-neutral"
APPROVED, REJECTED = ReviewStatus.APPROVED, ReviewStatus.REJECTED
LEGACY = re.compile(r"Nozomu|Naruto|Jcink|narutorol|account 59")
# Audit events of network, processes (a model provider), databases and browsers.
FORBIDDEN_EVENTS = ("socket.", "subprocess.", "os.system", "os.exec", "os.spawn",
                    "os.posix_spawn", "os.startfile", "os.fork", "_winapi.CreateProcess",
                    "sqlite3.", "urllib.", "http.", "ftplib.", "smtplib.", "webbrowser.")
FORBIDDEN_EXIT = 97
MARKER_ENV = "ROLEPLAY_VERTICAL_MARKER"


def child_script(before: str = "") -> str:
    """Run the CLI under an audit hook that cannot be silenced by the code it watches."""
    return (
        "import os, runpy, sys\n"
        f"FORBIDDEN = {FORBIDDEN_EVENTS!r}\n"
        "def _guard(event, args):\n"
        "    if event.startswith(FORBIDDEN):\n"
        f"        with open(os.environ[{MARKER_ENV!r}], 'a', encoding='utf-8') as marker:\n"
        "            marker.write(event + '\\n')\n"
        f"        os._exit({FORBIDDEN_EXIT})\n"
        "sys.addaudithook(_guard)\n"
        f"{before}"
        "runpy.run_module('core.runtime.cli', run_name='__main__', alter_sys=True)\n"
    )


_WATCH = {"active": False, "events": []}


def _parent_guard(event: str, args) -> None:
    """Inert unless a human step is running; audit hooks cannot be removed once added."""
    if _WATCH["active"] and event.startswith(FORBIDDEN_EVENTS):
        _WATCH["events"].append(event)
        raise RuntimeError(f"invocación prohibida en el recorrido vertical: {event}")


sys.addaudithook(_parent_guard)


def watched(action):
    """Run `action` with the parent guard on; return its result and the forbidden events."""
    _WATCH["active"], _WATCH["events"] = True, []
    try:
        result = action()
    finally:
        _WATCH["active"] = False
    return result, list(_WATCH["events"])


class VerticalSliceTest(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.base, True)
        self.dossier = self.base / "expediente"
        shutil.copytree(DOSSIER, self.dossier)
        self.inputs = self.base / "entradas"
        shutil.copytree(INPUTS, self.inputs)
        self.workspace = self.base / "workspace"
        self.instance = self.base / "instancia"
        self.marker = self.base / "invocaciones-prohibidas.txt"

    # --- helpers ------------------------------------------------------------------------------

    def run_child(self, *argv: str, before: str = "") -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-B", "-c", child_script(before), *argv],
                              cwd=ROOT, capture_output=True, stdin=subprocess.DEVNULL,
                              env={**os.environ, MARKER_ENV: str(self.marker)})

    def cli(self, *argv: str) -> dict:
        """One agent step in a new process, with --json; fails on any error or invocation."""
        result = self.run_child("--json", *argv)
        self.assertFalse(self.marker.exists(), msg=f"{argv}: {self.read_marker()}")
        payload = json.loads(result.stdout.decode("utf-8"))
        self.assertEqual((result.returncode, payload.get("ok")), (0, True),
                         msg=f"{argv}: {payload}")
        return payload

    def character(self, *argv: str) -> dict:
        return self.cli("character", *argv, "--instance", str(self.instance),
                        "--character-id", "ejemplo")

    def fill(self, name: str, **values: str) -> Path:
        """An external temporary copy of an input with its placeholders replaced."""
        text = (self.inputs / name).read_text(encoding="utf-8")
        for key, value in values.items():
            text = text.replace(f"__{key}__", value)
        assert "__" not in text, name
        target = self.inputs / f"lleno-{name}"
        target.write_bytes(text.encode("utf-8"))
        return target

    def read_marker(self) -> str:
        return self.marker.read_text(encoding="utf-8") if self.marker.exists() else ""

    def human(self, action):
        """One human step through the API, watched by the parent audit hook."""
        result, events = watched(action)
        self.assertEqual(events, [])
        return result

    def state_bytes(self) -> dict[str, bytes]:
        roots = [r for r in (self.workspace, self.instance) if r.exists()]  # not the marker
        return {p.relative_to(self.base).as_posix(): p.read_bytes()
                for root in roots for p in sorted(root.rglob("*")) if p.is_file()}

    def assert_repeat_changes_nothing(self, action) -> object:
        before = self.state_bytes()
        result = action()
        self.assertEqual(self.state_bytes(), before)
        return result

    def effective(self) -> dict:
        return self.character("effective", "show")["composition"]

    # --- the slice ----------------------------------------------------------------------------

    def test_full_slice_survives_restarts_and_repetitions(self):
        # Dossier → workspace.
        self.assertTrue(self.cli("assimilation", "init", "--dossier", str(self.dossier),
                                 "--workspace", str(self.workspace))["created"])
        self.assertFalse(self.assert_repeat_changes_nothing(lambda: self.cli(
            "assimilation", "init", "--dossier", str(self.dossier),
            "--workspace", str(self.workspace)))["created"])

        # Four candidate classes, all pending.
        candidate_files = sorted((self.inputs / "candidates").glob("*.json"))
        for path in candidate_files:
            self.assertTrue(self.cli("assimilation", "candidate", "add", "--workspace",
                                     str(self.workspace), "--input", str(path))["created"])
        self.assertFalse(self.assert_repeat_changes_nothing(lambda: self.cli(
            "assimilation", "candidate", "add", "--workspace", str(self.workspace),
            "--input", str(candidate_files[0])))["created"])
        listed = self.cli("assimilation", "candidate", "list", "--workspace",
                          str(self.workspace))["candidates"]
        self.assertEqual({c["class"] for c in listed},
                         {"LITERAL", "INTERPRETATION", "PROPOSAL", "UNCERTAINTY"})

        # Human decisions and closure (barrier A through the API).
        for candidate_id in ("normas", "mundo", "fichas", "staff", "formato", "costa", "clima"):
            self.human(lambda: decide(self.workspace, candidate_id))
        self.human(lambda: decide(self.workspace, "turnos", status=REJECTED))
        self.assert_repeat_changes_nothing(lambda: self.human(
            lambda: decide(self.workspace, "normas")))
        self.human(lambda: close(self.workspace))
        self.assert_repeat_changes_nothing(lambda: self.human(lambda: close(self.workspace)))

        # Instance.
        self.assertTrue(self.cli("instance", "init", "--workspace", str(self.workspace),
                                 "--output", str(self.instance))["created"])
        self.assertFalse(self.assert_repeat_changes_nothing(lambda: self.cli(
            "instance", "init", "--workspace", str(self.workspace),
            "--output", str(self.instance)))["created"])
        corpus = {(e["candidate_id"], e["version"]): e for e in self.cli(
            "instance", "corpus", "list", "--instance", str(self.instance))["candidates"]}
        self.assertNotIn(("turnos", 1), corpus)
        statics = {name: data for name, data in self.state_bytes().items()
                   if name.startswith("instancia/")}

        # Human concept v1.
        self.import_concept(1)
        self.assertFalse(self.assert_repeat_changes_nothing(lambda: self.import_concept(1))
                         .created)
        root = self.effective()
        self.assertEqual((root["applied_proposals"], root["text"]),
                         ([], (self.inputs / "concepto-v1.md").read_text(encoding="utf-8")))

        # Two complete proposals on the exact base; one accepted, the other obsolete then
        # rejected.
        accepted = self.fill("propuesta-aceptada.json",
                             BASE_COMPOSITION_SHA256=root["composition_sha256"])
        alternative = self.fill("propuesta-alternativa.json",
                                BASE_COMPOSITION_SHA256=root["composition_sha256"])
        for path in (accepted, alternative):
            added = self.character("proposal", "add", "--input", str(path))
            self.assertEqual((added["created"], added["proposal"]["status"]), (True, "PENDING"))
        self.assertFalse(self.assert_repeat_changes_nothing(
            lambda: self.character("proposal", "add", "--input", str(accepted)))["created"])
        self.decide_proposal("convivencia", APPROVED)
        self.assertEqual(self.proposal_statuses(), {"convivencia": ("APPROVED", True),
                                                    "origen": ("OBSOLETE", False)})
        self.decide_proposal("origen", REJECTED)
        self.assert_repeat_changes_nothing(lambda: self.decide_proposal("origen", REJECTED))
        effective = self.effective()
        accepted_value = json.loads(accepted.read_text(encoding="utf-8"))
        self.assertEqual((effective["text"], [s["proposal_id"]
                                              for s in effective["applied_proposals"]]),
                         (accepted_value["text"], ["convivencia"]))

        # Sheet v1: only the declared concept plus approved corpus/proposals feed it.
        sheet = self.character("draft", "create", "--version", "1", "--composition-sha256",
                               effective["composition_sha256"], "--input",
                               str(self.inputs / "ficha-v1.md"))["draft"]
        self.assertEqual((sheet["lifecycle"], sheet["review_status"],
                          sheet["publication_status"], sheet["current"]),
                         ("ACTIVE", "PENDING_HUMAN_REVIEW", "NOT_CONFIRMED", True))
        self.assertEqual(sheet["corpus_refs"], [
            {"candidate_id": c, "candidate_sha256": corpus[(c, 1)]["candidate_sha256"],
             "version": 1} for c in ("normas", "clima")])
        self.assertFalse(self.assert_repeat_changes_nothing(lambda: self.character(
            "draft", "create", "--version", "1", "--composition-sha256",
            effective["composition_sha256"], "--input",
            str(self.inputs / "ficha-v1.md")))["created"])

        # Concept v2: the chain restarts and v1 becomes STALE by derivation only.
        revision = self.character("draft", "list")["state_revision"]
        self.import_concept(2)
        stale = self.character("draft", "show", "--version", "1")
        self.assertEqual(stale["state_revision"], revision + 1)
        self.assertTrue(stale["draft"]["stale_reason"].startswith(
            "EFFECTIVE_COMPOSITION_CHANGED:"))
        restarted = self.effective()
        self.assertEqual((restarted["applied_proposals"], restarted["concept"]["version"]),
                         ([], 2))
        self.assertEqual(self.proposal_statuses(), {"convivencia": ("APPROVED", False),
                                                    "origen": ("REJECTED", False)})

        # Sheet v2 and the transcribed staff response.
        v2 = self.character("draft", "create", "--version", "2", "--composition-sha256",
                            restarted["composition_sha256"], "--input",
                            str(self.inputs / "ficha-v2.md"))["draft"]
        self.assertEqual(v2["corpus_refs"], [])
        response = self.fill("respuesta-staff.json", DRAFT_SHA256=v2["draft_sha256"])
        self.record_staff(response)
        self.assertFalse(self.assert_repeat_changes_nothing(
            lambda: self.record_staff(response)).created)
        self.assertEqual(self.effective(), restarted)

        # 7a: a topic with someone else's post, a seed, a developed draft and its publication.
        topic = self.narrative("topic", "create", "--character-id", "ejemplo", "--title",
                               "En el muelle")
        self.assertEqual((topic["created"], topic["state_revision"]), (True, 1))
        self.assertFalse(self.assert_repeat_changes_nothing(lambda: self.narrative(
            "topic", "create", "--character-id", "ejemplo", "--title", "En el muelle"))["created"])
        self.record_post()
        self.assertFalse(self.assert_repeat_changes_nothing(self.record_post).created)
        seed = self.import_seed().seed
        self.assertEqual(seed.mode.value, "CONTINUAR")
        self.assertFalse(self.assert_repeat_changes_nothing(self.import_seed).created)
        shown = self.narrative("seed", "show", "--seed-id", "turno-1", "--version", "1")["seed"]
        context = self.narrative("topic", "show")["topic"]["context_sha256"]
        draft_input = self.fill("borrador-narrativo.json", SEED_SHA256=shown["seed_sha256"],
                                CONTEXT_SHA256=context,
                                COMPOSITION_SHA256=restarted["composition_sha256"],
                                SHEET_SHA256=v2["draft_sha256"])
        draft = self.narrative("draft", "create", "--input", str(draft_input))["draft"]
        self.assertEqual((draft["lifecycle"], draft["publication"], draft["target_position"],
                          draft["sheet"]["version"]), ("ACTIVE", "NONE", 2, 2))
        self.assertFalse(self.assert_repeat_changes_nothing(lambda: self.narrative(
            "draft", "create", "--input", str(draft_input)))["created"])
        copy = self.run_child("narrative", "draft", "show", "--instance", str(self.instance),
                              "--topic-id", "muelle", "--draft-id", "turno-1", "--version", "1")
        self.assertEqual(copy.returncode, 0)
        block = copy.stdout.decode("utf-8").split("«Fin del post.»):\n")[1].split(
            "Fin del post.\n")[0]
        self.assertEqual(block, draft["publishable_text"])
        for private in (*draft["ooc_notes"], *draft["private_notes"]):
            self.assertNotIn(private, block)
        publication = self.fill("publicacion.json", DRAFT_SHA256=draft["draft_sha256"])
        self.confirm_publication(publication)
        self.assertFalse(self.assert_repeat_changes_nothing(
            lambda: self.confirm_publication(publication)).created)
        posts = self.narrative("post", "list")["posts"]
        self.assertEqual([(p["position"], p["author"], p["post_id"]) for p in posts],
                         [(1, "OTHER", "respuesta-1"), (2, "SELF", "propio-1")])
        drafts = self.narrative("draft", "list")["drafts"]
        self.assertEqual([(d["lifecycle"], d["publication"]) for d in drafts],
                         [("STALE", "EDITED")])
        self.assertEqual(self.narrative("topic", "show")["state_revision"], 5)
        self.assertEqual(self.effective(), restarted)

        # Final state: whole history visible, nothing published, statics untouched.
        drafts = self.character("draft", "list")["drafts"]
        self.assertEqual([(d["version"], d["lifecycle"], d["current"], d["review_status"],
                           d["publication_status"]) for d in drafts],
                         [(1, "STALE", False, "PENDING_HUMAN_REVIEW", "NOT_CONFIRMED"),
                          (2, "ACTIVE", True, "APPROVED", "NOT_CONFIRMED")])
        shown = self.character("draft", "show", "--version", "1")["draft"]
        self.assertEqual(shown["stale_reason"], "SUPERSEDED_BY:character-sheet:v2")
        self.assertEqual(len(self.character("concept", "list")["concepts"]), 2)
        self.cli("instance", "status", "--instance", str(self.instance))
        final = self.state_bytes()
        for name, data in statics.items():
            self.assertEqual(final[name], data, msg=name)
        self.assertEqual(sorted(n for n in final if n.startswith("instancia/")
                                and n not in statics),
                         ["instancia/characters/ejemplo/state.json",
                          "instancia/narrative/topics/muelle/state.json"])
        self.assert_instructions_are_v1()
        for name, data in final.items():
            self.assertIsNone(LEGACY.search(data.decode("utf-8", "replace")), msg=name)

    def narrative(self, group: str, action: str, *argv: str) -> dict:
        topic = () if (group, action) == ("topic", "list") else ("--topic-id", "muelle")
        return self.cli("narrative", group, action, "--instance", str(self.instance), *topic,
                        *argv)

    # --- human steps --------------------------------------------------------------------------

    def record_post(self):
        return self.human(lambda: record_external_post(
            self.instance, expected_core_root=ROOT, topic_id="muelle",
            input_path=self.inputs / "post-ajeno.json", terminal=FakeTerminal()))

    def import_seed(self):
        return self.human(lambda: import_human_seed(
            self.instance, expected_core_root=ROOT, topic_id="muelle",
            input_path=self.inputs / "semilla.json", terminal=FakeTerminal()))

    def confirm_publication(self, path: Path):
        return self.human(lambda: confirm_narrative_publication(
            self.instance, expected_core_root=ROOT, topic_id="muelle", draft_id="turno-1",
            version=1, input_path=path, terminal=FakeTerminal()))

    def import_concept(self, version: int):
        return self.human(lambda: import_concept(
            self.instance, expected_core_root=ROOT, character_id="ejemplo", version=version,
            input_path=self.inputs / f"concepto-v{version}.md", terminal=FakeTerminal()))

    def decide_proposal(self, proposal_id: str, status: ReviewStatus):
        return self.human(lambda: record_proposal_decision(
            self.instance, expected_core_root=ROOT, character_id="ejemplo",
            proposal_id=proposal_id, version=1, review_status=status, terminal=FakeTerminal()))

    def record_staff(self, path: Path):
        return self.human(lambda: record_staff_response(
            self.instance, expected_core_root=ROOT, character_id="ejemplo", version=2,
            review_status=APPROVED, input_path=path, terminal=FakeTerminal()))

    def proposal_statuses(self) -> dict[str, tuple[str, bool]]:
        return {p["proposal_id"]: (p["status"], p["applied_to_effective"])
                for p in self.character("proposal", "list")["proposals"]}

    def assert_instructions_are_v1(self):
        for name, template in (("AGENTS.md", EXPECTED_AGENTS), ("CLAUDE.md", EXPECTED_CLAUDE)):
            wanted = (template.replace("$display_name", "Foro neutral de prueba")
                      .replace("$forum_id", "foro-neutral")
                      .replace("$common_policy", EXPECTED_POLICY)
                      .replace("$core_root_ps", str(ROOT).replace("'", "''"))
                      .replace("$instance_root_ps", str(self.instance).replace("'", "''")))
            self.assertEqual((self.instance / name).read_bytes(), wanted.encode("utf-8"),
                             msg=name)


class GuardTest(unittest.TestCase):
    """The watchers catch an invocation even when the watched code swallows the exception."""

    def setUp(self):
        self.base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.base, True)
        self.marker = self.base / "invocaciones-prohibidas.txt"

    def test_child_guard_cannot_be_silenced(self):
        attempts = {
            "socket.": "import socket\n"
                       "try:\n"
                       "    socket.create_connection(('127.0.0.1', 9), timeout=0.01)\n"
                       "except BaseException:\n"
                       "    pass\n",
            "subprocess.": "import subprocess\n"
                           "try:\n"
                           "    subprocess.run([sys.executable, '-c', 'pass'])\n"
                           "except BaseException:\n"
                           "    pass\n",
            "sqlite3.": "import sqlite3\n"
                        "try:\n"
                        "    sqlite3.connect(':memory:')\n"
                        "except BaseException:\n"
                        "    pass\n",
        }
        for prefix, before in attempts.items():
            with self.subTest(prefix=prefix):
                result = subprocess.run(
                    [sys.executable, "-B", "-c", child_script(before), "--json", "instance",
                     "status", "--instance", str(self.base)],
                    cwd=ROOT, capture_output=True, stdin=subprocess.DEVNULL,
                    env={**os.environ, MARKER_ENV: str(self.marker)})
                self.assertEqual((result.returncode, result.stdout), (FORBIDDEN_EXIT, b""))
                self.assertTrue(self.marker.read_text(encoding="utf-8").startswith(prefix))
                self.marker.unlink()

    def test_child_guard_lets_a_clean_step_run(self):
        result = subprocess.run(
            [sys.executable, "-B", "-c", child_script(), "--json", "instance", "status",
             "--instance", str(self.base / "no-existe")],
            cwd=ROOT, capture_output=True, stdin=subprocess.DEVNULL,
            env={**os.environ, MARKER_ENV: str(self.marker)})
        self.assertNotEqual(result.returncode, FORBIDDEN_EXIT)
        self.assertFalse(json.loads(result.stdout)["ok"])
        self.assertFalse(self.marker.exists())

    def test_parent_guard_records_swallowed_invocations(self):
        def swallowed():
            try:
                socket.create_connection(("127.0.0.1", 9), timeout=0.01)
            except BaseException:
                pass
            return "terminado"

        result, events = watched(swallowed)
        self.assertEqual(result, "terminado")
        self.assertTrue(events and events[0].startswith("socket."))
        self.assertEqual(watched(lambda: "limpio"), ("limpio", []))


class NeutralInputsTest(unittest.TestCase):
    def test_inputs_are_neutral(self):
        for path in sorted(INPUTS.rglob("*")):
            if path.is_file():
                with self.subTest(path=path.name):
                    self.assertIsNone(LEGACY.search(path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    unittest.main()
