"""Character operations on a forum instance: human concepts (4d1) and agent proposals (4d2).

Importing a concept and deciding on a proposal are human actions under barrier A: the exact
texts, hashes and sizes are shown and the person types a phrase with a one-time code. That
records explicit adoption by a person; it does not prove who wrote the text, and a fake terminal
or pseudo terminal bypasses it. Adding a proposal is not a human action and changes nothing
until a person approves it; approving only composes the character design.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from dataclasses import replace
from pathlib import Path

from core.character.models import (
    CharacterError,
    CharacterProposal,
    CharacterState,
    ConceptImportResult,
    ConceptVersion,
    CorpusCandidateRef,
    EffectiveComposition,
    LoadedCharacter,
    ProposalAddResult,
    ProposalDecisionResult,
    ProposalStatus,
    ProposalView,
    check_character_id,
    check_concept_text,
    decode_character_state,
    encode_character_content,
    make_concept_version,
    make_proposal_decision,
)
from core.character.models import _check_free_text, _check_id, _check_sha256
from core.review.models import ReviewStatus
from core.runtime.assimilation import (
    AssimilationError,
    Terminal,
    _corpus_lock,
    _require_interactive,
    _require_unlocked,
    confirm_human_action,
)
from core.runtime.instance import (
    CHARACTER_STATE,
    CHARACTERS_DIR,
    InstanceError,
    LoadedInstance,
    get_approved_candidate,
    load_instance,
)
from core.runtime.persistence import (
    PersistenceError,
    atomic_write_bytes,
    encode_state,
    load_state,
)
from core.runtime.workspace import (
    WorkspaceError,
    _ConcurrentDestination,
    _contains,
    _destination_state,
    _identity,
    _is_link,
    _linked_component,
    _publish,
    _remove_staging,
)

_UTF8_BOM = b"\xef\xbb\xbf"
_PROPOSAL_INPUT_KEYS = frozenset({"base_composition_sha256", "citations", "proposal_id",
                                  "rationale", "text", "version"})
_CITATION_INPUT_KEYS = frozenset({"candidate_id", "version"})
_PROPOSAL_VERB = {ReviewStatus.APPROVED: "APROBAR", ReviewStatus.REJECTED: "RECHAZAR"}
_NOTICE = ("Esta decisión solo compone el diseño del personaje; no es aprobación de staff, "
           "aprendizaje, utilizabilidad, publicación ni canon.")


def import_concept(instance_root: Path, *, expected_core_root: Path, character_id: str,
                   version: int, input_path: Path, terminal: Terminal) -> ConceptImportResult:
    """Declare `input_path` as version `version` of the person's concept for `character_id`."""
    try:
        return _import_concept(Path(instance_root), Path(expected_core_root), character_id,
                               version, Path(input_path), terminal)
    except (AssimilationError, InstanceError, WorkspaceError, PersistenceError) as exc:
        raise CharacterError(exc.code, exc.reason) from exc
    except OSError as exc:
        raise CharacterError("IO", f"error de disco al importar el concepto: {exc}") from exc


def list_concepts(instance: LoadedInstance, *, character_id: str) -> tuple[ConceptVersion, ...]:
    return _character(instance, character_id).state.concepts


def get_concept(instance: LoadedInstance, *, character_id: str, version: int) -> ConceptVersion:
    for concept in list_concepts(instance, character_id=character_id):
        if concept.version == version:
            return concept
    raise CharacterError("INVALID_STATE", f"el personaje «{character_id}» no tiene la versión "
                                          f"{version} del concepto")


def add_proposal(instance_root: Path, *, expected_core_root: Path,
                 character_id: str, value: object) -> ProposalAddResult:
    """Register a complete alternative composition written by the agent. Not a human action."""
    return _wrap("añadir la propuesta", _add_proposal, Path(instance_root),
                 Path(expected_core_root), character_id, value)


def list_proposals(instance: LoadedInstance, *, character_id: str) -> tuple[ProposalView, ...]:
    """Every proposal in insertion order, with its derived status."""
    return _character(instance, character_id).state.replay.views


def get_proposal(instance: LoadedInstance, *, character_id: str,
                 proposal_id: str, version: int) -> ProposalView:
    view = _character(instance, character_id).state.view(proposal_id, version)
    if view is None:
        raise CharacterError("INVALID_STATE", f"«{character_id}» no tiene la propuesta "
                                              f"{proposal_id} v{version}")
    return view


def get_effective_composition(instance: LoadedInstance, *,
                              character_id: str) -> EffectiveComposition:
    return _character(instance, character_id).state.replay.effective


def record_proposal_decision(instance_root: Path, *, expected_core_root: Path,
                             character_id: str, proposal_id: str, version: int,
                             review_status: ReviewStatus,
                             terminal: Terminal) -> ProposalDecisionResult:
    """Record APPROVED/REJECTED for one exact proposal version after the exact phrase.

    Barrier A blocks the automated command path but does not authenticate a person: a fake
    terminal or pseudo terminal bypasses it.
    """
    return _wrap("decidir sobre la propuesta", _record_proposal_decision, Path(instance_root),
                 Path(expected_core_root), character_id, proposal_id, version, review_status,
                 terminal)


def citation_lines(instance: LoadedInstance, proposal: CharacterProposal) -> tuple[str, ...]:
    """`Citas aprobadas (K):` and one resolved line per citation, in the author's order."""
    lines = [f"Citas aprobadas ({len(proposal.citations)}):"]
    for index, ref in enumerate(proposal.citations, start=1):
        candidate = _resolve(instance, ref.candidate_id, ref.version)
        line = (f"Cita {index}: {candidate.candidate_id} v{candidate.version} | "
                f"{candidate.candidate_class.value} | {candidate.domain.value} | APPROVED | "
                f"sha256={candidate.candidate_sha256}")
        lines.append(f"{line} | REQUIERE CONFIRMACIÓN" if candidate.requires_confirmation
                     else line)
    return tuple(lines)


def proposal_blocks(view: ProposalView) -> str:
    """Rationale, cited base and proposed text, each complete between its header and footer."""
    return (_block("Motivo exacto (hasta «Fin del motivo.»):", view.proposal.rationale,
                   "Fin del motivo.")
            + _block("BASE CITADA — texto exacto (hasta «Fin de la base.»):", view.base.text,
                     "Fin de la base.")
            + _block("PROPUESTA — texto completo que se aprueba/rechaza (hasta «Fin de la "
                     "propuesta.»):", view.proposal.text, "Fin de la propuesta."))


def find_character(instance: LoadedInstance, character_id: str) -> LoadedCharacter | None:
    for character in instance.characters:
        if character.state.character_id == character_id:
            return character
    return None


def _character(instance: LoadedInstance, character_id: str) -> LoadedCharacter:
    character = find_character(instance, character_id)
    if character is None:
        raise CharacterError("INVALID_STATE", f"no existe el personaje «{character_id}» en esta "
                                              "instancia")
    return character


# --- Import -----------------------------------------------------------------------------------


def _import_concept(instance_root: Path, core_root: Path, character_id: str, version: int,
                    input_path: Path, terminal: Terminal) -> ConceptImportResult:
    _require_interactive(terminal)
    check_character_id(character_id)
    if type(version) is not int or version < 1:
        raise CharacterError("INVALID_STATE", "la versión del concepto debe ser un entero positivo")
    instance = load_instance(instance_root, expected_core_root=core_root)
    raw, text = _read_input(input_path, instance.instance_root, core_root)
    existing = find_character(instance, character_id)
    state_path = instance.instance_root / CHARACTERS_DIR / character_id / CHARACTER_STATE

    if existing is not None:
        concepts = existing.state.concepts
        if version <= len(concepts):
            if concepts[version - 1].text == text:
                return ConceptImportResult(existing, concepts[version - 1], False)
            raise CharacterError("CONFLICT", f"la versión {version} del concepto de «{character_id}» "
                                             "ya existe con otro texto; usa la versión "
                                             f"{len(concepts) + 1}")
        if version != len(concepts) + 1:
            raise CharacterError("CONFLICT", f"la siguiente versión del concepto de «{character_id}» "
                                             f"es la {len(concepts) + 1}, no la {version}")
        if concepts[-1].text == text:
            raise CharacterError("CONFLICT", "el texto es idéntico a la versión vigente; no hay nada "
                                             "que importar")
        _require_unlocked(state_path, "este personaje")
    elif version != 1:
        raise CharacterError("CONFLICT", f"«{character_id}» todavía no existe: su primer concepto es "
                                         "la versión 1")

    receipt = confirm_human_action(terminal, phrase_prefix=f"DECLARAR-CONCEPTO {character_id} "
                                                           f"v{version}",
                                   prompt=_prompt(character_id, version, text))
    concept = make_concept_version(forum_id=instance.config.forum_id, character_id=character_id,
                                   version=version, text=text, receipt=receipt)

    # Second read after the human answered: nothing may have changed meanwhile.
    again = load_instance(instance_root, expected_core_root=core_root)
    raw_again, _ = _read_input(input_path, again.instance_root, core_root)
    current = find_character(again, character_id)
    if raw_again != raw or (current is None) != (existing is None) or (
        current is not None and current.state_revision != existing.state_revision
    ):
        raise CharacterError("CONFLICT", "la instancia o el archivo cambiaron mientras se "
                                         "confirmaba; no se ha guardado nada")
    if existing is None:
        return _create_character(again, character_id, concept)
    return _append_concept(again, existing, concept)


def _create_character(instance: LoadedInstance, character_id: str,
                      concept: ConceptVersion) -> ConceptImportResult:
    """Publish `characters/<id>/` atomically with the first concept."""
    state = CharacterState(character_id, (concept,))
    data = encode_state(encode_character_content(state), revision=1)
    folder = instance.instance_root / CHARACTERS_DIR
    linked = _linked_component(folder)
    if linked is not None:
        raise CharacterError("UNSAFE_DESTINATION", f"{linked} es un enlace simbólico o una "
                                                   "junction")
    folder.mkdir(exist_ok=True)
    if _is_link(folder) or not folder.is_dir():
        raise CharacterError("UNSAFE_DESTINATION", f"{folder} no es una carpeta normal")
    target = folder / character_id
    initial = _destination_state(target)
    if initial is not None:
        raise CharacterError("CONFLICT", f"{target} ya existe")
    staging = folder / f".{character_id}.staging-{secrets.token_hex(8)}"
    staging.mkdir()
    concurrent = None
    try:
        with open(staging / CHARACTER_STATE, "xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        _check_staged(staging, instance.config.forum_id, state)
        try:
            _publish(staging, target, initial)
        except _ConcurrentDestination as race:
            concurrent = race
    except BaseException as exc:
        leftover = _remove_staging(staging)
        if leftover is None or not isinstance(exc, (CharacterError, WorkspaceError, OSError)):
            raise
        code = exc.code if isinstance(exc, (CharacterError, WorkspaceError)) else "IO"
        reason = exc.reason if isinstance(exc, (CharacterError, WorkspaceError)) else str(exc)
        raise CharacterError(code, f"{reason}; además no se pudo borrar {leftover}: bórrala a "
                                   "mano") from exc
    if concurrent is not None:
        leftover = _remove_staging(staging)
        winner = target / CHARACTER_STATE
        identical = winner.is_file() and not _is_link(winner) and winner.read_bytes() == data
        if leftover is not None:
            raise CharacterError("IO", f"otro proceso creó a la vez el personaje en {target}, pero "
                                       f"no se pudo borrar {leftover}: bórrala a mano"
                                 ) from concurrent.error
        if not identical:
            raise CharacterError("CONFLICT", f"otro proceso creó a la vez «{character_id}» con otro "
                                             "contenido; no se ha tocado")
        return ConceptImportResult(_reload(instance, character_id), concept, False)
    return ConceptImportResult(_reload(instance, character_id), concept, True)


def _append_concept(instance: LoadedInstance, existing: LoadedCharacter,
                    concept: ConceptVersion) -> ConceptImportResult:
    """The new concept is the next event; proposals and decisions are kept untouched."""

    def build(again: LoadedInstance, current: LoadedCharacter) -> CharacterState:
        return replace(current.state, concepts=(*current.state.concepts, concept))

    return ConceptImportResult(_write_event(instance, existing, build), concept, True)


def _path_guard(character_root: Path):
    """A check that the character folder is still the same plain folder, with no link on the way.

    It runs before taking the lock, right after taking it and right before writing; the remaining
    window between the last check and the atomic replace cannot be closed without handle-relative
    file APIs, which the standard library does not offer on Windows.
    """
    identity = _folder_identity(character_root)

    def guard() -> None:
        linked = _linked_component(character_root / CHARACTER_STATE)
        if linked is not None:
            raise CharacterError("UNSAFE_DESTINATION", f"{linked} es un enlace simbólico o una "
                                                       "junction; no se ha escrito nada")
        if _folder_identity(character_root) != identity:
            raise CharacterError("CONFLICT", f"{character_root} fue sustituida mientras se "
                                             "guardaba; no se ha escrito nada")

    return guard


def _folder_identity(folder: Path) -> tuple[int, int]:
    try:
        info = os.lstat(folder)
    except OSError as exc:
        raise CharacterError("CONFLICT", f"{folder} ya no está disponible") from exc
    return (info.st_dev, info.st_ino)


def _check_staged(staging: Path, forum_id: str, expected: CharacterState) -> None:
    revision, content = load_state(staging / CHARACTER_STATE)
    if revision != 1 or decode_character_state(content, forum_id=forum_id,
                                               revision=revision) != expected:
        raise CharacterError("INVALID_STATE", "el estado preparado no se pudo verificar")


def _reload(instance: LoadedInstance, character_id: str) -> LoadedCharacter:
    reloaded = load_instance(instance.instance_root, expected_core_root=instance.config.core_root)
    return _character(reloaded, character_id)


def _read_input(input_path: Path, instance_root: Path, core_root: Path) -> tuple[bytes, str]:
    """A regular file outside the checkout and the instance, UTF-8 without BOM."""
    path = Path(input_path).absolute()
    linked = _linked_component(path)
    if linked is not None:
        raise CharacterError("INVALID_STATE", f"{linked} es un enlace simbólico o una junction; "
                                              "usa la ruta real del archivo")
    if not path.is_file():
        raise CharacterError("INVALID_STATE", f"{path} no existe o no es un archivo")
    real = _identity(path)
    for name, root in (("el checkout del core", core_root), ("la instancia", instance_root)):
        if _contains(_identity(root), real):
            raise CharacterError("INVALID_STATE", f"el archivo del concepto no puede estar dentro de "
                                                  f"{name}; guárdalo fuera")
    raw = path.read_bytes()
    if raw.startswith(_UTF8_BOM):
        raise CharacterError("INVALID_STATE", "el concepto empieza con BOM; guárdalo como UTF-8 "
                                              "sin BOM")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CharacterError("INVALID_STATE", "el archivo del concepto no es UTF-8 válido") from exc
    return raw, check_concept_text(text)


def _prompt(character_id: str, version: int, text: str) -> str:
    data = text.encode("utf-8")
    shown = text if text.endswith("\n") else text + "\n"
    return ("DECLARACIÓN HUMANA DE AUTORÍA\n"
            f"Personaje: {character_id}\n"
            f"Versión: {version}\n"
            f"SHA-256: {hashlib.sha256(data).hexdigest()}\n"
            f"Bytes UTF-8: {len(data)}\n"
            f"Termina en LF: {'SÍ' if text.endswith(chr(10)) else 'NO'}\n"
            "Concepto exacto (hasta «Fin del concepto.»):\n"
            f"{shown}"
            "Fin del concepto.\n"
            "Declara que este texto es el concepto que tú aportas; no una propuesta del agente.\n")


# --- Proposals --------------------------------------------------------------------------------


def _wrap(action: str, function, *args):
    try:
        return function(*args)
    except (AssimilationError, InstanceError, WorkspaceError, PersistenceError) as exc:
        raise CharacterError(exc.code, exc.reason) from exc
    except OSError as exc:
        raise CharacterError("IO", f"error de disco al {action}: {exc}") from exc


def _add_proposal(instance_root: Path, core_root: Path, character_id: str,
                  value: object) -> ProposalAddResult:
    check_character_id(character_id)
    instance = load_instance(instance_root, expected_core_root=core_root)
    character = _character(instance, character_id)
    proposal_id, version, base, text, rationale, wanted = _parse_proposal_input(value)
    citations = _resolve_citations(instance, wanted)
    proposal = _new_proposal(character, proposal_id, version, base, text, rationale, citations)
    if isinstance(proposal, ProposalAddResult):
        return proposal

    def build(again: LoadedInstance, current: LoadedCharacter) -> CharacterState:
        if _resolve_citations(again, wanted) != citations:
            raise CharacterError("CONFLICT", "las citas ya no resuelven igual; no se ha guardado "
                                             "nada")
        return replace(current.state, proposals=(*current.state.proposals, proposal))

    reloaded = _write_event(instance, character, build)
    return ProposalAddResult(reloaded, proposal, True)


def _new_proposal(character: LoadedCharacter, proposal_id: str, version: int, base: str,
                  text: str, rationale: str, citations: tuple[CorpusCandidateRef, ...]
                  ) -> CharacterProposal | ProposalAddResult:
    """The proposal to add, or the existing identical one (idempotent retry)."""
    state = character.state
    semantic = (base, text, rationale, citations)
    existing = state.view(proposal_id, version)
    if existing is not None:
        old = existing.proposal
        if (old.base_composition_sha256, old.text, old.rationale, old.citations) == semantic:
            return ProposalAddResult(character, old, False)
        raise CharacterError("CONFLICT", f"{proposal_id} v{version} ya existe con otro contenido; "
                                         "crea la versión siguiente")
    previous = state.current_proposal(proposal_id)
    expected = 1 if previous is None else previous.version + 1
    if version != expected:
        raise CharacterError("CONFLICT", f"la siguiente versión de {proposal_id} es la {expected}, "
                                         f"no la {version}")
    effective = state.replay.effective
    if base != effective.composition_sha256:
        raise CharacterError("CONFLICT", "base_composition_sha256 no es la composición efectiva "
                                         "vigente; consulta «character effective show»")
    proposal = CharacterProposal(state.character_id, proposal_id, version, state.revision + 1,
                                 effective.concept, base, text, rationale, citations)
    if previous is not None and (previous.concept, previous.base_composition_sha256,
                                 previous.text, previous.rationale, previous.citations) == (
        proposal.concept, *semantic
    ):
        raise CharacterError("CONFLICT", f"{proposal_id} v{version} repite la versión anterior")
    return proposal


def _record_proposal_decision(instance_root: Path, core_root: Path, character_id: str,
                              proposal_id: str, version: int, review_status: ReviewStatus,
                              terminal: Terminal) -> ProposalDecisionResult:
    _require_interactive(terminal)
    if not isinstance(review_status, ReviewStatus) or review_status not in _PROPOSAL_VERB:
        raise CharacterError("INVALID_STATE", "la decisión debe ser APPROVED o REJECTED")
    check_character_id(character_id)
    _check_id("proposal_id", proposal_id)
    if type(version) is not int or version < 1:
        raise CharacterError("INVALID_STATE", "la versión de la propuesta debe ser un entero "
                                              "positivo")
    instance = load_instance(instance_root, expected_core_root=core_root)
    character = _character(instance, character_id)
    view = get_proposal(instance, character_id=character_id, proposal_id=proposal_id,
                        version=version)
    state = character.state
    if view.decision is not None:
        if view.decision.review_status is review_status:
            return ProposalDecisionResult(character, view.decision, False,
                                          state.replay.effective)
        raise CharacterError("CONFLICT", f"{proposal_id} v{version} ya tiene la decisión "
                                         f"{view.decision.review_status.value}; para otra "
                                         "alternativa crea una versión nueva")
    if review_status is ReviewStatus.APPROVED and view.status is not ProposalStatus.PENDING:
        raise CharacterError("CONFLICT", f"{proposal_id} v{version} está {view.status.value}: solo "
                                         "se aprueba una propuesta pendiente sobre la composición "
                                         "efectiva vigente")
    state_path = character.character_root / CHARACTER_STATE
    _require_unlocked(state_path, "este personaje")
    verb = _PROPOSAL_VERB[review_status]
    receipt = confirm_human_action(
        terminal, phrase_prefix=f"{verb}-PROPUESTA {proposal_id} v{version}",
        prompt=_proposal_prompt(instance, character, view, verb))
    decision = make_proposal_decision(forum_id=instance.config.forum_id,
                                      character_id=character_id, proposal=view.proposal,
                                      decision_revision=state.revision + 1,
                                      review_status=review_status, receipt=receipt)

    def build(again: LoadedInstance, current: LoadedCharacter) -> CharacterState:
        return replace(current.state,
                       proposal_decisions=(*current.state.proposal_decisions, decision))

    reloaded = _write_event(instance, character, build)
    return ProposalDecisionResult(reloaded, decision, True, reloaded.state.replay.effective)


def _write_event(instance: LoadedInstance, character: LoadedCharacter, build) -> LoadedCharacter:
    """Append one event under the character lock; any change since `character` is a CONFLICT."""
    character_id = character.state.character_id
    state_path = character.character_root / CHARACTER_STATE
    guard = _path_guard(character.character_root)
    guard()
    with _corpus_lock(state_path, "este personaje", guard=guard):
        again = load_instance(instance.instance_root, expected_core_root=instance.config.core_root)
        current = find_character(again, character_id)
        if (current is None or current.state_revision != character.state_revision
                or current.state != character.state):
            raise CharacterError("CONFLICT", "el personaje cambió mientras se confirmaba; no se ha "
                                             "guardado nada")
        new_state = build(again, current)
        if new_state.revision != current.state_revision + 1:
            raise CharacterError("INVALID_STATE", "un cambio debe añadir exactamente un evento")
        data = encode_state(encode_character_content(new_state), revision=new_state.revision)
        guard()
        atomic_write_bytes(state_path, data)
    return _reload(instance, character_id)


def _parse_proposal_input(value: object):
    if not isinstance(value, dict) or set(value) != _PROPOSAL_INPUT_KEYS:
        raise CharacterError("INVALID_STATE", "la propuesta debe tener exactamente las claves "
                                              + ", ".join(sorted(_PROPOSAL_INPUT_KEYS)))
    proposal_id = _check_id("proposal_id", value["proposal_id"])
    version = value["version"]
    if type(version) is not int or version < 1:
        raise CharacterError("INVALID_STATE", "version debe ser un entero positivo")
    _check_sha256("base_composition_sha256", value["base_composition_sha256"])
    _check_free_text("el texto de la propuesta", value["text"])
    _check_free_text("el motivo de la propuesta", value["rationale"])
    citations = value["citations"]
    if not isinstance(citations, list) or not citations:
        raise CharacterError("INVALID_STATE", "citations debe ser una lista no vacía")
    wanted = []
    for item in citations:
        if not isinstance(item, dict) or set(item) != _CITATION_INPUT_KEYS:
            raise CharacterError("INVALID_STATE", "cada cita tiene exactamente candidate_id y "
                                                  "version")
        _check_id("candidate_id", item["candidate_id"])
        if type(item["version"]) is not int or item["version"] < 1:
            raise CharacterError("INVALID_STATE", "la versión de cada cita debe ser un entero "
                                                  "positivo")
        wanted.append((item["candidate_id"], item["version"]))
    return (proposal_id, version, value["base_composition_sha256"], value["text"],
            value["rationale"], tuple(wanted))


def _resolve_citations(instance: LoadedInstance,
                       wanted: tuple[tuple[str, int], ...]) -> tuple[CorpusCandidateRef, ...]:
    if len(set(wanted)) != len(wanted):
        raise CharacterError("INVALID_STATE", "la propuesta repite una cita")
    return tuple(CorpusCandidateRef(cid, version, _resolve(instance, cid, version).candidate_sha256)
                 for cid, version in wanted)


def _resolve(instance: LoadedInstance, candidate_id: str, version: int):
    try:
        return get_approved_candidate(instance, candidate_id=candidate_id,
                                      version=version).candidate
    except InstanceError as exc:
        raise CharacterError("INVALID_STATE", exc.reason) from exc


def _proposal_prompt(instance: LoadedInstance, character: LoadedCharacter, view: ProposalView,
                     verb: str) -> str:
    proposal = view.proposal
    effective = character.state.replay.effective
    current = "SÍ" if proposal.base_composition_sha256 == effective.composition_sha256 else "NO"
    lines = [
        "DECISIÓN HUMANA SOBRE PROPUESTA",
        f"Personaje: {character.state.character_id}",
        f"Propuesta: {proposal.proposal_id} v{proposal.version}",
        f"Estado antes de decidir: {view.status.value}",
        f"Decisión: {verb}",
        f"Concepto humano citado: v{proposal.concept.version}",
        f"Concepto SHA-256: {proposal.concept.concept_sha256}",
        f"Base vigente ahora: {current}",
        f"Base composición SHA-256: {proposal.base_composition_sha256}",
        f"Resultado composición SHA-256: {proposal.result_composition_sha256}",
        f"Propuesta SHA-256: {proposal.proposal_sha256}",
        f"Base bytes UTF-8: {view.base.utf8_size}",
        f"Propuesta bytes UTF-8: {proposal.utf8_size}",
        *citation_lines(instance, proposal),
    ]
    return "".join(f"{line}\n" for line in lines) + proposal_blocks(view) + _NOTICE + "\n"


def _block(header: str, text: str, footer: str) -> str:
    return f"{header}\n{text if text.endswith(chr(10)) else text + chr(10)}{footer}\n"
