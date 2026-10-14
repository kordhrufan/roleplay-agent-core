import json
import os
import unittest
from unittest import mock

import core.runtime.narrative as narrative_module
from core.memory.narrative import (
    DraftPublication,
    NarrativeError,
    PostAuthor,
    SeedMode,
    context_sha256,
)
from core.review.models import DraftLifecycle, ReviewStatus
from core.runtime import assimilation, persistence
from core.runtime.instance import update_lock_path
from core.runtime.narrative import (
    PublicationPort,
    confirm_narrative_publication,
    create_narrative_draft,
    create_topic,
    get_narrative_draft,
    get_topic,
    import_human_seed,
    list_topics,
    record_external_post,
)
from core.runtime.persistence import load_state
from tests.instance_support import ROOT
from tests.test_assimilation_decisions import FakeTerminal
from tests.test_character_draft import DraftCase

LOCATOR = "https://foro.example/t/40#p1"
OBSERVED = "2026-10-14T20:00:00+02:00"
TOPIC = "escena"


class NarrativeCase(DraftCase):
    """An instance with `aria`, whose sheet v1 the staff approved (character revision 3)."""

    def setUp(self):
        super().setUp()
        self.create()
        self.record()

    # --- paths and state ---

    def topic_root(self, topic_id=TOPIC):
        return self.instance / "narrative" / "topics" / topic_id

    def topic_path(self, topic_id=TOPIC):
        return self.topic_root(topic_id) / "state.json"

    def topic_lock(self, topic_id=TOPIC):
        return self.topic_root(topic_id) / "state.json.lock"

    def topic(self, topic_id=TOPIC):
        return get_topic(self.loaded(), topic_id=topic_id)

    def state(self, topic_id=TOPIC):
        return self.topic(topic_id).state

    def snapshot(self, topic_id=TOPIC):
        path = self.topic_path(topic_id)
        return path.read_bytes(), os.stat(path).st_mtime_ns

    # --- inputs ---

    def write_json(self, name, value):
        path = self.root / name
        if isinstance(value, bytes):
            path.write_bytes(value)
        else:
            path.write_bytes(json.dumps(value, ensure_ascii=False).encode("utf-8"))
        return path

    def post_value(self, post_id="respuesta-1", author="otro participante",
                   content="Texto ajeno completo.\n", locator=LOCATOR, observed_at=OBSERVED):
        return {"post_id": post_id, "author_label": author, "locator": locator,
                "observed_at": observed_at, "content": content}

    def seed_value(self, seed_id="turno-1", version=1, intent="Presentarse en la plaza",
                   tone="Sereno", beats=("Llega al atardecer",), details=("Lleva su capa",),
                   ooc_constraints=("No decidir por otros",),
                   pending_outcomes=("Si el guardia la deja pasar",)):
        return {"seed_id": seed_id, "version": version, "intent": intent, "tone": tone,
                "beats": list(beats), "details": list(details),
                "ooc_constraints": list(ooc_constraints),
                "pending_outcomes": list(pending_outcomes)}

    def draft_value(self, draft_id="turno-1", version=1, seed_id="turno-1", seed_version=1,
                    text="Aria cruza la plaza.\n", citations=(("normas", 3),), seed_sha256=None,
                    context=None, composition=None, sheet_version=1, sheet_sha256=None,
                    ooc_notes=("Nota OOC",), private_notes=("Pienso que...",),
                    pending_outcomes=("Respuesta del guardia",), topic_id=TOPIC):
        state = self.state(topic_id)
        seed = state.seed(seed_id, seed_version)
        return {
            "draft_id": draft_id, "version": version, "seed_id": seed_id,
            "seed_version": seed_version,
            "seed_sha256": seed_sha256 or (seed.seed_sha256 if seed else "0" * 64),
            "context_sha256": context or context_sha256(state.replay.context),
            "composition_sha256": composition or self.effective().composition_sha256,
            "sheet_version": sheet_version,
            "sheet_sha256": sheet_sha256 or self.draft(sheet_version).record.draft_sha256,
            "citations": [{"candidate_id": c, "version": v} for c, v in citations],
            "publishable_text": text, "ooc_notes": list(ooc_notes),
            "private_notes": list(private_notes), "pending_outcomes": list(pending_outcomes),
        }

    def publication_value(self, post_id="post-propio-1", draft_id="turno-1", version=1,
                          text=None, draft_sha256=None, locator=LOCATOR + "2",
                          observed_at="2026-10-14T20:15:00+02:00", topic_id=TOPIC):
        record = self.state(topic_id).draft(draft_id, version)
        return {"post_id": post_id,
                "draft_sha256": draft_sha256 or (record.draft_sha256 if record else "0" * 64),
                "locator": locator, "observed_at": observed_at,
                "published_text": record.publishable_text if text is None else text}

    # --- operations ---

    def new_topic(self, topic_id=TOPIC, title="Escena en la plaza", character_id="aria"):
        return create_topic(self.instance, expected_core_root=ROOT, character_id=character_id,
                            topic_id=topic_id, title=title)

    def record_post(self, value=None, terminal=None, name="post.json", topic_id=TOPIC,
                    **kwargs):
        path = self.write_json(name, value if value is not None else self.post_value(**kwargs))
        return record_external_post(self.instance, expected_core_root=ROOT, topic_id=topic_id,
                                    input_path=path, terminal=terminal or FakeTerminal())

    def seed(self, value=None, terminal=None, name="semilla.json", topic_id=TOPIC, **kwargs):
        path = self.write_json(name, value if value is not None else self.seed_value(**kwargs))
        return import_human_seed(self.instance, expected_core_root=ROOT, topic_id=topic_id,
                                 input_path=path, terminal=terminal or FakeTerminal())

    def ndraft(self, value=None, name="borrador.json", topic_id=TOPIC, **kwargs):
        path = self.write_json(name, value if value is not None
                               else self.draft_value(topic_id=topic_id, **kwargs))
        return create_narrative_draft(self.instance, expected_core_root=ROOT, topic_id=topic_id,
                                      input_path=path)

    def confirm(self, draft_id="turno-1", version=1, value=None, terminal=None,
                name="publicacion.json", topic_id=TOPIC, **kwargs):
        path = self.write_json(name, value if value is not None else self.publication_value(
            draft_id=draft_id, version=version, topic_id=topic_id, **kwargs))
        return confirm_narrative_publication(
            self.instance, expected_core_root=ROOT, topic_id=topic_id, draft_id=draft_id,
            version=version, input_path=path, terminal=terminal or FakeTerminal())

    def ready(self):
        """Topic, seed turno-1 v1 and draft turno-1 v1 on the empty topic."""
        self.new_topic()
        self.seed()
        self.ndraft()

    def assert_error(self, code, action, *args, **kwargs):
        with self.assertRaises(NarrativeError) as ctx:
            action(*args, **kwargs)
        self.assertEqual(ctx.exception.code, code, ctx.exception.reason)
        return ctx.exception


class StartTopicTest(NarrativeCase):
    def test_empty_topic_seed_alternatives_and_exact_publication(self):
        result = self.new_topic()
        self.assertTrue(result.created)
        self.assertEqual((result.topic.state_revision, result.topic.state.replay.posts),
                         (1, ()))
        self.assertFalse(self.new_topic().created)
        self.assert_error("CONFLICT", self.new_topic, title="Otro título")
        self.assertEqual([t.state.topic_id for t in list_topics(self.loaded())], [TOPIC])
        self.assertEqual(list_topics(self.loaded(), character_id="otro"), ())

        seed = self.seed()
        self.assertEqual((seed.created, seed.seed.mode, seed.seed.context, seed.topic.state_revision),
                         (True, SeedMode.START, (), 2))
        first = self.ndraft()
        alternative = self.ndraft(draft_id="alternativa", text="Aria espera en la sombra.\n",
                                  citations=())
        self.assertEqual((first.created, first.draft.record.target_position,
                          first.draft.lifecycle, first.draft.publication),
                         (True, 1, DraftLifecycle.ACTIVE, DraftPublication.NONE))
        self.assertEqual(alternative.topic.state_revision, 4)
        sheet = first.draft.record.sheet
        approved = self.draft(1)
        self.assertEqual((sheet.version, sheet.draft_sha256, sheet.staff_review_sha256,
                          first.draft.record.character_revision),
                         (1, approved.record.draft_sha256,
                          approved.staff_response.staff_review_sha256, 3))

        published = self.confirm()
        self.assertTrue(published.created)
        self.assertTrue(published.publication.content_matches_draft)
        state = published.topic.state
        self.assertEqual([(p.position, p.author, p.post_id) for p in state.replay.posts],
                         [(1, PostAuthor.SELF, "post-propio-1")])
        views = {v.record.draft_id: v for v in state.replay.draft_views}
        self.assertEqual((views["turno-1"].lifecycle, views["turno-1"].publication),
                         (DraftLifecycle.STALE, DraftPublication.EXACT))
        self.assertEqual((views["alternativa"].lifecycle, views["alternativa"].publication),
                         (DraftLifecycle.STALE, DraftPublication.NONE))
        # A retry is a no-op; the alternative cannot be published on a context that moved on.
        before = self.snapshot()
        self.assertFalse(self.confirm().created)
        self.assertEqual(self.snapshot(), before)
        self.assert_error("CONFLICT", self.confirm, draft_id="alternativa",
                          post_id="post-propio-2")
        self.assertEqual(self.state(), state)
        self.assertFalse(self.topic_lock().exists())

    def test_edited_publication_keeps_both_texts_and_is_never_the_draft(self):
        self.ready()
        result = self.confirm(text="Aria cruza la plaza, despacio.\n")
        publication = result.publication
        view = get_narrative_draft(self.loaded(), topic_id=TOPIC, draft_id="turno-1", version=1)
        self.assertEqual((publication.content_matches_draft, view.publication,
                          view.record.publishable_text, self.state().post("post-propio-1").content),
                         (False, DraftPublication.EDITED, "Aria cruza la plaza.\n",
                          "Aria cruza la plaza, despacio.\n"))
        self.assertEqual(publication.draft_sha256, view.record.draft_sha256)
        self.assert_error("CONFLICT", self.confirm, text="Otra edición\n")

    def test_publication_does_not_confirm_pending_outcomes_or_change_the_character(self):
        self.ready()
        character = self.loaded().characters[0]
        self.confirm()
        self.assertEqual(self.loaded().characters[0], character)
        self.assertEqual(self.state().draft("turno-1", 1).pending_outcomes,
                         ("Respuesta del guardia",))


class ContinueTopicTest(NarrativeCase):
    def test_posts_by_others_then_seed_draft_publication_and_next_reply(self):
        self.new_topic()
        one = self.record_post()
        two = self.record_post(post_id="respuesta-2", author="otra persona",
                               content="Segunda respuesta\r\nsin final")
        self.assertEqual([(r.created, r.post.position) for r in (one, two)],
                         [(True, 1), (True, 2)])
        self.assertEqual(self.state().post("respuesta-2").content,
                         "Segunda respuesta\r\nsin final")
        seed = self.seed().seed
        self.assertEqual((seed.mode, len(seed.context)), (SeedMode.CONTINUE, 2))
        draft = self.ndraft().draft.record
        self.assertEqual((draft.target_position, draft.context), (3, seed.context))
        self.confirm()
        three = self.record_post(post_id="respuesta-3", content="Tercera\n", name="p3.json")
        self.assertEqual(three.post.position, 4)
        state = self.state()
        self.assertEqual([(p.position, p.author) for p in state.replay.posts],
                         [(1, PostAuthor.OTHER), (2, PostAuthor.OTHER), (3, PostAuthor.SELF),
                          (4, PostAuthor.OTHER)])
        # The next turn: a new seed captures the four posts.
        nxt = self.seed(seed_id="turno-2", name="s2.json").seed
        self.assertEqual(len(nxt.context), 4)
        self.assertEqual(self.ndraft(draft_id="turno-2", seed_id="turno-2",
                                     name="b2.json").draft.record.target_position, 5)
        # Everything survives a reload from disk exactly.
        self.assertEqual(self.state(), get_topic(self.loaded(), topic_id=TOPIC).state)

    def test_external_post_retries_and_conflicts(self):
        self.new_topic()
        self.record_post()
        before = self.snapshot()
        with mock.patch.object(narrative_module, "_corpus_lock") as lock:
            terminal = FakeTerminal()
            self.assertFalse(self.record_post(terminal=terminal).created)
        lock.assert_not_called()
        self.assertEqual((terminal.reads, self.snapshot()), (0, before))
        for change in ({"content": "Otro\n"}, {"author": "otra"}, {"locator": "otro"},
                       {"observed_at": "2026-10-14T21:00:00+02:00"},
                       {"observed_at": "2026-10-14T18:00:00+00:00"}):  # same instant, other text
            with self.subTest(change=change):
                self.assert_error("CONFLICT", self.record_post, **change)
        self.ready_draft_on_posts()
        self.assert_error("CONFLICT", self.confirm, post_id="respuesta-1")

    def ready_draft_on_posts(self):
        self.seed()
        self.ndraft()


class SheetAndCompositionTest(NarrativeCase):
    def test_only_the_current_active_approved_sheet_on_the_effective_composition(self):
        self.new_topic()
        self.seed()
        sheet_v1 = self.draft(1).record.draft_sha256
        composition_v1 = self.effective().composition_sha256
        # A pending v2 supersedes the approved v1: neither can be cited.
        self.create(version=2, text="# Ficha v2\n")
        self.assert_error("CONFLICT", self.ndraft, sheet_version=1)
        self.assert_error("CONFLICT", self.ndraft, sheet_version=2)
        # Rejected by the staff: still not citable.
        self.record(version=2, status=ReviewStatus.REJECTED, name="r2.json")
        self.assert_error("CONFLICT", self.ndraft, sheet_version=2)
        # Approved v3 is citable; a wrong hash or an old composition is not.
        self.create(version=3, text="# Ficha v3\n")
        self.record(version=3, name="r3.json")
        self.assert_error("CONFLICT", self.ndraft, sheet_version=3, sheet_sha256=sheet_v1)
        self.assertTrue(self.ndraft(sheet_version=3).created)
        # A new approved proposal changes the composition: v3 becomes stale.
        self.add(text="# Aria\nExploradora valiente.\n")
        self.decide()
        self.assert_error("CONFLICT", self.ndraft, draft_id="otro", sheet_version=3)
        self.assert_error("CONFLICT", self.ndraft, draft_id="otro", sheet_version=3,
                          composition=composition_v1)

    def test_a_later_character_change_keeps_history_and_warns_at_publication(self):
        self.ready()
        self.add(text="# Aria\nExploradora valiente.\n")
        self.decide()
        loaded = self.loaded()  # the historical sheet still validates
        self.assertEqual(get_topic(loaded, topic_id=TOPIC).state.draft("turno-1", 1).sheet.version,
                         1)
        terminal = FakeTerminal()
        self.confirm(terminal=terminal)
        self.assertIn("Composición/ficha vigentes ahora: NO\n", terminal.output)


class CitationTest(NarrativeCase):
    def test_citations_zero_many_uncertainty_and_invalid(self):
        self.new_topic()
        self.seed()
        self.assertEqual(self.ndraft(citations=()).draft.record.citations, ())
        many = self.ndraft(draft_id="dos", citations=(("normas", 3), ("duda", 1), ("mundo", 1)))
        self.assertEqual([c.key for c in many.draft.record.citations],
                         [("normas", 3), ("duda", 1), ("mundo", 1)])
        for citations in ((("normas", 3), ("normas", 3)),):
            self.assert_error("INVALID_STATE", self.ndraft, draft_id="tres", citations=citations)
        for citations in ((("idea", 1),), (("nada", 1),), (("normas", 1),), (("normas", 2),)):
            with self.subTest(citations=citations):
                self.assert_error("INVALID_STATE", self.ndraft, draft_id="tres",
                                  citations=citations)
        bad = self.draft_value(draft_id="tres")
        for citations in ([{"candidate_id": "normas"}], [{"candidate_id": "normas", "version": 3,
                                                          "candidate_sha256": "0" * 64}],
                          [{"candidate_id": "normas", "version": "3"}], {"normas": 3}):
            with self.subTest(citations=citations):
                self.assert_error("INVALID_STATE", self.ndraft, value={**bad,
                                                                       "citations": citations})


class SeedAndDraftRulesTest(NarrativeCase):
    def test_seed_versions_retries_and_repeats(self):
        self.new_topic()
        self.seed()
        before = self.snapshot()
        terminal = FakeTerminal()
        self.assertFalse(self.seed(terminal=terminal).created)
        self.assertEqual((terminal.reads, self.snapshot()), (0, before))
        self.assert_error("CONFLICT", self.seed, intent="Otra")
        self.assert_error("CONFLICT", self.seed, version=3)
        self.assert_error("CONFLICT", self.seed, version=2)  # repeats v1 on the same context
        self.assertEqual(self.seed(version=2, tone="Tenso").seed.version, 2)
        self.record_post()
        # Same ideas, new context: a meaningful new version.
        self.assertEqual(self.seed(version=3, tone="Tenso").seed.context, self.state().replay.context)
        for value in ({**self.seed_value(), "extra": 1}, {"seed_id": "x"},
                      {**self.seed_value(version=4), "beats": "uno"},
                      {**self.seed_value(version=4), "version": True},
                      {**self.seed_value(version=4), "intent": ""},
                      {**self.seed_value(version=4), "details": [""]},
                      {**self.seed_value(version=4), "seed_id": "Mayúscula"}):
            with self.subTest(value=value):
                self.assert_error("INVALID_STATE", self.seed, value=value)

    def test_draft_requires_current_seed_and_context(self):
        self.new_topic()
        self.seed()
        self.assert_error("CONFLICT", self.ndraft, seed_sha256="1" * 64)
        self.assert_error("CONFLICT", self.ndraft, context="1" * 64)
        self.assert_error("INVALID_STATE", self.ndraft, seed_id="no-existe", seed_sha256="1" * 64)
        self.assert_error("CONFLICT", self.ndraft, version=2)
        self.ndraft()
        before = self.snapshot()
        with mock.patch.object(narrative_module, "_corpus_lock") as lock:
            self.assertFalse(self.ndraft().created)
        lock.assert_not_called()
        self.assertEqual(self.snapshot(), before)
        self.assert_error("CONFLICT", self.ndraft, text="Otro texto\n")
        self.assert_error("CONFLICT", self.ndraft, version=2)  # repeats v1
        self.assertTrue(self.ndraft(version=2, ooc_notes=()).created)
        # A post after the seed: the seed no longer matches the topic, drafts go STALE.
        self.record_post()
        self.assertTrue(all(v.lifecycle is DraftLifecycle.STALE
                            for v in self.state().replay.draft_views))
        self.assert_error("CONFLICT", self.ndraft, draft_id="nuevo")
        self.assert_error("CONFLICT", self.confirm)

    def test_draft_keeps_channels_apart(self):
        self.ready()
        record = self.state().draft("turno-1", 1)
        self.assertEqual((record.publishable_text, record.ooc_notes, record.private_notes,
                          record.pending_outcomes),
                         ("Aria cruza la plaza.\n", ("Nota OOC",), ("Pienso que...",),
                          ("Respuesta del guardia",)))
        for name in ("Nota OOC", "Pienso que", "Respuesta del guardia"):
            self.assertNotIn(name, record.publishable_text)


class PublicationRulesTest(NarrativeCase):
    def test_publication_conflicts(self):
        self.ready()
        self.assert_error("CONFLICT", self.confirm, draft_sha256="1" * 64)
        self.assert_error("INVALID_STATE", self.confirm, version=2,
                          value=self.publication_value())
        self.assert_error("INVALID_STATE", self.confirm, value={**self.publication_value(),
                                                                "extra": True})
        self.assert_error("INVALID_STATE", self.confirm, value={**self.publication_value(),
                                                                "observed_at": "ayer"})
        self.assert_error("INVALID_STATE", self.confirm, value={**self.publication_value(),
                                                                "published_text": ""})
        self.confirm()
        self.assert_error("CONFLICT", self.confirm, post_id="post-propio-otro")

    def test_publication_port_is_never_used(self):
        self.assertFalse(hasattr(narrative_module, "publish"))
        with mock.patch.object(PublicationPort, "publish") as publish:
            self.ready()
            self.confirm()
        publish.assert_not_called()


class BarrierTest(NarrativeCase):
    def actions(self):
        return (("post", lambda t: self.record_post(terminal=t)),
                ("seed", lambda t: self.seed(terminal=t, seed_id="otra")),
                ("publication", lambda t: self.confirm(terminal=t)))

    def test_wrong_phrase_eof_non_interactive_and_ctrl_c_write_nothing(self):
        self.ready()
        for name, action in self.actions():
            for terminal, code in ((FakeTerminal(transform=lambda p: p.lower() + "\n"),
                                    "INVALID_STATE"),
                                   (FakeTerminal(transform=lambda p: p + " \n"), "INVALID_STATE"),
                                   (FakeTerminal(transform=lambda p: None), "INVALID_STATE"),
                                   (FakeTerminal(interactive=False), "INVALID_STATE")):
                with self.subTest(name=name, terminal=terminal):
                    before = self.snapshot()
                    self.assert_error(code, action, terminal)
                    self.assertEqual(self.snapshot(), before)
            with self.subTest(name=name, interrupt=True):
                def interrupt():
                    raise KeyboardInterrupt

                before = self.snapshot()
                with self.assertRaises(KeyboardInterrupt):
                    action(FakeTerminal(on_read=interrupt))
                self.assertEqual(self.snapshot(), before)
                self.assertFalse(self.topic_lock().exists())

    def test_input_or_topic_changed_during_the_prompt_is_a_conflict(self):
        self.ready()
        names = {"post": "post.json", "seed": "semilla.json", "publication": "publicacion.json"}
        for name, action in self.actions():
            with self.subTest(name=name, change="input"):
                def touch(name=name):
                    path = self.root / names[name]
                    path.write_bytes(path.read_bytes().replace(b"}", b" }"))

                before = self.snapshot()
                self.assert_error("CONFLICT", action, FakeTerminal(on_read=touch))
                self.assertEqual(self.snapshot(), before)
        counter = {"n": 0}
        for name, action in self.actions():
            with self.subTest(name=name, change="topic"):
                def other_writer():
                    counter["n"] += 1
                    self.ndraft(draft_id=f"intruso-{counter['n']}", name="intruso.json",
                                citations=())

                before = counter["n"]
                self.assert_error("CONFLICT", action, FakeTerminal(on_read=other_writer))
                self.assertEqual(counter["n"], before + 1)
                self.assertIsNotNone(self.state().draft(f"intruso-{counter['n']}", 1))

    def test_any_instance_change_during_the_prompt_is_a_conflict(self):
        """REV7A-01: what was shown (character, corpus, other topics) must still hold."""
        self.ready()
        self.new_topic(topic_id="otro-tema", title="Otro")
        counter = {"n": 0}

        def proposal():
            counter["n"] += 1
            self.add(proposal_id=f"carrera-{counter['n']}", text=f"# Aria\nCambio {counter['n']}\n")

        def other_topic():
            counter["n"] += 1
            self.record_post(topic_id="otro-tema", post_id=f"ajeno-{counter['n']}",
                             name="otro.json")

        for change in (proposal, other_topic):
            for name, action in self.actions():
                with self.subTest(name=name, change=change.__name__):
                    before = self.snapshot()
                    self.assert_error("CONFLICT", action, FakeTerminal(on_read=change))
                    self.assertEqual(self.snapshot(), before)
                    self.assertFalse(self.topic_lock().exists())

    def test_vigency_turning_no_during_the_publication_prompt_is_a_conflict(self):
        self.ready()

        def approve():
            self.add(text="# Aria\nExploradora valiente.\n")
            self.decide()

        terminal = FakeTerminal(on_read=approve)
        before = self.snapshot()
        self.assert_error("CONFLICT", self.confirm, terminal=terminal)
        self.assertIn("Composición/ficha vigentes ahora: SÍ\n", terminal.output)
        self.assertEqual(self.snapshot(), before)
        terminal = FakeTerminal()
        self.assertTrue(self.confirm(terminal=terminal).created)
        self.assertIn("Composición/ficha vigentes ahora: NO\n", terminal.output)

    def test_a_read_without_changes_during_the_prompt_still_appends_one_event(self):
        self.ready()
        for name, action in reversed(self.actions()):  # publish before a post moves the topic
            with self.subTest(name=name):
                revision = self.topic().state_revision
                self.assertTrue(action(FakeTerminal(on_read=self.loaded)).created)
                self.assertEqual(self.topic().state_revision, revision + 1)

    def test_locks_and_update_in_progress(self):
        self.ready()
        self.topic_lock().write_bytes(b"")
        for name, action in self.actions():
            with self.subTest(name=name):
                terminal = FakeTerminal()
                self.assert_error("CONFLICT", action, terminal)
                self.assertEqual(terminal.reads, 0)
        self.assert_error("CONFLICT", self.ndraft, draft_id="otro")
        self.topic_lock().unlink()
        update_lock_path(self.instance).write_bytes(b"")
        for name, action in self.actions():
            with self.subTest(name=name, update=True):
                self.assert_error("CONFLICT", action, FakeTerminal())
        self.assert_error("CONFLICT", self.ndraft, draft_id="otro")
        self.assert_error("CONFLICT", self.new_topic, topic_id="otro-tema")
        update_lock_path(self.instance).unlink()

    def test_failed_replace_and_release_keep_guarantees(self):
        self.ready()
        before = self.snapshot()
        with mock.patch.object(persistence.os, "replace", side_effect=OSError("simulado")):
            self.assert_error("IO", self.seed, seed_id="otra")
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.topic_lock().exists())
        real_unlink = assimilation.os.unlink

        def stubborn(path, *args, **kwargs):
            if str(path).endswith(".lock"):
                raise PermissionError("bloqueado")
            return real_unlink(path, *args, **kwargs)

        with mock.patch.object(assimilation.os, "unlink", stubborn):
            error = self.assert_error("IO", self.seed, seed_id="otra")
        self.assertIn("el cambio se guardó", error.reason)
        self.topic_lock().unlink()
        self.assertIsNotNone(self.state().seed("otra", 1))  # the event was not lost


class InputFileTest(NarrativeCase):
    def test_inputs_must_be_regular_external_files_with_strict_json(self):
        self.new_topic()
        for inside in (self.instance / "post.json", ROOT / "CLAUDE.md"):
            with self.subTest(inside=inside):
                if inside.parent == self.instance:
                    inside.write_bytes(json.dumps(self.post_value()).encode())
                error = self.assert_error("INVALID_STATE", record_external_post, self.instance,
                                          expected_core_root=ROOT, topic_id=TOPIC,
                                          input_path=inside, terminal=FakeTerminal())
                if inside.parent == self.instance:
                    inside.unlink()
                else:
                    self.assertIn("dentro de", error.reason)
        raw = json.dumps(self.post_value()).encode()
        for data in (b"\xef\xbb\xbf" + raw, raw.replace(b'"post_id"', b'"post_id": "x", "post_id"'),
                     b'{"post_id": NaN}', b"[]", raw.replace(b'"respuesta-1"', b"1")):
            with self.subTest(data=data[:40]):
                self.assert_error("INVALID_STATE", self.record_post, value=data)
        self.assert_error("INVALID_STATE", self.record_post, value=self.post_value(
            content="con \x00 nulo"))
        self.assert_error("INVALID_STATE", self.record_post, value=self.post_value(
            author="dos\nlíneas"))
        self.assert_error("INVALID_STATE", self.record_post, value=self.post_value(
            observed_at="2026-10-14T20:00:00"))
        missing = self.root / "no-existe.json"
        self.assert_error("INVALID_STATE", record_external_post, self.instance,
                          expected_core_root=ROOT, topic_id=TOPIC, input_path=missing,
                          terminal=FakeTerminal())
        self.assertEqual(self.topic().state_revision, 1)

    @unittest.skipUnless(os.name == "nt", "las junctions son de Windows")
    def test_input_through_a_junction_is_rejected(self):
        import _winapi
        self.new_topic()
        real = self.root / "real"
        real.mkdir()
        (real / "post.json").write_bytes(json.dumps(self.post_value()).encode())
        link = self.root / "enlace"
        try:
            _winapi.CreateJunction(str(real), str(link))
        except OSError as exc:
            self.skipTest(f"no se pudo crear una junction: {exc}")
        self.assert_error("INVALID_STATE", record_external_post, self.instance,
                          expected_core_root=ROOT, topic_id=TOPIC, input_path=link / "post.json",
                          terminal=FakeTerminal())


class TopicCreateTest(NarrativeCase):
    def test_validation_and_missing_character(self):
        self.assert_error("INVALID_STATE", self.new_topic, character_id="nadie")
        for topic_id in ("Mayus", "dos--guiones", "", "con espacio"):
            with self.subTest(topic_id=topic_id):
                self.assert_error("INVALID_STATE", self.new_topic, topic_id=topic_id)
        for title in ("", " espacio", "dos\nlíneas"):
            with self.subTest(title=title):
                self.assert_error("INVALID_STATE", self.new_topic, title=title)
        self.assertFalse((self.instance / "narrative" / "topics" / "mayus").exists())
        self.assert_error("INVALID_STATE", get_topic, self.loaded(), topic_id=TOPIC)

    def test_creation_is_atomic_and_leaves_no_staging(self):
        self.new_topic()
        topics = self.instance / "narrative" / "topics"
        self.assertEqual(sorted(p.name for p in topics.iterdir()), [TOPIC])
        self.assertEqual(sorted(p.name for p in self.topic_root().iterdir()), ["state.json"])
        self.assertEqual(load_state(self.topic_path())[0], 1)

    @unittest.skipUnless(os.name == "nt", "las junctions son de Windows")
    def test_junction_swap_when_appending_writes_nothing_outside(self):
        import _winapi
        self.new_topic()
        real_lock = narrative_module._corpus_lock
        swapped = {}

        def racing_lock(state_path, subject, guard=None):
            aside = self.root / "fuera-tema"
            self.topic_root().rename(aside)
            _winapi.CreateJunction(str(aside), str(self.topic_root()))
            swapped["aside"] = aside
            return real_lock(state_path, subject, guard=guard)

        with mock.patch.object(narrative_module, "_corpus_lock", racing_lock):
            error = self.assert_error("UNSAFE_DESTINATION", self.seed)
        aside = swapped["aside"]
        self.assertEqual(sorted(p.name for p in aside.iterdir()), ["state.json"])
        self.assertEqual(load_state(aside / "state.json")[0], 1)
        self.assertIn("junction", error.reason)


if __name__ == "__main__":
    unittest.main()
