import copy
import dataclasses
import hashlib
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from adapters.manual import load_manual_dossier
from core.memory.provenance import SourceRef
from core.review.models import ReviewStatus
from core.runtime import assimilation, persistence
from core.runtime.assimilation import (
    CLOSURE_ID,
    NONCE_ALPHABET,
    AssimilationClosure,
    AssimilationDecision,
    AssimilationError,
    HumanConfirmationReceipt,
    add_candidate,
    canonical_json_bytes,
    close_assimilation,
    record_candidate_decision,
)
from core.runtime.persistence import encode_state, load_state
from core.runtime.workspace import CORPUS_STATE, WorkspaceError, create_workspace, load_workspace

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "dossiers" / "minimal-neutral"
APPROVED, REJECTED = ReviewStatus.APPROVED, ReviewStatus.REJECTED
LITERALS = {
    "normas": ("forum_rules", "manual-foro", "1", "Convivencia",
               "Trata con respeto al resto de participantes"),
    "mundo": ("setting", "mundo-base", "2", None, "# Mundo base"),
    "fichas": ("character_creation", "manual-foro", "1", "Fichas", "Cada ficha incluye nombre"),
    "staff": ("staff_review", "revision-staff", "1", None, "Las fichas se publican"),
    "formato": ("platform_format", "formato-posts", "1", "Formato",
                "Los posts se escriben en tercera persona"),
}


def literal_input(candidate_id: str, version: int = 1, cls: str = "LITERAL", text: str | None = None):
    section, source_id, source_version, passage, quote = LITERALS[candidate_id]
    return {"candidate_id": candidate_id, "version": version,
            "domain": "WORLD" if section == "setting" else "RULES", "class": cls,
            "text": quote if text is None else text, "scope": "foro",
            "citations": [{"dossier_section": section, "source_id": source_id,
                           "source_version": source_version, "declared_passage": passage,
                           "quote": quote}]}


class FakeTerminal:
    """Test-only terminal. Answers with the phrase shown in the prompt, optionally transformed."""

    def __init__(self, interactive: bool = True, transform=lambda phrase: phrase + "\n",
                 on_read=None):
        self.interactive = interactive
        self.transform = transform
        self.on_read = on_read
        self.output = ""
        self.reads = 0

    def is_interactive(self) -> bool:
        return self.interactive

    def write(self, text: str) -> None:
        self.output += text

    def read_line(self):
        self.reads += 1
        if self.on_read is not None:
            self.on_read()
        phrase = re.search(r"Escribe exactamente: (.+)\n> $", self.output).group(1)
        return self.transform(phrase)


class DecisionCase(unittest.TestCase):
    def setUp(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root)
        shutil.copytree(FIXTURE, root / "exp")
        self.workspace = root / "ws"
        create_workspace(load_manual_dossier(root / "exp"), dossier_dir=root / "exp",
                         workspace=self.workspace, core_root=ROOT)
        self.state = self.workspace / CORPUS_STATE

    def loaded(self):
        return load_workspace(self.workspace)

    def add(self, value: dict):
        loaded = self.loaded()
        return add_candidate(self.state, dossier=loaded.dossier,
                             expected_revision=loaded.corpus_revision, value=value)

    def decide(self, candidate_id: str, version: int = 1, status=APPROVED, terminal=None):
        loaded = self.loaded()
        return record_candidate_decision(
            self.state, dossier=loaded.dossier, expected_revision=loaded.corpus_revision,
            candidate_id=candidate_id, version=version, review_status=status,
            terminal=terminal or FakeTerminal())

    def close(self, terminal=None):
        loaded = self.loaded()
        return close_assimilation(self.state, dossier=loaded.dossier,
                                  expected_revision=loaded.corpus_revision,
                                  terminal=terminal or FakeTerminal())

    def add_all_literals(self):
        for candidate_id in LITERALS:
            self.add(literal_input(candidate_id))

    def approve_all(self):
        for candidate_id in LITERALS:
            self.decide(candidate_id)

    def assert_unchanged(self, before: bytes):
        self.assertEqual(self.state.read_bytes(), before)


class ModelTest(unittest.TestCase):
    RECEIPT = HumanConfirmationReceipt("TTY_NONCE_V1", "a" * 64)
    EVIDENCE = SourceRef("human-decision:x", "assimilation://f/human-decisions/x")

    def test_receipt(self):
        for method, digest in (("TTY", "a" * 64), ("TTY_NONCE_V1", "A" * 64),
                               ("TTY_NONCE_V1", "a" * 63)):
            with self.subTest(method=method, digest=digest[:2]):
                with self.assertRaises(AssimilationError):
                    HumanConfirmationReceipt(method, digest)

    def test_decision_validation_and_immutability(self):
        decision = AssimilationDecision("candidate:x:v1", "x", 1, "b" * 64, APPROVED, self.RECEIPT,
                                        self.EVIDENCE)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            decision.review_status = REJECTED
        for overrides in (dict(decision_id="candidate:x:v2"), dict(candidate_version=0),
                          dict(review_status=ReviewStatus.PENDING_HUMAN_REVIEW),
                          dict(candidate_sha256="x"), dict(receipt=None), dict(evidence=None)):
            with self.subTest(overrides=str(overrides)[:40]):
                with self.assertRaises(AssimilationError):
                    dataclasses.replace(decision, **overrides)

    def test_closure_validation(self):
        closure = AssimilationClosure(CLOSURE_ID, 3, "c" * 64, self.RECEIPT, self.EVIDENCE)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            closure.base_revision = 4
        for overrides in (dict(closure_id="otro"), dict(base_revision=-1), dict(base_revision=True)):
            with self.subTest(overrides=str(overrides)):
                with self.assertRaises(AssimilationError):
                    dataclasses.replace(closure, **overrides)


class DecisionTest(DecisionCase):
    def setUp(self):
        super().setUp()
        self.add_all_literals()

    def test_prompt_is_exact(self):
        terminal = FakeTerminal()
        with mock.patch.object(assimilation.secrets, "choice", side_effect=list("ABCDEFGH")):
            result = self.decide("normas", terminal=terminal)
        sha = result.decision.candidate_sha256
        self.assertEqual(terminal.output,
                         "DECISIÓN HUMANA REQUERIDA\nCandidato: normas\nVersión: 1\n"
                         f"SHA-256: {sha}\nDecisión: APROBAR\n"
                         "Escribe exactamente: APROBAR normas v1 ABCDEFGH\n> ")
        terminal = FakeTerminal()
        with mock.patch.object(assimilation.secrets, "choice", side_effect=list("23456789")):
            self.decide("mundo", status=REJECTED, terminal=terminal)
        self.assertIn("Decisión: RECHAZAR\nEscribe exactamente: RECHAZAR mundo v1 23456789\n> ",
                      terminal.output)

    def test_nonce_alphabet_and_length(self):
        terminal = FakeTerminal()
        self.decide("normas", terminal=terminal)
        nonce = re.search(r"APROBAR normas v1 (\S+)\n> $", terminal.output).group(1)
        self.assertEqual(len(nonce), 8)
        self.assertTrue(set(nonce) <= set(NONCE_ALPHABET))
        self.assertEqual(len(NONCE_ALPHABET), 32)
        self.assertFalse(set("IO01") & set(NONCE_ALPHABET))

    def test_answer_rules(self):
        before = self.state.read_bytes()
        rejected = {
            "trailing space": lambda p: p + " \n",
            "lowercase": lambda p: p.lower() + "\n",
            "leading space": lambda p: " " + p + "\n",
            "other nonce": lambda p: p[:-1] + ("A" if p[-1] != "A" else "B") + "\n",
            "eof": lambda p: None,
        }
        for name, transform in rejected.items():
            with self.subTest(name):
                terminal = FakeTerminal(transform=transform)
                with self.assertRaises(AssimilationError) as ctx:
                    self.decide("normas", terminal=terminal)
                self.assertEqual(ctx.exception.code, "INVALID_STATE")
                self.assertEqual(terminal.reads, 1)
                self.assert_unchanged(before)
        self.assertEqual(self.decide("normas", terminal=FakeTerminal(
            transform=lambda p: p + "\r\n")).decision.review_status, APPROVED)

    def test_eof_message_says_cancelled(self):
        with self.assertRaises(AssimilationError) as ctx:
            self.decide("normas", terminal=FakeTerminal(transform=lambda p: None))
        self.assertIn("cancelada", ctx.exception.reason)

    def test_non_interactive_terminal_never_prompts(self):
        before = self.state.read_bytes()
        terminal = FakeTerminal(interactive=False)
        with self.assertRaises(AssimilationError):
            self.decide("normas", terminal=terminal)
        self.assertEqual((terminal.output, terminal.reads), ("", 0))
        self.assert_unchanged(before)

    def test_keyboard_interrupt_propagates_without_writing(self):
        before = self.state.read_bytes()

        def interrupt():
            raise KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            self.decide("normas", terminal=FakeTerminal(on_read=interrupt))
        self.assert_unchanged(before)

    def test_persisted_shape_without_nonce(self):
        terminal = FakeTerminal()
        result = self.decide("normas", terminal=terminal)
        nonce = re.search(r"v1 (\S+)\n> $", terminal.output).group(1)
        raw = self.state.read_text(encoding="utf-8")
        self.assertNotIn(nonce, raw)
        revision, content = load_state(self.state)
        self.assertEqual(revision, result.corpus_revision)
        record = content["decisions"][0]
        self.assertEqual(set(record), {"candidate_id", "candidate_sha256", "candidate_version",
                                       "decision_id", "evidence", "receipt", "review_status"})
        self.assertEqual(record["decision_id"], "candidate:normas:v1")
        self.assertEqual(record["receipt"]["method"], "TTY_NONCE_V1")
        phrase = f"APROBAR normas v1 {nonce}"
        self.assertEqual(record["receipt"]["confirmation_sha256"],
                         hashlib.sha256(phrase.encode()).hexdigest())
        evidence = record["evidence"]
        self.assertEqual(set(evidence), {"locator", "section_or_passage", "sha256", "source_id"})
        self.assertEqual(evidence["locator"],
                         "assimilation://foro-neutral/human-decisions/candidate%3Anormas%3Av1")
        self.assertEqual(evidence["source_id"], "human-decision:candidate:normas:v1")
        payload = {k: v for k, v in record.items() if k != "evidence"}
        self.assertEqual(evidence["sha256"],
                         hashlib.sha256(canonical_json_bytes(payload, pretty=False)).hexdigest())
        self.assertEqual(self.loaded().decisions, (result.decision,))

    def test_retry_is_idempotent_without_prompt_or_write(self):
        first = self.decide("normas")
        before = (self.state.read_bytes(), self.state.stat().st_mtime_ns)
        terminal = FakeTerminal()
        again = self.decide("normas", terminal=terminal)
        self.assertEqual((again.created, again.corpus_revision), (False, first.corpus_revision))
        self.assertEqual(terminal.output, "")
        self.assertEqual(before, (self.state.read_bytes(), self.state.stat().st_mtime_ns))

    def test_opposite_decision_conflicts(self):
        self.decide("normas")
        with self.assertRaises(AssimilationError) as ctx:
            self.decide("normas", status=REJECTED)
        self.assertEqual(ctx.exception.code, "CONFLICT")

    def test_unknown_candidate_or_status(self):
        with self.assertRaises(AssimilationError) as ctx:
            self.decide("no-existe")
        self.assertEqual(ctx.exception.code, "INVALID_STATE")
        with self.assertRaises(AssimilationError):
            self.decide("normas", status=ReviewStatus.PENDING_HUMAN_REVIEW)

    def test_only_current_version_can_be_decided_and_history_survives(self):
        self.decide("normas")
        self.add(literal_input("normas", version=2, cls="INTERPRETATION", text="Respeto mutuo."))
        state = self.loaded()
        self.assertEqual(len(state.decisions), 1)
        with self.assertRaises(AssimilationError):
            self.decide("formato", version=2)
        self.add(literal_input("formato", version=2, cls="INTERPRETATION", text="Tercera persona."))
        with self.assertRaises(AssimilationError) as ctx:
            self.decide("formato", version=1)
        self.assertEqual(ctx.exception.code, "CONFLICT")
        self.decide("normas", version=2, status=REJECTED)
        self.assertEqual([d.decision_id for d in self.loaded().decisions],
                         ["candidate:normas:v1", "candidate:normas:v2"])

    def test_concurrent_change_during_confirmation_conflicts(self):
        def concurrent_add():
            self.add(literal_input("normas", version=2, cls="PROPOSAL", text="Otra idea."))

        with self.assertRaises(AssimilationError) as ctx:
            self.decide("formato", terminal=FakeTerminal(on_read=concurrent_add))
        self.assertEqual(ctx.exception.code, "CONFLICT")
        self.assertEqual(self.loaded().decisions, ())

    def test_failed_replace_keeps_previous_bytes(self):
        before = self.state.read_bytes()
        with mock.patch.object(persistence.os, "replace", side_effect=OSError("simulado")):
            with self.assertRaises(AssimilationError) as ctx:
                self.decide("normas")
        self.assertEqual(ctx.exception.code, "IO")
        self.assert_unchanged(before)

    def tamper(self, change):
        revision, content = load_state(self.state)
        content = copy.deepcopy(content)
        revision = change(content) or revision
        self.state.write_bytes(encode_state(content, revision=revision))
        with self.assertRaises(WorkspaceError) as ctx:
            self.loaded()
        self.assertEqual(ctx.exception.code, "INVALID_STATE")

    def test_manipulated_decisions_fail_on_load(self):
        self.decide("normas")
        original = self.state.read_bytes()
        changes = {
            "status": lambda c: c["decisions"][0].update(review_status="REJECTED"),
            "candidate hash": lambda c: c["decisions"][0].update(candidate_sha256="0" * 64),
            "evidence hash": lambda c: c["decisions"][0]["evidence"].update(sha256="0" * 64),
            "locator": lambda c: c["decisions"][0]["evidence"].update(locator="x://y"),
            "receipt": lambda c: c["decisions"][0]["receipt"].update(confirmation_sha256="0" * 64),
            "unknown candidate": lambda c: c["decisions"][0].update(candidate_id="otro"),
            "duplicate": lambda c: c["decisions"].append(c["decisions"][0]),
            "extra key": lambda c: c["decisions"][0].update(nota="x"),
        }
        for name, change in changes.items():
            with self.subTest(name):
                self.tamper(change)
                self.state.write_bytes(original)
        self.loaded()


class LockTest(DecisionCase):
    """REV4C1-01: no mutation can slip in between the second read and the write."""

    def setUp(self):
        super().setUp()
        self.add_all_literals()
        self.lock = self.state.with_name(self.state.name + ".lock")

    def racing_write(self, intruder):
        """Patch the write so that, just before it, another 'process' tries to mutate."""
        real_write = assimilation._write_corpus
        outcomes = []

        def write(*args, **kwargs):
            try:
                intruder()
                outcomes.append("intruder succeeded")
            except AssimilationError as exc:
                outcomes.append(exc.code)
            return real_write(*args, **kwargs)

        return mock.patch.object(assimilation, "_write_corpus", write), outcomes

    def intruder_add(self):
        loaded = self.loaded()
        add_candidate(self.state, dossier=loaded.dossier, expected_revision=loaded.corpus_revision,
                      value=literal_input("formato", version=2, cls="PROPOSAL", text="Intrusa."))

    def test_decision_window_is_serialized(self):
        patch, outcomes = self.racing_write(self.intruder_add)
        with patch:
            result = self.decide("normas")
        self.assertEqual(outcomes, ["CONFLICT"])
        loaded = self.loaded()
        self.assertEqual(loaded.decisions, (result.decision,))
        self.assertEqual(max(c.version for c in loaded.candidates if c.candidate_id == "formato"), 1)
        self.assertFalse(self.lock.exists())

    def test_closure_window_is_serialized(self):
        self.approve_all()
        patch, outcomes = self.racing_write(self.intruder_add)
        with patch:
            result = self.close()
        self.assertEqual(outcomes, ["CONFLICT"])
        loaded = self.loaded()
        self.assertEqual(loaded.closure, result.closure)
        self.assertEqual(len(loaded.candidates), len(LITERALS))

    def test_add_candidate_window_is_serialized(self):
        loaded = self.loaded()
        patch, outcomes = self.racing_write(lambda: self.decide("normas"))
        with patch:
            add_candidate(self.state, dossier=loaded.dossier,
                          expected_revision=loaded.corpus_revision,
                          value=literal_input("formato", version=2, cls="PROPOSAL", text="Otra."))
        self.assertEqual(outcomes, ["CONFLICT"])
        self.assertEqual(self.loaded().decisions, ())

    def test_stale_lock_blocks_before_prompting(self):
        self.lock.write_bytes(b"")
        before = self.state.read_bytes()
        terminal = FakeTerminal()
        with self.assertRaises(AssimilationError) as ctx:
            self.decide("normas", terminal=terminal)
        self.assertEqual(ctx.exception.code, "CONFLICT")
        self.assertIn(str(self.lock), ctx.exception.reason)
        self.assertEqual(terminal.output, "")
        with self.assertRaises(AssimilationError) as ctx:
            self.add(literal_input("formato", version=2, cls="PROPOSAL", text="Otra."))
        self.assertEqual(ctx.exception.code, "CONFLICT")
        self.assert_unchanged(before)
        self.lock.unlink()
        self.decide("normas")

    def test_lock_is_released_after_failures(self):
        with mock.patch.object(persistence.os, "replace", side_effect=OSError("simulado")):
            with self.assertRaises(AssimilationError):
                self.decide("normas")
        self.assertFalse(self.lock.exists())
        with self.assertRaises(AssimilationError):
            self.decide("normas", terminal=FakeTerminal(transform=lambda p: "no\n"))
        self.assertFalse(self.lock.exists())
        self.decide("normas")
        self.assertFalse(self.lock.exists())


class LockReleaseTest(DecisionCase):
    """REV4C1-04: failing to remove the lock is reported, never silenced."""

    def setUp(self):
        super().setUp()
        self.add_all_literals()
        self.lock = self.state.with_name(self.state.name + ".lock")

    def stubborn_unlink(self):
        real_unlink = assimilation.os.unlink

        def unlink(path, *args, **kwargs):
            if str(path).endswith(".lock"):
                raise PermissionError("bloqueado")
            return real_unlink(path, *args, **kwargs)

        return mock.patch.object(assimilation.os, "unlink", unlink)

    def test_after_a_successful_write(self):
        revision = self.loaded().corpus_revision
        with self.stubborn_unlink():
            with self.assertRaises(AssimilationError) as ctx:
                self.add(literal_input("formato", version=2, cls="PROPOSAL", text="Otra."))
        self.assertEqual(ctx.exception.code, "IO")
        self.assertIn("el cambio se guardó", ctx.exception.reason)
        self.assertIn(str(self.lock), ctx.exception.reason)
        self.assertTrue(self.lock.exists())
        self.lock.unlink()
        self.assertEqual(self.loaded().corpus_revision, revision + 1)

    def test_after_a_failed_write(self):
        before = self.state.read_bytes()
        with self.stubborn_unlink(), \
                mock.patch.object(persistence.os, "replace", side_effect=OSError("simulado")):
            with self.assertRaises(AssimilationError) as ctx:
                self.decide("normas")
        self.assertEqual(ctx.exception.code, "IO")
        self.assertIn("simulado", ctx.exception.reason)
        self.assertIn("no se guardó ningún cambio", ctx.exception.reason)
        self.assertIn(str(self.lock), ctx.exception.reason)
        self.assertIsInstance(ctx.exception.__cause__, AssimilationError)
        self.assertTrue(self.lock.exists())
        self.lock.unlink()
        self.assert_unchanged(before)

    def failing_close(self, really_close: bool):
        real_close = assimilation.os.close
        left_open = []

        def close(fd):
            if really_close:
                real_close(fd)
            else:
                left_open.append(fd)
            raise OSError("cerrar")

        return mock.patch.object(assimilation.os, "close", close), left_open, real_close

    def test_close_error_after_closing_removes_the_lock(self):
        before = self.state.read_bytes()
        patch, _, _ = self.failing_close(really_close=True)
        with patch:
            with self.assertRaises(AssimilationError) as ctx:
                self.add(literal_input("formato", version=2, cls="PROPOSAL", text="Otra."))
        self.assertEqual(ctx.exception.code, "IO")
        self.assertNotIn("bórralo a mano", ctx.exception.reason)
        self.assertFalse(self.lock.exists())
        self.assert_unchanged(before)

    def test_close_failure_that_keeps_the_lock_is_reported(self):
        before = self.state.read_bytes()
        patch, left_open, real_close = self.failing_close(really_close=False)
        try:
            with patch:
                with self.assertRaises(AssimilationError) as ctx:
                    self.add(literal_input("formato", version=2, cls="PROPOSAL", text="Otra."))
        finally:
            for fd in left_open:
                real_close(fd)
        self.assertEqual(ctx.exception.code, "IO")
        self.assert_unchanged(before)
        if self.lock.exists():  # Windows cannot delete a file that is still open
            self.assertIn(str(self.lock), ctx.exception.reason)
            self.lock.unlink()


class BarrierLimitDocumentationTest(unittest.TestCase):
    """REV4C1-02: the accepted limit of barrier A is stated where users and callers look."""

    def test_docstrings_state_the_limit(self):
        for obj in (assimilation.Terminal, assimilation.record_candidate_decision,
                    assimilation.close_assimilation):
            with self.subTest(obj=obj.__name__):
                self.assertIn("does not authenticate", obj.__doc__)

    def test_cli_help_states_the_limit(self):
        import contextlib
        import io

        from core.runtime import cli
        for argv in (["assimilation", "candidate", "--help"], ["assimilation", "--help"]):
            with self.subTest(argv=argv):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertEqual(cli.main(argv), 0)
                help_text = " ".join(out.getvalue().split())
                self.assertIn("no autentica a la persona", help_text)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.main(["assimilation", "candidate", "--help"])
        help_text = " ".join(out.getvalue().split())
        for name in ("approve", "reject"):
            self.assertRegex(help_text, rf"{name} \S+ una versión; .*no autentica a la persona")


class ClosureTest(DecisionCase):
    def test_blocked_while_pending_or_uncovered(self):
        self.add_all_literals()
        with self.assertRaises(AssimilationError) as ctx:
            self.close()
        self.assertIn("faltan decisiones", ctx.exception.reason)
        for candidate_id in LITERALS:
            self.decide(candidate_id, status=REJECTED if candidate_id == "staff" else APPROVED)
        terminal = FakeTerminal()
        with self.assertRaises(AssimilationError) as ctx:
            self.close(terminal)
        self.assertIn("«Revisión del staff» no tiene ningún LITERAL aprobado", ctx.exception.reason)
        self.assertEqual(terminal.output, "")

    def test_uncertainty_does_not_cover_a_section(self):
        for candidate_id in LITERALS:
            if candidate_id != "staff":
                self.add(literal_input(candidate_id))
                self.decide(candidate_id)
        self.add(literal_input("staff", cls="UNCERTAINTY", text="¿Quién aprueba?"))
        self.decide("staff")
        with self.assertRaises(AssimilationError) as ctx:
            self.close()
        self.assertIn("Revisión del staff", ctx.exception.reason)

    def test_superseded_pending_versions_do_not_block(self):
        self.add_all_literals()
        self.add(literal_input("normas", version=2, cls="PROPOSAL", text="Primera idea."))
        self.add(literal_input("normas", version=3))
        self.approve_all_current()
        self.assertTrue(self.close().created)

    def approve_all_current(self):
        for candidate in self.loaded().candidates:
            if candidate.version == max(c.version for c in self.loaded().candidates
                                        if c.candidate_id == candidate.candidate_id):
                self.decide(candidate.candidate_id, candidate.version)

    def test_close_prompt_shape_and_terminal_state(self):
        self.add_all_literals()
        self.add({"candidate_id": "duda", "version": 1, "domain": "WORLD", "class": "UNCERTAINTY",
                  "text": "¿Clima?", "scope": "foro",
                  "citations": [{"dossier_section": "setting", "source_id": "mundo-base",
                                 "source_version": "2", "declared_passage": None,
                                 "quote": "- Costa norte"}]})
        self.add({"candidate_id": "idea", "version": 1, "domain": "RULES", "class": "PROPOSAL",
                  "text": "Idea.", "scope": "foro",
                  "citations": [{"dossier_section": "forum_rules", "source_id": "manual-foro",
                                 "source_version": "1", "declared_passage": "Convivencia",
                                 "quote": "turno"}]})
        self.approve_all()
        self.decide("duda")
        self.decide("idea", status=REJECTED)
        revision = self.loaded().corpus_revision
        terminal = FakeTerminal()
        with mock.patch.object(assimilation.secrets, "choice", side_effect=list("ZZZZ2222")):
            result = self.close(terminal)
        snapshot = result.closure.snapshot_sha256
        self.assertEqual(terminal.output,
                         f"CIERRE HUMANO REQUERIDO\nForo: foro-neutral\nRevisión del corpus: {revision}\n"
                         f"Snapshot SHA-256: {snapshot}\nVigentes: 7; aprobados: 6; rechazados: 1\n"
                         "Rechazados: idea v1\nIncertidumbres: duda v1\n"
                         f"Escribe exactamente: CERRAR foro-neutral r{revision} ZZZZ2222\n> ")
        self.assertEqual((result.created, result.corpus_revision, result.closure.base_revision),
                         (True, revision + 1, revision))
        _, content = load_state(self.state)
        self.assertEqual(set(content["closure"]), {"base_revision", "closure_id", "evidence",
                                                   "receipt", "snapshot_sha256"})
        self.assertEqual(content["closure"]["evidence"]["locator"],
                         "assimilation://foro-neutral/human-decisions/assimilation-closure")
        expected = hashlib.sha256(canonical_json_bytes(
            {"candidates": content["candidates"], "decisions": content["decisions"]},
            pretty=False)).hexdigest()
        self.assertEqual(snapshot, expected)
        self.assertEqual(self.loaded().closure, result.closure)

        before = (self.state.read_bytes(), self.state.stat().st_mtime_ns)
        terminal = FakeTerminal()
        again = self.close(terminal)
        self.assertEqual((again.created, terminal.output), (False, ""))
        self.assertEqual(before, (self.state.read_bytes(), self.state.stat().st_mtime_ns))
        with self.assertRaises(AssimilationError) as ctx:
            self.add(literal_input("normas", version=2, cls="PROPOSAL", text="Tarde."))
        self.assertEqual(ctx.exception.code, "CONFLICT")
        self.assertEqual(self.decide("normas").created, False)

    def test_wrong_close_phrase_writes_nothing(self):
        self.add_all_literals()
        self.approve_all()
        before = self.state.read_bytes()
        with self.assertRaises(AssimilationError):
            self.close(FakeTerminal(transform=lambda p: p.replace("CERRAR", "cerrar") + "\n"))
        self.assert_unchanged(before)

    def test_manipulated_closure_fails_on_load(self):
        self.add_all_literals()
        self.approve_all()
        self.close()
        original = self.state.read_bytes()
        changes = {
            "snapshot": lambda c: c["closure"].update(snapshot_sha256="0" * 64),
            "base revision": lambda c: c["closure"].update(base_revision=0),
            "evidence": lambda c: c["closure"]["evidence"].update(sha256="0" * 64),
            "revision": lambda c: load_state(self.state)[0] + 1,
            "decision removed": lambda c: c["decisions"].pop() and None,
            "candidate added": lambda c: c["candidates"].append(c["candidates"][0]),
        }
        for name, change in changes.items():
            with self.subTest(name):
                self.state.write_bytes(original)
                self.tamper(change)
        self.state.write_bytes(original)
        self.loaded()

    tamper = DecisionTest.tamper


if __name__ == "__main__":
    unittest.main()
