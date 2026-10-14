"""Assimilation workspace: an external folder holding an exact copy of a ready dossier.

The workspace is where candidates will be prepared and decided (4b-4c) before any forum
instance or agent instructions exist. Managed files are covered by an integrity manifest; the
corpus state is a self-hashed envelope. Hashes detect edits; they do not authenticate actors.

An expansion workspace (5a) is a separate kind: it binds by content to an existing instance,
holds a copy of that instance's dossier and closed corpus, a strictly additive successor dossier
and the delta of one round. Earlier closures are never reopened.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import string
from dataclasses import dataclass
from pathlib import Path

from core.runtime.assimilation import (
    DOSSIER_NAME,
    AssimilationCandidate,
    AssimilationClosure,
    AssimilationDecision,
    AssimilationError,
    ClosedCorpus,
    CorpusSnapshot,
    DossierDelta,
    DossierError,
    DossierFileRef,
    DossierSectionStatus,
    DossierSnapshot,
    ExpansionContext,
    LoadedForumDossier,
    decode_candidate_state,
    decode_closed_corpus,
    load_dossier,
)
from core.runtime.persistence import (
    PersistenceError,
    canonical_json_bytes,
    encode_state,
    load_state,
    parse_strict_json,
)

WORKSPACE_SCHEMA_VERSION = 1
INTEGRITY_SCHEMA_VERSION = 1

WORKSPACE_FILE = "workspace.json"
DOSSIER_DIR = "dossier"
DOSSIER_PATH = f"{DOSSIER_DIR}/{DOSSIER_NAME}"
CORPUS_STATE = "corpus/state.json"
INTEGRITY_FILE = "work/integrity.json"
WORKSPACE_KIND = "forum-assimilation-workspace"
INITIAL_CORPUS = {"candidates": [], "closure": None, "decisions": []}
EXPANSION_WORKSPACE_SCHEMA_VERSION = 2
EXPANSION_WORKSPACE_KIND = "forum-assimilation-expansion-workspace"
BASE_CORPUS = "corpus/base.json"
BASE_PREFIX = "base"
BASE_DOSSIER_DIR = f"{BASE_PREFIX}/{DOSSIER_DIR}"
BASE_DOSSIER_PATH = f"{BASE_DOSSIER_DIR}/{DOSSIER_NAME}"

_TEMPLATE = Path(__file__).resolve().parent / "templates" / "workspace.template.json"
_CHECKOUT_MARKER = ("core", "runtime", "cli.py")
_CODES = frozenset({"INVALID_STATE", "CONFLICT", "UNSAFE_DESTINATION", "IO"})
_WORKSPACE_KEYS = frozenset(
    {"core_root", "display_name", "dossier", "dossier_version", "forum_id", "kind",
     "schema_version"}
)
_EXPANSION_KEYS = _WORKSPACE_KEYS | {"base_dossier", "base_instance"}
_BASE_INSTANCE_KEYS = frozenset({"corpus_revision", "corpus_sha256", "instance_json_sha256",
                                 "integrity_sha256", "snapshot_sha256"})
_INTEGRITY_KEYS = frozenset({"algorithm", "files", "schema_version"})
_MANAGED_KEYS = frozenset({"path", "sha256", "size"})
_NAME_SURROGATE = 0x20000000  # reparse tags that redirect to another path (junction, symlink)
_FORUM_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_CONTROL = re.compile(r"[\x00-\x1f]")


class WorkspaceError(ValueError):
    """`code` is INVALID_STATE, CONFLICT, UNSAFE_DESTINATION or IO."""

    def __init__(self, code: str, reason: str):
        if code not in _CODES:
            raise ValueError(f"unknown workspace error code {code!r}")
        self.code = code
        self.reason = reason
        super().__init__(f"{code}: {reason}")


@dataclass(frozen=True, slots=True)
class ManagedFile:
    path: str
    sha256: str
    size: int

    def __post_init__(self) -> None:
        _check_relative(self.path)
        if not isinstance(self.sha256, str) or not _SHA256.fullmatch(self.sha256):
            _invalid(f"hash inválido para {self.path}")
        if type(self.size) is not int or self.size < 0:
            _invalid(f"tamaño inválido para {self.path}")

    def as_json(self) -> dict[str, object]:
        return {"path": self.path, "sha256": self.sha256, "size": self.size}


@dataclass(frozen=True, slots=True)
class BaseInstance:
    """What an expansion workspace binds to: the instance's static state, by content."""

    corpus_revision: int
    corpus_sha256: str
    instance_json_sha256: str
    integrity_sha256: str
    snapshot_sha256: str

    def __post_init__(self) -> None:
        if type(self.corpus_revision) is not int or self.corpus_revision < 1:
            _invalid("base_instance.corpus_revision debe ser un entero positivo")
        for name in ("corpus_sha256", "instance_json_sha256", "integrity_sha256",
                     "snapshot_sha256"):
            value = getattr(self, name)
            if not isinstance(value, str) or not _SHA256.fullmatch(value):
                _invalid(f"base_instance.{name} debe ser un SHA-256 en minúsculas")

    def as_json(self) -> dict[str, object]:
        return {"corpus_revision": self.corpus_revision, "corpus_sha256": self.corpus_sha256,
                "instance_json_sha256": self.instance_json_sha256,
                "integrity_sha256": self.integrity_sha256,
                "snapshot_sha256": self.snapshot_sha256}


@dataclass(frozen=True, slots=True)
class WorkspaceConfig:
    schema_version: int
    forum_id: str
    display_name: str
    dossier_version: str
    core_root: Path
    dossier_path: str
    dossier_files: tuple[ManagedFile, ...]
    base_instance: BaseInstance | None = None  # only expansion workspaces (schema 2)
    base_dossier_files: tuple[ManagedFile, ...] = ()

    @property
    def is_expansion(self) -> bool:
        return self.base_instance is not None

    def __post_init__(self) -> None:
        if self.base_instance is None:
            if type(self.schema_version) is not int or self.schema_version != WORKSPACE_SCHEMA_VERSION:
                _invalid(f"schema_version debe ser {WORKSPACE_SCHEMA_VERSION}")
            if self.base_dossier_files != ():
                _invalid("solo un workspace de ampliación copia el expediente base")
        else:
            if (type(self.schema_version) is not int
                    or self.schema_version != EXPANSION_WORKSPACE_SCHEMA_VERSION):
                _invalid(f"schema_version debe ser {EXPANSION_WORKSPACE_SCHEMA_VERSION}")
            if not isinstance(self.base_instance, BaseInstance):
                _invalid("base_instance inválido")
            _check_managed_list(self.base_dossier_files)
            base_paths = [f.path for f in self.base_dossier_files]
            if BASE_DOSSIER_PATH not in base_paths or not all(
                path.startswith(f"{BASE_DOSSIER_DIR}/") for path in base_paths
            ):
                _invalid(f"base_dossier.files debe incluir {BASE_DOSSIER_PATH} y solo rutas bajo "
                         f"{BASE_DOSSIER_DIR}/")
        if not isinstance(self.forum_id, str) or not _FORUM_ID.fullmatch(self.forum_id):
            _invalid("forum_id inválido")
        for name in ("display_name", "dossier_version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or value != value.strip() or _CONTROL.search(value):
                _invalid(f"{name} inválido")
        if not isinstance(self.core_root, Path) or not self.core_root.is_absolute():
            _invalid("core_root debe ser una ruta absoluta")
        if self.dossier_path != DOSSIER_PATH:
            _invalid(f"dossier.path debe ser {DOSSIER_PATH}")
        _check_managed_list(self.dossier_files)
        paths = [f.path for f in self.dossier_files]
        if DOSSIER_PATH not in paths:
            _invalid(f"dossier.files debe incluir {DOSSIER_PATH}")
        if not all(p.startswith(f"{DOSSIER_DIR}/") for p in paths):
            _invalid("dossier.files solo admite rutas bajo dossier/")


@dataclass(frozen=True, slots=True)
class LoadedWorkspace:
    """In an expansion workspace, candidates/decisions/closure are the round's delta only."""

    config: WorkspaceConfig
    workspace_root: Path
    dossier: LoadedForumDossier
    corpus_revision: int
    candidates: tuple[AssimilationCandidate, ...]
    decisions: tuple[AssimilationDecision, ...]
    closure: AssimilationClosure | CorpusSnapshot | None
    expansion: ExpansionContext | None = None


@dataclass(frozen=True, slots=True)
class WorkspaceInitResult:
    workspace: LoadedWorkspace
    created: bool


def create_workspace(
    dossier: LoadedForumDossier, *, dossier_dir: Path, workspace: Path, core_root: Path
) -> WorkspaceInitResult:
    """Create `workspace` from a loaded dossier, or return the identical existing one."""
    if not isinstance(dossier, LoadedForumDossier):
        _invalid("se necesita un expediente cargado")
    dossier_dir = Path(dossier_dir)
    core_root = _checkout(core_root)
    target = _absolute(workspace)
    try:
        if _identity(dossier.dossier_path) != _identity(dossier_dir / DOSSIER_NAME):
            _invalid("el expediente cargado no corresponde a la carpeta indicada")
        _check_destination(target, core_root, dossier_dir)
        initial = _destination_state(target)
        expected = _expected_files(dossier, dossier_dir, core_root)
        if target.exists() and any(target.iterdir()):
            return WorkspaceInitResult(_existing(target, expected, core_root), False)
        return _materialize(target, expected, dossier, core_root, initial)
    except PersistenceError as exc:
        raise WorkspaceError(exc.code, exc.reason) from exc
    except OSError as exc:
        raise WorkspaceError("IO", f"error de disco al crear el workspace: {exc}") from exc


def load_workspace(workspace_root: Path, *, expected_core_root: Path | None = None) -> LoadedWorkspace:
    """Load and verify a workspace. Any edit outside the core makes it fail closed."""
    root = _absolute(workspace_root)
    try:
        return _load_workspace(root, expected_core_root)
    except PersistenceError as exc:
        raise WorkspaceError(exc.code, exc.reason) from exc
    except DossierError as exc:
        raise WorkspaceError("INVALID_STATE", f"el expediente copiado no carga: {exc}") from exc
    except OSError as exc:
        raise WorkspaceError("IO", f"error de disco al leer el workspace: {exc}") from exc


# --- Creation ---------------------------------------------------------------------------------


def _checkout(core_root: Path) -> Path:
    core_root = Path(core_root)
    if not core_root.is_absolute():
        _invalid("core_root debe ser una ruta absoluta")
    if not core_root.joinpath(*_CHECKOUT_MARKER).is_file():
        _invalid(f"{core_root} no es el checkout de roleplay-agent-core")
    return core_root.resolve()


def _absolute(path: Path) -> Path:
    try:
        return Path(path).absolute()
    except TypeError as exc:
        raise WorkspaceError("INVALID_STATE", "la ruta del workspace no es válida") from exc


def _check_destination(target: Path, core_root: Path, dossier_dir: Path,
                       *others: tuple[str, Path]) -> None:
    _require_publish_support()
    if _CONTROL.search(str(target)):
        _unsafe("la ruta del workspace contiene caracteres de control")
    linked = _linked_component(target)
    if linked is not None:
        _unsafe(f"{linked} es un enlace simbólico o una junction; usa la ruta real")
    parent = target.parent
    if not parent.is_dir():
        _unsafe(f"la carpeta padre {parent} no existe; créala antes")
    real = _identity(target)
    for name, other in (("el checkout del core", core_root), ("el expediente", dossier_dir),
                        *others):
        other_real = _identity(other)
        if _contains(other_real, real) or _contains(real, other_real):
            _unsafe(f"el workspace no puede coincidir ni solaparse con {name}")
    if target.exists() and not target.is_dir():
        _unsafe(f"{target} existe y no es una carpeta")


def _identity(path: Path) -> str:
    """One spelling per filesystem object: no device prefix, long names, resolved links, case."""
    text = _strip_device_prefix(os.fspath(Path(path).absolute()))
    return os.path.normcase(_strip_device_prefix(os.path.realpath(text)))


def _strip_device_prefix(text: str) -> str:
    if os.name != "nt":
        return text
    if text.startswith("\\\\?\\UNC\\"):
        return "\\\\" + text[8:]
    if text.startswith(("\\\\?\\", "\\\\.\\")):
        return text[4:]
    return text


def _contains(outer: str, inner: str) -> bool:
    try:
        return os.path.commonpath([outer, inner]) == outer
    except ValueError:  # different drives
        return False


def _is_link(path: Path) -> bool:
    """Symlinks and Windows junctions (any reparse point that redirects to another path).

    Other reparse points, such as cloud placeholders (e.g. OneDrive), are ordinary content.
    """
    try:
        info = os.lstat(path)
    except (FileNotFoundError, NotADirectoryError):
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    return bool(getattr(info, "st_reparse_tag", 0) & _NAME_SURROGATE)


def _linked_component(path: Path) -> Path | None:
    """The first existing component of `path`, itself or a parent, that is a link or junction."""
    absolute = Path(_strip_device_prefix(os.fspath(Path(path).absolute())))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if not os.path.lexists(current):
            return None
        if _is_link(current):
            return current
    return None


def _destination_state(target: Path) -> tuple[int, int, int] | None:
    """Identity of the destination when it was checked: None if absent."""
    try:
        info = os.lstat(target)
    except FileNotFoundError:
        return None
    return (info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode))


def _publish_supported() -> bool:
    """Atomic no-replace publishing relies on Windows rename semantics."""
    return os.name == "nt"


def _require_publish_support() -> None:
    if not _publish_supported():
        _unsafe("crear workspaces e instancias solo está soportado en Windows por ahora: en "
                "este sistema, renombrar una carpeta puede reemplazar otra vacía creada a la vez")


def _publish(staging: Path, target: Path, initial: tuple[int, int, int] | None) -> None:
    """Move the staging into place only if the destination is exactly as it was checked.

    Absent stays absent (rename never replaces an existing folder on Windows); an initially empty
    folder must be the same folder and still empty. Any other change is a CONFLICT and the
    destination is left untouched. Only Windows is supported: on POSIX, rename could replace an
    empty folder created in the instant between the last check and the rename, so creation is
    refused there (see `_require_publish_support`).
    """
    _require_publish_support()
    linked = _linked_component(target)
    if linked is not None:
        raise WorkspaceError("UNSAFE_DESTINATION", f"{linked} es un enlace simbólico o una "
                                                   "junction; usa la ruta real")
    if _destination_state(target) != initial:
        raise WorkspaceError("CONFLICT", f"{target} cambió mientras se preparaba; no se ha "
                                         "tocado")
    if initial is not None:
        if any(target.iterdir()):
            raise WorkspaceError("CONFLICT", f"{target} dejó de estar vacía; no se ha tocado")
        target.rmdir()
    try:
        os.replace(staging, target)
    except OSError as exc:
        if os.path.lexists(target):
            raise _ConcurrentDestination(exc) from exc
        if initial is not None:
            target.mkdir()
        raise


class _ConcurrentDestination(Exception):
    """Another actor created the destination between the last check and the rename."""

    def __init__(self, error: OSError):
        super().__init__(str(error))
        self.error = error


def _existing(target: Path, expected: dict[str, bytes], core_root: Path) -> LoadedWorkspace:
    """Accept a non-empty destination only if it is exactly the workspace that would be created."""
    if _tree_bytes(target) != expected:
        raise WorkspaceError("CONFLICT", f"{target} ya contiene otro contenido; elige una "
                                         "carpeta vacía o inexistente")
    return load_workspace(target, expected_core_root=core_root)


def _dossier_copy(dossier: LoadedForumDossier, dossier_dir: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {DOSSIER_PATH: _read_regular(dossier_dir / DOSSIER_NAME)}
    for loaded in _loaded_sources(dossier):
        if loaded.spec.path is not None:
            files.setdefault(f"{DOSSIER_DIR}/{loaded.spec.path}",
                             loaded.literal_text.encode("utf-8"))
    return files


def _render_config(dossier: LoadedForumDossier, core_root: Path,
                   dossier_files: list[ManagedFile]) -> dict:
    meta = dossier.dossier
    rendered = string.Template(_TEMPLATE.read_text(encoding="utf-8")).substitute(
        core_root_json=json.dumps(str(core_root), ensure_ascii=False),
        display_name_json=json.dumps(meta.display_name, ensure_ascii=False),
        dossier_files_json=json.dumps([f.as_json() for f in dossier_files], ensure_ascii=False),
        dossier_version_json=json.dumps(meta.dossier_version, ensure_ascii=False),
        forum_id_json=json.dumps(meta.forum_id, ensure_ascii=False),
    )
    return parse_strict_json(rendered.encode("utf-8"), _TEMPLATE.as_posix())


def _expected_files(
    dossier: LoadedForumDossier, dossier_dir: Path, core_root: Path
) -> dict[str, bytes]:
    files = _dossier_copy(dossier, dossier_dir)
    dossier_files = sorted((_managed(path, data) for path, data in files.items()),
                           key=lambda f: f.path)
    config_data = _render_config(dossier, core_root, dossier_files)
    _parse_config(config_data)
    files[WORKSPACE_FILE] = canonical_json_bytes(config_data, pretty=True)
    files[CORPUS_STATE] = encode_state(INITIAL_CORPUS, revision=0)
    covered = sorted(
        [_managed(WORKSPACE_FILE, files[WORKSPACE_FILE]), *dossier_files], key=lambda f: f.path
    )
    integrity = {
        "algorithm": "sha256",
        "files": [f.as_json() for f in covered],
        "schema_version": INTEGRITY_SCHEMA_VERSION,
    }
    files[INTEGRITY_FILE] = canonical_json_bytes(integrity, pretty=True)
    return files


def _materialize(
    target: Path, expected: dict[str, bytes], dossier: LoadedForumDossier, core_root: Path,
    initial: tuple[int, int, int] | None, recheck=None,
) -> WorkspaceInitResult:
    staging = target.parent / f".{target.name}.staging-{secrets.token_hex(8)}"
    staging.mkdir()
    concurrent: tuple[LoadedWorkspace, OSError] | None = None
    try:
        for relative, data in expected.items():
            path = staging.joinpath(*relative.split("/"))
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        staged = load_workspace(staging, expected_core_root=core_root)
        if _source_fingerprint(staged.dossier) != _source_fingerprint(dossier):
            raise WorkspaceError("CONFLICT", "el expediente cambió mientras se copiaba; repite")
        if recheck is not None:
            recheck()
        try:
            _publish(staging, target, initial)
        except _ConcurrentDestination as race:
            # Another actor created the destination meanwhile: never overwrite it.
            concurrent = (_existing(target, expected, core_root), race.error)
    except BaseException as exc:
        leftover = _remove_staging(staging)
        if leftover is None or not isinstance(exc, (WorkspaceError, OSError)):
            raise
        code = exc.code if isinstance(exc, WorkspaceError) else "IO"
        reason = exc.reason if isinstance(exc, WorkspaceError) else str(exc)
        raise WorkspaceError(code, f"{reason}; además no se pudo borrar {leftover}: bórrala a "
                                   "mano") from exc
    if concurrent is not None:
        loaded, replace_error = concurrent
        leftover = _remove_staging(staging)
        if leftover is not None:
            raise WorkspaceError("IO", f"otro proceso creó a la vez el mismo workspace en {target}, "
                                       f"pero no se pudo borrar {leftover}: bórrala a mano"
                                 ) from replace_error
        return WorkspaceInitResult(loaded, False)
    return WorkspaceInitResult(load_workspace(target, expected_core_root=core_root), True)


def _remove_staging(staging: Path) -> str | None:
    """Remove the known staging directory. Return its path if something could not be removed."""
    if not os.path.lexists(staging):
        return None
    try:
        shutil.rmtree(staging)
    except OSError:
        return str(staging)
    return None


def _source_fingerprint(dossier: LoadedForumDossier) -> tuple:
    return (dossier.dossier, tuple((s.literal_text, s.source_ref.sha256)
                                   for s in _loaded_sources(dossier)))


def _loaded_sources(dossier: LoadedForumDossier):
    for section in dossier.sections:
        yield from section.sources
    for material in dossier.loose_material:
        yield material.source


def _tree_bytes(root: Path) -> dict[str, bytes]:
    """Every file under `root` (no symlinks allowed). Empty directories count as a difference."""
    result: dict[str, bytes] = {}
    for current, directories, files in os.walk(root, followlinks=False):
        here = Path(current)
        for name in directories + files:
            if _is_link(here / name):
                raise WorkspaceError("CONFLICT", f"{here / name} es un enlace simbólico")
        if not directories and not files and here != root:
            result[here.relative_to(root).as_posix() + "/"] = b""
        for name in files:
            result[(here / name).relative_to(root).as_posix()] = (here / name).read_bytes()
    return result


def _read_regular(path: Path) -> bytes:
    if _is_link(path) or not path.is_file():
        _invalid(f"{path} no es un archivo regular")
    return path.read_bytes()


def _managed(path: str, data: bytes) -> ManagedFile:
    return ManagedFile(path, hashlib.sha256(data).hexdigest(), len(data))


# --- Expansion (5a) ---------------------------------------------------------------------------


def create_expansion_workspace(
    instance_root: Path, *, dossier: LoadedForumDossier, dossier_dir: Path, workspace: Path,
    core_root: Path,
) -> WorkspaceInitResult:
    """Create the expansion workspace of one round over an instance, or return the identical one.

    The successor dossier must be strictly additive. The instance is read, never written; the
    workspace keeps byte copies of its dossier and closed corpus and binds to it by content.
    """
    if not isinstance(dossier, LoadedForumDossier):
        _invalid("se necesita un expediente cargado")
    dossier_dir = Path(dossier_dir)
    core_root = _checkout(core_root)
    target = _absolute(workspace)
    instance_root = _absolute(instance_root)
    try:
        if _identity(dossier.dossier_path) != _identity(dossier_dir / DOSSIER_NAME):
            _invalid("el expediente cargado no corresponde a la carpeta indicada")
        real_instance, real_dossier = _identity(instance_root), _identity(dossier_dir)
        if _contains(real_instance, real_dossier) or _contains(real_dossier, real_instance):
            _unsafe("el expediente no puede coincidir ni solaparse con la instancia")
        _check_destination(target, core_root, dossier_dir, ("la instancia", instance_root))
        base = _read_instance_base(instance_root, core_root)
        compare_additive_dossier(
            base.dossier, dossier,
            previous_versions=tuple(s.dossier.dossier_version for s in base.closed.snapshots))
        initial = _destination_state(target)
        expected = _expected_expansion_files(dossier, dossier_dir, core_root, base)
        if target.exists() and any(target.iterdir()):
            return WorkspaceInitResult(_existing(target, expected, core_root), False)

        def recheck() -> None:
            if _read_instance_base(instance_root, core_root).fingerprint != base.fingerprint:
                raise WorkspaceError("CONFLICT", "la instancia cambió mientras se preparaba la "
                                                 "ampliación; repite")

        return _materialize(target, expected, dossier, core_root, initial, recheck)
    except PersistenceError as exc:
        raise WorkspaceError(exc.code, exc.reason) from exc
    except AssimilationError as exc:
        raise WorkspaceError(exc.code, exc.reason) from exc
    except OSError as exc:
        raise WorkspaceError("IO", f"error de disco al crear la ampliación: {exc}") from exc


@dataclass(frozen=True, slots=True)
class _InstanceBase:
    instance_json: bytes
    integrity: bytes
    corpus: bytes
    dossier_files: dict[str, bytes]
    dossier: LoadedForumDossier
    closed: ClosedCorpus

    @property
    def fingerprint(self) -> tuple:
        return (self.instance_json, self.integrity, self.corpus, self.dossier_files)


def _read_instance_base(instance_root: Path, core_root: Path) -> _InstanceBase:
    from core.runtime.instance import (
        INSTANCE_CORPUS,
        INSTANCE_FILE,
        INSTANCE_INTEGRITY,
        InstanceError,
        load_instance,
        closed_corpus_of,
    )

    try:
        instance = load_instance(instance_root, expected_core_root=core_root)
        closed = closed_corpus_of(instance)
    except InstanceError as exc:
        raise WorkspaceError(exc.code, exc.reason) from exc
    root = instance.instance_root
    files = {f.path: _read_managed(root, f.path) for f in instance.config.dossier_files}
    for managed in instance.config.dossier_files:
        if _managed(managed.path, files[managed.path]) != managed:
            raise WorkspaceError("CONFLICT", f"{managed.path} de la instancia cambió mientras se "
                                             "leía")
    return _InstanceBase(_read_managed(root, INSTANCE_FILE), _read_managed(root, INSTANCE_INTEGRITY),
                         _read_managed(root, INSTANCE_CORPUS), files, instance.dossier, closed)


def _expected_expansion_files(dossier: LoadedForumDossier, dossier_dir: Path, core_root: Path,
                              base: _InstanceBase) -> dict[str, bytes]:
    files = _dossier_copy(dossier, dossier_dir)
    dossier_files = sorted((_managed(path, data) for path, data in files.items()),
                           key=lambda f: f.path)
    base_copy = {f"{BASE_PREFIX}/{path}": data for path, data in base.dossier_files.items()}
    base_files = sorted((_managed(path, data) for path, data in base_copy.items()),
                        key=lambda f: f.path)
    config_data = _render_config(dossier, core_root, dossier_files)
    config_data["kind"] = EXPANSION_WORKSPACE_KIND
    config_data["schema_version"] = EXPANSION_WORKSPACE_SCHEMA_VERSION
    config_data["base_instance"] = BaseInstance(
        corpus_revision=base.closed.revision,
        corpus_sha256=hashlib.sha256(base.corpus).hexdigest(),
        instance_json_sha256=hashlib.sha256(base.instance_json).hexdigest(),
        integrity_sha256=hashlib.sha256(base.integrity).hexdigest(),
        snapshot_sha256=base.closed.current.snapshot_sha256,
    ).as_json()
    config_data["base_dossier"] = {"files": [f.as_json() for f in base_files],
                                   "path": BASE_DOSSIER_PATH}
    _parse_config(config_data)
    files.update(base_copy)
    files[WORKSPACE_FILE] = canonical_json_bytes(config_data, pretty=True)
    files[BASE_CORPUS] = base.corpus
    files[CORPUS_STATE] = encode_state(INITIAL_CORPUS, revision=base.closed.revision)
    covered = sorted([_managed(WORKSPACE_FILE, files[WORKSPACE_FILE]), *dossier_files,
                      *base_files, _managed(BASE_CORPUS, base.corpus)], key=lambda f: f.path)
    integrity = {"algorithm": "sha256", "files": [f.as_json() for f in covered],
                 "schema_version": EXPANSION_WORKSPACE_SCHEMA_VERSION}
    files[INTEGRITY_FILE] = canonical_json_bytes(integrity, pretty=True)
    return files


def compare_additive_dossier(base: LoadedForumDossier, successor: LoadedForumDossier, *,
                             previous_versions: tuple[str, ...]) -> DossierDelta:
    """The new source keys of `successor`, which must keep every earlier occurrence intact.

    Versions are opaque: "successor" means a version never used in the chain, not a larger one.
    Earlier occurrences stay, in order, with the same metadata, origin and bytes; new ones use
    keys `(source_id, version)` that did not exist. A MISSING section may become PROVIDED with
    new sources; everything else (status, notes, NOT_APPLICABLE) stays identical.
    """
    old, new = base.dossier, successor.dossier
    if (old.schema_version, old.forum_id, old.display_name) != (
        new.schema_version, new.forum_id, new.display_name
    ):
        _conflict("el expediente sucesor debe conservar schema, forum_id y nombre")
    if new.dossier_version == old.dossier_version or new.dossier_version in previous_versions:
        _conflict(f"la versión de expediente «{new.dossier_version}» ya se usó en este corpus; "
                  "usa una versión nueva")
    old_keys = {(s.spec.source_id, s.spec.version) for s in _loaded_sources(base)}
    added: list[tuple[str, str]] = []

    def occurrence(loaded) -> tuple:
        return (loaded.spec, loaded.literal_text, loaded.source_ref.sha256)

    def take_new(loaded, where: str) -> None:
        key = (loaded.spec.source_id, loaded.spec.version)
        if key in old_keys:
            _conflict(f"{where}: la fuente {loaded.spec.source_id} v{loaded.spec.version} ya "
                      "existía y no puede añadirse, moverse ni cambiarse; usa otra versión")
        if key not in added:
            added.append(key)

    for before, after in zip(base.sections, successor.sections):
        where = f"«{before.spec.section.value}»"
        expected = [occurrence(s) for s in before.sources]
        position, fresh = 0, 0
        for loaded in after.sources:
            if position < len(expected) and occurrence(loaded) == expected[position]:
                position += 1
            else:
                take_new(loaded, where)
                fresh += 1
        if position != len(expected):
            _conflict(f"{where}: falta, cambió o se reordenó una fuente existente")
        if before.spec.notes != after.spec.notes:
            _conflict(f"{where}: la nota de la sección no puede cambiar en una ampliación")
        if before.spec.status != after.spec.status and not (
            before.spec.status is DossierSectionStatus.MISSING
            and after.spec.status is DossierSectionStatus.PROVIDED and fresh
        ):
            _conflict(f"{where}: el estado de la sección no puede cambiar así en una ampliación")
    old_loose = [(m.spec, m.source.literal_text, m.source.source_ref.sha256)
                 for m in base.loose_material]
    new_loose = [(m.spec, m.source.literal_text, m.source.source_ref.sha256)
                 for m in successor.loose_material]
    if new_loose[:len(old_loose)] != old_loose:
        _conflict("el material suelto solo admite anexos al final, con lo anterior intacto")
    for material in successor.loose_material[len(old_loose):]:
        take_new(material.source, "material suelto")
    if not added:
        _conflict("el expediente sucesor no añade ninguna fuente nueva")
    return DossierDelta(old.dossier_version, new.dossier_version, tuple(added))


# --- Loading ----------------------------------------------------------------------------------


def _load_workspace(root: Path, expected_core_root: Path | None) -> LoadedWorkspace:
    linked = _linked_component(root)
    if linked is not None:
        _invalid(f"{linked} es un enlace simbólico o una junction; usa la ruta real")
    if not root.is_dir():
        _invalid(f"{root} no es una carpeta de workspace")
    config_raw = _read_managed(root, WORKSPACE_FILE)
    config_data = parse_strict_json(config_raw, WORKSPACE_FILE)
    _require_canonical(config_raw, config_data, WORKSPACE_FILE)
    config = _parse_config(config_data)

    integrity_raw = _read_managed(root, INTEGRITY_FILE)
    integrity_data = parse_strict_json(integrity_raw, INTEGRITY_FILE)
    _require_canonical(integrity_raw, integrity_data, INTEGRITY_FILE)
    covered = _parse_integrity(integrity_data, config.schema_version)
    extra_cover = [*config.base_dossier_files]
    if config.is_expansion:
        extra_cover.append(_managed(BASE_CORPUS, _read_managed(root, BASE_CORPUS)))
    expected_cover = tuple(sorted([_managed(WORKSPACE_FILE, config_raw), *config.dossier_files,
                                   *extra_cover], key=lambda f: f.path))
    if covered != expected_cover:
        _invalid(f"{INTEGRITY_FILE} no corresponde a {WORKSPACE_FILE} y al expediente copiado")
    for managed in covered:
        data = _read_managed(root, managed.path)
        if len(data) != managed.size or hashlib.sha256(data).hexdigest() != managed.sha256:
            _invalid(f"{managed.path} se modificó fuera del core")
    trees = [(DOSSIER_DIR, {f.path for f in config.dossier_files})]
    if config.is_expansion:
        trees.append((BASE_PREFIX, {f.path for f in config.base_dossier_files}))
    for folder, listed in trees:
        for current, directories, files in os.walk(root / folder, followlinks=False):
            here = Path(current)
            for name in directories + files:
                path = here / name
                if _is_link(path):
                    _invalid(f"{path.relative_to(root).as_posix()} es un enlace simbólico")
                if name in files and path.relative_to(root).as_posix() not in listed:
                    _invalid(f"{path.relative_to(root).as_posix()} no forma parte del "
                             "expediente copiado")

    if expected_core_root is not None and _identity(config.core_root) != _identity(expected_core_root):
        raise WorkspaceError("CONFLICT", f"el workspace pertenece al checkout {config.core_root}")
    dossier = load_dossier(root / DOSSIER_DIR)
    meta = dossier.dossier
    if (meta.forum_id, meta.display_name, meta.dossier_version) != (
        config.forum_id, config.display_name, config.dossier_version
    ):
        _invalid("el expediente copiado no coincide con workspace.json")

    context = _expansion_context(root, config, dossier) if config.is_expansion else None
    if not _reject_symlinks(root, CORPUS_STATE).is_file():
        _invalid(f"falta {CORPUS_STATE} o no es un archivo")
    revision, content = load_state(root / CORPUS_STATE)
    try:
        state = decode_candidate_state(content, dossier=dossier, revision=revision,
                                       context=context)
    except AssimilationError as exc:
        raise WorkspaceError(exc.code, f"{CORPUS_STATE}: {exc.reason}") from exc
    return LoadedWorkspace(config, root, dossier, revision, state.candidates, state.decisions,
                           state.closure, context)


def _expansion_context(root: Path, config: WorkspaceConfig,
                       dossier: LoadedForumDossier) -> ExpansionContext:
    """Rebuild the round from the copies held by the workspace; the instance is not opened."""
    base_dossier = load_dossier(root / BASE_PREFIX / DOSSIER_DIR)
    base_meta = base_dossier.dossier
    if (base_meta.forum_id, base_meta.display_name) != (config.forum_id, config.display_name):
        _invalid("el expediente base copiado no corresponde a workspace.json")
    base_raw = _read_managed(root, BASE_CORPUS)
    base = config.base_instance
    if hashlib.sha256(base_raw).hexdigest() != base.corpus_sha256:
        _invalid(f"{BASE_CORPUS} no corresponde a base_instance")
    base_revision, base_content = load_state(root / BASE_CORPUS)
    if base_revision != base.corpus_revision:
        _invalid(f"{BASE_CORPUS} no está en la revisión de base_instance")
    base_files = tuple(ManagedFile(f.path[len(BASE_PREFIX) + 1:], f.sha256, f.size)
                       for f in config.base_dossier_files)
    try:
        closed = decode_closed_corpus(base_content, dossier=dossier, revision=base_revision,
                                      descriptor=dossier_descriptor(base_dossier, base_files))
    except AssimilationError as exc:
        raise WorkspaceError(exc.code, f"{BASE_CORPUS}: {exc.reason}") from exc
    if closed.current.snapshot_sha256 != base.snapshot_sha256:
        _invalid(f"{BASE_CORPUS} no está en el snapshot de base_instance")
    delta = compare_additive_dossier(
        base_dossier, dossier,
        previous_versions=tuple(s.dossier.dossier_version for s in closed.snapshots))
    return ExpansionContext(closed, delta, dossier_descriptor(dossier, config.dossier_files))


def expansion_input_bytes(root: Path) -> dict[str, bytes]:
    """Every static file of an expansion workspace by relative path (no delta, no lock)."""
    files = {name: _read_managed(root, name) for name in (WORKSPACE_FILE, INTEGRITY_FILE,
                                                          BASE_CORPUS)}
    for folder in (DOSSIER_DIR, BASE_PREFIX):
        for relative, data in _tree_bytes(root / folder).items():
            files[f"{folder}/{relative}"] = data
    return files


def dossier_descriptor(dossier: LoadedForumDossier,
                       files: tuple[ManagedFile, ...]) -> DossierSnapshot:
    """The snapshot descriptor of a dossier from its managed files (paths under dossier/)."""
    meta = dossier.dossier
    return DossierSnapshot(meta.schema_version, meta.forum_id, meta.dossier_version,
                           tuple(DossierFileRef(f.path, f.sha256, f.size) for f in files))


def _parse_config(data: object) -> WorkspaceConfig:
    if not isinstance(data, dict):
        _invalid(f"{WORKSPACE_FILE} no tiene exactamente las claves esperadas")
    expansion = data.get("kind") == EXPANSION_WORKSPACE_KIND
    if set(data) != (_EXPANSION_KEYS if expansion else _WORKSPACE_KEYS):
        _invalid(f"{WORKSPACE_FILE} no tiene exactamente las claves esperadas")
    if not expansion and data["kind"] != WORKSPACE_KIND:
        _invalid(f"{WORKSPACE_FILE} no es un workspace de asimilación")
    dossier = data["dossier"]
    if not isinstance(dossier, dict) or set(dossier) != {"files", "path"}:
        _invalid(f"{WORKSPACE_FILE}: «dossier» debe tener exactamente files y path")
    if not isinstance(data["core_root"], str):
        _invalid(f"{WORKSPACE_FILE}: core_root debe ser texto")
    base_instance, base_files = None, ()
    if expansion:
        instance, base = data["base_instance"], data["base_dossier"]
        if not isinstance(instance, dict) or set(instance) != _BASE_INSTANCE_KEYS:
            _invalid(f"{WORKSPACE_FILE}: «base_instance» con claves inesperadas")
        if not isinstance(base, dict) or set(base) != {"files", "path"}:
            _invalid(f"{WORKSPACE_FILE}: «base_dossier» debe tener exactamente files y path")
        if base["path"] != BASE_DOSSIER_PATH:
            _invalid(f"{WORKSPACE_FILE}: base_dossier.path debe ser {BASE_DOSSIER_PATH}")
        base_instance = BaseInstance(**{key: instance[key] for key in _BASE_INSTANCE_KEYS})
        base_files = _parse_managed_list(base["files"])
    return WorkspaceConfig(
        schema_version=data["schema_version"],
        forum_id=data["forum_id"],
        display_name=data["display_name"],
        dossier_version=data["dossier_version"],
        core_root=Path(data["core_root"]),
        dossier_path=dossier["path"],
        dossier_files=_parse_managed_list(dossier["files"]),
        base_instance=base_instance,
        base_dossier_files=base_files,
    )


def _parse_integrity(data: object, schema_version: int = INTEGRITY_SCHEMA_VERSION
                     ) -> tuple[ManagedFile, ...]:
    if not isinstance(data, dict) or set(data) != _INTEGRITY_KEYS:
        _invalid(f"{INTEGRITY_FILE} no tiene exactamente las claves esperadas")
    if type(data["schema_version"]) is not int or data["schema_version"] != schema_version:
        _invalid(f"{INTEGRITY_FILE}: schema_version desconocido")
    if data["algorithm"] != "sha256":
        _invalid(f"{INTEGRITY_FILE}: algoritmo desconocido")
    return _parse_managed_list(data["files"])


def _parse_managed_list(value: object) -> tuple[ManagedFile, ...]:
    if not isinstance(value, list):
        _invalid("la lista de archivos gestionados debe ser una lista")
    files = []
    for item in value:
        if not isinstance(item, dict) or set(item) != _MANAGED_KEYS:
            _invalid("cada archivo gestionado tiene exactamente path, sha256 y size")
        files.append(ManagedFile(item["path"], item["sha256"], item["size"]))
    result = tuple(files)
    _check_managed_list(result)
    return result


def _check_managed_list(files: object) -> None:
    if not isinstance(files, tuple) or not all(isinstance(f, ManagedFile) for f in files):
        _invalid("los archivos gestionados deben ser una tupla de ManagedFile")
    paths = [f.path for f in files]
    if paths != sorted(paths) or len(set(paths)) != len(paths):
        _invalid("los archivos gestionados deben estar ordenados y sin repetir")


def _read_managed(root: Path, relative: str) -> bytes:
    _check_relative(relative)
    path = _reject_symlinks(root, relative)
    if not path.is_file():
        _invalid(f"falta {relative} o no es un archivo")
    return path.read_bytes()


def _reject_symlinks(root: Path, relative: str) -> Path:
    path = root
    for segment in relative.split("/"):
        path = path / segment
        if _is_link(path):
            _invalid(f"{relative} atraviesa un enlace simbólico")
    return path


def _require_canonical(raw: bytes, data: object, name: str) -> None:
    if raw != canonical_json_bytes(data, pretty=True):
        _invalid(f"{name} se modificó fuera del core (no está en forma canónica)")


def _check_relative(path: object) -> None:
    if not isinstance(path, str) or not path or "\\" in path or path.startswith("/"):
        _invalid(f"ruta gestionada inválida: {path!r}")
    if ":" in path or _CONTROL.search(path):
        _invalid(f"ruta gestionada inválida: {path!r}")
    for segment in path.split("/"):
        if segment in ("", ".", "..") or segment != segment.rstrip(". "):
            _invalid(f"ruta gestionada inválida: {path!r}")


def _invalid(reason: str) -> None:
    raise WorkspaceError("INVALID_STATE", reason)


def _conflict(reason: str) -> None:
    raise WorkspaceError("CONFLICT", reason)


def _unsafe(reason: str) -> None:
    raise WorkspaceError("UNSAFE_DESTINATION", reason)
