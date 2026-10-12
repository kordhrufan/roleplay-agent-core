"""Command line for forum workspaces. There is no publishing command.

Run from the checkout root: `py -3.11 -B -m core.runtime.cli [--json] <command> ...`.
Exit codes: 0 ok, 2 usage, 3 invalid input or state, 4 conflict or unsafe destination, 5 I/O.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from adapters.manual import ManualAdapterError, load_manual_dossier
from core.runtime.assimilation import (
    AssimilationCandidate,
    AssimilationError,
    DossierSection,
    _candidate_record,
    _source_declarations,
    _SourceDeclaration,
    add_candidate,
)
from core.runtime.persistence import PersistenceError, load_strict_json
from core.runtime.workspace import (
    CORPUS_STATE,
    LoadedWorkspace,
    WorkspaceError,
    create_workspace,
    load_workspace,
)

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_INVALID = 3
EXIT_CONFLICT = 4
EXIT_IO = 5

LOOSE_SECTION = "loose_material"

_EXIT_BY_CODE = {
    "INVALID_STATE": EXIT_INVALID,
    "CONFLICT": EXIT_CONFLICT,
    "UNSAFE_DESTINATION": EXIT_CONFLICT,
    "IO": EXIT_IO,
}


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else EXIT_USAGE
    try:
        return args.handler(args)
    except ManualAdapterError as exc:
        return _fail(args, "INVALID_STATE", exc.reason)
    except (WorkspaceError, AssimilationError, PersistenceError) as exc:
        return _fail(args, exc.code, exc.reason)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="core.runtime.cli",
        description="Prepara el workspace de asimilación de un foro. No publica nada.",
    )
    parser.add_argument("--json", action="store_true", help="salida en JSON")
    commands = parser.add_subparsers(dest="command", required=True, metavar="comando")

    assimilation = commands.add_parser("assimilation", help="workspace de asimilación")
    groups = assimilation.add_subparsers(dest="group", required=True, metavar="acción")

    init = groups.add_parser("init", help="importa un expediente listo a un workspace externo")
    init.add_argument("--dossier", required=True, type=Path, help="carpeta del expediente")
    _workspace_argument(init)
    init.set_defaults(handler=_assimilation_init, action_name="assimilation.init")

    status = groups.add_parser("status", help="comprueba la integridad del workspace")
    _workspace_argument(status)
    status.set_defaults(handler=_assimilation_status, action_name="assimilation.status")

    source = groups.add_parser("source", help="consulta las fuentes del expediente copiado")
    source_actions = source.add_subparsers(dest="source_action", required=True, metavar="acción")
    source_list = source_actions.add_parser("list", help="lista las fuentes declaradas")
    _workspace_argument(source_list)
    source_list.set_defaults(handler=_source_list, action_name="assimilation.source.list")
    source_show = source_actions.add_parser("show", help="muestra el texto de una fuente")
    _workspace_argument(source_show)
    source_show.add_argument("--section", required=True,
                             choices=[s.value for s in DossierSection] + [LOOSE_SECTION])
    source_show.add_argument("--source-id", required=True)
    source_show.add_argument("--source-version", required=True)
    passage = source_show.add_mutually_exclusive_group()
    passage.add_argument("--declared-passage", help="pasaje declarado en el expediente")
    passage.add_argument("--without-declared-passage", action="store_true",
                         help="la declaración sin pasaje")
    source_show.set_defaults(handler=_source_show, action_name="assimilation.source.show")

    candidate = groups.add_parser("candidate", help="candidatos de asimilación pendientes")
    candidate_actions = candidate.add_subparsers(dest="candidate_action", required=True,
                                                 metavar="acción")
    add = candidate_actions.add_parser("add", help="añade un candidato citado (queda pendiente)")
    _workspace_argument(add)
    add.add_argument("--input", required=True, type=Path, help="archivo JSON del candidato")
    add.set_defaults(handler=_candidate_add, action_name="assimilation.candidate.add")
    candidate_list = candidate_actions.add_parser("list", help="lista los candidatos")
    _workspace_argument(candidate_list)
    candidate_list.set_defaults(handler=_candidate_list, action_name="assimilation.candidate.list")
    show = candidate_actions.add_parser("show", help="muestra un candidato")
    _workspace_argument(show)
    show.add_argument("--candidate-id", required=True)
    show.add_argument("--version", type=int, help="versión concreta (por defecto, la última)")
    show.set_defaults(handler=_candidate_show, action_name="assimilation.candidate.show")
    return parser


def _workspace_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace", required=True, type=Path, help="carpeta del workspace")


def _checkout() -> Path:
    return Path(__file__).resolve().parents[2]


def _load(args: argparse.Namespace) -> LoadedWorkspace:
    return load_workspace(args.workspace, expected_core_root=_checkout())


# --- assimilation init / status ---------------------------------------------------------------


def _assimilation_init(args: argparse.Namespace) -> int:
    dossier = load_manual_dossier(args.dossier)
    result = create_workspace(
        dossier, dossier_dir=args.dossier, workspace=args.workspace, core_root=_checkout()
    )
    workspace = result.workspace
    forum_id = workspace.config.forum_id
    root = str(workspace.workspace_root)
    if args.json:
        _emit({"ok": True, "action": args.action_name, "created": result.created,
               "forum_id": forum_id, "workspace": root})
    elif result.created:
        _line(f"Workspace creado para el foro «{forum_id}» en {root}.")
    else:
        _line(f"El workspace del foro «{forum_id}» ya existía con el mismo contenido: {root}.")
    return EXIT_OK


def _assimilation_status(args: argparse.Namespace) -> int:
    workspace = _load(args)
    forum_id = workspace.config.forum_id
    root = str(workspace.workspace_root)
    if args.json:
        _emit({"ok": True, "action": args.action_name, "forum_id": forum_id,
               "integrity": "OK", "workspace": root})
    else:
        _line(f"Workspace íntegro del foro «{forum_id}» en {root} "
              f"(revisión del corpus {workspace.corpus_revision}).")
    return EXIT_OK


# --- assimilation source ----------------------------------------------------------------------


def _source_list(args: argparse.Namespace) -> int:
    workspace = _load(args)
    declarations = _source_declarations(workspace.dossier)
    if args.json:
        _emit({"ok": True, "action": args.action_name,
               "sources": [_source_json(d) for d in declarations],
               "workspace": str(workspace.workspace_root)})
    elif not declarations:
        _line("No hay fuentes.")
    else:
        for declaration in declarations:
            _line(_source_line(declaration))
    return EXIT_OK


def _source_show(args: argparse.Namespace) -> int:
    workspace = _load(args)
    section = None if args.section == LOOSE_SECTION else DossierSection(args.section)
    matches = [d for d in _source_declarations(workspace.dossier)
               if (d.section, d.source_id, d.source_version)
               == (section, args.source_id, args.source_version)]
    if args.without_declared_passage:
        matches = [d for d in matches if d.declared_passage is None]
    elif args.declared_passage is not None:
        matches = [d for d in matches if d.declared_passage == args.declared_passage]
    if not matches:
        raise AssimilationError("INVALID_STATE", "no hay ninguna fuente declarada con esa "
                                                 "sección, id, versión y pasaje; consulta "
                                                 "«assimilation source list»")
    if len(matches) > 1:
        options = ", ".join("--without-declared-passage" if d.declared_passage is None
                            else f"--declared-passage {json.dumps(d.declared_passage, ensure_ascii=False)}"
                            for d in matches)
        raise AssimilationError("INVALID_STATE", f"esa fuente se declara con {len(matches)} "
                                                 f"pasajes; elige uno: {options}")
    declaration = matches[0]
    if args.json:
        _emit({"ok": True, "action": args.action_name,
               "source": {**_source_json(declaration), "literal_text": declaration.literal_text},
               "workspace": str(workspace.workspace_root)})
        return EXIT_OK
    _line(_source_line(declaration))
    lines = declaration.literal_text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    width = len(str(len(lines)))
    for number, line in enumerate(lines, start=1):
        _write_exact(f"{number:>{width}} | {line.rstrip(chr(13))}\n")
    return EXIT_OK


def _source_json(declaration: _SourceDeclaration) -> dict[str, object]:
    return {
        "candidate_eligible": declaration.candidate_eligible,
        "declared_passage": declaration.declared_passage,
        "dossier_section": _section_name(declaration),
        "domain": declaration.domain.value if declaration.domain is not None else None,
        "source_id": declaration.source_id,
        "source_sha256": declaration.source_sha256,
        "source_version": declaration.source_version,
    }


def _source_line(declaration: _SourceDeclaration) -> str:
    passage = "null" if declaration.declared_passage is None else declaration.declared_passage
    domain = "null" if declaration.domain is None else declaration.domain.value
    eligible = "SI" if declaration.candidate_eligible else "NO"
    return (f"{_section_name(declaration)} | {declaration.source_id} | "
            f"v{declaration.source_version} | pasaje={passage} | "
            f"sha256={declaration.source_sha256} | dominio={domain} | candidato={eligible}")


def _section_name(declaration: _SourceDeclaration) -> str:
    return LOOSE_SECTION if declaration.section is None else declaration.section.value


# --- assimilation candidate -------------------------------------------------------------------


def _candidate_add(args: argparse.Namespace) -> int:
    workspace = _load(args)
    value = load_strict_json(args.input)
    result = add_candidate(workspace.workspace_root / CORPUS_STATE, dossier=workspace.dossier,
                           expected_revision=workspace.corpus_revision, value=value)
    candidate = result.candidate
    if args.json:
        _emit({"ok": True, "action": args.action_name, "candidate_id": candidate.candidate_id,
               "candidate_sha256": candidate.candidate_sha256,
               "corpus_revision": result.corpus_revision, "created": result.created,
               "version": candidate.version, "workspace": str(workspace.workspace_root)})
    else:
        prefix = "Candidato añadido" if result.created else "Candidato ya existente"
        _line(f"{prefix}: {_candidate_line(candidate)}")
        _line(f"Revisión del corpus: {result.corpus_revision}.")
    return EXIT_OK


def _candidate_list(args: argparse.Namespace) -> int:
    workspace = _load(args)
    candidates = workspace.candidates
    if args.json:
        _emit({"ok": True, "action": args.action_name,
               "candidates": [_candidate_summary(c) for c in candidates],
               "corpus_revision": workspace.corpus_revision,
               "workspace": str(workspace.workspace_root)})
    elif not candidates:
        _line("No hay candidatos.")
    else:
        for candidate in candidates:
            _line(_candidate_line(candidate))
    return EXIT_OK


def _candidate_show(args: argparse.Namespace) -> int:
    workspace = _load(args)
    versions = [c for c in workspace.candidates if c.candidate_id == args.candidate_id]
    if args.version is not None:
        versions = [c for c in versions if c.version == args.version]
    if not versions:
        wanted = args.candidate_id if args.version is None else f"{args.candidate_id} v{args.version}"
        raise AssimilationError("INVALID_STATE", f"no existe el candidato {wanted}")
    candidate = versions[-1]
    if args.json:
        _emit({"ok": True, "action": args.action_name,
               "candidate": _candidate_record(candidate, include_hash=True),
               "corpus_revision": workspace.corpus_revision,
               "workspace": str(workspace.workspace_root)})
        return EXIT_OK
    _line(_candidate_line(candidate))
    for citation in candidate.citations:
        passage = "null" if citation.declared_passage is None else citation.declared_passage
        _line(f"Cita: {citation.dossier_section.value} | {citation.source_id} | "
              f"v{citation.source_version} | pasaje={passage} | "
              f"sha256={citation.source_sha256} | caracteres {citation.start}-{citation.end}")
    _line("Texto (exacto, hasta «Fin del texto.»):")
    _write_exact(candidate.text)
    if not candidate.text.endswith("\n"):
        _write_exact("\n(el texto no termina en salto de línea)\n")
    _line("Fin del texto.")
    return EXIT_OK


def _candidate_summary(candidate: AssimilationCandidate) -> dict[str, object]:
    return {
        "candidate_id": candidate.candidate_id,
        "candidate_sha256": candidate.candidate_sha256,
        "class": candidate.candidate_class.value,
        "domain": candidate.domain.value,
        "review_status": candidate.review_status.value,
        "version": candidate.version,
    }


def _candidate_line(candidate: AssimilationCandidate) -> str:
    line = (f"{candidate.candidate_id} v{candidate.version} | {candidate.candidate_class.value} | "
            f"{candidate.domain.value} | {candidate.review_status.value} | "
            f"sha256={candidate.candidate_sha256}")
    return f"{line} | REQUIERE CONFIRMACIÓN" if candidate.requires_confirmation else line


# --- output -----------------------------------------------------------------------------------


def _fail(args: argparse.Namespace, code: str, reason: str) -> int:
    if args.json:
        _emit({"ok": False, "code": code, "message": reason})
    else:
        _line(f"Error ({code}): {reason}", sys.stderr)
    return _EXIT_BY_CODE[code]


def _line(text: str, stream=None) -> None:
    _write_exact(text + "\n", stream)


def _write_exact(text: str, stream=None) -> None:
    """All CLI output: exact UTF-8 with LF line ends, no newline translation or replacement.

    User content (candidate texts, source literals, passages) must reach the human unchanged,
    whatever the console code page.
    """
    stream = sys.stdout if stream is None else stream
    buffer = getattr(stream, "buffer", None)
    if buffer is None:  # an in-memory text stream, e.g. in tests
        stream.write(text)
        return
    stream.flush()
    buffer.write(text.encode("utf-8"))
    buffer.flush()


def _emit(payload: dict[str, object]) -> None:
    _line(json.dumps(payload, ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
