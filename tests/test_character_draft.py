import copy
import dataclasses
import hashlib
import json
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from core.character.models import (
    DRAFT_ID,
    CharacterDraftRecord,
    CharacterDraftView,
    CharacterError,
    CharacterState,
    StaffResponse,
    applied_corpus_refs,
    concept_root,
    decode_character_state,
    draft_record,
    encode_character_content,
    make_draft_record,
    make_staff_response,
    staff_response_record,
)
from core.review.models import (
    DraftLifecycle,
    DraftVersion,
    PublicationStatus,
    ReviewStatus,
    approve,
    mark_stale,
)
from core.runtime import assimilation, character as character_module
from core.runtime.character import (
    create_draft,
    get_draft,
    list_drafts,
    record_staff_response,
)
from core.runtime.instance import approved_corpus
from core.runtime.persistence import encode_state, load_state
from tests.instance_support import ROOT
from tests.test_assimilation_decisions import FakeTerminal
from tests.test_character_proposals import (
    APPROVED,
    RECEIPT,
    REJECTED,
    ProposalCase,
    Resolver,
    concept,
    decide,
    proposal,
    ref,
    sha,
)

OBSERVED = datetime(2026, 10, 12, 18, 30, tzinfo=timezone(timedelta(hours=2)))
LOCATOR = "https://foro.example/t/12#p3"
STAFF_NOTICE = (
    "La persona usuaria declara que ha transcrito esta respuesta y su localizador sobre esta "
    "versión exacta.\n"
    "Este registro no autentica al staff, no cambia la composición y no implica publicación, "
    "canon, aprendizaje ni utilizabilidad.\n"
    "APPROVED acredita aprobación transcrita; REJECTED también abarca rechazo o cambios "
    "solicitados, cuyo detalle queda en la respuesta literal.\n")


def sheet(state: CharacterState, version=1, content="# Ficha\nNombre: Aria\n", forum_id="foro"):
    effective = state.replay.effective
    return make_draft_record(forum_id=forum_id, character_id="aria", version=version,
                             created_revision=state.revision + 1,
                             composition_sha256=effective.composition_sha256,
                             concept=state.current_concept(),
                             corpus_refs=applied_corpus_refs(effective), content=content)


def staff(record, revision, status=APPROVED, response="Aprobada, bienvenida.", locator=LOCATOR,
          observed=OBSERVED):
    return make_staff_response(character_id="aria", record=record, review_revision=revision,
                               review_status=status, response=response, locator=locator,
                               observed_at=observed, receipt=RECEIPT)


def with_events(state: CharacterState, **changes) -> CharacterState:
    return dataclasses.replace(state, **changes)


class ChainMixin:
    def setUp(self):
        self.c1, self.c2 = concept(), concept(2, "# Aria\nSegunda.\n")
        root = concept_root("aria", self.c1)
        self.a = proposal(root, 2, "a", text="Texto A\n")
        after_a = CharacterState("aria", (self.c1,), (self.a,), (decide(self.a, 3),))
        self.b = proposal(after_a.replay.effective, 4, "b", text="Texto B\n",
                          citations=(ref("mundo", 1), ref()))
        self.state = CharacterState("aria", (self.c1,), (self.a, self.b),
                                    (decide(self.a, 3), decide(self.b, 5)))


class DraftModelTest(ChainMixin, unittest.TestCase):
    def test_record_shape_refs_and_hash(self):
        record = sheet(self.state)
        effective = self.state.replay.effective
        self.assertEqual([r.key for r in record.corpus_refs], [("normas", 3), ("mundo", 1)])
        draft = record.draft
        self.assertEqual((draft.draft_id, draft.lifecycle, draft.review_status,
                          draft.publication_status),
                         (DRAFT_ID, DraftLifecycle.ACTIVE, ReviewStatus.PENDING_HUMAN_REVIEW,
                          PublicationStatus.NOT_CONFIRMED))
        self.assertEqual(draft.source_refs[0], self.c1.evidence)
        self.assertEqual(draft.context_refs, (
            f"character:aria:composition:{effective.composition_sha256}",
            f"character:aria:concept:v1:{self.c1.concept_sha256}",
            f"corpus:normas:v3:{'1' * 64}", f"corpus:mundo:v1:{'2' * 64}"))
        persisted = draft_record(record)
        self.assertEqual(set(persisted), {
            "composition_sha256", "concept", "content", "context_refs", "corpus_refs",
            "created_revision", "draft_id", "draft_sha256", "lifecycle", "publication_evidence",
            "publication_status", "review_evidence", "review_status", "source_refs",
            "stale_reason", "utf8_size", "version"})
        self.assertEqual(persisted["source_refs"][1], {
            "ic_date": None, "locator": "instance://foro/corpus/candidates/normas/v3",
            "observed_at": None, "section_or_passage": "candidate:normas:v3",
            "sha256": "1" * 64, "source_id": "corpus-candidate:normas:v3"})
        core = {k: v for k, v in persisted.items() if k != "draft_sha256"}
        self.assertEqual(record.draft_sha256, sha(core))
        self.assertEqual(persisted["created_revision"], 6)
        odd = sheet(self.state, forum_id="foro/ñ")
        self.assertEqual(odd.draft.source_refs[1].locator,
                         "instance://foro%2F%C3%B1/corpus/candidates/normas/v3")

    def test_content_kept_exactly(self):
        for text in ("Ñandú «ü» 🌊\n", "línea\r\notra\r\n", "sin salto final"):
            with self.subTest(text=text):
                record = sheet(self.state, content=text)
                self.assertEqual((record.draft.content, record.utf8_size),
                                 (text, len(text.encode())))
        for text in ("", " \n", "\ufeffhola", "hola\x07", "a\x00b"):
            with self.subTest(text=text):
                with self.assertRaises(CharacterError):
                    sheet(self.state, content=text)

    def test_record_validation_and_immutability(self):
        record = sheet(self.state)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            record.composition_sha256 = "0" * 64
        draft = record.draft
        bad_drafts = {
            "other draft id": dataclasses.replace(draft, draft_id="otra"),
            "already approved": approve(draft, 1, self.c1.evidence),
            "other context": dataclasses.replace(draft, context_refs=draft.context_refs[:-1]),
            "other sources": dataclasses.replace(draft, source_refs=draft.source_refs[:-1]),
        }
        for name, bad in bad_drafts.items():
            with self.subTest(name):
                with self.assertRaises(CharacterError):
                    CharacterDraftRecord("aria", "foro", 6, record.composition_sha256,
                                         record.concept, record.corpus_refs, bad)
        with self.assertRaises(CharacterError):
            CharacterDraftRecord("aria", "foro", 6, record.composition_sha256, record.concept,
                                 record.corpus_refs * 2, draft)
        with self.assertRaises(CharacterError):
            make_draft_record(forum_id="foro", character_id="aria", version=0,
                              created_revision=6, composition_sha256=record.composition_sha256,
                              concept=self.c1, corpus_refs=(), content="x")

    def test_staff_response_shape_and_validation(self):
        record = sheet(self.state)
        response = staff(record, 7, response="Línea\r\nsin final")
        persisted = staff_response_record(response)
        self.assertEqual(set(persisted), {
            "composition_sha256", "draft_id", "draft_sha256", "draft_version", "evidence",
            "receipt", "response", "response_sha256", "review_revision", "review_status",
            "staff_review_sha256"})
        self.assertEqual(response.response_sha256,
                         hashlib.sha256("Línea\r\nsin final".encode()).hexdigest())
        self.assertEqual(persisted["evidence"], {
            "ic_date": None, "locator": LOCATOR, "observed_at": "2026-10-12T18:30:00+02:00",
            "section_or_passage": "character-sheet:aria:v1",
            "sha256": response.response_sha256, "source_id": "staff-response:aria:v1"})
        core = {k: v for k, v in persisted.items() if k != "staff_review_sha256"}
        self.assertEqual(response.staff_review_sha256, sha(core))
        bad = {
            "pending": dict(status=ReviewStatus.PENDING_HUMAN_REVIEW),
            "string status": dict(status="APPROVED"),
            "locator newline": dict(locator="a\nb"),
            "locator tab": dict(locator="a\tb"),
            "empty locator": dict(locator=" "),
            "naive date": dict(observed=datetime(2026, 10, 12, 18, 30)),
            "empty response": dict(response=""),
        }
        for name, kwargs in bad.items():
            with self.subTest(name):
                with self.assertRaises(CharacterError):
                    staff(record, 7, **kwargs)
        with self.assertRaises(CharacterError):
            dataclasses.replace(response, evidence=dataclasses.replace(
                response.evidence, source_id="staff-response:aria:v2"))


class DraftReplayTest(ChainMixin, unittest.TestCase):
    def test_pending_then_staff_response_never_changes_the_composition(self):
        record = sheet(self.state)
        pending = with_events(self.state, drafts=(record,))
        view = pending.replay.draft_views[0]
        self.assertEqual((view.current, view.effective.lifecycle, view.effective.review_status),
                         (True, DraftLifecycle.ACTIVE, ReviewStatus.PENDING_HUMAN_REVIEW))
        self.assertEqual(view.base, self.state.replay.effective)
        for status in (APPROVED, REJECTED):
            with self.subTest(status=status):
                response = staff(record, 7, status)
                decided = with_events(pending, staff_responses=(response,))
                view = decided.replay.draft_views[0]
                self.assertEqual((view.effective.review_status, view.effective.review_evidence),
                                 (status, response.evidence))
                self.assertEqual(view.effective.publication_status,
                                 PublicationStatus.NOT_CONFIRMED)
                self.assertEqual(decided.replay.effective, self.state.replay.effective)
                self.assertEqual(decided.revision, 7)
                self.assertIs(decided.staff_response_for(record), response)

    def test_stale_by_composition_and_by_supersession(self):
        record = sheet(self.state)
        old = self.state.replay.effective.composition_sha256
        with_draft = with_events(self.state, drafts=(record,))
        c = proposal(self.state.replay.effective, 7, "c", text="Texto C\n")
        changed = with_events(with_draft, proposals=(*with_draft.proposals, c),
                              proposal_decisions=(*with_draft.proposal_decisions, decide(c, 8)))
        view = changed.replay.draft_views[0]
        self.assertEqual(view.effective.stale_reason,
                         f"EFFECTIVE_COMPOSITION_CHANGED:{old}->"
                         f"{changed.replay.effective.composition_sha256}")
        self.assertEqual(changed.revision, 8)
        v2 = sheet(changed, 2)
        late = staff(record, 10, APPROVED)
        both = with_events(changed, drafts=(record, v2), staff_responses=(late,))
        first, second = both.replay.draft_views
        self.assertEqual((first.current, first.effective.lifecycle, first.effective.stale_reason,
                          first.effective.review_status),
                         (False, DraftLifecycle.STALE, "SUPERSEDED_BY:character-sheet:v2",
                          APPROVED))
        self.assertEqual((second.current, second.effective.lifecycle), (True,
                                                                        DraftLifecycle.ACTIVE))
        self.assertIs(both.current_draft(), v2)
        concept_changed = with_events(with_draft, concepts=(self.c1, self.c2))
        self.assertEqual(concept_changed.replay.draft_views[0].effective.lifecycle,
                         DraftLifecycle.STALE)

    def test_invalid_logs(self):
        record = sheet(self.state)
        root_state = CharacterState("aria", (self.c1,))
        stale_record = make_draft_record(
            forum_id="foro", character_id="aria", version=1, created_revision=6,
            composition_sha256=root_state.replay.effective.composition_sha256, concept=self.c1,
            corpus_refs=(), content="x")
        no_refs = make_draft_record(
            forum_id="foro", character_id="aria", version=1, created_revision=6,
            composition_sha256=record.composition_sha256, concept=self.c1, corpus_refs=(),
            content="x")
        other_evidence = make_draft_record(
            forum_id="foro", character_id="aria", version=1, created_revision=6,
            composition_sha256=record.composition_sha256, concept=self.c2,
            corpus_refs=record.corpus_refs, content="x")
        cases = {
            "old composition": dict(drafts=(stale_record,)),
            "missing corpus refs": dict(drafts=(no_refs,)),
            "other concept evidence": dict(drafts=(other_evidence,)),
            "version skip": dict(drafts=(sheet(self.state, 2),)),
            "response before its sheet": dict(drafts=(sheet(self.state),),
                                              staff_responses=(staff(record, 6),)),
            "two responses": dict(drafts=(record,), staff_responses=(staff(record, 7),
                                                                     staff(record, 8))),
            "response to other text": dict(drafts=(record,), staff_responses=(
                staff(sheet(self.state, content="otra"), 7),)),
            "duplicate revision": dict(drafts=(record, dataclasses.replace(
                sheet(self.state, 2), ))),
        }
        for name, changes in cases.items():
            with self.subTest(name):
                with self.assertRaises(CharacterError):
                    with_events(self.state, **changes)

    def test_views_reject_incoherent_derivations(self):
        record = sheet(self.state)
        base = self.state.replay.effective
        response = staff(record, 7)
        with self.assertRaises(CharacterError):
            CharacterDraftView(record, record.draft, response, True, base)
        with self.assertRaises(CharacterError):
            CharacterDraftView(record, record.draft, None, False, base)
        with self.assertRaises(CharacterError):
            CharacterDraftView(record, record.draft, None, True,
                               concept_root("aria", self.c1))
        CharacterDraftView(record, approve(record.draft, 1, response.evidence), response, True,
                           base)

    def test_views_reject_impossible_stale_reasons(self):
        record = sheet(self.state)
        base = self.state.replay.effective
        own = record.composition_sha256
        other = "f" * 64
        invalid = [
            (True, f"SUPERSEDED_BY:{DRAFT_ID}:v999"),
            (False, "SUPERSEDED_BY:otro:v2"),
            (False, f"SUPERSEDED_BY:{DRAFT_ID}:v1"),
            (False, f"SUPERSEDED_BY:{DRAFT_ID}:v02"),
            (False, f"EFFECTIVE_COMPOSITION_CHANGED:{own}->{other}"),
            (True, "motivo arbitrario"),
            (True, f"EFFECTIVE_COMPOSITION_CHANGED:{other}->{own}"),
            (True, f"EFFECTIVE_COMPOSITION_CHANGED:{own}->{own}"),
            (True, f"EFFECTIVE_COMPOSITION_CHANGED:{own}->{'F' * 64}"),
        ]
        for current, reason in invalid:
            with self.subTest(current=current, reason=reason):
                with self.assertRaises(CharacterError):
                    CharacterDraftView(record, mark_stale(record.draft, reason), None, current,
                                       base)
        for current, reason in ((False, f"SUPERSEDED_BY:{DRAFT_ID}:v2"),
                                (True, f"EFFECTIVE_COMPOSITION_CHANGED:{own}->{other}")):
            CharacterDraftView(record, mark_stale(record.draft, reason), None, current, base)


class DraftCodecTest(ChainMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        record = sheet(self.state)
        self.full = with_events(self.state, drafts=(record,),
                                staff_responses=(staff(record, 7, REJECTED,
                                                       "Cambios solicitados:\r\n- edad"),))
        self.content = encode_character_content(self.full)

    def decode(self, content, revision=7):
        return decode_character_state(content, forum_id="foro", revision=revision,
                                      candidate_resolver=Resolver())

    def test_four_or_six_keys(self):
        self.assertEqual(set(encode_character_content(self.state)),
                         {"character_id", "concepts", "proposal_decisions", "proposals"})
        self.assertEqual(set(self.content) - set(encode_character_content(self.state)),
                         {"drafts", "staff_responses"})
        self.assertEqual(self.decode(self.content), self.full)
        data = encode_state(self.content, revision=7)
        self.assertEqual(encode_state(encode_character_content(self.decode(self.content)),
                                      revision=7), data)
        five = {k: v for k, v in self.content.items() if k != "staff_responses"}
        empty = dict(encode_character_content(self.state), drafts=[], staff_responses=[])
        for name, content in {"five keys": five, "six empty": empty,
                              "extra": dict(self.content, extra=[])}.items():
            with self.subTest(name):
                with self.assertRaises(CharacterError):
                    self.decode(content, revision=7 if name != "six empty" else 5)

    def test_every_tampering_is_rejected(self):
        draft = lambda c: c["drafts"][0]  # noqa: E731
        response = lambda c: c["staff_responses"][0]  # noqa: E731
        changes = {
            "content": lambda c: draft(c).update(content="otra"),
            "draft hash": lambda c: draft(c).update(draft_sha256="0" * 64),
            "lifecycle": lambda c: draft(c).update(lifecycle="STALE"),
            "review status": lambda c: draft(c).update(review_status="APPROVED"),
            "publication": lambda c: draft(c).update(publication_status="PUBLISHED"),
            "stale reason": lambda c: draft(c).update(stale_reason="x"),
            "source locator": lambda c: draft(c)["source_refs"][1].update(locator="x://y"),
            "context": lambda c: draft(c)["context_refs"].pop(),
            "corpus hash": lambda c: draft(c)["corpus_refs"][0].update(candidate_sha256="3" * 64),
            "corpus order": lambda c: draft(c)["corpus_refs"].reverse(),
            "created revision": lambda c: draft(c).update(created_revision=5),
            "size": lambda c: draft(c).update(utf8_size=1),
            "draft id": lambda c: draft(c).update(draft_id="otra"),
            "unknown concept": lambda c: draft(c)["concept"].update(version=9),
            "response text": lambda c: response(c).update(response="otra"),
            "response hash": lambda c: response(c).update(response_sha256="0" * 64),
            "record hash": lambda c: response(c).update(staff_review_sha256="0" * 64),
            "response status": lambda c: response(c).update(review_status="APPROVED"),
            "evidence locator": lambda c: response(c)["evidence"].update(locator="otra"),
            "non canonical date": lambda c: response(c)["evidence"].update(
                observed_at="2026-10-12T18:30:00.000+02:00"),
            "naive date": lambda c: response(c)["evidence"].update(
                observed_at="2026-10-12T18:30:00"),
            "receipt": lambda c: response(c)["receipt"].update(method="OTRO"),
            "review revision": lambda c: response(c).update(review_revision=6),
            "unknown draft": lambda c: response(c).update(draft_version=2),
            "draft sha in response": lambda c: response(c).update(draft_sha256="0" * 64),
        }
        for name, change in changes.items():
            with self.subTest(name):
                content = copy.deepcopy(self.content)
                change(content)
                with self.assertRaises(CharacterError):
                    self.decode(content)

    def test_revision_sums_the_five_histories(self):
        for revision in (6, 8):
            with self.assertRaises(CharacterError):
                self.decode(self.content, revision=revision)
        self.assertNotIn("PUBLISHED", json.dumps(self.content))


class DraftCase(ProposalCase):
    def write_sheet(self, text="# Ficha\nNombre: Aria\n", name="ficha.md"):
        path = self.root / name
        path.write_bytes(text.encode("utf-8"))
        return path

    def create(self, version=1, composition=None, text="# Ficha\nNombre: Aria\n",
               name="ficha.md", input_path=None):
        return create_draft(self.instance, expected_core_root=ROOT, character_id="aria",
                            version=version,
                            composition_sha256=composition or self.effective().composition_sha256,
                            input_path=input_path or self.write_sheet(text, name))

    def write_response(self, draft_sha256=None, locator=LOCATOR,
                       observed_at="2026-10-12T18:30:00+02:00", response="Aprobada.",
                       name="respuesta.json", raw=None, version=1):
        path = self.root / name
        if raw is None:
            raw = json.dumps({
                "draft_sha256": draft_sha256 or self.draft(version).record.draft_sha256,
                "locator": locator, "observed_at": observed_at, "response": response,
            }, ensure_ascii=False).encode("utf-8")
        path.write_bytes(raw)
        return path

    def record(self, version=1, status=APPROVED, terminal=None, input_path=None, **kwargs):
        return record_staff_response(
            self.instance, expected_core_root=ROOT, character_id="aria", version=version,
            review_status=status, input_path=input_path or self.write_response(
                version=version, **kwargs),
            terminal=terminal or FakeTerminal())

    def draft(self, version=1):
        return get_draft(self.loaded(), character_id="aria", version=version)


class DraftCreateTest(DraftCase):
    def test_create_persists_and_changes_nothing_else(self):
        effective = self.effective()
        result = self.create(text="Ñ\r\nsin final")
        self.assertTrue(result.created)
        self.assertEqual(result.character.state_revision, 2)
        view = self.draft()
        self.assertEqual((view.current, view.effective.lifecycle, view.effective.review_status,
                          view.effective.publication_status, view.record.corpus_refs,
                          view.effective.content),
                         (True, DraftLifecycle.ACTIVE, ReviewStatus.PENDING_HUMAN_REVIEW,
                          PublicationStatus.NOT_CONFIRMED, (), "Ñ\r\nsin final"))
        _, content = load_state(self.state_path())
        self.assertEqual(content["drafts"], [draft_record(view.record)])
        self.assertEqual(content["staff_responses"], [])
        self.assertEqual(self.effective(), effective)
        self.assertFalse(self.lock_path().exists())

    def test_refs_come_only_from_applied_proposals(self):
        self.add(proposal_id="a", text="A\n", citations=(("normas", 3),))
        self.decide("a")
        self.add(proposal_id="b", text="B\n", citations=(("duda", 1), ("normas", 3)))
        self.decide("b")
        self.add(proposal_id="pendiente", text="P\n", citations=(("mundo", 1),))
        self.create()
        corpus = {e.candidate.key: e.candidate.candidate_sha256
                  for e in approved_corpus(self.loaded())}
        refs = self.draft().record.corpus_refs
        self.assertEqual([(r.key, r.candidate_sha256) for r in refs],
                         [(("normas", 3), corpus[("normas", 3)]),
                          (("duda", 1), corpus[("duda", 1)])])

    def test_retry_is_idempotent_even_after_the_composition_changes(self):
        self.create()
        composition = self.draft().record.composition_sha256
        data = self.state_path().read_bytes()
        mtime = os.stat(self.state_path()).st_mtime_ns
        with mock.patch.object(character_module, "_corpus_lock") as lock:
            self.assertFalse(self.create(composition=composition).created)
        lock.assert_not_called()
        self.assertEqual((self.state_path().read_bytes(), os.stat(self.state_path()).st_mtime_ns),
                         (data, mtime))
        self.add(text="Otra\n")
        self.decide()
        self.assertFalse(self.create(composition=composition).created)

    def test_conflicts_and_input_errors(self):
        self.create()
        composition = self.draft().record.composition_sha256
        conflicts = {
            "same version other text": dict(composition=composition, text="Otra\n"),
            "version skip": dict(version=3, text="Otra\n"),
            "stale composition": dict(version=2, composition="0" * 64, text="Otra\n"),
            "repeats previous": dict(version=2),
        }
        for name, kwargs in conflicts.items():
            with self.subTest(name):
                with self.assertRaises(CharacterError) as ctx:
                    self.create(**kwargs)
                self.assertEqual(ctx.exception.code, "CONFLICT")
        invalid = {
            "bad hash": dict(version=2, composition="ABC"),
            "version zero": dict(version=0),
            "empty": dict(version=2, text=" \n"),
            "control": dict(version=2, text="a\x07"),
            "bom": dict(version=2, text="\ufeffhola"),
        }
        for name, kwargs in invalid.items():
            with self.subTest(name):
                with self.assertRaises(CharacterError) as ctx:
                    self.create(**kwargs)
                self.assertEqual(ctx.exception.code, "INVALID_STATE")
        current = self.effective().composition_sha256
        inside = self.instance / "ficha.md"
        inside.write_bytes(b"x\n")
        for path in (inside, ROOT / "README.md", self.root / "no-existe.md"):
            with self.subTest(path=path.name):
                with self.assertRaises(CharacterError):
                    self.create(version=2, composition=current, input_path=path)
        inside.unlink()
        with self.assertRaises(CharacterError) as ctx:
            create_draft(self.instance, expected_core_root=ROOT, character_id="nadie",
                         version=1, composition_sha256="0" * 64, input_path=self.write_sheet())
        self.assertEqual(ctx.exception.code, "INVALID_STATE")
        self.assertEqual(len(list_drafts(self.loaded(), character_id="aria")), 1)

    def test_lifecycle_on_disk(self):
        self.create()
        revision = self.loaded().characters[0].state_revision
        self.add(text="Otra\n")
        self.decide()
        self.assertEqual(self.draft().effective.lifecycle, DraftLifecycle.STALE)
        self.assertTrue(self.draft().effective.stale_reason.startswith(
            "EFFECTIVE_COMPOSITION_CHANGED:"))
        self.assertEqual(self.loaded().characters[0].state_revision, revision + 2)
        self.create(version=2, text="# Ficha v2\n")
        self.assertEqual(self.draft().effective.stale_reason, "SUPERSEDED_BY:character-sheet:v2")
        self.import_concept(2, "# Aria\nOtra base.\n")
        self.assertEqual([(v.version, v.current, v.effective.lifecycle)
                          for v in list_drafts(self.loaded(), character_id="aria")],
                         [(1, False, DraftLifecycle.STALE), (2, True, DraftLifecycle.STALE)])
        _, content = load_state(self.state_path())
        self.assertEqual([d["lifecycle"] for d in content["drafts"]], ["ACTIVE", "ACTIVE"])

    def test_concurrent_create_is_not_lost(self):
        real_lock = character_module._corpus_lock
        competitor = []

        def racing_lock(state_path, subject, guard=None):
            if not competitor:
                competitor.append(True)
                self.add(proposal_id="otra", text="Del otro proceso\n")
            return real_lock(state_path, subject, guard=guard)

        with mock.patch.object(character_module, "_corpus_lock", racing_lock):
            with self.assertRaises(CharacterError) as ctx:
                self.create()
        self.assertEqual(ctx.exception.code, "CONFLICT")
        self.assertEqual(list_drafts(self.loaded(), character_id="aria"), ())


class StaffRecordTest(DraftCase):
    def expected_prompt(self, view, status, response, citations=()):
        record = view.record
        data = response.encode("utf-8")
        content = record.draft.content
        shown = response if response.endswith("\n") else response + "\n"
        return (
            "REGISTRO HUMANO DE RESPUESTA ATRIBUIDA AL STAFF\n"
            "Personaje: aria\n"
            f"Ficha: character-sheet v{record.version}\n"
            f"Vigencia actual: {view.effective.lifecycle.value}\n"
            f"Resultado transcrito: {status}\n"
            f"Ficha SHA-256: {record.draft_sha256}\n"
            f"Composición citada SHA-256: {record.composition_sha256}\n"
            f"Respuesta SHA-256: {hashlib.sha256(data).hexdigest()}\n"
            f"Respuesta bytes UTF-8: {len(data)}\n"
            f"Locator declarado: {LOCATOR}\n"
            "Observada en: 2026-10-12T18:30:00+02:00\n"
            f"Concepto citado: v1 | sha256={record.concept.concept_sha256} | "
            f"evidencia={record.draft.source_refs[0].sha256}\n"
            f"Corpus citado ({len(citations)}):\n"
            + "".join(f"Cita {i}: {c} | APPROVED\n" for i, c in enumerate(citations, start=1))
            + "FICHA CITADA — texto exacto (hasta «Fin de la ficha citada.»):\n"
            f"{content if content.endswith(chr(10)) else content + chr(10)}"
            "Fin de la ficha citada.\n"
            "RESPUESTA TRANSCRITA — texto exacto (hasta «Fin de la respuesta.»):\n"
            f"{shown}"
            "Fin de la respuesta.\n"
            + STAFF_NOTICE)

    def test_record_prompt_and_state(self):
        self.add(text="A\n", citations=(("normas", 3),))
        self.decide()
        self.create(text="Ficha sin salto final")
        view = self.draft()
        effective = self.effective()
        normas = next(e.candidate for e in approved_corpus(self.loaded())
                      if e.candidate.key == ("normas", 3))
        terminal = FakeTerminal()
        response = "Aprobada «sí».\r\nBienvenida"
        result = self.record(terminal=terminal, response=response)
        prompt, phrase_line = terminal.output.rsplit("Escribe exactamente: ", 1)
        self.assertEqual(prompt, self.expected_prompt(
            view, "APPROVED", response,
            (f"normas v3 | sha256={normas.candidate_sha256}",)))
        self.assertRegex(phrase_line,
                         r"^REGISTRAR-RESPUESTA-STAFF APPROVED character-sheet v1 "
                         r"[A-HJ-NP-Z2-9]{8}\n> $")
        self.assertEqual(result.response.receipt.confirmation_sha256,
                         hashlib.sha256(phrase_line[:-3].encode()).hexdigest())
        self.assertTrue(result.created)
        self.assertEqual((result.draft.effective.review_status,
                          result.draft.effective.publication_status),
                         (ReviewStatus.APPROVED, PublicationStatus.NOT_CONFIRMED))
        self.assertEqual(self.effective(), effective)
        _, content = load_state(self.state_path())
        self.assertEqual(content["staff_responses"], [staff_response_record(result.response)])
        self.assertEqual(content["staff_responses"][0]["review_revision"],
                         result.character.state_revision)

    def test_zero_citations_changes_requested_and_late_response(self):
        self.create()
        self.add(text="Otra\n")
        self.decide()
        view = self.draft()
        self.assertEqual(view.effective.lifecycle, DraftLifecycle.STALE)
        terminal = FakeTerminal()
        text = "Cambios solicitados:\n- revisa la edad\n"
        result = self.record(status=REJECTED, terminal=terminal, response=text)
        self.assertEqual(terminal.output.rsplit("Escribe exactamente: ", 1)[0],
                         self.expected_prompt(view, "REJECTED", text))
        self.assertIn("Corpus citado (0):\nFICHA CITADA", terminal.output)
        self.assertEqual((result.draft.effective.review_status,
                          result.draft.effective.lifecycle),
                         (ReviewStatus.REJECTED, DraftLifecycle.STALE))

    def test_retry_and_conflicting_responses(self):
        self.create()
        self.record()
        data = self.state_path().read_bytes()
        terminal = FakeTerminal()
        again = self.record(terminal=terminal)
        self.assertEqual((again.created, terminal.output), (False, ""))
        self.assertEqual(self.state_path().read_bytes(), data)
        for kwargs in (dict(status=REJECTED), dict(response="Otra respuesta"),
                       dict(locator="https://foro.example/otro"),
                       dict(observed_at="2026-10-13T09:00:00+02:00")):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(CharacterError) as ctx:
                    self.record(**kwargs)
                self.assertEqual(ctx.exception.code, "CONFLICT")
        self.assertEqual(self.state_path().read_bytes(), data)

    def test_input_rules(self):
        self.create()
        good = json.loads(self.write_response().read_bytes())
        invalid = {
            "extra key": json.dumps({**good, "staff": "x"}).encode(),
            "missing key": json.dumps({k: v for k, v in good.items() if k != "locator"}).encode(),
            "duplicate key": b'{"response": "a", "response": "b"}',
            "bom": b"\xef\xbb\xbf" + json.dumps(good).encode(),
            "bad hash": json.dumps({**good, "draft_sha256": "XYZ"}).encode(),
            "naive date": json.dumps({**good, "observed_at": "2026-10-12T18:30:00"}).encode(),
            "non canonical date": json.dumps(
                {**good, "observed_at": "2026-10-12T18:30:00.000+02:00"}).encode(),
            "date text": json.dumps({**good, "observed_at": "ayer"}).encode(),
            "locator newline": json.dumps({**good, "locator": "a\nb"}).encode(),
            "empty response": json.dumps({**good, "response": " "}).encode(),
            "control response": json.dumps({**good, "response": "a\u0007"}).encode(),
        }
        for name, raw in invalid.items():
            with self.subTest(name):
                terminal = FakeTerminal()
                with self.assertRaises(CharacterError) as ctx:
                    self.record(terminal=terminal, raw=raw)
                self.assertEqual(ctx.exception.code, "INVALID_STATE")
                self.assertEqual(terminal.output, "")
        with self.assertRaises(CharacterError) as ctx:
            self.record(draft_sha256="0" * 64)
        self.assertEqual(ctx.exception.code, "CONFLICT")
        for kwargs in (dict(version=2), dict(status=ReviewStatus.PENDING_HUMAN_REVIEW)):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(CharacterError):
                    self.record(input_path=self.write_response(), **kwargs)
        inside = self.instance / "respuesta.json"
        inside.write_bytes(self.write_response().read_bytes())
        with self.assertRaises(CharacterError):
            self.record(input_path=inside)
        inside.unlink()
        self.assertIsNone(self.draft().staff_response)

    def test_answer_rules_write_nothing(self):
        self.create()
        data = self.state_path().read_bytes()
        for name, transform in {"lowercase": lambda p: p.lower() + "\n",
                                "extra space": lambda p: p + " \n",
                                "eof": lambda p: None}.items():
            with self.subTest(name):
                with self.assertRaises(CharacterError):
                    self.record(terminal=FakeTerminal(transform=transform))
        terminal = FakeTerminal(interactive=False)
        with self.assertRaises(CharacterError):
            self.record(terminal=terminal)
        self.assertEqual(terminal.output, "")

        def interrupt():
            raise KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            self.record(terminal=FakeTerminal(on_read=interrupt))
        self.assertEqual(self.state_path().read_bytes(), data)
        self.assertFalse(self.lock_path().exists())

    def test_changes_during_the_prompt_are_conflicts(self):
        self.create()
        path = self.write_response()

        def change_input():
            path.write_bytes(path.read_bytes().replace(b"Aprobada.", b"Aprobada!"))

        with self.assertRaises(CharacterError) as ctx:
            self.record(input_path=path, terminal=FakeTerminal(on_read=change_input))
        self.assertEqual(ctx.exception.code, "CONFLICT")

        def change_state():
            self.add(proposal_id="otra", text="Concurrente\n")

        with self.assertRaises(CharacterError) as ctx:
            self.record(terminal=FakeTerminal(on_read=change_state))
        self.assertEqual(ctx.exception.code, "CONFLICT")
        self.assertIsNone(self.draft().staff_response)

    def test_locks_failed_replace_and_release(self):
        self.create()
        self.lock_path().write_bytes(b"")
        terminal = FakeTerminal()
        with self.assertRaises(CharacterError) as ctx:
            self.record(terminal=terminal)
        self.assertEqual((ctx.exception.code, terminal.output), ("CONFLICT", ""))
        with self.assertRaises(CharacterError) as ctx:
            self.create(version=2, text="Otra\n")
        self.assertEqual(ctx.exception.code, "CONFLICT")
        self.lock_path().unlink()
        from core.runtime import persistence
        before = self.state_path().read_bytes()
        with mock.patch.object(persistence.os, "replace", side_effect=OSError("simulado")):
            with self.assertRaises(CharacterError) as ctx:
                self.record()
        self.assertEqual(ctx.exception.code, "IO")
        self.assertEqual(self.state_path().read_bytes(), before)
        self.assertFalse(self.lock_path().exists())
        real_unlink = assimilation.os.unlink

        def stubborn(path, *args, **kwargs):
            if str(path).endswith(".lock"):
                raise PermissionError("bloqueado")
            return real_unlink(path, *args, **kwargs)

        with mock.patch.object(assimilation.os, "unlink", stubborn):
            with self.assertRaises(CharacterError) as ctx:
                self.record()
        self.assertEqual(ctx.exception.code, "IO")
        self.assertIn("el cambio se guardó", ctx.exception.reason)
        self.lock_path().unlink()
        self.assertEqual(self.draft().effective.review_status, ReviewStatus.APPROVED)

    @unittest.skipUnless(os.name == "nt", "las junctions son de Windows")
    def test_junction_swap_when_taking_the_lock_writes_nothing_outside(self):
        import _winapi
        self.create()
        real_lock = character_module._corpus_lock
        folder = self.instance / "characters" / "aria"
        for name, action in (("record", lambda: self.record()),
                             ("create", lambda: self.create(version=2, text="Otra\n"))):
            with self.subTest(name):
                aside = self.root / f"fuera-{name}"

                def racing_lock(state_path, subject, guard=None):
                    folder.rename(aside)
                    _winapi.CreateJunction(str(aside), str(folder))
                    return real_lock(state_path, subject, guard=guard)

                with mock.patch.object(character_module, "_corpus_lock", racing_lock):
                    with self.assertRaises(CharacterError) as ctx:
                        action()
                self.assertEqual(ctx.exception.code, "UNSAFE_DESTINATION")
                self.assertEqual(sorted(p.name for p in aside.iterdir()), ["state.json"])
                self.assertEqual(load_state(aside / "state.json")[0], 2)
                os.rmdir(folder)
                aside.rename(folder)


if __name__ == "__main__":
    unittest.main()
