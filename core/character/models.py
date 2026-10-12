"""Character state inside a forum instance: human concepts, agent proposals and human decisions.

The concept is free Markdown kept character by character. Every concept version and every
decision on a proposal is adopted by a person through barrier A (a typed phrase in an interactive
terminal); that records explicit human adoption, not who originally wrote the text. Proposals
are complete alternative compositions written by the agent; they never change anything until a
person approves them, and approving only composes the character design: it is not staff
approval, learning, usability, publication or canon.

The state is an event log: every concept, proposal and decision takes exactly one revision of
the state envelope. The effective composition is derived by replaying that log; it is never
stored, so there is a single authority.

Imports from `core.runtime` are deferred to function bodies: `core.runtime` imports this module.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import quote

from core.memory.provenance import SourceRef
from core.review.models import ReviewStatus

if TYPE_CHECKING:
    from core.runtime.assimilation import AssimilationCandidate, HumanConfirmationReceipt

_CHARACTER_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_FORBIDDEN_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_CODES = frozenset({"INVALID_STATE", "CONFLICT", "UNSAFE_DESTINATION", "IO"})
_CONTENT_KEYS = frozenset({"character_id", "concepts", "proposal_decisions", "proposals"})
_CONCEPT_KEYS = frozenset({"authorship", "concept_sha256", "evidence", "receipt", "text",
                           "utf8_size", "version"})
_EVIDENCE_KEYS = frozenset({"locator", "section_or_passage", "sha256", "source_id"})
_RECEIPT_KEYS = frozenset({"confirmation_sha256", "method"})
_CONCEPT_REF_KEYS = frozenset({"concept_sha256", "version"})
_CITATION_KEYS = frozenset({"candidate_id", "candidate_sha256", "version"})
_PROPOSAL_KEYS = frozenset({"base_composition_sha256", "citations", "concept", "created_revision",
                            "proposal_id", "proposal_sha256", "rationale",
                            "result_composition_sha256", "text", "utf8_size", "version"})
_DECISION_KEYS = frozenset({"base_composition_sha256", "decision_id", "decision_revision",
                            "evidence", "proposal_id", "proposal_sha256", "proposal_version",
                            "receipt", "result_composition_sha256", "review_status"})

CandidateResolver = Callable[[str, int], "AssimilationCandidate"]


class CharacterError(ValueError):
    """`code` is INVALID_STATE, CONFLICT, UNSAFE_DESTINATION or IO."""

    def __init__(self, code: str, reason: str):
        if code not in _CODES:
            raise ValueError(f"unknown character error code {code!r}")
        self.code = code
        self.reason = reason
        super().__init__(f"{code}: {reason}")


class ConceptAuthorship(str, Enum):
    HUMAN_DECLARED = "HUMAN_DECLARED"


class ProposalStatus(str, Enum):
    """A derived view, never persisted."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    OBSOLETE = "OBSOLETE"


def check_character_id(value: object) -> str:
    if not isinstance(value, str) or not _CHARACTER_ID.fullmatch(value):
        _invalid("el ID del personaje solo admite minúsculas ASCII, dígitos y guiones simples "
                 "(p. ej. «mi-personaje»)")
    return value


def check_concept_text(text: object) -> str:
    """Free text kept exactly: TAB/CR/LF allowed, other controls and NUL rejected."""
    return _check_free_text("el concepto", text)


def _check_free_text(name: str, text: object) -> str:
    if not isinstance(text, str) or not text.strip():
        _invalid(f"{name} no puede estar vacío")
    if text.startswith("﻿"):
        _invalid(f"{name} empieza con BOM; guárdalo como UTF-8 sin BOM")
    if _FORBIDDEN_CONTROL.search(text):
        _invalid(f"{name} contiene caracteres de control (solo se admiten tabulador y saltos de "
                 "línea)")
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        _invalid(f"{name} contiene caracteres que no se pueden guardar en UTF-8")
    return text


def _check_id(name: str, value: object) -> str:
    if not isinstance(value, str) or not _CHARACTER_ID.fullmatch(value):
        _invalid(f"{name} solo admite minúsculas ASCII, dígitos y guiones simples")
    return value


def _check_positive(name: str, value: object) -> int:
    if type(value) is not int or value < 1:
        _invalid(f"{name} debe ser un entero positivo")
    return value


def _check_decision_status(value: object) -> ReviewStatus:
    if not isinstance(value, ReviewStatus) or value not in (ReviewStatus.APPROVED,
                                                            ReviewStatus.REJECTED):
        _invalid("una decisión sobre una propuesta solo puede ser APPROVED o REJECTED")
    return value


def _check_sha256(name: str, value: object) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        _invalid(f"{name} debe ser un SHA-256 en minúsculas")
    return value


# --- Concepts (4d1) ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ConceptVersion:
    version: int
    text: str
    authorship: ConceptAuthorship
    receipt: HumanConfirmationReceipt
    evidence: SourceRef
    concept_sha256: str = field(init=False)
    utf8_size: int = field(init=False)

    def __post_init__(self) -> None:
        from core.runtime.assimilation import HumanConfirmationReceipt

        if type(self.version) is not int or self.version < 1:
            _invalid("la versión del concepto debe ser un entero positivo")
        check_concept_text(self.text)
        if not isinstance(self.authorship, ConceptAuthorship):
            _invalid("autoría desconocida")
        if not isinstance(self.receipt, HumanConfirmationReceipt):
            _invalid("el concepto necesita un recibo de confirmación humana")
        if not isinstance(self.evidence, SourceRef):
            _invalid("el concepto necesita evidencia SourceRef")
        data = self.text.encode("utf-8")
        object.__setattr__(self, "concept_sha256", hashlib.sha256(data).hexdigest())
        object.__setattr__(self, "utf8_size", len(data))

    @property
    def ref(self) -> ConceptRef:
        return ConceptRef(self.version, self.concept_sha256)


# --- Proposals and decisions (4d2) ------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ConceptRef:
    version: int
    concept_sha256: str

    def __post_init__(self) -> None:
        _check_positive("la versión del concepto citado", self.version)
        _check_sha256("concept_sha256", self.concept_sha256)

    def as_json(self) -> dict[str, object]:
        return {"concept_sha256": self.concept_sha256, "version": self.version}


@dataclass(frozen=True, slots=True)
class CorpusCandidateRef:
    """A current APPROVED candidate of the closed snapshot; resolved via get_approved_candidate."""

    candidate_id: str
    version: int
    candidate_sha256: str

    def __post_init__(self) -> None:
        _check_id("candidate_id", self.candidate_id)
        _check_positive("la versión del candidato citado", self.version)
        _check_sha256("candidate_sha256", self.candidate_sha256)

    @property
    def key(self) -> tuple[str, int]:
        return (self.candidate_id, self.version)

    def as_json(self) -> dict[str, object]:
        return {"candidate_id": self.candidate_id, "candidate_sha256": self.candidate_sha256,
                "version": self.version}


@dataclass(frozen=True, slots=True)
class CharacterProposal:
    """A complete alternative composition written by the agent (never a patch)."""

    character_id: str
    proposal_id: str
    version: int
    created_revision: int
    concept: ConceptRef
    base_composition_sha256: str
    text: str
    rationale: str
    citations: tuple[CorpusCandidateRef, ...]
    proposal_sha256: str = field(init=False)
    result_composition_sha256: str = field(init=False)
    utf8_size: int = field(init=False)

    def __post_init__(self) -> None:
        check_character_id(self.character_id)
        _check_id("proposal_id", self.proposal_id)
        _check_positive("la versión de la propuesta", self.version)
        _check_positive("created_revision", self.created_revision)
        if not isinstance(self.concept, ConceptRef):
            _invalid("la propuesta debe citar un concepto")
        _check_sha256("base_composition_sha256", self.base_composition_sha256)
        _check_free_text("el texto de la propuesta", self.text)
        _check_free_text("el motivo de la propuesta", self.rationale)
        if not isinstance(self.citations, tuple) or not self.citations or not all(
            isinstance(c, CorpusCandidateRef) for c in self.citations
        ):
            _invalid("la propuesta necesita al menos una cita del corpus aprobado")
        if len({c.key for c in self.citations}) != len(self.citations):
            _invalid("la propuesta repite una cita")
        object.__setattr__(self, "utf8_size", len(self.text.encode("utf-8")))
        object.__setattr__(self, "proposal_sha256", _hash(_proposal_core(self)))
        object.__setattr__(self, "result_composition_sha256", _hash({
            "base_composition_sha256": self.base_composition_sha256,
            "character_id": self.character_id,
            "concept": self.concept.as_json(),
            "proposal": {"proposal_id": self.proposal_id,
                         "proposal_sha256": self.proposal_sha256, "version": self.version},
            "text": self.text,
        }))

    @property
    def key(self) -> tuple[str, int]:
        return (self.proposal_id, self.version)


@dataclass(frozen=True, slots=True)
class CharacterProposalDecision:
    decision_id: str
    decision_revision: int
    proposal_id: str
    proposal_version: int
    proposal_sha256: str
    base_composition_sha256: str
    result_composition_sha256: str
    review_status: ReviewStatus
    receipt: HumanConfirmationReceipt
    evidence: SourceRef

    def __post_init__(self) -> None:
        from core.runtime.assimilation import HumanConfirmationReceipt

        _check_id("proposal_id", self.proposal_id)
        _check_positive("proposal_version", self.proposal_version)
        if self.decision_id != f"proposal:{self.proposal_id}:v{self.proposal_version}":
            _invalid("decision_id no corresponde a la propuesta y su versión")
        _check_positive("decision_revision", self.decision_revision)
        for name in ("proposal_sha256", "base_composition_sha256", "result_composition_sha256"):
            _check_sha256(name, getattr(self, name))
        _check_decision_status(self.review_status)
        if not isinstance(self.receipt, HumanConfirmationReceipt):
            _invalid("la decisión necesita un recibo de confirmación humana")
        if not isinstance(self.evidence, SourceRef):
            _invalid("la decisión necesita evidencia SourceRef")

    @property
    def proposal_key(self) -> tuple[str, int]:
        return (self.proposal_id, self.proposal_version)

    def matches(self, proposal: CharacterProposal) -> bool:
        return (self.proposal_key == proposal.key
                and self.proposal_sha256 == proposal.proposal_sha256
                and self.base_composition_sha256 == proposal.base_composition_sha256
                and self.result_composition_sha256 == proposal.result_composition_sha256)


@dataclass(frozen=True, slots=True)
class AppliedProposal:
    proposal: CharacterProposal
    decision: CharacterProposalDecision

    def __post_init__(self) -> None:
        if not isinstance(self.proposal, CharacterProposal) or not isinstance(
            self.decision, CharacterProposalDecision
        ):
            _invalid("paso aplicado inválido")
        if not self.decision.matches(self.proposal):
            _invalid("la decisión no corresponde a la propuesta aplicada")
        if self.decision.review_status is not ReviewStatus.APPROVED:
            _invalid("solo una propuesta aprobada puede aplicarse")


@dataclass(frozen=True, slots=True)
class EffectiveComposition:
    character_id: str
    concept: ConceptRef
    text: str
    composition_sha256: str
    applied_proposals: tuple[AppliedProposal, ...]

    def __post_init__(self) -> None:
        check_character_id(self.character_id)
        if not isinstance(self.concept, ConceptRef):
            _invalid("la composición necesita su concepto")
        _check_free_text("la composición", self.text)
        _check_sha256("composition_sha256", self.composition_sha256)
        if not isinstance(self.applied_proposals, tuple) or not all(
            isinstance(a, AppliedProposal) for a in self.applied_proposals
        ):
            _invalid("pasos aplicados inválidos")

    @property
    def utf8_size(self) -> int:
        return len(self.text.encode("utf-8"))


@dataclass(frozen=True, slots=True)
class ProposalView:
    proposal: CharacterProposal
    status: ProposalStatus
    decision: CharacterProposalDecision | None
    applied_to_effective: bool
    base: EffectiveComposition  # the effective composition when the proposal was added

    def __post_init__(self) -> None:
        if not isinstance(self.proposal, CharacterProposal):
            _invalid("la vista necesita su propuesta")
        if not isinstance(self.status, ProposalStatus):
            _invalid("estado de propuesta desconocido")
        if not isinstance(self.base, EffectiveComposition) or (
            self.base.character_id, self.base.concept, self.base.composition_sha256
        ) != (self.proposal.character_id, self.proposal.concept,
              self.proposal.base_composition_sha256):
            _invalid("la base mostrada no es la composición citada por la propuesta")
        if self.status in (ProposalStatus.APPROVED, ProposalStatus.REJECTED):
            if (not isinstance(self.decision, CharacterProposalDecision)
                    or self.decision.review_status.value != self.status.value
                    or not self.decision.matches(self.proposal)):
                _invalid("el estado de la propuesta no corresponde a su decisión")
        elif self.decision is not None:
            _invalid("una propuesta pendiente u obsoleta no puede tener decisión")
        if self.applied_to_effective and self.status is not ProposalStatus.APPROVED:
            _invalid("solo una propuesta aprobada puede estar aplicada")


@dataclass(frozen=True, slots=True)
class CharacterReplay:
    """Result of replaying the event log: the effective composition and every proposal view."""

    effective: EffectiveComposition
    views: tuple[ProposalView, ...]


@dataclass(frozen=True, slots=True)
class CharacterState:
    character_id: str
    concepts: tuple[ConceptVersion, ...]
    proposals: tuple[CharacterProposal, ...] = ()
    proposal_decisions: tuple[CharacterProposalDecision, ...] = ()
    replay: CharacterReplay = field(init=False, compare=False, repr=False)

    def __post_init__(self) -> None:
        check_character_id(self.character_id)
        if not isinstance(self.concepts, tuple) or not self.concepts or not all(
            isinstance(c, ConceptVersion) for c in self.concepts
        ):
            _invalid("un personaje necesita al menos un concepto declarado")
        if [c.version for c in self.concepts] != list(range(1, len(self.concepts) + 1)):
            _invalid("las versiones del concepto deben ser 1, 2, 3… sin huecos")
        for previous, current in zip(self.concepts, self.concepts[1:]):
            if previous.concept_sha256 == current.concept_sha256:
                _invalid(f"la versión {current.version} del concepto repite la anterior")
        if not isinstance(self.proposals, tuple) or not all(
            isinstance(p, CharacterProposal) for p in self.proposals
        ):
            _invalid("las propuestas deben ser una tupla de CharacterProposal")
        if not isinstance(self.proposal_decisions, tuple) or not all(
            isinstance(d, CharacterProposalDecision) for d in self.proposal_decisions
        ):
            _invalid("las decisiones deben ser una tupla de CharacterProposalDecision")
        if any(p.character_id != self.character_id for p in self.proposals):
            _invalid("una propuesta pertenece a otro personaje")
        object.__setattr__(self, "replay", _replay(self))

    @property
    def revision(self) -> int:
        """Events in the log: one revision per concept, proposal and decision."""
        return len(self.concepts) + len(self.proposals) + len(self.proposal_decisions)

    def current_concept(self) -> ConceptVersion:
        return self.concepts[-1]

    def current_proposal(self, proposal_id: str) -> CharacterProposal | None:
        versions = [p for p in self.proposals if p.proposal_id == proposal_id]
        return versions[-1] if versions else None

    def decision_for(self, proposal: CharacterProposal) -> CharacterProposalDecision | None:
        for decision in self.proposal_decisions:
            if decision.proposal_key == proposal.key:
                return decision
        return None

    def view(self, proposal_id: str, version: int) -> ProposalView | None:
        for view in self.replay.views:
            if view.proposal.key == (proposal_id, version):
                return view
        return None


@dataclass(frozen=True, slots=True)
class LoadedCharacter:
    character_root: Path
    state_revision: int
    state: CharacterState


@dataclass(frozen=True, slots=True)
class ConceptImportResult:
    character: LoadedCharacter
    concept: ConceptVersion
    created: bool


@dataclass(frozen=True, slots=True)
class ProposalAddResult:
    character: LoadedCharacter
    proposal: CharacterProposal
    created: bool


@dataclass(frozen=True, slots=True)
class ProposalDecisionResult:
    character: LoadedCharacter
    decision: CharacterProposalDecision
    created: bool
    effective: EffectiveComposition


# --- Replay -----------------------------------------------------------------------------------


def concept_root(character_id: str, concept: ConceptVersion) -> EffectiveComposition:
    """The composition a concept starts: its own text, with no proposal applied."""
    sha = _hash({"character_id": character_id, "concept": concept.ref.as_json(),
                 "text": concept.text})
    return EffectiveComposition(character_id, concept.ref, concept.text, sha, ())


def _replay(state: CharacterState) -> CharacterReplay:
    total = state.revision
    explicit: dict[int, tuple[str, object]] = {}
    for proposal in state.proposals:
        explicit.setdefault(proposal.created_revision, ("proposal", proposal))
    for decision in state.proposal_decisions:
        if decision.decision_revision in explicit:
            _invalid(f"la revisión {decision.decision_revision} está repetida")
        explicit[decision.decision_revision] = ("decision", decision)
    if len(explicit) != len(state.proposals) + len(state.proposal_decisions):
        _invalid("dos propuestas comparten revisión")
    if any(not 1 <= revision <= total for revision in explicit):
        _invalid("una revisión de propuesta o decisión está fuera del historial")
    created = [p.created_revision for p in state.proposals]
    decided = [d.decision_revision for d in state.proposal_decisions]
    if created != sorted(created) or decided != sorted(decided):
        _invalid("las propuestas y decisiones deben estar en orden de revisión")
    concept_revisions = [r for r in range(1, total + 1) if r not in explicit]
    events = dict(explicit)
    for revision, concept in zip(concept_revisions, state.concepts):
        events[revision] = ("concept", concept)

    effective: EffectiveComposition | None = None
    current: ConceptVersion | None = None
    latest: dict[str, int] = {}
    seen: dict[tuple[str, int], CharacterProposal] = {}
    bases: dict[tuple[str, int], EffectiveComposition] = {}
    decisions: dict[tuple[str, int], CharacterProposalDecision] = {}
    for revision in range(1, total + 1):
        kind, item = events[revision]
        if kind == "concept":
            current = item
            effective = concept_root(state.character_id, item)
        elif kind == "proposal":
            proposal = item
            if current is None or effective is None:
                _invalid(f"la propuesta {proposal.proposal_id} v{proposal.version} es anterior al "
                         "primer concepto")
            if proposal.concept != current.ref:
                _invalid(f"{proposal.proposal_id} v{proposal.version} no cita el concepto vigente")
            if proposal.base_composition_sha256 != effective.composition_sha256:
                _invalid(f"{proposal.proposal_id} v{proposal.version} no parte de la composición "
                         "efectiva de su momento")
            if proposal.version != latest.get(proposal.proposal_id, 0) + 1:
                _invalid(f"{proposal.proposal_id} salta a la versión {proposal.version}")
            latest[proposal.proposal_id] = proposal.version
            seen[proposal.key] = proposal
            bases[proposal.key] = effective
        else:
            decision = item
            proposal = seen.get(decision.proposal_key)
            if proposal is None or not decision.matches(proposal):
                _invalid(f"la decisión {decision.decision_id} no corresponde a una propuesta "
                         "anterior exacta")
            if decision.proposal_key in decisions:
                _invalid(f"la propuesta {decision.decision_id} tiene dos decisiones")
            decisions[decision.proposal_key] = decision
            if decision.review_status is ReviewStatus.APPROVED:
                if (latest[proposal.proposal_id] != proposal.version
                        or proposal.concept != current.ref
                        or proposal.base_composition_sha256 != effective.composition_sha256):
                    _invalid(f"{decision.decision_id} se aprobó sin ser la propuesta vigente sobre "
                             "la composición efectiva")
                effective = EffectiveComposition(
                    state.character_id, current.ref, proposal.text,
                    proposal.result_composition_sha256,
                    (*effective.applied_proposals, AppliedProposal(proposal, decision)))
    applied = {step.proposal.key for step in effective.applied_proposals}
    views = []
    for proposal in state.proposals:
        decision = decisions.get(proposal.key)
        if decision is not None:
            status = ProposalStatus(decision.review_status.value)
        elif (proposal.concept == current.ref and latest[proposal.proposal_id] == proposal.version
              and proposal.base_composition_sha256 == effective.composition_sha256):
            status = ProposalStatus.PENDING
        else:
            status = ProposalStatus.OBSOLETE
        views.append(ProposalView(proposal, status, decision, proposal.key in applied,
                                  bases[proposal.key]))
    return CharacterReplay(effective, tuple(views))


# --- Factories and codec ----------------------------------------------------------------------


def make_concept_version(*, forum_id: str, character_id: str, version: int, text: str,
                         receipt: HumanConfirmationReceipt) -> ConceptVersion:
    """Build a concept version with its evidence (a SourceRef over the canonical payload)."""
    check_character_id(character_id)
    check_concept_text(text)
    data = text.encode("utf-8")
    payload = _evidence_payload(character_id, version, text, hashlib.sha256(data).hexdigest(),
                                len(data), receipt)
    return ConceptVersion(version, text, ConceptAuthorship.HUMAN_DECLARED, receipt,
                          _evidence(forum_id, character_id, version, payload))


def make_proposal_decision(*, forum_id: str, character_id: str, proposal: CharacterProposal,
                           decision_revision: int, review_status: ReviewStatus,
                           receipt: HumanConfirmationReceipt) -> CharacterProposalDecision:
    """Build a decision with its evidence over the canonical payload."""
    if not isinstance(proposal, CharacterProposal):
        _invalid("la decisión necesita la propuesta exacta")
    _check_decision_status(review_status)
    decision_id = f"proposal:{proposal.proposal_id}:v{proposal.version}"
    payload = {
        "base_composition_sha256": proposal.base_composition_sha256,
        "character_id": character_id,
        "decision_id": decision_id,
        "decision_revision": decision_revision,
        "proposal_id": proposal.proposal_id,
        "proposal_sha256": proposal.proposal_sha256,
        "proposal_version": proposal.version,
        "receipt": _receipt_record(receipt),
        "result_composition_sha256": proposal.result_composition_sha256,
        "review_status": review_status.value,
    }
    segments = "/".join(quote(s, safe="") for s in (character_id, "proposals",
                                                     proposal.proposal_id,
                                                     f"v{proposal.version}", "decision"))
    evidence = SourceRef(
        source_id=f"human-proposal-decision:{character_id}:{proposal.proposal_id}:"
                  f"v{proposal.version}",
        locator=f"instance://{quote(forum_id, safe='')}/characters/{segments}",
        sha256=_hash(payload),
        section_or_passage=decision_id,
    )
    return CharacterProposalDecision(decision_id, decision_revision, proposal.proposal_id,
                                     proposal.version, proposal.proposal_sha256,
                                     proposal.base_composition_sha256,
                                     proposal.result_composition_sha256, review_status, receipt,
                                     evidence)


def encode_character_content(state: CharacterState) -> dict[str, object]:
    return {
        "character_id": state.character_id,
        "concepts": [_concept_record(state.character_id, c) for c in state.concepts],
        "proposal_decisions": [decision_record(d) for d in state.proposal_decisions],
        "proposals": [proposal_record(p) for p in state.proposals],
    }


def decode_character_state(content: object, *, forum_id: str, revision: int,
                           candidate_resolver: CandidateResolver | None = None) -> CharacterState:
    """Rebuild a character state, recompute every hash and evidence and replay the event log.

    `candidate_resolver(candidate_id, version)` must return the current APPROVED candidate of
    the instance (or raise); it is required as soon as a proposal cites the corpus.
    """
    from core.runtime.assimilation import AssimilationError, HumanConfirmationReceipt

    if type(revision) is not int or revision < 1:
        _invalid("la revisión del personaje debe ser un entero positivo")
    if not isinstance(content, dict) or set(content) != _CONTENT_KEYS:
        _invalid("el estado del personaje no tiene exactamente las claves esperadas")
    character_id = check_character_id(content["character_id"])
    for name in ("concepts", "proposals", "proposal_decisions"):
        if not isinstance(content[name], list):
            _invalid(f"{name} debe ser una lista")

    def receipt_of(record: object, where: str):
        if not isinstance(record, dict) or set(record) != _RECEIPT_KEYS:
            _invalid(f"{where}: recibo con claves inesperadas")
        try:
            return HumanConfirmationReceipt(record["method"], record["confirmation_sha256"])
        except AssimilationError as exc:
            _invalid(f"{where}: {exc.reason}")

    concepts = []
    for position, record in enumerate(content["concepts"], start=1):
        where = f"concepto {position}"
        if not isinstance(record, dict) or set(record) != _CONCEPT_KEYS:
            _invalid(f"{where}: claves inesperadas")
        if record["authorship"] != ConceptAuthorship.HUMAN_DECLARED.value:
            _invalid(f"{where}: autoría desconocida")
        concept = make_concept_version(forum_id=forum_id, character_id=character_id,
                                       version=record["version"], text=record["text"],
                                       receipt=receipt_of(record["receipt"], where))
        if _concept_record(character_id, concept) != record:
            _invalid(f"{where}: se modificó fuera del core (hash, tamaño o evidencia distintos)")
        concepts.append(concept)

    proposals = []
    for position, record in enumerate(content["proposals"], start=1):
        where = f"propuesta {position}"
        if not isinstance(record, dict) or set(record) != _PROPOSAL_KEYS:
            _invalid(f"{where}: claves inesperadas")
        concept_ref = record["concept"]
        if not isinstance(concept_ref, dict) or set(concept_ref) != _CONCEPT_REF_KEYS:
            _invalid(f"{where}: concepto citado con claves inesperadas")
        citations = record["citations"]
        if not isinstance(citations, list):
            _invalid(f"{where}: citations debe ser una lista")
        refs = []
        for item in citations:
            if not isinstance(item, dict) or set(item) != _CITATION_KEYS:
                _invalid(f"{where}: cita con claves inesperadas")
            refs.append(CorpusCandidateRef(item["candidate_id"], item["version"],
                                           item["candidate_sha256"]))
        proposal = CharacterProposal(character_id, record["proposal_id"], record["version"],
                                     record["created_revision"],
                                     ConceptRef(concept_ref["version"],
                                                concept_ref["concept_sha256"]),
                                     record["base_composition_sha256"], record["text"],
                                     record["rationale"], tuple(refs))
        if proposal_record(proposal) != record:
            _invalid(f"{where}: se modificó fuera del core (hashes o tamaño distintos)")
        for ref in proposal.citations:
            if candidate_resolver is None:
                _invalid(f"{where}: no se pueden verificar sus citas del corpus")
            try:
                candidate = candidate_resolver(ref.candidate_id, ref.version)
            except ValueError as exc:
                _invalid(f"{where}: la cita {ref.candidate_id} v{ref.version} no es una versión "
                         f"vigente aprobada ({getattr(exc, 'reason', exc)})")
            if candidate.candidate_sha256 != ref.candidate_sha256:
                _invalid(f"{where}: la cita {ref.candidate_id} v{ref.version} no coincide con el "
                         "corpus")
        proposals.append(proposal)

    by_key = {p.key: p for p in proposals}
    decisions = []
    for position, record in enumerate(content["proposal_decisions"], start=1):
        where = f"decisión {position}"
        if not isinstance(record, dict) or set(record) != _DECISION_KEYS:
            _invalid(f"{where}: claves inesperadas")
        try:
            status = ReviewStatus(record["review_status"])
        except (ValueError, TypeError):
            _invalid(f"{where}: estado desconocido")
        proposal = by_key.get((_check_id("proposal_id", record["proposal_id"]),
                               _check_positive("proposal_version", record["proposal_version"])))
        if proposal is None:
            _invalid(f"{where}: no corresponde a ninguna propuesta")
        decision = make_proposal_decision(forum_id=forum_id, character_id=character_id,
                                          proposal=proposal,
                                          decision_revision=record["decision_revision"],
                                          review_status=status,
                                          receipt=receipt_of(record["receipt"], where))
        if decision_record(decision) != record:
            _invalid(f"{where}: se modificó fuera del core (hash o evidencia distintos)")
        decisions.append(decision)

    state = CharacterState(character_id, tuple(concepts), tuple(proposals), tuple(decisions))
    if state.revision != revision:
        _invalid("la revisión del personaje no corresponde a su historial")
    return state


def concept_summary(concept: ConceptVersion) -> dict[str, object]:
    return {
        "authorship": concept.authorship.value,
        "concept_sha256": concept.concept_sha256,
        "evidence_sha256": concept.evidence.sha256,
        "utf8_size": concept.utf8_size,
        "version": concept.version,
    }


def concept_record(character_id: str, concept: ConceptVersion) -> dict[str, object]:
    return _concept_record(character_id, concept)


def proposal_record(proposal: CharacterProposal) -> dict[str, object]:
    return {**_proposal_core(proposal), "proposal_sha256": proposal.proposal_sha256,
            "result_composition_sha256": proposal.result_composition_sha256}


def decision_record(decision: CharacterProposalDecision) -> dict[str, object]:
    return {
        "base_composition_sha256": decision.base_composition_sha256,
        "decision_id": decision.decision_id,
        "decision_revision": decision.decision_revision,
        "evidence": _evidence_record(decision.evidence),
        "proposal_id": decision.proposal_id,
        "proposal_sha256": decision.proposal_sha256,
        "proposal_version": decision.proposal_version,
        "receipt": _receipt_record(decision.receipt),
        "result_composition_sha256": decision.result_composition_sha256,
        "review_status": decision.review_status.value,
    }


def composition_record(composition: EffectiveComposition) -> dict[str, object]:
    return {
        "applied_proposals": [{
            "decision_evidence_sha256": step.decision.evidence.sha256,
            "proposal_id": step.proposal.proposal_id,
            "proposal_sha256": step.proposal.proposal_sha256,
            "result_composition_sha256": step.proposal.result_composition_sha256,
            "version": step.proposal.version,
        } for step in composition.applied_proposals],
        "composition_sha256": composition.composition_sha256,
        "concept": composition.concept.as_json(),
        "text": composition.text,
        "utf8_size": composition.utf8_size,
    }


def _proposal_core(proposal: CharacterProposal) -> dict[str, object]:
    return {
        "base_composition_sha256": proposal.base_composition_sha256,
        "citations": [c.as_json() for c in proposal.citations],
        "concept": proposal.concept.as_json(),
        "created_revision": proposal.created_revision,
        "proposal_id": proposal.proposal_id,
        "rationale": proposal.rationale,
        "text": proposal.text,
        "utf8_size": proposal.utf8_size,
        "version": proposal.version,
    }


def _concept_record(character_id: str, concept: ConceptVersion) -> dict[str, object]:
    return {
        "authorship": concept.authorship.value,
        "concept_sha256": concept.concept_sha256,
        "evidence": _evidence_record(concept.evidence),
        "receipt": _receipt_record(concept.receipt),
        "text": concept.text,
        "utf8_size": concept.utf8_size,
        "version": concept.version,
    }


def _evidence_record(evidence: SourceRef) -> dict[str, object]:
    return {"locator": evidence.locator, "section_or_passage": evidence.section_or_passage,
            "sha256": evidence.sha256, "source_id": evidence.source_id}


def _evidence_payload(character_id: str, version: int, text: str, sha256: str, size: int,
                      receipt: HumanConfirmationReceipt) -> dict[str, object]:
    return {
        "authorship": ConceptAuthorship.HUMAN_DECLARED.value,
        "character_id": character_id,
        "concept_sha256": sha256,
        "receipt": _receipt_record(receipt),
        "text": text,
        "utf8_size": size,
        "version": version,
    }


def _evidence(forum_id: str, character_id: str, version: int, payload: dict) -> SourceRef:
    if type(version) is not int or version < 1:
        _invalid("la versión del concepto debe ser un entero positivo")
    subject = f"concept:{character_id}:v{version}"
    return SourceRef(
        source_id=f"human-concept:{character_id}:v{version}",
        locator=(f"instance://{quote(forum_id, safe='')}/characters/"
                 f"{quote(character_id, safe='')}/concepts/v{version}"),
        sha256=_hash(payload),
        section_or_passage=subject,
    )


def _hash(value: object) -> str:
    from core.runtime.persistence import canonical_json_bytes

    return hashlib.sha256(canonical_json_bytes(value, pretty=False)).hexdigest()


def _receipt_record(receipt: HumanConfirmationReceipt) -> dict[str, object]:
    return {"confirmation_sha256": receipt.confirmation_sha256, "method": receipt.method}


def _invalid(reason: str) -> None:
    raise CharacterError("INVALID_STATE", reason)
