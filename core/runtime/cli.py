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
from core.runtime.workspace import WorkspaceError, create_workspace, load_workspace

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_INVALID = 3
EXIT_CONFLICT = 4
EXIT_IO = 5

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
        return _fail(args, EXIT_INVALID, "INVALID_STATE", exc.reason)
    except WorkspaceError as exc:
        return _fail(args, _EXIT_BY_CODE[exc.code], exc.code, exc.reason)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="core.runtime.cli",
        description="Prepara el workspace de asimilación de un foro. No publica nada.",
    )
    parser.add_argument("--json", action="store_true", help="salida en JSON")
    commands = parser.add_subparsers(dest="command", required=True, metavar="comando")

    assimilation = commands.add_parser("assimilation", help="workspace de asimilación")
    actions = assimilation.add_subparsers(dest="action", required=True, metavar="acción")

    init = actions.add_parser("init", help="importa un expediente listo a un workspace externo")
    init.add_argument("--dossier", required=True, type=Path, help="carpeta del expediente")
    init.add_argument("--workspace", required=True, type=Path, help="carpeta del workspace")
    init.set_defaults(handler=_assimilation_init, action_name="assimilation.init")

    status = actions.add_parser("status", help="comprueba la integridad del workspace")
    status.add_argument("--workspace", required=True, type=Path, help="carpeta del workspace")
    status.set_defaults(handler=_assimilation_status, action_name="assimilation.status")
    return parser


def _checkout() -> Path:
    return Path(__file__).resolve().parents[2]


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
        print(f"Workspace creado para el foro «{forum_id}» en {root}.")
    else:
        print(f"El workspace del foro «{forum_id}» ya existía con el mismo contenido: {root}.")
    return EXIT_OK


def _assimilation_status(args: argparse.Namespace) -> int:
    workspace = load_workspace(args.workspace, expected_core_root=_checkout())
    forum_id = workspace.config.forum_id
    root = str(workspace.workspace_root)
    if args.json:
        _emit({"ok": True, "action": args.action_name, "forum_id": forum_id,
               "integrity": "OK", "workspace": root})
    else:
        print(f"Workspace íntegro del foro «{forum_id}» en {root} "
              f"(revisión del corpus {workspace.corpus_revision}).")
    return EXIT_OK


def _fail(args: argparse.Namespace, exit_code: int, code: str, reason: str) -> int:
    if args.json:
        _emit({"ok": False, "code": code, "message": reason})
    else:
        print(f"Error ({code}): {reason}", file=sys.stderr)
    return exit_code


def _emit(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
