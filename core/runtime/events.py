"""Shared mechanics of the append-only, self-hashed states in an instance's mutable trees.

`characters/<id>/state.json` (4d) and `narrative/topics/<id>/state.json` (7a) are both an event log
in one self-hashed envelope, written under one lock per folder. These helpers hold the mechanics
that both use: the guard, appending exactly one event and publishing a new folder by staging.
Callers pass the lock and publish primitives they resolve at call time, so tests that replace
them in the caller's module keep working.
"""

from __future__ import annotations

import os
import secrets
from collections.abc import Callable
from pathlib import Path

from core.runtime.instance import require_no_update
from core.runtime.persistence import atomic_write_bytes
from core.runtime.workspace import (
    WorkspaceError,
    _ConcurrentDestination,
    _destination_state,
    _is_link,
    _linked_component,
    _remove_staging,
)

ErrorFactory = Callable[[str, str], Exception]


def folder_guard(folder: Path, state_name: str, instance_root: Path,
                 error: ErrorFactory) -> Callable[[], None]:
    """A check that `folder` is still the same plain folder, with no link on the way, and that no
    `instance update` is replacing the instance's static files.

    It runs before taking the lock, right after taking it and right before writing; the remaining
    window between the last check and the atomic replace cannot be closed without handle-relative
    file APIs, which the standard library does not offer on Windows.
    """
    identity = folder_identity(folder, error)

    def guard() -> None:
        require_no_update(instance_root)
        linked = _linked_component(folder / state_name)
        if linked is not None:
            raise error("UNSAFE_DESTINATION", f"{linked} es un enlace simbólico o una junction; "
                                              "no se ha escrito nada")
        if folder_identity(folder, error) != identity:
            raise error("CONFLICT", f"{folder} fue sustituida mientras se guardaba; no se ha "
                                    "escrito nada")

    return guard


def folder_identity(folder: Path, error: ErrorFactory) -> tuple[int, int]:
    try:
        info = os.lstat(folder)
    except OSError as exc:
        raise error("CONFLICT", f"{folder} ya no está disponible") from exc
    return (info.st_dev, info.st_ino)


def append_event(state_path: Path, *, subject: str, guard: Callable[[], None],
                 prepare: Callable[[], bytes], lock) -> None:
    """Under the lock: `prepare` reloads, checks nothing changed and returns the new envelope with
    exactly one more event; the guard runs again and the file is replaced atomically."""
    guard()
    with lock(state_path, subject, guard=guard):
        data = prepare()
        guard()
        atomic_write_bytes(state_path, data)


def publish_new_folder(parent: Path, name: str, state_name: str, data: bytes, *,
                       instance_root: Path, noun: str, label: str, error: ErrorFactory,
                       check_staged: Callable[[Path], None], lock, publish) -> bool:
    """Publish `<parent>/<name>/<state_name>` atomically; True if created, False if an identical
    one was published at the same time by someone else.

    `<parent>/.<name>.create.lock` exists meanwhile: `instance update` refuses to start while it
    exists, and this publication refuses to go on while an update lock exists.
    """
    linked = _linked_component(parent)
    if linked is not None:
        raise error("UNSAFE_DESTINATION", f"{linked} es un enlace simbólico o una junction")
    parent.mkdir(parents=True, exist_ok=True)
    if _is_link(parent) or not parent.is_dir():
        raise error("UNSAFE_DESTINATION", f"{parent} no es una carpeta normal")
    with lock(parent / f".{name}.create", f"la creación de {label}",
              guard=lambda: require_no_update(instance_root)):
        return _publish_staged(parent, name, state_name, data, instance_root=instance_root,
                               noun=noun, label=label, error=error, check_staged=check_staged,
                               publish=publish)


def _publish_staged(parent: Path, name: str, state_name: str, data: bytes, *,
                    instance_root: Path, noun: str, label: str, error: ErrorFactory,
                    check_staged: Callable[[Path], None], publish) -> bool:
    target = parent / name
    initial = _destination_state(target)
    if initial is not None:
        raise error("CONFLICT", f"{target} ya existe")
    staging = parent / f".{name}.staging-{secrets.token_hex(8)}"
    staging.mkdir()
    concurrent = None
    try:
        with open(staging / state_name, "xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        check_staged(staging)
        require_no_update(instance_root)
        try:
            publish(staging, target, initial)
        except _ConcurrentDestination as race:
            concurrent = race
    except BaseException as exc:
        leftover = _remove_staging(staging)
        coded = getattr(exc, "code", None), getattr(exc, "reason", None)
        if leftover is None or not (isinstance(exc, (WorkspaceError, OSError))
                                    or all(isinstance(v, str) for v in coded)):
            raise
        code = coded[0] if isinstance(coded[0], str) else "IO"
        reason = coded[1] if isinstance(coded[1], str) else str(exc)
        raise error(code, f"{reason}; además no se pudo borrar {leftover}: bórrala a mano") from exc
    if concurrent is not None:
        leftover = _remove_staging(staging)
        winner = target / state_name
        identical = winner.is_file() and not _is_link(winner) and winner.read_bytes() == data
        if leftover is not None:
            raise error("IO", f"otro proceso creó a la vez {noun} en {target}, pero no se pudo "
                              f"borrar {leftover}: bórrala a mano") from concurrent.error
        if not identical:
            raise error("CONFLICT", f"otro proceso creó a la vez {label} con otro contenido; no "
                                    "se ha tocado")
        return False
    return True
