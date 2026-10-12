import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from adapters.manual import load_manual_dossier
from core.review.models import ReviewStatus
from core.runtime import cli
from core.runtime.assimilation import add_candidate, record_candidate_decision
from core.runtime.workspace import CORPUS_STATE, create_workspace, load_workspace
from tests.test_assimilation_decisions import LITERALS, FakeTerminal, literal_input

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "dossiers" / "minimal-neutral"
HUMAN_COMMANDS = (
    ["candidate", "approve", "--candidate-id", "normas", "--version", "1"],
    ["candidate", "reject", "--candidate-id", "normas", "--version", "1"],
    ["close"],
)


def run(*argv: str, stdin: str = "") -> tuple[int, str, str]:
    """Run main with a non-interactive stdin, as any automated caller would."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
            mock.patch.object(sys, "stdin", io.StringIO(stdin)):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class DecisionCliCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        shutil.copytree(FIXTURE, root / "exp")
        self.workspace = root / "ws"
        create_workspace(load_manual_dossier(root / "exp"), dossier_dir=root / "exp",
                         workspace=self.workspace, core_root=ROOT)
        self.ws = str(self.workspace)
        self.state = self.workspace / CORPUS_STATE
        for candidate_id in LITERALS:
            loaded = load_workspace(self.workspace)
            add_candidate(self.state, dossier=loaded.dossier,
                          expected_revision=loaded.corpus_revision,
                          value=literal_input(candidate_id))


class ParserTest(DecisionCliCase):
    def test_required_arguments(self):
        for argv in (["candidate", "approve", "--workspace", "x", "--candidate-id", "normas"],
                     ["candidate", "reject", "--workspace", "x", "--version", "1"],
                     ["candidate", "approve", "--candidate-id", "normas", "--version", "1"],
                     ["candidate", "approve", "--workspace", "x", "--candidate-id", "normas",
                      "--version", "uno"],
                     ["close"], ["decision", "list"]):
            with self.subTest(argv=argv):
                self.assertEqual(run("assimilation", *argv)[0], 2)

    def test_no_bypass_flags(self):
        base = ["assimilation", "candidate", "approve", "--workspace", self.ws, "--candidate-id",
                "normas", "--version", "1"]
        for extra in (["--yes"], ["--force"], ["--nonce", "ABCDEFGH"],
                      ["--confirmation", "APROBAR normas v1 ABCDEFGH"], ["--input", "x.json"]):
            with self.subTest(extra=extra):
                self.assertEqual(run(*base, *extra)[0], 2)
        for extra in (["--yes"], ["--nonce", "ABCDEFGH"]):
            self.assertEqual(run("assimilation", "close", "--workspace", self.ws, *extra)[0], 2)


class HumanCommandTest(DecisionCliCase):
    def invoke(self, command: list[str], *extra: str, stdin: str = "") -> tuple[int, str, str]:
        if command[0] == "candidate":
            argv = ["assimilation", "candidate", command[1], "--workspace", self.ws, *command[2:]]
        else:
            argv = ["assimilation", *command, "--workspace", self.ws]
        return run(*extra, *argv, stdin=stdin)

    def test_json_is_rejected_before_any_prompt(self):
        before = self.state.read_bytes()
        for command in HUMAN_COMMANDS:
            with self.subTest(command=command[:2]):
                code, out, _ = self.invoke(command, "--json")
                self.assertEqual(code, 3)
                payload = json.loads(out)
                self.assertEqual(set(payload), {"ok", "code", "message"})
                self.assertEqual(payload["code"], "INVALID_STATE")
                self.assertNotIn("Escribe exactamente", out)
        self.assertEqual(self.state.read_bytes(), before)

    def test_non_interactive_stdin_is_rejected_even_with_the_right_phrase(self):
        before = self.state.read_bytes()
        for command in HUMAN_COMMANDS:
            with self.subTest(command=command[:2]):
                code, out, err = self.invoke(command, stdin="APROBAR normas v1 ABCDEFGH\n")
                self.assertEqual((code, out), (3, ""))
                self.assertIn("terminal interactiva", err)
        self.assertEqual(self.state.read_bytes(), before)

    def test_environment_does_not_bypass(self):
        env = {"ROLEPLAY_NONCE": "ABCDEFGH", "ROLEPLAY_CONFIRMATION": "APROBAR normas v1 ABCDEFGH",
               "CI": "1"}
        with mock.patch.dict(os.environ, env):
            code, _, _ = self.invoke(HUMAN_COMMANDS[0])
        self.assertEqual(code, 3)

    def test_system_terminal_requires_both_ttys(self):
        terminal = cli._SystemTerminal()
        for stdin_tty, stdout_tty, expected in ((True, True, True), (True, False, False),
                                                (False, True, False)):
            with self.subTest(stdin=stdin_tty, stdout=stdout_tty):
                with mock.patch.object(sys.stdin, "isatty", return_value=stdin_tty), \
                        mock.patch.object(sys.stdout, "isatty", return_value=stdout_tty):
                    self.assertIs(terminal.is_interactive(), expected)

    def test_subprocess_with_redirected_output_cannot_decide(self):
        before = self.state.read_bytes()
        for command in HUMAN_COMMANDS:
            with self.subTest(command=command[:2]):
                argv = (["assimilation", "candidate", command[1], "--workspace", self.ws,
                         *command[2:]] if command[0] == "candidate"
                        else ["assimilation", *command, "--workspace", self.ws])
                result = subprocess.run([sys.executable, "-B", "-m", "core.runtime.cli", *argv],
                                        cwd=ROOT, capture_output=True, stdin=subprocess.DEVNULL)
                self.assertEqual(result.returncode, 3)
                self.assertNotIn("Escribe exactamente".encode(), result.stdout)
        self.assertEqual(self.state.read_bytes(), before)


class EffectiveDecisionDisplayTest(DecisionCliCase):
    """REV4C1-03: candidate list/show show the effective decision next to the record."""

    def test_list_and_show(self):
        loaded = load_workspace(self.workspace)
        result = record_candidate_decision(
            self.state, dossier=loaded.dossier, expected_revision=loaded.corpus_revision,
            candidate_id="normas", version=1, review_status=ReviewStatus.REJECTED,
            terminal=FakeTerminal())
        code, out, _ = run("assimilation", "candidate", "list", "--workspace", self.ws)
        lines = {line.split(" ")[0]: line for line in out.splitlines()}
        self.assertTrue(lines["normas"].endswith(" | decisión=REJECTED"))
        self.assertIn("PENDING_HUMAN_REVIEW", lines["normas"])
        self.assertNotIn("decisión=", lines["formato"])
        code, out, _ = run("--json", "assimilation", "candidate", "list", "--workspace", self.ws)
        decisions = {c["candidate_id"]: c["decision"] for c in json.loads(out)["candidates"]}
        self.assertEqual(decisions["normas"], "REJECTED")
        self.assertIsNone(decisions["formato"])
        code, out, _ = run("assimilation", "candidate", "show", "--workspace", self.ws,
                           "--candidate-id", "normas")
        self.assertIn(f"Decisión: REJECTED (evidencia={result.decision.evidence.sha256})\n", out)
        code, out, _ = run("assimilation", "candidate", "show", "--workspace", self.ws,
                           "--candidate-id", "formato")
        self.assertIn("Decisión: pendiente\n", out)
        code, out, _ = run("--json", "assimilation", "candidate", "show", "--workspace", self.ws,
                           "--candidate-id", "normas")
        payload = json.loads(out)
        self.assertEqual(payload["decision"]["review_status"], "REJECTED")
        self.assertEqual(payload["candidate"]["review_status"], "PENDING_HUMAN_REVIEW")


class DecisionListTest(DecisionCliCase):
    def test_empty_and_filled(self):
        self.assertEqual(run("assimilation", "decision", "list", "--workspace", self.ws)[1],
                         "No hay decisiones.\n")
        loaded = load_workspace(self.workspace)
        result = record_candidate_decision(
            self.state, dossier=loaded.dossier, expected_revision=loaded.corpus_revision,
            candidate_id="normas", version=1, review_status=ReviewStatus.APPROVED,
            terminal=FakeTerminal())
        decision = result.decision
        code, out, _ = run("assimilation", "decision", "list", "--workspace", self.ws)
        self.assertEqual(code, 0)
        self.assertEqual(out, f"normas v1 | APPROVED | sha256={decision.candidate_sha256} | "
                              f"evidencia={decision.evidence.sha256}\n")
        code, out, _ = run("--json", "assimilation", "decision", "list", "--workspace", self.ws)
        payload = json.loads(out)
        self.assertEqual(set(payload), {"ok", "action", "decisions", "corpus_revision", "workspace"})
        self.assertEqual(payload["action"], "assimilation.decision.list")
        self.assertEqual(payload["corpus_revision"], result.corpus_revision)
        self.assertEqual(payload["decisions"], [{
            "candidate_id": "normas", "candidate_sha256": decision.candidate_sha256,
            "candidate_version": 1, "decision_id": "candidate:normas:v1",
            "evidence_sha256": decision.evidence.sha256, "review_status": "APPROVED"}])


if __name__ == "__main__":
    unittest.main()
