"""Narrative topics: literal memory of a forum thread for one character (7a).

A topic is an event log in one self-hashed envelope: its header (revision 1), posts by others
transcribed by the person, seeds (ideas the person declares), drafts the agent develops from a
seed on the exact approved character, and manual publications the person confirms afterwards.
The core keeps and verifies content, hashes, links and states. It does not write, summarise,
extract facts or judge style, rules or faithfulness: no event here is an IC fact, canon or a
confirmed outcome. OOC notes, private notes and pending outcomes live in separate fields and are
never joined to the publishable text.

Imports from `core.runtime` are deferred to function bodies: `core.runtime` imports this module.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING
from urllib.parse import quote

from core.character.models import (
    CorpusCandidateRef,
    _check_free_text,
    check_locator,
    check_observed_at,
    parse_observed_at,
    source_record,
)
from core.memory.provenance import SourceRef
from core.review.models import DraftLifecycle, DraftVersion, PublicationStatus, confirm_publication

if TYPE_CHECKING:
    from core.runtime.assimilation import HumanConfirmationReceipt

_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_CODES = frozenset({"INVALID_STATE", "CONFLICT", "UNSAFE_DESTINATION", "IO"})
_CONTENT_KEYS = frozenset({"drafts", "external_posts", "publications", "seeds", "topic"})
_TOPIC_KEYS = frozenset({"character_id", "created_revision", "title", "topic_id"})
_POST_REF_KEYS = frozenset({"content_sha256", "position", "post_id"})
_SOURCE_KEYS = frozenset({"ic_date", "locator", "observed_at", "section_or_passage", "sha256",
                          "source_id"})
_RECEIPT_KEYS = frozenset({"confirmation_sha256", "method"})
_EXTERNAL_KEYS = frozenset({"author_label", "content", "content_sha256", "created_revision",
                            "evidence", "position", "post_id", "post_sha256", "receipt",
                            "utf8_size"})
_SEED_KEYS = frozenset({"beats", "context", "context_sha256", "created_revision", "details",
                        "evidence", "intent", "ooc_constraints", "pending_outcomes", "receipt",
                        "seed_id", "seed_sha256", "tone", "version"})
_SHEET_KEYS = frozenset({"composition_sha256", "draft_sha256", "staff_review_sha256", "version"})
_CITATION_KEYS = frozenset({"candidate_id", "candidate_sha256", "version"})
_DRAFT_KEYS = frozenset({"character_revision", "citations", "composition_sha256", "context",
                         "context_sha256", "created_revision", "draft_id", "draft_sha256",
                         "ooc_notes", "pending_outcomes", "private_notes", "publishable_text",
                         "seed_id", "seed_sha256", "seed_version", "sheet", "target_position",
                         "utf8_size", "version"})
_PUBLICATION_KEYS = frozenset({"content_matches_draft", "content_sha256", "draft_id",
                               "draft_sha256", "draft_version", "evidence", "position", "post_id",
                               "publication_revision", "publication_sha256", "published_text",
                               "receipt", "utf8_size"})
_SEED_LISTS = ("beats", "details", "ooc_constraints", "pending_outcomes")
_DRAFT_LISTS = ("ooc_notes", "private_notes", "pending_outcomes")

CandidateResolver = Callable[[str, int], object]


class NarrativeError(ValueError):
    """`code` is INVALID_STATE, CONFLICT, UNSAFE_DESTINATION or IO."""

    def __init__(self, code: str, reason: str):
        if code not in _CODES:
            raise ValueError(f"unknown narrative error code {code!r}")
        self.code = code
        self.reason = reason
        super().__init__(f"{code}: {reason}")


class PostAuthor(str, Enum):
    OTHER = "OTHER"  # transcribed by the person from someone else's post
    SELF = "SELF"    # the person's own post, confirmed after manual publication


class SeedMode(str, Enum):
    START = "INICIAR"
    CONTINUE = "CONTINUAR"


class DraftPublication(str, Enum):
    NONE = "NONE"
    EXACT = "EXACT"
    EDITED = "EDITED"


# --- validation -------------------------------------------------------------------------------


def check_narrative_id(name: str, value: object) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        _invalid(f"{name} solo admite minúsculas ASCII, dígitos y guiones simples")
    return value


def check_label(name: str, value: object) -> str:
    """One line, no controls, no surrounding spaces (titles, author labels)."""
    if (not isinstance(value, str) or not value.strip() or value != value.strip()
            or _CONTROL.search(value) or value.startswith("﻿")):
        _invalid(f"{name} debe ser una línea de texto sin controles ni espacios en los extremos")
    return value


def _positive(name: str, value: object) -> int:
    if type(value) is not int or value < 1:
        _invalid(f"{name} debe ser un entero positivo")
    return value


def _sha(name: str, value: object) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        _invalid(f"{name} debe ser un SHA-256 en minúsculas")
    return value


def _text_list(name: str, value: object) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        _invalid(f"{name} debe ser una tupla")
    for item in value:
        _free(name, item)
    return value


def _free(name: str, value: object) -> str:
    try:
        return _check_free_text(name, value)
    except ValueError as exc:
        _invalid(getattr(exc, "reason", str(exc)))


def _receipt(value: object, what: str) -> None:
    from core.runtime.assimilation import HumanConfirmationReceipt

    if not isinstance(value, HumanConfirmationReceipt):
        _invalid(f"{what} necesita un recibo de confirmación humana")


def _evidence(value: object, what: str) -> SourceRef:
    if not isinstance(value, SourceRef):
        _invalid(f"{what} necesita evidencia SourceRef")
    return value


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --- models -----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TopicHeader:
    topic_id: str
    character_id: str
    title: str
    created_revision: int = 1

    def __post_init__(self) -> None:
        check_narrative_id("topic_id", self.topic_id)
        check_narrative_id("character_id", self.character_id)
        check_label("el título", self.title)
        if self.created_revision != 1 or type(self.created_revision) is not int:
            _invalid("la cabecera del tema es siempre el evento 1")


@dataclass(frozen=True, slots=True)
class PostRef:
    """A post of the topic by position and exact content: literal context, not a list of facts."""

    post_id: str
    position: int
    content_sha256: str

    def __post_init__(self) -> None:
        check_narrative_id("post_id", self.post_id)
        _positive("position", self.position)
        _sha("content_sha256", self.content_sha256)

    def as_json(self) -> dict[str, object]:
        return {"content_sha256": self.content_sha256, "position": self.position,
                "post_id": self.post_id}


@dataclass(frozen=True, slots=True)
class ExternalPost:
    """Someone else's post as the person transcribed it. The declared author, locator and text
    authenticate neither identity nor consent. `topic_id` is not persisted."""

    topic_id: str
    post_id: str
    position: int
    created_revision: int
    author_label: str
    content: str
    receipt: HumanConfirmationReceipt
    evidence: SourceRef
    utf8_size: int = field(init=False)
    content_sha256: str = field(init=False)
    post_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        check_narrative_id("topic_id", self.topic_id)
        check_narrative_id("post_id", self.post_id)
        _positive("position", self.position)
        _positive("created_revision", self.created_revision)
        check_label("el autor declarado", self.author_label)
        _free("el post ajeno", self.content)
        _receipt(self.receipt, "el post ajeno")
        evidence = _evidence(self.evidence, "el post ajeno")
        object.__setattr__(self, "utf8_size", len(self.content.encode("utf-8")))
        object.__setattr__(self, "content_sha256", text_sha256(self.content))
        _check_source(evidence, f"external-post:{self.topic_id}:{self.post_id}",
                      self.content_sha256, observed=True)
        object.__setattr__(self, "post_sha256", _hash(_without(external_record(self),
                                                               "post_sha256")))

    @property
    def ref(self) -> PostRef:
        return PostRef(self.post_id, self.position, self.content_sha256)


@dataclass(frozen=True, slots=True)
class HumanSeed:
    """Ideas the person declares for one turn: development instructions, never IC facts.

    It captures the topic's posts at that moment: none means starting the topic, one or more
    means continuing it. `topic_id` is not persisted."""

    topic_id: str
    seed_id: str
    version: int
    created_revision: int
    context: tuple[PostRef, ...]
    intent: str
    tone: str
    beats: tuple[str, ...]
    details: tuple[str, ...]
    ooc_constraints: tuple[str, ...]
    pending_outcomes: tuple[str, ...]
    receipt: HumanConfirmationReceipt
    evidence: SourceRef
    context_sha256: str = field(init=False)
    seed_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        check_narrative_id("topic_id", self.topic_id)
        check_narrative_id("seed_id", self.seed_id)
        _positive("la versión de la semilla", self.version)
        _positive("created_revision", self.created_revision)
        _check_context(self.context)
        _free("la intención", self.intent)
        _free("el tono", self.tone)
        for name in _SEED_LISTS:
            _text_list(name, getattr(self, name))
        _receipt(self.receipt, "la semilla")
        evidence = _evidence(self.evidence, "la semilla")
        object.__setattr__(self, "context_sha256", context_sha256(self.context))
        _check_source(evidence, f"human-seed:{self.topic_id}:{self.seed_id}:v{self.version}",
                      _hash(seed_payload(self)), observed=False)
        object.__setattr__(self, "seed_sha256", _hash(_without(seed_record(self),
                                                               "seed_sha256")))

    @property
    def key(self) -> tuple[str, int]:
        return (self.seed_id, self.version)

    @property
    def mode(self) -> SeedMode:
        return SeedMode.CONTINUE if self.context else SeedMode.START


@dataclass(frozen=True, slots=True)
class CharacterSheetRef:
    """The approved sheet a draft was developed on, with its composition and staff response."""

    version: int
    draft_sha256: str
    composition_sha256: str
    staff_review_sha256: str

    def __post_init__(self) -> None:
        _positive("la versión de la ficha", self.version)
        for name in ("draft_sha256", "composition_sha256", "staff_review_sha256"):
            _sha(name, getattr(self, name))

    def as_json(self) -> dict[str, object]:
        return {"composition_sha256": self.composition_sha256, "draft_sha256": self.draft_sha256,
                "staff_review_sha256": self.staff_review_sha256, "version": self.version}


@dataclass(frozen=True, slots=True)
class NarrativeDraftRecord:
    """A complete post developed by the agent outside the core from one seed. Only
    `publishable_text` may be copied; the other channels are never joined to it."""

    topic_id: str
    draft_id: str
    version: int
    created_revision: int
    seed_id: str
    seed_version: int
    seed_sha256: str
    context: tuple[PostRef, ...]
    target_position: int
    character_revision: int
    composition_sha256: str
    sheet: CharacterSheetRef
    citations: tuple[CorpusCandidateRef, ...]
    publishable_text: str
    ooc_notes: tuple[str, ...]
    private_notes: tuple[str, ...]
    pending_outcomes: tuple[str, ...]
    context_sha256: str = field(init=False)
    utf8_size: int = field(init=False)
    draft_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        check_narrative_id("topic_id", self.topic_id)
        check_narrative_id("draft_id", self.draft_id)
        _positive("la versión del borrador", self.version)
        _positive("created_revision", self.created_revision)
        check_narrative_id("seed_id", self.seed_id)
        _positive("seed_version", self.seed_version)
        _sha("seed_sha256", self.seed_sha256)
        _check_context(self.context)
        if self.target_position != len(self.context) + 1:
            _invalid("el borrador debe ocupar la posición siguiente a su contexto")
        _positive("character_revision", self.character_revision)
        _sha("composition_sha256", self.composition_sha256)
        if not isinstance(self.sheet, CharacterSheetRef):
            _invalid("el borrador necesita la ficha aprobada exacta")
        if self.sheet.composition_sha256 != self.composition_sha256:
            _invalid("la ficha citada no corresponde a la composición del borrador")
        if not isinstance(self.citations, tuple) or not all(
            isinstance(c, CorpusCandidateRef) for c in self.citations
        ):
            _invalid("las citas del borrador son inválidas")
        if len({c.key for c in self.citations}) != len(self.citations):
            _invalid("el borrador repite una cita")
        _free("el post", self.publishable_text)
        for name in _DRAFT_LISTS:
            _text_list(name, getattr(self, name))
        object.__setattr__(self, "context_sha256", context_sha256(self.context))
        object.__setattr__(self, "utf8_size", len(self.publishable_text.encode("utf-8")))
        object.__setattr__(self, "draft_sha256", _hash(_without(draft_record(self),
                                                                "draft_sha256")))

    @property
    def key(self) -> tuple[str, int]:
        return (self.draft_id, self.version)

    @property
    def content_sha256(self) -> str:
        return text_sha256(self.publishable_text)


@dataclass(frozen=True, slots=True)
class NarrativePublication:
    """The person confirms, after publishing by hand, the exact text that was published.

    It records an external fact and keeps the final text even when it differs from the draft:
    the original draft is never presented as published if it was edited. `topic_id` is not
    persisted."""

    topic_id: str
    post_id: str
    position: int
    publication_revision: int
    draft_id: str
    draft_version: int
    draft_sha256: str
    published_text: str
    content_matches_draft: bool
    receipt: HumanConfirmationReceipt
    evidence: SourceRef
    utf8_size: int = field(init=False)
    content_sha256: str = field(init=False)
    publication_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        check_narrative_id("topic_id", self.topic_id)
        check_narrative_id("post_id", self.post_id)
        _positive("position", self.position)
        _positive("publication_revision", self.publication_revision)
        check_narrative_id("draft_id", self.draft_id)
        _positive("draft_version", self.draft_version)
        _sha("draft_sha256", self.draft_sha256)
        _free("el texto publicado", self.published_text)
        if type(self.content_matches_draft) is not bool:
            _invalid("content_matches_draft debe ser booleano")
        _receipt(self.receipt, "la publicación")
        evidence = _evidence(self.evidence, "la publicación")
        object.__setattr__(self, "utf8_size", len(self.published_text.encode("utf-8")))
        object.__setattr__(self, "content_sha256", text_sha256(self.published_text))
        _check_source(evidence, f"publication:{self.topic_id}:{self.post_id}",
                      self.content_sha256, observed=True)
        object.__setattr__(self, "publication_sha256",
                           _hash(_without(publication_record(self), "publication_sha256")))

    @property
    def draft_key(self) -> tuple[str, int]:
        return (self.draft_id, self.draft_version)

    @property
    def ref(self) -> PostRef:
        return PostRef(self.post_id, self.position, self.content_sha256)


@dataclass(frozen=True, slots=True)
class NarrativePostView:
    """A post of the topic in position order, transcribed (OTHER) or confirmed (SELF)."""

    position: int
    author: PostAuthor
    source: ExternalPost | NarrativePublication

    @property
    def post_id(self) -> str:
        return self.source.post_id

    @property
    def content(self) -> str:
        return (self.source.content if isinstance(self.source, ExternalPost)
                else self.source.published_text)

    @property
    def ref(self) -> PostRef:
        return self.source.ref


@dataclass(frozen=True, slots=True)
class NarrativeDraftView:
    record: NarrativeDraftRecord
    lifecycle: DraftLifecycle
    publication: DraftPublication
    published: NarrativePublication | None

    def __post_init__(self) -> None:
        if self.lifecycle not in (DraftLifecycle.ACTIVE, DraftLifecycle.STALE):
            _invalid("un borrador narrativo solo puede estar ACTIVE o STALE")
        if (self.publication is DraftPublication.NONE) != (self.published is None):
            _invalid("la relación del borrador con su publicación es incoherente")
        if self.published is not None and (
            self.published.draft_key != self.record.key
            or self.published.draft_sha256 != self.record.draft_sha256
            or self.published.content_matches_draft
            != (self.publication is DraftPublication.EXACT)
        ):
            _invalid("la publicación no corresponde a este borrador")


@dataclass(frozen=True, slots=True)
class LoadedNarrativeTopic:
    topic_root: object  # pathlib.Path; logical location inside the instance
    state_revision: int
    state: "TopicState"


@dataclass(frozen=True, slots=True)
class TopicReplay:
    posts: tuple[NarrativePostView, ...]
    draft_views: tuple[NarrativeDraftView, ...]

    @property
    def context(self) -> tuple[PostRef, ...]:
        return tuple(post.ref for post in self.posts)


@dataclass(frozen=True, slots=True)
class TopicState:
    header: TopicHeader
    external_posts: tuple[ExternalPost, ...] = ()
    seeds: tuple[HumanSeed, ...] = ()
    drafts: tuple[NarrativeDraftRecord, ...] = ()
    publications: tuple[NarrativePublication, ...] = ()
    replay: TopicReplay = field(init=False, compare=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.header, TopicHeader):
            _invalid("el tema necesita su cabecera")
        for name, kind in (("external_posts", ExternalPost), ("seeds", HumanSeed),
                           ("drafts", NarrativeDraftRecord),
                           ("publications", NarrativePublication)):
            items = getattr(self, name)
            if not isinstance(items, tuple) or not all(isinstance(i, kind) for i in items):
                _invalid(f"{name} debe ser una tupla de {kind.__name__}")
            if any(i.topic_id != self.header.topic_id for i in items):
                _invalid(f"un elemento de {name} pertenece a otro tema")
        object.__setattr__(self, "replay", _replay(self))

    @property
    def topic_id(self) -> str:
        return self.header.topic_id

    @property
    def revision(self) -> int:
        return (1 + len(self.external_posts) + len(self.seeds) + len(self.drafts)
                + len(self.publications))

    def seed(self, seed_id: str, version: int) -> HumanSeed | None:
        return next((s for s in self.seeds if s.key == (seed_id, version)), None)

    def latest_seed(self, seed_id: str) -> HumanSeed | None:
        versions = [s for s in self.seeds if s.seed_id == seed_id]
        return versions[-1] if versions else None

    def draft(self, draft_id: str, version: int) -> NarrativeDraftRecord | None:
        return next((d for d in self.drafts if d.key == (draft_id, version)), None)

    def latest_draft(self, draft_id: str) -> NarrativeDraftRecord | None:
        versions = [d for d in self.drafts if d.draft_id == draft_id]
        return versions[-1] if versions else None

    def draft_view(self, draft_id: str, version: int) -> NarrativeDraftView | None:
        return next((v for v in self.replay.draft_views if v.record.key == (draft_id, version)),
                    None)

    def post(self, post_id: str) -> NarrativePostView | None:
        return next((p for p in self.replay.posts if p.post_id == post_id), None)


def seed_semantics(seed: HumanSeed) -> tuple:
    """What the person declared, without version, revision, context, receipt or hashes."""
    return (seed.intent, seed.tone, seed.beats, seed.details, seed.ooc_constraints,
            seed.pending_outcomes)


def draft_semantics(draft: NarrativeDraftRecord) -> tuple:
    """What a draft says and rests on, without version, revision, context or derived hashes."""
    return (draft.seed_id, draft.seed_version, draft.seed_sha256, draft.composition_sha256,
            draft.sheet.version, draft.sheet.draft_sha256, draft.citations,
            draft.publishable_text, draft.ooc_notes, draft.private_notes, draft.pending_outcomes)


def _replay(state: TopicState) -> TopicReplay:
    total = state.revision
    events: dict[int, tuple[str, object]] = {1: ("topic", state.header)}
    for kind, items, attribute in (
        ("external", state.external_posts, "created_revision"),
        ("seed", state.seeds, "created_revision"),
        ("draft", state.drafts, "created_revision"),
        ("publication", state.publications, "publication_revision"),
    ):
        revisions = [getattr(item, attribute) for item in items]
        if revisions != sorted(revisions):
            _invalid("los eventos de cada historial deben estar en orden de revisión")
        for item, revision in zip(items, revisions):
            if revision in events:
                _invalid(f"la revisión {revision} está repetida")
            if not 2 <= revision <= total:
                _invalid("una revisión de evento está fuera del historial")
            events[revision] = (kind, item)
    if len(events) != total:
        _invalid("el historial del tema tiene huecos")

    posts: list[NarrativePostView] = []
    used_ids: set[str] = set()
    seeds: dict[tuple[str, int], HumanSeed] = {}
    latest_seed: dict[str, int] = {}
    drafts: dict[tuple[str, int], NarrativeDraftRecord] = {}
    latest_draft: dict[str, int] = {}
    published: dict[tuple[str, int], NarrativePublication] = {}
    for revision in range(2, total + 1):
        kind, item = events[revision]
        context = tuple(post.ref for post in posts)
        if kind == "external":
            if item.post_id in used_ids or item.position != len(posts) + 1:
                _invalid(f"el post {item.post_id} no ocupa la posición siguiente o está repetido")
            used_ids.add(item.post_id)
            posts.append(NarrativePostView(item.position, PostAuthor.OTHER, item))
        elif kind == "seed":
            if item.version != latest_seed.get(item.seed_id, 0) + 1:
                _invalid(f"la semilla {item.seed_id} salta a la versión {item.version}")
            if item.context != context:
                _invalid(f"la semilla {item.seed_id} v{item.version} no captura el contexto de "
                         "su momento")
            previous = seeds.get((item.seed_id, item.version - 1))
            if previous is not None and (seed_semantics(previous), previous.context) == (
                seed_semantics(item), item.context
            ):
                _invalid(f"la semilla {item.seed_id} v{item.version} repite la anterior")
            latest_seed[item.seed_id] = item.version
            seeds[item.key] = item
        elif kind == "draft":
            seed = seeds.get((item.seed_id, item.seed_version))
            if seed is None or seed.seed_sha256 != item.seed_sha256:
                _invalid(f"el borrador {item.draft_id} no cita una semilla anterior exacta")
            if item.context != context or seed.context != context:
                _invalid(f"el borrador {item.draft_id} v{item.version} no parte del contexto "
                         "vigente de su semilla")
            if item.version != latest_draft.get(item.draft_id, 0) + 1:
                _invalid(f"el borrador {item.draft_id} salta a la versión {item.version}")
            previous = drafts.get((item.draft_id, item.version - 1))
            if previous is not None and (draft_semantics(previous), previous.context) == (
                draft_semantics(item), item.context
            ):
                _invalid(f"el borrador {item.draft_id} v{item.version} repite el anterior")
            latest_draft[item.draft_id] = item.version
            drafts[item.key] = item
        elif kind == "publication":
            draft = drafts.get(item.draft_key)
            if draft is None or draft.draft_sha256 != item.draft_sha256:
                _invalid(f"la publicación {item.post_id} no corresponde a un borrador anterior "
                         "exacto")
            if item.draft_key in published:
                _invalid(f"el borrador {item.draft_id} v{item.draft_version} ya se publicó")
            if draft.context != context or item.position != draft.target_position:
                _invalid(f"la publicación {item.post_id} no ocupa la posición de su borrador")
            if item.post_id in used_ids:
                _invalid(f"el post {item.post_id} está repetido")
            if item.content_matches_draft != (item.published_text == draft.publishable_text):
                _invalid(f"la publicación {item.post_id} no declara bien si coincide con el "
                         "borrador")
            used_ids.add(item.post_id)
            published[item.draft_key] = item
            posts.append(NarrativePostView(item.position, PostAuthor.SELF, item))
    final = tuple(post.ref for post in posts)
    views = []
    for draft in state.drafts:
        publication = published.get(draft.key)
        if publication is None:
            relation = DraftPublication.NONE
        elif publication.content_matches_draft:
            relation = DraftPublication.EXACT
            # Only the exact text counts as the draft published; an edited one never does.
            version = draft_as_review_draft(draft)
            if confirm_publication(version, version.version, publication.evidence
                                   ).publication_status is not PublicationStatus.PUBLISHED:
                _invalid("la publicación exacta no se pudo confirmar")
        else:
            relation = DraftPublication.EDITED
        lifecycle = DraftLifecycle.ACTIVE if draft.context == final else DraftLifecycle.STALE
        views.append(NarrativeDraftView(draft, lifecycle, relation, publication))
    return TopicReplay(tuple(posts), tuple(views))


def draft_as_review_draft(draft: NarrativeDraftRecord) -> DraftVersion:
    """The review-model view of a narrative draft (to apply `confirm_publication`)."""
    source = SourceRef(source_id=f"narrative-draft:{draft.topic_id}:{draft.draft_id}:"
                                 f"v{draft.version}",
                       locator=f"instance://narrative/topics/{draft.topic_id}/drafts/"
                               f"{draft.draft_id}/v{draft.version}",
                       sha256=draft.draft_sha256)
    return DraftVersion(f"narrative:{draft.topic_id}:{draft.draft_id}", draft.version,
                        draft.publishable_text, (source,),
                        (f"context:{draft.context_sha256}",))


# --- factories --------------------------------------------------------------------------------


def make_external_post(*, topic_id: str, post_id: str, position: int, created_revision: int,
                       author_label: str, content: str, locator: str, observed_at: datetime,
                       receipt: HumanConfirmationReceipt) -> ExternalPost:
    _free("el post ajeno", content)
    check_narrative_id("post_id", post_id)
    evidence = SourceRef(source_id=f"external-post:{topic_id}:{post_id}",
                         locator=check_locator(locator), sha256=text_sha256(content),
                         observed_at=check_observed_at(observed_at))
    return ExternalPost(topic_id, post_id, position, created_revision, author_label, content,
                        receipt, evidence)


def make_seed(*, forum_id: str, topic_id: str, seed_id: str, version: int,
              created_revision: int, context: tuple[PostRef, ...], intent: str, tone: str,
              beats: tuple[str, ...], details: tuple[str, ...],
              ooc_constraints: tuple[str, ...], pending_outcomes: tuple[str, ...],
              receipt: HumanConfirmationReceipt) -> HumanSeed:
    check_narrative_id("topic_id", topic_id)
    check_narrative_id("seed_id", seed_id)
    _positive("la versión de la semilla", version)
    probe = _SeedPayload(topic_id, seed_id, version, created_revision, context, intent, tone,
                         beats, details, ooc_constraints, pending_outcomes, receipt)
    segments = "/".join(quote(s, safe="") for s in (topic_id, "seeds", seed_id, f"v{version}"))
    evidence = SourceRef(source_id=f"human-seed:{topic_id}:{seed_id}:v{version}",
                         locator=f"instance://{quote(forum_id, safe='')}/narrative/topics/"
                                 f"{segments}",
                         sha256=_hash(seed_payload(probe)),
                         section_or_passage=f"seed:{seed_id}:v{version}")
    return HumanSeed(topic_id, seed_id, version, created_revision, context, intent, tone, beats,
                     details, ooc_constraints, pending_outcomes, receipt, evidence)


def make_publication(*, topic_id: str, post_id: str, publication_revision: int,
                     draft: NarrativeDraftRecord, published_text: str, locator: str,
                     observed_at: datetime,
                     receipt: HumanConfirmationReceipt) -> NarrativePublication:
    _free("el texto publicado", published_text)
    check_narrative_id("post_id", post_id)
    evidence = SourceRef(source_id=f"publication:{topic_id}:{post_id}",
                         locator=check_locator(locator), sha256=text_sha256(published_text),
                         observed_at=check_observed_at(observed_at))
    return NarrativePublication(topic_id, post_id, draft.target_position, publication_revision,
                                draft.draft_id, draft.version, draft.draft_sha256,
                                published_text, published_text == draft.publishable_text,
                                receipt, evidence)


@dataclass(frozen=True, slots=True)
class _SeedPayload:
    """The fields a seed's evidence hashes, before the evidence exists."""

    topic_id: str
    seed_id: str
    version: int
    created_revision: int
    context: tuple[PostRef, ...]
    intent: str
    tone: str
    beats: tuple[str, ...]
    details: tuple[str, ...]
    ooc_constraints: tuple[str, ...]
    pending_outcomes: tuple[str, ...]
    receipt: HumanConfirmationReceipt


# --- records ----------------------------------------------------------------------------------


def context_sha256(context: tuple[PostRef, ...]) -> str:
    return _hash([ref.as_json() for ref in context])


def topic_record(header: TopicHeader) -> dict[str, object]:
    return {"character_id": header.character_id, "created_revision": header.created_revision,
            "title": header.title, "topic_id": header.topic_id}


def external_record(post: ExternalPost) -> dict[str, object]:
    return {
        "author_label": post.author_label,
        "content": post.content,
        "content_sha256": post.content_sha256,
        "created_revision": post.created_revision,
        "evidence": source_record(post.evidence),
        "position": post.position,
        "post_id": post.post_id,
        "post_sha256": getattr(post, "post_sha256", None),
        "receipt": _receipt_record(post.receipt),
        "utf8_size": post.utf8_size,
    }


def seed_payload(seed) -> dict[str, object]:
    """What a seed's evidence hashes: every persisted field except the evidence and the hash."""
    return {
        "beats": list(seed.beats),
        "context": [ref.as_json() for ref in seed.context],
        "context_sha256": context_sha256(seed.context),
        "created_revision": seed.created_revision,
        "details": list(seed.details),
        "intent": seed.intent,
        "ooc_constraints": list(seed.ooc_constraints),
        "pending_outcomes": list(seed.pending_outcomes),
        "receipt": _receipt_record(seed.receipt),
        "seed_id": seed.seed_id,
        "tone": seed.tone,
        "version": seed.version,
    }


def seed_record(seed: HumanSeed) -> dict[str, object]:
    return {**seed_payload(seed), "evidence": source_record(seed.evidence),
            "seed_sha256": getattr(seed, "seed_sha256", None)}


def draft_record(draft: NarrativeDraftRecord) -> dict[str, object]:
    return {
        "character_revision": draft.character_revision,
        "citations": [c.as_json() for c in draft.citations],
        "composition_sha256": draft.composition_sha256,
        "context": [ref.as_json() for ref in draft.context],
        "context_sha256": draft.context_sha256,
        "created_revision": draft.created_revision,
        "draft_id": draft.draft_id,
        "draft_sha256": getattr(draft, "draft_sha256", None),
        "ooc_notes": list(draft.ooc_notes),
        "pending_outcomes": list(draft.pending_outcomes),
        "private_notes": list(draft.private_notes),
        "publishable_text": draft.publishable_text,
        "seed_id": draft.seed_id,
        "seed_sha256": draft.seed_sha256,
        "seed_version": draft.seed_version,
        "sheet": draft.sheet.as_json(),
        "target_position": draft.target_position,
        "utf8_size": draft.utf8_size,
        "version": draft.version,
    }


def publication_record(publication: NarrativePublication) -> dict[str, object]:
    return {
        "content_matches_draft": publication.content_matches_draft,
        "content_sha256": publication.content_sha256,
        "draft_id": publication.draft_id,
        "draft_sha256": publication.draft_sha256,
        "draft_version": publication.draft_version,
        "evidence": source_record(publication.evidence),
        "position": publication.position,
        "post_id": publication.post_id,
        "publication_revision": publication.publication_revision,
        "publication_sha256": getattr(publication, "publication_sha256", None),
        "published_text": publication.published_text,
        "receipt": _receipt_record(publication.receipt),
        "utf8_size": publication.utf8_size,
    }


# --- public serializers (persisted fields plus documented derived state; receipts carry no nonce)


def topic_summary(state: TopicState) -> dict[str, object]:
    return {**topic_record(state.header), "context_sha256": context_sha256(state.replay.context),
            "draft_count": len(state.drafts), "post_count": len(state.replay.posts),
            "publication_count": len(state.publications), "revision": state.revision,
            "seed_count": len(state.seeds)}


def post_summary(view: NarrativePostView) -> dict[str, object]:
    source = view.source
    record = (external_record(source) if isinstance(source, ExternalPost)
              else publication_record(source))
    return {**record, "author": view.author.value}


def seed_summary(seed: HumanSeed) -> dict[str, object]:
    return {**seed_record(seed), "mode": seed.mode.value}


def narrative_draft_summary(view: NarrativeDraftView) -> dict[str, object]:
    return {**draft_record(view.record), "lifecycle": view.lifecycle.value,
            "publication": view.publication.value,
            "published_post_id": None if view.published is None else view.published.post_id}


def publication_summary(publication: NarrativePublication) -> dict[str, object]:
    return publication_record(publication)


def encode_topic_content(state: TopicState) -> dict[str, object]:
    return {
        "drafts": [draft_record(d) for d in state.drafts],
        "external_posts": [external_record(p) for p in state.external_posts],
        "publications": [publication_record(p) for p in state.publications],
        "seeds": [seed_record(s) for s in state.seeds],
        "topic": topic_record(state.header),
    }


def decode_topic_state(content: object, *, forum_id: str, revision: int,
                       candidate_resolver: CandidateResolver,
                       sheet_check: Callable[[str, CharacterSheetRef, int], None]
                       ) -> TopicState:
    """Rebuild a topic, recompute every hash and evidence and replay its event log.

    `candidate_resolver(candidate_id, version)` returns the current APPROVED candidate or raises;
    `sheet_check(character_id, sheet, character_revision)` raises unless that approved sheet,
    composition and staff response exist in the character's history.
    """
    from core.runtime.assimilation import AssimilationError, HumanConfirmationReceipt

    if type(revision) is not int or revision < 1:
        _invalid("la revisión del tema debe ser un entero positivo")
    if not isinstance(content, dict) or set(content) != _CONTENT_KEYS:
        _invalid("el tema no tiene exactamente las claves esperadas")
    for name in ("drafts", "external_posts", "publications", "seeds"):
        if not isinstance(content[name], list):
            _invalid(f"{name} debe ser una lista")
    topic = content["topic"]
    if not isinstance(topic, dict) or set(topic) != _TOPIC_KEYS:
        _invalid("la cabecera del tema tiene claves inesperadas")
    header = TopicHeader(topic["topic_id"], topic["character_id"], topic["title"],
                         topic["created_revision"])
    topic_id = header.topic_id

    def receipt_of(value: object, where: str):
        if not isinstance(value, dict) or set(value) != _RECEIPT_KEYS:
            _invalid(f"{where}: recibo con claves inesperadas")
        try:
            return HumanConfirmationReceipt(value["method"], value["confirmation_sha256"])
        except AssimilationError as exc:
            _invalid(f"{where}: {exc.reason}")

    def evidence_of(value: object, where: str) -> tuple[str, datetime | None]:
        if not isinstance(value, dict) or set(value) != _SOURCE_KEYS:
            _invalid(f"{where}: evidencia con claves inesperadas")
        observed = value["observed_at"]
        return value["locator"], None if observed is None else parse_observed_at(observed)

    def context_of(value: object, where: str) -> tuple[PostRef, ...]:
        if not isinstance(value, list) or not all(
            isinstance(r, dict) and set(r) == _POST_REF_KEYS for r in value
        ):
            _invalid(f"{where}: contexto con claves inesperadas")
        return tuple(PostRef(r["post_id"], r["position"], r["content_sha256"]) for r in value)

    def texts(value: object, where: str) -> tuple[str, ...]:
        if not isinstance(value, list):
            _invalid(f"{where}: se esperaba una lista de textos")
        return tuple(value)

    external = []
    for position, record in enumerate(content["external_posts"], start=1):
        where = f"post ajeno {position}"
        if not isinstance(record, dict) or set(record) != _EXTERNAL_KEYS:
            _invalid(f"{where}: claves inesperadas")
        locator, observed = evidence_of(record["evidence"], where)
        post = make_external_post(topic_id=topic_id, post_id=record["post_id"],
                                  position=record["position"],
                                  created_revision=record["created_revision"],
                                  author_label=record["author_label"], content=record["content"],
                                  locator=locator, observed_at=observed,
                                  receipt=receipt_of(record["receipt"], where))
        if external_record(post) != record:
            _invalid(f"{where}: se modificó fuera del core")
        external.append(post)

    seeds = []
    for position, record in enumerate(content["seeds"], start=1):
        where = f"semilla {position}"
        if not isinstance(record, dict) or set(record) != _SEED_KEYS:
            _invalid(f"{where}: claves inesperadas")
        seed = make_seed(forum_id=forum_id, topic_id=topic_id, seed_id=record["seed_id"],
                         version=record["version"], created_revision=record["created_revision"],
                         context=context_of(record["context"], where), intent=record["intent"],
                         tone=record["tone"], beats=texts(record["beats"], where),
                         details=texts(record["details"], where),
                         ooc_constraints=texts(record["ooc_constraints"], where),
                         pending_outcomes=texts(record["pending_outcomes"], where),
                         receipt=receipt_of(record["receipt"], where))
        if seed_record(seed) != record:
            _invalid(f"{where}: se modificó fuera del core")
        seeds.append(seed)

    drafts = []
    for position, record in enumerate(content["drafts"], start=1):
        where = f"borrador {position}"
        if not isinstance(record, dict) or set(record) != _DRAFT_KEYS:
            _invalid(f"{where}: claves inesperadas")
        sheet = record["sheet"]
        if not isinstance(sheet, dict) or set(sheet) != _SHEET_KEYS:
            _invalid(f"{where}: ficha con claves inesperadas")
        citations = record["citations"]
        if not isinstance(citations, list) or not all(
            isinstance(c, dict) and set(c) == _CITATION_KEYS for c in citations
        ):
            _invalid(f"{where}: citas con claves inesperadas")
        refs = tuple(CorpusCandidateRef(c["candidate_id"], c["version"], c["candidate_sha256"])
                     for c in citations)
        for ref in refs:
            try:
                candidate = candidate_resolver(ref.candidate_id, ref.version)
            except ValueError as exc:
                _invalid(f"{where}: la cita {ref.candidate_id} v{ref.version} no es una versión "
                         f"vigente aprobada ({getattr(exc, 'reason', exc)})")
            if candidate.candidate_sha256 != ref.candidate_sha256:
                _invalid(f"{where}: la cita {ref.candidate_id} v{ref.version} no coincide con "
                         "el corpus")
        draft = NarrativeDraftRecord(
            topic_id, record["draft_id"], record["version"], record["created_revision"],
            record["seed_id"], record["seed_version"], record["seed_sha256"],
            context_of(record["context"], where), record["target_position"],
            record["character_revision"], record["composition_sha256"],
            CharacterSheetRef(sheet["version"], sheet["draft_sha256"],
                              sheet["composition_sha256"], sheet["staff_review_sha256"]),
            refs, record["publishable_text"], texts(record["ooc_notes"], where),
            texts(record["private_notes"], where), texts(record["pending_outcomes"], where))
        if draft_record(draft) != record:
            _invalid(f"{where}: se modificó fuera del core")
        try:
            sheet_check(header.character_id, draft.sheet, draft.character_revision)
        except ValueError as exc:
            _invalid(f"{where}: la ficha citada no es válida ({getattr(exc, 'reason', exc)})")
        drafts.append(draft)

    by_key = {d.key: d for d in drafts}
    publications = []
    for position, record in enumerate(content["publications"], start=1):
        where = f"publicación {position}"
        if not isinstance(record, dict) or set(record) != _PUBLICATION_KEYS:
            _invalid(f"{where}: claves inesperadas")
        draft = by_key.get((check_narrative_id("draft_id", record["draft_id"]),
                            _positive("draft_version", record["draft_version"])))
        if draft is None:
            _invalid(f"{where}: no corresponde a ningún borrador")
        locator, observed = evidence_of(record["evidence"], where)
        publication = make_publication(topic_id=topic_id, post_id=record["post_id"],
                                       publication_revision=record["publication_revision"],
                                       draft=draft, published_text=record["published_text"],
                                       locator=locator, observed_at=observed,
                                       receipt=receipt_of(record["receipt"], where))
        if publication_record(publication) != record:
            _invalid(f"{where}: se modificó fuera del core")
        publications.append(publication)

    state = TopicState(header, tuple(external), tuple(seeds), tuple(drafts),
                       tuple(publications))
    if state.revision != revision:
        _invalid("la revisión del tema no corresponde a su historial")
    return state


# --- helpers ----------------------------------------------------------------------------------


def _check_context(context: object) -> None:
    if not isinstance(context, tuple) or not all(isinstance(r, PostRef) for r in context):
        _invalid("el contexto debe ser una tupla de PostRef")
    if [r.position for r in context] != list(range(1, len(context) + 1)):
        _invalid("el contexto debe cubrir las posiciones 1..K en orden")
    if len({r.post_id for r in context}) != len(context):
        _invalid("el contexto repite un post")


def _check_source(evidence: SourceRef, source_id: str, sha256: str, *, observed: bool) -> None:
    if (evidence.source_id, evidence.sha256, evidence.ic_date) != (source_id, sha256, None):
        _invalid(f"la evidencia no corresponde a {source_id}")
    if observed:
        check_locator(evidence.locator)
        if evidence.observed_at is None:
            _invalid("la evidencia necesita la fecha en que se observó")
        check_observed_at(evidence.observed_at)


def _receipt_record(receipt) -> dict[str, object]:
    return {"confirmation_sha256": receipt.confirmation_sha256, "method": receipt.method}


def _without(record: dict, key: str) -> dict:
    return {k: v for k, v in record.items() if k != key}


def _hash(value: object) -> str:
    from core.runtime.persistence import canonical_json_bytes

    return hashlib.sha256(canonical_json_bytes(value, pretty=False)).hexdigest()


def _invalid(reason: str) -> None:
    raise NarrativeError("INVALID_STATE", reason)
