"""Forum dossier: the human-written `expediente.md` that feeds rule and setting assimilation.

It parses, validates and loads the dossier with provenance, and records cited assimilation
candidates as pending proposals. It never approves, interprets or indexes sources. Error reasons
are in Spanish because the dossier is written by hand and every message must help to fix it.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

from core.memory.provenance import SourceRef
from core.review.models import ReviewStatus
from core.runtime.persistence import (
    PersistenceError,
    atomic_write_bytes,
    canonical_json_bytes,
    encode_state,
    load_state,
)

DOSSIER_NAME = "expediente.md"
DOSSIER_SCHEMA_VERSION = 1


class DossierSection(str, Enum):
    FORUM_RULES = "forum_rules"
    SETTING = "setting"
    CHARACTER_CREATION = "character_creation"
    STAFF_REVIEW = "staff_review"
    PLATFORM_FORMAT = "platform_format"
    COMBAT_SYSTEM = "combat_system"
    ABILITY_TECHNIQUE_CREATION = "ability_technique_creation"


class DossierSectionStatus(str, Enum):
    PROVIDED = "PROVIDED"
    MISSING = "MISSING"
    NOT_APPLICABLE = "NOT_APPLICABLE"


REQUIRED_SECTIONS = (
    DossierSection.FORUM_RULES,
    DossierSection.SETTING,
    DossierSection.CHARACTER_CREATION,
    DossierSection.STAFF_REVIEW,
    DossierSection.PLATFORM_FORMAT,
)
OPTIONAL_SECTIONS = (
    DossierSection.COMBAT_SYSTEM,
    DossierSection.ABILITY_TECHNIQUE_CREATION,
)

_HEADINGS = {
    DossierSection.FORUM_RULES: "Normas generales",
    DossierSection.SETTING: "Ambientación",
    DossierSection.CHARACTER_CREATION: "Creación de fichas",
    DossierSection.STAFF_REVIEW: "Revisión del staff",
    DossierSection.PLATFORM_FORMAT: "Plataforma y formato",
    DossierSection.COMBAT_SYSTEM: "Sistema de combate",
    DossierSection.ABILITY_TECHNIQUE_CREATION: "Creación de técnicas o habilidades",
}
_SECTION_BY_HEADING = {heading: section for section, heading in _HEADINGS.items()}
_LOOSE_HEADING = "Material suelto"
_HEADING_ORDER = tuple(_HEADINGS[s] for s in DossierSection) + (_LOOSE_HEADING,)
_STATUS_MARKERS = {
    "FALTA": DossierSectionStatus.MISSING,
    "NO APLICA": DossierSectionStatus.NOT_APPLICABLE,
}

_HEADER_TITLE = "# Expediente del foro"
_HEADER_KEYS = ("forum_id", "nombre", "versión_expediente")
_META_PREFIX = "Metadatos: "
_META_KEYS = ("id", "versión", "autoridad", "alcance", "desde", "hasta", "pasaje", "archivo",
              "sugerencias")
_META_REQUIRED = ("id", "versión", "autoridad", "alcance")
_META_SEPARATOR = " | "

_FORUM_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_CONTROL = re.compile(r"[\x00-\x1f]")
_ATX_HEADING = re.compile(r"#{1,6}(?:[ \t]|$)")
_FENCE_OPEN = re.compile(r"(~{4,}) texto")
_FENCE_LIKE = re.compile(r"~{4,}")
_TILDE_RUN = re.compile(r"~+")
_UTF8_BOM = b"\xef\xbb\xbf"


class DossierError(ValueError):
    """An invalid dossier: where (locator and 1-based line, if known) and why."""

    def __init__(self, locator: str, line: int | None, reason: str):
        self.locator = locator
        self.line = line
        self.reason = reason
        where = f"{locator}:{line}" if line is not None else locator
        super().__init__(f"{where}: {reason}")


# --- Public model -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DossierSourceSpec:
    """A declared source. Exactly one of `path` and `inline_text` holds the literal's origin."""

    source_id: str
    version: str
    authority: str
    scope: str
    effective_from: date | None
    effective_until: date | None
    section_or_passage: str | None
    path: str | None
    inline_text: str | None

    def __post_init__(self) -> None:
        owner = type(self).__name__
        _check_text(owner, "id", self.source_id)
        _check_text(owner, "versión", self.version)
        _check_text(owner, "autoridad", self.authority)
        _check_text(owner, "alcance", self.scope)
        for name, value in (("desde", self.effective_from), ("hasta", self.effective_until)):
            if value is not None and type(value) is not date:
                _fail(owner, f"«{name}» debe ser una fecha o null")
        if (
            self.effective_from is not None
            and self.effective_until is not None
            and self.effective_from > self.effective_until
        ):
            _fail(owner, "«desde» no puede ser posterior a «hasta»")
        if self.section_or_passage is not None:
            _check_text(owner, "pasaje", self.section_or_passage)
        if (self.path is None) == (self.inline_text is None):
            _fail(owner, "una fuente necesita exactamente un origen: «archivo» o texto en línea")
        if self.path is not None:
            _check_relative_path(owner, self.path)
        if self.inline_text is not None:
            if not isinstance(self.inline_text, str):
                _fail(owner, "el texto en línea debe ser texto")
            _check_utf8(owner, "texto en línea", self.inline_text)
            if "\r" in self.inline_text:
                _fail(owner, "el texto en línea canónico no puede contener CR")
            if not self.inline_text.strip():
                _fail(owner, "el texto en línea está vacío")

    @property
    def key(self) -> tuple[str, str]:
        return (self.source_id, self.version)


@dataclass(frozen=True, slots=True)
class DossierSectionSpec:
    section: DossierSection
    status: DossierSectionStatus
    notes: str | None
    sources: tuple[DossierSourceSpec, ...]

    def __post_init__(self) -> None:
        owner = type(self).__name__
        if not isinstance(self.section, DossierSection):
            _fail(owner, "sección desconocida")
        if not isinstance(self.status, DossierSectionStatus):
            _fail(owner, "estado desconocido")
        heading = _HEADINGS[self.section]
        if self.notes is not None:
            _check_text(owner, "Nota", self.notes)
        if not isinstance(self.sources, tuple) or not all(
            isinstance(s, DossierSourceSpec) for s in self.sources
        ):
            _fail(owner, "las fuentes deben ser una tupla de DossierSourceSpec")
        if self.section in REQUIRED_SECTIONS and self.status is DossierSectionStatus.NOT_APPLICABLE:
            _fail(owner, f"«{heading}» es obligatoria y no admite «Estado: NO APLICA»")
        if self.status is DossierSectionStatus.PROVIDED and not self.sources:
            _fail(owner, f"«{heading}» no tiene fuentes; añade una o marca «Estado: FALTA»")
        if self.status is not DossierSectionStatus.PROVIDED and self.sources:
            _fail(owner, f"«{heading}» tiene «Estado:» y fuentes a la vez; quita uno de los dos")


@dataclass(frozen=True, slots=True)
class LooseMaterialSpec:
    source: DossierSourceSpec
    suggested_sections: tuple[DossierSection, ...]

    def __post_init__(self) -> None:
        owner = type(self).__name__
        if not isinstance(self.source, DossierSourceSpec):
            _fail(owner, "la fuente debe ser un DossierSourceSpec")
        if not isinstance(self.suggested_sections, tuple) or not all(
            isinstance(s, DossierSection) for s in self.suggested_sections
        ):
            _fail(owner, "las sugerencias deben ser una tupla de secciones")
        if len(set(self.suggested_sections)) != len(self.suggested_sections):
            _fail(owner, "«sugerencias» repite una sección")


@dataclass(frozen=True, slots=True)
class ForumDossier:
    schema_version: int
    forum_id: str
    display_name: str
    dossier_version: str
    sections: tuple[DossierSectionSpec, ...]
    loose_material: tuple[LooseMaterialSpec, ...]

    def __post_init__(self) -> None:
        owner = type(self).__name__
        if type(self.schema_version) is not int or self.schema_version != DOSSIER_SCHEMA_VERSION:
            _fail(owner, f"schema_version debe ser {DOSSIER_SCHEMA_VERSION}")
        _check_forum_id(owner, self.forum_id)
        _check_text(owner, "nombre", self.display_name)
        _check_text(owner, "versión_expediente", self.dossier_version)
        if not isinstance(self.sections, tuple) or tuple(
            getattr(s, "section", None) for s in self.sections
        ) != tuple(DossierSection):
            _fail(owner, "las siete secciones deben aparecer una vez y en orden fijo")
        if not all(isinstance(s, DossierSectionSpec) for s in self.sections):
            _fail(owner, "las secciones deben ser DossierSectionSpec")
        if not isinstance(self.loose_material, tuple) or not all(
            isinstance(m, LooseMaterialSpec) for m in self.loose_material
        ):
            _fail(owner, "el material suelto debe ser una tupla de LooseMaterialSpec")
        seen: dict[tuple[str, str], DossierSourceSpec] = {}
        for spec in self.all_sources():
            first = seen.setdefault(spec.key, spec)
            conflict = _repeat_conflict(first, spec)
            if conflict:
                _fail(owner, _repeat_reason(spec, conflict, None))

    def all_sources(self) -> tuple[DossierSourceSpec, ...]:
        """Every source occurrence in document order: sections first, then loose material."""
        return tuple(s for section in self.sections for s in section.sources) + tuple(
            m.source for m in self.loose_material
        )


@dataclass(frozen=True, slots=True)
class LoadedDossierSource:
    spec: DossierSourceSpec
    literal_text: str
    source_ref: SourceRef

    def __post_init__(self) -> None:
        owner = type(self).__name__
        if not isinstance(self.spec, DossierSourceSpec) or not isinstance(self.source_ref, SourceRef):
            _fail(owner, "tipos inválidos")
        if not isinstance(self.literal_text, str) or not self.literal_text.strip():
            _fail(owner, "el literal está vacío")
        if self.spec.inline_text is not None and self.literal_text != self.spec.inline_text:
            _fail(owner, "el literal no coincide con el texto en línea declarado")
        if (
            self.source_ref.source_id != self.spec.source_id
            or self.source_ref.section_or_passage != self.spec.section_or_passage
            or self.source_ref.sha256 != _sha256(self.literal_text.encode("utf-8"))
        ):
            _fail(owner, "el SourceRef no corresponde a la fuente y su literal")


@dataclass(frozen=True, slots=True)
class LoadedDossierSection:
    spec: DossierSectionSpec
    sources: tuple[LoadedDossierSource, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.spec, DossierSectionSpec) or not isinstance(self.sources, tuple):
            _fail(type(self).__name__, "tipos inválidos")
        if tuple(getattr(s, "spec", None) for s in self.sources) != self.spec.sources:
            _fail(type(self).__name__, "las fuentes cargadas no corresponden a la sección")


@dataclass(frozen=True, slots=True)
class LoadedLooseMaterial:
    spec: LooseMaterialSpec
    source: LoadedDossierSource

    def __post_init__(self) -> None:
        if not isinstance(self.spec, LooseMaterialSpec) or not isinstance(
            self.source, LoadedDossierSource
        ):
            _fail(type(self).__name__, "tipos inválidos")
        if self.source.spec != self.spec.source:
            _fail(type(self).__name__, "la fuente cargada no corresponde al material suelto")


@dataclass(frozen=True, slots=True)
class LoadedForumDossier:
    dossier: ForumDossier
    dossier_path: Path
    sections: tuple[LoadedDossierSection, ...]
    loose_material: tuple[LoadedLooseMaterial, ...]

    def __post_init__(self) -> None:
        owner = type(self).__name__
        if not isinstance(self.dossier, ForumDossier) or not isinstance(self.dossier_path, Path):
            _fail(owner, "tipos inválidos")
        if not isinstance(self.sections, tuple) or tuple(
            getattr(s, "spec", None) for s in self.sections
        ) != self.dossier.sections:
            _fail(owner, "las secciones cargadas no corresponden al expediente")
        if not isinstance(self.loose_material, tuple) or tuple(
            getattr(m, "spec", None) for m in self.loose_material
        ) != self.dossier.loose_material:
            _fail(owner, "el material suelto cargado no corresponde al expediente")


@dataclass(frozen=True, slots=True)
class DossierAssessment:
    missing_required: tuple[DossierSection, ...]
    missing_optional: tuple[DossierSection, ...]
    ready_for_assimilation: bool

    def __post_init__(self) -> None:
        owner = type(self).__name__
        if not isinstance(self.missing_required, tuple) or not isinstance(
            self.missing_optional, tuple
        ):
            _fail(owner, "las secciones que faltan deben ser tuplas")
        if not all(s in REQUIRED_SECTIONS for s in self.missing_required):
            _fail(owner, "missing_required solo admite secciones obligatorias")
        if not all(s in OPTIONAL_SECTIONS for s in self.missing_optional):
            _fail(owner, "missing_optional solo admite secciones opcionales")
        if self.ready_for_assimilation is not (not self.missing_required):
            _fail(owner, "ready_for_assimilation exige que no falte ninguna obligatoria")


# --- Public functions -------------------------------------------------------------------------


def parse_dossier(text: str, *, locator: str = DOSSIER_NAME) -> ForumDossier:
    """Parse an `expediente.md` text. Reads nothing from disk."""
    dossier, _ = _parse(text, locator)
    return dossier


def assess_dossier(dossier: ForumDossier) -> DossierAssessment:
    """Report missing sections. A missing optional section is reported but does not block."""
    missing = [s.section for s in dossier.sections if s.status is DossierSectionStatus.MISSING]
    required = tuple(s for s in missing if s in REQUIRED_SECTIONS)
    optional = tuple(s for s in missing if s in OPTIONAL_SECTIONS)
    return DossierAssessment(required, optional, not required)


def load_dossier(dossier_dir: Path) -> LoadedForumDossier:
    """Load `<dossier_dir>/expediente.md` and every declared source, binding each to its hash."""
    try:
        dossier_dir = Path(dossier_dir)
    except TypeError as exc:
        raise DossierError("load_dossier", None, "la carpeta del expediente debe ser una ruta") from exc
    document = dossier_dir / DOSSIER_NAME
    locator = document.as_posix()
    try:
        if dossier_dir.is_symlink() or not dossier_dir.is_dir():
            raise DossierError(dossier_dir.as_posix(), None, "el expediente debe ser un directorio")
        if document.is_symlink() or not document.is_file():
            raise DossierError(locator, None, f"no existe {DOSSIER_NAME} como archivo regular")
        raw = document.read_bytes()
        root = dossier_dir.resolve(strict=True)
    except OSError as exc:
        raise DossierError(locator, None, f"no se pudo leer el expediente: {exc}") from exc
    if raw.startswith(_UTF8_BOM):
        raise DossierError(locator, 1, "el archivo empieza con BOM; guárdalo como UTF-8 sin BOM")
    text = _decode_utf8(raw, locator, None)
    dossier, occurrences = _parse(text, locator)

    file_cache: dict[str, tuple[str, str, str]] = {}
    loaded: list[LoadedDossierSource] = []
    hashes: dict[tuple[str, str], tuple[str, int]] = {}
    for spec, line in occurrences:
        if spec.path is not None:
            if spec.path not in file_cache:
                file_cache[spec.path] = _read_source_file(dossier_dir, root, spec.path, locator, line)
            literal, digest, source_locator = file_cache[spec.path]
        else:
            literal = spec.inline_text
            digest = _sha256(literal.encode("utf-8"))
            source_locator = (
                f"{locator}#inline:id={quote(spec.source_id, safe='')}"
                f"&version={quote(spec.version, safe='')}"
            )
        first = hashes.setdefault(spec.key, (digest, line))
        if first[0] != digest:
            raise DossierError(locator, line, _repeat_reason(spec, "contenido", first[1]))
        source_ref = SourceRef(
            source_id=spec.source_id,
            locator=source_locator,
            sha256=digest,
            section_or_passage=spec.section_or_passage,
        )
        loaded.append(LoadedDossierSource(spec, literal, source_ref))

    remaining = iter(loaded)
    sections = tuple(
        LoadedDossierSection(section, tuple(next(remaining) for _ in section.sources))
        for section in dossier.sections
    )
    loose = tuple(LoadedLooseMaterial(m, next(remaining)) for m in dossier.loose_material)
    return LoadedForumDossier(dossier, document, sections, loose)


# --- Parser -----------------------------------------------------------------------------------


@dataclass(slots=True)
class _OpenSection:
    heading: str
    line: int
    section: DossierSection | None  # None for loose material
    status: DossierSectionStatus = DossierSectionStatus.PROVIDED
    notes: str | None = None
    phase: str = "start"  # start -> status -> note -> sources
    sources: list[tuple[DossierSourceSpec, int, tuple[DossierSection, ...]]] = field(
        default_factory=list
    )


def _parse(text: object, locator: str) -> tuple[ForumDossier, list[tuple[DossierSourceSpec, int]]]:
    lines = _canonical_lines(text, locator)

    def fail(line: int, reason: str) -> None:
        raise DossierError(locator, line, reason)

    forum_id, display_name, dossier_version = _parse_header(lines, locator)
    sections: list[_OpenSection] = []
    current: _OpenSection | None = None
    index = 4
    while index < len(lines):
        line = lines[index]
        number = index + 1
        if line == "":
            index += 1
            continue
        if line == "### Fuente":
            if current is None:
                fail(number, "«### Fuente» debe ir dentro de una sección")
            if current.status is not DossierSectionStatus.PROVIDED:
                fail(number, f"«{current.heading}» tiene «Estado:» y fuentes a la vez; borra la "
                             "línea «Estado:» si aportas fuentes")
            index = _parse_source(lines, index, current, locator)
            current.phase = "sources"
            continue
        if _ATX_HEADING.match(line):
            current = _open_section(line, number, sections, locator)
            sections.append(current)
            index += 1
            continue
        if current is None:
            fail(number, "texto inesperado antes de «## Normas generales»")
        if line.startswith("Estado:"):
            _parse_status(line, number, current, locator)
        elif line.startswith("Nota:"):
            _parse_note(line, number, current, locator)
        elif line.startswith("Metadatos:"):
            fail(number, "«Metadatos:» debe ir justo después de «### Fuente»")
        elif _FENCE_LIKE.match(line):
            fail(number, "valla de texto sin una fuente en línea justo antes; revisa «### Fuente» "
                         "y que «Metadatos:» no lleve «archivo»")
        else:
            fail(number, "texto inesperado; fuera de una valla solo se admiten encabezados, "
                         "«Estado:», «Nota:», «### Fuente» y «Metadatos:» (sin sangría ni "
                         "espacios finales)")
        index += 1
    if len(sections) < len(_HEADING_ORDER):
        fail(len(lines), f"falta el encabezado «## {_HEADING_ORDER[len(sections)]}»")

    occurrences: list[tuple[DossierSourceSpec, int]] = []
    first_seen: dict[tuple[str, str], tuple[DossierSourceSpec, int]] = {}
    for open_section in sections:
        for spec, line, _ in open_section.sources:
            first, first_line = first_seen.setdefault(spec.key, (spec, line))
            conflict = _repeat_conflict(first, spec)
            if conflict:
                fail(line, _repeat_reason(spec, conflict, first_line))
            occurrences.append((spec, line))

    domain = []
    for open_section in sections[:-1]:
        try:
            domain.append(
                DossierSectionSpec(
                    open_section.section,
                    open_section.status,
                    open_section.notes,
                    tuple(spec for spec, _, _ in open_section.sources),
                )
            )
        except DossierError as exc:
            raise DossierError(locator, open_section.line, exc.reason) from exc
    loose = tuple(
        LooseMaterialSpec(spec, suggestions) for spec, _, suggestions in sections[-1].sources
    )
    dossier = ForumDossier(
        DOSSIER_SCHEMA_VERSION, forum_id, display_name, dossier_version, tuple(domain), loose
    )
    return dossier, occurrences


def _canonical_lines(text: object, locator: str) -> list[str]:
    if not isinstance(text, str):
        raise DossierError(locator, None, "el expediente debe ser texto")
    if text.startswith("﻿"):
        raise DossierError(locator, 1, "el texto empieza con BOM; guárdalo como UTF-8 sin BOM")
    canonical = text.replace("\r\n", "\n")
    lone_cr = canonical.find("\r")
    if lone_cr != -1:
        line = canonical.count("\n", 0, lone_cr) + 1
        raise DossierError(locator, line, "retorno de carro (CR) suelto; usa saltos LF o CRLF")
    return canonical.split("\n")


def _parse_header(lines: list[str], locator: str) -> tuple[str, str, str]:
    if not lines or lines[0] != _HEADER_TITLE:
        raise DossierError(locator, 1, f"la primera línea debe ser «{_HEADER_TITLE}»")
    values = []
    for offset, key in enumerate(_HEADER_KEYS, start=1):
        number = offset + 1
        line = lines[offset] if offset < len(lines) else None
        prefix = f"{key}: "
        if line is None or not line.startswith(prefix):
            raise DossierError(locator, number, f"la línea {number} debe ser «{prefix}<valor>»")
        value = line[len(prefix):]
        try:
            if key == "forum_id":
                _check_forum_id("cabecera", value)
            else:
                _check_text("cabecera", key, value)
        except DossierError as exc:
            raise DossierError(locator, number, exc.reason) from exc
        values.append(value)
    return values[0], values[1], values[2]


def _open_section(
    line: str, number: int, sections: list[_OpenSection], locator: str
) -> _OpenSection:
    title = line[3:] if line.startswith("## ") else None
    if title not in _HEADING_ORDER:
        raise DossierError(locator, number, f"encabezado desconocido «{line}»")
    expected = _HEADING_ORDER[len(sections)] if len(sections) < len(_HEADING_ORDER) else None
    if title != expected:
        if any(s.heading == title for s in sections):
            raise DossierError(locator, number, f"encabezado repetido «{line}»")
        raise DossierError(locator, number, f"encabezado fuera de orden; se esperaba «## {expected}»")
    section = None if title == _LOOSE_HEADING else _SECTION_BY_HEADING[title]
    return _OpenSection(heading=title, line=number, section=section)


def _parse_status(line: str, number: int, current: _OpenSection, locator: str) -> None:
    if current.section is None:
        raise DossierError(locator, number, "«Material suelto» no admite «Estado:»")
    if current.phase != "start":
        raise DossierError(locator, number, "«Estado:» debe ser la primera línea de la sección")
    marker = line[len("Estado: "):] if line.startswith("Estado: ") else None
    if marker not in _STATUS_MARKERS:
        raise DossierError(locator, number, "estado desconocido; usa «Estado: FALTA» o "
                                            "«Estado: NO APLICA», u omítelo si aportas fuentes")
    status = _STATUS_MARKERS[marker]
    if status is DossierSectionStatus.NOT_APPLICABLE and current.section in REQUIRED_SECTIONS:
        raise DossierError(locator, number, f"«{current.heading}» es obligatoria y no admite "
                                            "«Estado: NO APLICA»; usa «Estado: FALTA»")
    current.status = status
    current.phase = "status"


def _parse_note(line: str, number: int, current: _OpenSection, locator: str) -> None:
    if current.section is None:
        raise DossierError(locator, number, "«Material suelto» no admite «Nota:»")
    if current.phase not in ("start", "status"):
        raise DossierError(locator, number, "solo se admite una «Nota:», antes de las fuentes")
    if not line.startswith("Nota: "):
        raise DossierError(locator, number, "escribe la nota como «Nota: <texto>»")
    note = line[len("Nota: "):]
    try:
        _check_text("Nota", "Nota", note)
    except DossierError as exc:
        raise DossierError(locator, number, exc.reason) from exc
    current.notes = note
    current.phase = "note"


def _parse_source(lines: list[str], index: int, current: _OpenSection, locator: str) -> int:
    """Parse the source starting at `### Fuente` (lines[index]); return the next line index."""
    meta_index = index + 1
    while meta_index < len(lines) and lines[meta_index] == "":
        meta_index += 1
    if meta_index >= len(lines) or not lines[meta_index].startswith(_META_PREFIX):
        raise DossierError(locator, min(meta_index, len(lines) - 1) + 1,
                           "se esperaba «Metadatos: ...» tras «### Fuente»")
    meta_line = meta_index + 1
    fields = _parse_metadata(lines[meta_index], meta_line, current.section is None, locator)
    after = meta_index + 1
    inline_text = None
    if fields["archivo"] is not None:
        if after < len(lines) and _FENCE_LIKE.match(lines[after]):
            raise DossierError(locator, after + 1,
                               "una fuente con «archivo» no lleva texto en línea; quita la valla "
                               "o quita «archivo»")
        next_index = after
    else:
        inline_text, next_index = _parse_fence(lines, after, meta_line, locator)
    try:
        spec = DossierSourceSpec(
            source_id=fields["id"],
            version=fields["versión"],
            authority=fields["autoridad"],
            scope=fields["alcance"],
            effective_from=fields["desde"],
            effective_until=fields["hasta"],
            section_or_passage=fields["pasaje"],
            path=fields["archivo"],
            inline_text=inline_text,
        )
    except DossierError as exc:
        raise DossierError(locator, meta_line, exc.reason) from exc
    current.sources.append((spec, meta_line, fields["sugerencias"]))
    return next_index


def _parse_fence(lines: list[str], index: int, meta_line: int, locator: str) -> tuple[str, int]:
    match = _FENCE_OPEN.fullmatch(lines[index]) if index < len(lines) else None
    if match is None:
        raise DossierError(locator, meta_line + 1,
                           "sin «archivo», la línea siguiente a «Metadatos:» debe abrir el texto "
                           "con «~~~~ texto» (cuatro o más virgulillas)")
    fence = match.group(1)
    close = index + 1
    while close < len(lines) and lines[close] != fence:
        close += 1
    if close >= len(lines):
        raise DossierError(locator, index + 1, f"la valla «{fence}» no tiene cierre")
    literal = "".join(line + "\n" for line in lines[index + 1:close])
    if not literal.strip():
        raise DossierError(locator, index + 1, "el texto en línea está vacío")
    for offset, line in enumerate(lines[index + 1:close], start=index + 2):
        longest = max((len(run) for run in _TILDE_RUN.findall(line)), default=0)
        if longest >= len(fence):
            raise DossierError(locator, offset,
                               f"el texto contiene {longest} virgulillas seguidas; usa una valla de "
                               f"al menos {longest + 1}, o comprueba que la valla abierta en la "
                               f"línea {index + 1} tenga su cierre")
    return literal, close + 1


class _ConstantError(ValueError):
    pass


def _reject_constant(name: str) -> object:
    raise _ConstantError(name)


_DECODER = json.JSONDecoder(parse_constant=_reject_constant)


def _parse_metadata(line: str, number: int, loose: bool, locator: str) -> dict[str, object]:
    def fail(reason: str) -> None:
        raise DossierError(locator, number, reason)

    values: dict[str, object] = {}
    position = len(_META_PREFIX)
    while True:
        equals = line.find("=", position)
        if equals == -1:
            fail("se esperaba «clave=valor» en «Metadatos:»")
        key = line[position:equals]
        if key not in _META_KEYS:
            fail(f"clave desconocida «{key}»; se admiten: {', '.join(_META_KEYS)}")
        if key in values:
            fail(f"clave repetida «{key}»")
        try:
            value, end = _DECODER.raw_decode(line, equals + 1)
        except json.JSONDecodeError as exc:
            raise DossierError(locator, number,
                               f"valor de «{key}» no es JSON válido ({exc.msg}); los textos van "
                               f"entre comillas dobles y sin fecha se escribe null") from exc
        except _ConstantError as exc:
            raise DossierError(locator, number, f"valor de «{key}» no admite {exc}") from exc
        except RecursionError as exc:
            raise DossierError(locator, number, f"valor de «{key}» anidado en exceso") from exc
        except ValueError as exc:
            raise DossierError(locator, number, f"valor de «{key}» no válido ({exc})") from exc
        values[key] = value
        if end == len(line):
            break
        if not line.startswith(_META_SEPARATOR, end):
            fail(f"texto inesperado tras el valor de «{key}»; separa los campos con « | »")
        position = end + len(_META_SEPARATOR)

    missing = [key for key in _META_REQUIRED if key not in values]
    if missing:
        fail(f"faltan claves obligatorias: {', '.join(missing)}")
    for key in _META_REQUIRED:
        if not isinstance(values[key], str):
            fail(f"«{key}» debe ser un texto entre comillas")
    fields: dict[str, object] = {key: values[key] for key in _META_REQUIRED}
    for key in ("desde", "hasta"):
        fields[key] = _parse_date(values.get(key), key, fail)
    for key in ("pasaje", "archivo"):
        value = values.get(key)
        if value is not None and not isinstance(value, str):
            fail(f"«{key}» debe ser un texto entre comillas o null")
        fields[key] = value
    if "sugerencias" in values and not loose:
        fail("«sugerencias» solo se admite en «Material suelto»")
    fields["sugerencias"] = _parse_suggestions(values.get("sugerencias", []), fail)
    return fields


def _parse_date(value: object, key: str, fail) -> date | None:
    if value is None:
        return None
    if isinstance(value, str) and _ISO_DATE.fullmatch(value):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    fail(f"«{key}» debe ser una fecha real \"AAAA-MM-DD\" o null")


def _parse_suggestions(value: object, fail) -> tuple[DossierSection, ...]:
    if not isinstance(value, list):
        fail("«sugerencias» debe ser una lista, p. ej. [\"Ambientación\"]")
    sections = []
    for item in value:
        if not isinstance(item, str):
            fail("cada sugerencia debe ser el nombre de una sección entre comillas")
        if item not in _SECTION_BY_HEADING:
            names = ", ".join(f"\"{h}\"" for h in _SECTION_BY_HEADING)
            fail(f"sugerencia desconocida {json.dumps(item, ensure_ascii=False)}; usa: {names}")
        section = _SECTION_BY_HEADING[item]
        if section in sections:
            fail(f"«sugerencias» repite \"{item}\"")
        sections.append(section)
    return tuple(sections)


# --- Validation helpers -----------------------------------------------------------------------


def _fail(owner: str, reason: str) -> None:
    raise DossierError(owner, None, reason)


def _check_text(owner: str, name: str, value: object) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        _fail(owner, f"«{name}» debe ser un texto no vacío sin espacios al principio ni al final")
    if _CONTROL.search(value):
        _fail(owner, f"«{name}» contiene caracteres de control")
    _check_utf8(owner, name, value)


def _check_utf8(owner: str, name: str, value: str) -> None:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        _fail(owner, f"«{name}» contiene caracteres que no se pueden guardar en UTF-8")


def _check_forum_id(owner: str, value: object) -> None:
    if not isinstance(value, str) or not _FORUM_ID.fullmatch(value):
        _fail(owner, "forum_id solo admite minúsculas ASCII, dígitos y guiones simples "
                     "(p. ej. «mi-foro»)")


def _check_relative_path(owner: str, value: object) -> None:
    if not isinstance(value, str) or not value:
        _fail(owner, "«archivo» debe ser una ruta no vacía")
    if "\\" in value:
        _fail(owner, "«archivo» debe usar «/» como separador")
    if value.startswith("/"):
        _fail(owner, "«archivo» debe ser relativa a la carpeta del expediente")
    if ":" in value:
        _fail(owner, "«archivo» no admite «:» (unidades de Windows o flujos alternativos)")
    if _CONTROL.search(value):
        _fail(owner, "«archivo» contiene caracteres de control")
    _check_utf8(owner, "archivo", value)
    for segment in value.split("/"):
        if segment in ("", ".", ".."):
            _fail(owner, "«archivo» no admite segmentos vacíos, «.» ni «..»")
        if segment != segment.rstrip(". "):
            _fail(owner, "«archivo» no admite nombres que terminen en punto o espacio")


def _repeat_conflict(first: DossierSourceSpec, other: DossierSourceSpec) -> str | None:
    if first.key != other.key:
        return None
    for name, attribute in (
        ("autoridad", "authority"),
        ("alcance", "scope"),
        ("desde", "effective_from"),
        ("hasta", "effective_until"),
        ("archivo", "path"),
        ("texto en línea", "inline_text"),
    ):
        if getattr(first, attribute) != getattr(other, attribute):
            return name
    return None


def _repeat_reason(spec: DossierSourceSpec, field: str, first_line: int | None) -> str:
    where = f" en la línea {first_line}" if first_line is not None else ""
    return (
        f"la fuente id=\"{spec.source_id}\" versión=\"{spec.version}\" ya se declaró{where} con "
        f"otro valor de «{field}»; una misma id y versión deben coincidir salvo «pasaje» "
        f"(usa otra versión si el contenido cambió)"
    )


def _decode_utf8(raw: bytes, locator: str, line: int | None) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        where = line if line is not None else raw.count(b"\n", 0, exc.start) + 1
        raise DossierError(locator, where, "el archivo no es UTF-8 válido") from exc


def _read_source_file(
    dossier_dir: Path, root: Path, relative: str, locator: str, line: int
) -> tuple[str, str, str]:
    try:
        return _read_checked_source_file(dossier_dir, root, relative, locator, line)
    except OSError as exc:
        raise DossierError(locator, line, f"no se pudo leer «archivo» {relative}: {exc}") from exc


def _read_checked_source_file(
    dossier_dir: Path, root: Path, relative: str, locator: str, line: int
) -> tuple[str, str, str]:
    candidate = dossier_dir
    for segment in relative.split("/"):
        candidate = candidate / segment
        if candidate.is_symlink():
            raise DossierError(locator, line, f"«archivo» atraviesa un enlace simbólico: {relative}")
    if not candidate.is_file():
        raise DossierError(locator, line, f"«archivo» no existe o no es un archivo: {relative}")
    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise DossierError(locator, line, f"«archivo» sale de la carpeta del expediente: {relative}")
    raw = candidate.read_bytes()
    try:
        literal = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DossierError(locator, line, f"«archivo» no es UTF-8 válido: {relative}") from exc
    if not literal.strip():
        raise DossierError(locator, line, f"«archivo» está vacío: {relative}")
    return literal, _sha256(raw), candidate.as_posix()


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


# --- Assimilation candidates (4b) -------------------------------------------------------------
# A candidate is a cited proposal about the forum's rules or setting. Creating one never approves
# it: every candidate stays PENDING_HUMAN_REVIEW until a human decision (4c).


class AssimilationDomain(str, Enum):
    RULES = "RULES"
    WORLD = "WORLD"


class CandidateClass(str, Enum):
    LITERAL = "LITERAL"
    INTERPRETATION = "INTERPRETATION"
    PROPOSAL = "PROPOSAL"
    UNCERTAINTY = "UNCERTAINTY"


_DOMAIN_BY_SECTION = {
    section: (AssimilationDomain.WORLD if section is DossierSection.SETTING
              else AssimilationDomain.RULES)
    for section in DossierSection
}
_CANDIDATE_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_SHA256_HEX = re.compile(r"[0-9a-f]{64}")
_ASSIMILATION_CODES = frozenset({"INVALID_STATE", "CONFLICT", "IO"})
_INPUT_KEYS = frozenset({"candidate_id", "version", "domain", "class", "text", "scope",
                         "citations"})
_INPUT_CITATION_KEYS = frozenset({"dossier_section", "source_id", "source_version",
                                  "declared_passage", "quote"})
_RECORD_KEYS = frozenset({"candidate_id", "candidate_sha256", "citations", "class", "domain",
                          "review_status", "scope", "text", "version"})
_RECORD_CITATION_KEYS = frozenset({"declared_passage", "dossier_section", "end", "quote",
                                   "source_id", "source_sha256", "source_version", "start"})
_CORPUS_KEYS = frozenset({"candidates", "closure", "decisions"})


class AssimilationError(ValueError):
    """`code` is INVALID_STATE, CONFLICT or IO."""

    def __init__(self, code: str, reason: str):
        if code not in _ASSIMILATION_CODES:
            raise ValueError(f"unknown assimilation error code {code!r}")
        self.code = code
        self.reason = reason
        super().__init__(f"{code}: {reason}")


@dataclass(frozen=True, slots=True)
class CandidateCitation:
    """An exact, half-open character range of a loaded source literal."""

    dossier_section: DossierSection
    source_id: str
    source_version: str
    source_sha256: str
    declared_passage: str | None
    start: int
    end: int
    quote: str

    def __post_init__(self) -> None:
        if not isinstance(self.dossier_section, DossierSection):
            _invalid_candidate("la sección de la cita es desconocida")
        _require_candidate_text("source_id", self.source_id)
        _require_candidate_text("source_version", self.source_version)
        if self.declared_passage is not None:
            _require_candidate_text("declared_passage", self.declared_passage)
        if not isinstance(self.source_sha256, str) or not _SHA256_HEX.fullmatch(self.source_sha256):
            _invalid_candidate("source_sha256 debe ser un SHA-256 en minúsculas")
        for name in ("start", "end"):
            if type(getattr(self, name)) is not int:
                _invalid_candidate(f"{name} debe ser un entero")
        _require_content("quote", self.quote)
        if not 0 <= self.start < self.end or self.end - self.start != len(self.quote):
            _invalid_candidate("el rango de la cita no corresponde a la longitud de quote")

    @property
    def coordinate(self) -> tuple:
        return (self.dossier_section, self.source_id, self.source_version,
                self.declared_passage, self.start, self.end)


@dataclass(frozen=True, slots=True)
class AssimilationCandidate:
    candidate_id: str
    version: int
    domain: AssimilationDomain
    candidate_class: CandidateClass
    text: str
    scope: str
    citations: tuple[CandidateCitation, ...]
    review_status: ReviewStatus = ReviewStatus.PENDING_HUMAN_REVIEW
    candidate_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_id, str) or not _CANDIDATE_ID.fullmatch(self.candidate_id):
            _invalid_candidate("candidate_id solo admite minúsculas ASCII, dígitos y guiones "
                               "simples (p. ej. «convivencia-respeto»)")
        if type(self.version) is not int or self.version < 1:
            _invalid_candidate("version debe ser un entero positivo")
        if not isinstance(self.domain, AssimilationDomain):
            _invalid_candidate("domain debe ser RULES o WORLD")
        if not isinstance(self.candidate_class, CandidateClass):
            _invalid_candidate("class debe ser LITERAL, INTERPRETATION, PROPOSAL o UNCERTAINTY")
        _require_content("text", self.text)
        _require_candidate_text("scope", self.scope)
        if self.review_status is not ReviewStatus.PENDING_HUMAN_REVIEW:
            _invalid_candidate("un candidato nuevo solo puede estar PENDING_HUMAN_REVIEW")
        if not isinstance(self.citations, tuple) or not self.citations or not all(
            isinstance(c, CandidateCitation) for c in self.citations
        ):
            _invalid_candidate("citations debe ser una tupla no vacía de citas")
        if len({c.coordinate for c in self.citations}) != len(self.citations):
            _invalid_candidate("una cita está repetida")
        for citation in self.citations:
            if _DOMAIN_BY_SECTION[citation.dossier_section] is not self.domain:
                _invalid_candidate(
                    f"una cita de «{_HEADINGS[citation.dossier_section]}» no pertenece al dominio "
                    f"{self.domain.value}; WORLD solo admite «{_HEADINGS[DossierSection.SETTING]}»"
                )
        if self.candidate_class is CandidateClass.LITERAL:
            if len(self.citations) != 1:
                _invalid_candidate("un LITERAL lleva exactamente una cita")
            if self.text != self.citations[0].quote:
                _invalid_candidate("en un LITERAL, text debe ser idéntico a la cita")
        record = _candidate_record(self, include_hash=False)
        object.__setattr__(self, "candidate_sha256",
                           hashlib.sha256(canonical_json_bytes(record, pretty=False)).hexdigest())

    @property
    def key(self) -> tuple[str, int]:
        return (self.candidate_id, self.version)

    @property
    def requires_confirmation(self) -> bool:
        return self.candidate_class is CandidateClass.UNCERTAINTY


@dataclass(frozen=True, slots=True)
class CandidateAddResult:
    candidate: AssimilationCandidate
    created: bool
    corpus_revision: int


def parse_candidate_input(value: object, *, dossier: LoadedForumDossier) -> AssimilationCandidate:
    """Build a candidate from the author's JSON: the core locates each quote and fixes its range."""
    if not isinstance(value, dict) or set(value) != _INPUT_KEYS:
        _invalid_candidate("el candidato debe tener exactamente las claves "
                           f"{', '.join(sorted(_INPUT_KEYS))}")
    citations_value = value["citations"]
    if not isinstance(citations_value, list) or not citations_value:
        _invalid_candidate("citations debe ser una lista no vacía")
    declarations = _source_declarations(dossier)
    citations = tuple(_resolve_input_citation(i, item, declarations)
                      for i, item in enumerate(citations_value, start=1))
    return AssimilationCandidate(
        candidate_id=value["candidate_id"],
        version=value["version"],
        domain=_enum_value(AssimilationDomain, value["domain"], "domain"),
        candidate_class=_enum_value(CandidateClass, value["class"], "class"),
        text=value["text"],
        scope=value["scope"],
        citations=citations,
    )


def decode_candidate_state(
    content: object, *, dossier: LoadedForumDossier, revision: int
) -> AssimilationState:
    """Rebuild and re-verify candidates, decisions and closure against the copied dossier."""
    if not isinstance(content, dict) or set(content) != _CORPUS_KEYS:
        _invalid_candidate("el corpus debe tener exactamente candidates, closure y decisions")
    records = content["candidates"]
    if not isinstance(records, list):
        _invalid_candidate("candidates debe ser una lista")
    declarations = _source_declarations(dossier)
    candidates: list[AssimilationCandidate] = []
    latest: dict[str, int] = {}
    for position, record in enumerate(records, start=1):
        candidate = _decode_record(position, record, declarations)
        expected = latest.get(candidate.candidate_id, 0) + 1
        if candidate.version != expected:
            _invalid_candidate(f"el candidato {candidate.candidate_id} salta de la versión "
                               f"{expected - 1} a la {candidate.version}")
        latest[candidate.candidate_id] = candidate.version
        candidates.append(candidate)

    forum_id = dossier.dossier.forum_id
    by_key = {c.key: c for c in candidates}
    decision_records = content["decisions"]
    if not isinstance(decision_records, list):
        _invalid_candidate("decisions debe ser una lista")
    decisions: list[AssimilationDecision] = []
    for position, record in enumerate(decision_records, start=1):
        decision = _decode_decision(position, record, forum_id)
        candidate = by_key.get((decision.candidate_id, decision.candidate_version))
        if candidate is None or candidate.candidate_sha256 != decision.candidate_sha256:
            _invalid_candidate(f"la decisión {decision.decision_id} no corresponde a ningún "
                               "candidato exacto")
        if any(d.decision_id == decision.decision_id for d in decisions):
            _invalid_candidate(f"la decisión {decision.decision_id} está repetida")
        decisions.append(decision)

    state = AssimilationState(tuple(candidates), tuple(decisions), None)
    if content["closure"] is None:
        return state
    closure = _decode_closure(content["closure"], forum_id)
    if type(revision) is not int or closure.base_revision + 1 != revision:
        _invalid_candidate("el cierre no corresponde a la revisión del corpus")
    if closure.snapshot_sha256 != _snapshot_sha256(state):
        _invalid_candidate("el cierre no corresponde al contenido actual del corpus")
    blockers = _closure_blockers(state, dossier)
    if blockers:
        _invalid_candidate(f"el cierre no cumple sus condiciones: {'; '.join(blockers)}")
    return AssimilationState(state.candidates, state.decisions, closure)


def add_candidate(
    state_path: Path, *, dossier: LoadedForumDossier, expected_revision: int, value: object
) -> CandidateAddResult:
    """Append a new pending candidate version, or return the identical existing one."""
    with _corpus_lock(state_path):
        return _add_candidate_locked(state_path, dossier, expected_revision, value)


def _add_candidate_locked(
    state_path: Path, dossier: LoadedForumDossier, expected_revision: int, value: object
) -> CandidateAddResult:
    revision, content, state = _load_corpus(state_path, dossier, expected_revision)
    candidate = parse_candidate_input(value, dossier=dossier)
    by_key = {c.key: c for c in state.candidates}
    if candidate.key in by_key:
        if by_key[candidate.key].candidate_sha256 == candidate.candidate_sha256:
            return CandidateAddResult(by_key[candidate.key], False, revision)
        raise AssimilationError("CONFLICT", f"{candidate.candidate_id} v{candidate.version} ya "
                                            "existe con otro contenido; usa una versión nueva")
    if state.closure is not None:
        raise AssimilationError("CONFLICT", "la asimilación está cerrada; una corrección requiere "
                                            "otro workspace")
    versions = [c for c in state.candidates if c.candidate_id == candidate.candidate_id]
    expected_version = len(versions) + 1
    if candidate.version != expected_version:
        raise AssimilationError("CONFLICT", f"la siguiente versión de {candidate.candidate_id} es "
                                            f"la {expected_version}, no la {candidate.version}")
    if versions and _semantic_payload(versions[-1]) == _semantic_payload(candidate):
        raise AssimilationError("CONFLICT", f"la versión {candidate.version} de "
                                            f"{candidate.candidate_id} no cambia nada respecto a "
                                            "la anterior")
    new_content = dict(content)
    new_content["candidates"] = [*content["candidates"],
                                 _candidate_record(candidate, include_hash=True)]
    _write_corpus(state_path, new_content, revision + 1)
    return CandidateAddResult(candidate, True, revision + 1)


# --- Human decisions and closure (4c1) --------------------------------------------------------
# Decisions and the closure are only recorded after someone types, in an interactive terminal,
# a phrase containing a one-time code (barrier A, chosen by the user). LIMIT: this blocks an
# agent's normal, automated command path, but it does not authenticate a person and is not a
# cryptographic guarantee: code that imports this module and passes a fake Terminal, a pseudo
# terminal, or an edited core can bypass it.

HUMAN_CONFIRMATION_METHOD = "TTY_NONCE_V1"
NONCE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
NONCE_LENGTH = 8
CLOSURE_ID = "assimilation-closure"

_DECISION_STATUSES = (ReviewStatus.APPROVED, ReviewStatus.REJECTED)
_PHRASE_VERB = {ReviewStatus.APPROVED: "APROBAR", ReviewStatus.REJECTED: "RECHAZAR"}
_RECEIPT_KEYS = frozenset({"confirmation_sha256", "method"})
_EVIDENCE_KEYS = frozenset({"locator", "section_or_passage", "sha256", "source_id"})
_DECISION_KEYS = frozenset({"candidate_id", "candidate_sha256", "candidate_version",
                            "decision_id", "evidence", "receipt", "review_status"})
_CLOSURE_KEYS = frozenset({"base_revision", "closure_id", "evidence", "receipt",
                           "snapshot_sha256"})


class Terminal(Protocol):
    """Where the confirmation is answered.

    The CLI only uses the real terminal and offers no way to supply the one-time code. Passing
    any other implementation (as tests do) bypasses barrier A: it does not authenticate a person.
    """

    def is_interactive(self) -> bool: ...

    def write(self, text: str) -> None: ...

    def read_line(self) -> str | None: ...


@dataclass(frozen=True, slots=True)
class HumanConfirmationReceipt:
    method: str
    confirmation_sha256: str

    def __post_init__(self) -> None:
        if self.method != HUMAN_CONFIRMATION_METHOD:
            _invalid_candidate(f"método de confirmación desconocido: {self.method!r}")
        _require_sha256("confirmation_sha256", self.confirmation_sha256)


@dataclass(frozen=True, slots=True)
class AssimilationDecision:
    decision_id: str
    candidate_id: str
    candidate_version: int
    candidate_sha256: str
    review_status: ReviewStatus
    receipt: HumanConfirmationReceipt
    evidence: SourceRef

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_id, str) or not _CANDIDATE_ID.fullmatch(self.candidate_id):
            _invalid_candidate("candidate_id inválido en una decisión")
        if type(self.candidate_version) is not int or self.candidate_version < 1:
            _invalid_candidate("candidate_version debe ser un entero positivo")
        if self.decision_id != _decision_id(self.candidate_id, self.candidate_version):
            _invalid_candidate("decision_id no corresponde al candidato y su versión")
        _require_sha256("candidate_sha256", self.candidate_sha256)
        if self.review_status not in _DECISION_STATUSES:
            _invalid_candidate("una decisión solo puede ser APPROVED o REJECTED")
        if not isinstance(self.receipt, HumanConfirmationReceipt):
            _invalid_candidate("la decisión necesita un recibo de confirmación humana")
        if not isinstance(self.evidence, SourceRef):
            _invalid_candidate("la decisión necesita evidencia SourceRef")

    @property
    def candidate_key(self) -> tuple[str, int]:
        return (self.candidate_id, self.candidate_version)


@dataclass(frozen=True, slots=True)
class AssimilationClosure:
    closure_id: str
    base_revision: int
    snapshot_sha256: str
    receipt: HumanConfirmationReceipt
    evidence: SourceRef

    def __post_init__(self) -> None:
        if self.closure_id != CLOSURE_ID:
            _invalid_candidate(f"closure_id debe ser {CLOSURE_ID}")
        if type(self.base_revision) is not int or self.base_revision < 0:
            _invalid_candidate("base_revision debe ser un entero no negativo")
        _require_sha256("snapshot_sha256", self.snapshot_sha256)
        if not isinstance(self.receipt, HumanConfirmationReceipt):
            _invalid_candidate("el cierre necesita un recibo de confirmación humana")
        if not isinstance(self.evidence, SourceRef):
            _invalid_candidate("el cierre necesita evidencia SourceRef")


@dataclass(frozen=True, slots=True)
class AssimilationState:
    candidates: tuple[AssimilationCandidate, ...]
    decisions: tuple[AssimilationDecision, ...]
    closure: AssimilationClosure | None

    def current_versions(self) -> tuple[AssimilationCandidate, ...]:
        """The highest version of each candidate id, in first-appearance order."""
        latest: dict[str, AssimilationCandidate] = {}
        for candidate in self.candidates:
            latest[candidate.candidate_id] = candidate
        return tuple(latest.values())

    def decision_for(self, candidate: AssimilationCandidate) -> AssimilationDecision | None:
        for decision in self.decisions:
            if decision.candidate_key == candidate.key:
                return decision
        return None


@dataclass(frozen=True, slots=True)
class DecisionResult:
    decision: AssimilationDecision
    created: bool
    corpus_revision: int


@dataclass(frozen=True, slots=True)
class ClosureResult:
    closure: AssimilationClosure
    created: bool
    corpus_revision: int


def record_candidate_decision(
    state_path: Path, *, dossier: LoadedForumDossier, expected_revision: int, candidate_id: str,
    version: int, review_status: ReviewStatus, terminal: Terminal,
) -> DecisionResult:
    """Record APPROVED/REJECTED for exactly one current candidate version.

    Requires the exact phrase typed in `terminal`. Barrier A blocks the automated command path
    but does not authenticate a person: a fake terminal or pseudo terminal bypasses it.
    """
    _require_interactive(terminal)
    if review_status not in _DECISION_STATUSES:
        _invalid_candidate("la decisión debe ser APPROVED o REJECTED")
    revision, content, state = _load_corpus(state_path, dossier, expected_revision)
    candidate = _decidable_candidate(state, candidate_id, version)
    existing = state.decision_for(candidate)
    if existing is not None:
        if existing.review_status is review_status:
            return DecisionResult(existing, False, revision)
        raise AssimilationError("CONFLICT", f"{candidate_id} v{version} ya tiene la decisión "
                                            f"{existing.review_status.value}; para cambiarla crea "
                                            "una versión nueva del candidato")
    if state.closure is not None:
        raise AssimilationError("CONFLICT", "la asimilación está cerrada")
    if candidate.version != _latest_version(state, candidate_id):
        raise AssimilationError("CONFLICT", f"{candidate_id} v{version} ya no es la versión "
                                            "vigente; decide sobre la última")
    _require_unlocked(state_path)
    verb = _PHRASE_VERB[review_status]
    nonce = _nonce()
    phrase = f"{verb} {candidate_id} v{version} {nonce}"
    _confirm(terminal, phrase, [
        "DECISIÓN HUMANA REQUERIDA",
        f"Candidato: {candidate_id}",
        f"Versión: {version}",
        f"SHA-256: {candidate.candidate_sha256}",
        f"Decisión: {verb}",
    ])
    receipt = HumanConfirmationReceipt(HUMAN_CONFIRMATION_METHOD, _sha256_text(phrase))
    decision_id = _decision_id(candidate_id, version)
    payload = {
        "candidate_id": candidate_id,
        "candidate_sha256": candidate.candidate_sha256,
        "candidate_version": version,
        "decision_id": decision_id,
        "receipt": _receipt_record(receipt),
        "review_status": review_status.value,
    }
    decision = AssimilationDecision(decision_id, candidate_id, version,
                                    candidate.candidate_sha256, review_status, receipt,
                                    _evidence(dossier.dossier.forum_id, decision_id, payload))
    with _corpus_lock(state_path):
        revision_again, content, state = _load_corpus(state_path, dossier, None)
        if (revision_again != revision or state.closure is not None
                or _decidable_candidate(state, candidate_id, version) != candidate
                or state.decision_for(candidate) is not None):
            raise AssimilationError("CONFLICT", "el corpus cambió mientras se confirmaba; repite")
        new_content = dict(content)
        new_content["decisions"] = [*content["decisions"], _decision_record(decision)]
        _write_corpus(state_path, new_content, revision + 1)
    return DecisionResult(decision, True, revision + 1)


def close_assimilation(
    state_path: Path, *, dossier: LoadedForumDossier, expected_revision: int, terminal: Terminal
) -> ClosureResult:
    """Close the corpus snapshot after the exact phrase is typed. Closing is terminal.

    Barrier A blocks the automated command path but does not authenticate a person: a fake
    terminal or pseudo terminal bypasses it.
    """
    _require_interactive(terminal)
    revision, content, state = _load_corpus(state_path, dossier, expected_revision)
    if state.closure is not None:
        return ClosureResult(state.closure, False, revision)
    blockers = _closure_blockers(state, dossier)
    if blockers:
        _invalid_candidate(f"todavía no se puede cerrar: {'; '.join(blockers)}")
    forum_id = dossier.dossier.forum_id
    snapshot = _snapshot_sha256(state)
    current = state.current_versions()
    statuses = [state.decision_for(c).review_status for c in current]
    rejected = [c for c, s in zip(current, statuses) if s is ReviewStatus.REJECTED]
    uncertain = [c for c in current if c.requires_confirmation]
    _require_unlocked(state_path)
    nonce = _nonce()
    phrase = f"CERRAR {forum_id} r{revision} {nonce}"
    _confirm(terminal, phrase, [
        "CIERRE HUMANO REQUERIDO",
        f"Foro: {forum_id}",
        f"Revisión del corpus: {revision}",
        f"Snapshot SHA-256: {snapshot}",
        f"Vigentes: {len(current)}; aprobados: {statuses.count(ReviewStatus.APPROVED)}; "
        f"rechazados: {len(rejected)}",
        f"Rechazados: {_candidate_names(rejected) or 'ninguno'}",
        f"Incertidumbres: {_candidate_names(uncertain) or 'ninguna'}",
    ])
    receipt = HumanConfirmationReceipt(HUMAN_CONFIRMATION_METHOD, _sha256_text(phrase))
    payload = {
        "base_revision": revision,
        "closure_id": CLOSURE_ID,
        "receipt": _receipt_record(receipt),
        "snapshot_sha256": snapshot,
    }
    closure = AssimilationClosure(CLOSURE_ID, revision, snapshot, receipt,
                                  _evidence(forum_id, CLOSURE_ID, payload))
    with _corpus_lock(state_path):
        revision_again, content, state_again = _load_corpus(state_path, dossier, None)
        if (revision_again != revision or state_again.closure is not None
                or _snapshot_sha256(state_again) != snapshot):
            raise AssimilationError("CONFLICT", "el corpus cambió mientras se confirmaba; repite")
        new_content = dict(content)
        new_content["closure"] = _closure_record(closure)
        _write_corpus(state_path, new_content, revision + 1)
    return ClosureResult(closure, True, revision + 1)


def _load_corpus(
    state_path: Path, dossier: LoadedForumDossier, expected_revision: int | None
) -> tuple[int, dict, AssimilationState]:
    try:
        revision, content = load_state(state_path)
    except PersistenceError as exc:
        raise AssimilationError(exc.code, exc.reason) from exc
    if expected_revision is not None and revision != expected_revision:
        raise AssimilationError("CONFLICT", f"el corpus cambió (revisión {revision}, se esperaba "
                                            f"{expected_revision}); vuelve a intentarlo")
    state = decode_candidate_state(content, dossier=dossier, revision=revision)
    return revision, content, state


def _lock_path(state_path: Path) -> Path:
    return Path(state_path).with_name(Path(state_path).name + ".lock")


def _require_unlocked(state_path: Path) -> None:
    """Courtesy check before asking for a phrase; the lock itself is taken again to write."""
    if os.path.lexists(_lock_path(state_path)):
        raise AssimilationError("CONFLICT", f"otro proceso está modificando el corpus "
                                            f"({_lock_path(state_path)}); espera a que termine o, "
                                            "si no hay ninguno en marcha, borra ese archivo")


@contextmanager
def _corpus_lock(state_path: Path):
    """Serialize every corpus mutation between processes: re-read, validate and write under it.

    The lock is a file created exclusively next to the state. If a process dies holding it, or
    the file cannot be removed, it stays and later mutations fail with CONFLICT until a person
    removes it; failing to remove it is always reported, never silenced.
    """
    lock = _lock_path(state_path)
    try:
        handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise AssimilationError("CONFLICT", f"otro proceso está modificando el corpus ({lock}); "
                                            "espera a que termine o, si no hay ninguno en "
                                            "marcha, borra ese archivo") from exc
    except OSError as exc:
        raise AssimilationError("IO", f"no se puede bloquear el corpus: {exc}") from exc
    try:
        os.close(handle)
    except OSError as exc:
        note = "" if _release_lock(lock) else f"; además no se pudo borrar {lock}: bórralo a mano"
        raise AssimilationError("IO", f"no se pudo preparar el cerrojo del corpus: {exc}{note}"
                                ) from exc
    try:
        yield
    except AssimilationError as exc:
        if _release_lock(lock):
            raise
        raise AssimilationError(exc.code, f"{exc.reason}; no se guardó ningún cambio, pero no se "
                                          f"pudo borrar el cerrojo {lock}: bórralo a mano antes "
                                          "de seguir") from exc
    except BaseException:
        _release_lock(lock)
        raise
    if not _release_lock(lock):
        raise AssimilationError("IO", f"el cambio se guardó, pero no se pudo borrar el cerrojo "
                                      f"{lock}: bórralo a mano antes de seguir")


def _release_lock(lock: Path) -> bool:
    """Remove the lock file; return False if it is still there."""
    try:
        os.unlink(lock)
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return True


def _write_corpus(state_path: Path, content: dict, revision: int) -> None:
    try:
        atomic_write_bytes(Path(state_path), encode_state(content, revision=revision))
    except PersistenceError as exc:
        raise AssimilationError(exc.code, exc.reason) from exc


def _require_interactive(terminal: Terminal) -> None:
    if not terminal.is_interactive():
        _invalid_candidate("esta decisión exige una terminal interactiva: ejecuta el comando tú "
                           "mismo en la terminal, sin redirigir la entrada ni la salida")


def _decidable_candidate(state: AssimilationState, candidate_id: str,
                         version: int) -> AssimilationCandidate:
    for candidate in state.candidates:
        if candidate.key == (candidate_id, version):
            return candidate
    _invalid_candidate(f"no existe el candidato {candidate_id} v{version}")


def _latest_version(state: AssimilationState, candidate_id: str) -> int:
    return max(c.version for c in state.candidates if c.candidate_id == candidate_id)


def _nonce() -> str:
    return "".join(secrets.choice(NONCE_ALPHABET) for _ in range(NONCE_LENGTH))


def _confirm(terminal: Terminal, phrase: str, lines: list[str]) -> None:
    """Show the request, read one answer and require the exact phrase. One attempt only."""
    terminal.write("".join(f"{line}\n" for line in lines)
                   + f"Escribe exactamente: {phrase}\n> ")
    answer = terminal.read_line()
    if answer is None:
        _invalid_candidate("confirmación cancelada (fin de la entrada); no se ha guardado nada")
    if answer.endswith("\n"):
        answer = answer[:-1]
        if answer.endswith("\r"):
            answer = answer[:-1]
    if answer != phrase:
        _invalid_candidate("la frase no coincide; no se ha guardado nada. Repite el comando para "
                           "obtener un código nuevo")


def _closure_blockers(state: AssimilationState, dossier: LoadedForumDossier) -> list[str]:
    blockers = []
    current = state.current_versions()
    pending = [c for c in current if state.decision_for(c) is None]
    if pending:
        blockers.append(f"faltan decisiones sobre {_candidate_names(pending)}")
    approved_literals = [c for c in current if c.candidate_class is CandidateClass.LITERAL
                         and (d := state.decision_for(c)) is not None
                         and d.review_status is ReviewStatus.APPROVED]
    covered = {citation.dossier_section for c in approved_literals for citation in c.citations}
    for section in dossier.dossier.sections:
        if section.status is DossierSectionStatus.PROVIDED and section.section not in covered:
            blockers.append(f"«{_HEADINGS[section.section]}» no tiene ningún LITERAL aprobado")
    return blockers


def _snapshot_sha256(state: AssimilationState) -> str:
    snapshot = {
        "candidates": [_candidate_record(c, include_hash=True) for c in state.candidates],
        "decisions": [_decision_record(d) for d in state.decisions],
    }
    return hashlib.sha256(canonical_json_bytes(snapshot, pretty=False)).hexdigest()


def _candidate_names(candidates) -> str:
    return ", ".join(f"{c.candidate_id} v{c.version}" for c in candidates)


def _decision_id(candidate_id: str, version: int) -> str:
    return f"candidate:{candidate_id}:v{version}"


def _evidence(forum_id: str, subject_id: str, payload: dict) -> SourceRef:
    return SourceRef(
        source_id=f"human-decision:{subject_id}",
        locator=f"assimilation://{forum_id}/human-decisions/{quote(subject_id, safe='')}",
        sha256=hashlib.sha256(canonical_json_bytes(payload, pretty=False)).hexdigest(),
        section_or_passage=subject_id,
    )


def _receipt_record(receipt: HumanConfirmationReceipt) -> dict:
    return {"confirmation_sha256": receipt.confirmation_sha256, "method": receipt.method}


def _evidence_record(evidence: SourceRef) -> dict:
    return {"locator": evidence.locator, "section_or_passage": evidence.section_or_passage,
            "sha256": evidence.sha256, "source_id": evidence.source_id}


def _decision_record(decision: AssimilationDecision) -> dict:
    return {
        "candidate_id": decision.candidate_id,
        "candidate_sha256": decision.candidate_sha256,
        "candidate_version": decision.candidate_version,
        "decision_id": decision.decision_id,
        "evidence": _evidence_record(decision.evidence),
        "receipt": _receipt_record(decision.receipt),
        "review_status": decision.review_status.value,
    }


def _closure_record(closure: AssimilationClosure) -> dict:
    return {
        "base_revision": closure.base_revision,
        "closure_id": closure.closure_id,
        "evidence": _evidence_record(closure.evidence),
        "receipt": _receipt_record(closure.receipt),
        "snapshot_sha256": closure.snapshot_sha256,
    }


def _decode_receipt(value: object, where: str) -> HumanConfirmationReceipt:
    if not isinstance(value, dict) or set(value) != _RECEIPT_KEYS:
        _invalid_candidate(f"{where}: recibo con claves inesperadas")
    return HumanConfirmationReceipt(value["method"], value["confirmation_sha256"])


def _check_evidence(value: object, expected: SourceRef, where: str) -> SourceRef:
    if not isinstance(value, dict) or set(value) != _EVIDENCE_KEYS:
        _invalid_candidate(f"{where}: evidencia con claves inesperadas")
    if value != _evidence_record(expected):
        _invalid_candidate(f"{where}: la evidencia no corresponde al registro (modificado fuera "
                           "del core)")
    return expected


def _decode_decision(position: int, record: object, forum_id: str) -> AssimilationDecision:
    where = f"decisión {position} del corpus"
    if not isinstance(record, dict) or set(record) != _DECISION_KEYS:
        _invalid_candidate(f"{where}: claves inesperadas")
    receipt = _decode_receipt(record["receipt"], where)
    status = _enum_value(ReviewStatus, record["review_status"], f"{where}: review_status")
    payload = {key: record[key] for key in _DECISION_KEYS - {"evidence"}}
    if not isinstance(record["decision_id"], str):
        _invalid_candidate(f"{where}: decision_id inválido")
    evidence = _check_evidence(record["evidence"],
                               _evidence(forum_id, record["decision_id"], payload), where)
    return AssimilationDecision(record["decision_id"], record["candidate_id"],
                                record["candidate_version"], record["candidate_sha256"], status,
                                receipt, evidence)


def _decode_closure(record: object, forum_id: str) -> AssimilationClosure:
    where = "cierre del corpus"
    if not isinstance(record, dict) or set(record) != _CLOSURE_KEYS:
        _invalid_candidate(f"{where}: claves inesperadas")
    receipt = _decode_receipt(record["receipt"], where)
    payload = {key: record[key] for key in _CLOSURE_KEYS - {"evidence"}}
    evidence = _check_evidence(record["evidence"], _evidence(forum_id, CLOSURE_ID, payload), where)
    return AssimilationClosure(record["closure_id"], record["base_revision"],
                               record["snapshot_sha256"], receipt, evidence)


def _require_sha256(name: str, value: object) -> None:
    if not isinstance(value, str) or not _SHA256_HEX.fullmatch(value):
        _invalid_candidate(f"{name} debe ser un SHA-256 en minúsculas")


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class _SourceDeclaration:
    """One distinct (section, id, version, passage) declaration of the dossier."""

    section: DossierSection | None  # None for loose material
    source_id: str
    source_version: str
    declared_passage: str | None
    literal_text: str
    source_sha256: str

    @property
    def candidate_eligible(self) -> bool:
        return self.section is not None

    @property
    def domain(self) -> AssimilationDomain | None:
        return _DOMAIN_BY_SECTION[self.section] if self.section is not None else None

    @property
    def key(self) -> tuple:
        return (self.section, self.source_id, self.source_version, self.declared_passage)


def _source_declarations(dossier: LoadedForumDossier) -> tuple[_SourceDeclaration, ...]:
    """Distinct source declarations in dossier order, loose material last (not citable)."""
    if not isinstance(dossier, LoadedForumDossier):
        _invalid_candidate("se necesita un expediente cargado")
    pairs = [(section.spec.section, loaded) for section in dossier.sections
             for loaded in section.sources]
    pairs += [(None, material.source) for material in dossier.loose_material]
    seen: dict[tuple, _SourceDeclaration] = {}
    for section, loaded in pairs:
        declaration = _SourceDeclaration(section, loaded.spec.source_id, loaded.spec.version,
                                         loaded.spec.section_or_passage, loaded.literal_text,
                                         loaded.source_ref.sha256)
        seen.setdefault(declaration.key, declaration)
    return tuple(seen.values())


def _find_declaration(
    declarations: tuple[_SourceDeclaration, ...], section: DossierSection, source_id: str,
    source_version: str, declared_passage: str | None,
) -> _SourceDeclaration:
    key = (section, source_id, source_version, declared_passage)
    for declaration in declarations:
        if declaration.key == key:
            return declaration
    passage = "null" if declared_passage is None else json.dumps(declared_passage,
                                                                 ensure_ascii=False)
    _invalid_candidate(
        f"no hay ninguna fuente declarada en «{_HEADINGS[section]}» con id "
        f"{json.dumps(source_id, ensure_ascii=False)}, versión "
        f"{json.dumps(source_version, ensure_ascii=False)} y pasaje {passage}; consulta "
        "«assimilation source list»"
    )


def _resolve_input_citation(
    index: int, item: object, declarations: tuple[_SourceDeclaration, ...]
) -> CandidateCitation:
    where = f"cita {index}"
    allowed = _INPUT_CITATION_KEYS | {"occurrence"}
    if not isinstance(item, dict) or not _INPUT_CITATION_KEYS <= set(item) <= allowed:
        _invalid_candidate(f"{where}: debe tener exactamente dossier_section, source_id, "
                           "source_version, declared_passage, quote y, opcionalmente, occurrence")
    section = _enum_value(DossierSection, item["dossier_section"], f"{where}: dossier_section")
    for name in ("source_id", "source_version"):
        if not isinstance(item[name], str):
            _invalid_candidate(f"{where}: {name} debe ser texto")
    passage = item["declared_passage"]
    if passage is not None and not isinstance(passage, str):
        _invalid_candidate(f"{where}: declared_passage debe ser texto o null")
    quote_text = item["quote"]
    _require_content(f"{where}: quote", quote_text)
    occurrence = item.get("occurrence")
    if "occurrence" in item and (type(occurrence) is not int or occurrence < 1):
        _invalid_candidate(f"{where}: occurrence debe ser un entero desde 1")
    declaration = _find_declaration(declarations, section, item["source_id"],
                                    item["source_version"], passage)
    literal = declaration.literal_text
    starts = _all_occurrences(literal, quote_text)
    if not starts:
        _invalid_candidate(f"{where}: la cita no aparece literalmente en esa fuente (se compara "
                           "carácter a carácter, incluidos espacios y saltos de línea)")
    if occurrence is None and len(starts) > 1:
        _invalid_candidate(f"{where}: la cita aparece {len(starts)} veces "
                           f"({_positions(literal, starts)}); alarga la cita o indica "
                           "«occurrence» desde 1")
    if occurrence is not None and occurrence > len(starts):
        _invalid_candidate(f"{where}: occurrence {occurrence} no existe; la cita aparece "
                           f"{len(starts)} vez/veces ({_positions(literal, starts)})")
    start = starts[(occurrence or 1) - 1]
    return CandidateCitation(section, declaration.source_id, declaration.source_version,
                             declaration.source_sha256, declaration.declared_passage, start,
                             start + len(quote_text), quote_text)


def _all_occurrences(literal: str, quote_text: str) -> list[int]:
    """Every start position, overlapping matches included."""
    starts, position = [], literal.find(quote_text)
    while position != -1:
        starts.append(position)
        position = literal.find(quote_text, position + 1)
    return starts


def _positions(literal: str, starts: list[int]) -> str:
    def line_column(offset: int) -> str:
        line = literal.count("\n", 0, offset) + 1
        column = offset - (literal.rfind("\n", 0, offset) + 1) + 1
        return f"línea {line}, columna {column}"

    shown = "; ".join(line_column(s) for s in starts[:10])
    return shown if len(starts) <= 10 else f"{shown}; y {len(starts) - 10} más"


def _decode_record(
    position: int, record: object, declarations: tuple[_SourceDeclaration, ...]
) -> AssimilationCandidate:
    where = f"candidato {position} del corpus"
    if not isinstance(record, dict) or set(record) != _RECORD_KEYS:
        _invalid_candidate(f"{where}: claves inesperadas")
    citations_value = record["citations"]
    if not isinstance(citations_value, list):
        _invalid_candidate(f"{where}: citations debe ser una lista")
    citations = []
    for item in citations_value:
        if not isinstance(item, dict) or set(item) != _RECORD_CITATION_KEYS:
            _invalid_candidate(f"{where}: una cita tiene claves inesperadas")
        citation = CandidateCitation(
            _enum_value(DossierSection, item["dossier_section"], f"{where}: dossier_section"),
            item["source_id"], item["source_version"], item["source_sha256"],
            item["declared_passage"], item["start"], item["end"], item["quote"],
        )
        declaration = _find_declaration(declarations, citation.dossier_section, citation.source_id,
                                        citation.source_version, citation.declared_passage)
        if (declaration.source_sha256 != citation.source_sha256
                or declaration.literal_text[citation.start:citation.end] != citation.quote):
            _invalid_candidate(f"{where}: una cita ya no corresponde a su fuente")
        citations.append(citation)
    if record["review_status"] != ReviewStatus.PENDING_HUMAN_REVIEW.value:
        _invalid_candidate(f"{where}: estado de revisión inesperado")
    candidate = AssimilationCandidate(
        candidate_id=record["candidate_id"],
        version=record["version"],
        domain=_enum_value(AssimilationDomain, record["domain"], f"{where}: domain"),
        candidate_class=_enum_value(CandidateClass, record["class"], f"{where}: class"),
        text=record["text"],
        scope=record["scope"],
        citations=tuple(citations),
    )
    if candidate.candidate_sha256 != record["candidate_sha256"]:
        _invalid_candidate(f"{where}: se modificó fuera del core (hash distinto)")
    return candidate


def _candidate_record(candidate: AssimilationCandidate, *, include_hash: bool) -> dict:
    record = {
        "candidate_id": candidate.candidate_id,
        "citations": [
            {
                "declared_passage": c.declared_passage,
                "dossier_section": c.dossier_section.value,
                "end": c.end,
                "quote": c.quote,
                "source_id": c.source_id,
                "source_sha256": c.source_sha256,
                "source_version": c.source_version,
                "start": c.start,
            }
            for c in candidate.citations
        ],
        "class": candidate.candidate_class.value,
        "domain": candidate.domain.value,
        "review_status": candidate.review_status.value,
        "scope": candidate.scope,
        "text": candidate.text,
        "version": candidate.version,
    }
    if include_hash:
        record["candidate_sha256"] = candidate.candidate_sha256
    return record


def _semantic_payload(candidate: AssimilationCandidate) -> dict:
    record = _candidate_record(candidate, include_hash=False)
    del record["version"]
    return record


def _enum_value(enum: type[Enum], value: object, name: str):
    try:
        return enum(value)
    except (ValueError, TypeError):
        options = ", ".join(e.value for e in enum)
        _invalid_candidate(f"{name} debe ser uno de: {options}")


def _require_candidate_text(name: str, value: object) -> None:
    try:
        _check_text("candidato", name, value)
    except DossierError as exc:
        raise AssimilationError("INVALID_STATE", exc.reason) from exc


def _require_content(name: str, value: object) -> None:
    """Free text kept character by character: may span lines, must not be blank."""
    if not isinstance(value, str) or not value.strip():
        _invalid_candidate(f"«{name}» debe ser un texto no vacío")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        _invalid_candidate(f"«{name}» contiene caracteres que no se pueden guardar en UTF-8")


def _invalid_candidate(reason: str) -> None:
    raise AssimilationError("INVALID_STATE", reason)
