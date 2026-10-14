import dataclasses
import hashlib
import json
import subprocess
import sys
import typing
import unittest
from datetime import datetime, timedelta, timezone

from core.character.models import CorpusCandidateRef
from core.memory.narrative import (
    CharacterSheetRef,
    DraftPublication,
    ExternalPost,
    HumanSeed,
    NarrativeDraftRecord,
    NarrativeDraftView,
    NarrativeError,
    NarrativePublication,
    PostAuthor,
    PostRef,
    SeedMode,
    TopicHeader,
    TopicState,
    check_label,
    check_narrative_id,
    context_sha256,
    decode_topic_state,
    draft_record,
    encode_topic_content,
    external_record,
    make_external_post,
    make_publication,
    make_seed,
    narrative_draft_summary,
    post_summary,
    publication_record,
    seed_payload,
    seed_record,
    seed_summary,
    text_sha256,
    topic_summary,
)
from core.memory.provenance import SourceRef
from core.review.models import DraftLifecycle
from core.runtime.assimilation import HUMAN_CONFIRMATION_METHOD, HumanConfirmationReceipt
from core.runtime.narrative import PublicationPort, PublicationReceipt, PublicationRequest
from core.runtime.persistence import canonical_json_bytes
from tests.instance_support import ROOT

RECEIPT = HumanConfirmationReceipt(HUMAN_CONFIRMATION_METHOD, "a" * 64)
OBSERVED = datetime(2026, 10, 14, 20, 0, tzinfo=timezone(timedelta(hours=2)))
H = "b" * 64


def digest(value):
    return hashlib.sha256(canonical_json_bytes(value, pretty=False)).hexdigest()


def external(post_id="respuesta-1", position=1, revision=2, content="Texto ajeno\n",
             author="otro participante", locator="https://foro.example/t/1#p1"):
    return make_external_post(topic_id="escena", post_id=post_id, position=position,
                              created_revision=revision, author_label=author, content=content,
                              locator=locator, observed_at=OBSERVED, receipt=RECEIPT)


def seed(context=(), revision=2, version=1, **changes):
    fields = {"intent": "Presentarse", "tone": "Sereno", "beats": ("Llega",), "details": (),
              "ooc_constraints": ("No decidir por otros",), "pending_outcomes": ()}
    fields.update(changes)
    return make_seed(forum_id="foro", topic_id="escena", seed_id="turno-1", version=version,
                     created_revision=revision, context=context, receipt=RECEIPT, **fields)


def sheet(composition=H):
    return CharacterSheetRef(1, "c" * 64, composition, "d" * 64)


def draft(seed_value, revision=3, text="Aria cruza la plaza.\n", citations=(), version=1,
          draft_id="turno-1", target=None, **changes):
    lists = {"ooc_notes": ("OOC",), "private_notes": ("Privado",),
             "pending_outcomes": ("Pendiente",)}
    lists.update(changes)
    context = seed_value.context
    return NarrativeDraftRecord("escena", draft_id, version, revision, seed_value.seed_id,
                                seed_value.version, seed_value.seed_sha256, context,
                                len(context) + 1 if target is None else target, 3, H, sheet(),
                                citations, text, lists["ooc_notes"], lists["private_notes"],
                                lists["pending_outcomes"])


class ValidationTest(unittest.TestCase):
    def test_ids_and_labels(self):
        for value in ("a", "turno-1", "a1-b2-c3"):
            self.assertEqual(check_narrative_id("x", value), value)
        for value in ("", "A", "a--b", "-a", "a-", "a_b", "ñ", 1, None, "a b"):
            with self.subTest(value=value):
                with self.assertRaises(NarrativeError) as ctx:
                    check_narrative_id("x", value)
                self.assertEqual(ctx.exception.code, "INVALID_STATE")
        self.assertEqual(check_label("t", "Título «uno» ñ"), "Título «uno» ñ")
        for value in ("", " a", "a ", "a\nb", "a\tb", "﻿a", 3, "a\x7f"):
            with self.subTest(value=value):
                with self.assertRaises(NarrativeError):
                    check_label("t", value)
        with self.assertRaises(ValueError):
            NarrativeError("OTRO", "x")

    def test_header_and_refs(self):
        self.assertEqual(TopicHeader("escena", "aria", "Plaza").created_revision, 1)
        for args in (("Escena", "aria", "T"), ("escena", "aria", ""), ("escena", "aria", "T", 2),
                     ("escena", "aria", "T", True)):
            with self.subTest(args=args):
                with self.assertRaises(NarrativeError):
                    TopicHeader(*args)
        ref = PostRef("p", 1, H)
        self.assertEqual(ref.as_json(), {"content_sha256": H, "position": 1, "post_id": "p"})
        for args in (("p", 0, H), ("p", True, H), ("p", 1, "B" * 64), ("P", 1, H)):
            with self.subTest(args=args):
                with self.assertRaises(NarrativeError):
                    PostRef(*args)
        self.assertEqual(context_sha256(()), digest([]))
        self.assertEqual(context_sha256((ref,)), digest([ref.as_json()]))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            ref.position = 2


class ExternalPostTest(unittest.TestCase):
    def test_record_hashes_and_exact_text(self):
        for content in ("Línea\r\nsin final", "\tTab\n", "Ñ" * 3):
            with self.subTest(content=content):
                post = external(content=content)
                self.assertEqual(post.content, content)
                self.assertEqual((post.utf8_size, post.content_sha256),
                                 (len(content.encode()), hashlib.sha256(content.encode()).hexdigest()))
        post = external()
        record = external_record(post)
        self.assertEqual(sorted(record), ["author_label", "content", "content_sha256",
                                          "created_revision", "evidence", "position", "post_id",
                                          "post_sha256", "receipt", "utf8_size"])
        self.assertEqual(record["receipt"], {"confirmation_sha256": "a" * 64,
                                             "method": HUMAN_CONFIRMATION_METHOD})
        self.assertEqual(record["evidence"], {
            "ic_date": None, "locator": "https://foro.example/t/1#p1",
            "observed_at": "2026-10-14T20:00:00+02:00", "section_or_passage": None,
            "sha256": post.content_sha256, "source_id": "external-post:escena:respuesta-1"})
        self.assertEqual(post.post_sha256,
                         digest({k: v for k, v in record.items() if k != "post_sha256"}))
        self.assertEqual(post.ref, PostRef("respuesta-1", 1, post.content_sha256))

    def test_invalid_posts(self):
        for kwargs in ({"content": ""}, {"content": "con\x00nulo"}, {"content": "﻿BOM"},
                       {"content": "control\x07"}, {"author": "dos\nlíneas"}, {"author": ""},
                       {"post_id": "Mal"}, {"position": 0}, {"locator": ""},
                       {"locator": "con\nsalto"}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises((NarrativeError, ValueError)):
                    external(**kwargs)
        with self.assertRaises(ValueError):
            make_external_post(topic_id="escena", post_id="p", position=1, created_revision=2,
                               author_label="a", content="x", locator="l",
                               observed_at=datetime(2026, 10, 14), receipt=RECEIPT)
        post = external()
        for change in ({"receipt": None}, {"evidence": None},
                       {"evidence": dataclasses.replace(post.evidence, sha256=H)},
                       {"evidence": dataclasses.replace(post.evidence, ic_date="año 3")},
                       {"evidence": dataclasses.replace(post.evidence, source_id="otro")}):
            with self.subTest(change=list(change)):
                with self.assertRaises((NarrativeError, ValueError)):
                    ExternalPost("escena", "respuesta-1", 1, 2, "otro participante",
                                 "Texto ajeno\n", change.get("receipt", RECEIPT),
                                 change.get("evidence", post.evidence))


class SeedTest(unittest.TestCase):
    def test_payload_evidence_mode_and_lists(self):
        start = seed()
        self.assertEqual((start.mode, start.context_sha256), (SeedMode.START, context_sha256(())))
        self.assertEqual(start.evidence.source_id, "human-seed:escena:turno-1:v1")
        self.assertEqual(start.evidence.locator,
                         "instance://foro/narrative/topics/escena/seeds/turno-1/v1")
        self.assertEqual(start.evidence.section_or_passage, "seed:turno-1:v1")
        self.assertIsNone(start.evidence.observed_at)
        self.assertEqual(start.evidence.sha256, digest(seed_payload(start)))
        record = seed_record(start)
        self.assertEqual(start.seed_sha256,
                         digest({k: v for k, v in record.items() if k != "seed_sha256"}))
        self.assertEqual(record["details"], [])
        ref = external().ref
        follow = seed(context=(ref,), revision=3, beats=("Uno", "Dos"))
        self.assertEqual((follow.mode, follow.context), (SeedMode.CONTINUE, (ref,)))
        self.assertEqual(seed_summary(follow)["mode"], "CONTINUAR")
        self.assertNotEqual(follow.seed_sha256, seed(revision=3, beats=("Uno", "Dos")).seed_sha256)

    def test_invalid_seeds(self):
        ref = external().ref
        for kwargs in ({"intent": ""}, {"tone": "\x00"}, {"beats": ["lista"]}, {"beats": ("",)},
                       {"details": ("ok", 3)}, {"context": [ref]},
                       {"context": (PostRef("p", 2, H),)},
                       {"context": (ref, PostRef("respuesta-1", 2, H))}, {"version": 0}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises((NarrativeError, ValueError)):
                    seed(**kwargs)


class DraftAndPublicationTest(unittest.TestCase):
    def test_draft_record_and_channels(self):
        base = seed()
        citations = (CorpusCandidateRef("normas", 3, H),)
        record = draft(base, citations=citations)
        data = draft_record(record)
        self.assertEqual(sorted(data), sorted([
            "character_revision", "citations", "composition_sha256", "context",
            "context_sha256", "created_revision", "draft_id", "draft_sha256", "ooc_notes",
            "pending_outcomes", "private_notes", "publishable_text", "seed_id", "seed_sha256",
            "seed_version", "sheet", "target_position", "utf8_size", "version"]))
        self.assertEqual(record.draft_sha256,
                         digest({k: v for k, v in data.items() if k != "draft_sha256"}))
        self.assertEqual((data["publishable_text"], data["ooc_notes"], data["private_notes"],
                          data["pending_outcomes"]),
                         ("Aria cruza la plaza.\n", ["OOC"], ["Privado"], ["Pendiente"]))
        self.assertEqual(data["citations"], [{"candidate_id": "normas", "candidate_sha256": H,
                                              "version": 3}])
        self.assertEqual(draft(base, ooc_notes=(), private_notes=(),
                               pending_outcomes=()).ooc_notes, ())
        for kwargs in ({"target": 2}, {"text": ""}, {"citations": citations * 2},
                       {"citations": [citations[0]]}, {"private_notes": ("",)}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises((NarrativeError, ValueError)):
                    draft(base, **kwargs)
        with self.assertRaises(NarrativeError):
            dataclasses.replace(record, sheet=sheet(composition="e" * 64))

    def test_publication_exact_and_edited(self):
        record = draft(seed())
        exact = make_publication(topic_id="escena", post_id="propio", publication_revision=4,
                                 draft=record, published_text=record.publishable_text,
                                 locator="https://foro.example/t/1#p2", observed_at=OBSERVED,
                                 receipt=RECEIPT)
        edited = make_publication(topic_id="escena", post_id="propio", publication_revision=4,
                                  draft=record, published_text="Otro texto",
                                  locator="https://foro.example/t/1#p2", observed_at=OBSERVED,
                                  receipt=RECEIPT)
        self.assertEqual((exact.content_matches_draft, edited.content_matches_draft),
                         (True, False))
        self.assertEqual((edited.position, edited.draft_sha256, edited.published_text),
                         (1, record.draft_sha256, "Otro texto"))
        data = publication_record(edited)
        self.assertEqual(edited.publication_sha256,
                         digest({k: v for k, v in data.items() if k != "publication_sha256"}))
        self.assertEqual(data["evidence"]["source_id"], "publication:escena:propio")
        with self.assertRaises(NarrativeError):
            dataclasses.replace(edited, content_matches_draft=1)
        self.assertNotIn("ooc_notes", data)
        # Views: the relation must agree with the publication.
        for lifecycle, relation, published in (
            (DraftLifecycle.RETIRED, DraftPublication.NONE, None),
            (DraftLifecycle.ACTIVE, DraftPublication.EXACT, None),
            (DraftLifecycle.ACTIVE, DraftPublication.NONE, exact),
            (DraftLifecycle.ACTIVE, DraftPublication.EXACT, edited),
            (DraftLifecycle.ACTIVE, DraftPublication.EDITED, exact),
        ):
            with self.subTest(lifecycle=lifecycle, relation=relation):
                with self.assertRaises(NarrativeError):
                    NarrativeDraftView(record, lifecycle, relation, published)
        self.assertEqual(NarrativeDraftView(record, DraftLifecycle.STALE, DraftPublication.EDITED,
                                            edited).published, edited)

    def test_state_replay_and_summaries(self):
        header = TopicHeader("escena", "aria", "Plaza «uno»")
        empty = TopicState(header)
        self.assertEqual((empty.revision, empty.replay.posts, empty.replay.context), (1, (), ()))
        self.assertEqual(topic_summary(empty), {
            "character_id": "aria", "context_sha256": context_sha256(()), "created_revision": 1,
            "draft_count": 0, "post_count": 0, "publication_count": 0, "revision": 1,
            "seed_count": 0, "title": "Plaza «uno»", "topic_id": "escena"})
        first = seed()
        record = draft(first)
        publication = make_publication(topic_id="escena", post_id="propio",
                                       publication_revision=4, draft=record,
                                       published_text=record.publishable_text,
                                       locator="l", observed_at=OBSERVED, receipt=RECEIPT)
        other = external(post_id="respuesta-1", position=2, revision=5)
        state = TopicState(header, (other,), (first,), (record,), (publication,))
        self.assertEqual([(p.position, p.author) for p in state.replay.posts],
                         [(1, PostAuthor.SELF), (2, PostAuthor.OTHER)])
        view = state.draft_view("turno-1", 1)
        self.assertEqual((view.lifecycle, view.publication),
                         (DraftLifecycle.STALE, DraftPublication.EXACT))
        self.assertEqual(post_summary(state.replay.posts[0]),
                         {**publication_record(publication), "author": "SELF"})
        summary = narrative_draft_summary(view)
        self.assertEqual((summary["lifecycle"], summary["publication"],
                          summary["published_post_id"]), ("STALE", "EXACT", "propio"))
        self.assertFalse({"facts", "canon", "nonce"} & set(summary))
        with self.assertRaises(NarrativeError):  # a gap in the revisions
            TopicState(header, (external(revision=3),))
        with self.assertRaises(NarrativeError):  # an element of another topic
            TopicState(TopicHeader("otra", "aria", "T"), (external(),))


class SemanticRepeatTest(unittest.TestCase):
    """REV7A-03: a new version identical to the previous one on the same context never loads."""

    HEADER = TopicHeader("escena", "aria", "Plaza")

    def decode(self, content, revision):
        return decode_topic_state(content, forum_id="foro", revision=revision,
                                  candidate_resolver=lambda *a: None,
                                  sheet_check=lambda *a: None)

    def test_repeated_seed_version(self):
        first = seed()
        content = encode_topic_content(TopicState(self.HEADER, seeds=(first,)))
        content["seeds"].append(seed_record(seed(version=2, revision=3)))
        with self.assertRaises(NarrativeError) as ctx:
            self.decode(content, 3)
        self.assertIn("repite la anterior", ctx.exception.reason)
        with self.assertRaises(NarrativeError):
            TopicState(self.HEADER, seeds=(first, seed(version=2, revision=3)))
        # A changed field, or the same ideas on a new context, are real new versions.
        changed = TopicState(self.HEADER, seeds=(first, seed(version=2, revision=3, tone="Tenso")))
        self.assertEqual(self.decode(encode_topic_content(changed), 3), changed)
        post = external(revision=3)
        later = TopicState(self.HEADER, (post,),
                           (first, seed(version=2, revision=4, context=(post.ref,))))
        self.assertEqual(self.decode(encode_topic_content(later), 4), later)

    def test_repeated_draft_version(self):
        first = seed()
        one = draft(first)
        content = encode_topic_content(TopicState(self.HEADER, seeds=(first,), drafts=(one,)))
        content["drafts"].append(draft_record(draft(first, revision=4, version=2)))
        with self.assertRaises(NarrativeError) as ctx:
            self.decode(content, 4)
        self.assertIn("repite el anterior", ctx.exception.reason)
        changed = TopicState(self.HEADER, seeds=(first,),
                             drafts=(one, draft(first, revision=4, version=2, text="Otro\n")))
        self.assertEqual(self.decode(encode_topic_content(changed), 4), changed)
        other_id = TopicState(self.HEADER, seeds=(first,),
                              drafts=(one, draft(first, revision=4, draft_id="alternativa")))
        self.assertEqual(self.decode(encode_topic_content(other_id), 4), other_id)


class FacadeTest(unittest.TestCase):
    """REV7A-04: core.memory exports the narrative model in any import order."""

    def test_import_orders(self):
        script = ("import importlib, sys\n"
                  "for name in sys.argv[1:]: importlib.import_module(name)\n"
                  "import core.memory as m, core.memory.narrative as n, core.runtime as r\n"
                  "assert all(getattr(m, k) is getattr(n, k) for k in m.__all__ if k != "
                  "'SourceRef')\n"
                  "assert m.TopicState is r.TopicState\n"
                  "from core.memory import *\n"
                  "assert TopicState is n.TopicState\n")
        for order in (["core.character.models", "core.memory"], ["core.memory", "core.runtime"],
                      ["core.runtime", "core.memory"], ["core.memory.narrative"]):
            with self.subTest(order=order):
                result = subprocess.run([sys.executable, "-B", "-c", script, *order], cwd=ROOT,
                                        capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr.decode())


class PublicationBoundaryTest(unittest.TestCase):
    def test_dtos_and_protocol_are_only_a_contract(self):
        request = PublicationRequest("Texto", text_sha256("Texto"), "tema:escena")
        receipt = PublicationReceipt(text_sha256("Texto"), None)
        for value in (request, receipt):
            with self.assertRaises(dataclasses.FrozenInstanceError):
                value.content_sha256 = H
        self.assertIs(PublicationPort.__mro__[1], typing.Protocol)
        self.assertEqual([name for name in vars(PublicationPort)
                          if not name.startswith("_")], ["publish"])
        for path in (ROOT / "adapters").rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertNotIn("PublicationPort", text)
                self.assertNotIn("def publish", text)

    def test_sheet_ref_json(self):
        self.assertEqual(json.loads(json.dumps(sheet().as_json())),
                         {"composition_sha256": H, "draft_sha256": "c" * 64,
                          "staff_review_sha256": "d" * 64, "version": 1})
        for args in ((0, H, H, H), (1, "x", H, H), (True, H, H, H)):
            with self.subTest(args=args):
                with self.assertRaises(NarrativeError):
                    CharacterSheetRef(*args)


class SeedEvidenceIsLocalTest(unittest.TestCase):
    def test_human_seed_rejects_foreign_evidence(self):
        good = seed()
        bad = dataclasses.replace(good.evidence, sha256=H)
        with self.assertRaises(NarrativeError):
            HumanSeed("escena", "turno-1", 1, 2, (), "Presentarse", "Sereno", ("Llega",), (),
                      ("No decidir por otros",), (), RECEIPT, bad)
        self.assertIsInstance(good.evidence, SourceRef)


if __name__ == "__main__":
    unittest.main()
