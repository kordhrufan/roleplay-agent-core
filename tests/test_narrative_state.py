import copy
import hashlib
import os
import unittest

from core.memory.narrative import (
    DraftPublication,
    PostAuthor,
    encode_topic_content,
)
from core.review.models import DraftLifecycle
from core.runtime.instance import InstanceError, load_instance
from core.runtime.persistence import canonical_json_bytes, encode_state, load_state
from tests.instance_support import ROOT
from tests.test_narrative_workflow import TOPIC, NarrativeCase


class RichTopicCase(NarrativeCase):
    """Topic: p1 OTHER, p2 SELF exact, p3 OTHER, p4 SELF edited (revision 9)."""

    def setUp(self):
        super().setUp()
        self.new_topic()
        self.record_post()
        self.seed()
        self.ndraft(citations=(("normas", 3), ("duda", 1)))
        self.confirm()
        self.record_post(post_id="respuesta-2", content="Otra respuesta\n", name="p2.json")
        self.seed(seed_id="turno-2", name="s2.json")
        self.ndraft(draft_id="turno-2", seed_id="turno-2", name="b2.json")
        self.confirm(draft_id="turno-2", post_id="post-propio-2", text="Editado a mano\n",
                     name="c2.json")


class EnvelopeAndReplayTest(RichTopicCase):
    def test_exact_envelope_and_lazy_creation(self):
        revision, content = load_state(self.topic_path())
        state = self.state()
        self.assertEqual((revision, self.topic().state_revision, state.revision), (9, 9, 9))
        self.assertEqual(content, encode_topic_content(state))
        self.assertEqual(self.topic_path().read_bytes(),
                         encode_state(encode_topic_content(state), revision=9))
        self.assertEqual(sorted(content), ["drafts", "external_posts", "publications", "seeds",
                                           "topic"])
        self.assertEqual(sorted(p.name for p in (self.instance / "narrative").iterdir()),
                         ["topics"])

    def test_positions_authors_and_views(self):
        state = self.state()
        self.assertEqual([(p.position, p.author, p.post_id) for p in state.replay.posts],
                         [(1, PostAuthor.OTHER, "respuesta-1"),
                          (2, PostAuthor.SELF, "post-propio-1"),
                          (3, PostAuthor.OTHER, "respuesta-2"),
                          (4, PostAuthor.SELF, "post-propio-2")])
        views = [(v.record.draft_id, v.lifecycle, v.publication, v.record.target_position)
                 for v in state.replay.draft_views]
        self.assertEqual(views, [("turno-1", DraftLifecycle.STALE, DraftPublication.EXACT, 2),
                                 ("turno-2", DraftLifecycle.STALE, DraftPublication.EDITED, 4)])
        self.assertEqual([len(s.context) for s in state.seeds], [1, 3])
        self.assertEqual(state.post("post-propio-2").content, "Editado a mano\n")


class NoTopicsTest(NarrativeCase):
    def test_instances_without_narrative_are_unchanged(self):
        self.assertFalse((self.instance / "narrative").exists())
        self.assertEqual(self.loaded().topics, ())

    def test_folder_layout_is_strict(self):
        self.new_topic()
        narrative = self.instance / "narrative"
        cases = (
            (narrative / "intruso.txt", b"x"),
            (narrative / "topics" / "suelto.json", b"{}"),
            (self.topic_root() / "otro.json", b"{}"),
        )
        for path, data in cases:
            with self.subTest(path=path.name):
                path.write_bytes(data)
                with self.assertRaises(InstanceError) as ctx:
                    self.loaded()
                self.assertEqual(ctx.exception.code, "INVALID_STATE")
                path.unlink()
        leftover = narrative / "topics" / f".{TOPIC}.staging-0011223344556677"
        leftover.mkdir()
        with self.assertRaises(InstanceError):
            self.loaded()
        leftover.rmdir()
        (narrative / "topics" / ".otro.create.lock").write_bytes(b"")
        self.assertEqual(len(self.loaded().topics), 1)  # a creation in progress is transient
        os.unlink(narrative / "topics" / ".otro.create.lock")
        self.topic_lock().write_bytes(b"")
        self.assertEqual(len(self.loaded().topics), 1)
        self.topic_lock().unlink()
        self.topic_root().rename(narrative / "topics" / "renombrado")
        with self.assertRaises(InstanceError):
            self.loaded()


class TamperTest(RichTopicCase):
    def assert_tampered(self, mutate, revision_delta=0):
        original = self.topic_path().read_bytes()
        revision, content = load_state(self.topic_path())
        changed = copy.deepcopy(content)
        mutate(changed)
        self.topic_path().write_bytes(encode_state(changed, revision=revision + revision_delta))
        try:
            with self.assertRaises(InstanceError) as ctx:
                load_instance(self.instance, expected_core_root=ROOT)
            self.assertEqual(ctx.exception.code, "INVALID_STATE")
        finally:
            self.topic_path().write_bytes(original)

    def test_every_field_hash_evidence_receipt_and_revision(self):
        def setter(*path, value):
            def mutate(content):
                target = content
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
            return mutate

        def dropper(*path):
            def mutate(content):
                target = content
                for key in path[:-1]:
                    target = target[key]
                del target[path[-1]]
            return mutate

        cases = {
            "topic id": setter("topic", "topic_id", value="otro"),
            "character": setter("topic", "character_id", value="nadie"),
            "header revision": setter("topic", "created_revision", value=2),
            "extra key": setter("topic", "extra", value=1),
            "post content": setter("external_posts", 0, "content", value="Cambiado\n"),
            "post hash": setter("external_posts", 0, "content_sha256", value="0" * 64),
            "post record hash": setter("external_posts", 0, "post_sha256", value="0" * 64),
            "post size": setter("external_posts", 0, "utf8_size", value=1),
            "post position": setter("external_posts", 0, "position", value=2),
            "post revision": setter("external_posts", 0, "created_revision", value=3),
            "post author": setter("external_posts", 0, "author_label", value=""),
            "post ic date": setter("external_posts", 0, "evidence", "ic_date", value="año 3"),
            "post evidence hash": setter("external_posts", 0, "evidence", "sha256",
                                         value="0" * 64),
            "post evidence id": setter("external_posts", 0, "evidence", "source_id",
                                       value="otro"),
            "post observed": setter("external_posts", 0, "evidence", "observed_at",
                                    value="2026-10-14T20:00:00"),
            "receipt method": setter("external_posts", 0, "receipt", "method", value="OTRO"),
            "receipt hash": setter("external_posts", 0, "receipt", "confirmation_sha256",
                                   value="zz"),
            "receipt extra": setter("external_posts", 0, "receipt", "nonce", value="ABCDEFGH"),
            "seed intent": setter("seeds", 0, "intent", value="Otra"),
            "seed context": setter("seeds", 0, "context", value=[]),
            "seed context hash": setter("seeds", 0, "context_sha256", value="0" * 64),
            "seed hash": setter("seeds", 0, "seed_sha256", value="0" * 64),
            "seed locator": setter("seeds", 0, "evidence", "locator", value="otro"),
            "seed version": setter("seeds", 0, "version", value=2),
            "seed beats": setter("seeds", 0, "beats", value="uno"),
            "seed missing": dropper("seeds", 0, "tone"),
            "draft text": setter("drafts", 0, "publishable_text", value="Otro\n"),
            "draft private": setter("drafts", 0, "private_notes", value=["Añadido"]),
            "draft staff": setter("drafts", 0, "sheet", "staff_review_sha256", value="0" * 64),
            "draft sheet version": setter("drafts", 0, "sheet", "version", value=2),
            "draft citation hash": setter("drafts", 0, "citations", 0, "candidate_sha256",
                                          value="0" * 64),
            "draft citation version": setter("drafts", 0, "citations", 0, "version", value=1),
            "draft character revision": setter("drafts", 0, "character_revision", value=99),
            "draft target": setter("drafts", 0, "target_position", value=3),
            "draft composition": setter("drafts", 0, "composition_sha256", value="0" * 64),
            "draft seed hash": setter("drafts", 0, "seed_sha256", value="0" * 64),
            "publication text": setter("publications", 0, "published_text", value="Otro\n"),
            "publication match": setter("publications", 1, "content_matches_draft", value=True),
            "publication draft hash": setter("publications", 0, "draft_sha256", value="0" * 64),
            "publication position": setter("publications", 0, "position", value=3),
            "publication revision": setter("publications", 0, "publication_revision",
                                           value=9),
            "publication draft": setter("publications", 0, "draft_version", value=2),
            "seed order": lambda c: c["seeds"].reverse(),
            "post removed": lambda c: c["external_posts"].pop(),
            "draft removed": lambda c: c["drafts"].pop(0),
        }
        for name, mutate in cases.items():
            with self.subTest(case=name):
                self.assert_tampered(mutate)
        for delta in (1, -1):
            with self.subTest(revision_delta=delta):
                self.assert_tampered(lambda c: None, revision_delta=delta)
        self.assertEqual(self.topic().state_revision, 9)  # restored intact

    def test_a_sheet_that_is_not_approved_in_history_invalidates_the_topic(self):
        character_path = self.state_path()
        original = character_path.read_bytes()
        revision, content = load_state(character_path)
        changed = copy.deepcopy(content)
        changed["staff_responses"] = []
        character_path.write_bytes(encode_state(changed, revision=revision - 1))
        try:
            with self.assertRaises(InstanceError):
                self.loaded()
        finally:
            character_path.write_bytes(original)
        self.assertEqual(self.topic().state_revision, 9)


class HistoricalSheetTest(NarrativeCase):
    """REV7A-02: the cited character revision is replayed; a self-consistent forgery fails."""

    def setUp(self):
        super().setUp()
        self.new_topic()
        self.seed()
        self.ndraft()

    def forge(self, character_revision):
        original = self.topic_path().read_bytes()
        revision, content = load_state(self.topic_path())
        record = content["drafts"][0]
        record["character_revision"] = character_revision
        record["draft_sha256"] = hashlib.sha256(canonical_json_bytes(
            {k: v for k, v in record.items() if k != "draft_sha256"}, pretty=False)).hexdigest()
        self.topic_path().write_bytes(encode_state(content, revision=revision))
        return original

    def assert_forgery_rejected(self, character_revision):
        original = self.forge(character_revision)
        try:
            with self.assertRaises(InstanceError) as ctx:
                self.loaded()
            self.assertEqual(ctx.exception.code, "INVALID_STATE")
            self.assertIn(f"revisión {character_revision} del personaje", ctx.exception.reason)
        finally:
            self.topic_path().write_bytes(original)

    def test_revisions_before_the_sheet_or_its_approval(self):
        self.assertEqual(self.state().draft("turno-1", 1).character_revision, 3)
        for revision in (1, 2):  # only the concept; the sheet still pending
            with self.subTest(revision=revision):
                self.assert_forgery_rejected(revision)

    def test_a_revision_where_another_sheet_was_current_and_later_changes(self):
        self.create(version=2, text="# Ficha v2\n")  # character revision 4: v1 superseded
        self.add(text="# Aria\nExploradora valiente.\n")  # revision 5
        self.decide()  # revision 6: the composition changes
        self.assertEqual(self.state().draft("turno-1", 1).character_revision, 3)  # still loads
        for revision in (4, 5, 6):
            with self.subTest(revision=revision):
                self.assert_forgery_rejected(revision)


if __name__ == "__main__":
    unittest.main()
