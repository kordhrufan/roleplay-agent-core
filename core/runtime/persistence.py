"""Provisional JSON persistence for workspaces and instances (until SQLite).

Strict canonical JSON, atomic single-file replacement and a self-hashed state envelope. The
hashes detect accidental edits; they do not authenticate who wrote the file.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

STATE_SCHEMA_VERSION = 1

_STATE_KEYS = frozenset({"schema_version", "revision", "content", "content_sha256"})
_UTF8_BOM = b"\xef\xbb\xbf"
_CODES = frozenset({"INVALID_STATE", "IO"})


class PersistenceError(ValueError):
    """Invalid persisted data (`INVALID_STATE`) or a filesystem failure (`IO`)."""

    def __init__(self, code: str, reason: str):
        if code not in _CODES:
            raise ValueError(f"unknown persistence error code {code!r}")
        self.code = code
        self.reason = reason
        super().__init__(f"{code}: {reason}")


def canonical_json_bytes(value: object, *, pretty: bool) -> bytes:
    """UTF-8 JSON with sorted keys. Pretty: two-space indent and final LF. Compact: no spaces."""
    try:
        if pretty:
            text = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                              allow_nan=False) + "\n"
        else:
            text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                              allow_nan=False)
        return text.encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise PersistenceError("INVALID_STATE", f"el valor no se puede guardar como JSON: {exc}") from exc


def load_strict_json(path: Path) -> object:
    """Read a strict JSON document: UTF-8 without BOM, no duplicate keys or NaN/Infinity."""
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise PersistenceError("IO", f"no se puede leer {Path(path).as_posix()}: {exc}") from exc
    return parse_strict_json(raw, Path(path).as_posix())


def parse_strict_json(raw: bytes, locator: str) -> object:
    if raw.startswith(_UTF8_BOM):
        raise PersistenceError("INVALID_STATE", f"{locator} empieza con BOM")
    try:
        text = raw.decode("utf-8")
        return json.loads(text, object_pairs_hook=_reject_duplicates,
                          parse_constant=_reject_constant)
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise PersistenceError("INVALID_STATE", f"{locator} no es JSON estricto: {exc}") from exc


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Replace `path` with `data` through a fresh temporary file in the same directory.

    The destination is never opened for truncation. This is atomic per file against process
    failures; it is neither a multi-file transaction nor a guarantee against power loss.
    """
    path = Path(path)
    if not isinstance(data, bytes):
        raise PersistenceError("INVALID_STATE", "atomic_write_bytes necesita bytes")
    temporary = None
    try:
        handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.",
                                             suffix=".tmp")
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    except OSError as exc:
        reason = f"no se puede escribir {path.as_posix()}: {exc}"
        if temporary is not None and not _remove(temporary):
            reason += f"; además no se pudo borrar el temporal {temporary}: bórralo a mano"
        temporary = None
        raise PersistenceError("IO", reason) from exc
    finally:
        if temporary is not None:  # interrupted by a non-OSError exception
            _remove(temporary)


def encode_state(content: object, *, revision: int) -> bytes:
    """Serialize a mutable state inside the common self-hashed envelope."""
    if type(revision) is not int or revision < 0:
        raise PersistenceError("INVALID_STATE", "revision debe ser un entero no negativo")
    envelope = {"schema_version": STATE_SCHEMA_VERSION, "revision": revision, "content": content}
    envelope["content_sha256"] = hashlib.sha256(
        canonical_json_bytes(envelope, pretty=False)
    ).hexdigest()
    return canonical_json_bytes(envelope, pretty=True)


def load_state(path: Path) -> tuple[int, object]:
    """Read a state envelope; the file must be byte-identical to its canonical encoding."""
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise PersistenceError("IO", f"no se puede leer {path.as_posix()}: {exc}") from exc
    data = parse_strict_json(raw, path.as_posix())
    if not isinstance(data, dict) or set(data) != _STATE_KEYS:
        raise PersistenceError("INVALID_STATE", f"{path.as_posix()} no es un sobre de estado")
    if type(data["schema_version"]) is not int or data["schema_version"] != STATE_SCHEMA_VERSION:
        raise PersistenceError("INVALID_STATE", f"{path.as_posix()} tiene un schema_version desconocido")
    revision = data["revision"]
    if type(revision) is not int or revision < 0:
        raise PersistenceError("INVALID_STATE", f"{path.as_posix()} tiene una revision inválida")
    expected = encode_state(data["content"], revision=revision)
    if raw != expected:
        raise PersistenceError(
            "INVALID_STATE",
            f"{path.as_posix()} se modificó fuera del core (no coincide el hash o la forma canónica)",
        )
    return revision, data["content"]


def _remove(path: str) -> bool:
    """Delete a temporary file; return False if it is still there."""
    try:
        os.unlink(path)
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return True


def _reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"clave repetida {key!r}")
        result[key] = value
    return result


def _reject_constant(name: str) -> object:
    raise ValueError(f"constante JSON no estándar {name}")
