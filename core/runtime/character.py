"""Character operations on a forum instance: the person declares concept versions (4d1).

Importing a concept is a human action under barrier A: the exact text, its hash and size are
shown and the person types a phrase with a one-time code. That records explicit adoption by a
person; it does not prove who wrote the file, and a fake terminal or pseudo terminal bypasses it.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from pathlib import Path

from core.character.models import (
    CharacterError,
    CharacterState,
    ConceptImportResult,
    ConceptVersion,
    LoadedCharacter,
    check_character_id,
    check_concept_text,
    decode_character_state,
    encode_character_content,
    make_concept_version,
)
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
    character_id = existing.state.character_id
    state_path = existing.character_root / CHARACTER_STATE
    guard = _path_guard(existing.character_root)
    guard()
    with _corpus_lock(state_path, "este personaje", guard=guard):
        revision, content = load_state(state_path)
        state = decode_character_state(content, forum_id=instance.config.forum_id,
                                       revision=revision)
        if revision != existing.state_revision or state != existing.state:
            raise CharacterError("CONFLICT", "el personaje cambió mientras se confirmaba; no se ha "
                                             "guardado nada")
        new_state = CharacterState(character_id, (*state.concepts, concept))
        data = encode_state(encode_character_content(new_state), revision=revision + 1)
        guard()
        atomic_write_bytes(state_path, data)
    return ConceptImportResult(_reload(instance, character_id), concept, True)


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
