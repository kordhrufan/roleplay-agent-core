"""Draft review states.

Lifecycle (freshness), human review and publication are independent axes: approving does not
publish, publishing does not approve or create canon, and staleness does not undo a decision.
Every transition returns a new `DraftVersion`; the previous value is never mutated.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from core.memory.provenance import SourceRef


class DraftLifecycle(str, Enum):
    ACTIVE = "ACTIVE"
    STALE = "STALE"
    RETIRED = "RETIRED"


class ReviewStatus(str, Enum):
    PENDING_HUMAN_REVIEW = "PENDING_HUMAN_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class PublicationStatus(str, Enum):
    NOT_CONFIRMED = "NOT_CONFIRMED"
    PUBLISHED = "PUBLISHED"


class ReviewStateError(ValueError):
    """A draft state is incoherent or a transition is not allowed."""


@dataclass(frozen=True, slots=True)
class DraftVersion:
    draft_id: str
    version: int
    content: str
    source_refs: tuple[SourceRef, ...]
    context_refs: tuple[str, ...]
    lifecycle: DraftLifecycle = DraftLifecycle.ACTIVE
    review_status: ReviewStatus = ReviewStatus.PENDING_HUMAN_REVIEW
    publication_status: PublicationStatus = PublicationStatus.NOT_CONFIRMED
    stale_reason: str | None = None
    review_evidence: SourceRef | None = None
    publication_evidence: SourceRef | None = None

    def __post_init__(self) -> None:
        _require_text("draft_id", self.draft_id)
        _require_text("content", self.content)
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise ValueError("version must be a positive integer")
        if not isinstance(self.source_refs, tuple) or not self.source_refs:
            raise ValueError("source_refs must be a non-empty tuple")
        if not all(isinstance(ref, SourceRef) for ref in self.source_refs):
            raise ValueError("source_refs must contain only SourceRef values")
        if not isinstance(self.context_refs, tuple):
            raise ValueError("context_refs must be a tuple")
        for ref in self.context_refs:
            _require_text("context_refs item", ref)
        _require_member("lifecycle", self.lifecycle, DraftLifecycle)
        _require_member("review_status", self.review_status, ReviewStatus)
        _require_member("publication_status", self.publication_status, PublicationStatus)
        self._check_coherence()

    def _check_coherence(self) -> None:
        if self.lifecycle is DraftLifecycle.ACTIVE and self.stale_reason is not None:
            raise ReviewStateError("an ACTIVE draft cannot have a stale_reason")
        if self.lifecycle is DraftLifecycle.STALE and self.stale_reason is None:
            raise ReviewStateError("a STALE draft requires a stale_reason")
        if self.stale_reason is not None:
            _require_text("stale_reason", self.stale_reason)
        _check_evidence(
            "review",
            self.review_status is ReviewStatus.PENDING_HUMAN_REVIEW,
            self.review_evidence,
        )
        _check_evidence(
            "publication",
            self.publication_status is PublicationStatus.NOT_CONFIRMED,
            self.publication_evidence,
        )


def approve(draft: DraftVersion, expected_version: int, evidence: SourceRef) -> DraftVersion:
    """Record a human approval of exactly `expected_version`. Does not publish.

    A decision is a fact about the version, recorded whatever its lifecycle; whether the draft
    is still usable is told by the lifecycle axis, not by refusing the decision.
    """
    _check_decidable(draft, expected_version, evidence)
    return replace(draft, review_status=ReviewStatus.APPROVED, review_evidence=evidence)


def reject(draft: DraftVersion, expected_version: int, evidence: SourceRef) -> DraftVersion:
    """Record a human rejection of exactly `expected_version`."""
    _check_decidable(draft, expected_version, evidence)
    return replace(draft, review_status=ReviewStatus.REJECTED, review_evidence=evidence)


def mark_stale(draft: DraftVersion, reason: str) -> DraftVersion:
    """Flag an ACTIVE draft whose context changed. Keeps review and publication as they are."""
    _require_text("reason", reason)
    if draft.lifecycle is not DraftLifecycle.ACTIVE:
        raise ReviewStateError(f"only an ACTIVE draft can become STALE, not {draft.lifecycle.value}")
    return replace(draft, lifecycle=DraftLifecycle.STALE, stale_reason=reason)


def retire(draft: DraftVersion) -> DraftVersion:
    """Withdraw a draft from use. Content, decisions and evidence are preserved."""
    if draft.lifecycle is DraftLifecycle.RETIRED:
        raise ReviewStateError("draft is already RETIRED")
    return replace(draft, lifecycle=DraftLifecycle.RETIRED)


def confirm_publication(
    draft: DraftVersion, expected_version: int, evidence: SourceRef
) -> DraftVersion:
    """Record that exactly `expected_version` was published, with its evidence.

    Publication is an external fact: it is recorded whatever the review status or lifecycle
    (text already published may be imported without a prior approval). It does not approve the
    draft, consolidate memory or confirm outcomes that belong to other participants.
    """
    _check_version(draft, expected_version)
    _require_evidence(evidence)
    if draft.publication_status is PublicationStatus.PUBLISHED:
        raise ReviewStateError("publication is already confirmed for this version")
    return replace(
        draft, publication_status=PublicationStatus.PUBLISHED, publication_evidence=evidence
    )


def _check_decidable(draft: DraftVersion, expected_version: int, evidence: SourceRef) -> None:
    _check_version(draft, expected_version)
    _require_evidence(evidence)
    if draft.review_status is not ReviewStatus.PENDING_HUMAN_REVIEW:
        raise ReviewStateError(f"review already decided: {draft.review_status.value}")


def _check_version(draft: DraftVersion, expected_version: int) -> None:
    if draft.version != expected_version:
        raise ReviewStateError(
            f"version mismatch: draft is v{draft.version}, decision is for v{expected_version}"
        )


def _require_evidence(evidence: object) -> None:
    if not isinstance(evidence, SourceRef):
        raise ReviewStateError("evidence must be a SourceRef")


def _check_evidence(axis: str, pending: bool, evidence: SourceRef | None) -> None:
    if pending and evidence is not None:
        raise ReviewStateError(f"{axis} evidence present without a {axis} decision")
    if not pending and not isinstance(evidence, SourceRef):
        raise ReviewStateError(f"{axis} status requires SourceRef evidence")


def _require_member(name: str, value: object, enum: type[Enum]) -> None:
    if not isinstance(value, enum):
        raise ValueError(f"{name} must be a {enum.__name__}")


def _require_text(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
