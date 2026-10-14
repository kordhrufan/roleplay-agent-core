"""Forum instance: a self-contained folder generated from a closed assimilation workspace.

The instance holds an exact copy of the dossier and of the closed corpus snapshot, plus the
`AGENTS.md`/`CLAUDE.md` instructions for the forum agent. It only answers queries: nothing here
mutates the corpus, decides or publishes. It records a fingerprint of its source workspace, not
its path, and keeps working if the workspace is moved or deleted.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import string
from dataclasses import dataclass, replace
from pathlib import Path

from core.character.models import (
    CandidateResolver,
    CharacterError,
    LoadedCharacter,
    check_character_id,
    decode_character_state,
)
from core.review.models import ReviewStatus
from core.runtime.assimilation import (
    AssimilationCandidate,
    AssimilationClosure,
    AssimilationDecision,
    AssimilationError,
    AssimilationState,
    ClosedCorpus,
    DossierError,
    LoadedForumDossier,
    decode_candidate_state,
    decode_closed_corpus,
    load_dossier,
)
from core.runtime.persistence import (
    PersistenceError,
    canonical_json_bytes,
    load_state,
    parse_strict_json,
)
from core.runtime.workspace import (
    CORPUS_STATE,
    DOSSIER_DIR,
    DOSSIER_PATH,
    WORKSPACE_FILE,
    ManagedFile,
    WorkspaceError,
    _check_managed_list,
    _checkout,
    _ConcurrentDestination,
    _contains,
    _destination_state,
    _identity,
    _is_link,
    _linked_component,
    _managed,
    _parse_managed_list,
    _publish,
    _remove_staging,
    _require_publish_support,
    _strip_device_prefix,
    _tree_bytes,
    dossier_descriptor,
    load_workspace,
)

INSTANCE_SCHEMA_VERSION = 1
INSTANCE_KIND = "forum-roleplay-instance"
INSTANCE_FILE = "instance.json"
INSTANCE_CORPUS = "corpus/state.json"
INSTANCE_INTEGRITY = "work/integrity.json"
AGENTS_FILE = "AGENTS.md"
CLAUDE_FILE = "CLAUDE.md"
CHARACTERS_DIR = "characters"
CHARACTER_STATE = "state.json"
CHARACTER_LOCK = "state.json.lock"

_TEMPLATES = Path(__file__).resolve().parent / "templates"
INSTANCE_TEMPLATE = _TEMPLATES / "instance.template.json"
POLICY_TEMPLATE = _TEMPLATES / "instance-policy.template.md"
AGENTS_TEMPLATE = _TEMPLATES / "AGENTS.template.md"
CLAUDE_TEMPLATE = _TEMPLATES / "CLAUDE.template.md"
COMMON_BEGIN = "<!-- BEGIN ROLEPLAY-AGENT-CORE:COMMON -->\n"
COMMON_END = "<!-- END ROLEPLAY-AGENT-CORE:COMMON -->"

_CODES = frozenset({"INVALID_STATE", "CONFLICT", "UNSAFE_DESTINATION", "IO"})
_ROOT_FILES = frozenset({AGENTS_FILE, CLAUDE_FILE, INSTANCE_FILE})
_ROOT_DIRS = frozenset({"dossier", "corpus", "work"})  # static, covered by integrity
_MUTABLE_ROOT_DIRS = frozenset({CHARACTERS_DIR})  # self-hashed states, validated one by one
_CONFIG_KEYS = frozenset({"core_root", "corpus", "display_name", "dossier", "dossier_version",
                          "forum_id", "instance_root", "kind", "packages", "schema_version",
                          "source_workspace"})
_CORPUS_KEYS = frozenset({"path", "revision", "sha256", "size", "snapshot_sha256"})
_INTEGRITY_KEYS = frozenset({"algorithm", "files", "schema_version"})
_FORUM_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_CONTROL = re.compile(r"[\x00-\x1f]")
_LOCK = CORPUS_STATE + ".lock"


class InstanceError(ValueError):
    """`code` is INVALID_STATE, CONFLICT, UNSAFE_DESTINATION or IO."""

    def __init__(self, code: str, reason: str):
        if code not in _CODES:
            raise ValueError(f"unknown instance error code {code!r}")
        self.code = code
        self.reason = reason
        super().__init__(f"{code}: {reason}")


@dataclass(frozen=True, slots=True)
class InstanceCorpus:
    path: str
    revision: int
    sha256: str
    size: int
    snapshot_sha256: str

    def __post_init__(self) -> None:
        if self.path != INSTANCE_CORPUS:
            _invalid(f"corpus.path debe ser {INSTANCE_CORPUS}")
        for name in ("revision", "size"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                _invalid(f"corpus.{name} debe ser un entero no negativo")
        for name in ("sha256", "snapshot_sha256"):
            _require_sha256(f"corpus.{name}", getattr(self, name))


@dataclass(frozen=True, slots=True)
class SourceWorkspace:
    """A fingerprint of the source workspace; neither a link to it nor an authentication."""

    workspace_json_sha256: str

    def __post_init__(self) -> None:
        _require_sha256("source_workspace.workspace_json_sha256", self.workspace_json_sha256)


@dataclass(frozen=True, slots=True)
class InstanceConfig:
    schema_version: int
    forum_id: str
    display_name: str
    dossier_version: str
    core_root: Path
    instance_root: Path
    dossier_path: str
    dossier_files: tuple[ManagedFile, ...]
    corpus: InstanceCorpus
    source_workspace: SourceWorkspace
    packages: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != INSTANCE_SCHEMA_VERSION:
            _invalid(f"schema_version debe ser {INSTANCE_SCHEMA_VERSION}")
        if not isinstance(self.forum_id, str) or not _FORUM_ID.fullmatch(self.forum_id):
            _invalid("forum_id inválido")
        for name in ("display_name", "dossier_version"):
            value = getattr(self, name)
            if (not isinstance(value, str) or not value or value != value.strip()
                    or _CONTROL.search(value)):
                _invalid(f"{name} inválido")
        for name in ("core_root", "instance_root"):
            value = getattr(self, name)
            if not isinstance(value, Path) or not value.is_absolute():
                _invalid(f"{name} debe ser una ruta absoluta")
        if self.dossier_path != DOSSIER_PATH:
            _invalid(f"dossier.path debe ser {DOSSIER_PATH}")
        try:
            _check_managed_list(self.dossier_files)
        except WorkspaceError as exc:
            _invalid(exc.reason)
        paths = [f.path for f in self.dossier_files]
        if DOSSIER_PATH not in paths or not all(p.startswith(f"{DOSSIER_DIR}/") for p in paths):
            _invalid("dossier.files debe incluir el expediente y solo rutas bajo dossier/")
        if not isinstance(self.corpus, InstanceCorpus):
            _invalid("corpus inválido")
        if not isinstance(self.source_workspace, SourceWorkspace):
            _invalid("source_workspace inválido")
        if self.packages != ():
            _invalid("packages debe estar vacío en esta versión")


@dataclass(frozen=True, slots=True)
class ApprovedCorpusEntry:
    candidate: AssimilationCandidate
    decision: AssimilationDecision

    def __post_init__(self) -> None:
        if not isinstance(self.candidate, AssimilationCandidate) or not isinstance(
            self.decision, AssimilationDecision
        ):
            _invalid("entrada de corpus inválida")
        if (self.decision.candidate_key != self.candidate.key
                or self.decision.candidate_sha256 != self.candidate.candidate_sha256):
            _invalid("la decisión no corresponde al candidato")
        if self.decision.review_status is not ReviewStatus.APPROVED:
            _invalid("solo las entradas APPROVED son utilizables")


@dataclass(frozen=True, slots=True)
class LoadedInstance:
    config: InstanceConfig
    instance_root: Path
    dossier: LoadedForumDossier
    corpus_revision: int
    candidates: tuple[AssimilationCandidate, ...]
    decisions: tuple[AssimilationDecision, ...]
    closure: AssimilationClosure
    characters: tuple[LoadedCharacter, ...]


@dataclass(frozen=True, slots=True)
class InstanceInitResult:
    instance: LoadedInstance
    created: bool


def create_instance(workspace_root: Path, *, output: Path, core_root: Path) -> InstanceInitResult:
    """Materialize a closed workspace as a new instance at `output`, or return the identical one."""
    try:
        return _create_instance(Path(workspace_root), output, core_root)
    except (WorkspaceError, PersistenceError, AssimilationError, CharacterError) as exc:
        raise InstanceError(exc.code, exc.reason) from exc
    except DossierError as exc:
        raise InstanceError("INVALID_STATE", str(exc)) from exc
    except OSError as exc:
        raise InstanceError("IO", f"error de disco al crear la instancia: {exc}") from exc


def load_instance(instance_root: Path, *, expected_core_root: Path | None = None) -> LoadedInstance:
    """Load and verify an instance. Any edit outside the core makes it fail closed."""
    root = _absolute(instance_root)
    try:
        return _load_instance(root, root, expected_core_root)
    except (WorkspaceError, PersistenceError, AssimilationError, CharacterError) as exc:
        raise InstanceError(exc.code, exc.reason) from exc
    except DossierError as exc:
        raise InstanceError("INVALID_STATE", f"el expediente copiado no carga: {exc}") from exc
    except OSError as exc:
        raise InstanceError("IO", f"error de disco al leer la instancia: {exc}") from exc


def approved_corpus(instance: LoadedInstance) -> tuple[ApprovedCorpusEntry, ...]:
    """Current versions with an APPROVED decision, in stable order. Nothing else is usable."""
    state = AssimilationState(instance.candidates, instance.decisions, instance.closure)
    entries = []
    for candidate in state.current_versions():
        decision = state.decision_for(candidate)
        if decision is not None and decision.review_status is ReviewStatus.APPROVED:
            entries.append(ApprovedCorpusEntry(candidate, decision))
    return tuple(entries)


def closed_corpus_of(instance: LoadedInstance) -> ClosedCorpus:
    """The instance's closed corpus as a snapshot chain (a v1 instance has one LEGACY_V1 link)."""
    try:
        revision, content = load_state(instance.instance_root.joinpath(*INSTANCE_CORPUS.split("/")))
        if revision != instance.corpus_revision:
            raise InstanceError("CONFLICT", "el corpus de la instancia cambió mientras se leía")
        return decode_closed_corpus(
            content, dossier=instance.dossier, revision=revision,
            descriptor=dossier_descriptor(instance.dossier, instance.config.dossier_files))
    except (AssimilationError, PersistenceError) as exc:
        raise InstanceError(exc.code, exc.reason) from exc


def get_approved_candidate(instance: LoadedInstance, *, candidate_id: str,
                           version: int) -> ApprovedCorpusEntry:
    """The exact current approved version; never falls back to another version."""
    for entry in approved_corpus(instance):
        if entry.candidate.key == (candidate_id, version):
            return entry
    raise InstanceError("INVALID_STATE", f"{candidate_id} v{version} no es una versión vigente "
                                         "aprobada del corpus; consulta «instance corpus list»")


# --- Creation ---------------------------------------------------------------------------------


def _create_instance(workspace_root: Path, output: Path, core_root: Path) -> InstanceInitResult:
    core_root = _checkout(core_root)
    first = _read_source(workspace_root, core_root)
    target = _absolute(output)
    _check_destination(target, core_root, workspace_root)
    initial = _destination_state(target)
    expected = _expected_files(first, target, core_root)
    if target.exists() and any(target.iterdir()):
        return InstanceInitResult(_existing(target, expected, core_root), False)
    return _materialize(target, expected, workspace_root, core_root, first, initial)


@dataclass(frozen=True, slots=True)
class _Source:
    workspace_json: bytes
    dossier_files: dict[str, bytes]
    corpus: bytes
    loaded_dossier: LoadedForumDossier
    corpus_revision: int
    state: AssimilationState


def _read_source(workspace_root: Path, core_root: Path) -> _Source:
    workspace = load_workspace(workspace_root, expected_core_root=core_root)
    root = workspace.workspace_root
    if workspace.expansion is not None:
        _invalid("ese es un workspace de ampliación: aplícalo a su instancia con «instance "
                 "update», no crea una instancia nueva")
    if workspace.closure is None:
        _invalid("la asimilación del workspace no está cerrada; ciérrala antes de crear la "
                 "instancia (`assimilation close`)")
    if os.path.lexists(root.joinpath(*_LOCK.split("/"))):
        raise InstanceError("CONFLICT", f"el corpus del workspace está bloqueado "
                                        f"({root.joinpath(*_LOCK.split('/'))})")
    dossier_files = {f.path: _read_regular(root, f.path) for f in workspace.config.dossier_files}
    source = _Source(
        workspace_json=_read_regular(root, WORKSPACE_FILE),
        dossier_files=dossier_files,
        corpus=_read_regular(root, CORPUS_STATE),
        loaded_dossier=workspace.dossier,
        corpus_revision=workspace.corpus_revision,
        state=AssimilationState(workspace.candidates, workspace.decisions, workspace.closure),
    )
    for managed in workspace.config.dossier_files:
        data = dossier_files[managed.path]
        if _managed(managed.path, data) != managed:
            raise InstanceError("CONFLICT", f"{managed.path} cambió mientras se leía el workspace")
    revision, _ = load_state(root.joinpath(*CORPUS_STATE.split("/")))
    if revision != workspace.corpus_revision:
        raise InstanceError("CONFLICT", "el corpus cambió mientras se leía el workspace")
    return source


def _check_destination(target: Path, core_root: Path, workspace_root: Path) -> None:
    _require_publish_support()
    if _CONTROL.search(str(target)):
        _unsafe("la ruta de la instancia contiene caracteres de control")
    linked = _linked_component(target)
    if linked is not None:
        _unsafe(f"{linked} es un enlace simbólico o una junction; usa la ruta real")
    if not target.parent.is_dir():
        _unsafe(f"la carpeta padre {target.parent} no existe; créala antes")
    real = _identity(target)
    for name, other in (("el checkout del core", core_root), ("el workspace", workspace_root)):
        other_real = _identity(other)
        if _contains(other_real, real) or _contains(real, other_real):
            _unsafe(f"la instancia no puede coincidir ni solaparse con {name}")
    if target.exists() and not target.is_dir():
        _unsafe(f"{target} existe y no es una carpeta")


def _expected_files(source: _Source, target: Path, core_root: Path) -> dict[str, bytes]:
    instance_root = _canonical(target)
    core = _canonical(core_root)
    meta = source.loaded_dossier.dossier
    dossier_files = sorted((_managed(p, d) for p, d in source.dossier_files.items()),
                           key=lambda f: f.path)
    rendered = string.Template(INSTANCE_TEMPLATE.read_text(encoding="utf-8")).substitute(
        core_root_json=json.dumps(str(core), ensure_ascii=False),
        corpus_revision=source.corpus_revision,
        corpus_sha256_json=json.dumps(_sha256(source.corpus)),
        corpus_size=len(source.corpus),
        snapshot_sha256_json=json.dumps(source.state.closure.snapshot_sha256),
        display_name_json=json.dumps(meta.display_name, ensure_ascii=False),
        dossier_files_json=json.dumps([f.as_json() for f in dossier_files], ensure_ascii=False),
        dossier_version_json=json.dumps(meta.dossier_version, ensure_ascii=False),
        forum_id_json=json.dumps(meta.forum_id, ensure_ascii=False),
        instance_root_json=json.dumps(str(instance_root), ensure_ascii=False),
        workspace_json_sha256_json=json.dumps(_sha256(source.workspace_json)),
    )
    config_data = parse_strict_json(rendered.encode("utf-8"), INSTANCE_TEMPLATE.as_posix())
    config = _parse_config(config_data)
    files: dict[str, bytes] = dict(source.dossier_files)
    files[INSTANCE_CORPUS] = source.corpus
    files[INSTANCE_FILE] = canonical_json_bytes(config_data, pretty=True)
    files[AGENTS_FILE] = render_instructions(AGENTS_TEMPLATE, config)
    files[CLAUDE_FILE] = render_instructions(CLAUDE_TEMPLATE, config)
    covered = sorted((_managed(path, data) for path, data in files.items()), key=lambda f: f.path)
    integrity = {"algorithm": "sha256", "files": [f.as_json() for f in covered],
                 "schema_version": INSTANCE_SCHEMA_VERSION}
    files[INSTANCE_INTEGRITY] = canonical_json_bytes(integrity, pretty=True)
    return files


def render_instructions(template: Path, config: InstanceConfig) -> bytes:
    """Render AGENTS.md or CLAUDE.md for an instance; the common block is the policy verbatim."""
    text = string.Template(template.read_text(encoding="utf-8")).substitute(
        display_name=config.display_name,
        forum_id=config.forum_id,
        common_policy=POLICY_TEMPLATE.read_text(encoding="utf-8"),
        core_root_ps=_powershell(config.core_root),
        instance_root_ps=_powershell(config.instance_root),
    )
    return text.encode("utf-8")


def _existing(target: Path, expected: dict[str, bytes], core_root: Path) -> LoadedInstance:
    if _tree_bytes(target) != expected:
        raise InstanceError("CONFLICT", f"{target} ya contiene otro contenido; elige una "
                                        "carpeta vacía o inexistente")
    return load_instance(target, expected_core_root=core_root)


def _materialize(target: Path, expected: dict[str, bytes], workspace_root: Path, core_root: Path,
                 first: _Source, initial: tuple[int, int, int] | None) -> InstanceInitResult:
    staging = target.parent / f".{target.name}.staging-{secrets.token_hex(8)}"
    staging.mkdir()
    concurrent: tuple[LoadedInstance, OSError] | None = None
    try:
        for relative, data in expected.items():
            path = staging.joinpath(*relative.split("/"))
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        _load_instance(staging, target, core_root)
        second = _read_source(workspace_root, core_root)
        if (second.workspace_json, second.dossier_files, second.corpus) != (
            first.workspace_json, first.dossier_files, first.corpus
        ):
            raise InstanceError("CONFLICT", "el workspace cambió mientras se creaba la instancia; "
                                            "repite")
        try:
            _publish(staging, target, initial)
        except _ConcurrentDestination as race:
            # Another actor created the destination meanwhile: never overwrite it.
            concurrent = (_existing(target, expected, core_root), race.error)
    except BaseException as exc:
        leftover = _remove_staging(staging)
        if leftover is None or not isinstance(exc, (InstanceError, WorkspaceError, OSError)):
            raise
        code = exc.code if isinstance(exc, (InstanceError, WorkspaceError)) else "IO"
        reason = exc.reason if isinstance(exc, (InstanceError, WorkspaceError)) else str(exc)
        raise InstanceError(code, f"{reason}; además no se pudo borrar {leftover}: bórrala a "
                                  "mano") from exc
    if concurrent is not None:
        loaded, replace_error = concurrent
        leftover = _remove_staging(staging)
        if leftover is not None:
            raise InstanceError("IO", f"otro proceso creó a la vez la misma instancia en {target}, "
                                      f"pero no se pudo borrar {leftover}: bórrala a mano"
                                ) from replace_error
        return InstanceInitResult(loaded, False)
    return InstanceInitResult(load_instance(target, expected_core_root=core_root), True)


# --- Loading ----------------------------------------------------------------------------------


def _load_instance(physical: Path, logical_root: Path,
                   expected_core_root: Path | None) -> LoadedInstance:
    """Verify the instance stored at `physical` as if it lived at `logical_root`."""
    linked = _linked_component(physical)
    if linked is not None:
        _invalid(f"{linked} es un enlace simbólico o una junction; usa la ruta real")
    if not physical.is_dir():
        _invalid(f"{physical} no es una carpeta de instancia")
    entries = {p.name: p for p in physical.iterdir()}
    for name, path in entries.items():
        if _is_link(path):
            _invalid(f"{name} es un enlace simbólico o una junction")
        expected_kind = (name in _ROOT_FILES and path.is_file()
                         or name in _ROOT_DIRS | _MUTABLE_ROOT_DIRS and path.is_dir())
        if not expected_kind:
            _invalid(f"{name} no forma parte de la instancia")
    config_raw = _read_regular(physical, INSTANCE_FILE)
    config_data = parse_strict_json(config_raw, INSTANCE_FILE)
    if config_raw != canonical_json_bytes(config_data, pretty=True):
        _invalid(f"{INSTANCE_FILE} se modificó fuera del core (no está en forma canónica)")
    config = _parse_config(config_data)
    if _identity(config.instance_root) != _identity(logical_root):
        _invalid(f"la instancia se creó para {config.instance_root}; no se puede usar desde "
                 "otra ruta")
    if expected_core_root is not None and _identity(config.core_root) != _identity(expected_core_root):
        raise InstanceError("CONFLICT", f"la instancia pertenece al checkout {config.core_root}")

    integrity_raw = _read_regular(physical, INSTANCE_INTEGRITY)
    integrity_data = parse_strict_json(integrity_raw, INSTANCE_INTEGRITY)
    if integrity_raw != canonical_json_bytes(integrity_data, pretty=True):
        _invalid(f"{INSTANCE_INTEGRITY} se modificó fuera del core (no está en forma canónica)")
    if not isinstance(integrity_data, dict) or set(integrity_data) != _INTEGRITY_KEYS:
        _invalid(f"{INSTANCE_INTEGRITY} no tiene exactamente las claves esperadas")
    if (integrity_data["algorithm"] != "sha256" or type(integrity_data["schema_version"]) is not int
            or integrity_data["schema_version"] != INSTANCE_SCHEMA_VERSION):
        _invalid(f"{INSTANCE_INTEGRITY}: algoritmo o versión desconocidos")
    covered = _parse_managed_list(integrity_data["files"])
    agents_raw = _read_regular(physical, AGENTS_FILE)
    claude_raw = _read_regular(physical, CLAUDE_FILE)
    expected_cover = tuple(sorted(
        [_managed(AGENTS_FILE, agents_raw), _managed(CLAUDE_FILE, claude_raw),
         _managed(INSTANCE_FILE, config_raw), *config.dossier_files,
         ManagedFile(INSTANCE_CORPUS, config.corpus.sha256, config.corpus.size)],
        key=lambda f: f.path))
    if covered != expected_cover:
        _invalid(f"{INSTANCE_INTEGRITY} no corresponde a los archivos de la instancia")
    for managed in covered:
        if _managed(managed.path, _read_regular(physical, managed.path)) != managed:
            _invalid(f"{managed.path} se modificó fuera del core")
    listed = {f.path for f in covered} | {INSTANCE_INTEGRITY}
    allowed_dirs = {parent for path in listed for parent in _parents(path)}
    for directory in _ROOT_DIRS:
        for current, directories, files in os.walk(physical / directory, followlinks=False):
            here = Path(current)
            for name in directories + files:
                path = here / name
                relative = path.relative_to(physical).as_posix()
                if _is_link(path):
                    _invalid(f"{relative} es un enlace simbólico o una junction")
                if name in files and relative not in listed:
                    _invalid(f"{relative} no forma parte de la instancia")
                if name in directories and relative not in allowed_dirs:
                    _invalid(f"{relative}/ no forma parte de la instancia")

    dossier = load_dossier(physical / DOSSIER_DIR)
    meta = dossier.dossier
    if (meta.forum_id, meta.display_name, meta.dossier_version) != (
        config.forum_id, config.display_name, config.dossier_version
    ):
        _invalid("el expediente copiado no coincide con instance.json")
    revision, content = load_state(physical.joinpath(*INSTANCE_CORPUS.split("/")))
    if revision != config.corpus.revision:
        _invalid("la revisión del corpus no coincide con instance.json")
    state = decode_candidate_state(content, dossier=dossier, revision=revision)
    if state.closure is None or state.closure.snapshot_sha256 != config.corpus.snapshot_sha256:
        _invalid("el corpus de la instancia no es el snapshot cerrado declarado")
    for name, template, raw in ((AGENTS_FILE, AGENTS_TEMPLATE, agents_raw),
                                (CLAUDE_FILE, CLAUDE_TEMPLATE, claude_raw)):
        if render_instructions(template, config) != raw:
            _invalid(f"{name} no corresponde a su plantilla")
    provisional = LoadedInstance(config, logical_root, dossier, revision, state.candidates,
                                 state.decisions, state.closure, ())

    def resolve(candidate_id: str, version: int) -> AssimilationCandidate:
        return get_approved_candidate(provisional, candidate_id=candidate_id,
                                      version=version).candidate

    characters = _load_characters(physical, logical_root, config.forum_id, resolve)
    return replace(provisional, characters=characters)


def _load_characters(physical: Path, logical_root: Path, forum_id: str,
                     resolve: CandidateResolver) -> tuple[LoadedCharacter, ...]:
    """The only mutable namespace: `characters/<id>/state.json` (+ an optional lock).

    `resolve` accepts only current APPROVED candidates of this instance's closed snapshot.
    """
    folder = physical / CHARACTERS_DIR
    if not os.path.lexists(folder):
        return ()
    if _is_link(folder) or not folder.is_dir():
        _invalid(f"{CHARACTERS_DIR} no es una carpeta normal")
    loaded = []
    for entry in sorted(folder.iterdir(), key=lambda p: p.name):
        where = f"{CHARACTERS_DIR}/{entry.name}"
        if _is_link(entry) or not entry.is_dir():
            _invalid(f"{where} no es la carpeta de un personaje")
        try:
            check_character_id(entry.name)
        except CharacterError:
            _invalid(f"{where} no es un ID de personaje válido (¿restos de una operación "
                     "interrumpida?)")
        children = {child.name: child for child in entry.iterdir()}
        if CHARACTER_STATE not in children or not set(children) <= {CHARACTER_STATE,
                                                                     CHARACTER_LOCK}:
            _invalid(f"{where} debe contener solo {CHARACTER_STATE} y, como mucho, su cerrojo")
        for name, child in children.items():
            if _is_link(child) or not child.is_file():
                _invalid(f"{where}/{name} no es un archivo normal")
        revision, content = load_state(entry / CHARACTER_STATE)
        state = decode_character_state(content, forum_id=forum_id, revision=revision,
                                       candidate_resolver=resolve)
        if state.character_id != entry.name:
            _invalid(f"{where} contiene el personaje «{state.character_id}»")
        loaded.append(LoadedCharacter(logical_root / CHARACTERS_DIR / entry.name, revision,
                                      state))
    return tuple(loaded)


def _parse_config(data: object) -> InstanceConfig:
    if not isinstance(data, dict) or set(data) != _CONFIG_KEYS:
        _invalid(f"{INSTANCE_FILE} no tiene exactamente las claves esperadas")
    if data["kind"] != INSTANCE_KIND:
        _invalid(f"{INSTANCE_FILE} no es una instancia de foro")
    corpus, dossier, source = data["corpus"], data["dossier"], data["source_workspace"]
    if not isinstance(corpus, dict) or set(corpus) != _CORPUS_KEYS:
        _invalid(f"{INSTANCE_FILE}: «corpus» con claves inesperadas")
    if not isinstance(dossier, dict) or set(dossier) != {"files", "path"}:
        _invalid(f"{INSTANCE_FILE}: «dossier» con claves inesperadas")
    if not isinstance(source, dict) or set(source) != {"workspace_json_sha256"}:
        _invalid(f"{INSTANCE_FILE}: «source_workspace» con claves inesperadas")
    for name in ("core_root", "instance_root"):
        if not isinstance(data[name], str):
            _invalid(f"{INSTANCE_FILE}: {name} debe ser texto")
    if not isinstance(data["packages"], list):
        _invalid(f"{INSTANCE_FILE}: packages debe ser una lista")
    return InstanceConfig(
        schema_version=data["schema_version"],
        forum_id=data["forum_id"],
        display_name=data["display_name"],
        dossier_version=data["dossier_version"],
        core_root=Path(data["core_root"]),
        instance_root=Path(data["instance_root"]),
        dossier_path=dossier["path"],
        dossier_files=_parse_managed_list(dossier["files"]),
        corpus=InstanceCorpus(corpus["path"], corpus["revision"], corpus["sha256"],
                              corpus["size"], corpus["snapshot_sha256"]),
        source_workspace=SourceWorkspace(source["workspace_json_sha256"]),
        packages=tuple(data["packages"]),
    )


# --- Helpers ----------------------------------------------------------------------------------


def _parents(relative: str) -> list[str]:
    """`a/b/c.md` -> [`a`, `a/b`]."""
    parts = relative.split("/")[:-1]
    return ["/".join(parts[:i]) for i in range(1, len(parts) + 1)]


def _absolute(path: Path) -> Path:
    try:
        return Path(path).absolute()
    except TypeError as exc:
        raise InstanceError("INVALID_STATE", "la ruta de la instancia no es válida") from exc


def _canonical(path: Path) -> Path:
    """Absolute, links resolved, long names and no device prefix; original case kept."""
    text = _strip_device_prefix(os.fspath(Path(path).absolute()))
    return Path(_strip_device_prefix(os.path.realpath(text)))


def _powershell(path: Path) -> str:
    """A path for a single-quoted PowerShell string: every `'` doubled."""
    return str(path).replace("'", "''")


def _read_regular(root: Path, relative: str) -> bytes:
    path = root
    for segment in relative.split("/"):
        path = path / segment
        if _is_link(path):
            _invalid(f"{relative} atraviesa un enlace simbólico o una junction")
    if not path.is_file():
        _invalid(f"falta {relative} o no es un archivo")
    return path.read_bytes()


def _require_sha256(name: str, value: object) -> None:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        _invalid(f"{name} debe ser un SHA-256 en minúsculas")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _invalid(reason: str) -> None:
    raise InstanceError("INVALID_STATE", reason)


def _unsafe(reason: str) -> None:
    raise InstanceError("UNSAFE_DESTINATION", reason)
