"""Character state inside a forum instance: concept versions declared by the person.

The concept is free Markdown kept character by character. Every version is adopted by a person
through barrier A (a typed phrase in an interactive terminal); that records explicit human
adoption, not who originally wrote the text. Proposals and decisions arrive in 4d2.

Imports from `core.runtime` are deferred to function bodies: `core.runtime` imports this module.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import quote

from core.memory.provenance import SourceRef

if TYPE_CHECKING:
    from core.runtime.assimilation import HumanConfirmationReceipt

_CHARACTER_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_FORBIDDEN_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_CODES = frozenset({"INVALID_STATE", "CONFLICT", "UNSAFE_DESTINATION", "IO"})
_CONTENT_KEYS = frozenset({"character_id", "concepts", "proposal_decisions", "proposals"})
_CONCEPT_KEYS = frozenset({"authorship", "concept_sha256", "evidence", "receipt", "text",
                           "utf8_size", "version"})
_EVIDENCE_KEYS = frozenset({"locator", "section_or_passage", "sha256", "source_id"})
_RECEIPT_KEYS = frozenset({"confirmation_sha256", "method"})


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


def check_character_id(value: object) -> str:
    if not isinstance(value, str) or not _CHARACTER_ID.fullmatch(value):
        _invalid("el ID del personaje solo admite minúsculas ASCII, dígitos y guiones simples "
                 "(p. ej. «mi-personaje»)")
    return value


def check_concept_text(text: object) -> str:
    """Free text kept exactly: TAB/CR/LF allowed, other controls and NUL rejected."""
    if not isinstance(text, str) or not text.strip():
        _invalid("el concepto no puede estar vacío")
    if text.startswith("﻿"):
        _invalid("el concepto empieza con BOM; guárdalo como UTF-8 sin BOM")
    if _FORBIDDEN_CONTROL.search(text):
        _invalid("el concepto contiene caracteres de control (solo se admiten tabulador y saltos "
                 "de línea)")
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        _invalid("el concepto contiene caracteres que no se pueden guardar en UTF-8")
    return text


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


@dataclass(frozen=True, slots=True)
class CharacterState:
    character_id: str
    concepts: tuple[ConceptVersion, ...]
    proposals: tuple = ()
    proposal_decisions: tuple = ()

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
        if self.proposals != () or self.proposal_decisions != ():
            _invalid("las propuestas todavía no están disponibles")

    def current_concept(self) -> ConceptVersion:
        return self.concepts[-1]


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


def encode_character_content(state: CharacterState) -> dict[str, object]:
    return {
        "character_id": state.character_id,
        "concepts": [_concept_record(state.character_id, c) for c in state.concepts],
        "proposal_decisions": [],
        "proposals": [],
    }


def decode_character_state(content: object, *, forum_id: str, revision: int) -> CharacterState:
    """Rebuild a character state and recompute every hash and evidence."""
    from core.runtime.assimilation import AssimilationError, HumanConfirmationReceipt

    if type(revision) is not int or revision < 1:
        _invalid("la revisión del personaje debe ser un entero positivo")
    if not isinstance(content, dict) or set(content) != _CONTENT_KEYS:
        _invalid("el estado del personaje no tiene exactamente las claves esperadas")
    character_id = check_character_id(content["character_id"])
    if content["proposals"] != [] or content["proposal_decisions"] != []:
        _invalid("el estado del personaje contiene propuestas no admitidas todavía")
    records = content["concepts"]
    if not isinstance(records, list):
        _invalid("concepts debe ser una lista")
    concepts = []
    for position, record in enumerate(records, start=1):
        where = f"concepto {position}"
        if not isinstance(record, dict) or set(record) != _CONCEPT_KEYS:
            _invalid(f"{where}: claves inesperadas")
        receipt_data = record["receipt"]
        if not isinstance(receipt_data, dict) or set(receipt_data) != _RECEIPT_KEYS:
            _invalid(f"{where}: recibo con claves inesperadas")
        try:
            receipt = HumanConfirmationReceipt(receipt_data["method"],
                                               receipt_data["confirmation_sha256"])
        except AssimilationError as exc:
            _invalid(f"{where}: {exc.reason}")
        if record["authorship"] != ConceptAuthorship.HUMAN_DECLARED.value:
            _invalid(f"{where}: autoría desconocida")
        concept = make_concept_version(forum_id=forum_id, character_id=character_id,
                                       version=record["version"], text=record["text"],
                                       receipt=receipt)
        if _concept_record(character_id, concept) != record:
            _invalid(f"{where}: se modificó fuera del core (hash, tamaño o evidencia distintos)")
        concepts.append(concept)
    return CharacterState(character_id, tuple(concepts))


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


def _concept_record(character_id: str, concept: ConceptVersion) -> dict[str, object]:
    return {
        "authorship": concept.authorship.value,
        "concept_sha256": concept.concept_sha256,
        "evidence": {"locator": concept.evidence.locator,
                     "section_or_passage": concept.evidence.section_or_passage,
                     "sha256": concept.evidence.sha256,
                     "source_id": concept.evidence.source_id},
        "receipt": _receipt_record(concept.receipt),
        "text": concept.text,
        "utf8_size": concept.utf8_size,
        "version": concept.version,
    }


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
    from core.runtime.persistence import canonical_json_bytes

    if type(version) is not int or version < 1:
        _invalid("la versión del concepto debe ser un entero positivo")
    subject = f"concept:{character_id}:v{version}"
    return SourceRef(
        source_id=f"human-concept:{character_id}:v{version}",
        locator=(f"instance://{quote(forum_id, safe='')}/characters/"
                 f"{quote(character_id, safe='')}/concepts/v{version}"),
        sha256=hashlib.sha256(canonical_json_bytes(payload, pretty=False)).hexdigest(),
        section_or_passage=subject,
    )


def _receipt_record(receipt: HumanConfirmationReceipt) -> dict[str, object]:
    return {"confirmation_sha256": receipt.confirmation_sha256, "method": receipt.method}


def _invalid(reason: str) -> None:
    raise CharacterError("INVALID_STATE", reason)
