import dataclasses
import unittest

from core.memory.provenance import SourceRef
from core.review import models
from core.review.models import (
    DraftLifecycle,
    DraftVersion,
    PublicationStatus,
    ReviewStateError,
    ReviewStatus,
    approve,
    confirm_publication,
    mark_stale,
    reject,
    retire,
)

SOURCE = SourceRef("turn-7", "topics/scene/sources/turn-7.txt")
APPROVAL = SourceRef("user-approval-1", "user message: approves v2")
REJECTION = SourceRef("user-rejection-1", "user message: rejects v2")
PUBLICATION = SourceRef("post-123", "forum post 123")


def draft(**overrides) -> DraftVersion:
    fields = dict(
        draft_id="scene-reply",
        version=2,
        content="Borrador IC.",
        source_refs=(SOURCE,),
        context_refs=("memory:scene@rev3",),
    )
    fields.update(overrides)
    return DraftVersion(**fields)


class DraftVersionValidationTest(unittest.TestCase):
    def test_defaults_are_active_pending_and_unpublished(self):
        d = draft()
        self.assertIs(d.lifecycle, DraftLifecycle.ACTIVE)
        self.assertIs(d.review_status, ReviewStatus.PENDING_HUMAN_REVIEW)
        self.assertIs(d.publication_status, PublicationStatus.NOT_CONFIRMED)
        self.assertIsNone(d.stale_reason)
        self.assertIsNone(d.review_evidence)
        self.assertIsNone(d.publication_evidence)

    def test_has_no_canon_or_outcome_state(self):
        names = {f.name for f in dataclasses.fields(DraftVersion)}
        self.assertFalse({n for n in names if "canon" in n or "outcome" in n})

    def test_rejects_invalid_version(self):
        for bad in (0, -1, True, 1.0, "2"):
            with self.subTest(version=bad):
                with self.assertRaises(ValueError):
                    draft(version=bad)

    def test_rejects_empty_identity_or_content(self):
        for field in ("draft_id", "content"):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    draft(**{field: "  "})

    def test_requires_at_least_one_source_ref(self):
        with self.assertRaises(ValueError):
            draft(source_refs=())
        with self.assertRaises(ValueError):
            draft(source_refs=[SOURCE])
        with self.assertRaises(ValueError):
            draft(source_refs=("turn-7",))

    def test_context_refs_must_be_non_empty_text(self):
        draft(context_refs=())
        with self.assertRaises(ValueError):
            draft(context_refs=("",))
        with self.assertRaises(ValueError):
            draft(context_refs=["memory:scene"])

    def test_states_must_be_enum_members(self):
        with self.assertRaises(ValueError):
            draft(lifecycle="ACTIVE")
        with self.assertRaises(ValueError):
            draft(review_status="APPROVED", review_evidence=APPROVAL)

    def test_evidence_must_match_status(self):
        incoherent = (
            dict(review_status=ReviewStatus.APPROVED),
            dict(review_status=ReviewStatus.REJECTED),
            dict(review_evidence=APPROVAL),
            dict(publication_status=PublicationStatus.PUBLISHED),
            dict(publication_evidence=PUBLICATION),
            dict(lifecycle=DraftLifecycle.STALE),
            dict(stale_reason="CONTEXT_CHANGED"),
        )
        for overrides in incoherent:
            with self.subTest(**{k: str(v) for k, v in overrides.items()}):
                with self.assertRaises(ReviewStateError):
                    draft(**overrides)

    def test_stale_reason_cannot_be_blank(self):
        with self.assertRaises(ValueError):
            draft(lifecycle=DraftLifecycle.STALE, stale_reason=" ")

    def test_is_immutable(self):
        d = draft()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            d.review_status = ReviewStatus.APPROVED


class ReviewTransitionTest(unittest.TestCase):
    def test_approval_does_not_publish(self):
        approved = approve(draft(), 2, APPROVAL)
        self.assertIs(approved.review_status, ReviewStatus.APPROVED)
        self.assertEqual(approved.review_evidence, APPROVAL)
        self.assertIs(approved.publication_status, PublicationStatus.NOT_CONFIRMED)
        self.assertIsNone(approved.publication_evidence)
        self.assertIs(approved.lifecycle, DraftLifecycle.ACTIVE)

    def test_rejection_only_changes_review(self):
        rejected = reject(draft(), 2, REJECTION)
        self.assertIs(rejected.review_status, ReviewStatus.REJECTED)
        self.assertEqual(rejected.review_evidence, REJECTION)
        self.assertIs(rejected.publication_status, PublicationStatus.NOT_CONFIRMED)
        self.assertIs(rejected.lifecycle, DraftLifecycle.ACTIVE)

    def test_publication_does_not_change_review_or_create_canon(self):
        published = confirm_publication(draft(), 2, PUBLICATION)
        self.assertIs(published.publication_status, PublicationStatus.PUBLISHED)
        self.assertEqual(published.publication_evidence, PUBLICATION)
        self.assertIs(published.review_status, ReviewStatus.PENDING_HUMAN_REVIEW)
        self.assertIsNone(published.review_evidence)
        self.assertEqual(published.content, "Borrador IC.")
        names = {f.name for f in dataclasses.fields(published)}
        self.assertNotIn("canon", names)

    def test_publication_can_be_recorded_without_prior_approval(self):
        published = confirm_publication(draft(), 2, PUBLICATION)
        self.assertIs(published.review_status, ReviewStatus.PENDING_HUMAN_REVIEW)

    def test_stale_keeps_previous_approval_and_publication(self):
        approved = approve(draft(), 2, APPROVAL)
        published = confirm_publication(approved, 2, PUBLICATION)
        stale = mark_stale(published, "CONTEXT_CHANGED")
        self.assertIs(stale.lifecycle, DraftLifecycle.STALE)
        self.assertEqual(stale.stale_reason, "CONTEXT_CHANGED")
        self.assertIs(stale.review_status, ReviewStatus.APPROVED)
        self.assertEqual(stale.review_evidence, APPROVAL)
        self.assertIs(stale.publication_status, PublicationStatus.PUBLISHED)

    def test_mark_stale_requires_reason_and_active_draft(self):
        with self.assertRaises(ValueError):
            mark_stale(draft(), "  ")
        stale = mark_stale(draft(), "CONTEXT_CHANGED")
        with self.assertRaises(ReviewStateError):
            mark_stale(stale, "AGAIN")
        with self.assertRaises(ReviewStateError):
            mark_stale(retire(draft()), "CONTEXT_CHANGED")

    def test_retire_preserves_content_decisions_and_history(self):
        approved = approve(draft(), 2, APPROVAL)
        stale = mark_stale(approved, "CONTEXT_CHANGED")
        retired = retire(stale)
        self.assertIs(retired.lifecycle, DraftLifecycle.RETIRED)
        self.assertEqual(retired.content, approved.content)
        self.assertEqual(retired.source_refs, approved.source_refs)
        self.assertEqual(retired.stale_reason, "CONTEXT_CHANGED")
        self.assertIs(retired.review_status, ReviewStatus.APPROVED)
        self.assertEqual(retired.review_evidence, APPROVAL)
        self.assertIs(stale.lifecycle, DraftLifecycle.STALE)
        with self.assertRaises(ReviewStateError):
            retire(retired)

    def test_retiring_is_not_an_approval(self):
        retired = retire(draft())
        self.assertIs(retired.review_status, ReviewStatus.PENDING_HUMAN_REVIEW)
        self.assertIs(retired.publication_status, PublicationStatus.NOT_CONFIRMED)

    def test_decisions_require_exact_version(self):
        for transition, evidence in ((approve, APPROVAL), (reject, REJECTION),
                                     (confirm_publication, PUBLICATION)):
            for wrong in (1, 3):
                with self.subTest(transition=transition.__name__, expected=wrong):
                    with self.assertRaises(ReviewStateError):
                        transition(draft(), wrong, evidence)

    def test_decisions_require_source_evidence(self):
        for transition in (approve, reject, confirm_publication):
            for bad in (None, "user said yes"):
                with self.subTest(transition=transition.__name__, evidence=bad):
                    with self.assertRaises(ReviewStateError):
                        transition(draft(), 2, bad)

    def test_review_decision_is_final_for_a_version(self):
        approved = approve(draft(), 2, APPROVAL)
        with self.assertRaises(ReviewStateError):
            approve(approved, 2, APPROVAL)
        with self.assertRaises(ReviewStateError):
            reject(approved, 2, REJECTION)

    def test_decision_is_recorded_on_stale_or_retired_draft(self):
        for inactive in (mark_stale(draft(), "CONTEXT_CHANGED"), retire(draft())):
            for transition, evidence, status in ((approve, APPROVAL, ReviewStatus.APPROVED),
                                                 (reject, REJECTION, ReviewStatus.REJECTED)):
                with self.subTest(lifecycle=inactive.lifecycle.value, transition=transition.__name__):
                    decided = transition(inactive, 2, evidence)
                    self.assertIs(decided.review_status, status)
                    self.assertEqual(decided.review_evidence, evidence)
                    self.assertIs(decided.lifecycle, inactive.lifecycle)
                    self.assertEqual(decided.stale_reason, inactive.stale_reason)
                    self.assertIs(decided.publication_status, PublicationStatus.NOT_CONFIRMED)

    def test_decision_does_not_depend_on_order_with_staleness(self):
        approve_first = mark_stale(approve(draft(), 2, APPROVAL), "CONTEXT_CHANGED")
        stale_first = approve(mark_stale(draft(), "CONTEXT_CHANGED"), 2, APPROVAL)
        self.assertEqual(approve_first, stale_first)

    def test_publication_is_recorded_on_stale_or_retired_draft(self):
        for inactive in (mark_stale(draft(), "CONTEXT_CHANGED"), retire(draft()),
                         retire(mark_stale(draft(), "CONTEXT_CHANGED"))):
            with self.subTest(lifecycle=inactive.lifecycle.value, stale_reason=inactive.stale_reason):
                published = confirm_publication(inactive, 2, PUBLICATION)
                self.assertIs(published.publication_status, PublicationStatus.PUBLISHED)
                self.assertEqual(published.publication_evidence, PUBLICATION)
                self.assertIs(published.lifecycle, inactive.lifecycle)
                self.assertEqual(published.stale_reason, inactive.stale_reason)
                self.assertIs(published.review_status, ReviewStatus.PENDING_HUMAN_REVIEW)
                self.assertIsNone(published.review_evidence)
                with self.assertRaises(ReviewStateError):
                    confirm_publication(inactive, 3, PUBLICATION)

    def test_publication_is_confirmed_once(self):
        published = confirm_publication(draft(), 2, PUBLICATION)
        with self.assertRaises(ReviewStateError):
            confirm_publication(published, 2, PUBLICATION)

    def test_three_axes_coexist(self):
        d = mark_stale(confirm_publication(reject(draft(), 2, REJECTION), 2, PUBLICATION),
                       "CONTEXT_CHANGED")
        self.assertEqual(
            (d.lifecycle, d.review_status, d.publication_status),
            (DraftLifecycle.STALE, ReviewStatus.REJECTED, PublicationStatus.PUBLISHED),
        )

    def test_transitions_do_not_mutate_input(self):
        original = draft()
        approve(original, 2, APPROVAL)
        confirm_publication(original, 2, PUBLICATION)
        mark_stale(original, "CONTEXT_CHANGED")
        self.assertEqual(original, draft())

    def test_no_combined_or_implicit_transitions(self):
        public = {name for name in dir(models) if not name.startswith("_")}
        for forbidden in ("approve_and_publish", "publish_and_canonize", "canonize", "publish"):
            self.assertNotIn(forbidden, public)


if __name__ == "__main__":
    unittest.main()
